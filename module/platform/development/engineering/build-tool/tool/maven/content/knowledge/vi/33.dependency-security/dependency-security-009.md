# Tránh lộ token hoặc mật khẩu qua POM, log và báo cáo trong Maven

## 1. Vì sao bảo vệ credentials là một phần của an toàn phụ thuộc?

Trong chủ đề **An toàn phụ thuộc**, Maven cần kết nối các repository để tải dependencies, plugins và đôi khi để publish artifacts. Private Maven repositories (Nexus Repository, Artifactory, GitHub Packages, các dịch vụ nội bộ...) thường yêu cầu **username/password, access token hoặc credentials ngắn hạn**.

Nếu credential bị đặt sai vị trí hoặc in ra diagnostic output, nó có thể bị lộ qua **ba đường chính**:

1. **POM và source control**: `pom.xml`, `.mvn/maven.config`, profiles, Git history, source JAR, tệp resources hoặc cấu hình được commit.
2. **Maven, plugin và CI logs**: Maven `-X` debug, `-e` stack trace, lệnh có `-Dsecret=value`, process listing, shell history, HTTP URL chứa username/token, exceptions, `System.out.println` hoặc step log của CI.
3. **Báo cáo/artifacts**: Surefire XML/text report, HTML test/site reports, dependency or plugin outputs, SBOM/báo cáo security, crash dumps, archived workspace, screenshots và các file đính kèm ticket.

**Mục tiêu không chỉ là “không viết mật khẩu trực tiếp trong POM”.** Cần quản lý cả vòng đời secret: **tạo với quyền tối thiểu → cấp cho đúng job/tool → không in/đóng gói → bảo vệ log/report → thu hồi/rotate khi nghi ngờ**.

Đường đi lý tưởng:

```text
Private Maven repository
         ^
         | authenticated HTTPS
         |
Maven Resolver / Deploy Plugin
         ^
         | server id + credentials
         |
user/CI settings.xml  <---- CI secret store / short-lived credential
         ^
         | server <id> matches repository or mirror id
         |
POM chỉ chứa repository id, URL không có thông tin đăng nhập
         |
         +-- Git: chỉ source và cấu hình không bí mật
         +-- Log: chỉ trạng thái không nhạy cảm
         +-- Report: đã loại bỏ secret trước khi chia sẻ
```

Bài này dựa trên Maven 3.9.x và Java 17, đồng thời giải thích các thay đổi bảo mật trên Maven 3.10+/Maven 4. Các ví dụ **không chứa credential thật**, không yêu cầu đăng nhập hay deploy lên hệ thống bên ngoài.

## 2. Phân biệt những giá trị nào là secret

| Giá trị | Thông thường là secret? | Cách xử lý |
| --- | --- | --- |
| `repository id` như `team-releases` | Không, nhưng có thể tiết lộ cấu trúc tổ chức | Để trong POM nếu được phép; không coi là token |
| URL `https://repo.example.invalid/maven/releases/` | Không chứa credential; endpoint nội bộ có thể nhạy cảm | URL tách khỏi token; kiểm tra trước khi chia sẻ |
| Git commit SHA, Maven GAV | Không phải secret theo mặc định | Ghi log để truy vết nếu chính sách cho phép |
| Username triển khai | Có thể là thông tin cần bảo vệ | Không in tùy tiện, không hardcode |
| Password/token/API key | **Có** | CI secret store/secret manager, quyền tối thiểu, không in |
| `Authorization: Bearer ...` | **Có** | Không ghi header vào logs/reports |
| HTTP Basic Base64 của `username:token` | **Có** | Base64 là encoding, không phải encryption |
| Password đã mã hóa theo cơ chế Maven 3 | **Vẫn phải bảo vệ** | Không commit hoặc chia sẻ như giá trị công khai |
| Private SSH key/GPG signing key | **Có** | Key store/agent, quyền file nghiêm ngặt |
| Maven Central dependency version/checksum | Thường không | Có thể công khai, nhưng vẫn phải xác thực nguồn |
| Test fixture rõ ràng không phải credential | Không | Không dùng nhầm secret thật để viết test |

**Một chuỗi chỉ an toàn khi nó thực sự không cấp quyền.** Đừng gọi token còn hiệu lực là “sample token” rồi đưa vào tài liệu. Trong ví dụ của bài, domain `example.invalid` và chuỗi fixture trong JUnit đều **không hoạt động và không đại diện token thật**.

## 3. Anti-pattern nguy hiểm: secret trực tiếp trong pom.xml

Một cấu hình cần tránh:

```xml
<!-- PHẢN VÍ DỤ: đừng dùng trong dự án thật -->
<repositories>
    <repository>
        <id>private-libs</id>
        <url>https://account:DEMO_NOT_A_REAL_SECRET@repo.example.invalid/maven/</url>
    </repository>
</repositories>
```

Chuỗi `DEMO_NOT_A_REAL_SECRET` chỉ là **fixture minh họa vô hiệu**. Vấn đề nằm ở **cách nhúng credential trong URL**, không phải giá trị cụ thể.

Các nguy cơ:

- POM được commit, fork, review, xuất hiện trong Git history và pull-request diffs.
- Một số Maven artifacts còn kèm POM metadata, làm secret có khả năng bị phân phối theo artifact.
- Maven/debug/log/error có thể in URL đầy đủ hoặc URL sau biến đổi.
- CI, scanners và IDE plugins có thể đọc, sao lưu, cache POM.
- Git history vẫn lưu giá trị cũ dù bạn xóa dòng ở commit mới.

Cũng tránh:

```xml
<!-- PHẢN VÍ DỤ: secret literal trong Maven properties -->
<properties>
    <internal.api.token>DEMO_NOT_A_REAL_SECRET</internal.api.token>
    <internal.repo.password>DEMO_NOT_A_REAL_SECRET</internal.repo.password>
</properties>
```

Đừng dùng `<properties>` làm kho bí mật. Maven property interpolation có thể khiến giá trị di chuyển sang plugin configuration, generated resources, reports hoặc effective POM.

### 3.1. POM đúng: chỉ giữ repository ID/URL không chứa secret

Ví dụ download repository:

```xml
<repositories>
    <repository>
        <id>team-private-read</id>
        <url>https://repo.example.invalid/repository/maven-group/</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
```

Ví dụ đích phát hành (đoạn khác trong cùng POM, **chỉ dành cho project được cấp quyền deploy**):

