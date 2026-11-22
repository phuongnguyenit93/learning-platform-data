# Quản lý version của Java artifact

**Version artifact** là phiên bản được gán cho một thành phần phần mềm đã build và phát hành, chẳng hạn JAR, WAR, thư viện, ứng dụng desktop hoặc installer. Version giúp người dùng nhận biết nội dung thay đổi, giúp build tool tìm đúng dependency, giúp hệ thống phân phối chọn bản cần cài và giúp nhóm phát hành truy vết artifact về source commit.

Một dự án Java thường có nhiều loại version cùng lúc: version của public API, version Maven/Gradle, version ghi trong JAR manifest, version ứng dụng, version native package, version của Java runtime và build identifier của CI. Các giá trị này có quan hệ với nhau nhưng phục vụ các mục đích khác nhau. Cần định nghĩa một nguồn version chuẩn và quy tắc ánh xạ rõ ràng giữa chúng.

Bài này trình bày Semantic Versioning, Maven coordinates và SNAPSHOT, Gradle project/archive version, JAR manifest metadata, jpackage package version, Git tags, dependency resolution, CI release process và cách kiểm tra version của artifact đã build.

## 1. Version của artifact có ý nghĩa gì?

Version trả lời một số câu hỏi:

- Đây là bản phát hành nào?
- Public API có thay đổi tương thích ngược không?
- Dependency nào có thể sử dụng artifact này?
- Artifact này được build từ source revision nào?
- Installer có thể nâng cấp bản cài trước đó không?
- Người vận hành đang chạy đúng bản đã phát hành hay không?

Một file tên version-demo.jar chưa đủ để xác định duy nhất nội dung. Cần xem thêm groupId, artifactId, version, classifier, repository, checksum và provenance.

Ví dụ một thư viện:

~~~text
groupId:    com.acme.platform
artifactId: customer-client
version:    2.4.1
packaging:  jar
~~~

Maven coordinate đầy đủ là:

~~~text
com.acme.platform:customer-client:2.4.1
~~~

Một ứng dụng desktop có thể có version 2.4.1, trong khi nó được build bằng JDK 24, Maven 3.9.12 và installer revision 3. Đây là những thông tin khác nhau:

| Giá trị | Ví dụ | Ý nghĩa |
|---|---|---|
| Application version | 2.4.1 | Phiên bản chức năng của ứng dụng |
| Library/API version | 2.4.1 | Phiên bản public API của thư viện |
| Maven/Gradle project version | 2.4.1 | Version trong hệ thống build/publish |
| JAR Implementation-Version | 2.4.1 | Version metadata trong manifest |
| Installer/package revision | 3 | Lần đóng gói hoặc revision theo package format |
| Java runtime version | 24.0.2 | Phiên bản JVM được dùng hoặc bundle |
| Build identifier | 184 | Một lần chạy CI cụ thể |
| Git revision | abc1234 | Commit source tạo ra artifact |

Không dùng Java runtime version thay cho application version. Ứng dụng version 2.4.1 có thể chạy trên Java 17, 21 hoặc 24 tùy yêu cầu tương thích.

## 2. Semantic Versioning (SemVer)

Semantic Versioning 2.0.0 là quy tắc gán version dựa trên thay đổi của public API. Dạng version ổn định:

~~~text
MAJOR.MINOR.PATCH
~~~

- **MAJOR:** tăng khi có thay đổi không tương thích ngược trong public API.
- **MINOR:** tăng khi bổ sung chức năng tương thích ngược.
- **PATCH:** tăng khi sửa lỗi tương thích ngược.

Ví dụ:

| Thay đổi | Version cũ | Version mới |
|---|---|---|
| Sửa lỗi không làm thay đổi API | 2.4.1 | 2.4.2 |
| Thêm method public tương thích ngược | 2.4.1 | 2.5.0 |
| Xóa hoặc đổi chữ ký API public | 2.4.1 | 3.0.0 |

Khi tăng MINOR, PATCH được đặt lại 0. Khi tăng MAJOR, MINOR và PATCH được đặt lại 0.

### Cần định nghĩa public API trước

SemVer chỉ có ý nghĩa khi dự án xác định rõ public API. API có thể bao gồm:

- Public classes, interfaces, constructors và methods.
- Public method signatures, checked exceptions và return types.
- Public configuration keys hoặc file formats.
- REST/IPC contracts nếu artifact cung cấp service.
- Các hành vi được tài liệu hóa mà người dùng dựa vào.

