# Cập nhật dependency và theo dõi bản vá đúng phiên bản trong Spring Security

> **Phạm vi:** triển khai và vận hành ứng dụng **Java 17+, Spring Boot 3.x và Spring Security 6.x** (Maven hoặc Gradle). Chủ đề là **biết chính xác dependency nào đang được sử dụng, nhận biết bản vá an ninh áp dụng cho phiên bản nào, cập nhật một cách nhất quán và chứng minh bản build mới đã được triển khai**. Tài liệu có quy trình điều tra dependency graph, đọc Spring Security Advisories/CVE, bản mẫu ứng dụng Java/Gradle chạy được, kiểm thử hồi quy, quản lý BOM, SBOM và tự động hóa pull request. Phiên bản xuất hiện trong ví dụ là **mốc minh họa đã được đối chiếu tài liệu chính thức**, không phải cam kết rằng đó luôn là phiên bản mới nhất tại thời điểm bạn đọc.

## 1. Vì sao việc cập nhật dependency là công việc bảo mật?

Một ứng dụng dùng `spring-boot-starter-security` có thể chạy ổn nhiều năm nhưng vẫn chứa các thư viện đã phát hiện lỗ hổng. Khi một advisory được công bố, tổ chức cần biết **mã nào bị ảnh hưởng, package nào đang nằm trong artifact và bản khắc phục thực sự có mặt ở production chưa**.

Đừng gộp các câu hỏi này thành “mình đã sửa build.gradle rồi”:

1. **Declared version:** build file đang khai báo phiên bản Spring Boot/plugin/thư viện nào?
2. **Managed version:** BOM hoặc dependency management gợi ý các phiên bản nào?
3. **Resolved version:** Gradle/Maven cuối cùng chọn phiên bản nào cho `runtimeClasspath` hoặc dependency tree, kể cả dependency **bắc cầu** (transitive)?
4. **Packaged version:** phiên bản nào thực sự được đóng gói trong executable JAR, WAR, container image hoặc native binary?
5. **Deployed version:** instance đang phục vụ traffic chạy build/image digest và tập thư viện nào?
6. **Affected/fixed version:** advisory chính thức xác định khoảng phiên bản bị ảnh hưởng, điều kiện khai thác và các bản vá nào?

Một pull request đổi phiên bản **không** đồng nghĩa production đã được vá. Một security scanner báo “có CVE trong repo” cũng chưa đủ chứng minh đường tấn công có thể khai thác ở cấu hình đang dùng; tuy vậy, phát hiện ấy phải được **triage có chứng cứ**, không chỉ bị bỏ qua vì service “chưa thấy lỗi”.

### Ví dụ dòng phụ thuộc

```text
security-patch-demo
  |
  +-- org.springframework.boot:spring-boot-starter-security
  |      |
  |      +-- Spring Security Web / Config / Core / Crypto...
  |
  +-- org.springframework.boot:spring-boot-starter-web
         |
         +-- Spring Framework / embedded servlet container / JSON...
         |
         +-- Other transitive libraries

build.gradle declares starter without per-module version
       |
       v
Spring Boot BOM + Gradle resolution choose exact modules
       |
       v
bootJar packages a concrete runtime dependency set
       |
       v
Deployment rolls out a concrete image/artifact digest
```

Các nhánh thực tế thay đổi theo dòng Spring Boot, modules và các starter bạn chọn. Sơ đồ này minh họa **trách nhiệm kiểm kê**, không phải bản in dependency tree của một build cụ thể.

## 2. Spring Boot BOM giúp giữ phiên bản đồng bộ

### 2.1. BOM là gì?

**Bill of Materials (BOM)** là tập các **version constraints/managed versions** cho một nhóm dependency. Spring Boot phân phối `spring-boot-dependencies` để quản lý phiên bản Spring Framework, Spring Security, thư viện HTTP, JSON, logging, database, v.v. Mục tiêu là dùng một bộ tương thích đã được dự án Boot kiểm thử cùng nhau.

Trong dự án Boot thông thường, bạn khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

**Không cần tự thêm version** vào từng starter hoặc các module Spring Security do BOM quản lý nếu plugin/dependency management đã được cấu hình đúng. Lợi ích: nâng **Spring Boot patch** thường kéo theo tập các dependency đã được cập nhật phù hợp với dòng Boot đó.

Lưu ý quan trọng: **chỉ áp plugin `org.springframework.boot` không nên được coi là toàn bộ cơ chế BOM của mọi cấu hình Gradle**. Dự án Gradle có thể dùng plugin `io.spring.dependency-management` hoặc dùng native `platform(...)` để thực sự áp dụng BOM. Khi kiểm kê, phải xem build script và resolved dependency graph, không đoán từ tên plugin.

### 2.2. Patch, minor, major không hoàn toàn giống nhau

Ví dụ về một phiên bản ba thành phần:

```text
MAJOR.MINOR.PATCH

6.5.11
| |  |
| |  +--- Patch trong một release line
| +------ Minor release line
+-------- Major generation
```

Đây là **mẫu đọc định dạng**: không suy từ số ví dụ rằng `6.5.11` là phiên bản đang được deploy hoặc là phiên bản mới nhất. Spring Security mô tả patch releases chủ yếu nhằm sửa lỗi và duy trì tương thích trong line, còn major release có thể có breaking changes. Dù là patch, **đều phải chạy test** vì bug/security fix có thể làm một luồng vốn phụ thuộc vào hành vi sai thay đổi.

Đối với Spring Boot 3.x, thông thường ghép với Spring Framework 6.x và Spring Security 6.x do BOM của dòng Boot tương ứng quản lý. Khi chuyển lên thế hệ Boot mới hơn, cần xem migration guide, Java/Gradle/Maven requirements và thay đổi API, không tự chuyển từng thư viện sang major khác theo số lớn nhất trên kho package.

### 2.3. “Đúng phiên bản” là phiên bản được hỗ trợ và chứa bản sửa

Không có một con số **duy nhất** bảo đảm mọi ứng dụng đều an toàn. Một phiên bản phù hợp phải thỏa:

