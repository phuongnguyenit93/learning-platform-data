# Build lại từ bản checkout sạch và môi trường độc lập với Maven

## 1. Mục tiêu: build lại được, không phụ thuộc “máy của tác giả”

Khi một dự án Java chạy `mvn clean verify` thành công trên máy của lập trình viên, ta mới chứng minh rằng **working tree, toolchain, cache, Maven settings và các điều kiện hiện tại** cho phép build. Một bản build đáng tin cậy hơn phải có thể bắt đầu từ **Git commit đã chốt** và một môi trường mới, rồi tạo được artifact đạt cùng tiêu chí chất lượng. Đối với yêu cầu **reproducible build** nghiêm ngặt, artifact phải còn **giống nhau từng byte** khi đầu vào và các điều kiện được kiểm soát như nhau.

Đề bài này tập trung vào hai hành động có quan hệ nhưng khác nhau:

1. **Clean checkout:** lấy lại source từ Git commit, không mượn file chưa commit, thư mục `target`, output build hay configuration tự phát trên máy làm việc.
2. **Independent environment:** không phụ thuộc một Maven cache, user settings, plugin version, JDK hoặc tài nguyên cục bộ tình cờ đã tồn tại. Dùng Maven Wrapper, JDK theo policy, repository/cache tách biệt và cùng hướng dẫn build.

Kết quả thực hành: một dự án Maven Java 17 chạy được, ba unit tests JUnit 5, output JAR bình thường, hai lần build từ **hai Git clones khác nhau**, hai local repositories và Maven Wrapper cùng version; cuối cùng đối chiếu SHA-256 và byte JAR. Một ví dụ mở rộng cho CI bằng hai container/VM riêng được giải thích để tránh hiểu nhầm “hai thư mục trên cùng máy” đã là xác minh độc lập hoàn toàn.

**Nguyên tắc:** `BUILD SUCCESS` là điều kiện cần nhưng **không phải** bằng chứng đủ cho một artifact có thể được tái tạo từ checkout sạch và càng không tự bảo đảm byte-for-byte reproducibility.

## 2. Phân biệt các cấp độ “tái lập”

| Cấp độ | Điều gì được giữ giống? | Bằng chứng |
| --- | --- | --- |
| **Buildable** | Source hiện tại có thể build | Maven exit code thành công |
| **Clean-checkout buildable** | Một Git commit, không dùng file chưa commit | Build từ checkout mới và kiểm test/artifact |
| **Environment-independent** | Điều kiện build được công bố và tái tạo trên môi trường mới | Chạy ở máy/container/VM khác, dùng toolchain được kiểm soát |
| **Functionally equivalent** | Cùng API/behavior dưới các tests đã chọn | Unit/integration/consumer tests, smoke tests |
| **Byte-for-byte reproducible** | Cùng source, build instructions và những đầu vào được kiểm soát | Artifact bytes/SHA-256 giống nhau |
| **Verifiable published artifact** | Binary đã publish khớp binary tự rebuild | So hash với artifact được lấy từ repository phát hành |

Ví dụ hai JAR chạy giống nhau nhưng khác timestamps của ZIP entries có thể vượt qua unit tests mà **hash khác**. Ngược lại, hai JAR giống byte không chứng minh business logic đúng nếu bộ tests bỏ sót hành vi quan trọng.

Reproducibility cần xác định **đúng artifact đang so sánh**. So `target/rebuild-check-1.0.0.jar` với cùng GAV ở lần rebuild thứ hai có ý nghĩa; so một JAR thường với một shaded JAR hay một file source JAR khác classifier thì không.

## 3. Vì sao mvn clean không đồng nghĩa “sạch”?

Phase `clean` xóa output theo Maven Clean Plugin, thông thường là `target/`, nhưng **không** tự dọn các nguồn ảnh hưởng khác:

- File source đã sửa nhưng chưa commit, `git status` không sạch.
- File untracked được script lén đọc từ workspace.
- `~/.m2/repository` có dependency SNAPSHOT, plugin hoặc artifact cũ.
- `~/.m2/settings.xml`, global Maven settings hay corporate mirrors khác nhau.
- `.mvn/maven.config`, `.mvn/jvm.config`, `.mvn/extensions.xml` có cấu hình không được review.
- Biến môi trường `JAVA_HOME`, `MAVEN_OPTS`, `JAVA_TOOL_OPTIONS`, `TZ`, `LANG`, `LC_ALL`.
- Maven chạy từ bản cài trong `PATH` khác với CI.
- JDK khác major/patch/vendor, hệ điều hành khác, line endings khác.
- Timestamp hiện tại, timezone, file order, random seed, hostname, username, absolute paths.
- Repository online cung cấp cùng tọa độ SNAPSHOT nhưng bytes đã thay.
- Script dùng network, filesystem, database, git metadata hoặc secrets mà không ghi lại input.

Vì vậy **checkout sạch** là lấy lại source từ Git commit; **Maven cache sạch** là local repository mới; còn **môi trường độc lập** bao gồm cả toolchain và các yếu tố bên ngoài. Đây là ba loại “sạch” khác nhau.

### 3.1. Kiểm trạng thái Git trước khi đóng băng đầu vào

Trong repository nguồn:

```bash
git rev-parse HEAD
git status --porcelain
git ls-files
```

`git rev-parse HEAD` cho commit ID; `git status --porcelain` **không in gì khi working tree sạch** (với điều kiện không có thay đổi được Git theo dõi/hiển thị). `git ls-files` cho biết các file mà Git đang quản lý.

Nếu chỉ có `pom.xml` trong Git nhưng thiếu `src/main/resources`, `.mvn/wrapper` hoặc scripts, clean checkout sẽ không build giống máy tác giả. Hãy commit các file cấu thành đầu vào thực tế; không commit `target/` và cache Maven.

**Lưu ý:** `.gitignore` có thể che file không được Git theo dõi. Một file bị ignore nhưng build dùng nó vẫn là dependency ẩn. Kiểm quy trình packaging, resources và scripts để chắc chắn tất cả input bắt buộc được quản lý hoặc cấp có chủ đích.

## 4. Kiểm soát đầu vào build theo lớp

