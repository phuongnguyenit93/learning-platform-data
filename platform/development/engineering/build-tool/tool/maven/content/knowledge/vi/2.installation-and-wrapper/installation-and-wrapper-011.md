# Xử lý lỗi mạng, proxy hoặc JDK khi Maven Wrapper khởi động

Maven Wrapper (`mvnw` trên Linux/macOS, `mvnw.cmd` trên Windows) giúp dự án chạy bằng **phiên bản Maven được ghim cho dự án**, kể cả khi người dùng chưa cài Maven toàn cục. Lần đầu chạy, Wrapper có thể cần tải công cụ bootstrap và bản phân phối Maven qua mạng, giải nén vào cache, rồi mới khởi động Maven bằng Java. Vì vậy, nhiều lỗi “Wrapper không chạy” xảy ra **trước khi Maven xử lý `pom.xml` và phụ thuộc của dự án**.

Bài này hướng dẫn tách đúng giai đoạn lỗi, kiểm tra kết nối mạng/proxy/TLS, chọn JDK tương thích, xử lý cache và xác minh kết quả trên Windows, Linux, macOS hoặc môi trường CI. Các lệnh dưới đây thực hiện ở **thư mục gốc dự án**, nơi có `mvnw` và `.mvn/wrapper/maven-wrapper.properties`.

## 1. Wrapper khởi động theo những giai đoạn nào?

1. **Chạy script:** shell hoặc Windows thực thi `./mvnw` hay `.\mvnw.cmd`. Script phải tồn tại, có quyền chạy và tìm được công cụ tải file/Java cần dùng.
2. **Bootstrap Wrapper:** tùy kiểu Wrapper, các script dùng `curl`, `wget`, PowerShell hoặc Java; có kiểu cần tải `maven-wrapper.jar`, có kiểu không dùng JAR này.
3. **Tải bản phân phối Maven:** Wrapper đọc `distributionUrl` trong `.mvn/wrapper/maven-wrapper.properties`, tìm bản Maven được ghim trong cache và tải ZIP nếu chưa có.
4. **Giải nén và chạy Maven:** Maven distribution được giải nén (thông thường vào `~/.m2/wrapper/dists`) và Maven khởi chạy bằng Java của môi trường.
5. **Maven thực hiện goal:** Maven mới giải quyết plugin/dependency từ repository theo POM, settings, mirror, proxy... rồi thực thi build.

Điểm quan trọng: **proxy dùng để tải ZIP của Maven có thể khác proxy mà Maven dùng để tải dependency sau khi đã chạy**. Không nên bắt đầu bằng cách sửa `settings.xml` nếu lỗi xảy ra ngay lúc script tải Maven.

| Dấu hiệu trong log | Giai đoạn cần kiểm tra đầu tiên | Nguyên nhân điển hình |
| --- | --- | --- |
| `./mvnw: Permission denied` | Script | Thiếu quyền executable trên Unix |
| `curl: (6) Could not resolve host` | Tải file | DNS, hostname sai, proxy |
| `Connection timed out` | Tải file | Firewall, proxy, đường truyền hoặc đích không phản hồi |
| HTTP `407 Proxy Authentication Required` | Tải qua proxy | Proxy cần xác thực |
| HTTP `401`, `403` hoặc `404` | URL/tải file | Thiếu quyền hoặc đường dẫn phân phối không đúng |
| `PKIX path building failed` / `SSLHandshakeException` | HTTPS bằng Java | JDK không tin chứng chỉ hoặc lỗi thương lượng TLS |
| `curl: (60) SSL certificate problem` | HTTPS bằng curl | Kho CA của curl/hệ điều hành không tin chứng chỉ |
| `JAVA_HOME is not defined correctly` | Java/Maven runtime | Biến trỏ sai thư mục JDK |
| `UnsupportedClassVersionError` | Nạp class Java | Java runtime quá cũ so với bytecode đang chạy |
| `ZipException`/giải nén lỗi | Maven distribution/cache | ZIP tải dở, hỏng hoặc không đủ dung lượng |

## 2. Xác định bản Maven và loại Wrapper của dự án

Cấu trúc tối thiểu thường có dạng:

```text
project/
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
└── pom.xml
```

