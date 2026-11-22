# Maven Settings: proxies, nonProxyHosts và truy cập mạng doanh nghiệp

## 1. Bối cảnh: Maven không tải được dependency sau khi vào mạng công ty

Một dự án Maven có thể biên dịch bình thường ở nhà nhưng không chạy được tại văn phòng hoặc trong CI của doanh nghiệp. Terminal báo lỗi như `Could not transfer artifact`, `407 Proxy Authentication Required`, `Connection timed out` hoặc `PKIX path building failed`; trong khi trình duyệt vẫn mở được website.

Nguyên nhân không nhất thiết nằm trong `pom.xml`. Maven phải tải **POM, dependency, plugin và metadata** từ các repository, còn mạng công ty có thể yêu cầu đi qua HTTP proxy, DNS/VPN nội bộ, repository manager hoặc chuỗi chứng chỉ TLS do tổ chức quản lý.

Bài này tập trung vào ba kỹ năng:

1. Cấu hình `<proxies>` và `<nonProxyHosts>` đúng vị trí trong Maven `settings.xml`, hiểu từng trường và đích nào đi qua proxy.
2. Phân biệt **proxy mạng** với **mirror/repository manager** và thông tin xác thực của chúng; cấu hình an toàn trong môi trường doanh nghiệp.
3. Kiểm chứng một build Java 17/JUnit 5 qua Maven, chẩn đoán lỗi mạng có hệ thống mà không vô hiệu hóa TLS, không để lộ mật khẩu và không tự ý bỏ qua quy định bảo mật.

Ví dụ hướng đến **Maven 3.9.x**, **JDK 17+**. Các tên máy `proxy.corp.example` và `packages.corp.example` dùng miền ví dụ, **không phải máy chủ thật**; khi thực hành cần lấy hostname, port, quyền và URL thật từ bộ phận IT hoặc tài liệu hạ tầng được phép sử dụng. Không suy đoán hay tự quét địa chỉ nội bộ.

## 2. Bản đồ đường đi của một lần tải artifact

~~~text
                       mvn clean verify
                              |
                              v
                    Maven / Maven Resolver
                              |
              chọn repository theo POM/settings
                              |
                       có mirror?
                      /          \
                    không          có
                    |             |
                    v             v
             repository gốc   repository manager
                    |             |
                    +------+------+  
                           |
                    xét hostname đích
                           |
             nonProxyHosts có khớp?
                      /          \
                    có            không
                    |               |
                 kết nối trực tiếp   |
                                   v
                             proxy được bật
                                   |
                          repository đích
                                   |
                      tải dependency/plugin/POM
~~~

**Không nhầm hai tầng:**

- **Repository/Mirror** quyết định Maven **đến host nào để lấy artifact**. Ví dụ mọi repository bên ngoài được ánh xạ về `https://packages.corp.example/repository/maven-public/`.
- **Proxy** quyết định kết nối đến **host đích đã chọn** đi trực tiếp hay qua một máy trung gian, ví dụ `proxy.corp.example:8080`.
- **`nonProxyHosts`** là danh sách các hostname **không đi qua proxy**. Nó không chọn repository, không cài chứng chỉ và không tự cho phép truy cập một hostname vốn bị firewall chặn.
- **VPN/DNS/firewall/TLS** vẫn là các điều kiện độc lập. Có `settings.xml` đúng mà chưa kết nối VPN cần thiết thì repository nội bộ vẫn có thể không truy cập được.

Trong nhiều công ty, cách được IT khuyến nghị là Maven dùng **repository manager nội bộ** (Nexus, Artifactory hoặc hệ thống tương đương), còn chính server quản lý repository mới kết nối ra Internet theo chính sách hạ tầng. Máy lập trình viên khi đó có thể **không cần proxy Internet trực tiếp** để tải Maven dependencies, miễn kết nối được repository nội bộ.

## 3. Maven đọc settings.xml ở đâu?

Maven 3 có hai vị trí settings thường gặp:

| Vị trí | Phạm vi | Có nên commit vào Git dự án? |
| --- | --- | --- |
| `<MAVEN_HOME>/conf/settings.xml` | Global settings của bản Maven đã cài | Không; do máy/CI và quản trị hệ thống |
| `<USER_HOME>/.m2/settings.xml` | User settings của người chạy Maven | **Không**; có thể chứa proxy, mirror, thông tin xác thực |
| `pom.xml` của dự án | Mô hình build, dependency, plugin, repository dự án | Có, nhưng **không đặt thông tin đăng nhập vào đây** |
| `.mvn/maven.config` | Tùy chọn Maven CLI gắn với dự án | Có thể commit các tùy chọn an toàn, nhưng không đặt secrets |

Khi tồn tại cả global và user settings, Maven hợp nhất chúng; thông thường thiết lập người dùng có ưu tiên tại phần cấu hình cùng loại. Mặc định, user settings nằm ở `~/.m2/settings.xml` trên Linux/macOS hoặc tương ứng thư mục home của người dùng Windows.

Dùng `-s` để chỉ rõ một user settings file khác mà không sửa POM:

~~~bash
mvn -s /path/to/corporate-settings.xml clean verify
~~~

Trên Windows PowerShell, chẳng hạn:

~~~powershell
mvn -s "$HOME\.m2\settings.xml" clean verify
~~~

`-s` chọn user settings thay thế cho lần chạy đó; nó **không tự tắt global settings**. Nếu phải chỉ rõ global settings có thể dùng `-gs`, nhưng không tự ghi đè cấu hình do IT quản lý.

**Khác biệt phiên bản:** Maven 4 còn hỗ trợ một số project settings tại `.mvn/settings.xml` với giới hạn riêng; đừng lấy quy tắc Maven 4 rồi giả định Maven 3.9 tự đọc user proxy từ đường dẫn này.