Một thay đổi có thể phá vỡ tương thích dù method signature không đổi. Ví dụ, method trước đây chấp nhận null nhưng bản mới ném exception; hoặc thay đổi default behavior làm ứng dụng downstream không còn hoạt động.

Không nên tăng PATCH chỉ vì diff code nhỏ. Hãy đánh giá tác động đối với contract mà người dùng đã dựa vào.

### Version 0.x

Theo SemVer, MAJOR bằng 0 dùng cho giai đoạn phát triển ban đầu. Public API chưa được xem là ổn định và có thể thay đổi bất cứ lúc nào.

Ví dụ:

~~~text
0.3.0
0.4.0
0.4.1
1.0.0
~~~

Khi phát hành 1.0.0, dự án tuyên bố public API đã đạt mức ổn định theo chính sách tương thích của mình.

### Pre-release version

Có thể gắn nhãn bản thử nghiệm sau PATCH bằng dấu gạch ngang:

~~~text
2.5.0-alpha.1
2.5.0-beta.2
2.5.0-rc.1
2.5.0
~~~

Với cùng MAJOR.MINOR.PATCH, pre-release có độ ưu tiên thấp hơn bản phát hành chính thức. Ví dụ:

~~~text
2.5.0-alpha.1 < 2.5.0-beta.1
2.5.0-beta.1 < 2.5.0-rc.1
2.5.0-rc.1 < 2.5.0
~~~

Pre-release identifier chỉ gồm ASCII chữ, số và dấu gạch ngang; numeric identifier không được có số 0 ở đầu, trừ chính giá trị 0.

Dùng alpha cho thử nghiệm sớm, beta cho kiểm thử rộng hơn và rc khi dự kiến nội dung đã sẵn sàng phát hành nếu không còn lỗi chặn.

### Build metadata

SemVer cho phép metadata sau dấu cộng:

~~~text
2.5.0+build.184
2.5.0-rc.1+sha.abc1234
~~~

Build metadata giúp truy vết build nhưng **không làm thay đổi version precedence**. Hai version chỉ khác phần metadata sau dấu cộng có cùng độ ưu tiên theo SemVer.

Nếu repository hoặc package manager không xử lý SemVer 2 đầy đủ, hãy giữ build number và Git SHA trong manifest/provenance riêng thay vì đưa dấu cộng vào version coordinate.

### Version đã phát hành phải bất biến

Một khi version release đã được publish, nội dung artifact của version đó không được thay thế bằng binary khác. Nếu cần sửa, phát hành version mới.

Ví dụ, nếu 2.4.1 đã được phát hành nhưng phát hiện lỗi, tạo 2.4.2. Không upload lại một JAR khác dưới cùng coordinate 2.4.1. Điều này bảo vệ cache, checksum, chữ ký và khả năng tái lập của dependency graph.

