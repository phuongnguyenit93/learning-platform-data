# Component metadata rules để sửa metadata thiếu hoặc sai trong Gradle

## Mục tiêu bài học

Khi dùng một dependency bên ngoài, Gradle không chỉ tải file JAR. Gradle còn đọc **metadata** để biết module ấy là gì, phụ thuộc module nào, cung cấp những **variant** nào và có thuộc tính hay **capability** gì. Nếu thư viện được publish với POM/Ivy/Gradle Module Metadata thiếu hoặc sai, graph có thể thiếu thư viện cần ở runtime, kéo theo thư viện thừa, chọn variant không đúng JDK hoặc cho phép hai implementation xung đột.

**Component metadata rules** là cơ chế sửa hay bổ sung thông tin của **module được lấy từ repository**, trước khi Gradle sử dụng thông tin ấy để phân giải dependencies. Cơ chế này cho phép khắc phục những publication chưa chính xác **trong phạm vi build đang sử dụng chúng**, mà không phải chỉnh sửa file POM trên Maven Central hay thay JAR đã phát hành.

Sau bài này bạn có thể:

1. Nhận diện vấn đề nào xuất phát từ **metadata sai/thiếu**, vấn đề nào không.
2. Hiểu thời điểm áp dụng và phạm vi **ComponentMetadataRule**, **ComponentMetadataContext**, **ComponentMetadataDetails**.
3. Phân biệt **components.withModule(group:name, rule)** với **components.all(rule)** và hai cách viết rule **inline** / **class riêng**.
4. Sửa dependency bắc cầu bị thiếu, thừa hoặc yêu cầu version không đúng bằng **withDependencies**, **add**, **removeAll** và **version**.
5. Đặt rule đúng **variant** bằng **withVariant(name)** hoặc **allVariants**, tránh làm sai API/runtime classpath.
6. Hiểu mức nâng cao: **withCapabilities**, **withDependencyConstraints**, **attributes**, **addVariant**, **withFiles**, **belongsTo**, **status/statusScheme**.
7. Tạo một ví dụ **Java 17 + Maven repository cục bộ** để thấy lỗi runtime khi POM thiếu dependency và cách rule sửa nó.
8. Đánh giá tính **đúng đắn, cô lập, cacheability**, khả năng test và cách chia sẻ rule cho nhiều module.
9. Biết khi nào nên sửa upstream publication, dùng **dependency constraints**, **dependency substitution** hoặc **artifact transform** thay cho metadata rule.

Bài dùng chủ yếu **Groovy DSL (build.gradle)**, có phần đối chiếu **Kotlin DSL**. Những tọa độ **demo:** và **org.example:** là dữ liệu minh họa, không phải thư viện cần tải từ Internet.

## 1. Metadata của một component là gì?

Một dependency Maven có dạng:

~~~text
group:name:version
demo:legacy-client:1.0
~~~

Thông tin Gradle cần khi resolution có thể gồm:

| Thành phần | Ví dụ | Tác động |
| --- | --- | --- |
| Định danh component | **demo:legacy-client:1.0** | Biết module đang nói tới |
| Dependency edges | **demo:helper:1.0** | Kéo các dependencies bắc cầu vào graph |
| Variants | **compile**, **runtime**, **apiElements**, **runtimeElements** | Chọn artifact/dependencies phù hợp cho consumer |
| Attributes | **org.gradle.usage**, **org.gradle.jvm.version** | Chọn variant theo nhu cầu API/runtime, JDK |
| Capabilities | **demo:logging-implementation** | Phát hiện hai module cung cấp cùng chức năng |
| Dependency constraints | Version range/strict constraint | Hạn chế version của module khác |
| Artifacts | **legacy-client-1.0.jar**, JAR có classifier | Biết file nào thuộc variant được chọn |
| Component status | **integration**, **milestone**, **release** | Tham gia lựa chọn theo trạng thái, đặc biệt dynamic/latest selector |

Maven POM thường có **groupId, artifactId, version, dependencies, packaging**. Nó không diễn đạt phong phú variants/capabilities như Gradle Module Metadata. Ivy descriptor lại có **configurations** và những quy tắc mapping riêng. Gradle phải chuyển đổi các format ấy thành mô hình có variants trước khi giải graph.

### 1.1. Ba format thường gặp

- **Gradle Module Metadata (.module)**: biểu diễn variants, attributes, dependencies và constraints chi tiết; thường đầy đủ hơn.
- **Maven POM (.pom)**: mô tả module/dependencies theo mô hình Maven; Gradle tự **suy diễn variants** khi đọc POM.
- **Ivy descriptor (ivy.xml)**: cung cấp configurations và dependencies theo Ivy; các đặc điểm mapping khác Maven POM.

**Không đoán tên variant từ tên task hoặc file JAR.** Với một module chỉ có POM, Gradle có những variant dẫn xuất tên **compile** và **runtime** (cùng các dạng liên quan); với module publish Gradle Module Metadata, tên có thể là **apiElements**, **runtimeElements** hay custom names. Rule cần chọn variant **thật sự có trong metadata đang được dùng**.

### 1.2. Ví dụ metadata sai gây hậu quả

Giả sử class **demo.LegacyClient** gọi **demo.Helper** ở runtime. Nhưng POM của **demo:legacy-client:1.0** không khai báo phụ thuộc **demo:helper:1.0**.

Graph Gradle nhìn thấy:

~~~text
:app
└── demo:legacy-client:1.0
~~~

Graph đúng mà thư viện cần:

~~~text
:app
└── demo:legacy-client:1.0
    └── demo:helper:1.0
~~~

Nếu chỉ dựa vào POM sai, chương trình có thể biên dịch nhưng lỗi:

~~~text
java.lang.NoClassDefFoundError: demo/Helper
~~~

**Metadata rule** có thể bổ sung dependency edge còn thiếu vào runtime variant. Nó **không** tự tạo class **demo.Helper**, không biên dịch lại JAR, và không sửa POM gốc trong repository.

## 2. Vị trí của ComponentMetadataRule trong quá trình resolution

Mô hình:

~~~text
Project yêu cầu module (group:name:version)
                |
                v
Gradle tra cứu repository, lấy metadata
                |
                v
Gradle parse .module / .pom / ivy.xml
                |
                v
Áp dụng Component Metadata Rules phù hợp
                |
                v
Xây dựng graph: dependencies, constraints
                |
                v
Chọn phiên bản / variant / capability hợp lệ
                |
                v
Tải artifacts được chọn và dùng cho task
~~~

Điểm quan trọng:

- Rule được áp dụng **sau khi metadata component được tải/đọc**, nhưng **trước khi thông tin đó được dùng** để giải dependencies.
- Rule không trực tiếp ghi đè nội dung POM/Ivy trên server. Nó tạo một **góc nhìn metadata đã được điều chỉnh** trong build đang resolve module.
- Rule phải được đăng ký **trước khi configuration liên quan bị phân giải**. Đăng ký rule sau khi classpath đã được resolve là quá muộn.
- Rule được Gradle áp dụng trên **component metadata**, khác với một **task action** chạy khi build thực thi.
- Mỗi configuration có graph và nhu cầu variant khác nhau; sửa **runtime** không mặc nhiên đồng nghĩa sửa **compile**.
- Rules không tự áp dụng cho **mọi project/build trên máy**. Muốn chia sẻ, cần cấu hình rule trong các project phù hợp, convention plugin, hoặc settings theo hỗ trợ/version cụ thể.
- Gradle có thể **cache kết quả rule** và không gọi lại rule trong mỗi invocation. Không dùng side effects của rule làm một bước build.

## 3. Hai cách đăng ký rule: inline và class

### 3.1. Dùng inline action để thử một chỉnh sửa nhỏ

Trong một project có Gradle Groovy DSL:

~~~groovy
dependencies {
    components {
        withModule('demo:legacy-client') {
            if (id.version == '1.0') {
                withVariant('runtime') {
                    withDependencies {
                        add('demo:helper:1.0')
                    }
                }
            }
        }
    }

    implementation 'demo:legacy-client:1.0'
}
~~~

Nhận xét:

