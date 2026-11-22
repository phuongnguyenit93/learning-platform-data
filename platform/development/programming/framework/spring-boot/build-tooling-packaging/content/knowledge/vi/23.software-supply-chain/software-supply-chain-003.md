# Quét lỗ hổng dependency và đối chiếu phiên bản thực tế trong artifact

## 1. Vì sao phải quét cả dependency graph lẫn artifact?

Một ứng dụng Spring Boot có thể chỉ khai báo vài starter trong Maven hoặc Gradle, nhưng các starter kéo theo nhiều thư viện bắc cầu (*transitive dependencies*). Version ghi trong POM chưa chắc là version cuối cùng được chọn sau khi áp dụng BOM, dependency management, profile, exclusions và conflict resolution.

Khi đóng thành executable JAR, Spring Boot thường đặt dependencies trong **BOOT-INF/lib/**. Executable WAR đặt thư viện trong **WEB-INF/lib/** và có thể có thêm **WEB-INF/lib-provided/**. Vì vậy, để trả lời câu hỏi “bản phát hành thật đang chứa thư viện nào và version nào?”, cần kiểm tra chính archive đã build, không chỉ đọc POM.

Khi đóng ứng dụng thành container image, phạm vi còn rộng hơn: image có thể chứa JRE/JVM, OS packages và native libraries từ run image. Một dependency scanner chỉ nhìn Maven graph không thể thay thế việc quét image cuối.

> **Quy trình kiểm chứng có ba lớp:**  
> **(1) Dependency graph** cho biết build tool đã resolve gì; **(2) artifact inventory** cho biết archive thực sự đóng gói gì; **(3) container image scan** cho biết cả thư viện ứng dụng lẫn OS/runtime packages nào có trong image triển khai.

Bài này dùng Java 17, Spring Boot 3.5.16 và Maven làm ví dụ chính; có lệnh tương đương cho Gradle. Plugin scanner được pin để tái lập ví dụ, còn policy CVE và cơ sở dữ liệu lỗ hổng phải được cập nhật theo thời điểm quét.

### Mục tiêu sau bài

- Phân biệt dependency được khai báo, dependency được resolve, dependency được đóng vào JAR/WAR và package trong container image.
- Dùng Maven dependency tree và Gradle dependencyInsight để tìm version cuối.
- Dùng OWASP Dependency-Check để tìm lỗ hổng đã công bố trong dependency.
- Tạo CycloneDX SBOM để lưu component, version và quan hệ dependency.
- Dùng Trivy quét JAR/WAR, SBOM và container image.
- Đọc BOOT-INF/lib, WEB-INF/lib, WEB-INF/lib-provided và META-INF/maven/**/pom.properties.
- Viết chương trình Java 17 thuần để liệt kê GAV của nested JAR trong executable archive.
- Đối chiếu scanner với version thực tế, xử lý false positive và nâng dependency an toàn.
- Đặt quality gate CI, lưu report, SBOM, image digest và bằng chứng build.

## 2. Bốn loại thông tin cần phân biệt

| Loại thông tin | Nguồn | Trả lời câu hỏi nào? | Giới hạn |
|---|---|---|---|
| **Declared dependencies** | pom.xml, build.gradle(.kts), version catalog | Dự án yêu cầu thư viện nào? | Có thể chưa ghi version trực tiếp hoặc còn dependency bắc cầu |
| **Resolved dependency graph** | Maven dependency:tree, Gradle dependencies/dependencyInsight | Build tool cuối cùng chọn version nào và qua nhánh nào? | Chưa chứng minh component được đóng vào artifact |
| **Packaged components** | Nested JAR/WAR, pom.properties, SBOM hoặc scanner đọc archive | Bản phát hành thực sự chứa binary nào? | Shaded JAR hoặc binary thiếu metadata khó nhận diện đầy đủ |
| **Runtime image components** | Trivy image scan, image SBOM, OCI metadata | Container cuối chứa OS packages, JRE và application libraries nào? | Không thay thế kiểm tra cấu hình runtime và exploitability |

### 2.1. Dependency có trong graph nhưng không nằm trong JAR

Ví dụ:

- spring-boot-starter-test thường có scope test, không được đóng vào runtime JAR.
- Maven provided không nằm trong runtime classpath thông thường; executable WAR có thể đặt một số dependency ở WEB-INF/lib-provided/ để hỗ trợ embedded execution.
- Dependency optional có quy tắc truyền sang consumer khác dependency thông thường.
- Dependency bị exclusion loại khỏi một nhánh có thể vẫn được kéo vào từ nhánh khác.
- Thư viện có thể được shade/relocate vào JAR khác, làm mất cấu trúc nested JAR riêng.

Không kết luận “scanner tìm thấy dependency trong POM thì binary đó chắc chắn có trong production archive”. Hãy xem scope, packaging plugin và archive thật.

### 2.2. Component có trong image nhưng không có trong Maven graph

Ví dụ:

- JRE/JVM do Paketo Java buildpack cung cấp.
- OpenSSL, libc, CA certificates và OS packages đến từ run image.
- Native libraries được buildpack hoặc image extension cài thêm.
- Tool/agent được đưa vào image qua buildpack layers.

Đó là lý do phải quét **container image cuối** bên cạnh JAR/WAR. SBOM do Maven tạo thường mô tả component của project graph; nó không tự đại diện cho mọi package OS trong image.

## 3. Thuật ngữ bảo mật dependency

| Thuật ngữ | Ý nghĩa |
|---|---|
| **SCA (Software Composition Analysis)** | Phân tích component bên thứ ba, version, license và rủi ro |
| **CVE** | Mã định danh lỗ hổng đã được công bố |
| **CWE** | Phân loại loại điểm yếu phần mềm |
| **CVSS** | Điểm đánh giá mức nghiêm trọng kỹ thuật của lỗ hổng |
| **CPE** | Định danh sản phẩm/version thường dùng khi đối chiếu lỗ hổng |
| **PURL** | Package URL, định danh package theo hệ sinh thái |
| **SBOM** | Software Bill of Materials: danh sách component và quan hệ |
| **VEX** | Thông tin về khả năng lỗ hổng ảnh hưởng đến sản phẩm cụ thể |
| **Fix version** | Version đã sửa hoặc nằm ngoài dải bị ảnh hưởng |
| **False positive** | Scanner báo có vấn đề nhưng component/version thực tế không bị ảnh hưởng |
| **False negative** | Lỗ hổng tồn tại nhưng scanner không phát hiện hoặc không liên kết được component |

