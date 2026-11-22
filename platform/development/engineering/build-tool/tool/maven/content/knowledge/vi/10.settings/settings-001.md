# Vai trò của settings.xml và ranh giới với pom.xml trong Maven

Trong Maven, **`pom.xml` mô tả dự án cần xây dựng**, còn **`settings.xml` mô tả cách Maven hoạt động trong một môi trường cụ thể**. Hai tệp có thể cùng ảnh hưởng kết quả build, nhưng không thay thế chức năng của nhau.

- `pom.xml` trả lời: dự án có tọa độ gì, dùng những dependency/plugin nào, biên dịch ra sao, tạo JAR/WAR gì và cấu hình lifecycle nào được áp dụng.
- `settings.xml` trả lời: Maven lưu cache ở đâu, tải artifact qua repository manager/mirror hoặc proxy nào, dùng thông tin xác thực nào và profile môi trường nào đang được kích hoạt.
- Settings có thể gián tiếp làm thay đổi build (ví dụ repository/profile/property), nhưng **không phải một bản POM thứ hai** để khai báo dependencies, build plugins hoặc project version.

Bài học sử dụng những cú pháp thông dụng với Maven 3.9.x và POM model 4.0.0; với Maven 4, nên đối chiếu tài liệu theo phiên bản vì cơ chế settings và bảo mật repository có thể có bổ sung.

## 1. Bảng phân biệt trách nhiệm

| Nội dung | `pom.xml` | `settings.xml` |
| --- | --- | --- |
| Phạm vi | Dự án/module cụ thể | Máy, người dùng, CI hoặc Maven installation |
| Root XML | `<project>` | `<settings>` |
| Nơi lưu thường gặp | Thư mục gốc project, version control | `~/.m2/settings.xml` hoặc Maven installation |
| Tọa độ artifact | `groupId`, `artifactId`, `version`, `packaging` | Không định danh artifact dự án |
| Dependency | `<dependencies>`, `<dependencyManagement>` | Không định nghĩa trực tiếp project dependencies |
| Plugin/lifecycle | `<build><plugins>`, `<pluginManagement>`, `<executions>` | Không cho phép tùy ý thêm plugin execution vào settings |
| Repository tải về | Có thể khai báo `repositories`, `pluginRepositories` | Mirror, proxy, và repositories qua settings profiles |
| Repository deploy | `<distributionManagement>` định nghĩa đích publish | `<servers>` chứa cấu hình đăng nhập theo ID |
| Cấu hình cá nhân | Hạn chế đặt vào POM dùng chung | `localRepository`, `proxies`, `offline`, `interactiveMode` |
| Bí mật | Không đặt mật khẩu/token trong Git/POM | Quản lý qua settings được bảo vệ và CI secret store |
| Chia sẻ | Thường commit, review, phát hành cùng dự án | Chỉ chia sẻ template an toàn, không chia sẻ credentials thật |

Ví dụ cùng một `pom.xml` khai báo `org.junit.jupiter:junit-jupiter:5.11.0`. Máy cá nhân có thể tải từ Central; CI doanh nghiệp tải qua Nexus/Artifactory nội bộ. **Dependency vẫn do POM xác định**; settings quyết định tuyến kết nối, quyền và môi trường Maven.

## 2. Vị trí global settings và user settings

Hai đường dẫn tiêu chuẩn:

```text
Global settings: ${maven.home}/conf/settings.xml
User settings:   ${user.home}/.m2/settings.xml
```

- Trên Linux/macOS, user settings thường là `~/.m2/settings.xml`.
- Trên Windows, thường là `C:\Users\<user>\.m2\settings.xml`.
- Maven có thể chạy mà không cần tự tạo user settings; khi đó sử dụng default/global settings.
- Khi cả hai tồn tại, Maven **merge** chúng và user settings có ưu tiên ở những trường trùng/được ghi đè. Các collection như servers, mirrors, profiles còn có quy tắc merge theo ID.

