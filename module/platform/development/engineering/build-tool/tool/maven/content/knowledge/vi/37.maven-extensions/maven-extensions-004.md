# Truy cập MavenProject, MavenSession và mô hình dự án khi mở rộng Maven

## 1. Mục tiêu bài học

Khi viết một Maven plugin tùy chỉnh, bạn thường cần biết **project nào đang được build**, version nào thực sự có hiệu lực sau khi kế thừa parent POM, build directory ở đâu, reactor có những module nào, người dùng truyền `-D` property gì và dependencies nào đã được Maven phân giải.

Maven 3 cung cấp hai đối tượng context quan trọng:

- **`org.apache.maven.project.MavenProject`**: đại diện cho một project/module đã được Maven dựng model. Nó có GAV, packaging, basedir, build settings, dependency declarations, properties, source roots và artifact state.
- **`org.apache.maven.execution.MavenSession`**: đại diện cho một lần thực thi Maven. Nó chứa danh sách project được chọn trong reactor, Maven execution goals, user properties, offline mode, settings và context dùng chung của invocation.

Bên cạnh đó, **`org.apache.maven.model.Model`** là cấu trúc POM. Không được nhầm một Model với resolved dependency artifacts hay toàn bộ MavenSession.

Sau bài này, người học có thể:

1. Viết một **Mojo** được Maven inject `MavenProject` và `MavenSession`.
2. Đọc project GAV, packaging, `basedir`, `build.directory`, properties và dependencies.
3. Phân biệt **original POM**, **effective model**, **resolved artifacts** và **reactor selection**.
4. Dùng `session.getProjects()`, `session.getTopLevelProject()`, `session.getUserProperties()`, `session.getGoals()` và `session.isOffline()` đúng chỗ.
5. Khai báo `@Mojo(requiresDependencyResolution = ResolutionScope.RUNTIME)` khi thật sự cần resolved dependencies.
6. Xây plugin Maven 3 chạy trên **Java 17**, cài vào Maven local repository rồi gọi goal từ một consumer project Java 17 có JUnit 5.
7. Hiểu `aggregator=true`, per-module execution, `-N`, `-pl`, `-am` và parallel thread safety.
8. Tránh sửa MavenProject/Session không chủ đích, log secrets hoặc nhầm Maven Core API với application dependency.

**Phạm vi tương thích:** ví dụ dùng **Maven 3.9.9**, Java 17 và Maven Plugin Tools **3.15.2** đã ghim để tái hiện. Đây không phải khẳng định phiên bản mới nhất. Maven 4 có API/plugin behavior khác: khi migrate cần đọc hướng dẫn riêng.

## 2. Vì sao không tự parse pom.xml khi viết plugin?

Một child POM có thể khai:

```xml
<parent>
    <groupId>dev.learning</groupId>
    <artifactId>build-parent</artifactId>
    <version>1.0.0</version>
</parent>
<artifactId>service</artifactId>
```

Child không nhất thiết tự khai `groupId` hoặc `version` cấp project. Nếu dùng XML parser đơn giản chỉ đọc local `<groupId>`/`<version>`, plugin có thể báo thiếu dữ liệu, dù Maven đã kế thừa hai giá trị từ parent.

Cách đúng trong Mojo:

```java
String gav = project.getGroupId() + ":"
        + project.getArtifactId() + ":"
        + project.getVersion();
```

Các getters trên `MavenProject` thể hiện project sau khi Maven model building đã xử lý inheritance/interpolation/profile activation phù hợp. Bạn không phải tự viết lại Maven Model Builder.

**Tuy nhiên:** project model được xây dựng không có nghĩa tất cả JAR dependencies đã được tải hoặc đã nằm trong resolved classpath.

## 3. Sơ đồ ngữ cảnh của Maven plugin

```text
Maven CLI: mvn -B -ntp verify -Dinspector.tag=classroom
                         |
                         v
                    MavenSession
          (one invocation; request, reactor, props)
                         |
         +---------------+---------------+
         |                               |
         v                               v
    MavenProject A                 MavenProject B
      (module A)                     (module B)
         |                               |
         v                               v
       Model                           Model
   (effective POM)                 (effective POM)
         |
         v
  Plugin goal / Mojo
         |
         v
  Resolved artifacts
  (only when requested)
```

- `MavenSession` không phải một POM khác, mà là context của invocation.
- `MavenProject` không phải toàn bộ workspace mà là project mà Mojo đang xử lý.
- `Model` là dữ liệu khai báo về dependencies/plugins/properties; không chứa toàn bộ downloaded artifact objects.
- Trong multi-module reactor, một goal có thể chạy trên từng project, còn session list có thể chứa những modules đã được chọn.

## 4. Các API Java cần biết

```java
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;
import org.apache.maven.project.MavenProject;
import org.apache.maven.execution.MavenSession;
import org.apache.maven.model.Model;
```

Đây là đoạn imports, chưa phải một class runnable. Một Maven plugin project thường khai:

- `maven-plugin-api` để có `AbstractMojo`, `MojoExecutionException`.
- `maven-core` để có `MavenProject`, `MavenSession`.
- `maven-model` để có `Model`.
- `maven-artifact` để có `Artifact` khi đọc resolved dependencies.
- `maven-plugin-annotations` để có `@Mojo`, `@Parameter`, `ResolutionScope`.
- `maven-plugin-plugin` để sinh plugin descriptor trong JAR.

Các Maven runtime APIs trong plugin project thường để **scope `provided`**, vì Maven runtime cung cấp classes đó. Không bundle một Maven Core khác vào plugin JAR một cách tùy tiện.

## 5. MavenProject cung cấp những gì?

API quan trọng của `MavenProject`:

| API | Mục đích |
| --- | --- |
| `getGroupId()`, `getArtifactId()`, `getVersion()` | Effective GAV hiện tại |
| `getPackaging()`, `getName()` | Packaging/name |
| `getFile()`, `getBasedir()` | File POM/basedir khi có |
| `getBuild()` | Build config như directory, finalName |
| `getProperties()` | Project model properties |
| `getModel()` | Model gắn với MavenProject |
| `getOriginalModel()` | Original model nếu có |
| `getDependencies()` | Model dependency declarations |
| `getDependencyManagement()` | Managed versions/dependencies |
| `getArtifacts()` | Resolved project artifacts, có thể lazy/scope-dependent |
| `getArtifact()` | Artifact đại diện cho chính project |
| `getModules()` | Module names khai trong model |
| `getParent()` | MavenProject của declared parent nếu có |
| `getCompileSourceRoots()` | Main source roots hiện tại |
| `getTestCompileSourceRoots()` | Test source roots hiện tại |

**Không coi** `MavenProject` là một global singleton. Nó gắn với module/execution context. Một aggregator root project và một child project là hai MavenProject khác nhau, dù chúng cùng được gọi từ một CLI command.

## 6. MavenSession cung cấp những gì?

`MavenSession` là context một Maven execution:

| API | Ý nghĩa thực tiễn |
| --- | --- |
| `getProjects()` | Selected reactor MavenProjects cho invocation |
| `getTopLevelProject()` | Top-level project của session |
| `getCurrentProject()` | Current project theo session execution context |
| `getGoals()` | Goals/phases trong execution request |
| `getUserProperties()` | User properties như `-Dinspector.tag=classroom` |
| `getSystemProperties()` | System properties của execution |
| `isOffline()` | Maven có đang chạy offline |
| `getExecutionRootDirectory()` | Root directory của execution request |
| `getSettings()` | Maven settings hiện có |
| `getRepositorySession()` | Maven Resolver context, nâng cao |
| `getRequest()` | MavenExecutionRequest |

