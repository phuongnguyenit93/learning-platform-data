# Kiểm tra dependency có lỗ hổng bằng công cụ hoặc plugin phù hợp trong Gradle

## 1. Vấn đề cần giải quyết

Một ứng dụng Java có thể vượt qua `compileJava`, `test` và `check` nhưng vẫn đưa những thư viện chứa lỗ hổng đã được công bố vào `runtimeClasspath` hoặc artifact triển khai. Nguyên nhân phổ biến là các thư viện **trực tiếp** và **bắc cầu (transitive)** có vòng đời riêng: một dependency được thêm từ nhiều năm trước, một BOM giữ phiên bản cũ, hoặc một module bên thứ ba kéo thêm thành phần mà người phát triển chưa từng ghi trực tiếp trong `build.gradle.kts`.

**Software Composition Analysis (SCA)** là nhóm kỹ thuật kiểm kê các thành phần bên ngoài, xác định phiên bản thực tế và so khớp chúng với những nguồn dữ liệu lỗ hổng đã biết (như CVE, OSV và vendor advisories). Trong dự án Gradle, có thể chạy công cụ SCA dưới dạng plugin, CLI, scanner trên SBOM hoặc dịch vụ theo dõi tập trung.

Chủ đề thuộc nhóm **Chất lượng mã** của **Build Tool Gradle**, nhưng phạm vi SCA là **rủi ro từ thành phần phụ thuộc**, không phải quy tắc định dạng mã nguồn. Bài học cung cấp một workflow có thể áp dụng cho Java 17 và Gradle Kotlin DSL, ví dụ plugin **OWASP Dependency-Check**, lựa chọn **OSV-Scanner**, cách tạo **CycloneDX SBOM** và những nguyên tắc triage/CI.

Sau khi học, bạn sẽ biết:

1. Phân biệt dependency vulnerability scan với unit test, Checkstyle, Dependency Locking, Dependency Verification và SBOM.
2. Kiểm tra resolved dependency graph bằng `dependencies` và `dependencyInsight`, tránh đánh giá từ version được khai báo mà bỏ qua version được chọn.
3. Cài plugin `org.owasp.dependencycheck` và chạy `dependencyCheckAnalyze` trên project Java 17.
4. Hiểu nguồn NVD, CPE/PURL, CVE, CVSS, dữ liệu cũ, false positives và false negatives.
5. Thiết lập `failBuildOnCVSS`, `failOnError`, phạm vi configurations, report formats và NVD API key từ môi trường CI.
6. Biết khi nào dùng `dependencyCheckAggregate` cho multi-project builds và cách liên kết scan task vào `check`.
7. Tạo và quản lý kết quả HTML/JSON/SARIF; không suy ra “không có CVE” chỉ vì không có report.
8. Sử dụng OSV-Scanner v2 với Gradle lockfile hoặc verification metadata và hiểu giới hạn của cách đọc manifest.
9. Xuất CycloneDX SBOM và quét lại những thành phần đã resolve theo phạm vi của bản phát hành.
10. Phân loại phát hiện, đánh giá khả năng ảnh hưởng, chọn phiên bản sửa, kiểm tra cập nhật và quản lý suppressions có thời hạn.
11. Xây dựng quality gate cho CI không làm rò rỉ token/API key và không che mất lỗi scanner.
12. Hiểu giới hạn quan trọng: không tìm được CVE không đồng nghĩa thành phần an toàn; điểm CVSS cao không luôn phản ánh mức rủi ro ở từng hệ thống.

**Phiên bản minh họa:** OWASP Dependency-Check Gradle plugin `13.0.0` (bản trên Gradle Plugin Portal tháng 11/2026), CycloneDX Gradle plugin `3.5.1`, Java 17. Khi dùng với repository thật, hãy pin phiên bản plugin đã được tổ chức kiểm thử và kiểm tra yêu cầu Gradle Wrapper/JDK. Kết quả CVE và số lượng lỗ hổng phụ thuộc dữ liệu bảo mật tại **thời điểm thực hiện quét**, nên bài không hứa số phát hiện cố định.

## 2. Một lỗi phụ thuộc xuất hiện ở đâu trong Gradle?

Xét graph:

~~~text
:app
  |
  +-- implementation("com.example:business-client:1.0")
  |       |
  |       +-- transitive "com.vendor:json-core:2.0"
  |       +-- transitive "org.sample:codec:1.5"
  |
  +-- implementation("com.vendor:json-core:2.2")
  |
  +-- runtimeOnly("com.example:driver:3.0")
          |
          +-- transitive "org.sample:codec:1.7"
~~~

Gradle giải quyết yêu cầu phiên bản theo những rules áp dụng, có thể chọn `json-core:2.2` và `codec:1.7`, chứ không phải luôn giữ các version ở từng nhánh như source declarations.

**Scanner tốt cần xác định các thành phần đã được resolve thực tế**, bao gồm transitive modules và scope liên quan đến sản phẩm được phát hành. Nếu chỉ grep `build.gradle.kts` để tìm version, có thể bỏ lỡ dependency bắc cầu, substitutions, BOM constraints và những phiên bản đã được conflict resolution nâng lên.

Trong một Java project:

- `compileClasspath`: modules dùng khi compile.
- `runtimeClasspath`: modules có thể cần ở runtime; là scope đặc biệt quan trọng với application.
- `testCompileClasspath` và `testRuntimeClasspath`: libraries dùng cho test.
- `annotationProcessor`: annotation processors chạy trong quá trình biên dịch.
- Build plugins/buildscript classpath: chạy bằng quyền của build tool, rủi ro riêng.
- `provided`/`compileOnly`/container-provided libraries: có thể không nằm trong artifact cuối nhưng vẫn cần đánh giá môi trường triển khai tương ứng.

Với `java-library` được publish, cần xem cả dependencies công bố ở API/runtime variants. Với Spring Boot fat JAR hoặc Shadow JAR, cần xác minh tập components **thực tế được đóng gói**; dependency graph trong Gradle và artifact phát hành không luôn có phạm vi trùng hoàn toàn.

## 3. SCA, SBOM, vulnerability feed và remediation khác nhau

| Khái niệm | Trả lời câu hỏi | Không tự đảm bảo |
| --- | --- | --- |
| SCA vulnerability scan | Thành phần/version này có advisory nào đã biết? | Mọi lỗi bảo mật đều được phát hiện |
| Dependency graph | Những module nào thực sự được resolve và qua đường nào? | Module có an toàn hay không |
| SBOM | Trong phạm vi khai báo có những thành phần và quan hệ nào? | SBOM tự chứng minh không có CVE |
| CVE/advisory database | Có lỗ hổng công khai được gắn với package/phiên bản nào? | Không có false positive/false negative |
| CVSS | Mức độ nghiêm trọng theo mô hình đánh giá | Priority thực tế của từng tổ chức |
| EPSS | Ước tính xác suất khai thác theo mô hình dữ liệu tại thời điểm xem | Lỗ hổng chắc chắn sẽ/không bị khai thác |
| CISA KEV | Các CVE có bằng chứng bị khai thác theo danh mục chính thức | Đã áp dụng remediation cho app của bạn |
| Dependency locking | Phiên bản modules đã chọn có thay đổi không? | Integrity hoặc an toàn của JAR |
| Dependency verification | Byte artifact khớp checksum/chữ ký đáng tin không? | Artifact không chứa lỗ hổng logic |
| Java tests | Các hành vi đã được assert có đúng không? | Không có lỗ hổng từ dependency chưa được test |
| Security code review | Nghiệp vụ và luồng dữ liệu có vấn đề gì? | Thay thế việc cập nhật CVE feeds |

**Một kết quả “0 vulnerabilities” chỉ có nghĩa công cụ không phát hiện lỗ hổng theo phạm vi, dữ liệu, phiên bản và thuật toán nhận diện của lượt quét.** Nó không bảo đảm sản phẩm an toàn.

### 3.1. CVE, GHSA, OSV và tên định danh

- **CVE**: ID tham chiếu lỗ hổng được công bố, ví dụ `CVE-2021-44228`.
- **GHSA**: advisory ID trong GitHub Security Advisory Database.
- **OSV**: schema/API và database thống nhất các advisory liên quan open source.
- **NVD**: cơ sở dữ liệu lỗ hổng của NIST, có metadata/CVSS/CPE.
- **PURL**: Package URL, biểu diễn ecosystem + package coordinates, ví dụ Maven `pkg:maven/org.apache.commons/commons-lang3@3.14.0`.
- **CPE**: Common Platform Enumeration mô tả sản phẩm/phiên bản, hữu ích cho mapping NVD nhưng đôi khi dễ nhận diện nhầm Java JAR.
- **CWE**: loại điểm yếu phần mềm; không phải một lỗ hổng cụ thể đã xác định trong JAR.

Một lỗ hổng có thể xuất hiện dưới **nhiều ID nguồn**. Khi triage, cần xem aliases/affected versions thay vì đếm cùng một vấn đề nhiều lần.

### 3.2. Điểm CVSS 7.0 có nghĩa gì?

CVSS là một thang điểm severity thường từ 0 đến 10. Một quality gate “fail khi CVSS từ 7.0 trở lên” là chính sách **sàng lọc**, không phải phép đo xác suất bị tấn công trực tiếp vào ứng dụng đang triển khai.

Ví dụ một library chứa vulnerable function nhưng application không bao giờ gọi đường chạy đó vẫn cần điều tra reachability; ngược lại một lỗi CVSS trung bình nhưng bị khai thác tích cực và nằm trên đường public-facing có thể cần ưu tiên cao. Cân nhắc cả EPSS, KEV, attack surface, exposure, exploit prerequisites và mức độ quan trọng của dịch vụ.

## 4. Công cụ nào phù hợp với mục tiêu nào?

