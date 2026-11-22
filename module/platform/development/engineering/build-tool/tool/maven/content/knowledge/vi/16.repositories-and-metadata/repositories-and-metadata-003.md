# Tệp POM, artifact, checksum và maven-metadata.xml trong Maven

## 1. Bốn khái niệm cần tách biệt

Khi Maven tải một dependency hoặc phát hành một project, repository không chỉ chứa một tệp JAR. Thông thường có **POM descriptor**, **artifact thực tế**, **checksum sidecar** và đôi khi **repository metadata**. Chúng phục vụ những nhiệm vụ khác nhau:

| Loại tệp | Ví dụ | Tác dụng |
| --- | --- | --- |
| **POM artifact** | `catalog-core-1.0.0.pom` | Mô tả Maven project và dependencies |
| **Binary artifact** | `catalog-core-1.0.0.jar` | Chứa class/resources để consumer sử dụng |
| **Checksum** | `catalog-core-1.0.0.jar.sha1` | Mã băm của chính tệp JAR, phục vụ kiểm tra bytes |
| **Repository metadata** | `maven-metadata.xml` | Khám phá versions, plugin prefixes hoặc snapshot timestamps |
| **Chữ ký tách rời** | `catalog-core-1.0.0.jar.asc` | Có thể dùng xác thực publisher bằng public key đáng tin |

**POM không phải JAR. Metadata không phải POM. Checksum không tự xác thực publisher.** Bốn sự phân biệt này giúp chẩn đoán lỗi Maven chính xác hơn nhiều so với giả định mọi file trong cùng thư mục đều có vai trò giống nhau.

Trong bài, nhóm tọa độ `com.example:catalog-core` là **ví dụ giả định**; không khẳng định artifact đó đã được upload lên Maven Central. Dùng Maven 3.9+ và Java 17+ cho bài thực hành cuối.

## 2. Quy tắc chuyển tọa độ GAV thành repository path

Một dependency Maven cơ bản:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.16.0</version>
</dependency>
~~~

Bộ ba `groupId:artifactId:version` là **GAV**. Khi cần một artifact cụ thể, Maven còn xét **extension/type** và **classifier**.

Layout **Maven 2/default** sử dụng ánh xạ:

~~~text
repository-root/
  groupId-thay-dau-cham-bang-dau-gach-cheo/
    artifactId/
      baseVersion/
        artifactId-version.pom
        artifactId-version.extension
        artifactId-version-classifier.extension
~~~

Ví dụ release GAV `com.example:catalog-core:1.0.0` với packaging `jar`:

~~~text
com/
  example/
    catalog-core/
      1.0.0/
        catalog-core-1.0.0.pom
        catalog-core-1.0.0.jar
~~~

Với dependency `org.apache.commons:commons-lang3:3.16.0`, hai relative paths thông thường là:

~~~text
org/apache/commons/commons-lang3/3.16.0/commons-lang3-3.16.0.pom
org/apache/commons/commons-lang3/3.16.0/commons-lang3-3.16.0.jar
~~~

Những đường dẫn này có thể gắn sau URL gốc của repository, ví dụ Maven Central:

~~~text
https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.16.0/commons-lang3-3.16.0.pom
https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.16.0/commons-lang3-3.16.0.jar
~~~

Nhận xét:

- Chỉ phần **groupId** đổi dấu chấm thành thư mục; ví dụ `com.example` → `com/example`.
- Thư mục kế tiếp là **artifactId**, sau đó là **baseVersion**.
- Một tệp không tuân layout không tự được Maven tìm thấy qua GAV dù nó có tồn tại trên server.
- `extension` có thể là `.jar`, `.war`, `.pom`, `.zip`, `.tar.gz`... tùy artifact.
- `classifier` là phần bổ sung như `sources`, `javadoc`, `tests`, chỉ có khi publisher phát hành loại file đó.
- HTTP repository **không cần cung cấp HTML directory listing**: Maven dựng đường dẫn từ tọa độ và dùng metadata cho những thao tác discovery.