**An toàn:** đừng log toàn bộ `getSettings()`, `getUserProperties()`, `getSystemProperties()` hoặc `getRequest()` trong CI. Chúng có thể mang token, usernames, internal repository URLs và thông tin nhạy cảm.

## 7. Inject MavenProject bằng @Parameter

Cách được Maven Plugin Tools tài liệu hóa cho Maven 3:

```java
@Parameter(defaultValue = "${project}", readonly = true, required = true)
private MavenProject project;
```

- `defaultValue="${project}"` dùng Maven Plugin Parameter Expression Evaluator để inject object MavenProject đang được dùng.
- `readonly=true` cho biết parameter không nên bị user cấu hình tùy ý qua POM.
- `required=true` để fail configuration khi context bắt buộc không có.
- Nên khai `@Mojo(requiresProject = true)` cho goal cần đọc project model.

**Sai lầm:** tạo `new MavenProject()` trong `execute()` rồi nghĩ đó là project đang build. Object tự tạo không có model/session context Maven đã chuẩn bị.

## 8. Inject MavenSession

Tương tự:

```java
@Parameter(defaultValue = "${session}", readonly = true, required = true)
private MavenSession session;
```

Đây là cách lấy session context **do Maven runtime cấp**, không phải tự tạo.

Tài liệu Plugin Tools ở các phiên bản khác nhau từng sử dụng `@Component` cho session/project scoped objects trong Maven 3.2.5+, và tài liệu mới cũng đề cập JSR-330 hoặc `@Parameter` tùy API. Hãy chọn cơ chế được bản Maven + Plugin Tools đang hỗ trợ, đừng đặt nhiều annotation cạnh tranh lên cùng một field.

Bài lab này sử dụng **`@Parameter(defaultValue=...)`** minh bạch, với Maven 3.9.9 baseline.

## 9. Parameter project khác parameter cấu hình thường

```java
@Parameter(defaultValue = "${project}", readonly = true)
private MavenProject project;

@Parameter(property = "inspector.tag", defaultValue = "none")
private String tag;
```

- Field `project` nhận Maven context.
- Field `tag` nhận cấu hình do người dùng cung cấp, ví dụ `-Dinspector.tag=classroom`.
- `${project.version}` là expression trả version String; `${project}` là expression inject cả object.
- `property` dùng cho một plugin option cụ thể; không có nghĩa CLI `-D` tự thay đổi mọi field trong MavenProject.
- `readonly=true` là metadata cho configuration, không phải sandbox bảo mật.

Đừng hướng dẫn user truyền `-Dproject=...` để “thay MavenProject” hoặc tự override readonly context.

## 10. Effective model và original model

Ba cách đọc khác nhau:

```java
Model effective = project.getModel();
Model original = project.getOriginalModel();
String version = project.getVersion();
```

- `getModel()` trả model gắn với MavenProject đã được Maven dựng.
- `getOriginalModel()` cho original POM model nếu available. Có context original model **không có**; kiểm tra null.
- `getVersion()` trả version hiệu lực của MavenProject.
- Cả hai model chứa cấu trúc POM, **không** tự chứa toàn bộ resolved transitive dependency files.

Ví dụ original child POM chỉ có artifactId và parent. Effective version có thể được kế thừa từ parent, còn `getOriginalModel()` vẫn phản ánh khai báo gốc.

Không coi `getModel()` là một XML text nguyên gốc. Nếu muốn một báo cáo human-readable của POM hiệu lực, dùng Maven Help Plugin `effective-pom` hoặc Serialize Model một cách có chủ đích.

## 11. Original dependencies và effective model dependencies

```java
Model original = project.getOriginalModel();
Model effective = project.getModel();

if (original != null) {
    getLog().info("Original deps: " + original.getDependencies().size());
}
getLog().info("Model deps: " + effective.getDependencies().size());
```

**Cách hiểu:**

- `original.getDependencies()` phản ánh dependency declarations của original model.
- `effective.getDependencies()` phản ánh dependencies của effective project model (có thể đã nhận inheritance).
- Hai số không nhất thiết bằng nhau.
- Nếu project dùng BOM/dependencyManagement, managed versions có thể thay đổi mà không tăng số dependency declarations.
- Hai số này không tính toàn bộ transitive graph.

**Không sửa** `project.getModel().getDependencies()` như cách “điều chỉnh dependency resolution” trong một inspection Mojo. Maven đã dựng graph ở các giai đoạn phù hợp; mutation tùy tiện có thể làm state không nhất quán.

## 12. Project dependency vs resolved artifact

Maven Model có `org.apache.maven.model.Dependency`, tức là **khai báo dependency** với groupId/artifactId/version/scope/exclusions.

Maven artifact API có `org.apache.maven.artifact.Artifact`, biểu diễn artifact coordinates và khi đã resolve có thể chứa file/dữ liệu liên quan.

Khác biệt:

```java
int declared = project.getModel().getDependencies().size();

for (Artifact artifact : project.getArtifacts()) {
    getLog().info(artifact.getGroupId() + ":" + artifact.getArtifactId());
}
```

Đoạn này là **ý tưởng**, chưa có imports/class bao quanh. `getArtifacts()` có thể phụ thuộc lúc nào goal chạy, scopes cần thiết, và việc Maven đã resolve dependencies chưa.

Nếu Mojo **cần** resolved files, hãy khai `requiresDependencyResolution` trong `@Mojo`, không chỉ gọi `getArtifacts()` rồi hy vọng mọi thứ đã tải.

## 13. Chọn ResolutionScope phù hợp

Theo Maven Plugin Tools:

| Scope annotation | Phạm vi Maven chuẩn bị |
| --- | --- |
| `ResolutionScope.NONE` | Không yêu cầu dependency graph |
| `ResolutionScope.COMPILE` | Compile + provided/system theo semantics |
| `ResolutionScope.RUNTIME` | Compile + runtime dependencies |
| `ResolutionScope.TEST` | Compile + provided/system + runtime + test |
| `ResolutionScope.COMPILE_PLUS_RUNTIME` | Scope mở rộng cho Maven 3 |
| `ResolutionScope.RUNTIME_PLUS_SYSTEM` | Scope mở rộng cho Maven 3 |

Đối với goal chỉ in GAV/packaging, **không cần** `requiresDependencyResolution`. Đối với goal in resolved runtime dependencies, dùng `ResolutionScope.RUNTIME`. Nếu muốn inspect JUnit test classpath thì dùng `ResolutionScope.TEST`, nhưng chỉ khi thực sự cần.

Scope rộng hơn có thể khiến Maven tải nhiều artifacts hơn và tạo lỗi offline/mirror không cần thiết.

## 14. @Mojo có các thuộc tính gì?

```java
@Mojo(
    name = "inspect",
    defaultPhase = LifecyclePhase.VALIDATE,
    requiresProject = true,
    threadSafe = true
)
```

- `name`: goal name.
- `defaultPhase`: phase mặc định được mô tả trong descriptor.
- `requiresProject`: yêu cầu context project.
- `threadSafe`: tuyên bố plugin implementation an toàn với parallel reactor execution.
- `requiresDependencyResolution`: nếu cần Maven resolve artifacts trước goal.
- `aggregator`: liên quan goal tổng hợp reactor, nhưng không bảo đảm mọi invocation đều chạy đúng một lần trên mọi module trên disk.

**Quan trọng:** `defaultPhase=VALIDATE` không khiến goal tự chạy cùng mọi `mvn validate`. Phải **bind execution** vào lifecycle hoặc gọi goal trực tiếp.