**Không đồng nhất CVE, CVSS và trạng thái khai thác.** CVE là định danh, CVSS là điểm nghiêm trọng; chúng không tự trả lời ứng dụng có gọi tới code dễ tổn thương hay không hoặc lỗ hổng có đang bị khai thác thực tế không. Khi ưu tiên xử lý, xem thêm advisory của nhà cung cấp, CISA Known Exploited Vulnerabilities (KEV), khả năng truy cập từ mạng, code path có thể kích hoạt và dữ liệu bị ảnh hưởng.

### 3.1. Quét dependency không phải kiểm thử bảo mật toàn diện

Dependency scanner tập trung vào **known vulnerabilities** trong component nhận diện được. Nó không tự chứng minh:

- Code ứng dụng không có SQL injection, authorization bug hay lỗi nghiệp vụ.
- Không có secret bị commit hoặc cấu hình sai.
- Mọi dependency đều có license phù hợp.
- Mọi binary được nhận diện chính xác nếu thiếu metadata.
- Không có lỗ hổng mới chưa được công bố trong database.
- Một CVE có thể khai thác được trong cách ứng dụng đang sử dụng thư viện.

Cần kết hợp SCA với SAST, secret scanning, IaC/container misconfiguration scanning, DAST hoặc penetration testing tùy yêu cầu.

## 4. Maven chọn phiên bản thực tế như thế nào?

### 4.1. BOM và dependencyManagement

Spring Boot parent/BOM quản lý nhiều version dependency đã được kiểm thử cùng nhau. POM có thể khai báo dependency mà không ghi version:

§§§xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
§§§

Maven đọc version management từ parent/BOM, resolve dependency bắc cầu và áp dụng quy tắc mediation. Version ghi trong một khai báo trực tiếp không phải lúc nào cũng là version cuối của toàn graph; dependency management, direct dependency và các nhánh bắc cầu có thể ảnh hưởng kết quả.

**Không tự nâng một dependency Spring riêng lẻ chỉ vì scanner gợi ý version cao hơn.** Nếu dependency thuộc Spring Boot BOM, trước tiên xem bản Spring Boot patch release nào đã cập nhật bộ dependency tương ứng. Override một thành phần đơn lẻ có thể tạo tổ hợp framework không nằm trong ma trận tương thích của Boot.

### 4.2. Xem dependency graph đã resolve

Từ thư mục root Maven project:

§§§bash
# Xem dependency hierarchy:
mvn dependency:tree

# Tập trung vào runtime và hiển thị node bị loại do conflict:
mvn dependency:tree -Dscope=runtime -Dverbose

# Lọc một dependency cụ thể:
mvn dependency:tree -Dscope=runtime \
  -Dincludes=com.fasterxml.jackson.core:jackson-databind

# Lưu graph:
mvn dependency:tree -Dscope=runtime -Dverbose \
  -DoutputFile=target/runtime-dependency-tree.txt
§§§

dependency:tree hiển thị hierarchy và version Maven build thực tế sử dụng. Với -Dverbose, output có thể cho thấy node bị loại vì conflict và version được chọn. Đừng chỉ đọc dòng dependency trực tiếp trong POM.

Ví dụ output **minh họa**:

§§§text
com.example:supply-chain-lab:jar:1.0.0
+- org.springframework.boot:spring-boot-starter-web:jar:3.5.16:compile
|  +- org.springframework.boot:spring-boot-starter:jar:3.5.16:compile
|  \- org.springframework:spring-webmvc:jar:<resolved-version>:compile
\- org.springframework.boot:spring-boot-starter-test:jar:3.5.16:test
   \- org.junit.jupiter:junit-jupiter:jar:<resolved-version>:test
§§§

Các token <resolved-version> là placeholder giải thích cấu trúc, không phải version thực để copy. Version thật phụ thuộc BOM, profile, dependency overrides và thời điểm build.

### 4.3. Xem effective POM và mismatch với BOM

§§§bash
# POM sau khi kế thừa parent, profile và property interpolation:
mvn help:effective-pom -Doutput=target/effective-pom.xml

# Kiểm tra dependency version được resolve có khác dependencyManagement:
mvn dependency:analyze-dep-mgt

# Tìm dependency dùng mà chưa khai báo hoặc khai báo nhưng không dùng:
mvn dependency:analyze
§§§

effective-pom giúp hiểu version management thực tế. dependency:analyze-dep-mgt tìm mismatch giữa dependency được resolve và dependencyManagement. dependency:analyze phân tích bytecode để tìm dependency dùng mà chưa khai báo hoặc khai báo nhưng không dùng.

dependency:analyze có thể không nhận ra dependency được gọi qua reflection, ServiceLoader, cấu hình XML, script hoặc plugin mechanism. Không xóa dependency chỉ dựa trên một warning mà chưa kiểm tra cách ứng dụng sử dụng.

### 4.4. Scope ảnh hưởng tới artifact

| Maven scope | Compile classpath | Runtime classpath | Ghi chú đóng gói |
|---|---|---|---|
| compile (mặc định) | Có | Có | Thường được đóng trong executable JAR |
| runtime | Không cần cho compile source | Có | Thường được đóng trong executable JAR |
| provided | Có | Không theo runtime classpath Maven thông thường | Executable WAR có thể đặt ở WEB-INF/lib-provided/ |
| test | Có trong test | Không | Không đóng vào app runtime JAR |
| system | Theo đường dẫn cục bộ | Theo cấu hình classpath | Khó tái lập, cần kiểm tra đặc biệt |
| optional | Tùy project khai báo | Có thể có trong app hiện tại | Không truyền sang consumer giống dependency thường |

Scope chỉ là một phần của quy tắc đóng gói. Hãy xem cấu hình Spring Boot Maven/Gradle plugin và file JAR/WAR sau build.

## 5. Đối chiếu phiên bản trong Spring Boot executable JAR/WAR

### 5.1. Cấu trúc executable JAR

Spring Boot Maven/Gradle plugin thường tạo executable JAR có cấu trúc:

§§§text
supply-chain-lab-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/supplychain/...
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-core-*.jar
    │   ├── jackson-databind-*.jar
    │   └── ... runtime dependencies khác
    ├── classpath.idx       (nếu được tạo)
    └── layers.idx          (nếu bật layered packaging)
§§§

Application classes nằm trong BOOT-INF/classes/; dependency JAR nằm trong BOOT-INF/lib/. Spring Boot Loader xử lý cấu trúc này khi chạy bằng java -jar.

**Đối chiếu phiên bản:** tên nested JAR thường có dạng artifactId-version.jar, nhưng tên file chưa phải bằng chứng duy nhất. Nên kiểm tra cả metadata Maven được nhúng trong từng JAR và đối chiếu với dependency tree/SBOM.

