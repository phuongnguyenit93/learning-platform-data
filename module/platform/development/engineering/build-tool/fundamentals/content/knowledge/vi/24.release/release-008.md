# Tách quyền đọc phụ thuộc khỏi quyền xuất bản

Trong vòng đời build và phát hành Java, có hai hoạt động truy cập repository khác nhau:

- **Đọc dependency:** tải JAR, POM, module metadata, plugin và các artifact mà project cần để biên dịch, kiểm thử hoặc chạy build.
- **Xuất bản artifact:** tải JAR/WAR, POM, metadata, checksum hoặc signature của sản phẩm do pipeline tạo lên repository để module khác hoặc người dùng tiêu thụ.

Hai hoạt động này thường dùng cùng một hệ thống quản lý artifact, nhưng có rủi ro và mục đích khác nhau. Một lập trình viên cần quyền đọc dependency để build project không nhất thiết cần quyền ghi vào repository release. Một job kiểm thử pull request có thể cần tải thư viện nội bộ nhưng không nên có khả năng thay thế artifact đã phát hành.

Nguyên tắc thiết kế là **cấp quyền tối thiểu theo nhiệm vụ**: danh tính dùng để resolve dependency chỉ có quyền đọc ở những repository cần thiết; danh tính dùng để publish chỉ có quyền ghi vào đúng repository, đúng phạm vi và trong đúng giai đoạn pipeline.

~~~text
                 Source + build scripts
                          |
                          v
                    Resolve inputs
                          |
              Read-only repository identity
                          |
                          v
                 Compile + test + package
                          |
                          v
                   Release approval
                          |
                          v
                 Publish release artifact
                          |
              Publish-only CI identity
                          |
                          v
                Release repository
~~~

Tách quyền giúp giảm thiệt hại nếu token bị lộ, tránh việc build thông thường vô tình ghi đè artifact và làm rõ trách nhiệm giữa bước tiêu thụ dependency với bước phát hành sản phẩm.

## 1. Đọc dependency và publish artifact là hai quyền khác nhau

Một repository manager thường cung cấp API để client tải artifact và API để client upload/deploy artifact. Cùng một tài khoản có thể được cấu hình cả hai quyền, nhưng không có nghĩa mọi client hoặc pipeline đều cần cả hai.

Ví dụ, project orders-service cần thư viện company:payment-core:2.3.0 để biên dịch. Build cần quyền đọc:

- Artifact JAR của payment-core.
- POM hoặc Gradle module metadata mô tả dependency bắc cầu.
- Checksum hoặc signature nếu quy trình xác minh sử dụng.
- Plugin và build extension từ repository tương ứng.

Sau khi build, release pipeline có thể cần publish orders-service:1.8.0. Đây là quyền ghi:

- Upload JAR hoặc WAR.
- Upload POM/module metadata.
- Upload checksum, signature hoặc file phụ trợ.
- Ghi metadata/version theo quy định repository.

Một token có quyền ghi thường có khả năng gây ảnh hưởng lớn hơn token chỉ đọc. Nếu token publish bị lộ, kẻ tấn công có thể đẩy artifact giả, thay đổi version có thể tải được hoặc làm nhiễm chuỗi cung ứng phần mềm.

### Bảng phân biệt

| Hoạt động | Quyền cần thiết | Ví dụ người dùng/job |
|---|---|---|
| Resolve dependency công khai | Đọc repository công khai | Developer build local, CI |
| Resolve dependency nội bộ | Đọc đúng nhóm repository nội bộ | CI compile/test |
| Tải plugin build | Đọc plugin repository | Gradle/Maven build |
| Publish snapshot | Ghi repository snapshot | CI của nhánh phát triển |
| Publish release | Ghi repository release được chỉ định | Release pipeline sau điều kiện phê duyệt |
| Promote artifact | Quyền promote/copy theo chính sách | Release automation |
| Xóa hoặc sửa artifact | Quyền quản trị đặc biệt | Repository administrator, tác vụ vận hành được kiểm soát |

Một build job thông thường nên chỉ cần quyền đọc. Quyền publish chỉ xuất hiện ở job có nhiệm vụ phát hành và có điều kiện bảo vệ phù hợp.

## 2. Repository có thể phân chia quyền ở nhiều lớp

Quyền truy cập không chỉ được xác định bởi username/password. Repository manager thường có thể áp dụng quyền theo:

- Repository hoặc repository group.
- Đường dẫn/groupId/artifactId.
- Loại repository: proxy, hosted, snapshot, release.
- Hành động: browse, read, deploy, overwrite, delete, administer.
- Nhóm người dùng, service account hoặc token.
- Môi trường hoặc pipeline được phép sử dụng identity đó.

Tên quyền cụ thể phụ thuộc sản phẩm quản lý artifact. Hãy ánh xạ chính sách tổ chức vào mô hình permission thực tế của repository manager.

### Quyền đọc thường cần những gì?

Một client Maven/Gradle có thể cần tải metadata trước khi tải file artifact. Chỉ cho phép đọc JAR nhưng chặn POM hoặc module metadata có thể làm dependency resolution thất bại.

Quyền đọc thường phải bao gồm các request cần thiết cho:

- Tọa độ artifact và metadata version.
- POM hoặc Gradle module metadata.
- JAR, WAR, ZIP hoặc classifier artifact.
- Metadata snapshot nếu project dùng snapshot.
- Checksum/signature nếu client hoặc policy yêu cầu.
- Plugin, parent POM, BOM và build extension.
- Dependency bắc cầu từ các repository được cấu hình.

Nếu project dùng repository group, hãy kiểm tra group đó có expose đúng repository nguồn. Nếu một dependency được lấy từ repository khác, identity cần quyền đọc ở repository đó nữa.

### Quyền publish nên được giới hạn ra sao?

Một identity publish chỉ nên có quyền:

- Ghi vào repository đích được chỉ định.
- Publish đúng nhóm artifact hoặc namespace mà project sở hữu.
- Tạo version theo quy tắc release/snapshot.
- Upload metadata và checksum cần thiết.
- Không xóa hoặc ghi đè release đã phát hành nếu chính sách yêu cầu bất biến.

Không cấp quyền quản trị repository cho pipeline chỉ để upload một JAR. Việc xóa artifact, thay đổi permission, tạo repository hoặc thay cấu hình proxy nên thuộc vai trò quản trị riêng.

## 3. Mô hình identity riêng cho từng nhiệm vụ

Một cách triển khai dễ kiểm soát là tạo các danh tính riêng:

| Identity | Mục đích | Quyền đề xuất |
|---|---|---|
| Developer-read | Build local | Read dependency cần thiết |
| CI-read | Compile, test, package | Read dependency và plugin repository |
| Snapshot-publisher | Publish snapshot từ nhánh phát triển | Read dependency + write snapshot repository |
| Release-publisher | Publish release đã được phê duyệt | Read dependency + write đúng release repository |
| Repository-admin | Quản trị repository và permission | Quyền quản trị theo vai trò, không dùng cho build thông thường |

Trong thực tế, có thể tách read và publish identity hoàn toàn, hoặc cấp cho release job hai credential có phạm vi riêng. Nếu một job vừa phải tải dependency vừa phải publish, hãy dùng credential đọc và credential ghi riêng để dễ thu hồi, audit và giới hạn quyền.

### Tránh dùng tài khoản cá nhân cho pipeline

Pipeline không nên dùng tài khoản cá nhân của lập trình viên. Khi nhân viên đổi nhóm hoặc nghỉ việc, build có thể mất quyền truy cập. Tài khoản cá nhân cũng khiến audit log khó phân biệt hành động của người và hành động tự động.

Nên dùng service account hoặc workload identity được cấp riêng cho automation. Tên identity nên thể hiện nhiệm vụ, ví dụ ci-dependency-reader hoặc release-publisher-orders.

### Tách identity theo project hoặc nhóm artifact

Nếu mọi project dùng chung một publish token, sự cố ở một repository có thể ảnh hưởng nhiều sản phẩm. Giới hạn identity theo project/namespace giúp giảm phạm vi tác động.

Ví dụ, token của orders-service chỉ được publish com.company.orders:* vào repository release của nhóm orders. Nó không nên ghi được artifact của payments-service hoặc plugin build dùng chung.

## 4. Quyền đọc dependency trong Gradle

Gradle khai báo repository để resolve dependency trong khối repositories. Repository dùng cho dependency của project khác với repository dùng để publish artifact trong cấu hình publishing.

Ví dụ cấu hình repository đọc nội bộ:

~~~groovy
repositories {
    maven {
        name = 'companyRead'
        url = uri('https://repo.example.com/maven-public')
        credentials {
            username = providers.environmentVariable('REPO_READ_USER').orNull
            password = providers.environmentVariable('REPO_READ_TOKEN').orNull
        }
    }
    mavenCentral()
}
~~~

Build đọc username/token từ environment. Không ghi giá trị credential trực tiếp vào build.gradle hoặc commit vào Git.

Nếu repository cho phép anonymous read, có thể không cần credential cho dependency công khai. Chỉ cấp credential khi cần truy cập repository private hoặc khi chính sách yêu cầu xác thực.

### Không phải mọi repository đều là repository dependency

Gradle có nhiều nơi khai báo repository:

- pluginManagement.repositories trong settings.gradle dùng để tìm Gradle plugins.
- buildscript.repositories dùng cho classpath của build script kiểu cũ.
- repositories của project dùng để resolve dependency của source code.
- publishing.repositories dùng để gửi artifact được publish.

Một token chỉ có quyền đọc dependency project có thể chưa đủ để tải plugin nếu plugin nằm ở repository khác. Ngược lại, quyền đọc plugin repository không có nghĩa token được phép publish artifact.

Ví dụ settings.gradle:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        maven {
            name = 'companyPlugins'
            url = uri('https://repo.example.com/gradle-plugins')
            credentials {
                username = providers.environmentVariable('PLUGIN_READ_USER').orNull
                password = providers.environmentVariable('PLUGIN_READ_TOKEN').orNull
            }
        }
    }
}
~~~

Nếu repository plugin là public hoặc được mirror nội bộ, hãy cấu hình đúng nguồn được tổ chức sử dụng. Không dùng credential có quyền publish chỉ để tải plugin.

### Kiểm tra dependency resolution

Có thể xem dependency graph:

~~~shell
./gradlew dependencies --configuration runtimeClasspath
~~~

Hoặc tìm một dependency cụ thể:

~~~shell
./gradlew dependencyInsight --dependency payment-core --configuration runtimeClasspath
~~~

