# Cấu hình proxy, TLS và chẩn đoán lỗi kết nối repository trong Gradle

## 1. Vì sao Gradle không tải được dependency dù trình duyệt vẫn vào mạng?

Gradle cần truy cập mạng ở nhiều thời điểm: tải **Gradle distribution** nếu Wrapper chưa có, tìm **plugin** cho build script, tìm **dependency** của ứng dụng, tải **Java toolchain** khi được cấu hình thích hợp, và **publish** artifact lên repository. Trên mạng doanh nghiệp, các kết nối có thể phải đi qua HTTP/HTTPS proxy, hệ thống xác thực tập trung, firewall, DNS nội bộ hoặc thiết bị kiểm tra TLS (TLS inspection).

Bởi vậy, thông báo như `Could not resolve ...` hoặc `Could not GET ...` chỉ là **triệu chứng**. Nguyên nhân thật có thể là:

- Gradle không được cấu hình proxy dù trình duyệt đã dùng proxy/PAC.
- Proxy yêu cầu xác thực (HTTP **407**) trong khi Maven repository lại có thông tin đăng nhập khác (HTTP **401/403**).
- Gradle chạy bằng một JDK không tin cậy chứng chỉ CA nội bộ, dẫn tới `PKIX path building failed`.
- Địa chỉ repository sai, DNS không phân giải được, service đang lỗi hoặc đường truyền bị timeout.
- Plugin được tìm ở **plugin repositories**, nhưng bạn chỉ cấu hình **project dependency repositories**.
- Gradle Wrapper chưa tải xong distribution, nên build script chưa hề được chạy.
- Dependency thiếu trong repository hoặc cache offline, không phải lỗi TLS hay proxy.

Mục tiêu bài này là **cấu hình và chẩn đoán đúng lớp**, không “sửa” bằng cách tắt kiểm tra TLS, chuyển sang HTTP không mã hóa, ghi password vào source hay xóa toàn bộ cache mù quáng.

Sau bài học, bạn cần biết xác định kết nối đang lỗi ở pha nào, cấu hình JVM proxy qua `gradle.properties`, hiểu `http.nonProxyHosts`, phân biệt JDK truststore với repository credentials, dùng lệnh mạng và Gradle để khoanh vùng, và xây CI an toàn.

## 2. Bản đồ kết nối của một Gradle build

~~~text
Terminal / CI
     |
     +--> ./gradlew / gradlew.bat
     |      |
     |      +--> Wrapper bootstrap:
     |             services.gradle.org hoặc distribution mirror
     |             (khi distribution chưa có trong Gradle User Home)
     |
     +--> Gradle JVM / Daemon
            |
            +--> settings.gradle(.kts)
            |      +--> pluginManagement.repositories
            |      |       -> Gradle Plugin Portal / Maven plugin mirror
            |      +--> dependencyResolutionManagement.repositories
            |              -> Maven Central / repository noi bo
            |
            +--> build.gradle(.kts)
            |      +--> plugins { ... }
            |      +--> repositories { ... } (neu project cho phep)
            |      +--> dependencies { ... }
            |
            +--> task publish
                   -> Maven repository dich (repository ghi artifact)

May tinh / JDK -> Proxy (neu can) -> TLS / CA -> Repository server
~~~

**Một lỗi mạng không nhất thiết xuất phát từ nơi bạn đang nhìn trong build script.** Nếu terminal dừng ngay ở “Downloading ... gradle-...-bin.zip”, Wrapper đang cố tải bản phân phối Gradle; sửa `repositories { mavenCentral() }` trong `build.gradle.kts` không giải quyết được. Nếu lỗi “Plugin ... was not found”, phải xem plugin repositories. Nếu lỗi từ `compileClasspath` hoặc `runtimeClasspath`, kiểm tra dependency repositories và bản thân tọa độ dependency.

### 2.1. Bốn đích cần tách biệt

| Kết nối | Nơi khai báo/kiểm tra | Khi nào xuất hiện |
| --- | --- | --- |
| **Wrapper distribution** | `gradle/wrapper/gradle-wrapper.properties`, `distributionUrl`, mạng/JVM của Wrapper | Trước khi Gradle runtime sẵn sàng, nếu distribution chưa cache |
| **Gradle plugin resolution** | `pluginManagement { repositories { ... } }` trong `settings.gradle.kts`; đôi khi còn plugin ở buildscript classpath | Khi Gradle resolve plugin |
| **Project dependency resolution** | `dependencyResolutionManagement.repositories` ở settings hoặc `repositories` trong project, tùy repositories mode | Khi classpath/configuration được resolve |
| **Publishing/upload** | `publishing { repositories { ... } }` hoặc plugin publish riêng | Khi task upload/publish thực thi |

Proxy và TLS hoạt động ở **lớp mạng/JVM**, có thể ảnh hưởng nhiều loại kết nối cùng lúc; còn **repository credentials và các repository blocks** thuộc từng loại hoạt động và không tự thay thế nhau.

## 3. Proxy trong Gradle là proxy của JVM

Gradle chủ yếu dùng các **Java system properties** chuẩn để truy cập HTTP/HTTPS qua proxy. Đó không phải cùng thứ với `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` mà một số công cụ dòng lệnh (ví dụ `curl`) hoặc runtime khác đọc. Không thể giả định cứ cài proxy trên trình duyệt, hệ điều hành hoặc terminal là Gradle JVM tự làm giống hệt.

Những khóa JVM tiêu biểu:

| Java system property | Vai trò |
| --- | --- |
| `http.proxyHost` | Host proxy cho HTTP |
| `http.proxyPort` | Cổng proxy HTTP |
| `https.proxyHost` | Host proxy cho HTTPS |
| `https.proxyPort` | Cổng proxy HTTPS |
| `http.proxyUser` / `http.proxyPassword` | Credentials proxy cho HTTP trong môi trường hỗ trợ |
| `https.proxyUser` / `https.proxyPassword` | Credentials proxy cho HTTPS trong môi trường hỗ trợ |
| `http.nonProxyHosts` | Những host cần kết nối trực tiếp, bỏ qua proxy, dùng cho cả HTTP và HTTPS theo cấu hình Java/Gradle được tài liệu hóa |
| `socksProxyHost` / `socksProxyPort` | SOCKS proxy nếu hạ tầng dùng cơ chế đó |

**Bẫy phổ biến:** với HTTPS, Gradle vẫn dùng tên `http.nonProxyHosts` (không phải `https.nonProxyHosts`) cho danh sách bypass proxy. Các host trong danh sách thường được ngăn bởi dấu `|` và có thể dùng wildcard như `*.corp.example`.

Không coi mọi proxy là một hộp giống nhau: forward proxy, reverse proxy, transparent TLS inspection proxy, SOCKS và corporate VPN có thể có hành vi khác nhau. Hỏi đội mạng **proxy host, port, loại xác thực, bypass domains, HTTPS inspection certificate và DNS path** thay vì đoán giá trị.

## 4. Cấu hình proxy trong Gradle User Home