1. **components { ... }** là block cấu hình component metadata rules nằm trong **dependencies**.
2. **withModule('demo:legacy-client')** chỉ chọn group **demo**, name **legacy-client**, bất kể version; vì vậy code tự kiểm tra **id.version == '1.0'** nếu chỉ muốn vá bản lỗi 1.0.
3. **withVariant('runtime')** tác động tới variant runtime của metadata dạng Maven POM được Gradle suy diễn.
4. **withDependencies { add('demo:helper:1.0') }** bổ sung dependency bị thiếu vào metadata của variant đó.
5. **implementation 'demo:legacy-client:1.0'** là dòng khai báo dependency thật của project; metadata rule **không thay thế** declaration này.

Ưu điểm inline: dễ thử, không cần thêm class. Nhược điểm: khó quản lý khi nhiều rule, có thể kém cache-friendly và khó reuse/test. Với một workaround tồn tại lâu, nên dùng class rule tách biệt và **@CacheableRule**.

### 3.2. ComponentMetadataRule dạng class riêng

~~~groovy
import org.gradle.api.artifacts.CacheableRule
import org.gradle.api.artifacts.ComponentMetadataContext
import org.gradle.api.artifacts.ComponentMetadataRule

@CacheableRule
abstract class FixLegacyClientMetadata implements ComponentMetadataRule {
    void execute(ComponentMetadataContext context) {
        if (context.details.id.version != '1.0') {
            return
        }

        context.details.withVariant('runtime') {
            withDependencies {
                add('demo:helper:1.0')
            }
        }
    }
}
~~~

Đây là **định nghĩa class Groovy** có thể đặt trong **build.gradle** (ở vị trí hợp lệ sau **plugins** nếu script có plugins DSL), hoặc tổ chức trong plugin code. **ComponentMetadataRule** yêu cầu implement phương thức **execute(ComponentMetadataContext)**. Từ context truy cập **details** để điều chỉnh metadata.

Đăng ký class:

~~~groovy
dependencies {
    components {
        withModule('demo:legacy-client', FixLegacyClientMetadata)
    }
    implementation 'demo:legacy-client:1.0'
}
~~~

**@CacheableRule** là **org.gradle.api.artifacts.CacheableRule**, không phải **@CacheableTask**. Nó thông báo rule đủ điều kiện để Gradle cache **kết quả biến đổi metadata**, không phải cache đầu ra một task JavaCompile.

### 3.3. withModule và all

| API | Phạm vi | Nên dùng |
| --- | --- | --- |
| **withModule('group:name', RuleClass)** | Một module group/name, các versions phù hợp | Mặc định khi biết publication nào sai |
| **withModule('group:name') { ... }** | Một module, inline action | Khảo sát hoặc workaround nhỏ |
| **all(RuleClass)** | Nhiều modules được resolution xét | Chỉ khi policy thực sự phổ quát |
| **all { ... }** | Rule inline chung | Cân nhắc hiệu suất và phạm vi |

Thông thường **withModule** an toàn hơn **all** vì metadata sai thường thuộc một module hoặc dải version nhỏ. Nếu đăng ký class cho toàn bộ modules, cần kiểm tra **context.details.id.group**, **name**, **version** cẩn thận và không làm biến đổi những publication lành mạnh.

## 4. API quan trọng trong metadata rule

**context.details** là **ComponentMetadataDetails**. Những điểm truy cập thường gặp:

~~~groovy
void execute(ComponentMetadataContext context) {
    def details = context.details

    def group = details.id.group
    def name = details.id.name
    def version = details.id.version

    details.withVariant('runtime') {
        // Đổi thông tin của một variant cụ thể
    }
}
~~~

**id.group/name/version** là thông tin nhận dạng của component đang được xử lý. Không nên cố sửa group/name/version tùy ý để “chuyển” module sang module khác; muốn thay dependency selector hãy xem **dependency substitution** hoặc sửa declaration.

| API | Tác dụng | Lưu ý |
| --- | --- | --- |
| **withVariant(name) { ... }** | Chỉnh một variant cụ thể | Chỉ hiệu quả nếu variant tồn tại |
| **allVariants { ... }** | Chỉnh mọi variant hiện có | Có thể ảnh hưởng cả compile/runtime và variant khác |
| **addVariant(name, base) { ... }** | Tạo variant từ một variant/configuration hiện có | Cần mô tả attributes, capabilities, files phù hợp |
| **withDependencies { ... }** | Thêm/xóa/sửa dependency edges của variant | Dependency graph thay đổi |
| **withDependencyConstraints { ... }** | Thêm/xóa/sửa constraints của variant | Constraint không tự thêm module |
| **withCapabilities { ... }** | Thêm/bớt capability của variant | Có thể kích hoạt capability conflict |
| **attributes { ... }** | Sửa đặc tính chọn variant | Dùng attribute type đúng |
| **withFiles { ... }** | Mô tả artifact files của variant | Không tự tạo file trên repository |
| **belongsTo(...)** | Liên kết component với platform, thường virtual platform | Dùng cho alignment khi metadata thiếu |
| **status/statusScheme** | Điều chỉnh trạng thái version | Ảnh hưởng lựa chọn latest/status |
| **changing** | Điều chỉnh tính chất module thay đổi theo thời gian | Ảnh hưởng chính sách cache |

Phân biệt **metadata rule** với **resolutionStrategy.eachDependency**: cái đầu làm giàu/sửa mô tả module được tải, cái sau can thiệp vào cách chọn dependency từ yêu cầu. Sửa POM sai thường hợp với **metadata rule**, còn thay module yêu cầu theo policy build có thể hợp với constraint/substitution/rule khác.

## 5. Lab chạy được: POM thiếu dependency runtime

Mục tiêu: chứng minh thật rằng khi POM **legacy-client:1.0** bỏ sót **helper:1.0**, ứng dụng có thể **NoClassDefFoundError**, còn metadata rule đúng sẽ thêm helper vào **runtimeClasspath**.

Lab này sử dụng **Java 17+** và một **Maven repository trên ổ đĩa**. Không cần tải dependencies từ Maven Central. Bạn cần Gradle Wrapper hợp lệ và JDK 17; việc tải distribution/toolchain khi môi trường chưa chuẩn bị vẫn là vấn đề riêng.

### 5.1. Cây dự án

~~~text
component-metadata-lab/
├── settings.gradle
├── build.gradle
├── FixtureGenerator.java
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── src/main/java/demo/App.java
└── lab-repo/                          # tạo bởi FixtureGenerator
    └── demo/
        ├── helper/1.0/
        │   ├── helper-1.0.pom
        │   └── helper-1.0.jar
        └── legacy-client/1.0/
            ├── legacy-client-1.0.pom  # cố tình thiếu dependency
            └── legacy-client-1.0.jar
~~~

**gradlew** và thư mục **gradle/wrapper** phải lấy từ project đã setup Wrapper hoặc được Gradle tạo, không tự tạo JAR Wrapper bằng tay.

### 5.2. settings.gradle

~~~groovy
rootProject.name = 'component-metadata-lab'
~~~

### 5.3. Chương trình Java tạo hai artifact Maven cục bộ

