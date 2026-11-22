# Kiểm soát nguồn artifact, mirror và kho Maven nội bộ tin cậy

## 1. Vấn đề: build thành công không có nghĩa dependencies đáng tin

Một project Java có thể khai báo chính xác:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.17.0</version>
</dependency>
~~~

Nhưng để tạo classpath, Maven phải tải một JAR và POM tương ứng từ đâu đó. Nếu các repository được phép không kiểm soát, build có thể nhận **cùng GAV nhưng bytes khác**, phụ thuộc một kho đã bị takeover, hoặc vô tình dùng một package công khai có tên trùng với internal library. Build plugins còn đặc biệt nhạy cảm: Maven có thể **thực thi code plugin** trước khi hoàn tất build.

**An toàn phụ thuộc** không chỉ có “pin version”; cần quản lý **nguồn tải**, **tính toàn vẹn**, **provenance**, **quyền phát hành**, **cache**, **toolchain** và **quy trình CI**. Các mục tiêu của bài:

1. Hiểu Maven local/remote repositories, thứ tự resolver, parent/BOM/transitive metadata.
2. Phân biệt `repositories`, `pluginRepositories`, `mirrors`, `servers` và `distributionManagement`.
3. Cấu hình `settings.xml` để route qua một Maven repository manager nội bộ được phê duyệt.
4. Hiểu `mirrorOf=central`, `*`, `external:*`, `external:http:*`, exclusions và precedence.
5. Giữ chặn external HTTP từ Maven 3.8.1, TLS, checksum/signature và credential scope.
6. Phòng dependency confusion, repository poisoning, plugin supply-chain và namespace collisions.
7. Xây lab Maven 3.9+/Java 17/JUnit 5 chạy thật mà không cần một repository server riêng.
8. Kiểm tra clean resolution/CI policy và xử lý lỗi mà không bypass bảo mật.

**Kết luận quan trọng:** mirror làm Maven hướng requests tới một endpoint, nhưng **endpoint đó chỉ đáng tin khi tổ chức quản trị upstreams, quyền upload, namespace, scan/quarantine và tính bất biến**.

## 2. Maven tìm artifact như thế nào?

Ví dụ một lần build:

~~~text
Git checkout + pom.xml
     |
     v
Maven builds effective project model
     |
     +-- project dependencies
     +-- parent POMs
     +-- imported BOMs
     +-- transitive dependencies
     +-- build plugins + plugin dependencies
     +-- build extensions / descriptors
     |
     v
Maven Resolver
     |
     +-- local repository (cache)
     |
     +-- remote repository list
            |
            v
         mirror selection
            |
            v
     approved internal HTTPS group
            |
            +-- hosted internal releases
            +-- hosted snapshots (nếu policy cho phép)
            +-- vetted third-party artifacts
            +-- approved Maven Central proxy
~~~

Maven thường dùng local repository dưới `${user.home}/.m2/repository`. Nó lưu JARs, POMs, plugin artifacts và metadata. Nếu một artifact đã có và được resolver coi là dùng được, Maven có thể không download lại. **Vì vậy build xanh trên laptop không chứng minh một CI agent sạch sẽ dùng đúng remote source**.

Maven mặc định biết Maven Central qua Super POM. Nhưng active profiles, project/parent POMs và dependency POMs có thể bổ sung remote repository contexts. Chỉ nhìn `pom.xml` hiện tại là chưa đủ để kết luận toàn bộ nguồn tải.

### 2.1. GAV là định danh, không phải chứng nhận nguồn

Một artifact thường có Maven coordinates:

~~~text
groupId:artifactId:version[:type[:classifier]]
~~~

Với Commons Lang:

~~~text
org.apache.commons:commons-lang3:3.17.0:jar
~~~

Maven repository layout tương ứng:

~~~text
org/apache/commons/commons-lang3/3.17.0/
    commons-lang3-3.17.0.pom
    commons-lang3-3.17.0.jar
~~~

GAV không chứa host URL hoặc checksum. Hai remote repositories trả khác bytes dưới cùng GAV sẽ làm nguồn không còn đáng tin/tái hiện, dù project POM pin version. Bảo vệ phải đi từ repository governance đến CI verification.

### 2.2. Gồm cả parent POM, BOM và build plugins

Không chỉ thư viện runtime:
- Parent POM có thể định nghĩa repository, plugin, profile và build config.
- BOM mang managed dependency versions.
- Transitive dependency POM có thể mang những repository definitions mà author hiện tại không để ý.
- Maven plugins thực thi code trong build environment, có thể đọc filesystem và environment variables.
- Build extensions có thể thay đổi hành vi Maven trước các phases thông thường.

Một policy chỉ chặn dependency runtime mà bỏ plugin resolution sẽ chưa đủ.

## 3. Năm cơ chế Maven cần phân biệt

| Khái niệm | Khai báo phổ biến | Dùng cho |
| --- | --- | --- |
| Project repository | `<repositories>` ở POM/settings profile | Tải dependencies |
| Plugin repository | `<pluginRepositories>` ở POM/settings profile | Tải Maven plugins |
| Mirror | `<mirrors>` trong settings | Thay URL/endpoint cho repository request match |
| Server credentials | `<servers>` trong settings | Auth theo ID của repository/mirror endpoint |
| Publication target | `<distributionManagement>` trong POM | Nơi `mvn deploy` upload artifact |

**`distributionManagement` là điểm xuất bản, không phải download mirror.**

Một POM có:

~~~xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.invalid/repository/releases/</url>
    </repository>
</distributionManagement>
~~~

không ép project tải mọi dependency từ URL này. Muốn kiểm đường resolution cần settings/mirrors/repository manager.