Gradle hỗ trợ đặt Java system properties trong `gradle.properties` bằng tiền tố `systemProp.`. Đối với thông tin theo máy/người dùng, nên đặt tại **`GRADLE_USER_HOME/gradle.properties`**, nằm ngoài source repository.

### 4.1. Ví dụ cho mạng doanh nghiệp

Giả sử đội hạ tầng cấp proxy tên `proxy.corp.example`, cổng `8080` và yêu cầu kết nối trực tiếp tới một số host nội bộ. Nội dung ví dụ **`GRADLE_USER_HOME/gradle.properties`**:

~~~properties
# Day la vi du host/port, phai thay bang thong so duoc cap.
systemProp.http.proxyHost=proxy.corp.example
systemProp.http.proxyPort=8080

systemProp.https.proxyHost=proxy.corp.example
systemProp.https.proxyPort=8080

# Chu y: https cung dung http.nonProxyHosts.
systemProp.http.nonProxyHosts=localhost|127.*|*.corp.example
~~~

`proxy.corp.example` là địa chỉ minh họa, không phải proxy tồn tại công khai. Chỉ sử dụng các giá trị thật do đội mạng cung cấp.

Ý nghĩa:

- Gradle JVM dùng proxy đã khai báo cho HTTP/HTTPS khi giao thức và client mạng áp dụng các system properties đó.
- Những host khớp `http.nonProxyHosts` có thể đi **trực tiếp**, nên phải có tuyến mạng/DNS thực sự cho đường trực tiếp. Nếu nội bộ vẫn phải qua proxy, đừng đưa hostname vào bypass list.
- Host nội bộ kiểu `repo.corp.example` có thể dùng proxy hoặc bypass tùy kiến trúc, không có quy tắc “nội bộ là luôn bypass”.

**Không cần commit đoạn này** vào `gradle.properties` của project nếu proxy chỉ dành cho một văn phòng/CI. Đặt proxy cụ thể trong source có thể làm laptop ngoài mạng nội bộ không build được.

### 4.2. Phân biệt ba vị trí tương tự nhau

~~~text
project/
├── gradle.properties                 # Root project Gradle properties
├── .gradle/                          # Project-local state, khong phai User Home
└── gradle/wrapper/...

<GRADLE_USER_HOME>/
├── gradle.properties                 # Machine/user configuration
├── caches/
├── daemon/
└── wrapper/dists/
~~~

Gradle User Home mặc định thường là `~/.gradle` (Linux/macOS) hoặc profile người dùng tương ứng trên Windows; có thể thay bằng `GRADLE_USER_HOME`. Trong multi-project build, Gradle chỉ xét `systemProp.*` trong **root project `gradle.properties`** khi đọc project properties; đặt `systemProp.https.proxyHost` trong `subproject/gradle.properties` không có hiệu lực như người dùng thường mong đợi. Dùng user-level properties hoặc root project file thích hợp.

Nếu dùng file root được commit chỉ để mô tả môi trường build, **không đặt proxy password, username nhạy cảm hoặc private key** trong đó. Tránh chia sẻ nguyên User Home vì còn chứa cache và logs.

### 4.3. Có cần cấu hình cả http và https?

Nếu các endpoint đều là HTTPS, `https.proxyHost`/`https.proxyPort` là phần chính. Tuy nhiên có build hoặc redirect sử dụng HTTP; thiết lập cả hai theo thông số tổ chức giúp nhất quán. Không “sửa” TLS certificate lỗi bằng cách chuyển repository HTTPS sang HTTP; kết nối tới repository và artifact cần được bảo vệ.

Proxy server dùng địa chỉ `proxy.corp.example:8080` không nhất thiết là một HTTPS server; đó thường là địa chỉ HTTP proxy thực hiện **CONNECT** để tạo đường hầm tới host HTTPS. Đừng tự chuyển host thành URL hay thêm `https://` vào giá trị `https.proxyHost`, vì thuộc tính này thường mong **hostname**, không phải URL hoàn chỉnh.

## 5. Proxy authentication khác repository authentication

Một request qua proxy có thể trải qua **hai lớp xác thực riêng**:

~~~text
Gradle client
   |
   |  Proxy-Authorization (neu proxy yeu cau)
   v
Forward proxy
   |
   |  Authorization (neu repository yeu cau)
   v
Maven repository
~~~

Các response thường giúp nhận diện:

| Mã | Phía có thể trả về | Ý nghĩa phổ biến |
| --- | --- | --- |
| **407 Proxy Authentication Required** | Proxy | Thiếu/sai thông tin đăng nhập proxy hoặc scheme không hợp lệ |
| **401 Unauthorized** | Repository/origin server | Thiếu/sai credentials của repository, hoặc cơ chế auth không đúng |
| **403 Forbidden** | Repository/gateway/ACL | Đã đi tới nơi nào đó nhưng không được phép truy cập; đôi khi là policy chặn |
| **404 Not Found** | Repository/mirror | Sai đường dẫn artifact/plugin, chưa tồn tại, hoặc hệ thống che resource không có quyền |
| **429 Too Many Requests** | Gateway/server | Bị rate limit; cần backoff theo chính sách |
| **502/503/504** | Gateway/proxy/origin | Lỗi upstream, bảo trì hoặc timeout gateway |

Không suy từ HTTP status một cách tuyệt đối: proxy doanh nghiệp hoặc repository manager có thể chuyển đổi/che lỗi. Dựa vào response headers an toàn, URL đích, tài liệu hệ thống và server logs của người có quyền.

### 5.1. Proxy credentials

Gradle Networking Guide có các Java system properties như:

~~~properties
# Duong dan: GRADLE_USER_HOME/gradle.properties
systemProp.https.proxyHost=proxy.corp.example
systemProp.https.proxyPort=8080
# Neu proxy bat buoc dang nhap, cung cap cac keys sau
# tu cau hinh user/secret store duoc quan ly:
# systemProp.https.proxyUser
# systemProp.https.proxyPassword
~~~

Đây là **chỉ dẫn tên khóa**, không phải một file đầy đủ với credentials. Không ghi mật khẩu thật trong ví dụ, tài liệu, source hoặc screenshot. Nếu buộc lưu credentials trong user-level properties, bảo vệ quyền đọc file, phân quyền tối thiểu và áp dụng chính sách xoay vòng. Một số proxy dùng NTLM/SSO/Kerberos hoặc policy riêng, không giải quyết được chỉ bằng username/password thông thường; cần cấu hình được đội mạng hỗ trợ.

### 5.2. Repository credentials

Với Maven repository riêng, nên dùng Gradle Credentials API, không tự ghép token vào URL:

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials

repositories {
    maven {
        name = "corpReleases"
        url = uri("https://maven.corp.example/repository/releases")
        credentials(PasswordCredentials::class)
    }
}
~~~

Đây là **snippet cho `build.gradle.kts`**, yêu cầu Maven endpoint thật và có quyền truy cập. Gradle lookup project properties theo repository identity như `corpReleasesUsername` và `corpReleasesPassword`; các giá trị thực tế có thể cấp từ user-level `gradle.properties` hoặc biến môi trường `ORG_GRADLE_PROJECT_corpReleasesUsername`/`ORG_GRADLE_PROJECT_corpReleasesPassword` trong CI.

