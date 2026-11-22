# Proxy, chứng chỉ TLS và quyền truy cập tài nguyên mạng

Một quy trình build Java thường cần truy cập mạng để tải Gradle hoặc Maven, plugin, thư viện, metadata phiên bản và các tài nguyên khác từ repository. Trong mạng doanh nghiệp, những kết nối này có thể phải đi qua proxy, sử dụng tài khoản xác thực, hoặc tin cậy chứng chỉ do tổ chức cấp. Nếu môi trường build chưa được cấu hình đúng, dự án có thể biên dịch bình thường trên một máy nhưng thất bại khi tải dependency trên máy khác hoặc trong CI.

Bài này giải thích cách nhận diện các kết nối mạng của quá trình build, cấu hình proxy, xử lý chứng chỉ TLS, truy cập repository riêng và chẩn đoán lỗi thường gặp. Các ví dụ tập trung vào Java cùng Maven và Gradle; nguyên tắc tương tự cũng áp dụng cho các công cụ build khác.

## 1. Build tool cần truy cập mạng ở những thời điểm nào?

Một lệnh build có thể tạo ra nhiều kết nối mạng khác nhau. Ví dụ:

- **Wrapper distribution:** Gradle Wrapper hoặc Maven Wrapper có thể cần tải bản phân phối của công cụ build trước khi chạy dự án.
- **Plugin:** Maven và Gradle có thể tải plugin dùng để biên dịch, kiểm tra chất lượng, đóng gói hoặc triển khai.
- **Dependency:** công cụ tải các thư viện mà mã nguồn hoặc plugin cần.
- **Repository metadata:** công cụ đọc metadata để xác định phiên bản, biến thể, checksum và vị trí artifact.
- **Tài nguyên bổ sung:** script build, schema, file cấu hình hoặc dịch vụ nội bộ có thể được truy cập qua HTTP hoặc HTTPS.

Vì vậy, lỗi mạng không nhất thiết xảy ra ở bước biên dịch mã nguồn. Build có thể thất bại trước khi dự án được cấu hình, trong lúc tải plugin, hoặc khi một dependency chỉ được yêu cầu ở một task cụ thể.

Có thể hình dung đường đi của một yêu cầu như sau:

~~~text
Gradle / Maven / Wrapper
          |
          v
    DNS và cấu hình mạng
          |
          v
   Proxy (nếu được yêu cầu)
          |
          v
 Repository / máy chủ HTTPS
          |
          v
 Xác thực TLS và chứng chỉ
          |
          v
 Xác thực tài khoản repository
          |
          v
 Tải metadata, plugin hoặc JAR
~~~

Mỗi lớp có thể gây ra một nhóm lỗi riêng. Ví dụ, lỗi DNS xảy ra trước khi kết nối đến proxy hoặc máy chủ; lỗi 407 thường liên quan đến xác thực proxy; lỗi chứng chỉ xảy ra trong quá trình bắt tay TLS; lỗi 401 hoặc 403 thường liên quan đến quyền truy cập tài nguyên.

## 2. Xác định đúng môi trường Java đang chạy build

Trước khi chỉnh proxy hoặc chứng chỉ, hãy xác định tiến trình build đang sử dụng Java nào. Chứng chỉ được tin cậy bởi một JDK không nhất thiết cũng được tin cậy bởi JDK khác.

Kiểm tra Java trong terminal:

~~~text
java -version
javac -version
~~~

Với Maven:

~~~text
mvn -version
~~~

Với Gradle Wrapper:

~~~text
./gradlew --version
~~~

Trên Windows, dùng tệp wrapper tương ứng:

~~~powershell
.\gradlew.bat --version
~~~

Thông tin phiên bản thường cho biết JVM hoặc Java home mà công cụ đang sử dụng. Nếu Maven hoặc Gradle chạy bằng một JDK khác với JDK mà bạn thường gọi từ terminal, hãy cấu hình proxy và truststore cho đúng JVM đó.

Cũng cần phân biệt **JVM chạy build** và **Java toolchain dùng để biên dịch dự án**. Ví dụ, Gradle có thể chạy bằng JDK 21 nhưng sử dụng toolchain JDK 17 để biên dịch mã nguồn. Kết nối tải dependency và việc kiểm tra chứng chỉ thường do JVM chạy Gradle thực hiện; thay đổi toolchain biên dịch không tự động thay đổi truststore của JVM chạy build.

## 3. Proxy là gì và khi nào cần dùng?

Proxy là máy chủ trung gian nhận yêu cầu mạng từ máy của bạn rồi chuyển tiếp đến đích. Tổ chức có thể yêu cầu mọi kết nối Internet phải đi qua proxy để kiểm soát truy cập, ghi log hoặc áp dụng chính sách bảo mật.

