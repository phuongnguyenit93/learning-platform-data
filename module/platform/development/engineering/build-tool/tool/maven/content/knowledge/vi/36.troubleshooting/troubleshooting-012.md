# Khác biệt giữa máy cá nhân, IDE và CI do Maven settings hoặc profile

## 1. Cùng một Git commit nhưng ba kết quả build khác nhau

Trong nhóm **Chẩn đoán lỗi**, một hiện tượng khó chịu là:

- Ở terminal máy cá nhân, chạy `mvn clean verify` được **BUILD SUCCESS**.
- Trong IntelliJ IDEA/Eclipse, Maven import hoặc test báo lỗi dù source code không đổi.
- Trên CI, chạy cùng lệnh nhìn bề ngoài nhưng bị `401 Unauthorized`, `Could not resolve artifact`, không tìm thấy plugin, không dùng đúng Java version hoặc chỉ một profile bị kích hoạt khiến test thất bại.

**Nguyên nhân thường không nằm ở một dòng Java duy nhất.** Maven tạo **effective build** từ nhiều nguồn: POM parent/child, global/user settings, profiles active, command-line user properties, Maven/JDK versions, environment variables, dependency repositories và cache. IDE còn có lựa chọn Maven distribution, settings file, importer JDK và test runner riêng. CI có thể dùng settings được tạo động và không có secrets như máy developer.

Cần phân biệt:

> **Cùng source code + cùng câu lệnh hiển thị** chưa chắc là **cùng effective settings, active profiles, effective POM, JDK, dependency cache và goal execution**.

Mục tiêu bài này là dùng **bằng chứng so sánh được** thay vì đoán hoặc xóa toàn bộ cache.

### Sau bài học bạn có thể

1. Giải thích khác biệt giữa `pom.xml`, global `settings.xml`, user `settings.xml` và profiles.
2. Xác định profile nào được kích hoạt từ POM, settings, CLI, JDK, OS hoặc property.
3. Phân biệt `-s`, `-gs`, `-P`, `-D`, `-f`, local repository và mirror.
4. Dùng Maven Help Plugin để xem **active profiles, effective settings, effective POM** một cách an toàn.
5. So sánh terminal, IDE và CI về Maven distribution/JDK/settings/runner.
6. Chạy dự án Java 17 có hai chế độ `dev` và `ci` thông qua filtered resource và JUnit 5.
7. Xử lý các lỗi điển hình: 401/403, cache SNAPSHOT stale, thiếu plugins, profile vô tình active, offline mode, sai JDK.
8. Thiết kế CI dùng **profile tường minh** và có báo cáo chẩn đoán không làm lộ credentials.

Bài dùng **Maven 3.9.x**, **Java 17**, JUnit Jupiter **5.11.4** và Maven Help Plugin **3.5.2** để minh họa. Những phiên bản được ghim nhằm minh bạch, không khẳng định đây là bộ version mới nhất trong mọi hệ thống.

## 2. Bản đồ cấu hình Maven: dữ liệu đến từ đâu?

```text
                      project source
                           |
          parent POM ---> pom.xml <--- child/module POM
                           |
                      POM profiles
                           |
     global settings.xml --+-- user settings.xml
      Maven installation        ~/.m2/
                           |
                     activeProfiles
       -P cli, implicit JDK/OS/property/file activation
                           |
        CLI user properties -D... / .mvn/maven.config
                           |
        Maven model building and plugin execution
                           |
                    EFFECTIVE BUILD
          (active profiles + effective POM/settings)
                           |
    JDK, Maven version, remote mirrors, local repository
                           |
            compile / test / package / verify
                           |
               artifact / reports / exit code
```

Đây là **sơ đồ khái niệm**, không phải thứ tự precedence tuyệt đối cho mọi field. Ví dụ mirror selection, plugin resolution, POM properties và JVM system properties có những quy tắc khác nhau; cần kiểm chứng bằng các công cụ Help Plugin và Maven logs.

### 2.1. pom.xml giữ những gì?

`pom.xml` là **project model**, thường chứa:

- `groupId/artifactId/version/packaging`.
- `dependencies` và `dependencyManagement`.
- `build/plugins` và `pluginManagement`.
- Profiles liên quan đến **cách build project** (compiler, resources, tests, packaging).
- `repositories` và `pluginRepositories` khi có lý do được phép.
- `distributionManagement` dành cho đích upload/publish.

POM thông thường được commit vào Git. Không đặt token thật, mật khẩu, user-specific absolute paths hoặc cấu hình máy cá nhân vào đây.

### 2.2. global settings.xml

Với Maven 3.x, vị trí thông thường:

```text
${maven.home}/conf/settings.xml
```

Đây là settings đi kèm **bản cài đặt Maven**. Nếu IDE dùng một Maven bundled khác hoặc CI cài Maven ở đường dẫn khác, global settings có thể khác.

### 2.3. user settings.xml

Vị trí thông thường:

```text
${user.home}/.m2/settings.xml
```

Đây là settings theo **tài khoản OS chạy Maven**, có thể chứa proxies, mirror, localRepository, repositories/profiles và server credentials.

Khi có cả global và user settings, Maven **merge** chúng; cấu hình **user-specific có ưu thế** trước global ở những phần trùng phù hợp. Một CI runner dùng home directory khác sẽ không tự có file settings của developer.

### 2.4. IDE không phải một lớp settings chuẩn mới của Maven core

IDE có thể cấu hình:
- Maven distribution: bundled, external hoặc Maven Wrapper.
- User settings file được chọn và local repository path.
- Maven importer JDK và runner JDK.
- Profiles được bật trong Maven tool window.
- Runner là **IDE-native JUnit** hay Maven Surefire/Failsafe.
- Workspace environment variables và JDK/OS.

Những lựa chọn này **thay đổi cách Maven được gọi và môi trường của Maven**, chứ không thêm một định dạng POM riêng do Maven core định nghĩa.

### 2.5. CI settings là gì?

CI thường:
1. Checkout cùng source từ Git.
2. Setup JDK/Maven ở runner.
3. Tạo/cấp **user settings.xml riêng** (có mirrors, servers, credentials, repositories).
4. Chạy một tập profiles, `-D` properties và goals.
5. Dùng local cache tạm hoặc cache phục hồi.
6. Upload logs/reports.

Vì vậy CI **không tự giống máy developer**, kể cả khi YAML chỉ có dòng `mvn clean verify`.

## 3. Những loại cấu hình thường gây chênh lệch

