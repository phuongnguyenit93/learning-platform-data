# Chạy cùng bộ kiểm thử trên môi trường cũ và mới

Khi nâng Java từ JDK đang vận hành sang JDK mục tiêu, câu hỏi quan trọng không chỉ là “ứng dụng có biên dịch được không?” mà còn là **“cùng dữ liệu đầu vào và cùng hợp đồng nghiệp vụ, hệ thống trên môi trường mới có còn hành xử đúng như trước không?”**. Một ứng dụng có thể khởi động trên JDK mới nhưng đổi cách xử lý thời gian, số thập phân, serialization, JDBC, TLS, reflection hoặc quản lý tài nguyên. Nếu chỉ chạy test trên môi trường mới, nhóm khó phân biệt lỗi hồi quy với hành vi cũ đã sai, thay đổi bảo mật có chủ đích hoặc khác biệt cấu hình.

Trong **Java Advance Compatibility Migration**, phương pháp nền tảng của chương **Kiểm thử hồi quy** là chạy một **bộ kiểm thử có thể đối chiếu** trên môi trường nguồn và đích, giữ dữ liệu và tiêu chí kiểm tra nhất quán, sau đó so kết quả theo từng ca thử chứ không chỉ nhìn dòng BUILD SUCCESS. Phương pháp này tạo bằng chứng cho quyết định migration, đồng thời chỉ ra nơi cần sửa mã, nâng dependency, thay cấu hình hoặc cập nhật hợp đồng.

“Cùng bộ kiểm thử” có nghĩa là giữ **cùng mục tiêu, cùng ca kiểm tra, cùng dữ liệu chuẩn và cùng assertions trong phạm vi có thể so sánh**. Nó không nhất thiết có nghĩa phải chạy cùng một file bytecode ở mọi tình huống: đôi khi test phải được biên dịch riêng cho các JDK hoặc framework khác nhau. Điểm khác biệt phải được ghi rõ để không tạo kết luận sai.

## 1. Vì sao chỉ kiểm thử trên JDK mới chưa đủ?

Giả sử một nhóm chuyển Java 17 sang Java 21. CI của JDK 21 chạy 400 test và tất cả PASS. Báo cáo này vẫn để ngỏ nhiều câu hỏi:

- Trên Java 17 có bao nhiêu test đã chạy? Có những lỗi baseline nào?
- 400 test có đúng là **cùng 400 test** trên cả hai JVM không?
- Có test bị bỏ do thay JUnit engine, plugin, tag hoặc Maven profile không?
- Cùng phiên bản dependency, database, schema và dữ liệu fixture hay không?
- Những thay đổi hành vi nằm ngoài assertions hiện có đã được kiểm chưa?
- Có thử các đường lỗi, quyền truy cập bị từ chối và dữ liệu lịch sử không?
- Test chạy trên JDK 21 thực sự, hay Gradle chạy Java 21 nhưng test worker chạy JDK khác?
- Có thay đổi container, OS, timezone, font hoặc credential trong cùng đợt không?

Một bài kiểm thử thành công chỉ chứng minh những điều đã được kiểm **trong chính môi trường chạy nó**. Muốn đánh giá hồi quy, cần có điểm tham chiếu ở môi trường nguồn và quy tắc so sánh rõ ràng.

## 2. Xác định chính xác môi trường cũ và mới

Nhãn “old” và “new” thường quá mơ hồ. Cần tạo **environment fingerprint** cho mỗi test run.

| Thành phần | Bằng chứng nên lưu | Lý do |
|---|---|---|
| Source | Git commit/tag, trạng thái file được build | Tránh so hai source revision không cùng cơ sở |
| JDK | Feature/update/build, vendor, CPU architecture | Java update hoặc distribution khác có thể khác hành vi |
| Compiler | JDK compiler, `--release`, bytecode baseline | Phân biệt compiler và runtime |
| Test JVM | Java launcher thực thi unit/integration tests | Không nhất thiết trùng JVM chạy build tool |
| Build tool | Gradle/Maven wrapper, plugin versions | Ảnh hưởng dependency resolution và test discovery |
| Dependency | Resolved graph, BOM, version lock | Thư viện có thể đổi behavior không do JDK |
| OS/container | OS, image digest, CPU/memory limits | Tác động path, native code, memory và timeout |
| Database | Driver/server version, schema revision | Tác động JDBC, timestamp, transaction |
| Locale/timezone | Locale, ZoneId, DB session timezone | Tác động format ngày giờ và dữ liệu |
| Runtime flags | GC, module opens, TLS, native access | Tác động startup và security |
| Test selection | Task/goal, tag, profile, danh sách testcase | Phát hiện test bị skip/mất |
| External systems | Mock version, sandbox endpoint, service contract | Giảm nhiễu từ bên ngoài |

Ví dụ bản ghi:

~~~yaml
regressionRun:
  runId: "java17-baseline-001"
  commit: "record actual commit SHA"
  runtime:
    jdkFeature: 17
    jdkVendorBuild: "record java -version"
    os: "linux-x64"
    timezone: "UTC"
  build:
    tool: "Gradle"
    wrapperVersion: "record actual version"
    release: 17
  dependencies:
    lockChecksum: "record actual checksum"
  database:
    version: "record actual version"
    schema: "S42"
  testSuite:
    id: "regression-v1"
    executedCount: "fill from report"
    report: "reports/java17/"
