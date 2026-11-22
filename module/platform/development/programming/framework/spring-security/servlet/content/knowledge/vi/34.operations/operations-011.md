# Rà soát dependency, bản vá và cấu hình trước khi phát hành — Spring Security Servlet

## 1. Vì sao một bản build thành công chưa đủ an toàn?

Một ứng dụng Spring Boot sử dụng Spring Security để bảo vệ API, form đăng nhập hoặc OAuth2 Login. Các kiểm thử nghiệp vụ đều xanh, file JAR đã được build thành công. Nhưng trước khi phát hành vẫn có thể tồn tại nhiều rủi ro:

- **Dependency trực tiếp hoặc bắc cầu (transitive)** có lỗ hổng đã được công bố; thư viện được khai báo “đúng phiên bản” trong POM nhưng runtime lại dùng bản khác vì dependency mediation hoặc override.
- **Spring Security và Spring Framework không đồng bộ** vì một dependency được nâng riêng trong khi Spring Boot BOM vẫn quản lý các module còn lại.
- **JDK, embedded Tomcat/Jetty, base image, proxy** hoặc thư viện native chưa được cập nhật, dù mã Java ứng dụng không đổi.
- **Cấu hình production khác test**: URL nhạy cảm bị `permitAll()`, CSRF bị vô hiệu hóa toàn cục, CORS quá rộng, session cookie chưa có flag cần thiết, reverse proxy không được đặt đúng trust boundary.
- **Secret bị đưa vào cấu hình/build/log**, tài khoản demo hoặc actuator endpoint vô tình được expose ra Internet.
- **Đã có bản vá nhưng chưa kiểm khả năng tương thích**; vội đổi phiên bản làm login/session/CSRF hoạt động khác hoặc không còn đúng policy.
- **Không có rollback hoặc bằng chứng phát hành**, nên khi sự cố xảy ra không biết bản đang chạy gồm những dependency/config nào.

Do đó, “rà soát trước phát hành” là một **security release gate** có bằng chứng, không chỉ việc chạy `mvn package`.

Mục tiêu của bài: xây quy trình thực hành để **kiểm kê dependency → đánh giá lỗ hổng → lựa chọn và kiểm thử bản vá → xác minh cấu hình Spring Security Servlet → đóng băng artifact/cấu hình → triển khai có kiểm soát**, kèm ví dụ Java 17, Maven, Spring Boot 3 và MockMvc.

**Giới hạn thông tin phiên bản:** POM mẫu bên dưới cố định **Spring Boot 3.3.5** để minh họa cấu hình có thể tái lập tại một thời điểm. Nó **không** hàm ý 3.3.5 hoặc bất kỳ dependency nào trong bài là phiên bản mới nhất hay còn được bảo trì tại thời điểm người đọc phát hành. Trước mỗi release cần kiểm thông báo bảo mật và trạng thái hỗ trợ **hiện tại** của vendor/upstream, lựa chọn bản vá được tổ chức phê duyệt. Không suy diễn CVE “đang tồn tại” từ ví dụ lịch sử.

## 2. Phạm vi kiểm kê: nhiều lớp hơn pom.xml

Một ứng dụng Servlet có nhiều tầng:

~~~text
                         Source repository
                                  |
                                  v
                  pom.xml / dependencyManagement
                                  |
                 +----------------+----------------+
                 |                                 |
          Direct dependencies                Transitive dependencies
                 |                                 |
                 +----------------+----------------+
                                  |
                                  v
                    Spring Boot application JAR
                     Spring Security / Framework
                     Jackson / logging / embedded
                     Servlet container libraries
                                  |
                                  v
                       JDK + OS/base image
                                  |
                                  v
                Ingress / reverse proxy / TLS / WAF
                                  |
                                  v
                  Identity provider / DB / secrets
                                  |
                                  v
                      Production runtime config
~~~

Bản rà soát phải phân biệt:

| Lớp | Cần kiểm | Bằng chứng nên lưu |
| --- | --- | --- |
| Source/commit | Nhánh, commit, thay đổi security config và source của dependency | Commit SHA, review approval, changelog |
| Maven dependencies | Direct + transitive + scopes runtime/test, version được giải quyết cuối cùng | Dependency tree, effective POM |
| Maven build plugins | Plugin version, plugin dependencies, nguồn tải, hành vi build | POM, plugin report, CI configuration |
| Spring Boot/Security | Boot BOM, Spring Framework, Spring Security, Spring MVC, embedded servlet container | BOM/resolved coordinates, compatibility tests |
| Java runtime | JDK vendor, phiên bản, security update, JVM flags | `java -version`, image/host metadata |
| Image/OS | Base image digest, OS packages, native libraries | Image SBOM, scanner report, digest |
| Infrastructure | TLS/proxy/CDN, network policy, cookies, trusted headers | Deployment manifests, config diff |
| Secrets/IdP | Secret source, rotation, OAuth/LDAP/JWT trust config | Secret inventory *không chứa giá trị*, approval |
| Live application | SecurityFilterChain, endpoints, headers, logging, environment profiles | Test report, smoke test, deployment record |

**Đừng bỏ qua transitive dependencies:** ứng dụng chỉ khai báo `spring-boot-starter-web` nhưng starter kéo theo nhiều thư viện, trong đó có embedded servlet container. SCA chỉ quét các dòng dependency trực tiếp sẽ bỏ sót phần đáng kể attack surface.

**Đừng chỉ quét JAR:** container image/OS, binary tools và thư viện JS phía frontend cũng có vulnerability lifecycle riêng. Công cụ quét Java SCA không thay thế image scanner hoặc secret scanner.

## 3. Spring Boot BOM: nâng phiên bản có chủ đích, không tùy tiện ghép

Với Maven, parent `spring-boot-starter-parent` cung cấp quản lý phiên bản tương thích cho nhiều dependencies, trong đó có các thành phần Spring. Dùng starter thường **không cần** chỉ định phiên bản riêng cho từng thư viện được BOM quản lý.

Ví dụ đúng về nguyên tắc:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
</dependencies>
~~~

Đây là **mảnh POM**. Một file POM hoàn chỉnh để kiểm thử có ở mục 8.

Cần làm rõ bốn trường hợp nâng cấp:

1. **Nâng Spring Boot sang bản phát hành được hỗ trợ, đã kiểm chứng compatibility**: thường giúp đồng bộ nhiều thư viện được quản lý và chứa các sửa lỗi liên quan. Đọc release notes và migration notes trước.
2. **Override một dependency được BOM quản lý** để nhận bản vá khẩn cấp: chỉ sau khi biết phạm vi ảnh hưởng, tương thích ABI/API và được chấp thuận. Ghi rõ lý do, issue/CVE liên quan, ngày hết hạn của override và kế hoạch xóa override khi BOM cập nhật.
3. **Nâng thư viện không do BOM quản lý**: vẫn cần pin version, kiểm test, license và transitive dependencies.
4. **Nâng build plugin, JDK hoặc servlet container riêng**: có thể thay đổi output/build behavior/runtime; phải được kiểm đúng layer chứ không trông chờ chỉ tăng Spring Security version.

