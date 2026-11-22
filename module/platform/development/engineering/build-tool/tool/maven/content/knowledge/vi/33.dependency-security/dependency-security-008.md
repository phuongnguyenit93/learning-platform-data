# Giới hạn quyền đọc, xuất bản và ký artifact trong Maven

> **Build Tool Maven · An toàn phụ thuộc**  
> Bài học dùng Maven 3.9.x, Java 17 và các thành phần phổ biến của quy trình CI/CD. Trọng tâm là **phân quyền tối thiểu** cho ba hành động rất khác nhau: **đọc/tải dependency**, **xuất bản artifact** và **ký artifact**. Ví dụ có POM Java 17 tự chạy, hai JUnit tests, cấu hình `settings.xml` dành cho read-only và publisher, Maven Deploy Plugin 3.1.4, Maven GPG Plugin 3.2.8, quy trình xác minh SHA-256/chữ ký và checklist ứng phó sự cố.

## 1. Bài toán: cùng là Maven repository, nhưng không phải cùng một quyền

Một developer mở dự án và chạy:

```bash
mvn -B clean verify
```

thường chỉ cần **đọc** Maven dependencies, parent POM, plugins và metadata từ các repositories hợp lệ. Build thành công không đòi tài khoản được phép upload binary mới lên repository.

Ngược lại, release pipeline chạy:

```bash
mvn -B clean deploy
```

có thể cần **quyền ghi** vào một repository đích. Nếu artifact phải được ký, bước ký còn cần **quyền sử dụng một khóa ký đáng tin cậy**. Quyền ký là quyền sử dụng cryptographic identity, không phải một quyền upload thông thường.

Ba năng lực khác nhau:

```text
ĐỌC (consume)
  Maven Resolver -> GET metadata/POM/JAR/plugin
                |
                v
      tải dependencies có kiểm soát

XUẤT BẢN (publish)
  Maven Deploy Plugin -> ghi POM/JAR/metadata
                       vào release/snapshot repository

KÝ (sign)
  Maven GPG Plugin hoặc signing service
     -> dùng private key tạo detached signature
     -> consumer dùng public key để verify
```

**Nguyên tắc an toàn:** tài khoản chỉ cần đọc không được quyền publish; tài khoản được publish không tự được sử dụng khóa ký; người quản lý repository không mặc định được dùng khóa ký phát hành. Trong triển khai thực tế, authorization được áp **tại repository server, IAM và signing service**, không chỉ qua POM.

### 1.1. Tại sao vấn đề này thuộc “an toàn phụ thuộc”?

Nếu tài khoản build đọc dependency bị lộ mà cũng có quyền publish, kẻ tấn công có thể thử **thay thế một artifact** hoặc upload phiên bản độc hại vào namespace mà các dự án khác tiêu thụ. Nếu khóa ký bị lộ, kẻ tấn công có thể ký artifact giả dưới một identity đáng tin.

Chỉ cần nhầm một quyền là **vùng ảnh hưởng** có thể mở rộng từ một dự án sang nhiều consumers:

```text
Một CI job bị chiếm quyền
          |
          +-- chỉ đọc --------> rò rỉ private artifacts/metadata
          |
          +-- có publish -----> upload artifact độc hại/ghi đè release
          |
          +-- có private key -> tạo chữ ký mang identity đáng tin
          |
          +-- admin ----------> sửa policy, tài khoản, delete, retention
```

Rủi ro thực tế tùy repository manager, permission model, khả năng ghi đè và consumer verification. Không suy rằng mọi hệ thống đều cho overwrite release; **cần chủ động cấm và kiểm thử điều đó**.

## 2. Phân biệt authentication, authorization và integrity

- **Authentication (xác thực):** hệ thống biết principal là ai, ví dụ một service account/token/job identity.
- **Authorization (phân quyền):** principal được làm gì tại repository/namespace/channel nào.
- **Integrity (toàn vẹn):** file tải có đúng bytes mong đợi, ví dụ so SHA-256.
- **Authenticity (tính xác thực):** nguồn tạo/ký có đúng trusted identity hay không.
- **Provenance (nguồn gốc build):** artifact digest liên hệ tới source commit, builder và build process.
- **Approval (phê duyệt):** tổ chức cho phép phát hành artifact nào, tới môi trường nào.

Một `<server>` trong Maven `settings.xml` **chỉ cung cấp thông tin xác thực**, không tự tạo ACL ở repository. Một `gpg --verify` có thể cho biết signature đúng với một public key, nhưng nếu public key chưa được xác minh theo trust policy thì chưa kết luận artifact an toàn.

### 2.1. Ma trận vai trò tham khảo

Đây là **thiết kế chính sách gợi ý**, không phải những tên role Maven tự tạo:

| Principal | Đọc artifact | Publish SNAPSHOT | Publish RELEASE | Ký release | Sửa ACL/xóa artifact |
| --- | --- | --- | --- | --- | --- |
| Developer / local build | Có, chỉ repos cần thiết | Không mặc định | Không | Không | Không |
| PR CI / test job | Có, read-only | Không | Không | Không | Không |
| Snapshot publisher | Có | Có, đúng namespace SNAPSHOT | Không | Không | Không |
| Release publisher | Có | Không, trừ nhu cầu riêng | Có, đúng namespace version | Không mặc định | Không |
| Signing identity/job | Đọc chính artifact đã duyệt | Không | Không | Có, đúng key và policy | Không |
| Release approver | Đọc evidence | Không | Quyền phê duyệt, không phải token upload | Không mặc định | Không |
| Repository administrator | Theo vận hành | Theo quyền quản trị | Theo quyền quản trị | **Không mặc định** | Có, audit và kiểm soát |
| Consumer production | Có, đúng artifacts | Không | Không | Không | Không |

**Cách ly nhiệm vụ** không yêu cầu mỗi tổ chức phải có chính xác tám role. Điều cốt lõi là **người, token hoặc job nào được cấp quyền gì**, theo tài nguyên nào, thời gian bao lâu và có thể lạm dụng như thế nào.

### 2.2. Những chiều scope cần xét

Không chỉ giới hạn theo thao tác `read/write`:

- **Repository:** releases, snapshots, staging, mirror, hosted hoặc proxy.
- **Namespace:** `groupId`, package prefix hoặc project/tenant được sở hữu.
- **Version:** SNAPSHOT hay release; có cho overwrite cùng GAV không.
- **Action:** read, list, upload, overwrite, delete, change metadata, promote, sign.
- **Identity:** cá nhân, bot, GitHub/GitLab/Jenkins workflow, workload identity.
- **Environment:** development, test, protected release, production.
- **Time:** token có TTL, khả năng rotate/revoke, lịch sử audit.
- **Network:** runner được phép nối tới những hosts nào.
- **Approval:** signed tag, review, release manager hoặc protected environment.

Quyền ghi vào một repository **không** nên đồng nghĩa quyền xóa mọi bản release hoặc thay đổi toàn bộ ACL. Server nào không hỗ trợ granular ACL theo namespace/action thì phải dùng **repository tách biệt, proxy/promotion hoặc tài khoản giới hạn hơn** để đạt cùng mục tiêu.

## 3. Maven lấy dependencies bằng quyền nào?

Khi build, Maven Resolver tải những đầu vào như:

```text
Parent POM
Imported BOM
Project dependency POM/JAR
Transitive dependency POM/JAR
Maven plugins và plugin dependencies
Build extensions
maven-metadata.xml / checksums
```

Đầu vào có thể đến từ Maven Central, private repository, mirror do `settings.xml` cấu hình hoặc local cache.

- Public artifacts thường **không cần credentials**.
- Private artifacts có thể cần **read-only token**.
- Nếu cần credentials, Maven dùng `<servers>` trong `settings.xml` và matching repository/mirror IDs.
- Local repository cache là dữ liệu trên máy, **không phải quyền truy cập server**. Có cache không có nghĩa principal có quyền đọc remote lúc này.

### 3.1. Vì sao không đặt token vào `pom.xml`?