Có thể gặp một số kiểu cấu hình:

- **HTTP proxy:** proxy nhận yêu cầu HTTP và thường hỗ trợ đường hầm CONNECT để truy cập máy chủ HTTPS.
- **HTTPS proxy:** kết nối từ máy khách đến chính proxy cũng sử dụng TLS; đây là cấu hình khác với việc truy cập một trang HTTPS qua HTTP proxy.
- **Proxy yêu cầu xác thực:** người dùng phải cung cấp tài khoản hoặc thông tin xác thực do quản trị mạng cấp.
- **Proxy nội bộ và ngoại lệ:** một số địa chỉ nội bộ được truy cập trực tiếp, không đi qua proxy.

Không nên tự đoán địa chỉ hoặc cổng proxy. Hãy lấy cấu hình từ quản trị viên mạng hoặc tài liệu môi trường phát triển. Các giá trị như **proxy.example.com** và **8080** trong ví dụ chỉ là giá trị minh họa.

### Biến môi trường proxy

Nhiều công cụ dòng lệnh và thư viện mạng nhận các biến môi trường:

~~~text
HTTP_PROXY
HTTPS_PROXY
NO_PROXY
~~~

Một số môi trường còn dùng tên chữ thường tương ứng. Tuy nhiên, không phải mọi thành phần Java hoặc mọi phiên bản build tool đều tự động đọc các biến này. Java thường sử dụng các thuộc tính hệ thống như **http.proxyHost** và **https.proxyHost**; Maven và Gradle có cơ chế cấu hình riêng.

Vì vậy, nếu trình duyệt truy cập Internet được nhưng Gradle hoặc Maven không tải được dependency, không nên kết luận rằng proxy đã được cấu hình cho mọi ứng dụng. Cần kiểm tra cấu hình mà chính tiến trình build sử dụng.

## 4. Cấu hình proxy cho Maven

Maven lưu cấu hình người dùng trong tệp **settings.xml**, thường nằm tại:

~~~text
Windows: %USERPROFILE%\.m2\settings.xml
macOS/Linux: ~/.m2/settings.xml
~~~

Có thể đặt proxy trong phần **proxies**:

~~~xml
<settings>
  <proxies>
    <proxy>
      <id>company-proxy</id>
      <active>true</active>
      <protocol>http</protocol>
      <host>proxy.example.com</host>
      <port>8080</port>
      <username>PROXY_USERNAME</username>
      <password>PROXY_PASSWORD</password>
      <nonProxyHosts>localhost|127.*|*.internal.example.com</nonProxyHosts>
    </proxy>
  </proxies>
</settings>
~~~

Ý nghĩa các trường:

- **id:** tên nhận diện cấu hình proxy.
- **active:** bật hoặc tắt cấu hình proxy.
- **protocol:** giao thức mà Maven dùng để kết nối đến proxy. Với proxy HTTP hỗ trợ CONNECT, giá trị thường là **http**, kể cả khi đích đến là URL HTTPS.
- **host** và **port:** máy chủ và cổng proxy.
- **username** và **password:** thông tin xác thực proxy nếu proxy yêu cầu.
- **nonProxyHosts:** các máy chủ được truy cập trực tiếp. Các mẫu được phân cách bằng dấu gạch đứng (**|**).

Không phải lúc nào cũng cần username và password. Nếu proxy không yêu cầu xác thực, hãy bỏ hai phần tử này. Danh sách **nonProxyHosts** cần tuân theo chính sách mạng của tổ chức; không đưa miền nội bộ vào danh sách ngoại lệ nếu quản trị viên yêu cầu đi qua proxy.

Maven có thể sử dụng mirror để chuyển các yêu cầu repository sang máy chủ nội bộ. Ví dụ, một tổ chức có thể cung cấp mirror cho Maven Central nhằm lưu cache hoặc kiểm soát dependency:

~~~xml
<settings>
  <mirrors>
    <mirror>
      <id>company-mirror</id>
      <mirrorOf>central</mirrorOf>
      <url>https://repo.example.com/maven-central</url>
    </mirror>
  </mirrors>
</settings>
~~~

Nếu tổ chức yêu cầu mọi repository được chuyển qua một mirror, quản trị viên có thể cấu hình phạm vi mirror rộng hơn. Hãy dùng đúng URL và giá trị **mirrorOf** do tổ chức cung cấp; cấu hình sai có thể làm Maven không tìm thấy artifact dù proxy đã hoạt động.

Proxy và mirror giải quyết hai việc khác nhau: proxy điều khiển đường truyền mạng, còn mirror thay đổi repository mà Maven truy cập.

