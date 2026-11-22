# Bổ sung git.properties bằng plugin phù hợp để truy vết commit trong Spring Boot

## 1. Tại sao cần gắn Git commit vào artifact?

Một microservice Spring Boot có thể trả lời `/actuator/health` là `UP`, nhưng khi sự cố xảy ra đội vận hành vẫn phải trả lời: **JAR này được build từ commit nào?** Hai ứng dụng cùng mang version `1.0.0` chưa chắc có cùng mã nguồn nếu chúng được build từ hai Git revisions khác nhau, hoặc một phiên bản đã được rebuild từ working tree chưa commit.

Thông tin Git commit trong artifact giúp:

- Đối chiếu tiến trình đang chạy với source revision và release pipeline.
- Tìm chính xác commit đã đưa một thay đổi vào production hoặc staging.
- So sánh các pod/nodes của cùng service để phát hiện rollout chưa đồng nhất.
- Liên kết log sự cố, issue, pull request và CI build với một source revision.
- Kiểm chứng rằng **file executable JAR được deploy** chứa metadata của commit vừa build, thay vì dựa vào tên file hay thông tin in trên CI console.
- Hỗ trợ rollback, điều tra regression và cung cấp thêm bằng chứng cho provenance của bản phát hành.

Giải pháp thông dụng trong Maven là dùng **Git Commit Id Maven Plugin** (tọa độ hiện hành `io.github.git-commit-id:git-commit-id-maven-plugin`) để tạo file `git.properties` trong output classpath, sau đó Spring Boot có thể tạo bean `GitProperties` và đưa thông tin phù hợp lên Actuator `/actuator/info`.

Bài thuộc mục **Metadata bản dựng** trong chủ đề **Spring Boot Build Tooling Packaging**. Sau bài này, bạn có thể:

1. Hiểu `git.properties`, file phải nằm ở đâu trong plain JAR và Spring Boot executable JAR.
2. Cấu hình plugin Maven có version cụ thể, phase phù hợp, output path và allowlist metadata.
3. Tạo ứng dụng Java 17+/Spring Boot với endpoint đọc commit và Actuator `info`.
4. Kiểm tra metadata ở `target/classes` và **trong `BOOT-INF/classes/git.properties` của JAR đã đóng gói**.
5. So commit ghi trong archive với `git rev-parse HEAD` và giải thích các sai khác do shallow clone, detached HEAD, working tree dirty.
6. Tránh lộ thông tin không cần thiết khi xuất Git metadata qua HTTP và khi phát hành JAR cho người khác.
7. Phân biệt `git.properties` với `build-info.properties`, version Maven, checksum artifact và bằng chứng ký/phát hành.
8. Thiết kế bước CI fail-fast khi thiếu Git metadata hoặc plugin tạo metadata không khớp commit.

**Bộ minh họa:** Java `17`, Spring Boot `3.5.16`, Maven `3.9+` và Git Commit Id Maven Plugin `10.0.1`. Đây là một tổ hợp được chọn để giải thích cấu hình, không phải yêu cầu mọi dự án đều nâng phiên bản. Plugin 10.0.1 có trên Maven Central; bản major 10 đã có thay đổi yêu cầu Maven 3.9+, vì vậy **kiểm tra build tool của dự án trước khi nâng**.

## 2. git.properties là gì và được dùng khi nào?

`git.properties` là một tài nguyên dạng Java Properties chứa metadata được trích từ **Git repository ở thời điểm build**. Ví dụ **minh họa**:

~~~properties
git.branch=main
git.commit.id=0123456789abcdef0123456789abcdef01234567
git.commit.id.abbrev=0123456
git.commit.time=2025-06-10T08:30:00Z
~~~

**Các giá trị ở ví dụ không phải commit của dự án người học.** Khi chạy plugin thật, id/branch/commit time được đọc từ repository hiện tại; chúng phụ thuộc commit, cách checkout và plugin configuration. Không chép một SHA giả vào `src/main/resources/git.properties` để giả vờ đã truy vết.

Cấu trúc quan trọng:

| Thuộc tính | Ý nghĩa | Độ ổn định và giới hạn |
| --- | --- | --- |
| `git.commit.id` | Full Git object ID của commit đang được chọn | Là khóa truy vết quan trọng nhất; với repository SHA-1 thường 40 ký tự hex, repo SHA-256 có thể dài hơn |
| `git.commit.id.abbrev` | Git commit id rút gọn | Tiện hiển thị nhưng có thể va chạm; dùng full id khi đối chiếu chính xác |
| `git.commit.time` | Thời gian của commit theo Git | Không phải thời điểm deploy hoặc thời điểm JVM start |
| `git.branch` | Tên branch theo metadata checkout | Có thể khác giữa local và CI; trong detached HEAD có thể không phải tên branch release |
| `git.dirty` | Trạng thái working tree tại build nếu cho phép sinh thuộc tính này | Hữu ích để cảnh báo build ngoài commit; **không thay** kiểm tra trực tiếp Git status trước release |
| `git.build.time` | Thời điểm plugin chạy build | Có thể thay đổi ở mỗi lần build; cần cân nhắc yêu cầu reproducibility |

Trong ví dụ chính, chúng ta chủ động chỉ giữ **commit id, id rút gọn, commit time và branch**. Các trường như email người commit, commit message đầy đủ, tên người build, hostname hay remote URL **không cần thiết** cho nhu cầu xác định revision của service và có thể bị lộ nếu đưa vào artifact.

### 2.1. git.properties không phải build-info.properties

| Tài nguyên | Bên tạo điển hình | Thông tin trọng tâm | Spring Boot cung cấp |
| --- | --- | --- | --- |
| `git.properties` tại **gốc classpath** | `git-commit-id-maven-plugin` hoặc plugin Git tương đương | Git revision, branch, commit time... | `GitProperties`, Actuator `GitInfoContributor` |
| `META-INF/build-info.properties` | Spring Boot Maven goal `build-info` hoặc Gradle `bootBuildInfo` | Tên, group, version và thời điểm build | `BuildProperties`, Actuator `BuildInfoContributor` |
| `META-INF/MANIFEST.MF` | JAR/WAR archiver và Spring Boot repackage | `Main-Class`, `Start-Class`, các manifest attributes | Dùng để khởi chạy/inspect archive |
| SHA-256 artifact | Tool tính hash trên **file JAR thực tế** | Danh tính byte-level của artifact | Không tự có chỉ nhờ Git plugin |

Git commit là **định danh source revision**, còn artifact checksum là **định danh bytes của file được phát hành**. Hai lần build cùng commit vẫn có thể cho artifact khác nhau nếu timestamp, dependencies hoặc compiler behavior không được kiểm soát. Tạo `git.properties` **không tự làm build reproducible**.

