# Kiểm soát quyền truy cập kho và bảo vệ thông tin xác thực

Build tool cần truy cập repository để tải dependency, plugin và đôi khi để xuất bản artifact. Repository có thể công khai hoặc nội bộ, chứa thư viện release, snapshot, package thử nghiệm hay artifact chỉ dành cho một nhóm dự án. Khi repository yêu cầu xác thực, build phải cung cấp thông tin truy cập phù hợp.

Nếu quyền truy cập được cấp quá rộng hoặc credential được lưu sai chỗ, một build có thể trở thành đường dẫn làm lộ token, password hay quyền publish của tổ chức. Người có quyền đọc dependency không nhất thiết cần quyền publish; job chạy từ pull request bên ngoài cũng không nên nhận credential phát hành. Vì vậy, kiểm soát repository cần kết hợp **phân quyền tối thiểu**, **lưu trữ credential an toàn**, **truyền credential đúng lúc**, **bảo vệ log** và **xác minh nguồn artifact**.

Bài học này tập trung vào repository Maven/Gradle, cấu hình xác thực trong máy developer và CI, cách giới hạn quyền đọc/ghi, vòng đời token, bảo vệ thông tin nhạy cảm và các lỗi thường gặp khi build truy cập repository.

## 1. Repository có những quyền truy cập nào?

Một repository package thường hỗ trợ một số hành động khác nhau:

| Quyền | Ý nghĩa | Ví dụ người/tiến trình cần quyền |
|---|---|---|
| Read/browse | Xem metadata và tải artifact | Developer, CI build, ứng dụng consumer |
| Publish/write | Upload package và metadata mới | CI release, maintainer được ủy quyền |
| Overwrite/delete | Thay thế hoặc xóa package đã lưu | Repository administrator hoặc release manager trong quy trình đặc biệt |
| Admin/configure | Tạo repository, chỉnh policy, user và permission | Repository administrator |
| Promote | Chuyển package giữa staging/release hoặc thay đổi trạng thái phê duyệt | Release automation/authorized maintainer |

Không phải repository nào cũng có đúng các tên quyền này. Nexus, Artifactory, GitHub Packages, GitLab Package Registry và dịch vụ khác có mô hình role/permission riêng. Khi thiết kế pipeline, hãy ánh xạ nhu cầu thực tế sang quyền mà nền tảng cung cấp.

### 1.1. Tách quyền đọc và quyền ghi

Phần lớn developer và job kiểm thử chỉ cần đọc dependency. Chỉ job phát hành đáng tin cậy mới cần quyền ghi artifact release.

Ví dụ phân quyền:

```text
Developer laptop
  └── Read: internal dependencies
      No release publish permission by default

Pull request from fork
  └── Read: approved public/cache sources only
      No repository write token

Trusted CI verification
  └── Read: dependencies and plugins
      No release publish permission

Trusted release job
  └── Read: dependencies
      Write: designated release repository

Repository administrator
  └── Manage users, roles and repository policy
```

Tách quyền giúp giới hạn thiệt hại nếu một job, developer machine hoặc dependency bị xâm nhập. Một token chỉ có quyền đọc không thể được dùng để thay đổi package release nếu repository thực thi permission đúng.

### 1.2. Quyền truy cập phải gắn với repository cụ thể

Tránh cấp quyền rộng như “mọi repository, mọi package, mọi thao tác” nếu chỉ cần tải một nhóm thư viện. Có thể tạo role cho:

- Nhóm repository release.
- Nhóm repository snapshot.
- Package của một team hoặc product.
- Một môi trường publish thử nghiệm.
- Một repository proxy/cache dùng để tải dependency.

Quyền càng cụ thể, việc audit và thu hồi càng dễ. Hãy xem xét cả quyền kế thừa từ group, project hoặc organization; một token có thể nhận quyền rộng hơn quyền được gán trực tiếp.

## 2. Phân biệt credential đọc dependency và credential publish

Một build thường có hai luồng truy cập khác nhau:

1. **Dependency resolution:** Gradle/Maven gửi request tới repository để đọc metadata và tải JAR/POM/module metadata.
2. **Publication:** build upload JAR/WAR, POM, Gradle Module Metadata, checksum hoặc file đính kèm lên repository đích.

Hai luồng có thể dùng URL và credential khác nhau. Không nên dùng một token có quyền admin chỉ để tải một dependency private.

