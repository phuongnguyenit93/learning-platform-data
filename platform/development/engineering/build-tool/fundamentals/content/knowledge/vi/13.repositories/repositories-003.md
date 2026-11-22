# Kho cục bộ, kho từ xa và bộ nhớ đệm của công cụ build

Một dự án Java thường sử dụng nhiều thư viện bên ngoài. Thay vì tải từng file JAR và chép vào thư mục dự án, build tool phân giải dependency từ các **repository** (kho lưu trữ). Repository có thể nằm trên máy lập trình viên, trên máy chủ của tổ chức hoặc trên một dịch vụ công khai như Maven Central.

Để build nhanh hơn và giảm việc tải lại cùng một dữ liệu, công cụ build còn sử dụng **cache** (bộ nhớ đệm). Cache có thể lưu metadata dependency, artifact đã tải, kết quả biến đổi artifact hoặc output của task build. Repository và cache đều có thể chứa file JAR, nhưng chúng có mục đích và vòng đời khác nhau.

Hiểu rõ sự khác biệt này giúp xử lý các tình huống thường gặp:

- Vì sao máy cá nhân build được khi mất mạng nhưng máy CI mới lại không build được?
- Vì sao đã publish một JAR mới nhưng Gradle vẫn sử dụng version cũ?
- Vì sao xóa thư mục `build/` không làm dependency được tải lại?
- Vì sao `mavenLocal()` có thể khiến máy lập trình viên dùng một JAR cũ khác với JAR trên repository chung?
- Khi nào nên dùng offline mode, refresh dependency hoặc xóa cache?
- Làm thế nào để kiểm soát nguồn tải dependency, credential và tính toàn vẹn của artifact?

## 1. Repository và cache là hai khái niệm khác nhau

**Repository** là nơi lưu trữ và phân phối module/artifact cùng metadata. Build tool truy cập repository để tìm dependency theo tọa độ hoặc tên module, version, variant và các thông tin liên quan.

**Cache** là vùng lưu trữ cục bộ để tái sử dụng dữ liệu đã phân giải hoặc kết quả build. Cache giảm thời gian truy cập mạng và tránh thực hiện lại những công việc không cần thiết.

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| Local repository | Kho artifact trên máy hoặc trong vùng lưu trữ cục bộ được công cụ quản lý | Maven `~/.m2/repository`; một Maven repository dạng file; `mavenLocal()` trong Gradle |
| Remote repository | Kho artifact được truy cập qua mạng hoặc dịch vụ repository | Maven Central, Nexus, Artifactory, GitHub Packages |
| Dependency cache | Lưu metadata và artifact đã phân giải để dùng lại | Gradle dependency cache; Maven local repository khi tải dependency từ remote |
| Build cache | Lưu output của task build để tái sử dụng khi input tương đương | Gradle local/remote build cache |
| Wrapper distribution cache | Lưu bản phân phối Gradle/Maven Wrapper đã tải | Gradle distributions trong Gradle User Home |

Một repository có thể là local hoặc remote theo vị trí truy cập. Một cache thường nằm trên máy đang chạy build và có thể bị xóa, làm mới hoặc tái tạo. Không nên xem cache là nguồn phát hành chính thức của thư viện.

## 2. Luồng phân giải dependency tổng quát

Khi build cần một dependency, công cụ build xác định module và version được yêu cầu, sau đó tìm metadata và artifact trong các nguồn đã cấu hình. Nếu dữ liệu đã có trong cache và còn hợp lệ theo chính sách cache, công cụ có thể dùng lại mà không cần tải lại.

Luồng khái quát:

```text
Build script / POM
       |
       v
Dependency request
       |
       v
Kiểm tra cache cục bộ
       |
       +---- Có dữ liệu hợp lệ ----> Dùng lại artifact/metadata
       |
       +---- Thiếu hoặc cần refresh
                     |
                     v
              Remote repository
                     |
                     v
             Tải metadata/artifact
                     |
                     v
               Lưu vào cache
                     |
                     v
               Tiếp tục build
```

Đây là mô hình khái quát. Quy tắc lựa chọn repository, metadata, version, variant và thời hạn cache cụ thể phụ thuộc Maven hoặc Gradle cũng như cấu hình của dự án.

## 3. Maven local repository

Maven dùng local repository để lưu artifact và metadata mà Maven đã tải hoặc cài đặt. Vị trí mặc định thường là:

```text
Linux/macOS: ~/.m2/repository
Windows:     %USERPROFILE%\.m2\repository
```

Đường dẫn có thể thay đổi qua cấu hình `<localRepository>` trong `settings.xml`.

Ví dụ cấu trúc repository:

```text
~/.m2/repository/
└── com/
    └── example/
        └── order-service/
            └── 2.4.0/
                ├── order-service-2.4.0.jar
                ├── order-service-2.4.0.pom
                └── order-service-2.4.0.jar.sha1
```

