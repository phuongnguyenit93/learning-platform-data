# Build một lần và đưa đúng artifact qua các bước phát hành

> **Nhóm: IDE và CI — Build Tool Maven.** Bài này trình bày nguyên tắc *build once, promote many*: biên dịch/kiểm thử một bản Maven artifact duy nhất, giữ nguyên **bytes** của artifact đó khi chuyển qua các cổng kiểm tra, repository và môi trường triển khai. Mục tiêu là chứng minh **thứ chạy ở production chính là thứ đã được kiểm thử và phê duyệt**, không chỉ có cùng tên hoặc version.

## 1. Cùng version không đồng nghĩa cùng artifact

Giả sử ứng dụng Java có tọa độ Maven `dev.lesson:build-once-demo:1.0.0`. Một pipeline thiếu kiểm soát có thể:

```text
Developer IDE           CI Build             Staging                  Production
mvn package             mvn verify           mvn package              mvn package
    |                       |                    |                        |
    v                       v                    v                        v
app-1.0.0.jar A          app-1.0.0.jar B     app-1.0.0.jar C         app-1.0.0.jar D
```

Bốn tệp có cùng tên/GAV nhưng **không chắc có cùng bytes**. JDK/compiler version, plugin versions, dependency graph, môi trường, time, locale, resource filtering, profiles, build timestamp hoặc source revision có thể làm file khác nhau.

QA đã test JAR B nhưng production chạy JAR D. Nếu hai file khác nhau, việc test B không tự chứng minh D có cùng hành vi.

**Luồng nên dùng:**

```text
Git commit/tag đã được phê duyệt
                |
                v
        CI Build & Test (một lần)
                |
                v
       Immutable candidate
       app.jar + POM + SHA-256 + source SHA
                |
       +--------+---------+
       |                  |
       v                  v
   QA / Staging      Security / Approval
       |                  |
       +--------+---------+
                |
                v
     Publish/promote exact artifact
                |
         +------+------+
         |             |
         v             v
     Pre-production   Production
         |             |
         +-- cùng artifact bytes/digest
```

Khi artifact đã qua test, các bước sau **không chạy lại compiler/packager**. Chúng chỉ tải, xác minh, copy/publish/promote và triển khai file đã có. Đây chính là ý nghĩa của **“build một lần”**.

### Tại sao cách này quan trọng?

- Cho phép trace từ Git commit đến artifact đã dùng để test và deploy.
- Tránh staging/production tạo binary khác do environment.
- Có thể rollback bằng artifact cũ đã lưu thay vì build lại tag cũ.
- Giúp tách job build ít đặc quyền khỏi job publish có credentials.
- Giảm duplicate builds và những lỗi do hai lần resolve dependency khác nhau.
- Dễ gắn test reports, SBOM, chữ ký/provenance và approvals với một artifact cụ thể.
- Có khả năng so sánh SHA-256 ở mọi điểm bàn giao.

**Giới hạn:** cùng một JAR vẫn có thể hoạt động khác ở môi trường có cấu hình, JDK/runtime, database, network và secrets khác nhau. Build-once giữ **binary identity**, không thay thế integration tests hoặc kiểm tra môi trường.

## 2. Phân biệt các thuật ngữ dễ bị dùng lẫn

| Thuật ngữ | Định nghĩa | Bằng chứng phù hợp |
| --- | --- | --- |
| Build success | Maven goals kết thúc thành công | `BUILD SUCCESS` và reports |
| Functional correctness | Tests thực thi hành vi và assertions được chọn | Unit/IT/contract/security reports |
| Reproducible build | Có thể **rebuild** từ inputs tương đương để cho bytes giống nhau | Hai hash từ independent rebuild |
| Build once | Một build tạo ra candidate được giữ lại | CI run ID và immutable artifact object |
| Immutable artifact | Artifact không được sửa/ghi đè dưới cùng danh tính | Object digest, repository immutability |
| Artifact promotion | Chuyển **file đã test** sang trạng thái/repository được cho phép | Hash trước–sau, approval/audit |
| Maven artifact deploy | Upload JAR/POM/metadata vào Maven repository | GAV/registry metadata và checksum |
| Runtime deployment | Đưa ứng dụng vào môi trường chạy | Deployment manifest, artifact digest/config version |
| Provenance | Bằng chứng source/builder/inputs dẫn đến output | Build attestation/signature |

**Build tái lập** có nghĩa hai lần build độc lập *có thể* cho cùng kết quả byte. **Build-once** thì ngược lại: chỉ build một candidate, rồi chuyển **chính object đó**. Hai ý tưởng hỗ trợ nhau nhưng không đồng nghĩa.

## 3. “Đúng artifact” phải xác định bởi nhiều trường

Maven sử dụng tọa độ theo cấu trúc:

```text
groupId:artifactId:version[:type[:classifier]]
```

Ví dụ:

```text
dev.lesson:build-once-demo:1.0.0:jar
```

Tọa độ này giúp Maven dependency resolver chọn thư viện, nhưng nó **không phải fingerprint của bytes**. Nếu repository cho phép overwrite hoặc cache trỏ tới file khác, cùng GAV có thể không đảm bảo cùng binary.

Một release record nên có:

| Bằng chứng | Ý nghĩa |
| --- | --- |
| Git commit SHA | Nguồn source được build |
| Git release tag | Nhãn release đã phê duyệt |
| Group/artifact/version/type/classifier | Định danh Maven package |
| SHA-256 của JAR | Định danh byte của artifact chính |
| SHA-256 của consumer POM | Bảo toàn dependency metadata |
| SHA-256 của attached artifacts | Sources/Javadocs/signatures/SBOM nếu có |
| CI run ID/job/attempt | Nguồn build và test reports |
| Maven/JDK/toolchain/plugin versions | Khả năng audit cách tạo file |
| Builder identity/provenance/signature | Xác minh người/hệ thống tạo output |
| Repository object/version | Vị trí immutable được publish |
| Environment/config revision | Biết runtime nào đang dùng file đó |

