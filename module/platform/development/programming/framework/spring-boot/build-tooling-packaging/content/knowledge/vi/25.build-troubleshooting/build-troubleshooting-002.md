# Xử lý Plugin not found, dependency không tải được và kho yêu cầu xác thực

## 1. Phân loại lỗi trước khi sửa

Maven/Spring Boot build có thể thất bại với các thông báo **No plugin found for prefix**, **PluginResolutionException**, **Could not resolve dependencies**, **Could not transfer artifact**, HTTP **401/403/407**, **PKIX path building failed**, **UnknownHostException**, timeout hoặc **maven-default-http-blocker**.

Những lỗi này không có cùng nguyên nhân. Plugin resolution khác dependency resolution; repository authentication khác proxy authentication; TLS trust khác username/password. Hãy xác định **artifact đầu tiên không resolve được**, URL Maven đang gọi và loại response trước khi thay version hoặc sửa POM.

| Nhóm | Thông báo | Nơi kiểm tra đầu tiên |
| --- | --- | --- |
| Plugin | No plugin found for prefix, PluginResolutionException | Plugin coordinates/version, pluginRepositories |
| Dependency | Could not resolve dependencies, Failed to read artifact descriptor | GAV, repositories, parent/BOM, transitive path |
| Repository auth | 401, 403 | settings.xml, server ID, token và read permission |
| Proxy | 407 | settings.xml proxies, proxy account |
| TLS | PKIX path building failed | CA chain, JDK truststore, TLS inspection |
| Network | DNS, timeout, connection refused | DNS, VPN, firewall, proxy, service health |
| Policy/path | 404, blocked HTTP | URL, repository layout, release/snapshot policy |
| Local state | Cached failure, offline failure | .m2 cache, update policy, offline mode |

## 2. Maven có hai nhóm repository

Maven dùng local repository (mặc định **USER_HOME/.m2/repository**) để cache artifacts, và remote repositories để tải artifacts từ bên ngoài.

| Cấu hình | Mục đích |
| --- | --- |
| **repositories** | Tải project dependencies, parent POM và BOM |
| **pluginRepositories** | Tải Maven plugins và plugin artifacts |
| **distributionManagement** | Nơi deploy/publish artifact của project |
| **mirrors** | Thay URL repository khi resolve |
| **servers** | Credentials cho repository, mirror hoặc deployment server |

**repositories không thay thế pluginRepositories.** Dependency có thể tải được trong khi plugin vẫn không tìm thấy vì plugin nằm ở kho riêng hoặc profile pluginRepository chưa active.

## 3. Xử lý Plugin not found

### 3.1. Xác minh coordinates và prefix

Maven plugin có ba tọa độ chính: groupId, artifactId, version. Ví dụ Spring Boot Maven Plugin:

~~~text
org.springframework.boot:spring-boot-maven-plugin:3.5.16
~~~

Lệnh prefix:

~~~bash
./mvnw spring-boot:run
~~~

yêu cầu Maven tìm plugin có prefix **spring-boot**. Khi prefix metadata không resolve, thử full coordinates:

~~~bash
./mvnw org.springframework.boot:spring-boot-maven-plugin:3.5.16:run
~~~

Full coordinates bỏ qua bước tìm prefix, nhưng Maven vẫn cần tải plugin nếu nó chưa có trong local repository. Nếu lệnh này cũng fail, kiểm tra version, repository, mirror, authentication và network.

### 3.2. Nguyên nhân thường gặp

1. Typo groupId/artifactId/prefix.
2. Version không tồn tại hoặc release/SNAPSHOT bị disable.
3. Plugin nằm trong repository riêng nhưng thiếu pluginRepository.
4. Profile chứa pluginRepository chưa active.
5. Mirror không proxy plugin artifacts hoặc URL sai.
6. Server ID không khớp repository/mirror ID nên credentials không được dùng.
7. Proxy, TLS, DNS hoặc firewall chặn request.
8. Local repository không ghi được do permission/disk.
9. Repository không chứa plugin version đã yêu cầu.

### 3.3. Spring Boot plugin version management

Khi kế thừa **spring-boot-starter-parent**, Maven nhận dependency management và plugin management. Có thể khai báo plugin không cần version:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Nếu chỉ import **spring-boot-dependencies** BOM, BOM quản lý dependency versions nhưng không tự cung cấp plugin management như starter parent. Khi đó cần khai báo version plugin và goal repackage:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.5.16</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Spring Boot 3.5.16 yêu cầu Java 17+ và Maven 3.6.3+. Kiểm tra Maven thực sự chạy:

~~~bash
./mvnw --version
java -version
~~~

Ưu tiên Maven Wrapper đã commit trong project để local và CI dùng cùng Maven distribution.

## 4. Plugin repositories khác dependency repositories

Nếu công ty có kho dependencies và kho plugins riêng, POM có thể khai báo:

~~~xml
<repositories>
    <repository>
        <id>company-dependencies</id>
        <url>https://repo.example.com/repository/maven-dependencies/</url>
        <releases><enabled>true</enabled></releases>
        <snapshots><enabled>false</enabled></snapshots>
    </repository>
</repositories>

<pluginRepositories>
    <pluginRepository>
        <id>company-plugins</id>
        <url>https://repo.example.com/repository/maven-plugins/</url>
        <releases><enabled>true</enabled></releases>
        <snapshots><enabled>false</enabled></snapshots>
    </pluginRepository>
</pluginRepositories>
~~~

Hai IDs khác nhau nên settings.xml cần hai server entries tương ứng. Nếu plugin chỉ có trong **company-plugins**, khai báo riêng **company-dependencies** không giúp Maven tìm plugin.

### 4.1. Releases và snapshots

Version **1.2.0-SNAPSHOT** cần repository bật snapshots. Version release **1.2.0** cần releases enabled. Plugin repositories cũng có hai cờ này.

~~~xml
<releases><enabled>false</enabled></releases>
<snapshots>
    <enabled>true</enabled>
    <updatePolicy>always</updatePolicy>
</snapshots>
~~~

Đoạn trên chỉ minh họa kho snapshot. Không đổi release thành SNAPSHOT chỉ để né lỗi nếu artifact không được publish ở snapshot repository.

## 5. Dependency không tải được

### 5.1. Kiểm tra GAV và artifact metadata

Maven coordinates gồm:
- **groupId**: namespace.
- **artifactId**: tên artifact.
- **version**: version.
- **type**: loại artifact, thường là jar.
- **classifier**: biến thể artifact nếu có.

Ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>3.5.16</version>
</dependency>
~~~

Khi dùng Spring Boot parent/BOM tương ứng, version đã được quản lý nên có thể bỏ version. Nếu resolve fail, kiểm tra chính tả GAV, version đã publish chưa, artifact có trong repository không, release/SNAPSHOT policy và classifier/type.

### 5.2. DependencyManagement không tự thêm dependency

BOM/parent quản lý version nhưng không tự đưa dependency vào classpath. Project vẫn phải khai báo dependency trong **dependencies**.

Tương tự, **pluginManagement** quản lý cấu hình/version của plugin khi plugin được khai báo; nó không tự kích hoạt tất cả plugin.

### 5.3. Transitive dependencies

Một dependency trực tiếp có thể tồn tại nhưng POM của nó trỏ tới dependency bắc cầu không tải được. Log thường nêu đường dẫn:

~~~text
application
  -> library-a
      -> library-b
          -> library-c
~~~

Tập trung vào artifact đầu tiên không resolve được. Sau khi plugin cần thiết tải được, dùng:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Lệnh này hiển thị dependency graph, version được chọn, scope và exclusions. Nếu chính Maven Dependency Plugin không resolve, hãy sửa plugin resolution trước hoặc xem effective POM.

## 6. Kiểm tra active profiles và effective configuration

Repository có thể nằm trong profile của POM hoặc settings.xml. Profile không active thì repository bên trong không tham gia resolution.

~~~bash
./mvnw help:active-profiles
./mvnw help:effective-pom -Dverbose
./mvnw help:effective-settings
~~~

- **help:active-profiles**: profile nào đang active.
- **help:effective-pom**: POM sau kế thừa và áp dụng profiles.
- **help:effective-settings**: settings hợp nhất từ global và user settings.

Các goal Help Plugin cũng cần được resolve. Nếu Help Plugin chưa tải được, dùng log -X và kiểm tra POM/settings trực tiếp.

Ví dụ settings profile:

~~~xml
<profiles>
    <profile>
        <id>company-repositories</id>
        <repositories>
            <repository>
                <id>company-dependencies</id>
                <url>https://repo.example.com/repository/maven-public/</url>
            </repository>
        </repositories>
        <pluginRepositories>
            <pluginRepository>
                <id>company-plugins</id>
                <url>https://repo.example.com/repository/maven-public/</url>
            </pluginRepository>
        </pluginRepositories>
    </profile>
</profiles>
<activeProfiles>
    <activeProfile>company-repositories</activeProfile>