Các thành phần trong đường dẫn phản ánh `groupId`, `artifactId` và `version`. Repository có thể lưu thêm sources, Javadoc, checksum, metadata và những artifact classifier khác.

### 3.1. Maven tải dependency từ remote vào local repository

Khi POM khai báo:

```xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>order-service</artifactId>
  <version>2.4.0</version>
</dependency>
```

Maven tìm module trong local repository và các remote repository được cấu hình. Nếu artifact chưa có trong local repository, Maven có thể tải từ remote repository phù hợp rồi lưu vào local repository để lần sau dùng lại.

Vì vậy, local repository Maven vừa đóng vai trò kho cục bộ cho artifact đã cài đặt, vừa là nơi cache dependency đã tải từ xa.

### 3.2. Cài artifact của project vào local repository

Lệnh:

```bash
mvn install
```

thực hiện lifecycle tới phase `install`, trong đó artifact của project được cài vào local repository của người dùng. Project khác trên cùng máy có thể khai báo dependency tới tọa độ đó và sử dụng artifact đã cài.

Ví dụ module:

```xml
<groupId>com.example</groupId>
<artifactId>reporting-library</artifactId>
<version>1.0.0-SNAPSHOT</version>
```

Sau khi chạy `mvn install`, artifact có thể xuất hiện trong:

```text
~/.m2/repository/com/example/reporting-library/1.0.0-SNAPSHOT/
```

`install` chỉ cài vào local repository của môi trường hiện tại. Nó không publish lên server chung và không làm cho các máy khác tự nhìn thấy artifact.

### 3.3. Cài một file JAR bên ngoài vào local repository

Trong trường hợp cần đưa một JAR không có trong repository vào Maven local repository, có thể dùng `maven-install-plugin:install-file` với tọa độ phù hợp:

```bash
mvn install:install-file \
  -Dfile=libs/vendor-library.jar \
  -DgroupId=com.vendor \
  -DartifactId=vendor-library \
  -Dversion=3.2.1 \
  -Dpackaging=jar
```

Lệnh này tạo/cài metadata và artifact theo tọa độ đã cung cấp. Nếu không có POM gốc hoặc metadata dependency chính xác, Maven không thể tự suy ra toàn bộ dependency bắc cầu của JAR đó. Cần quản lý dependency bổ sung và nguồn gốc artifact một cách rõ ràng.

Không nên dùng local repository như một cách phân phối lâu dài cho cả nhóm. Nếu nhiều project hoặc nhiều máy cần artifact, hãy publish lên repository chung có quản lý version và quyền truy cập.

## 4. Maven remote repository

Remote repository là kho artifact được truy cập qua mạng, thường dùng giao thức HTTPS. Các nguồn phổ biến:

- Maven Central cho thư viện công khai.
- Repository nội bộ của tổ chức.
- Repository do Nexus hoặc Artifactory quản lý.
- Repository của nền tảng lưu trữ package.

Maven có thể lấy dependency từ nhiều remote repository. Project có thể khai báo repository trong POM; người dùng hoặc tổ chức cũng có thể cấu hình repository và mirror qua `settings.xml`.

### 4.1. Khai báo repository trong POM

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

`id` là định danh repository trong cấu hình Maven. `url` là địa chỉ kho. `releases` và `snapshots` cho phép cấu hình repository có phục vụ loại version tương ứng hay không.

Thông thường, repository release không nên cho phép snapshot. Tách kho release và snapshot giúp kiểm soát việc phát hành ổn định và artifact đang phát triển.

### 4.2. Repository cho Maven plugin

Maven có khái niệm `pluginRepositories` riêng để phân giải plugin build. Dependency của ứng dụng và plugin dùng các cấu hình repository tương ứng.

Ví dụ:

```xml
<pluginRepositories>
  <pluginRepository>
    <id>company-plugins</id>
    <url>https://repo.example.com/maven/plugins</url>
  </pluginRepository>
</pluginRepositories>
```

Không nên giả định một cấu hình repository dependency luôn thay thế mọi cấu hình plugin repository trong mọi trường hợp. Khi lỗi tải plugin Maven, hãy kiểm tra phần repository dành cho plugin và mirror trong `settings.xml`.

## 5. Maven `settings.xml`, mirror và credential

`settings.xml` chứa cấu hình theo người dùng hoặc môi trường Maven, chẳng hạn local repository, mirror, proxy, server credentials và profile. File thường nằm tại:

```text
~/.m2/settings.xml
```

Trên Windows:

```text
%USERPROFILE%\.m2\settings.xml
```

Có thể cấu hình mirror để chuyển mọi yêu cầu repository qua một repository manager nội bộ:

```xml
<settings>
  <mirrors>
    <mirror>
      <id>company-mirror</id>
      <mirrorOf>*</mirrorOf>
      <url>https://repo.example.com/maven/group</url>
    </mirror>
  </mirrors>
</settings>
```