| Hạng mục | Máy cá nhân | IDE | CI | Triệu chứng |
| --- | --- | --- | --- | --- |
| Maven version | Maven đã cài global | Bundled/external/wrapper | Setup action/container | Plugin behavior khác |
| JDK chạy Maven | `JAVA_HOME` shell | Importer/runner JDK | Setup-java/container | `release version 17 not supported` |
| Global settings | Maven installation A | Maven installation B | Maven installation C | Mirror/proxy khác |
| User settings | `~/.m2/settings.xml` | IDE custom path | CI-generated settings | 401 hoặc repo không tìm thấy |
| Active profiles | Auto hoặc `-Pdev` | Tick trong tool window | `-Pci`/settings | Resource/test behavior khác |
| CLI properties | `-D...` thủ công | Run configuration | YAML/env flags | Tham số test khác |
| Local repository | Cache lâu ngày | Cache IDE khai báo | Cache rỗng/tạm | Missing/stale SNAPSHOT |
| Repositories/mirrors | VPN/private repo | Mirror khác | Proxy/firewall/allowlist | 403, 404, timeout |
| Offline mode | `-o` hoặc settings | Offline checkbox | Runner không có Internet | Không resolve plugin |
| Goals | `test` | IDE native JUnit | `verify` | Failsafe/quality gate khác |
| Locale/timezone | Máy dev | IDE JVM | Runner UTC | Tests phụ thuộc clock |
| File path/case | Windows/macOS | IDE workspace | Linux runner | Resource not found |
| Environment variables | Shell profile | IDE launch env | CI secrets | Activation khác |

**Nên kiểm tra theo thứ tự:** Maven/JDK và settings → active profiles/effective POM → repositories/cache → goals/tests → plugin cụ thể. Đừng bắt đầu bằng việc xóa cache hoặc nâng tất cả plugins khi chưa có bằng chứng.

## 4. settings.xml: những phần có ảnh hưởng lớn nhất

Trong Maven 3.x, settings thường có:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <localRepository>...</localRepository>
    <offline>false</offline>
    <servers>...</servers>
    <mirrors>...</mirrors>
    <proxies>...</proxies>
    <profiles>...</profiles>
    <activeProfiles>...</activeProfiles>
</settings>
```

Đây chỉ là **cấu trúc minh họa**, không phải một file có thể dùng nguyên văn vì dấu `...` không phải giá trị thật.

### 4.1. localRepository

Giá trị mặc định thường là:

```text
${user.home}/.m2/repository
```

Một máy đã có dependency SNAPSHOT/parent/plugin cached có thể build thành công, trong khi CI cache sạch phải tải từ remote và gặp 401 hoặc lỗi artifact missing.

Thay local repository chỉ đổi **nơi Maven lưu và lấy cache**, không sửa lỗi repository URL/server ID hoặc artifact version sai. Có thể chỉ định tạm bằng:

```bash
mvn -B -ntp -Dmaven.repo.local=/path/to/isolated-repo clean verify
```

Thay `/path/to/isolated-repo` bằng thư mục hợp lệ cho OS. Lệnh này tạo/populate cache mới, có thể tải nhiều dependencies và mất thời gian; chỉ dùng khi cần cô lập nguyên nhân, không xóa cache chính.

### 4.2. mirrors

Ví dụ cấu hình **khái niệm**:

```xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>central</mirrorOf>
        <url>https://repo.example.invalid/maven-proxy/</url>
    </mirror>
</mirrors>
```

- Mirror có thể **thay đổi nơi Maven lấy dependencies và plugins**.
- `mirrorOf=central` áp dụng cho Maven Central theo ID, không phải tất cả endpoints.
- `mirrorOf=*` có thể điều hướng nhiều remote repositories qua cùng một manager.
- Repository `id` để tìm download endpoint và effective mirror ID có thể khác nhau.
- Một mirror hỏng, thiếu quyền hoặc chỉ cache một phần artifacts có thể gây lỗi ở CI/IDE.

**Không dùng domain trong ví dụ để tải artifact:** `example.invalid` là domain vô hiệu được chọn cố ý. POM lab runnable ở phần sau **không yêu cầu mirror này**.

Mirror của Maven Resolver **không mặc nhiên thay thế** đích `distributionManagement` mà Maven Deploy Plugin dùng để publish.

### 4.3. servers và credentials

`servers/server/id` cần khớp repository/mirror ID mà Maven resolver hoặc deploy plugin sử dụng. Dùng credentials ngoài Git:

```xml
<!-- ĐOẠN MINH HỌA: đặt trong user/CI settings, không commit -->
<servers>
    <server>
        <id>company-mirror</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_TOKEN}</password>
    </server>
</servers>
```

Khi developer có token nhưng CI không được cấp:
- Local build PASS nhờ auth.
- CI báo **401** hoặc **403**.
- Sửa bằng đúng credential injection, scope, expiry, server ID.
- **Không nhúng token vào `pom.xml` hoặc `-Dpassword=...` để workaround**.

### 4.4. proxies, offline và plugin repositories

- `<proxies>` ảnh hưởng kết nối Maven tới remote servers trong môi trường đi qua proxy.
- `<offline>true</offline>` hoặc Maven `-o` cấm truy cập network; artifacts chưa cached sẽ không resolve.
- `repositories` cho dependencies và `pluginRepositories` cho Maven plugins có vai trò khác nhau; khai báo dependency repo đúng chưa chắc đủ cho một plugin từ private plugin repo.
- IDE có thể bật **Work offline** dù terminal không có `-o`.
- CI corporate network có thể yêu cầu custom CA truststore/TLS settings; không “sửa” lỗi chứng chỉ bằng cách tắt xác minh TLS.

### 4.5. settings profile không giống POM profile

Một profile trong `settings.xml` chỉ có những phần thích hợp ở phạm vi môi trường:
- `activation`
- `properties`
- `repositories`
- `pluginRepositories`

Không đặt tùy tiện `<build><plugins>` hoặc `<dependencies>` vào settings profile như ở POM; chúng không thuộc mô hình settings profile.

**Chốt:** Đặt **build logic portable** vào POM; đặt **network/auth/local machine policy** vào settings. Một settings profile vẫn có thể cung cấp properties được POM sử dụng, vì thế nó **có thể làm kết quả build khác nhau**.

## 5. Maven profiles: activation là nguồn lệch lớn nhất

Profile là một bộ thay đổi có điều kiện lên effective build. Profiles có thể khai báo:
- Trong `pom.xml` của project (per project).
- Trong global/user `settings.xml`.
- Một số phiên bản Maven cũ từng có cơ chế ngoài POM; không xem đó là hướng dẫn chuẩn mới.

### 5.1. Active bằng -P

```bash
mvn -B -ntp -Pci clean verify
mvn -B -ntp -Pdev clean verify
```

`-P` bật profile theo ID. Nhiều profile có thể được chỉ định bằng dấu phẩy:

```bash
mvn -B -ntp -Pci,quality clean verify
```

Nếu `quality` không có trên project/settings, tính nghiêm ngặt khác giữa Maven versions. Maven 4 có cách đánh dấu optional profile bằng prefix `?`; không dùng một profile ID không tồn tại rồi mặc định Maven sẽ chạy đủ quality gates.

### 5.2. Active-by-default

```xml
<profile>
    <id>dev</id>
    <activation>
        <activeByDefault>true</activeByDefault>
    </activation>
    <properties>
        <lab.mode>dev</lab.mode>
    </properties>
