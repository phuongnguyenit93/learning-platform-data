# Khai báo yêu cầu phân giải phụ thuộc của goal trong Maven

## 1. Bài toán: goal của Maven plugin cần những dependency nào?

Bạn đang viết một Maven plugin có hai goal:

- `collect-graph`: phân tích danh sách tọa độ `groupId:artifactId:version` và các dependencies bắc cầu của một project, **không cần mở nội dung JAR**.
- `list-runtime-files`: kiểm tra các file dependency JAR mà ứng dụng cần lúc chạy, nên phải có đường dẫn artifact thực sự.

Cả hai goal đều sử dụng `MavenProject`, nhưng chúng cần Maven chuẩn bị dữ liệu theo **hai mức khác nhau**. Nếu không khai báo, một goal có thể nhìn thấy đồ thị chưa đủ hoặc nhận `Artifact#getFile() == null`. Nếu khai quá rộng, Maven phải tải nhiều artifact ngoài nhu cầu, gây chậm, khó hoạt động offline hoặc thất bại ở phase sớm.

Maven cho phép tác giả plugin mô tả nhu cầu ngay trong `@Mojo`:

```java
@Mojo(
    name = "collect-graph",
    requiresDependencyCollection = ResolutionScope.TEST
)
```

và:

```java
@Mojo(
    name = "list-runtime-files",
    requiresDependencyResolution = ResolutionScope.RUNTIME
)
```

Ý nghĩa quan trọng:

> **Collection** dựng thông tin về dependency graph và tọa độ artifacts; **resolution** còn cố tìm/tải nội dung artifacts để goal có thể sử dụng files. Phải khai báo đúng yêu cầu ở cấp **Mojo/goal**, không phải chỉ ở POM dependency của plugin.

Bài thuộc nhóm **Mở rộng Maven**. Ví dụ được viết theo **Maven 3.9.x**, **Java 17** và **Maven Plugin Tools 3.16.0**, đối chiếu với hướng dẫn phát triển plugin của Apache Maven năm 2026. Đây là kiến thức dành cho **người phát triển Maven plugin**, không chỉ người cấu hình dependency của một ứng dụng.

### Mục tiêu học tập

Sau bài, bạn có thể:
1. Phân biệt dependency graph collection và artifact file resolution.
2. Khai báo `requiresDependencyCollection`, `requiresDependencyResolution` bằng `@Mojo` và `ResolutionScope`.
3. Biết mỗi enum scope tương ứng những loại dependencies nào trong Maven 3.
4. Hiểu tại sao `@Mojo` không tự buộc một goal chạy ở lifecycle phase.
5. Biết cách lấy dependencies qua `MavenProject#getArtifacts()`, và kiểm `Artifact#getFile()` an toàn.
6. Phân biệt dependencies của **project đang được build** với dependencies của **chính Maven plugin**.
7. Tạo được plugin Java 17 thực tế có hai goal và descriptor `META-INF/maven/plugin.xml`.
8. Tạo consumer project có compile/runtime/test dependencies và so sánh outputs.
9. Hiểu vì sao Maven có thể báo resolution error **trước khi** gọi `execute()`.
10. Tránh phân giải phạm vi quá rộng ở phase sớm hoặc trên reactor multi-module chưa build.
11. Kiểm descriptor và debug bằng Maven Help Plugin, Maven Dependency Plugin và logs.
12. Viết tests/integration checks để bảo đảm scope và file requirements đúng.

## 2. Collection và resolution: khác nhau ngay từ trách nhiệm của Maven

### 2.1. Dependency collection là gì?

Một Maven dependency có ít nhất những đặc điểm như:
- groupId, artifactId, version;
- extension/type và classifier nếu có;
- scope như compile, runtime, test, provided, system;
- metadata từ POM, dependencyManagement, exclusions và optional;
- quan hệ bắc cầu trong dependency graph.

Để **collect**, Maven Resolver đọc project model và các POM/metadata cần thiết, chọn versions, áp dụng mediation/filters và dựng tập dependencies. Nó có thể phải truy cập repository để lấy **POM descriptors và metadata**, nhưng **không bắt buộc tải file JAR thực thi**.

Ví dụ:

```text
app:1.0
├── org.apache.commons:commons-lang3:3.14.0 (compile)
├── org.slf4j:slf4j-api:2.0.13           (runtime)
└── org.junit.jupiter:junit-jupiter:5.11.4 (test)
    ├── junit-jupiter-api
    ├── junit-jupiter-params
    └── junit-jupiter-engine
```

Đây là **sơ đồ rút gọn**, không phải toàn bộ graph đã được Maven giải quyết: JUnit còn các transitive components khác và versions phụ thuộc POM/mediation. Nếu goal chỉ cần in tọa độ, việc tải mọi JAR là không cần thiết.

### 2.2. Dependency resolution là gì?

**Resolve** đi xa hơn collection: Maven phải làm cho những artifacts thuộc scope yêu cầu có các nội dung files tương ứng, ví dụ `commons-lang3-3.14.0.jar` trong local repository. Với MavenProject, `Artifact#getFile()` có thể chỉ tới file/directory đã được phân giải.

```text
project POM + dependency graph
                |
                v
            collection
                |
                v
       coordinates/scopes
                |
                v
             resolution
                |
                v
       actual artifact files
```

Resolution có thể yêu cầu Maven tải artifacts, kiểm repository/mirror, xác nhận checksum theo policy, ghi local cache, hoặc sử dụng reactor outputs. Nếu artifact bị thiếu và Maven không thể tải nó, goal có thể **không được gọi**.

### 2.3. Bảng so sánh

| Đặc tính | `requiresDependencyCollection` | `requiresDependencyResolution` |
| --- | --- | --- |
| Mục tiêu | Biết những dependencies/transitive coordinates nào tồn tại | Có files thực tế của dependencies thuộc scope |
| Đọc POM và metadata | Có thể cần | Có thể cần |
| Tải JAR dependencies | Không được yêu cầu chỉ bởi collection | Có thể cần nếu local cache chưa có |
| `Artifact#getFile()` | Có thể `null` | Thường có file/dir thích hợp khi resolution thành công |
| Dùng cho | License list theo tọa độ, inventory/graph, phân tích phiên bản | Copy/extract JAR, bytecode scan, mở artifact files |
| Ưu điểm | Ít tải binary hơn; phù hợp một số phase sớm | Goal có thể làm việc với contents của artifact |
| Giới hạn | Không được giả định files sẵn | Có thể fail/chậm nếu thiếu artifact |
| Kiểu khai báo | `@Mojo(requiresDependencyCollection = ...)` | `@Mojo(requiresDependencyResolution = ...)` |

**Điểm dễ nhầm:** collection **không có nghĩa offline**. Nếu POM của transitive dependency chưa được cache, Maven vẫn có thể liên hệ remote repository để lấy POM/metadata. Khác biệt chỉ là nó **không yêu cầu tải binary JAR** cho mọi dependency.

### 2.4. Collection-only vẫn có thể nhìn thấy file

Nếu trước đó một phase/goal khác đã phân giải dependency, trong một lần chạy Maven có thể đã có file trong local cache và các `Artifact` có thể trỏ tới file. Vì vậy kết luận đúng là **file không được bảo đảm**, không phải “mọi `getFile()` luôn `null` khi dùng collection”.

Để viết plugin chắc chắn:
- nếu chỉ in tọa độ: **không cần gọi `getFile()`**;
- nếu phải đọc contents: **khai `requiresDependencyResolution` phù hợp**;
- nếu đọc path tùy điều kiện: kiểm `null`/`exists()`, và xử lý lỗi có thông điệp rõ.

## 3. Cấu hình ở cấp Mojo: Annotation, Descriptor và Maven Core

### 3.1. @Mojo

Apache Maven Plugin Tools cung cấp annotation:

```java
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.ResolutionScope;
```

Ví dụ:

```java
@Mojo(
    name = "inspect",
    requiresDependencyResolution = ResolutionScope.RUNTIME,
    threadSafe = true
)
public final class InspectMojo extends AbstractMojo {
    // ...
}
```

Trong lúc build Maven plugin, `maven-plugin-plugin` đọc annotations và tạo descriptor `META-INF/maven/plugin.xml` trong plugin JAR. **Maven sử dụng descriptor để biết yêu cầu của goal trước khi gọi mã Java**.

`@Mojo` là metadata khai báo, không phải một lời gọi API tải dependencies bên trong `execute()`.

