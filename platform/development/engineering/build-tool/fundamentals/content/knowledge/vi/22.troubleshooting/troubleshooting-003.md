# Lỗi tải plugin, thư viện và truy cập kho lưu trữ

Trong một dự án Java, Maven hoặc Gradle có thể thất bại trước cả khi compiler được chạy vì không tải được plugin hoặc thư viện cần thiết. Thông báo như 401 Unauthorized, 403 Forbidden, 404 Not Found, 407 Proxy Authentication Required, PKIX path building failed, UnknownHostException, Read timed out hoặc Could not resolve dependency thường xuất hiện ở giai đoạn này.

Các lỗi đó có thể nhìn giống nhau vì đều khiến build không lấy được một thành phần từ mạng, nhưng nguyên nhân rất khác nhau: sai tọa độ artifact, repository chưa được khai báo, plugin và dependency dùng hai cơ chế phân giải riêng, credential không hợp lệ, proxy chặn kết nối, chứng thư TLS không được tin cậy, metadata cũ, repository đang offline hoặc artifact chưa được publish.

Muốn chẩn đoán hiệu quả, trước hết phải xác định build đang tải **plugin**, **dependency của project**, **dependency của plugin/build script** hay đang **publish artifact**. Sau đó đọc loại lỗi và kiểm tra đúng repository, cấu hình xác thực, đường mạng và metadata liên quan. Bài này trình bày các cơ chế và quy trình xử lý cho Maven và Gradle.

## 1. Build tool tải những thành phần nào?

Một build Java có thể cần tải nhiều loại thành phần ở những thời điểm khác nhau:

| Thành phần | Ví dụ | Mục đích |
|---|---|---|
| Build plugin | Maven Compiler Plugin, Gradle Checkstyle Plugin | Thực hiện compile, test, đóng gói, kiểm tra chất lượng |
| Plugin dependency | Thư viện mà chính plugin cần để chạy | Cung cấp chức năng cho plugin |
| Project dependency | Jackson, JUnit, JDBC driver | Được ứng dụng hoặc test sử dụng |
| Build script dependency | Thư viện được dùng trong logic build script | Mở rộng build logic, script hoặc convention plugin |
| Parent POM/BOM | Parent POM, dependency BOM | Kế thừa cấu hình hoặc quản lý version |
| Metadata | POM, Gradle Module Metadata, Maven snapshot metadata | Mô tả version, variant, dependency và vị trí artifact |
| Publication artifact | JAR, POM, sources, Javadoc, ZIP | Được upload lên repository để consumer sử dụng |

Không phải tất cả thành phần đều được phân giải qua cùng một cấu hình repository. Vì vậy, khi lỗi ghi "Could not resolve plugin" cần kiểm tra nơi khai báo plugin repository; khi lỗi ghi "Could not resolve dependency" cần kiểm tra dependency repository; khi upload thất bại cần kiểm tra publication repository và quyền ghi.

## 2. Phân biệt plugin resolution và dependency resolution

Đây là bước đầu tiên quan trọng nhất. Một repository đã được khai báo cho dependency của ứng dụng không có nghĩa build tool sẽ tự dùng nó để tải plugin.

### 2.1. Maven

Maven có các cấu hình riêng:

- repositories: nơi Maven tìm dependency của project.
- pluginRepositories: nơi Maven tìm Maven build plugin.
- distributionManagement: nơi publish artifact của project.
- mirrors trong settings.xml: chuyển yêu cầu repository qua endpoint khác, có thể áp dụng cho cả dependency và plugin repository theo mirror rule.

Ví dụ khai báo dependency repository:

~~~xml
<repositories>
    <repository>
        <id>company-public</id>
        <url>https://repo.example.com/maven-public</url>
    </repository>
</repositories>
~~~

Ví dụ khai báo plugin repository:

~~~xml
<pluginRepositories>
    <pluginRepository>
        <id>company-plugins</id>
        <url>https://repo.example.com/maven-plugins</url>
    </pluginRepository>
</pluginRepositories>
~~~

Nếu Maven tải được dependency nhưng không tải được Maven Compiler Plugin, hãy kiểm tra pluginRepositories, mirror trong settings.xml và cấu hình Maven của môi trường CI. Không nên kết luận rằng toàn bộ repository server đang lỗi chỉ từ một loại resolution.

### 2.2. Gradle

Gradle cũng phân biệt repository cho plugin và dependency:

- pluginManagement.repositories trong settings.gradle hoặc settings.gradle.kts: phân giải plugin được khai báo trong block plugins.
- dependencyResolutionManagement.repositories trong settings hoặc repositories của project: phân giải dependency ứng dụng.
- buildscript.repositories: phân giải dependency cho classpath của build script kiểu cũ.
- publishing.repositories: nơi upload publication.

Ví dụ Kotlin DSL:

~~~kotlin
// settings.gradle.kts
pluginManagement {
    repositories {
        gradlePluginPortal()
        maven {
            url = uri("https://repo.example.com/gradle-plugins")
        }
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
        maven {
            url = uri("https://repo.example.com/maven-public")
        }
    }
}
~~~

Nếu plugin DSL báo không tìm thấy plugin nhưng dependency Maven Central vẫn tải được, hãy kiểm tra pluginManagement.repositories. Nếu build script dùng block buildscript với dependency classpath, kiểm tra buildscript.repositories; block này không tự động lấy repository từ dependencyResolutionManagement.

### 2.3. Plugin marker artifact của Gradle

Với cú pháp:

~~~kotlin
plugins {
    id("com.example.quality") version "1.2.0"
}
~~~

Gradle thường phân giải plugin marker artifact trước, rồi mới tìm implementation artifact. Vì vậy, repository nội bộ chỉ mirror implementation JAR nhưng không có marker artifact có thể làm plugin DSL thất bại.

Nếu tổ chức lưu plugin trong Maven repository nội bộ, hãy xác nhận repository chứa marker artifact mà Gradle cần, hoặc cấu hình pluginManagement.resolutionStrategy để ánh xạ plugin ID sang module implementation theo quy ước của tổ chức.

Ví dụ ánh xạ:

~~~kotlin
pluginManagement {
    repositories {
        maven {
            url = uri("https://repo.example.com/gradle-plugins")
        }
    }
    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == "com.example.quality") {
                useModule("com.example.build:quality-gradle-plugin:1.2.0")
            }
        }
    }
}
~~~

Đây là ví dụ cấu hình ánh xạ plugin ID sang module. Repository phải có đúng module/version và metadata cần thiết. Nếu dùng mapping này, hãy kiểm tra plugin marker có thực sự không được publish và giữ mapping đồng bộ với quy trình phát hành plugin.

## 3. Nhận diện loại lỗi từ thông báo

Mã HTTP hoặc exception trong log thường cung cấp manh mối đầu tiên:

| Thông báo | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| 400 Bad Request | Request sai định dạng, repository policy hoặc server từ chối request | URL, metadata, request và log repository manager |
| 401 Unauthorized | Thiếu hoặc sai thông tin xác thực | Credential, server ID, token hết hạn |
| 403 Forbidden | Đã nhận diện client nhưng không có quyền hoặc bị policy chặn | Quyền đọc/ghi, repository policy, IP/network policy |
| 404 Not Found | URL hoặc artifact không tồn tại tại endpoint được hỏi | Tọa độ, version, repository, classifier, metadata |
| 407 Proxy Authentication Required | Proxy yêu cầu xác thực | Proxy host/port và credential proxy |
| 408 Request Timeout | Request hết thời gian chờ ở server/gateway | Kết nối, tải server và timeout |
| 409 Conflict | Xung đột khi upload hoặc version đã tồn tại theo policy | Release immutability, version và deployment rules |
| 429 Too Many Requests | Bị giới hạn tần suất | Rate limit, retry/backoff, cache/proxy |
| 500/502/503/504 | Repository manager, gateway hoặc upstream gặp lỗi | Trạng thái server, proxy upstream, retry và vận hành |
| UnknownHostException | DNS không phân giải được hostname | DNS, VPN, hostname và network |
| ConnectException / Connection refused | Kết nối TCP bị từ chối | Host, port, firewall, service đang chạy |
| SocketTimeoutException / Read timed out | Kết nối hoặc phản hồi quá chậm | Proxy, network, server load, timeout |
| PKIX path building failed | JVM không xây dựng được certificate trust chain | CA, truststore, certificate chain, proxy TLS inspection |
| Hostname mismatch | Certificate không khớp hostname | URL và certificate server |
| Checksum validation failed | Digest tải được không khớp metadata/checksum | Artifact bị lỗi, cache, proxy hoặc publish không hoàn chỉnh |
| Could not find artifact/module | Không tìm được tọa độ hoặc version phù hợp | Repository, coordinates, metadata và publication |

Mã lỗi có thể được repository manager cố ý thay đổi vì lý do bảo mật. Ví dụ một số server trả 404 cho cả artifact không tồn tại và artifact người dùng không được phép đọc. Hãy xem log server hoặc hỏi quản trị viên khi status code chưa đủ để kết luận.

## 4. Kiểm tra tọa độ artifact trước khi sửa network

Nhiều lỗi tải thư viện thực chất là lỗi khai báo dependency.

Với Maven, tọa độ thường có dạng:

~~~text
groupId:artifactId:version
~~~

Ví dụ:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.17.2</version>
</dependency>
~~~

Trong Maven repository layout, groupId được chuyển thành đường dẫn bằng dấu slash. Ví dụ:

~~~text
com/fasterxml/jackson/core/jackson-databind/2.17.2/
    jackson-databind-2.17.2.pom
    jackson-databind-2.17.2.jar
~~~

Kiểm tra các chi tiết:

- groupId có đúng từng segment không?
- artifactId có chính xác, kể cả dấu gạch nối và chữ hoa/thường không?
- version có được publish không?
- Dependency có classifier hoặc type đặc biệt không?
- Repository có đúng loại release/snapshot không?
- Có exclusion hoặc dependency management làm thay đổi version không?

Ví dụ khai báo classifier sai có thể khiến Maven tìm file không tồn tại dù JAR chính đã được publish. Một dependency có classifier tests không tương đương với JAR chính.

### 4.1. Release và SNAPSHOT

Maven thường phân biệt version release như 1.4.0 và snapshot như 1.5.0-SNAPSHOT. Repository có thể bật/tắt chính sách release và snapshot riêng.

Ví dụ repository chỉ cho release:

~~~xml
<repository>
    <id>company-releases</id>
    <url>https://repo.example.com/maven-releases</url>
    <releases>
        <enabled>true</enabled>
    </releases>
    <snapshots>
        <enabled>false</enabled>
    </snapshots>
</repository>
~~~

Nếu project yêu cầu 1.5.0-SNAPSHOT nhưng endpoint chỉ phục vụ release, Maven có thể không tìm thấy artifact. Kiểm tra cả repository policy trong POM/settings và policy trên repository manager.

Snapshot thường sử dụng metadata để ánh xạ version dạng -SNAPSHOT sang timestamped artifact. Nếu metadata cũ hoặc publish bị gián đoạn, client có thể tìm một snapshot build cũ hoặc không tìm thấy file mới.

### 4.2. Version được quản lý gián tiếp

Version có thể đến từ Maven parent POM, BOM trong dependencyManagement, Gradle version catalog, platform hoặc constraint. Khi log báo đang tải một version không như mong đợi, hãy xem version thực tế được resolve chứ không chỉ đọc dependency declaration trực tiếp.

Với Maven:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Các lệnh này giúp xác định version và đường đi dependency. Nếu artifact không được tải vì một version khác đang được chọn, cần sửa dependency management/constraint hoặc khai báo version theo chính sách dự án.

## 5. Repository URL và cấu trúc endpoint

Repository URL phải trỏ đến endpoint tương thích với giao thức mà build tool đang sử dụng. Một số URL là root của repository; một số là group/virtual repository; một số là endpoint upload riêng.

Ví dụ:

~~~text
https://repo.example.com/repository/maven-public/
https://repo.example.com/repository/maven-releases/
https://repo.example.com/repository/maven-snapshots/
~~~

Không nên tự đoán URL từ giao diện web của repository manager. Trang browse UI, REST API, raw storage path và Maven repository endpoint có thể là những URL khác nhau.