### 5.2. Cấu trúc executable WAR

§§§text
supply-chain-lab-1.0.0.war
├── META-INF/MANIFEST.MF
├── WEB-INF/
│   ├── classes/
│   ├── lib/
│   │   └── ... dependency JARs
│   └── lib-provided/
│       └── ... dependency phục vụ embedded execution
└── org/springframework/boot/loader/...
§§§

WEB-INF/lib/ chứa dependencies thông thường. WEB-INF/lib-provided/ chứa một số dependency cần khi chạy WAR bằng embedded container nhưng không cần khi triển khai lên servlet container truyền thống. Nếu artifact được chạy ở cả hai chế độ, hãy quét và kiểm tra đúng tập component cho từng cách triển khai.

### 5.3. Liệt kê nested libraries bằng JDK

Linux/macOS:

§§§bash
jar tf target/supply-chain-lab-1.0.0.jar |
  grep '^BOOT-INF/lib/'
§§§

Windows PowerShell:

§§§powershell
jar tf target/supply-chain-lab-1.0.0.jar |
  Select-String '^BOOT-INF/lib/'
§§§

Với executable WAR:

§§§bash
jar tf target/supply-chain-lab-1.0.0.war |
  grep -E '^WEB-INF/(lib|lib-provided)/'
§§§

Các lệnh này liệt kê đường dẫn và tên file trong archive. Muốn xem metadata Maven bên trong nested JAR, có thể trích thư viện ra thư mục tạm riêng:

§§§bash
mkdir -p target/archive-inspect
cd target/archive-inspect
jar xf ../supply-chain-lab-1.0.0.jar BOOT-INF/lib
find BOOT-INF/lib -name '*.jar'
§§§

Từng JAR có thể chứa:

§§§text
META-INF/maven/<groupId>/<artifactId>/pom.properties
META-INF/maven/<groupId>/<artifactId>/pom.xml
§§§

pom.properties thường ghi groupId, artifactId, version. Một số binary không có metadata này; shaded/uber JAR có thể chứa nhiều descriptor hoặc bị lọc mất metadata. Cần xử lý UNKNOWN và đối chiếu bằng scanner khác.

## 6. Java 17: chương trình kiểm kê phiên bản trong nested JAR

Chương trình sau dùng **chỉ JDK 17**, không cần thêm dependency. Nó mở executable Boot JAR/WAR như ZIP archive, tìm nested JAR trong BOOT-INF/lib/, WEB-INF/lib/, WEB-INF/lib-provided/, đọc META-INF/maven/**/pom.properties và in GAV cùng đường dẫn.

Tạo BootArchiveInventory.java:

§§§java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Properties;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipInputStream;

public final class BootArchiveInventory {

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println(
                "Usage: java BootArchiveInventory <app.jar|app.war>");
            System.exit(2);
        }

        try (ZipFile archive = new ZipFile(Path.of(args[0]).toFile())) {
            List<ZipEntry> libraries = new ArrayList<>();
            var entries = archive.entries();

            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                String name = entry.getName();

                boolean nestedLibrary =
                    name.startsWith("BOOT-INF/lib/")
                    || name.startsWith("WEB-INF/lib/")
                    || name.startsWith("WEB-INF/lib-provided/");

                if (!entry.isDirectory()
                        && nestedLibrary
                        && name.endsWith(".jar")) {
                    libraries.add(entry);
                }
            }

            libraries.sort(Comparator.comparing(ZipEntry::getName));
            System.out.println(
                "Nested dependency archives: " + libraries.size());

            for (ZipEntry library : libraries) {
                List<String> coordinates =
                    readCoordinates(archive.getInputStream(library));

                if (coordinates.isEmpty()) {
                    System.out.println(
                        "UNKNOWN\t" + library.getName());
                } else {
                    for (String gav : coordinates) {
                        System.out.printf(
                            "%s\t%s%n", gav, library.getName());
                    }
                }
            }
        }
    }

    private static List<String> readCoordinates(
            InputStream nestedJarBytes) throws IOException {

        List<String> result = new ArrayList<>();

        try (ZipInputStream nested =
                new ZipInputStream(nestedJarBytes)) {

            ZipEntry entry;

            while ((entry = nested.getNextEntry()) != null) {
                String name = entry.getName();

                if (name.startsWith("META-INF/maven/")
                        && name.endsWith("/pom.properties")) {

                    Properties properties = new Properties();
                    properties.load(nested);

                    String groupId = properties.getProperty("groupId");
                    String artifactId =
                        properties.getProperty("artifactId");
                    String version = properties.getProperty("version");

                    if (groupId != null
                            && artifactId != null
                            && version != null) {
                        result.add(
                            groupId + ":" + artifactId + ":" + version);
                    }
                }
            }
        }

        return result;
    }
}
§§§

Biên dịch và chạy bằng Java 17:

§§§bash
javac BootArchiveInventory.java
java BootArchiveInventory target/supply-chain-lab-1.0.0.jar
§§§

Với WAR:

§§§bash
java BootArchiveInventory target/supply-chain-lab-1.0.0.war
§§§

Output **phụ thuộc đúng artifact đã build**, ví dụ minh họa:

§§§text
Nested dependency archives: <count>
org.springframework.boot:spring-boot-*:3.5.16    BOOT-INF/lib/spring-boot-*.jar
org.springframework:spring-core:<resolved>      BOOT-INF/lib/spring-core-<resolved>.jar
com.fasterxml.jackson.core:jackson-databind:<resolved>    BOOT-INF/lib/jackson-databind-<resolved>.jar
§§§

<count> và <resolved> là placeholder giải thích, không phải stdout literal. Code này **kiểm kê metadata**, không quét CVE. Nếu JAR không có pom.properties, code in UNKNOWN; dùng tên file, manifest, SBOM, Trivy JSON hoặc nguồn phát hành để điều tra. Với shaded JAR có nhiều component đã gộp class, một descriptor không thể đại diện đầy đủ mọi thư viện được shade.

## 7. OWASP Dependency-Check: quét CVE trong dependency Maven

OWASP Dependency-Check là công cụ SCA nhận diện component và đối chiếu với lỗ hổng đã công bố, trong đó có dữ liệu từ National Vulnerability Database (NVD). Maven plugin có goal check cho từng project và aggregate để tổng hợp các module trong reactor.

### 7.1. Cấu hình Maven plugin