## 15. Kiến trúc lab: plugin + consumer

Tạo hai Maven projects độc lập:

```text
maven-model-lab/
├── plugin/
│   ├── pom.xml
│   └── src/main/java/dev/learning/maven/inspect/
│       ├── InspectMojo.java
│       └── InspectDependenciesMojo.java
└── consumer/
    ├── pom.xml
    └── src/
        ├── main/java/dev/learning/example/DemoApp.java
        └── test/java/dev/learning/example/DemoAppTest.java
```

- `plugin`: packaging `maven-plugin`, cung cấp goals `inspect` và `inspect-deps`.
- `consumer`: JAR project Java 17 với Commons Lang compile dependency và JUnit test dependency.
- Build/install plugin trước vào local Maven repository.
- Chuyển sang consumer, gọi plugin bằng **fully-qualified goal** tránh prefix ambiguity.

Lab tách rời để không mắc vòng lặp khi consumer cần plugin đang được biên dịch cùng reactor.

## 16. Plugin POM đầy đủ (Java 17)

File `plugin/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.maven</groupId>
    <artifactId>project-inspector-maven-plugin</artifactId>
    <version>1.0.0</version>
    <packaging>maven-plugin</packaging>
    <name>Project Inspector Maven Plugin</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.api.version>3.9.9</maven.api.version>
        <plugin.tools.version>3.15.2</plugin.tools.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-plugin-api</artifactId>
            <version>${maven.api.version}</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-core</artifactId>
            <version>${maven.api.version}</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-model</artifactId>
            <version>${maven.api.version}</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-artifact</artifactId>
            <version>${maven.api.version}</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.maven.plugin-tools</groupId>
            <artifactId>maven-plugin-annotations</artifactId>
            <version>${plugin.tools.version}</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-plugin-plugin</artifactId>
                <version>${plugin.tools.version}</version>
                <configuration>
                    <goalPrefix>project-inspector</goalPrefix>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### Giải thích POM plugin

1. `<packaging>maven-plugin</packaging>` cho phép Maven dùng lifecycle phù hợp để tạo plugin descriptor.
2. `maven-plugin-plugin` 3.15.2 quét `@Mojo` annotations và tạo `META-INF/maven/plugin.xml`.
3. Plugin Tools annotations được khai ở `provided`; Maven Plugin Plugin đọc metadata khi build.
4. Maven Plugin API/Core/Model/Artifact versions đồng bộ Maven 3.9.9, scope `provided`.
5. Compiler Plugin ghim Java target 17. Plugin JAR sẽ cần JVM Maven runtime chạy JDK17+.
6. Cấu hình `goalPrefix` giúp mô tả prefix; lab vẫn gọi bằng full coordinate.
7. Không tự thêm execution `descriptor` trùng khi packaging `maven-plugin` đã bind goal đó.
8. Các Maven APIs là **API của build runtime**, không phải dependency runtime của consumer Java application.

**Lưu ý tương thích:** việc compile với Maven Core 3.9.9 không tự buộc người dùng chạy đúng Maven 3.9.9. Nếu plugin dùng API không có ở Maven runtime cũ, có thể gặp `NoSuchMethodError`; cần kiểm thử/giới hạn Maven versions được hỗ trợ.

## 17. InspectMojo.java hoàn chỉnh

File `plugin/src/main/java/dev/learning/maven/inspect/InspectMojo.java`:

```java
package dev.learning.maven.inspect;

import java.util.List;

import org.apache.maven.execution.MavenSession;
import org.apache.maven.model.Model;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.LifecyclePhase;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;
import org.apache.maven.project.MavenProject;

@Mojo(
    name = "inspect",
    defaultPhase = LifecyclePhase.VALIDATE,
    requiresProject = true,
    threadSafe = true
)
public final class InspectMojo extends AbstractMojo {

    @Parameter(defaultValue = "${project}", readonly = true, required = true)
    private MavenProject project;

    @Parameter(defaultValue = "${session}", readonly = true, required = true)
    private MavenSession session;

    @Parameter(property = "inspector.showReactor", defaultValue = "true")
    private boolean showReactor;

    @Override
    public void execute() throws MojoExecutionException {
        if (project == null || session == null) {
            throw new MojoExecutionException(
                    "Maven project/session context is unavailable");
        }

        Model effective = project.getModel();
        Model original = project.getOriginalModel();

        getLog().info("project.gav=" + project.getGroupId()
                + ":" + project.getArtifactId()
                + ":" + project.getVersion());

        getLog().info("project.packaging=" + project.getPackaging());
        getLog().info("project.basedir=" + project.getBasedir());
        getLog().info("project.build.directory="
                + project.getBuild().getDirectory());

        getLog().info("model.version=" + effective.getModelVersion());
        getLog().info("model.effective.dependencies="
                + effective.getDependencies().size());

        if (original != null) {
            getLog().info("model.original.dependencies="
                    + original.getDependencies().size());
        } else {
            getLog().info("model.original=unavailable");
        }

        getLog().info("session.offline=" + session.isOffline());
        getLog().info("session.user.inspector.tag="
                + session.getUserProperties()
                         .getProperty("inspector.tag", "unset"));

        List<MavenProject> projects = session.getProjects();
        int size = projects == null ? 0 : projects.size();
        getLog().info("session.selected.projects=" + size);

        if (showReactor && projects != null) {
            for (MavenProject item : projects) {
                getLog().info("reactor.project="
                        + item.getGroupId() + ":"
                        + item.getArtifactId() + ":"
                        + item.getVersion());
            }
        }
    }
}
```

### Đọc code chính xác

- `project` và `session` được Maven inject **trước `execute()`**.
- `project.getGroupId/getArtifactId/getVersion` trả effective GAV.
- `project.getBuild().getDirectory()` lấy configured build directory thay vì hardcode `target`.
- `effective.getDependencies().size()` đếm dependencies của effective model, không đếm transitive JARs.
- `original` được null-check vì không nên giả định mọi synthetic/project model có original POM.
- `session.getUserProperties()` chỉ đọc key `inspector.tag`, tránh log toàn bộ credentials.
- `session.getProjects()` là selected reactor projects.
- `showReactor` là user-configurable option, có thể truyền `-Dinspector.showReactor=false`.
- Không mutate MavenProject/Session nên logic lab có read-only design.

## 18. InspectDependenciesMojo.java hoàn chỉnh

File `plugin/src/main/java/dev/learning/maven/inspect/InspectDependenciesMojo.java`:

```java
package dev.learning.maven.inspect;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;

import org.apache.maven.artifact.Artifact;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;
import org.apache.maven.plugins.annotations.ResolutionScope;
import org.apache.maven.project.MavenProject;

@Mojo(
    name = "inspect-deps",
    requiresProject = true,
    requiresDependencyResolution = ResolutionScope.RUNTIME,
    threadSafe = true
)
public final class InspectDependenciesMojo extends AbstractMojo {

    @Parameter(defaultValue = "${project}", readonly = true, required = true)
    private MavenProject project;