**Ngoại lệ cần nhớ:** remote snapshot thường dùng thư mục `1.1.0-SNAPSHOT` nhưng file có tên timestamped `1.1.0-20261110.143000-4`. Điều này không áp dụng cho release đơn giản ở trên.

## 3. POM trong source khác gì POM đã publish?

Project nguồn có file:

~~~text
catalog-core/
├── pom.xml
└── src/main/java/com/example/catalog/App.java
~~~

Khi module được publish hoặc install, repository thường chứa:

~~~text
catalog-core-1.0.0.pom
~~~

Đó là **POM artifact**: descriptor được Maven consumer dùng để hiểu module. Nó thường lấy thông tin từ `pom.xml` của source; nhưng một số quy trình publication có thể xử lý/flatten POM, nên **không nên khẳng định hai file luôn giống hệt từng byte**. Khi debug dependency của một bản đã phát hành, nên đọc bản `.pom` **thực sự nằm trong repository**.

POM cung cấp:

1. **groupId, artifactId, version, packaging** và thông tin về module.
2. **Dependencies** với groupId/artifactId/version/type/scope/classifier khi được khai báo.
3. Thông tin cần thiết để Maven dựng **transitive dependency graph**: dependencies, exclusions, dependency management, parent POM/BOM...
4. Metadata nhà phát hành như name, description, license, SCM/developers nếu được khai báo.
5. Một số cấu hình khác của model Maven.

Maven không mặc định đọc bytecode trong `.jar` để suy luận toàn bộ dependency graph: dependency descriptor chính là **POM**.

### POM có nhưng JAR không tồn tại: chưa chắc repository hỏng

Một project có:

~~~xml
<packaging>pom</packaging>
~~~

có thể là parent/BOM/aggregator. Artifact chính cần publish của nó thường là **POM**, không có main JAR. Ví dụ sử dụng BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>platform-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đoạn XML này là một mảnh POM, không phải chương trình độc lập. Maven dùng **POM của BOM**, chứ không tìm main JAR cho BOM như một thư viện Java.

Nếu POM của một module `packaging=jar` đã có nhưng `.jar` không tồn tại, có thể publisher upload thiếu binary, sai version/classifier, repository proxy cache thiếu hoặc artifact access bị từ chối. Phải kiểm tra **packaging, type, classifier và URL tệp cụ thể**, không chỉ xem metadata.

## 4. Artifact chính và các artifact phụ

Một module JAR có thể được phát hành kèm các file:

~~~text
catalog-core-1.0.0.pom
catalog-core-1.0.0.jar
catalog-core-1.0.0-sources.jar
catalog-core-1.0.0-javadoc.jar
catalog-core-1.0.0-tests.jar
~~~

| Tệp | Nội dung | Có phải luôn có? |
| --- | --- | --- |
| `.pom` | Descriptor Maven | Thường là một phần của publication |
| `.jar` không classifier | JAR chính của packaging `jar` | Thường có sau package/install/deploy |
| `-sources.jar` | Sources cho IDE/người dùng | Không; cần plugin attach sources |
| `-javadoc.jar` | Javadoc | Không; cần plugin tạo/attach |
| `-tests.jar` | Các class kiểm thử nếu được attach | Không; không phải mặc định |
| `.war`, `.zip`, `.tar.gz` | Các loại artifact khác | Tùy packaging và plugin |

Ví dụ một dependency yêu cầu **test JAR**:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>catalog-core</artifactId>
    <version>1.0.0</version>
    <type>test-jar</type>
    <scope>test</scope>
</dependency>
~~~

Maven cần một artifact tests đúng loại/classifier. **Khai báo test-jar không làm Maven tự tạo hoặc publish file đó**; publisher phải tạo attached artifact trước.

Ở publication time, plugins quyết định attached artifacts. Ở consumption time, Maven ánh xạ dependency type/classifier sang extension và đường dẫn phù hợp. Đừng chỉ nhìn “JAR tồn tại” rồi suy ra mọi classifier đều có.

