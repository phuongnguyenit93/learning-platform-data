# Metadata artifact trong hệ sinh thái Java

Trong nhóm Quản lý artifact, metadata là thông tin giúp build tool, repository và người dùng nhận diện, phân giải, kiểm tra và sử dụng một binary đã được build. Với thư viện Java, metadata xuất hiện ở nhiều nơi: POM của Maven, `maven-metadata.xml` trong repository, Gradle Module Metadata (`.module`), manifest bên trong JAR, module descriptor `module-info.class`, checksum và chữ ký.

Các loại metadata này có nhiệm vụ khác nhau. POM và `.module` mô tả component, dependency và cách consumer sử dụng artifact. `maven-metadata.xml` giúp repository tìm phiên bản hoặc ánh xạ SNAPSHOT. Manifest mô tả thuộc tính của JAR và ứng dụng. `module-info.class` mô tả Java module. Checksum và chữ ký hỗ trợ kiểm tra tính toàn vẹn và nguồn gốc.

Bài học dùng Maven 3.9.12, Gradle 9.2.1 và Zulu/OpenJDK 24.0.2. Ví dụ Java tương thích Java 17+. Đã publish một thư viện mẫu lên file repository cục bộ bằng cả Maven và Gradle, kiểm tra POM, repository metadata, Gradle `.module`, JAR manifest, module descriptor và checksum.

## 1. Metadata nằm ở đâu trong vòng đời artifact?

Một artifact không chỉ là file JAR. Consumer cần biết file đó thuộc component nào, phiên bản nào, cần dependency nào và có thể dùng trong compile/runtime context nào.

~~~text
Source + build configuration
          |
          v
    Compile / Package
          |
          v
      Library JAR
       |       |
       |       +--> META-INF/MANIFEST.MF
       |       +--> module-info.class (if modular)
       |       +--> embedded build metadata (tool-specific)
       |
       v
   Publish to repository
       |
       +--> artifact JAR
       +--> POM / Gradle .module
       +--> sources / Javadoc JAR
       +--> maven-metadata.xml
       +--> checksums / signatures
                    |
                    v
            Dependency resolution
                    |
                    v
              Consumer build
~~~

Có thể chia metadata thành bốn nhóm:

| Nhóm | Ví dụ | Vai trò |
|---|---|---|
| Component metadata | `pom.xml`, `.module` | Coordinates, dependencies, variants, capabilities |
| Repository metadata | `maven-metadata.xml` | Danh sách version, snapshot timestamp, plugin prefix |
| Archive metadata | `MANIFEST.MF`, `module-info.class` | Thuộc tính JAR, entry point, module graph |
| Integrity/provenance | `.sha256`, `.asc`, JAR signature, SBOM | Kiểm tra file, signer và thành phần phần mềm |

Một file có thể nằm cạnh JAR trong repository hoặc nằm bên trong JAR. Đừng nhầm POM sidecar với `META-INF/maven/.../pom.xml` được một số build plugin nhúng vào JAR.

## 2. Maven coordinates: định danh artifact bằng GAV

Maven xác định một component chính bằng ba tọa độ:

- `groupId`: tổ chức hoặc namespace sở hữu component.
- `artifactId`: tên component.
- `version`: phiên bản được phát hành.

Ví dụ:

~~~xml
<groupId>com.example</groupId>
<artifactId>metadata-demo</artifactId>
<version>1.2.0</version>
<packaging>jar</packaging>
~~~

GAV của component này là `com.example:metadata-demo:1.2.0`.

Trong Maven repository layout, `groupId` được chuyển dấu chấm thành thư mục:

~~~text
Repository root/
  com/
    example/
      metadata-demo/
        1.2.0/
          metadata-demo-1.2.0.pom
          metadata-demo-1.2.0.jar
          metadata-demo-1.2.0-sources.jar
          metadata-demo-1.2.0-javadoc.jar
~~~

`packaging` xác định loại artifact chính và cách Maven gắn lifecycle/plugin. Với Java library, `jar` là packaging phổ biến. `war`, `pom`, `maven-plugin` và các packaging khác có quy tắc tương ứng.

Ngoài GAV, một file được nhận diện thêm bằng extension và classifier:

- Extension là loại file, ví dụ `jar`, `pom`, `zip`.
- Classifier phân biệt biến thể gắn với cùng GAV, ví dụ `sources`, `javadoc`, `tests`, `linux-x86_64`.

Ví dụ dependency có classifier:

~~~xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>metadata-demo</artifactId>
  <version>1.2.0</version>
  <classifier>tests</classifier>
  <type>test-jar</type>
</dependency>
~~~

Không tự thêm classifier chỉ vì file có tên khác. Classifier phải được khai báo và publish đúng trong component metadata.

## 3. POM: metadata mô tả component cho Maven

POM là XML project model. POM được publish cạnh artifact và được Maven đọc để biết tọa độ, dependency graph, license, SCM, developer và các thông tin project khác.

