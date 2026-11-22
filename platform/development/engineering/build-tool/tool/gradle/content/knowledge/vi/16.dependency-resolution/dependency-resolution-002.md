# Xung đột phiên bản và nguyên tắc lựa chọn mặc định trong Gradle

## Mục tiêu bài học

Trong ứng dụng Java, bạn có thể chỉ khai báo **demo:engine:1.0**, nhưng một thư viện khác lại phụ thuộc bắc cầu vào **demo:engine:2.0**. Khi biên dịch hoặc chạy, Gradle cần quyết định **phiên bản nào của cùng một module** sẽ xuất hiện trong dependency graph của một configuration. Nếu không hiểu quy tắc này, bạn rất dễ nhầm rằng phiên bản ghi trực tiếp luôn được giữ, thư viện khai báo trước luôn thắng, hoặc Gradle tự bảo đảm tương thích ngược khi chọn bản mới.

Sau bài này, bạn có thể:

1. Giải thích **version conflict** theo định danh module **group:name** và phân biệt nó với **capability conflict**.
2. Đọc dependency graph gồm yêu cầu trực tiếp và **transitive dependencies**; hiểu **configuration** được phân giải riêng.
3. Mô tả quy tắc thông thường: **Gradle chọn phiên bản cao nhất phù hợp trong các phiên bản được yêu cầu**, sau khi xét constraints, rules, metadata và các hạn chế khác.
4. Phân biệt **version được yêu cầu** với **version cuối cùng được chọn**; giải thích các ký hiệu **1.0 -> 2.0**, **(*)** và các lý do selection trong **dependencyInsight**.
5. Hiểu tại sao “version cố định” kiểu **group:name:1.0** thông thường là **require**, không phải **pin tuyệt đối**.
6. Sử dụng **dependency constraints**, **strictly**, **prefer**, **require**, **reject**, **platform/BOM**, **failOnVersionConflict** và biết rủi ro của **force**.
7. Tạo một ví dụ **Java 17 + Gradle Groovy DSL chạy được** với repository Maven cục bộ, trong đó hai dependency bắc cầu yêu cầu **1.0** và **2.0**.
8. Chẩn đoán và xử lý xung đột mà không vội **exclude** những dependency vẫn cần tại runtime.

Bài chủ yếu dùng **build.gradle (Groovy DSL)**. Các đoạn **build.gradle.kts** chỉ rõ điểm khác ở Kotlin DSL. Các tọa độ **demo:** dùng trong lab là giả định do chính bạn tạo, không phải thư viện công khai cần tải từ Internet.

## 1. Xung đột phiên bản là gì?

Một module bên ngoài Gradle được định danh phổ biến bằng:

~~~text
group:name
~~~

Version là thuộc tính được yêu cầu cho module:

~~~text
group:name:version
~~~

Ví dụ:

~~~text
com.acme:codec:1.0
com.acme:codec:2.0
~~~

Hai tọa độ trên mô tả **cùng module com.acme:codec** nhưng có **hai version khác nhau**. Khi cùng xuất hiện trong graph của một configuration, Gradle phải chọn một version được phép.

### 1.1. Sơ đồ dependency graph

Giả sử:

~~~text
:app
├── com.acme:api-client:1.0
│   └── com.acme:codec:1.0
└── com.acme:report-client:1.0
    └── com.acme:codec:2.0
~~~

Hai nhánh đều yêu cầu **com.acme:codec**. Nếu không có constraint mạnh hay rule thay đổi lựa chọn, Gradle chọn **codec:2.0** theo mặc định.

Graph sau resolution có ý nghĩa:

~~~text
:app
├── api-client:1.0
│   └── codec:1.0 -> 2.0
└── report-client:1.0
    └── codec:2.0
~~~

**codec:1.0 -> 2.0** nghĩa là **yêu cầu 1.0 được điều chỉnh thành version 2.0 đã chọn**; không phải Gradle tải cả hai JAR và nạp chúng cạnh nhau cho cùng một module trong configuration này.

### 1.2. Cùng group:name mới là version conflict thông thường

| Yêu cầu A | Yêu cầu B | Nhận định |
| --- | --- | --- |
| **demo:engine:1.0** | **demo:engine:2.0** | Cùng group/name, khác version → version conflict |
| **demo:engine:1.0** | **demo:parser:2.0** | Hai module khác tên → không phải version conflict trực tiếp |
| **demo:engine:1.0** | **other:engine:2.0** | Group khác nhau → hai module khác nhau |
| **demo:engine:1.0** | **demo:engine:1.0** | Cùng version; thường không tạo version conflict |
| Hai thư viện khác GAV nhưng cùng cung cấp một **capability** | — | Có thể gây **capability conflict**, cần cơ chế khác |

Gradle có hệ thống **capabilities/variant selection** để nhận biết hai module cung cấp cùng một chức năng. Khi hai module khác nhau có cùng capability, Gradle không đơn thuần “chọn version cao nhất của group:name”, mà có thể báo conflict và yêu cầu rule chọn implementation.

**Phạm vi chính của bài này** là **version conflict của cùng module**, không phải giải quyết mọi trường hợp JAR trùng class hoặc conflict giữa implementations.

## 2. Quy tắc mặc định: chọn phiên bản cao nhất được chấp nhận

Theo cơ chế giải quyết graph, Gradle xét **những yêu cầu về version** từ tất cả nhánh liên quan, gồm direct dependencies, transitive dependencies và constraints. Trong trường hợp thông thường có nhiều version cố định được yêu cầu cho **cùng một module**, Gradle chọn **version cao nhất** trong những lựa chọn không bị cấm.

Ví dụ:

~~~groovy
dependencies {
    implementation 'demo:engine:1.0'
    implementation 'demo:engine:2.0'
}
~~~

Nếu cả hai version tồn tại, module có metadata/artifact hợp lệ, không có rule đặc biệt và không có strict constraint mâu thuẫn, version cuối cùng thường là **2.0**.

Điều này có ba hệ quả quan trọng:

1. **Không phải “version khai báo đầu tiên thắng”.** Đảo hai dòng dependency không làm **1.0** thắng.
2. **Không phải “dependency trực tiếp thắng transitive”.** Direct **1.0** có thể bị nâng thành **2.0** do nhánh transitive.
3. **Không phải “thư viện yêu cầu nhiều lần hơn thắng”.** Một lần yêu cầu **2.0** vẫn có thể vượt nhiều lần yêu cầu **1.0**.

Gradle không tự biết **2.0** có binary compatibility với API của **1.0** hay không. Quy tắc chọn version giải quyết graph, **không thay thế kiểm thử biên dịch/runtime**.

### 2.1. Cụm “cao nhất” có ngoại lệ về constraint/range