| Công cụ/cách tiếp cận | Ưu điểm | Điểm cần lưu ý |
| --- | --- | --- |
| **OWASP Dependency-Check Gradle** | Tích hợp task, nhận diện nhiều artifact types, báo cáo HTML/JSON/SARIF, CVSS gate | Dữ liệu NVD, CPE matching, initial update/cache, có false positives |
| **OSV-Scanner v2 CLI** | Đọc một số Gradle lockfiles/verification metadata, quét qua OSV DB, dễ thêm CI stage | Cần đúng lockfile/phạm vi; không tự resolve mọi graph Gradle nếu chỉ đọc manifest |
| **CycloneDX Gradle plugin** | Xuất SBOM từ resolved dependency graphs; dùng cho inventory/attestation/scanning downstream | Tạo SBOM **không tự tìm CVE** |
| **Dependency-Track** | Nhận SBOM, theo dõi inventory/advisories liên tục qua các bản phát hành | Cần vận hành server, auth, policy và truy xuất kết quả |
| **GitHub Dependabot/Dependency Review** | Hữu ích khi code ở GitHub, PR dependency changes và alerts | Phụ thuộc GitHub data/indexing, không mặc định là Gradle resolved runtime graph |
| **Snyk/Trivy/Grype và SCA thương mại** | Có thể tích hợp repo/image/SBOM/vulnerability DB khác | Phạm vi và license khác nhau; cần xác minh scanner support thực tế |

Không nhất thiết dùng mọi công cụ cùng lúc. Đối với Java Gradle project cần **scan ngay trong Gradle task graph**, OWASP Dependency-Check là một lựa chọn dễ minh họa. Đối với quy trình có lockfile và scanner CLI sẵn trong CI, OSV-Scanner có thể phù hợp. Đối với tổ chức cần quản lý vòng đời artifacts sau phát hành, nên phát hành SBOM và theo dõi liên tục.

**Quyết định dựa trên mục tiêu, không chỉ tên plugin:** cần scan local hay release artifact, PR hay nightly, dependency graph hay container image, support Java/Maven private repo ra sao, có offline mirror và SLA khắc phục hay không.

## 5. Thực hành đầy đủ: Gradle Java 17 + OWASP Dependency-Check

### 5.1. Yêu cầu môi trường

Bài thực hành dùng:

- Một JDK 17 để chạy app/toolchain; Gradle có thể chọn toolchain độc lập với JDK chạy Daemon.
- Gradle Wrapper thuộc phiên bản tương thích với plugin được pin.
- Gradle Plugin Portal để resolve `org.owasp.dependencycheck` hoặc plugin mirror hợp lệ.
- Maven Central (hoặc mirror được cho phép) để resolve application dependency.
- Khả năng cập nhật NVD vulnerability data (trực tiếp qua NVD API hoặc mirror nội bộ được duyệt).
- NVD API key **được khuyến nghị mạnh** để hạn chế throttling; không nhúng key vào source.

Plugin Dependency-Check 13.x có yêu cầu môi trường riêng; tài liệu dự án plugin ghi tương thích trong phạm vi các Gradle 7.6.4–9.x đã được kiểm thử, và Gradle JVM ít nhất Java 11. Với môi trường enterprise, luôn đối chiếu test matrix của **bản đang dùng**, không dựa đơn thuần vào ví dụ bài học.

Một lượt `dependencyCheckAnalyze` không chỉ chạy `javac`; nó còn cần tải hoặc truy cập vulnerability feeds. Vì vậy Java app có thể chạy ngay trong khi lượt scan đầu tiên vẫn lỗi network hoặc bị rate limit. **Đây là hai loại lỗi khác nhau.**

### 5.2. Cấu trúc dự án

~~~text
gradle-sca-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── src/
│   ├── main/
│   │   └── java/
│   │       └── demo/
│   │           └── Main.java
│   └── test/
│       └── java/
│           └── demo/
│               └── MainTest.java
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.properties
        └── gradle-wrapper.jar
~~~

Một project mới cần tạo Gradle Wrapper được phê duyệt trước khi chạy những lệnh dùng `./gradlew`. Không chép một JAR Wrapper hoặc SHA từ nguồn không đáng tin để thử bảo mật.

**settings.gradle.kts**

~~~kotlin
rootProject.name = "gradle-sca-demo"
~~~

### 5.3. build.gradle.kts đầy đủ

~~~kotlin
plugins {
    application
    id("org.owasp.dependencycheck") version "13.0.0"
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

dependencies {
    implementation(
        "org.apache.commons:commons-lang3:3.14.0"
    )

    testImplementation(
        platform("org.junit:junit-bom:5.10.2")
    )
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

dependencyCheck {
    // Chặn khi phát hiện vulnerability có CVSS >= 7.0.
    failBuildOnCVSS.set(7.0f)

    // Không coi scanner lỗi là một lượt kiểm tra thành công.
    failOnError.set(true)

    // Tạo báo cáo người đọc và máy đọc được.
    formats.set(listOf("HTML", "JSON"))

    // NVD API key được nhận qua biến môi trường, KHÔNG hardcode.
    nvd.apiKey.set(
        providers.environmentVariable("NVD_API_KEY")
    )
}

// Chỉ áp security gate vào check sau khi đã xác định policy.
// Bởi mặc định không được giả định scanner đã nối vào check.
tasks.named("check") {
    dependsOn(tasks.named("dependencyCheckAnalyze"))
}
~~~

**Ý nghĩa của cấu hình:**

1. `application` cung cấp Java plugin, source sets, `run` và Test task.
2. Plugin id `org.owasp.dependencycheck` được pin phiên bản `13.0.0`; không dùng version động.
3. Dependency production `commons-lang3` tạo một JAR có tọa độ cụ thể để SCA kiểm tra. Phiên bản ở đây chỉ là dữ liệu minh họa, **không được coi là đã đánh giá an toàn**.
4. Các JUnit dependencies chỉ ở test scope. Một scanner có thể bỏ test groups theo default; muốn scan cả test build toolchain phải xem scope chính xác.
5. `failBuildOnCVSS.set(7.0f)` tạo một quality gate cho vulnerability được scanner xác định đạt ngưỡng. Đây là **chính sách của bài lab**, không phải ngưỡng phù hợp với mọi tổ chức.
6. `failOnError.set(true)` ngăn việc scanner/data update gặp lỗi mà bị hiểu thành một lượt scan sạch.
7. `formats.set(listOf("HTML", "JSON"))` yêu cầu báo cáo dễ đọc và báo cáo dùng cho CI.
8. `nvd.apiKey` tham chiếu `NVD_API_KEY` từ môi trường. Không đưa API key vào file build, Git hay ví dụ in log.
9. `check.dependsOn(dependencyCheckAnalyze)` **thêm scanner vào quality gate**. Nếu chỉ apply plugin mà không có wiring này, đừng giả định mọi invocation `check` đều đã chạy SCA.
10. Ngoài việc gắn vào `check`, bạn vẫn có thể chạy task scan trực tiếp để chỉ tập trung bảo mật.

`DependencyCheckExtension` trong plugin 13.x dùng Gradle `Property` cho `failBuildOnCVSS`, `formats`, `failOnError` và NVD API key; mẫu trên dùng `.set(...)` để tránh nhầm với thuộc tính task không được quản lý. Khi dùng một version plugin cũ hơn, đối chiếu DSL tương ứng.

**Chú ý:** `NVD_API_KEY` có thể chưa được đặt trong môi trường. Ứng dụng Java và `test` vẫn có thể chạy; vulnerability scan thiếu key có thể chậm, bị giới hạn số yêu cầu hoặc không hoàn tất. CI nên cấp key bằng secret store.

### 5.4. src/main/java/demo/Main.java

~~~java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static String greeting(String name) {
        return "Xin chào, " + StringUtils.capitalize(name) + "!";
    }

    public static void main(String[] args) {
        System.out.println(greeting("gradle"));
    }
}
~~~

Đây là Java 17 hợp lệ và thực sự **sử dụng dependency bên ngoài**. Scanner có một module production để kiểm kê ngoài những JUnit modules phục vụ test.

### 5.5. src/test/java/demo/MainTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {

    @Test
    void capitalizesTheName() {
        assertEquals(
            "Xin chào, Gradle!",
            Main.greeting("gradle")
        );
    }
}
~~~

Test xác nhận behavior, **không kiểm tra CVE**. Một test pass không chứng minh Commons Lang không chứa vulnerability; một vulnerability advisory không tự chứng minh test logic hiện tại fail.

### 5.6. Chạy Java app và unit test

Linux/macOS:

~~~bash
./gradlew --quiet run
./gradlew test --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --quiet run
.\gradlew.bat test --console=plain
~~~

**Stdout chính xác do `demo.Main` in ra:**

~~~text
Xin chào, Gradle!
~~~

JUnit test có **1 testcase**, expected pass khi compile/runtime dependencies resolve được. Logs của Gradle/JUnit không có một số dòng cố định vì phiên bản, cache, OS, Gradle console mode và build result khác nhau.

Có thể đối chiếu Java thuần bằng javac sau khi Gradle đã tải dependencies, nhưng phải tự cung cấp đúng Commons Lang JAR trên compile/runtime classpath. Vì đó là dependency ngoài JDK, **không thể** compile ví dụ `Main.java` chỉ bằng `javac Main.java` mà không có JAR. Đây là điểm giúp phân biệt dependency management của Gradle với `javac` cơ bản.

### 5.7. Chạy scan bảo mật

Linux/macOS:

~~~bash
./gradlew dependencyCheckAnalyze --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencyCheckAnalyze --console=plain
~~~

**Kết quả cần kiểm chứng**: task thực hiện phân tích dependencies được cấu hình, có thể update NVD cache, tạo report HTML/JSON và trả status theo `failOnError`/`failBuildOnCVSS`.

Đường dẫn reports theo plugin 13.x thường là:

~~~text
build/reports/dependency-check/dependency-check-report.html
build/reports/dependency-check/dependency-check-report.json
~~~

Plugin dùng Gradle reporting base directory; nếu đã thay `outputDirectory`, file nằm tại nơi cấu hình tương ứng. Trước khi đánh giá CI, hãy xác nhận report file **thực sự tồn tại, có các packages được quét và timestamp tương ứng với lượt scan**.

**Không đưa ra stdout giả dạng “0 vulnerabilities” hoặc “1 CVE”**: dữ liệu NVD thay đổi theo thời gian, classifier có thể khác và scanner có thể chưa tải được feed. Với bài lab, điều chắc chắn là source/output Java; còn vulnerability count phải lấy từ report thực tế.

### 5.8. Chạy quality gate