### 2.2. File xuất hiện ở đâu?

Trong dự án Maven Spring Boot tiêu chuẩn:

~~~text
Git repository + pom.xml
             |
             v
git-commit-id-maven-plugin:revision
             |
             v
target/classes/git.properties
             |
             v
Maven jar + spring-boot:repackage
             |
             v
target/commit-trace-demo-1.0.0.jar
  BOOT-INF/classes/git.properties
  BOOT-INF/classes/demo/Application.class
  BOOT-INF/classes/demo/VersionController.class
  BOOT-INF/lib/...
~~~

Đường dẫn `BOOT-INF/classes` áp dụng với **Spring Boot executable JAR layout** thường gặp. Đối với executable WAR, application classpath resource thường nằm ở `WEB-INF/classes/git.properties`. Nếu chỉ kiểm tra một file sinh trong `target/` rồi không tìm thấy nó trong archive, chưa thể kết luận runtime sẽ nhận được Git metadata.

## 3. Chọn đúng plugin Maven và hiểu thay đổi tọa độ

### 3.1. Plugin được dùng trong bài

Sử dụng tọa độ:

~~~text
groupId    : io.github.git-commit-id
artifactId : git-commit-id-maven-plugin
version    : 10.0.1
goal       : revision
~~~

Plugin này chuyên trích Git repository information và có khả năng xuất `git.properties`. Tài liệu project minh họa `<generateGitPropertiesFile>true</generateGitPropertiesFile>` cùng `<generateGitPropertiesFilename>${project.build.outputDirectory}/git.properties</generateGitPropertiesFilename>`.

Bản 10.x yêu cầu Maven `3.9+` (và Java đủ mới cho plugin); Java17 của ví dụ đáp ứng phần Java. Nếu dự án đang ở Maven cũ, hãy xem compatibility matrix và release notes để chọn **bản plugin phù hợp** hoặc nâng Maven/Wrapper có kiểm soát, không sao chép version này một cách máy móc.

### 3.2. Gặp plugin cũ thì làm sao?

Có thể bắt gặp tọa độ đời trước như:

~~~xml
<groupId>pl.project13.maven</groupId>
<artifactId>git-commit-id-plugin</artifactId>
~~~

Đây là tên/nhóm từng được sử dụng trong các project cũ; không phải plugin khác nên cài song song theo thói quen. Khi thấy cả hai trong effective POM, phải xác định cơ chế đang chạy, tránh hai execution cùng ghi một `git.properties` theo cách có thể ghi đè.

Spring Boot `spring-boot-starter-parent` phiên bản hiện đại cũng có plugin configuration được quản lý. Tài liệu Spring Boot hướng dẫn chỉ cần **khai báo plugin** khi dùng parent; trong ví dụ này thêm version/configuration tường minh để cách lọc field dễ thấy. **Không thêm hai execution `revision` trùng nhau** nếu parent đã cấu hình execution; kiểm tra `mvn help:effective-pom` khi project có parent hoặc profile phức tạp.

### 3.3. Tại sao không tự chạy git rồi append vào file?

Bạn có thể tự viết script gọi `git rev-parse HEAD`, nhưng script phải xử lý shell quoting, detached HEAD, working trees, shallow clones, Windows vs POSIX, encoding, missing repository và vị trí resource trong output. Plugin chuyên dụng đã tích hợp Maven lifecycle và cơ chế xuất các properties cần thiết. Dùng plugin giúp giảm custom code, **không miễn** việc kiểm tra Git metadata cuối và xử lý CI/environment.

## 4. Điều kiện đầu vào: phải build từ Git repository có commit

Để plugin tạo metadata có ý nghĩa, hãy build từ **Git working tree có commit** mà phiên bản plugin có thể truy cập metadata. Chỉ có source files mà không có `.git` thì plugin không thể tự biết một SHA đáng tin.

Trong repo đã có commit:

~~~bash
git rev-parse HEAD
git status --short
git branch --show-current
mvn -version
java -version
~~~

Giải thích:

- `git rev-parse HEAD` cho commit **đang được checkout**, dùng làm giá trị chuẩn đối chiếu với `git.commit.id`.
- `git status --short` liệt kê tracked/untracked changes; bản release muốn truy vết đầy đủ nên kiểm soát working tree sạch hoặc báo rõ mọi thay đổi chưa commit.
- `git branch --show-current` có thể in trống khi ở detached HEAD — điều rất bình thường trong CI.
- `mvn -version` cho thấy Maven version và Java mà Maven đang sử dụng.
- `java -version` cho biết Java trên terminal; nếu có nhiều JDK, xác nhận cả Maven JVM/toolchains.

Nếu chỉ tạo một folder source chưa chạy `git init` và `git commit`, không có commit ID hợp lệ để sinh. Trong bài tập độc lập ở mục 5, cần **tạo commit trước** khi gọi Maven build.

**Lưu ý về worktrees/submodules:** `.git` có thể là một **file trỏ đến Git directory thực** chứ không phải thư mục con. Tránh hardcode tùy tiện `${project.basedir}/.git` khi module hoặc worktree dùng layout khác; để plugin tìm Git metadata theo cơ chế của nó, rồi kiểm tra trong môi trường thật.

## 5. Ví dụ đầy đủ: Maven + Spring Boot + git.properties

Ví dụ là một HTTP application Spring Boot nhỏ. Người học sẽ tạo Git commit, build executable JAR, kiểm tra file Git trong artifact và gọi endpoint trả về commit.

### 5.1. Cấu trúc

~~~text
commit-trace-demo/
  pom.xml
  VerifyGitProperties.java
  src/
    main/
      java/
        demo/
          Application.java
          VersionController.java
      resources/
        application.properties
~~~

Sau khi chạy `git init`/`git commit` còn có Git repository metadata. File `VerifyGitProperties.java` nằm ở **project root** và là công cụ QA độc lập dùng Java 17 source-file launcher, không được compile vào Spring Boot JAR.

### 5.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>commit-trace-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>io.github.git-commit-id</groupId>
                <artifactId>git-commit-id-maven-plugin</artifactId>
                <version>10.0.1</version>
                <configuration>
                    <generateGitPropertiesFile>true</generateGitPropertiesFile>
                    <generateGitPropertiesFilename>${project.build.outputDirectory}/git.properties</generateGitPropertiesFilename>
                    <commitIdGenerationMode>flat</commitIdGenerationMode>
                    <includeOnlyProperties>
                        <includeOnlyProperty>^git.commit.id$</includeOnlyProperty>
                        <includeOnlyProperty>^git.commit.id.abbrev$</includeOnlyProperty>
                        <includeOnlyProperty>^git.commit.time$</includeOnlyProperty>
                        <includeOnlyProperty>^git.branch$</includeOnlyProperty>
                    </includeOnlyProperties>
                    <failOnNoGitDirectory>true</failOnNoGitDirectory>
                    <failOnUnableToExtractRepoInfo>true</failOnUnableToExtractRepoInfo>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao cấu hình này có ý nghĩa?**