- Đang thuộc **release line nhận bản sửa theo chính sách hỗ trợ** áp dụng cho tổ chức.
- **Không nằm trong affected range** của advisory liên quan, hoặc đã đáp ứng **fixed version** và những điều kiện bổ sung trong advisory.
- Tương thích với Spring Boot/Spring Framework/Security, Java runtime, Gradle/Maven, Servlet container và các extension bạn dùng.
- **Đã được resolve và đóng gói thực tế**, không chỉ thay đổi trong file dependency.
- Đã qua kiểm thử authentication, authorization, CSRF, session, headers và các chức năng nghiệp vụ trọng yếu.
- Được deploy đủ các instances và có bằng chứng build/image version/digest.

Nếu một bản vá chưa có trên dòng hiện tại, đánh giá nâng lên minor/major **đang được hỗ trợ** hoặc áp dụng biện pháp giảm thiểu tạm thời được vendor khuyến nghị; đặt thời hạn nâng cấp và quản lý exception rõ ràng.

## 3. Một sơ đồ ra quyết định khi có CVE/advisory

```text
Nhận thông báo mới
      |
      v
Xác nhận nguồn chính thức / ngày công bố / package / advisory ID
      |
      v
Lấy dependency graph đã RESOLVE cho version build đang deploy
      |
      +-- Không có module/package? -> ghi evidence, xem artifact/runtime
      |
      +-- Có module trong affected range?
            |
            +-- Không -> lưu bằng chứng version, tiếp tục theo dõi
            |
            +-- Có -> kiểm tra điều kiện bị ảnh hưởng,
                       attack surface, exposed entry point, controls
                       |
                       v
             Có fixed release trên supported line?
                 |                     |
                Có                   Không
                 |                     |
                 v                     v
          Nâng patch/BOM        Upgrade release line
          hoặc vendor fix       hoặc mitigation có thời hạn
                 \                     /
                  v                   v
                Build + tests + scan + kiểm tra artifact/SBOM
                              |
                              v
               Phê duyệt, canary, release, theo dõi
                              |
                              v
                  Xác minh toàn bộ production instances
```

**Triage dựa trên bằng chứng, không dựa trên đoán:** một advisory có thể chỉ ảnh hưởng khi bật tính năng cụ thể, có chuỗi filter nhất định hoặc khi ứng dụng nhận input không đáng tin tại API nhất định. Cần đọc **phiên bản bị ảnh hưởng, phiên bản đã sửa, điều kiện cấu hình, mô tả tác động và các hướng dẫn**. Nếu chưa xác minh được phạm vi, giữ trạng thái “đang đánh giá” và ưu tiên biện pháp bảo vệ thích hợp; đừng ghi “không ảnh hưởng” khi thiếu evidence.

Thang CVSS/EPSS, exploit availability, đường truy cập Internet, quyền cần để khai thác, tài sản và dữ liệu bị ảnh hưởng giúp **xếp thứ tự xử lý**. Chúng không thay việc kiểm tra chính xác component/affected range; CVE severity cao không đồng nghĩa mọi cách dùng đều bị khai thác được, và severity thấp không đồng nghĩa có thể trì hoãn vô hạn.

## 4. Nguồn thông tin chính thức nên theo dõi

