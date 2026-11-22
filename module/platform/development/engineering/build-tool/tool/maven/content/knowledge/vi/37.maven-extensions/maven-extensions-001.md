# Khi nào cần plugin riêng thay vì cấu hình plugin có sẵn trong Maven?

## 1. Vấn đề cần quyết định

Maven chủ yếu thực hiện build thông qua **plugin goals**. Compiler Plugin biên dịch source; Surefire Plugin chạy tests; Resources Plugin xử lý tài nguyên; JAR Plugin tạo artifact. Các plugin này đã có tham số, goals và executions đủ đáp ứng phần lớn yêu cầu build Java.

Khi phát sinh nghiệp vụ mới, nhóm phát triển có nhiều lựa chọn: cấu hình một plugin có sẵn, phối hợp các plugins, chia sẻ cấu hình bằng parent POM, gọi một CLI tool, viết một Enforcer rule, hoặc **phát triển Maven plugin riêng**. Chọn nhầm giải pháp thường khiến build quá phức tạp, khó debug và tăng chi phí bảo trì.

**Nguyên tắc:** chỉ phát triển plugin riêng khi có **behavior mới có giá trị tái sử dụng** và lợi ích tích hợp sâu với Maven vượt quá chi phí bảo trì. Một POM dài hay một plugin option khó tìm **không tự là lý do đủ**.

Bài này cung cấp tiêu chí ra quyết định, cách tìm khả năng có sẵn, đánh đổi theo quy mô, cùng ví dụ đầy đủ Maven 3.9.x/Java 17. Ví dụ là một **release policy Maven plugin** kiểm tra quan hệ giữa Maven project version và metadata trong file cấu hình. Các file có thể copy thành dự án thực hành gồm POM plugin, Java Mojo, validation logic, JUnit tests, POM consumer, policy và Main Java.

## 2. Cần hiểu plugin, goal, phase và execution

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Plugin | Artifact chứa một hay nhiều Maven goals | `maven-compiler-plugin` |
| Mojo/goal | Một hành động plugin cung cấp | `compiler:compile` |
| Lifecycle phase | Mốc điều phối build | `validate`, `compile`, `test`, `package`, `verify` |
| Execution | Gắn một goal với phase và cấu hình | Chạy `enforcer:enforce` ở `validate` |
| Parameter | Dữ liệu plugin cho phép tùy biến | `release=17` |
| `build/plugins` | Plugin/goal project thực sự sử dụng | Compiler, Surefire |
| `pluginManagement` | Quản lý version/default config, không tự sinh execution mới | Corporate parent |
| `packaging=maven-plugin` | Loại Maven project dùng để xây một plugin JAR | Custom goal |
| Core extension | Mở rộng Maven core/session, khác ordinary build plugin | Tracing/lifecycle extension |

Ví dụ khi chỉ muốn Java 17:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.1</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
```

Đây là **plugin configuration fragment**, không phải POM hoàn chỉnh. Không cần viết một plugin mới để gọi compiler với Java 17.

### Phân biệt mục tiêu của parent POM

Nếu nhiều repository cần cùng Maven/JDK versions, Surefire options, plugin versions hay quality checks, tạo một **parent POM** có pluginManagement/executions thường dễ hơn xây plugin Java riêng. Parent chỉ chia sẻ **cấu hình**; viết Mojo chỉ hợp lý nếu cần thêm **logic thực thi mới**.

`<pluginManagement>` khác `<build><plugins>`: quản lý version không tự làm goal chạy trong lifecycle trừ khi goal được default binding hoặc project instantiate/bind.

## 3. Thứ tự các giải pháp nên xét

Khi gặp một yêu cầu build mới, thử theo thứ tự từ chi phí thấp tới cao:

1. **Tìm option/goal trong plugin đang dùng.** Xem documentation và `help:describe -Ddetail`. Một parameter có thể giải quyết ngay.
2. **Thêm execution cho goal sẵn có.** Nếu đúng hành động nhưng chạy sai phase, dùng `<executions><execution><phase>...`.
3. **Dùng parent POM/pluginManagement/profiles.** Khi mục tiêu là áp dụng nhất quán nhiều modules/repos.
4. **Kết hợp plugins có sẵn.** Ví dụ Resources + Compiler, Build Helper + Source Plugin, JAR/Assembly/Shade, Enforcer + Dependency Plugin.
5. **Tách một CLI/script có thể test.** Khi tác vụ không cần Maven model, chỉ dùng cục bộ hoặc phù hợp công cụ ngoài Maven.
6. **Viết custom Enforcer rule.** Khi công việc chủ yếu là kiểm một policy và fail/pass.
7. **Viết custom Maven plugin.** Khi cần nhiều goals, lifecycle integration, project/artifact context, reusable build behavior và parameter contract.
8. **Viết core extension.** Chỉ khi ordinary Mojo không đủ vì phải can thiệp Maven core/session/event/resolution; độ phức tạp lớn hơn.

**Lợi ích của cách tiếp cận này:** chọn công cụ ít quyền hạn nhất và đơn giản nhất mà vẫn đáp ứng requirement, thay vì bắt build team bảo trì một Maven API mới chỉ để chạy một script.

## 4. Ma trận chọn giải pháp

| Yêu cầu thực tế | Giải pháp ưu tiên | Khi nào plugin riêng đáng xem |
| --- | --- | --- |
| Chốt Java release, compiler flags | Maven Compiler Plugin | Khi cần code generation/integration không có sẵn |
| Giới hạn Maven/JDK/dependency versions | Maven Enforcer Plugin | Nếu policy nhiều bước không thể diễn đạt bằng rules |
| Chạy unit và integration tests | Surefire/Failsafe Plugin | Nếu test protocol mới không được hỗ trợ |
| Copy/filter resource | Maven Resources Plugin | Nếu phải biến đổi dữ liệu domain-specific |
| Thêm generated source directory | Build Helper Maven Plugin | Nếu phải tự sinh nội dung source |
| Đóng JAR/WAR hoặc fat JAR | JAR/WAR/Shade/Assembly | Nếu output format thực sự mới |
| Copy dependency artifacts | Maven Dependency Plugin | Khi cần xuất artifact domain-specific |
| Chia sẻ 10 plugin versions | Parent POM và pluginManagement | Thường không cần custom plugin |
| Chạy tool ngoài Maven | exec-maven-plugin/maven-antrun-plugin | Khi nhiều scripts rải rác thành workflow khó kiểm |
| Cấm các release policy trái quy định | Built-in/custom Enforcer rule | Khi cần độc lập goal hoặc Maven model/artifact integration sâu |
| Sinh report và attach artifact riêng | Tìm plugin tương ứng | Có thể hợp lý với custom Mojo |
| Intercept Maven core/session | Core extension có sẵn | Đây là loại mở rộng khác, không phải plugin goal |

**Cần xem actual plugin version và goal documentation.** Một chức năng có thể đã xuất hiện trong plugin mới; đừng tái lập logic vì đang đọc tài liệu của version cũ.

## 5. Kiểm tra plugin hiện có trước khi tạo project mới

### 5.1. Đọc help:describe

Ví dụ xem tham số Compiler Plugin:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin:3.14.1 -Dgoal=compile -Ddetail
```

