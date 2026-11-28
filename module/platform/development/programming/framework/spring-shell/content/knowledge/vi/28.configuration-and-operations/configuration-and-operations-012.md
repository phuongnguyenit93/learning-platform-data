# Theo dõi phiên bản ứng dụng và khả năng tái hiện một lần chạy

Khi một command Spring Shell tạo ra kết quả sai hoặc khác giữa hai lần thực thi, nhóm vận hành cần biết binary nào đã chạy, được build từ source nào, dùng cấu hình và dữ liệu nào, rồi tái hiện được lần chạy đó.

Muốn làm được điều này, cần theo dõi hai lớp thông tin:

- **Nguồn gốc ứng dụng:** phiên bản phát hành, commit Git, thời điểm build, phiên bản Java, dependency và mã băm của artifact.
- **Ngữ cảnh từng lần chạy:** command đã gọi, đầu vào, snapshot dữ liệu, cấu hình có hiệu lực, môi trường runtime, kết quả và mã thoát.

Spring Boot 3.3 cung cấp `BuildProperties`, `GitProperties` và Actuator `info` để công bố thông tin build. Spring Shell có thể dùng các bean này trong một command như `app version`. Ứng dụng cũng có thể ghi một run manifest để lưu ngữ cảnh của từng lần thực thi.

## 1. Phân biệt phiên bản, build và lần chạy

Các giá trị dưới đây trả lời những câu hỏi khác nhau:

| Giá trị | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Application version | Người dùng đang chạy bản phát hành nào? | `2.4.1` |
| Source revision | Binary được tạo từ commit nào? | `8d2c4f1a...` |
| Build identifier | Pipeline hoặc lần build nào tạo artifact? | `release-2026.11.26-1842` |
| Artifact digest | File binary cụ thể có nội dung nào? | SHA-256 |
| Dependency set | Các thư viện nào được đóng gói? | SBOM |
| Run ID | Đây là lần thực thi cụ thể nào? | UUID |
| Correlation ID | Những log/sự kiện nào thuộc cùng một thao tác? | `job-7c1...` |

Không dùng riêng version như `2.4.1` để xác định binary. Hai artifact có thể cùng version nhưng được build từ hai commit khác nhau, có dependency khác nhau hoặc được tạo bởi hai pipeline khác nhau.

Một bộ nhận diện có ích cho ứng dụng CLI thường gồm:

~~~text
Application version : 2.4.1
Git commit          : 8d2c4f1a7b...
Git branch          : release/2.4
Build ID            : release-2026.11.26-1842
Artifact SHA-256    : 2b7f...c91a
Java runtime        : 17.0.12
Run ID              : 4c8d...
~~~

Application version, Git commit và Artifact SHA-256 nhận diện bản phần mềm. Run ID nhận diện một lần chạy. Mỗi lần gọi command có thể tạo một Run ID mới dù binary không thay đổi.

## 2. Tạo build metadata bằng Spring Boot

Spring Boot Maven Plugin và Gradle Plugin có thể sinh file `META-INF/build-info.properties` chứa group, artifact, name và version. Khi file này có trên classpath, Spring Boot tự cấu hình bean `BuildProperties`.

`BuildProperties` cung cấp các phương thức:

- `getGroup()`: group ID.
- `getArtifact()`: artifact ID.
- `getName()`: tên project.
- `getVersion()`: phiên bản project.
- `getTime()`: thời điểm build, nếu metadata có trường này.

Build metadata hữu ích cho command `app version`, log khởi động, báo cáo lỗi và endpoint Actuator.

### 2.1. Maven: sinh build-info

Thêm execution `build-info` vào `spring-boot-maven-plugin`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>build-info</goal>
                    </goals>
                    <configuration>
                        <time>off</time>
                        <additionalProperties>
                            <java.version>${java.version}</java.version>
                        </additionalProperties>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

`build-info` tạo file dưới `target/classes/META-INF/build-info.properties` để đóng gói cùng ứng dụng. `time` có thể được đặt thành `off` hoặc loại khỏi `excludeInfoProperties` nếu không muốn đưa thời điểm build vào metadata.

Ở pipeline cần ghi nhận thời điểm build, có thể giữ trường `build.time`, nhưng cần dùng một timestamp ổn định nếu mục tiêu là tái tạo artifact giống hệt. Không dùng thời điểm hiện tại một cách tùy tiện trong file build metadata.

### 2.2. Gradle: sinh build-info

Với Spring Boot Gradle Plugin:

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

Hoặc dùng cấu hình tối giản:

~~~groovy
springBoot {
    buildInfo()
}
~~~

