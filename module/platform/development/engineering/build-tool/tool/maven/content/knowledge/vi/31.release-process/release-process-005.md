# Staging, kiểm chứng và công bố artifact theo cơ chế của kho đích

## 1. Vì sao phát hành artifact không chỉ là mvn deploy?

Khi phát triển thư viện Java với Maven, `mvn clean package` tạo artifact, `mvn verify` chạy các kiểm chứng được cấu hình, `mvn install` cài artifact vào local Maven repository, còn `mvn deploy` đưa artifact/POM tới remote repository. Nhưng **remote deployment không tự đồng nghĩa với công bố phiên bản đã được kiểm duyệt**.

Một quy trình release có kiểm soát thường có ba chặng:

1. **Stage**: đưa một bộ artifact ứng viên vào vùng tạm hoặc dịch vụ nhận bundle, chưa mở cho toàn bộ consumers.
2. **Verify**: kiểm tra binary, POM metadata, GAV, dependencies, source/Javadoc, chữ ký, checksums, security rules và khả năng consumer tải/chạy được.
3. **Publish/Promote/Release**: thực hiện thao tác cuối **theo cơ chế riêng của kho đích** để bản đã duyệt trở nên có thể tiêu thụ.

Cơ chế khác nhau đáng kể:

- **Maven Central Publisher Portal**: upload bundle, server validation, rồi **Publish** thủ công hoặc tự động; `VALIDATED` chưa phải `PUBLISHED`.
- **Nexus Repository có tính năng Staging**: tổ chức có thể upload tới hosted staging repo, gắn component tags và promote/move sang target repository theo entitlements/API đang có.
- **JFrog Artifactory**: có **Build Promotion** từ published build-info; thao tác có thể copy/move artifact sang repo khác, hoặc chỉ cập nhật trạng thái.
- **Remote Maven hosted repo thuần**: `mvn deploy` có thể upload trực tiếp vào release repository mà không có approval stage nào. Nếu URL cho consumer truy cập ngay, về thực tế đó đã là một bước publish.

**Không dùng `BUILD SUCCESS` của một lệnh để tuyên bố mọi chặng đều xong.** Thành công của `mvn deploy` với Central plugin có thể chỉ nghĩa là bundle đã được upload và `VALIDATED`, đang đợi người dùng Publish.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Tách Maven lifecycle khỏi workflow staging/verification/publication.
2. Phân biệt release candidate, SNAPSHOT, release GAV và immutable artifact.
3. Liệt kê các release gates cần vượt qua.
4. Tạo project Maven Java 17 với JUnit test và main JAR có thể kiểm tra được.
5. Dùng Maven Deploy Plugin và `distributionManagement` đúng vai trò.
6. Thực hiện consumer smoke test từ một staging repository thay vì dựa vào local reactor.
7. Tính và so sánh SHA-256 giữa ứng viên và artifact đã phát hành bằng Java 17.
8. Hiểu Central Portal states, `autoPublish` và `waitUntil`.
9. Chọn đúng Nexus Staging hoặc Artifactory Build Promotion, không nhầm API cũ với API mới.
10. Kiểm soát metadata, GPG signatures, checksums, approvals, provenance và rollback.
11. Chẩn đoán lỗi validation, 401/403/409, thiếu dependencies và không tìm thấy artifact sau publish.
12. Thiết kế CI phát hành mà không rebuild một JAR khác sau khi candidate đã được duyệt.

## 2. Quy trình tổng quát: build once, verify, promote exactly the same bytes

~~~text
Git commit/tag -> build environment được cố định
        |
        v
  mvn clean verify
        |
        +--- tests / static checks / license / security / SBOM
        |
        v
  Release candidate: artifact set + POM + metadata
        |
        +--- SHA-256 / signatures / provenance
        |
        v
  Upload vào staging / Portal deployment
        |
        v
  Repository validation + consumer smoke test
        |
        +--- FAIL -> hủy candidate hoặc sửa -> build lại và QA lại
        |
        v
  Approval / policy gate
        |
        v
  Publish hoặc promote bằng tính năng kho đích
        |
        v
  Kiểm tra PUBLISHED và consumer download
        |
        v
  Lưu release evidence và thông báo phiên bản
~~~

Nguyên tắc là **không build lại artifact sau khi đã kiểm thử candidate**. Nếu bạn kiểm `stage-lib-1.0.0.jar` ở staging rồi chạy lại build trước khi phát hành, JAR sau có thể khác bytes do generated timestamps, JDK, dependencies, environment hay source thay đổi. Khi kho hỗ trợ server-side promotion, promote/copy/move **đúng bytes** đã qua gate; nếu không hỗ trợ, giữ hash và kiểm lại tất cả bytes sau upload cuối.

Một version `1.0.0` được public phải coi là **immutable** theo policy phù hợp. Maven Central nhấn mạnh không thay thế/xóa những component đã công bố. Khi phát hiện lỗi sau public, thông thường phát hành `1.0.1` và thông báo consumers, thay vì ghi đè `1.0.0`.

### 2.1. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Không được suy ra |
| --- | --- | --- |
| Release candidate | Một bộ files đang được đánh giá | Không bắt buộc version chứa `-RC` |
| Stage | Khu vực/đối tượng deployment chưa được duyệt công khai | Không có API thống nhất giữa các kho |
| Validation | Server-side kiểm tra bundle, metadata, policy | Không chứng minh code không có bug |
| Verification | QA của team, dependency tests, signatures, hashes | Không thay thế published state |
| Promotion | Dời/copy/đổi stage của artifact được duyệt | Không phải Maven core goal |
| Publication | Kho đích mở artifact cho consumers | Không bảo đảm search index cập nhật ngay |
| SNAPSHOT | Version phát triển có thể đổi/được dọn theo retention | Không phù hợp public immutable release |
| GAV | `groupId:artifactId:version` | Không tự chứng minh nguồn gốc hay bytes |

### 2.2. Không coi 1.0.0-RC1 là staging riêng tư

