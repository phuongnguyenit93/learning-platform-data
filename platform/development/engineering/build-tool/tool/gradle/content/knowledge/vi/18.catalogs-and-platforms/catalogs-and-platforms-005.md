# Giới hạn catalog: phiên bản đề xuất không phải kết quả phân giải bắt buộc trong Gradle

## Mục tiêu bài học

**Version catalog** là nơi đặt tên và tập trung khai báo tọa độ dependency, plugin và những version mong muốn. Nhưng một con số xuất hiện trong **gradle/libs.versions.toml** không nhất thiết là **con số Gradle sẽ đưa lên compileClasspath/runtimeClasspath**. Khi nhiều dependency bắc cầu, constraint hay platform tham gia cùng một graph, Gradle thực hiện **dependency resolution** để chọn version cuối cùng.

Đây là một giới hạn quan trọng của catalog: **catalog làm nhất quán cách yêu cầu dependency, không tự tạo một khóa phiên bản toàn cục và không thay thế bộ giải dependency**.

Sau bài này bạn có thể:

1. Phân biệt **catalog version**, **requested version**, **selected/resolved version** và **locked version**.
2. Hiểu vì sao **version.ref** được nhiều alias dùng chung không bảo đảm các module được resolve theo cùng phiên bản.
3. Dự đoán kết quả của Gradle khi thư viện direct yêu cầu **1.0**, còn dependency transitive yêu cầu **2.0**.
4. Biết rằng TOML version đơn giản mang nghĩa **require**, **không phải strictly**; nhưng **rich version** trong catalog có thể đặt **strictly/prefer/reject** một cách tường minh.
5. Dùng **dependencies**, **dependencyInsight** để xem version được chọn trong **đúng configuration**.
6. Hiểu khác biệt giữa **version catalog**, **dependency constraints**, **platform/BOM**, **enforcedPlatform**, **dependency locking** và **dependency verification**.
7. Tạo bài lab có Java 17, Gradle Groovy DSL và local Maven repository, **không dựa vào dependency từ Internet**, để quan sát phiên bản catalog 1.0 được resolve thành 2.0.
8. Chọn giải pháp đúng để quản lý phiên bản mà không lạm dụng **force** hay nhầm kết quả của thư viện test với runtime của ứng dụng.

Ví dụ chính dùng **build.gradle** (Groovy DSL); có đoạn tương ứng cho **build.gradle.kts**. Bài không giả định một thư viện “demo” đang tồn tại trên Maven Central: chính lab sẽ tạo module cục bộ.

## 1. Bốn giá trị thường bị lẫn lộn

Ví dụ một catalog:

~~~toml
# gradle/libs.versions.toml
[versions]
engine = "1.0"

[libraries]
engine = { module = "demo:engine", version.ref = "engine" }
~~~

Trong **build.gradle**:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation libs.engine
}
~~~

Các khái niệm:

| Khái niệm | Nó ở đâu? | Ý nghĩa thực tế |
| --- | --- | --- |
| **Catalog version** | **[versions] engine = "1.0"** | Giá trị được alias tham chiếu để **tạo yêu cầu dependency** |
| **Requested version** | Dependency **demo:engine:1.0** qua **libs.engine** | Version mà một cạnh trong graph yêu cầu |
| **Selected/resolved version** | Kết quả **runtimeClasspath/compileClasspath** | Version Gradle chọn cho module này sau conflict resolution, constraints, platforms, rules... |
| **Locked version** | Lock state nếu bật dependency locking | Version được giữ từ lần giải trước theo lockfile; không phải mặc định của catalog |

**Catalog không trực tiếp là dependency graph.** Tệp TOML mô tả một tập alias và version, còn một dependency thực sự được đưa vào graph khi project dùng alias ấy (ví dụ **implementation libs.engine**), một plugin thêm nó hoặc một cạnh transitive yêu cầu nó.

Một alias nằm trong catalog nhưng **không được sử dụng** không tự làm Gradle đưa module đó vào runtimeClasspath. Một version trong **[versions]** chưa được alias tham chiếu cũng không có ảnh hưởng đến resolution.

### 1.1. Câu “version trong catalog chỉ là đề xuất” phải hiểu chính xác

Với:

~~~toml
[versions]
engine = "1.0"
~~~

Gradle xem giá trị đơn giản **"1.0"** là **required version** khi alias dùng nó. Điều này **mạnh hơn một soft prefer** nhưng **yếu hơn một strictly constraint**: khi graph xuất hiện một yêu cầu version cao hơn, **1.0 có thể được nâng lên**.

Vì vậy không nên nói **"catalog luôn dùng prefer"** — câu đó không chính xác về mặt API. Phát biểu đúng là:

> Version thường trong catalog trở thành yêu cầu version thông thường, **không cưỡng chế kết quả cuối cùng**; muốn giới hạn cứng phải khai báo cơ chế constraint/locking phù hợp.

Bên dưới ta sẽ thấy TOML cũng hỗ trợ **strictly**, **prefer** và **reject**, nên giới hạn của catalog không có nghĩa catalog **không bao giờ** biểu đạt một version constraint mạnh. Giới hạn là **catalog không tự động kiểm soát toàn bộ graph chỉ nhờ con số/alias đã khai báo**.

## 2. Gradle thực sự phân giải version như thế nào?

Khi Gradle cần **runtimeClasspath** cho Java application, nó duyệt các dependency edges từ:

- **Direct dependencies** khai báo bởi project: **implementation**, **runtimeOnly**, **api** (ở module java-library), ...
- **Transitive dependencies** trong metadata của các module đã chọn.
- **Constraints** do project hoặc các modules/platform khai báo.
- **Version requirements** như require, strictly, prefer, reject và ranges.
- **Resolution rules**, module metadata/variants, và dependency locking (nếu có).

Trong trường hợp thông thường, khi **cùng group:name** bị yêu cầu ở version **1.0** và **2.0** mà không có ràng buộc khác, Gradle chọn **version cao nhất được chấp nhận**, ở đây là **2.0**.

### 2.1. Graph minh họa

Giả sử:

~~~text
:app
├── demo:engine:1.0               <- dùng libs.engine từ catalog
└── demo:client:1.0               <- dùng libs.client từ catalog
    └── demo:engine:2.0           <- nằm trong POM của client
~~~

Graph sau khi Gradle giải:

~~~text
:app
├── demo:engine:1.0 -> 2.0
└── demo:client:1.0
    └── demo:engine:2.0
~~~

**Không phải Gradle dùng đồng thời hai phiên bản engine** trong cùng graph của configuration này. Nó chọn **engine:2.0** và thông báo rằng một yêu cầu **engine:1.0** đã bị điều chỉnh thành **2.0**.

**Thứ tự**:

~~~groovy
implementation libs.engine
implementation libs.client
~~~

so với:

~~~groovy
implementation libs.client
implementation libs.engine
~~~

không quyết định phiên bản thắng. Dòng được khai báo trước không có quyền ưu tiên đặc biệt trong version conflict resolution.

### 2.2. Direct dependency không đương nhiên mạnh hơn transitive

Dòng:

~~~groovy
implementation libs.engine
~~~

có thể là yêu cầu trực tiếp của app cho engine 1.0. Nhưng một library khác trong graph vẫn có thể yêu cầu engine 2.0. Nếu chỉ có các yêu cầu thông thường, Gradle được phép nâng direct engine 1.0 lên 2.0.

**Phiên bản ghi rõ trong code không đồng nghĩa strict pin.** Điều này đúng cho cả string notation:

~~~groovy
implementation 'demo:engine:1.0'
~~~