Ví dụ:

| Hoạt động | Repository | Credential phù hợp |
|---|---|---|
| Tải thư viện nội bộ | `internal-maven-read` | Read-only token |
| Tải plugin nội bộ | `internal-plugin-proxy` | Read-only token riêng hoặc quyền đọc được giới hạn |
| Publish snapshot | `team-snapshots` | Token ghi snapshot |
| Publish release | `company-releases` | Token release chỉ cấp cho job release |
| Xóa hoặc sửa repository | Repository admin | Tài khoản quản trị riêng, không dùng trong build thường ngày |

Một số tổ chức dùng cùng một endpoint cho read và write nhưng vẫn có thể cấp token khác nhau. Quyền được kiểm tra ở phía server, không chỉ dựa vào URL trong build script.

## 3. Credential là gì và cần bảo vệ những loại nào?

Credential là dữ liệu chứng minh danh tính hoặc quyền truy cập. Trong quy trình build, chúng có thể gồm:

- Username và password.
- Access token hoặc personal access token.
- Deploy token/service account token.
- API key.
- SSH private key.
- Client certificate và private key.
- Credential cho cloud identity hoặc workload identity.
- Credential để ký artifact, image hoặc provenance.

Các giá trị này không nên được coi là cấu hình thông thường. Nếu bị lộ, người khác có thể tải package nội bộ, publish package giả, xóa artifact, truy cập registry hoặc sử dụng quyền của service account.

### 3.1. Không đặt credential trong source code

Không viết trực tiếp password/token trong `build.gradle`, `build.gradle.kts`, `pom.xml`, `settings.gradle`, `gradle.properties` đã commit hoặc script khởi chạy được lưu trong repository.

Ví dụ không an toàn:

```groovy
repositories {
    maven {
        url = uri('https://repo.example.com/maven')
        credentials {
            username = 'build-user'
            password = 'secret-token-value'
        }
    }
}
```

Ngay cả khi repository private, mọi người có quyền đọc source hoặc lịch sử Git có thể lấy credential. Xóa token khỏi commit mới không xóa nó khỏi Git history, fork, clone hoặc log đã lưu.

Hãy lưu tên biến/property trong build script và cấp giá trị thật từ môi trường an toàn khi build.

### 3.2. Không đưa credential vào URL

Tránh URL như:

```text
https://user:password@repo.example.com/maven/releases
```

Credential có thể xuất hiện trong log, exception, process metadata, proxy log hoặc cấu hình được chia sẻ. Hãy dùng cơ chế authentication riêng của Maven/Gradle hoặc credential helper của nền tảng.

### 3.3. Không truyền secret qua command line nếu có lựa chọn tốt hơn

Đối số command line có thể bị ghi lại trong shell history, process listing hoặc log CI. Tránh:

```bash
mvn deploy -Drepo.password=secret-token-value
```

Ưu tiên secret store của CI, environment variable được bảo vệ hoặc file settings được tạo trong workspace tạm với quyền file phù hợp. Cơ chế cụ thể phụ thuộc runner và nền tảng.

## 4. Maven: khai báo repository đọc dependency

Maven có thể khai báo repository trong `pom.xml`:

```xml
<repositories>
  <repository>
    <id>company-internal</id>
    <url>https://repo.example.com/maven/public</url>
  </repository>
</repositories>
```

`id` định danh repository trong cấu hình Maven. `url` là endpoint truy cập. Đoạn trên chỉ khai báo nguồn đọc dependency, chưa cung cấp credential và chưa khai báo nơi publish.

Với plugin, có thể có `<pluginRepositories>` riêng. Nếu repository manager cung cấp một group/virtual repository gom Maven Central và các kho nội bộ, thường nên dùng endpoint được tổ chức quản lý để áp dụng proxy, audit và policy tập trung.

## 5. Maven: lưu credential trong `settings.xml`

Maven dùng `settings.xml` để chứa cấu hình theo người dùng hoặc môi trường, thường ở:

```text
Linux/macOS: ~/.m2/settings.xml
Windows:     %USERPROFILE%\.m2\settings.xml
```

Ví dụ repository có `id` là `company-internal`:

```xml
<settings>
  <servers>
    <server>
      <id>company-internal</id>
      <username>${env.MAVEN_REPO_USER}</username>
      <password>${env.MAVEN_REPO_TOKEN}</password>
    </server>
  </servers>
</settings>
```