Ví dụ anti-pattern:

~~~xml
<!-- Ví dụ KHÔNG nên áp dụng mù quáng -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
    <version>6.3.0</version>
</dependency>
~~~

Nếu phần khác của cùng ứng dụng vẫn dùng một dòng Spring Security khác do BOM quản lý, có nguy cơ xung đột hoặc hành vi khó đoán. Không kết luận riêng con số `6.3.0` có/không có lỗ hổng; vấn đề ví dụ là **override lẻ không có bằng chứng tương thích**.

Khi buộc phải override, hãy đọc **effective POM** và **resolved dependency graph** để bảo đảm các module thực tế nhất quán, chạy regression tests về filter chain, login, session, authorization, method security và ứng xử lỗi. Trong hệ thống nhiều module Maven, kiểm cả parent, dependencyManagement, exclusions, test/runtime scope và plugin riêng.

## 4. Lấy bằng chứng dependency thực tế bằng Maven

Trong thư mục có `pom.xml` và Maven/JDK được cài đặt:

~~~bash
# Ghi rõ JDK runtime/build dùng tại môi trường kiểm thử.
java -version
mvn -version

# Clean + chạy unit/integration tests và các verify goals đã cấu hình.
mvn -B -ntp clean verify

# Đọc cây dependency đã được Maven resolve.
mvn -B -ntp dependency:tree

# Lưu bằng chứng tree vào thư mục artifact của build.
mvn -B -ntp dependency:tree -DoutputFile=target/dependency-tree.txt

# Xem effective POM sau inheritance, profiles, dependencyManagement.
mvn -B -ntp help:effective-pom -Doutput=target/effective-pom.xml

# Gợi ý dependency khai báo dư hoặc thiếu do phân tích usage.
mvn -B -ntp dependency:analyze
~~~

**Đọc đúng ý nghĩa từng lệnh:**

- `dependency:tree` biểu thị graph Maven resolve, gồm direct/transitive. Đây là bước thiết yếu để điều tra phiên bản cuối cùng chứ không chỉ nhìn bản POM khai báo.
- `help:effective-pom` cho thấy cấu hình sau inheritance/profiles, giúp phát hiện dependency override hoặc repository/plugin config bất ngờ.
- `dependency:analyze` tập trung khai báo/tham chiếu, có thể có false positives khi dùng reflection, annotation processing, framework injection; **không phải vulnerability scanner**.
- `clean verify` chạy các lifecycle phases và test đã gắn; nếu dự án vô tình đặt `skipTests`/profile sai, lệnh này không tự tạo test còn thiếu. Xem test report và các bước CI thật sự chạy.
- Với nhiều module, chạy tại root reactor và kiểm artifact từng module. Với profile production, so sánh resolved graph dưới profile đó; `mvn dependency:tree` cho một profile khác không bảo đảm production classpath trùng khớp.

Cần lưu **tọa độ dependency** (`groupId:artifactId:version:scope`) và bản JDK dùng build/release. Đừng xem một warning màu đỏ từ tool là sự thật tuyệt đối; kiểm thêm dependency được dùng ở code path nào, có thể bị loại khỏi runtime, có bản vá upstream hay chưa.

**Reproducibility:** pin plugin/build tool versions, cố định nguồn repository theo chính sách, hạn chế `LATEST`, `RELEASE`, snapshot và version ranges không kiểm soát. Với image, ưu tiên pin **digest** thay vì chỉ tag dễ đổi. Artifact đã build/scan nên được **promote nguyên vẹn** qua staging → production, không build lại ở production với phiên bản phụ thuộc khác.

## 5. SBOM: danh sách thành phần để điều tra sau này

**Software Bill of Materials (SBOM)** là tài liệu máy đọc được mô tả thành phần của artifact, thường theo CycloneDX hoặc SPDX. Nó giúp trả lời câu hỏi “Bản deploy tối hôm qua có chứa thư viện X phiên bản Y không?” mà không phải đoán lại từ branch hiện tại.

Một quy trình hợp lý:

~~~text
Build clean from approved commit
        |
        +--> resolved dependency tree
        +--> Maven SBOM (direct/transitive components)
        +--> image/OS SBOM nếu đóng gói container
        +--> test + vulnerability/license scan
        +--> artifact SHA-256 + provenance
        |
        v
Archive cùng release ID và deploy chính artifact đó
~~~

Nếu nhóm dùng **CycloneDX Maven plugin**, cần pin phiên bản plugin trong `pom.xml` hoặc quản lý plugin tập trung, tạo SBOM trong CI và lưu artifact sinh ra. Ví dụ command **sau khi plugin đã được khai báo và pin trong build**:

~~~bash
mvn -B -ntp cyclonedx:makeBom
~~~

Phần cấu hình plugin phải được đội build cung cấp theo phiên bản hiện đang được hỗ trợ và chính sách nội bộ; ví dụ học tập bên dưới **không buộc thêm plugin bảo mật không được kiểm phiên bản**. Khi có nhiều Maven modules, kiểm chọn goal phù hợp (chẳng hạn BOM tổng hợp) để không bỏ thành phần của module khác.

SBOM không tự kết luận một dependency có lỗ hổng **có thể khai thác trong ứng dụng**. Nó là dữ liệu đầu vào cho SCA, inventory, incident response và quản trị license. File SBOM có thể chứa thông tin nội bộ về cấu trúc hệ thống; lưu/chi sẻ theo quyền phù hợp.

Kiểm chất lượng SBOM: chứa cả direct/transitive, version thực đã resolve, Java runtime/image layer nếu có, format được parser chấp nhận, liên kết được đúng checksum của artifact. Nếu SBOM tạo cho `main` nhưng production deploy một JAR khác thì bằng chứng không đủ.

## 6. SCA, CVE, advisory và quyết định vá

**Software Composition Analysis (SCA)** so sánh inventory với các nguồn cảnh báo lỗ hổng, thường xuất kết quả theo package version và CVE/GHSA/advisory tương ứng. Nguồn đánh giá gồm:

- Thông báo bảo mật và release notes **chính thức** của Spring, thư viện liên quan, JDK, servlet container, OS/base image.
- Cơ sở dữ liệu và advisory có nguồn gốc rõ: CVE/NVD, GitHub Security Advisories, OSV, danh mục lỗ hổng đã bị khai thác của cơ quan có thẩm quyền, nếu áp dụng.
- Bộ SCA/container scanner của tổ chức đã cập nhật dữ liệu, ghi thời điểm và phiên bản scanner.
- Kết quả kiểm thử thực tế ở code path đang chạy, cấu hình có/không bật tính năng dễ bị tấn công, và khả năng có mitigation.