Một POM có metadata cơ bản:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>metadata-demo</artifactId>
  <version>1.2.0</version>
  <packaging>jar</packaging>

  <name>Metadata Demo</name>
  <description>Example library that demonstrates artifact metadata.</description>
  <url>https://example.com/metadata-demo</url>

  <licenses>
    <license>
      <name>Apache License, Version 2.0</name>
      <url>https://www.apache.org/licenses/LICENSE-2.0</url>
    </license>
  </licenses>

  <developers>
    <developer>
      <id>example-team</id>
      <name>Example Team</name>
    </developer>
  </developers>

  <scm>
    <connection>scm:git:https://example.com/metadata-demo.git</connection>
    <url>https://example.com/metadata-demo</url>
  </scm>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>api-support</artifactId>
      <version>2.4.0</version>
      <scope>compile</scope>
    </dependency>
  </dependencies>
</project>
~~~

Các phần có ý nghĩa:

- `name`, `description`, `url`: giúp người dùng hiểu component.
- `licenses`: công bố license áp dụng cho artifact.
- `developers`: thông tin nhóm phát triển.
- `scm`: nguồn quản lý source và connection.
- `properties`: thuộc tính build có thể được plugin dùng.
- `dependencies`: dependency mà consumer cần resolve.
- `dependencyManagement`: quản lý version mặc định trong một dependency family; tự nó không thêm dependency vào classpath.
- `distributionManagement`: repository đích để deploy release/SNAPSHOT.

Dependency scope ảnh hưởng nơi dependency được dùng và cách nó truyền tới consumer. Các scope thường gặp là `compile`, `provided`, `runtime`, `test`, `system` và `import` (trong dependency management với POM BOM). Chọn scope theo contract thật của thư viện; khai báo sai scope có thể làm dependency biến mất khỏi runtime hoặc rò dependency không cần thiết tới consumer.

POM là metadata dành cho build tool, không phải file manifest nằm trong JAR. Nếu người dùng tải riêng JAR mà không có repository/POM, Maven không tự biết dependency transitive của thư viện đó.

## 4. Repository metadata `maven-metadata.xml`

`maven-metadata.xml` là metadata do Maven repository quản lý. Đây không phải POM và cũng không phải binary artifact. Maven tự đọc nó trong các thao tác tìm version, resolve SNAPSHOT và khám phá Maven plugin.

Có ba vị trí metadata chính:

1. **Group level:** nằm trong thư mục `groupId`, chủ yếu ánh xạ plugin prefix tới `artifactId`.
2. **Artifact level:** nằm trong thư mục `groupId/artifactId`, mô tả danh sách version, `latest`, `release` và `lastUpdated`.
3. **Version level:** nằm trong thư mục của base SNAPSHOT version, mô tả timestamp/build number và mapping tới từng snapshot file.

Ví dụ metadata ở artifact level:

~~~xml
<metadata>
  <groupId>com.example</groupId>
  <artifactId>metadata-demo</artifactId>
  <versioning>
    <latest>1.2.0</latest>
    <release>1.2.0</release>
    <versions>
      <version>1.0.0</version>
      <version>1.1.0</version>
      <version>1.2.0</version>
    </versions>
    <lastUpdated>20261110120000</lastUpdated>
  </versioning>
</metadata>
~~~

Repository manager có thể cập nhật metadata này khi deploy artifact. Không tự sửa `maven-metadata.xml` để ép Maven dùng một file JAR; nếu repository metadata không đồng nhất, hãy sửa quy trình publish hoặc metadata bằng chức năng quản trị chính thức của repository.

Maven metadata thường có checksum sidecar theo cấu hình repository. Khi tải artifact, Maven có thể dùng metadata và checksum để resolve/kiểm tra file.

## 5. SNAPSHOT metadata và timestamped version

`1.2.0-SNAPSHOT` là base version có thể thay đổi khi nhóm deploy build mới. Trong remote Maven repository, mỗi lần deploy SNAPSHOT thường được lưu dưới tên có timestamp và build number.

Ví dụ thư mục version vẫn là:

~~~text
com/example/metadata-demo/1.2.0-SNAPSHOT/
~~~

Nhưng artifact file có thể là:

~~~text
metadata-demo-1.2.0-20261110.120000-3.jar
metadata-demo-1.2.0-20261110.120000-3.pom
maven-metadata.xml
~~~

Metadata version-level ánh xạ base version `1.2.0-SNAPSHOT` tới snapshot cụ thể:

~~~xml
<metadata modelVersion="1.1.0">
  <groupId>com.example</groupId>
  <artifactId>metadata-demo</artifactId>
  <version>1.2.0-SNAPSHOT</version>
  <versioning>
    <snapshot>
      <timestamp>20261110.120000</timestamp>
      <buildNumber>3</buildNumber>
    </snapshot>
    <snapshotVersions>
      <snapshotVersion>
        <extension>jar</extension>
        <value>1.2.0-20261110.120000-3</value>
        <updated>20261110120000</updated>
      </snapshotVersion>
      <snapshotVersion>
        <extension>pom</extension>
        <value>1.2.0-20261110.120000-3</value>
        <updated>20261110120000</updated>
      </snapshotVersion>
    </snapshotVersions>
  </versioning>
