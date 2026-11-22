# Phân biệt kho mã nguồn với kho lưu trữ artifact

Trong một dự án Java, nhóm thường làm việc với ít nhất hai loại kho lưu trữ. **Kho mã nguồn** giữ mã nguồn, lịch sử thay đổi và cấu hình dự án để các thành viên cùng phát triển. **Kho lưu trữ artifact** giữ những sản phẩm đã được build, chẳng hạn JAR, WAR, POM và metadata, để các dự án khác hoặc môi trường triển khai có thể tải và sử dụng.

Hai loại kho này có liên quan trong quy trình build nhưng giải quyết hai nhu cầu khác nhau. Git repository giúp quản lý sự thay đổi của mã nguồn. Maven repository hoặc Gradle-compatible artifact repository giúp phân phối dependency và sản phẩm đã đóng gói. Đưa nhầm một loại dữ liệu vào sai nơi sẽ làm khó việc phát triển, phát hành và tái tạo build.

## 1. Hai loại kho giải quyết hai bài toán khác nhau

| Tiêu chí | Kho mã nguồn (source code repository) | Kho lưu trữ artifact (artifact repository) |
|---|---|---|
| Mục đích | Quản lý mã nguồn và lịch sử phát triển | Lưu trữ, phân phối package/artifact đã tạo hoặc được publish |
| Nội dung thường gặp | `.java`, test, build scripts, POM, README, CI workflow, cấu hình dự án | `.jar`, `.war`, `.pom`, metadata, checksum, source JAR, Javadoc JAR |
| Đơn vị quản lý | Repository, branch, commit, tag | Repository/package, tọa độ, version, classifier, metadata |
| Thao tác chính | Clone, branch, commit, merge, tag, review | Resolve, download, install, publish, deploy, proxy/cache |
| Người sử dụng | Developer, reviewer, CI | Build tool, CI, hệ thống triển khai, dự án tiêu thụ dependency |
| Ví dụ | Git repository trên GitHub, GitLab, Bitbucket hoặc máy chủ Git nội bộ | Maven Central, Nexus Repository, JFrog Artifactory hoặc package registry tương thích |
| Lịch sử | Lịch sử commit và nhánh | Các phiên bản artifact đã publish và metadata của chúng |

Ví dụ: repository Git của `order-service` chứa `src/main/java`, `src/test/java`, `pom.xml` hoặc `build.gradle.kts`. Khi CI build thành công, nó tạo `order-service-1.4.0.jar`. JAR và POM tương ứng có thể được publish lên artifact repository để `billing-service` khai báo làm dependency.

Kho mã nguồn trả lời câu hỏi: “Mã và cấu hình nào đã tạo ra sản phẩm này?”. Kho artifact trả lời câu hỏi: “Tôi có thể tải sản phẩm đã build nào, với version và metadata nào?”.

## 2. Kho mã nguồn lưu những gì?

Kho mã nguồn thường được quản lý bằng hệ thống Version Control System (VCS), phổ biến nhất là Git. Một repository Git lưu các commit, branch, tag và nội dung file tương ứng với từng trạng thái của dự án.

Một dự án Java có thể có cấu trúc như sau:

```text
order-service/
├── .git/
├── .gitignore
├── README.md
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
└── .github/                    # ví dụ cấu hình CI nếu dùng GitHub
    └── workflows/
```

Các thành phần thường được commit:

- Mã nguồn Java và mã nguồn kiểm thử.
- Tệp mô tả build như `pom.xml`, `build.gradle` hoặc `build.gradle.kts`.
- Build wrapper và cấu hình phiên bản build tool.
- Cấu hình dự án có thể chia sẻ, ví dụ formatter, static analysis và CI workflow.
- Tài liệu hướng dẫn build, chạy và đóng góp.
- Các file lock hoặc version catalog nếu dự án dùng cơ chế đó.

Các thư mục đầu ra như Maven `target/` hoặc Gradle `build/` thường không commit vì chúng có thể được tái tạo từ mã nguồn và cấu hình. Thư mục cache cục bộ như `.gradle/` hoặc dữ liệu trong `~/.m2/` cũng không phải nội dung cần chia sẻ qua Git.

