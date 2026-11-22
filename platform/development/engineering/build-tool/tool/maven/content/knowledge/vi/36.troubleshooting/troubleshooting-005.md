# Lỗi xác thực, proxy, TLS và mirror chặn truy cập kho Maven

## 1. Tại sao một lỗi “Could not transfer artifact” có nhiều nguyên nhân?

Khi Maven tải dependencies, plugins hoặc metadata, thông báo `Could not resolve dependencies`, `Failed to read artifact descriptor`, `Plugin resolution failed` hay `Could not transfer artifact` thường chỉ là **lỗi cấp cao**. Muốn sửa đúng, phải đọc nguyên nhân ở sâu trong log: repository ID, URL, HTTP status hoặc exception của DNS/TCP/TLS/proxy.

Các nhóm triệu chứng chính:

| Triệu chứng trong log | Đối tượng cần xem trước | Không nên làm ngay |
| --- | --- | --- |
| `401 Unauthorized` | Repository/mirror credentials, token, server ID, origin binding | Tắt SSL |
| `403 Forbidden` | Quyền, hosted repo policy, IP restriction, auth gateway | Xin quyền admin vô điều kiện |
| `407 Proxy Authentication Required` | Corporate proxy, proxy username/password | Đổi token Maven Central |
| `PKIX path building failed` | CA chain, truststore của JDK Maven đang chạy | Bật `ssl.insecure` |
| `SSLHandshakeException` | TLS protocol/cert, proxy interception, mTLS | Đổi HTTPS thành HTTP |
| `maven-default-http-blocker` | Maven 3.8.1+ chặn external HTTP | Xóa cơ chế chặn |
| `UnknownHostException` | DNS, hostname, VPN/proxy | Xóa toàn bộ `~/.m2` |
| `Connection refused/timed out` | Host, port, firewall, proxy, service | Thay Java source |
| `404 Not Found` | GAV, version, classifier, URL, mirror/repo content | Tắt hostname validation |
| `429` / `503` | Rate limit, repository manager health, retry policy | Retry vô hạn |
| `Failure was cached` | Local negative cache sau lần tải thất bại | Reset cả máy |

Một câu rất quan trọng: **repo không truy cập được không nhất thiết là Maven Central có sự cố.** Có thể Maven thực tế được định tuyến tới mirror nội bộ, proxy bắt xác thực, corporate CA chưa được JVM tin cậy hoặc HTTP bị Maven chặn có chủ đích.

Bài này hướng dẫn phân biệt lỗi **xác thực repository**, **xác thực proxy**, **TLS certificate/handshake** và **mirror policy**, sau đó kiểm chứng theo quy trình an toàn.

### Mục tiêu

1. Hiểu luồng resolution Maven và các pha plugin/dependency/deploy.
2. Đọc `settings.xml` với `servers`, `mirrors`, `proxies`.
3. Phân biệt 401, 403, 407, PKIX, 404, 429, timeout và blocked mirror.
4. Cấu hình mirror ID, `mirrorOf`, wildcard/exclusions và credentials đúng.
5. Hiểu `maven-default-http-blocker` từ Maven 3.8.1.
6. Sửa proxy/TLS qua cấu hình chính xác, không bỏ qua kiểm tra bảo mật.
7. Hiểu Maven 3.9+ native Resolver HTTP transport và Maven 3.10+/4 origin-scoped credentials.
8. Biết dùng `help:effective-settings`, `effective-pom`, `-U`, `-o`, `-Dmaven.repo.local` đúng mục đích.
9. Thực hành Java 17/Maven/Commons Lang/JUnit với project biên dịch được.
10. Chạy Java 17 checker chỉ xác nhận mirror/server IDs mà **không in mật khẩu**.
11. Tạo triage checklist cho lỗi trên CI, laptop và repository manager.

## 2. Maven chọn URL repository như thế nào?

Một project có POM và dependencies cần resolution theo các bước:

~~~text
pom.xml / parent / Super POM / active profiles
              |
              v
repositories / pluginRepositories
              |
              v
settings.xml mirror selection
(mirror có thể THAY repository ID và URL)
              |
              v
Maven Resolver transport / proxy rules
              |
              v
DNS -> TCP -> proxy CONNECT -> TLS/CA verification
              |
              v
HTTP authentication -> authorization -> artifact request
              |
              v
artifact .pom / .jar / maven-metadata.xml
              |
              v
Maven local repository cache
              |
              v
compile, test, package, install, deploy
~~~

Một lỗi xảy ra trước `compile` không nên được chữa bằng sửa Java code. Nếu plugin `maven-compiler-plugin` chưa tải được, chưa có compiler để thực hiện build. Nếu artifact descriptor `.pom` bị 401, JAR có thể tồn tại nhưng Maven chưa xác định được transitive dependencies.

### 2.1. Ba đường repository khác nhau

| Nguồn cấu hình | Mục đích | Nhầm lẫn thường gặp |
| --- | --- | --- |
| `<repositories>` | Tải thư viện và transitive dependencies | Tưởng nó là nơi deploy project |
| `<pluginRepositories>` | Tải Maven plugins/dependencies của plugins | Chỉ thêm thư viện vào dependencies để chữa plugin lỗi |
| `<distributionManagement>` | Chọn URL ghi artifact khi `mvn deploy` | Tưởng `mvn install` cần upload credential |

Một Nexus/Artifactory thường có **group/proxy repo** dành cho download và **hosted release/snapshot repo** dành cho upload. Cần kiểm **repo thực sự Maven dùng** sau mirror selection, chứ không chỉ đọc URL từ source POM.

### 2.2. Mirror không có nghĩa thử nhiều URLs tuần tự

Maven chỉ chọn **một matching mirror cho mỗi repository**. Khi mirror `mirrorOf=*` thay Maven Central cùng các vendor repos, nó phải là repository manager có đủ upstream hoặc chứa mọi artifacts cần thiết. Nếu mirror thiếu một plugin, Maven không mặc nhiên quay về Maven Central để thử lần nữa.