</metadata>
~~~

Consumer khai báo `1.2.0-SNAPSHOT`; Maven đọc metadata để tìm file timestamped tương ứng. Vì SNAPSHOT có thể thay đổi, không dùng SNAPSHOT làm version release production cần tái lập lâu dài.

Release version như `1.2.0` nên bất biến sau khi phát hành. Không deploy một binary khác lên cùng tọa độ release; hãy tăng version. Nếu repository cho phép ghi đè release, build cũ có thể resolve ra binary mới mà không đổi POM hoặc source code.

## 6. Gradle Module Metadata: file `.module`

Gradle Module Metadata (GMM) là định dạng metadata riêng của Gradle, thường có tên `<artifact>-<version>.module`. Khi dùng Maven Publish hoặc Ivy Publish, Gradle tự publish `.module` cùng POM/Ivy descriptor để giữ các khái niệm không biểu diễn đầy đủ trong POM.

GMM có thể mô tả:

- Variants như `apiElements`, `runtimeElements`, `sourcesElements`, `javadocElements`.
- Attributes như Java target version, usage, category và library elements.
- Dependency constraints và rich version constraints.
- Capabilities và feature variants.
- Artifact files gắn với từng variant.

Ví dụ rút gọn của `.module`:

~~~json
{
  "formatVersion": "1.1",
  "component": {
    "group": "com.example",
    "module": "metadata-demo",
    "version": "1.2.0"
  },
  "variants": [
    {
      "name": "apiElements",
      "attributes": {
        "org.gradle.category": "library",
        "org.gradle.usage": "java-api",
        "org.gradle.jvm.version": 17
      },
      "files": [
        {
          "name": "metadata-demo-1.2.0.jar",
          "url": "metadata-demo-1.2.0.jar"
        }
      ]
    }
  ]
}
~~~

POM và `.module` được publish song song. Maven consumer đọc POM; Gradle consumer có thể ưu tiên GMM để chọn variant phù hợp. Không xóa file `.module` hoặc marker `published-with-gradle-metadata` trong POM nếu publication cần hỗ trợ Gradle variant-aware resolution.

POM không thể biểu diễn mọi khái niệm của Gradle, vì vậy Gradle phải map một phần model sang Maven. Khi publish, Gradle có thể cảnh báo nếu dependency constraint, capability hoặc variant không thể biểu diễn tương đương trong POM. Hãy đọc warning và kiểm tra cả Gradle consumer lẫn Maven consumer nếu thư viện hỗ trợ cả hai.

## 7. Manifest bên trong JAR

JAR là ZIP archive có thể chứa manifest tại:

~~~text
META-INF/MANIFEST.MF
~~~

Manifest có các main attributes áp dụng cho toàn archive và các named sections áp dụng cho entry cụ thể. Một manifest đơn giản:

~~~text
Manifest-Version: 1.0
Implementation-Title: Metadata Demo
Implementation-Version: 1.2.0
Specification-Title: Metadata Demo API
Specification-Version: 1.2
Main-Class: com.example.app.Main
Automatic-Module-Name: com.example.metadata
Multi-Release: true
~~~

Một số attribute thường dùng:

| Attribute | Ý nghĩa |
|---|---|
| `Manifest-Version` | Phiên bản cú pháp manifest |
| `Main-Class` | Entry point khi chạy `java -jar` |
| `Class-Path` | Các URL tương đối tới dependency JAR cần thiết |
| `Implementation-Title` | Tên implementation |
| `Implementation-Version` | Phiên bản implementation |
| `Implementation-Vendor` | Nhà cung cấp implementation |
| `Specification-Title` | Tên specification/API |
| `Specification-Version` | Phiên bản specification |
| `Automatic-Module-Name` | Tên module ổn định cho JAR chưa có module descriptor |
| `Multi-Release` | Đánh dấu multi-release JAR khi đặt `true` |

`Class-Path` trong manifest dùng các URL tương đối, phân cách bằng khoảng trắng; nó không dùng `File.pathSeparator`. Đây là quy tắc riêng của JAR manifest, khác với classpath argument của lệnh `java -cp`.

`Main-Class` cần thiết cho executable JAR, nhưng không phải mọi library JAR đều cần nó. `Implementation-Version` hữu ích cho diagnostic, nhưng consumer không nên dùng manifest để thay thế dependency management hoặc version pinning.

Manifest line có giới hạn chiều dài theo JAR specification; công cụ `jar`/build plugin tự xử lý line wrapping và continuation. Hạn chế tự ghi manifest bằng string nếu không cần thiết.

## 8. `module-info.class` và JPMS metadata