### 2.1. Git quản lý thay đổi, không phải nơi phân giải dependency Maven

Git có thể lưu một file JAR nếu người dùng commit file đó, nhưng Git không tự cung cấp cơ chế dependency resolution theo tọa độ Maven, không đọc POM để tìm dependency bắc cầu và không quản lý Maven snapshot metadata.

Một repository Git có thể chứa source code của một thư viện, nhưng một dự án Maven thường không thể chỉ khai báo GAV rồi mặc nhiên tải source từ Git. Maven cần artifact đã được publish trong một repository tương thích, hoặc cần một cơ chế build/source dependency riêng được cấu hình rõ ràng.

Tương tự, Git tag `v1.4.0` đánh dấu một trạng thái của source repository. Nó không tự động publish `order-service-1.4.0.jar` lên Maven repository. CI hoặc quy trình release phải build và publish artifact như một bước riêng.

## 3. Kho lưu trữ artifact giữ những gì?

Artifact repository là dịch vụ lưu trữ và phân phối các package được tạo ra hoặc được phát hành. Trong Java, định dạng phổ biến là Maven repository layout. Artifact repository có thể chứa:

- JAR chứa bytecode và resource.
- WAR dùng để triển khai web application.
- POM mô tả tọa độ và dependency của artifact.
- Source JAR và Javadoc JAR được publish kèm.
- Metadata dùng để tra cứu version và snapshot.
- Checksum hoặc chữ ký để hỗ trợ xác minh tính toàn vẹn/nguồn gốc.
- Các loại package khác nếu repository manager hỗ trợ, chẳng hạn npm package, container image hoặc package của hệ sinh thái khác.

Ví dụ, một Maven repository có thể chứa:

```text
repository-root/
└── vn/acme/order/order-service/1.4.0/
    ├── order-service-1.4.0.pom
    ├── order-service-1.4.0.jar
    ├── order-service-1.4.0-sources.jar
    ├── order-service-1.4.0-javadoc.jar
    ├── order-service-1.4.0.jar.sha1       # tùy repository
    └── order-service-1.4.0.pom.sha1       # tùy repository
```

Đây là ví dụ minh họa layout và các file có thể có. Không phải mọi repository đều tạo cùng loại checksum hoặc bắt buộc phải có source/Javadoc JAR.

Artifact repository không chỉ là một thư mục dùng chung. Repository manager có thể cung cấp quyền truy cập, xác thực, chính sách release/snapshot, proxy đến repository bên ngoài, cache, kiểm tra checksum, audit và dọn dẹp version cũ.

## 4. Maven repository là gì?

Maven repository là nơi Maven tìm và lưu artifact theo tọa độ, thường là:

```text
groupId:artifactId:version
```

Ví dụ:

```text
vn.acme.order:order-service:1.4.0
```

Maven phân giải tọa độ thành đường dẫn repository. Với groupId `vn.acme.order`, artifactId `order-service` và version `1.4.0`, đường dẫn thường là:

```text
vn/acme/order/order-service/1.4.0/
    order-service-1.4.0.pom
    order-service-1.4.0.jar
```

POM cho Maven biết metadata của artifact và các dependency liên quan. JAR chứa lớp và resource thực tế. Maven có thể cần cả hai để phân giải và sử dụng dependency.

### 4.1. Local repository và remote repository

Maven thường làm việc với hai nhóm repository:

- **Local repository**: nằm trên máy người dùng, mặc định là `~/.m2/repository`. Maven lưu các artifact đã tải và các artifact được cài đặt cục bộ bằng `mvn install`.
- **Remote repository**: repository qua mạng, ví dụ Maven Central hoặc repository nội bộ của tổ chức. Maven tải dependency từ đây và có thể publish artifact lên một remote repository có quyền ghi.

Khi cần dependency, Maven kiểm tra local repository và sử dụng remote repository theo chính sách phân giải/cập nhật. Local repository giúp giảm tải mạng, nhưng không phải nơi chia sẻ artifact cho toàn nhóm.

