# Chọn OpenSAML 4 hoặc OpenSAML 5 theo phiên bản Spring Security

## 1. Mục tiêu của bài học

Trong **Spring Security - federation**, nhóm **Chuyển đổi và nâng cấp**, việc chọn **OpenSAML 4** hay **OpenSAML 5** không phải sở thích tùy ý của nhóm phát triển. Nó là quyết định tương thích giữa **phiên bản Spring Security**, các thành phần SAML mà Spring cung cấp, **dependency graph** thực tế của Maven/Gradle, Java runtime, Jakarta/Servlet APIs và mã tùy biến mà ứng dụng sử dụng.

Một cấu hình sai có thể gây:
- Build lỗi vì `OpenSaml4AuthenticationProvider` không còn ở Spring Security 7.
- Startup lỗi `NoClassDefFoundError`, `NoSuchMethodError`, `ClassNotFoundException` hoặc `ServiceConfigurationError` do **lẫn OpenSAML 4 và 5** hoặc các dependencies không đồng bộ.
- SAML login fail ở bước parse, build AuthnRequest, validate chữ ký, decrypt EncryptedAssertion, metadata hoặc Single Logout.
- Một bản nâng cấp “chạy được” nhưng vô tình bỏ các kiểm tra quan trọng như `InResponseTo`, `AudienceRestriction`, `Recipient`, chữ ký hoặc replay.
- Rủi ro bảo mật từ việc tiếp tục dùng một major version OpenSAML đã **end of life** mà không có bản sửa lỗi.

**Kết quả cần đạt:** sau bài này, bạn có thể đọc phiên bản thực tế của Spring Security, xác định major OpenSAML phù hợp, cấu hình build theo đúng nhánh, kiểm tra runtime classpath, chuyển các custom API từ `OpenSaml4XXX` sang `OpenSaml5XXX`, chạy regression tests và quyết định có an toàn để đưa bản nâng cấp lên production hay không.

> **Quy tắc nhanh:** **Spring Security 6.5** hỗ trợ chọn OpenSAML 4 (mặc định) hoặc OpenSAML 5 (opt-in); **Spring Security 7.x đã loại bỏ hỗ trợ OpenSAML 4, cần OpenSAML 5**. Các bản Spring Security khác phải đối chiếu tài liệu đúng version; đừng tự suy rằng mọi nhánh 6.x đều có cùng cơ chế chọn.

## 2. Ma trận quyết định theo phiên bản — nền tảng của mọi lựa chọn

| Spring Security trong ứng dụng | OpenSAML cần xem xét | Cơ chế mặc định/giới hạn | Khuyến nghị |
| --- | --- | --- | --- |
| **6.5.x** | **OpenSAML 4.x** hoặc **5.x** | Tài liệu 6.5 nói default transitive dependency là OpenSAML 4; `spring-security-config` chọn implementation tương ứng dựa trên phiên bản thư viện tìm thấy. | Dự án hiện hữu có thể tạm giữ 4 để giảm rủi ro khi chuyển đổi; **ưu tiên kiểm thử opt-in 5** trước khi sang Spring Security 7 vì 4 đã EOL. |
| **7.0.x / 7.1.x** | **OpenSAML 5.x** | Spring Security 7 **removed OpenSAML 4 support**; luồng mặc định dùng `OpenSaml5AuthenticationProvider`. | Dùng OpenSAML 5 theo dependency management được hỗ trợ; xóa custom `OpenSaml4XXX`, không tìm cách ép provider 4 chạy. |
| **6.4.x trở xuống** | Phụ thuộc vào **đúng patch/docs** | Không áp quy tắc 6.5/7 tự động; API, BOM, transitive dependencies và hỗ trợ major có thể khác. | Xác nhận tài liệu/Javadoc của chính release, rồi lên kế hoạch đi qua nhánh 6.5 hoặc đường nâng cấp đã hỗ trợ. |
| **Spring Security 5.x hoặc Spring Security SAML Extension cũ** | Legacy lineage riêng | Khác namespace, dependency, metadata, API và Servlet stack; không coi chỉ đổi OpenSAML jar là migration đầy đủ. | Trước tiên nâng cấp stack có kế hoạch, port sang `spring-security-saml2-service-provider`, xác thực Jakarta/Java/IdP compatibility. |

