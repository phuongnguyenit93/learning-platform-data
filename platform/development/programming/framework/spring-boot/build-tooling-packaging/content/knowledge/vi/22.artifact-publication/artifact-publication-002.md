# Quản lý phiên bản phát hành, SNAPSHOT và classifier khi xuất bản Spring Boot/Maven

## 1. Bài toán: cùng tên ứng dụng, nhưng thực tế phát hành artifact nào?

Trong Spring Boot, câu nói “đã deploy phiên bản 1.4.0” chưa đủ để truy vết artifact. Một Maven module có thể tạo:

- `release-demo-1.4.0.jar`: JAR thông thường, dùng làm **main artifact** trong dependency graph.
- `release-demo-1.4.0-exec.jar`: JAR được Spring Boot repackage, có loader và nested dependencies để chạy `java -jar`.
- `release-demo-1.4.0-sources.jar` và `release-demo-1.4.0-javadoc.jar`: artifacts phụ trợ.
- `release-demo-1.5.0-SNAPSHOT-exec.jar`: tên artifact cục bộ ở giai đoạn phát triển; khi deploy lên snapshot repository, file remote có thể mang timestamp/build number.
- Một OCI image chứa executable JAR, với **image digest** hoàn toàn khác Maven coordinates và JAR SHA-256.

Nếu pipeline chọn nhầm plain JAR, chạy `java -jar` có thể thất bại. Nếu project tiêu thụ executable JAR của Spring Boot như thư viện, classpath thường không nhìn thấy các application classes nằm dưới `BOOT-INF/classes`. Nếu staging dùng SNAPSHOT mà production lại tham chiếu SNAPSHOT, cùng logical version có thể resolve sang bytes mới ở những thời điểm khác nhau.

Bài thuộc mục **Xuất bản sản phẩm** trong chủ đề **Spring Boot Build Tooling Packaging**. Sau bài này, bạn sẽ biết:

1. Đọc đúng Maven GAV và các phần mở rộng `type`/`extension`/`classifier`.
2. Phân biệt phiên bản development `-SNAPSHOT` với release cố định, kể cả dạng timestamped snapshots trong remote repository.
3. Dùng `spring-boot-maven-plugin` tạo plain JAR và executable JAR có classifier `exec` cùng một Maven version.
4. Viết và chạy một ứng dụng Java 17+/Spring Boot Maven hoàn chỉnh, kiểm tra hai artifacts bằng Java 17 standard library.
5. Hiểu tác dụng của `mvn package`, `mvn install`, `mvn deploy`, `distributionManagement` và `settings.xml`.
6. Chuyển từ phiên bản SNAPSHOT sang release có commit/tag và chuyển sang SNAPSHOT tiếp theo bằng quy trình có kiểm soát.
7. Tránh phát hành trùng version release, trộn repository policy, bỏ sót classifier, hoặc publish artifacts chưa vượt QA.
8. Thiết kế CI lưu Git revision, POM version, classifier, byte checksum và repository coordinates của **từng file đã phát hành**.

**Bộ minh họa:** Java `17`, Spring Boot `3.5.16`, Maven tương thích, module `com.example.release:release-demo:1.4.0-SNAPSHOT`. Version `1.4.0-SNAPSHOT` chỉ là dữ liệu học tập; không suy từ nó rằng hệ thống thực đang có release 1.4.0. Không cần kết nối repository production để thực hành phần build và kiểm tra.

## 2. Maven coordinates: version, packaging và classifier không thay thế nhau

Một Maven artifact được nhận diện chủ yếu bằng:

~~~text
groupId : artifactId : version
~~~

Trong thực hành sử dụng artifact, còn có **extension/type** và **classifier**. Với ví dụ:

~~~text
groupId    = com.example.release
artifactId = release-demo
version    = 1.4.0-SNAPSHOT
type       = jar
classifier = (không có) hoặc exec
~~~

Các chuỗi thường gặp:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `groupId` | `com.example.release` | Namespace của tổ chức/nhóm artifact |
| `artifactId` | `release-demo` | Định danh module trong group |
| `version` | `1.4.0` hoặc `1.4.0-SNAPSHOT` | Phiên bản logic của module |
| `packaging` | `jar`, `war`, `pom` | Maven lifecycle và artifact loại mặc định do project tạo |
| `extension` / dependency `type` | `jar`, `war`, `pom`, `zip`... | Dạng artifact hoặc cách Maven diễn giải artifact trong dependency |
| `classifier` | `exec`, `sources`, `javadoc`, `tests`... | Biến thể artifact **cùng GAV** và extension/type tương ứng |

**Điều quan trọng:** classifier là một phần của artifact identity, **không tạo version mới**. `release-demo:1.4.0:jar:exec` và main `release-demo:1.4.0:jar` đều gắn với cùng logical release nhưng là **hai file khác nhau**. Hậu tố `-exec` trong filename là cách thể hiện classifier, không phải một phần của `artifactId` hoặc `version`.

Với Maven dependency XML, đây là hai yêu cầu khác nhau:

~~~xml
<!-- Main JAR: không classifier -->
<dependency>
    <groupId>com.example.release</groupId>
    <artifactId>release-demo</artifactId>
    <version>1.4.0</version>
</dependency>
~~~

~~~xml
<!-- Explicit classifier, khi consumer THẬT SỰ cần biến thể exec -->
<dependency>
    <groupId>com.example.release</groupId>
    <artifactId>release-demo</artifactId>
    <version>1.4.0</version>
    <type>jar</type>
    <classifier>exec</classifier>
</dependency>
~~~

Đoạn thứ hai chứng minh cách chọn artifact có classifier, **không phải khuyến nghị dùng Spring Boot executable JAR làm dependency bình thường**. Application classes bên trong executable JAR đặt dưới `BOOT-INF/classes` nên dependent modules thường **không** load chúng theo classpath chuẩn. Khi cần API/thư viện, dùng plain JAR hoặc tách module thư viện.

### 2.1. Định dạng tọa độ trong công cụ và repository path

Trong cú pháp hiển thị Maven truyền thống có thể thấy:

~~~text
groupId:artifactId:packaging:version
groupId:artifactId:packaging:classifier:version
~~~

Một số công cụ dùng các cách viết khác hoặc ghi `type` thay `packaging`. Đừng tự đoán thứ tự tham số `classifier`/`version` của một CLI chỉ từ định dạng filename. Đối với POM, **dependency XML** là cách rõ ràng, còn repository path là chứng cứ artifact đã publish.

Maven repository layout thường giống:

~~~text
com/example/release/release-demo/1.4.0/
  release-demo-1.4.0.pom
  release-demo-1.4.0.jar
  release-demo-1.4.0-exec.jar
~~~

Nếu attach sources/Javadoc, cùng version directory còn có `-sources.jar` và `-javadoc.jar`. Cấu trúc này không yêu cầu thay `artifactId` hoặc tạo một version khác cho từng classifier.

### 2.2. finalName không thay Maven GAV

Trong `pom.xml`, `<build><finalName>service</finalName></build>` ảnh hưởng tên file cục bộ như `target/service.jar` hoặc `target/service-exec.jar`. Nó **không** đổi `groupId:artifactId:version` ở repository khi install/deploy. Nếu người vận hành chỉ nhìn filename, rất dễ nhầm identity của release.

