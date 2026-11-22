# Đồng bộ JDK, Maven, settings và profile giữa IDE với terminal

## 1. Vì sao cùng một pom.xml nhưng IDE và terminal build khác nhau?

Trong một dự án Java dùng Maven, tình huống phổ biến là terminal chạy `mvn clean verify` thành công nhưng IDE báo lỗi import, dùng sai JDK, không tải được dependency, hoặc một bài kiểm thử chỉ hỏng khi chạy bằng nút Run trong IDE. Cũng có trường hợp IDE xanh nhưng CI đỏ dù cả ba môi trường đều mở cùng một `pom.xml`.

Nguyên nhân thường không nằm ở Java source mà ở **ngữ cảnh thực thi Maven**:

- **JDK chạy Maven**: JVM khởi động Maven, ảnh hưởng plugin, TLS, system properties và quy tắc kích hoạt profile theo JDK.
- **JDK biên dịch**: JDK/Javac thực sự dùng bởi Compiler Plugin hoặc Maven Toolchains.
- **JDK chạy tests và app**: có thể khác JDK importer, compiler và Maven runner.
- **Phiên bản Maven**: Maven hệ thống, bản kèm IDE, hoặc Maven Wrapper trong repository.
- **Maven settings**: user/global `settings.xml`, mirrors, repositories, proxies, server credentials, offline mode và local repository.
- **Maven profiles**: kích hoạt theo `-P`, `settings.xml`, JDK, OS, properties, environment, file hoặc `activeByDefault`.
- **Maven command-line và JVM options**: `.mvn/maven.config`, `.mvn/jvm.config`, `MAVEN_OPTS`, `MAVEN_ARGS`, các `-D...` riêng của Run Configuration.
- **Working directory và scope**: root aggregator hay một module con; build Maven Runner hay biên dịch/bấm Run bằng cơ chế native IDE.

Mục tiêu không phải làm tất cả máy có cùng absolute path, mà là bảo đảm **các thông số có tác động đến build và test giống nhau theo chính sách dự án**, đồng thời ghi rõ những khác biệt được phép: đường dẫn JDK, local Maven cache, tài khoản repository và thông số máy.

Trong bài, ta sử dụng **Java 17, Maven 3.9.x**, một Maven project đơn module, hai profile `local`/`ci`, một resource được Maven filtering và bốn JUnit 5 tests. Bài thực hành kiểm tra rằng **IDE Maven Runner, terminal và CI** chọn đúng profile thay vì chỉ có trạng thái `BUILD SUCCESS` chung chung.

## 2. Ma trận đối chiếu trước khi sửa cấu hình

| Thành phần | Terminal thường lấy từ đâu? | IDE có thể dùng gì khác? | Kiểm chứng |
| --- | --- | --- | --- |
| JDK chạy Maven | `JAVA_HOME`, PATH, launcher | JDK for importer / Maven runner JRE | `mvn -version` trong cả hai ngữ cảnh |
| JDK compiler | Maven runtime JDK hoặc Toolchain | Project SDK / native IDE compiler | Compiler release, Toolchains logs, test bytecode |
| JDK chạy tests | Surefire JVM/toolchain | Native JUnit Run Configuration JRE | Maven test và native JUnit runner phân biệt |
| Maven binary | Lệnh `mvn` trên PATH hoặc `./mvnw` | Bundled Maven / Custom Maven / Wrapper | `mvn -version`, IDE Maven home |
| User settings | `${user.home}/.m2/settings.xml` hoặc `-s` | User settings file override riêng | `help:effective-settings` an toàn |
| Global settings | `${maven.home}/conf/settings.xml` hoặc `-gs` | Global settings của bản Maven IDE chọn | Maven home + effective settings |
| Local repository | Default hoặc `-Dmaven.repo.local` | Local repository override | Path thực tế, dependency tree |
| Active profiles | `-P`, settings, activation | Tích chọn IDE Profiles, runner options | `help:active-profiles` |
| Maven CLI flags | Shell, `MAVEN_ARGS`, `.mvn/maven.config` | IDE runner options khác | Lệnh Maven thực được chạy |
| Maven JVM flags | `MAVEN_OPTS`, `.mvn/jvm.config` | Importer/runner VM options | Log JVM, system properties |
| Dependency resolution | settings, mirrors, repos, offline | Cache khác, proxy khác, offline toggle | Dependency tree và transfer logs |
| Build goal | `clean verify`, `test`, `package` | Native Build Project hoặc một goal khác | Chạy cùng Maven goals trước khi so sánh |

**Không đồng nhất “Project SDK = JDK chạy Maven”.** Một IDE có thể dùng JDK 17 để phân tích Java code nhưng dùng JVM 21 để chạy Maven; compiler có thể tiếp tục tạo bytecode Java 17 nhờ `maven.compiler.release=17`. Nếu một plugin có ràng buộc JDK khác, hai build vẫn có thể khác.

## 3. Bốn loại version Java cần phân biệt

### 3.1. JDK chạy Maven

Lệnh từ terminal:

```bash
java -version
javac -version
mvn -version
```

`java -version` cho biết executable `java` mà shell tìm thấy; `javac -version` cho biết compiler nằm trên PATH; còn **`mvn -version` hiển thị Java version và Java home của JVM thực sự chạy Maven**. Đây là bằng chứng quan trọng nhất để so terminal với Maven Runner.

Nếu `java -version` báo 17 nhưng `mvn -version` báo 21, rất có thể `JAVA_HOME` và PATH khác nhau. Ngược lại, `javac -version` báo 21 nhưng Maven đang chạy JDK 17 cũng có thể xảy ra.

### 3.2. JDK dùng để compile

Trong POM:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Khi Maven Compiler Plugin hỗ trợ `--release`, cấu hình này chọn target language/API của Java 17. Nó **không tự tải một JDK 17**, không có nghĩa Maven đang chạy JDK 17 và không đặt JRE cho nút Run của IDE. Nếu chạy `javac` quá cũ để hỗ trợ release 17, build vẫn fail.

### 3.3. JDK chạy unit tests

Maven Surefire Plugin chạy test bằng Java mà Maven/test fork configuration chọn. Maven Toolchains và tùy chọn riêng của Surefire có thể thay JVM dùng cho test. Trong IDE, nút Run trên một test class có thể chạy bằng **IDE JUnit runner**, không đi qua Surefire và không nhận đúng Maven profiles/system properties.

Vì vậy phải phân biệt hai bằng chứng:

- `./mvnw -Pci ... test` chạy **Maven Surefire**.
- Nhấn Run cạnh `@Test` chạy **IDE test runner** trừ khi IDE được cấu hình delegate build/test đến Maven.

Đừng lấy một native IDE JUnit PASS để kết luận một Maven profile đã được kích hoạt.

### 3.4. JDK chạy ứng dụng

Run Configuration có thể chọn JRE riêng, khác compiler/Maven. Một app được compile cho release 17 vẫn có thể fail ở runtime nếu chạy dưới JRE 11 với `UnsupportedClassVersionError`.

Khi debug lỗi, ghi cụ thể JDK **Maven / compiler / tests / ứng dụng**, thay vì nói mơ hồ “dự án dùng Java 17”.

## 4. Đồng bộ Maven binary bằng Maven Wrapper

Một shell có thể gọi Maven 3.9.x trong khi IDE dùng bản Maven bundled khác; kết quả của Maven core, plugin resolver, model builder và profile behavior có thể khác.