Do đã khai báo `tasks.named("check") { dependsOn(...) }`:

~~~bash
./gradlew check --console=plain
~~~

Task graph bao gồm Java `test` **và** `dependencyCheckAnalyze`. Nếu một test fail, hoặc scanner gặp lỗi (với `failOnError=true`), hoặc lỗ hổng do scanner xác định đạt mức CVSS gate, `check` sẽ không thể hoàn thành thành công.

Muốn kiểm tra graph mà không chạy scan:

~~~bash
./gradlew check --dry-run --console=plain
~~~

`--dry-run` chỉ xác nhận task selection, **không** download vulnerability data, không quét JAR và không chứng minh clean security report.

## 6. Bốn task của OWASP Dependency-Check Gradle plugin

| Task | Chức năng |
| --- | --- |
| `dependencyCheckAnalyze` | Phân tích dependencies của project, tạo report |
| `dependencyCheckAggregate` | Phân tích ở phạm vi multi-project/aggregate theo plugin |
| `dependencyCheckUpdate` | Cập nhật local NVD/cache vulnerability data |
| `dependencyCheckPurge` | Xóa local NVD database của plugin để rebuild dữ liệu |

**Không nhầm `dependencyCheckUpdate` với Gradle `--refresh-dependencies`.** Lệnh đầu cập nhật vulnerability database của scanner; lệnh sau ảnh hưởng resolution/caching thông tin dependencies của Gradle. Một scan muốn chính xác phải có cả dependency graph cần thiết và vulnerability feed đủ mới.

### 6.1. Khi nào dùng Analyze?

Dùng `dependencyCheckAnalyze` để scan một project Java; trong một multi-project build, có thể áp plugin ở từng project hoặc chọn task paths phù hợp. Phải đánh giá phạm vi thật của cấu hình đó: nó có quét `runtimeClasspath`, test groups, annotation processor, custom configurations hay artifact packaging không?

### 6.2. Khi nào dùng Aggregate?

Với nhiều subprojects `:core`, `:api`, `:app`, plugin có `dependencyCheckAggregate` để tạo báo cáo tổng hợp. Nên apply trên root hoặc application project theo kiến trúc và đọc plugin docs cho chính version đó.

Ví dụ ở root (mẫu **riêng**, không phải file đơn module ở mục 5):

~~~kotlin
plugins {
    id("org.owasp.dependencycheck") version "13.0.0"
}

tasks.named("check") {
    dependsOn(tasks.named("dependencyCheckAggregate"))
}
~~~

Đoạn này **giả định root có `check` task** do Base/Java plugin hoặc build logic cung cấp; nếu không có, phải apply `base` hoặc tạo lifecycle policy hợp lý. Với root project chỉ apply Dependency-Check, bạn có thể chạy `./gradlew dependencyCheckAggregate` trực tiếp mà không cần đặt `check` ở root.

**Không nối cả `Analyze` lẫn `Aggregate` cho tất cả subprojects một cách vô ý**, vì có thể quét trùng và tiêu tốn NVD API requests/cache. Thiết kế một chiến lược: scan per-module phục vụ module owner, hoặc aggregate phục vụ release/security gate, hoặc cả hai với cadence rõ ràng.

### 6.3. Update và Purge

~~~bash
./gradlew dependencyCheckUpdate --console=plain
~~~

Dùng khi muốn cập nhật CVE data cache. Với CI nên có cache/mirror có kiểm soát và policy về data age, không ép mọi ephemeral runner tải full database ngay trong mỗi PR.

~~~bash
./gradlew dependencyCheckPurge --console=plain
~~~

Chỉ dùng khi cần xử lý cache/database hỏng, schema incompatibility hoặc quy trình nâng cấp plugin. **Purge không phải cách “fix CVEs”**; nó xóa dữ liệu scanner, và lần quét sau phải tải lại feed, có thể chậm hoặc vượt rate limit.

## 7. NVD API key, nguồn dữ liệu và rate limiting

OWASP Dependency-Check hiện dùng NVD API để cập nhật nguồn CVE data; việc tải đầy đủ lần đầu có thể nặng, và NVD áp rate limits. Từ Dependency-Check 9+, team phát triển khuyến nghị dùng **NVD API key**. Các bản cũ hơn 12.1.0 đã bị ảnh hưởng bởi thay đổi NVD API trong giai đoạn 2026; dùng plugin được hỗ trợ và chú ý migrations.

### 7.1. Cấp secret bằng môi trường

Tại máy cá nhân, cấu hình `NVD_API_KEY` theo cơ chế quản lý bí mật của hệ điều hành hoặc secret manager. Không đưa key thật vào source, screenshot, CI log hoặc command được lưu trong shell history.

Trong Gradle Kotlin DSL như phần 5:

~~~kotlin
dependencyCheck {
    nvd.apiKey.set(
        providers.environmentVariable("NVD_API_KEY")
    )
}
~~~

CI secret store cấp giá trị biến đó **chỉ cho job tin cậy**. Nếu secret chưa có, policy có thể yêu cầu fail sớm với thông báo thiếu key trong workflow thay vì chạy một lượt scan cực chậm. Không nên hard-code key vào `gradle.properties` được commit.

### 7.2. Dữ liệu cũ cũng là một rủi ro

Một cache được cập nhật tuần trước có thể chưa biết advisory mới vừa công bố. Quality gate cần theo dõi:

- Last successful feed update.
- Age của NVD database / cache.
- HTTP errors, 429/403 rate limiting.
- Scanner/plugin version.
- Suppression policy và thời hạn hiệu lực.
- Report timestamp/scan coverage.

`autoUpdate` mặc định bật; không tắt nó vĩnh viễn chỉ để CI chạy nhanh hơn. Nếu buộc chạy offline, phải có quy trình **sync feed hoặc NVD data mirror** và đo độ tươi của dữ liệu.

### 7.3. Vì sao nhiều pipeline dùng mirror NVD?

Nếu 20 build jobs cùng cập nhật toàn bộ NVD database, có thể gây rate-limit và tăng thời gian CI. Một thiết kế tốt:

~~~text
NVD API / authorized feed
            |
            v
controlled update/mirror job
            |
            v
managed cache/data feed
            |
            +--> PR scanner jobs
            |
            +--> nightly aggregate scan
            |
            +--> release security gate
~~~

Chọn mirror theo cơ chế được Dependency-Check hỗ trợ (`nvd.datafeedUrl`, data/cache options), bảo vệ integrity và credentials. **Không coi một mirror tự xây là đáng tin chỉ vì scan nhanh**. Nếu cache hỏng, xác định nguyên nhân trước khi purge.

### 7.4. Fail closed khi scanner lỗi

`failOnError=true` nghĩa là lỗi scanner có thể làm build fail, tách bạch **“không thể kiểm tra”** với **“đã kiểm tra và không phát hiện”**. Với pipeline release, đây thường là lựa chọn an toàn. Nếu hệ thống cần resilience khi NVD tạm ngừng, có thể tách scanner thành required security stage với retries, cache/mirror và SLA, thay vì đổi `failOnError=false` và bỏ qua scan mà không ai biết.

## 8. CVSS gate: default không phải policy an toàn

Một chi tiết rất quan trọng trong OWASP Dependency-Check Gradle docs: `failBuildOnCVSS` có default **11**, trong khi CVSS scores thường nằm từ 0 đến 10. Vì vậy **default có thể không làm build fail chỉ vì tìm thấy CVE**. Muốn có gate, phải đặt threshold có chủ đích.

Ví dụ:

~~~kotlin
dependencyCheck {
    failBuildOnCVSS.set(7.0f)
    failOnError.set(true)
}
~~~

Đây là **mảnh DSL** để thêm/sửa trong project đã apply plugin, không phải file build độc lập.

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `failBuildOnCVSS` | Ngưỡng CVSS từ đó scan có thể fail build |
| `failOnError` | Lỗi thực thi scanner/update dữ liệu có làm fail không |
| `junitFailOnCVSS` | Ngưỡng riêng khi xuất report định dạng JUNIT |
| `format` / `formats` | Chọn định dạng report |
| `skipTestGroups` | Bỏ qua một số test dependencies theo rule của plugin |
| `scanConfigurations` | Chỉ định configurations được quét |
| `skipConfigurations` | Chỉ định configurations bỏ qua |
| `suppressionFile(s)` | Áp suppression được review |
| `failBuildOnUnusedSuppressionRule` | Có fail nếu suppression rule không còn match không |

**`scanConfigurations` và `skipConfigurations` loại trừ nhau**: không đặt cả hai theo những danh sách xung đột. `skipTestGroups` mặc định `true` trong plugin docs; muốn đánh giá JUnit/test tooling phải xem riêng scope và có thể thay policy.

### 8.1. Severity không phải remediation priority duy nhất

Một CVE có CVSS 9.8 có thể không reachable trong app nhưng vẫn cần ghi nhận, xác minh, review exception hoặc cập nhật. Một CVE 6.5 nằm ở public internet-facing endpoint và trong CISA KEV có thể cần ưu tiên rất cao. Team nên viết **quy tắc triage** kết hợp severity, known exploitation, reachability, exposure và time-to-fix, thay vì “CVSS 7.0 là tất cả”.

### 8.2. Không che lỗi bằng ngưỡng 11

Một cấu hình dùng `failBuildOnCVSS=11.0` có thể hữu ích khi đang thu thập baseline reports, nhưng **đó là audit mode**, không phải security gate. Nếu `check` kết thúc thành công trong audit mode mà report có vulnerability, CI phải thể hiện trạng thái audit và có backlog/owner, không tuyên bố scan pass về mức rủi ro.

## 9. Chọn phạm vi quét: runtime, test, annotation processor, plugins

Một ứng dụng Java có thể có nhiều Gradle configurations. SCA không phải chỉ là đọc những dòng `implementation` hiện trong source.

### 9.1. runtimeClasspath

Đối với application, `runtimeClasspath` thường là điểm bắt đầu quan trọng vì chứa các JAR mà app cần khi chạy. Kiểm tra:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --console=plain
~~~

Nếu tìm thấy một module trong report security mà bạn không khai báo trực tiếp, dùng `dependencyInsight`:

~~~bash
./gradlew dependencyInsight \
  --dependency commons-lang3 \
  --configuration runtimeClasspath \
  --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath --console=plain