Một named Java module có module descriptor được biên dịch từ `module-info.java`:

~~~java
module com.example.metadata {
    requires java.logging;
    exports com.example.metadata.api;
}
~~~

Khi compile, `module-info.class` được đặt ở root của JAR. Descriptor có thể mô tả:

- `requires`: module phụ thuộc.
- `exports`: package public mà module cho phép module khác truy cập.
- `opens`: package được mở cho reflection.
- `uses`: service mà module cần.
- `provides`: implementation cung cấp cho service.
- `requires transitive` và `requires static`: điều khiển quan hệ module dependency.

Kiểm tra JAR:

~~~text
jar --describe-module --file target/metadata-demo-1.2.0.jar
~~~

Khi JAR không có `module-info.class`, nó có thể trở thành automatic module khi đặt trên module path. Tên automatic module thường được suy ra từ filename; manifest attribute `Automatic-Module-Name` cung cấp tên ổn định hơn để tránh tên thay đổi khi file được rename.

`Automatic-Module-Name` không thay thế module descriptor. Khi dự án đã có `module-info.java`, descriptor là nguồn metadata module chính.

Multi-release JAR có thể chứa các class theo phiên bản Java trong `META-INF/versions/<N>/`. Nếu JAR có nội dung này, manifest phải có `Multi-Release: true` để JVM xử lý đúng. Không thêm attribute này nếu archive không được đóng gói theo cấu trúc multi-release.

## 9. Metadata được nhúng trong JAR

Một số build tool nhúng thêm metadata của project vào archive. Ví dụ Maven JAR Plugin thường đặt:

~~~text
META-INF/maven/com.example/metadata-demo/pom.xml
META-INF/maven/com.example/metadata-demo/pom.properties
~~~

`pom.properties` thường chứa:

~~~properties
groupId=com.example
artifactId=metadata-demo
version=1.2.0
~~~

Metadata nhúng giúp diagnostic hoặc thư viện tự đọc thông tin build của chính nó. Nó không thay POM sidecar mà Maven dùng để resolve dependency từ repository.

Không phải mọi Gradle JAR đều nhúng `pom.properties`; định dạng phụ thuộc build plugin và cấu hình. Nếu ứng dụng cần đọc version runtime, có thể dùng package implementation version hoặc resource build-info do dự án tạo ra, nhưng phải định nghĩa hành vi khi metadata vắng mặt.

## 10. Sources, Javadoc và classifier artifacts

Một publication thường có nhiều file cùng GAV:

~~~text
metadata-demo-1.2.0.jar
metadata-demo-1.2.0-sources.jar
metadata-demo-1.2.0-javadoc.jar
~~~

- Binary JAR chứa class/resource để chạy.
- Sources JAR chứa source code để IDE hiển thị khi debug hoặc navigate.
- Javadoc JAR chứa HTML API documentation để IDE hiển thị hover/help.

Maven Source Plugin và Javadoc Plugin có thể attach các artifact này vào publication. Gradle Java Plugin hỗ trợ:

~~~groovy
java {
    withSourcesJar()
    withJavadocJar()
}
~~~

Gradle tạo task `sourcesJar` và `javadocJar`, đồng thời gắn các variant tương ứng vào Java component. Khi publish `from components.java`, các artifact phụ được publish cùng publication.

Không tự đổi classifier của một file mà consumer đã phụ thuộc vào. Nếu publish `tests`, `sources`, `javadoc` hoặc native artifact, hãy khai báo đúng extension/classifier để dependency resolver tìm được file.

## 11. Checksum: kiểm tra tính toàn vẹn

Repository có thể publish checksum sidecar:

~~~text
metadata-demo-1.2.0.jar.sha256
metadata-demo-1.2.0.jar.sha512
metadata-demo-1.2.0.jar.sha1
~~~

Checksum giúp phát hiện file bị thay đổi hoặc hỏng trong quá trình lưu trữ/truyền tải. SHA-256 và SHA-512 phù hợp cho kiểm tra integrity hiện đại; MD5/SHA-1 chỉ nên được hiểu là metadata legacy nếu repository còn cung cấp.

Tính checksum của file local:

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 .\target\metadata-demo-1.2.0.jar
~~~

Linux:

~~~sh
sha256sum target/metadata-demo-1.2.0.jar
~~~

macOS:

~~~sh
shasum -a 256 target/metadata-demo-1.2.0.jar
~~~

So sánh giá trị tính được với checksum lấy từ nguồn tin cậy. Nếu tải cả JAR và checksum từ cùng một repository đã bị xâm nhập, attacker có thể thay cả hai; checksum một mình không xác thực danh tính publisher.

Gradle Maven Publish tạo checksum metadata cho các file publish. Repository manager cũng có thể tạo checksum sidecar theo policy. Không tự tạo một checksum file có tên giống checksum chính thức nhưng nội dung không khớp artifact.

## 12. Chữ ký PGP và chữ ký JAR

