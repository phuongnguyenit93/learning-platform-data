# Chẩn đoán lỗi proxy, TLS, chứng chỉ và chế độ offline khi build Spring Boot

## 1. Xác định đúng lớp gây lỗi

Khi Maven không tải được dependency hoặc plugin, thông báo cuối thường là `Could not transfer artifact`, `Non-resolvable parent POM` hoặc `PluginResolutionException`. Đây là thao tác thất bại; nguyên nhân gốc thường nằm ở DNS, TCP, proxy, HTTP authentication, TLS certificate validation hoặc local repository.

Có bốn lớp cần phân biệt:

1. **Network:** máy chạy Maven có phân giải DNS, mở được TCP và đi tới đúng host/port không?
2. **Proxy/repository routing:** Maven có dùng đúng proxy, bypass list, mirror và repository endpoint không?
3. **TLS/authentication:** JVM có xác minh được certificate chain và hostname không? Proxy/repository có yêu cầu credentials hoặc client certificate không?
4. **Offline/cache:** Maven có đủ dependencies, parent POM, plugins và plugin dependencies trong local repository không?

```text
Developer / CI runner
       |
       v
Maven process + JDK
       |
       +--> settings.xml: proxy / mirror / credentials
       |
       v
Corporate proxy (nếu có)
       |
       +--> CONNECT tunnel cho HTTPS
       |
       v
Maven repository / repository manager
       |
       v
Local repository (~/.m2/repository)
       |
       v
Compile -> Test -> Package -> Verify
```

Maven dùng JDK để thực hiện TLS. Browser mở được URL không chứng minh JDK của Maven tin certificate đó. Build laptop có thể pass trong khi CI fail vì runner dùng JDK, truststore, proxy hoặc local cache khác.

Ví dụ trong bài dùng Java 17, Spring Boot 3.5.0 và Maven 3.9.x để giữ cấu hình nhất quán. Đây là bộ version đào tạo; dự án thật cần pin phiên bản tương thích với chính sách hỗ trợ của tổ chức.

## 2. Xác nhận Maven đang chạy bằng JDK nào

Trước khi sửa certificate hoặc proxy, kiểm tra Maven thực sự dùng JDK nào:

```bash
mvn -version
java -version
where java
where mvn
```

Trên Linux/macOS:

```bash
which java
which mvn
echo "$JAVA_HOME"
```

`mvn -version` cho biết Maven version, Java version, Java home và OS. `java` trong PATH có thể khác JDK mà Maven/IDE/CI runner sử dụng.

Kiểm tra:
- `JAVA_HOME` trỏ đến JDK dự kiến.
- `mvn -version` hiển thị Java major version phù hợp project.
- IDE có Maven runner JDK riêng.
- CI runner có thể chạy Maven trong container/toolchain khác.
- Maven Wrapper có thể tải Maven distribution riêng; xem `distributionUrl` trong `.mvn/wrapper/maven-wrapper.properties`.
- `MAVEN_OPTS` có thể thêm truststore hoặc JVM properties cho Maven.

**Không import certificate vào một JDK bất kỳ rồi giả định Maven sẽ dùng nó.** Lấy Java home từ chính `mvn -version`, sau đó xác định truststore tương ứng.

## 3. Phân biệt proxy, mirror và repository

### 3.1. Proxy là đường đi mạng

Proxy là máy trung gian nhận request từ Maven rồi chuyển tiếp tới repository. Trong mạng doanh nghiệp, proxy có thể:
- Kiểm soát domain được phép truy cập.
- Yêu cầu xác thực.
- Ghi log và giới hạn tốc độ.
- Dùng TLS inspection để kiểm tra HTTPS traffic.
- Chặn kết nối trực tiếp từ developer/CI runner ra Internet.

Maven cấu hình proxy trong `settings.xml`, thường ở `~/.m2/settings.xml`. Đây là cấu hình môi trường chạy Maven, không phải dependency configuration trong `pom.xml`.

### 3.2. Mirror là repository thay thế

Mirror là URL Maven dùng thay cho một remote repository. Ví dụ tổ chức có Nexus/Artifactory repository group làm proxy/cache cho Maven Central. Khi cấu hình `mirrorOf=*`, Maven có thể route hầu hết remote repositories qua endpoint nội bộ đó.

| Thành phần | Câu hỏi nó trả lời | Cấu hình |
| --- | --- | --- |
| Proxy | Maven kết nối ra ngoài bằng đường mạng nào? | `<proxies>` trong `settings.xml` |
| Mirror | Maven lấy dependency từ repository endpoint nào? | `<mirrors>` trong `settings.xml` |
| Repository | Artifact được lưu/phục vụ ở đâu? | `<repositories>` hoặc `pluginRepositories` |
| Server credentials | Dùng tài khoản nào để xác thực repository? | `<servers>` trong `settings.xml` |
| TLS truststore | JVM tin CA nào khi xác minh HTTPS? | JSSE truststore / JDK security configuration |

Một request có thể đi qua cả mirror lẫn proxy: Maven chọn mirror URL, rồi kết nối tới URL đó qua proxy nếu proxy đang active và host không nằm trong `nonProxyHosts`.

### 3.3. Luồng request

```text
pom.xml repository
      |
      v
Maven mirror selection
      |
      v
https://repo.corp.example/repository/maven-public/
      |
      v
Proxy selection (nếu host không bypass)
      |
      v
TLS + HTTP authentication
      |
      v
Artifact download
```

Nếu mirror trỏ sai URL, thêm proxy không sửa được lỗi. Nếu proxy đúng nhưng JVM không tin CA, đổi mirror cũng không sửa TLS handshake. Nếu artifact chưa từng được cache, bật offline mode cũng không thể tự tạo dependency đó.

## 4. Cấu hình Maven proxy trong settings.xml

### 4.1. Ví dụ settings.xml

Ví dụ sau minh họa proxy HTTP nội bộ và một Maven mirror. Thay hostname, port, repository path và secret references bằng giá trị do IT/DevOps cấp.