`pom.xml` thường được commit vào Git và có thể được publish cùng artifact. Đưa token vào POM khiến secrets dễ lộ qua source, published POM, build logs, effective POM hoặc files được gửi cho consumer.

**Thông lệ đúng:** POM khai báo GAV và repository location cần thiết, còn credentials do **`settings.xml` bên ngoài source** hoặc credential helper/provider được platform hỗ trợ cung cấp; CI inject secrets từ secret manager ở đúng job.

### 3.2. `repositories` khác `pluginRepositories`

```xml
<repositories>
    <repository>
        <id>private-dependencies</id>
        <url>https://repo.example.invalid/maven/dependencies</url>
    </repository>
</repositories>
```

`<repositories>` phục vụ dependency resolution; `<pluginRepositories>` phục vụ Maven plugin resolution. Hai loại đều có thể cần read credentials tùy môi trường.

Đoạn trên là **fragment minh họa**, `example.invalid` cố ý không hoạt động, không xuất hiện trong POM runnable bên dưới. Với một build chỉ dùng Maven Central, không cần thêm private URL.

### 3.3. Mirror có thể thay đổi endpoint thực được xác thực

```xml
<mirrors>
    <mirror>
        <id>company-read-mirror</id>
        <mirrorOf>*</mirrorOf>
        <url>https://repo.example.invalid/maven/public-group</url>
    </mirror>
</mirrors>
```

Nếu mirror được áp dụng, endpoint thực là mirror và Maven có thể tra credentials theo **mirror ID**. Server entry phải khớp ID phù hợp với endpoint được dùng; không chỉ nhìn `<repository><id>` trong POM rồi đoán.

`mirrorOf=*` là một **định tuyến rộng**, không tự giới hạn namespace hay cấp quyền nào. Cần áp **server-side ACL** ở repository manager, bảo vệ network và xem xét nguồn upstream được proxy.

## 4. `settings.xml` cho consumer: chỉ đọc và không có khóa ký