Các task này giúp xác nhận dependency được resolve từ graph/configuration nào. Để xác minh quyền đọc, có thể chạy trên cache mới hoặc một runner sạch. Không cần cấp quyền ghi chỉ để thực hiện các lệnh kiểm tra này.

## 5. Quyền publish artifact trong Gradle

Gradle Maven Publish Plugin sử dụng cấu hình publishing.repositories để xác định đích publish. Đây là một cấu hình riêng với repository resolve dependency.

Ví dụ:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.company.orders'
version = providers.gradleProperty('releaseVersion').orElse('1.0.0-SNAPSHOT').get()

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }

    repositories {
        maven {
            name = 'companyReleases'
            url = uri('https://repo.example.com/maven-releases')
            credentials {
                username = providers.environmentVariable('PUBLISH_USER').orNull
                password = providers.environmentVariable('PUBLISH_TOKEN').orNull
            }
        }
    }
}
~~~

Ví dụ này minh họa nơi cấu hình publish credential. Trong dự án thật, version và repository URL cần được quản lý theo release policy. Không nên để token publish tồn tại trong mọi job chỉ vì cấu hình publishing được khai báo trong build script.

### Credential chỉ cần ở job publish

Một số pipeline có thể cấu hình biến PUBLISH_USER/PUBLISH_TOKEN chỉ trong release job. Job pull request và unit test không nhận các biến đó. Khi task publish không được gọi, build thường không cần credential publish.

Hãy kiểm tra cách plugin đọc credential và cách CI inject environment. Tránh resolve hoặc log secret trong giai đoạn configuration nếu không cần thiết. Không bật debug log có thể in thông tin xác thực.

### Publish task không phải task build thông thường

Với publication tên mavenJava và repository companyReleases, Gradle thường tạo task dạng:

~~~shell
./gradlew publishMavenJavaPublicationToCompanyReleasesRepository
~~~

Tên task phụ thuộc publication và repository name. Có thể xem task list để xác nhận. Task publish có thể gom nhiều publication/repository task, vì vậy hãy biết chính xác lệnh pipeline gọi và đích mà nó sẽ ghi.

Không nên chạy một task publish tổng quát nếu build có nhiều repository và bạn chỉ muốn publish đến một đích cụ thể.

## 6. Tách repository đọc và repository ghi trong Gradle

Một build có thể đọc dependency từ repository group nhưng publish vào hosted release repository.

Ví dụ:

~~~groovy
repositories {
    maven {
        name = 'companyRead'
        url = uri('https://repo.example.com/maven-public')
        credentials {
            username = providers.environmentVariable('REPO_READ_USER').orNull
            password = providers.environmentVariable('REPO_READ_TOKEN').orNull
        }
    }
}

publishing {
    repositories {
        maven {
            name = 'companyReleaseWrite'
            url = uri('https://repo.example.com/maven-releases')
            credentials {
                username = providers.environmentVariable('RELEASE_USER').orNull
                password = providers.environmentVariable('RELEASE_TOKEN').orNull
            }
        }
    }
}
~~~

Trong mô hình này:

- REPO_READ_TOKEN chỉ có quyền đọc repository group cần thiết.
- RELEASE_TOKEN chỉ có quyền publish vào repository release được chỉ định.
- Hai token được cấp bởi hai identity hoặc hai policy riêng.
- Developer build local không cần biết release token.
- CI test job không nhận release token.
- Release job mới nhận credential ghi khi đã đạt điều kiện phát hành.

Không nên cấp cùng một token cho cả hai biến chỉ để cấu hình đơn giản. Nếu repository manager bắt buộc dùng một identity có cả read và write, hãy hỏi quản trị viên xem có thể tạo token riêng theo scope hoặc repository permission không.

## 7. Quyền đọc dependency trong Maven

Maven dùng phần repositories trong POM hoặc settings profile để tải dependency. Repository dùng để tải dependency khác với đích publish được khai báo trong distributionManagement.

Ví dụ repository đọc:

~~~xml
<repositories>
    <repository>
        <id>company-read</id>
        <url>https://repo.example.com/maven-public</url>
    </repository>
</repositories>
~~~

Maven lấy credential tương ứng từ settings.xml, thông qua server có id khớp repository id.

Ví dụ settings.xml:

~~~xml
<settings>
    <servers>
        <server>
            <id>company-read</id>
            <username>...</username>
            <password>...</password>
        </server>
    </servers>
</settings>
~~~

Các dấu ba chấm là placeholder. Trong CI, settings có thể được tạo từ secret store hoặc được cung cấp qua file cấu hình an toàn. Không commit password thật vào repository.

### Plugin repository

Maven có thể cần plugin từ plugin repository. Cấu hình pluginRepositories hoặc repository mirror trong settings có thể quyết định nguồn tải plugin.

Nếu project tải dependency thành công nhưng không tải được plugin, hãy kiểm tra plugin repository, mirror và server id. Đừng cấp quyền publish artifact ứng dụng để khắc phục lỗi đọc plugin.

### Mirror trong settings.xml

Tổ chức có thể cấu hình Maven mirror để mọi dependency request đi qua repository manager nội bộ. Khi đó, server id cần khớp với mirror id được sử dụng sau khi áp dụng mirror configuration.

Điều quan trọng là xác định repository cuối cùng Maven truy cập, không chỉ đọc URL trong POM. help:effective-settings và log Maven ở mức phù hợp có thể giúp kiểm tra cấu hình đã áp dụng; không in nội dung credential.

