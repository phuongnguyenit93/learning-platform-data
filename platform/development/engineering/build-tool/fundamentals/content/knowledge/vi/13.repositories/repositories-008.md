# Xác thực kho riêng và quản lý thông tin truy cập

Trong một dự án Java, thư viện và plugin thường được tải từ các kho artifact như Maven Central, Gradle Plugin Portal hoặc repository nội bộ của tổ chức. Repository nội bộ có thể chứa thư viện chưa công khai, plugin riêng, snapshot hoặc các bản phát hành chỉ dành cho nhóm phát triển. Để truy cập những kho này, build tool cần xác thực danh tính và được cấp quyền phù hợp.

Thông tin xác thực (credentials) thường gồm username/password, access token hoặc một loại thông tin xác thực khác do hệ thống repository hỗ trợ. Vì build chạy trên máy lập trình viên và trên CI, cách lưu và cung cấp credentials phải bảo đảm đúng người hoặc job được phép truy cập, đồng thời tránh đưa bí mật vào mã nguồn, log hoặc artifact.

Bài học này tập trung vào cách Gradle và Maven kết nối tới repository riêng, cách ánh xạ credentials vào đúng repository, cách cấp secret cho CI và cách điều tra lỗi xác thực.

## 1. Repository riêng và hai loại quyền truy cập

**Artifact repository** là nơi lưu trữ và phân phối các thành phần build như JAR, WAR, POM, Gradle Module Metadata, plugin, sources JAR và artifact đã publish.

Một tổ chức có thể dùng repository manager như Nexus Repository, JFrog Artifactory hoặc một dịch vụ Maven-compatible khác. Repository riêng thường được dùng cho các mục đích:

- Phân phối thư viện nội bộ giữa các project.
- Lưu plugin hoặc convention plugin do tổ chức phát triển.
- Lưu snapshot và bản release chưa công khai.
- Proxy/cache repository bên ngoài để kiểm soát nguồn tải dependency.
- Nhận artifact do pipeline CI publish.

Khi làm việc với repository, cần phân biệt hai luồng chính:

| Luồng | Hoạt động | Quyền thường cần |
|---|---|---|
| Đọc (resolve/download) | Build tool tìm metadata và tải dependency hoặc plugin. | Read hoặc pull. |
| Ghi (publish/deploy) | Build tool tải artifact, metadata và checksum lên repository. | Deploy hoặc write. |

Một pipeline kiểm thử thường chỉ cần quyền đọc dependency. Pipeline phát hành cần quyền ghi vào repository release. Không nên dùng một token có toàn quyền quản trị cho mọi máy lập trình viên và mọi job CI.

### 1.1. Repository dependency khác repository plugin

Gradle có các khu vực cấu hình repository riêng:

- `repositories {}` trong project hoặc `dependencyResolutionManagement.repositories` trong settings dùng để phân giải dependency của ứng dụng.
- `pluginManagement.repositories` trong settings dùng để phân giải plugin được khai báo trong `plugins {}`.
- `publishing.repositories` trong build script dùng để publish artifact.

Ba khu vực có thể trỏ đến cùng một máy chủ repository, nhưng mỗi khu vực phục vụ một mục đích và có thể cần quyền hoặc cấu hình khác nhau.

Maven cũng phân biệt repository dùng cho dependency, `pluginRepositories` dùng để tìm Maven plugin và `distributionManagement` dùng làm đích deploy artifact. `settings.xml` cung cấp thông tin server tương ứng cho các repository này.

Không nên giả định rằng khai báo credentials cho repository dependency sẽ tự động áp dụng cho plugin repository hoặc đích publish. Hãy xác định chính xác request đang truy cập khu vực nào.

## 2. Xác thực và phân quyền là hai việc khác nhau

**Authentication (xác thực)** trả lời câu hỏi: request đến từ người dùng hoặc hệ thống nào? **Authorization (phân quyền)** trả lời câu hỏi: danh tính đó được phép làm gì trên repository hoặc nhóm artifact nào?

Ví dụ, CI có thể xác thực thành công bằng token nhưng vẫn không được publish vào repository release vì token chỉ có quyền đọc. Tương tự, username/password đúng nhưng tài khoản đã bị thu hồi quyền đối với một repository cụ thể.

| Kết quả | Cách hiểu thường gặp |
|---|---|
| Xác thực thành công và có quyền | Có thể đọc hoặc publish theo quyền được cấp. |
| `401 Unauthorized` | Credentials thiếu, sai, hết hạn hoặc không được máy chủ chấp nhận. |
| `403 Forbidden` | Máy chủ nhận diện được danh tính nhưng danh tính không có quyền thực hiện thao tác, tùy cách server triển khai. |
| `404 Not Found` | Artifact hoặc repository không tồn tại; một số hệ thống cũng dùng 404 để không tiết lộ tài nguyên bị hạn chế. |
| `407 Proxy Authentication Required` | Proxy mạng yêu cầu xác thực riêng. |