Theo mặc định, `buildInfo()` tạo `build.time` bằng thời điểm build. Giá trị này thay đổi sau mỗi lần build, khiến task không thể ở trạng thái up-to-date và làm output thay đổi. Nếu ưu tiên tính lặp lại của artifact, loại trường `time` như ví dụ đầu.

Có thể bổ sung các thuộc tính ổn định như build number do CI cấp, revision hoặc phiên bản Java. Chỉ thêm dữ liệu đã được chuẩn hóa và không chứa secret hay thông tin riêng tư của máy build.

## 3. Ghi nhận Git commit

Version cho biết bản phát hành, còn Git commit cho biết source revision. Hai bản build cùng version vẫn có thể đến từ hai commit khác nhau.

Spring Boot có thể tự cấu hình `GitProperties` nếu `git.properties` nằm ở root classpath. Bean này cung cấp:

- `getBranch()`: tên branch.
- `getCommitId()`: commit ID đầy đủ.
- `getShortCommitId()`: commit ID rút gọn.
- `getCommitTime()`: thời điểm commit.

### 3.1. Maven: tạo git.properties

Nếu dùng `spring-boot-starter-parent`, có thể khai báo Git Commit ID Plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>io.github.git-commit-id</groupId>
            <artifactId>git-commit-id-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Plugin tạo `git.properties` từ repository tại thời điểm build. Có thể cấu hình plugin để chỉ giữ các trường cần thiết. Nếu pipeline build từ source archive không có thư mục `.git`, cần cung cấp revision qua build metadata do CI truyền vào.

### 3.2. Gradle: tạo git.properties

Dùng plugin `gradle-git-properties`:

~~~groovy
plugins {
    id 'com.gorylenko.gradle-git-properties' version '2.4.1'
}
~~~

Plugin tạo `git.properties` trong output resources. Có thể giới hạn các thuộc tính được ghi để tránh đưa thông tin môi trường không cần thiết vào artifact.

### 3.3. Lưu ý về branch và working tree

Commit ID đầy đủ là thông tin nhận diện source đáng tin cậy hơn tên branch. Branch có thể đổi tên hoặc bị xóa; pipeline cũng có thể checkout ở trạng thái detached HEAD.

Nếu build từ working tree có thay đổi chưa commit, commit ID không mô tả đầy đủ source thực tế. Pipeline phát hành nên kiểm tra working tree sạch. Nếu cho phép build thử từ thay đổi chưa commit, hãy ghi trạng thái dirty và mã băm của patch hoặc source archive đã dùng.

Không ghi nội dung patch riêng tư vào log hoặc run manifest. Chỉ lưu mã nhận diện và vị trí artifact đã được kiểm soát quyền truy cập.

## 4. Hiển thị phiên bản bằng command Spring Shell

Spring Shell không yêu cầu ứng dụng phải có một command version cố định. Có thể tự định nghĩa `app version` để người vận hành kiểm tra binary đang chạy.

Ví dụ dùng `ObjectProvider` để command vẫn hoạt động khi metadata chưa được tạo:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.info.BuildProperties;
import org.springframework.boot.info.GitProperties;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class VersionCommands {

    private final ObjectProvider<BuildProperties> buildProperties;
    private final ObjectProvider<GitProperties> gitProperties;

    public VersionCommands(
            ObjectProvider<BuildProperties> buildProperties,
            ObjectProvider<GitProperties> gitProperties) {
        this.buildProperties = buildProperties;
        this.gitProperties = gitProperties;
    }

    @ShellMethod(key = "app version", value = "Hiển thị phiên bản ứng dụng.")
    public String version() {
        BuildProperties build = buildProperties.getIfAvailable();
        GitProperties git = gitProperties.getIfAvailable();

        String version = build != null
                ? build.getVersion()
                : "unknown";
        String artifact = build != null
                ? build.getArtifact()
                : "unknown";
        String commit = git != null
                ? git.getCommitId()
                : "unknown";
        String branch = git != null
                ? git.getBranch()
                : "unknown";

        return """
                Application : %s
                Artifact    : %s
                Git commit  : %s
                Git branch  : %s
                """.formatted(version, artifact, commit, branch);
    }
}
~~~

Sau khi cấu hình build-info và git.properties, người dùng có thể chạy:

~~~text
shell:>app version
Application : 2.4.1
Artifact    : inventory-shell
Git commit  : 8d2c4f1a7b...
Git branch  : release/2.4
~~~

Nếu metadata chưa tồn tại, command hiển thị `unknown`. Trong pipeline phát hành, nên kiểm tra metadata là bắt buộc để tránh tạo artifact không có thông tin nhận diện.