## 8. Quyền publish trong Maven

Maven publish/deploy thường sử dụng distributionManagement để xác định nơi upload artifact.

Ví dụ:

~~~xml
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
~~~

repository là đích release; snapshotRepository là đích snapshot. id được dùng để tìm credential trong Maven settings.xml.

Ví dụ settings cho publish:

~~~xml
<settings>
    <servers>
        <server>
            <id>company-releases</id>
            <username>...</username>
            <password>...</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>...</username>
            <password>...</password>
        </server>
    </servers>
</settings>
~~~

Có thể cấp snapshot credential cho CI của nhánh phát triển và chỉ cấp release credential cho pipeline release. Nếu repository policy cho phép, dùng hai token khác nhau để tránh snapshot job có quyền ghi release.

### Chạy deploy

Maven deploy phase upload artifact đã build vào repository được cấu hình:

~~~shell
./mvnw --batch-mode clean deploy
~~~

Không dùng lệnh này trong job pull request thông thường nếu job không có mục tiêu publish. deploy là một phần của Maven lifecycle và có thể thực hiện upload sau các phase trước đó.

Nếu chỉ muốn build và test mà không publish, dùng một lifecycle mục tiêu phù hợp như:

~~~shell
./mvnw --batch-mode clean verify
~~~

verify có thể chạy các kiểm tra đã được gắn vào lifecycle nhưng không mặc định deploy artifact đến repository từ xa.

## 9. Tách credential đọc và ghi trong Maven settings

Maven dùng server.id để ánh xạ credential tới repository hoặc mirror. Có thể cấu hình hai id riêng:

~~~xml
<repositories>
    <repository>
        <id>company-read</id>
        <url>https://repo.example.com/maven-public</url>
    </repository>
</repositories>

<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.com/maven-releases</url>
    </repository>
</distributionManagement>
~~~

Trong settings.xml, identity đọc và identity publish được cấu hình riêng theo id tương ứng. Một CI job chỉ build/test có thể nhận server credential company-read. Release job nhận thêm company-releases.

Cần nhớ rằng Maven settings thường chứa nhiều server credential. Nếu một job được cấp toàn bộ settings file có cả read và publish token, job đó có thể sử dụng cả hai. Để thực sự tách quyền, tạo settings file tối thiểu cho từng job hoặc cấp credential theo cơ chế chỉ expose đúng secret cần thiết.

### Không nhầm repository id với tên tài khoản

id là khóa để Maven tìm server configuration, không phải username. Nếu id trong distributionManagement không khớp server id trong settings.xml, Maven có thể không tìm được credential và bị HTTP 401/403 khi deploy.

Khi điều tra lỗi deploy, kiểm tra cả URL và id. Không in password ra log để xác nhận.

## 10. Repository snapshot và release

Nhiều repository manager tách snapshot và release thành repository riêng vì chính sách version và tính bất biến khác nhau.

| Đặc điểm | Snapshot repository | Release repository |
|---|---|---|
| Mục đích | Bản phát triển chưa ổn định | Bản phát hành được đánh dấu chính thức |
| Version ví dụ | 2.4.0-SNAPSHOT | 2.4.0 |
| Có thể cập nhật cùng version? | Thường cho phép cập nhật theo policy | Thường không cho phép ghi đè |
| Người publish | CI phát triển hoặc nhánh tích hợp | Release pipeline được kiểm soát |
| Quyền ghi | Snapshot publisher | Release publisher |
| Tiêu thụ | Kiểm thử tích hợp, thử nghiệm | Build downstream và triển khai chính thức |

Không phải repository manager nào cũng áp dụng đúng cùng quy tắc. Hãy xác nhận policy thực tế của repository.

### Vì sao release cần bất biến?

Nếu com.company:orders:1.8.0 được publish hôm nay rồi bị ghi đè ngày mai, hai build downstream cùng khai báo version đó có thể tải nội dung khác nhau. Điều này phá vỡ khả năng truy vết và tái lập.

Release repository nên từ chối redeploy cùng tọa độ/version hoặc chỉ cho phép thao tác sửa chữa theo quy trình quản trị có audit. Khi cần phát hành sửa lỗi, tạo version mới thay vì âm thầm thay nội dung version cũ.

### Snapshot không nên dùng làm release

Snapshot phù hợp cho quá trình phát triển, nơi nội dung có thể thay đổi. Không nên dùng snapshot làm dependency của sản phẩm release nếu yêu cầu là artifact bất biến. Hãy chuyển sang version release cụ thể và khóa dependency theo chính sách.

## 11. Tách quyền theo giai đoạn CI

Một pipeline có thể chia thành các job có quyền khác nhau:

~~~text
Pull request
    |
    v
Compile + Unit test
    |
    | Read-only dependency token
    v
Package + reports
    |
    v
Merge to protected branch
    |
    v
Publish snapshot (nếu cần)
    |
    | Snapshot write token
    v
Release tag + approval
    |
    v
Publish release
    |
    | Release write token
    v
Verify repository artifact + record digest
~~~

### Pull request job

Job pull request thường cần:

- Checkout source.
- JDK và build wrapper.
- Quyền đọc dependency nội bộ nếu project cần.
- Chạy compile/test/lint.
- Lưu test report.