Ví dụ chọn settings thay thế cho một lệnh:

```bash
# Linux/macOS: đường dẫn ví dụ, file phải tồn tại
mvn -s /home/dev/.m2/corporate-settings.xml clean verify

# Chỉ định global settings khác nếu có yêu cầu vận hành
mvn -gs /opt/maven/conf/global-settings.xml validate
```

```powershell
# Windows PowerShell
mvn.cmd -s "C:\Users\dev\.m2\corporate-settings.xml" clean verify
```

`-s`/`--settings` chọn **user settings**; `-gs`/`--global-settings` chọn **global settings**. Chọn POM dự án khác dùng `-f`/`--file`, không phải `-s`.

Nếu chạy bằng Maven Wrapper, ví dụ `./mvnw -s /path/to/settings.xml verify`, các tùy chọn `-s` được chuyển cho Maven sau khi Wrapper khởi động. Wrapper có thể cần tải **Maven distribution ZIP trước khi Maven được chạy**; việc tải này không mặc nhiên tuân theo mirrors trong settings.

## 3. Cấu trúc settings.xml: root, schema và các thành phần

Ví dụ một file settings độc lập, hợp lệ về cấu trúc:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <localRepository>${user.home}/.m2/repository</localRepository>
    <interactiveMode>true</interactiveMode>
    <offline>false</offline>
</settings>
```

Namespace `.../SETTINGS/1.2.0` và XSD `settings-1.2.0.xsd` **khác** POM namespace `.../POM/4.0.0`. Không copy root `<project>` hoặc `modelVersion` từ POM sang settings: đó là hai loại XML với schema khác nhau.

Những phần tử settings thường gặp:

| Phần tử | Công dụng | Điều cần nhớ |
| --- | --- | --- |
| `localRepository` | Thư mục lưu dependency/plugin đã tải | Mặc định `${user.home}/.m2/repository` |
| `interactiveMode` | Maven có hỏi input tương tác hay không | CLI `-B` thường dùng ở CI |
| `offline` | Maven Resolver không truy cập remote repositories | Offline cần cache đầy đủ |
| `pluginGroups` | GroupId được tìm khi gọi plugin bằng tên rút gọn | Không tự tải plugin nào |
| `servers` | Credentials và cấu hình server theo ID | Không commit secrets |
| `mirrors` | Ánh xạ repository ID sang endpoint khác | Có thể ảnh hưởng plugin và dependency |
| `proxies` | Thiết lập proxy mạng cho Maven | Không phải repository |
| `profiles` | Repository/property/activation cho môi trường | Tập phần tử ít hơn POM profile |
| `activeProfiles` | Những profile được bật | Ảnh hưởng effective POM/build |

Có thể đổi local repository chỉ cho một lần chạy bằng CLI, không cần sửa file toàn máy:

```bash
mvn -Dmaven.repo.local=/tmp/maven-repo -B verify
```

`/tmp/maven-repo` chỉ là đường dẫn ví dụ trên Unix. Nếu thư mục chưa có plugin/dependency, lần build online sẽ phải tải chúng; offline có thể thất bại.

### Nội suy biến trong settings.xml

Maven settings hỗ trợ các tham chiếu như:

- `${user.home}`: system property của JVM;
- `${env.MAVEN_REPO_USER}`: biến môi trường chứa tên đăng nhập;
- `${env.MAVEN_REPO_PASSWORD}`: biến môi trường chứa bí mật xác thực.

Điểm cần nhớ từ Settings Reference: **properties được khai báo bên trong settings profiles không được dùng để nội suy chính file settings theo cách của system properties/environment variables**. Khi cần cấu hình tham số, dùng biến môi trường, CI templates hoặc cơ chế được Maven version hỗ trợ, thay vì suy đoán một property mới luôn nội suy được mọi chỗ.

## 4. POM vẫn là nơi mô tả dự án và build

POM tối thiểu:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>settings-boundary</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
```

