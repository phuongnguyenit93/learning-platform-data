
# Thực hiện nâng cấp JDK theo giai đoạn với kiểm thử và phương án quay lui

Nâng cấp Java trong hệ thống đang vận hành không chỉ là thay `JAVA_HOME` hoặc đặt một JDK mới trong Dockerfile. Một thay đổi JDK có thể tác động compiler, class-file version, framework, dependencies, TLS, charset, garbage collection (GC), JPMS, native libraries và quá trình triển khai nhiều phiên bản cùng lúc. Hệ thống có thể **build thành công nhưng fail khi khởi động**, hoặc **khởi động được nhưng gây lỗi khi đọc dữ liệu của phiên bản cũ**. Nếu không chuẩn bị rollback, một lỗi nhỏ có thể làm thời gian phục hồi kéo dài.

Bài thực hành thuộc *Java Advance Compatibility Migration*, chương *Bài thực hành*, xây dựng một quy trình nâng **Java 11 → Java 17 → Java 21** theo giai đoạn. Chúng ta sẽ tạo một ứng dụng Java nhỏ, chụp baseline, thay toolchain và runtime theo từng bước, chạy ma trận kiểm thử, thiết kế canary, lưu bằng chứng và diễn tập quay lui.

Các JDK 11/17/21 là **mốc ví dụ**; dự án thật phải chọn những phiên bản runtime, library và application server được vendor/tổ chức hỗ trợ. Các lệnh trong bài dành cho môi trường lab hoặc staging riêng. Tài liệu **không tuyên bố** những lệnh, test hay rollout đã được thực thi.

## 1. Mục tiêu học tập

Sau khi hoàn thành, người học có thể:

1. Phân biệt **JDK chạy build**, **mức `--release` của compiler** và **JDK chạy ứng dụng**.
2. Kiểm kê source, dependencies, plugins, JVM flags, containers và external services.
3. Lưu baseline gồm Git SHA, artifact checksum, test results và runtime configuration.
4. Nâng JDK bằng những bước có acceptance criteria cụ thể.
5. Chạy unit, CLI smoke, contract, integration, runtime matrix và performance tests.
6. Nhận diện lỗi bytecode, thiếu API/provider, JPMS/reflection và cờ JVM không còn hỗ trợ.
7. Test một dịch vụ khi bản cũ/bản mới cùng hoạt động.
8. Lập và diễn tập rollback bao gồm cả application image, cấu hình, database và event state.
9. Ghi quyết định `GO`, `HOLD` hay `ROLLBACK` dựa trên bằng chứng, không đoán.

### 1.1. Đầu ra của bài thực hành

Mẫu workspace:

~~~text
jdk-migration-lab/
├── pom.xml
├── src/
│   ├── main/java/lab/migration/ReceiptCli.java
│   └── test/java/lab/migration/ReceiptCliTest.java
├── fixtures/expected-output.txt
├── deploy/
│   ├── runtime-java11.env.example
│   ├── runtime-java17.env.example
│   └── runtime-java21.env.example
└── evidence/
    ├── s0-baseline/
    ├── s1-build-jdk17/
    ├── s2-runtime17/
    ├── s3-runtime21/
    ├── s4-target21-optional/
    └── rollback/
~~~

Cây thư mục này là **bài tập cần tạo**, không khẳng định các file đã có. Mỗi thư mục evidence phải liên kết với đúng artifact và môi trường, tránh lưu đè kết quả vào `latest`.

## 2. Ba chiều cần tách khi nâng JDK

| Chiều | Ví dụ | Quyết định điều gì? |
|---|---|---|
| Build/compiler JDK | JDK 21 | Compiler/tooling chạy ở phiên bản Java nào |
| Compiler `--release` | 17 | Mức API và class-file target của source được compile |
| Runtime JDK | JDK 17/21 | JVM nạp và chạy artifact thực tế |

Ví dụ, JDK 21 compile với `--release 17` tạo class-file major version thường là **61**, không phải 65. Nhưng việc này **không hạ bytecode của dependency** đã được biên dịch sẵn với Java 21.

Một ứng dụng có thể chạy trên Java 21 mà vẫn giữ target Java 17 để hỗ trợ khách hàng hoặc rolling deployment. Không có quy tắc bắt buộc “nâng runtime thì nâng source target ngay”.

### 2.1. Kế hoạch giai đoạn

| Stage | Build JDK | Compiler target | Runtime kiểm tra | Mục tiêu |
|---|---|---|---|---|
| S0 | 11 | 11 | 11 | Baseline |
| S1 | 17 | 11 | 11 và 17 | Nâng build JDK, giữ contract binary |
| S2 | 17 | 17 | 17 | Nâng minimum runtime |
| S3 | 21 | 17 | 17 và 21 nếu còn hỗ trợ 17 | Chuyển runtime JDK 21, giữ bytecode |
| S4 (tùy chọn) | 21 | 21 | 21 | Dùng Java 21 API/language features |

### 2.2. Quy trình cổng kiểm thử

~~~mermaid
flowchart TD
    A["S0 baseline và inventory"] --> B["S1 compiler JDK 17, target 11"]
    B --> C{"Runtime 11/17 và tests đạt?"}
    C -->|Không| X["HOLD: sửa candidate hoặc trở về baseline"]
    C -->|Có| D["S2 minimum runtime 17"]
    D --> E{"Consumers, dependencies hỗ trợ?"}
    E -->|Không| X
    E -->|Có| F["S3 runtime 21, target 17"]
    F --> G{"Integration, SLO và rollback đạt?"}
    G -->|Không| X
    G -->|Có| H["Canary → promote"]
    H --> I["S4 target 21 chỉ khi cần"]
~~~

**Không tự nhảy stage** chỉ vì JDK cuối cùng chạy được với một chức năng đơn giản.

## 3. Nguyên tắc an toàn