Mã HTTP chỉ là manh mối. Một số repository manager có thể trả thông báo khác nhau theo chính sách bảo mật. Hãy kiểm tra cả URL, repository ID, token scope, trạng thái tài khoản và quyền trên repository.

## 3. Các hình thức credentials phổ biến

Repository có thể hỗ trợ một hoặc nhiều hình thức xác thực:

| Hình thức | Mô tả | Trường hợp thường gặp |
|---|---|---|
| Username và password | Tên tài khoản cùng mật khẩu. | Repository nội bộ hoặc tài khoản dịch vụ. |
| Username và access token | Token thay cho mật khẩu, thường có scope và thời hạn. | CI, tài khoản dịch vụ, repository manager. |
| HTTP Basic Authentication | Credentials được gửi theo cơ chế Basic qua HTTP request. | Nhiều Maven-compatible repository hỗ trợ. Nên dùng qua HTTPS. |
| HTTP header/token authentication | Token được gửi trong header do repository yêu cầu, ví dụ header riêng hoặc bearer token. | Dịch vụ artifact hỗ trợ token-based authentication. |
| Client certificate hoặc cơ chế SSO | Danh tính được xác thực qua chứng thư hoặc hạ tầng tổ chức. | Môi trường doanh nghiệp có chính sách xác thực tập trung. |

Gradle hỗ trợ các loại credentials và authentication scheme theo cấu hình repository. Maven thường lấy credentials từ server entry trong `settings.xml`, còn cách truyền chúng qua HTTP do Maven transport và repository hỗ trợ quyết định.

Không nên tự suy đoán tên header, loại token hoặc endpoint cấp token. Hãy dùng đúng hướng dẫn của repository manager hoặc nhóm quản trị hệ thống.

## 4. Nguyên tắc lưu trữ và sử dụng credentials

Credentials là bí mật vận hành. Một khi bị lộ, người khác có thể đọc mã nội bộ, tải artifact chưa công khai hoặc publish artifact giả mạo tùy quyền của token.

Các nguyên tắc quan trọng:

1. **Không commit secret vào Git.** Không đặt mật khẩu, access token, private key hoặc nội dung `settings.xml` chứa bí mật trong repository.
2. **Dùng secret store hoặc biến môi trường.** Lấy secret từ kho bí mật của hệ điều hành, CI hoặc nền tảng quản lý secret của tổ chức.
3. **Cấp quyền tối thiểu.** Dùng token read-only cho job cần tải dependency; chỉ cấp quyền publish cho pipeline phát hành.
4. **Tách token theo môi trường và mục đích.** Token local, CI đọc dependency và CI publish nên có phạm vi phù hợp, dễ thu hồi độc lập.
5. **Đặt thời hạn và luân chuyển token.** Thu hồi token khi nhân sự hoặc pipeline không còn cần quyền; thay token theo chính sách bảo mật.
6. **Không in secret ra log.** Tránh `println`, `echo`, `Write-Host`, dump toàn bộ environment hoặc bật log nhạy cảm khi credentials được truyền vào.
7. **Dùng HTTPS và xác minh chứng thư.** Không tắt kiểm tra TLS để vượt qua lỗi chứng thư.
8. **Không truyền secret trên dòng lệnh nếu có lựa chọn an toàn hơn.** Tham số có thể lưu trong shell history hoặc hiển thị trong danh sách process tùy môi trường.
9. **Không đóng gói credentials vào artifact.** JAR, POM, manifest và image không được chứa token truy cập repository.

Một file cấu hình nằm ngoài Git vẫn cần quyền truy cập hệ điều hành phù hợp. Ví dụ `~/.gradle/gradle.properties` hoặc `~/.m2/settings.xml` có thể chứa credentials cho máy cá nhân; hãy hạn chế quyền đọc file và không đồng bộ nó vào kho mã nguồn.

## 5. Cấu hình repository riêng trong Gradle

Gradle cho phép khai báo Maven repository trong `repositories {}`. Ví dụ sau minh họa một repository nội bộ chỉ dùng để đọc dependency:

```groovy
repositories {
    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.com/maven/releases')

        credentials(PasswordCredentials)
    }
    mavenCentral()
}
```

Khai báo `credentials(PasswordCredentials)` cho Gradle biết repository này dùng username/password credentials. Tên repository `companyReleases` cũng giúp Gradle xác định các project properties dùng để lấy username và password.

### 5.1. Cung cấp credentials qua Gradle properties