Không thể rút gọn Gradle thành một hàm **Math.max** với mọi version:

- Một dependency có **strictly('1.0')** không chấp nhận version **2.0**.
- Một **reject('2.0')** loại **2.0** khỏi tập ứng viên được phép.
- **version ranges** có thể giới hạn hoặc tác động tới ứng viên.
- **platform/BOM**, dependency constraints và resolution rules có thể nâng, hạ hoặc chặn một version.
- Module metadata có **variants/capabilities** có thể làm lựa chọn phức tạp hơn.
- Dynamic versions như **1.+** cần tìm candidate trên repositories và phụ thuộc cache thời điểm.

Vì thế, cách nói chính xác là: **quy tắc mặc định chọn highest acceptable candidate, trong giới hạn version requirements và các cơ chế resolution đang có hiệu lực**.

### 2.2. Một graph đã chọn version không có nghĩa mọi configuration cùng chọn

Trong Java plugin, các configuration như:

- **compileClasspath**
- **runtimeClasspath**
- **testCompileClasspath**
- **testRuntimeClasspath**

có tập dependency, variants và phạm vi khác nhau. Chẳng hạn **testImplementation** thêm thư viện chỉ cho test; vì vậy version của một module có thể khác giữa compile và test graph.

Khi kiểm tra version, luôn hỏi: **module nào, project nào, configuration nào?** Không đọc kết quả **runtimeClasspath** rồi mặc định **testRuntimeClasspath** giống hệt.

## 3. Trực tiếp hay bắc cầu: một yêu cầu version thường không phải pin

### 3.1. Direct dependency không có quyền ưu tiên tự động

Ví dụ:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'demo:engine:1.0'
    implementation 'demo:client:1.0'
}
~~~

Giả sử metadata của **demo:client:1.0** nói rằng nó phụ thuộc **demo:engine:2.0**. Khi phân giải **runtimeClasspath**, nếu không có hạn chế mạnh hơn, Gradle thường chọn engine **2.0**.

Câu **implementation 'demo:engine:1.0'** không nói “chỉ được dùng đúng 1.0”. Nó đặt một **required version** theo nghĩa có thể được nâng do conflict resolution. Một version cố định trong notation không đồng nghĩa một strict pin.

### 3.2. Transitive dependency đến từ metadata

Một thư viện từ Maven repository thường có file **POM** mô tả dependencies của nó. Gradle cũng hỗ trợ **Gradle Module Metadata** có variants/constraints giàu thông tin hơn. Vì vậy:

- Project của bạn có thể không khai báo **engine** nhưng engine vẫn xuất hiện qua client.
- Version **2.0** có thể đến từ nhiều nhánh transitive, không hẳn từ một dòng trong build.gradle.
- Một dependency constraint có thể tham gia chọn version **mà không tự thêm module** vào graph.

Để biết thật sự version nào đang được yêu cầu bởi những nhánh nào, cần dùng **dependencies** hoặc **dependencyInsight**, không đoán từ tên thư viện.

### 3.3. Tại sao Gradle thường dùng một version của module?

Trên một Java classpath, hai JAR cung cấp cùng package/class ở hai version có thể dẫn tới hành vi phụ thuộc thứ tự classloader và lỗi linkage. Gradle cố gắng tạo graph thống nhất cho một module trong một configuration. Đây là lý do **version conflict** được giải quyết thay vì tải mọi version riêng lẻ.

Tuy vậy, Gradle không thể bảo đảm tránh tất cả **duplicate classes**. Hai module khác GAV có thể cùng chứa một class; một JAR “shaded” có thể có code trùng; custom classloaders có thể nạp các version khác nhau ở runtime. Đó là những vấn đề rộng hơn version conflict của một module.

## 4. Cách Gradle so sánh phiên bản

Gradle có **version ordering** riêng; không được áp dụng so sánh chuỗi ký tự đơn thuần.

### 4.1. Thứ tự phiên bản số

~~~text
1.9 < 1.10
1.2 < 1.3
2.0 < 10.0
~~~

Dù string **"1.9"** có thể lớn hơn **"1.10"** trong một phép so từ điển, Gradle phân tách các phần phiên bản và so phần số thích hợp.

### 4.2. Qualifiers và stability

Version có thể chứa hậu tố như **-alpha**, **-beta**, **-rc**, **-SNAPSHOT**, **-final**, **-release**. Gradle có quy tắc so sánh những qualifier, ưu tiên bản phát hành không qualifier khi các ứng viên có cùng base version trong những trường hợp thông thường.

Ví dụ khái niệm:

~~~text
1.0-beta < 1.0
~~~

Nhưng đừng nghĩ Gradle là một bộ kiểm tra **Semantic Versioning** đầy đủ hoặc tự phát hiện API-breaking changes. Những version như **1.0.0-jre** và **1.0.0-android**, hoặc timestamp/SNAPSHOT, cần đánh giá theo quy tắc version ordering, metadata và status thực tế.

### 4.3. Dynamic version khác xung đột giữa hai version cố định

~~~groovy
dependencies {
    implementation 'demo:engine:1.+'
}
~~~

Dạng **1.+** yêu cầu Gradle chọn một version phù hợp với prefix đó từ các version có trong repository. Bởi vậy:

- **Version động** cần khám phá danh sách version từ metadata/repositories.
- Kết quả có thể thay đổi khi repository publish version mới hoặc cache hết TTL.
- Nếu module còn bị một nhánh khác yêu cầu version cụ thể, conflict resolution lại xem toàn bộ yêu cầu.
- Không nên chỉ viết **1.+** rồi kỳ vọng classpath được ghim vĩnh viễn.

Trong build cần reproducibility, ưu tiên version được kiểm soát, dependency locking/verification, và hạn chế dynamic versions.

## 5. Đọc dependency report: requested version và selected version

Gradle cung cấp task **dependencies** và **dependencyInsight** để bạn kiểm tra chính xác.

### 5.1. dependencies cho toàn graph

Ví dụ trên Linux/macOS:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Một đoạn report **minh họa**, không nhất thiết trùng byte với output của mọi bản Gradle:

~~~text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- demo:client-a:1.0
|    \--- demo:engine:1.0 -> 2.0
\--- demo:client-b:1.0
     \--- demo:engine:2.0
~~~

Các ký hiệu cần biết:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| **1.0 -> 2.0** | Yêu cầu **1.0**, nhưng version chọn là **2.0** |
| **(*)** | Nhánh con đã được hiển thị ở vị trí khác; report bỏ lặp |
| **(c)** | Dependency constraint, không tự thêm module vào graph |
| **(n)** | Dependency chưa được phân giải ở vị trí report đó |
| **FAILED** | Phân giải ở nút tương ứng thất bại |

Không nhất thiết mọi nhánh của report đều in được URL repository; report tập trung vào graph và version selection.