Một artifact chỉ được cài bằng `mvn install` trên máy A sẽ xuất hiện trong local repository của máy A. Máy B không tự có artifact đó. Để chia sẻ giữa các máy hoặc CI, cần publish lên remote artifact repository hoặc build các module liên quan trong cùng một reactor build.

### 4.2. Repository công khai và repository nội bộ

Một số repository phổ biến:

- Maven Central: kho công khai được nhiều dự án Java sử dụng để tải thư viện.
- Nexus Repository: repository manager có thể host, proxy hoặc group nhiều repository.
- JFrog Artifactory: repository manager hỗ trợ nhiều loại package và luồng phân phối artifact.
- GitHub Packages hoặc GitLab Package Registry: package registry gắn với nền tảng quản lý source/CI, có thể lưu Maven packages.

Một tổ chức có thể dùng repository manager nội bộ làm điểm truy cập chung. Nó có thể proxy Maven Central, lưu artifact nội bộ và nhóm các repository thành một endpoint để developer/CI cấu hình đơn giản hơn.

## 5. Kho mã nguồn và kho artifact tham gia vào luồng build như thế nào?

Một luồng phát triển và phân phối Java điển hình:

```text
Developer
   |
   v
Clone source repository (Git)
   |
   v
Sửa mã nguồn / test / build configuration
   |
   v
Commit và push / tạo Pull Request
   |
   v
CI lấy source ở commit đã chọn
   |
   +------------------------------+
   |                              |
   v                              v
Resolve dependencies          Compile / test
từ artifact repositories          |
   |                              v
   +--------------------------> Package JAR/WAR
                                  |
                                  v
                           Publish artifact
                                  |
                                  v
                         Artifact repository
                                  |
                                  v
                       Dự án khác / deployment
```

Kho mã nguồn là đầu vào của build. Artifact repository cung cấp dependency đầu vào và nhận artifact đầu ra sau khi publish. Cùng một pipeline có thể đọc từ nhiều repository và publish lên một repository khác.

Ví dụ: `order-service` phụ thuộc `platform-security`. CI lấy source `order-service` từ Git, tải `platform-security:2.0.0` từ Maven repository, build và test, sau đó publish `order-service:1.4.0` lên repository nội bộ. Một dự án khác có thể khai báo `order-service` làm dependency nếu artifact đó được thiết kế để tái sử dụng.

## 6. Cấu hình Maven để đọc dependency từ artifact repository

Trong POM, phần `<repositories>` khai báo nơi Maven có thể tìm dependency của project. Ví dụ:

```xml
<repositories>
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
</repositories>
```

`id` định danh repository trong cấu hình Maven và có thể được dùng để liên kết với credential trong `settings.xml`. URL trỏ đến endpoint Maven repository, không phải URL Git clone của source repository.

Credential thường được cấu hình trong user settings, ví dụ:

```xml
<settings>
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.REPO_USER}</username>
            <password>${env.REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Tên `<id>` trong `<server>` cần khớp với id repository hoặc mirror mà Maven sử dụng. Trong thực tế, cách nội suy credential và chính sách secret phụ thuộc cấu hình Maven/CI; không commit token thật vào repository mã nguồn.

### 6.1. Mirror trong `settings.xml`

Thay vì khai báo endpoint nội bộ trong từng POM, tổ chức có thể cấu hình mirror trong `settings.xml`:

```xml
<settings>
    <mirrors>
        <mirror>
            <id>company-public-group</id>
            <mirrorOf>*</mirrorOf>
            <url>https://repo.example.com/maven-public</url>
        </mirror>
    </mirrors>
</settings>
```

Mirror có thể chuyển yêu cầu repository qua repository manager của công ty. Repository manager có thể proxy các kho công khai và host artifact nội bộ. Nhờ vậy, Maven có một điểm truy cập thống nhất, còn tổ chức quản lý chính sách mạng, xác thực và cache ở phía server.

### 6.2. Phân biệt nơi đọc dependency và nơi publish artifact

Maven dùng `<repositories>` để đọc dependency. Việc publish artifact thường được cấu hình qua `<distributionManagement>` và credential trong `settings.xml`:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.com/maven-releases</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.com/maven-snapshots</url>
    </snapshotRepository>
</distributionManagement>
```