**`https.proxyUser`/`https.proxyPassword` không thay thế `corpReleasesUsername`/`corpReleasesPassword`.** Nếu mạng trả 407, kiểm tra proxy; nếu repository trả 401/403, kiểm tra repository credentials và quyền.

Không bật chế độ log cả HTTP headers để thử “xem mật khẩu đã truyền chưa”. Một giá trị bảo mật xuất hiện trong log là một sự cố cần xử lý, không phải thành công chẩn đoán.

## 6. Repository ở đâu: pluginManagement và dependencyResolutionManagement

Một cấu hình proxy chính xác cũng không cứu được một build tìm **sai repository**.

Gradle tách plugin repositories khỏi dependency repositories. Trong multi-project build hoặc dự án muốn quản lý tập trung, có thể cấu hình **`settings.gradle.kts`**:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "repository-network-demo"
~~~

- `pluginManagement.repositories` là nơi resolve các plugin được khai báo trong `plugins { ... }`, đặc biệt plugin bên ngoài Gradle.
- `dependencyResolutionManagement.repositories` là nơi lấy **application/library dependencies** của project theo cơ chế tập trung.
- `RepositoriesMode.FAIL_ON_PROJECT_REPOS` cấm project tự thêm repository ngoài tập trung. Khi dùng nó, đừng thêm lại `repositories { mavenCentral() }` trong `build.gradle.kts`; Gradle có thể báo lỗi do chế độ repository policy, **không phải lỗi mạng**.
- Nếu dự án dùng chế độ khác như `PREFER_PROJECT` hoặc `PREFER_SETTINGS`, precedence của repositories thay đổi, cần đọc cấu hình thực tế.

Các phần tử `java` và `application` thuộc các plugin Gradle tích hợp sẵn, không cần Gradle Plugin Portal để tải plugin binary riêng. Ngược lại, plugin bên thứ ba có thể yêu cầu repository và plugin marker khác với dependency Maven thông thường.

### 6.1. Phân biệt URL của plugin và module

Một thông báo kiểu:

~~~text
Plugin [id: 'some.plugin', version: 'x.y'] was not found
~~~

không nhất thiết là lỗi proxy. Có thể plugin ID/version sai, plugin marker không nằm trong repository khai báo hoặc repository nội bộ chưa mirror plugin portal. Nếu lỗi là:

~~~text
Could not resolve org.example:library:1.0
~~~

hãy kiểm tra classpath configuration, `repositories` cho project và repository thực sự có module/version đó. Nếu lỗi ở task `publish`, nơi nhận upload là **publishing repository**, không phải tự động là repository dùng để download.

**Đừng thay `pluginManagement` bằng `repositories` của project hoặc ngược lại** khi khoanh vùng lỗi.

## 7. TLS là gì và proxy ảnh hưởng HTTPS thế nào?

TLS (Transport Layer Security) giúp mã hóa kết nối và xác thực danh tính server qua chứng chỉ số. Với HTTPS, JVM cần kiểm tra ít nhất các khía cạnh:

- Chuỗi chứng chỉ có đi tới một **CA được tin cậy** không?
- Hostname trong URL có khớp **SAN (Subject Alternative Name)** của certificate không?
- Chứng chỉ có còn hiệu lực, đúng mục đích, và được server gửi cùng intermediate chain phù hợp không?
- Client và server (hoặc TLS inspection appliance) có hỗ trợ chung TLS protocol/cipher suite không?
- Kết nối qua proxy có thiết lập CONNECT/tunnel hoặc TLS interception đúng theo chính sách không?

**HTTPS qua forward proxy thông thường:**

~~~text
JVM (Gradle)
   |
   | CONNECT repo.maven.apache.org:443
   v
Forward proxy
   |
   | TCP tunnel
   v
TLS handshake voi repo.maven.apache.org
   |
   v
Maven Central
~~~

Nếu tổ chức dùng **TLS inspection**, proxy có thể chấm dứt TLS rồi cấp một certificate cho hostname repository được ký bởi **CA nội bộ**. Lúc này trình duyệt có thể truy cập thành công vì tin CA nội bộ trong OS/browser trust store, trong khi JDK của Gradle chưa tin CA đó. Kết quả: `SSLHandshakeException` hoặc `PKIX path building failed`.

**Không chữa bằng “trust all certificates”.** Việc tắt hostname verification, sửa mã để bỏ qua `X509TrustManager` hay đổi URL sang HTTP làm mất xác thực endpoint, tạo nguy cơ man-in-the-middle và artifact bị thay đổi.

## 8. JDK truststore: khi nào cần và cách cấu hình an toàn

Java có cơ chế **truststore** để chứa những CA/certificates được tin cậy cho TLS. Nhiều JDK sử dụng truststore mặc định `cacerts`, nhưng vị trí, nội dung và sự tích hợp với certificate store hệ điều hành khác nhau theo vendor/JDK/thiết lập.

Nếu repository dùng certificate công khai hợp lệ, thông thường JDK đủ mới đã có CA phù hợp. Khi dùng CA nội bộ hoặc TLS inspection, cần đội bảo mật cung cấp **certificate CA chính thống** và xác nhận đường tin cậy. Không import bất cứ certificate nào lấy từ một trang lỗi không xác thực, và không tự chấp nhận certificate không rõ nguồn.

### 8.1. Ưu tiên truststore riêng thay vì sửa cacerts toàn hệ thống

Giả sử đội an ninh cấp một file PEM `corp-root-ca.pem` đã được xác minh qua kênh đáng tin cậy. Dùng JDK keytool để **tạo một truststore riêng**:

~~~bash
keytool -importcert \
  -alias corp-root-ca \
  -file corp-root-ca.pem \
  -keystore gradle-truststore.p12 \
  -storetype PKCS12
~~~

Trên PowerShell có thể dùng một dòng:

~~~powershell
keytool -importcert -alias corp-root-ca -file corp-root-ca.pem -keystore gradle-truststore.p12 -storetype PKCS12
~~~

Lệnh sẽ yêu cầu thao tác xác nhận và/hoặc mật khẩu qua prompt tùy JDK/tình trạng keystore. Hãy đối chiếu fingerprint certificate với thông tin do đội bảo mật cung cấp **trước khi chọn tin cậy**. Không đưa private key vào truststore chỉ để kiểm tra server. Truststore chứa các public certificates; mật khẩu truststore và quyền đọc file vẫn cần bảo vệ theo chính sách.

Có thể xem certificate đã import:

~~~bash
keytool -list -v -keystore gradle-truststore.p12 -storetype PKCS12 -alias corp-root-ca
~~~

Đây là lệnh kiểm tra **local**, không gửi file certificate lên mạng.

### 8.2. Chỉ định truststore cho JVM mà Gradle dùng

Khi đã có đường dẫn truststore tuyệt đối hợp lệ, cách cấu hình có thể là Java system properties trong **`GRADLE_USER_HOME/gradle.properties`**:

~~~properties
# Vi du tren Linux/macOS; phai dung duong dan local da ton tai.
systemProp.javax.net.ssl.trustStore=/home/developer/security/gradle-truststore.p12
systemProp.javax.net.ssl.trustStoreType=PKCS12
~~~

Đây là **ví dụ định dạng**: nếu môi trường yêu cầu password, phải cấp/kiểm soát nó theo hướng dẫn JDK và chính sách nội bộ; tránh đưa password vào command line hoặc file được commit. Nếu set `javax.net.ssl.trustStore` trỏ tới file không tồn tại hoặc sai type, hành vi tin cậy TLS có thể trở nên lỗi hơn trước.

Một cách khác là cấu hình JVM arguments cho **Gradle Daemon**, ví dụ thuộc tính `org.gradle.jvmargs` trong user-level properties:

~~~properties
# Vi du: can phoi hop voi nhung JVM args khac cua du an.
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8 -Djavax.net.ssl.trustStore=/home/developer/security/gradle-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12
~~~

**Lưu ý:** việc đặt lại `org.gradle.jvmargs` có thể thay đổi các JVM arguments khác đang có; phải kết hợp với cấu hình hiện hữu. Không ghi password trực tiếp vào command-line visible hoặc commit properties có chứa credentials. Nếu có yêu cầu dùng truststore password, cân nhắc cơ chế cấp bảo mật do tổ chức quản lý.

Trên Windows, có thể dùng đường dẫn dạng forward slash khi JDK/đường dẫn cho phép, chẳng hạn `C:/secure/gradle-truststore.p12`, để giảm sai escape trong file `.properties`. Không dùng literal `C:\some\path` mà không hiểu quy tắc escape của Java properties.

### 8.3. JDK chạy Gradle khác Java toolchain dùng biên dịch

Lỗi TLS download dependency xảy ra trong **JVM của Gradle/Daemon và thư viện network liên quan**. Nó không được chữa bằng cách chỉ đổi `java.toolchain.languageVersion` của task `JavaCompile`.

Kiểm tra:

~~~bash
./gradlew --version
~~~

Lệnh thường in thông tin Gradle và JVM. Tuy nhiên, môi trường hiện đại còn có Daemon JVM criteria hoặc `org.gradle.java.home`, khiến launcher và daemon dùng JDK khác nhau. Hãy xác minh JDK thực sự chạy tác vụ liên quan; đừng chỉ nhìn giá trị `JAVA_HOME` hoặc JDK mà IDE dùng để compile Java.

Sau khi thay đổi truststore, proxy hoặc daemon JVM settings, nếu cần có thể dừng daemon theo cách có kiểm soát để những phiên build sau sử dụng cấu hình mới:

~~~bash
./gradlew --stop
./gradlew --version
~~~

`--stop` chỉ yêu cầu dừng các daemon Gradle phù hợp; không xóa source, không xóa cache. Tránh chạy khi có build quan trọng đang dùng các daemon đó.

## 9. Các lỗi SSLHandshakeException và PKIX thường gặp

| Dấu hiệu trong exception | Giả thuyết chính | Cách kiểm tra hợp lý |
| --- | --- | --- |
| `PKIX path building failed` | Không tìm được trust anchor phù hợp, thiếu CA hoặc intermediate, TLS inspection | Kiểm tra chain thực và truststore của đúng JDK |
| `unable to find valid certification path to requested target` | JVM không dựng được certificate chain đáng tin | Xác minh CA nguồn chính thống, intermediate, môi trường proxy |
| `No subject alternative names matching ...` | URL hostname không khớp certificate SAN | Kiểm tra hostname, reverse proxy và certificate phía server |
| `certificate expired` / `NotAfter` | Certificate hết hạn hoặc giờ hệ thống sai | Kiểm tra thời gian máy và hạn cert, liên hệ admin |
| `Received fatal alert: handshake_failure` | Protocol/cipher/client certificate/SNI/inspection incompatibility | So sánh JDK, TLS versions và policy server/proxy |
| `protocol_version` | Client/server không có phiên bản TLS chung | Nâng cấp JDK/Gradle phù hợp; sửa cấu hình server, không bật TLS cũ nguy hiểm |
| `Connection reset` ngay lúc handshake | Proxy/firewall đóng kết nối hoặc server/network issue | Kiểm tra CONNECT, proxy logs, TCP path, chính sách TLS |
| `Remote host terminated the handshake` | Server/proxy đóng handshake | Xem nguyên nhân gốc ở proxy/JVM/server trước khi thay đổi code |

Nếu trình duyệt truy cập được nhưng Gradle thất bại, cần so sánh **cùng hostname, cùng proxy route, cùng CA, cùng account và cùng JDK**. Trình duyệt và Gradle không nhất thiết có trust store hoặc proxy settings giống nhau.

### 9.1. Có nên cưỡng ép TLS version?

JDK và Gradle có các cách cấu hình phiên bản TLS, ví dụ Java property `https.protocols`, nhưng **không nên đặt một giá trị cố định vô cớ**. JDK 17+ thường hỗ trợ các phiên bản hiện đại theo policy. Nếu server cũ chỉ hỗ trợ protocol không an toàn, nên nâng cấp hoặc sửa server theo hướng dẫn bảo mật, thay vì hạ khả năng bảo vệ của mọi dependency download.

Trong môi trường yêu cầu TLS interception, phải có CA nội bộ được phê duyệt, certificate chain đúng và hostname validation còn hiệu lực.

## 10. Quy trình chẩn đoán 7 bước theo thứ tự

### Bước 1 — Xác định chính xác pha và hostname đang lỗi

Đọc lỗi sau khi đã **lọc dữ liệu nhạy cảm**. Ghi riêng:

- Lệnh đang chạy: `./gradlew --version`, `help`, `compileJava`, `test`, `publish`?
- Hostname: Gradle distribution, Plugin Portal, Maven Central, repository nội bộ hay publishing server?
- Hoạt động: wrapper download, plugin resolution, dependency resolution, upload?
- Exception sâu nhất / HTTP status: `UnknownHostException`, `ConnectException`, `SSLHandshakeException`, 407, 401, 404...?
- Lỗi chỉ xảy ra ở CI hay cả laptop? Có liên quan VPN/proxy khác không?

Tối thiểu hóa thông tin chia sẻ: không gửi Authorization header, proxy password, URL có token, private key hoặc full environment dump lên ticket.

### Bước 2 — Phân biệt lỗi Wrapper với lỗi Gradle runtime

Nếu chưa tải được Gradle distribution, có thể thấy:

~~~text
Downloading https://services.gradle.org/distributions/gradle-...-bin.zip
...
java.net.SocketTimeoutException
~~~

Lúc này build script và project repositories **chưa chạy**. Kiểm tra `distributionUrl` trong `gradle/wrapper/gradle-wrapper.properties`, proxy/trust của JVM khởi động Wrapper, quyền kết nối tới distribution host hoặc mirror do tổ chức quản lý.

`gradle-wrapper.properties` chủ yếu xác định distribution/version, không phải nơi đúng để lưu proxy password. Tránh gắn credentials vào `distributionUrl` vì file này thường được commit. Với private distribution server, Gradle Wrapper có cơ chế riêng cho credentials, kể cả các property giới hạn theo hostname; tham khảo tài liệu chính thức trước khi dùng.

