# Phân biệt tạo artifact, đưa vào kho cục bộ và xuất bản từ xa

Trong quy trình build Java, các từ *package*, *install* và *publish/deploy* thường xuất hiện gần nhau nhưng mô tả những việc khác nhau. Một project có thể tạo ra file JAR thành công mà chưa đưa file đó vào kho nào; có thể cài artifact vào kho Maven cục bộ để project khác trên cùng máy sử dụng; hoặc có thể xuất bản artifact lên repository từ xa để đồng đội, CI và các ứng dụng khác tải về.

Ba hoạt động này cần được phân biệt rõ:

- **Tạo artifact (package/assemble):** biên dịch và đóng gói output của project thành JAR, WAR, ZIP hoặc định dạng khác.
- **Đưa vào kho cục bộ (install to local repository):** lưu artifact cùng metadata vào repository trên máy đang build để các build khác trên máy đó phân giải được.
- **Xuất bản từ xa (publish/deploy):** gửi artifact và metadata lên repository server có thể được nhiều máy truy cập theo quyền được cấp.

Sơ đồ tổng quát:

```text
Source code + dependencies
          |
          v
     Compile / test
          |
          v
   Create artifact
    JAR / WAR / ZIP
          |
          +--------------------+
          |                    |
          v                    v
  Local repository      Remote repository
  (Maven local)         (Nexus / Artifactory / registry)
          |                    |
          v                    v
  Builds on same       Builds on other machines,
  machine can use it   CI and consumers can use it
```

Tạo file JAR không tự động có nghĩa artifact đã được publish. `mvn install` không upload lên server. `mvn deploy` mới thực hiện bước triển khai artifact lên remote repository theo cấu hình Maven. Trong Gradle, `assemble` tạo output, `publishToMavenLocal` đưa publication vào Maven local repository, còn task `publish...Repository` gửi publication tới repository đã khai báo.

## 1. Artifact là gì?

Artifact là sản phẩm được tạo từ project để lưu trữ, sử dụng hoặc phân phối. Trong hệ sinh thái Java, các dạng thường gặp gồm:

| Artifact | Ví dụ | Mục đích |
|---|---|---|
| JAR | `order-domain-2.4.0.jar` | Thư viện Java hoặc ứng dụng đóng gói |
| WAR | `order-web-2.4.0.war` | Ứng dụng web triển khai trên servlet container |
| Sources JAR | `order-domain-2.4.0-sources.jar` | Source code đi kèm thư viện |
| Javadoc JAR | `order-domain-2.4.0-javadoc.jar` | Tài liệu API |
| ZIP/TAR distribution | `order-service-2.4.0.zip` | Ứng dụng cùng thư viện, script và cấu hình mẫu |
| Container image | `registry.example.com/order-service:2.4.0` | Ứng dụng cùng runtime và filesystem image |

Artifact có thể được tạo trong thư mục output của build, ví dụ `target/` với Maven hoặc `build/libs/` với Gradle. Ở giai đoạn này, file chỉ tồn tại trong workspace của build. Một project khác chưa thể khai báo dependency tới artifact đó qua repository chung nếu artifact chưa được cài hoặc publish vào nơi mà project kia tìm kiếm.

## 2. Tạo artifact không đồng nghĩa với install hoặc publish

Giả sử module có tọa độ:

```text
groupId:    com.example
artifactId: order-domain
version:    2.4.0
packaging:  jar
```

Khi đóng gói, build tạo file:

```text
order-domain-2.4.0.jar
```

File này có thể nằm trong:

```text
Maven:  target/order-domain-2.4.0.jar
Gradle: build/libs/order-domain-2.4.0.jar
```

Các thư mục trên là output của project. Chúng không phải Maven local repository và cũng không phải remote repository. Nếu chỉ gửi đường dẫn file JAR cho một người khác, người đó có thể dùng file thủ công, nhưng build tool không tự tìm thấy artifact theo tọa độ dependency cho tới khi file và metadata được đặt trong một repository mà build đã cấu hình.

### 2.1. Tại sao cần phân biệt?

- Khi chỉ cần kiểm tra sản phẩm vừa tạo, đọc file trong `target/` hoặc `build/libs/` là đủ.
- Khi muốn một project khác trên cùng máy sử dụng bản thư viện đang phát triển, local repository có thể tiện lợi.
- Khi muốn nhiều máy, CI hoặc nhóm phát triển sử dụng cùng artifact, cần remote repository.
- Khi phát hành release, cần lưu artifact và metadata ở nơi có version, quyền truy cập và retention rõ ràng.