Maven Wrapper cung cấp lệnh nằm trong repository:

```bash
./mvnw -version
./mvnw -B clean verify
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd -version
.\mvnw.cmd -B clean verify
```

Wrapper giúp sử dụng **Maven distribution đã pin** trong `.mvn/wrapper/maven-wrapper.properties`. Nó không tự cài JDK phù hợp cho mọi máy và không tự đồng bộ `settings.xml`, environment variables hay local repository. Những phần đó phải được cấu hình riêng.

### 4.1. Khởi tạo Wrapper một lần và review vào Git

Ví dụ, khi project chưa có Wrapper và Maven hệ thống đã cài:

```bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.2:wrapper -Dmaven=3.9.9
```

Đây là lệnh **thiết lập project**; chạy một lần theo quy trình, review các file được sinh ra rồi commit những thành phần Wrapper cần thiết. Maven 3.9.9 ở ví dụ là một **version được pin để học**, không khẳng định là bản mới nhất.

Sau khi đã có Wrapper, cả terminal, IDE và CI nên chọn **Maven Wrapper**, không mỗi môi trường tự dùng bundled/system Maven khác. Dùng `./mvnw -version` làm lệnh đối chiếu.

### 4.2. Những điểm cần kiểm khi Wrapper không hoạt động

- Wrapper scripts `mvnw`, `mvnw.cmd` và `.mvn/wrapper/maven-wrapper.properties` có đủ trong checkout?
- Script trên Unix có quyền thực thi? Nếu repository không bảo toàn mode, cần xử lý đúng trong Git.
- `distributionUrl` dùng HTTPS/nguồn tin cậy và được phép qua firewall/proxy?
- Mirror/settings có cho tải Maven distribution và plugins không?
- IDE có thực sự chọn Wrapper, hay chỉ tìm thấy nó nhưng vẫn dùng Maven home khác?
- `./mvnw -version` có in đúng pinned Maven version?
- Maven Wrapper không biến `JAVA_HOME` thành JDK 17; cần kiểm `Java home` riêng.

Không vô tình kiểm tra checksum hoặc nguồn tải Wrapper bằng cách bỏ qua TLS verification hoặc tắt bảo mật repository. Tổ chức có thể yêu cầu tải qua artifact mirror được phê duyệt.

## 5. Maven settings: hai file nguồn và cách ghi đè

Theo Apache Maven, các settings phổ biến là:

```text
${maven.home}/conf/settings.xml        global settings
${user.home}/.m2/settings.xml         user settings
```

Maven kết hợp settings ở hai mức, thường **user settings ưu tiên** khi có giá trị đè. Khi IDE dùng Maven home khác, nó cũng có thể dùng **global settings khác**. IDE còn cho phép chỉ định riêng **user settings file** và **local repository**, nên cùng một user account vẫn có thể resolve dependencies khác nhau.

Dùng CLI khi cần một file settings được cấp riêng:

```bash
./mvnw -s /path/to/approved-settings.xml -B clean verify
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd -s 'C:\path\to\approved-settings.xml' -B clean verify
```

Đường dẫn `/path/to/...` và `C:\path\to\...` là **placeholder đường dẫn môi trường**, phải thay bằng file thật. Không commit file settings chứa credentials vào repository.

### 5.1. Settings có thể cấu hình gì?

| Element | Vai trò |
| --- | --- |
| `<localRepository>` | Nơi cache/download artifacts |
| `<servers>` | Credentials và cấu hình server theo ID |
| `<mirrors>` | Mirror/proxy repository destinations |
| `<proxies>` | Proxy mạng dùng bởi Maven |
| `<profiles>` | Properties, repositories, pluginRepositories và activation được phép trong settings |
| `<activeProfiles>` | Các ID profile mặc định được bật trong settings |
| `<offline>` | Trạng thái Maven offline |
| `<pluginGroups>` | Nhóm plugin dùng khi gọi goal qua prefix |

Settings profiles **không có đầy đủ khả năng của POM build profiles**: không đặt mọi cấu hình build plugin/execution trực tiếp trong settings như một POM. Các cấu hình như Maven Compiler Plugin, resources filtering và test configuration chính nên nằm trong project `pom.xml`.

### 5.2. Ví dụ mirror không chứa secret

Một settings **chỉ minh họa**:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>approved-cache</id>
            <mirrorOf>central</mirrorOf>
            <url>https://repo.example.invalid/maven/public</url>
        </mirror>
    </mirrors>
</settings>
```

Domain `example.invalid` **không phải repository có thật**. Dùng nó nguyên xi sẽ gây lỗi tải dependency; chỉ thay URL khi tổ chức đã cấp mirror phù hợp. Không điền username/password/token vào POM hoặc ví dụ chia sẻ.

Nếu IDE dùng settings chứa mirror doanh nghiệp còn terminal dùng mặc định, terminal có thể gặp 401/403, PKIX/TLS, timeout hoặc tải artifacts khác. Khi đó việc sửa `pom.xml` thường **không phải giải pháp đúng**.

### 5.3. Local repository không đồng nghĩa remote repository

Default Maven local repository là `${user.home}/.m2/repository`. Có thể chỉ định path kiểm chứng:

```bash
./mvnw -Dmaven.repo.local=/path/to/qa-m2 -B clean verify
```

Nó đổi nơi cache local, **không** thay GAV và không tự thêm một remote repository. IDE local repository override và terminal `-Dmaven.repo.local` khác nhau có thể giải thích vì sao một bên có dependency đã cache và bên kia phải download.

Không xoá toàn bộ `~/.m2` chỉ để xử lý lỗi import IDE. Nên đối chiếu version, repo path, mirror và POM trước; chỉ dọn những artifact cache cụ thể khi có bằng chứng và quyền phù hợp.

## 6. Đọc effective settings mà không lộ credentials

Maven Help Plugin hỗ trợ `effective-settings` để hiển thị settings sau khi kết hợp global/user. Ví dụ:

```bash
./mvnw -B org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-settings -DshowPasswords=false
```

`showPasswords=false` là mặc định của goal ở plugin tương ứng. **Không dùng `-DshowPasswords=true` trong CI hoặc chia sẻ logs.** Dù passwords được ẩn, effective settings vẫn có thể chứa URL nội bộ, tên máy, repository path, username hoặc thông tin nhạy cảm khác; hãy rà soát trước khi upload/đưa vào ticket.

Để so IDE với terminal:

1. Kiểm Maven home và user settings file được chọn ở IDE.
2. Kiểm `mvn -version`/Wrapper version và global settings thuộc Maven home đó.
3. Chạy đúng goal effective-settings trong **IDE Maven Runner**, không chỉ trong IDE terminal.
4. So mirror IDs, repository URLs, offline flag và local repository.
5. Không so nội dung secrets giữa hai file bằng cách in plaintext ra chat/log.

Nếu CLI dùng `-s` riêng, mọi lệnh đối chiếu phải dùng cùng flag; nếu quên, `help:effective-settings` có thể báo khác với build lỗi.

## 7. Profile Maven hoạt động ở đâu và kích hoạt thế nào?

Maven profiles có thể định nghĩa trong project `pom.xml`, trong user settings hoặc global settings. Chúng được kích hoạt bởi nhiều cơ chế:

- Tường minh bằng `-PprofileId`.
- Danh sách `<activeProfiles>` trong settings.
- `activeByDefault` trong POM.
- Điều kiện JDK, OS, system/user property, environment variable, packaging hoặc file existence theo plugin/Maven version.

Lệnh minh họa:

```bash
./mvnw -Plocal clean verify
./mvnw -Pci clean verify
```

Nếu mỗi profile thay dependency, resource filtering hoặc compiler options, hai lệnh có thể tạo artifacts khác nhau dù dùng cùng Java source.

### 7.1. `activeByDefault` có thể gây lệch khó thấy

Khi một profile trong POM dùng:

```xml
<activation>
    <activeByDefault>true</activeByDefault>
