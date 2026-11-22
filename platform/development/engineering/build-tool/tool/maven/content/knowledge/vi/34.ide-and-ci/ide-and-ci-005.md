# Dùng Maven Wrapper, chế độ batch và cấu hình không phụ thuộc máy

## 1. Mục tiêu: một lệnh build nhất quán từ IDE đến CI

Dự án Java có thể build thành công trên máy người viết nhưng thất bại trên máy đồng nghiệp hoặc CI dù mã nguồn giống nhau. Những nguyên nhân thường gặp: phiên bản Maven khác, JDK chạy Maven khác JDK dự kiến, plugin chưa được ghim phiên bản, local repository có JAR được cài thủ công, proxy/`settings.xml` của người dùng khác nhau, đường dẫn tuyệt đối trong POM, encoding/timezone tùy hệ điều hành hoặc pipeline đang chờ prompt.

Một build **portable** nhằm tạo được **hợp đồng thực thi rõ ràng**: từ một commit cụ thể, người dùng biết cần JDK nào, dùng Maven version nào, lấy dependencies từ đâu, chạy lệnh nào, kiểm tra thành công ra sao. Ba công cụ chính của chủ đề:

1. **Maven Wrapper:** các launcher `mvnw`/`mvnw.cmd` trong repository, tải/chạy **phiên bản Maven được chọn** thay vì phụ thuộc vào Maven trên `PATH`.
2. **Batch mode và log ổn định:** `-B`/`--batch-mode` giúp chạy không tương tác, `-ntp`/`--no-transfer-progress` giảm log download progress trong CI, cộng exit-code checking.
3. **Cấu hình gắn với project nhưng không gắn với một máy:** `pom.xml`, `.mvn/maven.config`, `.mvn/jvm.config`, version pinning, Enforcer; settings/credentials/JDK installation cụ thể được cung cấp từ môi trường theo một giao diện đã mô tả.

**Phân biệt quan trọng:** Wrapper ghim **Maven runtime**, không tự cài Java JDK, không tự bảo vệ supply chain, không tự làm mọi JAR reproducible và không tự biến mọi IDE thành dùng Wrapper. Mỗi lớp phải được cấu hình rõ.

### 1.1. Sơ đồ các đầu vào

```text
Code repository (nên commit)
  pom.xml                       build, plugins, Java target
  mvnw, mvnw.cmd                Wrapper launchers
  .mvn/wrapper/maven-wrapper.properties
                                Maven version/distribution URL
  .mvn/maven.config             CLI arguments dùng chung
  .mvn/jvm.config               JVM startup options dùng chung
  src/main, src/test            Java code / tests

Machine or CI environment
  JDK / JAVA_HOME               công cụ Java thật
  network/proxy/CA              tải Maven và artifacts
  settings.xml                  approved mirrors, credentials
  toolchains.xml                local JDK installation paths
  local .m2 repository          cache và installed artifacts
  secrets / timeout             theo hạ tầng, không commit
```

Đừng copy một thư mục `~/.m2` của developer làm “cấu hình build”. Local Maven repository có thể chứa cache và artifacts cài thủ công; nó không thay source repository/provenance.

| Yêu cầu | Giải pháp chính | Giới hạn |
| --- | --- | --- |
| Maven version nhất quán | Checked-in Wrapper | Cần bootstrap Maven distribution |
| Java target rõ ràng | `maven.compiler.release=17` | Không tự provision JDK |
| Kiểm phiên bản build tools | Maven Enforcer | Chỉ fail nếu sai, không cài tools |
| CI không tương tác | `-B`, CI timeout | Plugin tùy biến vẫn có thể hỏi stdin |
| Không spam progress bar | `-ntp` | Không chuyển Maven sang offline |
| Cấu hình CLI chung | `.mvn/maven.config` | Không đặt secret hoặc bypass-test flags |
| JVM startup config | `.mvn/jvm.config`, `MAVEN_OPTS` | Heap/OS resources có thể khác nhau |
| Credential/mirror | CI-provisioned `settings.xml` | Không được commit mật khẩu |
| Reproducible archives | Plugin versions, `outputTimestamp` | Còn JDK, newline, resources, môi trường |

## 2. Maven Wrapper: cài đặt và dùng đúng

### 2.1. Wrapper hoạt động thế nào?

Maven Wrapper được khởi tạo một lần bởi Wrapper Plugin. Sau đó repository chứa những tệp cơ bản:

```text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
```

Khi gọi `./mvnw` hoặc `mvnw.cmd`, scripts xác định Maven distribution được ghi ở `distributionUrl`. Nếu chưa có trong cache Wrapper, nó được tải và unpack theo type/bootstrap; những lần sau thường dùng lại bản đã tải. Maven process mới chạy các goals và resolve build plugins/dependencies.

**Không có Maven cài toàn cục vẫn chạy được một Wrapper đã commit**, nhưng vẫn cần JDK và quyền download hoặc cache Maven distribution. Khi *tạo* Wrapper lần đầu, cách thuận tiện là dùng Maven cài sẵn để chạy `wrapper:wrapper`.

### 2.2. Tạo Wrapper phiên bản cụ thể

Ví dụ khởi tạo một project mới bằng **Maven Wrapper Plugin 3.3.4**, ghim **Apache Maven 3.9.11**:

```bash
mvn -version
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.11 -Dtype=only-script
```

- `-N`/`--non-recursive` chỉ chạy goal trên root (hữu ích khi reactor có modules).
- Dùng tọa độ plugin đầy đủ, tránh phụ thuộc plugin-prefix resolution.
- `-Dmaven=3.9.11` chỉ phiên bản Maven distribution mong muốn.
- `-Dtype=only-script` chỉ strategy bootstrap; là mặc định của cài đặt Wrapper mới theo tài liệu hiện đại.
- Đây là **mốc phiên bản đã được Apache phát hành**, không phải khẳng định đây là bản mới nhất mọi thời điểm.

Khi repo đã có Wrapper, **không khởi tạo lại vô cớ**: kiểm tra file/version hiện tại và chỉ update bằng pull request đã được review. Wrapper Plugin có thể giữ type cũ khi cập nhật nếu người dùng không chỉ định `-Dtype`.

### 2.3. Distribution URL