## 3. Maven: các phase `package`, `install` và `deploy`

Maven tổ chức build theo lifecycle. Trong default lifecycle, ba phase liên quan trực tiếp tới bài học này là:

| Phase | Vai trò |
|---|---|
| `package` | Đóng gói output thành artifact theo packaging của project |
| `install` | Cài artifact và metadata vào local repository |
| `deploy` | Xuất bản artifact và metadata lên remote repository |

Các phase nằm theo thứ tự trong cùng lifecycle. Khi chạy một phase, Maven thực hiện các phase trước đó trong lifecycle tương ứng.

### 3.1. `mvn package`: chỉ tạo artifact trong project output

```bash
mvn package
```

Maven thực hiện các phase trước `package`, như validate, compile, test và package theo lifecycle/plugin đã cấu hình. Với project JAR thông thường, file được tạo dưới `target/`.

Lệnh này không đưa artifact vào Maven local repository và cũng không gửi artifact lên remote repository.

### 3.2. `mvn install`: đưa artifact vào local repository

```bash
mvn install
```

Maven chạy các phase trước `install`, bao gồm package, rồi cài artifact và POM tương ứng vào local repository. Vị trí mặc định thường là:

```text
Linux/macOS: ~/.m2/repository
Windows:     %USERPROFILE%\.m2\repository
```

Với tọa độ `com.example:order-domain:2.4.0`, file có thể được lưu tại:

```text
~/.m2/repository/com/example/order-domain/2.4.0/
    order-domain-2.4.0.jar
    order-domain-2.4.0.pom
```

Project khác trên cùng máy có thể khai báo dependency tới tọa độ đó. Maven sẽ tìm artifact trong local repository trước khi cần tải từ remote repository theo quy tắc phân giải.

`install` ở đây có nghĩa cài package vào kho Maven cục bộ. Nó không cài ứng dụng thành Windows service, không copy JAR vào `/usr/bin` và không triển khai ứng dụng lên server.

### 3.3. `mvn deploy`: xuất bản lên remote repository

```bash
mvn deploy
```

Maven chạy các phase trước `deploy`, bao gồm package và install, sau đó plugin deploy gửi artifact cùng metadata lên remote repository được cấu hình. Remote repository thường là repository manager của tổ chức hoặc dịch vụ package hosting.

Khi publish thành công, máy khác có thể tải artifact theo tọa độ dependency nếu repository đó được khai báo và người dùng có quyền truy cập.

### 3.4. So sánh trực tiếp Maven

| Lệnh | Tạo file trong `target/` | Ghi vào `~/.m2/repository` | Upload remote repository |
|---|---:|---:|---:|
| `mvn package` | Có | Không | Không |
| `mvn install` | Có | Có | Không |
| `mvn deploy` | Có | Có theo lifecycle | Có |

Vì Maven chạy tuần tự qua các phase, `mvn deploy` không chỉ upload một file đã có. Nó thực hiện lifecycle từ đầu đến phase deploy. Nếu CI cần bảo đảm artifact được kiểm tra trước khi phát hành, hãy cấu hình test/verification ở đúng phase và chỉ cấp quyền deploy cho job đã đạt điều kiện.

## 4. Maven local repository và remote repository

### 4.1. Local repository

Local repository là kho artifact trên máy người dùng. Mặc định nó nằm trong `.m2/repository`, nhưng có thể thay đổi qua `settings.xml`:

```xml
<settings>
  <localRepository>D:/maven-cache/repository</localRepository>
</settings>
```

Ví dụ trên chỉ minh họa vị trí tùy chỉnh. Local repository thường chứa:

- Dependency tải từ remote repository.
- Maven plugin và các dependency của plugin.
- Artifact do chính người dùng cài qua `mvn install`.
- POM và metadata cần cho việc phân giải.

Vì vậy, xóa local repository có thể khiến Maven phải tải lại nhiều dependency và làm mất artifact nội bộ chỉ mới được `install` trên máy đó.

### 4.2. Remote repository

Remote repository là kho package được truy cập qua mạng. Ví dụ:

- Maven Central cho thư viện công khai.
- Nexus hoặc Artifactory do tổ chức quản lý.
- GitHub Packages hoặc package registry của nền tảng khác.
- Repository nội bộ lưu artifact release và snapshot.

