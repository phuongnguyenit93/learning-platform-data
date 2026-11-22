# Đóng gói artifact trong Java

Artifact là sản phẩm nhị phân có thể phân phối được tạo từ source code sau quá trình build. Trong Java, artifact thường là JAR, WAR, EAR, ZIP/TAR distribution hoặc runtime image có thể cài đặt và chạy độc lập.

Trong CI/CD, đóng gói artifact chuyển source code thành binary có version, metadata và cấu trúc rõ ràng để kiểm thử, lưu trữ, phát hành và triển khai. Artifact phải chứa đúng class, resource và dependency cần thiết; chạy được trên runtime mục tiêu; có thể xác định nguồn gốc và kiểm tra tính toàn vẹn.

Nguyên tắc quan trọng là **build một lần, kiểm thử một lần, triển khai chính artifact đó qua các môi trường**. Staging và production cần nhận cùng binary đã được kiểm thử, nhận diện bằng version và checksum. Không build lại binary khi promote lên production.

## 1. Artifact trong vòng đời CI/CD

~~~text
Source code
    |
    v
Compile + test
    |
    v
Package artifact
    |
    v
Verify + scan + sign
    |
    v
Publish immutable version
    |
    v
Deploy staging
    |
    v
Promote same artifact digest
    |
    v
Production
~~~

| Bước | Kết quả |
|---|---|
| Compile | Class file và resource đã xử lý |
| Test | Bằng chứng code đáp ứng test |
| Package | JAR, WAR, EAR hoặc distribution |
| Verify | Kiểm tra archive, manifest, dependency và khả năng chạy |
| Scan | Kết quả kiểm tra lỗ hổng và license |
| Sign | Chữ ký xác thực nguồn gốc và tính toàn vẹn |
| Publish | Artifact được lưu trong repository có version |
| Promote | Cùng artifact được đưa sang môi trường kế tiếp |

Không coi toàn bộ thư mục target hoặc build là artifact phát hành. Những thư mục này có thể chứa class tạm, test report và file intermediate. CI nên chọn đúng file cuối cùng cùng metadata cần lưu.

## 2. Các loại artifact Java phổ biến

### JAR

JAR là archive dựa trên ZIP, thường chứa class file, resource, thư mục META-INF, manifest và có thể có module descriptor hoặc thông tin chữ ký. JAR có thể được dùng làm dependency trên classpath hoặc module path. JAR thông thường không nhất thiết chạy trực tiếp bằng java -jar.

### Thin JAR

Thin JAR chỉ chứa code và resource của project. Dependency bên ngoài được cung cấp qua classpath hoặc runtime distribution. Ưu điểm là file nhỏ, dependency được quản lý riêng và phù hợp thư viện publish lên Maven repository. Nhược điểm là khi chạy ứng dụng phải cung cấp đúng dependency; Main-Class trong manifest chưa đủ nếu ứng dụng cần thư viện bên ngoài.

### Executable JAR

Executable JAR có manifest chứa Main-Class. Có thể chạy bằng:

~~~bash
java -jar application.jar
~~~

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.acme.Application
Implementation-Title: artifact-demo
Implementation-Version: 1.0.0
~~~

Executable JAR vẫn có thể là thin JAR. Main-Class chỉ xác định entry point, không tự động đóng gói dependency.

### Fat JAR hoặc shaded JAR

Fat JAR, còn gọi là uber JAR, chứa application classes cùng dependency cần thiết trong một archive. Nó dễ phân phối vì chỉ có một file, nhưng kích thước lớn hơn và có thể xung đột resource/class. Cần xử lý META-INF/services, license và signature. Maven Shade Plugin có thể đóng gói dependency và relocate package khi cần.

### WAR, EAR và distribution

| Định dạng | Mục đích |
|---|---|
| WAR | Web application chạy trong servlet container hoặc application server |
| EAR | Nhiều thành phần enterprise như WAR và module JAR |
| ZIP/TAR distribution | Ứng dụng, dependency, script khởi chạy và tài liệu |