`<repositories>` và `<distributionManagement>` có vai trò khác nhau. Một endpoint dùng để tải dependency không nhất thiết là endpoint được phép ghi. CI thường có quyền đọc rộng hơn quyền publish; chỉ job release được cấp credential ghi vào release repository.

## 7. Cấu hình Gradle để đọc dependency từ artifact repository

Gradle khai báo repository dependency trong `repositories`:

```kotlin
repositories {
    mavenCentral()

    maven {
        name = "companyPublic"
        url = uri("https://repo.example.com/maven-public")
    }
}

dependencies {
    implementation("vn.acme.platform:platform-security:2.0.0")
}
```

Gradle dùng tọa độ dependency để tìm module metadata và artifact. Tùy repository, metadata có thể là POM Maven, Gradle Module Metadata hoặc metadata khác mà Gradle hỗ trợ.

Nếu repository yêu cầu xác thực, có thể lấy thông tin từ environment variable:

```kotlin
repositories {
    maven {
        url = uri("https://repo.example.com/maven-public")
        credentials {
            username = System.getenv("REPO_USER")
            password = System.getenv("REPO_TOKEN")
        }
    }
}
```

Trong cấu hình thực tế, cần xử lý trường hợp biến môi trường không tồn tại và tránh in credential ra log. Không nên ghi user/token thật trực tiếp vào build script được commit.

### 7.1. Plugin repository khác dependency repository

Gradle có thể dùng các repository khác nhau cho plugin và dependency:

```kotlin
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
```

`pluginManagement.repositories` dùng để phân giải plugin Gradle. `dependencyResolutionManagement.repositories` hoặc `repositories` trong build script dùng để phân giải dependency của project theo chính sách build. Khi plugin không tải được nhưng dependency ứng dụng tải bình thường, hãy kiểm tra đúng nhóm repository tương ứng.

## 8. Publish artifact từ dự án Java

Sau khi build thành công, artifact có thể được publish lên kho lưu trữ để dự án khác sử dụng. Việc publish là một bước riêng so với commit source code.

### 8.1. Maven: `install` và `deploy`

Hai lệnh thường gặp:

```bash
./mvnw install
```

`install` build và cài artifact vào local repository của máy đang chạy Maven, thường là `~/.m2/repository`. Nó hữu ích khi thử nghiệm một module hoặc dùng artifact đó từ một project khác trên cùng máy.

```bash
./mvnw deploy
```

`deploy` chạy các phase cần thiết và publish artifact lên remote repository được cấu hình trong `distributionManagement`, dùng credential tương ứng trong Maven settings hoặc cơ chế xác thực của môi trường.

Vì vậy, `install` không có nghĩa publish lên server dùng chung. Nếu đồng nghiệp không tìm thấy artifact sau khi bạn chạy `mvn install`, đó là hành vi bình thường: artifact mới chỉ nằm trong local repository của bạn.

### 8.2. Gradle: `maven-publish`

Gradle có Maven Publish plugin để publish artifact:

```kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "vn.acme.platform"
version = "2.0.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }

    repositories {
        maven {
            name = "companyReleases"
            url = uri("https://repo.example.com/maven-releases")
            credentials {
                username = System.getenv("REPO_USER")
                password = System.getenv("REPO_TOKEN")
            }
        }
    }
}
```

Với cấu hình này, publication lấy thông tin component Java và publish theo tọa độ `group`, `artifactId` và `version` của project. Tên task cụ thể do Gradle tạo dựa trên publication và repository; có thể xem task bằng:

```bash
./gradlew tasks --all
```

Sau khi kiểm tra cấu hình, chạy task publish phù hợp với tên publication/repository. Không nên cấp credential publish cho mọi build thông thường nếu chỉ một pipeline release cần quyền ghi.