Có hai kiểu chữ ký thường gặp:

**Detached PGP signature** thường có đuôi `.asc`, nằm cạnh artifact:

~~~text
metadata-demo-1.2.0.jar
metadata-demo-1.2.0.jar.asc
~~~

Consumer dùng GPG và public key fingerprint đáng tin cậy để xác minh. Detached signature ký file artifact bên ngoài archive.

**JAR signing** dùng `jarsigner`. Công cụ cập nhật manifest digest và thêm signature file/block vào `META-INF`, ví dụ:

~~~text
META-INF/MANIFEST.MF
META-INF/DEMO.SF
META-INF/DEMO.RSA
~~~

Tạo keystore, ký và xác minh là các thao tác riêng. Ví dụ lệnh:

~~~text
jarsigner -keystore release.p12 -storetype PKCS12 -signedjar metadata-demo-signed.jar metadata-demo.jar release-key
jarsigner -verify -verbose -certs metadata-demo-signed.jar
~~~

Trong quy trình release, private key phải được giữ trong hệ thống signing/CI secret an toàn. Không commit keystore, private key, token hoặc password vào repository hay POM.

Một chữ ký JAR hợp lệ về mặt digest chưa có nghĩa certificate được trust. Consumer còn phải kiểm tra certificate chain, fingerprint, thời hạn và timestamp. Chữ ký JAR cũng không giống detached PGP signature: định dạng và cách consumer xác minh khác nhau.

Ký sau khi hoàn thiện archive. Thay đổi entry đã ký sau đó sẽ làm signature verification thất bại; nếu cần sửa nội dung, build lại và ký lại.

## 13. SBOM và provenance đi kèm artifact

SBOM (Software Bill of Materials) mô tả component và dependency được dùng để tạo sản phẩm. Các định dạng phổ biến gồm CycloneDX và SPDX. SBOM có thể được publish như artifact riêng hoặc attach vào release:

~~~text
metadata-demo-1.2.0.jar
metadata-demo-1.2.0.pom
metadata-demo-1.2.0.module
metadata-demo-1.2.0-sbom.cdx.json
metadata-demo-1.2.0.jar.asc
~~~

SBOM bổ sung thông tin thành phần, license, version và dependency; nó không thay thế POM hoặc Gradle Module Metadata dùng để resolve dependency.

Provenance/attestation có thể ghi lại source revision, build workflow, builder identity và các input của build. Lưu trữ và xác minh provenance theo quy trình supply-chain của tổ chức; không tự coi một JSON file có tên `provenance` là attestation đáng tin nếu không có chữ ký/identity verification.

## 14. Publish metadata bằng Maven

Để publish artifact, Maven dùng `distributionManagement` trong POM hoặc cấu hình deploy phù hợp:

~~~xml
<distributionManagement>
  <repository>
    <id>releases</id>
    <url>https://repo.example.com/maven-releases/</url>
  </repository>
  <snapshotRepository>
    <id>snapshots</id>
    <url>https://repo.example.com/maven-snapshots/</url>
  </snapshotRepository>
</distributionManagement>
~~~

`id` phải khớp với `<server><id>` trong Maven `settings.xml`, nơi cấu hình credential. Đặt credential trong settings/CI secret store, không đặt password trong POM.

Ví dụ publish:

~~~text
mvn -B -ntp clean deploy
~~~

- `install` đưa artifact vào local Maven repository để build khác trên cùng máy có thể dùng.
- `deploy` publish artifact và POM lên repository đã cấu hình.
- `package` chỉ tạo package ở local workspace; không publish lên remote repository.

Một project POM nên pin version build plugin và khai báo source encoding/release target. Ví dụ Maven JAR Plugin có thể thêm manifest attributes:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-jar-plugin</artifactId>
  <version>3.4.2</version>
  <configuration>
    <archive>
      <manifestEntries>
        <Implementation-Title>Metadata Demo</Implementation-Title>
        <Implementation-Version>1.2.0</Implementation-Version>
        <Specification-Title>Metadata Demo API</Specification-Title>
      </manifestEntries>
    </archive>
  </configuration>
</plugin>
~~~

Gắn Sources/Javadoc JAR bằng Maven Source Plugin và Maven Javadoc Plugin khi publication yêu cầu. Đặt đúng classifier và kiểm tra artifact thực tế trong repository sau deploy.

## 15. Publish metadata bằng Gradle

Dùng `maven-publish` để publish Java component:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.2.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            pom {
                name = 'Metadata Demo'
                description = 'Example Java library.'
                url = 'https://example.com/metadata-demo'
                licenses {
                    license {
                        name = 'Apache License, Version 2.0'
                        url = 'https://www.apache.org/licenses/LICENSE-2.0'
                    }
                }
                scm {
                    connection = 'scm:git:https://example.com/metadata-demo.git'
                    url = 'https://example.com/metadata-demo'
                }
            }
        }
    }
    repositories {
        maven {
            name = 'releases'
            url = uri('https://repo.example.com/maven-releases')
            credentials {
                username = providers.environmentVariable('REPO_USER').get()
                password = providers.environmentVariable('REPO_TOKEN').get()
            }
        }
    }
}
~~~