Ví dụ pin org.owasp:dependency-check-maven:13.0.0. Version này yêu cầu Maven 3.8.1+ và JDK 11+; project ví dụ sử dụng Java 17 và Maven 3.9.x.

Thêm vào build/plugins của POM:

§§§xml
<plugin>
    <groupId>org.owasp</groupId>
    <artifactId>dependency-check-maven</artifactId>
    <version>13.0.0</version>
    <configuration>
        <!-- Fail khi CVSS >= 7.0; policy minh họa. -->
        <failBuildOnCVSS>7.0</failBuildOnCVSS>
        <formats>
            <format>HTML</format>
            <format>JSON</format>
        </formats>
    </configuration>
    <executions>
        <execution>
            <id>dependency-vulnerability-check</id>
            <phase>verify</phase>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
§§§

Với cấu hình này, mvn verify gọi goal check. Report HTML/JSON thường được ghi vào target/. failBuildOnCVSS so với threshold đã chọn; nếu finding đạt hoặc vượt ngưỡng, build có thể fail.

**Chú ý:** mặc định failBuildOnCVSS là 11, trong khi CVSS thông thường nằm trong khoảng 0–10, nên mặc định này không tự làm build fail vì CVSS. Hãy cấu hình ngưỡng phù hợp policy; không giả định chỉ vì report có finding thì pipeline đã chặn release.

### 7.2. Chạy scan và xem report

§§§bash
# Chạy riêng goal:
mvn dependency-check:check

# Chạy toàn bộ lifecycle tới verify:
mvn clean verify
§§§

Report phổ biến:

§§§text
target/dependency-check-report.html
target/dependency-check-report.json
§§§

Tên file có thể thay đổi theo outputDirectory, report formats và plugin version. Đọc log goal để xác định path thật.

Trong report, tập trung vào component/version được nhận diện, CVE/advisory, severity/CVSS, affected version range, fixed version, dependency path và evidence mà analyzer dùng.

### 7.3. NVD API key và cache

Lần đầu chạy có thể mất nhiều thời gian vì plugin tải và xử lý dữ liệu NVD. OWASP Dependency-Check khuyến nghị duy trì cache và xem xét mirror dữ liệu khi tích hợp vận hành.

Nếu tổ chức cấp NVD API key, lưu credential trong Maven settings.xml dưới một server id và dùng cơ chế mã hóa password của Maven; sau đó cấu hình plugin tham chiếu nvdApiServerId. Không ghi API key trực tiếp vào POM, script CI hoặc dòng lệnh có thể xuất hiện trong process logs. Khi dùng -X, tránh để credential lộ trong debug output.

### 7.4. Suppression: chỉ dùng cho finding đã điều tra

False positive có thể xảy ra khi scanner ánh xạ nhầm component/version hoặc metadata của thư viện không đầy đủ. Dependency-Check hỗ trợ suppression file, nhưng suppression phải có kiểm soát:

- Chỉ định đúng package/CVE/version bị xác định sai.
- Ghi lý do và bằng chứng kỹ thuật.
- Có owner chịu trách nhiệm và ngày xem xét lại.
- Giới hạn phạm vi, tránh bỏ qua cả group/artifact rộng nếu không cần.
- Gỡ suppression khi component hoặc advisory thay đổi.

**Không suppress để làm build xanh** khi chưa xác minh component, version và ảnh hưởng. Nếu finding là thật, nâng dependency hoặc áp dụng mitigation có thể kiểm chứng.

### 7.5. Multi-module Maven

Trong reactor nhiều module, dependency-check:check có thể tạo report theo module. Goal aggregate tổng hợp dependencies của các child projects. Chọn goal theo cấu trúc reactor và giữ report của đúng build; không chỉ scan root POM rồi mặc định mọi module đều được phân tích.

## 8. CycloneDX: tạo SBOM để biết bản phát hành gồm gì

**SBOM không phải vulnerability scanner.** Nó là danh sách component có cấu trúc, có thể chứa version, supplier, identifiers và quan hệ dependency. Scanner có thể dùng SBOM để đối chiếu với vulnerability database.

CycloneDX Maven plugin tạo BOM chứa direct và transitive dependencies. Ví dụ pin 2.9.3, hỗ trợ CycloneDX 1.6:

§§§xml
<plugin>
    <groupId>org.cyclonedx</groupId>
    <artifactId>cyclonedx-maven-plugin</artifactId>
    <version>2.9.3</version>
    <executions>
        <execution>
            <id>generate-cyclonedx-bom</id>
            <phase>package</phase>
            <goals>
                <goal>makeBom</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <projectType>application</projectType>
        <schemaVersion>1.6</schemaVersion>
        <outputFormat>json</outputFormat>
        <includeTestScope>false</includeTestScope>
    </configuration>
</plugin>
§§§

Với một module, goal makeBom tạo SBOM cho module. Trong multi-module reactor, dùng makeAggregateBom để tạo BOM aggregate ở build root. Output mặc định thường ở target/bom.json; kiểm tra outputDirectory/outputName nếu POM thay đổi.

Chạy:

§§§bash
mvn cyclonedx:makeBom
§§§

Hoặc mvn clean package nếu đã bind execution vào phase package.

### 8.1. Maven SBOM và image SBOM khác nhau

| SBOM | Thường mô tả | Không nên mặc định chứa |
|---|---|---|
| Maven/CycloneDX makeBom | Dependencies theo Maven graph và scope được cấu hình | Toàn bộ OS packages trong run image |
| Trivy scan JAR/WAR | Component Java nhận diện trong archive và nested JAR | Mọi package hệ điều hành |
| Trivy image SBOM | Component được nhận diện trong final OCI image, gồm OS và language packages | Source dependency graph đầy đủ nếu metadata thiếu |
| Aggregate multi-module SBOM | Component của nhiều Maven modules | Những tool/plugin/runtime ngoài phạm vi BOM |

Với release container, nên lưu **Maven SBOM và image SBOM** hoặc SBOM được sinh trực tiếp từ image theo policy. Chúng trả lời hai câu hỏi khác nhau: graph của project và contents của image cuối.

## 9. Trivy: quét JAR/WAR, SBOM và container image

Trivy hỗ trợ Java JAR/WAR/PAR/EAR, pom.xml và Gradle lockfiles. Với JAR, Trivy đọc pom.properties/MANIFEST.MF và có thể nhận diện inner JAR. Khi cần xem đường dẫn nested dependency chi tiết, dùng JSON report vì table format có thể chỉ hiển thị tên root archive.

### 9.1. Quét POM/source directory

§§§bash
trivy fs --scanners vuln .
§§§