~~~

`dependencyInsight` cho biết selected version, requested versions, selection reasons và các paths đưa module vào graph. Nó **không tự trả thông tin CVE**, nhưng giúp tìm nơi cần nâng version hoặc thay dependency.

### 9.2. test dependencies

Test libraries không nhất thiết đi vào production JAR, nhưng vẫn có thể chứa lỗ hổng ảnh hưởng CI/test runners hoặc làm tăng attack surface khi tests xử lý dữ liệu không tin cậy.

Trong plugin docs, `skipTestGroups` mặc định `true`. Nếu tổ chức có policy quét cả test tooling, có thể cấu hình:

~~~kotlin
dependencyCheck {
    skipTestGroups.set(false)
}
~~~

Đây là **mẫu bổ sung**; cách nhận diện test groups còn phụ thuộc plugin/configuration names. Hãy kiểm tra report đã có test dependencies như kỳ vọng, không chỉ nhìn flag.

### 9.3. annotation processors và Gradle build plugins

Một annotation processor và một Gradle plugin chạy trong build/CI với quyền đọc file, chạy code và có thể truy cập network. Chúng có rủi ro supply chain riêng, không nên bị loại khỏi threat model chỉ vì không được đóng gói trong runtime JAR.

OWASP plugin có `scanBuildEnv` (mặc định `false` theo docs) để mở rộng một số phạm vi build environment. Tuy nhiên phạm vi plugin DSL resolution, buildscript và included builds có nhiều chi tiết; **không coi scanBuildEnv=true là bảo đảm quét mọi binary mà Gradle đã tải**.

Với hệ thống quan trọng, bổ sung policy review plugin versions, plugin repositories, dependency verification và scanner cho build toolchain. Phân biệt rõ **application dependencies** với **build dependencies** trong reports và ownership.

### 9.4. Kiểm tra custom configurations

Nếu team dùng `providedRuntime`, `developmentOnly`, `integrationTestRuntimeClasspath` hoặc một configuration riêng, có thể cần chọn:

~~~kotlin
dependencyCheck {
    scanConfigurations.set(
        listOf("runtimeClasspath", "testRuntimeClasspath")
    )
}
~~~

Mảnh DSL này **chỉ có ý nghĩa** nếu project có các configuration được nêu và bạn chủ ý giới hạn scanner ở đó. Nếu chỉ quét 2 configurations, những modules ở annotationProcessor/custom scopes có thể **không còn được kiểm tra**; cần chính sách bổ sung.

Không đặt `scanConfigurations` ở root multi-project và cho rằng tất cả modules đều có cùng configuration names.

### 9.5. Fat JAR, container image và deployment

Một Spring Boot executable JAR có thể đóng gói nested JARs. Docker image còn có OS packages, base image libraries và JDK runtime. Scan Gradle dependencies **không thay thế** scanning image/artifact cuối.

Một quy trình release thường cần:

~~~text
Resolved Gradle graph
       |
       +--> Dependency/SBOM scan
       |
       v
Packaged JAR/WAR
       |
       +--> Artifact scan (nếu yêu cầu)
       |
       v
Container image
       |
       +--> OS/JDK/application image scan
       |
       v
Deployment policy
~~~

**SBOM phải khớp boundary của artifact được gắn kèm.** Không lấy aggregate SBOM của toàn monorepo gắn cho một service JAR mà không giải thích rõ scope.

## 10. Đọc report đúng cách

Với OWASP Dependency-Check, báo cáo HTML cung cấp summary và chi tiết findings, trong khi JSON/SARIF thuận tiện cho tự động hóa/triage.

Một bảng kiểm kê trong report có thể nêu:

| Trường | Ý nghĩa |
| --- | --- |
| Dependency filename/coordinates | Artifact được xác định, có thể là JAR/POM/module |
| Evidence / CPE / PURL | Dữ liệu và mã định danh dùng để match sản phẩm |
| CVE/advisory ID | Lỗ hổng công khai được liên kết |
| Affected version / fixed version | Phạm vi versions bị ảnh hưởng và bản vá nếu nguồn hỗ trợ |
| CVSS / severity | Điểm/mức nghiêm trọng theo nguồn và phiên bản scoring |
| References | NVD/vendor advisory/changelog |
| Suppressed | Finding đã bị áp ngoại lệ (nếu có) |
| Scan timestamp / database age | Khi nào và với dữ liệu nào lượt scan chạy |

**Không lấy report làm dữ liệu bất biến.** Khi NVD hoặc vendor cập nhật mapping/affected range/CVSS, một scan chạy lại vào ngày khác có thể cho kết quả khác dù dependency graph không đổi.

### 10.1. Ví dụ diễn giải finding

Giả sử scanner nêu một transitive module `org.example:codec:1.7` có advisory. Đây là ví dụ **giả định**, không khẳng định module có thật hay có CVE.

Một quy trình kiểm tra:

1. Xác minh tọa độ và selected version trong report.
2. Đối chiếu Maven artifact metadata và dependencyInsight.
3. Xem advisory gốc, affected version range và fixed version.
4. Đánh giá `codec` có nằm trong production runtime/artifact không.
5. Kiểm tra phần mã/API dễ bị khai thác có reachable không, nhưng đừng vội dismiss nếu chưa có bằng chứng.
6. Tìm nâng version của parent dependency hoặc thêm constraint phù hợp.
7. Chạy lại scanner và tests.
8. Ghi quyết định và owner trong security ticket.

### 10.2. Vì sao CPE matching có false positives?

Một JAR name giống tên sản phẩm khác có thể bị scanner map nhầm sang CPE. Ví dụ một package Java có tên “xml-parser” có thể bị liên kết với product cùng tên nhưng publisher khác. Trước khi triage mức nghiêm trọng, phải so vendor/package identifiers, coordinates, CPE và advisory gốc.

Không suppress theo tên JAR quá rộng. Xác định rõ component identity và lý do kết luận false positive.

### 10.3. Vì sao có false negatives?

Scanner có thể bỏ sót do:

- Module không nằm trong selected scan configurations.
- Artifact bị shade/relocate mà metadata bị mất.
- CVE chưa được công bố hoặc chưa vào database.
- CPE/PURL match không đầy đủ.
- Database cache quá cũ.
- Repository private/internal không cung cấp metadata đúng.
- Vulnerability advisory chỉ có vendor-specific ID chưa được feed ingest.
- Component do CI download bằng script ngoài Gradle resolution.

Do đó **0 findings không thể là tiêu chí duy nhất** đánh giá an toàn.

## 11. Chọn phương án khắc phục: upgrade, replace, constraint, exclude

Khi finding xác thực và có bản sửa, ưu tiên nâng module đến version đã fix và được project kiểm thử. Nhưng trong Gradle graph có nhiều cách phụ thuộc vào cấu trúc thực tế.

### 11.1. Nâng direct dependency

Ví dụ bạn có:

~~~kotlin
dependencies {
    implementation("com.vendor:core:1.0")
}
~~~

Và vendor advisory cho biết phiên bản fixed phù hợp là `1.2` (tọa độ/version **chỉ minh họa**):

~~~kotlin
dependencies {
    implementation("com.vendor:core:1.2")
}
~~~

Sau đó xem graph, compile/test, integration test, ABI compatibility và scan lại. Đừng nâng vô tội vạ lên `latest.release` hoặc dynamic version chỉ để tiêu đi một finding, vì điều đó làm builds kém ổn định.

### 11.2. Transitive module: nâng parent hoặc dùng constraint

Giả sử `business-client:1.0` kéo `codec:1.7` có vấn đề; vendor đã test `codec:1.8`. Nếu sửa parent release có sẵn, **ưu tiên nâng parent**.

Nếu cần tạm áp một version constraint và đã kiểm tra compatibility:

~~~kotlin
dependencies {
    implementation("com.example:business-client:1.0")

    constraints {
        implementation("org.example:codec:1.8") {
            because(
                "Bản codec này đã được đánh giá và kiểm thử theo advisory"
            )
        }
    }
}
~~~

Đây là **mảnh ví dụ** với tọa độ và version giả định, không phải một công thức sửa CVE có thật. Constraint tham gia version selection khi module xuất hiện trong graph; nó **không tự thêm module** nếu chưa có dependency.

Kiểm tra:

~~~bash
./gradlew dependencyInsight \
  --dependency codec \
  --configuration runtimeClasspath
~~~

### 11.3. Exclusion không phải “xóa CVE” bằng mọi giá

Nếu module bắc cầu thực sự không được dùng, có thể loại trừ có chủ đích:

~~~kotlin
dependencies {
    implementation("com.example:business-client:1.0") {
        exclude(
            group = "org.example",
            module = "unused-codec"
        )
    }
}
~~~

Nhưng nếu library cần `unused-codec` ở runtime, exclusion có thể gây `NoClassDefFoundError` hoặc hành vi sai. Phải chạy integration tests và kiểm tra packaged artifact.

**Tìm remediation tận gốc, không chỉ làm report mất một dòng CVE.**

### 11.4. BOM/platform và lockfile

Nếu project quản lý một family version qua Maven BOM hoặc Java Platform, nên update BOM/platform để các modules tương thích, rồi cập nhật dependency locks nếu dùng locking. Không chỉ ép một JAR bất kỳ từ family lên version cao hơn khi vendor yêu cầu cùng một release train.

Nhớ:

- Gradle **Version Catalog**: aliases và declared versions.
- Gradle **Platform/BOM/constraints**: các yêu cầu phiên bản tham gia resolution.
- `gradle.lockfile`: selected module versions đã được khóa.
- Dependency verification: byte artifact có khớp trusted hash/signature hay không.
- Vulnerability scanner: những versions/artifacts ấy có advisory nào đã biết.

Các lớp này có thể dùng cùng nhau; không lớp nào thay thế toàn bộ lớp còn lại.

## 12. OSV-Scanner: lựa chọn CLI cho lockfile và SBOM

**OSV-Scanner v2** có cách làm khác OWASP Dependency-Check. Nó nhận diện dependencies từ những formats được hỗ trợ rồi đối chiếu OSV vulnerability database.

Theo danh sách format của OSV-Scanner v2, các file Java có thể được hỗ trợ bao gồm:

- `gradle.lockfile` (Gradle dependency locking).
- `buildscript-gradle.lockfile`.
- `gradle/verification-metadata.xml`.
- `pom.xml`.
- Một số artifact/binary/SBOM formats khác tùy subcommand.

Với Gradle, **scan một resolved lockfile thường đáng tin hơn chỉ scan text `build.gradle.kts`**, bởi lockfile chứa versions đã chọn. Không suy đoán OSV-Scanner có thể tự resolve mọi dynamic dependency đang khai báo trong một build file bất kỳ.

### 12.1. Tạo lock state cho Java project

Bổ sung vào `build.gradle.kts` của Java project:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau đó resolve đúng configuration:

~~~bash
./gradlew dependencies \
  --configuration runtimeClasspath \
  --write-locks \
  --console=plain
~~~

Với project một module, file thường là:

~~~text
gradle.lockfile
~~~

Nếu là multi-project, lockfile nằm theo project, chẳng hạn `app/gradle.lockfile`, và phải resolve đúng configurations của mỗi project. Lockfile không tự sinh cho mọi configuration nếu task chưa resolve chúng.

**Review rồi commit lockfile** vì nó là một phần của version policy. Đừng sửa tay để “bỏ CVE” mà không update dependency graph.

### 12.2. Quét bằng OSV-Scanner v2

Sau khi cài **binary OSV-Scanner v2 chính thức** theo hướng dẫn dự án, chạy từ project root:

~~~bash
osv-scanner scan source -r .
~~~

Hoặc nhắm một lockfile cụ thể:

~~~bash
osv-scanner scan source --lockfile=gradle.lockfile
~~~

Đây là CLI bên ngoài Gradle, không phải một task do Java plugin tự tạo. `-r` quét đệ quy các lockfile/manifest/SBOM được scanner hỗ trợ; trong monorepo nó có thể tìm nhiều files và thời gian quét dài hơn.

Kết quả CVE động theo thời điểm và dữ liệu OSV. Nếu scanner nhận thiếu format do version v1/v2 khác nhau, chạy `osv-scanner --help` và đối chiếu tài liệu v2 chứ không trộn syntax các major versions.

### 12.3. Một giới hạn quan trọng

Gradle `gradle.lockfile` thể hiện versions đã được khóa của **những configurations được resolve và bật locking**. Nếu project không tạo lockfile cho runtime hoặc artifact được publish không nằm trong phạm vi lock, OSV scan trên lockfile có thể bỏ sót components.

Nếu OSV-Scanner đọc `verification-metadata.xml`, file này còn có artifacts từ scopes khác và không nhất thiết mô tả chính xác một runtime artifact; vì vậy cần phân biệt **“tập artifacts được verify”** với **“tập runtime dependencies được triển khai”**.

### 12.4. Scan riêng hệ sinh thái Maven

OSV-Scanner hỗ trợ transitive resolution cho `pom.xml` trong phạm vi nêu ở tài liệu, nhưng một `pom.xml` **không mặc định giữ mọi Gradle variant/rule/resolution substitution**. Với Gradle-native build, ưu tiên dữ liệu resolved graph/SBOM hoặc lockfile đúng project.

### 12.5. Không cố nhét scanner CLI vào doLast của check

Một cách nhanh nhưng thiếu an toàn là:

~~~kotlin
tasks.named("check") {
    doLast {
        // Gọi shell command chưa khai báo input/output.
    }
}
~~~

Cách này làm task lifecycle khó cache/configuration cache và khó quản lý tool version/results. Nếu tích hợp OSV CLI vào Gradle, hãy dùng **task type chuyên biệt hoặc plugin có khai báo inputs/outputs**, và phụ thuộc vào task tạo SBOM/lockfile thích hợp. Đối với CI, chạy CLI ở một stage riêng thường rõ ràng hơn.

## 13. CycloneDX SBOM: kiểm kê trước, quét sau

**SBOM (Software Bill of Materials)** là danh sách thành phần và quan hệ thành phần của một sản phẩm. CycloneDX là một trong các định dạng phổ biến; một SBOM có thể được quét bởi OSV-Scanner, Dependency-Track hoặc nền tảng SCA khác.

CycloneDX Gradle plugin 3.x phân biệt **Direct SBOM** cho từng project và **Aggregate SBOM** cho build.

### 13.1. Tạo SBOM ở root project

Trong root `build.gradle.kts` (mẫu **riêng**, không phải code đầy đủ của project mục 5):

~~~kotlin
plugins {
    id("org.cyclonedx.bom") version "3.5.1"
}
~~~

Sau đó:

~~~bash
./gradlew cyclonedxBom --console=plain
~~~

Theo plugin 3.x, các đường dẫn đầu ra mặc định của aggregate thường là:

~~~text
build/reports/cyclonedx/bom.json
build/reports/cyclonedx/bom.xml
~~~

Direct SBOM của subprojects nằm dưới:

~~~text
<subproject>/build/reports/cyclonedx-direct/bom.json
<subproject>/build/reports/cyclonedx-direct/bom.xml
~~~

Tùy plugin version/config, root project cũng có direct SBOM. Kiểm tra file thật trước khi upload; đừng suy luận một artifact `:app:jar` sẽ bao hàm toàn bộ aggregate inventory của các module không được phân phối cùng app.

### 13.2. Direct vs Aggregate SBOM

| SBOM | Tốt cho | Điểm lưu ý |
| --- | --- | --- |
| Direct SBOM của `:app` | Gắn vào artifact/JAR do `:app` phát hành | Đảm bảo scope phù hợp packaging |
| Direct SBOM của `:lib` | Library riêng publish lên Maven | Mô tả module đó, không đại diện toàn hệ thống |
| Aggregate SBOM ở root | Inventory/review của nhiều project trong một build | Có thể chứa modules không nằm trong một service riêng |

Một SBOM được sinh từ resolved dependency graph **không tự bảo đảm** có mọi OS package trong container image, JDK runtime hoặc downloaded binary do custom task đưa vào. Muốn inventory triển khai đầy đủ cần bổ sung image/build artifact scanning.

### 13.3. Quét SBOM bằng OSV-Scanner

Với scanner v2 và một file CycloneDX phù hợp:

~~~bash
osv-scanner scan source -L build/reports/cyclonedx/bom.json
~~~

Theo OSV-Scanner docs, `scan source` có thể nhận SBOM/lockfile với `-L`, và hỗ trợ CycloneDX filenames đúng pattern. Nếu công cụ yêu cầu đuôi tên cụ thể, hãy xuất SBOM theo convention/plugin output hoặc truyền đường dẫn trực tiếp như trên.

**Quy tắc:** tạo SBOM ≠ tìm CVE. Cần một bước vulnerability matching và triage riêng. Nếu SBOM bị cũ so với binary deploy, vulnerability result cho SBOM đó không đại diện release mới.

### 13.4. Dependency-Track cho theo dõi liên tục

Khi tổ chức có nhiều services/release versions, một nền tảng như OWASP Dependency-Track có thể tiếp nhận SBOM, định danh project/version, lưu inventory và re-evaluate advisory changes định kỳ.

Các yếu tố cần quản trị:

- SBOM source và project identity.
- Mỗi lần release gắn đúng version/artifact.
- API tokens và phân quyền upload.
- Retention/policy và security tickets.
- Ownership của findings và review cadence.
- Không công khai SBOM chứa thông tin module nội bộ ngoài policy.

Không dùng Dependency-Track chỉ vì “có dashboard” nếu scanner kết quả không được phân loại/xử lý và không có owner.

## 14. False positives: điều tra trước khi suppression

SCA sử dụng heuristics, database aliases và matching. Một finding có thể **không áp dụng** cho một artifact cụ thể vì scanner gán nhầm CPE, package bị fork khác vendor, hoặc affected range được xác định sai.

Khi thấy một finding nghi false positive:

1. Ghi lại artifact coordinates (group:name:version), SHA-256 nếu có, package URL/CPE.
2. Mở advisory gốc, xem affected ranges và ecosystem.
3. Đối chiếu publisher/source repository và evidence của scanner.
4. Xác minh JAR đang dùng, classpath/packaging và runtime environment.
5. Ghi lý do không áp dụng, người duyệt và bằng chứng.
6. Nếu cần suppression, chỉ suppress **một finding đúng package/version/ID**, đặt thời hạn review.
7. Quét lại sau khi áp suppression để bảo đảm các findings còn lại vẫn hiển thị.

Không thấy vulnerability hiện ra sau suppression **không phải bằng chứng CVE đã được sửa**. Nó chỉ là một ngoại lệ về cách trình bày/gate.

### 14.1. OWASP Dependency-Check suppression XML

Plugin hỗ trợ `suppressionFile` hoặc `suppressionFiles`, đọc Checkstyle-style? **Không**: OWASP Dependency-Check suppression có **XML schema riêng**, không phải Checkstyle `suppressions.xml`.

Một suppression có thể khớp theo package/filename, CPE, CVE hoặc other fields tùy phiên bản engine. Đọc tài liệu suppression của Dependency-Check và xác định chính xác matcher; một regex quá rộng có thể che toàn bộ một thư viện.

Vì suppression sẽ bỏ qua phát hiện bảo mật, **bài không cung cấp một quy tắc suppress CVE thật để copy mù quáng**. Khi có false positive đã được review, hãy dùng suppression template do chính report/CLI của phiên bản scanner tạo ra, giới hạn identifier và gắn lý do/expiry.

Một đường dẫn cấu hình (chỉ khi file được cấp qua PR đã review):

~~~kotlin
dependencyCheck {
    suppressionFile.set(
        layout.projectDirectory.file("config/security/suppressions.xml")
            .asFile.absolutePath
    )
}
~~~

Đây là **mảnh tùy chọn** cho plugin với `suppressionFile` kiểu `Property<String>`; muốn áp dụng phải tạo file XML hợp lệ theo schema OWASP Dependency-Check, không dùng một Checkstyle suppression XML. Không thêm file rỗng chỉ để làm mất lỗi.

### 14.2. Expiry và unused suppression

OWASP Dependency-Check hỗ trợ thời hạn cho suppression rule và chế độ:

~~~kotlin
dependencyCheck {
    failBuildOnUnusedSuppressionRule.set(true)
}
~~~

Ý tưởng: nếu một suppression không còn match, CI có thể yêu cầu xóa exception cũ. Trước khi bật cho project lớn, review chính sách suppressions hiện có và version plugin; đừng áp dụng ngay nếu có nhiều rules legacy chưa được dọn.

### 14.3. Tránh suppress do chưa có bản fix

Một CVE được xác thực nhưng chưa có fixed version **không phải false positive**. Nếu cần chấp nhận rủi ro tạm thời, hãy ghi risk acceptance có owner, hạn xử lý và compensating controls. Không đánh đồng với suppression kỹ thuật để scanner im lặng.

## 15. False negatives: không thể chỉ tin report sạch

Một scanner không thể biết mọi lỗ hổng chưa được công bố, và nó còn chịu ảnh hưởng extraction quality.

Để giảm vùng mù:

- Scan đúng runtime dependency graph và final artifact/binary.
- Review shading/relocation/embedded JARs.
- Bổ sung image scanning nếu triển khai container.
- Quét build plugin và annotation processors trong pipeline riêng khi cần.
- Kiểm tra nguồn dữ liệu còn cập nhật và plugin version được hỗ trợ.
- Đọc vendor security bulletins nếu package hệ sinh thái chưa được OSV/NVD bao phủ tốt.
- Tạo SBOM và lưu cho released artifacts để có thể re-scan sau này.
- Không bỏ qua dependencies nằm trên classpath chỉ vì chúng không xuất hiện trực tiếp trong `build.gradle.kts`.
- Có cơ chế phát hiện failures/empty reports/zero scanned components, không biến “scan không chạy” thành “0 CVEs”.

### 15.1. Một trường hợp điển hình: shaded JAR

Nếu library A đóng gói lại mã của B bên trong chính JAR của A, Gradle graph có thể không còn dependency coordinate B. Scanner chỉ dựa vào metadata có thể bỏ lỡ B, hoặc gán sai version. Lúc này scanning final binary và xác minh provenance/package structure quan trọng.

### 15.2. Một trường hợp khác: native dependency

JNI/native `.so`/`.dll`, Alpine/Debian packages hoặc JDK image không phải Maven module. Java Gradle graph scanner không tự bao phủ chúng. Để release một container cần thêm image-level SBOM/SCA và kiểm tra base image.

## 16. Kiểm soát thay đổi bằng Version Catalog, BOM và dependency locking

**Version Catalog** có thể giúp tập trung khai báo version:

~~~toml
[versions]
commons-lang = "3.14.0"

[libraries]
commons-lang = {
    module = "org.apache.commons:commons-lang3",
    version.ref = "commons-lang"
}
~~~

Đây là **mảnh `gradle/libs.versions.toml`**, không thay `build.gradle.kts`. Nó giúp code review declared version, nhưng **không đảm bảo** một transitive dependency khác không buộc Gradle chọn version cao hơn.

**Java Platform/BOM** đưa constraints vào resolution graph để quản lý family versions. Tuy nhiên một BOM version có thể vẫn chứa lỗ hổng đã biết nếu vendor chưa sửa hoặc application pin release train cũ.

**Dependency locking** ghi resolved versions cho configurations:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Một lần update có kiểm soát:

~~~bash
./gradlew dependencies \
  --configuration runtimeClasspath \
  --write-locks \
  --console=plain
~~~

Sau đó review `gradle.lockfile` và quét CVE lại.

**Dependency Verification** kiểm tra checksum/signature artifacts, bảo vệ integrity, nhưng không chứng minh library không chứa CVE. **Wrapper distributionSha256Sum** bảo vệ ZIP Gradle distribution khi Wrapper download, không kiểm tra application dependencies.

Sơ đồ:

~~~text
Version Catalog/BOM/constraints
           |
           v
Gradle resolves versions
           |
           +--> dependency locking (pin selection)
           |
           +--> dependency verification (artifact bytes)
           |
           v
Runtime graph / packaged artifact
           |
           +--> OWASP Dependency-Check or OSV-Scanner
           +--> CycloneDX SBOM -> downstream scanner
           |
           v
Triage -> Upgrade/Replace/Mitigate -> Test -> Re-scan
~~~

Không nên bỏ lockfile hoặc verification metadata khi bắt đầu dùng scanner; các cơ chế bổ sung nhau.

## 17. Thiết kế CI/CD: PR, nightly và release

Một pipeline SCA vững nên chia rõ **scan execution**, **feed health**, **quality gate** và **remediation ownership**.

### 17.1. PR pipeline

- Chạy compile/unit tests.
- Scan các dependency versions được chọn hoặc SBOM mới.
- Fail nếu scanner lỗi theo policy.
- Fail nếu phát hiện CVE vượt ngưỡng và không có exception được duyệt.
- Upload reports dưới CI artifacts, giữ retention phù hợp.
- Review diff dependency declarations, BOM, lockfile và report security trước merge.

### 17.2. Nightly/recurring scan

Dù source không đổi, NVD/OSV có thể xuất advisory mới. Vì vậy build pass hôm qua **không bảo đảm** hôm nay không có finding. Nightly scan re-evaluate released projects là một chiến lược hữu ích:

- Update vulnerability feeds/mirror.
- Scan release SBOMs và active branches.
- Mở ticket cho findings mới.
- Phân loại severity, KEV, EPSS, exploitability.
- Theo dõi SLA xử lý và hết hạn exceptions.
- Không tạo lại artifact chỉ để kiểm tra nếu đã có versioned SBOM đáng tin.

### 17.3. Release pipeline

Với release, cần security gate phản ánh đúng artifact được triển khai, không chỉ source manifest. Một workflow minh họa:

~~~bash
set -e

./gradlew clean test --console=plain

./gradlew dependencyCheckAnalyze --console=plain

./gradlew assemble --console=plain
~~~

**Đây là một script minh họa** cho project đơn module ở phần 5. Nếu `check` đã phụ thuộc `dependencyCheckAnalyze`, có thể đơn giản hóa:

~~~bash
set -e
./gradlew clean build --console=plain
~~~

Nhưng chỉ khi đã kiểm chứng graph `check` thực sự có scanner và pipeline không có `-x dependencyCheckAnalyze` hoặc `failOnError=false`. Thứ tự scan vs assemble không nhất thiết bắt buộc; output/quality policy quyết định.

### 17.4. Vì sao không chỉ xem BUILD SUCCESSFUL?

Nếu `failBuildOnCVSS` đang ở default 11, báo cáo có CVE mức cao vẫn có thể đi cùng `BUILD SUCCESSFUL`. Nếu scanner bị skip hoặc `skip=true`, quality gate cũng có thể không chạy. CI phải quan sát:

1. Scanner task đã được chọn/thực thi thành công.
2. Report có danh sách dependencies được scan.
3. Feed timestamp và scanner version phù hợp.
4. Quality policy đã bật đúng threshold.
5. Không có suppressions không được duyệt.
6. Report thuộc đúng project/release build.

### 17.5. Lưu reports an toàn

HTML/JSON/SARIF có thể lộ tên dependencies, private Maven artifact names và paths. CI nên lưu trong artifact store có phân quyền, không đăng công khai mặc định. Không lưu NVD API key hoặc registry credentials trong report/log.

### 17.6. Fail vs monitor modes

| Mode | Khi nào phù hợp | Điều kiện |
| --- | --- | --- |
| Enforced gate | PR hoặc release có vulnerability policy ổn định | `failBuildOnCVSS` phù hợp, `failOnError=true`, report có thật |
| Monitor/audit | Codebase legacy chưa có lộ trình loại hết CVE | Báo cáo rõ findings, ticket/owner, hạn chuyển enforced |
| Nightly alerting | Phát hiện CVE mới sau release | Feed refresh, alert, SLA xử lý |
| Emergency exception | Vendor chưa có fix hoặc có blocking compatibility | Approval có thời hạn, scope hẹp, compensating controls |

Monitor mode không có nghĩa “quét xong là an toàn”; báo cáo phải được người chịu trách nhiệm đánh giá.

## 18. Bảng tình huống và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `dependencyCheckAnalyze` không tồn tại | Plugin chưa apply hoặc sai project/task path | Kiểm tra plugins block, `tasks --all`, root/subproject |
| Task fail trước khi có report | Lỗi plugin/Gradle/JDK, repositories, NVD API | Đọc stack trace và logs, không kết luận có CVE |
| NVD API 403/429 | Rate limit, thiếu/không hợp lệ key, nhiều CI jobs | Dùng secret hợp lệ, cache/mirror, exponential backoff theo tool docs |
| Lượt scan đầu tiên rất lâu | Full NVD data download và index | Dùng cache/mirror được quản lý, không vội tắt autoUpdate |
| Scanner báo H2 database incompatible | Nâng plugin/schema hoặc cache cũ | Đọc migration notes; purge có chủ đích |
| `BUILD SUCCESSFUL` nhưng report có CVE | CVSS threshold default 11 hoặc audit policy | Đặt failBuildOnCVSS, xác nhận gate wiring |
| `check` không chạy scanner | Chưa `dependsOn(dependencyCheckAnalyze)` | Bổ sung rõ ràng, kiểm tra --dry-run |
| Report không có test dependencies | skipTestGroups hoặc scan scope | Review skipTestGroups/scanConfigurations |
| Không thấy transitive JAR | Chỉ quét declared deps, artifact shaded/variant khác | Kiểm tra runtimeClasspath/final binary |
| CVE gắn nhầm artifact | CPE false positive | So vendor/purl/advisory, suppression hẹp sau review |
| Một CVE không được scanner tìm thấy | DB stale, CVE chưa ingest, scanner scope thiếu | Kiểm tra data source, graph, vendor advisory |
| Khác kết quả giữa local và CI | Cache age, plugin versions, repositories, scan scope | Pin versions, compare reports và graph |
| OSV không tìm Gradle deps | Thiếu lockfile, scan wrong directory, format không hỗ trợ | Tạo lockfile và dùng source scan -r đúng root |
| CycloneDX SBOM thiếu module | Direct vs aggregate hoặc disabled task | Kiểm tra source/aggregate boundaries |
| Scanner dùng nhiều RAM | NVD index/JAR analyzers | Tuning JVM/cache/runner resources, tránh concurrent full update |
| Scan report cũ tồn tại sau fail | Build dir còn artifact từ lần trước | Kiểm tra timestamp/job artifacts, clean output policy |
| Scanner lỗi mà build vẫn pass | failOnError=false hoặc scan không nằm trong graph | Gắn required stage và failOnError=true |
| Pin transitive version làm runtime lỗi | Constraint/exclude không tương thích ABI | Kiểm tra dependencyInsight và integration tests |
| Suppression hết hạn | Exception policy có deadline | Xem xét lại finding/fix, không gia hạn mù |
| Secret xuất hiện trong log | API key bị truyền/in không an toàn | Rotate/revoke key, sửa pipeline secret handling |
| Scan image cho ít CVE hơn Gradle | DB/scopes/component extraction khác nhau | So SBOM và coverage, không coi scanner nào luôn đúng |

