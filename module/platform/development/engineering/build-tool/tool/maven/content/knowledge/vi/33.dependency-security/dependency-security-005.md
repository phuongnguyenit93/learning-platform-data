# Kiểm soát lỗ hổng thư viện và chính sách nâng cấp trong Maven

## 1. Bài toán: dùng dependency có nghĩa là nhận cả rủi ro của nó

Một ứng dụng Java hiếm khi chỉ chứa mã do nhóm tự viết. Maven giải quyết dependency theo tọa độ artifact và POM, bao gồm cả những thư viện được kéo **bắc cầu** từ các thư viện trực tiếp. Ví dụ:

~~~text
my-service
├── org.apache.commons:commons-lang3:3.17.0       [direct compile]
├── org.example:integration-adapter:2.0.0          [direct runtime]
│   ├── org.example:network-client:4.0.0           [transitive runtime]
│   └── org.example:serialization-core:1.5.0      [transitive runtime]
└── org.junit.jupiter:junit-jupiter:5.11.4         [direct test]
~~~

Đây là **sơ đồ ví dụ về cấu trúc dependency**, không phải dependency tree thực của `commons-lang3` hoặc một báo cáo đã quét. Một CVE được công bố ở `network-client` có thể ảnh hưởng ứng dụng dù `pom.xml` của ứng dụng không hề viết trực tiếp artifact đó.

“Không có dependency trực tiếp chứa CVE” **không đồng nghĩa an toàn**; ngược lại, “scan báo một CVE” **chưa đủ chứng minh** đoạn mã dễ tổn thương được dùng và có thể bị khai thác. Phải xem resolved graph, version thực, phạm vi triển khai, affected versions và điều kiện exploit.

**Mục tiêu của bài:** biết cách phát hiện và kiểm soát rủi ro từ Maven libraries; thiết lập cảnh báo/quality gate trong CI; ưu tiên, nâng cấp và kiểm thử; tránh che dấu CVE bằng suppression không kiểm soát; theo dõi chính sách nâng cấp định kỳ và khẩn cấp.

Bài dùng Maven 3.9.x, JDK 17+ và ví dụ Java 17. Các plugin security scanning cần dữ liệu online/NVD cache và có thể fail vì hạ tầng, không phải vì project Java sai. Những điểm cần phân biệt sẽ được ghi rõ.

## 2. Phân biệt bốn lớp rủi ro

| Lớp | Ví dụ | Cách kiểm |
| --- | --- | --- |
| **Project dependencies** | Libraries dùng compile/runtime/test. | Maven dependency tree, SCA, SBOM, published POM. |
| **Build plugins/extensions** | Compiler, Surefire, Codegen, Enforcer, Site, Maven plugins và chính dependencies của plugin. | Pin plugin versions, scanner hỗ trợ plugin classpath, update advisories, CI review. |
| **JDK/base image/OS/native code** | JDK runtime, container OpenSSL, Linux packages, JNI shared libraries. | Image/host scanner, JDK vendor advisories, SBOM ngoài Maven. |
| **Build/distribution supply chain** | Repository bị thay đổi, dependency confusion, chữ ký bị giả, artifact bị republish. | Repo allowlist, checksums/signatures/provenance, immutable release, credentials. |

Maven Dependency-Check phân tích những gì nằm trong phạm vi plugin/parameters: **không tự biến nó thành scanner hoàn chỉnh cho kernel, OS packages, runtime image, hạ tầng hoặc mọi dịch vụ bên ngoài**.

Trong một Java service chạy Docker, kiểm Maven libraries nhưng bỏ qua JDK và OS image vẫn để sót các lỗ hổng độc lập. Chính sách phụ thuộc tốt cần một inventory thống nhất giữa application dependencies và base runtime.

## 3. Khái niệm CVE, CVSS, CPE, PURL, CWE, KEV và EPSS

- **CVE (Common Vulnerabilities and Exposures):** định danh một lỗ hổng đã được công bố, ví dụ `CVE-YYYY-NNNN` là *dạng định danh*, không phải một CVE cụ thể trong bài.
- **CVSS (Common Vulnerability Scoring System):** cách định lượng mức độ nghiêm trọng theo đặc điểm kỹ thuật; không tự chỉ ra exploit có xảy ra trong ứng dụng của bạn.
- **CPE (Common Platform Enumeration):** định danh sản phẩm/nhà cung cấp được một số bộ dữ liệu và scanner sử dụng. Mapping Maven GAV → CPE có thể không chính xác, dẫn đến false positive/false negative.
- **PURL (Package URL):** định danh package theo ecosystem, ví dụ `pkg:maven/org.apache.commons/commons-lang3@3.17.0`. PURL có thể giúp match advisory theo tọa độ Maven chính xác hơn.
- **CWE:** nhóm điểm yếu phần mềm; giúp hiểu kiểu bug/cách khắc phục, không phải artifact version.
- **CISA KEV:** danh mục lỗ hổng được cơ quan CISA ghi nhận đã bị khai thác trong thực tế; là một tín hiệu ưu tiên mạnh khi hệ thống liên quan.
- **EPSS:** ước lượng xác suất khai thác theo mô hình thống kê; bổ sung cho CVSS, không thay test/triage.

**Câu hỏi triage quan trọng:** GAV/version này **thật sự bị ảnh hưởng** theo advisory của maintainer hay không? Mã dễ tổn thương nằm trong đường chạy nào? Có người dùng không đáng tin điều khiển input không? Có mitigations sẵn? Có fix release? Service có public exposure không? Có KEV/active exploitation không?

Không nên dùng “CVSS cao” làm kết luận cuối, nhưng có thể dùng ngưỡng CVSS làm **cổng cảnh báo tự động ban đầu**, sau đó xét ngữ cảnh.

## 4. Phân biệt resolved version và version ghi trong POM

Maven không đơn giản lấy mọi thẻ `<version>` rồi đặt tất cả artifact versions lên classpath. Nó:

1. Đọc dependencies trực tiếp.
2. Đọc POMs của dependencies để mở rộng graph bắc cầu.
3. Áp dụng scope/optional/exclusions, BOM/dependencyManagement.
4. Resolve xung đột version theo mediation và management.
5. Lấy những artifacts phù hợp vào compile/runtime/test classpaths.

Vì vậy security inventory phải dựa trên **resolved dependency graph**, không chỉ grep `<dependencies>` trong source POM.

Một ví dụ xung đột:

~~~text
service
├── library-A:1.0.0
│   └── parser-core:1.2.0
└── library-B:1.0.0
    └── parser-core:2.0.0
~~~

Maven 3 có quy tắc **nearest definition** và tie-breaking theo thứ tự khai báo khi không có quản lý version chi phối. Scanner/đội bảo mật phải biết parser-core **version nào thực sự được resolve**. Việc POM của library-A nhắc đến `1.2.0` không tự đảm bảo service cuối cùng đang chạy bản đó.

Dùng `mvn dependency:tree`, dependencyManagement/effective POM và SBOM dựa trên Maven resolution. Khi dùng Shade hoặc fat JAR, phải kiểm cả **binary thực tế** vì dependency metadata có thể không phản ánh đầy đủ classes đã được nhúng/relocate.

## 5. Scope quyết định ngữ cảnh, không quyết định lỗ hổng có quan trọng hay không

| Maven scope | Vai trò thông thường | Cách đánh giá |
| --- | --- | --- |
| `compile` | Compile và thường có trong runtime; transitive theo rules. | Kiểm production exploitability, API usage. |
| `runtime` | Cần khi chạy, không nhất thiết tại compile. | Ưu tiên cao nếu service runtime exposed. |
| `provided` | Cần compile/test, runtime do container/platform cung cấp. | Kiểm version thực trong container/app server, không bỏ qua. |
| `test` | Test tooling và test runtime của module. | Không bỏ qua hoàn toàn: có thể ảnh hưởng CI, secrets, test infrastructure. |
| `system` | Library path cố định theo máy, khó di động. | Tránh dùng cho production; inventory riêng. |
| `import` | Chỉ cho BOM `type=pom` trong dependencyManagement. | Kiểm BOM versions/availability và graph effective. |

