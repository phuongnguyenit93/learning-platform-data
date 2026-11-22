# Kiểm tra tương thích Java, Spring Boot và phần mở rộng Kerberos

> **Module:** Spring Security – federation · **Chủ đề cha:** Chuyển đổi và nâng cấp. Bài Knowledge này trình bày phương pháp xác minh tính tương thích giữa **JDK**, **Spring Boot**, **Spring Framework**, **Spring Security**, **Spring Security Kerberos extension**, **Jakarta Servlet**, **JAAS/JGSS**, cùng hạ tầng **KDC/Active Directory/SPNEGO**. “Build thành công” chỉ là một tầng kiểm tra: phải bảo đảm browser nhận `WWW-Authenticate: Negotiate`, gửi service ticket thật, server dùng keytab đúng giải mã được, user được liên kết đúng tài khoản nội bộ và chỉ nhận quyền được cấp.

> **Mốc tham chiếu:** tháng 11/2026. Con số version là những nhánh và baseline đã đối chiếu từ tài liệu Spring/Maven Central khi biên soạn; trước triển khai cần kiểm tra support policy, bản vá bảo mật mới nhất và version thực tế đang resolve. Phần Kerberos 2.x thuộc dòng Spring Security 6, trong khi các modules Kerberos 7.x đã đổi Maven group để đồng hành với Spring Security 7.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Vẽ sơ đồ dependency từ JDK và Servlet container đến Spring Security SPNEGO filter, Kerberos provider, JAAS/JGSS, keytab/KDC và local user mapping.
2. Hiểu tại sao các phiên bản Spring Boot 3/4 đều yêu cầu Java 17+ nhưng không thể tùy ý dùng cùng Kerberos extension.
3. Đọc đúng baseline Kerberos 2.1.1 (JDK 17, Security 6.3.0, Framework 6.1.8); Kerberos 2.2.0 (JDK 17, Security 6.5.1, Framework 6.2.8); và Kerberos 7.1.2 (JDK 17, Security 7.1.2, Framework 7.0.10).
4. Chọn Maven coordinates `org.springframework.security.kerberos:*:2.x` khi dùng Spring Security 6, và `org.springframework.security:spring-security-kerberos-*:7.x` khi dùng Spring Security 7.
5. Phân biệt `javax.servlet.Filter` với `jakarta.servlet.Filter`; đồng thời biết `javax.security.auth.Subject`, `javax.security.auth.kerberos.KerberosPrincipal` là Java SE và **không** đổi thành `jakarta.security.auth`.
6. Kiểm tra `SpnegoAuthenticationProcessingFilter`, `SpnegoEntryPoint`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator` và `UserDetailsService` theo API từng generation.
7. Viết cấu hình `SecurityFilterChain` trên Spring Boot 3 với Kerberos service-ticket validation bằng keytab, không dùng `WebSecurityConfigurerAdapter` cũ.
8. Phân biệt một Kerberos acceptor (nhận SPNEGO) với Kerberos initiator (KerberosRestTemplate hoặc LDAP service client).
9. Chạy Gradle `dependencyInsight`, Maven `dependency:tree`, `jdeps` và một Java 17 classpath probe để phát hiện linkage/version conflict.
10. Kiểm SPN, realm, KVNO, encryption type, JAAS/krb5.conf, DNS, NTP, browser IWA và reverse proxy sau khi nâng JDK.
11. Thiết kế unit, MockMvc, MiniKdc, AD-sandbox, browser E2E và multi-node tests đúng phạm vi.
12. Chạy Java 17 decision matrix demo với stdout xác định; không coi output như giấy chứng nhận vendor support.
13. Nắm cách xử lý NoClassDefFoundError, NoSuchMethodError, UnsupportedClassVersionError, 401 loop, KRB_AP_ERR_MODIFIED và 403 sau xác thực.
14. Lập checklist nâng cấp, rollout, quan sát, rollback và ứng phó nếu keytab/service principal bị sai hoặc bị lộ.

## 2. Kiến trúc xác thực Kerberos trên Spring Security

~~~text
Browser / SPNEGO capable client
    |
    | GET /intranet
    | 401 WWW-Authenticate: Negotiate
    |
    | (acquires service ticket from KDC)
    | Authorization: Negotiate <opaque-SPNEGO-token>
    v
TLS termination / reverse proxy
    |
    v
Spring Security FilterChainProxy (correct SecurityFilterChain)
    |
    v
SpnegoAuthenticationProcessingFilter
    |
    v
AuthenticationManager / ProviderManager
    |
    v
KerberosServiceAuthenticationProvider
    |
    +--> SunJaasKerberosTicketValidator
    |        |
    |        +--> JAAS + JGSS in JDK
    |        +--> service principal / realm
    |        +--> keytab / KVNO / encryption types
    |        +--> KDC-issued service ticket
    |
    v
UserDetailsService / local identity mapping
    |
    v
Authentication + GrantedAuthorities + SecurityContext
    |
    v
Controller / service / tenant and object-level authorization
~~~

Các lớp trên thuộc nhiều hệ thống độc lập. Nếu filter tồn tại trên classpath nhưng không được thêm vào `SecurityFilterChain`, browser không bao giờ tới ticket validator. Nếu Kerberos ticket hợp lệ nhưng `UserDetailsService` không nhận ra principal, ứng dụng phải từ chối, không cấp role mặc định. Nếu source Java biên dịch nhưng keytab trỏ sai SPN hoặc sai KVNO, production sẽ lỗi dù CI compile xanh.

### 2.1. Tách sáu loại tương thích

| Loại | Câu hỏi cần trả lời | Bằng chứng |
| --- | --- | --- |
| **Ngôn ngữ/runtime** | Java source, bytecode, JVM và JGSS provider có tương thích? | `java -version`, `javac`, classfile, JDK modules. |
| **Framework** | Boot/Framework/Security/Kerberos BOM có nhất quán? | Dependency tree, resolved runtime classpath, Javadoc. |
| **Servlet binary** | Web filter được compile với `jakarta.servlet.Filter` đúng container? | Type signatures và startup test. |
| **Protocol** | 401 Negotiate và Kerberos service-ticket validation hoạt động? | Ticket từ KDC test + HTTP/browser test. |
| **Authorization** | User principal trỏ đúng local account/tenant và role? | Local repository/negative tests, 200/403. |
| **Vận hành** | Keytab, SPN, NTP, proxy, container/JDK, replica và rollback đúng? | Canary từng node, security/log audits. |

### 2.2. Không nhầm các providers

- `KerberosServiceAuthenticationProvider` kiểm tra service tickets/SPNEGO tokens, cần `KerberosTicketValidator` và `UserDetailsService` để map local user/authorities.
- `SunJaasKerberosTicketValidator` dùng Java JAAS/Krb5 và service keytab; đây là đường **acceptor**.
- `KerberosAuthenticationProvider` thường dùng client-side authentication với username/password-to-KDC qua `KerberosClient`. Nó **không tự** lấy `Authorization: Negotiate` từ Servlet request.
- `SpnegoAuthenticationProcessingFilter` phân tích Negotiate header và gọi `AuthenticationManager`.
- `SpnegoEntryPoint` gửi challenge `WWW-Authenticate: Negotiate` với status 401, có tùy chọn forward/fallback.
- `KerberosRestTemplate` là đường **client/initiator** gọi một downstream HTTP service được Kerberos bảo vệ; cần test riêng nếu ứng dụng dùng.
- Một HTTP 401 challenge đầu tiên có thể là expected; 401 lặp sau khi đã gửi token thật mới cần điều tra.

## 3. Ma trận phiên bản được kiểm chứng theo nhánh

| Nhánh hệ thống | Java | Spring Boot/Framework/Security | Kerberos module | Nhận xét |
| --- | --- | --- | --- | --- |
| **Legacy** | Java 8/11/17 tùy minor | Boot 2.x, Framework 5.x, Security 5.x, `javax.servlet` | Kerberos 1.x/legacy, cần kiểm lockfile. | Là baseline để di chuyển, **không** đưa nguyên web filter vào Jakarta app. |
| **Spring 6 đời 6.3** | Java 17+ | Boot 3.3.x, Framework 6.1.x, Security 6.3.x | Kerberos **2.1.1** docs được test cùng JDK 17, Security 6.3.0, Framework 6.1.8. | **Candidate**; build và integration test theo patch thực. |
| **Spring 6 đời 6.5** | Java 17+ | Boot 3.5.x, Framework 6.2.x, Security 6.5.x | Kerberos **2.2.0** docs được test cùng JDK 17, Security 6.5.1, Framework 6.2.8. | Candidate, dùng group 2.x; kiểm support status. |
| **Spring 7** | Java 17+ | Boot 4.0/4.1.x, Framework 7.x, Security 7.x | Kerberos **7.1.2** docs được test JDK 17, Security 7.1.2, Framework 7.0.10. | Major migration; dùng group mới `org.springframework.security`. |
| **Mix sai** | Bất kỳ | Boot 3/Security 6 và Kerberos group/version của Security 7. | Không tạo một tested baseline hợp lệ. | Block để sửa dependencies. |
| **Mix sai** | Bất kỳ | Boot 4/Security 7 và Kerberos 2.x. | Rủi ro duplicate classes/API mismatch. | Không dùng làm candidate. |

Các nguồn Spring Boot nêu:
- **Spring Boot 3.3.13** cần Java 17+ và Spring Framework 6.1.21+ với Tomcat 10.1/Servlet 6.0.
- **Spring Boot 3.5.16** cần Java 17+ và Spring Framework 6.2.19+.
- **Spring Boot 4.1.2** cần Java 17+ và Spring Framework 7.0.10+ với Servlet 6.1+.
- Baseline patch/framework của một nhánh **không bảo đảm** mọi combination tùy chọn được test; dùng BOM và chính sách security support của nhánh thực.
- Các bản Java 21/25 có thể là lựa chọn LTS theo support matrix, nhưng phải test GSS/Krb5 thực; **không tự suy Java 25 tương thích với một extension đời cũ chỉ vì Java 17 có thể chạy**.

### 3.1. Artifact metadata có thể đáng tin hơn trang GitHub Releases

GitHub Releases của một repo có thể hiện tag v2.1.0 trong khi Maven Central đã có `org.springframework.security.kerberos:spring-security-kerberos-web:2.2.0`, và Spring docs ghi 2.2.0. Khi kiểm “mới nhất”:
1. Đối chiếu chính **reference docs của version**, không dùng một link documentation không pin version để xem historical behavior.
2. Kiểm Maven Central package/POM/Gradle Module Metadata.
3. Kiểm transitive dependencies (Kerberos 2.2.0 web POM tham chiếu Spring Security Web 6.5.1, Jakarta Servlet 6.0, Kerberos core 2.2.0).
4. Kiểm BOM version thực của Boot app, không để transitive version tự “nâng” security stack ngoài kiểm soát.
5. Kiểm EOL/security patch policy của organization và supplier.
6. Khi Security 7 dùng Kerberos core/web `7.x` theo group mới chứ **không** đổi group của artifact 2.2.0 rồi giữ version 2.2.0.

### 3.2. Vì sao support “Java 17 baseline” chưa đủ?

Một project Spring Boot 3 chạy Java 17 nhưng dùng old Kerberos 1.x được compile với `javax.servlet.Filter` vẫn có thể fail. Một project Boot 4 chạy Java 21 nhưng kéo `spring-security-core:6.x` vào classpath cùng Security 7 có thể fail linkage. JDK đúng là điều kiện cần, không đủ.

## 4. Java EE `javax.servlet` khác Jakarta `jakarta.servlet`

### 4.1. Các imports cần migrate

~~~java
// LEGACY Java EE / Spring Framework 5:
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

// Jakarta Servlet / Spring Framework 6+:
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
~~~

Hai `Filter` trên **không phải cùng Java type**. Bổ sung cả `javax.servlet-api` và `jakarta.servlet-api` vào dependency graph không làm class cũ tự implement interface mới. Filter binary có signature cũ có thể fail khi gắn vào Servlet 5/6 container, dù source compile.

### 4.2. Không đổi JAAS/JGSS Java SE sang Jakarta

~~~java
// Java 17+ Java SE, VẪN là javax.security.auth:
import javax.security.auth.Subject;
import javax.security.auth.login.LoginContext;
import javax.security.auth.kerberos.KerberosPrincipal;

// Java GSS-API:
import org.ietf.jgss.GSSContext;
import org.ietf.jgss.GSSManager;
~~~

`javax.security.auth.*` nằm trong Java SE, không phải Java EE Servlet API. **Không có quy tắc đổi toàn bộ `javax.` thành `jakarta.`.** Những chỗ thật sự thuộc Java EE như `javax.annotation`, `javax.validation`, `javax.persistence` cần kế hoạch riêng tùy framework.

### 4.3. Kiểm dependency sai bằng mã lỗi

| Lỗi | Gợi ý nguyên nhân | Phân loại |
| --- | --- | --- |
| `ClassNotFoundException: javax.servlet.Filter` | Legacy web filter còn dùng Java EE trên Jakarta runtime. | Sai thế hệ web API. |
| `ClassNotFoundException: jakarta.servlet.Filter` | Runtime/container thiếu Jakarta Servlet. | Thiếu dependency/container. |
| `ClassCastException` khi ép old Filter sang new Filter | Trộn javax/jakarta binary. | Migrate thư viện. |
| `NoSuchMethodError` ở Spring Security API | Security Core/Web/Config không cùng major/minor. | Version skew. |
| `UnsupportedClassVersionError` | JRE thấp hơn class file target (Java17=61). | Runtime JDK sai. |
| `NoClassDefFoundError` khi tạo SPNEGO filter | Kerberos web/core module hoặc transitive class thiếu. | Dependency graph. |
| `ExceptionInInitializerError` khi startup JGSS | JAAS/Krb5 config hoặc runtime provider. | Xem nguyên nhân sâu. |

## 5. Maven coordinates và dependency management

### 5.1. Với Spring Security 6: Kerberos extension 2.x

~~~groovy
// Nhánh Spring Boot 3.x, Spring Security 6.x:
implementation 'org.springframework.security.kerberos:spring-security-kerberos-core:2.2.0'
implementation 'org.springframework.security.kerberos:spring-security-kerberos-web:2.2.0'
~~~

Ví dụ `build.gradle` cho lab Boot 3.5:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security.kerberos:spring-security-kerberos-core:2.2.0'
    implementation 'org.springframework.security.kerberos:spring-security-kerberos-web:2.2.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') { useJUnitPlatform() }
~~~

**Chú ý:** Đây là build skeleton về dependency; SPNEGO login cần KDC test/keytab/SPN, không chạy end-to-end chỉ với dependency. Boot BOM quản lý Spring artifacts, không chắc quản lý version extension 2.x; cần kiểm resolved graph/constraints. Không ép Security Core/Web thành 6.5.1 nếu Boot BOM chọn patch cao hơn hợp lệ, nhưng cũng không bỏ qua binary tests khi override.

Maven:

~~~xml
<!-- Spring Security 6 / Kerberos 2.2.0 -->
<dependency>
  <groupId>org.springframework.security.kerberos</groupId>
  <artifactId>spring-security-kerberos-core</artifactId>
  <version>2.2.0</version>
</dependency>
<dependency>
  <groupId>org.springframework.security.kerberos</groupId>
  <artifactId>spring-security-kerberos-web</artifactId>
  <version>2.2.0</version>
</dependency>
~~~

### 5.2. Với Spring Security 7: modules theo group mới

~~~groovy
// Spring Boot 4 / Security 7, lấy version từ đúng Security BOM:
implementation 'org.springframework.security:spring-security-kerberos-core'
implementation 'org.springframework.security:spring-security-kerberos-web'
~~~

Maven:

~~~xml
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-kerberos-core</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
~~~

Spring Security 7 reference xác nhận dependency coordinates đổi group từ `org.springframework.security.kerberos` sang `org.springframework.security`. Package Java class như `org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter` có thể giữ tên; **Maven group và Java package khác nhau**.

Bản Boot 4 cũng thay một số starter names/layout; khi tạo app Boot 4 mới nên dùng Spring Initializr/Boot 4 BOM thay vì bê nguyên các dependency từ Boot 3. Với Web MVC servlet stack, ví dụ starter định hướng:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
repositories { mavenCentral() }
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-kerberos-core'
    implementation 'org.springframework.security:spring-security-kerberos-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
tasks.named('test') { useJUnitPlatform() }
~~~

**Đây là candidate build**, phải xác nhận starter/artifacts/BOM của Boot 4.x thực tế; không tuyên bố đã chạy thành công trên một project chưa cung cấp. Không trộn Kerberos 2.x và 7.x trên cùng runtime classpath.

### 5.3. Bản Kerberos 2.1.1 và Boot 3.3

Tài liệu Kerberos 2.1.1 ghi đã build và test JDK 17, Security 6.3.0, Framework 6.1.8. Điều này làm nó trở thành candidate hợp lý cho app Security 6.3, không chứng minh phiên bản Boot 3.3 patch bất kỳ được support vĩnh viễn. Khi nâng Boot 3.3 lên 3.5, cần xem có nên đổi Kerberos 2.1.x → 2.2.0 và kiểm theo Security/Framework generation, không chọn chỉ theo số version cao hơn.

### 5.4. Dùng một thế hệ dependency duy nhất

~~~text
OK CANDIDATE:
  Boot 3.5.x / Spring Security 6.5.x
  Kerberos group org.springframework.security.kerberos
  Kerberos 2.2.0
  jakarta.servlet 6.0 / Framework 6.2 generation

OK CANDIDATE:
  Boot 4.1.x / Spring Security 7.1.x
  Kerberos group org.springframework.security
  Kerberos 7.1.x / Framework 7 generation
  Servlet 6.1+ / Jakarta

BAD:
  Kerberos web 2.2.0 with Security core 7.1.x
  Kerberos 2.x and Kerberos 7.x both on classpath
  javax.servlet.Filter in Jakarta application
  Spring Security core 6.x alongside Security web 7.x
~~~

## 6. Xem resolved dependency graph thay vì chỉ nhìn build.gradle

### 6.1. Gradle

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-security-kerberos-web \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-web \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency jakarta.servlet-api \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency javax.servlet-api \
  --configuration runtimeClasspath
~~~

Nếu không có javax.servlet, `dependencyInsight` có thể trả “no dependencies matching”; đó là bình thường trong Jakarta app. Kiểm:
- Requested versus **resolved** version.
- BOM/platform constraints và conflict resolution.
- `compileClasspath` vs `runtimeClasspath`.
- Local repository, internal proxies, dependency locks/checksums.
- Fat JAR/external WAR packaging, duplicate security libraries ở shared container classloader.
- CVEs, support status, artifact provenance, transitive patch drift.

### 6.2. Maven

~~~bash
mvn -version
mvn help:effective-pom

mvn dependency:tree \
  -Dincludes=org.springframework.security

mvn dependency:tree \
  -Dincludes=org.springframework.security.kerberos

mvn dependency:tree \
  -Dincludes=jakarta.servlet,javax.servlet
~~~

Dùng Maven Enforcer/Gradle dependency constraints, SBOM và security scanning để phát hiện skew. Không dùng rule “forbid mọi javax” vì **javax.security.auth** của JDK cần giữ; chỉ rà đúng Java EE API packages/artifacts mà target runtime không dùng.

### 6.3. Dùng jdeps và classfile

~~~bash
# Tìm external API references từ JAR đã build.
jdeps --multi-release 17 path/to/kerberos-or-app.jar

# Xem major classfile nếu gặp UnsupportedClassVersionError.
javap -verbose -classpath path/to/classes \
  org.example.kerberos.KerberosApplication
~~~

Java 8 classfile major=52; Java 11=55; Java 17=61; Java 21=65. `jdeps` có giới hạn với dynamic reflection/ServiceLoader; cần runtime tests.

## 7. JDK 17: JAAS, JGSS, krb5.conf và vấn đề runtime

### 7.1. Module Java SE

- `java.security.jgss` cung cấp Java GSS API/Kerberos support trên JDK tiêu chuẩn.
- `javax.security.auth.Subject`, `javax.security.auth.login.LoginContext` là JAAS API hợp lệ.
- `javax.security.auth.kerberos.KerberosPrincipal` không bị thay bởi Jakarta Servlet.
- `org.ietf.jgss.GSSManager`/`GSSContext` dùng để đàm phán/accept service tickets.
- Nếu dùng `jlink` custom image, xác nhận JGSS module/provider không bị cắt; build JDK và runtime image phải cùng capability.
- JDK crypto/default encryption policies thay đổi giữa patch/major; test enctypes được KDC/AD phát thay vì mặc định luôn hỗ trợ RC4/DES cũ.

### 7.2. Java options và keytab

~~~text
JAVA_TOOL_OPTIONS=-Djava.security.krb5.conf=/etc/krb5.conf
APP_KRB_SERVICE_PRINCIPAL=HTTP/portal.example.org@EXAMPLE.ORG
APP_KRB_KEYTAB_PATH=/run/secrets/http-service.keytab
~~~

Dùng secret mounts/Vault và service account least privilege. `krb5.conf` phải là config tin cậy; DNS SRV/realm mapping, SPN và thời gian UTC/NTP phải khớp KDC. Không in full keytab contents hoặc raw Negotiate headers khi debug.

### 7.3. Lệnh kiểm tra chỉ đọc

~~~bash
# Xem entries principal/KVNO và enctypes, không in secret key.
klist -k -e /run/secrets/http-service.keytab

# Xem timestamps entry; KHÔNG phải hạn dùng kiểu X509.
klist -k -t /run/secrets/http-service.keytab

# Với test TGT/KDC đã được cấp phép:
kvno -k /run/secrets/http-service.keytab \
  HTTP/portal.example.org@EXAMPLE.ORG
~~~

**Không dùng `klist -K`**: nó có thể hiển thị giá trị khóa bí mật. `kvno -k` thử giải mã service ticket qua keytab nhưng cần client credential cache/TGT và KDC/network hoạt động; nếu fail, phân loại DNS/clock/principal/enctype trước khi kết luận keytab hỏng.

### 7.4. Không tự rotate KDC key trong preflight

MIT `kadmin ktadd` có thể randomize principal keys/change KVNO theo workflow, gây outage ở những service instances chưa có new keytab. Monitor/CI chỉ chạy commands read-only. Rotation cần change ticket, KDC/AD admin, overlap và rollback có kiểm chứng. Old keytab trên disk **không** khôi phục KDC secret đã bị thay.

## 8. SPNEGO filter và SecurityFilterChain trên Spring Boot 3

Mẫu dưới minh họa cách dùng Kerberos 2.2.0 ở Spring Security 6. Nó cần KDC test, service principal và keytab thật để có thể đăng nhập; **không phải chương trình Java chỉ với JDK**.

### 8.1. Cấu trúc project

~~~text
spnego-upgrade-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/org/example/kerberos/
    │   ├── KerberosApplication.java
    │   ├── KerberosSecurityConfig.java
    │   └── ApiController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'spnego-upgrade-lab'
~~~

`KerberosApplication.java`:

~~~java
package org.example.kerberos;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KerberosApplication {
    public static void main(String[] args) {
        SpringApplication.run(KerberosApplication.class, args);
    }
}
~~~

`application.yml`:

~~~yaml
app:
  kerberos:
    service-principal: "${APP_KRB_SERVICE_PRINCIPAL}"
    keytab-path: "${APP_KRB_KEYTAB_PATH}"

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

### 8.2. `KerberosSecurityConfig.java`

~~~java
package org.example.kerberos;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;

@Configuration
public class KerberosSecurityConfig {

    @Bean
    UserDetailsService labUsers() {
        // CHỈ LAB: không sao chép hard-coded roles vào production.
        return name -> {
            if (!"alice@EXAMPLE.ORG".equals(name)) {
                throw new UsernameNotFoundException("unauthorized");
            }
            return User.withUsername(name)
                .password("{noop}unused-no-password-flow")
                .authorities("APP_READ")
                .build();
        };
    }

    @Bean
    SecurityFilterChain web(
            HttpSecurity http,
            UserDetailsService labUsers,
            @Value("${app.kerberos.service-principal}")
                String servicePrincipal,
            @Value("${app.kerberos.keytab-path}")
                String keytabPath) throws Exception {

        SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(servicePrincipal);
        validator.setKeyTabLocation(
            new FileSystemResource(keytabPath));
        validator.setDebug(false);

        KerberosServiceAuthenticationProvider provider =
            new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(labUsers);

        ProviderManager manager =
            new ProviderManager(provider);

        SpnegoAuthenticationProcessingFilter filter =
            new SpnegoAuthenticationProcessingFilter();
        filter.setAuthenticationManager(manager);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/error").permitAll()
                .requestMatchers("/api/**")
                    .hasAuthority("APP_READ")
                .anyRequest().denyAll()
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new SpnegoEntryPoint()
                )
            )
            .authenticationProvider(provider)
            .addFilterBefore(
                filter, BasicAuthenticationFilter.class
            )
            .build();
    }
}
~~~

`ApiController.java`:

~~~java
package org.example.kerberos;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "UP");
    }

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication auth) {
        return Map.of(
            "authenticated", auth.isAuthenticated(),
            "authType", auth.getClass().getSimpleName()
        );
    }
}
~~~

### 8.3. Giới hạn thiết kế

- `labUsers` chỉ là fixture. Production cần map Kerberos principal + realm từ ticket đã verify → local user ID bất biến → trạng thái active/tenant/role theo trusted repository; không auto-link bằng email và không cấp `ROLE_ADMIN` mặc định.
- Không kích hoạt `formLogin` hoặc `httpBasic` trong lab trên; chuỗi password `{noop}...` không được dùng làm phương thức login. Production nên thay hẳn test UserDetailsService.
- `SpnegoEntryPoint` gửi `401 WWW-Authenticate: Negotiate`, đây là challenge đầu tiên hợp lệ, không phải lỗi.
- `SunJaasKerberosTicketValidator` cần đúng service principal/keytab và GSS provider trên JDK; đoạn config không tạo KDC.
- Mặc định local user mapping có thể nhận principal format khác `alice@EXAMPLE.ORG` tùy realm/validator; phải xác nhận trong test, không so kiểu substring.
- Không tắt CSRF toàn bộ Spring app để SPNEGO hoạt động. Các business POST dùng session cookie phải có CSRF policy, authorization/tenant checks.
- Không đăng ký Filter hai lần ngoài `SecurityFilterChain`; với multiple chains cần rõ `@Order/securityMatcher`.
- Spring Security 7 có API/behavior lifecycle khác, cần build/test và dùng dependency group 7.x trước khi tái dùng mã này.
- Không log raw HTTP `Authorization: Negotiate`, keytab path nhạy cảm, plaintext KDC creds hoặc GSS debug ở production.

## 9. Đường đi của HTTP Negotiate và những kết quả thường gặp

~~~text
GET https://portal.example.org/api/me
  -> 401 Unauthorized
  <- WWW-Authenticate: Negotiate

Browser receives challenge
  -> acquires KDC-issued service ticket for
     HTTP/portal.example.org@EXAMPLE.ORG

GET /api/me
  -> Authorization: Negotiate <token>

SPNEGO Filter
  -> TicketValidator validates GSS service ticket
  -> UserDetailsService maps verified principal
  -> SecurityContext stores Authentication
  -> Authorization checks local APP_READ
  -> 200 OK or 403 if business role missing
~~~

**Nâng cấp phải phân biệt** lỗi “browser không gửi token” với “validator không giải mã token” và “local authorization từ chối”. Đừng xử lý chung mọi 401/403 bằng cách tắt filter.

| Dấu hiệu | Khả năng chính | Phép thử |
| --- | --- | --- |
| 401 Negotiate đầu tiên | Thường là challenge expected. | Browser có gửi request thứ hai chứa token không? |
| 401 lặp nhưng không có `Authorization: Negotiate` | Browser IWA allowlist, URL origin, proxy, client KDC/TGT. | Tracing header presence (redacted). |
| 401 sau token | SPN/realm, KVNO/keytab/enctype, clock, Kerberos provider. | KDC test, `kvno -k`, GSS error class. |
| App 403 sau auth | Local role, disabled user, tenant restrictions. | UserDetailsService/AuthorizationManager logs redacted. |
| 302 form login thay 401 | Entry point/chain khác; có intentional fallback. | Filter chain order và routing. |
| Chỉ một replica fail | Keytab mounts, JDK/config drift hoặc clock. | Canary từng node. |
| Ticket đúng nhưng user sai | Realm canonicalization, identity-link error. | Trusted immutable mapping. |

## 10. Java 17 tool chạy độc lập: kiểm classpath và modules

Chương trình này **biên dịch/chạy bằng JDK 17 không cần Spring**, không truy cập KDC và không đọc keys. Kết quả phản ánh classes có trong **runtime classpath hiện tại**, không chứng nhận ticket validation pass.

### 10.1. `KerberosClasspathProbe.java`

~~~java
import java.util.List;

public final class KerberosClasspathProbe {

    enum Status {
        PRESENT, MISSING, BROKEN_LINKAGE
    }

    record Probe(String label, String className) {}

    static Status inspect(String className) {
        try {
            Class.forName(
                className, false,
                Thread.currentThread().getContextClassLoader()
            );
            return Status.PRESENT;
        } catch (ClassNotFoundException e) {
            return Status.MISSING;
        } catch (LinkageError e) {
            return Status.BROKEN_LINKAGE;
        }
    }

    public static void main(String[] args) {
        System.out.println("javaFeature=" +
            Runtime.version().feature());
        System.out.println("javaVendor=" +
            System.getProperty("java.vendor"));
        System.out.println("jgssModule=" +
            ModuleLayer.boot()
                .findModule("java.security.jgss")
                .isPresent());

        List<Probe> checks = List.of(
            new Probe(
                "kerberosPrincipalFromJdk",
                "javax.security.auth.kerberos.KerberosPrincipal"
            ),
            new Probe(
                "gssManagerFromJdk",
                "org.ietf.jgss.GSSManager"
            ),
            new Probe(
                "jakartaServlet",
                "jakarta.servlet.Filter"
            ),
            new Probe(
                "legacyJavaxServlet",
                "javax.servlet.Filter"
            ),
            new Probe(
                "springFilterChain",
                "org.springframework.security.web.SecurityFilterChain"
            ),
            new Probe(
                "spnegoFilter",
                "org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter"
            ),
            new Probe(
                "ticketValidator",
                "org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator"
            )
        );

        for (Probe p : checks) {
            System.out.println(
                p.label() + "=" + inspect(p.className())
            );
        }
    }
}
~~~

### 10.2. Chạy

~~~bash
javac --release 17 KerberosClasspathProbe.java
java KerberosClasspathProbe
~~~

Ví dụ output trên **JDK 17 tiêu chuẩn, chạy với classpath chỉ chứa chương trình này**, không có Spring/Servlet JARs (vendor dòng thứ hai tùy máy):

~~~text
javaFeature=17
javaVendor=<ten-vendor-thuc-te>
jgssModule=true
kerberosPrincipalFromJdk=PRESENT
gssManagerFromJdk=PRESENT
jakartaServlet=MISSING
legacyJavaxServlet=MISSING
springFilterChain=MISSING
spnegoFilter=MISSING
ticketValidator=MISSING
~~~

**Không suy “MISSING Spring = app lỗi”** khi chỉ chạy `java KerberosClasspathProbe` ngoài app classpath. Để dùng chính xác, chạy tool ở test/runtime classpath của ứng dụng đã build. `PRESENT` chỉ chứng minh ClassLoader tìm được class; nếu component không là bean hoặc KDC sai thì authentication vẫn thất bại. `BROKEN_LINKAGE` là tín hiệu kiểm version/NoClassDefFoundError sâu hơn.

## 11. Java 17 deterministic compatibility demo

Đây là chương trình **quy tắc sơ bộ**, không truy Maven Central, không đọc BOM và không kiểm runtime KDC. Output là `CANDIDATE_TEST_REQUIRED` để nhắc rằng một stack có cấu trúc đúng vẫn phải qua end-to-end tests.

### 11.1. `KerberosUpgradeMatrixDemo.java`

~~~java
public final class KerberosUpgradeMatrixDemo {

    record Stack(
        int javaFeature,
        int bootMajor,
        int securityMajor,
        String kerberosGroup,
        boolean jakartaServlet) {}

    enum Result {
        LEGACY_REVIEW,
        JAVA_BASELINE_FAIL,
        CANDIDATE_TEST_REQUIRED,
        VERSION_MISMATCH
    }

    static Result evaluate(Stack s) {
        if (s.bootMajor() >= 3 && s.javaFeature() < 17) {
            return Result.JAVA_BASELINE_FAIL;
        }

        if (s.bootMajor() == 2
                && s.securityMajor() == 5
                && !s.jakartaServlet()) {
            return Result.LEGACY_REVIEW;
        }

        if (s.bootMajor() == 3
                && s.securityMajor() == 6
                && s.jakartaServlet()
                && "org.springframework.security.kerberos"
                    .equals(s.kerberosGroup())) {
            return Result.CANDIDATE_TEST_REQUIRED;
        }

        if (s.bootMajor() >= 4
                && s.securityMajor() == 7
                && s.jakartaServlet()
                && "org.springframework.security"
                    .equals(s.kerberosGroup())) {
            return Result.CANDIDATE_TEST_REQUIRED;
        }

        return Result.VERSION_MISMATCH;
    }

    static void show(String name, Stack s) {
        System.out.println(name + "=" + evaluate(s));
    }

    public static void main(String[] args) {
        show("legacyBoot2", new Stack(
            11, 2, 5, "org.springframework.security.kerberos",
            false));
        show("java11Boot3", new Stack(
            11, 3, 6, "org.springframework.security.kerberos",
            true));
        show("boot3Kerberos2", new Stack(
            17, 3, 6, "org.springframework.security.kerberos",
            true));
        show("boot4Kerberos7", new Stack(
            21, 4, 7, "org.springframework.security",
            true));
        show("boot3WrongGroup", new Stack(
            17, 3, 6, "org.springframework.security",
            true));
        show("boot4OldGroup", new Stack(
            21, 4, 7, "org.springframework.security.kerberos",
            true));
        show("boot3LegacyServlet", new Stack(
            17, 3, 6, "org.springframework.security.kerberos",
            false));
    }
}
~~~

### 11.2. Lệnh chạy và stdout chính xác

~~~bash
javac --release 17 KerberosUpgradeMatrixDemo.java
java KerberosUpgradeMatrixDemo
~~~

~~~text
legacyBoot2=LEGACY_REVIEW
java11Boot3=JAVA_BASELINE_FAIL
boot3Kerberos2=CANDIDATE_TEST_REQUIRED
boot4Kerberos7=CANDIDATE_TEST_REQUIRED
boot3WrongGroup=VERSION_MISMATCH
boot4OldGroup=VERSION_MISMATCH
boot3LegacyServlet=VERSION_MISMATCH
~~~

Phần này chỉ mô phỏng version **generation rules**, không xét minor/patch, vendor JDK, KDC, security vulnerabilities. Ví dụ `boot4Kerberos7=CANDIDATE_TEST_REQUIRED` **không phải** bảo đảm toàn bộ Security 7 artifacts đã đúng. `legacyBoot2=LEGACY_REVIEW` không có nghĩa legacy Boot 2 được support hiện tại.

## 12. Migrate legacy Spring Security configuration

### 12.1. Không giữ WebSecurityConfigurerAdapter

Code đời Security 5 có thể còn:

~~~java
// LEGACY / CHỈ ĐỂ NHẬN DIỆN KHI MIGRATE:
extends WebSecurityConfigurerAdapter
http.authorizeRequests().antMatchers("/**").authenticated();
http.addFilterBefore(spnegoFilter, BasicAuthenticationFilter.class);
~~~

Khi sang Security 6/7, dùng:
- `@Bean SecurityFilterChain`;
- `authorizeHttpRequests` và `requestMatchers`;
- `AuthenticationProvider`/`ProviderManager` riêng cho Kerberos service tickets;
- `SpnegoEntryPoint` và filter order rõ;
- `securityMatcher`/`@Order` đúng nếu nhiều chains;
- Spring Security Test và protocol integration tests;
- session/CSRF/authorization được giữ nguyên chính sách hoặc nâng chuẩn có kiểm soát.

### 12.2. Có nhiều filter chains

~~~text
Chain 1, higher precedence:
  /api/** bearer token authentication, stateless

Chain 2:
  /intranet/** browser SPNEGO, session-aware

Chain 3:
  other routes, explicit public or deny
~~~

Nếu API chain bắt một intranet URL trước, browser có thể chỉ nhận `WWW-Authenticate: Bearer` chứ không có `Negotiate`. Ngược lại SPNEGO challenge trên máy API stateless có thể gây loop. Test `FilterChainProxy` matching cùng rule order và các đường login/logout.

### 12.3. SecurityContext persistence

Custom `SpnegoAuthenticationProcessingFilter` có nhiều setter về `SecurityContextRepository`, `SessionAuthenticationStrategy` và success/failure handlers theo Javadoc. Khi nâng Security version cần test:
- Authentication được lưu ở đúng SecurityContext.
- Session được tạo/lưu hoặc stateless theo contract.
- Session ID rotation tránh fixation.
- SecurityContext không leak giữa requests, threads hoặc tenants.
- Logout thực sự invalidates local session.
- CSRF trên business POST vẫn được bảo vệ.
- Failed GSS token không giữ lại Authentication từ session trước theo cách không an toàn.

Đừng assume “framework lo toàn bộ” nếu custom filter được tạo thủ công. Cần xác nhận behavior bằng integration tests với filter thực.

## 13. Kerberos + Active Directory / MIT KDC: tương thích hạ tầng

### 13.1. Service Principal Name

~~~text
Public URL: https://portal.example.org
Service principal: HTTP/portal.example.org@EXAMPLE.ORG
Realm: EXAMPLE.ORG
Keytab: /run/secrets/http-service.keytab
JDK: approved Java 17+ runtime
~~~

Khi browser truy cập reverse proxy URL, nó thường xin service ticket theo public hostname/SPN, không phải host container nội bộ. Nếu keytab chứa `HTTP/pod-1...` nhưng browser gửi ticket cho `HTTP/portal.example.org`, SPNEGO có thể bị từ chối. Kiểm DNS/CNAME/canonicalization/KDC realm trust và duplicate SPN.

### 13.2. KVNO, enctypes, keytab rotation

Keytab **không có ngày notAfter như X.509**. Thay vì nhìn tuổi file:
- Liệt kê principal, KVNO và encryption types (`klist -k -e`).
- So với KDC authoritative key version/allowed enctypes.
- Dùng service-ticket decryption canary (ví dụ `kvno -k`) với test principal được cấp quyền.
- Kiểm acceptance trên từng replica, trong quá trình rotation có thể có old+new key overlap.
- Đừng tự gọi `ktadd`/`cpw -randkey` trong monitor job vì có thể làm đổi long-term KDC principal key/KVNO.
- Đừng bật DES/RC4 hoặc tắt encryption checks tùy tiện khi nâng Java/KDC.

### 13.3. Java/JGSS/OS policy

- Java patch updates có thể thay default crypto/enctypes/JGSS behaviors.
- Linux và Windows có default krb5.conf/ticket cache/realm discovery khác nhau.
- AD có domain-joined browser/SSPI/Extended Protection, có thể fallback NTLM nếu cấu hình cho phép.
- Một request thành công qua NTLM **không chứng minh** Kerberos GSS ticket acceptance; test mechanism thực.
- JDK vendor, CPU architecture, container image và JGSS modules phải được ghi vào release manifest.
- NTP/clock skew ảnh hưởng vé Kerberos, test expired/not-yet-valid ticket.
- Kerberos LDAP client (JAAS initiator) và HTTP SPNEGO acceptor là hai đường khác, test riêng.
- Fallback login phải là phương án được IAM phê duyệt, không tự cấp anonymous/admin khi KDC unavailable.

### 13.4. Server và proxy

- Reverse proxy không được strip `WWW-Authenticate` / `Authorization` headers thuộc Negotiate flow.
- Cấu hình trusted proxy forwarded host/proto đúng để browser/KDC chọn SPN.
- Có thể cần phân biệt HTTP keep-alive, proxy auth, TLS termination và browser policies.
- Không log raw `Authorization: Negotiate` token dù là header để debug.
- Nếu một node pass, một node fail thì kiểm per-node keytab/KVNO/env/JDK và credentials cache.
- GSS debug flags chỉ dùng rất hạn chế trên test host và kiểm log sanitization.

## 14. Phân tầng kiểm thử sau nâng cấp

| Tầng | Mục tiêu | Công cụ | Không được suy quá |
| --- | --- | --- | --- |
| Static compile | Packages/API/bytecode đúng. | Gradle/Maven, jdeps, javac. | Không chứng minh KDC/login. |
| Startup | Beans/filter/provider khởi tạo. | `@SpringBootTest` và test config. | Không chứng minh ticket valid. |
| Controller | Role, tenant, CSRF, error status. | MockMvc + Spring Security Test. | Không chứng minh Kerberos nếu dùng mock Authentication. |
| Ticket validator | JAAS/JGSS giải mã vé. | MiniKdc/MIT/AD sandbox, keytab test. | Không chứng minh browser flow nếu chỉ unit GSS. |
| Browser E2E | SPNEGO HTTP challenge→token→login. | Domain-joined browser/`curl --negotiate`, proxy, test KDC. | Không thay production policy testing. |
| Multi-node | Rollout/DR/keytab consistency. | Canary từng replica. | Không thể suy toàn cluster từ một node. |

### 14.1. `MockMvc` có thể test 401 challenge

~~~java
// MẢNH kiểm thử: phải có Spring Security FilterChain
// thực trong ApplicationContext test và test keytab config.
mvc.perform(get("/api/me"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        "WWW-Authenticate",
        org.hamcrest.Matchers.containsString("Negotiate")
    ));
~~~

Đây chỉ là challenge ban đầu. `with(authentication(...))` hoặc `@WithMockUser` giả lập đã authenticated và **không đi qua KDC/JAAS ticket verification**. Không báo “Kerberos crypto PASS” từ một MockMvc 200.

### 14.2. Test một GSS handshake thật

Chuỗi lab:
1. Dựng disposable test realm/KDC/AD sandbox.
2. Tạo test user và service principal/secret qua workflow được cấp phép.
3. Mount keytab cho service, cấu hình krb5.conf/realm/NTP/DNS.
4. Khởi chạy app target build, anonymous request phải nhận `401 Negotiate`.
5. Client có test TGT thực hiện HTTP Negotiate; expect 200 sau verified ticket + local account allowed.
6. Wrong keytab/KVNO/principal/realm, expired tickets, clock skew hoặc token tamper → fail closed.
7. Kerberos pass nhưng local user disabled/authority thiếu → deny/403 theo policy.
8. Thử trên browser OS thực, proxy và các replicas.
9. Cô lập credentials, không dùng production KDC, không commit test keytab ngoài policy.

### 14.3. Curl với test TGT đã có

~~~bash
# Chỉ trong môi trường lab, test principal đã kinit.
curl --negotiate -u : \
  https://portal.example.org/api/me

# Không dùng --insecure để bỏ TLS checks.
# Không in raw Authorization token vào CI logs.
~~~

`curl --negotiate` cần libcurl GSSAPI/SPNEGO hỗ trợ, credential cache và KDC hợp lệ. Một lệnh thất bại có thể do client curl build chứ không phải app Kerberos extension.

### 14.4. Tại sao Java 17+ phải test cụ thể

- Java17 JGSS/ciphers tested với KDC hiện tại chưa chắc giống Java21/25.
- Certificate/SSL/HTTP proxy behavior có thể thay.
- KDC có thể từ chối RC4/DES đã deprecated trong security policy.
- App nhiều node dùng JDK vendor khác nhau có thể có GSS behavior khác.
- JVM có module JGSS trên build image nhưng custom runtime image bị thiếu.
- Container file permissions/SELinux và secret volume mounts có thể gây JAAS login fail.
- Nâng Servlet container có thể thay HTTP header parsing, session/cookie behavior.

## 15. Kiểm thử CI và chọn candidate

### 15.1. Pipeline gợi ý

~~~text
1. Baseline inventory + target version decision
2. Java runtime & toolchain validation
3. Dependency/BOM lock + SBOM scan
4. javax.servlet vs jakarta.servlet static analysis
5. Compile + JUnit + MockMvc authorization
6. Startup with test keytab
7. KDC-issued ticket acceptor tests
8. Browser/proxy HTTP Negotiate E2E
9. Wrong SPN/KVNO/enctype/clock/tenant negative cases
10. Keytab rotation/replica/DR consistency tests
11. Security review + change approval
12. Canary rollout + telemetry + rollback readiness
~~~

### 15.2. Không làm CI có tác dụng thay đổi KDC

- Không chạy `ktadd`/`cpw` với KDC production.
- Không in keytab bằng `klist -K`, không log `Negotiate` token.
- Không lưu secret trong Git/container image.
- Tạo sandbox realm/test principals với vòng đời riêng.
- Test keytab/credentials qua secret manager và destroy theo policy.
- CI chỉ được chủ động mutate disposable test KDC theo quyền đã cấp.
- Retain audit về artifact digest, version, success/fail classes và case ID; không retain raw ticket.
- Lỗi `KRB_AP_ERR_MODIFIED` phải phân loại, không tự đổi KDC key.

### 15.3. So sánh trước–sau

| Tín hiệu | Before | After (candidate) | PASS khi |
| --- | --- | --- | --- |
| `java -version` | Java cũ | Java17/21 approved | Actual runtime hợp lệ. |
| Security dependency graph | Legacy | Exact candidate | Không skew/duplicate. |
| SPNEGO challenge | 401 Negotiate | 401 Negotiate | Header và chain đúng. |
| Ticket acceptance | Pass | Pass | Real KDC ticket và keytab. |
| User mapping | User/realm đúng | Không thay sai owner | Same trusted mapping. |
| Local roles | Quyền đã duyệt | Không tăng bất thường | Tenant/resource security. |
| Session/logout | Theo policy cũ | Theo design đã duyệt | Không fixation/leak. |
| Per-node canaries | Good | Good trên mọi node | Không hidden intermittent failures. |
| Secret handling | Restricted | Restricted | Không lộ token/keytab. |

## 16. Ma trận kiểm thử chi tiết

| ID | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| C01 | Boot 3 chạy trên Java 11. | Blocker: yêu cầu Java 17+. |
| C02 | Boot 4 Java 17, Security 7/Kerberos 7 đúng BOM. | Candidate; E2E tests bắt buộc. |
| C03 | Boot 3 + Kerberos 1.x javax Servlet. | Reject/migrate Jakarta binary. |
| C04 | Boot 3 code còn `javax.security.auth.Subject`. | Bình thường: Java SE. |
| C05 | Boot 3.3/Security 6.3 với Kerberos 2.1.1. | Candidate theo docs, cần runtime check. |
| C06 | Boot 3.5/Security 6.5 với Kerberos 2.2.0. | Candidate, không bỏ patch review. |
| C07 | Boot 4/Security 7 dùng group Kerberos cũ 2.x. | Reject major mix. |
| C08 | Boot 4/Security 7 dùng group `org.springframework.security`. | Candidate, phải test. |
| C09 | Spring Security Core6/Web7. | Fail dependency skew. |
| C10 | Boot4/Framework7 kéo Spring Framework6. | Fail dependency skew. |
| C11 | Kerberos 2.x và 7.x cùng runtime. | Fail duplicate/mixed classes. |
| C12 | Boot 3 WAR vào Tomcat 9. | Reject Servlet namespace mismatch. |
| C13 | Boot 4 trên Servlet 6.0-only server. | Reject Servlet 6.1+ requirement. |
| C14 | Compile toolchain17, runtime JDK11. | UnsupportedClassVersionError. |
| C15 | Custom jlink không có java.security.jgss. | Kerberos unavailable. |
| C16 | Kerberos-core bị exclude. | Provider/validator linkage fail. |
| C17 | Kerberos-web bị exclude. | Spnego filter missing. |
| C18 | Legacy WebSecurityConfigurerAdapter còn trong Security6. | Compile fail/migrate. |
| C19 | Legacy antMatchers/authorizeRequests config. | Migrate supported DSL. |
| C20 | Không add SPNEGO filter vào FilterChainProxy. | Không nhận valid ticket. |
| C21 | SPNEGO filter chạy hai lần. | Duplicate processing detected. |
| C22 | Sai AuthenticationEntryPoint. | Không có 401 Negotiate trên protected route. |
| C23 | Browser nhận initial 401 Negotiate. | Expected protocol challenge. |
| C24 | Browser không gửi token ở request sau. | Client IWA/trust policy investigation. |
| C25 | Real service ticket decrypt thành công. | Auth succeeds + local policy. |
| C26 | Tampered service ticket. | Reject, no fallback admin. |
| C27 | Wrong SPN HTTP/backend hostname. | Reject, sửa realm/SPN/proxy. |
| C28 | KDC KVNO8, node keytab chỉ KVNO7. | Detect mismatch/canary fail theo overlap. |
| C29 | Keytab permission denied. | Startup/GSS fails securely. |
| C30 | CI log chứa keytab contents. | Security QA FAIL. |
| C31 | Script dùng `klist -K`. | Security QA FAIL: secret exposure. |
| C32 | Encryption type bị JDK/KDC chặn. | Fail, không bật cipher yếu bừa bãi. |
| C33 | Clock skew ngoài policy. | Kerberos reject. |
| C34 | DNS SRV/realm mapping sai. | KDC lookup fails. |
| C35 | Duplicate AD SPN. | Ticket validation inconsistent/fails. |
| C36 | Reverse proxy strip `WWW-Authenticate`. | Browser không nhận challenge. |
| C37 | Reverse proxy strip `Authorization`. | Loop 401. |
| C38 | Negotiate fallback NTLM thay Kerberos. | Không báo Kerberos PASS. |
| C39 | Ticket pass, UserDetailsService không tìm user. | Deny, không default role. |
| C40 | Kerberos pass, local account disabled. | Deny. |
| C41 | Kerberos pass, user không có APP_ADMIN. | 403 admin endpoint. |
| C42 | Hai realms có cùng username. | Không tự link một local user bằng name. |
| C43 | Email claim trùng account cũ. | Không auto-link. |
| C44 | MockMvc mock authentication trả 200. | Controller pass, không chứng minh KDC. |
| C45 | MiniKdc lab ticket accepted. | Lab cryptographic integration PASS. |
| C46 | Client KerberosRestTemplate gọi downstream. | Test initiator độc lập. |
| C47 | Kerberized LDAP bind sau Java upgrade. | Test JAAS initiator config. |
| C48 | Java21 JGSS behavior khác Java17. | Cần integration/test vendor. |
| C49 | Replica A pass, B fail. | Per-node keytab/JDK drift detected. |
| C50 | Session fixation sau login. | Session rotation policy tested. |
| C51 | SecurityContext không persist đúng. | Fix repository/strategy. |
| C52 | CSRF bị disable để tránh lỗi auth. | QA FAIL cho business POST. |
| C53 | Multi-chain bearer chiếm intranet route. | Fix matcher/order. |
| C54 | Actuator lộ keytab path/subject/user. | Security QA FAIL. |
| C55 | Compile pass khi KDC offline. | Không suy Kerberos PASS. |
| C56 | `ktadd` trong CI preflight thay KDC keys. | Operational FAIL. |
| C57 | Fat JAR chứa service keytab. | Security FAIL. |
| C58 | Rollback old JAR nhưng KDC key đã rotate. | Rollback có thể không hoạt động. |
| C59 | App server shared classloader chứa Spring Security cũ. | Linkage FAIL. |
| C60 | Upgrade Security7 không đổi Maven group Kerberos. | Resolve/update coordinates. |

### 16.1. Lab A — Dependency audit

1. Chụp `java -version` trên build runner và **runtime container**.
2. Chạy Gradle/Maven dependency tree; xác nhận Spring Security Core/Web/Config/Kerberos align.
3. Tìm `javax.servlet` trong source và JAR dependencies; chỉ migrate Java EE types.
4. Xác nhận `javax.security.auth` của JDK tiếp tục hợp lệ.
5. Loại legacy `WebSecurityConfigurerAdapter`, đổi sang `SecurityFilterChain`.
6. Chạy `KerberosClasspathProbe` với app classpath, phân tích `PRESENT/MISSING/BROKEN_LINKAGE`.
7. Rà Servlet container của WAR, node JVM vendor và supported version.

### 16.2. Lab B — KDC/SPNEGO thực

1. Dựng sandbox KDC/AD realm với test user và service principal.
2. Mount keytab test, cấu hình SPN/realm, DNS, NTP, JGSS.
3. GET protected endpoint chưa login → 401 Negotiate.
4. Client có TGT thật thực hiện HTTP Negotiate; test success.
5. Wrong keytab/SPN/KVNO/token/clock → reject.
6. User đã valid Kerberos nhưng local role thiếu → 403.
7. Check filters, SecurityContext, session fixation, CSRF, logout.
8. Chạy lại trên các JVM target, browser/OS và replicas.

### 16.3. Lab C — Rollout/rollback

1. Thiết lập error budget baseline: challenge count, auth success, GSS error classes, role denies.
2. Build target artifact cùng SBOM/lockfile, ký release digest.
3. Staging pass rồi canary 1% traffic/approved cohort.
4. Theo dõi 401 loops, SPNEGO success, keytab/KVNO từng replica.
5. Không rotate KDC keys cùng lúc với framework migration nếu có thể.
6. Thử rollback JAR và xác minh session compatibility/old key availability.
7. Nếu rotation không tránh được, có KDC admin phê duyệt overlap/rollback.
8. Mở rộng rollout chỉ khi every-node canary và local authorization đạt.

## 17. Troubleshooting theo lỗi

### 17.1. `ClassNotFoundException: javax.servlet.Filter`

Legacy web filter hoặc library build cho Boot2/Java EE. Đổi sang Jakarta-compatible Kerberos extension và Spring stack phù hợp, không add cả hai javax/jakarta để che mismatch.

### 17.2. `NoSuchMethodError` trong SpringSecurity

Có thể `spring-security-core` và `spring-security-web` ở khác major/minor, hoặc extension kéo transitive cũ. Dùng `dependencyInsight` và align BOM, không fix bằng cách ép một JAR không rõ nguồn.

### 17.3. `UnsupportedClassVersionError`

Runtime JVM nhỏ hơn classfile target. Java17 classfile major61; kiểm `java -version` **trong container chạy thật**, không chỉ Gradle compile.

### 17.4. `NoClassDefFoundError: jakarta/servlet/Filter`

Container/runtime thiếu Jakarta Servlet đúng generation, hoặc WAR deploy lên server cũ. Boot3 cần Jakarta container, Boot4 yêu cầu Servlet 6.1+. Không nhét javax Servlet vào classpath.

### 17.5. 401 Negotiate loop

Phân loại browser có gửi token, proxy có forward header, keytab/SPN/KVNO/enctype/realm/NTP và GSS provider; kiểm `kvno -k` với TGT test. Không disable service-ticket verification.

### 17.6. `KRB_AP_ERR_MODIFIED`

Thường liên quan service principal key mismatch, duplicate SPN, wrong keytab/KVNO, encrypted ticket không giải mã. Cần KDC/admin phối hợp và per-node checks; không chạy `ktadd` bừa bãi.

### 17.7. 403 sau SPNEGO success

Local principal mapping, account disabled, tenant/resource policy hoặc granted authorities khác trước. Đây là **authorization** chứ không nhất thiết Kerberos bug. Không sửa bằng cấp admin cho mọi Kerberos user.

### 17.8. Một replica login được, một replica không

So Java runtime, keytab mount/permissions, KVNO/enctypes, krb5.conf, DNS, NTP, Spring dependency versions và filter chain; không chỉ nhìn một health endpoint.

### 17.9. Browser Windows không login nhưng curl Linux pass

Có thể browser Intranet allowlist, account/TGT, AD policy, NTLM fallback, proxy TLS/Channel Binding. Test actual mechanism; không hạ security policy để “xanh”.

### 17.10. KerberosRestTemplate hoặc LDAP client fail

Hai use cases này dùng Kerberos **initiator** credentials/JAAS khác service **acceptor**; dù browser SPNEGO server test pass vẫn cần test client path riêng.

## 18. Migration runbook

### 18.1. P0 — Khảo sát

Ghi rõ JDK vendor/patch, Boot/Framework/Security/Kerberos version, WAR/JAR, container, keytab/SPN, AD/KDC, proxy, browsers, JAAS flags, local UserDetailsService, chain order và security/support status. Thu baseline metrics từ hệ thống trước nâng cấp.

### 18.2. P1 — Chọn target được kiểm chứng

Dựa docs tested baseline/BOM và patch security; chọn một target profile cụ thể, không trộn Kerberos 2.x/7.x. Nếu cần Java17 uplift, kiểm stack cũ có support trước khi đổi framework, hoặc dựng môi trường parallel.

### 18.3. P2 — Nâng code và build

Migrate Java EE imports, remove WebSecurityConfigurerAdapter, align dependency graph. Kiểm SecurityFilterChain, JAAS/JGSS module, Bean startup, test sources, static analysis và SBOM. Không thay keytab/KDC ngoài change scope.

### 18.4. P3 — Tích hợp sandbox KDC

Dùng real tickets/realm/SPN/keytab, kiểm 401→Negotiate→success, wrong ticket fail, local role/tenant. Test both Kerberos service provider và các Kerberos clients/downstream nếu có.

### 18.5. P4 — Staging end-to-end

Browser OS/browsers đại diện, HTTPS proxy, domain-joined/KDC test, multi-node secret distribution. Verify session handling, CSRF, logout, key rotation overlap và attack/negative tests.

### 18.6. P5 — Canary production có kiểm soát

Rollout theo từng node/cohort, theo dõi authentication success, 401 loops, KRB error class, user mapping/role deny, secret leaks và observed runtime versions. Có rollback trigger/phương án KDC phối hợp.

### 18.7. P6 — Kết thúc

Đối chiếu target artifact/actual runtime, hoàn tất release note/support matrix, keytab versions, runbook, owner sign-off, no unexpected role grants, no secret logging. Không coi job deploy SUCCESS đồng nghĩa SSO PASS.

### 18.8. Rollback có điều kiện

Nếu chỉ đổi JAR/JDK mà SPN/KDC keys chưa đổi, rollback thường đơn giản hơn; nếu KDC rotate KVNO/password hoặc session serialization đổi, old JAR/keytab có thể không còn tương thích. KDC admin và app owner phải duyệt cả KDC state, service keys và session recovery; **không** tự đổi KDC keys để rollback.

## 19. Checklist production

- [ ] Đã có source-target versions của JDK, Boot, Framework, Security, Kerberos, Servlet container.
- [ ] Java runtime >=17 nếu dùng Boot3/4; kiểm đúng runtime container.
- [ ] Spring Boot 3/Security 6 dùng Kerberos extension 2.x theo `org.springframework.security.kerberos`.
- [ ] Spring Boot 4/Security 7 dùng Kerberos modules theo `org.springframework.security`.
- [ ] Đã so tested baseline Kerberos 2.1.1, 2.2.0, 7.1.x với Spring stack.
- [ ] Không trộn Security 6/7 hoặc cả Kerberos 2.x và 7.x trên classpath.
- [ ] Source Java EE `javax.servlet` được migrate sang Jakarta; không đổi JAAS Java SE `javax.security.auth`.
- [ ] SecurityFilterChain thay cho WebSecurityConfigurerAdapter; filters/provider/entrypoint order đúng.
- [ ] Runtime JAAS/JGSS module và JDK crypto policy tương thích KDC enctypes.
- [ ] Service principal đúng public hostname/realm, keytab secret mount đúng ACL.
- [ ] KVNO/enctype/GSS ticket decryption canary pass trên từng replica.
- [ ] Không dùng `klist -K`, không chạy destructive `ktadd` trong CI.
- [ ] HTTP 401 WWW-Authenticate Negotiate → real service ticket → local auth được test.
- [ ] Browser IWA/AD policies, TLS/proxy/DNS/NTP được kiểm trên staging.
- [ ] UserDetailsService mapping theo trusted principal+realm, local enabled/tenant/roles.
- [ ] No fallback role default hoặc email-only account linking.
- [ ] CSRF, session fixation, SecurityContext persistence, logout và multi-chain được test.
- [ ] MockMvc tests chỉ nhận là controller-level; có KDC integration riêng.
- [ ] Có negative tests wrong SPN/KVNO/enctype/expired ticket/user disabled.
- [ ] KerberosRestTemplate/LDAP initiator paths được test riêng nếu được sử dụng.
- [ ] Build/lockfile/SBOM và support/security patch review đều PASS.
- [ ] Runtime không log keytab, tickets, credentials hoặc nhạy cảm PII.
- [ ] Có alert 401 loop/GSS failures, per-node drift và rollback readiness.
- [ ] Các case C01–C60 hoặc coverage tương đương đã chạy và có evidence thực.

## Ghi nhớ

> **Kiểm tra tương thích Kerberos phải đi qua nhiều tầng: Java/JGSS, Spring Boot/Framework/Security, đúng Maven group/version Kerberos, Jakarta Servlet, keytab/KDC/SPN, browser HTTP Negotiate và local authorization.** Nhánh Security 6 dùng Kerberos extension 2.x tại `org.springframework.security.kerberos`; nhánh Security 7 dùng modules Kerberos tại `org.springframework.security`. **`javax.servlet` thay bằng `jakarta.servlet` nhưng `javax.security.auth` vẫn là Java SE.** Build/MockMvc pass không chứng minh ticket thật được xác minh. Chỉ đưa bản nâng cấp vào production sau khi real Kerberos ticket, local user/permission, session và từng replica cùng vượt qua QA.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): Java 17+ và Framework 6.1/Tomcat 10.1.
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java 17+ và Framework 6.2.
- [Spring Boot 4.1 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java 17+, Framework 7, Servlet 6.1+.
- [Spring Framework — Version Compatibility](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions): Java SE, javax/Jakarta generations.
- [Spring Security Kerberos 2.1.1 — Introduction](https://docs.spring.io/spring-security-kerberos/reference/2.1/introduction.html): tested JDK17, Security6.3, Framework6.1.
- [Spring Security Kerberos 2.2.0 — Introduction](https://docs.spring.io/spring-security-kerberos/reference/introduction.html): tested JDK17, Security6.5.1, Framework6.2.8.
- [Spring Security Kerberos 2.2.0 — Configuration](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): SPNEGO filter, provider, JAAS validator và UserDetailsService.
- [Maven Central — Kerberos Web 2.2.0](https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-web/2.2.0): Maven coordinates và transitive dependency baseline.
- [Spring Security 7.1 — Kerberos Introduction](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html): new dependency group `org.springframework.security` và JDK17 baseline.
- [Spring Security — SPNEGO Filter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): Jakarta Servlet filter/security context.
- [Spring Security — SpnegoEntryPoint Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html): HTTP 401 Negotiate, fallback support.
- [Spring Security — Servlet Filter Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): FilterChainProxy và SecurityFilterChain.
- [Spring Security — Getting Spring Security](https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html): dependency BOM/version management.
- [Spring Boot — Testing Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): ApplicationContext and MockMvc tests.
- [MIT Kerberos — klist](https://web.mit.edu/Kerberos/krb5-current/doc/user/user_commands/klist.html): keytab metadata và cảnh báo -K.
- [MIT Kerberos — kvno](https://web.mit.edu/Kerberos/krb5-current/doc/user/user_commands/kvno.html): real service-ticket decryption test.
- [MIT Kerberos — kadmin](https://web.mit.edu/KERBEROS/krb5-1.21/doc/admin/admin_commands/kadmin_local.html): ktadd key rotation hazards.
- [Oracle Java 17 — Java GSS-API Guide](https://docs.oracle.com/en/java/javase/17/security/java-generic-security-services-java-gss-api.html): JGSS/JAAS Kerberos.