- Dùng workspace lab, disposable database và staging có kiểm soát; không trực tiếp sửa production.
- Giữ bản last-known-good của binary, runtime image, config và data/schema compatibility.
- Không thêm quá nhiều thay đổi không liên quan trong một stage.
- Không tắt TLS certificate validation, không vô hiệu hóa các kiểm soát bảo mật để “cho test xanh”.
- Không dùng `-XX:+IgnoreUnrecognizedVMOptions` để che lỗi JVM flag cũ.
- Không chạy DDL nguy hiểm hay rollback dữ liệu thật khi chưa có backup/approval.
- Không lưu credentials, tokens, private keys hoặc raw customer data trong reports.
- Không đánh dấu test chưa chạy là PASS.
- Khi một gate bắt buộc thất bại, lựa chọn mặc định là **HOLD**, không promote.

### 3.1. Các trạng thái cần dùng

~~~text
PENDING:  Chưa bắt đầu.
RUNNING:  Đang thực hiện.
PASS:     Test đã chạy và đạt.
FAIL:     Test đã chạy và thất bại.
SKIPPED:  Test bị bỏ qua.
BLOCKED:  Thiếu điều kiện để chạy.
HOLD:     Stage chưa đủ điều kiện chuyển tiếp.
GO:       Stage đã được phê duyệt.
ROLLBACK: Quay lại trạng thái được duyệt.
~~~

Một build job exit 0 không chứng minh mọi integration tests, rollback tests và performance gates đều đạt.

## 4. Chuẩn bị môi trường

Cần Git, Maven, JDK 11/17/21, shell/PowerShell và quyền lưu artifact. Nếu làm phần mở rộng deployment, cần container runtime cùng database/queue thử nghiệm.

### 4.1. Kiểm tra toolchain

~~~bash
java -version
javac -version
mvn -version
git --version
~~~

Ghi output thực tế: vendor, version/update và architecture. Với Gradle, ghi riêng JVM chạy Gradle daemon và Java toolchain compiler.

### 4.2. Chuyển JDK rõ ràng

Linux/macOS:

~~~bash
export JAVA_HOME=/path/to/approved-jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
java -version
mvn -version
~~~

Windows PowerShell:

~~~powershell
$env:JAVA_HOME = "C:\jdks\jdk-17"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
mvn -version
~~~

Các đường dẫn chỉ là minh họa. Trong CI, chọn JDK bằng toolchain/container image được pin version thay vì giả định PATH đang đúng.

## 5. Tạo dự án Maven mẫu

Ứng dụng đơn giản giúp xác minh đúng sự khác nhau giữa build và runtime. Nó nhận số tiền và timestamp, phát ra một dòng wire-format có dấu chấm thập phân và UTC.

Contract:

~~~text
Input:  12.345 2026-11-12T00:00:00Z
Output: amount=12.34;at=2026-11-12T00:00:00Z
~~~

Quy tắc `HALF_EVEN` và hai chữ số thập phân chỉ là yêu cầu **giả định của lab**. Trong nghiệp vụ thật, chính sách tiền tệ phải do domain quyết định.

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>lab.migration</groupId>
    <artifactId>jdk-migration-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>11</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>lab.migration.ReceiptCli</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các versions plugin/JUnit là một bộ ví dụ để giảng dạy; dự án thật phải xác minh bản được hỗ trợ và phù hợp JDK/vendor. `maven.compiler.release` có thể được ghi đè khi chạy:

~~~bash
mvn -B -ntp clean verify -Dmaven.compiler.release=17
~~~

Chạy Maven bằng JDK 21 với property trên **không đồng nghĩa** runtime JDK đã là 17 hoặc 21. Cần kiểm tra `mvn -version`.

### 5.2. ReceiptCli.java

~~~java
package lab.migration;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;

public final class ReceiptCli {
    private ReceiptCli() {
    }

    public static String render(BigDecimal amount, Instant at) {
        String money = amount.setScale(
                2, RoundingMode.HALF_EVEN).toPlainString();

        return "amount=" + money + ";at=" + at;
    }

    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println(
                    "Usage: <amount> <UTC-ISO-8601-instant>");
            System.exit(2);
        }

        try {
            BigDecimal amount = new BigDecimal(args[0]);
            Instant at = Instant.parse(args[1]);
            System.out.println(render(amount, at));
        } catch (RuntimeException invalidInput) {
            System.err.println("Invalid input: " +
                    invalidInput.getClass().getSimpleName());
            System.exit(2);
        }
    }
}
~~~

File đặt tại `src/main/java/lab/migration/ReceiptCli.java`.

Điểm đáng chú ý:

- `BigDecimal(String)` tránh sai số của binary floating-point.
- `toPlainString()` và `HALF_EVEN` giữ format theo contract.
- `Instant` xác định thời điểm UTC.
- Không dùng locale hệ thống để format số.
- Exit code giúp scheduler/script xác định input sai.

### 5.3. ReceiptCliTest.java

~~~java
package lab.migration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import org.junit.jupiter.api.Test;

class ReceiptCliTest {
    private static final Instant AT =
            Instant.parse("2026-11-12T00:00:00Z");

    @Test
    void keepsHalfEvenDecimalContract() {
        assertEquals(
                "amount=12.34;at=2026-11-12T00:00:00Z",
                ReceiptCli.render(new BigDecimal("12.345"), AT));
        assertEquals(
                "amount=12.36;at=2026-11-12T00:00:00Z",
                ReceiptCli.render(new BigDecimal("12.355"), AT));
    }

    @Test
    void formatsZero() {
        assertEquals(
                "amount=0.00;at=2026-11-12T00:00:00Z",
                ReceiptCli.render(BigDecimal.ZERO, AT));
    }

    @Test
    void rejectsMalformedTimestamp() {
        assertThrows(DateTimeParseException.class,
                () -> Instant.parse("not-a-timestamp"));
    }
}
~~~

File đặt tại `src/test/java/lab/migration/ReceiptCliTest.java`.

### 5.4. Fixture

`fixtures/expected-output.txt`:

~~~text
amount=12.34;at=2026-11-12T00:00:00Z
~~~

Lưu ý newline và charset khi so sánh exact bytes. Nếu output contract là một dòng logic, có thể định nghĩa quy tắc chuẩn hóa newline rõ ràng cho các OS.

## 6. Stage S0 — Chụp baseline Java 11