```xml
<distributionManagement>
    <repository>
        <id>team-releases</id>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>team-snapshots</id>
        <url>https://repo.example.invalid/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

**Hai khái niệm khác nhau**:

- `<repositories>` và `<pluginRepositories>` định nghĩa nơi **tải về** dependencies/plugins.
- `<distributionManagement>` định nghĩa đích **upload/publish** của Maven Deploy Plugin.
- `<mirrors>` ở `settings.xml` có thể thay đổi endpoint download; mirror không mặc nhiên đổi đích deploy.
- `<servers><server><id>...` liên kết repository hoặc mirror đến credentials ở môi trường người dùng/CI.

**Repository ID không phải token.** ID dùng để Maven chọn cấu hình authentication; giá trị secret phải được cấp ở nơi khác.

## 4. Dùng settings.xml cho authentication

Maven hỗ trợ user settings tại `${user.home}/.m2/settings.xml`, thường là `~/.m2/settings.xml` trên Unix/macOS. File này dùng cho **môi trường/máy**, không phải mã nguồn của một project.

Một ví dụ không chứa secret literal:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>team-private-read</id>
            <username>${env.MAVEN_READ_USER}</username>
            <password>${env.MAVEN_READ_TOKEN}</password>
        </server>
        <server>
            <id>team-releases</id>
            <username>${env.MAVEN_DEPLOY_USER}</username>
            <password>${env.MAVEN_RELEASE_TOKEN}</password>
        </server>
        <server>
            <id>team-snapshots</id>
            <username>${env.MAVEN_DEPLOY_USER}</username>
            <password>${env.MAVEN_SNAPSHOT_TOKEN}</password>
        </server>
    </servers>
</settings>
```

**Đây là mẫu user/CI settings**, không yêu cầu chép file này vào Git. Các biến môi trường phải được secret manager cấp thật khi job cần dùng chúng.

### 4.1. ID phải trùng đúng

| Thao tác | ID trong cấu hình POM/settings | Cấu hình server cần khớp |
| --- | --- | --- |
| Download private dependency | `team-private-read` | `servers/server/id = team-private-read` |
| Deploy release | `team-releases` | `servers/server/id = team-releases` |
| Deploy SNAPSHOT | `team-snapshots` | `servers/server/id = team-snapshots` |
| Download qua mirror | ID của mirror hiệu lực | Server ID thường phải khớp mirror ID mà resolver dùng |

Nếu repository URL đúng nhưng ID bị lệch, Maven có thể **không lấy được credentials phù hợp**, gây 401/403. Không “sửa” bằng cách chuyển password từ settings vào POM.

### 4.2. Environment interpolation trong settings

Maven Settings Reference hỗ trợ interpolation các environment variables qua cú pháp:

```text
${env.MAVEN_READ_TOKEN}
```

và Java system properties như `${user.home}`. Tuy nhiên **properties định nghĩa trong profile của chính settings.xml không dùng để interpolate phần settings khác** theo cách đó.

Giá trị thật có thể do shell hoặc CI secret manager cung cấp. Nếu biến không có mặt, kết quả có thể là lỗi resolution/xác thực hoặc giá trị chưa được thay; kiểm tra nguyên nhân trong môi trường bảo mật, **không echo giá trị** để debug.

### 4.3. Quyền file và đường dẫn

Trên Unix/macOS:

```bash
chmod 700 ~/.m2
chmod 600 ~/.m2/settings.xml
```

Chỉ áp dụng cho **settings file của chính bạn** khi file đã tồn tại và chính sách cho phép. Trong CI, tạo file cấu hình tạm ở nơi chỉ job được đọc và xóa an toàn theo vòng đời runner.

Trên Windows, dùng NTFS ACL để giới hạn quyền đọc; `chmod` không phải cơ chế tương đương trên Windows PowerShell.

**Không commit `settings.xml` có credentials vào Git**. Thư mục Maven local repository cũng không phải nơi lưu trữ secrets lâu dài; plugins có thể ghi metadata/cache không mong đợi, nên kiểm soát quyền truy cập máy build.

### 4.4. Maven 4 project settings: không phải nơi đặt passwords

Maven 4 hỗ trợ project-level `.mvn/settings.xml` nhưng **bỏ qua user-specific credentials trong project settings**, theo Settings Reference. Không dùng file dưới repository làm cách “chia sẻ cấu hình có token” cho cả team. Vẫn cần user/CI secret settings bên ngoài source tree.

## 5. Maven 3 password encryption không thay secret manager

Maven 3.x cung cấp cơ chế mã hóa password qua các lệnh `--encrypt-master-password` và `--encrypt-password`, dùng file `settings-security.xml`.

**Nhưng tài liệu chính thức mô tả bảo vệ này ở mức obfuscation-grade**, không thay thế secrets management hay file permissions. Ai có được cả encrypted values và master material có thể giải mã.

Khi sử dụng Maven 3:

1. Tránh truyền mật khẩu thẳng thành argument của lệnh encryption.
2. Sử dụng cách nhập tương tác theo phiên bản được hỗ trợ.
3. Bảo vệ `settings.xml` và `settings-security.xml` cùng những file backup/editor history.
4. Không commit encrypted credential và master configuration vào repository.
5. Với CI, thường ưu tiên token ngắn hạn do secret manager cấp và settings file sinh tạm thay vì cố coi encrypted literal là “an toàn để public”.
6. Nếu máy build bị xâm nhập, **mã hóa Maven 3 không ngăn việc token đang sử dụng bị lấy ra**.

Maven 4 đưa vào cơ chế password encryption mạnh hơn và công cụ `mvnenc`, với các dispatchers và master-key sources. Theo tài liệu Maven 4, có thể dùng:

```bash
mvnenc init
mvnenc diag
```

Các lệnh này liên quan Maven 4 và cấu hình mã hóa, **không phải Maven 3 commands**. Khi tổ chức chuyển phiên bản, tham khảo tài liệu Maven 4 cho `settings-security4.xml` và cách quản lý master key.

**Quy tắc:** mã hóa giá trị lưu trên ổ đĩa là một lớp phòng vệ, nhưng **không có nghĩa có thể in nó ra log, phát tán bản settings, hoặc dùng token có quyền quá rộng**.

## 6. Không truyền token qua Maven CLI arguments

Phản ví dụ:

```bash
# KHÔNG CHẠY: có thể lộ vào shell history, process list và CI logs
mvn deploy -Drepository.password=DEMO_NOT_A_REAL_SECRET
```