Maven Help Plugin cho biết goals, tham số, user properties và default values theo plugin descriptor.

Đọc thêm web documentation đúng version vì:
- Parameter có thể đổi default;
- Một goal có thể được bind sẵn bởi packaging;
- Plugin version cũ có thể không hỗ trợ option mới;
- Một parameter có thể áp dụng cho goal A nhưng không có ở goal B.

### 5.2. Xem effective POM

```bash
mvn -B -ntp help:effective-pom -Doutput=effective-pom.xml
```

Dùng để xác minh inheritance và active profiles. Nó không tự chứng minh goal đã chạy. Xem thêm Maven build log để biết plugin executions thực tế.

### 5.3. Đánh giá plugin bên thứ ba

Một community plugin đáng dùng khi có release hợp lệ, source/repository đáng tin, license rõ, compatibility Maven/JDK, issue tracker và security fixes. Không chọn một plugin bỏ hoang hoặc lấy từ repository lạ chỉ vì rút ngắn được vài dòng XML.

## 6. Ví dụ nên cấu hình Enforcer, không viết plugin mới

Một tổ chức yêu cầu JDK từ 17 và Maven từ 3.9 trở lên. Maven Enforcer đã có built-in rules:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.3</version>
    <executions>
        <execution>
            <id>enforce-toolchain</id>
            <phase>validate</phase>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireMavenVersion>
                        <version>[3.9,)</version>
                    </requireMavenVersion>
                    <requireJavaVersion>
                        <version>[17,)</version>
                    </requireJavaVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là fragment thêm vào `<build><plugins>` của một POM, không phải file POM độc lập. Không nên tạo `CheckJdkMojo` riêng chỉ để kiểm điều kiện trên.

Những yêu cầu như giữ test coverage, chạy Checkstyle, build source JAR, tạo Javadoc JAR hoặc thêm source root cũng nên bắt đầu bằng các plugins hiện có.

## 7. Khi nào custom plugin thật sự hợp lý?

Một plugin mới có cơ sở khi nhiều yếu tố sau cùng đúng:

- **Logic doanh nghiệp mới:** Không có built-in plugin/goal diễn đạt trọn behavior cần thiết.
- **Gắn chặt Maven:** Cần project version, project basedir, artifact metadata, lifecycle phase, attached outputs hoặc reactor context.
- **Dùng nhiều repository:** Muốn policy/code dùng chung và upgrade theo một artifact version.
- **Parameter API rõ:** Người dùng có thể cấu hình hoặc override một số option hợp lệ.
- **Failure semantics rõ:** Maven fail khi vi phạm, có thông báo chỉ ra cách sửa.
- **Output deterministic:** Không âm thầm ghi clock/user/path/random vào artifacts.
- **Chi phí kiểm thử chấp nhận được:** Có unit và integration tests, kiểm Maven/JDK compatibility.
- **Có ownership:** Có người phụ trách security, release, migration, versioning và hỗ trợ users.

### Những dấu hiệu KHÔNG nên viết plugin

Nếu chỉ một lệnh Linux ở một repo, chưa rõ requirement, không có owner, hoặc built-in Enforcer rule giải quyết sạch, plugin riêng có thể gây nhiều chi phí hơn giá trị.

**Câu hỏi quyết định:** Logic đang thiếu thuộc *Maven behavior* hay chỉ là *một script có thể chạy ở bất cứ đâu*?

## 8. Bài thực hành: một policy đủ đặc thù để minh họa plugin

Giả sử team quy định:

- Mỗi project có file `config/release-policy.properties`.
- `release.channel` chỉ nhận `stable` hoặc `preview`.
- Version Maven kết thúc `-SNAPSHOT` phải dùng `preview`.
- Version không kết thúc `-SNAPSHOT` phải dùng `stable`.
- `release.owner` phải là ID đội hợp lệ, bắt đầu bằng chữ thường; phần còn lại cho phép chữ thường, số và dấu nối.