Một POM có `<repositories>` cũng không tự khóa mọi plugin download; Maven sử dụng `pluginRepositories` cho build plugins.

## 4. Thứ tự các remote repository trong Maven

Theo tài liệu *Setting up Multiple Repositories*, các nguồn cấu hình remote repositories được xét theo nhóm:

1. **Effective settings:** global settings và user settings, gồm các active profiles.
2. **Effective build POM:** current project POM, parent POMs, Super POM.
3. **Effective POMs dọc dependency path:** transitive artifact descriptors.

Trước khi tạo kết nối tải artifact, Maven áp **mirrors** theo configuration.

Điều này có ba hệ quả:

- Một dependency POM có thể góp repository context, không chỉ POM hiện tại.
- Đăng ký một repository trong POM không có nghĩa Maven bỏ mọi repository còn lại.
- Corporate settings có thể áp mirror cho nhiều repository IDs khác nhau, kể cả những repository đến từ transitive descriptors.

Dùng:

~~~bash
mvn help:effective-pom -Dverbose
mvn help:effective-settings
mvn dependency:tree
~~~

để kiểm model/resolution. **Cẩn thận:** effective-settings có thể chứa thông tin xác thực/server config. Không công khai full output từ CI có secrets.

Repository IDs cần duy nhất theo ngữ cảnh: ID trùng trong effective settings hoặc POM có thể gây lỗi/overwrite theo quy tắc Maven; ID cũng liên quan đến local metadata, mirror matching và credential lookup. Không đổi IDs tùy tiện để “thử may”.

## 5. Mirror là gì, và không phải là gì?

Mirror dùng để thay một remote repository bằng endpoint khác khi Maven chọn repository resolution:

~~~xml
<mirrors>
    <mirror>
        <id>corp-maven-group</id>
        <mirrorOf>central</mirrorOf>
        <url>https://repo.example.invalid/repository/maven-approved/</url>
    </mirror>
</mirrors>
~~~

Đây là fragment của **Maven `settings.xml`**, không phải `pom.xml`. Host `.invalid` là minh họa **không tồn tại**, không dùng trực tiếp để chạy build.

- `id=corp-maven-group`: identity của endpoint mirror.
- `mirrorOf=central`: match repository ID `central`.
- `url`: nơi Maven thật sự kết nối nếu mirror match.

Nếu kho mirror cần read authentication, `<server><id>corp-maven-group</id>` trong settings cần tương ứng. **ID `central` không tự được dùng làm credential ID của mirror mới**.

Mirror **không tự tải, quét hay tổng hợp tất cả Maven Central**. Repository manager nội bộ phải được server administrator cấu hình làm proxy/group/hosted repos, cùng policy kiểm duyệt.

## 6. Cú pháp `mirrorOf` và vùng phủ thực tế

| Selector | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| `central` | Chỉ repository ID `central` | Không bắt repository ID khác |
| `*` | Tất cả repositories theo mirror matching | Có thể redirect cả local file/localhost test repos |
| `external:*` | Ngoại trừ localhost và `file://` repositories | Local/file repositories không bị redirect |
| `external:http:*` | External HTTP repositories | Không bao gồm localhost và HTTPS |
| `repo1,repo2` | Hai IDs cụ thể | Không mở rộng tới mọi ID khác |
| `*,!approved-local` | Tất cả trừ ID được loại | Có đường ngoại lệ theo ID |
| `external:*,!private-repo` | External trừ ID private-repo | Chỉ an toàn nếu ngoại lệ được kiểm soát |

**Đừng chèn khoảng trắng tùy tiện** trong selector, chẳng hạn `!repo1, *`; tài liệu Maven lưu ý whitespace có thể làm matcher không hoạt động như dự kiến. Viết `!repo1,*` khi có ý định đó.

**`external:*` không có nghĩa “mọi host công khai”.** Nó cũng match repository HTTPS ở mạng nội bộ nếu repository không phải localhost/file-based. Điều này thường có lợi khi team muốn tất cả network resolution đi qua một approved group; nhưng không phải một policy cho mọi `file://` path.

## 7. Mirror matching precedence và thứ tự khai báo

Maven ưu tiên mirror có `<mirrorOf>` **khớp chính xác repository ID**. Nếu không có exact match, Maven chọn **advanced/wildcard mirror đầu tiên match** trong effective settings.

Ví dụ một cấu hình chủ động chặn external HTTP trước khi áp catch-all external mirror:

~~~xml
<mirrors>
    <mirror>
        <id>deny-external-http</id>
        <mirrorOf>external:http:*</mirrorOf>
        <url>http://0.0.0.0/</url>
        <blocked>true</blocked>
    </mirror>

    <mirror>
        <id>corp-maven-group</id>
        <mirrorOf>external:*</mirrorOf>
        <url>https://repo.example.invalid/repository/maven-approved/</url>
    </mirror>
</mirrors>
~~~

Với một external HTTP repository, hai selectors đều có thể match. **Nếu `external:*` đứng trước trong effective order, Maven có thể route HTTP request sang HTTPS group thay vì fail do blocker.** Redirect vào group tin cậy có thể là policy riêng hợp lệ, nhưng khi cần “HTTP declaration phải bị fail”, phải kiểm matching và thứ tự.

`<blocked>true</blocked>` không bắt Maven tải `http://0.0.0.0/`; URL này chỉ là pseudo endpoint cho một mirror bị chặn. Không dùng nó làm một thật proxy URL.

**Maven không tổng hợp nhiều mirror entries thành một repository group.** Nếu cần kết hợp Maven Central, artifacts của vendor và hosted nội bộ, phải làm tại repository manager, không thêm nhiều `<mirrorOf>*</mirrorOf>` rồi kỳ vọng Maven query tất cả.

