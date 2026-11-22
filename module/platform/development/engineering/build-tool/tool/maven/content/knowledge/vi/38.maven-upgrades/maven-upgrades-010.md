# Chuẩn bị khả năng quay lại phiên bản Maven trước khi áp dụng nâng cấp rộng rãi

## 1. Mục tiêu: nâng cấp có đường lui được thử trước, không chỉ có kế hoạch trên giấy

Một nhóm phát triển dự kiến nâng phiên bản Apache Maven được dùng bởi developer laptops, IDE, CI runners, build containers và quy trình phát hành. Nâng cấp có thể mang lại sửa lỗi, cải thiện Maven Resolver, bảo mật hoặc tính năng mới. Tuy nhiên, nếu chỉ thay Maven trên toàn công ty rồi chờ phát hiện lỗi, khả năng khôi phục sẽ phụ thuộc vào trí nhớ của vài người, trạng thái local cache và những phiên bản cũ có còn tải được hay không.

**Khả năng quay lại (rollback readiness)** là năng lực **đã được chuẩn bị, diễn tập và xác nhận** để đưa các build workflows về một **baseline đã biết là chạy tốt** sau khi candidate Maven không đáp ứng tiêu chí, mà không làm mất source, phát hành sai artifact, lộ credentials hoặc âm thầm bỏ qua tests.

Một rollback thật sự cần cả:
- **Bản cấu hình cũ có thể khôi phục**: Maven distribution, wrapper files, CI image, plugin versions, settings/extensions, JDK.
- **Artifact và công cụ cũ có thể truy xuất**: approved Maven distribution, kiểm checksum, dependency mirror, repository credentials phù hợp.
- **Lệnh chạy rõ ràng**: ai kích hoạt, thứ tự sửa những layer nào, checkpoint và tiêu chí xác nhận phục hồi.
- **Bằng chứng baseline**: logs, test reports, JAR/POM/metadata, các smoke/integration tests, lệnh tạo ra chúng.
- **Ranh giới tác dụng phụ**: không được ghi đè immutable release, không rollback production deployment chỉ bằng cách hạ Maven, không dùng một local cache bẩn để che lỗi.
- **Quyền quyết định**: owner, gate, thời điểm dừng rollout, thông báo, trách nhiệm khôi phục và kiểm lại.

Với bài lab, dùng **Maven 3.9.16 làm baseline** và **Maven 3.10.0 làm candidate**. Theo lịch sử Apache Maven tại thời điểm viết (10/11/2026), hai phiên bản này là bản GA. Maven 4.0.0 vẫn đang ở nhánh release candidate; phần riêng của bài giải thích tại sao chuyển sang Maven 4 cần kế hoạch phức tạp hơn.

**Nguyên tắc vàng:** nếu chưa chạy thử quy trình trở về phiên bản cũ trên một môi trường có trạng thái tương đương production CI, thì chưa thể khẳng định nâng cấp có khả năng rollback.

## 2. “Rollback Maven” thực chất có thể là nhiều kiểu rollback

Đừng gọi chung mọi thay đổi là “nâng Maven”. Ghi chính xác lớp cần quay lại:

| Lớp | Thay đổi điển hình | Cách khôi phục |
| --- | --- | --- |
| Maven core/CLI | Maven 3.9.16 → 3.10.0 | Trỏ lại distribution cũ bằng Wrapper, CI image hoặc tool installation |
| Maven Wrapper | `.mvn/wrapper/maven-wrapper.properties`, `mvnw` | Revert toàn bộ wrapper config/scripts tương ứng |
| Build plugins | Compiler, Surefire, JAR, Deploy plugins | Revert POM/pluginManagement và executions |
| JDK chạy Maven | Temurin 17 → 21 hoặc phiên bản khác | Khôi phục JDK/JAVA_HOME/CI setup nếu cần; kiểm baseline thực tế |
| Maven settings | `settings.xml`, mirrors, servers, proxies | Trả lại cấu hình đã được phê duyệt qua secrets/config management |
| Maven extensions | `.mvn/extensions.xml`, `.mvn/maven.config` | Khôi phục bản tương thích với Maven cũ |
| CI job/container | Docker image, runner image, `mvn` PATH | Pin lại digest/image/tool setup và xác minh runtime |
| Project POM model | Maven 4.1.0 `<subprojects>`, root attrs | Revert cả POM changes không tương thích Maven 3 |
| Artifact publishing | Staging, deploy URL, signing | Dừng phát hành mới, kiểm remote repository và release policy |
| Ứng dụng đang vận hành | Runtime/container/service đã deploy | Cần **kế hoạch rollback ứng dụng riêng**, không chỉ hạ Maven |

**Quan trọng:** Một POM có thể được revert nhưng CI vẫn gọi một `mvn` mới từ PATH. Ngược lại, Maven Wrapper đã về 3.9.16 nhưng plugin vừa nâng cấp yêu cầu Maven 3.10 hoặc Maven 4. Khi đó “đã rollback phiên bản Maven” vẫn chưa đưa toàn build về trạng thái biết tốt.

### 2.1. Upgrade vs rollback vs roll-forward

- **Upgrade:** chuyển sang candidate mới theo kế hoạch.
- **Rollback:** khôi phục một tập cấu hình/đường chạy cũ đã kiểm chứng.
- **Roll-forward:** phát triển bản sửa mới trên candidate khi việc quay lại không còn an toàn hoặc không thể phục hồi trạng thái bên ngoài.
- **Application rollback:** triển khai lại phiên bản ứng dụng trước đó; không đồng nghĩa Maven toolchain rollback.

Chọn chiến lược theo rủi ro. Nếu một release đã ghi schema dữ liệu không tương thích ngược, rollback Maven **không sửa database schema**. Nếu một artifact release GAV đã công bố là immutable, rollback không cho phép ghi JAR khác lên chính GAV đó.

## 3. Mốc phiên bản, tương thích và phạm vi của ví dụ