### 2.3. Plugin resolution và dependency resolution có thể dùng paths khác

Nếu `mvn test` fail ngay khi tải Surefire Plugin, kiểm mirror và `pluginRepositories`. Nếu tới compile rồi `commons-lang3` fail, kiểm `repositories`, dependency GAV và effective mirror. Trạng thái network không thể kết luận chỉ dựa vào `BUILD FAILURE`.

## 3. `settings.xml`: vị trí, ưu tiên và phần có thể chứa secret

Vị trí thường gặp:

~~~text
Global settings:  ${maven.home}/conf/settings.xml
User settings:    ${user.home}/.m2/settings.xml
~~~

Maven ghép global/user settings theo settings model; user settings thường có ưu tiên cao hơn ở cấu hình trùng. Trong CI, `HOME`, `JAVA_HOME` và settings path có thể hoàn toàn khác laptop.

Lệnh chọn tệp settings:

~~~bash
mvn -B -ntp -s /secure/path/settings.xml test
mvn -B -ntp -gs /secure/path/global-settings.xml test
~~~

Đường `/secure/path/...` chỉ là placeholder. Không sử dụng settings production thật trong lab mẫu có hostname `.invalid`.

### 3.1. Một mẫu settings hoàn chỉnh nhưng không có secret thật

Tạo `settings-corp-template.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">

    <mirrors>
        <mirror>
            <id>company-mirror</id>
            <mirrorOf>central</mirrorOf>
            <url>https://repo.example.invalid/repository/maven-public/</url>
        </mirror>
    </mirrors>

    <servers>
        <server>
            <id>company-mirror</id>
            <username>${env.REPO_READ_USER}</username>
            <password>${env.REPO_READ_TOKEN}</password>
        </server>
    </servers>

    <proxies>
        <proxy>
            <id>company-proxy</id>
            <active>false</active>
            <protocol>http</protocol>
            <host>proxy.example.invalid</host>
            <port>8080</port>
            <nonProxyHosts>localhost|*.corp.example</nonProxyHosts>
        </proxy>
    </proxies>
</settings>
~~~

**Chú ý đặc biệt:** `example.invalid` và `proxy.example.invalid` là ví dụ **cố ý không kết nối được**. File chỉ để học cấu trúc và chạy checker offline ở mục 11. Nếu muốn tải dependencies qua kho công ty, phải thay hostname bằng endpoint HTTPS thật được quản trị viên xác nhận, cấp token qua secrets manager và bật proxy nếu chính sách mạng yêu cầu.

- Mirror `id=company-mirror` là effective repository ID dùng cho các request thay thế `central`.
- `mirrorOf=central` nghĩa là chỉ thay repository có ID `central`, không phải mọi private repo.
- `servers/server/id=company-mirror` phải trùng **mirror ID**, không chỉ `central`.
- `password=${env.REPO_READ_TOKEN}` là nội suy environment, không chứa literal token.
- Proxy `active=false` khiến nó không được sử dụng trong mẫu này.
- `nonProxyHosts` dùng **dấu gạch đứng `|`** làm separator, có hỗ trợ wildcard `*`.

`servers` và `proxies` nằm trực tiếp dưới `settings`, không nhét vào một `profile`. Profiles có repositories và activation nhưng không định nghĩa server credential ở cấp ấy.

### 3.2. Vì sao server ID là chìa khóa?

| Repository được Maven dùng | ID `server` thường cần |
| --- | --- |
| Private repo trực tiếp `private-release-read` | `private-release-read` |
| Mirror `company-mirror` thay `central` | `company-mirror` |
| Deploy release `distributionManagement.repository.id=company-release` | `company-release` |
| Deploy staging với `altDeploymentRepository=stage::url` | `stage` |
| Proxy cần username/password | Dùng `proxies/proxy`, **không phải servers** |

Maven không dùng hostname để tự đoán credentials. Hai ID `Company-Mirror` và `company-mirror` không nên coi là tương đương. Trường hợp `server.id=central` nhưng Maven request ghi `from/to company-mirror` có thể dẫn tới 401 vì không tìm đúng credentials cho mirror.

### 3.3. Đặt token ở đâu?

- Lưu token trong CI secret store hoặc hệ thống quản lý secrets có quyền hạn phù hợp.
- Trong `settings.xml` dùng env references khi được Maven version hỗ trợ.
- Không đặt token vào POM, Maven command line, URL query string hoặc tài liệu public.
- Dùng read-only token cho dependency/plugin download; write token riêng cho `mvn deploy`.
- Với Maven 3, password encryption chỉ ở mức **obfuscation-grade** theo tài liệu chính thức; không thay thế secrets manager.
- Maven 4 có `mvnenc` và encryption dispatchers mới, cách cấu hình khác Maven 3; không copy nguyên config encryption cũ.

## 4. Đọc `mirrorOf` và xác định mirror nào thực sự thắng

### 4.1. Các selector cần nhớ

| `mirrorOf` | Phạm vi |
| --- | --- |
| `central` | Repository ID `central` chính xác |
| `*` | Tất cả repo IDs match selector |
| `external:*` | Remote external repos, không gồm localhost/file repos |
| `external:http:*` | External HTTP repositories, không gồm localhost |
| `*,!internal-test` | Tất cả trừ ID `internal-test` |
| `external:*,!vendor` | External trừ `vendor` |
| `central,vendor` | Hai IDs được liệt kê |

Một mirror `mirrorOf=central` không tương đương `mirrorOf=*`. Nếu tổ chức dùng mirror catch-all, nó phải thực sự proxy Central và các vendor repos được phép.

### 4.2. Precedence

Maven ưu tiên **exact repository ID match**, rồi chọn **mirror khai báo đầu tiên** trong những wildcard/selectors match. Ví dụ:

~~~xml
<mirrors>
    <mirror>
        <id>special-central</id>
        <mirrorOf>central</mirrorOf>
        <url>https://repo.example.invalid/repository/central/</url>
    </mirror>

    <mirror>
        <id>all-repositories</id>
        <mirrorOf>*</mirrorOf>
        <url>https://repo.example.invalid/repository/all/</url>
    </mirror>
</mirrors>
~~~

Đây là fragment trong `settings.xml`. Khi Maven xử lý `central`, exact mirror `special-central` thắng. Repository `vendor` không có exact match có thể bị `all-repositories` thay. Maven **không tự thử mirror thứ hai** sau khi mirror được chọn đầu tiên trả 404/401.

### 4.3. Whitespace và exclusions

Trong danh sách selectors, dùng `*,!internal-test` thay vì `!internal-test, *` với khoảng trắng không chuẩn. Apache Maven cảnh báo whitespace có thể khiến mirror selector không match như kỳ vọng. Khi điều tra, đọc **literal** `mirrorOf` trong effective settings, không chỉ tên mirror.

### 4.4. Một mirror không tạo thành repository manager

Nếu bạn cần Central, corporate hosted libs và vendor packages, hãy dùng **repository manager** (Nexus/Artifactory) để tạo group/virtual repository với upstreams/permissions hợp lệ. Khai nhiều mirrors cùng `mirrorOf=*` không làm Maven gộp chúng thành một danh sách fallback.

## 5. Maven 3.8.1: chặn external HTTP theo mặc định

Từ Maven **3.8.1**, bản phân phối có cấu hình **maven-default-http-blocker** trong global settings, dùng `external:http:*` và `<blocked>true</blocked>` để chặn repositories HTTP bên ngoài. Đây là một biện pháp bảo vệ supply-chain.

Ví dụ log rút gọn:

~~~text
Could not transfer artifact ...
from/to maven-default-http-blocker (http://0.0.0.0/):
Blocked mirror for repositories:
[old-vendor (http://old.example.invalid/maven, default, releases)]
~~~

`0.0.0.0` ở đây không phải host repo thật cần ping. Maven dùng blocked mirror để không cho lấy artifact qua HTTP plaintext.

### 5.1. Repo HTTP có thể đến từ đâu?

- Project POM hiện tại.
- Parent POM.
- Dependency POM đã được publish từ lâu và khai `repositories`.
- Plugin metadata hoặc repository profile.
- Settings/profile của tổ chức.

Không nhất thiết thấy `http://...` ngay trong `pom.xml` đang mở. Tìm repository ID/URL được liệt kê ở **nested error** và đọc source POM/effective settings liên quan.