Tham khảo quy tắc đầy đủ tại [Semantic Versioning 2.0.0](https://semver.org/).

## 3. Version trong Maven

Maven nhận diện artifact bằng ba thành phần chính:

~~~text
groupId:artifactId:version
~~~

Ví dụ:

~~~xml
<groupId>com.acme.platform</groupId>
<artifactId>customer-client</artifactId>
<version>2.4.1</version>
<packaging>jar</packaging>
~~~

- groupId định danh namespace của tổ chức hoặc dự án.
- artifactId định danh component.
- version định danh bản cụ thể của component.

Các giá trị này xác định đường dẫn artifact trong Maven repository và được dùng khi khai báo dependency.

### Khai báo version trong pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.platform</groupId>
    <artifactId>customer-client</artifactId>
    <version>2.4.1</version>
    <packaging>jar</packaging>
</project>
~~~

Build:

~~~bash
mvn clean package
~~~

Tên JAR mặc định:

~~~text
target/customer-client-2.4.1.jar
~~~

Maven POM Reference mô tả GAV là tọa độ xác định artifact trong repository. Xem [Maven POM Reference — Maven Coordinates](https://maven.apache.org/pom.html).

### SNAPSHOT là gì?

Một version kết thúc bằng -SNAPSHOT biểu thị bản phát triển chưa phải release bất biến:

~~~xml
<version>2.5.0-SNAPSHOT</version>
~~~

Khi deploy snapshot lên repository hỗ trợ Maven snapshot metadata, repository có thể lưu artifact với timestamp và build number duy nhất. Consumer khai báo version 2.5.0-SNAPSHOT sẽ dùng metadata để tìm snapshot hiện hành theo chính sách update.

Ví dụ một bản lưu nội bộ có thể có tên dạng:

~~~text
customer-client-2.5.0-20261110.103015-4.jar
~~~

Tên timestamp cụ thể do repository tạo, không nên tự đặt bằng tay.

Dùng SNAPSHOT trong quá trình phát triển tích hợp. Khi phát hành chính thức, chuyển sang version release:

~~~text
2.5.0-SNAPSHOT  ->  2.5.0
~~~

Không dùng SNAPSHOT cho dependency production cần tái lập vì cùng coordinate có thể resolve ra nội dung khác theo thời gian.

### Dependency declaration

Một ứng dụng sử dụng thư viện:

~~~xml
<dependency>
    <groupId>com.acme.platform</groupId>
    <artifactId>customer-client</artifactId>
    <version>2.4.1</version>
</dependency>
~~~

Nên khai báo version rõ ràng hoặc quản lý tập trung bằng dependencyManagement/BOM. Tránh dùng version range rộng nếu không có chính sách kiểm soát vì dependency resolution có thể chọn một bản mới hơn dự kiến.

Kiểm tra dependency graph:

~~~bash
mvn dependency:tree
~~~

Nếu có nhiều version của cùng một artifact qua transitive dependencies, Maven mediation chọn version theo quy tắc dependency graph và dependency management. Hãy kiểm tra cây dependency trước khi override.

### Maven version ordering không đồng nhất hoàn toàn với SemVer 2

Maven có thuật toán so sánh version riêng. Dù các version thông thường thường có thứ tự gần với SemVer, Maven POM Reference ghi rõ thuật toán version ordering không tương thích đầy đủ với SemVer 2.0.0; dấu cộng và build metadata không được xử lý theo quy tắc precedence của SemVer 2, và so sánh qualifier không phân biệt hoa thường.

Vì vậy:

- Không giả định mọi chuỗi version hợp lệ SemVer đều có thứ tự giống Maven.
- Tránh dựa vào build metadata có dấu cộng trong Maven coordinates.
- Không so sánh version bằng String.compareTo().
- Dùng Maven version-aware APIs hoặc dependency resolver khi cần so sánh Maven versions.

Tham khảo [Maven Version Order Specification](https://maven.apache.org/pom.html#version-order-specification).

## 4. Version trong Gradle

Gradle sử dụng thuộc tính project version để định danh project khi publish và thường dùng làm phần version trong tên archive.

Trong build.gradle:

~~~groovy
plugins {
    id 'java'
}

group = 'com.acme.platform'
version = '2.4.1'
~~~

Sau khi chạy:

~~~bash
./gradlew clean jar
~~~

Tên JAR mặc định thường là:

~~~text
build/libs/<project-name>-2.4.1.jar
~~~

### Tùy chỉnh archive name

Gradle archive task có các thuộc tính:

- archiveBaseName: phần tên chính.
- archiveVersion: phần version.
- archiveClassifier: hậu tố phân biệt loại artifact.
- archiveExtension: phần mở rộng.

Ví dụ:

~~~groovy
tasks.named('jar', Jar) {
    archiveBaseName = 'customer-client'
    archiveVersion = project.version.toString()
    archiveClassifier = 'desktop'
}
~~~

Kết quả:

~~~text
build/libs/customer-client-2.4.1-desktop.jar
~~~

Classifier có thể phân biệt sources, javadoc, platform-specific bundle hoặc biến thể nội dung. Classifier không thay thế version và không nên dùng để biểu diễn một thay đổi API.

Gradle tài liệu hóa archiveVersion mặc định lấy từ project.version; xem [Gradle Working With Files — Archive Tasks](https://docs.gradle.org/current/userguide/working_with_files.html).

### Đưa version vào publication

Khi dùng Maven Publish Plugin, version của publication cần nhất quán với project version:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.acme.platform'
version = '2.4.1'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            groupId = project.group.toString()
            artifactId = 'customer-client'
            version = project.version.toString()
        }
    }
}
~~~

Gradle có thể publish POM và Gradle Module Metadata. Consumer dùng metadata này để giải quyết dependency, variant và artifact.

### Tránh dynamic dependency version trong release build

Các khai báo như:

~~~groovy
implementation 'com.acme:library:2.+'
~~~

có thể resolve ra version khác ở những thời điểm khác nhau. Release build nên dùng version cố định hoặc dependency constraints/locking đã được kiểm soát.

Kiểm tra dependency:

~~~bash
./gradlew dependencies
~~~

Xem dependency của một configuration cụ thể:

~~~bash
./gradlew dependencyInsight --dependency customer-client --configuration runtimeClasspath
~~~

Dùng dependency locking nếu cần giữ chính xác phiên bản đã resolve giữa các lần build và CI.

## 5. Ghi version vào JAR manifest

Tên file JAR có thể bị đổi khi copy hoặc rename. Vì vậy, nên ghi version metadata vào manifest của JAR.

Các thuộc tính thường dùng:

| Manifest attribute | Ý nghĩa |
|---|---|
| Manifest-Version | Phiên bản định dạng manifest, thường là 1.0 |
| Implementation-Title | Tên implementation |
| Implementation-Version | Version của implementation/artifact |
| Implementation-Vendor | Nhà cung cấp implementation |
| Specification-Title | Tên specification |
| Specification-Version | Version của specification/API contract |
| Specification-Vendor | Nhà cung cấp specification |
| Build-Revision | Thuộc tính tùy chỉnh có thể chứa Git SHA |

**Manifest-Version không phải application version.** Ví dụ, một JAR có Manifest-Version 1.0 nhưng Implementation-Version 2.4.1 là hoàn toàn bình thường.

JAR File Specification định nghĩa Implementation-Version và Specification-Version là metadata cho package versioning. Xem [JAR File Specification — Main Attributes](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html).

### Cấu hình Maven JAR Plugin

Trong pom.xml:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <configuration>
                <archive>
                    <manifest>
                        <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
                        <addDefaultSpecificationEntries>true</addDefaultSpecificationEntries>
                    </manifest>
                    <manifestEntries>
                        <Build-Revision>abc1234</Build-Revision>
                    </manifestEntries>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Với POM có version 2.4.1, Maven JAR Plugin ghi Implementation-Version và các metadata tương ứng vào manifest. Build revision có thể được truyền từ CI thay vì hard-code.

### Cấu hình Gradle JAR manifest

Trong build.gradle:

~~~groovy
version = '2.4.1'

tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Implementation-Title': project.name,
            'Implementation-Version': project.version.toString(),
            'Implementation-Vendor': 'Acme Corporation',
            'Specification-Version': '2.4',
            'Build-Revision': 'abc1234'
        )
    }
}
~~~