**Không có một điểm CVSS duy nhất quyết định hoàn toàn mức ưu tiên.** Cần đánh giá thêm exploitability, có bằng chứng đang bị khai thác hay không, Internet exposure, quyền trước khi khai thác, ảnh hưởng dữ liệu, phiên bản bị tác động thực tế và tính sẵn có của bản vá.

Một **bản ghi triage** hữu ích:

| Thuộc tính | Nội dung |
| --- | --- |
| Component | `group:artifact:resolvedVersion` hoặc OS package |
| Advisory | ID và đường dẫn nguồn chính thức |
| Exposure | Runtime? build/test-only? endpoint/capability đang dùng? |
| Impact | RCE, SSRF, auth bypass, information leak, DoS... theo advisory |
| Exploitability | Có public exploit/in-the-wild evidence? đường vào đã mở? |
| Fix | Phiên bản đã vá được vendor xác nhận, tương thích BOM? |
| Workaround | Feature flag, chặn endpoint/network, cấu hình giảm rủi ro |
| Owner/deadline | Người xử lý và SLA theo mức rủi ro |
| Exception | Lý do có bằng chứng, approver, thời hạn hết hiệu lực |
| Evidence | Dependency tree, scan date, regression tests, deployment ID |

**Ví dụ giả định**: một scanner phát hiện lỗ hổng trong parser X phiên bản Y, kéo vào qua thư viện Z. Không được lập tức kết luận sản phẩm dễ bị RCE chỉ từ một dòng scan; cần xác định parser có nằm trong runtime artifact, nhận dữ liệu không tin cậy và có đi qua code path chịu ảnh hưởng không. Nhưng cũng **không được tự đánh dấu false positive** chỉ vì nhóm chưa thấy exploit. Ghi kết luận dựa vào advisory và thử nghiệm.

Khi bản vá chưa thể triển khai ngay: áp dụng mitigation có kiểm chứng, tăng logging/monitoring có kiểm soát, giới hạn exposure và ghi **exception có ngày hết hạn**. “Đã chấp nhận rủi ro” không phải miễn rà soát mãi mãi. Với lỗ hổng nghiêm trọng và đang bị khai thác, có thể cần **chặn phát hành hoặc tắt tính năng** thay vì tiếp tục ship theo lịch.

**Scanner freshness:** kết quả clean hôm qua không chứng minh không có advisory mới hôm nay. Release gate cần ghi timestamp của database SCA và lịch scan lại artifact đang chạy, nhất là ứng dụng tồn tại lâu giữa các release.

## 7. Quy trình áp dụng bản vá không phá security behavior

Khi xác định một dependency cần vá, triển khai theo nhịp:

~~~text
Advisory / scanner finding
       |
       v
Verify affected coordinate and reachability
       |
       v
Choose vendor-supported fixed version / compatible BOM
       |
       v
Create isolated change; no broad unrelated upgrades
       |
       v
Resolve dependency graph + scan again
       |
       v
Compile + unit + integration + security regression
       |
       v
Build immutable artifact; verify checksum / SBOM
       |
       v
Staging/canary and rollback rehearsal
       |
       v
Production promotion + monitor + re-scan
~~~

**Thay đổi nhỏ, kiểm chứng rõ** thường dễ review và rollback hơn một đợt nâng toàn bộ plugin/JDK/Spring dependencies đồng thời. Tuy nhiên đôi khi vendor yêu cầu nâng cả dòng Boot/Spring để hỗ trợ bản vá; khi đó phải kiểm migration notes và những breaking changes liên quan.

Ví dụ các regression đặc biệt quan trọng sau khi nâng Spring Security/Spring Framework:

- **URL matching**: `requestMatchers`, thứ tự matcher, servlet path, nhiều `SecurityFilterChain`, encoded URL/trailing slash.
- **Authentication**: login, Basic, form login, OAuth2/OIDC, logout, failure handler, session fixation protection, remember-me.
- **Authorization**: `hasRole`/`hasAuthority`, `@PreAuthorize`, role hierarchy, principal kiểu tùy biến và account status.
- **CSRF**: form POST, JSON endpoint được browser gọi, token repository, cookie-backed SPA, logout.
- **Headers/CORS**: CSP/HSTS, X-Content-Type-Options, CORS preflight/actual request, `Origin` allowlist.
- **Servlet container/session**: cookies, forwarding/error dispatch, reverse proxy/forwarded headers, session timeout/persistence.
- **Dependencies khác**: serialization/JSON, validation, logging, upload/download, TLS provider và timeouts.

Với lỗ hổng ở embedded Tomcat hoặc Jackson, không chỉ cập nhật starter-web version bằng cách sửa một dòng thiếu căn cứ. Xem phiên bản resolved của component bị ảnh hưởng, release note/vulnerability fix từ vendor và kiểm tương thích BOM.

Một bản vá có thể giải quyết CVE nhưng đổi hành vi auth hoặc session; không chấp nhận release chỉ vì SCA từ đỏ thành xanh mà thiếu **negative security tests**.

## 8. Ví dụ Java 17 + Spring Boot 3.3.5 để kiểm security release gate

Ví dụ nhỏ này minh họa cách một ứng dụng Servlet có URL policy rõ, giữ CSRF và các security headers, rồi chạy **MockMvc regression tests** trước release.

**Quan trọng:** đây là **ứng dụng luyện kiểm thử**, không phải production authentication. Nó cố tình không cấp user đăng nhập thật; tests dựng principal bằng `with(user(...))` để kiểm authorization, còn một HTTP Basic request có credential bất kỳ sẽ bị từ chối. Điều này giúp tránh hard-code tài khoản demo hoặc tin generated default password của Spring Boot như một production login flow. Trước khi deploy ứng dụng nghiệp vụ thật phải bổ sung **authentication provider đã xác minh**, test nó độc lập và triển khai cấu hình secrets phù hợp.

### 8.1. Cấu trúc

~~~text
release-security-gate-demo/
├── pom.xml
├── src/main/java/example/releasegate/ReleaseGateApplication.java
├── src/main/resources/application.properties
└── src/test/java/example/releasegate/ReleaseGateSecurityTests.java
~~~

### 8.2. POM hoàn chỉnh

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>release-security-gate-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Không khai báo phiên bản riêng cho `spring-security-web`, `spring-security-config`, Spring MVC hoặc Jackson; để parent/BOM quản lý. Nếu tổ chức yêu cầu bản vá khác, nâng/override phải được kiểm chứng và ghi nhận như mục 3–7.

### 8.3. Cấu hình tối giản

**src/main/resources/application.properties**:

~~~properties
# Không đưa secret vào file. Hạn chế chi tiết lỗi trả cho client.
server.error.include-message=never
server.error.include-stacktrace=never
~~~

Đây **không phải** checklist cấu hình production đầy đủ. Đặc biệt, cấu hình HTTPS/trust proxy/session cookie/actuator phải gắn với kiến trúc triển khai thật, tránh chép properties không phù hợp vào môi trường khác.

### 8.4. Servlet security policy và endpoint