`mirrorOf` xác định repository nào được thay thế bởi mirror. Giá trị `*` có nghĩa mirror áp dụng cho tất cả repository phù hợp. Tổ chức có thể dùng mirror để kiểm soát nguồn tải, cache dependency tập trung và áp dụng chính sách bảo mật.

### 5.1. Credential trong Maven settings

Credential nên được cấu hình trong `settings.xml` theo `id` khớp với repository hoặc mirror cần xác thực:

```xml
<settings>
  <servers>
    <server>
      <id>company-mirror</id>
      <username>${env.REPO_USERNAME}</username>
      <password>${env.REPO_PASSWORD}</password>
    </server>
  </servers>
</settings>
```

Ví dụ dùng environment variable để minh họa việc lấy credential từ môi trường. Cần bảo đảm biến môi trường được cấp an toàn và không in giá trị ra log. Maven hỗ trợ password encryption, nhưng cơ chế mã hóa Maven không thay thế một secret manager hoặc chính sách bảo vệ máy người dùng.

Không commit credential thật vào POM hoặc `settings.xml` được chia sẻ. Với CI, nên dùng secret store của nền tảng và tạo file settings tạm hoặc truyền cấu hình phù hợp trong job.

### 5.2. Proxy

Nếu môi trường cần proxy để truy cập repository, Maven có thể cấu hình proxy trong `settings.xml`:

```xml
<settings>
  <proxies>
    <proxy>
      <id>company-proxy</id>
      <active>true</active>
      <protocol>https</protocol>
      <host>proxy.example.com</host>
      <port>8443</port>
      <nonProxyHosts>localhost|127.0.0.1|*.example.internal</nonProxyHosts>
    </proxy>
  </proxies>
</settings>
```

Thông tin proxy ở ví dụ là placeholder. Nếu proxy yêu cầu xác thực, credential cũng phải được bảo vệ như các credential repository.

## 6. Gradle repositories

Gradle khai báo nơi tìm dependency trong `repositories {}` hoặc trong dependency resolution management ở `settings.gradle`.

Ví dụ trong `build.gradle`:

```groovy
repositories {
    mavenCentral()

    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.com/maven/releases')
    }
}
```

Gradle sẽ dùng các repository được cấu hình để phân giải module. Thứ tự khai báo có ý nghĩa: khi một module được tìm thấy trong repository, Gradle gắn kết việc phân giải module đó với repository tương ứng và tìm artifact của module từ cùng nguồn theo metadata. Không nên dựa vào việc Gradle sẽ lấy metadata từ một repository rồi tùy ý lấy JAR từ repository khác.

### 6.1. Khai báo repository tập trung trong settings

Với dự án nhiều project, có thể quản lý repository dependency tập trung ở `settings.gradle`:

```groovy
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        mavenCentral()
        maven {
            name = 'companyReleases'
            url = uri('https://repo.example.com/maven/releases')
        }
    }
}
```

`FAIL_ON_PROJECT_REPOS` yêu cầu project không tự khai báo repository riêng, giúp tổ chức kiểm soát nguồn dependency tập trung. Gradle còn có các chế độ repository management khác; chọn chế độ tùy chính sách của build.

`pluginManagement { repositories { ... } }` trong settings là cấu hình repository để phân giải Gradle plugins. Nó khác với `dependencyResolutionManagement` dành cho dependency của project. Khi plugin không tải được, cần kiểm tra `pluginManagement` thay vì chỉ xem `repositories` trong build script.

### 6.2. Dùng `mavenLocal()` trong Gradle

Gradle có thể đọc Maven local repository bằng:

```groovy
repositories {
    mavenLocal()
    mavenCentral()
}
```

`mavenLocal()` trỏ tới local Maven repository của người dùng, thường là `~/.m2/repository`. Đây là cách hữu ích khi phát triển hai project độc lập và muốn thử một thư viện vừa `mvn install` vào local repository.

Tuy nhiên, `mavenLocal()` có thể làm build phụ thuộc vào trạng thái riêng trên máy. Một artifact cũ đã được cài cục bộ có thể được chọn thay cho artifact mới trên repository chung, khiến kết quả build khác nhau giữa máy cá nhân và CI.

Chỉ nên dùng `mavenLocal()` khi có mục đích phát triển cụ thể. Với build CI và build cần tái lập, nên ưu tiên repository có version rõ ràng và nguồn phát hành dùng chung.

## 7. Gradle dependency cache

Gradle có dependency cache riêng, thường nằm dưới Gradle User Home:

```text
Linux/macOS: ~/.gradle/caches/
Windows:     %USERPROFILE%\.gradle\caches\
```

Một số dữ liệu liên quan đến dependency được lưu trong vùng như:

```text
~/.gradle/caches/modules-2/
```

Dependency cache có thể lưu:

- Metadata module và thông tin repository.
- Kết quả phân giải version.
- Artifact đã tải.
- Thông tin về dependency graph.
- Các dữ liệu cần thiết để tái sử dụng kết quả phân giải.

Đường dẫn và cấu trúc nội bộ có thể thay đổi theo phiên bản Gradle; không nên dựa vào tên thư mục nội bộ như một API ổn định.

### 7.1. Dependency cache không phải thư mục output của project

Gradle project thường có thư mục `.gradle/` riêng chứa trạng thái build của project, còn `build/` chứa output của các task. Gradle User Home chứa cache dùng chung giữa các build của cùng người dùng.

| Vị trí | Vai trò thường gặp |
|---|---|
| `<project>/.gradle/` | Trạng thái và dữ liệu build cục bộ của project |
| `<project>/build/` | Class file, resource, archive và output task |
| `GRADLE_USER_HOME/caches/` | Dependency cache, build cache cục bộ và dữ liệu cache khác |
| `GRADLE_USER_HOME/wrapper/dists/` | Gradle distributions đã tải qua Wrapper |

Xóa `build/` không đồng nghĩa xóa dependency cache. Chạy `clean` thường chỉ xóa output build của project, không xóa toàn bộ dependency đã tải.

### 7.2. Gradle dùng cache khi nào?

Khi một dependency đã được phân giải và artifact còn trong cache, Gradle có thể sử dụng lại mà không tải lại toàn bộ dữ liệu. Với version cố định và metadata còn hợp lệ, việc này giúp build nhanh hơn và có thể cho phép build offline.

Với dynamic version như `1.+`, hoặc changing module như snapshot/chưa ổn định, Gradle cần chính sách cache để xác định khi nào kiểm tra lại repository. Thời hạn cache mặc định có thể thay đổi theo loại dependency và cấu hình; không nên dựa vào cache để bảo đảm luôn nhận được bản mới nhất ngay lập tức.

## 8. Gradle dependency cache và Gradle build cache khác nhau

Hai loại cache này thường bị nhầm vì đều nằm trong Gradle User Home.

**Dependency cache** lưu thông tin phân giải dependency và artifact từ repository.

**Build cache** lưu output của task build có thể tái sử dụng dựa trên input và cache key.

| Đặc điểm | Dependency cache | Build cache |
|---|---|---|
| Lưu gì? | Metadata dependency và artifact đã tải | Output của task build có thể cache |
| Dùng để làm gì? | Tránh tải/phân giải dependency lặp lại | Tránh thực hiện lại task khi input tương đương |
| Nguồn dữ liệu | Repository và dependency resolution | Task output từ build trước hoặc remote build cache |
| Cấu hình thường gặp | `repositories`, dependency cache policy | `buildCache`, `outputs.cacheIf`, task input/output |
| Ví dụ | JAR của Jackson đã tải | Output của task compile hoặc code generation đủ điều kiện cache |

Một task có thể không cần chạy lại vì output còn up-to-date ngay trong project, hoặc output được khôi phục từ build cache. Điều đó khác với việc Gradle dùng JAR đã tải từ dependency cache.

Ví dụ bật build cache:

```bash
./gradlew build --build-cache
```

Build cache cần task có input/output được khai báo đúng và task có thể cache an toàn. Không phải mọi task đều có thể hoặc nên được cache, đặc biệt task có tác dụng phụ bên ngoài hoặc output phụ thuộc trạng thái không được khai báo.

## 9. Gradle Wrapper distribution cache

Gradle Wrapper tải bản phân phối Gradle được khai báo trong:

```text
gradle/wrapper/gradle-wrapper.properties
```