~~~

Đây chỉ là mẫu hồ sơ, **không phải kết quả đã chạy**. Nếu không biết một thông tin, ghi UNKNOWN hoặc NOT_CAPTURED thay vì đoán.

## 3. Cùng một bài toán nhưng có ba kiểu so sánh

### 3.1. Chỉ đổi runtime JDK

Giữ cùng source commit, application binary và dependency khi chúng hỗ trợ cả hai JVM:

~~~text
Same application binary + same dependency set
             |
        +----+----+
        |         |
      JDK OLD   JDK NEW
        |         |
   Same tests  Same tests
        |         |
      Report A Report B
~~~

Cách này giúp cô lập ảnh hưởng của JDK runtime tương đối tốt. Nhưng nếu library cũ không hỗ trợ JDK mới, tổ hợp ấy không thể được coi là trạng thái hỗ trợ chính thức.

### 3.2. Đổi cả JDK và dependency/framework

~~~text
OLD: JDK 17 + framework A + driver X + schema S1
NEW: JDK 21 + framework B + driver Y + schema S2
~~~

Chạy cùng contract tests giúp xác nhận **toàn bộ stack mới**, nhưng không đủ để khẳng định khác biệt chỉ do JDK. Cần test trung gian nếu tồn tại tổ hợp được hỗ trợ, hoặc reproduction nhỏ để khoanh vùng.

### 3.3. Kiểm consumer binary cũ

Nếu hệ thống cung cấp thư viện/plugin API, ngoài rebuild source cần giữ một consumer JAR đã biên dịch ở phiên bản cũ, thử chạy bytecode đó với dependency/runtime mới. Việc luôn biên dịch lại consumer có thể che lỗi `NoSuchMethodError` hoặc `IllegalAccessError` mà consumer chưa rebuild sẽ gặp.

**Mỗi kiểu test trả lời một câu hỏi khác nhau.** Báo cáo migration phải nêu kiểu so sánh thực sự được chạy.

## 4. “Cùng bộ kiểm thử” cần giữ giống nhau những gì?

Một phép so sánh đáng tin cậy giữ các yếu tố sau:

1. **Cùng test intent:** cùng yêu cầu được bảo vệ.
2. **Cùng test identity:** test ID hoặc mapping từ ca cũ sang ca mới.
3. **Cùng input và fixture:** bao gồm những giá trị biên.
4. **Cùng assertion nghiệp vụ:** trừ thay đổi được phê duyệt.
5. **Cùng test selection:** tag, suite, profile và filter.
6. **Cùng contract của external dependencies:** mock/sandbox khi có thể.
7. **Cùng điều kiện đo hợp lý:** tài nguyên, concurrency, warm-up, timezone.
8. **Cùng cách ghi kết quả:** phân biệt PASS, FAIL, SKIPPED, NOT_RUN.

Một số metadata như PID, cổng ngẫu nhiên hoặc timestamp log có thể khác vì môi trường. Chỉ loại bỏ chúng trong quá trình so sánh nếu đã xác định **không thuộc hợp đồng**. Không normalize toàn bộ output đến mức che cả số tiền, trạng thái nghiệp vụ hoặc thay đổi bảo mật.

## 5. Chuẩn bị baseline trước khi sửa source

Lý tưởng nhất, chạy regression suite trên môi trường nguồn trước khi nâng JDK hoặc dependency.

~~~text
Commit X (baseline)
  - capture JDK and dependency versions
  - run compile, unit, integration, contract tests
  - save reports and expected outputs
  - record known failures and skips

Commit X on target runtime (if supported)
  - run equivalent test selection
  - save reports
  - compare by test ID and behavior

Later migration commits
  - keep contract suite and baseline references
  - record intentionally changed expectations
~~~

Nếu baseline có test bị lỗi sẵn, đừng gọi candidate có cùng lỗi là regression mới. Tuy nhiên, cũng không biến lỗi baseline thành PASS. Ghi rõ known issue, owner và điều kiện xử lý.

| Trạng thái | Ý nghĩa |
|---|---|
| PASS | Test đã chạy và đạt assertion |
| FAIL | Test đã chạy và sai assertion |
| SKIPPED | Test được phát hiện nhưng bỏ qua theo quy tắc |
| NOT_RUN | Không có bằng chứng test đã thực thi |
| BLOCKED | Hạ tầng/dependency khiến test không thể chạy |
| FLAKY | Kết quả thay đổi giữa các lần chạy có điều kiện tương đương |
| NOT_SUPPORTED | Tổ hợp không thuộc ma trận hỗ trợ |

Không dùng PASS để thay thế NOT_RUN hay NOT_SUPPORTED.

## 6. Bổ sung bộ kiểm thử hồi quy theo rủi ro Java migration

| Phạm vi | Những ca kiểm thử nên có |
|---|---|
| Source/build | Compile, annotation processors, generated source, packaging |
| Binary/runtime | Class loading, linkage, service providers, reflection, agent/JNI |
| API/behavior | Giá trị, null, exception, ordering, validation |
| Dữ liệu | DECIMAL precision, timestamp, Unicode, JSON/XML, serialization |
| JDBC/ORM | Type mapping, transaction, generated keys, SQLState |
| Giao thức | HTTP headers/status/body, retry/timeout, TLS |
| Bảo mật | Invalid certificates, authorization, input filters, permission |
| Đồng thời | Race, deadlock, cancellation, thread-local/resource lifecycle |
| File/OS | Path, permission, encoding, font, native library |
| Vận hành | Startup, health check, shutdown, logs, GC/memory |
| Hiệu năng | Throughput, latency percentile, RSS, GC pauses |