Maven ghép `id` của `<server>` với `id` của repository được truy cập. Vì vậy, hai giá trị cần khớp chính xác. Environment variable là placeholder; cần cấp chúng từ môi trường đã bảo vệ.

Không commit file `settings.xml` cá nhân nếu nó chứa credential. Nếu CI cần settings file riêng, tạo file từ secret store trong job và bảo đảm không upload nó như artifact.

### 5.1. Credential cho deploy repository

Trong `pom.xml`, khai báo đích publish:

```xml
<distributionManagement>
  <repository>
    <id>company-releases</id>
    <url>https://repo.example.com/maven/releases</url>
  </repository>
  <snapshotRepository>
    <id>company-snapshots</id>
    <url>https://repo.example.com/maven/snapshots</url>
  </snapshotRepository>
</distributionManagement>
```

Trong `settings.xml`, cấu hình credential tương ứng:

```xml
<settings>
  <servers>
    <server>
      <id>company-releases</id>
      <username>${env.RELEASE_REPO_USER}</username>
      <password>${env.RELEASE_REPO_TOKEN}</password>
    </server>
    <server>
      <id>company-snapshots</id>
      <username>${env.SNAPSHOT_REPO_USER}</username>
      <password>${env.SNAPSHOT_REPO_TOKEN}</password>
    </server>
  </servers>
</settings>
```

Việc tách hai server id cho phép cấp token và permission khác nhau. Job snapshot không cần dùng token release nếu chỉ upload snapshot.

### 5.2. Mirror và credential

Maven có thể cấu hình mirror trong `settings.xml` để chuyển request repository qua một endpoint khác:

```xml
<mirrors>
  <mirror>
    <id>company-mirror</id>
    <mirrorOf>*</mirrorOf>
    <url>https://repo.example.com/maven/group</url>
  </mirror>
</mirrors>
```

Nếu mirror yêu cầu authentication, credential thường được khai báo trong `<servers>` với `id` của mirror. Khi điều tra lỗi 401/403, hãy kiểm tra repository thực tế sau khi áp dụng mirror và server id tương ứng, không chỉ nhìn `id` trong POM.

`mirrorOf` quá rộng có thể chuyển cả request plugin/dependency qua một endpoint không hỗ trợ loại artifact đó. Cần cấu hình mirror phù hợp với chính sách repository của tổ chức.

## 6. Maven: mã hóa password và giới hạn của nó

Maven hỗ trợ cơ chế mã hóa password trong `settings.xml` thông qua `settings-security.xml` và các lệnh `mvn --encrypt-master-password`/`mvn --encrypt-password` ở những phiên bản hỗ trợ.

Mục tiêu của cơ chế này là tránh lưu password dạng văn bản rõ trong file settings. Tuy nhiên, mã hóa password của Maven không thay thế secret manager hoặc kiểm soát quyền truy cập filesystem. Người có quyền đọc cả file mã hóa và master password tương ứng có thể giải mã hoặc sử dụng credential theo môi trường đó.

Các nguyên tắc:

- Giữ `settings-security.xml` và master password an toàn.
- Không commit file settings/security cá nhân vào source repository.
- Bảo vệ quyền đọc file trên máy developer và runner.
- Không coi password đã mã hóa trong Maven settings là an toàn nếu cả hai file được lưu trong cùng một nơi công khai.
- Với CI, ưu tiên cấp credential từ secret store và tạo settings tạm trong job.

Nếu dùng cơ chế password encryption, hãy theo tài liệu đúng phiên bản Maven đang chạy; định dạng và quy trình có thể khác giữa các major version.

## 7. Gradle: khai báo credential mà không ghi secret vào build script

Gradle cho phép đọc project property hoặc environment variable để cấu hình repository.

Ví dụ Groovy DSL:

```groovy
repositories {
    maven {
        name = 'companyInternal'
        url = uri('https://repo.example.com/maven/public')
        credentials {
            username = providers.gradleProperty('repoUser')
                .orElse(providers.environmentVariable('REPO_USER')).orNull
            password = providers.gradleProperty('repoPassword')
                .orElse(providers.environmentVariable('REPO_PASSWORD')).orNull
        }
    }
}
```

Ví dụ Kotlin DSL:

```kotlin
repositories {
    maven {
        name = "companyInternal"
        url = uri("https://repo.example.com/maven/public")
        credentials {
            username = providers.gradleProperty("repoUser")
                .orElse(providers.environmentVariable("REPO_USER")).orNull
            password = providers.gradleProperty("repoPassword")
                .orElse(providers.environmentVariable("REPO_PASSWORD")).orNull
        }
    }
}
```

Các tên property/environment variable là ví dụ. Khi dùng private repository, credential phải được cấp trước khi Gradle gửi request. Không đặt giá trị thật trong build script.

### 7.1. Gradle project properties

Gradle có thể nhận project property từ nhiều nguồn, ví dụ:

- `gradle.properties` trong Gradle User Home.
- `gradle.properties` của project.
- Command line `-P`.
- Environment variable theo quy ước `ORG_GRADLE_PROJECT_<propertyName>`.

Với secret cá nhân, file trong Gradle User Home thường phù hợp hơn file project được commit:

```properties
# ~/.gradle/gradle.properties
repoUser=developer-read-user
repoPassword=token-value-from-secret-store
```

File này chỉ là ví dụ vị trí; bảo vệ quyền đọc file của user OS và không đồng bộ nó lên repository. Trong CI, có thể đặt environment variable:

```text
ORG_GRADLE_PROJECT_repoUser
ORG_GRADLE_PROJECT_repoPassword
```

Giá trị thật cần được cấu hình như secret trong CI platform. Không in chúng ra log.

### 7.2. Không commit secret trong `gradle.properties`

Một project có thể có `gradle.properties` để chứa cấu hình không nhạy cảm như memory setting hoặc build option. Nếu file chứa password/token, nó không còn phù hợp để commit.

Nên:

- Đặt credential trong `~/.gradle/gradle.properties` hoặc secret injection của CI.
- Dùng property name trong build script, không ghi giá trị thật.
- Đảm bảo file cá nhân không bị thêm vào Git.
- Nếu project cần một file local riêng, thêm quy tắc ignore phù hợp và kiểm tra Git tracking.
- Không đưa Gradle User Home vào artifact hoặc log chia sẻ.

## 8. Gradle: tách repository đọc dependency và repository publish

Gradle dùng hai khu vực cấu hình khác nhau:

- `repositories { ... }` để phân giải dependency.
- `publishing.repositories { ... }` để xác định nơi publish publication.

Ví dụ repository đọc:

```kotlin
repositories {
    maven {
        name = "internalRead"
        url = uri("https://repo.example.com/maven/public")
        credentials {
            username = providers.gradleProperty("readRepoUser").orNull
            password = providers.gradleProperty("readRepoToken").orNull
        }
    }
    mavenCentral()
}
```

Ví dụ repository publish:

```kotlin
publishing {
    repositories {
        maven {
            name = "internalReleases"
            url = uri("https://repo.example.com/maven/releases")
            credentials {
                username = providers.gradleProperty("publishRepoUser").orNull
                password = providers.gradleProperty("publishRepoToken").orNull
            }
        }
    }
}
```

Việc dùng property khác nhau giúp cấp quyền đọc và ghi riêng. Job build/test chỉ cần read credential; job release mới nhận publish credential.

## 9. Giới hạn repository nguồn để giảm rủi ro dependency confusion

Nếu Gradle/Maven tìm dependency trong nhiều repository không được kiểm soát, một package có cùng tọa độ hoặc tên gần giống có thể được lấy từ nguồn không mong muốn.

Các biện pháp:

- Dùng repository manager nội bộ làm proxy cho nguồn công khai khi tổ chức có chính sách đó.
- Giới hạn group/module được phép lấy từ từng repository.
- Không thêm repository tùy tiện trong từng subproject.
- Kiểm soát repository declaration ở `settings.gradle` hoặc build convention phù hợp.
- Kiểm tra tọa độ dependency, version và nguồn được phân giải.
- Bảo vệ quyền publish package nội bộ để người ngoài không thể chiếm namespace.

### 9.1. Gradle content filtering

Gradle cho phép giới hạn nội dung mà một repository có thể cung cấp:

```kotlin
repositories {
    maven {
        name = "companyInternal"
        url = uri("https://repo.example.com/maven/internal")
        content {
            includeGroup("com.example.internal")
            includeGroupByRegex("com\\.example\\.platform(\\..*)?")
        }
    }

    mavenCentral {
        content {
            excludeGroup("com.example.internal")
        }
    }
}
```