Vì vậy release manifest nên ghi cả **Maven GAV + classifier + extension + SHA-256 + Git revision**, không chỉ `target/service.jar`.

## 3. SNAPSHOT: một phiên bản logic dành cho các bản build còn thay đổi

Trong Maven convention, hậu tố **` -SNAPSHOT `** (không có dấu cách trong POM) thể hiện một **version đang phát triển**, ví dụ:

~~~xml
<version>1.4.0-SNAPSHOT</version>
~~~

Trên máy local, sau `mvn clean package`, tên thường là:

~~~text
target/release-demo-1.4.0-SNAPSHOT.jar
target/release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

Hai tên này phản ánh **logical base version**. Nếu cùng version được deploy lên snapshot repository nhiều lần, repository có thể lưu **timestamped unique snapshots** để phân biệt các lần publish:

~~~text
com/example/release/release-demo/1.4.0-SNAPSHOT/
  release-demo-1.4.0-20261109.031405-3.jar
  release-demo-1.4.0-20261109.031405-3-exec.jar
  release-demo-1.4.0-20261109.031405-3.pom
  maven-metadata.xml
~~~

`20261109.031405-3` là **ví dụ minh họa**, không phải timestamp đã được tạo khi chạy bài học. Phần `20261109.031405` theo định dạng timestamp UTC `yyyyMMdd.HHmmss` và `3` là build number do repository metadata quản lý. Không tự điền timestamp/build number đó vào project `<version>`; logical version trong POM vẫn là `1.4.0-SNAPSHOT`.

### 3.1. Maven metadata ánh xạ từ SNAPSHOT logic đến binary thực

Ở version directory của remote snapshot repository, `maven-metadata.xml` có thể chứa:

~~~xml
<metadata>
    <groupId>com.example.release</groupId>
    <artifactId>release-demo</artifactId>
    <version>1.4.0-SNAPSHOT</version>
    <versioning>
        <snapshot>
            <timestamp>20261109.031405</timestamp>
            <buildNumber>3</buildNumber>
        </snapshot>
        <snapshotVersions>
            <snapshotVersion>
                <extension>jar</extension>
                <value>1.4.0-20261109.031405-3</value>
            </snapshotVersion>
            <snapshotVersion>
                <classifier>exec</classifier>
                <extension>jar</extension>
                <value>1.4.0-20261109.031405-3</value>
            </snapshotVersion>
        </snapshotVersions>
    </versioning>
</metadata>
~~~

Fragment trên **rút gọn để học**; metadata thật còn có `updated`, `lastUpdated` và các elements phù hợp repository/plugin version. Điều cốt lõi: Maven có thể resolve **main JAR** và **`exec` JAR** qua cùng logical SNAPSHOT version nhưng với cặp `classifier + extension` khác nhau.

### 3.2. Vì sao SNAPSHOT không phù hợp làm khóa phát hành bất biến?

Cùng dependency:

~~~xml
<dependency>
    <groupId>com.example.release</groupId>
    <artifactId>release-demo</artifactId>
    <version>1.4.0-SNAPSHOT</version>
</dependency>
~~~

ở hai thời điểm có thể resolve sang **hai deployment snapshots khác nhau**, tùy repository metadata, cache, mirrors và update policy. Lệnh `mvn -U ...` có thể ép Maven kiểm tra cập nhật snapshots/release metadata theo khả năng resolver, nhưng **không biến logical SNAPSHOT thành bản phát hành immutable**.

Dùng SNAPSHOT cho integration liên tục là hợp lý nếu consumer chấp nhận thay đổi; với production, nên deploy/pin **artifact release cụ thể và checksum/digest** đã nghiệm thu, không gọi một SNAPSHOT mutable như một release cố định.

### 3.3. -SNAPSHOT khác pre-release qualifiers

Maven không ép toàn bộ dự án tuân thủ Semantic Versioning. Tên như `1.4.0-RC1`, `1.4.0-beta.1`, `1.4.0` là những **version strings khác**; chỉ suffix `-SNAPSHOT` có semantics Maven dành cho snapshot resolution/deployment. Một release candidate **không tự là SNAPSHOT** nếu không dùng suffix đó.

Đội ngũ có thể định nghĩa policy SemVer, ví dụ major khi breaking API, minor khi thêm tính năng tương thích, patch khi sửa lỗi. Nhưng policy đó là **quy ước phát hành của dự án**, không phải bằng chứng Maven tự xác định thay bạn.

## 4. Release version: bảo toàn danh tính và bytes sau khi công bố

Một Maven release tiêu biểu:

~~~xml
<version>1.4.0</version>
~~~

khác `1.4.0-SNAPSHOT`. Khi publish release, version directory thường là:

~~~text
com/example/release/release-demo/1.4.0/
  release-demo-1.4.0.pom
  release-demo-1.4.0.jar
  release-demo-1.4.0-exec.jar
~~~

Một release đáng tin cần hai lớp chính sách:

1. **Version identity:** `1.4.0` được gắn với source commit/tag, dependency graph, POM, JDK/toolchain và pipeline xác định.
2. **Artifact integrity:** mỗi file được công bố có SHA-256/signature/provenance riêng và repository **không cho ghi đè** bản đã phát hành.

Đừng sửa code rồi `mvn deploy` lại đúng version `1.4.0` để “vá nhanh” artifact công khai. Nếu repository cho overwrite, các consumer có thể thấy bytes khác nhau cho cùng tọa độ, phá rollback và điều tra. Hãy phát hành version mới (ví dụ `1.4.1`) hoặc dùng cơ chế release correction có audit, chứ không im lặng thay artifact cũ.

### 4.1. Version numbering và rollback

Một chiến lược thường gặp:

~~~text
1.4.0-SNAPSHOT    phát triển dòng 1.4
1.4.0-RC1         bản thử nghiệm release candidate (theo policy team)
1.4.0             bản ổn định được công bố
1.4.1             bản sửa lỗi sau release 1.4.0
1.5.0-SNAPSHOT    tiếp tục phát triển tính năng dòng 1.5
~~~

Rollback production không phải đổi lại `<version>1.4.0</version>` rồi build mới. Nó nên **triển khai lại đúng artifact bytes của bản 1.4.0 đã lưu**, thường qua immutable repository coordinate/checksum hoặc image registry digest.

Maven project version không tự ghi commit ID, build timestamp hay OCI digest. Nếu cần truy vết chính xác, kết hợp Git revision, artifact hashes và CI release manifest. Một version dễ đọc giúp điều phối, còn checksums giúp xác minh tệp thực tế.

## 5. Classifier trong Spring Boot: giữ plain JAR và executable JAR

### 5.1. Mặc định repackage không có classifier

Nếu Spring Boot Maven Plugin `repackage` được chạy **không có `classifier`**, nó thường thay main JAR bằng executable JAR, còn archive ban đầu có thể được lưu với hậu tố `.original`. Mô hình này thuận tiện cho ứng dụng chỉ deploy bằng `java -jar`, nhưng không phù hợp khi module ấy được tiêu thụ làm **dependency JAR thông thường**.

Lý do: application classes trong executable JAR nằm dưới `BOOT-INF/classes`, các runtime dependencies ở `BOOT-INF/lib`. Một dependent project dùng classpath tiêu chuẩn không coi `BOOT-INF/classes` như root `demo/`.

