# Liên hệ artifact với commit, tag và kết quả build trong quy trình phát hành Maven

> **Build Tool Maven · Quy trình phát hành**  
> Bài thực hành dùng **Git, Maven 3.9.x, JDK 17**, Maven Compiler Plugin **3.14.1**, Maven JAR Plugin **3.5.1**, Maven Surefire Plugin **3.6.1** và JUnit Jupiter **5.11.4**. Mục tiêu là thiết lập đường truy xuất **Git commit → release tag → CI run → Maven GAV → bytes của artifact → kết quả kiểm thử**, để có thể trả lời câu hỏi: *“File JAR đang chạy thực sự được tạo từ commit nào, ở lần build nào, đã qua những kiểm tra nào?”*

## 1. Vì sao chỉ biết `artifactId` và `version` là chưa đủ?

Sau một release, có thể thấy:

```text
org.example:release-provenance-demo:jar:1.4.0
```

hoặc file:

```text
release-provenance-demo-1.4.0.jar
```

Những thông tin ấy trả lời **artifact được đặt tên như thế nào**, nhưng chưa chứng minh:

- Source thực sự được lấy từ **commit SHA nào**?
- Git tag `v1.4.0` có trỏ tới chính commit đó không?
- CI build nào tạo ra file **bytes cụ thể**?
- Maven/JDK/plugins/dependencies nào được dùng?
- Unit/integration/security checks đã chạy và PASS hay bị skip?
- SHA-256 của JAR thực sự được triển khai là gì?
- JAR đã triển khai có giống JAR từng được kiểm thử và phê duyệt không?
- Ai/cơ chế nào cung cấp metadata, nó có được xác thực không?

**Một version không phải một bằng chứng nguồn gốc.** Một Maven GAV có thể bị publish sai, đổi file trong repository không áp chính sách immutability, hoặc bị copy/chèn lại bởi quy trình thủ công. Tương tự, `Implementation-Version: 1.4.0` nằm trong manifest không tự chứng minh code đúng commit của release.

Hãy tư duy theo **chuỗi chứng cứ**:

```text
Repository URL
     |
Git commit SHA (immutable object ID trong Git object database)
     |
Release tag v1.4.0 -> phải resolve về đúng commit
     |
CI job/run ID + builder/toolchain + nguồn input
     |
mvn clean verify --> tests, reports, quality gates
     |
Artifact Maven GAV + JAR bytes
     |
SHA-256 digest + provenance/attestation + chữ ký (nếu policy yêu cầu)
     |
Artifact repository -> deployment/production
```

Mỗi mắt xích phải có **định danh kiểm chứng được** và **quan hệ nhất quán**. Chỉ tạo một bảng chứa những chuỗi giống nhau chưa đủ; cần kiểm chứng mối liên hệ giữa chúng.

## 2. Phân biệt các định danh

| Khái niệm | Ví dụ minh họa | Ý nghĩa và giới hạn |
| --- | --- | --- |
| Git repository | URL remote của dự án | Nguồn chứa lịch sử; URL có thể đổi chủ/quyền |
| Git commit | Full object ID từ `git rev-parse HEAD` | Chỉ đích danh một Git object; độ dài phụ thuộc object format của repository |
| Git tag | `v1.4.0` | Tên tham chiếu release; có thể là lightweight, annotated hoặc signed |
| Git tag object | Object của annotated tag | Chứa metadata/tagger/message và có thể chữ ký; **khác** object ID commit |
| Maven coordinates | `org.example:release-provenance-demo:1.4.0` | Tên dependency/artifact theo POM/repository |
| CI build/run ID | ID do CI platform cấp | Định danh lần thực thi; khác commit và Maven version |
| CI run URL | Đường link đến logs/test reports | Cần phân quyền/lưu giữ, có thể hết hạn |
| Artifact digest | SHA-256 của **bytes JAR** | Dùng để kiểm tra đúng file; không tự chứng minh ai tạo |
| Test results | JUnit XML, CI checks | Bằng chứng về **những kiểm tra đã chạy** trong một run cụ thể |
| Provenance | Quan hệ source/build/subject | Có thể chỉ là file tự khai hoặc attestation có chữ ký do trusted builder cấp |
| Deployment ID | ID của lần triển khai | Chứng minh bản nào được triển khai nếu gắn đúng digest |

Trong Maven, tọa độ thường viết theo dạng:

```text
groupId:artifactId:packaging:version
```

ví dụ:

```text
org.example:release-provenance-demo:jar:1.4.0
```

Khi dùng dependency, POM khai báo `groupId`, `artifactId`, `version`; packaging mặc định thường là `jar`. **Git SHA và CI run ID không phải thành phần mặc định của Maven GAV.** Chúng cần được ghi/đính kèm có chủ đích.

### 2.1. Commit SHA khác commit message và branch name

Một nhánh như `main` hoặc `release/1.4` có thể **tiếp tục di chuyển** sau khi build. Một commit message như `Prepare release 1.4.0` không bảo đảm duy nhất. Trong hồ sơ phát hành, lưu **full commit object ID** và repository identity; chỉ dùng branch name như thông tin bổ sung.

Không cố định quy tắc “commit SHA luôn dài 40 ký tự”: các Git repositories có thể dùng SHA-1 hoặc SHA-256 object format. Hãy lưu chính xác chuỗi do Git trả về trong môi trường nguồn, không tự cắt để “đẹp log”.

### 2.2. Tag không nhất thiết là một commit object

Một **lightweight tag** là ref chỉ tới một object (thường commit). Một **annotated tag** có tag object riêng, lưu tagger/date/message; một **signed tag** bổ sung chữ ký cryptographic.

Ví dụ:

```bash
git tag -a v1.4.0 -m "Release 1.4.0"
```

tạo annotated tag; còn:

```bash
git tag -s v1.4.0 -m "Release 1.4.0"
```

tạo signed annotated tag nếu signing key/trust setup đã cấu hình.

Hai lệnh trên là **minh họa thao tác chủ động tạo release tag**, không phải thao tác buộc thực hiện khi chỉ đọc bài. Không dùng `git tag -f` để âm thầm chuyển một release tag đã phát hành sang commit khác.

**Lưu ý:** ký Git tag **khác** ký JAR, và cả hai đều khác **CI provenance attestation**. Ký tag xác thực tag object theo một key; muốn xác thực một JAR được build từ tag ấy vẫn phải có bằng chứng nối source, builder và artifact bytes.

## 3. Kiểm chứng tag thực sự trỏ tới commit build

Đứng trong repository đã checkout đúng nguồn:

```bash
git status --porcelain
git rev-parse --verify HEAD
git rev-parse --verify "refs/tags/v1.4.0^{commit}"
```

`HEAD` là commit đang checkout. Biểu thức `refs/tags/v1.4.0^{commit}` **peel annotated tag object** tới commit được gắn tag; cũng xử lý trường hợp ref trực tiếp trỏ commit.

Các điều kiện để phát hành từ đúng tag:

1. `git status --porcelain` rỗng trước build (không có thay đổi tracked/untracked ngoài policy).
2. Git tag tồn tại, resolve thành commit.
3. Commit từ tag bằng **chính xác** commit ở `HEAD`.
4. Remote/repository được phép tin cậy, refs đã fetch theo quy trình release.
5. Nếu policy yêu cầu signed tag, chữ ký được xác minh bằng đúng trusted key.
6. POM version thống nhất với release tag (`v1.4.0` → Maven version `1.4.0` trong demo).

Ví dụ Git hỗ trợ:

```bash
git show --no-patch --format=fuller HEAD
git show --no-patch v1.4.0
```

Với signed annotated tag, có thể:

```bash
git tag -v v1.4.0
```

**Chỉ dùng `git tag -v` làm kiểm tra chữ ký khi tag thật sự được ký.** Annotated tag tạo bằng `-a` nhưng không ký không thể tự cho signature PASS. Kết quả verify còn phụ thuộc trusted public keys/trust policy.

### 3.1. Lỗi dễ bỏ qua: tag đã được build nhưng pipeline checkout nhầm

Một release job có thể nhận biến môi trường cho tag `v1.4.0`, nhưng checkout lại **tip của branch `main`** mới hơn. Nếu job chỉ ghi tên tag vào manifest, artifact có thể bị gắn sai provenance.

Đúng cách: CI checkout chính commit do release tag tham chiếu, rồi assert:

```text
Git HEAD == peel(refs/tags/v1.4.0)
```

**Không tin một biến tên `TAG_NAME` hoặc `GITHUB_REF` là bằng chứng rằng working tree đang ở commit của tag.** Một số CI environments dùng merge commits/temporary refs cho pull-request workflows. Release job cần kiểm tra chính working checkout.

### 3.2. Tính toàn vẹn của tag sau phát hành

Git tag là một **ref name có thể bị di chuyển** nếu người vận hành có quyền phù hợp. Bảo vệ release tags ở Git hosting, hạn chế force push/rewrite, ghi lại commit SHA tại thời điểm approval, và dùng signed tags nếu tổ chức yêu cầu.

Khi điều tra release lịch sử, đừng chỉ chạy `git show v1.4.0` rồi coi ref hiện tại luôn là bản đã được dùng hôm phát hành. Đối chiếu SHA đã được ghi trong CI log/provenance và release records.

## 4. Maven GAV, POM version và tag cần khớp ra sao?

Ví dụ bài lab dùng:

```xml
<groupId>org.example</groupId>
<artifactId>release-provenance-demo</artifactId>
<version>1.4.0</version>
<packaging>jar</packaging>
```

Quy ước phát hành của demo:

```text
Git tag:          v1.4.0
Maven POM version: 1.4.0
Expected JAR:     target/release-provenance-demo-1.4.0.jar
```

**Đây là chính sách của dự án**, không phải Maven tự suy tag từ `<version>` hoặc tự tạo Git tag. Maven mặc định không bắt buộc Git tag trùng project version. Team cần đặt rule và kiểm tra trong pipeline.

### 4.1. Vì sao không đưa toàn bộ SHA vào artifactId?

Ví dụ:

```text
release-provenance-demo-a7c1...jar
```

có thể thuận tiện cho lưu files nội bộ, nhưng làm identity Maven/consumer phức tạp. Thông thường nên giữ **GAV là định danh release**, và lưu **full source commit, build ID, SHA-256** trong hồ sơ bên cạnh artifact. Nếu team dùng commit-derived version, cần thống nhất Maven version policy và repository layout, không tùy tiện đặt SHA ở artifactId chỉ để thay cho provenance.

### 4.2. Version giống nhau vẫn có thể chứa bytes khác nhau

Hai lệnh chạy hai lần:

```bash
mvn clean package
mvn clean package
```

có thể tạo JAR cùng tên, nhưng bytes/hash có thể khác nếu timestamps, file order, inputs, plugin configuration hoặc embedded build ID thay đổi.

Ngay cả khi JAR giống byte-for-byte, điều đó không tự chứng minh nó đã được tạo ở một CI run được phê duyệt. Phải gắn **artifact digest** với build/test records đã xác minh.

### 4.3. SNAPSHOT khác release

`1.4.0-SNAPSHOT` có thể được publish nhiều lần với snapshot metadata/timestamp build khác nhau tùy repository; **GAV hiển thị đơn giản chưa đủ** để nhận diện đúng một snapshot binary. Khi cần xác định snapshot đang chạy, dùng version thực tế đã resolve, repository URL, artifact digest và CI run.

`1.4.0` là release version; repository production nên áp chính sách **immutable release artifacts**, không cho upload lại file khác cùng GAV mà không kiểm soát. Không dựa vào “tên không đổi” làm integrity check.

## 5. Chiến lược lưu build metadata: trong JAR và ngoài JAR

Một cách thực tế là chia metadata thành hai lớp:

**Lớp trong JAR, tương đối ổn định theo nguồn/release:**

```text
META-INF/MANIFEST.MF
    Implementation-Version: 1.4.0
    Git-Commit: <giá trị lấy từ HEAD>
    Git-Tag: v1.4.0
```

Các dòng trên là **minh họa cấu trúc**, không phải dữ liệu đã được xác minh của một release có thật.

**Lớp ngoài JAR, thay đổi theo lần chạy CI:**

```text
ci-run-id
ci-run-url
builder identity
mvn -version / JDK / OS / build image
test report paths và kết quả
artifact SHA-256
artifact repository URL
approval/deployment references
attestation/signature references
```

Vì mỗi lần CI chạy có ID mới, **không nên vô tình nhúng ID đó vào bytes của JAR** nếu bạn muốn rebuild cùng một commit tạo JAR byte-identical. Nên để run-specific metadata **bên ngoài** và nối bằng SHA-256 của JAR.

### 5.1. Vì sao manifest metadata không phải “bằng chứng cryptographic”?

Bất kỳ ai sửa JAR có thể sửa một manifest không được bảo vệ. Một `Git-Commit: ...` trong `MANIFEST.MF` **là nhãn do build cung cấp**, không tự chứng minh JAR được build từ Git commit đó.

Muốn có nguồn gốc đáng tin cậy hơn, cần:

- CI thực sự checkout và verify commit/tag.
- Builder identity và build invocation được ghi bởi một hệ thống có quyền tin cậy.
- Digest của artifact được ghi sau build/test.
- Kết quả test được gắn với **cùng run và cùng artifact digest**.
- Attestation/chữ ký phù hợp được xác minh với trusted key hoặc identity.
- Release repository và deployment kiểm tra digest.

**Checksum đơn thuần chỉ phát hiện khác bytes khi đã có giá trị kỳ vọng từ nguồn đáng tin cậy.**

### 5.2. Reproducibility trade-off

Nếu nhúng:

```xml
<Ci-Build-Id>${ci.run.id}</Ci-Build-Id>
```

thì hai build cùng commit nhưng run ID khác **có thể cho JAR hash khác**. Điều này không nhất thiết sai cho mọi sản phẩm, nhưng phá mục tiêu byte-identical artifacts nếu run ID luôn mới.

Bài lab chính vì vậy **không nhúng CI run ID vào JAR**. Nó đưa source identity vào manifest và run identity vào bản ghi build bên ngoài, rồi nối bằng artifact SHA-256.

## 6. Lab Maven Java 17: JAR có nguồn commit/tag và tests

Bài dùng single-module project để việc truy xuất artifact rõ ràng.

### 6.1. Cây file

```text
release-provenance-demo/
├── pom.xml
├── src/
│   ├── main/java/org/example/release/ReleaseMain.java
│   └── test/java/org/example/release/ReleaseMainTest.java
└── audit/
    └── ArtifactAudit.java
```

`audit/ArtifactAudit.java` là **công cụ kiểm tra độc lập** được compile bằng JDK, không phải Java source chính được đưa vào JAR. Các files `.class` của tool audit nằm ngoài artifact ứng dụng để không làm thay đổi artifact đang được xem xét.