**Đừng nhầm:** Git SHA nhận diện source revision, SHA-256 JAR nhận diện **binary**, còn digest do CI artifact service trả về có thể nhận diện **ZIP chứa nhiều files**. Ba thứ này không hoán đổi cho nhau.

### Một checksum có chứng minh an toàn không?

Không. Hash chỉ chứng minh nội dung file so với một **giá trị tham chiếu đáng tin**. Nếu một đối tượng độc hại sửa đồng thời `app.jar` và `SHA256SUMS`, phép kiểm checksum nội bộ vẫn có thể xanh. Cần trust vào source CI run/identity, protection rules, repository permissions, chữ ký/provenance và approvals.

## 4. Maven lifecycle có thể âm thầm build lần thứ hai

Default lifecycle Maven có các mốc:

```text
validate -> compile -> test -> package -> verify -> install -> deploy
```

Khi chạy:

```bash
mvn -B -ntp clean verify
```

Maven đi qua compile/test/package và quality checks đã cấu hình, thường tạo JAR tại `target/`.

Một lỗi pipeline phổ biến:

```bash
# Job kiểm thử:
mvn -B -ntp clean verify

# Job phát hành chạy ở worker khác:
mvn -B -ntp deploy
```

**`mvn deploy` là phase của default lifecycle**, nên job publisher có thể chạy lại compile/test/package trước khi upload. Điều đó không bảo đảm JAR thứ hai trùng bytes với JAR được QA.

Các lệnh `mvn package`, `mvn verify` hoặc `mvn install` ở bước staging cũng có cùng rủi ro nếu dùng để dựng lại binary.

### `-DskipTests` không sửa được lỗi này

```bash
mvn deploy -DskipTests=true
```

Cờ skip tests không biến `deploy` thành lệnh copy file. Maven vẫn có thể chạy compiler/resources/JAR/other goals. Vì vậy vẫn không đảm bảo **đúng JAR cũ**.

### Những cách publish không rebuild

1. **Repository manager promotion:** dùng chức năng staging/close/release/promote của Nexus/Artifactory/nền tảng tương đương để chuyển object đã kiểm thử.
2. **Maven Deploy Plugin `deploy:deploy-file`:** upload một JAR/POM **đã được tạo**, không chạy default lifecycle packaging.
3. **Object storage:** upload immutable ZIP/JAR/TAR theo digest.
4. **Container image registry:** promote/deploy theo OCI image digest `sha256:...`, tránh chạy lại `docker build` ở mỗi stage.

Ở đây **`mvn deploy:deploy-file`** là **goal** có dấu hai chấm; **`mvn deploy`** là **phase**. Đây là khác biệt quyết định đối với “build một lần”.

## 5. Vai trò IDE so với CI trong phát hành

Developer có thể dùng IntelliJ IDEA, Eclipse hoặc VS Code để:

- Import `pom.xml`.
- Chạy unit tests, debug và thử local JAR.
- Kiểm tra dependency tree/effective POM trong môi trường phát triển.
- Phát hiện lỗi trước khi push.

Tuy nhiên artifact từ IDE không nhất thiết là **bản chính thức**. Laptop có thể dùng JDK khác, local Maven repo có SNAPSHOT riêng, environment variables/profile khác hoặc có uncommitted changes.

Quy trình phù hợp hơn:

```text
IDE -> source code/tests
  -> reviewed Git commit/protected tag
  -> CI build controlled toolchain
  -> immutable artifact bundle
  -> QA/security/approval
  -> release repository
  -> deployment consumes artifact by immutable identity
```

Nếu tổ chức cho phép release từ máy developer, cần thiết lập **cùng bằng chứng**: clean source revision, pinned toolchain, test results, provenance, hashes, upload audit. Không mặc định IDE artifact được miễn kiểm chứng.

## 6. Dự án Java 17 minh họa hoàn chỉnh

Dùng project đơn module `build-once-demo` để học nguyên tắc đúng byte. JAR không có runtime dependency ngoài Java 17. Version `1.0.0` tương ứng tag `v1.0.0` trong workflow ví dụ.

### Cấu trúc

```text
build-once-demo/
├── pom.xml
└── src/
    ├── main/java/dev/lesson/handoff/ArtifactApp.java
    └── test/java/dev/lesson/handoff/ArtifactAppTest.java
```

`target` do Maven sinh, không commit vào Git.

### `pom.xml` đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.lesson</groupId>
    <artifactId>build-once-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Build Once Demo</name>
    <description>Promote one tested Maven artifact without rebuilding</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>dev.lesson.handoff.ArtifactApp</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Các quyết định thiết kế:**

- Java 17, Compiler Plugin `3.13.0` và JAR Plugin `3.4.2` được pin.
- JUnit Jupiter `5.11.4` + Surefire `3.5.2` cung cấp unit test gate.
- `failIfNoTests=true` ngăn việc tình cờ chạy 0 tests rồi tuyên bố xanh.
- `project.build.outputTimestamp` là giá trị cố định để giảm biến động ZIP/JAR entry timestamps. Đây là **mốc minh họa**, không phải yêu cầu mọi version phải dùng 2024.
- JAR có `Main-Class`, chạy được bằng `java -jar`.
- POM **không chứa credentials**, cũng không cần khai remote deployment URL cho phần build.
- Project không có sources/Javadocs/SBOM/signatures: phần sau giải thích cách mở rộng artifact set nếu release thực cần.

### `src/main/java/dev/lesson/handoff/ArtifactApp.java`

```java
package dev.lesson.handoff;

public final class ArtifactApp {

    private ArtifactApp() {
    }

    public static long add(long a, long b) {
        return Math.addExact(a, b);
    }

    public static void main(String[] args) {
        System.out.println("HANDOFF_RESULT=" + add(2, 3));
    }
}
```

Method `add` dùng Java `Math.addExact`. Phép cộng tràn `long` sẽ ném `ArithmeticException`. Code không đọc time, network hay variables; dễ smoke test nhất quán.