Một version `1.0.0-RC1` không kết thúc bằng `-SNAPSHOT`. Maven/repository có thể xử lý nó như một release version. Nếu upload thẳng lên public Maven Central, nó cũng có thể trở thành artifact immutable dù mang chữ RC. **Quyền truy cập và trạng thái của kho** mới xác định ứng viên có private hay chưa.

### 2.3. SNAPSHOT và release có chính sách khác

Một `1.0.0-SNAPSHOT` được dùng cho iteration, có snapshot metadata, timestamped instances và retention policy. SNAPSHOT publishing của Central Portal là một cơ chế riêng, không qua cùng release validation workflow. Để staging một release `1.0.0` trước khi công bố, sử dụng cơ chế **validated deployment** hoặc hosted staging repo, không biến snapshot repository thành cổng publish release không kiểm soát.

## 3. Các release gates bắt buộc suy xét

| Gate | Kiểm tra | Bằng chứng thường lưu |
| --- | --- | --- |
| G0 — Identity | Commit/tag, GAV, version, builder, JDK/Maven/plugin versions | Git SHA, build ID, effective POM |
| G1 — Build quality | Compile, unit/integration tests, static checks | Test reports, CI job logs |
| G2 — Artifact set | Main JAR/POM, classifiers, source/Javadoc nếu đích yêu cầu | Bundle listing, artifact manifest |
| G3 — Integrity | SHA-256, file size, GPG signatures, provenance | Digest records, verification logs |
| G4 — Metadata | POM GAV, dependencies, scopes, parent/BOM, license/SCM/developers | Released POM, policy validation |
| G5 — Consumer smoke test | Tải đúng GAV từ staging bằng consumer ngoài reactor/cache riêng | Dependency tree, compile/run logs |
| G6 — Approval | Quyền, security/license policy, release reviewer | Approval ID, policy decisions |
| G7 — Publication | Kho báo published/promoted, consumer tải public được | Deployment ID, URLs, post-release check |

Không phải kho nào cũng tự kiểm tất cả gates. Maven Central thường kiểm bundle signatures, checksums và POM requirements; nó không chạy toàn bộ unit/integration tests hoặc đánh giá mọi vulnerability của ứng dụng của bạn. Tổ chức phải áp dụng những kiểm chứng cần thiết trước khi Publish.

### 3.1. Bộ files cần phát hành

Ví dụ Maven Central cho một library JAR có thể yêu cầu:

~~~text
stage-lib-1.0.0.jar
stage-lib-1.0.0.pom
stage-lib-1.0.0-sources.jar
stage-lib-1.0.0-javadoc.jar
stage-lib-1.0.0.jar.asc
stage-lib-1.0.0.pom.asc
stage-lib-1.0.0-sources.jar.asc
stage-lib-1.0.0-javadoc.jar.asc
stage-lib-1.0.0.jar.md5
stage-lib-1.0.0.jar.sha1
...
~~~

Trường `...` chỉ biểu thị còn các checksum của những files khác; **không phải tên file thực**. Central yêu cầu MD5/SHA1 checksum files và chấp nhận SHA256/SHA512; Central Publishing Plugin có thể tạo checksums. Những chữ ký `.asc` cần được ký bằng key hợp lệ do publisher quản lý. Mỗi loại kho nội bộ có thể có rules khác nhau; không áp yêu cầu của Central cho mọi Artifactory/Nexus một cách máy móc.

### 3.2. Maven POM là hợp đồng consumer

File JAR đúng không đủ. Published POM cần có đúng GAV và dependency graph: `scope`, `optional`, `exclusions`, version, BOM/parent references. Nếu POM còn `${revision}` chưa resolved hoặc parent riêng không thể tải, consumer có thể fail ngay cả khi JAR bytecode hợp lệ.

Dùng `help:effective-pom` để hiểu build producer nhưng phải đọc **POM đã upload** và test consumer ngoài reactor. Với `flatten-maven-plugin` hoặc Maven 4 consumer POM, đừng chỉ kiểm source `pom.xml`.

## 4. Maven lifecycle và repository destination

Với project `packaging=jar`:

~~~bash
mvn -B -ntp clean package
mvn -B -ntp clean verify
mvn -B -ntp clean install
mvn -B -ntp clean deploy
~~~

- `package` tạo JAR sau compile/test theo lifecycle.
- `verify` đến phase verify, chạy goals được bind; không tự bật security scan nếu chưa cấu hình.
- `install` ghi artifact + POM vào **local Maven repository**.
- `deploy` upload artifact + POM tới **remote repository** đã khai, hoặc được plugin publishing khác xử lý.

Đích của Maven Deploy Plugin thuần thường được xác định bằng:

~~~xml
<distributionManagement>
  <repository>
    <id>candidate-stage</id>
    <url>https://repo.example.invalid/repository/libs-staging/</url>
  </repository>
  <snapshotRepository>
    <id>dev-snapshots</id>
    <url>https://repo.example.invalid/repository/libs-snapshots/</url>
  </snapshotRepository>
</distributionManagement>
~~~

**`repo.example.invalid` là địa chỉ cố ý không hoạt động**, chỉ minh họa. Không chạy `mvn deploy` bằng nguyên mẫu khi chưa thay đúng endpoint và được cấp quyền.

Maven thường chọn `repository` cho version release, `snapshotRepository` cho `-SNAPSHOT` khi được khai. ID được tra cứu trong `settings.xml`:

~~~xml
<servers>
  <server>
    <id>candidate-stage</id>
    <username>${env.MVN_RELEASE_USER}</username>
    <password>${env.MVN_RELEASE_TOKEN}</password>
  </server>
</servers>
~~~

Fragment này đặt **bên trong settings.xml hợp lệ**. Không commit secrets, không đưa token lên command line, không dùng write credential trong consumer job. Repository `<repositories>` hoặc `pluginRepositories` chỉ dùng cho dependency/plugin download, **không thay thế distributionManagement để upload**.

### 4.1. Deploy Plugin 3.x alternate destination