Với JDK 11:

~~~bash
java -version
mvn -version
git rev-parse HEAD
git status --porcelain

mvn -B -ntp clean verify -Dmaven.compiler.release=11

java -jar target/jdk-migration-lab-1.0.0.jar \
  12.345 2026-11-12T00:00:00Z
~~~

Expected stdout:

~~~text
amount=12.34;at=2026-11-12T00:00:00Z
~~~

### 6.1. Kiểm tra bytecode

~~~bash
jar tf target/jdk-migration-lab-1.0.0.jar

javap -verbose \
  -classpath target/jdk-migration-lab-1.0.0.jar \
  lab.migration.ReceiptCli
~~~

Java 11 classfile có major version **55**.

### 6.2. Tính checksum

Linux/macOS:

~~~bash
sha256sum target/jdk-migration-lab-1.0.0.jar
~~~

Windows PowerShell, viết một dòng để tránh nhầm shell escaping:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "target\jdk-migration-lab-1.0.0.jar"
~~~

Ghi kết quả kèm build ID/source commit. Một JAR build lại có thể có hash khác dù version/name vẫn giống.

### 6.3. Gate S0

- [ ] JVM và Maven đang dùng JDK 11.
- [ ] Unit tests được chạy, số pass/fail/skip rõ.
- [ ] CLI output khớp fixture.
- [ ] Invalid input tạo exit code khác 0.
- [ ] JAR có main class và major 55.
- [ ] Git commit, dependencies, JDK update được ghi.
- [ ] Artifact checksum và config được lưu.
- [ ] Có last-known-good để quay lại.

Nếu baseline còn lỗi hoặc test flaky chưa được phân loại, **HOLD** trước khi nâng.

## 7. Stage S1 — Nâng build JDK lên 17, giữ target Java 11

Với JDK 17 đã chọn:

~~~bash
java -version
mvn -version
mvn -B -ntp clean verify -Dmaven.compiler.release=11
~~~

### 7.1. Yêu cầu quan trọng

Kiểm tra `javap -verbose`: major vẫn **55**. Compiler mới nhưng bytecode vẫn hướng tới runtime 11.

Chạy **cùng JAR** trên hai runtime:

~~~bash
/path/to/jdk-11/bin/java \
  -jar target/jdk-migration-lab-1.0.0.jar \
  12.345 2026-11-12T00:00:00Z

/path/to/jdk-17/bin/java \
  -jar target/jdk-migration-lab-1.0.0.jar \
  12.345 2026-11-12T00:00:00Z
~~~

Không chạy lại Maven để tạo JAR mới ở giữa hai smoke tests.

### 7.2. Lỗi có thể xuất hiện

- Maven plugin/annotation processor chưa hỗ trợ compiler JDK mới.
- Build script dùng internal JDK APIs.
- Test phụ thuộc default locale/charset.
- Reflection vào JDK private packages.
- Dependency version động được resolve khác.
- JVM flags của Maven/test runner không còn hợp lệ.

### 7.3. Acceptance criteria

| Kiểm tra | Điều kiện |
|---|---|
| Build JDK | Maven thật sự chạy trên JDK 17 |
| Compiler target | Java 11/major 55 |
| Smoke Java 11 | Output và exit code đạt |
| Smoke Java 17 | Output và exit code đạt |
| Tests | Mandatory tests PASS |
| Artifact | Hash và reports gắn cùng JAR |
| Recovery | Có thể dùng lại S0 |

## 8. Stage S2 — Chuyển minimum runtime sang Java 17

Khi đã chắc chắn những consumer/runtime bắt buộc không còn Java 11, có thể nâng target.

~~~bash
mvn -B -ntp clean verify -Dmaven.compiler.release=17
~~~

Class-file major của Java 17 là **61**.

### 8.1. Thất bại có chủ đích

Chạy JAR target 17 trên Java 11 có thể báo:

~~~text
java.lang.UnsupportedClassVersionError:
class file version 61.0 is not supported by this runtime
~~~

Thông báo chính xác phụ thuộc JVM. Đây là giới hạn hợp lệ: **Java 11 không nạp được bytecode Java 17**. Không chữa bằng cách thêm JVM flags. Muốn rollback về runtime Java 11, cần **artifact target 11** đã lưu.

### 8.2. Inventory runtime bắt buộc

- HTTP services và workers.
- Scheduled jobs.
- Plugin/application server.
- Batch utilities.
- Customer-hosted installations.
- CI test launchers.
- Custom `jlink` images.
- Monitoring agents/native libraries.

Nếu còn nơi phải dùng Java 11, không phát hành artifact target 17 cho môi trường đó.

### 8.3. Gate S2

- [ ] Minimum runtime 17 được công bố và triển khai.
- [ ] Artifact target 17/major 61.
- [ ] Integration tests trên JDK 17 đạt.
- [ ] Dependencies/agents/providers hỗ trợ JDK 17.
- [ ] Không còn consumer bắt buộc chạy Java 11.
- [ ] Có last-known-good artifact/config JDK 11.
- [ ] Data/schema rollback đã được đánh giá.

## 9. Stage S3 — Nâng runtime/build lên JDK 21, giữ target 17

Để tách runtime migration khỏi bytecode change:

~~~bash
mvn -B -ntp clean verify -Dmaven.compiler.release=17
~~~

Maven chạy JDK 21, nhưng classfile major vẫn **61**.

### 9.1. Chạy trên hai JVM

~~~bash
/path/to/jdk-17/bin/java \
  -jar target/jdk-migration-lab-1.0.0.jar \
  12.345 2026-11-12T00:00:00Z

/path/to/jdk-21/bin/java \
  -jar target/jdk-migration-lab-1.0.0.jar \
  12.345 2026-11-12T00:00:00Z
~~~

Ghi binary hash và runtime thực tế cho mỗi test. `--release 17` **không đảm bảo** third-party JAR, native libraries hoặc Java agents cũng tương thích Java 17.

### 9.2. Các lớp rủi ro cần kiểm chứng

