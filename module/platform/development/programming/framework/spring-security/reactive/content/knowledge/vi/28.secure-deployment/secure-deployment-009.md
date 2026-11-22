# Gia cố phụ thuộc và kiểm tra thông báo lỗ hổng theo phiên bản — Spring Security Reactive

## 1. Mục tiêu

Một ứng dụng Spring Security chạy trên Spring WebFlux có thể được cấu hình xác thực và phân quyền đúng nhưng vẫn gặp rủi ro từ thư viện có lỗ hổng: Spring Security, Spring Framework, Reactor Core, Reactor Netty, Netty, thư viện JWT/OAuth2, JSON parser, HTTP client, logging hoặc các dependency bắc cầu (transitive).

Bài này hướng dẫn cách:
1. Xác định **đúng các phiên bản thực sự được build, đóng gói và chạy**; phân biệt dependency khai báo với phiên bản đã giải quyết.
2. Tra cứu thông báo bảo mật (security advisory) theo **artifact, phiên bản, nhánh hỗ trợ, điều kiện khai thác và bản sửa**.
3. Nâng cấp an toàn theo BOM/compatibility matrix của Spring Boot, có kiểm thử hồi quy đặc thù WebFlux/Spring Security.
4. Tự động tạo SBOM, quét Software Composition Analysis (SCA), quản lý cảnh báo và chứng minh bản vá đã nằm trong artifact triển khai.

**Nguyên tắc:** Không kết luận một hệ thống an toàn chỉ vì dependency scanner cho kết quả xanh, và cũng không mặc định mọi CVE mà scanner nêu đều khai thác được trong hệ thống. Cần kết hợp phiên bản thực tế, điều kiện trong advisory, cấu hình runtime, mức độ phơi nhiễm và bằng chứng kiểm thử.

## 2. Bề mặt phụ thuộc của ứng dụng reactive

Một dịch vụ Spring Boot WebFlux có thể dùng:
- **Spring Security:** spring-security-core, spring-security-config, spring-security-web, các module OAuth2 client/resource server, JOSE/JWT và test.
- **Spring WebFlux / Framework:** spring-webflux, spring-web, các module Spring Framework hỗ trợ.
- **Reactive runtime:** reactor-core, reactor-netty-http, Netty transport, HTTP codec, TLS/HTTP2 và các module Netty bắc cầu.
- **HTTP client và định danh:** WebClient, JWT/JWK xử lý chữ ký, thư viện OAuth2/OIDC/JOSE được kéo vào qua các starter.
- **Serialization/quan sát:** Jackson, logging framework, Micrometer, tracing bridges, OTEL/Brave.
- **Phần mềm triển khai:** JDK/JRE, base container image, native libraries, reverse proxy, ingress, API gateway. Những phần này cần luồng quét riêng ngoài Maven/Gradle.

**Chú ý phân biệt stack:** WebFlux dùng SecurityWebFilterChain, WebFilter, Reactor Context và Reactor Netty thường gặp. Các lỗ hổng liên quan Servlet filter, HttpSession hoặc Tomcat có thể không áp dụng khi dịch vụ không sử dụng chúng; ngược lại, lỗ hổng Reactor Netty, reactive security hoặc WebClient có thể bị bỏ sót nếu chỉ rà soát phần servlet. Một ứng dụng có cả thư viện servlet và reactive không tự động có cùng đường khai thác: phải kiểm tra web application type và cấu hình thực chạy.

Hãy ghi nhận cả các dependency thuộc nhánh test/build và plugin; chúng có thể không nằm trong runtime nhưng vẫn ảnh hưởng môi trường CI hoặc chuỗi cung ứng. Phân loại chúng rõ để không suy diễn rằng một thư viện chỉ xuất hiện ở test classpath cũng được đóng gói vào production.

## 3. Phát hiện đúng phiên bản đã được giải quyết

Dependency khai báo có thể được quản lý bởi parent POM, BOM, Gradle platform, constraints, resolution rules hoặc dependency transitive. Vì vậy khai báo không có số phiên bản không có nghĩa là ứng dụng dùng “phiên bản mới nhất”. Việc kiểm tra CVE phải dựa vào **resolved dependency graph** của chính commit và build dùng để triển khai.

### Maven: liệt kê dependency và nguồn quản lý phiên bản

Chạy từ thư mục dự án có Maven Wrapper:

~~~bash
./mvnw dependency:tree
./mvnw dependency:tree -Dscope=runtime
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
~~~

Trên Windows có thể dùng mvnw.cmd thay cho ./mvnw. Lệnh đầu hiển thị dependency trực tiếp và bắc cầu, lệnh thứ hai tập trung runtime classpath, lệnh cuối tạo effective POM để kiểm tra parent, dependencyManagement và các override. Với dự án nhiều module, chạy ở module đóng gói ứng dụng hoặc kiểm tra cây dependency của từng module liên quan; kết quả ở root không phải lúc nào cũng tương đương artifact được deploy.

Tìm các tọa độ quan trọng như:
- org.springframework.security:spring-security-web
- org.springframework.security:spring-security-config
- org.springframework:spring-webflux
- io.projectreactor:reactor-core
- io.projectreactor.netty:reactor-netty-http
- io.netty:netty-handler
- các thư viện xử lý JWT/OAuth2 xuất hiện trong cây thực tế.

Tìm **phiên bản resolved** và nhánh kéo thư viện vào, thay vì chỉ tìm một string trong pom.xml.

### Gradle: kiểm tra runtimeClasspath và đường giải quyết

Trong dự án Gradle có Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty-http --configuration runtimeClasspath
~~~

Lệnh dependencyInsight cho biết vì sao một phiên bản được chọn, ví dụ do BOM, constraint, conflict resolution hoặc dependency transitive. Đối với multi-project build, chạy task của từng subproject phù hợp. Trên Windows thay ./gradlew bằng gradlew.bat.

**Chứng minh phiên bản khi deploy:** Build báo một phiên bản chưa đủ. Hãy đối chiếu dependency graph/SBOM với nội dung JAR/WAR và image thực sự đang chạy; cùng source code nhưng artifact được build ở thời điểm khác có thể có thư viện khác. Ghi lại commit SHA, build ID, artifact digest, base image digest và SBOM. Đừng dựa vào số phiên bản ghi trong một bảng theo dõi thủ công nếu thiếu bản build tương ứng.

## 4. BOM và tính tương thích: cập nhật theo cả họ Spring

Spring Boot quản lý nhiều dependency bằng spring-boot-dependencies BOM; Maven starter parent và Gradle dependency-management/platform có thể dùng BOM để chọn các phiên bản tương thích. Với Spring Security Reactive, nâng cấp một JAR lẻ đôi khi làm lệch phiên bản Spring Security, Framework, Reactor và Netty.

**Maven (phần của pom.xml cho dự án đã dùng Spring Boot parent):**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
~~~

Đây là **đoạn POM**, không phải POM hoàn chỉnh. Phiên bản starter được quản lý khi parent/BOM phù hợp đã được cấu hình ở nơi khác. Nếu chỉ dùng HTTP Basic hoặc form login, không tự thêm OAuth2 Resource Server; chỉ giữ dependency thật sự có nhu cầu. Nếu quản lý version bằng BOM nhưng không dùng starter parent, phải khai báo import BOM đúng theo cấu hình build hiện tại.

**Gradle (Kotlin DSL, phần dành cho build đã áp dụng Spring Boot plugin):**

~~~kotlin
dependencies {
    implementation(platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    ))
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
}
~~~

Gradle còn có cách dùng plugin io.spring.dependency-management để tự import BOM. Đoạn Kotlin trên minh họa cách dùng native Gradle platform, không phải file build.gradle.kts độc lập. Kiểm tra BOM đã thực sự được import bằng dependencies và dependencyInsight.

**Quy trình chọn version:**
1. Xác định nhánh Spring Boot đang dùng và còn được hỗ trợ bảo mật hay không.
2. Tra Spring Security/Spring Framework/Reactor Netty bị ảnh hưởng theo advisory; tìm bản vá trên **nhánh tương thích**.
3. Ưu tiên bản Spring Boot patch/minor có managed versions đã được sửa; kiểm tra release notes và dependency versions được Spring Boot quản lý.
4. Nếu cần override một dependency khẩn cấp trước khi BOM cập nhật, ghi rõ lý do, phạm vi override, tương thích nhị phân, test và ngày gỡ override. Tránh cưỡng ép đồng loạt phiên bản bằng resolutionStrategy.force hoặc exclude vô điều kiện.
5. Với upgrade qua major/minor, kiểm tra Java baseline, hướng dẫn migration, thay đổi API SecurityWebFilterChain, OAuth2/JWT và behavior framework.