**`~/.m2/settings.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">

    <proxies>
        <proxy>
            <id>company-http-proxy</id>
            <active>true</active>
            <protocol>http</protocol>
            <host>proxy.corp.example</host>
            <port>8080</port>
            <username>${env.MAVEN_PROXY_USER}</username>
            <password>${env.MAVEN_PROXY_PASSWORD}</password>
            <nonProxyHosts>localhost|127.0.0.1|repo.corp.example|*.corp.example</nonProxyHosts>
        </proxy>
    </proxies>

    <mirrors>
        <mirror>
            <id>company-maven-mirror</id>
            <name>Company Maven repository group</name>
            <url>https://repo.corp.example/repository/maven-public/</url>
            <mirrorOf>*</mirrorOf>
        </mirror>
    </mirrors>

    <servers>
        <server>
            <id>company-maven-mirror</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Maven settings hỗ trợ interpolation từ environment variables, vì vậy có thể cấp `MAVEN_PROXY_USER`, `MAVEN_PROXY_PASSWORD`, `MAVEN_REPO_USER` và `MAVEN_REPO_TOKEN` từ secret manager/CI variables. Không commit token hoặc password vào Git. File settings có credentials cần được giới hạn quyền đọc theo tài khoản chạy build.

### 4.2. Vì sao protocol là http trong khi repository URL là https?

Trong cấu hình proxy, `<protocol>` mô tả giao thức kết nối **từ Maven tới proxy**. Nó không nhất thiết phải giống scheme của repository URL.

Nhiều corporate proxy nhận kết nối HTTP ở port 8080, sau đó hỗ trợ HTTPS tunnel bằng HTTP `CONNECT`. Vì vậy, cấu hình phổ biến có:
- Proxy endpoint: `http://proxy.corp.example:8080`
- Repository endpoint: `https://repo.maven.apache.org/maven2/`

Sau lệnh `CONNECT`, TLS handshake tới repository được thực hiện bên trong tunnel. Nếu proxy thực hiện TLS inspection, certificate mà JVM nhìn thấy có thể do corporate proxy phát hành; khi đó cần CA phù hợp trong truststore.

Nếu proxy endpoint thực sự dùng HTTPS, xác nhận protocol/port theo hướng dẫn của đội quản trị proxy và phiên bản Maven transport.

### 4.3. nonProxyHosts

`nonProxyHosts` liệt kê host mà Maven kết nối trực tiếp, không qua proxy. Maven dùng dấu `|` để phân tách pattern và hỗ trợ wildcard.

```xml
<nonProxyHosts>localhost|127.0.0.1|*.svc.cluster.local|*.corp.example</nonProxyHosts>
```

Sai `nonProxyHosts` có thể khiến:
- Repository nội bộ cần truy cập trực tiếp nhưng request lại bị gửi qua Internet proxy.
- Host nội bộ không phân giải được từ proxy.
- Proxy từ chối domain private.
- Request đi sai route dù DNS nội bộ hoạt động.

Không thêm `*` tùy tiện vì nó có thể khiến mọi host bypass proxy. Liệt kê chính xác domain nội bộ mà tổ chức yêu cầu.

### 4.4. Proxy không xác thực

Nếu proxy không yêu cầu username/password, bỏ hai phần tử đó:

```xml
<proxy>
    <id>company-http-proxy</id>
    <active>true</active>
    <protocol>http</protocol>
    <host>proxy.corp.example</host>
    <port>8080</port>
    <nonProxyHosts>localhost|127.0.0.1|*.corp.example</nonProxyHosts>
</proxy>
```

Một số proxy doanh nghiệp dùng SSO/NTLM/Kerberos hoặc agent hệ điều hành thay cho Basic authentication. Xác nhận cơ chế được hỗ trợ bởi proxy và Maven transport; không chuyển password sang URL hoặc bật tùy chọn xác thực không an toàn.

### 4.5. Kiểm tra mirror ID và server ID

Khi Maven dùng mirror, `<server><id>` cần khớp ID của repository/mirror mà Maven thực sự kết nối. Trong ví dụ, ID là `company-maven-mirror` ở cả `<mirror>` và `<server>`.

Nếu credentials chỉ khai báo cho `central` nhưng Maven đã route qua mirror có ID `company-maven-mirror`, Maven có thể không dùng credentials bạn dự kiến.

Nếu tổ chức dùng `mirrorOf=*`, xác nhận URL mirror là repository group được cấp quyền truy cập cả dependencies lẫn plugins. Một repository chỉ chứa release packages của team có thể không có plugin/parent POM cần cho build.

### 4.6. Dùng file settings riêng

```bash
mvn -s .mvn/company-settings.xml -B -ntp clean verify
```

Khi dùng `-s`, kiểm tra file đó có đủ proxy, mirror, credentials và profiles cần thiết. Đừng giả định nó tự lấy mọi cấu hình từ user settings khác. Maven có global settings và user settings; user settings có độ ưu tiên cao hơn khi hai file được merge.

## 5. Kiểm tra network trước khi thay đổi Maven

### 5.1. Kiểm tra DNS và TCP

Trên Windows PowerShell:

```powershell
Resolve-DnsName proxy.corp.example
Test-NetConnection proxy.corp.example -Port 8080
Resolve-DnsName repo.maven.apache.org
Test-NetConnection repo.maven.apache.org -Port 443
```

Trong mạng bắt buộc dùng proxy, direct connection tới repository có thể bị chặn có chủ đích. Khi đó, kiểm tra TCP tới proxy quan trọng hơn; không kết luận Internet hỏng chỉ vì direct connection thất bại.

Trên Linux:

```bash
getent hosts proxy.corp.example
nc -vz proxy.corp.example 8080
getent hosts repo.maven.apache.org
```

`nc` chỉ kiểm tra TCP tới host/port; nó không xác nhận proxy authentication, HTTP response hoặc TLS trust.

### 5.2. Kiểm tra HTTPS bằng curl

Nếu proxy hỗ trợ HTTP CONNECT:

```bash
curl -I -v \
  --proxy http://proxy.corp.example:8080 \
  https://repo.maven.apache.org/maven2/
```

Nếu proxy yêu cầu authentication, dùng cơ chế credentials được phê duyệt; tránh ghi password trực tiếp vào command line vì process list, shell history hoặc CI logs có thể lưu lại.

Trên Windows, gọi `curl.exe` để tránh nhầm alias PowerShell:

```powershell
curl.exe -I -v --proxy http://proxy.corp.example:8080 https://repo.maven.apache.org/maven2/
```

`curl` và Maven có thể dùng trust store khác nhau. Trên Windows, curl có thể dùng Windows certificate store trong khi Maven dùng truststore của JDK. Vì thế curl thành công chỉ chứng minh đường đi và trust của curl, chưa chứng minh Java TLS sẽ thành công.