</profile>
```

Ở POM này, `dev` có thể active mặc định. **Khi một profile khác trong cùng POM được kích hoạt**, ví dụ `ci`, các active-by-default profiles trong POM đó được **tắt tự động**.

Đây là nguyên nhân:
- Terminal không truyền `-P` → `dev` active.
- CI truyền `-Pci` → `dev` inactive, `ci` active.
- Resource filtering/test behavior khác dù cùng source.

### 5.3. Active bằng settings.xml

```xml
<activeProfiles>
    <activeProfile>ci</activeProfile>
</activeProfiles>
```

Trong user settings, danh sách này bật profile theo ID cho Maven session. Một profile `ci` có thể được định nghĩa trong POM; khi settings kích hoạt nó, ngay cả lệnh terminal **không có `-Pci`** vẫn có thể dùng `ci`.

Vì thế **chỉ nhìn dòng command là chưa đủ**; phải xem effective settings và active-profiles.

Nếu settings có profile cùng ID với POM và cùng hoạt động, profile settings có thể ưu tiên ở các trường thích hợp. **Tránh đặt cùng ID cho hai nội dung cấu hình khác ngữ nghĩa** và xác nhận effective model thay vì dựa vào trực giác.

### 5.4. Implicit activation

Maven có thể tự bật profile dựa vào:
- JDK version chạy Maven.
- OS family/name/arch/version.
- JVM/system/CLI property, ví dụ `-Denv=ci`.
- Sự tồn tại hoặc không tồn tại của file.
- Các điều kiện được Maven version hỗ trợ khác.

Ví dụ POM profile dựa vào property:

```xml
<profile>
    <id>ci-by-property</id>
    <activation>
        <property>
            <name>build.environment</name>
            <value>ci</value>
        </property>
    </activation>
    <properties>
        <lab.mode>ci</lab.mode>
    </properties>
</profile>
```

Khi chạy:

```bash
mvn -Dbuild.environment=ci verify
```

profile có thể active. Nếu CI quên user property hoặc IDE không truyền nó, profile không active. Vì thế, với môi trường phát hành, **explicit `-Pci` thường dễ audit hơn activation quá phụ thuộc máy**.

### 5.5. JDK, OS và file activation: thận trọng khi chuyển máy

Một profile có:

```xml
<activation>
    <jdk>[17,18)</jdk>
</activation>
```

có thể active khi Maven chạy trên JDK 17 nhưng không active với JDK 21, dù `maven.compiler.release=17`.

Một profile theo OS Windows có thể active ở máy developer nhưng không active trong Linux CI. Một profile theo `<file><exists>...` có thể active do file local còn sót nhưng CI checkout mới không có.

**Không hardcode absolute user paths vào profile activation trong POM** nếu mục tiêu là build portable. Nếu phải có file theo môi trường, log giá trị không nhạy cảm/activation evidence và lập test cho cả hai trường hợp.

### 5.6. Profile effects và inheritance

Một POM profile không phải một object profile được kế thừa nguyên vẹn ở child như một block cấu hình. **Các tác động của profile đã active** (plugins, properties...) có thể được kế thừa khi Maven xây effective model. Trong multi-module, profile có thể active khác nhau tùy POM scope và activation context.

Đừng suy đoán rằng `-Pci` chắc chắn kích hoạt cùng một profile block ở mọi module khi chỉ một vài POM khai báo ID đó. Hãy dùng `help:active-profiles` và `help:effective-pom` cho modules cần thiết.

## 6. Thứ tự ưu tiên: cần biết nhưng không thần thánh hóa

Những nguyên tắc đáng tin:
- User settings được merge với global settings, user-specific values thường có ưu thế.
- POM parent/child, active profiles và plugin configurations được model builder kết hợp thành effective POM.
- CLI `-P` bật profile tường minh; `-D` truyền user properties có ảnh hưởng đến activation và interpolation.
- Các profiles active có thể ghi đè cùng property. Nếu nhiều profiles trùng key, quy tắc merge/order phụ thuộc vị trí profile; **xem effective output** thay vì đoán.
- CLI `-s` thay user settings đang dùng; `-gs` thay global settings.
- CLI `-Dmaven.repo.local=...` có thể chọn local cache path khác.
- Environment variables chỉ có ý nghĩa khi được Maven, settings/POM hoặc plugin đọc; chúng không tự biến mọi profile thành active.

**Không đưa ra một bảng precedence duy nhất và áp dụng cho tất cả settings, POM, repositories, profiles, properties và toolchains.** Chúng có model merge/activation riêng. Dùng công cụ introspection.

## 7. Bộ lệnh chẩn đoán đầu tiên — không cần sửa source

Từ đúng project root, ở **mỗi môi trường**:

```bash
mvn -version
java -version
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-settings
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

**Ý nghĩa:**
1. `mvn -version`: Maven distribution, Java version dùng để chạy Maven, Maven home, OS.
2. `java -version`: Java mà shell tìm thấy; có thể khác Java mà Maven thực sự dùng. Nếu khác, kiểm tra `JAVA_HOME` và PATH.
3. `help:active-profiles`: chính xác profile nào đang active cho build/session.
4. `help:effective-settings`: settings đã merge từ global/user, repositories/servers/mirrors/proxy/profile info.
5. `help:effective-pom`: effective project model sau parent inheritance và active profiles.

Trong thực tế, giúp giảm noise bằng Help Plugin `-Doutput=...` hoặc filter an toàn; **không tự động gửi nguyên effective settings/POM lên chat, issue hoặc CI artifact**.

### 7.1. Quan sát một property cụ thể

```bash
mvn -q org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=lab.mode -DforceStdout
```

Nếu project lab của bài được cấu hình đúng, ở mặc định nó có giá trị `dev`, khi thêm `-Pci` sẽ là `ci`. Lệnh có thể có format/log khác nhau theo plugin invocation; kiểm tra output thực tế.

### 7.2. So sánh với CI bằng dữ liệu không nhạy cảm

Một mẫu báo cáo có thể chứa:

```text
Commit: <Git SHA>
Maven: 3.9.x
JDK used by Maven: 17.x
Starting POM: ./pom.xml
User settings source: CI-generated (path, not content)
Active profiles: ci
Goals: clean verify
Selected modules: all
Local repository: ephemeral cache
Repository mirror: company mirror (ID only)
Surefire tests: N executed, F failures
Build result: FAILURE or SUCCESS
```

Giá trị `<Git SHA>` và số N/F là **trường thay thế trong format báo cáo**, không phải log literal. **Không ghi token, password hoặc headers** vào báo cáo để “đủ chi tiết”.

### 7.3. Help Plugin cũng có rủi ro chia sẻ

`help:effective-settings` ẩn passwords theo mặc định (Maven Help Plugin bản đang xét), nhưng có option `showPasswords=true`. **Không bật tùy chọn đó khi chuẩn bị chia sẻ log**.

Effective POM có thể chứa properties, URL hoặc cấu hình nhạy cảm nếu project đã đưa secret sai chỗ. Maven `-X` debug có thể in thêm config/system properties. Đọc trong runner/terminal tin cậy; **redact từ nguồn**, không dựa hoàn toàn vào CI mask.

## 8. Bài thực hành: Maven Java 17 với profile dev và ci

Lab này không cần truy cập private repository, không chứa token thật và cho thấy **cùng source nhưng profile khác sẽ tạo resource khác**. Sau đó dùng settings để kích hoạt profile và xem kết quả.

### 8.1. Cây thư mục

```text
profile-diagnostics-lab/
├── pom.xml
├── lab-settings.xml             (tệp settings KHÔNG chứa secret)
├── ci-settings.xml              (tệp settings KHÔNG chứa secret)
└── src/
    ├── main/
    │   ├── java/dev/course/
    │   │   ├── EnvironmentReport.java
    │   │   └── App.java
    │   └── resources/build-info.properties
    └── test/java/dev/course/
        └── EnvironmentReportTest.java
```

Yêu cầu: Maven 3.9.x, JDK 17+, terminal và network để tải Maven plugins/JUnit lần đầu nếu local repository chưa cached.

### 8.2. pom.xml hoàn chỉnh

Tạo `profile-diagnostics-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.course</groupId>
    <artifactId>profile-diagnostics-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <lab.mode>base</lab.mode>
        <lab.label>Maven profile lab</lab.label>
    </properties>

    <profiles>
        <profile>
            <id>dev</id>
            <activation>
                <activeByDefault>true</activeByDefault>
            </activation>
            <properties>
                <lab.mode>dev</lab.mode>
            </properties>
        </profile>
        <profile>
            <id>ci</id>
            <properties>
                <lab.mode>ci</lab.mode>
            </properties>
        </profile>
    </profiles>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
                <includes>
                    <include>build-info.properties</include>
                </includes>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
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
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <expected.mode>${lab.mode}</expected.mode>
                    </systemPropertyVariables>
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

**Giải thích POM:**
- Giá trị base `lab.mode=base` là fallback nếu không có profile nào active.
- Profile `dev` có `activeByDefault=true` nên mặc định dùng `lab.mode=dev`.
- Profile `ci` chỉ active khi được chọn qua `-Pci` hoặc cơ chế activation phù hợp.
- Khi `ci` active trong cùng POM, `dev` active-by-default tắt; `lab.mode=ci`.
- Resources Plugin thay `${lab.mode}` trong một file resources. Không bật filtering cho tất cả binary resources vì có thể làm hỏng nội dung.
- Surefire truyền `expected.mode` tới test JVM với giá trị Maven đã resolve; test so property này với filtered resource thật.
- Cùng một test suite chạy ở hai profiles. Bài không đặt logic đặc biệt vào Java để “đoán CI” qua environment variable.
- Project không deploy artifact và không cần credentials.

### 8.3. build-info.properties

Tạo `src/main/resources/build-info.properties`:

```properties
lab.mode=${lab.mode}
lab.label=${lab.label}
```

Hai placeholder được Resources Plugin thay trong phase `process-resources`. File nằm trong `target/classes/build-info.properties` và sau `package` sẽ được đưa vào JAR.

**Không dùng token/password trong resource filtering.** Nếu thay một property bằng secret môi trường, nội dung đó có thể bị đóng vào artifact và lộ qua JAR.

### 8.4. EnvironmentReport.java

Tạo `src/main/java/dev/course/EnvironmentReport.java`:

```java
package dev.course;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Properties;

public final class EnvironmentReport {
    private EnvironmentReport() {
    }

    private static Properties read() {
        Properties properties = new Properties();

        try (InputStream input = EnvironmentReport.class
                .getClassLoader()
                .getResourceAsStream("build-info.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing build-info.properties");
            }

            properties.load(input);
            return properties;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    public static String mode() {
        return read().getProperty("lab.mode");
    }

    public static String label() {
        return read().getProperty("lab.label");
    }

    public static String summary() {
        return "MODE=" + mode() + "; LABEL=" + label();
    }
}
```

Method đọc **resource được Maven filter trong quá trình build**; Java application không tự đọc `pom.xml`, `settings.xml` hoặc CLI profile. Nếu profile làm build resource khác, output Java cũng khác.

### 8.5. App.java

Tạo `src/main/java/dev/course/App.java`:

```java
package dev.course;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(EnvironmentReport.summary());
    }
}
```

Ở profile mặc định `dev`, stdout dự kiến chính xác:

```text
MODE=dev; LABEL=Maven profile lab
```

Ở `-Pci`, stdout dự kiến chính xác:

```text
MODE=ci; LABEL=Maven profile lab
```

### 8.6. EnvironmentReportTest.java — 3 JUnit 5 tests

Tạo `src/test/java/dev/course/EnvironmentReportTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class EnvironmentReportTest {
    @Test
    void filteredModeMatchesEffectiveModel() {
        String expected = System.getProperty("expected.mode");
        assertNotNull(expected, "Surefire expected.mode missing");
        assertEquals(expected, EnvironmentReport.mode());
    }

    @Test
    void labelIsStableAcrossProfiles() {
        assertEquals("Maven profile lab", EnvironmentReport.label());
    }

    @Test
    void interpolationWasCompleted() {
        assertFalse(
                EnvironmentReport.mode().contains("${"),
                "Resources filtering did not resolve lab.mode");
    }
}
```

**Có 3 tests**:
1. Property Maven active profile và filtered resource phải cùng một giá trị.
2. Label không đổi giữa hai profile.
3. Resource không còn placeholder chưa được Maven interpolate.

**Giới hạn quan trọng:** test so hai representations trong cùng build; nó **không chứng minh profile mà người vận hành định chọn là profile đã được chọn**. Nếu IDE/CI cùng vô tình dùng `dev` và test expected value cũng thành `dev`, test vẫn PASS! Cần kiểm tra active profiles/effective model và policy chọn profile tường minh.

### 8.7. lab-settings.xml: settings profile không đụng bí mật

Tạo `profile-diagnostics-lab/lab-settings.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <profiles>
        <profile>
            <id>lab-settings</id>
            <properties>
                <lab.settings.marker>loaded</lab.settings.marker>
            </properties>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>lab-settings</activeProfile>
    </activeProfiles>