Kiểm tra:

1. URL có đúng scheme https và hostname không?
2. Path có đúng repository name hoặc group/virtual repository không?
3. Có path segment thừa hoặc thiếu không?
4. Endpoint có hỗ trợ Maven layout/Gradle metadata không?
5. Client đang đọc hay upload? Read URL và deployment URL có thể khác nhau.
6. Repository có yêu cầu VPN hoặc network nội bộ không?

Đối với repository manager, endpoint group/virtual thường được cung cấp cho consumer đọc dependency; hosted release/snapshot repository có thể là endpoint riêng dành cho publisher. Dùng đúng URL do quản trị viên cung cấp.

## 6. Maven: cấu hình repository, mirror và profile

### 6.1. Repository trong POM

Project có thể khai báo repository trong POM:

~~~xml
<repositories>
    <repository>
        <id>company-public</id>
        <url>https://repo.example.com/repository/maven-public/</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
        </snapshots>
    </repository>
</repositories>
~~~

id là định danh repository và cũng được dùng để ghép với credential trong settings.xml. URL phải là endpoint Maven repository.

### 6.2. Repository trong settings profile

Một tổ chức có thể đặt repository trong settings.xml profile và kích hoạt profile:

~~~xml
<settings>
    <profiles>
        <profile>
            <id>company-repositories</id>
            <repositories>
                <repository>
                    <id>company-public</id>
                    <url>https://repo.example.com/repository/maven-public/</url>
                </repository>
            </repositories>
            <pluginRepositories>
                <pluginRepository>
                    <id>company-plugins</id>
                    <url>https://repo.example.com/repository/maven-plugins/</url>
                </pluginRepository>
            </pluginRepositories>
        </profile>
    </profiles>
    <activeProfiles>
        <activeProfile>company-repositories</activeProfile>
    </activeProfiles>
</settings>
~~~

Nếu repository hoạt động trên máy developer nhưng không hoạt động trong CI, hãy so sánh settings file, active profiles, mirror và environment của hai nơi.

### 6.3. Mirror

Mirror chuyển yêu cầu repository sang endpoint khác. Ví dụ tổ chức muốn mọi yêu cầu Maven đi qua repository manager nội bộ:

~~~xml
<settings>
    <mirrors>
        <mirror>
            <id>company-mirror</id>
            <mirrorOf>*</mirrorOf>
            <url>https://repo.example.com/repository/maven-public/</url>
        </mirror>
    </mirrors>
</settings>
~~~

mirrorOf xác định repository nào được thay thế. Quy tắc có thể dùng wildcard hoặc loại trừ repository cụ thể. Nếu mirror áp dụng quá rộng, Maven có thể gửi cả yêu cầu plugin hoặc repository đặc biệt đến endpoint không chứa các artifact đó.

Khi một artifact có vẻ tồn tại ở Maven Central nhưng không tải được qua mirror nội bộ, kiểm tra:

- Mirror có được chọn cho repository đó không?
- Repository manager có proxy đúng upstream không?
- Cache/proxy có lỗi hoặc metadata cũ không?
- Policy của group repository có bao gồm hosted/proxy repository cần thiết không?

### 6.4. Credential trong settings.xml

Credential Maven thường đặt trong servers của settings.xml:

~~~xml
<settings>
    <servers>
        <server>
            <id>company-public</id>
            <username>BUILD_USER</username>
            <password>BUILD_TOKEN_FROM_SECRET_STORE</password>
        </server>
    </servers>
</settings>
~~~

Giá trị id trong server phải khớp repository hoặc mirror ID thực tế mà Maven dùng. Nếu request đi qua mirror có ID company-mirror, credential có thể cần gắn với ID mirror thay vì ID repository ban đầu.

Không commit password/token thật vào POM hoặc repository source. CI nên sinh/cung cấp settings file từ secret store hoặc dùng cơ chế credential được tổ chức phê duyệt. Khi bật -X, cần cẩn thận không chia sẻ log có thông tin nhạy cảm.

### 6.5. Effective settings và effective POM

Khi cấu hình kế thừa nhiều lớp, hãy xem cấu hình thực tế Maven đã hợp nhất:

~~~bash
./mvnw help:effective-settings
./mvnw help:effective-pom
~~~

Kiểm tra active profile, mirror, repository URL, plugin repository và distribution management. Nếu lệnh Help Plugin cũng không tải được, dùng log Maven và đọc trực tiếp settings file đang được launcher chọn.

## 7. Gradle: cấu hình repository và thứ tự phân giải

### 7.1. Dependency repository

Kotlin DSL:

~~~kotlin
repositories {
    mavenCentral()
    maven {
        name = "companyPublic"
        url = uri("https://repo.example.com/repository/maven-public/")
    }
}
~~~

Groovy DSL:

~~~groovy
repositories {
    mavenCentral()
    maven {
        name = 'companyPublic'
        url = uri('https://repo.example.com/repository/maven-public/')
    }
}
~~~

Gradle truy vấn repository theo quy tắc resolution và metadata của module. Không nên thêm hàng loạt repository công khai/ngẫu nhiên chỉ để làm lỗi biến mất; điều đó có thể khiến cùng tọa độ được lấy từ nguồn không mong muốn.

### 7.2. Repository trong settings

Tổ chức có thể tập trung dependency repository trong settings:

~~~kotlin
// settings.gradle.kts
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
        maven {
            name = "companyPublic"
            url = uri("https://repo.example.com/repository/maven-public/")
        }
    }
}
~~~

repositoriesMode quy định quan hệ giữa repository trong settings và repository được khai báo trong project build script. Nếu dùng FAIL_ON_PROJECT_REPOS, một project tự khai báo repository có thể làm build thất bại theo policy. Hãy kiểm tra mode hiện tại trước khi thêm repository vào build script.

### 7.3. Plugin repository

Plugin DSL cần repository trong pluginManagement:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        maven {
            name = "companyPlugins"
            url = uri("https://repo.example.com/repository/gradle-plugins/")
        }
    }
}
~~~

Nếu một plugin không tồn tại ở Gradle Plugin Portal nhưng được publish nội bộ, endpoint nội bộ cần được khai báo tại đây. Repository dependency bình thường không tự động thay thế plugin repository.

