# Dependency cục bộ từ `files`, `fileTree` và hạn chế metadata trong Gradle

## 1. Bối cảnh và mục tiêu

Một dự án Java đôi khi cần dùng JAR chỉ có sẵn trên máy, được nhà cung cấp gửi dưới dạng binary, hoặc chưa được publish vào Maven/Ivy repository. Gradle cho phép đưa JAR đó vào classpath bằng `files(...)` hoặc lấy nhiều file theo mẫu tên bằng `fileTree(...)`. Hai API này tiện dụng nhưng thường dễ bị hiểu nhầm: **đưa JAR vào classpath không đồng nghĩa Gradle đã hiểu JAR là một module có group, version, transitive dependencies và variants**.

Bài học giúp bạn:

- Khai báo file dependency đúng scope trong **Gradle Kotlin DSL** (`build.gradle.kts`).
- Phân biệt `files("libs/a.jar")` với `fileTree("libs") { include("*.jar") }` và module dependency `group:name:version`.
- Hiểu vì sao JAR cục bộ **không mang metadata module** và Gradle không tự resolve dependency bắc cầu cho JAR.
- Tạo và chạy một ứng dụng **Java 17+** sử dụng JAR local hoàn toàn bằng JDK tools và Gradle Wrapper.
- Phát hiện vấn đề do thiếu transitives, class trùng, thứ tự FileTree, khác biệt compile/runtime và artifact publication.
- Nối một JAR **do task sinh ra** với producer bằng task-output provider/`builtBy`.
- Biết lúc nào nên chuyển sang **project dependency** hoặc module publish với POM/Gradle Module Metadata.
- Chẩn đoán bằng `dependencies`, `jar --list`, `jdeps`, Gradle logs và một consumer project độc lập.

Các lệnh `./gradlew` minh họa Linux/macOS; dùng `.\gradlew.bat` trên Windows PowerShell. Những nơi có mã chưa độc lập được đánh dấu rõ; không đoán rằng một file demo chưa tồn tại có thể tự xuất hiện.

## 2. Ba loại dependency không giống nhau

| Loại | Cách khai báo | Gradle biết gì? | Đặc trưng |
| --- | --- | --- | --- |
| **Module dependency** | `implementation("org.example:lib:1.0")` | Module coordinates, metadata từ repository, có thể có phiên bản/variants/transitives. | Tốt nhất cho thư viện phát hành và chia sẻ. |
| **Project dependency** | `implementation(project(":lib"))` | Project component, outgoing variants, task và dependency edges trong build. | Tốt cho module mã nguồn cùng build. |
| **File dependency** | `implementation(files("libs/lib.jar"))` | Một đường dẫn file/tập file được thêm vào configuration. | Không có module metadata, không tự suy ra transitives. |
| **FileTree dependency** | `implementation(fileTree("libs") { include("*.jar") })` | Các file được chọn theo pattern. | Vẫn là file dependency; thứ tự file không đảm bảo. |

**Điểm quan trọng:** trong `implementation(files("libs/a.jar"))`, `implementation` cho biết phạm vi sử dụng (configuration), còn `files(...)` cho biết nguồn dữ liệu là một file/tập file, **không phải** module từ repository. Gradle có thể fingerprint nội dung JAR như classpath input cho `JavaCompile`; việc thiếu **module metadata** không có nghĩa Gradle mù trước mọi thay đổi bytes của file.

### Từ module đến artifact

Với module dependency thông thường, Gradle đọc metadata như `.module`, Maven `pom.xml` hoặc Ivy `ivy.xml` để xác định dependencies, version rules và variants, rồi resolve artifacts. Với `files(...)`, Gradle đã có một file path trực tiếp, nên **không có graph metadata để truy ra JAR bắc cầu**. Tên file `commons-codec-1.15.jar` trông giống Maven artifact không tự mang `group = commons-codec` và `version = 1.15` vào Gradle component model.

## 3. `files(...)`: liệt kê file trực tiếp

