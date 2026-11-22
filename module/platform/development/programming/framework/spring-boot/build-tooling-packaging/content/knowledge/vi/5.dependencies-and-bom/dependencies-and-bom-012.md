# Cấu hình kho Maven, mirror, proxy và thông tin xác thực trong Spring Boot

## 1. Bức tranh tổng thể: thư viện được tìm ở đâu và kết nối đi như thế nào?

Một dự án Spring Boot dùng Maven phải tải nhiều loại artifact: parent POM, Spring Boot BOM, các starter, thư viện bắc cầu (*transitive dependencies*) và Maven plugins như compiler, surefire, resources hay `spring-boot-maven-plugin`. Nếu một trong những thành phần đó không truy cập được, `mvn package` có thể thất bại dù mã Java hoàn toàn đúng.

Bốn thành phần cần phân biệt:

- **Remote Maven repository (kho từ xa)** lưu POM, JAR, metadata và plugin theo tọa độ `groupId:artifactId:version`. Maven Central và Nexus/Artifactory nội bộ là những ví dụ.
- **Local repository** là bộ nhớ đệm artifact trên máy build, mặc định `~/.m2/repository`. Nó giúp không cần tải lại, nhưng không phải một máy chủ mirror.
- **Mirror** thay địa chỉ remote repository Maven sẽ kết nối. Chẳng hạn mọi lần tải từ ID `central` được chuyển sang endpoint của repository manager nội bộ.
- **Network proxy** là máy chủ trung gian cho kết nối mạng. Nó quyết định đường đi đến repository, trong khi mirror quyết định repository đích. Có thể dùng cả hai, một hoặc không cần thành phần nào.

Thông tin xác thực cũng có hai phạm vi: **repository credentials** cho kho artifact và **proxy credentials** cho proxy mạng. Khi gặp HTTP 401, 403 hoặc 407 cần xác định bên nào đang từ chối.

```text
pom.xml: dependency / parent / plugin / BOM
           |
           v
      Maven Resolver
           |
           +--> local cache (~/.m2/repository)
           |
           +--> logical repository (central, private, vendor)
                      |
                      +--> settings.xml: chọn mirror theo mirrorOf
                      |
                      +--> settings.xml: lấy server credentials theo ID
                      |
                      +--> settings.xml: proxy / nonProxyHosts
                                        |
                                        v
                              Repository manager / Internet
```

**BOM không chỉ ra nơi tải artifact.** Maven BOM và `spring-boot-starter-parent` chủ yếu giúp quản lý phiên bản; repository/mirror/network/credentials mới quyết định có thể tải POM và JAR tương ứng hay không.

## 2. Đặt cấu hình đúng nơi

| Vị trí | Nội dung phù hợp | Có commit vào Git? |
| --- | --- | --- |
| `pom.xml` | Dependency, plugin, version, repository cần cho project, `distributionManagement` | Có, nhưng tuyệt đối không đặt token/password |
| `~/.m2/settings.xml` | Mirror, proxy, server credentials, profile của máy dev/CI | Không; đây là cấu hình riêng, có thể chứa secret |
| `${maven.home}/conf/settings.xml` | Global settings của bản Maven cài đặt | Thường do hệ thống quản lý |
| `~/.m2/repository` | Cache artifact/POM/metadata đã tải | Không; không chỉnh trực tiếp để cấu hình mirror |
| `.mvn/maven.config` | Lựa chọn command-line Maven chung của dự án | Có thể, nếu không có secret |
| Settings do CI cấp qua `mvn -s <path>` | Tài khoản và routing của build agent | Giữ ngoài source control, quyền tối thiểu |

Maven hợp nhất global và user settings, trong đó user settings có ưu tiên cao hơn với các mục trùng tương ứng. Tham số `-s` dùng một user settings file chỉ định, còn `-gs` chọn global settings. Maven Wrapper `./mvnw` thường giúp cố định phiên bản Maven phù hợp với repository.

**Nguyên tắc:** POM mô tả yêu cầu build chung; settings mô tả môi trường mạng và quyền truy cập; secret do người dùng hoặc CI cung cấp riêng. Đừng “sửa” lỗi tải dependency bằng cách đưa username/password trực tiếp vào `pom.xml` hoặc URL repository trong Git.

## 3. Remote repository và cách Maven phân giải artifact

Với `org.springframework.boot:spring-boot-starter-web:3.5.0`, Maven repository theo bố cục chuẩn có dạng:

```text
org/springframework/boot/spring-boot-starter-web/3.5.0/
  spring-boot-starter-web-3.5.0.pom
  spring-boot-starter-web-3.5.0.jar
```

Maven cần POM để xác định dependency tiếp theo và có thể cần `maven-metadata.xml` với một số kiểu version/snapshot. **BOM có packaging `pom`**; việc thiếu file JAR của BOM không phải vấn đề. Maven tải plugin từ plugin repositories, có thể khác dependency repositories.

Maven Central thường có sẵn qua Super POM. Chỉ thêm repository riêng khi artifact hoặc plugin thực sự không có ở nguồn được cho phép.

### 3.1. Dependency repository trong `pom.xml`

Ví dụ thêm kho vendor, với URL **minh họa, không tồn tại**:

```xml
<repositories>
    <repository>
        <id>vendor-releases</id>
        <url>https://repo.vendor.example/releases</url>
        <releases><enabled>true</enabled></releases>
        <snapshots><enabled>false</enabled></snapshots>
    </repository>
</repositories>
```

`<id>vendor-releases</id>` là tên logic dùng trong Maven. Nếu repository cần xác thực mà **không có mirror**, `<server><id>vendor-releases</id>` trong settings phải khớp ID này. Nếu có mirror, ID dùng cho credentials thường là ID **mirror đã chọn**.

Snapshot và release là hai policy quan trọng: kho chỉ chứa release không tự phục vụ `1.0.0-SNAPSHOT`. Khi dự án dùng các dependency không cố định hoặc snapshot, metadata/cache policy ảnh hưởng kết quả resolve.

### 3.2. Plugin repository là cấu hình riêng

```xml
<pluginRepositories>
    <pluginRepository>
        <id>vendor-plugins</id>
        <url>https://repo.vendor.example/plugins</url>
    </pluginRepository>
</pluginRepositories>
```

`<repositories>` là nơi tìm dependency. `<pluginRepositories>` là nơi tìm build plugins và các plugin dependency. Nếu Maven tải được Spring Boot starter nhưng không tải được `spring-boot-maven-plugin` hoặc `maven-surefire-plugin`, kiểm tra plugin repository/mirror. Quy tắc mirror có thể áp dụng cho cả dependency và plugin repositories.

### 3.3. Repository qua settings profile

Có thể dùng settings profile trên máy dev/CI khi kho không cần đưa vào POM dự án:

```xml
<profiles>
    <profile>
        <id>internal-releases</id>
        <repositories>
            <repository>
                <id>team-releases</id>
                <url>https://repo.example.org/repository/team-releases/</url>
                <releases><enabled>true</enabled></releases>
                <snapshots><enabled>false</enabled></snapshots>
            </repository>
        </repositories>
    </profile>
</profiles>
<activeProfiles>
    <activeProfile>internal-releases</activeProfile>
</activeProfiles>
```

Đây là đoạn **bên trong phần tử `<settings>`**, không phải file XML hoàn chỉnh. Có thể kích hoạt profile đã tồn tại bằng `mvn -Pinternal-releases package`. Nhưng nếu đang có mirror `external:*` hoặc `*`, repository `team-releases` có thể tiếp tục bị chuyển sang mirror. Để truy cập riêng phải thiết kế mirror exclusion hoặc cho repository manager gộp cả nguồn nội bộ.

## 4. Mirror trong Maven: ý nghĩa và thứ tự lựa chọn

Mirror được khai báo trong `settings.xml`:

```xml
<mirrors>
    <mirror>
        <id>corp-central</id>
        <name>Central via company cache</name>
        <url>https://repo.example.org/repository/maven-central/</url>
        <mirrorOf>central</mirrorOf>
    </mirror>
</mirrors>
```

`mirrorOf=central` chỉ thay repository có ID `central`, không tự thay `vendor-releases` hoặc `team-releases`. Đây là mapping từ **repository ID gốc** sang **mirror có ID/URL mới**.

| Giá trị `mirrorOf` | Hành vi |
| --- | --- |
| `central` | Chỉ repository có ID `central` |
| `*` | Mọi repository; yêu cầu mirror phục vụ/proxy được tất cả artifact cần thiết |
| `external:*` | Repository từ xa, trừ localhost và repo dạng `file:` |
| `external:http:*` | Repository HTTP bên ngoài, trừ localhost (Maven 3.8+) |
| `central,vendor-releases` | Hai ID liệt kê |
| `*,!team-releases` | Tất cả ngoại trừ ID `team-releases` |
| `external:*,!team-releases` | Các repo bên ngoài, trừ `team-releases` |