### 6.2. `pom.xml` hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>release-provenance-demo</artifactId>
    <version>1.4.0</version>
    <packaging>jar</packaging>
    <name>Release Provenance Demo</name>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>

        <!-- Giá trị chỉ để chạy local khi chưa làm release từ tag -->
        <release.commit>local-unverified</release.commit>
        <release.tag>untagged</release.tag>
    </properties>

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
                <version>3.5.1</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>org.example.release.ReleaseMain</mainClass>
                            <addDefaultImplementationEntries>true</addDefaultImplementationEntries>
                        </manifest>
                        <manifestEntries>
                            <Git-Commit>${release.commit}</Git-Commit>
                            <Git-Tag>${release.tag}</Git-Tag>
                        </manifestEntries>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Cấu hình này làm gì?**

1. Maven Compiler Plugin dùng release level **17**.
2. Surefire **3.6.1** chạy JUnit Jupiter tests từ `src/test/java`.
3. Maven JAR Plugin **3.5.1** tạo `release-provenance-demo-1.4.0.jar`.
4. `<manifest><mainClass>...` làm JAR chạy được bằng `java -jar`.
5. `<addDefaultImplementationEntries>true</addDefaultImplementationEntries>` thêm implementation metadata, trong đó có `Implementation-Version`.
6. `<manifestEntries>` thêm `Git-Commit` và `Git-Tag` qua Maven Archiver; tên headers có dấu gạch ngang nên dùng các XML element names đúng như ví dụ.
7. `release.commit=local-unverified`, `release.tag=untagged` là **dấu hiệu build local**, **không đủ điều kiện phát hành**. Release CI **bắt buộc** override bằng các giá trị đã kiểm chứng từ Git trước khi publish.
8. `project.build.outputTimestamp` giúp timestamp entries ổn định với packaging plugins hỗ trợ reproducible builds; nó **không tự bảo đảm hash giống nhau trong mọi môi trường**.

**Lưu ý:** Maven không tự đọc Git SHA từ `${release.commit}`. Trong demo, đây là **Maven properties thông thường**, phải cấp bằng `-D` từ giá trị Git đã xác minh; không có plugin tự động Git trong POM.

### 6.3. `src/main/java/org/example/release/ReleaseMain.java`

```java
package org.example.release;

public final class ReleaseMain {
    private ReleaseMain() {
    }

    public static String message() {
        return "release-provenance-demo: OK";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Class không có dependencies runtime bên ngoài JDK. Nó có `main`, phù hợp `Main-Class` trong manifest.

### 6.4. `src/test/java/org/example/release/ReleaseMainTest.java`

```java
package org.example.release;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class ReleaseMainTest {
    @Test
    void messageIsStable() {
        assertEquals("release-provenance-demo: OK",
                ReleaseMain.message());
    }

    @Test
    void messageHasExpectedPrefix() {
        assertTrue(ReleaseMain.message()
                .startsWith("release-provenance-demo:"));
    }
}
```

Hai tests kiểm tra một thuộc tính giá trị và một thuộc tính định dạng. Trong project thật phải có tests thực cho business logic, API compatibility, integration/security checks tùy release policy; demo này chỉ dùng 2 tests để minh họa **liên kết kết quả build**.

### 6.5. Build local trước khi có tag

Từ thư mục project:

```bash
java -version
javac -version
mvn -version
mvn -B clean verify
```

Nếu tools/dependencies được resolve và tests PASS, kết quả sẽ có:

```text
target/classes/org/example/release/ReleaseMain.class
target/test-classes/org/example/release/ReleaseMainTest.class
target/release-provenance-demo-1.4.0.jar
target/surefire-reports/TEST-org.example.release.ReleaseMainTest.xml
```

Dòng tổng kết tests dự kiến:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **phần kết quả kiểm thử cần xác minh**, không phải toàn bộ Maven console logs.

Chạy JAR:

```bash
java -jar target/release-provenance-demo-1.4.0.jar
```

**Stdout chính xác:**

```text
release-provenance-demo: OK
```

Vì đang ở build local không truyền Git SHA, manifest sẽ cho các headers:

```text
Git-Commit: local-unverified
Git-Tag: untagged
```

**Không phát hành artifact mang hai giá trị local ấy như một release đã được chứng thực.** Mục đích default là cho phép người học build ví dụ độc lập trước khi có Git repository/tag.

### 6.6. `audit/ArtifactAudit.java`: đọc manifest và tính SHA-256

Đây là một **utility Java 17 hoàn chỉnh** nhận đường dẫn JAR và hai expected values, sau đó kiểm tra `Git-Commit`, `Git-Tag`, hiển thị `Main-Class`, `Implementation-Version` và checksum.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class ArtifactAudit {
    private ArtifactAudit() {
    }

    private static String sha256(Path file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = Files.newInputStream(file)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = in.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                    "Usage: ArtifactAudit JAR EXPECTED_COMMIT EXPECTED_TAG");
            System.exit(2);
        }

        Path jarPath = Path.of(args[0]);
        String actualCommit;
        String actualTag;
        String mainClass;
        String implementationVersion;

        try (JarFile jar = new JarFile(jarPath.toFile())) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("Missing JAR manifest");
            }
            Attributes attributes = manifest.getMainAttributes();
            mainClass = attributes.getValue("Main-Class");
            implementationVersion = attributes.getValue(
                    "Implementation-Version");
            actualCommit = attributes.getValue("Git-Commit");
            actualTag = attributes.getValue("Git-Tag");
        }

        if (!args[1].equals(actualCommit)) {
            throw new IllegalStateException(
                    "Git-Commit does not match expected source");
        }
        if (!args[2].equals(actualTag)) {
            throw new IllegalStateException(
                    "Git-Tag does not match expected release tag");
        }

        System.out.println("Main-Class=" + mainClass);
        System.out.println("Implementation-Version="
                + implementationVersion);
        System.out.println("Git-Commit=" + actualCommit);
        System.out.println("Git-Tag=" + actualTag);
        System.out.println("SHA-256=" + sha256(jarPath));
        System.out.println("Metadata match: PASS");
    }
}
```

Compile **audit utility bên ngoài Maven main artifact**:

```bash
javac audit/ArtifactAudit.java
```

Trong project root, sau build local:

```bash
java -cp audit ArtifactAudit target/release-provenance-demo-1.4.0.jar local-unverified untagged
```

Các dòng đầu/cuối dự kiến:

```text
Main-Class=org.example.release.ReleaseMain
Implementation-Version=1.4.0
Git-Commit=local-unverified
Git-Tag=untagged
SHA-256=...  (64 ký tự hexadecimal của JAR thực)
Metadata match: PASS
```

Dòng `SHA-256=...` trong block trên là **dạng minh họa**, không phải stdout literal có thể đoán trước. Công cụ thật in **64 ký tự hexadecimal** sau dấu `=`. Giá trị phụ thuộc bytes artifact cuối. Những dòng còn lại xác định được từ POM/các đối số của demo.

**Giới hạn quan trọng:** utility này so **metadata trong JAR với giá trị kỳ vọng được người dùng cung cấp**. Nó không xác minh Git repository, chữ ký, CI logs hoặc trust chain. Nếu người dùng cấp expected values giả thì tool vẫn có thể báo `Metadata match: PASS`. Hãy kết hợp nó với bước CI nguồn bên dưới.

### 6.7. Vì sao đọc manifest bằng API Java?

File manifest tuân thủ Java JAR specification: một header dài có thể bị xuống dòng tại ranh giới byte và dùng dòng continuation. Không nên parse `MANIFEST.MF` bằng các quy tắc text line đơn giản kiểu “mỗi dòng là một header”.

`JarFile.getManifest()` cùng `Attributes.getValue()` đọc **logical header values**, tránh lỗi đọc nhầm newline continuation. Việc utility in Git SHA chính là phép đọc từ **artifact JAR đã đóng gói**, không dựa vào source POM ở workspace.