Theo [Apache Maven Releases History](https://maven.apache.org/docs/history), các bản đáng chú ý trong kịch bản là:

- **Maven 3.9.16:** baseline đã được phê duyệt của nhóm giả định.
- **Maven 3.10.0:** candidate GA có thể dùng để minh họa nâng cùng major.
- **Maven 4.0.0-rc-7:** một release candidate được liệt kê trong lịch sử; **không coi nó là bản GA** hay mặc định đưa vào production.
- **Java 17:** runtime tối thiểu được yêu cầu khi thử Maven 4 theo tài liệu migration; lab dùng Java17 để đơn giản hóa.

Chúng ta **không khẳng định** 3.9.16 là baseline của mọi tổ chức. Baseline phải được chọn từ phiên bản đang chạy tốt đã được inventory/approve thực tế. Nếu hệ thống đang dùng Maven 3.10.0, vẫn áp dụng cùng phương pháp với một baseline khác phù hợp.

Ví dụ cấu hình project sẽ được cố định trên **Maven 3.x**, sử dụng POM model 4.0.0. Không lén bật Maven4-only features trong giai đoạn mà nhóm vẫn yêu cầu có thể quay về Maven 3.

## 4. Trước khi nâng cấp: đóng băng trạng thái đã biết tốt

Một gói baseline nên ghi những thông tin sau:

| Thông tin | Ví dụ trong bài | Cách kiểm |
| --- | --- | --- |
| Commit source | Git commit được tag/phê duyệt | `git rev-parse HEAD` |
| Maven invocation | `./mvnw -B -ntp clean verify` | CI command và log |
| Maven distribution | `3.9.16` | `./mvnw -version` |
| JDK runtime | JDK 17 | `java -version`, Maven `Java version` |
| Maven Wrapper | `mvnw`, `mvnw.cmd`, `.mvn/wrapper/...` | Git diff và checksum |
| Plugin versions | Compiler 3.13.0, Surefire 3.5.2, JAR 3.4.2 | POM/effective POM |
| Dependency graph | Dependency versions đã resolve | dependency tree/BOM |
| Maven settings | Mirror IDs, server IDs, proxies; **không lưu secrets** | Protected config snapshot |
| CI images | Docker digest/runner/tool configuration | CI config version |
| Tests và reports | Unit/IT/contract/packaging/smoke | Surefire/Failsafe reports |
| Artifacts | JAR/POM/checksum/manifest | Build outputs |
| Repo destinations | Approved staging/release repositories | Deploy policy, ACL |
| Rollback owner | Build/release engineer và approver | Runbook |

Giữ **bằng chứng** khác với sao chép toàn bộ secret. Không đính kèm `settings.xml` có password, private key, environment dumps hoặc log chứa tokens vào tài liệu baseline công khai. Dùng danh tính secret/key reference và version của secret config trong vault.

### 4.1. Những gì cần ghi từ command line

Từ root project:

~~~bash
git status --short
git rev-parse HEAD
java -version
javac -version
mvn -version
~~~

Nếu repository có Maven Wrapper:

~~~bash
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Trên Windows dùng:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
~~~

`mvn -version` là Maven system được resolve từ PATH. `./mvnw -version` là distribution được Wrapper chọn. Hai kết quả có thể khác. **Bản chạy thật trong CI mới quyết định baseline đang được kiểm**, không phải việc file wrapper tồn tại trong Git.

### 4.2. Không đánh đồng Git tag với binary backup

Git tag lưu source/configuration snapshot. Nó **không đảm bảo** Maven binary, Docker image, dependency/plugin artifacts, JDK cũ, internal mirror và credentials còn tồn tại sau nhiều tháng.

Trước rollout:
1. Đảm bảo approved Maven distribution cũ có thể tải từ repository/mirror được hỗ trợ.
2. Xác minh checksum theo nguồn tin cậy.
3. Đảm bảo CI image cũ được giữ bằng immutable digest hoặc tool installation version.
4. Xác nhận Java runtime phù hợp vẫn có.
5. Giữ plugin dependencies cần cho baseline resolve được từ approved repositories.
6. Đặt quy tắc retention cho baseline artifacts/logs.
7. Thử **thực sự tải và chạy bản cũ trên runner sạch**.

## 5. Maven Wrapper: điểm neo tốt cho việc quay lui

Maven Wrapper cho phép repository khai báo distribution để chạy bằng `mvnw`/`mvnw.cmd`, thay vì dựa vào Maven có sẵn trên PATH. Thành phần quan trọng:

~~~text
project/
├── mvnw
├── mvnw.cmd
└── .mvn/
    └── wrapper/
        └── maven-wrapper.properties
~~~

Dạng `only-script` dùng shell/PowerShell để tải và khởi chạy Maven distribution, không yêu cầu commit Wrapper JAR. Khi dùng wrapper type khác, số files có thể khác; phải revert **cả bộ được sử dụng**, không chỉ sửa một property tùy ý.

### 5.1. Baseline `distributionUrl` ví dụ

Trong `.mvn/wrapper/maven-wrapper.properties`:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.16/apache-maven-3.9.16-bin.zip
~~~

Đây là URL có version cụ thể theo Maven Central artifact layout. Với môi trường doanh nghiệp, có thể dùng approved internal mirror. Trước khi dựa vào URL trong kế hoạch rollback, kiểm **artifact thực tồn tại và SHA-256** bằng nguồn tin cậy, vì network policy có thể chặn public URLs.

### 5.2. Candidate chỉ thay đúng version ở cùng lớp

Khi thử candidate 3.10.0:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.10.0/apache-maven-3.10.0-bin.zip
~~~

**Phải commit bản thay đổi này vào branch/candidate revision riêng.** Không tự sửa file trên toàn bộ shared workspace/CI runner rồi mới tìm cách nhớ version cũ.

Nếu dùng `distributionSha256Sum`, phải cập nhật checksum thật tương ứng từng Maven ZIP. **Không dùng checksum của 3.9.16 cho ZIP 3.10.0**, và không điền một checksum giả chỉ để wrapper chạy.

Maven Wrapper hỗ trợ `distributionSha256Sum` (và `wrapperSha256Sum` khi có wrapper JAR) để kiểm artifact tải về. Đây là một phần của supply-chain safety; rollback cần khôi phục checksum cũ cùng URL cũ.

### 5.3. Tạo Wrapper theo tài liệu Apache

Với project chưa có Wrapper, từ root và Maven installation đủ dùng:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.16 -Dtype=only-script
~~~

Lệnh trên là bước **khởi tạo dự án một lần**, sẽ tạo/cập nhật wrapper scripts/config trong workspace; không chạy trên repository của người khác khi chưa được review. Sau khi tạo, kiểm file diff và commit theo quy trình.

~~~bash
git diff -- mvnw mvnw.cmd .mvn/wrapper/maven-wrapper.properties
./mvnw -version
~~~

Trên Windows, dùng `.\mvnw.cmd -version`. Nếu script `mvnw` chưa có quyền execute trên Linux/macOS, cấp quyền phù hợp trong Git khi phê duyệt setup.

**Không tạo Wrapper bằng version không rõ rồi cho rằng nó tự đoán baseline.** Hãy xác định version và distro URL cụ thể.

### 5.4. Không hardcode credentials vào Wrapper URL

Một URL dạng `https://user:token@repo...` có thể lộ qua commit, logs hoặc exception. Nếu internal repository cần auth, dùng cơ chế credentials được Wrapper hỗ trợ và secret manager của CI theo policy, **không đưa token thật vào `maven-wrapper.properties`**.

## 6. Ba điều kiện để Wrapper thực sự giúp rollback

1. **CI phải gọi Wrapper**, chẳng hạn `./mvnw -B -ntp clean verify`, không gọi system `mvn` vô tình.
2. **Wrapper artifacts phải còn truy xuất được**, kể cả từ isolated runner không có cache Maven cũ.
3. **POM/plugin/JDK/settings phải còn tương thích với distribution được quay lại**.

Nếu một candidate update thay Maven Wrapper 3.9.16 thành 3.10.0 nhưng CI chạy `mvn`, revert URL **không đổi toolchain thực tế**. Nếu CI image đã loại bỏ JDK17 hoặc một plugin được cập nhật yêu cầu Maven4, khôi phục Wrapper đơn thuần **không đủ**.

## 7. Lab Java 17: tạo một chuẩn hành vi không phụ thuộc Maven version

Ta dùng project Maven một module có POM đầy đủ, một class Java và JUnit 5 tests. Mục đích không phải làm Maven version xuất hiện trong Java output, mà là có **đầu ra nghiệp vụ, bytecode baseline và test suite ổn định** để đối chiếu giữa hai Maven distributions.

### 7.1. Cấu trúc thư mục

~~~text
maven-rollback-lab/
├── pom.xml
├── mvnw                      (tạo bằng Maven Wrapper setup)
├── mvnw.cmd                  (tạo bằng Maven Wrapper setup)
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
└── src/
    ├── main/java/com/example/rollback/ReleaseContract.java
    └── test/java/com/example/rollback/ReleaseContractTest.java
~~~

Nếu chưa làm bước Wrapper, **POM + Java sources vẫn build được bằng Maven 3.9+ installed**; chỉ những lệnh `./mvnw` mới cần wrapper scripts đã tạo.

### 7.2. `pom.xml` hoàn chỉnh cho Maven 3.x

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.rollback</groupId>
    <artifactId>maven-rollback-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.jupiter.version>5.11.4</junit.jupiter.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.jupiter.version}</version>
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
                        <id>require-approved-build-tool-line</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                            <fail>true</fail>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Tại sao POM có Enforcer?** Rule `[3.9,4.0)` được chọn để **cả Maven 3.9.16 và Maven 3.10.0** hợp lệ, nhưng một lần vô tình chạy Maven 4 sẽ fail rõ ở `validate`. Rule `[17,)` yêu cầu **JVM chạy Maven** là Java17+. Nó không tự thay JAVA_HOME, không tải JDK và không chứng minh mọi code path runtime đúng.