Chuỗi minh họa không có quyền truy cập. Nhưng nếu thay bằng token thật, các nguy cơ gồm:

- Shell history ghi toàn command line.
- Process listing của hệ điều hành có thể nhìn thấy arguments.
- CI lưu thông số command dưới dạng log/metadata.
- Maven và plugin có thể echo user properties trong debug/exception.
- Maven Surefire có thể chuyển user/system properties sang forked tests.
- Lệnh được copy vào issue/ticket/chat làm tăng phạm vi phát tán.

Cũng tránh `-Dtoken=...`, `-Dpassword=...`, secret trong `MAVEN_OPTS`, `JAVA_TOOL_OPTIONS`, `.mvn/maven.config` hoặc `.mvn/jvm.config`. Một số file `.mvn/*` được commit theo project và JVM command-line options có thể lộ qua process inspection.

**Thay thế:** gắn credentials với server ID trong **user/CI settings.xml**, lấy giá trị từ CI secret manager qua env interpolation. Các plugin không dùng Maven server authentication cần cơ chế chính thức của plugin (ví dụ credential provider, env var name, secret file), không tự biến token thành POM property.

### 6.1. Environment variables cũng cần bảo vệ

Biến môi trường **không phải vault**:

- Process con hoặc code chạy cùng job có thể đọc env.
- Debuggers/crash dumps, telemetry và plugin độc hại có thể thu thập env.
- Nếu shell in biến hoặc `env`/`printenv`, nó vẫn lộ.
- Trên shared runners, đặc quyền OS và cô lập job có ý nghĩa lớn.

Vì thế **cấp env chỉ ở bước thực sự cần** và chạy trên trusted runner. Không đưa secrets vào job của pull request không đáng tin cậy hoặc scripts do attacker kiểm soát.

### 6.2. Không nhúng credential vào URL

Tránh:

```text
https://username:DEMO_NOT_A_REAL_SECRET@repo.example.invalid/repository/releases/
scm:git:https://username:DEMO_NOT_A_REAL_SECRET@git.example.invalid/team/repo.git
```

Những URL này có thể bị ghi vào POM, Git config, process logs, exceptions hoặc report. Dùng URL sạch và cơ chế authentication riêng như server settings, SSH agent hoặc SCM provider credential store.

**Đừng gửi token trong query string** dạng `?access_token=...`; proxies, access logs, monitoring và reports có thể ghi nguyên URL.

## 7. Maven log: giảm dữ liệu chứ không chỉ che chuỗi

Một log có thể vô tình chứa:

```text
[INFO] Downloading from team-private-read: https://repo.example.invalid/...
[ERROR] Authentication failed for server team-releases
[DEBUG] ... plugin configuration / system properties ...
```

Các dòng chỉ là **minh họa format**, không phải log thực tế. URL hoặc server ID có thể không phải secret nhưng vẫn lộ topology nội bộ.

### 7.1. Các tùy chọn cần phân biệt

| Tùy chọn Maven | Tác dụng | Đánh giá bảo mật |
| --- | --- | --- |
| `-B` / `--batch-mode` | Không hỏi tương tác | Có ích trong CI, **không che secrets** |
| `-ntp` | Không hiển thị download transfer progress | Giảm noise, **không phải redaction** |
| `-q` | Quiet mode | Giảm log, **không đảm bảo log không lộ** |
| `-e` | Stack traces của lỗi | Có thể chứa dữ liệu plugin/config/path |
| `-X` | Full debug logging | **Chỉ dùng ở môi trường được kiểm soát**, dễ lộ cấu hình nhạy cảm |
| `-s /path/settings.xml` | Chọn settings file | Giúp dùng CI settings riêng; path vẫn có thể bị in |
| `-D...` | Truyền user property | Tránh dùng để mang giá trị secret |

**Không bao giờ coi `mvn -q` là lớp bảo vệ đủ để publish raw logs ra công khai.** Những Maven plugins và custom scripts có thể tự in nội dung họ nhận được.

### 7.2. Debug 401/403 mà không xuất token

Cách đọc lỗi:

- **401 Unauthorized**: credentials thiếu/sai, challenge authentication hoặc cấu hình server ID không khớp.
- **403 Forbidden**: tài khoản bị hạn chế quyền hoặc repository policy chặn.
- **404/400/409**: URL sai, version policy, conflict/redeploy forbidden... tùy server.

Kiểm tra theo thứ tự:

1. Effective repository ID và URL **không chứa userinfo/token**.
2. `settings.xml/servers/server/id` khớp ID cần dùng.
3. CI job có được cấp secret **ở đúng step** không (kiểm tra biến có mặt, không in giá trị).
4. Token còn hiệu lực, scope đủ hẹp nhưng đúng operation (read vs publish).
5. Repository manager còn tồn tại, policy snapshot/release và origin binding.
6. Xem status code, non-sensitive error code và phần log đã rà soát.
7. Nếu cần debug sâu, chạy trong **ephemeral private runner**, không đăng nguyên `-X` output lên công khai.

**Không yêu cầu người dùng gửi password/token để “xem giúp”**. Một screenshot có phần password bị che thủ công cũng có thể lộ ở tab khác hoặc clipboard; chia sẻ cấu hình đã xóa hoàn toàn secrets mới là cách đúng.

## 8. help:effective-settings và help:effective-pom: hữu ích nhưng cần kiểm soát

Hai lệnh thường dùng:

```bash
mvn help:effective-pom
mvn help:effective-settings
```

- `help:effective-pom` hiển thị POM sau inheritance/profiles/interpolation, có thể chứa URLs, plugin properties hoặc giá trị config nhạy cảm nếu đã đưa secret sai chỗ.
- `help:effective-settings` hiển thị settings được hợp nhất; Maven Help Plugin **mặc định ẩn passwords**, nhưng vẫn có thể hiển thị nhiều thông tin về servers, URLs, profiles và proxy endpoints.
- Maven Help Plugin có tùy chọn **`showPasswords=true`** để hiện passwords. **Không bật trên CI hoặc khi chuẩn bị gửi log ra ngoài**.
- Một report khác hoặc Maven plugin version cũ có thể không thực hiện redaction giống Help Plugin, vì vậy đừng suy luận “Maven luôn tự che tất cả secrets”.

Tập lệnh kiểm tra tương đối ít noise:

```bash
mvn -B -ntp help:effective-pom
mvn -B -ntp help:effective-settings
```

