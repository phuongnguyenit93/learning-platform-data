# Chính sách không thay thế artifact release đã công bố

## 1. Release bất biến là gì?

Trong Maven, một **release artifact đã công bố** phải tiếp tục đại diện cho đúng nội dung và metadata đã được phát hành. Không được biên dịch một JAR mới rồi ghi đè file có cùng `groupId:artifactId:version` chỉ vì muốn sửa bug, đổi dependency hoặc làm lại build.

Ví dụ, tọa độ:

```text
dev.training.release:release-guard-lab:1.0.0
```

đã được publish cho các consumer. Nếu code cần sửa, nhóm phát triển nên tạo **release version mới**, chẳng hạn `1.0.1`, và yêu cầu consumer nâng cấp khi phù hợp. Không thay `release-guard-lab-1.0.0.jar` bằng nội dung khác vẫn mang nhãn `1.0.0`.

Đây là **release immutability** hoặc **no redeploy of published release**. Maven Central quy định: sau khi một component đã release và publish, publisher không được thay đổi nội dung component; khi bản đã công bố có bug, cần công bố version mới. Tham khảo [Sonatype Central FAQ](https://central.sonatype.org/faq/can-i-change-a-component/) và [Apache Maven guide to Central](https://maven.apache.org/repository/guide-central-repository-upload).

**Quan trọng:** một shell script kiểm tra tồn tại, một khóa CI hoặc một Java check phía client không đủ để đảm bảo quy tắc. Hosted **release repository phải chặn overwrite trên server**, vì có thể nhiều CI jobs hoặc người dùng cùng upload. Trong Sonatype Nexus Repository, chính sách thích hợp là **Deployment Policy: Disable redeploy**. Tài liệu: <https://help.sonatype.com/en/configurable-repository-fields.html>.

Bài này trình bày nguyên nhân kỹ thuật, Maven coordinates, SNAPSHOT đối chiếu với release, repository policy, Maven Deploy/Release Plugin, quy trình staged publication, xử lý failure/partial upload, mô-đun reactor và **lab Java 17 + Maven** minh họa lần ghi đầu thành công nhưng cùng version bị từ chối khi ghi lần thứ hai.

## 2. Cùng GAV phải trỏ tới cùng release contract

Một Maven project dùng các tọa độ:

- **groupId**: namespace, ví dụ `dev.training.release`.
- **artifactId**: tên gói, ví dụ `release-guard-lab`.
- **version**: số hiệu release, ví dụ `1.0.0`.

Maven còn dùng extension/type và classifier để phân biệt file. Một release có thể chứa:

```text
dev/training/release/release-guard-lab/1.0.0/
    release-guard-lab-1.0.0.pom
    release-guard-lab-1.0.0.jar
    release-guard-lab-1.0.0-sources.jar
    release-guard-lab-1.0.0-javadoc.jar
    checksums hoặc signatures tùy repository policy
```

**Không chỉ JAR phải bất biến.** File `.pom` mô tả dependencies/transitive graph cho Maven Resolver. Sources/Javadoc, classified artifacts, chữ ký và checksums đều là thành phần có ý nghĩa trong release distribution.

Nếu một publisher thay file POM nhưng giữ JAR, một consumer dùng `1.0.0` ở thời điểm khác nhau có thể resolve dependency versions/scopes khác nhau. Vì vậy, **sửa POM cũ cũng là thay một bản release đã công bố**.

Một nuance: `maven-metadata.xml` ở cấp artifact có thể được repository cập nhật để ghi nhận **version mới `1.0.1`**. Việc update index version **không** cho phép thay binary hoặc POM ở thư mục `1.0.0`.

### 2.1. Phân biệt classifier và một version mới

Các artifacts `release-guard-lab-1.0.0-sources.jar` hoặc `...-javadoc.jar` dùng classifier nhưng vẫn thuộc component version `1.0.0`. Không suy ra rằng có quyền thêm/thay classifier sau final-publication chỉ vì main JAR không đổi. Quyền bổ sung file vào component đã published phụ thuộc provider policy; Maven Central giữ component đã công bố bất biến.

Muốn phát hành một bản sửa cùng API, hãy tạo version mới và xuất bản **một tập artifacts nhất quán**: JAR, POM, sources/Javadoc và các signatures theo yêu cầu.

### 2.2. Cùng checksum có được deploy lại không?

Không nên. Hosted repository có **Disable redeploy** có thể từ chối request upload cùng tọa độ kể cả khi bytes giống nhau. Nếu đã publish bản giống hệt, không cần gửi lại. Nếu bytes khác, càng không được phép ghi đè.

## 3. Tại sao không thay release?

### 3.1. Reproducibility

Giả sử hai ứng dụng đều phụ thuộc `library:1.0.0`:

```text
consumer-A (máy đã cache) -> library:1.0.0 -> bytes A
consumer-B (máy mới)      -> library:1.0.0 -> bytes B
```

Nếu thư viện bị overwrite trên remote, cùng version dẫn đến hai behaviors. Chẩn đoán `NoSuchMethodError`, classpath conflict, bug bảo mật hoặc sự cố production trở nên không đáng tin: version không còn định danh nội dung cụ thể.

Immutable releases là điều kiện nền tảng cho reproducible build. Tuy nhiên, để tái lập **bit-for-bit** còn phải pin Java/Maven versions, plugins, dependencies, generated resources và tránh timestamps nondeterministic.

### 3.2. Maven cache và repository proxies

Một artifact có thể tồn tại ở:
- Local Maven repository `~/.m2/repository`.
- Cache của CI runner.
- Nexus/Artifactory proxy và repository group.
- Các mirrors hoặc môi trường offline.

Khi remote cho phép overwrite, mỗi cache có thể giữ bản khác nhau. Không thể sửa lịch sử build bằng cách yêu cầu mọi consumer xóa cache. **Không thay nội dung published version ngay từ đầu** tránh trạng thái phân kỳ này.

### 3.3. Provenance, signatures và SBOM

Một release có thể đã được QA và:
- Đính kèm checksum SHA-256.
- Ký số.
- Được phân tích vulnerability/license.
- Ghi vào SBOM.
- Liên kết với Git commit/tag và build run ID.

Nếu cùng GAV được thay nội dung, các bằng chứng này không còn trỏ tới cùng bytes. **Hash và chữ ký là phương tiện kiểm chứng**, còn server-side deny-overwrite là hàng rào ngăn thay release.

### 3.4. API compatibility

Nếu thay JAR `1.0.0` để thêm/bỏ method mà không tăng version, consumer có thể bị lỗi binary compatibility dù không đổi `pom.xml`. Hãy dùng version mới, release notes và consumer tests. Version mới có phải patch/minor/major hay không phụ thuộc Semantic Versioning hoặc chính sách phiên bản riêng của dự án.

## 4. Release khác SNAPSHOT

| Khía cạnh | Release `1.0.0` | Development `1.0.1-SNAPSHOT` |
| --- | --- | --- |
| Mục đích | Phiên bản đã chốt | Bản đang phát triển |
| Chính sách nội dung | Immutable sau publish | Có thể cập nhật theo snapshot workflow |
| Repository thường dùng | Hosted releases | Hosted snapshots |
| Maven resolution | GAV cố định | Metadata có thể trỏ tới snapshot build mới |
| Cho phép deploy lại base version | Không với immutable release | Tùy snapshot repository policy |

Một snapshot repository có thể chứa:

```text
release-guard-lab/1.0.1-SNAPSHOT/
    release-guard-lab-1.0.1-20261110.090000-1.jar
    release-guard-lab-1.0.1-20261110.100000-2.jar
    maven-metadata.xml
```

Đây là **tên minh họa**. Maven base `1.0.1-SNAPSHOT` có thể resolve đến timestamped build khác khi metadata được cập nhật. Không đồng nhất việc có nhiều snapshot builds với quyền thay một released `1.0.0.jar`.

**Pre-release `1.0.0-rc1` hoặc `1.0.0-beta1` không kết thúc bằng `-SNAPSHOT`**. Khi publish vào releases repository bất biến, chúng cũng không nên bị ghi đè. Nếu RC1 cần sửa, tạo RC2/version khác.

### 4.1. Dynamic versions làm giảm độ ổn định

Một project dùng version ranges, placeholders `LATEST`/`RELEASE` hoặc SNAPSHOT dependencies có thể nhận graph thay đổi qua thời gian. Có thể dùng Maven Enforcer `banDynamicVersions` và `requireReleaseVersion` trong release policy; các rules đó **không thay thế** Disable redeploy ở remote repository.

## 5. Maven Central và Nexus: chính sách ở server

### 5.1. Maven Central

Central FAQ nêu rõ: component đã released/published không thể bị thay đổi; lỗi phải được sửa bằng version mới. Phân biệt:
- **Staging/validation trước publication**: có thể được provider cho drop/retry theo workflow được ghi tài liệu.
- **Final public publication**: component đã công bố không được sửa như một thao tác nâng cấp thông thường.

Nếu sau publish phát hiện CVE, malformed POM hoặc bug nghiêm trọng, phát hành version mới và tạo advisory, thông báo consumers. Nếu cần xử lý ngoại lệ, làm việc với provider/security team theo thủ tục được cấp phép, không sửa trực tiếp storage.

### 5.2. Nexus Deployment Policy

Nexus hosted repository có:
- **Disable redeploy**: một component chỉ deploy một lần; upload lại bị từ chối.
- **Allow redeploy**: có thể overwrite component.
- **Read-only**: không nhận upload.

Chọn **Disable redeploy** cho Maven releases repository. Snapshot repository có thể sử dụng cơ chế thích hợp riêng. Trong Artifactory/sản phẩm khác, tên setting có thể khác; tìm chính sách **reject overwrite of existing release components** và kiểm tra trên repository sandbox, không thử đè release thật.

### 5.3. Server-side guard chặn race

Hai jobs cùng làm:

```text
Job A: HEAD -> chưa có -> upload 1.0.0
Job B: HEAD -> chưa có -> upload 1.0.0
```

Preflight `HEAD`/`GET` không an toàn tuyệt đối do **TOCTOU**: trạng thái có thể thay giữa bước kiểm tra và upload. Ngoài ra `HEAD` có thể bị 403/404 vì auth/proxy, hoặc file JAR chưa có trong khi POM đã có.

Repository phải **từ chối ngay lúc ghi lại một release đã tồn tại**. CI lock và preflight là biện pháp hỗ trợ, không phải thay thế server policy. Không cấp CI publisher quyền admin để tự đổi repository sang Allow redeploy khi upload bị từ chối.

## 6. Maven Deploy Plugin và các vòng đời

Phân biệt:

| Lệnh | Ý nghĩa |
| --- | --- |
| `mvn clean verify` | Compile/tests/verify, chưa publish |
| `mvn install` | Cài artifact vào **local repository** |
| `mvn deploy` | Chạy default lifecycle đến phase deploy, gồm các phases trước |
| `mvn deploy:deploy` | Gọi trực tiếp goal upload, không tự chạy đầy đủ previous lifecycle |
| `mvn deploy:deploy-file` | Upload file độc lập theo tọa độ |
| `mvn release:prepare` | Chuẩn bị source versions/SCM tag |
| `mvn release:perform` | Checkout tagged source, build/deploy theo release workflow |

**Maven Deploy Plugin là công cụ upload**, không phải nơi quyết định release immutable. Nếu target cho phép redeploy, Maven Deploy Plugin không bảo vệ bạn khỏi việc thay version cũ.

### 6.1. distributionManagement

Một POM production có thể chứa:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.invalid/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

Đây là **snippet minh họa**; `example.invalid` không hoạt động. Với hệ thống thật, cấu hình `<server><id>` tương ứng trong Maven `settings.xml` hoặc CI secret manager. Không đưa mật khẩu/token vào source POM/log.

Maven Deploy Plugin 3.x hỗ trợ `-DaltDeploymentRepository=id::url` nhưng đó không phải đường bypass release policy. Cũng không được upload cùng GAV khác bytes sang một repository khác để né Disable redeploy: consumers dùng mirrors khác nhau sẽ có cùng version nhưng khác nội dung.

### 6.2. install không phải deploy

`mvn install` ghi vào `~/.m2/repository` hoặc local repository được cấu hình. Local repository có thể được Maven sử dụng làm cache hoặc nơi lưu artifacts vừa build; **nó không bảo đảm release immutability giống public repository**.

`mvn -U` hoặc xóa local cache chỉ ảnh hưởng resolution/caching, không tạo quyền overwrite ở hosted remote. Đừng cố “fix” server redeploy denial bằng cách dọn `~/.m2`.

## 7. Maven Release Plugin, tag và staged publication

Maven Release Plugin hỗ trợ hai bước:
1. `release:prepare` kiểm tra working copy/versions và các điều kiện release, đổi source POM từ SNAPSHOT sang release version, chạy test, commit/tag SCM và chuyển development sang version tiếp theo.
2. `release:perform` checkout source theo SCM tag/release descriptor rồi build và deploy.

```text
1.0.0-SNAPSHOT
      |
release:prepare
      |
      +-- Git/SCM tag: v1.0.0
      +-- Release POM: 1.0.0
      +-- Next development: 1.0.1-SNAPSHOT
      |
release:perform
      |
      +-- checkout v1.0.0
      +-- build, tests
      +-- stage/approved publish
      |
      v
release 1.0.0 immutable
```

Những tên versions/tags này là **ví dụ**, không phải default bắt buộc cho mọi project. Release Plugin cần SCM configuration hợp lệ. **release:rollback không hoàn tác một component đã public trên Central**; nó xử lý những thay đổi preparation được hỗ trợ, không sửa published artifacts.

### 7.1. Staging trước final publish

Một quy trình an toàn:

```text
tag -> build -> tests -> staging
                         |
                   validate POM/signatures
                         |
                   QA/SBOM/consumer tests
                         |
                       approve?
                         |
                 promote approved bytes
                         |
               immutable releases repository
```

Nếu lỗi khi component **chưa public**, dùng chức năng drop/retry staging của provider. Sau final-publication, mọi sửa code/POM phải đi qua **version mới**. Tránh rebuild bytes khác sau khi reviewer đã approve một staged artifact; nếu bắt buộc rebuild, kiểm tra checksum/provenance và reproducibility.

## 8. Lab Java 17: mô phỏng từ chối thay release

**An toàn:** lab này không dùng Maven Central/Nexus credentials, không cấu hình remote deployment và **không gọi `mvn deploy`**. Ta build Maven JAR và dùng một class Java để copy file tới thư mục **`sandbox-repository`** với `StandardOpenOption.CREATE_NEW`. Lần đầu tạo thành công, lần hai cùng version bị từ chối.

Đây là **mô phỏng một-file no-overwrite**, không phải Maven repository manager: không tự sinh published POM, checksums, signatures, metadata hoặc atomic publication nhiều files. Production phải dùng repository server policy.

### 8.1. Cây file

```text
release-guard-lab/
├── pom.xml
├── src/
│   ├── main/java/dev/training/release/
│   │   ├── PriceCalculator.java
│   │   ├── App.java
│   │   └── NoOverwritePublisher.java
│   └── test/java/dev/training/release/
│       └── PriceCalculatorTest.java
└── sandbox-repository/  (tạo sau khi chạy demo)
```

Chuẩn bị Linux/macOS:

```bash
mkdir -p release-guard-lab/src/main/java/dev/training/release
mkdir -p release-guard-lab/src/test/java/dev/training/release
cd release-guard-lab
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "release-guard-lab/src/main/java/dev/training/release" | Out-Null
New-Item -ItemType Directory -Force -Path "release-guard-lab/src/test/java/dev/training/release" | Out-Null
Set-Location release-guard-lab
```

Từ đây mọi lệnh chạy ở root `release-guard-lab`. Cần JDK 17+, Maven 3.9.x, có thể lấy JUnit/plugins từ Maven Central/mirror nếu local cache chưa có.

### 8.2. POM hoàn chỉnh

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training.release</groupId>
    <artifactId>release-guard-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.4</version>
            </plugin>
        </plugins>
    </build>
</project>
```

POM **không có `<distributionManagement>`**, vì không cần remote target. Plugin versions được ghim để baseline rõ; `3.1.4` là một version đã phát hành của Deploy Plugin, **không khẳng định là mới nhất**. Goal deploy không được gọi trong lab.

### 8.3. PriceCalculator.java

Tệp `src/main/java/dev/training/release/PriceCalculator.java`:

```java
package dev.training.release;

public final class PriceCalculator {

    private PriceCalculator() {
    }

    public static long subtotal(long unitPrice, long quantity) {
        if (unitPrice < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                "price and quantity must be non-negative");
        }
        return Math.multiplyExact(unitPrice, quantity);
    }
}
```

`Math.multiplyExact` bảo đảm lỗi overflow được phát hiện, thay vì âm thầm trả một số sai.

### 8.4. App.java

Tệp `src/main/java/dev/training/release/App.java`:

```java
package dev.training.release;