### 3.2. requiresDependencyResolution

```java
@Mojo(
    name = "inspect-jar-files",
    requiresDependencyResolution = ResolutionScope.RUNTIME
)
```

Đánh dấu rằng khi goal bắt đầu, Maven cần phân giải dependencies thuộc runtime classpath scope. Các JAR cần tải (nếu chưa có) được chuẩn bị **trước** khi mã của goal kiểm `Artifact#getFile()`.

Đừng chọn `ResolutionScope.TEST` chỉ vì nó “bao trùm tất cả”. Với goal runtime-only, `TEST` có thể buộc tải JUnit/Surefire-related **project test dependencies** dù không liên quan mục tiêu, gây chậm và tăng nguy cơ lỗi repo.

### 3.3. requiresDependencyCollection

```java
@Mojo(
    name = "inspect-graph",
    requiresDependencyCollection = ResolutionScope.TEST
)
```

Chọn khi goal cần thông tin **toàn bộ tập dependencies của test classpath**, nhưng không mở file JAR. Đây là lựa chọn tự nhiên cho một goal in tọa độ hoặc phân tích dependency scopes.

### 3.4. Nếu không khai báo thì sao?

Với Java annotation `@Mojo` trong Maven Plugin Tools 3.16.0, mặc định:

```text
requiresDependencyResolution = NONE
requiresDependencyCollection = NONE
```

**Chú ý phân biệt tài liệu:** Một số tài liệu plugin descriptor cũ mô tả default của trường descriptor `requiresDependencyResolution` theo cách lịch sử; mặc định **annotation** `@Mojo` hiện hành là `ResolutionScope.NONE`. Khi viết code Java dựa trên annotations, dùng Javadocs đúng version và kiểm **descriptor thực tế** sau khi build, không suy từ bảng doc cũ.

Nếu goal chỉ đọc `project.getName()`, `project.getBuild().getDirectory()` hay xử lý config không cần dependencies, **NONE là đúng** và tránh việc Maven làm thêm việc không cần.

### 3.5. @Mojo không tự gọi goal theo lifecycle

`@Mojo(defaultPhase = LifecyclePhase.VERIFY)` chỉ đặt **default phase** của goal trong descriptor. Nó **không tự động khiến plugin goal chạy** khi người dùng chỉ thêm plugin vào POM. Muốn chạy theo lifecycle cần execution binding phù hợp:

```xml
<executions>
    <execution>
        <id>inspect-after-test</id>
        <phase>verify</phase>
        <goals>
            <goal>collect-graph</goal>
        </goals>
    </execution>
</executions>
```

Đây là **fragment plugin configuration**, cần được đặt dưới `<build><plugins><plugin>` của consumer POM. Đừng copy fragment vào plugin source POM rồi kỳ vọng nó tự áp dụng cho mọi downstream projects.

## 4. ResolutionScope: các enum constants cần nhớ

Theo `org.apache.maven.plugins.annotations.ResolutionScope` (Plugin Tools 3.16.0):

| Enum | Descriptor value | Dependencies được yêu cầu trong Maven 3 |
| --- | --- | --- |
| `NONE` | Không yêu cầu | Không yêu cầu collection/resolution |
| `COMPILE` | `compile` | compile + system + provided |
| `RUNTIME` | `runtime` | compile + runtime |
| `TEST` | `test` | compile + system + provided + runtime + test |
| `COMPILE_PLUS_RUNTIME` | `compile+runtime` | compile + system + provided + runtime |
| `RUNTIME_PLUS_SYSTEM` | `runtime+system` | compile + system + runtime |

**COMPILE_PLUS_RUNTIME và RUNTIME_PLUS_SYSTEM** được ghi trong Javadocs là các kết hợp đặc thù Maven 3. Khi thiết kế plugin dùng cả Maven 3 và 4, cần kiểm API/compatibility docs của runtime Maven 4, không mặc định copy enum behavior từ Maven 3.

### 4.1. Phân biệt ngưỡng scope với scope của một dependency

Trong consumer POM:

```xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <version>2.0.13</version>
    <scope>runtime</scope>
</dependency>
```

`<scope>runtime</scope>` là cách người dùng khai **scope của một dependency**. Còn `ResolutionScope.RUNTIME` trong `@Mojo` là yêu cầu của **goal đối với tập dependencies cần chuẩn bị**.

Cả hai có liên hệ nhưng **không phải cùng một cấu hình**. Đặt `@Mojo(...RUNTIME)` không sửa `scope` trong POM. Và filter thủ công trong `execute()` không khiến Maven biết phải resolve những JAR chưa có.

### 4.2. COMPILE không tự bao gồm runtime

Tên enum dễ đánh lừa. Theo Maven Plugin Tools:

- `COMPILE` = compile + system + provided.
- `RUNTIME` = compile + runtime.
- `TEST` = mọi nhóm chính.

Nếu plugin cần compile dependencies và cả runtime-only artifacts nhưng **không cần test**, hãy cân nhắc `COMPILE_PLUS_RUNTIME` trên Maven 3. Nếu plugin chỉ cần classpath của ứng dụng khi chạy, `RUNTIME` thường thích hợp hơn.

### 4.3. TEST không có nghĩa chỉ lấy dependencies scope test

`ResolutionScope.TEST` yêu cầu tập dependencies đủ cho **test classpath**, nên bao gồm compile/runtime/provided/system lẫn test. Một goal dùng `TEST` có thể làm tăng download chi phí đáng kể so với `RUNTIME`. Đừng nhầm `TEST` là bộ lọc chỉ lấy artifacts có `<scope>test</scope>`.

## 5. Project thực hành: Maven plugin có hai goal độc lập

Chúng ta tạo một plugin thật với packaging `maven-plugin` và một consumer project riêng. Bài ví dụ **có thể build/install/run** trên Maven 3.9.16, JDK 17 và có khả năng tải dependencies từ Maven Central (hoặc mirror được cấu hình).

Project name dùng dạng `scope-inspector-maven-plugin` theo convention không chiếm tiền tố `maven-...-plugin` dành cho plugins chính thức của Apache Maven.

### 5.1. Cấu trúc dự án

```text
maven-goal-resolution-lab/
├── scope-inspector-maven-plugin/
│   ├── pom.xml
│   └── src/main/java/dev/example/training/plugin/
│       ├── CollectGraphMojo.java
│       └── ListRuntimeFilesMojo.java
└── scope-inspector-consumer/
    ├── pom.xml
    ├── src/main/java/dev/example/consumer/ConsumerMain.java
    └── src/test/java/dev/example/consumer/ConsumerMainTest.java
```

Đây là hai Maven projects **độc lập**, không phải một reactor Maven multi-module; mục đích là tách việc **biên dịch plugin** và **sử dụng plugin**. Ta chạy `mvn install` cho plugin rồi chạy Maven CLI với full plugin coordinates trong consumer.

### 5.2. POM của Maven plugin (đầy đủ)

File `scope-inspector-maven-plugin/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example.training</groupId>
    <artifactId>scope-inspector-maven-plugin</artifactId>
    <version>1.0.0</version>
    <packaging>maven-plugin</packaging>
    <name>Dependency Scope Inspector Maven Plugin</name>

    <prerequisites>
        <maven>3.9.0</maven>
    </prerequisites>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven-plugin-tools.version>3.16.0</maven-plugin-tools.version>
        <maven-api.version>3.9.16</maven-api.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-plugin-api</artifactId>
            <version>${maven-api.version}</version>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-core</artifactId>
            <version>${maven-api.version}</version>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>org.apache.maven.plugin-tools</groupId>
            <artifactId>maven-plugin-annotations</artifactId>
            <version>${maven-plugin-tools.version}</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-plugin-plugin</artifactId>
                <version>${maven-plugin-tools.version}</version>
                <configuration>
                    <goalPrefix>scope-inspector</goalPrefix>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Giải thích POM plugin:**

- `<packaging>maven-plugin</packaging>` kích hoạt lifecycle thích hợp để tạo Maven plugin descriptor.
- `maven-plugin-api` cung cấp `AbstractMojo`, `MojoExecutionException`, logger.
- `maven-core` cung cấp `MavenProject`. Ví dụ truy cập artifact model qua `org.apache.maven.artifact.Artifact`.
- `maven-plugin-annotations` cung cấp `@Mojo`, `@Parameter`, `ResolutionScope`.
- Cả API/Core/Annotations đều `provided` vì Maven host cung cấp runtime API; không bundle một bản Maven Core mới vào plugin JAR một cách không cần thiết.
- `maven-plugin-plugin:3.16.0` sinh `META-INF/maven/plugin.xml` từ annotations; không cần tự viết descriptor.
- `goalPrefix=scope-inspector` thuận lợi khi dùng short plugin prefix; bài sử dụng **full coordinates** để tránh ambiguity.
- `maven.compiler.release=17` nghĩa là plugin này yêu cầu Java runtime tương thích Java 17; không cam kết chạy trên Java 8/11.
- `maven-api.version=3.9.16` ghim theo Maven 3.9.16. Khi muốn hỗ trợ bản Maven 3 cũ hơn, build/test với **Maven API tối thiểu** và CI matrix phù hợp, tránh vô tình gọi API mới chỉ có trong 3.9.16.
- `<prerequisites><maven>3.9.0</maven>` dành cho project plugin, không phải convention tùy tiện cho project Java application.

### 5.3. CollectGraphMojo.java — thu thập tọa độ, không yêu cầu JAR

Đường dẫn `scope-inspector-maven-plugin/src/main/java/dev/example/training/plugin/CollectGraphMojo.java`:

```java
package dev.example.training.plugin;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