</settings>
```

File này **không chứa password, token, URL mirror hoặc private repository** nên phù hợp cho bài học. Nó được dùng để chứng minh một profile từ user settings có thể active mà không cần `-P`. Profile này chỉ đặt marker và **không sửa `lab.mode`** để không gây nhập nhằng với ví dụ dev/ci.

Đây là **alternative user settings**; dùng `-s` có thể thay thế user settings thường dùng. Global settings vẫn có thể được merge, tùy Maven invocation và configuration.

### 8.8. ci-settings.xml: tự kích hoạt POM profile từ settings

Tạo `profile-diagnostics-lab/ci-settings.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <activeProfiles>
        <activeProfile>ci</activeProfile>
    </activeProfiles>
</settings>
```

Không cần khai báo profile `ci` lần thứ hai trong settings; **POM đã có profile tên `ci`**. Theo cơ chế activeProfiles, settings có thể bật profile cùng ID trong project, làm lệnh không có `-Pci` vẫn dùng mode CI.

Đây là demo về **rủi ro cấu hình ẩn**: người đọc command `mvn clean verify` có thể tưởng chỉ chạy profile mặc định, nhưng settings đã chọn `ci`.

**Không tự động commit một CI settings chứa credentials** vào Git. Hai file trong lab đều hoàn toàn không nhạy cảm; sản phẩm thật nên tạo user/CI settings từ secret store khi có authentication.

## 9. Chạy các tình huống để quan sát khác biệt

Tất cả command dưới đây chạy từ root `profile-diagnostics-lab`. Mỗi lần thay profile cần dùng `clean verify` để tránh resource còn lại từ lần trước.

### 9.1. Không chỉ rõ profile

```bash
mvn -B -ntp clean verify
java -cp target/classes dev.course.App
```

Trong môi trường **không có user/global settings nào tự kích hoạt `ci` hoặc ghi đè `lab.mode`**, dự kiến:
- Profile `dev` active-by-default.
- Surefire chạy 3 tests, 0 failures.
- Java stdout:

```text
MODE=dev; LABEL=Maven profile lab
```

**Điều kiện cần ghi rõ:** nếu user settings hiện tại đã bật profile `ci`, kết quả có thể khác. Để chạy một baseline thật sự được kiểm soát, có thể dùng `-s lab-settings.xml` với settings file của bài và kiểm tra global settings; lab-settings không tác động `lab.mode`.

### 9.2. Chọn CI profile tường minh

```bash
mvn -B -ntp -Pci clean verify
java -cp target/classes dev.course.App
```

Dự kiến 3 tests PASS và stdout:

```text
MODE=ci; LABEL=Maven profile lab
```

Cùng code Java và POM nhưng resource `target/classes/build-info.properties` đã được filter với giá trị khác; có thể xem file đó và so với source template.

### 9.3. Dùng alternative settings profile

```bash
mvn -B -ntp -s lab-settings.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -B -ntp -s lab-settings.xml clean verify
java -cp target/classes dev.course.App
```

Profile settings `lab-settings` active, nhưng nó không thay `lab.mode`. Khi không có global/settings khác can thiệp, POM dev vẫn mặc định → stdout dev.

**Bài học:** một profile active không nhất thiết đổi app behavior. Cần xem **profile đóng góp field nào**; đừng đổ mọi khác biệt cho tên profile mà không kiểm tra effective values.

### 9.4. Settings tự bật POM CI profile

```bash
mvn -B -ntp -s ci-settings.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -B -ntp -s ci-settings.xml clean verify
java -cp target/classes dev.course.App
```

Với POM lab và settings file đã tạo, dự kiến:

```text
MODE=ci; LABEL=Maven profile lab
```

Maven command build **không có -Pci**, nhưng settings cung cấp `<activeProfile>ci</activeProfile>`. Đây là minh họa vì sao chỉ so dòng `mvn ...` của terminal với CI chưa đủ.

### 9.5. Cô lập user settings khi máy có cấu hình riêng

Trường hợp máy developer có `~/.m2/settings.xml` dùng private mirror hoặc activeProfile không mong muốn, chỉ định `-s lab-settings.xml` để thay user settings trong phép thử.

**Không kết luận đó là môi trường hoàn toàn sạch**: Maven vẫn có global settings đi kèm distribution, `.mvn/maven.config` trong project và environment variables. Muốn baseline đáng tin phải kiểm tra các inputs đó nữa.

### 9.6. Lệnh kiểm tra profile và property

```bash
mvn -B -ntp -Pci org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -q -Pci org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=lab.mode -DforceStdout
mvn -B -ntp -Pci org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

Tìm `lab.mode`, resources filtering và Surefire `expected.mode` trong effective POM. **Không lấy một test PASS làm bằng chứng chọn đúng profile** nếu không có kiểm tra active-profiles.

## 10. So sánh terminal và IDE từng bước

IDE có thể dùng Maven khác hẳn terminal. Khi chẩn đoán:

### 10.1. Kiểm tra Maven distribution

- Terminal: `mvn -version`.
- IDE Maven settings: xem **Bundled Maven**, **External Maven** hoặc **Maven Wrapper** đang được dùng.
- CI: xem setup Maven/package image/Maven Wrapper version.

Maven Wrapper (khi dự án đã có `mvnw`/`mvnw.cmd` và wrapper config) giúp chuẩn hóa **Maven distribution**. Nó **không tự bảo đảm** JDK, settings, profiles và credentials giống nhau.

Nếu `./mvnw -version` và `mvn -version` khác, đừng bỏ qua sự khác biệt trước khi so build failures.

### 10.2. Kiểm tra JDK

- Terminal: `mvn -version` cho biết JDK Maven thực sự đang chạy.
- IDE: importer JDK và runner JDK có thể khác; IDE-native JUnit có thể dùng thêm test JRE riêng.
- CI: setup-java/container JDK và toolchains.

Ví dụ POM đặt:

```xml
<maven.compiler.release>17</maven.compiler.release>
```

Nó quy định Java language/API target cho compiler tương thích, nhưng **không tự cài JDK 17** và không bảo đảm JDK vendor/update giống nhau. Maven chạy trên JDK quá cũ có thể báo lỗi compiler `release version 17 not supported`.