- Class loading/module access/reflection.
- Security provider/TLS/truststore.
- Charset/locale/TZDB.
- JDBC/ORM/transactions.
- JSON/XML/event serialization.
- JNI/native components.
- Java agent/instrumentation.
- GC/heap/CPU ergonomics.
- Startup/readiness/shutdown.
- API contract và shared data formats.

### 9.3. Gate S3

| Nhóm | Bằng chứng |
|---|---|
| Build JDK | JDK 21 compiler/toolchain report |
| Target | Major 61 |
| Runtime | Smoke 17 và 21 |
| Integration | DB/broker/framework/provider tests |
| Security | TLS/auth/driver/provider tests |
| Business | Contract và data invariants |
| Performance | SLO và resource budget |
| Rollback | Last-known-good, rehearsal |
| Traceability | Artifact hash, manifest, test IDs |

## 10. Stage S4 — Target Java 21 khi thực sự cần

~~~bash
mvn -B -ntp clean verify -Dmaven.compiler.release=21
~~~

Java 21 có class-file major **65**. JAR target 21 không chạy trên Java 17.

Chỉ thực hiện S4 nếu runtime Java 21 là minimum được hỗ trợ và có lợi ích rõ (API/source features mới, dependency yêu cầu mới hoặc thay đổi support policy). Nếu vẫn phải hỗ trợ Java 17, có thể giữ target 17 dù runtime production đã lên Java 21.

## 11. Ma trận binary và runtime

| Artifact | Target | Java 11 | Java 17 | Java 21 |
|---|---|---|---|---|
| S0 | 11 | Test | Test nếu hỗ trợ | Test nếu hỗ trợ |
| S1 | 11 | Test | Test | Test nếu hỗ trợ |
| S2 | 17 | Không hỗ trợ | Test | Test nếu hỗ trợ |
| S3 | 17 | Không hỗ trợ | Test nếu hỗ trợ | Test |
| S4 | 21 | Không hỗ trợ | Không hỗ trợ | Test |

“Test” không có nghĩa PASS mặc định. Phải có kết quả thật cho những tổ hợp sản phẩm công bố hỗ trợ.

### 11.1. Đừng suy từ classfile version đơn lẻ

Một JAR target 17 có thể mang dependency target 21. Ngược lại, classfile target thấp không bảo đảm API ngoài Java SE hoặc native provider tương thích. Hãy xem **cả dependency graph và runtime behavior**.

## 12. Kiểm kê dependencies, JDK internals và JPMS

~~~bash
mvn dependency:tree

jdeps --jdk-internals --recursive \
  --class-path "lib/*" app.jar

jdeps --print-module-deps \
  --class-path "lib/*" app.jar
~~~

`jdeps` phân tích tham chiếu tĩnh, không thấy mọi reflection strings, dynamic plugins hoặc JNI. Trong application server, dependencies do server cung cấp còn có thể nằm ngoài Maven dependency tree.

### 12.1. Những nhóm cần kiểm tra

| Nhóm | Rủi ro |
|---|---|
| JDK internals | `sun.*` và internal APIs bị hạn chế/loại |
| JPMS | `--add-opens`, `--add-exports`, reflection |
| Annotation processors | Compiler/plugin JDK compatibility |
| Bytecode tooling | ASM/agents không hiểu classfile mới |
| Java EE/Jakarta | `javax.*`/`jakarta.*` và server generation |
| Logging | API/provider binding khác nhau |
| JDBC/ORM | Driver, transaction, provider versions |
| TLS/security | Certificate/algorithm/provider behavior |
| Native | JNI/JNA, ABI/architecture |
| Plugin host | API được host cung cấp và classloader identity |

### 12.2. Không dùng module flags để chữa lỗi sai tầng

`InaccessibleObjectException` liên quan JPMS/deep reflection; `NoClassDefFoundError` thường là thiếu class hoặc lỗi initialization; `NoSuchMethodError` thường là binary mismatch. Cần điều tra đúng nguyên nhân.

## 13. JVM flags có thể làm startup thất bại

Cấu hình legacy có thể chứa:

~~~text
-XX:+UseConcMarkSweepGC
-XX:+PrintGCDetails
-Xloggc:logs/gc.log
--illegal-access=permit
~~~

CMS bị loại khỏi HotSpot từ JDK 14; nhiều flags/logging options thay đổi theo release. Một số cấu hình làm JVM dừng **trước khi `main()` chạy**.

Nguồn cần kiểm kê: Docker entrypoint, Helm/Kubernetes values, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, service scripts, Maven/Gradle test runners và monitoring agents.

### 13.1. Xác minh effective JVM settings

HotSpot/JDK hỗ trợ:

~~~bash
java -XX:+PrintCommandLineFlags -version
java -XX:+PrintFlagsFinal -version
java --list-modules
~~~

Với process đang chạy:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.version
~~~

Command line có thể chứa secret; redaction trước khi lưu report. Không dùng IgnoreUnrecognizedVMOptions để “bỏ qua cho chạy”; cần loại flags không còn hợp lệ và xác nhận collector thực tế.

## 14. Các lớp kiểm thử của một migration

| Test | Điều cần chứng minh |
|---|---|
| Build/static | Source/bytecode/dependency hợp lệ |
| Unit | Business behavior giữ nguyên |
| CLI/smoke | Artifact có thể khởi động và trả output |
| Runtime matrix | JDK versions được hỗ trợ đều chạy được |
| Contract | Client/producer/consumer cũ hiểu giao thức mới |
| Integration | Database, queue, framework, native provider |
| Security | TLS, auth, truststore, algorithm policy |
| Performance | p99, throughput, GC, CPU/RSS |
| Deployment | Canary, rolling, graceful shutdown |
| State rollback | Shared DB/event/session đọc được sau quay lui |

Không dùng một unit test PASS để thay thế hết các lớp khác.

### 14.1. Smoke CLI và error path

~~~bash
java -jar target/jdk-migration-lab-1.0.0.jar \
  12.345 2026-11-12T00:00:00Z
~~~

Dự kiến một dòng output đúng như fixture. Trường hợp invalid:

~~~bash
java -jar target/jdk-migration-lab-1.0.0.jar \
  bad-number 2026-11-12T00:00:00Z
~~~

Kiểm tra exit code khác 0 và không có partial side effects. Message exception thực tế có thể khác nhau giữa JDK, nên nếu contract chỉ yêu cầu error category, đừng hardcode toàn bộ văn bản exception.

### 14.2. Test dữ liệu ranh giới

- Decimal `12.345` và `12.355` với HALF_EVEN.
- Số 0, âm và số rất lớn.
- Dấu phẩy thập phân nếu protocol chỉ chấp nhận dấu chấm.
- Timestamp invalid, timezone offsets và DST khi có lịch địa phương.
- Unicode/tiếng Việt và raw UTF-8 bytes.
- JSON null/missing/unknown fields khi ứng dụng dùng JSON.
- Duplicate requests/events và idempotency.
- Session/cache cũ và mới nếu deploy trộn version.

## 15. Kiểm thử charset, số thập phân và thời gian

Những thay đổi có thể không làm fail compile mà làm **dữ liệu đổi nghĩa**.

### 15.1. Charset

~~~java
byte[] bytes = "Tiếng Việt".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);
String text = new String(
        bytes, java.nio.charset.StandardCharsets.UTF_8);
~~~

Dùng charset tường minh với file/wire contract. JDK 18 thay đổi default charset theo JEP 400, nên dữ liệu legacy cần được giải mã theo encoding thực tế đã dùng, không tự động giả định UTF-8.

### 15.2. Decimal

~~~java
BigDecimal amount = new BigDecimal("12.345");
String wire = amount.setScale(
        2, RoundingMode.HALF_EVEN).toPlainString();
~~~

Không dùng `new BigDecimal(12.345)` để mô hình hóa số tiền decimal vì input double đã là binary floating-point.

### 15.3. Date/time

~~~java
Instant timestamp =
        Instant.parse("2026-11-12T00:00:00Z");
~~~

Không dùng JVM default timezone làm một phần của giao thức. Với lịch địa phương, giữ zone/offset và test DST nếu phù hợp.

## 16. Integration với framework và database

CLI chỉ chứng minh cơ chế compile/runtime cơ bản. Với một dịch vụ thật, cần chạy:

- JDBC/transaction tests.
- ORM entity scanning và mapping.
- Servlet/REST request/filter tests.
- JSON/XML/event serialization.
- ServiceLoader/provider discovery.
- TLS handshakes và authentication.
- Agent/bytecode instrumentation.
- JNI/native integration.
- Startup/readiness, threads/shutdown.
- Custom runtime image modules nếu dùng `jlink`.

### 16.1. Test trên môi trường tương đương production

Nếu production chạy container có resource limits và một JDK image tối giản, integration test chỉ trên developer laptop/full JDK có thể không phát hiện thiếu module/provider, CPU throttling hoặc native library mismatch.

### 16.2. Không dùng dữ liệu production chưa kiểm soát

Test migrations trên disposable DB hoặc dữ liệu ẩn danh; backup/snapshot phải theo policy. Không chạy destructive schema operations trên database thật trong bài lab.

## 17. Mixed-version deployments

Một rolling deployment có thể cùng lúc có:

~~~text
T0: [V1/Java17, V1/Java17, V1/Java17]
T1: [V1/Java17, V1/Java17, V2/Java21]
T2: [V1/Java17, V2/Java21, V2/Java21]
T3: [V2/Java21, V2/Java21, V2/Java21]
~~~

Cần thử hai hướng:

- Client V1 gọi server V2.
- Client V2 gọi server V1 nếu topology cho phép.
- Producer V1 → consumer V2.
- Producer V2 → consumer V1.
- V1/V2 cùng đọc/ghi database/cache.
- Retry từ V1 sang V2 không tạo đơn hàng trùng.
- Session/token do V2 viết vẫn đọc được khi rollback về V1.
- Graceful shutdown/drain trong rolling.

### 17.1. HTTP contract khác bytecode compatibility

Hai JVM độc lập có thể giao tiếp bằng JSON/gRPC dù chạy Java major khác nhau. Điều cần giữ là **wire protocol, schema và semantic behavior**. Nhưng nếu dùng Java native serialization, binary class names và `serialVersionUID` trở thành vấn đề khác cần test.

### 17.2. Canary ít traffic vẫn tác động rộng

Một canary chỉ 5% HTTP traffic có thể phát event schema mới cho toàn bộ consumers. Vì thế, “bật reader hiểu new format trước, bật writer phát new format sau” thường là chiến lược an toàn hơn.

## 18. Database expand–migrate–contract

Nếu V1 dùng `customer_name` còn V2 muốn `first_name`/`last_name`, không xóa cột cũ khi V1 vẫn đang chạy.

~~~sql
ALTER TABLE orders ADD COLUMN first_name VARCHAR(100);
ALTER TABLE orders ADD COLUMN last_name VARCHAR(100);
~~~

Quy trình:

~~~mermaid
flowchart TD
    A["Schema S1 + app V1"] --> B["Expand S2: thêm schema"]
    B --> C["Test V1 còn đọc/ghi"]
    C --> D["V1/V2 cùng hoạt động"]
    D --> E["Backfill + dual-read/write có kiểm soát"]
    E --> F["Consumer cũ rút hết"]
    F --> G["Contract S3: bỏ cấu trúc cũ"]
~~~

### 18.1. Những bài test bắt buộc

- V1 insert/update trên schema expanded.
- V2 đọc dữ liệu V1 đã ghi.
- V1 đọc dữ liệu V2 ghi trong cửa sổ rollback.
- Constraints/defaults không phá V1.
- Backfill không gây mất dữ liệu/lock quá lâu.
- Nếu dual-write, xử lý partial failure và consistency.
- Nếu schema contract đã chạy, rollback V1 có còn hợp lệ?

**Rollback container image không tự khôi phục database schema**.

## 19. Performance baseline và GC

JDK mới có thể thay GC ergonomics, JIT và container awareness.