import org.apache.maven.artifact.Artifact;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;
import org.apache.maven.plugins.annotations.ResolutionScope;
import org.apache.maven.project.MavenProject;

/**
 * Displays the coordinates of test-classpath dependencies.
 * File contents are not needed.
 */
@Mojo(
        name = "collect-graph",
        requiresDependencyCollection = ResolutionScope.TEST,
        threadSafe = true
)
public final class CollectGraphMojo extends AbstractMojo {

    @Parameter(
            defaultValue = "${project}",
            readonly = true,
            required = true
    )
    private MavenProject project;

    @Override
    public void execute() throws MojoExecutionException {
        Set<Artifact> collected = project.getArtifacts();
        if (collected == null) {
            throw new MojoExecutionException(
                    "Maven did not provide the collected dependency set");
        }

        List<Artifact> sorted = new ArrayList<>(collected);
        sorted.sort(Comparator.comparing(Artifact::getId));

        getLog().info("Collected artifacts: " + sorted.size());

        for (Artifact artifact : sorted) {
            getLog().info(
                    "COORD " + artifact.getGroupId()
                    + ":" + artifact.getArtifactId()
                    + ":" + artifact.getVersion()
                    + " scope=" + artifact.getScope()
            );
        }
    }
}
```

**Tại sao code này thực hiện đúng ý định?**

1. `@Mojo(name = "collect-graph")` đăng ký goal tên `collect-graph`.
2. `requiresDependencyCollection = ResolutionScope.TEST` yêu cầu collection ở phạm vi đầy đủ cho test classpath.
3. `@Parameter(defaultValue = "${project}", readonly = true, required = true)` đưa MavenProject hiện tại vào field; nó **không phải annotation cấp dependency scope**.
4. `project.getArtifacts()` trả tập artifacts tương ứng với phạm vi mà Maven đã chuẩn bị cho goal, bao gồm transitive dependencies đã chọn theo rules Maven.
5. Sorting theo `Artifact#getId()` để thứ tự log ổn định, vì `Set` không bảo đảm thứ tự hiển thị.
6. Goal **không gọi `getFile()`**, không đọc JAR, không copy artifact và không yêu cầu resolution.
7. Kết quả in tên/version/scope thực tế từ Maven, không hard-code số dependencies.
8. `threadSafe=true` hợp lý ở đây vì goal không ghi trạng thái chia sẻ, không dùng static mutable state và chỉ log dữ liệu MavenProject. Plugin tác động vào filesystem/network sẽ cần review kỹ trước khi tự nhận thread-safe.

**Lưu ý:** `project.getArtifacts()` phản ánh tập dependencies đã được Maven chuẩn bị và lọc theo thực thi thực tế. Nó không phải raw POM text, không nhất thiết giữ tất cả candidates từng bị mediation loại bỏ. Muốn xem một graph đầy đủ gồm conflicts/omissions và vì sao chúng bị chọn/bỏ, dùng Maven Resolver APIs phù hợp hoặc dependency analysis tools thay vì coi `Set<Artifact>` là toàn bộ lý lịch mediation.

### 5.4. ListRuntimeFilesMojo.java — yêu cầu artifact files

Đường dẫn `scope-inspector-maven-plugin/src/main/java/dev/example/training/plugin/ListRuntimeFilesMojo.java`:

```java
package dev.example.training.plugin;

import java.io.File;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

import org.apache.maven.artifact.Artifact;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;
import org.apache.maven.plugins.annotations.ResolutionScope;
import org.apache.maven.project.MavenProject;

/**
 * Lists files associated with resolved runtime dependencies.
 */
@Mojo(
        name = "list-runtime-files",
        requiresDependencyResolution = ResolutionScope.RUNTIME,
        threadSafe = true
)
public final class ListRuntimeFilesMojo extends AbstractMojo {

    @Parameter(
            defaultValue = "${project}",
            readonly = true,
            required = true
    )
    private MavenProject project;

    @Override
    public void execute() throws MojoExecutionException {
        Set<Artifact> artifacts = project.getArtifacts();
        if (artifacts == null) {
            throw new MojoExecutionException(
                    "Maven did not provide the resolved dependency set");
        }

        List<Artifact> sorted = new ArrayList<>(artifacts);
        sorted.sort(Comparator.comparing(Artifact::getId));

        getLog().info("Runtime artifacts: " + sorted.size());

        for (Artifact artifact : sorted) {
            File file = artifact.getFile();

            if (file == null || !file.exists()) {
                throw new MojoExecutionException(
                        "Resolved artifact has no usable file: "
                        + artifact.getId());
            }

            getLog().info(
                    "FILE " + artifact.getGroupId()
                    + ":" + artifact.getArtifactId()
                    + ":" + artifact.getVersion()
                    + " scope=" + artifact.getScope()
                    + " => " + file.getAbsolutePath()
            );
        }
    }
}
```

**Những lựa chọn kỹ thuật có chủ đích:**

- Goal yêu cầu `RUNTIME`, nên Maven chuẩn bị **compile + runtime** dependencies, không chủ động kéo test-only artifacts.
- `Artifact#getFile()` có ý nghĩa tại đây vì goal thực sự cần tham chiếu file/directory.
- Kiểm `file != null` và `file.exists()` làm lỗi rõ hơn nếu artifact đặc biệt, repo hoặc reactor output không như kỳ vọng.
- Không dùng `file.isFile()` vì trong một số reactor/build situations đường dẫn artifact đại diện một thư mục output hợp lệ. Nếu mục tiêu thực sự yêu cầu **JAR archive file**, plugin cần kiểm `type/extension` và `isFile()` theo use case cụ thể.
- `file.getAbsolutePath()` phụ thuộc OS, local repository và working directory. Bài không đưa một stdout “chính xác” giả cho các đường dẫn này.
- Sorting giúp log dễ đối chiếu giữa hai lần chạy trong cùng resolution state.
- Nếu Maven không resolve được artifact, thông thường lỗi sẽ xảy ra **trước** `execute()`. Đoạn kiểm trong code chỉ là defense-in-depth, không thay yêu cầu annotation.

### 5.5. Hai goal trong một plugin nhưng có yêu cầu khác nhau

Một Maven plugin là một artifact chứa nhiều Mojos. Mỗi Mojo có thể tự chọn:

```text
scope-inspector-maven-plugin:1.0.0
    |
    +-- collect-graph
    |      requiresDependencyCollection = TEST
    |
    +-- list-runtime-files
           requiresDependencyResolution = RUNTIME
```

Không cần ép cả plugin dùng chung `TEST` resolution. **Maven đọc metadata của goal được gọi**, vì vậy goal chỉ cần tọa độ không gây yêu cầu tải binary của goal khác.

## 6. Project consumer: dependencies có compile, runtime và test

### 6.1. pom.xml consumer đầy đủ