Ví dụ:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.5-bin.zip
```

Bản phân phối đã tải được lưu trong Gradle User Home, thường ở `wrapper/dists/`. Đây là cache của chính Gradle distribution, không phải dependency cache của project.

Nếu build mới chạy được trên máy cá nhân nhưng máy CI phải tải Gradle trước, có thể đơn giản là máy CI chưa có distribution trong cache. Khi mạng không có sẵn và distribution chưa được cache, Wrapper không thể tự tạo ra bản phân phối cần thiết.

## 10. Cache policy, dynamic version và changing module

### 10.1. Version cố định

Khai báo version cụ thể giúp dependency resolution ổn định hơn:

```groovy
dependencies {
    implementation 'com.example:reporting-library:1.4.2'
}
```

Với version cố định, build yêu cầu đúng version `1.4.2`. Nếu artifact trên repository bị thay thế bằng nội dung khác nhưng giữ nguyên version, đó là hành vi không tốt của repository và có thể làm build không tái lập. Release artifact nên được xem là bất biến.

### 10.2. Dynamic version

Ví dụ dynamic version trong Gradle:

```groovy
dependencies {
    implementation 'com.example:reporting-library:1.+'
}
```

Gradle cần tra metadata để chọn version phù hợp với dynamic selector. Kết quả có thể thay đổi theo thời gian khi repository xuất hiện version mới. Cache dynamic version giúp tránh truy vấn repository ở mọi lần build, nhưng cũng có nghĩa build có thể tiếp tục dùng kết quả cũ trong thời gian cache còn hiệu lực.

Với ứng dụng cần build tái lập, nên ưu tiên version cụ thể hoặc dùng dependency locking/constraints để kiểm soát kết quả.

### 10.3. Changing module và SNAPSHOT

Một changing module có thể được cập nhật nội dung trong khi version string không đổi. Ví dụ Maven `1.0-SNAPSHOT` thường trỏ tới snapshot build mới nhất của dòng version đó. Repository dùng metadata snapshot để ánh xạ version `1.0-SNAPSHOT` tới artifact timestamped cụ thể.

Gradle có thể đánh dấu dependency là changing:

```groovy
dependencies {
    implementation('com.example:reporting-library:1.0-SNAPSHOT') {
        changing = true
    }
}
```

Với changing module, Gradle áp dụng cache policy cho việc kiểm tra nội dung/metadata mới. Nếu cần cập nhật sớm, có thể dùng `--refresh-dependencies`, nhưng không nên biến mọi build thành việc tải lại mọi artifact.

Maven có chính sách update cho snapshot trong repository và local metadata. Có thể dùng `-U` để yêu cầu Maven kiểm tra snapshot cập nhật và một số artifact release còn thiếu theo quy tắc Maven:

```bash
mvn -U verify
```

### 10.4. Thời hạn cache của Gradle

Gradle có thời gian cache mặc định cho dynamic versions và changing modules; có thể điều chỉnh bằng `resolutionStrategy.cacheDynamicVersionsFor(...)` và `cacheChangingModulesFor(...)`.

Ví dụ:

```groovy
configurations.configureEach {
    resolutionStrategy {
        cacheDynamicVersionsFor 10, 'minutes'
        cacheChangingModulesFor 5, 'minutes'
    }
}
```

Ví dụ trên rút ngắn thời hạn cache để minh họa. Không nên đặt TTL quá thấp nếu không có nhu cầu, vì build sẽ truy cập repository thường xuyên hơn. Với dependency release bất biến, dùng version cố định vẫn là lựa chọn dễ kiểm soát hơn dynamic version.

## 11. Offline mode

Offline mode yêu cầu build tool không truy cập repository mạng và chỉ dùng dữ liệu đã có sẵn ở local/cache.

### 11.1. Gradle offline

```bash
./gradlew build --offline
```

Nếu tất cả dependency cần thiết đã có trong Gradle dependency cache và các task không cần tài nguyên mạng khác, build có thể hoàn tất. Nếu thiếu một artifact hoặc metadata cần thiết, Gradle báo lỗi vì không thể tải thêm.

Offline mode không có nghĩa mọi task đều không sử dụng mạng. Một custom task có thể tự gọi HTTP client hoặc chạy lệnh tải file. `--offline` điều khiển dependency resolution của Gradle; nó không tự chặn mọi kết nối mạng do logic tùy chỉnh thực hiện.

### 11.2. Maven offline

```bash
mvn -o verify
```

Maven chỉ dùng các artifact/plugin có sẵn trong local repository. Nếu một plugin hoặc dependency chưa được tải, build sẽ thất bại.

### 11.3. Khi nào dùng offline mode?

Offline mode hữu ích khi:

- Làm việc trên máy bay hoặc môi trường mạng bị giới hạn.
- Xác nhận một build có thể tái sử dụng cache đã chuẩn bị.
- CI có bước tải dependency riêng và bước build sau cần chạy không truy cập mạng.
- Điều tra một lỗi phụ thuộc vào repository từ xa.

Không nên dùng offline mode như giải pháp mặc định để che lỗi repository. Nếu build thất bại vì thiếu artifact, cần chuẩn bị cache hoặc cấu hình repository phù hợp.

## 12. Làm mới dependency cache

### 12.1. Gradle `--refresh-dependencies`

Khi nghi ngờ metadata hoặc artifact đã cache không còn phù hợp, có thể chạy:

```bash
./gradlew build --refresh-dependencies
```

Tùy chọn này yêu cầu Gradle làm mới trạng thái phân giải dependency. Nó không có nghĩa mọi JAR sẽ luôn bị tải lại từ đầu; Gradle có thể kiểm tra metadata/checksum và tái sử dụng artifact nếu nội dung không thay đổi.

Đây là lựa chọn đầu tiên khi cần kiểm tra cập nhật dependency mà không muốn xóa toàn bộ Gradle User Home.

### 12.2. Maven `-U`

Với Maven:

```bash
mvn -U verify
```

`-U` yêu cầu kiểm tra cập nhật snapshot và các release bị thiếu theo quy tắc của Maven. Nó không phải lệnh xóa toàn bộ local repository.

### 12.3. Xóa cache khi nào?

Chỉ cân nhắc xóa cache khi có bằng chứng cache bị hỏng, dữ liệu không nhất quán hoặc cách làm mới thông thường không giải quyết được. Xóa cache có thể khiến lần build sau tải lại rất nhiều artifact, làm mất dữ liệu dùng chung của các project khác và tăng thời gian build.

Với Maven, local repository thường chứa cả artifact do người dùng `install` và dependency đã tải. Xóa toàn bộ `~/.m2/repository` có thể làm mất các module nội bộ chưa publish lên remote.

Với Gradle, xóa toàn bộ `~/.gradle/caches` có thể làm mất dependency cache và build cache. Nên đóng Gradle daemon/build trước khi thực hiện thao tác quản trị cache và chỉ xóa vùng thực sự cần thiết.

## 13. Repository order và nguồn dependency

Khi một build khai báo nhiều repository, thứ tự và phạm vi repository có thể ảnh hưởng kết quả phân giải.

Ví dụ Gradle:

```groovy
repositories {
    maven {
        name = 'company'
        url = uri('https://repo.example.com/maven')
    }
    mavenCentral()
}
```

Nếu một module được tìm thấy trong repository đầu tiên, Gradle gắn việc phân giải module đó với repository này. Không nên trông đợi Gradle lấy metadata từ repository công ty nhưng lấy artifact từ Maven Central khi repository đầu tiên thiếu file. Repository manager nội bộ nên proxy hoặc lưu đầy đủ artifact mà nó công bố.

Với Maven, thứ tự repository và mirror cũng ảnh hưởng nơi tìm artifact. Trong tổ chức, thường nên cấu hình một mirror/group repository tập trung để kiểm soát nguồn tải thay vì để từng project tự thêm nhiều nguồn không đồng nhất.

### 13.1. Giới hạn nội dung repository trong Gradle

Gradle cho phép giới hạn group hoặc module được tìm trong repository cụ thể:

```groovy
repositories {
    maven {
        name = 'companyInternal'
        url = uri('https://repo.example.com/maven')
        content {
            includeGroupByRegex 'com\\.example(\\..*)?'
        }
    }

    mavenCentral()
}
```

Ví dụ này giới hạn repository nội bộ cho group `com.example` và các group con theo regex. Điều này giúp tránh việc một repository không đáng tin cậy cung cấp một module trùng tọa độ với module nội bộ.

Với module quan trọng, có thể dùng exclusive content để chỉ định repository duy nhất được phép cung cấp group/module đó. Cấu hình cụ thể cần được thiết kế nhất quán ở cấp settings/project theo chính sách repository của build.

### 13.2. Repository nội bộ như proxy/cache tập trung

Repository manager như Nexus hoặc Artifactory có thể hoạt động như một nhóm repository:

```text
Gradle/Maven build
       |
       v