WAR thường chứa WEB-INF/classes, WEB-INF/lib và web resources. Distribution ZIP/TAR thường có JAR chính, dependency JAR trong lib, script trong bin, file cấu hình mẫu và license.

### Runtime image và installer

jlink tạo custom Java runtime image từ các module cần thiết. jpackage tạo application image hoặc installer như MSI, EXE, DEB, RPM, PKG hoặc DMG. Đây là package dành cho ứng dụng desktop hoặc phần mềm cần bộ cài, khác với JAR dùng làm dependency.

## 3. Chọn đúng loại artifact

| Nhu cầu | Artifact nên cân nhắc |
|---|---|
| Library dùng làm dependency | Thin JAR + POM/Gradle metadata |
| Library cần IDE source lookup | JAR + sources JAR + Javadoc JAR |
| Command-line tool ít dependency | Executable JAR |
| Ứng dụng có nhiều dependency | Fat JAR hoặc ZIP/TAR distribution |
| Web application | WAR |
| Enterprise application | EAR nếu application server yêu cầu |
| Desktop app cần bộ cài | jpackage installer |
| Ứng dụng modular cần runtime riêng | jlink runtime image, có thể kết hợp jpackage |

Một JAR có Main-Class nhưng cần thư viện bên ngoài vẫn có thể lỗi ClassNotFoundException hoặc NoClassDefFoundError. Manifest Class-Path có thể khai báo relative URL của dependency JAR, nhưng phải quản lý đường dẫn và cách phân phối các file đó. Với ứng dụng nhiều dependency, distribution có thư mục lib hoặc fat JAR thường dễ vận hành hơn.

## 4. Cấu trúc project và Maven lifecycle

Ví dụ cấu trúc Maven:

~~~text
artifact-demo/
  pom.xml
  src/
    main/java/com/acme/ArtifactDemo.java
    main/resources/application.properties
    test/java/com/acme/ArtifactDemoTest.java
  target/
    classes/
    test-classes/
    surefire-reports/
    artifact-demo-1.0.0.jar
~~~

Quy ước: Java source đặt trong src/main/java; resource runtime đặt trong src/main/resources; test source đặt trong src/test/java. Không đưa test classes, file .env, private key, credential hoặc IDE metadata vào archive.

Maven dùng các lifecycle phase:

| Phase | Vai trò |
|---|---|
| validate | Kiểm tra project và thông tin build |
| compile | Biên dịch source code |
| test | Chạy unit test |
| package | Đóng gói JAR, WAR hoặc định dạng khai báo |
| integration-test | Chạy integration test nếu được cấu hình |
| verify | Kiểm tra tiêu chí chất lượng và kết quả test |
| install | Cài artifact vào local Maven repository |
| deploy | Publish artifact lên remote repository |

Các phase chạy tuần tự. Tạo artifact bằng:

~~~bash
mvn clean package
~~~

Trong CI nên ưu tiên:

~~~bash
mvn -B clean verify
~~~

verify chạy các bước trước đó và cho phép thực hiện integration test hoặc quality checks đã cấu hình. Chỉ dùng mvn deploy khi project đã cấu hình remote repository và pipeline được phép publish.

## 5. Tạo executable JAR bằng Maven

Ví dụ dưới đây tạo JAR chạy được bằng java -jar. Project không có dependency bên ngoài để tập trung vào cấu trúc artifact.

Tệp src/main/java/com/acme/ArtifactDemo.java:

~~~java
package com.acme;

public final class ArtifactDemo {

    private ArtifactDemo() {
    }

    public static void main(String[] args) {
        System.out.println("ARTIFACT_OK version=1.0.0");
    }
}
~~~

Tệp pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.acme</groupId>
    <artifactId>artifact-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.acme.ArtifactDemo</mainClass>
                        </manifest>
                        <manifestEntries>
                            <Implementation-Title>artifact-demo</Implementation-Title>
                            <Implementation-Version>1.0.0</Implementation-Version>
                        </manifestEntries>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Biên dịch, test và đóng gói:

~~~bash
mvn -B clean verify
~~~