</activation>
```

nó thường chỉ active nếu **không có profile khác trong cùng POM được kích hoạt**. Khi IDE bật `ci` còn terminal không bật gì, một profile default có thể bị vô hiệu và những properties/dependencies thay đổi.

Bài thực hành **không** dùng `activeByDefault`. Thay vào đó, luôn yêu cầu `-Plocal` hoặc `-Pci` rõ ràng; trường hợp không chọn profile được gắn giá trị `unselected` để test phát hiện.

### 7.2. Profile cùng ID ở settings và POM

Profile activation được xử lý theo từng container model; profile trong settings và profile trong POM không thể được hiểu đơn giản như một “global profile object” duy nhất. Những properties có thể bị ảnh hưởng bởi precedence giữa user/CLI/POM/profile. Vì vậy tránh đặt profile ID trùng nhưng ý nghĩa khác nhau ở settings và POM; hãy kiểm **active profile list và effective POM** thực tế.

### 7.3. Profile theo environment có thể bất ngờ

Ví dụ POM profile:

```xml
<activation>
    <property>
        <name>env.BUILD_FLAVOR</name>
        <value>ci</value>
    </property>
</activation>
```

Nếu CI process có `BUILD_FLAVOR=ci`, Maven có thể kích hoạt profile. IDE khởi chạy trước khi environment variable được cập nhật có thể **không** nhìn thấy biến đó trong process environment của nó.

Ví dụ trên chỉ là **một activation fragment**, không phải POM đầy đủ. Với một bài build cần tái lập, nên truyền `-Pci` và những user properties bắt buộc một cách tường minh, thay vì dựa vào biến tình cờ của máy.

## 8. Kiểm tra active profiles và effective POM

Ba lệnh quan trọng:

```bash
./mvnw -B org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
./mvnw -B org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
./mvnw -B org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=maven.compiler.release -q -DforceStdout
```

Khi cần xem profile cụ thể:

```bash
./mvnw -Plocal -B org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
./mvnw -Pci -B org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
```

Lệnh `active-profiles` cho biết profile nào đang active trong ngữ cảnh đó; `effective-pom` cho biết project model sau inheritance, profiles và configuration được áp dụng. Câu lệnh `evaluate` giúp xem một Maven expression/property trong project, không tự xác nhận JVM chạy Maven nếu expression chỉ là compiler release.

**Đừng dùng mỗi `mvn help:active-profiles` từ IDE terminal rồi suy ra Maven Runner của IDE dùng cùng settings.** Terminal tích hợp là một shell; Maven import/build runner có thể dùng Maven/JDK/settings/profiles riêng.

### 8.1. Ghi report theo lệnh Maven, không ghi secrets

Một form so sánh gọn:

```text
Field                      IDE Maven Runner       Terminal
Maven version              ...                    ...
Java home (Maven runtime)  ...                    ...
User settings path         ...                    ...
Global Maven home          ...                    ...
Local repository           ...                    ...
Active Maven profiles      ...                    ...
compiler.release           ...                    ...
Dependency resolution      ...                    ...
Test count/result          ...                    ...
```

Điền **giá trị thật đã kiểm** của từng môi trường. Không commit file effective-settings có credentials hoặc địa chỉ nội bộ nếu tài liệu sẽ public.

## 9. .mvn/maven.config và .mvn/jvm.config: không cùng mục đích

Khi project dùng Maven 3.9.x, có thể lưu CLI flags chung trong `.mvn/maven.config`:

```text
--no-transfer-progress
--fail-at-end
```

**Maven 3.9.0+ yêu cầu mỗi argument của `.mvn/maven.config` nằm trên một dòng riêng.** Bắt đầu từ Maven 3.9.3, dòng `#` có thể được hiểu là comment trong file này; đừng áp dụng giả định đó cho mọi bản Maven cũ.

File `.mvn/jvm.config` là **JVM startup options** cho Maven launcher, ví dụ:

```text
-Xmx768m
-Dfile.encoding=UTF-8
```

Không để `-Xmx768m` trong `.mvn/maven.config` và không để `-Pci` trong `.mvn/jvm.config`: file thứ nhất chứa Maven CLI args, file thứ hai chứa JVM args.

Cả hai có thể commit vào Git nếu **không chứa secrets hoặc absolute paths cá nhân** và mọi thành viên đồng thuận về defaults.

### 9.1. Vì sao không commit profile -Pci làm mặc định?

Nếu `.mvn/maven.config` chứa `-Pci`, terminal có thể tự động bật CI profile cho mọi command. IDE có thể có lựa chọn “Use settings from .mvn/maven.config” hoặc cách importer xử lý khác, khiến người dùng khó hiểu vì sao profile lệch.

Trong bài thực hành, giữ `.mvn/maven.config` **chỉ có flags vô hại**, rồi chọn `-Plocal`/`-Pci` tường minh ở cả IDE và terminal.

### 9.2. MAVEN_OPTS, MAVEN_ARGS, JAVA_TOOL_OPTIONS

- `MAVEN_OPTS`: JVM options khi Maven launcher khởi động JVM, ví dụ `-Xmx1g`.
- `MAVEN_ARGS`: từ Maven 3.9.0, có thể thêm Maven CLI args trước những arguments người dùng nhập.
- `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS`: Java launcher/JVM có thể áp dụng theo cơ chế riêng, ảnh hưởng nhiều Java processes, không chỉ Maven.
- `.mvn/jvm.config`: JVM options theo project qua Maven launcher.

Một terminal có `MAVEN_ARGS=-Pci` nhưng IDE process không kế thừa biến đó có thể gây khác profile. Một IDE chạy từ desktop icon thường không nhận environment từ shell mới mở sau đó. Trước khi so profile, kiểm environment của **process thực sự chạy Maven**.

Không in nguyên môi trường ra ticket vì có thể chứa tokens/secrets. Chỉ xem các biến liên quan và redact khi chia sẻ.

## 10. Dự án Java 17 thực hành: phát hiện sai profile bằng test

Dự án có POM một module, hai Maven profiles, resource được filter và bốn JUnit 5 testcases.

Cấu trúc:

```text
env-parity-lab/
├── pom.xml
├── .mvn/
│   ├── maven.config
│   └── jvm.config
├── src/
│   ├── main/
│   │   ├── java/dev/parity/
│   │   │   ├── BuildInfo.java
│   │   │   └── Main.java
│   │   └── resources/build-info.properties
│   └── test/java/dev/parity/
│       ├── BuildInfoTest.java
│       └── MainTest.java
└── target/                     (tạo sau khi Maven build)
```