public final class App {

    private App() {
    }

    public static void main(String[] args) {
        System.out.println(
            "total=" + PriceCalculator.subtotal(125, 3));
    }
}
```

Stdout Java chính xác:

```text
total=375
```

### 8.5. PriceCalculatorTest.java

Tệp `src/test/java/dev/training/release/PriceCalculatorTest.java`:

```java
package dev.training.release;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {

    @Test
    void multipliesPriceAndQuantity() {
        assertEquals(375L, PriceCalculator.subtotal(125, 3));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(IllegalArgumentException.class,
            () -> PriceCalculator.subtotal(-1, 3));
    }

    @Test
    void rejectsOverflow() {
        assertThrows(ArithmeticException.class,
            () -> PriceCalculator.subtotal(Long.MAX_VALUE, 2));
    }
}
```

Ba JUnit Jupiter tests kiểm tra phép tính, input âm và overflow.

### 8.6. NoOverwritePublisher.java

Tệp `src/main/java/dev/training/release/NoOverwritePublisher.java`:

```java
package dev.training.release;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class NoOverwritePublisher {

    private static final String GAV =
        "dev.training.release:release-guard-lab:1.0.0";

    private static final String FILE_PATH =
        "dev/training/release/release-guard-lab/1.0.0/"
        + "release-guard-lab-1.0.0.jar";

    private NoOverwritePublisher() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println(
                "Usage: NoOverwritePublisher <jar-file> <sandbox-dir>");
            System.exit(2);
            return;
        }

        Path source = Path.of(args[0]);
        Path target = Path.of(args[1]).resolve(FILE_PATH);
        Files.createDirectories(target.getParent());

        try (InputStream input = Files.newInputStream(source);
             OutputStream output = Files.newOutputStream(
                 target,
                 StandardOpenOption.CREATE_NEW,
                 StandardOpenOption.WRITE)) {

            input.transferTo(output);

        } catch (FileAlreadyExistsException e) {
            System.err.println(
                "REJECTED " + GAV + ": already published");
            System.exit(3);
            return;
        }

        System.out.println("PUBLISHED " + GAV);
    }
}
```

Phân tích:
- `FILE_PATH` cố định theo tọa độ của lab.
- `CREATE_NEW` chỉ tạo file khi target chưa có, không dùng `REPLACE_EXISTING`.
- Không cần `Files.exists` trước; nếu dùng kiểm tra rồi ghi có thể bị race TOCTOU.
- Lần thứ hai gặp `FileAlreadyExistsException`, in stderr và exit `3`.
- Copy JAR được thực hiện qua `InputStream.transferTo` của JDK.

**Giới hạn:** nếu process bị kill giữa khi copy, file local có thể chưa đủ bytes. Demo không có transaction hay temporary-file promotion; không xử lý symlink trust và không đủ để làm Maven component store. Nó chỉ giải thích chính sách no-overwrite trên một file path.

### 8.7. Build baseline

```bash
mvn -version
mvn -B -ntp clean verify
java -cp target/classes dev.training.release.App
```

Sau build thành công, JAR ở `target/release-guard-lab-1.0.0.jar`. Surefire dự kiến chạy 3 tests:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Đây là thống kê, không phải toàn bộ Maven log. `java -cp` in chính xác:

```text
total=375
```

Không dùng `java -jar` vì manifest không có Main-Class; `-cp target/classes` là đúng với lab.

### 8.8. Publish giả lần thứ nhất

Khi `sandbox-repository` chưa chứa file tương ứng:

```bash
java -cp target/classes dev.training.release.NoOverwritePublisher target/release-guard-lab-1.0.0.jar sandbox-repository
```

Stdout chính xác:

```text
PUBLISHED dev.training.release:release-guard-lab:1.0.0
```

File được tạo tại:

```text
sandbox-repository/dev/training/release/release-guard-lab/1.0.0/release-guard-lab-1.0.0.jar
```

Đây **chỉ là sandbox local**, không phải một Maven remote repository được publish đầy đủ.

### 8.9. Publish giả lần thứ hai

**Không xóa sandbox giữa hai lần.** Chạy lại cùng command:

```bash
java -cp target/classes dev.training.release.NoOverwritePublisher target/release-guard-lab-1.0.0.jar sandbox-repository
```

Stderr chính xác:

```text
REJECTED dev.training.release:release-guard-lab:1.0.0: already published
```

Exit code **3**, có chủ đích. Trong PowerShell có thể đọc `$LASTEXITCODE`, trong Bash dùng `echo $?` ngay sau lệnh. Nếu lần đầu đã báo REJECTED thì sandbox có file từ thí nghiệm trước; không ghi đè, dùng một sandbox mới khi muốn chạy lại.

### 8.10. Thay code nhưng không nâng version

Thử sửa phép tính hoặc lời in trong Java source, build lại bằng `mvn clean verify` nhưng **giữ POM version 1.0.0**. Publisher vẫn từ chối target `.../1.0.0/...jar` đã tồn tại. Đây là hành vi mong muốn, dù nội dung JAR mới khác hay giống bytes cũ.

**Maven clean xóa `target` nhưng không xóa `sandbox-repository`** bên cạnh `src`; điều này giúp thấy version đã “công bố” vẫn được giữ sau rebuild.

### 8.11. Phiên bản mới mới là cách sửa

Trong release process thật, nâng version `1.0.0` thành `1.0.1` (nếu phù hợp policy), build/test lại, đưa artifacts vào `.../1.0.1/` và publish qua server no-redeploy. **Không dùng nguyên class demo hard-coded 1.0.0 để xuất bản 1.0.1**; nó không phải Maven Deploy Plugin thay thế.

### 8.12. So checksum trong sandbox

Linux/macOS:

```bash
sha256sum target/release-guard-lab-1.0.0.jar
sha256sum sandbox-repository/dev/training/release/release-guard-lab/1.0.0/release-guard-lab-1.0.0.jar
```

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -Path "target/release-guard-lab-1.0.0.jar"
Get-FileHash -Algorithm SHA256 -Path "sandbox-repository/dev/training/release/release-guard-lab/1.0.0/release-guard-lab-1.0.0.jar"
```