    @Override
    public void execute() throws MojoExecutionException {
        if (project == null) {
            throw new MojoExecutionException("No Maven project injected");
        }

        Set<Artifact> artifacts = project.getArtifacts();
        List<String> lines = new ArrayList<>();

        for (Artifact artifact : artifacts) {
            lines.add(artifact.getGroupId() + ":"
                    + artifact.getArtifactId() + ":"
                    + artifact.getVersion() + ":"
                    + artifact.getScope());
        }

        Collections.sort(lines);
        getLog().info("runtime.resolved.count=" + lines.size());

        for (String line : lines) {
            getLog().info("runtime.artifact=" + line);
        }
    }
}
```

### Vì sao `requiresDependencyResolution = RUNTIME`?

Goal đầu tiên `inspect` đọc metadata project, **không cần tải các project runtime JARs**. Goal `inspect-deps` cần artifacts đã resolve nên Maven chuẩn bị runtime classpath theo annotation trước khi thực thi.

Ở consumer của lab, Commons Lang compile dependency thường xuất hiện trong runtime artifact set; JUnit Jupiter test dependency không nằm trong runtime scope. Những project khác có thể có nhiều transitive runtime JARs.

Không tự suy rằng `getArtifacts()` luôn đầy đủ trước `compile` hoặc `test`: nội dung có thể lazy và phụ thuộc resolution scope/phase. Chính annotation requirements làm việc đó rõ ràng.

## 19. So sánh hai Mojo

| Khía cạnh | inspect | inspect-deps |
| --- | --- | --- |
| Injection `MavenProject` | Có | Có |
| Injection `MavenSession` | Có | Không cần |
| Đọc `getModel()` | Có | Không cần |
| Đọc `getOriginalModel()` | Có | Không cần |
| Xem selected reactor list | Có | Không cần |
| Yêu cầu project runtime artifacts | Không | Có |
| Có thể cần tải Commons Lang trước execute | Không nhất thiết | Có khi uncached |
| Đếm JUnit test dependency như runtime artifact | Không làm | Không |
| Sửa project/session model | Không | Không |

**Không cấu hình `ResolutionScope.TEST` trên mọi goal**: làm vậy có thể tăng network/CPU và gây failure trong môi trường offline dù goal chỉ cần đọc version.

## 20. Consumer pom.xml độc lập

File `consumer/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning.example</groupId>
    <artifactId>demo-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
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
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
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

POM consumer **không khai plugin tùy chỉnh**; ta gọi goal bằng full-coordinate trực tiếp để kiểm chứng injection. Việc Maven local repository đã chứa plugin **không có nghĩa** plugin tự chạy trong `mvn verify`.

## 21. Consumer main Java

File `consumer/src/main/java/dev/learning/example/DemoApp.java`:

```java
package dev.learning.example;

import org.apache.commons.lang3.StringUtils;

public final class DemoApp {
    private DemoApp() {
    }

    public static String message() {
        return "Hello " + StringUtils.capitalize("maven") + " model";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

**Stdout chính xác của ứng dụng**:

```text
Hello Maven model
```

Đây là Java 17 chạy được nếu Commons Lang JAR có trong runtime classpath. POM tạo plain JAR và không có `Main-Class`, nên **không hướng dẫn** `java -jar target/demo-consumer-1.0.0.jar` như một executable jar.

## 22. Consumer JUnit test

File `consumer/src/test/java/dev/learning/example/DemoAppTest.java`:

```java
package dev.learning.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class DemoAppTest {
    @Test
    void messageIsStable() {
        assertEquals("Hello Maven model", DemoApp.message());
    }
}
```

Unit test dùng JUnit Jupiter 5.11.4 ở scope test và Surefire 3.2.5. Test này xác minh behavior Java main, nhưng **không** thay plugin descriptor/injection integration test.

## 23. Build và install plugin

Từ thư mục `maven-model-lab/`:

**Linux/macOS:**

```bash
cd plugin
mvn -B -ntp clean install
jar tf target/project-inspector-maven-plugin-1.0.0.jar
```

**Windows PowerShell:**

```powershell
Set-Location plugin
mvn -B -ntp clean install
jar tf "target\project-inspector-maven-plugin-1.0.0.jar"
```

Khi thành công, Maven Plugin Plugin tạo `META-INF/maven/plugin.xml` trong plugin JAR. Trong listing tìm:

```text
META-INF/maven/plugin.xml
dev/learning/maven/inspect/InspectMojo.class
dev/learning/maven/inspect/InspectDependenciesMojo.class
```

Đây là **các entries cần xuất hiện**, không phải toàn bộ output. Maven Plugin Tools cũng ghi goal descriptors cho `inspect` và `inspect-deps`.

`mvn install` ghi plugin artifact vào **local Maven repository**, không publish lên Maven Central. Consumer phải dùng cùng Maven repository hoặc một repository thực sự chứa plugin artifact phù hợp.

## 24. Chạy plugin từ consumer

Từ thư mục `plugin`, chuyển sang consumer rồi build:

**Linux/macOS:**

```bash
cd ../consumer
mvn -B -ntp clean verify
mvn -B -ntp dev.learning.maven:project-inspector-maven-plugin:1.0.0:inspect -Dinspector.tag=classroom
```

**Windows PowerShell:**

```powershell
Set-Location ..\consumer
mvn -B -ntp clean verify
mvn -B -ntp dev.learning.maven:project-inspector-maven-plugin:1.0.0:inspect "-Dinspector.tag=classroom"
```

Những **dòng log cốt lõi dự kiến**, sau khi bỏ Maven banners và những đường dẫn riêng máy:

```text
[INFO] project.gav=dev.learning.example:demo-consumer:1.0.0
[INFO] project.packaging=jar
[INFO] model.version=4.0.0
[INFO] model.effective.dependencies=2
[INFO] model.original.dependencies=2
[INFO] session.offline=false
[INFO] session.user.inspector.tag=classroom
[INFO] session.selected.projects=1
[INFO] reactor.project=dev.learning.example:demo-consumer:1.0.0
```

**Các dòng basedir/build.directory thay đổi theo máy và được lược khỏi ví dụ.** `session.offline=false` giả sử bạn không dùng `-o`. Con số selected projects bằng 1 trong consumer độc lập, không phải cam kết cho multi-module project.

Nếu Maven runtime/Plugin Tools khác baseline, log text có thể khác; phần cần xác minh là project/session values.

## 25. Chạy inspect-deps và so scope

Trong consumer:

```bash
mvn -B -ntp dev.learning.maven:project-inspector-maven-plugin:1.0.0:inspect-deps
```

Với runtime dependency graph của consumer baseline, dòng quan trọng dự kiến:

```text
[INFO] runtime.artifact=org.apache.commons:commons-lang3:3.14.0:compile
```

- Commons Lang là compile dependency nhưng được dùng ở runtime, nên nằm trong runtime resolution scope.
- JUnit Jupiter là test-only dependency, nên thường không hiện ở goal yêu cầu runtime scope.
- `model.effective.dependencies=2` ở goal trước **không mâu thuẫn** với runtime resolved artifact set ít hơn.
- Plugin API/Core dependencies ở project plugin **không bị biến thành project dependencies của consumer**.

Không hardcode `runtime.resolved.count=1` trong automated tests của mọi invocation: nếu project có thêm transitive deps, profiles hoặc goals trước đó, data có thể thay đổi.

## 26. Chạy Java main đúng classpath

Cách tiện với Maven Exec Plugin full-coordinate:

```bash
mvn -B -ntp org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=dev.learning.example.DemoApp
```

Stdout của chương trình:

```text
Hello Maven model
```

Exec Plugin có thể cần được tải lần đầu; nó là plugin khác, không phải goal của plugin inspector.

**Linux/macOS** với Maven local repo mặc định:

```bash
java -cp "target/classes:$HOME/.m2/repository/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" dev.learning.example.DemoApp
```

**Windows PowerShell** với local repo mặc định:

```powershell
java -cp "target\classes;$HOME\.m2\repository\org\apache\commons\commons-lang3\3.14.0\commons-lang3-3.14.0.jar" dev.learning.example.DemoApp
```

Nếu dùng `-Dmaven.repo.local` hoặc custom Maven settings, phải thay path trong `-cp`. Hai lệnh java direct cần `target/classes` được build trước.

## 27. Goal trực tiếp khác lifecycle phase

Một `@Mojo(defaultPhase=VALIDATE)` **không đồng nghĩa** tự chạy trong mọi:

```bash
mvn validate
```

Lệnh full-coordinate:

```bash
mvn dev.learning.maven:project-inspector-maven-plugin:1.0.0:inspect
```

thực thi goal cụ thể mà **không bắt Maven tự chạy toàn bộ compile/test lifecycle**.

Nếu muốn tự động chạy `inspect` cùng `mvn validate`, khai một execution trong **consumer/pom.xml**:

```xml
<plugin>
    <groupId>dev.learning.maven</groupId>
    <artifactId>project-inspector-maven-plugin</artifactId>
    <version>1.0.0</version>
    <executions>
        <execution>
            <id>inspect-on-validate</id>
            <phase>validate</phase>
            <goals>
                <goal>inspect</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Fragment trên phải đặt dưới `<build><plugins>...</plugins></build>`. Đây là **tùy chọn bổ sung**, không có trong consumer POM baseline.