Nếu `./gradlew --version` thành công nhưng `./gradlew compileJava` thất bại khi tải module, Wrapper đã vượt qua bước đầu; chuyển sang dependency repositories.

### Bước 3 — Kiểm tra DNS và TCP từ chính máy/CI runner

Linux/macOS (các lệnh tùy hệ điều hành và gói cài):

~~~bash
# Hoi DNS (khong can password).
nslookup repo.maven.apache.org

# Kiem tra HTTP/TLS endpoint o muc khac voi Gradle.
curl -I https://repo.maven.apache.org/maven2/
~~~

Windows PowerShell:

~~~powershell
Resolve-DnsName repo.maven.apache.org
Test-NetConnection repo.maven.apache.org -Port 443
curl.exe -I https://repo.maven.apache.org/maven2/
~~~

**Cách hiểu đúng:**

- `Resolve-DnsName` hoặc `nslookup` thành công chỉ xác nhận một góc của DNS, chưa đảm bảo endpoint kết nối được qua proxy.
- `Test-NetConnection` tới repository là **kết nối trực tiếp**; trên mạng buộc qua proxy, kiểm tra trực tiếp có thể thất bại hoàn toàn bình thường.
- `curl` có thể tự đọc `HTTPS_PROXY`/`NO_PROXY` hoặc hệ thống CA khác với JVM. Thành công ở `curl` **không chứng minh** Gradle cũng dùng đúng proxy hoặc tin cùng CA.
- HTTP HEAD `-I` có thể bị repository chặn (405/403) dù GET cho artifact hợp lệ. Dựa vào DNS/TLS/status và chính sách endpoint, không coi mọi non-200 là lỗi Gradle.

Không dùng `curl -v` hoặc dump HTTP headers trên CI log chứa credentials nếu chưa có phương án redaction.

### Bước 4 — Kiểm tra proxy host/port và bypass

Đối chiếu với đội mạng:

- `https.proxyHost`/`https.proxyPort` chính xác và reachable?
- Proxy có yêu cầu xác thực? Có dùng NTLM/SSO mà Java properties thông thường chưa đủ?
- `http.nonProxyHosts` có vô tình bypass hostname cần đi proxy không?
- Máy dev đi qua VPN, còn CI runner đi một subnet khác?
- Có HTTPS inspection làm thay certificate chain không?

Có thể kiểm tra **kết nối tới proxy host/port** thay vì chỉ thử repository:

~~~powershell
Test-NetConnection proxy.corp.example -Port 8080
~~~

Đây là lệnh minh họa, thay hostname bằng proxy thực tế. Kết nối TCP thành công chỉ cho biết cổng reachable, không chứng minh proxy đã cho phép CONNECT đến repository hay đã xác thực thành công.

### Bước 5 — Phân biệt TLS và authentication

- `407`: làm việc với proxy credentials/policy, không thay Maven dependency version.
- `401` hoặc `403` từ origin repository: kiểm tra repo credentials, token quyền, path, HTTPS policy.
- `PKIX`: kiểm tra đúng JDK truststore, chain CA, TLS inspection. Không chuyển sang HTTP.
- `UnknownHostException`: DNS, VPN, proxy bypass/hostname.
- `Connect timed out` / `Read timed out`: đường mạng, firewall, server load, proxy, timeout, DNS path.
- `404`: kiểm tra tọa độ artifact, plugin ID/version và repository URL/context path, chưa đủ kết luận có lỗi network.

Chỉ khi đã biết lỗi thuộc loại nào mới thay đổi cấu hình; không thay đồng thời proxy, JDK, repositories và credentials vì sẽ mất khả năng xác định nguyên nhân.

### Bước 6 — Dùng Gradle diagnostics có chủ đích

~~~bash
# Hien thi Gradle/JVM; co the download Wrapper neu chua cache.
./gradlew --version

# Xem cau hinh chung; co the khong resolve dependency app.
./gradlew help --stacktrace --console=plain

# Resolve graph cua configuration thuc su co dependency.
./gradlew dependencies --configuration compileClasspath --info --console=plain

# Yeu cau Gradle kiem tra lai metadata/dynamic resolution.
./gradlew dependencies --configuration compileClasspath --refresh-dependencies --console=plain
~~~

Nếu project không có plugin Java thì `compileClasspath` có thể không tồn tại; phải chọn configuration **resolvable có thật** của project. `dependencies` giúp xem graph và metadata, **không bảo đảm download toàn bộ JAR** nếu artifact file chưa cần. Khi cần kiểm tra tải file thực tế, dùng task `compileJava`/`run` của một project kiểm chứng có dependency hợp lệ.

Các cờ có ý nghĩa:

| Cờ | Giúp gì? | Không làm được gì? |
| --- | --- | --- |
| `--stacktrace` | Xem chuỗi nguyên nhân exception | Không sửa mạng/TLS |
| `--info` | Có thêm log resolution/HTTP ở mức Gradle cho phép | Không chứng minh rằng mọi credentials được ẩn an toàn |
| `--debug` | Rất nhiều log, chỉ dùng khi cần ở môi trường tin cậy | Có thể tiết lộ endpoint/headers/thông tin nhạy cảm |
| `--refresh-dependencies` | Yêu cầu kiểm tra lại metadata và trạng thái dependency theo cơ chế Gradle | Không đổi CA/proxy/permissions; không phải luôn xóa mọi artifact đã tải |
| `--offline` | Chỉ dùng dữ liệu dependency đã cache để phân giải khi có thể | Không chứng minh internet đã sửa; có thể fail nếu cache chưa đủ |
| `--stop` | Dừng Gradle daemons để lượt sau dùng cấu hình JVM mới khi cần | Không xóa cache hoặc chữa lỗi cert |

**Thứ tự đề xuất:** bắt đầu với `--stacktrace` và `--info`; chỉ dùng `--debug` tạm thời trong môi trường không có secrets, và kiểm tra log trước khi lưu/chia sẻ. Không chạy nhiều lệnh debug song song làm tăng rate-limit hay tải nhiều lần không cần thiết.

### Bước 7 — Kiểm tra output sau khi sửa từng lớp

Sau khi chỉnh **một** biến (proxy, bypass, JDK truststore, repository URL, credentials), chạy lại cùng tác vụ gây lỗi với cùng môi trường. Ghi nhận:

- Gradle resolve plugin/dependency ở đúng host chưa?
- Có thoát khỏi lỗi 407/PKIX/timeout để chuyển sang lỗi khác không?
- Dependency graph có đúng artifact/version không?
- Lỗi chỉ còn ở CI hay ở máy cá nhân?
- Có tạo file output và test chạy thành công không?

Một build chạy bằng `--offline` hoặc may mắn dùng cache cũ **không đủ** để kết luận đường kết nối mới đã hoạt động.

## 11. Demo Java 17+ kiểm tra repository bằng một dependency thật