Bản patch thường ít thay đổi API hơn major/minor, nhưng **không đảm bảo** không có thay đổi hành vi: bản vá bảo mật có thể chủ ý siết kiểm tra và làm lộ lỗi cấu hình trước đó. Không trì hoãn vô thời hạn bằng cách giữ một nhánh đã hết hỗ trợ.

## 5. Nguồn tin bảo mật và cách đọc advisory

Nguồn nên ưu tiên theo thứ tự:
1. **Advisory của chính nhà phát hành:** [Spring Security Advisories](https://spring.io/security/), mô tả điều kiện gây lỗi, phiên bản ảnh hưởng, fixed version và availability.
2. **Ghi chú phát hành và chính sách hỗ trợ:** Spring Boot, Spring Security, Reactor/Netty cho nhánh đang vận hành.
3. **Cơ sở dữ liệu lỗ hổng:** [NVD](https://nvd.nist.gov/), [GitHub Advisory Database](https://github.com/advisories), [OSV](https://osv.dev/) để đối chiếu CVE, GHSA, package ecosystems và metadata.
4. **Thông tin khai thác thực tế:** [CISA Known Exploited Vulnerabilities](https://www.cisa.gov/known-exploited-vulnerabilities-catalog) khi đánh giá ưu tiên; không dùng mỗi điểm CVSS để thay thế bối cảnh triển khai.

Một advisory thường có:
- **CVE/GHSA và ngày công bố**: định danh và mốc để theo dõi, không phải phiên bản thư viện.
- **Affected products/versions**: khoảng phiên bản bị ảnh hưởng; đọc kỹ dấu mốc inclusive, nhánh và cách đánh số. Không so sánh phiên bản như chuỗi ký tự thuần (ví dụ 1.3.10 khác 1.3.7).
- **Conditions/prerequisites**: thành phần phải có, phương thức gọi, tính năng kích hoạt, cấu hình, cách hệ thống lộ ra bên ngoài.
- **Fix versions/availability**: nhánh và bản vá tương ứng; phân biệt OSS và Enterprise Support Only.
- **Mitigation/workaround**: biện pháp tạm thời và giới hạn của nó; không tự coi workaround là bản vá vĩnh viễn.
- **Migration/behavior changes**: có thể phải đổi cấu hình, API hoặc dữ liệu mã hóa; không chỉ thay số phiên bản.

Lưu bản snapshot của kết luận theo thời điểm đánh giá, nhưng kiểm tra lại trước release vì advisory có thể được chỉnh sửa, bổ sung nhánh hoặc rút lại nhận định.

## 6. Đối chiếu CVE với đúng phiên bản và điều kiện sử dụng

Với **mỗi dependency có cảnh báo**, đi theo chuỗi:

**Artifact thực tế → phiên bản resolved → advisory chính thức → điều kiện tác động → phiên bản sửa cùng nhánh → bằng chứng upgrade/test → quyết định.**

Mẫu bảng điều tra:

| Mục | Cần ghi |
| --- | --- |
| Artifact và phạm vi | Maven coordinates, module, runtime/test/build, đường dependency transitive |
| Phiên bản thực tế | Version trong lockfile/SBOM/JAR hoặc image theo build ID |
| Advisory | CVE/GHSA, URL nhà phát hành, ngày kiểm tra |
| Điều kiện tác động | WebFlux vs Servlet, tính năng, runtime config, quyền kẻ tấn công, dữ liệu liên quan |
| Kết luận | Affected và reachable; affected nhưng không sử dụng tính năng; false positive; đang xác minh |
| Xử lý | Fixed version, nhánh hỗ trợ, mitigation tạm, tests, deadline, người phụ trách |
| Bằng chứng | PR, diff dependency tree, báo cáo SCA mới, kết quả regression test, artifact digest |

Không mặc định trạng thái "not exploitable" chỉ vì không thấy lời gọi API trực tiếp: dependency transitive, auto-configuration, library reflection hoặc framework entry points có thể gọi thay ứng dụng. Kết luận về reachability phải có code/config review hoặc công cụ đáng tin; nếu thiếu bằng chứng, để trạng thái "chưa xác minh" và áp dụng biện pháp giảm thiểu thích hợp.

## 7. Ví dụ thật: CVE-2026-47844 với Reactor Netty

Theo [thông báo chính thức CVE-2026-47844](https://spring.io/security/cve-2026-47844/) công bố ngày **20/08/2026**, Reactor Netty HTTP Server có thể làm lộ chi tiết exception giữa những request không liên quan **trong một số tình huống khi server được cấu hình Brave Tracing**. Advisory liệt kê các nhánh ảnh hưởng:
- Reactor Netty **1.3.0 đến 1.3.6**.
- Reactor Netty **1.1.0 đến 1.2.18**.
- Reactor Netty **1.0.52 trở xuống**.

Advisory chỉ ra bản sửa **1.3.7 (OSS)**. Một số bản sửa khác được liệt kê dành riêng cho Enterprise Support; không suy ra mọi phiên bản ghi trong danh sách đều có ở kho OSS công khai.

Giả sử resolved dependency graph của một dịch vụ WebFlux chứa reactor-netty-http 1.3.6. Cần kiểm tra:
1. Có thực sự chạy Reactor Netty HTTP Server không, hay module chỉ được kéo vào cho mục đích khác?
2. Có sử dụng Brave Tracing theo điều kiện advisory không? Kiểm tra dependency tracing bridge, bean/config hiệu lực và trạng thái production.
3. Artifact deploy đang có đúng phiên bản này không? Tìm trong dependency tree và SBOM.
4. Nếu phiên bản và điều kiện tác động trùng, nâng lên bản sửa tương thích theo BOM/nhánh đã xác nhận; kiểm thử truy cập đồng thời, xử lý exception, tracing propagation, log và latency.
5. Nếu điều kiện chưa chắc, không tự hạ cảnh báo về "an toàn"; ghi nhận "cần xác minh" và ưu tiên patch.

**Bài học:** Một CVE nêu rõ tính năng kích hoạt không có nghĩa là mọi ứng dụng có cùng JAR đều bị khai thác; nhưng scanner không thể thay con người kiểm tra runtime. Đồng thời, một package không được thấy trong pom.xml vẫn có thể được starter kéo vào gián tiếp.

Ví dụ khác: [CVE-2026-47842](https://spring.io/security/cve-2026-47842/) ảnh hưởng cách dùng cụ thể của AesBytesEncryptor trong Spring Security; advisory cảnh báo một số trường hợp nâng cấp API mã hóa còn cần **migration dữ liệu đã mã hóa**, vì bản sửa không nhất thiết có khả năng đọc dữ liệu cũ bằng cấu hình cũ. Vì vậy không quy mọi vấn đề bảo mật thành "nâng dependency rồi khởi động lại".

## 8. Quét SCA tự động cho Maven

[OWASP Dependency-Check](https://owasp.org/projects/Dependency-Check) phân tích dependency đã biết để tìm lỗ hổng công bố. Ví dụ cấu hình **thêm vào build/plugins** trong pom.xml Maven (plugin phiên bản 13.0.0 là phiên bản tài liệu chính thức được tra cứu vào 07/11/2026):

~~~xml
<plugin>
    <groupId>org.owasp</groupId>
    <artifactId>dependency-check-maven</artifactId>
    <version>13.0.0</version>
    <configuration>
        <failBuildOnCVSS>7.0</failBuildOnCVSS>
        <failOnError>true</failOnError>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Chạy:

~~~bash
./mvnw verify
~~~

Goal check được gắn vào verify; báo cáo thường nằm trong target/dependency-check-report.html theo cấu hình mặc định. Ngưỡng 7.0 trong ví dụ có nghĩa build bị chặn nếu phát hiện vulnerability có điểm CVSS đạt ngưỡng, nhưng **ngưỡng này là chính sách minh họa**, cần điều chỉnh theo mức độ rủi ro và quy trình triage của dự án. Lưu ý plugin mặc định có failBuildOnCVSS=11, tức chỉ quét mà không chặn vì CVSS có thang 0–10; muốn gate phải thiết lập rõ.

Phân tích yêu cầu dữ liệu lỗ hổng mới. Lần đầu cập nhật NVD có thể lâu; trong CI cần chuẩn bị cache/mirror hoặc API key phù hợp, quản lý key qua secrets và tránh in ra log. Lỗi tải dữ liệu không được biến thành báo cáo "không có CVE". Tùy cấu hình, failOnError=true cho phép fail-closed khi scanner không chạy được.

**Đọc báo cáo:** Đối chiếu artifact/CPE/PURL, phiên bản thật, căn nguyên dependency transitive, advisory upstream và trạng thái fix. Tool có thể match nhầm CPE, thiếu advisory mới hoặc báo CVE nhưng ứng dụng không đáp ứng điều kiện exploit; kết quả scan là tín hiệu điều tra, không phải kết luận cuối.

## 9. Quét SCA tự động cho Gradle

Ví dụ dùng **Groovy DSL build.gradle**, thêm plugin vào block plugins hiện có và cấu hình task (phiên bản plugin OWASP Dependency-Check 13.0.0 được xác nhận từ tài liệu/plugin portal thời điểm bài viết):

~~~groovy
plugins {
    id 'org.owasp.dependencycheck' version '13.0.0'
}

dependencyCheck {
    failBuildOnCVSS = 7.0
    failOnError = true
}
~~~

Nếu build.gradle đã có block plugins, gộp dòng plugin vào block đó; không tạo hai block thiếu kiểm soát. Chạy:

~~~bash
./gradlew dependencyCheckAnalyze
~~~

Báo cáo được sinh trong build/reports theo cấu hình mặc định; đối với multi-project build cần xem xét dependencyCheckAggregate để bao quát đúng các subprojects. Kiểm tra plugin version thích hợp với Gradle/JDK thực tế trước khi tích hợp. Không để task quét chỉ chạy thủ công và bị bỏ qua ở nhánh release.

Maven và Gradle đều có thể dùng nhiều scanner, ví dụ OSV-Scanner hoặc công cụ quản lý dependency của nền tảng CI. Mỗi scanner có nguồn và quy tắc tương quan riêng: tổng hợp kết quả và xác minh upstream advisory, không cộng số CVE trùng thành các sự cố khác nhau.

## 10. SBOM: ghi lại thành phần của build để tra cứu theo thời gian

SBOM (Software Bill of Materials) là danh sách component và quan hệ dependency gắn với một artifact. Với ứng dụng reactive, SBOM giúp trả lời nhanh "dịch vụ nào đã phát hành reactor-netty-http 1.3.6?" khi một advisory mới được công bố.

**Maven: sinh CycloneDX SBOM** (lệnh minh họa cho dự án có Maven Wrapper; bản 2.9.3 đã có trên Maven Central):

~~~bash
./mvnw org.cyclonedx:cyclonedx-maven-plugin:2.9.3:makeAggregateBom
~~~

**Gradle: thêm CycloneDX plugin 3.5.1 vào block plugins của dự án Gradle phù hợp**:

~~~groovy
plugins {
    id 'org.cyclonedx.bom' version '3.5.1'
}
~~~

~~~bash
./gradlew cyclonedxBom
~~~

Đối với CycloneDX Gradle 3.x, cyclonedxBom tạo SBOM tổng hợp cho các subprojects tham gia; tùy yêu cầu phát hành, direct SBOM của đúng module deploy có thể chính xác hơn aggregate SBOM toàn repository. Không tự coi một SBOM tổng hợp lớn là thành phần của mỗi JAR. Xác thực nội dung bằng việc kiểm tra có đủ module Spring Security, Spring WebFlux, Reactor Netty và Netty runtime trước khi lưu.

**Thông tin nên gắn cùng SBOM:** tên service, version ứng dụng, commit SHA, build ID, dependency lock, thời điểm build, artifact/image digest và môi trường phát hành. Lưu file SBOM cùng artifact trong kho có quyền truy cập phù hợp. SBOM phản ánh thành phần tại thời điểm tạo; nó không thay việc quét lại khi có advisory mới. SBOM cũng không tự chứng minh artifact được build từ nguồn an toàn hoặc có provenance đã ký.

## 11. Khóa phiên bản và xác minh dependency để chống drift

Hai vấn đề khác nhau cần giải:
- **Reproducibility:** build hôm nay và ngày mai giải quyết cùng một tập artifact đã duyệt.
- **Integrity/provenance:** artifact được tải về đúng nội dung mong đợi, không bị thay thế hoặc kéo từ nguồn không đáng tin.

Với Gradle có thể kích hoạt dependency locking:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Tạo hoặc cập nhật lockfile có chủ đích:

~~~bash
./gradlew dependencies --write-locks
~~~

Commit gradle.lockfile sau khi review thay đổi; khi bản vá được duyệt, cập nhật lock trong cùng PR và kiểm tra diff. Lockfile giúp ngăn dependency bắc cầu tự đổi âm thầm, **nhưng đồng thời khóa cả phiên bản lỗi** nếu không có lịch cập nhật. Kiểm tra lock cho buildscript/plugin nếu chúng là phần quan trọng của quy trình build.

Bên cạnh locking, bật [Gradle Dependency Verification](https://docs.gradle.org/current/userguide/securing_dependencies.html) khi phù hợp để xác minh checksum/chữ ký thư viện; cấu hình nằm ở gradle/verification-metadata.xml. Kiểm tra nguồn artifact repository, hạn chế snapshot/dynamic version không kiểm soát, pin plugin và tránh repository không đáng tin. Với Maven, dựa vào dependencyManagement/BOM, version cố định, Maven Wrapper, chính sách repository và kiểm soát build được tái lập. Khóa số phiên bản và xác minh checksum là hai lớp độc lập; không cái nào tự sửa CVE.

## 12. Quy trình vá dependency theo từng phiên bản

### Bước 1 — Nhận cảnh báo và xác định phạm vi

Nhận advisory qua Spring RSS, công cụ SCA, Dependabot/Renovate hoặc hệ thống quản lý vulnerability. Định danh ảnh hưởng bằng artifact, resolved version, sản phẩm chạy, cấu hình và exposure. Kiểm tra các image đang chạy và các version release cũ còn phục vụ traffic, không chỉ HEAD của main.

### Bước 2 — Ưu tiên theo rủi ro thực

Xem xét CVSS, CISA KEV, mã khai thác công khai, khả năng remote exploitation, có xác thực hay không, dữ liệu/tài nguyên liên quan và mức phơi ra Internet. Sự cố auth bypass/RCE trên public endpoint thường cần xử lý cấp bách. Không biến CVSS thành thứ tự duy nhất; một lỗi mức vừa nhưng chắc chắn reachable có thể cần ưu tiên hơn một lỗi cao không có điều kiện khai thác.

### Bước 3 — Chọn đường nâng cấp

Ưu tiên bản Boot/Security/Reactor đã sửa và còn hỗ trợ. Với nhánh không còn OSS patch, đánh giá upgrade lên nhánh được hỗ trợ hoặc chính sách hỗ trợ thương mại thực sự đang có; **không lấy phiên bản Enterprise-only rồi giả định có thể tải về**. Đọc release notes, migration guide và changelog, đặc biệt khi bản vá thay đổi cryptography, session handling, proxy headers hoặc ủy quyền.

### Bước 4 — Thay đổi có thể review

Tạo PR nhỏ: cập nhật BOM/parent/plugin version và lockfile, loại override lỗi thời, ghi advisory link. Bật kiểm thử tự động; tránh nâng một đợt hàng trăm dependency không liên quan nếu một cập nhật nhỏ hơn đã giải quyết được vấn đề. Nếu bắt buộc nâng lớn, chia theo nhóm đã có regression tests và rollback plan.

### Bước 5 — Kiểm chứng bản build và runtime

Sau build, chạy dependency:tree/dependencyInsight và quét lại SCA, so SBOM cũ/mới, xác minh artifact digest. Deploy vào môi trường thử với cấu hình sát production; test auth flows, WebClient, tracing và HTTP server. Đừng coi build PASS là bằng chứng CVE đã hết khi version vẫn bị kéo ngược bởi constraint hoặc image deploy chưa đổi.

### Bước 6 — Phát hành và theo dõi

Rollout theo đợt/canary khi phù hợp, quan sát 401/403, 5xx, token validation failures, session issues, throughput, latency và memory. Chuẩn bị rollback ở cấp artifact, nhưng không quay trở lại bản có lỗ hổng đang bị khai thác nếu có biện pháp an toàn hơn. Lưu bằng chứng và đóng cảnh báo theo đúng artifact đã thực sự deploy.

## 13. Kiểm thử hồi quy riêng cho Spring Security WebFlux

Nâng cấp Spring Security, Spring Framework, Reactor Netty hoặc thư viện OAuth2/JWT có thể thay đổi behavior ở lớp reactive ngay cả khi service vẫn build thành công.

| Kịch bản | Điều phải xác minh |
| --- | --- |
| Request không xác thực | Endpoint bảo vệ trả 401; endpoint công khai vẫn hoạt động. |
| Token ký sai, hết hạn, sai issuer/audience | Resource Server từ chối theo cấu hình thực tế; không chấp nhận token đã bị sửa. |
| Có xác thực nhưng thiếu quyền | Endpoint trả 403 hoặc hành vi đã thiết kế; không bypass rule của SecurityWebFilterChain. |
| CSRF, CORS, session/cookie | Quy tắc hoạt động theo kiểu xác thực browser hay token; không vô tình mở rộng origin. |
| Reactive context propagation | SecurityContext không mất/không rò sang request khác khi đổi scheduler và concurrency. |
| WebClient/downstream | TLS, timeout, retry, OAuth2 client credential và HTTP status mapping không thay đổi ngoài dự kiến. |
| HTTP/2, Netty và tracing | Kiểm tra khi dùng thật, đặc biệt nếu advisory yêu cầu Brave/OTel tracing hoặc protocol cụ thể. |
| Observability | Log/trace không lộ token, cookie hay dữ liệu cá nhân khi exceptions, retry và timeout. |

Dùng WebTestClient với test application context/Spring Security test utilities ở phiên bản phù hợp; kiểm tra request thực qua filter chain. Không viết test chỉ assert class có thể load: điều đó không xác nhận lỗ hổng đã bị sửa. Với lỗi có mô tả khai thác cụ thể, dựng trường hợp test âm tính an toàn trong môi trường cô lập; tránh thử khai thác production.

## 14. Thiết kế quality gate trong CI/CD

Một pipeline hữu ích gồm các kiểm tra có kết quả kiểm toán được:

~~~text
Pull request
  -> Resolve dependency graph + verify lock/checksum
  -> Unit/integration tests (SecurityWebFilterChain, OAuth2/JWT, WebClient)
  -> SCA scan (OWASP Dependency-Check / OSV / nền tảng tổ chức)
  -> Triage: phiên bản + điều kiện + bản sửa + rủi ro
  -> Build artifact, phát hành SBOM và digest
  -> Deploy thử nghiệm + smoke/regression tests
  -> Approve/rollout + lưu bằng chứng artifact đang chạy
  -> Quét lại SBOM/artifact khi xuất hiện advisory mới
~~~

Gợi ý chính sách:
- **Gate rõ ràng:** Chặn lỗ hổng chưa có chấp thuận ở ngưỡng rủi ro đã xác định, hoặc có evidence khai thác tích cực; chặn nếu scanner không cập nhật được dữ liệu theo yêu cầu.
- **Không lạm dụng suppression:** Nếu false positive hoặc không affected, suppression phải gắn CVE/artifact/version, ghi lý do/bằng chứng, người duyệt và hạn rà soát. Không suppress trọn nhóm org.springframework hoặc Netty để làm đẹp báo cáo.
- **Dữ liệu dùng để quyết định phải mới:** NVD/OSV/advisory có thể cập nhật sau khi artifact phát hành. Lập lịch quét định kỳ các bản đang chạy và nhận cảnh báo mới.
- **Bảo vệ pipeline:** Credentials cho repo/NVD scanner lấy từ secret store, phân quyền tối thiểu; không in token vào log, không tin artifact từ repository không được duyệt, không tắt failOnError để vượt cửa release.
- **Tách false positive và không reachable:** False positive là match sai artifact/version; không reachable là advisory thực sự nói tới component nhưng điều kiện khai thác có bằng chứng không tồn tại. Hai quyết định cần evidence khác nhau.

## 15. Các lỗi phổ biến cần tránh

1. Chỉ nhìn version Spring Boot trong pom.xml mà không kiểm tra resolved Spring Security và Reactor Netty.
2. Chỉ kiểm tra direct dependencies; bỏ transitive do starter hoặc thư viện khác kéo vào.
3. Cập nhật một JAR Spring Security riêng lẻ, gây lệch phiên bản với các module config/web/oauth2 hoặc Framework.
4. Nhìn CVE cùng tên package rồi kết luận "bị khai thác" mà không đọc affected range, điều kiện và stack Servlet/Reactive.
5. Dùng string comparison để so version; bỏ sót bản 1.3.10 lớn hơn 1.3.7.
6. Coi mọi bản sửa có trong advisory là bản OSS, bỏ qua nhãn Enterprise Support Only và EOL.
7. Chỉ sửa build.gradle/pom.xml nhưng không cập nhật Gradle lock, container image, deployment manifest hoặc bản đang phục vụ traffic.
8. Coi SCA report xanh là đủ dù dữ liệu NVD quá cũ, scanner lỗi hoặc dependency thực tế không được scan.
9. Tắt toàn bộ rules vì cảnh báo khó xử lý; không lưu owner, bằng chứng và hạn xem lại cho exception.
10. Nâng cấp bảo mật mà không test 401/403, JWT validation, reactive context, tracing, WebClient và HTTP server.
11. Phát hành SBOM aggregate sai phạm vi, khiến khó biết JAR/service cụ thể nào chứa bản lỗi.
12. Không theo dõi các bản deploy cũ; code main đã vá nhưng traffic vẫn chạy trên image dễ bị khai thác.

## 16. Checklist thực hành cho một đợt phát hành

- [ ] Đã biết commit, build ID, artifact/image digest và resolved runtime dependency graph.
- [ ] Đã rà Spring Security, Spring Framework, Spring WebFlux, Reactor Core/Netty, Netty, OAuth2/JWT cùng transitive.
- [ ] Đã kiểm tra nhánh Spring Boot/Security còn được hỗ trợ và thông báo chính thức theo phiên bản.
- [ ] Mỗi CVE có phân tích affected range, điều kiện runtime, fix branch và evidence.
- [ ] Bản vá tương thích với BOM/stack; override, nếu có, được lý giải và kiểm thử.
- [ ] Build, integration security tests, SCA scan và smoke test qua môi trường thử đều đạt.
- [ ] SBOM và lockfile khớp artifact dự định deploy; báo cáo scanner dùng dữ liệu vulnerability mới.
- [ ] Không có suppression rộng; ngoại lệ có lý do, chủ sở hữu, thời hạn và kế hoạch xử lý.
- [ ] Rollout có giám sát, rollback/mitigation được đánh giá cho rủi ro bảo mật.
- [ ] Theo dõi advisories mới liên tục cho cả các artifact đã phát hành.

## 17. Tài liệu tra cứu chính thức

- [Spring Security Advisories](https://spring.io/security/) — danh sách thông báo và bản sửa theo nhánh.
- [CVE-2026-47844 Reactor Netty](https://spring.io/security/cve-2026-47844/) — ví dụ phiên bản và điều kiện Brave Tracing, công bố 20/08/2026.
- [CVE-2026-47842 Spring Security](https://spring.io/security/cve-2026-47842/) — ví dụ việc vá có thể kéo theo migration API/dữ liệu mã hóa.
- [Spring Security — Getting Spring Security](https://docs.spring.io/spring-security/reference/getting-spring-security.html) — versioning và dependency.
- [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html) — BOM, Gradle platform/dependency-management.
- [Spring Boot — Supported Versions](https://github.com/spring-projects/spring-boot/wiki/Supported-Versions) — chính sách hỗ trợ và nguyên tắc nâng phiên bản.
- [OWASP Dependency-Check Maven](https://dependency-check.github.io/DependencyCheck/dependency-check-maven/) và [Gradle](https://dependency-check.github.io/DependencyCheck/dependency-check-gradle/) — lệnh, cấu hình và báo cáo.
- [CycloneDX Maven plugin](https://github.com/CycloneDX/cyclonedx-maven-plugin) và [Gradle plugin](https://github.com/CycloneDX/cyclonedx-gradle-plugin) — phát hành SBOM.
- [Gradle Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html) và [Dependency Verification](https://docs.gradle.org/current/userguide/securing_dependencies.html).

**Lưu ý thời điểm:** Các con số phiên bản cụ thể trong ví dụ/advisory và plugin đã được đối chiếu theo tài liệu được công bố tới ngày **07/11/2026**. Trước mỗi lần release, tra lại trang upstream và xác nhận artifact được tải về thực tế; phiên bản mới, danh sách nhánh hỗ trợ và thông báo lỗ hổng có thể thay đổi.

**Ghi nhớ:** Gia cố phụ thuộc không dừng ở thao tác tăng version. Một đợt vá có căn cứ phải chứng minh **đúng package, đúng phiên bản, đúng nhánh hỗ trợ, đúng điều kiện ảnh hưởng, đúng artifact triển khai** và có kiểm thử bảo đảm các luồng bảo mật reactive tiếp tục hoạt động.