Khi có nhiều mirror, Maven ưu tiên mirror có `mirrorOf` khớp chính xác ID gốc, sau đó mới xét các biểu thức nâng cao theo thứ tự khai báo. Tránh khoảng trắng không chủ đích trong danh sách pattern vì cú pháp phân tích của Maven có các quy tắc chặt chẽ.

**Một repository không được Maven đồng thời ghép nhiều mirror để tìm artifact.** Nếu cần kết hợp Maven Central, kho release/snapshot nội bộ và kho vendor, nên sử dụng một repository manager (group/virtual repo) có thể proxy hoặc host tất cả nguồn cần thiết. Đặt nhiều mirror cùng `mirrorOf=*` không tạo chế độ fallback đáng tin cậy.

Chọn `external:*` khi muốn giữ repo file/localhost dùng cho development; chọn `*` khi mọi nguồn, kể cả các repo riêng, phải đi qua một endpoint quản trị. Repo manager phía sau phải có **cả plugin và POM/BOM**, nếu không lỗi resolution sẽ xuất hiện sớm.

## 5. Mẫu `~/.m2/settings.xml` đầy đủ: mirror, credentials và proxy

Ví dụ dưới đây giả định môi trường có repository manager qua HTTPS, token tài khoản riêng và một proxy mạng tùy chọn. **Toàn bộ `example.org` là URL minh họa**; cần thay bằng endpoint thực tế. Nếu không cần proxy thì bỏ toàn bộ block `<proxies>`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>corp-maven</id>
            <name>Corporate Maven repository manager</name>
            <url>https://repo.example.org/repository/maven-public/</url>
            <mirrorOf>external:*</mirrorOf>
        </mirror>
    </mirrors>

    <servers>
        <server>
            <id>corp-maven</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>

    <proxies>
        <proxy>
            <id>corp-egress</id>
            <active>true</active>
            <protocol>http</protocol>
            <host>proxy.example.org</host>
            <port>8080</port>
            <nonProxyHosts>*.example.org|localhost|127.0.0.1</nonProxyHosts>
        </proxy>
    </proxies>
</settings>
```

Cách hoạt động của ví dụ: Maven cần artifact từ `central`; `external:*` khớp và chuyển request sang `corp-maven`; Maven tìm `<server id="corp-maven">` để lấy username/token; vì hostname `repo.example.org` khớp `*.example.org` trong `nonProxyHosts` nên không dùng proxy cho URL này.

### 5.1. Khai báo secret qua biến môi trường

Maven settings hỗ trợ nội suy các biểu thức `${env.MAVEN_REPO_USER}` và `${env.MAVEN_REPO_TOKEN}`. Các biến phải được đặt trước khi Maven chạy, ví dụ trên Linux/macOS:

```bash
export MAVEN_REPO_USER="build-user"
# MAVEN_REPO_TOKEN cần do secret manager/CI cấp an toàn.
mvn -B -ntp verify
```

PowerShell minh họa việc đặt **username**, còn token lấy từ cơ chế quản lý secret của tổ chức:

```powershell
$env:MAVEN_REPO_USER = "build-user"
mvn -B -ntp verify
```

Không copy token thật vào script commit, command line hay shell history. Nếu CI inject token từ secret store, đảm bảo secret chỉ được cấp ở job cần dùng và không bị echo/log. Maven có cơ chế mã hóa password riêng theo phiên bản (Maven 3 và Maven 4 có khác biệt); khi dùng phải xem đúng hướng dẫn của phiên bản. Dù mã hóa, vẫn bảo vệ file settings và master secret.

### 5.2. Tại sao ID phải khớp?

`<server><id>corp-maven</id>` **khớp mirror ID**, không phải repository gốc `central`. Nếu đổi mirror thành `company-group` nhưng để server ID `corp-maven`, Maven có thể không gửi đúng credentials rồi nhận 401. Với repo riêng không bị mirror, server ID phải khớp repository ID đang kết nối.

Đừng đặt thông tin xác thực chung trên một mirror quá rộng nếu không phù hợp chính sách quyền. Nên dùng tài khoản đọc artifact giới hạn phạm vi; quyền publish nên cấp riêng.

## 6. Proxy trong Maven và lỗi xác thực proxy

Proxy không lưu artifact như repository manager; nó chuyển tiếp request qua mạng. Nếu tổ chức buộc đi Internet qua proxy, cấu hình proxy trong Maven `settings.xml`:

```xml
<proxies>
    <proxy>
        <id>corp-egress</id>
        <active>true</active>
        <protocol>http</protocol>
        <host>proxy.example.org</host>
        <port>8080</port>
        <username>${env.MAVEN_PROXY_USER}</username>
        <password>${env.MAVEN_PROXY_TOKEN}</password>
        <nonProxyHosts>*.example.org|localhost|127.0.0.1</nonProxyHosts>
    </proxy>