Job này không cần quyền publish release. Với pull request từ fork, secret có thể bị ẩn; nên thiết kế test job có thể chạy với dependency public hoặc một mirror read-only được cấp an toàn.

### Main branch hoặc snapshot job

Sau khi merge vào nhánh được bảo vệ, CI có thể publish snapshot nếu quy trình dự án cần. Identity chỉ có quyền ghi snapshot repository và không có quyền sửa release.

### Release job

Release job nên có các điều kiện:

- Chạy từ tag hoặc commit được xác định.
- Build/test đã thành công.
- Version release hợp lệ.
- Được phê duyệt nếu policy yêu cầu.
- Có quyền ghi vào release repository.
- Lưu log, checksum, signature và metadata.
- Không cho phép pull request không tin cậy truy cập release token.

Không cần cấp release token cho các job chạy trên mọi branch hoặc mọi commit.

## 12. Cấu hình credential theo môi trường

Credential nên được cung cấp ở thời điểm cần và theo scope tối thiểu.

Một ví dụ phân chia:

| Job | Read token | Snapshot token | Release token |
|---|---:|---:|---:|
| Pull request validation | Có | Không | Không |
| Main branch test | Có | Không | Không |
| Snapshot publish | Có | Có | Không |
| Release verification | Có | Không | Chưa cần |
| Release publish | Có | Không | Có |
| Staging deploy | Không cần nếu image đã có | Không | Không |
| Production deploy | Không cần nếu image đã có | Không | Không |

Job deploy ứng dụng thường chỉ cần pull image từ container registry hoặc lấy artifact đã được promote. Nó không cần quyền publish Maven artifact nếu không thực hiện chức năng đó.

### Credential có thời hạn

Nếu nền tảng hỗ trợ, ưu tiên token ngắn hạn hoặc workload identity thay vì token dài hạn. Token ngắn hạn giảm khoảng thời gian bị lạm dụng nếu lộ. Có thể cấp credential theo job, audience và repository scope.

Nếu phải dùng token dài hạn:

- Lưu trong secret store.
- Giới hạn quyền và phạm vi.
- Có lịch xoay vòng.
- Thu hồi khi không còn sử dụng.
- Không dùng chung giữa dự án không liên quan.
- Theo dõi audit log.

### Secret masking không phải bảo vệ tuyệt đối

CI có thể che một số giá trị secret trong log, nhưng không nên dựa vào masking để cho phép in secret. Secret có thể bị biến đổi, encode, chia nhỏ hoặc xuất hiện trong stack trace theo cách masking không nhận diện.

Không echo credential, không đưa nó vào command line không cần thiết và không ghi vào artifact.

## 13. Repository group và quyền đọc tối thiểu

Repository manager có thể cung cấp một repository group tổng hợp nhiều repository. Điều này thuận tiện cho consumer vì chỉ cần cấu hình một URL đọc.

Ví dụ:

~~~text
maven-public
  ├── maven-central-proxy
  ├── company-releases
  └── company-snapshots
~~~

Nếu mọi dependency được đọc qua group maven-public, CI-read identity có thể chỉ cần quyền đọc group đó thay vì quyền quản trị hoặc ghi vào từng repository.

Tuy nhiên, group có thể expose snapshot hoặc repository nội bộ mà project không cần. Hãy giới hạn nội dung group theo policy. Nếu một project chỉ cần release dependencies, không nhất thiết phải cấp quyền đọc snapshot repository.

### Read permission không phải browse permission trong mọi hệ thống

Một số repository manager phân biệt quyền xem danh sách artifact với quyền tải trực tiếp. Client build thường cần tải metadata và file theo tọa độ, không nhất thiết cần browse toàn bộ repository. Hãy cấp đúng permission mà Maven/Gradle client cần, rồi kiểm tra bằng một cold build.

### Không dùng admin token để debug

Nếu dependency resolution thất bại, đừng thử bằng admin credential rồi kết luận cấu hình build đúng. Admin token có thể vượt qua các lỗi permission và che giấu việc identity thực tế thiếu quyền. Hãy test bằng đúng read-only identity sẽ được pipeline dùng.

## 14. Publish chỉ đến đúng repository và namespace

Build script có thể khai báo nhiều publishing repository. Một lỗi cấu hình hoặc task publish tổng quát có thể gửi artifact đến nhiều đích hơn dự kiến.

Hãy đặt tên repository rõ ràng và tạo task/command cụ thể. Ví dụ Gradle có thể có repository companySnapshots và companyReleases, với publication task riêng. CI nên gọi task phù hợp với version/pipeline.

Trong Maven, phân biệt repository và snapshotRepository trong distributionManagement. Kiểm tra version có hậu tố SNAPSHOT hay không và repository đích được chọn.

### Namespace và tọa độ

Giới hạn quyền ghi theo groupId hoặc namespace nếu repository manager hỗ trợ. Ví dụ identity của một nhóm có thể ghi com.company.orders nhưng không ghi com.company.platform.

Điều này ngăn một pipeline hoặc token bị lộ thay thế artifact của nhóm khác.

### Không cấp quyền delete nếu chỉ cần upload

Upload/publish và delete thường là các permission riêng. Release pipeline thường không cần xóa artifact. Nếu cần cleanup snapshot, dùng một job cleanup riêng với quyền xóa được giới hạn repository và retention policy.

## 15. Xác minh quyền bằng hai phép thử riêng