Ví dụ CI có dependency test bị lỗ hổng thực thi code khi phân tích dữ liệu không tin cậy thì vẫn có rủi ro đối với **CI secrets**, dù artifact đó không được đưa vào production runtime. Vì vậy policy có thể chia mức ưu tiên/quality gate theo scope và threat model, **không chỉ “skip test = an toàn”**.

OWASP Dependency-Check có các tham số như `skipTestScope` và `scanPlugins`; theo tài liệu plugin 13.x, `skipTestScope` mặc định true và `scanPlugins` mặc định false. Muốn kiểm phần này phải cấu hình có chủ đích hoặc dùng công cụ bổ sung.

## 6. Phân biệt dependency risk, security advisory và exploit thực tế

Một báo cáo SCA thường cung cấp:

~~~text
Component/GAV: org.example:parser-core:1.2.0
Advisory/CVE:  [một định danh đã được nguồn tin cậy xác nhận]
Severity:      theo advisory/CVSS
Affected:      khoảng versions
Fixed:         version có bản vá theo vendor, nếu có
Evidence:      cách scanner match component
Paths:         service -> library-A -> parser-core
~~~

Khối trên là **mẫu cấu trúc báo cáo**, không phải finding thật hay dữ liệu CVE đã kiểm chứng.

Các trường có thể khác giữa NVD, GitHub Security Advisories, OSV, Sonatype, maintainer advisories. Một package name giống sản phẩm khác có thể bị CPE match nhầm. Nếu scanner cho thấy tên package/namespace/version không khớp advisory, **chưa nên tự động chốt affected**.

Ngược lại, không có CVE công bố **không chứng minh** dependency hoàn toàn không có lỗ hổng: zero-day, chưa được công bố, hoặc scanner chưa đủ dữ liệu đều có thể xảy ra. Duy trì updates và defense-in-depth bên cạnh SCA.

## 7. Quy trình kiểm soát dependency security theo vòng đời

Một quy trình đủ dùng cho nhóm ứng dụng:

~~~text
Inventory chính xác (tree/SBOM/lock policy)
                 |
                 v
Nguồn advisories cập nhật + scan tự động
                 |
                 v
Triage affected component, exploitability, exposure
                 |
            +----+----+
            |         |
       True positive  False positive
            |         |
         Remediate   Suppress có bằng chứng,
         hoặc giảm   owner, ticket, hạn và review
         thiểu
            |
            v
Nâng version / đổi thư viện / patch / config mitigation
            |
            v
Test compile + unit + integration + regression + performance
            |
            v
Re-scan, verify dependency tree và sản phẩm release
            |
            v
CI gate, phê duyệt, deploy, monitor advisories tiếp theo
~~~

Mọi finding cần **owner, mức ưu tiên, hạn xử lý hoặc ngoại lệ được duyệt**, trạng thái và bằng chứng. Không biến scan thành “một báo cáo HTML không ai xem”.

Một baseline tốt gồm: scan mỗi pull request chạm POM/BOM/lock, scan build định kỳ vì CVE mới có thể xuất hiện dù code không đổi, và theo dõi khẩn cấp advisory có exploit thực tế.

## 8. Công cụ trong hệ sinh thái Maven và vai trò

| Công cụ | Cung cấp gì? | Giới hạn |
| --- | --- | --- |
| Maven Dependency Plugin `dependency:tree` | Resolved direct/transitive graph, scopes/versions. | Không phải scanner CVE. |
| OWASP Dependency-Check Maven Plugin | Match dependencies với advisory data và sinh HTML/JSON/SARIF/... reports, có CVSS gate. | Có thể false positive/negative; cần dữ liệu online/cached mới. |
| MojoHaus Versions Maven Plugin | Thấy versions mới của dependencies, plugins, properties và hỗ trợ thay POM. | Không tự kết luận version mới là an toàn hoặc tương thích. |
| Maven Enforcer Plugin | Rule-based policy: bannedDependencies, requireUpperBoundDeps, convergence, no snapshot... | Không phải database CVE; chính sách phải được cấu hình. |
| CycloneDX Maven Plugin | Xuất SBOM gồm các components/dependencies để lưu/scan ở công cụ khác. | SBOM không tự chặn CVEs nếu không kết hợp scanner/policy. |
| Repository manager (Artifactory/Nexus/... nếu tổ chức dùng) | Access control, caching, policy/metadata/quarantine. | Phụ thuộc license/config; không thay đánh giá rủi ro ứng dụng. |
| OS/container scanner | Nhận diện JDK, native libs, base image packages. | Không thay Maven resolved graph. |

Bài ví dụ bên dưới dùng **Maven Dependency/Versions/Enforcer/CycloneDX/OWASP Dependency-Check** nhưng phân biệt bước build bình thường và bước security scan cần NVD data. Không ép tất cả ứng dụng chịu chi phí tải CVE feed ngay ở mọi local `mvn test`.

## 9. Ví dụ runnable Java 17: project được bảo vệ bằng Maven policies

Tạo cây dự án:

~~~text
secure-greeting-demo/
├── pom.xml
└── src/
    ├── main/java/org/example/security/
    │   ├── GreetingService.java
    │   └── Main.java
    └── test/java/org/example/security/
        └── GreetingServiceTest.java
~~~

Ví dụ dùng **một dependency thư viện thực**:

~~~text
org.apache.commons:commons-lang3:3.17.0
~~~

Version `3.17.0` chỉ là **mốc cấu hình để hướng dẫn lệnh**, không có lời khẳng định nó là bản mới nhất hay miễn nhiễm CVE vào bất cứ ngày nào. Nhóm phải đối chiếu advisory/version mới tại thời điểm build, thay đổi mốc nếu policy yêu cầu.

`GreetingService` dùng `StringUtils` của commons-lang3 nên dependency không thừa. JUnit Jupiter `5.11.4` chỉ dùng cho test. Plugin versions được pin; thư viện không bị tự nâng ngầm khi chỉ chạy Maven.

Maven profile `security-audit` tích hợp CycloneDX và OWASP Dependency-Check; khi không bật profile, `mvn clean verify` vẫn biên dịch và chạy JUnit một cách bình thường.

## 10. pom.xml hoàn chỉnh: dependency, Enforcer và profile quét