File `scope-inspector-consumer/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example.training</groupId>
    <artifactId>scope-inspector-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>

        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.13</version>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
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

**Ba loại dependencies để so sánh:**

- `commons-lang3:3.14.0` mặc định **compile**. Nó thuộc cả RUNTIME classpath set.
- `slf4j-api:2.0.13` ghi `<scope>runtime</scope>`. Nó thuộc `ResolutionScope.RUNTIME` nhưng không thuộc `COMPILE`.
- `junit-jupiter:5.11.4` ghi `test`. Nó xuất hiện trong tập `TEST` collection, cùng transitive test dependencies, nhưng **không thuộc runtime-only resolution**.

Đây là ví dụ phân loại, không yêu cầu app gọi Commons Lang/SLF4J APIs để minh họa scope. Các artifacts vẫn được Maven xử lý dựa trên khai báo POM. Với project production, nên loại dependency không sử dụng để giảm supply-chain/size, nhưng ở đây chúng được đưa vào có chủ đích cho bài thực hành.

### 6.2. ConsumerMain.java

File `scope-inspector-consumer/src/main/java/dev/example/consumer/ConsumerMain.java`:

```java
package dev.example.consumer;

import java.util.Locale;

public final class ConsumerMain {

    private ConsumerMain() {
    }

    public static String format(String value) {
        if (value == null || value.isBlank()) {
            return "scope=none";
        }
        return "scope=" + value.strip().toLowerCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        System.out.println(format(" Runtime "));
    }
}
```

Chương trình chỉ dùng Java standard library; nhờ đó lệnh chạy `java -cp target/classes` không cần liệt kê dependency JAR ở CLI. `Locale.ROOT` giúp output nhất quán giữa các hệ điều hành. Tính đúng của chương trình **không phụ thuộc** thành công của plugin goals — chúng là bước Maven analysis riêng.

### 6.3. ConsumerMainTest.java

File `scope-inspector-consumer/src/test/java/dev/example/consumer/ConsumerMainTest.java`:

```java
package dev.example.consumer;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class ConsumerMainTest {

    @Test
    void formatsText() {
        assertEquals("scope=runtime",
                ConsumerMain.format(" Runtime "));
    }

    @Test
    void handlesBlank() {
        assertEquals("scope=none",
                ConsumerMain.format("   "));
    }

    @Test
    void handlesNull() {
        assertEquals("scope=none",
                ConsumerMain.format(null));
    }
}
```

Có **3 JUnit Jupiter tests**. `maven-surefire-plugin:3.5.2` phát hiện test class `*Test` theo naming convention. Nếu Maven test log nói “Tests run: 0” thì không được coi là đúng kết quả kỳ vọng.

## 7. Build, tạo descriptor, install plugin và gọi hai goal

### 7.1. Kiểm môi trường

Chạy:

```bash
mvn -version
java -version
```

Ví dụ yêu cầu Maven **3.9.16** và Java **17+**. Source plugin đã được compile để nhắm Java 17; `@Mojo` annotations/Plugin Tools 3.16.0 và Maven API 3.9.16 là các dependencies có version xác định. Nếu chỉ có Maven 3.8, bạn không ở môi trường đã kiểm cho bài và có thể không dùng được mọi API/feature.

### 7.2. Build và install plugin trong local Maven repository

Từ thư mục `scope-inspector-maven-plugin`:

```bash
mvn -B -ntp clean install
```

Maven sẽ:
1. Tải dependencies của **plugin project** theo POM plugin.
2. Biên dịch hai classes Mojo.
3. Dùng `maven-plugin-plugin` tạo `META-INF/maven/plugin.xml`.
4. Đóng gói `scope-inspector-maven-plugin-1.0.0.jar`.
5. Install JAR/POM/metadata vào local repository.

Đây là lệnh local **không publish Maven Central**. `mvn install` là cần thiết cho consumer độc lập tìm plugin theo coordinates đã ghim.

Kiểm JAR có descriptor:

```bash
jar tf target/scope-inspector-maven-plugin-1.0.0.jar
```

Trong danh sách phải có:

```text
META-INF/maven/plugin.xml
```

Ngoài ra có classes:

```text
dev/example/training/plugin/CollectGraphMojo.class
dev/example/training/plugin/ListRuntimeFilesMojo.class
```

Đây là các **dòng có thể xuất hiện trong output của `jar tf`**, không phải toàn bộ output chính xác: thứ tự entry, directory entries và metadata khác phụ thuộc JAR build.

### 7.3. Build consumer độc lập

Từ thư mục `scope-inspector-consumer`:

```bash
mvn -B -ntp clean verify
java -cp target/classes dev.example.consumer.ConsumerMain
```

Với Maven Central/mirror truy cập được, kết quả Maven test kỳ vọng được tóm tắt:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là phần tóm tắt, **không phải toàn bộ Maven console log**.

**Stdout chính xác** của ứng dụng Java:

```text
scope=runtime
```

Nếu phải build offline, các dependencies/plugins phải có sẵn trong local repository. `mvn -o` có thể thất bại vì artifact POM/JAR chưa từng được tải; lỗi offline không tự chứng minh annotation sai.

### 7.4. Gọi collect-graph

Trong consumer directory:

```bash
mvn -B -ntp dev.example.training:scope-inspector-maven-plugin:1.0.0:collect-graph
```

Maven sẽ kiểm descriptor và chuẩn bị **dependency collection cho TEST scope**, rồi gọi `CollectGraphMojo.execute()`.

Đầu ra **minh họa, chỉ trích các dòng đại diện**:

```text
[INFO] COORD org.apache.commons:commons-lang3:3.14.0 scope=compile
[INFO] COORD org.junit.jupiter:junit-jupiter:5.11.4 scope=test
[INFO] COORD org.slf4j:slf4j-api:2.0.13 scope=runtime
```

Ngoài ba dòng này còn có thể có **transitive JUnit/artifact entries**, và thứ tự log thật được sort bằng `Artifact#getId()`, không nhất thiết trùng thứ tự ba dòng minh họa. Không hard-code “Collected artifacts: 3” vì số lượng lớn hơn do transitive graph. Kết luận cần kiểm là **TEST collection bao gồm test dependencies** nhưng không phải tải binary JAR chỉ vì annotation này.

### 7.5. Gọi list-runtime-files

```bash
mvn -B -ntp dev.example.training:scope-inspector-maven-plugin:1.0.0:list-runtime-files
```

Maven chuẩn bị artifacts trong **RUNTIME scope** rồi gọi `ListRuntimeFilesMojo.execute()`.

Kết quả điển hình có các dòng mang cấu trúc:

```text
[INFO] FILE org.apache.commons:commons-lang3:3.14.0 scope=compile => .../commons-lang3-3.14.0.jar
[INFO] FILE org.slf4j:slf4j-api:2.0.13 scope=runtime => .../slf4j-api-2.0.13.jar
```

Đây là **placeholder đường dẫn** và chỉ là ví dụ dòng log, không phải stdout nguyên văn. Đường dẫn local Maven repository thay đổi theo OS/username/mirror, và log có thể còn nhiều entries tùy dependency resolution. **JUnit test-only artifact không được yêu cầu bởi RUNTIME scope**, dù có thể đã được tải trước đó khi chạy `verify`.

### 7.6. So sánh trực tiếp collection và resolution

Trong hai lần chạy:
- `collect-graph` in tọa độ, **không dùng file paths**;
- `list-runtime-files` in file paths và yêu cầu file tồn tại;
- `collect-graph` dùng `TEST`, nên có thể liệt kê JUnit;
- `list-runtime-files` dùng `RUNTIME`, nên không yêu cầu JUnit test-only;
- Nếu trước đó chạy consumer `verify`, các JAR test đã được tải rồi, vì vậy **không lấy số HTTP requests ở lần gọi sau làm chứng minh** về bản chất collection. Thực hiện quan sát trên local repository cách ly nếu cần đo network, nhưng tránh xóa cache chính.

## 8. Kiểm descriptor: Annotation đã được Maven ghi ra sao?

### 8.1. Vì sao cần plugin.xml?

Maven cần biết goal requirements **trước khi thực thi code**. JAR plugin chứa descriptor tại:

```text
META-INF/maven/plugin.xml
```

Maven Plugin Plugin sinh descriptor trong `process-classes` của packaging `maven-plugin`, rồi bundle nó vào JAR. Vì thế sửa annotation Java nhưng **không rebuild/install plugin** sẽ khiến consumer tiếp tục dùng descriptor cũ.

### 8.2. Đọc descriptor từ JAR