Đây là **policy ví dụ**, không phải quy định Maven. Nó phối hợp metadata project version, nội dung file và một business rule nhiều điều kiện. Vẫn có thể triển khai bằng **custom Enforcer rule**, nhưng ở đây ta cố ý tạo một Mojo độc lập để học Maven plugin packaging và lifecycle.

Ma trận kỳ vọng:

| Project version | Channel | Owner | Kết quả |
| --- | --- | --- | --- |
| `1.0.0` | `stable` | `platform` | PASS |
| `1.1.0-SNAPSHOT` | `preview` | `platform` | PASS |
| `1.0.0` | `preview` | `platform` | FAIL |
| `1.1.0-SNAPSHOT` | `stable` | `platform` | FAIL |
| `1.0.0` | `stable` | trống | FAIL |
| `1.0.0` | file không tồn tại | — | FAIL |

### 8.1. Cấu trúc workspace

```text
plugin-lab/
├── release-policy-maven-plugin/
│   ├── pom.xml
│   └── src/
│       ├── main/java/com/example/build/policy/
│       │   ├── PolicyValidator.java
│       │   └── CheckPolicyMojo.java
│       └── test/java/com/example/build/policy/
│           └── PolicyValidatorTest.java
└── sample-app/
    ├── pom.xml
    ├── config/release-policy.properties
    └── src/main/java/com/example/app/Main.java
```

Hai thư mục là **hai Maven projects độc lập**. Không có một root aggregator POM. Cần install hoặc publish plugin trước khi consumer resolve được goal.

### 8.2. POM hoàn chỉnh của plugin

Tạo `release-policy-maven-plugin/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.build</groupId>
    <artifactId>release-policy-maven-plugin</artifactId>
    <version>1.0.0</version>
    <packaging>maven-plugin</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-plugin-api</artifactId>
            <version>3.9.16</version>
            <scope>provided</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.maven.plugin-tools</groupId>
            <artifactId>maven-plugin-annotations</artifactId>
            <version>3.16.0</version>
            <scope>provided</scope>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-plugin-plugin</artifactId>
                <version>3.16.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là **POM đầy đủ**, có thể dùng với Maven 3.9.x và JDK 17 cùng repositories cho các artifacts đã ghim.

Điểm quan trọng:
- Packaging `maven-plugin` khác `jar` thông thường.
- `maven-plugin-api` cung cấp `AbstractMojo`, `MojoFailureException`, `MojoExecutionException`.
- `maven-plugin-annotations` cung cấp `@Mojo`, `@Parameter`, `LifecyclePhase`.
- Hai dependencies cho Maven Plugin API/annotations dùng `provided`, tránh đóng chúng như runtime dependencies của plugin.
- Maven Plugin Plugin `3.16.0` sinh plugin descriptor trong `process-classes` theo Maven plugin lifecycle.
- Maven Compiler Plugin ghim Java release 17, nghĩa là plugin **cần runtime JDK 17+** khi chạy trong Maven process.
- Surefire chạy JUnit tests ở giai đoạn test.
- Dù Maven Plugin API `3.9.16` là lựa chọn cho ví dụ, dự án production phải test mức Maven core tối thiểu và Maven 4 nếu tuyên bố support.

### 8.3. Tách business logic khỏi Maven: PolicyValidator.java

File `release-policy-maven-plugin/src/main/java/com/example/build/policy/PolicyValidator.java`:

```java
package com.example.build.policy;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public final class PolicyValidator {

    private PolicyValidator() {
    }

    public static void validate(Path file, String projectVersion)
            throws IOException {
        if (file == null || !Files.isRegularFile(file)) {
            throw new IllegalArgumentException("Release policy file is missing");
        }
        if (projectVersion == null || projectVersion.isBlank()) {
            throw new IllegalArgumentException("Project version is missing");
        }

        Properties values = new Properties();
        try (Reader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            values.load(reader);
        }

        String channel = values.getProperty("release.channel", "");
        String owner = values.getProperty("release.owner", "");

        if (!"stable".equals(channel) && !"preview".equals(channel)) {
            throw new IllegalArgumentException(
                    "release.channel must be stable or preview");
        }

        String expected = projectVersion.endsWith("-SNAPSHOT")
                ? "preview" : "stable";
        if (!expected.equals(channel)) {
            throw new IllegalArgumentException(
                    "Project version " + projectVersion
                    + " requires release.channel=" + expected);
        }

        if (!owner.matches("[a-z][a-z0-9-]*")) {
            throw new IllegalArgumentException(
                    "release.owner must be a lowercase team id");
        }
    }
}
```

Đây là **Java 17 compilable**. Không cần Maven container để unit-test phần business rule, vì logic chỉ đọc một `Path`, `String projectVersion` và ném exceptions cho cases không hợp lệ.

Các điểm kỹ thuật:
- `Properties.load(Reader)` đọc từ `Reader` UTF-8 đã cấu hình.
- So chuỗi bằng `"stable".equals(...)` để tránh NullPointerException.
- `-SNAPSHOT` là suffix của ví dụ. Nếu tổ chức có qualifier khác, cần mở rộng policy rõ.
- Không log toàn bộ file vì một policy file production có thể chứa dữ liệu nhạy cảm.
- Không tạo output ngẫu nhiên nên kiểm tra này deterministic nếu đầu vào ổn định.
- Nếu policy đòi reject duplicate properties, cần parser strict riêng; `Properties` mặc định có thể ghi đè key trùng. Đây là giới hạn đã biết của ví dụ.

### 8.4. Adapter cho Maven: CheckPolicyMojo.java

File `release-policy-maven-plugin/src/main/java/com/example/build/policy/CheckPolicyMojo.java`:

```java
package com.example.build.policy;