Dùng một nguồn version chuẩn để đặt project.version, archiveVersion và Implementation-Version. Không duy trì các giá trị độc lập dễ lệch nhau.

### Đọc version từ Java runtime

Java Package API có thể đọc package metadata được ghi trong manifest.

File **VersionInfo.java**:

~~~java
package com.acme.version;

public final class VersionInfo {
    public static void main(String[] args) {
        Package p = VersionInfo.class.getPackage();

        System.out.println(
            "Implementation-Title=" + p.getImplementationTitle()
        );
        System.out.println(
            "Implementation-Version=" + p.getImplementationVersion()
        );
    }
}
~~~

Nếu JAR manifest có:

~~~text
Implementation-Title: version-demo
Implementation-Version: 2.4.1
~~~

Chạy:

~~~bash
java -cp target/version-demo-2.4.1.jar com.acme.version.VersionInfo
~~~

Stdout:

~~~text
Implementation-Title=version-demo
Implementation-Version=2.4.1
~~~

Nếu chạy class trực tiếp từ thư mục classes hoặc một môi trường không có manifest metadata, getImplementationVersion() có thể trả về null. Ứng dụng nên xử lý trường hợp đó, ví dụ hiển thị unknown hoặc dùng resource build-time đã được tạo rõ ràng.

### Main-Class là thuộc tính khác

Implementation-Version chỉ cung cấp metadata. Nó không khai báo entry point.

Nếu muốn chạy bằng:

~~~bash
java -jar app.jar
~~~

JAR cần có Main-Class trong manifest. Có thể khai báo bằng Maven JAR Plugin, Gradle manifest hoặc tùy chọn jar --main-class. Không nhầm Main-Class với Implementation-Version.

## 6. Phân biệt application version, artifact version và Java version

Một dự án có thể phát hành nhiều thành phần:

~~~text
customer-client       2.4.1
customer-server       5.7.0
desktop-application   3.2.4
installer-package     3.2.4
Java runtime          24.0.2
build number          184
~~~

Không nhất thiết tất cả module có cùng version. Một thư viện có thể phát hành độc lập với ứng dụng sử dụng nó.

Nên xác định:

- Version của API/library: thay đổi theo public contract của library.
- Version ứng dụng: thay đổi theo chức năng và hành vi sản phẩm.
- Version installer: theo phiên bản sản phẩm mà installer cài đặt.
- Package revision: theo quy ước native package manager nếu có.
- Java runtime version: JDK/JRE được dùng để compile hoặc bundle.
- Build identifier: xác định lần chạy pipeline cụ thể.

### Java target version không phải artifact version

Ví dụ Maven compiler:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Giá trị này xác định Java API và class-file target. Nó không có nghĩa artifact version là 17.

Một artifact có thể có:

~~~text
Implementation-Version: 2.4.1
Build-Jdk-Spec: 24
Java release target: 17
~~~

Điều này có nghĩa artifact version 2.4.1 được build trên JDK 24 và biên dịch tương thích Java 17 theo cấu hình release.

### Multi-release JAR

Multi-release JAR có thể chứa class khác nhau cho các Java release trong các thư mục:

~~~text
META-INF/versions/9/
META-INF/versions/17/
META-INF/versions/21/
~~~

Manifest khai báo:

~~~text
Multi-Release: true
~~~

Đây là cách một artifact hỗ trợ nhiều Java runtime version trong cùng một JAR. Các con số 9, 17, 21 là Java platform release của class/resource, không phải version phát hành của artifact.

## 7. Version trong installer bằng jpackage

jpackage có tùy chọn:

~~~text
--app-version
~~~

Option này xác định version của application và/hoặc native package. Ví dụ:

~~~bash
jpackage --type app-image --input input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --app-version 2.4.1 --dest dist
~~~

Version được đưa vào metadata và cách đặt tên package theo nền tảng. Tài liệu JDK mô tả --app-version là version của application/package; xem [Oracle JDK 24 jpackage Guide](https://docs.oracle.com/en/java/javase/24/jpackage/index.html).

### Giữ version đầy đủ trong manifest

Một số native package manager có giới hạn hoặc quy tắc version riêng. Vì vậy, hãy:

1. Giữ version sản phẩm theo SemVer trong release metadata.
2. Ghi full version vào JAR manifest.
3. Truyền version phù hợp với package format cho --app-version.
4. Nếu cần, lưu pre-release label hoặc build metadata trong release notes/provenance.
5. Kiểm tra metadata thực tế của package sau khi tạo.

Không giả định mọi native package format xử lý mọi chuỗi SemVer giống nhau.

### Giữ package identity ổn định

Version thay đổi qua từng release, nhưng identity của sản phẩm thường cần ổn định.

- Windows: giữ --win-upgrade-uuid cho cùng một sản phẩm và upgrade line.
- macOS: giữ --mac-package-identifier ổn định.
- Linux: giữ package name ổn định; tăng package version và revision theo quy tắc distro.

Không tạo upgrade UUID mới cho mỗi version nếu mong muốn installer nhận diện và nâng cấp bản cũ.

### Package revision khác application version

Trên Linux, jpackage có --linux-app-release để đặt release/revision trong RPM spec hoặc Debian control file. Đây có thể là revision của quá trình đóng gói, trong khi version ứng dụng vẫn giữ nguyên.

Ví dụ một bản rebuild package do sửa metadata có thể giữ application version 2.4.1 nhưng tăng package revision theo chính sách phát hành của tổ chức.

## 8. Quản lý version bằng Git tag và CI

Git tag giúp liên kết source revision với version phát hành.

Ví dụ:

~~~bash
git tag -a v2.4.1 -m "Release 2.4.1"
git push origin v2.4.1
~~~

CI có thể lấy tag để xác định release version:

~~~bash
git describe --tags --always
~~~

Quy trình release đề xuất:

1. Merge code đã review vào nhánh release/main.
2. Chạy test, API compatibility check và dependency verification.
3. Xác định version theo thay đổi public API.
4. Tạo annotated Git tag.
5. Build artifact từ đúng commit tag.
6. Ghi version và Git SHA vào manifest/provenance.
7. Tạo checksum và chữ ký.
8. Publish artifact vào release repository.
9. Lưu release notes và dependency metadata.
10. Không sửa artifact đã phát hành; mọi thay đổi tạo version mới.

### Tránh lấy version từ thời điểm build

Không dùng timestamp hiện tại làm version release chính. Hai lần build cùng source có thể tạo hai tên artifact khác nhau dù nội dung không thay đổi.

Có thể ghi timestamp build trong provenance hoặc log CI. Nếu cần build number, dùng một trường riêng.

### Version và source revision phải khớp

Trước khi release, xác nhận:

- Git tag đúng version.
- Working tree không có thay đổi chưa commit.
- POM/Gradle version khớp tag.
- JAR manifest khớp version.
- Installer metadata khớp version sản phẩm.
- Build revision khớp commit.
- Checksum được tạo từ artifact cuối cùng.

Nếu một giá trị không khớp, dừng release và sửa pipeline hoặc version source trước khi publish.

## 9. Dependency version và tương thích

Version của dependency ảnh hưởng tới API, runtime behavior và khả năng tái lập.

### Pin dependency version

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>com.acme.platform</groupId>
    <artifactId>customer-client</artifactId>
    <version>2.4.1</version>
</dependency>
~~~

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'com.acme.platform:customer-client:2.4.1'
}
~~~