Artifact được tạo tại target/artifact-demo-1.0.0.jar.

Chạy artifact:

~~~bash
java -jar target/artifact-demo-1.0.0.jar
~~~

Stdout chính xác:

~~~text
ARTIFACT_OK version=1.0.0
~~~

Ví dụ không có dependency ngoài. Nếu thêm dependency, phải quyết định phân phối dependency riêng hay tạo fat JAR.

## 6. Đóng gói dependency bằng Maven Shade Plugin

Khi ứng dụng cần dependency nhưng muốn phân phối một file duy nhất, có thể dùng Maven Shade Plugin.

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.2</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
                <filters>
                    <filter>
                        <artifact>*:*</artifact>
                        <excludes>
                            <exclude>META-INF/*.SF</exclude>
                            <exclude>META-INF/*.DSA</exclude>
                            <exclude>META-INF/*.RSA</exclude>
                            <exclude>META-INF/*.EC</exclude>
                        </excludes>
                    </filter>
                </filters>
                <transformers>
                    <transformer implementation=
                      "org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                        <mainClass>com.acme.ArtifactDemo</mainClass>
                    </transformer>
                    <transformer implementation=
                      "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Chạy mvn clean package. Shade Plugin được bind vào phase package và tạo shaded JAR.

Nhiều dependency có thể cùng chứa resource có tên giống nhau. Ví dụ quan trọng là META-INF/services. Java ServiceLoader đọc các file này để tìm implementation; ServicesResourceTransformer hợp nhất service descriptor từ các dependency.

Các resource như LICENSE và NOTICE cũng cần được xử lý phù hợp với điều kiện phân phối của dependency. Dependency JAR đã ký có thể chứa META-INF/*.SF, *.RSA, *.DSA hoặc *.EC. Khi Shade gộp và thay đổi nội dung archive, chữ ký ban đầu không còn xác thực được nội dung mới. Loại signature file cũ khỏi archive được hợp nhất và ký lại artifact cuối nếu cần.

Nếu hai dependency có class trùng package hoặc version xung đột, Shade Plugin có thể relocate package. Relocation có thể ảnh hưởng reflection, serialization, resource name và service descriptor; chỉ dùng khi đã kiểm tra các tác động đó.

## 7. Tạo application distribution bằng Gradle

Gradle Java Plugin tạo JAR trong build/libs. Nếu ứng dụng cần dependency và script khởi chạy, dùng Application Plugin.

Ví dụ build.gradle.kts:

~~~kotlin
plugins {
    application
}
group = "com.acme"
version = "1.0.0"
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
application {
    mainClass.set("com.acme.ArtifactDemo")
}
tasks.jar {
    manifest {
        attributes(
            "Main-Class" to "com.acme.ArtifactDemo",
            "Implementation-Title" to project.name,
            "Implementation-Version" to project.version
        )
    }
}
~~~

Build và chạy kiểm tra:

~~~bash
./gradlew clean check
~~~

Tạo ZIP distribution:

~~~bash
./gradlew distZip
~~~

Tạo TAR distribution:

~~~bash
./gradlew distTar
~~~

Cài distribution vào thư mục build:

~~~bash
./gradlew installDist
~~~

Các output thường gặp:

~~~text
build/
  libs/artifact-demo-1.0.0.jar
  distributions/artifact-demo-1.0.0.zip
  distributions/artifact-demo-1.0.0.tar
  install/artifact-demo/bin/
  install/artifact-demo/lib/
~~~

Application Plugin tạo start script và đóng gói dependency vào lib. ZIP/TAR distribution là gói ứng dụng có thể chạy bằng script, không phải một fat JAR duy nhất.

Với Gradle 9, archive task mặc định dùng thứ tự file tái lập và timestamp cố định để hỗ trợ reproducible archives. Với Gradle cũ, cần kiểm tra hoặc cấu hình các thuộc tính archive tương ứng.

## 8. Artifact coordinates và cách đặt version

Maven nhận diện artifact bằng các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| groupId | Namespace của tổ chức/project | com.acme |
| artifactId | Tên module | artifact-demo |
| version | Phiên bản phát hành | 1.0.0 |
| classifier | Phân biệt biến thể | sources, javadoc, tests |
| type/packaging | Định dạng artifact | jar, war, pom |

Ví dụ tọa độ là com.acme:artifact-demo:1.0.0. Tên file mặc định là artifact-demo-1.0.0.jar. Với classifier, file có thể là artifact-demo-1.0.0-sources.jar hoặc artifact-demo-1.0.0-javadoc.jar.

Semantic Versioning thường dùng MAJOR.MINOR.PATCH: MAJOR cho thay đổi không tương thích API, MINOR cho tính năng tương thích ngược, PATCH cho sửa lỗi tương thích ngược.

SNAPSHOT thường dùng cho bản phát triển chưa phải release cuối cùng. Release version như 1.0.0 nên được xem là bất biến. Nếu cần sửa lỗi sau khi publish, phát hành 1.0.1 thay vì ghi đè file 1.0.0.

Build metadata có thể lưu Git commit SHA, build number, JDK vendor/version, CI pipeline ID, dependency lock hoặc SBOM reference. Không để timestamp động trong archive nếu mục tiêu là reproducible build.

## 9. Kiểm tra nội dung JAR bằng JDK tools

Liệt kê nội dung:

~~~bash
jar --list --file target/artifact-demo-1.0.0.jar
~~~

Kiểm tra tính toàn vẹn archive bằng JDK 26:

~~~bash
jar --validate --file target/artifact-demo-1.0.0.jar
~~~

Lệnh này kiểm tra các vấn đề cấu trúc như entry trùng lặp, đường dẫn không an toàn và tính nhất quán API của multi-release JAR. Nó không thay thế test chức năng hoặc security scan.

Manifest nằm tại META-INF/MANIFEST.MF. Kiểm tra Main-Class, Implementation-Version, Class-Path và Multi-Release nếu có.

Với modular JAR:

~~~bash
jar --describe-module --file application.jar
~~~

Kiểm tra module name, requires, exports, uses và provides theo thiết kế module của project.

Chạy smoke test:

~~~bash
java -jar target/artifact-demo-1.0.0.jar
~~~

JAR có thể hợp lệ về ZIP nhưng vẫn thiếu class, resource hoặc dependency cần thiết. Smoke test xác nhận launcher có thể chạy artifact theo cách dự kiến.

## 10. Dependency, bảo mật và kiểm tra CI

Một artifact chạy được trên máy build chưa chắc chạy được trong production. Trước khi publish, kiểm tra dependency runtime, scope compile/runtime/provided, version conflict, class/package trùng, native library phụ thuộc OS/architecture, service provider và license.

Với Maven:

~~~bash
mvn dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies
~~~

Một pipeline nên kiểm tra: build thành công; unit/integration test đạt; đúng file và version; manifest đúng; archive không chứa test class, local config hoặc secret; dependency runtime đầy đủ; JAR validation và smoke test thành công; license/vulnerability scan đạt; checksum, SBOM và provenance được lưu.

Linux:

~~~bash
ls -lh target/artifact-demo-1.0.0.jar
jar --list --file target/artifact-demo-1.0.0.jar
jar --validate --file target/artifact-demo-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-Item target/artifact-demo-1.0.0.jar
jar --list --file target/artifact-demo-1.0.0.jar
jar --validate --file target/artifact-demo-1.0.0.jar
~~~

Không đóng gói password, API token, private key, .env, log có dữ liệu nhạy cảm, test fixture chứa dữ liệu thật không được phép phân phối hoặc IDE metadata.

Nên có dependency vulnerability scan, license compliance scan, SBOM theo SPDX hoặc CycloneDX, checksum SHA-256, chữ ký phát hành, provenance ghi nhận source commit/builder/build process, repository permission, immutable release policy và retention phù hợp.

## 11. Checksum và ký artifact

Checksum là giá trị hash của file. SHA-256 thường được dùng để xác định hai file có cùng nội dung hay không.

Linux:

~~~bash
sha256sum target/artifact-demo-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash target/artifact-demo-1.0.0.jar -Algorithm SHA256
~~~

Checksum giúp phát hiện file bị thay đổi hoặc hỏng trong quá trình upload/download. Tuy nhiên, checksum tải từ cùng một nguồn không xác thực danh tính người phát hành. Muốn xác minh nguồn gốc, cần chữ ký số hoặc provenance đáng tin cậy.

jarsigner ký nội dung JAR bằng certificate/key. Java tooling có thể xác minh chữ ký và phát hiện entry đã bị thay đổi.

~~~bash
jarsigner -keystore release.p12 -storetype PKCS12 application.jar release-key
jarsigner -verify -verbose -certs application.jar
~~~

Private key và password phải được quản lý qua secret store hoặc signing service. Không commit keystore hoặc credential vào source repository. Thực hiện shading, manifest update và resource merge trước khi ký artifact cuối.

Một số repository như Maven Central yêu cầu chữ ký PGP đi kèm artifact và metadata. JAR signing và PGP signing là hai lớp chữ ký khác nhau; hãy theo yêu cầu của repository và chính sách phát hành.

## 12. Reproducible build

Reproducible build là khả năng tạo ra artifact có byte content giống hệt nhau khi build lại từ cùng source, build instructions và môi trường đã kiểm soát.

### Maven

Có thể đặt timestamp cố định cho archive:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Dùng plugin version có hỗ trợ reproducible build và pin version của plugin. Có thể kiểm tra bằng:

~~~bash
mvn clean install
mvn clean verify artifact:compare
~~~

So sánh cục bộ là bước kiểm tra cơ bản. Để xác nhận độc lập mạnh hơn, cần rebuild trong môi trường khác nhưng giữ nguyên source và build instructions.

### Gradle

Gradle 9 mặc định tạo archive với file order tái lập và timestamp cố định. Với bản cũ, kiểm tra cấu hình của Jar/Zip task:

~~~kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Các yếu tố khác ảnh hưởng reproducibility gồm JDK vendor/version, Wrapper version, plugin/dependency version, generated source, locale, timezone, environment variable và timestamp/đường dẫn tuyệt đối nhúng vào output.

Pin dependency, dùng wrapper, toolchain và build container đã xác định. Đừng thêm timestamp hoặc build number động vào nội dung archive nếu cần byte-for-byte reproducibility.

## 13. Publish artifact lên repository

Artifact repository lưu binary và metadata để project hoặc deployment pipeline khác sử dụng. Ví dụ gồm Maven Central, Nexus Repository, Artifactory, GitHub Packages và repository nội bộ.

Maven dùng distributionManagement trong POM để khai báo repository đích:

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

Credential được cấu hình riêng trong Maven settings.xml, với server id khớp id trong POM. CI nên lấy credential từ secret manager hoặc secret variables.

Khi release đã được verify:

~~~bash
mvn deploy
~~~

Deploy Plugin publish artifact, POM và các artifact đính kèm lên remote repository. Không đặt username/password trực tiếp trong pom.xml.

Maven Central hiện dùng Central Portal publishing flow. Không giả định quy trình deploy cũ tới OSSRH vẫn áp dụng; hãy dùng hướng dẫn publishing hiện hành của Sonatype và plugin được hỗ trợ.

Gradle Maven Publish Plugin tạo Maven publication từ Java component và publish tới Maven-compatible repository:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}
group = 'com.acme'
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
}
~~~

Repository URL và authentication được cấu hình trong publishing.repositories. Không hardcode credential trong build.gradle; dùng Gradle properties hoặc CI secrets.

Release repository nên giữ version bất biến. Snapshot repository dùng cho bản phát triển có thể cập nhật theo policy. Không upload hai binary khác nhau dưới cùng release coordinates. Nếu release có lỗi, tăng version và publish bản mới.

## 14. jlink và jpackage cho ứng dụng tự chứa runtime

JAR thường yêu cầu người dùng có Java runtime phù hợp. Nếu cần gói runtime cùng ứng dụng, có thể dùng JDK packaging tools.

jlink tạo runtime image tùy chỉnh từ module ứng dụng và các module phụ thuộc:

~~~bash
jlink --module-path mods --add-modules com.acme.app --output build/runtime
~~~

jlink cần module path có module ứng dụng và các module cần thiết. Nhà phát triển chịu trách nhiệm cập nhật runtime image khi cần cập nhật JDK hoặc security patch.

jpackage nhận ứng dụng đã build và tạo application image hoặc native installer:

~~~bash
jpackage --type app-image --name ArtifactDemo --input target/package-input --main-jar artifact-demo.jar --main-class com.acme.ArtifactDemo
~~~

Thư mục input cần chứa main JAR và dependency cần thiết. Nếu ứng dụng dùng dependency ngoài, phải đưa chúng vào input directory và cấu hình đúng classpath/runtime.

| Nền tảng | Định dạng |
|---|---|
| Windows | exe, msi |
| Linux | deb, rpm |
| macOS | pkg, dmg |

jpackage tạo runtime bằng jlink nếu không được truyền runtime image có sẵn. Việc tạo installer cần thực hiện trên nền tảng đích và có thể cần công cụ bổ sung như WiX trên Windows hoặc Xcode tools trên macOS.

Nếu đóng gói ứng dụng dùng ServiceLoader, kiểm tra service provider modules trong runtime image. Với JDK 25+, jpackage không tự include service bindings mặc định; có thể cần truyền jlink option --bind-services khi ứng dụng phụ thuộc cơ chế service binding.

## 15. Artifact trong pipeline CI/CD

~~~text
Checkout source
      |
      v
Resolve pinned toolchain and dependencies
      |
      v
Compile + unit tests
      |
      v
Package JAR/WAR/distribution
      |
      v
Verify archive + smoke test
      |
      v
Security scan + SBOM
      |
      v
Checksum + signature + provenance
      |
      v
Publish immutable version
      |
      v
Deploy to staging
      |
      v
Promote same artifact digest
      |
      v
Production
~~~

Quy tắc pipeline:

1. Build từ commit đã xác định.
2. Dùng Maven Wrapper hoặc Gradle Wrapper.
3. Pin JDK toolchain và plugin/dependency version.
4. Chạy test trước khi publish.
5. Kiểm tra artifact sau khi package.
6. Tạo checksum và SBOM.
7. Ký artifact theo policy.
8. Upload vào repository với version duy nhất.
9. Lưu artifact reference và digest trong release metadata.
10. Deploy staging bằng artifact đã publish.
11. Sau khi staging đạt, promote cùng artifact sang production.
12. Không build lại binary khi promote.

CI system thường có chức năng upload artifact để chia sẻ file giữa các job hoặc lưu build output ngắn hạn. Artifact repository chuyên dụng có versioning, dependency metadata, retention và quyền truy cập phù hợp cho phân phối dài hạn. Không nhầm CI job artifact với release repository vì mỗi nơi có retention và chính sách truy cập khác nhau.

## 16. Troubleshooting khi đóng gói artifact

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tạo được JAR | Compile/test/package thất bại | Đọc lỗi Maven/Gradle và sửa phase đầu tiên bị lỗi |
| JAR thiếu resource | Resource nằm sai thư mục hoặc bị exclude | Đặt trong src/main/resources và kiểm tra archive |
| java -jar báo no main manifest attribute | Manifest thiếu Main-Class | Cấu hình Main-Class trong manifest |
| ClassNotFoundException khi chạy | Thin JAR thiếu dependency runtime | Tạo distribution hoặc shaded JAR |
| NoClassDefFoundError | Dependency thiếu hoặc version conflict | Kiểm tra runtime dependency tree |
| ServiceLoader không tìm thấy provider | META-INF/services bị mất khi shading | Dùng ServicesResourceTransformer |
| SecurityException khi dùng shaded JAR | Signature file dependency cũ còn trong archive | Loại signature file cũ và ký artifact cuối nếu cần |
| JAR lớn bất thường | Gói nhầm dependency, test data hoặc resource | Kiểm tra jar --list và dependency graph |
| Version trong file name sai | Build version và release version không đồng bộ | Xác minh coordinates và pipeline variable |
| Không publish được | Repository URL, quyền hoặc credential sai | Kiểm tra settings.xml, server id và CI secrets |
| Publish cùng version bị từ chối | Release repository áp dụng immutability | Tăng version và phát hành bản mới |
| Checksum không khớp | File hỏng hoặc artifact đã thay đổi | Tải lại từ nguồn tin cậy và xác minh digest |
| Chữ ký không hợp lệ | Archive bị thay đổi sau khi ký hoặc key không đúng | Chỉ ký sau bước package cuối và xác minh certificate |
| Build lại cho ra hash khác | Timestamp, file order hoặc môi trường không ổn định | Kiểm tra reproducible build, toolchain và plugin |
| Installer thiếu module | Runtime image thiếu dependency/module/service binding | Kiểm tra module graph và jlink options |
| Artifact chạy trên máy build nhưng lỗi production | Runtime/JDK/OS/dependency khác nhau | Smoke test trên môi trường gần production |

## 17. Quy trình đóng gói artifact có thể tái lập

1. Chọn loại artifact theo cách ứng dụng được sử dụng.
2. Chốt groupId, artifactId, version và classifier.
3. Pin JDK, Maven/Gradle Wrapper, plugin và dependency.
4. Xác định Java release mục tiêu bằng compiler release/toolchain.
5. Chạy validate, compile và test.
6. Package đúng loại JAR, WAR, EAR hoặc distribution.
7. Kiểm tra manifest, module descriptor và resource.
8. Xác nhận dependency runtime có thể được resolve.
9. Chạy jar --validate và smoke test artifact.
10. Scan dependency, license và nội dung nhạy cảm.
11. Tạo SBOM, checksum và chữ ký theo policy.
12. Publish release version vào repository.
13. Lưu digest và provenance của binary.
14. Deploy staging từ đúng artifact đã publish.
15. Promote cùng digest lên production sau khi kiểm thử đạt.
16. Giữ artifact và metadata theo retention policy.

## 18. Ghi nhớ

- Artifact là binary đầu ra có thể phân phối của quá trình build.
- JAR chứa class/resource; Main-Class giúp JAR có entry point nhưng không tự đóng gói dependency.
- Thin JAR phù hợp library; fat/shaded JAR gom dependency; distribution ZIP/TAR kèm script và lib.
- WAR và EAR dành cho mô hình triển khai web/enterprise tương ứng.
- jlink tạo custom runtime image; jpackage tạo application image hoặc installer.
- Maven package tạo artifact; verify chạy kiểm tra; install vào local repository; deploy publish lên remote repository.
- Gradle Java Plugin tạo JAR; Application Plugin tạo distribution có dependency và start script.
- Artifact coordinates gồm groupId, artifactId, version, classifier và type.
- Release version nên bất biến; khi sửa lỗi hãy phát hành version mới.
- Kiểm tra nội dung JAR, manifest, dependency và smoke test sau khi package.
- Shade phải xử lý resource trùng, service descriptor và signature file.
- Checksum kiểm tra nội dung; chữ ký xác thực nguồn gốc; provenance ghi lại quá trình build.
- Reproducible build giúp so sánh binary được tạo lại từ cùng source và build environment.
- Không chứa secret hoặc file local trong artifact.
- Build một lần, kiểm thử và triển khai cùng một binary qua các môi trường.

## Tài liệu tham khảo chính thức

- [JAR File Specification — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)
- [The jar Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [Introduction to the Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle)
- [Maven JAR Plugin — Usage and Manifest Customization](https://maven.apache.org/plugins/maven-jar-plugin/usage.html)
- [Apache Maven Shade Plugin — Usage](https://maven.apache.org/components/plugins/maven-shade-plugin/usage.html)
- [Maven Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/)
- [Gradle Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
- [Gradle Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html)
- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [The jpackage Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Packaging Overview — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [Sonatype Central — Immutability of Published Components](https://central.sonatype.org/publish/requirements/immutability/)