### 5.2. Cách sửa đúng

1. Nếu URL HTTP trong POM do bạn quản lý, đổi sang **HTTPS endpoint có thật** và được publisher hỗ trợ.
2. Nếu nằm trong dependency POM cũ, ưu tiên cập nhật dependency version có metadata mới.
3. Nếu chưa đổi upstream POM được, dùng HTTPS mirror ở repository manager được công ty tin cậy.
4. Xác minh TLS CA, mirror coverage và permissions.
5. Chạy lại Maven với clean/isolated cache khi cần, xác nhận không bị chặn nữa.

**Không** tắt `blocked` hoặc khai HTTP ngoại lệ chỉ vì muốn build xanh. Nếu kho cũ chỉ còn HTTP, cần kế hoạch migrate hoặc đưa vào repository manager được kiểm soát, không đưa toàn bộ dependency traffic về HTTP ngoài.

## 6. Proxy: `407` là lỗi của proxy, không phải lỗi token Maven repository

Corporate proxy thường đứng giữa Maven và remote repositories. Browser có thể dùng PAC/SSO hoặc certificate store khác JVM, nên browser tải URL được **không chứng minh Maven tải được**.

### 6.1. Proxy cấu hình đúng cấp

~~~xml
<proxies>
    <proxy>
        <id>corp-outbound</id>
        <active>true</active>
        <protocol>http</protocol>
        <host>proxy.example.invalid</host>
        <port>8080</port>
        <username>${env.PROXY_USER}</username>
        <password>${env.PROXY_TOKEN}</password>
        <nonProxyHosts>localhost|*.corp.example</nonProxyHosts>
    </proxy>
</proxies>
~~~

Đây là fragment trong settings; `.invalid` không kết nối được. Không chạy với hostname mẫu. `active=true` chỉ dùng khi proxy thực sự tồn tại và được cấp phép. Nếu proxy không cần authentication, bỏ `username`/`password` thay vì điền credentials bừa.

`nonProxyHosts` dùng **`|`**, không phải dấu phẩy. Mẫu `*.corp.example` có thể được dùng để bypass proxy với internal hosts nếu route trực tiếp được phép; cấu hình sai sẽ gây timeout.

### 6.2. Sự khác biệt giữa 401, 403 và 407

- `401` thường là repository/gateway authentication; kiểm `server.id` theo effective repo/mirror ID và token.
- `407` thường là proxy authentication, có thể xảy ra khi proxy xử lý HTTP `CONNECT` tới HTTPS repo; kiểm `settings.proxies`.
- `403` có thể là repository ACL hoặc proxy policy; cần xem response/correlation ID mà không lộ secret.

Không lấy `repo token` điền vào `proxy.password` để chữa 407. Hai hệ thống thường có identity và permissions khác nhau.

### 6.3. Browser OK, Maven FAIL

Các khác biệt phổ biến:
- Browser dùng OS truststore; Maven dùng truststore của JDK.
- Browser dùng SSO/PAC; Maven dùng `settings.xml` hoặc JVM transport settings.
- Browser có cookies/session login; Maven Resolver không dùng browser cookies.
- Browser và Maven dùng DNS/proxy/VPN route khác nhau.

Do đó khi debug, dùng `mvn -version` và đúng runtime settings; không dựa vào screenshot browser.