**Lưu ý:** Wrapper files không có sẵn trong cấu trúc này. Sau khi chạy goal wrapper ở mục 4, có thêm `mvnw`, `mvnw.cmd` và `.mvn/wrapper/...`. Nếu chưa tạo Wrapper, thay `./mvnw` bằng `mvn` trong các lệnh thực hành. Để đạt parity lâu dài, nên review và commit Wrapper theo policy.

Trong bài demo, POM quy định Maven 3.9.x/JDK 17 cho **JVM chạy Maven** bằng Enforcer Plugin. Phần Toolchains sau bài sẽ giải thích cách thiết kế khác khi Maven runtime và compiler JDK được phép tách ra.

## 11. POM hoàn chỉnh: pin toolchain yêu cầu, resource filtering, Surefire và profiles

Tệp `env-parity-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.parity</groupId>
    <artifactId>env-parity-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <demo.active.profile>unselected</demo.active.profile>
        <expectedFlavor>UNSET</expectedFlavor>
    </properties>

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
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <expectedFlavor>${expectedFlavor}</expectedFlavor>
                    </systemPropertyVariables>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.5.0</version>
                <executions>
                    <execution>
                        <id>check-maven-and-jdk</id>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireJavaVersion>
                                    <version>[17,18)</version>
                                </requireJavaVersion>
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
                                </requireMavenVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>local</id>
            <properties>
                <demo.active.profile>local</demo.active.profile>
            </properties>
        </profile>
        <profile>
            <id>ci</id>
            <properties>
                <demo.active.profile>ci</demo.active.profile>
            </properties>
        </profile>
    </profiles>
</project>
```

**Điểm kỹ thuật đáng chú ý:**

1. `demo.active.profile=unselected` ở phần properties mặc định giúp nhận ra profile bị bỏ quên.
2. Profile `local` hoặc `ci` ghi đè property này khi được bật.
3. Resource filtering thay `${demo.active.profile}` bằng giá trị profile hiệu lực khi chạy phase `process-resources`.
4. Surefire truyền **`expectedFlavor` độc lập từ command** vào JVM tests, để test so được mong đợi của CI/developer với resource đã filter. Đây là phép thử phát hiện IDE/CLI chọn profile khác.
5. `expectedFlavor=UNSET` là sentinel; nếu không truyền `-DexpectedFlavor=...`, test sẽ fail có chủ đích, tránh build xanh giả.
6. Enforcer `requireJavaVersion [17,18)` yêu cầu Maven JVM chạy Java 17.x; `requireMavenVersion [3.9,4.0)` yêu cầu Maven 3.9.x. Nếu dùng Java 21 cho Maven runtime dù compiler release là 17, demo **cố ý fail** để chứng minh khác biệt.
7. Plugin versions được pin trong POM để IDE/terminal/CI không ngầm chọn các default plugin versions khác nhau.
8. Plugin Enforcer `enforce` mặc định gắn với phase `validate` khi execution không chỉ định phase khác, nên lỗi môi trường xuất hiện sớm trước compile.
9. Chưa dùng Toolchains trong POM demo; nếu cần Maven runtime JDK khác compile JDK, xem phần 18 và điều chỉnh Enforcer policy.
10. Không có repository credentials, absolute paths, môi trường công ty hoặc URLs thật trong POM.

Không coi `${project.version}` hay `${maven.compiler.release}` là biến shell; đây là **Maven model properties** được sử dụng khi Maven xử lý POM/resources.

## 12. Resource được Maven filtering: build-info.properties

Tệp `src/main/resources/build-info.properties`:

```properties
profile=${demo.active.profile}
java.target=${maven.compiler.release}
artifact=${project.groupId}:${project.artifactId}:${project.version}
```

Sau:

```bash
mvn -Plocal -DexpectedFlavor=local clean verify
```

nếu build đúng, file đã được filter nằm tại `target/classes/build-info.properties` và nội dung kỳ vọng:

```properties
profile=local
java.target=17
artifact=dev.parity:env-parity-lab:1.0.0
```

Sau:

```bash
mvn -Pci -DexpectedFlavor=ci clean verify
```

file cùng đường dẫn trong build output có nội dung:

```properties
profile=ci
java.target=17
artifact=dev.parity:env-parity-lab:1.0.0
```

Đây là **hai kết quả dự kiến từ hai lượt build riêng**. Trong thực tế, hãy đọc file sau từng lệnh. Phải có `clean` hoặc chính sách resource processing rõ để tránh đọc output từ lượt trước.

Nếu IDE chỉ chạy native Java compiler mà không thực hiện Maven resources filtering, file có thể còn literal `${demo.active.profile}`. Khi mục tiêu là đối chiếu build Maven, hãy chạy **Maven goal trong IDE**, không dùng native Build Project rồi kết luận filter đã hoạt động.

## 13. Java 17 model đọc resource: BuildInfo.java

Tệp `src/main/java/dev/parity/BuildInfo.java`:

```java
package dev.parity;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public record BuildInfo(
        String profile, String javaTarget, String artifact) {

    public static BuildInfo load() throws IOException {
        try (InputStream input = BuildInfo.class.getResourceAsStream(
                "/build-info.properties")) {
            if (input == null) {
                throw new IOException("Missing build-info.properties");
            }
            Properties properties = new Properties();
            properties.load(input);
            return new BuildInfo(
                    properties.getProperty("profile"),
                    properties.getProperty("java.target"),
                    properties.getProperty("artifact"));
        }
    }
}
```

Đây là một **record Java 17** có constructor/accessors được sinh bởi Java compiler. `Properties.load(InputStream)` phù hợp vì các value được filter trong ví dụ đều dùng ASCII. Nếu resource thật chứa ký tự Unicode ngoài Latin-1, cần lưu đúng encoding và cân nhắc `Reader` với UTF-8 thay vì mặc định của `Properties.load(InputStream)`.

`BuildInfo.load()` không biết IDE hay terminal đã chạy Maven. Nó chỉ đọc **byte resource đã đóng vào classpath**; chính điều này cho phép test phát hiện profile được Maven chọn trong build output.

## 14. Main.java và stdout mong đợi

Tệp `src/main/java/dev/parity/Main.java`:

```java
package dev.parity;

import java.io.IOException;

public final class Main {
    private Main() {
    }

    public static String description() throws IOException {
        BuildInfo info = BuildInfo.load();
        return "Profile=" + info.profile()
                + ";JDK=" + info.javaTarget()
                + ";Artifact=" + info.artifact();
    }

    public static void main(String[] args) throws IOException {
        System.out.println(description());
    }
}
```

Với profile `local`:

```text
Profile=local;JDK=17;Artifact=dev.parity:env-parity-lab:1.0.0
```

Với profile `ci`:

```text
Profile=ci;JDK=17;Artifact=dev.parity:env-parity-lab:1.0.0
```

Đây là stdout **của riêng Java Main**, không phải toàn bộ log Maven. Chuỗi `JDK=17` ở đây là **maven.compiler.release được filter**, không phải bằng chứng runtime `java.home` đang trỏ JDK 17. Chính Enforcer và `mvn -version` kiểm tra thêm JVM chạy Maven.

### 14.1. Chạy Main sau Maven build

Từ project root, sau `mvn ... clean verify`:

```bash
java -cp target/classes dev.parity.Main
```

Dự án chỉ dùng Java standard library khi runtime, nên không cần thêm external JAR vào classpath. Output phụ thuộc profile được chọn ở **lần build gần nhất**. Nếu vừa build `ci`, `java -cp` sẽ đọc `profile=ci`.