Tệp `secure-greeting-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example.security</groupId>
    <artifactId>secure-greeting-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <name>Secure Greeting Demo</name>
    <description>Maven dependency security and upgrade policy demo.</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <commons-lang3.version>3.17.0</commons-lang3.version>
        <junit-jupiter.version>5.11.4</junit-jupiter.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>${commons-lang3.version}</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit-jupiter.version}</version>
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
                <version>3.6.3</version>
                <executions>
                    <execution>
                        <id>validate-toolchain</id>
                        <phase>validate</phase>
                        <goals><goal>enforce</goal></goals>
                        <configuration>
                            <rules>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
                                </requireMavenVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>security-audit</id>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.cyclonedx</groupId>
                        <artifactId>cyclonedx-maven-plugin</artifactId>
                        <version>2.9.3</version>
                        <executions>
                            <execution>
                                <id>create-sbom</id>
                                <phase>package</phase>
                                <goals><goal>makeBom</goal></goals>
                            </execution>
                        </executions>
                    </plugin>
                    <plugin>
                        <groupId>org.owasp</groupId>
                        <artifactId>dependency-check-maven</artifactId>
                        <version>13.0.0</version>
                        <configuration>
                            <failBuildOnCVSS>7.0</failBuildOnCVSS>
                            <failOnError>true</failOnError>
                            <formats>
                                <format>HTML</format>
                                <format>JSON</format>
                            </formats>
                        </configuration>
                        <executions>
                            <execution>
                                <id>scan-known-vulnerabilities</id>
                                <phase>verify</phase>
                                <goals><goal>check</goal></goals>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        </profile>
    </profiles>
</project>
~~~

POM trên là **file hoàn chỉnh** cho demo, không có dấu ba chấm bỏ lửng và không cần parent/BOM bên ngoài. Những dữ kiện thiết yếu:

- `commons-lang3.version`/`junit-jupiter.version` là properties cho Maven dependency versions.
- JUnit nằm ở `scope=test`, không phải dependency runtime của application.
- Enforcer kiểm Java 17+ và Maven 3.9.x; **không tự làm quét CVE**. Maven 4 chưa nằm trong version range của demo.
- `security-audit` là profile **không active by default**. Khi kích hoạt, CycloneDX goal `makeBom` chạy ở `package`, Dependency-Check goal `check` chạy ở `verify`.
- `failBuildOnCVSS=7.0` là **ngưỡng ví dụ của tổ chức giả định**, không phải chuẩn Maven bắt buộc. Findings có score từ ngưỡng này trở lên có thể làm build fail khi được tool đánh giá, còn kết quả phụ thuộc data/matching/suppressions.
- `failOnError=true` làm scanner failure (ví dụ lỗi cập nhật dữ liệu) thành failure; phân biệt với finding vulnerability.
- Không hard-code NVD API key trong POM. `Dependency-Check 13.0.0` cần truy cập data sources hoặc cache hợp lệ; bản scan đầu có thể lâu/rate-limited nếu chưa cấu hình NVD credentials/cache.
- Không có plugin tự ý sửa POM trong profile: build và audit là các bước **quan sát/chặn**, upgrades được xử lý theo pull request riêng.

**Giới hạn diễn giải:** POM này không cam kết commons-lang3:3.17.0 an toàn. Muốn biết tình trạng bảo mật thực tế phải chạy scanner và kiểm advisories ở thời điểm sử dụng. Build scan có thể thất bại vì CVEs đúng, false positives, rate limits hoặc server outage; phải phân biệt qua report/log.

## 11. Java source: dùng dependency thật

Tệp `src/main/java/org/example/security/GreetingService.java`:

~~~java
package org.example.security;

import java.util.Locale;
import org.apache.commons.lang3.StringUtils;

public final class GreetingService {
    private GreetingService() {
    }

    public static String greet(String rawName) {
        String name = StringUtils.isBlank(rawName)
                ? "guest"
                : rawName.strip();
        return "Hello, " + StringUtils.upperCase(name, Locale.ROOT) + "!";
    }
}
~~~

`StringUtils.isBlank(null)` trả true nên demo có thể xử lý null; `StringUtils.upperCase(String, Locale)` chuyển chữ hoa dùng locale ổn định. Với chuỗi `" Maven "`, output phải là `"Hello, MAVEN!"`; với `"   "` hoặc null, output là `"Hello, GUEST!"`.

Tệp `src/main/java/org/example/security/Main.java`:

~~~java
package org.example.security;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? " Maven " : args[0];
        System.out.println(GreetingService.greet(name));
    }
}
~~~

Class `Main` không tự chứa commons-lang3; nó gọi GreetingService đã được compile với commons-lang3. Khi chạy Java thủ công phải đưa commons-lang3 JAR lên runtime classpath; Maven dependency resolution không tự thêm JAR vào một lệnh `java -cp` do người dùng tự viết.

## 12. Test Java 17 và stdout chính xác

Tệp `src/test/java/org/example/security/GreetingServiceTest.java`:

~~~java
package org.example.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingServiceTest {
    @Test
    void formatsProvidedName() {
        assertEquals("Hello, MAVEN!", GreetingService.greet(" Maven "));
    }

    @Test
    void usesDefaultForBlankInput() {
        assertEquals("Hello, GUEST!", GreetingService.greet("   "));
        assertEquals("Hello, GUEST!", GreetingService.greet(null));
    }
}
~~~

Maven Surefire 3.5.2 có thể chạy JUnit Jupiter test theo POM. Bài có hai test methods, ba assertions. Những JUnit dependency artifacts được Maven resolve trong **test scope**, không phải trong runtime classpath để chạy `Main`.

Tại thư mục `secure-greeting-demo/`:

~~~bash
mvn --version
java --version
mvn -B -ntp clean verify
~~~

Sau khi build pass, tải direct/runtime dependencies vào `target/dependency`:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:copy-dependencies -DincludeScope=runtime
~~~

Linux/macOS:

~~~bash
java -cp "target/classes:target/dependency/*" org.example.security.Main
~~~

Windows PowerShell/CMD:

~~~powershell
java -cp "target\classes;target\dependency\*" org.example.security.Main
~~~

**Stdout chính xác của riêng chương trình Java khi không truyền đối số:**

~~~text
Hello, MAVEN!
~~~

Đây là stdout **của lệnh Java**, không phải toàn bộ log Maven. `target/dependency/*` dùng wildcard của Java launcher để thêm JARs trong thư mục; trên Windows separator classpath là `;`. Demo không cấu hình main JAR manifest/uber-JAR nên không dùng `java -jar target/secure-greeting-demo-...jar` mà thiếu dependencies.

## 13. Kiểm baseline graph bằng Maven Dependency Plugin

Từ root project, lệnh:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Kiểm các artifacts:

~~~text
org.example.security:secure-greeting-demo:jar:1.0.0-SNAPSHOT
+- org.apache.commons:commons-lang3:jar:3.17.0:compile
\- org.junit.jupiter:junit-jupiter:jar:5.11.4:test
   \- ... các test-only dependencies theo POM của JUnit ...
~~~

Đây là **cấu trúc rút gọn**, không phải toàn bộ log hay lời khẳng định số lượng transitive artifacts đúng bằng một số cố định. JUnit có thể kéo thêm JUnit Platform/engine/API artifacts theo published POM của phiên bản đó.

Lệnh lọc:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dincludes=org.apache.commons:commons-lang3
~~~

Xem effective model khi POM có parent/BOM/profiles:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom
~~~

Cần giải thích findings theo **resolved version**. Một CPE match tới thư viện cùng tên nhưng tọa độ khác không tự được coi là lỗ hổng của commons-lang3. Nếu scan cho CVE nào đó, đối chiếu GAV + advisory affected range thay vì đoán từ `pom.xml`.

## 14. Quét bằng OWASP Dependency-Check Maven Plugin

Khi cần security audit, chạy:

~~~bash
mvn -B -ntp -Psecurity-audit clean verify
~~~

Trong profile `security-audit`:

- Goal `cyclonedx:makeBom` sinh SBOM ở phase `package`.
- Goal `dependency-check:check` quét dependencies ở phase `verify`, sử dụng CVE/advisory data hiện có, và sinh báo cáo trong build output.
- `failBuildOnCVSS=7.0` khiến phát hiện vượt quality gate có thể làm Maven báo build failure. Đây là một **policy gate ví dụ**, không phải kết quả scan cố định.

Các output quan trọng thường là:

~~~text
target/bom.xml
target/bom.json
target/dependency-check-report.html
target/dependency-check-report.json
~~~

Tên file/phương thức tạo phụ thuộc các plugin versions/configs đã khai báo và không nên được thay bằng file báo cáo giả khi scanner fail. Nếu scan bị chặn trước khi sinh report do thiếu NVD data, output có thể thiếu.

**Không khẳng định output scan là “0 CVE”** khi chưa chạy và khi CVE data thay đổi thường xuyên. Không gắn kết quả CVSS của một dependency cụ thể vào bài học như thể đã có bằng chứng live. CI phải lưu report và đọc logs/exit status thực tế.

## 15. NVD API data và chính sách cache

OWASP Dependency-Check cần cập nhật dữ liệu lỗ hổng từ nguồn ngoài như NVD/NIST (cùng các data sources khác tùy analyzer). Khi scan lần đầu, việc download/index dữ liệu có thể tốn thời gian và bị rate limit. Nếu cache lâu không cập nhật, nó có thể **bỏ sót advisory mới**.

Các lựa chọn vận hành:

1. Xin **NVD API key** cho tổ chức theo hướng dẫn chính thức; lưu bằng secret manager/Maven settings server, không commit vào Git.
2. Cấu hình `nvdApiServerId` trỏ `<server><id>...` trong `settings.xml` khi phù hợp; plugin lấy API key theo cơ chế cấu hình.
3. Tái sử dụng cache/database của Dependency-Check trong CI runners theo plugin version, schema và retention policy.
4. Theo dõi thời điểm dữ liệu cập nhật lần cuối; đặt alert nếu quá cũ.
5. Tách lỗi **scanner/feeds unavailable** khỏi lỗi **lỗ hổng được xác nhận**. Với `failOnError=true`, cả hai có thể khiến build fail, nhưng cần runbook khác nhau.
6. Có thể dùng update job định kỳ, service/mirror được quản lý; **không** tắt `autoUpdate` vô thời hạn chỉ để CI xanh.

Ví dụ một phần plugin config tham khảo:

~~~xml
<configuration>
    <nvdApiServerId>nvd-readonly</nvdApiServerId>
    <failOnError>true</failOnError>
</configuration>
~~~

Đây **không phải POM hoàn chỉnh** và không được chèn vào demo trừ khi bạn đã cấu hình server `nvd-readonly` trong settings/CI. NVD API key là dữ liệu nhạy cảm, không để ở `<nvdApiKey>plain-text-secret</nvdApiKey>` trong source.

Khi gặp HTTP 403/429, hãy kiểm NVD API key, quota, proxy, network và CI concurrency trước khi sửa bất kỳ dependency version nào.

## 16. Đọc báo cáo scanner theo mức bằng chứng

Một finding hữu ích cần có tối thiểu:

| Trường | Tại sao cần |
| --- | --- |
| GAV/PURL/CPE evidence | Xác định component/version scanner đã nhận diện. |
| Advisory/CVE ID và nguồn | Truy tới mô tả gốc, affected/fixed ranges. |
| CVSS base severity | Gợi ý mức khẩn, không kết luận exploitability. |
| Dependency path | Ai kéo component vào? Direct hay transitive? |
| Scope/runtime reachability | Có được đóng gói vào app/container không? |
| Code path/attack preconditions | Input không tin cậy có thể đến phương thức lỗi không? |
| Fixed version/mitigation | Nâng thẳng được không, có patch/backport/config workaround? |
| Data freshness | Advisory feed cập nhật lúc nào? Scanner version/schema phù hợp? |
| False positive evidence | Product mapping có thực đúng không? |
| Owner, due date, exception | Đảm bảo follow-up kiểm soát được. |

Một báo cáo HTML giúp review, còn JSON/SARIF/JUnit-style reports phục vụ CI aggregation khi plugin và tools hỗ trợ. Không chỉ dựa vào dòng log có “CVE”; cần tìm bản ghi **artifact và affected version chính xác**.

Nếu scanner match sai CPE, hãy ưu tiên xác minh PURL/GAV và upstream advisory, sau đó dùng suppression có giới hạn. Nếu scanner bỏ sót do phụ thuộc shaded/vendored, cần scanner binary/SBOM bổ sung.

## 17. CVSS threshold là policy đầu vào, không phải business risk cuối cùng

Một ngưỡng demo:

~~~xml
<failBuildOnCVSS>7.0</failBuildOnCVSS>
~~~

Nghĩa là khi scanner nhận thấy CVSS từ ngưỡng 7.0 trở lên, quality gate có thể fail. Nhưng **không nên tự động biến mọi phát hiện CVSS 6.9 thành không cần xử lý**.

Tình huống A: Một thư viện lỗi remote code execution có CVSS cao nhưng được dùng đúng ở endpoint public nhận input không đáng tin → ưu tiên cao. Tình huống B: Một finding có severity cao nhưng scanner match nhầm CPE sang phần mềm khác → cần chứng minh false positive. Tình huống C: Một lỗ hổng severity trung bình đang bị khai thác rộng rãi trong stack thực dùng → vẫn có thể cần xử lý khẩn.

Một policy có thể kết hợp:

- **Exploit thực tế** (CISA KEV, vendor incident, exploited in the wild).
- **Exposure** (public/internal, auth, attack surface, data classification).
- **Reachability** (affected method có được dùng không, runtime conditions).
- **CVSS/EPSS** và advisory confidence.
- **Patch availability** và upgrade/test effort.
- **Criticality** của service và business impact.

Ngưỡng CI vẫn hữu ích để phản ứng nhanh, nhưng cần kênh triage và approval khi có ngoại lệ hợp lý.

## 18. Quy trình triage CVE có thể kiểm toán

Ví dụ một record giả định:

~~~text
Finding ID: SEC-204
Component: org.example:parser-core:1.2.0
Source: vendor advisory + vulnerability scanner
Dependency path: checkout-service -> data-adapter -> parser-core
Environment: production API
Evidence: affected version confirmed; vulnerable parser input reachable
Priority: P1 (internal policy example)
Action: upgrade adapter/parser-core to validated patched combination
Owner: Checkout team
Due: theo SLO P1 của tổ chức
Validation: integration tests + rescan + SBOM diff
Exception: none
~~~

Đây **không phải CVE có thật**; là ví dụ record triage và quy trình ra quyết định. Mỗi bước:

1. **Confirm:** kiểm GAV/filename/checksum, scanner match và advisory affected range.
2. **Scope:** biết service deploy nào đang dùng version đó, qua nhánh nào, môi trường nào.
3. **Impact:** có data path dễ tấn công/privilege không?
4. **Mitigation:** patch, upgrade, disable feature, restrict input, WAF/ACL, sandbox hoặc tạm gỡ chức năng; ghi residual risk.
5. **Test:** compile/tests, regression/performance/security test và smoke test deployment.
6. **Close:** rescan, kiểm final GAV/SBOM, ghi SHA và release version có patch.
7. **Review:** nếu chấp nhận rủi ro tạm, phải có người duyệt, hết hạn và theo dõi lại.

Không để record ở trạng thái “ignored” không owner, không ngày hết hạn, không có nguồn bằng chứng.

## 19. False positives: suppression phải chính xác và có hạn

Dependency-Check có thể match CPE sai vì nhiều package sử dụng tên sản phẩm giống nhau. Khi có bằng chứng rõ scanner đang gắn advisory của **sản phẩm khác**, có thể tạo suppression XML.

Theo hướng dẫn chính thức, có thể chọn phần tử `gav`/`packageUrl` hoặc hash/filename cùng `cpe`/`cve` để ràng buộc finding; có attribute `until` để tự hết hạn. Một **mảnh ví dụ mô phỏng**, không dùng nguyên trong project thật:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<suppressions
    xmlns="https://jeremylong.github.io/DependencyCheck/dependency-suppression.1.4.xsd">
    <suppress until="2027-01-15Z">
        <notes><![CDATA[
        SEC-204: confirmed false-positive product identity;
        reviewer: AppSec; revisit before expiration.
        ]]></notes>
        <gav>org.example:demo-parser:1.0.0</gav>
        <cpe>cpe:/a:unrelated:product</cpe>
    </suppress>
</suppressions>
~~~

Các tọa độ/CPE trong mảnh này **là dữ liệu giả**, không tương ứng finding có thật; nó chỉ trình bày cách scope + owner + expiry. Khi dùng thực tế, lấy syntax và IDs từ chính report của plugin và khớp schema đang chạy.

Plugin config có thể thêm:

~~~xml
<configuration>
    <suppressionFiles>
        <suppressionFile>config/security/dependency-check-suppressions.xml</suppressionFile>
    </suppressionFiles>
    <failBuildOnUnusedSuppressionRule>true</failBuildOnUnusedSuppressionRule>
</configuration>
~~~

Đây cũng là **mảnh cấu hình tùy chọn**, chưa nằm trong POM runnable. Chỉ thêm khi file suppression tương ứng tồn tại. `failBuildOnUnusedSuppressionRule` giúp phát hiện suppressions không còn khớp finding nhưng có thể cần review trên CI.

**Không suppress toàn bộ CVSS cao** để build pass; không dùng pattern wildcard che mọi version của thư viện bị ảnh hưởng; không suppress một CVE đã được xác nhận affected chỉ vì chưa nâng cấp kịp. Với rủi ro thật cần **risk acceptance** và action plan, không khai man false positive.

## 20. Chính sách nâng cấp: chủ động khác khẩn cấp

Cần phân biệt hai kênh:

**Nâng cấp định kỳ:** đưa dependencies/plugins về phiên bản được hỗ trợ, giảm technical debt, phản ứng trước EOL/supply-chain risk. Lịch có thể theo tháng hoặc theo sprint, tùy số lượng dependencies/độ nhạy hệ thống.

**Nâng cấp khẩn cấp:** khi có advisory xác nhận ảnh hưởng, KEV/active exploitation, critical RCE hoặc policy gate bị vi phạm. Không chờ lịch nâng cấp chung nếu risk không chấp nhận được.

Chính sách cần trả lời:

- Ai sở hữu mỗi Maven module và BOM/platform version?
- Mỗi dự án có một bản kiểm kê dependency/SBOM cập nhật đến commit nào?
- Khi advisory mới xuất hiện, ai nhận notification, ai xác minh?
- CVEs nào phải chặn merge/release; việc bypass cần ai duyệt?
- Thời gian mục tiêu xử lý theo mức rủi ro là bao lâu?
- Có được nâng major tự động không? Ai chịu trách nhiệm API compatibility?
- Nếu chưa có fix version, giải pháp giảm thiểu và ngày review là gì?
- Bằng chứng đóng finding gồm những tests/logs/SBOM nào?

**Không có một SLA/SLO bắt buộc do Maven đặt ra.** Các mốc ở mục 22 chỉ là ví dụ nội bộ, phải điều chỉnh theo hệ thống và tổ chức.

## 21. Phân loại upgrades: patch, minor, major và rủi ro

| Loại nâng cấp | Trường hợp minh họa | Cần kiểm |
| --- | --- | --- |
| Patch `x.y.z → x.y.(z+1)` | Bản vá bảo mật/bugfix theo semantic versioning nếu library tuân theo. | Release notes, regression, transitive changes. |
| Minor `x.y → x.(y+1)` | Tính năng hoặc behavior mới theo chính sách maintainer. | API compatibility, config defaults, deprecations. |
| Major `x → x+1` | Có thể breaking API/bytecode/config. | Migration guide, compile/integration/performance tests. |
| Đổi implementation | Library bị EOL hoặc không có fix. | License, semantics, security, migration cost. |
| Pin/override transitive | Vendor fix chưa ra ở upstream wrapper. | Conflict/compatibility, CVE impact, owner của override. |
| Giảm exposure | Tắt chức năng, chặn đầu vào, isolate service. | Bằng chứng mitigation, thời hạn chờ patch. |

**SemVer không phải pháp luật**: nhiều artifacts không tuân thủ chặt, thậm chí patch release có thể thay behavior. Đọc changelog và test hệ thống thực sau bất kỳ version bump nào.

Một version mới nhất cũng không nhất thiết là version tốt nhất: có thể chưa tương thích JDK 17, đã đổi license, chứa regression, hoặc chưa được tổ chức phê duyệt. **Chỉ chọn version sau khi kiểm advisory + compatibility + tests**.

## 22. SLO/SLA xử lý lỗ hổng: một ví dụ, không phải chuẩn Maven

Một tổ chức có thể đưa ra ma trận mẫu:

| Tình huống | Mức ưu tiên ví dụ | Mục tiêu xử lý nội bộ ví dụ |
| --- | --- | --- |
| Lỗ hổng đang bị khai thác, ảnh hưởng service public có đường tấn công thực. | P0 | Mitigation ngay trong ca trực; patch theo incident process. |
| Lỗ hổng nghiêm trọng confirmed, exposed nhưng chưa ghi nhận exploit trực tiếp. | P1 | Fix hoặc mitigation có review trong vài ngày. |
| Rủi ro trung bình với exploit conditions hạn chế, có bản vá. | P2 | Đưa vào sprint/chu kỳ cập nhật sắp tới. |
| Low severity/không reachable, nhưng confirmed affected. | P3 | Theo dõi và xử lý định kỳ; ghi risk acceptance nếu cần. |
| False positive có evidence. | Exception | Suppress narrowly + hết hạn + owner, không gọi là đã patch. |

Không biến mốc thời gian “vài ngày” của ví dụ thành policy áp dụng cho mọi công ty. Với regulated systems hay public critical infrastructure, nghĩa vụ xử lý có thể khác; phải theo legal/security policy thực tế.

Một CVE có score thấp nhưng thuộc CISA KEV hoặc có exploit phù hợp có thể được nâng lên P0/P1. Một finding score cao nhưng scanner nhận sai component cần investigation, không gán team là đã bị compromise.

## 23. Tìm versions mới mà chưa sửa POM

MojoHaus Versions Maven Plugin có các goals **chỉ hiển thị update candidates**:

~~~bash
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:display-dependency-updates
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:display-plugin-updates
mvn -B -ntp org.codehaus.mojo:versions-maven-plugin:2.22.0:display-property-updates
~~~

Với POM demo, property `commons-lang3.version` và `junit-jupiter.version` là nơi quản lý phiên bản tập trung, nên lệnh `display-property-updates` có thể giúp phát hiện candidates nếu metadata repo truy cập được.

**Giới hạn quan trọng:**

- Versions Plugin so sánh phiên bản **theo repository metadata**, không phải advisory scanner.
- Version mới xuất hiện không chứng minh đó là bản fix security cụ thể.
- Nếu repo đang offline/cache lỗi, kết quả update list có thể thiếu.
- Một version candidate mới hơn có thể là pre-release hoặc không tương thích JDK/toolchain.
- Các goals `display-*` ở trên không sửa source POM. Goals `update-*` hoặc `set` có thể **chỉnh POM**, phải dùng qua PR và review.

Đưa thông tin “version mới” vào triage record rồi tra advisory/release notes của library. Không tự động áp dụng mọi bản mới nhất trên production branch.

## 24. Nâng commons-lang3 trong ví dụ theo quy trình an toàn

Giả sử scan/advisory đã xác nhận version `3.17.0` cần nâng và một phiên bản thay thế được team kiểm chứng (gọi tạm là `VERSION_DA_DUYET`). **Không khẳng định số version cụ thể là patched** khi chưa có advisory xác nhận.

Một PR nâng cấp có trình tự:

1. Xác định **fixed version tối thiểu** từ advisory upstream/security notice.
2. Xác nhận fixed version tồn tại trong repository được phép, tương thích Maven/JDK 17.
3. Cập nhật property `commons-lang3.version` trong POM sang **một version số thực đã được duyệt**.
4. Xem `git diff` để bảo đảm chỉ thay tọa độ dự kiến.
5. Chạy compile, unit/integration tests và quality gate/security scan.
6. Chạy `dependency:tree` để kiểm resolved graph không còn artifact/version cũ.
7. Chạy runtime smoke test và SBOM diff.
8. Review release notes, classpath conflicts, ảnh hưởng API/config và performance.
9. Merge/release theo approvals và theo dõi incidents sau deploy.

Các lệnh có thể chạy sau khi source POM đã được cập nhật:

~~~bash
git diff -- pom.xml
mvn -B -ntp clean verify
mvn -B -ntp -Psecurity-audit verify
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

**Không bắt buộc chạy hai lần `verify` nếu CI đã chạy profile security-audit trong cùng build**; danh sách trên minh họa các bước kiểm riêng nhằm phân biệt lỗi unit tests và lỗi scanner data. Với CI tối ưu có thể gom phù hợp nhưng luôn lưu rõ log/report.

Nếu `security-audit` fail vì dữ liệu NVD unavailable, không tự gọi đó là “version mới vẫn có CVE”. Phân loại lỗi hạ tầng trước, giữ release gate chưa đạt theo policy.

## 25. Nâng dependency bắc cầu qua direct override và dependencyManagement

Giả sử POM effective graph có:

~~~text
service
  -> adapter:1.0.0
      -> parser-core:1.2.0 [affected]
~~~

Một phương án là nâng **adapter** lên release đã kéo `parser-core` fixed version. Đây thường là hướng dễ bảo trì nếu vendor đã test compatibility.

Nếu adapter chưa cập nhật nhưng parser-core phiên bản patched binary-compatible, consumer có thể thử quản lý transitive version:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>parser-core</artifactId>
            <version>2.0.1</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **mảnh minh họa với artifacts giả định**, không thuộc POM runnable và không khẳng định `2.0.1` là bản vá thực tế. Management chỉ điều khiển version nếu dependency đó xuất hiện trong graph, **không tự tạo dependency**.

Nếu project import BOM, version override đặt đúng management layer hoặc cập nhật BOM theo platform policy. Hãy kiểm sự ưu tiên giữa direct dependency, BOM và parent; một change ở parent có thể ảnh hưởng hàng chục modules.

**Rủi ro override:** parser-core được nâng mà adapter không tương thích API/binary, dẫn `NoSuchMethodError`, `ClassNotFoundException` hoặc behavior change tại runtime. Nếu cần override tạm thời, tạo ticket, owner và kế hoạch xóa override khi upstream adapter đã nâng.

## 26. Enforcer rules để ngăn dependency graph xấu quay lại

Maven Enforcer Plugin không biết CVE DB nhưng có thể khóa một số policy structurally:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.6.3</version>
    <executions>
        <execution>
            <id>dependency-policy</id>
            <phase>validate</phase>
            <goals><goal>enforce</goal></goals>
            <configuration>
                <rules>
                    <dependencyConvergence/>
                    <requireUpperBoundDeps/>
                    <banDynamicVersions/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **mảnh cấu hình policy nâng cao**; **không** đặt vào runnable POM gốc để tránh thêm quality gates chưa được lựa chọn. Ý nghĩa:

- `dependencyConvergence` phát hiện nhiều versions cùng GAV trên các nhánh cần hội tụ.
- `requireUpperBoundDeps` kiểm xem resolved version có đáp ứng upper-bound rules trên transitive graph.
- `banDynamicVersions` cấm versions yêu cầu resolution động theo quy tắc plugin.

**Lưu ý:** Enforcer có thể fail trên những dependency graphs hiện hữu có lý do kỹ thuật; phải đánh giá/thiết kế exceptions chứ không bật rule rồi lạm dụng excludes. Và các rules trên **không** chứng minh lỗ hổng CVE đã biến mất: một version hội tụ vẫn có thể bị ảnh hưởng bởi advisory.

Để cấm riêng một artifact/version đã bị xác nhận rủi ro, có thể dùng `bannedDependencies` với `excludes` scoped theo GAV/ranges. Nhưng cần hiểu syntax version range và kiểm cả transitive paths. Một ban rule chỉ cho đúng một CVE/version cần được update khi có advisory mới, không thay SCA định kỳ.

## 27. Giới hạn và ngoại lệ của bannedDependencies

Một mảnh ví dụ:

~~~xml
<bannedDependencies>
    <searchTransitive>true</searchTransitive>
    <excludes>
        <exclude>org.example:insecure-parser:[1.0,2.0)</exclude>
    </excludes>
</bannedDependencies>
~~~

Mảnh này dùng **artifacts giả** và version range minh họa, **không thuộc POM runnable**. Nó thể hiện chính sách cấm một khoảng version được xác minh affected. Maven Enforcer hỗ trợ `searchTransitive`, nên có thể chặn cả dependency được kéo vào qua các modules trung gian.

Một dependency trực tiếp mới có thể bỏ qua tên parser nhưng vẫn kéo `insecure-parser` transitively. Vì vậy `searchTransitive=true` thường phù hợp với banned dependency policy. Nếu tạo exceptions với `includes`, cần document điều kiện/owner và review định kỳ.

**Không được dùng bannedDependencies để thay scanner hoàn toàn**: danh sách chặn thủ công không thể tự biết mọi CVE mới, đặc biệt trong các package chưa từng được nhóm sử dụng trước đó.

## 28. CycloneDX SBOM làm bằng chứng inventory

CycloneDX là format SBOM (Software Bill of Materials). Plugin cho Maven có thể xuất danh sách components và các dependency relationships để lưu cùng release.

Trong profile demo:

~~~xml
<plugin>
    <groupId>org.cyclonedx</groupId>
    <artifactId>cyclonedx-maven-plugin</artifactId>
    <version>2.9.3</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals><goal>makeBom</goal></goals>
        </execution>
    </executions>
</plugin>
~~~

Với project **đơn module**, goal `makeBom` là phù hợp; output mặc định thường là:

~~~text
target/bom.xml
target/bom.json
~~~

SBOM có thể chứa components và versions ở dependency graph, giúp so sánh giữa hai builds. Cấu hình plugin có thể thay output format/name, projectType, classifier hoặc skipAttach; với `makeAggregateBom`, plugin còn hỗ trợ **multi-module reactor**.

**SBOM không tự nói component có CVE** nếu không có vuln data/vulnerability enrichment; đó là inventory. Nên gắn SBOM với release GAV và Git SHA, lưu immutable artifact, rồi dùng scanner/service đánh giá CVEs mới đối với cùng SBOM theo thời gian.

Một SBOM cũ có thể vẫn hữu ích để tra affected deployments khi advisory mới xuất hiện, nhưng nó sẽ sai nếu build thực tế chứa shaded/vendored/native artifacts chưa được inventoried.

## 29. Dùng SBOM để trả lời “các ứng dụng nào bị ảnh hưởng?”

Khi nhận một advisory mới về `parser-core`, không nên chỉ search trên Git source files; version có thể nằm ở transitive graph. Quy trình:

1. Từ advisory, xác định package ecosystem Maven, groupId/artifactId và affected version ranges.
2. Tìm trong SBOMs của **bản build đã deploy**, không chỉ current main branch.
3. Với mỗi service/release, xác định resolved dependency, scope, packaging và link đến producer.
4. Kiểm có runtime exposure: server, batch, CI worker, Android/client hay thư viện dùng lại.
5. Tạo issue/team owner và ưu tiên sửa theo risk.
6. Sau patch, build SBOM mới và so difference.

Một service có thể có source POM version mới nhưng deployment production vẫn chạy binary từ image cũ. Đó là lý do inventory phải gắn **artifact digest/image digest và deployment version**, không chỉ trạng thái Git.

Bộ dữ liệu tối thiểu nên nối được: GAV + Git commit + Maven dependency tree/SBOM + CI build ID + container digest + environment deployment. Không chia sẻ private SBOM ra công khai nếu nó bộc lộ thông tin nội bộ không được phép.

## 30. Build plugins và supply-chain risk của chính công cụ quét

Maven plugins chạy code trên máy developer/CI với quyền của build process. Một plugin bị takeover hoặc dependency plugin chứa vulnerability có thể nguy hiểm dù artifact đó không nằm trong application runtime classpath.

Một số biện pháp:

- Pin versions của Maven Compiler/Surefire/Deploy/Shade/Codegen/Security plugins.
- Giới hạn repository/mirror và write permissions; tránh tải Maven plugins từ nguồn ngẫu nhiên.
- Không truyền credentials trực tiếp trong POM hoặc arguments bị log công khai.
- Review plugin updates qua Versions Plugin và advisories như project libraries.
- Dùng CI runners cách ly, secrets least privilege, và không để PR từ nguồn không đáng tin có publish credentials.
- Kiểm Maven extensions `.mvn/extensions.xml` hoặc core extensions nếu dự án dùng.
- Với Dependency-Check, có config `scanPlugins` để quét plugin artifacts trong phạm vi hỗ trợ, nhưng không mặc định full coverage cho mọi build tool/integration.

Vì vậy một pipeline security “sử dụng scanner mới nhất” cũng phải kiểm chính **scanner/plugin được tải**, data updates và quyền chạy. Không tự cho rằng Maven `dependency:tree` của app liệt kê mọi plugin classpath.

## 31. Multi-module reactor: kiểm toàn bộ graph và tránh scan trùng

Một multi-module project có thể có:

~~~text
platform-parent/
├── pom.xml
├── core/
├── adapter/
├── api/
└── cli/
~~~

Security policy cho reactor cần:

- Kiểm **mọi module**/effective POM nếu chúng phát hành độc lập.
- Kiểm cả transitive dependencies có thể chỉ xuất hiện ở module adapter.
- Chọn aggregation để có một báo cáo tổng thể, đồng thời giữ module ownership/path.
- Phân biệt artifact `pom` parent/BOM với runtime JARs.
- Đảm bảo test scopes/plugin scans không bị bỏ qua ngoài chủ đích.
- Không tạo nhiều job cùng tải NVD data/cache rồi làm rate-limit hoặc database contention.
- Gắn findings với module thực sự dùng affected library.