Có thể hiển thị thêm `build.getTime()` và `git.getCommitTime()` nếu tổ chức cần theo dõi thời điểm. Hai timestamp có ý nghĩa khác nhau: thời điểm tạo artifact và thời điểm commit source.

## 5. Dùng Actuator info khi ứng dụng có endpoint quản trị

Nếu ứng dụng có `spring-boot-starter-actuator`, endpoint `info` có thể công bố build và Git metadata:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Spring Boot tự tạo các contributor khi có dữ liệu tương ứng:

| Contributor | Nguồn dữ liệu |
|---|---|
| `build` | `META-INF/build-info.properties` |
| `git` | `git.properties` |
| `env` | Các thuộc tính `info.*` |
| `java` | Thông tin runtime Java |
| `os` | Thông tin hệ điều hành |

Có thể thêm thông tin do ứng dụng quản lý:

~~~yaml
info:
  app:
    name: inventory-shell
    owner: inventory-platform
    data-schema: "v5"
~~~

Khi cần, tạo `InfoContributor` riêng để bổ sung metadata. Không đưa password, token, URL có credential, biến môi trường nhạy cảm hoặc toàn bộ cấu hình runtime vào endpoint này.

`info` không được expose qua HTTP mặc định trong cấu hình thông thường; chỉ endpoint `health` được expose mặc định. Khi mở `info`, hãy giới hạn mạng truy cập và áp dụng xác thực/phân quyền phù hợp. Nếu không muốn công bố Git metadata, đặt `management.info.git.enabled=false`.

Với CLI không chạy HTTP server, command `app version` thường phù hợp hơn. Không cần thêm Actuator chỉ để in version nếu ứng dụng không dùng các tính năng quản trị khác.

## 6. Phân biệt reproducible build và reproducible run

Hai khái niệm thường bị nhầm:

| Khái niệm | Mục tiêu | Cách kiểm chứng |
|---|---|---|
| Reproducible build | Cùng source, dependency và môi trường build tạo ra artifact byte-for-byte giống nhau | So sánh SHA-256 của các artifact độc lập |
| Reproducible run | Cùng binary, input, cấu hình và trạng thái phụ thuộc tạo ra cùng kết quả logic | Chạy lại với run manifest và so sánh output |

Một artifact reproducible không bảo đảm command tạo cùng kết quả ở mọi lần chạy. Ví dụ, command dùng `LocalDate.now()`, số ngẫu nhiên, thứ tự collection không ổn định hoặc dữ liệu từ API bên ngoài có thể trả kết quả khác nhau.

Ngược lại, hai lần chạy có thể cho cùng kết quả logic dù artifact khác byte, chẳng hạn khi build metadata chứa thời điểm build khác nhau. Vì vậy cần kiểm tra cả nguồn gốc binary và ngữ cảnh thực thi.

## 7. Làm cho artifact build có thể tái tạo

Để tạo artifact giống hệt giữa các lần build, cần kiểm soát những đầu vào có thể thay đổi:

- Source revision và trạng thái working tree.
- Phiên bản JDK và compiler.
- Phiên bản Gradle/Maven Wrapper và build plugin.
- Phiên bản dependency, không dùng version range hoặc snapshot không được khóa.
- Thứ tự file trong archive và timestamp của entry.
- Build metadata có trường thời gian hoặc đường dẫn máy build.
- Locale, timezone, encoding và biến môi trường được dùng trong build.

### 7.1. Maven: output timestamp ổn định

Maven hỗ trợ `project.build.outputTimestamp` để các plugin đóng gói archive dùng timestamp ổn định:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Giá trị trên là ví dụ cố định. Trong pipeline thực tế, có thể cung cấp timestamp ổn định theo source revision hoặc release metadata. Không đặt nó thành thời điểm hiện tại ở mỗi lần build nếu muốn artifact byte-for-byte giống nhau.

Kiểm tra các plugin đóng gói có hỗ trợ reproducible output. Có thể dùng Maven Artifact Plugin để so sánh hai lần build:

~~~bash
./mvnw clean install
./mvnw clean verify artifact:compare
~~~

So sánh tại cùng máy giúp phát hiện timestamp hoặc thứ tự archive không ổn định. Để kiểm chứng mạnh hơn, build lại trên một môi trường độc lập với cùng source và build instructions.

### 7.2. Gradle: thứ tự archive và timestamp

Với Gradle, cấu hình archive task:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Gradle 9 đặt hai thuộc tính này theo hướng reproducible mặc định. Với phiên bản cũ hơn, cấu hình tường minh giúp tránh phụ thuộc vào default của từng bản Gradle.