| Lớp | Cần pin/ghi nhận | Ví dụ |
| --- | --- | --- |
| Source | Commit SHA, submodules, Git LFS | `git rev-parse HEAD` |
| Maven runtime | Maven Wrapper distribution | `.mvn/wrapper/maven-wrapper.properties` |
| JDK | Major/version/vendor/toolchain | `java -version`, `JAVA_HOME` |
| POM build | Compiler/Surefire/JAR/Resources versions | `pom.xml` |
| Dependencies | Fixed versions, trusted repositories | JUnit 5.10.2, BOM version |
| Plugins | Fixed versions và plugin dependencies | Compiler 3.13.0, JAR 3.4.2 |
| Build environment | OS/locale/timezone/env vars | container image digest hoặc build record |
| Output metadata | Stable timestamps/order/encoding | `project.build.outputTimestamp` |
| Repository state | Local cache path, settings, mirrors | `-Dmaven.repo.local=...`, `-s ...` |
| Tests | Test discovery, runtime/test data | Surefire XML và exit code |
| Published artifact | Binary bytes/checksum/provenance | SHA-256 của JAR đã phát hành |

**Đừng hardcode credentials vào POM/README.** Khi cần access private repository, lấy thông tin nhạy cảm qua CI secret management; ghi nhận **repository IDs/policies** nhưng không phát tán token.

## 5. Maven Wrapper để chốt Maven version

Maven Wrapper cung cấp `mvnw`, `mvnw.cmd` và `.mvn/wrapper/maven-wrapper.properties` để project gọi đúng Maven distribution thay vì dùng lệnh `mvn` ngẫu nhiên trong `PATH`.

Ví dụ sau khi đã tạo POM:

```bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper \
    -Dmaven=3.9.9 -Dtype=only-script
```

Lệnh trên là **bước bootstrap của người tạo repository**. Nó cần một Maven sẵn có để chạy Wrapper Plugin lần đầu; sau khi tạo/commit scripts và properties, những người khác có thể dùng:

```bash
./mvnw -version
./mvnw -B clean verify
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd -version
.\mvnw.cmd -B clean verify
```

Wrapper type `only-script` tải/khởi động Maven distribution theo cấu hình, **không yêu cầu commit `maven-wrapper.jar`**. Chạy `git add mvnw mvnw.cmd .mvn/wrapper/maven-wrapper.properties` và commit. Trên Unix bảo đảm file `mvnw` có executable bit trong Git hoặc gọi `sh ./mvnw` theo môi trường phù hợp.

Trong `.mvn/wrapper/maven-wrapper.properties`, property `distributionUrl` trỏ bản Maven đã chọn. Có thể thêm `distributionSha256Sum` **với hash thật đã xác minh từ nguồn đáng tin**, để kiểm binary Maven tải về. Không điền một hash tự đoán.

**Wrapper pin Maven chứ không tự pin JDK.** Vẫn cần cấu hình JDK 17 trong CI/container/SDK tool và xác minh `java -version`. Nếu Wrapper download thất bại do proxy/offline thì đó là lỗi bootstrap/dependency availability, không tự chứng minh source sai.

## 6. Java 17 Maven project dùng trong bài

Dự án đơn module, không có database, network runtime hoặc thư viện production bên ngoài. JUnit chỉ ở test scope. Điều này giữ artifact nhỏ và giảm biến số cần điều tra trong phép so sánh JAR bytes.

```text
rebuild-check/
├── pom.xml
├── .gitattributes
├── .gitignore
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/maven-wrapper.properties
└── src/
    ├── main/
    │   ├── java/demo/rebuild/
    │   │   ├── BuildMessage.java
    │   │   └── Main.java
    │   └── resources/demo/rebuild/banner.txt
    └── test/java/demo/rebuild/BuildMessageTest.java
```

**Không viết file Maven Wrapper scripts bằng tay từ ví dụ này.** Tạo bằng lệnh Wrapper Plugin ở phần 5 rồi commit output thực tế.

Tệp `.gitignore` chỉ là ví dụ:

```gitignore
target/
.qa-m2-local/
```

Không thêm `src/`, `mvnw` hoặc `.mvn/` vào gitignore. Nếu repo đã có các quy tắc ignore, hãy kiểm `git check-ignore` khi nghi ngờ input bị thiếu.

## 7. POM đầy đủ với plugin versions, JDK và timestamp cố định

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.rebuild</groupId>
    <artifactId>rebuild-check</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Rebuild Check</name>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.5.0</version>
                <executions>
                    <execution>
                        <id>enforce-build-runtime</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9.9]</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,18)</version>
                                </requireJavaVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Lý do của các quyết định:**

1. `packaging=jar` cho output main JAR `target/rebuild-check-1.0.0.jar`.
2. `maven.compiler.release=17` khiến compiler target Java 17 API/bytecode. Nó không tự cài JDK.
3. Enforcer yêu cầu **Maven đúng 3.9.9 và JDK major 17** ở runtime build của demo. Đây là policy cố tình nghiêm để hai môi trường giống nhau hơn; vẫn cần ghi nhận JDK patch/vendor nếu đòi byte identity cao.
4. `maven-site`, shading, codegen và resource filtering không được bật vì chúng thêm biến số không cần trong demo.
5. Pin Clean, Resources, Compiler, Surefire và JAR plugin versions, tránh implicit upgrades theo effective build.
6. JUnit Jupiter 5.10.2 ở `test` scope, không được đóng vào main JAR.
7. `failIfNoTests=true` chặn tình huống build PASS dù không tìm được test trong project nhỏ này.
8. `project.build.outputTimestamp` được cố định ở **một UTC timestamp hợp lệ**, giúp plugins hỗ trợ reproducible archives không chèn thời gian build hiện tại vào ZIP entries.

**Không lấy `2024-01-01T00:00:00Z` làm ngày release thật.** Đây là giá trị cố định cho demo. Trong release pipeline, project có thể đặt timestamp từ Git commit hoặc release metadata theo một quy tắc deterministic, rồi commit/chốt giá trị đó.

### 7.1. Vì sao cần outputTimestamp?

ZIP/JAR chứa metadata timestamp ở từng entry. Ngay cả khi `.class` giống nhau, hai lần đóng gói với timestamp theo đồng hồ hiện tại có thể tạo JAR khác byte. Maven JAR Plugin 3.4.2 hỗ trợ `project.build.outputTimestamp` để kiểm soát archive entry timestamps.

Tuy nhiên property này **không thần kỳ sửa mọi output**. Nếu một plugin sinh JSON chứa username, hostname, absolute path, timestamp động hoặc thứ tự không ổn định, JAR vẫn có thể khác. Cần tìm plugin/file gây khác biệt rồi sửa tại nguồn.

Theo tài liệu Maven hiện hành, Maven **3.10.0 trở đi** và một số Maven 4 milestone có mặc định hỗ trợ chế độ Reproducible Builds ở core/super POM. Nhưng bài chủ động pin **Maven 3.9.9** và khai báo property rõ ràng, nên không dựa vào behavior mặc định của dòng Maven khác.