## 9. Source JAR không phải source code repository

Artifact repository đôi khi lưu file `-sources.jar` và `-javadoc.jar`. Những file này dễ gây nhầm lẫn với kho mã nguồn.

- **Source code repository** lưu lịch sử phát triển, commit, branch, tag, build configuration và thường là toàn bộ mã nguồn dự án.
- **Sources JAR** là artifact đính kèm một version đã publish, thường chứa các file `.java` tương ứng với binary để IDE hiển thị source khi debug hoặc điều hướng.
- **Javadoc JAR** là artifact chứa tài liệu API đã sinh.

Sources JAR không thay thế Git repository: nó thường không chứa lịch sử commit, branch, issue, pull request, pipeline hay mọi file dự án. Ngược lại, Git repository không tự cung cấp binary JAR đã release cho dependency resolution.

Một số repository manager có thể lưu source archive hoặc link tới source control metadata. Dù vậy, chức năng và mục đích của source repository và artifact repository vẫn cần được phân biệt.

## 10. Repository manager: host, proxy và group repository

Trong tổ chức, một repository manager như Nexus Repository hoặc Artifactory thường cung cấp nhiều loại repository logic:

| Loại repository | Vai trò |
|---|---|
| Hosted repository | Lưu artifact do tổ chức tự publish |
| Proxy repository | Chuyển tiếp yêu cầu đến repository bên ngoài và cache artifact đã tải |
| Group/virtual repository | Kết hợp nhiều repository thành một endpoint để client truy cập |

Ví dụ tổ chức có thể cấu hình:

```text
company-maven-public
├── hosted: company-releases
├── hosted: company-snapshots
└── proxy:  maven-central-cache
```

Developer cấu hình một endpoint `company-maven-public` để tải dependency. CI release publish vào `company-releases` hoặc `company-snapshots` tùy version. Repository manager xử lý quyền ghi và chính sách riêng cho từng loại.

Proxy repository giảm số lần tải từ Internet, tăng tốc build và giúp tổ chức kiểm soát nguồn dependency. Tuy nhiên, cache không thay thế việc quản lý version và nguồn gốc artifact; cần chính sách cập nhật, kiểm tra bảo mật và retention phù hợp.

## 11. Version và tính bất biến của artifact

Kho mã nguồn và kho artifact dùng các cách định danh khác nhau. Git commit được nhận diện bằng hash; artifact thường được nhận diện bằng tọa độ và version.

Ví dụ:

```text
Git commit:  7f3a... (hash minh họa)
Git tag:     v1.4.0
Maven GAV:   vn.acme.order:order-service:1.4.0
```

Tag có thể trỏ tới commit được dùng để tạo release. Pipeline release build source ở tag đó rồi publish artifact với version tương ứng. Việc ánh xạ tag và artifact version là quy ước release của dự án; Maven không tự biết Git tag nào đã tạo ra một JAR nếu không có metadata hoặc provenance đi kèm.

### 11.1. Release repository và snapshot repository

Thông thường, tổ chức tách:

- Release repository: lưu các version ổn định như `1.4.0`, thường áp dụng chính sách không ghi đè.
- Snapshot repository: lưu version phát triển như `1.5.0-SNAPSHOT`, có thể cập nhật nhiều lần.

Maven có thể cấu hình release và snapshot repository trong `distributionManagement`. Repository manager cũng thường có chính sách riêng cho phép/không cho phép snapshot và release.

Không nên tái sử dụng release version cho nội dung binary khác. Nếu cùng một tọa độ release trả về các nội dung khác nhau theo thời gian, hai máy có thể build ra kết quả khác dù POM không đổi. Snapshot được phép thay đổi theo metadata, nên không phù hợp làm đầu vào bất biến cho mọi quy trình release.

## 12. Bảo mật và quyền truy cập

Kho mã nguồn và kho artifact đều có thể chứa dữ liệu nhạy cảm, nhưng rủi ro và quyền truy cập khác nhau.

Với source repository:

- Kiểm soát quyền đọc/ghi, branch protection và review.
- Không commit token, password, private key hoặc file cấu hình chứa credential.
- Dùng secret store của nền tảng CI để cấp thông tin xác thực.
- Xem xét file được thêm vào commit, kể cả file build output hoặc archive ngoài ý muốn.

Với artifact repository:

- Cấp quyền đọc dependency cho developer/CI cần thiết.
- Cấp quyền publish riêng cho pipeline hoặc nhóm phát hành.
- Tách quyền publish snapshot và release nếu chính sách yêu cầu.
- Dùng HTTPS và cơ chế xác thực được tổ chức hỗ trợ.
- Kiểm soát việc ghi đè version, retention, checksum và chữ ký.
- Theo dõi nguồn gốc dependency và artifact được publish.

Không nên đặt credential repository trong POM, build script hoặc file được commit. Maven thường lấy credential từ `settings.xml` ở môi trường người dùng/CI; Gradle có thể đọc từ environment variable hoặc secret provider. Cần tránh in giá trị secret ra log.

## 13. Liên kết source và artifact để có thể truy xuất nguồn gốc

Một artifact được publish nên có cách truy ngược về source và quy trình tạo ra nó. Các thông tin hữu ích gồm:

- Git repository URL.
- Commit hash hoặc release tag.
- GAV và version được publish.
- Build number hoặc pipeline run ID.
- Phiên bản JDK và build tool.
- Danh sách dependency hoặc SBOM nếu quy trình yêu cầu.
- Checksum/chữ ký và thông tin provenance nếu hệ thống hỗ trợ.

Thông tin này có thể được lưu trong manifest, build metadata, artifact properties, release notes hoặc hệ thống provenance riêng. Không phải mọi format artifact tự chứa đầy đủ các trường trên; pipeline cần quyết định metadata nào phải được phát hành.

Ví dụ quy ước release:

```text
Git tag:        order-service-v1.4.0
Source commit:  <commit hash>
Maven GAV:      vn.acme.order:order-service:1.4.0
Artifact:       order-service-1.4.0.jar
Pipeline:       release-2026-0142
```

Khi có sự cố trong production, nhóm có thể dùng GAV để tìm binary đã triển khai, rồi dùng commit hash hoặc tag để truy về source đã tạo ra binary đó.

## 14. Các tình huống thường gặp và cách xử lý

| Tình huống | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Đã push code lên Git nhưng dự án khác không tải được JAR | Chưa publish artifact lên Maven repository | Chạy pipeline publish/deploy hoặc build và publish theo quy trình nhóm |
| Chạy `mvn install` nhưng đồng nghiệp không thấy dependency | Artifact chỉ nằm trong local repository của máy hiện tại | Publish lên remote artifact repository |
| Maven tải được dependency công khai nhưng không tải được artifact nội bộ | Repository nội bộ chưa được khai báo, mirror sai hoặc thiếu quyền | Kiểm tra POM/settings, URL, server id và credential |
| CI không tải được artifact mà máy local có | Artifact chỉ được cài cục bộ hoặc CI dùng repository/settings khác | Publish artifact lên kho chung và cấu hình CI tương ứng |
| Không publish được release | Credential chỉ có quyền đọc, URL sai hoặc version đã tồn tại theo chính sách bất biến | Kiểm tra `distributionManagement`, quyền ghi và version mới |
| Dependency mới publish nhưng build vẫn dùng bản cũ | Local cache, snapshot metadata hoặc chính sách cập nhật | Xác nhận version, metadata và refresh dependency theo cơ chế công cụ |
| Không tìm thấy mã nguồn khi debug dependency | Chưa publish source JAR hoặc IDE không tải được sources | Publish/đính kèm sources và kiểm tra IDE/source attachment |
| Git tag có nhưng artifact không tồn tại | Tag chỉ đánh dấu source, chưa có bước release publish | Kiểm tra pipeline release và artifact repository |

## 15. Thực hành: lần theo một thư viện từ source đến consumer

Giả sử nhóm có thư viện `platform-security` và ứng dụng `order-service`.