## 5. Checksum sidecar và chữ ký .asc

Một remote repository có thể chứa:

~~~text
catalog-core-1.0.0.jar
catalog-core-1.0.0.jar.sha1
catalog-core-1.0.0.jar.sha256
catalog-core-1.0.0.jar.asc

catalog-core-1.0.0.pom
catalog-core-1.0.0.pom.sha1

maven-metadata.xml
maven-metadata.xml.sha1
~~~

**Checksum đi kèm từng tệp riêng:** hash của JAR khác hash của POM; checksum của metadata cũng không phải checksum của JAR. Tài liệu layout Maven lịch sử nêu `.md5`, `.sha1`; một số repositories cung cấp thêm `.sha256` hoặc `.sha512`. Không được giả định nơi nào cũng có tất cả suffix này.

| Thuật toán | Dung lượng digest | Chiều dài biểu diễn hex |
| --- | ---: | ---: |
| MD5 | 128 bit | 32 ký tự |
| SHA-1 | 160 bit | 40 ký tự |
| SHA-256 | 256 bit | 64 ký tự |
| SHA-512 | 512 bit | 128 ký tự |

Cách kiểm tra checksum:

1. Lấy đúng file artifact.
2. Lấy expected digest của **chính file đó** từ nguồn đáng tin.
3. Tính lại hash trên bytes thực tế.
4. So sánh toàn bộ digest.

Nếu checksum mismatch, có thể file tải dở/hỏng, repo mirror trả bytes khác, sidecar stale, hoặc có thay đổi không được phép. **Không nên tắt checksum policy chỉ để build xanh**.

### Checksum khác authenticity

Checksum tự thân **không xác thực publisher**. Nếu một bên độc hại kiểm soát cả JAR và sidecar, họ có thể công bố cả hai cùng khớp. MD5/SHA-1 còn có điểm yếu collision đã biết nên càng không được dùng làm cơ sở xác thực độc lập.

File `.asc` thường là **OpenPGP detached signature**. Muốn tin vào chữ ký, cần xác minh file bằng public key đáng tin và xác minh đúng người/công ty sở hữu public key ấy. Chỉ thấy `.asc` tồn tại hoặc chỉ thấy chữ ký khớp một public key bất kỳ chưa đủ.

Để bảo đảm nguồn phát hành, cần kết hợp repository access policy, TLS, trusted signing keys, provenance và kiểm soát supply chain phù hợp. **SHA-256 mạnh hơn SHA-1 nhưng vẫn không thay thế kiểm tra nguồn gốc**.

### Tự tính SHA-256

Trên Linux:

~~~bash
sha256sum target/catalog-core-1.0.0.jar
~~~

Trên macOS:

~~~bash
shasum -a 256 target/catalog-core-1.0.0.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -Path "target/catalog-core-1.0.0.jar"
~~~

Giá trị hash cụ thể tùy **nội dung byte** của file JAR được build. Vì timestamp, manifest, compiler hoặc file đầu vào có thể làm bytes khác, không thể đưa một hash cố định rồi cam kết luôn đúng trong mọi môi trường.

## 6. Maven repository metadata: ba cấp G/A/V

Tên file **maven-metadata.xml** không chỉ có một nghĩa. Apache Maven phân biệt ba cấp:

| Cấp | Đường dẫn | Nội dung/khả năng phục vụ |
| --- | --- | --- |
| **G** (group) | `groupId-path/maven-metadata.xml` | Map **plugin prefix** sang plugin artifactId |
| **A/GA** (artifact) | `groupId-path/artifactId/maven-metadata.xml` | Danh sách versions, latest/release/lastUpdated |
| **V** (snapshot) | `groupId-path/artifactId/baseVersion-SNAPSHOT/maven-metadata.xml` | Timestamp, buildNumber, snapshotVersions |

**Metadata là file XML dành cho discovery/resolution, không phải dependency artifact thông thường.** Maven vận hành metadata tự động; nó không thay tệp `.pom` và không chứa binary classes.