Chạy:

~~~text
./gradlew publish
~~~

Gradle tạo task publication theo tên publication/repository, ví dụ `publishMavenJavaPublicationToReleasesRepository`. `publish` chạy các task publish đã cấu hình.

Để thêm manifest attributes:

~~~groovy
tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Implementation-Title': project.name,
            'Implementation-Version': project.version
        )
    }
}
~~~

Gradle tự tạo `.module` và POM khi dùng Maven Publish. Nếu cấu hình custom variant hoặc dependency constraints, kiểm tra cảnh báo mapping để bảo đảm Maven consumer vẫn có POM phù hợp. Không đưa repository credential vào `gradle.properties` đã commit hoặc build script có thể public.

## 16. Versioning và metadata nhất quán

Version là một phần của identity artifact. Cần đồng bộ version giữa:

- GAV trong POM/Gradle publication.
- Tên file artifact.
- `Implementation-Version` trong manifest nếu dùng.
- Version trong embedded `pom.properties`.
- Version trong SBOM/provenance.
- Release tag và changelog.

Không hardcode nhiều version độc lập trong POM, Gradle script và manifest nếu chúng có thể lấy từ cùng một project version. Version mismatch làm người dùng khó xác định binary thực sự đang chạy.

Dùng semantic versioning khi phù hợp với contract của thư viện: major cho thay đổi không tương thích, minor cho chức năng tương thích ngược, patch cho sửa lỗi tương thích. Maven không bắt buộc semantic versioning; đó là policy của project.

Release artifact nên bất biến. Snapshot có thể thay đổi theo lần deploy; release version không nên được deploy đè. Không dùng `LATEST` hoặc `RELEASE` dynamic version trong dependency production nếu cần build tái lập; pin version cụ thể hoặc dùng dependency constraints/platform đã kiểm soát.

## 17. Reproducible artifact và build metadata

Cùng source, dependency và build configuration nên tạo ra artifact có nội dung ổn định. Metadata có thể làm JAR thay đổi giữa hai lần build nếu timestamp, build path, machine name hoặc generated build id bị nhúng vào archive.

Với Maven, có thể đặt:

~~~xml
<properties>
  <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Đặt timestamp theo quy trình reproducible build của project, thường lấy từ source revision/release timestamp đã được chuẩn hóa.

Với Gradle, archive tasks được thiết kế để có output ổn định khi input không đổi; tránh tự thêm thời gian hiện tại hoặc đường dẫn máy local vào manifest/resources.

Các nguyên tắc:

- Pin JDK/toolchain và plugin version.
- Pin dependency version, tránh dynamic version không kiểm soát.
- Đặt encoding rõ ràng.
- Chuẩn hóa archive timestamp và file order.
- Không nhúng username, máy build, đường dẫn local hoặc secret.
- Không tạo build identifier ngẫu nhiên nếu downstream cache/reproducibility cần ổn định.
- Lưu checksum sau khi artifact cuối cùng đã được tạo và ký.

Metadata phục vụ traceability nên ghi source revision/build provenance có kiểm soát, nhưng không làm artifact khác nhau một cách vô nghĩa giữa hai lần build từ cùng input.

## 18. Kiểm tra artifact và metadata sau khi publish

Không chỉ tin vào thông báo `BUILD SUCCESS`. Hãy kiểm tra repository output:

~~~text
# List JAR entries
jar --list --file target/metadata-demo-1.2.0.jar

# Inspect module descriptor
jar --describe-module --file target/metadata-demo-1.2.0.jar

# Extract manifest for inspection
jar --extract --file target/metadata-demo-1.2.0.jar META-INF/MANIFEST.MF
~~~

Trong Maven project:

~~~text
mvn help:effective-pom
mvn dependency:tree
mvn -B -ntp deploy
~~~

Trong Gradle project:

~~~text
./gradlew outgoingVariants
./gradlew dependencies
./gradlew publishToMavenLocal
~~~

Kiểm tra repository version directory có đúng file:

- Main JAR và POM.
- `.module` nếu publish bằng Gradle.
- Sources/Javadoc JAR nếu được yêu cầu.
- Snapshot `maven-metadata.xml` khi publish SNAPSHOT.
- Checksum/signature theo repository policy.

Để kiểm tra artifact đã publish có thể được consumer resolve, tạo một consumer project sạch và khai báo dependency bằng đúng GAV. Đừng chỉ kiểm tra producer build; một POM sai hoặc thiếu classifier có thể vẫn cho producer build xanh nhưng consumer không resolve được.

## 19. Ví dụ Java 17+: đọc metadata từ JAR