OWASP Dependency-Check Maven Plugin có goal `aggregate` cho multi-module report; CycloneDX có `makeAggregateBom`. Đây là **goals khác** với `check`/`makeBom` ở project đơn module của ví dụ. Nếu dùng aggregation, hãy kiểm plugin docs/cấu hình Maven reactor và output naming thực tế; không kỳ vọng copy nguyên executions đơn module vào mỗi child luôn tạo report tối ưu.

## 32. CI gates: tách lỗi security finding với lỗi hạ tầng scanner

Một pipeline ví dụ:

~~~text
Checkout + JDK17/Maven3.9.x
    |
    v
mvn -B -ntp clean verify
    |
    v
mvn -B -ntp -Psecurity-audit verify
    |
    +--> SBOM artifacts
    +--> Dependency-Check HTML/JSON
    |
    v
Classify exit:
- Tests fail                        -> code/test failure
- Dependency-Check finding >= gate -> vulnerability gate failure
- NVD/API/update/cache error        -> scanner infrastructure failure
- All pass                          -> eligible for review/release
    |
    v
Review + approve exceptions + promote artifacts
~~~

Không đơn giản viết một job `|| true` sau scanner: cách đó làm mọi CVE và lỗi feed đều biến mất khỏi status. Nếu muốn có chế độ advisory-only cho branch phát triển, cấu hình rõ policy, vẫn publish reports và tạo issues; production release gate có thể nghiêm hơn.