## 8. Java source: tính toán và resource ổn định

Tệp `src/main/java/demo/rebuild/BuildMessage.java`:

```java
package demo.rebuild;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class BuildMessage {
    private BuildMessage() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public static String banner() {
        try (InputStream stream = BuildMessage.class
                .getResourceAsStream("/demo/rebuild/banner.txt")) {
            if (stream == null) {
                throw new IllegalStateException("Missing banner resource");
            }
            return new String(stream.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot read banner", ex);
        }
    }

    public static String message() {
        return banner() + ": 2 + 3 = " + add(2, 3);
    }
}
```

Các điểm liên quan tới build tái lập:

- Code không lấy `Instant.now()`, random number, hostname hay environment variable để sinh output build.
- `Math.addExact` xử lý integer overflow nhất quán theo Java semantics.
- `InputStream.readAllBytes()` và `String.strip()` có trong Java 17.
- Resource được đọc qua **classpath** nên có trong JAR, không cần source directory khi chạy sau packaging.
- UTF-8 được chọn rõ để tránh khác nhau theo default charset.

Tệp `src/main/java/demo/rebuild/Main.java`:

```java
package demo.rebuild;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(BuildMessage.message());
    }
}
```

Tệp `src/main/resources/demo/rebuild/banner.txt` chứa đúng một dòng (cuối dòng LF):

```text
BUILD_READY
```

Với code và resource này, stdout của riêng `Main` là:

```text
BUILD_READY: 2 + 3 = 5
```

Khi so sánh JAR bytes, Maven Resources Plugin sẽ copy resource vào artifact. Giữ line endings của resource ổn định, vì thay CRLF/LF có thể làm khác JAR bytes ngay cả khi `banner().strip()` trả cùng một chuỗi.

## 9. JUnit 5 tests: ba checks độc lập

Tệp `src/test/java/demo/rebuild/BuildMessageTest.java`:

```java
package demo.rebuild;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class BuildMessageTest {

    @Test
    void readsClasspathResource() {
        assertEquals("BUILD_READY", BuildMessage.banner());
    }

    @Test
    void calculatesDeterministicValue() {
        assertEquals(5, BuildMessage.add(2, 3));
    }

    @Test
    void refusesIntegerOverflow() {
        assertThrows(ArithmeticException.class,
                () -> BuildMessage.add(Integer.MAX_VALUE, 1));
    }
}
```

Dự kiến Surefire nhận **3 test methods** và báo:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Đây là **kỳ vọng từ code mẫu**, không phải log của một Maven build đã thực hiện trong bài Knowledge. Vì JAR thông thường không chứa JUnit, chương trình runtime không cần tải test libraries.

Phải kiểm `target/surefire-reports/TEST-demo.rebuild.BuildMessageTest.xml` được tạo trong **lần build mới**; không dùng file XML từ checkout trước làm bằng chứng tests hiện tại chạy.

## 10. Chuẩn hóa line endings và file tracking

Tệp `.gitattributes` gợi ý:

```gitattributes
*.java text eol=lf
*.xml text eol=lf
*.txt text eol=lf
*.properties text eol=lf
mvnw text eol=lf
mvnw.cmd text eol=crlf
```

Git áp dụng EOL rules khi checkout các file được theo dõi, giúp giảm khác biệt Windows/Linux. Khi thay `.gitattributes` cho repository đã có file, cần review cách Git re-normalize file content; đừng tự tạo commit biến đổi hàng nghìn file không liên quan.

**Chú ý:** `.gitattributes` không sửa những file được tạo bởi plugin trong lúc build, cũng không kiểm soát locale/timezone. Nó chỉ xử lý phần source paths áp dụng rule. `*.xml` ở đây áp dụng `pom.xml`, không ép JUnit-generated report XML phải giống byte.

Tệp `.gitignore`:

```gitignore
target/
.qa-m2-local/
```

Giữ Maven Wrapper scripts/properties, POM, Java source và resource trong Git. Không dựa vào file được `.gitignore` bỏ qua nhưng vẫn được script dùng làm đầu vào.

## 11. Lần build tham chiếu ban đầu

Từ thư mục project sau khi đã tạo POM, source và Maven Wrapper:

Linux/macOS:

```bash
./mvnw -version
java -version
./mvnw -B clean verify
```

Windows PowerShell:

```powershell
.\mvnw.cmd -version
java -version
.\mvnw.cmd -B clean verify
```

Sau khi build thành công, kỳ vọng có:

```text
target/classes/demo/rebuild/BuildMessage.class
target/classes/demo/rebuild/Main.class
target/classes/demo/rebuild/banner.txt
target/rebuild-check-1.0.0.jar
target/surefire-reports/TEST-demo.rebuild.BuildMessageTest.xml
```

Hai lệnh Java sau đều dùng được khi `target` đã build:

```bash
java -cp target/classes demo.rebuild.Main
java -cp target/rebuild-check-1.0.0.jar demo.rebuild.Main
```

**Stdout của từng lệnh Java:**

```text
BUILD_READY: 2 + 3 = 5
```

Lệnh thứ hai chạy **class và resource trong packaged JAR**, thay vì `target/classes`. Không dùng `java -jar` vì manifest không khai báo `Main-Class` ở ví dụ này. Một JAR library có thể chạy bằng `java -cp ... FullClassName` mà không phải executable JAR.

Kiểm archive entries:

```bash
jar tf target/rebuild-check-1.0.0.jar
```

Tìm hai class và entry `demo/rebuild/banner.txt`, cùng Maven metadata/manifest thông thường. **Không đòi output `jar tf` chỉ chứa đúng ba dòng** vì archive có thể chứa `META-INF` và những file metadata khác.

## 12. Chốt Git commit làm nguồn duy nhất

Sau khi tạo Maven Wrapper và những file từ phần 6–10, cần commit trạng thái làm **đầu vào**:

```bash
git status --porcelain
git add pom.xml src .gitattributes .gitignore \
    mvnw mvnw.cmd .mvn/wrapper/maven-wrapper.properties
git commit -m "Add reproducible Maven build example"
git status --porcelain
git rev-parse HEAD
```

Lệnh `git commit` đòi repository và Git identity đã được cấu hình. Nếu project thuộc một repo Git có sẵn, không cần `git init` lại. **Không ép commit** khi còn thay đổi không thuộc bài hoặc khi project cần review/approval; đây là thao tác thực hành do người đọc thực hiện.