### 6.1. G-level: plugin prefix

Đường dẫn ví dụ:

~~~text
org/apache/maven/plugins/maven-metadata.xml
~~~

Ví dụ **minh họa**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
    <plugins>
        <plugin>
            <name>Apache Maven Compiler Plugin</name>
            <prefix>compiler</prefix>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
    </plugins>
</metadata>
~~~

Khi chạy plugin bằng prefix rút gọn, chẳng hạn `mvn compiler:compile`, Maven có thể sử dụng thông tin plugin prefix trong pluginGroups tương ứng để xác định **artifactId**. Metadata này **không phải danh sách versions của mọi dependency trong group**.

### 6.2. A-level: danh sách phiên bản artifact

Ví dụ với artifact **com.example:catalog-core**:

~~~text
com/example/catalog-core/maven-metadata.xml
~~~

XML minh họa (không phải metadata live):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
    <groupId>com.example</groupId>
    <artifactId>catalog-core</artifactId>
    <versioning>
        <latest>1.1.0-SNAPSHOT</latest>
        <release>1.0.0</release>
        <versions>
            <version>0.9.0</version>
            <version>1.0.0</version>
            <version>1.1.0-SNAPSHOT</version>
        </versions>
        <lastUpdated>20261110143000</lastUpdated>
    </versioning>
</metadata>
~~~

Đọc đúng từng trường:

- **groupId/artifactId**: metadata này thuộc artifact nào.
- **versions/version**: các version entries mà repository ghi nhận.
- **latest**: version latest ghi trong metadata; có thể là snapshot, **không có nghĩa stable**.
- **release**: release version ghi nhận, **không bảo đảm tuân SemVer hoặc tương thích API**.
- **lastUpdated**: mốc cập nhật metadata theo dạng UTC **yyyyMMddHHmmss**, không phải hash hay build timestamp của từng JAR.

Metadata danh sách versions hữu ích khi Maven giải quyết **version ranges**, chọn plugin version hoặc cần khám phá những version đang có. Với **version release cố định**, Maven thường có thể dựng path tới POM/JAR mà không cần một lượt quét liệt kê versions.

### 6.3. V-level: metadata của SNAPSHOT

Khi dự án publish version:

~~~xml
<version>1.1.0-SNAPSHOT</version>
~~~

**BaseVersion** là `1.1.0-SNAPSHOT`. Một remote deployment giả định có thể thay phần SNAPSHOT trong **tên file** bằng timestamp/buildNumber:

~~~text
1.1.0-20261110.143000-4
~~~

Thư mục vẫn theo baseVersion:

~~~text
com/example/catalog-core/1.1.0-SNAPSHOT/
    maven-metadata.xml
    catalog-core-1.1.0-20261110.143000-4.pom
    catalog-core-1.1.0-20261110.143000-4.jar
    catalog-core-1.1.0-20261110.143000-4.jar.sha1
~~~

Nội dung metadata minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<metadata>
    <groupId>com.example</groupId>
    <artifactId>catalog-core</artifactId>
    <version>1.1.0-SNAPSHOT</version>
    <versioning>
        <snapshot>
            <timestamp>20261110.143000</timestamp>
            <buildNumber>4</buildNumber>
        </snapshot>
        <lastUpdated>20261110143000</lastUpdated>
        <snapshotVersions>
            <snapshotVersion>
                <extension>pom</extension>
                <value>1.1.0-20261110.143000-4</value>
                <updated>20261110143000</updated>
            </snapshotVersion>
            <snapshotVersion>
                <extension>jar</extension>
                <value>1.1.0-20261110.143000-4</value>
                <updated>20261110143000</updated>
            </snapshotVersion>
        </snapshotVersions>
    </versioning>
</metadata>
~~~

Timestamp **20261110.143000** và buildNumber **4** chỉ minh họa, không khẳng định một artifact đó đã được deploy. `snapshotVersions` có thể chứa entry cho từng extension/classifier, bao gồm sources/javadoc nếu publisher đã attach.