Company repository manager
       |
       +---- Local hosted releases
       |
       +---- Local hosted snapshots
       |
       +---- Proxy Maven Central
       |
       +---- Proxy external repositories
```

Lợi ích:

- Kiểm soát nguồn dependency mà build được phép sử dụng.
- Cache artifact bên ngoài để giảm tải mạng và tăng tốc build.
- Lưu trữ release nội bộ ở một địa chỉ dùng chung.
- Quản lý quyền publish và quyền download.
- Áp dụng chính sách quét lỗ hổng, giấy phép và retention.
- Giảm phụ thuộc vào trạng thái local repository của từng máy.

## 14. Release và Snapshot repository

Một tổ chức thường tách artifact phát hành ổn định và artifact đang phát triển.

| Loại | Đặc điểm | Ví dụ version |
|---|---|---|
| Release | Artifact được xem là bất biến sau khi phát hành | `1.4.2`, `2.0.0` |
| Snapshot | Artifact có thể được cập nhật trong cùng dòng version phát triển | `1.5.0-SNAPSHOT` |

Maven thường phân biệt snapshot và release trong repository policy. Snapshot metadata có thể ánh xạ version base như `1.5.0-SNAPSHOT` sang một artifact timestamped cụ thể. Điều này cho phép nhiều lần publish snapshot mà không phải tạo version release mới cho mỗi lần thử nghiệm.

Release repository nên từ chối ghi đè artifact cùng tọa độ/version. Nếu nội dung thay đổi nhưng version không đổi, cache và consumer có thể giữ nội dung cũ, dẫn tới build không tái lập.

Gradle cũng hỗ trợ changing module và có cache policy tương ứng. Tuy nhiên, không nên dùng version thay đổi nội dung liên tục cho dependency production. Version cố định cùng quy trình release bất biến giúp xác định chính xác đầu vào build.

## 15. Dependency locking và verification

Repository và cache giúp tải, lưu và tái sử dụng dependency. Nhưng để build đáng tin cậy, cần kiểm soát version và nội dung artifact.

### 15.1. Dependency locking

Dependency locking ghi lại version đã được chọn cho một số configuration. Khi version selector có thể thay đổi, lock state giúp những lần build sau dùng cùng kết quả resolution cho đến khi lock được cập nhật có chủ đích.

Trong Gradle, có thể bật locking cho các configuration:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Sau đó chạy task phù hợp với phiên bản Gradle để ghi lock state, ví dụ:

```bash
./gradlew dependencies --write-locks
```

Locking quản lý version được chọn; nó không tự bảo đảm nội dung file trên repository không bị thay thế. Vì vậy, có thể kết hợp dependency locking với dependency verification.

### 15.2. Dependency verification

Gradle dependency verification cho phép kiểm tra checksum hoặc chữ ký của artifact đã phân giải. File cấu hình thường là:

```text
gradle/verification-metadata.xml
```

Có thể khởi tạo metadata verification bằng task:

```bash
./gradlew --write-verification-metadata sha256 help
```

Lệnh trên có thể ghi checksum cho các dependency được quan sát trong lần chạy. Cần review metadata trước khi commit và bảo đảm nguồn tin cậy được xác minh. Không nên tự động chấp nhận checksum mới khi đang điều tra một thay đổi không rõ nguồn gốc.

Maven cũng hỗ trợ checksum ở repository và có các plugin/cơ chế kiểm soát dependency, nhưng mức độ xác minh phụ thuộc cấu hình và công cụ được sử dụng. Không nên giả định checksum tải cùng từ một server luôn đủ để xác minh nguồn gốc độc lập; với yêu cầu bảo mật cao, cần quy trình trust/signature phù hợp.

## 16. Credential và bảo mật repository

Khi truy cập repository riêng, build có thể cần username/password hoặc token. Credential nên được cung cấp từ môi trường hoặc secret manager, không đặt trực tiếp trong build script được commit.

Ví dụ Gradle:

```groovy
repositories {
    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.com/maven/releases')

        credentials {
            username = providers.environmentVariable('REPO_USERNAME').orNull
            password = providers.environmentVariable('REPO_PASSWORD').orNull
        }
    }
}
```

Trong project thực tế, cần cấu hình credential theo API/provider phù hợp với phiên bản Gradle và tránh truy cập secret trong configuration phase nếu không cần. Gradle có thể yêu cầu credential khi repository cần xác thực; không in giá trị ra console.

Một số nguyên tắc bảo mật:

- Chỉ dùng HTTPS cho repository từ xa khi có thể.
- Cấp quyền read và publish riêng biệt.
- Dùng token có phạm vi tối thiểu và thời hạn phù hợp.
- Không commit token, mật khẩu hoặc private key.
- Không cho phép repository không đáng tin cậy cung cấp module nội bộ cùng tọa độ.
- Bật dependency verification khi dự án cần kiểm soát tính toàn vẹn artifact.
- Review thay đổi repository declaration như một thay đổi bảo mật của build.

## 17. Kiểm tra dependency được lấy từ đâu

### 17.1. Maven dependency tree

```bash
mvn dependency:tree
```

Lệnh này hiển thị dependency graph và giúp xác định dependency nào kéo một thư viện vào. Có thể lọc theo dependency cụ thể bằng tùy chọn plugin tương ứng.

Để kiểm tra effective settings hoặc cấu hình Maven, có thể dùng các goal help phù hợp; cần cẩn thận vì output có thể chứa thông tin môi trường nhạy cảm.

### 17.2. Gradle dependencies

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Lệnh này hiển thị dependency graph của configuration `runtimeClasspath`.

Để tìm lý do một module/version được chọn:

```bash
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