Các versions plugin được pin thay vì để POM sử dụng defaults khó kiểm soát. JUnit Jupiter scope `test` chỉ cần lúc compile/run tests. **Không có publish/deploy goal** nên lab không gây thay đổi remote repositories.

### 7.3. `ReleaseContract.java`

Tạo `src/main/java/com/example/rollback/ReleaseContract.java`:

~~~java
package com.example.rollback;

public final class ReleaseContract {

    private ReleaseContract() {
    }

    public record Quote(
            long subtotalCents,
            int taxPercent,
            long totalCents) {
    }

    public static Quote quote(long subtotalCents, int taxPercent) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException(
                    "subtotalCents must be non-negative");
        }

        if (taxPercent < 0 || taxPercent > 100) {
            throw new IllegalArgumentException(
                    "taxPercent must be between 0 and 100");
        }

        long taxCents = Math.multiplyExact(
                subtotalCents, (long) taxPercent) / 100;

        long total = Math.addExact(subtotalCents, taxCents);
        return new Quote(subtotalCents, taxPercent, total);
    }

    public static String report(long subtotalCents, int taxPercent) {
        Quote result = quote(subtotalCents, taxPercent);
        return "release-contract=v1; total-cents="
                + result.totalCents();
    }

    public static void main(String[] args) {
        System.out.println(report(10_000, 10));
    }
}
~~~

Đây là một hàm tính tiền **giả lập** trong lab, không phải bộ máy thuế thực tế. Với giá trị tạo số lẻ cent, phép chia integer lấy phần nguyên; sản phẩm tài chính thật phải có chính sách rounding.

**Stdout cố định của `ReleaseContract.main`:**

~~~text
release-contract=v1; total-cents=11000
~~~

Không in số Maven version trong stdout, vì Maven không phải runtime dependency của ứng dụng này. `./mvnw -version` mới là bằng chứng về Maven thực sự dùng để compile/package.

### 7.4. `ReleaseContractTest.java`

Tạo `src/test/java/com/example/rollback/ReleaseContractTest.java`:

~~~java
package com.example.rollback;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReleaseContractTest {

    @Test
    void computesTheExpectedContract() {
        assertEquals(
                new ReleaseContract.Quote(10_000, 10, 11_000),
                ReleaseContract.quote(10_000, 10));
    }

    @Test
    void supportsZeroTax() {
        assertEquals(10_000,
                ReleaseContract.quote(10_000, 0).totalCents());
    }

    @Test
    void rejectsNegativeSubtotal() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> ReleaseContract.quote(-1, 10));

        assertEquals("subtotalCents must be non-negative",
                error.getMessage());
    }

    @Test
    void rejectsInvalidTaxPercentage() {
        assertThrows(IllegalArgumentException.class,
                () -> ReleaseContract.quote(1000, -1));

        assertThrows(IllegalArgumentException.class,
                () -> ReleaseContract.quote(1000, 101));
    }

    @Test
    void runsOnJava17OrNewer() {
        assertTrue(Runtime.version().feature() >= 17);
    }
}
~~~

Có **5 JUnit 5 test methods**. Kỳ vọng ở cả baseline và candidate: năm tests pass. Đây là một mẫu kỹ thuật “golden behavior”, không phải benchmark hiệu năng hay phép chứng minh Maven internals giống nhau.

### 7.5. Build baseline rồi chạy chương trình

Từ `maven-rollback-lab/`, sau khi đã setup wrapper baseline:

~~~bash
./mvnw -version
./mvnw -B -ntp clean verify
java -cp target/classes com.example.rollback.ReleaseContract
~~~

Kỳ vọng:
- `./mvnw -version` báo Apache Maven **3.9.16**.
- Enforcer checks Maven thuộc `[3.9,4.0)` và JDK >=17.
- Compiler tạo bytecode target Java 17.
- Surefire chạy **5 JUnit tests**, không failures/errors/skips.
- JAR tạo ra ở `target/maven-rollback-lab-1.0.0.jar`.
- Java main in chính xác `release-contract=v1; total-cents=11000`.

**Không dùng** `java -jar target/maven-rollback-lab-1.0.0.jar` trong ví dụ này vì POM chưa thiết lập `Main-Class` manifest. Lệnh `java -cp target/classes ...` rõ ràng và đáng tin.

Với Windows:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
java -cp target/classes com.example.rollback.ReleaseContract
~~~

### 7.6. Kiểm bytecode trước/sau nâng cấp

Sau build:

~~~bash
javap -verbose target/classes/com/example/rollback/ReleaseContract.class
~~~

Tìm:

~~~text
major version: 61
~~~

Major version 61 tương ứng Java17 classfile. Với Maven 3.9.16 và 3.10.0, POM đều dùng `maven.compiler.release=17`, nên expectation này không đổi.

**Nhưng** classfile major 61 chỉ là điều kiện về target bytecode; nó không chứng minh mọi artifact bytes giống nhau hoặc toàn bộ dependency graph không đổi. Cần tests, reports và checksum khi thích hợp.

## 8. Thiết lập khả năng rollback ở cấp Git trước khi đổi Wrapper

Lưu một commit/tag baseline theo quy trình repository đã được cấp quyền. Ví dụ, sau khi kiểm working tree sạch:

~~~bash
git status --short
git rev-parse HEAD
git tag --list "buildtools-preupgrade-*"
~~~

Nếu chưa có tag tương tự và team cho phép:

~~~bash
git tag -a buildtools-preupgrade-v1 -m "Known-good Maven build tooling"
~~~

Đây là **ví dụ đặt tên tag**. Không tạo tag trùng, không force-move tag và không tự push tag ra remote khi chưa được owner phê duyệt.

Tag cần trỏ đến commit mà **CI thật** đã pass. Nếu tag chỉ vào một commit local chưa có wrapper scripts/plugin pins thì nó không phải điểm rollback đáng tin.

### 8.1. Upgrade commit phải dễ revert

Một pull request tốt **tách**:
- Wrapper distribution Maven version/checksum.
- CI image/câu lệnh theo wrapper.
- POM/plugins cần thiết cho candidate.
- Maven 4-only changes (nếu có) thành bước sau.

Không gộp một lúc refactor kiến trúc, nâng JDK, thay release repository, đổi plugin và chỉnh nghiệp vụ ứng dụng vào cùng một commit khổng lồ. Khi lỗi xảy ra, người xử lý khó biết revert những thay đổi nào.

**Đường rollback ngắn nhất** là một commit/PR nhỏ chỉ đổi Maven version, với các compatibility fixes tối thiểu. Sau khi thấy candidate ổn định, mới nâng những phần khác thành các lần rollout riêng.

## 9. Dùng hai nhánh hoặc hai worktrees để thử trước và sau

Từ một repository Git đã có baseline/candidate commits, có thể tạo hai worktrees:

~~~bash
git worktree add --detach ../maven-baseline BASELINE_COMMIT
git worktree add --detach ../maven-candidate CANDIDATE_COMMIT
~~~

`BASELINE_COMMIT` và `CANDIDATE_COMMIT` là **chỗ thay bằng commit hashes thật** do reviewer xác nhận. Đây là lệnh cho team sandbox, không phải nội dung để chạy nguyên văn. Worktrees không tự pin JDK hoặc settings; cần đảm bảo hai môi trường dùng cùng chính sách và ghi version.

Tại worktree baseline:

~~~bash
cd ../maven-baseline
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Tại worktree candidate (từ thư mục parent phù hợp):

~~~bash
cd ../maven-candidate
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Khi cả hai có thể build, so JUnit test count, Maven/JDK versions, effective POM, logs, classfile target, JAR contents và các smoke tests.

**Không cho hai worktrees dùng chung `target/` paths**. Chúng có thể dùng chung Maven local repository nếu policies cho phép, nhưng khi cần phân biệt cached plugins/artifacts cũ, dùng Maven local repositories cách ly.