Không cần chạy tất cả trong một task. Có thể tổ chức unit, integration, contract, security, performance và end-to-end suites riêng; nhưng mỗi suite phải có cơ chế so sánh hoặc lý do chỉ áp dụng một môi trường.

## 7. Thiết kế test có thể chạy lặp lại

Các test bị ảnh hưởng bởi clock, timezone, random seed, file paths hoặc remote services sẽ tạo nhiễu lớn khi đối chiếu hai JDK.

### 7.1. Cố định Clock cho thời gian nghiệp vụ

Thay vì:

~~~java
LocalDate today = LocalDate.now();
~~~

hãy cho phép inject Clock:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

public final class BillingDateService {
    private final Clock clock;

    public BillingDateService(Clock clock) {
        this.clock = clock;
    }

    public String todayIso() {
        return LocalDate.now(clock)
                .format(DateTimeFormatter.ISO_LOCAL_DATE);
    }
}
~~~

Test JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;

class BillingDateServiceTest {
    @Test
    void usesVietnamBusinessDate() {
        Clock fixed = Clock.fixed(
                Instant.parse("2026-11-11T18:30:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(
                "2026-11-12",
                new BillingDateService(fixed).todayIso());
    }
}
~~~

Điều này giúp test không phụ thuộc ngày giờ của runner. Nếu dữ liệu liên quan timezone rules lịch sử, phải lưu JDK/tzdb version khi đối chiếu.

### 7.2. Chỉ rõ Locale và Charset

~~~java
String formatted = String.format(
        java.util.Locale.US,
        "%,.2f",
        1234.5);
~~~

Nếu format thuộc hợp đồng, chọn locale cụ thể. Khi đọc/ghi file văn bản, chỉ rõ charset:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String text = Files.readString(
        Path.of("fixtures", "customer-vi.txt"),
        StandardCharsets.UTF_8);
~~~

`Files.readString` yêu cầu Java 11+. Nếu baseline phải hỗ trợ Java 8, dùng Reader/InputStream với UTF-8 tương ứng.

### 7.3. Cô lập trạng thái

Test nên tự tạo và dọn dữ liệu của mình, dùng thư mục tạm riêng, không dựa vào record có sẵn trên máy lập trình viên. Với database hoặc broker, mỗi job nên có schema, namespace hoặc fixture có thể reset. Không để các test trên JDK cũ và mới cùng cập nhật một bảng hoặc queue nếu điều đó không thuộc chính đối tượng đang kiểm.

## 8. Ví dụ: cùng một contract test trên hai JDK

Giả sử hợp đồng tính thuế yêu cầu giữ decimal precision:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class InvoiceCalculator {
    private InvoiceCalculator() {}

    public static BigDecimal total(
            BigDecimal net,
            BigDecimal taxRate) {

        if (net == null || taxRate == null) {
            throw new IllegalArgumentException("Missing value");
        }

        return net.multiply(BigDecimal.ONE.add(taxRate))
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

Test JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class InvoiceCalculatorTest {
    @Test
    void preservesDecimalPrecision() {
        BigDecimal actual = InvoiceCalculator.total(
                new BigDecimal("19.995"),
                new BigDecimal("0.10"));

        assertEquals(new BigDecimal("21.99"), actual);
    }

    @Test
    void rejectsMissingRate() {
        assertThrows(
                IllegalArgumentException.class,
                () -> InvoiceCalculator.total(
                        new BigDecimal("20.00"), null));
    }
}
~~~

Phép tính `19.995 × 1.10 = 21.9945` được làm tròn về `21.99` theo HALF_UP ở hai chữ số thập phân. Ví dụ này cho thấy một test nên xác định **hành vi cụ thể**, không chỉ kiểm method không ném exception.

Các ca biên bổ sung nên bao gồm giá trị 0, âm, rất lớn, scale khác nhau, null và ranh giới rounding. Nếu ứng dụng dùng JDBC, cần thêm test round-trip qua cột SQL DECIMAL thật thay vì chỉ test toán học Java.

## 9. So sánh kết quả theo ngữ nghĩa, không theo chuỗi tùy tiện

Ví dụ hai timestamp:

~~~text
OLD: 2026-11-12T00:00:00Z
NEW: 2026-11-12T07:00:00+07:00
~~~

Chúng có thể biểu diễn cùng một instant. Nếu hợp đồng quy định instant, so `Instant` sau khi parse. Nhưng nếu API cam kết format `Z` hoặc timezone cụ thể, thay đổi chuỗi có thể là breaking change.

Tương tự:

- JSON object key order có thể không quan trọng, nhưng array order có thể quan trọng.
- `BigDecimal.compareTo()` kiểm giá trị số; `equals()` còn xét scale.
- XML prefix có thể khác nhưng namespace URI tương đương; schema/element contract vẫn phải đúng.
- CSV có thể yêu cầu newline và quoting cụ thể.
- File PDF có thể khác metadata ngẫu nhiên nhưng cần giữ đúng Unicode/glyph, bố cục hoặc text extraction theo yêu cầu.

**Không tạo normalizer rộng** để xóa mọi khác biệt rồi tuyên bố hai môi trường tương đương.

## 10. Golden files và dữ liệu lịch sử

Với serializer, ORM, event hoặc report, nên lưu fixtures đại diện:

~~~text
fixtures/
  invoice-v1.json
  customer-vi.txt
  payment-legacy.bin

expected/
  invoice-response.json
  reconciliation.csv
  report-summary.xml
~~~

Một test trên JDK cũ và mới đọc cùng fixture rồi so output với hợp đồng. Ngoài round-trip trên runtime mới, phải thử đọc những dữ liệu mà phiên bản cũ đã tạo nếu hệ thống cam kết hỗ trợ.

Đừng tự regenerate expected snapshots chỉ vì candidate khác baseline. Trước tiên xác định thay đổi do fix có chủ đích, lỗi hồi quy, khác biệt serialization hoặc metadata không ổn định.

## 11. Test cả trường hợp lỗi và giới hạn bảo mật

Một regression suite chỉ có happy path không đủ.

| Test | Hợp đồng cần giữ hoặc đánh giá |
|---|---|
| Input không hợp lệ | Validation từ chối có kiểm soát |
| Token hết hạn | Không được truy cập |
| User thiếu quyền | Bị từ chối theo chính sách |
| TLS hostname sai | Certificate/hostname verification phải từ chối |
| Deserialization class không được phép | Filter chặn input |
| SQL constraint vi phạm | Transaction rollback và exception phù hợp |
| XML external entity nguy hiểm | Parser từ chối theo cấu hình bảo mật |
| File permission bị giới hạn | Không đọc/ghi ngoài quyền được cấp |

Đôi khi JDK mới từ chối một hành vi không an toàn mà JDK cũ từng chấp nhận. Đây **không tự động là regression phải khôi phục**. Cần xem lại hợp đồng và chính sách bảo mật, sửa certificate/peer/config phù hợp hoặc cập nhật test expectation có phê duyệt.

Negative tests phải chạy trong môi trường kiểm thử được cho phép, không cố tình khai thác production.

## 12. Source compatibility và binary compatibility là hai phép thử riêng

**Source compatibility**: compile consumer source cũ bằng dependency/JDK mới. Test có thể phát hiện method bị xóa, overload ambiguous, generic signature hoặc module export thay đổi.

**Binary compatibility**: chạy consumer bytecode đã biên dịch trước với library/runtime mới, khi tổ hợp được hỗ trợ. Test có thể phát hiện `NoSuchMethodError`, `NoClassDefFoundError`, `IllegalAccessError` và lỗi linkage.

Nếu luôn rebuild consumer khi test, bạn có thể không phát hiện được binary incompatibility đối với plugin hoặc ứng dụng downstream chưa rebuild.

### 12.1. Compiler release không đủ

Biên dịch bằng JDK 21 với `--release 17` giúp giới hạn source/bytecode và API Java SE của source được biên dịch. Nó **không kiểm soát bytecode của dependency JAR** đã có. Nếu sản phẩm tuyên bố hỗ trợ Java 17, cần chạy integration/runtime tests thực trên JVM 17.

## 13. Build JVM không nhất thiết là test JVM

Trong Gradle, có thể có JVM chạy daemon, compiler toolchain, test worker và JavaExec task riêng. Trong Maven, JVM chạy Maven core, compiler và Surefire/Failsafe test fork cũng có thể khác nhau.

Lệnh:

~~~bash
java -version
./gradlew --version
./mvnw --version
~~~

hữu ích để quan sát môi trường nhưng chưa đủ xác nhận tất cả test workers dùng JVM nào. Cần xem cấu hình launcher/toolchain, report và lệnh thực thi.

Một kết luận nên ghi:

~~~text
Gradle daemon JDK: 21
Compiler toolchain: 21
javac --release: 17
Unit tests launcher: 17
Application target: 17 and 21
~~~

Đây là ví dụ, không phải cấu hình bắt buộc.

## 14. Gradle: tổ chức test matrix bằng Java toolchain

Giả sử ứng dụng hỗ trợ Java 17 và Java 21, mã nguồn cùng dependency có thể chạy trên Java 17. Có thể biên dịch theo baseline rồi chạy **cùng test classes** trên hai runtime.

Ví dụ `build.gradle.kts` mang tính minh họa:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

listOf(17, 21).forEach { version ->
    tasks.register<Test>("testJava$version") {
        group = "verification"
        description = "Run tests on JDK $version"

        testClassesDirs =
            sourceSets["test"].output.classesDirs
        classpath =
            sourceSets["test"].runtimeClasspath

        useJUnitPlatform()

        javaLauncher.set(
            javaToolchains.launcherFor {
                languageVersion.set(
                    JavaLanguageVersion.of(version))
            }
        )

        reports.junitXml.required.set(true)
        reports.junitXml.outputLocation.set(
            layout.buildDirectory.dir(
                "test-results/java$version")
        )
    }
}
~~~

Những task này cần JDK toolchains có sẵn hoặc được provision theo cấu hình. Chúng chỉ kiểm runtime các test được compile theo release 17 và các dependency cũng phải chạy được trên 17. Với dự án khác, task/plugin/version có thể cần cấu hình riêng.

Lệnh tham khảo:

~~~bash
./gradlew clean testJava17 testJava21
~~~

**Không phải lệnh đã được thực thi khi viết bài này.** Nếu muốn thành release gate, pipeline phải chạy những task này rõ ràng hoặc nối chúng vào task verification. Việc đăng ký task không bảo đảm CI tự thực hiện.

### 14.1. Compile matrix và runtime matrix khác nhau

- **Compile matrix:** cùng source được biên dịch dưới compiler được hỗ trợ; kiểm source/API compatibility.
- **Runtime matrix:** cùng bytecode/test artifact được chạy trên các JVM hỗ trợ; kiểm runtime compatibility.
- **End-to-end matrix:** artifact/container triển khai thực tế với JDK, OS, DB và external services cụ thể.

Không nên xem một loại matrix là bằng chứng cho mọi loại.

### 14.2. Test selection phải giống nhau

Trên cả hai runtime, cần giữ cùng `useJUnitPlatform()`, test filters, tags, environment variables và nguồn fixtures. Test data/report output nên được phân vùng theo task để không ghi đè. Nếu một task phát hiện 200 test còn task khác chỉ 150, phải điều tra trước khi tuyên bố “cùng bộ test đều PASS”.

## 15. Maven: chạy wrapper với hai JDK được provision

Một cách thực tế là CI tạo hai jobs, mỗi job thiết lập JDK khác và chạy cùng command:

~~~bash
./mvnw clean verify
~~~

Trong cả hai jobs cần lưu:

- `./mvnw --version` và Java version của Maven.
- Maven Compiler Plugin/release.
- JDK của test fork theo cấu hình Surefire/Failsafe.
- Active profiles và test selection.
- JUnit engine/plugin và số lượng test được phát hiện.
- Dependency tree/resolved artifacts.

Maven Toolchains có thể cho compiler dùng JDK khác JVM chạy Maven, nhưng không mặc định mọi plugin và test fork dùng cùng toolchain. Nếu cần kiểm runtime hai JDK, đặt **đúng JVM cho test** và xác nhận bằng report.

Ví dụ compiler baseline Java 17:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Đây là cấu hình thuộc build POM; cần compiler/plugin version thực sự hỗ trợ. Nó không tự bảo đảm tất cả runtime dependencies chạy được trên Java 17.

## 16. CI matrix: cùng source, cùng suites, hai runtime

Một pipeline khái niệm:

~~~text
                     Commit X
                         |
                 Pin dependencies
                         |
               Prepare test fixtures
                         |
            +------------+------------+
            |                         |
        JDK OLD                  JDK NEW
            |                         |
      Wrapper build             Wrapper build
            |                         |
      Unit/contract             Unit/contract
      integration                integration
            |                         |
        Report A                 Report B
            |                         |
            +-----------+-------------+
                        |
                  Compare by ID
                        |
             Triage and go/no-go
~~~

Một YAML **pseudocode** độc lập nhà cung cấp CI:

~~~yaml
matrix:
  java:
    - "17"
    - "21"

forEachJob:
  checkout: "same commit"
  provisionJdk: "selected matrix version"
  run:
    - "java -version"
    - "./gradlew clean test"
  publishReports:
    - "build/test-results/test/"
    - "build/reports/tests/test/"
~~~

File này chỉ minh họa logic; không phải cấu hình có thể copy chạy trực tiếp trên GitHub Actions/GitLab/Jenkins. Khi triển khai, cần dùng syntax của CI provider, pin tool/action versions theo chính sách và cung cấp JDK/dependencies rõ ràng.

### 16.1. Khi cần OS matrix

Nếu application chạy trên Windows/Linux/macOS hoặc dùng JNI, file permissions, font, charset và external commands, có thể bổ sung OS/architecture matrix. Nếu production chỉ là Linux, ít nhất cần test artifact/container gần với Linux runtime thực tế.

Không nên mở một ma trận quá lớn rồi bỏ qua kết quả của các job chậm. Những tổ hợp được hỗ trợ phải có coverage và thời gian chạy hợp lý; những tổ hợp chưa kiểm cần được ghi rõ.

## 17. So sánh test inventory, không chỉ tổng số PASS

Một báo cáo hữu ích:

| Test ID | Old | New | Việc cần làm |
|---|---|---|---|
| `InvoiceCalculatorTest.preservesDecimalPrecision` | PASS | PASS | Không khác |
| `BillingDateServiceTest.usesVietnamBusinessDate` | PASS | FAIL | Kiểm timezone và dependency |
| `SecurityTest.rejectsInvalidCertificate` | FAIL | PASS | Đánh giá security fix/contract cũ |
| `PluginTest.loadsLegacyExtension` | PASS | NOT_RUN | Khôi phục coverage hoặc ghi limitation |
| `JdbcTest.roundTripDecimal` | FAIL | FAIL | Lỗi baseline hoặc hạ tầng chung |
| `ConcurrentTest.noLostUpdate` | FLAKY | FLAKY | Kiểm race và test fixture |

Tất cả dữ liệu trong bảng chỉ là **ví dụ**.

Một sai lầm là nói “cả hai bên đều 400 tests passed” trong khi danh sách khác nhau. Cần kiểm danh sách test identifiers và số lần thực sự chạy. Một số tool có thể thay đổi tên testcase cho parameterized tests; khi đó cần quy tắc ánh xạ test ID theo framework/plugin.

### 17.1. JUnit XML reports

Các build tools thường cung cấp báo cáo JUnit-style XML. Có thể so class/test names, failures, skips, execution time và thông tin configuration. Tuy nhiên, **thiếu XML report không có nghĩa test PASS**. Báo cáo phải phân biệt NOT_RUN và INCOMPLETE_REPORT.

Nếu upgrade làm một số test không còn được phát hiện, nguyên nhân có thể là:

- JUnit Jupiter engine thiếu hoặc version không tương thích.
- Surefire/Failsafe hoặc Gradle test runner thay đổi.
- Tags/profiles khác nhau giữa hai jobs.
- Test classes không compile.
- Test được disabled có điều kiện.
- Một task integration test không được nối vào pipeline.

## 18. JDBC, ORM và dữ liệu cũ: test cả hai chiều

Một lần nâng JDK có thể kéo theo đổi JDBC driver hoặc ORM. Regression suite cần bao gồm:

- SQL `NULL` khác 0, false và chuỗi rỗng.
- `BigDecimal` precision/scale/rounding.
- `DATE`, `TIME`, `TIMESTAMP`, timezone/DST.
- UUID, JSON, ARRAY, BLOB/CLOB theo vendor.
- Unicode, tiếng Việt và collation.
- Transaction commit/rollback, isolation, generated keys.
- Connection pool lifecycle, timeout và TLS.
- `SQLException`/`SQLState` nếu retry/error handling dựa vào chúng.

Cần thử **dữ liệu do phiên bản cũ đã ghi**. Chỉ ghi bằng driver mới rồi đọc lại bằng chính nó có thể bỏ sót lỗi backward compatibility.

Một ma trận mẫu:

| Driver | Server/schema | Mục tiêu |
|---|---|---|
| Cũ | Cũ | Baseline |
| Mới | Cũ | Khoanh vùng thay đổi driver |
| Mới | Mới | Trạng thái mục tiêu |
| Cũ | Mới | Chỉ thử nếu tổ hợp còn được hỗ trợ |

Không ép chạy tổ hợp unsupported; ghi lý do không chạy.

## 19. Sự cố chỉ có ở JDK mới: phân loại đúng trước khi sửa

| Triệu chứng | Điều tra ưu tiên |
|---|---|
| `invalid source release` | Compiler/toolchain không đúng |
| `UnsupportedClassVersionError` | Bytecode và runtime JDK không tương thích |
| `NoSuchMethodError` | API binary hoặc transitive dependency conflict |
| `ClassNotFoundException` | Packaging, classpath/module path |
| `InaccessibleObjectException` | Framework reflection và JPMS |
| `SSLHandshakeException` | Truststore, certificate, protocol |
| Timestamp lệch giờ | JDBC/ORM mapping, timezone/session setting |
| PDF khác font | Font availability, Java desktop/headless, image |
| Native library không load | OS/architecture, path, ABI, permissions |
| GC pause/memory khác | GC mặc định, heap sizing, workload, cgroup |
| Test fail chỉ CI | Environment, test isolation, seed, cache, credential |

Một lỗi xảy ra sau khi nâng JDK chưa chắc do JDK. Nếu đồng thời đổi build tool, framework và container, cần reproduction nhỏ hoặc test trung gian để xác định yếu tố gây khác biệt.

## 20. Test flaky và concurrency

JDK mới có thể thay đổi timing hoặc scheduling, khiến race condition đã tồn tại bộc lộ. Một test fail 1/20 lần không nên tự động coi là PASS sau khi retry.

Nên:

1. Giữ seed và fixture khi có thể.
2. Lưu lần chạy thất bại, stack trace và timing.
3. Chạy lặp lại cả hai môi trường nếu nghi flaky.
4. Kiểm shared state, thread-safety, timeouts và synchronization.
5. Đánh dấu FLAKY riêng trong report.
6. Không dùng retry vô hạn để che lỗi.

Test concurrency nên kiểm **invariants** (“không mất dữ liệu”, “không deadlock”, “cuối cùng đạt trạng thái hợp lệ”), không giả định thứ tự thread nếu ứng dụng không bảo đảm.

## 21. Hiệu năng phải so bằng workload, không bằng một unit test đơn lẻ

Một đơn vị test chạy 15 ms trên JDK cũ và 12 ms trên JDK mới **chưa chứng minh** môi trường mới nhanh hơn 20%. JIT, GC, warm-up, thread scheduling và CPU throttling có thể gây nhiễu.

Khi đánh giá performance regression:

- Giữ cùng request mix, dataset, concurrency và duration.
- Cố gắng giữ cùng CPU/memory limit, OS/architecture.
- Warm-up và lặp nhiều lần.
- Đo throughput, p95/p99 latency, error rate.
- Theo dõi GC pause, allocation, heap/metaspace, peak RSS.
- Xác nhận GC được chọn vì default có thể đổi giữa JDK.
- So theo SLO/resource budget, không yêu cầu biểu đồ giống từng pixel.

Có thể dùng JMH cho microbenchmark Java, nhưng không thay thế load test end-to-end. Performance suite thường là một phần riêng của CI/staging; không nên làm flakiness của unit suite tăng bằng assertions thời gian quá chặt.

## 22. Khi hành vi mới là thay đổi được chấp thuận

Không phải mọi khác biệt cần sửa để trở lại cũ. Ví dụ:

- JDK mới từ chối TLS/certificate yếu theo chính sách.
- Framework mới sửa một bug serialization.
- Application chủ động đổi API response theo versioning.
- JDBC driver mới trả một kiểu chính xác hơn, và hệ thống chấp nhận cập nhật hợp đồng.

Quy trình xử lý diff:

1. Xác định output/exception thay đổi cụ thể.
2. Kiểm release notes, issue và contract hiện tại.
3. Phân loại regression hay intentional change.
4. Xác định consumer bị ảnh hưởng và yêu cầu migration.
5. Nếu thay đổi được chấp thuận, cập nhật expected test có review.
6. Nếu là regression, sửa nguyên nhân và chạy lại.
7. Ghi owner, quyết định và phạm vi tương thích còn lại.

**Không sửa test cho PASS chỉ vì deadline**, và không tắt kiểm soát bảo mật để tái tạo một behavior cũ thiếu an toàn.

## 23. Tránh nhiễm chéo test giữa môi trường cũ và mới

Nếu hai CI jobs chạy song song, chúng không nên dùng chung mutable state trừ khi đó là chủ đề test.

Ví dụ:

~~~text
Run OLD:
  Database schema: regression_old_001
  Object store prefix: regression/old/001/
  Queue topic: regression-old-001

Run NEW:
  Database schema: regression_new_001
  Object store prefix: regression/new/001/
  Queue topic: regression-new-001
~~~

Khi không thể cô lập service, có thể chạy tuần tự và reset state một cách có kiểm chứng. Dùng cùng **fixture về mặt logic** không có nghĩa phải dùng chung một instance database được nhiều job ghi.

## 24. Mẫu báo cáo so sánh có thể review

~~~yaml
comparison:
  sourceCommit: "record actual commit"
  suiteId: "core-regression-v4"
  baseline:
    jdk: "old exact vendor/build"
    executed: 420
    passed: 418
    failed: 1
    skipped: 1
  candidate:
    jdk: "new exact vendor/build"
    executed: 420
    passed: 417
    failed: 2
    skipped: 1
  differences:
    newFailures:
      - "BillingDateServiceTest.usesVietnamBusinessDate"
    resolvedFailures: []
    missingTests: []
  evidence:
    baselineXml: "reports/old/"
    candidateXml: "reports/new/"
    dependencyGraph: "reports/resolution/"
  decision: "BLOCKED_PENDING_TRIAGE"
~~~

Mẫu này không phải kết quả test thực tế. Báo cáo đầy đủ nên kèm artifact digest, database/schema, OS/container, launch arguments, known issues, những test bị skip có lý do, và output diff cho mỗi testcase quan trọng.

Nếu test inventory khác nhau, báo cáo phải nêu rõ **coverage gap** thay vì kết luận dựa vào số PASS.

## 25. Quy trình thực hiện theo từng bước

### Bước 1: Chốt yêu cầu và phiên bản

Xác định JDK/stack nguồn và đích, người tiêu thụ API, contract cần giữ, Java minimum runtime và phạm vi OS/container.

### Bước 2: Lưu baseline trên môi trường cũ

Chạy build/test theo lệnh chuẩn, ghi commit, dependency versions, JDK, reports, known failures và fixtures.

### Bước 3: Xây core regression suite chung

Giữ cùng test IDs, input, assertions và selection rules. Những test chỉ áp dụng JDK/framework mới phải nằm trong suite riêng và ghi lý do.

### Bước 4: Kiểm soát nguồn nondeterminism

Clock, seed, locale, timezone, charset, file paths, database state, external service mocks và concurrency phải được quản lý.

### Bước 5: Provision JDK/build toolchain rõ ràng

Dùng wrapper, compiler release, test launcher và runtime flags thích hợp. Xác minh phiên bản Java thực sự chạy tests.

### Bước 6: Chạy candidate ở môi trường đích

Dùng cùng suite và fixture trong phạm vi hỗ trợ. Lưu logs, test XML, outputs và environment fingerprint.

### Bước 7: So test inventory

Kiểm số test được phát hiện, chạy, skip và thiếu. Không tiếp tục kết luận tương đương khi một số test quan trọng không được thực thi.

### Bước 8: So behavior và metrics

Phân tích giá trị, exception, contract outputs, dữ liệu lịch sử, TLS/security và performance theo SLO.

### Bước 9: Phân loại và xử lý differences

Phân biệt bug mới, lỗi baseline, thay đổi được phê duyệt, môi trường lệch hoặc flaky test. Chỉ sửa code/config/test expectation khi có nguyên nhân.

### Bước 10: Lưu quyết định phát hành

Ghi PASS/FAIL/NOT_RUN/BLOCKED/NOT_SUPPORTED, owner, risk acceptance, môi trường chưa kiểm và rollback/roll-forward plan.

## 26. Khi không thể dùng chính xác một bộ test

Một số tình huống bắt buộc khác biệt:

- API mới chỉ tồn tại trên JDK đích.
- Framework đổi namespace `javax.servlet` sang `jakarta.servlet`.
- Native/agent library không hỗ trợ JDK hoặc OS cũ.
- Database schema đổi không tương thích ngược.
- Security policy mới yêu cầu negative test khác.
- Tính năng mới không có tương đương trên baseline.

Khi đó nên chia:

~~~text
Core regression suite:
  contracts shared by old and new
  -> directly comparable

Migration-specific suite:
  removed APIs, module openness, new restrictions
  -> run where applicable

New-feature suite:
  features absent on old runtime
  -> no old-environment equivalence claim
~~~

Điều quan trọng là **không dùng bộ test khác nhau mà vẫn gọi là kết quả tương đương hoàn toàn**.

## 27. Những hiểu lầm thường gặp

**“Bộ test xanh trên JDK mới chứng minh không có hồi quy.”** Không, cần baseline và xác nhận cùng test inventory.

**“Cùng một lệnh Gradle nghĩa là cùng JDK test.”** Không, Gradle daemon, toolchain và test launcher có thể khác nhau.

**“Một file test compile trên Java 21 sẽ chạy Java 17.”** Không nhất thiết; phải kiểm `--release`, bytecode dependency và JVM thực.

**“Chỉ cần so tổng số test PASS.”** Không, test identities và skips mới giúp phát hiện coverage gap.

**“Có thể bỏ baseline vì nó đã có flaky tests.”** Baseline có vấn đề vẫn cung cấp thông tin nếu ghi rõ lỗi và tách chúng khỏi regression mới.

**“Snapshot khác thì tự cập nhật expected.”** Không. Cần hiểu hợp đồng nào đã thay đổi.

**“Cứ normalize output hết thì hai môi trường tương đương.”** Có thể che sai số, timezone, authorization hoặc format.

**“JDK mới siết TLS là lỗi phải bật lại cấu hình cũ.”** Có thể là thay đổi bảo mật đúng, cần sửa endpoint/chứng chỉ theo chính sách.

**“Retry cho đến khi test PASS là đủ.”** Không, test flaky hoặc bug concurrency vẫn tồn tại.

**“Performance tốt hơn trong một lần chạy nghĩa là JVM nhanh hơn.”** Cần workload, warm-up, nhiều lần đo và giới hạn tài nguyên tương đương.

**“NOT_RUN có thể xem là PASS.”** Không, đây là giới hạn bằng chứng.

**“Nếu đổi nhiều dependency thì không thể so test.”** Vẫn có thể so core contract suite; chỉ phải trung thực rằng nguyên nhân thay đổi không được cô lập hoàn toàn.

## 28. Checklist hoàn tất regression matrix

- [ ] Đã ghi JDK nguồn và đích bằng feature/update/vendor/build cụ thể.
- [ ] Đã lưu source commit, dependency graph và artifact version.
- [ ] Đã xác định câu hỏi chỉ đổi JDK hay đổi cả stack.
- [ ] Đã chốt core regression suite, test IDs, tags và profiles.
- [ ] Đã lưu baseline và known failures trước migration khi có thể.
- [ ] Đã xác minh compiler, `--release`, build JVM và test JVM.
- [ ] Đã giữ input fixtures, schema và service contracts nhất quán.
- [ ] Đã cô lập DB/queue/storage của những test runs song song.
- [ ] Đã kiểm clock, timezone, locale, charset, random seed và working directory.
- [ ] Đã kiểm source, binary, data, behavior và security theo rủi ro.
- [ ] Đã có negative tests và dữ liệu lịch sử nếu sản phẩm yêu cầu.
- [ ] Đã so danh sách testcase thực sự chạy và skips, không chỉ tổng PASS.
- [ ] Đã phân loại differences và không auto-regenerate expected vô điều kiện.
- [ ] Đã đo performance theo workload/SLO có kiểm soát.
- [ ] Đã chạy trên OS/container/JDK thuộc ma trận hỗ trợ.
- [ ] Đã đánh dấu NOT_RUN, BLOCKED hoặc NOT_SUPPORTED chính xác.
- [ ] Đã lưu JUnit XML, logs, outputs, artifact digest và environment fingerprint.
- [ ] Đã ghi những consumer và môi trường chưa được kiểm chứng.
- [ ] Đã có owner, go/no-go criteria và kế hoạch rollback/roll-forward.

## Kết luận

**Chạy cùng bộ kiểm thử trên môi trường cũ và mới là cách xây bằng chứng tương thích có thể đối chiếu**, không chỉ là thực thi hai lệnh build rồi xem cả hai đều màu xanh. Cần xác định chính xác baseline và candidate, giữ cùng core regression suite, dữ liệu và assertions, kiểm soát nondeterminism, xác minh JVM thực sự chạy test, rồi so test inventory, hành vi và các chỉ số vận hành.

Khi bắt buộc thay cả JDK, dependency và framework, hãy nói rõ giới hạn của phép so sánh, giữ contract tests và chia test thành các nhóm chung và riêng theo môi trường. Mọi khác biệt cần được phân loại thành hồi quy, thay đổi được phê duyệt, lỗi hạ tầng hay thiếu bằng chứng. Kết luận tốt phải trả lời được **test nào đã chạy, trên runtime nào, với dữ liệu nào, khác ở đâu và vì sao an toàn để phát hành**.