Sau khi cấu hình, kiểm tra read và publish bằng identity tương ứng.

### Phép thử đọc

- Dùng CI-read identity.
- Chạy build từ cache lạnh hoặc runner sạch.
- Resolve dependency nội bộ.
- Xác nhận POM/module metadata và artifact tải được.
- Xác nhận không có quyền ghi nếu repository policy hỗ trợ kiểm tra deny.

### Phép thử publish

- Dùng publish identity trong repository thử nghiệm hoặc namespace thử.
- Publish một tọa độ/version kiểm thử theo policy.
- Xác nhận artifact và metadata xuất hiện.
- Thử xác nhận identity không thể ghi vào repository/namespace ngoài phạm vi.
- Thu hồi hoặc xóa artifact thử nghiệm theo quy trình quản trị.

Không nên kiểm tra quyền ghi bằng cách cố ghi đè một release production. Dùng repository sandbox hoặc tọa độ thử nghiệm được phép.

### HTTP status thường gặp

| Mã | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| 401 Unauthorized | Thiếu hoặc sai thông tin xác thực | Credential có được cấp, đúng server id/username không? |
| 403 Forbidden | Đã xác thực nhưng không đủ quyền | Identity có đúng read/deploy permission không? |
| 404 Not Found | URL hoặc tọa độ không tồn tại; một số hệ thống ẩn tài nguyên không được phép xem | Repository URL, group, version và quyền đọc |
| 409 Conflict | Version/artifact đã tồn tại hoặc trạng thái repository xung đột | Release immutability, redeploy policy |
| 5xx | Repository server hoặc proxy gặp lỗi | Server health, request id, retry có giới hạn |

Không phải mọi hệ thống đều trả đúng cùng mã cho cùng nguyên nhân. Đọc response body và server audit log theo quyền truy cập được cấp, nhưng không đưa token vào log.

## 16. Tách quyền khi dùng artifact được tạo ở pipeline upstream

Trong multi-project hoặc multi-repository organization, một pipeline có thể publish thư viện nội bộ và pipeline khác tải nó.

~~~text
library pipeline
    |
    v
Build + test payment-core
    |
    v
Publish payment-core:2.3.0
    |
    v
Repository manager
    |
    v
orders-service pipeline
    |
    v
Read payment-core:2.3.0
    |
    v
Build + test orders-service
~~~

Pipeline payment-core cần publish permission cho namespace của thư viện. Pipeline orders-service chỉ cần read permission để tải dependency.

Không nên cấp cho orders-service quyền ghi vào repository của payment-core chỉ vì nó cần tiêu thụ artifact.

### Build theo thứ tự và artifact promotion

Nếu artifact upstream chưa được publish, downstream có thể dùng composite build hoặc orchestration tạo dependency trước. Khi artifact đã được phát hành, downstream nên tiêu thụ version cụ thể từ repository.

Nếu tổ chức có quy trình promote artifact từ staging repository sang release repository, quyền promote có thể tách khỏi quyền upload ban đầu. Điều này cho phép kiểm tra artifact trước khi nó trở thành release chính thức.

## 17. Ký artifact và quyền publish

Một số tổ chức yêu cầu ký artifact hoặc metadata bằng key riêng. Ký và publish là hai thao tác khác nhau:

- **Signing identity:** được phép tạo signature cho artifact theo chính sách.
- **Publish identity:** được phép upload artifact vào repository.
- **Read identity:** được phép tải artifact/signature để xác minh.

Không nên để private signing key trong repository hoặc image. Release pipeline có thể yêu cầu key từ HSM, signing service hoặc secret manager. Build/test job thông thường không cần signing key.

Nếu pipeline ký artifact trước khi upload, hãy xác minh checksum của file được ký đúng với file được publish. Nếu repository manager tự ký hoặc tạo metadata, hiểu rõ identity và audit trail của thao tác đó.

### Xác minh chữ ký khi đọc

Consumer có thể tải artifact cùng signature và xác minh bằng public key/trust configuration được quản lý. Read identity chỉ cần quyền tải file và signature; không cần quyền ký hoặc publish.

## 18. Audit, xoay vòng và thu hồi token

Quyền tách biệt chỉ hữu ích khi identity được quản lý trong suốt vòng đời.

Các hoạt động cần có:

- Ghi nhận token/service account thuộc job hoặc project nào.
- Theo dõi thời điểm token được dùng và repository bị truy cập.
- Xoay vòng credential theo chính sách.
- Thu hồi token khi project/job ngừng hoạt động.
- Điều tra upload bất thường hoặc version không mong đợi.
- Giữ audit log của publish/promote/delete.
- Xác nhận token cũ không còn được pipeline tham chiếu sau khi xoay vòng.

### Khi token bị lộ

Quy trình phản ứng thường gồm:

1. Thu hồi hoặc disable token bị lộ.
2. Xác định repository, namespace và khoảng thời gian token có thể đã được sử dụng.
3. Kiểm tra audit log để tìm upload, overwrite, delete hoặc thay đổi permission.
4. Xác định artifact có bị thay đổi hay không bằng checksum/digest và provenance.
5. Tạo credential mới với quyền tối thiểu.
6. Cập nhật secret store/pipeline.
7. Chạy lại build và xác minh quyền.
8. Ghi nhận sự cố và hành động khắc phục.