**src/main/java/example/releasegate/ReleaseGateApplication.java**:

~~~java
package example.releasegate;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReleaseGateApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReleaseGateApplication.class, args);
    }

    @Bean
    UserDetailsService denyDefaultAccounts() {
        // Demo không có user thật. Bean này chặn việc Boot
        // tự tạo tài khoản mặc định có password được in ra log.
        // Production PHẢI thay bằng authentication provider thật.
        return username -> {
            throw new UsernameNotFoundException(
                    "No real users configured in demo");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/me")
                            .authenticated()
                        .requestMatchers(
                                HttpMethod.POST, "/api/notes")
                            .hasRole("USER")
                        .requestMatchers(
                                HttpMethod.GET, "/admin/audit")
                            .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .headers(headers -> headers
                        .contentSecurityPolicy(csp -> csp
                                .policyDirectives(
                                        "default-src 'self'; " +
                                        "object-src 'none'; " +
                                        "base-uri 'self'")))
                .build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/public/ping")
        Map<String, String> ping() {
            return Map.of("status", "ok");
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("user", authentication.getName());
        }

        @PostMapping("/api/notes")
        ResponseEntity<Map<String, String>> createNote() {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(Map.of("id", "note-1"));
        }

        @GetMapping("/admin/audit")
        Map<String, String> audit() {
            return Map.of("result", "restricted");
        }
    }
}
~~~

Giải thích từng quyết định:

- `requestMatchers(HttpMethod.GET, "/public/ping").permitAll()`: chỉ GET public; không vô tình mở toàn bộ HTTP methods tại URL.
- `GET /api/me`: yêu cầu authenticated. User không có role vẫn có thể xem dữ liệu của chính họ nếu application có logic profile đúng.
- `POST /api/notes`: yêu cầu `ROLE_USER`. CSRF vẫn bật, nên test role phải dùng token hợp lệ.
- `GET /admin/audit`: chỉ `ROLE_ADMIN`.
- `anyRequest().denyAll()`: route/method chưa khai báo bị chặn ở Security trước khi MVC xử lý. Không mặc định sẽ có 404/405.
- `httpBasic`: trong demo unauthenticated protected request thường là **401** thay vì redirect `/login`; ứng dụng sử dụng form/OIDC login có thể có entry point khác.
- `headers.contentSecurityPolicy`: thêm một CSP cơ bản theo chính sách demo. CSP phù hợp với API này không nhất thiết đủ cho SPA hoặc trang có script/style inline; production phải xây chính sách CSP theo assets thực tế, có thể dùng nonce/report-only khi triển khai.
- Không tắt CSRF. `permitAll` hoặc `authenticated` không đồng nghĩa miễn `CsrfFilter`.
- `denyDefaultAccounts` ngăn application sử dụng một login mặc định ngoài ý muốn; **mọi Basic credential gửi từ bên ngoài đều bị từ chối**. Test principal được tạo riêng ở test layer, không được coi là xác thực password thật.

**Các trường hợp chưa được demo xử lý:** multi-tenant ACL, password policy, logout, session persistence, OAuth2/OIDC integration, rate limiting, error routing, HTTP proxy, deployment secrets. Khi áp dụng production, phải thêm kiểm thử và bảo vệ phù hợp, không copy nguyên ứng dụng demo ra Internet như một authentication service.

### 8.5. Kiểm thử ma trận security bằng MockMvc

**src/test/java/example/releasegate/ReleaseGateSecurityTests.java**:

~~~java
package example.releasegate;