## 8. Maven 3.8.1 và CVE-2021-26291

Apache Maven 3.8.1 đưa ra lớp hardening mặc định chống **external HTTP repositories**. Lý do liên quan CVE-2021-26291: dependency POM có thể khai một repository HTTP hoặc domain đã bị bỏ, dẫn đến nguy cơ man-in-the-middle hoặc repository/domain hijacking.

Một mirror thường có trong `conf/settings.xml`:

~~~xml
<mirror>
    <id>maven-default-http-blocker</id>
    <mirrorOf>external:http:*</mirrorOf>
    <url>http://0.0.0.0/</url>
    <blocked>true</blocked>
</mirror>
~~~

Thông báo lỗi kiểu:

~~~text
Blocked mirror for repositories:
  legacy-repo (http://old.example.invalid/maven2)
~~~

là dấu hiệu Maven đang **chặn external HTTP**, không phải công cụ bị hỏng. Ví dụ hostname `.invalid` ở đây chỉ minh họa.

Cách giải quyết đúng:
- Xác định POM/parent/transitive artifact nào khai repository HTTP.
- Dùng HTTPS endpoint được phê duyệt, không âm thầm thay `blocked` thành false.
- Nếu upstream cũ không hỗ trợ HTTPS, tổ chức có thể proxy/host artifact trong repository nội bộ sau kiểm duyệt.
- Xem version dependency mới hơn bỏ repository legacy.
- Kiểm legal/license/provenance trước khi mirror lại artifact.

**HTTPS chỉ bảo vệ đường truyền tới host**, không tự khẳng định host đáng tin hoặc artifact an toàn.

## 9. Kiến trúc một repository manager nội bộ đáng tin

Một ví dụ:

~~~text
Developer laptops / CI runners
       |
       | HTTPS + scoped read credentials
       v
    maven-approved-group
       |
       +-- internal-releases        hosted, immutable
       +-- internal-snapshots       hosted, restricted
       +-- approved-thirdparty     hosted, compliance-reviewed
       +-- maven-central-proxy      proxy, controlled upstream
~~~

Có thể triển khai với Nexus Repository, Artifactory hoặc sản phẩm tương đương. Names trong sơ đồ chỉ là gợi ý tổ chức.

Các trách nhiệm **phía server**:

1. Chỉ proxy những upstream đã được xét duyệt.
2. Giới hạn quyền upload theo project/namespace.
3. Đặt policy releases bất biến, không cho overwrite cùng GAV khác bytes.
4. Phân quyền snapshots và releases.
5. Xác định priority/group membership để tránh public artifact shadow internal artifact.
6. Scan/quarantine theo policy bảo mật và giấy phép.
7. Ghi audit logs để biết artifact tới từ upstream/hosted nào.
8. Xử lý cache/metadata/retention minh bạch.
9. Quản lý token scopes và TLS certificate.
10. Có quy trình revoke/quarantine compromised artifact.

**Mirror nội bộ không đủ nếu mọi developer đều có quyền upload vào hosted releases nằm đầu group.** Lúc đó một artifact độc hại vẫn có thể mang cùng internal GAV và được Maven tải qua một URL “nội bộ” vốn có thật.

## 10. Dependency confusion và namespace collision

Giả sử team sở hữu:

~~~text
com.company.platform:auth-sdk:2.4.0
~~~

Nếu repo group đồng thời tìm một public artifact **trùng GAV**, có nguy cơ resolve sai binary hoặc làm cache không nhất quán, tùy repository order, group members và artifact availability.

Phòng ngừa:
- Có policy **ownership** cho namespace `com.company.*`.
- Internal release artifacts được upload chỉ bởi authorized publisher.
- Server-side policy/denylist ngăn public proxy nhận internal GAV nếu hỗ trợ.
- Bất biến artifacts theo GAV.
- Không dùng dynamic version ranges hoặc unreviewed snapshots làm release dependencies.
- Dùng approved group repository và clean CI.
- Kiểm checksum/provenance từ nguồn tin cậy.
- Xem repository-manager audit logs khi cần chứng minh artifact đến từ đâu.

Không kết luận origin chỉ bằng `mvn dependency:tree`: tree cho **group/artifact/version/scope/graph**, không phải bằng chứng đầy đủ của URL đã phát binary.

### 10.1. Không phải collision nào cũng là tấn công

Repository migration, republished third-party JAR hoặc sai quyền upload cũng có thể tạo artifact bytes khác dưới cùng GAV. Tác động tới reproducibility vẫn nghiêm trọng. Đừng chờ có attacker rõ ràng mới bật immutable releases.

## 11. Checksum policy giúp gì và giới hạn ở đâu?

Maven repository policy hỗ trợ:

~~~xml
<releases>
    <enabled>true</enabled>
    <checksumPolicy>fail</checksumPolicy>
</releases>
~~~

Một checksum **không khớp** có thể khiến download/build fail theo policy. Các modes bao gồm `warn`, `fail`, `ignore`. Trong hệ Maven 3, default thường là `warn`, còn Maven 4 có default nghiêm hơn theo tài liệu API; team dùng nhiều versions nên kiểm chính Maven version hiện tại.

**Điều quan trọng:** nếu kẻ tấn công kiểm soát cả JAR và checksum file ở server, họ có thể thay cả hai cho khớp. Checksum không tự chứng minh **authenticity**. Kết hợp với:
- Approved HTTPS upstreams.
- Signed/provenance metadata được verify với key/identity đáng tin.
- Immutable hosted releases.
- Repository manager quarantine và security scanning.
- Controlled group membership.
- Network egress policy và CI audit.

Maven không mặc định xác minh **mọi GPG signature của mọi dependency** chỉ vì `.asc` tồn tại trên repository. Nếu yêu cầu xác minh chữ ký/provenance, phải thiết lập công cụ và policy kiểm tra thực tế, không coi file tồn tại là đủ.

## 12. Releases, snapshots và update policy

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `<releases><enabled>true</enabled>` | Cho phép dùng release artifact từ repository |
| `<snapshots><enabled>false</enabled>` | Không cho snapshot artifact qua repository rule đó |
| `<updatePolicy>daily</updatePolicy>` | Ví dụ tần suất Maven xem metadata/update theo policy |
| `<checksumPolicy>fail</checksumPolicy>` | Fail khi không đáp ứng checksum validation |
| Immutable release policy | **Phía repository manager**, không chỉ là POM XML |
| Snapshot retention/ACL | **Phía repository manager** và pipeline policy |

Ví dụ project release dùng snapshot dependency có thể khó tái hiện sau vài tuần vì timestamped snapshot metadata thay đổi. Không mặc định “cache giúp build ổn” là đủ; cần pin exact releases và kiểm transitive dependencies.

Một repository group gồm cả releases và snapshots phải có chính sách explicit. Việc disable snapshots trên **một** logical repository ID không tự ngăn một repository ID khác đưa snapshot vào graph.

## 13. `servers`: credentials đi theo mirror ID

Nếu mirror có:

~~~xml
<mirror>
    <id>corp-maven-group</id>
    <mirrorOf>external:*</mirrorOf>
    <url>https://repo.example.invalid/repository/maven-approved/</url>
</mirror>
~~~

thì server entry cần cùng ID:

~~~xml
<servers>
    <server>
        <id>corp-maven-group</id>
        <username>${env.MAVEN_REPO_READ_USER}</username>
        <password>${env.MAVEN_REPO_READ_TOKEN}</password>
    </server>
</servers>
~~~

Các `${env....}` là **tham chiếu environment**; giá trị thật phải được secret store/credential manager cung cấp cho build process. Không đưa raw tokens vào POM, Git, command line hoặc issue public.

Cần phân biệt:
- **Read-only token** dùng build jobs.
- **Write token** chỉ dành approved publishing jobs.
- **Snapshot publisher** nếu cần có scope riêng.
- **Admin token** không dùng chỉ để CI download.

Một repository ID hợp lệ **không tự chứng minh URL đáng tin**. Project/parent POM không đáng tin có thể làm credential ID/URL trở thành rủi ro nếu client không có origin binding phù hợp.

### 13.1. Credential-origin binding trong Maven mới

Theo Maven Settings Reference:
- Maven **3.10.0** và Maven **4.0.0+** hỗ trợ `repositoryOrigins` trong settings.
- Maven **3.9.16 và cũ hơn** bỏ qua trường này và có thể cảnh báo tag không nhận diện.
- Property `maven.repository.credentialScope` có các chế độ `origin`, `strict`, `id` ở versions hỗ trợ.
- Cơ chế ràng buộc origin giúp giảm nguy cơ cùng server ID được dùng tại host khác.

**Không giả định Maven 3.9.x có bảo vệ origin như Maven 3.10+**, và không dùng cấu hình Maven 4 rồi cho rằng nó được áp trên mọi runner. Cơ chế này chủ yếu áp cho credentials Maven Resolver sử dụng; custom plugins đọc settings trực tiếp có thể không chịu cùng ràng buộc.

Vẫn cần verify URL/host/TLS và bảo vệ runners khỏi untrusted code.

## 14. Mẫu `settings.xml` dùng cho môi trường được kiểm soát

Đây là **template đầy đủ để đọc và điều chỉnh**, không phải file có thể chạy thành công nguyên trạng: hostname `.invalid` cố ý giả để không chỉ vào server thật. Trước khi dùng cần có approved repository group URL từ administrator và secrets được cấp đúng môi trường.

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">

    <mirrors>
        <mirror>
            <id>deny-external-http</id>
            <mirrorOf>external:http:*</mirrorOf>
            <url>http://0.0.0.0/</url>
            <blocked>true</blocked>
        </mirror>
        <mirror>
            <id>corp-maven-group</id>
            <mirrorOf>external:*</mirrorOf>
            <url>https://repo.example.invalid/repository/maven-approved/</url>
        </mirror>
    </mirrors>

    <servers>
        <server>
            <id>corp-maven-group</id>
            <username>${env.MAVEN_REPO_READ_USER}</username>
            <password>${env.MAVEN_REPO_READ_TOKEN}</password>
        </server>
    </servers>

    <profiles>
        <profile>
            <id>controlled-repositories</id>

            <repositories>
                <repository>
                    <id>central</id>
                    <url>https://repo.maven.apache.org/maven2/</url>
                    <releases>
                        <enabled>true</enabled>
                        <checksumPolicy>fail</checksumPolicy>
                    </releases>
                    <snapshots>
                        <enabled>false</enabled>
                    </snapshots>
                </repository>
            </repositories>

            <pluginRepositories>
                <pluginRepository>
                    <id>central</id>
                    <url>https://repo.maven.apache.org/maven2/</url>
                    <releases>
                        <enabled>true</enabled>
                        <checksumPolicy>fail</checksumPolicy>
                    </releases>
                    <snapshots>
                        <enabled>false</enabled>
                    </snapshots>
                </pluginRepository>
            </pluginRepositories>
        </profile>
    </profiles>

    <activeProfiles>
        <activeProfile>controlled-repositories</activeProfile>
    </activeProfiles>
</settings>
~~~

### 14.1. Điều gì được bảo đảm, điều gì chưa?

- `deny-external-http` đứng trước corporate wildcard để **ưu tiên chặn external HTTP** nếu không có exact mirror khác ưu tiên cao hơn trong effective settings.
- `corp-maven-group` nhận phần lớn network remote repository requests.
- `<server>` dùng mirror ID cho read auth.
- `<repositories>`/`<pluginRepositories>` có checksum policy strict cho ID `central` trong active profile.
- `snapshots.enabled=false` chỉ cho logical repository được nêu, **không bảo đảm mọi repository/endpoint khác** cũng từ chối snapshots.
- `external:*` vẫn **không mirror localhost/file-based repositories**.
- Các repository managers/proxies phía server vẫn cần govern nguồn, group ordering, ACL, quarantine, audit.

**Đừng cho rằng `<checksumPolicy>fail</checksumPolicy>` của một repository ID tự là global rule cho mọi repository được import từ POM lạ.** Nếu tổ chức cần kiểm toàn bộ artifact intake, thiết kế server-side/pipeline verification rộng hơn.

### 14.2. `central` URL có được gọi trực tiếp không?

Khi mirror match, Maven dùng **mirror URL** để tải thay original repository. URL Central trong profile thể hiện logical repository definition và policy; nó không nhất thiết là URL kết nối trực tiếp khi có `external:*`.

Nếu run ở environment không có quyền truy cập `corp-maven-group`, build fail là expected. **Không tắt mirror để project release “xanh”** nếu policy yêu cầu tất cả downloads phải được govern.

## 15. Áp mirror cho parent POM, BOM và plugin

Một parent POM/Imported BOM có thể được tải trước khi project hoàn tất model. Vì vậy:
- Corporate settings phải có sẵn từ đầu Maven invocation.
- Không chỉ chèn repository config vào module con sau khi parent resolution đã fail.
- Các plugin/build extensions không được để thoát khỏi approved source.
- `pluginRepositories` là một mặt cấu hình riêng nhưng mirror selection vẫn có thể route Maven plugin download requests qua approved group.

Một thay đổi parent POM có thể thêm plugin hoặc repository không review. Version pin ở child không bù được mọi inherited plugin execution; xem effective POM và parent provenance.

## 16. Lab Maven/Java 17 không cần một server nội bộ thật

Để thực hành an toàn, trước tiên tạo project mà Maven có thể build với Maven Central hoặc corporate settings **đã được cấu hình hợp lệ sẵn**. Sau đó áp template nội bộ khi bạn có endpoint thật. Không yêu cầu người học tải JAR lạ hay tự publish lên repository.

### 16.1. Cấu trúc

~~~text
trusted-source-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/trust/App.java
    └── test/java/com/example/trust/AppTest.java
~~~

Điều kiện:
- Maven 3.9+ và JDK 17+.
- Repository được phép có Maven Compiler/Surefire/JAR/Exec Plugins, Commons Lang và JUnit.
- Không cần token, Docker, GPG key hoặc cấu hình network đặc biệt khi có Maven Central hợp lệ.

### 16.2. `pom.xml` hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.trust</groupId>
    <artifactId>trusted-source-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <commons.lang3.version>3.17.0</commons.lang3.version>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>${commons.lang3.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.jupiter.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
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
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.7.0</version>
                <configuration>
                    <mainClass>com.example.trust.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

POM không có custom `repositories`/`pluginRepositories`; Maven sử dụng effective settings + Super POM. Nếu corporate mirror active, library và plugin resolution có thể đi qua mirror mà **không sửa source POM**.

### 16.3. `App.java`

Tạo `src/main/java/com/example/trust/App.java`:

~~~java
package com.example.trust;

import java.util.Locale;

import org.apache.commons.lang3.StringUtils;

public final class App {

    private App() {
    }

    public static String normalize(String value) {
        return StringUtils.upperCase(
                StringUtils.trimToEmpty(value), Locale.ROOT);
    }

    public static String message(String value) {
        String clean = normalize(value);
        if (clean.isEmpty()) {
            return "EMPTY";
        }
        return "Resolved via Maven: " + clean;
    }

    public static void main(String[] args) {
        System.out.println(message(" maven "));
    }
}
~~~

`StringUtils` là class thật trong Commons Lang 3.17.0; không có network requests ở runtime. Maven tải library trước, compiler dùng nó rồi Exec Plugin chạy với dependency classpath.

### 16.4. `AppTest.java`

Tạo `src/test/java/com/example/trust/AppTest.java`:

~~~java
package com.example.trust;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {

    @Test
    void uppercasesText() {
        assertEquals("MAVEN", App.normalize("  maven  "));
    }

    @Test
    void handlesNull() {
        assertEquals("", App.normalize(null));
    }

    @Test
    void handlesWhitespaceOnly() {
        assertEquals("EMPTY", App.message("  "));
    }

    @Test
    void formatsMessage() {
        assertEquals("Resolved via Maven: MAVEN",
                App.message(" maven "));
    }
}
~~~

Có **4 JUnit 5 test methods**, mỗi method có assertion. Tests kiểm behavior Java, **không kiểm remote repo authenticity**; CI/repository policy thực hiện nhiệm vụ sau.

### 16.5. Build và stdout chính xác

Tại thư mục chứa POM:

~~~bash
mvn -version
java -version
mvn -B clean verify
mvn -q exec:java
~~~

Expected:
- Compiler tạo Java 17 classes.
- JUnit tests chạy 4 methods, pass.
- JAR `target/trusted-source-demo-1.0.0.jar` được tạo.
- Main có **stdout**:

~~~text
Resolved via Maven: MAVEN
~~~

Đây là stdout của Java `App`, không phải khẳng định toàn bộ Maven logs không có dòng khác. POM không tạo executable manifest/fat JAR, vì vậy không dùng `java -jar target/trusted-source-demo-1.0.0.jar` như cách chạy mặc định.

## 17. Chạy lab với approved mirror khi đã có endpoint thực

Chỉ sau khi repository admin cung cấp approved URL, thay host `.invalid` trong `settings.xml` và lưu file ngoài Git. Sau đó có thể chạy:

~~~bash
mvn -B -s /path/to/approved-settings.xml clean verify
mvn -q -s /path/to/approved-settings.xml exec:java
~~~

Với endpoint đúng và artifact bytes tương thích, Java `App` vẫn in:

~~~text
Resolved via Maven: MAVEN
~~~

Thay đổi ở đây là **nguồn tải/đường kết nối/policy**. Nếu dùng nguyên `repo.example.invalid`, Maven sẽ fail vì không tồn tại; đó là hành vi đúng của một URL mẫu.

Một số Maven logs có thể ghi:

~~~text
Using mirror corp-maven-group for central
Downloading from corp-maven-group: ...
~~~

Đây chỉ là **minh họa nội dung logs**, không phải đúng nguyên văn từng dòng trên mọi Maven version. Để xác nhận provenance thật, dùng approved resolver logs cùng repository-manager access/audit logs và checksum metadata.

## 18. Local Maven repo sạch quan trọng như thế nào?

Nếu `~/.m2/repository` đã có một JAR do developer cài thủ công (`install-file`) hoặc download nhiều tháng trước, build có thể pass mà không thực hiện request tới mirror mới.

Trong POSIX shell, dùng một local repo riêng **chưa chứa artifacts**:

~~~bash
mvn -B -Dmaven.repo.local=/tmp/maven-repo-fresh-demo clean verify
~~~

Khi có approved settings:

~~~bash
mvn -B -s /path/to/approved-settings.xml -Dmaven.repo.local=/tmp/maven-repo-fresh-approved clean verify
~~~

Windows PowerShell:

~~~powershell
mvn -B "-Dmaven.repo.local=$env:TEMP\maven-repo-fresh-demo" clean verify
~~~

Không dùng chung path đã được populate từ test trước để kết luận “đã tải từ remote”. `mvn clean` xóa `target/` của project, **không xóa local Maven cache**. Không xóa nguyên `~/.m2/repository` của developer/máy dùng chung chỉ để test; hãy dùng isolated path.

### 18.1. Offline mode chỉ chứng minh cache đủ

~~~bash
mvn -o clean verify
~~~

Nếu đã tải đủ trước đó, Maven có thể build offline. Điều này không chứng minh remote trust policy hiện tại đang được áp dụng, vì Maven có thể **không truy cập remote** ở invocation này.

### 18.2. `-U` không chứng nhận remote

~~~bash
mvn -U clean verify
~~~

`-U` có thể yêu cầu Maven kiểm cập nhật snapshots/cached missing artifacts theo resolver behavior. Nó không biến một untrusted repository thành trusted, cũng không bảo đảm mọi release đã cache sẽ được tải lại. Muốn test clean resolution, dùng một fresh local repo và approved repository settings.

## 19. Kiểm `dependency:tree` và effective model

Các lệnh hữu ích:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
mvn help:effective-pom -Dverbose
mvn help:effective-settings
~~~

Một dòng dependency tree điển hình:

~~~text
org.apache.commons:commons-lang3:jar:3.17.0:compile
~~~

Đây là **dòng rút gọn**, không phải full Maven stdout. Tree cho version/scope/graph; nó không chứng minh binary được lấy từ remote server nào. Để xác minh nguồn:
- Xem repository manager access logs.
- Xem safe Maven resolver logs/download metadata.
- Kiểm checksums của artifact và trusted provenance.
- So effective mirrors/profile rules trên CI.
- Kiểm local cache/source-tracking metadata khi cần, không coi stale cache là nguồn chính xác.

BOM hoặc `dependencyManagement` chỉ kiểm **version metadata**, không tự bảo đảm host/source/trust identity.

## 20. Build plugins là đường thực thi code trong pipeline

Một `<plugin>` Maven không giống một dependency ứng dụng được classloader load sau khi deploy. Build plugin chạy trong process/JVM của Maven hoặc subprocess và có thể đọc environment, source, credentials, network.

Policy nên:
1. Pin plugin versions trong `pluginManagement`/`plugins`.
2. Chỉ tải plugin + plugin dependencies qua approved sources.
3. Kiểm build extensions/parent profiles.
4. Không cấp signing key/deploy token cho untrusted PR code.
5. Giới hạn CI egress tới kho nội bộ khi khả thi.
6. Audit Maven wrapper và Maven distribution.
7. Tách build read-only và publish restricted jobs.
8. Kiểm software bill of materials/trusted toolchain.

**Maven mirror không phải network firewall.** Một plugin/script tự HTTP request ngoài Maven Resolver có thể bypass mirror; cần kiểm network/runtime chính sách riêng.

## 21. Snapshot versus release trust policy

| | Release artifact | Snapshot artifact |
| --- | --- | --- |
| Ví dụ | `2.4.0` | `2.4.1-SNAPSHOT` |
| Tính bất biến | Nên immutable | Thường có metadata/bytes thay đổi |
| Usage | Stable reproducible builds | Development, internal CI |
| Repository | Hosted releases | Hosted snapshots |
| Write rights | Approved release publishers | Authorized snapshot jobs |
| CI validation | Signed/provenance/baseline gates | Tests, lifecycle policy, cache management |

Nếu group chứa cả snapshot và release, server-side repo membership, priority và ACL là quyết định quan trọng. Không cho một public proxy artifact `com.company.*` shadow internal package khi policy yêu cầu namespace ownership.

## 22. Kiểm soát egress và tránh POM có repository lạ

Một Maven POM có thể chứa:

~~~xml
<repositories>
    <repository>
        <id>unapproved-repository</id>
        <url>https://untrusted.example.invalid/maven/</url>
    </repository>
</repositories>
~~~

Đây là **phản ví dụ cho một nguồn chưa được duyệt**, không phải URL thật. Nếu effective settings mirror `external:*` match, Maven Resolver sẽ dùng approved group thay vì kết nối trực tiếp tới host đó. Nhưng nếu settings bị thay, hoặc có ngoại lệ selector, yêu cầu có thể đi ra ngoài.

CI nên:
- Có protected settings được cấu hình bởi môi trường, không bởi untrusted PR.
- Kiểm repositories/plugins/extensions ở POM.
- Hạn chế network egress.
- Reject unknown repository sources theo policy.
- Không sửa policy bằng việc thêm untrusted URL vào POM chỉ vì build đang thiếu artifact.
- Kiểm cả dependency POMs/repository contexts, nhất là với legacy Maven projects.

## 23. Những lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Could not find artifact` | Sai GAV/version, group chưa có artifact | Xem effective repo, group membership |
| Build xanh local nhưng fail CI | Local cache chứa artifact riêng | Fresh CI local repository |
| External HTTP bị chặn | Maven 3.8.1+ blocker | Dùng HTTPS/approved proxy, không tắt blocker |
| HTTP 401 | Mirror ID khác server ID hoặc token thiếu | Kiểm ID/env presence, không in token |
| HTTP 403 | Repo token thiếu read permission | Sửa ACL/scope theo policy |
| HTTP 404 | Repository group thiếu path/artifact | Xác minh hosted/proxy membership |
| HTTP 429 | Repository rate limit | Backoff/retry theo CI policy, không đổi nguồn lạ |
| TLS error | CA/truststore/hostname | Sửa chứng chỉ, không disable TLS |
| Plugin tải từ nơi khác dự kiến | pluginRepositories, profile hoặc custom fetch | Xem effective POM và plugin logs |
| `checksumPolicy=fail` báo lỗi | Byte mismatch hoặc checksum thiếu | Quarantine/điều tra metadata |
| Maven báo blocked mirror | `external:http:*` blocker match | Tìm POM chứa URL HTTP |
| Mirror áp cho file:// test repo | Dùng `mirrorOf=*` quá rộng | Review selector ngoại lệ |
| `external:*` bỏ qua file:// | Đúng semantic selector | Cần CI policy/`*` nếu muốn route mọi request |
| Same GAV nhưng bytes khác | Overwrite hoặc collision/cache poison | So SHA256, provenance, audit logs |
| `mvn -o verify` pass | Cache đủ, không download | Không coi là chứng cứ remote trust |
| Plugin code lạ có network access | Mirror không chặn custom requests | Network firewall/egress policy |
| Secrets lộ trong debug logs | `-X` hoặc plugin in config | Rotate token, restrict logs |
| Maven 3.9 không hiểu repositoryOrigins | Feature chỉ ở versions mới | Check Maven version, don't assume protection |
| Snapshot đổi giữa builds | Mutable metadata, retention | Pin releases/time-stamped metadata theo policy |

**Đừng giảm security setting chỉ để build pass.** Một source bị chặn có thể là dấu hiệu policy bảo vệ đúng; cần điều tra nguồn và quy trình approve artifact.

## 24. Kiểm tra theo quy trình CI

Một pipeline được quản lý có thể dùng trình tự:

~~~text
Checkout approved commit
  |
  v
Pin Java/Maven/Wrapper/toolchain versions
  |
  v
Provision protected settings.xml and read-only token
  |
  v
Fresh or attested local Maven repository
  |
  v
Resolve via approved HTTPS group
  |
  v
Verify repository logs, provenance, checksum policy
  |
  v
mvn -B clean verify
  |
  v
Check dependency tree, plugin versions, test reports
  |
  v
Security/SBOM/license checks
  |
  v
Only approved release job gets write token
~~~

Một build job read-only không cần deploy token. Nếu artifact do team tạo phải được upload, dùng job riêng có approval/limited privileges, kiểm signatures và immutable GAV. **Không để bước chạy code PR không tin cậy cùng môi trường có write credentials**.

Cần lưu build metadata đủ để tái hiện: Git commit, Maven/JDK versions, settings/mirror policy version (không kèm secrets), resolved dependencies, plugin versions, provenance và checksums của release artifacts.

## 25. Bài tập tự kiểm tra

**Câu 1.** Có version pin trong POM rồi có cần kiểm nguồn không?

**Đáp:** Có. Version/GAV không tự bảo đảm repository URL, artifact bytes và provenance.

**Câu 2.** `<repositories>` có kiểm Maven plugins không?

**Đáp:** Không đầy đủ; Maven có `<pluginRepositories>` cho plugin resolution.

**Câu 3.** `distributionManagement` là gì?

**Đáp:** Repository đích khi project publish qua lifecycle, không phải dependency download mirror.

**Câu 4.** `mirrorOf=central` có ép mọi remote source qua group không?

**Đáp:** Không. Chỉ match repository ID `central`.

**Câu 5.** `mirrorOf=external:*` có bắt file:// repositories không?

**Đáp:** Không. Nó loại file-based và localhost repos.

**Câu 6.** `mirrorOf=*` phù hợp cho mọi integration test không?

**Đáp:** Không mặc định. Nó có thể redirect file/localhost fixture repositories mà test đang cần.

**Câu 7.** Mirror entries có hợp thành một repository group không?

**Đáp:** Không. Maven chọn một match; repository manager mới tổng hợp các repositories.

**Câu 8.** Exact ID mirror và advanced wildcard, cái nào được xét trước?

**Đáp:** Exact ID trước; wildcard ưu tiên first match theo effective order.

**Câu 9.** Vì sao Maven 3.8.1 chặn external HTTP?

**Đáp:** Để giảm rủi ro MITM và untrusted repository từ dependency POMs.

**Câu 10.** `<blocked>true</blocked>` có gọi thật `http://0.0.0.0/` không?

**Đáp:** Không. Blocked mirror ngăn request và báo lỗi.

**Câu 11.** `checksumPolicy=fail` có bảo đảm JAR không bị attacker thay khi checksum cũng bị thay không?

**Đáp:** Không; cần trust root/provenance/signature từ nguồn độc lập.

**Câu 12.** Một repository group nội bộ có tự an toàn nếu ai cũng có write permission không?

**Đáp:** Không. Cần ACL/immutability/namespace ownership.

**Câu 13.** Maven credential-origin binding hỗ trợ từ Maven 3.9 không?

**Đáp:** Không ở cùng mức như Maven 3.10+; kiểm exact version và feature support.

**Câu 14.** `dependency:tree` có cho URL của từng JAR một cách đầy đủ không?

**Đáp:** Không. Nó cho artifact graph; cần resolver logs/repository-manager audit.

**Câu 15.** Vì sao thử bằng fresh local Maven repository?

**Đáp:** Để không vô tình dùng artifact đã cache hoặc install thủ công từ trước.

**Câu 16.** `mvn -o verify` pass có xác minh remote trust hiện tại không?

**Đáp:** Không. Offline mode không cần truy cập remote nếu cache đủ.

**Câu 17.** BOM có giúp enforce nguồn đáng tin không?

**Đáp:** Không. BOM quản lý versions/metadata, không phải repository origin.

**Câu 18.** Một Maven plugin độc hại có thể đọc token của CI runner không?

**Đáp:** Có thể nếu job cấp token và plugin thực thi với quyền phù hợp, nên tách trust boundary.

**Câu 19.** HTTPS đủ chứng minh nhà phát hành đáng tin không?

**Đáp:** Không. Cần xác minh host/ownership, artifact provenance và release policy.

**Câu 20.** Khi internal GAV bị public artifact trùng namespace, cần làm gì?

**Đáp:** Kiểm group membership/priority, denylist namespace từ proxy, immutable releases và audit/resolution.

## 26. Checklist áp dụng trước khi cho pipeline phát hành

1. Nêu rõ upstream nào được tin cậy; không cho POM tùy ý mở nguồn.
2. Dùng approved HTTPS Maven repository manager.
3. Tách hosted releases, snapshots, third-party và Central proxy.
4. Kiểm group order để public GAV không shadow internal artifacts.
5. Bảo vệ internal namespace và quyền upload.
6. Bật immutable releases, audit logs và quarantine.
7. Route Maven dependencies/plugin downloads qua approved mirror.
8. Kiểm `mirrorOf` có đúng `central`/`external:*`/`*` theo policy.
9. Bảo vệ external HTTP blocker, không tự disable.
10. Kiểm mirror ordering/exact-ID precedence.
11. Kiểm các file/localhost repository exceptions.
12. Dùng `settings.xml` ngoài Git và token read-only.
13. Server IDs khớp mirror IDs; origin binding theo version hỗ trợ.
14. Pin Maven/JDK/toolchain/plugins và dependency versions.
15. Review parent POM, BOM, extensions và active profiles.
16. Chạy clean Maven build trên isolated/attested local repository.
17. Xem `dependency:tree`, effective settings và POM một cách không lộ secrets.
18. Kiểm checksum policy và hiểu giới hạn authenticity.
19. Thẩm định signatures/provenance của artifacts trọng yếu.
20. Quét CVE/license, duy trì SBOM và artifact inventory.
21. Tránh mutable SNAPSHOTs/dynamic ranges ở release.
22. Không dùng offline build pass làm bằng chứng remote source.
23. Không giả định mirror là firewall cho custom network calls.
24. Tách PR/read-only CI với approved publish job.
25. Kiểm repository logs/alerts cho không hợp lệ uploads.
26. Nếu artifact compromised, quarantine, rotate credentials và phát hành version mới.
27. Ghi lại commit, versions, source policy, artifact checksums cho release.
28. Re-test consumers từ một fresh local repository.
29. Không bypass block/SSL/checksum chỉ vì lỗi download.
30. Rà soát định kỳ repository allowlists, credentials và namespace policy.

## Tài liệu tham khảo chính thức

- [Apache Maven — Using Mirrors for Repositories](https://maven.apache.org/guides/mini/guide-mirror-settings.html)
- [Apache Maven — Setting up Multiple Repositories](https://maven.apache.org/guides/mini/guide-multiple-repositories.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Apache Maven — Repository Management](https://maven.apache.org/repository-management.html)
- [Apache Maven — Maven 3.8.1 Release Notes, CVE-2021-26291](https://maven.apache.org/docs/3.8.1/release-notes.html)
- [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Guide to Configuring Plugins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Security Reports](https://maven.apache.org/security.html)
- [Apache Maven — Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Apache Maven — Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [MojoHaus — Exec Maven Plugin](https://www.mojohaus.org/exec-maven-plugin/)