POM quản lý tọa độ artifact, dependency graph, parent/BOM, source layout, plugin goals, lifecycle, testing và packaging. Trên đây, `<modelVersion>4.0.0</modelVersion>` là phiên bản mô hình POM, không phải phiên bản Maven binary hay `<version>1.0.0</version>` của ứng dụng.

**Ví dụ ranh giới:** muốn thêm JUnit thì khai báo nó trong `<dependencies>` ở POM (hoặc kế thừa dependency từ parent), có thể quản lý version qua `<dependencyManagement>`. Chỉ thêm URL repository chứa JUnit vào settings **không thêm JUnit vào classpath của project**.

Muốn chạy Checkstyle ở phase `verify` thì khai báo plugin/execution trong POM hoặc parent POM. Đặt `<build><plugins>` vào `settings.xml` là sai mô hình settings, không làm Maven chấp nhận cấu hình build đó.

POM có thể chỉ định repositories, nhưng thông tin mạng/credentials cá nhân nên tách khỏi POM dùng chung. Khi có chính sách repository manager, settings mirror thường thích hợp hơn việc chép URL nội bộ vào mọi dự án.

## 5. Mirrors, servers và proxies không đồng nghĩa

### 5.1. `mirrors`: chuyển endpoint tải artifact

Đoạn XML trong `<settings>`:

```xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <name>Corporate Maven Repository Manager</name>
        <url>https://repo.example.org/repository/maven-public/</url>
        <mirrorOf>central</mirrorOf>
    </mirror>
</mirrors>
```

`repo.example.org` là hostname **minh họa**, phải thay bằng repository manager thật của tổ chức.

- `mirrorOf=central` khớp **ID repository gốc**, không phải URL hoặc tên dependency.
- `company-mirror` là ID **đích mới** Maven kết nối.
- Mirror có thể được dùng để tải cả dependencies và plugin artifacts, tùy repository mapping.
- `mirrorOf=*` chuyển mọi repository request phù hợp sang một endpoint. Endpoint đó phải chứa hoặc proxy được mọi artifact cần thiết; bản thân Maven **không gộp nhiều mirror thành một repository ảo**.
- Các pattern như `external:*` hoặc `*,!internal` có ý nghĩa riêng; nếu cấu hình nhiều mirrors, Maven xét direct ID matching và các quy tắc matching theo tài liệu.

Không đặt `<mirrorOf>company-mirror</mirrorOf>` bằng chính ID mirror khi thực tế muốn mirror `central`. Không chọn `mirrorOf=*` nếu repository manager nội bộ chưa được chuẩn bị đầy đủ: việc đó có thể khiến một dự án không tải được artifact vốn có sẵn ở repository khác.

### 5.2. `servers`: credentials theo ID endpoint thực tế

Nếu mirror bên trên cần đăng nhập, thông tin xác thực tương ứng có dạng:

```xml
<servers>
    <server>
        <id>company-mirror</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_PASSWORD}</password>
    </server>
</servers>
```

Đây là đoạn XML **đặt trong settings**, không phải file độc lập và không có tài khoản/mật khẩu thật. Các biến môi trường phải được cung cấp bởi máy/CI.

**Lưu ý quan trọng về ID:** Maven kết nối mirror `company-mirror`, vì vậy thông thường server credentials phải có `<id>company-mirror</id>`. ID `central` là repository được mirror, không phải tên tài khoản đăng nhập. Trường hợp truy cập repository deploy riêng cần server ID riêng theo `distributionManagement` trong POM.

Ở những Maven version mới, credential matching còn có thể ràng buộc scheme/host/port để ngăn gửi thông tin đăng nhập sang repository trùng ID nhưng khác nguồn gốc. Khi gặp lỗi quyền, hãy kiểm tra **ID + URL thật + chính sách phiên bản Maven**, không chỉ ID.