Tạo file **FixtureGenerator.java** tại root. Chương trình dùng **JavaCompiler** thuộc JDK để biên dịch class, **JarOutputStream** để đóng gói và **Files.writeString** để tạo hai POM. POM của legacy-client cố tình không có phần **dependencies**.

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
            throw new IllegalStateException("Requires JDK 17+, not a JRE");
        }

        Path helperSource = Path.of(
                "lab-work", "helper", "src", "demo", "Helper.java"
        );
        Path clientSource = Path.of(
                "lab-work", "client", "src", "demo", "LegacyClient.java"
        );
        Path helperClasses = Path.of("lab-work", "helper", "classes");
        Path clientClasses = Path.of("lab-work", "client", "classes");

        Files.createDirectories(helperSource.getParent());
        Files.createDirectories(clientSource.getParent());
        Files.createDirectories(helperClasses);
        Files.createDirectories(clientClasses);

        Files.writeString(helperSource, """
                package demo;
                public final class Helper {
                    public static String value() {
                        return "helper ready";
                    }
                }
                """, StandardCharsets.UTF_8);

        Files.writeString(clientSource, """
                package demo;
                public final class LegacyClient {
                    public static String message() {
                        return "Client: " + Helper.value();
                    }
                }
                """, StandardCharsets.UTF_8);

        compile(
                compiler,
                "--release", "17",
                "-d", helperClasses.toString(),
                helperSource.toString()
        );

        compile(
                compiler,
                "--release", "17",
                "-classpath", helperClasses.toString(),
                "-d", clientClasses.toString(),
                clientSource.toString()
        );

        writeModule(
                "helper",
                helperClasses.resolve("demo/Helper.class"),
                "demo/Helper.class"
        );
        writeModule(
                "legacy-client",
                clientClasses.resolve("demo/LegacyClient.class"),
                "demo/LegacyClient.class"
        );

        System.out.println("Created two Maven fixtures.");
    }

    private static void compile(
            JavaCompiler compiler, String... args
    ) throws IOException {
        int code = compiler.run(null, null, null, args);
        if (code != 0) {
            throw new IOException("javac failed with code " + code);
        }
    }

    private static void writeModule(
            String name, Path classFile, String entryName
    ) throws IOException {
        Path module = Path.of("lab-repo", "demo", name, "1.0");
        Files.createDirectories(module);

        String pom = """
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <modelVersion>4.0.0</modelVersion>
                  <groupId>demo</groupId>
                  <artifactId>%s</artifactId>
                  <version>1.0</version>
                  <packaging>jar</packaging>
                </project>
                """.formatted(name);
        Files.writeString(
                module.resolve(name + "-1.0.pom"),
                pom,
                StandardCharsets.UTF_8
        );

        try (JarOutputStream jar = new JarOutputStream(
                Files.newOutputStream(
                        module.resolve(name + "-1.0.jar")
                ))) {
            jar.putNextEntry(new JarEntry(entryName));
            Files.copy(classFile, jar);
            jar.closeEntry();
        }
    }
}
~~~

**Kiểm tra logic của generator:**

- Compile Helper trước nên **Helper.class** tồn tại.
- Compile LegacyClient với classpath là helperClasses nên lời gọi **Helper.value()** hợp lệ.
- JAR **legacy-client** chỉ chứa **LegacyClient.class**, **không có Helper.class** bên trong.
- POM legacy-client vẫn chỉ có groupId/artifactId/version/packaging. Nó **cố tình không khai báo dependency helper**, chính là lỗi metadata ta muốn sửa.
- Source Java dùng **text block** và **String.formatted(...)**, hợp lệ với Java 17.

Chạy ở root:

~~~bash
javac FixtureGenerator.java
java FixtureGenerator
~~~

Dòng stdout khi thành công:

~~~text
Created two Maven fixtures.
~~~

Hãy kiểm tra **lab-repo/demo/helper/1.0** và **lab-repo/demo/legacy-client/1.0** trước khi chạy Gradle. Không thay đổi POM trong nửa đầu bài, vì cần quan sát hành vi khi metadata sai.

### 5.4. App.java gọi LegacyClient

Tạo **src/main/java/demo/App.java**:

~~~java
package demo;

public final class App {
    public static void main(String[] args) {
        System.out.println(LegacyClient.message());
    }
}
~~~

App tham chiếu **LegacyClient** từ dependency trực tiếp. **LegacyClient.message()** có signature trả **String**; lúc chạy phương thức mới thực hiện code truy cập Helper.

### 5.5. build.gradle trước khi sửa metadata

~~~groovy
plugins {
    id 'application'
}

repositories {
    maven {
        name = 'localFixture'
        url = uri('lab-repo')
    }
}