Remote repository có thể cung cấp artifact cho nhiều máy và nhiều pipeline. Nó là nơi phù hợp để phân phối artifact dùng chung, không phụ thuộc local repository của một developer.

### 4.3. Repository dùng để đọc và repository dùng để publish

Maven phân biệt repository để phân giải dependency với đích publish:

- `<repositories>` khai báo nguồn Maven tìm dependency của project.
- `<pluginRepositories>` khai báo nguồn tìm Maven plugin.
- `<distributionManagement>` khai báo đích deploy artifact của project.
- `settings.xml` chứa mirror, server credentials, proxy và cấu hình theo người dùng/môi trường.

Ví dụ khai báo đích phát hành trong `pom.xml`:

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

`repository` là đích cho release; `snapshotRepository` là đích cho snapshot. URL là placeholder và cần thay bằng endpoint thực tế của tổ chức.

Không nên nhầm `<repositories>` với `<distributionManagement>`. Một phần mô tả nơi tải dependency; phần còn lại mô tả nơi upload artifact do project tạo ra.

## 5. Cấu hình credential Maven để publish

Maven thường ghép `id` trong `distributionManagement` với `id` trong `<servers>` của `settings.xml` để tìm credential.

Ví dụ `~/.m2/settings.xml`:

```xml
<settings>
  <servers>
    <server>
      <id>company-releases</id>
      <username>${env.REPO_USERNAME}</username>
      <password>${env.REPO_PASSWORD}</password>
    </server>
    <server>
      <id>company-snapshots</id>
      <username>${env.REPO_USERNAME}</username>
      <password>${env.REPO_PASSWORD}</password>
    </server>
  </servers>
</settings>
```

Các biến môi trường là placeholder. Trong CI, cấp giá trị từ secret store của nền tảng. Không commit token/password vào `pom.xml`, không in secret ra log và không dùng chung credential có quyền deploy release cho job không đáng tin cậy.

Chạy publish:

```bash
mvn deploy
```

Nếu gặp 401/403, kiểm tra `id` có khớp, credential còn hiệu lực, quyền deploy và URL repository. Không giải quyết lỗi quyền bằng cách đưa password trực tiếp vào command line hoặc source control.

## 6. Gradle: `assemble`, `build` và publishing là các việc khác nhau

Gradle không dùng Maven lifecycle phases theo cùng cách. Với Java plugin, các task thường gặp:

| Task | Vai trò |
|---|---|
| `jar` | Tạo JAR của source set chính |
| `assemble` | Tạo các artifact của project |
| `check` | Chạy các verification task được gắn vào lifecycle |
| `build` | Tổng hợp verification và assembly |
| `publishToMavenLocal` | Publish publication đã cấu hình vào Maven local repository |
| `publish` | Tổng hợp các task publish tới repository đã khai báo |

### 6.1. `./gradlew jar` hoặc `assemble`: tạo artifact

```bash
./gradlew jar
```

Task `jar` tạo JAR trong thư mục `build/libs/`. `assemble` là task lifecycle để tạo các artifact của project, bao gồm JAR khi Java plugin được áp dụng.

```bash
./gradlew assemble
```

Các task này không tự động publish artifact lên Maven repository. File được tạo trong project output để kiểm tra, chạy thử hoặc được task khác sử dụng.

### 6.2. `./gradlew build`: verification cộng assembly

```bash
./gradlew build
```

Với Java plugin, `build` phụ thuộc vào `check` và `assemble`. Do đó, build thường chạy test/verification đã được nối vào `check` và tạo artifact qua `assemble`.

`build` không có nghĩa publish lên remote repository. Nếu muốn xuất bản, cần cấu hình publication và chạy task publish tương ứng.

## 7. Gradle `maven-publish`

Gradle cung cấp plugin `maven-publish` để định nghĩa publication Maven và gửi artifact tới Maven repository.

Ví dụ `build.gradle` dùng Groovy DSL:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '2.4.0'