Có thể dùng một project riêng, **không chứa secret**, để tách việc resolve Maven Central khỏi ứng dụng lớn. Cần Gradle Wrapper còn hoạt động, JDK 17+ tương thích với phiên bản Gradle, và mạng cho phép truy cập Maven Central (trực tiếp hoặc proxy).

Cấu trúc:

~~~text
repository-connectivity-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/java/example/Main.java
~~~

### 11.1. settings.gradle.kts

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "repository-connectivity-demo"
~~~

### 11.2. build.gradle.kts

~~~kotlin
plugins {
    application
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}

application {
    mainClass.set("example.Main")
}
~~~

### 11.3. src/main/java/example/Main.java

~~~java
package example;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(StringUtils.capitalize("gradle repository"));
    }
}
~~~

Trong project này, plugin `application` cung cấp Java compile/runtime tasks và Gradle sẽ cần lấy `commons-lang3` từ Maven Central nếu chưa có dữ liệu phù hợp trong cache.

Chạy Linux/macOS:

~~~bash
./gradlew --version
./gradlew -q run --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat -q run --console=plain
~~~

Khi mạng/JVM/repository đều hoạt động và dependency đã resolve, dòng do chương trình in là:

~~~text
Gradle repository
~~~

Lưu ý: ví dụ này không in “proxy đã hoạt động”, chỉ cho thấy một dependency Maven Central được dùng thành công trong build. Nếu artifact đã cache từ trước, kết quả **chưa chứng minh lần chạy đã truy cập mạng**. Chạy tại môi trường test sạch được kiểm soát hoặc kiểm tra network/proxy logs an toàn khi cần xác minh mạng thực sự.

### 11.4. Thử trạng thái offline để phân biệt cache với mạng

Sau một lượt build thành công, chạy:

~~~bash
./gradlew -q run --offline --console=plain
~~~

Nếu dependencies/plugin/Gradle distribution cần thiết đã được cache, build có thể tiếp tục thành công. Nếu cache chưa đủ, lệnh có thể báo thiếu dependency. Điều này giúp hiểu vai trò cache nhưng **không thay thế test online** và không chứng minh proxy/TLS đã được cấu hình đúng.

Không xóa nguyên `~/.gradle/caches` chỉ để kiểm tra khi máy làm việc còn build quan trọng. Có thể dùng môi trường Gradle User Home test riêng theo quyền được cấp, nhưng không được sao chép credentials từ user thật một cách không kiểm soát.

## 12. Hướng dẫn xử lý một số lỗi cụ thể

### 12.1. UnknownHostException

Nguyên nhân có thể: hostname repository sai, DNS resolver chưa biết tên nội bộ, VPN chưa nối, DNS của container/runner khác desktop, hoặc proxy bypass nhầm khiến client truy cập trực tiếp host không thể phân giải.

Quy trình:

1. Xác định hostname thật từ lỗi **đã ẩn dữ liệu nhạy cảm**.
2. Dùng `nslookup` / `Resolve-DnsName` trong **chính môi trường build**.
3. Xem client thực sự kết nối **proxy** hay **host đích**.
4. Kiểm tra `http.nonProxyHosts` và hostname trong repository settings.
5. Không sửa bằng cách hardcode IP hoặc tắt xác thực hostname TLS.

### 12.2. HTTP 407

Đây thường là proxy chưa chấp nhận xác thực.

1. Đảm bảo host/port proxy đúng.
2. Kiểm tra credentials/proxy auth scheme qua hạ tầng.
3. Nếu NTLM/SSO, Gradle/JDK có thể cần domain hoặc cấu hình hỗ trợ; hỏi đội mạng thay vì nhúng password vào script.
4. Kiểm tra CI có được cấp quyền truy cập proxy từ runner không.
5. Không thay `corpReleasesPassword` để chữa `https.proxyPassword` nếu lỗi đến từ proxy.

### 12.3. HTTP 401 hoặc 403 từ repository

1. Kiểm tra URL context path của Maven server và request method.
2. Xác nhận token/username được cấp quyền download/publish đúng repository.
3. Kiểm tra credentials API và tên property tương ứng với tên repository.
4. Phân biệt token hết hạn, policy theo IP hoặc permission denied.
5. Không chụp màn hình hoặc paste URL mang credentials để nhờ debug.

### 12.4. PKIX path building failed

1. Xác định JDK đang chạy Gradle, không chỉ JDK compile.
2. Kiểm tra certificate chain của endpoint **qua cùng proxy route**.
3. Xác minh có TLS inspection và CA nội bộ được duyệt.
4. Cấp trusted CA chain vào truststore riêng đã bảo vệ, hoặc sửa server gửi intermediate chain đầy đủ.
5. Không tắt verification, không thêm `allowInsecureProtocol`, không chuyển HTTPS thành HTTP.

### 12.5. Timeout / Connection reset

1. Xác định timeout xảy ra khi DNS, TCP connect, HTTP CONNECT, TLS handshake hay download body.
2. Kiểm tra proxy/gateway logs, firewall ACL, VPN và service health.
3. Kiểm tra vấn đề chỉ xuất hiện ở CI, khi chạy song song hoặc khi file artifact lớn.
4. Tham khảo điều chỉnh timeout/retry của thành phần liên quan **sau khi xác định mạng đã đúng**; tăng timeout không sửa credentials hay CA.
5. Không vô hạn tăng retry khi server trả 401/403/407 hoặc 404.

### 12.6. Plugin resolution lỗi nhưng dependency resolution vẫn tốt

1. Kiểm tra plugin ID/version.
2. Xem `pluginManagement.repositories` trong settings.
3. Đối chiếu công ty có mirror Gradle Plugin Portal/plugin marker hay chưa.
4. Nếu dùng init scripts hoặc enterprise settings plugin, kiểm tra repository policy.
5. Không kết luận Maven Central hoàn toàn bị chặn chỉ vì một plugin không tồn tại.

## 13. Gradle Wrapper bootstrap: một trường hợp đặc biệt

Wrapper tải Gradle distribution **trước khi** Gradle build scripts có thể được đánh giá. Nó dùng cấu hình URL trong:

~~~text
gradle/wrapper/gradle-wrapper.properties
~~~

Chẳng hạn dòng (chỉ minh họa cấu trúc):

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
~~~

Phiên bản trong URL **phải phù hợp với Wrapper của project và chính sách môi trường**; không sao chép một version bất kỳ vào production chỉ để sửa kết nối.

Khi Wrapper không tải được:

- Kiểm tra Internet/proxy tới hostname distribution (có thể có redirects).
- Kiểm tra Java/Wrapper JVM truststore và proxy system properties từ nơi Wrapper hỗ trợ.
- Nếu doanh nghiệp dùng mirror distribution nội bộ, cấu hình URL được đội hạ tầng duyệt cùng xác minh checksum.
- Với private distribution, dùng cơ chế credentials chính thức của Wrapper, ưu tiên properties được giới hạn theo hostname để tránh phát tán credential sang host khác.
- Không thêm token vào `distributionUrl` được commit.
- Không bỏ qua checksum hoặc vô hiệu hóa URL/certificate validation chỉ để chạy qua lỗi.