`dependencyInsight` giúp xem đường dependency và lý do resolution chọn version. Khi điều tra nguồn repository, có thể bật log phù hợp để quan sát việc tải artifact và kiểm tra cấu hình repository.

### 17.3. Kiểm tra local cache và artifact

Với Maven, có thể tìm artifact trong `~/.m2/repository` hoặc vị trí local repository đã cấu hình.

Với Gradle, dependency cache có cấu trúc nội bộ phức tạp hơn. Không nên chỉnh sửa hoặc di chuyển file trong cache bằng tay. Dùng lệnh Gradle để refresh hoặc cấu hình cache thay vì thao tác trực tiếp vào các file nội bộ.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `Could not resolve` hoặc không tìm thấy dependency | Repository sai URL, thiếu credential, version không tồn tại hoặc mạng/proxy lỗi | Kiểm tra repository declaration, settings, credential và kết nối |
| Máy cá nhân build được, CI thất bại | Dependency chỉ có trong local cache/local Maven repository của máy cá nhân | Publish artifact lên repository chung hoặc chuẩn bị cache CI |
| Maven dùng JAR cũ trong local repository | Artifact release bị ghi đè hoặc local artifact cũ được cài trước đó | Dùng version mới, kiểm tra nguồn artifact và tránh ghi đè release |
| Gradle không nhận snapshot mới | Changing module metadata còn trong cache | Kiểm tra `changing`, cache TTL và thử `--refresh-dependencies` |
| Offline build thất bại | Cache chưa có một dependency/plugin/metadata cần thiết | Chạy online để chuẩn bị cache hoặc cấu hình repository phù hợp |
| Xóa `build/` nhưng dependency vẫn còn | `clean` không xóa dependency cache | Phân biệt project output với Gradle/Maven dependency cache |
| Dùng `mavenLocal()` tạo kết quả khác CI | Local repository có artifact khác với repository chung | Chỉ dùng khi cần, kiểm tra tọa độ/version và ưu tiên repository chung |
| Maven không tải được plugin | Plugin repository hoặc mirror chưa được cấu hình đúng | Kiểm tra `pluginRepositories` và `settings.xml` mirror |
| Gradle lấy module từ repository không mong muốn | Thứ tự repository hoặc content filter chưa phù hợp | Kiểm tra repository order, content filtering và metadata |
| Lỗi 401/403 | Credential sai hoặc thiếu quyền | Kiểm tra token, server id/repository name và quyền truy cập |
| Checksum verification thất bại | Artifact khác checksum đã tin cậy hoặc metadata verification sai | Xác minh nguồn và nội dung trước khi cập nhật checksum |
| Build cache không tái sử dụng output | Task không cacheable, input/output không đầy đủ hoặc cache key khác | Kiểm tra task annotations, inputs, outputs và cấu hình build cache |