## 5. Cấu hình proxy cho Gradle

Gradle thường nhận proxy HTTP/HTTPS thông qua các thuộc tính hệ thống của JVM. Có thể khai báo trong tệp **gradle.properties** ở thư mục người dùng:

~~~text
Windows: %USERPROFILE%\.gradle\gradle.properties
macOS/Linux: ~/.gradle/gradle.properties
~~~

Ví dụ:

~~~properties
systemProp.http.proxyHost=proxy.example.com
systemProp.http.proxyPort=8080
systemProp.https.proxyHost=proxy.example.com
systemProp.https.proxyPort=8080
systemProp.http.nonProxyHosts=localhost|127.*|*.internal.example.com
~~~

Các thuộc tính trên khai báo proxy cho kết nối HTTP và HTTPS. Nếu proxy yêu cầu xác thực, Gradle/JVM còn hỗ trợ các thuộc tính như:

~~~properties
systemProp.http.proxyUser=PROXY_USERNAME
systemProp.http.proxyPassword=PROXY_PASSWORD
~~~

Thông tin tài khoản cần được quản lý như bí mật. Không commit mật khẩu vào repository. Có thể đặt cấu hình cá nhân trong Gradle user home hoặc để pipeline CI cung cấp giá trị từ kho bí mật. Nếu dùng proxy có cơ chế xác thực đặc biệt, hãy kiểm tra phương thức xác thực mà proxy hỗ trợ và hướng dẫn của quản trị viên; không phải mọi cơ chế xác thực doanh nghiệp đều tương thích với cấu hình username/password cơ bản.

Tệp **gradle.properties** trong thư mục dự án có thể được chia sẻ cùng mã nguồn, còn tệp trong Gradle user home phù hợp hơn với cấu hình riêng của máy phát triển. Các thuộc tính hệ thống trong cấu hình dự án cũng cần được đặt đúng vị trí theo quy tắc của Gradle; trong dự án nhiều module, nên ưu tiên cấu hình dùng chung ở root project hoặc user home.

### Lưu ý về Gradle Wrapper

Gradle Wrapper có thể tải bản phân phối Gradle trước khi Gradle đọc và thực thi cấu hình của dự án. Vì vậy, cấu hình proxy chỉ nằm trong script build hoặc cấu hình được đọc sau khi Gradle khởi động có thể chưa đủ để tải chính bản phân phối Wrapper.

Trong trường hợp Wrapper không tải được distribution, hãy cấu hình thuộc tính proxy cho JVM khởi chạy Wrapper, chẳng hạn thông qua biến môi trường **JAVA_TOOL_OPTIONS** hoặc **GRADLE_OPTS** do môi trường cung cấp. Ví dụ chỉ đặt host và port:

~~~text
-Dhttps.proxyHost=proxy.example.com -Dhttps.proxyPort=8080
~~~

Sau khi Wrapper tải được Gradle, cấu hình trong Gradle user home có thể được dùng cho các yêu cầu tiếp theo của quá trình build. Với Maven Wrapper, cũng cần xem riêng bước tải Maven distribution và cấu hình JVM mà tiến trình Wrapper sử dụng; tệp settings.xml chỉ có tác dụng sau khi Maven được khởi chạy và đọc cấu hình.

## 6. Phân biệt proxy, repository và thông tin xác thực

Có ít nhất hai loại thông tin xác thực khác nhau trong một quy trình build:

1. **Tài khoản proxy:** cho phép máy của bạn đi qua máy chủ trung gian.
2. **Tài khoản repository:** cho phép tải hoặc đẩy artifact lên kho lưu trữ Maven/Gradle.

Hai tài khoản này có thể hoàn toàn khác nhau. Đăng nhập proxy thành công không có nghĩa tài khoản repository cũng có quyền tải artifact riêng.

### Khai báo thông tin xác thực repository trong Maven

Maven sử dụng phần **servers** trong settings.xml. Giá trị **id** phải khớp với id của repository hoặc mirror được khai báo trong cấu hình Maven:

~~~xml
<settings>
  <servers>
    <server>
      <id>internal-releases</id>
      <username>REPOSITORY_USERNAME</username>
      <password>REPOSITORY_PASSWORD</password>
    </server>
  </servers>
</settings>
~~~

Ví dụ repository có id tương ứng:

~~~xml
<repositories>
  <repository>
    <id>internal-releases</id>
    <url>https://repo.example.com/releases</url>
  </repository>
</repositories>
~~~

Nếu id không khớp, Maven có thể không gửi thông tin xác thực đến repository mong muốn. Không nên đặt thông tin đăng nhập trực tiếp trong pom.xml vì tệp này thường được commit và chia sẻ.