**Nguồn chính thức:** trang [OpenSAML Support của Spring Security 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html) xác nhận hỗ trợ hai major, default 4 và cách opt-in 5. Trang [What's New in Spring Security 7.0](https://docs.spring.io/spring-security/reference/7.0/whats-new.html) xác nhận **loại bỏ OpenSAML 4**. Trang [migrating SAML 2.0 to Security 7](https://docs.spring.io/spring-security/reference/6.5/migration-7/saml2.html) hướng dẫn đổi dependencies và những API tùy biến.

### 2.1. Một câu trả lời đúng phải chứa phiên bản cụ thể

Hỏi “Dùng Spring Boot 3 có dùng OpenSAML 5 được không?” là **chưa đủ thông tin**. Cần hỏi chính xác:
1. Spring Boot version và BOM/parent đang quản lý `spring-security-*` là gì?
2. **Spring Security artifact version cuối cùng** trong runtime classpath là bao nhiêu?
3. Java 17/21/25 nào đang được chạy, khác gì với JDK build?
4. Maven/Gradle đang resolve **các module `org.opensaml` nào và version nào**?
5. Có custom class trực tiếp tạo `OpenSaml4AuthenticationProvider`, `OpenSaml4AuthenticationRequestFactory`, OpenSAML XML objects hay không?
6. Ứng dụng sử dụng login, SLO, metadata, XML signing/decryption, dynamic registrations và custom validators ở mức nào?
7. Các thư viện khác như Apache WSS4J/Shibboleth có kéo OpenSAML major khác không?

**Không chọn theo tên artifact Maven đơn lẻ.** Ví dụ `opensaml-saml-api` tồn tại ở cả 4 và 5; phải kiểm **resolved version**, các module `opensaml-core` cũ và `opensaml-core-api`/`opensaml-core-impl` mới, cùng bytecode/API compatibility.

## 3. OpenSAML và Spring Security làm những việc gì?

**OpenSAML** là thư viện XML/SAML do hệ sinh thái Shibboleth cung cấp: SAML protocol/data objects, XML marshalling/unmarshalling, signatures, encryption, metadata và các utilities liên quan. Nó **không phải một Identity Provider hay Service Provider hoàn chỉnh**.

**Spring Security SAML 2.0 Service Provider** cung cấp:
- `Saml2WebSsoAuthenticationRequestFilter`: tạo/đưa AuthnRequest tới IdP.
- `Saml2WebSsoAuthenticationFilter`: tiếp nhận browser POST SAMLResponse.
- `Saml2AuthenticationTokenConverter`: kết hợp response với relying-party context.
- `RelyingPartyRegistration` và repository: issuer/SP entityID, ACS, IdP SSO URL, keys và metadata.
- `OpenSamlXAuthenticationProvider` và request/metadata helpers: kết nối Spring Security với API OpenSAML major tương ứng.
- Các phần SLO/metadata/session management tùy configuration.

Cấu hình tối thiểu cho phần **SAML SP** là dependency chính thức:

```xml
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-saml2-service-provider</artifactId>
</dependency>
```

Tên artifact đúng là **`spring-security-saml2-service-provider`**. Đừng lấy một dòng mô tả cũ có tên module `spring-security-saml` làm hướng dẫn copy/paste nếu nó không khớp phần dependency XML của reference docs. Không gán version Spring Security riêng khi Spring Boot BOM/parent đã quản lý trọn bộ, trừ khi có kế hoạch nâng cấp có kiểm soát.

### 3.1. Chuỗi xử lý SAML2 không tự thay đổi chỉ vì đổi OpenSAML major

```text
Browser --GET /saml2/authenticate/{registrationId}-->
  Spring SAML AuthnRequest filter
    -> load approved RelyingPartyRegistration
    -> create/sign/encode AuthnRequest
    -> redirect browser to IdP
IdP authenticates user and returns browser POST:
  POST /login/saml2/sso/{registrationId}
    -> Spring SAML response filter
    -> token converter resolves registration
    -> OpenSAML-specific provider validates signed/encrypted SAML
    -> SAML principal + local authorization mapping
    -> Spring Authentication/session
```

**OpenSAML major khác nhau chủ yếu tác động implementation/API/dependencies ở giữa luồng**, chứ không cho phép bỏ AuthnRequest correlation, destination, issuer, audience, conditions, signature và replay validation.

## 4. Vì sao tên class `OpenSaml4XXX` và `OpenSaml5XXX` quan trọng?

Trong Spring Security 6.5, tài liệu nêu quy tắc:
- `OpenSamlXXX`: tên lớp hoặc abstraction có thể áp dụng trên các major mà phiên bản Spring đó hỗ trợ.
- `OpenSaml4XXX`: implementation Spring phụ thuộc API OpenSAML 4.
- `OpenSaml5XXX`: implementation Spring phụ thuộc API OpenSAML 5.

Ví dụ:
- `OpenSaml4AuthenticationProvider` được dùng trong nhánh 4 của Spring Security còn hỗ trợ.
- `OpenSaml5AuthenticationProvider` là implementation của nhánh 5.
- Tùy phiên bản, còn có factory, metadata repository và helpers `OpenSaml4...`/`OpenSaml5...`.

**Chọn đúng JAR không đủ nếu custom code vẫn new lớp của major khác.**

### 4.1. Spring Security 6.5: cơ chế tự chọn class

Tài liệu 6.5 cho biết `spring-security-config` sẽ xác định implementation tương ứng với OpenSAML major đang hiện diện. Đây là hành vi **auto-selection cho configuration mặc định**, không phải lời hứa mọi `new OpenSaml4AuthenticationProvider()` tự biến thành OpenSAML 5 hoặc mọi extension point sẽ tự được port.

Khi tự tạo custom `AuthenticationProvider`, `Saml2AuthenticationRequestFactory`, decrypter, signature validator, marshaller, metadata parser, bạn có trách nhiệm:
- Đổi tên class/constructor theo API của major được chọn.
- Đổi type signatures cho callbacks, converters và token wrappers đã thay.
- Kiểm tra ordering validation/decryption.
- Bảo vệ core SAML validators mặc định khi mở rộng.

### 4.2. Spring Security 7: không còn “chọn 4 hay 5”

Ở Spring Security 7, bảng lựa chọn đã thu hẹp: **5.x** là nhánh OpenSAML được hỗ trợ. Nếu code/binary/library phụ thuộc Spring `OpenSaml4...`, ứng dụng **không thể giải quyết bằng cách thêm OpenSAML 4 jars** vì class Spring bên đó có thể đã bị loại.

Cần **port custom code** hoặc tạm giữ Spring Security 6.5 được hỗ trợ trong kế hoạch nâng cấp có thời hạn. Không triển khai 7 + 4 như một cấu hình chính thức hoặc dùng trick đổi package/classloader để né lỗi.

## 5. Kiểm kê phiên bản trước khi sửa file build

Trước khi chỉnh dependency, lập một bảng môi trường:

| Thông tin | Cách lấy | Giá trị cần ghi vào change request |
| --- | --- | --- |
| Spring Boot version | Parent POM/BOM, Gradle plugins | Version chính xác, không chỉ “Boot 3”. |
| Spring Security version | Dependency tree runtime | Version của `spring-security-config`, `spring-security-web`, `spring-security-saml2-service-provider`. |
| OpenSAML modules | Dependency tree runtime | Major/patch của `opensaml-saml-api`, `opensaml-saml-impl`, core và supporting modules. |
| Java build và runtime | `java -version`, `mvn -version` / Gradle toolchain | Cả JVM của build lẫn image/container runtime. |
| Servlet/Jakarta dependencies | Dependency tree và container | Không trộn `javax.servlet` và `jakarta.servlet` trái API. |
| XML Security libraries | Dependency tree | Apache Santuario, xmltooling, Shibboleth utilities. |
| Custom SAML API usage | Code search trong dự án được phép | Các `OpenSaml4...` classes, XMLObject builders, custom decrypters. |
| Authentication flows | Integration test inventory | SP-initiated, IdP-initiated theo policy, multi-IdP, signed requests, encrypted assertions, SLO. |
| IdP registrations | Approved metadata/config | EntityID, ACS, signature cert, algorithm, NameID/attributes mapping. |

**Lệnh Maven**, chạy từ thư mục ứng dụng khi được phép:

```bash
mvn -version
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.opensaml
mvn dependency:tree -Dincludes=net.shibboleth
mvn dependency:tree -Dverbose
mvn help:effective-pom
```

Một số plugin/version xử lý cú pháp `-Dincludes` khác nhau; nếu lọc không ra đủ, dùng `mvn dependency:tree` toàn bộ và tìm các nhóm. Phải kiểm **runtime artifact versions**, không chỉ phần declared dependencies.

**Lệnh Gradle**:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-saml-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
```

Trên Windows dùng `gradlew.bat`, PowerShell hoặc shell phù hợp. `dependencyInsight` giúp giải thích version conflict, constraints và dependency nào đã kéo một major ngoài dự kiến.

## 6. Java 17 và Jakarta: đừng nhầm “nâng OpenSAML” với “nâng JDK”

OpenSAML 5 thuộc **Shibboleth Java 17 platform**, yêu cầu **Java 17 trở lên**. OpenSAML 4 thuộc dòng Java 11 cũ và đã end of life. Spring Boot 3.x và 4.x cũng dùng Java 17 trở lên làm baseline (chi tiết version/runtime và servlet API phụ thuộc đúng nhánh).

**Những sai lầm thường gặp:**
- Dùng Maven chạy JDK 21 nhưng container production chạy Java 11: build có thể hoàn tất, runtime không đọc được class file.
- Chỉ đổi `sourceCompatibility` hoặc `--release` mà không đổi JVM thật dùng trong app image.
- Thấy `javax.servlet.ServletOutputStream` không có trong runtime Jakarta và cho rằng “Java 21 không hỗ trợ OpenSAML”.
- Giữ thư viện tích hợp pre-Jakarta cũ trong ứng dụng Boot 3/4 có `jakarta.servlet` dẫn đến `NoClassDefFoundError`.
- Đổi OpenSAML 4→5 nhưng vẫn dùng library integration/WSS4J version chỉ tương thích với 4.

### 6.1. Phân biệt namespace

| Hệ API | Dấu hiệu | Việc cần làm |
| --- | --- | --- |
| Java EE / pre-Jakarta | `javax.servlet.*` | Không giả định chạy với `jakarta.servlet.*` mà không có bước chuyển đổi tương thích. |
| Jakarta EE | `jakarta.servlet.*` | Đồng bộ Spring Framework/Boot/Security và container. |
| OpenSAML Java platform 4 | Java 11 platform, legacy support | Có thể tồn tại trong app cũ nhưng không phải nền tảng nâng cấp 7. |
| OpenSAML Java platform 5 | Java 17 platform | Phù hợp mục tiêu Spring Security 7, kiểm dependencies cùng major. |

**Không khuyên “hạ Java xuống 11 để giữ OpenSAML 4”** trong một ứng dụng Spring Security 6/7 mới: điều đó sai baseline platform và không xử lý end-of-life risk.

## 7. Nguồn Maven của Shibboleth và kiểm soát chuỗi cung ứng

Spring Security SAML2 SP dependency có các artifacts thuộc OpenSAML/Shibboleth. Tài liệu Spring Security cho biết thường cần thêm **Shibboleth Releases Repository** để phân giải dependency.

Maven:

```xml
<repositories>
  <repository>
    <id>shibboleth-releases</id>
    <name>Shibboleth Releases Repository</name>
    <url>https://build.shibboleth.net/maven/releases/</url>
    <releases><enabled>true</enabled></releases>
    <snapshots><enabled>false</enabled></snapshots>
  </repository>
</repositories>
```

Gradle Kotlin DSL:

```kotlin
repositories {
    mavenCentral()
    maven {
        url = uri("https://build.shibboleth.net/maven/releases/")
        mavenContent { releasesOnly() }
    }
}
```

**Các URL trên là public artifact repository được Spring docs tham chiếu, không phải metadata endpoint của IdP.** Tại doanh nghiệp có Artifactory/Nexus nội bộ, ưu tiên mirror đã duyệt, kiểm source/provenance, TLS, artifact signatures/checksums, repository allowlist và dependency lock.

**Không bật snapshot repos trong production** để giải quyết “Could not find OpenSAML”, không thêm repository tùy ý do một dependency đề nghị và không dùng version `LATEST`, `+`, snapshot để xác định build release. Nếu build chỉ thành công khi thêm một repository lạ, cần security review trước.

## 8. Phương án A: Spring Security 6.5 giữ OpenSAML 4 mặc định

Trong nhánh **6.5**, tài liệu chính thức ghi OpenSAML 4 là default. Nếu ứng dụng chưa có custom override hoặc dependencies gây conflict, chỉ cần SAML SP dependency:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
```

Điều kiện:
- BOM/parent đã quản lý **Spring Security 6.5 patch** tương ứng.
- Runtime dependency graph thực sự chỉ có OpenSAML 4 artifacts hợp lệ với Spring 6.5; không có 5.x lẫn.
- Mọi custom provider/factory dùng API 4 tương thích với đúng patch.
- Java/Servlet stack và IdP integration tests pass.
- Có kế hoạch di chuyển vì **OpenSAML 4 không còn được Shibboleth hỗ trợ**, không coi đây là trạng thái lâu dài.

**Khi nào giữ tạm?** Nếu doanh nghiệp đang ổn định ở 6.5, một số custom code dùng OpenSAML 4 chưa port, hoặc IdP integration yêu cầu kiểm thử dài. Việc giữ tạm cần **risk acceptance và migration deadline**, không bỏ qua advisory/cần nâng patch của Spring Security trong thời gian chuyển.

**Tuyệt đối không áp cách giữ 4 này cho Spring Security 7.x.**

## 9. Phương án B: Spring Security 6.5 chọn OpenSAML 5 trước khi lên 7

Mục tiêu tốt cho dự án chuẩn bị chuyển Spring Security 7 là **nâng OpenSAML major trước**, giảm số thay đổi cùng lúc. Spring Security 6.5 có thể chọn implementation `OpenSaml5XXX` khi dependency graph chỉ có OpenSAML 5 hợp lệ.

Tài liệu Spring Security 6.5 hướng dẫn loại các transitive `org.opensaml` có major 4 rồi khai báo **OpenSAML 5 API và implementation**. Ví dụ dưới đây minh họa cách ghim **OpenSAML 5.2.3** — một phiên bản release được Shibboleth Maven repository ghi nhận năm 2026 — thay vì sao chép ví dụ docs cũ dùng 5.1.2. **Phải kiểm lại advisory và test compatibility của combo cụ thể trước release**; version ở đây là ví dụ build pin, không phải cam kết mọi project sẽ chạy được chỉ sau khi paste.

### 9.1. Maven override có kiểm soát

```xml
<properties>
  <opensaml.version>5.2.3</opensaml.version>
</properties>

<dependencies>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
    <exclusions>
      <exclusion>
        <groupId>org.opensaml</groupId>
        <artifactId>*</artifactId>
      </exclusion>
    </exclusions>
  </dependency>
  <dependency>
    <groupId>org.opensaml</groupId>
    <artifactId>opensaml-saml-api</artifactId>
    <version>${opensaml.version}</version>
  </dependency>
  <dependency>
    <groupId>org.opensaml</groupId>
    <artifactId>opensaml-saml-impl</artifactId>
    <version>${opensaml.version}</version>
  </dependency>
</dependencies>
```

**Phải đặt trong POM của ứng dụng đã có parent/BOM, Java và repositories**, không phải một POM hoàn chỉnh. Nếu corporate BOM hoặc transitive modules vẫn ép các thư viện `org.opensaml` khác về 4.x, phải điều chỉnh dependency management/constraints đúng phạm vi và **verify toàn bộ runtime tree**. Không chỉ nhìn hai direct dependencies.

Ở Maven, ký hiệu `<artifactId>*</artifactId>` trong exclusion của tài liệu cho phép loại dependencies `org.opensaml` do Spring SAML module kéo theo; nó **không xóa tất cả OpenSAML trong project nếu thư viện khác còn kéo chúng từ một nhánh khác**. Nếu build vẫn có 4 và 5 cùng lúc, lần theo dependency tree và sửa tại đúng nguồn; không dùng exclusion toàn cục không hiểu tác dụng.

### 9.2. Tại sao phải loại `opensaml-core` cũ?

Một thay đổi cấu trúc trong OpenSAML 5 là module **`opensaml-core` của 4.x được tách thành `opensaml-core-api` và `opensaml-core-impl`**. Tài liệu Spring Security 6.5 yêu cầu sửa dependency graph khi chọn 5 vì thay đổi này.

Với 5.x mong đợi một graph nhất quán gồm:
- `org.opensaml:opensaml-saml-api:5.x`
- `org.opensaml:opensaml-saml-impl:5.x`
- `org.opensaml:opensaml-core-api:5.x`
- `org.opensaml:opensaml-core-impl:5.x`
- Các module bổ trợ và XML Security/Shibboleth dependencies tương thích do BOM/metadata quản lý.

**Dấu hiệu đáng ngờ:** `opensaml-saml-api:5.2.3` đứng cùng `opensaml-core:4.x` hoặc `opensaml-saml-impl:4.x`. Build có thể compile phần source không chạm API xung đột, nhưng runtime SAML login chết khi class loader thực sự sử dụng method khác signature.

### 9.3. Không nhầm Spring Security auto-selection với phiên bản tự động

Sau khi thay JARs:
- Spring 6.5 config có thể chọn `OpenSaml5` components **nếu dependencies đúng**.
- Custom bean do ứng dụng tự new vẫn phải đổi sang 5.
- Một Spring dependency patch có thể có thay đổi API/support cụ thể; cần chạy tests và xem runtime logs.
- Nếu package trùng nhưng class ABI thay, **mã compile lần này không đảm bảo artifact cũ trong image đã bị thay**.
- Đặc biệt kiểm CI cache, fat JAR packaging, Docker multi-stage image, runtime mounts và BOM overrides.

## 10. Gradle: chọn OpenSAML 5 với constraints và exclusion rõ ràng

Với Gradle Kotlin DSL trong một app đang dùng **Spring Security 6.5**, có thể diễn đạt cùng mục tiêu:

```kotlin
repositories {
    mavenCentral()
    maven {
        url = uri("https://build.shibboleth.net/maven/releases/")
        mavenContent { releasesOnly() }
    }
}

dependencies {
    implementation("org.springframework.security:spring-security-saml2-service-provider") {
        exclude(group = "org.opensaml", module = "opensaml-core")
    }

    constraints {
        implementation("org.opensaml:opensaml-core-api:5.2.3")
        implementation("org.opensaml:opensaml-core-impl:5.2.3")
        implementation("org.opensaml:opensaml-saml-api:5.2.3")
        implementation("org.opensaml:opensaml-saml-impl:5.2.3")
    }

    implementation("org.opensaml:opensaml-saml-api:5.2.3")
    implementation("org.opensaml:opensaml-saml-impl:5.2.3")
}
```

**Đây là ví dụ định hướng theo cấu trúc Gradle trong Spring docs, phải review resolved dependencies**; nếu thư viện khác còn ép OpenSAML 4, exclusion chỉ tại module `opensaml-core` của dependency trên chưa đủ. `constraints` có thể ảnh hưởng chọn version, nhưng không thay thế việc kiểm graph. Với corporate platform/BOM, ưu tiên một nơi quản lý version OpenSAML duy nhất.

Lệnh sau nâng cấp:

```bash
./gradlew clean test
./gradlew dependencyInsight --dependency opensaml-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-saml-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-saml-impl --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Nếu runtime graph vẫn có core 4, saml 4 hoặc XML/Santuario không tương thích, **chưa được coi là migration thành công**. Không sử dụng `configurations.all { exclude group="org.opensaml" }` bừa bãi vì nó có thể loại cả OpenSAML 5 mà bạn cần.

## 11. Phương án C: Spring Security 7.x dùng OpenSAML 5

Với **Spring Security 7**, lựa chọn đúng là **OpenSAML 5**. Spring Security 7.0 What's New nêu rõ đã **removed Open SAML 4 support**; reference SAML2 Login mô tả `OpenSaml5AuthenticationProvider` là provider mặc định.

Thông thường hãy ưu tiên **Spring Boot compatible BOM** và dependency tiêu chuẩn, không copy nguyên các exclusions dành cho việc opt-in 5 trong Spring Security 6.5:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
```

Không cần thêm một `OpenSaml4AuthenticationProvider` bean để “giữ logic cũ”. Nếu bạn đã copy override `org.opensaml` từ nhánh 6.5, **đánh giá xóa override không còn cần thiết** và để Boot/Spring platform chọn bộ dependencies được kiểm thử; chỉ ghim OpenSAML 5 patch riêng khi cần advisory fix và đã kiểm tương thích.

### 11.1. Spring Boot 4 / Spring Security 7 không chỉ thay mỗi POM

Đường nâng từ Boot 3 + Security 6 sang Boot 4 + Security 7 còn bao gồm:
- Java 17 baseline; Jakarta Servlet/EE platform version mới.
- Spring Framework 7.x và thay đổi cấu hình/lifecycle.
- Các API Spring Security 7 đã remove/deprecate, ví dụ thay đổi `AssertingPartyDetails` → `AssertingPartyMetadata`.
- Thay đổi xử lý URI match, response validation, principal/attributes và SLO tùy customizations.
- Module split và dependency transitive thay đổi theo Spring Boot 4.
- Các customizations dùng class của OpenSAML 4 cần port.

**Không chạy Spring Security 7 trên một Spring Framework/Boot version không tương thích chỉ vì compile được một vài classes.** Theo [migrating to 7](https://docs.spring.io/spring-security/reference/migration/), ưu tiên đi qua 6.5 và cập nhật các bản maintenance của Boot 4/Security 7 trong migration path được hỗ trợ.

## 12. Chuyển custom provider: từ OpenSaml4... sang OpenSaml5...

Trong project có custom SAML provider, thường sẽ tìm thấy những import như:

```java
import org.springframework.security.saml2.provider.service.authentication.OpenSaml4AuthenticationProvider;
```

Ở Spring Security 7, import này **không còn phù hợp**, và code phải chuyển sang API 5:

```java
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider;
```

**Không dừng ở đổi tên import.** Những converter, validator và decrypter callbacks có thể dùng token types/method signatures khác. Các ví dụ ở phần 6.5 docs hoặc Javadoc của một patch chưa chắc compile nguyên trạng trên 7.1.

### 12.1. Mảnh cấu hình provider trong Spring Security có OpenSAML 5

Ví dụ sau là **mảnh Spring Boot/Spring Security Servlet**, không tự chạy như Java SE; phải có RelyingPartyRegistration và đúng version Spring Security:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider;
import org.springframework.security.web.SecurityFilterChain;

public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        OpenSaml5AuthenticationProvider provider =
            new OpenSaml5AuthenticationProvider();

        http.authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated())
            .saml2Login(saml2 ->
                saml2.authenticationManager(new ProviderManager(provider)));

        return http.build();
    }
}
```

**Khi không cần tùy biến, dùng `saml2Login(Customizer.withDefaults())` và để Spring cấu hình provider mặc định**. Mảnh code trên hữu ích để chỉ rõ `OpenSaml5AuthenticationProvider`, nhưng không tự thêm `RelyingPartyRegistrationRepository`, IdP certificates, secrets, claims mapping hay SLO. Không tạo provider mới chỉ để ép phiên bản khi Spring đã auto-config đúng.

### 12.2. OpenSAML initialization

Trong các custom components có gọi trực tiếp OpenSAML objects, Spring docs hướng dẫn dùng:

```java
static {
    OpenSamlInitializationService.initialize();
}
```

Đây là đoạn dùng class từ **Spring Security SAML support** với import phù hợp, không phải Java SE demo tự chạy. Cách này khác việc tự tùy ý gọi `org.opensaml.core.config.InitializationService.initialize()` nhiều lần hoặc thao tác XMLObjectProviderFactory trước initialization.

**Quan trọng:** việc khởi tạo đúng không sửa incompatibility của mixed major JARs. Một `OpenSamlInitializationService` chạy thành công không chứng minh signature validators/cipher suites ở end-to-end flow hoạt động.

## 13. Các thay đổi tùy biến cần rà soát khi sang OpenSAML 5

Không phải mọi hệ thống chỉ cần default SSO flow. Các dự án thường tùy biến:

| Tầng | Những gì cần kiểm | Test chứng minh |
| --- | --- | --- |
| AuthnRequest factory | XML Object builders, NameIDPolicy, ForceAuthn, signing, RelayState. | Request hợp lệ đúng IdP/ACS/algorithm. |
| SAML response provider | `OpenSaml4AuthenticationProvider` → `OpenSaml5AuthenticationProvider`. | Signed response pass, modified response fail. |
| Response validators | Issuer, Destination, InResponseTo, Status, NameID requirements. | Wrong Issuer/ACS/InResponseTo bị reject. |
| Assertion validators | Conditions, audience, recipient, SubjectConfirmationData, clock skew. | Expired/wrong audience/replay fail. |
| Encryption/decryption | EncryptedAssertion, EncryptedAttribute, EncryptedID, decrypter strategies. | Sign-then-encrypt combinations đúng. |
| Principal conversion | NameID, attributes, local account mapping, authorities. | Principal/roles không đổi hoặc thay có chủ đích. |
| RelyingPartyRegistration | `AssertingPartyDetails` API và metadata API mới. | Multi-IdP resolution, correct verification cert. |
| SAML metadata parsing | XML schema, certificates, algorithm/endpoint bindings. | Trusted metadata only, reject unsigned tampering. |
| SAML Single Logout | LogoutRequest/Response signing, SessionIndex, session correlation. | Valid SLO completes, forged logout rejected. |
| XML ParserPool | Entity limits, XXE, encoding, request size constraints. | Oversized/XML abuse bị từ chối an toàn. |
| Test fixtures | XML generated từ OpenSAML 4 objects không phù hợp 5 API. | Tests compile với full major 5 and expected XML. |
| Build/test tooling | Classpath, Gradle/Maven plugins, test harness class loaders. | CI, fat JAR và runtime image đều nhất quán. |

**Custom `Saml2ResponseValidator` hoặc `Saml2AuthenticationConverter` không được vô tình bỏ default validators.** Kiểm code và Javadoc của release đang chạy; **nối thêm validation** thường an toàn hơn thay thế toàn bộ, trừ khi có đặc tả/threat model rõ ràng.

### 13.1. Thay đổi kiểm tra NameID và thứ tự validation trong Spring Security 7

Spring Security 6.5 migration guide mô tả chuyển đổi thứ tự xử lý response khi chuẩn bị 7:
1. Verify Response signature nếu có.
2. Decrypt Response.
3. Validate assertions (verify signature, decrypt, conditions).
4. Validate Response fields như Destination/Issuer sau xử lý assertions.

Trong một số trường hợp Spring Security 6 kiểm Response fields trước assertion fields; Spring Security 7 đổi thứ tự, chuyển xử lý một số validation liên quan NameID khỏi bước mặc định mà custom response converter trước đây kỳ vọng.

**Nếu custom principal converter không yêu cầu NameID**, behavior mới có thể hữu ích. Nhưng nếu business identity mapping **bắt buộc NameID**, custom converter/validator phải tự xác minh sự hiện diện và giá trị hợp lệ thay vì mặc định kỳ vọng bước cũ đã thực hiện.

Spring Security 6.5 migration guide có option thử behavior 7 trước:

```java
OpenSaml5AuthenticationProvider provider =
    new OpenSaml5AuthenticationProvider();