## 19. Quy trình xử lý sự cố repository/cache

Khi build không tải được hoặc dùng nhầm dependency, có thể lần theo thứ tự:

1. **Xác định dependency request:** group/module, artifact, version, classifier và configuration cần dùng.
2. **Xác định repository đã cấu hình:** Maven POM/settings/mirror hoặc Gradle settings/build repositories.
3. **Kiểm tra credential và mạng:** HTTPS, proxy, token, quyền đọc và certificate.
4. **Kiểm tra local state:** Maven local repository hoặc Gradle dependency cache có artifact/metadata hay không.
5. **Kiểm tra version policy:** release, snapshot, dynamic version, changing module và cache TTL.
6. **Thử refresh có mục tiêu:** Maven `-U` hoặc Gradle `--refresh-dependencies` khi cần kiểm tra cập nhật.
7. **Thử offline để xác định phụ thuộc mạng:** nếu cache thiếu, build sẽ chỉ ra artifact chưa có sẵn.
8. **Kiểm tra dependency graph:** xác định module nào kéo dependency và version nào được chọn.
9. **Kiểm tra integrity:** checksum, signature hoặc dependency verification khi có cấu hình.
10. **Chỉ xóa cache khi có bằng chứng cần thiết:** ưu tiên làm mới có mục tiêu thay vì xóa toàn bộ vùng lưu trữ.

## 20. Nguyên tắc tổ chức repository cho nhóm phát triển

Một quy trình build ổn định thường có những đặc điểm:

- Dependency release được publish lên repository dùng chung, không phụ thuộc vào `mvn install` trên máy một cá nhân.
- Repository công khai và nội bộ được quản lý rõ ràng; module nội bộ không bị lấy nhầm từ nguồn không tin cậy.
- Snapshot và release được tách theo chính sách của tổ chức.
- Credential được cấp qua secret store hoặc cấu hình cá nhân an toàn.
- CI có thể dùng cache để tăng tốc nhưng vẫn có khả năng tạo build từ cache sạch.
- Version dependency được kiểm soát bằng version cố định, constraints hoặc dependency locking.
- Artifact được xác minh bằng checksum/signature khi yêu cầu bảo mật cần thiết.
- Cache có thể xóa và tái tạo mà không làm mất nguồn phát hành chính thức.

## 21. Tổng kết

Repository là nguồn lưu trữ và phân phối module/artifact; cache là nơi lưu dữ liệu đã phân giải hoặc output build để tái sử dụng. Maven local repository thường vừa chứa dependency tải về vừa chứa artifact do `mvn install` cài vào. Maven remote repository phân phối artifact qua mạng và có thể được điều khiển bằng POM, `settings.xml`, mirror, proxy và credential.

Gradle khai báo repository trong build/settings, còn dependency cache nằm trong Gradle User Home. `mavenLocal()` cho phép Gradle đọc local Maven repository nhưng có thể làm build phụ thuộc trạng thái riêng của máy. Gradle dependency cache khác Gradle build cache: một bên lưu metadata/artifact dependency, bên kia lưu output của task.

Offline mode chỉ hoạt động khi dữ liệu cần thiết đã có trong cache. `--refresh-dependencies` và Maven `-U` giúp kiểm tra cập nhật mà không cần xóa toàn bộ cache. Với build tái lập và an toàn, hãy dùng version rõ ràng, repository được kiểm soát, credential bảo mật, dependency locking và verification phù hợp.