## 4. Cú pháp proxies chuẩn trong settings.xml

### 4.1. Một settings.xml có thể đọc và chỉnh sửa

Giả sử doanh nghiệp cho phép outbound qua HTTP proxy `proxy.corp.example` cổng `8080`, không cần xác thực cho máy đã được cấp quyền. Một file **đầy đủ về cú pháp** tại `~/.m2/settings.xml` có thể là:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <proxies>
        <proxy>
            <id>corp-http-proxy</id>
            <active>true</active>
            <protocol>http</protocol>
            <host>proxy.corp.example</host>
            <port>8080</port>
            <nonProxyHosts>localhost|127.0.0.1|corp.example|*.corp.example</nonProxyHosts>
        </proxy>
    </proxies>
</settings>
~~~

Đây là **mẫu cấu hình**, không có tác dụng kết nối đến hostname ví dụ. Bạn phải thay bằng thông số hợp lệ do IT cung cấp trước khi thử trên môi trường thật. Nếu doanh nghiệp không yêu cầu proxy, **không tự thêm `<proxies>` chỉ vì thấy trong bài học**.

Maven đọc các thuộc tính trong `<proxies><proxy>`:

| Trường | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `id` | Định danh riêng của mục proxy | Giúp phân biệt nhiều mục proxy |
| `active` | Chọn có sử dụng cấu hình proxy này không | `true` để bật, `false` để tắt; Maven dùng proxy hoạt động phù hợp protocol |
| `protocol` | Giao thức của proxy, ví dụ `http` | **Không đồng nghĩa** repository URL phải dùng HTTP |
| `host` | Tên DNS hoặc IP của **proxy** | Chỉ hostname, không thêm `https://` hoặc `:8080` vào đây |
| `port` | Cổng của **proxy** | Là số nguyên, ở ví dụ là `8080` |
| `username` / `password` | Xác thực proxy, nếu proxy yêu cầu | Khác tài khoản Maven repository; xem mục bảo mật |
| `nonProxyHosts` | Danh sách hostname kết nối trực tiếp, không dùng proxy | Dùng dấu `|` và wildcard như `*.corp.example` |

Với doanh nghiệp cần HTTPS qua một HTTP proxy, nhiều transport có thể dùng **HTTP CONNECT** để tạo đường hầm TLS đến repository HTTPS. Không đổi repository URL từ HTTPS sang HTTP để “hợp” với `<protocol>http</protocol>`; khả năng hỗ trợ và yêu cầu xác thực phụ thuộc proxy và transport của Maven đang sử dụng. Hãy dùng cấu hình proxy do IT phát hành.

### 4.2. Nhiều proxy và cờ active

Một `settings.xml` có thể chứa nhiều mục `<proxy>`, nhưng điều đó **không có nghĩa Maven thử toàn bộ proxy lần lượt khi một proxy hỏng**. Theo settings model, khi có nhiều mục hoạt động, Maven xét proxy phù hợp giao thức và có thể chọn mục đầu tiên phù hợp. Không nên bật nhiều proxy cạnh tranh cho cùng protocol rồi chờ cơ chế fallback.

Nếu di chuyển giữa mạng văn phòng và mạng cá nhân:

- Tại văn phòng, dùng settings có proxy doanh nghiệp theo tài liệu IT.
- Ngoài văn phòng, dùng settings không có proxy hoặc đặt `<active>false</active>` cho proxy không còn được truy cập.
- Có thể dùng hai file settings riêng và chọn bằng `-s`, thay vì commit file cấu hình mạng cá nhân vào repository.

Một proxy inactive không đóng vai trò “cấu hình dự phòng tự động” cho proxy active.

## 5. nonProxyHosts: tránh đẩy địa chỉ nội bộ qua proxy ngoài

### 5.1. Danh sách ngăn proxy áp dụng theo hostname đích

Ví dụ:

~~~xml
<nonProxyHosts>localhost|127.0.0.1|corp.example|*.corp.example</nonProxyHosts>
~~~

Đọc như sau:

- `localhost`: kết nối đến hostname này không dùng proxy.
- `127.0.0.1`: kết nối đến IP loopback này không dùng proxy.
- `corp.example`: khớp chính tên miền gốc đó.
- `*.corp.example`: mẫu wildcard cho các hostname con như `packages.corp.example` hoặc `git.corp.example`.

Đây là **chuỗi chứa các hostname/pattern**, không phải danh sách URL. Không ghi:

~~~text
https://packages.corp.example/repository/maven-public/
~~~

vào `nonProxyHosts` rồi mong Maven phân tích scheme/đường dẫn. Thay vào đó, dùng tên host `packages.corp.example` hoặc một wildcard được phê duyệt. Cũng không dùng dấu phẩy như separator mặc định nếu muốn cấu hình tương thích với hướng dẫn Maven/JDK: **dấu phân tách chuẩn ở đây là `|`**.

Dấu `*` ở `*.corp.example` là wildcard hostname, không phải cú pháp subnet CIDR. Viết `10.0.0.0/8` trong `nonProxyHosts` không tạo một quy tắc định tuyến IP/subnet tương đương firewall/VPN. Với IP nội bộ cụ thể, kiểm tra hành vi của transport và liệt kê host/IP cần thiết theo hướng dẫn vận hành.

### 5.2. Đừng nhầm host bị loại proxy với host proxy

Mục `<host>proxy.corp.example</host>` là **máy trung gian**. Mục `<nonProxyHosts>packages.corp.example</nonProxyHosts>` là **máy đích** mà Maven muốn tới trực tiếp.

Nếu mirror đang trỏ đến:

~~~text
https://packages.corp.example/repository/maven-public/
~~~

và `*.corp.example` nằm trong `nonProxyHosts`, kết nối từ Maven đến **packages.corp.example** được kỳ vọng không qua proxy (nếu transport áp dụng rule). Máy phải có DNS/VPN/route và quyền truy cập trực tiếp đến host đó. Nếu IT yêu cầu đi qua proxy để vào repository nội bộ, **không đưa hostname đó vào nonProxyHosts**; chính sách mạng thật quyết định.

### 5.3. Các sai lầm khiến rule không có tác dụng

| Sai lầm | Kết quả có thể gặp | Cách sửa |
| --- | --- | --- |
| Ghi URL đầy đủ thay hostname | Pattern không khớp hostname đích | Chỉ ghi host/pattern |
| Dùng dấu phẩy thay `|` | Pattern có thể không được tách đúng theo transport/JDK | Dùng `|` |
| Chỉ ghi `*.corp.example` khi cần khớp cả `corp.example` | Domain gốc có thể không khớp wildcard cho subdomain | Ghi thêm `corp.example` |
| Loại mọi hostname khỏi proxy | Maven không đến được repository Internet khi mạng chặn outbound | Chỉ loại hostname được phép truy cập trực tiếp |
| Đặt `nonProxyHosts` thành subnet CIDR | Không phải cấu hình subnet firewall | Dùng hostname rule phù hợp hoặc cấu hình mạng do IT quản lý |
| Host đích đã bị mirror đổi sang một domain khác | Rule cho repository cũ không còn phù hợp | Xem host **sau khi** mirror được chọn |
| Repository nội bộ thực tế phải qua proxy | Bypass proxy khiến timeout/connection refused | Theo sơ đồ mạng và hướng dẫn IT |

**Quy tắc học tập:** vẽ đường đi đến **host cuối cùng Maven thực sự gọi** rồi mới quyết định có thuộc `nonProxyHosts` hay không.

## 6. Phân biệt proxy và mirror/repository manager doanh nghiệp

Nhiều công ty không cho máy người dùng tải trực tiếp từ Maven Central; thay vào đó, họ dùng một repository manager nội bộ để cache artifact, kiểm soát policy, cấp quyền và thống nhất nguồn.

**Proxy mạng** và **repository mirror** là hai cấu hình khác nhau:

- Proxy có `host` + `port`; trung chuyển kết nối mạng.
- Mirror có `id` + `url` + `mirrorOf`; thay thế **địa chỉ repository Maven** mà Maven sẽ sử dụng.
- Repository manager có thể proxy các repository upstream ở phía **server** nhưng cơ chế đó không đồng nghĩa Maven client phải khai `<proxies>` để đi ra Internet.
- Một mirror duy nhất có thể đại diện nhiều repository thông qua repository manager, nhưng mirror không tự “gộp” nhiều backend; repository manager mới thực hiện việc đó.

### 6.1. Ví dụ settings.xml với proxy và mirror

Giả sử IT cung cấp:

- HTTP proxy: `proxy.corp.example:8080` để ra ngoài.
- Maven repository manager: `https://packages.corp.example/repository/maven-public/`, có thể kết nối trực tiếp qua VPN/LAN.
- Policy: mọi remote repository được Maven yêu cầu sẽ dùng mirror nội bộ.

Một file settings **đầy đủ về cấu trúc**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <proxies>
        <proxy>
            <id>corp-http-proxy</id>
            <active>true</active>
            <protocol>http</protocol>
            <host>proxy.corp.example</host>
            <port>8080</port>
            <nonProxyHosts>localhost|127.0.0.1|corp.example|*.corp.example</nonProxyHosts>
        </proxy>
    </proxies>

    <mirrors>
        <mirror>
            <id>corp-maven</id>
            <name>Corporate Maven Repository Manager</name>
            <url>https://packages.corp.example/repository/maven-public/</url>
            <mirrorOf>external:*</mirrorOf>
        </mirror>
    </mirrors>
</settings>
~~~

Ở đây, `<mirrorOf>external:*</mirrorOf>` chọn các repository **ngoại vi**, loại trừ kiểu localhost và file repository; `<mirrorOf>*</mirrorOf>` còn rộng hơn, phù hợp khi hạ tầng yêu cầu tất cả repository qua một repository manager. `<mirrorOf>central</mirrorOf>` chỉ thay `central`. **Chọn theo policy IT**, không tự đổi `mirrorOf` để tìm đường vòng khi repository nội bộ từ chối.

Vì mirror ví dụ có hostname `packages.corp.example` và `*.corp.example` nằm trong `nonProxyHosts`, Maven kết nối **trực tiếp** đến repository manager (giả sử DNS/VPN cho phép), mặc dù proxy Internet vẫn được khai báo. Nếu không có mirror và Maven đến một repository ngoài, hostname đó thường không khớp `nonProxyHosts` và có thể dùng proxy.

**Lưu ý:** thay một repository URL bằng mirror không bảo đảm artifact đã có ở đó; repository manager phải cho phép hoặc có khả năng lấy đúng dependency/plugin cần thiết. Nếu mirror chặn một dependency theo policy, đó là quyết định quản trị, không phải lỗi cần né tránh bằng URL ngẫu nhiên.

### 6.2. Chứng thực repository nằm ở servers, không phải proxy

Nếu `https://packages.corp.example/...` yêu cầu tài khoản, Maven tra `<servers>` theo **server id khớp với id repository/mirror được sử dụng**.

Ví dụ, **chỉ là đoạn XML thêm bên trong phần tử `<settings>` ở trên**, khi hệ thống CI đã cấp các biến môi trường tương ứng:

~~~xml
<servers>
    <server>
        <id>corp-maven</id>
        <username>${env.CORP_REPO_USER}</username>
        <password>${env.CORP_REPO_PASSWORD}</password>
    </server>
</servers>
~~~

`corp-maven` ở `<server><id>` phải khớp `<mirror><id>corp-maven</id>` trong mẫu này. Nếu một mirror có id khác, Maven không nhất thiết gắn credential vào đúng server. `<servers>` xác thực **repository manager**, không xác thực máy `proxy.corp.example`.

Maven hỗ trợ interpolation `${env.NAME}` trong `settings.xml`; các biến môi trường **phải được cung cấp thực sự** cho tiến trình Maven, thường qua secret store của CI hoặc cơ chế đăng nhập được quản trị. Không để tệp với biến chưa được định nghĩa rồi kết luận username/password đã đúng.

## 7. Proxy có xác thực: username/password và bảo vệ bí mật

Nếu proxy đòi xác thực, hai trường liên quan nằm **bên trong chính phần tử `<proxy>`**:

~~~xml
<username>${env.CORP_PROXY_USER}</username>
<password>${env.CORP_PROXY_PASSWORD}</password>
~~~

Đoạn trên cần được đặt vào `<proxy>` tương ứng; nó **không phải settings.xml độc lập**. Các tên biến chỉ minh họa cách truyền thông tin, không có username/password thật được đưa vào bài.

Phân biệt hai nhóm thông tin:

| Nhóm | Cấu hình | Thường dùng cho |
| --- | --- | --- |
| Proxy authentication | `proxies/proxy/username` và `password` | Trả lời yêu cầu proxy, ví dụ HTTP `407` |
| Repository authentication | `servers/server` với `id` khớp repository/mirror | Trả lời yêu cầu repository manager, ví dụ `401` |
| VPN/SSO/network access | Client VPN, danh tính thiết bị, chính sách doanh nghiệp | Quyết định có DNS/route/quyền truy cập vào hạ tầng nội bộ |
| TLS trust | Truststore/JDK hoặc cơ chế CA được IT cấp | Kiểm tra chuỗi chứng chỉ server/proxy TLS |

**Không đặt mật khẩu vào `pom.xml`, file Git, `.mvn/maven.config`, URL chứa user:password hoặc log debug.** `settings.xml` là tệp riêng của người dùng/máy CI; giới hạn quyền đọc file và cấp thông tin từ secret store khi được phép.

Maven 3 có cơ chế mã hóa mật khẩu bằng `settings-security.xml` và các lệnh mã hóa, nhưng **đây không thay thế hoàn toàn hệ thống quản lý secrets**; tài liệu Maven 3 nhấn mạnh mức bảo vệ không đủ để chống lại người có quyền đọc các thành phần liên quan. Không tự tạo các khóa giả để làm ví dụ, không in mật khẩu lên command line. Với hệ thống mới, dùng cơ chế secrets chính thức của công ty.

**Lưu ý môi trường:** biến môi trường cũng là dữ liệu nhạy cảm; trên máy/CI có quyền truy cập không phù hợp, chúng có thể lộ qua log, dump hoặc tiến trình. Hạn chế log và không chia sẻ output chứa credential.

## 8. Kiểm chứng settings đang có hiệu lực: không đoán từ tên file

### 8.1. Xem Maven/JDK đang được gọi

~~~bash
mvn -version
~~~

Lệnh này cho biết Maven, Java và đường dẫn runtime. Nhưng nó **không chứng minh Maven đã truy cập một repository qua proxy** vì chỉ xem phiên bản thường không cần tải artifact.

### 8.2. Xem effective settings

Từ một dự án Maven hợp lệ:

~~~bash
mvn -s /path/to/corporate-settings.xml help:effective-settings
~~~

Help Plugin có goal `effective-settings` để hiển thị settings sau khi hợp nhất global và user settings. Hãy kiểm tra `proxies`, `mirrors`, `servers/id` và `active` có khớp ý định không. Theo mặc định, goal này **ẩn password**; **không bật `showPasswords=true`** và không dán toàn bộ output lên diễn đàn công khai.

Lưu ý: lần đầu gọi `help:effective-settings` có thể cũng phải **tải Maven Help Plugin từ repository**. Nếu mạng đang hỏng, nó có thể thất bại trước khi in được effective settings. Khi đó hãy kiểm tra tệp XML, DNS/VPN và cấu hình proxy trước; đừng coi việc goal không chạy là bằng chứng `settings.xml` không được đọc.

### 8.3. Thử tải artifact thật, thay vì chỉ chạy validate

Lệnh `mvn validate` đôi khi có thể thành công mà **chưa cần mạng** nếu không có goal cần tải. Để thử kết nối repository với dependency có thật, một cách thông dụng là:

~~~bash
mvn -B -ntp -U dependency:get -Dartifact=org.apache.commons:commons-lang3:3.14.0
~~~

Goal `dependency:get` có thể cần tải chính Maven Dependency Plugin và artifact được yêu cầu, nên nó là kiểm tra gần nhu cầu thật hơn `mvn -version`. **Nhưng nếu mọi thứ đã có trong cache cục bộ, BUILD SUCCESS không chứng minh vừa kết nối được mạng.** Hãy xem log tải artifact nếu cần xác minh network thực sự.

Nếu dùng file settings riêng:

~~~bash
mvn -B -ntp -s /path/to/corporate-settings.xml -U dependency:get -Dartifact=org.apache.commons:commons-lang3:3.14.0
~~~

`-U` yêu cầu cập nhật theo chính sách Maven (đặc biệt với SNAPSHOT) nhưng không buộc tải lại mọi release đã cache; không xóa toàn bộ `~/.m2/repository` để “kiểm tra proxy”, vì làm mất cache chung và có thể ảnh hưởng công việc khác.