Tránh dynamic versions trong release build nếu không có cơ chế khóa dependency.

### Kiểm tra transitive dependency

Một dependency có thể kéo theo phiên bản khác của cùng library. Dùng:

~~~bash
mvn dependency:tree
~~~

hoặc:

~~~bash
./gradlew dependencyInsight --dependency customer-client --configuration runtimeClasspath
~~~

Nếu version được chọn khác dự kiến, kiểm tra dependency path, constraints, dependencyManagement và exclusion.

### BOM và dependency alignment

BOM giúp quản lý một tập version tương thích:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme.platform</groupId>
            <artifactId>platform-bom</artifactId>
            <version>2.4.1</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Các module sử dụng BOM có thể khai báo dependency mà không phải lặp version ở từng nơi.

Trong Gradle có thể dùng platform hoặc version catalog để quản lý version tập trung. Đối với release build, dependency lock giúp cố định phiên bản đã resolve.

### Không giả định MINOR luôn an toàn trong mọi hệ sinh thái

SemVer quy định ý nghĩa tương thích dựa trên public API do nhà cung cấp công bố. Tuy nhiên, một thư viện có thể không tuân thủ SemVer hoặc có behavior compatibility riêng. Hãy kiểm tra release notes, API diff và test integration trước khi nâng dependency.

## 10. So sánh version đúng cách

Không so sánh version như chuỗi thông thường:

~~~java
"2.10.0".compareTo("2.9.0")
~~~

So sánh từ điển có thể cho kết quả sai vì ký tự '1' đứng trước '9', dù numeric component 10 lớn hơn 9.

Cần dùng parser/comparator theo scheme đã chọn:

- SemVer 2: dùng thư viện tương thích SemVer 2.
- Maven version: dùng Maven ComparableVersion hoặc resolver tương ứng.
- OSGi version: dùng quy tắc OSGi.
- Native package version: dùng comparator của package manager.

Không dùng một comparator cho mọi loại version. Ví dụ, Maven version ordering không hoàn toàn tương thích SemVer 2.

### Ví dụ thứ tự SemVer

~~~text
1.9.0 < 1.10.0
2.0.0-alpha < 2.0.0-beta
2.0.0-beta < 2.0.0-rc.1
2.0.0-rc.1 < 2.0.0
~~~

Build metadata không ảnh hưởng precedence:

~~~text
2.0.0+build.10
2.0.0+build.11
~~~

Hai version này có cùng precedence theo SemVer. Nếu cần phân biệt build cụ thể, dùng Git SHA hoặc build identifier bên cạnh version.

## 11. Thực hành: kiểm tra version trong Maven JAR

Tạo project:

~~~text
version-demo/
├── pom.xml
└── src/main/java/com/acme/version/VersionInfo.java
~~~

File **VersionInfo.java**:

~~~java
package com.acme.version;

public final class VersionInfo {
    public static void main(String[] args) {
        Package p = VersionInfo.class.getPackage();

        System.out.println(
            "Implementation-Title=" + p.getImplementationTitle()
        );
        System.out.println(
            "Implementation-Version=" + p.getImplementationVersion()
        );
    }
}
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>version-demo</artifactId>
    <version>2.4.1</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
                            <addDefaultSpecificationEntries>true</addDefaultSpecificationEntries>
                        </manifest>
                        <manifestEntries>
                            <Build-Revision>example-git-sha</Build-Revision>
                        </manifestEntries>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Build:

~~~bash
mvn clean package
~~~

Artifact được tạo:

~~~text
target/version-demo-2.4.1.jar
~~~

Kiểm tra manifest:

~~~bash
jar --extract --file target/version-demo-2.4.1.jar META-INF/MANIFEST.MF
~~~

Manifest có các trường tương tự:

~~~text
Manifest-Version: 1.0
Implementation-Title: version-demo
Implementation-Version: 2.4.1
Specification-Version: 2.4
Build-Revision: example-git-sha
~~~