Với repository tên `companyReleases`, Gradle có thể lấy hai property:

```text
companyReleasesUsername
companyReleasesPassword
```

Trên máy cá nhân, có thể lưu các property này trong file người dùng:

```text
<GRADLE_USER_HOME>/gradle.properties
```

Thông thường Gradle User Home nằm ở `~/.gradle` trên Linux/macOS hoặc thư mục `.gradle` trong profile người dùng trên Windows. Ví dụ cấu trúc property:

```properties
companyReleasesUsername=your-account
companyReleasesPassword=your-token
```

Các giá trị trên chỉ là placeholder. Hãy thay bằng credentials do tổ chức cấp và bảo đảm file này không nằm trong repository. Nếu cần dùng một file khác, Gradle cũng hỗ trợ cấu hình Gradle User Home phù hợp với môi trường.

Trong CI, có thể cung cấp project property qua biến môi trường theo quy ước `ORG_GRADLE_PROJECT_`:

```text
ORG_GRADLE_PROJECT_companyReleasesUsername
ORG_GRADLE_PROJECT_companyReleasesPassword
```

Giá trị của hai biến phải được lấy từ secret store của CI. Không ghi token trực tiếp vào YAML pipeline hoặc build script.

### 5.2. Khai báo credentials tường minh

Trong một số build, bạn muốn chỉ rõ nguồn cấp secret. Có thể lấy giá trị từ Gradle property hoặc environment variable bằng Provider API:

```groovy
def repoUser = providers.gradleProperty('companyRepoUser')
    .orElse(providers.environmentVariable('COMPANY_REPO_USER'))

def repoToken = providers.gradleProperty('companyRepoToken')
    .orElse(providers.environmentVariable('COMPANY_REPO_TOKEN'))

repositories {
    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.com/maven/releases')

        credentials {
            username = repoUser.get()
            password = repoToken.get()
        }
    }
}
```

Đoạn mã minh họa cách lấy secret từ provider; khi chạy trong môi trường không có property hoặc biến môi trường tương ứng, `get()` sẽ không có giá trị để cung cấp và build cần được cấu hình credentials trước khi truy cập repository. Có thể bổ sung kiểm tra cấu hình phù hợp với yêu cầu project để thông báo lỗi rõ ràng.

Với repository chỉ cần truy cập công khai trong local nhưng cần xác thực trong CI, có thể tách cấu hình theo môi trường hoặc dùng repository manager cho phép đọc công khai. Không nên đưa token giả hoặc token rỗng vào cấu hình rồi giả định mọi server đều xử lý giống nhau.

### 5.3. Giới hạn nhóm artifact mà repository được phép cung cấp

Gradle hỗ trợ content filtering để giới hạn group nào được tìm trong repository:

```groovy
repositories {
    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.com/maven/releases')
        credentials(PasswordCredentials)

        content {
            includeGroupByRegex('com\\.example(\\..*)?')
        }
    }

    mavenCentral()
}
```

Content filter giúp tránh gửi yêu cầu tìm một module không thuộc phạm vi repository nội bộ. Điều này làm cấu hình resolution rõ ràng hơn, giảm request không cần thiết và hỗ trợ hạn chế việc dependency nội bộ bị tìm nhầm từ repository công khai.

Repository manager cũng có thể được cấu hình để proxy hoặc chỉ phục vụ một nhóm artifact. Hãy thống nhất quy tắc ở cả client và server để tránh dependency confusion, tức tình huống cùng tọa độ module có thể được lấy từ nguồn không mong muốn.

### 5.4. Phân biệt release và snapshot repository

Nhiều tổ chức tách repository release và snapshot. Gradle có thể giới hạn nội dung repository:

```groovy
repositories {
    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.com/maven/releases')
        credentials(PasswordCredentials)
        mavenContent {
            releasesOnly()
        }
    }

    maven {
        name = 'companySnapshots'
        url = uri('https://repo.example.com/maven/snapshots')
        credentials(PasswordCredentials)
        mavenContent {
            snapshotsOnly()
        }
    }
}
```

`releasesOnly()` và `snapshotsOnly()` cho Gradle biết loại module version nào nên được tìm ở repository tương ứng. Quy tắc này cần khớp chính sách của server và cách version được đặt.

## 6. Xác thực repository plugin của Gradle

Nếu plugin được lưu trong repository riêng, cần khai báo repository đó trong `pluginManagement.repositories` của `settings.gradle`:

```groovy
pluginManagement {
    repositories {
        maven {
            name = 'companyPlugins'
            url = uri('https://repo.example.com/gradle-plugins')
            credentials(PasswordCredentials)
        }
        gradlePluginPortal()
    }
}
```