Khi scanner lỗi hạ tầng, nhóm có thể có **quy trình tạm thời** (retry có giới hạn ở tầng CI, dùng cache cập nhật, alternate approved scanner, release exception có thời hạn) nhưng **không** nên gọi là “không có lỗ hổng”. Việc có cho release tiếp hay không phải theo risk policy đã thống nhất.

## 33. Lưu báo cáo đúng cách và tránh tiết lộ dữ liệu nhạy cảm

Một lần scan có thể tạo:

~~~text
target/dependency-check-report.html
target/dependency-check-report.json
target/bom.xml
target/bom.json
~~~

Hãy lưu chúng như CI artifacts theo retention policy, gắn với commit và service/version. Báo cáo có thể chứa dependency names, GAV, paths và attack surface; những thông tin này có thể nhạy cảm trong môi trường doanh nghiệp.

Cần rà soát trước khi public:

- Không để NVD API key/credentials trong logs hoặc artifact.
- Xem scanner có in file path, repository URL nội bộ, env vars hoặc system property không.
- Kiểm suppression XML chứa dữ liệu nội bộ/ticket IDs và có cần redaction không.
- Có access control/retention cho SBOM và vulnerability findings.
- Có workflow để người sở hữu module tìm lại report khi CVE mới xuất hiện.