Sau khi bind:

```bash
mvn -B -ntp validate -Dinspector.tag=lifecycle
```

`inspect` được gọi bởi lifecycle. Nếu chạy `mvn validate plugin:inspect` khi inspect cũng đã được bind vào validate, goal có thể chạy **hai lần**.

`pluginManagement` quản lý versions/config nhưng **không tự kích hoạt** tất cả custom goal executions.

## 28. Reactor projects khác modules khai trong POM

Ví dụ:

```text
reactor/
├── pom.xml             packaging pom
├── api/pom.xml
└── service/pom.xml
```

Root POM khai:

```xml
<modules>
    <module>api</module>
    <module>service</module>
</modules>
```

Phân biệt:

- `rootProject.getModules()` trả danh sách tên modules khai trong root model, như `api`, `service`.
- `session.getProjects()` trả MavenProject objects **được Maven chọn trong invocation**.
- `session.getTopLevelProject()` trả top-level project theo session.
- `session.getExecutionRootDirectory()` trả execution root directory.
- `project.getBasedir()` trả directory của **module đang xử lý**.
- `project.getParent()` liên quan declared parent POM, không nhất thiết là aggregator root.

Không đồng nhất **aggregation** (`<modules>`) và **inheritance** (`<parent>`). Một aggregator POM có thể không phải parent của mọi module và ngược lại.

## 29. -N, -pl, -am ảnh hưởng session.getProjects

Từ reactor root:

```bash
mvn -B -ntp validate
mvn -B -ntp -N validate
mvn -B -ntp -pl :service validate
mvn -B -ntp -pl :service -am validate
```

- Lệnh không selectors thường chọn reactor projects theo normal traversal.
- `-N` non-recursive, không xử lý các child modules như full reactor.
- `-pl :service` chọn service module.
- `-am` chọn thêm reactor dependencies cần thiết để build module đó.

Vì vậy **không assert** `session.getProjects().size()` phải bằng số child directories trên disk. Nó là selected Maven projects theo request.

Một plugin chạy per-module có thể được thực thi nhiều lần với **injected project khác nhau**, trong khi `session.getProjects()` vẫn mô tả selected reactor cho invocation.

## 30. Aggregator Mojo khác per-project Mojo

Một goal dùng để tổng hợp toàn reactor có thể khai:

```java
@Mojo(
    name = "aggregate-report",
    aggregator = true,
    requiresProject = true
)
```

Đây chỉ là annotation fragment, không phải chương trình hoàn chỉnh.

Aggregator behavior phụ thuộc cách gọi goal, lifecycle và reactor selection. **Không coi** `aggregator=true` là bảo đảm “quét mọi module có trên filesystem” khi user đang dùng `-pl`, `-N` hoặc chạy từ một module con.

Khi thiết kế aggregator:

1. Quy định phải chạy từ root hay chỉ selected reactor.
2. Duyệt `session.getProjects()` theo ngữ cảnh.
3. Tránh ghi cùng output file từ per-module goals đồng thời.
4. Nếu chạy song song, xác định rõ thread safety.
5. Chỉ tổng hợp dữ liệu của các modules thực sự được Maven chọn.
6. Không mutate object state của modules nếu goal chỉ làm báo cáo.

## 31. getCurrentProject có thay injected project không?

MavenSession có API:

```java
MavenProject current = session.getCurrentProject();
```

Nhưng nếu Mojo đã được inject:

```java
@Parameter(defaultValue = "${project}", readonly = true)
private MavenProject project;
```

hãy **ưu tiên injected `project`** cho current module processing. `session.getCurrentProject()` phụ thuộc execution context, không phải cơ chế chọn module tùy ý. Trong parallel reactor, đừng dựa vào một session-global mutable current-project field như giả thiết thread-safety.

Không gọi `session.setCurrentProject(...)` trong plugin chỉ để ép context của một child module.

## 32. User properties khác project properties

Trong POM:

```xml
<properties>
    <application.language>vi</application.language>
</properties>
```

Trong Mojo:

```java
String language = project.getProperties()
        .getProperty("application.language", "unset");

String tag = session.getUserProperties()
        .getProperty("inspector.tag", "unset");
```

- `project.getProperties()` thuộc MavenProject model, có thể gồm các values inherited/effective.
- `session.getUserProperties()` gồm user overrides như `-Dinspector.tag=classroom`.
- `session.getSystemProperties()` có system properties dùng để xây model/activate profiles.
- `@Parameter(property = "inspector.tag")` là cách thích hợp để khai **tùy chọn plugin** có thể cấu hình.
- Không giả định mọi CLI `-D` value đều được ghi vào `project.getProperties()` theo đúng hình thức raw POM.

**Lưu ý bảo mật:** project properties/user/system properties có thể chứa token hoặc đường dẫn nội bộ; chỉ log keys đã được phép.

## 33. Project build directory nên lấy từ model

Một project có thể override:

```xml
<build>
    <directory>build-output</directory>
</build>
```

Không hardcode:

```java
File dir = new File(project.getBasedir(), "target");
```

Hãy dùng:

```java
String configuredDirectory = project.getBuild().getDirectory();
File dir = new File(configuredDirectory);
```

Đây là code fragment, cần import `java.io.File`. Nó phản ánh configured build directory trong Maven effective model. Với module con, `basedir` khác execution root, vì vậy không nối path từ session root theo giả định một module.

## 34. Source roots và generated sources

MavenProject có:

```java
List<String> mainRoots = project.getCompileSourceRoots();
List<String> testRoots = project.getTestCompileSourceRoots();
```

Đây là fragment cần import `java.util.List`.

Nếu Mojo chạy tại `validate`, generated source roots do code generator bind ở `generate-sources` **chưa chắc đã được thêm** vào project. Thông tin sẽ phụ thuộc lifecycle phase và plugin executions đã diễn ra.

Khi viết một code-generator goal thật, có thể dùng:

```java
project.addCompileSourceRoot(generatedDirectory.getAbsolutePath());
```

hoặc cho test:

```java
project.addTestCompileSourceRoot(generatedTestDir.getAbsolutePath());
```

Những dòng này là **fragment có điều kiện**: directories phải là `java.io.File` hợp lệ, code generator thực sự tạo source files, và goal nên chạy trước compile/testCompile trong phase `generate-sources`/`generate-test-sources`.