Với repository tên `companyPlugins`, Gradle có thể lấy property tương ứng:

```text
companyPluginsUsername
companyPluginsPassword
```

Trong CI, có thể đưa vào qua:

```text
ORG_GRADLE_PROJECT_companyPluginsUsername
ORG_GRADLE_PROJECT_companyPluginsPassword
```

Plugin DSL thường cần plugin marker artifact để ánh xạ plugin ID sang implementation. Nếu repository nội bộ chỉ lưu implementation artifact mà không lưu marker, build có thể cần `pluginManagement.resolutionStrategy` để ánh xạ ID sang module implementation theo hướng dẫn của plugin. Lỗi không tìm thấy plugin có thể là vấn đề marker hoặc plugin mapping, không nhất thiết là lỗi username/password.

Nếu build dùng `buildscript { repositories { ... } }` cho một build script dependency cũ, đó là một classpath khác và cần cấu hình repository/credentials trong đúng khối `buildscript`. Không nên cho rằng repository dependency của project tự động áp dụng cho buildscript classpath.

## 7. Publish artifact lên repository riêng bằng Gradle

Để publish Java component, thường dùng `maven-publish` plugin:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.orders'
version = '1.4.0'

publishing {
    publications {
        create('mavenJava', MavenPublication) {
            from components.java
        }
    }

    repositories {
        maven {
            name = 'companyReleases'
            url = uri('https://repo.example.com/maven/releases')
            credentials(PasswordCredentials)
        }
    }
}
```

Vì repository tên `companyReleases`, Gradle dùng property `companyReleasesUsername` và `companyReleasesPassword` cho credentials. Pipeline publish cần token có quyền deploy vào repository release. Không nên tái sử dụng token đọc dependency nếu token đó không có quyền ghi; cũng không nên cấp quyền ghi cho mọi build kiểm thử.

Lệnh publish thường là:

```bash
./gradlew publish
```

Task publish có thể tạo và tải lên POM, artifact chính, sources hoặc metadata bổ sung tùy publication. Hãy kiểm tra repository đích, version và quyền ghi trước khi chạy pipeline release.

## 8. Cấu hình repository riêng trong Maven

Maven dùng `pom.xml` để khai báo repository hoặc đích deploy, còn credentials thường nằm trong `settings.xml`. Hai tệp có nhiệm vụ riêng:

- `pom.xml` là cấu hình dự án được commit cùng mã nguồn, chứa URL/ID repository và quy tắc build không bí mật.
- `settings.xml` là cấu hình theo môi trường hoặc người dùng, chứa server credentials, mirror, proxy và các thiết lập riêng của máy.

### 8.1. Khai báo repository để tải dependency

Trong `pom.xml`:

```xml
<repositories>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.com/maven/releases</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
```

ID `company-releases` là định danh để Maven liên kết repository này với cấu hình server tương ứng trong `settings.xml`.

### 8.2. Khai báo credentials trong `settings.xml`

Ví dụ cấu hình trong file `settings.xml` của người dùng:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.REPO_USER}</username>
            <password>${env.REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Maven ghép server entry với repository bằng `id`. Trong ví dụ, ID trong `<server>` phải khớp `company-releases` trong POM. Các placeholder `${env.REPO_USER}` và `${env.REPO_TOKEN}` lấy giá trị từ environment của tiến trình Maven.

Trên máy cá nhân, file người dùng thường ở `~/.m2/settings.xml` hoặc vị trí Maven được cấu hình. Trong CI, nên tạo hoặc cung cấp settings file từ secret store trong workspace tạm có quyền truy cập hạn chế, rồi xóa sau job theo cơ chế bảo vệ của runner.

Không commit `settings.xml` chứa credentials vào repository. Nếu cần cung cấp một mẫu cấu hình cho nhóm, chỉ commit file mẫu không có secret và ghi rõ tên biến môi trường cần thiết.

### 8.3. Publish artifact bằng Maven Deploy Plugin

Trong `pom.xml`, khai báo đích deploy:

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

Trong `settings.xml`, có thể có hai server entry:

```xml
<servers>
    <server>
        <id>company-releases</id>
        <username>${env.REPO_RELEASE_USER}</username>
        <password>${env.REPO_RELEASE_TOKEN}</password>
    </server>
    <server>
        <id>company-snapshots</id>
        <username>${env.REPO_SNAPSHOT_USER}</username>
        <password>${env.REPO_SNAPSHOT_TOKEN}</password>
    </server>