provider.setValidateResponseAfterAssertions(true);
```

Đoạn này **là API chuẩn bị migration trong Security 6.5 theo tài liệu**; **không giả định method còn tồn tại hoặc cần gọi trong mọi bản 7.x**. Trên Spring Security 7, phải đối chiếu Javadoc/current API và test behavioral expectations.

### 13.2. Decryption order là ranh giới bảo mật

OpenSAML/Spring cần xử lý chính xác các trường hợp:
- Response được ký, chứa encrypted assertion.
- Assertion được ký rồi chứa encrypted attribute.
- Assertion được mã hóa và ký theo các combination của IdP.

`OpenSaml5AuthenticationProvider` có hai decryption strategies:
- **Response elements decrypter**: cho encrypted elements ở cấp Response, ví dụ EncryptedAssertion.
- **Assertion elements decrypter**: cho encrypted elements trong Assertion, ví dụ EncryptedAttribute/EncryptedID.

**Không giải mã các phần của signed Assertion trước khi xác minh chữ ký theo thứ tự mà provider yêu cầu**, vì có thể thay đổi XML/canonicalization và làm chữ ký invalid, hoặc tệ hơn là lẫn trust boundary. Trang [Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) có ví dụ tùy biến hai loại decrypter riêng.

### 13.3. Với SLO và request binding

Khi đổi major, kiểm thử:
- Signed AuthnRequest HTTP-Redirect/POST, Signature algorithms, canonicalization.
- IdP SSO Binding URL và RelayState encoding.
- ACS HTTP POST, `InResponseTo` và request repository.
- LogoutRequest/LogoutResponse XML signing/verification, SLO correlation và local sessions.
- SAML metadata generation, signed metadata trust, certificate rotation.
- IdP-initiated nếu policy cho phép, không tự bật unsolicited SSO vì migration.

**Một SAML login happy-path không chứng minh SLO hoặc encrypted assertions còn đúng.**

## 14. Dependency conflict thực tế: nhìn vào nhóm artifact, không chỉ lỗi cuối

### 14.1. Kiểu conflict 1: có cả OpenSAML 4 và 5

```text
spring-security-saml2-service-provider:6.5.x
  -> opensaml-saml-api:4.x