Ví dụ này cho phép repository nội bộ cung cấp các group được chỉ định và loại group nội bộ khỏi Maven Central. Regex phải được điều chỉnh theo namespace thật.

Content filter giúp giới hạn nguồn phân giải; nó không thay thế authentication, checksum verification hoặc dependency locking.

### 9.2. Repository mode tập trung

Với multi-project build, có thể quản lý repository dependency ở `settings.gradle`:

```kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        maven {
            name = "companyGroup"
            url = uri("https://repo.example.com/maven/group")
        }
        mavenCentral()
    }
}
```

Chế độ này ngăn project tự thêm repository ngoài cấu hình tập trung theo chính sách đã chọn. Điều đó giúp reviewer biết dependency có thể đến từ đâu.

## 10. TLS và xác minh máy chủ repository

Credential chỉ được bảo vệ khi truyền qua kênh phù hợp. Repository private nên dùng HTTPS với certificate hợp lệ.

Không nên:

- Dùng HTTP không mã hóa để gửi password/token qua mạng.
- Tắt certificate validation để “sửa nhanh” lỗi TLS.
- Tin certificate tùy tiện hoặc thêm CA không rõ nguồn vào truststore.
- Ghi token trong URL hoặc query string.

Nếu repository dùng CA nội bộ, cấu hình truststore theo quy trình IT/security của tổ chức. Không vô hiệu hóa TLS verification bằng một workaround chung trong build script.

Lỗi TLS có thể do certificate hết hạn, hostname không khớp, CA chưa được tin cậy, proxy TLS inspection hoặc JDK truststore khác nhau. Thu thập lỗi cụ thể và sửa trust chain ở môi trường được quản lý.

## 11. CI: cấp credential đúng job và đúng thời điểm

CI platform thường có secret store hoặc masked variables. Credential nên được cấp cho đúng job cần sử dụng, với scope và thời hạn phù hợp.

Một pipeline có thể tách:

```text
Pull request job
  - build/test
  - no publish credential

Main branch verification job
  - build/test/scan
  - read-only repository credential

Release job after approval
  - download verified artifact
  - short-lived publish credential
  - publish/promote release
```

### 11.1. Không cấp secret cho pull request từ fork

Code trong pull request có thể thay đổi build script, plugin, test hoặc task. Nếu job chạy code không đáng tin cậy có quyền đọc secret, code đó có thể in hoặc gửi secret ra ngoài.

Đặc biệt nguy hiểm khi workflow:

- Chạy build script do contributor thay đổi.
- Cho phép task/plugin thực thi shell command tùy ý.
- Cấp token có quyền publish/admin.
- Upload log hoặc artifact chứa file cấu hình credential.

Với pull request từ fork, dùng job không có secret hoặc chỉ có credential đọc công khai được phép. Chỉ cấp write credential trong job phát hành chạy từ branch/tag/revision được tin cậy và sau các approval cần thiết.

### 11.2. Scope theo job, environment và branch

Nếu CI hỗ trợ environment protection, branch restriction hoặc deployment approval, hãy dùng chúng để giới hạn khi nào release credential được cấp.

Ví dụ policy:

- Token đọc dependency có thể cấp cho job build nội bộ.
- Token snapshot chỉ cấp cho job publish snapshot từ branch được phép.
- Token release chỉ cấp cho job tag/release đã được review.
- Token admin không cấp cho pipeline build thông thường.

Không nên lưu credential ở biến global nếu nền tảng cho phép giới hạn theo environment/job.

### 11.3. Ưu tiên short-lived token hoặc workload identity

Nếu nền tảng hỗ trợ, dùng token ngắn hạn được cấp cho job hoặc workload identity thay vì personal access token tồn tại lâu. Token ngắn hạn giảm khoảng thời gian bị khai thác nếu log hoặc runner bị lộ.

Nếu buộc phải dùng token dài hạn:

- Chọn scope tối thiểu.
- Gắn token với service account chuyên dụng.
- Đặt expiry và lịch rotation.
- Không dùng chung token giữa nhiều pipeline không liên quan.
- Có quy trình thu hồi khẩn cấp.

## 12. Bảo vệ log, build scan và artifact CI

Một credential không nằm trong source vẫn có thể bị lộ qua log hoặc file output.

Các nguồn rò rỉ thường gặp:

- `--debug`/`-X` in request header hoặc URL.
- Script dùng `set -x` hoặc PowerShell verbose hiển thị biến môi trường.
- Build task in toàn bộ repository configuration.
- Exception chứa URL có userinfo.
- File `settings.xml` hoặc `gradle.properties` được upload nhầm.
- Build Scan thu thập environment variable hoặc build property.
- Docker layer lưu file credential đã xóa ở layer sau.

### 12.1. Masking không phải ranh giới bảo mật tuyệt đối

CI masking giúp ẩn một số giá trị đã đăng ký trong log. Tuy nhiên, masking có thể thất bại khi secret được encode, chia nhỏ, biến đổi hoặc in theo định dạng khác. Không nên dựa vào masking để cho phép code không đáng tin cậy tiếp cận secret.

Nguyên tắc tốt nhất là không cấp secret cho job không cần nó, đồng thời tránh in environment hoặc config đầy đủ.

### 12.2. Kiểm tra file được upload

Trước khi upload diagnostics/artifact, xác nhận không chứa:

- `settings.xml` có credential.
- `gradle.properties` cá nhân.
- `.env` hoặc file token.
- SSH private key/client certificate.
- Docker config hoặc registry auth file.
- Log đã in secret.

Chỉ upload file cần cho bước sau. Dùng allowlist file thay vì upload toàn bộ workspace nếu không cần thiết.

## 13. Rotation, expiry và thu hồi credential

Credential cần có vòng đời quản lý rõ ràng:

1. Tạo token/service account cho mục đích cụ thể.
2. Gán scope và permission tối thiểu.
3. Lưu vào secret manager hoặc kho credential được bảo vệ.
4. Cấp cho đúng user/job vào đúng thời điểm.
5. Theo dõi lần sử dụng và audit log nếu nền tảng hỗ trợ.
6. Rotate theo lịch hoặc khi có dấu hiệu lộ.
7. Thu hồi token cũ sau khi chuyển sang token mới.
8. Kiểm tra pipeline đã dùng credential mới và không còn phụ thuộc token cũ.

Nếu nghi ngờ token đã lộ:

- Thu hồi hoặc disable token ngay theo quy trình của repository/identity provider.
- Tạo credential mới với scope tối thiểu.
- Kiểm tra audit log để tìm thao tác bất thường.
- Kiểm tra package bị publish/thay đổi/xóa.
- Kiểm tra Git history, CI log, artifact và file cấu hình đã lưu.
- Làm sạch hoặc thay thế artifact bị ảnh hưởng theo release policy.
- Cập nhật secret store và pipeline.

Xóa chuỗi token khỏi file hiện tại không đủ nếu token vẫn còn hiệu lực hoặc đã xuất hiện trong lịch sử/log. Phải thu hồi token ở phía cấp phát.

## 14. Service account và danh tính máy

Không nên dùng tài khoản cá nhân của developer cho pipeline publish. Dùng service account hoặc workload identity dành cho CI giúp:

- Tách hành động của con người và automation.
- Gán quyền theo một pipeline/repository cụ thể.
- Audit ai/job nào đã publish.
- Rotate/disable credential mà không ảnh hưởng tài khoản cá nhân.
- Giới hạn quyền theo branch, environment hoặc release workflow.

Tên service account nên mô tả mục đích, ví dụ `ci-order-service-read` hoặc `release-order-service-publish`. Tránh một tài khoản `admin-build` có quyền quản trị toàn bộ repository cho mọi dự án.

Nếu dùng cloud workload identity/OIDC, ưu tiên federation với CI provider để cấp token tạm thời theo job claim thay vì lưu cloud secret dài hạn trong CI variables.

## 15. Dependency verification và bảo vệ nguồn package

Authentication xác định ai được truy cập repository. Nó không tự chứng minh artifact tải về là artifact đúng hoặc không bị thay đổi.

Có thể bổ sung:

- Dependency locking để kiểm soát version được chọn.
- Dependency verification/checksum để xác nhận nội dung artifact.
- Signature verification khi hệ sinh thái/package hỗ trợ.
- Repository allowlist/content filter.
- SBOM và vulnerability scan.
- Quy trình review khi thêm repository hoặc dependency mới.
- Chính sách release version bất biến.