</servers>
```

Maven chọn server credentials theo ID của repository đích. Release và snapshot có thể dùng token khác nhau để giới hạn quyền. Lệnh deploy thường dùng:

```bash
./mvnw deploy
```

Lệnh này chạy lifecycle đến deploy theo cấu hình POM. Hãy bảo đảm version, repository URL và quyền publish phù hợp trước khi chạy trong pipeline phát hành.

### 8.4. Repository mirror và ID của server

Maven có thể chuyển mọi request hoặc một nhóm repository qua mirror được khai báo trong `settings.xml`:

```xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>*</mirrorOf>
        <url>https://repo.example.com/maven/group</url>
    </mirror>
</mirrors>
```

Khi request được chuyển qua mirror, credentials thường cần được khai báo cho ID của mirror đang được dùng, ở đây là `company-mirror`. Đây là nguyên nhân phổ biến khiến cấu hình server ID ban đầu không được sử dụng như mong đợi sau khi thêm mirror.

Mirror có thể giúp tổ chức tập trung kiểm soát nguồn dependency, cache và audit. Tuy nhiên, cần cấu hình `mirrorOf` đúng để không vô tình chuyển cả repository publish hoặc plugin repository theo một chính sách không phù hợp.

### 8.5. Plugin repository và credentials trong Maven

Maven dùng `<pluginRepositories>` để khai báo repository phân phối plugin:

```xml
<pluginRepositories>
    <pluginRepository>
        <id>company-plugin-releases</id>
        <url>https://repo.example.com/maven/plugins</url>
    </pluginRepository>
</pluginRepositories>
```

Nếu plugin repository yêu cầu xác thực, thêm `<server>` có ID `company-plugin-releases` trong `settings.xml`. Plugin dependency và dependency ứng dụng được phân giải theo các luồng khác nhau; hãy đối chiếu đúng repository ID khi điều tra lỗi tải plugin.

## 9. Bảo vệ credentials trong CI

CI thường cần tải dependency nội bộ ở mỗi lần build. Chỉ pipeline phát hành mới cần credentials ghi repository. Hãy lấy secret từ cơ chế quản lý bí mật của CI và chỉ cấp cho job cần dùng.

Ví dụ khái quát với GitHub Actions:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build with private repository access
        env:
          ORG_GRADLE_PROJECT_companyReleasesUsername: ${{ secrets.REPO_USER }}
          ORG_GRADLE_PROJECT_companyReleasesPassword: ${{ secrets.REPO_READ_TOKEN }}
        run: ./gradlew clean build
```

Ví dụ này cấp credentials đọc repository cho đúng bước build. Trong pipeline thực tế, hãy dùng action/setup Java hoặc cơ chế toolchain phù hợp với dự án và cấu hình secret theo chính sách của tổ chức.

Với job publish, dùng token có quyền ghi riêng và chỉ cấp trên branch/tag hoặc workflow phát hành đáng tin cậy. Không cấp publish token cho mọi pull request.

### 9.1. Không đưa secret cho pull request từ fork

Một pull request từ fork hoặc nguồn không tin cậy có thể sửa build script, plugin, test hoặc workflow để đọc biến môi trường và gửi dữ liệu ra ngoài. Vì vậy:

- Không cấp secret publish cho job chạy mã không tin cậy.
- Kiểm soát quyền chạy workflow có quyền ghi repository.
- Tách build kiểm thử pull request khỏi job publish release.
- Chỉ cấp secret sau bước phê duyệt hoặc điều kiện branch protection phù hợp.
- Hạn chế quyền của token theo repository, package và thao tác cần thiết.

Masking secret trong log là lớp bảo vệ hữu ích nhưng không thay thế việc giới hạn nơi secret được cấp. Một script độc hại có thể mã hóa hoặc biến đổi secret trước khi in, khiến cơ chế masking không nhận ra.

### 9.2. Tách token đọc và token ghi

Một mô hình thường dùng:

| Job | Quyền cần | Token đề xuất |
|---|---|---|
| Build pull request nội bộ | Đọc dependency riêng | Token read-only, giới hạn repository cần thiết. |
| Build trên branch tin cậy | Đọc dependency và chạy kiểm tra | Token read-only. |
| Release pipeline | Đọc dependency và publish artifact | Token publish có quyền ghi đúng repository release. |
| Job quản trị repository | Tạo repository, thay quyền, quản lý user | Tài khoản quản trị riêng, không dùng trong build thông thường. |

Tách token giúp thu hồi hoặc điều tra sự cố theo đúng luồng. Nếu token đọc bị lộ, người tấn công không nên có quyền ghi đè artifact release.

## 10. Password encryption và file cấu hình cục bộ của Maven

Maven hỗ trợ cơ chế mã hóa password trong `settings.xml` thông qua master password và `settings-security.xml`. Cơ chế này giúp tránh lưu mật khẩu dạng rõ trong một số tình huống, nhưng không nên xem nó như một secret vault hoặc cơ chế chống lại người đã chiếm quyền truy cập tài khoản hệ điều hành.