Ví dụ cấu hình:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
```

Đây là URL ví dụ đến bản Maven đã xác định, **không có nghĩa mọi dự án phải dùng 3.9.9**. Cần giữ bản Maven mà dự án yêu cầu; nếu nguồn tải là repository nội bộ, dùng URL đã được tổ chức phê duyệt. `distributionUrl` trỏ đến **Maven distribution ZIP**, không phải một dependency hay plugin đơn lẻ.

Kiểm tra file và nội dung trên Linux/macOS:

```bash
pwd
ls -la mvnw .mvn/wrapper
cat .mvn/wrapper/maven-wrapper.properties
```

Trên Windows PowerShell:

```powershell
Get-Location
Get-Item .\mvnw.cmd
Get-ChildItem .mvn/wrapper
Get-Content .mvn/wrapper/maven-wrapper.properties
```

Các loại Wrapper được Apache Maven hỗ trợ:

- **`only-script`:** script tải Maven trực tiếp qua `curl`/`wget` (Unix) hoặc PowerShell (Windows), không dùng `maven-wrapper.jar`. Đây là mặc định ở các phiên bản Wrapper hiện đại.
- **`script`:** script có thể tải và chạy `maven-wrapper.jar` trước khi lấy Maven.
- **`bin`:** JAR bootstrap đã có sẵn tại `.mvn/wrapper/maven-wrapper.jar`.
- **`source`:** có thể biên dịch `MavenWrapperDownloader.java` để tải JAR khi cần, đòi hỏi công cụ `javac` phù hợp.

**Không thấy `maven-wrapper.jar` chưa chắc là lỗi.** Với `only-script`, việc không có JAR là chủ ý. Hãy đọc script và xác định loại/phiên bản Wrapper thay vì tự tải JAR từ nguồn không rõ. Nếu dự án dùng `script` hay `bin` mà thông báo `Could not find or load main class org.apache.maven.wrapper.MavenWrapperMain`, lúc đó mới kiểm tra JAR và đường dẫn classpath tương ứng.

## 3. Thu thập thông tin ban đầu mà không thay đổi cấu hình

### Linux/macOS

```bash
java -version
javac -version
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
command -v java
command -v curl
command -v wget
MVNW_VERBOSE=true ./mvnw --version
```

`java -version` thường in ra stderr; riêng điều này không có nghĩa lệnh bị lỗi. Một trong `curl` hoặc `wget` không có sẵn vẫn có thể đủ đối với `only-script`. `MVNW_VERBOSE=true` yêu cầu Wrapper in thêm thông tin chẩn đoán nếu bản Wrapper hỗ trợ.

Nếu gặp `Permission denied` và file thuộc repository đã tin cậy:

```bash
chmod +x mvnw
./mvnw --version
```

Nên bảo toàn executable bit trong Git để máy Unix/CI chạy thống nhất. Nếu báo `/bin/sh^M: bad interpreter` hoặc `$'\r': command not found`, kiểm tra script có bị đổi line ending sang CRLF; trên Unix cần LF.

### Windows PowerShell

```powershell
java -version
javac -version
$env:JAVA_HOME
Get-Command java
$env:MVNW_VERBOSE = "true"
.\mvnw.cmd --version
```

PowerShell dùng `.\mvnw.cmd` cho script hiện tại. Nếu `java -version` đúng nhưng Maven Wrapper vẫn dùng Java khác, cần kiểm tra `JAVA_HOME` vì script có thể ưu tiên JDK từ biến này. Đừng chỉ dùng `mvn --version`: lệnh đó gọi Maven cài toàn cục; phiên bản và kết quả có thể khác `mvnw` của dự án.

Khi chia sẻ log, che URL có token, proxy credentials và đường dẫn bí mật. Chỉ cần giữ phần mã lỗi, tên giai đoạn, HTTP status và bản Java/Maven phục vụ chẩn đoán.

## 4. Xử lý DNS, timeout, HTTP và URL phân phối sai

Trước khi sửa một file cấu hình, đối chiếu `distributionUrl` thực tế:

1. Domain/hostname có đúng chính tả, phân giải được trong mạng đang dùng không?
2. URL có dẫn đến file ZIP còn tồn tại và đúng phiên bản của dự án không?
3. Máy/CI có được phép kết nối HTTPS ra ngoài, hay bắt buộc đi qua proxy hoặc mirror nội bộ?
4. Có HTTP redirect sang domain khác bị firewall chặn không?
5. Có lỗi tải dở, dung lượng đĩa hoặc quyền ghi cache không?

Có thể kiểm tra một URL Maven công khai mẫu bằng công cụ gần với downloader thật:

```bash
# Linux/macOS: -L theo redirect; -I gửi HEAD
curl -I -L --connect-timeout 10 "https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip"
```

```powershell
# PowerShell: gọi curl.exe để tránh nhầm alias
curl.exe -I -L --connect-timeout 10 "https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip"
```

Thay URL mẫu bằng `distributionUrl` thật khi kiểm tra dự án. Không phải máy chủ nào cũng hỗ trợ HTTP `HEAD`: nếu nhận 405, cần kiểm tra bằng yêu cầu GET hoặc công cụ được tổ chức phê duyệt. Kết quả curl thành công cũng **chưa chứng minh Java/PowerShell downloader có cùng proxy/truststore**.

Hướng xử lý theo từng mã lỗi:

- **DNS không phân giải được:** sửa hostname/URL nếu sai, kiểm tra VPN, DNS hoặc cấu hình proxy. Không liên quan phiên bản dependency trong `pom.xml`.
- **Timeout/connection refused:** kiểm tra firewall, route, proxy host/port và chính sách outbound của CI; nếu bắt buộc đi qua proxy thì kết nối trực tiếp sẽ thất bại.
- **407:** proxy cần xác thực; xử lý bằng phương thức cấp quyền chính thức thay vì đặt mật khẩu thẳng trên command line.
- **401/403:** máy chủ đích từ chối yêu cầu; kiểm tra tài khoản, quyền truy cập, token và path; tránh retry liên tục.
- **404:** distribution không có tại URL; xác minh phiên bản, tên file ZIP và repository.
- **Lỗi giải nén:** kiểm tra quyền ghi, dung lượng và checksum; xem mục cache bên dưới.

Không nên đổi HTTPS thành HTTP, tắt xác minh chứng chỉ hoặc tải file từ website không đáng tin để “chữa nhanh” lỗi mạng.

## 5. Cấu hình proxy đúng với công cụ tải

### 5.1. Wrapper dạng script dùng curl/wget

Trong nhiều môi trường, `curl` hoặc `wget` nhận proxy từ biến môi trường. Ví dụ với địa chỉ proxy **minh họa**:

```bash
# Linux/macOS, trong shell hiện tại
export HTTPS_PROXY=http://proxy.example.org:8080
export HTTP_PROXY=http://proxy.example.org:8080
MVNW_VERBOSE=true ./mvnw --version
```

Windows PowerShell:

```powershell
$env:HTTPS_PROXY = "http://proxy.example.org:8080"
$env:HTTP_PROXY = "http://proxy.example.org:8080"
$env:MVNW_VERBOSE = "true"
.\mvnw.cmd --version
```

Đây là ví dụ khi proxy đã được quản trị xác nhận. **Biến proxy không được mọi downloader dùng như nhau:** `curl`, `wget`, PowerShell và Java có cơ chế cấu hình khác nhau; trên Windows, script PowerShell có thể chịu ảnh hưởng cấu hình proxy hệ thống. Hãy xác nhận công cụ nào thực sự thực hiện download rồi thử lại ngay bằng công cụ đó.

Trong mạng doanh nghiệp, có thể dùng **Maven repository manager** nội bộ và đặt `distributionUrl` đến file Maven ZIP tương ứng. Một số phiên bản Maven Wrapper còn hỗ trợ `MVNW_REPOURL` để điều hướng truy cập đến repository manager; cần đối chiếu hướng dẫn và behavior đúng phiên bản Wrapper. Không giả định mirror khai báo trong Maven `settings.xml` luôn được trình tải `curl`/PowerShell của bước bootstrap sử dụng.

### 5.2. Downloader chạy bằng Java

Nếu stack trace của lỗi tải có `java.net` hoặc `javax.net.ssl`, Java có các system properties:

- `https.proxyHost`, `https.proxyPort` cho HTTPS;
- `http.proxyHost`, `http.proxyPort` cho HTTP;
- `http.nonProxyHosts` cho host không qua proxy, cũng được Java HTTPS dùng.

Ví dụ cấu hình **cho các tiến trình JVM** trong shell hiện tại:

```bash
export JAVA_TOOL_OPTIONS="-Dhttps.proxyHost=proxy.example.org -Dhttps.proxyPort=8080"
./mvnw --version
```

```powershell
$env:JAVA_TOOL_OPTIONS = "-Dhttps.proxyHost=proxy.example.org -Dhttps.proxyPort=8080"
.\mvnw.cmd --version
```

`JAVA_TOOL_OPTIONS` có thể ảnh hưởng tới nhiều JVM khởi chạy trong session; xác nhận và gỡ biến khi kết thúc chẩn đoán. Những thuộc tính này **không làm curl/wget/PowerShell tự chuyển qua proxy Java**. Nếu proxy cần NTLM, Kerberos, PAC hoặc xác thực đặc biệt, yêu cầu hướng dẫn từ quản trị mạng; chỉ khai báo host/port có thể chưa đủ.

### 5.3. Khi Maven đã khởi động: proxy trong settings.xml

Nếu `./mvnw --version` chạy thành công nhưng build thất bại khi tải dependency/plugin, Maven thường dùng cấu hình trong `~/.m2/settings.xml` của người dùng (Windows: trong thư mục `.m2` thuộc user). Ví dụ XML về proxy:

```xml
<settings>
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
</settings>
```

`nonProxyHosts` phân tách bởi dấu `|`; có thể dùng wildcard. Tài khoản/mật khẩu proxy nếu cần phải được lưu theo cơ chế được tổ chức cho phép, với quyền truy cập thích hợp, **không commit secrets** vào Git.

**Phân biệt:** `settings.xml` phục vụ Maven Resolver, plugin và dependency sau bootstrap. Nó không tự động bảo đảm proxy của script tải Maven distribution hoạt động, đặc biệt với Wrapper `only-script`. Khi sự cố xảy ra trước khi có output phiên bản Maven, hãy quay lại mục 5.1/5.2.

## 6. TLS, SSLHandshakeException và chứng chỉ doanh nghiệp

Môi trường công ty có thể sử dụng proxy kiểm tra TLS, cấp lại chứng chỉ với **CA nội bộ**. Trình duyệt có thể tin CA này, còn Java JDK hoặc curl trên cùng máy chưa chắc tin. Vì vậy “trình duyệt mở được URL” không đủ để kết luận việc tải Maven từ Wrapper sẽ thành công.

### 6.1. Java báo PKIX hoặc SSLHandshakeException

Khi gặp `PKIX path building failed`, `SSLHandshakeException` hoặc `unable to find valid certification path`, thực hiện:

1. Xác định downloader tạo lỗi là Java Wrapper hay Maven runtime đã chạy.
2. Kiểm tra `JAVA_HOME` và `java -version` để biết **JDK nào** đang dùng truststore; máy có nhiều JDK có thể có CA khác nhau.
3. Đối chiếu chứng chỉ máy chủ, tên hostname, thời gian hệ thống và việc proxy có thực hiện TLS inspection.
4. Lấy CA root/intermediate **đã được quản trị xác nhận**, rồi cấu hình hệ thống/JDK truststore hoặc truststore riêng theo chính sách tổ chức.
5. Chạy lại `mvnw --version`; nếu phần này thành công nhưng build vẫn lỗi TLS, chẩn đoán repository khác ở giai đoạn Maven.

Java hỗ trợ các thuộc tính `javax.net.ssl.trustStore` và `javax.net.ssl.trustStoreType`. Ví dụ cú pháp với **truststore hợp lệ đã được cung cấp**:

```bash
export JAVA_TOOL_OPTIONS="-Djavax.net.ssl.trustStore=/opt/corp/certs/truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12"
./mvnw --version
```

Đường dẫn chỉ minh họa: file phải có thật, chứa chuỗi CA đáng tin cậy và được mở khóa đúng nếu đặt mật khẩu. Khi dùng truststore riêng, đừng vô tình loại bỏ những CA công cộng cần thiết. Không nhập chứng chỉ từ nguồn không xác minh.

### 6.2. Curl/PowerShell báo certificate verify failed

Lỗi `curl: (60) SSL certificate problem` hoặc thông báo certificate verify của công cụ OS thường cần xử lý ở **kho tin cậy của downloader đó**. Chỉnh Java truststore không mặc nhiên sửa được curl. Làm theo hướng dẫn quản trị CA của tổ chức, tránh:

- `curl -k`/`--insecure`;
- tắt SSL validation hoặc bỏ qua kiểm tra checksum;
- chuyển URL phân phối sang `http://` để né TLS.