| Metric | Baseline | Candidate | Gate |
|---|---|---|---|
| Throughput | Đo thực | Đo thực | Theo business SLO |
| p95/p99 latency | Đo thực | Đo thực | Theo latency SLO |
| Error/timeout rate | Đo thực | Đo thực | Theo error budget |
| GC pause p99/max | Đo thực | Đo thực | Theo pause budget |
| CPU/throttling | Đo thực | Đo thực | Có headroom |
| RSS/native memory | Đo thực | Đo thực | Dưới memory limit |
| Startup/readiness | Đo thực | Đo thực | Trong rollout budget |

Không lấy chỉ số của Java 11 trên máy 16 cores so sánh với Java 21 trong pod quota 1 vCPU rồi kết luận do collector.

### 19.1. Điều kiện benchmark

- Cùng workload/dataset/concurrency khi có thể.
- Warmup đầy đủ.
- JDK vendor/update rõ ràng.
- GC flags, heap limits rõ.
- Resource limits/architecture tương đương.
- Database/network dependencies ổn định.
- Có nhiều attempts và raw measurements.
- Theo dõi p99/error cùng CPU/RSS, không chỉ GC count.

Ví dụ log GC trên HotSpot:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -jar app.jar
~~~

Không bật profiling nặng ở production thiếu phê duyệt.

## 20. Evidence của mỗi stage

~~~text
evidence/
└── s3-runtime21/
    └── ci-8124/
        ├── manifest.yaml
        ├── app.jar
        ├── app.jar.sha256
        ├── toolchain.txt
        ├── dependency-tree.txt
        ├── jvm-flags.redacted.txt
        ├── unit-report.xml
        ├── smoke-jdk17.txt
        ├── smoke-jdk21.txt
        ├── integration-report.xml
        ├── performance.json
        ├── rollback-rehearsal.txt
        └── decision.yaml
~~~

### 20.1. Manifest mẫu

~~~yaml
migration:
  stage: "S3"
  objective: "Nâng runtime JDK 21, giữ target 17"
  predecessor: "S2"

source:
  commit: "EXACT_GIT_COMMIT"

build:
  id: "ci-8124"
  compiler_jdk: "EXACT_JDK21_VENDOR_AND_UPDATE"
  maven_version: "EXACT_MAVEN_VERSION"
  release_target: 17

artifact:
  path: "app.jar"
  sha256: "EXACT_SHA256"

tests:
  unit: "unit-report.xml"
  runtime17: "smoke-jdk17.txt"
  runtime21: "smoke-jdk21.txt"
  integration: "integration-report.xml"
  performance: "performance.json"

decision:
  status: "PENDING"
  rollback_artifact: "LAST_KNOWN_GOOD_SHA"
  owner: "RELEASE_OWNER"
~~~

Các giá trị `EXACT_*` là placeholder. Không dùng manifest mẫu làm bằng chứng test thật.

### 20.2. Build một lần, promote cùng artifact

Tránh:

~~~text
Build A → Test A → Rebuild B → Deploy B
~~~

Ưu tiên:

~~~text
Build A → SHA A → Test A → Staging A → Canary A → Production A
~~~

Nếu ký hoặc repackaging tạo binary mới, lưu checksum/provenance riêng.

### 20.3. Failed tests vẫn cần evidence

Có thể có trạng thái hợp lệ:

~~~text
TEST_STATUS=FAIL
EVIDENCE_UPLOAD=SUCCESS
RELEASE_GATE=BLOCKED
~~~

Không xóa failure logs hoặc chỉ giữ attempt retry PASS. Redact secrets/PII và quản lý retention.

## 21. Thiết kế release gates

| Gate | Tiêu chí | Nếu không đạt |
|---|---|---|
| Source/build | Commit, toolchain, dependency rõ | HOLD |
| Artifact | Binary hash/digest trùng bản đã test | HOLD |
| Unit/contract | Required tests thực sự PASS | HOLD |
| Runtime matrix | Supported JDKs chạy được | HOLD |
| Integration | DB/broker/provider/security đạt | HOLD |
| Shared data | State/schema rollback-compatible | HOLD |
| Performance | SLO/resource budget đạt | HOLD |
| Canary | Metrics ổn định theo version | HOLD/ROLLBACK |
| Recovery | Last-known-good có thể khôi phục | Không promote |

### 21.1. SKIPPED khác PASS

Nếu một test HSM bị skip vì thiết bị unavailable, ghi `SKIPPED`/`BLOCKED` và lý do. Không cộng test này vào số PASS. Nếu có waiver, cần owner, risk, mitigation, người duyệt và ngày hết hạn.

## 22. Canary rollout có kiểm soát

Một dịch vụ sau staging có thể:

1. Deploy candidate V2/JDK21 trên subset instances.
2. Giữ V1/JDK17 làm last-known-good.
3. Gửi tỷ lệ request nhỏ sang V2 theo policy.
4. Theo dõi error rate, p99, CPU/RSS/GC theo version.
5. Xem database/event/queue consumers có lỗi không.
6. Tăng traffic theo từng mốc nếu đạt.
7. Dừng/rollback ngay khi chạm trigger được duyệt.
8. Lưu deployment ID, digest, config và quyết định.

Health/readiness trả 200 chỉ chứng minh endpoint sức khỏe đáp ứng điều kiện probe, **không thay thế** end-to-end contracts, shared-state tests và business invariants.

## 23. Rollback phải được thiết kế trước

Một rollback plan gồm:

- Trigger: lỗi business, SLO, security hoặc dữ liệu.
- Last-known-good artifact/image digest.
- Runtime JDK và JVM flags tương ứng.
- Config/feature flags của phiên bản cũ.
- DB/event/session state compatibility.
- Cách chuyển traffic và dừng writers nguy hiểm.
- Người ra quyết định và người thực hiện.
- Smoke/contract/data verification sau quay lui.
- Evidence và incident follow-up.

### 23.1. Các tầng rollback

**Binary:** trở về JAR/container image cũ.

**Runtime:** trở về JDK/runtime image cũ khi artifact tương thích.

**Configuration:** khôi phục JVM flags, endpoints, feature flags.