Có thể giải nén JAR vào một directory tạm có kiểm soát rồi mở `META-INF/maven/plugin.xml`, hoặc dùng lệnh Maven Help Plugin để xem goal metadata. Ví dụ trong consumer:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.1:describe -Dplugin=dev.example.training:scope-inspector-maven-plugin:1.0.0 -Dgoal=collect-graph -Ddetail
```

`maven-help-plugin:describe` giúp xem yêu cầu goal và parameters từ plugin metadata. Bạn cũng có thể đổi `-Dgoal=list-runtime-files` để đối chiếu.

### 8.3. Descriptor fragment mong đợi

**Mẫu dưới đây chỉ là fragment** của `plugin.xml`, không phải descriptor đầy đủ:

```xml
<mojo>
    <goal>collect-graph</goal>
    <requiresDependencyCollection>test</requiresDependencyCollection>
    <!-- other generated elements -->
</mojo>
```

Với goal thứ hai:

```xml
<mojo>
    <goal>list-runtime-files</goal>
    <requiresDependencyResolution>runtime</requiresDependencyResolution>
    <!-- other generated elements -->
</mojo>
```

Sự hiện diện của đúng element/value mới là điều cần kiểm; descriptor có nhiều trường khác, và một số trường không yêu cầu có thể vắng mặt. Không tự chèn fragment này bằng tay vào plugin JAR để “sửa” annotation; hãy sửa source, build/install và kiểm artifact được dùng thật.

### 8.4. Xem effective plugin version

Lệnh gọi full coordinates:

```bash
mvn dev.example.training:scope-inspector-maven-plugin:1.0.0:collect-graph
```

đảm bảo dùng version plugin `1.0.0`, thay vì một bản khác bị Maven plugin prefix/version resolution chọn. Khi debug “đã sửa @Mojo nhưng behavior không đổi”, kiểm:
- đang chạy đúng version/canonical GAV;
- plugin JAR được install lại sau sửa;
- local repository không chứa duplicate/stale version;
- consumer Maven đang dùng đúng `settings.xml`/repository;
- không có plugin version override ở POM/parent;
- descriptor trong **đúng JAR** chứa attributes kỳ vọng.

## 9. Mối quan hệ với lifecycle phase

### 9.1. Phân giải xảy ra trước execute()

Thứ tự khái quát:

```text
User invokes Maven goal
        |
        v
Maven resolves the plugin and reads plugin.xml
        |
        v
Reads goal's requiresDependencyCollection/Resolution
        |
        v
Prepare project dependencies for declared scope
        |
        +--- Failure (repo/missing artifact/network)
        |       |
        |       v
        |    BUILD FAILURE before execute()
        |
        v
Configure/inject Mojo @Parameter fields
        |
        v
Call execute()
```

Đó là lý do một goal có thể **không in được log đầu tiên trong execute()** khi Maven thất bại phân giải dependency. Nếu muốn xử lý trường hợp missing JAR “mềm” bên trong goal, không thể chỉ `catch` bên trong `execute()` khi lỗi xảy ra **trước lúc method được gọi**.

Nếu use case cần danh sách unresolved coordinates, chọn collection-only hoặc gọi Maven Resolver APIs thích hợp với error handling riêng, không ép full resolution bằng annotation.

### 9.2. Early phase và reactor modules chưa package

Giả sử reactor:

```text
root/
├── common/
├── library/ (depends on common)
└── app/     (depends on library)
```

Một goal yêu cầu `ResolutionScope.TEST` ở `validate` hoặc `generate-sources` có thể đòi các JAR của sibling module **chưa được compile/package**. Maven Dependency Plugin tài liệu hóa tình huống này: `dependency:resolve` có thể thất bại khi module chưa build, còn `dependency:collect` chỉ cần POM information nên hữu ích hơn ở phase sớm.

Giải pháp tùy trường hợp:
- Goal chỉ cần coordinates → `requiresDependencyCollection`.
- Goal cần JAR → chạy sau lifecycle phase đã tạo/resolve artifacts phù hợp, ví dụ `package` rồi goal.
- Thiết kế Maven reactor build order/dependencies rõ ràng.
- Không bind goal có full resolution quá sớm nếu outputs chưa tồn tại.
- Nếu có vòng phụ thuộc modules, sửa graph; không chữa bằng cách đổi scope tùy tiện.

### 9.3. @Mojo.defaultPhase không buộc chạy tự động

Ví dụ:

```java
@Mojo(
    name = "audit",
    defaultPhase = LifecyclePhase.VERIFY,
    requiresDependencyResolution = ResolutionScope.RUNTIME
)
```

Nếu consumer không bind plugin goal vào execution, `mvn verify` không tự gọi `audit` chỉ vì defaultPhase đã đặt. Default phase giúp một số plugin configurations/descriptor mechanisms xác định phase khi execution đã có. Cần chỉ định `<executions>` trong POM consumer khi muốn tự chạy mỗi build.

### 9.4. requiresProject khác dependency requirements

`@Mojo(requiresProject = true)` (mặc định của goal) nói plugin cần một MavenProject từ POM. Nó **không đồng nghĩa** project dependencies được resolve. Ngược lại, goal không cần project có thể chạy ngoài project directory, nhưng không thể truy cập `MavenProject.getArtifacts()` như khi đang build một project thực.

Nếu goal phân tích dependency graph, nên giữ `requiresProject=true` (mặc định) và khai collection/resolution rõ ràng.

## 10. MavenProject, Artifact và classpath APIs

### 10.1. getArtifacts()

Trong Maven 3:

```java
Set<Artifact> artifacts = project.getArtifacts();
```

được dùng để lấy các dependency artifacts tương ứng với kết quả Maven đã chuẩn bị cho project và execution context, thường bao gồm dependencies bắc cầu. **Đừng dùng nó như một Maven Resolver raw dependency tree đầy đủ**: candidates bị dependency mediation loại bỏ có thể không còn ở tập cuối.

Với collection-only goal, ưu tiên đọc `groupId`, `artifactId`, `version`, `scope`, `type`, `classifier`. Không giả định `getFile()` luôn khác null.

### 10.2. getDependencyArtifacts() và direct declarations

`MavenProject` cũng có `getDependencyArtifacts()` liên quan tập dependency artifacts do project model khai báo trực tiếp. Trong Maven 3, API/lifecycle có những trạng thái lazy loading; nếu cần phân biệt **direct declarations** và resolved transitive dependencies thật chính xác, hãy xác minh Maven version/phase và thử nghiệm với project nhiều mức.

**Không dùng `project.getDependencyArtifacts()` thay `getArtifacts()` rồi tuyên bố tự nhiên thu được mọi transitive artifacts**. Muốn biết nguồn/đường đi của một dependency, dùng Maven Resolver dependency graph APIs hoặc kiểm `mvn dependency:tree`.

### 10.3. Classpath elements

MavenProject còn có các phương thức như:
- `getCompileClasspathElements()`;
- `getRuntimeClasspathElements()`;
- `getTestClasspathElements()`.

Những API này trả danh sách path dùng cho classpath theo mục đích riêng, có thể bao gồm output directories của project. Cần goal requirements phù hợp với các paths nó muốn tiêu thụ. **Artifact#getFile() và classpath elements không phải một danh sách đồng nhất**: classpath thường có cả output directory của chính project, trong khi `project.getArtifacts()` chỉ tập dependency artifacts.

### 10.4. Plugin dependencies không phải project dependencies

Trong plugin POM ta khai:

```xml
<dependency>
    <groupId>org.apache.maven</groupId>
    <artifactId>maven-core</artifactId>
    <version>${maven-api.version}</version>
    <scope>provided</scope>