Không commit mật khẩu/token vào Git, kể cả trong `settings.xml` mẫu. Secrets nên lấy từ CI secret store hoặc cấu hình người dùng được bảo vệ. Nếu dùng tính năng password encryption, phải tuân theo cơ chế chính xác của Maven version và quản trị khóa; mã hóa không tự thay thế chính sách phân quyền.

### 5.3. `proxies`: đường đi mạng

Cấu hình proxy HTTP minh họa trong settings:

```xml
<proxies>
    <proxy>
        <id>corp-proxy</id>
        <active>true</active>
        <protocol>http</protocol>
        <host>proxy.example.org</host>
        <port>8080</port>
        <nonProxyHosts>localhost|*.example.org</nonProxyHosts>
    </proxy>
</proxies>
```

Proxy cho phép Maven đi qua mạng yêu cầu proxy; nó **không** chỉ định version artifact, không thay thế mirror và không giải quyết lỗi thiếu dependency declaration trong POM. Nếu cần proxy authentication, quản lý secrets bằng cơ chế được tổ chức phê duyệt.

Bảng chọn nhanh:

| Vấn đề | Sửa ở đâu trước? |
| --- | --- |
| Muốn download Maven Central thông qua kho nội bộ | `settings.xml` `<mirrors>` |
| HTTP 401 từ mirror | `settings.xml` `<servers>` ID mirror, kiểm tra credentials |
| HTTP 407 từ proxy | `settings.xml` `<proxies>`/chính sách xác thực mạng |
| Dependency còn thiếu trong project | `pom.xml` `<dependencies>` |
| Muốn tăng Java compiler release | `pom.xml` hoặc parent POM; đồng thời chuẩn bị JDK |
| Maven plugin không chạy goal | POM `<build><plugins><executions>` |
| Muốn cache Maven ở chỗ khác | `localRepository` trong settings hoặc `-Dmaven.repo.local` |

## 6. Profile trong settings khác profile của POM

**Settings profiles** chỉ hỗ trợ một tập phần tử hướng về môi trường:

- `<activation>`: điều kiện bật profile;
- `<repositories>` và `<pluginRepositories>`: nguồn dependency và plugin;
- `<properties>`: các property được đưa vào môi trường build.

Ngược lại, **POM profiles** có thể định nghĩa các cấu phần dự án như `dependencies`, `build`, `plugins`, `executions` mà model Maven cho phép. Vì vậy không copy một POM profile chứa `<build>` vào settings profile.

Ví dụ **settings.xml đầy đủ** dùng một repository nội bộ theo profile (các URL giả định):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <profiles>
        <profile>
            <id>internal-repositories</id>
            <repositories>
                <repository>
                    <id>internal-releases</id>
                    <url>https://repo.example.org/repository/releases/</url>
                    <releases>
                        <enabled>true</enabled>
                    </releases>
                    <snapshots>
                        <enabled>false</enabled>
                    </snapshots>
                </repository>
            </repositories>
            <pluginRepositories>
                <pluginRepository>
                    <id>internal-plugins</id>
                    <url>https://repo.example.org/repository/maven-plugins/</url>
                </pluginRepository>
            </pluginRepositories>
            <properties>
                <organization.environment>dev</organization.environment>
            </properties>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>internal-repositories</activeProfile>
    </activeProfiles>
</settings>
```

`<activeProfiles>` bật profile theo ID; có thể dùng `-P` để bật profile tương ứng khi được cấu hình. Property `organization.environment` có thể được dùng trong POM khi profile active. Đó là lý do hai máy có `pom.xml` giống hệt nhau nhưng settings khác nhau vẫn có thể cho effective POM/build khác nhau.

Một số điều cần tránh:

1. `activeProfiles` không tự tạo repositories khi profile chưa khai báo.
2. Tên profile trùng giữa settings và POM có quy tắc ưu tiên/kích hoạt riêng; không coi đó là một phép merge vô điều kiện.
3. Không dùng settings profile cho mọi biến đổi của build; những quy tắc thuộc bản chất project nên đặt ở POM để có thể review/version hóa.
4. Nếu repository/pluginRepository cần xác thực, xác định đúng server ID và origin, không chỉ kích hoạt profile.

## 7. Thực hành Java 17: một POM, hai cách truy cập repository

Tạo cấu trúc:

```text
settings-boundary/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── vn/example/settings/App.java
```

Nội dung `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>settings-boundary</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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