~~~bash
mvn -B -ntp deploy -DaltDeploymentRepository=candidate-stage::https://repo.example.invalid/repository/libs-staging/
~~~

Định dạng Deploy Plugin 3.x là `id::url`; bản 2.x cũ có `id::layout::url`, không trộn. ID thực tế khi override phải khớp `settings.servers.server.id`. Lệnh trên **chỉ minh họa syntax**, tuyệt đối không upload tới `.invalid`.

### 4.2. deployAtEnd không có atomicity

Trong multi-module reactor, `maven-deploy-plugin` có `deployAtEnd` để trì hoãn các deployment đến gần cuối build. Tuy nhiên nó **không bảo đảm all-or-nothing**; một phần artifacts có thể đã lên repo trước khi phần khác fail và Maven không rollback tự động. Với nhiều modules liên kết chặt, dùng cohort/bundle feature của kho hoặc một quy trình kiểm tra partial publication.

## 5. Lab Java 17: tạo một release candidate có thể kiểm chứng

Lab này tạo JAR có GAV `dev.example.release:stage-lib:1.0.0`, JUnit 5 test và một chương trình so SHA-256. Nó có thể **build local** không cần repository manager và token. Upload/promotion chỉ minh họa và yêu cầu môi trường được cho phép.

### 5.1. Cấu trúc

~~~text
stage-release-lab/
├── pom.xml
├── src/
│   ├── main/java/dev/example/release/ReleaseGreeting.java
│   └── test/java/dev/example/release/ReleaseGreetingTest.java
└── tools/
    └── CompareReleaseBytes.java
~~~

Yêu cầu Maven 3.9.x, JDK 17+, mirror/repository có thể tải plugins và JUnit. Những sample URL `.invalid` khiến deploy remote **không thể chạy nguyên xi**; đây là cách tránh accidental publication.

### 5.2. POM đầy đủ cho lab build local

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example.release</groupId>
    <artifactId>stage-lib</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Staging Release Lab</name>
    <description>Learning artifact for an authorized staging pipeline</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <distributionManagement>
        <repository>
            <id>candidate-stage</id>
            <url>https://repo.example.invalid/repository/libs-staging/</url>
        </repository>
        <snapshotRepository>
            <id>dev-snapshots</id>
            <url>https://repo.example.invalid/repository/libs-snapshots/</url>
        </snapshotRepository>
    </distributionManagement>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

POM này là **runnable để compile/test/package**, nhưng **chưa đủ điều kiện public lên Maven Central**: namespace `dev.example.release` là mẫu, không có xác nhận chủ sở hữu; project metadata, source/Javadoc, signatures chưa được chuẩn bị. Fragment bổ sung cho Central ở mục 8.

### 5.3. Java class chính

`src/main/java/dev/example/release/ReleaseGreeting.java`:

~~~java
package dev.example.release;

public final class ReleaseGreeting {
    private ReleaseGreeting() {
    }

    public static String hello(String name) {
        String safe = name == null || name.isBlank()
                ? "world"
                : name.trim();
        return "Release ready, " + safe + "!";
    }

    public static void main(String[] args) {
        System.out.println(hello("Maven"));
    }
}
~~~

### 5.4. JUnit 5

`src/test/java/dev/example/release/ReleaseGreetingTest.java`:

~~~java
package dev.example.release;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ReleaseGreetingTest {

    @Test
    void normalizesNames() {
        assertEquals("Release ready, Maven!",
                ReleaseGreeting.hello(" Maven "));
        assertEquals("Release ready, world!",
                ReleaseGreeting.hello("  "));
        assertEquals("Release ready, world!",
                ReleaseGreeting.hello(null));
    }
}
~~~

### 5.5. Build và kiểm tra

Từ thư mục `stage-release-lab`:

~~~bash
java -version
mvn -version
mvn -B -ntp clean verify
java -cp target/classes dev.example.release.ReleaseGreeting
jar tf target/stage-lib-1.0.0.jar
~~~

Với source và dependencies đúng, test log thường có:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Stdout **của riêng chương trình Java** (không gồm Maven log):

~~~text
Release ready, Maven!
~~~

Những entries quan trọng trong JAR:

~~~text
META-INF/MANIFEST.MF
dev/example/release/ReleaseGreeting.class
META-INF/maven/dev.example.release/stage-lib/pom.xml
~~~

Archive có thể thêm directory entries và metadata khác. JUnit tests không được đóng vào main JAR. Không chạy `java -jar target/stage-lib-1.0.0.jar` vì POM chưa khai `Main-Class` trong manifest.

## 6. Java 17: kiểm tra artifact không bị đổi bytes khi promote

Mỗi release candidate nên lưu SHA-256. Sau promotion, tải lại file từ **repo đã công bố** và so với staged file hoặc hash được lưu từ staging.

Tạo `tools/CompareReleaseBytes.java`:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;

public final class CompareReleaseBytes {
    private CompareReleaseBytes() {
    }

    private static byte[] sha256(Path path) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        try (InputStream in = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            int n;
            while ((n = in.read(buffer)) != -1) {
                md.update(buffer, 0, n);
            }
        }
        return md.digest();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: CompareReleaseBytes <staged> <published>");
            System.exit(2);
        }

        byte[] before = sha256(Path.of(args[0]));
        byte[] after = sha256(Path.of(args[1]));
        boolean same = Arrays.equals(before, after);

        System.out.println("STAGED SHA-256: "
                + HexFormat.of().formatHex(before));
        System.out.println("PUBLISHED SHA-256: "
                + HexFormat.of().formatHex(after));
        System.out.println("MATCHING SHA-256: " + same);

        if (!same) {
            System.exit(3);
        }
    }
}
~~~

Biên dịch và smoke test tool bằng cách đối chiếu file với chính nó:

~~~bash
javac -d target/check-tools tools/CompareReleaseBytes.java
java -cp target/check-tools CompareReleaseBytes target/stage-lib-1.0.0.jar target/stage-lib-1.0.0.jar
~~~

Dòng cuối của stdout **chắc chắn là**:

~~~text
MATCHING SHA-256: true
~~~

Hai dòng SHA-256 phía trước **khác nhau theo bytes của build thực tế**, không có một hash mẫu cố định nên không bịa stdout đầy đủ. **Lệnh same-file chỉ chứng minh chương trình hoạt động, chưa chứng minh repo promotion thành công.**

Sau publish, tải JAR từ staging và public/release repo bằng cơ chế được phép, rồi chạy:

~~~bash
java -cp target/check-tools CompareReleaseBytes path/to/staged/stage-lib-1.0.0.jar path/to/published/stage-lib-1.0.0.jar
~~~

Nếu repo **move** không giữ bản staging, hãy lưu hash trước khi promote và so với published hash sau đó. Hash khớp giúp xác nhận cùng bytes, nhưng không tự chứng minh authenticity; signature validation là gate riêng.

## 7. Kiểm chứng candidate qua Maven consumer ngoài reactor

Một producer có `BUILD SUCCESS` vẫn có thể phát hành POM sai `scope`, thiếu transitive dependencies hoặc parent không tải được. Cần dùng **consumer project** chỉ khai library GAV từ staging repository.

### 7.1. Consumer POM đầy đủ

Tạo một project riêng `stage-consumer/pom.xml`, **không đặt trong producer reactor**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example.consumer</groupId>
    <artifactId>stage-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>dev.example.release</groupId>
            <artifactId>stage-lib</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `stage-consumer/src/main/java/dev/example/consumer/ConsumerMain.java`:

~~~java
package dev.example.consumer;

import dev.example.release.ReleaseGreeting;

public final class ConsumerMain {
    private ConsumerMain() {
    }

    public static void main(String[] args) {
        System.out.println("CONSUMER: "
                + ReleaseGreeting.hello("Maven"));
    }
}
~~~

### 7.2. Cấu hình nơi đọc candidate

Với repo private staging, consumer cần repository URL và quyền **read-only**. Đoạn fragment settings sau chỉ minh họa:

~~~xml
<profiles>
  <profile>
    <id>stage-read</id>
    <repositories>
      <repository>
        <id>stage-read</id>
        <url>https://repo.example.invalid/repository/libs-staging-read/</url>
        <releases><enabled>true</enabled></releases>
        <snapshots><enabled>false</enabled></snapshots>
      </repository>
    </repositories>
  </profile>
</profiles>
<activeProfiles>
  <activeProfile>stage-read</activeProfile>
</activeProfiles>
~~~

Ghép fragment này vào một `settings.xml` có root hợp lệ. Nếu repo có auth, khai thêm `server.id=stage-read` với **read token**. Đường repo `.invalid` phải thay bằng nơi được cấp quyền.

Trong thư mục `stage-consumer`:

~~~bash
mvn -B -ntp -s /secure/path/stage-read-settings.xml -Dmaven.repo.local=./.m2-candidate clean compile
mvn -B -ntp -s /secure/path/stage-read-settings.xml -Dmaven.repo.local=./.m2-candidate org.codehaus.mojo:exec-maven-plugin:3.6.4:java -Dexec.mainClass=dev.example.consumer.ConsumerMain
~~~

`-Dmaven.repo.local=./.m2-candidate` dùng cache riêng để tránh Maven vô tình resolve library được `mvn install` trước đó trên máy producer. Lệnh chỉ chạy được sau **upload candidate** tới repository thật và cấu hình settings hợp lệ.

Stdout của consumer khi đúng:

~~~text
CONSUMER: Release ready, Maven!
~~~

Kiểm thêm dependency graph:

~~~bash
mvn -B -ntp -s /secure/path/stage-read-settings.xml -Dmaven.repo.local=./.m2-candidate org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Cần thấy `dev.example.release:stage-lib:jar:1.0.0` trong output. Nếu library thực tế có transitive dependencies, consumer phải resolve được chúng; đây là lý do không chỉ test producer compile.

### 7.3. Central Portal validated bundle chưa public

Khi dùng Central Portal, có **authenticated test download endpoint** cho validated deployment. Nó có thể được cấu hình như một Maven repository kiểm thử trước Publish, nhưng không đồng nghĩa candidate đã tồn tại trên public Central.

Ví dụ hình dạng endpoint theo docs:

~~~text
https://central.sonatype.com/api/v1/publisher/deployment/<deploymentId>/download/<relativePath>
~~~

Đây là mẫu URL với parameters, không phải endpoint cố định để copy nguyên vào POM. Phải cấu hình auth/token, repository và đường tương đối theo Central Publisher API.

## 8. Maven Central Publisher Portal: cơ chế công bố hiện đại

Central Portal hỗ trợ `org.sonatype.central:central-publishing-maven-plugin`. Tính đến tháng 11/2026, plugin **0.12.0** được công bố; docs mô tả `extensions=true` và `publishingServerId` để tích hợp lệnh `mvn deploy` với việc tạo/upload bundle. Nó khác Maven Deploy Plugin PUT thuần.

### 8.1. Preconditions

Để phát hành Maven Central, cần:

- Xác minh quyền sở hữu namespace/GAV; đừng dùng groupId ví dụ.
- POM chính xác với `name`, `description`, project URL, license, developers, SCM và metadata theo Central requirements.
- Binary JAR, source JAR, Javadoc JAR cho loại packaging cần.
- GPG/PGP detached signatures `.asc` và checksum files.
- Release version chưa public, không có `-SNAPSHOT` trong release publishing.
- Portal user token và quyền publish trong namespace.
- Pipeline có kiểm thử, scanner/provenance policy của chính project.

Central Publishing Plugin **không tự tạo đầy đủ sources/Javadoc JAR, GPG signatures hay các metadata POM bị thiếu**. Nó có thể tạo checksums của deployment bundle. Vì vậy không lấy `mvn deploy` với plugin cấu hình rồi mặc định đã đạt Central requirements.

### 8.2. Plugin cấu hình manual Publish

Fragment `pom.xml` dành cho một **project thực đã chuẩn bị dependencies và metadata**:

~~~xml
<plugin>
    <groupId>org.sonatype.central</groupId>
    <artifactId>central-publishing-maven-plugin</artifactId>
    <version>0.12.0</version>
    <extensions>true</extensions>
    <configuration>
        <publishingServerId>central</publishingServerId>
        <autoPublish>false</autoPublish>
        <waitUntil>validated</waitUntil>
    </configuration>
</plugin>
~~~

Đặt trong `project/build/plugins`. `autoPublish=false` giữ bước thủ công. `waitUntil=validated` yêu cầu plugin chờ server validation, **không hứa trạng thái PUBLISHED**.

Settings fragment với Portal token:

~~~xml
<servers>
    <server>
        <id>central</id>
        <username>${env.CENTRAL_TOKEN_USERNAME}</username>
        <password>${env.CENTRAL_TOKEN_PASSWORD}</password>
    </server>
</servers>
~~~

`publishingServerId` phải khớp settings `server.id`. Không ghi token literal trong POM/Git/log. Đừng chạy POM lab `dev.example.release` lên Central vì không sở hữu namespace và chưa đủ metadata.

### 8.3. Thêm sources, Javadoc và GPG theo yêu cầu

Một project public release thường thêm các Maven plugins sau, **đây là fragments, không phải project standalone**:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-source-plugin</artifactId>
    <version>3.3.1</version>
    <executions>
        <execution>
            <id>attach-sources</id>
            <goals><goal>jar-no-fork</goal></goals>
        </execution>
    </executions>
</plugin>

<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.12.0</version>
    <executions>
        <execution>
            <id>attach-javadocs</id>
            <goals><goal>jar</goal></goals>
        </execution>
    </executions>
</plugin>

<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-gpg-plugin</artifactId>
    <version>3.2.8</version>
    <executions>
        <execution>
            <id>sign-artifacts</id>
            <phase>verify</phase>
            <goals><goal>sign</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

Cần GPG private key/passphrase được bảo vệ và đúng release identity; các plugins/phase order phải thực sự tạo/attach đúng files. Chạy build rồi **kiểm tra bundle thật**, không chỉ POM cấu hình. Các fragments trên **không tự làm POM lab đủ điều kiện Maven Central**, vẫn phải bổ sung metadata và xác minh namespace.

### 8.4. Những trạng thái Central Portal cần hiểu

| State | Ý nghĩa |
| --- | --- |
| `PENDING` | Bundle upload xong, đang chờ xử lý |
| `VALIDATING` | Server kiểm tra bundle |
| `VALIDATED` | Checks đã qua; nếu manual thì chờ người có quyền Publish |
| `PUBLISHING` | Đang phát hành |
| `PUBLISHED` | Portal đã công bố component lên Central |
| `FAILED` | Có lỗi; đọc reasons/errors |

Với `autoPublish=false`, lệnh `mvn deploy` **có thể in BUILD SUCCESS khi state mới là VALIDATED**, như ví dụ trong tài liệu Central. Khi đó người có quyền phải vào Central Portal → Publishing/Deployments và chọn **Publish**. Nếu bundle lỗi, xử lý validation reason; `FAILED` không đồng nghĩa release public.

### 8.5. Automatic publishing có điều kiện

Khi tổ chức đã có upstream gates và cho phép tự động:

~~~xml
<configuration>
    <publishingServerId>central</publishingServerId>
    <autoPublish>true</autoPublish>
    <waitUntil>published</waitUntil>
</configuration>
~~~

`autoPublish=true` để portal phát hành sau khi validation thành công. `waitUntil=published` chờ công bố xong; `waitUntil=validated` chỉ chờ validation. **Không bật autoPublish để bypass một manual approval bắt buộc**.

### 8.6. Drop và immutability

Central Publisher API hỗ trợ **Drop** những deployment ở state cho phép như `VALIDATED`/`FAILED` chưa public. Nếu cần hỗ trợ lỗi, giữ deployment ID/logs/files theo hướng dẫn support thay vì Drop ngay. Sau khi `PUBLISHED`, Central public releases được coi là immutable; thông thường không xóa/overwrite như chỉnh một file ở FTP.

### 8.7. OSSRH đã sunset

Dịch vụ **OSSRH legacy đã chấm dứt vào 30/06/2025**. Các hướng dẫn cũ “oss.sonatype.org → Close staging → Release” không còn là quy trình mặc định cho Maven Central.

Sonatype có **OSSRH Staging API compatibility service**, mô phỏng **một phần** API Nexus Repository 2 cho các plugin legacy như `nexus-staging-maven-plugin`. Đây là lớp tương thích dẫn về Central Portal, không phải OSSRH cũ. Có thể có bước close/manual upload riêng tùy plugin; không dùng endpoints/tokens OSSRH cũ nếu docs yêu cầu Portal user token.

### 8.8. SNAPSHOT publishing

Central Portal hỗ trợ snapshots qua endpoint/cơ chế riêng; docs có URL:

~~~text
https://central.sonatype.com/repository/maven-snapshots/
~~~

SNAPSHOT có retention và không qua cùng release validation guarantees. Không dùng nó làm nơi vĩnh viễn chứng minh `1.0.0` đã duyệt.

## 9. Nexus Repository: staging theo hosted repositories và tags

Nexus Repository có tính năng **Staging** cho editions/entitlements phù hợp. Sonatype docs mô tả các thành phần **hosted repositories**, **component tags** và **REST endpoints** phục vụ promotion.

Một mô hình:

~~~text
libs-staging (hosted)
      |
      v
Component tag: release-1.0.0-build-246
      |
      v
QA / dependency / vulnerability checks
      |
  approval
      |
      v
Server-side promote/move
      |
      v
libs-release (hosted)
      |
      v
consumer via release/group URL
~~~

Những điểm phải xác minh trước khi triển khai:

1. Edition/entitlement/version Nexus thực có Staging feature không.
2. Repo staged có bị vô tình đưa vào group public/readable không.
3. API/role có đủ quyền tag/move/copy/discard không.
4. Policies target (snapshot/release, redeploy forbidden) phù hợp GAV.
5. Promotion có bao gồm main artifact, POM, classifiers và metadata cần thiết không.
6. Hash/bằng chứng release có thể đối chiếu trước và sau.
7. Có audit logs/approver và rollback strategy không.

**Không tự giả định mọi Nexus Repository 3 có UI Close/Release giống Nexus Repository Manager 2 hoặc OSSRH cũ.** Những hướng dẫn `nexus-staging-maven-plugin` thường gắn với Nexus 2 API/OSSRH; phải phân biệt với Nexus Staging tính năng mới và Central Portal.

Nếu instance Nexus không có Staging entitlement, có thể tự tổ chức **hai hosted repositories** và gate riêng nhưng không được gọi đó là transaction promotion tự động; phải kiểm tra product capabilities thực tế.

## 10. JFrog Artifactory: Build Promotion khác Maven deploy

Artifactory lưu artifacts và có cơ chế **Build-info** ghi identity build (name + number), artifacts và dependencies liên quan. Sau verify, có thể **promote build** sang target repository.

Ví dụ identity minh họa:

~~~text
Build name   : stage-lib-release
Build number : 246
Source repo  : libs-staging-local
Target repo  : libs-release-local
~~~

Lệnh JFrog CLI khi build-info thật đã tồn tại, server đã cấu hình và người dùng được phép:

~~~bash
jf rt build-promote stage-lib-release 246 libs-release-local --dry-run
jf rt build-promote stage-lib-release 246 libs-release-local --copy
~~~

`--dry-run` xem scope trước; `--copy` giữ source artifacts, còn mặc định CLI thường **move**. Không chạy operation thật trên repo không thuộc quyền hoặc khi chưa có approval.

### 10.1. Vì sao phải có build-info?

`mvn deploy` có thể upload POM/JAR vào Artifactory, nhưng **không tự bảo đảm published build-info đã tồn tại** theo format mà Build Promotion cần. JFrog CLI/CI integrations hoặc REST workflow phải ghi build-info, đảm bảo artifact membership đúng. Nếu lệnh `jf rt bpr` báo build not found, kiểm tra build name/number và build-info, không tự đổi GAV hay overwrite file.

### 10.2. Copy/move không phải lúc nào là toàn bộ release

Cần kiểm tra những files build-info liên kết: JAR/POM, source/Javadoc JAR, checksums/classifiers. Promotion chỉ được phép công bố những files chính xác thuộc release candidate. Nếu upload POM ngoài build-info và promotion bỏ sót, consumer có thể thất bại.

### 10.3. Phân biệt Build Promotion và Release Lifecycle Management

**Build Promotion** là thao tác build-info → target repository; **Release Lifecycle Management (RLM) / Release Bundle v2** là luồng sản phẩm khác. JFrog đã thông báo deprecation của RLM từ **31/07/2026** và mốc EOL dự kiến **31/01/2028**. Vì vậy quy trình mới cần xem roadmap hiện tại, không dùng RLM API chỉ vì một tutorial cũ. Build Promotion CLI/REST vẫn cần kiểm tra theo docs/edition hiện hành.

## 11. Bảng chọn cơ chế kho đích

| Kho đích | Stage | Verify | Công bố cuối |
| --- | --- | --- | --- |
| Maven Central Portal | Upload bundle bằng Central plugin/Publisher API | Portal validation + team gates | Manual Publish hoặc autoPublish |
| Nexus Staging | Hosted staged repo + component tags | Repo rules/CI/consumer | Promote/move qua Nexus API |
| Artifactory | Maven uploads + published build-info | Policy/Xray (nếu có) + consumer | `jf rt build-promote` / REST |
| Hosted Maven repo không staging | Có thể không có stage độc lập | Pre-deploy gates là bắt buộc | `mvn deploy` trực tiếp |
| Central SNAPSHOT | Upload snapshot riêng | Không có release validation như stable | Snapshot available, có thể cleanup |

Một pipeline có thể phối hợp: candidate nội bộ → QA → Central Portal. Nhưng Central Portal vẫn cần GPG/POM/checksum requirements và Publish; **promote ở Artifactory không có nghĩa artifact tự xuất hiện trên Maven Central**.

## 12. Thiết kế CI và quyền hạn

Mô hình các jobs:

~~~text
build-candidate
  -> unit/integration/static checks
  -> attach source/Javadoc/signatures (nếu cần)
  -> record build ID + SHA-256 + source commit
  -> stage-upload
  -> server-validation
  -> consumer-from-stage
  -> security/license/SBOM policy gate
  -> approval
  -> promote/Publish
  -> wait for actual published state
  -> consumer-from-released-repository
  -> release evidence
~~~

### 12.1. Tách read/write/publish roles

- Build job: quyền **read** dependencies/plugins.
- Stage job: quyền upload candidate, không cần quyền public release.
- QA job: quyền đọc staging, không có production write token.
- Approver/publish job: quyền publish/promote theo protected environment.
- Consumer verify job: read-only đúng repository public.

Không cung cấp release token cho pull request từ fork hoặc branch chưa tin cậy. Dùng CI secrets manager và masked/protected variables. `settings.xml` của Maven chứa server IDs/credentials và phải được cấp ở runtime; không commit password/token vào source POM hoặc logs.

### 12.2. Multi-module và partial publish

`maven-deploy-plugin:deployAtEnd=true` giúp trì hoãn các uploads, nhưng không tạo atomic transaction. Một module có thể đã public trước khi module kế tiếp fail. Nếu release nhiều GAV cần đồng bộ, sử dụng bundle/cohort functionality của repo và kiểm tra trạng thái của **toàn bộ** artifact set trước khi mở quyền đọc.

### 12.3. Provenance và release evidence