Với Gradle, dependency verification có thể được cấu hình bằng verification metadata và checksum/signature theo policy của dự án. Với Maven, có thể dùng checksum/signature, repository policy và plugin/công cụ kiểm tra phù hợp.

Không nên xem token read-only là đủ để bảo đảm supply chain. Một repository bị cấu hình sai hoặc dependency giả có thể được tải bằng quyền read hợp lệ.

## 16. Không dùng `mavenLocal()` hoặc repository cá nhân làm nguồn release mặc định

Maven local repository và Gradle `mavenLocal()` hữu ích trong phát triển local, nhưng chúng tạo ra trạng thái riêng theo máy. Một developer có thể vô tình dùng JAR tự cài cũ hoặc khác nội dung với artifact remote cùng tọa độ.

Đối với CI/release:

- Dùng repository được quản lý tập trung.
- Không phụ thuộc artifact chỉ tồn tại trong local repository của một người.
- Tránh cho `mavenLocal()` đứng trước repository release trong build production nếu không có lý do rõ ràng.
- Kiểm tra nguồn và checksum của dependency quan trọng.
- Dùng version bất biến cho release.

Nếu cần thử nghiệm thư viện local, hãy dùng project consumer và repository tạm được tạo riêng cho test thay vì làm nguồn dependency chung của pipeline release.

## 17. Lỗi xác thực và cách chẩn đoán

| Lỗi | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| HTTP 401 Unauthorized | Credential thiếu, sai, hết hạn hoặc server id không khớp | Kiểm tra tên biến, Maven server id/Gradle property và token expiry |
| HTTP 403 Forbidden | Danh tính hợp lệ nhưng không có quyền thao tác | Kiểm tra role, repository scope và read/write permission |
| HTTP 404 khi tải private package | URL sai, package không tồn tại hoặc server che thông tin truy cập | Kiểm tra tọa độ, repository path và quyền read |
| Maven deploy báo authentication failure | `distributionManagement.id` không khớp `<server><id>` | So khớp id trong POM/settings và credential được cấp |
| Gradle không gửi credential | Property/environment variable không được đọc hoặc repository dùng sai credentials type | Kiểm tra property name và cấu hình repository |
| TLS handshake/certificate error | CA/hostname/certificate/JDK truststore không phù hợp | Kiểm tra certificate chain và truststore; không tắt validation |
| Developer tải được, CI không tải được | CI thiếu secret, mirror hoặc quyền network | So sánh repository URL, server identity và network policy |
| Chỉ publish fail | Token chỉ có read permission hoặc sai release repository | Dùng publish token đúng scope và kiểm tra server policy |
| Credential bị lộ trong log | Debug/trace hoặc script in config | Thu hồi token, redaction log và sửa cách truyền secret |
| Dependency đến từ repository ngoài dự kiến | Repository order/filter/mirror chưa được kiểm soát | Kiểm tra dependency graph và content filtering |
| Token bị từ chối sau rotation | Pipeline còn dùng secret cũ hoặc secret chưa cập nhật ở environment | Kiểm tra scope/expiry và cập nhật đúng secret binding |

### 17.1. Chẩn đoán mà không in secret

Có thể kiểm tra:

- Biến môi trường có tồn tại hay không, chỉ in trạng thái set/unset.
- Maven server id có khớp repository/mirror id không.
- Gradle property name có được nhận không, không in value.
- Token còn hạn và có scope cần thiết không, qua giao diện/audit log của provider.
- URL repository và path có đúng không.
- Job chạy trong branch/environment được phép không.

Không dùng `env`, `printenv`, `set`, `Get-ChildItem Env:` hoặc dump toàn bộ Gradle/Maven settings trong log CI nếu chúng có thể chứa secret.

## 18. Ví dụ pipeline an toàn ở mức khái niệm

Một pipeline Java có thể được tổ chức:

```text
Pull request
  |
  +--> Build + unit tests
  |      - public dependency sources
  |      - no publish credential
  |
  +--> Optional private read dependency
         - read-only token if trusted policy permits

Trusted main branch
  |
  +--> Full verification
  |      - read-only repository token
  |      - no release write token
  |
  +--> Artifact inspection and smoke test

Approved release
  |
  +--> Download exact verified artifact
  +--> Verify checksum/provenance
  +--> Inject short-lived publish credential
  +--> Publish immutable release version
  +--> Record audit evidence
```