import java.io.File;
import java.io.IOException;

import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugin.MojoFailureException;
import org.apache.maven.plugins.annotations.LifecyclePhase;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;

@Mojo(
    name = "check-policy",
    defaultPhase = LifecyclePhase.VALIDATE,
    threadSafe = true
)
public final class CheckPolicyMojo extends AbstractMojo {

    @Parameter(
        property = "releasePolicy.file",
        defaultValue = "${project.basedir}/config/release-policy.properties",
        required = true
    )
    private File policyFile;

    @Parameter(
        defaultValue = "${project.version}",
        readonly = true,
        required = true
    )
    private String projectVersion;

    @Override
    public void execute()
            throws MojoExecutionException, MojoFailureException {
        try {
            PolicyValidator.validate(
                    policyFile.toPath(), projectVersion);
            getLog().info(
                    "Release policy valid for version " + projectVersion);
        } catch (IllegalArgumentException exception) {
            throw new MojoFailureException(exception.getMessage());
        } catch (IOException exception) {
            throw new MojoExecutionException(
                    "Cannot read release policy file", exception);
        }
    }
}
```

**Vai trò các annotations:**

| Annotation/API | Tác dụng |
| --- | --- |
| `@Mojo(name="check-policy")` | Đăng ký một Maven goal |
| `defaultPhase=LifecyclePhase.VALIDATE` | Chỉ ra phase mặc định của goal khi được bind |
| `threadSafe=true` | Tuyên bố goal an toàn cho parallel Maven khi implementation thực sự không dùng shared mutable state |
| `@Parameter(property="releasePolicy.file")` | Cho phép override file bằng Maven property |
| `${project.basedir}` | Đường dẫn file tương đối consumer project |
| `${project.version}` | Lấy version từ Maven project model |
| `getLog().info(...)` | Log qua API Maven, không `System.out.println` |
| `MojoFailureException` | Vi phạm policy, expected build failure |
| `MojoExecutionException` | I/O unexpected, lỗi execution |

**Quan trọng:** `@Mojo(defaultPhase=VALIDATE)` **không tự khiến mọi Maven project chạy goal đó**. Consumer cần khai báo plugin execution trong POM hoặc gọi full-coordinate goal trên command line.

**Thread safety:** Implementation chỉ đọc file của chính project và không dùng static mutable state, nên `threadSafe=true` hợp lý cho ví dụ. Một plugin ghi cùng shared file từ nhiều module không được công bố thread-safe chỉ vì có annotation.

### 8.5. Unit tests: PolicyValidatorTest.java

File `release-policy-maven-plugin/src/test/java/com/example/build/policy/PolicyValidatorTest.java`:

```java
package com.example.build.policy;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PolicyValidatorTest {

    @TempDir
    Path tempDir;

    private Path writePolicy(String text) throws Exception {
        Path file = tempDir.resolve("release-policy.properties");
        return Files.writeString(file, text, StandardCharsets.UTF_8);
    }

    @Test
    void stableReleasePasses() throws Exception {
        Path file = writePolicy(
                "release.channel=stable\nrelease.owner=platform\n");
        assertDoesNotThrow(
                () -> PolicyValidator.validate(file, "1.0.0"));
    }

    @Test
    void snapshotPreviewPasses() throws Exception {
        Path file = writePolicy(
                "release.channel=preview\nrelease.owner=platform\n");
        assertDoesNotThrow(
                () -> PolicyValidator.validate(file, "1.1.0-SNAPSHOT"));
    }

    @Test
    void previewOnReleaseFails() throws Exception {
        Path file = writePolicy(
                "release.channel=preview\nrelease.owner=platform\n");
        assertThrows(IllegalArgumentException.class,
                () -> PolicyValidator.validate(file, "1.0.0"));
    }

    @Test
    void missingOwnerFails() throws Exception {
        Path file = writePolicy("release.channel=stable\n");
        assertThrows(IllegalArgumentException.class,
                () -> PolicyValidator.validate(file, "1.0.0"));
    }

    @Test
    void missingFileFails() {
        Path file = tempDir.resolve("absent.properties");
        assertThrows(IllegalArgumentException.class,
                () -> PolicyValidator.validate(file, "1.0.0"));
    }
}
```

**Năm tests** gồm hai success cases và ba expected failure cases. `@TempDir` giúp mỗi test thao tác trong folder riêng. Đây là logic unit tests; chúng chưa kiểm Maven plugin descriptor, parameter injection hoặc lifecycle binding — phải chạy thêm một consumer project.

### 8.6. Build, test và install plugin

Đứng tại `plugin-lab`:

```bash
mvn -B -ntp -f release-policy-maven-plugin/pom.xml clean install
```

Khi môi trường/repositories phù hợp, kỳ vọng:
- Compile hai classes plugin/validator.
- Chạy **5 JUnit tests**, 0 failures/errors.
- Tạo descriptor qua `maven-plugin-plugin`.
- Đóng plugin JAR và install cùng POM vào **local Maven repository**.

Kiểm:

```bash
jar tf release-policy-maven-plugin/target/release-policy-maven-plugin-1.0.0.jar
```

Phải tìm entry:

```text
META-INF/maven/plugin.xml
```

File này ánh xạ goals/parameters cho Maven. **Có class `CheckPolicyMojo.class` nhưng thiếu descriptor không đủ để Maven dùng nó như plugin goal.**

Lệnh `mvn install` **không publish remote repository**. Nếu CI ở máy khác, phải publish/pluginRepositories hợp lệ hoặc install từ source trong pipeline.

## 9. POM consumer: dùng plugin như một quality gate

Tạo `sample-app/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.app</groupId>
    <artifactId>sample-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>com.example.build</groupId>
                <artifactId>release-policy-maven-plugin</artifactId>
                <version>1.0.0</version>
                <executions>
                    <execution>
                        <id>validate-release-policy</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>check-policy</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là POM consumer **độc lập**, version plugin đã ghim. Plugin dùng ở `<build><plugins>`, **không đặt vào `<dependencies>`** như library JAR.