## 7. Java và JDK: chọn đúng runtime cho Maven

Maven Wrapper tải **Maven distribution**, nhưng không mặc nhiên cài đúng JDK cho môi trường. Phân biệt:

- **Java để chạy Maven Core**: JDK thực thi lệnh Maven; các phiên bản Maven có yêu cầu Java tối thiểu.
- **Java để bootstrap Wrapper**: kiểu `source` có thể cần `javac`, kiểu chạy JAR cần runtime tương thích với bytecode của JAR.
- **Java để biên dịch ứng dụng**: phụ thuộc `maven.compiler.release` hoặc Maven Toolchains; không nhất thiết trùng Java runtime của Maven.

Ví dụ mốc tương thích:

| Maven/Wrapper | Yêu cầu cần biết |
| --- | --- |
| Maven 3.9.x | Chạy với JDK 8 trở lên |
| Maven 4.x | Chạy với JDK 17 trở lên |
| Wrapper `source` | Có `javac` để biên dịch helper khi cần |
| Dự án đặt `maven.compiler.release=17` | Cần JDK/toolchain có compiler Java 17; đây không phải phiên bản Maven |

Nếu gặp `JAVA_HOME is not defined correctly`, `java: command not found` hoặc `UnsupportedClassVersionError`, xác minh **Java mà script thật sự dùng**. Ví dụ cấu hình tạm trên Linux/macOS:

```bash
export JAVA_HOME=/opt/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version
./mvnw --version
```

Ví dụ Windows PowerShell:

```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-17"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
& "$env:JAVA_HOME\bin\java.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" -version
.\mvnw.cmd --version
```

Hai đường dẫn JDK trong ví dụ là **giả định**, phải thay bằng nơi JDK thực sự được cài. `JAVA_HOME` trỏ đến **thư mục gốc JDK**, không trỏ vào `bin` hoặc file `java`. Trên Windows, không lưu dấu ngoặc kép thành một phần của giá trị biến.

`UnsupportedClassVersionError` nghĩa là Java runtime không đọc được class biên dịch cho release mới hơn. Ví dụ **major version 61 = Java 17**; **major version 52 = Java 8**. Xem class nào bị từ chối: đó có thể là bootstrap Wrapper, Maven Core, plugin hoặc chương trình ứng dụng. Không tự động sửa `maven.compiler.release` chỉ vì thấy lỗi này ở giai đoạn Maven chưa khởi động.

Trong CI, đặt lệnh `java -version` **trước** `./mvnw --version` để phát hiện runner đang dùng JDK khác máy phát triển. Khi chạy Maven 4, runner tối thiểu phải cung cấp JDK 17; nâng Maven distribution mà không nâng image Java sẽ gây lỗi startup.