### `src/test/java/dev/lesson/handoff/ArtifactAppTest.java`

```java
package dev.lesson.handoff;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ArtifactAppTest {

    @Test
    void addsTwoNumbers() {
        assertEquals(5L, ArtifactApp.add(2, 3));
    }

    @Test
    void detectsOverflow() {
        assertThrows(
                ArithmeticException.class,
                () -> ArtifactApp.add(Long.MAX_VALUE, 1)
        );
    }
}
```

Hai test invocations chạy ở phase `test`. Đây chỉ là bài toán học tập; bộ test của dự án nghiệp vụ phải bao phủ yêu cầu, integration, security và edge cases theo rủi ro.

### Build và chạy JAR

```bash
mvn -version
java -version
mvn -B -ntp clean verify
java -jar target/build-once-demo-1.0.0.jar
```

**Stdout chính xác do ứng dụng in:**

```text
HANDOFF_RESULT=5
```

File đầu ra chính:

```text
target/build-once-demo-1.0.0.jar
target/surefire-reports/
```

Lệnh `clean verify` là **lần build được chọn làm candidate**. Sau bước này, những lệnh release/staging ở các mục sau **không build JAR thêm lần nào**.

## 7. Tạo gói bàn giao JAR + POM + source commit + checksum

Để không phụ thuộc tên `target/*.jar` ở mỗi job, đưa mọi output release candidate vào một thư mục được định nghĩa rõ:

```text
handoff/
├── app.jar
├── pom.xml
├── source-commit.txt
└── SHA256SUMS
```

- `app.jar`: **bản copy nguyên byte** từ `target/build-once-demo-1.0.0.jar`.
- `pom.xml`: POM được chọn để publish cùng artifact, không lấy từ checkout khác.
- `source-commit.txt`: full Git SHA của source commit được build.
- `SHA256SUMS`: SHA-256 của các files ở trên để phát hiện tình trạng sai bytes khi chuyển.

**Không đưa vào bundle:** Maven settings có secrets, `~/.m2`, SSH private keys, Git tokens, cloud credentials hoặc log nhạy cảm.

### Tạo handoff trên Linux

```bash
mkdir -p handoff
cp target/build-once-demo-1.0.0.jar handoff/app.jar
cp pom.xml handoff/pom.xml

# Chỉ chạy khi project đã nằm trong Git checkout đúng commit:
git rev-parse HEAD > handoff/source-commit.txt

(
  cd handoff
  sha256sum app.jar pom.xml source-commit.txt > SHA256SUMS
  sha256sum -c SHA256SUMS
)
```

Nếu đang thử bằng project mới tạo chưa `git init`/commit, `git rev-parse HEAD` sẽ fail. Hãy tạo một Git repository sandbox của chính bạn và commit các files trước; **đừng bịa SHA**.

### Trên macOS

Nếu máy không có `sha256sum`, dùng `shasum -a 256`:

```bash
(
  cd handoff
  shasum -a 256 app.jar pom.xml source-commit.txt > SHA256SUMS
  shasum -a 256 -c SHA256SUMS
)
```

### Trên Windows PowerShell

```powershell
New-Item -ItemType Directory -Path handoff -Force | Out-Null
Copy-Item target\build-once-demo-1.0.0.jar handoff\app.jar
Copy-Item pom.xml handoff\pom.xml

Get-FileHash -Algorithm SHA256 handoff\app.jar
Get-FileHash -Algorithm SHA256 handoff\pom.xml
```

Đoạn PowerShell đo hash, **không tạo `SHA256SUMS` dạng GNU**. Để chạy một workflow đa nền tảng, dùng cùng định dạng do script/tool chung quy định.

### POM cũng cần được kiểm tra

Đối với thư viện Maven, consumer tải POM để đọc dependencies, transitive dependencies và metadata. Nếu JAR đúng nhưng POM sai, bản phát hành vẫn có thể hỏng.

**Lưu ý với CI-friendly versions:** nếu POM dùng `${revision}`/`${changelist}` hoặc Flatten Maven Plugin, POM publish có thể là **consumer POM đã được resolve/flatten**, không phải source `pom.xml`. Project demo dùng `1.0.0` tĩnh nên copy source POM phù hợp. Dự án thật cần thu/handover đúng POM mà build sẽ phát hành.

## 8. Ba cấp độ kiểm tra integrity và provenance

### Cấp 1: file checksums

```bash
(
  cd handoff
  sha256sum -c SHA256SUMS
)
```

Lệnh này fail nếu bytes của file nào không khớp checksum đã ghi.

### Cấp 2: origin của artifact bundle

Handoff phải đến từ **đúng build job và CI run đã được chấp thuận**, không phải một artifact bất kỳ được upload cùng tên. Cần kiểm:

- CI run ID, build job ID và source commit.
- Protected branch/tag rules.
- Người/hệ thống có quyền upload/đổi artifact.
- Artifact object ID và digest ở cấp CI storage.
- Build workflow revision và toolchain configuration.
- Artifact signing/attestation khi policy yêu cầu.

### Cấp 3: bytes ở repository và runtime

Sau khi publish:

- Đọc artifact từ repository đích và đo SHA-256.
- Đối chiếu với JAR đã lưu ở handoff.
- Xác nhận Maven GAV và consumer POM đúng.
- Tại runtime, ghi nhận artifact digest/image digest, config version và deployment record.

**Một checksum bằng nhau cho hai files cụ thể là bằng chứng byte identity**, nhưng không đồng nghĩa mọi người dùng đã tải đúng URL/cache hoặc mọi dữ liệu runtime đều hợp lệ.

## 9. CI artifact archive không phải JAR digest

GitHub Actions `upload-artifact`/`download-artifact` truyền files giữa jobs. Artifact service có thể đóng các files thành một ZIP archive.

Do đó:

```text
JAR SHA-256           = digest của app.jar
POM SHA-256           = digest của pom.xml
CI artifact digest    = digest của archive chứa nhiều files
Git commit SHA        = ID của source commit
```

Các giá trị này **có thể đều là hex hash** nhưng đo **những đối tượng khác nhau**.

Từ `upload-artifact` v4, GitHub mô tả artifacts là immutable objects. GitHub cũng bổ sung digest SHA-256 khi upload/download. Theo thông báo ngày 18/03/2025, khi phát hiện artifact digest mismatch, hệ thống có thể **cảnh báo mà không tự fail workflow** ở một số phiên bản. Vì vậy job publisher cần một kiểm tra `SHA256SUMS` riêng theo chính sách **fail-closed**.

**Ghi chú:** Handoff checksum không phải chữ ký tin cậy nếu attacker có thể thay cả file và checksum. Kết hợp với protected tag, run identity, permission boundaries, signatures/provenance và environment approval.

## 10. Publish đúng bytes bằng Maven Deploy Plugin

Apache Maven Deploy Plugin hỗ trợ goal:

```text
org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file
```

Goal `deploy-file` dùng file hiện hữu làm đầu vào, có các tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| `-Dfile` | JAR artifact **đã tạo** |
| `-DpomFile` | POM đã chọn để publish |
| `-DrepositoryId` | Server ID ánh xạ với `settings.xml` |
| `-Durl` | Maven repository destination |
| `-DgroupId`/`-DartifactId`/`-Dversion` | Có thể suy từ `pomFile` nếu POM phù hợp |
| `-Dfiles`, `-Dclassifiers`, `-Dtypes` | Side artifacts khi cần, phải khớp số lượng/loại |

**Điểm then chốt:** `deploy-file` không chạy lại default lifecycle `compile/test/package`. Nó upload **file đã có**. Trái lại, `mvn deploy` có thể build lại trước khi deploy.

### Thử ở local file repository (không cần credentials thật)

Trên Linux/macOS có quyền ghi `/tmp` và một thư mục demo riêng:

```bash
(
  cd handoff
  sha256sum -c SHA256SUMS
)

mvn -B -ntp \
  org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file \
  -Dfile=handoff/app.jar \
  -DpomFile=handoff/pom.xml \
  -DrepositoryId=local-demo \
  -Durl=file:///tmp/build-once-demo-repository
```

Kỳ vọng layout Maven repository:

```text
/tmp/build-once-demo-repository/
└── dev/lesson/build-once-demo/
    ├── maven-metadata.xml
    └── 1.0.0/
        ├── build-once-demo-1.0.0.jar
        ├── build-once-demo-1.0.0.pom
        └── ...checksums/metadata (tùy plugin/repository)
```

Đường dẫn trên chỉ minh họa. **Không chạy đè lên một repository local đã chứa dữ liệu có giá trị hoặc một release trùng version**.

Kiểm tra:

```bash
sha256sum handoff/app.jar
sha256sum /tmp/build-once-demo-repository/dev/lesson/build-once-demo/1.0.0/build-once-demo-1.0.0.jar
```

**Hai hash phải trùng.** Nếu không, chưa thể tuyên bố đúng artifact đã được publish. Không bịa một hash cố định khi chưa thực sự đo bytes.

Với repository thật, thay `file:///tmp` bằng approved release repo URL và cấu hình credentials qua `settings.xml`/CI secret store, không nhúng password vào POM hoặc CLI URL.

### Tại sao không dùng cách này cho mọi multi-module reactor?

`deploy-file` phục vụ file cụ thể và optional side artifacts. Với reactor có nhiều modules, sources/Javadoc JARs, attached classifiers, GPG signatures, SBOM, staging repository metadata và lifecycle customizations, một lệnh upload **một JAR** là không đủ. Nên dùng repository-native promotion hoặc một publisher quản lý **toàn bộ artifact set đã được build và QA**.

## 11. Workflow GitHub Actions: build job không có quyền publish

Mẫu workflow sau minh họa **một release version `1.0.0`**. Khi release version khác, phải thay tag filter/POM/expected filename có kiểm soát. Không mặc định dùng tag `v*` bất kỳ với POM vẫn là `1.0.0`.

- Job **`build`** checkout tag và chạy **một lần** `mvn clean verify`; tập hợp handoff và kiểm checksum.
- Job **`publish`** chỉ chạy sau `build`, dưới GitHub Environment `maven-releases`; **không checkout lại source và không build lại JAR**.
- Job publisher nhận repository credentials **riêng**, không đưa secrets vào build job.
- Cả hai job cùng một workflow run; publisher download đúng tên candidate của build job này.

### `.github/workflows/release.yml`