Chạy `java -cp` không khởi động Maven, không kích hoạt Maven profile và không tự tạo lại filtered resources. Khi đổi profile, chạy Maven process-resources/build trước rồi mới chạy Main.

## 15. JUnit Jupiter tests kiểm sai profile và cấu hình build

Tệp `src/test/java/dev/parity/BuildInfoTest.java`:

```java
package dev.parity;

import java.io.IOException;
import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BuildInfoTest {

    @Test
    void matchesProfileExpectedByCaller() throws IOException {
        String expected = System.getProperty("expectedFlavor");
        assertNotNull(expected,
                "Pass -DexpectedFlavor=local or -DexpectedFlavor=ci");
        assertTrue(Set.of("local", "ci").contains(expected),
                "A concrete expected profile is required");
        assertEquals(expected, BuildInfo.load().profile());
    }

    @Test
    void recordsJavaTarget() throws IOException {
        assertEquals("17", BuildInfo.load().javaTarget());
    }

    @Test
    void recordsProjectCoordinates() throws IOException {
        assertEquals("dev.parity:env-parity-lab:1.0.0",
                     BuildInfo.load().artifact());
    }
}
```

Tệp `src/test/java/dev/parity/MainTest.java`:

```java
package dev.parity;

import java.io.IOException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {

    @Test
    void describesTheChosenBuildProfile() throws IOException {
        String expected = System.getProperty("expectedFlavor");
        assertEquals(
                "Profile=" + expected
                    + ";JDK=17;Artifact=dev.parity:env-parity-lab:1.0.0",
                Main.description());
    }
}
```

Tổng **4 tests** trên hai test classes:

- `matchesProfileExpectedByCaller`: so profile được Maven filter với kỳ vọng **độc lập** của người gọi.
- `recordsJavaTarget`: resource ghi target 17.
- `recordsProjectCoordinates`: resource có GAV đúng.
- `describesTheChosenBuildProfile`: API output khớp profile kỳ vọng.

Nếu terminal dùng `-Pci -DexpectedFlavor=ci` nhưng IDE dùng `-Plocal -DexpectedFlavor=ci`, test sẽ **fail** vì resource mang `local` còn kỳ vọng là `ci`. Đây là cách biến lỗi profile lệch thành bằng chứng QA rõ ràng.

**Lưu ý với native IDE JUnit runner:** nó có thể không chạy Surefire và không truyền `systemPropertyVariables` từ POM. Muốn kiểm đúng điều kiện trên, chạy **Maven test goal** từ Maven tool window/runner. Native runner cần được cấu hình system property riêng nếu bạn chủ đích muốn đối chiếu thêm.

## 16. Chạy hai profile và xác nhận kết quả

Nếu project đã có Wrapper và dùng JDK 17:

```bash
./mvnw -version
./mvnw -B -Plocal -DexpectedFlavor=local clean verify
./mvnw -B -Pci -DexpectedFlavor=ci clean verify
```

Nếu chưa có Wrapper, trong buổi thực hành có thể dùng `mvn` hệ thống nhưng phải xác nhận version nằm trong `[3.9,4.0)` và JDK nằm trong `[17,18)` để qua Enforcer.

Trên Windows PowerShell:

```powershell
.\mvnw.cmd -version
.\mvnw.cmd -B -Plocal -DexpectedFlavor=local clean verify
if ($LASTEXITCODE -ne 0) { throw 'local verification failed' }
.\mvnw.cmd -B -Pci -DexpectedFlavor=ci clean verify
if ($LASTEXITCODE -ne 0) { throw 'ci verification failed' }
```

Expected test summary trong mỗi lượt:

```text
BuildInfoTest: 3 tests
MainTest:      1 test
----------------------
Total:         4 tests
Failures:      0
Errors:        0
Skipped:       0
```

Output **không** phải log Surefire nguyên văn cố định; xem các file ở:

```text
target/surefire-reports/TEST-dev.parity.BuildInfoTest.xml
target/surefire-reports/TEST-dev.parity.MainTest.xml
```

Vì chạy `clean` trước mỗi profile, report thuộc một lượt hiện tại, giảm nguy cơ file stale. Tổng số lượt test khi chạy **hai command riêng** là 4 + 4, nhưng **mỗi build chỉ có 4 tests**, không phải một Maven run có 8 tests.

### 16.1. Thử lỗi profile không khớp

```bash
./mvnw -B -Plocal -DexpectedFlavor=ci clean test
```

Kỳ vọng `BuildInfoTest.matchesProfileExpectedByCaller` và `MainTest.describesTheChosenBuildProfile` **thất bại có chủ đích**, vì resource `profile=local` khác expected `ci`. Maven phải trả exit code khác 0 nếu Surefire hoạt động đúng.

Không “sửa” test bằng cách bỏ assertion khi muốn kiểm parity. Hãy đổi profile Maven hoặc expected parameter để cả hai phản ánh cùng workflow.

### 16.2. Thử thiếu profile

```bash
./mvnw -B clean test
```

POM mặc định `demo.active.profile=unselected` và `expectedFlavor=UNSET`, nên `matchesProfileExpectedByCaller` fail theo thiết kế. Bài này **cố ý không có default profile** để việc quên `-P` được phát hiện thay vì lặng lẽ chọn một environment ngẫu nhiên.

### 16.3. Thử sai Java/Maven version

Nếu IDE Maven Runner chạy Maven dưới JDK 21 trong khi Enforcer yêu cầu JDK 17, build sẽ fail ở `validate` trước unit tests. Nếu dùng Maven 4 nhưng require Maven `[3.9,4.0)`, cũng fail có chủ đích.

Đây là **policy của demo**, không phải tuyên bố mọi dự án bắt buộc chạy Maven 3.9/Java 17. Đối với một hệ thống cần Maven 4 hoặc JDK 21, cập nhật policy có review và giữ test matrix nhất quán.

## 17. Đối chiếu trong IntelliJ IDEA

IntelliJ có nhiều lựa chọn Maven/JDK không hoàn toàn đồng nhất với Project SDK. Tên menu có thể thay nhẹ theo bản IDEA, nhưng những mục quan trọng thường ở **Settings/Preferences → Build, Execution, Deployment → Build Tools → Maven**.

### 17.1. Chọn đúng Maven home

Trong Maven settings, kiểm **Maven home path**:

- Maven Wrapper từ `.mvn/wrapper/maven-wrapper.properties` (ưu tiên khi project có Wrapper đã kiểm).
- Custom Maven installation đúng version được phê duyệt.
- Bundled Maven chỉ dùng nếu version thực sự phù hợp.

Không dựa vào `mvn -version` ở terminal tích hợp để kết luận Maven home của IDE Maven Runner đúng; đó có thể là Maven lấy từ PATH của shell.

### 17.2. Phân biệt Project SDK / Importer JDK / Maven Runner JRE

Kiểm:

1. **Project SDK** tại Project Structure.
2. **JDK for importer** trong Maven Importing: JDK dùng khi import/resolve Maven project.
3. **JRE của Maven Runner**: JDK dùng khi chạy Maven goals từ IDE.
4. **JRE của Java/Unit Test Run Configuration**: JDK dùng khi chạy native app/test, có thể khác Runner.