dependencies {
    implementation 'demo:legacy-client:1.0'
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

Gradle chỉ biết dependency **demo:legacy-client:1.0** vì POM không nói rằng module này cần **demo:helper:1.0**.

Lệnh Linux/macOS:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat run
~~~

Trong report dependencies, graph thường chỉ có **legacy-client:1.0** ở phần external modules. Ở runtime, phần lỗi chính dự kiến:

~~~text
Exception in thread "main" java.lang.NoClassDefFoundError: demo/Helper
~~~

Gradle có thể báo thêm **Execution failed for task ':run'**, exit code và stack trace. Vì thế đoạn trên là **dòng lỗi cốt lõi**, không phải transcript đầy đủ cho mọi hệ điều hành/Gradle version.

**Tại sao App có thể biên dịch?** App chỉ gọi method **LegacyClient.message()** có signature trả String; compile không yêu cầu class **Helper** được đặt trực tiếp trên compile classpath của App. Nhưng khi code của LegacyClient chạy và nạp Helper, helper JAR thiếu gây **NoClassDefFoundError**.

### 5.6. build.gradle sau khi bổ sung ComponentMetadataRule

**Thay toàn bộ build.gradle ở mục 5.5** bằng nội dung sau. Không cần chỉnh file JAR hoặc POM trong **lab-repo**.

~~~groovy
import org.gradle.api.artifacts.CacheableRule
import org.gradle.api.artifacts.ComponentMetadataContext
import org.gradle.api.artifacts.ComponentMetadataRule

plugins {
    id 'application'
}

@CacheableRule
abstract class FixLegacyClientRuntime implements ComponentMetadataRule {
    void execute(ComponentMetadataContext context) {
        if (context.details.id.version != '1.0') {
            return
        }
        context.details.withVariant('runtime') {
            withDependencies {
                add('demo:helper:1.0')
            }
        }
    }
}

repositories {
    maven {
        name = 'localFixture'
        url = uri('lab-repo')
    }
}

dependencies {
    components {
        withModule('demo:legacy-client', FixLegacyClientRuntime)
    }
    implementation 'demo:legacy-client:1.0'
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

Ý nghĩa từng phần:

1. **FixLegacyClientRuntime** là một lớp rule, không phải một task, không có method **@TaskAction**.
2. **execute** chỉ xử lý version **1.0**; những versions khác của cùng module không bị thêm dependency giả.
3. **withVariant('runtime')** chọn variant runtime được Gradle suy diễn từ Maven POM.
4. **withDependencies { add(...) }** chèn dependency **demo:helper:1.0** vào metadata của variant ấy.
5. **components.withModule('demo:legacy-client', FixLegacyClientRuntime)** đăng ký rule trước khi runtimeClasspath resolve.
6. **@CacheableRule** cho phép Gradle cache kết quả rule nếu đáp ứng các yêu cầu về sự cô lập/đầu vào.
7. **implementation 'demo:legacy-client:1.0'** vẫn là dependency của App; rule chỉ sửa metadata module đó.

### 5.7. Chạy lại và xác minh

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency demo:helper
./gradlew run
~~~

PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --configuration runtimeClasspath --dependency demo:helper
.\gradlew.bat run
~~~

Graph có ý nghĩa:

~~~text
runtimeClasspath
\--- demo:legacy-client:1.0
     \--- demo:helper:1.0
~~~

Phần stdout do App in:

~~~text
Client: helper ready
~~~

Đây là kết quả mong đợi khi hai fixtures được tạo đúng bằng generator, Gradle đọc đúng local repo và không có rule khác can thiệp. Trạng thái task/log của Gradle có thể khác, nhưng **helper đã được đưa vào runtimeClasspath** là tín hiệu quan trọng nhất.

### 5.8. Vì sao chỉ sửa runtime variant?

Lỗi trong lab là **thiếu helper lúc thực thi**. App không gọi trực tiếp Helper nên compileClasspath không nhất thiết cần nó. Với module công bố qua Maven POM, Gradle suy diễn compile/runtime variants. Vì thế chỉ sửa **runtime** diễn đạt đúng nhu cầu.

Nếu API public của **LegacyClient** có method:

~~~java
public static Helper createHelper() { ... }
~~~

thì App muốn biên dịch dựa vào chữ ký **Helper** cũng phải có Helper trên **compileClasspath**. Khi đó cần kiểm tra metadata và sửa những variants phù hợp, có thể dùng **allVariants** hoặc **withVariant('compile')** cùng **withVariant('runtime')** cho POM metadata. **Không tự động add helper vào mọi variant nếu đó chỉ là runtime-only dependency.**

### 5.9. Cách nhận diện rule đã sửa metadata chứ không “giấu lỗi”

- **POM trên ổ đĩa không đổi**: legacy-client POM vẫn không có dependencies.
- **Gradle graph đổi**: runtimeClasspath có helper khi rule được đăng ký.
- **Chương trình chạy được**: class được đặt đúng vào runtime classpath.
- **Rule có scope giới hạn**: chỉ module **demo:legacy-client** và version **1.0**.
- **Không thêm direct helper dependency vào App**: App chỉ phụ thuộc client; vì vậy lab minh họa đúng giá trị của metadata rule.

## 6. Sửa dependencies thiếu, thừa và sai version

### 6.1. Thêm dependency bị bỏ sót

Đây là công thức từ lab:

~~~groovy
context.details.withVariant('runtime') {
    withDependencies {
        add('demo:helper:1.0')
    }
}
~~~

**add('group:name:version')** sửa metadata của **variant cụ thể**. Trong đời thực, cần xác minh tọa độ và version helper từ upstream release notes, mã nguồn hoặc publication chuẩn. Một dependency thêm sai có thể tạo conflict hoặc kéo mã không tin cậy vào graph.

### 6.2. Xóa dependency thừa do POM lỗi

Ví dụ module **org.example:parser:1.4** có metadata khai báo **org.example:old-xml:1.0** dù chức năng đó đã bị loại. Rule minh họa:

~~~groovy
import org.gradle.api.artifacts.CacheableRule
import org.gradle.api.artifacts.ComponentMetadataContext
import org.gradle.api.artifacts.ComponentMetadataRule

@CacheableRule
abstract class RemoveStaleDependency implements ComponentMetadataRule {
    void execute(ComponentMetadataContext context) {
        if (context.details.id.version != '1.4') return

        context.details.allVariants {
            withDependencies {
                removeAll { dep ->
                    dep.group == 'org.example' &&
                    dep.name == 'old-xml'
                }
            }
        }
    }
}
~~~

Đăng ký:

~~~groovy
dependencies {
    components {
        withModule('org.example:parser', RemoveStaleDependency)
    }
    implementation 'org.example:parser:1.4'
}
~~~

Đây là đoạn **minh họa rule**; tọa độ giả định, không phải bản vá cho một artifact có thật.

**removeAll** làm thay đổi metadata dependencies của tất cả variants mà rule đi qua. Đừng xóa vì “POM nhìn dài” hoặc vì dependency có CVE mà chưa biết liệu thư viện có cần nó không. Cần kiểm chứng cả compile/runtime/tests.

### 6.3. Thay dependency sai tọa độ

Nếu POM thực sự phụ thuộc module cũ nhưng phải dùng module mới, có thể loại edge sai và thêm edge đúng:

~~~groovy
context.details.withVariant('runtime') {
    withDependencies {
        removeAll { it.group == 'org.example' &&
                    it.name == 'old-adapter' }
        add('org.example:new-adapter:2.0')
    }
}
~~~

Đây là **đoạn code nằm trong execute(context)**, không phải một build.gradle độc lập. Chỉ dùng khi đã xác minh **new-adapter** thay thế tương thích cho **old-adapter**. Nếu thư viện thực sự nhúng tên class của old-adapter, thay module theo suy đoán có thể gây lỗi runtime.

### 6.4. Sửa version yêu cầu sai nhưng giữ dependency edge

API dependency metadata cho phép thay **version constraint** mà không phải xóa rồi thêm edge. Ví dụ code trong **withDependencies**:

~~~groovy
context.details.withVariant('runtime') {
    withDependencies {
        findAll { dep ->
            dep.group == 'org.example' &&
            dep.name == 'support-api'
        }.each { dep ->
            dep.version {
                require('2.1')
            }
            dep.because('Published POM declares an outdated requirement')
        }
    }
}
~~~

**require('2.1')** là yêu cầu version có thể bị nâng trong conflict resolution, **không phải pin tuyệt đối**. Nếu publication thật sự chỉ tương thích 2.1 và không chấp nhận 3.x, xem **strictly(...)** hoặc version range với test tương thích, không mặc định require chặn version cao hơn.

### 6.5. Thêm dependency constraint thay vì dependency bắt buộc

Trong một variant, bạn có thể dùng **withDependencyConstraints**:

~~~groovy
context.details.withVariant('runtime') {
    withDependencyConstraints {
        add('org.example:transport:2.3')
    }
}
~~~

Dependency constraint **không tự đưa transport vào graph**. Nó chỉ góp phần điều chỉnh version **nếu transport đã có trong graph** thông qua một dependency edge. Nếu module thực sự cần transport JAR để chạy, phải thêm nó bằng **withDependencies**, không chỉ bằng constraint.

### 6.6. Lựa chọn allVariants hay withVariant

| Triệu chứng | Vị trí nên cân nhắc |
| --- | --- |
| Thiếu JAR chỉ khi ứng dụng chạy | **withVariant('runtime')** cho POM-derived runtime |
| API public tham chiếu class từ dependency thiếu | **compile** và **runtime** nếu metadata nguồn/usage yêu cầu |
| POM kéo dependency sai trong mọi cấu hình | **allVariants**, nếu đã chứng minh |
| Module xuất bản Gradle Module Metadata | Chọn đúng **apiElements**, **runtimeElements** hoặc tên variant thực |
| Library có custom feature variant | Rule phải tôn trọng feature-specific dependencies, không áp tràn |

**allVariants không phải nút “sửa mọi thứ”**. Với artifact có nhiều feature variants, xóa hoặc thêm dependencies toàn cục có thể đưa dependency không cần thiết vào feature khác hoặc phá mô hình variants của producer.

## 7. Thêm capability để nhận diện hai implementation xung đột

Một metadata lỗi khác: hai JAR độc lập cung cấp **cùng một chức năng**, nhưng không khai báo capability chung. Ví dụ hai logging adapters, cả hai đều có thể được đưa vào graph gây lỗi chọn implementation.

Gradle hỗ trợ **capabilities** ở mức variant. Nếu hai modules có cùng capability, Gradle nhận diện **capability conflict** và có thể yêu cầu bạn chọn một implementation.

Ví dụ class rule:

~~~groovy
import org.gradle.api.artifacts.CacheableRule
import org.gradle.api.artifacts.ComponentMetadataContext
import org.gradle.api.artifacts.ComponentMetadataRule

@CacheableRule
abstract class AddLoggingCapability implements ComponentMetadataRule {
    void execute(ComponentMetadataContext context) {
        context.details.allVariants {
            withCapabilities {
                addCapability(
                    'org.example',
                    'logging-implementation',
                    context.details.id.version
                )
            }
        }
    }
}
~~~

Đăng ký cho hai module **giả định**:

~~~groovy
dependencies {
    components {
        withModule('org.example:log-backend-a', AddLoggingCapability)
        withModule('org.example:log-backend-b', AddLoggingCapability)
    }
}
~~~

Khi cùng xuất hiện trong graph và variants được chọn cùng cung cấp capability **org.example:logging-implementation**, Gradle có thể báo conflict thay vì âm thầm giữ hai implementations.

**Quan trọng:**

- Capability không phải dependency. **addCapability** không tự tải thư viện khác.
- Một variant có thể cung cấp **nhiều capabilities**; rule thêm capability thứ hai, không mặc nhiên bỏ default capability.
- Nếu có conflict, cần chọn implementation đúng bằng dependency design hoặc capability resolution strategy hợp lệ, không nghĩ “version cao nhất luôn tốt nhất”.
- Chỉ tạo capability chung khi hai modules thật sự là **alternatives**; nếu chúng cần tồn tại đồng thời, gán cùng capability sẽ làm mô hình sai.

## 8. Sửa attributes và thêm variants khi publication chưa đủ

### 8.1. Vì sao attributes quan trọng?

Gradle có **variant-aware dependency resolution**. Một module có thể cung cấp API variant, runtime variant, artifact cho Java 8, Java 17, native OS/CPU khác nhau. Consumer có attributes của configuration, Gradle so khớp để chọn variant.

Nếu publication không mô tả đúng **TargetJvmVersion**, Gradle có thể coi artifact không tương thích hoặc chọn artifact sai, dù cùng tọa độ module.

Ví dụ khái niệm chỉnh thuộc tính cho một POM-derived variant:

~~~groovy
import org.gradle.api.attributes.java.TargetJvmVersion

context.details.withVariant('runtime') {
    attributes {
        attribute(TargetJvmVersion.TARGET_JVM_VERSION_ATTRIBUTE, 17)
    }
}
~~~

Đoạn này chỉ là **phần nội dung trong execute(context)**; bạn cần import đúng trong file rule. Nó nói runtime variant này nhắm tới JVM 17. **Không tự đặt 17** chỉ vì project consumer dùng JDK 17: phải dựa trên bytecode/requirements thật của artifact.

### 8.2. addVariant tạo variant bổ sung

Một thư viện có thể publish JAR chính và JAR với classifier **jdk17**, nhưng POM không biểu đạt sự khác nhau như các variants. Bạn có thể dựa trên variant gốc để mô hình hóa JAR chuyên biệt:

~~~groovy
import org.gradle.api.attributes.java.TargetJvmVersion

context.details.addVariant('jdk17Runtime', 'runtime') {
    attributes {
        attribute(TargetJvmVersion.TARGET_JVM_VERSION_ATTRIBUTE, 17)
    }
    withFiles {
        removeAllFiles()
        addFile('legacy-client-1.0-jdk17.jar')
    }
}
~~~

Đây là **mẫu minh họa không độc lập**: nó cần module thực sự publish artifact **legacy-client-1.0-jdk17.jar** và một rule class/registration phù hợp. Đối với variant mới, tài liệu API yêu cầu **cấu hình artifact files tường minh**; đừng chỉ sao chép tên variant rồi kỳ vọng Gradle tự tìm đúng classifier JAR.

Nếu file được publish tại đường dẫn tương đối đặc biệt so với POM, **withFiles { addFile(name, uri) }** cho phép trỏ tới đường dẫn thích hợp. Hãy kiểm tra đường dẫn thực và version, vì metadata rule **không tạo file chưa tồn tại**.

### 8.3. Giới hạn của addVariant

- Variant phải có **attributes/capabilities/dependencies/files** nhất quán với thứ nó đại diện.
- Consumer chỉ chọn variant đúng nếu **attributes matching** có đủ thông tin.
- Với **Gradle Module Metadata**, tên variants là những tên xuất bản thực; với POM, thường bắt đầu từ các variants dẫn xuất.
- Với Ivy, base là **Ivy configuration**, không nhất thiết có attributes như một Gradle variant.
- Rule cần xác định Java target và classifier thực tế; việc đoán từ tên JAR có thể sai.
- Nếu module đã publish .module đầy đủ, chỉ thêm variant khi có lỗi thực sự, tránh biến graph thành mô hình khó hiểu.

### 8.4. Khi nào với POM nên tạo feature variant?

Một dependency Maven optional thường biểu đạt “có tính năng phụ nếu consumer chọn”, nhưng POM không mô tả các **feature variants** theo cách Gradle variant-aware hỗ trợ. Thay vì luôn thêm optional dependency vào runtime chính, có thể mô hình hóa variant có **capability** riêng và dependency riêng để consumer chỉ chọn khi dùng tính năng đó.

Đây là trường hợp nâng cao. Chỉ thực hiện khi xác định rõ:
1. Artifact nào của feature thực sự tồn tại.
2. Feature yêu cầu dependencies nào.
3. Capability nào phải được consumer yêu cầu.
4. Những variants gốc có được giữ nguyên không.
5. Kiểm thử cả consumer chọn feature và consumer không chọn.

Không nên vô điều kiện chuyển mọi dependency Maven optional thành bắt buộc chỉ để “đủ graph”.

## 9. belongsTo để alignment phiên bản khi metadata không có platform

Một nhóm modules như **org.example:core**, **org.example:transport**, **org.example:codec** có thể cần đồng bộ version. Nếu chúng không publish platform/BOM phù hợp, **ComponentMetadataDetails.belongsTo(...)** cho phép Gradle nhận diện cùng một **virtual platform**.

Ví dụ **mẫu rule minh họa**:

~~~groovy
@CacheableRule
abstract class ExampleAlignmentRule implements ComponentMetadataRule {
    void execute(ComponentMetadataContext context) {
        def version = context.details.id.version
        context.details.belongsTo("org.example:virtual-platform:${version}")
    }
}
~~~

Khi áp rule phù hợp cho **các module thuộc cùng hệ sinh thái**, virtual platform giúp Gradle alignment version theo các semantics platform resolution.

**Không coi belongsTo là ép mọi module tồn tại ở tất cả versions**. Nếu core có 2.0 nhưng transport chỉ có 1.0, việc alignment có thể tạo lỗi thiếu version hoặc conflict. Nếu publisher có BOM/platform thật, cân nhắc dùng nó trước; virtual alignment rule là phương án bổ sung cho metadata thiếu.

## 10. status, statusScheme và changing: sửa thông tin của component

Không phải tất cả lỗi metadata đều là thiếu dependency edge. Component còn có **status** và trạng thái **changing**.

### 10.1. Status cho dynamic latest selectors

Các trạng thái mặc định thường xếp theo độ trưởng thành:

~~~text
integration < milestone < release
~~~

Nếu một module bị đánh dấu **release** trong khi thực tế còn là snapshot/integration, các yêu cầu kiểu **latest.release** có thể chọn nó sai. Rule có thể điều chỉnh:

~~~groovy
if (context.details.id.version == '2.0-preview') {
    context.details.status = 'integration'
}
~~~

Có thể dùng **statusScheme** khi producer dùng dải trạng thái riêng:

~~~groovy
context.details.statusScheme = [
    'integration', 'milestone', 'release'
]
~~~

Đây là ví dụ đúng cú pháp Groovy cho list. Đừng tự thay status của những modules khác nhau chỉ theo thói quen; policy metadata phải phù hợp cách thư viện thực sự publish version. Nếu không yêu cầu dynamic/latest selection, sửa status có thể không giúp triệu chứng hiện tại.

### 10.2. Changing module không đồng nghĩa dynamic version

**changing** cho biết cùng tọa độ version có thể thay metadata/artifact theo thời gian. **Dynamic** như **1.+** có nghĩa Gradle phải chọn một version từ nhiều version ứng viên. Hai khái niệm khác nhau.

Rule có thể đánh dấu một module đã biết bị republish cùng version:

~~~groovy
if (context.details.id.version == '1.0-SNAPSHOT') {
    context.details.changing = true
}
~~~

Nhưng khi làm thế, cần hiểu **dependency cache TTL**, khả năng repository phục vụ bytes cũ và rủi ro không tái lập. Tránh coi việc republish cùng version là thiết kế phát hành production an toàn. Khi có thể, publish **immutable versions** mới.

### 10.3. Chỉnh metadata không thay version đã chọn bằng phép thần kỳ

Nếu graph có constraints xung đột hoặc module version không tồn tại, bạn cần kiểm tra **dependency resolution policy**. Metadata rule chỉ làm rõ hoặc thay metadata của **những components được xử lý**; không tự cung cấp artifact mới hay đảm bảo version mới phù hợp.

## 11. Rules theo source format: POM, Ivy, Gradle Module Metadata

| Format | Đặc điểm | Khi sửa nên chú ý |
| --- | --- | --- |
| **Maven POM** | Compile/runtime dependencies và optional mang semantics Maven; Gradle suy diễn variants | Với POM thường dùng **withVariant('compile')**, **withVariant('runtime')** phù hợp |
| **Ivy** | Configurations do publisher định nghĩa; metadata có branch, status | **withVariant(configName)** xử lý cấu hình Ivy; attributes/capabilities trên plain Ivy config có giới hạn |
| **Gradle Module Metadata** | Variants, attributes, capabilities và constraints có thể đã đầy đủ | Chọn đúng variant name; tránh sửa quá rộng |

### 11.1. Đọc descriptor riêng của Maven hoặc Ivy nếu cần

Trong rule bạn có thể truy vấn descriptor nguồn:

~~~groovy
import org.gradle.api.artifacts.maven.PomModuleDescriptor

void execute(ComponentMetadataContext context) {
    def pom = context.getDescriptor(PomModuleDescriptor)
    if (pom != null && pom.packaging == 'war') {
        // Ở đây có thể áp chỉnh sửa phù hợp cho WAR metadata.
    }
}
~~~

**Đây là fragment minh họa**, không chạy độc lập nếu không có class rule. Cần biết rule có đang xử lý Maven POM thật hay không; **getDescriptor** có thể trả null khi metadata không thuộc format được yêu cầu.

Ivy có **IvyModuleDescriptor**, chứa thông tin riêng như branch; không nên giả định những trường này tồn tại với .module hay POM. Với thành phần có Gradle Module Metadata, ưu tiên sử dụng variant metadata đúng nguồn.

### 11.2. Một artifact có thể có cả POM và .module

Trên Maven repository, một module có thể publish cả **POM** và **Gradle Module Metadata**. Gradle có thể dùng .module khi metadata nguồn và repository policy cho phép. Khi đó rule viết cho **variant name 'runtime'** của POM-derived metadata có thể không tác động đúng **runtimeElements** từ .module.

**Cách xác minh:** kiểm tra file metadata đã publish, báo cáo variants/attributes và resolution logs trước khi đặt **withVariant**. Nếu không chắc module dùng variant nào, không viết rule dựa vào suy đoán tên.

## 12. Tính cô lập, @CacheableRule và hiệu năng

### 12.1. Vì sao rule nên cacheable?

Metadata của một module có thể được truy vấn bởi nhiều configurations hoặc nhiều builds. Nếu rule đọc file môi trường, truy cập Project hay làm I/O tùy tiện, kết quả phụ thuộc trạng thái ngoài và khó cache/reproduce.

**@CacheableRule** cho phép Gradle cache kết quả biến đổi metadata nếu rule tuân thủ isolation và đầu vào khai báo phù hợp. Đây là đặc tính của **component metadata rule**, không phải build cache của task action.

Ưu tiên:

- Rule là **class riêng** triển khai ComponentMetadataRule.
- Đầu vào rule chỉ đến từ **context.details**, các tham số hợp lệ và Gradle-injected services được hỗ trợ.
- Hàm execute được thiết kế **deterministic**: cùng metadata/parameters → cùng kết quả.
- Không gọi network, không ghi file, không in thông báo như một cách tạo output.
- Chỉ tác động tới module/version/variant cần thiết.
- Dùng **withModule** thay cho **all** trừ khi policy phổ quát thật.
- Version/GAV vá lỗi được lưu rõ cùng lý do và kiểm thử.

### 12.2. Tham số hóa rule

Một class rule có thể nhận cấu hình, chẳng hạn target JVM version, thông qua **constructor @Inject** và **params(...)** khi đăng ký:

~~~groovy
import javax.inject.Inject
import org.gradle.api.artifacts.CacheableRule
import org.gradle.api.artifacts.ComponentMetadataContext
import org.gradle.api.artifacts.ComponentMetadataRule
import org.gradle.api.attributes.java.TargetJvmVersion

@CacheableRule
abstract class TargetJvmRule implements ComponentMetadataRule {
    final Integer target

    @Inject
    TargetJvmRule(Integer target) {
        this.target = target
    }

    void execute(ComponentMetadataContext context) {
        context.details.withVariant('runtime') {
            attributes {
                attribute(TargetJvmVersion.TARGET_JVM_VERSION_ATTRIBUTE, target)
            }
        }
    }
}
~~~

Đăng ký:

~~~groovy
dependencies {
    components {
        withModule('org.example:legacy-library', TargetJvmRule) {
            params(17)
        }
    }
}
~~~

Đây là **ví dụ cấu trúc rule và tham số**, chỉ có ý nghĩa khi module thật mang JVM target 17 và tên variant phù hợp. Gradle yêu cầu các tham số được cô lập, là Serializable hoặc những kiểu Gradle hỗ trợ. Không truyền object Project, open file handle hay service tùy ý vào constructor.

### 12.3. Không đọc Project trong execute

**Ví dụ xấu (không nên dùng):**

~~~groovy
void execute(ComponentMetadataContext context) {
    def selected = project.findProperty('requiredHelperVersion')
    // Project không phải đầu vào hợp lệ tự do cho rule cô lập.
}
~~~

Đừng dựa vào **project** trong rule như trong task configuration closure. Nếu cần khác biệt giữa hai environments, hãy truyền **tham số được khai báo rõ** và đảm bảo code tuân thủ cacheability/isolation; nếu không cần metadata được vá khác nhau, giữ rule không tham số sẽ dễ tái lập hơn.

### 12.4. Rule có thể được cache, đừng dựa vào số lần gọi

Một số cách debug bằng **println** trong execute khiến bạn tưởng rule “không chạy” khi lần sau không thấy log. Gradle có thể dùng kết quả rule đã cache. Hãy đánh giá **graph cuối cùng** qua dependencies/dependencyInsight và integration test, không coi số lần chạy execute là bằng chứng duy nhất.

## 13. Scope trong multi-project build

### 13.1. Đăng ký ở project tiêu thụ

Khi viết:

~~~groovy
dependencies {
    components {
        withModule('demo:legacy-client', FixLegacyClientRuntime)
    }
}
~~~

rule có hiệu lực trong **phạm vi dependency management của project nơi nó được đăng ký**. Với multi-project, một module con khác không nhất thiết tự nhận rule này nếu không có convention/central registration phù hợp.

### 13.2. Chia sẻ qua convention plugin

Khi nhiều subprojects đều dùng cùng legacy dependency:

1. Đưa class rule vào **build-logic** hoặc **buildSrc** với package rõ.
2. Đưa registration vào một **convention plugin**.
3. Áp dụng plugin đó cho đúng những subprojects cần nó.
4. Dùng functional tests để đảm bảo rule hoạt động trên cả compile/runtime configurations.

Ưu điểm: một bản vá được review, test và cập nhật tập trung; không phải sao chép closure vào nhiều **build.gradle**.

### 13.3. Rule từ settings.gradle

Gradle hiện đại hỗ trợ đăng ký component metadata rules ở **settings.gradle(.kts)** để áp dụng rộng cho build, nhưng tính năng **centralized component metadata rules** trong settings còn được tài liệu Gradle đánh dấu là **incubating**. Khi dùng, kiểm tra version Wrapper và policy của project. Không nhầm với **dependencyResolutionManagement.repositories**, vốn là cơ chế khác để tập trung danh sách kho.

**Không sửa file settings hoặc những subproject ngoài assignment của bài này** chỉ để thử một ví dụ; các đoạn trên mô tả kiến trúc áp dụng sau khi hiểu rule.

## 14. Metadata rule có thể và không thể sửa gì?

| Tình huống | Metadata rule có phù hợp? | Lý do |
| --- | --- | --- |
| POM quên một dependency runtime có thật | **Có** | Bổ sung edge trong variant runtime |
| POM khai báo dependency không cần | **Có, sau xác minh** | Xóa edge bằng removeAll |
| Dependency transitive version khai báo sai | **Có, thận trọng** | Điều chỉnh version constraint trong metadata |
| POM thiếu capability giữa hai implementations | **Có** | Thêm capability để Gradle phát hiện conflict |
| Classifier JAR tồn tại nhưng không có variant metadata | **Có, nâng cao** | addVariant + attributes + withFiles |
| Nhiều modules cần version alignment | **Có, tùy tình huống** | belongsTo với virtual platform |
| Module/version hoàn toàn không tồn tại trong repository | **Không** | Rule cần metadata component để thực thi |
| File JAR bị corrupt hoặc thiếu class thật | **Không** | Rule không sửa bytes của JAR |
| Repository không truy cập được/credentials sai | **Không** | Lỗi transport/auth, xảy ra trước rule |
| Muốn đổi module **old:lib** sang **new:lib** trong toàn project | **Thường không** | Xem dependency substitution/declaration |
| Muốn ép version cho một graph tiêu thụ | **Thường dùng constraint/platform/rich versions trước** | Policy version của consumer không nhất thiết là publication bug |
| Muốn biến đổi bytes của JAR | **Không** | Dùng artifact transform hoặc sửa producer |
| Muốn làm module publish metadata đúng cho mọi consumers | **Sửa upstream** | Rule chỉ áp dụng tại build khai báo/nhận nó |

**Một module có metadata nhưng thiếu artifact** không được “cứu” bằng cách viết withDependencies: Gradle vẫn cần tải artifact thật từ repository đúng. Tương tự, nếu module chỉ có POM sai nhưng POM không thể tải, rule không tự tạo được metadata.

## 15. Khi nào ưu tiên cách khác?

### 15.1. Sửa upstream publication là giải pháp lâu dài

Nếu bạn sở hữu thư viện:

1. Sửa dependency declarations trong source project.
2. Publish POM/Gradle Module Metadata đúng, với variants/capabilities nếu có.
3. Publish **version mới bất biến** thay vì thay JAR/POM dưới cùng GAV đã phát hành.
4. Kiểm thử consumer với publication mới.
5. Gỡ metadata workaround sau khi mọi consumers chuyển sang version đã sửa.

Rule là **bridge** cho metadata đã publish sai hoặc thư viện bên thứ ba chưa sửa; không nên trở thành lý do không bao giờ sửa producer.

### 15.2. Dependency constraint cho policy version của consumer

Nếu POM hoàn toàn đúng, nhưng ứng dụng cần tránh version lỗi và chọn bản vá:

~~~groovy
dependencies {
    constraints {
        implementation('org.example:json-core') {
            version {
                strictly('[2.1, 3.0[')
            }
            because('Application supports this API range')
        }
    }
}
~~~

Đây là **policy của consumer**, không phải chứng cứ POM của json-core sai. Constraint thích hợp hơn metadata rule nếu vấn đề chỉ là version mà app cho phép.

### 15.3. Dependency substitution để thay module

Khi cần chuyển từ một module sang module khác hoặc dùng project dependency thay binary, xem:

~~~groovy
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute module('org.example:legacy-api') using module('org.example:new-api:2.0')
    }
}
~~~