Tạo `ArtifactMetadataInspector.java`:

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class ArtifactMetadataInspector {
    private ArtifactMetadataInspector() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ArtifactMetadataInspector <jar-file>");
        }

        Path jarPath = Path.of(args[0]);

        try (JarFile jar = new JarFile(jarPath.toFile())) {
            Manifest manifest = jar.getManifest();
            Attributes attributes = manifest == null
                    ? new Attributes()
                    : manifest.getMainAttributes();

            System.out.println("JAR_NAME=" + jarPath.getFileName());
            System.out.println("MANIFEST_PRESENT=" + (manifest != null));
            System.out.println("IMPLEMENTATION_TITLE="
                    + attributes.getValue("Implementation-Title"));
            System.out.println("IMPLEMENTATION_VERSION="
                    + attributes.getValue("Implementation-Version"));
            System.out.println("AUTOMATIC_MODULE_NAME="
                    + attributes.getValue("Automatic-Module-Name"));
            System.out.println("MODULE_INFO_PRESENT="
                    + (jar.getEntry("module-info.class") != null));
        }
    }
}
~~~

Biên dịch:

~~~text
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d out ArtifactMetadataInspector.java
~~~

Chạy với artifact đã publish/build:

~~~text
java -cp out ArtifactMetadataInspector target/metadata-demo-1.2.0.jar
~~~

Nếu JAR có manifest attributes như ví dụ Maven/Gradle ở trên, output sẽ có dạng:

~~~text
JAR_NAME=metadata-demo-1.2.0.jar
MANIFEST_PRESENT=true
IMPLEMENTATION_TITLE=Metadata Demo
IMPLEMENTATION_VERSION=1.2.0
AUTOMATIC_MODULE_NAME=null
MODULE_INFO_PRESENT=true
~~~

`AUTOMATIC_MODULE_NAME=null` là bình thường khi JAR có `module-info.class` và manifest không khai báo `Automatic-Module-Name`. Chương trình đọc manifest và kiểm tra module descriptor entry; để xem exports/requires cụ thể, dùng `jar --describe-module`.

## 20. Kiểm tra chữ ký và checksum trong release pipeline

Sau khi publish artifact cuối cùng, tính SHA-256 và lưu checksum theo repository policy. Nếu ký JAR bằng `jarsigner`, kiểm tra signature trước khi upload:

~~~text
jarsigner -verify -verbose -certs target/metadata-demo-1.2.0.jar
~~~

Nếu cần strict verification:

~~~text
jarsigner -verify -strict -verbose -certs target/metadata-demo-1.2.0.jar
~~~

`-strict` có thể làm lệnh trả lỗi khi certificate chain hoặc trust policy không đạt yêu cầu. Đây là kiểm tra khác với việc chỉ xác nhận các entry digest còn khớp.

Với PGP detached signature:

~~~text
gpg --verify metadata-demo-1.2.0.jar.asc metadata-demo-1.2.0.jar
~~~

Xác minh fingerprint public key bằng kênh tin cậy độc lập. Không chấp nhận một public key chỉ vì nó được tải cùng artifact từ chính repository đang kiểm tra.

Một release pipeline tốt thường chạy theo thứ tự:

1. Build từ source revision đã được review/tag.
2. Chạy compile, tests, static checks và packaging.
3. Tạo POM/Gradle metadata, Sources/Javadoc JAR và SBOM.
4. Kiểm tra manifest, module descriptor và repository coordinates.
5. Tính checksum, ký artifact/metadata theo policy.
6. Publish vào staging/release repository.
7. Resolve artifact bằng consumer test project.
8. Promote release sau khi kiểm tra thành công.

## 21. Troubleshooting artifact metadata

### Consumer resolve được JAR nhưng thiếu dependency transitive

**Nguyên nhân:** POM thiếu dependency, scope sai, hoặc publication chỉ chứa binary mà không có component metadata.

**Cách xử lý:** kiểm tra POM đã publish, `dependency:tree`, Gradle `.module` và consumer configuration. Kiểm tra dependency scope/API exposure.

### Maven báo `Could not find artifact`

**Nguyên nhân:** GAV sai, version chưa publish, repository URL/profile chưa được bật hoặc snapshot/release repository cấu hình sai.

**Cách xử lý:** kiểm tra đường dẫn repository theo groupId/artifactId/version, POM và metadata. Xác nhận `distributionManagement`, settings profile và server id.

### SNAPSHOT consumer vẫn resolve binary cũ

**Nguyên nhân:** snapshot metadata cache, repository proxy cache hoặc timestamp mapping chưa được cập nhật.

**Cách xử lý:** kiểm tra version-level `maven-metadata.xml`, timestamp/buildNumber, repository cache policy và `-U` khi cần buộc Maven kiểm tra update. Không xóa metadata bằng tay trên repository dùng chung.

### Gradle consumer không thấy variant mong muốn

**Nguyên nhân:** `.module` không được publish/đọc, variant attributes không khớp consumer attributes hoặc publication map sang POM bị mất tính năng.