Maven hỗ trợ cơ chế mã hóa mật khẩu trong cấu hình người dùng thông qua **settings-security.xml** và lệnh mã hóa mật khẩu của Maven. Cơ chế này giúp tránh lưu mật khẩu rõ trong settings.xml, nhưng vẫn cần bảo vệ master password và quyền truy cập vào máy người dùng. Trong CI, nên dùng secret store của nền tảng và tạo hoặc cung cấp settings.xml trong môi trường chạy build.

### Khai báo thông tin xác thực repository trong Gradle

Gradle cho phép khai báo credentials cho repository trong script. Ví dụ Groovy DSL:

~~~groovy
repositories {
    maven {
        url = uri("https://repo.example.com/releases")
        credentials {
            username = System.getenv("REPO_USER")
            password = System.getenv("REPO_PASSWORD")
        }
    }
}
~~~

Pipeline hoặc môi trường phát triển sẽ cung cấp hai biến **REPO_USER** và **REPO_PASSWORD**. Với Kotlin DSL, khối credentials cũng có thể đọc giá trị từ biến môi trường:

~~~kotlin
repositories {
    maven {
        url = uri("https://repo.example.com/releases")
        credentials {
            username = System.getenv("REPO_USER")
            password = System.getenv("REPO_PASSWORD")
        }
    }
}
~~~

Nếu repository yêu cầu xác thực, hãy kiểm tra id hoặc URL, tên người dùng, token và quyền truy cập. Một số repository dùng token thay cho mật khẩu; khi đó cần dùng đúng loại credentials theo hướng dẫn của máy chủ.

Không ghi token hoặc mật khẩu vào file build.gradle, build.gradle.kts, gradle.properties được commit, log build hoặc ví dụ tài liệu. Nếu bí mật từng bị commit, xóa khỏi file hiện tại chưa đủ: cần thu hồi hoặc xoay vòng bí mật đó.

## 7. TLS và chứng chỉ số trong quá trình build

TLS (Transport Layer Security) bảo vệ kết nối đến máy chủ HTTPS. Trong quá trình bắt tay TLS, máy chủ gửi chứng chỉ để chứng minh danh tính. Java kiểm tra chuỗi chứng chỉ có dẫn đến một CA (Certificate Authority) được tin cậy hay không, chứng chỉ còn hạn không, tên máy chủ có khớp hay không và các điều kiện bảo mật khác có được đáp ứng hay không.

Các khái niệm quan trọng:

- **Server certificate:** chứng chỉ máy chủ gửi cho client.
- **CA certificate:** chứng chỉ của tổ chức phát hành hoặc ký chứng chỉ khác.
- **Certificate chain:** chuỗi chứng chỉ từ chứng chỉ máy chủ qua các CA trung gian đến CA gốc đáng tin cậy.
- **Truststore:** kho chứa các chứng chỉ hoặc CA mà ứng dụng Java tin cậy.
- **Keystore:** kho có thể chứa khóa riêng và chứng chỉ định danh của ứng dụng, thường dùng khi client cần xác thực bằng chứng chỉ.

Trình duyệt và Java có thể sử dụng các kho tin cậy khác nhau. Vì vậy, trình duyệt mở được repository không đảm bảo JVM chạy Maven hoặc Gradle cũng tin cậy chứng chỉ đó.

### Java lấy chứng chỉ tin cậy từ đâu?

JDK thường có truststore mặc định tên **cacerts** trong thư mục bảo mật của Java runtime. Vị trí cụ thể tùy phiên bản và cách cài đặt JDK. Có thể xem các chứng chỉ trong kho mặc định bằng:

~~~text
keytool -list -cacerts
~~~

Có thể kiểm tra một tệp chứng chỉ được cung cấp bởi quản trị viên:

~~~text
keytool -printcert -file corporate-root-ca.pem
~~~

Hãy xác minh fingerprint của chứng chỉ qua một kênh đáng tin cậy với quản trị viên hoặc bộ phận bảo mật. Không nhập một chứng chỉ chỉ vì nó xuất hiện trong thông báo lỗi hoặc được tải xuống từ một kết nối chưa xác thực.

### Tạo truststore riêng

Thay vì sửa truststore mặc định của JDK dùng chung, có thể tạo truststore riêng cho môi trường build:

~~~text
keytool -importcert -alias corporate-root-ca -file corporate-root-ca.pem -keystore company-truststore.p12 -storetype PKCS12
~~~

Lệnh sẽ yêu cầu xác nhận và mật khẩu cho truststore. Chỉ nhập CA gốc hoặc CA trung gian đã được xác minh theo hướng dẫn của tổ chức. Thông thường không nên nhập riêng chứng chỉ máy chủ ngắn hạn làm CA tin cậy, vì chứng chỉ máy chủ có thể được gia hạn hoặc thay thế.