Tùy phiên bản Wrapper, `gradle-wrapper.properties` có thể có `networkTimeout`, `retries` và backoff; chúng hỗ trợ mạng chậm nhưng không giải quyết sai CA/proxy auth/host.

**Điểm quyết định:** nếu lỗi xảy ra tại Wrapper bootstrap, các task báo cáo `dependencies` hay `outgoingVariants` chưa thể chạy. Phải giải quyết đường tải Gradle distribution trước.

## 14. Gradle trên CI/CD: cùng build, môi trường mạng khác

Một project chạy được trên laptop vẫn có thể fail trên CI vì:

- CI runner nằm trong VPC/subnet riêng, DNS khác máy dev.
- Proxy chỉ cho phép một nhóm IP hoặc tài khoản được truy cập.
- Truststore/JDK của runner khác Java trên laptop.
- CI chưa được cấp private repository credentials hoặc corporate CA.
- Container image không mang chính sách proxy của host, trong khi build local chạy ngoài container.
- CI cache có thể che lỗi network một thời gian; sau khi miss, build mới thất bại.

### 14.1. Thiết kế cấu hình CI

- **Proxy endpoint/port không nhạy cảm:** cấp từ cấu hình runner/managed image hoặc user-level Gradle properties cho job; không hardcode theo một mạng vào project chung.
- **Proxy credentials:** cấp từ CI secret manager, đúng scope, không in ra log. Có thể dùng cấu hình file Gradle User Home được tạo an toàn cho job, với quyền file giới hạn; xóa theo lifecycle runner. Không upload file ấy làm artifact.
- **TLS trust:** cài CA nội bộ đã được xác minh vào truststore của **JDK chạy Gradle** hoặc tạo truststore riêng cho job, không tắt certificate verification.
- **Repository credentials:** dùng Gradle repository credentials API và project properties từ CI secret store, tách với proxy credentials.
- **Isolation:** không chạy code từ PR không tin cậy trong job có secrets publish/repository đặc quyền; giới hạn permission, token sống ngắn và scope.
- **Caching:** chỉ cache những thư mục được chính sách cho phép; tránh upload nguyên Gradle User Home vì có properties, daemon logs, init scripts và metadata nhạy cảm.
- **Logging:** `--info` hay `--debug` có thể lộ topology hoặc thông tin nhạy cảm; kiểm tra trước khi đăng log lên ticket/PR.

### 14.2. Một bảng so sánh để khoanh vùng

| Kiểm tra | Laptop thành công, CI lỗi | Kết luận có cơ sở |
| --- | --- | --- |
| Cùng Wrapper version? | Khác | Có thể khác TLS/runtime behavior; chuẩn hóa Wrapper |
| Cùng JDK chạy Gradle? | Khác | Khác truststore/CA/protocol; so sánh JVM |
| Cùng proxy host/route? | Khác | Kiểm tra network policy của runner |
| Cùng repository URL/settings? | Khác | Có thể resolve từ mirror khác |
| Credentials có được cấp ở đúng step? | Không | Sửa secret scope/authorization; không hardcode |
| Cache có artifact? | Laptop có, CI không | Laptop có thể thành công dù network chưa thực sự hoạt động |
| DNS/cert chain qua route thực tế? | Khác | Cần đội mạng/PKI điều tra đường kết nối |

## 15. Bảo mật: những cách “chữa nhanh” phải tránh

Không dùng các biện pháp sau trong build production:

1. **Tắt TLS certificate validation** bằng custom trust manager tin tất cả certificate.
2. **Tắt hostname verification** khi hostname trong URL không khớp certificate.
3. **Chuyển repository từ HTTPS sang HTTP** hoặc bật `allowInsecureProtocol = true` để né `PKIX`. Gradle yêu cầu opt-in HTTP không bảo mật trong vài bối cảnh, nhưng việc opt-in **không sửa** chứng chỉ và làm giảm an toàn.
4. **Dán proxy password vào `build.gradle.kts`** hoặc file được commit.
5. **Đưa username/password/token vào URL** và lưu URL trong log/metadata.
6. **Dùng `--debug` hoặc `javax.net.debug` ở pipeline có credentials thật** rồi đăng nguyên log công khai. Các trace SSL có thể tiết lộ thông tin kết nối, certificate và metadata; phải xử lý theo chính sách.
7. **Xóa hết Gradle cache hoặc nâng/downgrade TLS vô cớ**: có thể che triệu chứng, gây tải thêm hoặc giảm bảo mật, nhưng không giải quyết gốc.
8. **Import certificate không xác minh fingerprint** từ máy/website không đáng tin.
9. **Tắt dependency verification/checksum** khi nghi proxy/mirror trả file bị thay đổi.
10. **Dùng cùng tài khoản publish quyền cao cho mọi build đọc dependency**.

Nếu log hoặc source đã lộ password/token, coi đó là sự cố: giới hạn chia sẻ, thu hồi/rotate credential, kiểm tra Git history/log/artifact/cache và điều chỉnh pipeline để tránh tái diễn.

## 16. Cây quyết định nhanh: từ lỗi đến hành động

~~~text
Gradle khong truy cap duoc repository?
  |
  +-- Dang Downloading gradle-...-bin.zip?
  |     -> Wrapper distribution, proxy/CA cua Wrapper, distributionUrl.
  |
  +-- Plugin not found / plugin resolution?
  |     -> pluginManagement.repositories + proxy/TLS + plugin ID/version.
  |
  +-- Could not resolve module?
  |     -> dependency repositories + coordinates + proxy/TLS + credentials.
  |
  +-- Publish/upload failed?
        -> publishing repository + permissions + network/TLS.

Sau do doc root cause:
  |
  +-- UnknownHostException
  |     -> DNS/VPN/bypass sai.
  |
  +-- Connect timed out / connection refused
  |     -> TCP route, proxy host/port, firewall, server.
  |
  +-- 407
  |     -> Proxy authentication/policy.
  |
  +-- 401/403
  |     -> Repository credentials/permissions hoac gateway policy.
  |
  +-- PKIX / certificate / hostname mismatch
  |     -> JDK truststore, chain, CA, TLS interception, SAN.
  |
  +-- 404 / artifact not found
  |     -> Repository path, dependency coordinates, version/plugin marker.
  |
  +-- 429 / 5xx
        -> Rate limit, proxy/upstream server, backoff/health.
~~~

Khi cần hỗ trợ đội mạng, gửi **tên host đích, thời gian sự cố, HTTP status/exception đã redact, Gradle version, JDK version và route/proxy name**. Không gửi password/token/cookie hoặc certificate private key.

## 17. Bài tập thực hành và đáp án

**Bài 1.** Trình duyệt vào Maven Central nhưng `./gradlew compileJava` báo `UnknownHostException`. Có thể kết luận Maven Central down không?  
**Đáp án:** chưa. Trình duyệt có thể dùng proxy/PAC khác JVM. Kiểm tra hostname, DNS, VPN, JVM `https.proxyHost` và `http.nonProxyHosts` từ chính môi trường Gradle.