### 5.2. Dùng classifier exec

Theo Spring Boot Maven Plugin, cấu hình:

~~~xml
<configuration>
    <mainClass>demo.Application</mainClass>
    <classifier>exec</classifier>
    <attach>true</attach>
</configuration>
~~~

cho phép **giữ main artifact bình thường** và tạo executable archive phụ `-exec.jar`. `attach=true` (mặc định của goal) khiến artifact được attach để Maven install/deploy vào repository **cùng GAV**.

Khi không có artifact classifier `exec` từ bước packaging trước đó, Boot plugin dùng main JAR làm source rồi tạo classifier-attached executable archive. Nếu một plugin **đã tạo artifact classifier exec** trước, goal repackage có thể dùng nó làm source và thay đúng biến thể đó; vì vậy phải nhìn effective POM và kiểm tra file output thật.

Một số điểm nên phân biệt:

| Cấu hình repackage | Kết quả chính | Điều cần lưu ý |
| --- | --- | --- |
| Không có `classifier` | Executable JAR thay main JAR | Module khác dùng làm dependency thường không đọc classes như plain JAR |
| `classifier=exec`, `attach=true` | Plain main JAR + executable `exec` artifact | Cả hai có thể được `install`/`deploy` |
| `classifier=exec`, `attach=false` | Có thể có executable output local nhưng không attach cho install/deploy | Không khẳng định remote có `-exec.jar` |
| `skip=true` | Bỏ qua repackage goal | Không tạo Boot executable archive từ goal đó |
| `<build><finalName>...` | Đổi tên file local | Không đổi GAV/classifier trong Maven repository |

**Không tự gắn `-exec` vào `artifactId`** để mô phỏng classifier, vì đó trở thành một module/repository coordinate khác. Dùng classifier khi muốn các biến thể thuộc cùng một component/version, và tách module khi API/lifecycle thật sự khác.

## 6. Bài thực hành hoàn chỉnh: một POM tạo hai JAR

### 6.1. Cấu trúc project

~~~text
release-demo/
  pom.xml
  InspectReleaseArtifacts.java
  src/
    main/
      java/
        demo/
          Application.java
~~~

`InspectReleaseArtifacts.java` được đặt tại **project root**, ngoài `src/main/java`, để làm công cụ kiểm tra artifacts độc lập. Nó không được đóng vào plain/executable JAR.

### 6.2. pom.xml dùng Java 17 + Spring Boot 3.5

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example.release</groupId>
    <artifactId>release-demo</artifactId>
    <version>1.4.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <configuration>
                            <mainClass>demo.Application</mainClass>
                            <classifier>exec</classifier>
                            <attach>true</attach>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Tại sao cấu hình như vậy?**

- `<version>1.4.0-SNAPSHOT</version>` là version của **cả hai artifacts**, không riêng executable JAR.
- `<packaging>jar</packaging>` cho Maven tạo main JAR thông thường.
- `spring-boot-starter-parent` quản lý plugin/dep versions và đã cấu hình execution goal `repackage` với id `repackage`. Khi **kế thừa parent này**, block `<execution><id>repackage</id>` ở POM ví dụ **tùy biến execution kế thừa**, không phải thêm một goal repackage thứ hai.
- `classifier=exec` yêu cầu Boot tạo một executable JAR có classifier `exec`. `attach=true` cho phép publish nó cùng main artifact.
- `mainClass=demo.Application` tránh ambiguity nếu sau này xuất hiện nhiều Java main classes.
- `java.version=17` đặt compile target theo Boot parent; cần JDK thực tế đủ mới để build.
- Không có distributionManagement hoặc credentials trong POM ví dụ. Người học có thể build/install **local** mà không cần có quyền vào remote repository.

**Trong dự án không dùng Spring Boot starter parent**, phải cấu hình plugin version và execution/bind goal `repackage` tường minh. Không thể chỉ chép một `<execution><id>repackage</id>` **không có goal** rồi giả định Maven biết phải gọi gì nếu parent không định nghĩa execution tương ứng.

### 6.3. Application.java