Giải thích trình tự:

1. Consumer yêu cầu version **1.1.0-SNAPSHOT**.
2. Resolver kiểm tra repository metadata theo update policy.
3. Metadata giúp ánh xạ baseVersion sang timestamped file phù hợp.
4. Maven lấy đúng POM/binary theo extension/classifier.
5. Lần deploy sau có thể làm metadata chọn timestamp/buildNumber khác.

Vì snapshot có thể thay đổi theo thời gian, **cùng một POM khai báo SNAPSHOT không đảm bảo hai lần build lấy cùng bytes**. Đối với local `mvn install`, filename thường dùng baseVersion kết thúc bằng `-SNAPSHOT`, khác remote timestamped publication.

## 7. Local repository khác remote repository

Local repository mặc định thường là:

~~~text
~/.m2/repository/
~~~

Nhưng có thể được điều chỉnh trong settings hoặc tham số Maven. Đây là **local cache/artifact store**, không phải source repository Git.

Tên metadata ở remote thường là:

~~~text
maven-metadata.xml
~~~

Khi lưu cache metadata từ remote có ID riêng, local repo có thể chứa:

~~~text
maven-metadata-central.xml
maven-metadata-company-snapshots.xml
~~~

Khi install một artifact cục bộ, có thể có:

~~~text
maven-metadata-local.xml
~~~

Một số tệp hỗ trợ Resolver còn có:

~~~text
_remote.repositories
*.lastUpdated
resolver-status.properties
~~~

Các tệp phụ này có thể ghi nhận repository origin, cache và kết quả resolution. Chúng **không phải mã nguồn hoặc artifact Java**, cũng không phải POM công bố, và không cần có cùng bộ file trên mọi Maven version/installation.

**Đừng sửa metadata local tùy tiện** rồi coi đó là sự thật của remote: một lần refresh có thể ghi đè, còn POM/JAR bytes thật có thể vẫn khác. Khi gặp cached failure, hãy điều tra tọa độ, URL, repository ID, access policy và file bị lỗi trước.

## 8. Package, install và deploy đặt artifact ở đâu?

| Maven phase/lệnh | Kết quả chính | Phạm vi |
| --- | --- | --- |
| **mvn package** | Tạo sản phẩm build thường trong `target/` | Project workspace |
| **mvn install** | Install POM và artifact vào local Maven repo | Máy/runner hiện tại |
| **mvn deploy** | Publish tới remote repository | Cần remote destination và credentials/quyền phù hợp |

Ví dụ với `com.example:catalog-core:1.0.0` packaging jar:

~~~text
mvn package:
  target/catalog-core-1.0.0.jar

mvn install:
  ~/.m2/repository/com/example/catalog-core/1.0.0/
    catalog-core-1.0.0.pom
    catalog-core-1.0.0.jar

mvn deploy:
  remote-repository/com/example/catalog-core/1.0.0/
    catalog-core-1.0.0.pom
    catalog-core-1.0.0.jar
    sidecar checksums / metadata tùy policy
~~~

Với `packaging=pom`, **không có main JAR mặc định**. Với sources/javadoc attached artifacts, những file phụ chỉ được install/deploy nếu plugins thật sự tạo và attach chúng.

**mvn install không làm đồng đội tự tải được JAR qua remote.** Deploy Maven artifact vào repository cũng **không đồng nghĩa triển khai ứng dụng lên máy chủ runtime/Kubernetes**. Maven Deploy Plugin cần repo destination (thường trong `distributionManagement`), quyền truy cập, và configuration phù hợp.

## 9. Ví dụ đầy đủ Java 17 để kiểm tra các tệp

Tạo project sau:

~~~text
catalog-core/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/catalog/
                └── App.java
~~~

Nội dung **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>catalog-core</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nội dung **src/main/java/com/example/catalog/App.java**:

~~~java
package com.example.catalog;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("POM and JAR are different files");
    }
}
~~~