## 8. Cache, file ZIP lỗi và checksum

Maven Wrapper thường lưu distribution dưới `~/.m2/wrapper/dists`, hoặc đường dẫn do `MAVEN_USER_HOME` ảnh hưởng. Thư mục này **khác** cache dependencies `~/.m2/repository`.

Nếu lỗi giải nén, file ZIP rỗng/hỏng hoặc download bị ngắt:

1. Xác định đúng version và URL Maven distribution dự án yêu cầu.
2. Kiểm tra ổ đĩa, quyền ghi thư mục cache, trạng thái tải đủ file.
3. Đối chiếu checksum SHA-256 từ nguồn đáng tin nếu dự án đã khai báo.
4. Khi đã chứng minh bản cache của **một version** bị hỏng, chỉ làm sạch phần cache đúng version đó theo quy định hệ thống và tải lại từ URL tin cậy; không xóa toàn bộ `~/.m2`.
5. Với CI không có internet, cấp sẵn distribution đã xác minh trong cache hoặc dùng kho nội bộ phục vụ Maven ZIP.

Maven Wrapper hỗ trợ `distributionSha256Sum` cho Maven distribution; các loại có Wrapper JAR có thể dùng `wrapperSha256Sum`. Đây phải là giá trị SHA-256 thật, không được tự bịa hoặc vô hiệu hóa để bỏ qua lỗi.