Đối với source code công khai, SBOM có thể được chia sẻ theo chính sách minh bạch; với service nội bộ, nên quản lý quyền truy cập theo organizational security requirements.

## 34. Case study 1: direct dependency có advisory, cách nâng

Tình huống giả định:

~~~text
Before:
service -> library-X:1.0.0 [affected version]
After:
service -> library-X:1.0.2 [validated fixed version]
~~~

Bước làm:

1. Tìm advisory gốc xác nhận `1.0.0` affected và `1.0.2` đã fix (trong ví dụ giả định).
2. Kiểm version `1.0.2` tồn tại trong approved repository và phù hợp JDK/Java API.
3. Cập nhật direct version hoặc version property của library-X.
4. Chạy `dependency:tree`, tests, integration, và scan.
5. Xác nhận SBOM after không chứa version affected.
6. Deploy môi trường thử trước, rồi theo dõi metrics/errors.

Không lấy nguyên `library-X` làm tên artifact thật; đây là **tình huống mô phỏng**, không có CVE hoặc advisory cụ thể nào được khẳng định. Trong thực tế, patch version phải lấy từ vendor advisories.

## 35. Case study 2: transitive dependency bị ảnh hưởng

Tình huống:

~~~text
Before:
service -> adapter-A:3.0.0 -> parser-core:1.2.0 [affected]
Option 1:
service -> adapter-A:3.1.0 -> parser-core:1.2.5 [fixed]
Option 2:
service -> adapter-A:3.0.0 -> parser-core:1.2.5 [temporary override]
~~~