</dependency>
```

Đây là dependency của **Maven plugin project** để compile Mojo. Nó không làm consumer tự có Maven Core trong runtime dependency graph.

Ngược lại, consumer POM có `commons-lang3`, `slf4j-api`, `junit-jupiter`. Hai `@Mojo` annotations điều khiển Maven chuẩn bị **consumer project dependencies**, không phải “tự tải dependency của plugin”.

Plugin dependencies được Maven resolve để nạp plugin class realm; đó là **một hoạt động khác** với project dependency collection/resolution của goal.

### 10.5. requiresDependencyResolution không thêm dependency vào project

Nếu consumer POM không khai SLF4J, việc đặt `ResolutionScope.RUNTIME` **không tự sinh SLF4J vào graph**. Annotation chỉ nói “hãy chuẩn bị những dependency **đang có** thuộc scope này”. Nó cũng không chuyển `test` dependency sang `runtime`, và không sửa direct/transitive relationships.

## 11. Khi nào dùng NONE, COMPILE, RUNTIME hay TEST?

### 11.1. Chỉ đọc MavenProject metadata

Một goal in project version hoặc build directory:

```java
@Mojo(name = "print-version")
```

Không cần collection/resolution. Đó là `NONE` mặc định. Việc chọn `TEST` chỉ làm Maven tải thêm dependencies để rồi không dùng.

### 11.2. Tạo dependency inventory/licensing theo tọa độ

```java
@Mojo(
    name = "inventory",
    requiresDependencyCollection = ResolutionScope.TEST
)
```

Phù hợp khi bạn muốn biết coordinate names, scope, versions mà không cần kiểm bytes JAR. Nhưng một license checker thực tế có thể phải đọc artifact POM/license metadata hoặc JAR license files; cần phân tích **đầu vào thật của goal** để quyết định collection đã đủ chưa.

### 11.3. Quét bytecode phục vụ production runtime

```java
@Mojo(
    name = "scan-runtime-classes",
    requiresDependencyResolution = ResolutionScope.RUNTIME
)
```

Nếu goal cần mở file JAR runtime, chọn `RUNTIME`. Nếu nó muốn quét test libraries luôn, chuyển sang `TEST` và chấp nhận download rộng hơn.

### 11.4. Compiler/annotation processing

Một goal phân tích compile-only/provided dependencies có thể cần `COMPILE`. Nếu nó dùng cả runtime-only jars, cân nhắc `COMPILE_PLUS_RUNTIME` trong Maven 3. Sự khác nhau dựa vào classpath sets thực, không dựa tên goal.

### 11.5. Copy mọi dependency JAR vào một thư mục

Nếu goal cần cả test artifacts, chọn full `TEST` resolution. Tuy nhiên không dùng `TEST` khi chỉ muốn deploy production runtime JARs, vì test-only code không thuộc runtime distribution thông thường.

### 11.6. Sử dụng cả collection và resolution

Tập yêu cầu chung có thể được khai bằng cả hai attributes cho cùng Mojo, nhưng **không nên lặp cả hai một cách máy móc**. Với một goal chỉ dùng resolved files của phạm vi nhất định, `requiresDependencyResolution` thường diễn đạt trực tiếp nhu cầu và resolution cũng dựa trên graph. Nếu goal có một tập collection khác với tập files muốn resolve, phải xác minh cách Maven version thực thi hai thuộc tính và `MavenProject` được populate, rồi viết integration tests. Đừng suy rằng Maven hợp nhất scopes theo một phép toán tùy ý mà không kiểm.

## 12. Lỗi thường gặp khi khai báo scope sai

### 12.1. Goal chỉ khai NONE nhưng đọc getArtifacts()

Nếu goal không yêu cầu collection/resolution, tập `project.getArtifacts()` có thể chưa được chuẩn bị đủ tùy context. Một run đi sau lifecycle phase khác có thể tình cờ hoạt động, trong khi gọi goal trực tiếp từ đầu lại không. **Đừng phụ thuộc vào thứ tự may mắn**: khai needs bằng annotation.

### 12.2. Collection-only nhưng mở file JAR

Code sai ý nghĩa:

```java
@Mojo(
    name = "open-jar",
    requiresDependencyCollection = ResolutionScope.TEST
)
public class OpenJarMojo extends AbstractMojo {
    // execute() assumes every artifact.getFile() is non-null
}
```

Đoạn trên là **anti-pattern fragment**, không phải class hoàn chỉnh. Collection cung cấp tọa độ, không bảo đảm files. Nếu goal thực sự đọc bytes, đổi sang resolution requirement tương ứng.

### 12.3. Resolving TEST mọi lúc

Một plugin chỉ cần compile classpath nhưng dùng `TEST` có thể làm download JUnit/Mockito/Testcontainers hoặc dependencies lớn không cần thiết. CI sẽ chậm và có thể fail khi test repository offline dù production artifacts đã có. Đổi xuống `COMPILE` hoặc `RUNTIME` nếu đáp ứng use case, rồi kiểm actual graph và tests.

### 12.4. Full resolution ở validate khi sibling artifacts chưa tồn tại

Maven báo không tìm được reactor artifact khi plugin chạy quá sớm. **Collection-only** phù hợp với goal không cần JAR; nếu phải inspect JAR thì chuyển execution phase sang khi outputs đã tạo và modules xây theo đúng graph.

### 12.5. Tưởng phải dùng @Component để nhận MavenProject

Để lấy MavenProject trong Maven 3 Mojo, pattern phổ biến:

```java
@Parameter(
    defaultValue = "${project}",
    readonly = true,
    required = true
)
private MavenProject project;
```

`@Parameter` với expression `${project}` cho Maven Plugin Manager inject MavenProject vào goal. `@Component` dùng để inject service/role khác, không nên đổi lung tung. Khi chuyển sang Maven 4 new plugin APIs/DI, cần kiểm migration docs.

### 12.6. Bỏ scope provided cho Maven APIs

Nếu một plugin POM đóng gói một Maven Core version không tương thích vào plugin class realm, có thể gây classloading/version conflicts. Khai Maven API/Core và annotations theo hướng dẫn plugin authoring, thường `provided`, rồi test trên các Maven versions muốn hỗ trợ.

### 12.7. Chạy plugin prefix nhưng Maven chọn sai plugin

Lệnh `mvn scope-inspector:collect-graph` yêu cầu prefix mapping có thể không được cấu hình hoặc Maven chọn version khác. Trong tutorial dùng full coordinates:

```bash
mvn dev.example.training:scope-inspector-maven-plugin:1.0.0:collect-graph
```

Nếu muốn short prefix, cần POM/pluginGroups/metadata phù hợp. **Tên artifact tuân convention không tự bảo đảm prefix resolution**.

## 13. Phân giải dependency chịu ảnh hưởng của POM, Maven Resolver và repository

### 13.1. Dependency mediation

Maven có thể gặp nhiều versions của cùng một artifact trong transitive graph. Dependency mediation (nearest definition, tie handling) quyết định version được chọn, và `dependencyManagement` có thể điều khiển versions. Hai goal của bài sẽ thấy **artifacts Maven đã chọn**, không phải tất cả candidate versions.

Đừng tự “sửa” selected version trong plugin log rồi khẳng định đó là artifact đang dùng. Nếu cần phân tích conflicts, kết hợp `mvn dependency:tree` và Maven Resolver graph details.

### 13.2. Optional và exclusions

`<optional>true</optional>` và `<exclusions>` trên đường phụ thuộc có thể làm một transitive dependency không xuất hiện trong graph. `requiresDependencyResolution = TEST` **không buộc Maven bỏ qua exclusions**. Nó chỉ yêu cầu files cho những artifacts còn lại trong phạm vi đã chọn.

### 13.3. Repositories, mirrors và offline

Cả collection và resolution có thể cần:
- POM descriptors và metadata;
- repository mirrors từ `settings.xml`;
- authentication cho private repository;
- Maven Resolver cache;
- plugin artifact và dependencies của plugin.

Trong offline mode (`mvn -o`), collection có thể fail nếu transitive POM còn thiếu dù người dùng tưởng “không tải JAR nên chạy offline”. Resolution yêu cầu thêm binaries, nên càng dễ fail nếu cache lạnh.

### 13.4. Snapshot và dynamic versions

SNAPSHOT metadata hoặc version ranges có thể làm dependency graph khác qua thời gian. Khi troubleshoot goal:
- ghi Maven/JDK/plugin versions;
- kiểm `settings.xml`/mirror;
- so `mvn dependency:tree`;
- xem `-U`/updatePolicy nếu cần refresh SNAPSHOT metadata;
- tránh release artifacts dựa mutable dependencies thiếu quản trị;
- không thay tọa độ dependency chỉ để né download error mà chưa biết root cause.

## 14. Tối ưu hiệu năng và tính đúng

### 14.1. Không giải quyết quá rộng

Một goal có thể in một dòng `project.getVersion()` mà khai `ResolutionScope.TEST`. Maven tải dependencies và validate repositories **trước khi** in dòng đó, làm CLI chậm hoặc thất bại không liên quan. Sửa annotation về `NONE` sẽ phù hợp hơn.

### 14.2. Collection tiết kiệm gì?

Với local Maven cache lạnh:
- Collection đọc POM/metadata để tính graph.
- Resolution đọc POM/metadata **và phải có binary JAR files** cho scope.
- Nếu graph rất lớn, collection thường ít bytes chuyển hơn.

Nhưng collection vẫn có chi phí graph mediation, transitive metadata I/O, HTTP nếu POM chưa cache. Đừng ghi benchmark định lượng kiểu “nhanh hơn 70%” khi chưa đo. Với cache đã warm, khác biệt có thể rất nhỏ.

### 14.3. Lựa chọn scope tương ứng

`RUNTIME` sẽ thường ít dependencies hơn `TEST`. Không có quy tắc lúc nào cũng ít hơn vì graph và scopes thực thay đổi. Đo actual counts/downloads/CI timing trước và sau khi sửa annotation; đừng đo chỉ một build cold download.

### 14.4. Tránh gọi Resolver APIs thừa

Nếu Maven đã đáp ứng annotation requirement và goal chỉ cần selected artifacts, sử dụng dữ liệu MavenProject được chuẩn bị. Đừng tự làm một vòng remote resolution riêng cho cùng dependencies nếu không có lý do. Resolver APIs cấp thấp hữu ích khi cần alternate repositories, classifiers, dependency graph conflict analysis hoặc custom error handling — nhưng phải có tests về version mediation, scopes và error behaviors.

### 14.5. Artifact files là dữ liệu không hoàn toàn tin cậy

Một goal phân giải JAR files rồi mở nội dung của chúng phải coi dependency content là **input không tin cậy**:
- kiểm archive paths, zip slip khi extract;
- giới hạn kích thước/decompression;
- không tự chạy code của dependency chỉ để “scan” nếu không cần;
- kiểm checksum/signature/provenance theo security policy;
- không đọc tài nguyên ngoài scope hoặc secrets của CI;
- không log private repository tokens.

Dependency resolution tự nó không bảo đảm artifacts không có malicious code.

## 15. Testing Maven plugin theo đúng goal requirement

### 15.1. Tests chỉ cho logic chưa đủ

Một unit test trực tiếp gọi `new CollectGraphMojo().execute()` có thể không có MavenProject injection/descriptor behavior, vì `@Mojo` được Maven sử dụng để chuẩn bị execution context. Nếu chỉ mock field, test không chứng minh Maven đã thu thập/resolved dependencies thật trước khi chạy.

Cần **integration test** với một consumer POM và Maven runtime mục tiêu.

### 15.2. Test matrix tối thiểu

| Case | Setup | Kỳ vọng |
| --- | --- | --- |
| Collection TEST | Consumer có compile/runtime/test dependencies | Có tọa độ test dependency |
| Resolution RUNTIME | Consumer có commons, slf4j, JUnit | Có file compile/runtime, không yêu cầu test-only |
| Missing artifact binary | Artifact chưa có và repo không truy cập | Resolution error trước execute |
| POM metadata thiếu | Offline và cache chưa có transitive POM | Collection cũng có thể fail |
| Goal NONE | Không cần dependency metadata | Không buộc resolve project deps |
| Maven profiles | Activate profile thêm dependency | Graph tương ứng thay |
| Exclusion | Exclude một transitive artifact | Artifact bị loại khỏi selected set |
| Reactor early phase | Goal bind trước package sibling | Có thể fail full resolution; collection phù hợp hơn |
| Updated plugin version | Rebuild/refresh local plugin JAR | Descriptor mới có đúng requirement |
| Parallel reactor | `-T 2` với plugin state | Không shared mutable state hoặc file race |

### 15.3. Dùng Maven Invoker Plugin cho production plugin

Apache Maven Plugin Testing có nhiều chiến lược; trong dự án thật có thể dùng Maven Invoker Plugin hoặc Maven Plugin Testing Harness để thực thi một số sample projects và assert logs/artifacts. Bài này cho **hai project tách rời** để người học chạy CLI và quan sát. Không có test automation cho plugin descriptor trong POM mẫu; muốn khẳng định hỗ trợ nhiều Maven versions cần CI integration matrix.

### 15.4. Assert những gì trong integration test?

Với plugin thật:
- Descriptor có `requiresDependencyCollection=test` ở collect goal.
- Descriptor có `requiresDependencyResolution=runtime` ở file goal.
- `collect-graph` không yêu cầu artifact files và log test-only coordinate.
- `list-runtime-files` có runtime artifact paths hợp lệ, không yêu cầu test-only files.
- Build không chạy lại plugin cũ.
- Lỗi thiếu artifact được phân loại đúng ở tầng Maven dependency resolution.
- Output và log không chứa tokens/secrets.
- Reactor compatibility được test nếu plugin khai hỗ trợ reactor.

## 16. Troubleshooting: goal không thấy dependency hoặc Maven fail

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `getArtifacts()` trống khi gọi goal trực tiếp | Chưa khai collection/resolution | Đặt `@Mojo` requirement phù hợp |
| `Artifact#getFile() == null` | Chỉ collection hoặc chưa resolve file | Dùng requiresDependencyResolution nếu cần bytes |
| Không thấy JUnit ở goal RUNTIME | JUnit thuộc test scope | Nếu cần test files, chọn TEST |
| Goal TEST kéo nhiều jars không dùng | Yêu cầu quá rộng | Hạ scope theo use case |
| Có coordinates nhưng không có JAR | Collection-only được thực thi đúng | Không coi là bug nếu goal không cần files |
| Download timeout trước khi log execute | Maven đang resolve dependencies trước goal | Kiểm repo/network/mirror |
| Offline collection fail | POM/metadata chưa cached | Làm warm metadata hoặc điều chỉnh offline policy |
| Offline resolution fail | Binary artifacts chưa cached | Pre-resolve binaries/kiểm repository |
| Reactor module artifact missing | Goal chạy trước khi module package | Chạy phase muộn hơn hoặc collection-only |
| Annotation đổi nhưng behavior không đổi | Plugin JAR/descriptor cũ | Rebuild/install và kiểm GAV/plugin.xml |
| Compiler error `MavenProject` not found | Thiếu maven-core dependency | Khai Maven Core API provided |
| Compiler error `@Mojo` not found | Thiếu maven-plugin-annotations | Khai Plugin Tools Annotations provided |
| Plugin không có goal | Descriptor không được tạo | `maven-plugin` packaging, plugin-plugin lifecycle |
| Could not find goal | Goal name sai hoặc stale descriptor | Kiểm `plugin.xml` và full coordinates |
| Wrong plugin selected by prefix | PluginGroups/metadata/versions | Gọi full plugin GAV:goal |
| `NullPointerException` trên `getFile()` | Assumption về file sai | Check null và khai resolution |
| Dep graph thiếu artifact đã exclude | POM exclusions/optional | Kiểm dependency:tree/POM graph |
| Conflict version khác kỳ vọng | Dependency mediation/management | effective POM + dependency:tree |
| Test CLI rất chậm | TEST resolution tải quá nhiều | Chọn phạm vi nhỏ nhất |
| Plugin classloading lỗi | Maven API/Core bundled xung đột | Scope provided, test Maven versions |
| Goal không chạy cùng verify | Chưa có execution binding | Cấu hình executions/phase |
| Multi-module chạy nhiều lần | Mojo per-module mặc định | Phân biệt aggregator vs per-module |
| `-T` báo plugin không thread-safe | Chưa khai/test threadSafe | Chỉ bật khi thực sự an toàn |
| Output chứa path khác ở Windows | Local cache/path khác | Đừng hard-code file absolute path |
| CI thiếu private repo credential | Mirror/settings server ID thiếu | Cấp read-only access phù hợp |
| Plugin resolve thành công nhưng scan fail | JAR malformed/too large | Validate archive content và bounded scan |