và alias:

~~~groovy
implementation libs.engine
~~~

Nếu hai cách cùng tạo yêu cầu **demo:engine:1.0**, bộ giải phiên bản cơ bản đối xử tương đương. Alias không thêm quyền ưu tiên bí mật.

### 2.3. Một configuration là một lần xét graph

Với Java plugin, **compileClasspath**, **runtimeClasspath**, **testCompileClasspath** và **testRuntimeClasspath** có graph khác nhau. Ví dụ test dependencies yêu cầu engine 3.0, nhưng runtime của app chỉ cần 2.0; kết quả có thể là:

| Configuration | Version engine có thể được chọn |
| --- | --- |
| **compileClasspath** | 2.0 |
| **runtimeClasspath** | 2.0 |
| **testRuntimeClasspath** | 3.0 |

Đây là ví dụ **giả định có nhánh test yêu cầu 3.0**, không phải kết quả cố định cho mọi build. Nó cho thấy **cùng một libs.versions.toml** không ép mọi configuration chọn cùng version nếu các nhánh dependency khác nhau.

**Luôn nêu đúng project và configuration khi nói “Gradle chọn version X”.**

## 3. Những gì catalog thực sự làm tốt

Version catalogs vẫn rất hữu ích:

1. **Centralized coordinates:** thay vì lặp **group:name:version** khắp module, đặt alias ở TOML.
2. **Type-safe accessors:** dùng **libs.engine**, **libs.client**, IDE hỗ trợ gợi ý và phát hiện alias sai.
3. **Version references:** nhiều alias cùng dùng **version.ref = "..."**, giảm version strings bị lặp.
4. **Bundles:** gom nhiều alias thành một nhóm dependencies dùng chung.
5. **Plugin aliases:** quản lý plugin IDs/versions dùng trong **plugins DSL**.
6. **Nhiều modules dùng cùng tên dependency:** giảm khác biệt do gõ nhầm hoặc quên cập nhật script.

Ví dụ TOML:

~~~toml
[versions]
engine = "1.0"
client = "1.0"

[libraries]
engine = { module = "demo:engine", version.ref = "engine" }
client = { module = "demo:client", version.ref = "client" }

[bundles]
runtime-stack = ["engine", "client"]
~~~

Và trong Groovy DSL:

~~~groovy
dependencies {
    implementation libs.bundles.runtime.stack
}
~~~

Bundle yêu cầu cả engine và client theo các alias trong catalog, **không phải một BOM** và **không làm graph “khóa 1.0”**. Client vẫn có thể yêu cầu engine 2.0 như ví dụ trên.

### 3.1. version.ref không phải alignment

Giả sử ba thư viện liên quan đều được trỏ vào một version key:

~~~toml
[versions]
stack = "1.5"

[libraries]
core = { module = "org.example:core", version.ref = "stack" }
api = { module = "org.example:api", version.ref = "stack" }
transport = { module = "org.example:transport", version.ref = "stack" }
~~~

Những cạnh trực tiếp từ ba aliases đều có requested version **1.5**. Nhưng **transport** có thể bị một nhánh transitive yêu cầu **1.6** và được Gradle chọn **1.6**, trong khi core/api vẫn là **1.5**. Đó là **không đồng bộ resolved versions**, dù TOML dùng cùng **version.ref**.

Nếu thư viện thuộc một **release train** phải dùng version thống nhất, hãy dùng **platform/BOM hoặc alignment metadata** có đủ constraints, không chỉ một key TOML.

### 3.2. Bundle cũng không thêm policy conflict resolution

Một bundle:

~~~toml
[bundles]
networking = ["http-api", "http-client", "http-logging"]
~~~

chỉ là **danh sách alias**. Nó không tự thêm constraints hoặc đảm bảo ba modules cùng version. Nếu một alias không cần xuất hiện ở một configuration, dùng bundle bừa còn có thể thêm dependency không cần thiết.

**Catalog cho phép biểu đạt cấu trúc rõ ràng; không thay thế việc hiểu dependency graph.**

## 4. Cấu trúc TOML và cách version được truyền vào declaration

Với default catalog, Gradle tự nhận diện **gradle/libs.versions.toml** trong root build (nếu không bị cấu hình khác thay thế). Bốn bảng cơ bản:

~~~toml
[versions]
shared = "1.0"

[libraries]
alpha = { module = "demo:alpha", version.ref = "shared" }
beta = { group = "demo", name = "beta", version = "2.0" }

[bundles]
set = ["alpha", "beta"]

[plugins]
# Không thêm plugin giả vào project thực hành nếu chưa có repository cung cấp.
~~~

- **[versions]** khai báo version strings hoặc rich version objects.
- **[libraries]** khai báo GAV/library aliases.
- **[bundles]** nhóm **library aliases**.
- **[plugins]** khai báo plugin IDs và versions (plugin version có semantics riêng).

TOML được Gradle đọc ở giai đoạn cấu hình để sinh accessors, nhưng **chưa có nghĩa module trong [libraries] đã được resolved**. Chỉ khi script dùng alias trong **dependencies** hoặc cơ chế tương đương, Gradle mới đưa yêu cầu đó vào dependency graph.

### 4.1. Catalog không làm phát sinh dependency nếu chỉ khai báo alias

Nếu TOML có:

~~~toml
[libraries]
unused = { module = "demo:unused", version = "1.0" }
~~~

nhưng không có dòng **implementation libs.unused** hoặc một sử dụng khác kéo module vào graph, **demo:unused** không xuất hiện chỉ vì alias tồn tại. Đây cũng là lý do catalog không thể coi là một **danh sách tất cả dependencies thực tế của project**.

### 4.2. Có thể định nghĩa alias không version

~~~toml
[libraries]
engine = { module = "demo:engine" }
~~~

Dòng trên tạo alias cho **tọa độ module mà chưa cung cấp version**. Nó hợp lý khi **platform/BOM hoặc một constraint khác** đưa version vào graph. Nhưng nếu graph không có bất kỳ version requirement đủ để chọn version, resolution có thể lỗi **không có version**.

Cách này nhấn mạnh catalog làm **khai báo tọa độ**, còn version policy có thể được cung cấp bởi một **component trong graph**.

### 4.3. Tránh hiểu nhầm “đã sửa TOML là mọi module được update”

Khi đổi:

~~~toml
[versions]
engine = "1.0"
~~~

thành:

~~~toml
[versions]
engine = "1.1"
~~~

bạn đang đổi requested version của **những aliases có version.ref tới engine** khi được sử dụng. Bạn **không tự cập nhật**:

- dependency edges của thư viện bên thứ ba;
- mọi version được một plugin tự khai báo;
- graph của included builds/các builds khác;
- lockfile cũ;
- constraints ở platform khác;
- những dependency được viết bằng string notation không dùng alias;
- các phần của app đã resolve/cache theo chính sách khác.

Sau khi sửa TOML cần **chạy dependency report** và tests. Đừng dựa vào “search text thấy chỉ còn 1.1 trong TOML” để kết luận runtime cũng là 1.1.

## 5. Bài thực hành Java 17: catalog yêu cầu 1.0 nhưng Gradle chọn 2.0

Lab **có thể chạy độc lập với Maven Central** vì tự sinh một Maven repository cục bộ. Cần **JDK 17+**, **Gradle Wrapper hợp lệ** và Gradle/JDK tương thích. Việc chuẩn bị Gradle distribution/toolchain khi máy còn trống có thể cần Internet; riêng **module dependencies của lab** đều nằm trên đĩa.