</activeProfiles>
~~~

Có thể kích hoạt rõ profile:

~~~bash
./mvnw -Pcompany-repositories clean verify
~~~

## 7. Authentication trong settings.xml

Maven tách credentials khỏi POM. URL/ID repository có thể chia sẻ trong project; username/password/token nằm trong **settings.xml**.

Vị trí thường gặp:
- Global: **MAVEN_HOME/conf/settings.xml**.
- User: **USER_HOME/.m2/settings.xml**.

Nếu cả hai tồn tại, Maven hợp nhất; user settings có ưu tiên cao hơn khi trùng cấu hình. Có thể chọn user settings bằng **-s**, global settings bằng **-gs**.

### 7.1. Server ID phải khớp repository ID

POM:

~~~xml
<repository>
    <id>company-dependencies</id>
    <url>https://repo.example.com/repository/maven-dependencies/</url>
</repository>
~~~

settings.xml:

~~~xml
<servers>
    <server>
        <id>company-dependencies</id>
        <username>build-user</username>
        <password>token-from-secret-store</password>
    </server>
</servers>
~~~

**ID là khóa ánh xạ credentials, không phải username.** Nếu POM dùng company-dependencies nhưng settings dùng company-releases, Maven có thể không gửi credentials đúng và server trả 401.

### 7.2. Dùng environment variables

~~~xml
<servers>
    <server>
        <id>company-dependencies</id>
        <username>${env.MVN_REPO_USER}</username>
        <password>${env.MVN_REPO_TOKEN}</password>
    </server>
    <server>
        <id>company-plugins</id>
        <username>${env.MVN_REPO_USER}</username>
        <password>${env.MVN_REPO_TOKEN}</password>
    </server>
</servers>
~~~

Linux/macOS:

~~~bash
export MVN_REPO_USER="build-user"
export MVN_REPO_TOKEN="token-from-secret-store"
./mvnw -s /secure/path/settings.xml clean verify
~~~

PowerShell:

~~~powershell
$env:MVN_REPO_USER = "build-user"
$env:MVN_REPO_TOKEN = "token-from-secret-store"
.\\mvnw.cmd -s C:\\secure\\settings.xml clean verify
~~~

Biến môi trường phải được thiết lập trong đúng process chạy Maven. Không ghi token thật vào POM, source control, shell history, command-line logs hoặc ảnh chụp màn hình.

## 8. Mirror và credentials của mirror

Maven mirror thay URL repository mà không cần sửa POM.

~~~xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <url>https://repo.example.com/repository/maven-public/</url>
        <mirrorOf>central</mirrorOf>
    </mirror>
</mirrors>
~~~

Maven có repository ID gốc **central**, nhưng request thực tế đi tới mirror ID **company-mirror**. Vì vậy server credentials phải dùng mirror ID:

~~~xml
<servers>
    <server>
        <id>company-mirror</id>
        <username>${env.MVN_REPO_USER}</username>
        <password>${env.MVN_REPO_TOKEN}</password>
    </server>
</servers>
~~~

Nếu mirror có ID company-mirror mà server chỉ khai báo ID central, credentials có thể không được dùng.

### 8.1. Mirror tất cả repositories

~~~xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <url>https://repo.example.com/repository/maven-public/</url>
        <mirrorOf>*</mirrorOf>
    </mirror>
</mirrors>
~~~

Endpoint nội bộ phải proxy/host mọi artifacts cần thiết, gồm plugins, parent POMs và dependencies. **mirrorOf=* không tự tổng hợp nhiều repositories**; repository manager phải được cấu hình thành group/proxy phù hợp.

Một số patterns:

| Pattern | Ý nghĩa |
| --- | --- |
| central | Repository có ID central |
| * | Mọi repository |
| external:* | Repository bên ngoài, không phải localhost/file |
| repo1,repo2 | Hai IDs cụ thể |
| *,!inhouse | Mọi repository trừ inhouse |

Không thêm khoảng trắng tùy tiện vào danh sách phân tách bằng dấu phẩy. Maven chọn một mirror khớp cho mỗi repository; nhiều mirror cùng khớp không được cộng thành một danh sách fallback.

## 9. Proxy authentication khác repository authentication

Request có thể đi qua proxy trước khi tới repository. Proxy và repository là hai nơi có thể yêu cầu credentials.