**Chạy trong môi trường riêng rồi kiểm tra output trước khi share.** Không coi stdout của lệnh này là đã được approve để đính vào ticket, upload làm artifact hoặc copy sang diễn đàn.

### 8.1. Dấu hiệu rò rỉ khó nhận ra

Một credential có thể xuất hiện dưới nhiều dạng:

- URL-encoded: ký tự đặc biệt được percent-encode.
- Base64 HTTP Basic: vẫn giải mã dễ dàng.
- Prefix/suffix hoặc token bị cắt bớt trong log.
- JSON/XML-escaped strings.
- Header authorization, cookies hoặc proxy credentials.
- Key-value `password=...` và `token=...`.
- Stack trace exception message chứa request URL.
- Artifact metadata hoặc generated resources.
- Hash của token: thường không cần in và có thể vẫn gây lộ thông tin khi token yếu hoặc bị đối chiếu.

**Masking tự động không bảo đảm nhận diện mọi biến thể.** Ưu tiên **không bao giờ tạo bản log chứa credential** thay vì chỉ tìm và thay chuỗi sau đó.

## 9. Test reports: Surefire có thể mang theo secret

Maven Surefire Plugin chạy unit tests ở phase `test` và thường tạo:

```text
target/surefire-reports/
    TEST-dev.course.SafeDiagnosticsTest.xml
    dev.course.SafeDiagnosticsTest.txt
```

Các files này có thể được CI upload, lưu lâu hoặc gắn vào PR. Tùy cấu hình/plugin version, reports có thể chứa:

- Test case names/status/time.
- `system-out` / `system-err` hoặc console output được capture.
- Exception messages, assertion expected/actual values.
- Stack traces khi fail.
- Properties của test JVM và một số environment-derived configuration khi được chuyển thành system properties.
- Đường dẫn workspace, URLs, hostnames, classpaths và các thông tin build khác.

**Không assume mọi env var tự động có trong XML**, nhưng **bất cứ secret nào bạn chuyển vào system property, in ra stdout/stderr hoặc đưa vào exception có thể bị đưa vào report**.

### 9.1. Anti-pattern test logs

Phản ví dụ Java:

```java
// PHẢN VÍ DỤ, không dùng token thật ở đây:
System.out.println(System.getenv("MAVEN_READ_TOKEN"));
```

Và một cấu hình Surefire nguy hiểm nếu biến là secret:

```xml
<!-- PHẢN VÍ DỤ: có thể đưa secret vào JVM properties/report -->
<systemPropertyVariables>
    <access.token>${env.MAVEN_READ_TOKEN}</access.token>
</systemPropertyVariables>
```

**Dù Maven resolver cần token để tải artifacts, unit test thường không cần biết token đó.** Đừng truyền credentials đọc repository qua `systemPropertyVariables` của test JVM nếu không có yêu cầu hợp lệ và kiểm soát reports chặt.

### 9.2. Report upload không phải hành động vô hại

Ví dụ nếu workflow có bước kiểu:

```yaml
- name: Upload test reports
  uses: actions/upload-artifact@v4
  with:
    name: surefire-reports
    path: target/surefire-reports/
```

thì reports có thể được lưu/cho phép tải theo quyền artifact retention. **Trước khi upload, phải bảo đảm tests không đưa secrets vào XML/txt**, và áp quyền truy cập/retention phù hợp. Một CI job fail nhưng report vẫn được upload để debug không tự tạo ra quyền công khai; cấu hình quyền cụ thể theo platform.

**Không tự thêm `-DtrimStackTrace=false` hoặc bật debug trong tests chứa credentials rồi upload toàn bộ logs.** Hãy giảm dữ liệu ở nguồn và rà soát trước chia sẻ.

## 10. Một ví dụ Java 17: diagnostic không in credentials

Mục tiêu lab là dạy **cách hiển thị trạng thái an toàn** thay vì in raw token, với mã chạy được và test tự kiểm tra rằng token fixture không xuất hiện.

### 10.1. Cấu trúc Maven project

```text
secret-hygiene-lab/
├── pom.xml
└── src/
    ├── main/java/dev/course/
    │   ├── SafeDiagnostics.java
    │   └── App.java
    └── test/java/dev/course/
        └── SafeDiagnosticsTest.java
```

**Project này không đăng nhập vào repository thật.** Maven tải JUnit/plugins qua repository đã có quyền truy cập theo môi trường, còn Java demo chỉ nhận **giá trị giả lập trong tests** để minh họa an toàn khi ghi log.

### 10.2. pom.xml hoàn chỉnh

Tạo `secret-hygiene-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.course</groupId>
    <artifactId>secret-hygiene-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
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
                <version>3.4.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
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

Project không có `<distributionManagement>` vì lab **không thực hiện deploy**. Không cần cấp token xuất bản cho một bài học có mục đích học cách tránh leak.

### 10.3. SafeDiagnostics.java

Tạo `src/main/java/dev/course/SafeDiagnostics.java`:

```java
package dev.course;

public final class SafeDiagnostics {
    private SafeDiagnostics() {
    }