### 16.1. Runbook đề xuất

1. Xác nhận goal đang được gọi bằng **full GAV** của đúng plugin version.
2. Xem plugin JAR có `META-INF/maven/plugin.xml` hay không.
3. Đối chiếu descriptor requirement với source `@Mojo`.
4. Kiểm Maven runtime version/JDK và `settings.xml`.
5. Xem lỗi xảy ra **trước hay trong `execute()`**; thêm một log đầu execute nếu cần.
6. So `mvn dependency:tree` của consumer để biết selected dependencies.
7. So `@Mojo` scope với use case: chỉ tọa độ hay cần file bytes?
8. Với JAR missing, kiểm cache/repository/offline/mirror.
9. Với reactor, kiểm phase, dependency ordering và module outputs.
10. Sửa annotation hoặc lifecycle phase, rebuild/install plugin, chạy lại integration case.
11. Không chuyển lên TEST scope hoặc thêm repository credentials chỉ để “xử lý tạm” khi không cần.
12. Kiểm kết quả/hiệu năng sau sửa, bổ sung integration tests chống tái phát.

## 17. Bài tập tự đánh giá

**1.** Goal chỉ in `project.getVersion()` nên khai requirement nào? **NONE** (không cần collection/resolution).

**2.** Goal cần groupId/artifactId/version của toàn test graph nhưng không mở JAR? **`requiresDependencyCollection = ResolutionScope.TEST`**.