Trong `.mvn/wrapper/maven-wrapper.properties`, dòng chính có thể là:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.11/apache-maven-3.9.11-bin.zip
```

Đây là một **dòng trích minh họa**, không khẳng định toàn bộ file do plugin sinh chỉ có một dòng. Giữ các fields hợp lệ khác nếu đã được plugin sinh ra. Pin version trong URL để tránh việc một launcher tải Maven khác theo thời gian.

Với doanh nghiệp, có thể dùng Maven distribution ở **approved repository manager** và cấu hình Wrapper URL/`MVNW_REPOURL` theo hướng dẫn Apache. Không tự chuyển sang một mirror lạ để “chạy nhanh hơn”; Maven distribution là executable tool sẽ chạy trong CI.

### 2.4. Chạy trên từng hệ điều hành

Linux/macOS:

```bash
./mvnw --version
./mvnw -B -ntp clean verify
```

Windows PowerShell:

```powershell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp clean verify
```

Windows Command Prompt:

```bat
mvnw.cmd --version
mvnw.cmd -B -ntp clean verify
```

`--version` cần hiển thị Maven 3.9.11 theo properties được chọn. Dòng Java version, vendor, OS và Maven home phụ thuộc máy; đừng sao chép một log giả làm “stdout chính xác cho mọi nền tảng”.

Trên Unix, `mvnw` phải có executable bit trong Git. Nếu báo `Permission denied`, kiểm tra file mode và cách checkout; không sửa quyền cả repository bằng lệnh đệ quy thiếu kiểm soát.

### 2.5. Wrapper type: four bootstrap strategies

| Type | Tệp đi kèm | Cách bootstrap | Ưu/nhược |
| --- | --- | --- | --- |
| `only-script` | `mvnw`, `mvnw.cmd`, properties | curl/wget trên Unix hoặc PowerShell trên Windows tải Maven distribution trực tiếp | Gọn; không cần Wrapper JAR |
| `script` | Scripts + properties | Scripts tải `maven-wrapper.jar` rồi thực thi bootstrap | Cần thêm bước lấy JAR |
| `bin` | Scripts + properties + `maven-wrapper.jar` | Bootstrap JAR nằm trong source tree | Tránh tải Wrapper JAR, nhưng commit binary |
| `source` | Scripts + properties + `MavenWrapperDownloader.java` | Có thể compile downloader source để tải Wrapper JAR | Có mã downloader trong tree, nhiều bước bootstrap |

**Không đồng nhất `only-script` với offline mode**: lần đầu vẫn có thể phải tải Maven zip. **Không phải mọi Wrapper đều có `.mvn/wrapper/maven-wrapper.jar`**; vắng JAR là bình thường với `only-script`.

Lệnh lựa chọn kiểu khác (chọn **một**, không chạy nối tiếp để ghi đè cùng project):

```bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.11 -Dtype=script
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.11 -Dtype=bin
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.11 -Dtype=source
```

### 2.6. Pin SHA-256 và bảo vệ bootstrap

Wrapper hỗ trợ properties:
- `distributionSha256Sum`: SHA-256 kỳ vọng của Maven distribution.
- `wrapperSha256Sum`: SHA-256 kỳ vọng của Wrapper JAR khi type sử dụng JAR.

**Chỉ ghi checksum thật đã xác minh từ nguồn tin cậy**; không đưa chuỗi hash giả để “minh họa” trong file có thể copy-run. Khi dùng `only-script`, điều quan trọng là Maven distribution; type này không dùng Wrapper JAR.

Quy trình bảo vệ:
1. Chọn version Maven và bootstrap type được duyệt.
2. Kiểm tra HTTPS source, checksum/signature qua kênh đáng tin.
3. Commit các launcher/properties do plugin sinh.
4. Review mọi thay đổi `mvnw`/`mvnw.cmd`/`.mvn/wrapper/*` như code có thể chạy.
5. Thử build trên môi trường sạch/cached distribution đã kiểm chứng.
6. Không bỏ hash/TLS verification khi proxy/download lỗi; sửa certificate, network, repository manager.

**Wrapper script chạy trước Maven**; một PR không tin cậy sửa `mvnw` có thể chạy lệnh nguy hiểm trước khi Enforcer/plugin security checks được thực thi. Đừng cấp release secrets cho các PR jobs chưa được tin cậy.

## 3. Batch mode và log CI

### 3.1. `-B`/`--batch-mode`

Chế độ batch hướng Maven đến **non-interactive execution**; dùng trong CI hoặc automation:

```bash
./mvnw -B clean verify
```

Mục đích: không chờ Maven/plugin hỏi tương tác trong các workflow có hỗ trợ batch. Tuy nhiên:
- `-B` **không đặt CI job timeout**.
- Không tự cấp username/password, GPG passphrase hoặc SCM credentials.
- Một custom plugin tự đọc stdin có thể vẫn không tuân thủ.
- Không tự chạy tests nếu bạn gọi goal khác bỏ qua lifecycle.
- Không có nghĩa output lúc nào cũng ít log.

Một pipeline đúng chuẩn cung cấp config/credentials trước và **fail rõ** nếu còn cần thông tin không có.

### 3.2. `-ntp`/`--no-transfer-progress`

`-ntp` tắt thanh tiến độ khi Maven transfer artifacts, giúp CI logs không bị tràn:

```bash
./mvnw -B -ntp clean verify
```

`-ntp` **không** tắt download, không chuyển Maven sang offline, không chứng minh dependency source đáng tin. Dùng `-o` nếu cần offline và đã pre-cache Wrapper distribution, Maven plugins, project dependencies.

### 3.3. Các tùy chọn CLI cần hiểu đúng

| Option | Tác dụng | Lưu ý |
| --- | --- | --- |
| `-B` | Batch/non-interactive | Khuyến nghị CI |
| `-ntp` | Ẩn transfer progress | Giữ log gọn |
| `-V` | In version rồi tiếp tục build | Hữu ích provenance |
| `-e` | Stack trace khi lỗi | Dùng điều tra |
| `-X` | Debug logging | Có thể lộ config nhạy cảm, tránh mặc định |
| `-q` | Quiet log | Có thể làm khó phân tích |
| `-o` | Offline | Không download Maven distribution hộ Wrapper |
| `-U` | Refresh missing releases/updated snapshots theo Maven resolver | Không tự fix repository policy |
| `-T 4` | Parallel reactor | Chỉ khi plugin/tests thread-safe |
| `-fae` | Fail at end | Chạy modules độc lập còn lại, cuối vẫn báo fail |
| `-fn` | Fail never | **Không dùng** cho required quality gate |
| `-DskipTests` | Bỏ chạy tests ở Surefire | **Không dùng** cho release gate |
| `-Dmaven.test.skip=true` | Có thể bỏ cả test compilation và execution | Không dùng khi yêu cầu kiểm thử |

**`-fae` và `-fn` không giống nhau.** `-fae` hữu ích lấy thêm test results từ modules độc lập, còn `-fn` có thể khiến CI xanh giả.

### 3.4. Exit code phải về CI

Shell POSIX:

```bash
./mvnw -B -ntp clean verify
status=$?
echo "maven_exit=$status"
exit "$status"
```

PowerShell:

```powershell
.\mvnw.cmd -B -ntp clean verify
$code = $LASTEXITCODE
Write-Output "maven_exit=$code"
exit $code
```

**Chú ý:** trong hai code blocks thật, các dấu `$` ở ví dụ Bash được chuyển thành ký tự `$` khi lưu bài, còn PowerShell `$code` có literal trong chuỗi Markdown. Dùng exit status, không chỉ tìm chữ `BUILD SUCCESS`; `|| true` hoặc `continue-on-error: true` có thể che lỗi. Với script `set -e`, dừng ngay khi Maven fail thay vì tiếp tục release.

## 4. `.mvn/maven.config`: CLI options của project

File `.mvn/maven.config` nằm ở project root, chứa Maven CLI arguments thường dùng. **Với Maven 3.9.0+, mỗi CLI argument phải nằm trên một dòng riêng**. Ví dụ hợp lệ:

```text
-ntp
-Dstyle.color=never
```

Nếu muốn batch trong mọi lần chạy:

```text
-B
-ntp
-Dstyle.color=never
```

Không viết một dòng:

```text
-B -ntp
```

với Maven 3.9.x; nó có thể bị đọc như một CLI argument thay vì hai options. Apache Maven Configuring Guide nêu mỗi argument một dòng từ 3.9.0; từ 3.9.3 dòng bắt đầu bằng `#` được hiểu là comment trong `maven.config`. Maven 3.8.x trở xuống không hỗ trợ comments tương ứng. Dự án đã pin Maven 3.9.11 nên tránh nhầm cú pháp từ tutorial dành cho phiên bản cũ.

**Nên để gì trong file này?**
- Flags không làm thay release semantics và phù hợp local lẫn CI, ví dụ `-ntp`.
- Có thể đặt `-B` nếu toàn đội đồng ý non-interactive mặc định.
- Không đặt `-DskipTests`, `-fn`, deploy goal, release credentials hoặc local absolute directory.
- Không ép profile riêng người dùng thành mặc định khi nhiều contributor/CI cần dùng chung.

Trong lab, chọn `-ntp` và `-Dstyle.color=never` cho output gọn, CI vẫn gọi `-B` tường minh.

### 4.1. `.mvn/jvm.config` khác gì?

`.mvn/jvm.config` chứa **JVM startup options** của process Maven, ví dụ:

```text
-Dfile.encoding=UTF-8
```

Với máy đủ bộ nhớ, có thể thêm `-Xmx1024m` nếu workload đòi hỏi, nhưng đây là lựa chọn **tùy resource limits**, không phải default bắt buộc cho mọi laptop/CI container.

| Cấu hình | Nơi đúng |
| --- | --- |
| Batch, transfer progress | CLI/`maven.config` |
| JVM heap, JVM system property | `jvm.config`/`MAVEN_OPTS` |
| Java source target | `pom.xml` Compiler Plugin |
| Maven runtime version | Wrapper properties |
| Maven repository mirror | `settings.xml` |
| Machine JDK path | `JAVA_HOME`/`toolchains.xml` |
| Secret token/password | CI secret store, không commit |

**Không dùng `.mvn/jvm.config` để đặt Maven goals**. Không dùng `.mvn/maven.config` để đặt `-Xmx` như một Maven CLI flag.

### 4.2. `MAVEN_OPTS` và `MAVEN_ARGS`

- `MAVEN_OPTS`: JVM options cho Maven, ví dụ heap/encoding.
- `MAVEN_ARGS`: từ **Maven 3.9.0**, arguments được thêm trước CLI arguments; có thể chứa `-B -ntp`.

Linux/macOS:

```bash
export MAVEN_OPTS="-Xmx1024m -Dfile.encoding=UTF-8"
export MAVEN_ARGS="-B -ntp"
./mvnw clean verify
```

PowerShell:

```powershell
$env:MAVEN_OPTS = "-Xmx1024m -Dfile.encoding=UTF-8"
$env:MAVEN_ARGS = "-B -ntp"
.\mvnw.cmd clean verify
```

Các biến này nằm ở **máy hoặc runner**. Nếu một build chỉ pass vì `MAVEN_ARGS` hoặc `MAVEN_OPTS` được đặt âm thầm trong profile cá nhân, nó chưa portable. Ghi rõ các yêu cầu thiết yếu trong repo/CI config và kiểm tra runtime thực tế. Apache Maven docs cũng nêu precedence của `MAVEN_OPTS` so với `jvm.config` khác giữa Maven 3 và Maven 4; tránh gán cùng option hai nơi.

## 5. Java JDK, Compiler, Enforcer và Toolchains

### 5.1. Wrapper không tải JDK

Chạy:

```bash
java -version
javac -version
./mvnw --version
```

hoặc PowerShell:

```powershell
java -version
javac -version
.\mvnw.cmd --version
```

Kiểm tra **Java version mà Maven process đang dùng**, không chỉ `java` trên shell. IDE có thể chọn Maven runner JDK khác terminal, CI action có thể trỏ đến JDK khác `JAVA_HOME`.

### 5.2. Compile Java 17 API đúng cách

POM:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Trên JDK hỗ trợ `--release 17`, compiler kiểm Java language level, bytecode target và standard Java APIs tương ứng. Nó không tự tải JDK17. Dùng đúng Compiler Plugin version và test runtime Java17 nếu đó là minimum supported Java.

### 5.3. Enforcer fail sớm khi Maven/JDK sai

Ví dụ Enforcer Plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.3</version>
    <executions>
        <execution>
            <id>enforce-build-tools</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireMavenVersion>
                        <version>[3.9.0,4.0.0)</version>
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

Đây là **snippet được dùng trong POM lab hoàn chỉnh**, không cần dán hai lần:
- Maven 3.8.x bị từ chối.
- Maven 4.x chưa được tự động cho phép nếu chưa kiểm chứng tương thích.
- Java 11 chạy Maven bị từ chối.
- Java 21 chạy Maven **được phép**, compiler vẫn target Java17. Muốn giới hạn đúng Java major 17, có thể dùng `[17,18)`.
- Rule **không cài** phiên bản Maven/JDK phù hợp; nó chỉ kiểm và báo fail.

### 5.4. Toolchains cho JDK khác JVM chạy Maven

Maven Toolchains Plugin cho project mô tả JDK requirement mà không hard-code JDK path trong POM. Ví dụ **snippet tùy chọn** (không là phần của lab mặc định):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <goals><goal>toolchain</goal></goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>[17,18)</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

Machine-local `toolchains.xml` thường nằm ở `~/.m2/toolchains.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
        </provides>
        <configuration>
            <jdkHome>/path/to/installed/jdk-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

Đường dẫn `/path/to/installed/jdk-17` chỉ là **giá trị minh họa cần thay ở từng máy**, không commit một path cứng vào POM dùng chung. Toolchain-aware plugins có thể dùng JDK này để compile/test/document; không phải plugin nào cũng hỗ trợ. Rule Enforcer `requireJavaVersion` kiểm **JDK chạy Maven**, không tự chuyển sang JDK được toolchain lựa chọn.

## 6. Repositories, settings và secret management

### 6.1. `settings.xml` không nên là một bí mật trong Git

Settings có thể chứa mirrors, proxy, servers, profiles và local repository path. Từng môi trường cần tạo settings từ template/secret manager hoặc cấu hình ngoài source. Không commit user/password/token, không đưa credentials vào `maven.config`, `distributionUrl` hoặc CI logs.

Sample `ci/settings.example.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>company-approved</id>
            <mirrorOf>*</mirrorOf>
            <url>https://repo.example.invalid/repository/maven-approved/</url>
        </mirror>
    </mirrors>
</settings>
```

**`example.invalid` cố ý không hoạt động**. Không copy file này làm CI settings thật trước khi thay URL bằng approved repository-manager endpoint. `mirrorOf=*` chuyển repository requests qua mirror, nhưng **không tự phân biệt private vs public GAV**; repository manager phải có routing/security policies để không tải nhầm nguồn.

Khi CI đã provision settings thật:

```bash
./mvnw -B -ntp -s ci/settings.xml clean verify
```

`-s` dùng alternate user settings, không tự gỡ global settings, môi trường, toolchain hoặc credentials của các job khác. Không mặc định rằng build đã không phụ thuộc máy chỉ vì chuyển settings vào một file chứa absolute path.

### 6.2. Đừng lưu repository cache vào source

Local Maven repository `~/.m2/repository` có thể chứa:
- Artifacts tải từ remote.
- Artifacts được `mvn install` cục bộ.
- Metadata/cache theo repository ID.
- Plugin dependencies và các versions trước.

Không nên copy cả `.m2` giữa developer machines hoặc upload làm “dependency source” cho CI. Tổ chức có thể cache Maven artifacts theo repository policy, nhưng cần kiểm soát origin, retention và integrity. Maven Wrapper distribution cache còn là lớp riêng với local artifact repository.

### 6.3. Cấu hình phụ thuộc host

Tránh những thứ như:
- `<systemPath>C:\Users\Alice\libs\internal.jar</systemPath>` trong project POM.
- Repository URL trỏ `localhost:8081` mà chỉ developer A chạy.
- `JAVA_HOME` path của một người được commit.
- Profile activation phụ thuộc tên user hoặc directory riêng.
- Tests đọc file `C:\Users\Alice\Desktop\fixture.json`.
- Plugin version không ghim, tải bản mới theo thời gian.
- Build pass chỉ do local `install:install-file` đã cài một JAR không tồn tại ở repository.

Thay thế bằng GAV dependency trong approved repository, classpath resources dưới `src/main/resources` hoặc `src/test/resources`, môi trường được provision và đường dẫn tương đối đúng theo project root.

## 7. Lab Java 17 hoàn chỉnh

**Mục tiêu lab:** từ một repository sạch, Wrapper dùng Maven 3.9.11, Enforcer đảm bảo Maven/JDK, Compiler target Java 17, Surefire chạy 3 tests, app in stdout ổn định. Không có database hoặc endpoint phụ thuộc máy; không gọi `deploy`.

Cấu trúc:

```text
portable-maven-lab/
├── pom.xml
├── mvnw                             (Wrapper Plugin sinh)
├── mvnw.cmd                         (Wrapper Plugin sinh)
├── .mvn/
│   ├── wrapper/maven-wrapper.properties
│   ├── maven.config
│   └── jvm.config
└── src/
    ├── main/java/dev/training/portable/
    │   ├── GreetingService.java
    │   └── App.java
    └── test/java/dev/training/portable/
        └── GreetingServiceTest.java
```

Yêu cầu:
- JDK 17+.
- Maven cài sẵn **chỉ cho người khởi tạo Wrapper lần đầu**, sau đó dùng checked-in `mvnw`.
- Network/mirror hợp lệ để tải Maven zip, JUnit và plugins nếu chưa cache.
- Quyền ghi project `target`/Wrapper distro cache.
- Không cần Docker, Maven Central account hay production credentials.

### 7.1. Tạo thư mục

Linux/macOS:

```bash
mkdir -p portable-maven-lab/src/main/java/dev/training/portable
mkdir -p portable-maven-lab/src/test/java/dev/training/portable
mkdir -p portable-maven-lab/.mvn
cd portable-maven-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "portable-maven-lab/src/main/java/dev/training/portable" | Out-Null
New-Item -ItemType Directory -Force -Path "portable-maven-lab/src/test/java/dev/training/portable" | Out-Null
New-Item -ItemType Directory -Force -Path "portable-maven-lab/.mvn" | Out-Null
Set-Location portable-maven-lab
```

Tạo các file sau đúng đường dẫn; lệnh build chạy trong `portable-maven-lab`.

### 7.2. `pom.xml` đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.portable</groupId>
    <artifactId>portable-maven-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
        <project.build.outputTimestamp>2026-11-10T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
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
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.3</version>
                <executions>
                    <execution>
                        <id>enforce-build-tools</id>
                        <goals><goal>enforce</goal></goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9.0,4.0.0)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
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
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Phân tích:
- `groupId:artifactId:version` là `dev.training.portable:portable-maven-lab:1.0.0`.
- `maven.compiler.release=17` kiểm compile target.
- Enforcer kiểm Maven version trong `[3.9.0,4.0.0)` và Java runtime Maven tối thiểu 17.
- JUnit Jupiter chỉ dùng `test` scope, không là runtime dependency của application.
- Compiler, Surefire, Jar plugins được ghim.
- `project.build.outputTimestamp` hỗ trợ deterministic ZIP entry timestamps với plugin có support; không phải cam kết hash giống nhau trên mọi OS.
- Không có `systemPath`, local hostname, credentials hoặc `distributionManagement`.

### 7.3. `GreetingService.java`

Tệp `src/main/java/dev/training/portable/GreetingService.java`:

```java
package dev.training.portable;

import java.util.Locale;

public final class GreetingService {

    private GreetingService() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        return "Hello, " + name.strip() + "!";
    }

    public static String normalizeTag(String tag) {
        if (tag == null || tag.isBlank()) {
            throw new IllegalArgumentException("tag is required");
        }
        return tag.strip().toLowerCase(Locale.ROOT);
    }
}
```

`String.strip` và `String.isBlank` tồn tại trong JDK 17. `Locale.ROOT` tránh phụ thuộc default locale cho normalization của machine-readable tag. Nếu dùng `String.toLowerCase()` mặc định, một số locale có quy tắc khác khiến test/string identifier thay đổi.

### 7.4. `App.java`

Tệp `src/main/java/dev/training/portable/App.java`:

```java
package dev.training.portable;

public final class App {

    private App() {
    }

    public static void main(String[] args) {
        System.out.println(
            "message=" + GreetingService.greet("  Maven  "));
        System.out.println(
            "tag=" + GreetingService.normalizeTag(" RELEASE "));
    }
}
```

**Stdout chính xác của Java app (nội dung hai dòng):**

```text
message=Hello, Maven!
tag=release
```

`println` dùng newline của nền tảng (LF trên Unix, CRLF thường trên Windows); nội dung từng dòng được giữ. Không nhầm hai dòng này với toàn bộ Maven build log vốn khác theo Maven/JDK/OS.

### 7.5. `GreetingServiceTest.java`

Tệp `src/test/java/dev/training/portable/GreetingServiceTest.java`:

```java
package dev.training.portable;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {

    @Test
    void trimsWhitespaceAroundName() {
        assertEquals(
            "Hello, Maven!",
            GreetingService.greet("  Maven  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
            IllegalArgumentException.class,
            () -> GreetingService.greet(" \t "));
    }

    @Test
    void normalizesTagIndependentlyOfDefaultLocale() {
        assertEquals(
            "release",
            GreetingService.normalizeTag(" RELEASE "));
    }
}
```

**Có ba JUnit Jupiter tests**, class name `GreetingServiceTest` khớp Surefire discovery pattern. Test failure phải làm `verify` và CI job fail; không dùng `-DskipTests` trong required check.

### 7.6. Khởi tạo Wrapper trong lab

Từ root đã có POM:

```bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.11 -Dtype=only-script
```

Plugin tạo launcher scripts/properties. **Không tự viết Shell script giả làm Wrapper.** Sau khởi tạo, kiểm tra `distributionUrl` và commit được review. Maven wrapper plugin và distribution tải từ approved repository như các build tools khác.

### 7.7. `.mvn/maven.config`

Tạo file:

```text
-ntp
-Dstyle.color=never
```

Đây là hai **Maven CLI arguments trên hai dòng**, dùng được với Maven 3.9.11. Không bỏ thêm `-DskipTests`. Nếu IDE muốn hiển thị color logs, team có thể chỉ commit `-ntp` và đặt color trong CI, không ảnh hưởng Java code.

### 7.8. `.mvn/jvm.config`

Tạo file:

```text
-Dfile.encoding=UTF-8
```

Không hard-code `-Xmx4096m` cho mọi máy khi chưa có nhu cầu. POM đã có `project.build.sourceEncoding=UTF-8`, vì JVM startup property và source encoding là hai lớp khác nhau.

### 7.9. Chạy và kiểm chứng

Linux/macOS:

```bash
./mvnw --version
./mvnw -B -ntp clean verify
java -cp target/classes dev.training.portable.App
```

Windows PowerShell:

```powershell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp clean verify
java -cp "target\classes" dev.training.portable.App
```

Nếu build/test thành công:
- Maven version trong Wrapper là `3.9.11`.
- Surefire chạy 3 tests, failures/errors = 0.
- JAR xuất hiện ở `target/portable-maven-lab-1.0.0.jar`.
- Java application in hai dòng đã nêu.

Surefire summary theo số tests dự kiến:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Không khẳng định đó là toàn bộ output Maven. **Không dùng `java -jar` nếu chưa cấu hình Main-Class manifest**; lab dùng `java -cp target/classes`.

### 7.10. Kiểm thử trường hợp sai version

**Maven khác:** chạy global `mvn` 3.8.x với `validate` sẽ bị Enforcer từ chối, trong khi Wrapper dùng Maven 3.9.11. **JDK 11:** Wrapper vẫn cố bootstrap Maven nhưng Enforcer/compile yêu cầu JDK 17+ nên fail. **JDK 21:** Enforcer `[17,)` pass và Compiler nhắm Java17; nhưng nên có CI test trên JDK17 nếu đó là minimum runtime supported.

**Offline:** `./mvnw -o verify` chỉ chạy được nếu Wrapper Maven distribution và tất cả dependencies/plugins đã có cache; `-o` không làm launcher tự có zip Maven nếu chưa tải.

## 8. Maven từ IDE và multi-module reactor

### 8.1. IDE có thể dùng Maven khác Wrapper

IntelliJ IDEA, Eclipse/m2e, NetBeans và các IDE khác có Maven integration/config riêng. IDE có thể dùng:
- Bundled Maven (khác version).
- External Maven ở local path.
- Maven Wrapper của project nếu IDE hỗ trợ và được chọn.

**Không suy luận IDE đang dùng Wrapper chỉ vì repository chứa `mvnw`.** Kiểm tra Maven home/runtime, JDK dùng để import project, JDK chạy Maven goals và Project SDK. Một IDE có thể import bằng JDK 11 dù terminal `java -version` là 17.

Dùng `./mvnw -B clean verify` làm **baseline chuẩn**. Nếu IDE build khác, so:
1. Maven version/Wrapper selection.
2. Maven runner JDK/`JAVA_HOME`.
3. Active Maven profiles.
4. Effective settings/mirror/proxy.
5. `.mvn/maven.config` và `.mvn/jvm.config`.
6. Annotation processor/generated source settings.

Không đổi project POM để “hợp với laptop người A” khi nguyên nhân thật là IDE runtime lệch.

### 8.2. Root Wrapper cho multi-module

Một reactor:

```text
platform/
    pom.xml                 aggregator
    mvnw
    mvnw.cmd
    .mvn/
    api/pom.xml
    app/pom.xml
```

Đặt **một Wrapper ở root** để cả reactor dùng cùng Maven version. Từ root build all modules:

```bash
./mvnw -B -ntp clean verify
```

Chọn module app và Maven reactor dependencies:

```bash
./mvnw -B -ntp -pl :app -am verify
```

`-pl` chọn project, `-am` thêm các module mà app phụ thuộc trong reactor. Khi release cả reactor cần full build/QA; đừng báo “all modules passed” khi chỉ chạy subset.

## 9. CI pipeline: lệnh ổn định và không lộ secret

Một pipeline nên:
1. Checkout đúng source commit/tag.
2. Provision JDK 17+, Java vendor theo policy.
3. Dùng checked-in Wrapper, kiểm checksum/URL khi bootstrap.
4. Cấp approved settings/credentials từ CI secret manager.
5. Gọi `./mvnw -B -ntp clean verify`.
6. Giữ exit code thật.
7. Lưu test reports/artifact provenance, không log secrets.
8. Chỉ publish sau quality gates và approval.

### 9.1. POSIX shell CI script

```bash
#!/usr/bin/env sh
set -eu

java -version
./mvnw --version
./mvnw -B -ntp clean verify
test -f target/portable-maven-lab-1.0.0.jar
java -cp target/classes dev.training.portable.App
```

`set -e` khiến script dừng khi Maven/test check lỗi. `test -f` chỉ xác nhận JAR có mặt; việc tests pass còn do Maven/Surefire exit status và reports.

### 9.2. Windows PowerShell CI

```powershell
.\mvnw.cmd -B -ntp clean verify
$code = $LASTEXITCODE
if ($code -ne 0) {
    exit $code
}
java -cp "target\classes" dev.training.portable.App
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
```

Cẩn thận khi port shell snippets: Windows classpath delimiter thường là dấu `;`, Unix là `:`. Lab dùng một thư mục `target/classes` nên không phải nối dependency runtime paths.

### 9.3. GitHub Actions YAML minh họa

Đây chỉ là example CI host, **không đòi hỏi có tài khoản GitHub** để học Maven:

```yaml
name: Maven CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Maven Wrapper verify
        run: ./mvnw -B -ntp clean verify
      - name: Java output smoke test
        run: java -cp target/classes dev.training.portable.App
```

Production workflow có thể yêu cầu pin GitHub Actions theo **reviewed commit SHA** thay vì floating tag, khóa quyền token, dùng approved Maven mirror và không cấp release secrets cho PR chưa tin cậy. Cache giúp tốc độ, không tự chứng minh artifact source. Với Windows runner, thay shell command theo PowerShell/`mvnw.cmd`.

## 10. Reproducible builds và những phụ thuộc môi trường khó thấy

Maven Wrapper chỉ ghim Maven runtime. JAR hash còn có thể phụ thuộc:
- JDK major/vendor/version.
- Maven plugin versions.
- Dependency version ranges/SNAPSHOT và repository nguồn.
- ZIP timestamps, resource timestamps, manifest.
- Source encoding và line endings.
- Default locale/timezone.
- Network resources được fetch động.
- Source generation/annotation processors.
- Tên user, directory, OS khi tool ghi metadata.

POM lab có:

```xml
<project.build.outputTimestamp>2026-11-10T00:00:00Z</project.build.outputTimestamp>
```

Tính năng `outputTimestamp` giúp archive plugins tương thích đặt timestamps có thể tái lập. Nó không có nghĩa mọi project builds luôn bit-for-bit identical. Muốn kiểm chứng, build độc lập và so checksums:

Linux/macOS:

```bash
sha256sum target/portable-maven-lab-1.0.0.jar
```

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -Path "target/portable-maven-lab-1.0.0.jar"
```

Không đưa một checksum giả vì build bytes thực phụ thuộc nhiều đầu vào. Nếu hashes khác, so JDK, resources, ZIP entries, plugin versions và generated files trước khi kết luận Wrapper lỗi.

### 10.1. Encoding, locale và timezone

- Trong POM, khai báo `project.build.sourceEncoding=UTF-8`.
- Trong code xử lý identifiers, dùng `Locale.ROOT` thay vì default locale khi phù hợp.
- Với logic thời gian, dùng `Clock` có thể inject vào tests, hoặc `Instant`/UTC.
- Với generated files, quyết định newline LF/CRLF policy.
- Tránh test so exact ANSI/color/progress lines trong Maven console logs.
- Nếu test cần timezone mặc định riêng, cấu hình tường minh trong test JVM; đừng dựa vào timezone máy tác giả.

### 10.2. Absolute path và system-scope dependencies

Không nên dùng:

```xml
<dependency>
    <groupId>dev.training</groupId>
    <artifactId>local-utils</artifactId>
    <version>1.0.0</version>
    <scope>system</scope>
    <systemPath>C:\Users\Alice\libs\local-utils.jar</systemPath>
</dependency>
```

Đây là **anti-pattern**, không phải phần của POM lab. Đường dẫn đó không tồn tại trên Linux runner và không tạo provenance tốt. Thay bằng Maven GAV trong approved repository hoặc build module đó trong reactor. Những path của JDK trong `toolchains.xml` là **machine-local**, hợp lệ nếu mỗi runner tự provision, khác với hard-code path trong shared POM.

### 10.3. Resources và config

Không nên đọc file cố định như `C:\Users\Alice\Desktop\config.json` từ Java code. Nếu đó là static resource của app, đưa dưới `src/main/resources` rồi đọc qua `ClassLoader.getResourceAsStream` hoặc `App.class.getResourceAsStream`. Nếu đó là secret, cung cấp qua secret manager/môi trường deployment thay vì commit trong JAR.

Không đưa `.m2` của developer vào Git. `.gitignore` mẫu:

```gitignore
/target/
/out/
/.idea/
*.iml
.classpath
.project
.settings/
```

**Không ignore toàn bộ `.mvn/`**: nó chứa project-owned Wrapper và config cần được commit/review.

## 11. Offline, proxy, Maven Wrapper bootstrap và bảo mật

### 11.1. Offline không có nghĩa không cần chuẩn bị

```bash
./mvnw -B -ntp -o verify
```

`-o` bảo Maven Resolver chỉ dùng artifacts trong local repository. Nhưng launcher Wrapper **chạy trước khi Maven được khởi động**; nếu Maven distribution chưa cache thì vẫn cần nguồn để tải. Cũng phải có các build plugins, JUnit, dependencies trong cache.

Vì vậy không gọi `-o` như một “bản sửa” khi CI vừa bị 401/429/TLS problem. Hãy provision source/credentials/cache hợp lệ.

### 11.2. Proxy của Wrapper khác proxy của Resolver

Với `only-script`, bootstrap có thể dùng curl/wget/PowerShell; Maven Resolver sau đó dùng JVM HTTP transport. `settings.xml` proxy có thể ảnh hưởng resolver nhưng không phải lúc nào giải quyết được bootstrap download. Điều tra đúng tầng:
- Wrapper distribution URL/cache và checksum.
- Outbound HTTPS/proxy của shell.
- JVM truststore, proxy/server settings.
- Corporate repository manager/mirror.
- CA cert chain, DNS, firewall.

**Không tắt certificate verification** để “fix” SSL error trong CI. Không nhét password vào distributionUrl được commit.

### 11.3. Debug logs và credentials

`-X` có thể in nhiều cấu hình/URLs/headers. `help:effective-settings` ẩn passwords theo mặc định; **không bật `-DshowPasswords=true` trong log chia sẻ**. Dù ẩn password, log vẫn có thể lộ internal URLs/usernames. Chỉ thu logs chi tiết theo quyền cần thiết, sanitize trước khi chia sẻ.

### 11.4. Dependency source cũng cần được pin/trust

Một build đúng Maven version vẫn có thể tải plugin/dependency từ repository không được duyệt. Dùng mirrors/repository manager với routing policies, pin plugin/dependency versions, kiểm approved artifacts provenance và tránh snapshot/dynamic versions trong releases. Wrapper không tự thay thế kiểm soát này.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân hay gặp | Hướng xử lý |
| --- | --- | --- |
| `./mvnw: Permission denied` | `mvnw` mất executable bit | Kiểm file mode và checkout |
| PowerShell không chạy `./mvnw` | Dùng launcher Unix | `.\mvnw.cmd` |
| Wrapper không tải Maven | URL/TLS/proxy/credentials/checksum | Xem Wrapper properties và approved network |
| Maven version khác khi dùng IDE | IDE bundled/external Maven | Chọn Wrapper/Maven runtime đúng |
| Maven đúng version nhưng Java cũ | Wrapper không tải JDK | Provision JDK17+; xem Maven runtime Java |
| `release version 17 not supported` | Compiler JDK cũ | JDK17+ hoặc toolchain phù hợp |
| Enforcer `requireJavaVersion` fail | JVM đang chạy Maven sai | Chỉnh CI/IDE Maven JDK |
| `-B -ntp` trong `maven.config` bị lỗi | Hai tokens trên một dòng ở Maven 3.9+ | Mỗi option một dòng |
| JVM báo `Could not find or load main class #` | Dòng comment trong `jvm.config` không được Maven 3 hỗ trợ | Bỏ comments khỏi file |
| Build pass local, fail CI vì dependency | Cache/local install hoặc settings khác | Dùng approved repo, kiểm sources |
| CI log tràn progress | Không dùng `-ntp` hoặc bật `-X` | Giảm noise, giữ error details |
| `BUILD SUCCESS` nhưng không có test | `skipTests` hoặc naming/config sai | Xem Surefire test results |
| Maven chờ mãi | Network hoặc plugin interactive | `-B`, CI timeout, kiểm plugin/config |
| Offline fail | Thiếu distro/plugins/dependencies trong cache | Provision cache chính thống |
| 401/403 | Server credentials/permissions | Check server ID/proxy/policy |
| PKIX certificate error | JVM/proxy CA trust | Cài trusted CA đúng cách |
| JAR hashes khác | JDK/plugins/timestamps/line endings | Reproducibility analysis |
| Maven không thấy module | CWD/`-f`/`-pl`/`-N` không đúng | Chạy từ root Wrapper, kiểm reactor |
| CI exit 0 dù test fail | Shell che exit code/`-fn` | Sửa script/job policy |

### 12.1. Chuỗi lệnh điều tra

Linux/macOS từ root:

```bash
java -version
javac -version
./mvnw --version
./mvnw -B -ntp -e validate
```

Bước tiếp theo, khi có quyền: xem `.mvn/maven.config`, `.mvn/jvm.config`, effective settings, CI environment variables và Maven repository manager logs. Tránh xuất nội dung secret/token vào ticket công khai.

## 13. Bài tập ứng dụng

**Bài 1.** Một người dùng Maven 3.8, người khác 3.9.11. Lệnh nào nên là baseline?

**Đáp án:** Checked-in `./mvnw`/`mvnw.cmd`; Maven version trong Wrapper distribution được pin. Enforcer nên kiểm minimum/range.

**Bài 2.** Wrapper chạy Maven 3.9.11 nhưng JDK 11, vì sao build Java17 fail?

**Đáp án:** Wrapper không cung cấp JDK; Maven Enforcer và Compiler yêu cầu Java17+. Phải provision JDK hoặc toolchain.

**Bài 3.** `-B` và `-ntp` có phải cùng một tùy chọn không?

**Đáp án:** Không. `-B` là batch/noninteractive, `-ntp` ẩn transfer progress.

**Bài 4.** `.mvn/maven.config` có dòng `-B -ntp` trên Maven 3.9.x. Tại sao sai?

**Đáp án:** Maven 3.9 đọc một argument mỗi dòng, nên phải tách thành `-B` và `-ntp`.

**Bài 5.** Maven CLI option và JVM startup option nên đặt ở đâu?

**Đáp án:** Maven CLI trong `maven.config` hoặc CLI; JVM options như `-Xmx` trong `jvm.config` hoặc `MAVEN_OPTS`.

**Bài 6.** `MAVEN_ARGS` hoạt động từ Maven version nào trong Apache docs?

**Đáp án:** Maven 3.9.0 trở đi.

**Bài 7.** Sao không commit local JDK path từ `toolchains.xml` vào shared POM?

**Đáp án:** Path cài JDK khác theo môi trường; POM mô tả yêu cầu, runner/local toolchain cung cấp path.

**Bài 8.** Enforcer `requireJavaVersion [17,)` có từ chối Java 21 không?

**Đáp án:** Không. Nó yêu cầu Java tối thiểu 17. Muốn giới hạn major 17, dùng `[17,18)`.

**Bài 9.** Lab app in những dòng nào?

**Đáp án:** `message=Hello, Maven!` và `tag=release`.

**Bài 10.** Lab có bao nhiêu unit tests?

**Đáp án:** 3 tests: trim, blank rejection, locale-independent normalize.

**Bài 11.** Wrapper `only-script` có nghĩa build offline 100% không?

**Đáp án:** Không. Trước lần đầu Maven distribution cần được tải/cache; Maven plugins/dependencies cũng cần sẵn.

**Bài 12.** Project đang dùng `scope=system` với JAR dưới home của một người. Sửa thế nào?

**Đáp án:** Publish GAV vào approved repository hoặc build module trong reactor, không hard-code path.

**Bài 13.** `mirrorOf=*` đảm bảo không có dependency confusion chưa?

**Đáp án:** Chưa. Repository manager phải có approved upstream/routing policies, nhất là private namespace không fallback sang public.

**Bài 14.** Có nên dùng `-fn` trong required release CI không?

**Đáp án:** Không. Nó có thể che failures và làm job thành công giả; dùng exit status thật.

**Bài 15.** Wrapper và `outputTimestamp` có bảo đảm JAR giống bit-for-bit trên mọi máy không?

**Đáp án:** Không. Còn JDK, plugin, resources, line endings, generated inputs; cần kiểm chứng rebuild độc lập.

**Bài 16.** Tại sao Wrapper file changes cần code review?

**Đáp án:** Launcher scripts được thực thi trước Maven goals và có thể ảnh hưởng bảo mật CI.

**Bài 17.** Khi IDE Maven version khác CLI, nên sửa POM theo IDE hay config IDE?

**Đáp án:** Đối chiếu IDE Maven runner/JDK/settings với project Wrapper baseline; không biến POM thành config laptop.

**Bài 18.** CI đang dùng cache Maven, có cần source provenance không?

**Đáp án:** Có. Cache là tối ưu tốc độ, không xác thực nguồn artifact.

**Bài 19.** Tại sao không cho `./mvnw -o` là solution cho proxy bị lỗi?

**Đáp án:** Thiếu artifacts/distro trong cache thì offline fail; phải sửa/provision mạng và mirror đúng.

**Bài 20.** Tác dụng của `-pl :app -am` với reactor?

**Đáp án:** Chọn module app và những modules mà app phụ thuộc trong reactor; không có nghĩa full reactor đã pass.

## 14. Checklist đưa vào dự án thật

- [ ] Root repo chứa `mvnw`, `mvnw.cmd`, Wrapper properties được commit và review.
- [ ] Maven version pin rõ, không phụ thuộc Maven trên PATH.
- [ ] Wrapper distribution source HTTPS được approved, checksum verified khi cần.
- [ ] Maven Wrapper scripts executable/working trên Linux và Windows theo môi trường cần hỗ trợ.
- [ ] JDK version được provision trong developer setup và CI.
- [ ] Enforcer rules kiểm Maven/JDK range thực tế.
- [ ] Compiler `release` target đúng minimum Java API/runtime.
- [ ] Plugins/critical dependencies ghim versions.
- [ ] `.mvn/maven.config` một argument một dòng cho Maven 3.9.x.
- [ ] `.mvn/jvm.config` chứa JVM flags hợp lệ, không paths riêng người dùng.
- [ ] Không commit secrets, local `settings.xml` hoặc `toolchains.xml` hard-coded.
- [ ] CI có approved mirror/repository manager với source controls.
- [ ] CI dùng `-B`, `-ntp`, timeout và truyền exit code.
- [ ] Không dùng `-fn` hoặc skip tests trong required gates.
- [ ] Unit tests và output thực tế được kiểm tra trên JDK minimum supported.
- [ ] Không có system-scope/absolute file dependencies.
- [ ] IDE import/sync dùng Maven/JDK phù hợp Wrapper baseline.
- [ ] Local cache không phải nguồn của artifacts thiếu trên remote.
- [ ] Timestamp/encoding/locale/timezone được kiểm khi cần reproducibility.
- [ ] CI artifact logs không chứa secrets, có build provenance.
- [ ] Bootstrap trên runner sạch/Windows/Linux được thử khi cần.
- [ ] Release không được phát hành chỉ vì một local build `BUILD SUCCESS`; cần QA/approval.

## 15. Tài liệu chính thức

- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/): tạo và chạy `mvnw`/`mvnw.cmd`, types, checksums.
- [Apache Maven Wrapper Plugin — wrapper:wrapper](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html): `-Dmaven`, `-Dtype`, distribution URL.
- [Apache Maven Wrapper Plugin — Usage](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html): four distribution strategies.
- [Maven Wrapper Distribution](https://maven.apache.org/tools/wrapper/maven-wrapper-distribution/): cấu phần các Wrapper types.
- [Configuring Apache Maven](https://maven.apache.org/configure.html): `MAVEN_OPTS`, `MAVEN_ARGS`, `maven.config`, `jvm.config` và quy tắc phiên bản.
- [Maven CLI Options Reference](https://maven.apache.org/ref/3-LATEST/maven-embedder/cli.html): `-B`, `-ntp`, `-o`, `-s`, `-fae`, `-fn`.
- [Maven Settings Reference](https://maven.apache.org/settings.html): settings, mirrors, servers, profiles.
- [Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html): `mirrorOf` và repository manager.
- [Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html): JDK requirement trong POM và local `toolchains.xml`.
- [Maven Enforcer — requireMavenVersion](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html): Maven version rules.
- [Maven Enforcer — requireJavaVersion](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html): JDK runtime rules.
- [Maven Compiler Plugin — Setting release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): target Java APIs/bytecode.
- [Configuring Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html): `outputTimestamp`, compare builds.
- [Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): compile/test/verify/install/deploy.
- [Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor semantics.