Kiểm tra nội dung truststore:

~~~text
keytool -list -keystore company-truststore.p12 -storetype PKCS12
~~~

Để JVM sử dụng truststore riêng, cần cung cấp các thuộc tính hệ thống tương ứng:

~~~text
-Djavax.net.ssl.trustStore=/path/to/company-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=TRUSTSTORE_PASSWORD
~~~

Hãy thay đường dẫn và mật khẩu bằng giá trị của môi trường. Nếu truststore có mật khẩu, hãy truyền mật khẩu thông qua cơ chế bí mật của máy phát triển hoặc CI; không commit mật khẩu vào repository hay ghi nó vào log. Khi cấu hình cho Maven, các tùy chọn JVM có thể được truyền qua **MAVEN_OPTS**. Với Gradle daemon, có thể cấu hình các tùy chọn JVM qua **org.gradle.jvmargs** hoặc cơ chế khởi chạy JVM phù hợp với môi trường.

Một truststore tùy chỉnh có thể thay thế tập CA mặc định mà JVM sử dụng. Nếu ứng dụng cần cả CA công khai lẫn CA nội bộ, hãy tạo truststore có đầy đủ các CA cần thiết hoặc dùng phương án cấu hình được tổ chức phê duyệt. Không giả định rằng chỉ thêm một CA nội bộ vào truststore riêng sẽ tự động giữ lại toàn bộ CA trong cacerts mặc định.

### TLS inspection của proxy doanh nghiệp

Một số proxy doanh nghiệp giải mã và kiểm tra lưu lượng HTTPS bằng cách tạo chứng chỉ thay thế cho từng máy chủ đích, được ký bởi CA nội bộ của tổ chức. Khi đó, JVM cần tin cậy CA nội bộ được dùng để ký các chứng chỉ thay thế.

Nếu thiếu CA này, trình duyệt có thể hoạt động do đã được quản lý và cài CA nội bộ, trong khi Java vẫn báo lỗi chứng chỉ. Hãy yêu cầu bộ phận IT cung cấp CA và fingerprint chính thức, sau đó cấu hình truststore cho đúng JVM chạy build.

Không khắc phục lỗi bằng cách tắt kiểm tra chứng chỉ, bỏ qua hostname verification hoặc cài một trust-all trust manager. Các cách đó làm mất khả năng xác thực máy chủ và khiến thông tin xác thực hoặc dependency có thể bị đánh cắp hay thay thế.

## 8. Mutual TLS: khi repository yêu cầu chứng chỉ phía client

Một số dịch vụ nội bộ yêu cầu xác thực hai chiều, gọi là mutual TLS (mTLS). Trong trường hợp này:

- Client xác minh chứng chỉ của server bằng **truststore**.
- Server xác minh danh tính client bằng chứng chỉ và khóa riêng do client cung cấp, thường được lưu trong **keystore**.

Đây là hai mục đích khác nhau. Nếu repository yêu cầu chứng chỉ client, chỉ thêm CA máy chủ vào truststore sẽ không đủ. Bạn cần được cấp chứng chỉ client, khóa riêng và hướng dẫn cấu hình tương ứng.

Các thuộc tính JVM thường gặp cho client keystore:

~~~text
-Djavax.net.ssl.keyStore=/path/to/client-keystore.p12
-Djavax.net.ssl.keyStoreType=PKCS12
-Djavax.net.ssl.keyStorePassword=KEYSTORE_PASSWORD
~~~

Không chia sẻ tệp chứa khóa riêng hoặc mật khẩu keystore qua repository mã nguồn, chat công khai hay log CI. Hãy lưu chúng trong kho bí mật hoặc cơ chế chứng chỉ do tổ chức quản lý, đồng thời tuân thủ chính sách cấp phát và thu hồi chứng chỉ.

## 9. Quyền truy cập tài nguyên mạng và repository nội bộ

Ngay cả khi proxy và TLS đã hoạt động, build vẫn có thể không tải được artifact vì repository yêu cầu quyền truy cập riêng hoặc bị giới hạn mạng.

Cần kiểm tra các yếu tố sau:

- **Repository URL:** đúng máy chủ, cổng, đường dẫn và giao thức HTTPS.
- **Repository ID:** khớp với cấu hình credentials của Maven hoặc cấu hình repository trong Gradle.
- **Quyền đọc/ghi:** tài khoản có quyền tải dependency hay chỉ được xem một số repository.
- **Mirror và repository policy:** build có đang được chuyển đến mirror nội bộ hay không; mirror có đồng bộ artifact cần thiết chưa.
- **DNS và firewall:** máy có phân giải được tên miền và được phép kết nối đến máy chủ hoặc proxy không.
- **Rate limit:** repository có giới hạn số yêu cầu hoặc tạm thời từ chối tải xuống không.
- **Artifact coordinates:** group, artifact, version và classifier có chính xác không; artifact có thực sự tồn tại trong repository đó không.

Với Maven, cần xem cả repository dùng cho dependency và repository dùng cho plugin. Một cấu hình mirror có thể thay đổi nơi tải dependency; plugin repository cũng cần được truy cập trong giai đoạn cấu hình hoặc thực thi plugin.

Với Gradle, cần kiểm tra các khối **repositories**, **pluginManagement.repositories** và **buildscript.repositories** nếu dự án sử dụng plugin hoặc buildscript dependency. Cấu hình repository cho dependency của ứng dụng không nhất thiết tự động áp dụng cho plugin được tải trong giai đoạn khởi tạo build.

Không nên thêm repository tùy tiện chỉ để làm build chạy được. Repository bổ sung có thể làm thay đổi nguồn artifact, thứ tự phân giải hoặc rủi ro supply chain. Hãy ưu tiên repository chính thức hoặc mirror do tổ chức quản lý.

## 10. Cấu hình mạng trong CI

Build trên máy cá nhân có thể thành công nhưng thất bại trên CI vì runner dùng mạng, JDK, user home hoặc truststore khác.

Một pipeline cần xác định rõ:

1. Runner có truy cập được proxy hoặc repository không.
2. Proxy host, port và credentials được cung cấp bằng cách nào.
3. JVM nào chạy Maven/Gradle Wrapper.
4. CA nội bộ đã được cài vào truststore của JVM đó chưa.
5. Repository credentials được lấy từ secret store nào.
6. Cache dependency có được chia sẻ đúng cách và có phù hợp với chính sách bảo mật không.

Không đặt thông tin bí mật trong file YAML pipeline được commit. Hãy khai báo chúng trong secret variables hoặc secret store của hệ thống CI. Khi build log được công khai hoặc chia sẻ, cần tránh in toàn bộ biến môi trường, nội dung settings.xml, gradle.properties hoặc tham số JVM có chứa mật khẩu.

Nếu CI dùng container, cần cấu hình chứng chỉ và proxy bên trong container hoặc image chạy build. Việc cài CA vào máy host không đảm bảo container tự động nhận được chứng chỉ đó. Tương tự, cấu hình proxy trong terminal của người dùng không nhất thiết có mặt trong runner.

Đối với build cần tính lặp lại, nên thống nhất phiên bản JDK, Wrapper, repository và cách cung cấp truststore giữa máy phát triển và CI. Nếu dùng dependency cache hoặc chế độ offline, hãy bảo đảm cache chứa đủ artifact và plugin cần thiết cho task đang chạy.

## 11. Chẩn đoán lỗi theo thông báo

Các lỗi mạng thường có thể được phân loại dựa trên thông báo và giai đoạn xảy ra.

| Lỗi hoặc thông báo | Nguyên nhân có thể gặp | Hướng kiểm tra |
|---|---|---|
| **UnknownHostException** | DNS không phân giải được tên proxy hoặc repository | Kiểm tra tên máy chủ, DNS, VPN và cấu hình mạng |
| **Connection timed out** | Firewall chặn, proxy không phản hồi, sai cổng hoặc đường mạng không thông | Xác nhận host/port, VPN, firewall và khả năng truy cập proxy |
| **Connection refused** | Máy chủ đích không lắng nghe tại cổng đó hoặc kết nối bị từ chối | Kiểm tra URL, cổng và trạng thái dịch vụ |
| **407 Proxy Authentication Required** | Proxy yêu cầu thông tin xác thực hoặc credentials không hợp lệ | Kiểm tra cấu hình proxy, username/password hoặc cơ chế đăng nhập |
| **PKIX path building failed** | JVM không xây dựng được chuỗi chứng chỉ đến CA đáng tin cậy | Kiểm tra CA nội bộ, truststore, chuỗi intermediate và đúng JDK đang chạy build |
| **SSLHandshakeException** | Bắt tay TLS thất bại do chứng chỉ, giao thức, cipher hoặc yêu cầu mTLS | Đọc nguyên nhân lồng bên trong; kiểm tra truststore, thời hạn chứng chỉ và client certificate |
| **No subject alternative names matching** | Tên máy chủ trong URL không khớp với tên trong chứng chỉ | Dùng đúng hostname được chứng chỉ cấp cho; không tắt hostname verification |
| **CertificateExpiredException** | Chứng chỉ máy chủ hoặc CA đã hết hạn | Kiểm tra thời hạn và yêu cầu quản trị viên gia hạn/cập nhật chuỗi chứng chỉ |
| **401 Unauthorized** | Thiếu hoặc sai thông tin xác thực repository | Kiểm tra credentials và repository ID |
| **403 Forbidden** | Tài khoản đã được nhận diện nhưng không có quyền thực hiện thao tác | Kiểm tra quyền đọc/ghi, token scope và chính sách repository |
| **404 Not Found** | Artifact, phiên bản hoặc đường dẫn repository không tồn tại; mirror chưa đồng bộ | Kiểm tra tọa độ dependency, URL và trạng thái mirror |
| **Could not resolve dependency** | Repository không truy cập được, artifact không tồn tại hoặc một dependency bắc cầu bị thiếu | Xem repository được truy vấn, thông báo lỗi gốc và dependency cụ thể |