Nếu JAR source chưa được build lại từ khi copy, hash phải giống. Không đưa một giá trị checksum giả vì bytes phụ thuộc build thực tế. Checksums giúp so nội dung, không cấp quyền overwrite.

```gitignore
/target/
/sandbox-repository/
```

Đây là một mẫu `.gitignore` cho lab, giúp không commit generated outputs.

## 9. Khi deployment lỗi: không retry mù

Remote upload thường gồm nhiều files: JAR, POM, metadata, checksums, signatures, classified artifacts. Client có thể timeout **sau khi server đã nhận một số file**. Không thể suy ra upload chưa xảy ra chỉ vì Maven báo lỗi.

Quy trình:
1. Giữ build logs/checksums.
2. Xác nhận repository ID và GAV.
3. Kiểm tra component state qua API/UI được cấp quyền.
4. Phân biệt staging chưa publish với final published.
5. Kiểm tra JAR/POM/classifiers nào đã được nhận.
6. Với staged deployment, xử lý drop/retry theo provider docs.
7. Với release đã published, không overwrite; nếu có lỗi, version mới hoặc provider-approved incident workflow.
8. Không đổi repository URL hoặc xóa cache để bypass no-redeploy.

| Triệu chứng | Có thể do | Hướng xử lý |
| --- | --- | --- |
| "Redeploy not allowed" | GAV/component đã tồn tại | Dừng; không upload lại |
| `401` | Auth không hợp lệ | Kiểm tra server ID/CI secret |
| `403` | Thiếu quyền hoặc policy | Đọc response, không tự cấp admin |
| `400` | Validation/POM/signature/policy | Sửa staging nếu chưa published |
| `409` | Component conflict | Tra trạng thái version |
| HTTP `429`/`5xx` hoặc timeout | Rate limit/server, upload không rõ kết quả | Tra state trước retry |
| Repo releases từ chối SNAPSHOT | Sai repository/policy | Dùng snapshot repository |
| Releases bị gửi vào snapshots repo | distributionManagement sai | Sửa endpoint trước public release |