Yêu cầu Maven 3.9+ và JDK 17+; Maven cần giải quyết các plugins nếu chưa có trong cache. Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -version
mvn -B clean package
java -cp target/catalog-core-1.0.0.jar com.example.catalog.App
jar tf target/catalog-core-1.0.0.jar
~~~

**Stdout chính xác của lệnh java**:

~~~text
POM and JAR are different files
~~~

Trong kết quả `jar tf` phải có ít nhất:

~~~text
com/example/catalog/App.class
~~~

JAR còn có thể chứa các entry `META-INF/` và thư mục. Ví dụ không khai báo `Main-Class` trong manifest, nên lệnh `java -cp ... com.example.catalog.App` được dùng thay vì giả định `java -jar` tự chạy.

Tiếp tục:

~~~bash
mvn -B install
~~~

Với local repo mặc định, sau khi install thành công sẽ có các tệp chính:

~~~text
~/.m2/repository/com/example/catalog-core/1.0.0/
  catalog-core-1.0.0.pom
  catalog-core-1.0.0.jar
~~~

Có thể có metadata/tracking files khác. **Đây chỉ là local install**, không phải remote publication.

So sánh checksum của file build và file install trên Linux:

~~~bash
sha256sum target/catalog-core-1.0.0.jar
sha256sum ~/.m2/repository/com/example/catalog-core/1.0.0/catalog-core-1.0.0.jar
~~~

Hai hash sẽ bằng nhau nếu hai file có cùng bytes. Giá trị hash phải được tính thật, không thể hardcode cho mọi lượt build.

## 10. Java 17 tự tính SHA-256, không cần thư viện ngoài

Có thể sử dụng một chương trình thuần Java để kiểm tra checksum. Tạo **Sha256.java** trong một thư mục thử nghiệm độc lập:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class Sha256 {
    private Sha256() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java Sha256 <file>");
            System.exit(2);
        }

        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            byte[] buffer = new byte[8192];
            int n;
            while ((n = input.read(buffer)) != -1) {
                hash.update(buffer, 0, n);
            }
        }
        System.out.println(HexFormat.of().formatHex(hash.digest()));
    }
}
~~~

Từ thư mục chứa **Sha256.java**:

~~~bash
javac Sha256.java
java Sha256 path/to/catalog-core/target/catalog-core-1.0.0.jar
~~~

Stdout là **64 ký tự hex chữ thường**, thay đổi theo bytes thực tế. Code đọc file từng khối, không nạp cả JAR lớn vào RAM. Chương trình **chỉ tính SHA-256**, không tự xác minh chữ ký `.asc` hay xác thực nguồn artifact.

## 11. Maven phân giải một dependency có version cố định như thế nào?

Giả sử trong POM của ứng dụng có:

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.16.0</version>
</dependency>
~~~

Một luồng xử lý khái quát:

1. Maven xây **effective POM** của project, áp dụng parent, profiles và dependencyManagement.
2. Resolver xác định dependency coordinates, type, classifier và phiên bản cần dùng.
3. Với **release version cố định**, Maven có thể dựng path `.pom` và `.jar` từ layout.
4. `.pom` cung cấp metadata để phân giải transitive dependencies.
5. Khi goal cần classpath, Maven tải/cached binary `.jar`.
6. Artifact được kiểm tra và lưu theo repository policy; checksum sidecar có thể được dùng.
7. Compiler/test/plugin sử dụng classpath dựa trên những dependencies đã resolve.

**Sources/Javadoc không tự bắt buộc được tải** chỉ vì main JAR có mặt. Một IDE hoặc plugin có thể yêu cầu attached classifier sau.

Đối với **version range** hoặc **SNAPSHOT**, metadata phục vụ chọn version/timestamp. Với dependency graph có nhiều version của cùng artifact, Maven còn áp dụng quy tắc mediation/dependencyManagement; không thể coi `latest` trong metadata là version tự động được chọn cho mọi application.

## 12. SNAPSHOT, version range và reproducible build

### SNAPSHOT