publishing {
    publications {
        create('mavenJava', MavenPublication) {
            from components.java
            artifactId = 'order-domain'
        }
    }
}
```

`from components.java` tạo publication từ Java component, bao gồm artifact chính và metadata dependency phù hợp với component. `group`, `artifactId` và `version` tạo tọa độ publication.

Sau khi cấu hình, Gradle tạo task publication tương ứng. Có thể xem các task bằng:

```bash
./gradlew tasks --all
```

### 7.1. Publish vào Maven local

```bash
./gradlew publishToMavenLocal
```

Task này đưa các publication Maven đã cấu hình vào local Maven repository của người dùng, thường là `~/.m2/repository`.

Project khác có thể sử dụng artifact đó qua `mavenLocal()` trong repositories của nó:

```groovy
repositories {
    mavenLocal()
    mavenCentral()
}
```

Điểm cần phân biệt:

- `publishToMavenLocal` là thao tác **ghi publication vào local Maven repository**.
- `mavenLocal()` là khai báo **đọc dependency từ local Maven repository** khi Gradle phân giải dependency.

Hai cái phục vụ hai chiều khác nhau. `mavenLocal()` không publish artifact; `publishToMavenLocal` không tự làm project khác khai báo `mavenLocal()`.

### 7.2. Publish lên remote Maven repository

Thêm repository đích vào `publishing.repositories`:

```groovy
publishing {
    publications {
        create('mavenJava', MavenPublication) {
            from components.java
            artifactId = 'order-domain'
        }
    }

    repositories {
        maven {
            name = 'internalReleases'
            url = uri('https://repo.example.com/maven/releases')
            credentials {
                username = providers.environmentVariable('REPO_USERNAME').orNull
                password = providers.environmentVariable('REPO_PASSWORD').orNull
            }
        }
    }
}
```

URL và environment variable là ví dụ. Cần cấu hình credential theo repository manager và chính sách của tổ chức.

Task publish thường có tên dạng:

```text
publishMavenJavaPublicationToInternalReleasesRepository
```

Tên chính xác được sinh từ publication name và repository name. Có thể chạy:

```bash
./gradlew tasks --all
```

để xem task thực tế. Task tổng hợp `publish` chạy các publication task tới repository đã cấu hình.

```bash
./gradlew publish
```

Nếu chỉ muốn publish tới một repository hoặc publication cụ thể, gọi task tương ứng thay vì task tổng hợp.

### 7.3. `publishToMavenLocal` không cần khai báo remote repository

Gradle tạo task `publishToMavenLocal` từ publication đã cấu hình. Task này không cần một remote repository trong `publishing.repositories`. Nó dùng Maven local repository trên máy.

Ngược lại, task publish remote cần repository đích đã được khai báo. Nếu không có repository phù hợp, Gradle không có nơi để gửi artifact.

## 8. Metadata publication: POM và Gradle Module Metadata

Xuất bản một artifact Java thường không chỉ upload file JAR. Consumer còn cần metadata để biết tọa độ, version, dependency và các thông tin cần thiết để phân giải.

### 8.1. Maven POM

POM publication mô tả:

- `groupId`, `artifactId`, `version`.
- Packaging và metadata dự án.
- Dependency và scope.
- Thông tin license, developer, SCM nếu được cấu hình.
- Các thông tin khác phục vụ consumer và repository.

Ví dụ POM rút gọn:

```xml
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>order-domain</artifactId>
  <version>2.4.0</version>
  <packaging>jar</packaging>