application
  -> opensaml-saml-impl:5.x
  -> opensaml-core-impl:5.x

RESULT: mixed major / incompatible API risk
```

Maven/Gradle có thể chọn một version cho trùng coordinates nhưng vẫn để module từ major khác nằm chung runtime. **Bộ phận classloader chọn được một class không có nghĩa toàn bộ OpenSAML APIs tương thích**.

**Khắc phục:** kiểm `dependency:tree`/`dependencyInsight`, exclude đúng transitive 4, đưa full 5 dependency set cùng version và chạy clean full build + SAML integration tests.

### 14.2. Kiểu conflict 2: thư viện thứ ba kéo OpenSAML cũ

Một thư viện WS-Security có thể dùng OpenSAML 4 để xác minh SAML assertions trong SOAP, trong khi app Spring SAML login dùng 5. Ví dụ Apache WSS4J 3.x có lineage OpenSAML 4, WSS4J 4.x chuyển sang OpenSAML 5/Java 17.

**Không ép toàn bộ project vào một graph trộn hỗn hợp.** Cần lựa chọn compatible version của thư viện tích hợp, tách module/process nếu cần hoặc trì hoãn nâng Spring 7 có kiểm soát. Một exclusion ở Spring SAML module không giải quyết dependency do WSS4J khác kéo vào.

### 14.3. Kiểu conflict 3: deploy fat JAR khác runtime tree đã kiểm

- CI build có bản OpenSAML 5, container image vẫn lấy artifact cũ do cache.
- `BOOT-INF/lib/` chứa cả jar 4 và 5 hoặc jar không đúng patch.
- Application server shared classloader nạp OpenSAML 4 trước classpath của app.
- IDE chạy với classpath khác Maven test.
- Một dependency shade/relocate classes không được xét trong SBOM.
- Partial rolling upgrade để các pods khác Spring Security/OpenSAML major trong thời gian SSO callback.

**Biện pháp:** xem resolved dependencies, inspect packaged artifact, build image reproducible, SBOM, compare build hash/dependency graph và test startup cùng image/container dùng production.

### 14.4. Kiểu conflict 4: JAXB/Jakarta và XML Security

Một lỗi `javax.servlet.*` missing hoặc `jakarta.*` mismatch thường xuất phát từ **Servlet stack** chứ không phải “OpenSAML không chạy trên JDK mới”. Những lỗi `org.apache.xml.security` có thể đến từ XML Security library không khớp. Phải truy ngược **class name, declaring artifact, dependency edge và deployed classpath**.

**Không chữa bằng cách thả từng JAR từ Internet vào `lib/`** cho tới khi startup hết lỗi; cách đó có thể để nhiều phiên bản XML signature implementation và lỗ hổng parser.

## 15. Bảo mật: EOL và advisory phải tham gia quyết định

Shibboleth ghi OpenSAML 5 là major Java hiện hành dựa trên Java 17; các major trước đã **end of life**. Mục tiêu migration không chỉ là tương thích API mà còn là **còn được nhận security fixes**.

Các đánh giá cần có:
- Có advisory nào ảnh hưởng parser, XML signature, encryption/decryption, SAML inflate, resource exhaustion hoặc unsafe deserialization?
- Spring Security patch version đang chạy đã có security fixes tương ứng chưa?
- Bản OpenSAML 5 patch đang khóa có nằm trong phiên bản hỗ trợ/được cập nhật không?
- Shibboleth artifact repository và Spring Security version được duyệt trong doanh nghiệp chưa?
- JDK XML parser properties và request-body limits có bảo vệ DoS không?
- Có kiểm `SubjectConfirmation`, Audience, Recipient, Destination, replay, signature policy và certificate trust sau nâng cấp không?

**Một mốc cụ thể:** [OpenSAML security advisory 13/05/2026](https://shibboleth.net/pipermail/announce/2026-May/000384.html) nói OpenSAML **5.2.2** bổ sung mặc định parser limits chống một dạng DoS. Vì vậy ví dụ cũ trong docs 6.5 dùng **5.1.2** không nên bị sao chép như “bản vá bảo mật được khuyên dùng cho 2026”. Ví dụ 5.2.3 ở trên là phiên bản release đã xác minh trong Shibboleth repository; luôn đánh giá security advisory và compatibility mới hơn trước phát hành.

[Spring Security Releases 09/06/2026](https://spring.io/blog/2026/06/09/spring-security-releases-2026-06/) còn công bố các CVE liên quan đến SAML inflation/decryption và những phần khác của Security. **Không đồng nhất fix OpenSAML với fix Spring Security**: cả hai tầng đều phải được cập nhật theo advisory và dependency policy.

### 15.1. Checklist kiểm thư viện theo ngày release

```text
[ ] Spring Security selected supported maintenance line
[ ] OpenSAML major matches Spring Security line
[ ] OpenSAML minor/patch reviewed against Shibboleth advisories
[ ] Spring Security patch reviewed against Spring advisories
[ ] Java and servlet/Jakarta platforms compatible
[ ] No mixed OpenSAML 4/5 modules in runtime
[ ] Signature, encryption, replay and XML parsing tests pass
[ ] SBOM, artifact provenance and checksum verified
[ ] Staged canary and emergency rollback strategy approved
```

**Rollback an toàn** khác “rollback lên thư viện đã bị lỗ hổng nghiêm trọng”. Nếu chỉ có image cũ đã biết vulnerable, cần đánh giá containment/temporary disable SAML login thay vì tự động tái kích hoạt rủi ro.

## 16. Lộ trình nâng cấp hai giai đoạn giảm rủi ro

### Giai đoạn A: chuẩn bị trên Spring Security 6.5

1. Chốt Boot/Spring Security **6.5 maintenance patch** được duyệt.
2. Chạy toàn bộ SAML integration tests với OpenSAML 4 hiện có để tạo baseline.
3. Kiểm custom imports `OpenSaml4`, OpenSAML XML builders, validators, decryptors và metadata utilities.
4. Thay dependencies cho OpenSAML 5 theo hướng dẫn 6.5 và lock compatible patch.
5. Port custom code sang `OpenSaml5` APIs, giữ validation semantics.
6. Kiểm classpath/repository/fat jar/runtime Java 17.
7. Test SSO/SLO/encryption/metadata, multi-IdP, tampered assertions, wrong audience, replay.
8. Canary với IdP test, đo login success/rejection reason codes; không đổi IdP config và SAML library cùng lúc nếu không cần.
9. Chốt evidence: dependency tree, artifacts, tests, security sign-off.

**Gate giai đoạn A:** Spring Security 6.5 + OpenSAML 5 chạy được trên cùng môi trường với các negative tests chính xác. Điều này giúp tách lỗi **nâng OpenSAML major** khỏi lỗi **nâng Spring Security major**.

### Giai đoạn B: chuyển Spring Security 7

1. Đối chiếu chính thức migration guide của đúng Spring Security 7 patch và Boot compatible line.
2. Nâng Spring Boot/Framework/Security theo supported matrix, không nâng lẻ module Security.
3. Xóa các tùy biến Java/OpenSAML 4 còn sót, kiểm class removed/deprecated.
4. Đánh giá thay đổi `AssertingPartyDetails` → `AssertingPartyMetadata`.
5. Đánh giá response validation order và custom NameID/Principal mapping.
6. Đánh giá `Saml2WebSsoAuthenticationFilter` khi không có RelyingPartyRegistration, tránh redirect loop.
7. Chạy lại unit/integration/contract tests, SAML SLO, metadata, migration data/caches.
8. Test rollout giữa các pods/instances và rollback config/IdP registration.
9. Cập nhật dashboards, SBOM, change control và incident response.
10. Promote khi mọi canary/negative tests pass.

**Không nên gộp đồng thời**: OpenSAML major, Boot major, IdP certificate rotation, IdP metadata refresh algorithm và tenant role mapping trong cùng một thay đổi nếu có thể tránh. Một bước phá nhiều ranh giới sẽ rất khó quy root cause khi login fail.

## 17. Java 17 runnable: trình kiểm tra chính sách chọn OpenSAML

Ví dụ sau **chạy độc lập bằng Java 17**, không dùng Spring/OpenSAML thật. Nó mô phỏng các quy tắc đã xác nhận ở trên và phân loại một bản kê dependency phiên bản. Các boolean biểu thị **kết quả kiểm Maven/Gradle runtime graph**, không phải dữ liệu tự động đọc từ classpath. Mô hình **không thay thế** dependency audit hoặc integration test.

Tạo tệp **`OpenSamlCompatibilityAdvisor.java`**:

```java
public final class OpenSamlCompatibilityAdvisor {