Một version `1.1.0-SNAPSHOT` trong POM **không phải lời hứa cùng bytes ở mọi lần build**. Snapshot repository có thể nhận bản deploy mới với timestamp/buildNumber khác, và resolver có thể lấy bản mới khi metadata/update policy cho phép.

Nếu cần phát hành production tái tạo được, hạn chế SNAPSHOT trong dependencies đã đóng băng, hoặc lưu chính xác provenance và artifact bytes đã sử dụng.

### Version range

Một dependency dùng range, ví dụ:

~~~xml
<version>[1.0,2.0)</version>
~~~

có thể cần A-level metadata để biết version candidates khả dụng. Khi publisher thêm version mới hoặc metadata cập nhật, cùng một range có thể chọn candidate khác. Ngay cả range `[1.0,2.0)` có thể chứa `2.0-rc1` vì Maven so sánh qualifier này dưới `2.0`; range là điều kiện thứ tự, không phải phép lọc major SemVer đơn giản.

**Cách phòng tránh:** pin versions đã kiểm thử bằng POM/dependencyManagement/BOM, review dependency tree, quản lý plugin/JDK version và biết những input ảnh hưởng artifact output.

## 13. Chẩn đoán lỗi POM, JAR, checksum và metadata

Các lệnh thông dụng từ project thật:

~~~bash
mvn -version
mvn help:effective-pom
mvn dependency:tree
mvn -X dependency:tree
~~~

- `help:effective-pom`: xem POM đã merge, dependencyManagement và plugin config.
- `dependency:tree`: xem dependency graph và version cuối.
- `-X`: debug log có repository URL/ID và thông báo resolution, có thể chứa thông tin nhạy cảm; lọc trước khi chia sẻ.

Thử cập nhật metadata hoặc offline khi có mục đích:

~~~bash
mvn -U dependency:tree
mvn -o dependency:tree
~~~

- `-U`: yêu cầu Maven kiểm tra cập nhật snapshots và metadata theo quy tắc của Maven; **không nâng toàn bộ releases lên latest**.
- `-o`: chạy offline; nếu artifact/plugin chưa có local cache hợp lệ thì có thể thất bại.

| Triệu chứng | Khả năng | Cách xác định |
| --- | --- | --- |
| POM tải được nhưng JAR 404 | POM-only, sai type/classifier hoặc publish thiếu binary | Xem packaging và đúng path của JAR |
| JAR thấy trên server nhưng Maven thiếu POM | Descriptor publication thiếu hoặc mirror/cache không đồng bộ | Kiểm tra `.pom` của version |
| Checksum mismatch | Bytes, sidecar hoặc mirror không khớp | Điều tra nguồn/policy, không bỏ qua xác minh |
| SNAPSHOT vẫn là bản cũ | V-level metadata/cache/update policy chưa đổi | Kiểm tra metadata, repo ID, `-U` phù hợp |
| Không có `-sources.jar` | Attached sources chưa được publish | Không coi là lỗi main JAR mặc định |
| Local build được, CI tải không được | Artifact chỉ mới `mvn install` trên laptop | Publish remote qua pipeline có quyền |
| Plugin prefix không phân giải | G-level plugin metadata hoặc pluginGroups | Xem plugin coordinates đầy đủ |
| Metadata liệt kê version nhưng file thiếu | Metadata stale hoặc deploy dở | Điều tra repository manager |
| Cùng GAV hai mirror trả file hash khác | Content không đồng nhất | Kiểm tra trusted origin/checksum |
| Đổi máy build ra dependency khác | SNAPSHOT, version range, settings/mirror khác | Pin versions, đối chiếu effective POM và tree |

**Đừng tự xóa sạch toàn bộ `~/.m2/repository` khi gặp lỗi**: điều đó tốn cache, có thể ảnh hưởng các build khác, và không sửa một tọa độ sai. Chỉ xử lý cache/metadata có chọn lọc khi đã biết nguyên nhân.

Nếu remote metadata cần sửa, dùng quy trình của repository manager/publisher; sửa tay một file XML không đảm bảo artifacts và sidecar checksums khớp.