Cách cơ bản trên `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

dependencies {
    implementation(files("libs/vendor-api.jar"))
    runtimeOnly(files("libs/vendor-runtime.jar", "libs/vendor-bridge.jar"))
    testImplementation(files("libs/test-helper.jar"))
}
~~~

Đây là **mẫu cú pháp**, giả định các JAR đã thực sự tồn tại. Không có dependency tự động được tải chỉ vì bạn viết tên file.

- `implementation(files(...))` đưa JAR vào compile và runtime classpath thông thường của Java project.
- `compileOnly(files(...))` chỉ phục vụ biên dịch, không tự có trên runtime classpath.
- `runtimeOnly(files(...))` có lúc chạy, không đủ để mã nguồn chính trực tiếp import class lúc compile.
- `testImplementation(files(...))` phục vụ test source set, không tự đưa JAR vào artifact production.
- Những bucket này xuất hiện khi plugin Java/Java Library/Application hoặc plugin phù hợp được áp dụng. Chỉ viết `dependencies` trong project trống không tự tạo `implementation`.

Đường dẫn `libs/vendor-api.jar` là **đường dẫn tương đối của project** đang cấu hình. Trong multi-project build, `app/build.gradle.kts` với `files("libs/x.jar")` thường trỏ tới `app/libs/x.jar`, không phải tự động root `libs/x.jar`. Nếu cần file ở root, chỉ rõ bằng Gradle layout API thích hợp; tránh đường dẫn tuyệt đối riêng từng máy như `C:\Users\alice\Downloads\vendor.jar`.

### Nhiều file explicit

~~~kotlin
dependencies {
    implementation(files("libs/a.jar", "libs/b.jar", "libs/c.jar"))
}
~~~

Cách này giúp người review thấy danh sách file chính xác. Không “tối ưu” bằng việc chuyển sang glob nếu bạn chỉ có vài JAR: một file mới không nên lặng lẽ nhập classpath. `files` không phải cú pháp tải module từ Maven: `repositories { mavenCentral() }` không làm Gradle tự kiếm transitive metadata cho các file đã được chỉ định bằng path.

## 4. Bài thực hành Java 17 chạy được, không cần repository bên ngoài

Mục tiêu: tự biên dịch một class Java thành `libs/local-greeter.jar`, rồi chạy ứng dụng Gradle dùng class đó. Tất cả mã có thể biên dịch bằng JDK 17+.

### 4.1. Cấu trúc

~~~text
local-dependency-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── src/local/java/demo/local/LocalGreeter.java
├── src/main/java/example/App.java
└── libs/
    └── local-greeter.jar   # sẽ được tạo bằng JDK jar
~~~

Giả định bạn đã có Gradle Wrapper hoạt động trong dự án thử. `settings.gradle.kts`:

~~~kotlin
rootProject.name = "local-dependency-demo"
~~~

`src/local/java/demo/local/LocalGreeter.java`:

~~~java
package demo.local;

public final class LocalGreeter {
    private LocalGreeter() {
    }

    public static String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

`src/main/java/example/App.java`:

~~~java
package example;

import demo.local.LocalGreeter;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(LocalGreeter.greet("Gradle"));
    }
}
~~~

### 4.2. Build script

Toàn bộ `build.gradle.kts`:

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
    mainClass.set("example.App")
}

dependencies {
    implementation(files("libs/local-greeter.jar"))
}
~~~

Không cần `mavenCentral()` vì library này là file dependency. `application` bao gồm chức năng Java và tạo task `run`; Java toolchain yêu cầu JDK 17 phù hợp hoặc cơ chế provisioning đã cấu hình.

### 4.3. Tạo JAR bằng JDK

Linux/macOS, chạy ở root:

~~~bash
mkdir -p libs build/local-classes
javac -encoding UTF-8 -d build/local-classes src/local/java/demo/local/LocalGreeter.java
jar --create --file libs/local-greeter.jar -C build/local-classes .
jar --list --file libs/local-greeter.jar
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force libs | Out-Null
New-Item -ItemType Directory -Force build/local-classes | Out-Null
javac -encoding UTF-8 -d build/local-classes src/local/java/demo/local/LocalGreeter.java
jar --create --file libs/local-greeter.jar -C build/local-classes .
jar --list --file libs/local-greeter.jar
~~~

`javac -encoding UTF-8` giữ đúng chuỗi tiếng Việt nếu source được lưu bằng UTF-8. `jar --create` đóng `demo/local/LocalGreeter.class` vào `libs/local-greeter.jar`. `jar --list` hiển thị danh sách entries, cần nhìn thấy class kể trên. Không nên gọi `javac` từ `build.gradle.kts` ở cấp cấu hình như một side effect chỉ để tạo JAR; đây là quy trình tạo dữ liệu mẫu bên ngoài Gradle.

### 4.4. Chạy và xác nhận output

~~~bash
./gradlew -q run
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Stdout của `example.App.main` là:

~~~text
Xin chào, Gradle!
~~~

Thông báo khác của Gradle/daemon có thể phụ thuộc phiên bản và môi trường, đặc biệt lần đầu chọn toolchain. Nếu không thấy kết quả, kiểm tra `jar --list`, package name, classpath, file path và trạng thái `compileJava`.

Điểm rút ra:

1. App **biên dịch** nhờ file JAR được Gradle đưa lên compileClasspath.
2. App **chạy** nhờ JAR được đưa lên runtimeClasspath.
3. Gradle **không tự biết group/version hoặc transitive metadata** chỉ từ `libs/local-greeter.jar`.
4. Nếu sửa class `LocalGreeter`, tái tạo JAR rồi chạy lại, Gradle có thể phát hiện classpath input thay đổi. **Thiếu module metadata không đồng nghĩa bỏ qua nội dung JAR trong up-to-date checks**.
5. `dependencyInsight` với group/name tưởng tượng không biến file local thành module: cần xem path/classpath và nội dung artifact khi chẩn đoán.

## 5. `fileTree(...)`: chọn một nhóm file theo pattern

Khi vendor giao một thư mục nhiều JAR:

~~~text
libs/
├── core.jar
├── helper.jar
├── helper-sources.jar
├── tools/
│   ├── image.jar
│   └── debug-tool.jar
└── docs/
    └── notes.txt
~~~

Cách liệt kê toàn bộ JAR:

~~~kotlin
plugins {
    java
}

dependencies {
    implementation(fileTree("libs") {
        include("**/*.jar")
        exclude("**/*-sources.jar")
        exclude("**/*-javadoc.jar")
        exclude("**/debug-*.jar")
    })
}
~~~

`fileTree("libs")` tạo FileTree cho thư mục này. `include`/`exclude` lọc file bằng **glob pattern**. `**/*.jar` phù hợp khi cần cả file trong thư mục con; `*.jar` thường được dùng cho tập JAR ở cấp thư mục trực tiếp. Nếu cần giới hạn chỉ một loại JAR, hãy dùng naming convention rõ ràng và kiểm tra tập file đã chọn thực tế.

### So sánh nhanh với `files`

| Đặc điểm | `files("libs/a.jar", "libs/b.jar")` | `fileTree("libs") { include("*.jar") }` |
| --- | --- | --- |
| Chọn gì? | Hai đường dẫn explicit. | Mọi file match pattern. |
| Thêm file mới | Không tự trở thành dependency. | Có thể tự được chọn. |
| Review build logic | Có danh sách cụ thể. | Cần xem nội dung thư mục. |
| Thứ tự file | Danh sách explicit dễ kiểm soát hơn. | **Không được Gradle đảm bảo ổn định**. |
| Group/version | Không có. | Không có. |
| Transitive metadata | Không có. | Không có. |
| Áp dụng module conflict resolution | Không như dependency có module identity. | Cũng không. |
| Khả năng tái lập | Tốt hơn nếu file bytes/đường dẫn cố định. | Dễ dao động khi file set/order đổi. |

**Lưu ý quan trọng từ tài liệu Gradle:** thứ tự các file trong `FileTree` có thể thay đổi **ngay trên cùng một máy**. Điều này ảnh hưởng các task có classpath/order-sensitive inputs và khả năng dùng cache. Đừng dùng fileTree để lựa chọn “JAR mới nhất”, “JAR ưu tiên”, hoặc coi thứ tự glob là một chính sách version resolution.

### Những lỗi do glob quá rộng

- Thư mục chứa cả `library-1.0.jar` và `library-2.0.jar`: cả hai có thể cùng lên classpath, không có module conflict resolution giúp chọn một version.
- Thư mục có `library-sources.jar`, `library-javadoc.jar`: fileTree có thể đưa nhầm vào runtimeClasspath.
- Có một JAR mới do IDE/download đặt vào `libs`: nó có thể gia nhập classpath khi build script không đổi.
- Những bản JVM/Gradle/task khác nhau có thể xử lý thứ tự classpath hơi khác; nếu có **class trùng package/name** trong nhiều JAR, hành vi runtime dễ khó đoán.

Với số lượng ít, **ưu tiên `files` explicit**. Với thư viện chia sẻ dài hạn, **ưu tiên publish module có metadata thật**.

## 6. Hạn chế metadata: khác với module dependency ra sao?

Một module từ Maven/Ivy/Gradle repository có thể có:

- Danh tính **group:name:version**, nguồn gốc và version metadata.
- Danh sách dependency khác mà nó cần (transitives).
- Scopes và version constraints.
- Gradle variants/attributes, capabilities, artifact variants, Java API/runtime distinction.
- Artifact được publish có tổ chức và kiểm tra tính toàn vẹn theo chính sách repository.

File dependency chỉ mô tả file: `libs/vendor.jar`. Gradle không mở JAR rồi “đoán POM” hoặc tên các thư viện nó cần.

### Hệ quả 1: không tự resolve transitive dependencies

Giả sử `vendor-client.jar` được biên dịch với API từ `commons-codec`. Chỉ khai báo:

~~~kotlin
dependencies {
    implementation(files("libs/vendor-client.jar"))
}
~~~

**Không** làm Gradle tự thêm `commons-codec:commons-codec`. Nếu public method signature của vendor-client đụng type từ codec, bạn có thể gặp lỗi **compile**. Nếu app chỉ gọi một method mà bên trong vendor-client mới nạp codec, compile có thể thành công nhưng lúc chạy có thể ném `NoClassDefFoundError` hoặc `ClassNotFoundException`.

Sửa tạm khi đã biết đúng dependency:

~~~kotlin
repositories {
    mavenCentral()
}

dependencies {
    implementation(files("libs/vendor-client.jar"))
    implementation("commons-codec:commons-codec:1.15")
}
~~~

Gradle lúc này nhận `commons-codec` như một **dependency riêng của ứng dụng**, không phải một cạnh bắc cầu được khôi phục từ metadata của `vendor-client.jar`. Nếu vendor có POM chính thức, tốt hơn nên sử dụng hoặc publish module đúng cách thay vì tự duy trì danh sách JAR thủ công.

### Hệ quả 2: không có version conflict resolution theo module identity

Hai file `libs/codec-1.11.jar` và `libs/codec-1.15.jar` không mang group/name để Gradle coi là hai versions của **cùng module** rồi chọn một. Nếu cả hai vào classpath, chúng có thể chứa class giống hệt FQCN mà JVM chọn theo thứ tự. Một **dependency constraint** như `constraints { implementation("commons-codec:commons-codec:1.15") }` chỉ tác động **module identity** trong graph, không tự thay thế file `codec-1.11.jar` bằng một JAR khác.

Tương tự, version catalog alias chỉ là cách tham chiếu module coordinates; nó không gán version logic cho các JAR trong `libs/`.

### Hệ quả 3: variant/capability metadata bị mất

Với module/project dependency có metadata, Gradle có thể chọn variant `java-api` khi compile và `java-runtime` khi chạy; có thể giải quyết capabilities conflicts. Với local JAR, bạn đưa **chính file ấy** vào configuration tương ứng. Gradle không biết local JAR nào là API variant, runtime variant, bản phù hợp Java 17 hay bản có feature khác trừ khi bạn xây dựng model bổ sung.

### Hệ quả 4: công cụ audit không có đầy đủ thông tin

Một file JAR có tên dễ hiểu vẫn không nói chắc nhà phát hành, version, license hoặc provenance. Các công cụ chỉ đọc module dependency graph có thể bỏ sót local binary. Với JAR vendor, cần quản lý checksum, nguồn tải, license, version và kế hoạch cập nhật ngoài graph khi chưa có metadata. Không nên dùng JAR local để lách các chính sách dependency kiểm soát an toàn.

## 7. Thí nghiệm có hai JAR: app chạy thiếu dependency bắc cầu

Một ví dụ Java 17 không dùng library bên ngoài minh họa trực tiếp hậu quả thiếu metadata.

### Hai class source độc lập

`src/local/java/demo/base/BaseFormatter.java`:

~~~java
package demo.base;

public final class BaseFormatter {
    private BaseFormatter() {
    }

    public static String format(String name) {
        return "Hello, " + name;
    }
}
~~~

`src/local/java/demo/adapter/Adapter.java`:

~~~java
package demo.adapter;

import demo.base.BaseFormatter;

public final class Adapter {
    private Adapter() {
    }

    public static String message() {
        return BaseFormatter.format("Gradle");
    }
}
~~~

Tạo hai JAR bằng Linux/macOS JDK 17:

~~~bash
mkdir -p libs build/base-classes build/adapter-classes
javac -d build/base-classes src/local/java/demo/base/BaseFormatter.java
jar --create --file libs/base.jar -C build/base-classes .
javac -cp libs/base.jar -d build/adapter-classes src/local/java/demo/adapter/Adapter.java
jar --create --file libs/adapter.jar -C build/adapter-classes .
~~~

Trên Windows PowerShell, tạo `libs` và hai thư mục `build/...-classes` trước bằng `New-Item -ItemType Directory -Force ... | Out-Null`, sau đó chạy các lệnh `javac` và `jar` tương tự. `Adapter.class` dùng `BaseFormatter.class` nhưng **không chứa** class BaseFormatter trong `adapter.jar`.

`src/main/java/example/App.java`:

~~~java
package example;

import demo.adapter.Adapter;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(Adapter.message());
    }
}
~~~

`settings.gradle.kts` vẫn đặt tên project và `build.gradle.kts` dùng `application`, `mainClass` bằng `example.App`. Ban đầu chỉ khai báo:

~~~kotlin
dependencies {
    implementation(files("libs/adapter.jar"))
}
~~~

`App` chỉ cần class `Adapter` để compile và method `message()` có signature trả `String`, nên compile có thể thành công. Nhưng khi chạy, JVM sẽ cố tải `demo.base.BaseFormatter` **không có ở runtimeClasspath**. Một lỗi có thể gặp là:

~~~text
java.lang.NoClassDefFoundError: demo/base/BaseFormatter
~~~

Đây là **loại lỗi kỳ vọng**, không phải toàn bộ stacktrace bất biến của JVM/Gradle. Thêm file còn thiếu:

~~~kotlin
dependencies {
    implementation(files("libs/adapter.jar", "libs/base.jar"))
}
~~~

Chạy `./gradlew -q run`, stdout của `main` là:

~~~text
Hello, Gradle
~~~

**Bản chất:** khi `adapter.jar` được compile bằng `base.jar`, thông tin “adapter phụ thuộc base” **không trở thành metadata module Gradle**. Consumer chỉ nhận những JAR đã được khai báo. Nếu hai JAR được publish như modules cùng POM/Gradle Module Metadata mô tả quan hệ, consumer có thể nhận base transitively.

## 8. File dependency được publish như thế nào?

Đây là một giới hạn quan trọng được Gradle nói rõ: **file dependencies không được đưa vào published dependency descriptor** (POM/Ivy/Gradle module publication theo cách một module dependency bình thường được khai báo). Vì vậy, một thư viện chỉ dùng `api(files("libs/vendor-api.jar"))` khi đang làm việc trong monorepo **không đủ** để đảm bảo consumer từ repository nhận vendor-api.jar.

Ví dụ project `:sdk`:

~~~kotlin
plugins {
    `java-library`
}

dependencies {
    api(files("libs/vendor-api.jar"))
}
~~~

Nếu project `:app` cùng build dùng `implementation(project(":sdk"))`, file dependency của `:sdk` có thể tham gia **transitive dependencies trong cùng build**, tùy variant/model. Đây là khả năng được tài liệu Gradle nêu rõ. Nhưng sau khi `:sdk` được **publish** thành module để một **build độc lập** gọi `implementation("com.company:sdk:1.0")`, published dependency descriptor không mang một module dependency tương ứng cho `vendor-api.jar`. Consumer ngoài có thể bị thiếu class.

**Không đánh đồng hai câu:**
- Trong **cùng một build** file dependencies có thể được truyền theo project dependency.
- Với **published component metadata**, file dependencies không được tự chuyển thành dependencies được publish cho consumer ngoài.

**Giải pháp:** xuất bản binary vendor thành module `group:name:version` với metadata và những transitives thực sự cần, rồi cho `:sdk` khai báo module dependency với `api` hoặc `implementation` đúng vị trí. Sau khi publish, tạo một **consumer project độc lập** chỉ dùng repository/artifact publish và chạy compile/runtime tests. Không kết luận an toàn chỉ vì project monorepo của bạn chạy được.

## 9. Khi JAR được tạo bởi một Gradle task khác

Nếu `libs/vendor.jar` đã tồn tại trước build, `files(...)` chỉ đúng path. Nhưng nếu file được một **task producer** tạo ra, đừng viết mỗi `files("build/generated/helper.jar")` rồi mong Gradle tự biết phải chạy producer trước consumer.

Có hai yếu tố riêng biệt:

1. **Task dependency/producer association** để file được sinh trước khi task tiêu thụ đọc.
2. **Module metadata** để biết dependency bắc cầu, variants và version. Có yếu tố 1 không tự đem lại yếu tố 2.

### File collection từ TaskProvider

Mảnh `build.gradle.kts` minh họa:

~~~kotlin
plugins {
    java
}

val generateLocalJar by tasks.registering(Jar::class) {
    archiveFileName.set("generated-helper.jar")
    destinationDirectory.set(layout.buildDirectory.dir("generated-jars"))
    from(layout.projectDirectory.dir("prebuilt-classes"))
}

dependencies {
    implementation(files(generateLocalJar))
}
~~~

Đoạn code **giả định thư mục `prebuilt-classes` đã chứa các `.class`**; task `Jar` không biên dịch source. `files(generateLocalJar)` sử dụng output của TaskProvider và có thể mang thông tin dependency để Gradle sắp xếp producer trước consumer. Với nguồn Java trong cùng build, `project(":lib")` thường là lựa chọn tốt hơn khi có thể.

### Nếu bạn chỉ biết output path: `builtBy`

Mảnh minh họa khác, **không dán đồng thời với mẫu trùng tên nếu chưa thiết kế lại**:

~~~kotlin
val localJar = files(
    layout.buildDirectory.file("generated-jars/generated-helper.jar")
) {
    builtBy("generateLocalJar")
}

dependencies {
    implementation(localJar)
}
~~~

Ở đây `builtBy` nói rõ task nào tạo file; **nó không tự viết file**, và không bổ sung POM/module metadata. Task `generateLocalJar` phải thực sự tồn tại và tạo output tương ứng. Nếu producer còn cần inputs/outputs chuẩn để up-to-date checking và Build Cache, chúng cũng phải được khai báo chính xác.

**Anti-pattern:**

~~~kotlin
dependencies {
    implementation(files("build/generated-jars/generated-helper.jar"))
}
~~~

Nếu JAR chỉ được sinh sau một task khác nhưng không có producer association, Gradle có thể compile trước khi file xuất hiện hoặc dựa vào file cũ tình cờ còn trong build directory. Không dùng `afterEvaluate` hoặc ghi file ngay khi configuration để “sửa” thứ tự; hãy khai báo quan hệ task và output phù hợp.

## 10. `flatDir` cũng không tạo metadata chuẩn

Trong những dự án legacy thường thấy:

~~~kotlin
repositories {
    flatDir {
        dirs("libs")
    }
}

dependencies {
    implementation("legacy:vendor-client:1.0")
}
~~~

`flatDir` có thể tìm artifact dựa trên tên file và tạo **metadata tạm** từ JAR hiện diện. Nhưng nó **không hỗ trợ POM/Ivy metadata** đầy đủ nên không biết transitive dependencies thật của vendor-client. Gradle khuyến nghị **tránh flatDir** nếu có thể dùng repository chuẩn.

| Phương pháp | Có repo lookup? | Đọc POM/Gradle Module Metadata thật? | Tự giải quyết transitives? |
| --- | --- | --- | --- |
| `files("libs/a.jar")` | Không. | Không. | Không. |
| `fileTree("libs")` | Không. | Không. | Không. |
| `flatDir { dirs("libs") }` | Có theo artifact filename. | Không; metadata tổng hợp. | Không biết transitives thật. |
| Maven/Ivy repository có metadata | Có. | Có, nếu publication đúng. | Có, dựa theo metadata. |
| Project dependency | Không phải tra binary repo. | Dùng Gradle project model/variants. | Có thể qua project graph. |

Nếu Gradle tìm thấy cùng một module cả trong flatDir lẫn repository có metadata thật, Gradle thường ưu tiên metadata thực. FlatDir không phải cách ép override mọi Maven module.

### Tốt hơn: publish module vào Maven/Ivy repository

Cấu trúc Maven repository giả định:

~~~text
repo/
└── com/company/vendor-client/1.0/
    ├── vendor-client-1.0.jar
    └── vendor-client-1.0.pom
~~~

Nếu JAR đã được publish đúng với POM chứa dependencies và tọa độ hợp lệ, consumer có thể khai báo:

~~~kotlin
repositories {
    maven {
        url = uri("repo")
    }
}

dependencies {
    implementation("com.company:vendor-client:1.0")
}
~~~

**Đây là ví dụ tiêu thụ**, không phải quy trình tự động tạo repo/POM. Chỉ đổi tên và chép JAR vào thư mục trên không tự sinh metadata bắc cầu. Cần publish POM/Gradle Module Metadata **đúng** bằng Maven Publish plugin hay quy trình quản lý artifact của tổ chức. Với CI/đa máy, repository nội bộ có kiểm soát thường tốt hơn phụ thuộc một thư mục cục bộ chỉ có trên máy tác giả.

## 11. `@jar`, classifier và file dependency: phân biệt rõ

Gradle có cú pháp **artifact-only notation** với module coordinate như:

~~~kotlin
dependencies {
    // Minh họa cú pháp; artifact com.example:legacy:1.0 không được tạo ở đây.
    implementation("com.example:legacy:1.0@jar")
}
~~~

Đây **không phải** cùng cơ chế với `files("libs/legacy.jar")`: nó vẫn là một declaration dạng module notation yêu cầu artifact extension, nhưng nó có thể **bỏ qua metadata module/transitive/variant resolution** cho request đó. Vì thế dùng `@jar` chỉ để “lấy được một JAR nhanh” có thể làm mất dependencies bắc cầu tương tự khi dùng file local.

**Classifier** như `sources` hoặc `javadoc` cũng không đồng nghĩa Gradle variant. Một module có thể publish artifacts khác nhau nhưng vẫn cần metadata/attributes để biết cái nào dùng lúc compile/runtime. Không đưa `sources.jar` vào classpath chạy chỉ vì glob chọn được file đó.

**Kết luận:** nếu cần module dependency management, dùng module notation bình thường với repository/metadata. Cả `files`, `fileTree`, `flatDir` và artifact-only `@jar` đều có trade-off; không nên lạm dụng chúng để che metadata bị thiếu.

## 12. Version catalogs, constraints, lockfiles và security

Những công cụ quản lý dependency nổi tiếng **không tự sửa được metadata thiếu** của local file.

- **Version catalog**: `libs.versions.toml` định nghĩa alias cho module dependency; nếu bạn khai báo `implementation(files("libs/a.jar"))`, catalog không tự đặt group/version cho file.
- **Dependency constraints**: `constraints { implementation("g:n:1.2") }` quản lý version của **module g:n đã có mặt trong graph**; nó không tìm file `libs/n-1.0.jar` và tự thay bằng bản 1.2.
- **Dependency locking**: khóa resolved versions của module graph để build tái lập; không tự biến một JAR vô danh thành module publish.
- **Dependency verification**: có cơ chế xác thực dependency artifacts theo support của Gradle. Đối với local binary, vẫn phải xác minh checksum/chữ ký/vendor/provenance theo chính sách; không nên mặc định mọi local file được kiểm tra như một module từ repository.
- **SBOM/license audit**: một số công cụ dựa trên module coordinates có thể không có đủ thông tin để xác định file local. Giữ bản kê tên file, hash, nhà cung cấp, license và version tương ứng nếu dự án bắt buộc tích hợp JAR local.

Ví dụ một bản kê ngoài build (không phải cú pháp Gradle):

~~~text
File: libs/vendor-client.jar
Vendor: nhà cung cấp đã được xác thực
Version: phiên bản được ghi trong tài liệu bàn giao
SHA-256: giá trị tính từ đúng file phát hành
Required libraries: danh sách module/JAR theo tài liệu vendor
License: giấy phép được kiểm tra trước khi phân phối
~~~

Đừng chèn giá trị hash giả trong README rồi gọi là bằng chứng. Tính hash trên bytes thật bằng công cụ hệ điều hành/JDK được phép; kiểm tra với giá trị do nguồn đáng tin cung cấp. Không chạy JAR từ nguồn không rõ chỉ để thử xem nó hoạt động.

## 13. Khả năng tái lập: kiểm soát file set và classpath order

Một file dependency dùng path riêng của tác giả làm CI dễ thất bại. Hãy dùng project-relative path hoặc một repository quản lý artifact đúng cách.

Với `fileTree`, cần thêm ba bước kiểm soát:

1. **Giới hạn file set**: include/exclude và quy tắc tên; loại bản cũ, source/doc/test JAR khỏi runtime.
2. **Không dựa vào thứ tự FileTree**: Gradle không bảo đảm thứ tự traversal, thậm chí trên cùng máy. Nếu classpath chứa hai JAR cung cấp cùng fully-qualified class name, không nên dựa vào thứ tự file để “chọn version”.
3. **Theo dõi binary content**: khi JAR được cập nhật mà tên vẫn như cũ, source control, checksum hoặc artifact repository phải ghi nhận bytes. Gradle tasks có thể phát hiện thay đổi classpath input, nhưng audit/versioning vẫn là việc riêng.

Một build “hôm qua chạy được” không tự chứng minh JAR hôm nay có cùng nội dung hoặc giấy phép. Tương tự, chỉ vì `build.gradle.kts` không đổi không có nghĩa tập `fileTree("libs")` không đổi.

## 14. Chẩn đoán bằng Gradle/JDK

Từ ví dụ ở mục 4:

~~~bash
./gradlew --version
./gradlew -q run
./gradlew compileJava --info
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
jar --list --file libs/local-greeter.jar
jdeps libs/local-greeter.jar
~~~

- `--version`: xác định Gradle/JDK thực sự dùng.
- `run`: kiểm tra class có trên runtimeClasspath và chương trình hoạt động.
- `compileJava --info`: tìm lý do task compile bị chạy lại; classpath có thể là input được theo dõi.
- `dependencies --configuration ...`: kiểm tra cách Gradle lập configuration và file dependencies có mặt; report có thể hiển thị `files`, không có cây Maven transitives.
- `jar --list`: xác nhận JAR có class/package đúng, không giúp tự suy ra thông tin POM.
- `jdeps`: phân tích static class references, hữu ích để gợi ý thiếu thư viện nhưng không bảo đảm phát hiện reflection/service loader hay tái tạo publish metadata.
- `dependencyInsight --dependency g:n --configuration runtimeClasspath`: rất hữu ích khi đang phân tích **module** selection, nhưng không nên kỳ vọng nó giải thích GAV cho local file chưa có identity.

### Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| `package ... does not exist` ở compile | JAR không ở compileClasspath, path sai hoặc file không chứa class. | Kiểm tra `implementation(files(...))`, package, `jar --list`. |
| `NoClassDefFoundError` khi run | Dependency bắc cầu thiếu JAR hoặc dùng `compileOnly` sai. | Xem runtimeClasspath, tài liệu vendor, thêm module/file đúng. |
| `NoSuchMethodError` | Classpath chứa binary version không tương thích, nhiều JAR chứa class trùng. | Loại JAR trùng, kiểm tra version và thứ tự classpath. |
| `dependencyInsight` không thấy tên local library | File dependency không có module identity. | Xem file path/classpath/JAR entries thay vì đoán group. |
| Thêm một JAR vào `libs` làm build thay đổi | `fileTree` pattern quá rộng. | Explicit `files` hoặc thu hẹp pattern/di trú module. |
| CI không thấy `libs/vendor.jar` | File chưa được phân phối hoặc đường dẫn local máy cá nhân. | Cung cấp binary bằng nguồn kiểm soát, path thống nhất, checksum. |
| Consumer từ Maven bị thiếu vendor classes | File dependency không có trong published descriptor. | Publish vendor như module có metadata, kiểm thử consumer độc lập. |
| Task Java chạy trước task đóng JAR | Dependency là path trần, thiếu producer association. | Dùng task outputs/`builtBy`/task dependency đúng. |
| Build Cache giảm hit sau khi dùng `fileTree` | File ordering/set thay đổi. | Ưu tiên explicit files hoặc module dependency, kiểm soát file set. |
| `flatDir` không tự kéo dependent modules | Không có POM/Ivy metadata đầy đủ. | Publish vào Maven/Ivy repository có metadata. |
| Muốn nâng version local JAR bằng constraint không hiệu lực | Constraint tác động module GAV, không tác động file path. | Quản lý artifact explicit hoặc publish module để dùng constraint. |
| `implementation` unresolved trong Kotlin DSL | Chưa apply plugin tạo configuration. | Apply `java`, `java-library`, `application`... đúng dự án. |

## 15. Quy trình lựa chọn cho dự án sản phẩm

1. **Có mã nguồn thư viện trong cùng build?** Ưu tiên `project(":lib")`: Gradle có model variant và task dependencies.
2. **Có module publish chính thức?** Dùng `group:name:version` và repository thật, không copy JAR về `libs`.
3. **Chỉ có file vendor?** Kiểm tra nguồn gốc/giấy phép/hash và transitive list; tạm dùng `files(...)` explicit để giới hạn phạm vi.
4. **Vendor giao nhiều JAR cùng một bundle?** Có thể dùng `fileTree` có include/exclude chặt, nhưng kiểm tra class/version trùng, không dựa vào glob order.
5. **JAR do task của build tạo?** Sử dụng output provider hoặc `builtBy` và tránh copy đường dẫn build output qua project bằng string.
6. **Library sẽ publish cho bên ngoài?** Publish vendor binary như module có metadata, sửa dependency declaration và kiểm thử consumer ở một build khác.
7. **Sau migration?** So sánh compileClasspath/runtimeClasspath, chạy test/runtime, kiểm tra transitive graph, artifact bytes và bản kê license.

### Checklist review

- [ ] Local JAR có lý do sử dụng thay vì module/project dependency.
- [ ] Đường dẫn không phụ thuộc máy cá nhân; CI có thể lấy đúng bytes.
- [ ] `files` explicit khi chỉ có vài JAR; `fileTree` có pattern chặt nếu phải dùng.
- [ ] Không chứa nhiều version JAR hoặc class trùng một cách không kiểm soát.
- [ ] Scope `implementation`/`runtimeOnly`/`compileOnly`/`testImplementation` phản ánh cách dùng.
- [ ] Không dựa vào file dependency để tự suy ra transitive modules, version constraints hoặc variants.
- [ ] Các JAR do task tạo có producer association chuẩn, không phụ thuộc file cũ.
- [ ] Published dependency descriptor được kiểm thử riêng; không assume file dependency được publish.
- [ ] Có thông tin vendor, hash, license, update plan và JAR provenance.
- [ ] Đã chạy compile/runtime tests trên môi trường giống CI và đọc artifact thực.
- [ ] Không dùng `flatDir` hay `@jar` như giải pháp mặc định để “lấy lại” metadata.

## 16. Câu hỏi tự kiểm tra

1. **`files("libs/a.jar")` có tự biết version a.jar không?** Không. Nó là file path, không phải GAV module.
2. **`fileTree` có tự resolve transitive dependencies không?** Không; nó chỉ chọn file theo glob.
3. **Thứ tự FileTree có ổn định trên cùng máy?** Gradle không đảm bảo, có thể ảnh hưởng classpath và cache.
4. **Một JAR có tên `codec-1.15.jar` có tương đương `commons-codec:commons-codec:1.15` không?** Không, chỉ tương đương về bytes nếu bạn chứng minh, không tương đương về metadata.
5. **Nếu adapter.jar dùng base.jar ở runtime, chỉ khai báo adapter.jar thì sao?** App có thể compile nhưng runtime thiếu `BaseFormatter`; phải thêm base.jar hoặc dùng module metadata đúng.
6. **File dependency có được theo dõi bytes bởi JavaCompile không?** Có thể, vì classpath là task input. Thiếu module metadata là khái niệm khác.
7. **`api(files(...))` trong project có tự xuất hiện như module dependency trong POM publish không?** Không, file dependencies không được đưa vào published dependency descriptor.
8. **Trong multi-project build, file dependency có thể được truyền transitively không?** Có thể qua project variants trong cùng build; không đồng nghĩa consumer ngoài nhận được.
9. **`flatDir` có đọc Maven POM đầy đủ không?** Không, dùng metadata tổng hợp từ artifact.
10. **Dependency constraint có tự nâng `libs/codec-1.11.jar` lên JAR 1.15 không?** Không, constraint áp cho module identity trong graph.
11. **Nếu local JAR được task khác sinh, phải làm gì?** Nối TaskProvider output hoặc `builtBy`/dependency để producer chạy trước.
12. **`@jar` có giữ nguyên metadata/transitives của module không?** Artifact-only notation có thể bỏ qua metadata cho dependency đó.
13. **Vì sao một JAR mới trong `libs` có thể làm build thay đổi dù script y nguyên?** Nếu fileTree match pattern, file mới gia nhập classpath.
14. **Nên dùng gì với nhiều thư viện chia sẻ giữa repository?** Module versioned trên Maven/Ivy repository với POM/Gradle Module Metadata đúng.
15. **Làm sao biết thiếu class do transitive file dependency?** Xem runtimeClasspath, `jar --list`, `jdeps` và stacktrace; không chỉ kiểm tra compile pass.

## Tài liệu Gradle chính thức

- [Declaring Dependencies — File Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html): `files`, `fileTree`, metadata, thứ tự FileTree, publication và `builtBy`.
- [Repository Types](https://docs.gradle.org/current/userguide/supported_repository_types.html): vì sao `flatDir` không có POM/Ivy metadata thật.
- [Dependency Resolution](https://docs.gradle.org/current/userguide/dependency_resolution.html): tách graph resolution khỏi artifact resolution.
- [Metadata Formats](https://docs.gradle.org/current/userguide/supported_metadata_formats.html): Gradle Module Metadata, POM, Ivy, variants và transitive graph.
- [Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html): local Maven/Ivy và repository layouts.
- [Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight`.
- [Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): FileCollection, FileTree và file operations.
- [Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html): publication semantics và variants.