### Một số lệnh kiểm tra hữu ích

Xem cấu hình Java của Maven:

~~~text
mvn -version
~~~

Xem phiên bản và JVM của Gradle Wrapper:

~~~text
./gradlew --version
~~~

Kiểm tra chứng chỉ của máy chủ bằng công cụ OpenSSL nếu công cụ có sẵn:

~~~text
openssl s_client -connect repo.example.com:443 -servername repo.example.com -showcerts
~~~

Lệnh này giúp quan sát chuỗi chứng chỉ mà máy chủ gửi trong một kết nối TLS trực tiếp. Nếu môi trường dùng proxy, cần kiểm tra đường kết nối qua proxy theo đúng cách tổ chức cấu hình; kết quả kết nối trực tiếp không đại diện cho đường truyền mà build tool thực sự sử dụng.

Kiểm tra chứng chỉ được cung cấp dưới dạng tệp:

~~~text
keytool -printcert -file corporate-root-ca.pem
~~~

Chạy Maven với mức log chi tiết hơn khi cần xác định repository hoặc plugin đang được truy cập:

~~~text
mvn -X verify
~~~

Với Gradle:

~~~text
./gradlew --info build
~~~

Chỉ dùng log debug ở môi trường được kiểm soát. Log chi tiết có thể chứa URL nội bộ, thông tin cấu hình hoặc dữ liệu nhạy cảm. Hãy kiểm tra và che thông tin trước khi gửi log cho người khác.

Khi cần phân tích TLS sâu hơn, Java hỗ trợ tùy chọn debug như **javax.net.debug=ssl,handshake**. Đây là log rất dài, chỉ nên bật tạm thời để chẩn đoán và không nên để mặc định trong pipeline.

## 12. Quy trình xử lý sự cố có thứ tự

Khi build không truy cập được tài nguyên mạng, hãy xử lý từ lớp thấp đến lớp cao để khoanh vùng nguyên nhân:

1. **Xác định giai đoạn lỗi:** lỗi xảy ra khi tải Wrapper, tải plugin, resolve dependency hay thực hiện task?
2. **Xác nhận JVM:** dùng Maven hoặc Gradle để xem đúng Java home và phiên bản đang chạy.
3. **Kiểm tra DNS và đường mạng:** xác nhận hostname, VPN, firewall và cổng kết nối.
4. **Kiểm tra proxy:** host, port, protocol, ngoại lệ non-proxy và credentials có đúng không?
5. **Kiểm tra TLS:** hostname, thời hạn chứng chỉ, chuỗi CA và truststore của đúng JVM.
6. **Kiểm tra xác thực repository:** credentials, repository ID, token scope và quyền đọc artifact.
7. **Kiểm tra repository và dependency:** URL, mirror, tọa độ artifact, phiên bản và dependency bắc cầu.
8. **So sánh với CI hoặc máy khác:** JDK, proxy, truststore, user home và biến môi trường có khác nhau không?

Chỉ thay đổi một nhóm cấu hình tại một thời điểm và chạy lại đúng lệnh đã thất bại. Cách này giúp xác định yếu tố nào thực sự giải quyết được lỗi.

## 13. Các nguyên tắc bảo mật cần giữ

Cấu hình mạng là một phần của môi trường build và có thể ảnh hưởng trực tiếp đến tính an toàn của dependency. Hãy giữ các nguyên tắc sau:

- Lấy proxy, CA certificate và repository URL từ nguồn chính thức của tổ chức.
- Xác minh fingerprint của CA trước khi thêm vào truststore.
- Không tắt xác thực TLS hoặc hostname verification để bỏ qua lỗi.
- Không lưu mật khẩu proxy, token repository, private key hoặc truststore password trong mã nguồn.
- Dùng secret store của máy phát triển hoặc CI để cấp credentials.
- Cấp quyền tối thiểu cần thiết cho tài khoản repository.
- Ưu tiên HTTPS và repository/mirror được tổ chức phê duyệt.
- Xoay vòng token hoặc mật khẩu nếu chúng bị lộ trong log, commit hoặc artifact.
- Chỉ bật log debug và TLS trace trong thời gian cần thiết; rà soát trước khi chia sẻ.

Một cấu hình build chạy được chưa chắc đã là cấu hình an toàn. Ví dụ, tắt xác minh chứng chỉ có thể làm build tải được dependency, nhưng cũng mở đường cho máy chủ giả mạo hoặc proxy độc hại cung cấp artifact bị thay thế.

## 14. Ví dụ tổng hợp: Maven qua proxy và repository nội bộ

Giả sử một máy phát triển nằm trong mạng doanh nghiệp, phải đi qua proxy để truy cập Internet và cần tải dependency từ repository nội bộ.

Cấu hình trong **~/.m2/settings.xml** có thể gồm proxy và credentials repository:

~~~xml
<settings>
  <proxies>
    <proxy>
      <id>company-proxy</id>
      <active>true</active>
      <protocol>http</protocol>
      <host>proxy.example.com</host>
      <port>8080</port>
      <nonProxyHosts>localhost|127.*|*.internal.example.com</nonProxyHosts>
    </proxy>
  </proxies>

  <servers>
    <server>
      <id>internal-releases</id>
      <username>REPOSITORY_USERNAME</username>
      <password>REPOSITORY_PASSWORD</password>
    </server>
  </servers>
</settings>
~~~

Trong cấu hình dự án, repository dùng cùng id:

~~~xml
<repositories>
  <repository>
    <id>internal-releases</id>
    <url>https://repo.example.com/releases</url>
  </repository>
</repositories>
~~~

Nếu repository sử dụng CA nội bộ, hãy yêu cầu CA đã xác minh và tạo truststore riêng. Sau đó cung cấp truststore cho JVM chạy Maven thông qua tùy chọn JVM được quản lý an toàn. Không đặt mật khẩu thật vào file dự án.

Chạy kiểm tra:

~~~text
mvn -version
mvn verify
~~~

Nếu lệnh báo 407, kiểm tra proxy. Nếu báo lỗi PKIX hoặc SSLHandshakeException, kiểm tra TLS và truststore. Nếu báo 401 hoặc 403, kiểm tra credentials repository và quyền truy cập. Nếu artifact không tồn tại, kiểm tra tọa độ dependency và repository URL.

## 15. Ví dụ tổng hợp: Gradle qua proxy

Với Gradle, đặt proxy trong Gradle user home, ví dụ **~/.gradle/gradle.properties**:

~~~properties
systemProp.http.proxyHost=proxy.example.com
systemProp.http.proxyPort=8080
systemProp.https.proxyHost=proxy.example.com
systemProp.https.proxyPort=8080
systemProp.http.nonProxyHosts=localhost|127.*|*.internal.example.com
~~~

Nếu repository nội bộ cần tài khoản, cung cấp biến môi trường trong môi trường chạy build:

~~~text
REPO_USER
REPO_PASSWORD
~~~

Sau đó khai báo repository trong script bằng cách đọc các biến này, như ví dụ ở phần credentials. Nếu cần CA nội bộ, cấu hình truststore cho JVM chạy Gradle daemon. Nếu lỗi xảy ra trước khi Gradle được tải, hãy cấu hình proxy cho chính JVM chạy Gradle Wrapper.

Chạy kiểm tra:

~~~text
./gradlew --version
./gradlew build --info
~~~

Trên Windows:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat build --info
~~~

Khi build chạy thành công, hãy bảo đảm cấu hình cần thiết được cung cấp nhất quán trên máy phát triển và CI, đồng thời giữ bí mật ngoài repository mã nguồn.

## 16. Kết luận

Proxy, TLS và quyền truy cập tài nguyên mạng là ba phần khác nhau nhưng liên quan chặt chẽ trong môi trường build. Proxy quyết định cách yêu cầu đi qua mạng; TLS xác minh và bảo vệ kết nối HTTPS; credentials và quyền repository quyết định người dùng có thể truy cập artifact hay không.

Khi xử lý sự cố, cần xác định đúng JVM và giai đoạn kết nối, sau đó kiểm tra DNS, proxy, TLS, xác thực và repository theo thứ tự. Cấu hình rõ ràng, dùng truststore được xác minh và quản lý bí mật đúng cách sẽ giúp quy trình build ổn định, có thể lặp lại và an toàn trên máy cá nhân lẫn CI.