Đây là **ví dụ policy substitution** cần kiểm thử compatibility, không phải một rule thay POM. Substitution thay **dependency selector**; metadata rule điều chỉnh **metadata của component đã chọn**.

### 15.4. Artifact transform cho bytes, không phải dependency graph

Nếu bạn cần **giải nén, instrument, convert hoặc transform artifact** theo attributes, xem **artifact transforms**. Component metadata rule mô tả những files/variants tồn tại, không mở JAR, sửa class file hay ghi bản JAR mới.

### 15.5. Exclude transitive dependency cũng khác metadata rule

Consumer có thể dùng:

~~~groovy
dependencies {
    implementation('org.example:client:1.0') {
        exclude group: 'org.example', module: 'obsolete-logging'
    }
}
~~~

**exclude** tác động tại dependency edge mà consumer khai báo; nó không sửa metadata của library trên toàn graph. Nếu dependency xuất hiện từ nhánh khác, có thể vẫn nằm trong graph. Nếu POM của **client** thực sự publish dependency thừa, metadata rule có thể chính xác hơn vì sửa metadata tại source component.

## 16. Cách kiểm thử rule theo trường hợp và các lệnh debug

### 16.1. Trước khi thêm rule: thu thập bằng chứng

Chạy ở đúng project/configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
    --configuration runtimeClasspath \
    --dependency legacy-client