Lưu:
- Git commit/tag và release approver.
- Build ID, builder image, JDK/Maven/plugin versions.
- GAV của tất cả modules và attachment list.
- Hashes trước và sau publish.
- GPG key fingerprint (không lưu private key).
- Test/security/license reports và SBOM nếu policy yêu cầu.
- Deployment ID, server validation state, target repo URL.
- Independent consumer test logs và thời điểm Published.
- Quyết định xử lý nếu gate FAIL.

**`BUILD SUCCESS` đơn lẻ không thể thay thế những bằng chứng này.**

## 13. Xử lý trường hợp thất bại

### 13.1. Candidate bị từ chối trước publish

- Central Portal: xem `FAILED` reasons, hoặc Drop `VALIDATED` candidate không muốn phát hành theo quyền/policy. Khi cần support, giữ bằng chứng thay vì Drop ngay.
- Nexus: discard candidate/tag theo staging workflow được cấp quyền.
- Artifactory: loại staged artifacts và/hoặc build-info theo policy; **xóa build-info không tự xóa binaries**.
- Hosted repo không stage: upload có thể đã visible, phải đánh giá consumers trước khi định xóa.

Sửa lỗi rồi build **candidate/version mới** nếu artifact content thay đổi; không chỉnh một artifact đã được duyệt rồi bỏ qua QA.

### 13.2. Đã công bố lên Maven Central nhưng phát hiện bug

Maven Central duy trì release immutability. Thông thường phát hành version mới (ví dụ `1.0.1`) rồi thông báo, chứ không ghi đè/xóa `1.0.0`. Với sự cố bảo mật nghiêm trọng, tuân theo security/advisory support process.

### 13.3. Promotion partial fail

Nếu một operation hoặc batch nhiều repositories fail giữa chừng, có thể một số files đã tồn tại ở target. Xác minh **từng GAV/file/hash** trước khi retry, tránh duplicate conflict. Không blind retry một deployment mơ hồ khi release repo cấm overwrite.

## 14. Lỗi phổ biến và cách điều tra

**1. `mvn deploy` thành công nhưng Central chưa công khai:** Với `autoPublish=false`, state có thể chỉ `VALIDATED`. Vào Central Portal Deployments xác nhận publish. Đừng chỉ dựa vào Maven `BUILD SUCCESS`.

**2. Portal `FAILED` ở validation:** Kiểm tra namespace permission, POM required fields, sources/Javadoc, GPG .asc, checksums và version đã công bố. Không bật autoPublish để bỏ validation, vì không có cơ chế bypass như vậy.

**3. `1.0.0` đã tồn tại/HTTP 409:** Release immutable hoặc duplicate component. Tạo version mới, không tự bật redeploy trên public repo.

**4. `401` hoặc `403` khi deploy:** Sai `server.id`, token hết hạn, thiếu quyền hoặc endpoint/policy sai. Xác định chính xác repository ID sau CLI overrides và settings được CI load; không log token.

**5. Maven báo missing distributionManagement:** `<repositories>` chỉ dùng download, không chọn deploy target. Khai `distributionManagement` hoặc alternative repository hợp lệ.

**6. Upload vào group/proxy URL:** Những kho này thường chỉ để đọc. Cần hosted write endpoint hoặc product-specific virtual deploy mechanism.

**7. Staging bị public trước approval:** Kiểm tra group/virtual repo đang expose staging và anonymous read access, không chỉ tên repository.

**8. Nexus không có Close/Release:** Có thể dùng Nexus 3 edition không có Staging entitlement, hoặc tutorial đang mô tả Nexus 2/OSSRH cũ.

**9. Artifactory Build Promotion không tìm được build:** Kiểm tra build-info published, build name/build number, permission và source repository.

**10. JAR public đúng tên nhưng khác staged SHA-256:** Có thể build lại, artifact cache cũ, sai GAV/path hoặc incomplete promotion. Dừng xác nhận release cho đến khi đối chiếu bytes.

**11. Consumer thiếu dependency:** POM public thiếu transitive metadata, parent/BOM unresolved, scope/exclusion sai. Test consumer trên repository/cache độc lập; không dùng local `mvn install` che lỗi.

**12. SNAPSHOT biến mất:** Snapshot có retention policy, không dùng làm archival proof của stable release.

**13. Maven Central đã `PUBLISHED` nhưng search chưa thấy:** Search indexing/mirrors có thể chậm. Kiểm tra download qua repository URL/Maven consumer thay vì chỉ search UI.

**14. Signature verify fail:** Kiểm tra public key/fingerprint, file bytes sau upload và ký đúng POM/JAR; đừng bỏ qua signature requirement để làm pipeline xanh.

**15. Missing sources/Javadoc:** Plugin attach goal chưa chạy, release profile thiếu hoặc bundle collect khác dự kiến. Inspect bundle thực, không chỉ đọc plugin configuration.

**16. Build lại sau QA làm thay bytes:** Đó là candidate khác, phải kiểm tra lại; dùng server-side promotion khi có thể.

**17. CI có quyền deploy ở laptop nhưng không ở runner:** Runner dùng settings/identity khác, protected secrets không được inject, branch không đủ quyền hoặc network proxy khác. Kiểm tra CI runtime chứ không in secret.

**18. Lỗi mạng/TLS/timeout:** Không tắt certificate validation hoặc retry bừa; xác minh endpoint, CA chain, JDK truststore, proxy, service health và trạng thái upload trước đó.

**19. Public release gặp bug nhưng không thể rollback:** Đây là đặc tính immutable release. Remediate bằng version mới/advisory chứ không hứa overwrite/delete thành công.

## 15. Bài tập có đáp án

**A.** `mvn deploy` với Central plugin `autoPublish=false` trả BUILD SUCCESS. Có đủ điều kiện nói đã public chưa?

**Đáp án:** chưa. Kiểm tra deployment state; `VALIDATED` là chờ Publish, `PUBLISHED` mới là công bố.

**B.** Vì sao không nên build lại file JAR sau khi đã test trên staging?

**Đáp án:** bytes có thể đổi; consumer sẽ nhận artifact chưa qua đúng gates. Promote cùng bytes hoặc kiểm lại candidate mới.