```yaml
name: Maven Build Once Demo

on:
  push:
    tags:
      - 'v1.0.0'

permissions:
  contents: read

concurrency:
  group: maven-release-${{ github.ref }}
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Checkout approved release tag
        uses: actions/checkout@v7
        with:
          persist-credentials: false

      - name: Java 17 for build
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - name: Build and test once
        run: mvn -B -ntp clean verify

      - name: Assemble immutable candidate
        shell: bash
        run: |
          set -euo pipefail
          test "$GITHUB_REF_NAME" = "v1.0.0"
          test -f target/build-once-demo-1.0.0.jar
          mkdir -p handoff
          cp target/build-once-demo-1.0.0.jar handoff/app.jar
          cp pom.xml handoff/pom.xml
          printf '%s\n' "$GITHUB_SHA" > handoff/source-commit.txt
          (
            cd handoff
            sha256sum app.jar pom.xml source-commit.txt > SHA256SUMS
            sha256sum -c SHA256SUMS
          )

      - name: Smoke test candidate
        shell: bash
        run: |
          set -euo pipefail
          test "$(java -jar handoff/app.jar)" = "HANDOFF_RESULT=5"

      - name: Save exact handoff
        uses: actions/upload-artifact@v4
        with:
          name: build-once-demo-1.0.0
          path: handoff/
          if-no-files-found: error
          retention-days: 14

  publish:
    needs: build
    runs-on: ubuntu-latest
    timeout-minutes: 15
    environment: maven-releases
    steps:
      - name: Java 17 and Maven settings
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          server-id: releases
          server-username-env-var: MAVEN_REPO_USERNAME
          server-password-env-var: MAVEN_REPO_TOKEN

      - name: Get the same candidate
        uses: actions/download-artifact@v4
        with:
          name: build-once-demo-1.0.0
          path: handoff

      - name: Verify exact files and source
        shell: bash
        run: |
          set -euo pipefail
          test -f handoff/app.jar
          test -f handoff/pom.xml
          (
            cd handoff
            sha256sum -c SHA256SUMS
          )
          test "$(cat handoff/source-commit.txt)" = "$GITHUB_SHA"

      - name: Publish existing JAR and POM without rebuilding
        shell: bash
        env:
          RELEASE_REPOSITORY_URL: ${{ vars.MAVEN_RELEASE_REPOSITORY_URL }}
          MAVEN_REPO_USERNAME: ${{ secrets.MAVEN_REPO_USERNAME }}
          MAVEN_REPO_TOKEN: ${{ secrets.MAVEN_REPO_TOKEN }}
        run: |
          set -euo pipefail
          test -n "$RELEASE_REPOSITORY_URL"
          test -n "$MAVEN_REPO_USERNAME"
          test -n "$MAVEN_REPO_TOKEN"
          mvn -B -ntp \
            org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file \
            -Dfile=handoff/app.jar \
            -DpomFile=handoff/pom.xml \
            -DrepositoryId=releases \
            "-Durl=$RELEASE_REPOSITORY_URL"
```

### Điều kiện bắt buộc trước khi dùng workflow

1. Tạo **GitHub Environment** `maven-releases`; cấu hình **required reviewers/protection rules**. Chỉ ghi `environment: maven-releases` trong YAML **không tự bật chế độ phê duyệt** nếu repository settings chưa có rule.
2. Khai repository/environment **variable** `MAVEN_RELEASE_REPOSITORY_URL` là URL repository release thực và được phép publish.
3. Khai đúng **secrets** `MAVEN_REPO_USERNAME` và `MAVEN_REPO_TOKEN` cho publisher environment.
4. Bật tag protection/release branch rules và bảo đảm source tag đã được review.
5. Tại publisher, `setup-java@v6` tạo `settings.xml` dùng **tên environment variables** `MAVEN_REPO_USERNAME`/`MAVEN_REPO_TOKEN`, không hardcode plaintext token vào POM.
6. Chọn release repository **immutable**, chặn overwrite cùng `dev.lesson:build-once-demo:1.0.0`.
7. Workflow ví dụ chạy trên GitHub-hosted Linux runner có Maven cài sẵn. Nếu dùng self-hosted runner, phải provision Maven/JDK và action runtime tương thích.
8. Trong tổ chức yêu cầu supply-chain hardening, nên **pin GitHub Actions theo full commit SHA** đã kiểm tra; major tags `@v7`/`@v6`/`@v4` chỉ làm ví dụ dễ đọc.
9. Mẫu chỉ publish một JAR và một POM tĩnh. Multi-module/artifact set đầy đủ cần workflow tương ứng.
10. Không chạy repo upload khi thiếu quyền/phê duyệt; các secrets/URL ngoài environment không được suy đoán.

### Điều gì bảo đảm không build lại?

Trong `build` chỉ có **một** lệnh Maven chạy default lifecycle tới `verify`. `publish` không có bước `actions/checkout` và không gọi `mvn package`/`mvn verify`/`mvn deploy`. Nó chỉ download handoff, xác minh checksum rồi gọi **pinned deploy-file goal**.

Plugin `deploy-file` có thể được Maven tải/khởi chạy ở publish job, nhưng nó **không chạy compile/package của project**. Maven repository vẫn có thể tạo/cập nhật metadata của repository, điều đó không có nghĩa JAR đã build lại.

**Trust boundary:** publisher có secrets nhưng không chạy `java -jar handoff/app.jar`. Smoke test ứng dụng đã chạy ở job build ít đặc quyền. Với code PR/chưa được review, job build cũng phải chạy trong sandbox phù hợp; không cấp publisher token cho các PR workflows.

### Hạn chế của ví dụ này

Checksum được gửi **cùng** bundle; nếu bundle origin không tin cậy hoặc cả JAR và SHA256SUMS bị thay thì checksum check không đủ xác thực. Phải kiểm source/CI run provenance, tag protection, environment approval và attestation nếu policy cần.

Job publisher cũng cần kiểm tra **GAV trong POM đã khớp tag** và policy repository; workflow demo hardcode `v1.0.0`/`1.0.0` nên dễ quan sát, nhưng không có quy tắc tự động đa phiên bản.

## 12. Repository promotion khác runtime deployment

Một hệ thống production có thể gồm ba workflow riêng:

```text
(A) CI BUILD:
source -> mvn clean verify -> app.jar/POM -> SHA-256

(B) MAVEN PUBLISH/PROMOTE:
candidate -> staging repository -> approve -> release repository

(C) RUNTIME DEPLOY:
read exact released GAV/digest -> stage env -> production env
```

**`mvn deploy` của Maven** nói về upload Maven artifact vào repository, không tự triển khai ứng dụng vào Kubernetes, VM hay một ứng dụng đang chạy.

Khi dùng repository manager như Nexus/Artifactory:

- Có thể upload candidate vào staging repository, kiểm tra và phê duyệt.
- Sau đó **promote/copy/move** các object và metadata phù hợp lên release repository mà không tạo lại JAR.
- API và tên thao tác khác nhau theo sản phẩm, phiên bản và edition; **không có một lệnh Maven CLI duy nhất chung cho mọi repository manager**.
- Bảo đảm promotion chuyển đủ POM/JAR/side artifacts; không chọn thiếu classifiers/chữ ký.
- Sau khi promotion, đọc lại JAR và so digest với candidate.