**State:** chỉ rollback database/queue/cache khi có phương án đã test; nhiều thay đổi không thể đảo ngược an toàn.

Nếu artifact đã target Java 21, chạy nó trên Java 17 không được. Nếu V2 đã ghi schema mới mà V1 không đọc được, chỉ đổi binary là chưa đủ.

## 24. Runbook rollback minh họa

~~~text
DETECT
  1. Alert hoặc invariant fail.
  2. Xác nhận artifact version, JDK và scope.

FREEZE
  3. Dừng tăng canary traffic.
  4. Ngăn thêm writes không tương thích nếu cần.
  5. Ghi image digest, JVM flags, DB revision, logs.

ROLLBACK
  6. Chuyển traffic về last-known-good.
  7. Khôi phục binary/runtime/config được duyệt.
  8. Không tự động down-migrate DB chưa được test.
  9. Bảo toàn candidate artifact và incident evidence.

VERIFY
  10. Chạy smoke/contract tests.
  11. Kiểm tra DB, events, cache/session invariants.
  12. Xác nhận error/latency/resource metrics hồi phục.
  13. Ghi quyết định và bài học sau sự cố.
~~~

### 24.1. Kubernetes staging example

~~~bash
kubectl rollout status deployment/receipt-service \
  -n staging --timeout=180s

kubectl rollout history deployment/receipt-service \
  -n staging

kubectl rollout undo deployment/receipt-service \
  -n staging
~~~

**Chỉ thực hiện ở môi trường được phép.** `rollout undo` không tự rollback DB schema, ConfigMaps, Secrets hoặc external side effects.

### 24.2. Khi rollback không an toàn

Nếu V2 đã tạo record/event mà V1 không hiểu:

- Đánh dấu trạng thái `ROLLBACK_UNSAFE`.
- Cân nhắc roll-forward fix.
- Dùng adapter hoặc giữ old-reader compatibility.
- Feature-gate việc tạo dữ liệu mới.
- Dùng backup/restore với đánh giá mất dữ liệu nếu bắt buộc.
- Không tuyên bố rollback thành công chỉ vì V1 container start được.

## 25. Bài tập diễn tập sự cố

### Bài A — Cờ JVM đã bị loại

Candidate JDK mới không khởi động với một GC flag legacy.

1. Lưu startup stderr đã redaction.
2. Truy ra flag từ script/container/env.
3. Không bỏ qua unknown option.
4. Khôi phục runtime/config last-known-good.
5. Loại/cập nhật flag trong candidate.
6. Chạy startup test lại.
7. Lưu cả failed và corrected run IDs.

**Đạt khi:** xác định chính xác nguyên nhân, giữ được rollback và candidate mới được kiểm tra.

### Bài B — Bytecode cao hơn JVM

JAR target Java 21 được chạy nhầm trên Java 17.

1. Đọc `UnsupportedClassVersionError`.
2. Dùng `javap` kiểm tra major 65.
3. Ghi JDK runtime/artifact hash.
4. Chọn build target thấp hoặc nâng runtime fleet.
5. Chạy lại ma trận.

**Đạt khi:** biết đây là lỗi target, không phải thiếu `--add-opens`.

### Bài C — Decimal wire format lệch locale

Contract:

~~~text
amount=12.34;at=2026-11-12T00:00:00Z
~~~

Candidate sinh:

~~~text
amount=12,34;at=2026-11-12T00:00:00Z
~~~

Consumer cũ dùng dấu chấm.

1. Viết regression fixture.
2. Xác định default locale/formatter.
3. Dùng decimal representation theo wire contract.
4. Chạy test nhiều locale và JDK.
5. Lưu report, không promote khi contract fail.

### Bài D — State làm rollback thất bại

Giả sử V2 phát enum `REFUNDED` nhưng V1 chỉ biết `CREATED/PAID/CANCELLED`.

1. Test V2 producer → V1 consumer.
2. Xác định parse/semantic failure.
3. Đánh dấu rollback unsafe nếu V1 không đọc được state.
4. Đề xuất reader-first/write-later.
5. Thiết kế adapter hoặc roll-forward.
6. Ghi chính xác thời điểm có thể loại bỏ compatibility layer.

## 26. Decision record

~~~yaml
decision:
  stage: "S3"
  artifact_digest: "sha256:EXACT_HASH"
  status: "HOLD"
  reason: "Required integration test failed"
  report: "integration-report.xml"
  rollback_target: "LAST_KNOWN_GOOD_DIGEST"
  owner: "Assigned release owner"
  decided_at: "ISO_8601_TIMESTAMP"
~~~

Đây là ví dụ, không phải approval/test kết quả thật.

## 27. CI pipeline có evidence gate

~~~mermaid
flowchart TD
    A["Pinned source commit + stage ID"] --> B["Toolchain + dependency resolution"]
    B --> C["Unit/build"]
    C --> D["Artifact + checksum"]
    D --> E["Cross-JDK, contract, integration, performance"]
    E --> F["Archive reports cả khi FAIL"]
    F --> G{"Mandatory gates đạt?"}
    G -->|Không| H["HOLD"]
    G -->|Có| I["Staging/canary same digest"]
    I --> J{"SLO và recovery đạt?"}
    J -->|Có| K["Promote by digest"]
    J -->|Không| L["Rollback + incident evidence"]
~~~

Pipeline thật cần pin toolchain, dependency versions, artifact checksum, DB/broker image và runtime configuration. Build cache không phải kho release bất biến.

## 28. Bảng chẩn đoán lỗi

| Triệu chứng | Nguyên nhân có thể | Điều tra |
|---|---|---|
| Maven fail với JDK mới | Plugin/compiler mismatch | Maven/JDK versions |
| `UnsupportedClassVersionError` | Bytecode quá mới | `javap`, runtime Java |
| `NoClassDefFoundError` | Missing class/module/provider | Dependencies, runtime image |
| `NoSuchMethodError` | Binary library mismatch | Method descriptors, graph |
| `InaccessibleObjectException` | Deep reflection bị chặn | JPMS, framework |
| `ServiceConfigurationError` | SPI/provider resolution | Services/module graph |
| Unrecognized VM option | Cờ obsolete/removed | Startup arguments |
| TLS handshake fail | Truststore/security mismatch | Certificates, algorithms |
| CSV decimal/time khác | Locale/timezone/charset | Wire fixtures |
| p99 tăng | GC/CPU/DB/network | Metrics, traces, resource limits |
| Rollback binary nhưng DB lỗi | Schema/state không tương thích | Expand/contract, backup |
| Canary HTTP xanh, queue lỗi | Event schema mismatch | Consumer errors, DLQ |
| Test chỉ fail CI | Env/JDK/locale khác | Toolchain snapshot |