Đây là **versions mô phỏng**.

Ưu tiên nâng adapter-A lên release được vendor duy trì và test cùng patched parser-core. Nếu chưa có adapter update, cân nhắc `dependencyManagement`/direct override với review API compatibility. Không exclude parser-core nếu adapter cần class đó lúc chạy.

Sau đổi, kiểm các đường graph:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Đôi khi parser-core vào graph qua **nhiều nhánh**; một exclusion ở adapter-A không chặn nhánh khác. Muốn cấm version affected một cách rõ, kết hợp Enforcer bannedDependencies và SCA gate theo tổ chức.

## 36. Case study 3: scanner báo false positive hoặc thiếu feed

**False positive:** scanner match Maven artifact `org.example:demo-parser` với CPE của một sản phẩm khác chỉ vì cùng tên. Sau khi đối chiếu PURL/GAV/version và upstream advisory, AppSec xác nhận mismatch. Cách xử lý: suppression narrowly-scoped, owner/ticket/expiry, test scanner tiếp tục nhận diện các CVEs khác.

**Feed unavailable:** CI báo HTTP 429 với NVD API. Đây **không phải CVE**; không sửa version commons-lang3 để chữa lỗi. Kiểm key, cache, số jobs chạy song song, throttle/quota và proxy. Pipeline có thể fail vì `failOnError=true`; báo “security scan unavailable” thay vì “project bị vulnerability”.

**Real positive nhưng chưa có fix:** ghi affected path/exposure, patch alternatives/mitigation, exception process có thời hạn và trách nhiệm. Không suppress như false positive.

Ba tình huống trên có cùng triệu chứng bề ngoài **“CI đỏ”**, nhưng cần ba remediation workflows khác nhau.

## 37. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân hay gặp | Hướng giải quyết |
| --- | --- | --- |
| `dependency:tree` không thấy dependency bị nêu CVE. | Artifact bị omit do scope/exclusion, hoặc scanner nhận diện file nhúng/shaded. | Xem effective graph và binary/package evidence. |
| Scanner báo CVE của sản phẩm không dùng. | CPE mapping false positive. | Kiểm PURL/GAV, upstream advisory, suppression có hạn. |
| Scanner báo 0 vulnerabilities khi offline lâu. | Data cache cũ/scan không cập nhật. | Xem data freshness, không coi 0 là bảo đảm sạch. |
| NVD trả 403/429. | API key/quota/proxy/rate-limit. | Cấu hình key an toàn, cache/update job và concurrency. |
| Scan fail trước khi có report. | Cập nhật data/DB schema hoặc plugin lỗi. | Phân loại infrastructure failure. |
| `failBuildOnCVSS=11` không làm build fail khi có CVEs. | 11 vượt thang 0–10, default không fail theo severity. | Đặt threshold phù hợp policy. |
| Có `failOnError=true` nhưng scanner vẫn báo CVE. | `failOnError` chỉ kiểm lỗi thực thi, không thay threshold CVSS. | Đọc config riêng của hai flags. |
| Dependency tăng version nhưng CVE còn trong report. | Chưa chọn patched version, transitive path khác, cache không đúng, hoặc false positive. | Đọc advisory/graph/report bằng evidence. |
| App compile pass nhưng runtime `NoSuchMethodError`. | Upgrade phá binary compatibility/transitive mediation. | Integration/smoke test, điều chỉnh versions. |
| `versions:display-dependency-updates` có version mới nhưng không có CVE. | Công cụ báo update availability, không phải vulnerability scanner. | Review release notes và policy trước khi nâng. |
| `dependencyManagement` đổi version nhưng component không xuất hiện. | Management không thêm dependency thật. | Kiểm dependency declarations/graph. |
| CVE medium nhưng có KEV exploit. | Score không phản ánh hết active exploitation. | Nâng priority theo threat intelligence. |
| Suppression wildcard khiến mọi CVE biến mất. | Suppression quá rộng, không có owner/expiry. | Scope từng finding và audit exceptions. |
| Test-scope dependency bị bỏ scan. | `skipTestScope` default true trong tool config. | Định nghĩa CI tool risk, bật scan bổ sung. |
| Maven plugin có CVE nhưng `dependency:tree` của app không thấy. | Plugin classpath riêng với project dependencies. | Kiểm build plugin versions/analyzer hỗ trợ. |
| SBOM thiếu thư viện native trong image. | Maven BOM chỉ biết các component thuộc scope của nó. | Container/OS scanner và combined SBOM. |
| Scanner pass PR nhưng CVE xuất hiện tuần sau. | Vulnerability data thay đổi qua thời gian. | Scan định kỳ cả deployed releases/SBOM. |
| Sửa Maven property mà không thấy version mới. | BOM/dependencyManagement override hoặc wrong module. | Xem help:effective-pom, tree và profile. |
| Tự động upgrade major làm API fail. | Breaking changes hoặc minimum Java mới. | Review changelog/migration và compatibility suite. |