## 10. Isolated Maven local repository giảm việc “laptop tôi pass”

Maven local repository thường ở `${user.home}/.m2/repository`. Nó chứa downloaded dependencies/plugins và những artifacts từng được `mvn install`. Nếu candidate đã tải một plugin mới hoặc build cũ cài internal artifacts, thử rollback trên chính cache đó có thể không đại diện cho runner sạch.

Có thể dùng một location riêng cho test:

~~~bash
./mvnw -B -ntp \
  -Dmaven.repo.local="$HOME/.m2/rollback-sandbox" \
  clean verify
~~~

Đây là lệnh POSIX khi đã có wrapper. PowerShell có thể dùng:

~~~powershell
.\mvnw.cmd -B -ntp `
  "-Dmaven.repo.local=$HOME\.m2\rollback-sandbox" `
  clean verify
~~~

Dùng một local repo riêng cho baseline và một repo khác cho candidate nếu muốn so cold resolution độc lập; khi benchmark performance, warm dependencies trước và giữ đối chứng công bằng.

**Không xóa cả `~/.m2/repository`** để chữa lỗi. Nó có thể chứa dữ liệu của nhiều dự án và credentials/metadata cần xử lý theo chính sách. Không dùng `rm -rf` trên một đường dẫn không được xác minh. Nếu muốn xóa sandbox, xác nhận đó thực sự là directory sandbox và không đang được job khác dùng.

### 10.1. Mirror và plugin repository vẫn phải giống chính sách thực

`-Dmaven.repo.local` chỉ đổi vị trí local repository; nó **không thay** Maven settings, mirrors, active profiles hoặc access đến internal repositories. Nếu test rollback trong môi trường có Internet nhưng production chỉ dùng private mirror, vẫn có rủi ro bản cũ không tải được.

Một rollback rehearsal có giá trị cao phải thử trên runner với **network/ACL tương tự CI thật** và approved artifact repositories.

## 11. Đối chiếu cấu hình effective POM và dependency graph

Với mỗi candidate version, chạy:

~~~bash
./mvnw -B -ntp help:effective-pom
./mvnw -B -ntp dependency:tree
~~~

Đối với multi-module project, có thể dùng `-pl`/`-am` theo reactor graph để lấy phạm vi chính xác. Ghi lại:
- Plugins có version và executions gì sau inheritance.
- Java source/target/release, test plugin, Failsafe config.
- Active profiles và parent/BOM versions.
- Repositories/mirrors được cấu hình và nơi dependency resolve.
- Internal plugins/extensions có tương thích Maven candidate hay không.
- Annotation processor versions và toolchain JDK requirements.

**Đừng so effective POM bằng cách xuất toàn bộ settings có credentials ra issue công khai.** `help:effective-settings` và `mvn -X` có thể đưa thông tin nhạy cảm vào logs; cần redact/limit quyền.

### 11.1. Không nâng Maven và plugins hàng loạt một cách vô thức

Apache Maven 4 migration guide khuyến nghị nâng plugins lên các phiên bản còn tương thích Maven 3 trước, rồi thử Maven 4, sau đó mới dùng những features chỉ có Maven 4. Một plugin phiên bản mới có thể **yêu cầu Maven core cao hơn** và làm rollback core không còn chạy được.

Khi thấy:

~~~text
The plugin requires Maven version 4.x
~~~

trong một project cần fallback Maven 3, **đừng bỏ qua** bằng cách hạ Enforcer rule hoặc skip goal. Quay lại plugin compatible và thực hiện nâng core/plugin theo hai bước có gates.

## 12. Canary rollout: giới hạn phạm vi sự cố

Không mở candidate đồng thời cho toàn công ty. Chia đợt:

| Giai đoạn | Đối tượng | Tiêu chí đi tiếp |
| --- | --- | --- |
| 0. Baseline | CI hiện hành | Known-good pass, reports đã giữ |
| 1. Sandbox | Repo lab và vài dự án ít rủi ro | Maven candidate + clean verify pass |
| 2. Dual CI | Baseline và candidate chạy song song | Test/artifact/phase đối chiếu rõ |
| 3. Canary | Nhóm nhỏ/one CI runner pool | Không có regression theo gate/quan sát |
| 4. Broader adoption | Nhiều modules/repos hơn | Lịch rollback, owner, metrics sẵn |
| 5. Default | Toàn bộ supported workflows | Approval, audit, review retention |

**Không dùng mặc định mọi CI jobs ngay khi bản candidate pass một project lab.** Maven ecosystem gồm multi-module Reactor, JUnit/Surefire/Failsafe, compiler, plugins tự viết, credentials, deploy, codegen và hệ thống publish; mỗi nhóm cần kiểm riêng.

### 12.1. Những dự án nên chọn cho canary

- Một JAR Java đơn giản.
- Một multi-module Reactor có parent/BOM/pluginManagement.
- Project dùng integration tests/Failsafe.
- Project có annotation processors/codegen.
- Project dùng internal Maven plugins/extensions.
- Project có Maven Toolchains/JDK matrix.
- Project có signing/release staging policy.
- Project cần plugin không tương thích tốt với Maven major mới.

Chọn đại diện giúp phát hiện regression sớm; không nhất thiết đưa các job có quyền publish production vào đợt thử đầu tiên.

## 13. CI workflow: gọi Wrapper và giữ khả năng phục hồi

Ví dụ GitHub Actions khi source demo nằm ở repository root và Wrapper scripts đã được commit:

~~~yaml
name: Maven upgrade verification

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21']

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Select test JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven

      - name: Record actual build tooling
        run: |
          java -version
          javac -version
          ./mvnw -version

      - name: Verify Maven build
        run: ./mvnw -B -ntp clean verify
~~~

Workflow này sẽ dùng Maven distribution từ `.mvn/wrapper/maven-wrapper.properties` của **commit được checkout**. Vì vậy baseline branch và candidate PR branch có thể chạy cùng cấu trúc workflow mà nhận Maven versions khác nhau.

**Điều kiện để gọi là dual validation:** cần chạy baseline và candidate revisions trên các CI jobs/PR checks riêng, cùng inputs/test suites tương ứng; **một job matrix chỉ thay Java version không tự đồng thời kiểm hai Maven versions**.

### 13.1. Pin tool image và actions theo policy

Với supply-chain controls nghiêm ngặt, pin GitHub Actions bằng immutable commit SHA và CI images bằng digest đã được phê duyệt. Các tags trong ví dụ là minh họa dễ đọc; chính sách tổ chức có thể yêu cầu pin chính xác hơn.

Nếu runner upgrade làm hệ điều hành hoặc JDK thay đổi đồng thời, khó quy lỗi cho Maven. Đợt canary nên giữ các biến khác ổn định, rồi thử thêm OS/JDK matrix ở bước riêng.

### 13.2. CI không được bỏ qua tests để candidate trông xanh

Không chấp nhận:

~~~bash
./mvnw -DskipTests -Dmaven.test.skip=true clean package
~~~

làm bằng chứng tương đương với baseline `clean verify` có tests. Skip flags thay đổi tiêu chí chất lượng. Tương tự, `-fn` (fail never) có thể làm exit status không phản ánh failures đúng yêu cầu.

Với một release gate, chạy cả unit/integration/security checks cần thiết theo policy, lưu reports, không chỉ đọc dòng `BUILD SUCCESS`.

## 14. Gate để quyết định tiếp tục, dừng hay quay lại

Một upgrade cần **rollback triggers** được định nghĩa trước khi có sự cố:

| Gate | Đo cái gì | Tín hiệu dừng/rollback |
| --- | --- | --- |
| Tool identity | `./mvnw -version` theo revision | Sai Maven distribution/Wrapper URL/checksum |
| Java baseline | JDK, `maven.compiler.release`, bytecode | Classfile target hoặc JDK requirement không phù hợp |
| Build correctness | `clean verify` exit status | Fail mới ở candidate, baseline pass |
| Tests | Surefire/Failsafe tests count/errors/skips | Tests mất, fail hoặc bị skip ngoài policy |
| Reactor | Build full modules và `-pl -am` | Dependency ordering/resolution regression |
| Plugin compatibility | Compiler, Surefire, shading, codegen, plugins nội bộ | Goal/metadata/API không tương thích |
| Artifact integrity | JAR/POM contents, metadata/checksum | Nội dung thay đổi bất ngờ, không giải thích được |
| Performance | Wall time, memory, CPU, cache | Regression vượt ngưỡng tổ chức đặt |
| CI environment | Runner/JDK/image/tools available | Candidate chỉ pass trên laptop |
| Staging deploy | Approved test repository, credentials | Sai đích upload hoặc lỗi ACL/signing |
| Security/compliance | SBOM/signatures/scans | Bước kiểm bị thiếu hoặc bypass |
| Recoverability | Thử quay lại và chạy baseline | Không thể quay lại và verify trong điều kiện thử |

**Không đưa ngưỡng hiệu năng hay SLA tùy ý** như “chậm hơn 5% thì rollback” mà không có số liệu hiện trạng, traffic và business risk. Owner cần xác lập ngưỡng trước rollout, có metrics để kiểm.

### 14.1. Phân loại lỗi trước khi rollback

Một job fail vì remote Maven Central/Artifactory bị outage không nhất thiết do Maven candidate. Nhưng nếu candidate dùng HTTP transport khác hoặc resolution semantics thay đổi, lỗi có thể do phiên bản. So logs baseline/candidate trên cùng environment, đọc root cause thay vì quy hết cho network.

Nếu artifact reproducibility checksum khác, kiểm compiler/JDK/plugins/timestamps/dependencies. **Checksum khác không luôn là Maven regression**, nhưng là lý do phải dừng publish cho đến khi giải thích được.

## 15. Diễn tập rollback ngay trong sandbox

Một rehearsal đúng nên được thực hiện **trước khi mở rollout rộng**:

**Bước A — tạo baseline ổn định:**

~~~bash
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Lưu report Maven 3.9.16, JDK, JUnit 5 tests, JAR và output của `ReleaseContract.main`.

**Bước B — thử candidate ở branch/commit khác:**

Trong candidate revision có wrapper URL 3.10.0:

~~~bash
./mvnw -version
./mvnw -B -ntp clean verify
java -cp target/classes com.example.rollback.ReleaseContract
~~~

Kỳ vọng CLI là 3.10.0 và app vẫn in chính xác:

~~~text
release-contract=v1; total-cents=11000
~~~

**Bước C — mô phỏng trigger rollback:** một plugin nội bộ không tương thích candidate, test regression hoặc gate bắt buộc fail. Trong lab không cần chủ động phá code hay bỏ kiểm bảo mật để chứng minh lỗi.

**Bước D — khôi phục baseline revision/configuration** (qua branch/worktree hoặc revert change-set được phê duyệt), không sửa Maven global installation của mọi developer.

**Bước E — kiểm trên runner sạch/cấu hình giống CI:**

~~~bash
./mvnw -version
./mvnw -B -ntp clean verify
java -cp target/classes com.example.rollback.ReleaseContract
~~~

Phải thấy Maven 3.9.16, 5 tests pass và stdout nghiệp vụ giống baseline.

**Bước F — kiểm không có side effects ngoài sandbox**: không upload artifact nhầm vào production repository, không thay release tags, không sửa global settings/secrets.

Nếu bước E không chạy được vì Maven distribution cũ đã mất khỏi approved mirror, kế hoạch rollback **chưa sẵn sàng**, dù Git revert thực hiện được.

## 16. Runbook rollback khi candidate gây regression

Một runbook ngắn nhưng dùng được trong sự cố:

### 16.1. Điều kiện kích hoạt

- Có một gate P0/P1 hoặc lỗi ảnh hưởng release pipeline khiến tiếp tục candidate không an toàn.
- Baseline trước upgrade vẫn có evidence known-good.
- Người chịu trách nhiệm có quyền dừng rollout, revert repo/config và liên hệ owners khác.
- Đã xác định phạm vi môi trường bị ảnh hưởng và actions đã xảy ra (build/test/install/deploy).

### 16.2. Trình tự thực thi

1. **Dừng mở rộng rollout** và tạm khóa/suspend các jobs có quyền publish nếu nguy cơ phát hành sai artifact.
2. **Thông báo chủ sở hữu CI/repository** về lỗi, thời điểm, ảnh hưởng và quyết định rollback.
3. **Chốt commit candidate + logs/evidence** (không lưu secrets) để điều tra; không xóa dấu vết trước.
4. **Khôi phục Wrapper version, checksum và scripts** về baseline approved revision.
5. **Khôi phục CI image/JDK/Maven invocation**, xác nhận jobs dùng `./mvnw` thay vì system `mvn`.
6. **Khôi phục POM/plugins/extensions/settings config** nếu thay đổi trong upgrade không tương thích bản cũ.
7. **Chạy một clean verify trong isolated/known-clean environment** có access đến baseline dependencies/artifacts.
8. **Kiểm unit/integration/smoke gates và artifact contents**; xác minh JUnit tests thực sự chạy.
9. **Khôi phục CI required checks** về status/hình thức phê duyệt ban đầu; không bỏ gates để nhanh đạt xanh.
10. **Kiểm các jobs staging/release đã chạy**: artifacts được upload, tọa độ GAV, signatures/checksum, audit.
11. **Theo dõi builds kế tiếp** để phát hiện plugin cache/runner lệch version hoặc regressions khác.
12. **Đóng sự cố và mở lại rollout** chỉ khi root cause/fix có owner và một rollout mới được phê duyệt.

### 16.3. Các lệnh kiểm sau rollback

Trên POSIX:

~~~bash
git rev-parse HEAD
git status --short
./mvnw -version
java -version
./mvnw -B -ntp clean verify
java -cp target/classes com.example.rollback.ReleaseContract
~~~

`git status --short` phải cho biết working tree có thay đổi nào, nhưng một tree dirty không tự giải thích vì sao; không tự xóa file untracked. Nếu CI sử dụng checkout sạch, expected thường là tree sạch ngoài build outputs được `.gitignore`.

### 16.4. Cách revert commit thay đổi

Nếu candidate là một commit Git riêng trên shared branch, người có quyền có thể dùng:

~~~bash
git revert CANDIDATE_COMMIT
~~~

`CANDIDATE_COMMIT` là commit hash thật cần chọn sau khi xem dependency của các commits. Lệnh tạo **một commit đảo thay đổi**. Nó không tự rollback runner images, Maven installation toàn máy, tokens hay remote artifacts.

**Không dùng `git reset --hard` hoặc force-push lên shared branches như bước rollback mặc định.** Chúng có thể phá lịch sử/công việc của người khác. Khi candidate gồm nhiều commits, review thứ tự và tạo revert PR có CI checks; đừng copy một dòng `git revert` nếu thay đổi đã trộn với feature code.

Nếu upgrade mới nằm ở candidate branch chưa merge, cách đơn giản có thể là **đóng PR và giữ default branch ở baseline**, thay vì revert những gì chưa được áp dụng.

## 17. Rollback container/CI image không thể chỉ dùng `mvnw`

Một số tổ chức không dùng Maven Wrapper trong production CI. Họ dùng:

~~~text
CI image: registry.example.invalid/build/maven-java17@sha256:<digest>
Command: mvn clean verify
~~~

Ở mô hình này, Maven version thuộc Docker image/tool installation, không thuộc repository wrapper. Chuỗi `<digest>` chỉ là placeholder, **không phải digest dùng được**.

Để rollback:
- Ghi exact image tag **và immutable digest** (khi registry hỗ trợ).
- Giữ baseline image trong retention policy.
- Cập nhật job template để pin lại digest cũ.
- Đảm bảo runner vẫn được phép pull image.
- Kiểm `mvn -version` bên trong chính container.
- Không trộn JDK mới vào baseline image khi mục tiêu chỉ rollback Maven.