Dùng Gradle Wrapper và Java toolchain để cố định phiên bản build tool và JDK. Bật dependency locking nếu dự án cần bảo đảm dependency resolution không thay đổi giữa các lần build.

### 7.3. Không để build metadata phá tính lặp lại

`build.time` là trường dễ làm artifact thay đổi. Gradle `buildInfo()` mặc định dùng thời điểm hiện tại và task sẽ luôn cần chạy lại. Loại `time` nếu không cần thông tin đó trong artifact:

~~~groovy
springBoot {
    buildInfo {
        excludes = ['time']
    }
}
~~~

Với Maven, dùng `time=off` hoặc loại `time` khỏi `excludeInfoProperties`. Nếu vẫn cần timestamp, dùng giá trị ổn định được chia sẻ giữa các lần build của cùng source revision.

Thông tin build có thể chứa `version`, `commit` và `build ID` ổn định. Không nhúng hostname, username, thư mục workspace hoặc timestamp tùy ý vào artifact nếu các giá trị này không phục vụ mục đích truy vết.

## 8. Tính checksum và lưu SBOM

Sau khi tạo artifact, tính SHA-256 để xác định chính xác file được phân phối:

~~~bash
sha256sum build/libs/inventory-shell.jar
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash .\build\libs\inventory-shell.jar -Algorithm SHA256
~~~

Lưu digest trong release manifest hoặc hệ thống artifact repository. Khi tải binary để tái hiện lỗi, tính lại digest và so sánh với giá trị đã phát hành.

SBOM mô tả thành phần và phiên bản dependency trong artifact. Spring Boot hỗ trợ tạo CycloneDX SBOM qua Maven hoặc Gradle plugin. Lưu SBOM cạnh artifact để nhóm vận hành xác định dependency đã có trong bản phát hành.

Artifact digest và SBOM bổ sung cho nhau:

- Digest nhận diện byte của file.
- SBOM mô tả thành phần phần mềm.
- Git commit nhận diện source revision.
- Build ID nhận diện pipeline tạo artifact.

Không thay digest bằng version string hoặc tên file. Tên file có thể được giữ nguyên trong khi nội dung thay đổi.

Digest thường được tính sau khi đóng gói và lưu trong release manifest, artifact repository hoặc metadata của container image. Không thể nhúng SHA-256 của toàn bộ JAR vào chính JAR rồi mong giá trị đó vẫn khớp, vì việc thêm digest sẽ làm thay đổi nội dung cần hash. Nếu command cần hiển thị digest, pipeline có thể truyền digest qua metadata triển khai bên ngoài artifact.

## 9. Tạo run manifest cho mỗi lần thực thi

Để tái hiện một lần chạy, cần lưu một bản ghi mô tả ngữ cảnh. Có thể gọi bản ghi này là `run-manifest.json` hoặc `run-manifest.yaml`.

Ví dụ:

~~~json
{
  "runId": "4c8d5b73-22a4-4d90-8a1d-0db0e1b9f610",
  "startedAt": "2026-11-26T15:00:00Z",
  "correlationId": "job-7c1...",
  "application": {
    "name": "inventory-shell",
    "version": "2.4.1",
    "gitCommit": "8d2c4f1a7b...",
    "artifactSha256": "2b7f...c91a"
  },
  "command": {
    "name": "report generate",
    "options": {
      "warehouse": "HN",
      "format": "csv"
    }
  },
  "inputs": [
    {
      "reference": "inventory-snapshot-2026-11-25",
      "sha256": "7a21...9f31"
    }
  ],
  "configuration": {
    "profile": "production",
    "fingerprint": "8f5c...1e2a"
  },
  "runtime": {
    "java": "17.0.12",
    "os": "Linux",
    "architecture": "amd64",
    "locale": "vi_VN",
    "timeZone": "Asia/Ho_Chi_Minh"
  },
  "determinism": {
    "clock": "2026-11-25T00:00:00Z",
    "randomSeed": 12345
  },
  "result": {
    "status": "SUCCESS",
    "exitCode": 0
  }
}
~~~

Các trường trong manifest cần được chọn theo loại command. Command chỉ đọc báo cáo có thể cần snapshot dữ liệu, format và locale. Command thay đổi dữ liệu có thể cần thêm schema version, transaction reference và trạng thái side effect.

### 9.1. Trường nên có trong run manifest