</proxies>
```

Đây là **đoạn thay thế block `<proxies>`** trong settings mẫu, không dán thành block thứ hai. Khi proxy không cần đăng nhập, bỏ `username/password`. Giao thức proxy có thể là `http` trong khi URL repository dùng `https`: HTTP proxy vẫn có thể mở tunnel TLS bằng CONNECT; cần đối chiếu hạ tầng thực tế.

**`nonProxyHosts` rất quan trọng:** nếu repo nội bộ có thể truy cập trực tiếp, tránh đưa kết nối đến nó qua proxy Internet. Pattern `*.example.org|localhost|127.0.0.1` là ví dụ, phải sửa theo DNS nội bộ. Một số hệ thống sử dụng proxy/PAC ở browser, nhưng JVM/Maven chạy khác nên không tự kế thừa mọi cài đặt trình duyệt.

| Mã/triệu chứng | Ý nghĩa khả dĩ | Hướng giải quyết |
| --- | --- | --- |
| HTTP 401 | Repository từ chối credentials hoặc token hết hạn | Kiểm tra server ID sau mirror, token và quyền đọc |
| HTTP 403 | Đã xác thực nhưng không có quyền hoặc bị policy chặn | Kiểm tra permission/repository path, policy nhóm release/snapshot |
| HTTP 407 | **Proxy** yêu cầu xác thực | Kiểm tra proxy user/token và nonProxyHosts |
| `Connect timed out` | Mạng, firewall, proxy, VPN hoặc host/port sai | Xác nhận DNS và đường đi từ máy chạy build |
| `UnknownHostException` | Host không resolve qua DNS | Kiểm tra repository URL và DNS/proxy |
| `PKIX path building failed` | JVM không tin chuỗi chứng chỉ TLS | Cài CA/trust store đúng chính sách, dùng JDK phù hợp |
| HTTP 404 | Artifact/version không tồn tại, sai repo/group hoặc mirror thiếu upstream | Đối chiếu tọa độ, URL, snapshot/release và repository manager |
| `Non-resolvable parent POM` | Maven không tải được parent | Kiểm tra parent, mirror, credentials và cache |
| `Non-resolvable import POM` | Maven không tải được BOM | Kiểm tra BOM, repository, release policy, proxy |
| `PluginResolutionException` | Không tải được plugin | Kiểm tra plugin repository, mirror và quyền |

**Không tắt xác minh TLS** để vượt lỗi `PKIX`. Với proxy doanh nghiệp có HTTPS inspection, cần cấu hình đúng corporate CA và Java trust store đang sử dụng. HTTP 407 và 401 có bản chất khác nhau: xác thực proxy không sửa được bằng cách đổi `<servers>` của repository.

## 7. Đọc dependency và publish artifact là hai chiều riêng biệt

Tải dependency xảy ra trong quá trình resolve và có thể dùng mirror; triển khai artifact Maven (`mvn deploy`) thường sử dụng `distributionManagement`:

```xml
<distributionManagement>
    <repository>
        <id>team-releases</id>
        <url>https://repo.example.org/repository/team-releases/</url>
    </repository>
    <snapshotRepository>
        <id>team-snapshots</id>
        <url>https://repo.example.org/repository/team-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

Đây là **đoạn `pom.xml`**. Để deploy, `settings.xml` phải có credentials trùng ID `team-releases` và `team-snapshots`, trừ khi dùng cơ chế tương đương được phiên bản Maven hỗ trợ. **Server ID `corp-maven` dùng để tải từ mirror không tự đảm bảo deploy được**, vì đích upload dùng ID khác.

Maven `mvn package` tạo archive; `mvn deploy` đưa artifact Maven lên repository có cấu hình phù hợp. OCI image và container registry dùng cơ chế publish khác (ví dụ `docker push` hoặc plugin riêng); Maven repository mirror không biến thành container registry.

## 8. Spring Boot parent, BOM và liên hệ repository

Một project Maven đơn giản minh họa Spring Boot 3.5.0, Java 17:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>repository-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là POM minh họa **dependency resolution**; chưa có class `main`/`@SpringBootApplication` nên không được coi là ứng dụng đã chạy HTTP server. Phiên bản 3.5.0 được cố định cho ví dụ, không ngụ ý là bản Spring Boot mới nhất.