~~~

PowerShell viết một dòng:

~~~powershell
.\gradlew.bat dependencyInsight --configuration runtimeClasspath --dependency legacy-client
~~~

**dependencies** hiển thị graph, **dependencyInsight** tập trung vào một module và lý do chọn version/variant theo thông tin có sẵn. Không có lệnh nào tự hiểu code trong JAR để biết những dependencies bạn đã quên.

### 16.2. Kiểm tra compileClasspath và runtimeClasspath riêng

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Với lab chỉ sửa runtime variant:

- **compileClasspath** có thể chỉ chứa **legacy-client**.
- **runtimeClasspath** có **legacy-client** cùng **helper**.
- **run** thành công vì runtime classpath đủ class.

Nếu bạn sửa compile variant khi lỗi chỉ ở runtime, compiler có thể vẫn không có gì thay đổi ở môi trường thực thi. Ngược lại, nếu API cần helper khi compile, chỉ sửa runtime không đủ.

### 16.3. Dùng --info/--debug có mục đích

~~~bash
./gradlew run --info
~~~

Nếu cần xem resolution sâu hơn:

~~~bash
./gradlew run --debug
~~~

Logs có thể chứa đường dẫn repository, URL nội bộ và thông tin cấu hình. Không chia sẻ log nguyên bản nếu có secret/credentials. **--debug** nhiều output và không phải kiểm thử correctness thay cho graph/functional tests.