**Bước 1 — Phát triển thư viện.** Developer clone Git repository `platform-security`, sửa Java source, test và build file, rồi commit/push thay đổi.

**Bước 2 — Tạo release.** Nhóm tạo tag `v2.0.0` sau khi review và kiểm thử. CI checkout commit tương ứng, build bằng wrapper, chạy test và tạo JAR/POM.

**Bước 3 — Publish artifact.** Pipeline publish tọa độ `vn.acme.platform:platform-security:2.0.0` lên release repository. Repository lưu JAR, POM và metadata liên quan.

**Bước 4 — Sử dụng dependency.** `order-service` khai báo:

```xml
<dependency>
    <groupId>vn.acme.platform</groupId>
    <artifactId>platform-security</artifactId>
    <version>2.0.0</version>
</dependency>
```

Maven tải artifact từ remote repository hoặc dùng bản đã có trong local repository. Build `order-service` không cần clone source `platform-security` để sử dụng JAR đã publish.

**Bước 5 — Truy ngược khi có lỗi.** Nhóm xác định GAV của thư viện đang được ứng dụng dùng, kiểm tra artifact trong repository, sau đó dùng release metadata/tag/commit để tìm đúng source tương ứng.

Luồng này cho thấy source repository và artifact repository phối hợp với nhau: source repository quản lý quá trình tạo sản phẩm; artifact repository phân phối kết quả đã tạo.

## 16. Khi nào nên dùng Git submodule hoặc multi-module build?

Đôi khi nhóm muốn dùng source của một dự án khác trực tiếp thay vì lấy binary artifact. Có thể gặp Git submodule, Git subtree, composite build của Gradle hoặc Maven multi-module/reactor build.

Các cơ chế này phục vụ việc kết hợp source project hoặc module trong quá trình phát triển/build. Chúng không biến Git thành Maven artifact repository.

- Git submodule tham chiếu một repository Git khác tại một commit cụ thể.
- Gradle multi-project/composite build kết hợp nhiều project trong cùng build hoặc build logic.
- Maven multi-module gom nhiều module vào một reactor build để build theo quan hệ phụ thuộc.
- Artifact repository cung cấp binary/package đã publish để consumer phân giải độc lập với source checkout.

Chọn cách nào phụ thuộc vào việc nhóm muốn phát triển đồng thời source, chia sẻ binary đã release hay xây dựng nhiều module cùng một lần. Với dependency được tiêu thụ bởi nhiều dự án độc lập, publish artifact có version thường giúp phân phối và kiểm soát release rõ ràng.

## 17. Những điều cần ghi nhớ

- Kho mã nguồn quản lý file dự án, commit, branch, tag và lịch sử thay đổi; kho artifact lưu package đã build và metadata để phân phối.
- Git tag không tự publish JAR/WAR; cần pipeline hoặc lệnh publish/deploy riêng.
- Maven local repository (`~/.m2/repository`) chỉ phục vụ máy hiện tại; `mvn install` không publish cho toàn nhóm.
- Remote artifact repository lưu dependency và artifact đã publish; repository manager có thể host, proxy và group nhiều kho.
- Maven `<repositories>` dùng để đọc dependency; `<distributionManagement>` mô tả nơi publish artifact.
- Gradle tách repository phân giải plugin và dependency; Maven/Gradle đều có cơ chế publish riêng.
- `-sources.jar` là artifact đính kèm để IDE tải source, không thay thế Git source repository.
- Release version nên bất biến; snapshot có thể thay đổi theo metadata và chính sách repository.
- Cần tách quyền đọc dependency và quyền publish, giữ credential trong secret store và gắn artifact với source commit/tag để truy xuất nguồn gốc.

Khi thiết kế quy trình build Java, hãy để source repository làm nguồn quản lý mã và cấu hình, còn artifact repository làm nơi phân phối những package đã được tạo và kiểm soát version. CI kết nối hai nơi: lấy source, tải dependency, build/test, rồi publish artifact cùng metadata đủ để consumer sử dụng và nhóm có thể truy ngược về commit đã tạo ra nó.