### 6.4. NTLM, Kerberos và proxy đặc biệt

Maven proxy guide lưu ý hỗ trợ NTLM không đồng nhất theo transport. Một vài cấu hình Java/Wagon-specific có thể xử lý trường hợp riêng, nhưng không coi đó là “official universal fix”. Nếu hạ tầng bắt buộc integrated auth, phối hợp với IT/repository admin và dùng một route/proxy chính thức được hỗ trợ.

## 7. TLS và lỗi `PKIX path building failed`

Maven tải artifact qua `https://` bằng Java TLS stack. JVM kiểm tra certificate chain tới CA được trust, hostname, thời hạn, TLS version/cipher và đôi khi client certificate.

Một log điển hình:

~~~text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed
SunCertPathBuilderException:
  unable to find valid certification path to requested target
~~~

### 7.1. Các nguyên nhân thực tế

- Internal repository dùng corporate CA mà JDK CI chưa trust.
- Corporate proxy chặn/giải mã TLS rồi phát hành cert theo internal CA.
- Server thiếu intermediate certificate hoặc chain cấu hình sai.
- Certificate hết hạn, hostname mismatch, đồng hồ máy sai.
- JDK quá cũ thiếu CA/protocol cần thiết.
- Server yêu cầu client certificate (mTLS) nhưng Maven không có keystore phù hợp.
- Không tương thích TLS protocol/cipher do policy máy chủ.

### 7.2. Xác định đúng JDK đang chạy Maven

~~~bash
mvn -version
java -version
~~~

`mvn -version` cho thấy JVM dùng chạy Maven; IDE và CLI có thể trỏ JDK khác. Trong CI cần ghi JDK vendor/version, base image, `JAVA_HOME`, Maven Wrapper version và truststore path.

### 7.3. Cách sửa an toàn: chứng chỉ CA đã xác minh

Security/IT cần cung cấp CA certificate được xác minh fingerprint từ kênh tin cậy. Dùng `keytool` để xem:

~~~bash
keytool -printcert -file /secure/path/company-ca.crt
~~~

Sau khi so certificate fingerprint với admin, có thể import vào **dedicated truststore**:

~~~bash
keytool -importcert -alias company-ca -file /secure/path/company-ca.crt -keystore /secure/path/maven-truststore.p12 -storetype PKCS12
~~~

Lệnh là minh họa, đòi file CA và đường file thật; `keytool` có thể yêu cầu mật khẩu tương tác. Không đặt truststore password trong shell history hoặc tài liệu công khai.

Một JDK truststore được Maven dùng qua JSSE properties:

~~~text
javax.net.ssl.trustStore
javax.net.ssl.trustStoreType=PKCS12
javax.net.ssl.trustStorePassword
~~~

Có thể cấp qua `MAVEN_OPTS` hoặc cấu hình CI runner/secret store hợp lệ. Nếu thay truststore mặc định, phải đảm bảo các trusted roots cần cho **mọi** repository vẫn có sẵn. Không import một certificate lạ chỉ để “hết đỏ”.

### 7.4. Truststore khác keystore

- `trustStore` chứa CAs mà JVM **tin** khi kiểm tra server.
- `keyStore` có thể chứa **client private key/certificate** nếu remote repo dùng mutual TLS.

mTLS có thể yêu cầu:

~~~text
javax.net.ssl.keyStore
javax.net.ssl.keyStoreType=PKCS12
javax.net.ssl.keyStorePassword
~~~

Đừng gửi private key cho người không có quyền và đừng đưa key material vào POM/Git. Không phải lỗi TLS nào cũng cần client certificate.

### 7.5. Các cờ không nên dùng làm cách chữa

Không khuyến nghị các cờ bypass như `maven.wagon.http.ssl.insecure=true`, `maven.wagon.http.ssl.allowall=true`, `trustAll` hoặc `curl -k` để làm release build. Chúng làm mất xác minh CA/hostname, tăng rủi ro nhận artifact giả mạo và có thể **không áp dụng** với Maven 3.9+ native Resolver HTTP transport.

## 8. Maven 3.9+ native HTTP transport khác Wagon

Apache Maven chuyển default transport từ **Wagon** sang **Maven Resolver native HTTP** kể từ **Maven 3.9.0**. Nhiều bài blog cũ chỉ nêu các option `maven.wagon.http.*` hoặc cấu hình `httpConfiguration` theo `GET/HEAD/PUT`, vốn có thể không còn tác dụng như mô tả với native transport.

Tài liệu Maven có property:

~~~bash
mvn -B -ntp -Dmaven.resolver.transport=native test
mvn -B -ntp -Dmaven.resolver.transport=wagon test
~~~

Dùng để **so sánh behavior trong môi trường debug được phép**, không phải fix lâu dài cho token sai hoặc certificate chưa trust. `native` là default thông thường trên Maven 3.9+. Khi test hai transports, ghi rõ Maven release, config proxy/timeout, endpoint và kết quả; không tự coi `wagon` an toàn hơn.

Transport khác nhau có thể làm warning/logs/HTTP tuning khác nhau, nhưng:
- `401` vẫn cần credentials hợp lệ.
- `407` vẫn cần proxy authentication.
- `PKIX` vẫn cần trusted CA và TLS đúng.
- `maven-default-http-blocker` vẫn là security policy với external HTTP.

## 9. Maven 3.10+/Maven 4: repository origin binding

Tài liệu Maven Settings hiện hành mô tả từ **Maven 3.10.0 và Maven 4.0.0** có bảo vệ **credential origin** theo scheme, host và port. Trước đây server ID là chìa khóa chính; điều đó tạo rủi ro một dependency POM không tin cậy khai cùng ID nhưng URL khác để khiến credentials bị gửi tới host lạ.

### 9.1. Khi `server.id` đã khớp nhưng token vẫn không được gửi