**C.** `1.0.0-RC1` upload thẳng Central có tự private không?

**Đáp án:** không; tên RC không tạo staging state. Kho và thao tác Publish mới quyết định.

**D.** Portal validation có thay thế unit tests không?

**Đáp án:** không. Nó kiểm rules/artifact metadata; publisher phải test code.

**E.** Nexus Repository instance nào cũng hỗ trợ staging API mới không?

**Đáp án:** không. Kiểm tra edition/entitlement, version và API được bật.

**F.** `jf rt build-promote` cần gì ngoài JAR?

**Đáp án:** build-info hợp lệ, build identity, target repo và quyền promotion.

**G.** Ý nghĩa của JFrog `--copy`?

**Đáp án:** copy artifacts sang target và giữ source, thay vì move như default thường dùng.

**H.** Vì sao consumer test nên dùng cache Maven riêng?

**Đáp án:** tránh dùng library đã cài local từ source producer, bảo đảm resolve từ staging repo.

**I.** `MATCHING SHA-256: true` chứng minh nguồn gốc người phát hành không?

**Đáp án:** không. Nó chỉ so bytes/hash; authenticity cần chữ ký và trust policy.

**J.** `deployAtEnd` có làm multi-module deploy atomic không?

**Đáp án:** không. Nó chỉ trì hoãn deployment, không bảo đảm rollback toàn bộ.

**K.** Public release có bug thì overwrite `1.0.0`?

**Đáp án:** không theo immutable policy; phát hành version mới và thông báo consumers.

**L.** Central Publishing Plugin tự sinh POM metadata/licenses và GPG signatures đầy đủ không?

**Đáp án:** không. Project phải cung cấp POM metadata, source/Javadoc và GPG ký theo requirements.

**M.** Artifactory RLM và Build Promotion có giống nhau không?

**Đáp án:** không; build-info promotion là một workflow, RLM/Release Bundle là sản phẩm/luồng khác và đã có thông báo deprecation.

**N.** `mvn install` thành công chứng minh remote staging đã có artifact?

**Đáp án:** không. Install chỉ ghi vào local Maven repository.

**O.** Nếu `PUBLISHED` nhưng chưa search thấy artifact, phải làm gì?

**Đáp án:** kiểm tra trạng thái Portal, repository download và Maven consumer; có thể có độ trễ indexing.

## 16. Checklist release

- [ ] GAV và commit/tag được xác định rõ.
- [ ] Đúng Maven/JDK/plugin versions và dependency resolution.
- [ ] `mvn clean verify` cùng required scans/tests đã chạy.
- [ ] Candidate JAR, POM, sources/Javadoc/classifiers đầy đủ theo kho đích.
- [ ] POM metadata/parent/BOM/transitive dependency graph usable.
- [ ] Signatures/checksums và SHA-256 đã được lưu.
- [ ] Staging không vô tình mở public read trước approval.
- [ ] Server-side validation đạt, errors đã xử lý.
- [ ] Consumer độc lập test từ staging và cache riêng.
- [ ] Security, SBOM, license, provenance gates theo policy.
- [ ] Người duyệt/CI environment tách quyền từ build và upload.
- [ ] Central `VALIDATED` được phân biệt với `PUBLISHED`.
- [ ] Nexus staging entitlement và promotion API đã xác minh.
- [ ] JFrog build-info và copy/move semantics đã xác minh.
- [ ] Không coi `deployAtEnd` là atomic transaction.
- [ ] Không rebuild candidate đã QA để làm release.
- [ ] Published GAV, POM, JAR và hashes được đối chiếu.
- [ ] Public consumer resolve/download thực sự thành công.
- [ ] Ghi release evidence và có kế hoạch version mới nếu phát hiện lỗi.
- [ ] Không chứa release token/private keys trong source hoặc logs.

## 17. Nguồn tham khảo

1. [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): package, verify, install, deploy.
2. [Maven Deploy Plugin — Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html): distributionManagement và upload.
3. [Maven Deploy Plugin — deploy:deploy](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html): deployAtEnd không bảo đảm atomicity, alternate repository.
4. [Maven Settings](https://maven.apache.org/settings.html): server IDs, credentials, mirrors.
5. [Maven Central — Publishing with the Maven Plugin](https://central.sonatype.org/publish/publish-portal-maven/): Central plugin 0.12.0, autoPublish, waitUntil.
6. [Maven Central — Publisher API](https://central.sonatype.org/publish/publish-portal-api/): PENDING/VALIDATING/VALIDATED/PUBLISHING/PUBLISHED/FAILED, manual Publish/Drop và validated test endpoints.
7. [Maven Central — Requirements](https://central.sonatype.org/publish/requirements/): POM metadata, sources/Javadoc, GPG và checksums.
8. [Maven Central — Immutability](https://central.sonatype.org/publish/requirements/immutability/): không overwrite public releases.
9. [Maven Central — SNAPSHOT Publishing](https://central.sonatype.org/publish/publish-portal-snapshots/): riêng snapshot lifecycle.
10. [Maven Central — OSSRH Staging API Compatibility](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/): API compatibility và migration.
11. [Maven Central — OSSRH Sunset](https://central.sonatype.org/news/20250326_ossrh_sunset/): OSSRH EOL 30/06/2025.
12. [Nexus Repository — Staging](https://help.sonatype.com/en/staging.html): hosted repositories, component tags, promotion.
13. [Nexus Repository — Staging Concepts](https://help.sonatype.com/en/staging-concepts.html): thiết kế release stages.
14. [JFrog — Manage Builds](https://docs.jfrog.com/integrations/docs/manage-builds): build-info và copy/move.
15. [JFrog — Build-info Integration](https://docs.jfrog.com/artifactory/docs/build-integration): `jf rt bpr`.
16. [JFrog — Build Promotion API](https://docs.jfrog.com/integrations/reference/promotebuild): quyền và REST operation.
17. [JFrog — RLM Deprecation](https://docs.jfrog.com/governance/docs/promote-a-release-bundle-v2-version): lifecycle product notice.