Khi runtime deployment cần chọn version, ưu tiên **immutable GAV/object version** hoặc image digest. Không tải một mutable alias “latest” rồi cho rằng chắc chắn là release đã được QA.

## 13. Build một lần, cấu hình khác nhau khi chạy

Một codebase thường có:

- Staging database URL khác production.
- API endpoint, feature flags, timezone, locale và authentication config khác.
- Secrets chỉ có ở environment, không có trong source artifact.
- JDK runtime hoặc hạ tầng khác cần test compatibility.

Cách làm **không hợp với build-once**:

```bash
# Phản ví dụ — mỗi môi trường tạo một JAR khác.
mvn package -Pstaging
mvn package -Pproduction
```

Nếu Maven profiles làm resource filtering hay chọn code/config khác, đây là **hai artifacts**. Hãy dùng runtime configuration ở bên ngoài JAR: environment variables, ConfigMap/Secrets, file config từ deployment platform hoặc secret manager.

```text
Cùng SHA-256(app.jar)
  + staging config revision S
  -> staging runtime
  + production config revision P
  -> production runtime
```

Hai môi trường **được phép có cấu hình khác**, nhưng phải lưu lại **binary digest + config revision** trong deployment record để debug. Binary giống nhau không đồng nghĩa hành vi giống nhau với mọi dữ liệu/DB version.

## 14. Artifact set: JAR không phải lúc nào cũng đủ

Với một library release, ngoài main JAR/POM còn có thể cần:

```text
build-once-demo-1.0.0.jar
build-once-demo-1.0.0.pom
build-once-demo-1.0.0-sources.jar
build-once-demo-1.0.0-javadoc.jar
build-once-demo-1.0.0.jar.asc
build-once-demo-1.0.0.pom.asc
build-once-demo-1.0.0-sources.jar.asc
build-once-demo-1.0.0-javadoc.jar.asc
SBOM / provenance / checksums, theo chính sách
```

Demo POM **không tạo** sources/Javadocs/signatures, nên danh sách trên là ví dụ về một release thực tế phức tạp hơn.

### Đừng tạo lại Javadocs/sources ở publisher

Nếu release yêu cầu sources/Javadocs, tạo chúng trong **build job**, kiểm tra, hash, rồi chuyển cùng candidate. Nếu publisher chạy Javadoc plugin lần khác, generated docs có thể khác bytes do JDK/plugin/time.

### Consumer POM khác source POM

Với CI-friendly version placeholders `${revision}`, `${sha1}`, `${changelist}` và Flatten Maven Plugin, **consumer POM** publish có thể là file đã được flatten/resolve. Nếu publisher lấy source POM chưa xử lý, consumer Maven có thể không resolve đúng dependency graph. Handoff cần lấy đúng **publishable POM do build tạo** và xác minh metadata đó.

### Signatures và attestation

Chữ ký/attestation là các **artifact bằng chứng gắn với digest**, không phải lý do để thay bytes của JAR đã QA. Có thể tạo chữ ký sau approval bằng key được bảo vệ, nhưng điều đó tạo **file ký mới**, phải log/audit và kiểm với đúng hash. Không cấp signing key trong job build PR chưa tin cậy.

## 15. Immutable release và SNAPSHOT khác nhau

Một cách đặt policy:

```text
dev.lesson:build-once-demo:1.0.0 -> immutable JAR A
dev.lesson:build-once-demo:1.0.1 -> immutable JAR B (bản sửa)
```

Khi `1.0.0` đã được consumer cache, **không overwrite `1.0.0` bằng bytes khác**. Nếu có lỗi, hãy phát hành `1.0.1` hoặc một version mới theo policy.

### SNAPSHOT không phải immutable release identity

`1.0.1-SNAPSHOT` có thể liên tục có nội dung mới, repository metadata/timestamped snapshot thay đổi. Việc staging tải “SNAPSHOT mới nhất” còn production tải một ngày sau **có thể nhận file khác**.

Nếu cần thử snapshot candidate, lưu **timestamped object/digest cụ thể**, hoặc chuyển sang unique immutable release version trước khi phê duyệt. Không dùng `latest`/version ranges để xác định bytes tại production.

### Tại sao artifact retention quan trọng?

CI artifact upload thường có retention giới hạn. Một bản release cần khả năng audit/rollback lâu dài hơn phải được giữ trong **immutable artifact repository/storage** theo retention policy, không chỉ ở archive tạm của workflow.

## 16. Xác minh ở đích cuối: không dừng tại “upload success”

Sau khi publish:

1. Query đúng repository/version/path.
2. Download **JAR thực tế** từ repository bằng phương pháp được phép.
3. So SHA-256 download với artifact record đã phê duyệt.
4. Xem POM publish có đúng GAV/dependency metadata.
5. Nếu có attached files/signatures/SBOM, xác minh đủ số lượng và signatures.
6. Chạy consumer integration test hoặc smoke test trên JAR tải từ **repository**, với quyền thấp.
7. Ghi repository object digest, build run, commit/tag và approver.
8. Khi production deploy, ghi đúng artifact digest đang thực sự được runner/container runtime sử dụng.

**Lưu ý:** repository manager có thể tạo metadata/checksum side files bổ sung. Việc `maven-metadata.xml` thay đổi không tự đồng nghĩa **JAR bytes bị sửa**. Phạm vi cần giữ bất biến phải được quy định rõ.

## 17. Rollback: dùng artifact cũ, không rebuild source cũ

Giả sử production dùng `1.0.0` và xảy ra incident. Rollback có thể:

- Xem deployment manifest để biết artifact digest hiện tại.
- Chọn một release cũ đã được kiểm chứng, ví dụ `0.9.9`.
- Kiểm tra database/schema/config compatibility.
- Deploy **chính artifact đã lưu** của `0.9.9`.
- Xác minh health và ghi rollback audit record.