**Mục tiêu:** một ứng dụng import **demo.Engine**. Catalog yêu cầu engine 1.0. Một module khác **demo:client:1.0** có POM khai báo transitive dependency engine 2.0. Khi cả hai ở runtimeClasspath, app in **Selected engine: 2.0** dù TOML ghi **1.0**.

### 5.1. Cây thư mục

~~~text
catalog-resolution-lab/
├── settings.gradle
├── build.gradle
├── FixtureGenerator.java
├── gradle/
│   ├── libs.versions.toml
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
├── src/
│   └── main/java/demo/App.java
└── lab-repo/                         # Được FixtureGenerator tạo
    └── demo/
        ├── engine/1.0/
        │   ├── engine-1.0.pom
        │   └── engine-1.0.jar
        ├── engine/2.0/
        │   ├── engine-2.0.pom
        │   └── engine-2.0.jar
        └── client/1.0/
            ├── client-1.0.pom       # Phụ thuộc engine 2.0
            └── client-1.0.jar
~~~

**Gradle Wrapper** cần được tạo bởi lệnh Wrapper/Gradle hoặc lấy từ project tin cậy; ví dụ không tự chế **gradle-wrapper.jar**.

### 5.2. settings.gradle

~~~groovy
rootProject.name = 'catalog-resolution-lab'
~~~

Với default file **gradle/libs.versions.toml**, không cần tự khai báo **versionCatalogs { create('libs') ... }** trong settings.

### 5.3. gradle/libs.versions.toml

~~~toml
[versions]
engine = "1.0"
client = "1.0"

[libraries]
engine = { module = "demo:engine", version.ref = "engine" }
client = { module = "demo:client", version.ref = "client" }

[bundles]
all = ["engine", "client"]
~~~

Cụ thể:

- **libs.engine** yêu cầu **demo:engine:1.0**.
- **libs.client** yêu cầu **demo:client:1.0**.
- **libs.bundles.all** nếu được dùng sẽ thêm cả hai aliases; không ép engine giữ 1.0.
- Version **engine = "1.0"** không có nghĩa Gradle đã pin nó bằng **strictly**.

### 5.4. FixtureGenerator.java tạo JAR và Maven POM

Tạo file **FixtureGenerator.java** ở root project:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class FixtureGenerator {

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Use a JDK 17+, not a JRE");
        }

        writeEngine(compiler, "1.0");
        writeEngine(compiler, "2.0");
        writeClient();
        System.out.println("Generated three Maven modules.");
    }

    private static void writeEngine(
            JavaCompiler compiler, String version
    ) throws IOException {
        Path source = Path.of(
                "fixture-build", version, "src", "demo", "Engine.java"
        );
        Path classes = Path.of("fixture-build", version, "classes");
        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);

        String code = """
                package demo;
                public final class Engine {
                    public static String version() {
                        return "%s";
                    }
                }
                """.formatted(version);
        Files.writeString(source, code, StandardCharsets.UTF_8);

        int result = compiler.run(
                null, null, null,
                "--release", "17",
                "-d", classes.toString(),
                source.toString()
        );
        if (result != 0) {
            throw new IOException("Failed to compile engine " + version);
        }

        Path module = modulePath("engine", version);
        writePom(module, "engine", version, "");
        Path jarPath = module.resolve("engine-" + version + ".jar");

        try (JarOutputStream jar = new JarOutputStream(
                Files.newOutputStream(jarPath))) {
            jar.putNextEntry(new JarEntry("demo/Engine.class"));
            Files.copy(classes.resolve("demo/Engine.class"), jar);
            jar.closeEntry();
        }
    }

    private static void writeClient() throws IOException {
        Path module = modulePath("client", "1.0");
        String dependency = """
                  <dependencies>
                    <dependency>
                      <groupId>demo</groupId>
                      <artifactId>engine</artifactId>
                      <version>2.0</version>
                      <scope>compile</scope>
                    </dependency>
                  </dependencies>
                """;
        writePom(module, "client", "1.0", dependency);

        // JAR không chứa class, nhưng là một JAR hợp lệ.
        try (JarOutputStream ignored = new JarOutputStream(
                Files.newOutputStream(
                        module.resolve("client-1.0.jar")))) {
            // POM của client là nguồn cạnh dependency transitive.
        }
    }

    private static Path modulePath(
            String artifact, String version
    ) throws IOException {
        Path module = Path.of(
                "lab-repo", "demo", artifact, version
        );
        Files.createDirectories(module);
        return module;
    }

    private static void writePom(
            Path module,
            String artifact,
            String version,
            String dependencies
    ) throws IOException {
        String pom = """
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <modelVersion>4.0.0</modelVersion>
                  <groupId>demo</groupId>
                  <artifactId>%s</artifactId>
                  <version>%s</version>
                  <packaging>jar</packaging>
                %s</project>
                """.formatted(artifact, version, dependencies);

        Files.writeString(
                module.resolve(artifact + "-" + version + ".pom"),
                pom,
                StandardCharsets.UTF_8
        );
    }
}
~~~

Giải thích:

1. **JavaCompiler** từ JDK 17+ tạo **Engine.class** cho version 1.0 và 2.0.
2. Mỗi JAR engine có cùng **demo.Engine** nhưng method **version()** trả chuỗi khác.
3. POM engine là Maven metadata tối thiểu, không có transitive dependencies.
4. Client 1.0 có một JAR rỗng hợp lệ và **POM khai báo engine 2.0**. Nó không cần class Java trong JAR để thể hiện một dependency transitive.
5. Maven layout chuẩn **group/artifact/version** giúp Gradle đọc các POM trong thư mục **lab-repo**.
6. **Text blocks** và **String.formatted(...)** là cú pháp Java 17 hợp lệ.

Chạy ở root trên máy có JDK 17+:

~~~bash
javac FixtureGenerator.java
java FixtureGenerator
~~~

Phần stdout của generator khi thành công:

~~~text
Generated three Maven modules.
~~~

Kiểm tra ba folder **lab-repo/demo/engine/1.0**, **engine/2.0** và **client/1.0** trước khi chạy Gradle.

### 5.5. build.gradle: dùng alias nhưng không khóa version

~~~groovy
plugins {
    id 'application'
}

repositories {
    maven {
        name = 'fixtureRepository'
        url = uri('lab-repo')
    }
}

dependencies {
    implementation libs.engine
    implementation libs.client
}