Trong build này, Maven phải tải parent POM, transitives của starter, plugin mặc định và Boot Maven plugin. Nếu mirror chỉ có JAR nội bộ nhưng không proxy Central/Plugin, resolution sẽ lỗi. Nếu parent POM không resolve được, Maven có thể thất bại ngay **trước** khi chạy compiler hoặc test.

### Nếu import BOM mà không dùng Spring Boot parent

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là đoạn trong POM, không phải file hoàn chỉnh. BOM kiểm soát phiên bản dependency được quản lý, nhưng **không cung cấp toàn bộ cấu hình plugin mặc định giống `spring-boot-starter-parent`**. Kể cả đã import BOM, phải tải được artifact `spring-boot-dependencies:3.5.0:pom` từ repository được chọn.

## 9. Công cụ và quy trình kiểm tra Maven

### 9.1. Những lệnh cơ bản

```bash
mvn -version
mvn help:effective-settings
mvn help:active-profiles
mvn help:effective-pom
mvn -U -B -ntp dependency:tree
```

Ý nghĩa:

- `mvn -version` cho biết phiên bản Maven, Java và đường chạy JVM.
- `help:effective-settings` cho thấy cấu hình đã ghép từ user/global settings (mirror/proxy/profiles), nhưng output có thể nhạy cảm: **chỉ xem trong môi trường được phép, không dán công khai**.
- `help:active-profiles` liệt kê profile đang bật.
- `help:effective-pom` kiểm tra parent, dependency management, repository và plugin đã được kế thừa.
- `-U` yêu cầu kiểm tra lại artifact/metadata liên quan (đặc biệt snapshot hoặc kết quả truy xuất thiếu đã cache); `-B` chạy batch, `-ntp` tắt progress transfer log; `dependency:tree` hiển thị cây dependency.

Lưu ý: các goal `help:*` và `dependency:tree` là Maven plugins, nên **chính chúng cũng cần resolve từ repository** nếu cache chưa có. Khi môi trường mất mạng hoàn toàn, lỗi Help Plugin không chứng minh không tồn tại file settings.

Có thể chỉ định settings file CI cụ thể:

```bash
mvn -s /path/to/ci-settings.xml -B -ntp verify
```

Đường dẫn trên là ví dụ; Windows dùng đường dẫn Windows phù hợp. Xác minh file thực sự tồn tại và đã được nạp, đặc biệt khi máy dev chạy được nhưng build agent không có `~/.m2/settings.xml`.

### 9.2. Điều tra một lỗi resolution

1. Xác định **artifact cụ thể** gây lỗi: parent POM, BOM, dependency hay Maven plugin; đọc `groupId/artifactId/version` và URL báo lỗi.
2. Kiểm tra **effective settings** và `mirrorOf` để biết Maven thực sự đã chọn endpoint nào. Nhìn POM một mình chưa đủ.
3. Kiểm tra **ID xác thực**: server phải khớp mirror ID được chọn; deploy dùng `distributionManagement.repository.id`.
4. Xác minh **mạng** từ chính máy/agent chạy Maven: DNS, VPN, proxy, nonProxyHosts, trust store JVM. Browser trên máy khác truy cập được không chứng minh CI đi được.
5. Xác minh **repository manager** có được cấu hình proxy nhóm artifact cần tải hay không, quyền read, release/snapshot policy và token còn hiệu lực.
6. Nếu hệ thống đã sửa nhưng Maven vẫn ghi lỗi “was cached ... resolution will not be reattempted”, thử `mvn -U ...`. Không vội xóa toàn bộ `~/.m2/repository` gây tải lại lớn mà không chữa đúng nguyên nhân.
7. Khi cần `-X` để debug, **ẩn credentials, header và URL nhạy cảm** trước khi gửi log.

`mvn -o package` chỉ chạy offline khi mọi artifact/POM/plugin cần thiết đã ở local cache; offline PASS không chứng minh kết nối repository hiện tại hoạt động.

## 10. Dùng Gradle để tải Maven artifacts: cấu hình nào khác?

Gradle hỗ trợ Maven repositories nhưng có cấu hình riêng. Trong project Gradle, dependency repositories và plugin repositories được tách:

- `repositories` hoặc `dependencyResolutionManagement.repositories`: nơi tải thư viện Java, Spring Boot starters, BOM...
- `pluginManagement.repositories`: nơi resolve Gradle plugins, gồm plugin marker; cấu hình ở `settings.gradle(.kts)`.
- `gradle.properties` / JVM system properties: cấu hình proxy, secret và các lựa chọn Gradle.

**Lưu ý phiên bản:** từ **Gradle 9.8.0**, một tính năng incubating có thể reuse Maven mirror settings khi bật riêng `org.gradle.mirror.maven.settings=true`. Mặc định Gradle **không** tự áp dụng Maven `settings.xml`; kể cả bật tính năng này thì Maven proxy/profile không được nhập. Xem mục 10.4.

### 10.1. Ví dụ Gradle Kotlin DSL với hai Maven repositories nội bộ

**`settings.gradle.kts`:**

```kotlin
pluginManagement {
    repositories {
        maven {
            name = "corpPlugins"
            url = uri("https://repo.example.org/repository/gradle-plugins/")
            credentials(PasswordCredentials::class)
        }
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        maven {
            name = "corpMaven"
            url = uri("https://repo.example.org/repository/maven-public/")
            credentials(PasswordCredentials::class)
        }
    }
}

rootProject.name = "spring-build-demo"
```

**`build.gradle.kts` để thử dependency resolution:**