| Nhóm | Trường gợi ý | Lý do |
|---|---|---|
| Nhận diện | `runId`, `correlationId` | Tìm log và output của một lần chạy |
| Ứng dụng | version, commit, artifact digest | Biết chính xác binary |
| Command | tên command, option đã làm sạch | Biết thao tác được thực hiện |
| Input | reference, checksum, dataset version | Khôi phục đúng dữ liệu |
| Configuration | profile, config fingerprint, feature flags | Khôi phục hành vi ứng dụng |
| Runtime | Java, OS, architecture, locale, timezone | Phát hiện khác biệt môi trường |
| Determinism | clock, random seed | Kiểm soát nguồn không xác định |
| External systems | API version, database schema, snapshot ID | Xác định phụ thuộc bên ngoài |
| Result | status, exit code, output digest, duration | So sánh kết quả |

Không lưu toàn bộ environment variables hoặc raw command line. Chỉ ghi các trường đã allow-list và đã loại bỏ thông tin xác thực.

### 9.2. Sinh Run ID và Correlation ID

Tạo Run ID tại thời điểm bắt đầu command:

~~~java
UUID runId = UUID.randomUUID();
~~~

Run ID là định danh của lần chạy, không phải seed để làm kết quả tất định. Correlation ID có thể được truyền qua các service hoặc log khi một command gọi nhiều thành phần.

Log sự kiện theo cấu trúc:

~~~java
log.info(
        "command.started runId={} correlationId={} command={}",
        runId,
        correlationId,
        "report generate");
~~~

Khi kết thúc, ghi cùng ID cùng trạng thái, thời gian xử lý và mã thoát. Không tạo ID mới ở mỗi lớp nếu mục tiêu là liên kết toàn bộ một lần chạy.

## 10. Hash đầu vào và cấu hình

Đường dẫn file không đủ để xác định nội dung input. File có thể bị thay thế trong khi vẫn giữ nguyên tên. Với input file, nên ghi reference và checksum.

Ví dụ tính SHA-256:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public static String sha256(Path path) throws Exception {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");

    try (InputStream input = Files.newInputStream(path)) {
        byte[] buffer = new byte[8192];
        int read;
        while ((read = input.read(buffer)) != -1) {
            digest.update(buffer, 0, read);
        }
    }

    return HexFormat.of().formatHex(digest.digest());
}
~~~

Với cấu hình, chỉ fingerprint một tập thuộc tính đã được chọn và sắp xếp ổn định. Không hash toàn bộ Environment hoặc secret rồi đưa digest vào manifest; các giá trị có entropy thấp có thể bị dò ngược.

Ví dụ tập thuộc tính an toàn có thể gồm:

- Tên profile.
- Phiên bản schema.
- Mã feature flag không nhạy cảm.
- Định dạng báo cáo.
- Locale và timezone.
- Giới hạn xử lý đã công bố.

Nếu cần kiểm chứng cấu hình có chứa dữ liệu nhạy cảm, dùng một mã fingerprint được tạo bằng HMAC với khóa bảo vệ riêng. Không đưa khóa HMAC vào artifact, log hoặc run manifest.

## 11. Kiểm soát các nguồn không xác định khi chạy

Ngay cả khi binary và input giống nhau, kết quả có thể thay đổi do thời gian, ngẫu nhiên, thứ tự dữ liệu hoặc hệ thống ngoài.

| Nguồn thay đổi | Biện pháp kiểm soát |
|---|---|
| `LocalDate.now()` / `Instant.now()` | Inject `Clock` và ghi thời điểm tham chiếu |
| Số ngẫu nhiên | Dùng seed có thể ghi lại và truyền vào generator |
| Thứ tự collection | Sắp xếp theo khóa ổn định trước khi tính toán hoặc xuất |
| Locale mặc định | Đặt locale tường minh |
| Timezone mặc định | Đặt timezone tường minh |
| Charset mặc định | Dùng UTF-8 hoặc charset được khai báo |
| Dữ liệu database thay đổi | Dùng snapshot ID hoặc transaction-consistent export |
| API bên ngoài thay đổi | Ghi version/response reference hoặc dùng fixture khi replay |
| Feature flag thay đổi | Ghi giá trị flag có liên quan trong manifest |
| Working directory khác | Dùng đường dẫn cấu hình rõ ràng và chuẩn hóa input path |
| Rounding/format số | Quy định precision, scale và locale |

Không phải mọi command đều cần deterministic tuyệt đối. Với command đọc dữ liệu trực tiếp từ hệ thống đang hoạt động, mục tiêu có thể là tái dựng đúng input và trạng thái phụ thuộc thay vì bảo đảm output không thay đổi.

### 11.1. Inject Clock

Không gọi trực tiếp `LocalDate.now()` trong nghiệp vụ cần tái hiện. Inject `Clock`:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Service sử dụng clock:

~~~java
import java.time.Clock;
import java.time.LocalDate;

public class ReportService {

    private final Clock clock;

    public ReportService(Clock clock) {
        this.clock = clock;
    }