Với POM demo, chọn JDK 17 cho **Maven Runner** để qua Enforcer; importer và Project SDK nên được chọn phù hợp cho Java 17; nếu muốn native test so được, Run Configuration cũng chọn Java 17 và property kỳ vọng tương ứng.

### 17.3. Đồng bộ user settings, local repo, Maven config

Trong Maven settings, tìm **User settings file** và **Local repository**. Nếu terminal dùng `-s /path/to/approved-settings.xml` thì IDEA phải dùng cùng file hoặc một file tương đương đã phê duyệt; nếu có local repository override, ghi lại sự khác biệt.

Kiểm tùy chọn **Use settings from `.mvn/maven.config`** nếu bản IDE cung cấp. Không giả định IDE tự dùng mọi lựa chọn `.mvn` giống terminal trong mọi version.

### 17.4. Bật đúng Maven profile và chạy Maven goals

Trong Maven tool window, chọn/tích đúng profile `local` hoặc `ci` (tuỳ phiên bản IntelliJ). Sau đó chạy Maven command bằng Runner có user property:

```text
-Pci -DexpectedFlavor=ci clean verify
```

hoặc:

```text
-Plocal -DexpectedFlavor=local clean verify
```

Đọc console của **Maven Runner**, đối chiếu Maven/Java version, active profiles và Surefire test summary. Nếu IDE bật profile bằng checkbox đồng thời command cũng chỉ định `-P`, tránh vô tình bật hai profile với property cùng tên; để dễ QA, dùng một nguồn điều khiển profile rõ ràng.

### 17.5. Reimport/Reload sau khi thay POM/settings

Sau khi đổi settings, active profiles, dependencies hoặc JDK, yêu cầu IDE **Reload/Reimport Maven Projects** để mô hình dependencies đồng bộ. Đôi khi IDE indexes có trạng thái cũ; không xóa cache IDE ngay khi chưa đối chiếu Maven goals và reimport.

Nếu native IDE Run pass nhưng Maven Runner fail, xem khác biệt runner/profiles/settings trước. Nếu Maven Runner pass nhưng editor vẫn báo lỗi import, kiểm JDK importer, Maven reload và project modules/content roots.

## 18. Eclipse/m2e, VS Code và các IDE khác

Các IDE khác có cùng nhóm điểm cần đồng bộ nhưng tên menu khác:

### 18.1. Eclipse với m2e

- Kiểm Maven Installations: Maven external/wrapper được hỗ trợ hay Maven tích hợp.
- Kiểm Maven User Settings, global settings, local repository và active profiles.
- Kiểm Installed JREs, Project JRE/JDK và Java Compiler compliance.
- Chạy **Maven Build** với `-Plocal/-Pci` và `-DexpectedFlavor` đã chọn, không chỉ Project → Build.
- Dùng **Maven → Update Project** khi POM/profile/settings đã thay.

M2E có lifecycle mappings riêng; một IDE builder không nhất thiết chạy mọi plugin execution y hệt Maven CLI. Khi có khác biệt, ưu tiên tái hiện lỗi bằng cùng Maven goals và JDK.

### 18.2. VS Code với Java/Maven extensions

- Kiểm JDK được Java extension/runtime cấu hình và JDK process thực thi Maven.
- Kiểm Maven executable/Wrapper mà extension sử dụng.
- Kiểm user settings/repository/profiles mà task Maven truyền.
- Chạy Maven goals trong Maven explorer/task với đúng flags.
- Không coi JDK được Java language server dùng là JDK Maven đang chạy nếu chưa xác nhận.

Các key/settings extension có thể đổi theo phiên bản. Dùng documentation của bản extension hiện có và `mvn -version`/Maven logs thay vì hardcode một key không được kiểm.

## 19. Đồng bộ JDK theo Toolchains khi cần tách runtime và compiler

Mẫu POM ở phần 11 **chủ động bắt Maven chạy bằng Java 17** và compile target 17. Có những dự án cần Maven chạy JVM 21 nhưng vẫn compile code bằng JDK 17. Khi ấy, Maven Toolchains là cách chính thức để chọn JDK cho các plugin toolchain-aware.

### 19.1. Khái niệm toolchain

- JVM chạy Maven có thể là một JDK.
- `maven-toolchains-plugin` chọn JDK khác theo requirement được khai báo.
- Compiler Plugin, Surefire và một số plugin khác có khả năng sử dụng selected toolchain, tùy plugin/version và config.
- File user-level `${user.home}/.m2/toolchains.xml` ánh xạ requirements đến `jdkHome` trên từng máy.
- File toolchains **không** tự tạo JDK hoặc xác minh máy đã cài đúng JDK; đường dẫn phải hợp lệ.

### 19.2. POM toolchain fragment

**Đây là phương án THAY THẾ** cho policy JDK runtime quá chặt của POM runnable, không thêm mù vào demo rồi mong Enforcer tiếp tục cho Java 21 chạy Maven.

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

Một file toolchains của developer (thay path thật):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
        </provides>
        <configuration>
            <jdkHome>/path/to/jdk-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

JDK `version` có thể được khai báo theo full patch version như `17.0.x`; dùng version range `[17,18)` trong requirement để phù hợp cả `17` và các bản patch thuộc major 17 theo tài liệu Maven Toolchains. Nếu thêm vendor requirement, nó phải match dữ liệu vendor cung cấp.

### 19.3. Enforcer và Toolchains không phải một cơ chế

POM runnable có:

```xml
<requireJavaVersion>
    <version>[17,18)</version>
</requireJavaVersion>
```

Rule này kiểm **Java chạy Maven**, không thay bằng việc chọn Toolchains. Nếu dự án cho Maven runtime JDK 21 nhưng compile JDK 17, phải **xem lại Enforcer rule**, bảo đảm Compiler/Surefire dùng đúng toolchain và test trên JDK hỗ trợ. Không chỉ thêm toolchain rồi bỏ qua build fail từ Enforcer.

### 19.4. Không lộ đường dẫn cá nhân

`toolchains.xml` chứa absolute JDK home của từng máy, vì vậy thường được quản lý ngoài project. POM chỉ khai báo requirement như Java 17. CI cần cài JDK tương ứng và cấp toolchain hợp lệ; không commit local JDK paths của một developer.

## 20. Cấu hình CI dùng cùng build contract

CI cần dùng cùng nguồn phiên bản và lệnh:

```bash
./mvnw -version
./mvnw -B -Pci -DexpectedFlavor=ci clean verify
```

Nếu chưa tạo Wrapper, dùng Maven 3.9.x đã được CI provision nhưng phải đối chiếu Enforcer và `mvn -version`. CI cần cài JDK 17, không chỉ đặt compiler release.

Một pipeline gồm:

```text
Checkout cùng commit
       |
       v
Cài / chọn JDK 17 theo build policy
       |
       v
Sử dụng Maven Wrapper đã pin
       |
       v
Cấp user settings/mirror/credentials an toàn
       |
       v
./mvnw -version
       |
       v
./mvnw -B -Pci -DexpectedFlavor=ci clean verify
       |
       v
Đọc Surefire XML và expected 4 tests
       |
       v
Lưu artifact/report/provenance theo policy
```

Đừng commit `settings.xml` có password hoặc dùng credentials developer trong CI. Dùng secret management của CI, giới hạn log/debug và không in kết quả `help:effective-settings` chứa thông tin nội bộ nếu không cần.

### 20.1. Đối chiếu bằng chứng giữa terminal/IDE/CI