Nếu token chỉ có quyền đọc, phạm vi ảnh hưởng thường nhỏ hơn token publish/admin. Đây là một lý do quan trọng để tách credential từ đầu.

## 19. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Có quyền tải dependency nghĩa là có quyền publish | Read và deploy/write là permission riêng. |
| Build local cần publish token | Build/compile/test thông thường chỉ cần quyền đọc dependency. |
| Dùng một token cho mọi pipeline sẽ đơn giản hơn | Token rộng làm tăng phạm vi ảnh hưởng khi bị lộ hoặc bị dùng sai. |
| Maven repositories và distributionManagement là cùng một cấu hình | repositories dùng để đọc dependency; distributionManagement xác định đích deploy. |
| Gradle repositories và publishing.repositories là cùng một danh sách | Một bên resolve dependency, bên kia publish publication. |
| Có quyền đọc repository group là cần quyền admin | Consumer thường chỉ cần quyền đọc metadata và artifact qua group. |
| Release publisher cần quyền xóa artifact | Publish không đồng nghĩa delete; release thường cần bất biến. |
| Pull request job có thể nhận release token nếu secret được mask | Masking không biến secret thành an toàn khi cấp cho code không tin cậy. |
| Token publish dùng được cho mọi namespace | Permission có thể và nên giới hạn theo repository/groupId/project. |
| 401 và 403 có cùng nguyên nhân | 401 thường liên quan authentication; 403 thường liên quan authorization, nhưng server cụ thể có thể khác. |
| Dùng admin token để thử build là cách xác nhận quyền | Admin token có thể che giấu thiếu quyền của identity thật. |
| Snapshot và release có thể dùng chung policy | Snapshot thường cho phép cập nhật; release thường cần version bất biến. |
| Job deploy ứng dụng cần quyền publish Maven | Nếu image/artifact đã được publish, deployment job thường chỉ cần quyền pull/read và quyền deploy vào môi trường. |

## 20. Quy trình thiết kế quyền cho một project

Khi thiết lập repository access cho một project Java:

1. Liệt kê tất cả repository dùng để tải dependency, plugin, parent POM và BOM.
2. Xác định repository group hoặc namespace mà project cần đọc.
3. Tạo read identity chỉ có quyền tải metadata và artifact cần thiết.
4. Cấu hình Gradle/Maven để dùng read credential từ secret store.
5. Chạy cold build bằng identity read-only.
6. Xác định artifact repository và namespace mà project sẽ publish.
7. Tạo snapshot/release publisher riêng theo nhu cầu.
8. Giới hạn quyền ghi vào đúng repository và groupId/project.
9. Chỉ cấp publish credential trong job có nhiệm vụ publish.
10. Kiểm tra release version, branch/tag, approval và điều kiện pipeline.
11. Publish thử vào repository sandbox hoặc namespace kiểm thử.
12. Xác nhận read job không thể ghi và publish job không thể ghi ngoài phạm vi.
13. Lưu audit trail, checksum/signature và metadata release.
14. Xây dựng lịch xoay vòng/thu hồi credential.

Mỗi identity cần có owner và mục đích rõ. Nếu không còn biết token được dùng bởi job nào, việc xoay vòng và thu hồi sẽ khó thực hiện an toàn.

## 21. Ví dụ ma trận quyền cho pipeline

Giả sử project orders-service có dependency nội bộ payment-core, cần publish release của chính nó và triển khai container image.

| Pipeline/job | Dependency repository | Maven release repository | Container registry | Deployment platform |
|---|---|---|---|---|
| Pull request checks | Read | Không | Không | Không |
| Main branch tests | Read | Không | Không | Không |
| Snapshot publish | Read | Write snapshot only | Không | Không |
| Release build/test | Read | Không ở bước test | Không | Không |
| Release publish | Read | Write orders-service release | Write image nếu stage tạo/push image | Không |
| Staging deploy | Không cần nếu artifact đã có | Không | Pull image | Deploy staging |
| Production deploy | Không cần nếu artifact đã có | Không | Pull image | Deploy production |

Đây là một mẫu để thảo luận với repository/platform team. Một số tổ chức dùng repository manager để promote artifact thay vì publish lại; một số tách image push và deploy thành hai identity. Điều quan trọng là mỗi job chỉ có các quyền nó thực sự sử dụng.

## 22. Ví dụ kiểm tra cấu hình Gradle và Maven

### Gradle: build đọc dependency, publish chỉ khi được cấp token

Trong build.gradle, có thể khai báo hai khối repository độc lập. Build thường chỉ cần REPO_READ_USER và REPO_READ_TOKEN. Các biến RELEASE_PUBLISH_USER và RELEASE_PUBLISH_TOKEN chỉ được cấp trong release job.

~~~groovy
repositories {
    maven {
        name = 'companyRead'
        url = uri('https://repo.example.com/maven-public')
        credentials {
            username = providers.environmentVariable('REPO_READ_USER').orNull
            password = providers.environmentVariable('REPO_READ_TOKEN').orNull
        }
    }
}

publishing {
    repositories {
        maven {
            name = 'companyRelease'
            url = uri('https://repo.example.com/maven-releases')
            credentials {
                username = providers.environmentVariable('RELEASE_PUBLISH_USER').orNull
                password = providers.environmentVariable('RELEASE_PUBLISH_TOKEN').orNull
            }
        }
    }
}
~~~