### 5.2. dependencyInsight cho một module

~~~bash
./gradlew dependencyInsight --dependency demo:engine --configuration runtimeClasspath
~~~

PowerShell:

~~~powershell
.\gradlew.bat dependencyInsight --dependency demo:engine --configuration runtimeClasspath
~~~

Ở project multi-module, chỉ định đúng project:

~~~bash
./gradlew :app:dependencyInsight --dependency demo:engine --configuration runtimeClasspath
~~~

Báo cáo có thể nêu:

- **By conflict resolution: between versions 1.0 and 2.0**.
- **By constraint** nếu một constraint tác động.
- **By ancestor** nếu strict version ở một nhánh áp dụng.
- **Forced** nếu có force/enforced platform.
- **Selected by rule** nếu custom resolution rule thay đổi lựa chọn.
- Các đường dẫn dependency đưa phiên bản vào graph.

**Không chỉ xem “selected version”**: cần biết **ai yêu cầu phiên bản khác** và **vì sao Gradle chọn version ấy**.

### 5.3. Phân tích phiên bản được chọn từ góc nhìn an toàn

Nếu report cho thấy **1.0 -> 2.0**, cần kiểm tra:

1. **Compile:** code của project còn biên dịch với API 2.0 không?
2. **Runtime:** các thư viện transitive vẫn tương thích nhị phân với 2.0 không?
3. **Tests:** unit/integration/smoke tests đã chạy trên resolved graph thật chưa?
4. **Security:** version chọn có thuộc danh sách bị từ chối, thiếu bản vá hoặc source không tin cậy không?
5. **Publishing:** nếu project là thư viện, constraints/metadata có được xuất bản nhất quán cho người tiêu dùng không?

Chọn phiên bản mới hơn là một **quy tắc graph**, không phải bằng chứng version mới an toàn với mọi caller.

## 6. Bài thực hành Java 17: hai nhánh yêu cầu hai version của cùng module

Mục tiêu là tạo **local Maven repository** chứa:

~~~text
demo:client-a:1.0 -> demo:engine:1.0
demo:client-b:1.0 -> demo:engine:2.0
~~~

Đồng thời repository chứa **engine 1.0** và **engine 2.0** với hai file JAR khác nhau, class chung **demo.Engine**:

- Engine **1.0**: **Engine.version()** trả về **"1.0"**.
- Engine **2.0**: **Engine.version()** trả về **"2.0"**.

Project app phụ thuộc trực tiếp **client-a** và **client-b**, không phụ thuộc trực tiếp engine ở lần chạy đầu. Gradle phải phân giải transitive conflict. **Không cần Maven Central cho dependencies của lab**; chỉ cần Gradle Wrapper, JDK 17 tương thích và các file được tạo bên dưới.

### 6.1. Cấu trúc thư mục

~~~text
gradle-conflict-lab/
├── settings.gradle
├── build.gradle
├── FixtureGenerator.java
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── src/main/java/demo/App.java
└── lab-repo/                    # sẽ được tạo từ FixtureGenerator
    └── demo/
        ├── engine/1.0/
        │   ├── engine-1.0.pom
        │   └── engine-1.0.jar
        ├── engine/2.0/
        │   ├── engine-2.0.pom
        │   └── engine-2.0.jar
        ├── client-a/1.0/
        │   ├── client-a-1.0.pom
        │   └── client-a-1.0.jar
        └── client-b/1.0/
            ├── client-b-1.0.pom
            └── client-b-1.0.jar
~~~

**Wrapper hợp lệ** phải được lấy từ một project đã khởi tạo hoặc tạo bằng Gradle đã cài; không tự dựng **gradle-wrapper.jar** bằng mã này. Có thể đặt các files của lab trong một thư mục mới và dùng Wrapper từ project tin cậy cùng phiên bản Gradle/JDK phù hợp.

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'gradle-conflict-lab'
~~~

### 6.3. Tạo fixture Maven bằng Java 17 (không cần thư viện ngoài)

Lưu chương trình dưới tên **FixtureGenerator.java** ở root project:

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
            throw new IllegalStateException("Requires a JDK, not only a JRE");
        }

        engine(compiler, "1.0");
        engine(compiler, "2.0");

        client("client-a", "1.0");
        client("client-b", "2.0");

        System.out.println("Generated four local Maven modules.");
    }

    private static void engine(
            JavaCompiler compiler, String version
    ) throws IOException {
        Path src = Path.of(
                "lab-build", version, "src", "demo", "Engine.java"
        );
        Path classes = Path.of("lab-build", version, "classes");
        Files.createDirectories(src.getParent());
        Files.createDirectories(classes);

        String javaSource =
                "package demo;\n" +
                "public final class Engine {\n" +
                "  public static String version() { return \"" +
                version + "\"; }\n" +
                "}\n";

        Files.writeString(src, javaSource, StandardCharsets.UTF_8);
        int exit = compiler.run(
                null, null, null,
                "--release", "17",
                "-d", classes.toString(),
                src.toString()
        );
        if (exit != 0) {
            throw new IOException("Compilation failed for engine " + version);
        }

        Path module = modulePath("engine", version);
        writePom(module, "engine", version, null);

        Path jar = module.resolve("engine-" + version + ".jar");
        try (JarOutputStream out =
                     new JarOutputStream(Files.newOutputStream(jar))) {
            out.putNextEntry(new JarEntry("demo/Engine.class"));
            Files.copy(classes.resolve("demo/Engine.class"), out);
            out.closeEntry();
        }
    }

    private static void client(
            String name, String engineVersion
    ) throws IOException {
        Path module = modulePath(name, "1.0");
        writePom(module, name, "1.0", engineVersion);

        // JAR rỗng nhưng hợp lệ: client chỉ mang dependency metadata.
        try (JarOutputStream ignored = new JarOutputStream(
                Files.newOutputStream(module.resolve(name + "-1.0.jar")))) {
            // No class entries are necessary for the lab.
        }
    }

    private static Path modulePath(
            String artifactId, String version
    ) throws IOException {
        Path directory = Path.of(
                "lab-repo", "demo", artifactId, version
        );
        Files.createDirectories(directory);
        return directory;
    }

    private static void writePom(
            Path directory,
            String artifactId,
            String version,
            String engineVersion
    ) throws IOException {
        String dependency = engineVersion == null ? "" : """
                  <dependencies>
                    <dependency>
                      <groupId>demo</groupId>
                      <artifactId>engine</artifactId>
                      <version>%s</version>
                      <scope>compile</scope>
                    </dependency>
                  </dependencies>
                """.formatted(engineVersion);

        String pom = """
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <modelVersion>4.0.0</modelVersion>
                  <groupId>demo</groupId>
                  <artifactId>%s</artifactId>
                  <version>%s</version>
                  <packaging>jar</packaging>
                %s</project>
                """.formatted(artifactId, version, dependency);

        Files.writeString(
                directory.resolve(artifactId + "-" + version + ".pom"),
                pom,
                StandardCharsets.UTF_8
        );
    }
}
~~~