### 7.4. Buildscript repository

Build script kiểu cũ có thể tải plugin/library cho chính build:

~~~groovy
buildscript {
    repositories {
        mavenCentral()
        maven {
            url 'https://repo.example.com/repository/build-tools/'
        }
    }
    dependencies {
        classpath 'com.example:legacy-build-plugin:1.2.0'
    }
}
~~~

Đây là classpath của build script. Nếu lỗi xuất hiện ở buildscript classpath, hãy kiểm tra repository trong block buildscript, không chỉ repositories dành cho dependency ứng dụng.

### 7.5. Repository content filter và exclusive content

Gradle hỗ trợ giới hạn repository nào được phép phục vụ một nhóm module. Content filter giúp tránh truy vấn nhầm nguồn và giảm nguy cơ lấy package nội bộ từ repository công khai.

Ví dụ:

~~~kotlin
repositories {
    maven {
        name = "companyInternal"
        url = uri("https://repo.example.com/repository/internal/")
        content {
            includeGroupByRegex("com\\.example(\\..*)?")
        }
    }
    mavenCentral()
}
~~~

Nếu filter không khớp group thực tế, Gradle sẽ không hỏi repository đó cho module cần thiết. Khi nhận lỗi module không tìm thấy dù artifact tồn tại, kiểm tra content filter, exclusive content và repository mode.

## 8. Xác thực: 401, 403 và 407

### 8.1. 401 Unauthorized

401 thường có nghĩa server yêu cầu credential nhưng client không gửi hoặc gửi credential không hợp lệ.

Kiểm tra:

- Username/token có đúng không?
- Token đã hết hạn hoặc bị thu hồi chưa?
- Credential có được cấp trong môi trường CI không?
- Maven server ID có khớp repository/mirror ID không?
- Gradle có đọc đúng environment variable/secret không?
- Request đang đến đúng repository host không?

Không nên giải quyết 401 bằng cách chuyển repository sang HTTP hoặc tắt xác thực. Hãy sửa credential và cơ chế cung cấp secret.

### 8.2. 403 Forbidden

403 thường cho biết client đã được nhận diện nhưng không có quyền thực hiện hành động, hoặc request bị policy chặn. Một số repository manager cũng dùng 403 khi user không được phép nhìn thấy repository.

Phân biệt quyền:

- Read/download: quyền lấy artifact.
- Browse: quyền xem nội dung qua giao diện.
- Add/deploy: quyền publish artifact.
- Delete/overwrite: quyền xóa hoặc thay thế artifact.

Developer có thể có quyền đọc nhưng không có quyền publish. CI release job có thể có quyền deploy vào release repository còn CI pull request chỉ có quyền đọc.

### 8.3. 407 Proxy Authentication Required

407 là phản hồi từ proxy, không nhất thiết từ artifact repository. Kiểm tra proxy host, port và thông tin xác thực proxy. Credential proxy khác credential repository; không dùng server ID Maven repository để sửa lỗi proxy authentication.

## 9. Maven và Gradle: cấu hình proxy

### 9.1. Maven proxy trong settings.xml

Ví dụ cấu hình proxy:

~~~xml
<settings>
    <proxies>
        <proxy>
            <id>corporate-proxy</id>
            <active>true</active>
            <protocol>http</protocol>
            <host>proxy.example.com</host>
            <port>8080</port>
            <nonProxyHosts>localhost|127.0.0.1|*.internal.example.com</nonProxyHosts>
        </proxy>
    </proxies>
</settings>
~~~

Nếu proxy yêu cầu authentication, Maven settings có các trường username/password tương ứng. Credential phải được giữ trong cấu hình riêng tư và không commit.

nonProxyHosts xác định hostname được kết nối trực tiếp. Nếu repository nội bộ nằm trong danh sách này nhưng network yêu cầu đi qua proxy (hoặc ngược lại), kết nối có thể thất bại.

### 9.2. Gradle proxy qua system properties

Gradle/JVM có thể nhận proxy properties trong gradle.properties:

~~~properties
systemProp.http.proxyHost=proxy.example.com
systemProp.http.proxyPort=8080
systemProp.https.proxyHost=proxy.example.com
systemProp.https.proxyPort=8080
systemProp.http.nonProxyHosts=localhost|127.0.0.1|*.internal.example.com
~~~

Nếu proxy yêu cầu username/password, Gradle/JVM có các system property tương ứng, nhưng nên cấp secret qua môi trường bảo mật của CI và tránh lưu giá trị nhạy cảm trong file được commit.

Không phải mọi transport hoặc plugin đều dùng cấu hình proxy theo cùng cách. Nếu một request đi qua custom client, kiểm tra tài liệu plugin và cách client đó nhận proxy configuration.

### 9.3. Phân biệt proxy với repository mirror

Proxy network chuyển tiếp kết nối HTTP(S) ra ngoài. Repository proxy là một repository manager nhận request Maven/Gradle rồi cache hoặc chuyển tiếp artifact đến upstream. Hai lớp này có thể cùng tồn tại:

~~~text
Maven / Gradle
      |
      v
Corporate HTTP proxy (nếu cần)
      |
      v
Repository manager nội bộ
      |
      v
Upstream repository
~~~

Nếu request đến repository manager nội bộ thành công nhưng repository manager không tải được Maven Central, vấn đề nằm ở upstream/proxy của repository manager. Developer không thể sửa bằng cách thay credential của project nếu lỗi xảy ra ở tầng server-to-server.

## 10. TLS, certificate và lỗi PKIX

Khi truy cập HTTPS, JVM kiểm tra certificate chain của server. Lỗi phổ biến:

~~~text
PKIX path building failed
unable to find valid certification path to requested target
~~~

Nó thường có nghĩa JVM không tin cậy CA phát hành certificate hoặc không nhận được chain phù hợp. Một số nguyên nhân:

- Repository dùng certificate từ CA nội bộ chưa được thêm vào truststore của JDK.
- Corporate proxy thực hiện TLS inspection và thay certificate bằng CA của tổ chức.
- Server thiếu intermediate certificate.
- Certificate hết hạn hoặc chưa có hiệu lực.
- URL dùng hostname không khớp Subject Alternative Name của certificate.
- CI dùng JDK/truststore khác máy developer.
- Đồng hồ hệ thống sai khiến certificate có vẻ chưa có hiệu lực hoặc đã hết hạn.

### 10.1. Kiểm tra certificate và hostname

Trước tiên, xác nhận hostname trong repository URL đúng với hostname certificate. Không truy cập qua IP hoặc alias không có trong SAN nếu server không hỗ trợ alias đó.

Có thể xem certificate chain bằng công cụ phù hợp trên môi trường:

~~~bash
openssl s_client -connect repo.example.com:443 -servername repo.example.com -showcerts
~~~

Trên Windows có thể dùng trình duyệt, PowerShell hoặc công cụ quản trị certificate để xem issuer, validity và SAN. Kết quả của OpenSSL giúp quan sát chain nhưng không tự chứng minh JVM tin cậy certificate.

### 10.2. Thêm CA nội bộ vào truststore

Nếu tổ chức dùng CA nội bộ, lấy certificate CA từ nguồn quản trị đáng tin cậy và xác minh fingerprint qua kênh độc lập. Sau đó quản trị truststore dành cho JDK/CI theo chính sách của tổ chức.

Có thể chỉ định truststore riêng cho một JVM:

~~~text
-Djavax.net.ssl.trustStore=/path/to/company-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Nếu truststore có password, cấp qua secret store hoặc cơ chế bảo mật của CI. Không ghi password thật vào build file hoặc log.

Không nên tắt certificate validation, dùng trust-all manager hoặc bật tùy chọn insecure protocol để làm build qua được. Cách đó bỏ mất xác minh server và có thể khiến dependency bị thay thế trên đường truyền.

### 10.3. TLS version và proxy inspection

Một số lỗi handshake do client và server không có TLS protocol/cipher suite tương thích hoặc do proxy inspection. Kiểm tra:

- JDK version và security policy.
- Repository server/proxy có hỗ trợ TLS version hiện đại không?
- Certificate chain mà JVM thực sự nhận được.
- Có proxy can thiệp HTTPS không?
- Có khác biệt giữa JDK developer và JDK CI không?

Không nên hạ TLS xuống phiên bản cũ hoặc bật cipher yếu như giải pháp mặc định. Cần phối hợp với quản trị viên repository/network để sửa cấu hình server và trust chain.

## 11. DNS, firewall và kết nối mạng

### 11.1. UnknownHostException

Lỗi này cho biết JVM không phân giải được hostname thành địa chỉ IP. Kiểm tra:

- Hostname có chính xác không?
- DNS của máy/CI có phân giải được không?
- VPN hoặc mạng nội bộ đã kết nối chưa?
- CI runner có quyền truy cập DNS nội bộ không?
- Proxy có cần thiết để truy cập host bên ngoài không?

Các lệnh kiểm tra trên Windows:

~~~powershell
Resolve-DnsName repo.example.com
Test-NetConnection repo.example.com -Port 443
~~~

Trên Linux/macOS có thể dùng:

~~~bash
getent hosts repo.example.com
curl -I https://repo.example.com/
~~~

Endpoint repository có thể không cho truy cập root path hoặc trả status không phải 200. Mục tiêu của lệnh là kiểm tra DNS/kết nối HTTP(S), không phải xác nhận một tọa độ artifact cụ thể tồn tại.

### 11.2. Connection refused hoặc timeout

Connection refused thường cho biết host đã phản hồi nhưng port không nhận kết nối, service không chạy hoặc firewall từ chối. Timeout có thể do route, VPN, firewall, proxy, server quá tải hoặc packet bị drop.

Kiểm tra port và network path trước khi thay dependency version. Nếu mọi artifact trên cùng hostname đều timeout, khả năng cao là network/server chứ không phải tọa độ Maven.

### 11.3. Không dùng ping làm bằng chứng duy nhất

Một server có thể chặn ICMP nhưng vẫn phục vụ HTTPS. Ping thất bại không chứng minh repository không truy cập được. Hãy kiểm tra DNS và TCP port thực tế của endpoint, sau đó thử một HTTP request phù hợp.

## 12. Offline mode, cache và metadata cũ

Build tool có thể giữ dependency đã tải trong local cache. Điều này giúp build nhanh và có thể hỗ trợ offline build, nhưng cũng có thể che lỗi repository hoặc giữ metadata cũ.

### 12.1. Maven offline và update

Chạy Maven offline:

~~~bash
./mvnw -o package
~~~

Ở chế độ offline, Maven không truy cập remote repository. Nếu dependency hoặc plugin chưa có trong local repository, build sẽ thất bại dù remote server đang hoạt động.

Maven có thể được yêu cầu kiểm tra cập nhật/snapshot:

~~~bash
./mvnw -U clean verify
~~~

-U yêu cầu Maven kiểm tra các snapshot được cập nhật và artifact release bị thiếu trước đó theo cơ chế update. Nó không sửa URL sai, credential sai hoặc artifact chưa được publish.

Maven lưu thông tin lỗi tải trong local repository, có thể gồm file .lastUpdated. Nếu nghi ngờ trạng thái cache lỗi, hãy dùng -U trước. Chỉ xóa đúng thư mục artifact/version bị lỗi khi đã xác định cần làm mới; không xóa toàn bộ ~/.m2/repository như bước đầu tiên.

### 12.2. Gradle offline và refresh

Gradle offline:

~~~bash
./gradlew --offline build
~~~

Build chỉ dùng những dependency/metadata đã có trong cache. Nếu thiếu module, build không thể tải mới.

Yêu cầu Gradle làm mới dependency metadata:

~~~bash
./gradlew --refresh-dependencies build
~~~

Gradle sẽ kiểm tra lại trạng thái dependency theo cơ chế cache của nó. Điều này không nhất thiết tải lại mọi file nếu nội dung và metadata vẫn được xác định là giống nhau.

Nếu dependency resolve sai do metadata cache, --refresh-dependencies có thể giúp. Nếu repository URL, quyền hoặc version sai, cần sửa cấu hình gốc.