## 19. Một ví dụ security triage có hệ thống

Giả định report của ứng dụng chứa:

~~~text
Module: org.example:codec:1.7
Path:   app -> business-client:1.0 -> codec:1.7
Finding: security advisory
Status: action required
~~~

Các coordinates và finding ở đây chỉ minh họa quy trình, **không phải một CVE được xác nhận ngoài đời**.

### Bước 1: xác định package và version thực tế

~~~bash
./gradlew dependencyInsight \
  --dependency codec \
  --configuration runtimeClasspath
~~~

Kiểm tra direct vs transitive, selected variant, requested versions và lý do conflict resolution.

### Bước 2: mở advisory chính thức

Xem affected/fixed versions, CVE aliases, attack vector, prerequisites, mitigations, vendor statement và các caveats về package. Đừng chỉ lấy một số CVSS từ summary.

### Bước 3: đánh giá ảnh hưởng

- Module có đóng gói vào artifact không?
- Class/method dễ bị tấn công có reachable từ input không tin cậy không?
- Có public endpoint hoặc deserialization/templating/network parser nào liên quan không?
- Có WAF/rate limits/sandbox/feature flags giảm exposure không?
- Vendor có fixed version tương thích hay bản vá backport không?
- Lỗi nằm ở CI/build tooling hay production runtime?

### Bước 4: đề xuất remediation

Ưu tiên nâng module cha hoặc BOM/platform theo vendor compatibility matrix. Nếu phải dùng constraint trực tiếp, cần tests và giải thích rõ tính tạm thời. Nếu không có fix, có thể tạm giảm attack surface hoặc disable feature theo risk acceptance đã duyệt.

### Bước 5: xác minh

Chạy unit/integration/regression tests, xem dependency graph mới, scan lại với feed cập nhật, so old/new report. Không chỉ so `BUILD SUCCESSFUL` mà bỏ qua report.

### Bước 6: đóng security ticket

Ghi bản fix, task/commit, bằng chứng scanner, owner và ngày hoàn thành; nếu chưa fix thì ghi exception expiry và monitoring plan.

## 20. Các rủi ro bảo mật riêng của scanner và build pipeline

Một SCA plugin tự nó cũng là **mã bên thứ ba chạy trong Gradle build**, có thể truy cập dependencies, local caches và network. Vì vậy:

- Pin plugin version từ nguồn đáng tin.
- Hạn chế plugin repositories.
- Dùng Gradle Wrapper chính thức và xác minh distribution/JAR theo policy.
- Dùng dependency verification cho artifact checksums/signatures.
- Không cho CI job từ untrusted fork PR tiếp cận `NVD_API_KEY` hoặc private registry credentials.
- Đừng log environment variables/secrets.
- Dùng cache paths với permissions phù hợp; không chia sẻ cache writeable giữa các security trust boundaries.
- Với external scanner CLI, dùng binary/OCI image đã được phê duyệt, pin version/digest.
- Kiểm tra outbound network và dữ liệu gửi tới dịch vụ SaaS trước khi upload SBOM/report nội bộ.

### 20.1. Cẩn trọng với dynamic vulnerability data

SCA reports không thuần deterministic như output từ một unit test: dữ liệu advisory có thể đổi. Để tái hiện một quyết định security, ghi scanner/plugin version, feed timestamps, project artifact version, lockfile/SBOM hash và report ID. Nhờ vậy team có thể phân biệt “dependency mới” với “advisory mới”.

### 20.2. Không download và thực thi một thư viện độc hại để test scanner

Để học cách cấu hình SCA, **không cần** thêm một dependency đã biết có lỗ hổng nghiêm trọng vào production project hoặc chạy PoC khai thác. Bài lab dùng Commons Lang bình thường và giải thích rằng số CVE tìm thấy có thể thay đổi. Nếu tổ chức cần kiểm thử policy báo lỗi CVE, hãy dùng một **fixture cô lập/kiểm tra file report giả lập** do security team kiểm soát, không trộn nó vào application artifact.

## 21. Đề xuất quy trình vận hành theo thời gian

Chỉ chạy scanner một lần khi tạo dự án chưa đủ vì CVE data xuất hiện liên tục. Một chương trình SCA thực tế gồm:

1. **Inventory:** biết mọi service, artifact, runtime và build-tooling dependency.
2. **Baseline:** scan phiên bản đang dùng và lập backlog.
3. **Gate:** đặt severity/risk thresholds cho PR và release.
4. **Refresh:** update vulnerability feeds hoặc mirror định kỳ.
5. **Triage:** phân biệt true/false positives, affected/exploitability.
6. **Remediate:** upgrade/replace/mitigate theo SLA.
7. **Verify:** test, re-scan, xem resolved graph, tạo SBOM mới.
8. **Exception:** approval có ngày hết hạn và trách nhiệm rõ.
9. **Monitor:** re-scan released SBOMs kể cả khi source không đổi.
10. **Audit:** lưu bằng chứng quyết định và hiệu quả chính sách.

Các chỉ số quản trị có thể gồm median remediation time, số findings quá hạn, tỷ lệ services được scan, feed freshness và số exceptions sắp hết hạn. Đừng tối ưu “0 findings” bằng cách giảm phạm vi scanner hoặc tăng suppressions.

## 22. Thực hành mở rộng: một build có nhiều Gradle modules

Giả sử:

~~~text
root/
├── settings.gradle.kts
├── build.gradle.kts
├── core/build.gradle.kts
├── api/build.gradle.kts
└── app/build.gradle.kts
~~~

**settings.gradle.kts**:

~~~kotlin
rootProject.name = "secure-multi-project"
include(":core", ":api", ":app")
~~~

Mỗi Java subproject có dependencies riêng. Trong trường hợp muốn báo cáo tổng hợp theo release:

- Apply OWASP Dependency-Check trên root hoặc application project phù hợp.
- Dùng `dependencyCheckAggregate`.
- Kiểm tra những modules được plugin bao phủ.
- Gắn root quality gate nếu root có `check` task; nếu không, sử dụng task trực tiếp từ CI.
- Nếu tạo CycloneDX Aggregate SBOM, nhớ rằng nó mô tả inventory của build, không tự chứng minh mọi module nằm trong một deployable unit.

Một root script minh họa **chỉ chuyên aggregate**:

~~~kotlin
plugins {
    base
    id("org.owasp.dependencycheck") version "13.0.0"
}

dependencyCheck {
    failBuildOnCVSS.set(7.0f)
    failOnError.set(true)
    formats.set(listOf("HTML", "JSON"))
    nvd.apiKey.set(
        providers.environmentVariable("NVD_API_KEY")
    )
}

tasks.named("check") {
    dependsOn(tasks.named("dependencyCheckAggregate"))
}
~~~

Đây không phải script đầy đủ cho các `:core`, `:api`, `:app`; chúng vẫn cần Java plugins/dependencies/repositories theo từng module. Với plugin 13.x, root aggregate phải được kiểm tra trên một repo thật để đảm bảo `scanProjects`/`skipProjects` và Gradle project graph khớp ý định.

Một CI command:

~~~bash
./gradlew dependencyCheckAggregate --console=plain
~~~

**Chỉ dùng một aggregate report làm release gate khi hiểu rõ nó đang quét project nào.** Để bảo vệ một service độc lập, một Direct SBOM hoặc per-project report gắn đúng release boundary có thể chính xác hơn.

## 23. Các lỗi hiểu nhầm cần tránh

### 23.1. “Gradle build pass nên dependencies an toàn”

Sai. `test`/`check` mặc định không nhất thiết chạy SCA. Ngay cả khi scanner được gắn, một project với `failBuildOnCVSS=11` có thể chỉ tạo report mà không fail vì vulnerabilities.

### 23.2. “Có gradle.lockfile thì không có CVE”

Sai. Lockfile pin module versions; các versions ấy vẫn có thể chứa lỗ hổng. Lock còn có thể giữ một vulnerable version lâu hơn nếu không cập nhật.

### 23.3. “Có checksum SHA-256 của JAR thì đó là JAR an toàn”

Sai. Checksum xác minh bytes khớp baseline; một artifact hợp lệ do nhà phát hành phân phối vẫn có thể có CVE hoặc bug logic.

### 23.4. “SBOM là kết quả quét lỗ hổng”

Sai. SBOM là inventory. Cần scanner/analyzer để nối packages/versions với advisories. Một SBOM cũ còn có thể không đại diện đúng deployed artifact.

### 23.5. “Cứ suppress tất cả false positives để report còn 0 findings”

Sai. Nếu suppression quá rộng hoặc không có expiry/owner, nhiều vấn đề thật sẽ bị che. Nên kiểm tra advisory và component identity trước rồi chỉ suppress trường hợp được duyệt.

### 23.6. “CVSS thấp là không đáng quan tâm”

Sai. Exposure và known exploitation có thể thay đổi risk priority; một CVE có CVSS trung bình nhưng có exploit đang được sử dụng hoặc đặt trên public endpoint có thể cần xử lý gấp.

### 23.7. “SCA báo finding là chắc chắn khai thác được”

Sai. SCA thường dựa package/version, không nhất thiết làm reachability analysis chi tiết. Cần xem vulnerable function, deployment context và vendor advisory. Tuy nhiên không được dùng câu “không reachable” như một cách dismiss thiếu bằng chứng.

