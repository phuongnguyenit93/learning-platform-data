# Module artifact trong Java: build, publish và tiêu thụ

## Mục tiêu

Sau bài này, bạn có thể giải thích module artifact; phân biệt build module với module của Java Platform Module System (JPMS); hiểu artifact coordinates và repository layout; tạo artifact riêng cho từng module trong Maven multi-module và Gradle multi-project build; quản lý dependency giữa module; phân biệt build output, local install và remote publication; publish JAR, POM, sources, Javadoc và metadata; quản lý release/SNAPSHOT; kiểm tra artifact trước khi phát hành; và xử lý lỗi khi module không tạo, không publish hoặc consumer không resolve được artifact.

## 1. Module artifact là gì?

Trong Java project chia thành nhiều module, mỗi module có trách nhiệm riêng và có thể tạo ra một hoặc nhiều **artifact** để module khác hoặc ứng dụng bên ngoài sử dụng.

Ví dụ:

~~~text
shop-platform/
├── domain/
├── persistence/
└── application/
~~~

- `domain` chứa model và business rule.
- `persistence` triển khai truy cập dữ liệu và phụ thuộc `domain`.
- `application` ghép các thành phần thành ứng dụng và phụ thuộc `domain`, `persistence`.

Sau khi build, mỗi module có thể tạo artifact:

~~~text
domain-1.0.0.jar
persistence-1.0.0.jar
application-1.0.0.jar
~~~

Artifact có thể là JAR, WAR, EAR, ZIP, POM hoặc file theo định dạng riêng. Một module dạng aggregator có thể chỉ tạo POM, không tạo JAR.

Trong phạm vi **quản lý artifact**, module artifact là output có thể định danh và phân phối được của một module trong build. Artifact được lưu trong repository để consumer khai báo dependency bằng tọa độ ổn định.

### Một module có thể tạo nhiều artifact

Một Java library module có thể tạo:

- Main JAR chứa class và resource production.
- Sources JAR để IDE và developer xem source.
- Javadoc JAR để tra cứu API.
- Test JAR hoặc test fixtures nếu dự án chủ động xuất bản test utility.
- Artifact phụ có classifier hoặc extension riêng.
- POM và metadata mô tả dependency/publication.
- SBOM, checksum, signature và provenance đi kèm release.

Một artifact không nhất thiết là JAR. Module frontend có thể tạo ZIP static assets; module triển khai có thể tạo WAR; module native có thể tạo binary theo OS/architecture.

## 2. Phân biệt build module và Java module (JPMS)

Từ “module” có hai nghĩa phổ biến trong hệ sinh thái Java. Cần phân biệt để tránh cấu hình nhầm.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Build module | Một project/subproject được Maven hoặc Gradle build riêng trong cùng build | Maven module `domain`, Gradle project `:domain` |
| JPMS module | Một đơn vị module của Java Platform Module System, có module descriptor và quy tắc phụ thuộc/đóng gói | `com.example.domain` |
| Artifact | File output được định danh và phân phối | `com.example:domain:1.0.0` |
| Repository | Nơi lưu artifact và metadata để consumer tải | Maven repository nội bộ |

Một Gradle subproject hoặc Maven module có thể tạo JAR không có `module-info.class`. Khi đó nó vẫn là module của build và vẫn có artifact hợp lệ.

Ngược lại, một JPMS module có thể được đóng gói thành modular JAR. Module name trong JPMS không phải Maven `artifactId`, cũng không nhất thiết bằng tên Gradle project.

Ví dụ:

- Maven coordinates: `com.acme.platform:domain:1.0.0`.
- JPMS module name: `com.acme.platform.domain`.
- File: `domain-1.0.0.jar`.

Ba giá trị này liên quan về naming convention nhưng có mục đích khác nhau.

## 3. Artifact coordinates định danh module output

Artifact không chỉ là file có tên tùy ý. Build repository sử dụng tọa độ để xác định artifact và phiên bản.

Với Maven, các trường thường gặp là:

| Trường | Vai trò |
|---|---|
| `groupId` | Nhóm/tổ chức sở hữu artifact |
| `artifactId` | Tên artifact/module |
| `version` | Phiên bản |
| `classifier` | Phân biệt artifact phụ cùng tọa độ cơ bản |
| `extension` | Phần mở rộng file, thường là `jar`, `pom`, `zip` |

Ba trường `groupId:artifactId:version` thường được gọi là GAV. Khi mô tả đầy đủ artifact, xét thêm classifier và extension (GAVCE).

Ví dụ:

~~~text
groupId    = com.acme.platform
artifactId = domain
version    = 1.0.0
classifier = sources
extension  = jar
~~~

Tọa độ main artifact:

~~~text
com.acme.platform:domain:1.0.0
~~~

Artifact sources cùng phiên bản có tọa độ đầy đủ:

~~~text
com.acme.platform:domain:1.0.0:jar:sources
~~~

Classifier là trường tùy chọn. Nó hữu ích khi một module publish nhiều file cùng version, chẳng hạn `sources`, `javadoc` hoặc `tests`.

Không dùng classifier để che giấu các phiên bản API không tương thích. Nếu hai artifact là hai dòng phát triển hoặc contract khác nhau, hãy thiết kế `artifactId`/version rõ ràng.

### Maven repository layout

Với:

~~~text
groupId    = com.acme.platform
artifactId = domain
version    = 1.0.0
~~~

Maven repository thường lưu:

~~~text
com/
└── acme/
    └── platform/
        └── domain/
            └── 1.0.0/
                ├── domain-1.0.0.jar
                ├── domain-1.0.0.pom
                ├── domain-1.0.0-sources.jar
                └── domain-1.0.0-javadoc.jar
~~~

Mỗi artifact có thể có checksum/signature và repository metadata riêng. POM mô tả identity và dependency metadata của project.