Trivy có thể phân tích POM và dependency files trong project để lập inventory và tìm vulnerability. Với Maven, phân tích POM có thể cần truy cập local/remote repositories để giải quyết metadata. Nếu bật offline mode, một số dependency không có trên máy local có thể bị bỏ qua; vulnerability database vẫn cần được cập nhật.

### 9.2. Quét executable JAR trực tiếp

Sau khi chạy mvn clean package:

§§§bash
trivy fs --scanners vuln \
  --format json \
  --output target/trivy-jar-report.json \
  target/supply-chain-lab-1.0.0.jar
§§§

Với executable WAR:

§§§bash
trivy fs --scanners vuln \
  --format json \
  --output target/trivy-war-report.json \
  target/supply-chain-lab-1.0.0.war
§§§

Trivy Java analyzer có thể phân tích inner JARs. JSON report hữu ích khi cần đối chiếu BOOT-INF/lib/... hoặc WEB-INF/lib/... với inventory của ứng dụng.

### 9.3. Quét container image cuối

Nếu ứng dụng được đóng thành image:

§§§bash
trivy image --scanners vuln \
  --format json \
  --output target/trivy-image-report.json \
  supply-chain-lab:1.0.0
§§§

Lệnh này quét vulnerabilities trong image, gồm OS packages và language-specific components mà Trivy nhận diện. Với image đa kiến trúc, chỉ định platform phù hợp khi cần, ví dụ --platform linux/arm64; không mặc định kết quả linux/amd64 đại diện cho image chạy trên ARM.

### 9.4. Tạo và quét SBOM của container image

§§§bash
trivy image \
  --format cyclonedx \
  --output target/image-sbom.cdx.json \
  supply-chain-lab:1.0.0

trivy sbom target/image-sbom.cdx.json
§§§

Theo mặc định, CycloneDX output của Trivy là SBOM; vulnerability findings không tự động được nhúng vào SBOM đó. Nếu cần xuất dữ liệu vulnerability cùng report CycloneDX, cấu hình scanner theo tài liệu Trivy và xác định rõ mục đích file.

SBOM do công cụ khác tạo có thể thiếu metadata tùy chỉnh mà Trivy dùng để nhận diện chính xác một số package. Khi kết quả scan SBOM khác scan image/JAR, so sánh component identifiers, paths và source metadata.

## 10. Ví dụ Maven Java 17 hoàn chỉnh để chạy pipeline scan

Ta tạo ứng dụng web tối giản để có executable JAR thật cho dependency graph, Dependency-Check, CycloneDX, archive inventory và Trivy.

### 10.1. Cấu trúc project

§§§text
supply-chain-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/supplychain/
    │   ├── SupplyChainApplication.java
    │   └── StatusController.java
    └── test/java/com/example/supplychain/
        └── StatusControllerTest.java
§§§

Ví dụ pin Spring Boot 3.5.16, Java 17, OWASP Dependency-Check 13.0.0 và CycloneDX Maven plugin 2.9.3. Đây là version phục vụ ví dụ; trước khi dùng trong dự án thật, đối chiếu compatibility và version policy của tổ chức.

### 10.2. pom.xml

§§§xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>supply-chain-lab</artifactId>
    <version>1.0.0</version>
    <name>Supply Chain Lab</name>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>

            <plugin>
                <groupId>org.owasp</groupId>
                <artifactId>dependency-check-maven</artifactId>
                <version>13.0.0</version>
                <configuration>
                    <failBuildOnCVSS>7.0</failBuildOnCVSS>
                    <formats>
                        <format>HTML</format>
                        <format>JSON</format>
                    </formats>
                </configuration>
                <executions>
                    <execution>
                        <id>dependency-vulnerability-check</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>check</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.cyclonedx</groupId>
                <artifactId>cyclonedx-maven-plugin</artifactId>
                <version>2.9.3</version>
                <configuration>
                    <projectType>application</projectType>
                    <schemaVersion>1.6</schemaVersion>
                    <outputFormat>json</outputFormat>
                    <includeTestScope>false</includeTestScope>
                </configuration>
                <executions>
                    <execution>
                        <id>generate-cyclonedx-bom</id>
                        <phase>package</phase>
                        <goals>
                            <goal>makeBom</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
§§§

Spring Boot plugin tạo executable JAR. Dependency-Check check chạy tại verify; CycloneDX makeBom chạy tại package. Ngưỡng CVSS 7.0 chỉ là policy minh họa: dự án phải chọn threshold theo rủi ro, loại sản phẩm và SLA xử lý.

### 10.3. Main class

SupplyChainApplication.java:

§§§java
package com.example.supplychain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SupplyChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(SupplyChainApplication.class, args);
    }
}
§§§

### 10.4. Controller có response xác định

StatusController.java:

§§§java
package com.example.supplychain;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/status")
    public String status() {
        return "supply-chain-lab: OK\n";
    }
}
§§§

### 10.5. Unit test

StatusControllerTest.java:

§§§java
package com.example.supplychain;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StatusControllerTest {

    @Test
    void returnsStableStatus() {
        assertEquals(
            "supply-chain-lab: OK\n",
            new StatusController().status()
        );
    }
}
§§§

Đây là unit test cho controller, không mở HTTP server. Nó xác nhận output logic; không thay thế scan artifact hoặc smoke test container.

### 10.6. Build và tạo report

Từ root có POM:

§§§bash
java -version
mvn -version
mvn clean verify
§§§

Sau khi build hoàn thành, output thường gồm:

§§§text
target/supply-chain-lab-1.0.0.jar
target/bom.json
target/dependency-check-report.html
target/dependency-check-report.json
target/runtime-dependency-tree.txt   (nếu đã lưu tree)
§§§

Tên report phụ thuộc plugin configuration. Nếu Dependency-Check phát hiện finding đạt threshold, mvn verify có thể kết thúc với BUILD FAILURE; report vẫn cần được lưu để điều tra. Build fail vì CVE **không có nghĩa compile/package sai**.

### 10.7. Chạy inventory và Trivy

§§§bash
# Xem resolved graph:
mvn dependency:tree -Dscope=runtime -Dverbose \
  -DoutputFile=target/runtime-dependency-tree.txt

# Liệt kê nested libraries:
jar tf target/supply-chain-lab-1.0.0.jar |
  grep '^BOOT-INF/lib/'

# Kiểm kê GAV bằng Java 17:
javac BootArchiveInventory.java
java BootArchiveInventory target/supply-chain-lab-1.0.0.jar

# Quét executable JAR:
trivy fs --scanners vuln target/supply-chain-lab-1.0.0.jar