Nếu cần JDK riêng cho build, có thể dùng **Maven Toolchains** (maven-toolchains-plugin + machine-local `toolchains.xml`), tách JDK Maven chạy với JDK mà toolchain-aware plugins sử dụng. Phải cấu hình và kiểm chứng, không chỉ thấy `toolchains.xml` tồn tại.

### 10.3. Kiểm tra profiles trong IDE

Trong Maven tool window:
- Xem ticked/active Maven profiles.
- Kiểm tra Run Configuration có `-P...` hoặc `-D...` không.
- Xem settings file path và local repository path.
- Chạy **Maven goal `clean verify`** từ IDE (không phải nút IDE-native JUnit) để đối chiếu.
- Nếu IDE cho phép, hiển thị output của `help:active-profiles` và `help:effective-pom` trong cùng run context.

**Một IDE test runner PASS có thể chưa thực hiện Maven Failsafe/Checkstyle/JaCoCo goals** như CI. Hãy phân biệt kết quả IDE-native tests với Maven lifecycle.

### 10.4. IDE reimport project chưa cập nhật

Sau khi sửa POM, IDE có thể giữ project model cũ tới khi Maven reimport/reload. Nếu code ở terminal build PASS nhưng IDE báo import error:
1. Kiểm tra distribution/JDK/settings/profiles.
2. Reload/reimport Maven project.
3. Đọc error thuộc dependency resolution, project model hay Java compile.
4. Nếu cần, chạy same goal từ IDE terminal để tách IDE importer issue khỏi Maven CLI issue.

Không bắt đầu bằng **Invalidate All Caches** khi chưa xác định nguyên nhân; thao tác đó có thể mất thời gian mà không sửa profile/settings sai.

## 11. CI khác local bằng cách nào và nên cấu hình ra sao?

Một pipeline có thể dùng CI-created settings với server tokens:
- Settings file từ `actions/setup-java` hoặc container entrypoint.
- Secrets môi trường CI cho download/deploy, không có trên pull request fork.
- Private Maven mirror chỉ truy cập qua VPN/network nội bộ.
- Profiles active từ CLI hoặc settings.
- JDK cố định qua setup-java.
- Cache Maven được phục hồi từ các lần chạy khác.

### 11.1. Ví dụ GitHub Actions cho lab không có secrets

File `.github/workflows/maven-profiles.yml`:

```yaml
name: Maven profile diagnostics

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify-ci-profile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Capture non-secret environment versions
        run: |
          java -version
          mvn -version

      - name: Show active Maven profiles
        run: |
          mvn -B -ntp -Pci org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles

      - name: Build with explicit CI profile
        run: mvn -B -ntp -Pci clean verify

      - name: Verify application mode
        run: java -cp target/classes dev.course.App

      - name: Keep Surefire test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: surefire-ci-profiles
          path: target/surefire-reports/
          if-no-files-found: warn
          retention-days: 7
```

Với POM lab, CI step App dự kiến in:

```text
MODE=ci; LABEL=Maven profile lab
```

**Quan trọng:** workflow này là ví dụ học thuật, không deploy, không có secret. Trên production hãy pin Actions versions/commit SHAs, áp rules cho protected branches, và không upload raw effective settings nếu chúng chứa thông tin nội bộ. Report upload là để điều tra khi build fail, không biến Maven failure thành PASS.

### 11.2. Khi CI dùng private repository

Trong môi trường thật, có thể dùng CI secret manager cấp credentials cho Maven settings; đảm bảo `server/id` khớp repository/mirror ID và không in password trong log.

**Không đẩy `settings.xml` có token vào Git.** Một public build không có access vào private repo sẽ không thể resolve dependencies, dù cùng source. Điều này không được giải quyết bằng cách ghi token vào URL POM.

### 11.3. Khi cùng -Pci nhưng CI vẫn khác local

Kiểm tra:
- Global/user settings, mirror/proxy/servers.
- Maven/JDK versions.
- Base image, OS, locale/timezone.
- `.mvn/maven.config`, env properties và system properties.
- Repository contents, SNAPSHOT retention, local cache.
- Maven profiles có activation JDK/OS/file.
- Plugin version management và CI-specific environment settings.

**Explicit -Pci kiểm soát một phần cấu hình, không khóa toàn bộ môi trường.**

## 12. Lỗi 401/403/404 và dependency resolution: phân loại trước khi sửa

| Triệu chứng | Nguyên nhân điển hình | Hướng chẩn đoán ít rủi ro |
| --- | --- | --- |
| Local PASS, CI 401 | CI không có token hoặc server ID sai | Kiểm tra ID, secret injection, scopes mà không in token |
| CI 403 | Quyền repo không đủ, policy chặn | Kiểm tra role, repository allowlist, IP/network policy |
| Plugin resolution fail riêng ở CI | `pluginRepositories` hoặc mirror thiếu plugin | So effective settings, plugin repo URL/ID |
| Dependency 404 | Sai GAV/version hoặc endpoint | So exact GAV, repository policy, URL |
| Parent POM không resolve | Parent remote/private, relativePath sai | So reactor/root, settings/repo và GAV |
| CI offline error | `-o`/settings offline hoặc runner không network | Kiểm tra offline flag, cached artifacts |
| TLS handshake/cert fail | Truststore/CA khác | Dùng CA/truststore đúng, không tắt TLS verification |
| Download timeout | Proxy/firewall/DNS/VPN khác | Kiểm tra network path và proxy |
| Local dùng stale SNAPSHOT | Cache có version cũ | Dùng controlled update/isolated repo; không xóa mù |
| Version range khác artifact | Repo metadata khác theo mirror/cache | Pin released version và verify dependency tree |

**Đọc HTTP status code và endpoint ID, nhưng không đưa Authorization headers, signed URLs hoặc raw `-X` logs lên ticket công khai.**

### 12.1. -U có giải quyết tất cả cache issues?

`mvn -U` yêu cầu Maven force-check updated SNAPSHOT releases và missing releases theo chính sách Maven version. Nó **không sửa** token sai, profile chưa active, JDK sai hoặc repository URL nhầm.

Ví dụ:

```bash
mvn -B -ntp -U clean verify
```

Chỉ dùng sau khi đã biết chuyện liên quan remote metadata/cache và muốn cập nhật. Không nhầm `-U` với xóa local repo hoặc refresh mọi immutable release JAR.

### 12.2. Đặt isolated local repository khi cần

```bash
mvn -B -ntp -Dmaven.repo.local=/tmp/maven-lab-cache clean verify
```

Đây là **lệnh POSIX**, trên Windows chọn đường dẫn kiểu Windows. Nó giúp xem local cache lâu ngày có che missing dependency không. Khi dùng cache riêng, Maven có thể phải tải plugins/dependencies mới; đừng coi lỗi do network của cache sạch là lỗi source code.