### 5.3. Kiểm tra TLS chain

Nếu có OpenSSL, kiểm tra HTTPS qua HTTP proxy:

```bash
openssl s_client \
  -proxy proxy.corp.example:8080 \
  -connect repo.maven.apache.org:443 \
  -servername repo.maven.apache.org \
  -showcerts
```

Quan sát:
- Certificate subject/SAN có đúng hostname không.
- Issuer là public CA hay corporate inspection CA.
- Certificate còn hiệu lực hay đã hết hạn.
- Server có gửi intermediate certificates cần thiết không.
- OpenSSL báo verify return code nào.

Có thể xem certificate do server trả về trực tiếp bằng:

```bash
keytool -printcert -sslserver repo.maven.apache.org:443 -rfc
```

Lệnh `keytool -sslserver` kết nối trực tiếp, không thay thế bài kiểm tra qua proxy. Nếu mạng chỉ cho phép CONNECT qua proxy, dùng OpenSSL hoặc công cụ TLS được tổ chức cấp để kiểm tra đúng route.

## 6. Phân biệt lỗi proxy với lỗi repository

| HTTP/status hoặc exception | Ý nghĩa thường gặp | Kiểm tra tiếp |
| --- | --- | --- |
| `407 Proxy Authentication Required` | Proxy cần credentials hoặc credentials sai | Proxy username/password, auth mechanism, proxy ID |
| `401 Unauthorized` | Repository/server yêu cầu xác thực | `<servers>` ID khớp mirror/repository ID, token |
| `403 Forbidden` | Đã tới server nhưng policy không cho phép | Repository permissions, group membership, artifact policy |
| `404 Not Found` | Artifact/path không tồn tại tại endpoint đã chọn | Mirror URL, repository path, GAV/plugin coordinates |
| `429 Too Many Requests` | Rate limit | Repository manager throttling, CI concurrency |
| `502` / `503` / `504` | Proxy/gateway/upstream unavailable hoặc timeout | Proxy logs, repository manager health, remote status |
| `UnknownHostException` | DNS không phân giải được host | Host nào đang được resolve: proxy hay repository |
| `ConnectException: Connection refused` | Host có thể tới được nhưng port không nhận kết nối | Proxy host/port, service listener, firewall |
| `SocketTimeoutException` | Kết nối hoặc response quá thời gian | Route, proxy load, repository latency, firewall |
| `SSLHandshakeException` | TLS handshake thất bại | Certificate chain, hostname, truststore, protocol, mTLS |

**Đừng nhầm 407 với 401.** 407 là proxy authentication; 401 thường là repository/server authentication. Nếu Maven dùng mirror, kiểm tra mirror ID thực tế trong settings trước khi thay token.

Một thông báo `Could not transfer artifact` có thể bọc exception gốc. Dùng `-e` để xem stack trace và `-X` khi cần thêm chi tiết:

```bash
mvn -B -ntp -U -e validate
mvn -B -ntp -U -X validate
```

`-X` tạo log rất chi tiết. Trước khi gửi log ra ngoài, xóa credentials, token, authorization headers, private repository URLs, usernames và thông tin nội bộ. Không đưa toàn bộ `settings.xml` lên ticket công khai.

## 7. TLS certificate và truststore trong Java

### 7.1. Truststore và keystore khác nhau

- **Truststore:** chứa CA/certificate mà Java tin khi xác minh certificate của server.
- **Keystore:** chứa private key và certificate của chính client/server, thường dùng khi cần mutual TLS (mTLS).

Khi Maven truy cập `https://repository.example`, JVM kiểm tra certificate chain của repository bằng truststore. Khi repository yêu cầu client certificate, Maven có thể cần keystore chứa private key và client certificate tương ứng.

`PKIX path building failed` thường cho thấy JVM không dựng được certificate chain về trust anchor mà nó tin. Không giải quyết lỗi này bằng cách thêm client private key nếu vấn đề thực tế là thiếu trusted CA.

### 7.2. JVM chọn truststore nào?

Theo JSSE của JDK, nếu `javax.net.ssl.trustStore` được chỉ định, JVM sẽ dùng file đó. Nếu property trỏ tới file không tồn tại, JSSE có thể tạo trust manager với truststore rỗng. Nếu không chỉ định, JVM tìm `jssecacerts`, sau đó `cacerts` trong Java home.

Kiểm tra:
- `mvn -version` để biết Java home.
- Giá trị `javax.net.ssl.trustStore` trong JVM options.
- File truststore có tồn tại và có thể đọc không.
- Truststore type có đúng `JKS` hoặc `PKCS12` không.
- Certificate có phải CA được tổ chức phê duyệt không.
- Server có gửi đủ intermediate certificates không.

### 7.3. Kiểm tra JDK cacerts

Dùng `keytool` đi cùng JDK mà Maven sử dụng:

```bash
keytool -list -cacerts
keytool -list -v -cacerts -alias company-root-ca
```

Không giả định tất cả JDK cài trên máy dùng cùng một `cacerts`. IDE, Maven CLI, Maven Wrapper, CI container và runtime container có thể dùng Java home khác nhau.

### 7.4. Tạo truststore riêng và import corporate CA

Trong doanh nghiệp, HTTPS inspection có thể khiến proxy thay certificate public server bằng certificate do corporate CA ký. JDK cần tin corporate root CA đã được xác minh.

Quy trình an toàn:

1. Nhận file CA certificate từ nguồn nội bộ được xác thực (IT/security PKI).
2. Xác minh SHA-256 fingerprint qua kênh độc lập, đáng tin cậy.
3. Kiểm tra subject/issuer/validity của certificate.
4. Tạo truststore riêng cho Maven hoặc build runner.
5. Import CA vào truststore đó.
6. Chỉ định truststore cho JVM chạy Maven.
7. Chạy lại build và xác nhận lỗi TLS đã được giải quyết.

Kiểm tra file certificate trước khi import:

```bash
keytool -printcert -file corp-root-ca.cer
```

Tạo truststore PKCS12 và import:

```bash
keytool -importcert \
  -alias corp-proxy-root \
  -file corp-root-ca.cer \
  -keystore "$HOME/.m2/corp-truststore.p12" \
  -storetype PKCS12
```

Sau khi import, kiểm tra entry:

```bash
keytool -list -v \
  -keystore "$HOME/.m2/corp-truststore.p12" \
  -storetype PKCS12 \
  -alias corp-proxy-root
```