**Không tự thêm source roots trong một goal chỉ đọc metadata**: đây là mutation làm thay đổi build state, không cần thiết và có thể ảnh hưởng các goals phía sau.

## 35. Project artifact khác resolved dependency artifacts

Hai API dễ bị nhầm:

```java
Artifact currentProjectArtifact = project.getArtifact();
Set<Artifact> dependencies = project.getArtifacts();
```

- `getArtifact()` là artifact đại diện **chính project** (tọa độ đóng gói).
- `getArtifacts()` trả resolved project dependencies có thể gồm transitive artifacts, filtered theo scope/phase.
- `getDependencies()` là declarations, không phải resolved file set.
- `getDependencyManagement()` là managed versions/scope rules, không tự thêm dependency vào project.

Nếu plugin cần file bytes JAR, phải kiểm tra resolved artifact state và `artifact.getFile()` hợp lệ. Không suy `Model Dependency` có File JAR vì đó là khai báo trong POM.

## 36. Vì sao không nên mutate Model trong inspect?

`project.getModel()` cho bạn một Model object, nhưng không có nghĩa thay một field trong đó sẽ khiến Maven **chạy lại toàn bộ Model Builder/Resolver**.

Ví dụ:

```java
project.getModel().setVersion("2.0.0");
```

Đây là ví dụ **không nên làm**, không thuộc runnable lab. Nó có thể làm MavenProject effective GAV, artifact, reactor dependency graph và state khác trở nên không nhất quán.

Nếu cần tạo metadata mới:

- Ưu tiên plugin configuration `@Parameter`.
- Nếu cần generated source roots, mutate qua API chuyên biệt đúng phase.
- Nếu cần attached artifacts, dùng Maven Project Helper APIs và hiểu lifecycle.
- Nếu thay version/dependencies, sửa POM trước khi Maven dựng model, không sửa tùy ý trong inspection Mojo.

Plugin should treat project model as **read-only by default**.

## 37. Maven API version và compatibility

Lab pin Maven API 3.9.9 và Java release 17 để đơn giản hóa kiểm chứng, nhưng:

- Plugin Java 17 bytecode yêu cầu Maven JVM chạy JDK 17+, dù consumer compile target có thể khác.
- Maven 3.8.x có thể thiếu API Maven Core mà plugin compile với 3.9.9 sử dụng.
- Maven 4 có API/model/migration path khác; không mặc định binary compatibility.
- Nếu đóng thêm maven-core JAR vào plugin runtime classpath sai cách, có thể xảy ra classloading clashes.
- Maven Plugin Tools version phải tương thích với Maven runtime minimum đã chọn.
- Testing Harness/Invoker với nhiều Maven versions là cách tốt để công bố supported range thực.

Đừng ghi “hỗ trợ mọi Maven 3” khi bạn chỉ build/test bằng Maven 3.9.9.

## 38. Maven plugin descriptor sinh ra ở đâu?

Một Maven plugin JAR chứa:

```text
META-INF/maven/plugin.xml
```

Descriptor mô tả:

- Goal names `inspect`, `inspect-deps`.
- Java implementation classes.
- Default lifecycle phase nếu có.
- Project/aggregator/threadsafety requirements.
- Dependency resolution requirements.
- Parameters và default values.

Sau `mvn clean install` của plugin project, dùng `jar tf` để kiểm tra descriptor có trong plugin JAR. Nếu không có, kiểm tra packaging, maven-plugin-plugin version, annotation scanning và goal execution ở `process-classes`.

Đừng tự sửa JAR `plugin.xml` thủ công. Sửa Java annotations/POM, rebuild và kiểm tra lại.

## 39. Help Plugin describe để kiểm chứng goal metadata