- `spring-boot-starter-parent` quản lý Spring Boot dependency/plugin versions và pre-configures Git Commit Id Plugin. Khi khai báo plugin trong `<build><plugins>`, dùng cấu hình `revision` được parent kế thừa; **không nhất thiết phải chèn thêm execution thủ công** trong POM có parent này.
- `<version>10.0.1</version>` pin plugin cụ thể cho bộ Maven3.9+/Java17. Trên hệ thống đang dùng Maven cũ, phải điều chỉnh plugin và parent theo compatibility requirements.
- `generateGitPropertiesFile=true` khiến plugin **viết file** thay vì chỉ tạo Maven project properties cho resource filtering.
- `generateGitPropertiesFilename` trỏ đến **gốc classpath output** `target/classes/git.properties`, để Spring Boot có thể tự tìm qua `classpath:/git.properties`.
- `commitIdGenerationMode=flat` xuất khóa `git.commit.id` (không phải `git.commit.id.full`). Trong plugin, tùy chọn `full` của property này chuyển tên khóa thành `git.commit.id.full` để hỗ trợ JSON nested-object structure; nó **không** có nghĩa `flat` chỉ giữ SHA ngắn. Với ví dụ `GitProperties.getCommitId()` chúng ta muốn khóa `git.commit.id` rõ ràng.
- `includeOnlyProperties` là danh sách **regex cho tên properties**, giới hạn output. Đây là lớp kiểm soát tránh vô tình nhúng email, remote URL, commit message hoặc username. Dấu `^` và `$` giúp pattern match chính xác tên khóa.
- `failOnNoGitDirectory`/`failOnUnableToExtractRepoInfo` được đặt `true` để release build **không âm thầm phát hành một JAR thiếu Git metadata**. Nếu pipeline build từ source archive không có `.git`, phải thiết kế nguồn commit identity tin cậy khác và kiểm chứng, không lặng lẽ tắt fail.
- Plugin `spring-boot-maven-plugin` cùng Boot parent đóng gói JAR executable ở phase `package`. Git file được sinh trước packaging nên có thể vào `BOOT-INF/classes`.

**Chú ý về parent/no-parent:** Nếu POM không kế thừa `spring-boot-starter-parent`, bạn cần cấu hình tường minh phase `initialize`/goal `revision` cho Git plugin cũng như goal `repackage` của Spring Boot plugin. Đoạn cấu hình độc lập đó được nêu ở mục 12.

### 5.3. Application.java