application {
    mainClass = 'demo.App'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

- **application** là core Gradle plugin.
- **libs.engine** được đọc từ default catalog, yêu cầu engine **1.0**.
- **libs.client** yêu cầu client **1.0**, nhưng POM của client yêu cầu engine **2.0**.
- **repositories** dùng local Maven directory; không cần **mavenCentral()**.
- **application.mainClass** khai báo main class.
- Java toolchain yêu cầu JDK 17 cho Java compile/run.

### 5.6. src/main/java/demo/App.java

~~~java
package demo;

public final class App {
    public static void main(String[] args) {
        System.out.println("Selected engine: " + Engine.version());
    }
}
~~~

App không import một tên class có version; **demo.Engine** giống nhau ở cả JAR 1.0 và 2.0. Gradle quyết định **JAR phiên bản nào thuộc runtimeClasspath**.

### 5.7. Chạy project

Linux/macOS:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency demo:engine --configuration runtimeClasspath
./gradlew run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency demo:engine --configuration runtimeClasspath
.\gradlew.bat run
~~~

Một phần report phụ thuộc (hình dạng minh họa):

~~~text
+--- demo:engine:1.0 -> 2.0
\--- demo:client:1.0
     \--- demo:engine:2.0
~~~

Phần stdout **do App in**, khi fixtures và các lệnh được thiết lập như trên:

~~~text
Selected engine: 2.0
~~~

Lưu ý Gradle có nhiều dòng log khác; **Selected engine: 2.0** là dòng quan trọng cần so với kết quả bạn dự đoán.

### 5.8. Thử bỏ client

Tạm sửa dependencies thành:

~~~groovy
dependencies {
    implementation libs.engine
}
~~~

Bây giờ, với local Maven repository chỉ có một yêu cầu engine 1.0 và không có constraints/rules khác, output từ app sẽ là:

~~~text
Selected engine: 1.0
~~~

**Điểm quan sát:** cùng một alias **libs.engine**, nhưng thêm hoặc bỏ nhánh transitive của **libs.client** khiến selected version đổi. **TOML không thay đổi**; chính graph thay đổi.

Sau thí nghiệm, khôi phục cả **libs.engine** và **libs.client** để làm bài tiếp.

### 5.9. Dùng bundle cũng không khóa version

Thay dependencies bằng:

~~~groovy
dependencies {
    implementation libs.bundles.all
}
~~~

Bundle **all** bao gồm engine và client nên graph lại có hai yêu cầu 1.0 và 2.0. Với default rules, app lại in:

~~~text
Selected engine: 2.0
~~~

Bundle chỉ là cách viết gọn nhiều dependencies, không tạo một constraint chặn phiên bản.

## 6. Nhìn catalog và graph cạnh nhau

Đây là bài học cốt lõi của lab:

| Nguồn thông tin | Giá trị quan sát | Kết luận |
| --- | --- | --- |
| **[versions] engine** | **1.0** | Version được dùng để tạo yêu cầu thông thường của alias |
| **libs.engine** | **demo:engine:1.0** | Direct requested version |
| **POM demo:client:1.0** | **demo:engine:2.0** | Transitive requested version |
| **runtimeClasspath** | **demo:engine:2.0** | Selected/resolved version |
| **App stdout** | **Selected engine: 2.0** | Artifact engine 2.0 được nạp tại runtime |

Nếu ai đó hỏi “project đang dùng engine version nào?”, **tệp TOML không đủ để trả lời**. Cần xác định configuration và đọc kết quả **dependencyInsight**, vì TOML chỉ mô tả một phần inputs cho bộ giải.

### 6.1. Ký hiệu trong dependencies report

Các dòng dạng:

~~~text
demo:engine:1.0 -> 2.0
~~~

nghĩa là một dependency edge **yêu cầu 1.0**, nhưng Gradle **chọn 2.0**. Nó không có nghĩa **hai bản engine cùng trên classpath** của graph đó.

Ký hiệu khác:

| Ký hiệu | Thường có nghĩa |
| --- | --- |
| **(*)** | Nhánh dependency lặp đã được Gradle hiển thị ở nơi khác |
| **(c)** | Một dependency constraint, không tự thêm module vào graph |
| **FAILED** | Dependency/variant không giải được ở vị trí được hiển thị |
| **->** | Requested version khác selected version |

### 6.2. dependencyInsight cho biết tại sao chọn

~~~bash
./gradlew dependencyInsight --dependency demo:engine --configuration runtimeClasspath
~~~

Trong lab, Gradle có thể liệt kê selection reason như **By conflict resolution: between versions 1.0 and 2.0**. Khi có constraints/platform/forced versions, selection reasons có thể thay đổi, ví dụ **By constraint**, **Forced**, **By ancestor**, **Selected by rule**.

**dependencyInsight** không phải lệnh tải lại mọi JAR, và không thay thế integration test. Nó cho ta góc nhìn cụ thể về **một module, một configuration, một graph**.

### 6.3. Multi-project: chỉ định đúng module

Với multi-project có **:app**, **:server**, **:lib**, đừng chạy report ở root rồi nghĩ đó là graph của app:

~~~bash
./gradlew :app:dependencyInsight \
    --dependency demo:engine \
    --configuration runtimeClasspath
~~~

PowerShell:

~~~powershell
.\gradlew.bat :app:dependencyInsight --dependency demo:engine --configuration runtimeClasspath
~~~

Mỗi subproject có các dependencies/constraints riêng. Dù các subprojects cùng đọc catalog, kết quả vẫn có thể khác nếu graph khác.

## 7. Rich versions trong catalog: khi nào TOML thực sự giới hạn version?

**Version catalog hỗ trợ rich versions cho library aliases.** Điều đó khác với khẳng định “catalog không thể có constraints”.

Bốn thuật ngữ:

| Khóa trong rich version | Nghĩa | Có pin exact version không? |
| --- | --- | --- |
| **require** | Yêu cầu version thường; có thể được nâng khi giải conflict | **Không** |
| **strictly** | Chỉ chấp nhận version/range đã khai báo, trừ các quy tắc precedence liên quan | **Có giới hạn cứng** |
| **prefer** | Giá trị mong muốn mềm khi không có yêu cầu mạnh hơn | **Không** |
| **reject** | Loại các version cụ thể | Không pin một version, nhưng cấm một số candidates |

### 7.1. Chuyển engine catalog sang strictly

Trong lab, thay **gradle/libs.versions.toml** bằng:

~~~toml
[versions]
engine = { strictly = "1.0" }
client = "1.0"

[libraries]
engine = { module = "demo:engine", version.ref = "engine" }
client = { module = "demo:client", version.ref = "client" }
~~~

Giữ **build.gradle**:

~~~groovy
dependencies {
    implementation libs.engine
    implementation libs.client
}
~~~

Bây giờ **libs.engine** mang một **strict requirement đúng 1.0**. Trong fixture hiện tại, nhánh client chỉ **require engine 2.0** theo metadata Maven, không đưa ra strict requirement. Theo quy tắc rich version, strict direct dependency có thể **hạ version được chọn xuống 1.0**. App của lab chỉ dùng method chung có ở cả hai bản nên với graph hợp lệ, output sẽ là:

~~~text
Selected engine: 1.0
~~~

**Không diễn giải thành “strictly luôn an toàn”.** Nếu client thực sự dùng API chỉ có trong engine 2.0, downgrade có thể phá runtime; nếu có strict constraints bất tương thích khác, graph có thể thất bại. Dùng **strictly** khi có lý do tương thích rõ và kiểm thử đủ.

### 7.2. strictly không tự áp dụng cho aliases không được sử dụng

Giả sử TOML chứa:

~~~toml
[versions]
engine = { strictly = "1.0" }

[libraries]
engine = { module = "demo:engine", version.ref = "engine" }
~~~

nhưng project chỉ khai báo:

~~~groovy
dependencies {
    implementation 'demo:client:1.0'
}
~~~

Nếu không dùng **libs.engine** trong graph, strict version của alias **libs.engine** không tự được tiêm vào mọi configuration. Catalog không hoạt động như một global constraint registry. Client có thể vẫn kéo engine 2.0 qua POM, tùy repositories/constraints khác.

**Muốn quy định chung cho một module ở những project có dùng nó, hãy dùng platform, constraints hoặc một convention plugin được áp dụng phù hợp**, không chỉ khai báo strict alias rồi không sử dụng.

### 7.3. Strict range thay vì exact version

Trong library project, exact strict version có thể bó buộc consumers. Một strict range cho biết dải đã được kiểm thử:

~~~toml
[versions]
engine = { strictly = "[1.0, 2.0[", prefer = "1.5" }

[libraries]
engine = { module = "demo:engine", version.ref = "engine" }
~~~

Đây là một rich version:

- **strictly = "[1.0, 2.0["** cho phép version >=1.0 và <2.0, loại 2.0.
- **prefer = "1.5"** là ưu tiên mềm bên trong dải nếu có candidate phù hợp.
- Nếu không repository nào cung cấp version thích hợp, hoặc constraints khác không thể tương thích, resolution có thể thất bại.

**Trong local lab chỉ có engine 1.0 và 2.0**, ưu tiên 1.5 không tự sinh version 1.5. Đừng khẳng định Gradle sẽ tải engine 1.5 khi nó không tồn tại.

### 7.4. Reject version lỗi

Ví dụ:

~~~toml
[versions]
engine = { require = "1.0", reject = ["1.4", "1.5"] }
~~~

Đây là ví dụ mô tả policy, không liên quan trực tiếp phiên bản của lab. Nó chỉ loại các versions được chỉ rõ, không pin 1.0. Nếu có version khác được phép và được yêu cầu/chọn, Gradle vẫn có thể dùng nó.

**Tình huống phổ biến:** app dùng một thư viện có phiên bản lỗi nghiêm trọng, nhưng vẫn cần các bản vá sau đó. **reject** một vài version được xác minh lỗi thường hợp lý hơn ép mãi version cũ.

### 7.5. Không nên ghi cả require và strictly thiếu cân nhắc

Rich versions có quy tắc khi kết hợp hoặc override các trường. **strictly** đặt giới hạn cứng, trong khi **require** diễn đạt yêu cầu thông thường. Nếu mục tiêu là khoảng version được phép, mô tả bằng **strictly(range)** và **prefer(value)** rõ hơn việc đặt nhiều version fields mà không hiểu precedence.

Các định nghĩa strong constraints có thể được truyền qua Gradle Module Metadata tới consumers của library được publish. Với một public library, **strictly exact version** có thể hạn chế downstream dependencies và làm build của người khác không giải được; ưu tiên strict range nếu đó đúng là ràng buộc tương thích của API.

## 8. Vì sao platform/BOM giải quyết bài toán khác catalog?

**Catalog** là **bảng alias + requested versions**. **Platform/BOM** là một **component đưa dependency constraints vào graph**. Khác biệt này là chìa khóa khi một tổ chức muốn nhiều modules được quản lý theo cùng chính sách.

| Công cụ | Tác dụng chính | Có tham gia resolution graph? | Có tự pin mọi version? |
| --- | --- | --- | --- |
| Version catalog | Tập trung aliases, versions, bundles, plugin IDs | **Gián tiếp** qua aliases được dùng | **Không**, trừ constraints rich version của từng alias được dùng |
| Dependency constraint | Điều kiện version khi module xuất hiện | **Có** | Bare require: không; strictly: có giới hạn |
| Regular platform / BOM | Tập hợp dependency constraints cho nhóm modules | **Có** | Không nhất thiết exact; constraints thường có thể được nâng |
| Enforced platform | Cưỡng chế version constraints từ BOM/platform | **Có** | Mạnh; cần đánh giá xung đột và tác động transitive |
| Dependency locking | Khóa kết quả resolution đã ghi | **Có**, qua lock constraints | Giữ selected version theo lockfile |
| Dependency verification | Xác minh bytes/signatures metadata/artifacts | Kiểm tra provenance, không phải version selector | **Không** |

### 8.1. Import Maven BOM bằng platform

Ví dụ minh họa, dùng một BOM đã publish thật trong dự án thực tế:

~~~groovy
dependencies {
    implementation platform('org.example:example-bom:2.0')
    implementation 'org.example:api'
    implementation 'org.example:runtime'
}
~~~

Tọa độ **org.example** ở đây chỉ là placeholder tài liệu; không phải BOM có thật. Khi BOM thật cung cấp constraints, các dependencies có thể được khai báo **không có version** để platform đề xuất chúng.

**BOM không có nghĩa Gradle bỏ qua mọi version requirements khác.** Với regular platform, một dependency khác có thể gây nâng version theo conflict resolution. Nếu platform chứa strict constraints và Gradle endorse những constraints đó theo cơ chế tương ứng, chúng có thể có hiệu lực mạnh hơn. Tóm lại, phải xem **nội dung constraint và cơ chế nhập platform**, không chỉ nhìn thấy chữ **platform(...)**.

### 8.2. Enforced platform khác regular platform

~~~groovy
dependencies {
    implementation enforcedPlatform('org.example:example-bom:2.0')
    implementation 'org.example:api'
}
~~~

**enforcedPlatform** áp các constraints từ BOM theo dạng cưỡng chế, thường tương ứng strict version semantics. Nó có thể **ngăn nâng ngoài các version trong BOM** và lan truyền ảnh hưởng tới consumers nếu bạn xuất bản library có enforced platform.

**Khuyến nghị:** dùng enforcedPlatform chỉ khi thật sự cần toàn bộ bộ version đã chốt và hiểu ảnh hưởng transitively. Với library public, thường nên tránh vì consumer khó thay đổi version hợp lệ; với application nội bộ, có thể cân nhắc sau kiểm thử.

### 8.3. Catalog và platform nên kết hợp như thế nào?

Tổ chức lớn có thể dùng catalog cho **tên aliases**, còn platform cho **version policy**. Ví dụ:

~~~toml
# gradle/libs.versions.toml
[libraries]
engine = { module = "demo:engine" }
client = { module = "demo:client" }
~~~

Trong ứng dụng có platform phù hợp:

~~~groovy
dependencies {
    implementation platform(project(':dependency-platform'))
    implementation libs.engine
    implementation libs.client
}
~~~

Ở đây **catalog aliases không có version**; platform sẽ cung cấp constraints cho chúng. Đoạn **platform(project(':dependency-platform'))** chỉ chạy nếu settings đã include project **:dependency-platform** và project ấy áp **java-platform**/cung cấp constraints phù hợp. Đây là **mẫu kiến trúc**, không phải một thay thế trực tiếp được chạy trong lab một project của mục 5.

### 8.4. Ví dụ java-platform project

Một file **dependency-platform/build.gradle** tối giản:

~~~groovy
plugins {
    id 'java-platform'
}

dependencies {
    constraints {
        api 'demo:engine:2.0'
        api 'demo:client:1.0'
    }
}
~~~

Nếu root **settings.gradle** khai báo:

~~~groovy
rootProject.name = 'multi-project-sample'
include('app', 'dependency-platform')
~~~

và **app** dùng **platform(project(':dependency-platform'))**, Gradle đưa constraints từ platform vào graph của app. Đây là cách thực tế để thể hiện **version policy cho một nhóm module**.

**Lưu ý:** bare constraints **api 'demo:engine:2.0'** là requirements có thể được nâng trong một số xung đột, không phải exact pin. Nếu app cần một dải strict, hãy khai báo đúng rich version constraints trong platform, rồi kiểm chứng consumers.

## 9. Dependency constraints: không cần biến mọi thứ thành strict alias

Nếu một transitive module phải đạt tối thiểu một version an toàn, constraint trong project có thể diễn đạt policy rõ hơn catalog entry.

~~~groovy
dependencies {
    implementation libs.client

    constraints {
        implementation('demo:engine:2.0') {
            because 'Application is tested with engine 2.0'
        }
    }
}
~~~

Constraint này chỉ có hiệu lực **nếu engine xuất hiện trong graph**, không tự thêm engine. Nếu client POM không khai báo engine và không có dependency khác kéo engine, constraint không làm engine xuất hiện.

Ngược lại:

~~~groovy
dependencies {
    implementation libs.engine
}
~~~

thêm **một dependency edge**. Vì vậy, **constraint** là công cụ phù hợp khi muốn kiểm soát version của module được kéo vào qua dependency khác mà không cố ý thêm một JAR không còn cần thiết.

### 9.1. Bare constraint cũng không pin chính xác

~~~groovy
constraints {
    implementation 'demo:engine:1.0'
}
~~~

Theo Gradle rich versions, version đơn trong constraint là **require 1.0**, **không phải strictly 1.0**. Nếu graph có yêu cầu engine 2.0, bare constraint không tự chặn việc nâng.

Để thể hiện giới hạn thật:

~~~groovy
dependencies {
    constraints {
        implementation('demo:engine') {
            version {
                strictly '[1.0, 2.0['
                prefer '1.5'
            }
        }
    }
}
~~~

Đây là ví dụ về scope của constraint trong một project, không phải bản vá mặc định cho lab nơi engine 2.0 đã có. Trong graph có các yêu cầu không tương thích, Gradle có thể báo resolution failure hoặc chọn version khác được constraints cho phép tùy semantics.

### 9.2. Vì sao không dùng resolutionStrategy.force bừa?

Bạn có thể thấy code như:

~~~groovy
configurations.configureEach {
    resolutionStrategy.force 'demo:engine:1.0'
}
~~~

**force** có thể cưỡng chế kết quả, nhưng khó giải thích hợp đồng tương thích và có nguy cơ downgrade một transitive dependency thật sự cần version mới. Nếu client được biên dịch với API chỉ có ở engine 2.0, việc ép engine 1.0 có thể gây **NoSuchMethodError** hoặc **NoClassDefFoundError** khi chạy.

Với build mới, ưu tiên rich versions, constraints hoặc platform nếu chúng diễn đạt mục tiêu chính xác hơn. **Force không làm mã Java tự tương thích với version cũ.**

### 9.3. Dependency substitution và exclusions không phải chính sách pin

- **Exclude** loại một dependency edge, không chỉ đổi version.
- **Dependency substitution** đổi module/project selector theo rule.
- **force** cưỡng chế một version.
- **strictly** diễn đạt tập version được chấp nhận.
- **platform** gom constraints cho một tập modules.
- **catalog** giữ aliases và version declarations.

Nếu mục tiêu chỉ là “mọi app module dùng phiên bản đã kiểm thử”, thêm exclude hoặc substitution mà chưa hiểu graph thường làm build khó bảo trì hơn.

## 10. Dependency locking: giữ phiên bản đã phân giải, không chỉ đề xuất

Nếu bạn cần **kết quả resolution tái lập**, dependency locking giúp ghi lại những version **đã được chọn**, khác với TOML mô tả version requests.

Trong project:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Ví dụ tạo lock state cho configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --write-locks
~~~

Tùy Gradle version và cấu trúc project, lock state được ghi vào file lock theo cơ chế Gradle; cần review và commit nếu CI dùng trạng thái khóa. Với lab, lock có thể ghi **demo:engine:2.0** mặc dù TOML khai báo requested engine **1.0**.

**Điều này không mâu thuẫn**: catalog muốn engine 1.0, graph dẫn đến engine 2.0, lock giữ engine 2.0 như version đã được lựa chọn.

### 10.1. Khi TOML đổi nhưng lock còn cũ

Giả sử:

1. Hôm trước catalog yêu cầu engine 1.0.
2. Graph có client nên resolved engine 2.0, được ghi vào lockfile.
3. Hôm nay bạn đổi TOML engine thành 2.1 nhưng lock vẫn là 2.0.

Gradle có thể báo resolution/lock inconsistency do yêu cầu mới không tương thích locked version. **Không tự xóa lockfile chỉ để làm build xanh**; nên update lock state theo quy trình review và chạy tests trên graph mới.

### 10.2. Dependency verification giải bài toán khác

**Dependency verification** dựa trên checksums/chữ ký để xác minh artifact/metadata được nhận. Nó không tự quyết định engine 1.0 hay 2.0. Các cơ chế phối hợp:

- Catalog: **tên và requested versions**.
- Platform/constraints: **version requirements** trong graph.
- Lock: **selected versions** đã chốt.
- Verification: **artifact bytes/metadata** có khớp nguồn đáng tin không.
- Repository policy: **nơi Gradle được phép lấy artifact**.

Một artifact có đúng version nhưng sai bytes vẫn có thể nguy hiểm; khóa version và kiểm chứng artifact là hai việc riêng.

## 11. Catalog aliases cho plugins có semantics khác library aliases

Ngoài **[libraries]**, catalog có **[plugins]**:

~~~toml
[versions]
example-plugin = "1.2.3"

[plugins]
example = { id = "org.example.some-plugin", version.ref = "example-plugin" }
~~~

Đây là **ví dụ cấu trúc TOML**; plugin ID và version ở trên không được giả định tồn tại. Nếu plugin thật tồn tại và repository hỗ trợ:

~~~groovy
plugins {
    alias(libs.plugins.example)
}
~~~

Với plugin aliases, Gradle hiện đại sử dụng **required version** và các trường **prefer/strictly/reject** không có cùng khả năng được hỗ trợ như library rich versions; khai báo những rich constraints khác cho plugins đang bị deprecate theo tài liệu Gradle.

Đặc biệt:

1. **Plugin resolution** sử dụng cơ chế **pluginManagement.repositories**/plugin marker, khác với **repositories** của **implementation**.
2. Version catalog plugin alias không điều khiển mọi dependencies mà plugin đó thêm vào project.
3. Bạn không thể dùng alias plugin từ catalog như một truy cập **libs.plugins** trực tiếp trong **settings.gradle** theo đúng cách dùng của project build scripts.
4. Đổi version plugin alias có thể thay build logic, nhưng **không tự pin runtimeClasspath**.
5. **[libraries]** và **[plugins]** giải quyết những lớp dependency khác nhau, dù cùng sống trong TOML.

Không nên hiểu câu “catalog không enforce version của library” như tuyên bố mọi luật của plugin DSL đều giống library resolution.

## 12. Version catalog trong multi-project và khi publish libraries

### 12.1. Chia sẻ catalog không đồng nghĩa mọi subproject dùng cùng classpath

Nếu các module **:app**, **:service**, **:lib** cùng dùng **libs.engine**, chúng có cùng **requested version** từ catalog. Nhưng:

- **:app** có thể còn phụ thuộc một client yêu cầu engine 2.0.
- **:service** có thể chỉ dùng engine 1.0.
- **:lib** có thể có runtime dependencies bổ sung khác.

Kết quả **runtimeClasspath** được phân giải riêng trong mỗi project. Để kiểm soát nhóm liên quan, cần platform/constraints hoặc convention policies phù hợp và kiểm tra report của từng module.

### 12.2. Included build không phải một subproject bình thường

**buildSrc** và các **included builds** là builds có settings/configurations riêng. Không được tự suy luận tất cả tự chia sẻ default libs catalog với root build trong mọi trường hợp. Nếu build logic cần các aliases cùng version, phải cấu hình/import catalog phù hợp cho build ấy.

### 12.3. Library published ra ngoài: consumer có thể chọn version khác

Một project library dùng **libs.engine** để khai báo dependency engine 1.0. Khi publish Gradle Module Metadata hoặc Maven POM, consumer khác giải graph của **họ** dựa trên metadata đó cùng với dependencies/constraints riêng.

Vì vậy, library author không thể bảo đảm downstream consumer sẽ chọn engine 1.0 chỉ vì **libs.versions.toml của library ghi 1.0**. Catalog là một phần build logic của producer, không phải bộ cưỡng chế version toàn cục cho mọi consumer.

Nếu API chỉ tương thích một version range, library nên biểu đạt constraint phù hợp qua published metadata (với các giới hạn format), kiểm thử consumer và tránh exact strictly nếu không thật sự cần.

## 13. Khi nào chọn từng cơ chế?

| Nhu cầu thực tế | Công cụ phù hợp | Vì sao |
| --- | --- | --- |
| Tránh lặp tọa độ/module IDs trong scripts | **Version catalog** | Alias rõ, IDE completion |
| Nhiều aliases dùng chung version để dễ cập nhật | **version.ref** | Đồng bộ **declaration inputs** |
| Gom một nhóm dependencies thường đi cùng nhau | **Catalog bundle** | Ngắn gọn, không tự alignment |
| Ràng buộc một dependency không được vượt API range | **strictly(range)** | Giới hạn version được chấp nhận |
| Tránh một vài versions lỗi | **reject(...)** | Loại candidates có vấn đề |
| Nâng một transitive module tối thiểu khi nó xuất hiện | **Dependency constraint** | Không tự thêm module không cần |
| Quản lý nhiều modules phải tương thích nhau | **Platform/BOM, alignment** | Constraints thuộc graph |
| Cưỡng chế trọn bộ version từ BOM trong app | **enforcedPlatform**, có kiểm thử | Cưỡng chế mạnh, có hệ quả |
| Giữ kết quả dependency graph giữa CI và local | **Dependency locking** | Chốt selected versions |
| Kiểm tra artifact không bị thay bytes | **Dependency verification** | Checksum/signature |
| Muốn biết version thật đang chạy | **dependencyInsight + runtimeClasspath** | Đọc graph đã resolve |

**Không có một “catalog setting” nào tự làm hết các việc trên.**

### 13.1. Một chiến lược thực dụng

Với project Java nhiều module:

1. Giữ **gradle/libs.versions.toml** làm nguồn alias/dependency names.
2. Dùng **platform/BOM** nếu hệ sinh thái module cần alignment hoặc version constraints dùng chung.
3. Khi một phiên bản cụ thể bị lỗi, dùng **strictly/reject** đúng phạm vi, không chỉ đổi TOML rồi tin rằng build đã tránh nó.
4. Dùng **dependencyInsight** trên configurations ứng dụng và tests để xem kết quả.
5. Ghi **dependency lockfile** và verification metadata theo chính sách nếu cần build tái lập.
6. Giữ Gradle Wrapper/JDK/repository policy nhất quán giữa CI và máy dev.
7. Chạy unit/integration tests sau mọi thay đổi version có thể ảnh hưởng binary compatibility.

## 14. Debug: catalog ghi 1.0, sao vẫn thấy 2.0?

### Trường hợp A — Thư viện transitive yêu cầu version cao hơn

**Dấu hiệu:** dependency tree có **1.0 -> 2.0**.

**Cách xử lý:** chạy dependencyInsight; xác định dependency nào kéo 2.0. Nếu 2.0 an toàn, cập nhật yêu cầu catalog hoặc giữ graph đã test. Nếu không tương thích, cần sửa dependency graph hoặc strict range phù hợp; không dùng exclude vô điều kiện.

### Trường hợp B — Platform hoặc BOM đang tham gia graph

**Dấu hiệu:** report có component platform và các dòng constraint **(c)**, selection reason **By constraint**.

**Cách xử lý:** đọc version constraints từ platform/BOM. Một regular platform có thể nâng yêu cầu catalog; enforced platform có sức ép cao hơn. Đừng xóa catalog alias để “sửa” một platform được tổ chức cố ý áp dụng.

### Trường hợp C — Rich version của alias không như bạn tưởng

**Dấu hiệu:** TOML là **require/prefer/strictly/reject**; graph chọn version khác hoặc lỗi.

**Cách xử lý:** kiểm tra chính xác object ở **[versions]** hoặc **[libraries].version**, đọc report selection reasons. **prefer** không pin; **require** có thể được nâng; **strictly** hạn chế tập chấp nhận.

### Trường hợp D — Dependency locking giữ version cũ

**Dấu hiệu:** TOML đổi, lockfile chưa update, Gradle báo lock state không nhất quán hoặc version khác kỳ vọng.

**Cách xử lý:** review lockfile, update locks có chủ đích và xác nhận tests; không tự động xóa lock mọi lần catalog thay đổi.

### Trường hợp E — Sai configuration

**Dấu hiệu:** compile graph chọn 1.0 nhưng testRuntime graph chọn 2.0.

**Cách xử lý:** so sánh **compileClasspath**, **runtimeClasspath**, **testRuntimeClasspath** của đúng project; xác định nhánh dependency tạo khác biệt.

### Trường hợp F — Version plugin bị nhầm với version library

**Dấu hiệu:** người dùng sửa **[plugins]** rồi kỳ vọng **implementation** được pin.

**Cách xử lý:** xem plugin resolution và dependency resolution riêng. Plugin có thể thêm dependencies nhưng alias của plugin không thay version constraints cho tất cả runtime modules.

### Trường hợp G — Đã xem TOML nhưng chưa chạy dependency resolution

**Dấu hiệu:** kết luận chỉ dựa vào một dòng **[versions]**.

**Cách xử lý:** chạy:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency demo:engine --configuration runtimeClasspath
~~~

Trong CI, ghi lại report/diff version selection theo quy trình nội bộ. **Phiên bản thực tế là kết quả resolution**, không phải một số text được tìm thấy bằng grep trong TOML.

### Trường hợp H — Repository/cache khiến kết quả khác máy

**Dấu hiệu:** cùng catalog nhưng một máy thấy JAR/metadata khác, hoặc dynamic version thay đổi.

**Cách xử lý:** so sánh repository policy, cache, lock state, metadata và Gradle Wrapper; dùng môi trường kiểm chứng độc lập khi cần. **--refresh-dependencies** tái kiểm tra metadata/artifacts theo cơ chế Gradle, không đồng nghĩa download lại toàn bộ JAR, và không thay thế việc khóa version.

## 15. Lỗi thiết kế thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “TOML ghi 1.0 nên runtime chắc chắn 1.0” | Catalog declaration không phải resolved graph | Xem runtimeClasspath/dependencyInsight |
| “Cùng version.ref nghĩa là modules được align” | Các modules có transitive constraints khác nhau | Dùng platform/BOM/alignment |
| “Bundle là BOM thu nhỏ” | Bundle chỉ khai báo nhiều aliases | Tách bundle khỏi version policy |
| “Direct dependency luôn thắng transitive” | Default conflict resolution có thể nâng direct version | Xem full graph và selection reasons |
| “require nghĩa là strictly” | Require cho phép upgrades | Dùng strictly khi thật cần |
| “Catalog không hỗ trợ strict version” | Rich versions có strictly/prefer/reject | Khai báo TOML đúng và **sử dụng alias** |
| “Strict alias cho module không được dùng vẫn pin mọi graph” | Alias chưa xuất hiện không đóng góp constraint | Dùng platform/constraint trong configuration thực tế |
| “platform lúc nào cũng ép exact version” | Regular platform thường cung cấp constraints có thể được nâng | Phân biệt regular/enforced/strict constraints |
| “enforcedPlatform luôn tốt cho public library” | Có thể buộc consumers dùng version không mong muốn | Chọn regular platform hoặc strict range có chủ đích |
| “Lockfile và catalog là một” | Lock chốt resolved version, catalog tạo requested version | Quản lý riêng và review |
| “force sửa được binary incompatibility” | Có thể khiến JAR runtime thiếu API | Test và thay đổi graph đúng |
| “Thay TOML là đủ cho bảo mật” | Artifact bytes/repository source còn là biến số | Verification, repository policy, test |
| “Tất cả configurations resolve như nhau” | Test/runtime/compile có graph khác | Debug đúng configuration |
| “Không cần xem dependencies vì aliases đều type-safe” | Type safety kiểm tra tên alias, không giải thích selection | dependencies/dependencyInsight |

## 16. Bài tập tự kiểm tra có đáp án

### Bài 1 — Kết quả mặc định

Catalog:

~~~toml
[versions]
engine = "1.0"
client = "1.0"

[libraries]
engine = { module = "demo:engine", version.ref = "engine" }
client = { module = "demo:client", version.ref = "client" }
~~~

Client POM yêu cầu engine 2.0. App dùng **libs.engine** và **libs.client**, không có strict constraints.

**Đáp án:** Gradle thường chọn **demo:engine:2.0**; catalog vẫn giữ requested 1.0. Xem **1.0 -> 2.0** trong dependency report.

### Bài 2 — Đảo hai dòng dependencies

~~~groovy
dependencies {
    implementation libs.client
    implementation libs.engine
}
~~~

**Đáp án:** thứ tự declaration không buộc engine 1.0 thắng. Với graph giống lab, selected engine vẫn là 2.0.

### Bài 3 — Một version key cho ba modules

Ba aliases cùng **version.ref = "stack"** có đủ bảo đảm resolved versions giống nhau không?

**Đáp án:** không. Đây là cách đồng bộ version được **yêu cầu**, không phải graph alignment. Khi transitive constraints khác nhau, từng module vẫn có thể chọn version khác.

### Bài 4 — Dùng bundle

**libs.bundles.all** có cả engine và client. Bundle có loại client transitive engine 2.0 không?

**Đáp án:** không; bundle là nhóm aliases. Resolution vẫn thấy engine 1.0 từ alias và engine 2.0 từ POM client.

### Bài 5 — Rich version

~~~toml
[versions]
engine = { strictly = "1.0" }
~~~

**Hỏi:** điều gì thay đổi khi app thật sự dùng **libs.engine**?

**Đáp án:** yêu cầu từ alias trở thành strict version 1.0, có thể ngăn nâng lên 2.0 hoặc làm graph fail nếu constraints không tương thích. Nó không khiến mọi app không dùng alias bị pin engine 1.0.

### Bài 6 — Prefer

~~~toml
[versions]
engine = { prefer = "1.0" }
~~~

**Đáp án:** prefer là soft preference; một yêu cầu version mạnh hơn trong graph có thể dẫn đến engine 2.0. Không coi prefer như enforced pin.

### Bài 7 — TOML đổi, lockfile vẫn giữ version

Catalog đổi yêu cầu engine 1.0 thành 2.1 nhưng lock ghi engine 2.0.

**Đáp án:** có thể gặp xung đột giữa required version mới và locked strict version. Cần update lock theo quy trình, không tuyên bố catalog đã tự nâng runtime.

### Bài 8 — Catalog và platform

Một platform được import bằng **implementation platform(...)** mang constraints engine 2.0, còn catalog engine yêu cầu 1.0.

**Đáp án:** nếu constraints cho phép, version resolved có thể là 2.0. Cần xem constraint semantics; một regular platform không nhất thiết pin exact trong mọi trường hợp.

### Bài 9 — Alias không được dùng

TOML có **unused = { module = "demo:unused", version = "1.0" }** nhưng app không dùng alias hay module đó.

**Đáp án:** alias không tự thêm dependency; **demo:unused** không xuất hiện chỉ vì có trong catalog.

### Bài 10 — Report nào đúng?

Project nhiều modules, app gặp lỗi runtime với engine. Nên chạy **:lib:compileClasspath** hay **:app:runtimeClasspath**?

**Đáp án:** bắt đầu ở **:app:runtimeClasspath** vì đó là graph của môi trường app gặp lỗi, dùng **:app:dependencyInsight** cho engine. Có thể so sánh thêm :lib/compile và test graphs sau.

### Bài 11 — Nên dùng gì cho an ninh?

App không gọi trực tiếp một thư viện, nhưng transitively nó cần version đã vá. Muốn áp yêu cầu minimum version nếu module xuất hiện.

**Đáp án:** dependency constraint có version tối thiểu thích hợp; catalog alias đơn lẻ không được sử dụng sẽ không có tác dụng. Cần thêm locking/verification và tests theo chính sách.

### Bài 12 — Khi nào enforcedPlatform nguy hiểm?

Bạn xuất bản một library dùng enforcedPlatform cho 30 modules.

**Đáp án:** constraints có thể truyền sang consumers và giới hạn/override những versions họ cần. Nên đánh giá contract, dùng regular platform/rich constraints khi phù hợp và chỉ enforce khi có lý do rõ ràng.

## 17. Checklist trước khi tuyên bố phiên bản đã được kiểm soát

- Đã phân biệt **requested vs resolved** chưa?
- **Version catalog** có đang biểu đạt đúng aliases và rich versions không?
- **version.ref** chỉ chia sẻ declaration hay có platform/constraints cần thiết cho alignment?
- Đã biết **configuration** chịu ảnh hưởng và **project** chủ sở hữu graph chưa?
- Đã chạy **dependencyInsight** cho module có xung đột chưa?
- Có nhánh transitive, platform/BOM, strict/force/rule nào thay kết quả không?
- **Required version** có bị hiểu nhầm thành **strict pin** không?
- Nếu dùng strict/range, các libraries tương thích đã được kiểm chứng chưa?
- Nếu có enforcedPlatform, có đánh giá hệ quả cho consumers của public library chưa?
- Lockfile đã phù hợp với selected versions mong muốn chưa?
- Repository policy và dependency verification có được cấu hình cho build cần độ tin cậy cao chưa?
- Đã chạy Java compile/runtime/integration tests trên **resolved graph** thật chưa?
- CI và máy phát triển dùng cùng Gradle Wrapper, JDK, metadata/repository policy và lock state chưa?

## Tài liệu tham khảo chính thức

- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): TOML format, aliases, rich versions, bundles, plugin aliases và giới hạn version requests.
- [Gradle — Using Catalogs with Platforms](https://docs.gradle.org/current/userguide/centralizing_catalog_platform.html): phân biệt catalog và platform trong dependency resolution.
- [Gradle — Declaring Rich Versions](https://docs.gradle.org/current/userguide/rich_versions.html): require, strictly, prefer, reject và những tác động conflict resolution.
- [Gradle — Platforms](https://docs.gradle.org/current/userguide/platforms.html): regular platform, enforcedPlatform, strict version endorsement.
- [Gradle — Declaring Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html): constraints cho direct/transitive modules, java-platform.
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencies, dependencyInsight, ký hiệu graph và selection reasons.
- [Gradle — Dependency Graph Resolution](https://docs.gradle.org/current/userguide/dependency_graph_resolution.html): version conflicts, lựa chọn module/variants.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): khóa selected versions, update lock state.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum và chữ ký để kiểm tra artifacts.

**Kết luận:** **libs.versions.toml** giúp mô tả **những dependencies/versions mà project muốn yêu cầu** theo cách có tổ chức. **Gradle dependency resolution** mới quyết định **version thực sự được chọn** trong mỗi configuration. Một version catalog thường **không cưỡng chế** kết quả đó chỉ nhờ version string; nếu cần chính sách mạnh, hãy chọn **rich version, constraint, platform, locking** đúng mục đích, rồi xác nhận bằng **dependencyInsight và kiểm thử runtime**.