**Cách xử lý:** xem `outgoingVariants`, `.module`, dependency attributes và repository metadata sources. Kiểm tra warning khi publish.

### Sources/Javadoc JAR không xuất hiện

**Nguyên nhân:** plugin/task không attach artifact, classifier sai hoặc publication không lấy từ component có variant đó.

**Cách xử lý:** kiểm tra `sourcesJar`, `javadocJar`, Maven source/javadoc plugin execution và file thực tế trong repository.

### `Implementation-Version` bị thiếu

**Nguyên nhân:** manifest không được cấu hình hoặc artifact được tạo bởi task khác với task đang kiểm tra.

**Cách xử lý:** cấu hình Maven JAR Plugin/Gradle `Jar.manifest`, build lại và kiểm tra `META-INF/MANIFEST.MF`.

### `jar --describe-module` không tìm thấy module descriptor

**Nguyên nhân:** JAR không chứa `module-info.class`; JAR có thể là classpath JAR hoặc automatic module.

**Cách xử lý:** kiểm tra `module-info.java`, compiler release, source set và JAR contents. Nếu cần tên automatic module ổn định, cấu hình `Automatic-Module-Name`.

### Checksum mismatch

**Nguyên nhân:** file hỏng, proxy cache sai, artifact bị thay đổi sau khi checksum được tạo hoặc đang so sánh nhầm classifier/version.

**Cách xử lý:** tải lại từ repository tin cậy, xác minh đúng file/version/classifier và kiểm tra log publish. Không sửa checksum để khớp một binary không rõ nguồn.

### JAR signature invalid

**Nguyên nhân:** archive bị thay đổi sau khi ký, entry bị hỏng, signature block thiếu hoặc certificate/trust chain không hợp lệ.

**Cách xử lý:** build lại rồi ký lại sau cùng; kiểm tra certificate chain, timestamp và public key fingerprint. Phân biệt digest mismatch với certificate untrusted.

### Release bị ghi đè

**Nguyên nhân:** repository cho phép redeploy cùng release version hoặc CI không kiểm tra version tồn tại.

**Cách xử lý:** bật release immutability/redeploy policy, tăng version và dùng staging repository. Không dựa vào `maven-metadata.xml` để phát hiện mọi trường hợp ghi đè binary.

## 22. Checklist trước khi phát hành artifact

- [ ] `groupId`, `artifactId`, `version` và packaging đúng.
- [ ] POM có name, description, URL, license, SCM và developer metadata cần thiết.
- [ ] Dependency và scope phản ánh đúng API/runtime contract.
- [ ] Gradle `.module` và POM nhất quán với publication.
- [ ] Snapshot/release repository được chọn đúng theo version.
- [ ] `maven-metadata.xml` được repository cập nhật đúng.
- [ ] Main JAR có manifest attributes cần thiết.
- [ ] `module-info.class` hoặc `Automatic-Module-Name` đúng với module policy.
- [ ] Sources/Javadoc JAR được attach khi release yêu cầu.
- [ ] SBOM/provenance được tạo nếu supply-chain policy yêu cầu.
- [ ] Checksum được tính từ file cuối cùng.
- [ ] Signature được xác minh bằng key/certificate đáng tin cậy.
- [ ] Artifact version release không bị redeploy/ghi đè.
- [ ] Consumer project resolve và sử dụng được artifact từ repository đích.
- [ ] Build reproducibility và tool/plugin versions được kiểm soát.
- [ ] Credential không nằm trong POM, JAR, manifest hoặc source repository.

## 23. Tài liệu tham khảo

- Apache Maven — Maven POM Reference: https://maven.apache.org/pom.html
- Apache Maven — Repository Metadata: https://maven.apache.org/repositories/metadata.html
- Apache Maven — Repository Layout và SNAPSHOT: https://maven.apache.org/repository/layout.html
- Apache Maven — Maven Deploy Plugin: https://maven.apache.org/plugins/maven-deploy-plugin/
- Gradle — Gradle Module Metadata: https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html
- Gradle — Publishing a project as a module: https://docs.gradle.org/current/userguide/publishing_setup.html
- Gradle — Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
- Java SE 24 — JAR File Specification: https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html
- Oracle JDK 24 — `jar` command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Oracle JDK 24 — `jarsigner` command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html
- Java SE 24 — `java.util.jar.Manifest`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/jar/Manifest.html
- Java SE 24 — `java.util.jar.JarFile`: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/jar/JarFile.html

Artifact metadata tạo cầu nối giữa binary và hệ sinh thái build/repository. POM và `.module` giúp consumer hiểu component/dependency/variant; `maven-metadata.xml` hỗ trợ version và SNAPSHOT resolution; manifest và `module-info.class` mô tả JAR ở runtime; checksum và chữ ký hỗ trợ integrity/authenticity. Một release đáng tin cần kiểm tra các lớp metadata này cùng binary cuối cùng và thử resolve từ một consumer project độc lập.