Tạo `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CommandLineRunner report() {
        return args -> System.out.println("release-demo:ok");
    }
}
~~~

Ứng dụng dùng Spring Boot starter (không có embedded web server), in một dòng rồi Spring application context thường không có server thread phải giữ lâu. Với các dòng lệnh sau đây, **dòng do code của ứng dụng in** là:

~~~text
release-demo:ok
~~~

Spring logs và Maven build logs là đầu ra khác, không tính vào chính dòng `System.out.println`.

### 6.4. Build và kiểm tra tên file

Tại root có `pom.xml`:

~~~bash
mvn -B -ntp clean verify
~~~

Sau khi build thành công, project tạo hai artifacts chính:

~~~text
target/release-demo-1.4.0-SNAPSHOT.jar
target/release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

**Không chờ executable archive có tên `release-demo-exec-1.4.0-SNAPSHOT.jar`**: Maven naming convention thường đặt classifier **sau version**. Ngoài hai JAR có thể có build directories và metadata khác trong `target/`.

Chạy executable JAR:

~~~bash
java -jar target/release-demo-1.4.0-SNAPSHOT-exec.jar \
  --spring.main.banner-mode=off \
  --logging.level.root=OFF
~~~

Lệnh này dùng cú pháp tiếp dòng POSIX shell. Trên Windows PowerShell có thể chạy một dòng:

~~~powershell
java -jar .\target\release-demo-1.4.0-SNAPSHOT-exec.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Dòng do chương trình chủ động in:

~~~text
release-demo:ok
~~~

**Không dùng `java -jar target/release-demo-1.4.0-SNAPSHOT.jar` làm tiêu chí PASS**, vì đây là **plain JAR** không có launcher/dependencies như executable Boot archive. Plain JAR được dùng theo classpath/dependency graph bình thường, không phải để một mình đóng vai full application.

### 6.5. Inspect bằng jar tf

~~~bash
jar tf target/release-demo-1.4.0-SNAPSHOT.jar
jar tf target/release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

Đặc điểm kỳ vọng:

| Entry hoặc dấu hiệu | Plain main JAR | `exec` Boot JAR |
| --- | --- | --- |
| `demo/Application.class` tại classpath root | Có | Không ở root |
| `BOOT-INF/classes/demo/Application.class` | Không | Có |
| `BOOT-INF/lib/...jar` | Không | Có |
| `org/springframework/boot/loader/...` | Không | Có |
| `Main-Class` là Boot `JarLauncher` | Không | Có |
| `Start-Class: demo.Application` | Không phải manifest contract bắt buộc | Có |

Đây là sự khác biệt **nội dung artifact**, không chỉ hậu tố filename. Khi `repackage` đã attach `exec` đúng, `mvn install` và `mvn deploy` có thể publish cả hai phiên bản dưới cùng GAV.

## 7. Viết Java 17 validator để tránh chọn nhầm plain và executable JAR

Tạo `InspectReleaseArtifacts.java` tại project root:

~~~java
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class InspectReleaseArtifacts {

    private static void check(boolean condition, String detail) {
        if (!condition) {
            throw new IllegalStateException(detail);
        }
    }

    private static String attribute(JarFile jar, String name)
            throws Exception {
        Manifest manifest = jar.getManifest();
        if (manifest == null) {
            return null;
        }
        Attributes attrs = manifest.getMainAttributes();
        return attrs.getValue(name);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java InspectReleaseArtifacts.java "
                            + "<plain.jar> <exec.jar>");
        }

        try (JarFile plain = new JarFile(
                    Path.of(args[0]).toFile());
             JarFile exec = new JarFile(
                    Path.of(args[1]).toFile())) {

            check(plain.getEntry("demo/Application.class") != null,
                    "Main JAR lacks root application class");
            check(plain.getEntry(
                    "BOOT-INF/classes/demo/Application.class") == null,
                    "Main JAR unexpectedly has Boot layout");

            check(exec.getEntry(
                    "BOOT-INF/classes/demo/Application.class") != null,
                    "Exec JAR lacks packaged application class");
            check(exec.stream().anyMatch(e ->
                    e.getName().startsWith("BOOT-INF/lib/")
                            && e.getName().endsWith(".jar")),
                    "Exec JAR lacks nested runtime libraries");

            String main = attribute(exec, "Main-Class");
            String start = attribute(exec, "Start-Class");

            check("org.springframework.boot.loader.launch.JarLauncher"
                    .equals(main),
                    "Unexpected Boot launcher: " + main);
            check("demo.Application".equals(start),
                    "Unexpected Start-Class: " + start);

            System.out.println("plain.jar.layout=PASS");
            System.out.println("exec.jar.layout=PASS");
            System.out.println("classifier.exec=PASS");
        }
    }
}
~~~

Đây là chương trình Java 17 standard library, **không cần import Spring**. Nó đọc **chính file ZIP/JAR đã build**: xác minh plain JAR có class ở root, executable JAR chứa `BOOT-INF/classes`/`BOOT-INF/lib` và manifest Boot 3.5 có launcher đúng. Nếu fail, ném exception và Java launcher trả nonzero exit code, thích hợp dùng trong CI.

Sau `mvn clean verify`, chạy:

~~~bash
java InspectReleaseArtifacts.java \
  target/release-demo-1.4.0-SNAPSHOT.jar \
  target/release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

Trong PowerShell, dùng một dòng:

~~~powershell
java InspectReleaseArtifacts.java .\target\release-demo-1.4.0-SNAPSHOT.jar .\target\release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

Với POM/code ví dụ ở trên, stdout **do validator tự in khi PASS** chính xác là:

~~~text
plain.jar.layout=PASS
exec.jar.layout=PASS
classifier.exec=PASS
~~~

**Lưu ý scope:** Kiểm tra này tập trung vào Spring Boot 3.5 `JAR` layout, không phải mọi phiên bản Spring Boot hay `layout=ZIP/WAR/NONE`. Khi dùng layout khác, launcher/path khác; phải sửa điều kiện theo hợp đồng artifact thật. Bài không khẳng định đã chạy những lệnh này trên máy của bạn, mà cung cấp code/expected output để bạn thực hành.

### 7.1. Kiểm tra checksum của từng artifact

POSIX:

~~~bash
sha256sum target/release-demo-1.4.0-SNAPSHOT.jar
sha256sum target/release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\target\release-demo-1.4.0-SNAPSHOT.jar -Algorithm SHA256
Get-FileHash .\target\release-demo-1.4.0-SNAPSHOT-exec.jar -Algorithm SHA256
~~~

Hai hashes **khác nhau là bình thường**, vì plain và exec JAR là hai files với cấu trúc và dependencies khác. Đừng so hai hash với nhau để kết luận một trong hai “sai release”. Điều cần xác minh là mỗi file có đúng role/classifier và lưu checksum tương ứng.

## 8. package, install và deploy: ba ranh giới khác nhau

| Lệnh | Tác dụng chính | Có ghi lên remote repository? |
| --- | --- | --- |
| `mvn package` | Build artifact trong `target/` theo lifecycle | Không |
| `mvn verify` | Chạy lifecycle đến verify; thường gồm tests/package và các verification plugins đã bind | Không |
| `mvn install` | Chạy lifecycle đến install, đưa main/attached artifacts vào Maven **local repository** | Không |
| `mvn deploy` | Chạy lifecycle đến deploy, đưa artifacts vào repository được cấu hình bởi deployment plugin | Có, nếu trỏ remote; hoặc file repository nếu cấu hình file: |

**`mvn install` không phải triển khai ứng dụng lên Tomcat, Kubernetes hay production**. Nó làm artifact khả dụng trong `~/.m2/repository` (hoặc local repository path theo cấu hình) cho Maven builds khác cùng môi trường.

Với ví dụ `1.4.0-SNAPSHOT`, sau:

~~~bash
mvn -B -ntp clean install
~~~

local Maven repo có thể có:

~~~text
~/.m2/repository/com/example/release/release-demo/1.4.0-SNAPSHOT/
  release-demo-1.4.0-SNAPSHOT.pom
  release-demo-1.4.0-SNAPSHOT.jar
  release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

Đường dẫn `~/.m2/repository` là giá trị mặc định phổ biến, không phải hằng số: Maven `settings.xml` có thể đổi `localRepository`. Trên Windows, đường dẫn thường nằm dưới user home `.m2\repository`.

Với `attach=true`/`classifier=exec` và build hợp lệ, goal install/deploy biết đến cả main artifact và attached artifact. Ngược lại, nếu `attach=false` mà bạn vẫn thấy `-exec.jar` local, đừng cho rằng nó đã được publish lên Maven repository.

### 8.1. Deploy phase có thể chạy lại lifecycle

Nếu bạn chạy `mvn clean verify`, smoke-test JAR A, rồi chạy tiếp `mvn deploy`, Maven có thể thực hiện lại các phases trước deploy, bao gồm packaging/repackage. JAR B sau đó **có thể khác bytes** do timestamps/generated metadata hoặc thay đổi workspace. Vì vậy không được mặc nhiên nói “đã test file A thì deploy chắc chắn file A”.

Một release pipeline chặt chẽ nên:

- Đặt các verification gates phù hợp **trước deploy** trong cùng lifecycle/build orchestration, hoặc dùng **staging repository** có bước kiểm tra/promote sau khi upload.
- Nếu dùng nhiều jobs, chuyển artifact bytes qua kho trung gian có checksum và kiểm tra lại trước khi publish.
- Sau deploy, kiểm tra remote artifact coordinates/classifiers và file hashes rồi mới promote/announce.
- Không chạy một Maven build khác rồi âm thầm upload file thay thế mà giữ nguyên release version.

## 9. distributionManagement: chỉ định nơi publish, không chứa mật khẩu

Maven Deploy Plugin sử dụng `distributionManagement` trong POM để biết repository đích. Một ví dụ **minh họa cấu hình**, không phải URL triển khai thật:

~~~xml
<distributionManagement>
    <repository>
        <id>demo-releases</id>
        <url>https://repo.example.invalid/repository/releases</url>
    </repository>
    <snapshotRepository>
        <id>demo-snapshots</id>
        <url>https://repo.example.invalid/repository/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

Địa chỉ `repo.example.invalid` cố ý là domain ví dụ **không dùng để upload thật**. Trong dự án thật, repo manager (Nexus/Artifactory/registry Maven tương đương) và đội vận hành cung cấp HTTPS URL/phân quyền chính xác. Không đoán endpoint từ tên công ty.

Khi POM version kết thúc bằng `-SNAPSHOT`, Maven thường dùng `snapshotRepository`; với release non-SNAPSHOT, dùng `repository`. Nếu thiếu `snapshotRepository`, behavior fallback phụ thuộc cấu hình deploy/plugin; nên khai báo explicit để không trộn hai policy, và xem logs target repo khi triển khai.

### 9.1. Repository server IDs và credentials

Credentials **không thuộc POM**. Maven `settings.xml` có thể khai báo server ID tương ứng:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>demo-releases</id>
            <username>release-publisher</username>
        </server>
        <server>
            <id>demo-snapshots</id>
            <username>snapshot-publisher</username>
        </server>
    </servers>
</settings>
~~~

**Đoạn này chỉ cho thấy mapping ID**, cố ý không có password/token vì không nên ghi secrets trong bài Knowledge. Trong CI, credentials phải được cung cấp bởi secret management/settings được quản lý thích hợp; không commit `settings.xml` chứa password/token vào Git hoặc in ra log public. Với Maven mới, có các cơ chế credential origin binding; khi nâng Maven/enterprise mirror cần xem đúng version tài liệu settings.

`<id>` trong `distributionManagement` phải phù hợp `<server><id>` cho phép Maven tìm credentials. Lỗi HTTP 401/403 thường là vấn đề token/permission/server ID; không phải lỗi phiên bản `1.4.0-SNAPSHOT` hay classifier.

### 9.2. Dependency repository khác publishing repository

Trong POM, `<repositories>`/`<pluginRepositories>` mô tả nơi **resolve/downloading** dependencies/plugins; `<distributionManagement>` chỉ nơi **upload artifacts của project**. Không thêm repository có quyền publish vào `<repositories>` rồi cho rằng `mvn deploy` sẽ biết upload vào đâu.

Repository manager còn có policies cho snapshot vs release, permissions, retention và overwrite protection. Sự có mặt của URL trong POM không tự cấp quyền. Mọi thao tác publish thật phải qua CI/approval và repository được phép.

## 10. Thực hành publish local file repository, không đụng remote production

Nếu muốn nhìn layout deploy mà **không cần tài khoản repository**, có thể dùng Maven Deploy Plugin với `altDeploymentRepository` trỏ đến một file repository **cục bộ của bài thực hành**.

Lệnh minh họa từ project root, với Maven Deploy Plugin hiện đại:

~~~bash
mvn -B -ntp clean deploy \
  -DaltDeploymentRepository=lab::file:./target/lab-maven-repo
~~~

Lệnh này **thực sự chạy goal deploy** nhưng đích upload là `file:./target/lab-maven-repo`, không phải máy chủ HTTP production. Nó tạo repository files/metadata trong working directory test, tùy Maven deploy-plugin version và đường dẫn được resolve. Đây là bài lab; nếu chạy trong CI thật, đảm bảo path cục bộ và cleanup phù hợp, không trỏ nhầm `-DaltDeploymentRepository` tới release repository.

**Lưu ý phiên bản plugin:** cú pháp `id::url` dùng với Maven Deploy Plugin 3.x. Một số plugin 2.x cũ dùng `id::layout::url`. Với Spring Boot parent có quản lý versions, xem effective POM/plugin version trước khi dùng lệnh ở project khác.

Sau đó kiểm tra repository filesystem dưới `target/lab-maven-repo/com/example/release/release-demo/` và đọc `maven-metadata.xml` nếu có. Các snapshot deployments có thể nhận timestamped filenames, thay cho tên `-SNAPSHOT` cục bộ. Không hardcode timestamp hoặc build number khi viết QA.

**Không gọi đây là production release.** File repository chỉ giúp hiểu vai trò `deploy`/metadata; production repository cần HTTPS/authentication, immutability, auditing, artifact scanning và promotion policy riêng.

### 10.1. Maven deploy-file khác Maven deploy

`mvn deploy` publish **project artifacts** (main artifact, POM, attached classifiers) theo lifecycle. `mvn deploy:deploy-file` là goal riêng thường dùng để upload một artifact có sẵn hoặc third-party binary, khi đó phải cung cấp file, tọa độ, repository/pom và có thể thêm các file/classifiers khác theo cấu hình plugin.

Nếu dùng `deploy-file` chỉ cho `-exec.jar` mà quên `main JAR`/POM hoặc sai classifier, consumer có thể gặp lỗi dependency resolution. Vì vậy với project do Maven build bình thường, **ưu tiên `mvn deploy`/staging workflow** để Maven nhận đúng bộ project artifacts. Chỉ dùng `deploy-file` khi bạn biết rõ những files cần publish và có kiểm chứng repository metadata.

## 11. Chuyển SNAPSHOT sang release có kiểm soát

### 11.1. Quy trình thủ công dùng Maven Versions Plugin

Giả sử repository đang ở `1.4.0-SNAPSHOT` và team đã quyết định phát hành `1.4.0`. Dùng Maven Versions Plugin từ project root (project thực cần pin plugin version trong build governance):

~~~bash
mvn versions:set -DnewVersion=1.4.0 -DgenerateBackupPoms=false
git diff -- pom.xml
~~~

Lệnh `versions:set` chỉnh project version trong POM. Nó **không** tự sửa ứng dụng để tương thích, không tự đóng Git tag và không publish. Với multi-module, cần xem các flags để cập nhật parent/child versions nhất quán.

Khi code đã khóa và QA hoàn tất:

~~~bash
mvn -B -ntp clean verify
java InspectReleaseArtifacts.java \
  target/release-demo-1.4.0.jar \
  target/release-demo-1.4.0-exec.jar
java -jar target/release-demo-1.4.0-exec.jar \
  --spring.main.banner-mode=off \
  --logging.level.root=OFF
~~~

Validator ở mục 7 nhận filenames theo version hiện tại; main/executable layout không thay chỉ vì bỏ suffix `-SNAPSHOT`. Dòng do `Application` in vẫn là `release-demo:ok`.

Sau khi các gates đạt và commit được phê duyệt, lưu Git revision cùng POM version. Ví dụ thao tác SCM:

~~~bash
git add pom.xml
git commit -m "Release 1.4.0"
git tag v1.4.0
~~~

Các lệnh này **minh họa quy trình cho một Git repository hợp lệ**, không phải lệnh cần chạy trong mọi team. Team có thể dùng signed tags, protected branches và automation. Chỉ tag khi Git working tree/permissions/branch policy đã được xác nhận; đừng tự tạo tag hoặc push khi chưa được giao quyền.

### 11.2. Phát hành và chuyển lại dòng phát triển

Sau khi release `1.4.0` được publish/approved (và **không** overwrite bytes dưới cùng version), có thể mở phiên bản tiếp:

~~~bash
mvn versions:set \
  -DnewVersion=1.5.0-SNAPSHOT \
  -DgenerateBackupPoms=false
git diff -- pom.xml
~~~

Chỉ chọn `1.5.0-SNAPSHOT` khi kế hoạch phiên bản phù hợp; nếu đội ngũ tiếp tục patch branch `1.4.x`, phiên bản development có thể là `1.4.1-SNAPSHOT`. Không bắt buộc cứ release `1.4.0` thì minor tiếp theo phải là 1.5.0.

**Đừng chạy update version/release/SCM operations tự động vào production chỉ vì có ví dụ này.** Hệ thống thật có approval gates, versioning policy, protected tags, CI credentials và staging/promotion.

### 11.3. Maven Release Plugin

Maven Release Plugin có các goals `release:prepare` và `release:perform`. Theo tài liệu:

- `prepare` có thể kiểm tra uncommitted changes/SNAPSHOT dependencies, thay POM version, chạy các checks, commit/tag, rồi tăng next development version.
- `perform` có thể checkout release tag và thực hiện publish theo cấu hình.
- Cần SCM configuration, Git credentials/permissions, distributionManagement và plugin versions phù hợp.
- Plugin có thể **thay source/POM/tags/remote artifacts**; không dùng thử trên repository thực khi chưa hiểu tác động.

Đây là workflow phát hành có trạng thái, không phải một lệnh thay thế `mvn package` đơn giản. Với CI có release orchestrator riêng, có thể dùng cách khác, miễn identity/provenance và artifact immutability được kiểm chứng.

## 12. SNAPSHOT policy, consumer resolution và dependency hygiene

### 12.1. Consumer trỏ đến SNAPSHOT

Một consumer dùng `1.4.0-SNAPSHOT` có thể nhận artifact mới ở thời điểm resolver refresh snapshot metadata. Điều này hữu ích cho integration environment, nhưng nguy hiểm nếu consumer cần rollback deterministic.

Các kiểm soát:

- Không sử dụng SNAPSHOT mutable ở production khi không có chính sách đặc biệt được duyệt.
- Với integration builds, ghi lại **resolved snapshot timestamp/build number** và binary SHA-256, không chỉ logical version.
- Quản lý `updatePolicy`/mirrors và dependency cache; hiểu tác động của `mvn -U` đối với quá trình resolve.
- Không bật snapshot resolution cho một release repository không có lý do, hoặc ngược lại trỏ release build vào repository nhận snapshot.
- Khi release cần khóa dependency graph, ưu tiên các non-SNAPSHOT versions và artifact integrity verification.

### 12.2. Classifier thuộc mỗi snapshot artifact

Trong remote metadata, `snapshotVersions` phân biệt artifacts bằng **extension** và **classifier**. Nếu repository đã có main `jar` nhưng không có `exec` `jar`, consumer `classifier=exec` có thể không resolve được dù `1.4.0-SNAPSHOT` về mặt logic tồn tại.

Khi deploy, kiểm tra **đủ hai files** và metadata mapping trước khi cho rằng full release set đã sẵn sàng. Trong CI có thể yêu cầu repository API trả đúng artifacts và so checksums từ upload, thay vì chỉ nhìn Maven `BUILD SUCCESS`.

### 12.3. SNAPSHOT và dependencyManagement/BOM

Spring Boot parent/BOM quản lý versions của nhiều dependencies, nhưng **không tự đổi version của project thành release**. Project có thể vẫn là `1.4.0-SNAPSHOT` trong khi mọi external dependency đều là bản stable.

Ngược lại, một project mang version `1.4.0` nhưng phụ thuộc `some-lib:2.0-SNAPSHOT` vẫn có nguy cơ sử dụng binary mutable. Release policy nên kiểm tra cả **project version** và **resolved dependency tree**, không chỉ chuỗi trong POM root.

Tương tự, plugin versions cũng cần được quản lý; việc release code không ngăn Maven plugin được upgrade tự động qua range/khai báo thiếu version trong một POM khác.

## 13. Source JAR, Javadoc JAR và test JAR: classifier nào nên được publish?

Bên cạnh `exec`, Maven thường có các attached artifacts:

| Classifier | Tác dụng điển hình | Ai dùng |
| --- | --- | --- |
| *(trống)* | Main binary JAR cho compile/runtime dependency | Project khác dùng như library |
| `exec` | Boot executable JAR đóng gói nested dependencies | Runtime deployment/CLI |
| `sources` | Source archive | IDE/source browsing, source repository |
| `javadoc` | API documentation | IDE, docs, một số publishing policies |
| `tests` | Test classes (nếu dự án chủ động attach test JAR) | Test utilities, không mặc nhiên là runtime dependency |

Classifiers **không nên sử dụng để che giấu breaking API**. Nếu `exec` và main JAR của cùng GAV chứa application behavior/contract hoàn toàn khác ở mức đáng kể, nên xem lại thiết kế artifact và module boundaries.

Để publish sources/Javadocs, thường dùng Maven Source Plugin/Javadoc Plugin với executions tương ứng; không tự suy rằng `mvn deploy` sinh `-sources.jar` và `-javadoc.jar` nếu POM không khai báo. Một số public repositories (ví dụ Maven Central) có policy metadata, source/Javadoc và signing cụ thể; nội bộ Nexus/Artifactory có thể yêu cầu khác.

Khi module thực chất chỉ là Spring Boot application không có API để dùng như library, có thể **không cần** publish plain JAR như consumable dependency. Nhưng nếu team có yêu cầu vừa làm library vừa làm runnable program, classifier `exec` giúp tách rõ hai vai trò, với điều kiện dependency graph và packaging đã được test.

## 14. Multi-module: version và classifier phải nhất quán trong reactor

Một monorepo Maven:

~~~text
project/
  pom.xml            (packaging=pom, parent/aggregator)
  api/
    pom.xml          (library jar)
  service/
    pom.xml          (Spring Boot application jar)
~~~

Một chiến lược:

- `api` publish main library artifact cùng release version hoặc theo versioning policy riêng.
- `service` tạo executable JAR classifier `exec` nếu cần giữ main JAR.
- Parent/BOM quản lý versions và plugin executions, nhưng chỉ các modules thực sự có main class mới chạy `repackage` cho application.
- Parent `packaging=pom` không có executable JAR để chạy; đừng ép repackage cho mọi module.
- Nếu child version kế thừa parent, khi nâng release cần kiểm tra parent references và dependency versions nội bộ có được cập nhật không.

Trong reactor, ví dụ:

~~~bash
mvn -pl service -am clean verify
~~~

` -pl service -am ` (không có khoảng trắng khi gõ `-pl`) chọn service module và những project nó phụ thuộc trong reactor. Path outputs thường là `service/target/...jar`, không phải `target/...jar` của repo root. Với artifacts thuộc modules khác nhau, `groupId`/`artifactId` có thể khác dù chúng dùng chung version.

Khi publish reactor bằng `mvn deploy`, phải nhìn output từng module/classifier và repository permissions. Tránh dùng wildcard upload cả `target/*.jar` từ nhiều modules vì có thể trộn plain/executable/sources và artifacts cũ.

### 14.1. Dependency với classifier exec trong module khác

Nếu `api` hoặc `service-b` cần gọi một Java class từ `service`, sử dụng **main JAR** của `service` nếu contract cho phép; tốt hơn là đặt API/logic dùng chung trong `api` module. **Không lấy executable `-exec.jar` làm thư viện chỉ vì filename chứa dependencies**.

Spring Boot executable JAR là sản phẩm để **khởi chạy**, không phải assembly thay cho dependency management. Đưa executable JAR lên Maven repository **không** khiến nested libraries tự biến thành transitive Maven dependencies của mọi consumer theo cách họ mong đợi.

## 15. Phát hành đúng artifact qua CI/CD

Một pipeline release có thể ghi các gates sau:

~~~text
1. Checkout đúng Git commit/tag
2. Xác nhận clean source và POM project version
3. Resolve dependencies/toolchain/parent versions
4. mvn -B -ntp clean verify
5. Kiểm tra plain JAR + exec JAR đúng version/classifier
6. java -jar exec JAR và smoke-test thật
7. Lưu SHA-256 riêng của plain/exec/POM/source artifacts
8. Staging/publish theo Maven repository policy
9. Verify uploaded artifacts + snapshot/release metadata + hashes
10. Promote/announce immutable release (hoặc snapshot CI artifact)
11. Ghi revision + GAV + classifier + SHA + repository URL
12. Deploy đúng artifact đã được kiểm chứng
~~~

**Không đẩy release chỉ vì `mvn clean package` báo success.** Kiểm tra cả file layout, runtime, source commit/working tree, dependency scopes/versions và repository bytes sau upload. Dùng repository staging/promotion khi cần giữ gate trước khi release visible với consumer.

### 15.1. Release manifest tối thiểu

Một record minh họa:

~~~text
SCM revision:       Git commit SHA được CI xác minh
Maven GAV:          com.example.release:release-demo:1.4.0
Main artifact:      release-demo-1.4.0.jar
Main classifier:    (none)
Executable artifact:release-demo-1.4.0-exec.jar
Exec classifier:    exec
Packaging:          jar
JDK:                Java 17 (toolchain version đã pin)
Repository:         authorized release repository
Hash main:          SHA-256 từ file đã publish
Hash exec:          SHA-256 từ file đã publish
QA:                 artifact inspect + runnable smoke PASS
~~~

Đây là **mẫu field**, không chứa SHA giả. Trong thực tế phải điền checksum thực lấy từ artifacts và gắn CI job ID/timestamp, source revision, dependency lock/provenance khi policy yêu cầu.

### 15.2. Git tags và artifact names không thay thế checksums

`v1.4.0` Git tag cho biết source reference; Maven `1.4.0` là version logic; file `release-demo-1.4.0-exec.jar` là một artifact; SHA-256 của file là fingerprint bytes. Cả bốn **có vai trò khác nhau**.

Một tag có thể bị di chuyển nếu repository không bảo vệ; cùng source có thể rebuild thành JAR bytes khác nếu timestamps/plugin/dependencies không deterministic. Vì vậy CI nên bảo vệ tags, lưu checksums, pin tools/repositories và lưu thông tin artifact đã được publish.

### 15.3. Reproducibility không đồng nghĩa release policy

`project.build.outputTimestamp` có thể giúp Maven plugins tạo archives có timestamps ổn định:

~~~xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Fragment minh họa này phải ghép vào properties hiện có và chọn thời điểm có **release policy**, không sao chép ngày 2024 cho mọi bản. Nhưng timestamp cố định cũng không chứng minh Maven release 1.4.0 được publish đúng source, hay transitive dependencies hoàn toàn bất biến.

Ngược lại, repo manager cấm overwrite release vẫn không tự bảo đảm JAR byte-for-byte reproducible từ source. Đây là hai việc bổ sung: **integrity/immutability của bản đã phát hành** và **khả năng tái build ra cùng bytes**.

## 16. Gradle maven-publish và classifier: mô hình tương đương

Dù ví dụ trọng tâm là Maven, Spring Boot Gradle Plugin cũng có `bootJar` (executable) và `jar` (plain) với thuộc tính archive classifier. Trong project Gradle Groovy DSL đã có plugins Java/Spring Boot tương thích, có thể xác định rõ:

~~~groovy
tasks.named('bootJar') {
    archiveClassifier = 'exec'
}

tasks.named('jar') {
    archiveClassifier = ''
}
~~~

Đây là **fragment**, không phải build.gradle độc lập. Cần xác nhận cú pháp/property style theo Gradle version; trong Kotlin DSL thường dùng `archiveClassifier.set("exec")` và `archiveClassifier.set("")`.

Để publish đúng artifacts với `maven-publish`, phải tạo `MavenPublication` và **attach đúng bootJar artifact** theo cấu hình task/artifacts của project, không kết luận rằng hai tasks build thành công tức cả hai đã upload. Version `1.4.0-SNAPSHOT` ở Gradle cũng có Maven snapshot semantics nếu publish tới Maven-compatible repository, nhưng resolution/publishing plugins, repository credentials và classifiers được khai báo bằng Gradle DSL riêng.

Không dán cấu hình `<classifier>exec</classifier>` của Maven Spring Boot plugin vào `build.gradle` rồi hy vọng nó hoạt động; hai plugins có cấu trúc cấu hình khác nhau. Khi dùng Gradle, áp dụng cùng nguyên tắc: **main vs executable artifact, snapshot vs release, version identity vs bytes, remote repository policy**.

## 17. Lỗi thường gặp và chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Kiểm tra đúng |
| --- | --- | --- |
| `java -jar release-demo-1.4.0.jar` báo thiếu main manifest | Đang chạy **plain main JAR** | Chọn `-exec.jar`; inspect manifest/classpath |
| `ClassNotFoundException` khi consumer dùng `-exec.jar` như dependency | App classes ở `BOOT-INF/classes` | Dùng plain JAR hoặc tách `api` module |
| Chỉ có một JAR sau package | `classifier` chưa áp dụng đúng execution, repackage không chạy | Effective POM, parent `repackage` execution id, build logs |
| Chỉ main JAR xuất hiện ở repository | `attach=false` hoặc classifier không được attach | Boot plugin `attach`, Maven install/deploy log và remote files |
| Hai JAR có version khác | POMs/modules/profile/job khác | `mvn help:evaluate`, selected module, build revision |
| Không resolve `classifier=exec` | Remote repo thiếu attached artifact hoặc metadata classifier | `maven-metadata.xml`, artifact paths và repository permissions |
| SNAPSHOT resolve khác hôm qua | Remote metadata đã trỏ deployment mới, local cache/update policy | Snapshot timestamp/buildNumber, `mvn -U`, checksums |
| Release repo không nhận SNAPSHOT | Repository policy từ chối snapshots | Kiểm tra `distributionManagement.snapshotRepository` |
| Snapshot repo không nhận release | Repository policy từ chối non-SNAPSHOT | Kiểm tra `distributionManagement.repository` |
| `mvn deploy` báo missing distributionManagement | POM thiếu repository đích và không có alt deployment configuration | POM/effective POM, deploy-plugin docs |
| HTTP 401/403 khi deploy | Credentials/server ID/permission không khớp | Maven settings, credential store, repository policy |
| HTTP 400/409 khi deploy release | Version đã tồn tại hoặc repository từ chối overwrite/policy | Xem response và phát hành version mới khi cần |
| `mvn install` thành công nhưng người khác không thấy artifact | Chỉ local repository được cập nhật | Dùng remote deploy/publish được phê duyệt |
| Lệnh `versions:set` không cập nhật modules | Parent/child references hoặc scope chưa được xử lý | Versions Plugin args, inspect all POM diffs |
| Repo có `-sources.jar` nhưng không có exec | Attachments do nhiều plugins khác nhau quản lý | Spring Boot `classifier=exec`/`attach` và execution |
| `finalName` đổi, Maven consumer không tìm file | Nhầm local filename với GAV/repository naming | Kiểm tra coordinates của publication |
| Release same version nhưng SHA thay đổi | Rebuild/overwrite artifact, dependency/plugin/time không kiểm soát | Repo immutability, provenance, checksums |
| Snapshot timestamp có `-3` nhưng POM version vẫn SNAPSHOT | Hành vi unique snapshot bình thường | Repository metadata mapping |
| CI kiểm tra JAR A nhưng upload JAR B | `mvn deploy` re-run lifecycle hoặc jobs build độc lập | Hash before/after, stage artifact và verify remote |
| Parent `packaging=pom` không có exec JAR | Parent chỉ aggregator/BOM | Chỉ repackage service module có main |
| Gradle bootJar build xanh nhưng không publish | Publication thiếu task artifact `bootJar` | `maven-publish` configuration, remote contents |

Khi gặp lỗi, điều tra theo thứ tự: **effective POM/version → mục tiêu classifier → local target artifacts → manifest/layout → install/deploy logs → repository files/metadata → runtime artifact hash**. Đừng đổi ngẫu nhiên `classifier` hay pin một timestamped snapshot làm project version chỉ để vượt một lỗi resolver.

## 18. Checklist và câu hỏi tự kiểm tra

### Checklist trước khi phát hành

- [ ] Xác định chính xác `groupId`, `artifactId`, `version`, `packaging`.
- [ ] Quyết định rõ artifact nào là **main JAR**, artifact nào là **exec JAR**, và consumers dùng loại nào.
- [ ] Nếu cần cả hai, `repackage` dùng `classifier=exec` với `attach=true`.
- [ ] Build sạch; kiểm tra manifest/`BOOT-INF` và chạy đúng `-exec.jar`.
- [ ] Lưu SHA-256 riêng của main, exec, sources/Javadocs nếu phát hành.
- [ ] SNAPSHOT chỉ dùng cho luồng phát triển phù hợp, không dùng làm khóa immutable production.
- [ ] Release version được bảo vệ khỏi overwrite, gắn với Git commit/tag và artifact bytes.
- [ ] Repository `snapshotRepository`/`repository` và permissions đúng loại version.
- [ ] Credentials chỉ ở secrets/settings, không commit token vào POM.
- [ ] `mvn install` local khác `mvn deploy` remote; không dùng thay thao tác deploy app.
- [ ] Với multi-module, version và execution/classifiers nhất quán từng module.
- [ ] CI verify **đúng file sẽ publish**, đối chiếu repository artifacts sau deploy.
- [ ] Đã xác định rollback bằng **artifact immutable** chứ không phải rebuild cùng version.

### Tự kiểm tra

**Câu A.** `1.4.0-SNAPSHOT` và `1.4.0` có phải cùng Maven version?

**Trả lời:** Không. Đây là hai version identifiers khác nhau. `-SNAPSHOT` cho phép resolution/deployment theo snapshot metadata, còn release thường được quản lý immutability riêng.

**Câu B.** Local file `release-demo-1.4.0-SNAPSHOT-exec.jar` có nhất thiết giữ tên này trên remote repository?

**Trả lời:** Không. Remote snapshot repository có thể dùng unique timestamped filename như `release-demo-1.4.0-20261109.031405-3-exec.jar`, trong khi POM logical version vẫn `1.4.0-SNAPSHOT`.

**Câu C.** Vì sao Spring Boot executable JAR có classifier `exec` không phải dependency JAR thông thường?

**Trả lời:** App classes nằm trong `BOOT-INF/classes`, nested dependencies trong `BOOT-INF/lib`, được Boot launcher nạp khi `java -jar`. Dependent module dùng Java classpath thông thường nên dùng plain JAR hoặc API module.

**Câu D.** `attach=false` có ảnh hưởng đến file local hay repository?

**Trả lời:** Repackaged JAR có thể vẫn được tạo ở local target, nhưng không được attach để install/deploy như classifier artifact. Phải kiểm tra actual output và remote contents.

**Câu E.** Thay `<finalName>app</finalName>` có tạo Maven artifactId `app` không?

**Trả lời:** Không. Nó đổi local filename, còn Maven GAV vẫn theo `groupId`, `artifactId`, `version` trong POM.

**Câu F.** Tại sao cùng Git tag và version release chưa đủ chứng minh artifact được publish giống bytes đã kiểm thử?

**Trả lời:** Hai build từ một commit có thể khác timestamps/dependencies, và deploy phase có thể chạy lại packaging. Cần lưu/đối chiếu checksums của đúng artifact và remote download/promotion.

**Câu G.** `mvn install` có làm ứng dụng mới xuất hiện trên server production không?

**Trả lời:** Không. Nó chỉ cài artifacts vào Maven local repository. Publish lên repository dùng `deploy`; deploy ứng dụng vào runtime là workflow khác nữa.

**Câu H.** `maven-metadata.xml` trong SNAPSHOT repo dùng classifier để làm gì?

**Trả lời:** Metadata phân biệt các biến thể qua `classifier + extension` khi ánh xạ logical SNAPSHOT sang timestamped version. Main JAR và `exec` JAR là hai sub-artifacts khác nhau dù cùng base version.

## 19. Tài liệu chính thức

- Maven — POM Reference (coordinates, packaging, distributionManagement): https://maven.apache.org/pom.html
- Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — Maven Repository Layout (classifier và extension): https://maven.apache.org/repository/layout.html
- Maven — Maven Repository Metadata: https://maven.apache.org/repositories/metadata.html
- Maven — Repository Metadata Model (timestamp, buildNumber, snapshotVersion): https://maven.apache.org/ref/3-LATEST/maven-repository-metadata/repository-metadata.html
- Maven — Deploy Plugin Usage: https://maven.apache.org/plugins/maven-deploy-plugin/usage.html
- Maven — Deploy Plugin Network/Local Staging: https://maven.apache.org/plugins/maven-deploy-plugin/examples/deploy-network-issues.html
- Maven — Settings Reference (servers, credentials and repositories): https://maven.apache.org/settings.html
- Maven — Maven Release Plugin / Prepare a Release: https://maven.apache.org/maven-release/maven-release-plugin/usage/prepare-release.html
- Maven — Versions Plugin (set project version): https://www.mojohaus.org/versions/versions-maven-plugin/set-mojo.html
- Spring Boot 3.5 — Packaging Executable Archives (repackage, classifier, attach): https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Maven Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/
- Java 17 — JarFile API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html

**Kết luận:** `version` trả lời **đây là bản phát hành nào**, `-SNAPSHOT` báo **đây là version phát triển có thể thay đổi**, còn `classifier` phân biệt **biến thể artifact** trong cùng GAV. Với Spring Boot, `classifier=exec` giúp giữ main JAR làm library và executable JAR làm sản phẩm chạy. Hãy kiểm tra **cả hai files**, chỉ publish lên đúng snapshot/release repository theo policy, lưu checksum/commit và đảm bảo production triển khai **chính bytes đã được nghiệm thu**, không chỉ một tên version dễ nhớ.