Tọa độ GAV được hiểu trong phạm vi repository. Hai repository khác nhau có thể chứa cùng GAV nhưng bytes không giống nhau. Đây là lý do cần repository policy, checksum verification và release immutability.

## 4. Artifact lifecycle: tạo, cài local và publish remote

Một module artifact thường đi qua các giai đoạn:

~~~text
Source của module
       |
       v
Compile + test
       |
       v
Package artifact
       |
       v
Local build output
       |
       +----> Consume trực tiếp trong cùng build
       |
       +----> Install vào local repository
       |
       +----> Publish lên remote repository
                    |
                    v
              Consumer resolve
                    |
                    v
              Compile / run
~~~

Ba thao tác thường bị nhầm:

| Thao tác | Nơi lưu | Mục đích |
|---|---|---|
| Build/package | Thư mục output của module | Tạo file để kiểm tra hoặc dùng trong build hiện tại |
| Install | Local repository của developer/agent | Cho build khác trên cùng máy resolve artifact |
| Publish/deploy | Remote repository | Chia sẻ artifact cho team, CI hoặc consumer |

Ví dụ Maven:

- `mvn package` tạo artifact trong thư mục `target`.
- `mvn install` cài artifact và POM vào local repository, thường là `~/.m2/repository`.
- `mvn deploy` đưa artifact, POM và attached artifacts lên remote repository đã cấu hình.

Ví dụ Gradle:

- `./gradlew :domain:jar` tạo JAR trong output của project.
- `./gradlew :domain:publishToMavenLocal` publish publication vào local Maven repository.
- `./gradlew :domain:publish` thực thi các task publish tới remote repository đã cấu hình.

Local repository không phải nơi phát hành chính thức. Một build chạy thành công nhờ artifact cũ trong local repository chưa chứng minh module hiện tại tạo ra artifact đúng. Khi điều tra lỗi, hãy phân biệt artifact mới vừa build với artifact cũ đã được install trước đó.

## 5. Maven multi-module project tạo artifact như thế nào?

Maven hỗ trợ gom nhiều project vào một build bằng parent/aggregator POM. Cơ chế điều phối này gọi là **Maven Reactor**.

Reactor:

1. Thu thập các module được khai báo.
2. Xác định quan hệ phụ thuộc.
3. Sắp xếp module theo thứ tự build hợp lệ.
4. Chạy lifecycle/goal cho các module được chọn.

Nếu `application` phụ thuộc `domain`, Reactor build `domain` trước khi cần nó cho `application`.

### Aggregation và inheritance

Hai chức năng này thường được đặt trong cùng root POM nhưng có ý nghĩa khác nhau:

- **Aggregation:** `<modules>` gom các project để Maven Reactor build cùng một lần.
- **Inheritance:** `<parent>` cho phép child POM kế thừa properties, dependency management, plugin management và cấu hình chung.

Một POM có thể vừa là aggregator vừa là parent, nhưng đây không phải cùng một cơ chế. Child có thể kế thừa parent mà không được aggregator build; aggregator cũng có thể gom module không kế thừa trực tiếp từ nó.

Chỉ dependency thực tế trong module mới tạo quan hệ dependency để Reactor sắp xếp. Việc khai báo một tọa độ trong `dependencyManagement` hoặc `pluginManagement` không tự tạo dependency/order.

### Cấu trúc project

~~~text
shop-platform/
├── pom.xml
├── domain/
│   ├── pom.xml
│   └── src/main/java/
└── application/
    ├── pom.xml
    └── src/main/java/
~~~

### Parent/aggregator POM

File root `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.platform</groupId>
    <artifactId>shop-platform</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>domain</module>
        <module>application</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.acme.platform</groupId>
                <artifactId>domain</artifactId>
                <version>1.0.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
~~~

`packaging` là `pom` vì root POM dùng để quản lý/aggregate các module. Nó không tự tạo `shop-platform-1.0.0.jar`.

`<modules>` khai báo các thư mục module. `dependencyManagement` quản lý version của dependency, nhưng không tự làm module trở thành dependency; module consumer vẫn phải khai báo dependency thực tế.

### Domain module POM

File `domain/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme.platform</groupId>
        <artifactId>shop-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>domain</artifactId>
    <packaging>jar</packaging>
</project>
~~~

Maven kế thừa `groupId`, version và properties từ parent. Module này có packaging `jar`, nên lifecycle tạo `domain-1.0.0.jar`.

### Application module POM