## 14. Checklist xem repository đúng cách

1. Ghi đầy đủ **groupId, artifactId, version, extension/type và classifier**.
2. Dựng path theo layout, kiểm tra đúng repository ID/URL.
3. Xem POM descriptor để biết packaging, dependencies và parent/BOM.
4. Xác minh binary artifact có thực sự được publish và đúng classifier.
5. Phân biệt checksum `.md5/.sha1/.sha256` với chữ ký `.asc`.
6. Với danh sách versions, mở **GA-level metadata**.
7. Với plugin prefix, mở **G-level metadata**.
8. Với SNAPSHOT, mở **V-level metadata** và `snapshotVersions`.
9. Nhớ baseVersion snapshot khác filename timestamped remote.
10. Phân biệt remote `maven-metadata.xml` với metadata cache `maven-metadata-<repo-id>.xml` và local metadata.
11. Kiểm tra **package → install → deploy** là các phạm vi khác nhau.
12. Dùng Maven logs, effective POM, dependency tree, checksum và provenance để kết luận.
13. Không lấy `latest/release` làm chứng cứ phiên bản đã được kiểm thử hoặc an toàn.
14. Không tin một artifact chỉ vì bytes khớp sidecar lấy từ cùng nguồn không tin cậy.
15. Với CI/release quan trọng, pin dependencies/plugins/JDK, lưu provenance và kiểm tra artifact output.

## 15. Bài tập tự kiểm tra

**Câu 1.** Repository có `catalog-core-1.0.0.pom` và `catalog-core-1.0.0.jar`. Tệp nào chứa class Java?

**Đáp:** Main JAR thường chứa class/resource; POM descriptor mô tả model và dependencies.

**Câu 2.** Parent có `packaging=pom` nhưng không thấy main JAR; đây có chắc là lỗi?

**Đáp:** Không. POM-only artifact là bình thường cho parent/BOM.

**Câu 3.** File `.jar.sha1` khớp JAR tải cùng host; đã xác thực publisher?

**Đáp:** Chưa. Hash không tự xác thực nguồn; cần trusted key/signature/provenance.

**Câu 4.** Metadata nào liệt kê các versions của `com.example:catalog-core`?

**Đáp:** `com/example/catalog-core/maven-metadata.xml` ở cấp GA.

**Câu 5.** Tại sao SNAPSHOT folder tên `1.1.0-SNAPSHOT`, còn JAR file có timestamp?

**Đáp:** Folder dùng baseVersion; file dùng resolved timestamped version, được V-level metadata ánh xạ.

**Câu 6.** Thấy `maven-metadata-central.xml` trong local repo; đó là POM artifact?

**Đáp:** Không. Đó có thể là bản cache metadata của remote repo mang ID central.

**Câu 7.** Đã `mvn install` thành công có nghĩa teammate có thể tải từ remote?

**Đáp:** Không. Install dùng local repository; cần deploy theo policy để publish remote.

**Câu 8.** Không thấy `-sources.jar`; main dependency có nhất thiết hỏng không?

**Đáp:** Không. Sources là attached artifact tùy chọn.

**Câu 9.** Một version release cụ thể có thể dựng URL POM/JAR từ GAV và layout không?

**Đáp:** Thường có nếu biết extension/classifier. Điều đó không bảo đảm file tồn tại hoặc được phép tải.

**Câu 10.** Cùng GAV mà mirror A và B có hash khác; có thể coi chúng tương đương?

**Đáp:** Không. Cần kiểm tra bytes, trusted source, publication và provenance.

## Tài liệu tham khảo chính thức

- [Apache Maven — Repository Layout](https://maven.apache.org/repositories/layout.html)
- [Apache Maven — Maven Metadata](https://maven.apache.org/repositories/metadata.html)
- [Apache Maven — Repository Metadata Model](https://maven.apache.org/ref/3-LATEST/maven-repository-metadata/)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/)
- [Apache Software Foundation — Verify Releases](https://apache.org/info/verification.html)