</project>
```

Nếu chỉ copy JAR vào một thư mục mà không có metadata phù hợp, Maven/Gradle consumer có thể không phân giải dependency bắc cầu như mong muốn.

### 8.2. Gradle Module Metadata

Gradle có thể publish thêm file `.module` để mô tả variant, capability và dependency theo mô hình Gradle. POM là định dạng phổ biến cho Maven ecosystem, còn Gradle Module Metadata giữ được nhiều thông tin variant-aware hơn.

Khi dùng `maven-publish` với component, Gradle có thể xuất bản metadata tương ứng. Repository cần lưu các file metadata cùng artifact. Không nên xóa `.module` một cách tùy tiện nếu consumer Gradle dựa vào variant information.

### 8.3. Vì sao metadata quan trọng?

Một artifact có thể chạy được khi thêm JAR thủ công vào classpath nhưng consumer dependency resolution vẫn thất bại nếu:

- POM thiếu dependency bắc cầu.
- Scope được khai báo sai.
- Version hoặc artifactId không khớp tọa độ.
- Classifier/extension không đúng.
- Publication thiếu variant hoặc metadata cần thiết.
- Repository không lưu đủ các file publication.

Do đó, kiểm tra publication cần xác nhận cả JAR/WAR và metadata, không chỉ file binary.

## 9. Snapshot và release khi install/publish

Maven phân biệt version release và snapshot:

| Loại | Ví dụ | Đặc điểm |
|---|---|---|
| Release | `2.4.0` | Nên bất biến sau khi phát hành |
| Snapshot | `2.5.0-SNAPSHOT` | Có thể được cập nhật trong quá trình phát triển |

Khi `mvn deploy` với version kết thúc bằng `-SNAPSHOT`, Maven sử dụng `snapshotRepository` nếu được cấu hình. Với version release, Maven dùng `repository`.

Gradle `maven-publish` cũng publish version theo tọa độ đã cấu hình. Repository manager có thể áp dụng chính sách snapshot/release riêng.

Không nên ghi đè release version với nội dung mới. Nếu sửa code sau khi đã publish `2.4.0`, hãy phát hành version mới theo versioning policy. Nếu dùng snapshot trong quá trình phát triển, cần hiểu cache policy và metadata snapshot để tránh nhầm bản cũ với bản mới.

## 10. Local install hữu ích trong tình huống nào?

Local repository phù hợp cho vòng lặp phát triển trên một máy, đặc biệt khi hai project được phát triển độc lập nhưng có quan hệ dependency.

Ví dụ:

```text
workspace/
├── order-domain/
└── order-service/
```

Developer thay đổi `order-domain`, sau đó chạy:

```bash
cd order-domain
mvn install
```

Project `order-service` có thể khai báo:

```xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>order-domain</artifactId>
  <version>2.5.0-SNAPSHOT</version>
</dependency>
```

và phân giải bản đã cài vào local repository.

Với Gradle, có thể publish module library vào Maven local:

```bash
./gradlew publishToMavenLocal
```

Sau đó consumer Gradle khai báo `mavenLocal()`.

### 10.1. Hạn chế của local repository

- Chỉ có trên máy người đã cài/publish artifact.
- Máy CI hoặc developer khác không tự nhìn thấy artifact đó.
- Có thể chứa version cũ hoặc artifact được build từ source chưa commit.
- Khó truy vết nếu nhiều người cùng dùng version snapshot/local.
- Có thể làm kết quả build khác nhau giữa máy cá nhân và CI.

Không nên dùng local repository làm nơi phân phối chính thức cho cả nhóm. Khi artifact cần được chia sẻ, publish lên remote repository.

### 10.2. `mavenLocal()` có thể che artifact từ remote

Trong Gradle:

```groovy
repositories {
    mavenLocal()
    mavenCentral()
}
```

Gradle có thể tìm module trong Maven local repository. Nếu local repository có cùng tọa độ/version với artifact remote, developer có thể dùng bản local khác nội dung với bản trên server. Điều này tạo ra hiện tượng “máy tôi chạy được, CI không chạy được”.

Chỉ khai báo `mavenLocal()` khi cần thử nghiệm local. Với build CI/release, nên dùng repository dùng chung và version rõ ràng để kết quả nhất quán.

## 11. Publish artifact bên thứ ba vào local repository

Đôi khi cần dùng một JAR bên ngoài không có trong repository được cấu hình. Maven có thể cài file đó vào local repository bằng `install:install-file`:

```bash
mvn install:install-file \
  -Dfile=libs/vendor-sdk.jar \
  -DgroupId=com.vendor \
  -DartifactId=vendor-sdk \
  -Dversion=3.2.1 \
  -Dpackaging=jar