## 7. Tạo release artifact từ Git commit/tag đã kiểm chứng

### 7.1. Lệnh Bash cho Linux/macOS

Giả sử repository chứa POM demo và **tag `v1.4.0` đã tồn tại**. Đứng từ root repository; đây là script release **kiểm tra điều kiện rồi build**, không tự tạo hay push tag.

```bash
set -euo pipefail

TAG=v1.4.0
COMMIT="$(git rev-parse --verify HEAD)"
TAG_COMMIT="$(git rev-parse --verify "refs/tags/$TAG^{commit}")"

if [ -n "$(git status --porcelain)" ]; then
  echo "Refuse release: working tree is dirty" >&2
  exit 1
fi

if [ "$COMMIT" != "$TAG_COMMIT" ]; then
  echo "Refuse release: HEAD is not the tag commit" >&2
  exit 1
fi

mvn -B -ntp -Drelease.commit="$COMMIT" \
    -Drelease.tag="$TAG" clean verify

javac audit/ArtifactAudit.java
java -cp audit ArtifactAudit \
    target/release-provenance-demo-1.4.0.jar "$COMMIT" "$TAG"
```

Nếu ở Windows WSL/Bash có `sha256sum`:

```bash
sha256sum target/release-provenance-demo-1.4.0.jar
```

**Điều kiện trước khi chạy:** tag thực sự thuộc repository đang checkout và working tree sạch. Nếu script dừng ở `git rev-parse`, `git status` hoặc Maven tests, pipeline phải dừng **không publish**.

### 7.2. Windows PowerShell

Ví dụ tương đương khi đứng ở project root trong PowerShell:

```powershell
$tag = "v1.4.0"
$commit = (git rev-parse --verify HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Cannot resolve HEAD"
}

$tagRef = "refs/tags/" + $tag + "^{commit}"
$tagCommit = (git rev-parse --verify $tagRef).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Cannot resolve release tag"
}

$changes = git status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw "Cannot inspect Git working tree"
}
if ($changes) {
    throw "Refuse release: working tree is dirty"
}
if ($commit -ne $tagCommit) {
    throw "Refuse release: HEAD is not tag commit"
}

mvn -B -ntp "-Drelease.commit=$commit" "-Drelease.tag=$tag" clean verify
if ($LASTEXITCODE -ne 0) {
    throw "Maven build or tests failed"
}

javac audit/ArtifactAudit.java
if ($LASTEXITCODE -ne 0) {
    throw "Audit tool compilation failed"
}

java -cp audit ArtifactAudit target/release-provenance-demo-1.4.0.jar $commit $tag
if ($LASTEXITCODE -ne 0) {
    throw "Artifact metadata audit failed"
}

Get-FileHash -Algorithm SHA256 target/release-provenance-demo-1.4.0.jar
```

**PowerShell `Get-FileHash` và Bash `sha256sum` cùng tính SHA-256 của bytes file**. Cách trình bày output khác nhau, nhưng hex digest phải khớp cho cùng file bytes. `Get-FileHash` trả object với property `Hash`; khi đối chiếu, bỏ khác biệt chữ hoa/thường nếu phù hợp.

### 7.3. Manifest dự kiến sau build từ tag

Vì Maven nhận `-Drelease.commit` và `-Drelease.tag`, JAR có:

```text
Implementation-Version: 1.4.0
Git-Commit: <full commit object ID thực lấy từ Git>
Git-Tag: v1.4.0
Main-Class: org.example.release.ReleaseMain
```

Đây là dạng hiển thị logic, **không phải raw manifest phải giữ thứ tự**. Java Archiver có thể thêm headers khác và xuống dòng với một header quá dài. Dùng `ArtifactAudit` để kiểm tra logic values.

### 7.4. Phòng chống lẫn tag do nhầm phiên bản POM

Bản demo giữ POM `1.4.0` và tag `v1.4.0`. Trong hệ thống thật cần một gate **so version**: lấy `project.version` từ POM hiệu lực rồi đối chiếu với tag quy ước, ví dụ:

```bash
mvn -N -q -DforceStdout help:evaluate -Dexpression=project.version
```

Output dự kiến từ demo là:

```text
1.4.0
```

Khi một project có CI-friendly `${revision}`, phải đối chiếu **effective version và published POM** theo đúng quy trình (có thể cần flatten). Không dựa vào tên file JAR hoặc tag để suy version POM một cách không kiểm chứng.

## 8. Kết quả build/test phải gắn với **cùng artifact digest**

Một báo cáo release hữu ích cần ít nhất:

| Trường | Nguồn đáng tin cậy mong muốn |
| --- | --- |
| `repository` | Repository canonical URL từ CI checkout configuration |
| `commit` | Git full object ID của source thực sự checkout |
| `tag` | Release ref đã resolve/verified tới commit |
| `artifactGav` | POM effective GAV và repository artifact path |
| `artifactSha256` | SHA-256 tính trên **file JAR cuối** sau package |
| `ciRunId`, `ciRunUrl` | CI platform tự gán, không do user tự điền tùy ý |
| `builder` | CI runner image/VM/toolchain identity |
| `toolchain` | `mvn -version`, `java -version`, OS, build image digest |
| `tests` | Names/count/status và đường dẫn XML reports từ **run hiện tại** |
| `gates` | Unit tests, integration tests, dependency scan, static checks... |
| `buildStatus` | Thành công/thất bại theo CI exit code và gates |
| `artifactRepositoryUrl` | Nơi đã publish và khả năng đọc lại bytes |
| `approval` | Release approval/change record, nếu cần |
| `attestation` | Chữ ký, builder attestation, provenance reference nếu có |

**Không viết `tests=PASS` chỉ vì lệnh `mvn site` tạo một HTML report xanh.** Với Maven Surefire, nên lưu XML report tại:

```text
target/surefire-reports/TEST-org.example.release.ReleaseMainTest.xml
```

và CI job kết luận PASS từ exit code, test count, XML failures/errors/skipped và các quality gates khác.

### 8.1. Dữ liệu kết quả kiểm thử có thể giả cũ

Nếu build không `clean`, file XML có thể thuộc run trước. Nếu tests bị skip, project vẫn có thể package thành công; nếu CI chỉ tải một cached report, nó có thể nhầm với kết quả hiện tại.

Một release pipeline nên:

1. Checkout commit của tag vào workspace sạch.
2. Chạy `mvn -B clean verify` không skip tests.
3. Lưu test XML/logs dưới **CI run ID hiện tại**.
4. Fail nếu số test chạy thấp hơn ngưỡng theo policy.
5. Sau khi build PASS, tính SHA-256 file JAR đã tạo.
6. Gắn hash đó với CI run/test summary và source commit/tag.
7. Publish **chính file đã được kiểm tra**, không build lại tùy tiện rồi giả định giống bytes.
8. Nếu có signing/attestation, thực hiện theo policy với artifact digest và trusted identity.

### 8.2. Một file evidence bên ngoài JAR

Có thể tạo một **bản ghi text đơn giản** làm ví dụ (không phải chuẩn SLSA hay attestation đã ký), bằng Bash sau khi tests PASS:

```bash
ARTIFACT=target/release-provenance-demo-1.4.0.jar
SHA256="$(sha256sum "$ARTIFACT" | cut -d ' ' -f1)"

{
  printf 'artifact_gav=%s\n' "org.example:release-provenance-demo:jar:1.4.0"
  printf 'artifact_sha256=%s\n' "$SHA256"
  printf 'source_commit=%s\n' "$COMMIT"
  printf 'source_tag=%s\n' "$TAG"
  printf 'ci_run_id=%s\n' "${CI_RUN_ID:-local-manual}"
  printf 'surefire_xml=%s\n' \
      "target/surefire-reports/TEST-org.example.release.ReleaseMainTest.xml"
  printf 'build_result=%s\n' "verify-command-succeeded"
} > target/release-evidence.txt
```