Đọc kỹ fingerprint trước khi xác nhận import. Không import certificate chỉ vì browser hiển thị nó; hãy xác minh certificate đến từ PKI/IT chính thức.

### 7.5. Cấu hình Maven dùng truststore riêng

Trên Linux/macOS:

```bash
export MAVEN_OPTS="-Djavax.net.ssl.trustStore=$HOME/.m2/corp-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12"
mvn -B -ntp -U clean verify
```

Trên Windows PowerShell:

```powershell
$env:MAVEN_OPTS = "-Djavax.net.ssl.trustStore=$env:USERPROFILE\.m2\corp-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12"
mvn -B -ntp -U clean verify
Remove-Item Env:MAVEN_OPTS
```

Nếu truststore yêu cầu password, cung cấp bằng secret mechanism phù hợp với CI/JVM process và giới hạn quyền đọc. Tránh ghi password vào shell history, source code hoặc log. Truststore chỉ chứa public CA certificates, nhưng file vẫn cần được quản lý để tránh thay đổi ngoài kiểm soát.

Có thể cấu hình truststore trong `MAVEN_OPTS` cho một lần chạy; đừng để truststore path cũ tồn tại âm thầm trong environment rồi ảnh hưởng build khác.

### 7.6. Vì sao không nên ghi đè cacerts toàn cục?

Import CA trực tiếp vào JDK `cacerts` có thể hoạt động, nhưng:
- Cần quyền ghi vào JDK installation.
- JDK upgrade có thể thay file truststore.
- Nhiều project dùng chung một JDK nên phạm vi ảnh hưởng rộng.
- Khó truy vết ai thêm CA và khi nào.
- CI runner ephemeral cần provisioning lại.

Truststore riêng thường dễ version, mount và quản lý theo môi trường hơn. Nếu tổ chức yêu cầu truststore hệ thống, hãy dùng quy trình quản lý certificate chuẩn của họ.

### 7.7. Certificate chain thiếu intermediate

Một server thường gửi leaf certificate và intermediate certificates cần thiết để chain về root CA. Root CA có thể đã được truststore tin cậy, nhưng nếu server không gửi intermediate, một số client có thể không dựng được chain.

Trong tình huống đó:
- Yêu cầu repository/proxy administrator cấu hình full certificate chain đúng.
- Kiểm tra output `openssl s_client -showcerts`.
- So sánh issuer/subject giữa các certificate.
- Xác định root CA đã được truststore tin hay chưa.

Đừng import tùy tiện từng leaf certificate của mọi host vào truststore như cách chữa mặc định. Sửa server chain hoặc cài đúng corporate root CA đã xác minh thường bền vững hơn.

## 8. Phân tích các lỗi TLS thường gặp

| Lỗi | Ý nghĩa | Hướng kiểm tra |
| --- | --- | --- |
| `PKIX path building failed` | Không dựng được trust chain về CA được tin | Truststore, corporate CA, missing intermediate |
| `unable to find valid certification path` | JVM không tìm được certificate path hợp lệ | JDK truststore đang dùng, CA root |
| `No subject alternative DNS name matching ...` | Hostname không khớp SAN của certificate | URL hostname, reverse proxy, certificate SAN |
| `CertificateExpiredException` | Certificate đã hết hạn hoặc chưa có hiệu lực | Certificate validity và system clock |
| `handshake_failure` | TLS negotiation hoặc authentication thất bại | Protocol/cipher compatibility, mTLS requirement |
| `protocol_version` | Hai bên không có TLS version chung | JDK policy, server TLS configuration |
| `certificate_required` | Server yêu cầu client certificate | Client keystore và mTLS configuration |
| `bad_certificate` | Peer từ chối certificate được gửi | Client cert chain, EKU, expiry, issuer |
| `Connection reset` trong handshake | Kết nối bị đóng giữa chừng | Proxy inspection, firewall, server logs |

### 8.1. PKIX path building failed

Nguyên nhân phổ biến:
- Corporate proxy ký lại certificate nhưng JDK chưa trust corporate CA.
- JDK cũ có root CA store chưa cập nhật.
- Maven dùng JDK khác với JDK mà bạn đã import certificate.
- Truststore custom path sai hoặc file không tồn tại.
- Server gửi certificate chain không đầy đủ.
- Một security property trỏ tới truststore rỗng.

Cách kiểm tra:
1. Chạy `mvn -version`.
2. Xác định Java home.
3. Kiểm tra `MAVEN_OPTS` và `javax.net.ssl.trustStore`.
4. Kiểm tra certificate chain qua đúng proxy route.
5. Xác minh corporate CA fingerprint.
6. Import CA đã xác minh vào truststore đúng.
7. Chạy lại dependency/plugin resolution.

### 8.2. Hostname mismatch

Nếu certificate có SAN cho `repo.company.example` nhưng Maven gọi `repo-alias.company.example`, Java có thể từ chối kết nối dù certificate được CA tin cậy.

Hãy:
- Dùng canonical hostname mà repository administrator cung cấp.
- Kiểm tra DNS alias/load balancer.
- Cấp certificate có SAN phù hợp.
- Tránh tắt hostname verification.

Truststore chỉ giải quyết trust chain; nó không biến certificate sai hostname thành hợp lệ.

### 8.3. Certificate expired hoặc clock sai

Certificate có khoảng thời gian `Not Before` và `Not After`. Máy runner sai ngày/giờ có thể đánh giá certificate là chưa có hiệu lực hoặc hết hạn.

Kiểm tra đồng hồ hệ điều hành/NTP, certificate leaf/intermediate, certificate proxy/load balancer/repository và system time của JVM. Không kéo dài ngày hệ thống để né expiry; sửa đồng bộ thời gian hoặc gia hạn certificate ở nơi cấp.

### 8.4. TLS protocol/cipher mismatch

Nếu server chỉ cho TLS version/cipher mà JDK không hỗ trợ hoặc security policy đã disable, handshake có thể thất bại. Kiểm tra JDK version, security policy, TLS versions server hỗ trợ, proxy CONNECT/TLS passthrough và JSSE handshake logs.

Không bật TLS 1.0/1.1 hoặc cipher yếu như giải pháp lâu dài. Cập nhật server/proxy hoặc JDK để có cấu hình TLS được hỗ trợ.

### 8.5. Mutual TLS (mTLS)

