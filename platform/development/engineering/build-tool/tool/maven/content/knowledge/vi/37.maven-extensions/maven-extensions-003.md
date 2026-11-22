# Tạo Mojo, khai báo goal và nhận tham số cấu hình trong Maven

## 1. Bức tranh tổng quan

Maven không chỉ chạy những plugins có sẵn như Compiler, Surefire hoặc JAR Plugin. Một nhóm phát triển có thể tự viết **Maven plugin bằng Java** để thực thi logic build riêng: kiểm tra quy ước dự án, tạo metadata, kiểm tra cấu hình, hỗ trợ code generation hoặc đưa một tác vụ nội bộ thành lệnh Maven dùng được trong CI.

Trong thuật ngữ Maven:
- **Plugin** là một artifact Java có `<packaging>maven-plugin</packaging>`, chứa một hoặc nhiều **goals**.
- **Mojo** là lớp Java hiện thực một goal, thường `extends AbstractMojo` và có method `execute()`.
- **Goal** là tên tác vụ xuất hiện trong câu lệnh `mvn plugin-prefix:goal` hoặc `mvn groupId:artifactId:version:goal`.
- **Plugin descriptor** ở `META-INF/maven/plugin.xml` là metadata giúp Maven biết plugin chứa goals nào, implementation class, parameters và yêu cầu thực thi.
- **`@Mojo`** đánh dấu lớp Java trở thành một goal và khai báo thuộc tính goal.
- **`@Parameter`** công bố một field/setter là input có thể nhận từ `<configuration>`, system/user property `-D...` hoặc biểu thức Maven.
- **Lifecycle phase** như `validate`, `compile` và `verify` là các mốc xây dựng; goal chỉ chạy theo lifecycle nếu có binding phù hợp.

Một sơ đồ:

```text
Maven project consuming a plugin
       |
       +-- POM <build><plugins><plugin>...
       |            |
       |            +-- <configuration> / <executions>
       |
       +-- mvn dev.learning.tools:greet-maven-plugin:1.0.0:greet
                    |
                    v
        Plugin artifact in Maven repository
                    |
          META-INF/maven/plugin.xml
                    |
          identifies goal "greet"
                    |
       GreetingMojo extends AbstractMojo
                    |
       @Parameter fields are configured
                    |
                 execute()
                    |
          Maven getLog() / errors
```

**Kết quả học tập:** tự xây được một plugin Java 17 hoàn chỉnh, tạo descriptor, cài plugin vào local repository, gọi goal qua tọa độ đầy đủ, cấu hình bằng POM và `-D`, bind goal vào `validate`, đọc lỗi tham số, viết tests và hiểu các giới hạn về bảo mật, tương thích phiên bản, parallel builds.

> Bài thực hành dùng Apache Maven **3.9.x** và Maven Plugin Tools / Maven Plugin Plugin **3.16.0**, là các phiên bản đã được Apache phát hành. Trong POM mẫu, Maven Plugin API dùng `3.9.16` và Java target là `17`. Đây là **các phiên bản được ghim cho bài thực hành**, không phải lời khẳng định mọi bản đó luôn mới nhất. Cần JDK 17+ và nguồn Maven artifacts được phép dùng.