    public LocalDate reportDate() {
        return LocalDate.now(clock);
    }
}
~~~

Trong test hoặc replay, cung cấp clock cố định:

~~~java
Clock replayClock = Clock.fixed(
        Instant.parse("2026-11-25T00:00:00Z"),
        ZoneOffset.UTC);
~~~

Manifest ghi thời điểm logic được sử dụng. Trường `startedAt` vẫn ghi thời gian thực tế của lần chạy để điều tra; trường `clock` ghi thời gian nghiệp vụ được dùng trong phép tính.

### 11.2. Ghi seed cho phép tính ngẫu nhiên

Nếu thuật toán sử dụng random, nhận seed từ tham số hoặc cấu hình:

~~~java
import java.util.Random;

long seed = 12345L;
Random random = new Random(seed);
~~~

Ghi seed vào manifest nếu nó không chứa thông tin nhạy cảm. Dùng cùng thuật toán và cùng phiên bản runtime khi replay, vì cách triển khai random hoặc thư viện có thể thay đổi theo phiên bản.

Không dùng seed cố định cho mục đích bảo mật như tạo token, mật khẩu hoặc khóa. Seed cố định chỉ phù hợp với tính toán cần tái hiện.

## 12. Ghi run manifest trong ứng dụng

Có thể mô hình hóa manifest bằng Java record:

~~~java
import java.time.Instant;
import java.util.Map;

public record RunManifest(
        String runId,
        String correlationId,
        Instant startedAt,
        String applicationVersion,
        String gitCommit,
        String artifactSha256,
        String command,
        Map<String, String> safeOptions,
        String inputReference,
        String inputSha256,
        String configurationFingerprint,
        String javaVersion,
        String operatingSystem,
        String architecture,
        String locale,
        String timeZone,
        Instant logicalClock,
        Long randomSeed,
        String status,
        Integer exitCode,
        String outputSha256,
        Long durationMillis) {
}
~~~

Một service chịu trách nhiệm ghi manifest bằng Jackson:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class RunManifestWriter {

    private final ObjectMapper objectMapper;

    public RunManifestWriter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public void write(RunManifest manifest, Path target) throws IOException {
        Path absoluteTarget = target.toAbsolutePath();
        Files.createDirectories(absoluteTarget.getParent());
        objectMapper.writerWithDefaultPrettyPrinter()
                .writeValue(absoluteTarget.toFile(), manifest);
    }
}
~~~

Đường dẫn output cần được cấu hình và kiểm soát quyền truy cập. Tên file có thể dùng Run ID để tránh ghi đè manifest của lần chạy trước.

Trong command, tạo Run ID và truyền cùng một context qua các bước:

~~~java
import java.time.Clock;
import java.util.UUID;

@ShellMethod(key = "report generate")
public String generate(String input) {
    UUID runId = UUID.randomUUID();
    Instant startedAt = clock.instant();

    try {
        ReportResult result = reportService.generate(input);
        runRecorder.success(runId, startedAt, result);
        return "Đã tạo báo cáo. Run ID: " + runId;
    }
    catch (RuntimeException ex) {
        runRecorder.failure(runId, startedAt, ex);
        throw ex;
    }
}
~~~

Ví dụ chỉ minh họa luồng. Trong ứng dụng thực tế, `runRecorder` cần nhận application version, Git commit, input hash, config fingerprint và kết quả. Chỉ lưu option đã làm sạch; không đưa raw input hoặc secret vào manifest.

Nếu command thực hiện nhiều side effect, hãy ghi trạng thái `STARTED`, `SUCCESS`, `FAILED` hoặc `PARTIAL` và cập nhật manifest sau khi biết kết quả. Tránh ghi `SUCCESS` trước khi transaction hoặc tác vụ bên ngoài hoàn tất.

## 13. Tái hiện một lần chạy

Khi có Run ID và manifest, quy trình tái hiện có thể thực hiện theo thứ tự:

1. Lấy artifact đúng version và Git commit.
2. Tính SHA-256 của artifact và so sánh với digest trong manifest.
3. Khôi phục dependency/SBOM và runtime tương ứng.
4. Lấy lại input snapshot và kiểm tra checksum.
5. Khôi phục các thuộc tính cấu hình được allow-list và fingerprint.
6. Thiết lập locale, timezone, Clock và random seed đã ghi.
7. Chạy đúng command với các option đã làm sạch.
8. Thu thập output, exit code, log và manifest mới.
9. So sánh kết quả logic với lần chạy gốc.

Với command có side effect, không replay trực tiếp vào production. Dùng môi trường cô lập, database snapshot hoặc mock hệ thống ngoài để tránh xóa, gửi hoặc ghi dữ liệu lần thứ hai.