    public static String summary(
            String repositoryId,
            String username,
            String token) {
        if (repositoryId == null ||
                !repositoryId.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException(
                    "Repository identifier is invalid");
        }

        boolean hasCredentials =
                username != null && !username.isBlank()
                && token != null && !token.isBlank();

        return "Repository=" + repositoryId
                + "; credentialsConfigured=" + hasCredentials;
    }
}
```

Điểm thiết kế:

- Method nhận username/token nhưng **không nối chúng vào string output**, không dùng `toString()` của một credential object.
- Nó chỉ in trạng thái boolean `credentialsConfigured`.
- Repository ID bị giới hạn ký tự để tránh newline/control characters trong output, giảm log-injection đối với ID.
- Thông báo lỗi invalid ID không echo input.
- Đây là **demo log hygiene**, không phải một class authentication client hay thư viện redaction hoàn chỉnh.

Một số tổ chức còn coi việc “có credential” là thông tin nhạy cảm. Khi đó chỉ log trạng thái chung như `Repository connection configured` theo policy hoặc bỏ log hoàn toàn.

### 10.4. App.java

Tạo `src/main/java/dev/course/App.java`:

```java
package dev.course;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(
                SafeDiagnostics.summary(
                        "demo-releases", null, null));
    }
}
```

Stdout chính xác:

```text
Repository=demo-releases; credentialsConfigured=false
```

Không đọc token từ env trong main của ví dụ, nên stdout không phụ thuộc các secrets trên máy của người học.

### 10.5. SafeDiagnosticsTest.java

Tạo `src/test/java/dev/course/SafeDiagnosticsTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SafeDiagnosticsTest {
    @Test
    void doesNotPrintFixtureSecret() {
        String syntheticValue = "FIXTURE_ONLY_NOT_A_REAL_CREDENTIAL";
        String output = SafeDiagnostics.summary(
                "team-releases", "fixture-user", syntheticValue);

        assertEquals(
                "Repository=team-releases; credentialsConfigured=true",
                output);
        assertFalse(output.contains(syntheticValue));
        assertFalse(output.contains("fixture-user"));
    }

    @Test
    void reportsMissingCredentials() {
        assertEquals(
                "Repository=demo-releases; credentialsConfigured=false",
                SafeDiagnostics.summary(
                        "demo-releases", null, null));
    }

    @Test
    void rejectsUnsafeRepositoryId() {
        assertThrows(
                IllegalArgumentException.class,
                () -> SafeDiagnostics.summary(
                        "bad\nid", "fixture-user", "fixture-only"));
    }
}
```

**Có 3 JUnit 5 tests.** Chuỗi `FIXTURE_ONLY_NOT_A_REAL_CREDENTIAL` là test-only fixture không cấp quyền ở bất kỳ hệ thống nào, không phải token thật. Bài test chủ ý **không in syntheticValue ra stdout/stderr**. Không sao chép cách dùng fake fixture thành việc nhúng **mật khẩu thật** trong test source.

**Tính giới hạn của unit test:** test này chỉ chứng minh method `summary` không đưa giá trị fixture vào chuỗi output. Nó **không chứng minh** toàn bộ Maven, CI, third-party plugins hoặc HTTP client của dự án thật không có đường rò rỉ khác.

## 11. Chạy ví dụ và quan sát reports

Từ thư mục `secret-hygiene-lab`:

```bash
mvn -version
mvn -B -ntp clean verify
java -cp target/classes dev.course.App
```

Với JDK 17+/Maven/JUnit plugins được resolve thành công:

- Compiler tạo `target/classes`.
- Surefire chạy 3 tests, không có failure/error.
- Maven tạo ordinary JAR ở `target/secret-hygiene-lab-1.0.0-SNAPSHOT.jar`.
- Ứng dụng in đúng một dòng:

```text
Repository=demo-releases; credentialsConfigured=false
```

Các dấu hiệu trong Maven log:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là **log rút gọn**, không phải toàn bộ output chính xác của một lần chạy cụ thể.

Reports điển hình:

```text
target/surefire-reports/TEST-dev.course.SafeDiagnosticsTest.xml
target/surefire-reports/dev.course.SafeDiagnosticsTest.txt
```

**Kiểm tra an toàn:** đọc report trên máy/runner riêng để chắc chắn không có **credential thật** trước khi publish. Fixture trong bài không có quyền truy cập. Đừng chỉ xem status PASS: một test vẫn có thể PASS nhưng in một secret vào console nếu viết test/production logging sai.

Để chạy một JAR dạng executable cần manifest `Main-Class` hoặc plugin đặc biệt; POM bài không cấu hình chúng. Lệnh chạy đúng là `java -cp target/classes dev.course.App`.

## 12. Tránh đưa secrets vào source/resources và packaged JAR

Một lỗi khác rất thực tế là credentials trong files bị đóng vào artifact:

```text
src/main/resources/
    application.properties
    config.yml
    service-account.json
    credentials.txt
```

Maven Resources Plugin có thể copy resources vào `target/classes`, và JAR Plugin đóng chúng vào JAR. Nếu chúng chứa token thật, **bí mật đã trở thành một phần của artifact**.

Ví dụ cấu hình cần tránh:

```properties
# PHẢN VÍ DỤ; không ghi token thật vào resource
maven.repo.token=DEMO_NOT_A_REAL_SECRET
```

Giải pháp:
- Tách runtime secrets khỏi packaged resources.
- Chỉ đóng các non-sensitive defaults/keys names; lấy secret từ runtime secret store khi chương trình thật sự cần.
- Không cho build plugin resource filtering copy `${env.MAVEN_READ_TOKEN}` vào output.
- Đặt file mẫu ví dụ không bí mật (tên trường, mô tả), không có giá trị cấp quyền.
- Nếu project có Spring Boot hoặc framework khác, hiểu đúng cơ chế externalized configuration của framework đang dùng và kiểm soát nơi package/scanner đọc.
- Kiểm tra **JAR/WAR/ZIP sau build**, không chỉ source folder.
- Cẩn thận `-sources.jar`, site/report/Javadoc và Docker build context, vì chúng có thể chứa những file không nằm trong runtime JAR.

### 12.1. Kiểm tra nội dung artifact mà không làm lộ

Để liệt kê entries:

```bash
jar tf target/secret-hygiene-lab-1.0.0-SNAPSHOT.jar
```

Lệnh này không in file payload, nhưng entry names/paths có thể vẫn mang thông tin nhạy cảm trong project thật. Nếu phát hiện tệp không mong muốn, xem nội dung trong môi trường riêng, **không đăng đầy đủ archive lên ticket công khai**.

Một bài học quan trọng: **file .gitignore chỉ ngăn Git track files chưa được add; nó không ngăn Maven đóng gói các file trong `src/main/resources`**. Phải kiểm soát cả Git và packaging.

## 13. .gitignore và Git history

Một tệp `.gitignore` minh họa:

```gitignore
# Build outputs and local secrets
target/
.env
.env.*
!.env.example
*.local.properties
.local-secrets/
*.log
```

Đây chỉ là phần **phòng ngừa**. Không phải mọi dự án đều nên ignore tất cả `*.log` vì có thể có test fixtures/log examples; cân nhắc cấu trúc repo thực tế.

**Quan trọng:** nếu một file chứa token **đã từng được commit**, thêm vào `.gitignore` không xóa nó khỏi Git history, remote clones, CI caches hoặc mirrors. Hành động đúng khi secret đã lộ được trình bày ở mục incident response.

Không tạo file `.env.example` có password “tạm dùng chung” còn hiệu lực. File example chỉ chứa **tên biến, định dạng và hướng dẫn cấp qua secret store**, không phải dữ liệu truy cập thật.

### 13.1. Kiểm tra trước commit

Checklist review:

- POM không có credentials hoặc userinfo trong URL.
- Không có literal `password`, `accessKey`, `token` kèm giá trị thực.
- Không có private key, certificate signing key hoặc service-account JSON trong resources.
- `.mvn/maven.config` và `.mvn/jvm.config` không mang secrets.
- Git diff không thêm file cấu hình local.
- Secret scanner đã được chạy trên changes/history theo policy.
- Sau build, JAR/ZIP/sources/report không chứa dữ liệu cấp quyền.

**Không rely duy nhất vào tìm keyword `token`**: tên biến hoặc giá trị có thể không chứa những chữ đó, bị encoded, split hoặc được lấy từ plugin khác.

## 14. CI/CD: inject credential vào đúng job, không in ra

Một mẫu GitHub Actions dành cho **release job được cấp quyền** (không chạy cho pull requests):

```yaml
name: Publish Maven release
on:
  push:
    tags:
      - 'v*'