### 12.3. Phân biệt cache dependency với build output cache

Gradle dependency cache lưu metadata/artifact đã resolve. Build cache lưu output task có thể tái sử dụng. Đây là hai loại cache khác nhau.

- Dependency cache lỗi: xem repository, metadata, artifact và --refresh-dependencies.
- Build output cache lỗi: xem task inputs/outputs, cache key và --no-build-cache.

Không nên xóa build cache để sửa 401/PKIX khi tải dependency. Cũng không nên xóa dependency cache để sửa task custom khai báo input sai.

## 13. Missing artifact: repository có hoạt động nhưng file không tồn tại

Nếu server trả 404, hãy kiểm tra artifact thực tế đã được publish chưa.

Với Maven, kiểm tra đường dẫn tương ứng GAV, classifier và extension. Ví dụ:

~~~text
vn/acme/platform/platform-api/2.1.0/
    platform-api-2.1.0.pom
    platform-api-2.1.0.jar
~~~

Nếu chỉ có POM nhưng thiếu JAR, dependency có thể là POM-only/BOM hoặc publication bị thiếu binary. Nếu project khai báo JAR nhưng repository chỉ chứa POM, resolution có thể thất bại khi tải artifact.

Các nguyên nhân khác:

- Build chỉ chạy mvn install, chưa mvn deploy.
- Artifact chỉ nằm trong local repository của máy publish.
- Gradle task tạo JAR nhưng publication không attach JAR.
- Publish sai repository (snapshot thay vì release hoặc ngược lại).
- Version trong consumer không trùng version được publish.
- Classifier/type sai.
- Repository manager chưa đồng bộ/cache metadata.
- Release bị từ chối vì version đã tồn tại và policy không cho overwrite.

Đối với artifact nội bộ, xác nhận tọa độ và file trong repository manager hoặc hỏi nhóm sở hữu artifact. Không tự tạo file rỗng cùng tọa độ để vượt qua resolution.

## 14. Metadata lỗi hoặc không nhất quán

Build tool không chỉ tải JAR. Nó thường tải POM, Gradle Module Metadata hoặc Maven metadata trước để xác định dependency graph và artifact cần lấy.

### 14.1. POM thiếu hoặc sai

Một POM không hợp lệ có thể khiến Maven không đọc được dependency hoặc metadata. Một POM thiếu dependency runtime có thể làm consumer compile được nhưng thiếu thư viện lúc chạy.

Kiểm tra:

- POM có được publish cùng JAR không?
- XML có hợp lệ không?
- Parent POM/BOM được tham chiếu có tồn tại không?
- Dependency version có được quản lý đúng không?
- Scope và optional có phản ánh đúng hợp đồng thư viện không?

### 14.2. Gradle Module Metadata

Gradle có thể sử dụng file .module ngoài POM Maven để biểu diễn variants và attributes. Nếu metadata này lỗi hoặc tham chiếu artifact không tồn tại, consumer Gradle có thể resolve khác với Maven consumer.

Khi Maven tải được nhưng Gradle thất bại, kiểm tra:

- Repository có phục vụ .module không?
- Metadata có được publish đúng không?
- Variant/attribute có phù hợp consumer không?
- Publication có upload đầy đủ file được metadata tham chiếu không?
- Có rule metadataSources thay đổi cách Gradle đọc metadata không?

### 14.3. Snapshot metadata

Maven snapshot metadata ánh xạ version -SNAPSHOT sang timestamped artifact. Nếu upload bị ngắt giữa chừng hoặc metadata không được cập nhật đúng, client có thể nhận metadata trỏ đến file không có.

Khi lỗi chỉ xảy ra với SNAPSHOT:

1. Xác nhận snapshot repository được bật.
2. Kiểm tra metadata của version snapshot.
3. Xác nhận publisher đã upload đầy đủ POM và binary.
4. Kiểm tra repository manager có cache metadata cũ không.
5. Làm mới metadata ở client sau khi xác nhận server đã hoàn tất publish.

## 15. Checksum mismatch và artifact bị hỏng

Checksum mismatch có thể do:

- Upload chưa hoàn tất hoặc file bị cắt cụt.
- Proxy/cache trả về nội dung cũ hoặc lỗi.
- Metadata checksum không khớp artifact.
- Repository manager đồng bộ không hoàn chỉnh.
- Artifact bị thay đổi sau khi checksum được tạo.
- Cùng một release version bị ghi đè trái policy.

Hãy xác minh hash của file ở nơi publish và file tải về. Nếu repository cung cấp checksum riêng, so sánh với digest tự tính. Với artifact có chữ ký, xác minh chữ ký theo trust policy.

Không tắt checksum validation chỉ để build thành công. Nếu checksum không khớp, cần xác định nguồn tạo ra sai khác và tải/publish lại artifact hợp lệ.

## 16. Upload artifact: đọc được không có nghĩa ghi được

Một developer có thể tải dependency thành công nhưng không có quyền publish. Với Maven, nơi publish thường được khai báo trong distributionManagement:

~~~xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.com/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.com/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
~~~

Credential cần khớp ID trong settings.xml. Release version và snapshot version có thể được gửi đến endpoint khác nhau.

Với Gradle Maven Publish:

~~~kotlin
publishing {
    repositories {
        maven {
            name = "companyReleases"
            url = uri("https://repo.example.com/repository/maven-releases/")
            credentials {
                username = System.getenv("REPO_USER")
                password = System.getenv("REPO_TOKEN")
            }
        }
    }
}
~~~

Trong thực tế, cần kiểm tra biến môi trường có được cấp và không rỗng trước khi publish. Không in giá trị credential ra log.

### 16.1. Version release bất biến

Nhiều repository manager không cho phép ghi đè release version đã tồn tại. Upload cùng GAV lần thứ hai có thể trả 400 hoặc 409. Đây thường là chính sách bảo vệ tính bất biến của release.

Giải pháp là phát hành version mới theo quy tắc versioning, hoặc dùng snapshot repository cho bản phát triển. Không nên thay binary dưới cùng release coordinate vì consumer có thể nhận các nội dung khác nhau cho cùng một version.

### 16.2. Publish thiếu artifact