# Quét Maven SBOM:
trivy sbom target/bom.json
§§§

Nếu đã tạo container image:

§§§bash
trivy image --scanners vuln supply-chain-lab:1.0.0
§§§

Kết quả phụ thuộc ngày quét, scanner version, vulnerability database và nội dung artifact. Không ghi cứng “0 vulnerabilities” làm output mẫu cho ứng dụng có dependencies thật.

### 10.8. Smoke test ứng dụng

Chạy JAR:

§§§bash
java -jar target/supply-chain-lab-1.0.0.jar
§§§

Từ terminal khác, khi Spring Boot đã sẵn sàng:

§§§bash
curl -fsS http://localhost:8080/status
§§§

HTTP body do controller trả về **chính xác**:

§§§text
supply-chain-lab: OK
§§§

Body có newline cuối. Spring Boot startup logs có thể xuất hiện trên console. Smoke test xác nhận artifact khởi động được; nó không chứng minh dependency không có CVE.

## 11. Đối chiếu kết quả của ba lớp

Sau khi chạy graph, archive inventory và image scan, lập bảng:

| Component | Maven resolved graph | Boot JAR/WAR | Container image | Việc cần kiểm tra |
|---|---|---|---|---|
| spring-core | Có version đã resolve | Có nested JAR trong BOOT-INF/lib | Có Java component | So GAV và CVE |
| jackson-databind | Có nếu được kéo vào | Có/không tùy runtime graph và packaging | Có/không tùy artifact | Kiểm tra transitive path |
| JUnit Jupiter | Scope test | Thường không có | Thường không có | Nếu thấy trong runtime artifact, kiểm tra packaging |
| Servlet container | Phụ thuộc starter/scope | WAR có thể có WEB-INF/lib hoặc lib-provided | Có thể nằm trong Java layer | Xác định embedded hay external |
| Java runtime | Không phải Maven dependency thông thường | Không nhất thiết nằm trong JAR | Có thể nằm trong buildpack launch layer | Quét image để thấy runtime |
| OpenSSL/CA packages | Không có trong Maven graph | Không có trong JAR | Có thể có trong OS base layers | Quét image OS packages |

### 11.1. Dấu hiệu lệch version

**Tình huống A — graph và archive trùng nhau:** version đã resolve xuất hiện trong BOOT-INF/lib; đây là trạng thái bình thường.

**Tình huống B — graph có dependency nhưng archive không có:** kiểm tra scope test/provided, optional, exclusions, plugin packaging và artifact cũ. Không kết luận ngay scanner thiếu component.

**Tình huống C — archive có JAR không thấy trong graph:** kiểm tra nested dependency được copy thủ công, custom plugin, local module, shaded/uber JAR, WEB-INF/lib-provided hoặc archive cũ.

**Tình huống D — filename và pom.properties khác nhau:** có thể artifact được rename/repackage, descriptor cũ, shaded JAR hoặc metadata sai. Ghi lại checksum, kiểm tra repository source và so với resolved coordinates.

**Tình huống E — image scan có OS CVE không có trong Maven report:** đây thường là package từ run image, buildpack runtime layer hoặc native OS package. Cập nhật base/run image hoặc package nền tương thích; sửa POM không giải quyết được mọi OS finding.

### 11.2. Phân biệt các công cụ

- Maven dependency:tree: cây dependency và version Maven resolve.
- Maven dependency:analyze: dependency dùng mà chưa khai báo/khai báo nhưng không dùng.
- Maven dependency:analyze-dep-mgt: resolved version khác version trong dependencyManagement.
- OWASP Dependency-Check: đối chiếu component với vulnerability advisories.
- CycloneDX: ghi inventory và quan hệ dependency.
- Trivy: quét filesystem, JAR/WAR, SBOM và image theo scanner hỗ trợ.

Không có một lệnh nào thay thế tất cả.

## 12. Gradle: xem runtimeClasspath, khóa version và xác minh artifact

### 12.1. Xem dependency graph

§§§bash
# Runtime graph:
./gradlew dependencies --configuration runtimeClasspath

# Lý do một dependency được chọn:
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath

# Compile graph:
./gradlew dependencies --configuration compileClasspath
§§§

dependencyInsight cho biết version selection reason, constraints và các nhánh yêu cầu dependency. Đây là công cụ quan trọng khi BOM, version catalog hoặc transitive dependencies khiến version được chọn khác mong đợi.

### 12.2. Dependency locking

Gradle hỗ trợ dependency locking để ghi lại resolved versions. Ví dụ trong build.gradle:

§§§groovy
dependencyLocking {
    lockAllConfigurations()
}
§§§

Sau khi cấu hình, resolve các configuration cần thiết và ghi lock state:

§§§bash
./gradlew dependencies --write-locks
./gradlew build
§§§

Lock file giúp build dùng lại version đã resolve, hạn chế version động thay đổi giữa hai lần build. Locking **không** chứng minh artifact an toàn hoặc không có CVE; nó chỉ cố định dependency selection.

### 12.3. Dependency verification

Gradle dependency verification hỗ trợ checksum/signature để kiểm tra tính toàn vẹn và nguồn gốc artifact tải về:

§§§bash
./gradlew --write-verification-metadata sha256 help
§§§

Lệnh bootstrap tạo gradle/verification-metadata.xml. Phải review diff và xác minh checksum/signature từ nguồn đáng tin trước khi chấp nhận metadata. Bootstrap từ repository đã bị compromise có thể ghi lại checksum của chính binary độc hại.

**Dependency verification khác vulnerability scanning:** checksum/signature xác minh artifact có đúng nội dung/nguồn đã tin cậy không; SCA đối chiếu component/version với database lỗ hổng đã biết. Cần cả hai khi policy yêu cầu.

### 12.4. Quét artifact Gradle

Sau khi bootJar tạo archive:

§§§bash
./gradlew clean test bootJar

jar tf build/libs/supply-chain-lab-1.0.0.jar |
  grep '^BOOT-INF/lib/'

trivy fs --scanners vuln build/libs/supply-chain-lab-1.0.0.jar
§§§

Đường dẫn output phụ thuộc archiveBaseName, archiveVersion, classifier và cấu hình Gradle. Đối chiếu runtimeClasspath với BOOT-INF/lib của đúng JAR được release, không dùng artifact cũ trong build/libs.

## 13. Đánh giá finding và chọn cách sửa

Một finding CVSS cao không tự động đồng nghĩa ứng dụng đang bị khai thác; finding CVSS thấp cũng không tự động an toàn. Cần đánh giá:

1. Component/version có thật trong artifact/image đang triển khai không?
2. Version có nằm trong affected range của advisory không?
3. Có fixed version hoặc patch của vendor không?
4. Code path dễ tổn thương có được gọi trong ứng dụng không?
5. Endpoint có thể bị truy cập từ Internet hay chỉ từ mạng nội bộ?
6. Lỗ hổng có trong CISA KEV hoặc có exploit thực tế được công bố không?
7. Có mitigation khả thi trong khi chờ patch không?
8. Upgrade có phá Java baseline, Spring Boot compatibility, API hoặc serialization behavior không?

### 13.1. Thứ tự xử lý

- **Xác nhận component:** GAV, PURL, version, archive path và checksum.
- **Xác nhận advisory:** CVE, affected versions, fixed version, release notes.
- **Tìm dependency path:** direct hay transitive, module nào kéo vào.
- **Chọn cách sửa:** nâng direct dependency, parent/BOM, starter hoặc loại dependency không cần thiết.
- **Kiểm thử tương thích:** compile, unit/integration tests, smoke test và regression.
- **Build lại:** không sửa trực tiếp JAR trong target/ rồi phát hành.
- **Quét lại artifact/image:** chứng minh version mới có mặt và finding đã được xử lý.
- **Lưu bằng chứng:** reports, SBOM, commit, image digest, owner và thời điểm scan.

### 13.2. Ví dụ nâng dependency bắc cầu

Giả sử report chỉ ra org.example:example-parser được kéo vào từ một starter. Không thêm version ngẫu nhiên vào POM. Làm theo thứ tự:

1. Chạy mvn dependency:tree -Dverbose -Dincludes=org.example:example-parser.
2. Xác định starter hoặc dependency trực tiếp kéo component vào.
3. Xem Spring Boot BOM đang quản lý version nào.
4. Kiểm tra Spring Boot patch release hoặc upstream release đã sửa lỗ hổng.
5. Ưu tiên nâng BOM/parent phù hợp.
6. Nếu buộc override, ghi lý do và test compatibility.
7. Build lại rồi kiểm tra version trong BOOT-INF/lib và scan JAR/image.

Với dependency thuộc framework, nâng cả bộ version được framework kiểm thử thường an toàn hơn việc tự override một thành phần nền.

### 13.3. Suppression không phải remediation

Suppression chỉ điều chỉnh cách scanner báo finding; nó **không thay đổi binary** và không vá CVE. Khi dùng suppression, lưu lý do false positive hoặc lý do chấp nhận rủi ro, giới hạn đúng package/version/CVE, có người phê duyệt và lịch review. Không dùng suppression rộng để làm build xanh.

## 14. Nguồn false positive/false negative

| Nguyên nhân | Hệ quả | Cách điều tra |
|---|---|---|
| CPE match không chính xác | False positive | Kiểm tra GAV/PURL, vendor, version và advisory |
| JAR thiếu pom.properties/manifest | Không nhận diện được hoặc nhận sai version | Đối chiếu filename, repository, checksum, SBOM |
| Shaded/uber JAR | Một archive chứa code của nhiều component nhưng metadata không đầy đủ | Xem shading config, SBOM và analyzer |
| Vendor backport patch | Scanner có thể đánh giá theo upstream version chưa phản ánh patch | Đọc vendor advisory/package metadata |
| Vulnerability DB chưa cập nhật | Finding mới chưa xuất hiện | Cập nhật database, ghi scan timestamp |
| Scanner không hỗ trợ định dạng | Bỏ sót package | Quét bằng tool khác, kiểm tra archive |
| Scope khác nhau giữa POM và archive | Finding không khớp kỳ vọng | Đối chiếu dependency tree, scope và BOOT-INF/lib |
| Dependency bị copy thủ công | Không xuất hiện trong graph | Inventory archive và tìm nguồn binary |
| OS package trong image | Không xuất hiện trong Maven report | Quét final container image |
| Test/dev dependency | Có trong source graph nhưng không có runtime artifact | Kiểm tra scope và scanner policy |
| Suppression quá rộng | Che finding thật | Review suppression và bỏ rule không còn cần |

**Không xem “0 vulnerabilities” là chứng minh phần mềm an toàn.** Kết quả chỉ có nghĩa scanner không tìm thấy finding theo database, analyzer, metadata và phạm vi của lần quét đó.

## 15. Tích hợp CI/CD: chặn đúng thứ, lưu đúng bằng chứng

Một pipeline phát hành Spring Boot có thể đi theo thứ tự:

§§§text
1. Resolve dependencies
        |
2. Compile + unit/integration tests
        |
3. Generate executable JAR/WAR
        |
4. Dependency-Check + CycloneDX SBOM
        |
5. Inventory nested libraries and compare resolved versions
        |
6. Trivy scan JAR/WAR and SBOM
        |
7. Build OCI image
        |
8. Trivy scan final image (OS + application components)
        |
9. Review findings / enforce policy
        |
10. Publish immutable image digest + reports + SBOM
        |
11. Deploy the verified digest
§§§

### 15.1. Quality gates gợi ý

| Gate | Điều kiện mẫu | Hành động |
|---|---|---|
| Build correctness | Compile/test/package thành công | Dừng nếu fail |
| Dependency policy | Không có unresolved version conflict chưa được chấp nhận | Điều tra BOM/constraints |
| Vulnerability threshold | Không có finding đạt threshold policy | Fail hoặc yêu cầu phê duyệt |
| Critical/KEV | Component bị khai thác hoặc risk policy cấm | Chặn release theo policy |
| Artifact consistency | GAV/version trong archive khớp resolved graph theo scope | Fail nếu mismatch chưa giải thích |
| SBOM | Có BOM cho đúng build/artifact | Lưu làm release evidence |
| Image scan | OS/runtime/app findings đạt policy | Chặn hoặc tạo exception có owner |
| Integrity | Digest/checksum và provenance được lưu | Chỉ deploy artifact đã xác minh |
| Runtime smoke test | App khởi động và endpoint kiểm tra thành công | Không deploy nếu fail |

Threshold CVSS >= 7.0 trong POM chỉ là ví dụ. Tổ chức nên bổ sung exploitability, exposure, asset criticality và thời gian khắc phục. Không để một ngưỡng duy nhất thay thế risk review.

### 15.2. Những file nên lưu theo release

§§§text
release-evidence/
├── runtime-dependency-tree.txt
├── effective-pom.xml
├── dependency-check-report.html
├── dependency-check-report.json
├── bom.json
├── trivy-jar-report.json
├── trivy-image-report.json
├── image-sbom.cdx.json
├── artifact-sha256.txt
└── image-digest.txt
§§§