**Thứ tự debug:** GAV + resolved graph → scanner/plugin/data freshness → advisory affected range → scope/reachability → version policy → test/CI logs → deployed artifact/SBOM.

## 38. Checklist áp dụng trong đội dự án

- [ ] Mọi Java Maven module có owner và nơi nhận vulnerability alerts.
- [ ] Có inventory **resolved** direct/transitive dependencies và plugin versions.
- [ ] Có scan tại PR/release và quét định kỳ deployed versions.
- [ ] Có NVD/API credentials/cache strategy và kiểm thời gian feed update.
- [ ] Phân biệt scanner infrastructure failure với actual vulnerability finding.
- [ ] Có triage record: component/GAV/version, CVE/advisory, paths, exposure, owner, due date.
- [ ] Kết hợp CVSS với KEV/EPSS, reachability và service criticality.
- [ ] Không coi version mới nhất là tự động an toàn.
- [ ] Patch/major upgrades đều có regression/integration/performance tests.
- [ ] Nâng transitive dependency có kiểm mediation, BOM và parent management.
- [ ] Exceptions/suppressions scoped, có ticket, review, expiry và kiểm unused rules.
- [ ] Enforcer bảo vệ những policies có thể thể hiện bằng rules.
- [ ] SBOM được tạo/lưu theo release artifact và Git SHA.
- [ ] SCA có quality gate, report xuất CI; không âm thầm `|| true` mọi failures.
- [ ] Có playbook xử lý urgent exploitation, EOL và không có patched release.
- [ ] Container/JDK/OS/native dependencies được scan bằng công cụ ngoài Maven.
- [ ] Build plugins/CI runners/repository access nằm trong supply-chain policy.
- [ ] Không để API key, token hoặc secrets trong POM/log/report public.
- [ ] Sau remediation, `dependency:tree`, tests và scan xác nhận version đã thay.
- [ ] Số lượng finding quá hạn và tỷ lệ fix/false-positive được theo dõi định kỳ.

## 39. Câu hỏi tự kiểm tra

1. **Đọc `pom.xml` có đủ thấy toàn bộ dependencies thực tế không?** Không; phải xem transitive resolved graph, BOM/management và scopes.
2. **CVSS 9.8 có chắc application bị khai thác không?** Không; cần match GAV/version, reachability, preconditions và exposure.
3. **KEV/EPSS có thay CVSS không?** Không; là tín hiệu bổ sung để ưu tiên.
4. **Dependency test bị lỗi có thể ảnh hưởng CI không?** Có; test tooling có thể xử lý dữ liệu và secrets.
5. **OWASP Dependency-Check có tự cập nhật POM lên bản vá không?** Không; scanner chỉ phân tích/báo cáo/chặn theo cấu hình.
6. **Default `failBuildOnCVSS=11` có chặn lỗ hổng CVSS 9.8 không?** Không theo threshold, vì CVSS chỉ đến 10.
7. **`failOnError=true` có nghĩa tất cả CVEs đều làm build fail?** Không; nó điều khiển lỗi thực thi tool, còn `failBuildOnCVSS` điều khiển findings gate.
8. **Scanner có thể báo false positive không?** Có; đặc biệt trong CPE/package identity mapping.
9. **Có nên suppress một CVE thực vì chưa có thời gian nâng cấp không?** Không gắn nhãn false positive; dùng risk acceptance/mitigation được duyệt.
10. **`dependencyManagement` có tự thêm một dependency bị thiếu không?** Không.
11. **Tại sao cần chạy `dependency:tree` sau upgrade?** Để xem effective resolved version và nhánh transitive thực.
12. **Versions Plugin `display-*` có sửa POM không?** Không; nó thông báo candidates, còn `update-*` có thể sửa.
13. **Upgrade major có phải luôn security tốt hơn?** Không; còn incompatibility, regression và license risk.
14. **CycloneDX BOM có tự chặn CVE không?** Không; nó chủ yếu tạo inventory, cần scanner/policy.
15. **Scan đã pass hôm qua có đảm bảo hôm nay không có CVE mới không?** Không; vulnerability feed thay đổi, cần quét lại định kỳ.
16. **Có cần quét Maven plugins/OS image không?** Có theo threat model; Maven project dependency scan không đủ bao phủ mọi lớp.
17. **POM có một library compile nhưng app dùng shaded binary, dependency tree có chắc phản ánh mọi class không?** Không; cần binary/SBOM review bổ sung.
18. **Một CVE đã patch trong source nhưng production còn image cũ có an toàn chưa?** Chưa; cần kiểm các deployments thật.
19. **Lỗi NVD API 429 có phải là CVE?** Không; đó là infrastructure/data-fetch failure, cần xử lý riêng.
20. **Một security gate đáng tin cần gì ngoài exit code?** Report, data freshness, context/triage, exceptions có hạn và bằng chứng test/build.

## 40. Tài liệu tham khảo chính thức

- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive graph, scopes, mediation, optional/exclusions và dependencyManagement.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): parent, BOM, dependencies, plugin configuration và repositories.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): resolved GAV/dependency graph.
- [Apache Maven Dependency Plugin — copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html): runtime classpath jars.
- [OWASP Dependency-Check — Maven Plugin Configuration](https://dependency-check.github.io/DependencyCheck/dependency-check-maven/configuration.html): `failBuildOnCVSS`, `failOnError`, NVD data, reports, scopes.
- [OWASP Dependency-Check — check goal](https://dependency-check.github.io/DependencyCheck/dependency-check-maven/check-mojo.html): Maven goal và properties phiên bản plugin.
- [OWASP Dependency-Check — Suppressing False Positives](https://dependency-check.github.io/DependencyCheck/general/suppression.html): CPE/GAV/PURL suppressions, expiration và review.
- [OWASP Dependency-Check Project](https://owasp.org/projects/dependency-check): nguyên lý Software Composition Analysis, các data sources và giới hạn.
- [MojoHaus Versions Maven Plugin](https://www.mojohaus.org/versions/versions-maven-plugin/): `display-*` và `update-*` goals.
- [MojoHaus Versions Plugin — display-dependency-updates](https://www.mojohaus.org/versions/versions-maven-plugin/display-dependency-updates-mojo.html): đọc versions mới mà không tự sửa POM.
- [Apache Maven Enforcer — Built-In Rules](https://maven.apache.org/enforcer/enforcer-rules/index.html): rule catalog, bannedDependencies, requireUpperBoundDeps, banDynamicVersions.
- [Apache Maven Enforcer — Dependency Convergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html): conflict/convergence.
- [Apache Maven Enforcer — Banned Dependencies](https://maven.apache.org/components/enforcer/enforcer-rules/bannedDependencies.html): cấm artifacts/versions, scan transitive graph.
- [CycloneDX Maven Plugin](https://cyclonedx.github.io/cyclonedx-maven-plugin/): `makeBom`, `makeAggregateBom`, SBOM formats.
- [CISA — Known Exploited Vulnerabilities Catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog): tín hiệu lỗ hổng bị khai thác.
- [FIRST — EPSS](https://www.first.org/epss/): xác suất exploit dự báo.
- [NIST — National Vulnerability Database](https://nvd.nist.gov/): CVEs, CVSS, dữ liệu vulnerability.
- [OpenSSF — Scorecard](https://securityscorecards.dev/): thực hành đánh giá dự án open-source, bổ sung nhưng không thay SCA.

**Kết luận:** Kiểm soát lỗ hổng Maven là một **vòng đời quản trị**: inventory GAV/transitive dependencies → scan/advisory data cập nhật → xác minh affected/exposure → ưu tiên dựa trên CVSS, exploit thực tế và criticality → upgrade/mitigate có review → test + rescan + SBOM → giám sát định kỳ. OWASP Dependency-Check giúp phát hiện và đặt quality gate; Versions Plugin tìm upgrade candidates; Enforcer giữ structural policies; CycloneDX lưu inventory. Không dùng “scanner pass” làm bảo đảm tuyệt đối và không dùng suppression để giấu các rủi ro chưa xử lý.