## 13. Một số cấu hình ít thấy nhưng ảnh hưởng rất lớn

### 13.1. .mvn/maven.config

Một dự án có thể commit file `.mvn/maven.config` chứa CLI arguments mặc định cho Maven. Ví dụ `-Pci` hoặc `-DskipTests` trong đó ảnh hưởng ngay cả khi người chạy gõ `mvn clean verify`.

**Cần đọc file đó trong phạm vi repo thật khi điều tra**, nhưng trong lab chúng ta không thêm file này để tránh phụ thuộc cấu hình ẩn.

Khi máy local/IDE/CI dùng Maven versions khác nhau, cách parser xử lý arguments từ maven.config cũng có thể khác; không copy blindly một file option phức tạp từ IDE sang CI.

### 13.2. MAVEN_OPTS, JAVA_TOOL_OPTIONS và shell environment

- `MAVEN_OPTS` cấp JVM options cho Maven process.
- `JAVA_TOOL_OPTIONS` có thể tác động đến Java processes, kể cả test forks.
- Một số Maven versions còn hỗ trợ environment-argument injection (ví dụ `MAVEN_ARGS` theo version); kiểm tra exact Maven distribution.
- Environment variables như `CI` có thể được một profile hoặc plugin dùng cho activation/behavior nếu cấu hình.
- Locale/timezone và OS file separator ảnh hưởng tests có date/path assumptions.

**Không in toàn bộ environment** để debug khi runner có secrets. Chỉ ghi names/known-safe metadata.

### 13.3. Maven Toolchains

Một project có thể khai báo:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
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

**Snippet này không thuộc POM lab hoàn chỉnh**, chỉ minh họa nếu project dùng toolchains. Build host phải có `~/.m2/toolchains.xml` khai báo JDK tương ứng hoặc cơ chế discovery/select được cấu hình.

Compiler và test plugins **có thể** dùng toolchain JDK khác JDK Maven process; kiểm tra log toolchain selection. Trường `maven.compiler.release=17` chỉ đặt target language/API, không tự thiết lập toolchain.

### 13.4. Maven 4 project settings khác Maven 3

Maven 4 có hỗ trợ `.mvn/settings.xml` ở project level nhưng **không sử dụng các phần user-specific nhạy cảm** trong project settings như server credentials/localRepository. Không giả định Maven 3.9.x hiểu file đó giống Maven 4.

Trên Maven 3.9.x trong bài, tập trung vào global/user settings và `-s`. Khi chuyển Maven major version, đọc settings reference của version tương ứng rồi kiểm tra effective settings.

## 14. Chẩn đoán một ca thật theo trình tự

**Tình huống:** developer chạy `mvn verify` PASS, IDE hiện resource `MODE=dev`, CI lại in `MODE=ci` và một test cấu hình sản xuất FAIL.

### Bước 1: xác nhận chính xác môi trường

Trong terminal và CI:
```bash
mvn -version
java -version
```

Trong IDE xem Maven home, importer/runner JDK. Không dựa vào tên IDE project để suy ra Maven version.

### Bước 2: xác nhận settings input

- Maven user settings path có giống không?
- Có `-s custom-settings.xml` không?
- Có global settings của Maven distribution khác không?
- CI setup action có tạo `~/.m2/settings.xml` mới không?
- IDE có chọn offline mode/mirror/local repository khác không?

Không cần in credentials; chỉ so **paths, IDs, flags và những URL đã được redacted**.