Release job chạy task publish được chọn. PR job không nhận release variables và không gọi task publish.

Trong dự án thực tế, có thể cần cấu hình plugin repository ở settings.gradle riêng. Hãy xác nhận tất cả repository được dùng trong build đều có quyền đọc phù hợp.

### Maven: settings khác nhau theo job

Một cách rõ ràng là dùng settings file tối thiểu cho từng job:

- settings-read.xml: chỉ chứa server credential cho repository đọc.
- settings-release.xml: chứa read credential và server credential cho release repository.
- Cả hai file được tạo/cấp trong runner từ secret store, không commit credential vào Git.

Build/test:

~~~shell
./mvnw --settings settings-read.xml --batch-mode clean verify
~~~

Release publish:

~~~shell
./mvnw --settings settings-release.xml --batch-mode clean deploy
~~~

Tên file trên chỉ là ví dụ. Nếu settings file được tạo trong workspace, hãy đặt quyền file phù hợp và xóa sau khi job hoàn tất. Không upload file settings chứa secret thành artifact.

## 23. Checklist kiểm tra quyền trước khi phát hành

### Quyền đọc

- [ ] Tất cả dependency và plugin repository đã được liệt kê.
- [ ] Read identity có thể tải POM/module metadata và artifact.
- [ ] Cold build thành công với read identity.
- [ ] Không cần quyền publish để compile/test.
- [ ] Repository group không expose thêm nguồn không cần thiết.

### Quyền ghi

- [ ] Snapshot và release repository có policy riêng nếu cần.
- [ ] Publish identity chỉ ghi vào repository/namespace được giao.
- [ ] Không cấp delete/admin nếu pipeline không cần.
- [ ] Release repository bảo vệ version đã phát hành.
- [ ] Publish task/goal được gọi tường minh.

### CI và secret

- [ ] Pull request job không nhận release token.
- [ ] Secret được lấy từ CI secret store hoặc identity ngắn hạn.
- [ ] Token không xuất hiện trong source, log, image hoặc report.
- [ ] Credential chỉ được cấp cho job cần dùng.
- [ ] Có quy trình xoay vòng và thu hồi.

### Phát hành và audit

- [ ] Release source revision/version được xác định.
- [ ] Artifact đã qua test và điều kiện phê duyệt.
- [ ] Checksum/signature/provenance được lưu khi policy yêu cầu.
- [ ] Publish target đúng repository và namespace.
- [ ] Audit log cho phép truy vết identity đã upload.
- [ ] Có cách xử lý khi publish sai hoặc token bị lộ.

## 24. Bài thực hành

Thực hành trong một repository thử nghiệm hoặc namespace sandbox:

1. Tạo một dependency nội bộ mẫu và publish version đầu tiên bằng publisher identity có scope giới hạn.
2. Tạo read-only identity chỉ có quyền tải dependency từ repository chứa artifact đó.
3. Cấu hình Gradle hoặc Maven để resolve dependency bằng read-only identity.
4. Chạy build với cache lạnh và xác nhận dependency được tải thành công.
5. Thử dùng read-only identity để publish vào sandbox; xác nhận server từ chối thao tác ghi.
6. Tạo snapshot publisher chỉ có quyền ghi snapshot repository.
7. Tạo release publisher chỉ có quyền ghi release repository của project.
8. Cấu hình Gradle repositories và publishing.repositories bằng credential riêng, hoặc Maven repositories và distributionManagement với server id tương ứng.
9. Chạy pull request/test job không cấp publish token và xác nhận build vẫn thành công.
10. Chạy release job thử nghiệm có publish token, publish một version sandbox và xác minh artifact/metadata.
11. Thử publish vào namespace ngoài phạm vi bằng identity sandbox; xác nhận permission được từ chối.
12. Kiểm tra log, settings file và artifact để chắc chắn không chứa credential.
13. Ghi lại identity, repository, permission, owner và quy trình xoay vòng token.

Sau bài thực hành, bạn cần giải thích được vì sao quyền đọc và quyền publish phải tách biệt, Maven/Gradle cấu hình hai loại repository ở đâu, cách CI cấp credential theo job, và cách xác minh permission bằng cả thao tác được phép lẫn thao tác bị từ chối.

## 25. Tiêu chí hoàn tất thiết kế quyền repository

Một thiết kế có thể xem là hoàn tất khi:

1. Dependency read path được xác định rõ cho source dependency và build plugin.
2. Read identity chỉ có quyền tải những repository cần thiết.
3. Build/test job hoạt động mà không cần publish credential.
4. Publish identity được tách theo snapshot/release hoặc phạm vi phát hành phù hợp.
5. Publish chỉ ghi vào repository và namespace được giao.
6. Release artifact được bảo vệ khỏi ghi đè ngoài quy trình.
7. CI chỉ cấp credential cho job cần sử dụng.
8. Secret không bị lộ trong source, log, artifact hoặc image.
9. Permission được kiểm tra trong repository thử nghiệm.
10. Audit, owner, rotation và revocation được xác định.

Tách quyền đọc dependency khỏi quyền xuất bản làm cho build thông thường ít quyền hơn, release có kiểm soát hơn và sự cố credential có phạm vi ảnh hưởng nhỏ hơn. Khi thiết kế repository access, hãy bắt đầu từ câu hỏi mỗi job cần thực hiện hành động gì, sau đó cấp đúng quyền cho hành động đó.