Điều kiện: `COMMIT` và `TAG` đã được set/verified như mục 7, `sha256sum` hiện diện, Maven `verify` đã kết thúc với exit code 0. Nếu CI dùng biến ID khác, pipeline phải map nó thành `CI_RUN_ID` chính xác. **`local-manual` chỉ là dấu hiệu thao tác local**, không được nhận là CI run đã chứng thực.

Bản ghi ở `target/release-evidence.txt` cho phép tra cứu cơ bản. Tuy nhiên **nội dung có thể bị sửa bởi bất kỳ ai có quyền sửa file**; vì vậy không gọi nó là **attestation trusted**. Khi cần chain-of-custody mạnh, yêu cầu CI platform tạo attestation ký và policy kiểm tra.

### 8.3. Nên lưu evidence ở đâu?

Một thiết kế hợp lý:

```text
release record / artifact repository / CI artifacts:
  release-provenance-demo-1.4.0.jar
  release-provenance-demo-1.4.0.pom
  release-provenance-demo-1.4.0.jar.sha256
  source-commit.txt
  build-evidence.json hoặc .txt
  tests/TEST-*.xml
  build-toolchain.txt
  signed-attestation (nếu policy yêu cầu)
```

Thư mục/tên file trên là **cấu trúc ví dụ**, không phải Maven tự tạo mọi file. POM/JAR do Maven tạo và deploy; các bằng chứng còn lại cần **CI/release tooling** riêng quản lý.

Đừng đưa private deployment tokens, private keys, secret environment values vào published evidence.

## 9. SHA-256: nhận diện bytes, không tự chứng minh tính hợp pháp

Bằng Bash trên Linux/macOS:

```bash
sha256sum target/release-provenance-demo-1.4.0.jar
```

Bằng PowerShell trên Windows:

```powershell
(Get-FileHash -Algorithm SHA256 `
    target/release-provenance-demo-1.4.0.jar).Hash
```

Hai công cụ cho digest cùng giá trị khi input bytes y hệt. SHA-256 chỉ thay đổi khi bytes thay đổi, giả định hàm băm được sử dụng đúng.

### 9.1. Đối chiếu sau khi tải artifact

Nếu đã có một expected digest lấy từ release record tin cậy, tải JAR qua repository rồi:

1. Tính SHA-256 của **file đã tải**.
2. So với digest kỳ vọng bằng phép so khớp hex.
3. Xem manifest để đối chiếu commit/tag metadata.
4. Kiểm chứng published POM/GAV/version và dependency graph.
5. Xác minh provenance/chữ ký, builder identity và build policy.
6. Chạy smoke tests hoặc binary checks thích hợp trên file thực được triển khai.

Không chỉ so tên file hoặc `Implementation-Version`.

### 9.2. Checksum file đặt bên cạnh JAR có hạn chế

Nếu kẻ tấn công có quyền thay **cả JAR và file `.sha256`** ở cùng vị trí, chỉ đối chiếu hai file vẫn có thể PASS. Expected digest cần đến từ một nguồn có tính tin cậy/không thể bị sửa cùng kênh, ví dụ signed release manifest/attestation được kiểm chứng hoặc một hệ thống phát hành được bảo vệ.

**Hash đảm bảo equality theo input**, không tự xác minh tác giả hay nguồn build.

### 9.3. Chữ ký JAR khác chữ ký attestation

- **JAR signing**: xác thực một JAR theo cơ chế JAR signature/certificate (khi có).
- **Git tag signing**: bảo vệ một tag object bằng chữ ký.
- **Provenance attestation**: nói artifact digest nào được builder nào tạo từ input nào với parameters nào.
- **Checksums**: nhận diện bytes.

Những cơ chế này có thể **bổ sung** nhau, nhưng không thay thế nhau và không được coi là tương đương.

## 10. Reproducible build liên quan commit provenance như thế nào?

Một build được gọi là **reproducible** khi cùng source, inputs, environment và instructions có thể tạo ra những artifacts **byte-for-byte identical** trong những điều kiện được xác định. Đây là một cách kiểm chứng mối liên hệ từ source tới binary bằng xây dựng lại.

Apache Maven hướng dẫn dùng:

```xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

và các plugins hỗ trợ reproducible outputs. Demo đã khai báo property này.

**Nhưng:** một timestamp cố định **không đủ** nếu còn những yếu tố không được ghim, như:

- Compiler/JDK version/OS khác nhau.
- Versions của Maven plugins/dependencies thay đổi.
- Archive entry ordering.
- Generated content mang timestamp hiện tại.
- Artifact chứa absolute paths, usernames hoặc random values.
- Resource filtering phụ thuộc locale/timezone.
- CI run ID hoặc build timestamp thay đổi được nhúng vào JAR.
- Snapshot dependencies bị overwrite/chưa pin.

### 10.1. Vì sao không nhúng CI run ID vào manifest demo?

Giả sử cùng commit/tag được rebuild hai lần, CI IDs là `run-201` và `run-202`. Nếu build đóng gói `Ci-Run-Id` vào JAR, hai JAR khác bytes chỉ vì ID khác.

Chọn metadata **theo source/release** trong JAR (`Git-Commit`, `Git-Tag`, version) và metadata **theo run** ở sidecar/attestation giúp tăng khả năng build lại. Cần vẫn kiểm tra những nguồn không xác định khác.

### 10.2. Có thể kiểm tra Maven reproducibility như thế nào?

Apache Maven Reproducible Builds Guide gợi ý dùng Maven Artifact Plugin để kiểm tra build plan và so kết quả giữa lần build, ví dụ:

```bash
mvn clean install
mvn clean verify artifact:compare
```

Đây là **quy trình nâng cao** phụ thuộc Maven Artifact Plugin version/plugin resolution hiện tại. Trong CI production nên ghim plugin version cụ thể và đối chiếu cấu hình của tổ chức. Kết quả so sánh local hai lần **không phải bằng chứng mạnh** cho reproducibility độc lập ở máy khác.

Kiểm chứng cao hơn là **rebuild từ đúng commit/tag ở môi trường độc lập**, so SHA-256 artifact đã rebuild với digest published, và đối chiếu toolchain/dependency inputs. Nếu khác, cần phân tích buildinfo, timestamps, archive contents và source inputs.

### 10.3. Cẩn thận Maven version thay đổi theo thời gian

Với bài lab **Maven 3.9.x**, đặt `project.build.outputTimestamp` rõ trong POM giúp minh họa ý định. Những phiên bản Maven mới có thể thay đổi mặc định reproducible mode; vẫn phải xem **đúng Maven major/minor và plugin versions**. Không suy từ một build PASS rằng các artifacts sẽ tự reproducible ở mọi máy.

## 11. SLSA provenance và in-toto attestation: khi cần bằng chứng mạnh hơn

Một release quy mô lớn nên cân nhắc **SLSA provenance** hoặc in-toto attestation được tạo bởi trusted build platform, đặc biệt khi có yêu cầu supply-chain security.

Trong SLSA provenance v1.x, những khái niệm quan trọng gồm:

- **Subject**: artifact(s) được xác định bằng digest, ví dụ SHA-256.
- **Build definition**: build type, external parameters, resolved dependencies.
- **Run details**: builder identity, execution metadata, byproducts.
- **Source dependency**: repository/commit được ghi nhận bằng immutable digest/ref thích hợp.
- **Attestation**: một statement có thể được ký để consumer kiểm tra nguồn gốc và tính toàn vẹn.