Consumer bind goal vào phase `validate` để fail sớm trước compilation. Có thể override file bằng fragment **trong plugin**:

```xml
<configuration>
    <policyFile>${project.basedir}/config/service-release.properties</policyFile>
</configuration>
```

Hoặc user property `-DreleasePolicy.file=...`; hãy test precedence của các override quan trọng trong Maven version được hỗ trợ.

### 9.1. File sample-app/config/release-policy.properties

```properties
release.channel=stable
release.owner=platform
```

Với project version `1.0.0`, policy là hợp lệ.

### 9.2. File sample-app/src/main/java/com/example/app/Main.java

```java
package com.example.app;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from sample-app");
    }
}
```

Maven plugin chỉ kiểm policy trước compile; nó không tác động vào Java main.

### 9.3. Chạy consumer

Đã install plugin trước:

```bash
mvn -B -ntp -f sample-app/pom.xml validate
```

Log Maven khi success sẽ chứa:

```text
[INFO] Release policy valid for version 1.0.0
```

Đây **chỉ là một dòng log kỳ vọng**, không phải stdout toàn bộ Maven. Mức INFO và format prefix có thể thay đổi theo Maven version.

Build/verify:

```bash
mvn -B -ntp -f sample-app/pom.xml clean verify
```

Chạy Java từ root `plugin-lab`:

```bash
java -cp sample-app/target/classes com.example.app.Main
```

**Stdout chính xác của Java main:**

```text
Hello from sample-app
```

Không dùng `java -jar` khi chưa có `Main-Class` manifest; POM này chỉ tạo library-style JAR.

### 9.4. Thử một policy invalid

Trong một bản sao thực hành, thay file `.properties` thành:

```properties
release.channel=preview
release.owner=platform
```

Giữ POM version `1.0.0`, chạy:

```bash
mvn -B -ntp -f sample-app/pom.xml validate
```

**Kỳ vọng** Maven fail trong `validate` với phần thông báo:

```text
Project version 1.0.0 requires release.channel=stable
```

Vì `PolicyValidator` ném `IllegalArgumentException`, Mojo chuyển sang `MojoFailureException`. Đó là **expected policy failure**, không phải Maven dependency-resolution error.

Khôi phục `stable` sau khi test.

### 9.5. Thử SNAPSHOT hợp lệ

Đổi consumer version thành `1.1.0-SNAPSHOT`, policy:

```properties
release.channel=preview
release.owner=platform
```

Goal `check-policy` phải PASS, vì `projectVersion.endsWith("-SNAPSHOT")` là true. Đổi lại cả version và channel trước khi làm release production.

## 10. Kiểm thử plugin ở nhiều tầng

### Unit tests

`PolicyValidatorTest` đã kiểm domain logic mà không cần Maven process. Lợi ích là tests nhanh, rõ input và expected result.

### Plugin descriptor và injection

Sau `mvn package`, xem `META-INF/maven/plugin.xml`, goal `check-policy`, parameters `policyFile` và `projectVersion`. Nếu JAR không chứa descriptor, kiểm `<packaging>maven-plugin</packaging>`, `@Mojo` và Maven Plugin Plugin goal.

Có thể dùng Help Plugin để xem goal đã publish:

```bash
mvn -B -ntp -f sample-app/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:describe -Dplugin=com.example.build:release-policy-maven-plugin:1.0.0 -Dgoal=check-policy -Ddetail
```

### Integration tests

Cần test trên project consumer thật:
1. Release + stable: PASS.
2. SNAPSHOT + preview: PASS.
3. Release + preview: FAIL.
4. Missing file: FAIL.
5. Missing/invalid owner: FAIL.
6. Custom file override: đúng file.
7. Multi-module reactor: không lẫn project version/basedir.
8. Maven/JDK versions mục tiêu: plugin load thành công.
9. Parallel build nếu tuyên bố `threadSafe=true`.
10. Không in sensitive file contents vào logs.

**Apache Maven Plugin Testing Harness** giúp test Mojo/component injection; từ bản 3.4.0 dự án hỗ trợ JUnit 5 `MojoExtension` và `@MojoTest`. Với plugin production, thêm harness tests ngoài unit và CLI integration tests.

**Unit test thuần pass không đồng nghĩa Maven plugin chạy được.** Goal descriptor, Maven classloader, POM execution binding và repository lookup vẫn phải kiểm riêng.

## 11. Chọn lifecycle phase và cách gọi goal

Gọi riêng bằng full coordinates:

```bash
mvn -B -ntp -f sample-app/pom.xml com.example.build:release-policy-maven-plugin:1.0.0:check-policy
```

Hoặc bind vào consumer lifecycle:

```xml
<executions>
    <execution>
        <id>validate-release-policy</id>
        <phase>validate</phase>
        <goals>
            <goal>check-policy</goal>
        </goals>
    </execution>
</executions>
```