Nội dung `src/main/java/vn/example/settings/App.java`:

```java
package vn.example.settings;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Maven settings boundary OK");
    }
}
```

Với JDK 17+, Maven tương thích, có thể kết nối một Maven repository hợp lệ (thường Central khi không có mirror):

```bash
java -version
mvn --version
mvn -B clean package
java -cp target/settings-boundary-1.0.0.jar vn.example.settings.App
```

Output **chính xác của lệnh Java cuối cùng**:

```text
Maven settings boundary OK
```

Không dùng output trên để khẳng định log Maven chỉ có một dòng. Build Maven thực tế còn in log plugin/lifecycle, có thể tải plugin lần đầu. POM không có runtime dependencies bên ngoài JDK, nhưng vẫn cần các Maven plugins đã khai báo để compile/package.

Cùng một POM này, khi tổ chức bắt buộc đi qua repository manager nội bộ, tạo settings có `<mirror>`/`<server>` phù hợp ở máy/CI rồi chạy:

```bash
# File settings và repository phải thực sự tồn tại
mvn -s /path/to/corporate-settings.xml -B clean package
```

```powershell
# Windows PowerShell
mvn.cmd -s "C:\path\to\corporate-settings.xml" -B clean package
```

Kết quả JAR và stdout chương trình không cần thay đổi chỉ vì tuyến tải artifacts đổi. Tuy nhiên, nếu mirror nội bộ thiếu plugin hoặc credentials sai, build sẽ lỗi. Các URL `repo.example.org` và đường dẫn `/path/to/...` ở trên là ví dụ, **không phải endpoint dùng được nếu chưa cấu hình thật**.

## 8. Publish artifact: phân biệt distributionManagement và servers

Khi muốn publish artifact JAR/POM lên repository của tổ chức, `<distributionManagement>` thuộc **POM**:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.org/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.org/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

Đây là **đoạn XML đặt bên trong root `<project>`**, không phải file POM độc lập. Nó cho biết nơi triển khai artifact nhưng không nên mang credentials.

Trong **settings** của người chạy deploy:

```xml
<servers>
    <server>
        <id>company-releases</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_PASSWORD}</password>
    </server>
    <server>
        <id>company-snapshots</id>
        <username>${env.MAVEN_REPO_USER}</username>
        <password>${env.MAVEN_REPO_PASSWORD}</password>
    </server>
</servers>
```

Đây chỉ là đoạn settings minh họa, không chứa secrets. Với version release như `1.0.0`, Maven deploy plugin thường dùng repository release; với `1.0.0-SNAPSHOT`, thường dùng snapshotRepository. `mvn package` tạo artifact cục bộ trong `target`, `mvn install` cài local repository, còn `mvn deploy` mới publish lên remote khi đã cấu hình đúng.

Ba ID cần phân biệt rõ: `company-mirror` dùng cho **download qua mirror**, `company-releases` dùng để **deploy release**, `company-snapshots` dùng để **deploy snapshot**. Không có một `<server><id>` duy nhất luôn đúng cho mọi trường hợp.

## 9. Tính tái lập, CI và vấn đề bảo mật

Cùng một Git revision và POM, build vẫn có thể khác vì:

- Global/user settings khác nhau hoặc CLI `-s` chọn một file khác.
- Repository mirror cung cấp phiên bản/plugin/cache khác.
- Credentials, proxy, certificate CA hoặc firewall khác.
- Settings profiles active khác nhau làm thay đổi properties/repositories.
- Local repository khác, bản SNAPSHOT hoặc metadata khác nhau.
- Maven Wrapper/JDK/Maven version và CLI flags khác nhau.

Quy tắc triển khai:

1. Version hóa **POM, parent/BOM, plugin versions, Maven Wrapper** và chính sách JDK.
2. Quản lý settings máy/CI bằng **template không có secrets**, với ID mirror/server rõ ràng.
3. Inject credentials từ secret store tại runtime; hạn chế hiển thị secrets trong log và giữ file settings tạm đúng vòng đời.
4. Nếu tổ chức quản lý repository qua Nexus/Artifactory, cấu hình mirror để mọi developer dùng cùng nguồn đáng tin.
5. Ghi nhận các profile đang active, effective POM và phiên bản JDK khi debug sự khác nhau giữa môi trường.
6. Tránh đặt `<offline>true</offline>` ở user settings lâu dài nếu chưa có mục đích: sẽ ảnh hưởng mọi project của user; nếu chỉ test một lần, dùng `mvn -o`.
7. Không cho rằng tính năng mã hóa password trong Maven đủ để chia sẻ settings chứa secrets công khai; kiểm soát cả khóa, permissions, credential scope và CI.

**Lưu ý:** Maven settings chỉ điều khiển Maven và các thành phần tôn trọng cấu hình đó. Plugin/ứng dụng tự gửi HTTP ngoài Maven Resolver có thể có cơ chế proxy/TLS khác; Wrapper downloader cũng có thể chạy trước khi settings được áp dụng.

## 10. Chẩn đoán effective settings và effective POM

Ba lệnh hỗ trợ điều tra:

```bash
mvn help:effective-settings
mvn help:effective-pom -Doutput=effective-pom.xml
mvn help:active-profiles
```

- `help:effective-settings` cho biết cấu hình settings sau merge, hữu ích để xác nhận mirror, repository, profile và các lựa chọn môi trường.
- `help:effective-pom` cho biết cấu hình project sau parent/profile/defaults, giúp kiểm tra dependency/plugin/lifecycle.
- `help:active-profiles` cho biết profiles đang được kích hoạt.

Các goal này thuộc Maven Help Plugin, có thể phải tải plugin lần đầu. **Kết quả effective settings và log debug được coi là có thể nhạy cảm**, không đăng nguyên bản lên issue công khai hoặc CI artifact không hạn chế, kể cả khi một số trường mật khẩu được che.

Khi nghi sai file settings:

```bash
mvn -s /path/to/corporate-settings.xml help:effective-settings
mvn -s /path/to/corporate-settings.xml -B validate
```

`validate` chỉ kiểm tra sớm ở mô hình/lifecycle, chưa chứng minh các goals build đều có thể tải plugin và dependency. `mvn -X verify` có thể cung cấp thông tin debug nhưng cần lọc log vì nó có thể tiết lộ metadata hạ tầng và URLs.

Một quy trình xử lý lỗi:

1. **POM không parse được:** kiểm tra XML, `<project>`, `modelVersion`, tags và tọa độ parent. Settings không sửa một POM sai cú pháp.
2. **Dependency, parent hoặc plugin không resolve:** kiểm tra tọa độ/phiên bản POM rồi kiểm tra mirror, repository IDs, proxy, auth, offline/cache trong effective settings.
3. **HTTP 401/403:** xem endpoint Maven đang kết nối (mirror hay deploy repository), server ID tương ứng, credential scope và quyền tài khoản.
4. **HTTP 407:** kiểm tra proxy, không vội đổi dependency.
5. **Plugin goal không chạy:** kiểm tra POM `<build><executions>`, không tìm nơi đặt goal trong settings.
6. **Build khác giữa hai máy:** đối chiếu Maven/JDK, settings, profiles, effective POM, local repository và options CLI.
7. **Wrapper chưa tải xong Maven distribution:** kiểm tra script/URL/downloader của Wrapper; Maven settings chưa chắc đã có hiệu lực ở bước bootstrap.