Tên và số lượng report phụ thuộc pipeline; mục đích là truy ngược từ image digest về source/build, dependency versions, scanner database và quyết định xử lý finding.

### 15.3. Multi-module Maven

Với reactor nhiều module:

- dependency:tree chạy ở đúng module để xem graph module đó.
- dependency-check:aggregate có thể tạo báo cáo aggregate; vẫn giữ report theo module khi cần tìm owner.
- CycloneDX makeAggregateBom tổng hợp các module trong reactor.
- Artifact inventory phải chạy trên **đúng executable JAR/WAR** của app được phát hành.
- Không dùng BOM aggregate làm bằng chứng duy nhất rằng mọi binary đã được đóng vào app.
- Nếu nhiều ứng dụng được release riêng, lưu SBOM/image digest riêng cho từng app.

## 16. Lỗi thường gặp và hướng khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| dependency:tree có version khác POM | BOM, mediation hoặc direct override | Xem -Dverbose, effective POM và dependency path |
| Không thấy dependency trong BOOT-INF/lib | Scope/test/provided/exclusion hoặc artifact cũ | Kiểm tra scope, đúng JAR, packaging plugin |
| JAR chứa library không có trong graph | Copy thủ công, shading, local module hoặc archive cũ | Kiểm tra plugin, build inputs, checksum |
| Dependency-Check không chạy trong mvn package | Goal gắn ở verify | Chạy mvn verify hoặc gọi goal trực tiếp |
| Lần scan đầu rất lâu | Tải và xử lý vulnerability database | Dùng cache/mirror, cấp API key đúng cách |
| Dependency-Check báo finding lặp | Cùng component xuất hiện qua nhiều đường | Gom theo GAV/CVE, đọc dependency path |
| Trivy JAR không nhận diện version | Thiếu pom.properties/manifest | Đọc archive, filename, SBOM và hash |
| Trivy image có OS CVE không có trong POM | Run image/OS package | Nâng builder/run image hoặc package nền |
| trivy sbom không khớp image scan | SBOM thiếu properties hoặc không cùng artifact | Tạo lại SBOM từ image đã scan và so digest |
| CVE không có fixed version | Chưa có bản vá hoặc advisory chưa cập nhật | Kiểm tra vendor, mitigation và theo dõi |
| Nâng dependency gây lỗi compile/runtime | Version không tương thích framework/API | Nâng BOM/Boot patch phù hợp, chạy regression |
| Build fail do failBuildOnCVSS | Finding đạt threshold | Điều tra finding; không hạ threshold để che |
| Report không có JSON | Chỉ cấu hình HTML hoặc output format sai | Kiểm tra formats và plugin version |
| SBOM không chứa OS packages | SBOM sinh từ Maven graph | Tạo SBOM từ final container image |
| Scan pass nhưng image deploy vẫn cũ | Deploy nhầm tag/digest | So image digest và release record |
| CVE mới xuất hiện sau deploy | Database/advisory được cập nhật | Rescan SBOM/image đã phát hành |
| Dependency verification fail checksum | Binary khác checksum đã tin | Dừng sử dụng, xác minh nguồn; không tự động chấp nhận checksum mới |

## 17. Checklist trước khi release

- [ ] Đã xác định đúng executable JAR/WAR sẽ phát hành.
- [ ] Đã xem Maven dependency tree runtime verbose hoặc Gradle runtimeClasspath.
- [ ] Đã kiểm tra BOM, effective POM và version overrides.
- [ ] Đã xác định direct/transitive dependency path cho finding quan trọng.
- [ ] Đã chạy OWASP Dependency-Check với database cập nhật và threshold rõ.
- [ ] Đã tạo CycloneDX SBOM và lưu theo build.
- [ ] Đã liệt kê BOOT-INF/lib, WEB-INF/lib, WEB-INF/lib-provided khi phù hợp.
- [ ] Đã đối chiếu version trong archive với resolved graph.
- [ ] Đã quét chính JAR/WAR, không chỉ quét POM.
- [ ] Đã quét final container image để phát hiện OS/JRE/runtime packages.
- [ ] Đã kiểm tra finding theo advisory, fixed version, reachability và exposure.
- [ ] Suppression có lý do, owner và review date.
- [ ] Đã build lại và quét lại sau khi nâng dependency.
- [ ] Đã lưu report, SBOM, checksum và image digest.
- [ ] Đã chạy unit/integration tests và smoke test artifact/image.
- [ ] Chỉ deploy đúng image digest đã được xác minh.

**Kết luận:** Muốn biết ứng dụng Spring Boot có dependency dễ tổn thương hay không, phải kết hợp **resolved dependency graph**, **phiên bản binary thực tế trong JAR/WAR** và **component trong container image**. Maven/Gradle cho biết version được chọn; OWASP Dependency-Check và Trivy đối chiếu với dữ liệu lỗ hổng; CycloneDX ghi inventory; còn việc đọc nested archive giúp chứng minh artifact đã đóng gói đúng version. Khi ba lớp kết quả khớp nhau, team mới có cơ sở tin rằng bản phát hành đã được quét và có thể truy vết.

### Tài liệu chính thức

- [Apache Maven Dependency Plugin — dependency tree và dependency analysis](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
- [Spring Boot — Executable JAR và nested dependencies](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [OWASP Dependency-Check Maven Plugin — Usage](https://jeremylong.github.io/DependencyCheck/dependency-check-maven/index.html)
- [OWASP Dependency-Check Maven Plugin — Configuration](https://jeremylong.github.io/DependencyCheck/dependency-check-maven/configuration.html)
- [OWASP Dependency-Check — Plugin goals và requirements](https://jeremylong.github.io/DependencyCheck/dependency-check-maven/plugin-info.html)
- [CycloneDX Maven Plugin — SBOM generation](https://cyclonedx.github.io/cyclonedx-maven-plugin/)
- [CycloneDX — Specification overview](https://cyclonedx.org/specification/overview/)
- [Trivy — Java package coverage](https://trivy.dev/docs/latest/guide/coverage/language/java/)
- [Trivy — Filesystem scanning](https://trivy.dev/docs/latest/guide/target/filesystem/)
- [Trivy — Container image scanning](https://trivy.dev/docs/latest/guide/target/container_image/)
- [Trivy — SBOM generation and scanning](https://trivy.dev/docs/latest/supply-chain/sbom/)
- [Gradle — Dependency locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle — Dependency verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [NIST — National Vulnerability Database](https://nvd.nist.gov/)
- [CISA — Known Exploited Vulnerabilities Catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