permissions:
  contents: read

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: release
    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up Java and Maven credentials
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
          server-id: team-releases
          server-username-env-var: MAVEN_DEPLOY_USER
          server-password-env-var: MAVEN_RELEASE_TOKEN

      - name: Verify and deploy
        env:
          MAVEN_DEPLOY_USER: ${{ secrets.MAVEN_DEPLOY_USER }}
          MAVEN_RELEASE_TOKEN: ${{ secrets.MAVEN_RELEASE_TOKEN }}
        run: mvn -B -ntp clean deploy
```

**Đây là workflow minh họa, không phải lệnh đã được chạy.** Nó giả định:
1. POM **đã có release version** và `distributionManagement/repository/id = team-releases` với URL hợp lệ.
2. Environment `release` trên GitHub đã được cấu hình đúng approval/protection policy.
3. Repository/environment secrets được cấp an toàn.
4. Runner có version tương thích với Actions đang dùng.
5. Các plugin/signing/quality gates bắt buộc của tổ chức đã có trong Maven lifecycle/CI.

**Hành vi setup-java@v6 quan trọng:** các tham số `server-username-env-var` và `server-password-env-var` là **TÊN biến môi trường**, không phải secret values. Action có thể tạo user settings theo dạng `${env.MAVEN_RELEASE_TOKEN}`; giá trị secret chỉ được inject tại step cần `mvn deploy`.

Không bật release secrets ở job PR của forks/untrusted code. GitHub Actions thường không cấp repository/environment secrets cho fork PRs; **đừng viết workaround để chuyển secret vào PR kiểm tra không đáng tin cậy**. Dùng job `mvn verify` không có publish credentials cho PR.

### 14.1. Masking trên CI chỉ là lưới an toàn

CI systems có thể mask known secrets trong logs, nhưng điều đó **không đảm bảo** nhận ra:

- Token đã bị biến đổi thành Base64 hoặc URL encoding.
- Secret split thành nhiều đoạn.
- Prefix/suffix được in tách dòng.
- Exception/proxy/log downstream ở hệ thống khác.
- File reports đã upload.
- Build tools tự ghi secret vào artifacts/metadata.

GitHub có lệnh `::add-mask::` cho một giá trị phát sinh tại runtime, nhưng phải mask **trước khi có log chứa giá trị**; chính câu lệnh đăng ký masking cũng cần được vận hành an toàn. Tốt hơn là **không in token**, hạn chế debug và chỉ cấp quyền cần thiết.

### 14.2. Quyền tối thiểu và thời hạn

- Token tải dependency: **read-only** ở repository cần thiết.
- Token deploy SNAPSHOT: chỉ ghi snapshot hosted repository.
- Token release: chỉ ghi release/staging repository theo approval.
- Không dùng một account admin toàn bộ repository manager cho mọi CI job.
- Ưu tiên credentials ngắn hạn, workload identity/OIDC khi hệ thống đích hỗ trợ.
- Ràng buộc release secrets vào protected environment; không dùng cho PR tùy ý.
- Không truyền secret cho third-party build plugins hoặc CI actions không tin cậy.
- Ghim/pin tool versions và review build extensions vì code chạy trong CI với quyền của runner có thể đọc env/settings.

**Secret manager không bảo vệ được token sau khi chính bạn đưa nó vào process không tin cậy.** Cần bảo vệ source/CI action/plugin supply chain đồng thời.

## 15. Maven 3.10+/4 repository origin binding

Một rủi ro tinh vi: credential trong `settings.xml/server/id` được Maven Resolver dùng để truy cập repository. Nếu cấu hình repository/mirror bị thay đổi URL sang host do attacker kiểm soát, credentials có thể bị dùng sai đích trong những cấu hình/version cũ.

Maven versions mới bổ sung **repository credential origin binding**:

- Maven 3.10+ có cơ chế ràng buộc server credentials với các origins đã biết/cấu hình.
- Maven 4 mở rộng và thay đổi quy tắc từ Settings Reference; Maven 4 mặc định `maven.repository.credentialScope=origin`, cũng có lựa chọn `strict` hoặc `id`.
- Một server không có origin binding trong chế độ strict có thể bị bỏ qua thay vì được cấp credentials mù.
- Những plugin **tự đọc settings server credentials** ngoài Resolver có thể không được cơ chế origin binding bảo vệ giống dependency download/deploy thông thường.

Đây là **lớp bổ sung**, không thay thế HTTPS/TLS validation, code review POM, repository allowlist, trusted plugin sources, secret rotation và quyền tối thiểu.

Nếu cần chính sách origin cụ thể, dùng **Settings Reference của chính Maven version đang triển khai** và kiểm tra behavior với repository manager staging. Không copy tags cấu hình Maven 4 vào Maven 3.9.x rồi mong được bảo vệ.

## 16. Báo cáo phân tích phụ thuộc, SBOM và chất lượng

Các công cụ tạo report như Maven Dependency Plugin, PMD, Checkstyle, SpotBugs, Surefire, Jacoco, Dependency-Check hoặc SBOM generators có vai trò khác nhau nhưng đều có thể **ghi dữ liệu** ra files/logs.

Không nhất thiết chúng sẽ in token; nguy cơ phụ thuộc configuration và dữ liệu chúng nhận:

- Dependency graph có thể chứa **internal coordinates, private repository URLs, organization identifiers**.
- Effective POM/settings có thể ghi những properties và endpoints nội bộ.
- Exceptions có thể ghi URL có userinfo nếu project cấu hình sai.
- Test reports có thể chứa stdout/stderr và assertion values.
- HTML site docs có thể nhúng metadata/config đã được filtering.
- Scan debug dumps có thể có headers/configuration và nên được lưu riêng.
- SBOM có thể liệt kê dependencies nội bộ, licenses và supply-chain metadata, không tự động là báo cáo công khai.

**Trước khi upload reports** vào GitHub artifacts, Sonar dashboard, security ticket hoặc hệ thống third-party, phải kiểm tra:
1. Nội dung có secrets, credentials, access tokens, private keys hoặc signed URLs không?
2. Có thông tin nội bộ không nên public dù không cấp quyền truy cập không?
3. Retention và access scope phù hợp với policy không?
4. Tools có được cập nhật để không in secret trong error paths không?
5. Nếu phát hiện finding, có thể gửi **đoạn log đã redacted và context đủ** thay vì full dump không?

Một quality gate có thể FAIL mà vẫn tạo artifact chứa sensitive logs. **Báo cáo chẩn đoán cũng là dữ liệu cần phân quyền**.

## 17. Chính sách log an toàn trong Java và build plugins

Quy tắc tốt nhất: **log sự kiện/ID/trạng thái, không log nguyên request, response headers hoặc configuration object có secrets**.

Ví dụ an toàn:

```java
System.out.println(
        "Repository authentication configured: true");