Một số repository nội bộ yêu cầu client certificate:
- Truststore xác minh certificate của server.
- Keystore chứa client private key và client certificate.
- Certificate phải còn hạn và được server trust.
- Client certificate cần đúng key usage/extended key usage theo policy.

Maven SSL configuration có thể dùng `javax.net.ssl.keyStore` và `javax.net.ssl.keyStoreType`. Không đưa private key vào repository source hoặc Docker image build context công khai.

## 9. Bật JSSE debug khi cần

Khi exception không nói rõ certificate nào bị từ chối, JSSE debug giúp xem trust manager, certificate chain và TLS handshake.

Linux/macOS:

```bash
MAVEN_OPTS="-Djavax.net.debug=ssl,handshake,trustmanager" \
  mvn -B -ntp -U validate
```

Windows PowerShell:

```powershell
$env:MAVEN_OPTS = "-Djavax.net.debug=ssl,handshake,trustmanager"
mvn -B -ntp -U validate
Remove-Item Env:MAVEN_OPTS
```

Tùy chọn debug có thể tạo log rất lớn. Dùng trong một lần tái hiện có kiểm soát, lưu log ở nơi bảo mật và redact trước khi chia sẻ.

Các dòng có ích:
- `trustStore is: ...`: JVM đang dùng truststore nào.
- `Reloaded ... trust certs`: số certificate đã nạp.
- Certificate subject/issuer: CA chain đang được nhìn thấy.
- `Found trusted certificate`: trust manager tìm được trust anchor.
- TLS protocol/cipher negotiation: hai bên chọn được protocol/cipher nào.

JSSE debug chỉ cho biết góc nhìn của JVM. Kết hợp proxy logs, repository logs và network checks để xác định thành phần nào đóng kết nối.

## 10. Maven offline mode hoạt động như thế nào?

### 10.1. Local repository là cache trên máy chạy Maven

Maven local repository mặc định là `~/.m2/repository`; trên Windows thường là `%USERPROFILE%\.m2\repository`.

Local repository lưu dependencies/plugins đã tải và artifact được cài local. Nó không tự đồng bộ giữa các developer hoặc CI runners. Khi Maven cần artifact chưa có trong local repository, Maven thường truy cập remote repository để tải. Offline mode ngăn Maven thực hiện truy cập remote đó.

### 10.2. Bật offline bằng CLI

```bash
mvn -o -B -ntp clean verify
```

`-o` là `--offline`. Đây là cách bật offline cho một lần chạy.

Có thể cấu hình cố định trong `settings.xml`:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <offline>true</offline>
</settings>
```

Khi mạng hoạt động trở lại, bỏ cấu hình offline hoặc đặt `false`; nếu không Maven vẫn từ chối truy cập remote repository.

### 10.3. Offline không tự tải hoặc tạo dependency còn thiếu

Một build offline chỉ thành công khi local repository có đủ:
- Parent POMs và imported BOMs.
- Dependencies theo đúng profiles/scopes.
- Maven plugins được gọi trong lifecycle.
- Plugin dependencies.
- Maven extensions trong `.mvn/extensions.xml`.
- Metadata/artifacts mà plugin/task cụ thể cần.
- Maven distribution nếu dùng Maven Wrapper và distribution chưa được tải.

Một project từng chạy `mvn package` có thể vẫn thiếu plugin dùng ở phase `verify`, integration test profile hoặc release profile. Offline `clean verify` có thể fail dù offline `compile` thành công.

### 10.4. Warm up local repository trước khi offline

Khi còn mạng và proxy/mirror đã cấu hình đúng, chạy:

```bash
mvn -B -ntp dependency:go-offline
```

Sau đó chạy thử build với đúng profile và goals:

```bash
mvn -B -ntp -Pprod clean verify
```

Cuối cùng kiểm tra offline:

```bash
mvn -o -B -ntp -Pprod clean verify
```

`dependency:go-offline` giúp tải project dependencies và plugins mà Maven Dependency Plugin có thể xác định. Nó không bảo đảm mọi plugin tùy biến, profile động, extension hoặc tác vụ build đều đã được cache. Bài kiểm tra quyết định vẫn là chạy chính xác build command trong offline mode trên môi trường sẽ sử dụng.

### 10.5. Profile phải giống nhau

Nếu online build dùng profile `prod` nhưng bước warm-up không bật profile, dependencies riêng của profile đó có thể chưa được cache.

```bash
mvn -B -ntp -Pprod dependency:go-offline
mvn -B -ntp -Pprod clean verify
mvn -o -B -ntp -Pprod clean verify
```

Kiểm tra profile thực sự active bằng `mvn help:active-profiles`. Nếu có profile theo OS/JDK/property, bảo đảm môi trường warm-up và offline build tương thích.

### 10.6. Maven Wrapper cũng cần distribution

Maven Wrapper có thể tải Maven distribution trước khi Maven chạy. Vì thế, `settings.xml` của Maven không thể sửa lỗi tải wrapper distribution nếu Maven process chưa khởi động.

Kiểm tra `.mvn/wrapper/maven-wrapper.properties`, xem `distributionUrl` và bảo đảm distribution đã có sẵn hoặc URL wrapper có thể truy cập qua network/proxy phù hợp. Build offline cần cache/provision cả Maven distribution chứ không chỉ `~/.m2/repository`.

## 11. Chẩn đoán lỗi offline và local repository

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Cannot access ... in offline mode` | Artifact chưa có trong local repository | Warm up khi online hoặc dùng internal repository |
| `Plugin ... could not be resolved` | Plugin hoặc plugin dependency chưa cache | Chạy plugin/goal cần thiết khi online |
| `Non-resolvable parent POM` khi offline | Parent POM chưa cache hoặc repository ID/path khác | Resolve parent online qua đúng mirror trước |
| Build `compile` pass nhưng `verify` fail | Plugin ở phase sau chưa cache | Warm up lifecycle `verify` và profiles |
| Máy developer pass, CI offline fail | Local repository hai môi trường khác nhau | Seed cache CI hoặc dùng internal repository |
| `mvn -o` vẫn chạy task cần remote data | Plugin tự thực hiện network request | Xem plugin docs/config; chuẩn bị dữ liệu local hoặc bỏ task khỏi offline profile |
| Snapshot không cập nhật | Offline không thể kiểm tra remote metadata mới | Chuyển online để resolve snapshot theo policy |
| Artifact tải dở/corrupt | Cache có file không hoàn chỉnh hoặc checksum mismatch | Online, xóa đúng artifact version directory rồi tải lại |
| `.lastUpdated` khiến artifact chưa resolve lại | Maven ghi nhận lần tải thất bại trước | Online chạy `-U`, kiểm tra repository và metadata |
| Wrapper không chạy khi offline | Maven distribution chưa được cache | Provision distribution trước khi ngắt mạng |