Tách job build và job publish giúp giảm thời gian mà write credential tồn tại. Job publish không cần chạy lại toàn bộ source code nếu có thể nhận artifact đã được build và kiểm tra từ job trước.

### 18.1. CI nên tránh truyền secret cho step không cần

Nếu CI hỗ trợ khai báo secret theo step, chỉ gắn secret vào bước truy cập repository. Các bước compile/test thuần túy không cần credential publish thì không nên nhận nó.

Với workflow nhiều job, secret scope theo environment/release approval thường tốt hơn một biến global luôn có mặt trong mọi job.

## 19. Checklist thiết kế quyền repository

Khi tạo một repository hoặc service account cho dự án, hãy trả lời:

1. Build cần đọc những group/package nào?
2. Artifact được publish vào repository nào?
3. Ai cần quyền read?
4. Job nào cần quyền write?
5. Có cần tách snapshot và release không?
6. Có cho phép overwrite/delete không?
7. Token có scope theo repository/package không?
8. Token có expiry/rotation không?
9. Job từ fork có thể nhận secret không?
10. Repository có TLS và audit log không?
11. Có content filter/mirror policy không?
12. Có dependency verification/checksum/signature không?
13. Credential có thể xuất hiện trong log hoặc artifact CI không?
14. Có quy trình thu hồi khi nghi ngờ lộ không?

Quyền truy cập cần được review định kỳ. Khi project đổi owner, pipeline bị xóa hoặc service account không còn sử dụng, hãy thu hồi credential và role liên quan.

## 20. Quy trình xử lý khi credential bị lộ

Nếu phát hiện token/password trong Git, log hoặc artifact:

1. Xác định loại credential và hệ thống cấp phát.
2. Thu hồi/disable credential ở repository hoặc identity provider.
3. Kiểm tra audit log trong khoảng thời gian credential có thể đã bị lộ.
4. Tạo credential thay thế với scope tối thiểu và thời hạn phù hợp.
5. Cập nhật secret store, CI environment và cấu hình developer cần thiết.
6. Xác nhận pipeline dùng credential mới mà không in giá trị.
7. Xóa hoặc hạn chế quyền truy cập log/artifact chứa secret theo policy.
8. Xử lý Git history/fork/cache nếu cần, nhưng không xem việc rewrite history là thay thế thu hồi credential.
9. Kiểm tra package/release có bị publish hoặc thay đổi trái phép không.
10. Ghi lại sự cố và biện pháp ngăn tái diễn.

Thứ tự ưu tiên là vô hiệu hóa credential đã lộ và kiểm tra hành vi sử dụng. Xóa chuỗi trong source sau đó chỉ làm sạch một bản sao; token cũ vẫn có thể bị dùng cho đến khi bị thu hồi.

## 21. Nguyên tắc cần ghi nhớ

- Tách quyền read, publish, delete và admin; chỉ cấp quyền tối thiểu cho từng user/job.
- Không đặt password/token trong source code, URL, command line hoặc file được commit.
- Maven dùng `settings.xml` và `<server><id>` khớp repository/mirror hoặc `distributionManagement` id.
- Gradle đọc credential từ project property/environment variable/secret provider; không hard-code giá trị.
- Dùng credential riêng cho dependency read và artifact publish.
- Pull request từ fork không được nhận publish credential; chỉ job release đáng tin cậy mới có write token.
- Ưu tiên service account, short-lived token hoặc workload identity hơn credential cá nhân dài hạn.
- Dùng HTTPS và truststore hợp lệ; không tắt TLS validation để vượt lỗi.
- Bảo vệ log, Build Scan, settings file và CI artifacts; masking không thay thế việc không cấp secret.
- Rotate và thu hồi credential theo vòng đời; khi nghi lộ, revoke trước rồi mới dọn source/log.
- Giới hạn repository nguồn bằng mirror/content filter và kiểm tra dependency verification.
- Kiểm tra POM/Gradle metadata, dependency graph và audit log khi có vấn đề truy cập.

Kiểm soát repository an toàn bắt đầu từ việc biết chính xác build cần đọc gì, job nào cần ghi gì và credential nào đủ cho hành động đó. Khi quyền được giới hạn theo repository và job, secret được cấp từ nơi bảo vệ, log không làm lộ dữ liệu và token có vòng đời rõ ràng, build có thể truy cập package nội bộ mà không biến pipeline thành nơi lưu trữ hoặc phát tán credential.