Nếu dùng password encryption:

- Bảo vệ `settings-security.xml` và master password như thông tin nhạy cảm.
- Hạn chế quyền đọc các file cấu hình.
- Không commit file chứa password hoặc master password.
- Trong CI, ưu tiên secret store và cách cung cấp credentials được nền tảng hỗ trợ.
- Kiểm tra cách phiên bản Maven đang dùng xử lý encrypted password trước khi thiết kế pipeline.

Mã hóa password tại chỗ chỉ giải quyết một phần vấn đề lưu trữ. Nếu tiến trình Maven có thể giải mã và sử dụng password, một người kiểm soát tiến trình hoặc tài khoản đó có thể có cách lấy thông tin tương ứng.

## 11. TLS, proxy và chứng thư của repository

Repository riêng nên được truy cập qua HTTPS với chứng thư máy chủ hợp lệ. Nếu build báo lỗi certificate hoặc PKIX, hãy kiểm tra:

- URL có đúng hostname và scheme HTTPS không?
- Chứng thư còn hạn và được ký bởi CA mà JDK tin cậy không?
- Runner có trust store phù hợp với CA nội bộ không?
- Proxy doanh nghiệp có can thiệp TLS và yêu cầu cấu hình trust store riêng không?
- JDK dùng để chạy Gradle/Maven có trust store khác JDK trên máy cá nhân không?

Trong môi trường doanh nghiệp, CA nội bộ có thể cần được cài vào trust store phù hợp của JDK hoặc runner theo hướng dẫn quản trị. Không nên xử lý lỗi bằng cách tắt kiểm tra hostname hoặc bỏ qua xác thực chứng thư. Làm vậy có thể cho phép kẻ trung gian giả mạo repository và cung cấp artifact độc hại.

Proxy xác thực là một lớp khác với credentials repository. Nếu proxy trả `407`, cần cấu hình proxy theo hướng dẫn của môi trường; không nên thay token repository khi lỗi thực chất nằm ở proxy.

## 12. Điều tra lỗi xác thực repository

Khi tải dependency hoặc publish thất bại, hãy xác định request nào bị lỗi trước khi thay đổi credentials.

| Triệu chứng | Nguyên nhân có thể | Nơi kiểm tra |
|---|---|---|
| Gradle không tải được dependency nội bộ | Repository URL sai, credentials thiếu/sai, token hết hạn hoặc thiếu quyền đọc | `repositories`, tên repository, Gradle properties và secret CI. |
| Gradle không tìm thấy plugin nội bộ | Cấu hình `pluginManagement`, plugin marker hoặc credentials plugin repository chưa đúng | `settings.gradle`, plugin ID/version và repository plugin. |
| Maven báo 401 khi tải dependency | Server ID không khớp repository hoặc credentials không được nạp | `pom.xml`, `settings.xml`, `id` của repository/mirror và environment. |
| Maven deploy báo 401/403 | Token hết hạn, sai server ID hoặc tài khoản thiếu quyền ghi | `distributionManagement`, `<servers>` và quyền deploy. |
| Maven tải từ mirror nhưng không xác thực được | Server entry dùng ID repository gốc thay vì ID mirror | `settings.xml` phần `<mirrors>` và `<servers>`. |
| Local build thành công nhưng CI thất bại | Local có credentials trong user home/cache, CI thiếu secret hoặc dùng token khác | Secret mapping, runner identity và repository permissions. |
| Build chỉ lỗi trên một JDK/runner | TLS trust store hoặc proxy khác nhau | JDK thực tế, CA trust store và proxy config. |
| Publish thành công nhưng artifact không có ở repository mong muốn | URL, repository ID hoặc target release/snapshot sai | Log publish và cấu hình destination. |
| 404 với artifact private | Artifact sai tọa độ hoặc server che giấu tài nguyên không được phép truy cập | Group/artifact/version, classifier và quyền đọc. |

### 12.1. Quy trình kiểm tra với Gradle

1. Xác định task thất bại: dependency resolution, plugin resolution hay publish.
2. Kiểm tra repository URL, tên repository và phạm vi cấu hình.
3. Xác nhận Gradle nhận được property cần thiết mà không in giá trị secret.
4. Kiểm tra token còn hạn, đúng scope và có quyền read hoặc publish.
5. Xem log vừa đủ chi tiết để xác định host, repository và loại lỗi; tránh chia sẻ log chứa header hoặc credentials.
6. Nếu nghi ngờ TLS, kiểm tra JDK và trust store thay vì tắt xác thực.

Các lệnh hỗ trợ xem cấu hình và dependency:

```bash
./gradlew repositories
./gradlew dependencies --configuration runtimeClasspath
./gradlew build --info
```

Task `repositories` không phải task mặc định có mặt trong mọi Gradle project; nếu dự án không có task này, kiểm tra repository trong settings/build script và dùng log resolution phù hợp. `--info` có thể hiển thị thêm thông tin vận hành, nhưng không nên công khai log chưa được kiểm tra.

### 12.2. Quy trình kiểm tra với Maven

1. Xác định request đang tải dependency, plugin hay deploy artifact.
2. So sánh repository ID trong POM với server ID trong `settings.xml`.
3. Nếu có mirror, kiểm tra server ID của mirror đang thay thế repository.
4. Kiểm tra biến môi trường được Maven process nhận và token có quyền phù hợp.
5. Kiểm tra `distributionManagement` khi deploy, thay vì chỉ xem `<repositories>` dùng để tải dependency.
6. Nếu cần log debug, chỉ lưu và chia sẻ log sau khi loại bỏ thông tin nhạy cảm.

Các lệnh hỗ trợ:

```bash
./mvnw help:effective-settings
./mvnw help:effective-pom
./mvnw dependency:tree
```

`help:effective-settings` giúp xem settings đã hợp nhất, nhưng cần cẩn thận vì output có thể chứa thông tin cấu hình nhạy cảm tùy môi trường và plugin. Không đưa nguyên output vào issue công khai hoặc chat nếu chưa rà soát.

## 13. Tránh dependency confusion và nhầm nguồn artifact

Một module nội bộ có thể có tọa độ giống hoặc gần giống một module công khai. Nếu build tool tìm module đó ở repository không mong muốn, ứng dụng có thể tải nhầm artifact.

Ví dụ, công ty dùng group `com.example.internal` cho thư viện nội bộ. Nếu repository nội bộ không được cấu hình đúng, build có thể tìm module theo các nguồn khác hoặc thất bại. Một rủi ro nghiêm trọng hơn xuất hiện khi kẻ tấn công publish một package cùng tọa độ hoặc tên ở repository có độ ưu tiên hoặc chính sách resolution không như mong đợi.

Biện pháp giảm rủi ro:

- Dùng namespace group nội bộ được kiểm soát.
- Giới hạn group bằng content filters hoặc repository routing.
- Dùng repository manager làm nguồn proxy được quản lý.
- Hạn chế thêm repository tùy tiện vào build script.
- Kiểm soát repository order và policy cho release/snapshot.
- Xác minh checksum, chữ ký hoặc provenance cho artifact quan trọng.
- Không để build release phụ thuộc vào version động không được kiểm soát.

Trong Gradle, `content { includeGroup(...) }` hoặc `includeGroupByRegex(...)` giúp giới hạn nhóm module mà repository phục vụ. Trong Maven, mirror và repository manager có thể tập trung nguồn tải. Chính sách server vẫn cần được cấu hình tương ứng; filter phía client không thay thế xác thực hoặc quyền truy cập ở server.

## 14. Ví dụ hoàn chỉnh: local và CI cùng truy cập repository riêng

Giả sử công ty có repository Maven-compatible:

```text
https://repo.example.com/maven/releases
```

Project Gradle cần tải dependency nội bộ. Build script:

```groovy
repositories {
    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.com/maven/releases')
        credentials(PasswordCredentials)
        content {
            includeGroupByRegex('com\\.example(\\..*)?')
        }
    }
    mavenCentral()
}

dependencies {
    implementation 'com.example.orders:order-api:2.1.0'
}
```

Trên máy lập trình viên, credentials được lưu trong Gradle User Home, không nằm trong project. Trên CI, secret store cung cấp:

```text
ORG_GRADLE_PROJECT_companyReleasesUsername
ORG_GRADLE_PROJECT_companyReleasesPassword
```

Job build dùng token chỉ có quyền đọc. Job phát hành dùng một repository publish riêng và token chỉ có quyền deploy vào repository đó.

Nếu project dùng Maven, POM khai báo repository ID `company-releases`; `settings.xml` của local hoặc CI cung cấp `<server>` cùng ID và lấy username/token từ environment. Nếu publish, POM khai báo `distributionManagement` với ID đích và Maven dùng server entry tương ứng.

Nhờ cấu hình URL/ID nằm trong project và secret nằm trong môi trường, local và CI có thể dùng cùng quy tắc repository mà mỗi nơi vẫn dùng credentials riêng.

## 15. Một số hiểu nhầm thường gặp

### “Repository URL và password có thể commit cùng build script cho tiện”

URL repository thường không phải bí mật, nhưng password hoặc token là bí mật. Hãy commit cấu hình không nhạy cảm và cấp credentials từ user home hoặc secret store của CI.