import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReleaseGateSecurityTests {

    @Autowired
    MockMvc mvc;

    record Scenario(
            String method, String path, String actor,
            boolean includeCsrf, int expectedStatus) {}

    static Stream<Scenario> matrix() {
        return Stream.of(
                new Scenario("GET", "/public/ping", "ANON",
                        false, 200),
                new Scenario("GET", "/public/ping", "USER",
                        false, 200),
                new Scenario("GET", "/api/me", "ANON",
                        false, 401),
                new Scenario("GET", "/api/me", "USER",
                        false, 200),
                new Scenario("GET", "/api/me", "ADMIN",
                        false, 200),
                new Scenario("POST", "/api/notes", "ANON",
                        true, 401),
                new Scenario("POST", "/api/notes", "USER",
                        true, 201),
                new Scenario("POST", "/api/notes", "ADMIN",
                        true, 403),
                new Scenario("GET", "/admin/audit", "ANON",
                        false, 401),
                new Scenario("GET", "/admin/audit", "USER",
                        false, 403),
                new Scenario("GET", "/admin/audit", "ADMIN",
                        false, 200),
                new Scenario("DELETE", "/api/notes", "ANON",
                        true, 401),
                new Scenario("DELETE", "/api/notes", "USER",
                        true, 403),
                new Scenario("DELETE", "/api/notes", "ADMIN",
                        true, 403)
        );
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("matrix")
    void endpointPolicy(Scenario s) throws Exception {
        MockHttpServletRequestBuilder builder = request(
                HttpMethod.valueOf(s.method()), s.path());

        // Để kiểm role ở unsafe method, phải cấp CSRF hợp lệ.
        if (s.includeCsrf()) {
            builder.with(csrf());
        }

        if ("USER".equals(s.actor())) {
            builder.with(user("alice").roles("USER"));
        } else if ("ADMIN".equals(s.actor())) {
            builder.with(user("admin").roles("ADMIN"));
        }

        mvc.perform(builder)
                .andExpect(status().is(s.expectedStatus()));
    }

    @Test
    void unsafeMethodMissingCsrfIsDenied() throws Exception {
        mvc.perform(post("/api/notes")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfIsDenied() throws Exception {
        mvc.perform(post("/api/notes")
                        .with(user("alice").roles("USER"))
                        .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }

    @Test
    void basicCredentialsDoNotCreateARealUserInDemo()
            throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("someone", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void responseHasRequiredHeaders() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"))
                .andExpect(header().string(
                        "Content-Security-Policy",
                        "default-src 'self'; object-src 'none'; " +
                                "base-uri 'self'"))
                .andExpect(jsonPath("$.status").value("ok"));
    }
}
~~~

Test `@SpringBootTest` + `@AutoConfigureMockMvc` sử dụng application SecurityFilterChain trong Spring Test context. `with(user(...))` cung cấp **principal đã xác thực do test tự dựng**, không kiểm password/IdP. Do đó nó phù hợp để kiểm URL policy mà không cần tài khoản sản xuất. Test `httpBasic(...)` riêng xác minh rằng ví dụ không vô tình nhận một tài khoản không có thật.

Ma trận tách **anonymous, USER, ADMIN**, các HTTP methods và CSRF. Lưu ý `ADMIN` chỉ có `ROLE_ADMIN`, không tự có `ROLE_USER`; vì vậy POST notes bị 403 trong demo. Trong ứng dụng thật, có thể định nghĩa role hierarchy nếu nghiệp vụ yêu cầu.

Các security assertions cần kiểm theo ý nghĩa:

- Với **POST có role đúng**, gắn `.with(csrf())` để kết luận 201 thật sự vượt cả CSRF và authorization.
- Với **POST thiếu CSRF**, 403 không được dùng làm bằng chứng kiểm role; test CSRF được viết riêng.
- Với **method không khai báo**, deny-all có thể chặn trước khi Spring MVC trả 405.
- Kiểm header CSP và `nosniff` xác nhận baseline headers hiện diện; **không** xác minh HSTS vì MockMvc không mô phỏng việc trình duyệt kết nối HTTPS thực tế.
- Method/URL authorization không thay thế object-level ownership/tenant checks hoặc review logic lấy dữ liệu.

Chạy từ thư mục dự án:

~~~bash
mvn -B -ntp clean verify
~~~

Kỳ vọng **trên code và dependency đã khai báo**: các ca matrix, CSRF, Basic auth và security header được chạy; build chỉ được đưa qua release gate khi tất cả test relevant đều pass. Đây là **kết quả mong đợi**, không phải log build đã chạy trên máy hiện tại. Muốn kiểm pipeline thật phải chạy lệnh trong môi trường JDK/Maven/CI có dependency access.

Nếu dùng bản vá Spring Security khác hoặc cấu hình entry point khác, cập nhật status contract có chủ đích. Không sửa test để “làm xanh” bằng cách mở `permitAll` cho endpoint đáng lẽ private.

## 9. Cấu hình Spring Security Servlet: pre-release checklist

### 9.1. Kiểm từng SecurityFilterChain

Với một ứng dụng có thể có nhiều chain:

- Liệt kê **securityMatcher**, `@Order`, phạm vi request và filter được gắn vào mỗi chain.
- Bảo đảm tất cả URL nhạy cảm thật sự khớp **một chain có bảo vệ**; không vô tình có chain catch-all `permitAll` hoặc URL không được chain nào xử lý.
- Trong `authorizeHttpRequests`, ưu tiên matcher cụ thể trước matcher rộng; kiểm method, servlet path, context path và proxy rewrite.
- Tạo **default-deny** khi có thể và explicit public allowlist: `/login`, CSS/JS public, health endpoint đã giới hạn, OAuth callback hợp lệ.
- Kiểm `web.ignoring` hoặc việc bỏ filter chain cho static resources: khi có thể, dùng `permitAll` để giữ Security headers/filter behavior. Không bao giờ expose private uploads qua static resources công khai.
- Với `@PreAuthorize` và method security: `@EnableMethodSecurity`, Spring-managed proxy, tránh self-invocation, kiểm owner/tenant/permission tại service.

Một bài test thực tế cần có user thường **không** mở được file/đơn hàng của user khác chỉ vì cả hai thuộc `ROLE_MEMBER`. URL rule chỉ bảo vệ tầng **thao tác**, object-level ACL bảo vệ từng bản ghi.

### 9.2. Authentication và account lifecycle

- Không ship `{noop}`, hard-coded passwords, generated development user hoặc endpoint bypass auth.
- Kiểm PasswordEncoder/credential rotation, account disabled/locked, rate limiting, brute-force monitoring, logout và recovery flow.
- Nếu dùng OAuth2/OIDC: issuer/discovery/JWK, audience/client ID, redirect URI, allowed scopes, state/nonce, token storage, callback CSRF/session, mapping external identity sang local role.
- Nếu dùng resource server: JWT signature/issuer/audience/expiration, opaque token introspection nếu thích hợp, authority mapping không tự nâng quyền; không nhầm login principal với bearer API auth.
- Nếu dùng LDAP: LDAPS hoặc StartTLS xác minh chứng chỉ, service account ít quyền, không gửi credential plaintext.
- Kiểm logout/session revocation, account role changes và các phiên đã được cấp quyền trước đó.

**Phân biệt authentication vs authorization:** một người đăng nhập thành công không có nghĩa được xem tất cả tenant/project/document. Đặc biệt rà soát nơi app đọc `tenantId`, `userId`, `role` do client gửi thay vì dùng identity đáng tin từ SecurityContext.

### 9.3. CSRF, CORS và browser

**CSRF:** ứng dụng xác thực bằng cookie/session có thể bị browser tự gửi credential đến request cross-site; thường cần bật CSRF cho unsafe methods. Nếu quyết định tắt CSRF ở một nhóm API thuần bearer token, phải ghi threat model và chứng minh credential không thể được tự động browser gửi dưới cơ chế hiện tại. Không dùng `csrf.disable()` làm cách sửa 403 của `MockMvc` mà bỏ kiểm tra.

**CORS:** không cấu hình `allowedOrigins("*")` kết hợp credential allowance. Chỉ cho phép origin, method và headers thực sự cần; `Vary: Origin` và cache proxy có thể quan trọng. Preflight `OPTIONS` thường không có cookie/credential; khi bật CORS, phải để CORS xử lý đúng trước authentication. `permitAll(OPTIONS)` **không** tự tạo `Access-Control-Allow-Origin` hợp lệ.

**Cookies:** `Secure`, `HttpOnly`, `SameSite`, domain/path và session timeout phải được xem xét theo kiến trúc. `SameSite` có thể ảnh hưởng OAuth login redirect/callback hoặc tương tác cross-site, nên cần thử browser thật. Cookie flags không thay thế CSRF policy nếu vẫn có bề mặt cross-site attack.

### 9.4. Security headers và TLS

- Kiểm `X-Content-Type-Options: nosniff`; `Content-Security-Policy` nếu ứng dụng render HTML; chính sách phải được thử với scripts/styles/assets thực tế.
- **HSTS** chỉ có ý nghĩa khi browser nhận trên HTTPS hợp lệ. Không khẳng định HSTS hoạt động chỉ dựa trên MockMvc HTTP request; thử bằng HTTPS sau proxy thật.
- Đảm bảo TLS termination ở proxy và outbound TLS tới IdP/LDAP/database được xác minh, không dùng trust-all hoặc bỏ hostname verification.
- Với proxy: chỉ chấp nhận `Forwarded`/`X-Forwarded-*` từ **proxy đáng tin**, có kiểm soát ingress và clear headers do client tự đặt. Cấu hình `server.forward-headers-strategy` theo kiến trúc; tin mù vào forwarded headers có thể gây sai redirect URL, Host poisoning và nhầm HTTPS.
- Kiểm `Content-Disposition` và `Cache-Control` của tệp riêng. Không đưa secrets/token/PII vào log hoặc cache/CDN public.

### 9.5. Actuator, debug và lỗi

Nếu sử dụng Spring Boot Actuator:

- Chỉ expose `health`/`info` hoặc endpoint đúng nhu cầu; các endpoint như `env`, `configprops`, `heapdump`, `loggers`, `mappings` cần quyết định truy cập riêng, thường không public.
- Phân tách management port/network khi có thể, authn/authz và ingress theo mức rủi ro.
- Cấu hình health details tối thiểu cho người không xác thực, tránh lộ tên database/host.
- Không bật Spring Security debug/trace hoặc stack traces trong production mà thiếu giới hạn thời gian và redaction.
- Không trả raw exception, JWT, password, access token, session cookie hoặc PII nhạy cảm trong HTTP error response/log.

**Lưu ý:** bật/tắt Actuator khác nhau giữa ứng dụng; demo mục 8 **không** cài starter-actuator nên không có các endpoint đó. Không dựa vào đường dẫn `/actuator/**` trong ma trận nếu thực tế app không khai báo.

## 10. Secrets và cấu hình theo môi trường

Một bộ cấu hình hợp lệ trong test **không** đủ để kết luận production giống test. Hệ thống có thể cấu hình qua YAML, environment, JVM system properties, Config Server, Kubernetes Secret/ConfigMap, Helm values và secret manager.

Điều cần kiểm:

1. **Danh sách configuration inputs**, thứ tự ưu tiên và origin. Với Spring Boot, một giá trị từ environment hoặc CLI có thể ghi đè giá trị trong `application.yml`. Đừng chỉ mở file trong Git để đoán setting production.
2. **Profile đang chạy** (`spring.profiles.active`), tệp YAML/profile liên quan, feature flags và fallback. Phân biệt `local`, `test`, `staging`, `prod` rõ ràng.
3. **Secrets**: DB password, OAuth client secret, signing key, TLS private key, API key, webhook secret đến từ nguồn được quản lý, có rotation/audit; không xuất vào build artifact.
4. **Chặn cấu hình nguy hiểm**: dummy secrets, `{noop}`, permissive auth, `csrf.disable()` không có policy, wildcard CORS + credentials, `spring.security.debug=true`, stacktrace exposure, datasource credentials demo.
5. **Không in effective config có secret ra log**. Khi cần diff, redact value và so sánh các key/policy quan trọng thay vì dump cả environment.
6. **Phân quyền config**: ai được sửa Helm values, secret manager policy, ingress headers và admission settings? Source code review thôi không phát hiện việc thay đổi cấu hình bên ngoài repository.

Ví dụ **cấu hình production minh họa, không áp dụng đại trà**:

~~~properties
# HTTPS phải được triển khai thực tế tại ingress/app.
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax

# Không trả chi tiết exception nội bộ.
server.error.include-message=never
server.error.include-stacktrace=never
~~~

Các property cookie đặc biệt cần browser test nếu app dùng form/OIDC login/cookie session. Đối với OAuth2 callback có yêu cầu cross-site đặc biệt, phải kiểm SameSite và cookie/session handling theo flow thật, không đổi `SameSite=None` tùy tiện. `SameSite=None` trong browser hiện đại thường yêu cầu `Secure`; điều đó vẫn cần HTTPS và CSRF/threat model.

**Không đưa cấu hình mẫu trên vào POM hoặc file test rồi tuyên bố production đã an toàn.** Phải xác nhận **giá trị hiệu lực tại runtime** sau deploy, qua công cụ kiểm có redaction và security approval.

## 11. CI/CD release gate: kiểm ở build, staging và runtime

Một pipeline có thể có các cổng kiểm sau:

| Cổng | Điều kiện tối thiểu | Bằng chứng cần lưu |
| --- | --- | --- |
| Source review | Thay đổi auth/security được review, không còn secret trong diff | Commit SHA, review, secret-scan report |
| Dependency resolution | Không có version range/snapshot ngoài policy, BOM hợp lý | Tree, effective POM |
| SCA + license | Findings được vá hoặc exception hợp lệ; DB scan còn mới | SCA report + owner/expiry, license report |
| SBOM | Chứa direct/transitive và liên kết đúng artifact | CycloneDX/SPDX artifact |
| Build/test | JDK đã phê duyệt, clean verify pass, không skip tests | Test reports, CI logs đã redacted |
| Security tests | URL method/role, CSRF, headers, tenant ACL, auth failure pass | JUnit/MockMvc reports |
| Image/OS scan | Không có findings vượt policy; image digest pin | Scanner report, image digest |
| Staging smoke | Login, logout, proxy TLS/cookie, public/private routes đúng | Automated smoke result |
| Approval | Risk exception/hotfix có owner, hạn dùng và approver | Ticket/change record |
| Deploy | Promote chính artifact đã scan, canary/rollback sẵn sàng | Artifact digest, rollout ID |

Ví dụ một **chuỗi lệnh CI** dành cho Maven project:

~~~bash
set -e

java -version
mvn -version

mvn -B -ntp clean verify
mvn -B -ntp dependency:tree -DoutputFile=target/dependency-tree.txt
mvn -B -ntp help:effective-pom -Doutput=target/effective-pom.xml

# Bước SCA, SBOM, license, image scan do CI của tổ chức
# cấu hình với phiên bản tool được pin và policy được phê duyệt.
# Không xóa/chặn lỗi scanner để pipeline xanh giả.
~~~

Đây là **mảnh Bash cho môi trường Linux/macOS CI**; trên Windows PowerShell cần cú pháp phù hợp. `set -e` dừng script khi lệnh thất bại trong ngữ cảnh thông thường; CI cần kiểm riêng error handling của các pipe/job song song. Các lệnh hiển thị **không thay thế SCA scan** — phải cấu hình scanner thích hợp mới có bằng chứng vulnerability status. Nếu scanner cần mạng/cơ sở dữ liệu mới, quản lý cache/credential và thời điểm cập nhật dữ liệu minh bạch.

Các artifact nên được đặt tên theo release ID/commit SHA, có checksum, lưu theo retention. Không lưu secret/token dưới dạng test attachments, screenshot hay plain-text pipeline artifacts.

### 11.1. Không cho chạy release nếu test bị tắt

Một số tùy chọn như `-DskipTests` hoặc `-Dmaven.test.skip=true` có thể làm build nhanh nhưng **không tương đương quality gate**. CI phải xác minh test executed count và report chứ không chỉ exit code từ package stage.

Không cho deploy tự động khi có critical regression về authentication/authorization/CSRF hoặc khi dependency finding vượt mức rủi ro mà không có exception hợp lệ. Nếu security scanner outage, quyết định fail-closed hay tiếp tục bằng quy trình khẩn phải được phê duyệt từ trước; không âm thầm bỏ qua scanner.

### 11.2. Chứng thực artifact và nguồn gốc

Artifact được build từ commit đã review, qua runner/toolchain đã được tin cậy. Lưu checksum (ví dụ SHA-256 của JAR/image digest), provenance/attestation nếu nền tảng hỗ trợ, SBOM và scanner reports. Dùng **immutable artifact** từ staging sang production. Đừng rebuild với dependency versions thay đổi rồi sử dụng report của artifact cũ.

Với container image, việc pin base image theo digest không tự cập nhật security fixes: phải có quy trình chủ động tạo image mới khi có bản vá upstream. Không chọn giữa “pin” và “update” một cách cực đoan; cần **reproducibility + patch cadence** đồng thời.

### 11.3. Các smoke test nên chạy sau deploy

Từ một client bên ngoài đi qua **đúng ingress/proxy**:

- Public health route chỉ tiết lộ thông tin cho phép.
- Protected route anonymous trả 401/302/403 đúng loại entry point.
- Login thành công/thất bại, token/session/cookie behavior, logout và session invalidation.
- User role thấp không đọc được admin route; cross-tenant/resource owner phải bị từ chối.
- POST không CSRF token (trong trường hợp CSRF áp dụng) bị từ chối; POST hợp lệ với CSRF token/credential đúng thành công.
- HTTPS được redirect/hardening theo thiết kế; cookies có `Secure`/`HttpOnly`/`SameSite` phù hợp; HSTS chỉ quan sát trên HTTPS.
- Headers CSP/nosniff/caching đúng; origin CORS được phép và bị cấm có phản ứng khác nhau như policy.
- Actuator/internal debug endpoints không lộ; logs không chứa secrets/token.

**Không chạy thao tác phá dữ liệu trên production** để “test DELETE”. Dùng tenant/test data cô lập, môi trường staging, giao diện dry-run hoặc bài kiểm soát không có side effect nhạy cảm.

## 12. Canary, rollback và theo dõi sau phát hành

Rà soát security không kết thúc ở merge request. Khi deploy bản vá:

1. **Pre-deploy:** chụp lại version/dependency tree/SBOM/image digest/config đã redact, backup/snapshot khi cần; kiểm migration DB có backward compatibility.
2. **Canary:** đưa một phần traffic hoặc môi trường staging tương đương qua artifact mới; theo dõi login success/failure, 401/403, CSRF rejects, 5xx, latency, session creation, IdP callbacks và phát sinh token.
3. **So sánh baseline:** sự tăng 403 sau deploy có thể là policy được siết đúng, nhưng cũng có thể chặn người hợp lệ. Không chỉ nhìn KPI tổng; so theo endpoint, method và nhóm người dùng được phép quan sát.
4. **Quyết định promote/rollback:** nếu có bypass authorization, token validation lỗi hoặc session/cookie bug nghiêm trọng, dừng rollout theo runbook. Rollback application không phải lúc nào đủ nếu đã chạy DB migration hoặc thay đổi keys/secrets.
5. **Post-deploy:** xác nhận artifact digest của pod/VM thực, chạy smoke test, theo dõi scanner/advisory mới, tạo change record và thông báo đến owner.
6. **Hậu kiểm:** cập nhật lessons learned, dependency waiver expiration và test mới cho lỗi đã tìm thấy.

**Không lưu log quá chi tiết chứa credentials** chỉ vì cần debug auth failure. Tập trung mã sự kiện, request ID, endpoint/method, loại quyết định access, version/tenant identifier được xử lý theo chính sách privacy; redact authorization header, cookie, JWT, reset link và payload mật khẩu.

Một quy trình rollback tốt phải xét tác động của key rotation, session schema, data migrations và “roll forward to fixed version” khi rollback cũ sẽ khôi phục lỗ hổng nghiêm trọng. Không luôn quay về phiên bản cũ nếu phiên bản đó đã được xác nhận có thể bị khai thác; có thể tắt tính năng hoặc đưa emergency hotfix.

## 13. Xử lý phát hiện CVE sau khi release

Một bản đã được scan sạch khi phát hành vẫn có thể bị công bố lỗ hổng mới. Cần tạo quy trình liên tục:

~~~text
New advisory / monitoring alert
           |
           v
Identify affected artifacts via SBOM + deployment inventory
           |
           v
Verify exposure, fixed versions and mitigation
           |
           v
Risk decision / escalation and interim controls
           |
           v
Patch -> regression gate -> staged rollout
           |
           v
Confirm active runtime versions + close incident ticket
~~~

Truy vấn inventory phải trả lời được **dịch vụ nào, môi trường nào, artifact digest nào, dependency phiên bản nào** đang chạy. Nếu chỉ giữ POM mới nhất trên main branch thì không đủ để biết một bản cũ còn chạy ở staging/region khác.

Với CVE nghiêm trọng:

- Kiểm advisory vendor và phiên bản có fix, mức độ khai thác trong môi trường cụ thể, exposed endpoints/capabilities.
- Xác định các môi trường đã deploy, dữ liệu có thể ảnh hưởng và người chịu trách nhiệm.
- Áp dụng biện pháp giảm rủi ro tạm thời có kiểm chứng nếu chưa thể vá.
- Chạy lại tests authn/authz, CSRF, headers, session, proxy và business invariants sau khi nâng.
- Đưa mitigation/exception vào change record có owner và thời hạn, rồi xác nhận bằng SBOM/deployed artifact mới.
- Khi cần, thực hiện incident response và thông báo theo nghĩa vụ của tổ chức.

Không viết hướng dẫn “chỉ cần nâng lên bản X là an toàn” nếu chưa xác minh advisory hiện hành và BOM compatibility. Với các library/security framework thay đổi nhanh, bản fix cụ thể phải lấy từ nguồn đáng tin **tại thời điểm xử lý**.

## 14. Những sai lầm thường gặp trong release security review

| Sai lầm | Rủi ro | Cách đúng |
| --- | --- | --- |
| Chỉ xem direct dependencies | Bỏ transitive CVE | Resolved tree + SBOM runtime |
| Thấy version trong pom.xml rồi coi là runtime version | BOM/profile/override có thể đổi kết quả | Effective POM + dependency tree |
| Override mỗi `spring-security-web` vô điều kiện | Lệch dòng module/compatibility | Nâng BOM hợp lý hoặc override được kiểm chứng |
| Nhầm `dependency:analyze` với SCA | Không kiểm CVE | SCA/advisory report riêng |
| Chỉ dựa vào CVSS | Bỏ qua reachability/active exploitation/business impact | Triage có bằng chứng và SLA |
| Scan SBOM từ branch, deploy artifact khác | Kết quả không đại diện production | Promote immutable artifact, so checksum |
| Tắt test/CSRF để build xanh | Bỏ regression hoặc mở auth bypass | Test âm tính, policy exception được duyệt |
| Chỉ test `@WithMockUser` | Không kiểm auth provider/credential | Thêm integration tests login/token thật |
| Cho rằng 403 POST luôn là role check | Có thể bị CsrfFilter chặn trước | Role tests có CSRF hợp lệ và CSRF tests riêng |
| `permitAll("/**")` để chữa 401/403 | Mở URL không chủ đích | Allowlist public hẹp + denyAll |
| CORS `*` với credentials | Lộ dữ liệu qua browser policy | Origin allowlist, audit preflight |
| Tin forwarded headers bất kỳ | Sai host/scheme redirect, trust boundary | Trusted proxy, ingress header sanitation |
| Chỉ đặt HTTPS ở app, quên outbound TLS | Credential rò sang LDAP/IdP/DB | TLS end-to-end/truststore, hostname verification |
| Đưa secrets vào artifact/config dump | Lộ credential/key lâu dài | Secret manager, redact CI/log |
| Expose actuator/debug không phân quyền | Lộ env/config/heap/log | Giới hạn endpoints + network + auth |
| Không có rollback/chứng cứ deploy | Khó khắc phục sau hotfix | Immutable artifact, checksum, change record |
| Đóng CVE bằng một exception vô thời hạn | Rủi ro bị bỏ quên | Owner, bằng chứng, deadline/expiry |
| Pin image digest rồi không rebuild | Chạy OS packages lỗi thời | Pin + lịch patch/image rebuild |
| Tin bản phát hành cũ “vẫn được hỗ trợ” | Không nhận bảo mật upstream | Kiểm lifecycle/support/advisory hiện tại |

Cần ưu tiên kiểm **sự an toàn của hành vi runtime**, không chỉ tính thẩm mỹ của YAML/POM. Một cấu hình trông đúng nhưng không được chain nào áp dụng hoặc bị environment override vẫn có thể không bảo vệ gì.

## 15. Bài tập tự kiểm tra

**Câu 1.** POM khai `spring-boot-starter-web`, không khai báo Tomcat. Có cần kiểm lỗ hổng Tomcat?  
**Có.** Embedded container có thể là transitive runtime dependency và phải nằm trong inventory/SCA.

**Câu 2.** Dependency tree không có warning, `mvn clean verify` pass. Đã chứng minh không có CVE chưa?  
**Chưa.** Cần SCA/advisory scan cập nhật và triage riêng; build/test không phải vulnerability database.

**Câu 3.** Muốn vá một lỗi của Spring Security, có nên pin tùy tiện một module Spring Security cao hơn BOM?  
**Không.** Xem vendor-supported fixed version, BOM/compatibility và regression; override có kiểm soát khi bắt buộc.

**Câu 4.** Endpoint POST với user role đúng trả 403. Có chắc rule role sai không?  
**Không.** Có thể thiếu CSRF token. Test role phải cấp CSRF hợp lệ; test thiếu token riêng.

**Câu 5.** Scanner báo lỗ hổng ở test-only dependency; có thể xóa cảnh báo không cần xem?  
**Không.** Cần xác minh scope và threat model, bởi build/test environment cũng có supply-chain risk; ưu tiên theo mức ảnh hưởng và chính sách.

**Câu 6.** CORS preflight OPTIONS không có cookie bị 401. Có nên yêu cầu user login cho preflight?  
**Không nhất thiết.** Khi bật CORS, preflight cần được xử lý đúng trước auth; actual request vẫn bị kiểm authentication/authorization.

**Câu 7.** MockMvc thấy `X-Content-Type-Options` đúng và không thấy HSTS trên HTTP. Có kết luận HSTS production không có?  
**Không.** HSTS được quan sát trên HTTPS; cần kiểm qua ingress/proxy thực.

**Câu 8.** Runtime config ở Kubernetes khác `application.yml` trong Git. Dùng file nào làm bằng chứng bảo mật?  
**Giá trị hiệu lực sau khi áp dụng các nguồn cấu hình**, được thu thập/redact theo quyền; source file chỉ là một đầu vào.

**Câu 9.** Image được build và scan ở staging nhưng deploy bằng cách rebuild lại ở production. Kết quả scan còn bảo đảm không?  
**Không.** Dependency/image có thể khác; promote đúng artifact/digest đã được kiểm.

**Câu 10.** Đã giảm exposure bằng firewall cho CVE chưa vá. Có thể coi như fix xong và bỏ theo dõi?  
**Không.** Đây là mitigation/exception có thời hạn, cần owner, review và kế hoạch vá.

**Câu 11.** `@WithMockUser` test thành công có chứng minh password encoder hoặc OIDC signature validation đúng?  
**Không.** Mock principal bỏ qua authentication provider; cần integration tests riêng.

**Câu 12.** Sau patch, 401/403 tăng mạnh. Có thể xem là tín hiệu tốt vì hệ thống chặn nhiều request hơn không?  
**Không mặc định.** Cần phân loại request bị chặn đúng hay lỗi authorization/CSRF/session, so baseline và kiểm người dùng hợp lệ.

## 16. Checklist release gate thực hành

### Trước khi tạo artifact

- [ ] Commit đã được review, secret scan không phát hiện credential/key bị lộ.
- [ ] JDK/toolchain và lifecycle support được kiểm lại với nguồn upstream hiện hành.
- [ ] Dependency tree + effective POM được lưu, direct/transitive versions rõ.
- [ ] BOM và các override Spring/Security/Servlet được kiểm cùng nhau.
- [ ] SCA + license + image/OS scan dùng dữ liệu mới; findings có fix hoặc exception hợp lệ có owner/expiry.
- [ ] SBOM liên kết với artifact đúng, plugin/build sources được quản lý.
- [ ] Clean build/test không skip; test reports được lưu và kiểm executed counts.

### Trước khi triển khai staging

- [ ] URL/method/role matrix có anonymous, wrong role, CSRF, owner/tenant negative cases.
- [ ] Spring Security filter chains, matcher order và default deny được kiểm đúng môi trường.
- [ ] CSRF/CORS/headers/cookies/session/redirect/proxy được kiểm theo threat model.
- [ ] OAuth/OIDC, LDAP, JWT và authn provider được test nếu ứng dụng dùng.
- [ ] Không có admin/test account, `{noop}`, security debug, endpoint bypass không được phê duyệt.
- [ ] Secrets từ store phù hợp; runtime config diff đã redact, production profile chính xác.
- [ ] Actuator/internal endpoints và error details không lộ ra public.
- [ ] Staging kiểm qua proxy/TLS/IdP/DB gần production, không chỉ MockMvc.

### Trước khi promote production

- [ ] Artifact/image digest, SBOM, test report, SCA report và commit SHA nhất quán.
- [ ] Có approver, runbook, canary/rollback hoặc roll-forward plan.
- [ ] Kiểm migration và ảnh hưởng session/key rotation trước khi rollback.
- [ ] Smoke tests sau deploy có anonymous/role thấp/admin, CSRF và headers.
- [ ] Monitoring có auth failures/401/403/5xx theo method/endpoint, không log secret.
- [ ] Có owner và lịch re-scan để tiếp nhận advisory mới sau phát hành.

**Kết luận:** Rà soát dependency, bản vá và cấu hình trước khi phát hành không phải checklist tách rời chức năng bảo mật. Với Spring Security Servlet, một release đáng tin cần **biết chính xác đang đóng gói phiên bản nào**, **đánh giá và xử lý lỗ hổng có bằng chứng**, **kiểm chứng cấu hình bảo vệ ở runtime**, **chạy regression tests về authentication/authorization/CSRF**, và **phát hành đúng artifact đã được kiểm** với khả năng quan sát, thu hồi và khắc phục sau deploy.