### 16.4. Cache và --refresh-dependencies

~~~bash
./gradlew dependencies --configuration runtimeClasspath --refresh-dependencies
~~~

Flag này yêu cầu tái kiểm tra dependency metadata/artifacts ở repository; nó **không luôn tải lại toàn bộ JAR**. Nếu class rule đã thay đổi, Gradle có thể cập nhật cache kết quả theo implementation/inputs. Trong lab local, thường chỉ cần build script mới và phân giải graph lại; không nên xóa bừa **~/.gradle/caches**.

Khi rule đã được cache, **không nhìn thấy println trong execute** không phải bằng chứng rule không có hiệu lực. Kiểm tra bằng **runtimeClasspath** và stdout cuối cùng.

### 16.5. Checklist thử nghiệm tự động

Một functional test đáng tin cho metadata rule nên:

1. Tạo fixture repository với POM thật sự sai.
2. Giữ riêng source/binary của helper và client.
3. Chạy resolver trước rule, xác nhận helper **vắng mặt**.
4. Chạy app trước rule, xác nhận lỗi **NoClassDefFoundError**.
5. Bật rule, kiểm tra graph có helper đúng version.
6. Chạy app sau rule, xác nhận **Client: helper ready**.
7. Thêm test rằng module version **1.1** không bị vá nếu rule chỉ nhắm 1.0.
8. Chạy với cache độc lập nếu cần xác định tác động cache hoặc rule registration.
9. Kiểm tra configuration cache/parallel execution theo yêu cầu môi trường nếu rule đóng vai trò trong build logic lớn.
10. Kiểm tra rule không tự phát network call hoặc sửa file source.

Gradle **TestKit** có thể chạy những functional tests này khi đóng gói rule trong plugin riêng. Đối với bài học, các lệnh Wrapper và fixture Java đã cung cấp là đủ để quan sát cơ chế.

## 17. Troubleshooting: lỗi hay gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **NoClassDefFoundError** khi run | Metadata không kéo dependency runtime | Kiểm tra POM/variant/runtimeClasspath; thêm edge đúng nếu đã xác minh |
| Rule không thấy tác dụng | Không đăng ký đúng project/configuration, sai group:name, sai variant name | Kiểm tra **withModule**, version guard, metadata format và graph |
| **withVariant('runtime')** không tác động module | Module dùng .module với **runtimeElements** | Xác định variant name thật, đổi rule theo publication |
| Compile thành công nhưng runtime vẫn lỗi | Chỉ sửa compile variant, không sửa runtime | Sửa đúng variant cần dependency |
| Build có dependency lạ sau khi dùng allVariants | Rule phạm vi quá rộng | Dùng withVariant hoặc giới hạn group/version |
| **No matching variant** | Attributes sai hoặc feature variant bị khai báo thiếu | Kiểm tra attributes, capability, files và consumer requirements |
| **Two modules provide same capability** | Rule thêm capability chung và cả hai implementations xuất hiện | Chọn implementation đúng hoặc điều chỉnh metadata |
| **Cannot find module** | Repository không có module/metadata | Sửa repository/coordinates; rule không tạo module |
| Artifact bị thiếu sau addVariant | File classifier không được publish, withFiles sai path | Xem archive publication và đường dẫn tương đối |
| Version vẫn không đổi dù rule thêm constraint | Constraint không tự thêm dependency, hoặc version requirement khác mạnh hơn | Dùng dependencyInsight, hiểu rich versions |
| Rule chỉ hoạt động ở root project | Subproject không đăng ký cùng rule | Đưa vào convention plugin hoặc central registration phù hợp |
| Rule chạy chậm mỗi lần | Inline/không cacheable hoặc logic có side effects | Class cô lập + @CacheableRule, tránh I/O |
| **@CacheableRule** vẫn có vấn đề cache | Params không serializable hoặc capture Project state | Dùng tham số hợp lệ và service injection đúng |
| App vẫn lỗi sau khi helper được thêm | Helper version sai hoặc class thực sự không có trong artifact | Mở JAR/kiểm tra bytecode/compatibility; rule không sửa bytes |
| Version khác giữa dev và CI | Repositories/cache/metadata formats/Gradle khác nhau | Giữ Wrapper và policy nhất quán, test cache sạch |
| Rule xóa dependency khiến plugin khác hỏng | Metadata thực ra đúng cho feature variant | Khôi phục dependency, giới hạn rule vào variant/version đúng |
| Build mới vẫn dùng workaround lỗi cũ | Upstream đã sửa ở version mới, rule vẫn áp toàn bộ versions | Thêm version guard và kế hoạch gỡ rule |