Lưu ý về chế độ offline: `mvn -o`/`--offline` chỉ ảnh hưởng Maven khi giải quyết artifacts **sau khi Maven khởi động**; nó không tự tạo ra Maven distribution còn thiếu cho Wrapper. Cache CI của `wrapper/dists` có thể giảm download lặp lại, nhưng cần bảo vệ tính toàn vẹn của cache.

## 9. Hai ví dụ chẩn đoán theo giai đoạn

### Ví dụ A — trình duyệt truy cập được URL, Wrapper vẫn báo PKIX

- **Hiện tượng:** `.\mvnw.cmd --version` thất bại với `SSLHandshakeException`; trình duyệt mở URL bình thường.
- **Suy luận:** downloader dùng kho chứng chỉ khác trình duyệt, hoặc Java bị cấu hình proxy/truststore không đúng.
- **Thao tác:** kiểm tra loại Wrapper, log, `JAVA_HOME`/`java -version` và certificate chain qua proxy.
- **Giải quyết:** thêm CA doanh nghiệp **đã được xác thực** vào truststore phù hợp hoặc chuyển sang URL nội bộ được quản lý; chạy lại `.\mvnw.cmd --version`.
- **Không áp dụng:** bỏ qua SSL, giảm độ bảo mật hoặc sửa dependencies trong POM.

### Ví dụ B — máy cá nhân thành công, CI dùng Java quá cũ

- **Hiện tượng:** `./mvnw --version` trên máy cá nhân được, runner CI báo `UnsupportedClassVersionError` sau khi dự án ghim Maven 4.
- **Suy luận:** runner có thể đang chạy JDK 8/11, còn Maven 4 cần JDK 17 trở lên.
- **Thao tác:** in `java -version` và `JAVA_HOME` trước khi chạy Wrapper, kiểm tra `distributionUrl`.
- **Giải quyết:** chọn JDK/runtime tương thích trong runner; xác minh lại `./mvnw --version` rồi mới `./mvnw verify`.
- **Không áp dụng:** chỉ thay `maven.compiler.release` (đây là Java target khi compile).

## 10. Checklist xác nhận lỗi đã được xử lý

Tiến hành theo thứ tự để không nhầm giai đoạn:

1. **Script:** `mvnw`/`mvnw.cmd` và `.mvn/wrapper/maven-wrapper.properties` tồn tại; shell và quyền thực thi phù hợp.
2. **Java:** `java -version`, `javac -version` khi cần, `JAVA_HOME`, `PATH` khớp yêu cầu của Maven runtime.
3. **Download:** `distributionUrl` hợp lệ; công cụ tải có DNS, mạng, proxy và CA tin cậy; không dùng SSL insecure.
4. **Cache:** distribution đầy đủ, có quyền giải nén, checksum đúng nếu đã ghim.
5. **Wrapper:** `./mvnw --version` trên Unix hoặc `.\mvnw.cmd --version` trên Windows in được phiên bản Maven và Java thực sự đang chạy.
6. **Build:** sau đó mới chạy `./mvnw -B verify` (Windows: `.\mvnw.cmd -B verify`) để kiểm tra plugin, dependency và repository.

Nếu bước 5 thành công nhưng bước 6 báo `Could not resolve dependencies` hay `PluginResolutionException`, lúc này xem `settings.xml`, mirror, credentials, cache Maven và repository. Lỗi này thuộc **sau bootstrap**, cần xử lý khác với lỗi Wrapper tải Maven.

## Tài liệu chính thức

- [Apache Maven Wrapper — loại Wrapper, tải distribution, biến môi trường, checksum](https://maven.apache.org/tools/wrapper/)
- [Apache Maven — proxy trong settings.xml](https://maven.apache.org/guides/mini/guide-proxies.html)
- [Apache Maven — hướng dẫn cài đặt và yêu cầu JDK](https://maven.apache.org/install.html)
- [Apache Maven — chuyển sang Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html)
- [Oracle Java — Networking Properties](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/doc-files/net-properties.html)
- [Oracle Java — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html)