### 13.1. So sánh output

Không phải mọi byte output đều cần giống nhau. Terminal output có thể chứa timestamp, Run ID, ANSI color hoặc thời lượng xử lý. Nên tách:

- **Output nghiệp vụ:** dữ liệu báo cáo, kết quả tính toán, danh sách bản ghi.
- **Thông tin vận hành:** Run ID, thời gian chạy, host và duration.
- **Thông tin trình bày:** ANSI color, bảng, padding và line wrapping.

Khi kiểm tra tính tái hiện, so sánh output nghiệp vụ đã chuẩn hóa. Nếu output là JSON, có thể chuẩn hóa thứ tự key và bỏ các trường vận hành thay đổi trước khi tính checksum.

Không loại bỏ các trường có ý nghĩa nghiệp vụ chỉ để làm hai output giống nhau. Quy tắc chuẩn hóa phải được ghi rõ trong test.

## 14. Dùng run metadata trong log và báo cáo lỗi

Mọi log quan trọng trong một lần chạy nên mang cùng Run ID hoặc Correlation ID:

~~~java
log.info(
        "report.completed runId={} rows={} outputRef={}",
        runId,
        result.rowCount(),
        result.outputReference());
~~~

Khi xử lý lỗi:

~~~java
log.error(
        "report.failed runId={} errorType={}",
        runId,
        ex.getClass().getSimpleName());
~~~

Người dùng có thể gửi Run ID cho nhóm vận hành. Nhóm vận hành dùng ID để tìm manifest, log và artifact liên quan. Thông báo CLI không cần hiển thị stack trace hoặc thông tin nội bộ.

Không dùng Run ID thay cho xác thực hoặc quyền truy cập. Đây là định danh truy vết, không phải bí mật hay credential.

## 15. Kiểm tra reproducible build

Có thể kiểm chứng build reproducibility theo các bước:

| Bước | Việc thực hiện | Kết quả cần có |
|---|---|---|
| 1 | Checkout cùng commit ở hai workspace độc lập | Source revision giống nhau |
| 2 | Dùng cùng JDK, Wrapper, plugin và dependency lock | Toolchain giống nhau |
| 3 | Dùng cùng build arguments và output timestamp | Build input giống nhau |
| 4 | Build artifact ở cả hai workspace | Có hai artifact độc lập |
| 5 | Tính SHA-256 | Digest phải giống nhau |
| 6 | Nếu khác, dùng diffoscope hoặc kiểm tra archive entries | Xác định file/metadata thay đổi |

Một lần build lại trên cùng máy là bước kiểm tra ban đầu. Kiểm chứng mạnh hơn cần workspace hoặc container độc lập để phát hiện phụ thuộc vào username, thư mục hiện tại, timezone, file permissions hoặc biến môi trường.

## 16. Kiểm thử khả năng tái hiện một lần chạy

Nên có test cho cả metadata và hành vi:

| Test | Điều cần xác nhận |
|---|---|
| Version command | Hiển thị version, artifact và commit đúng |
| Thiếu build metadata | Hiển thị trạng thái chưa có metadata rõ ràng |
| Git metadata | Commit ID được đọc đúng từ `git.properties` |
| Run ID | Mỗi lần chạy có ID riêng và nhất quán trong log |
| Run manifest | Có đủ input reference, config fingerprint và runtime |
| Secret redaction | Password/token không xuất hiện trong manifest hoặc log |
| Input checksum | Cùng file tạo cùng SHA-256 |
| Clock replay | Cùng Clock và input tạo cùng ngày nghiệp vụ |
| Random seed | Cùng seed tạo cùng chuỗi kết quả với cùng thuật toán |
| Deterministic ordering | Cùng dữ liệu tạo cùng thứ tự output |
| Replay integration | Chạy lại với manifest cho kết quả nghiệp vụ tương đương |
| Artifact reproducibility | Hai build độc lập tạo cùng digest khi cấu hình yêu cầu |

Test replay cần dùng fixture hoặc snapshot cố định. Nếu test kết nối tới database hoặc API đang thay đổi, kết quả không thể được xem là bằng chứng về tính tất định.