Một file tự viết:

```text
commit=...
build=...
sha256=...
```

**không tự trở thành SLSA provenance hợp lệ**. Muốn tuyên bố theo SLSA, phải dùng đúng schema, producer/trust requirements và verify signature/policy theo mức đảm bảo đã chọn.

### 11.1. Ai là người đáng tin cậy tạo provenance?

Không nên tin một script chạy trong job không được bảo vệ có thể tự gán mình là “trusted builder” rồi ghi một file JSON. Provenance có ý nghĩa khi:

- Build platform identity được xác thực.
- Inputs/công thức build được ghi chính xác.
- Artifact digest được lấy từ outputs thật.
- Statement được ký hoặc được bảo vệ bằng cơ chế phù hợp.
- Consumer verify signer identity, source repository, ref/commit và build policy.

Maven POM có thể cung cấp cấu hình/metadata, nhưng **không tự cấp** attestation mạnh chỉ nhờ `mvn package`.

### 11.2. Chuỗi xác thực trong release pipeline

Một quy trình chuẩn hóa có thể gồm:

```text
Protected, signed release tag (nếu policy yêu cầu)
     |
Trusted CI checkout exact Git commit
     |
Build/test in controlled environment
     |
Final Maven artifact bytes
     |
SHA-256
     |
Trusted provenance attestation keyed by that digest
     |
Immutable artifact repository / controlled deployment
     |
Consumer verifies digest, signature and policy
```

Mỗi tổ chức có thể chọn mức bảo đảm khác nhau. Với lab cá nhân, manifest+Git gates+SHA+test XML là nền tảng. Với production cần bảo vệ release identities và chuỗi phát hành theo yêu cầu thực tế.

## 12. Maven Install, Deploy và artifact repository

`mvn package` tạo JAR trong `target/`; `mvn install` cài artifacts vào local repository; `mvn deploy` phát hành Maven artifacts tới remote repository được cấu hình.

Cú pháp POM có thể có:

```xml
<distributionManagement>
    <repository>
        <id>releases</id>
        <url>https://repo.example.invalid/maven/releases</url>
    </repository>
    <snapshotRepository>
        <id>snapshots</id>
        <url>https://repo.example.invalid/maven/snapshots</url>
    </snapshotRepository>
</distributionManagement>
```

Đây là **fragment minh họa**, domain `.invalid` cố ý không trỏ repository thật và **không nằm trong POM lab**. Release deployment cần URL thật, credentials ở `settings.xml`/secret manager, và approval phù hợp.

**Không đặt password, access token hoặc private key trực tiếp trong POM.**

### 12.1. Vì sao `deploy` có thể phá chuỗi truy xuất?

Nếu CI có hai jobs:

```text
Job A: mvn clean verify      → test JAR A
Job B: mvn clean deploy      → rebuild JAR B
```

thì bạn cần **chứng minh A và B có cùng bytes**. Nếu không có reproducibility check, `Job B` có thể upload một file khác với file đã được test/approved.

Thiết kế tốt hơn:

- Build một lần, test artifact đó, tính digest.
- Giữ JAR/POM/evidence như CI artifacts có kiểm soát.
- Publish đúng file JAR đã build/test; hoặc
- Nếu bắt buộc rebuild, so hash với artifact được test và fail khi khác.

### 12.2. `deploy` không tự có test provenance

Maven Deploy Plugin quan tâm tới publication của artifacts và POM theo `distributionManagement`; nó **không tự sinh** một report đầy đủ về Git SHA/tag/test results/CI run policy. Những thông tin ấy phải được pipeline bổ sung.

Trong release repository, nên lưu GAV, original JAR SHA-256, POM SHA-256, source commit, CI run link, test summary và attestation reference. Tên/version thôi chưa đủ.

### 12.3. Rollback cũng cần provenance

Khi rollback, đừng chỉ đổi version string theo trí nhớ. Chọn **artifact digest đã được deploy và phê duyệt trước đó**; xác nhận source commit/tag, CI build, tests, config compatibility và trạng thái lỗ hổng theo policy.

Một release tag có thể còn tồn tại trong Git nhưng artifact repository đã bị overwrite hoặc xóa. Vì thế phải quản lý **lịch sử artifact bytes và deployment** như dữ liệu phát hành riêng biệt.

## 13. Quy trình CI tham khảo từ tạo tag đến deploy

Một pipeline có thể tách thành các giai đoạn:

| Bước | Hành động | Điều kiện chặn |
| --- | --- | --- |
| 1. Trigger | Chỉ nhận protected release tag | Trigger từ PR hoặc branch không được publish release |
| 2. Checkout | Fetch ref, checkout exact commit | Không resolve đúng tag hoặc không khớp HEAD |
| 3. Verify source | Clean tree, review/signature policy | Dirty/unsigned tag không đạt policy |
| 4. Version gate | POM version vs tag | `v1.4.0` không khớp `1.4.0` |
| 5. Build | JDK/Maven/plugins pinned, `clean verify` | Exit code khác 0 |
| 6. Test QA | Đọc Surefire/Failsafe XML, quality gates | Tests thiếu/skipped/fail ngoài policy |
| 7. Artifact QA | Read manifest, compute SHA-256 | Metadata sai, main JAR thiếu, hash không ghi được |
| 8. Record evidence | Link commit, tag, run ID, digest, tests | Thiếu source/run/digest |
| 9. Sign/attest | Trusted builder ký theo policy | Không verify identity/signature |
| 10. Publish | Đúng file bytes tới immutable release repo | Upload lỗi hoặc digest repository khác |
| 11. Deploy | Đúng digest đã phê duyệt | Mismatch giữa approved và deployed |
| 12. Audit/rollback | Lưu evidence và retrieval | Logs/artifacts thiếu retention |

**Không có lệnh Maven duy nhất tự làm đầy đủ 12 bước.** Maven đảm nhiệm phần build/test/package/deploy phù hợp; Git/CI/artifact registry/provenance tooling phối hợp các bước khác.

### 13.1. Đừng nhầm job success với tests PASS

Nếu CI chạy `mvn clean package -DskipTests`, job có thể xanh, nhưng Surefire không chạy tests. Nếu Failsafe không được bind `integration-test`/`verify`, integration tests cũng có thể chưa chạy.

Hồ sơ phát hành nên ghi **thực tế**: số tests executed, failures, errors, skips, tên test suites, quality gates và trạng thái. Đừng suy tổng số tests từ số file HTML hoặc chỉ log `BUILD SUCCESS`.

### 13.2. Repo source metadata và Maven artifact version cần nhất quán

Trong một mono-repo nhiều Maven modules, có thể nhiều JAR từ cùng commit nhưng **khác GAV**. Mỗi artifact nên có digest riêng và được ghi trong release manifest/evidence. Không dùng một SHA-256 đại diện cho tất cả JARs.

Tương tự, Maven aggregator/parent POM có thể được publish như artifact **packaging=pom**; dù không tạo JAR, nó có published POM bytes cần version và provenance phù hợp.

### 13.3. Chốt source và binaries trong cùng release manifest

Lý tưởng release record cho biết:

```text
source: repository + immutable commit
release: tag + version
build: CI run ID + builder + parameters
quality: test results + pass/fail gates
outputs: every artifact GAV + SHA-256
publication: repository URL + upload verification
deployment: environment + deployed SHA-256
```

Một dòng release record trong dashboard không thể thay toàn bộ evidence nếu nó không dẫn tới dữ liệu gốc và không kiểm chứng được hash.

## 14. Xử lý các tình huống thực tế