**HTTP code không cố định giữa mọi repository providers.** Đừng lập luận rằng mọi `409` đều đồng nghĩa một release hoàn chỉnh đã xuất bản, hoặc mọi `403` đều do password sai.

## 10. Multi-module reactor: phát hành từng phần

Một reactor:

```text
parent (pom)
core (jar)
service (jar -> core)
app (jar -> service)
```

Nếu `mvn deploy` tuần tự, `core`/`service` có thể đã deploy trước khi `app` fail tests. Khi đó repository chứa một phần artifacts còn whole-reactor release chưa đạt. Chính sách immutable vẫn bảo vệ các artifact đã được công bố; nó không khiến quá trình publish của reactor trở thành một giao dịch all-or-nothing.

### 10.1. deployAtEnd

Maven Deploy Plugin có tham số `deployAtEnd`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-deploy-plugin</artifactId>
    <version>3.1.4</version>
    <configuration>
        <deployAtEnd>true</deployAtEnd>
    </configuration>
</plugin>
```

**Đây là snippet cho một dự án multi-module thực tế, không cần thêm vào POM lab.** Nó có thể trì hoãn upload để giảm rủi ro publish trước khi module khác fail. Tuy nhiên:
- Một batch upload có thể fail giữa chừng.
- Files/repositories đã nhận không được rollback tự động.
- Một module không bind deploy đứng sau vẫn có thể fail sau batch.
- Project nào có `deployAtEnd=false` có thể deploy ngay.
- External approvals/scan nằm ngoài invocation vẫn có thể chưa hoàn tất.

**deployAtEnd không phải atomic transaction.** Với whole-reactor release, dùng staging repository và promotion policy, kiểm thử toàn bộ module trước publication, so hashes/manifest và tổ chức approval.

## 11. Khi phát hiện bug sau final publish

Đừng thay phiên bản cũ. Hướng xử lý:
1. Xác định GAV và các consumer bị ảnh hưởng.
2. Đánh giá bug, CVE, API compatibility hoặc POM metadata sai.
3. Công bố advisory/release notes theo mức độ và chính sách.
4. Sửa code/POM trên branch mới.
5. Chọn version **chưa từng publish**.
6. Chạy unit, integration, consumer tests và security checks.
7. Tạo tag mới, build/scan/sign/publish version mới.
8. Cập nhật BOMs, docs và hướng dẫn nâng cấp.
9. Theo dõi adoption và xử lý sản phẩm đang dùng version cũ.
10. Nếu cần “rollback”, chuyển ứng dụng sang một version trước đã kiểm chứng, **không ghi đè artifact đã công bố**.

Maven Central không cho chỉnh sửa bản public như một hành động thông thường. Nếu cần takedown/quarantine vì rủi ro nghiêm trọng, chỉ dùng cơ chế được repository provider và security/legal team cho phép.

### 11.1. Những cách làm cần tránh

- Rebuild `1.0.0` rồi upload đè.
- Đổi POM `1.0.0` để chữa dependency mà giữ binary.
- Dùng `mvn -U` hoặc xóa `~/.m2` như thể đó là quyền redeploy.
- Đổi Git tag `v1.0.0` sang commit khác sau publish.
- Bật Allow redeploy tạm thời trên releases repository.
- Đăng một JAR khác cùng GAV ở repository thứ hai.
- Bỏ tests/quality gates để đưa hotfix ra nhanh.
- Xóa trực tiếp object/blob storage để lách policy.
- Xem `release:rollback` là công cụ xóa published component.

Mỗi việc trên gây mất tính nhất quán, provenance hoặc gây nhầm lẫn consumers.

## 12. CI release checklist

Một pipeline có thể theo thứ tự:

```text
Source tag + unique GAV
        |