## 29. Checklist từng stage

### S0

- [ ] JDK 11/vendor/update đã ghi.
- [ ] Build, unit, smoke PASS.
- [ ] Classfile major 55.
- [ ] Artifact checksum và Git SHA đã lưu.
- [ ] Last-known-good config còn truy xuất.

### S1

- [ ] Build JDK 17, target 11.
- [ ] Major vẫn 55.
- [ ] Cùng artifact chạy trên Java 11/17.
- [ ] Test results và dependency graph được lưu.
- [ ] Có đường quay lại S0.

### S2

- [ ] Runtime minimum đã chuyển Java 17.
- [ ] Target 17/major 61.
- [ ] Consumers, plugins, agents đều có phương án tương thích.
- [ ] Integration tests đạt.
- [ ] Rollback binary/config/data được đánh giá.

### S3

- [ ] Build/runtime JDK21, target 17/major 61.
- [ ] Runtime matrix 17/21 theo support policy đạt.
- [ ] TLS, serialization, locale, timezone tests đạt.
- [ ] JVM flags và GC đã xác nhận.
- [ ] Performance/resource budgets đạt.
- [ ] Canary và rollback rehearsal có evidence.

### S4 nếu có

- [ ] Đã công bố minimum Java21.
- [ ] Target 21/major 65.
- [ ] Không còn dependency cần runtime 17 cho artifact mới.
- [ ] Đã thử artifact trên runtime 21 thực tế.
- [ ] Có last-known-good cho giai đoạn mới.

## 30. Checklist trước production promotion

### Artifact và kiểm thử

- [ ] Source commit sạch, build toolchain được pin.
- [ ] Resolved dependencies và artifact digest rõ.
- [ ] Staging/canary dùng đúng artifact sẽ promote.
- [ ] Required tests PASS; skips/waivers có quyết định.
- [ ] Contract/mixed-version/state tests được áp dụng khi cần.
- [ ] Test runner environment và JDK runtime được ghi.

### Hiệu năng và an toàn

- [ ] Throughput/p99/error rate đạt SLO.
- [ ] CPU/RSS/GC/oom limits còn headroom.
- [ ] TLS/security/provider checks đạt.
- [ ] Observability phân biệt được Java và app version.
- [ ] Graceful shutdown/draining đã kiểm tra.

### Quay lui

- [ ] Last-known-good image/artifact và config còn sẵn.
- [ ] DB/event/session state rollback-safe hoặc có phương án riêng.
- [ ] Rollback triggers, owner và runbook đã duyệt.
- [ ] Đã diễn tập rollback trong môi trường phù hợp.
- [ ] Có test xác nhận hệ thống sau rollback.
- [ ] Có nơi lưu logs, checksum, decision và incident evidence.

## 31. Câu hỏi tự đánh giá

1. Vì sao compiler JDK 21 với `--release 17` không sinh bytecode Java 21?
2. JAR major 61 có chạy trên Java 11 không?
3. Nếu JUnit PASS nhưng API contract của client cũ FAIL, có được GO không?
4. Tại sao phải lưu SHA-256 của artifact được test?
5. Nếu V2 ghi dữ liệu mới, rollback về V1 có luôn an toàn?
6. Một canary nhỏ có thể làm event consumers cũ thất bại bằng cách nào?
7. Tại sao chỉ đo GC count không đủ đánh giá performance?
8. Làm sao phát hiện JVM flags không còn hỗ trợ trước production?
9. Khi nào nên giữ target Java 17 dù production dùng JDK 21?
10. Bằng chứng nào giúp chứng minh rollback đã khôi phục đúng hệ thống?

Khi trả lời, hãy chỉ ra test cases, artifact hashes, runtime và decision records tương ứng, thay vì chỉ lặp lại khái niệm.

## 32. Bài tập mở rộng

### 32.1. Framework migration

Thêm một framework/database dependency có support matrix rõ, ghi baseline và thử nâng theo từng nhóm. Kiểm tra public API, reflection, provider và binary compatibility.

### 32.2. Custom runtime image

Tạo runtime image với `jlink`/`jdeps` nếu phù hợp, rồi test dynamic services. Một image thiếu service provider có thể startup được nhưng fail ở chức năng hiếm.

### 32.3. Multi-service topology

Dựng V1/V2 ở hai endpoints test, có database và message broker disposable. Thử retry, cache/session, event compatibility và rollback sau V2 writes.

### 32.4. Security change

Giả lập TLS policy/certificate mismatch trên staging, kiểm tra error logs và quy trình cập nhật trust theo chính sách. Không tắt certificate validation để vượt qua test.

## Kết luận

**Nâng cấp JDK theo giai đoạn** cho phép tách lỗi compiler, bytecode target, runtime, dependency/framework và dữ liệu. Lộ trình **baseline Java 11 → build JDK 17 với target 11 → minimum runtime 17 → runtime JDK 21 với target 17 → target 21 khi cần** giúp giữ cửa sổ tương thích và thu thập bằng chứng có thể tái hiện.

Để phát hành an toàn, không chỉ cần một JAR build xanh. Cần **artifact checksum, ma trận kiểm thử runtime, contract/integration tests, performance SLO, canary observation và rollback đã diễn tập**. Khi một gate bắt buộc không đạt, chọn **HOLD** và điều tra. Nếu rollout chạm rollback trigger, ưu tiên khôi phục last-known-good **mà không làm hỏng database, event và session state**. Đó là cách chuyển đổi JDK có thể đo lường, truy xuất và phục hồi.