### 14.1. Artifact trong production ghi `Git-Commit` đúng nhưng CI run không tìm thấy

Có thể CI logs đã hết retention, artifact bị copy thủ công, manifest bị sửa sau build hoặc build không được chạy bởi hệ thống đáng tin cậy. Cần xem release registry, deployment record, artifact digest và attestation. **Commit label đúng chưa chứng minh CI từng chạy tests.**

Giải pháp dài hạn: lưu release evidence/attestation đủ lâu và gắn bằng artifact SHA.

### 14.2. Git tag trùng version nhưng trỏ commit khác

Có thể ai đó retag sau release hoặc job checkout sai. **Không** publish tiếp chỉ vì Maven version vẫn là `1.4.0`. So SHA lưu trong release record với tag đã peel hiện tại và commit của job. Nếu không khớp, chặn release và điều tra.

### 14.3. Hai CI runs cùng tag cho hai checksum khác nhau

Có thể run ID/timestamp được nhúng vào JAR, dependency snapshot thay đổi, JDK/compiler/plugin khác, generated resources mang giờ hiện tại hoặc build không deterministic. So manifest, archive entries, plugin versions, toolchain và input artifacts. **Không mặc định một trong hai là malicious**, nhưng không được bỏ qua mismatch.

### 14.4. Maven build PASS nhưng không thấy test XML

Có thể không có tests, test naming sai, bị skip, Surefire provider lỗi hoặc báo cáo nằm ở thư mục khác theo config. Kiểm tra `target/surefire-reports`, Surefire logs và test count. **Không báo release quality gate PASS** nếu policy yêu cầu tests mà không có bằng chứng.

### 14.5. GAV giống nhau nhưng JAR ở hai repositories khác hash

Đây là dấu hiệu repository divergence/overwrite hoặc artifacts do hai workflows khác tạo. Cần quyết định **digest đã được approval** và kiểm tra repository hiện được deploy. Không dựa vào tên `artifactId-version.jar`.

### 14.6. Manifest `Git-Commit` hiển thị SHA ngắn

SHA rút gọn tiện đọc nhưng có thể tăng nguy cơ trùng khi repository lớn; release records nên giữ **full object ID**. UI có thể hiển thị prefix, nhưng API/evidence nên giữ bản đầy đủ từ Git.

### 14.7. JAR là uber/fat JAR đã qua Shade

Artifact cuối có thể **khác JAR thường**. Nếu build dùng Shade/Assembly, checksum và provenance phải tính trên **đúng file đã publish/deploy**, không phải intermediate `target/original-...jar` hoặc main JAR chưa shade. Có thể kiểm tra manifest cuối, vì Shade transformer có thể sửa hoặc thay metadata từ JAR nguồn.

### 14.8. Tag signed nhưng JAR không signed

Đây là trạng thái có thể xảy ra: tag signature chỉ chứng minh tag object, không chứng minh jar bytes. Nếu policy đòi signed artifacts, phải ký artifact hoặc attestation đúng bước và verify sau packaging. Không suy “Git tag signed ⇒ Maven JAR signed”.

### 14.9. Checksums giống nhau nhưng build logs khác nhau

Nếu JAR bytes giống, khác nhau về thời gian run, runner ID hoặc thông tin không ảnh hưởng output là bình thường. Reproducibility hướng tới artifact bytes, không hướng tới mọi dòng log giống hệt. Vẫn cần kiểm tra mỗi run có đáp ứng policy tests/approval hay không.

### 14.10. Git repo có submodules hoặc generated sources

Git commit ID của top-level repo không đủ mô tả mọi input nếu build dựa trên submodules, external downloads, generated code, Git LFS objects hoặc private dependencies. Build record/provenance cần chỉ rõ **resolved dependencies** và các input digests/refs quan trọng. Đừng tuyên bố “chỉ cần một SHA của repo là đủ” cho mọi build system.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| JAR ghi `local-unverified` | CI không cấp property Git | Verify Git, truyền `-Drelease.commit` |
| JAR ghi `untagged` khi phát hành | Không cấp tag hoặc build từ branch | Dừng release, kiểm tra tagged checkout |
| Tag không trỏ HEAD | Checkout sai commit/ref hoặc tag bị đổi | So `git rev-parse HEAD` với peeled tag |
| `git tag -v` fail | Tag unsigned/không tin key/chữ ký lỗi | Kiểm tra tag policy và trusted keys |
| JAR có version khác tên tag | POM/CI version mismatch | Chặn publish, đọc `project.version` |
| `java -jar` báo no main manifest attribute | Main-Class chưa set hoặc chạy nhầm JAR | Kiểm tra maven-jar-plugin, artifact cuối |
| `ArtifactAudit` báo mismatch | Manifest metadata không khớp expected | Kiểm tra CLI properties, checkout, file đúng |
| `ArtifactAudit` chỉ ra SHA khác release record | File bytes bị thay hoặc record sai | Không deploy, điều tra nguồn |
| `mvn package` có JAR mà tests không chạy | Skip/no tests/plugin config | Kiểm tra Surefire XML, summary |
| Surefire XML có dữ liệu cũ | Reuse target/cache | `mvn clean verify`, audit timestamps |
| GAV đúng nhưng hash khác ở prod | Repository overwrite, copy sai file | So release digest với deployed binary |
| Same tag rebuild cho hash khác | Timestamp/build ID/snapshot/toolchain | Reproducible build investigation |
| CI run link trả 404 | Retention hoặc quyền truy cập | Lưu evidence độc lập lâu dài |
| Manifest chứa commit SHA rút gọn | Script dùng short hash | Dùng `git rev-parse --verify HEAD` |
| Site report hiển thị PASS nhưng build failed | HTML report cũ hoặc quality gate không bind | Kết quả run/exit code/test XML hiện tại |
| Artifact deploy thiếu POM | Upload file riêng không đủ Maven metadata | Kiểm tra published POM và GAV |
| Snapshot thay bytes nhưng cùng version | Snapshot lifecycle/repository semantics | Ghi timestamped version và digest cụ thể |
| Signed tag nhưng artifact không được chứng thực | Không có attestation/JAR signature | Verify artifact provenance riêng |
| Audit chạy trên unshaded JAR | Chọn sai output | Hash và audit chính published JAR |
| Release build lấy `main` thay tag | CI checkout ref sai | Gate HEAD == peeled tag |
| CI job đỏ nhưng release vẫn publish | Workflow conditions thiếu | Fail closed nếu gates chưa PASS |
| `mvn deploy` build lại khác artifact tested | Hai jobs package khác nhau | Promote exact file hoặc compare digests |
| Provenance file có chữ “trusted” nhưng không ký | File metadata tự khai | Dùng trusted builder và verify identity/signature |
| Dependency ngoài repository thay đổi | Version range/snapshot/chưa pin | Pin inputs, ghi resolved dependency digests |

### 15.1. Quy trình debug có thể lặp lại

1. Xác định **file artifact thực tế** được triển khai.
2. Tính SHA-256 của file ấy và so release record.
3. Đọc manifest `Git-Commit`/`Git-Tag` của chính file ấy.
4. Peel Git tag và kiểm tra commit trong release record.
5. Lấy CI run ID/URL, source checkout SHA, `mvn -version`.
6. Đọc test XML của đúng run, test count và quality gates.
7. So GAV/POM version với tag/repository path.
8. Xem artifact repository upload history/digest.
9. Nếu cần mạnh hơn, verify signed provenance/attestation policy.
10. Chỉ khi mối liên hệ hợp lệ mới kết luận artifact tương ứng release đã kiểm thử.

## 16. Câu hỏi tự kiểm tra