## 11. Những hiểu nhầm phổ biến

| Hiểu nhầm | Sửa cách hiểu |
| --- | --- |
| “`settings.xml` là POM phụ.” | Nó có root/schema/cấu phần riêng về môi trường, không phải cấu hình project thứ hai. |
| “Settings profile thêm `<dependencies>` và `<build>`.” | Cấu trúc này thuộc POM/profile dự án; settings profile giới hạn hơn. |
| “Có repository JUnit trong settings thì tự có JUnit dependency.” | Phải khai báo dependency trong POM hoặc kế thừa từ parent. |
| “Mirror là proxy mạng.” | Mirror đổi Maven repository endpoint; proxy là đường kết nối HTTP(S). |
| “`mirrorOf=central` thì server ID phải là central.” | Nếu thực tế kết nối `company-mirror`, credentials thường dùng ID của mirror. |
| “`mirrorOf=*` tự gộp toàn bộ repositories.” | Chỉ thay endpoint; repository manager phải tự proxy/tổng hợp nguồn. |
| “Một ID server dùng được cho download và mọi deploy.” | ID phải khớp endpoint thực tế, và có chính sách origin ở Maven version mới. |
| “User settings thay thế hoàn toàn global settings.” | Maven merge, user settings ưu tiên theo quy tắc model. |
| “Hai máy giống POM thì chắc chắn cùng effective build.” | Settings, profile, JDK, Maven version và cache vẫn có thể làm khác. |
| “`-s` chọn file POM.” | `-s` chọn settings; `-f` chọn POM. |
| “Có `<offline>true</offline>` thì Maven sẽ tải được dependencies thiếu.” | Offline **không tải từ remote**, yêu cầu cache đủ. |
| “Có thể đăng effective-settings để debug mà không xem trước.” | Có thể lộ cấu hình hạ tầng hoặc bí mật; phải rà soát trước. |

## 12. Tự kiểm tra

**Câu 1.** Một dự án đã khai báo JUnit đúng trong POM nhưng CI không được truy cập Central, chỉ được phép đi qua repository manager nội bộ. Nên sửa đâu?

**Đáp án:** Dùng settings mirror/repository policy của CI để điều hướng tải artifact; không đổi `groupId/artifactId/version` chỉ vì thay đường mạng. Repository manager phải chứa hoặc proxy được artifact cần thiết.

**Câu 2.** Đội muốn mọi project dùng Java release 17 và compiler plugin phiên bản cố định. Có nên đặt `<build><plugins>` trong settings?

**Đáp án:** Không. Đặt chính sách trong POM hoặc parent POM, đồng thời bảo đảm môi trường cung cấp JDK phù hợp.

**Câu 3.** Mirror có `id=company-mirror`, `mirrorOf=central` và nhận 401. Cần kiểm tra server ID nào đầu tiên?

**Đáp án:** `company-mirror` và URL/credentials tương ứng, vì Maven kết nối tới mirror; đồng thời xét cơ chế credential security của Maven version đang dùng.

**Câu 4.** Hai máy dùng cùng POM nhưng một máy build lỗi `Non-resolvable parent POM`. Bạn kiểm tra gì?

**Đáp án:** Tọa độ parent và `relativePath` trong POM; sau đó kiểm tra settings/mirror/repositories, credentials, profile, network và cache ở từng máy. Không kết luận ngay là mã Java hoặc plugin compile lỗi.

## Tài liệu chính thức

- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Configuring Maven](https://maven.apache.org/guides/mini/guide-configuring-maven.html)
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
- [Apache Maven — Guide to Using Proxies](https://maven.apache.org/guides/mini/guide-proxies.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven Help Plugin — effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