### “Dùng token có nghĩa token có thể làm mọi việc”

Token có scope và quyền riêng. Token đọc dependency có thể không được phép publish; token hết hạn hoặc bị thu hồi cũng có thể làm build thất bại.

### “Khai báo credentials ở repository dependency là đủ cho plugin và publish”

Gradle có khu vực repository riêng cho dependency, plugin và publishing. Maven có repository, pluginRepository và distributionManagement. Hãy cấu hình đúng request path và ID.

### “Maven server ID có thể đặt tùy ý”

Server entry phải khớp ID repository hoặc mirror mà Maven thực sự sử dụng. Nếu ID không khớp, Maven có thể không chọn credentials mong muốn.

### “401 và 403 có nghĩa giống nhau”

401 thường chỉ ra vấn đề xác thực; 403 thường chỉ ra vấn đề quyền. Tuy nhiên, repository manager có thể dùng phản hồi khác để che giấu tài nguyên. Cần kiểm tra log và quyền thực tế.

### “Lỗi TLS có thể xử lý bằng cách bỏ qua kiểm tra chứng thư”

Không nên. Hãy cài CA tin cậy và cấu hình đúng trust store. Tắt kiểm tra TLS khiến build có nguy cơ tải artifact từ máy chủ giả mạo.

### “Secret được mask trong CI log nên có thể cấp cho mọi pull request”

Không. Mã trong pull request không tin cậy có thể đọc biến môi trường và gửi secret ra ngoài theo cách không bị masking phát hiện. Hãy chỉ cấp secret cho job và nguồn mã đáng tin cậy.

## 16. Thực hành: cấu hình repository riêng an toàn

Trong một project Gradle hoặc Maven thử nghiệm, hãy thực hiện các bước sau với repository test do tổ chức cung cấp:

1. Xác định URL repository và loại thao tác cần thực hiện: tải dependency, tải plugin hay publish.
2. Tạo hoặc nhận một token read-only dành cho việc tải dependency.
3. Khai báo URL và repository name/ID trong build configuration.
4. Cấu hình credentials ở Gradle User Home hoặc Maven `settings.xml`, không đặt secret trong project.
5. Chạy lệnh build để xác nhận dependency được tải.
6. Thử token thiếu quyền hoặc hết hạn trong môi trường test được phép để quan sát lỗi xác thực và phân quyền.
7. Nếu có pipeline, đưa token qua secret store và chỉ cấp cho job cần truy cập.
8. Tạo token publish riêng cho repository thử nghiệm và kiểm tra quyền ghi bằng một artifact không quan trọng.
9. Kiểm tra log để chắc chắn không có token hoặc password xuất hiện.
10. Thu hồi token thử nghiệm khi không còn sử dụng.

Với Gradle, quan sát sự khác nhau giữa `repositories`, `pluginManagement.repositories` và `publishing.repositories`. Với Maven, kiểm tra `<repositories>`, `<pluginRepositories>`, `<distributionManagement>` và ID tương ứng trong `<servers>`.

Sau khi thực hành, hãy tự trả lời:

- Xác thực và phân quyền khác nhau thế nào?
- Vì sao repository dependency, plugin và publish có thể cần credentials riêng?
- Gradle lấy credentials cho repository được đặt tên như thế nào?
- Vì sao Maven `<server><id>` phải khớp repository hoặc mirror ID?
- Khi nào nên dùng token read-only và khi nào cần token publish?
- Vì sao không cấp secret cho job chạy pull request từ fork?
- Lỗi 401, 403, 404, 407 và lỗi TLS gợi ý những hướng điều tra nào?
- Content filtering và repository manager giúp giảm rủi ro dependency confusion ra sao?

## 17. Kết luận

Repository riêng cần xác thực để nhận diện người dùng hoặc job và phân quyền để quyết định thao tác đọc hoặc ghi. Gradle cấu hình repository dependency, plugin và publishing ở những khu vực riêng; credentials có thể được cung cấp qua Gradle properties hoặc environment variables do CI quản lý. Maven khai báo URL và repository ID trong POM, còn credentials được ánh xạ qua server entry trong `settings.xml`; khi dùng mirror, cần kiểm tra ID của mirror thực tế.

Hãy lưu secret ngoài repository, cấp quyền tối thiểu, tách token đọc và ghi, giới hạn job được nhận secret, dùng HTTPS với trust store hợp lệ và không để credentials xuất hiện trong log hoặc artifact. Khi build lỗi, xác định request đang truy cập repository nào, kiểm tra URL/ID, token scope, quyền và TLS trước khi thay đổi cấu hình. Cách làm này giúp cả máy lập trình viên và CI truy cập artifact nội bộ một cách an toàn và nhất quán.