    record Stack(
        int springMajor,
        int springMinor,
        int javaVersion,
        boolean hasOpenSaml4,
        boolean hasOpenSaml5,
        boolean legacyCore4,
        boolean customOpenSaml4Code) {}

    static String decide(Stack s) {
        if (s.javaVersion() < 17) {
            return "BLOCK_JAVA_BELOW_17";
        }
        if ((s.hasOpenSaml4() && s.hasOpenSaml5())
                || (s.legacyCore4() && s.hasOpenSaml5())) {
            return "BLOCK_MIXED_OPEN_SAML";
        }
        if (s.springMajor() >= 7) {
            if (s.hasOpenSaml4()) {
                return "BLOCK_OPEN_SAML_4_REMOVED";
            }
            if (!s.hasOpenSaml5()) {
                return "BLOCK_OPEN_SAML_5_MISSING";
            }
            if (s.customOpenSaml4Code()) {
                return "BLOCK_CUSTOM_OPEN_SAML_4_CODE";
            }
            return "READY_SPRING_7_OPEN_SAML_5";
        }
        if (s.springMajor() == 6 && s.springMinor() == 5) {
            if (s.hasOpenSaml5()) {
                if (s.customOpenSaml4Code()) {
                    return "BLOCK_CUSTOM_OPEN_SAML_4_CODE";
                }
                return "READY_6_5_OPEN_SAML_5_OPT_IN";
            }
            if (s.hasOpenSaml4()) {
                return "LEGACY_6_5_OPEN_SAML_4_DEFAULT";
            }
            return "BLOCK_OPEN_SAML_MISSING";
        }
        return "VERIFY_PINNED_SPRING_DOCUMENTATION";
    }