Tạo `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Đây là main class hợp lệ cho ứng dụng Spring MVC/Spring Boot.

### 5.4. VersionController.java

Tạo `src/main/java/demo/VersionController.java`:

~~~java
package demo;

import org.springframework.boot.info.GitProperties;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VersionController {

    private final GitProperties gitProperties;

    public VersionController(GitProperties gitProperties) {
        this.gitProperties = gitProperties;
    }

    @GetMapping(value = "/version",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String version() {
        String commit = gitProperties.getCommitId();
        if (commit == null || commit.isBlank()) {
            throw new IllegalStateException(
                    "git.commit.id was not packaged");
        }
        return "git.commit.id=" + commit + "\n";
    }
}
~~~

Bean `GitProperties` được Spring Boot auto-configure khi `git.properties` có mặt ở **gốc classpath** và cấu hình auto-configuration tương ứng được áp dụng. Vì controller yêu cầu constructor injection, **nếu thiếu GitProperties bean, ứng dụng không khởi động thành công** — một lựa chọn fail-fast có chủ đích cho bản demo.

`getCommitId()` trả commit id từ metadata; không cần tự chạy Git trong ứng dụng đã phát hành. Runtime container/image **không cần mang `.git`** khi `git.properties` đã được đóng gói lúc build.

Endpoint `/version` của ví dụ chỉ trả SHA để tránh phát tán thông tin không cần thiết. Phản hồi có **một dòng**, ví dụ:

~~~text
git.commit.id=<commit SHA thực tế của checkout>
~~~

Phần trong dấu `<...>` là ký hiệu mô tả, không phải stdout literal. Giá trị chính xác tùy repository và có thể xác nhận bằng `git rev-parse HEAD`. Không tự bịa SHA rồi ghi như một output đã được kiểm chứng.

### 5.5. application.properties

Tạo `src/main/resources/application.properties`:

~~~properties
management.endpoints.web.exposure.include=health,info
management.info.git.enabled=true
server.address=127.0.0.1
server.port=8085
~~~

Giải thích:

- `management.endpoints.web.exposure.include=health,info` mở rộng Actuator HTTP exposure để có thể gọi `/actuator/info` trong môi trường demo. Theo mặc định, Actuator thường chỉ expose `health` qua web.
- `management.info.git.enabled=true` bật Git info contributor; khi có `git.properties` đúng path, Boot có thể hiển thị metadata.
- `server.address=127.0.0.1` giới hạn ứng dụng demo trên loopback, tránh phơi endpoint ra mạng bên ngoài.
- `server.port=8085` giảm khả năng xung đột với server khác ở 8080; khi cổng đã được dùng, có thể truyền `--server.port=...` lúc chạy.

Đối với production, **không đưa ra kết luận rằng Actuator `info` luôn nên public**. Việc bật exposure phải đi cùng policy mạng, authentication/authorization và đánh giá dữ liệu sẽ bị lộ.

## 6. Tạo Git commit rồi build executable JAR

### 6.1. Nếu thư mục bài tập chưa là Git repository

Từ root chứa `pom.xml` và các file đã tạo:

~~~bash
git init
git add pom.xml src/main/java/demo/Application.java src/main/java/demo/VersionController.java src/main/resources/application.properties
git -c user.name="Demo Author" -c user.email="demo@example.invalid" commit -m "Add Git metadata demo"
~~~

`git init` tạo repository. `git add` chỉ stage **những file cần thiết**, không tự thêm `target/` hoặc secrets. `git -c user.name=... -c user.email=... commit` đặt identity chỉ cho commit minh họa và không sửa global Git configuration; địa chỉ `example.invalid` là miền ví dụ dành cho tài liệu.

Nếu repo đã có Git history, **không chạy lại `git init`/commit chỉ để làm bài**. Chỉ xác nhận `git rev-parse HEAD` trỏ đến revision muốn phát hành và working tree sạch theo policy.

### 6.2. Xác nhận dữ liệu đầu vào

~~~bash
git rev-parse HEAD
git status --short
mvn -version
~~~

Với bài tập mới commit xong, `git status --short` thường không in dòng nào nếu working tree sạch. `git rev-parse HEAD` in một mã commit tùy repo, **không thể ấn định trước**. Lệnh `mvn -version` phải cho thấy Maven phù hợp với plugin 10.0.1 và Java phù hợp với Spring Boot 3.5.

### 6.3. Build

~~~bash
mvn clean package
~~~

Kết quả chính cần tìm:

~~~text
target/classes/git.properties
target/commit-trace-demo-1.0.0.jar
~~~

Đường dẫn `target/classes/git.properties` chỉ ra plugin đã tạo metadata ở output classpath. File `target/commit-trace-demo-1.0.0.jar` là executable archive do Boot plugin tạo theo package lifecycle. Nếu Maven Wrapper đã được repo cấu hình, dùng `./mvnw clean package` trên Linux/macOS hoặc `.\mvnw.cmd clean package` trong PowerShell; Wrapper cũng cần được pin một phiên bản Maven tương thích.

Có thể xem file Git tại build output:

~~~bash
cat target/classes/git.properties
~~~

Trên PowerShell:

~~~powershell
Get-Content .\target\classes\git.properties
~~~

**Không mặc định nội dung các khóa luôn theo thứ tự cụ thể**; Java Properties không bảo đảm một trật tự trình bày có ý nghĩa nghiệp vụ. Hãy xác nhận tên trường và giá trị commit thay vì so text theo thứ tự dòng.

## 7. Kiểm tra git.properties đã thực sự nằm trong executable JAR

Nếu chỉ thấy `target/classes/git.properties` chưa đủ, vì packaging hoặc exclude rules vẫn có thể khiến file bị thiếu ở JAR cuối. Kiểm tra bằng JDK:

~~~bash
jar tf target/commit-trace-demo-1.0.0.jar
~~~

Trong danh sách archive entry Spring Boot JAR cần có:

~~~text
BOOT-INF/classes/git.properties
BOOT-INF/classes/demo/Application.class
BOOT-INF/classes/demo/VersionController.class
BOOT-INF/lib/...
~~~

Danh sách trên là **minh họa rút gọn**, không phải output nguyên văn của `jar tf`. File `git.properties` nằm trong application classpath của Boot nested archive. Đây là file **được đóng gói lúc build**, không phải file sẽ được runtime tái tạo từ Git.

### 7.1. Java 17 validator độc lập và kết quả xác định

Tạo `VerifyGitProperties.java` ở project root:

~~~java
import java.io.InputStream;
import java.nio.file.Path;
import java.util.Properties;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public class VerifyGitProperties {

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java VerifyGitProperties.java "
                    + "<jar-path> <expected-commit>");
        }

        Path path = Path.of(args[0]);
        String expected = args[1].trim();
        String entryName =
                "BOOT-INF/classes/git.properties";

        try (ZipFile zip = new ZipFile(path.toFile())) {
            ZipEntry entry = zip.getEntry(entryName);
            if (entry == null) {
                throw new IllegalStateException(
                        "Missing JAR entry: " + entryName);
            }

            Properties properties = new Properties();
            try (InputStream in = zip.getInputStream(entry)) {
                properties.load(in);
            }

            String actual = properties.getProperty(
                    "git.commit.id");
            if (actual == null || actual.isBlank()) {
                throw new IllegalStateException(
                        "git.commit.id is missing");
            }
            if (!expected.equals(actual)) {
                throw new IllegalStateException(
                        "Commit mismatch: expected=" + expected
                                + ", actual=" + actual);
            }

            System.out.println(
                    "git.properties.present=true");
            System.out.println(
                    "git.commit.id.matches=true");
        }
    }
}
~~~

Program chỉ dùng **Java Standard Library**, không import Spring. Nó đọc trực tiếp ZIP entry `BOOT-INF/classes/git.properties` từ **file JAR đã đóng gói**, so sánh giá trị `git.commit.id` với commit được truyền vào. Nếu file thiếu, property thiếu hoặc SHA không đúng, ném exception, Java launcher trả exit code khác 0.

Chạy trên Linux/macOS hoặc POSIX shell:

~~~bash
java VerifyGitProperties.java \
  target/commit-trace-demo-1.0.0.jar \
  "$(git rev-parse HEAD)"
~~~

Có thể viết trong **một dòng** nếu shell không hỗ trợ dấu tiếp dòng `\`. Trên Windows PowerShell:

~~~powershell
$commit = (git rev-parse HEAD).Trim()
java VerifyGitProperties.java .\target\commit-trace-demo-1.0.0.jar $commit
~~~

Với file **đúng và commit khớp**, stdout chính xác:

~~~text
git.properties.present=true
git.commit.id.matches=true
~~~

Hai dòng này không chứa SHA cụ thể nên output có thể xác định trước khi biết commit. Nếu SHA khác, validator báo FAIL và hiển thị expected/actual để tìm sai file, Git checkout, plugin configuration hoặc artifact cũ.

**Điểm cốt lõi:** so `git.commit.id` trong JAR với Git `HEAD` tại build checkout. Đừng chỉ kiểm tra `git.properties` “có tồn tại”, bởi một file metadata cũ/stale có thể bị sao chép vào archive và làm mọi truy vết sai.

### 7.2. Nếu mục tiêu là WAR thay vì JAR

Trong Spring Boot executable WAR, application resources thường nằm ở `WEB-INF/classes/git.properties`, không phải `BOOT-INF/classes/git.properties`. Cần thay `entryName` tương ứng trong validator, giữ logic so commit. External servlet container cũng đọc `git.properties` từ application classpath, nhưng cơ chế khởi động của WAR khác executable JAR.

Đừng viết một validator kiểm tra `target/classes` rồi mặc nhiên báo PASS cho WAR/JAR cuối; luôn kiểm tra **artifact sẽ được phát hành**.

## 8. Kiểm chứng runtime: /version và /actuator/info

### 8.1. Chạy executable JAR

Từ project root:

~~~bash
java -jar target/commit-trace-demo-1.0.0.jar
~~~

Ứng dụng dùng port 8085 và bind loopback theo cấu hình minh họa. Sau khi Spring Boot startup thành công, ở terminal khác gọi:

~~~bash
curl -fsS http://127.0.0.1:8085/version
curl -fsS http://127.0.0.1:8085/actuator/info
~~~

Với `/version`, body có dạng:

~~~text
git.commit.id=<full Git commit ID>
~~~

Giá trị trong `<...>` **khác nhau theo repo**, nên đó là ký hiệu minh họa chứ không phải stdout literal. So nó với `git rev-parse HEAD` từ checkout build. Khi kết thúc test, dừng Java process ở terminal đầu tiên.

### 8.2. Actuator Git information

Spring Boot Actuator có `GitInfoContributor`, có thể auto-configure từ bean `GitProperties`. Khi `git.properties` có mặt ở gốc classpath, `management.info.git.enabled=true` và `info` endpoint được expose cho HTTP, response của `GET /actuator/info` chứa nhánh `git` với các thuộc tính được phép.

Với file ở mục 5, response có thể chứa `branch`, `commit.id` và `commit.time`. **Không hardcode một JSON response nguyên văn**: SHA, branch, time là dữ liệu thực, còn serialization và mức độ expose có thể phụ thuộc Spring Boot version/configuration.

Theo tài liệu Spring Boot, mặc định Git contributor chỉ expose tập rút gọn như `git.branch`, `git.commit.id` và `git.commit.time` nếu các property hiện diện. Đặt:

~~~properties
management.info.git.mode=full
~~~

có thể yêu cầu expose toàn bộ thuộc tính trong `git.properties`, nhưng **không nên bật như một thói quen** vì metadata đầy đủ có thể bao gồm email, hostname, remote URL hoặc commit message. Bài minh họa đã allowlist ở plugin để giảm dữ liệu nhạy cảm.

**Spring Boot có Actuator không đồng nghĩa `info` được expose qua web mặc định.** Cần kiểm tra `management.endpoints.web.exposure.include=health,info` và security/access policy. Nếu endpoint trả `404`, `401` hoặc `403`, lỗi có thể nằm ở exposure/security, không nhất thiết thiếu Git file.

### 8.3. Đọc GitProperties trực tiếp trong application

Khi `GitProperties` bean có mặt, app code có thể gọi:

~~~java
String revision = gitProperties.getCommitId();
String shortRevision = gitProperties.getShortCommitId();
String branch = gitProperties.getBranch();
java.time.Instant commitTime = gitProperties.getCommitTime();
~~~

Đây là **snippet bên trong bean/controller có biến `gitProperties` đã được inject** như ví dụ `VersionController`, không phải file Java độc lập. Các getter có thể trả `null` nếu property tương ứng không tồn tại; vì thế code dùng ở nghiệp vụ hoặc log nên xử lý trạng thái thiếu dữ liệu theo policy.

`getCommitTime()` parse thời điểm commit thành `Instant` khi định dạng phù hợp; nếu file dùng format thời gian lạ, phải kiểm tra plugin `dateFormat`/`dateFormatTimeZone` và Spring Boot parser. Tài liệu Spring Boot khuyến nghị timestamp theo định dạng ISO 8601 được hỗ trợ. **Đừng nhầm commit time với deployment time**.

## 9. Maven lifecycle: vì sao file phải sinh trước packaging?

Bài thực hành dựa trên Spring Boot starter parent, đã cấu hình plugin tương ứng. Về mặt logic, thứ tự mong muốn là:

~~~text
Git metadata có sẵn ở build workspace
        |
        v
Maven initialize: Git revision information
        |
        v
git.properties được sinh vào target/classes
        |
        v
Maven compile/resources/package
        |
        v
Spring Boot repackage executable JAR
        |
        v
BOOT-INF/classes/git.properties
        |
        v
Runtime GitProperties + Actuator/info
~~~

Nếu plugin chỉ tạo file ở `target/git.properties` mà không được add làm resource, JAR có thể không chứa nó. Nếu plugin bị bind **sau** `package`, sẽ quá muộn để đưa metadata vào executable archive cùng build pass. Nếu tùy biến Maven lifecycle quá mức, phải xem effective plugin execution order.

### 9.1. No-parent POM: execution tường minh

Nếu **không** dùng `spring-boot-starter-parent`, cần tự cấu hình goal/phase. Đây là **fragment Maven plugin** (không phải POM đầy đủ):

~~~xml
<plugin>
    <groupId>io.github.git-commit-id</groupId>
    <artifactId>git-commit-id-maven-plugin</artifactId>
    <version>10.0.1</version>
    <executions>
        <execution>
            <id>git-revision</id>
            <phase>initialize</phase>
            <goals>
                <goal>revision</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <generateGitPropertiesFile>true</generateGitPropertiesFile>
        <generateGitPropertiesFilename>${project.build.outputDirectory}/git.properties</generateGitPropertiesFilename>
        <commitIdGenerationMode>flat</commitIdGenerationMode>
    </configuration>
</plugin>
~~~

Bạn còn phải quản lý versions/dependencies, compiler, resources và `spring-boot:repackage` goal trong no-parent project. Đừng chép cả fragment này vào POM bài mẫu **nếu execution tương tự đã được parent cung cấp**, vì nó có thể tạo hai lần chạy hoặc làm output khó kiểm soát. Với multi-module builds, xem phần 11.

### 9.2. Giữ đúng tính năng mà không lọc text thủ công

Bạn **không cần** đặt `git.properties` template trong `src/main/resources` và bật `<filtering>true</filtering>` trên mọi resource. Plugin có khả năng **tự sinh file** trực tiếp đến output classpath. Trộn cách sinh tự động và resource filtering có thể làm file bị ghi đè, nội dung SHA không nhất quán, hoặc vô tình thay placeholder trong các file không cần filter.

Nếu dự án đã có một `src/main/resources/git.properties` thủ công, nên loại bỏ hoặc xác định một **single source of truth**, tránh hai file cùng đường dẫn trong output archive.

## 10. Điều kiện CI: Git metadata có thực và đúng commit không?

Một release build đáng tin cậy nên xác nhận:

1. Checkout đúng commit được CI yêu cầu (không chỉ đúng branch name).
2. Repository metadata `.git` hoặc nguồn provenance tin cậy có thể truy cập ở giai đoạn sinh file.
3. `git status --porcelain` sạch nếu policy yêu cầu build từ committed source; untracked files phải được xem xét theo policy.
4. Maven thực sự chạy plugin `revision` trước khi đóng gói.
5. `git.properties` được tạo trong output classpath và đi vào đúng JAR/WAR.
6. Commit trong **archive cuối** khớp `git rev-parse HEAD` của build checkout.
7. Runtime service đọc ra commit đúng từ JAR; khi nhiều pods, kiểm tra từng instance hoặc release identity.
8. Pipeline publish **cùng artifact** vừa được verify, không rebuild/copy file khác sau bước kiểm tra.

Ví dụ CI script POSIX ở project root:

~~~bash
set -eu

commit=$(git rev-parse HEAD)
status=$(git status --porcelain)

if [ -n "$status" ]; then
  echo "Working tree is not clean" >&2
  exit 1
fi

mvn -B -ntp clean package

java VerifyGitProperties.java \
  target/commit-trace-demo-1.0.0.jar \
  "$commit"
~~~

Script này minh họa fail-fast trên hệ thống CI **đã có Git, Maven3.9+, Java17 và source files được checkout đầy đủ**. Tool `git status --porcelain` giúp phát hiện cả file untracked không bị ignore; nếu project sinh file không theo dõi từ trước khi check status, điều kiện này phải được áp đúng thời điểm.

**Không dùng `git branch --show-current` làm định danh release.** CI thường checkout detached HEAD nên branch name có thể trống. `git rev-parse HEAD` là giá trị cần đối chiếu để truy vết commit, kết hợp repo URL và source provenance ở CI. `git.branch` là metadata bổ sung có thể thiếu hoặc không ổn định giữa môi trường.

### 10.1. Shallow clone và detached HEAD

Nhiều CI systems chỉ checkout depth=1 để tăng tốc. Nếu Git object của `HEAD` có mặt, plugin vẫn có thể trích commit id; nhưng các tính năng phụ thuộc lịch sử/tag (`git describe`, closest tag, commit count, branch inference) có thể thiếu dữ liệu. Khi dùng chúng, phải quyết định checkout depth và tags phù hợp thay vì âm thầm nhận metadata không đầy đủ.

Trong detached HEAD, không suy rằng branch `HEAD` có nghĩa code chưa commit. Chính SHA mới là định danh ổn định. Hai bản build từ **cùng SHA** nhưng ở những refs/branches khác nhau có thể cho `git.branch` khác, nên metadata branch cũng có thể làm artifact **không giống từng byte** giữa builds. Nếu mục tiêu reproducibility nghiêm ngặt, cân nhắc chỉ nhúng những trường bất biến theo revision như full commit ID và commit time, và để branch/deploy environment trong external provenance.

### 10.2. Build từ source archive không có .git

Một Docker multi-stage build có thể `COPY src pom.xml` vào builder mà không copy `.git`. Plugin không thể tự trích Git revision nếu không có Git metadata. **Không nên copy toàn bộ `.git` vào final runtime image** để giải quyết điều này.

Các hướng hợp lý:

- Chạy Maven packaging ở CI workspace có Git metadata, sau đó chỉ copy **đúng JAR đã build** sang runtime image.
- Nếu phải build trong isolated context không có `.git`, đưa SHA từ hệ thống CI đáng tin và **sinh file properties theo quy trình đã được kiểm chứng**, nhưng tuyệt đối không coi tham số user-supplied chưa xác minh là bằng chứng commit.
- Chỉ cho phép build không có Git metadata trong profile phát triển có định nghĩa rõ; release pipeline nên fail khi mất provenance.

Không bật `failOnNoGitDirectory=false` cho mọi môi trường rồi kết luận “plugin chạy thành công” dù output không có SHA, vì mục tiêu của bài là **truy vết commit**.

### 10.3. Dirty working tree là bẫy provenance

`git.commit.id` mô tả commit HEAD, **không chứng minh** toàn bộ files dùng build khớp commit đó. Nếu source đang có uncommitted changes, JAR có thể chứa code khác HEAD dù `git.properties` vẫn ghi đúng SHA HEAD.

Với releases, kiểm soát `git status --porcelain` hoặc build từ checkout sạch theo policy; có thể bổ sung `git.dirty` như một trường CI-internal, nhưng không xem nó là thay thế hoàn toàn cho source integrity hoặc artifact hash. Cần giữ commit SHA, artifact checksum và CI build identifier để nối các loại bằng chứng.

## 11. Multi-module Maven: commit của repo và metadata của từng service

Trong một monorepo nhiều modules:

~~~text
platform/
  pom.xml
  .git/
  common/
    pom.xml
  service-a/
    pom.xml
  service-b/
    pom.xml
~~~

Nếu plugin chạy ở aggregator/parent module nhưng chỉ tạo `git.properties` trong `platform/target/classes`, file ấy **không tự xuất hiện** trong executable JAR của `service-a` hay `service-b`. Đường dẫn output dựa trên **project hiện hành**; phải xác định module nào cần metadata và execution nào đang chạy.

Cách kiểm tra:

~~~bash
mvn -pl service-a -am clean package
jar tf service-a/target/service-a-1.0.0.jar
~~~

Tên artifact chỉ là ví dụ nếu `service-a` dùng `artifactId=service-a`, `version=1.0.0` và Boot repackage. Cần tìm `BOOT-INF/classes/git.properties` trong **JAR service-a**, không chỉ trong `common/target` hay `platform/target`.

Một Git repository thường có một `HEAD` dùng chung cho toàn monorepo, nhưng nếu build nhiều submodules có nested Git repositories/submodules/worktrees thì source revision của mỗi module có thể khác. Tránh tự suy từ tên branch và không ép plugin chạy trên POM-only modules nếu chúng không tạo runtime artifact. Hãy kiểm tra cấu hình `skipPoms` hoặc per-module execution theo phiên bản plugin, và quyết định thiết kế nhất quán.

**Không** ép mỗi module publish cùng một `git.properties` vào một thư viện chung rồi để các JARs lồng ghi đè nhau. Mỗi executable application nên có một nguồn metadata rõ ràng ở classpath root của **chính application module**, dùng chung một Git revision chỉ khi source scope thực sự như vậy.

## 12. Bảo mật và dữ liệu không nên nhúng

Git metadata giúp chẩn đoán, nhưng nếu không lọc nội dung, một plugin có thể sinh:

- `git.commit.user.email` hoặc tên tác giả.
- `git.remote.origin.url`, có thể hé lộ host/private repository path.
- `git.commit.message.full`, có thể chứa issue nội bộ hoặc dữ liệu nhạy cảm.
- `git.build.user.name`, hostname, đường dẫn build hoặc thông tin CI worker.
- Tags, branch names nội bộ, thư mục phát hành, dirty-state hay các chi tiết nghiệp vụ khác.

**Hai bề mặt rò rỉ khác nhau:**

1. **Artifact JAR**: bất kỳ ai được phát file có thể mở `BOOT-INF/classes/git.properties`, bất kể Actuator có tắt hay không.
2. **HTTP endpoints**: nếu `/actuator/info` hoặc endpoint custom được public, các thuộc tính được phép expose có thể bị truy cập qua mạng.

Do đó kiểm soát từ **lúc tạo file** bằng `includeOnlyProperties`, rồi kiểm soát tiếp **lúc expose endpoint** qua Actuator/Spring Security/network policy. Đừng dùng `management.info.git.mode=full` nếu metadata file chứa thông tin mà client không nên xem. Cũng đừng cho endpoint custom trả toàn bộ `Properties` chỉ để tiện debug.

**Commit SHA thường không phải bí mật** theo nghĩa mật khẩu, nhưng có thể giúp fingerprint version, liên kết với repository không public hoặc lộ tiến độ deploy. Chính sách expose vẫn phụ thuộc ứng dụng/môi trường. Có thể chỉ hiển thị commit id ở endpoint nội bộ hoặc log có kiểm soát.

Nếu lỡ nhúng metadata nhạy cảm vào artifact phát hành, chỉ tắt HTTP endpoint **không** loại dữ liệu khỏi JAR đã phát hành. Cần chỉnh allowlist, rebuild và quản lý artifact đã bị chia sẻ theo quy trình bảo mật.

## 13. git.properties và reproducible build

Sinh Git metadata ảnh hưởng bytes của JAR. Nếu properties chứa **thời gian build hiện tại**, tên máy hoặc branch name không ổn định, hai lần build cùng commit có thể tạo ra khác bytes. Điều này quan trọng với yêu cầu **byte-for-byte reproducible JAR**.

Phân biệt:

| Loại metadata | Ổn định theo commit? | Khuyến nghị khi cần reproducibility |
| --- | --- | --- |
| Full commit ID | Có, nếu cùng Git object ID | Giữ lại |
| Commit time | Có trong object metadata của commit | Giữ lại nếu format/timezone được cố định |
| Commit author | Có trong commit, nhưng có thể chứa PII | Chỉ giữ nếu policy cho phép |
| Current branch | Không chắc: detached HEAD, nhiều branch có thể chứa cùng SHA | Không coi là bất biến theo commit |
| `git.build.time` | Không, nếu lấy wall-clock | Bỏ hoặc thay bằng value xác định |
| Build host/user | Không ổn định giữa machines | Bỏ khỏi artifact |
| `git.dirty` | Thay đổi theo working tree | Enforce clean build, cân nhắc không nhúng field |

Maven có `project.build.outputTimestamp` để giảm bất định trong timestamps của archive entries; **nó không tự biến `git.build.time` thành commit time** và không khống chế mọi plugin metadata. Muốn hai JAR giống bytes, còn phải khóa JDK, dependencies, Maven plugins, ZIP ordering, encoding, resources và generated inputs.

Có thể thêm timestamp archive xác định:

~~~xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Fragment minh họa này cần được **ghép vào `<properties>` hiện có** và dùng mốc ổn định theo release policy, không chép một ngày cố định vĩnh viễn cho mọi bản. Nếu dùng Source Date Epoch / commit timestamp, phải xác nhận build plugins thực sự hỗ trợ cơ chế đó.

Một pipeline kiểm chứng mạnh giữ hai định danh:

~~~text
Source revision: git.commit.id từ JAR
Artifact bytes : SHA-256 của JAR đã test/publish
~~~

Chúng bổ sung nhau. **Cùng SHA source chưa bảo đảm cùng JAR bytes**, và **cùng JAR checksum** không chứng minh ứng dụng an toàn hay không có dependencies bị lỗi. Plugin Git không thay thế ký số, provenance attestations hoặc SBOM.

## 14. Gradle tương đương: không dùng Maven plugin trong Gradle

Với Spring Boot build bằng Gradle, không áp `git-commit-id-maven-plugin` vào `build.gradle`. Theo tài liệu Spring Boot, một lựa chọn tương đương là `com.gorylenko.gradle-git-properties`, ví dụ Groovy DSL fragment:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'com.gorylenko.gradle-git-properties' version '2.4.1'
}
~~~

Đây là **đoạn minh họa plugin block**, không phải toàn bộ Gradle project. Một project web còn cần dependencies, repositories và version Gradle/Java được Spring Boot plugin hỗ trợ. Có thể cấu hình các properties cần xuất theo tài liệu plugin Gradle tương ứng; không giả định nó dùng **cùng tên XML params** với Maven.

Sau Gradle build, kiểm tra resource `git.properties` trong classpath output và đặc biệt **trong `BOOT-INF/classes/git.properties` của `bootJar`**. `GitProperties`/Actuator `info` phía Spring Boot vẫn dựa vào tên file và vị trí classpath; chúng không yêu cầu Maven khi runtime.

Tương tự, `springBoot { buildInfo() }` trong Gradle tạo `build-info.properties`, **khác** file Git. Nếu cần cả hai, cấu hình và kiểm tra hai resources độc lập. Không dùng một bản `build-info` thay cho Git revision.

## 15. Các ca lỗi phổ biến và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Maven báo không tìm thấy Git directory | Build từ source archive/Docker context không có `.git`; path Git khác | Dùng checkout có Git metadata hoặc nguồn SHA đáng tin đã xác minh |
| Plugin không chạy ở package | Chỉ khai báo trong `pluginManagement`, execution/parent không được kích hoạt | Xem `mvn help:effective-pom`, `mvn -X` khi cần, plugin execution logs |
| `target/classes/git.properties` không tồn tại | `generateGitPropertiesFile` chưa bật, output path sai hoặc lifecycle goal không chạy | Kiểm tra POM và plugin logs, exact filename |
| JAR không có `BOOT-INF/classes/git.properties` | File sinh ngoài output classpath, bị packaging excludes, chọn sai JAR | `jar tf` đúng executable archive |
| Spring Boot báo thiếu bean `GitProperties` | Không có file ở **classpath root**, plugin không sinh hoặc app chạy nhầm artifact | Kiểm tra entry trong JAR, startup logs và auto-configuration |
| `/actuator/info` trả 404 | Endpoint chưa expose, path khác hoặc không có Actuator starter | `management.endpoints.web.exposure.include`, dependency, base path |
| `/actuator/info` trả 401/403 | Spring Security/endpoint access policy chặn | Kiểm tra authorization, không vội sửa Git plugin |
| `/actuator/info` trả `{}` | InfoContributor chưa được bật/không có metadata phù hợp | Kiểm tra `git.properties`, `management.info.git.enabled`, output |
| `git.commit.id` null | Plugin tạo khóa `git.commit.id.full` với mode `full`, bị filter mất field hoặc file sai | Dùng `commitIdGenerationMode=flat` với `git.commit.id`, kiểm tra content |
| Commit trong JAR không khớp `HEAD` | Artifact từ build khác, plugin/file cũ, checkout chuyển commit sau package | So file path, `git rev-parse HEAD` tại build và archived SHA |
| Local có branch, CI thiếu branch | Detached HEAD hoặc shallow fetch | Coi commit id là định danh chính; đừng require branch trong CI |
| git metadata khác dù cùng commit | Build time, branch, dirty state, timezone/format thay đổi | Dùng allowlist stable fields, reproducibility policy |
| Full SHA bị rút gọn gây nhầm release | Đang dùng `git.commit.id.abbrev` khi đối chiếu | Dùng full `git.commit.id` cho CI |
| Multi-module chỉ parent có Git file | Plugin chạy sai module/output folder | Kiểm tra đúng service JAR, execution và output path |
| JAR có metadata nhạy cảm | Plugin sinh quá nhiều fields | Giảm `includeOnlyProperties`, rebuild và xem risk |
| Gọi `git rev-parse HEAD` ở container runtime thất bại | Runtime image không có `.git` hoặc Git binary | Dùng `git.properties` sinh từ build, không chạy Git ở runtime |

Khi điều tra, đi theo thứ tự: **Git source state → Maven plugin execution → target/classes/git.properties → executable JAR entry → runtime GitProperties/Actuator → deployed file identity**. Điều này giúp biết lỗi ở stage nào thay vì sửa cấu hình tùy tiện.

## 16. Quy trình nghiệm thu và câu hỏi tự kiểm tra

### 16.1. Checklist trước khi phát hành

- [ ] Build từ commit/repository được xác nhận; working tree sạch theo policy.
- [ ] Maven/Java/plugin versions tương thích và được quản lý có chủ đích.
- [ ] Git plugin được **thực thi**, không chỉ khai báo trong pluginManagement.
- [ ] Plugin tạo đúng `git.properties` ở gốc output classpath.
- [ ] Plugin chỉ xuất các field cần dùng; không đưa remote URL/email/secret vào artifact.
- [ ] `git.commit.id` chứa full SHA và khớp `git rev-parse HEAD` của checkout build.
- [ ] Archive cuối chứa `BOOT-INF/classes/git.properties` (hoặc `WEB-INF/classes` cho WAR).
- [ ] Java validator chạy trên **chính JAR sẽ phát hành** và trả `git.commit.id.matches=true`.
- [ ] Runtime có thể đọc `GitProperties`, endpoint `/version` hoạt động theo security policy.
- [ ] Actuator `info` chỉ được expose khi cần, với quyền truy cập phù hợp.
- [ ] CI detached HEAD/shallow clone được hiểu; không dùng branch làm định danh bất biến.
- [ ] Release record lưu commit SHA **và artifact SHA-256**, không đánh đồng hai loại.
- [ ] Publish đúng artifact đã kiểm chứng, không rebuild bằng workspace khác rồi âm thầm deploy.

### 16.2. Tự kiểm tra

**Câu 1.** Tại sao cần plugin nếu chỉ muốn xem SHA của HEAD khi build?

**Trả lời:** Có thể tự chạy Git, nhưng plugin tích hợp với Maven lifecycle, tạo file properties đúng output classpath, dễ được Spring Boot auto-configure. Vẫn phải kiểm tra artifact cuối.

**Câu 2.** Đặt `git.properties` vào `target/` có đủ để Spring Boot đọc không?

**Trả lời:** Chưa. File phải ở **gốc classpath** của app, ví dụ `target/classes/git.properties` và `BOOT-INF/classes/git.properties` bên trong executable JAR.

**Câu 3.** Tại sao plugin mode `full` có thể làm `git.commit.id` không tìm thấy?

**Trả lời:** `commitIdGenerationMode=full` có thể xuất khóa `git.commit.id.full`, khác tên khóa `git.commit.id` của mode `flat`. Cần nhất quán cấu hình, code và allowlist.

**Câu 4.** `git.commit.id` trong JAR trùng HEAD nhưng source có uncommitted changes. Có thể kết luận artifact đúng commit chưa?

**Trả lời:** Chưa. SHA chỉ chỉ về HEAD; nội dung build có thể gồm thay đổi ngoài commit. Release cần checkout sạch và chứng cứ artifact bytes.

**Câu 5.** Nếu CI build detached HEAD, `git.branch` trống hoặc khác local thì có phải commit sai?

**Trả lời:** Không. Detached HEAD không có branch checkout thông thường. So full `git.commit.id` với expected SHA; branch là metadata bổ trợ.

**Câu 6.** Có nên bật `management.info.git.mode=full` cho endpoint public?

**Trả lời:** Không nên theo mặc định. File có thể chứa remote URL, email, commit message và host. Giới hạn data ngay lúc sinh và kiểm soát endpoint exposure/security.

**Câu 7.** Hai JAR chứa cùng `git.commit.id` có chắc byte-identical không?

**Trả lời:** Không. ZIP timestamps, generated resources, dependency contents, build tools hoặc environment khác có thể làm file khác nhau. So checksum SHA-256 của **hai artifacts** nếu cần byte identity.

## 17. Tài liệu chính thức

- Spring Boot 3.5 — How-to Build: Generate Git Information: https://docs.spring.io/spring-boot/3.5/how-to/build.html
- Spring Boot 3.5 — Actuator Endpoints and Git Commit Information: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Boot 3.5.16 — GitProperties API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/info/GitProperties.html
- Git Commit Id Maven Plugin — Repository, setup, minimum requirements: https://github.com/git-commit-id/git-commit-id-maven-plugin
- Git Commit Id Maven Plugin — Configuration and Properties: https://github.com/git-commit-id/git-commit-id-maven-plugin/blob/master/docs/configuration-and-properties.md
- Git Commit Id Maven Plugin — Releases (bao gồm 10.0.1 và breaking changes): https://github.com/git-commit-id/git-commit-id-maven-plugin/releases
- Maven Central — Git Commit Id Maven Plugin 10.0.1: https://central.sonatype.com/artifact/io.github.git-commit-id/git-commit-id-maven-plugin/10.0.1
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Java 17 — ZipFile API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html
- Git — rev-parse manual: https://git-scm.com/docs/git-rev-parse
- Git — status manual: https://git-scm.com/docs/git-status

**Ghi nhớ:** Plugin phải sinh `git.properties` đúng **classpath root** lúc build, Spring Boot mới có thể dùng `GitProperties` tại runtime. Để truy vết commit đáng tin, hãy kiểm tra **full Git commit ID trong executable JAR với HEAD của build checkout**, chỉ xuất metadata cần thiết, lưu kèm artifact checksum và bảo vệ `/actuator/info` theo chính sách môi trường.