Không nên `git checkout v0.9.9 && mvn package` để “tạo lại” một JAR cũ rồi dùng ngay cho rollback. Dù reproducible build là mục tiêu tốt, không thể mặc định builder/dependency cache/toolchain ngày hôm nay tạo cùng bytes với bản `0.9.9` đã QA.

**Ngoại lệ quan trọng:** rollback binary có thể không rollback được schema/data migrations. Nếu schema không backward-compatible, có thể cần forward fix hoặc quy trình database riêng.

## 18. Tình huống sai thường gặp và cách sửa

| Triệu chứng | Gốc vấn đề | Cách xử lý |
| --- | --- | --- |
| Staging xanh, prod sai nhưng cùng version | Prod rebuild hoặc resolve object khác | Pin/digest artifact, không rebuild |
| `mvn deploy` ở publisher tạo hash khác | Default lifecycle chạy lại | Repository promotion hoặc `deploy-file` |
| `-DskipTests` vẫn tạo JAR mới | Skip tests không ngăn package | Loại bỏ lifecycle build ở publisher |
| Git SHA giống nhưng artifact SHA khác | JDK/plugin/time/dependency khác | Khóa toolchain, audit reproducibility |
| Artifact download nhầm run | Chỉ tra artifact theo tên, không theo run ID | Download từ đúng run/job, kiểm commit/digest |
| CI artifact digest không khớp JAR digest | Một cái hash ZIP, cái kia hash JAR | Đo đúng từng object |
| POM publish chứa `${revision}` | Copy source POM chưa flatten | Chọn đúng consumer POM |
| JAR đúng nhưng thiếu sources/Javadocs | Handoff chỉ có một file | Chuyển toàn bộ release artifact set |
| `401/403` khi upload | Repo ID, token, ACL sai | Khớp `repositoryId` với `settings.xml` và quyền server |
| Registry từ chối redeploy 1.0.0 | Immutability policy hoạt động | Tạo version mới, không tắt policy |
| Smoke test pass nhưng stage/prod khác | Runtime config/environment khác | Theo dõi config, integration tests |
| SNAPSHOT tự thay giữa stages | Mutable metadata/version | Pin timestamped object/digest |
| Release không thể rollback | Artifacts cũ đã bị xóa | Sửa retention/immutable storage |
| Checksum pass dù candidate bị thay | JAR và checksum cùng nguồn không tin cậy | Signature/provenance, protected workflow/run |
| Publisher chạy JAR với secrets | Trust boundary sai | Test ở job low-privilege, publisher chỉ chuyển file |
| GAV JAR và POM lệch nhau | Handoff từ nhiều builds | Hash cả JAR/POM, validate metadata/tag |
| Maven artifact publish nhưng app chưa chạy | `deploy` nghĩa repository, không runtime | Thêm runtime deployment job theo digest |
| Build quality reports khác release | Reports từ một run, artifact từ run khác | Bind reports/approval với đúng immutable candidate |

### Cách debug thứ tự thực thi

Đọc CI logs và tìm mọi lệnh `mvn package`, `mvn verify`, `mvn install`, `mvn deploy` hoặc plugin repackager chạy **sau** candidate. Nếu có, xác định chúng đang làm gì và đã tạo file mới hay chưa.

Kiểm container image pipeline: một Dockerfile có `RUN mvn package` ở bước staging sẽ build lại Java artifact, dù trước đó CI đã upload một JAR được QA. Mô hình đúng là **COPY JAR đã được kiểm chứng vào image** (và nếu tạo image ở bước này, sau đó pin/deploy đúng image digest), hoặc build image một lần rồi promote image digest.

## 19. Bài thực hành tại chỗ: local Maven repository

Đứng trong project đã tạo:

```bash
mvn -B -ntp clean verify

mkdir -p handoff
cp target/build-once-demo-1.0.0.jar handoff/app.jar
cp pom.xml handoff/pom.xml

(
  cd handoff
  sha256sum app.jar pom.xml > SHA256SUMS
  sha256sum -c SHA256SUMS
)

java -jar handoff/app.jar

mvn -B -ntp \
  org.apache.maven.plugins:maven-deploy-plugin:3.2.0:deploy-file \
  -Dfile=handoff/app.jar \
  -DpomFile=handoff/pom.xml \
  -DrepositoryId=local-demo \
  -Durl=file:///tmp/build-once-demo-repository

sha256sum handoff/app.jar
sha256sum /tmp/build-once-demo-repository/dev/lesson/build-once-demo/1.0.0/build-once-demo-1.0.0.jar
```

**Lưu ý:** ví dụ dùng path local Linux/macOS được phép ghi, không xóa hay overwrite repository ngoài phạm vi thực hành. Không có tác vụ network publish trừ khi bạn thay URL. Nếu Maven chưa cache Deploy Plugin, invocation goal có thể cần tải plugin; nhưng JAR ứng dụng **không được compile/package lại**.

Bạn cần thấy:

- Stdout `HANDOFF_RESULT=5`.
- SHA-256 của `handoff/app.jar` **bằng** SHA-256 JAR được lưu ở local repo.
- POM đi kèm có tọa độ đúng.
- Không có Maven compile/package run thứ hai sau handoff.

**Bài học trọng tâm là identity của byte**, không phải việc chứng minh một ứng dụng nghiệp vụ đã sẵn sàng production.

## 20. Câu hỏi tự kiểm tra

**Câu 1:** `mvn clean verify` ở job test rồi `mvn deploy` ở publisher có phải build-once không?

**Đáp án:** Không tự động. `deploy` là default lifecycle phase và có thể compile/package lại. Dùng repository promotion hoặc deploy-file trên bytes đã tạo.

**Câu 2:** Hai files có tên `app-1.0.0.jar` có chắc trùng byte không?

**Đáp án:** Không. Cần so hash/digest từ file thực.

**Câu 3:** Git commit SHA có thể thay cho JAR SHA-256 không?

**Đáp án:** Không. Một cái xác định source, cái kia xác định artifact bytes.

**Câu 4:** Vì sao không chỉ upload JAR mà còn POM?