```

Lệnh này tạo entry local theo tọa độ đã khai báo. Nếu không cung cấp POM phù hợp, Maven không tự biết đầy đủ dependency bắc cầu của JAR. Cần xác định metadata/dependency rõ ràng.

Việc này chỉ giải quyết máy hiện tại. Nếu cả nhóm cần SDK, nên publish artifact và POM phù hợp lên remote repository nội bộ theo quy trình được kiểm soát.

Maven cũng có `deploy:deploy-file` để upload một artifact có sẵn lên remote repository, nhưng cần cấu hình repository và metadata chính xác. Không dùng nó để thay thế quy trình build/release có kiểm thử nếu artifact là sản phẩm của project.

## 12. Publish không đồng nghĩa deploy ứng dụng lên production

Trong Maven, `deploy` là phase upload artifact lên remote repository. Nó không có nghĩa triển khai ứng dụng đang chạy lên production server.

Trong Gradle, `publish` cũng có nghĩa gửi publication tới repository đã cấu hình, không phải deploy service lên Kubernetes hoặc restart server.

Các hoạt động cần phân biệt:

| Thuật ngữ | Ý nghĩa trong ngữ cảnh build |
|---|---|
| Package/assemble | Tạo JAR/WAR/distribution |
| Maven install | Cài artifact vào local Maven repository |
| Gradle `publishToMavenLocal` | Publish Maven publication vào local Maven repository |
| Maven deploy / Gradle publish | Upload package và metadata lên remote repository |
| Application deployment | Đưa artifact đã phát hành vào môi trường chạy ứng dụng |
| Gradle `installDist` | Tạo application distribution trong thư mục cài đặt cục bộ của build output; không phải publish Maven local |

Một pipeline có thể publish artifact trước, rồi một hệ thống deployment khác tải artifact từ repository và triển khai nó lên môi trường chạy.

## 13. Kiểm tra artifact sau mỗi bước

Sau khi package, kiểm tra file trong output directory:

```bash
jar tf target/order-domain-2.4.0.jar
```

Với Gradle:

```bash
jar tf build/libs/order-domain-2.4.0.jar
```

Sau khi install local, kiểm tra tọa độ trong Maven local repository:

```text
~/.m2/repository/com/example/order-domain/2.4.0/
```

Sau khi publish remote, tải artifact từ repository bằng tọa độ đã phát hành hoặc dùng dependency của một consumer sample project để xác nhận repository metadata hoạt động.

### 13.1. Kiểm tra checksum

Tính SHA-256 ở output build:

```bash
sha256sum target/order-domain-2.4.0.jar
```

Sau khi tải từ remote repository, tính lại checksum và so sánh. Nếu khác, dừng việc sử dụng artifact và điều tra đường truyền, repository hoặc quá trình publish.

Checksum xác nhận nội dung file không đổi so với giá trị đã lưu; nó không tự chứng minh danh tính người publish. Với release quan trọng, có thể kết hợp chữ ký, provenance và quyền publish được kiểm soát.

### 13.2. Consumer test

Một cách kiểm tra publication có giá trị là tạo một project consumer nhỏ, chỉ khai báo repository và dependency theo tọa độ đã publish. Sau đó compile/test một API đại diện.

Consumer test giúp phát hiện:

- POM/module metadata thiếu dependency.
- Artifact không có trong repository mong muốn.
- Version hoặc classifier sai.
- Repository permission không đủ.
- API compile/runtime không tương thích.

Đối với thư viện dùng chung, consumer test có thể chạy trong CI trước khi đánh dấu release hoàn tất.

## 14. Quy trình phát hành Maven mẫu

Một quy trình release cơ bản:

1. Checkout source revision/tag đã chọn.
2. Chọn JDK và Maven Wrapper version theo dự án.
3. Chạy test và verification.
4. Chạy `mvn clean verify` để tạo và xác minh artifact.
5. Kiểm tra JAR/WAR, POM, version và checksum.
6. Chỉ sau khi đạt quality gate, cấp quyền publish cho job release.
7. Chạy `mvn deploy` hoặc publish đúng artifact đã tạo theo cơ chế pipeline.
8. Tải thử artifact từ remote repository bằng một consumer hoặc bước xác minh.
9. Lưu release metadata, checksum, log và provenance.

Nếu pipeline tách job build và job publish, hãy chuyển artifact đã build qua CI artifact storage và publish chính file đó. Tránh checkout lại source rồi package một lần nữa trong job publish nếu mục tiêu là publish đúng artifact đã kiểm thử.

## 15. Quy trình phát hành Gradle mẫu

Với Gradle `maven-publish`:

1. Cấu hình publication từ component phù hợp.
2. Chạy `check` và `build` để verification/assembly hoàn tất.
3. Kiểm tra archive và metadata publication.
4. Publish local để thử nghiệm consumer nếu cần, hoặc publish tới repository thử nghiệm.
5. Kiểm tra artifact từ repository bằng consumer project.
6. Publish release tới repository chính thức sau khi approval.
7. Lưu version, checksum và provenance.

Các lệnh thường gặp:

```bash
# Tạo artifact và chạy verification
./gradlew clean build

# Thử publication vào Maven local
./gradlew publishToMavenLocal

# Publish tới repository remote đã cấu hình
./gradlew publish
```

Trong CI release, cần bảo đảm task publish dùng đúng publication đã được kiểm tra và credential chỉ có mặt ở job được phép publish.

## 16. Release repository và snapshot repository

Tổ chức thường tách hai loại repository:

```text
Repository manager
   |
   +--> snapshots
   |      2.5.0-SNAPSHOT
   |
   +--> releases
          2.4.0
          2.4.1