~~~xml
<proxies>
    <proxy>
        <id>company-proxy</id>
        <active>true</active>
        <protocol>http</protocol>
        <host>proxy.example.com</host>
        <port>8080</port>
        <username>${env.MVN_PROXY_USER}</username>
        <password>${env.MVN_PROXY_PASSWORD}</password>
        <nonProxyHosts>localhost|127.0.0.1|*.internal.example.com</nonProxyHosts>
    </proxy>
</proxies>
~~~

Dùng đúng proxy protocol/host/port theo network team. **nonProxyHosts** là danh sách host không đi qua proxy, phân cách bằng dấu |.

- **407** thường là proxy authentication.
- **401** thường là repository authentication.

Đừng sửa POM trước khi xác định server nào trả status.

## 10. TLS và PKIX

Thông báo:

~~~text
PKIX path building failed
unable to find valid certification path to requested target
~~~

thường chỉ ra Java truststore không tin certificate chain của HTTPS server hoặc proxy TLS inspection.

Kiểm tra:
- URL HTTPS và hostname có đúng không.
- Certificate có hết hạn hoặc thiếu intermediate CA không.
- Maven dùng JDK/truststore nào.
- Corporate proxy có dùng CA riêng chưa được trust không.
- CI image có CA certificates cần thiết không.

Nếu có private CA, lấy certificate chain đã được xác minh từ administrator và cấu hình truststore theo policy. Ví dụ:

~~~bash
export MAVEN_OPTS="-Djavax.net.ssl.trustStore=/secure/company-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12"
./mvnw clean verify
~~~

Đường dẫn và loại keystore phải khớp file thật. Không ghi truststore password vào log/command line nếu có thể dùng secret injection.

**Không tắt SSL verification, không đổi HTTPS thành HTTP và không bỏ qua certificate errors.** Việc đó làm mất bảo vệ chống giả mạo repository và man-in-the-middle.

## 11. Maven 3.8.1+ chặn external HTTP repositories

Từ Maven 3.8.1, external repositories dùng HTTP bị chặn mặc định qua **maven-default-http-blocker** để giảm nguy cơ tải dependencies qua kết nối không mã hóa.

Thông báo thường gặp:

~~~text
Blocked mirror for repositories:
[maven-default-http-blocker (http://0.0.0.0/)]
~~~

Cách xử lý:
1. Tìm POM trực tiếp hoặc transitive dependency POM khai báo URL HTTP.
2. Nâng dependency lên version dùng HTTPS nếu có.
3. Nếu tổ chức kiểm soát repository, dùng HTTPS mirror tin cậy.
4. Kiểm tra repository manager proxy upstream qua HTTPS.
5. Không gỡ blocker hoặc cho phép HTTP toàn cục chỉ để build pass.

URL HTTP đôi khi nằm trong POM của dependency bắc cầu, không phải POM ứng dụng. Log sẽ chỉ ra đường dependency dẫn tới POM cũ. Cập nhật dependency thường là hướng sửa lâu dài.

## 12. Hiểu HTTP status từ repository

Các mã dưới đây là dấu hiệu chẩn đoán phổ biến, không phải quy luật tuyệt đối cho mọi repository manager.

| Status/lỗi | Ý nghĩa thường gặp | Việc cần kiểm tra |
| --- | --- | --- |
| 401 Unauthorized | Credentials thiếu/sai | Server ID, token/password, hết hạn, auth scheme |
| 403 Forbidden | Không có quyền hoặc bị policy chặn | Read permission, token scope, IP allowlist |
| 404 Not Found | Artifact/version/path không tồn tại hoặc repo không proxy | GAV, URL, layout, classifier |
| 407 Proxy Authentication Required | Proxy yêu cầu credentials | settings.xml proxies, proxy account |
| 429 Too Many Requests | Rate limit | Retry/backoff, CI concurrency, quota |
| 5xx | Repository/proxy/server tạm lỗi | Service health, upstream, status page |
| PKIX/TLS handshake | Certificate/truststore issue | CA chain, JDK truststore, proxy |
| UnknownHostException | DNS không resolve host | DNS, VPN, hostname, proxy |
| Timeout/refused | Network path/port/service không reachable | Firewall, route, proxy, service |

Một số kho cố ý trả 404 thay vì 401 để không tiết lộ artifact private có tồn tại hay không. Kết hợp HTTP response với server logs và quyền tài khoản.

### 12.1. 401

So repository ID trong POM/settings profile, mirror ID trong settings.xml, server ID trong servers và URL thực tế trong log -X. Nếu có mirror, so với **mirror ID**, không chỉ repository ID ban đầu.

### 12.2. 403

Token có thể đăng nhập thành công nhưng thiếu quyền read package/repository. Kiểm tra token scope, repository path, project ACL, account, IP allowlist và policy release/snapshot. Cấp quyền tối thiểu cần cho dependency/plugin read; publish/deploy dùng quyền riêng.

### 12.3. 404

Maven repository dùng layout theo groupId/artifactId/version. Ví dụ:

~~~text
org/example/library/1.2.3/library-1.2.3.pom
org/example/library/1.2.3/library-1.2.3.jar
~~~

Một version có thể chỉ có POM hoặc classifier riêng. Kiểm tra artifact đã publish đầy đủ chưa và repository manager có proxy đúng upstream không.

## 13. Local repository, cache và offline mode

Maven lưu artifacts trong **USER_HOME/.m2/repository**. Nếu lần tải trước thất bại, metadata/cache có thể khiến lần build sau tiếp tục báo cached failure. Không xóa toàn bộ local repository ngay khi gặp lỗi.

### 13.1. Dùng -U đúng lúc

~~~bash
./mvnw -U clean verify
~~~

**-U** buộc Maven kiểm tra missing releases và SNAPSHOT đã cập nhật ở remote repositories. Dùng sau khi sửa repository URL/credentials hoặc khi nghi kết quả failure bị cache.

**-U không sửa** typo, artifact không tồn tại, token hết hạn, 401/403, DNS/TLS/firewall hoặc HTTP bị block.

### 13.2. Offline mode

~~~bash
./mvnw -o clean verify
~~~

**-o** yêu cầu Maven hoạt động offline. Chỉ dùng khi parent POMs, plugins, plugin dependencies và project dependencies cần thiết đã có trong local repository. Nếu đang điều tra lỗi tải artifact, đừng bật offline.

### 13.3. Dọn cache có phạm vi

1. Xác nhận URL/coordinates/repository đúng.
2. Dùng -U để Maven thử lại.
3. Nếu vẫn lỗi, xác định đúng thư mục artifact/version trong .m2.
4. Chỉ xóa cache của artifact/version bị lỗi khi đã biết chính xác phạm vi.
5. Build lại và đọc log transfer.

Không xóa toàn bộ .m2/repository trên máy developer/CI dùng chung; thao tác đó buộc tải lại nhiều artifacts, tăng tải mạng và phá cache của dự án khác.

## 14. Bộ lệnh chẩn đoán có thứ tự

### Bước 1: xác nhận Maven/JDK

~~~bash
./mvnw --version
java -version
~~~

### Bước 2: lấy lỗi đầy đủ

~~~bash
./mvnw -U -e -X validate
~~~

- **-U**: kiểm tra missing releases và updated snapshots.
- **-e**: in exception details.
- **-X**: bật debug logs, giúp thấy repository URL/mirror và quá trình resolution.

Không gửi log -X chưa redacted ra public issue. Log có thể chứa private repository URLs, usernames, environment values hoặc metadata nhạy cảm.

### Bước 3: kiểm tra profiles và POM

~~~bash
./mvnw help:active-profiles
./mvnw help:effective-pom -Dverbose
~~~

Tìm spring-boot-maven-plugin version, pluginRepositories, repositories, dependencyManagement, pluginManagement và profile đã áp dụng.

### Bước 4: kiểm tra settings

~~~bash
./mvnw help:effective-settings
~~~

Xác nhận mirrors, server IDs, active settings profiles, proxy, local repository và offline setting. Maven Help Plugin ẩn password mặc định. **Không bật showPasswords=true** khi chia sẻ logs.

### Bước 5: xem dependency graph

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Tìm transitive dependency, version conflict, exclusions và scope. Nếu dependency plugin chưa tải được, sửa plugin resolution trước.

### Bước 6: build sạch

~~~bash
./mvnw -U -B -ntp clean verify
~~~

clean xóa target của project hiện tại; không xóa toàn bộ local Maven repository.

## 15. Project Spring Boot tối thiểu để tái hiện

Ví dụ dùng Java 17 và Spring Boot 3.5.16. Spring Boot 3.5.16 yêu cầu Maven 3.6.3 trở lên.

### 15.1. Cấu trúc

~~~text
repository-diagnostic/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
└── src/
    └── main/
        ├── java/com/example/repository/
        │   ├── RepositoryDiagnosticApplication.java
        │   └── HealthController.java
        └── resources/application.properties
~~~

Maven Wrapper cần được tạo bằng Spring Initializr hoặc Maven Wrapper plugin và commit vào repository.

### 15.2. Main class

Tệp **src/main/java/com/example/repository/RepositoryDiagnosticApplication.java**:

~~~java
package com.example.repository;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RepositoryDiagnosticApplication {
    public static void main(String[] args) {
        SpringApplication.run(RepositoryDiagnosticApplication.class, args);
    }
}
~~~

### 15.3. Controller

Tệp **src/main/java/com/example/repository/HealthController.java**:

~~~java
package com.example.repository;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {
    @GetMapping("/repository-check")
    public String check() {
        return "repository-resolution-ok";
    }
}
~~~

### 15.4. application.properties

~~~properties
spring.application.name=repository-diagnostic
server.port=8080
~~~

### 15.5. POM cơ bản

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>repository-diagnostic</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
~~~

Với POM này, Maven dùng Spring Boot parent để quản lý dependency/plugin versions. Không cần thêm version cho starter hoặc plugin.

### 15.6. Build và chạy

~~~bash
./mvnw -B -ntp clean verify
./mvnw spring-boot:run
~~~

Từ terminal khác:

~~~bash
curl --fail --silent --show-error http://localhost:8080/repository-check
~~~

Response body chính xác:

~~~text
repository-resolution-ok
~~~

Nếu build pass và endpoint trả đúng body, dependencies/plugins có thể resolve trong môi trường hiện tại, app compile/start được và endpoint hoạt động. Điều đó không chứng minh mọi private repositories hoặc mọi production profiles đã được kiểm tra.

## 16. CI/CD: cung cấp credentials an toàn

Một pipeline thường cần checkout source, thiết lập JDK/Wrapper, cung cấp settings.xml từ secret store, chạy Maven build/test rồi lưu reports/artifacts. Không lưu credentials vào artifacts.

Ví dụ GitHub Actions minh họa:

~~~yaml
name: Maven build

on:
  push:
    branches:
      - main
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Set up Java
        uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Create Maven settings
        env:
          MVN_REPO_USER: ${{ secrets.MVN_REPO_USER }}
          MVN_REPO_TOKEN: ${{ secrets.MVN_REPO_TOKEN }}
        run: |
          mkdir -p "$HOME/.m2"
          cat > "$HOME/.m2/settings.xml" <<'EOF'
          <settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
            <servers>
              <server>
                <id>company-mirror</id>
                <username>${env.MVN_REPO_USER}</username>
                <password>${env.MVN_REPO_TOKEN}</password>
              </server>
            </servers>
            <mirrors>
              <mirror>
                <id>company-mirror</id>
                <url>https://repo.example.com/repository/maven-public/</url>
                <mirrorOf>*</mirrorOf>
              </mirror>
            </mirrors>
          </settings>
          EOF
          chmod 600 "$HOME/.m2/settings.xml"

      - name: Verify
        run: ./mvnw -B -ntp -U clean verify
~~~

Đây là mẫu. Thay registry endpoint/secret names theo tổ chức; pin GitHub Actions theo commit SHA trong pipeline production theo supply-chain policy.

### 16.1. Pull request từ fork

Không cấp private repository tokens hoặc publish credentials cho workflow chạy untrusted code từ fork. Tách job kiểm tra PR khỏi job phát hành/sign/publish. Nếu cần private dependencies để test PR, thiết kế access policy có giới hạn và không để untrusted scripts đọc secrets.

### 16.2. Cache Maven dependencies

CI có thể cache local Maven repository để giảm download time. Nhưng cache không sửa được credentials hết hạn, mirror URL sai, artifact không tồn tại, repository không proxy plugin hoặc TLS/CA issue.

Để cô lập cache:

~~~bash
./mvnw -Dmaven.repo.local=target/m2-diagnostic -U -B clean verify
~~~

Lệnh này tạo cache mới trong target; lần đầu sẽ tải nhiều hơn. Không dùng đường dẫn cache tạm làm cấu hình lâu dài nếu chưa cân nhắc disk và CI cache policy.

## 17. Bảng quyết định: sửa ở đâu?

| Thông báo | Vị trí kiểm tra | Hành động đầu tiên |
| --- | --- | --- |
| No plugin found for prefix | Prefix, plugin group, pluginRepositories | Thử full coordinates, xác minh plugin version/repository |
| PluginResolutionException | Plugin coordinates, pluginRepositories, settings | Đọc lỗi transfer URL và server ID |
| Could not resolve dependencies | GAV, repositories, parent/BOM, profiles | Xác minh artifact/version và dependency path |
| Could not find artifact | Repository URL/path, release/snapshot | Kiểm tra artifact đã publish và repository policy |
| 401 | settings.xml servers | So server ID với repository/mirror ID, token |
| 403 | Repository permissions/policy | Kiểm tra read scope, project ACL, IP policy |
| 407 | settings.xml proxies | Kiểm tra proxy credentials |
| PKIX path building failed | JDK truststore/corporate CA | Import CA đã xác minh, cấu hình truststore |
| UnknownHostException | DNS/network | Kiểm tra host, VPN, DNS/proxy |
| Blocked mirror | POM/transitive POM URL HTTP | Chuyển HTTPS hoặc mirror HTTPS tin cậy |
| Cached failure | Local .m2 cache/update policy | Sau khi sửa remote, chạy -U |
| Offline resolution failure | Offline mode | Bỏ -o khi cần tải remote |
| Permission denied in .m2 | Local repository path | Sửa owner/permissions/disk |

## 18. Những lỗi cấu hình thường gặp

- **Ghi credentials vào POM:** POM được commit và chia sẻ; dùng settings.xml/secret store.
- **Server ID không khớp mirror ID:** Maven kết nối mirror nên credentials phải khớp mirror ID.
- **Chỉ khai báo repositories:** plugin ở kho khác cần pluginRepositories.
- **Nhầm dependencyManagement với dependencies:** BOM quản lý version, không tự thêm dependency vào classpath.
- **Đổi version để né authentication:** sửa credentials/permissions đúng nguyên nhân.
- **Tắt TLS hoặc mở lại HTTP:** làm dependency downloads dễ bị giả mạo; dùng HTTPS và CA tin cậy.
- **Dùng -U như thuốc chữa mọi lỗi:** -U không sửa typo, permission, URL, proxy, TLS hoặc artifact không tồn tại.
- **Xóa toàn bộ .m2:** tăng thời gian/tải mạng và che nguyên nhân; xử lý cache có phạm vi.

## 19. Bài tập thực hành

**Câu 1.** POM khai báo repository ID company-dependencies nhưng settings có server ID company-releases. Vì sao có thể nhận 401?

**Đáp án:** Maven ánh xạ credentials theo repository/server ID. Hai ID khác nhau nên credentials không khớp request.

**Câu 2.** Dependency tải được nhưng plugin không tải được. Vì sao?

**Đáp án:** Dependencies dùng repositories; plugins dùng pluginRepositories. Hai danh sách có thể khác nhau.

**Câu 3.** Tại sao full coordinates giúp chẩn đoán No plugin found for prefix?

**Đáp án:** Nó bỏ qua bước tìm prefix. Nếu full coordinates resolve được, vấn đề có thể nằm ở prefix metadata/group mapping.

**Câu 4.** Mirror có ID company-mirror và mirrorOf=central. Server credentials phải dùng ID nào?

**Đáp án:** company-mirror, vì Maven kết nối qua mirror đó.

**Câu 5.** Dependency version là 1.2.0-SNAPSHOT nhưng repository chỉ bật releases. Điều gì xảy ra?

**Đáp án:** Maven không tìm snapshot ở repository đó. Cần repository cho phép snapshots và metadata phù hợp.

**Câu 6.** Maven trả 407. Có nên đổi password repository không?

**Đáp án:** Không phải bước đầu. 407 là proxy authentication; kiểm tra settings.xml proxies.

**Câu 7.** Maven 3.8.1+ báo maven-default-http-blocker. Cách sửa an toàn?

**Đáp án:** Cập nhật URL sang HTTPS hoặc dùng HTTPS mirror được quản lý. Không gỡ HTTP blocker chỉ để build pass.

**Câu 8.** help:effective-settings có hiện password không?

**Đáp án:** Mặc định không. Không bật showPasswords khi chia sẻ logs.

**Câu 9.** Sau khi sửa token, Maven vẫn báo cached transfer failure. Làm gì?

**Đáp án:** Chạy -U để Maven kiểm tra lại missing releases/updated snapshots; nếu cần, xóa đúng cache artifact/version sau khi xác minh remote config.

**Câu 10.** Import spring-boot-dependencies BOM nhưng plugin không có version. Vì sao?

**Đáp án:** BOM quản lý dependency versions, không cung cấp plugin management như starter parent. Khai báo plugin version rõ ràng hoặc kế thừa parent.

## 20. Checklist xử lý sự cố

- [ ] Xác định lỗi nằm ở plugin, dependency, authentication, proxy, TLS hay local cache.
- [ ] Xác nhận Maven/JDK version qua Maven Wrapper.
- [ ] Kiểm tra plugin groupId, artifactId, version và goal.
- [ ] Phân biệt pluginRepositories với repositories.
- [ ] Kiểm tra release/snapshot policy.
- [ ] Kiểm tra active profiles và effective POM.
- [ ] Kiểm tra effective settings, mirror URL và mirrorOf.
- [ ] So server ID với repository ID hoặc mirror ID thực tế.
- [ ] Xác minh token, read permission, expiration và proxy credentials.
- [ ] Kiểm tra HTTPS certificate chain và truststore.
- [ ] Xác minh external HTTP repositories bị Maven block.
- [ ] Dùng -U sau khi sửa remote configuration nếu cần.
- [ ] Chỉ dọn cache artifact cụ thể khi có bằng chứng cache bị lỗi.
- [ ] Không commit credentials hoặc chia sẻ debug logs chưa redacted.
- [ ] Chạy clean verify và kiểm tra output/artifact sau khi sửa.
- [ ] Kiểm tra CI dùng cùng Maven settings/profile với môi trường đã xác minh.

## 21. Quy trình chẩn đoán tổng hợp

~~~text
Maven build fails
       |
       v
Read first unresolved coordinate and remote URL
       |
       +---- Plugin?
       |       +--> Check prefix / full coordinates
       |       +--> Check pluginRepositories
       |       +--> Check plugin version + release/snapshot
       |
       +---- Dependency?
       |       +--> Check GAV + parent/BOM
       |       +--> Check repositories + active profiles
       |       +--> Check transitive dependency path
       |
       +---- HTTP/auth/network?
               +--> 401/403: server ID, token, read permission
               +--> 407: proxy credentials
               +--> 404: coordinates, path, repository content
               +--> PKIX: CA/truststore
               +--> timeout/DNS: network/proxy
               +--> HTTP blocker: replace with HTTPS/mirror
       |
       v
Inspect effective POM/settings and -X logs
       |
       v
Correct one root cause
       |
       v
Retry with -U when remote cache may be stale
       |
       v
mvn clean verify
       |
       v
Record verified configuration and keep secrets out of logs
~~~

Đọc **artifact và URL đầu tiên không resolve được** thường hiệu quả hơn việc thay đồng thời nhiều version, thêm nhiều repositories hoặc xóa local cache.

## 22. Kết luận

Ba nhóm lỗi thường bị gọi chung là “Maven không tải được dependency”, nhưng cách xử lý khác nhau:

- **Plugin not found**: kiểm tra plugin coordinates, prefix, pluginRepositories và plugin version.
- **Dependency not found**: kiểm tra GAV, repositories, dependencyManagement, transitive path, active profiles và releases/snapshots.
- **Repository authentication**: kiểm tra settings.xml, server ID, mirror ID, token scope và quyền đọc.
- **Proxy/TLS/network**: xử lý proxy credentials, DNS, firewall và certificate trust.
- **Local cache**: chỉ dùng -U hoặc dọn đúng artifact sau khi remote configuration đã đúng.

Một cấu hình Maven ổn định cần POM mô tả dependency/plugin rõ ràng, settings.xml giữ credentials, mirror/repository manager được quản lý và CI dùng cùng Maven Wrapper/profile. Khi build lỗi, dựa vào tọa độ artifact, URL thực tế và HTTP/TLS response để sửa đúng tầng.

## 23. Tài liệu tham khảo chính thức

- Apache Maven — PluginResolutionException: https://cwiki.apache.org/confluence/spaces/MAVEN/pages/4589202/PluginResolutionException
- Apache Maven — Settings Reference: https://maven.apache.org/settings.html
- Apache Maven — Introduction to Repositories: https://maven.apache.org/guides/introduction/introduction-to-repositories
- Apache Maven — Using Mirrors for Repositories: https://maven.apache.org/guides/mini/guide-mirror-settings
- Apache Maven — Configuring Maven: https://maven.apache.org/guides/mini/guide-configuring-maven.html
- Apache Maven — Configuring a Proxy: https://maven.apache.org/guides/mini/guide-proxies.html
- Apache Maven — Password Encryption: https://maven.apache.org/guides/mini/guide-encryption.html
- Apache Maven — Maven 3.8.1 Release Notes: https://maven.apache.org/docs/3.8.1/release-notes.html
- Apache Maven Help Plugin — effective-settings: https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html
- Apache Maven Help Plugin — effective-pom: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Spring Boot 3.5.16 — Maven Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/
- Spring Boot 3.5.16 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 3.5 — Build Systems: https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html