### 11.1. Không xóa toàn bộ .m2 như bước đầu tiên

Xóa toàn bộ local repository khiến Maven phải tải lại toàn bộ dependencies/plugins. Nó có thể làm vấn đề tệ hơn khi đang offline, proxy/TLS chưa sửa, repository rate-limit hoặc CI cache lớn.

Nếu xác định một artifact version bị hỏng:
1. Ghi nhận GAV/plugin coordinates và path cụ thể.
2. Đảm bảo kết nối repository đã hoạt động.
3. Xóa đúng thư mục version bị lỗi trong local repository.
4. Chạy lại với `-U` nếu cần cập nhật metadata.
5. Kiểm tra checksum và artifact sau khi tải.

Không xóa cache khác nếu chưa có bằng chứng liên quan.

### 11.2. Kiểm tra local repository path

Có thể custom path bằng `localRepository` trong `settings.xml`. Nếu Maven CLI, IDE và CI dùng settings khác nhau, chúng có thể đọc những cache khác nhau.

Kiểm tra `localRepository` path, `settings.xml` thực tế được load, Maven user home, container volume mount và permission của thư mục cache. Không copy nguyên `.m2` giữa các máy một cách tùy tiện nếu cache có lock/partial files hoặc quyền sở hữu không phù hợp.

## 12. Proxy và TLS khi build trong Docker

Maven chạy trên host và Maven chạy trong Docker builder stage là hai môi trường khác nhau.

### 12.1. Docker build proxy

Docker hỗ trợ proxy build arguments như `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` và `ALL_PROXY`. Proxy có thể được cấp qua Docker client config hoặc command line:

```bash
docker build \
  --build-arg HTTP_PROXY=http://proxy.corp.example:8080 \
  --build-arg HTTPS_PROXY=http://proxy.corp.example:8080 \
  --build-arg NO_PROXY=localhost,127.0.0.1,.corp.example \
  .
```

Docker client config có thể chứa proxy settings tại `~/.docker/config.json`:

```json
{
  "proxies": {
    "default": {
      "httpProxy": "http://proxy.corp.example:8080",
      "httpsProxy": "http://proxy.corp.example:8080",
      "noProxy": "localhost,127.0.0.1,.corp.example"
    }
  }
}
```

Docker CLI có thể tự đưa proxy build args vào build. Những cài đặt này dành cho build/container process; chúng không nhất thiết cấu hình proxy cho Docker daemon hoặc Docker Desktop. Nếu `FROM` image không pull được, kiểm tra proxy của Docker daemon/BuildKit/Docker Desktop theo đúng môi trường.

### 12.2. Không lưu proxy trong Dockerfile bằng ENV

Không viết:

```dockerfile
ENV HTTPS_PROXY=http://proxy.corp.example:8080
```

Cấu hình proxy bằng `ENV` có thể đi vào image configuration/layers và bị lộ trong image metadata hoặc runtime container. Dùng proxy build args hoặc Docker client config theo tài liệu chính thức; không đưa username/password vào image.

### 12.3. Maven trong multi-stage Docker build

Ví dụ Dockerfile build Spring Boot app:

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN mvn -B -ntp -DskipTests package

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app
COPY --from=build /workspace/target/release-demo-0.1.0.jar /app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Ở đây Maven chạy trong builder image. Nếu Maven cần corporate CA:
- Builder JDK cần truststore có corporate root CA đã xác minh.
- Builder network cần proxy/mirror đúng.
- `settings.xml` có thể được mount hoặc cung cấp trong build stage bằng secret mount.
- Không copy proxy password, Maven token hoặc private key vào final image.
- Nếu ứng dụng trong final container cần gọi HTTPS nội bộ, runtime JRE của final stage cũng cần truststore tương ứng.

**Builder truststore và runtime truststore là hai môi trường.** Build tải dependency thành công không có nghĩa ứng dụng sau khi chạy container sẽ trust cùng CA.

### 12.4. Dùng BuildKit secret cho Maven settings

Nếu build cần Maven settings chứa credentials, tránh `COPY settings.xml` có password vào image layer. Có thể dùng BuildKit secret mount:

```dockerfile
# syntax=docker/dockerfile:1
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN --mount=type=secret,id=maven_settings,target=/root/.m2/settings.xml \
    mvn -s /root/.m2/settings.xml -B -ntp clean verify

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app
COPY --from=build /workspace/target/release-demo-0.1.0.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Build:

```bash
docker build \
  --secret id=maven_settings,src="$HOME/.m2/settings.xml" \
  -t release-demo:local .
```

BuildKit secret mount cung cấp file cho đúng RUN step và không commit file đó vào image layer theo cách `COPY` thông thường. Tuy nhiên, kiểm tra build logs và scripts để không in secret ra output. Không dùng credentials developer cá nhân trong CI production; cấp token tối thiểu từ CI secret store.

## 13. Ví dụ project Spring Boot Java 17 để tái hiện

Ta dùng project nhỏ để kiểm tra Maven dependency resolution và build lifecycle. Project này không cần cấu hình proxy trong `pom.xml`; proxy/mirror/truststore được quản lý ở môi trường Maven.

### 13.1. Cấu trúc project

```text
release-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/release/
                └── ReleaseDemoApplication.java
```

### 13.2. pom.xml hoàn chỉnh

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
    <artifactId>release-demo</artifactId>
    <version>0.1.0</version>
    <name>release-demo</name>
    <packaging>jar</packaging>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
```

### 13.3. Java application chạy được

**`src/main/java/com/example/release/ReleaseDemoApplication.java`:**

```java
package com.example.release;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ReleaseDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReleaseDemoApplication.class, args);
    }

    @GetMapping("/ready")
    public String ready() {
        return "ready";
    }

    @GetMapping("/version")
    public String version() {
        return "release-demo:0.1.0";
    }
}
```

### 13.4. Build qua proxy/mirror

Khi `settings.xml` đã được cấu hình đúng và JDK truststore đã tin CA cần thiết:

```bash
mvn -B -ntp -U clean verify
```