```

Snapshot repository phục vụ artifact đang phát triển, có thể được cập nhật theo chính sách. Release repository lưu version phát hành ổn định và nên từ chối ghi đè cùng tọa độ/version.

Việc tách repository giúp:

- Kiểm soát ai được publish snapshot và ai được publish release.
- Ngăn version release bị thay nội dung.
- Áp dụng retention cho snapshot.
- Hỗ trợ consumer chỉ dùng release trong production.
- Tách quy trình kiểm thử và quy trình phát hành chính thức.

Không nên publish artifact production từ một snapshot chưa được kiểm soát. Khi release, hãy dùng version bất biến và lưu đúng artifact đã xác minh.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Có JAR trong `target/` nhưng project khác không resolve được | Mới chạy `mvn package`, chưa install/publish | Dùng `mvn install` cho local hoặc `mvn deploy` cho remote |
| Developer dùng được dependency nhưng CI không tìm thấy | Artifact chỉ được cài trong `~/.m2/repository` của developer | Publish lên remote repository dùng chung |
| Gradle consumer không thấy module vừa build | Chưa publish hoặc consumer chưa khai báo `mavenLocal()`/remote repository phù hợp | Phân biệt task publish và repository dùng để đọc |
| `mvn deploy` trả 401/403 | Credential, server id hoặc quyền publish sai | So khớp `distributionManagement.id` với `settings.xml` server id |
| Gradle publish thất bại do authentication | Credential/provider hoặc quyền repository không đúng | Kiểm tra URL, credentials và quyền write |
| Dependency bắc cầu bị thiếu | POM/module metadata không đầy đủ | Kiểm tra publication component và metadata |
| Máy cá nhân dùng bản JAR khác CI | Local repository chứa artifact cũ cùng tọa độ | Kiểm tra local artifact và dùng repository chung/version mới |
| Release cùng version có nội dung khác | Repository cho phép ghi đè release | Bật immutability và phát hành version mới |
| Nhầm `installDist` với Maven install | Tên task giống từ “install” nhưng chức năng khác | `installDist` tạo application distribution; Maven `install` ghi local repository |
| Nhầm publish artifact với deploy ứng dụng | Hai bước có mục tiêu khác nhau | Tách package repository promotion khỏi deployment runtime |
| Có JAR nhưng consumer compile thất bại | Artifact/metadata/classifier hoặc API không phù hợp | Chạy consumer test và kiểm tra POM/module metadata |

## 18. Nguyên tắc cần ghi nhớ

- `package`/`assemble` tạo artifact trong output của project.
- Maven `install` ghi artifact và metadata vào local Maven repository.
- Maven `deploy` upload artifact và metadata lên remote repository.
- Gradle `assemble` tạo output; `build` tổng hợp verification và assembly.
- Gradle `publishToMavenLocal` ghi publication vào Maven local repository.
- Gradle `mavenLocal()` là repository declaration để đọc artifact từ local Maven repository.
- Gradle `publish` chạy các publication task tới remote repository đã cấu hình.
- Maven `<repositories>` dùng để đọc dependency; `<distributionManagement>` dùng để chỉ định đích publish.
- Maven server credential được ghép theo `id`; Gradle credential cần được cấp an toàn từ môi trường/secret store.
- Publication thường cần cả artifact binary và metadata như POM/Gradle Module Metadata.
- Local repository tiện cho thử nghiệm trên một máy nhưng không phải nguồn phân phối chính thức cho cả nhóm.
- Release version nên bất biến; dùng version mới khi nội dung thay đổi.
- Publish package lên repository khác với triển khai ứng dụng lên production.
- Kiểm tra artifact bằng consumer test, checksum và quyền truy cập sau khi publish.

Tạo artifact, đưa vào kho cục bộ và xuất bản từ xa là ba bước có mục đích khác nhau. Maven thể hiện rõ chúng qua `package`, `install` và `deploy`; Gradle phân tách `assemble`/`build`, `publishToMavenLocal` và các task `publish...Repository`. Hiểu đúng ranh giới này giúp chọn lệnh phù hợp cho phát triển local, chia sẻ nội bộ và phát hành chính thức, đồng thời tránh nhầm một file JAR vừa tạo với một package đã sẵn sàng cho consumer ở nơi khác.