Tài liệu chính thức chính: [Guide to Developing Java Plugins](https://maven.apache.org/guides/plugin/guide-java-plugin-development.html), [Using Plugin Tools Annotations](https://maven.apache.org/plugin-tools/maven-plugin-plugin/examples/using-annotations.html) và [Maven Plugin Plugin](https://maven.apache.org/plugin-tools/maven-plugin-plugin/).

## 2. Maven plugin khác thư viện Java thông thường

Cả hai đều có thể phát hành JAR, nhưng mục đích và cách Maven sử dụng khác nhau.

| Chủ đề | Java library | Maven plugin |
| --- | --- | --- |
| `packaging` thường dùng | `jar` | `maven-plugin` |
| Mục đích | Class/method cho application | Goal tác động quy trình build |
| API | Tùy library | `Mojo`/`AbstractMojo`, plugin APIs |
| Metadata quan trọng | POM, JAR | POM, JAR **và plugin descriptor** |
| Cách gọi | Import/use trong Java source | `mvn group:artifact:version:goal` |
| Tham số | Java args/constructors/config | Maven `@Parameter` + POM + `-D` |
| Vòng đời | Được build bởi Maven | Có thể chạy trong lifecycle của project khác |
| Phạm vi quyền | Theo JVM chạy application | Theo JVM/CI đang chạy Maven build |

**Maven plugin là code thực thi trong môi trường build**. Nó có thể đọc filesystem, biến môi trường, sử dụng network và (nếu được cấu hình) credentials của CI. Một custom goal cần được review như build-time executable code, không xem chỉ là file cấu hình vô hại.

### 2.1. Naming convention

Apache khuyến nghị cho third-party plugins:

```text
my-feature-maven-plugin
```

Ví dụ bài học chọn:

```text
groupId    = dev.learning.tools
artifactId = greet-maven-plugin
version    = 1.0.0
goal       = greet
```

**Không đặt tên `maven-greet-plugin` cho plugin của tổ chức**: pattern bắt đầu bằng `maven-...-plugin` được dành cho các official Apache Maven plugins theo Maven trademark/naming guidance.

### 2.2. Plugin prefix chỉ là tên rút gọn

Goal luôn có thể được gọi rõ ràng:

```bash
mvn dev.learning.tools:greet-maven-plugin:1.0.0:greet
```

Tên ngắn `greet:greet` phụ thuộc **plugin prefix mapping** và quá trình Maven khám phá plugin group: artifactId theo convention, metadata local/remote và `settings.xml` `pluginGroups`. Với plugin nội bộ mới tạo, **ưu tiên dạng đầy đủ** trong ví dụ/CI để tránh lỗi `No plugin found for prefix` hoặc vô tình dùng plugin khác cùng prefix.

## 3. Kiến trúc nội bộ: @Mojo, execute() và descriptor

### 3.1. Lớp Mojo tối giản

Ví dụ ngắn:

```java
package dev.learning.tools;

import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.Mojo;

/** Writes a fixed message to the Maven log. */
@Mojo(name = "hello")
public class HelloMojo extends AbstractMojo {
    @Override
    public void execute() throws MojoExecutionException {
        getLog().info("Hello from a Maven Mojo");
    }
}
```

**Đây chỉ là một đoạn class minh họa**, chưa phải project đầy đủ: muốn Maven nhận diện, phải có POM `maven-plugin`, plugin API, annotations và descriptor generator. Lab bên dưới dùng `GreetingMojo` hoàn chỉnh, không cần tạo thêm `HelloMojo`.

Các thành phần:
- `@Mojo(name="hello")` đăng ký **goal name**, không đặt tên JAR.
- `extends AbstractMojo` cung cấp `getLog()` và hạ tầng của Maven Mojo.
- `execute()` là điểm bắt đầu goal.
- `getLog().info(...)` dùng Maven logger thay vì in bừa bằng `System.out.println`.
- `MojoExecutionException` báo lỗi kỹ thuật khi goal không thể thực hiện.

### 3.2. Annotation là đầu vào để sinh descriptor

Maven Plugin Tools quét classes và annotations khi xây plugin. Plugin Plugin sinh metadata:

```text
greet-maven-plugin-1.0.0.jar
    |
    +-- dev/learning/tools/GreetingMojo.class
    +-- dev/learning/tools/GreetingFormatter.class
    +-- META-INF/maven/plugin.xml
```

Descriptor cho Maven biết:
- Goal `greet` có implementation class nào.
- Goal có `requiresProject`, `threadSafe`, default phase hoặc scopes không.
- Các parameters và kiểu dữ liệu.
- User property của mỗi parameter.
- Các defaults/required flags.
- Plugin dependency requirements.

**Không viết `plugin.xml` bằng tay cho lab annotation-based này.** `maven-plugin-plugin:descriptor` được bind trong lifecycle của `maven-plugin` packaging; chạy `package` sẽ tạo descriptor và đóng gói vào JAR. Không cần gọi goal tạo descriptor thủ công sau mỗi lần build.

### 3.3. Khi nào Maven đọc descriptor?

Khi consumer gọi plugin, Maven resolve plugin artifact và đọc `META-INF/maven/plugin.xml`. Nếu file này không tồn tại hoặc không có goal được yêu cầu, Maven sẽ không biết lớp Mojo cần chạy, ngay cả khi JAR chứa file `GreetingMojo.class`.

Vì vậy:
- Có annotation trong Java source **chưa đủ**.
- Cần Maven Plugin Plugin sinh descriptor khi build.
- Cần plugin JAR chứa descriptor.
- Cần cài hoặc publish đúng artifact/version để consumer tải được.

## 4. @Mojo: định danh goal và metadata

Một khai báo có nhiều thuộc tính:

```java
@Mojo(
    name = "greet",
    defaultPhase = LifecyclePhase.VALIDATE,
    requiresProject = true,
    threadSafe = true
)
public class GreetingMojo extends AbstractMojo {
    // execute() ...
}
```

Đây là **mẫu khai báo class**, không phải file Java độc lập. Ý nghĩa:

| Thuộc tính | Ý nghĩa | Chú ý |
| --- | --- | --- |
| `name` | **Tên goal** trong CLI | Bắt buộc, không trùng goal khác trong cùng plugin |
| `defaultPhase` | Phase mặc định dùng khi goal được bind theo cách phù hợp | **Không tự động chạy trong mọi project** |
| `requiresProject` | Có yêu cầu Maven project/POM không | Default thường là true |
| `threadSafe` | Khai báo goal an toàn với parallel build | Chỉ set true khi thực sự thread-safe |
| `aggregator` | Goal có phạm vi aggregator/reactor | Không tự bật với goal xử lý từng module |
| `requiresDependencyResolution` | Yêu cầu resolve dependencies theo scope | Có thể tăng thời gian build |
| `requiresDependencyCollection` | Yêu cầu collection graph theo scope | Không giống resolve tất cả JARs |
| `requiresOnline` | Goal đòi hỏi online | Không dùng nếu goal thuần local |

### 4.1. Bẫy phổ biến: defaultPhase không tự tạo lifecycle binding

`@Mojo(defaultPhase = LifecyclePhase.VALIDATE)` có ý nghĩa metadata cho phase phù hợp, nhưng **chỉ annotation này không làm `mvn validate` trong mọi project tự tìm và chạy plugin**.

Có hai phương thức khác nhau:

**Gọi goal trực tiếp:**

```bash
mvn dev.learning.tools:greet-maven-plugin:1.0.0:greet
```

**Bind goal vào lifecycle trong consumer POM:**

```xml
<executions>
    <execution>
        <id>greet-on-validate</id>
        <phase>validate</phase>
        <goals>
            <goal>greet</goal>
        </goals>
    </execution>
</executions>
```

Sau khi POM consumer có `execution`, `mvn validate` chạy goal. Việc ghi `<phase>validate</phase>` tường minh giúp tutorial và pipeline dễ đọc; một số goal có default phase được Maven dùng khi execution không khai báo phase, nhưng **không bao giờ suy ra mọi project tự bind goal chỉ từ annotation**.

### 4.2. threadSafe không phải cờ “chạy nhanh”

Đối với `mvn -T4`, Maven có thể thực thi modules độc lập trên nhiều threads. `threadSafe = true` là **lời cam kết của tác giả plugin**, không phải một cơ chế tự khóa shared state. Nếu goal ghi vào một file chung, port cố định hoặc sửa static mutable fields, đánh dấu threadSafe true là sai.

Bài lab chỉ format message và ghi Maven log, không ghi shared file, nên là ví dụ đơn giản có thể khai báo threadSafe. Với goal phức tạp, kiểm concurrency của plugin dependencies, caches và các external services trước khi đánh dấu.

### 4.3. requiresDependencyResolution chỉ dùng khi cần

Nếu goal chỉ đọc text và Maven project artifactId, không cần resolve dependency graph. Đừng đặt `requiresDependencyResolution=ResolutionScope.TEST` vô cớ: nó có thể khiến Maven tải hàng loạt test dependencies dù goal đơn giản, làm startup chậm và thêm failure do network.

Một goal kiểm classpath thực sự có thể cần:

```java
@Mojo(
    name = "inspect-classpath",
    requiresDependencyResolution = ResolutionScope.COMPILE
)
```

**Đây là snippet metadata không runnable một mình**, minh họa cách yêu cầu compile dependencies. Khi dùng thực tế phải import `ResolutionScope` và có logic kiểm graph.

## 5. @Parameter: Maven cung cấp input vào Mojo ra sao?

Maven inject config cho các annotated fields hoặc setters của goal. Ví dụ:

```java
@Parameter(property = "greet.message", defaultValue = "Hello")
private String message;

@Parameter(property = "greet.name", required = true)
private String name;

@Parameter(property = "greet.times", defaultValue = "1")
private int times;

@Parameter(property = "greet.uppercase", defaultValue = "false")
private boolean uppercase;

@Parameter(defaultValue = "${project.artifactId}", readonly = true)
private String projectArtifactId;
```

**Đây là tập field minh họa; lab có nguyên class với đúng fields và `execute()`.**

| Thành phần `@Parameter` | Tác dụng | Ví dụ |
| --- | --- | --- |
| `property` | Tên property Maven có thể lấy từ `-D...` hoặc properties | `greet.name` |
| `defaultValue` | Giá trị mặc định, có thể chứa expression Maven | `Hello` hoặc `${project.artifactId}` |
| `required` | Maven yêu cầu giá trị sau khi cấu hình | `required = true` |
| `readonly` | Hạn chế user cấu hình trực tiếp một thông tin hệ thống | Project artifactId |
| `name` | Tên parameter khác tên field | `@Parameter(name="displayName")` |
| `alias` | Tên thay thế của parameter | Hỗ trợ POM config tương thích |
| Java field type | Kiểu converter cần đưa vào field | `String`, `boolean`, `int`, `File`, lists... |

### 5.1. property khác tên POM element

Với field `private String name`:

```java
@Parameter(property = "greet.name", required = true)
private String name;
```

Cách cung cấp từ CLI:

```bash
mvn dev.learning.tools:greet-maven-plugin:1.0.0:greet -Dgreet.name=Lan
```

Cách cung cấp từ POM plugin configuration:

```xml
<configuration>
    <name>Lan</name>
</configuration>
```

**Lưu ý:** POM element là `<name>` (hoặc tên được khai báo qua `name`), trong khi `greet.name` là **tên property** cho `-D`. Đừng viết `<greet.name>Lan</greet.name>` rồi mặc định Maven hiểu như cùng một parameter.

### 5.2. required không thay domain validation

`@Parameter(required=true)` giúp Maven fail khi không inject được parameter bắt buộc. Nhưng cần **tự kiểm tra** những giá trị không hợp lệ như:
- Chuỗi `"   "` chỉ có khoảng trắng.
- Số nguyên `0` hoặc số âm cho repeat count.
- File path không nằm trong project output directory.
- Tên package không hợp lệ.
- Token/cấu hình chứa format bất ngờ.

Lab kiểm `name.isBlank()` và `1 ≤ times ≤ 5` bên trong `execute()`. `required=true` cộng với `defaultValue` không có nghĩa user buộc phải truyền tay: nếu default tạo giá trị hợp lệ thì parameter không còn thiếu.

### 5.3. defaultValue và Maven expressions

`@Parameter(defaultValue = "${project.artifactId}", readonly=true)` lấy artifactId của consumer project theo Maven expression evaluator. Các expressions thường gặp:

```text
${project.groupId}
${project.artifactId}
${project.version}
${project.build.directory}
${session}
${settings}
```

Cần có **Maven execution context phù hợp**, kiểu field phù hợp và module context rõ. Không tự suy ra `${project.artifactId}` là tên plugin: khi goal chạy ở consumer project, nó thường trỏ đến **consumer artifactId**.

Nếu plugin dùng `MavenProject` hoặc session objects thay vì String expressions, cần thêm API dependencies đúng scope và cân nhắc Maven 3/Maven 4 compatibility. Với bài đầu tiên dùng String giúp tách rõ parameter injection.

### 5.4. File, List, boolean và numbers

Ví dụ tham khảo (không là thành phần lab):

```java
@Parameter(
    defaultValue = "${project.build.directory}/generated-reports",
    property = "audit.outputDirectory"
)
private java.io.File outputDirectory;

@Parameter(defaultValue = "false", property = "audit.failOnWarning")
private boolean failOnWarning;

@Parameter(property = "audit.maxItems", defaultValue = "100")
private int maxItems;
```

Khi user cấu hình `maxItems=not-a-number`, Maven converter có thể fail **trước khi execute()**. Với fields `File`, hãy kiểm canonical destination và permission, không ghi ra đường dẫn ngoài workspace mà chưa được phép. Parameter là input, không bảo đảm an toàn.

**Setter injection** cũng được Maven Plugin Tools hỗ trợ ở các phiên bản phù hợp. Với field đơn giản, annotated private field đủ rõ; không cần tự viết getter/setter chỉ để Maven inject. Nếu dùng setter, tra đúng syntax và version Plugin Tools trong tài liệu chính thức trước khi chuyển code.

### 5.5. Thứ tự ưu tiên giữa POM và CLI

Maven phối hợp:
- XML `<configuration>` của plugin/execution trong POM.
- User/system properties như `-Dgreet.name=Lan`.
- `defaultValue` trong annotation.
- Maven model expressions.

**Không khẳng định vô điều kiện mọi `-D` luôn ghi đè mọi phần tử cấu hình XML.** XML explicit configuration và expression/property resolution có quy tắc của Maven/plugin configurator, phụ thuộc cách field được khai báo. Cách dễ học và kiểm chứng là:
1. Không cấu hình `<name>` trong consumer POM rồi dùng `-Dgreet.name=Lan`.
2. Cấu hình `<times>2</times>` trong consumer POM và không đưa `-Dgreet.times` ở lệnh đó.
3. Thử một nguồn duy nhất mỗi parameter trong lab.
4. Khi cần hỗ trợ CLI override bắt buộc, thiết kế/document cấu hình theo cách Maven expression được định nghĩa rõ và test behavior ở phiên bản đã ghim.

## 6. Lab hoàn chỉnh: plugin "greet" bằng Java 17

Tạo **hai Maven projects độc lập**:
- `plugin/`: code của Maven plugin, package dạng `maven-plugin`.
- `consumer/`: project gọi plugin, không cần Java source cho demo này.

Từ một workspace riêng, cây thư mục:

```text
maven-mojo-lab/
├── plugin/
│   ├── pom.xml
│   └── src/
│       ├── main/java/dev/learning/tools/
│       │   ├── GreetingFormatter.java
│       │   ├── GreetingPreview.java
│       │   └── GreetingMojo.java
│       └── test/java/dev/learning/tools/
│           └── GreetingFormatterTest.java
└── consumer/
    └── pom.xml
```

Không có parent aggregator ở `maven-mojo-lab/`; dùng `mvn -f plugin/pom.xml` và `mvn -f consumer/pom.xml` từ **thư mục maven-mojo-lab**. Đây là cách rõ nhất tránh vòng phụ thuộc plugin ↔ project sử dụng plugin.

### 6.1. Chuẩn bị thư mục

Linux/macOS:

```bash
mkdir -p maven-mojo-lab/plugin/src/main/java/dev/learning/tools
mkdir -p maven-mojo-lab/plugin/src/test/java/dev/learning/tools
mkdir -p maven-mojo-lab/consumer
cd maven-mojo-lab
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "maven-mojo-lab/plugin/src/main/java/dev/learning/tools" | Out-Null
New-Item -ItemType Directory -Force -Path "maven-mojo-lab/plugin/src/test/java/dev/learning/tools" | Out-Null
New-Item -ItemType Directory -Force -Path "maven-mojo-lab/consumer" | Out-Null
Set-Location maven-mojo-lab
```

Cần JDK17+, Maven 3.9.x, repository mirror được phép và quyền ghi vào workspace/local Maven repository. **Maven plugin được cài vào local repo bằng `install` để consumer có thể dùng**; không publish lên Central/Nexus trong bài thực hành.

### 6.2. `plugin/pom.xml` đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.tools</groupId>
    <artifactId>greet-maven-plugin</artifactId>
    <version>1.0.0</version>
    <packaging>maven-plugin</packaging>
    <name>Learning Greeting Maven Plugin</name>
    <description>
        A tiny Maven plugin for learning Mojo goal and parameters.
    </description>

    <prerequisites>
        <maven>3.9.0</maven>
    </prerequisites>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.plugin.tools.version>3.16.0</maven.plugin.tools.version>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <!-- Maven cung cấp API này khi plugin được chạy. -->
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-plugin-api</artifactId>
            <version>3.9.16</version>
            <scope>provided</scope>
        </dependency>

        <!-- Annotation dùng lúc build plugin descriptor. -->
        <dependency>
            <groupId>org.apache.maven.plugin-tools</groupId>
            <artifactId>maven-plugin-annotations</artifactId>
            <version>${maven.plugin.tools.version}</version>
            <scope>provided</scope>
        </dependency>

        <!-- Test dependency, không nằm trong plugin runtime. -->
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-plugin-plugin</artifactId>
                <version>${maven.plugin.tools.version}</version>
                <configuration>
                    <goalPrefix>greet</goalPrefix>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích chi tiết:

- `packaging=maven-plugin` không phải `jar` thông thường; Maven sử dụng bindings cần thiết để tạo descriptor.
- `maven-plugin-api` cung cấp `AbstractMojo`, `MojoExecutionException` và `MojoFailureException`; `provided` để tránh đóng gói Maven runtime API làm thư viện riêng bên trong plugin JAR.
- `maven-plugin-annotations` cung cấp `@Mojo`, `@Parameter`; `provided` vì annotations dùng để tạo metadata build-time, không cần như runtime library.
- Plugin Tools version `3.16.0` được ghim dùng chung cho annotation và Plugin Plugin; tránh mismatch.
- Java compiler `release=17` nghĩa consumers cần một runtime hỗ trợ plugin bytecode Java17+.
- `goalPrefix=greet` cung cấp tên prefix dự kiến; **dùng fully-qualified invocation trong lab** nên không phụ thuộc pluginGroups/metadata của repo.
- Surefire 3.6.1 hỗ trợ JUnit Jupiter tests.
- POM không có `distributionManagement` và không dùng release credentials. Chỉ cài local, không `deploy`.
- `<prerequisites><maven>3.9.0</maven></prerequisites>` mô tả Maven minimum trong plugin project; Maven 4 xử lý descriptor prerequisites theo rules mới. Để kiểm phiên bản chạy Maven 3.x trong consumer, nên có CI matrix và plugin version constraints rõ; riêng `prerequisites` không phải cơ chế tự tải Maven.

**Plugin project có Maven Plugin Plugin bản 3.16.0 đã ghi dưới `build/plugins`; `plugin:descriptor` được gắn mặc định với plugin packaging trong lifecycle.** Không cần thêm một execution `descriptor` tự chế có thể tạo duplicate descriptor ở phase sai.

### 6.3. `GreetingFormatter.java`

Tệp `plugin/src/main/java/dev/learning/tools/GreetingFormatter.java`:

```java
package dev.learning.tools;

import java.util.Locale;

/**
 * Pure Java helper, dễ unit test mà không cần khởi động Maven.
 */
public final class GreetingFormatter {

    private GreetingFormatter() {
    }

    public static String format(
            String message,
            String name,
            boolean uppercase) {

        if (message == null || message.isBlank()) {
            throw new IllegalArgumentException(
                "greet.message must not be blank");
        }

        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                "greet.name must not be blank");
        }

        String result = message.strip() + ", " + name.strip() + "!";
        return uppercase
            ? result.toUpperCase(Locale.ROOT)
            : result;
    }
}
```

Đây là **logic Java thuần**, không phụ thuộc Maven API:
- `strip()` loại khoảng trắng Unicode theo logic của JDK.
- `isBlank()` kiểm input chỉ có khoảng trắng.
- `Locale.ROOT` giữ behavior uppercase không phụ thuộc default locale của máy.
- Validation trả `IllegalArgumentException`; Mojo chuyển thành lỗi build thích hợp ở lớp adapter.

Tách business logic khỏi Maven execution API giúp kiểm thử dễ hơn và hỗ trợ tái sử dụng khi thêm goal khác.

### 6.4. `GreetingPreview.java`: stdout thuần Java kiểm chứng được

Tệp `plugin/src/main/java/dev/learning/tools/GreetingPreview.java`:

```java
package dev.learning.tools;

public final class GreetingPreview {

    private GreetingPreview() {
    }

    public static void main(String[] args) {
        System.out.println(
            GreetingFormatter.format("Hello", "Lan", false));
        System.out.println(
            GreetingFormatter.format("Xin chào", "Mai", true));
    }
}
```

**Stdout chính xác của chương trình Java này:**

```text
Hello, Lan!
XIN CHÀO, MAI!
```

Lệnh chạy sau khi build:

```bash
java -cp plugin/target/classes dev.learning.tools.GreetingPreview
```

Khác với log của Maven Plugin: `getLog().info(...)` được Maven format với prefix/ANSI/console tùy Maven và settings. **Không lấy nguyên log Maven làm stdout chính xác của `GreetingPreview`.**

### 6.5. `GreetingMojo.java`: một goal thật với parameters

Tệp `plugin/src/main/java/dev/learning/tools/GreetingMojo.java`:

```java
package dev.learning.tools;

import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugin.MojoFailureException;
import org.apache.maven.plugins.annotations.LifecyclePhase;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;

/**
 * Logs a configurable greeting in the current Maven project.
 */
@Mojo(
    name = "greet",
    defaultPhase = LifecyclePhase.VALIDATE,
    requiresProject = true,
    threadSafe = true
)
public final class GreetingMojo extends AbstractMojo {

    /** Greeting prefix, e.g. Hello. */
    @Parameter(property = "greet.message", defaultValue = "Hello")
    private String message;

    /** Name to greet; required from POM or property. */
    @Parameter(property = "greet.name", required = true)
    private String name;

    /** Number of greeting messages. */
    @Parameter(property = "greet.times", defaultValue = "1")
    private int times;

    /** Uppercase using a locale-independent helper. */
    @Parameter(property = "greet.uppercase", defaultValue = "false")
    private boolean uppercase;

    /** Maven project currently consuming the plugin. */
    @Parameter(
        defaultValue = "${project.artifactId}",
        readonly = true
    )
    private String projectArtifactId;

    @Override
    public void execute()
            throws MojoExecutionException, MojoFailureException {

        if (name == null || name.isBlank()) {
            throw new MojoFailureException(
                "greet.name must not be blank");
        }

        if (times < 1 || times > 5) {
            throw new MojoFailureException(
                "greet.times must be between 1 and 5");
        }

        final String line;
        try {
            line = GreetingFormatter.format(
                message, name, uppercase);
        } catch (IllegalArgumentException ex) {
            throw new MojoFailureException(ex.getMessage());
        }

        for (int i = 0; i < times; i++) {
            getLog().info(
                "[" + projectArtifactId + "] " + line);
        }
    }
}
```

Lớp này có một goal tên `greet`; không có mục đích network hoặc filesystem mutation. Khi Maven inject xong, nó:
1. Kiểm name và repeat count.
2. Dùng `GreetingFormatter` để tạo message.
3. Ghi `times` dòng qua Maven logger.
4. Throw `MojoFailureException` nếu user cấu hình sai.
5. Để Maven trả build failure thay vì `System.exit`.

**Lưu ý compile:** import của `@Mojo` và `@Parameter` nằm trong `org.apache.maven.plugins.annotations`, khác package `org.apache.maven.plugin` chứa `AbstractMojo`. Không import nhầm `org.apache.maven.plugin.Mojo` (interface) làm annotation.

### 6.6. Vì sao ở đây không cần MavenProject injection?

Mojo cần project artifactId để minh họa Maven expression nhưng chỉ cần một `String`:

```java
@Parameter(defaultValue = "${project.artifactId}", readonly = true)
private String projectArtifactId;
```

Khi consumer `greet-consumer` gọi goal, message log mang nhãn `[greet-consumer]`. Nếu thực sự phải đọc dependency graph, build dir hoặc modules, bạn có thể inject `MavenProject` bằng API phù hợp (thường `@Parameter(defaultValue="${project}", readonly=true)`) và thêm dependency `maven-core` đúng `provided` scope; **không cần làm thế trong bài đơn giản**, tránh coupling vào Maven internals.

## 7. Unit tests của logic Java

Tệp `plugin/src/test/java/dev/learning/tools/GreetingFormatterTest.java`:

```java
package dev.learning.tools;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingFormatterTest {

    @Test
    void formatsSimpleGreeting() {
        assertEquals(
            "Hello, Lan!",
            GreetingFormatter.format("Hello", "Lan", false));
    }

    @Test
    void trimsMessageAndName() {
        assertEquals(
            "Xin chào, Mai!",
            GreetingFormatter.format(
                "  Xin chào  ", "  Mai  ", false));
    }

    @Test
    void uppercasesWithRootLocale() {
        assertEquals(
            "XIN CHÀO, MAI!",
            GreetingFormatter.format(
                "Xin chào", "Mai", true));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
            IllegalArgumentException.class,
            () -> GreetingFormatter.format("Hello", "   ", false));
    }

    @Test
    void rejectsBlankMessage() {
        assertThrows(
            IllegalArgumentException.class,
            () -> GreetingFormatter.format(" ", "Lan", false));
    }
}
```

**5 JUnit Jupiter tests**:
- Basic formatting.
- Trimming.
- Locale-independent uppercase.
- Blank name.
- Blank message.

Đây là **unit tests của pure helper**, không phải integration tests chứng minh Maven đã inject annotation fields. Với phần parameter injection, cần chạy consumer goal ở các cấu hình bên dưới hoặc dùng Maven Plugin Testing Harness/Invoker Plugin.

### 7.1. Build và install plugin local

Từ thư mục root `maven-mojo-lab`:

```bash
mvn --version
java -version
mvn -B -ntp -f plugin/pom.xml clean install
```

Maven dùng lifecycle `maven-plugin`:
- Compile main Java classes.
- Sinh `plugin.xml` khi thực hiện plugin descriptor goal.
- Chạy 5 JUnit Jupiter tests.
- Đóng gói `plugin/target/greet-maven-plugin-1.0.0.jar`.
- Install plugin artifact và POM vào **local Maven repository**.

Dự kiến Surefire summary ở project plugin:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

Đây là thống kê theo source code và điều kiện build chuẩn, **không phải toàn bộ log Maven**; nếu môi trường thiếu Maven plugin API/dependencies hoặc JDK sai, build không thể hoàn tất.

### 7.2. Kiểm descriptor đã nằm trong JAR

Linux/macOS:

```bash
jar tf plugin/target/greet-maven-plugin-1.0.0.jar | grep 'META-INF/maven/plugin.xml'
```

Windows PowerShell:

```powershell
jar tf "plugin/target/greet-maven-plugin-1.0.0.jar" |
    Select-String "META-INF/maven/plugin.xml"
```

**Đường dẫn mong đợi có trong danh sách:**

```text
META-INF/maven/plugin.xml
```

Descriptor không phải Java source file bạn tự viết; nó là kết quả của Maven Plugin Plugin. Có thể kiểm `plugin/target/classes/META-INF/maven/plugin.xml` nếu cần debug thời điểm process-classes.

### 7.3. Chạy Java Preview

```bash
java -cp plugin/target/classes dev.learning.tools.GreetingPreview
```

Kết quả stdout chính xác:

```text
Hello, Lan!
XIN CHÀO, MAI!
```

Lệnh này **không gọi Mojo**; nó chỉ dùng helper Java đã compile. Bước consumer tiếp theo mới thực thi goal Maven thật.

## 8. Consumer project: gọi goal và bind vào lifecycle

Tệp `consumer/pom.xml` đầy đủ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.demo</groupId>
    <artifactId>greet-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <build>
        <plugins>
            <plugin>
                <groupId>dev.learning.tools</groupId>
                <artifactId>greet-maven-plugin</artifactId>
                <version>1.0.0</version>

                <configuration>
                    <!-- Name lấy từ CLI property greet.name. -->
                    <message>Hello</message>
                    <times>2</times>
                    <uppercase>false</uppercase>
                </configuration>

                <executions>
                    <execution>
                        <id>greet-on-validate</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>greet</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tại sao consumer dùng `packaging=pom`?** Bài học chỉ cần project context và plugin goal, không có Java source consumer. Build phase `validate` vẫn có hiệu lực cho một POM project. Với application `jar` thực tế, có thể gắn plugin vào POM của app mà không đổi logic goal.

### 8.1. Chạy goal trực tiếp

Sau `plugin clean install`:

```bash
mvn -B -ntp -f consumer/pom.xml dev.learning.tools:greet-maven-plugin:1.0.0:greet -Dgreet.name=Lan
```

Maven resolve plugin qua local Maven repository đã install, inject:
- `name=Lan` từ `-Dgreet.name=Lan`.
- `message=Hello` từ POM.
- `times=2` từ POM.
- `uppercase=false` từ POM.
- `projectArtifactId=greet-consumer` từ Maven project expression.

**Nội dung 2 dòng message trong Maven INFO logs**:

```text
[greet-consumer] Hello, Lan!
[greet-consumer] Hello, Lan!
```

Có thể có prefix `[INFO]`, plugin execution banner, project logs và khác biệt ANSI; đây là **payload của hai log messages**, không phải toàn bộ stdout nguyên văn của một Maven invocation.

### 8.2. Chạy phase validate

```bash
mvn -B -ntp -f consumer/pom.xml validate -Dgreet.name=Lan
```

Consumer POM đã bind `greet` vào `validate`, nên dự kiến cũng có **hai message payload** như trên. Khác với `mvn plugin:goal`, lệnh `mvn validate` thực hiện lifecycle phase và các goals đã được bind cho phase đó.

Chạy `mvn validate` **không** tự động chạy goal trên mọi project chưa khai báo `execution`. Nếu xóa section `<executions>` khỏi consumer POM, goal không còn được bind với `validate` chỉ vì Mojo ghi `defaultPhase=VALIDATE`.

### 8.3. Đổi tên từ CLI

```bash
mvn -B -ntp -f consumer/pom.xml validate -Dgreet.name=Mai
```

POM không ghi `<name>`, nên user property `-Dgreet.name` cung cấp parameter. Nội dung hai message:

```text
[greet-consumer] Hello, Mai!
[greet-consumer] Hello, Mai!
```

Nếu muốn thử cấu hình tên trực tiếp trong POM, thêm `<name>Hoa</name>` dưới `<configuration>` và bỏ `-Dgreet.name`. Đây là hai **nguồn cấu hình thay thế**; đừng yêu cầu một tham số lấy từ cả POM và CLI rồi kết luận precedence mà chưa kiểm thử.

### 8.4. Dùng defaultValue

Trong consumer POM, nếu **xóa `<message>Hello</message>`** khỏi `<configuration>`, annotation default `Hello` vẫn cung cấp message. Nếu xóa cả `<times>2</times>`, annotation default `1` làm goal log **một** dòng. Trường hợp xóa `name`/không truyền `-Dgreet.name` là khác: `@Parameter(required=true)` không có default, vì vậy goal nên fail khi Maven không có giá trị.

### 8.5. Direct goal và lifecycle có thể bị chạy hai lần

Một lệnh như:

```bash
mvn -B -ntp -f consumer/pom.xml validate dev.learning.tools:greet-maven-plugin:1.0.0:greet -Dgreet.name=Lan
```

bao gồm **hai requested tasks**:
1. Phase `validate` có execution `greet-on-validate`.
2. Goal `greet` được gọi trực tiếp.

Khi cả hai thực thi bình thường, goal có thể log **4 message payload** vì mỗi invocation dùng `times=2`. Đây không phải bug “Maven tự chạy hai lần” mà do user đã yêu cầu phase và goal; khi debugging hãy xem execution banner/goal invocations.

### 8.6. Quản lý phiên bản plugin

Consumer POM nên pin version:

```xml
<plugin>
    <groupId>dev.learning.tools</groupId>
    <artifactId>greet-maven-plugin</artifactId>
    <version>1.0.0</version>
</plugin>
```

Đây là snippet, không phải toàn bộ plugin config. Pin version cho reproducibility và security reviews. Maven plugin artifact không nên được thay bytes dưới cùng version release đã publish; khi sửa plugin code, phát hành **1.0.1** hoặc version mới theo policy.

## 9. Các lỗi tham số cần biết

### 9.1. Thiếu required parameter

Chạy consumer khi `name` chưa được cung cấp:

```bash
mvn -B -ntp -f consumer/pom.xml validate
```

Vì `@Parameter(property="greet.name",required=true)` không có default và consumer POM không có `<name>`, Maven sẽ báo lỗi cấu hình/injection goal. **Không ghi một chuỗi log lỗi cụ thể làm “stdout chính xác”**, vì thông báo và stack trace khác theo Maven/plugin tools version.

Để sửa, thêm `-Dgreet.name=Lan` hoặc cấu hình `<name>Lan</name>` trong consumer POM.

### 9.2. Blank name

```bash
mvn -B -ntp -f consumer/pom.xml validate "-Dgreet.name=   "
```

Nếu shell bảo toàn giá trị ba dấu cách, parameter có thể được Maven inject nhưng `name.isBlank()` khiến Mojo ném `MojoFailureException` với message `greet.name must not be blank`. **Đây là user input failure**, không phải lý do để tắt Maven error handling hoặc sửa file descriptor.

### 9.3. Repeat count không hợp lệ

Để không bị nhầm XML/CLI precedence, chỉnh consumer POM `<times>2</times>` thành `<times>0</times>` rồi chạy:

```bash
mvn -B -ntp -f consumer/pom.xml validate -Dgreet.name=Lan
```

Mojo sẽ ném `MojoFailureException("greet.times must be between 1 and 5")`. Sửa POM về giá trị 1–5.

Nếu viết `<times>abc</times>`, Maven có thể fail **trước execute()** khi converter không chuyển được chuỗi thành `int`. Lỗi conversion khác lỗi domain validation; tìm parameter name/expected Java type trong log.

### 9.4. Message blank

Thay `<message>Hello</message>` thành `<message> </message>` và chạy goal. Helper kiểm message blank và Mojo báo `greet.message must not be blank`. Maven có thể normalize XML whitespace khi cấu hình; tùy giá trị injection, thông báo cụ thể có thể là lỗi giá trị trống hoặc default được áp dụng. Bài học là **không chỉ dựa vào required/default**: input validation trong `execute()` vẫn cần cho user-controlled data.

### 9.5. Sự khác nhau giữa hai exception quan trọng

| Exception | Sử dụng khi | Ví dụ |
| --- | --- | --- |
| `MojoFailureException` | Điều kiện đầu vào/project vi phạm policy, có thể sửa bởi user | Name blank, count ngoài range, required config thiếu |
| `MojoExecutionException` | Lỗi kỹ thuật làm goal không thể thực thi | Không đọc được file, I/O failure, không gọi được service |

Cả hai có thể dẫn đến `BUILD FAILURE` và exit non-zero. Không dùng `System.exit(0)` để che lỗi hoặc `System.out.println` làm kênh duy nhất thông báo. Những exceptions này giúp Maven/CI xử lý error context đúng hơn.

## 10. Xem metadata và mô tả goal

### 10.1. help:describe

Sau khi `install` plugin, có thể dùng Apache Maven Help Plugin:

```bash
mvn -B -ntp -f consumer/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dplugin=dev.learning.tools:greet-maven-plugin:1.0.0 -Dgoal=greet -Ddetail=true
```

Help Plugin sẽ đọc plugin descriptor và hiển thị goal, metadata cùng parameters. Đối chiếu:
- Goal name `greet`.
- Implementation `dev.learning.tools.GreetingMojo`.
- `greet.name` required; `greet.message` default Hello.
- `greet.times` default 1, `greet.uppercase` default false.
- `defaultPhase=validate` nếu descriptor/help view trình bày.
- Java type của fields.

Tài liệu chính thức: [help:describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html).

### 10.2. Plugin Plugin có helpmojo tùy chọn

Apache Maven Plugin Plugin hỗ trợ goal `helpmojo` để sinh một `HelpMojo` riêng trong plugin source/build output. Nếu muốn có `greet:help`, có thể cấu hình plugin plugin execution tùy chọn:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-plugin-plugin</artifactId>
    <version>3.16.0</version>
    <executions>
        <execution>
            <id>generated-help-goal</id>
            <goals>
                <goal>helpmojo</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

**Đây là cấu hình nâng cao, không có trong runnable POM cơ bản.** Nó cần được merge vào chính plugin Plugin Plugin declaration, không tạo duplicate plugin entries. `helpmojo` và `descriptor` là các goals khác nhau; muốn sinh descriptor cho `@Mojo` thường chỉ cần lifecycle `maven-plugin` và phiên bản Plugin Plugin thích hợp.

### 10.3. Không nhầm `help:describe` với `help:evaluate`

- `help:describe`: xem **plugin/goal/parameters metadata**.
- `help:evaluate`: đánh giá Maven expressions, chẳng hạn project.version.
- `help:effective-pom`: xem cấu hình POM sau inheritance/profiles.
- `help:effective-settings`: xem settings merge, có thể chứa thông tin nhạy cảm.

Khi goal không nhận parameter dự kiến, inspect descriptor và effective configuration, không chỉ dựa vào source annotation; consumer có thể đang chạy **plugin version cũ** từ repository/cache.

## 11. Plugin prefix và goal discovery

### 11.1. Fully-qualified invocation là an toàn nhất cho lab

```bash
mvn -B -ntp -f consumer/pom.xml dev.learning.tools:greet-maven-plugin:1.0.0:greet -Dgreet.name=Lan
```

Ưu điểm: Maven biết rõ `groupId`, `artifactId`, `version` và `goal`. Không cần đoán plugin prefix hay configure `pluginGroups`.

### 11.2. Khi nào có thể dùng `greet:greet`?

Từ naming convention `greet-maven-plugin`, prefix dự kiến là `greet`. Nhưng lệnh:

```bash
mvn greet:greet -Dgreet.name=Lan
```

có thể fail vì Maven không tìm thấy prefix mapping trong current project/plugins hoặc trong các plugin groups được cấu hình. Có thể thêm custom plugin group vào `settings.xml`:

```xml
<pluginGroups>
    <pluginGroup>dev.learning.tools</pluginGroup>
</pluginGroups>
```

**Đây chỉ là đoạn settings**, không phải toàn bộ settings.xml. Với CLI trong CI, dùng full coordinates và pin version thay vì phụ thuộc nhiều vào prefix discovery/network metadata.

### 11.3. `pluginManagement` chưa làm plugin tự chạy

`<pluginManagement>` có thể cung cấp default plugin version/config cho child modules, nhưng **không tự bind plugin goals vào lifecycle**. Muốn chạy, vẫn cần khai báo dưới `<build><plugins>` kèm executions hoặc gọi goal trực tiếp phù hợp. Đây là một nguyên nhân phổ biến khiến custom goal “đã cấu hình” nhưng `mvn verify` không thấy chạy.

## 12. Kiểm thử custom Maven plugin đúng tầng

### 12.1. Unit tests

Phần lab đã kiểm `GreetingFormatter` bằng 5 JUnit tests. Đây là cách tốt để test pure logic, nhưng **không chứng minh**:
- Descriptor có goal `greet`.
- Maven inject `@Parameter` đúng.
- `<executions>` kích hoạt goal ở phase mong muốn.
- Error mapping chính xác trong Maven build.
- Plugin hoạt động ở Maven runtime/JDK versions mong muốn.

Vì vậy cần thêm tests thực thi goal thật.

### 12.2. Integration tests qua consumer

Một smoke test đơn giản từ root:

```bash
mvn -B -ntp -f plugin/pom.xml clean install
mvn -B -ntp -f consumer/pom.xml validate -Dgreet.name=Lan
```

Kiểm:
- Plugin artifact được install thành công.
- Descriptor tồn tại.
- Consumer resolve đúng plugin coordinates.
- Goal chạy chính xác tại `validate`.
- Log payload được in hai lần từ `times=2`.
- Exit code Maven bằng 0.
- Trường hợp thiếu name trả exit non-zero.

**Không dùng `mvn -fn` hoặc `-DskipTests` để thông qua kiểm thử**. Với CI, kiểm cả exit code lẫn test reports.

### 12.3. Maven Plugin Testing Harness

Apache Maven có [Maven Plugin Testing Harness](https://maven.apache.org/plugin-testing/), hỗ trợ thiết lập Mojo testing context và gọi goal trong môi trường thử nghiệm. Khi dự án mở rộng, có thể viết tests về:
- Load Mojo qua plugin descriptor.
- Field injection từ mẫu POM.
- Goal execute success/failure.
- Logging, file outputs, project context.

**Không bắt buộc áp harness cho ví dụ cơ bản nếu chưa chuẩn bị đầy đủ test POM/fixtures**. Không tự tuyên bố `GreetingFormatterTest` là harness integration test; nó chỉ test pure helper.

### 12.4. Maven Invoker Plugin

[Maven Invoker Plugin](https://maven.apache.org/plugins/maven-invoker-plugin/) có thể chạy các example consumer projects như một bài integration test thực tế. Một test fixture có thể:
1. Build/install plugin under test vào local test repository.
2. Chạy example `consumer/pom.xml` với `-Dgreet.name=Lan`.
3. Xác minh build success và log/payload.
4. Chạy một scenario thiếu required field để xác minh failure.
5. Tránh publish bất kỳ test artifact nào lên remote.

Nên cô lập test repository/workspaces để không dùng nhầm plugin SNAPSHOT/cached artifact từ phiên bản khác.

### 12.5. Test Maven CLI version matrix

Plugin target Java17, maven-plugin-api version3.9.16, Plugin Tools3.16.0; nên test trên Maven **3.9.x version được doanh nghiệp hỗ trợ** và JDK 17, JDK 21 nếu consumer cần. Không suy ra mọi version Maven3 hoặc Maven4 tương thích vì package compile. Maven4 có các API/plugin descriptor semantics phát triển riêng; khi muốn hỗ trợ Maven4, kiểm compatibility và test thực tế trên Maven4 release được duyệt.

## 13. Parameters nâng cao và dependency injection

### 13.1. `MavenProject`/`MavenSession`

Nếu goal cần thông tin project phức tạp, có thể khai báo fields với Maven expressions:

```java
// Snippet: cần import MavenProject và Maven API dependencies phù hợp.
@Parameter(defaultValue = "${project}", readonly = true)
private org.apache.maven.project.MavenProject project;
```

Khác với `projectArtifactId` kiểu `String` trong lab, type `MavenProject` yêu cầu dependency API đúng (thường `maven-core` scope provided khi xây plugin cho Maven3) và không nên sửa object bừa bãi. Goal dùng trong parallel reactor cần tránh mutable project state không có synchronization.

### 13.2. `@Component` và dependency injection

Plugin Tools có `@Component` để lấy các Maven/Plexus components khi thật sự cần, bên cạnh `@Parameter` để đọc config/project context. Đừng nhầm:
- `@Parameter` → cấu hình/expression/field injection.
- `@Component` → component/service injection.

Một custom goal có thể cần Plexus/Sisu container services, nhưng cần kiểm service lifecycle/scope khi dùng trong Maven Daemon hay `-T` parallel. Đối với utility thuần text, đừng thêm service injection vô cớ.

### 13.3. `@Execute`: fork lifecycle, không thay mặc định goal

Plugin Tools cung cấp `@Execute` cho goal cần fork một goal/phase/lifecycle. Đây là tính năng nâng cao; dùng sai có thể chạy thêm compile/test không mong muốn hoặc tạo vòng gọi. **Bài lab không cần fork lifecycle**: `execute()` chỉ ghi log.

`@Mojo(defaultPhase=VALIDATE)` không giống `@Execute(phase=...)`:
- `defaultPhase` nói phase mặc định khi goal được bind.
- `@Execute` định nghĩa forked execution liên quan đến goal.

Trước khi dùng `@Execute`, xem [Mojo API Specification](https://maven.apache.org/developers/mojo-api-specification.html) và phân biệt forked vs main lifecycle.

### 13.4. Aggregator và per-module goals

Goal gắn `aggregator=true` có thể làm việc với cả reactor thay vì mỗi project như goal thông thường, nhưng lifecycle behavior/CLI behavior có nuance. Nếu goal phải tạo **một** báo cáo chung cho multi-module:
- Xác định khi nào chạy một lần, khi nào chạy theo project.
- Sử dụng MavenProject/session APIs thích hợp.
- Không assume aggregator=true tự gom dependency graph hoặc render report.
- Tránh output shared path được nhiều module ghi đồng thời.
- Test khi chạy `mvn -T4`, `-pl`, `-am` và từ submodules.

Lab `GreetingMojo` là **per-project goal** thông thường, không cần aggregator.

## 14. Bảo mật và thiết kế một Mojo có chất lượng production

### 14.1. Validate inputs trước side effects

Một goal ghi file report cần validate:
- Tên file/path thuộc directory được phép.
- Không cho path traversal vượt workspace.
- Không overwrite file quan trọng.
- Không dùng arbitrary shell commands xây từ user input.
- Không log secret.
- Không kết nối mạng tự phát khi không cần.
- Không thay content release đã công bố.

Lab tránh side effects để tập trung vào annotation/parameter injection. Goal thật phải xác định trust boundary trước khi đọc/ghi filesystem hay gọi external process.

### 14.2. Không log credentials

Các parameters như `apiToken` hoặc `password` không được in bằng `getLog().info`, dù debugging dễ hơn. Dùng CI secret manager, Maven `settings.xml` server credentials khi phù hợp, least privilege và không commit secrets vào POM. Lưu ý một Maven plugin chạy trong CI có thể thấy môi trường/credentials hiện có; review plugin dependency/provenance và sandbox CI nơi cần.

### 14.3. Không dùng dynamic plugin versions cho release pipelines

Consumer nên pin plugin version, chẳng hạn `1.0.0`, chứ không phụ thuộc tình trạng repository thay đổi. Nếu cần hotfix code plugin, publish version mới, giữ `META-INF/maven/plugin.xml` khớp logic mới. Một local `mvn install` có thể ghi đè artifact cùng version trong cache; không coi đó là thực hành phù hợp cho remote immutable releases repository.

### 14.4. Thread safety, Maven Daemon và classloaders

Một goal có static mutable cache, global mutable fields hoặc singleton service có thể không thread-safe; với mvnd/JVM sống lâu, state leak giữa builds càng đáng lưu ý. `@Mojo(threadSafe=true)` phải dựa trên bằng chứng/test, không phải cách ép Maven bỏ warnings. Nếu goal ghi vào `target/generated-sources`, dùng directory theo module và tránh shared paths cho cả reactor.

### 14.5. Version compatibility của Maven Plugin API

`maven-plugin-api` được cung cấp bởi Maven runtime khi plugin chạy. Không đóng gói một Maven Core khác vào plugin fat JAR. Nếu gọi APIs chỉ tồn tại ở Maven3.9.16, consumer chạy Maven3.9.0 có thể gặp linkage error dù code compile. Bài lab chỉ dùng các API cơ bản đã ổn định; trong dự án thật cần:
- Ghim minimum Maven version đúng với APIs sử dụng.
- Chạy compatibility tests.
- Tránh các internal/non-public Maven classes.
- Theo tài liệu Maven 4 khi di chuyển plugin sang Maven4.

## 15. Troubleshooting theo triệu chứng

| Triệu chứng | Khả năng thường gặp | Cách xử lý |
| --- | --- | --- |
| `No plugin descriptor found` | Sai packaging hoặc descriptor không được sinh/đóng gói | Kiểm `maven-plugin`, Plugin Plugin, `plugin.xml` |
| `No plugin found for prefix` | Chưa có prefix mapping/pluginGroups, gọi từ project khác | Gọi full `groupId:artifactId:version:goal` |
| `Could not find goal 'greet'` | Descriptor không chứa goal hoặc consumer dùng plugin version cũ | Check `@Mojo(name)` và descriptor trong đúng JAR |
| `@Mojo cannot be resolved` | Thiếu `maven-plugin-annotations` dependency | Thêm dependency `provided` |
| `AbstractMojo cannot be resolved` | Thiếu `maven-plugin-api` dependency | Thêm API `provided` |
| Goal không chạy ở `mvn validate` | Chỉ có defaultPhase hoặc pluginManagement | Thêm `build/plugins/executions` |
| Required parameter missing | `name` không có giá trị | `-Dgreet.name=...` hoặc POM `<name>` |
| Parameter từ `-D` không có tác dụng | Property name sai hoặc POM config explicit khác | Xem descriptor và actual effective config |
| Repeat value `abc` fail trước execute | Không convert được sang `int` | Dùng số hợp lệ |
| Repeat `0` fail ở execute | Domain validation của Mojo | Đổi thành 1–5 |
| `BUILD FAILURE` sau MojoFailureException | Input/project vi phạm policy | Sửa config, không dùng `-fn` |
| Java class version lỗi | Runtime JDK thấp hơn target17 | Provision JDK17+ |
| `ClassNotFoundException` với Maven API | Plugin dependencies/scope không đúng, version incompatible | Fix POM and compatibility matrix |
| Tests không chạy | Surefire/Test naming hoặc skip flags | Kiểm `GreetingFormatterTest` và reports |
| `mvn install` pass nhưng consumer không resolve plugin | Local repo khác hoặc version/groupId sai | Check `-Dmaven.repo.local`, GAV và POM |
| Plugin output không giống stdout Java | Maven logger thêm prefix/ANSI | So log payload, không full console |
| Plugin chạy hai lần | Gọi cả phase và goal trong một lệnh | Xem executions/task list |
| Reactor parallel conflict | Shared output/static state | `-T1` để reproduce, sửa goal thread safety |
| Security scanner báo Maven API dependency bundle | Scope incorrect | Dùng `provided`, xem plugin JAR dependencies |
| Remote `deploy` bị từ chối | Permission/immutability policy | Không overwrite; phiên bản mới |

### 15.1. Checklist lệnh chẩn đoán

```bash
java -version
mvn --version
mvn -B -ntp -f plugin/pom.xml clean verify
jar tf plugin/target/greet-maven-plugin-1.0.0.jar
mvn -B -ntp -f plugin/pom.xml install
mvn -B -ntp -f consumer/pom.xml validate -Dgreet.name=Lan
```

Các commands thuộc **lab**; không tự chạy plugin download/deploy trên dự án production chỉ để debug. Nếu cần log chi tiết, dùng `-e` trước; `-X` có thể in nhiều cấu hình nhạy cảm và không nên mặc định trên CI có tokens.

## 16. Bài tập và đáp án

**Bài 1 — Phân biệt khái niệm.** Mojo, plugin và goal khác nhau ra sao?

**Đáp án:** Plugin là Maven artifact có thể chứa nhiều goals; mỗi goal thường được implement bởi một Mojo class, Maven gọi method `execute()` của Mojo.

**Bài 2 — Đặt tên.** Third-party plugin tên `maven-greet-plugin` có nên dùng không?

**Đáp án:** Không. Pattern `maven-...-plugin` dành cho official Apache plugins; dùng `greet-maven-plugin` hoặc `<prefix>-maven-plugin`.

**Bài 3 — Descriptor.** Vì sao compile được `GreetingMojo.class` mà Maven vẫn không tìm thấy goal?

**Đáp án:** JAR có thể thiếu `META-INF/maven/plugin.xml` hoặc descriptor không chứa `greet`. Kiểm packaging và Maven Plugin Plugin.

**Bài 4 — Goal name.** Annotation nào quyết định tên goal?

**Đáp án:** `@Mojo(name="greet")`.

**Bài 5 — Required.** Parameter nào lab yêu cầu từ consumer?

**Đáp án:** `name`, property `greet.name`, không có default.

**Bài 6 — CLI.** Cách truyền tên Lan?

**Đáp án:** `-Dgreet.name=Lan` hoặc `<name>Lan</name>` trong plugin `<configuration>`.

**Bài 7 — POM.** Tại sao `<times>2</times>` không phải `<greet.times>2</greet.times>`?

**Đáp án:** XML element là parameter name của field, còn `greet.times` là property alias cho CLI.

**Bài 8 — defaultValue.** Nếu không cấu hình message, lab dùng gì?

**Đáp án:** `Hello`.

**Bài 9 — Project expression.** `${project.artifactId}` trong consumer trả giá trị gì?

**Đáp án:** `greet-consumer`, không phải `greet-maven-plugin`.

**Bài 10 — Lifecycle.** Có `defaultPhase=VALIDATE` là `mvn validate` ở mọi POM sẽ chạy goal?

**Đáp án:** Không. Cần binding/execution hoặc gọi goal trực tiếp.

**Bài 11 — Test counts.** Lab có bao nhiêu JUnit unit tests?

**Đáp án:** Năm; test pure `GreetingFormatter`, chưa phải Mojo integration tests.

**Bài 12 — Java Preview.** Stdout chính xác là gì?

**Đáp án:**

```text
Hello, Lan!
XIN CHÀO, MAI!
```

**Bài 13 — Logger.** Dòng `getLog().info` có giữ nguyên stdout ở mọi máy không?

**Đáp án:** Không. Maven có thể thêm prefix/ANSI/console UI; nội dung payload là phần cần kiểm.

**Bài 14 — Error semantics.** Trường hợp `times=0` dùng exception nào?

**Đáp án:** `MojoFailureException` vì user config vi phạm range được cho phép.

**Bài 15 — Java compiler.** Plugin target17 có chạy được trên JVM11 không?

**Đáp án:** Không. Bytecode Java17 cần JDK/JRE hỗ trợ tương ứng.

**Bài 16 — Plugin API.** Tại sao `maven-plugin-api` scope `provided`?

**Đáp án:** Maven runtime cung cấp API; không nên đóng gói API Maven riêng trong JAR plugin.

**Bài 17 — Goal discovery.** Khi `greet:greet` không resolve, làm gì?

**Đáp án:** Dùng tọa độ đầy đủ, kiểm `pluginGroups`/prefix mapping và plugin artifact version.

**Bài 18 — Parallel.** `threadSafe=true` có tự bảo vệ shared file không?

**Đáp án:** Không. Đây là declaration; developer phải thiết kế/test concurrency.

**Bài 19 — help.** Command nào đọc metadata goal/parameters?

**Đáp án:** Maven Help Plugin `help:describe`, hoặc xem `META-INF/maven/plugin.xml`.

**Bài 20 — CI.** Có nên deploy plugin release mới sau khi chỉ unit test Formatter pass?

**Đáp án:** Chưa. Cần build descriptor, integration test consumer goal/parameters, kiểm Maven/JDK compatibility và policy bảo mật.

## 17. Checklist thực hành chuẩn

- [ ] Plugin artifact dùng `<packaging>maven-plugin</packaging>`.
- [ ] ArtifactId đúng third-party naming convention.
- [ ] `maven-plugin-api` và `maven-plugin-annotations` có versions/scope phù hợp.
- [ ] Maven Plugin Plugin được ghim version và sinh descriptor.
- [ ] Descriptor `META-INF/maven/plugin.xml` nằm trong built plugin JAR.
- [ ] Mojo extends `AbstractMojo` và override `execute()`.
- [ ] `@Mojo(name=...)` có tên goal rõ, không trùng trong plugin.
- [ ] `defaultPhase` và actual lifecycle `<executions>` được phân biệt.
- [ ] Parameters có Javadoc/description, type, default, property, required hợp lý.
- [ ] User input validation không chỉ dựa vào required.
- [ ] `-D` properties có tên rõ, không xung đột với POM config không mong muốn.
- [ ] Exceptions phân biệt config failure với execution/environment failure.
- [ ] Goal dùng `getLog()` thay cho ad-hoc stdout cho automation.
- [ ] Code không hard-code secret/user-home/path riêng máy.
- [ ] `threadSafe` chỉ true nếu code thật sự an toàn khi reactor parallel.
- [ ] Không yêu cầu dependency resolution/online vô cớ.
- [ ] Business logic tách khỏi Maven adapter để unit test.
- [ ] Unit tests chạy, không bị skip.
- [ ] Consumer test gọi full `groupId:artifactId:version:goal`.
- [ ] Test goal binding ở `validate`, missing parameter, invalid type/range.
- [ ] Plugin version được pin trong consumer.
- [ ] Plugin JAR không bundle Maven Core/API trái ý muốn.
- [ ] Maven/JDK compatibility matrix đã được kiểm theo policy.
- [ ] Plugin provenance/coordinates được review trước khi đưa vào CI.
- [ ] Không publish/deploy lên remote trong lab.
- [ ] Khi plugin release cần sửa, phát hành version mới thay vì overwrite.

## 18. Tài liệu Apache Maven chính thức

- [Guide to Developing Java Plugins](https://maven.apache.org/guides/plugin/guide-java-plugin-development.html): tạo Mojo, plugin POM, logging, parameters, invocation, binding.
- [Using Plugin Tools Java Annotations](https://maven.apache.org/plugin-tools/maven-plugin-plugin/examples/using-annotations.html): `@Mojo`, `@Parameter`, `@Execute`, `@Component` và Plugin Plugin setup.
- [Maven Plugin Plugin](https://maven.apache.org/plugin-tools/maven-plugin-plugin/): goals sinh descriptor/helpmojo và versions.
- [plugin:descriptor Goal](https://maven.apache.org/plugin-tools/maven-plugin-plugin/descriptor-mojo.html): sinh `plugin.xml`, lifecycle binding và options.
- [Plugin Plugin Usage](https://maven.apache.org/plugin-tools/maven-plugin-plugin/usage.html): descriptor/helpmojo, generated metadata.
- [Maven Plugin Annotations](https://maven.apache.org/plugin-tools/maven-plugin-tools-annotations/index.html): syntax metadata của `@Mojo`/`@Parameter`.
- [Mojo API Specification](https://maven.apache.org/developers/mojo-api-specification.html): goal requirements/parameters và execution behavior.
- [Maven Help Plugin — describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html): xem thông tin goal/parameters.
- [Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): cấu hình và executions trong POM.
- [Introduction to Plugin Prefix Mapping](https://maven.apache.org/guides/introduction/introduction-to-plugin-prefix-mapping.html): cách Maven tìm `prefix:goal`.
- [Maven Plugin Testing Harness](https://maven.apache.org/plugin-testing/): testing Mojo trong plugin context.
- [Maven Invoker Plugin](https://maven.apache.org/plugins/maven-invoker-plugin/): chạy integration test project/fixtures.
- [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phases, goals, plugin bindings.
- [Maven Plugin Tools 3.16.0 annotations API](https://maven.apache.org/plugin-tools/maven-plugin-annotations/apidocs/org/apache/maven/plugins/annotations/Mojo.html): annotation fields của goal.