Nếu hệ thống dùng Maven Toolchains Plugin, có thể **Maven process chạy JDK17 nhưng Compiler/Surefire dùng JDK21**. Runbook phải kiểm cả Maven launcher và toolchain/test JVM, không coi `java -version` một mình là bằng chứng đầy đủ.

## 18. Maven 4: vì sao kế hoạch rollback phức tạp hơn

Theo [Maven 4 migration guide](https://maven.apache.org/guides/mini/guide-migration-to-mvn4), lộ trình an toàn là:

1. **Prepare:** dùng Maven 3.9 gần nhất được hỗ trợ và plugin versions tương thích Maven 3.
2. **Test:** thử Maven 4 song song, sửa những vấn đề tương thích tối thiểu **vẫn giữ POM build được trên Maven 3**.
3. **Migrate:** chỉ sau khi quyết định bỏ Maven 3 mới bật các đặc tính Maven 4-only.

**Lời khuyên rollback:** duy trì một cửa sổ **dual compatibility** trước khi áp dụng POM4-only changes. Nếu ngay trong ngày đầu đổi cả Maven core, modelVersion 4.1.0, `<subprojects>`, plugin APIs và default deploy semantics, rollback không chỉ là đổi `distributionUrl`.

### 18.1. Maven 4 yêu cầu JDK 17 để chạy Maven

Maven 3.x có thể chạy trên nhiều JDK theo version constraints của từng release; Maven 4 yêu cầu Java17+. Trước khi canary Maven 4, phải đảm bảo developer/CI môi trường có Java17+.

Khi rollback về Maven3, **không tự buộc quay lại Java8** nếu project đã dựa vào Java17 và plugin/toolchain khác đã nâng. Core/JDK phải được kiểm theo compatibility matrix thực, không đoán từ tên phiên bản.

### 18.2. POM model 4.1.0 là rào cản với Maven3

Maven 4 có những feature mới yêu cầu `<modelVersion>4.1.0</modelVersion>` hoặc cấu trúc chuyên biệt. Maven 3 không hiểu POM4-only model theo cùng semantics. Nếu source đã dùng Maven4-only constructs, rollback core về Maven3 **phải đi kèm revert POM** về state 4.0.0 compatible.

Một ví dụ thay đổi mô hình (chỉ là snippet):

~~~xml
<!-- Maven 3 compatible -->
<modelVersion>4.0.0</modelVersion>
<modules>
    <module>api</module>
    <module>app</module>
</modules>
~~~

Maven 4 có thể dùng model4.1.0 và `<subprojects>` thay `<modules>` trong bối cảnh phù hợp. **Không lẫn các fragments này vào POM demo** trước khi muốn bỏ đường rollback Maven3.

### 18.3. Thay đổi default install/deploy at end

Maven 4 thay default `installAtEnd` và `deployAtEnd` thành `true` ở plugin tương ứng theo migration guide. Với một release pipeline dựa vào artifact được install/deploy ở thời điểm cũ, sự khác nhau có thể ảnh hưởng Reactor lifecycle và consumers.

Trước migration:
- Xem configuration plugin explicit/inherited.
- Test Reactor `install`/`deploy` trong **staging** có kiểm soát.
- Không dùng production repository để chứng minh rollback.
- Không dựa vào publish artifact đã có và immutable GAV.
- Khi cần, ghi explicit behavior compatible với phiên bản được test và review.
- Không tự sửa `installAtEnd` chỉ để khớp log nếu thiết kế project đang lỗi.

### 18.4. `settings-security4.xml` và plugin API

Maven 4 có cơ chế secret encryption/configuration mới; migration giữa Maven3 `settings-security.xml` và Maven4 cần kế hoạch riêng. Nếu rollback mà credentials không còn đọc được, build/publish có thể fail dù source tương thích.

Một số plugin internal dùng Maven APIs cũ có thể hoạt động khác. Vì vậy:
- Kiểm internal plugins/extensions trước canary.
- Giữ versions Maven3 compatible cho đường quay lui.
- Không ghi credentials thật vào Git để vượt lỗi cấu hình.
- Kiểm settings/mirrors/servers bằng protected configuration snapshots.

## 19. Những thành phần không được “rollback” theo cách thiếu kiểm soát

### 19.1. Immutable artifact repository

Một version Maven artifact như:

~~~text
com.example:payment-api:1.0.0
~~~

được publish với bytes cụ thể. Nếu candidate build tạo JAR khác, **không ghi đè cùng version** chỉ để quay về bytes cũ. Releases phải tuân thủ immutability và retention rules của repository.

Nếu artifact đã publish sai:
- Dừng pipeline/consumer promotion.
- Xác định GAV, checksum, signature và thời gian publish.
- Làm theo chính sách quarantine/revoke/deprecation của repository.
- Nếu cần artifact mới, phát hành **version mới**.
- Thông báo consumers đã tải bản bị ảnh hưởng.

Rollback Maven toolchain chỉ ảnh hưởng **những builds tiếp theo**; nó không tự sửa artifact đã phân phối.

### 19.2. Database/application migrations

Nếu nâng build tool kéo theo đổi application schema, config hoặc runtime deployment, phải có **application rollback** riêng, bao gồm data migration compatibility, backups và release orchestrator. Maven không có khả năng tự hoàn nguyên database hay container deployments.

### 19.3. Credentials/secrets

Không lấy `settings.xml` từ laptop của một developer rồi copy vào CI như “rollback credentials”. Dùng secret store/config management với permissions/versions đã phê duyệt. Trong incident, token hết hạn hoặc bị revoke phải được cấp lại theo quy trình; revert commit không khôi phục secret đúng cách.

## 20. “Thử rollback” không có nghĩa xóa các caches dùng chung

Sau nâng cấp, local Maven repository, Maven Wrapper distributions và caches có thể chứa:
- Maven binaries cũ/mới.
- Plugin versions đã tải.
- Dependency SNAPSHOT metadata khác nhau.
- Maven extensions và artifact resolution state.
- Build cache outputs theo input keys.
- Temporary generated files dưới `target`.

**Không xóa bừa `~/.m2`** hoặc tắt security checks để làm baseline pass. Dùng isolated caches/test worktrees cho diagnosis. Nếu nghi build cache gây stale output, tắt cache read cho validation hoặc dùng sandbox khác, rồi so với clean build.

### 20.1. Cache không thay kiểm nghiệm trên runner sạch

Một lần rollback pass nhờ local caches có thể thất bại khi team dùng runner mới. Trước rollout rộng, hãy xác nhận:
- Maven3 baseline distribution tải được từ approved mirror.
- Plugins/JUnit/dependencies resolve được với settings policy.
- Java17 toolchain còn hoạt động.
- Clean verify và integration tests chạy đủ.
- Không dùng cached test reports cũ làm kết quả của lần chạy hiện tại.
- Remote cache chia theo trust/correctness policy, không dùng cache poisoned từ untrusted CI jobs.

## 21. Kế hoạch nâng cấp có thể đảo ngược theo từng giai đoạn

### 21.1. Giai đoạn 0: inventory

Ghi: source revision, wrapper URL/version/checksum, Maven/JDK/plugin versions, settings/mirrors, required CI checks, build images, deploy workflows, local/remote caches. Owner review và xác nhận baseline.

### 21.2. Giai đoạn 1: candidate branch

Thay **một lớp quan trọng** (ở lab là Wrapper Maven 3.9.16 → 3.10.0). CI candidate chạy cùng POM/source/test suite. Không bật deploy production.

### 21.3. Giai đoạn 2: dual validation

Baseline và candidate builds song song trên hai revisions/runner pools. So outputs, duration, test counts, artifact contents, dependency graph, plugin logs, JVM versions và security checks.

### 21.4. Giai đoạn 3: rollback rehearsal

Chủ động thực hiện một lượt quay về baseline revision/config, không cần chờ candidate lỗi. Đảm bảo old distro vẫn tải được và 5 tests lab cùng representative project tests pass.

### 21.5. Giai đoạn 4: canary

Áp candidate cho một nhóm jobs/developers ít rủi ro. Giữ đường quay về bằng Wrapper/pinned images và giữ required checks. Theo dõi thời gian đủ để bắt các jobs hiếm chạy (weekly/release).

### 21.6. Giai đoạn 5: rollout có kiểm soát

Tăng phạm vi từng đợt theo gate, có owner và quyền dừng. Không đổi default image cho toàn bộ org trước khi có rollback runbook.

### 21.7. Giai đoạn 6: đóng cửa sổ rollback sau khi đủ điều kiện

Khi candidate được phê duyệt làm baseline mới:
- Cập nhật runbook, retention và CI templates.
- Có thể giảm giữ Maven cũ sau thời hạn policy, **không xóa ngay nếu projects còn phụ thuộc**.
- Với Maven4 migration, chỉ sử dụng POM4-only features khi đã chấp nhận kết thúc compatibility window với Maven3 và có release/roll-forward policy.

## 22. Troubleshooting khi rollback thất bại

| Triệu chứng | Nguyên nhân thường gặp | Hướng giải quyết |
| --- | --- | --- |
| Revert Wrapper nhưng CI vẫn chạy 3.10.0 | Job gọi system `mvn`, không gọi `./mvnw` | Sửa CI invocation hoặc image |
| `./mvnw -version` không tải được Maven3 | Old ZIP không còn ở mirror, URL blocked | Approved mirror/retention, checksum |
| Wrapper báo checksum mismatch | URL và `distributionSha256Sum` lệch | Khôi phục cặp version/checksum đáng tin |
| Maven3 không đọc POM sau Maven4 migration | Model4.1.0/features mới còn trong Git | Revert POM4-only changes cùng core |
| Maven3 báo plugin yêu cầu Maven4 | Plugin đã nâng và không rollback | Pin bản plugin Maven3 compatible |
| `mvn verify` fail, Wrapper pass | Toolchain/JDK/Enforcer mismatch | Kiểm `./mvnw -version`, POM, JAVA_HOME |
| Unit tests không chạy | Skip flags/cache policy/CI config | Required clean verify không skip |
| CI pass nhưng production consumer lỗi | Runtime/dependency/packaging paths không được test | Consumer integration/smoke tests |
| JAR checksum khác baseline | JDK/plugins/timestamps/deps thay | Diff outputs, reproducible build check |
| `Could not resolve plugin` | Repo mirror/credentials/cache khác | Kiểm approved repositories và access |
| Staging deploy fail 401/403 | Settings server ID/token scope sai | Protected settings/auth diagnostics |
| Maven4 cũ/nouveau local repo state làm lệch build | Cache/resolution state bị lẫn | Isolated local repo cho kiểm nghiệm |
| `git revert` gây conflicts | Candidate commits trộn với feature fixes | Review dependency commits, revert PR |
| CI image cũ bị xóa | Registry retention không giữ digest | Rebuild approved baseline image hoặc roll forward |
| Release GAV đã publish sai | Không thể overwrite immutable version | Quarantine/notice/new version theo policy |
| Tests pass local, fail runner sạch | Caches hoặc environment ẩn | Reproduce isolated runner, pin versions |
| `UnsupportedClassVersionError` | Build bytecode vượt Java runtime | Compiler release/JDK matrix |
| Failsafe IT khác baseline | Profile/phase/CI service difference | Test integration environments và reports |
| Maven4 root discovery khác Maven3 | Build root/module semantics thay | Review subprojects/root paths theo version |
| 3.9.16 bản cũ không còn được org hỗ trợ | Internal support window kết thúc | Chọn rollback target approved khác hoặc roll forward |
| Secrets xuất hiện trong logs | Debug/CI env leaks | Stop logs, revoke/rotate, incident response |

## 23. Một cách kiểm artifact dễ tái tạo

Ở lab Java17:

~~~bash
./mvnw -B -ntp clean verify
jar tf target/maven-rollback-lab-1.0.0.jar
java -cp target/classes com.example.rollback.ReleaseContract
~~~

Khi cần so JAR:
- Ghi checksum SHA-256 bằng công cụ OS phù hợp (`sha256sum` trên nhiều POSIX systems hoặc `Get-FileHash` PowerShell).
- So cả POM, manifest, compiled classes và generated resources nếu business contract yêu cầu.
- Xem `project.build.outputTimestamp` và plugin versions khi muốn kiểm reproducible archive.
- Không coi byte-for-byte equality là mặc định khi toolchains/JDK versions khác nhau.

Ví dụ trên PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 target/maven-rollback-lab-1.0.0.jar
~~~

Trên Linux:

~~~bash
sha256sum target/maven-rollback-lab-1.0.0.jar
~~~

**Không tự ghi checksum giả vào checklist.** Giá trị thực phải được lấy từ build và được giữ cùng commit/toolchain metadata.

### 23.1. Reproducible builds khác functional equivalence

Hai builds có thể cùng chạy 5 tests và cho cùng stdout nhưng JAR bytes vẫn khác do timestamps, plugin behavior, manifest hoặc generated files. Ngược lại, JAR bytes giống nhau không chứng minh integration tests trên database thật cũng chạy đúng.

Theo hướng dẫn Apache Maven, có thể dùng `project.build.outputTimestamp` và Maven Artifact Plugin `artifact:compare` để xem khả năng tái tạo, với môi trường được kiểm soát. Không ép một project đạt checksum giống nhau trên hai JDKs nếu build contract chưa yêu cầu binary reproducibility; dùng tiêu chí functional/security/integrity phù hợp và giải thích differences.

## 24. Một “rollback drill” có báo cáo hoàn chỉnh gồm gì?

Mẫu báo cáo cho team build:

~~~text
UPGRADE RUN: MAVEN-2026-EXAMPLE

Baseline:
  Git revision: <known-good commit>
  Maven Wrapper: 3.9.16
  JDK: 17
  POM plugins: pinned/approved
  CI checks: all required green

Candidate:
  Git revision: <upgrade commit>
  Maven Wrapper: 3.10.0
  Scope: sandbox + canary
  CI checks: statuses and links retained

Rollback rehearsal:
  Trigger: simulated build regression
  Action: revert candidate wrapper/config commit
  Restored Maven: 3.9.16 (verified by ./mvnw -version)
  Clean verify: PASS
  JUnit: 5 tests, 0 failures
  Application stdout: release-contract=v1; total-cents=11000
  Remote releases changed: none
  Owner/approver: recorded in internal runbook
~~~

Các dòng `<known-good commit>`, `<upgrade commit>` là **mẫu trường báo cáo**, không phải giá trị có sẵn. Khi điền thật, dùng commit hashes, CI job IDs, log links và times đã xác minh; không tự cho “PASS” nếu chưa chạy.

### 24.1. Những chi tiết cần có trong decision record

- Lý do nâng Maven và rủi ro được mong đợi.
- Danh sách affected repos/modules/runners/deploy paths.
- Baseline và candidate versions, release notes, compatibility.
- Phạm vi canary và owner/approver.
- Chính sách artifact immutability/staging.
- Objective gate thresholds và observation window.
- Hành động rollback chính xác và môi trường chạy.
- Evidence một lượt rollback rehearsal đã pass.
- Lựa chọn roll-forward nếu rollback không thể vì schema/toolchain irreversible.
- Security signoff, incident contacts và ngày re-evaluation.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Có `git tag` baseline là đã sẵn sàng rollback chưa?

**Đáp:** Chưa. Maven binary/Wrapper, JDK, plugins, CI image, settings/repositories và tests cần vẫn có thể phục hồi và chạy trên môi trường thật.

**Câu 2.** Sửa lại `distributionUrl` có khôi phục Maven version trong mọi CI job không?

**Đáp:** Không nếu CI gọi system `mvn` thay vì Maven Wrapper, hoặc CI image/tool installation override.

**Câu 3.** Vì sao phải thử tải Maven distribution cũ từ approved mirror?

**Đáp:** Rollback không thực hiện được nếu old version đã bị xóa, chặn network hoặc checksum không khớp.

**Câu 4.** Maven 3.9.16 và 3.10.0 có phải cùng Maven major không?

**Đáp:** Có. Chúng là hai releases của Maven 3, phù hợp để minh họa một nâng cấp có đường quay lui ít phá vỡ hơn Maven4 migration.

**Câu 5.** Tại sao không nâng JDK, plugins, POM4.1.0 và Maven core cùng một commit?

**Đáp:** Khó phân định regression và khó revert riêng; tốt hơn tách thành phases/gates có thể kiểm.

**Câu 6.** `mvn -version` và `./mvnw -version` có luôn giống nhau không?

**Đáp:** Không. System Maven phụ thuộc PATH/tool installation; Wrapper chọn distribution dựa vào project config.

**Câu 7.** Có thể rollback Maven core mà vẫn giữ POM model4.1.0 không?

**Đáp:** Không đối với Maven3 nếu POM đã dùng features chỉ Maven4 hỗ trợ. Cần revert POM hoặc có nhánh tương thích.

**Câu 8.** Maven4 yêu cầu runtime Java tối thiểu nào?

**Đáp:** Java17 theo migration guide ở thời điểm viết.

**Câu 9.** `git revert` có hoàn nguyên artifacts đã publish lên repository không?

**Đáp:** Không. Nó đảo changes trong Git; remote artifacts cần policy xử lý riêng.

**Câu 10.** Nếu plugin mới đòi Maven4, có thể chỉ hạ Wrapper về Maven3 không?

**Đáp:** Không. Cần pin plugin compatible và xác nhận effective POM.

**Câu 11.** Lần chạy lab baseline nên có bao nhiêu JUnit tests?

**Đáp:** Năm JUnit 5 test methods, cùng stdout Java đã định nghĩa.

**Câu 12.** Có nên xóa `~/.m2/repository` khi quay lui để “sạch” không?

**Đáp:** Không xóa bừa. Dùng isolated local repository/runner để test cold resolution.

**Câu 13.** `cache: maven` trong GitHub Actions có tự chứng minh rollback thành công không?

**Đáp:** Không. Nó chủ yếu cache dependencies; phải verify Maven version, test execution và artifacts.

**Câu 14.** “Candidate CI xanh” có đồng nghĩa có thể mở toàn công ty không?

**Đáp:** Chưa. Cần canary, dual validation, rollback rehearsal và representative projects.

**Câu 15.** Vì sao cần giữ JDK/plugin versions cùng baseline?

**Đáp:** Các phiên bản ấy ảnh hưởng tính tương thích và output; chỉ quay Maven mà đổi quá nhiều variables làm mất baseline.

**Câu 16.** Checksum SHA-256 khác có luôn chứng minh candidate sai không?

**Đáp:** Không luôn. Cần kiểm timestamps, toolchain, plugin và artifact contents; nhưng differences không giải thích được phải chặn phát hành.

**Câu 17.** `-DskipTests` có chấp nhận làm bằng chứng phục hồi không?

**Đáp:** Không khi tests là required gate. Bằng chứng phải thực thi đầy đủ suite theo policy.

**Câu 18.** Có thể override một release GAV bằng JAR cũ để rollback không?

**Đáp:** Không trong quy trình immutable Maven releases. Dùng quarantine/new version và thông báo theo policy.

**Câu 19.** CI pipeline dùng Docker Maven image nên rollback ở đâu?

**Đáp:** Quay image/tool installation về digest/version cũ và kiểm `mvn -version` trong container, không chỉ chỉnh Wrapper.

**Câu 20.** Khi nào có thể tuyên bố “Rollback-ready”?

**Đáp:** Khi baseline đã được định nghĩa, binary/settings/CI access còn dùng được, đã chạy **một rollback rehearsal trên môi trường gần production** với full required checks pass, có owner và runbook rõ ràng.

## 26. Checklist trước khi rollout trên diện rộng

1. Xác định lý do nâng Maven và affected workflows.
2. Ghi exact baseline và candidate Maven versions.
3. Xác nhận Maven candidate là GA hay release candidate.
4. Pin approved JDK và verify Maven runtime JDK.
5. Ghi Git commit/tag baseline từ CI pass thật.
6. Kiểm repository sạch và change-set nhỏ, dễ revert.
7. Có Maven Wrapper hoặc CI image/toolchain pin rõ version.
8. Kiểm `distributionUrl` trỏ chính xác Maven ZIP.
9. Xác minh `distributionSha256Sum` bằng nguồn tin cậy nếu áp dụng.
10. Giữ wrapper scripts tương ứng phiên bản/types đã dùng.
11. Chứng minh CI chạy `./mvnw` hoặc pinned image đúng.
12. Old Maven distribution còn có thể tải trên runner sạch.
13. Baseline plugin versions còn Maven-compatible.
14. Không nhập Maven4-only POM features khi cần fallback Maven3.
15. Parent/BOM/pluginManagement được kiểm qua effective POM.
16. Ghi Maven/JDK/plugin/extension versions và active profiles.
17. Kiểm `settings.xml`/mirrors/servers qua protected configuration.
18. Không lưu credentials hay private signing key trong baseline logs.
19. CI workflow có unit/integration tests đầy đủ, không skip.
20. Baseline JAR/POM/checksum và source revision được giữ.
21. Dùng local repositories cách ly khi nghi cached state.
22. Có full Reactor validation cho projects đa module.
23. Có test cho internal Maven plugins/extensions.
24. Kiểm Toolchains/compiler/test JVM khi chạy nhiều JDK.
25. Giữ secret/repository permissions ở mức tối thiểu.
26. Không publish candidate vào production trong sandbox phase.
27. Có staging repository riêng cho deploy rehearsal nếu cần.
28. Có canary projects đại diện và scope được định nghĩa.
29. Có rollback triggers/thresholds dựa trên dữ liệu.
30. Có owner/approver và communication channel.
31. Tách Maven core, plugin, JDK, image và POM migrations.
32. Có một lần **thực hiện quay lại baseline** thành công.
33. Rollback test dùng clean build/isolated environment.
34. Sau rollback, `./mvnw -version` đúng baseline.
35. Sau rollback, tests count/failures đúng như đã chấp nhận.
36. Sau rollback, Java output và critical contracts không đổi.
37. Xác minh published release GAVs không bị ghi đè.
38. Có kế hoạch ứng phó với artifacts sai đã phát hành.
39. Không dùng force push/reset destructive cho shared branches.
40. Có retention Maven binary/CI image và artifact dependencies.
41. Có rollback steps cho settings/extensions được triển khai ngoài Git.
42. Không tự xóa Maven global cache hoặc local artifacts bừa bãi.
43. Có khả năng chọn roll-forward khi external changes irreversible.
44. Có báo cáo evidence và root-cause review sau canary.
45. Chỉ thay đổi default toàn tổ chức khi đã đạt đủ gate.

## 27. Tài liệu tham khảo chính thức

- [Apache Maven — Releases History](https://maven.apache.org/docs/history)
- [Apache Maven — Starting with Maven 4 (migration guide)](https://maven.apache.org/guides/mini/guide-migration-to-mvn4.html)
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/wrapper/)
- [Apache Maven Wrapper Plugin — Usage](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html)
- [Apache Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Apache Maven — Build Lifecycle (package, install, deploy)](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Maven Enforcer Plugin `requireMavenVersion`](https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html)
- [Apache Maven — Maven Enforcer Plugin `requireJavaVersion`](https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html)
- [Apache Maven — Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Apache Maven — Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Apache Maven — Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [GitHub — actions/setup-java](https://github.com/actions/setup-java)
- [JUnit 5 — User Guide](https://docs.junit.org/5.11.4/user-guide/)