Chạy class:

~~~bash
java -cp target/version-demo-2.4.1.jar com.acme.version.VersionInfo
~~~

Stdout:

~~~text
Implementation-Title=version-demo
Implementation-Version=2.4.1
~~~

Nếu chạy trực tiếp từ classes directory, package metadata có thể null vì chưa có manifest. Hãy kiểm tra bằng artifact JAR thực tế.

## 12. Thực hành: kiểm tra version trong Gradle JAR

Cấu trúc source tương tự:

~~~text
version-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/acme/version/VersionInfo.java
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'version-demo'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
}

group = 'com.acme'
version = '2.4.1'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('jar', Jar) {
    archiveBaseName = 'version-demo'
    archiveVersion = project.version.toString()
    archiveClassifier = 'desktop'

    manifest {
        attributes(
            'Implementation-Title': project.name,
            'Implementation-Version': project.version.toString(),
            'Specification-Version': '2.4',
            'Build-Revision': 'example-git-sha'
        )
    }
}
~~~

Build:

~~~bash
./gradlew clean jar
~~~

Artifact:

~~~text
build/libs/version-demo-2.4.1-desktop.jar
~~~

Chạy:

~~~bash
java -cp build/libs/version-demo-2.4.1-desktop.jar com.acme.version.VersionInfo
~~~

Stdout:

~~~text
Implementation-Title=version-demo
Implementation-Version=2.4.1
~~~

Gradle project.version và manifest version được cấu hình từ cùng một giá trị để tránh lệch nhau.

## 13. Release version và reproducible artifact

Một release tốt phải truy vết được về source và có nội dung bất biến.

Ví dụ metadata phát hành:

~~~text
Application-Version: 2.4.1
Artifact: customer-client-2.4.1.jar
Git-Revision: abc1234
Build-Number: 184
JDK: 24.0.2
Maven: 3.9.12
SHA-256: <computed-checksum>
~~~

Trong thực tế, checksum phải được tính từ artifact thật. Không hard-code một giá trị checksum mẫu vào POM hoặc source.

Để artifact reproducible:

- Pin JDK và build tool.
- Pin plugin versions.
- Khóa dependency.
- Chuẩn hóa timestamp nếu archive yêu cầu.
- Không ghi username, hostname hoặc thời gian hiện tại vào artifact nếu không cần.
- Giữ source revision và build metadata.
- Build hai lần từ cùng source trong môi trường kiểm soát rồi so sánh checksum.

Version không thay thế checksum. Hai artifact có cùng version nhưng checksum khác là dấu hiệu cần điều tra.

## 14. Troubleshooting lỗi version artifact

### Tên JAR không khớp version trong POM

Kiểm tra project.version, artifactId, classifier và archive naming configuration. Với Gradle, xem archiveVersion và archiveClassifier. Với Maven, xem finalName và plugin configuration.

### Runtime trả về null khi đọc Implementation-Version

Có thể class đang chạy từ thư mục classes, JAR không có Implementation-Version, hoặc manifest attribute nằm sai section. Kiểm tra:

~~~bash
jar --list --file app.jar
jar --extract --file app.jar META-INF/MANIFEST.MF
~~~

Đảm bảo attribute nằm trong main section của manifest nếu muốn áp dụng cho package.

### java -jar báo no main manifest attribute

Implementation-Version không khai báo main class. Thêm Main-Class bằng Maven/Gradle manifest hoặc jar --main-class, rồi kiểm tra manifest.

### Maven SNAPSHOT không cập nhật như mong đợi

Kiểm tra snapshotRepository, repository updatePolicy, metadata và local cache. SNAPSHOT resolution phụ thuộc metadata của repository; không tự rename một JAR local thành timestamped snapshot.

### Dependency resolve ra version khác

Chạy mvn dependency:tree hoặc Gradle dependencyInsight. Kiểm tra transitive dependency, version constraints, dependencyManagement, BOM và locking.

### Version 2.10 bị xem nhỏ hơn 2.9

Không dùng so sánh chuỗi. Dùng comparator dành cho version scheme tương ứng.

### SemVer prerelease bị xếp thứ tự sai

Kiểm tra parser có hỗ trợ SemVer 2 và quy tắc numeric identifier hay không. Không dùng Maven version comparator như một bộ so sánh SemVer 2 tổng quát.

### Installer version không khớp JAR version

Kiểm tra --app-version, JAR Implementation-Version và metadata release. Tách application version khỏi package revision và Java runtime version.