**Bài 2.** Proxy HTTPS có host `proxy.corp.example` port 8080. Dùng property nào?  
**Đáp án:** `systemProp.https.proxyHost` và `systemProp.https.proxyPort` trong Gradle properties phù hợp; host được ghi là hostname chứ không phải URL hoàn chỉnh.

**Bài 3.** Muốn bypass proxy cho `localhost` và `*.corp.example` với HTTPS, dùng `https.nonProxyHosts`?  
**Đáp án:** không. Gradle/JVM dùng `http.nonProxyHosts=localhost|*.corp.example` cho HTTP và HTTPS theo tài liệu.

**Bài 4.** Gradle nhận HTTP 407, nhưng `corpReleasesUsername`/`corpReleasesPassword` chắc chắn đúng. Có mâu thuẫn không?  
**Đáp án:** không. 407 liên quan proxy; Maven repo credentials là lớp xác thực khác.

**Bài 5.** `PKIX path building failed` sau khi bật TLS inspection. Cách sửa chính thống?  
**Đáp án:** xác minh chain và CA do tổ chức phát hành, cập nhật truststore của JDK thực sự chạy Gradle theo policy; không bỏ qua TLS verification.

**Bài 6.** Cấu hình `repositories { mavenCentral() }` trong `build.gradle.kts` nhưng plugin vẫn báo không tìm thấy. Vì sao?  
**Đáp án:** plugin resolution dùng `pluginManagement.repositories` khác dependency repositories; cũng phải kiểm tra plugin ID/version và plugin marker.

**Bài 7.** `./gradlew --version` thất bại ở bước tải Gradle distribution. Sửa `dependencies` có giúp không?  
**Đáp án:** không; Wrapper bootstrap diễn ra trước khi build script được chạy.

**Bài 8.** `./gradlew run --offline` thành công sau khi mạng bị ngắt. Có chứng minh proxy mới cấu hình đúng?  
**Đáp án:** không. Có thể JAR/metadata đều đã cache. Cần kiểm thử online theo quy trình được phép.

**Bài 9.** `curl -I` thành công nhưng Gradle `PKIX` thất bại. Điều gì khác?  
**Đáp án:** curl có thể dùng CA của OS và proxy environment khác, trong khi Gradle dùng truststore/JDK riêng. So sánh cùng route và trust root.

**Bài 10.** Sau khi sửa `gradle.properties`, daemon cũ vẫn có hành vi bất thường. Có lệnh nào để restart daemon có kiểm soát?  
**Đáp án:** `./gradlew --stop` rồi chạy lại task; không xóa cache/source.

**Bài 11.** Gradle báo `404 Not Found` cho `org.sample:lib:99.0`. Có nên import CA mới?  
**Đáp án:** thường không; TLS đã đủ để nhận HTTP response. Kiểm tra dependency coordinates/version, repository URL và permissions.

**Bài 12.** Team đề xuất đổi HTTPS thành HTTP để tránh lỗi certificate. Có nên?  
**Đáp án:** không. Sửa certificate chain, CA/truststore hoặc hostname đúng cách; HTTP dễ bị can thiệp nội dung dependency.

**Bài 13.** CI runner khác laptop chỉ ở Java runtime. Vì sao có thể phát sinh lỗi TLS?  
**Đáp án:** JDK khác có trust anchors, protocol/cipher và security policies khác, dù source và Gradle scripts giống nhau.

**Bài 14.** Khi nào dùng `--refresh-dependencies`?  
**Đáp án:** khi nghi metadata/artifact cache không phản ánh repository hiện tại hoặc dynamic/changing dependencies cần kiểm tra lại; nó không sửa DNS, proxy password hay CA.

**Bài 15.** Nên gửi nguyên `--debug` log lên issue công khai để nhờ người khác phân tích?  
**Đáp án:** không. Debug log có thể chứa endpoint, headers, metadata và thông tin nhạy cảm; chỉ thu thập trong môi trường phù hợp rồi redact trước khi chia sẻ.

## 18. Checklist để đưa cấu hình repository vào dự án thật

- [ ] Phân biệt Wrapper bootstrap, plugin resolution, dependency resolution và publishing.
- [ ] Đã xác minh hostname/URL repository thật và repository scope tương ứng.
- [ ] Proxy host/port đến từ đội mạng, được cấu hình đúng với JVM Gradle, không chỉ trong browser.
- [ ] Nếu có bypass, `http.nonProxyHosts` chỉ chứa những host thực sự đi trực tiếp được.
- [ ] Proxy authentication (407) không bị nhầm với repository authentication (401/403).
- [ ] Secrets nằm ngoài source và logs, được quản lý với quyền tối thiểu.
- [ ] TLS chain/SAN được xác thực, CA nội bộ nhập từ kênh tin cậy và đúng JDK truststore.
- [ ] Không bật trust-all, không tắt hostname validation, không chuyển repo sang HTTP.
- [ ] Đã kiểm tra Gradle/JVM thực tế, nhất là sự khác nhau giữa Gradle daemon và Java toolchain.
- [ ] Lệnh `--info`/`--stacktrace` dùng có mục đích; không đăng log nhạy cảm.
- [ ] Phân biệt cache hit với kết nối mạng thật; không dùng offline result làm bằng chứng online.
- [ ] CI runner và laptop được so sánh về JDK, DNS, proxy, truststore, credentials và repository URL.
- [ ] Có quy trình rotate credentials và điều tra cache/artifact/log nếu từng bị rò rỉ.
- [ ] Khi chẩn đoán, thay **một yếu tố mỗi lần** rồi chạy lại tác vụ gốc.

## 19. Tài liệu chính thức

- [Gradle — Networking with Gradle](https://docs.gradle.org/current/userguide/networking.html): Java proxy system properties, HTTP/HTTPS, `http.nonProxyHosts` và proxy authentication.
- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): `gradle.properties`, `systemProp.*`, Gradle User Home, `org.gradle.java.home` và system properties.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): `distributionUrl`, bootstrap, proxy và private distribution credentials.
- [Gradle — Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories_adv.html): plugin repositories khác với dependency repositories.
- [Gradle — Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html): `dependencyResolutionManagement` và `RepositoriesMode`.
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): giới hạn tập repository được phép trong build.
- [Gradle — Supported Repository Protocols](https://docs.gradle.org/current/userguide/supported_repository_protocols.html): repository credentials và cách truy cập giao thức.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): cache metadata/artifacts, offline và refresh.
- [Gradle — Logging](https://docs.gradle.org/current/userguide/logging.html): `--quiet`, `--info`, `--debug`, `--stacktrace`.
- [Oracle Java — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): truststore, TLS certificate path và JVM security properties.

**Tổng kết:** muốn khắc phục lỗi repository, trước hết xác định **kết nối nào** đang lỗi (Wrapper/plugin/dependency/publish), rồi phân loại **mạng/proxy → xác thực → TLS/CA → URL/metadata/cache**. Sử dụng Java system properties đúng chỗ, giữ credentials ngoài source/log, xác minh truststore của JDK chạy Gradle và không đánh đổi tính toàn vẹn dependency để lấy một lượt build “xanh” tạm thời.