Fragment này đã có trong consumer POM. Các phase thường chọn:
- `validate`: check config/policy không cần classes.
- `generate-sources`: tạo Java source trước compile.
- `process-resources`: chuẩn bị resources cho artifact.
- `package`: xử lý artifact sau packaging.
- `verify`: kiểm hậu điều kiện sau tests/package.
- `deploy`: publish; cần đảm bảo credentials, quyền và release semantics.

**Không tạo một Mojo chạy lại `mvn clean verify` qua subprocess rồi tự bind vào `verify`**. Điều này có thể gây build đệ quy, double-execution, deadlock và diagnostics phức tạp. Fork lifecycle là kỹ thuật nâng cao, cần lý do chính đáng.

## 12. Plugin naming, prefix và distribution

Plugin ngoài Apache Maven nên theo convention `your-prefix-maven-plugin`, ví dụ `release-policy-maven-plugin`.

Dạng `maven-your-prefix-plugin` thường được dành cho official Apache Maven plugins (`org.apache.maven.plugins`), không nên đặt như vậy cho custom plugin.

Prefix `release-policy` có thể được suy từ artifactId và metadata của plugin group, nhưng short command:

```bash
mvn release-policy:check-policy
```

không phải lúc nào cũng resolve nếu Maven chưa biết plugin group, chưa có metadata hoặc settings thiếu `pluginGroups`.

**Khuyến nghị cho hướng dẫn và CI:** dùng full-coordinate syntax khi chạy lần đầu:

```bash
mvn com.example.build:release-policy-maven-plugin:1.0.0:check-policy
```

### Repositories và pluginRepositories

- `<pluginRepositories>` hoặc Maven settings/mirror dùng để tìm **build plugins**.
- `<repositories>` dùng cho **project dependencies**.
- `mvn install` chỉ lưu plugin JAR/POM vào **local** repository.
- `mvn deploy` mới publish plugin lên **remote**, nếu có distributionManagement/credentials và chính sách phát hành hợp lệ.

Một plugin chỉ tồn tại trong local repository của developer sẽ làm CI hoặc máy đồng nghiệp gặp `PluginResolutionException`. Đừng thay credentials bằng việc commit token trong POM.

## 13. Khi nào nên viết custom Enforcer rule thay vì Mojo?

**Enforcer rule** là lựa chọn gần nhất khi nhu cầu đơn giản là PASS/FAIL policy.

Chọn custom Enforcer rule nếu:
- Có một invariant, không sinh file hay artifact.
- Team đã dùng Maven Enforcer làm quality gate.
- Muốn tận dụng `enforcer:enforce` hiện có.
- Chỉ cần test policy, không cần độc lập plugin goals.

Chọn custom Maven plugin nếu:
- Cần nhiều goals có trách nhiệm khác nhau.
- Cần tích hợp project artifact, source roots hoặc output attachments.
- Muốn lifecycle API và parameter contract riêng.
- Có nhiều repo consumer, nhu cầu documentation/semantics chung.
- Có owner/team bảo trì và release.

**Ví dụ `check-policy` trong bài có thể dùng custom Enforcer rule.** Việc chọn Mojo chỉ để minh họa khi một nhóm quyết định cần standalone plugin goal; không phải kết luận Enforcer không làm được.

## 14. Script/CLI tool hay Maven plugin?

Một tool CLI độc lập có thể được gọi qua `exec-maven-plugin` hoặc `maven-antrun-plugin`. Đây là giải pháp hợp lý khi:
- Tool đã tồn tại và đã có tests;
- Không phải đọc Maven internals;
- Dùng trong một project hoặc workflow CI nhỏ;
- Có thể kiểm soát exit code, environment, timeout và paths.

Nhược điểm khi áp dụng rộng:
- Shell quoting khác Windows/Linux;
- Requires external language/runtime/toolchain;
- Script copies phân tán khó upgrade;
- Không có Maven plugin descriptor/parameter documentation;
- Logging, error classification, caching và lifecycle integration có thể kém rõ.

Nếu công việc phình thành nhiều shell commands lồng nhau, dùng lại trên nhiều repos, thì một plugin đúng nghĩa có thể giúp **đóng gói API và hạn chế sai lệch**. Nhưng không cần biến mọi CLI tool thành Maven plugin.

## 15. Plugin thường khác Maven core extension

Ordinary Maven plugin thực hiện một goal trong lifecycle. Core extension có thể được nạp từ `.mvn/extensions.xml` và can thiệp Maven session, event spying, resolution hay lifecycle internals.

**Không phát triển core extension** nếu chỉ muốn validate file, generate source, copy resource hoặc attach artifact bằng một Mojo. Core extension có compatibility/security impact lớn hơn, nên là lựa chọn hiếm khi các plugin goals không đáp ứng.

## 16. Vấn đề hiệu năng, tính tái lập và thread safety

### Thread safety

Nếu plugin được gắn ở nhiều modules, Maven có thể chạy các modules song song với `-T`. Một Mojo công bố `threadSafe=true` cần tránh:
- Static mutable caches chia sẻ giữa goals;
- Ghi cùng file global cho tất cả modules;
- Ghi vào local repo mà không có cơ chế lock;
- Dùng thư viện dependency vốn không thread-safe.

Ví dụ policy chỉ đọc file ở `project.basedir` và không có shared mutable state nên có cơ sở để threadSafe. Plugin tạo output phải ghi theo module path hoặc có synchronization rõ ràng.

### Reproducible outputs