Nếu upload thành công JAR chính nhưng thiếu Sources/Javadoc/POM hoặc metadata, kiểm tra publication đã attach đủ artifact hay chưa. Với Maven, kiểm tra plugin execution và deploy log. Với Gradle, kiểm tra MavenPublication có lấy component Java hoặc khai báo artifact bổ trợ rõ không.

## 17. Rate limit, retry và repository manager

Một repository công khai hoặc proxy có thể giới hạn request theo IP, token hoặc thời gian. Lỗi 429 thường cho biết client gửi quá nhiều request hoặc vượt quota. Lỗi 503/504 có thể do upstream chậm hoặc repository manager quá tải.

Hướng xử lý:

- Dùng repository manager/cache nội bộ nếu tổ chức cung cấp.
- Tránh chạy nhiều build không cần thiết đồng thời.
- Giữ dependency version ổn định và tận dụng cache hợp lý.
- Kiểm tra Retry-After nếu server cung cấp.
- Dùng retry/backoff có giới hạn thay vì vòng lặp liên tục.
- Báo quản trị viên repository khi lỗi xảy ra trên nhiều project/runner.

Không nên thêm nhiều repository public khác nhau như một cách né rate limit. Điều đó có thể gây tải lặp lại và làm dependency provenance khó kiểm soát.

## 18. Quy trình chẩn đoán theo từng bước

Khi build báo không tải được plugin hoặc thư viện, thực hiện theo thứ tự sau:

**Bước 1 — Ghi lại artifact và giai đoạn lỗi.** Xác định tên plugin/dependency, version, classifier nếu có, repository URL và task/phase đang chạy. Đừng chỉ ghi lại dòng cuối "build failed".

**Bước 2 — Phân loại resolution.** Xác định đó là Gradle plugin, Maven plugin, buildscript dependency, project dependency, parent/BOM hay publication. Kiểm tra đúng repository block.

**Bước 3 — Phân loại lỗi.** Nhìn status HTTP hoặc exception: 401/403/407 là auth/policy; 404 là endpoint/coordinates/metadata; PKIX là TLS trust; UnknownHost là DNS; timeout là network/server; checksum là integrity.

**Bước 4 — Kiểm tra tọa độ và repository policy.** Xác nhận group, artifact, version, classifier, extension, release/snapshot và endpoint.

**Bước 5 — Kiểm tra credential và proxy.** Xác nhận secret có mặt, ID khớp, token còn hiệu lực, proxy/network đúng. Không chia sẻ secret trong log.

**Bước 6 — Kiểm tra metadata và server.** Xác nhận artifact/POM/module metadata có thật và repository manager đã proxy/cache/publish đầy đủ.

**Bước 7 — Kiểm tra cache/offline.** Xác nhận không bật offline ngoài ý muốn. Dùng refresh có mục tiêu khi metadata/cache có khả năng cũ.

**Bước 8 — Thu thập log chi tiết và tái hiện tối thiểu.** Chạy một lệnh resolve nhỏ với log phù hợp. Không bật debug rộng rồi công khai log chứa credential.

**Bước 9 — Sửa nguyên nhân ở đúng lớp.** Sửa coordinates, repository, credentials, proxy, truststore, metadata hoặc publication. Tránh workaround làm giảm bảo mật.

**Bước 10 — Xác nhận bằng build sạch và CI.** Kiểm tra cả môi trường developer lẫn runner CI có cùng repository policy và quyền truy cập cần thiết.

## 19. Lệnh chẩn đoán Maven

Một số lệnh hữu ích:

~~~bash
# Xem version Maven và JVM đang dùng
./mvnw -version

# Hiển thị cấu hình settings đã hợp nhất
./mvnw help:effective-settings

# Hiển thị POM sau khi kế thừa/profile được áp dụng
./mvnw help:effective-pom

# Xem dependency graph
./mvnw dependency:tree

# Yêu cầu kiểm tra lại snapshot và artifact release bị thiếu
./mvnw -U clean verify

# Chạy offline để xác định build có phụ thuộc remote artifact chưa cache không
./mvnw -o package

# Log debug chi tiết
./mvnw -X -e clean verify
~~~

-X có thể tạo log rất dài và một số plugin có thể ghi thông tin môi trường nhạy cảm. Trước khi gửi log cho người khác, loại bỏ token, username nhạy cảm, URL có credential nhúng và dữ liệu nội bộ.

Khi cần kiểm tra một dependency cụ thể, có thể dùng Maven Dependency Plugin goal dependency:get với tọa độ đã biết, nếu plugin đó có thể được resolve:

~~~bash
./mvnw dependency:get -Dartifact=com.fasterxml.jackson.core:jackson-databind:2.17.2
~~~

Nếu goal này cũng thất bại vì không tải được plugin hoặc repository, nó không chứng minh tọa độ dependency sai; hãy đọc lỗi resolution đầu tiên trong log.

## 20. Lệnh chẩn đoán Gradle

~~~bash
# Xem Gradle version và JVM
./gradlew --version

# Xem dependency graph của runtime
./gradlew dependencies --configuration runtimeClasspath

# Xem lý do một module/version được chọn
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath

# Log thông tin
./gradlew build --info

# Log debug sâu hơn khi cần
./gradlew build --debug

# Làm mới dependency metadata/cache
./gradlew --refresh-dependencies build

# Chạy offline để xác định thành phần nào chưa có trong cache
./gradlew --offline build
~~~

Với plugin resolution, xem phần pluginManagement trong settings và log đầu build. dependencies --configuration runtimeClasspath không hiển thị plugin marker resolution như dependency ứng dụng. Dùng --info hoặc --debug để xem request plugin/repository, đồng thời kiểm tra settings file được build thực sự sử dụng.

## 21. Ma trận triệu chứng và hướng xử lý