**Tại sao fixture này hợp lệ?**

- **JavaCompiler** thuộc JDK, được dùng để biên dịch hai bản **Engine.class** khác nhau.
- Maven layout gồm **demo/engine/1.0/engine-1.0.pom** và **demo/engine/2.0/engine-2.0.pom**.
- Mỗi **client** có POM khai báo dependency trên engine với một version riêng.
- **client-a/client-b** có JAR rỗng nhưng hợp lệ; nhiệm vụ của chúng trong lab là mang **metadata dependency**.
- **Gradle đọc POM**, tạo graph, rồi xác định engine version; không cần tải framework bên ngoài.

Cách chạy trên Linux/macOS/PowerShell (có JDK 17+):

~~~bash
javac FixtureGenerator.java
java FixtureGenerator
~~~

Stdout khi thành công:

~~~text
Generated four local Maven modules.
~~~

### 6.4. build.gradle — cấu hình application

~~~groovy
plugins {
    id 'application'
}

repositories {
    maven {
        name = 'fixtureRepo'
        url = uri('lab-repo')
    }
}

dependencies {
    implementation 'demo:client-a:1.0'
    implementation 'demo:client-b:1.0'
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

**Không có mavenCentral()**: hai client và hai version engine được cung cấp từ thư mục **lab-repo**. Nếu Gradle Wrapper hoặc Java toolchain cần tải lần đầu, bước thiết lập môi trường có thể cần kết nối mạng; điều đó độc lập với dependency resolution trong lab.

### 6.5. src/main/java/demo/App.java

~~~java
package demo;

public final class App {
    public static void main(String[] args) {
        System.out.println("Selected engine: " + Engine.version());
    }
}
~~~

**App.java** tham chiếu **demo.Engine** từ module **demo:engine** được kéo vào classpath qua dependencies của clients. Nó không import version trực tiếp, vì version là thông tin phân giải của Gradle, không phải một phần tên package Java.

### 6.6. Quan sát kết quả mặc định

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

Trong graph **runtimeClasspath**, bạn sẽ thấy hai yêu cầu **demo:engine:1.0** và **demo:engine:2.0**; report thể hiện yêu cầu **1.0** được chọn thành **2.0**.

Dòng do **App** in ra:

~~~text
Selected engine: 2.0
~~~

Gradle còn in thông tin task và trạng thái build; đây chỉ là stdout của **App**.

### 6.7. Thêm direct dependency engine:1.0 có thay kết quả không?

Thêm vào **dependencies** của build.gradle:

~~~groovy
dependencies {
    implementation 'demo:client-a:1.0'
    implementation 'demo:client-b:1.0'
    implementation 'demo:engine:1.0'  // Yêu cầu trực tiếp
}
~~~

Trong graph vẫn có yêu cầu **engine:2.0** từ client-b. Nếu không có strict constraint/rule khác, Gradle tiếp tục chọn **engine:2.0**. Dòng **Selected engine: 2.0** không đổi.

**Bài học:** một dòng khai báo trực tiếp **1.0** thông thường không pin version đó khi transitive graph có version cao hơn.

### 6.8. Đổi thứ tự hai client có thay version không?

Thử hoán đổi:

~~~groovy
dependencies {
    implementation 'demo:client-b:1.0'
    implementation 'demo:client-a:1.0'
}
~~~

Trong ví dụ không có rule đặc biệt, engine vẫn được chọn **2.0**, vì Gradle không giải quyết version conflict chỉ bằng thứ tự dòng declaration.

### 6.9. Kiểm chứng không phụ thuộc vào mạng ngoài

Thư mục **lab-repo** có đầy đủ POM/JAR cho tất cả tọa độ lab. Nếu lệnh thất bại:

- Kiểm tra đã chạy **java FixtureGenerator** trước chưa.
- Kiểm tra đường dẫn **lab-repo/demo/engine/2.0/engine-2.0.jar**.
- Kiểm tra JDK 17+ được cung cấp cho toolchain.
- Kiểm tra thực sự đang chạy từ root project chứa **settings.gradle**.
- Kiểm tra Gradle Wrapper được cài đặt/khởi tạo hợp lệ.

Nếu hệ thống có cache cũ cho cùng GAV từ một lab khác, nên dùng **Gradle User Home riêng** hoặc tọa độ fixture khác trong môi trường thử nghiệm; đừng xóa cache chung của mọi project một cách tùy tiện.

## 7. Tùy chỉnh hành vi: failOnVersionConflict

Mặc định Gradle giải quyết conflict bằng một selected version. Nhưng một tổ chức có thể muốn **build thất bại ngay khi có hai yêu cầu version khác nhau**, trước khi lựa chọn ngầm tạo ra hành vi khó dự đoán.

Trong **build.gradle**:

~~~groovy
configurations.configureEach {
    resolutionStrategy.failOnVersionConflict()
}
~~~

Sau đó chạy:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Với lab ở mục 6, có **hai yêu cầu engine 1.0 và 2.0**, việc resolution có thể dừng với lỗi conflict thay vì báo graph chọn 2.0. Đây là **hành vi có chủ đích của policy**, không phải thư viện thiếu.

### 7.1. Vì sao không luôn bật failOnVersionConflict cho mọi build?

- Một dependency graph lớn có thể có nhiều yêu cầu cũ/mới vốn đã được test chạy với version cao hơn.
- Bật strict conflict reporting có thể làm build chuyển từ thành công sang thất bại mà chưa cung cấp chiến lược nâng cấp thư viện.
- Một số ecosystem dùng BOM/platform để phối hợp version; cần đánh giá cách policy tương tác với các module hiện có.
- Nếu muốn đảm bảo dependency graph đáng tin cậy, bạn còn cần dependency locking, verification và test runtime, không chỉ phát hiện conflict.

Dùng **failOnVersionConflict** khi team muốn xem mọi version disagreement là lỗi cần giải quyết tường minh. Để bắt đầu, có thể áp dụng cho một số configurations phù hợp thay vì áp cho tất cả rồi phải xử lý ngay hàng trăm xung đột lịch sử.

### 7.2. Giới hạn chính sách theo configuration

Ví dụ:

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.failOnVersionConflict()
}
~~~

Dạng này chỉ tác động tới **runtimeClasspath** của project hiện tại. Nếu cần testRuntimeClasspath hoặc các project khác, phải cấu hình riêng hoặc dùng convention plugin chung.