Maven tải parent POM, Spring Boot dependencies và plugins, sau đó compile/test/package. Nếu có lỗi, phân tích exception gốc trước khi thay đổi project.

### 13.5. Chạy ứng dụng sau build

```bash
java -jar target/release-demo-0.1.0.jar
```

Terminal khác:

```bash
curl -fsS http://localhost:8080/ready
curl -fsS http://localhost:8080/version
```

Response body lần lượt:

```text
ready
release-demo:0.1.0
```

Các lệnh curl chỉ kiểm tra ứng dụng local. Chúng không chứng minh Maven proxy/TLS đang hoạt động; việc đó đã được kiểm tra trong bước Maven dependency resolution.

### 13.6. Chạy build offline

Sau khi build online thành công và cache đã được warm up:

```bash
mvn -o -B -ntp clean verify
```

Nếu lệnh fail vì thiếu plugin/dependency, ghi nhận chính xác tọa độ artifact được báo thiếu, chuyển online để tải qua mirror đã cấu hình, rồi chạy lại offline. Không đổi version hoặc xóa toàn bộ local repository để che lỗi cache.

## 14. Chương trình Java 17 nhỏ để kiểm tra HTTPS từ JVM

Khi nghi ngờ lỗi TLS xảy ra trong ứng dụng runtime thay vì Maven, có thể dùng Java 17 `HttpClient` để kiểm tra cùng endpoint từ chính JDK đang chạy.

**`HttpsProbe.java`:**

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class HttpsProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java HttpsProbe <https-url>");
            System.exit(2);
        }

        URI uri = URI.create(args[0]);
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(20))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request,
                HttpResponse.BodyHandlers.discarding()
        );

        System.out.println("HTTP status: " + response.statusCode());
    }
}
```

Compile và chạy:

```bash
javac HttpsProbe.java
java HttpsProbe https://repo.maven.apache.org/maven2/
```

Nếu JVM cần HTTP proxy cho HTTPS target:

```bash
java \
  -Dhttps.proxyHost=proxy.corp.example \
  -Dhttps.proxyPort=8080 \
  HttpsProbe https://repo.maven.apache.org/maven2/
```

Đây là cấu hình Java networking system properties cho chương trình mẫu; nó không thay thế Maven `<proxies>` trong `settings.xml`. Ứng dụng dùng custom HTTP client, custom `ProxySelector` hoặc proxy authentication riêng có thể cần cấu hình khác. Nếu JVM báo `SSLHandshakeException`, kiểm tra truststore của đúng JDK đang chạy chương trình.

## 15. Quy trình chẩn đoán từ nhanh đến sâu

1. **Ghi lại lỗi gốc:** lấy exception sâu nhất, URL, artifact coordinates và phase Maven thất bại.
2. **Xác nhận toolchain:** `mvn -version`, Maven Wrapper distribution, Java home và `MAVEN_OPTS`.
3. **Kiểm tra network:** DNS và TCP tới proxy; chỉ kiểm tra direct repository nếu policy cho phép.
4. **Kiểm tra proxy:** host/port/protocol, active flag, credentials và `nonProxyHosts`.
5. **Kiểm tra mirror:** URL mirror, `mirrorOf`, repository group và server ID.
6. **Kiểm tra HTTP status:** phân biệt 407, 401, 403, 404, 429 và 5xx.
7. **Kiểm tra TLS:** certificate chain, SAN, expiry, JDK truststore và corporate CA.
8. **Kiểm tra mTLS:** chỉ khi server yêu cầu client certificate; xác nhận client keystore.
9. **Kiểm tra Maven cache:** artifact đã có chưa, `.lastUpdated`, plugin dependencies và profiles.
10. **Thử offline:** chỉ sau khi warm up đúng build command và Maven Wrapper distribution.
11. **Kiểm tra Docker riêng:** Docker daemon/BuildKit proxy, builder JDK truststore và final runtime JRE truststore.
12. **Lưu evidence:** settings IDs đã redacted, Maven/JDK versions, exception root cause, HTTP status và kết quả network/TLS.

### 15.1. Cây quyết định

```text
Maven download/build thất bại
          |
          v
   Có DNS/TCP tới proxy?
      /          \
    Không         Có
     |             |
 Sửa DNS/route      v
/host/port     HTTP request có đi qua proxy?
                  /          \
                Không         Có
                 |             |
          Kiểm proxy config    v
                       HTTP status là gì?
                       /      |       \
                    407     401/403   5xx
                     |        |        |
                Proxy auth  Repo auth  Proxy/repo
                                      health/policy
                       |
                       v
                 TLS handshake pass?
                    /       \
                  Không      Có
                   |          |
             Truststore/chain  v
             SAN/expiry/mTLS   Artifact có trong
                               local cache?
                                /       \
                              Không      Có
                               |          |
                         Warm up online  Kiểm plugin/
                         đúng profile    project config
                               |
                               v
                         Chạy lại -o