## 9. Ví dụ Java 17 + Maven có thể chạy để kiểm thử đường tải plugin/dependency

Phần mạng và `settings.xml` là nội dung chính của bài. Ví dụ này chỉ cung cấp **một dự án Maven nhỏ, chạy được** để bạn phân biệt “Maven kết nối tới repository khi build” với “chương trình Java chạy sau build”.

Tạo cấu trúc:

~~~text
network-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/network/NetworkBuild.java
    └── test/java/vn/example/network/NetworkBuildTest.java
~~~

### 9.1. POM hoàn chỉnh

File `network-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>network-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ví dụ chọn JUnit chỉ cho test. Ứng dụng khi chạy **không gọi HTTP**; network được Maven dùng để tải dependency/plugin trong giai đoạn build nếu cache chưa có. Một build pass chứng minh môi trường đã giải quyết được artifact theo cấu hình hiện tại, không phải mọi host Internet đều truy cập được.

### 9.2. Java source

File `network-demo/src/main/java/vn/example/network/NetworkBuild.java`:

~~~java
package vn.example.network;

public final class NetworkBuild {
    private NetworkBuild() {
    }

    public static String message() {
        return "Maven network build OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

File `network-demo/src/test/java/vn/example/network/NetworkBuildTest.java`:

~~~java
package vn.example.network;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class NetworkBuildTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Maven network build OK", NetworkBuild.message());
    }
}
~~~

Hai file khớp package `vn.example.network` và biên dịch được với JDK 17. JUnit Jupiter 5 chạy qua Surefire Plugin.

### 9.3. Chạy Maven bằng settings phù hợp

Từ thư mục `network-demo`, **Linux/macOS**:

~~~bash
mvn -B -ntp -s "$HOME/.m2/settings.xml" clean verify
java -cp target/network-demo-1.0.0.jar vn.example.network.NetworkBuild
~~~

**Windows PowerShell**:

~~~powershell
mvn -B -ntp -s "$HOME\.m2\settings.xml" clean verify
java -cp target\network-demo-1.0.0.jar vn.example.network.NetworkBuild
~~~

Nếu settings, JDK, repository và dependency đều hợp lệ, Maven kết thúc với `BUILD SUCCESS`, báo **1 test**, không fail. Lệnh chạy Java phía sau in **chính xác**:

~~~text
Maven network build OK
~~~

Nếu mạng công ty hiện không cho phép URL ví dụ `*.corp.example`, trước tiên phải thay `settings.xml` bằng địa chỉ thực tế được cấp. **Không yêu cầu chương trình Java truy cập một dịch vụ nội bộ** để làm bài; chỉ build Maven để kiểm tra đường tải artifacts.

### 9.4. Đọc log để xác định Maven đã dùng endpoint nào

Một lần build đầu có thể cho thấy Maven tải plugin và JUnit theo cấu hình. Khi dùng mirror, log Maven hoặc debug thường cho biết repository đã được thay bằng mirror có id như `corp-maven`. Thông báo tải artifact có thể khác tùy phiên bản transport, loại plugin và chính sách log.

Nếu build thất bại, hãy tách ba tình huống:

- Không giải quyết được **plugin** (Compiler, Surefire, Dependency Plugin) trước khi chạy mã: chưa có nghĩa Java sai; kiểm tra repository/mirror/proxy.
- Tải được plugin nhưng **dependency** không tìm thấy: kiểm tra tọa độ artifact, phiên bản, quyền mirror và cache nội bộ.
- Tải được dependency và biên dịch/test thất bại: có thể là lỗi mã Java/JUnit/POM, không phải đường truyền.

Cơ chế `settings.xml` dùng cho Maven để tải artifacts không tự truyền HTTP proxy cho **ứng dụng Java bạn vừa chạy**. Một chương trình Java tự gọi HTTP sẽ cần cấu hình client/JVM network riêng theo thư viện sử dụng.

## 10. Phân tích lỗi doanh nghiệp theo tầng nguyên nhân

| Triệu chứng trong Maven/terminal | Tầng cần kiểm tra | Hướng xử lý an toàn |
| --- | --- | --- |
| `407 Proxy Authentication Required` | **Proxy** từ chối xác thực | Kiểm tra host/port/protocol, tài khoản proxy được IT cấp, tình trạng SSO/proxy |
| `401 Unauthorized` khi gọi repository nội bộ | **Repository manager** yêu cầu đăng nhập | Kiểm tra `<servers><server><id>` có khớp mirror/repository id, quyền truy cập tài khoản |
| `403 Forbidden` từ repository nội bộ | Quyền hoặc policy trên repository | Xác nhận tài khoản có quyền artifact, kiểm tra policy/quarantine với admin |
| `UnknownHostException: proxy.corp.example` | DNS của proxy, VPN hoặc hostname sai | Kiểm tra DNS/VPN và hostname được cấp |
| `UnknownHostException: packages.corp.example` | DNS của repository đích | Kiểm tra mirror URL, VPN, DNS nội bộ |
| `Connection timed out` | Route/firewall, proxy bypass không hợp lệ hoặc mạng đứt | Vẽ đường đi thật, xác nhận host thuộc `nonProxyHosts` hay phải qua proxy |
| `Connection refused` | Dịch vụ không nghe cổng, proxy/host sai, policy | Xác nhận port và trạng thái endpoint qua IT |
| `PKIX path building failed` | Chuỗi chứng chỉ TLS/JDK truststore | Kiểm tra CA doanh nghiệp, chứng chỉ máy chủ và JDK được dùng; không bỏ xác minh TLS |
| `SSLHandshakeException` | TLS protocol, certificate hoặc interception | So sánh truststore/JDK và yêu cầu proxy TLS với quản trị viên |
| `Could not transfer artifact` | Thông báo tổng quát của Resolver | Đọc **nguyên nhân lồng bên trong**: 401, 407, DNS, timeout, TLS hay 404 |
| `404 Not Found` | Artifact/version không có ở repository hiện chọn | Kiểm tra groupId/artifactId/version, mirror và quy tắc repository manager |
| `429 Too Many Requests` | Rate limit repository/proxy | Kiểm tra giới hạn/caching với IT, tránh lặp truy vấn dồn dập |
| `502/503/504` từ proxy/repo manager | Gateway hoặc dịch vụ upstream lỗi | Kiểm tra trạng thái dịch vụ, liên hệ quản trị, không sửa POM ngẫu nhiên |
| Maven chạy offline rồi báo artifact unavailable | `-o` hoặc `<offline>true</offline>` | Bỏ offline nếu chính sách cho phép, dùng repository hợp lệ |
| Browser truy cập được nhưng Maven không | Browser dùng PAC/SSO/truststore khác Maven | Kiểm tra proxy Maven và JDK, đừng suy luận cấu hình browser tự áp dụng |
| `mvn -version` hoạt động nhưng `mvn test` lỗi mạng | Xem phiên bản không tải artifact | Thử goal thực sự giải quyết dependency/plugin |

**Mã phản hồi 401/403 và 407 là tín hiệu hữu ích:** 407 thường đến từ **proxy**, còn 401/403 khi gọi repository manager phản ánh xác thực/quyền của **repository**. Tuy nhiên vẫn cần xem log để biết hostname nào thực sự trả mã; một hệ thống gateway doanh nghiệp có thể trả lỗi theo cách khác.

### 10.1. Debug có kiểm soát

Khi log thường chưa đủ, có thể dùng `-e` (stack trace) hoặc `-X` (debug) khi được phép:

~~~bash
mvn -B -ntp -e clean verify
mvn -B -ntp -X dependency:tree
~~~

Không chạy hai lệnh chỉ để tạo thật nhiều log; chọn lệnh đang thất bại và đọc **nguyên nhân đầu tiên có nghĩa**. Log debug có thể lộ host nội bộ, đường dẫn cục bộ, property hoặc metadata nhạy cảm. **Không** gửi nguyên log hoặc effective settings chứa thông tin hạ tầng lên công khai. Không bật `-DshowPasswords=true` trong Help Plugin.

### 10.2. Tìm hiểu proxy theo kiểm thử đơn giản

Câu hỏi đầu tiên khi xử lý lỗi là: “Maven đang gọi **host nào** và theo route nào?”

1. Xác nhận `mvn -version`, tên dự án và `settings.xml` đang được chọn.
2. Kiểm tra `<mirror>`: host repository cuối cùng là Maven Central hay repository manager nội bộ?
3. Kiểm tra host đó có khớp `nonProxyHosts` không. Nếu có, Maven dự kiến đi trực tiếp; nếu không, xem proxy active/phù hợp.
4. Kiểm tra VPN, DNS và mạng được cấp quyền; trình duyệt dùng PAC có thể khác Maven.
5. Phân biệt lỗi HTTP auth, TLS, DNS, timeout hay 404 qua phần nguyên nhân của log.
6. Thay đổi **một cấu hình một lần**, chạy lại lệnh nhỏ nhất đã lỗi và đối chiếu.
7. Nếu doanh nghiệp quản lý proxy/CA/repository manager tập trung, mở yêu cầu hỗ trợ cho đội IT với thông tin **đã loại bỏ secrets**.

Không dùng việc tạm bỏ proxy hoặc chuyển repository sang URL không được phê duyệt làm một “cách chữa” lâu dài.

## 11. SSL/TLS và chứng chỉ nội bộ: đừng tắt bảo mật để build

Một tình huống phổ biến là Maven kết nối được hostname nhưng báo:

~~~text
PKIX path building failed: unable to find valid certification path to requested target
~~~

Điều này thường cho thấy JVM chạy Maven chưa tin cậy chuỗi chứng chỉ của repository hoặc TLS interception proxy doanh nghiệp. **Không phải dấu hiệu cần đổi tất cả URL từ HTTPS sang HTTP.**

Cách xử lý có trách nhiệm:

- Xác định Maven đang chạy bằng **JDK nào** qua `mvn -version`; IDE và terminal có thể dùng JDK/truststore khác nhau.
- Kiểm tra endpoint HTTPS và chuỗi chứng chỉ được tổ chức cấp; nếu có CA nội bộ, lấy chứng chỉ/truststore từ **nguồn chính thức**.
- Yêu cầu IT cung cấp cách cấu hình truststore cho JDK/Maven hoặc image CI tương ứng. Với một số cấu hình JVM, có thể truyền các system properties `javax.net.ssl.trustStore` và `javax.net.ssl.trustStorePassword`, nhưng vị trí và cách quản lý chúng phải theo chính sách bảo mật của tổ chức.
- Sau khi cập nhật truststore đúng cách, chạy lại lệnh có tải artifact và kiểm tra lỗi gốc đã biến mất.

**Tránh** thêm các cờ vô hiệu hóa kiểm tra chứng chỉ (ví dụ các cấu hình “insecure/allowall” của transport), cài CA từ nguồn không xác minh hoặc gửi truststore password qua mã nguồn/terminal history. Những biện pháp ấy có thể che lỗi MITM và vi phạm yêu cầu bảo mật của doanh nghiệp.

## 12. Browser proxy, HTTP_PROXY, MAVEN_OPTS và Maven settings: không giống nhau

Có bốn nơi thường gây nhầm:

1. **Trình duyệt hoặc proxy PAC do hệ điều hành phát hành:** có thể tự chọn proxy theo URL. Maven chạy trong JVM và transport của nó **không nhất thiết tự dùng cùng cấu hình browser/PAC**.
2. **Biến môi trường như `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`:** một số CLI đọc trực tiếp, nhưng đừng giả định mọi Maven transport/JDK luôn diễn giải chúng giống `curl` hay `git`.
3. **`MAVEN_OPTS` hoặc `.mvn/jvm.config`:** chứa các **tham số JVM chạy Maven**, chẳng hạn heap hoặc system properties Java. Một số Java networking clients có thể đọc `http.proxyHost`/`https.proxyHost`, nhưng khả năng và mức ưu tiên với Maven Resolver phụ thuộc transport; đây **không phải phương án mặc định thay cho `settings.xml`**.
4. **`settings.xml`:** cơ chế Maven được tài liệu chính thức hướng dẫn để chọn proxy/mirror và credentials liên quan đến kho artifact. Đây là điểm xuất phát phù hợp khi khắc phục lỗi tải plugin/dependency.

Nếu công ty cấp một PAC URL hoặc script proxy dùng cho browser, **không copy URL PAC vào `<proxy><host>`**. Maven cần hostname và port của proxy thực hoặc cơ chế tích hợp do tổ chức hỗ trợ. Nếu proxy dùng cơ chế NTLM/SSO phức tạp, tài liệu Maven lưu ý hỗ trợ NTLM **không được bảo đảm như con đường chuẩn**; hãy yêu cầu IT hướng dẫn một kết nối/transport được hỗ trợ thay vì đoán phương án vượt qua xác thực.

Đồng thời, cấu hình proxy trong Maven để tải dependency **không có nghĩa** một ứng dụng Java chạy bằng `java -jar` hay một JVM do test plugin fork tự động kế thừa toàn bộ cấu hình HTTP của Maven. Mỗi tiến trình/thư viện mạng có thể cần cấu hình riêng.

## 13. CI, Docker và quy trình nhóm an toàn

Trong một nhóm phát triển, thường nên chuẩn hóa **cách cung cấp settings** thay vì commit một bản settings chứa thông tin mạng và bí mật.

### 13.1. Trên máy lập trình viên

- Dùng user settings tại `~/.m2/settings.xml` theo hướng dẫn được cấp.
- Dùng mirror/repository manager nội bộ nếu công ty yêu cầu.
- Dùng VPN/DNS/certificate đúng quy trình, bảo vệ quyền đọc settings.
- Không commit `.m2`, mật khẩu hoặc bản export log có thông tin nội bộ vào Git.

### 13.2. Trên CI runner

CI nên cấp JDK, Maven/Maven Wrapper và **settings hợp lệ riêng cho runner**, với credential từ secret store. Ví dụ lệnh build trên runner Unix sau khi hạ tầng đã tạo file settings ở đường dẫn nội bộ:

~~~bash
./mvnw -B -ntp -s "$HOME/.m2/settings.xml" clean verify
~~~

Lệnh trên **không tự tạo settings**; nó chỉ tham chiếu file đã tồn tại. Một container có HOME, DNS, proxy network và truststore khác máy developer; nếu copy POM vào container nhưng không cấp settings/JDK/network phù hợp, việc build thất bại là điều có thể dự đoán.

Ở CI, hãy xác nhận:

- Repository URL và `mirrorOf` phù hợp chính sách, không truy vấn thẳng Maven Central khi bắt buộc qua repository manager.
- Host repository nội bộ thuộc `nonProxyHosts` **chỉ khi runner được phép kết nối trực tiếp**; không suy ra từ cấu hình laptop.
- Proxy credentials, repository credentials và cert/truststore được cấp qua kênh bí mật; giới hạn quyền truy cập.
- File settings không bị đưa vào Docker image phát hành, artifact hay build log.
- Log kết thúc `BUILD SUCCESS` và các test thật sự chạy, thay vì bỏ qua test để che lỗi mạng.

### 13.3. Thử nghiệm theo từng môi trường

| Môi trường | Kiểu kết nối thường gặp | Vấn đề cần phân biệt |
| --- | --- | --- |
| Laptop ở nhà | Internet trực tiếp hoặc VPN | Proxy công ty đang active gây timeout khi chưa vào VPN |
| Laptop trong LAN công ty | Proxy hoặc repository manager nội bộ | Host nào được bypass qua `nonProxyHosts` |
| CI trong mạng nội bộ | Repository manager/CA nội bộ | Settings và truststore được gắn vào runner đúng chưa |
| CI trên cloud | Proxy egress, tunnel hoặc repository gateway được duyệt | Firewall, DNS, CA và chính sách truy cập khác máy nội bộ |
| Container build | Network namespace/Home/JDK riêng | `~/.m2/settings.xml` của host không tự có trong container |

Không nên sao chép nguyên một cấu hình mạng từ laptop sang mọi runner. Mỗi môi trường phải tuân thủ chính sách proxy/repository/credential tương ứng.

## 14. Bài tập thực hành có thể tự kiểm tra

### Bài tập A — Đọc cấu hình proxy

Từ XML mục 4, hãy trả lời: hostname proxy là gì? Port bao nhiêu? Host `packages.corp.example` có được đặt ngoài proxy theo `nonProxyHosts` không? Host `repo.maven.apache.org` có khớp pattern ấy không? Giải thích bằng hostname, không chỉ nói “nội bộ” hoặc “bên ngoài”.

**Đáp án hướng dẫn:** proxy `proxy.corp.example:8080`; `packages.corp.example` khớp `*.corp.example`; `repo.maven.apache.org` không khớp pattern đó. Đường đi cuối cùng còn phụ thuộc mirror và khả năng proxy/transport thực tế.

### Bài tập B — Kết hợp mirror và proxy

Đọc settings mục 6 rồi vẽ đường đi khi Maven tìm JUnit từ Maven Central. Vì `mirrorOf=external:*`, repository yêu cầu được chuyển đến `packages.corp.example` trong mô hình này; nếu host đó nằm trong `nonProxyHosts` thì Maven kết nối trực tiếp, **không cần proxy Internet** cho kết nối đó (theo giả định hạ tầng của bài).

Nếu IT nói repository nội bộ **phải** đi qua proxy, bạn sẽ sửa gì? Cần điều chỉnh rule bypass cho host nội bộ theo chỉ dẫn IT; **không** đổi `mirrorOf` hoặc giảm TLS tùy ý.

### Bài tập C — Hai loại tài khoản

Trong một tình huống có proxy yêu cầu đăng nhập và mirror cũng yêu cầu đăng nhập, chỉ ra hai nơi giữ credentials tương ứng. Giải thích vì sao `<server><id>corp-maven</id>` khớp id mirror nhưng không thay username/password của proxy.

### Bài tập D — Build Maven có dependency

Dựng `network-demo` và chạy `mvn clean verify` với settings phù hợp mạng của bạn. Kiểm tra file `target/network-demo-1.0.0.jar`, report test và stdout của ứng dụng. Sau đó mô tả: bước nào có thể cần Internet/repository? Bước chạy `java -cp` có cần proxy không trong ví dụ này?

### Bài tập E — Phân biệt lỗi

Cho bốn lỗi `407`, `401`, `UnknownHostException` và `PKIX path building failed`, nối mỗi lỗi với tầng thường gặp: proxy auth, repository auth, DNS/VPN và TLS trust. Nêu đúng một thay đổi/kiểm tra có cơ sở cho mỗi trường hợp, tránh “thử tắt SSL” hay “xóa toàn bộ cache”.

### Bài tập F — Hiểu giá trị của nonProxyHosts

Thử hai tình huống mô phỏng trên giấy (không yêu cầu thay mạng doanh nghiệp thật):

1. Mirror host nội bộ có thể truy cập trực tiếp. Cấu hình `nonProxyHosts` nên khớp hostname đó.
2. Mirror host nội bộ bắt buộc qua proxy theo IT. Cấu hình `nonProxyHosts` **không** nên khớp hostname đó.

Giải thích vì sao cấu hình đúng ở mạng A có thể sai ở mạng B.

### Bài tập G — Phân tích tính xác thực của một lần build

Lệnh `mvn validate` trả `BUILD SUCCESS` trong một dự án đã có cache. Có thể kết luận proxy hoạt động không? **Không.** Hãy mô tả một phép thử cần Maven giải quyết artifact/plugin và nêu giới hạn: nếu artifact đã cache, thành công chưa chứng minh vừa truy cập mạng.

## 15. Checklist hoàn thành và cách ghi nhớ

Bạn đã nắm vững chủ đề khi có thể giải thích không nhìn tài liệu:

- `settings.xml` của Maven 3.9 đặt tại user home hoặc Maven installation và vì sao không commit credential vào POM.
- `proxies/proxy` có `id`, `active`, `protocol`, `host`, `port` và tùy chọn xác thực.
- `nonProxyHosts` dùng **host/pattern**, phân tách bằng `|`, hỗ trợ wildcard hostname; không phải URL list, firewall rule hay subnet CIDR.
- Mirror chọn **repository đích**; proxy định tuyến **kết nối** đến đích đó; `nonProxyHosts` có thể khiến host đã mirror được kết nối trực tiếp.
- `<servers>` dùng credentials repository theo id, khác với credentials của proxy.
- Browser/PAC, `HTTP_PROXY`, Maven settings, JVM networking và VPN không tự động là một cấu hình duy nhất.
- 407, 401/403, DNS timeout và PKIX thường thuộc những tầng lỗi khác nhau và cần kiểm tra khác nhau.
- Có thể dùng `help:effective-settings`, log build có kiểm soát và một goal tải dependency thực sự để kiểm chứng; cache làm giới hạn tính kết luận của một lần build.
- Giữ HTTPS và xác minh CA đúng chính sách doanh nghiệp; không tắt TLS, không công khai secrets/log nội bộ.
- Chạy được dự án `network-demo` và phân biệt việc Maven tải dependency trong build với việc ứng dụng Java chạy sau build.

Mục tiêu thực tế không phải “làm Maven vượt qua mạng doanh nghiệp bằng mọi giá”, mà là **đi đúng tuyến repository/proxy được cấp quyền, bảo toàn bảo mật và biết dùng bằng chứng để xác định đúng tầng lỗi**.

## 16. Tài liệu Maven chính thức

- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): cấu trúc settings, `proxies`, `servers`, `mirrors`, đường dẫn settings và interpolation từ environment variables.
- [Apache Maven — Configuring a Proxy](https://maven.apache.org/guides/mini/guide-proxies.html): `active`, `protocol`, xác thực proxy, `nonProxyHosts` và lưu ý NTLM.
- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html): `mirrorOf`, `*`, `external:*` và repository manager nội bộ.
- [Apache Maven — Configuring Maven](https://maven.apache.org/configure): phân biệt `settings.xml`, `MAVEN_OPTS`, `.mvn/jvm.config` và các phương thức cấu hình.
- [Apache Maven Help Plugin — effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html): hiển thị settings đang có hiệu lực và mặc định ẩn password.
- [Apache Maven 3 — Password Encryption](https://maven.apache.org/guides/mini/guide-encryption.html): cơ chế mã hóa mật khẩu Maven 3 và các giới hạn bảo mật.