## 8. Dependency constraints: đưa ra yêu cầu mà không thêm module mới

Constraint nói: **nếu module X xuất hiện trong graph, version của nó phải đáp ứng một điều kiện**. Constraint **không tự thêm** X nếu không có dependency khác cần nó.

Ví dụ:

~~~groovy
dependencies {
    implementation 'demo:client-a:1.0'
    implementation 'demo:client-b:1.0'

    constraints {
        implementation('demo:engine:2.0') {
            because 'We tested the application with engine 2.0'
        }
    }
}
~~~

**Constraint** này giúp ghi rõ version yêu cầu, nhưng vẫn là một **requirement có thể bị nâng** nếu graph có yêu cầu cao hơn và không có chặn. Nếu cả hai client bị loại khỏi graph và không có direct engine, constraint không tự bổ sung engine JAR.

### 8.1. Vì sao cần constraint thay vì thêm dependency trực tiếp?

Khi ứng dụng không gọi API của một module trực tiếp nhưng module đó là transitive dependency, thêm **implementation 'module:version'** vào build để áp policy có thể làm module xuất hiện dù nhánh transitive đã không còn cần nó. **Constraint** chỉ có tác dụng khi module thực sự được yêu cầu bởi một dependency.

Đây đặc biệt hữu ích khi:

- Cần nâng transitive dependency để có bản vá.
- Cần loại version lỗi mà không luôn thêm module mới.
- Cần mô tả giới hạn tương thích cho library consumers.
- Cần quản lý nhóm version bằng **java-platform** và published metadata.

### 8.2. Bare constraint không phải pin

~~~groovy
dependencies {
    constraints {
        implementation 'demo:engine:1.0'
    }
}
~~~

Dòng trên thông thường tương tự **require 1.0** và có thể bị graph nâng lên **2.0**. Nếu thật sự không thể dùng 2.0, cần dùng **strictly** hoặc một constraint thích hợp, không nghĩ bare version sẽ chặn upgrade.

## 9. Rich versions: require, strictly, prefer, reject

Gradle có các cấp độ version declaration để diễn đạt **mức độ bắt buộc**.

| Khai báo | Ý nghĩa căn bản | Có thể bị nâng? |
| --- | --- | --- |
| **require('1.0')** | Version phải đáp ứng tối thiểu 1.0 theo nghĩa default requirement | **Có**, bởi constraint/conflict resolution |
| **prefer('1.0')** | Ưu tiên mềm nếu không có yêu cầu mạnh hơn | **Có** |
| **strictly('1.0')** | Chỉ chấp nhận đúng 1.0 (hoặc range nếu khai báo range) | **Không** cho version ngoài phạm vi |
| **reject('2.0')** | Không chấp nhận version 2.0 | Phải chọn version khác hoặc thất bại |

### 9.1. strictly: yêu cầu thực sự chặt

Trong lab:

~~~groovy
dependencies {
    implementation 'demo:client-a:1.0'
    implementation 'demo:client-b:1.0'

    constraints {
        implementation('demo:engine') {
            version {
                strictly('1.0')
            }
            because('Only engine 1.0 is approved')
        }
    }
}
~~~

Ở đây client-b **require engine 2.0**, còn constraint chỉ chấp nhận **engine 1.0**. Trong tình huống này, Gradle có thể **thất bại vì version requirements không tương thích**, thay vì tự chọn 1.0 rồi bỏ qua yêu cầu tối thiểu 2.0.

**Đừng dùng strictly chỉ để “ép cho build chạy”** khi một thư viện thực sự yêu cầu API của version cao hơn. Nếu muốn downgrade, cần đánh giá compatibility và thay đổi dependency graph hoặc module phù hợp.

### 9.2. strictly với range linh hoạt

~~~groovy
dependencies {
    constraints {
        implementation('demo:engine') {
            version {
                strictly('[1.0, 2.0[')
                prefer('1.5')
            }
            because('Supported range is 1.x, prefer 1.5')
        }
    }
}
~~~