```

Ví dụ không an toàn:

```java
// PHẢN VÍ DỤ:
System.out.println(
        "Authorization: Bearer " + System.getenv("MAVEN_READ_TOKEN"));
```

Kể cả khi logger tự động che một số fields, `toString()` của object chứa secrets hoặc serializing config sang JSON vẫn có thể lộ. Một redaction function có regex đơn giản **không bao quát** biến thể Base64, URL encoding, multiline secret, structured tokens.

**Ưu tiên không lưu vào log ở điểm phát sinh.** Nếu buộc phải redact, dùng API/schema có biết rõ field types, unit tests và log pipeline policy; kiểm tra cả error/exception paths, không chỉ happy path.

### 17.1. Khi một plugin yêu cầu -Dsecret

Một số third-party Maven plugins có interface chỉ chấp nhận `-Dpassword=...` hoặc POM property. Trước khi dùng:
- Kiểm tra plugin docs có hỗ trợ env var **name**, settings server id, credentials provider, secret file path hoặc stdin không.
- Ưu tiên API không để secret xuất hiện trong command arguments.
- Nếu thực sự không có, đánh giá plugin/phiên bản khác hoặc wrapper/service được cấp phép với bảo vệ process/logs chặt.
- Không biến việc “CI masks logs” thành lý do coi `-Dsecret=value` an toàn.
- Báo cáo risk tới owner tool/security để có phương án phù hợp.

Không tự giả định Maven core sẽ che mọi custom property có chữ `password`. Plugin có thể đọc/in chính giá trị đó.

## 18. Debug checklist và incident response khi nghi lộ secret

### 18.1. Kiểm tra trước khi phát hành

- [ ] POM/repository URLs không có userinfo, tokens hoặc passwords.
- [ ] Maven settings nằm ở user/CI secret scope, không trong project source.
- [ ] IDs của Maven servers khớp repositories/mirrors hiệu lực.
- [ ] CI chỉ cấp read/write credentials theo nhiệm vụ cụ thể.
- [ ] Không có secret trong CLI args, shell history, `MAVEN_OPTS` hoặc `.mvn/*`.
- [ ] Không bật `mvn -X`, `showPasswords=true` hoặc debug headers trên public CI.
- [ ] Tests không print env/system properties/config objects chứa secrets.
- [ ] `target/surefire-reports`, site reports, scanner reports không có credential thật.
- [ ] JAR/WAR/sources JAR/Docker context không đóng gói settings/private key.
- [ ] CI artifact upload scopes và retention phù hợp.
- [ ] Secret scanner đã kiểm tra Git diff/history theo policy.
- [ ] Credentials có rotation/expiration và monitoring.

### 18.2. Nếu phát hiện secret trong POM, log hoặc report

Thực hiện theo thứ tự giảm thiểu tác hại, **không chỉ xóa dòng rồi coi xong**:

1. **Ngừng sử dụng token bị nghi lộ, revoke hoặc rotate** bằng cơ chế repository manager/identity provider phù hợp. Nếu chưa thể revoke tức thì vì availability, cần kích hoạt incident process, hạn chế quyền/thời hạn và xác định kế hoạch thay.
2. **Đánh giá phạm vi lộ:** Git commits/tags/history, forks/clones, PR logs, CI artifacts, ticket attachments, scanners, backup/log shipping.
3. **Thu hồi quyền truy cập vào bản đã lộ:** hạn chế/takedown artifacts/logs/reports ở nơi có thể; hiểu rằng người đã tải vẫn có thể giữ bản sao.
4. **Điều tra hoạt động bất thường:** xem server access/audit logs, scopes, IP/time/use patterns; không tự kết luận token không bị sử dụng nếu chưa có chứng cứ.
5. **Sửa nguồn rò rỉ:** chuyển credentials khỏi POM/URL/CLI, ngừng log request/config, cập nhật CI secret injection.
6. **Thực hiện Git history cleanup nếu cần** theo hướng dẫn platform và phối hợp với maintainers; rewrite history có thể ảnh hưởng commits, forks và signed tags.
7. **Kiểm tra lại**: token cũ đã bị vô hiệu, bản mới chỉ được cấp quyền tối thiểu, secrets scanner/report review PASS.
8. **Ghi nhận incident** và cải thiện pre-commit/CI controls để ngăn lặp.

**Xóa token khỏi latest commit không làm token cũ mất khỏi Git history.** Bởi vậy **rotation/revocation là ưu tiên**, kể cả khi sau đó lịch sử được làm sạch.

Không đăng **giá trị secret đã lộ** lên issue để xin hỗ trợ; dùng token ID đã được rút gọn hoặc timestamp/status thông tin an toàn.

### 18.3. Bảng chẩn đoán ngắn

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Maven 401 với private repository | Server ID sai hoặc CI không cấp env | So ID và scope, không in token |
| Maven 403 khi deploy | Token chỉ có quyền read hoặc policy chặn | Điều chỉnh role/pipeline qua admin |
| Local build PASS, CI FAIL 401 | CI không có secrets hoặc khác settings | Xem injection/CI environment |
| PR từ fork thiếu secrets | Hành vi bảo vệ CI đúng | Không cấp secrets cho untrusted PR |
| Password xuất hiện trong POM | Hardcoded property/URL | Revoke, loại khỏi source/history |
| Password xuất hiện ở terminal | `-Dtoken=...` hoặc shell `set -x` | Dừng debug, rotate và sửa cách truyền |
| Token xuất hiện trong test XML | Tests/logs/assertions/system properties | Loại khỏi forked test context, xử lý reports |
| Help Plugin in password | `showPasswords=true` hoặc tooling sai | Bỏ option, kiểm soát output, rotate nếu lộ |
| `-q` nhưng vẫn có leak | Plugin in stdout/error độc lập | Sửa logging ở nguồn |
| Scanner report chứa private URLs | Nội dung metadata hoặc debug enabled | Phân quyền/giảm dữ liệu trước upload |
| JAR có file credentials | Resource packaging sai | Bỏ file, revoke, rebuild/publish version mới |
| Token xuất hiện trong Git history | Secret đã commit | Rotate trước, xử lý history theo policy |
| CI mask `***` nhưng output khác vẫn lộ | Encoded/transformed secret | Không reliance vào mask, giảm logging |
| Maven 3 encrypted password bị copy | Mã hóa không phải vault | Giữ file/master an toàn, rotate khi cần |
| Downloader gửi credential sai host | Repo URL/mirror/origin policy | Kiểm tra effective origins, nâng Maven |
| Lệnh deploy không tìm được auth | `server/id` khác distributionManagement ID | Đồng bộ ID, không đưa token vào URL |

## 19. Bài tập thực hành

1. Giải thích vì sao token trong `pom.xml` nguy hiểm dù repository Git là private.
2. Phân biệt `<repositories>`, `<distributionManagement>` và `settings.xml/servers`.
3. Chỉ ra cách khớp `team-private-read`, `team-releases` và `team-snapshots` với server IDs.
4. Giải thích cú pháp `${env.MAVEN_READ_TOKEN}` và vì sao không hardcode token.
5. Vì sao dùng `-Dpassword=...` trên CLI không an toàn?
6. Vì sao shell history và process listing có thể trở thành nguồn rò rỉ?
7. So sánh tác dụng `-B`, `-ntp`, `-q`, `-e` và `-X` đối với log security.
8. Vì sao `help:effective-settings` mặc định che passwords nhưng output vẫn cần review?
9. Điều gì xảy ra nếu chạy `help:effective-settings` với `showPasswords=true` trên CI public?
10. Vì sao Maven 3 password encryption không thay thế secret manager?
11. Maven 4 cung cấp cải tiến nào so với Maven 3 trong mã hóa secrets?
12. Khi nào một test report có thể chứa token dù unit test FAIL hay PASS?
13. Vì sao gửi Maven token xuống `systemPropertyVariables` của Surefire là rủi ro?
14. Tạo dự án Java 17 đầy đủ của bài, chạy `mvn -B -ntp clean verify`.
15. Xác nhận có 3 tests và stdout chính xác `Repository=demo-releases; credentialsConfigured=false`.
16. Vì sao method `SafeDiagnostics.summary` không phản hồi nguyên token?
17. Ý nghĩa của test `doesNotPrintFixtureSecret` là gì, và giới hạn của nó?
18. Lệnh `jar tf` có ích gì khi kiểm tra secrets bị package vào archive?
19. Vì sao `.gitignore` không xóa secret đã commit trong quá khứ?
20. Một GitHub Actions workflow dùng `setup-java` lấy env var **name** khác gì truyền secret value?
21. Vì sao không cấp release token cho pull request từ fork?
22. Những biến đổi như Base64/URL-encoding làm masking kém tin cậy ra sao?
23. Credential origin binding trong Maven 3.10+/4 giúp giảm rủi ro gì?
24. Nếu CI log đã lộ token, việc đầu tiên là xóa log hay rotate/revoke token?
25. Xây một checklist chỉ cho phép public một Surefire/HTML report sau khi kiểm tra secrets.
26. Giải thích tại sao token có read-only scope vẫn cần bảo vệ.
27. Với 401/403, cách debug nào giữ token bí mật mà vẫn đủ thông tin cho quản trị?
28. Một plugin bên thứ ba log nguyên config object có thể làm lộ những gì?
29. Vì sao một masked log không bảo đảm server access log và uploaded reports đều sạch?
30. Nếu token được commit từ nhiều tháng trước, phải xử lý Git history và forks thế nào?

## 20. Tổng kết

Để tránh lộ token hoặc mật khẩu qua Maven **POM, log và báo cáo**, cần bảo vệ toàn bộ đường đi của credential:

- **POM:** chỉ lưu IDs, URLs và build metadata không nhạy cảm. Không lưu passwords, tokens, URL userinfo hoặc `-Dsecret` trong file commit.
- **Authentication:** dùng user/CI `settings.xml/servers`, khớp `id` với repository/mirror, cấp giá trị thật từ secrets manager/env interpolation ở môi trường được tin cậy.
- **Logs:** hạn chế `-X`/`-e`, không in env/request headers, không truyền token qua process args. `-q` và CI masking không phải biện pháp bảo vệ đủ.
- **Reports/artifacts:** xem Surefire XML/text, scanner/site outputs, resources và archive attachments như dữ liệu cần rà soát và phân quyền.
- **CI policy:** cấp credential tối thiểu, ngắn hạn, theo step/environment; không cấp release token cho untrusted PR.
- **Nếu đã lộ:** ưu tiên revoke/rotate rồi điều tra phạm vi, xử lý Git history/logs/artifacts và sửa nguồn leak.

Ví dụ Java 17 của bài có **3 JUnit tests**, một hàm diagnostic chỉ in thông tin không nhạy cảm và stdout chính xác:

```text
Repository=demo-releases; credentialsConfigured=false
```

**Nguyên tắc quan trọng nhất:** **secret an toàn nhất trong log hoặc báo cáo là secret không bao giờ được đưa vào đó.**

## 21. Tài liệu tham khảo

- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Guide to Password Encryption (Maven 3)](https://maven.apache.org/guides/mini/guide-encryption.html)
- [Apache Maven — Password Encryption (Maven 4)](https://maven.apache.org/guides/mini/guide-encryption-4.html)
- [Apache Maven Help Plugin — help:effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Apache Maven Help Plugin — help:effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Surefire Plugin — Reports](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Apache Maven Surefire Plugin — Using System Properties](https://maven.apache.org/surefire/maven-surefire-plugin/examples/system-properties.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [GitHub Actions — Using Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
- [GitHub Actions — Secure Use Reference](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub — actions/setup-java (publishing Maven packages)](https://github.com/actions/setup-java)