    static void show(String label, Stack stack) {
        System.out.println(label + "=" + decide(stack));
    }

    public static void main(String[] args) {
        show("S65_DEFAULT",
             new Stack(6, 5, 17, true, false, true, false));
        show("S65_OPT_IN",
             new Stack(6, 5, 17, false, true, false, false));
        show("S71_NORMAL",
             new Stack(7, 1, 17, false, true, false, false));
        show("S71_WITH_4",
             new Stack(7, 1, 17, true, false, true, false));
        show("MIXED_MAJORS",
             new Stack(7, 1, 17, true, true, true, false));
        show("LEGACY_CORE_4",
             new Stack(6, 5, 17, false, true, true, false));
        show("CUSTOM_PROVIDER_4",
             new Stack(6, 5, 17, false, true, false, true));
        show("JAVA_11",
             new Stack(7, 1, 11, false, true, false, false));
        show("MISSING_5",
             new Stack(7, 0, 17, false, false, false, false));
        show("OTHER_SPRING",
             new Stack(6, 4, 17, true, false, true, false));
    }
}
```

Biên dịch/chạy:

```bash
javac OpenSamlCompatibilityAdvisor.java
java OpenSamlCompatibilityAdvisor
```

**Stdout chính xác:**

```text
S65_DEFAULT=LEGACY_6_5_OPEN_SAML_4_DEFAULT
S65_OPT_IN=READY_6_5_OPEN_SAML_5_OPT_IN
S71_NORMAL=READY_SPRING_7_OPEN_SAML_5
S71_WITH_4=BLOCK_OPEN_SAML_4_REMOVED
MIXED_MAJORS=BLOCK_MIXED_OPEN_SAML
LEGACY_CORE_4=BLOCK_MIXED_OPEN_SAML
CUSTOM_PROVIDER_4=BLOCK_CUSTOM_OPEN_SAML_4_CODE
JAVA_11=BLOCK_JAVA_BELOW_17
MISSING_5=BLOCK_OPEN_SAML_5_MISSING
OTHER_SPRING=VERIFY_PINNED_SPRING_DOCUMENTATION
```

### 17.1. Phân tích output

- `S65_DEFAULT`: đúng behavior default 6.5, nhưng EOL risk cần migration plan.
- `S65_OPT_IN`: 6.5 có thể dùng 5 nếu graph và custom code đúng.
- `S71_NORMAL`: 7.x dùng OpenSAML 5 là lựa chọn hợp lệ về major.
- `S71_WITH_4`: 7.x + 4 không được hỗ trợ.
- `MIXED_MAJORS`: ứng dụng có cả 4 và 5, nên chặn rollout.
- `LEGACY_CORE_4`: core 4 xuất hiện cùng 5 dù dependency chính đã đổi.
- `CUSTOM_PROVIDER_4`: bytecode/code custom vẫn gắn Spring `OpenSaml4...`.
- `JAVA_11`: Java 11 không đáp ứng baseline.
- `MISSING_5`: Spring 7 không có OpenSAML 5 trong classpath.
- `OTHER_SPRING`: cần mở tài liệu đúng nhánh, không tự vận dụng ma trận 6.5.

**Giới hạn quan trọng:** chữ “READY” chỉ nói **đạt điều kiện chọn major sơ bộ**; nó **không chứng minh CVE-free**, signature correct, library ABI hợp, IdP trust đã thiết lập, hay mọi module hỗ trợ cùng patch. Những boolean không được lấy từ HTTP input và chương trình không có khả năng scan Maven project. Đây là bài thực hành logic decision, không phải ứng dụng bảo mật triển khai.

## 18. Thực hiện test sau khi đổi major — không chỉ build xanh

| Nhóm test | Positive case | Negative / regression case |
| --- | --- | --- |
| Build/dependency | Clean Maven/Gradle build, runtime chỉ một major OpenSAML. | Inject OpenSAML 4/5 conflict và xác nhận gate chặn. |
| Startup | Spring Boot context start, SAML provider và registrations tạo được. | Missing XML core/helper hoặc classloader mismatch phải fail rõ. |
| AuthnRequest | SP tạo request đúng IdP/ACS, signed theo policy. | Invalid IdP/registration hoặc malformed request bị reject. |
| SAMLResponse POST | Trusted IdP trả response hợp lệ, login tạo Authentication. | Modified XML/signature bị reject. |
| Issuer | Expected IdP issuer khớp. | Wrong issuer/unknown IdP không được tự thêm trust. |
| Audience | Assertion dành đúng SP EntityID. | Audience thuộc service khác bị reject. |
| Destination/Recipient | ACS public URL khớp. | Wrong scheme/host/path bị reject. |
| InResponseTo | Response gắn đúng request/session. | Mismatch/no pending AuthnRequest bị reject theo SP-initiated policy. |
| Replay | Một assertion dùng một lần. | Post lại same assertion/response bị chặn ở multi-node. |
| Conditions | NotBefore/NotOnOrAfter hợp lệ. | Expired/future assertion fail theo skew. |
| XML parsing | Valid signed SAML XML parse bình thường. | XXE, oversized XML, dangerous compression bị giới hạn. |
| EncryptedAssertion | SP decryption private key đúng, signed response hợp lệ. | Wrong key/ciphertext bị reject, không fallback plaintext. |
| EncryptedAttribute | Decrypt đúng thứ tự với signature validation. | Decrypt pre-signature làm sai xác thực hoặc bị reject. |
| NameID/principal | Expected NameID/attributes được map đúng. | Missing NameID được xử lý theo business security policy, không NPE. |
| Authorities | Verified group/tenant map tới roles đúng. | Admin role không tự xuất hiện từ untrusted attribute. |
| SP metadata | EntityID/ACS/signing and encryption certs như contract. | Private key không lộ, unexpected metadata cert không auto-trust. |
| SLO | Signed LogoutRequest/Response và SessionIndex đúng. | Forged logout hoặc wrong SessionIndex bị reject. |
| Multi-IdP | Mỗi registration dùng đúng trusted cert/issuer. | Cert/Issuer của IdP A không được dùng nhận IdP B. |
| Session/cookie | Browser POST SAMLResponse có state phù hợp. | SameSite, multi-tab, pod failover không gây bypass. |
| Rollout | Canary containers cùng version, metrics stable. | Old pod/new pod state mix được phát hiện; rollback policy safe. |

**SAMLResponse được ký hợp lệ chưa đủ để tạo một local admin user.** Sau cryptographic validation còn local account status, tenant mapping, RBAC và session fixation protection.

### 18.1. Metrics quan trọng khi nâng cấp

```text
saml_login_success_total{registration,build}
saml_login_failure_total{registration,reason,build}
saml_signature_rejected_total{registration}
saml_audience_rejected_total{registration}
saml_in_response_to_mismatch_total{registration}
saml_assertion_decrypt_failed_total{registration}
saml_assertion_replay_rejected_total{registration}
saml_metadata_refresh_failed_total{registration}
saml_slo_error_total{registration}
```

Không ghi raw `SAMLResponse`, `SAMLRequest`, private keys, NameID, Session ID, RelayState hoặc user identifiers làm metric labels. Gắn **build version, OpenSAML major, config version** theo labels có cardinality được kiểm soát để xác định lỗi sau rollout.

## 19. Chẩn đoán lỗi khi runtime không tương thích

| Triệu chứng | Lớp nguyên nhân | Cách xác minh và sửa |
| --- | --- | --- |
| `ClassNotFoundException: OpenSaml4AuthenticationProvider` | Spring Security 7 đã remove API 4. | Tìm custom import/bean, port sang OpenSaml5. |
| `NoClassDefFoundError: org/opensaml/core/...` | Thiếu OpenSAML 5 core API/impl hoặc mixed classpath. | Dependency tree, fat jar, version alignment. |
| `NoSuchMethodError` trong OpenSAML classes | API/binary incompatible versions. | Kiểm declaring artifact + resolved/runtime jar; không thêm random JAR. |
| `ClassNotFoundException: javax.servlet...` | Legacy servlet dependency trong Jakarta runtime. | Chuyển compatible library/Servlet namespace, không hạ Java. |
| Không tìm được `opensaml-saml-impl` | Repository/build dependency issue. | Thêm Shibboleth releases hoặc corporate approved mirror, không snapshot tùy ý. |
| Ứng dụng vẫn dùng OpenSaml4 bean ở 6.5 opt-in 5 | Custom code không được auto migrate. | Đổi bean/import/callback API, chạy compile và tests. |
| SAMLResponse fails signature | Verification cert/IdP config, algorithm or parsing difference. | So issuer/trust cert, signed XML, version; không disable signature. |
| EncryptedAssertion fail decrypt | Wrong SP key/algorithm/decrypter order. | Test response-level vs assertion-level decrypter. |
| Test NameID failed sau chuyển 7 | Response validation/converter behavior đổi. | Review custom NameID policy và response authentication converter. |
| SAML ACS 302 loop | Registration missing behavior/entry point in 7. | Điều tra filter chain, no-registration fallback; giữ deny policy. |
| SLO fail nhưng login OK | LogoutMessage validator/metadata/binding khác. | Test SLO separately, signing/cert/session index. |
| Parser rejects large assertion | XML parser size/depth limits và request body limits. | Kiểm actual legitimate size, không disable security limits bừa bãi. |
| Security scanner thấy OpenSAML 4 | Transitive WSS4J / legacy jars hoặc fat JAR cũ. | Dependency graph, cache, product inventory; không suppress bằng fake exclusions. |
| Lỗi chỉ xuất hiện sau deploy, không ở IDE | Runtime classloader, image, shared libs khác. | Inspect packaged JAR/SBOM/image and JVM versions. |
| OpenSAML 5 works in 6.5 but fails in 7 | Spring Security major migration APIs/behavior. | Đối chiếu 7 migration guide, response order, AssertingPartyMetadata, filter matcher. |

### 19.1. Tách lỗi build và lỗi giao thức

- **Build failure**: import/class removed → sửa source/dependency.
- **Runtime linkage failure**: `NoSuchMethodError`/`NoClassDefFoundError` → sửa resolved JAR/ABI.
- **Startup configuration failure**: missing repository/registration/cert → sửa Spring bean/config.
- **SAML protocol failure**: invalid signature, issuer, audience, recipient, replay → sửa trust/protocol.
- **Local authorization failure**: account disabled, no tenant/role → không liên quan OpenSAML major.
- **Browser/session failure**: SameSite, ACS, RelayState, multi-tab → chẩn đoán SSO state và proxies.

Không đánh đồng tất cả thành “OpenSAML 5 lỗi”. Một lỗi `SAMLResponse invalid` có thể là tín hiệu validators đang **đúng khi từ chối** một assertion không hợp lệ.

## 20. Những anti-pattern phổ biến

1. **“Spring Security 7 + OpenSAML 4 vẫn được nếu override POM.”** Sai: support class 4 đã bị loại.
2. **“Mọi Spring Security 6.x đều tự chọn OpenSAML 5.”** Không suy ra; phải kiểm tài liệu đúng version.
3. **“Chỉ đổi opensaml-saml-api version là đủ.”** Sai: còn core, impl và supporting modules.
4. **“OpenSAML 4 + 5 trong cùng classpath giúp backward compatibility.”** Thường là nguy cơ ABI/classpath conflict.
5. **“Một Maven exclusion loại được mọi library transitive 4.”** Sai nếu library khác còn kéo 4.
6. **“Custom OpenSaml4 provider tự đổi tên khi Boot upgrade.”** Sai: custom code cần port.
7. **“Java runtime 11 chạy được vì Maven compile trên 17.”** Sai với OpenSAML 5/Boot 3/4.
8. **“Thiếu javax.servlet vì Java 21 không hỗ trợ OpenSAML.”** Thường do Jakarta namespace mismatch.
9. **“Lấy ví dụ 5.1.2 trong docs làm version bảo mật 2026.”** Phải xem security advisories/patch mới.
10. **“Tắt XML parser size limit để vượt lỗi.”** Có thể mở DoS.
11. **“Thay signature validator bằng no-op để login qua.”** Mất trust boundary.
12. **“Metadata fetch qua HTTPS tự tin cert mới.”** Cần metadata signature/approved trust bootstrap.
13. **“Ký response đúng thì audience không quan trọng.”** Sai.
14. **“SAML login OK thì SLO mặc nhiên OK.”** Sai, test riêng.
15. **“Chỉ cần unit tests xanh, không cần IdP E2E.”** Sai, signed/encrypted/bindings phải test thực.
16. **“Có một `OpenSaml5AuthenticationProvider` class nghĩa classpath đúng.”** Sai, còn supporting libs.
17. **“Có thể dùng `spring-security-saml` cũ thay module SAML2 SP.”** Không phải artifact chính thức hiện hành.
18. **“Hạ Spring Security patch để giữ tương thích XML lỗi.”** Tăng exposure nếu patch chứa security fix.
19. **“Copy custom XML signature classes từ OpenSAML 4 sang 5 không cần review.”** Các API/validation order có thể khác.
20. **“Rollback sang image cũ dễ hơn security review.”** Không hợp lý nếu image đã vulnerable.
21. **“Nâng OpenSAML đồng thời rotate IdP cert/ACS/roles.”** Làm test khó quy nguyên nhân và tăng rủi ro.
22. **“Làm được SAML signing nghĩa decryption và metadata không cần test.”** Sai.
23. **“Boot BOM tự chọn tất cả dù có dependency overrides lẻ.”** Overwrites có thể phá graph; phải kiểm actual resolution.
24. **“Snapshot là phiên bản mới nhất nên an toàn hơn.”** Không có đảm bảo production support/security.
25. **“Kiểm thử bằng raw assertion production ở CI.”** Nguy cơ lộ bearer token và PII.

## 21. Checklist QA trước khi nâng cấp production

1. Xác định đúng Boot, Spring Security, Java và Servlet/Jakarta versions hiện tại.
2. Đối chiếu ma trận 6.5 vs 7.x với docs của đúng release.
3. Không dùng OpenSAML 4 trên Spring Security 7.
4. Nếu ở 6.5, đánh giá opt-in OpenSAML 5 trước khi nâng lên 7.
5. Tất cả `org.opensaml` modules và supporting libs cùng major/compatible patch.
6. Không còn legacy `opensaml-core:4.x` trong runtime OpenSAML 5.
7. Có dependency lock/BOM/corporate approved repositories/SBOM.
8. Runtime Java thực tế ≥17 khi dùng OpenSAML 5.
9. Không có legacy Servlet `javax.*` trong Jakarta component không tương thích.
10. Không còn custom `OpenSaml4...` imports/beans khi chọn 5/7.
11. App compile/run tests với packaged image, không chỉ IDE.
12. AuthnRequest tạo đúng registration/ACS, signing key/algorithm.
13. Signed SAMLResponse pass, modified response fail.
14. Wrong issuer/audience/recipient/destination/time/replay bị deny.
15. EncryptedAssertion/EncryptedAttribute decrypt theo thứ tự đúng và fail nếu sai key.
16. Custom response validator và NameID/Principal mapping đúng sau thay đổi Security 7.
17. SLO, metadata, multi-IdP và cert rotation được E2E test.
18. Session/callback path, browser POST, RelayState và InResponseTo còn đúng.
19. XML parser/resource limits vẫn chống XXE/DoS.
20. Spring/OpenSAML patches được đối chiếu advisories gần thời điểm release.
21. Có canary, alarms/metrics, rollback/disable plan và review bảo mật.
22. Không log raw SAMLResponse, private key, NameID, browser cookies.
23. Ownership của team bảo mật/IdP/ops và change evidence có ghi nhận rõ.
24. Người duyệt xác nhận **không có hành vi fail-open** trong security validators.

## 22. Câu hỏi tự kiểm tra

1. **Spring Security 6.5 mặc định dùng OpenSAML nào?** — OpenSAML 4 theo tài liệu 6.5.
2. **6.5 có dùng OpenSAML 5 được không?** — Có, opt-in dependencies và custom code tương thích.
3. **Spring Security 7.x có hỗ trợ OpenSAML 4 không?** — Không; Spring 7 đã remove.
4. **OpenSAML 5 yêu cầu Java nào?** — Java 17 trở lên theo Shibboleth platform.
5. **Tên đúng của dependency SAML Service Provider?** — `spring-security-saml2-service-provider`.
6. **`OpenSaml4AuthenticationProvider` tự hoạt động trên 7 không?** — Không, port sang OpenSaml5.
7. **Vì sao phải nhìn dependency tree thay vì POM?** — Runtime transitive/corporate overrides có thể kéo mixed majors.
8. **OpenSAML 5 thay đổi core module thế nào?** — Từ `opensaml-core` sang `opensaml-core-api` và `opensaml-core-impl`.
9. **Vì sao API/impl phải cùng major?** — Tránh ClassNotFound/NoSuchMethodError và semantic mismatch.
10. **Spring Boot và Security nên nâng lẻ không?** — Theo supported BOM/migration path; không ép lẻ modules.
11. **OpenSAML 5 có thay chữ ký SAML đúng thành “bỏ kiểm tra” không?** — Không, mọi checks còn cần.
12. **Vì sao test SLO riêng?** — Login và logout dùng message/keys/validators khác nhau.
13. **Maven repo nào được docs dùng cho Shibboleth?** — `https://build.shibboleth.net/maven/releases/`.
14. **Khi có javax.servlet NoClassDefFoundError nên kiểm gì?** — Servlet/Jakarta compatibility, không đoán Java version.
15. **Sau chuyển sang 7, custom NameID conversion cần kiểm gì?** — Default response validation order và converter responsibility.
16. **Vì sao OpenSAML 4 EOL ảnh hưởng kiến trúc?** — Không còn security maintenance của major đó.
17. **Có thể copy 5.1.2 từ tài liệu 6.5 mà không kiểm advisories?** — Không.
18. **Một class OpenSaml5 xuất hiện chứng minh deployment đúng?** — Không; còn dependency tree/runtime test.
19. **Cách giảm rủi ro nâng cấp?** — 6.5 + OpenSAML5 trước, rồi Security 7, với tests và canary.
20. **Thế nào là QA PASS thật?** — Đúng major/dependencies, Java/platform, cryptographic validation, SLO, negative tests, audit và rollback an toàn.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — OpenSAML Support: selecting OpenSAML 4/5 và dependency examples](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html)
- [Spring Security 6.5 — SAML2 Migration to Spring Security 7](https://docs.spring.io/spring-security/reference/6.5/migration-7/saml2.html)
- [Spring Security 7.0 — What's New (removed OpenSAML 4)](https://docs.spring.io/spring-security/reference/7.0/whats-new.html)
- [Spring Security 7 — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security 7 — Authenticating SAML Responses, validators và decryption](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — Migration Guide](https://docs.spring.io/spring-security/reference/migration/)
- [Shibboleth OpenSAML — project overview, Java 17 và end-of-life policy](https://shibboleth.atlassian.net/wiki/spaces/OSAML/overview)
- [Shibboleth Product Platforms — Java 17 platform for OpenSAML 5](https://shibboleth.atlassian.net/wiki/spaces/DEV/pages/1161266638/Product%2BPlatforms)
- [Shibboleth Releases Repository — OpenSAML BOM and releases](https://build.shibboleth.net/maven/releases/org/opensaml/opensaml-bom/)
- [OpenSAML Security Advisory — 13 May 2026 parser limits](https://shibboleth.net/pipermail/announce/2026-May/000384.html)
- [Spring Security Releases June 2026 — SAML-related CVEs](https://spring.io/blog/2026/06/09/spring-security-releases-2026-06/)
- [Spring Boot System Requirements — Java, Servlet, Framework compatibility](https://docs.spring.io/spring-boot/system-requirements.html)
- [Apache WSS4J — SAML/OpenSAML compatibility matrix](https://ws.apache.org/wss4j/)