| Triệu chứng | Kiểm tra đầu tiên | Hướng khắc phục thường gặp |
|---|---|---|
| Maven tải dependency được nhưng plugin không tải được | pluginRepositories, mirror, plugin version | Khai báo đúng plugin repository hoặc sửa mirror |
| Gradle tải dependency được nhưng plugin DSL thất bại | pluginManagement.repositories, plugin marker | Thêm đúng plugin repository/marker hoặc mapping plugin ID |
| 401 từ repository | Credential, token, ID khớp | Cấp lại token và ghép đúng server/repository ID |
| 403 khi download | Quyền read, policy, IP restriction | Cấp quyền đọc hoặc sửa policy/network |
| 403/409 khi deploy | Quyền write hoặc release đã tồn tại | Cấp quyền publish phù hợp hoặc phát hành version mới |
| 407 | Proxy authentication | Cấu hình credential proxy |
| 404 cho dependency nội bộ | Coordinates, version, endpoint, publication | Publish đúng artifact hoặc sửa tọa độ/repository |
| 404 cho plugin | Plugin repository/marker hoặc version | Kiểm tra plugin portal, marker artifact và version |
| PKIX path building failed | CA/truststore/JDK/proxy inspection | Cài CA tin cậy vào truststore phù hợp |
| Hostname mismatch | Repository URL và certificate SAN | Dùng hostname đúng hoặc sửa certificate server |
| UnknownHostException | DNS/VPN | Sửa DNS hoặc kết nối mạng nội bộ |
| Connection timeout | Firewall/proxy/server load | Kiểm tra TCP route, proxy và trạng thái server |
| 429 | Rate limit | Dùng cache/proxy, giảm request và retry có backoff |
| Checksum mismatch | Artifact/cache/proxy/publish | Xác minh file và tải/publish lại artifact hợp lệ |
| SNAPSHOT không thấy bản mới | Snapshot policy và metadata | Kiểm tra metadata, publish hoàn chỉnh và refresh |
| Chỉ CI thất bại | Settings, secrets, JDK, network runner | Đồng bộ cấu hình và cấp quyền đúng cho CI |
| Chỉ máy local thất bại | VPN, proxy, local settings/cache | Kiểm tra môi trường local và cache có mục tiêu |

## 22. Bảo mật khi chẩn đoán và truy cập repository

Repository credentials có thể cấp quyền đọc source nội bộ, package chưa phát hành hoặc publish release. Hãy coi token repository như secret có giá trị.

Thực hành tốt:

- Lưu credential trong secret store hoặc settings file ngoài source repository.
- Dùng token có phạm vi và thời hạn phù hợp.
- Tách quyền read, publish snapshot và publish release.
- Không nhúng username/password vào URL repository.
- Không commit settings.xml, gradle.properties có secret hoặc file cấu hình cá nhân.
- Không in credential trong build log.
- Khi gửi log debug, che token, authorization header, proxy password và URL nhạy cảm.
- Dùng HTTPS và truststore đúng; không tắt TLS verification.
- Giới hạn repository được phép phục vụ group nội bộ để tránh dependency confusion.
- Kiểm soát version và provenance của plugin vì plugin chạy code trong tiến trình build.

Đối với Gradle, dependency verification có thể được dùng để xác minh checksum/signature theo metadata được quản lý trong repository source. Khi bật verification, một dependency mới hoặc artifact thay đổi có thể làm build thất bại cho đến khi checksum/signature được kiểm tra và cập nhật có chủ đích. Không nên tắt verification rộng chỉ để vượt qua lỗi.

## 23. Phòng ngừa lỗi repository trong dự án và CI

- Dùng một endpoint repository manager nội bộ được tổ chức duy trì nếu có.
- Tách plugin repositories, dependency repositories và publication repositories theo đúng chức năng.
- Ghi rõ repository ID/name và URL trong cấu hình có kiểm soát.
- Dùng Maven Wrapper/Gradle Wrapper để đồng nhất build tool version.
- Pin version plugin và dependency quan trọng; tránh version động nếu cần build ổn định.
- Cấu hình credential qua secret store, không commit secret.
- Cấp quyền tối thiểu cho developer, CI pull request và release pipeline.
- Dùng mirror/proxy cache đúng cách và theo dõi upstream.
- Giữ release artifact bất biến; dùng snapshot cho bản phát triển.
- Kiểm tra metadata, checksum và chữ ký khi publish/consume theo chính sách.
- Ghi lại JDK, repository endpoint và build tool version trong log môi trường.
- Có thể chạy một bước resolve/dependency warm-up trong CI để phát hiện network/auth issue sớm.

## 24. Những điều cần ghi nhớ

- Trước khi sửa lỗi tải, xác định build đang resolve plugin, dependency ứng dụng, buildscript dependency hay publish artifact.
- Maven dùng repositories, pluginRepositories, distributionManagement và settings.xml mirror cho các vai trò khác nhau.
- Gradle tách pluginManagement.repositories, dependency repositories, buildscript.repositories và publishing.repositories.
- Gradle plugin DSL có thể cần plugin marker artifact; chỉ có implementation JAR chưa chắc đủ.
- 401, 403, 407, 404, PKIX, UnknownHost, timeout, 429 và checksum mismatch chỉ đến các lớp nguyên nhân khác nhau.
- Kiểm tra tọa độ, classifier, version, release/snapshot policy và endpoint trước khi kết luận repository server hỏng.
- Credential repository và proxy là hai loại xác thực khác nhau; ID Maven server phải khớp repository/mirror thực tế.
- PKIX thường liên quan trust chain/JDK/proxy TLS inspection; không tắt TLS validation để né lỗi.
- Offline mode chỉ dùng cache; refresh dependency giúp kiểm tra lại metadata nhưng không sửa cấu hình sai.
- Artifact có thể chưa được publish hoặc publication thiếu file dù build local thành công.
- Checksum mismatch cần điều tra tính toàn vẹn, không nên tắt validation.
- Debug log có thể chứa thông tin nhạy cảm; phải loại bỏ secret trước khi chia sẻ.

Khi Maven hoặc Gradle không tải được plugin hay thư viện, hãy bắt đầu từ tên thành phần và giai đoạn resolution, sau đó phân loại status/exception. Kiểm tra đúng repository block, tọa độ, policy, credential, proxy và truststore; cuối cùng xác nhận artifact/metadata thực sự tồn tại ở endpoint. Cách tiếp cận theo từng lớp giúp sửa đúng nguyên nhân, giữ an toàn cho thông tin xác thực và làm cho build hoạt động nhất quán trên máy developer lẫn CI.