## 17. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ ghi application version | Không phân biệt được hai binary cùng version | Ghi commit ID và artifact digest |
| Không sinh `build-info.properties` | `BuildProperties` không có dữ liệu | Bật Maven `build-info` hoặc Gradle `buildInfo()` |
| Không tạo `git.properties` | Không truy ra source revision | Cấu hình Git Commit ID Plugin hoặc gradle-git-properties |
| Build từ working tree dirty | Commit ID không mô tả hết source | Yêu cầu clean tree hoặc ghi trạng thái dirty và patch digest |
| Giữ `build.time` thay đổi liên tục | Artifact/task output không lặp lại | Loại `time` hoặc dùng timestamp ổn định |
| Chỉ so sánh tên file JAR | File cùng tên nhưng nội dung khác | So sánh SHA-256 |
| Không lưu input snapshot | Không thể khôi phục đúng dữ liệu | Lưu reference và checksum của input |
| Ghi toàn bộ command line | Có thể lộ password/token | Allow-list option và redaction |
| Hash toàn bộ config có secret | Digest có thể hỗ trợ dò giá trị nhạy cảm | Fingerprint tập cấu hình an toàn hoặc dùng HMAC |
| Dùng giờ hệ thống trực tiếp trong nghiệp vụ | Kết quả replay khác ngày hoặc timezone | Inject Clock và ghi thời điểm logic |
| Dùng random không ghi seed | Không tái tạo được kết quả | Truyền và lưu seed cho phép tính cần replay |
| Replay command có side effect trên production | Tạo dữ liệu trùng hoặc lặp thao tác | Dùng snapshot/môi trường cô lập |
| Chỉ ghi Run ID trong log đầu | Khó liên kết log ở service khác | Truyền correlation context xuyên suốt |
| Expose toàn bộ Actuator info | Lộ thông tin build và nội bộ | Giới hạn endpoint, xác thực và lọc trường |

## 18. Quy trình vận hành đề xuất

1. Cấp application version rõ ràng cho mỗi bản phát hành.
2. Gắn build-info và Git metadata vào artifact.
3. Kiểm tra source tree sạch trước khi phát hành.
4. Khóa JDK, build tool, plugin và dependency.
5. Cấu hình archive reproducibility và timestamp ổn định.
6. Tạo checksum SHA-256 và SBOM sau khi build.
7. Cung cấp command `app version` để người dùng kiểm tra binary.
8. Tạo Run ID cho mỗi lần chạy command quan trọng.
9. Ghi run manifest gồm artifact, commit, input, config fingerprint và runtime.
10. Ghi log với Run ID/Correlation ID và loại bỏ dữ liệu nhạy cảm.
11. Dùng Clock, seed và snapshot khi cần replay kết quả.
12. Kiểm thử hai build độc lập và chạy lại một số manifest đại diện.

## 19. Tổng kết

Theo dõi phiên bản ứng dụng cần nhiều hơn một chuỗi version. Spring Boot 3.3 có thể sinh `BuildProperties` từ `META-INF/build-info.properties` và `GitProperties` từ `git.properties`. Dùng chúng để hiển thị version và commit bằng command `app version`, hoặc công bố qua Actuator `info` khi endpoint được bảo vệ phù hợp.

Khả năng tái hiện một lần chạy cần nhận diện binary bằng commit và SHA-256, lưu input reference/checksum, cấu hình đã làm sạch, runtime, thời điểm nghiệp vụ, random seed và kết quả. Phân biệt reproducible build với reproducible run: một bên kiểm tra artifact byte-for-byte, bên kia kiểm tra hành vi khi chạy lại cùng ngữ cảnh.

Khi có build metadata, SBOM, checksum và run manifest, nhóm vận hành có thể xác định binary, khôi phục đầu vào và cấu hình, chạy lại trong môi trường an toàn, rồi so sánh kết quả để tìm nguyên nhân khác biệt.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Generate Build Information and Git Information](https://docs.spring.io/spring-boot/3.3/how-to/build.html) — tạo BuildProperties, GitProperties, build-info và git.properties bằng Maven/Gradle.
- [Spring Boot 3.3 — BuildProperties API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/info/BuildProperties.html) — group, artifact, version và build time.
- [Spring Boot 3.3 — GitProperties API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/info/GitProperties.html) — branch, commit ID và commit time.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/docs/3.3.0-M1/reference/html/actuator.html) — Git và build information trong info endpoint.
- [Spring Boot 3.3 — Gradle Plugin: Integrating with Actuator](https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html) — build-info properties và loại bỏ build.time để tăng repeatability.
- [Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html) — project.build.outputTimestamp, artifact comparison và build độc lập.
- [Gradle — Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html#sec:reproducible_archives) — timestamp cố định và thứ tự file ổn định trong archive.
- [Spring Boot — Generate a CycloneDX SBOM](https://docs.spring.io/spring-boot/how-to/build.html) — tạo SBOM bằng Maven hoặc Gradle.
- [Reproducible Builds](https://reproducible-builds.org/) — nguyên tắc và phương pháp kiểm chứng artifact có thể tái tạo.