File `application/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme.platform</groupId>
        <artifactId>shop-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>application</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>domain</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Version dependency `domain` được lấy từ `dependencyManagement` của parent. Đây là dependency thực tế nên Reactor có thể sắp xếp `domain` trước `application`.

### Chạy Maven Reactor

Từ thư mục root:

~~~bash
./mvnw clean verify
~~~

Maven build các module được khai báo theo dependency order. Khi build thành công, kiểm tra:

~~~text
domain/target/domain-1.0.0.jar
application/target/application-1.0.0.jar
~~~

Chỉ build module `application` và các module mà nó cần:

~~~bash
./mvnw -pl application -am verify
~~~

`-pl` chọn project; `-am` (also make) yêu cầu build thêm dependency module trong Reactor.

Chọn module theo artifactId:

~~~bash
./mvnw -pl :domain package
~~~

Nếu module được chọn phụ thuộc module khác trong reactor, dùng `-am` để build các dependency module cần thiết.

Các tùy chọn khác:

- `-amd`: build module được chọn và các module phụ thuộc vào nó.
- `-rf`: tiếp tục Reactor từ module chỉ định sau khi đã xử lý lỗi.
- `-fae`: tiếp tục các module khác rồi báo lỗi tổng hợp ở cuối.
- `-N`: không đệ quy xuống module con.

Thứ tự `<modules>` trong POM được dùng khi không có quan hệ phụ thuộc cụ thể quyết định thứ tự khác. Không nên dựa vào thứ tự khai báo để che giấu dependency bị thiếu.

## 6. Maven install và deploy từng module

### Install vào local repository

Chạy ở root:

~~~bash
./mvnw clean install
~~~

Maven chạy lifecycle đến `install` cho từng module. Artifact và POM được cài vào local repository để build khác trên cùng máy sử dụng.

Đường dẫn ví dụ:

~~~text
~/.m2/repository/com/acme/platform/domain/1.0.0/
~~~

Install hữu ích khi kiểm tra consumer project riêng biệt hoặc khi project không được build cùng một Reactor. Trong multi-module build thông thường, Reactor có thể kết nối module dependency trực tiếp mà không cần install trước.

### Deploy lên remote repository

POM hoặc parent POM có thể khai báo:

~~~xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.com/releases</url>
    </repository>

    <snapshotRepository>
        <id>internal-snapshots</id>
        <url>https://repo.example.com/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

`id` phải khớp với server entry trong Maven `settings.xml`. Credential nên được cấp từ secret store của CI hoặc cơ chế bảo mật tương ứng, không hardcode password trong POM hoặc commit vào repository.

Publish:

~~~bash
./mvnw clean deploy
~~~

Maven deploy plugin triển khai artifact, POM và attached artifacts. Trong multi-module build, mỗi module có thể deploy publication của mình theo lifecycle.

### Chỉ deploy một module

~~~bash
./mvnw -pl domain -am deploy
~~~

Lệnh này chọn `domain` cùng các module mà nó phụ thuộc. Không thêm `-am` nếu đã xác định module không có dependency module nào cần build trong reactor.

### Release và SNAPSHOT

Maven thường phân biệt:

- Release version: ví dụ `1.0.0`.
- Snapshot version: ví dụ `1.1.0-SNAPSHOT`.

Snapshot thể hiện bản phát triển có thể được cập nhật trước release. Repository Maven có thể lưu snapshot bằng timestamped version và metadata trỏ tới snapshot hiện hành.

Release artifact nên được xem là immutable: không ghi đè cùng tọa độ release bằng bytes khác. Nếu nội dung thay đổi, phát hành version mới. Chính sách này giúp consumer và cache không resolve cùng GAV nhưng nhận nội dung khác nhau.

## 7. Gradle multi-project build tạo artifact như thế nào?

Gradle dùng root project và subprojects được khai báo trong `settings.gradle` hoặc `settings.gradle.kts`.

### Cấu trúc project

~~~text
shop-platform/
├── settings.gradle
├── build.gradle
├── domain/
│   └── build.gradle
└── application/
    └── build.gradle
~~~

### Khai báo subprojects

File `settings.gradle`:

~~~groovy
rootProject.name = 'shop-platform'

include 'domain', 'application'
~~~

Gradle project path của hai module là `:domain` và `:application`.

### Domain module

File `domain/build.gradle`:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.acme.platform'
version = '1.0.0'

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }

    repositories {
        maven {
            name = 'localBuildRepo'
            url = layout.buildDirectory.dir('repo')
        }
    }
}
~~~

Java Library plugin tạo Java component. `withSourcesJar()` và `withJavadocJar()` yêu cầu tạo artifact phụ cho source và Javadoc.

Maven Publish plugin dùng component để xác định artifact và dependency metadata cần publish. Repository file-based ở ví dụ chỉ phục vụ minh họa; production thường dùng repository HTTPS nội bộ hoặc repository manager.

### Application module

File `application/build.gradle`:

~~~groovy
plugins {
    id 'application'
}

group = 'com.acme.platform'
version = '1.0.0'

dependencies {
    implementation project(':domain')
}
~~~

`project(':domain')` là project dependency. Gradle biết `application` cần output của `domain`, nên tạo task dependency và đưa output/transitive dependency phù hợp vào classpath.

Đây là dependency giữa subprojects trong cùng build. Nó không phải Maven coordinate đã publish.

### Build module artifact

Build JAR của domain:

~~~bash
./gradlew :domain:jar
~~~

Artifact mặc định:

~~~text
domain/build/libs/domain-1.0.0.jar
~~~

Chạy build toàn bộ project:

~~~bash
./gradlew build
~~~

Liệt kê project:

~~~bash
./gradlew projects
~~~

Xem task module:

~~~bash
./gradlew :domain:tasks --all
~~~

Tên task đầy đủ gồm project path và task name. Ví dụ `:domain:jar` chỉ rõ module cần build, giúp tránh nhầm với `jar` task của module khác.

## 8. Publish module bằng Gradle Maven Publish Plugin

Gradle có thể publish một Java component thành Maven publication.

Trong ví dụ `domain/build.gradle`, publication tên `mavenJava` và repository tên `localBuildRepo`. Gradle tạo task publish theo tên publication/repository:

~~~bash
./gradlew :domain:generatePomFileForMavenJavaPublication
./gradlew :domain:publishMavenJavaPublicationToLocalBuildRepoRepository
~~~

Publish tất cả publication được cấu hình trong project:

~~~bash
./gradlew :domain:publish
~~~

Publish vào local Maven repository:

~~~bash
./gradlew :domain:publishToMavenLocal
~~~

`publishToMavenLocal` đưa artifact và metadata vào local Maven cache. Nó không phải remote release.

### Publication identity

Gradle `MavenPublication` có các trường identity:

- `groupId`
- `artifactId`
- `version`

Theo mặc định, chúng được lấy từ `project.group`, `project.name` và `project.version`. Có thể override riêng trong publication khi naming policy cần khác tên project.

Ví dụ:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            groupId = 'com.acme.platform'
            artifactId = 'domain'
            version = '1.0.0'
        }
    }
}
~~~

Hãy đảm bảo dependency declaration của consumer khớp với tọa độ publication thực tế. Đổi tên project hoặc override artifactId có thể làm tọa độ publish khác với tên thư mục.

### Publish lên remote repository

Có thể thay file repository bằng repository HTTPS:

~~~groovy
publishing {
    repositories {
        maven {
            name = 'internalReleases'
            url = uri('https://repo.example.com/releases')
            credentials(PasswordCredentials)
        }
    }
}
~~~

Gradle có thể lấy credential từ Gradle properties hoặc environment theo cơ chế bảo mật của pipeline. Không commit username/password thật vào build script. Cần cấu hình credential tương ứng trước khi gọi task publish remote.

Task publish cụ thể:

~~~bash
./gradlew :domain:publishMavenJavaPublicationToInternalReleasesRepository
~~~

Tên task được tạo từ publication name và repository name. Dùng `./gradlew :domain:tasks --all` để xác nhận tên task thực tế sau khi cấu hình.

## 9. Project dependency và published artifact dependency

Có hai cách để một module sử dụng code của module khác.

### Project dependency trong cùng Gradle build

~~~groovy
dependencies {
    implementation project(':domain')
}
~~~

Gradle biết project producer, task graph và variant. Nó có thể dùng output của project dependency mà không cần publish JAR lên repository trước.

### External module dependency

Khi artifact đã được publish:

~~~groovy
dependencies {
    implementation 'com.acme.platform:domain:1.0.0'
}
~~~

Consumer resolve tọa độ từ repository được cấu hình.

### Maven dependency trong cùng Reactor

~~~xml
<dependency>
    <groupId>com.acme.platform</groupId>
    <artifactId>domain</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Nếu `domain` và `application` cùng nằm trong Maven Reactor và dependency được khai báo đúng, Maven build dependency module trước. Nếu build riêng consumer ngoài Reactor, dependency phải có sẵn trong local hoặc remote repository.

### So sánh

| Tiêu chí | Project dependency | Published artifact dependency |
|---|---|---|
| Phạm vi | Cùng build | Có thể khác repository/build |
| Định danh | Project path | Artifact coordinates |
| Build order | Build tool tự lập task graph/reactor | Consumer resolve artifact đã có |
| Metadata | Build model/variant trong build | POM và/hoặc Gradle Module Metadata |
| Phù hợp | Module phát triển cùng nhau | Module chia sẻ giữa nhiều project/team |

Không cần publish mỗi lần muốn test module dependency trong cùng một Gradle build hoặc Maven Reactor. Publish cần thiết khi muốn consumer bên ngoài build lấy artifact thông qua repository.

## 10. Dependency giữa các module và API boundary

Một module artifact nên thể hiện đúng API mà consumer được phép dùng.

Với Gradle Java Library plugin:

- `api` khai báo dependency cần thiết trên compile classpath của consumer vì public API của module expose type từ dependency đó.
- `implementation` giữ dependency nội bộ ở implementation/runtime side khi consumer không cần dependency đó để compile public API.

Ví dụ:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:public-contract:2.0.0'
    implementation 'org.example:internal-engine:3.1.0'
}
~~~

Dùng `api` quá rộng làm dependency graph của consumer lớn hơn và có thể khiến thay đổi implementation ảnh hưởng nhiều module. Dùng `implementation` khi dependency chỉ phục vụ nội bộ module.

Maven dùng dependency scope như `compile`, `provided`, `runtime`, `test` và `system` để mô tả cách dependency được sử dụng/truyền qua POM. Maven không có cặp `api`/`implementation` giống Gradle Java Library plugin; khi publish, POM thể hiện dependency và scope theo mô hình Maven.

### Tránh dependency cycle

Nếu `domain` phụ thuộc `application` trong khi `application` cũng phụ thuộc `domain`, build graph có vòng lặp hoặc kiến trúc module bị đảo chiều.

Cách xử lý:

1. Đưa contract dùng chung vào module nhỏ hơn.
2. Để implementation phụ thuộc contract.
3. Tránh để module thấp tầng phụ thuộc module orchestration.
4. Kiểm tra dependency graph thay vì chỉ dựa vào thứ tự thư mục.
5. Tách module khi có ranh giới trách nhiệm ổn định.

## 11. POM, Gradle Module Metadata và publication metadata

Artifact JAR chứa class/resource. Consumer còn cần metadata để biết cách resolve artifact và dependency của nó.

### Maven POM

POM publication có thể mô tả:

- groupId, artifactId, version.
- Packaging/type.
- Dependencies và scope.
- Parent/BOM hoặc dependency management theo cấu hình.
- Name, description, URL, licenses, developers và SCM metadata.
- Relocation khi tọa độ thay đổi.

Nếu chỉ upload một file JAR mà không có POM phù hợp, Maven consumer có thể thiếu dependency metadata và không biết thư viện cần thêm artifact nào.

### Gradle Module Metadata

Gradle có thể publish file `.module` bên cạnh Maven POM. Metadata này mô tả variant/capability/attributes của component chi tiết hơn Maven POM.

Ví dụ, cùng một component có thể có:

- API variant.
- Runtime variant.
- Sources variant.
- Javadoc variant.
- Variant theo platform/attribute.

Gradle consumer có thể sử dụng metadata để chọn variant phù hợp. Maven consumer chủ yếu dựa vào POM và artifact convention.

### Metadata phải khớp artifact

Nếu POM khai báo dependency version sai, hoặc Gradle metadata trỏ tới artifact/variant không tồn tại, file JAR có thể tải được nhưng consumer vẫn fail khi resolve hoặc runtime.

Sau khi publish, hãy kiểm tra POM và `.module` được tạo, identity/version đúng, dependency list đúng và artifact URL thực sự tải được.

## 12. Main artifact, attached artifact và classifier

Một module thường có một main artifact và có thể có artifact phụ.

Ví dụ:

~~~text
domain-1.0.0.jar
domain-1.0.0.pom
domain-1.0.0-sources.jar
domain-1.0.0-javadoc.jar
domain-1.0.0-tests.jar
~~~

Ý nghĩa:

| Artifact | Mục đích |
|---|---|
| Main JAR | Class/resource production |
| POM | Metadata cho Maven dependency resolution |
| Sources JAR | Source để IDE/developer tra cứu |
| Javadoc JAR | API documentation |
| Tests JAR | Test utility nếu module chủ động export |
| SBOM | Danh sách component/dependency |
| Signature/checksum | Kiểm tra integrity/authenticity |

Maven có thể attach artifact phụ với classifier. Ví dụ sources và Javadoc plugin thường tạo artifact classifier tương ứng.

Gradle Java plugin hỗ trợ `withSourcesJar()` và `withJavadocJar()`. Khi publication lấy từ `components.java`, các artifact này có thể được đưa vào publication theo cấu hình plugin.

Không publish test output hoặc nội dung nội bộ không dành cho consumer chỉ vì file đã được tạo trong build directory. Chọn publication rõ ràng và review nội dung trước khi phát hành.

## 13. Versioning và tương thích giữa module artifacts

Module version là một phần của contract với consumer.

Ví dụ:

~~~text
com.acme.platform:domain:1.0.0
com.acme.platform:persistence:1.0.0
com.acme.platform:application:1.0.0
~~~

Một multi-module release có thể dùng cùng version để thể hiện các module được phát hành đồng bộ. Cũng có thể version độc lập nếu module có vòng đời release riêng.

### SemVer và API compatibility

Với Semantic Versioning:

- MAJOR: thay đổi không tương thích API.
- MINOR: bổ sung chức năng tương thích ngược.
- PATCH: sửa lỗi tương thích ngược.

Đây là policy versioning, không phải hành vi tự động của Maven/Gradle. Build tool không tự kiểm tra rằng module thực sự tuân theo SemVer.

Nếu `application` yêu cầu `domain` version cụ thể, hãy quản lý dependency version tập trung bằng Maven BOM/parent hoặc Gradle version catalog/platform khi phù hợp.

### Release đồng bộ

Dùng một version chung khi:

- Các module luôn phát hành cùng nhau.
- API nội bộ thay đổi đồng bộ.
- Consumer cần một bộ module đã được kiểm tra tương thích.

### Release độc lập

Dùng version độc lập khi:

- Module có consumer và lịch phát hành riêng.
- API boundary ổn định.
- Thay đổi một module không bắt buộc release module khác.
- Team có quy trình compatibility test rõ ràng.

Không version độc lập chỉ để giảm số lần build nếu dependency compatibility chưa được kiểm soát.

## 14. SNAPSHOT và release repository

Snapshot phù hợp cho quá trình tích hợp phát triển. Release repository dành cho version đã phát hành.

Một policy thường dùng:

| Loại | Ví dụ | Policy |
|---|---|---|
| Snapshot | `1.2.0-SNAPSHOT` | Có thể cập nhật trong quá trình phát triển |
| Release | `1.2.0` | Immutable, không ghi đè |
| Candidate | `1.2.0-rc.1` | Pre-release theo policy của team |

Maven `distributionManagement` có thể khai báo repository riêng cho release và snapshot. Gradle publishing cũng có thể khai báo repository đích tương ứng.

Không để release version trỏ tới artifact thay đổi theo thời gian. Nếu cần sửa một artifact đã phát hành, tạo version mới và cập nhật consumer.

### Snapshot cache và stale artifact

Consumer có thể cache snapshot metadata hoặc artifact. Nếu snapshot được cập nhật nhưng consumer vẫn dùng bản cache cũ, kết quả có thể khác kỳ vọng.

Khi debug, kiểm tra:

- Snapshot metadata trong repository.
- Local repository cache.
- Thời điểm artifact publish.
- Dependency refresh policy.
- Build có resolve đúng repository không.

Gradle có thể refresh dependency:

~~~bash
./gradlew --refresh-dependencies
~~~

Maven có thể cập nhật snapshot theo update policy hoặc dùng tùy chọn cập nhật tương ứng. Chỉ xóa cache khi đã hiểu nguyên nhân; tránh dùng local cache làm bằng chứng release artifact đúng.

## 15. Publish và resolve artifact trong CI/CD

Một pipeline module release thường có các bước:

1. Checkout source revision đã xác định.
2. Build và test các module cần phát hành.
3. Xác minh dependency và version.
4. Tạo main artifact và attached artifacts.
5. Kiểm tra POM/Gradle metadata.
6. Tính checksum và ký artifact nếu policy yêu cầu.
7. Publish lên staging/release repository.
8. Kiểm tra artifact có thể resolve từ repository đích.
9. Promote hoặc release theo quy trình của repository.
10. Lưu manifest, SBOM và provenance.

### Không publish khi build/test thất bại

Publish task phải phụ thuộc vào các quality gate bắt buộc. Với Maven, gọi lifecycle phù hợp tới `deploy` sau khi tests và verification pass. Với Gradle, publish pipeline cần phụ thuộc vào build/verification tasks theo policy project.

Không chạy publish task độc lập nếu nó không đảm bảo build/test đã được thực thi. Một task publish có thể chỉ upload output hiện có.

### Staging trước release

Nếu repository hỗ trợ staging:

- Publish vào staging repository.
- Resolve artifact từ staging bằng một consumer test.
- Xác minh tọa độ, POM, checksums và signatures.
- Promote staging sang release khi validation pass.

Staging giảm nguy cơ đưa artifact sai lên repository release bất biến.

### Credential

- Dùng secret store của CI.
- Cấp quyền deploy tối thiểu cần thiết.
- Tách read credential và publish credential.
- Không log token/password.
- Không commit `settings.xml` có secret hoặc Gradle properties chứa credential.
- Rotate credential theo policy.

## 16. Kiểm tra artifact sau khi tạo

Đừng chỉ tin exit code của build. Xác minh file thực tế.

### Kiểm tra file và kích thước

Linux/macOS:

~~~bash
find domain/target -maxdepth 1 -type f -print
ls -lh domain/target/domain-1.0.0.jar
~~~

Gradle:

~~~bash
find domain/build/libs -maxdepth 1 -type f -print
ls -lh domain/build/libs/domain-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem domain\target -File
Get-Item domain\target\domain-1.0.0.jar | Select-Object Name, Length
~~~

### Liệt kê nội dung JAR

~~~bash
jar --list --file domain-1.0.0.jar
~~~

Kiểm tra:

- Package/class dự kiến có mặt.
- Resource cần thiết có mặt.
- Không có file local, secret hoặc test-only output ngoài ý muốn.
- Manifest có metadata đúng.
- Module descriptor có mặt nếu dự án dùng JPMS.

### Kiểm tra manifest

~~~bash
unzip -p domain-1.0.0.jar META-INF/MANIFEST.MF
~~~

Nếu không có `unzip`, có thể dùng `jar --extract` trong thư mục tạm rồi đọc file manifest.

### Tính checksum

Linux:

~~~bash
sha256sum domain-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash domain-1.0.0.jar -Algorithm SHA256
~~~

Checksum dùng để đối chiếu bytes. Nó không tự chứng minh nguồn phát hành đáng tin; cần signature hoặc provenance theo yêu cầu bảo mật.

## 17. Kiểm tra module artifact với consumer độc lập

Một artifact chỉ có giá trị khi consumer có thể resolve và sử dụng nó.

Tạo một consumer project tối giản, cấu hình đúng repository và dependency coordinate, rồi chạy:

~~~bash
./mvnw clean verify
~~~

hoặc:

~~~bash
./gradlew clean test
~~~

Consumer test nên xác minh:

- Artifact resolve từ repository đích.
- POM/Gradle metadata được tải.
- Dependency bắc cầu đầy đủ.
- Public class/API có thể compile.
- Runtime classpath có đủ dependency.
- Version được chọn đúng.
- Không phụ thuộc vào file trong workspace producer.
- Không vô tình lấy artifact cũ từ local cache.

Để kiểm tra remote publication, dùng clean workspace hoặc repository cache mới. Nếu consumer chỉ pass sau khi producer đã chạy `install` trên cùng máy, có thể consumer đang lấy artifact từ local repository thay vì remote repository.

## 18. JPMS modular JAR là một trường hợp đặc biệt

Java Platform Module System (JPMS) được giới thiệu trong Java 9. Một modular JAR chứa module descriptor đã biên dịch thành `module-info.class`.

Source descriptor:

~~~java
module com.acme.platform.domain {
    exports com.acme.platform.domain;
}
~~~

File source thường nằm ở:

~~~text
src/main/java/module-info.java
~~~

Khi compile, descriptor trở thành:

~~~text
module-info.class
~~~

Trong JAR modular, `module-info.class` nằm ở root của archive (hoặc vị trí version-specific đối với multi-release JAR).

### Descriptor điều khiển điều gì?

| Directive | Ý nghĩa |
|---|---|
| `requires` | Module này cần module khác |
| `exports` | Package được công khai cho module khác |
| `opens` | Package được mở cho reflection |
| `uses` | Module sử dụng service |
| `provides ... with ...` | Module cung cấp implementation cho service |

Ví dụ:

~~~java
module com.acme.platform.application {
    requires com.acme.platform.domain;
}
~~~

Module descriptor định nghĩa quan hệ module ở runtime/compiler. Maven coordinates vẫn dùng để tìm file artifact trong repository. JPMS module name được dùng trên module path để resolve module graph.

### JAR không có module-info

Một JAR không có module descriptor vẫn có thể được đặt trên module path như automatic module. Tên module có thể lấy từ manifest attribute `Automatic-Module-Name` hoặc được suy ra từ tên JAR.

Đối với library công khai, khai báo `Automatic-Module-Name` ổn định có thể giúp consumer JPMS dùng tên module nhất quán trước khi project chuyển sang modular JAR thật.

Không nên dựa lâu dài vào tên tự suy ra từ filename vì đổi tên artifact có thể làm module name thay đổi.

### Classpath và module path

- Classpath dùng mô hình class loading truyền thống.
- Module path cho phép JVM resolve module descriptor, đọc `requires` và áp dụng encapsulation.
- Một modular JAR đặt trên classpath được xử lý như JAR không modular.

Đừng nhầm “module artifact” với “JAR có module-info”. Một build module có thể publish non-modular JAR; JPMS module có thể được đóng gói trong artifact JAR và publish theo GAV bình thường.

### Kiểm tra module descriptor

~~~bash
jar --describe-module --file domain-1.0.0.jar
~~~

Lệnh này hiển thị tên module và descriptor mà JDK nhận diện. Nếu JAR không có descriptor, output có thể mô tả automatic module.

Có thể kiểm tra module dependency bằng `jdeps`:

~~~bash
jdeps --check com.acme.platform.domain --module-path libs
~~~

Thay tên module và module path bằng dữ liệu thật của project. `jdeps` hỗ trợ phân tích dependency ở cấp class/module; nó không thay thế test tích hợp.

## 19. Multi-release JAR và artifact theo platform

Một module đôi khi cần phân phối code khác nhau theo Java runtime version hoặc OS/architecture.

### Multi-release JAR

Multi-release JAR chứa base classes và các implementation thay thế theo Java release trong thư mục:

~~~text
META-INF/versions/9/
META-INF/versions/17/
~~~

Manifest phải có attribute:

~~~text
Multi-Release: true
~~~

Một file JAR duy nhất có thể cung cấp class phù hợp với runtime version. Đây là nhiều implementation bên trong một artifact, không phải nhiều Maven/Gradle build module.

### Artifact theo platform

Một library có native component có thể publish artifact riêng theo classifier hoặc tọa độ khác:

~~~text
native-engine-1.0.0-linux-x86_64.jar
native-engine-1.0.0-windows-x86_64.jar
native-engine-1.0.0-macos-aarch64.jar
~~~

Chọn convention nhất quán để consumer biết platform nào cần resolve. Với Gradle, variant attributes có thể mô hình hóa lựa chọn platform rõ hơn classifier đơn thuần.

Không dùng một classifier tùy ý nếu metadata không mô tả được cách consumer chọn đúng artifact. Cần test trên từng OS/architecture được hỗ trợ.

## 20. Quản lý thay đổi tọa độ artifact

Sau khi publish, tọa độ artifact trở thành contract với consumer. Đổi `groupId` hoặc `artifactId` có thể làm dependency cũ không resolve được.

Khi đổi tọa độ:

1. Chọn tọa độ mới và version policy.
2. Publish artifact mới.
3. Nếu dùng Maven repository, cân nhắc relocation POM tại tọa độ cũ.
4. Cập nhật consumer.
5. Ghi migration note và thời hạn hỗ trợ tọa độ cũ.
6. Không xóa artifact cũ nếu còn consumer cần resolve.

Maven relocation cho phép POM ở tọa độ cũ chỉ ra tọa độ mới. Nó giúp repository browser/build tool thông báo người dùng rằng artifact đã chuyển.

Không đổi artifactId chỉ để đổi tên thư mục nếu không có kế hoạch migration consumer.

## 21. Artifact integrity và supply-chain metadata

Artifact được chia sẻ qua repository cần có cơ chế xác minh phù hợp.

Các loại bằng chứng:

| Bằng chứng | Mục đích |
|---|---|
| SHA-256/SHA-512 | Phát hiện bytes bị thay đổi |
| Signature | Xác minh artifact được ký bởi key được tin cậy |
| POM/Gradle metadata | Mô tả identity, dependencies và variants |
| SBOM | Liệt kê component/dependency có trong artifact |
| Provenance/attestation | Ghi nhận source, workflow và môi trường tạo artifact |

Checksum được publish cùng artifact có thể giúp phát hiện hỏng file trong quá trình tải. Để xác minh nguồn phát hành, consumer cần checksum/signature lấy từ nguồn tin cậy.

Nếu ký artifact, quản lý private key trong CI secret/HSM hoặc signing service. Không đặt private key trong repository hoặc build output.

Không chỉnh sửa artifact sau khi đã ký hoặc publish. Nếu cần thay đổi bytes, phát hành version mới và tạo lại checksum/signature/attestation.

## 22. Lỗi thường gặp và cách xử lý

### Module build thành công nhưng không thấy JAR

**Nguyên nhân:** module dùng packaging `pom`, chưa chạy package phase, hoặc task tạo artifact chưa được gọi.

**Cách xử lý:** kiểm tra packaging, build task và output directory. Với Maven dùng `package`; với Gradle chạy `:module:jar` hoặc task tương ứng.

### Maven báo không tìm thấy dependency module cùng repository

**Nguyên nhân:** module không được khai báo trong Reactor, dependency tọa độ sai hoặc build consumer riêng khi artifact chưa được install/publish.

**Cách xử lý:** kiểm tra root `<modules>`, dependency GAV, Reactor order; chạy từ root hoặc `-pl ... -am`; nếu consumer độc lập, install/publish artifact trước.

### Maven Reactor build sai thứ tự hoặc module không được build

**Nguyên nhân:** dependency giữa module chưa khai báo thực tế; chỉ có entry trong `dependencyManagement` hoặc `pluginManagement`.

**Cách xử lý:** khai báo dependency/plugin/extension thực tế ở module cần dùng; xem Reactor summary và lệnh `-pl`, `-am`.

### Gradle báo project path không tồn tại

**Nguyên nhân:** thiếu `include` trong settings, sai tên project hoặc sai project path.

**Cách xử lý:** chạy `./gradlew projects`; kiểm tra `settings.gradle(.kts)`; dùng path đầy đủ như `:domain`.

### Gradle consumer lấy sai output module

**Nguyên nhân:** dùng file dependency tự tạo hoặc task-to-task dependency thay vì project dependency/variant model.

**Cách xử lý:** dùng `implementation project(':domain')` hoặc outgoing artifact/variant phù hợp; tránh hardcode path vào `build/libs`.

### Artifact local khác artifact remote

**Nguyên nhân:** local repository giữ artifact cũ, publish nhầm version/repository hoặc artifact bị ghi đè.

**Cách xử lý:** so sánh SHA-256, tọa độ, repository URL và metadata; dùng clean consumer workspace; áp dụng immutable release policy.

### Consumer resolve được JAR nhưng thiếu dependency

**Nguyên nhân:** POM không có dependency, Gradle publication lấy sai component hoặc artifact được upload thủ công mà thiếu metadata.

**Cách xử lý:** xem effective POM/Gradle Module Metadata; kiểm tra dependency tree; publish từ component đúng và kiểm thử bằng consumer độc lập.

### Sources/Javadoc JAR không xuất hiện

**Nguyên nhân:** chưa cấu hình source/Javadoc task hoặc publication không attach artifact phụ.

**Cách xử lý:** Maven cấu hình Sources/Javadoc Plugin; Gradle dùng `withSourcesJar()` và `withJavadocJar()`; kiểm tra danh sách file publication trước khi publish.

### Publish task không tìm thấy

**Nguyên nhân:** chưa apply Maven Publish Plugin, chưa khai báo publication/repository hoặc tên task khác.

**Cách xử lý:** kiểm tra plugin và `publishing` block; chạy `./gradlew :module:tasks --all`; dùng task name được Gradle tạo.

### Maven deploy bị 401/403

**Nguyên nhân:** server id không khớp, credential sai/hết hạn hoặc account thiếu quyền deploy.

**Cách xử lý:** đối chiếu `distributionManagement` id với `settings.xml`; cấp credential từ secret store; kiểm tra quyền repository và URL. Không đưa password vào POM.

### Release version đã tồn tại

**Nguyên nhân:** repository không cho ghi đè release hoặc pipeline đang cố publish lại cùng GAV.

**Cách xử lý:** xác minh artifact đã phát hành; nếu bytes đúng, không cần publish lại; nếu cần sửa, tăng version và phát hành bản mới.

### Snapshot resolve phiên bản cũ

**Nguyên nhân:** local cache hoặc snapshot metadata chưa được refresh.

**Cách xử lý:** kiểm tra metadata và repository đích; refresh dependency; xác nhận publish hoàn tất trước khi consumer resolve.

### JPMS báo module not found

**Nguyên nhân:** JAR không nằm trên module path, module name khác dự kiến, thiếu `module-info.class` hoặc dependency module chưa có.

**Cách xử lý:** dùng `jar --describe-module`; kiểm tra `module-info.java`; xác nhận module path và `requires` name.

### JPMS báo package không được export/open

**Nguyên nhân:** module descriptor không export package cho consumer hoặc framework cần reflection nhưng package chưa được opens phù hợp.

**Cách xử lý:** chỉ export API công khai; khai báo opens có giới hạn khi thật sự cần reflection; không mở toàn bộ module tùy tiện.

### Artifact theo platform được chọn sai

**Nguyên nhân:** classifier/variant không khớp OS/architecture hoặc metadata không khai báo điều kiện chọn.

**Cách xử lý:** kiểm tra classifier/variant attributes và platform detection; test resolve trên từng platform hỗ trợ.

## 23. Quy trình quản lý module artifact

### Khi phát triển module

1. Xác định trách nhiệm và public API của module.
2. Đặt group/artifact/version convention.
3. Khai báo dependency theo đúng ranh giới module.
4. Build và test module độc lập.
5. Kiểm tra JAR contents, manifest và metadata.
6. Kiểm tra dependency transitives và API exposure.
7. Nếu dùng JPMS, kiểm tra module descriptor riêng.

### Khi phát hành

1. Chốt version release.
2. Chạy build/test từ checkout sạch.
3. Tạo main artifact và artifact phụ cần thiết.
4. Kiểm tra POM/Gradle Module Metadata.
5. Tính checksum và ký artifact theo policy.
6. Publish lên staging/release repository.
7. Dùng consumer project độc lập để resolve và test.
8. Promote release và lưu provenance/SBOM.
9. Không ghi đè release coordinates đã phát hành.

### Khi consumer gặp lỗi

1. Xác nhận tọa độ dependency.
2. Xác nhận repository URL và credentials/read permission.
3. Kiểm tra POM/Gradle metadata.
4. Xem dependency graph và variant selection.
5. Kiểm tra version/cache.
6. Tải artifact và so sánh checksum.
7. Kiểm tra JPMS module name nếu dùng module path.
8. Tái hiện bằng clean consumer build.

## 24. Checklist trước khi publish module artifact

### Identity và nội dung

- [ ] `groupId`, `artifactId`, version đúng convention.
- [ ] Packaging/extension phù hợp.
- [ ] Main artifact chứa class/resource cần thiết.
- [ ] Không chứa secret, file local hoặc test output ngoài ý muốn.
- [ ] Classifier được dùng đúng cho artifact phụ.
- [ ] JPMS descriptor hợp lệ nếu module là modular JAR.

### Build và dependency

- [ ] Module được include trong Maven Reactor/Gradle settings.
- [ ] Dependency giữa module được khai báo đúng.
- [ ] Không có dependency cycle ngoài ý muốn.
- [ ] Public API và transitive dependency được review.
- [ ] Unit/integration tests pass.
- [ ] Version dependency được quản lý nhất quán.

### Publication

- [ ] POM hoặc Gradle Module Metadata đúng.
- [ ] Sources/Javadoc được publish nếu policy yêu cầu.
- [ ] Release và snapshot repository tách biệt.
- [ ] Credential được lấy từ secret store.
- [ ] Không ghi đè release version.
- [ ] Checksum/signature/provenance được tạo theo policy.

### Consumer verification

- [ ] Artifact resolve từ repository đích.
- [ ] Consumer compile và test thành công.
- [ ] Transitive dependencies đầy đủ.
- [ ] Artifact version/hash đúng.
- [ ] Không phụ thuộc vào local repository cũ.
- [ ] Migration/relocation được công bố nếu tọa độ thay đổi.

## 25. Tài liệu tham khảo chính thức

- [Maven Artifacts](https://maven.apache.org/repositories/artifacts.html) — artifact coordinates, GAVCE, classifier, extension và repository identity.
- [Guide to Working with Multiple Modules — Maven](https://maven.apache.org/guides/mini/guide-multiple-modules.html) — Maven Reactor, module collection, dependency order và chọn project.
- [Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/) — cài artifact và POM vào local repository.
- [Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/) — deploy artifact, POM và attached artifacts lên remote repository.
- [Multi-Project Builds — Gradle](https://docs.gradle.org/current/userguide/multi_project_builds.html) — root project, subprojects và dependency giữa các project.
- [The Maven Publish Plugin — Gradle](https://docs.gradle.org/current/userguide/publishing_maven.html) — publication, POM, repository và publish tasks.
- [Publishing a Project as a Module — Gradle](https://docs.gradle.org/current/userguide/publishing_setup.html) — artifact, Gradle Module Metadata, POM, checksum và signature.
- [JAR File Specification — Java SE](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html) — modular JAR, module descriptor, automatic module và multi-release JAR.
- [Introduction to Modules in Java — dev.java](https://dev.java/learn/modules/intro/) — module declaration, module path và modular JAR.

Module artifact là đầu ra có thể định danh và phân phối của một build module. Hãy quản lý identity, dependency metadata, version, repository và integrity cùng với chính file JAR/ZIP. Maven Reactor và Gradle multi-project build giúp module phối hợp trong cùng build; publication giúp consumer bên ngoài resolve artifact qua repository. Nếu dự án dùng JPMS, hãy kiểm tra module descriptor và module path như một lớp riêng bên cạnh artifact coordinates.