Nếu plugin sinh code/artifacts:
- Sắp thứ tự file/entries ổn định;
- Dùng UTF-8, timezone/locale được kiểm soát;
- Không nhúng `Instant.now()`, username, hostname, absolute checkout path;
- Tôn trọng `project.build.outputTimestamp` khi dùng archive-aware tools;
- Đặt output trong `project.build.directory` (thường `target`) và tránh tự sửa tracked source files;
- Kiểm hai clean builds bằng hash/Artifact Plugin compare.

**Plugin chỉ đọc/validate** nên giữ logic deterministic; tránh network request không cache và dữ liệu thời gian hiện tại nếu policy không đòi.

### Logging, errors và bảo mật

Phân biệt:
- Policy violation có thể sửa → `MojoFailureException`.
- Lỗi file I/O/exception ngoài dự kiến → `MojoExecutionException`.
- Optional input có documented fallback → log rõ fallback.
- Required input thiếu → fail sớm.

Không catch `Exception` rồi coi là success. Không log secrets hoặc toàn bộ file properties. CI build plugins có quyền filesystem/network của runner, vì vậy plugin là **một rủi ro supply chain** cần security review.

## 17. Compatibility và versioning của plugin riêng

Khi plugin được dùng ở nhiều repos, những thứ sau là **API công khai của hệ thống build**:
- Goal name và parameter names;
- Defaults/user properties;
- Lifecycle phases, failure behavior;
- Maven/JDK runtime minimum;
- Output paths/formats;
- Plugin version và artifact location.

Một thay đổi tưởng nhỏ có thể phá consumers:
- Đổi `check-policy` sang `validate` mà không giữ alias.
- Đổi `policyFile` default directory.
- Chuyển plugin bytecode target từ Java 17 lên Java 21.
- Đổi warning thành failure mặc định.
- Bỏ `release.channel=preview` mà không có migration.

**Cần có:** changelog, compatibility matrix, release notes, deprecation window, migration docs và integration tests với các POM consumer thực tế.

### Cost/benefit trước khi release

| Phương án | Cost ban đầu | Cost lâu dài |
| --- | --- | --- |
| Configure plugin có sẵn | Thấp | Theo dõi version/plugin changes |
| Parent POM + Enforcer | Thấp–trung bình | Quản lý inheritance/profiles |
| Script/CLI | Thấp–trung bình | Cross-platform, environment/toolchain |
| Custom Enforcer rule | Trung bình | Rule API, tests, versioning |
| Custom Maven plugin | Cao hơn | API/compatibility, publishing, security, user support |
| Core extension | Rất cao | Maven core behavior/compatibility |

Không có con số tuyệt đối “trên 20 repos phải viết plugin”. Chọn dựa trên reuse, complexity, maintenance và rủi ro sai lệch giữa các dự án.

## 18. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm |
| --- | --- | --- |
| Goal không được tìm thấy | Thiếu descriptor hoặc sai `@Mojo(name=...)` | Kiểm JAR và `plugin.xml` |
| `No plugin descriptor found` | Dự án dùng `jar` thay vì `maven-plugin` hoặc descriptor goal lỗi | Kiểm packaging/Plugin Plugin |
| `No plugin found for prefix` | Maven không tìm group/prefix metadata | Dùng full coordinates |
| `PluginResolutionException` | Plugin chưa install/publish hoặc pluginRepositories sai | Kiểm local/remote repo |
| Goal không chạy khi `mvn validate` | Consumer chưa bind execution | Kiểm `<executions><phase>validate` |
| `policyFile` null | Parameter injection/descriptor sai | Help Plugin + integration test |
| JDK quá cũ | Plugin compiled Java 17 | Kiểm `mvn -version` |
| Business policy invalid | Validation chủ động fail | Sửa config/version |
| File unreadable | I/O error | Kiểm permissions/path |
| Test helper pass nhưng plugin fail | Chưa test descriptor/binding | Consumer integration |
| Plugin dùng `System.out` | Log không theo Maven conventions | `getLog()` |
| Logs có secrets | Log raw properties/user parameters | Redact, giới hạn log |
| `-T` gây race | Shared mutable state/global output | Kiểm thread safety |
| CI không resolve plugin | Chỉ install trên máy dev | Publish/CI install |
| Maven 4 upgrade fail | Plugin API/core compatibility khác | Test matrix trước |
| Plugin ở `<dependencies>` không chạy | Không được khai báo như build plugin | Đưa vào `<build><plugins>` |
| `pluginManagement` không làm goal chạy | Chỉ quản lý version/config | Bind/instantiate plugin |
| `BUILD SUCCESS` nhưng policy chưa chạy | Execution missing hoặc profile tắt | Kiểm build log |
| Plugin không tạo output mong muốn | Sai phase/basedir/permissions | Kiểm goal contract |
| File `target` ghi không ổn định | Timestamp/random/ordering | Reproducibility tests |

### Debug checklist

1. Ghi Maven/JDK/plugin GAV.
2. Đọc Maven plugin build log; kiểm 5 JUnit tests.
3. Kiểm `META-INF/maven/plugin.xml` trong JAR.
4. Dùng full coordinates gọi goal.
5. Xem `help:describe -Ddetail`.
6. Kiểm consumer execution binding.
7. Kiểm `@Parameter` values, defaults và path.
8. Phân biệt `MojoFailureException`/`MojoExecutionException`.
9. Chạy valid/invalid consumer integration tests.
10. Test các Maven/JDK versions được hỗ trợ.
11. Kiểm parallel behavior nếu threadSafe.
12. Rà soát security/logs trước khi publish.