Sau khi install plugin, tại consumer:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.1:describe -Dplugin=dev.learning.maven:project-inspector-maven-plugin -Ddetail
```

Lệnh có thể cần tải Maven Help Plugin nếu cache trống. Nó giúp hiển thị goals/parameters của plugin.

Nếu goal không xuất hiện:

- Kiểm tra plugin JAR descriptor.
- Kiểm tra Maven local repository path của plugin và consumer có khớp không.
- Kiểm tra GAV/version đang resolve, tránh dùng cached plugin version khác.
- Kiểm tra `@Mojo` có được Plugin Tools trích xuất không.
- Kiểm tra prefix/full-coordinate khác nhau.

Không xóa toàn bộ `~/.m2/repository` làm bước đầu.

## 40. Plugin prefix không giống full-coordinate invocation

Full goal:

```bash
mvn dev.learning.maven:project-inspector-maven-plugin:1.0.0:inspect
```

Short goal theo naming convention có thể dùng prefix `project-inspector`:

```bash
mvn project-inspector:inspect
```

Nhưng short prefix có thể cần `pluginGroups`/metadata/đăng ký plugin đúng cách. **Ưu tiên full-coordinate goal** trong lab để tránh nhầm lỗi prefix lookup với lỗi injection trong Mojo.

Nếu full goal chạy được nhưng short goal không, kiểm tra plugin prefix mapping. Nếu cả hai không tải được artifact, kiểm tra plugin repositories/local cache/credentials.

## 41. Testing plugin: không chỉ new Mojo rồi execute

Unit test kiểu:

```java
InspectMojo mojo = new InspectMojo();
mojo.execute();
```

không đại diện một Maven invocation vì MavenProject/MavenSession fields chưa được Maven runtime inject.

Để test đúng:

1. Unit test domain logic đã tách khỏi Maven context.
2. Test descriptor của plugin artifact.
3. Maven Plugin Testing Harness cho injection/project fixture.
4. Maven Invoker Plugin chạy consumer fixtures trong Maven process.
5. Reactor tests với parent/child, `-N`, `-pl`, `-am`.
6. Tests với `ResolutionScope.RUNTIME`/`TEST`, offline và custom local repo.
7. Tests với Java/Maven versions trong supported range.
8. Kiểm tra không log secrets và không mutate project state.

Một direct CLI run trên consumer như lab là **end-to-end smoke test hữu ích**, nhưng chưa thay được test matrix cho production plugin.

## 42. Thread safety và parallel reactor

`@Mojo(threadSafe=true)` là lời tuyên bố của plugin author, không phải khóa tự động.

Nếu plugin chỉ đọc fields từ `MavenProject` và `MavenSession` rồi log, implementation đơn giản có thể phù hợp với parallel build. Nhưng khi thêm logic:

- Không lưu current MavenProject vào static mutable field.
- Không ghi cùng một output file từ mọi module cùng lúc.
- Không tự sửa `session.getProjects()` hoặc MavenSession request state.
- Không thay shared MavenProject properties mà không hiểu thứ tự lifecycle.
- Không giả định logs của `mvn -T 1C` luôn theo module order.
- Dùng output path riêng từng module nếu không phải aggregator report.
- Có integration tests cho parallel build và các plugins liên quan.

Không khai `threadSafe=true` nếu goal ghi/sửa state chung mà chưa được thiết kế an toàn.

## 43. Kịch bản multi-module: một goal có thể chạy nhiều lần

Nếu một plugin execution được inherited từ parent vào các modules, Maven có thể thực thi `inspect` trên nhiều projects:

```text
root (packaging pom)
api  (packaging jar)
service (packaging jar)
```

Log có thể gồm ba dòng `project.gav`, mỗi dòng ứng với **một injected MavenProject**.

Mặt khác, `session.selected.projects` có thể cùng một giá trị trong các lần chạy đó vì nó là selected reactor set.

**Không tính số lần Mojo execute bằng số projects trong session mà không xét execution binding/aggregator flags**. Một goal có thể được skip bởi profiles, selection hoặc plugin configuration.

## 44. Debug injection khi project null

Các nguyên nhân thường gặp:

| Tình huống | Chẩn đoán |
| --- | --- |
| Tự gọi `new InspectMojo()` | Không có Maven injection |
| Field thiếu `@Parameter` | Descriptor không có injection expression |
| `@Mojo(requiresProject=false)` nhưng goal đọc project | Context project không được đảm bảo |
| Goal chạy ngoài project folder | Maven có thể không có POM/project |
| Plugin descriptor không khớp class mới | Build/install plugin artifact cũ |
| Version Maven/Plugin Tools khác | Đọc descriptor và compatibility |
| Tester khởi tạo Mojo không theo harness | Cần Maven process/harness |

Nếu goal có `requiresProject=true`, chạy ngoài Maven project sẽ không có context như bạn kỳ vọng; Maven có thể fail trước `execute()`.

Đừng chữa bằng cách tạo một `new MavenProject()` giả rồi tiếp tục in dữ liệu không có thật.

## 45. Debug khi getArtifacts rỗng

Nếu inspect goal được gọi ở `validate` mà không khai dependency resolution, Maven có thể chưa có resolved artifacts.

Các bước:

1. Kiểm tra mục tiêu của goal: cần model declarations hay resolved files?
2. Nếu chỉ cần declarations, đọc `project.getDependencies()` hoặc `getModel()`.
3. Nếu cần resolved runtime graph, khai `requiresDependencyResolution = ResolutionScope.RUNTIME`.
4. Nếu cần test scope, chọn `ResolutionScope.TEST`.
5. Rebuild plugin và kiểm tra descriptor đã phản ánh requirement mới.
6. Gọi goal trực tiếp trên consumer có dependencies thật.
7. Nếu Maven không tải được JAR, kiểm tra repository/network thay vì coi graph empty là bug API.

**Không buộc mọi goal resolve TEST scope** để “chữa” graph, vì gây overhead không cần thiết.

## 46. Chẩn đoán build directory và reactor paths

Nếu plugin ghi log:

```text
project.basedir=/workspace/reactor/service
project.build.directory=/workspace/reactor/service/build-output
session.executionRoot=/workspace/reactor
```

Đây là **paths minh họa**, không phải expected output của lab một module. Mỗi field có ý nghĩa:

- Project basedir thuộc module.
- Build directory lấy từ effective build config của module.
- Execution root thuộc Maven invocation.

Một plugin ghi report chung ở root không nên tự giả định `project.getBasedir()` là root. Nếu cần root-based report, xác định rõ requirements và lấy directory từ session context phù hợp.

## 47. Lỗi do Maven runtime classpath vs Java application classpath

Plugin `project-inspector-maven-plugin` chạy trong **Maven plugin realm** và dùng Maven Core/Plugin API classes được Maven cung cấp.

Consumer Java application dùng Commons Lang/JUnit theo project dependency graph. Hai classpaths khác nhau:

| Classpath | Chứa |
| --- | --- |
| Maven JVM/Plugin realm | Maven Core, plugin JAR, plugin dependencies |
| Project compile/runtime | Commons Lang và source output |
| Project test | JUnit Jupiter và test output |
| Resolved artifact set của `inspect-deps` | Project artifacts theo RUNTIME scope |

Một lỗi `ClassNotFoundException` trong plugin có thể đến từ plugin realm; `NoClassDefFoundError` khi chạy DemoApp có thể do Commons Lang không nằm trong application classpath.

**Đừng sửa consumer dependencyManagement để chữa một Maven plugin API mismatch** nếu lỗi nằm ở plugin realm.

## 48. Anti-pattern cần tránh

- Parse POM XML rồi bỏ qua parent/BOM/profiles.
- `new MavenProject()` hoặc `new MavenSession()` thay injection.
- Cố inject session qua một user-configurable String parameter.
- In toàn bộ Settings/UserProperties ra CI logs.
- Đọc `getArtifacts()` trong goal không yêu cầu resolution rồi khẳng định graph “trống”.
- Sửa `project.getModel().setVersion()` tùy tiện trong lifecycle.
- Hardcode `target/` và working directory root.
- Giả định `session.getProjects()` có mọi directory/module tồn tại.
- Giả định `@Mojo(defaultPhase=...)` tự bind vào tất cả projects.
- Dùng short prefix khi cần debug plugin artifact version.
- Bundle Maven Core vào plugin JAR và làm mâu thuẫn runtime API.
- Khai threadSafe dù đang ghi file chung không có synchronization.
- Coi version Maven/JDK của machine build plugin bằng version consumer sẽ dùng.
- Tắt tests hoặc cắt bớt lifecycle chỉ để nhận log “BUILD SUCCESS”.
- Bỏ qua plugin descriptor QA trước khi publish plugin.

## 49. Checklist khi viết plugin đọc project/session

- [ ] Maven/Java baseline được xác định rõ (ví dụ Maven 3.9.9, Java 17).
- [ ] Plugin project dùng packaging `maven-plugin`.
- [ ] Maven Plugin Plugin version và annotations được pin.
- [ ] Maven API/Core/Model dependencies khai `provided`.
- [ ] Có `@Mojo(name=...)` và goal descriptor hợp lệ.
- [ ] Dùng `@Parameter(defaultValue="${project}", readonly=true)`.
- [ ] Dùng `@Parameter(defaultValue="${session}", readonly=true)`.
- [ ] Goal yêu cầu project có `requiresProject=true`.
- [ ] Đọc effective GAV bằng MavenProject getters.
- [ ] `getOriginalModel()` được null-check.
- [ ] Không nhầm model declarations với resolved artifacts.
- [ ] Goal cần artifact files có `requiresDependencyResolution` đúng scope.
- [ ] Không dùng TEST scope nếu chỉ cần runtime.
- [ ] Dùng `getBuild().getDirectory()` thay hardcoded target.
- [ ] Phân biệt `getModules()` và `session.getProjects()`.
- [ ] Xử lý `-N`, `-pl`, `-am` trong tests nếu làm aggregator.
- [ ] Không dựa vào `getCurrentProject()` như global selector.
- [ ] Không mutate model trong inspect goal.
- [ ] Nếu đăng ký generated source roots, chạy đúng phase và có tests.
- [ ] Không in secrets từ settings/user/system properties.
- [ ] Thread-safe declaration phản ánh implementation thực.
- [ ] Build/install plugin trước khi chạy consumer full-coordinate goal.
- [ ] Có plugin.xml trong artifact.
- [ ] Có integration smoke test trên consumer.
- [ ] Có test child/parent inheritance, build-directory overrides.
- [ ] Có test Maven runtime compatibility.
- [ ] Không nhầm plugin realm với project dependency classpath.
- [ ] Có error messages rõ khi Maven context không tồn tại.
- [ ] Đọc official Javadocs nếu nâng Maven version.
- [ ] Không gọi goal trực tiếp và bind lifecycle đồng thời khi không muốn chạy hai lần.

## 50. Bài tập có đáp án

1. **MavenProject đại diện điều gì?**  
   Một project/module đã được Maven dựng model.

2. **MavenSession đại diện điều gì?**  
   Một Maven execution context và selected reactor.

3. **Cách inject MavenProject trong lab?**  
   `@Parameter(defaultValue = "${project}", readonly = true)`.

4. **Cách inject MavenSession?**  
   `@Parameter(defaultValue = "${session}", readonly = true)`.

5. **`new MavenProject()` có tương đương injected project không?**  
   Không.

6. **API đọc project groupId?**  
   `project.getGroupId()`.

7. **API đọc effective version?**  
   `project.getVersion()`.

8. **API đọc current model?**  
   `project.getModel()`.

9. **API đọc original POM model?**  
   `project.getOriginalModel()` và null-check.

10. **`getModel().getDependencies()` có bao gồm transitive artifacts?**  
    Không, nó là model dependency declarations.

11. **API cho resolved project artifacts?**  
    `project.getArtifacts()` sau resolution phù hợp.

12. **Muốn runtime dependencies dùng annotation nào?**  
    `requiresDependencyResolution = ResolutionScope.RUNTIME`.

13. **Scope RUNTIME có JUnit test-only không?**  
    Không trong normal runtime resolution.

14. **Muốn test artifacts chọn gì?**  
    `ResolutionScope.TEST`.

15. **Plugin packaging của lab?**  
    `maven-plugin`.

16. **Plugin Maven Core dependencies dùng scope gì?**  
    `provided`.

17. **Goal inspect đọc gì?**  
    MavenProject model và MavenSession context.

18. **Goal inspect-deps làm gì?**  
    Yêu cầu runtime resolution rồi đọc getArtifacts.

19. **File descriptor quan trọng?**  
    `META-INF/maven/plugin.xml`.

20. **Lệnh cài plugin local?**  
    `mvn -B -ntp clean install` tại plugin project.

21. **Full-coordinate goal inspect?**  
    `mvn dev.learning.maven:project-inspector-maven-plugin:1.0.0:inspect`.

22. **Consumer cần khai plugin trong POM để gọi full goal không?**  
    Không nhất thiết nếu artifact resolve được.

23. **DefaultPhase VALIDATE tự khiến goal chạy khi mvn validate?**  
    Không, phải bind lifecycle execution.

24. **Binding goal trong POM ở đâu?**  
    `build/plugins` với `executions/execution/phase/goals`.

25. **pluginManagement có tự chạy inspect không?**  
    Không.

26. **`session.getProjects()` có luôn bằng số folders trong reactor?**  
    Không, phụ thuộc selected projects.

27. **`project.getModules()` trả gì?**  
    Tên modules được khai trong model của current project.

28. **`-N` ảnh hưởng gì?**  
    Không recurse qua child modules.

29. **`-pl` ảnh hưởng gì?**  
    Chọn subset reactor projects.

30. **`-am` ảnh hưởng gì?**  
    Thêm reactor dependencies cần để build selected modules.

31. **Top-level project có luôn bằng injected project không?**  
    Không.

32. **Trong per-module Mojo nên dựa vào đối tượng nào?**  
    Injected MavenProject.

33. **`session.getUserProperties()` đọc được gì?**  
    Các user properties như CLI `-Dinspector.tag=classroom`.

34. **Nên log toàn bộ Settings không?**  
    Không, có thể lộ credentials.

35. **Build directory nên lấy ở đâu?**  
    `project.getBuild().getDirectory()`.

36. **Main source roots API?**  
    `project.getCompileSourceRoots()`.

37. **Khi nào addCompileSourceRoot phù hợp?**  
    Goal generate sources thực sự tạo files trước compile.

38. **Có nên sửa project Model version trong inspect?**  
    Không, sẽ gây state inconsistency.

39. **`threadSafe=true` tự tạo thread safety?**  
    Không; implementation phải an toàn thật.

40. **Java main DemoApp in gì?**  
    `Hello Maven model`.

41. **Direct dependency compile của consumer?**  
    Commons Lang 3.14.0.

42. **Dependency test của consumer?**  
    JUnit Jupiter 5.11.4.

43. **Vì sao model count là 2 nhưng runtime graph ít hơn?**  
    JUnit ở test scope không thuộc runtime graph.

44. **Maven API phiên bản 3 có dùng y nguyên trên Maven 4 không?**  
    Không, phải xem compatibility/migration.

45. **Plugin prefix fail, full goal chạy: nên kiểm tra gì?**  
    Prefix mapping/pluginGroups/repository metadata.

46. **Làm sao test injection end-to-end?**  
    Maven Invoker/Plugin Testing Harness hoặc Maven process thật.

47. **MavenSession có method offline nào?**  
    `session.isOffline()`.

48. **MavenSession có method goals nào?**  
    `session.getGoals()`.

49. **Một plugin có nên lưu current MavenProject trong static field?**  
    Không, sai context/race trong parallel reactor.

50. **Nguyên tắc cốt lõi?**  
    Phân biệt project model, Maven session/reactor và resolved artifacts; inject đúng context, đọc hoặc mutate có chủ đích theo lifecycle.

## 51. Tài liệu tham khảo chính thức

- [Apache Maven — Guide to Developing Java Plugins](https://maven.apache.org/guides/plugin/guide-java-plugin-development.html): Mojo, plugin packaging, annotation và execution.
- [Maven Plugin Tools — Annotations](https://maven.apache.org/plugin-tools/maven-plugin-tools-annotations/): @Mojo, @Parameter, context injection.
- [Maven Plugin Tools — @Parameter API](https://maven.apache.org/plugin-tools/apidocs/org/apache/maven/plugins/annotations/Parameter.html): defaultValue, readonly, required, property.
- [Maven Plugin Tools — @Mojo API](https://maven.apache.org/plugin-tools/apidocs/org/apache/maven/plugins/annotations/Mojo.html): goal, phase, threadSafe, aggregator.
- [Maven Plugin Tools — ResolutionScope](https://maven.apache.org/plugin-tools/maven-plugin-annotations/apidocs/org/apache/maven/plugins/annotations/ResolutionScope.html): COMPILE, RUNTIME, TEST.
- [Maven Core 3.9.9 — MavenProject API](https://maven.apache.org/ref/3.9.9/maven-core/apidocs/org/apache/maven/project/MavenProject.html): Model, GAV, build, roots, artifacts.
- [Maven Core 3.9.9 — MavenSession API](https://maven.apache.org/ref/3.9.9/maven-core/apidocs/org/apache/maven/execution/MavenSession.html): session goals, projects, user properties, offline.
- [Maven Core 3.9.9 — MavenProject source](https://maven.apache.org/ref/3.9.9/maven-core/xref/org/apache/maven/project/MavenProject.html): getModel/getArtifacts implementation.
- [Maven POM Reference](https://maven.apache.org/pom.html): parent, modules, properties, dependency management.
- [Maven Guide to Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor sorting/selection.
- [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): scopes/transitive/mediation.
- [Maven Help Plugin — describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html): xem goals và parameters.
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): inspect effective model.
- [Maven Plugin Plugin — descriptor](https://maven.apache.org/plugin-tools/maven-plugin-plugin/descriptor-mojo.html): sinh descriptor từ Mojo annotations.
- [Maven Plugin Testing Harness](https://maven.apache.org/plugin-testing/): testing Mojo trong Maven context.
- [Maven Invoker Plugin](https://maven.apache.org/plugins/maven-invoker-plugin/): consumer integration tests.
- [Oracle JDK 17 Documentation](https://docs.oracle.com/en/java/javase/17/): Java compiler/runtime.

**Kết luận:** Khi mở rộng Maven, `MavenProject` mô tả **project/model hiện tại**, `MavenSession` mô tả **một Maven invocation/reactor**, và `project.getArtifacts()` thể hiện **resolved dependencies theo scope/phase**. Inject context đúng cách, dùng Model getters thay parse XML thô, chỉ yêu cầu resolution khi cần và kiểm tra plugin descriptor/compatibility trước khi đưa vào CI. Đó là nền tảng để viết các Mojo hoạt động đáng tin trên cả single-module lẫn multi-module builds.