### Release artifact đã publish cần sửa

Không thay file dưới cùng version release. Tạo version mới, cập nhật dependency và release notes, rồi publish artifact mới.

## 15. Quy trình release version đề xuất

1. Xác định phạm vi thay đổi và public API.
2. Chọn MAJOR, MINOR hoặc PATCH theo compatibility policy.
3. Chốt version trong Maven POM hoặc Gradle project.
4. Kiểm tra dependency versions và Java runtime target.
5. Chạy unit, integration và compatibility tests.
6. Tạo Git tag cho version.
7. Build artifact từ đúng tag/commit.
8. Ghi Implementation-Version và Git revision vào manifest.
9. Đặt version đúng cho application và native installer.
10. Tạo checksum, chữ ký và provenance.
11. Kiểm tra tên file, manifest, GAV và package metadata.
12. Publish vào release repository.
13. Lưu release notes và kết quả verification.
14. Giữ artifact release bất biến.

## 16. Checklist quản lý version artifact

- Đã định nghĩa public API hoặc compatibility contract.
- Có quy tắc MAJOR/MINOR/PATCH rõ ràng.
- Pre-release label được dùng đúng mục đích.
- Build metadata không bị hiểu nhầm là version precedence.
- Maven GAV hoặc Gradle group/name/version nhất quán.
- SNAPSHOT chỉ dùng trong phát triển.
- Release version không bị ghi đè.
- Dependency versions được pin hoặc khóa.
- Không so sánh version bằng String.compareTo().
- Maven version ordering không bị nhầm với SemVer 2.
- JAR manifest có Implementation-Version.
- Manifest-Version không bị nhầm với application version.
- Main-Class được khai báo riêng nếu cần java -jar.
- Package.getImplementationVersion() đã được kiểm tra.
- jpackage --app-version khớp version sản phẩm.
- Package identity ổn định qua các bản nâng cấp.
- Java runtime version được ghi riêng.
- Git tag và build revision truy vết được.
- Checksum được tính từ artifact cuối.
- Release artifact bất biến và có provenance.

## 17. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Artifact version | Version của file/component đã build |
| SemVer | Quy tắc MAJOR.MINOR.PATCH dựa trên public API |
| Major | Thay đổi không tương thích ngược |
| Minor | Chức năng mới tương thích ngược |
| Patch | Sửa lỗi tương thích ngược |
| Pre-release | Bản alpha, beta hoặc release candidate |
| Build metadata | Metadata sau dấu cộng, không ảnh hưởng SemVer precedence |
| GAV | Maven groupId, artifactId, version |
| SNAPSHOT | Bản phát triển thay đổi theo repository metadata |
| Classifier | Hậu tố phân biệt loại artifact |
| Implementation-Version | Version implementation trong JAR manifest |
| Specification-Version | Version của specification/API contract |
| Main-Class | Entry point để chạy JAR bằng java -jar |
| jpackage --app-version | Version của application/native package |
| Package revision | Revision đóng gói theo quy tắc package manager |
| Git tag | Nhãn source revision cho một version |
| Build number | Định danh một lần chạy CI |
| Provenance | Thông tin nguồn và quy trình tạo artifact |
| Immutable release | Artifact đã phát hành không bị thay thế |

Quản lý version artifact tốt bắt đầu bằng một compatibility policy rõ ràng và một nguồn version chuẩn. Đồng bộ Maven/Gradle coordinates, JAR manifest, installer metadata và Git tag; phân biệt version sản phẩm với Java runtime và build number; kiểm tra dependency resolution và giữ release artifact bất biến. Nhờ vậy, người dùng có thể chọn đúng dependency, vận hành đúng bản ứng dụng và truy vết chính xác binary đã phát hành.

## Tài liệu tham khảo

- Semantic Versioning — [Semantic Versioning 2.0.0](https://semver.org/)
- Apache Maven — [POM Reference and Maven Coordinates](https://maven.apache.org/pom.html)
- Apache Maven — [Version Order Specification](https://maven.apache.org/pom.html#version-order-specification)
- Sonatype — [Publishing Requirements and Correct Coordinates](https://central.sonatype.org/publish/requirements/)
- Gradle — [Working With Files and Archive Tasks](https://docs.gradle.org/current/userguide/working_with_files.html)
- Gradle — [Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- Oracle JDK 24 — [JAR File Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html)
- Oracle JDK 24 — [Packaging Tool User's Guide](https://docs.oracle.com/en/java/javase/24/jpackage/index.html)