Kiểm:
1. Maven version và `maven.repository.credentialScope`.
2. Effective repository/mirror ID.
3. Trusted origin của `server.id` có khớp scheme://host:port không?
4. Repository chỉ xuất hiện trong POM (Maven chưa biết khi khởi tạo settings) hay trong active settings profile/mirror?
5. Đích được IT/security duyệt chưa?

### 9.2. `repositoryOrigins` với settings model 1.3.0

Maven 3.10+/4 hỗ trợ khai trusted origins trong `settings.xml` phiên bản 1.3.0:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.3.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.3.0
                              https://maven.apache.org/xsd/settings-1.3.0.xsd">

    <servers>
        <server>
            <id>private-repo</id>
            <username>${env.REPO_READ_USER}</username>
            <password>${env.REPO_READ_TOKEN}</password>
            <repositoryOrigins>
                <repositoryOrigin>https://repo.example.invalid</repositoryOrigin>
            </repositoryOrigins>
        </server>
    </servers>
</settings>
~~~

Đây là một **mẫu riêng cho Maven version hỗ trợ schema mới**. Không copy `repositoryOrigins` vào settings 1.2.0 của Maven cũ. Origin chỉ gồm `scheme://host[:port]`, không kèm path `/repository/maven-public/` hay query. URL `.invalid` vẫn là placeholder.

### 9.3. `credentialScope`

Các giá trị theo Maven Settings Reference: `origin` (default cho cơ chế mới), `strict` và `id`. `strict` không cấp credentials khi trusted origin chưa được xác định; `id` quay về behavior dựa ID như bản cũ và giảm bảo vệ. **Không** bật `-Dmaven.repository.credentialScope=id` chỉ để chữa 401 mà chưa xác minh destination và bảo mật. Tốt hơn là làm rõ URL/origin, active settings profile và `repositoryOrigins` được phép.

## 10. Lab Java 17: kiểm tra repository resolution qua Maven

Một project nhỏ đủ để xác nhận **compile dependency** Commons Lang và **test dependency** JUnit được Maven lấy qua repository/mirror đúng. Nó không yêu cầu Nexus/Artifactory hoặc token để chạy trên máy có thể truy cập Maven Central hợp lệ.

### 10.1. Cấu trúc project

~~~text
maven-repository-lab/
├── pom.xml
├── settings-corp-template.xml
├── src/
│   ├── main/java/dev/example/repo/RepoAccessMain.java
│   └── test/java/dev/example/repo/RepoAccessTest.java
└── tools/
    └── RepoRouteCheck.java
~~~

Yêu cầu JDK 17+, Maven 3.9.x và khả năng tải artifacts/plugins từ Central hoặc mirror hợp lệ. **Không** dùng `-s settings-corp-template.xml` để chạy build khi còn `repo.example.invalid`; nó chỉ dùng cho checker offline ở mục 11.

### 10.2. `pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>maven-repository-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.17.0</version>
        </dependency>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Compiler Plugin sử dụng `--release 17`. `commons-lang3` là dependency cần cho Java main; `junit-jupiter` scope `test` dùng trong Surefire. Plugin versions được pin giúp debug lỗi download dễ truy GAV.

### 10.3. `RepoAccessMain.java`

~~~java
package dev.example.repo;

import org.apache.commons.lang3.StringUtils;

public final class RepoAccessMain {
    private RepoAccessMain() {
    }