| Nguồn | Dùng để xác minh | Điều không nên suy ra |
| --- | --- | --- |
| [Spring Security Advisories](https://spring.io/security/) | Advisory công bố, product/module, CVE, mức độ, affected/fixed versions | Không chỉ đọc tiêu đề hay chọn bản cao nhất mà không xét support |
| [Spring Boot Releases / Docs](https://spring.io/projects/spring-boot) | Dòng release, reference, nâng cấp, BOM tương ứng | “Có phiên bản mới” không đồng nghĩa deploy an toàn nếu chưa test |
| [Spring Security release documentation](https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html) | Numbering, starter, override, BOM | Override một module tùy tiện có thể gây lệch module |
| [Spring Boot Managed Dependencies](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html) | Các coordinates được BOM của **đúng** Boot patch quản lý | Không khẳng định runtime đang dùng đúng bản managed nếu có override/conflict |
| [Gradle dependency reports](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html) | Vì sao phiên bản X được chọn trên configuration Y | Không thể suy toàn bộ production artifact chỉ từ một configuration |
| [Apache Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html) | Resolved dependency tree | Không phản ánh các artifact khác nếu chưa xét scope/module/packaging |
| [GitHub Advisory Database](https://github.com/advisories) và [OSV](https://osv.dev/) | Thông tin vulnerability cho nhiều ecosystem | Scanner may báo false positive/thiếu precondition; cần triage |
| [NVD](https://nvd.nist.gov/) | Tham khảo CVE metadata, scoring và liên kết nguồn | Không dùng làm nguồn duy nhất khi vendor có hướng dẫn mới hơn |

**Nhịp vận hành:** theo dõi Spring security advisories thường xuyên qua RSS/notification/channels được tổ chức phê duyệt; kiểm tra dependency change requests theo lịch. Khi có thông tin khẩn, xử lý ngay theo rủi ro; đừng chờ lịch nâng phiên bản định kỳ.

### Câu hỏi quan trọng khi đọc advisory

1. CVE/advisory đó thuộc **Spring Security**, Spring Framework, Boot, Spring Data, Tomcat, Jackson, Logback hay module khác?
2. Tên **artifact** là gì? Có bị kéo vào build qua starter/transitive dependency không?
3. Khoảng affected version và fixed versions **theo từng release line** là gì?
4. Cần bật cấu hình/endpoint/feature cụ thể mới bị ảnh hưởng không?
5. Patch có trong Boot BOM đang dùng chưa, hay cần nâng Boot patch hoặc điều chỉnh dependency management có kiểm soát?
6. Các môi trường có cùng resolved artifact không? Test và production có khác image/version không?
7. Cần restart/redeploy mới loại bỏ bản JAR dễ tổn thương không?
8. Có mitigation tạm thời được vendor chấp nhận không? Ai phê duyệt và ngày hết hạn exception là gì?

## 5. Ví dụ dự án Gradle hoàn chỉnh để thực hành kiểm tra bản vá

### 5.1. Mục tiêu bài lab

Tạo một API nhỏ với:

- `GET /public` — công khai.
- `GET /api/me` — cần đăng nhập HTTP Basic.
- `GET /api/admin` — chỉ `ROLE_ADMIN`.
- Hai tài khoản demo `reader`/`reader-pass` và `admin`/`admin-pass`, password hash bằng BCrypt.
- Regression tests cho các đường 200, 401, 403.
- Build dùng **Spring Boot BOM** để không pin từng module Spring Security.

**Phiên bản được dùng trong mẫu:** `org.springframework.boot` plugin `3.5.16` là ví dụ một bản patch đã xuất hiện trong tài liệu Spring Boot 3.5 chính thức khi soạn bài. Đây **không phải lệnh yêu cầu mọi dự án hạ/nâng về 3.5.16** và không nên giả định nó còn là patch mới nhất. Khi thực hành trong dự án thật, **mở tài liệu release của supported line đang dùng và đối chiếu advisory/fixed versions trước khi thay version**.

### 5.2. Cấu trúc dự án

```text
security-patch-demo/
├── settings.gradle
├── build.gradle
├── gradlew                      # tạo bằng Gradle Wrapper
├── gradlew.bat                  # tạo bằng Gradle Wrapper
├── gradle/wrapper/...
└── src/
    ├── main/java/demo/SecurityPatchDemoApplication.java
    └── test/java/demo/SecurityPatchDemoApplicationTest.java
```

Những file `gradlew`, `gradlew.bat` và `gradle/wrapper/` là **các file wrapper do công cụ Gradle tạo** (ví dụ Spring Initializr). Chúng không được tạo ra chỉ bằng cách dán các đoạn code dưới đây; cần tạo project Boot/Gradle trước hoặc tạo Gradle Wrapper bằng Gradle đã cài.

### 5.3. settings.gradle

```groovy
rootProject.name = 'security-patch-demo'
```

### 5.4. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    // Native Gradle BOM support; không dùng plugin
    // io.spring.dependency-management trong biến thể này.
    implementation platform(
            org.springframework.boot.gradle.plugin
                    .SpringBootPlugin.BOM_COORDINATES)
    testImplementation platform(
            org.springframework.boot.gradle.plugin
                    .SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Hai điểm cần đọc kỹ:**

1. `org.springframework.boot` plugin được pin ở phiên bản xác định, thay vì `3.5.+` hoặc `latest.release`. Build có thể tái lập hơn, nhưng vẫn cần kiểm tra transitive versions, Gradle Wrapper và artifact repositories.
2. `implementation platform(...)` và `testImplementation platform(...)` áp dụng BOM của plugin Boot cho **hai configuration families** trong project này. Dùng native Gradle BOM là một lựa chọn được hỗ trợ, khác với cách dùng `io.spring.dependency-management`. Vì vậy không có version tường minh tại `spring-boot-starter-security` hoặc `spring-security-test`.

**Không thay thành `enforcedPlatform` một cách máy móc.** `platform` đưa constraints/recommendations vào resolution; một dependency có constraints khác hoặc override có thể khiến phiên bản được chọn khác bản trong BOM. `enforcedPlatform` ép versions và có thể làm xung đột với các dependency khác. Phải đọc `dependencyInsight` và quyết định dựa trên compatibility, không dựa trên cảm giác “càng ép càng an toàn”.

### 5.5. Java 17+ ứng dụng chạy được

Tạo file `src/main/java/demo/SecurityPatchDemoApplication.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityPatchDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityPatchDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password(encoder.encode("reader-pass"))
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("name", authentication.getName());
    }

    @GetMapping("/api/admin")
    String adminPage() {
        return "admin-only";
    }
}
```

File chứa đúng một class `public` trùng tên file, hai class package-private cùng package `demo`. `@SpringBootApplication` quét cả controller và configuration. API chỉ có GET, không tắt CSRF; mục đích ở đây là thử **hành vi security vẫn đúng sau khi nâng dependency**, không trình diễn một hệ thống phân quyền đầy đủ cho production.

### 5.6. Kiểm thử hồi quy bằng JUnit và MockMvc

Tạo `src/test/java/demo/SecurityPatchDemoApplicationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityPatchDemoApplicationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointStillWorksAfterUpgrade() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void anonymousUserStillNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordStillFails() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("reader", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validUserCanReadProfile() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("reader"));
    }

    @Test
    void normalUserStillCannotReadAdminEndpoint()
            throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminStillHasExpectedAccess() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-only"));
    }
}
```

Những test này là **functional regression smoke tests**: chúng xác nhận chính sách authentication/authorization của demo vẫn hoạt động sau cập nhật. Chúng **không chứng minh** mọi CVE đã được sửa; điều ấy cần đối chiếu affected/fixed versions trong advisory với resolved/packaged artifact, test điều kiện bị ảnh hưởng và deploy thực tế.

### 5.7. Chạy dự án

Với Gradle Wrapper và JDK 17 phù hợp:

```bash
./gradlew --version
./gradlew clean test bootJar
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat clean test bootJar
.\gradlew.bat bootRun
```

Khi server chạy ở `http://localhost:8080` theo mặc định:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/admin
curl -i -u admin:admin-pass http://localhost:8080/api/admin
```

Kỳ vọng tương ứng là 200, 401, 200, 403, 200 với cấu hình HTTP Basic trong ví dụ. Giá trị JSON có thể khác thứ tự thuộc tính; status và security decision mới là trọng tâm test. **Không dùng tài khoản demo/mật khẩu hard-code trong production.**

## 6. Đo phiên bản thực được dùng bằng Gradle

### 6.1. Xem runtimeClasspath

Chạy:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Báo cáo liệt kê các dependency được resolve cho `runtimeClasspath`, gồm dependency trực tiếp và transitive. Kiểm tra `org.springframework.security`, `org.springframework`, embedded server, JSON, logging và các module liên quan advisory.

**Không khẳng định phiên bản bằng mắt thường từ build.gradle**: một constraint có thể chọn version khác với version bạn tưởng. Khi thấy output dạng `requested -> selected`, bản **selected** mới là ứng viên đi vào runtime configuration.

### 6.2. Truy nguyên vì sao Spring Security Web dùng một version

```bash
./gradlew dependencyInsight \
  --dependency org.springframework.security:spring-security-web \
  --configuration runtimeClasspath
```

Lệnh trên giải thích **dependency path**, version được chọn và lý do selection. Thử tiếp:

```bash
./gradlew dependencyInsight \
  --dependency org.springframework.security:spring-security-core \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency org.springframework:spring-web \
  --configuration runtimeClasspath
```

Các dấu `\` tiếp dòng là cú pháp Bash; trên PowerShell đặt trên **một dòng** hoặc dùng dấu tiếp dòng của PowerShell:

```powershell
.\gradlew.bat dependencyInsight --dependency org.springframework.security:spring-security-web --configuration runtimeClasspath
.\gradlew.bat dependencies --configuration runtimeClasspath
```

**Cần phân biệt configuration:** `runtimeClasspath` phản ánh runtime của project Java thông thường; `testRuntimeClasspath` có thể thêm `spring-security-test`, JUnit và thư viện chỉ dùng khi test. Plugin, annotation processor hoặc classpath của build tools có thể thuộc configurations khác. Một thư viện có trong test classpath không có nghĩa nó có trong production jar; một thư viện chỉ dùng ở plugin build không nhất thiết ở runtime của ứng dụng.

### 6.3. Xem artifact đóng gói, không chỉ graph

Sau `bootJar` ở project ví dụ, tên file theo `settings.gradle` và `version`:

```bash
jar tf build/libs/security-patch-demo-0.0.1-SNAPSHOT.jar \
  | grep 'BOOT-INF/lib/spring-security-'
```

Trên PowerShell:

```powershell
jar tf build/libs/security-patch-demo-0.0.1-SNAPSHOT.jar |
    Select-String "BOOT-INF/lib/spring-security-"
```

Tên file thực tế có thể khác nếu project tùy biến `bootJar` hoặc version. Đọc `build/libs` trước khi chọn tên, tránh suy từ một tutorial. Với Boot executable JAR, `BOOT-INF/lib` thường chứa dependency JAR ở runtime; với WAR, native image, shaded JAR hoặc một packaging pipeline khác, cách kiểm tra phải tương ứng.

**Nếu dependencyInsight nói bản đã sửa nhưng executable JAR vẫn chứa bản cũ**, build/repackage hoặc cache/CI workflow có thể sai. Nếu JAR đúng nhưng container chạy bản cũ, lỗi nằm ở bước image build/push/deployment. Từng tầng phải có bằng chứng.

### 6.4. Dependency locking để tái lập

Nếu project chọn dùng Gradle dependency locking, thêm vào `build.gradle`:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Đây là **mảnh cấu hình thêm vào project**, không phải file Gradle độc lập. Sau đó tạo/refresh lock state cho các configurations cần resolve:

```bash
./gradlew dependencies --write-locks
./gradlew clean test
```

Commit lockfile được tạo để CI và developer dùng cùng resolved versions. Khi nâng BOM/patch, **cập nhật lockfile trong cùng pull request**; nếu lock cố định bản cũ, đổi plugin version mà không thay lock có thể gây resolution failure hoặc giữ dependency cũ theo constraints. Locking giúp tái lập, **không tự phát hiện hoặc vá lỗ hổng**. Không dùng dynamic versions như `6.+` để tránh việc CI tự nâng ngoài review.

Với nhiều modules/configurations, xác minh tất cả các configuration dùng khi build và deploy đã được resolve/locked. Gradle docs giải thích giới hạn lock (ví dụ buildscript dependencies hoặc SNAPSHOT/changing modules) và cách update khóa có chọn lọc.

## 7. Dự án Maven: kiểm tra dependency tree và version quản lý

Nếu project dùng Maven, **`spring-boot-starter-parent`** thông thường cung cấp dependency management tương ứng với Boot version. Ví dụ cấu hình minh họa trong `pom.xml`:

```xml
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

    <groupId>demo</groupId>
    <artifactId>security-patch-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
```

Đây là biến thể Maven tương ứng về dependency cho cùng ứng dụng Java/test ở mục 5; **chọn Maven hoặc Gradle**, không cần hai build files trong một project nếu hệ thống không có lý do đặc biệt.

Dùng Maven Wrapper (`mvnw`) nếu có:

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.security:spring-security-web
./mvnw help:effective-pom -Doutput=effective-pom.xml
./mvnw clean verify
```

Trong PowerShell hoặc Windows Command Prompt dùng `mvnw.cmd`. `dependency:tree` giúp xem graph thực được resolve và đường transitive; `effective-pom` giúp xem những thông số/managed dependencies sau khi Maven áp dụng parent, profile, BOM và inheritance. `effective-pom.xml` là file phát sinh để kiểm tra; không nhầm nó với artifact production hay sử dụng nó để ghi đè `pom.xml`.

Nếu không dùng Boot parent mà tự import `spring-boot-dependencies` trong `dependencyManagement`, cần xác minh rõ BOM import và plugin versions; BOM quản lý **dependency versions**, không tự quản lý mọi Maven build plugin giống parent.

## 8. Phương pháp cập nhật an toàn khi có advisory

### 8.1. Trường hợp A: bản sửa đã có trong Boot patch tương ứng

Quy trình ưu tiên:

1. Xác định bản Boot hiện tại và supported line của ứng dụng.
2. Xem advisory: library, affected range, fixed version và prerequisite.
3. Xem bảng **Managed Dependency Coordinates** cho bản Boot patch dự kiến.
4. Nâng **Boot patch** tương ứng trong build file hoặc parent POM, để Boot BOM chọn bộ dependency nhất quán.
5. Kiểm tra `dependencyInsight`/`dependency:tree`: module bị ảnh hưởng phải resolve sang bản đã sửa.
6. Chạy test, đóng gói artifact, quét dependency, triển khai canary và xác minh artifact trong runtime.

Đây thường là lộ trình ít phải can thiệp vào từng version nội bộ. Nhưng không có nghĩa mọi Boot patch mới sẽ chữa **mọi** CVE; phải đối chiếu chính xác module và bản sửa.

### 8.2. Trường hợp B: bản sửa đã có ở Spring Security nhưng Boot BOM chưa cập nhật

Có thể cần **override có kiểm soát** khi có nhu cầu khẩn. Đừng tùy tiện thêm:

```groovy
// PHẢN VÍ DỤ: dễ làm các Spring Security modules lệch version.
implementation 'org.springframework.security:spring-security-web:7.0.0'
```

Đây chỉ là **đoạn phản ví dụ không dành để chạy**: ép một major cao cho một module trong app Boot 3.x có thể tạo API/linkage conflicts hoặc thay đổi behavior. Với các module Spring Security, ưu tiên version alignment theo Spring Security BOM và hướng dẫn chính thức. Với Spring Framework, phải xem cả yêu cầu version tương thích.

Trong dự án Maven kế thừa Boot parent, tài liệu Spring Security cho phép dùng property `spring-security.version` để override phiên bản Security mà Boot quản lý, **sau khi đã xác minh fixed version và tính tương thích**:

```xml
<properties>
    <java.version>17</java.version>
    <spring-security.version>6.5.11</spring-security.version>
</properties>
```

Đây là **mảnh cấu hình minh họa**, không phải khuyến nghị pin `6.5.11` cho mọi CVE. Với Gradle dùng plugin `io.spring.dependency-management`, có thể dùng property quản lý tương ứng. Nhưng với **native `platform(...)`** như ví dụ ở mục 5, property kiểu Maven **không tự thay BOM constraints**; cần dùng cơ chế Gradle constraints/platform/resolution theo hướng dẫn phù hợp.

Mọi override khẩn phải được ghi lại: nguyên nhân/advisory, người phê duyệt, fixed version cần đạt, các module bị ảnh hưởng, kết quả dependency graph, test, ngày xem xét lại và kế hoạch **gỡ override khi BOM chính thức đã cập nhật**. Nếu vấn đề có liên quan Spring Framework, servlet container hoặc thư viện transitive khác, phải nâng đồng bộ theo khuyến nghị vendor thay vì ép riêng `spring-security-web`.

### 8.3. Trường hợp C: project nằm trên release line không còn nhận patch

Không thể giải quyết chỉ bằng “cập nhật lên patch mới nhất” nếu **dòng cũ không có bản sửa**. Cần:

- Xác minh thời hạn OSS/commercial support và vendor đang cung cấp fix cho line nào.
- Lập kế hoạch nâng major/minor được hỗ trợ, kể cả Java/Gradle/Maven/framework/Servlet requirements.
- Đánh giá breaking changes, API cấu hình Security DSL, matcher, filter chain, session/authentication behavior.
- Dùng mitigation tạm thời **được xem xét theo advisory**; hạn chế bề mặt tấn công ở gateway, tắt feature bị ảnh hưởng, rule phù hợp, rate limit/traffic controls khi hữu ích.
- Ghi nhận risk acceptance có người chịu trách nhiệm và deadline; không đặt permanent waiver cho scanner.
- Tái kiểm thử toàn bộ security flows và chức năng nghiệp vụ quan trọng.

Một bản vá tự backport không được vendor hỗ trợ đòi năng lực review/test/distribution riêng; không thể giả định sửa vài dòng source rồi công bố “CVE resolved”.

## 9. Đánh giá transitive dependencies và classpath drift

### 9.1. Dependency trực tiếp vs transitive

Ví dụ project chỉ khai báo `spring-boot-starter-web` nhưng một thư viện servlet/logging/JSON xuất hiện do dependency transitive. Khi có CVE cho một trong các thư viện ấy:

- Tìm qua `dependencyInsight` hoặc `dependency:tree` xem **ai kéo nó vào**.
- Xem có phải dependency thực sự vào `runtimeClasspath` và artifact production không.
- Xem Boot patch mới có quản lý bản fixed không.
- Nếu nhiều upstream mang cùng package, xem **resolution conflict** và version cuối.
- Nếu package không được dùng trên code path bị ảnh hưởng, ghi nhận điều kiện exploitability và kiểm tra scanner/advisory, không loại bỏ bừa.

Một số vulnerability thuộc **build-time tools, tests hoặc plugins**. Chúng vẫn có thể ảnh hưởng supply chain/CI, nhưng mức phơi nhiễm khác runtime server. Phải phân loại đúng scope thay vì coi “không ở runtime” là luôn vô hại.

### 9.2. Override cưỡng bức có thể làm build chạy nhưng lỗi runtime

Những vấn đề thường xuất hiện khi module versions không đồng bộ:

- `NoSuchMethodError`, `NoClassDefFoundError`, lỗi class linkage khi khởi động hoặc ở endpoint ít được gọi.
- CSRF/authentication/authorization thay đổi hành vi do fix bug.
- Servlet container hoặc Spring Framework yêu cầu API version tối thiểu.
- JSON serialization/validation/thư viện test thay đổi hành vi.
- Một module Spring Security đã mới nhưng module `spring-security-config`/`core`/`web` khác vẫn cũ.
- Lockfile hoặc dependency constraints giữ version cũ ngoài ý định.

**Cách tránh:** kiểm tra resolved tree trên runtime, test runtime thật, build jar/container và chạy test behavioral. Không dùng `exclude` hoặc `force` để “làm scanner xanh” nếu việc ấy loại bỏ security filter, codec hoặc module đang được ứng dụng cần.

### 9.3. SBOM: ghi lại thành phần cho từng artifact

**Software Bill of Materials (SBOM)** như CycloneDX lưu dependency components/versions/hashes cho build. Spring Boot hướng dẫn tích hợp CycloneDX Maven/Gradle plugins; CI có thể sinh SBOM gắn với artifact/image digest, giữ lại làm bằng chứng khi có advisory mới.

Một quy trình kiểm kê:

```text
Build commit SHA + toolchain + dependency lock
        |
        v
Resolve dependency graph (runtimeClasspath)
        |
        v
Build bootJar/container image
        |
        v
Generate/export SBOM for the artifact
        |
        v
Store artifact hash/image digest + SBOM + build provenance
        |
        v
Scan/advisory match + triage + release approval
```

**SBOM không phải scanner tự động** và một scanner cũng không tự hiểu đủ tất cả điều kiện exploit. Hãy liên kết SBOM với một build cụ thể, tránh chỉ có một file SBOM “của repo” không biết tương ứng bản deploy nào.

### 9.4. Kiểm tra container và nhiều môi trường

Ngoài Spring dependency JAR, một container còn có **base image**, OS packages, JRE và các agent/sidecars. Một security advisory cho OpenSSL/glibc/JRE không được sửa chỉ bằng nâng Spring Security. Ngược lại, nâng base image không cập nhật `spring-security-web` bên trong JAR nếu build Java không thay.

Để kết luận production đã vá, cần xác định:

- Tag và **digest** image đang chạy (tag có thể được ghi đè, digest là dấu định danh cụ thể hơn).
- Mỗi environment/region/instance đang chạy digest nào, bao gồm background workers.
- SBOM/dependency graph thuộc build digest ấy.
- Có còn old pods/replicas/blue-green slot đang nhận traffic không.
- Cache image/build có trả lại artifact cũ không.
- Nếu deployment có rollback, rollback target có tái đưa vulnerable version không; cần quản lý danh sách allowed digests.

## 10. Tự động hóa cập nhật: Dependabot, Renovate và review

### 10.1. Tự động mở pull request, không mặc định tự merge

Công cụ như **Dependabot** hoặc **Renovate** có thể phát hiện patch/minor updates, thay build file/lockfile và mở PR. Đây là cách tốt để tránh một project bị bỏ quên nhiều tháng. Nhưng **chỉ mở PR không chứng minh bản vá đã được deploy**; người/team sở hữu vẫn cần kiểm tra advisory, compatibility và test.

Ví dụ file `.github/dependabot.yml` dành cho một project Gradle và GitHub Actions:

```yaml
version: 2
updates:
  - package-ecosystem: "gradle"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
```

Đây là **mẫu cấu hình Dependabot version updates**: repo phải bật tính năng/quyền cần thiết trên GitHub; security update PRs và alerts có cài đặt riêng. Cấu hình thực tế nên xem multi-module directories, private registries, grouping, branch protection, cooldown, labels và ownership. Dù tool tạo PR tự động, CI phải chạy và người reviewer phải xem changelog/release notes.

**Không dùng lịch weekly làm SLA duy nhất cho CVE khẩn.** Alerts/advisories cần kênh thông báo và quy trình escalation độc lập, có thể tạo PR ngoài lịch thường lệ.

### 10.2. Bộ kiểm tra PR cập nhật dependency

Đối với PR do bot hoặc developer mở, review nên có:

| Kiểm tra | Bằng chứng cần giữ |
| --- | --- |
| Version manifest thay đổi gì? | Diff `build.gradle`/`pom.xml`, plugin/parent/BOM |
| Version được resolve là gì? | `dependencyInsight` hoặc `dependency:tree` ở đúng configuration |
| Module bị CVE có fixed version chưa? | Advisory chính thức + fixed version + graph |
| Lockfile/SBOM thay đổi nhất quán chưa? | Diff lockfile, SBOM mới và metadata build |
| Test security còn đúng không? | 200/401/403, CSRF, session, method-security, OAuth/OIDC nếu dùng |
| Functional regression? | Unit/integration/e2e, database/client compatibility |
| Binary artifact nào được build? | JAR metadata/hash và/or image digest |
| Deploy kế hoạch thế nào? | Canary, smoke, metrics, rollback, incident owner |
| Có override/waiver không? | Lý do, approver, deadline và theo dõi |

Đối với phụ thuộc không phải Spring như JDBC driver, Redis client hoặc messaging, có thể nâng độc lập tùy mức rủi ro. Với Spring Security/Framework, thường ưu tiên **giữ nhóm modules aligned** theo BOM/vendor guidance.

### 10.3. Không nhất thiết phải pin mọi bản transitive bằng tay

Pin quá nhiều version trong build file tạo “version soup”, khiến Boot BOM mất tác dụng và làm việc nâng patch trở nên khó khăn. Nên:

- Pin **Spring Boot plugin/parent** ở release cụ thể.
- Dùng BOM để quản lý dependency đã được hỗ trợ.
- Dùng lockfiles nếu muốn reproducibility và cập nhật chúng có review.
- Chỉ override vì nhu cầu có bằng chứng; có comment/advisory và ngày gỡ override.
- Tách dependency test/build-time/runtime khi xác định affected components.

**Không dùng `+`, `LATEST` hoặc wildcard động** chỉ để “tự được bảo mật”: chúng làm bản build thay đổi theo thời gian mà không có diff/review; phiên bản mới có thể gây breaking changes và không đảm bảo điều kiện deploy.

## 11. Một quy trình CI/CD cho bản vá có thể kiểm chứng

### 11.1. Luồng kiểm tra đề xuất

```text
Advisory / bot PR / scheduled review
      |
      v
Read source + affected/fixed version + preconditions
      |
      v
Change Boot patch/BOM or approved override
      |
      v
Dependency graph and lockfile verification
      |
      v
Unit tests + MockMvc security tests
      |
      v
Integration/E2E + SCA/dependency scan + SBOM
      |
      v
Build immutable artifact + provenance
      |
      v
Stage deployment + smoke security regression
      |
      v
Canary + metrics + review
      |
      v
Production rollout, verify every instance/image digest
      |
      v
Close advisory ticket with evidence + monitoring
```

### 11.2. Các cổng kiểm thử nên có

**Build gate:** Java toolchain/Gradle/Maven đủ version, build sạch, dependency graph được resolve, signature/checksum policy và repositories không đáng ngờ.

**Security regression gate:** test anonymous vào private endpoint bị chặn; sai credential 401 (HTTP Basic), user đúng 200; user thiếu role 403; admin đủ role 200. Với ứng dụng thực, thêm session logout/fixation, CSRF, OAuth2 Resource Server token validation, method security, filter chain order và multi-tenant resource policy.

**Dependency gate:** scanner phát hiện vulnerability theo package/version; đối chiếu severity và exploitability, không xóa/tắt tất cả warnings. Nếu exception được duyệt, gắn advisory IDs, lý do, thời hạn và người chịu trách nhiệm.

**Packaging gate:** executable JAR chứa correct Spring Security modules; SBOM/hash trùng artifact vừa build; container không có “lớp” cũ được copy từ cache hoặc artifact từ pipeline khác.

**Deployment gate:** xác minh phiên bản/digest đang chạy, không chỉ log “deploy succeeded”; smoke tests ở stage/canary, quan sát số lượng 401/403/500, login rate, token refresh, latency và các lỗi bất thường.

### 11.3. Rollout an toàn

Một patch của security filter có thể thay đổi cách xử lý URL encodings, matchers hoặc CSRF tokens. Rollout nên có:

1. Triển khai staging với representative configuration và test accounts.
2. So sánh authentication/authorization success/failure rates trước/sau.
3. Canary một phần traffic khi kiến trúc cho phép.
4. Có playbook rollback hoặc roll-forward khác, đồng thời **không vô tình rollback về bản dễ tổn thương**. Nếu không thể rollback an toàn, chuẩn bị hotfix/mitigation thay thế.
5. Với database/schema changes, tránh migration phá vỡ backward compatibility trong khi các phiên bản cũ/mới chạy đồng thời.
6. Ghi release metadata: commit, build ID, BOM/runtime versions, SBOM digest, target environment, approver và thời điểm deploy.

**Hạn chế tự động auto-merge dependency PR chỉ dựa trên “test xanh”** khi thay đổi liên quan authentication, authorization hoặc lỗ hổng nghiêm trọng. Test có thể chưa bao phủ tác động và một library mới có thể thay đổi security defaults; cần policy review phù hợp mức rủi ro.

## 12. Chẩn đoán các lỗi phổ biến khi cập nhật Spring Security

### 12.1. “Đã sửa build.gradle nhưng scanner vẫn báo CVE”

Kiểm tra theo thứ tự:

- Plugin/parent version đã thay, nhưng **lockfile** giữ version cũ?
- App dùng native BOM hay `io.spring.dependency-management`? Có override ở project con không?
- `dependencyInsight` có chọn version fixed không hay bị dependency constraint khác ghi đè?
- Scanner đang nhìn vào `testRuntimeClasspath`, `runtimeClasspath`, build plugin hay **image cũ**?
- Artifact/container build mới chưa? Image digest trong cluster đã đổi chưa?
- Scanner report có cache, component alias hoặc false-positive cần đối chiếu evidence không?
- CVE còn ảnh hưởng module/line mới hay chỉ một phần điều kiện cấu hình?

Không chỉ thêm `exclude` để khiến scanner im lặng khi chưa biết module đó còn nằm trong artifact hay không.

### 12.2. “Bump spring-security-web rồi chạy phát sinh NoSuchMethodError”

Khả năng modules Spring Security/Spring Framework chưa aligned hoặc plugin/compiled classpath khác runtime. Truy nguyên toàn bộ `org.springframework.security` và `org.springframework` bằng dependency graph; ưu tiên Boot BOM/approved Security BOM, xóa override không cần thiết, chạy integration tests và build clean. Không tự ý nâng một module sang major khác vì số version “mới hơn”.

### 12.3. “CI xanh nhưng deployment vẫn bị ảnh hưởng”

Có thể build từ commit khác, container copy JAR cũ, image tag bị tái sử dụng, blue/green slot chưa được thay hoặc rollout chỉ một phần. So sánh commit hash, artifact digest, image digest và instance runtime. **CI pass là một bằng chứng, không phải bằng chứng duy nhất về trạng thái production**.

### 12.4. “Thư viện chỉ là transitive nên không cần xử lý”

Sai. Lỗ hổng vẫn có thể bị khai thác qua thư viện transitively loaded. Phải xem scope, exposed code path và fixed version, không xem việc “mình không khai báo trực tiếp” như miễn trừ.

### 12.5. “CVE trong test dependency thì chắc chắn giống CVE ở server”

Không hoàn toàn. Test/build tool vulnerabilities có rủi ro CI/supply chain, còn runtime CVE có rủi ro production service. Cần đánh giá ở đúng môi trường. Tuy nhiên cũng không nên coi dependency test vô hại nếu CI xử lý code/input không đáng tin hoặc có quyền nhạy cảm.

### 12.6. “Patch luôn tương thích và có thể merge ngay”

Patch thường ít breaking hơn, nhưng security fix có thể siết điều kiện đã cho phép trước đây, gây lỗi các test phụ thuộc hành vi cũ thiếu an toàn. Chạy regression tests, xem release notes và chính sách mới; sửa ứng dụng theo hành vi bảo mật đúng, **không mở `permitAll` bừa để làm test xanh**.

### 12.7. “BOM đã an toàn nên mọi dependency trong project an toàn”

BOM là tập managed versions, không phải chứng nhận không có CVE. Project có thể thêm thư viện ngoài BOM, override, custom plugin, OS packages, image layers hoặc dependency scope khác. Cần kiểm kê end-to-end.

## 13. Checklist vận hành phiên bản và theo dõi bản vá

1. Mỗi service có **owner**, repository, môi trường deploy, build pipeline, inventory/SBOM và thông tin supported line.
2. Pin Boot plugin/parent version cụ thể; Java/Gradle/Maven toolchains được xác nhận tương thích.
3. Kiểm tra Boot BOM/Gradle native platform/Maven dependency management thực đang được dùng.
4. Bản `spring-boot-starter-security` không tự pin từng module nếu BOM đã quản lý đầy đủ.
5. Thu thập resolved graph ở **runtimeClasspath** hoặc Maven dependency tree cho build đã deploy.
6. Ghi lại packaged modules và artifact/image digest; phân biệt test/build-time và runtime.
7. Theo dõi Spring Security Advisories và các advisory cho Framework, Boot, server/container và thư viện transitive.
8. Với mỗi alert, kiểm tra affected range, fixed versions, prerequisites và exploitability.
9. Triage theo risk/scope và bằng chứng; không suppress scanner vô thời hạn.
10. Ưu tiên nâng Boot patch/BOM của supported line; override phải có lý do/phê duyệt/deadline.
11. Lockfile, SBOM và dependencies diff phải tương ứng cùng commit/build.
12. CI chạy regression tests cho login, roles, CSRF, method security, session/JWT và nghiệp vụ trọng yếu.
13. Kiểm tra `bootJar`/image thực sự chứa fixed modules.
14. Triển khai stage/canary, theo dõi metrics 401/403/500 và chuẩn bị rollback an toàn.
15. Xác minh **tất cả** production instances đã đổi digest; chú ý workers/batch jobs.
16. Ghi ticket kết luận với advisory, ảnh hưởng, fixed versions, bằng chứng build/deploy, thời điểm và người phê duyệt.
17. Tạo nhịp kiểm tra version updates định kỳ và kênh phản ứng CVE khẩn riêng.
18. Định kỳ đánh giá end-of-support; không ở lại dòng không còn được vá mà không có kế hoạch di chuyển.
19. Cập nhật playbook, test evidence và security policies khi nâng major/minor.
20. Không log secrets khi điều tra version/vulnerability; lưu artifact hashes và correlation IDs thay vì password/token.

## 14. Bài tập tự luyện

1. Vì sao `spring-boot-starter-security` không cần pin `spring-security-web`/`core` riêng nếu đang dùng Boot BOM đúng cách?
2. Phân biệt declared, managed, resolved, packaged và deployed versions. Mỗi loại kiểm tra bằng nguồn/công cụ nào?
3. Một advisory nói thư viện X ảnh hưởng phiên bản trong `runtimeClasspath` nhưng file `build.gradle` không khai báo X. Có thể vì sao?
4. Khi `dependencyInsight` cho biết version selected khác requested, bạn cần xem các thông tin nào?
5. Nếu sửa Boot patch nhưng không update lockfile, CI có thể gặp hiện tượng gì?
6. Vì sao không nên nâng `spring-security-web` lên một major khác trong khi các module Security vẫn ở bản cũ?
7. Một CVE chỉ khai thác được khi bật cấu hình nhất định. Bằng chứng gì cần có để kết luận service không bị ảnh hưởng, và ai nên phê duyệt?
8. Nếu fixed release không tồn tại trên supported line hiện tại, chọn phương án nào?
9. Vì sao `./gradlew test` pass không đủ chứng minh production đã hết lỗ hổng?
10. Vì sao cập nhật JRE/base image không tương đương cập nhật dependency trong `BOOT-INF/lib`?
11. Hãy lập một PR review checklist cho patch ảnh hưởng CSRF filter và HTTP request matchers.
12. Những kiểm thử nào dễ phát hiện cấu hình Spring Security bị nới quyền ngoài ý định sau upgrade?
13. SBOM khác vulnerability scanner ở đâu? Vì sao phải gắn SBOM với image digest/build ID?
14. Vì sao dependency version updates theo lịch weekly không thay được quy trình xử lý advisory khẩn?
15. Nếu scanner báo CVE sau khi release và rollback target cũng vulnerable, ứng dụng nên xử lý tình huống nào trước?
16. Khi sử dụng Maven Boot parent, vai trò `spring-security.version` là gì? Vì sao không áp dụng y nguyên property ấy cho Gradle native platform?
17. Vì sao release line đã hết support là rủi ro ngay cả khi hiện chưa có CVE được công bố?
18. Hãy mô tả bằng chứng tối thiểu chứng minh **một lỗ hổng cụ thể đã được vá trong toàn bộ production**.

**Gợi ý:** (1) BOM quản lý versions; (2) manifest/BOM/graph/JAR/container; (3) transitive dependency; (4) constraints/conflicts/paths; (5) lock cũ có thể chặn hoặc giữ old resolved version; (6) lệch API, linkage và hỗ trợ; (7) cấu hình thật, exposed path, advisory preconditions và review; (8) nâng line được hỗ trợ hoặc mitigation có thời hạn; (9) phải xem artifact/deploy và điều kiện CVE; (10) các lớp khác nhau; (11) matcher/CSRF/security regressions, resolved versions và rollout; (12) test anonymous, role, object owner, cross-tenant, unsafe methods; (13) inventory vs detection; (14) SLA khẩn; (15) mitigation/roll-forward an toàn; (16) parent properties vs Gradle constraints; (17) thiếu đường nhận patch sau này; (18) advisory fixed versions + build provenance + digest + tất cả instances.

## 15. Tài liệu chính thức

- [Spring Security — Security Advisories](https://spring.io/security/)
- [Spring Security 6.5 — Getting Spring Security, BOM và release numbering](https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Customize Dependency Versions và SBOM](https://docs.spring.io/spring-boot/how-to/build.html)
- [Spring Boot 3.5 — Gradle Plugin Dependency Management](https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Apache Maven — Dependency Plugin and dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
- [GitHub Docs — Dependabot Version Updates](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-version-updates)
- [GitHub Docs — Configuring Dependabot Version Updates](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-version-updates)
- [OWASP — Dependency-Check](https://owasp.org/www-project-dependency-check/)
- [CycloneDX — Software Bill of Materials](https://cyclonedx.org/)