Sau commit, `git status --porcelain` dự kiến không in gì nếu không có untracked changes được hiển thị. Build output `target/` đã ignore nên cũng không nằm trong commit.

**Quy tắc:** thay source sau commit rồi vẫn ghi nhận commit SHA cũ là một phép đo sai. Hai checkout phải dùng **đúng cùng commit** và các đầu vào bên ngoài được chốt riêng.

### 12.1. Nếu dùng Git submodules hoặc LFS

Các project thật có thể chứa dependency được đưa vào bằng Git submodule/LFS. Khi checkout sạch:

- Submodule commit pointers phải được pin và checkout đúng.
- LFS objects phải được fetch đúng phiên bản; pointer file không thay thế binary cần thiết.
- Build không được đòi secret/config file chưa được cấp qua CI.
- Generated code hoặc binary từ repository khác cần có version/hash được xác nhận.

Bài Java mẫu **không có** submodule/LFS. Các yêu cầu này là phần mở rộng khi áp dụng trong dự án thực.

## 13. Thực hành hai checkout và hai Maven caches trên Linux/macOS

Kịch bản chạy từ **root Git repository của dự án `rebuild-check`** sau khi đã commit. Nó tạo hai clones ở một thư mục tạm, mỗi clone sử dụng local Maven repository và wrapper home khác nhau.

```bash
SOURCE="$(pwd -P)"
COMMIT="$(git rev-parse HEAD)"
BASE="$(mktemp -d)"

git clone --no-local "$SOURCE" "$BASE/checkout-a"
git clone --no-local "$SOURCE" "$BASE/checkout-b"

git -C "$BASE/checkout-a" checkout --detach "$COMMIT"
git -C "$BASE/checkout-b" checkout --detach "$COMMIT"

mkdir -p "$BASE/home-a" "$BASE/home-b"

cat > "$BASE/settings.xml" <<'XML'
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
</settings>
XML

(
    cd "$BASE/checkout-a"
    HOME="$BASE/home-a" MAVEN_USER_HOME="$BASE/home-a/.m2" \
    ./mvnw -B -s "$BASE/settings.xml" \
        "-Dmaven.repo.local=$BASE/cache-a" clean verify
)

(
    cd "$BASE/checkout-b"
    HOME="$BASE/home-b" MAVEN_USER_HOME="$BASE/home-b/.m2" \
    ./mvnw -B -s "$BASE/settings.xml" \
        "-Dmaven.repo.local=$BASE/cache-b" clean verify
)

A="$BASE/checkout-a/target/rebuild-check-1.0.0.jar"
B="$BASE/checkout-b/target/rebuild-check-1.0.0.jar"

if cmp -s "$A" "$B"; then
    printf 'BITWISE_MATCH\n'
else
    printf 'BITWISE_MISMATCH\n'
    exit 1
fi
```

**Trước khi dùng trên máy thật**, bảo đảm Maven Wrapper có quyền thực thi Unix, Git source có đủ commit, quyền truy cập artifact/plugin repositories và JDK 17 được chọn theo Enforcer. Kịch bản dùng `git clone --no-local` để hạn chế việc clone dựa vào local hardlinks/objects optimization, nhưng vẫn chạy trên **cùng một host**.

Hai clones có đường dẫn khác nhau:

- `checkout-a` và `checkout-b`.
- Wrapper base `home-a/.m2` và `home-b/.m2`.
- Local Maven artifact caches `cache-a` và `cache-b`.
- Cùng một settings file tối giản không chứa mirror/profile tuỳ biến.
- Cùng commit SHA, Maven 3.9.9 qua Wrapper, JDK 17 của host.

Một `settings.xml` riêng tách **user Maven settings** khi truyền `-s`. Nó không tự gỡ mọi biến môi trường, JVM extensions hay corporate network policies; xem phần 16.

### 13.1. Kỳ vọng output và giới hạn

Khi dependencies/plugins tải được, các tests pass và JAR được build deterministic, dòng cuối dự kiến:

```text
BITWISE_MATCH
```

Nếu không khớp, script phải in `BITWISE_MISMATCH` và exit code 1. **Không tự sửa/tắt so sánh hash để báo pass.**

Dù hai byte JAR giống nhau, kịch bản mới chứng minh reproducibility trong **hai clones/caches trên cùng host và JDK**. Để tuyên bố build độc lập từ bên thứ ba, cần thử thêm OS/user/JDK/container khác như phần 18.

### 13.2. Hash SHA-256

Trên Linux:

```bash
sha256sum "$A" "$B"
```

Trên macOS thường có thể dùng:

```bash
shasum -a 256 "$A" "$B"
```

Hai đường dẫn khác nhưng SHA-256 phải giống nếu byte JAR giống nhau. `cmp -s` trả exit code 0 khi bytes bằng nhau; do đó **đối chiếu trực tiếp byte** và hash bổ sung hỗ trợ audit.

Không so mỗi file size: hai JAR cùng số byte vẫn có thể khác metadata/contents.

### 13.3. Chặn kết quả giả khi clone/build lỗi

Shell script ở trên mang tính hướng dẫn rõ các bước, nhưng môi trường CI nên bật fail-fast để lỗi của bước Git/Maven không bị các bước sau che. Trên Bash có thể thêm ở đầu một script CI thực:

```bash
set -euo pipefail
```

Nếu sử dụng `set -e`, các lệnh Git clone, checkout và Maven verify trả nonzero sẽ dừng pipeline. Với thư mục tạm đã được tạo, không xóa một path ngẫu nhiên bằng `rm -rf` khi chưa xác minh giá trị path. Dùng workspace cleanup của CI hoặc kiểm path thuộc thư mục tạm đúng scope.

## 14. Thực hành tương đương trên Windows PowerShell

Các bước sau dùng Windows PowerShell với một base directory mới theo GUID để tránh đè lên cache từ lần trước. Chạy từ root Git repository `rebuild-check`:

```powershell
$source = (Get-Location).Path
$commit = (git rev-parse HEAD).Trim()
$base = Join-Path $env:TEMP ('mvn-rebuild-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $base | Out-Null

$a = Join-Path $base 'checkout-a'
$b = Join-Path $base 'checkout-b'
$settings = Join-Path $base 'settings.xml'

git clone --no-local "$source" "$a"
if ($LASTEXITCODE -ne 0) { throw 'Git clone A failed' }
git clone --no-local "$source" "$b"
if ($LASTEXITCODE -ne 0) { throw 'Git clone B failed' }

git -C "$a" checkout --detach "$commit"
if ($LASTEXITCODE -ne 0) { throw 'Checkout A failed' }
git -C "$b" checkout --detach "$commit"
if ($LASTEXITCODE -ne 0) { throw 'Checkout B failed' }

@'
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
</settings>
'@ | Set-Content -LiteralPath $settings -Encoding UTF8

$oldWrapperHome = $env:MAVEN_USER_HOME

try {
    $env:MAVEN_USER_HOME = Join-Path $base 'home-a'
    Push-Location $a
    try {
        .\mvnw.cmd -B -s "$settings" `
            "-Dmaven.repo.local=$base\cache-a" clean verify
        if ($LASTEXITCODE -ne 0) { throw 'Build A failed' }
    } finally { Pop-Location }

    $env:MAVEN_USER_HOME = Join-Path $base 'home-b'
    Push-Location $b
    try {
        .\mvnw.cmd -B -s "$settings" `
            "-Dmaven.repo.local=$base\cache-b" clean verify
        if ($LASTEXITCODE -ne 0) { throw 'Build B failed' }
    } finally { Pop-Location }
}
finally {
    $env:MAVEN_USER_HOME = $oldWrapperHome
}

$jarA = Join-Path $a 'target\rebuild-check-1.0.0.jar'
$jarB = Join-Path $b 'target\rebuild-check-1.0.0.jar'

$hashA = (Get-FileHash -LiteralPath $jarA -Algorithm SHA256).Hash
$hashB = (Get-FileHash -LiteralPath $jarB -Algorithm SHA256).Hash

if ($hashA -eq $hashB) {
    Write-Output 'BITWISE_MATCH'
} else {
    throw 'BITWISE_MISMATCH'
}
```

`Get-FileHash -Algorithm SHA256` cho giá trị hash của file. Khi khớp, output của riêng nhánh so sánh là `BITWISE_MATCH`. Các dòng Maven/Git vẫn có log riêng, không được coi là stdout chỉ của lệnh kiểm hash.

Với PowerShell, backtick nối dòng phải ở cuối dòng và **không có whitespace theo sau**. Chỗ đặt `Push-Location`/`Pop-Location` giúp Maven Wrapper tìm project ở checkout tương ứng. `MAVEN_USER_HOME` chủ yếu phục vụ Wrapper distribution location; `-s` và `-Dmaven.repo.local` vẫn cần để chỉ rõ settings/cache Maven.

**Không xóa thư mục tạm `$base` bằng lệnh xóa recursive một cách mù quáng.** Chỉ dọn directory do script thực sự tạo ra và được xác minh dưới vùng temp hợp lệ.

## 15. So sánh cái gì và đọc kết quả như thế nào?

Dự án ví dụ tạo main JAR:

```text
target/rebuild-check-1.0.0.jar
```

Những thứ có thể so sánh:

1. **Byte identity của main JAR:** `cmp -s`, `sha256sum` hoặc `Get-FileHash`.
2. **Archive entries:** `jar tf` hoặc công cụ ZIP để thấy class/resource/manifest.
3. **Java behavior:** chạy `java -cp <jar> demo.rebuild.Main` ở hai môi trường, so stdout.
4. **Tests:** đọc Surefire XML từ đúng run, ba tests đều pass.
5. **Metadata:** Maven POM version, plugin versions và effective dependency tree.
6. **Published artifact:** nếu đang thử một release, so JAR rebuild với JAR tải từ staging/repository đã phát hành.

Với cùng source, cùng toolchain và output timestamp được pin, **byte JAR dự kiến bằng nhau**. Kỳ vọng này cần được **đo**, không suy ra chỉ từ cấu hình POM.

### 15.1. JAR hash khác nhưng ứng dụng chạy giống nhau

Nguyên nhân có thể là:

- ZIP entry timestamps khác.
- File manifest chứa build date, username hoặc absolute directory.
- Resource được lọc thành biến chứa thời gian/host/IP.
- File thứ tự không xác định trong archive.
- Git EOL khác khiến `.txt`/script/resource khác bytes.
- Annotation processor/code generator tạo output với random UUID/clock.
- Một plugin tạo metadata từ `git describe`, dirty status hoặc wall clock.
- JDK vendor/patch hoặc compiler options thay.
- Tài liệu/source JAR/javadoc/generation plugin không reproducible.

Cần giải quyết bằng cách tìm **entry khác đầu tiên**, không sửa expected hash thủ công.

### 15.2. Artifact hash giống nhưng tests fail

Có thể artifact main JAR được tạo giống byte nhưng CI tests đang dùng dữ liệu external thay đổi, timezone khác hoặc flaky tests. **Hash equality không thay thế quality gates.**

Ngược lại, tests pass không chứng minh byte equality. Ghi **hai kết quả riêng**: `TEST_QA` và `ARTIFACT_REPRODUCIBILITY`.

## 16. Đầu vào môi trường khó kiểm soát

### 16.1. JDK và Maven versions

Maven Wrapper pin Maven 3.9.9, Enforcer từ POM yêu cầu Maven 3.9.9 và Java 17. Nhưng hai bản JDK 17 khác vendor/patch vẫn có thể tạo output khác với một số công cụ. Với yêu cầu nghiêm ngặt, dùng:

- Container image **được pin bằng digest** (không chỉ tag `latest`).
- JDK distribution/version được ghi nhận.
- CI job logs `java -version`, `./mvnw -version`.
- Compiler flags và annotation processors được pin.
- Cùng OS/architecture hoặc kiểm chứng matrix xuyên OS theo policy.

Maven Toolchains Plugin có thể chọn JDK theo yêu cầu toolchain nhưng không tự download mọi JDK; `toolchains.xml` phải được CI cung cấp. Enforcer chỉ **kiểm điều kiện**, không thay Java runtime.

### 16.2. Maven settings, mirrors và profiles

`-s <settings.xml>` giúp dùng user settings có thể review. `-Dmaven.repo.local=<path>` tách local artifact cache. Tuy nhiên cần xét thêm:

- Global Maven settings từ distribution.
- `.mvn/maven.config`, `.mvn/jvm.config` và project extensions.
- Corporate mirrors/repositories/proxies.
- Active profiles, Java/OS/file activation.
- Maven repository credentials và secret injection.
- User JVM flags qua `MAVEN_OPTS`/`JAVA_TOOL_OPTIONS`.
- Maven extensions có thể bị load từ môi trường ngoài repository.

Nếu hai máy dùng cùng POM nhưng một profile tự bật theo OS/Java version, họ có thể build **hai sản phẩm khác nhau** mà không nhận ra. Ghi lại effective POM, Maven/JDK versions và profiles theo yêu cầu audit.

### 16.3. Dependencies và plugins không bất biến

Cần tránh:

- Dependency version ranges không được quản lý hoặc lock.
- `LATEST`/`RELEASE` theo mô hình cũ.
- SNAPSHOT dependencies thay đổi nội dung theo thời gian.
- Plugin không pin version, plugin prefix resolve khác.
- Repository cho phép ghi đè release artifacts.
- Dynamic code generation từ network mà không pin source/version.

Ngay cả khi dùng cache mới, Maven chỉ có thể tái lập nếu repository cung cấp **cùng bytes** cho từng dependency/plugin hoặc các checksum được xác minh. Pin version giúp nhưng không đủ nếu repository cho phép mutable artifacts.

### 16.4. Bẫy offline mode

Lệnh:

```bash
./mvnw -o clean verify
```

chỉ hoạt động khi **mọi** artifact/plugin cần thiết đã có trong local repository. Với cache mới hoàn toàn, offline mode thường sẽ fail. Đó là lỗi **dependency availability**, không tự chứng minh build bất khả tái lập.

Có thể chuẩn bị trước một cache qua Maven Dependency Plugin `go-offline` cho môi trường bị giới hạn network, nhưng goal này không cam kết mọi artifact được dynamic plugin execution yêu cầu đều chắc chắn có sẵn. Phải thực nghiệm **chính lifecycle của dự án** ở offline job trước khi tuyên bố hỗ trợ offline.

## 17. Maven Artifact Plugin: kiểm reproducible build tự động

Apache Maven có **Maven Artifact Plugin** hỗ trợ kiểm những plugin liên quan tới khả năng tái lập, so output build với artifact tham chiếu:

```bash
./mvnw -B \
    org.apache.maven.plugins:maven-artifact-plugin:3.7.0:check-buildplan
```

Mục tiêu `check-buildplan` giúp cảnh báo về plugin versions có vấn đề reproducible builds đã biết. Nó **không** chứng minh mọi dynamic resource/template hoặc external input đã ổn định.

Một phép thử nhanh trong **cùng checkout và local repository**:

```bash
./mvnw -B clean install
./mvnw -B clean verify \
    org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
```

Theo Maven reproducible builds guide, `compare` có thể so current output với artifact đã install/download làm reference. Kết quả/diagnostics có thể được ghi ra `.buildcompare` theo plugin configuration.

**Quan trọng:** đây là **local smoke test của reproducibility**, chưa chứng minh môi trường độc lập vì lần thứ hai vẫn có cùng OS, username, JDK, repository/cache và filesystem location. Dùng nó để tìm sớm timestamp/dynamic data, sau đó vẫn chạy **hai clean checkouts và môi trường tách biệt**.

Nếu kiểm artifact đã publish, tham khảo cấu hình `reference.repo` trong tài liệu Maven Artifact Plugin. Không install hoặc deploy đè release artifact vào repository production chỉ để tạo reference.

## 18. Từ hai checkout trên một host đến môi trường thực sự độc lập

Hai clones và cache riêng giúp tìm các dependency ẩn vào `target`, local artifacts, untracked source và một số dạng cache contamination. Nhưng chúng vẫn **chung**:

- Kernel/OS, CPU architecture, locale/timezone mặc định.
- Java binary/JDK installation.
- Network, DNS, corporate proxy/mirror.
- Một số environment variables và global Maven settings.
- Quyền filesystem và workspace mount.

Để tăng mức bảo đảm, triển khai hai job build ở **hai container/VM/runner độc lập**, không share Maven local caches, pin container images và bảo đảm cùng commit SHA.

Một mô hình CI:

```text
                  Git commit SHA cố định
                           |
             +-------------+-------------+
             |                           |
             v                           v
       Runner A                     Runner B
  checkout sạch, cache A       checkout sạch, cache B
  Maven Wrapper/JDK17           Maven Wrapper/JDK17
  clean verify                  clean verify
             |                           |
             v                           v
      rebuild-check.jar           rebuild-check.jar
             |                           |
             +------------+--------------+
                          |
                          v
                 so SHA-256 / bytes
                          |
                          v
               Tests PASS + Hash MATCH?
                          |
                +---------+--------+
                |                  |
               YES                 NO
                |                  |
                v                  v
          Chấp nhận QA       Chặn release, diff
```

Cần phân biệt **reproducible trên hai môi trường được kiểm soát** với **reproducible giữa mọi OS/JDK**. Một project có thể cam kết reproducibility trên cùng container digest và JDK distribution, chưa cam kết bitwise equality Windows/Linux. Chọn test matrix theo hợp đồng phát hành.

## 19. Dùng diffoscope khi checksum không giống

Nếu JAR khác, bước tiếp theo là xác định **file/entry/byte nào khác**. Có thể dùng công cụ so sánh ZIP archives hoặc diffoscope (nếu CI có cài sẵn). Không cần sửa code theo cảm tính.

Quy trình:

1. Lưu hai artifact không bị ghi đè bởi build sau.
2. Ghi SHA-256, file sizes và Git commit SHA.
3. Liệt kê contents bằng `jar tf`.
4. Xem manifest, `.class`, Maven metadata và resources theo từng entry.
5. So timestamps/entry order, resource line endings và generated files.
6. Nếu `.class` khác, kiểm JDK/compiler versions và bytecode generation.
7. Nếu resource khác, kiểm EOL, locale, filtering và environment variables.
8. Nếu chỉ archive metadata khác, kiểm `project.build.outputTimestamp` và phiên bản JAR/archiver plugins.
9. Đổi **đúng nguồn không xác định** rồi thử lại bằng clean checkout và cache mới.
10. Lưu diagnosis và kết quả hash mới trong CI.

Chỉ thay timestamp của file **sau khi build** bằng một script patch ZIP không phải giải pháp tốt nếu plugin nguồn vẫn sinh dữ liệu không deterministic; tốt hơn sửa cơ chế build ở nơi tạo artifact.

## 20. CI pipeline tối thiểu và tiêu chí đạt

Một pipeline cần có hai nhóm gate độc lập:

| Gate | Dữ liệu chứng minh | Tiêu chí dự án ví dụ |
| --- | --- | --- |
| Git source | Commit SHA và checkout status | Cùng một SHA ở hai jobs |
| Maven version | `./mvnw -version` | Maven 3.9.9 |
| Java | `java -version`, Enforcer | Java 17 |
| Build | Exit code của `clean verify` | Cả hai jobs PASS |
| Test discovery | Surefire XML | Mỗi job đúng 3 tests |
| Test quality | failures/errors/skipped | Đều bằng 0 |
| Artifact path | File main JAR | `rebuild-check-1.0.0.jar` |
| Artifact bytes | SHA-256/`cmp` | Hash/bytes bằng nhau |
| Runtime smoke | `java -cp <jar> demo.rebuild.Main` | `BUILD_READY: 2 + 3 = 5` |
| Cache isolation | Maven local repository paths | Hai cache không chia sẻ |
| Environment | JDK/container/settings/profiles | Có thể tái tạo và có record |
| Provenance | Commit + hash + toolchain | Khớp release candidate |

**Kết quả kỳ vọng từ code mẫu** không phải là log đã được thực thi trong môi trường này. Với real CI, nếu một build fail, không thực hiện hash PASS giả bằng artifact cũ trong workspace. Đồng thời đừng xóa những evidence đã có; archive logs/test XML có phân quyền phù hợp.

### 20.1. Bản build phát hành và bản rebuild

Có hai cách so sánh:

- **Hai rebuild độc lập cùng commit:** xem bản build có deterministic trong những môi trường kiểm soát hay không.
- **Rebuild so với artifact đã publish:** kiểm phát hành có đúng với source/recipe khai báo hay không.

Cách thứ hai cần lấy **artifact được publish thực sự** từ staging/repository, kiểm signature/checksum/provenance và so với JAR được rebuild. Không chỉ so hai output tại `target/` của cùng workspace.

Một release pipeline tốt nên promote **chính candidate artifact đã qua QA**, tránh rebuild lại rồi lặng lẽ publish một JAR byte khác.

## 21. Những thay đổi có thể làm mất tính tái lập

### 21.1. Thêm timestamp runtime vào resource được lọc

Nếu dùng Maven resource filtering để nhét `build.time` lấy từ đồng hồ hiện tại vào một file, JAR thay đổi theo giờ. Unit test logic có thể vẫn pass, nhưng SHA-256 khác.

Khắc phục: nếu cần metadata thời gian, chọn **timestamp cố định theo release/commit policy**, hoặc đưa thông tin build environment động vào một manifest ngoài artifact reproducible mà sản phẩm đã quy định.

### 21.2. Dùng thư viện SNAPSHOT cho plugin/codegen

SNAPSHOT cùng tọa độ có thể cho bytes mới sau một thời gian. Dù source Git không đổi, máy mới tải artifact khác và tạo output khác. Pin releases bất biến, kiểm checksum và repositories.

### 21.3. Build từ dirty working tree

Nếu source sửa chưa commit, build A dùng những sửa đổi đó trong khi Git clone B không có. Đây không phải lỗi Maven; đó là **hai source inputs khác nhau**. `git status --porcelain` và commit pin giúp tránh.

### 21.4. Java version thay đổi mà không nhận ra

`maven.compiler.release=17` giới hạn API/bytecode target nhưng không bắt compiler implementation của hai JDK vendor/patch khác nhau sinh mọi byte giống nhau. Pin toolchain và kiểm actual compiler/runtime. Java 17 application có thể chạy trên Java mới hơn, nhưng điều đó không tự bảo đảm artifact rebuilt bitwise giống nhau.

### 21.5. Plugin compile/test khác

Đổi Maven Compiler/Surefire/JAR plugin có thể thay generated metadata, test execution hoặc archive order. Build reproducibility cần pin **cả plugin versions**, không chỉ dependencies.

### 21.6. Môi trường offline

Một checkout mới không có cached Maven distribution/dependencies sẽ không build với `-o`. Muốn kiểm offline, **chuẩn bị cache có kiểm chứng** rồi chạy offline trong môi trường độc lập; không gọi đó là “fresh network resolution”.

### 21.7. Generated code lấy từ external API

Nếu build tải OpenAPI schema, Protobuf definitions hoặc dữ liệu từ server không pin version/hash, source commit không đủ xác định output. Vendor/pin schemas và generator versions hoặc ghi checksum của external inputs.

### 21.8. Đổi line endings khi checkout

Git/OS có thể cho resource CRLF ở Windows, LF ở Linux. `.gitattributes` với `eol=lf` giảm khác biệt input; cần kiểm resource data được đóng gói từ chính checkout.

## 22. Troubleshooting theo dấu hiệu

| Triệu chứng | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Clean clone không có `mvnw` | Chưa commit Wrapper scripts | Commit `.mvn/wrapper`, `mvnw`, `mvnw.cmd` |
| `Permission denied: ./mvnw` | Thiếu executable bit Unix | Sửa file mode/commit hoặc chạy shell phù hợp |
| Wrapper không tải Maven | Proxy/network/certificate/URL/checksum | Kiểm wrapper properties và trusted mirror |
| Build Maven version sai | Dùng `mvn` global thay Wrapper | Gọi `./mvnw`, đọc `-version` |
| Enforcer fail Java version | Chọn sai `JAVA_HOME`/JDK major | Chọn JDK17 đúng policy |
| `Non-resolvable parent POM` | Parent chưa publish/không nằm trong checkout | Pin parent GAV/repository, build Reactor phù hợp |
| Dependency not found ở cache sạch | Library/plugin chưa có trong repositories được phép | Kiểm settings/mirror/GAV, không hack local cache |
| Local build pass nhưng clean clone fail | Missing untracked/ignored file hoặc local artifact | Kiểm Git tracked inputs và source repository |
| Test count bằng 0 | Test naming/provider/skip flags sai | Surefire config, `failIfNoTests`, đọc XML |
| Maven `-o` fail khi cache trống | Dependency/plugin chưa tải | Chuẩn bị cache trước, thử online có kiểm soát |
| Hash khác dù tests pass | ZIP timestamps/generated metadata/EOL | `outputTimestamp`, archive diff, plugin versions |
| Hash giống nhưng tests fail | Tests dùng external/time-dependent data | Tách quality gate và reproducibility gate |
| Windows/Linux artifact khác | EOL/locale/JDK/plugin/OS differences | `.gitattributes`, env matrix, diff entries |
| `.class` khác bytes | Compiler patch/vendor/options/codegen khác | Pin JDK image/compiler/toolchains |
| Manifest khác | Plugin thêm build time/user/git dirty flag | Sửa plugin configuration và input |
| Resource trong JAR khác | Filtering/line ending/encoding | Pin UTF-8, bỏ dynamic values |
| Run A pass, run B download artifact khác | SNAPSHOT hoặc mutable remote repo | Pin releases/immutable sources và checksums |
| `cmp` chưa được cài trên Windows | Dùng POSIX command trên PowerShell | Dùng `Get-FileHash -Algorithm SHA256` |
| `java -jar` báo thiếu Main-Class | JAR mẫu không là executable JAR | Chạy `java -cp <jar> demo.rebuild.Main` |
| Maven Wrapper dùng cache chung | `MAVEN_USER_HOME` không tách | Đặt wrapper home riêng cho từng run |
| Maven Resolver dùng cache chung | Không truyền `maven.repo.local` | Chỉ định repo path riêng và kiểm logs |
| User Maven settings thay kết quả | Profiles/mirrors credentials ngoài Git | Truyền `-s` riêng, ghi effective settings policy |
| CI artifact hash khác staging | Pipeline rebuild/transform sau QA | Promote candidate đã kiểm hoặc compare binary |
| Một module bị skipped | Upstream failure/selection | Không coi SKIPPED là PASS |
| Cố chạy hash trước khi build xong | File cũ/thiếu trong workspace | Fail-fast, xác nhận exit code/artifact existence |

## 23. Câu hỏi tự kiểm tra

**1. `mvn clean verify` trên working tree cũ có tương đương clean checkout không?**

Không. Clean xóa build output, không hoàn nguyên source chưa commit, local Maven repository hay môi trường.

**2. Maven Wrapper pin được JDK không?**

Không. Wrapper chủ yếu pin Maven distribution; JDK được chọn qua CI/container/toolchains/JAVA_HOME và có thể kiểm bằng Enforcer.

**3. Hai JAR chạy cùng output có buộc SHA-256 giống nhau không?**

Không. Archive timestamps, manifest, resource bytes hay file order có thể khác mà behavior vẫn giống.

**4. Vì sao phải dùng hai Maven local caches?**

Để giảm khả năng một bản build âm thầm thành công nhờ artifact/plugin đã cài hoặc cache trên máy tác giả, và thử dependency resolution trong môi trường sạch hơn.

**5. Vì sao dùng `project.build.outputTimestamp`?**

Để các archive plugins hỗ trợ có thể tạo ZIP/JAR metadata thời gian ổn định thay vì dùng thời gian build hiện tại.

**6. Hai clones trên cùng host đã đủ tuyên bố independent-party reproducibility chưa?**

Chưa. Chúng vẫn chung JDK/OS/network và nhiều biến môi trường. Cần thử môi trường/runner thực sự độc lập và so với published artifact khi mục tiêu đó được yêu cầu.

**7. Có nên dùng dependency SNAPSHOT cho một reproducible release?**

Nên tránh nếu không có biện pháp pin exact bytes/provenance; SNAPSHOT có thể thay đổi dù POM/source không đổi.

**8. Vì sao phải xem Surefire XML?**

Để biết tests thực sự được phát hiện và chạy; `BUILD SUCCESS` cùng `0 failures` mà `0 tests` không đủ tin cậy.

**9. Artifact `target/rebuild-check-1.0.0.jar` được chạy bằng lệnh gì?**

`java -cp target/rebuild-check-1.0.0.jar demo.rebuild.Main`, vì không có Main-Class trong manifest.

**10. Nếu two-run hash khác, bước tiếp theo là gì?**

Lưu hai JAR, so archive entries/manifest/resources/bytecode, tìm nguồn timestamp, EOL, plugin/JDK/env khác biệt; sửa đúng đầu vào rồi thử lại từ clean checkout.

## 24. Checklist bàn giao

- [ ] Source commit SHA được ghi chính xác, không dùng dirty/untracked files làm input?
- [ ] Maven Wrapper scripts/properties được commit, Maven version đã pin?
- [ ] JDK vendor/version/major và Compiler release có policy rõ?
- [ ] Các Maven plugins và dependency versions quan trọng đã pin?
- [ ] `project.build.outputTimestamp`/reproducible archive mode hợp lệ?
- [ ] Source encoding/line endings và resource input có thể kiểm soát?
- [ ] Git submodules/LFS/codegen/external inputs được pin nếu có?
- [ ] Có ít nhất một clean checkout và build thành công mà không dựa IDE state?
- [ ] Có hai checkout hoặc hai CI runners độc lập với local Maven caches riêng?
- [ ] User settings, global settings, active profiles, env vars được kiểm soát hoặc ghi nhận?
- [ ] Mỗi job `clean verify` có exit code thành công và Surefire XML mới?
- [ ] Không có FAIL/ERROR/SKIPPED bị tính nhầm là PASS?
- [ ] Main JAR tên GAV/version đúng, chứa class/resource mong đợi?
- [ ] Runtime smoke có stdout chính xác và dùng JAR đã đóng gói?
- [ ] Đã so bytes hoặc SHA-256 của các JAR tương ứng?
- [ ] Nếu hash khác, đã có archive diff và root cause thay vì ghi đè expected hash?
- [ ] Khi cần release verification, so với binary published/staged thật?
- [ ] Có build provenance: commit, Maven/JDK, POM/plugins, checksum và môi trường?
- [ ] Không đưa secrets, repository credentials hay thông tin nhạy cảm vào logs/artifacts?
- [ ] Có policy rollback/cleanup cache và chỉ promote artifact đã qua QA?

**Kết luận:** để Maven build đáng tin, phải có **source checkout sạch tại một commit cố định** và **môi trường có thể tái tạo**: Wrapper, JDK, plugin/dependency versions, repositories/settings, resource encoding và output timestamps. Chạy lại trong hai checkouts/caches riêng phát hiện nhiều dependency ẩn; so JAR bytes/SHA-256 phát hiện nondeterminism mà unit tests không thấy. Với tuyên bố reproducibility nghiêm ngặt, phải thêm kiểm tra ở môi trường độc lập thực sự và đối chiếu với artifact đã publish, không chỉ `mvn clean` trên máy của tác giả.

### Tài liệu tham khảo chính thức

- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Apache Maven Wrapper — Usage](https://maven.apache.org/tools/wrapper/)
- [Apache Maven Wrapper Plugin — wrapper:wrapper](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html)
- [Apache Maven Artifact Plugin — Plugin Info](https://maven.apache.org/plugins/maven-artifact-plugin/plugin-info.html)
- [Apache Maven Artifact Plugin — artifact:compare](https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven JAR Plugin — Usage](https://maven.apache.org/plugins/maven-jar-plugin/usage.html)
- [Apache Maven Enforcer — requireMavenVersion](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html)
- [Apache Maven Enforcer — requireJavaVersion](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html)
- [Apache Maven Dependency Plugin — go-offline](https://maven.apache.org/plugins/maven-dependency-plugin/go-offline-mojo.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