- **[1.0, 2.0[** nghĩa là nhận **1.0** trở lên nhưng loại **2.0** và các version cao hơn.
- **prefer 1.5** là ứng viên ưu tiên mềm nếu có; nó không bắt buộc repository phải tồn tại 1.5 nếu dependency graph có cách chọn version khác hợp lệ trong range.
- Nếu nhánh khác bắt buộc **engine:2.0**, strict range có thể dẫn tới resolution error.

Trong thư viện được xuất bản cho bên thứ ba, **strict range** thường uyển chuyển hơn strict exact version vì không ép mọi consumer dùng đúng một bản.

### 9.3. reject: loại version lỗi

~~~groovy
dependencies {
    constraints {
        implementation('demo:engine') {
            version {
                require('[1.0, 3.0[')
                reject('1.5')
            }
            because('Avoid engine 1.5 regression')
        }
    }
}
~~~

Khi chọn version trong phạm vi thích hợp, Gradle loại ứng viên **1.5** khỏi tập chấp nhận. **reject** không tự có nghĩa “chọn đúng 1.4”; nó chỉ cấm những version đã nêu. Nếu không còn candidate phù hợp, resolution có thể thất bại.

Đối với CVE/bug, hãy nêu **version nào thực sự bị lỗi** và **đã có bản vá ở version nào** dựa trên thông tin đáng tin cậy, không sao chép ví dụ version giả định này như advisory an ninh.

### 9.4. prefer: gợi ý, không phải cưỡng chế

~~~groovy
dependencies {
    constraints {
        implementation('demo:engine') {
            version {
                prefer('1.0')
            }
        }
    }
}
~~~

Nếu graph có yêu cầu mạnh hơn **2.0**, **prefer 1.0** không bảo đảm chọn 1.0. Đây là điểm khác với **strictly**.

### 9.5. require và upper bound trong range

Có sự tinh tế với **require('[1.0, 2.0[')**: theo cơ chế Gradle, một yêu cầu **require** không nhất thiết cấm nâng lên version nằm trên upper bound nếu xung đột với một yêu cầu version cao hơn. Nếu mục tiêu là **chặn hoàn toàn 2.x**, hãy dùng **strictly('[1.0, 2.0[')**.

**Mẹo ghi nhớ:** 
- **require**: mức yêu cầu thông thường.
- **prefer**: đề nghị.
- **strictly**: giới hạn cứng.
- **reject**: danh sách phiên bản không chấp nhận.

## 10. Force, eachDependency và các resolution rules: dùng có cân nhắc

Gradle có API cũ hoặc chuyên biệt để override resolution khi bạn không thể sửa metadata/declarations gốc.

### 10.1. resolutionStrategy.force

~~~groovy
configurations.configureEach {
    resolutionStrategy.force('demo:engine:1.0')
}
~~~

**force** bảo Gradle ưu tiên version 1.0 cho module engine bất kể yêu cầu khác. Nếu client-b được biên dịch với API chỉ có ở engine 2.0, việc ép 1.0 có thể làm ứng dụng ném **NoSuchMethodError**, **NoClassDefFoundError** hoặc lỗi runtime tương tự.

Trong lab hiện tại class Engine vẫn có method **version()** ở hai version nên force 1.0 có thể tạo stdout **Selected engine: 1.0**. Nhưng đó **không chứng minh mọi trường hợp force downgrade đều an toàn**.

Tài liệu Gradle hiện đại khuyến nghị ưu tiên **rich versions/strictly** và dependency constraints hơn force cho các build mới, vì chúng diễn đạt yêu cầu version rõ hơn và có thể được truyền qua Gradle Module Metadata.

### 10.2. eachDependency khi thật sự cần rule động

~~~groovy
configurations.configureEach {
    resolutionStrategy.eachDependency { details ->
        if (details.requested.group == 'demo' &&
            details.requested.name == 'engine') {
            details.useVersion('2.0')
            details.because('Policy chooses engine 2.0')
        }
    }
}
~~~

Đây là **rule xử lý lựa chọn dependency**. Nó có thể phù hợp khi mapping version theo chính sách tổ chức không thể biểu đạt bằng constraint đơn giản, nhưng có nhược điểm:

- Logic ẩn trong một rule toàn cục khó tìm hơn khai báo dependency.
- Có thể thay version mà người tiêu dùng không ngờ.
- Cần áp dụng đúng scope configuration và test kết quả.
- Không nên dùng để che dependency metadata sai; cân nhắc component metadata rules và sửa publishing ở nguồn.

Bài này không khuyến nghị đồng thời **force**, **strictly**, **eachDependency**, **platform** cho cùng một module chỉ để tìm một tổ hợp “vừa chạy”. Hãy chọn **một cơ chế chính có mục tiêu rõ ràng**, kiểm tra insight và tests.

## 11. Platform/BOM và version catalog: đừng nhầm vai trò

Trong ứng dụng lớn, nhiều module phải dùng version phối hợp. Gradle hỗ trợ **platform** và **Maven BOM**.

### 11.1. platform mang constraints vào graph

Ví dụ Maven BOM:

~~~groovy
dependencies {
    implementation platform('org.example:example-bom:1.0')
    implementation 'org.example:module-a'
    implementation 'org.example:module-b'
}
~~~

Các tọa độ **org.example** ở đây **chỉ minh họa**, không có nghĩa bom này tồn tại công khai. Nếu BOM thật được import, các constraints trong BOM góp phần chọn version của các module liên quan.

**Một platform thường đưa ra version recommendations/constraints**, có thể được nâng bởi yêu cầu từ dependencies khác (trừ các **strict constraints** trong platform được endorsement theo semantics của Gradle).

### 11.2. enforcedPlatform có sức ép mạnh hơn

~~~groovy
dependencies {
    implementation enforcedPlatform('org.example:example-bom:1.0')
}
~~~

**enforcedPlatform** làm version constraints của BOM có tính cưỡng chế mạnh, có thể override yêu cầu khác. Điều đó hữu ích khi ứng dụng cần một bộ version đã kiểm thử thống nhất, nhưng có thể ảnh hưởng consumer nếu bạn **xuất bản thư viện** và để constraints lan truyền.

Không dùng **enforcedPlatform** tùy tiện trong library dùng chung chỉ để tránh đọc dependency graph. Nếu cần, xem cả ảnh hưởng transitive cho người tiêu dùng.

### 11.3. Version catalog không tự giải quyết conflict

Tệp **gradle/libs.versions.toml**:

~~~toml
[versions]
engine = "1.0"

[libraries]
engine = { module = "demo:engine", version.ref = "engine" }
~~~

Và trong build.gradle:

~~~groovy
dependencies {
    implementation libs.engine
}
~~~

Catalog giúp **đặt alias và tái sử dụng tọa độ/version declaration**, nhưng không tự pin classpath. Nếu graph có **demo:engine:2.0** transitive và không có strict constraint/rule khác, Gradle vẫn có thể chọn **2.0**.

Đây là một nhầm lẫn rất phổ biến: **đồng bộ file catalog** không đồng nghĩa **đồng bộ version đã resolved**. Hãy xem **dependencyInsight** và dùng platforms/constraints khi cần mô hình hóa version policy.

## 12. Dependency locking: khóa kết quả resolution cho build tái lập

Khi dependency graph có version động, changing modules hoặc nhiều nhánh yêu cầu version khác nhau, kết quả có thể thay đổi theo thời gian nếu metadata và cache thay đổi. **Dependency locking** giúp kiểm soát version cuối cùng đã phân giải, thay vì chỉ ghi version yêu cầu.

Ví dụ trong **build.gradle**:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Để tạo/ghi lock state cho configuration phù hợp:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --write-locks
~~~

Việc này tạo/cập nhật lock file theo cơ chế Gradle của bản đang dùng. **Cần review và commit lock file** nếu policy của repo yêu cầu khóa dependency để CI dùng cùng kết quả.

Đừng ghi lock file chỉ dựa vào artifact không đáng tin cậy; **locking chọn version**, không tự xác minh checksum hoặc tính an toàn của binary.

### 12.1. Khi graph yêu cầu nâng version nhưng lock giữ bản cũ

Gradle áp dụng locked versions như các **strict constraints** trong resolution. Nếu dependency trực tiếp mới có yêu cầu **tối thiểu cao hơn** locked version, resolution có thể thất bại. Đây là tín hiệu cần **update locks có chủ đích**, không xóa file lock để Gradle tự chọn version khác mà không review.

### 12.2. Dependency verification khác dependency locking

| Cơ chế | Kiểm soát |
| --- | --- |
| Version declaration | Yêu cầu version khi khai báo dependency |
| Constraint/strict/platform | Version nào được chấp nhận khi graph resolution |
| Dependency locking | Các version **đã chọn** được giữ nhất quán |
| Dependency verification | Bytes/metadata được tải có checksum/signature đáng tin |
| Repositories policy | Nguồn nào được phép cung cấp module |

Nhiều biện pháp kết hợp mới tạo build có thể kiểm chứng. Không có một lệnh **force** hay **lockAllConfigurations** nào tự giải quyết tất cả supply-chain risks.

## 13. Exclude không phải công cụ đầu tiên để sửa version conflict

Khi report có **demo:engine:1.0 -> 2.0**, một cách phản xạ sai là xóa engine transitive từ client-b:

~~~groovy
dependencies {
    implementation('demo:client-b:1.0') {
        exclude group: 'demo', module: 'engine'
    }
}
~~~

Đoạn này loại yêu cầu engine đi qua **một nhánh**. Nhưng nếu client-b thực sự gọi API của engine, việc loại dependency có thể gây **NoClassDefFoundError** hoặc **NoSuchMethodError** ở runtime. Nếu engine còn được kéo từ nhánh khác, exclude ở một nơi **không nhất thiết xóa hoàn toàn module khỏi graph**.

**Ưu tiên điều tra trước:**

1. Xác định client-b có thật sự cần engine không.
2. Kiểm tra version 2.0 có tương thích với client-a và App không.
3. Nếu vấn đề là metadata sai, sửa metadata ở nguồn hoặc dùng metadata rules phù hợp.
4. Nếu là version policy, dùng constraint/strict/version catalog + platform đúng vai trò.
5. Chỉ exclude module khi nó thật sự không cần, hoặc có implementation thay thế đã được kiểm chứng; giữ scope exclude càng hẹp càng tốt.

### 13.1. Exclude khác version reject

- **exclude** loại dependency edge/module khỏi một phần graph.
- **reject** loại **candidate version** khỏi tập version có thể chọn.
- **strictly** giới hạn tập **version chấp nhận**.
- **force** cưỡng chế version lựa chọn trên configuration.

Nếu bạn chỉ muốn tránh **engine 1.5** bị lỗi, **reject 1.5** hợp lý hơn một global exclude xóa toàn bộ engine.

## 14. Capability conflicts và variant conflicts là một nhóm khác

Gradle cũng có xung đột khi **hai component khác nhau cung cấp cùng capability**, chẳng hạn hai logging implementations. Trường hợp này không nhất thiết có cùng group:name, nên không dùng mặc định highest version của một module để “giải quyết”.

Ví dụ minh họa rule chọn capability:

~~~groovy
configurations.configureEach {
    resolutionStrategy.capabilitiesResolution
        .withCapability('com.example:logging') {
            selectHighestVersion()
        }
}
~~~

Đây chỉ là **ví dụ API** cần có các components thật sự khai báo capability **com.example:logging**. Không nên thêm nó vào lab nếu chưa có metadata capability phù hợp. Trong thực tế, chọn một implementation logging thường cần xem semantics và dependency metadata, không mặc định version cao hơn luôn an toàn.

**Variant conflict** có thể liên quan attributes như Java API/runtime, target JVM version, platform, capabilities. Gradle phân giải **component/variant** chứ không chỉ chọn JAR theo tên file. Khi lỗi cho thấy **No matching variant**, kiểm tra attributes/JDK/plugin trước, đừng giải thích mọi lỗi resolve bằng version conflict.

## 15. Chẩn đoán lỗi: loại nào, tại đâu, nguyên nhân gì?

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **1.0 -> 2.0** trong dependency tree | Conflict của cùng module; rule mặc định chọn 2.0 | Dùng dependencyInsight xác định nhánh yêu cầu 2.0 |
| Version khai báo trực tiếp 1.0 nhưng runtime là 2.0 | Direct version thông thường là require, không phải pin | Kiểm tra yêu cầu transitive; dùng constraint khi có policy |
| **failOnVersionConflict** làm build hỏng | Có ít nhất hai version requirements khác nhau | Quyết định version policy và sửa graph, đừng tắt kiểm tra nếu team cần nó |
| **strictly('1.0')** gây không resolve | Nhánh khác require ít nhất 2.0 | Nâng cấp code/nhánh, đổi constraint hợp lý, không ép chạy không tương thích |
| Lockfile 1.0, dependency mới require 2.0 | Lock strict cũ không còn tương thích | Update locks qua quy trình review |
| **Force** giúp resolve nhưng app báo NoSuchMethodError | Downgrade phá API mà thư viện khác cần | Chọn version tương thích, test integration, bỏ force sai |
| Bản được chọn có qualifier bất ngờ | Gradle version ordering/status và version ranges | Kiểm tra metadata, dependencyInsight, chính sách version |
| **Could not find demo:engine:2.0** | Repository không có metadata/artifact version được chọn | Kiểm tra source repository và publication; đừng tự coi là conflict selection lỗi |
| Report compile và runtime khác nhau | Configuration scopes có dependency graph khác | Chạy report trên đúng compileClasspath/runtimeClasspath |
| Test chạy nhưng app production lỗi | testRuntimeClasspath khác runtimeClasspath | So sánh graphs, bổ sung runtime/integration tests |
| **enforcedPlatform** override version | BOM constraints bị enforce | Xem BOM version, selection reasons, cân nhắc regular platform |
| Version catalog ghi 1.0 nhưng resolved 2.0 | Catalog chỉ là alias/notation | Xem constraints/platform/graph, không coi catalog là pin |
| Hai module khác GAV có cùng class | Không phải version conflict cùng module; shading/duplicate classes | Kiểm tra dependency contents/capabilities, chọn implementation đúng |
| Dynamic **1.+** đổi kết quả | Repository có version mới, TTL/cache thay đổi | Dùng fixed version, locking, có policy update |
| Dependency bị loại bằng exclude nhưng runtime lỗi | Đã xóa transitive module vẫn cần | Khôi phục dependency, sửa constraint/version thay vì exclude mù |
| **No matching variant** | Metadata/attributes/JVM compatibility không phù hợp | Xem variant selection; không quy mọi lỗi về version max |
| **dependencyInsight** không thấy module | Sai project/configuration hoặc module không trong graph | Chọn đúng **:module**, configuration và dependency pattern |

### 15.1. Quy trình debug 8 bước

1. **Ghi lại module group:name** thực sự có vấn đề, không chỉ tên class báo lỗi.
2. **Chọn đúng project và configuration**: **:app:runtimeClasspath** cho runtime của app, hoặc compile/test tương ứng.
3. **Chạy dependencies** để xem nhánh nào yêu cầu những version khác nhau.
4. **Chạy dependencyInsight** cho đúng group:name để thấy **selection reasons**.
5. **Tìm policy đã áp dụng**: constraint, strict, forced, rule, platform/BOM, lockfile.
6. **Phân biệt version selection với missing metadata/artifact**, capability/variant conflicts.
7. **Đề xuất thay đổi nhỏ, có nguyên nhân**: cập nhật module nguồn, constraint phù hợp, BOM, hoặc code tương thích.
8. **Kiểm chứng lại** bằng dependencyInsight, Java compile/tests, integration/runtime tests và lock/verification metadata nếu có.

## 16. Một số trường hợp lựa chọn nhanh

### Trường hợp A — Version mới hơn có bản vá và tương thích

Giả sử **client-a** yêu cầu engine 1.0 nhưng app cần 2.0 để có bản vá. Nếu 2.0 đã được kiểm thử, có thể dùng **constraint require 2.0** hoặc nâng dependency trực tiếp liên quan. **Không cần force** nếu graph đã chọn 2.0 và policy cho phép.

### Trường hợp B — Không thể dùng version 2.0 do API breaking

Dùng **strictly** hoặc strict range để diễn đạt giới hạn, nhưng phải chấp nhận build **báo lỗi** nếu một dependency khác thực sự yêu cầu tối thiểu 2.0. Cách giải quyết bền vững có thể là **đổi client-b sang version tương thích**, refactor code, hoặc dùng implementation thay thế; không phải chỉ hạ engine mà bỏ qua yêu cầu.

### Trường hợp C — Hai module khác nhau cùng cung cấp logging implementation

Đây là capability/duplicate implementation issue. Cần xác định nguồn nào cần giữ, dùng capabilities hoặc exclude đúng scope. **“Chọn max version của module” không giải quyết được hai module group:name khác nhau**.

### Trường hợp D — Một nhóm thư viện phải dùng version đồng bộ

Dùng **platform/BOM** để phối hợp constraints và quản lý tập module. Trong application, khi cần exact set đã test có thể cân nhắc **enforcedPlatform**; trong library xuất bản cho bên ngoài, cẩn trọng với strict constraints lan truyền.

### Trường hợp E — CI cần tái lập kết quả giống nhau

Dùng **dependency locking** cho version selection, verification cho artifact bytes và chính sách repositories. **--refresh-dependencies** không phải cơ chế cố định version; nó chỉ yêu cầu tái kiểm tra resolution khi phù hợp.

## 17. Bài tập tự kiểm tra có đáp án

### Bài 1 — Xác định version conflict

~~~text
:app
├── demo:alpha:1.0 -> demo:engine:1.0
└── demo:beta:1.0  -> demo:engine:2.0
~~~

Hỏi: theo mặc định, engine version nào được chọn?

**Đáp án:** **2.0**, khi cả hai version hợp lệ và không có rules/constraints loại nó. Số lần yêu cầu hay thứ tự các nhánh không làm 1.0 thắng.

### Bài 2 — Direct dependency có ghim version không?

~~~groovy
dependencies {
    implementation 'demo:engine:1.0'
    implementation 'demo:client-b:1.0'
}
~~~

Client-b yêu cầu engine 2.0. Hỏi: engine version nào thường được chọn?

**Đáp án:** **2.0**. Direct **1.0** là một version requirement thông thường, có thể được nâng do conflict resolution.

### Bài 3 — Khi nào failOnVersionConflict có ích?

Nếu team muốn mọi trường hợp hai version requirements khác nhau phải được xem xét thủ công, bật **resolutionStrategy.failOnVersionConflict()** ở những configurations mục tiêu. **Đáp án:** Gradle sẽ không im lặng chọn max cho conflict này, mà báo lỗi để người phụ trách chỉnh graph/policy.

### Bài 4 — Constraint có tự thêm engine?

~~~groovy
dependencies {
    constraints {
        implementation('demo:engine:2.0')
    }
}
~~~

Không có dependency nào khác yêu cầu engine. **Đáp án:** constraint không tự thêm engine vào graph. Nó chỉ tác động khi engine được kéo vào bằng một dependency thật.

### Bài 5 — strictly 1.0 gặp require 2.0

Constraint **strictly('1.0')**, client-b require **engine:2.0**. **Đáp án:** hai yêu cầu không tương thích; resolution có thể thất bại. Không coi strictly là lệnh “bỏ qua tất cả requirements” một cách an toàn.

### Bài 6 — prefer có ghim version không?

Constraint **prefer('1.0')**, client-b require **2.0**. **Đáp án:** không. Prefer mềm, không tự cấm chọn 2.0.

### Bài 7 — Xung đột phiên bản hay capability?

**logger-a:1.0** và **logger-b:2.0** cùng thực thi một API logging nhưng khác group:name. **Đáp án:** không phải version conflict thông thường của cùng module; nếu metadata khai báo cùng capability, đây có thể là capability conflict. Cách xử lý phụ thuộc implementation nào thực sự mong muốn.

### Bài 8 — Đọc ký hiệu ->

Report ghi **demo:engine:1.0 -> 2.0**. **Đáp án:** dependency edge yêu cầu engine 1.0, nhưng selected version của module trong configuration là 2.0. **Không phải hai version đã được tải như hai phần độc lập trong graph đó.**

### Bài 9 — Why not exclude?

App cần engine qua client-b. Một người định exclude engine khỏi client-b để chỉ còn 1.0. **Đáp án:** phải xác minh client-b có thể chạy thiếu engine hay không. Exclude loại edge, không áp version policy, nên có thể gây lỗi runtime. Thường nên xem constraint/version compatibility trước.

### Bài 10 — Tại sao compile và test có thể khác?

**testImplementation** có thêm một thư viện yêu cầu engine 3.0. **Đáp án:** testRuntimeClasspath có graph khác runtimeClasspath của production, nên version đã chọn có thể khác. Cần chạy dependencyInsight trên cả hai configuration.

## Tài liệu chính thức

- [Gradle — Dependency Constraints and Conflict Resolution](https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html): hai loại conflicts và lựa chọn version mặc định.
- [Gradle — Graph Resolution](https://docs.gradle.org/current/userguide/graph_resolution.html): version conflict, candidate ordering, metadata và rich versions.
- [Gradle — Declaring Dependency Versions](https://docs.gradle.org/current/userguide/dependency_versions.html): version ordering, rich versions, **require/strictly/prefer/reject**, dynamic/changing.
- [Gradle — Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html): constraints và precedence trong transitive graph.
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): **dependencies**, **dependencyInsight**, selection reasons.
- [Gradle — ResolutionStrategy Javadoc](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/ResolutionStrategy.html): **failOnVersionConflict**, **force**, rules.
- [Gradle — Platforms/BOM](https://docs.gradle.org/current/userguide/platforms.html): regular/enforced platform, phối hợp versions.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): khóa phiên bản đã resolved.
- [Gradle — Excluding Transitive Dependencies](https://docs.gradle.org/current/userguide/how_to_exclude_transitive_dependencies.html): cách exclude an toàn và rủi ro.

**Tổng kết:** Xung đột phiên bản xảy ra khi **cùng một module group:name được yêu cầu bởi nhiều version** trong một graph. **Mặc định Gradle chọn version cao nhất phù hợp**, không thiên vị declaration trực tiếp hay dòng khai báo trước. Muốn thay đổi kết quả, phải hiểu toàn graph và sử dụng **constraint/rich versions/platform/rule** phù hợp, rồi xác minh bằng **dependencyInsight** và tests. **Một graph phân giải thành công chưa tự chứng minh các thư viện tương thích nhị phân hoặc an toàn khi chạy.**