### Bước 3: xác nhận active profiles

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
```

Nếu local active `dev` còn CI active `ci` thì đây là khác biệt **được cấu hình có chủ đích hoặc vô ý**. Hãy quyết định profile nào đáng lẽ phải active theo policy.

### Bước 4: xác nhận effective project model

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

Kiểm tra `lab.mode`, plugin executions, resource filtering, dependency versions, profiles and properties. Với nhiều modules, kiểm tra đúng module bị lỗi.

### Bước 5: xác nhận outputs thực

Tìm `target/classes/build-info.properties` của lần build hiện tại. Chạy:

```bash
java -cp target/classes dev.course.App
```

Nếu `MODE=ci` khác `MODE=dev`, điều này cho thấy filtered content thực tế khác. Dùng `clean` để loại stale target trước phép thử nếu an toàn.

### Bước 6: so tests/goals/exit code

- IDE-native JUnit có thể chạy tests mà không gọi Maven Resources Plugin như CI.
- Maven `test` không tương đương `verify` khi project bind Failsafe/Checkstyle/JaCoCo ở phases sau.
- Một profile có thể thay `skipTests`, test includes hoặc plugin configuration.
- So `target/surefire-reports/` / `target/failsafe-reports/`, modules và số tests thực sự chạy.

### Bước 7: sửa đúng nguồn lệch

- Nếu profile CI cần active: thêm `-Pci` tường minh vào CI và local verification command.
- Nếu IDE Maven distribution sai: chọn Maven Wrapper/external version thống nhất.
- Nếu settings mirror/auth sai: sửa settings/secret injection, không đưa token vào POM.
- Nếu JDK sai: chỉnh Maven runner JDK/toolchains.
- Nếu cache stale: thử isolated repo hoặc `-U` có kiểm soát.
- Nếu profile theo OS/file không portable: refactor thành explicit property/profile hoặc thêm coverage tests.

**Không kết luận đã sửa xong chỉ vì một máy chạy PASS**. Rerun ở môi trường từng FAIL và so exact effective configuration/outputs.

## 15. Ma trận quyết định theo triệu chứng

| Khác biệt | Lệnh/chỗ xem đầu tiên | Phát hiện chính |
| --- | --- | --- |
| IDE compile fail, CLI pass | IDE Maven home/JDK, `mvn -version` | Khác JDK/Maven |
| CI 401, local pass | user settings server IDs, secret injection | Thiếu credential/quyền |
| CI không tải được plugin | pluginRepositories/mirror/offline | Plugin source khác |
| CI resource khác | `help:active-profiles` + filtered resource | Profile/property khác |
| Local tests pass, CI integration tests fail | `test` vs `verify`, Failsafe reports | Goal coverage khác |
| Same -Pci, output khác | effective POM/settings, -D/env | Property/activation khác |
| Local có dependency, CI thiếu | isolated repo + dependency GAV | Cache cũ/remote missing |
| IDE chỉ thiếu nguồn generated | Maven reimport, plugin executions | IDE model stale |
| Profile active trên Windows, không ở Linux | OS activation | Build profile gắn OS |
| Profile active trên JDK17, không ở JDK21 | JDK activation | Maven runtime JDK khác |
| Build khác giữa CI runners | Java/Maven image, env, cache | Non-hermetic inputs |
| Full reactor khác selected module | -pl/-am, parent POM inheritance | Modules/goals chưa chạy |

### 15.1. Có nên dùng mvn -X không?

`mvn -X` có thể giúp ở ca sâu (resolver transport, plugin config), nhưng là **biện pháp sau cùng**:
- Dùng trên private ephemeral runner khi có quyền.
- Không echo password/token.
- Không upload raw debug logs nếu CI dùng credentials.
- Cắt/redact những fields nhạy cảm trước khi gửi hỗ trợ.
- Không nhầm `-q` hoặc CI masking với sự bảo vệ tuyệt đối.

Trước khi bật `-X`, phần lớn vấn đề có thể chẩn đoán nhờ `-version`, Help Plugin, logs thông thường, repository IDs/HTTP status và Maven test reports.

## 16. Checklist để local, IDE và CI nhất quán hơn

- [ ] Dùng cùng source commit/tag và module selection.
- [ ] Ghim Maven distribution, ưu tiên Maven Wrapper nếu phù hợp.
- [ ] Ghim JDK 17/toolchain theo policy, kiểm tra `mvn -version`.
- [ ] POM ghim plugin/dependency versions, tránh SNAPSHOT/range tùy tiện.
- [ ] Profiles cho CI/production được bật **tường minh** khi cần.
- [ ] Không dựa vào một activeByDefault profile để ngầm chọn môi trường phát hành.
- [ ] Global/user/CI settings, -s/-gs và local repo được ghi nhận theo đường dẫn/ID, không lộ secret.
- [ ] Mirrors/proxies/repositories/pluginRepositories hợp lệ và được quản trị tập trung.
- [ ] Server IDs khớp effective repository/mirror IDs; credentials ở secret store.
- [ ] CI không cấp secrets cho untrusted pull request.
- [ ] Không dùng `-o`/offline hoặc `-DskipTests` ngoài policy.
- [ ] `.mvn/maven.config` và env flags được xét khi so effective invocation.
- [ ] IDE importer/runner Maven, JDK và profiles khớp intended Maven CLI build.
- [ ] IDE-native JUnit được phân biệt với Maven Surefire/Failsafe lifecycle.
- [ ] Có `help:active-profiles` và `help:effective-pom` evidence ở môi trường lỗi.
- [ ] Build từ `clean` nếu muốn loại outputs stale.
- [ ] Khi nghi cache, dùng localRepository cô lập thay vì xóa mù.
- [ ] Không upload raw effective-settings/effective-pom/debug logs có thông tin nội bộ.
- [ ] Đã xác nhận số tests, modules, goals và CI exit code.
- [ ] Fix được kiểm chứng lại trên môi trường từng thất bại.

## 17. Bài tập thực hành

1. Nêu đường dẫn global và user settings của Maven 3.x.
2. Giải thích user settings merge với global settings như thế nào.
3. POM profile khác settings profile về các trường cấu hình được phép ra sao?
4. Vì sao local cache có thể che thiếu dependency trên CI?
5. `mirrorOf=central` khác `mirrorOf=*` thế nào?
6. Vì sao pluginRepositories cần xem riêng khi không resolve Maven plugin?
7. Phân biệt `-s` với `-gs`.
8. `-Pci` khác `-Dbuild.environment=ci` theo cơ chế nào?
9. Active-by-default của profile dev thay đổi ra sao khi ci profile cùng POM active?
10. Vì sao một POM profile active theo JDK có thể khác giữa IDE và CI?
11. Profile active qua settings.xml có thể làm command không có -P vẫn chạy ci mode không?
12. Tạo POM/Java/resources/tests lab; chạy `mvn clean verify` và đếm 3 unit tests.
13. Xác nhận stdout `MODE=dev; LABEL=Maven profile lab` khi profile dev active.
14. Chạy `-Pci clean verify`, xác nhận stdout `MODE=ci; LABEL=Maven profile lab`.
15. Kiểm tra nội dung `target/classes/build-info.properties` ở hai lần build.
16. Dùng `lab-settings.xml` để active settings profile, xem `help:active-profiles`.
17. Dùng `ci-settings.xml` để bật POM ci profile mà không truyền `-Pci`.
18. Vì sao test `filteredModeMatchesEffectiveModel` có thể PASS dù chọn sai profile mong muốn?
19. Lệnh `help:effective-pom` giúp xem những giá trị nào?
20. `help:effective-settings` có nên copy nguyên lên public issue không?
21. Vì sao `-X` có thể làm log lộ thêm dữ liệu nhạy cảm?
22. `maven.compiler.release=17` có tự cài JDK17 cho CI không?
23. Maven Toolchains giúp tách JDK Maven process và compiler JDK thế nào?
24. Một IDE-native JUnit run có tương đương Maven `verify` không?
25. Khi CI 401 còn máy developer PASS, các bước nào không đòi in token?
26. Khi local SNAPSHOT cũ che lỗi, `-U` khác isolated repository thế nào?
27. Nếu Maven 4 có project settings, có thể commit credentials vào .mvn/settings.xml không?
28. Một profile theo OS/file có rủi ro gì với CI runner/container?
29. Đề xuất những metadata không nhạy cảm để ghi trong bug report Maven.
30. Thiết kế một CI gate kiểm tra active profile đúng thay vì chỉ thấy unit tests PASS.

## 18. Tổng kết

Khi máy cá nhân, IDE và CI cho kết quả khác nhau, **đừng mặc định code sai hoặc Maven lỗi**. Xác định **effective inputs**:

- **Settings**: global/user/CI-specific, mirrors, proxies, repositories, credentials và local cache.
- **Profiles**: POM/settings, activeByDefault, `-P`, property/JDK/OS/file activation.
- **Tools**: Maven/JDK versions, IDE importer/runner, wrapper và toolchains.
- **Invocation**: goals, modules, `-D` properties, env flags, skip settings.
- **Outputs**: effective POM, active profiles, filtered resources, reports và exit codes.

Trong lab Java 17, 3 JUnit tests kiểm tra filtered resource. Cùng source tạo stdout khác khi active profile khác:

```text
MODE=dev; LABEL=Maven profile lab
```

so với:

```text
MODE=ci; LABEL=Maven profile lab
```

Điều quan trọng là **biết sự khác biệt này có chủ đích hay là lỗi cấu hình**, và chứng minh bằng `help:active-profiles`, `help:effective-settings`, `help:effective-pom` thay vì suy đoán.

## 19. Tài liệu tham khảo chính thức

- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven Help Plugin — help:active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html)
- [Apache Maven Help Plugin — help:effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Help Plugin — help:effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Apache Maven Help Plugin — help:evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html)
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Apache Maven — Guide to Using Maven 3](https://maven.apache.org/guides/getting-started/index.html)
- [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