### 23.8. “Không có API key thì lệnh scanner chắc chắn pass”

Sai. NVD API có rate limit, có thể trả lỗi hoặc download rất chậm. Cần monitor scanner health và credential handling.

### 23.9. “Quét runtimeClasspath đủ để bảo vệ CI”

Không đủ. Annotation processors/build plugins, toolchain downloads, custom scripts và CI actions có quyền thực thi ở build-time. Chúng cần kiểm soát supply chain riêng.

### 23.10. “Một lần scan ở PR bảo đảm release mãi an toàn”

Sai. Các advisory được cập nhật sau release. Cần re-scan SBOMs/released artifact inventory theo lịch và triage phát hiện mới.

## 24. Bài tập tự kiểm tra và đáp án

**Câu 1.** Project dùng `implementation("com.example:client:1.0")`, client kéo một codec bắc cầu. Chỉ đọc build.gradle.kts có đủ để thấy codec thực tế đã chọn version nào không?

**Đáp án:** Không. Xem `runtimeClasspath` và `dependencyInsight` vì Gradle resolution có thể chọn version khác requested version.

**Câu 2.** Trong OWASP Dependency-Check, command nào quét project theo plugin?

**Đáp án:**

~~~bash
./gradlew dependencyCheckAnalyze --console=plain
~~~

**Câu 3.** Vì sao `failBuildOnCVSS` default 11 chưa phải quality gate thích hợp?

**Đáp án:** CVSS thông thường không vượt 10; ngưỡng 11 không làm build fail chỉ vì một CVE, cần threshold có chủ đích.

**Câu 4.** `failBuildOnCVSS` và `failOnError` khác nhau thế nào?

**Đáp án:** Ngưỡng CVSS xử lý **phát hiện lỗ hổng**; `failOnError` xử lý **lỗi thực thi scanner hoặc data analysis**. Đừng nhầm “scan không chạy” với “scan đã sạch”.

**Câu 5.** Lệnh `./gradlew check` có tự động chạy Dependency-Check nếu mới apply plugin không?

**Đáp án:** Không nên giả định. Hãy nối `check.dependsOn(dependencyCheckAnalyze)` và xác minh task graph.

**Câu 6.** OSV-Scanner v2 có thể đọc Gradle lockfile không?

**Đáp án:** Có trong danh sách supported manifests, ví dụ `gradle.lockfile`. Tuy nhiên file phải ghi đúng những selected versions/configurations được resolve; thiếu file/scope sẽ làm coverage thiếu.

**Câu 7.** Một SBOM CycloneDX có tự kiểm tra CVE không?

**Đáp án:** Không. Nó mô tả components/relationships; cần SCA vulnerability matching riêng.

**Câu 8.** Vì sao ứng dụng Java main trong lab không có stdout CVE cố định?

**Đáp án:** Output Java (`Xin chào, Gradle!`) cố định theo code, nhưng scanner report phụ thuộc thời điểm, vulnerability feed, scope, matching và network state.

**Câu 9.** Có nên đưa NVD API key vào `build.gradle.kts` không?

**Đáp án:** Không. Dùng secret store/environment `NVD_API_KEY`; tránh log và đừng cấp cho untrusted PR jobs.

**Câu 10.** Checksum artifact đúng có chứng minh không tồn tại CVE?

**Đáp án:** Không. Checksum đo integrity, không đánh giá lỗ hổng logic.

**Câu 11.** Project có `-x dependencyCheckAnalyze` trong release build thì còn security gate không?

**Đáp án:** Không còn lượt scan từ task đó trong graph. Phải kiểm tra CI commands và report được tạo mới.

**Câu 12.** Khi scanner báo CVE cho transitive dependency, nên hành động đầu tiên là gì?

**Đáp án:** Xác minh component identity/version/advisory, tìm dependency path và đưa ra remediation có test; không exclude ngẫu nhiên để mất finding.

**Câu 13.** Một library chứa CVE nhưng function bị lỗi không reachable trong ứng dụng; có được coi là false positive ngay không?

**Đáp án:** Không. Đó là vấn đề risk/exploitability triage, cần bằng chứng reachability và policy acceptance; đừng đồng nhất với CPE/package matching sai.

**Câu 14.** Plugin OWASP có thể tạo báo cáo JSON không?

**Đáp án:** Có, khi cấu hình `format`/`formats` hỗ trợ JSON trong phiên bản plugin tương ứng.

**Câu 15.** CISA KEV và EPSS dùng để làm gì?

**Đáp án:** Là tín hiệu hỗ trợ ưu tiên remediation, bên cạnh CVSS, exposure và dependency impact; không phải công cụ đảm bảo code đã fix.

**Câu 16.** Vì sao test dependencies cũng có thể quan trọng?

**Đáp án:** JUnit/testing libraries và processors chạy trong CI, có attack surface khác production, cần policy phù hợp chứ không bỏ mặc định.

**Câu 17.** Một CVE mới được công bố sau khi release đã pass scan; giải pháp là gì?

**Đáp án:** Re-scan releases qua SBOM/recorded dependency inventory theo lịch, tạo ticket/alert và khắc phục theo SLA.

**Câu 18.** Lệnh `dependencyCheckPurge` làm gì?

**Đáp án:** Xóa cache dữ liệu NVD của scanner, không xóa các lỗ hổng trong dependencies. Chỉ dùng khi xử lý cache/schema theo runbook.

## 25. Checklist sẵn sàng đưa vào CI

1. Xác định Gradle Wrapper/JDK tương thích với phiên bản scanner plugin.
2. Pin plugin version; tránh dynamic/latest không review.
3. Đọc đúng project graph và các configurations scan được lựa chọn.
4. Bảo đảm runtime dependencies, transitive modules và packaged artifacts được bao phủ.
5. Cấp NVD API key bằng secret store hoặc dùng mirror được duyệt.
6. Theo dõi feed freshness, rate limits, scanner failure và report timestamp.
7. Bật `failOnError=true`, đặt `failBuildOnCVSS` hoặc policy gate có chủ đích.
8. Nối scan vào `check` nếu muốn `build` là security gate; xác minh `--dry-run` chỉ để kiểm tra wiring.
9. Kiểm tra có report mới với danh sách components thực tế, không chấp nhận empty result ngầm.
10. Upload HTML/JSON/SARIF vào nơi có quyền phù hợp.
11. Triage theo advisory, affected ranges, selected versions, reachability, exposure, EPSS/KEV.
12. Cập nhật BOM/platform/constraints hoặc parent dependency thay vì chỉ ẩn CVE.
13. Sau remediation, chạy tests, dependencyInsight, scan lại và tạo SBOM mới.
14. Quản lý suppressions như security exceptions có owner, expiry, approval và justification.
15. Bảo vệ scanner/plugins/CI credentials khỏi untrusted code.
16. Re-scan released inventory sau mỗi feed refresh hoặc lịch định kỳ.
17. Với multi-project, xác định rõ per-project vs aggregate scope.
18. Với container images, bổ sung OS/JDK/image scanning.
19. Giữ bằng chứng scan và thay đổi dependency/lockfile trong code review.
20. Không gộp Checkstyle, test pass, checksum verification và CVE scan thành một kết luận “an toàn tuyệt đối”.

**Tóm tắt quy trình:**

~~~text
Gradle resolves selected dependency graph
                    |
                    v
             SCA / SBOM scan
                    |
          +---------+---------+
          |                   |
          v                   v
       Findings           Scan error
          |                   |
          v                   v
   Confirm/triage       Fail or retry by policy
          |
          v
Upgrade / Replace / Mitigate / Approved exception
          |
          v
Test + dependencyInsight + re-scan
          |
          v
Release with recorded SBOM and ongoing monitoring
~~~

## 26. Tài liệu chính thức và nguồn tham khảo

1. Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
2. Gradle — Dependency Constraints: https://docs.gradle.org/current/userguide/dependency_constraints.html
3. Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
4. Gradle — Verifying Dependencies: https://docs.gradle.org/current/userguide/dependency_verification.html
5. Gradle Plugin Portal — OWASP Dependency-Check: https://plugins.gradle.org/plugin/org.owasp.dependencycheck
6. OWASP Dependency-Check Gradle Plugin — Usage: https://dependency-check.github.io/DependencyCheck/dependency-check-gradle/
7. OWASP Dependency-Check Gradle Plugin — Configuration: https://dependency-check.github.io/DependencyCheck/dependency-check-gradle/configuration.html
8. OWASP Dependency-Check — Project Overview: https://owasp.org/projects/Dependency-Check/
9. OWASP Dependency-Check Gradle — Source/compatibility: https://github.com/dependency-check/dependency-check-gradle
10. NVD API documentation và API key request: https://nvd.nist.gov/developers/vulnerabilities
11. OSV-Scanner v2 — Documentation: https://google.github.io/osv-scanner/
12. OSV-Scanner — Supported Artifacts and Manifests: https://google.github.io/osv-scanner/supported-languages-and-lockfiles/
13. OSV-Scanner — Source Scanning: https://google.github.io/osv-scanner/scan-source/
14. CycloneDX Gradle plugin — Source and tasks: https://github.com/CycloneDX/cyclonedx-gradle-plugin
15. Gradle Plugin Portal — CycloneDX: https://plugins.gradle.org/plugin/org.cyclonedx.bom
16. OWASP Dependency-Track — Project: https://dependencytrack.org/
17. CISA Known Exploited Vulnerabilities Catalog: https://www.cisa.gov/known-exploited-vulnerabilities-catalog
18. FIRST CVSS: https://www.first.org/cvss/
19. FIRST EPSS: https://www.first.org/epss/
20. Open Source Vulnerabilities schema/API: https://osv.dev/

**Lưu ý về thời gian và phiên bản:** Plugin Portal và vulnerability feeds thay đổi liên tục. Những phiên bản được nêu nhằm tạo bài lab nhất quán với tài liệu tại ngày 09/11/2026, không phải chỉ định phải dùng bản đó trong mọi dự án. Khi chạy trên repository thật, xác minh plugin support matrix, Gradle Wrapper version, JDK, report paths và API/CLI options đúng phiên bản đã pin; tuyệt đối không tự tạo số CVE hay kết luận “clean scan” từ các ví dụ tĩnh trong bài.