**Đáp án:** Consumer Maven cần POM để resolve dependency metadata đúng.

**Câu 5:** Dấu `:` trong `deploy:deploy-file` quan trọng gì?

**Đáp án:** Nó gọi goal upload file đã có. `mvn deploy` là phase và có thể tạo lại output.

**Câu 6:** GitHub Actions artifact digest có bằng SHA-256 của JAR không?

**Đáp án:** Không mặc định; CI có thể hash archive ZIP chứa JAR và các files khác.

**Câu 7:** Vì sao không nên chạy `java -jar` ở publisher có secrets?

**Đáp án:** Binary chưa tin cậy có thể thực thi mã có quyền của job. Nên smoke test ở job isolated/low-privilege trước approval.

**Câu 8:** Dùng cùng JAR ở staging/prod có bảo đảm hành vi giống tuyệt đối?

**Đáp án:** Không. Runtime config, database, JDK và các services có thể khác nhau.

**Câu 9:** Khi thiếu artifact sources/Javadocs/signatures, có thể chạy goal generate lại ở publish job không?

**Đáp án:** Không lý tưởng. Cần tạo những files đó trong build candidate, QA và chuyển chúng đầy đủ.

**Câu 10:** Vì sao không overwrite version `1.0.0` đã phát hành?

**Đáp án:** Consumer caches/replicas có thể lưu bytes cũ và mới dưới cùng GAV, phá tính nhất quán/traceability.

**Câu 11:** Một bundle có SHA256SUMS pass đã chứng minh ai tạo JAR chưa?

**Đáp án:** Chưa. Cần provenance/trusted CI identity/signature và approved source.

**Câu 12:** Rollback nên làm gì với artifact cũ?

**Đáp án:** Deploy lại đúng immutable artifact đã lưu và kiểm digest/config compatibility; tránh build lại tag cũ nếu không có lý do và kiểm chứng.

## 21. Checklist triển khai build-once trong IDE và CI

- [ ] Xác định đúng Git commit/tag, GAV/version và source đã review.
- [ ] Chỉ một build job chịu trách nhiệm compile/test/package release candidate.
- [ ] Maven/JDK/plugin/dependency inputs được kiểm soát và ghi vào build record.
- [ ] Unit/IT/security quality gates thực sự chạy trước khi approve.
- [ ] Candidate JAR/POM/attachments có checksum từng file.
- [ ] Handoff lưu source commit, CI run/job và provenance references.
- [ ] Không đưa tokens/settings/passwords/private keys vào handoff bundle.
- [ ] Phân biệt Git SHA, JAR SHA-256, CI archive digest.
- [ ] Bước nhận file fail-closed nếu checksum/commit mismatch.
- [ ] Quyền upload artifact được giới hạn ở đúng CI workflow/run.
- [ ] Bước phát hành có environment approvals và credentials riêng.
- [ ] Job publish không chạy `mvn package`, `mvn verify` hoặc `mvn deploy` tạo lại file.
- [ ] Nếu dùng Maven Deploy Plugin, gọi pinned `deploy:deploy-file` với file/POM đã tồn tại.
- [ ] Với multi-module/attached artifacts, promote **toàn bộ release set**.
- [ ] Consumer POM được flatten/resolve nếu project dùng CI-friendly versioning.
- [ ] Repository cấm overwrite immutable release GAV.
- [ ] SNAPSHOT/aliases không được dùng như release identity bất biến.
- [ ] Staging và production dùng đúng artifact digest đã approve.
- [ ] Runtime config và secret management không thay bytes JAR.
- [ ] Có so checksum ở registry/download/deployment endpoint khi cần.
- [ ] Lưu artifact/version lâu đủ để rollback và audit.
- [ ] Signatures/SBOM/provenance liên kết đúng digest.
- [ ] Không cho code PR chưa review chạy trong publisher có secrets.
- [ ] Có record đầy đủ: SHA, artifact, config, approver, môi trường và thời điểm.

**Kết luận:** Trong Maven, “build một lần” là một quyết định **kiến trúc CI/CD**: tạo và kiểm thử **một bộ artifact xác định**, giữ nó bất biến, rồi chuyển **chính bộ byte đó** qua mọi cổng phát hành. `mvn deploy` là default lifecycle phase có thể chạy lại packaging; `deploy:deploy-file`/repository-native promotion cho phép sử dụng artifact đã tạo. GAV và Git tag giúp quản lý danh tính, còn SHA-256, provenance, approval và repository immutability giúp chứng minh **đúng file đã QA** đến được môi trường cuối.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven Deploy Plugin — Introduction](https://maven.apache.org/plugins/maven-deploy-plugin/)
- [Apache Maven Deploy Plugin 3.2.0 — deploy:deploy-file](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-file-mojo.html)
- [Apache Maven Deploy Plugin — Usage](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html)
- [Apache Maven — Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [GitHub Docs — Store and Share Workflow Artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- [GitHub Actions — Artifact v4 Immutability](https://github.blog/changelog/2024-02-12-github-actions-artifacts-v4-is-now-generally-available/)
- [GitHub Actions — Artifact Digest Verification](https://github.blog/changelog/2025-03-18-github-actions-now-supports-a-digest-for-validating-your-artifacts-at-runtime/)
- [GitHub Actions — setup-java](https://github.com/actions/setup-java)
- [GitHub Actions — checkout](https://github.com/actions/checkout)
- [GitHub Docs — Environments and Deployment Protection Rules](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)

*Các ví dụ sử dụng Java 17, Maven Compiler Plugin 3.13.0, Surefire 3.5.2, JAR Plugin 3.4.2, Deploy Plugin 3.2.0 và JUnit Jupiter 5.11.4. Workflow minh họa release một version cố định `v1.0.0`. Các lệnh chỉ xuất bản remote khi bạn tự cấu hình đúng repository URL, GitHub Environment và credentials đã được cấp quyền; nội dung bài không tuyên bố một release thật đã được chạy.*