| Kiểm tra | IDE Maven Runner | Terminal | CI |
| --- | --- | --- | --- |
| Maven distribution | Wrapper | Wrapper | Wrapper |
| Maven runtime JDK | 17 | 17 | 17 |
| Compiler release | 17 | 17 | 17 |
| Profile | `ci` hoặc `local` theo mục tiêu | Cùng profile khi so | `ci` |
| `expectedFlavor` | Cùng profile | Cùng profile | `ci` |
| Plugin versions | Từ POM | Từ POM | Từ POM |
| User settings | File được cấp | File tương đương | Secret-injected file |
| Repository mirror | Theo policy | Theo policy | Theo policy |
| Unit tests | 4 expected | 4 expected | 4 expected |
| Resource `profile` | Khớp profile đã chọn | Khớp | `ci` |

Không cần local repository path giống tuyệt đối trên ba máy. Đối với QA, quan trọng là dependency artifact versions/bytes resolve đúng và repository policy có thể kiểm chứng.

### 20.2. Lưu báo cáo từ cùng build

Surefire reports:

```text
target/surefire-reports/TEST-dev.parity.BuildInfoTest.xml
target/surefire-reports/TEST-dev.parity.MainTest.xml
```

Nếu Maven fail ở Enforcer validate do sai JDK/Maven, **không có test XML mới**. Đừng đánh dấu test pass chỉ vì file cũ tồn tại từ lần run trước. CI phải ghi exit code cùng commit, Maven/JDK/profiles và đọc reports mới tương ứng.

## 21. Khi IDE xanh nhưng terminal đỏ: quy trình điều tra

### Bước 1. Tái hiện cùng một Maven goal

Từ root project, dùng command có cùng profile và expected property:

```bash
./mvnw -B -Pci -DexpectedFlavor=ci clean verify
```

Chạy cùng goal/options từ **IDE Maven Runner**, không chỉ từ IDE terminal hoặc native Build Project.

### Bước 2. So phiên bản

Kiểm `mvn -version`/`mvnw -version` trong môi trường thực. Nếu khác:

- JDK Maven runtime?
- Maven distribution?
- Maven home/global settings?
- Compiler release/toolchain?
- Maven flags như `MAVEN_ARGS`?

### Bước 3. So Maven settings

Kiểm user settings path, mirrors, servers, proxies, local repository và offline. Với effective settings, giữ `showPasswords=false`, rà soát trước khi chia sẻ.

### Bước 4. So active profiles

```bash
./mvnw -B -Pci org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
```

Nếu IDE active hai profiles hoặc một profile settings khác, project properties/repositories có thể bị override.

### Bước 5. So effective POM / resource output

```bash
./mvnw -Pci -B org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

Đọc `target/classes/build-info.properties` sau `clean verify`. Nếu profile ci mà resource là `local`, cần xác định Maven runner đã chọn profile nào hoặc có output stale/IDE-native filtering khác.

### Bước 6. So dependency tree và test runner

Chạy đúng Maven test ở hai ngữ cảnh, so Surefire reports mới, đừng dùng một bên native JUnit và bên kia Surefire rồi xem kết quả là tương đương.

### Bước 7. Sửa nguyên nhân, không chỉ làm mất triệu chứng

Nếu IDE không thấy dependency vì mirror/settings khác, sửa Maven settings/IDE configuration, không bỏ repository security hoặc đổi POM tùy tiện. Nếu JDK Maven khác, sửa Runner JRE hoặc dùng Toolchains theo policy. Nếu chỉ IDE editor lỗi, reload Maven project sau khi terminal build đã chứng minh POM hợp lệ.

## 22. Bảng lỗi thường gặp và cách xử lý

| Triệu chứng | Nguồn lệch thường gặp | Hướng kiểm |
| --- | --- | --- |
| IDE compile Java 17, Maven báo invalid target release | Maven đang chạy JDK cũ | `mvn -version`, Runner JRE, Toolchains |
| Terminal pass, IDE Enforcer fail Java version | Maven Runner dùng JDK 21/11 | Runner JRE; Project SDK không đủ |
| Maven version khác dù cùng POM | IDE bundled Maven, terminal system Maven | Dùng Wrapper và kiểm version thật |
| IDE không tải được dependency | User settings/mirror/proxy/repo khác | Effective settings, offline, logs |
| Lỗi 401/403 repository | Server ID/credentials/quyền khác | Settings file phù hợp, secret manager |
| `PKIX path building failed` | Truststore/JDK/mirror TLS khác | Java home, CA trust, proxy; không tắt TLS |
| IDE báo offline resolution | IDE Maven Offline toggle | Bỏ offline khi cần tải dependency |
| Terminal build dùng artifact cũ | Local `.m2` cache khác | Repo path, selected versions, tree |
| `help:active-profiles` khác | IDE checkbox/Run Config/activation | Cùng `-P`, settings, environment |
| `activeByDefault` tự tắt | Profile khác được bật trong cùng POM | Chọn explicit profile rõ ràng |
| Resource còn `${demo.active.profile}` | Native IDE build chưa chạy Maven filtering | Chạy Maven process-resources/verify |
| Build local nhưng app báo profile ci | `.mvn/maven.config` hoặc MAVEN_ARGS chứa `-Pci` | Xem flags thực, cấu hình IDE |
| Maven run pass, native JUnit test fail | Native runner không có expectedFlavor | Dùng Maven test goal hoặc cấu hình JVM property |
| Surefire không thấy tests | Tên class, config plugin, skip flags | Surefire XML + `failIfNoTests` |
| `UnsupportedClassVersionError` | Runtime JDK thấp hơn compiled bytecode | Runtime Run Configuration/JDK |
| Enforcer fail khi Toolchains chọn JDK 17 | Enforcer kiểm Maven runtime JDK khác | Sửa policy JDK runtime, không chỉ toolchain |
| `.mvn/maven.config` không được áp dụng | IDE import/runner mode không đọc giống launcher | Kiểm IDE option và Maven Runner command |
| Dòng `#` trong `.mvn/jvm.config` làm Maven 3 lỗi | Maven 3 không hỗ trợ comment cú pháp đó | Loại comment trong jvm.config |
| Effective settings khác nhau | Global Maven home/user settings override khác | Maven home, `-s`, `-gs` |
| CI thiếu artifact dù IDE có | CI clean repo, mạng/repository policy khác | POM dependency, mirror and credentials |
| Bấm Build Project xanh nhưng `mvn verify` đỏ | Native IDE builder không chạy Maven lifecycle | Dùng Maven verify làm build gate |
| `0 tests` nhưng build xanh | Skip/no tests discovered | `failIfNoTests`, số test tối thiểu |
| Thay JDK env nhưng IDE không thấy | IDE process chưa nhận environment mới | Relaunch IDE hoặc chỉnh Runner JRE |
| Parent POM khác | `-f`/root module/settings khác | Cùng project root, effective POM |
| `-Pci` nhưng test local | Multiple active profiles ghi đè property | Active profiles + resource + effective POM |

### 22.1. Không sửa lỗi bằng cách xóa cache bừa

Xóa `.idea`, workspace metadata, `.m2` hoặc cache toàn hệ thống có thể làm tốn thời gian và xóa dữ liệu không liên quan. Thứ tự tốt hơn là:

1. So command/JDK/Maven.
2. So active profiles/settings.
3. Kiểm dependency tree và resource output.
4. Reload Maven project.
5. Chỉ dọn cache hoặc output cụ thể khi có bằng chứng stale và quyền phù hợp.

Một lỗi TLS/credentials sẽ không được sửa bằng cách xóa hàng nghìn dependency JAR.

## 23. Phân biệt build parity và environment parity hoàn toàn

Không cần toàn bộ môi trường IDE, terminal và CI **giống tuyệt đối**. Chúng có thể có:

- `JAVA_HOME` nằm ở ba đường dẫn khác nhau nhưng đều trỏ JDK 17 được phê duyệt.
- `user.home` khác nhau và local Maven repo khác nhau.
- Credential files khác nhau nhưng có cùng quyền repository.
- Proxy khác nhau tùy mạng nội bộ/CI.
- `MAVEN_OPTS` khác nhau về heap khi phù hợp memory budget.
- IDE dùng indexer/language server riêng mà không ảnh hưởng Maven artifact.

Điều cần tương thích là:

1. Maven core version theo policy.
2. JVM Maven/Compiler/Test/Runtime đáp ứng JDK constraints.
3. Project/parent/plugin/dependency versions được resolve đúng.
4. Profiles và user properties đúng với intended target.
5. Effective POM và filtered resources cùng meaning.
6. Surefire tests và output artifacts đạt chuẩn.
7. Repository/security settings hợp lệ, không dựa vào cache ngẫu nhiên.

Vì vậy không buộc copy file `settings.xml` có secrets từ máy một người sang máy khác. Dùng cấu hình độc lập phù hợp môi trường và so những **kết quả hiệu lực** quan trọng.

## 24. Câu hỏi tự kiểm tra

**1. `java -version` báo 17 thì Maven có chắc chạy Java 17 không?**

Không. Maven launcher có thể dùng `JAVA_HOME` hoặc JDK runner riêng của IDE. Kiểm `mvn -version` trong môi trường thực.

**2. `maven.compiler.release=17` có tự cài JDK 17 không?**

Không. Nó quy định target của compiler, không cung cấp JDK cho Maven hoặc JVM chạy ứng dụng.

**3. Maven Wrapper có đồng bộ Maven và Java bằng một lệnh duy nhất không?**

Wrapper giúp pin Maven distribution; JDK, settings, profiles và credentials vẫn cần được cấu hình/kiểm chứng riêng.

**4. Vì sao IDE terminal PASS nhưng Maven Runner IDE FAIL?**

Terminal tích hợp và Maven Runner có thể dùng Maven binary, JDK, user settings và active profiles khác nhau.

**5. `dependencyManagement` trong POM hoặc profiles có tự đưa dependency vào classpath không?**

Không. Management quản lý metadata/version; cần actual `<dependencies>` phù hợp. Profile có thể thêm dependency khi được kích hoạt, vì vậy effective POM của profile cần được xem.

**6. `.mvn/jvm.config` nên chứa `-Pci` không?**

Không. `-Pci` là Maven CLI option, thuộc `.mvn/maven.config` hoặc command runner; `.mvn/jvm.config` chứa JVM startup options.

**7. `-Plocal -DexpectedFlavor=ci clean test` trong demo sẽ thế nào?**

Tests kiểm profile cố ý fail, vì build resource mang `local` còn expected property là `ci`.

**8. Có nên cho `activeByDefault` chọn CI profile ngầm không?**

Không nên nếu mục tiêu là parity rõ ràng; nó có thể bị vô hiệu khi profile khác trong cùng POM được kích hoạt. Lệnh CI nên dùng `-Pci` tường minh.

**9. `help:effective-settings` an toàn để đăng nguyên văn công khai không?**

Không mặc nhiên. Passwords mặc định được che, nhưng URL/username/đường dẫn/cấu hình nội bộ có thể nhạy cảm. Rà soát trước khi chia sẻ.

**10. Enforcer requireJavaVersion và Toolchains có giống nhau không?**

Không. Enforcer rule kiểm JVM đang chạy Maven; Toolchains có thể chọn JDK cho các plugin hỗ trợ. Cần thiết kế cả hai theo policy.

## 25. Checklist đồng bộ trước khi merge

- [ ] IDE Maven Runner, terminal và CI chạy cùng Maven goals/flags khi so sánh?
- [ ] `mvnw -version` xác nhận Maven distribution và Java home phù hợp?
- [ ] `java -version`, `javac -version` và `mvn -version` được phân biệt?
- [ ] Project SDK, Importer JDK, Maven Runner JRE và Run Configuration JRE được kiểm riêng?
- [ ] Compiler `release`, test runtime JDK, Enforcer/Toolchains policy thống nhất?
- [ ] Maven Wrapper được pin/commit và IDE thật sự chọn Wrapper?
- [ ] User/global settings, mirrors, proxies và local repo được xác nhận?
- [ ] `-s`/`-gs`/`maven.repo.local` overrides không bị quên ở một môi trường?
- [ ] Không đưa credentials, truststore passwords hoặc tokens vào POM/logs?
- [ ] Profiles POM/settings active đúng, không có `activeByDefault` hoặc env activation bất ngờ?
- [ ] `.mvn/maven.config` và `.mvn/jvm.config` chứa đúng loại options?
- [ ] Không có MAVEN_ARGS/MAVEN_OPTS/environment khác gây thay đổi build ngầm?
- [ ] `help:active-profiles` và effective POM được đối chiếu trên từng Maven runner?
- [ ] Resources được Maven filter đúng profile, không đọc output stale?
- [ ] Surefire tests chạy đủ bốn cases, errors/failures/skipped bằng 0 trong demo?
- [ ] Khi native IDE test khác Maven Surefire, đã xác định runner và system properties?
- [ ] CI build từ cùng commit với JDK/Maven/toolchain được duyệt?
- [ ] Logs/reports lưu provenance cần thiết nhưng không làm lộ thông tin nội bộ?
- [ ] Không kết luận “parity hoàn toàn” chỉ dựa vào một nhãn BUILD SUCCESS?
- [ ] Nếu môi trường khác nhau hợp lệ, đã ghi rõ constraints và lý do?

**Kết luận:** đồng bộ Maven giữa IDE với terminal không chỉ là chọn Java 17 trong Project SDK. Cần so chính xác **JDK chạy Maven, compiler/test runtime JDK, Maven binary/Wrapper, user/global settings, local repository, profiles và CLI/JVM options**. Dùng `mvn -version`, Help Plugin, effective POM/settings, Maven profile chọn tường minh và một test kiểm resource filtering để phát hiện build lệch. Khi IDE Maven Runner, terminal và CI đều dùng **cùng build contract** và QA chạy thật, kết quả mới có thể tái lập.

### Tài liệu tham khảo

- [Apache Maven — Configuring Maven](https://maven.apache.org/configure.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Apache Maven Help Plugin — active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html)
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Help Plugin — effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Apache Maven Compiler Plugin — Setting the -source and -target](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-source-and-target.html)
- [Apache Maven Surefire Plugin — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Apache Maven Enforcer Plugin — Built-in Rules](https://maven.apache.org/enforcer/enforcer-rules/)
- [IntelliJ IDEA — Maven](https://www.jetbrains.com/help/idea/maven.html)
- [IntelliJ IDEA — Maven Run/Debug Configuration](https://www.jetbrains.com/help/idea/run-debug-configuration-maven.html)