**3.** Goal mở JAR để kiểm bytecode runtime libraries? **`requiresDependencyResolution = ResolutionScope.RUNTIME`**.

**4.** Collection-only có luôn hoạt động offline không? **Không.** Có thể cần POM/metadata chưa cache.

**5.** Collection-only bảo đảm mọi `Artifact#getFile()` khác null? **Không.** File có thể null.

**6.** Resolution-only khi artifact chưa có và remote không truy cập được sẽ fail lúc nào? Thường **trước `execute()`**.

**7.** `ResolutionScope.COMPILE` có bao gồm runtime-only dependency không? **Không.**

**8.** `ResolutionScope.RUNTIME` bao gồm scope nào? **compile và runtime** trong Maven 3.

**9.** `ResolutionScope.TEST` có chỉ lấy test dependencies? **Không.** Nó gồm compile, provided, system, runtime và test.

**10.** Muốn cả compile/provided/system/runtime nhưng không test trong Maven 3 dùng gì? **COMPILE_PLUS_RUNTIME**.

**11.** Tác giả plugin có nên khai `TEST` cho mọi goal vì nó mạnh nhất? **Không.** Tốn tải và tăng failure surface.

**12.** Goal resolution có tự tạo dependency không nằm trong consumer POM? **Không.** Chỉ chuẩn bị selected dependencies đã có.

**13.** `maven-core` trong plugin POM có tự thêm vào runtime dependencies của consumer không? **Không.** Đó là plugin implementation dependency.

**14.** Cần MavenProject trong Mojo field khai thế nào? **`@Parameter(defaultValue = "${project}", readonly = true, required = true)`**.

**15.** `@Mojo(defaultPhase=VERIFY)` có khiến plugin tự chạy khi thêm vào POM? **Không** nếu chưa có execution binding phù hợp.

**16.** Descriptor được tạo ở đâu? **`META-INF/maven/plugin.xml`** trong plugin JAR.

**17.** Khi đổi annotation nhưng consumer vẫn dùng requirement cũ, kiểm gì? Plugin version/JAR/descriptor và lần `mvn install`.

**18.** `project.getArtifacts()` có chứa mọi candidates bị version conflict loại bỏ không? **Không được bảo đảm**; đó là selected/resolved set.

**19.** Maven Dependency Plugin có goal minh họa collection-only chính thức? **`dependency:collect`**.

**20.** Maven Dependency Plugin có goal full resolution? **`dependency:resolve`**.

**21.** Vì sao plugin:descriptor requirements được xử lý trước execute? Maven cần chuẩn bị dependency context theo metadata trước khi gọi Mojo.

**22.** Khi phải xử lý missing artifact như một thông tin thay vì fail ngay, có nên full resolve bằng annotation không? Có thể chọn collection-only hoặc Resolver APIs tùy use case, kèm error handling rõ.

**23.** `getRuntimeClasspathElements()` có giống hoàn toàn `getArtifacts()` không? **Không**; classpath có thể gồm output dir của project.

**24.** Một goal được khai threadSafe=true có nghĩa gì? Tác giả khẳng định an toàn trong Maven parallel build, phải kiểm thực tế state/file concurrency.

**25.** Khi thấy `BUILD FAILURE` trước log đầu goal, nên debug gì? Plugin descriptor, dependency resolution/repository, phase và Maven runtime.

## 18. Checklist cho người viết Maven plugin

- [ ] Xác định goal cần **tọa độ** hay **actual artifact files**.
- [ ] Khai `requiresDependencyCollection` khi chỉ cần graph metadata.
- [ ] Khai `requiresDependencyResolution` khi phải mở/copy/scan file.
- [ ] Dùng `ResolutionScope` nhỏ nhất đủ mục đích: NONE/COMPILE/RUNTIME/TEST hoặc combinations Maven 3.
- [ ] Không nhầm `TEST` với “chỉ test dependencies”.
- [ ] Không nhầm `requiresDependencyResolution` với `<scope>` của dependency trong POM.
- [ ] Không dùng annotation để cố thêm dependencies không khai báo.
- [ ] Plugin POM dùng `maven-plugin` packaging.
- [ ] Có `maven-plugin-annotations` và Maven API/Core dependencies scope provided.
- [ ] Maven Plugin Plugin sinh descriptor từ annotations.
- [ ] Kiểm chính xác `META-INF/maven/plugin.xml` sau build.
- [ ] Gọi plugin bằng full GAV để tránh wrong version.
- [ ] `MavenProject` được inject qua `@Parameter(defaultValue="${project}")`.
- [ ] Không giả định `project.getArtifacts()` có mọi graph candidates.
- [ ] Không dùng `getFile()` trong collection-only goal khi chưa kiểm trạng thái.
- [ ] Với goal cần JAR files, kiểm file null/exists và file type.
- [ ] Ghi rõ lifecycle execution binding và phase nếu muốn chạy tự động.
- [ ] Không bind full-resolution goal quá sớm khi reactor modules chưa package.
- [ ] Biết lỗi có thể xảy ra trước `execute()`.
- [ ] Kiểm offline/mirrors/private repositories, không tăng privileges tùy tiện.
- [ ] Test per-module/aggregator và parallel execution khi hỗ trợ multi-module.
- [ ] Có integration test cho scope, transitive graph và missing artifact scenarios.
- [ ] Không tốn TEST resolution nếu goal chỉ dùng runtime dependencies.
- [ ] Không đọc/execute JAR contents không tin cậy ngoài yêu cầu goal.
- [ ] Kiểm Java/Maven version compatibility trước publish plugin.
- [ ] Lưu tài liệu plugin goals và behavior của artifacts/missing files.

## 19. Kết luận

**Khai báo requirement đúng là một phần của hợp đồng giữa Maven Core và Maven plugin goal.** Goal chỉ cần dependency graph nên dùng `requiresDependencyCollection`; goal cần nội dung JAR nên dùng `requiresDependencyResolution`. `ResolutionScope` xác định **classpath set mà Maven cần chuẩn bị**, không phải bộ lọc tùy ý hay cơ chế thay đổi scope của consumer POM.

Khai **thiếu** khiến goal phụ thuộc tình cờ vào trạng thái những phases đã chạy và dễ gặp `getFile() == null`; khai **quá rộng** khiến build tải thêm artifacts, chậm hoặc fail sớm ở repository. Cách kiểm tốt nhất là viết plugin có descriptor rõ ràng, sử dụng consumer project thử với compile/runtime/test dependencies, đối chiếu `plugin.xml`, chạy goal trực tiếp và có integration tests cho trường hợp thiếu file/multi-module.

### Tài liệu chính thức

- [Apache Maven — Guide to Developing Java Plugins](https://maven.apache.org/guides/plugin/guide-java-plugin-development)
- [Apache Maven Plugin Tools — Using Java Annotations](https://maven.apache.org/plugin-tools/maven-plugin-plugin/examples/using-annotations.html)
- [Maven Plugin Tools 3.16.0 — Mojo Annotation Javadoc](https://maven.apache.org/plugin-tools/maven-plugin-annotations/apidocs/org/apache/maven/plugins/annotations/Mojo.html)
- [Maven Plugin Tools 3.16.0 — ResolutionScope](https://maven.apache.org/plugin-tools/maven-plugin-annotations/apidocs/org/apache/maven/plugins/annotations/ResolutionScope.html)
- [Maven Plugin Tools 3.16.0 — Parameter Annotation](https://maven.apache.org/plugin-tools/maven-plugin-annotations/apidocs/org/apache/maven/plugins/annotations/Parameter.html)
- [Apache Maven — Plugin Plugin Usage/Descriptor](https://maven.apache.org/plugin-tools/maven-plugin-plugin/usage.html)
- [Apache Maven — Mojo API Specification](https://maven.apache.org/developers/mojo-api-specification.html)
- [Apache Maven 3 — Plugin Descriptor Model](https://maven.apache.org/ref/3.9.12/maven-plugin-api/plugin.html)
- [Apache Maven Dependency Plugin — dependency:collect](https://maven.apache.org/plugins/maven-dependency-plugin/collect-mojo.html)
- [Apache Maven Dependency Plugin — dependency:resolve](https://maven.apache.org/plugins/maven-dependency-plugin/resolve-mojo.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