Whole-project clean verify
        |
Tests / security / SBOM / API checks
        |
Stage built artifacts (not public)
        |
Hash / POM / signature validation
        |
Approval
        |
Promote exactly approved artifacts
        |
Immutable server-side releases repository
        |
Consumer smoke test + audit record
```

Danh sách cần đối chiếu:
- [ ] Version release là version mới, chưa public.
- [ ] Git tag/commit không bị rewrite.
- [ ] Maven/JDK/build-plugin versions được ghim.
- [ ] Không dùng SNAPSHOT/dynamic dependency trái release policy.
- [ ] Tests và quality gates chạy trên đúng commit.
- [ ] JAR, POM, classifiers, sources/Javadocs, checksums/signatures nhất quán.
- [ ] Staging chưa public có thể được drop/retry theo provider docs.
- [ ] Release repository dùng **no redeploy**; publisher không thể tự hạ policy.
- [ ] CI preflight có bổ trợ nhưng không là hàng rào duy nhất.
- [ ] Concurrency protection ngăn hai job cùng publish GAV.
- [ ] Approval chỉ cho artifacts đã kiểm thử.
- [ ] Multi-module deploy không được nhầm là atomic.
- [ ] Timeout được điều tra thay vì retry mù.
- [ ] Logs không lộ credentials.
- [ ] Release manifest lưu GAV, source tag, hash và build run ID.
- [ ] Consumer smoke test resolve đúng published POM/JAR.
- [ ] Có quy trình remediate bằng **version mới** thay vì overwrite.

## 13. Câu hỏi ôn tập và đáp án

**Câu 1.** Release immutability là gì?

**Đáp án:** Sau khi công bố, cùng GAV phải tiếp tục đại diện cho cùng release artifact/files; không thay bytes/metadata bằng bản khác.

**Câu 2.** Maven Central có cho thay `1.0.0.jar` đã public không?

**Đáp án:** Không. Phát hành version mới khi có bug.

**Câu 3.** GAV viết tắt ba thành phần gì?

**Đáp án:** groupId, artifactId, version.

**Câu 4.** POM có cần giữ bất biến không?

**Đáp án:** Có. Nó điều khiển dependency graph của consumer.

**Câu 5.** Vì sao snapshot khác release?

**Đáp án:** Snapshot có metadata trỏ tới các timestamped builds mới theo development policy; release version cần cố định.

**Câu 6.** Nexus policy nào chặn redeploy?

**Đáp án:** Disable redeploy.

**Câu 7.** Preflight HEAD đủ chống overwrite chưa?

**Đáp án:** Chưa. Có race TOCTOU và có thể bypass; cần server enforcement.

**Câu 8.** `mvn install` có publish remote không?

**Đáp án:** Không; nó cài vào local Maven repository.

**Câu 9.** `mvn deploy` có tự tạo immutability không?

**Đáp án:** Không, policy thuộc server.

**Câu 10.** `release:rollback` có undo release đã public Central không?

**Đáp án:** Không.

**Câu 11.** Lab `App.main` in chính xác gì?

**Đáp án:** `total=375`.

**Câu 12.** Lab có mấy unit tests?

**Đáp án:** Ba.

**Câu 13.** Publisher lab dùng option NIO gì?

**Đáp án:** `CREATE_NEW`.

**Câu 14.** Lần publish demo đầu in gì?

**Đáp án:** `PUBLISHED dev.training.release:release-guard-lab:1.0.0`.

**Câu 15.** Lần thứ hai in gì và exit code nào?

**Đáp án:** `REJECTED dev.training.release:release-guard-lab:1.0.0: already published` trên stderr, exit `3`.

**Câu 16.** Publisher demo có tạo Maven POM và metadata repository thật không?

**Đáp án:** Không, chỉ copy một JAR vào sandbox.

**Câu 17.** Nếu upload timeout, có nên retry toàn bộ release ngay không?

**Đáp án:** Không, phải kiểm tra component state/staging/files đã nhận.

**Câu 18.** `deployAtEnd=true` bảo đảm không partial deploy không?

**Đáp án:** Không. Nó trì hoãn deploy nhưng không transactional.

**Câu 19.** Hai repositories cùng GAV nhưng khác bytes gây vấn đề gì?

**Đáp án:** Consumer có thể nhận behavior khác dưới cùng version tùy mirror, phá reproducibility.

**Câu 20.** Có được thay GAV cũ khi phát hiện CVE không?

**Đáp án:** Không. Tạo advisory và phiên bản mới, dùng provider-approved incident process khi cần.

## 14. Nguồn chính thức

- [Sonatype Central — Can I change a component?](https://central.sonatype.org/faq/can-i-change-a-component/): bản release đã công bố không sửa/xóa, bugfix phải phát hành version mới.
- [Apache Maven — Uploading Artifacts to Central](https://maven.apache.org/repository/guide-central-repository-upload): release requirements và tính bất biến.
- [Nexus Repository — Configurable Repository Fields](https://help.sonatype.com/en/configurable-repository-fields.html): Disable redeploy / Allow redeploy / Read-only.
- [Apache Maven Deploy Plugin — Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html): deploy lifecycle, distributionManagement, deploy-file.
- [Apache Maven Deploy Plugin — deploy:deploy](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html): deployAtEnd và các tùy chọn.
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories): local/remote, snapshot/release.
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): credentials, mirrors, repository policies.
- [Apache Maven — Release Plugin](https://maven.apache.org/components/maven-release/maven-release-plugin/): prepare/perform, SCM versions.
- [Apache Maven — Releasing](https://maven.apache.org/guides/mini/guide-releasing.html): phát hành bằng Maven.
- [Apache Maven Enforcer — Ban Dynamic Versions](https://maven.apache.org/enforcer/enforcer-rules/banDynamicVersions.html): chính sách dependency versions.
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): verify/install/deploy phases.