    public static String message() {
        return "REPOSITORY OK: "
                + StringUtils.capitalize("maven");
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

`StringUtils.capitalize` của Commons Lang trả `Maven` với input `maven`.

### 10.4. `RepoAccessTest.java`

~~~java
package dev.example.repo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class RepoAccessTest {
    @Test
    void showsExpectedMessage() {
        assertEquals("REPOSITORY OK: Maven",
                RepoAccessMain.message());
    }
}
~~~

Một JUnit test method, một assertion. Nếu Maven tải được các dependencies và build thành công, log thường chứa:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **kết quả dự kiến**, không phải báo cáo đã thực thi trên môi trường người đọc.

### 10.5. Build và chạy main class

Từ project root, dùng settings Maven đã có route tới Central hoặc mirror hoạt động:

~~~bash
java -version
mvn -version
mvn -B -ntp clean test
mvn -B -ntp org.codehaus.mojo:exec-maven-plugin:3.6.4:java -Dexec.mainClass=dev.example.repo.RepoAccessMain
~~~

`exec-maven-plugin` cũng phải được tải nếu chưa cached. Application stdout chính xác:

~~~text
REPOSITORY OK: Maven
~~~

Ngoài ra Maven có INFO/BUILD SUCCESS logs. Nếu build fail từ bước tải plugin, điều đó là lỗi resolution/pluginRepository; không nên kết luận Java class sai.

## 11. Java checker offline: ID mirror/server có khớp không?

Tạo `tools/RepoRouteCheck.java` trong project. Chương trình chỉ đọc **một file settings XML**, tìm mirror literal `mirrorOf=central`, so với `servers.server.id` và báo trạng thái proxy. Nó **không đọc password/token values và không kết nối mạng**.

Đây là bài thực hành phân biệt một static configuration check với network authentication test: `Matching server ID: YES` không chứng minh token hợp lệ, TLS OK, proxy reachable hoặc quyền trên repository.

### 11.1. Code Java 17 đầy đủ

~~~java
import java.io.File;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;

public final class RepoRouteCheck {
    private RepoRouteCheck() {
    }

    private static Document readXml(String path) throws Exception {
        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(
                XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        factory.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(
                XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return factory.newDocumentBuilder().parse(
                new File(path));
    }

    private static String value(Element parent, String name) {
        for (Node node = parent.getFirstChild();
             node != null;
             node = node.getNextSibling()) {
            if (node instanceof Element element
                    && name.equals(element.getLocalName())) {
                return element.getTextContent().trim();
            }
        }
        return "";
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                    "Usage: RepoRouteCheck <settings.xml>");
            System.exit(2);
        }

        Document xml = readXml(args[0]);
        Element root = xml.getDocumentElement();

        String mirrorId = "";
        boolean matchesCentral = false;

        var mirrors = root.getElementsByTagNameNS("*", "mirror");
        for (int i = 0; i < mirrors.getLength(); i++) {
            Element mirror = (Element) mirrors.item(i);
            if ("central".equals(value(mirror, "mirrorOf"))) {
                mirrorId = value(mirror, "id");
                matchesCentral = true;
                break;
            }
        }

        boolean serverFound = false;
        var servers = root.getElementsByTagNameNS("*", "server");
        for (int i = 0; i < servers.getLength(); i++) {
            Element server = (Element) servers.item(i);
            if (!mirrorId.isEmpty()
                    && mirrorId.equals(value(server, "id"))) {
                serverFound = true;
                break;
            }
        }

        boolean activeProxy = false;
        var proxies = root.getElementsByTagNameNS("*", "proxy");
        for (int i = 0; i < proxies.getLength(); i++) {
            Element proxy = (Element) proxies.item(i);
            if ("true".equalsIgnoreCase(value(proxy, "active"))) {
                activeProxy = true;
            }
        }

        System.out.println("Configured mirror ID: " + mirrorId);
        System.out.println("Mirror for central: "
                + (matchesCentral ? "YES" : "NO"));
        System.out.println("Matching server ID: "
                + (serverFound ? "YES" : "NO"));
        System.out.println("Active proxy in template: "
                + (activeProxy ? "YES" : "NO"));
        System.out.println("Credential values inspected: NO");

        if (!matchesCentral || !serverFound) {
            System.exit(3);
        }
    }
}
~~~

`DocumentBuilderFactory` có namespace awareness, secure processing, không cho DOCTYPE/external DTD/schema để tránh XML external entity access. Chỉ dùng `mirrorOf=central` literal; nó **không tái hiện** toàn bộ matching algorithm cho `*`, exclusions, profiles hoặc user/global merge. `value` chỉ đọc direct child theo local name, tránh nhầm IDs lồng nhau.

### 11.2. Biên dịch và kiểm tra

Từ `maven-repository-lab`, sau khi tạo `settings-corp-template.xml` đúng mẫu:

~~~bash
javac -d target/route-check tools/RepoRouteCheck.java
java -cp target/route-check RepoRouteCheck settings-corp-template.xml
~~~

Stdout **chính xác cho XML mẫu**:

~~~text
Configured mirror ID: company-mirror
Mirror for central: YES
Matching server ID: YES
Active proxy in template: NO
Credential values inspected: NO
~~~

Nếu sửa mirror `id` mà quên server, checker in `Matching server ID: NO` và exit code `3`. Nó không đọc secret values, cũng không thử network. Khi CI dùng settings từ nhiều sources/profiles, phải xem effective settings theo chính Maven runtime thay vì dùng checker để tuyên bố toàn bộ cấu hình đúng.

## 12. Workflow debug Maven không làm lộ credentials

### 12.1. Bước 1 — lấy GAV và nguyên nhân gốc

Ghi:
- GAV của `.pom`, `.jar`, `maven-metadata.xml` hoặc plugin bị lỗi.
- Effective repository ID/URL xuất hiện sau `from/to`.
- HTTP code hoặc TLS exception nằm sâu trong `Caused by`.
- Phase Maven đang chạy (`compile`, `test`, `deploy`...).
- JDK/Maven version và runner/laptop gặp lỗi.

Chỉ có `Could not resolve` là chưa đủ để chọn cách sửa.

### 12.2. Bước 2 — đọc đúng phiên bản runtime

~~~bash
mvn -version
java -version
~~~

Maven có thể dùng `JAVA_HOME` khác lệnh `java` trong shell hoặc IDE. Đây là điều quan trọng nhất với `PKIX`/truststore.

### 12.3. Bước 3 — xem settings được merge an toàn

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-settings -DshowPasswords=false -Doutput=effective-settings.xml
~~~

Maven Help Plugin mặc định `showPasswords=false`. File kết quả vẫn có URLs, proxy host, usernames và thông tin nội bộ; **không commit hoặc gửi public**. Lệnh cũng cần Help Plugin có thể resolve. Nếu mạng hỏng từ đầu và plugin chưa cached, có thể chính lệnh help thất bại; khi đó xem settings XML offline và log resolver, không hiểu nhầm đây là lỗi mới.

### 12.4. Bước 4 — xem effective POM và repository sources

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Doutput=effective-pom.xml
~~~

Tìm `repositories`, `pluginRepositories`, `distributionManagement`, parent POM, active profiles, plugin GAV. **Effective POM không tự phản ánh toàn bộ mirror substitution**; phải xét kết hợp settings và log thực tế.

### 12.5. Bước 5 — kiểm mirror và credentials

Xác định chính xác `mirrorOf` match repository nào và ID mirror thắng. Với download private: `server.id` match effective repository/mirror ID. Với deploy: `server.id` match `distributionManagement.repository.id` hoặc alternate `repositoryId`. Với Maven mới: kiểm trusted origin.

Không dùng token có quyền write để chữa read-only build nếu có thể tách scopes.

### 12.6. Bước 6 — proxy, DNS và TLS

Đối chiếu:
- Proxy host/port/protocol/active flag.
- `nonProxyHosts` có trỏ request sai đường không.
- Proxy 407 hay repository 401.
- DNS/VPN/firewall từ runner.
- JDK truststore, certificate chain, TLS interception, validity, hostname.
- Transport Maven 3.9 native hay Wagon.

Browser/curl thành công chỉ là tín hiệu network, không bảo đảm JVM Maven có truststore/auth tương tự. Không dùng `curl -k` để coi là TLS đã được sửa.

### 12.7. Bước 7 — thử lại sau khi sửa lỗi nền

Nếu Maven đã nhớ failed resolution:

~~~bash
mvn -B -ntp -U clean test
~~~

`-U` yêu cầu cập nhật snapshot/missing artifacts theo chính sách Maven; nó **không** bỏ qua blocked mirror, credentials, proxy, CA hoặc hostname verification. Không retry vô hạn khi server trả `429`.

### 12.8. Bước 8 — kiểm với local Maven cache độc lập

~~~bash
mvn -B -ntp -Dmaven.repo.local=./.m2-diagnostic clean test
~~~

`./.m2-diagnostic` là local repo riêng. Khi lần đầu dùng nó, Maven cần tải plugins/dependencies. Nó giúp phát hiện build local xanh vì cache cũ, nhưng không tự cấp quyền hoặc tạo ra URL repository mới.

### 12.9. Bước 9 — kiểm dependency tree sau khi truy cập đã hoạt động

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
mvn -B -ntp clean verify
~~~

Nếu phase resolution đã qua nhưng runtime `NoClassDefFoundError`, đó có thể là lỗi scope/exclusions, không còn là 401/PKIX.

### 12.10. Bước 10 — tái hiện trên đúng CI runner

Runner CI có user home, network policy, protected variables và truststore khác laptop. Không dựa vào “build của tôi xanh” để kết luận repository manager đang truy cập được từ CI.

## 13. Offline mode, negative cache và lỗi 404

`-o` / `--offline` bảo Maven chỉ dùng artifacts đã có:

~~~bash
mvn -B -ntp -o test
~~~

Offline build `PASS` chỉ chứng minh cache đủ cho workflow đó, **không chứng minh remote repo đang hoạt động**.

Maven có thể ghi `.lastUpdated` markers và nhớ một lần tải artifact/metadata thất bại. Sau khi sửa route, `-U` có thể yêu cầu cập nhật. Không xóa toàn bộ `~/.m2` như bước đầu vì tốn mạng, có thể mất artifact local chỉ được install, và làm CI dễ dính rate limit.

### 13.1. Maven repository layout

Ví dụ:

~~~text
org.apache.commons:commons-lang3:3.17.0
    ->
org/apache/commons/commons-lang3/3.17.0/
    commons-lang3-3.17.0.pom
    commons-lang3-3.17.0.jar
~~~

`404` có thể do sai `groupId`, `artifactId`, `version`, `type`, `classifier` hoặc Maven đang dùng mirror không chứa artifact. Private repo cũng có thể trả 404 để che artifact trước request không có quyền. Vì vậy phải đối chiếu repository manager listing/policy và POM metadata, không kết luận chỉ từ HTTP code.

### 13.2. Repository policy

- Hosted release repo có thể không cho SNAPSHOT.
- Hosted snapshot repo có thể không chứa immutable release.
- Group/virtual repo có thể chưa bao gồm hosted private repo.
- Proxy repo có thể đang cache một 404/outage.
- ACL có thể cho GET `.jar` nhưng chặn `.pom` hoặc `maven-metadata.xml` do cấu hình lỗi.

Khi một `.pom` thiếu, Maven không có đầy đủ transitive dependency model; thay `scope` trong project POM không phải phương án sửa network mặc định.

## 14. Kịch bản lỗi và giải pháp

### A. `401` vì mirror ID khác server ID

Settings khai `mirror.id=company-mirror`, `mirrorOf=central`, nhưng `servers.server.id=central`. Khi Maven thật sự request `company-mirror`, sửa server ID để khớp, kiểm đúng endpoint/credential scope và trusted origin.

### B. `407` trên CI nhưng laptop hoạt động

CI có proxy/gateway khác; `settings.proxies` chưa khai auth hoặc token thiếu. Kiểm proxy, `nonProxyHosts` và permission của runner, không thay Central repository password.

### C. `PKIX` chỉ xảy ra khi đổi JDK

JDK mới dùng truststore khác; corporate CA chưa được cài hoặc server chain thiếu. So CA fingerprint, sửa server chain/runner truststore theo policy.

### D. `maven-default-http-blocker` sau nâng Maven

Một dependency POM cũ trỏ `http://old-vendor...`. Maven 3.8.1 chặn external HTTP. Nâng dependency/URL sang HTTPS hoặc dùng repository manager HTTPS được cấp quyền, không tắt `blocked`.

### E. Browser truy cập được nhưng Maven bị `SSLHandshakeException`

Browser có thể dùng OS truststore/SSO/PAC, Maven là JVM TLS; cần kiểm runtime Java/mTLS và proxy interception.

### F. Plugin download 404 nhưng application dependency download OK

`pluginRepositories`, plugin GAV hoặc mirror rule có thể khác tuyến library; repository manager chưa proxy plugin version. Kiểm `from/to` và GAV plugin.

### G. `mvn deploy` 403 nhưng `mvn test` PASS

Build có quyền đọc dependencies, nhưng chưa có quyền ghi hosted repository. Kiểm `distributionManagement` và `settings.server.id` của **write repo**, không dùng token download.

### H. Dùng `mirrorOf=*` nhưng private vendor repo không thấy

Mirror catch-all không chứa upstream vendor. Sửa repository manager group/virtual setup hoặc selector exclusions chính thức, không thêm HTTP công cộng ngoài policy.

### I. Cache laptop che lỗi

Laptop đã tải JAR từ trước; CI clean cache phải truy cập lại repo và gặp 401. Dùng `-Dmaven.repo.local` trong môi trường debug, kiểm settings và role.

### J. Quá nhiều runner gây 429

Giảm concurrent requests, dùng proxy repository/cache, backoff/jitter theo response headers và repository policy. Không blind retry trong vòng lặp tốc độ cao.

### K. Maven 3.10 `strict` không gửi credentials

Origin chưa được declared trusted dù ID khớp. Kiểm settings 1.3.0 `repositoryOrigins` và URL thật; không chuyển sang `credentialScope=id` để bypass mặc định.

### L. Native transport không dùng `maven.wagon.http.*` cũ

Đọc Resolver Transport Guide cho Maven 3.9+. Thử `-Dmaven.resolver.transport=wagon` chỉ là bước khoanh vùng; không coi nó thay thế sửa TLS hoặc auth.

## 15. Checklist trước khi đóng ticket

- [ ] Có GAV, filename, repo ID, URL và nested cause thật.
- [ ] Biết lỗi nằm ở dependency, plugin hay deploy.
- [ ] Đã kiểm Maven và JDK version từ chính runner.
- [ ] Đã xác minh user/global/`-s` settings.
- [ ] Có effective POM và effective settings được xem trong phạm vi bảo mật.
- [ ] Đã xác định mirror thắng, `mirrorOf`, blocked/exclusions.
- [ ] `servers.server.id` đúng effective ID, token scope đúng.
- [ ] `407` được xử lý tại proxy, không trộn repo credentials.
- [ ] `nonProxyHosts` có đúng cú pháp `|` và host rules.
- [ ] `PKIX` được xử lý bằng CA/truststore hợp lệ của đúng JVM.
- [ ] Không tắt TLS/certificate/hostname checks hoặc external HTTP blocker.
- [ ] Maven 3.9+ native transport được nhận biết.
- [ ] Maven 3.10+/4 origin-scoped credential policy được giữ.
- [ ] `-U` được dùng có lý do, không thay auth/SSL policy.
- [ ] Có isolated-cache test khi nghi local cache che lỗi.
- [ ] 404 được kiểm về GAV, classifier, repository content và ACL.
- [ ] 429/503 được xử lý theo backoff/service health, không brute force.
- [ ] Không có raw token/password/truststore private key trong logs/Git.
- [ ] Đã thử lại trên đúng CI runner và xác nhận failure biến mất.

## 16. Câu hỏi ôn tập và đáp án

**1.** 401 ở `company-mirror` nhưng server ID chỉ là `central`, cần xem gì? — **Đáp án:** Credentials phải tra theo mirror ID thực sự, tức `company-mirror`.

**2.** 407 có thể sửa chỉ bằng tăng quyền repository token? — **Không:** 407 là proxy authentication.

**3.** Maven 3.8.1 báo `maven-default-http-blocker`; có phải server Maven Central chết? — **Không:** Maven đang chặn external HTTP đã biết không an toàn.

**4.** `mirrorOf=*` có tự thử một mirror khác khi mirror đầu bị 404? — **Không:** Maven chọn một matching mirror, không aggregate/fallback tùy ý.

**5.** `nonProxyHosts` dùng dấu phân cách nào? — **`|`**, ví dụ `localhost|*.corp.example`.

**6.** Browser mở URL HTTPS được, Maven PKIX fail có mâu thuẫn không? — **Không:** JVM có truststore/proxy khác browser.

**7.** Có nên dùng `maven.wagon.http.ssl.insecure=true` để chữa PKIX? — **Không:** nó hạ bảo mật và có thể không phù hợp native transport.

**8.** Maven 3.9+ thường dùng native hay Wagon? — **Native Maven Resolver HTTP** theo mặc định.

**9.** Maven 3.10+ strict credential scope không gửi token; đổi sang `id` ngay? — **Không:** xác minh trusted repository origin và permission trước.

**10.** `mvn -o test` PASS đã chứng minh internet/repository đang OK? — **Không:** chỉ chứng minh local Maven cache đủ.

**11.** `mvn -U` có thể bỏ qua chặn HTTP/TLS không? — **Không:** chỉ ảnh hưởng update/resolution retry.

**12.** `RepoRouteCheck` báo Matching server ID YES chứng minh password đúng chưa? — **Chưa:** checker không đọc secret hoặc gửi HTTP request.

**13.** CI fail nhưng laptop PASS, nên kiểm yếu tố nào? — **Settings, proxy, env vars, JDK CA, local cache, runner identity và repository permissions.**

**14.** Maven `help:effective-settings` mặc định giấu passwords có thể upload public output không? — **Không nên:** URLs, usernames và cấu trúc hạ tầng vẫn nhạy cảm.

**15.** `mvn deploy` 403 trong khi `dependency:tree` PASS nói lên điều gì? — **Có thể** read repository hoạt động nhưng write endpoint/ACL không cho deploy.

## 17. Tài liệu chính thức

1. [Maven Settings Reference](https://maven.apache.org/settings.html) — servers, proxies, mirrors, settings profiles, repository origins.
2. [Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings) — `mirrorOf` selectors, precedence và one-mirror selection.
3. [Configuring a Proxy](https://maven.apache.org/guides/mini/guide-proxies.html) — proxy authentication, `nonProxyHosts`, transport caveats.
4. [Maven 3.8.1 Release Notes](https://maven.apache.org/docs/3.8.1/release-notes.html) — external HTTP blocker mặc định và migration.
5. [Resolver Transport Guide](https://maven.apache.org/guides/mini/guide-resolver-transport.html) — Maven 3.9+ native transport và Wagon.
6. [Advanced HTTP Wagon Configuration](https://maven.apache.org/guides/mini/guide-http-settings.html) — legacy HTTP settings và native transport caveats.
7. [Repository Authenticated HTTPS](https://maven.apache.org/guides/mini/guide-repository-ssl.html) — TLS truststore, keystore và client certificates.
8. [Help Plugin: effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html) — mặc định `showPasswords=false`.
9. [Help Plugin: effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html) — effective project/repository model.
10. [Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — dependencies graph.
11. [Maven 3 Password Encryption](https://maven.apache.org/guides/mini/guide-encryption.html) — cảnh báo obfuscation-grade và secret storage.
12. [Maven 4 Password Encryption](https://maven.apache.org/guides/mini/guide-encryption-4.html) — `mvnenc` và dispatchers.
13. [Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — các phase build/install/deploy.