## 18. Bài tập tự kiểm tra và đáp án

### Bài 1 — Có nên dùng metadata rule?

Ứng dụng chọn **org.example:net-client:2.0**, POM quên **org.example:net-core:2.0**, class trong net-client gọi net-core khi chạy.

**Đáp án:** có thể dùng metadata rule thêm **net-core** vào runtime variant của net-client, sau khi xác minh dependency thật và version chính xác. Phải ưu tiên upstream sửa POM nếu có quyền.

### Bài 2 — Bị thiếu artifact chứ không thiếu dependency

Repository chứa **legacy-client-1.0.pom**, nhưng file **legacy-client-1.0.jar** không tồn tại. Có thể dùng **withDependencies { add(...) }** để tạo JAR thiếu không?

**Đáp án:** không. Rule không tạo artifact. Sửa publication hoặc route repository sao cho artifact thật được cung cấp.

### Bài 3 — Compile hay runtime?

API public của thư viện không nhắc tới Helper, nhưng code nội bộ gọi Helper khi chạy.

**Đáp án:** với Maven POM được Gradle map thành variants, **runtime** là nơi phù hợp để thêm Helper vào graph tiêu thụ khi runtime. Nếu API public dùng kiểu Helper, compile variant cũng có thể cần dependency.

### Bài 4 — allVariants có luôn đúng?

Một module có **apiElements**, **runtimeElements**, **nativeWindows**, **nativeLinux**. Bạn muốn thêm thư viện hỗ trợ chỉ cho runtime Linux.

**Đáp án:** không dùng **allVariants** vô điều kiện. Tìm đúng variant runtime/Linux, chỉnh dependencies và attributes của variant đó; kiểm thử consumer trên OS phù hợp.

### Bài 5 — Constraint hay dependency?

Module được publish thiếu JAR bắt buộc ở runtime; bạn thêm **withDependencyConstraints { add('g:h:1.0') }**.

**Đáp án:** constraint **không tự thêm g:h** vào graph. Phải thêm dependency trong **withDependencies**, không phải chỉ constraint.

### Bài 6 — Inline hay cacheable class?

Một workaround xuất hiện trong 30 subprojects và được dùng trên CI mỗi ngày.

**Đáp án:** nên viết **class triển khai ComponentMetadataRule có @CacheableRule**, đưa vào convention plugin hoặc nơi quản lý build logic chung; giới hạn phạm vi. Inline phù hợp thử nhanh hơn.

### Bài 7 — withModule khóa version nào?

~~~groovy
withModule('demo:legacy-client', FixLegacyClientRuntime)
~~~

Rule có nhắm riêng version 1.0 không?

**Đáp án:** không. **withModule** match group/name, và rule sẽ được xét cho các versions của module. Muốn chỉ sửa **1.0**, đặt guard **context.details.id.version == '1.0'**.

### Bài 8 — Capability hay version conflict?

Hai modules khác group:name cùng cung cấp logging implementation, nhưng graph đang có cả hai.

**Đáp án:** có thể bổ sung **cùng capability** cho variants tương ứng bằng metadata rule để Gradle phát hiện capability conflict. Sau đó chọn một implementation đúng; không áp “chọn version cao nhất của cùng module” lên hai module khác GAV.

### Bài 9 — Sửa version sai

POM đòi **support-api:1.0** nhưng upstream xác nhận phải dùng tối thiểu 2.1.

**Đáp án:** sửa version constraint của dependency edge bằng **dep.version { require('2.1') }**, hoặc biện pháp tương đương nếu semantics đã xác nhận. **require** vẫn có thể cho version cao hơn; nếu không tương thích trên 2.x thì phải xét strict range.

### Bài 10 — Vì sao phải kiểm tra version guard?

Một thư viện version **1.0** có POM sai, version **1.1** đã sửa. Rule tiếp tục add helper với version cố định cho 1.1.

**Đáp án:** metadata mới có thể đã chứa helper đúng, rule có thể tạo dependency trùng hoặc yêu cầu version cũ không phù hợp. Guard version và gỡ workaround khi nâng producer là thực hành an toàn.

## 19. Checklist đưa rule vào dự án thật

- Đã xác minh **publication thật sự sai/thiếu**, không phải chỉ policy consumer chưa đúng chưa?
- Có bằng chứng cụ thể (POM/.module/Ivy descriptor, lỗi runtime, graph trước/sau) chưa?
- Đã phân biệt **module/version**, **variant**, **dependency edge**, **constraint** và **artifact file** chưa?
- Rule có dùng **withModule** nhắm đúng group:name chưa?
- Có **version guard** để không sửa versions đã được producer sửa metadata chưa?
- Chỉnh **compile/runtime** đúng nhu cầu chưa?
- Nếu thêm dependency, tọa độ/version có được xác minh chưa? Có đưa thư viện không tin cậy vào graph không?
- Nếu xóa dependency, consumer vẫn biên dịch/chạy đúng chưa?
- Nếu sửa capabilities/attributes, có kiểm thử variant selection thật chưa?
- Nếu addVariant, artifact có tồn tại đúng path và attributes/capabilities đầy đủ chưa?
- Rule có deterministic, isolation-friendly, cacheable và không đọc Project/file/network tùy ý chưa?
- Có test với **dependencies**, **dependencyInsight**, Java 17 compile/runtime chưa?
- Nếu multi-project, registration có áp đúng scope chưa?
- Có ghi lý do rule, nguồn bằng chứng và điều kiện gỡ bỏ khi upstream publish fix chưa?
- Có kế hoạch nâng thư viện/sửa producer dài hạn chưa?

## Tài liệu tham khảo chính thức

- [Gradle — Modifying Dependency Metadata](https://docs.gradle.org/current/userguide/component_metadata_rules.html): hướng dẫn ComponentMetadataRule, withDependencies, capabilities, variants, belongsTo và status.
- [Gradle — ComponentMetadataRule API](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/ComponentMetadataRule.html): interface và execute(ComponentMetadataContext).
- [Gradle — ComponentMetadataDetails API](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/ComponentMetadataDetails.html): allVariants, withVariant, addVariant, belongsTo, changing, status.
- [Gradle — ComponentMetadataHandler API](https://docs.gradle.org/current/dsl/org.gradle.api.artifacts.dsl.ComponentMetadataHandler.html): withModule/all và cách đăng ký rules.
- [Gradle — Variant Attributes](https://docs.gradle.org/current/userguide/variant_attributes.html): mapping POM/Ivy sang variants và cơ chế chọn variant.
- [Gradle — Metadata Formats](https://docs.gradle.org/current/userguide/supported_metadata_formats.html): POM, Ivy, Gradle Module Metadata.
- [Gradle — Dependency Graph Resolution](https://docs.gradle.org/current/userguide/dependency_graph_resolution.html): pipeline resolve version/metadata/variants.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): cache metadata, --refresh-dependencies, changing modules.
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencies/dependencyInsight.
- [Gradle — Rich Dependency Versions](https://docs.gradle.org/current/userguide/dependency_versions.html): require, strictly, prefer, reject và constraints.

**Kết luận:** Component metadata rule **sửa cách Gradle hiểu một module đã publish**, không sửa file JAR, không tự tạo artifact và không thay thế việc publish đúng ở nguồn. Cách dùng vững chắc nhất là **nhắm đúng group:name/version/variant**, chỉnh **dependency/constraint/capability/attribute** có bằng chứng, đóng gói thành **rule cô lập có cache**, và xác minh bằng **graph trước/sau cùng bài test runtime**. Với lỗi POM thiếu dependency, thêm dependency vào variant đúng thường giải quyết tận gốc triệu chứng hơn việc tùy tiện ép version hoặc exclude module ở consumer.