```kotlin
plugins {
    java
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Hai file này không biên dịch ứng dụng Spring Boot đầy đủ; chúng minh họa cấu hình repository và resolve một dependency Java. Sau khi thay URL và cung cấp credential thật, chạy:

```bash
./gradlew dependencies --configuration compileClasspath
```

Trên Windows dùng `gradlew.bat`. Kho `corpPlugins` cần proxy các **Gradle plugin markers** (ví dụ Spring Boot Gradle plugin); nếu không thì thêm repository plugin được cho phép. Kho `corpMaven` phải cung cấp dependency thường. Nếu kho không cần auth, bỏ `credentials(...)`.

`RepositoriesMode.FAIL_ON_PROJECT_REPOS` buộc khai báo kho ở settings, phù hợp chính sách tập trung; khi dùng mode này, đừng thêm `repositories` ở `build.gradle.kts` vì sẽ gây lỗi. Nếu project cần phép khai báo repo riêng, chọn mode tương ứng một cách có chủ đích.

### 10.2. Credentials của Gradle: externalized properties

Với tên repository `corpMaven` và `corpPlugins`, `credentials(PasswordCredentials::class)` tìm các property theo quy ước:

```properties
# ~/.gradle/gradle.properties - user-specific, KHÔNG commit
corpMavenUsername=your-service-account
corpMavenPassword=token-from-secret-store
corpPluginsUsername=your-service-account
corpPluginsPassword=token-from-secret-store
```

Giá trị trên là **placeholder**, không được dùng nguyên trạng trong production. Trong CI có thể cấp tương đương qua biến môi trường `ORG_GRADLE_PROJECT_corpMavenUsername` và `ORG_GRADLE_PROJECT_corpMavenPassword` từ secret manager. Không in token ra console. Khi repository nhận token qua HTTP header thay vì basic authentication, dùng cơ chế `HttpHeaderCredentials`/authentication phù hợp theo tài liệu Gradle, vẫn externalize bí mật.

### 10.3. Proxy của Gradle là JVM system properties

**`~/.gradle/gradle.properties`**, ví dụ:

```properties
systemProp.http.proxyHost=proxy.example.org
systemProp.http.proxyPort=8080
systemProp.https.proxyHost=proxy.example.org
systemProp.https.proxyPort=8080
systemProp.http.nonProxyHosts=*.example.org|localhost|127.0.0.1
```

Chú ý `http.nonProxyHosts` cũng là tên property JVM thường dùng cho các host loại trừ khi xử lý HTTPS. Để proxy có authentication, cấp `systemProp.http.proxyUser` / `systemProp.http.proxyPassword` hoặc các giá trị HTTPS liên quan qua user/CI configuration được bảo vệ; tránh commit chúng vào project `gradle.properties`. Gradle **không đọc phần `<proxies>` của Maven settings** để thay cho cấu hình này.

### 10.4. Tính năng Gradle mới: reuse Maven mirror settings

Gradle **9.8.0 trở lên** có hỗ trợ đang thử nghiệm, **tắt theo mặc định**. Khi tổ chức đã có mirror Maven và muốn dùng chung, thêm vào user-level `~/.gradle/gradle.properties`:

```properties
org.gradle.mirror.maven.settings=true
```

Khi bật, Gradle đọc các quy tắc `<mirrors>` và `<servers>` tương ứng trong Maven settings, áp dụng `mirrorOf` với HTTP/HTTPS Maven repositories; **không** thay file repository, Ivy, S3/GCS. Gradle dùng repository **name** để khớp Maven repository ID (có xử lý riêng cho Central). Gradle Plugin Portal cũng có thể bị chuyển nếu match rule trúng, nên kho nội bộ cần chứa/được proxy plugin marker artifacts.

Tính năng đó **không áp dụng Maven proxies, profiles hay pluginGroups** và không tự thay đổi publishing destination. Một số định dạng password encryption mới của Maven 4 chưa được hỗ trợ theo tài liệu của tính năng, nên phải kiểm tra đúng phiên bản Gradle/Maven. Nếu Gradle Wrapper cũ hoặc không bật flag, dùng cách khai báo `pluginManagement`/`dependencyResolutionManagement` ở mục 10.1.

Vì đây là tính năng mới, khi sửa lỗi nên kiểm tra Gradle Wrapper version và tài liệu của version đó, không mặc định mọi dự án Gradle đều đọc Maven `settings.xml`.

## 11. Bốn tình huống cấu hình phổ biến

### Máy dev truy cập Maven Central trực tiếp

Nếu HTTPS ra Internet được phép và không cần proxy, project Spring Boot chuẩn có thể build mà không tạo mirror hay `servers` riêng. Maven Central đã là nguồn mặc định. Khi lỗi xảy ra, kiểm tra DNS/JDK/TLS/version trước khi thêm repository khác.

### Công ty bắt buộc qua Nexus/Artifactory

Tạo group/virtual repository quản lý các upstream được phép, và trỏ Maven `mirrorOf=external:*` hoặc `*` tới đó; server ID phải trùng mirror ID. Trên CI, secret được inject riêng. Với Gradle, khai báo mirror trực tiếp ở settings hoặc (trên version mới, nếu phù hợp) opt-in reuse Maven mirror. Test cả plugin repository và BOM.

### Có kho nội bộ và vendor repo riêng

Nếu group repository đã kết hợp được, dùng một endpoint đơn giản. Nếu cần để `team-releases` truy cập riêng, `mirrorOf=external:*,!team-releases` có thể loại trừ ID đó và cần `<server id="team-releases">` riêng. Đừng dựng nhiều mirror cùng `*` để mong Maven tự fallback giữa chúng.

### Dev chạy được nhưng CI báo 401/PKIX

So sánh Maven/Gradle Wrapper, JDK/JAVA_HOME, user settings có thật trên agent, secret injection, ID server và corporate CA. Không nên “khắc phục” CI bằng cách commit token hoặc tắt TLS trong repository.

## 12. Bảng xử lý lỗi thường gặp

| Hiện tượng | Kiểm tra nhanh | Hướng sửa |
| --- | --- | --- |
| Maven cố tải từ `repo.maven.apache.org` dù muốn qua intranet | `mvn help:effective-settings`, `mirrorOf`, file `-s` | Sửa mirror pattern/ID và kiểm tra file settings thực tế được dùng |
| Mirror trả 404 cho Spring Boot parent/BOM | Kho có proxy Central không? Group URL đúng không? | Bổ sung upstream/hosted repo được phép, kiểm tra policy |
| Maven tải dependency được nhưng không tải plugin | `pluginRepositories`/mirror có plugin artifacts không? | Cấu hình plugin repository phù hợp |
| HTTP 401 từ repository manager | Server ID trùng mirror ID, token còn hạn? | Cấp đúng server credentials và quyền read |
| HTTP 407 qua corporate proxy | Maven `<proxy>` hoặc Gradle JVM proxy đúng? | Cấp proxy credential và nonProxyHosts |
| `PKIX path building failed` | Trust store của Java đang chạy Maven/Gradle | Cài đúng CA được tin cậy, không tắt SSL |
| Mạng timeout / DNS error | Máy/CI thực sự có route và DNS tới host? | Sửa proxy/VPN/firewall/endpoint |
| `Non-resolvable import POM` | BOM tọa độ/version, mirror, repo policy | Bảo đảm BOM POM có trong nguồn được phép |
| Gradle `Plugin ... was not found` | `pluginManagement.repositories` có plugin marker? | Thêm kho plugin phù hợp, khác kho dependency nếu cần |
| Bật reuse mirror của Gradle nhưng vẫn không đi qua proxy | Feature chỉ nhập mirror/server, không nhập Maven proxies | Cấu hình JVM system properties cho Gradle |
| Xóa cache rồi vẫn 404 | Remote thực sự không có artifact hoặc quyền sai | Sửa repo upstream/credentials/version, không tiếp tục xóa cache |
| Maven `-o` thành công nhưng máy mới thất bại | Máy đầu đã có cache local | Kiểm thử trên agent sạch với kết nối đúng |

## 13. Checklist trước khi đưa vào CI/CD

1. **Tính đúng nguồn:** dependency thường, Spring Boot parent/BOM, transitive dependency, Maven plugins và Gradle plugin markers đều có thể resolve từ nguồn đã phê duyệt.
2. **Tính đúng routing:** mirrorOf match đúng repository ID; proxy nonProxyHosts khớp DNS; không phụ thuộc máy dev/VPN tình cờ.
3. **Quyền truy cập tối thiểu:** account đọc dependency tách khỏi quyền publish; secret không có trong Git, URL, log và build artifacts.
4. **TLS/integrity:** HTTPS, CA/trust store đúng, checksum/chữ ký theo chính sách và khả năng truy vết artifact upstream.
5. **Version/build:** dùng Maven/Gradle Wrapper ổn định, xác định Java runtime, quản lý dependency/plugin version nhất quán; phân biệt snapshot với release.
6. **Cấu hình riêng môi trường:** dùng `settings.xml` hoặc `gradle.properties` user/CI, xác nhận agent được cấp secret và đúng file.
7. **Kiểm thử thực tế:** build trên CI đủ sạch để tải dependency/plugin, chạy test, kiểm tra lần build tiếp theo; không dùng kết quả offline làm bằng chứng network.
8. **Debug an toàn:** dùng `mvn help:effective-settings`, `mvn -U`, `gradlew dependencies` và log với thông tin nhạy cảm đã che; tránh `-X` công khai.
9. **Chính sách repository:** khóa quyền ghi vào mirror/group, kiểm soát nguồn bên ngoài và quy trình cập nhật cache. Mirror là cơ chế phân phối, không tự bảo đảm artifact đáng tin.

## 14. Những nhầm lẫn cần nhớ

- **Mirror ≠ proxy:** mirror đổi repository URL, proxy đổi đường kết nối. **Local repo ≠ mirror:** local repo chỉ là cache trên máy.
- **`mirrorOf=*` ≠ nhiều mirror dự phòng:** Maven chọn một mirror thích hợp; dùng repository manager group khi cần nguồn tổng hợp.
- **Server ID ≠ username:** server ID phải trùng ID repository/mirror mà Maven **thực sự kết nối**, còn username là tài khoản đăng nhập.
- **Dependency repository ≠ plugin repository:** cần kiểm tra cả hai, đặc biệt build Spring Boot có Maven/Gradle plugins.
- **BOM version management ≠ quyền truy cập:** cấu hình đúng version không thể thay cho repository/credentials.
- **`mvn deploy` ≠ tải dependency:** publishing dùng ID/URL riêng trong `distributionManagement`, thường cần quyền ghi riêng.
- **Maven settings ≠ Gradle settings:** Gradle 9.8+ có khả năng reuse mirror có điều kiện, nhưng proxy Maven không được tự nhập sang Gradle.
- **HTTP 407 ≠ HTTP 401:** 407 thường từ network proxy; 401 thường từ repository.
- **Bỏ qua TLS/commit token không phải sửa lỗi đúng:** khắc phục CA, ID, proxy, quyền và repository upstream.

## 15. Tài liệu chính thức theo phiên bản

- Maven – [Settings Reference](https://maven.apache.org/settings.html) (user/global settings, servers, mirrors, proxies, profiles).
- Maven – [Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html) (`mirrorOf`, `external:*`, matching priority).
- Maven – [Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) (version, transitive và BOM).
- Maven – [Deployment Security Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html) (deploy credentials).
- Gradle – [Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html).
- Gradle – [Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html).
- Gradle – [Networking](https://docs.gradle.org/current/userguide/networking.html).
- Gradle – [Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html).
- Gradle – [Release Notes 9.8.0](https://docs.gradle.org/9.8.0/release-notes.html) (opt-in reuse Maven mirror).

**Cách xác định nguyên nhân khi dependency không tải được:** xem Maven/Gradle đang tìm **artifact nào** → repository ID và URL gốc → mirror mapping → proxy route → credentials ID và quyền → tình trạng upstream/cache. Kiểm tra đúng từng lớp giúp khôi phục build Spring Boot an toàn và nhất quán giữa máy dev và CI.