```

## 16. Lỗi thường gặp trong môi trường doanh nghiệp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Browser mở Maven Central, Maven fail PKIX | Browser và JDK dùng truststore khác nhau | Kiểm tra Maven Java home và CA trong truststore |
| Curl pass nhưng Maven 407 | Curl dùng proxy credentials từ environment/config, Maven chưa có | Cấu hình proxy trong Maven settings |
| Maven 407 dù username đúng | Proxy auth scheme không được hỗ trợ hoặc credential scope sai | Xác nhận auth mechanism với proxy admin |
| Maven 401 khi mirror nội bộ | Server ID không khớp mirror ID hoặc token sai | Kiểm tra `<servers>` ID và token scope |
| Maven 403 | User đăng nhập được nhưng không có quyền artifact/group | Kiểm tra repository role/policy |
| `PKIX path building failed` chỉ khi bật VPN | VPN/proxy thay đổi TLS chain hoặc route | Kiểm tra certificate issuer và proxy path khi VPN bật |
| `PKIX path building failed` sau JDK upgrade | Truststore mới khác hoặc corporate CA chưa được provisioning | Import CA đã xác minh vào truststore JDK mới |
| Maven CLI pass nhưng IDE fail | IDE dùng Maven/JDK/settings riêng | Đồng bộ runner JDK và user settings trong IDE |
| Laptop pass, CI fail | CI container thiếu proxy/CA/cache | Provision proxy, CA, settings và warm cache cho runner |
| Maven pass, Docker build fail | BuildKit/daemon route hoặc builder image khác | Kiểm tra Docker proxy và builder JDK |
| Docker build pass, ứng dụng container fail HTTPS | Runtime JRE không trust CA nội bộ | Cài CA vào final runtime image/truststore |
| Offline build thiếu plugin | Plugin chưa cache | Warm up đúng lifecycle online |
| Wrapper không tải Maven | Wrapper distribution URL không truy cập được | Cache/provision Maven distribution riêng |
| Snapshot không cập nhật | Offline hoặc metadata update policy | Chuyển online và kiểm tra snapshot metadata |
| Lỗi checksum | Download bị cắt, proxy/repo corruption hoặc artifact không nhất quán | Xác minh repository/checksum; tải lại đúng artifact |

## 17. Bảo mật khi sửa proxy và TLS

Các giải pháp sau có thể làm một lệnh build chạy qua, nhưng làm giảm khả năng xác thực server và tạo rủi ro supply-chain:

- Bật chế độ SSL insecure hoặc bỏ hostname verification.
- Dùng trust-all `TrustManager`.
- Tắt TLS certificate validation trong curl/Java/Maven.
- Import certificate không rõ nguồn gốc.
- Copy private key/client keystore vào Git hoặc Docker image.
- Ghi proxy password/repository token vào command line hoặc log.
- Dùng một admin token cho tất cả developer/CI jobs.
- Tắt checksum policy để bỏ qua artifact integrity errors.
- Chạy build release với cache không rõ nguồn gốc.

**Không dùng bypass TLS như cách sửa production.** Nếu cần phân biệt lỗi truststore với lỗi proxy trong thử nghiệm có kiểm soát, dùng môi trường cô lập và làm theo security team's approval; sau thử nghiệm phải quay về certificate validation bình thường.

Nguyên tắc vận hành:
1. Tin đúng root CA đã xác minh, không tin mọi certificate.
2. Sửa hostname/certificate chain ở server nếu cấu hình sai.
3. Dùng token tối thiểu và tách proxy credentials khỏi repository credentials.
4. Dùng CI secret store hoặc file settings được bảo vệ.
5. Không copy credentials vào final image.
6. Pin JDK/Maven/toolchain và ghi lại versions.
7. Giữ checksum verification và artifact repository policy.
8. Theo dõi thời hạn certificate và quy trình rotation.
9. Lưu log chẩn đoán có redaction.
10. Kiểm thử offline cache trên đúng profiles/goals trước khi triển khai môi trường air-gapped.

## 18. Checklist vận hành

### Proxy và repository

- [ ] Đã xác nhận đúng Maven/JDK bằng `mvn -version`.
- [ ] Đúng `settings.xml` đang được sử dụng.
- [ ] Proxy host/port/protocol do tổ chức cấp.
- [ ] `nonProxyHosts` chứa đúng internal domains.
- [ ] Mirror URL là repository group có dependencies và plugins cần thiết.
- [ ] `mirrorOf` không route nhầm repository riêng.
- [ ] Server ID khớp mirror/repository ID.
- [ ] Proxy credentials và repository token được quản lý riêng.
- [ ] HTTP status đã được phân loại đúng bên từ chối request.

### TLS và certificate

- [ ] Đã xem certificate chain qua đúng network route.
- [ ] Đã xác minh corporate CA fingerprint qua kênh đáng tin cậy.
- [ ] Truststore thuộc đúng JDK mà Maven dùng.
- [ ] Custom truststore path/type tồn tại và đọc được.
- [ ] Hostname khớp SAN.
- [ ] Certificate còn hạn và system clock chính xác.
- [ ] Server gửi đủ intermediate chain.
- [ ] mTLS keystore chỉ cấu hình khi server thực sự yêu cầu.
- [ ] Không tắt certificate/hostname validation.

### Offline và Docker

- [ ] Đã warm up dependencies, plugins và profiles khi online.
- [ ] Maven Wrapper distribution đã được cache/provision.
- [ ] Offline test chạy đúng lifecycle/profile cần thiết.
- [ ] Local repository path và permissions đã rõ.
- [ ] Không xóa toàn bộ `.m2` nếu chưa xác định cache corruption.
- [ ] Docker daemon/BuildKit có proxy phù hợp.
- [ ] Builder JDK truststore có CA cần thiết.
- [ ] Final runtime JRE truststore có CA cần thiết nếu app gọi HTTPS nội bộ.
- [ ] Không đưa proxy credentials hoặc Maven token vào image.

## 19. Tài liệu chính thức

- Apache Maven – [Settings Reference](https://maven.apache.org/settings.html): user/global settings, proxy, mirrors, servers và profiles.
- Apache Maven – [Configuring a Proxy](https://maven.apache.org/guides/mini/guide-proxies.html): proxy fields, authentication và `nonProxyHosts`.
- Apache Maven – [Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories): local/remote repository, internal repository và offline mode.
- Apache Maven – [Remote Repository Access through Authenticated HTTPS](https://maven.apache.org/guides/mini/guide-repository-ssl.html): truststore, keystore và JSSE system properties.
- Apache Maven – [Maven Settings Reference 3.9](https://maven.apache.org/ref/3.9.0/maven-settings/settings.html): cấu trúc `settings.xml` và proxy fields.
- Oracle Java – [JSSE Reference Guide](https://docs.oracle.com/en/java/javase/24/security/java-secure-socket-extension-jsse-reference-guide.html): TLS, truststore selection, JSSE debug và certificate validation.
- Docker – [Use a Proxy Server with the Docker CLI](https://docs.docker.com/engine/cli/proxy/): Docker client proxy configuration, build args và bảo mật proxy values.
- Docker – [Build Variables](https://docs.docker.com/build/building/variables/): predefined proxy/build arguments và BuildKit behavior.
- Spring Boot 3.5 – [Maven Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/): Maven build integration cho Spring Boot.
- Spring Boot 3.5 – [System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java/Maven compatibility của Spring Boot 3.5.

**Ghi nhớ:** Khi Maven không tải được dependency, hãy xác định đúng lớp lỗi trước: network, proxy/mirror, HTTP authentication, TLS trust hoặc local cache. Proxy được cấu hình trong `settings.xml`; TLS trust được quyết định bởi JDK truststore; offline mode chỉ dùng được khi tất cả artifacts/plugins cần thiết đã có trong local repository. Với Docker, builder và runtime là hai môi trường riêng, nên phải kiểm tra proxy và CA ở đúng stage đang thực hiện kết nối.