**1.** Maven `1.4.0` có tự chứng minh Git commit không?  
**Đáp án:** Không. Maven version là coordinate, không phải cryptographic source provenance.

**2.** Vì sao cần full commit object ID?  
**Đáp án:** Để định danh chính xác commit, tránh dựa vào branch/ref di động hoặc short SHA.

**3.** `git tag -a` và `git tag -s` khác gì?  
**Đáp án:** Cả hai tạo annotated tag; `-s` ký tag object bằng signing key.

**4.** Vì sao peel tag bằng `^{commit}`?  
**Đáp án:** Để lấy commit phía sau annotated/lightweight tag, không nhầm tag object ID với commit ID.

**5.** `Git-Commit` trong manifest do Maven tự tra Git chưa?  
**Đáp án:** Không trong demo; pipeline phải truyền `-Drelease.commit` sau khi kiểm chứng Git.

**6.** Tại sao CI run ID nằm ở file evidence bên ngoài JAR?  
**Đáp án:** Run ID thay đổi ở mỗi lần chạy; nhúng vào JAR sẽ khiến bytes/hash thay đổi dù source giống.

**7.** `Git-Commit` trong manifest có chứng minh artifact hợp pháp không?  
**Đáp án:** Không; header là metadata tự khai, cần trusted build chain/attestation.

**8.** SHA-256 dùng để làm gì?  
**Đáp án:** Nhận diện và đối chiếu chính xác bytes của artifact.

**9.** Nếu kẻ tấn công sửa JAR lẫn checksum bên cạnh, checksum kiểm chứng được tác giả không?  
**Đáp án:** Không; cần expected digest từ nguồn đáng tin hoặc chữ ký/attestation.

**10.** `mvn clean verify` có tự chứng minh tests chạy đầy đủ không?  
**Đáp án:** Không; cần kiểm tra skip flags, test count, Surefire/Failsafe XML và quality gates.

**11.** Vì sao lưu CI run URL?  
**Đáp án:** Để truy cập logs, evidence và các bước kiểm thử đã xảy ra; cần retention và quyền truy cập phù hợp.

**12.** Làm sao xác nhận file production là bản đã được QA?  
**Đáp án:** So production artifact SHA-256 với digest đã được ghi và phê duyệt sau QA, cùng provenance.

**13.** Release tag có thể bị di chuyển không?  
**Đáp án:** Có nếu ai đó có quyền sửa ref; cần bảo vệ tags và ghi commit SHA tại release.

**14.** Ký tag có đồng nghĩa ký JAR không?  
**Đáp án:** Không. Chúng xác thực những đối tượng khác nhau.

**15.** Một rebuild cùng commit có hash khác nghĩa là gì?  
**Đáp án:** Cần điều tra nondeterministic inputs/toolchains/metadata, không tự kết luận artifact nào đáng tin.

**16.** Artifact GAV giống nhau có bảo đảm file JAR bytes giống nhau không?  
**Đáp án:** Không nếu repository cho overwrite hoặc build inputs khác.

**17.** SLSA provenance là chỉ một file text có `commit` và `sha256`?  
**Đáp án:** Không; cần statement schema, builder identity và cơ chế xác minh theo policy.

**18.** Vì sao nên publish file JAR đã được QA thay vì rebuild ở deploy job?  
**Đáp án:** Để bảo đảm bytes được deploy là bytes đã được test/phê duyệt; nếu rebuild cần verify hash equality.

**19.** Một mono-repo có nhiều Maven modules nên lưu một SHA-256 chung?  
**Đáp án:** Không. Mỗi artifact bytes có digest riêng; chúng có thể cùng source commit.

**20.** Các tình huống nào làm thiếu nguồn gốc dù Git SHA đúng?  
**Đáp án:** External dependencies, submodules, generated sources, build container, toolchain và artifact publication không được kiểm soát.

## 17. Checklist phát hành Maven có thể truy xuất

- [ ] Release trigger từ protected tag hoặc workflow được phê duyệt.
- [ ] Git checkout chính xác commit được tag chỉ đến.
- [ ] Working tree sạch, nguồn phụ thuộc được kiểm soát.
- [ ] Release tag được bảo vệ; signature được verify nếu policy yêu cầu.
- [ ] Maven GAV/project version khớp quy ước release tag.
- [ ] JDK/Maven/plugin versions và build image được ghi.
- [ ] Không dùng unpinned SNAPSHOT/dynamic dependencies trong release nếu policy cấm.
- [ ] `mvn clean verify` đã chạy thành công, không skip checks bắt buộc.
- [ ] Surefire/Failsafe XML của chính run có test count/status đúng.
- [ ] Artifact JAR cuối có `Implementation-Version`, `Git-Commit`, `Git-Tag` như dự kiến.
- [ ] Không phát hành JAR có `local-unverified`/`untagged`.
- [ ] SHA-256 được tính trên **file cuối sẽ publish/deploy**, không trên intermediate.
- [ ] CI run ID/URL gắn với commit/tag/GAV/digest và test evidence.
- [ ] Run-specific metadata nằm ngoài JAR nếu cần reproducibility.
- [ ] Có signed provenance/attestation nếu supply-chain policy đòi hỏi.
- [ ] Expected checksum/attestation được lưu ở kênh đáng tin cậy.
- [ ] Release repository không cho overwrite tùy ý cùng GAV.
- [ ] Artifact published đã được tải lại/đối chiếu bytes khi cần.
- [ ] Deployment dùng đúng digest đã được kiểm thử/phê duyệt.
- [ ] Có release/rollback history và retention đủ cho audit.
- [ ] Không lộ secrets, signer keys hoặc private tokens trong manifest/evidence.
- [ ] Logs test và provenance tồn tại lâu hơn thời gian cần truy vết sự cố.

## 18. Tài liệu chính thức và chuẩn tham khảo

1. [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html) — artifact coordinates, versions, dependencies.
2. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — `package`, `verify`, `install`, `deploy`.
3. [Apache Maven JAR Plugin — Manifest Customization](https://maven.apache.org/plugins/maven-jar-plugin/examples/manifest-customization.html) — Main-Class và custom archive manifest.
4. [Apache Maven Archiver — Manifest Entries](https://maven.apache.org/shared/maven-archiver/examples/manifestEntries.html) — custom `manifestEntries`.
5. [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html) — `outputTimestamp`, build plan và compare.
6. [Apache Maven Deploy Plugin — Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html) — `distributionManagement`, artifact repository.
7. [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/) — test execution và XML reports.
8. [Git — git-rev-parse](https://git-scm.com/docs/git-rev-parse) — full commit ID, `^{commit}` peel syntax.
9. [Git — git-tag](https://git-scm.com/docs/git-tag) — annotated/signed tags, verify.
10. [SLSA — Build Provenance v1](https://slsa.dev/spec/v1.1/provenance) — subject digest, build definition, run details, builder.
11. [in-toto — Attestation Statement](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md) — statement subject/predicate structure.
12. [Java SE 17 — JarFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html) — đọc manifest entries từ packaged JAR.
13. [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html) — SHA-256 digest.
14. [Java SE 17 — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html) — chuyển digest bytes sang hex.

**Kết luận:** **Commit SHA** định danh nguồn Git; **tag** định danh mốc release (phải resolve tới đúng commit); **Maven GAV** định danh artifact theo repository; **CI run/test reports** mô tả lần build và chất lượng kiểm thử; **SHA-256** định danh chính xác bytes file. Chỉ khi kết nối và **kiểm chứng** những thứ đó — lý tưởng với trusted provenance/attestation phù hợp — bạn mới có thể nói artifact đang phát hành hay triển khai thực sự tương ứng bản code và build đã được duyệt.