## 19. Bài tập áp dụng

1. Một project chỉ muốn Java 17 và Surefire 3.5.4: có cần custom plugin? **Không**, dùng Compiler/Surefire và parent POM.
2. Cần fail build nếu Maven nhỏ hơn 3.9: nên dùng gì? **Enforcer requireMavenVersion**.
3. Muốn tạo source root mới: xem plugin nào trước? **Build Helper Maven Plugin**.
4. Có một CLI tool đã test, chỉ dùng một repo: lựa chọn nhẹ nhất? **exec/script** nếu phù hợp portability/security.
5. Có policy dùng chung 35 repos và cần đọc `project.version`: giải pháp nào? **Xem custom Enforcer rule trước**, rồi cân nhắc Mojo nếu cần API goals riêng.
6. Plugin có `@Mojo` nhưng JAR thiếu descriptor: Maven có biết goal không? **Không**.
7. Vì sao `@Mojo(defaultPhase=VALIDATE)` chưa đủ để consumer tự chạy? **Cần execution/binding**.
8. Consumer POM có plugin dưới `<dependencies>`: đúng không? **Không**, goals ở `<build><plugins>`.
9. `1.2.0-SNAPSHOT` với channel `stable` ở demo ra sao? **FAIL**, cần `preview`.
10. Plugin ghi một file toàn cục từ mọi module nhưng gắn `threadSafe=true`: đúng không? **Không**, cần sửa shared side effects.
11. Unit tests của PolicyValidator đều pass nhưng consumer fails: xem đâu? **Descriptor, parameters, plugin resolution, lifecycle binding**.
12. Khi Maven 3 chạy được nhưng Maven 4 fail, có thể tuyên bố support Maven 4 không? **Không**, phải test compatibility.
13. Java `Main` của consumer in gì? **Hello from sample-app**.
14. Khi policy file chứa secrets, có nên in `Properties` ra log? **Không**.
15. Một requirement có sẵn trong Enforcer và cần dùng ở 20 repo: parent POM hay custom plugin? **Ưu tiên parent+Enforcer**, không phát triển Mojo thừa.

## 20. Checklist trước khi viết hoặc phát hành plugin

- [ ] Requirement là behavior mới, không chỉ cấu hình lặp lại.
- [ ] Đã tìm docs/help:describe cho plugins hiện có.
- [ ] Đã xem parent POM, pluginManagement và profiles.
- [ ] Đã xem Enforcer built-in/custom rules.
- [ ] Đã cân nhắc script/CLI và các vấn đề portability.
- [ ] Có lợi ích reuse, lifecycle integration và owner rõ.
- [ ] Plugin đặt tên theo convention `...-maven-plugin`.
- [ ] Đã dùng `<packaging>maven-plugin</packaging>`.
- [ ] Goals `@Mojo` và parameters `@Parameter` có contract rõ.
- [ ] Maven Plugin Plugin tạo `META-INF/maven/plugin.xml`.
- [ ] Plugin API/annotations/Compiler versions được ghim.
- [ ] Có unit tests và integration tests trên consumer POM.
- [ ] Goals được bind vào phase đúng.
- [ ] Lỗi business và lỗi I/O được phân biệt.
- [ ] Không log secrets; không ghi ra filesystem ngoài phạm vi.
- [ ] Có test thread safety nếu tuyên bố parallel support.
- [ ] Có reproducibility strategy nếu sinh artifacts.
- [ ] Consumers có repository/pluginRepositories hợp lệ.
- [ ] Maven/JDK runtime compatibility được kiểm chứng.
- [ ] Có owner, changelog, migration plan và security review.
- [ ] ROI tốt hơn giải pháp cấu hình/custom rule nhẹ hơn.

**Kết luận:** Trước khi phát triển Maven plugin, hãy hỏi **plugin hiện có có goal/parameter đáp ứng không**, sau đó xem parent POM, Enforcer, build-helper và script/CLI. Khi thật sự cần domain-specific behavior được dùng lại qua nhiều builds, gắn sâu với Maven lifecycle/model và có testing/versioning/ownership, custom plugin có thể là lựa chọn đúng. Hãy thiết kế rõ `@Mojo`, `@Parameter`, descriptor, phases, exception semantics và consumer contract; đừng tạo một plugin mới chỉ để tránh học cấu hình Maven đã có.

## Tài liệu tham khảo chính thức

- [Apache Maven — Guide to Developing Java Plugins](https://maven.apache.org/guides/plugin/guide-java-plugin-development.html)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Plugin Plugin — Overview](https://maven.apache.org/plugin-tools/maven-plugin-plugin/)
- [Apache Maven Plugin Plugin — Java Annotations](https://maven.apache.org/plugin-tools/maven-plugin-plugin/examples/using-annotations.html)
- [Apache Maven Plugin Plugin — plugin:descriptor](https://maven.apache.org/plugin-tools/maven-plugin-plugin/descriptor-mojo.html)
- [Apache Maven — Plugin Prefix Resolution](https://maven.apache.org/guides/introduction/introduction-to-plugin-prefix-mapping.html)
- [Apache Maven Help Plugin — help:describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html)
- [Apache Maven Enforcer — Built-in Rules](https://maven.apache.org/enforcer/enforcer-rules/)
- [Apache Maven — Plugin Testing Harness](https://maven.apache.org/plugin-testing/maven-plugin-testing-harness/)
- [Apache Maven — Plugins Compatibility Plan](https://maven.apache.org/developers/compatibility-plan.html)