Một **mẫu dành cho private company mirror**, không chạy được cho tới khi thay URL, account/token và scope thật:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <mirrors>
        <mirror>
            <id>company-read-mirror</id>
            <mirrorOf>*</mirrorOf>
            <url>https://repo.example.invalid/maven/public-group</url>
        </mirror>
    </mirrors>
    <servers>
        <server>
            <id>company-read-mirror</id>
            <username>${env.MVN_READ_USER}</username>
            <password>${env.MVN_READ_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Maven Settings Reference cho phép nội suy **environment variables** bằng `${env.VAR_NAME}`. Trong ví dụ, `MVN_READ_USER` và `MVN_READ_TOKEN` phải được CI cung cấp **từ secret manager**, không được copy một token thật vào repo.

**Quan trọng:** việc đưa `MVN_READ_TOKEN` vào settings **không biến token thành read-only**. Quản trị viên phải tạo credential có **ACL read-only tại repository manager**. Nếu credential thật có quyền publish, Maven vẫn có thể upload bằng nó trong trường hợp job hoặc plugin gọi thao tác ghi.

### 4.1. Xác minh read-only theo phương pháp không phá hoại

Trước khi cấp cho PR CI:

1. Kiểm tra quyền principal theo dashboard/IAM/repository manager.
2. Thử tải artifact private được phép bằng một **test account read-only**.
3. Thử truy cập namespace không được phép; kỳ vọng bị từ chối.
4. Với **repository kiểm thử riêng**, thực hiện negative test publish một canary version và kỳ vọng bị **403/unauthorized**; không thử ghi bừa vào release production.
5. Xem audit log server để bảo đảm action và principal đúng.
6. Không cấp quyền `delete`, `overwrite`, `role management` cho read-only token.

Một HTTP 401 thường báo chưa được xác thực/credential sai; HTTP 403 thường báo đã xác thực nhưng bị cấm theo policy. Nhà cung cấp repository có thể xử lý cụ thể khác; hãy xem server logs và cơ chế ẩn thông tin repository.

### 4.2. Các job nào có thể dùng read-only token?

- Local developer đã được cấp quyền đọc library nội bộ.
- CI build/test trên protected branches, theo rule tổ chức.
- Runtime dependency downloader/production deployment nếu cần đọc artifact đã duyệt.
- Scanner SBOM/license/vulnerability chỉ cần tải artifacts.

Với **untrusted fork pull request**, tránh đưa private credentials vào job. Nếu build cần private dependencies nhưng source từ fork không tin cậy, hãy dùng isolation/caching/proxy hoặc chính sách review phù hợp; không tự nâng quyền cho PR job chỉ để làm build xanh.

## 5. Xuất bản artifact: `distributionManagement` khác `<repositories>`

Maven Deploy Plugin dùng **`distributionManagement`** để quyết định nơi upload artifacts ở phase `deploy`. Read dependency repositories được khai báo bởi `<repositories>`/`pluginRepositories` và settings, không phải `distributionManagement`.

Ví dụ release/snapshot destinations:

```xml
<distributionManagement>
    <repository>
        <id>release-write</id>
        <url>https://repo.example.invalid/maven/releases</url>
    </repository>
    <snapshotRepository>
        <id>snapshot-write</id>
        <url>https://repo.example.invalid/maven/snapshots</url>
    </snapshotRepository>
</distributionManagement>
```

Đây là **fragment minh họa**; `.invalid` là địa chỉ cố ý không thể deploy, dùng để tránh gây ra thao tác phát hành thật trong bài.

### 5.1. `id` là khóa tra credentials, không phải quyền

Ví dụ một publisher job có `settings.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>release-write</id>
            <username>${env.MVN_PUBLISH_USER}</username>
            <password>${env.MVN_PUBLISH_TOKEN}</password>
        </server>
    </servers>
</settings>
```

`release-write` **phải khớp** `<distributionManagement><repository><id>` nếu Maven Deploy Plugin cần dùng credential đó.

**Nhưng:** ID là **tên cấu hình local**, không phải một role được Maven tạo và không buộc server chỉ cho release-write. Quyền đúng phải được cấp ở repository manager:

```text
identity:  release-publisher
actions:   read + upload ONLY
scope:     approved release repository / approved groupId
deny:      snapshots nếu không cần; delete; overwrite; manage permissions
```

Tên các `actions` trên là **mô hình policy**, không phải cú pháp ACL áp dụng chung cho Nexus/Artifactory/Central Portal. Mỗi nền tảng có UI/API quyền riêng.

### 5.2. Khác biệt giữa `mvn install` và `mvn deploy`

```bash
mvn -B clean install
```

thường build/test và chép artifacts vào **local Maven repository**. Điều đó không cần remote publisher token.

```bash
mvn -B clean deploy
```

đi qua default lifecycle tới phase deploy, rồi Maven Deploy Plugin có thể upload artifact/POM/attached artifacts và metadata đến **remote repository**.

`mvn deploy` **không mặc định** làm phát hành Maven Central; nó đi tới **đích được cấu hình** và chỉ khi credentials/quyền/network chính xác. Đối với Central Portal hiện đại, cách publish có thể cần **plugin/API riêng của provider** thay vì tin mọi repository hỗ trợ Maven Deploy Plugin truyền thống. Kiểm tra tài liệu publisher đang dùng trước khi thiết kế job.

### 5.3. Vì sao publisher job không nên có quyền ký?

Nếu publisher token bị lộ, kẻ tấn công có thể thử upload artifacts không được phép. Nếu cùng job còn giữ private signing key, kẻ đó có thể ký artifact giả dưới trusted identity, khiến sự cố nặng hơn.

Khi tổ chức có mức bảo đảm cao, thiết kế:

```text
Build/test job  --artifact SHA-256-->  Signer job/service
    read-only                           signing-only identity
                                             |
                                             v
                                   signatures + attestation
                                             |
                                             v
                                    Publisher/promotion job
                                   publish-only token + approval
```

Mỗi job cần xác minh **cùng artifact digest** khi nhận artifact từ bước trước. Không chạy lại `mvn package` để vô tình tạo JAR bytes khác rồi ký hoặc publish bản mới.

## 6. Ký artifact: chữ ký không phải mật khẩu deploy

Với Maven artifacts, một cách truyền thống là **Maven GPG Plugin** tạo OpenPGP **detached signatures** (thường có phần mở rộng `.asc`) cho JAR, POM và attached artifacts. Consumer dùng trusted public key để xác minh.

- **Public key** có thể chia sẻ để verify.
- **Private signing key** phải được giữ bí mật.
- **Passphrase** bảo vệ private key khi được lưu/nhập, nhưng passphrase không phải repository upload password.
- **Signing authority** quyết định key nào được phép ký release nào.
- **Publishing authority** quyết định principal nào được upload artifact tới repository nào.

`GPG Plugin:sign` không cấp quyền `mvn deploy`; `mvn deploy` không tự tạo chữ ký nếu plugin ký chưa được cấu hình/chạy.

### 6.1. Chữ ký GPG và SHA-256 có trách nhiệm khác nhau

| Cơ chế | Trả lời | Không tự trả lời |
| --- | --- | --- |
| SHA-256 của JAR | Bytes file có khớp expected digest không? | Ai tạo, ai ký, trusted hay không |
| OpenPGP signature `.asc` | Signature có hợp lệ với public key tương ứng không? | Public key có đúng trusted release key không |
| Maven GAV/version | Artifact được đặt tên ở repository thế nào? | Artifact bytes có đúng release approved không |
| Git signed tag | Tag object được ký bởi Git signing key nào? | Artifact JAR có được tạo đúng từ tag không |
| Provenance/attestation | Artifact digest gắn source/build/builder nào? | Chính sách trust được thỏa nếu chưa verify signer |
| Repository ACL | Ai có thể upload/đọc theo server policy | Artifact có an toàn khi runtime hay không |

Một signature **valid** với một public key **không đồng nghĩa key đó đáng tin**. Cần so fingerprint/identity với danh sách trusted release keys và kiểm tra hết hạn, thu hồi, rotation và policy.

### 6.2. GPG detached signatures không giống `jarsigner`

Maven GPG Plugin thường tạo **file chữ ký bên ngoài artifact**. `jarsigner` có thể ký theo cơ chế Java JAR signatures với entries bên trong ZIP/JAR. Hai cách có packaging, tool verify và chính sách trust khác nhau.

Trong bài này, **ký artifact** nghĩa là detached OpenPGP signatures cho artifacts/POM, **không** đồng nghĩa JAR đã được `jarsigner` theo cơ chế runtime Java.

### 6.3. Ai được sử dụng khóa ký?

Một mô hình tốt:

```text
Release signing key
    |
    +-- chỉ được dùng bởi protected signer job/service
    +-- chỉ sau khi kiểm tra artifact digest và approval
    +-- không xuất private key cho PR/test jobs
    +-- audit mỗi lần ký và identity caller
    +-- rotate/revoke theo policy
```

Nếu có HSM/KMS hoặc signing service hỗ trợ định dạng cần dùng, nên cho CI **gọi thao tác ký** thay vì tải private key ra runner. **Không giả định mọi HSM/KMS tạo được OpenPGP `.asc` theo GPG Plugin**; phải kiểm tra tích hợp của provider. Nếu dùng GPG software key, giảm thời gian lộ bằng isolated runner, secret injection và xóa ephemeral key material sau job theo quy trình kiểm soát.

## 7. `Maven GPG Plugin 3.2.8`: cấu hình và thực hành an toàn

Maven GPG Plugin có goal:

```text
org.apache.maven.plugins:maven-gpg-plugin:3.2.8:sign
```

Tài liệu chính thức mô tả goal `gpg:sign` ký project artifact, POM và attached artifacts; thường bind vào phase `verify`.

Ví dụ **chỉ trong release-sign profile**, không ép mọi người build local phải có khóa:

```xml
<profiles>
    <profile>
        <id>release-sign</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-gpg-plugin</artifactId>
                    <version>3.2.8</version>
                    <configuration>
                        <bestPractices>true</bestPractices>
                    </configuration>
                    <executions>
                        <execution>
                            <id>sign-release-artifacts</id>
                            <phase>verify</phase>
                            <goals>
                                <goal>sign</goal>
                            </goals>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
```

Đây là **POM fragment**; trong lab hoàn chỉnh bên dưới nó nằm trong `<project>`.

`bestPractices=true` yêu cầu plugin chặn các cách đưa passphrase không an toàn mà plugin nhận diện (từ 3.2.0). Với workstation, dùng **GPG agent** để nhập/cached passphrase. Với CI non-interactive, dùng đường truyền bí mật được plugin hỗ trợ, ví dụ **`MAVEN_GPG_PASSPHRASE` do secret manager inject**, không tự ghi thẳng vào POM hoặc command.

### 7.1. Những cách không nên làm

**Không** dùng:

```bash
mvn deploy -Dgpg.passphrase=actual-secret
```

Vì command-line arguments có thể lộ qua shell history, process table và logs. Maven GPG Plugin hiện cảnh báo/deprecate tham số này; với `bestPractices=true`, các pattern không an toàn có thể làm job fail.

**Không** đưa private key hoặc passphrase vào:

```text
pom.xml
src/main/resources
src/test/resources
.gitignore-đã-bỏ-quên-file-bí-mật
CI log/artifact bundle
container image layer
cached home directory dùng chung
```

`.gitignore` không cứu được một secret đã từng commit; cần revoke/rotate và dọn lịch sử theo quy trình. Một bí mật được “mã hóa” sơ sài nhưng được lưu chung với khóa giải mã cũng không còn là bí mật an toàn.

### 7.2. Verify detached signature

Giả sử người phát hành cung cấp:

```text
artifact-privilege-lab-1.0.0.jar
artifact-privilege-lab-1.0.0.jar.asc
```

Và bạn đã nhập **public key đúng** vào keyring theo quy trình xác thực fingerprint riêng:

```bash
gpg --verify artifact-privilege-lab-1.0.0.jar.asc artifact-privilege-lab-1.0.0.jar
```

`gpg --verify` cần trả exit code thành công với cryptographic signature hợp lệ. Sau đó **xem fingerprint** và so với trusted signer identity qua kênh đáng tin:

```bash
gpg --list-keys --fingerprint
```

Nếu chữ ký hợp lệ nhưng key lạ/không được ủy quyền, **không** đánh dấu release đáng tin. Nếu `.asc` của Maven GPG Plugin ở vị trí khác, lấy đúng signatures từ `target/`, build artifacts hay repository publish output; **không suy đoán path cố định**.

### 7.3. So digest trước và sau ký

Một detached signature không cần thay đổi bytes JAR được ký. Bạn có thể tính:

```bash
sha256sum target/artifact-privilege-lab-1.0.0.jar
```

trước và sau khi ký, kiểm tra **JAR hash không đổi**. Signature file có hash riêng nếu muốn lưu record.

Nếu có bước repack/shade/transform artifacts **sau khi ký**, chữ ký có thể không còn khớp final JAR. Quy trình đúng là **chốt final bytes rồi mới ký**, hoặc ký lại chính bytes đã transform và phê duyệt.

## 8. POM Java 17 hoàn chỉnh: chạy bình thường không cần publish/sign

Dự án lab sử dụng plugin versions cụ thể. Đường dẫn release repository trong `distributionManagement` dùng `.invalid` để **không vô tình publish ra đích thật**. Build và tests hoạt động bình thường qua Maven Central hoặc approved mirror; chỉ **`deploy`** mới cố dùng URL minh họa.

### 8.1. Cây thư mục

```text
artifact-privilege-lab/
├── pom.xml
└── src/
    ├── main/java/org/example/security/ReleaseApp.java
    └── test/java/org/example/security/ReleaseAppTest.java
```

Dùng **Maven 3.9.x**, **JDK 17+**, network/mirror đủ để resolve public test dependency và plugins. Không cần có GPG private key hoặc remote publisher token để chạy `mvn clean verify`.

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>artifact-privilege-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Artifact Privilege Lab</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
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
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>org.example.security.ReleaseApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
        </plugins>
    </build>

    <distributionManagement>
        <repository>
            <id>release-write</id>
            <url>https://repo.example.invalid/maven/releases</url>
        </repository>
        <snapshotRepository>
            <id>snapshot-write</id>
            <url>https://repo.example.invalid/maven/snapshots</url>
        </snapshotRepository>
    </distributionManagement>

    <profiles>
        <profile>
            <id>release-sign</id>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-gpg-plugin</artifactId>
                        <version>3.2.8</version>
                        <configuration>
                            <bestPractices>true</bestPractices>
                        </configuration>
                        <executions>
                            <execution>
                                <id>sign-artifacts</id>
                                <phase>verify</phase>
                                <goals>
                                    <goal>sign</goal>
                                </goals>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </profile>
    </profiles>
</project>
```

**Ba hành vi khác nhau từ cùng POM:**

1. `mvn clean verify`: build và test **không có signing job**, không chạm remote deployment.
2. `mvn -Prelease-sign clean verify`: build/test, sau đó **ký** ở `verify` nếu một GPG signer/key đã được cấu hình hợp lệ.
3. `mvn -Prelease-sign clean deploy`: build/test/ký rồi **thử publish** tới URL ở `distributionManagement` với credentials và quyền server phù hợp.

**Điểm an toàn được thiết kế:** profile ký **không active by default**; repository URLs cố ý giả. **Không chạy ví dụ `deploy` nguyên văn** để mong nó thành công. Muốn phát hành thật cần thay destinations, cấp ACL, chuẩn bị signing identity, CI approvals và verify artifact sau upload.

### 8.3. `src/main/java/org/example/security/ReleaseApp.java`

```java
package org.example.security;

public final class ReleaseApp {
    private ReleaseApp() {
    }

    public static String message() {
        return "ARTIFACT PRIVILEGES: SEPARATE";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Không có dependency runtime bên ngoài JDK, nên JAR có thể chạy bằng `java -jar` nhờ manifest `Main-Class` được cấu hình ở Maven JAR Plugin.

### 8.4. `src/test/java/org/example/security/ReleaseAppTest.java`

```java
package org.example.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class ReleaseAppTest {
    @Test
    void textIsDeterministic() {
        assertEquals("ARTIFACT PRIVILEGES: SEPARATE",
                     ReleaseApp.message());
    }

    @Test
    void textMentionsPrivileges() {
        assertTrue(ReleaseApp.message().contains("PRIVILEGES"));
    }
}
```

JUnit Jupiter 5 cho phép package-private test classes/methods; tên `ReleaseAppTest` theo convention Surefire, do đó Surefire Plugin 3.6.1 có thể chạy hai tests khi dependencies đã được resolve.

### 8.5. Chạy ở local hoặc PR CI bằng read-only

Từ thư mục gốc:

```bash
java -version
javac -version
mvn -version
mvn -B clean verify
```

Các outputs mong đợi:

```text
target/classes/org/example/security/ReleaseApp.class
target/test-classes/org/example/security/ReleaseAppTest.class
target/surefire-reports/TEST-org.example.security.ReleaseAppTest.xml
target/artifact-privilege-lab-1.0.0.jar
```

**Dòng tóm tắt dự kiến** của hai tests:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

Còn khi chạy JAR:

```bash
java -jar target/artifact-privilege-lab-1.0.0.jar
```

**Stdout chính xác của chương trình**:

```text
ARTIFACT PRIVILEGES: SEPARATE
```

Đây là **một chương trình runnable hoàn chỉnh**: class đúng package, method `main` đúng chữ ký, JAR có Main-Class, JUnit tests phù hợp Java 17.

**Không có nghĩa** build trên public Central cần `settings.xml` chứa secrets. Nếu chỉ đọc public dependencies/plugins, Maven mặc định có thể resolve qua Central mà không cần token.

### 8.6. Thực hiện dry-run an toàn không cần kho thật

Bạn có thể kiểm tra POM, tests, JAR và artifact digest bằng:

```bash
mvn -B clean verify
jar tf target/artifact-privilege-lab-1.0.0.jar
```

Đọc manifest:

```bash
unzip -p target/artifact-privilege-lab-1.0.0.jar META-INF/MANIFEST.MF
```

Lệnh `unzip -p` cần công cụ `unzip` được cài đặt; trên Windows có thể mở JAR bằng một ZIP tool. Không cần chạy `deploy` để kiểm thử compile/test code. Nếu không có công cụ `unzip`, `jar tf` vẫn dùng được để xem entry names nhưng không tự in nội dung manifest.

Tính hash bằng Linux/macOS:

```bash
sha256sum target/artifact-privilege-lab-1.0.0.jar
```

hoặc Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\target\artifact-privilege-lab-1.0.0.jar
```

Hash **không có giá trị cố định để chép vào README**, vì nó phụ thuộc bytes JAR thật. Dùng output trên chính file đã build và lưu vào release record nếu cần phát hành.

### 8.7. Profile ký cần khóa thật nhưng không được xuất bản lẫn trong nguồn

Khi đã chuẩn bị một signer được ủy quyền:

```bash
mvn -B -Prelease-sign clean verify
```

có thể tạo signatures của project artifacts/POM. Đây là **lệnh chỉ dành cho signing environment đã cấu hình**, không có key thì job sẽ báo lỗi, và đó là **đúng chính sách** thay vì tự ký bằng key không rõ nguồn.

`bestPractices=true` không tự tạo GPG key, không phân quyền người dùng; nó kiểm tra các cách dùng secrets mà plugin có thể nhận diện. Quyền dùng private key phải được **signing service/GPG home/runner policy** thực thi.

## 9. Ranh giới giữa build, sign và publish trong CI

Có hai mức thiết kế khác nhau.

### 9.1. Mức cơ bản: một release job dùng Maven profile ký

```text
Protected release tag + approval
         |
Maven clean verify với profile release-sign
         |
Signature files + JAR + POM
         |
Maven deploy tới release repository
```

Ưu điểm: triển khai quen thuộc, đơn giản với Maven GPG Plugin. Nhược điểm: **nếu private key được inject từ đầu job**, build plugins, test code hoặc scripts cùng job có thể chạm được secret. Do đó level này **không đạt cách ly signer tuyệt đối**.

**Cần thêm:** protected runners/branches, approvals, plugin/dependency trust, runner isolation, không chạy untrusted PR code với secrets, token ngắn hạn, audit.

### 9.2. Mức cách ly cao: signer độc lập với builder

```text
Untrusted/ordinary build job
    - chỉ read dependencies
    - compile + tests
    - không có signing key/publisher token
             |
             v
Immutable build artifact + SHA-256 + tests
             |
             v
Release approval/verify source and digest
             |
             v
Isolated signer
    - chỉ tải file đã được kiểm tra
    - không thực thi Maven project/scripts từ source
    - signing key ở HSM/KMS/agent được bảo vệ
    - xuất detached .asc
             |
             v
Publisher
    - chỉ upload exact approved bytes/signatures/POM
    - có token write giới hạn namespace
    - không cầm signing key
```

Ở mô hình này, có thể dùng signing service hoặc GPG CLI trên **file JAR được truyền an toàn**, không tái thực thi Maven goals từ POM có thể bị chỉnh. Nếu dùng công cụ `gpg` trực tiếp với key được cấu hình sẵn:

```bash
gpg --armor --detach-sign \
    --output artifact-privilege-lab-1.0.0.jar.asc \
    artifact-privilege-lab-1.0.0.jar
```

Lệnh minh họa thao tác ký **trong signer environment**, không phát hành tự động. Signer job cần nhận **expected SHA-256 từ approval record** và so trước khi ký. Với POM và các attached artifacts phải có chữ ký riêng theo release policy; ký **một JAR** chưa đồng nghĩa đã ký tất cả Maven publication files.

### 9.3. Tại sao promotion tốt hơn rebuild ở job publish?

Giả sử:

```text
Job A: mvn clean verify -> JAR A -> tests PASS -> hash A
Job B: mvn clean deploy -> Maven rebuilds -> JAR B
```

Nếu job B tạo JAR bytes khác, artifact phát hành **không phải** artifact A từng được kiểm thử. Đúng hơn là **promote exact approved bytes** từ immutable staging artifact store, hoặc chứng minh hash A = hash B.

Các nguyên nhân làm JAR khác có thể là timestamp, SNAPSHOT dependency, plugin/JDK version, build ID nhúng trong resources, code generation, hoặc files khác. Điều này liên quan trực tiếp tới **an toàn phụ thuộc và supply-chain integrity**.

## 10. Access boundary trong CI: nơi secrets được phép xuất hiện

CI thường có ít nhất bốn ngữ cảnh:

| Job | Source trust | Network/data access | Bí mật được cấp |
| --- | --- | --- | --- |
| PR build | Có thể không tin cậy | Public/approved read-only deps | Không có publisher token/GPG private key |
| Protected branch build | Được kiểm soát hơn | Private read-only nếu cần | Read-only token tối thiểu |
| Release signer | Trusted approval/artifact | Artifact store + signing service | Quyền ký cụ thể, không có admin repo token |
| Release publisher | Trusted release gate | Repository release endpoint | Scoped publisher credential, không có GPG private key |

**Quyền cấp cho job phải phụ thuộc trust level của trigger**, không chỉ tên workflow. Một PR từ fork, event do user input điều khiển, hay workflow có thể bị chỉnh bởi contributor không nên được quyền dùng release secrets.

### 10.1. Protected tags và environment approvals

Chỉ build release từ **đúng commit/tag đã được phê duyệt**:

```bash
git rev-parse --verify HEAD
git rev-parse --verify "refs/tags/v1.0.0^{commit}"
```

Hai commit IDs phải khớp theo release policy. `refs/tags/v1.0.0^{commit}` peel annotated tag về commit. Nếu tổ chức yêu cầu **signed tags**, dùng `git tag -v` cùng trusted signing key policy. Ký Git tag vẫn **khác** ký Maven artifacts.

Release job nên chỉ chạy từ protected refs và protected environment có approvals. Không tự quyết định cấp token bằng một biến môi trường do người gửi PR tùy ý điền.

### 10.2. Token ngắn hạn, scope nhỏ, một job dùng một credential

Theo OWASP Secrets Management guidance, ưu tiên secrets có **TTL ngắn**, hỗ trợ rotation/revocation, giới hạn quyền và attribution. Nếu repository provider hỗ trợ OIDC/workload identity hoặc token exchange, có thể giảm long-lived credentials; **không suy rằng mọi Maven repository hỗ trợ OIDC trực tiếp**.

Nếu provider chỉ dùng user token/API key, vẫn nên:

- Tạo publisher identity riêng cho CI.
- Giới hạn repository/namespace và quyền upload.
- Đặt token ở protected environment secrets/secret manager.
- Tránh reuse personal admin token.
- Đổi token khi role/job/chính sách thay đổi hoặc nghi ngờ lộ.
- Không cấp token cho PR/test/reusable workflows không tin cậy.
- Thu hồi token và xem audit logs ngay khi có sự cố.

### 10.3. Không tin `masking` là biện pháp duy nhất

CI secret masking có giới hạn; token có thể bị biến đổi, encode, tách nhỏ, in qua exception hoặc gửi qua network. Một job có quyền đọc environment variables thường có khả năng dùng chính token đó.

**Không dựa vào giả định “log đã che token thì code độc hại không lấy được token”.** Hạn chế job access, network egress, token scope/TTL và hành động từ code không tin cậy.

## 11. Bảo vệ `settings.xml` và GPG credentials

### 11.1. Các vị trí thông dụng

Maven có user settings:

```text
~/.m2/settings.xml
```

và global settings:

```text
${maven.home}/conf/settings.xml
```

Người dùng có thể chỉ định settings khác bằng:

```bash
mvn -s path/to/settings.xml clean verify
```

Điều đó **không** tự bảo đảm path chứa bí mật được bảo vệ. CI nên tạo settings theo job, đặt file permissions thích hợp, xóa khi kết thúc theo chính sách và không upload nó như build artifact.

### 11.2. Secret injection với environment variables

Maven Settings Reference hỗ trợ interpolation của `${env.MVN_READ_TOKEN}` và các biến khác. Điều này tránh phải commit token literal, nhưng **environment variable vẫn có thể bị đọc bởi process trong cùng job**.

Một job **read-only** chỉ nên nhận env vars `MVN_READ_*` cần thiết. Một job **publish-only** mới nhận `MVN_PUBLISH_*`. Bước **signer** mới có quyền dùng key/passphrase hoặc signing service; không trộn các secrets vào global variables cho toàn workflow.

### 11.3. Maven 3 password encryption không phải secret vault

Apache Maven 3.x có cơ chế mã hóa password với `settings-security.xml`, nhưng tài liệu Maven nêu rõ tính bảo vệ ở mức **obfuscation-grade**, không chống lại kẻ tấn công có quyền đọc ciphertext và master material.

Do đó:

- Không coi password đã được Maven 3 encrypt là an toàn khi commit vào Git.
- Không lưu `settings.xml` và `settings-security.xml` công khai trong cùng workspace.
- Dùng file permissions hạn chế, secure secret manager/CI secrets.
- Kiểm soát quyền người dùng và vòng đời credentials.
- Maven 4 có cơ chế encryption khác; không áp giả định Maven 4 cho Maven 3.

### 11.4. Không dùng secrets làm Maven properties

Các lệnh kiểu:

```bash
mvn -Drepository.password=actual-secret deploy
```

có thể lộ qua process args/logs/history. Trong CI, dùng secure settings injection/credential providers hỗ trợ; không để credentials trong `.mvn/maven.config` hoặc `pom.xml`.

Tương tự với GPG passphrase: **không** dùng `-Dgpg.passphrase=...`. Dùng gpg-agent hoặc biến môi trường được CI inject an toàn theo Maven GPG Plugin docs, và bảo đảm key material không bị ghi vào logs/artifacts.

## 12. Phân quyền qua repository manager: policy phải được thử bằng server

Một repository manager có thể phục vụ:

```text
maven-public-group    đọc dependencies
maven-snapshots       upload SNAPSHOT
maven-releases        upload immutable releases
quarantine           kiểm tra artifacts nguồn ngoài
staging              nơi xét duyệt trước khi promote
```

Tên trong sơ đồ là **ví dụ tổ chức**, không phải Maven tự khởi tạo các repositories này.

### 12.1. Policy read-only

- Cho phép đọc POM/JAR/metadata trong những namespaces cần thiết.
- Không được upload, overwrite, delete hoặc thay ACL.
- Giới hạn việc xem artifact private/mã nguồn nếu cần.
- Audit hành vi truy cập bất thường.
- Dùng TLS và hạn chế repository URLs/egress.

### 12.2. Policy snapshot publisher

- Chỉ cho upload tới SNAPSHOT repository.
- Chỉ những namespaces do project/team sở hữu.
- Nếu cho nhiều snapshots cùng version, có retention/quota/audit.
- Không được upload release hoặc xóa release.
- Không có signing key phát hành.

### 12.3. Policy release publisher

- Chỉ upload release coordinates đã được phê duyệt.
- Cấm overwrite release GAV đã tồn tại.
- Không có quyền delete/modify ACL theo mặc định.
- Gắn CI identity, source commit, artifact digest và approval record.
- Phải verify signatures/provenance theo policy nếu repository hỗ trợ; nếu không, một gate riêng phải thực thi.
- Dùng short-lived token nếu provider có hỗ trợ.

### 12.4. Policy signer

- Chỉ được ký artifacts thuộc project/version/commit đã duyệt.
- Private key không xuất ra worker nếu có thể dùng signing service.
- Không có quyền publish tùy ý tới repository.
- Tạo audit record gắn artifact digest, key ID/fingerprint, caller và time.
- Có quy trình revoke/rotate, xử lý key compromised.

### 12.5. Admin không phải signer

Repo admin có thể quản lý users/ACLs, repository config, retention, staging. Nhưng **không nên tự được cấp private release signing key**. Nếu một tài khoản có cả server admin, publisher và signer, vùng ảnh hưởng khi bị chiếm quyền rất lớn.

## 13. Những đường vòng phải xem khi thiết kế quyền publish

### 13.1. `deploy:deploy-file`

Maven Deploy Plugin ngoài `deploy:deploy` còn có:

```text
deploy:deploy-file
```

Goal này có thể publish **một file do caller chỉ định**, không nhất thiết tạo từ project Maven hiện tại. Vì vậy chỉ giới hạn pipeline script vào `mvn deploy` **không phải security boundary** nếu credential vẫn cho upload tùy ý.

**Đường phòng vệ thật:** server-side ACL theo namespace, release immutability, approval và audit mọi upload.

### 13.2. `-DaltDeploymentRepository`

Maven Deploy Plugin có các tham số cho deployment target khác POM khi dùng goal/version phù hợp. Một người điều khiển command line có thể cố chỉ sang repository khác.

Nếu credential bị cấp quá rộng, thay URL có thể mở khả năng publish trái phép. **Không** xem `distributionManagement` cố định trong POM là hàng rào đủ mạnh; bảo vệ destination/identity tại repository và CI policy.

### 13.3. Plugin/build extension tùy ý

Một POM có thể chứa Maven plugins hoặc extensions thực thi code trong build. Nếu CI runner có secrets, plugin scripts hoặc test code có thể đọc chúng trong cùng process/job.

Do đó build/test phải chạy **trước khi** cấp release secrets trong một môi trường bị cô lập. Không trộn untrusted plugin goals và signing key trong cùng job nếu policy đòi cách ly cao. Chỉ allow-approved plugins/repositories, pin versions và theo dõi dependency provenance.

### 13.4. Repository proxy/namespace confusion

Nếu một dependency private có `groupId:artifactId` trùng artifact trong public repository, resolver có thể tải nhầm nguồn nếu mirror/repo policy yếu hoặc internal artifact chưa được quản lý đúng. Đây là một hình thức supply-chain risk thường gọi **dependency confusion**.

Giải pháp gồm: thống nhất repository manager, kiểm soát nguồn upstream, ưu tiên internal namespace đúng policy, khóa versions/digests, cấm publish trái phép vào groupId của tổ chức. **Read-only client credential không tự loại rủi ro dependency confusion**.

### 13.5. SNAPSHOT overwrite

Trong nhiều repository managers, SNAPSHOT artifacts có thể được cập nhật thường xuyên. Vì thế snapshot publisher token **không nên dùng cho release publication**. Consumer release không nên phụ thuộc SNAPSHOT không được khóa/attest.

Quyền upload SNAPSHOT nên nằm ở project sandbox hoặc repository riêng, có audit và retention. Release immutable repository cần chính sách riêng.

## 14. Xác minh artifact đã ký trước khi consumer sử dụng

Một consumer có thể thực hiện:

1. Resolve **đúng GAV**, classifier và repository đã được phê duyệt.
2. Tải **JAR/POM** và signatures tương ứng từ kênh đã kiểm soát.
3. Tính SHA-256 của file JAR thật.
4. So SHA-256 với release record hoặc attestation đáng tin.
5. Chạy `gpg --verify` cho chữ ký JAR và POM nếu policy yêu cầu.
6. So signer fingerprint với trust list, kiểm tra trạng thái key.
7. Đọc provenance gắn source commit, builder và artifact digest.
8. Kiểm tra vulnerability/license policy của dependencies.
9. Chỉ promote/deploy **đúng bytes** đã được kiểm thử/ký/duyệt.

**Đừng đánh đồng signature valid với software vô hại**. Ký chỉ gắn một key identity với bytes, không tự chạy malware scanning hoặc chứng minh code không có lỗ hổng.

### 14.1. Ví dụ các bản ghi cần lưu

```text
groupId=org.example
artifactId=artifact-privilege-lab
version=1.0.0
packaging=jar
sourceCommit=<full Git object ID của run đã duyệt>
ciRunId=<ID do CI cấp>
artifactSha256=<hash thật của final JAR>
signerFingerprint=<fingerprint đã xác minh>
testResult=<CI test summary đã kiểm chứng>
repository=<verified destination URL>
approval=<release approval record>
```

Đây là **mẫu schema minh họa**, không phải file có giá trị thật; các chuỗi trong dấu góc phải được thay bằng **dữ liệu thực do hệ thống kiểm chứng**. Không dùng chúng làm “bằng chứng” nếu chưa nối với file digest và CI run.

### 14.2. Test negative: quyền sai phải bị từ chối

Một kế hoạch kiểm tra ACL trên **test/staging repository riêng**:

| Test | Dùng identity | Hành động | Kỳ vọng |
| --- | --- | --- | --- |
| 1 | Reader | GET permitted artifact | Thành công |
| 2 | Reader | Upload canary artifact | Bị từ chối |
| 3 | Reader | Delete canary artifact | Bị từ chối |
| 4 | Snapshot publisher | Upload vào SNAPSHOT sandbox | Thành công |
| 5 | Snapshot publisher | Upload vào release sandbox | Bị từ chối |
| 6 | Release publisher | Upload release version mới được duyệt | Thành công |
| 7 | Release publisher | Overwrite same release GAV | Bị từ chối |
| 8 | Release publisher | Delete/modify ACL | Bị từ chối |
| 9 | Signer | Ký digest đã duyệt | Thành công |
| 10 | Signer | Dùng key ký digest ngoài policy | Bị từ chối |
| 11 | PR/test job | Đọc publisher/signing secrets | Không được cấp |
| 12 | Consumer | Verify signature đúng key | PASS |
| 13 | Consumer | Verify artifact bị sửa một byte | FAIL |

Điều kiện: test trên **môi trường có quyền kiểm thử rõ ràng**. Không sử dụng canary upload/delete vào repository release production hoặc secrets thật khi chưa có cơ chế rollback/approval.

## 15. Chính sách signing key lifecycle

### 15.1. Khởi tạo

- Chọn thuật toán/kích thước/expiry phù hợp chính sách.
- Tạo key trong môi trường tin cậy, ưu tiên hardware-backed nếu phù hợp.
- Tách signing identities theo dự án/tổ chức hoặc mức độ nhạy cảm.
- Ghi public key fingerprint và xác minh qua kênh độc lập.
- Định nghĩa ai được yêu cầu ký và artifact/digest nào hợp lệ.

### 15.2. Lưu giữ và sử dụng

- Private key không nằm trong Git repository hoặc artifact registry public.
- Không gửi private key qua chat, issue tracker hay email thường.
- Dùng gpg-agent hoặc signing service để hạn chế đọc raw key.
- Cấp quyền ký ngay trong protected signer job sau approval.
- Không chạy untrusted source scripts trong key-access environment.
- Audit từng lần ký và alert signing volume bất thường.

### 15.3. Rotate, revoke, recover

- Đặt rotation schedule theo risk/policy.
- Ghi nhận old/new fingerprint và giai đoạn chuyển tiếp.
- Khi key lộ: dừng phát hành, revoke/disable key, rotate credentials, thông báo consumers, đánh giá artifacts đã ký trong thời gian nghi ngờ.
- Không cho phép một private key bị thu hồi tiếp tục ký các releases mới.
- Tách cơ chế **revocation** khỏi **deletion**: consumers có thể vẫn cần verify artifact lịch sử theo policy và thời điểm ký, dù khóa đã ngừng sử dụng.

### 15.4. Phân biệt ba thứ tự bị lộ

| Bị lộ | Hậu quả tiềm năng | Ưu tiên xử lý |
| --- | --- | --- |
| Read token | Truy cập trái phép private dependency/metadata | Revoke token, điều tra downloads, rà data exposure |
| Publish token | Upload artifact trái phép/ghi đè nếu ACL yếu | Revoke, freeze repository, audit uploads, verify digests |
| Private signing key | Ký binaries giả dưới trusted identity | Stop signing, revoke/rotate key, đánh giá signatures/publications |

Không xử lý lộ private signing key chỉ bằng cách đổi publisher password; hai authority độc lập.

## 16. Các lỗi và ngộ nhận thường gặp

| Hiện tượng/ngộ nhận | Nguyên nhân hoặc giới hạn | Cách xử lý |
| --- | --- | --- |
| Reader token vẫn upload được | Token cấp quyền server quá rộng | Sửa repository ACL, cấp token mới |
| POM có `<server>` mà nghĩ tạo permission | `<server>` chỉ tra credentials | Thiết lập ACL ở server/IAM |
| `mvn verify` thất bại với GPG key | Profile signing bị active ngoài ý muốn | Chỉ kích hoạt profile trên trusted release job |
| Deploy báo 401 | Credential thiếu/sai/hết hạn | Kiểm tra server ID/secret injection |
| Deploy báo 403 | Principal không có quyền action/repo | Kiểm tra ACL, không tăng quyền bừa |
| Deploy được snapshot nhưng không release | Tài khoản bị scope theo repo | Dùng publisher identity đúng release, qua approval |
| Deploy sang repository khác | `altDeploymentRepository`/cấu hình job khác | Khóa target và server-side namespace scope |
| GPG “Good signature” với key lạ | Cryptographic validity ≠ trust | So fingerprint với allowlist |
| JAR `.asc` không verify | File bị thay, sai signature/file/key | So đúng bytes và signing key |
| `-Dgpg.passphrase` bị từ chối | `bestPractices` chặn cách xử lý secret yếu | Dùng agent/env secrets do platform cấp |
| `settings.xml` mã hóa nhưng vẫn rò secret | Maven 3 encryption chỉ mức obfuscation | Secret manager và quyền file |
| CI PR có quyền dùng publisher token | Secret được cấp sai trust boundary | Protected environment, job isolation |
| GPG private key nằm trong container image | Layer/image/cache có thể bị trích xuất | Không đóng key vào image |
| GPG key có trên runner dùng chung | Runner bị chiếm quyền/đọc chéo | Ephemeral signer runner/service |
| Snapshot token ghi đè release được | ACL quá rộng | Phân tách repos/permissions |
| Release repository cho overwrite same GAV | Immutability chưa bật | Disable overwrite, audit changes |
| Tests PASS nhưng artifact deploy khác hash | Rebuild giữa sign/publish jobs | Promote exact approved bytes |
| Signed JAR nhưng POM unsigned | Signing workflow chỉ xử lý JAR | Ký POM/attached artifacts theo policy |
| Signature tồn tại nhưng version không đúng | Thiếu approval GAV/commit gate | So source tag, version, digest |
| `mvn deploy` gửi credential vào sai host | Mirror/server/URL bị chỉnh | Allowlist endpoint, config review, hạn chế egress |
| Consumer tin checksum cùng kênh bị thay | Artifact và hash cùng bị sửa | Trusted digest/attestation |
| Một service account dùng chung 5 teams | Không scope namespace | Tách service accounts theo repo/team |
| Admin token được đặt trong mọi build | Quyền quá rộng và phát tán | Dùng role tối thiểu, secret broker |
| `gpg --verify` PASS ⇒ phần mềm sạch | Signature không scan vulnerabilities | Scan/QA source, binary, provenance |
| Central Portal publish không dùng `mvn deploy` trực tiếp | Provider flow/API/plugin khác truyền thống | Đọc docs provider; đừng suy khả năng của repo |
| Mở private repo rộng cho public PR | Untrusted workflow cần secrets | Dùng review, isolate và least privilege |

### 16.1. Runbook khi nghi ngờ bị lộ credentials

1. **Dừng jobs có quyền sign/publish**, thu hồi token/key bị nghi ngờ lộ.
2. Bảo toàn audit logs, CI run IDs, repository upload history.
3. Xác định loại credential bị lộ: read, publish, sign hay admin.
4. Xem phạm vi repo/namespace, token TTL và workflow nào từng được cấp.
5. So SHA-256/signatures của artifacts mới được publish với approved release records.
6. Với key ký: xác minh thời điểm signing bất thường, thu hồi/rotate theo policy.
7. Khôi phục releases bằng artifact bytes đáng tin, không chỉ đổi version text.
8. Rotate các secrets liên quan và điều chỉnh server ACL/protected environment.
9. Rà lại CI untrusted triggers, `settings.xml`, POM plugins, runner egress.
10. Viết post-incident review, bổ sung kiểm thử negative permissions.

**Không giải quyết sự cố bằng cách xóa ngay logs hoặc overwrite lại JAR**: điều đó có thể làm mất bằng chứng và làm consumers không biết bản nào từng bị ảnh hưởng.

## 17. Thiết kế policy cho các tổ chức quy mô khác nhau

### 17.1. Nhóm nhỏ, một repository manager

Mô hình tối thiểu:

- `read-only` token cho developers/CI tests.
- `snapshot-publisher` token cho development pipeline, chỉ SNAPSHOT namespace.
- `release-publisher` token cho protected release workflow.
- Signing key dùng trong protected release environment, không ở PR workflow.
- Release repository immutable; có approval và audit.
- CI build trước, upload đúng artifact đã pass tests.

Nếu chưa đủ nguồn lực cho signer job độc lập, ít nhất dùng protected runner và chỉ inject key sau khi trust gates đã đạt; **ghi nhận đây là mức cách ly thấp hơn**.

### 17.2. Tổ chức nhiều teams/tenants

- ACL theo team namespace và repository.
- Không dùng publisher token “toàn công ty”.
- Separations of duties giữa owner source, release approver và registry admin.
- HSM/signing service với policy theo artifact digest/project.
- Repository manager whitelist upstreams, quarantine unknown artifacts.
- Audit phát hành gắn Git commit, CI run, GAV, SHA-256 và signer fingerprint.
- Controlled promotion staging → release thay vì rebuild không đối chiếu.

### 17.3. Dự án open-source phát hành ra Maven Central

Ngoài nguyên tắc chung:

- Đăng ký/kiểm soát namespace của tổ chức.
- Dùng **credential/token có quyền đúng namespace**, scope theo khả năng provider.
- Ký theo định dạng/quy trình hiện tại của publisher.
- Không coi Maven `<distributionManagement>` + `mvn deploy` là cách publish duy nhất cho mọi hạ tầng mới.
- Xác minh **Sonatype Central Portal** hoặc provider docs mới nhất về token, bundle/upload, publishing plugin và yêu cầu signature.
- Giữ secret ở CI protected environment, không publish từ untrusted PR.

**Không chép một ví dụ Central Portal token thật vào bài** vì tokens gắn tài khoản/namespace riêng; phương thức phát hành có thể thay đổi theo provider.

## 18. Câu hỏi tự kiểm tra

**1.** `settings.xml` `<server><id>release-write</id>` có tạo quyền upload không?  
**Đáp án:** Không. ID là khóa tra credential; quyền nằm ở repository/IAM.

**2.** Developer chạy `mvn verify` có cần token release publisher không?  
**Đáp án:** Không nếu chỉ đọc dependencies cần thiết.

**3.** Publisher token có nên ký artifacts không?  
**Đáp án:** Không mặc định; signing identity là quyền riêng.

**4.** `distributionManagement` khác `repositories` thế nào?  
**Đáp án:** Một bên mô tả đích upload, bên kia các nguồn đọc dependencies.

**5.** Vì sao publisher token nên scope theo namespace?  
**Đáp án:** Giảm khả năng upload packages giả sang dự án/team khác.

**6.** Read-only token có thể bị lộ thông tin không?  
**Đáp án:** Có; nó có thể tải private artifacts/metadata trong phạm vi được cấp.

**7.** Public key có cần bí mật không?  
**Đáp án:** Không, nó dùng verify; cần kiểm chứng fingerprint và nguồn tin cậy.

**8.** Private signing key có nên có trên PR runner không?  
**Đáp án:** Không.

**9.** Maven GPG Plugin `sign` chạy vào phase nào thường gặp?  
**Đáp án:** Có thể bind `verify` để ký artifacts/POM trước deploy.

**10.** `bestPractices=true` có thay role ACL không?  
**Đáp án:** Không; nó kiểm soát cách dùng secrets do plugin nhận diện.

**11.** `mvn deploy` có ký JAR tự động không?  
**Đáp án:** Không nếu không có signing configuration/goal tương ứng.

**12.** Một `.asc` valid có chứng minh key đáng tin không?  
**Đáp án:** Không; so fingerprint và trust policy.

**13.** Tại sao Maven 3 password encryption không phải vault?  
**Đáp án:** Cơ chế bảo vệ ở mức obfuscation, cần secret manager và quyền file.

**14.** Vì sao tránh `-Dgpg.passphrase`?  
**Đáp án:** Có thể lộ qua process arguments, history/logs.

**15.** Dùng một release job có cả Maven build và signing key có rủi ro gì?  
**Đáp án:** Plugins/test code trong cùng job có thể truy cập secret.

**16.** Cách ly signing job tốt hơn như thế nào?  
**Đáp án:** Chỉ nhận final artifacts đã kiểm tra và không chạy untrusted Maven POM/scripts.

**17.** `mvn install` có upload remote artifacts không?  
**Đáp án:** Không; nó ghi vào local repository theo mặc định.

**18.** `deploy:deploy-file` có thể publish file không do project build không?  
**Đáp án:** Có; vì vậy bảo vệ ở server-side ACL.

**19.** Vì sao cần cấm overwrite release GAV?  
**Đáp án:** Ngăn binary thay bytes trong khi version/coordinates giữ nguyên.

**20.** SHA-256 và chữ ký có thay thế test/security scanning không?  
**Đáp án:** Không; chúng kiểm tra identity/integrity, không đánh giá code có lỗ hổng.

**21.** Read job được gắn mirror read token nhưng có thật read-only chưa?  
**Đáp án:** Chỉ khi token bị giới hạn ở server và đã kiểm thử quyền.

**22.** Nếu private key lộ, chỉ đổi repository password đủ chưa?  
**Đáp án:** Không; cần revoke/rotate key và rà artifact/signature history.

**23.** `gpg --verify` trên artifact đã đổi một byte nên thế nào?  
**Đáp án:** Detached signature phải fail nếu nội dung đã ký bị đổi.

**24.** Lệnh `mvn -Prelease-sign clean deploy` của lab có publish thật được không?  
**Đáp án:** Không nguyên văn: URL dùng `.invalid`, và cần trusted signing/publisher setup đúng.

**25.** Ai nên có quyền sửa repository ACL?  
**Đáp án:** Principal quản trị chuyên trách, không phải read/publish/sign job thông thường.

**26.** Vì sao provider-specific publishing docs quan trọng?  
**Đáp án:** Có nơi dùng Central Portal/API/plugin workflow khác Maven Deploy Plugin cơ bản.

**27.** Một signed tag Git có đồng nghĩa JAR được GPG ký?  
**Đáp án:** Không; đó là hai đối tượng và quy trình khác nhau.

**28.** Quy tắc an toàn cốt lõi khi phân quyền Maven artifacts?  
**Đáp án:** **Đọc, publish và ký phải được giới hạn như ba năng lực riêng**, gắn repo/namespace/job/time/approval.

## 19. Checklist review quyền trước phát hành

- [ ] Các read-only principals chỉ có quyền cần thiết trên các repos phù hợp.
- [ ] Không có publisher token/secret signing key trong PR build.
- [ ] Snapshot publisher không ghi release repository.
- [ ] Release publisher chỉ ghi namespace/version theo policy và không xóa/overwrite.
- [ ] Repository ACL được kiểm tra **phía server**, không chỉ đọc Maven POM.
- [ ] Credentials không nằm trong Git, POM, `.mvn/maven.config`, logs hoặc artifacts.
- [ ] `settings.xml` dùng IDs phù hợp; mirror IDs không bị bỏ sót.
- [ ] Environment variables và secret manager được scope theo từng job.
- [ ] Token có TTL/rotation/revocation và audit đủ.
- [ ] Có approval cho protected release tags/environments.
- [ ] Chỉ build từ commit/tag được kiểm chứng.
- [ ] GPG private key không nằm trên builder untrusted.
- [ ] GPG `bestPractices=true` hoặc cơ chế bảo vệ tương đương được áp theo môi trường.
- [ ] Không truyền passphrase bằng CLI arguments.
- [ ] Signer fingerprint/trust list/rotation policy được quản lý.
- [ ] Ký **final JAR/POM/attached artifacts** theo policy.
- [ ] Verify `.asc`, SHA-256 và provenance trên chính file sẽ publish.
- [ ] Không rebuild sau QA mà không so artifact digest.
- [ ] Không cho release GAV overwrite; có retention/rollback.
- [ ] Negative tests chứng minh reader cannot upload và publisher cannot delete.
- [ ] Kiểm soát `deploy-file`/alt destination ở repository policy.
- [ ] Public dependency origin, private namespace và mirrors đã được xét.
- [ ] Không coi Maven 3 settings encryption là nơi lưu trữ bí mật an toàn.
- [ ] Có audit logs cho upload, signing, ACL changes, token issuance.
- [ ] Khi nghi lộ key/token, có quy trình freeze/revoke/rotate và thông báo consumers.
- [ ] Quy trình Central Portal/provider-specific được kiểm chứng nếu dùng registry đó.

## 20. Tài liệu tham khảo chính thức

1. [Apache Maven — Settings Reference](https://maven.apache.org/settings.html) — `servers`, `mirrors`, môi trường, credentials.
2. [Apache Maven — Security and Deployment Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html) — server IDs, nơi đặt credentials.
3. [Apache Maven Deploy Plugin — Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html) — `distributionManagement`, `deploy`, `deploy-file`.
4. [Apache Maven Deploy Plugin — Plugin Details](https://maven.apache.org/plugins/maven-deploy-plugin/plugin-info.html) — requirements và plugin goals.
5. [Apache Maven GPG Plugin — Usage](https://maven.apache.org/plugins/maven-gpg-plugin/usage.html) — signing project artifacts và POM.
6. [Apache Maven GPG Plugin — gpg:sign](https://maven.apache.org/plugins/maven-gpg-plugin/sign-mojo.html) — goal, `bestPractices`, GPG signer.
7. [Apache Maven GPG Plugin — Deploy Signed Artifacts](https://maven.apache.org/plugins/maven-gpg-plugin/examples/deploy-signed-artifacts.html) — release signing workflow, agent/env.
8. [Apache Maven — Password Encryption (Maven 3)](https://maven.apache.org/guides/mini/guide-encryption.html) — giới hạn bảo vệ mật khẩu trong settings.
9. [Apache Maven — POM Reference](https://maven.apache.org/pom.html) — `distributionManagement`, repositories và profiles.
10. [Sonatype Central — Publish Portal API](https://central.sonatype.org/publish/publish-portal-api/) — provider-specific authentication và publishing.
11. [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) — least privilege, lifetime, rotation, CI secrets.
12. [GitHub Actions — Using Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) — job/environment secrets, fork PR và OIDC khi provider hỗ trợ.
13. [Git — git-tag](https://git-scm.com/docs/git-tag) — protected/signed release tag concepts.
14. [GnuPG — Documentation](https://gnupg.org/documentation/) — detached signing, verify, key management.

**Kết luận:** Trong Maven, **đọc** nghĩa là resolve/tải dependencies từ các nguồn đã duyệt; **publish** nghĩa là upload artifacts/POM/metadata vào repository đúng namespace; **ký** nghĩa là sử dụng một private signing identity để tạo bằng chứng cryptographic cho final bytes. Tách ba năng lực theo **identity, job, repository, namespace, thời điểm và approval**. `settings.xml` chỉ chuyển credentials, POM chỉ mô tả nơi deploy và GPG Plugin chỉ thực hiện signing; **authorization thực sự phải được enforced ở repository server, CI secret boundary và signing service**.
