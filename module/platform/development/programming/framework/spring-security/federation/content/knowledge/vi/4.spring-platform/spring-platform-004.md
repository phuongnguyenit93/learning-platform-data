# Thiết lập `spring-security-saml2-service-provider` và các phụ thuộc OpenSAML

## 1. Bài toán: thêm khả năng SAML 2.0 cho ứng dụng Spring

Trong hệ thống **SAML 2.0 federation**, ứng dụng Spring đóng vai trò **Service Provider (SP)**, cũng được Spring Security gọi là **Relying Party (RP)**. Hệ thống nhận diện độc lập (Identity Provider, IdP; trong tài liệu Spring Security còn gọi là Asserting Party, AP) xác thực người dùng và gửi `SAMLResponse` về ứng dụng. SP phải kiểm tra thông điệp SAML theo cấu hình tin cậy trước khi tạo `Authentication` và phiên ứng dụng.

Muốn ứng dụng Spring Boot dùng luồng này, cần hai lớp thiết lập khác nhau:

1. **Thư viện và build:** khai báo module `org.springframework.security:spring-security-saml2-service-provider`, các phụ thuộc OpenSAML có phiên bản tương thích và repository giải quyết được artifact.
2. **Cấu hình federation:** khai báo IdP metadata, endpoint SSO, chứng chỉ xác minh chữ ký, định danh SP, ACS và thông tin ký/giải mã nếu IdP yêu cầu; cấu hình servlet security chain phù hợp.

**Cài dependency thành công không có nghĩa SSO đã chạy thành công.** Build chỉ chứng minh các JAR có mặt. Đăng nhập hoàn chỉnh còn cần IdP thực, quan hệ tin cậy và đường callback hoạt động.

Sau bài này, bạn sẽ biết cách thêm dependency bằng Gradle/Maven, giải thích vai trò OpenSAML, kiểm tra cây phụ thuộc, khai báo IdP, xác nhận các endpoint và xử lý lỗi thường gặp. Các ví dụ hướng tới **Spring Boot 3.x / Spring Security 6.x, Java 17 trở lên, Servlet/MVC**. Nếu dùng Spring Boot/Spring Security phiên bản khác, hãy đối chiếu tài liệu đúng phiên bản trước khi sao chép cấu hình.

## 2. Đặt đúng module vào kiến trúc

| Thành phần | Vai trò | Cần tự khai báo? |
| --- | --- | --- |
| `spring-boot-starter-web` | Ứng dụng Servlet/MVC, HTTP endpoint và servlet container | Có trong ví dụ web MVC |
| `spring-boot-starter-security` | Spring Security và các thành phần nền của filter chain | Có trong ví dụ |
| `spring-security-saml2-service-provider` | Tích hợp SAML 2.0 SP vào Spring Security; request/response, provider, registration và authentication | **Phụ thuộc chính cần thêm** |
| OpenSAML (`org.opensaml:...`) | Xử lý SAML/XML, đối tượng SAML, serialize/parse, chữ ký và các chức năng chuẩn liên quan | **Thông thường nhận qua phụ thuộc bắc cầu** của module SAML |
| Shibboleth Releases Maven repository | Nguồn phân phối cần thiết cho các artifact OpenSAML theo tài liệu Spring Security | Cần khai báo trong quản lý repositories khi dependency chưa lấy được từ nguồn hiện có |
| `RelyingPartyRegistrationRepository` | Chứa các cặp cấu hình SP–IdP | Spring Boot có thể tự tạo từ properties; có thể cung cấp bean riêng |
| `SecurityFilterChain` | Quy định endpoint nào bảo vệ và kích hoạt `saml2Login` | Spring Boot có cấu hình tự động khi phù hợp; có thể khai báo bean tùy chỉnh |

`spring-security-saml2-service-provider` là **Spring Security Servlet SP**, không phải thư viện độc lập để biến ứng dụng thành IdP, và cũng không phải một client giao thức OAuth/OIDC. Trong ứng dụng Spring WebFlux thuần Reactive, không mặc nhiên áp dụng filter/endpoint Servlet ở ví dụ này.

### Luồng phụ thuộc về ý tưởng

~~~text
Spring Boot Servlet application
    +-- spring-boot-starter-web
    +-- spring-boot-starter-security
    +-- spring-security-saml2-service-provider
          +-- Spring Security SAML integration
          +-- OpenSAML modules (resolved transitively)
                +-- SAML/XML processing and crypto dependencies

Runtime:
Browser -> Spring SP -> IdP
Browser <- IdP -> POST SAMLResponse -> Spring SP
                                  -> verify -> Authentication
~~~

Đây là sơ đồ chức năng, **không phải bản sao cây phụ thuộc đã resolve**; module con và version cụ thể thay đổi theo phiên bản. Hãy dùng lệnh `dependencies`/`dependency:tree` để xem dependency graph thật của dự án.

## 3. Trước khi thêm thư viện

Xác định bốn thông tin:

- **Bản Spring Boot và Spring Security được quản lý:** nếu dự án dùng Spring Boot dependency management/BOM, để BOM xác định phiên bản Spring Security. Không gắn một phiên bản Spring Security khác chỉ cho module SAML.
- **Hệ build:** Gradle Groovy DSL, Kotlin DSL hoặc Maven; repositories có thể được khai báo ở cấp ứng dụng hoặc cấp settings/parent.
- **Môi trường chạy:** JDK tương thích với dòng Spring Boot đang dùng; bài này dùng Java 17+ và Servlet stack.
- **Thông tin IdP:** metadata XML hoặc metadata URL tin cậy, `entityID`, SSO binding/location, public signing certificate, yêu cầu ký `AuthnRequest` và ACS URL đã đăng ký tại IdP.

Có thể hoàn tất phần **build** trước khi nhận metadata, nhưng chưa thể kết luận phần SSO runtime hoạt động. Nên dùng cùng một `registrationId` xuyên suốt ví dụ; ở đây chọn `corp`.

## 4. Gradle Groovy DSL: thêm dependency đúng cách

Trong dự án Spring Boot 3.x **đã có plugin Spring Boot và cơ chế dependency management tương thích**, bổ sung vào `build.gradle`:

~~~groovy
repositories {
    mavenCentral()
    maven {
        url = uri("https://build.shibboleth.net/maven/releases/")
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là **đoạn cấu hình trong build Gradle của dự án Boot đã tồn tại**, không phải toàn bộ `build.gradle` chạy độc lập. Các plugin, nhóm dự án, version và cấu hình repository khác được giữ theo dự án.

Giải thích:

- `implementation` làm thư viện khả dụng khi biên dịch và chạy ứng dụng. Đặt SAML module vào `testImplementation` hoặc `compileOnly` sẽ không đáp ứng runtime đăng nhập.
- Không ghi `version` ngay sau `spring-security-saml2-service-provider` khi BOM của Spring Boot đã quản lý phiên bản. Nếu dùng Gradle mà **không có BOM/plugin quản lý**, phải khai báo phiên bản tương thích trong quy hoạch chung, thay vì sao chép số phiên bản tùy ý.
- OpenSAML thường được dependency chính kéo vào bắc cầu. **Đừng khai báo thủ công toàn bộ `org.opensaml` module và version nếu chưa có lý do rõ ràng**; điều này dễ tạo nhiều version xung đột.
- Repository `https://build.shibboleth.net/maven/releases/` là Shibboleth releases URL được Spring Security document cho Maven. Một số trang Gradle/ví dụ cũ dùng URL dạng `/nexus/content/repositories/releases/`; kiểm tra URL được tổ chức và phiên bản tài liệu hỗ trợ, không thêm hàng loạt repository không xác định.

### Khi dự án quản lý repositories tập trung trong `settings.gradle`

Nhiều dự án Gradle đa module đặt repository trong `dependencyResolutionManagement` và khóa `RepositoriesMode.FAIL_ON_PROJECT_REPOS`. Khi đó đặt repository tại **settings**, không thêm `repositories` vào từng `build.gradle`:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
        maven {
            url = uri("https://build.shibboleth.net/maven/releases/")
        }
    }
}
~~~

Đoạn này là ví dụ bổ sung vào `settings.gradle` hiện có. Giữ chính sách repositories của tổ chức, đặc biệt khi dùng mirror/Nexus/Artifactory. Với Gradle multi-module, thêm dependency **vào module ứng dụng SP cần nó**, không nhất thiết thêm vào root hay tất cả thư viện con.

### Kotlin DSL (`build.gradle.kts`)

Nếu dự án dùng Kotlin DSL, hình thức tương đương là:

~~~kotlin
repositories {
    mavenCentral()
    maven {
        url = uri("https://build.shibboleth.net/maven/releases/")
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.security:spring-security-saml2-service-provider")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Không pha cú pháp Groovy `implementation '...'` vào `.kts`. Khi repositories đã được quản lý tại settings, chỉ thêm dependency trong module; không tạo khai báo repository trùng.

## 5. Maven: dependency và nguồn artifact

Với dự án Maven dùng Spring Boot parent hoặc import BOM tương thích, phần cần thiết trong `pom.xml` có dạng:

~~~xml
<repositories>
    <repository>
        <id>shibboleth-releases</id>
        <url>https://build.shibboleth.net/maven/releases/</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>

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
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-saml2-service-provider</artifactId>
    </dependency>
</dependencies>
~~~

Đây là **đoạn XML để chèn vào phần tử `<project>` của một POM hợp lệ**; không phải POM đầy đủ. Nếu parent `pom.xml` đã quản lý Spring Security, POM con chỉ khai báo `artifactId` mà không gắn version riêng. Nếu tổ chức sử dụng mirror, policy truy cập repository hoặc allow-list dependency, tuân theo cấu hình corporate Maven `settings.xml`.

Không nhầm hai artifact:
- **Đúng cho Spring Security hiện đại:** `org.springframework.security:spring-security-saml2-service-provider`.
- **Di sản Spring Security SAML Extension:** `org.springframework.security.extensions:spring-security-saml2-core`. Đây là dòng cũ với API/cách cấu hình khác; không dùng như bản thay thế cho module hiện đại.

## 6. OpenSAML đến từ đâu và dùng để làm gì?

OpenSAML là thư viện xử lý hiện thực kỹ thuật SAML/XML mà Spring Security dùng phía dưới. Ở cấp lập trình ứng dụng, bạn thường làm việc với API Spring Security như `RelyingPartyRegistration`, `Saml2Authentication`, `Saml2AuthenticatedPrincipal`, `Saml2X509Credential`; Spring Security tích hợp chúng với implementation dựa trên OpenSAML.

Các nhiệm vụ kỹ thuật của OpenSAML bao gồm:

1. Xây dựng, marshal và unmarshal đối tượng XML theo mô hình SAML.
2. Đọc `AuthnRequest`, `Response`, `Assertion` và metadata; xử lý binding/encoding trong các thành phần tích hợp.
3. Hỗ trợ XML Signature, XML Encryption và kiểm tra cấu trúc/điều kiện SAML theo logic của provider.
4. Phối hợp với Spring Security để xác minh response và tạo kết quả xác thực.

Vì sao cần Shibboleth repository? Không phải mọi artifact OpenSAML cần cho phiên bản Spring Security đều có thể resolve hoàn toàn từ Maven Central. Tài liệu Spring Security yêu cầu bổ sung Shibboleth releases repository cho SAML 2.0 SP. **Repository là nguồn tải JAR, không phải IdP đăng nhập**; khi app chạy, người dùng không chuyển hướng tới repository này.

Một số artifact OpenSAML có thể thấy trong dependency graph là `opensaml-saml-api`, `opensaml-saml-impl`, các module `opensaml-core` hoặc `opensaml-core-api`/`opensaml-core-impl`, cùng các thư viện hỗ trợ XML security. Danh sách chính xác phụ thuộc thế hệ OpenSAML và dependency management đang dùng.

### OpenSAML 4 và OpenSAML 5: không đoán tương thích

Spring Security 6.x có các triển khai mang tên như `OpenSaml4...` hoặc `OpenSaml5...` ở những bản hỗ trợ cả hai, trong khi các bản mới hơn có thể thay đổi mặc định và loại bỏ bản quá cũ. Đặc biệt, OpenSAML 5 tách một số module mà OpenSAML 4 có thể đóng gói chung (ví dụ `opensaml-core` so với `opensaml-core-api` và `opensaml-core-impl`).

| Quy tắc | Hành động |
| --- | --- |
| Ứng dụng bình thường với Boot BOM | Giữ BOM và dependency bắc cầu mặc định của SAML SP |
| Muốn chọn OpenSAML 5 trong bản Spring Security hỗ trợ chọn | Theo đúng hướng dẫn **OpenSAML Support của phiên bản Spring Security hiện dùng**, gồm exclusions và module bổ sung |
| Nâng cấp Spring Security 6 sang 7 | Rà release notes/migration SAML, kiểm tra provider OpenSAML, Java baseline và dependency graph trước khi nâng |
| Gặp `NoClassDefFoundError` hoặc `NoSuchMethodError` | Xem các version OpenSAML, XML security và cả dependency graph; nghi ngờ xung đột/bản không tương thích trước khi sửa logic nghiệp vụ |
| Dự án đã override OpenSAML | Ghi rõ lý do, tài liệu hỗ trợ và test tích hợp; không chỉ thay một version string rồi coi như hoàn tất |

Không thêm “OpenSAML version mới nhất” trực tiếp để vá lỗi resolution khi Spring Security đang được BOM quản lý: version mới có thể thay đổi API hoặc cấu trúc module. Cũng không loại bỏ thư viện kiểm tra chữ ký chỉ để build chạy được.

## 7. Kiểm chứng cây phụ thuộc trước khi thử đăng nhập

Trong thư mục dự án Gradle có wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-saml-impl --configuration runtimeClasspath
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency opensaml-saml-impl --configuration runtimeClasspath
~~~

Trong Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.opensaml
~~~

Ý nghĩa các lệnh:

- `dependencies` hiển thị resolved graph của **cấu hình runtime** (nơi thư viện SAML phải có mặt).
- `dependencyInsight` cho biết module/version được chọn, lý do selection và các đường phụ thuộc trong Gradle. Cờ `--dependency` là bộ lọc, không tự sửa version.
- `dependency:tree` là bản nhìn tương ứng của Maven; cú pháp lọc `-Dincludes` cần dependency plugin đủ mới theo môi trường build.
- Hãy tìm một dòng Spring Security nhất quán và các OpenSAML JAR được resolve; **không có một stdout cố định** vì Gradle, Maven, OS, BOM, repository và dependency của dự án khác nhau.
- Nếu build thành công nhưng dependency tree có nhiều bản OpenSAML không tương thích, kết quả build không đủ để kết luận SAML runtime an toàn hoặc hoạt động.

Khi mở rộng vào dự án có plugin build riêng, một số dependency có thể được khai báo qua convention plugin/capability; kiểm tra resolved graph của **module runtime thực tế**, không chỉ danh sách khai báo ở root.

## 8. Cấu hình tối thiểu IdP metadata trong Spring Boot

Sau khi dependency resolve, RP/SP cần biết **IdP nào đáng tin**. Cách gọn nhất là lấy metadata XML từ URL do IdP cung cấp hoặc từ một file metadata đã xác minh. Ví dụ trong `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "https://login.example.org/saml/metadata"
~~~

Mọi hostname `.example.org` trong bài là **địa chỉ minh họa**; đổi thành metadata URL thực của IdP khi triển khai. Đây là cấu hình lý tưởng khi IdP metadata chứa issuer, SSO service và chứng chỉ ký đáng tin cậy theo nhu cầu tích hợp.

- `corp` là **registrationId do ứng dụng chọn** để phân biệt IdP/đối tác. Nó xuất hiện trong URL khởi tạo và callback.
- `assertingparty.metadata-uri` chỉ đến **metadata của IdP** (AP), không phải metadata SP do ứng dụng tự công bố.
- Metadata XML thường chứa `EntityDescriptor entityID`, `IDPSSODescriptor`, `SingleSignOnService`, `KeyDescriptor`. Không tráo metadata IdP với XML metadata của SP.
- Việc metadata có thể tải được không đủ chứng minh đáng tin. Nguồn, TLS, ký/cấp phát metadata, chứng chỉ và trách nhiệm quản lý phải được xác minh theo quan hệ đã thiết lập với IdP.
- Không “đoán” URL `/metadata` bằng cách ghép domain: mỗi IdP có cấu trúc endpoint riêng, và một URL trả HTML login không phải XML metadata hợp lệ.

**Phương án metadata file nội bộ** khi muốn kiểm soát nguồn và vòng đời:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp-metadata.xml"
~~~

File tương ứng đặt tại `src/main/resources/saml/corp-idp-metadata.xml`. Đây là XML metadata **đã nhận và xác minh** từ IdP; không tự viết nội dung không có chứng cứ. Nếu dùng file cố định, cần quy trình cập nhật khi IdP đổi signing certificate/SSO endpoint; nếu tải metadata từ URL, xem rõ cơ chế refresh/caching của cấu hình/version thực tế.

### Khi không có metadata URI

Có thể cung cấp các trường IdP bằng tay (ví dụ khi IdP cấp riêng issuer, SSO URL, certificate):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              entity-id: "https://login.example.org/saml/issuer"
              singlesignon:
                url: "https://login.example.org/saml/sso"
                binding: "REDIRECT"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "classpath:saml/idp-signing.crt"
~~~

Đoạn trên giả định **IdP chấp nhận AuthnRequest không ký** để minh họa cấu hình với verification certificate; **chỉ dùng `sign-request: false` khi chính sách/metadata IdP cho phép**. Trường `entity-id` phải khớp `Issuer` của response từ IdP. `certificate-location` chứa **public X.509 certificate của IdP**, dùng để xác minh chữ ký, không chứa private key. Binding `REDIRECT` và URL cũng phải theo IdP thực; IdP có thể dùng POST binding. Nếu IdP bắt buộc request ký, cần thêm SP signing credentials thay vì tắt kiểm tra bên IdP.

Không triển khai đồng thời hai cách mẫu như hai khối YAML `spring:` lặp lại vô tình ghi đè nhau. Hãy chọn **metadata URI** hoặc **manual metadata** theo tình huống.

## 9. Khóa, chứng chỉ và các kiểu credentials

Trong federation, mỗi bên có khóa và chứng chỉ phục vụ vai trò khác nhau:

| Credential | Ai sở hữu? | Tác dụng |
| --- | --- | --- |
| IdP signing certificate, public | IdP cung cấp; SP lưu tin cậy | SP kiểm tra chữ ký của SAML Response/Assertion theo profile/chính sách |
| SP signing private key + X.509 certificate | SP giữ private key, có thể công bố cert | SP ký `AuthnRequest`/thông điệp theo yêu cầu IdP |
| SP decryption private key + X.509 certificate | SP giữ private key | SP giải mã assertion/attribute được IdP mã hóa cho SP |
| IdP encryption public certificate, nếu có | IdP cung cấp | SP dùng theo trường hợp phát thông điệp cần mã hóa gửi cho IdP |

**Không đánh đồng** chứng chỉ của IdP và SP; “certificate” thường là public, còn **private key là bí mật**. Có thể có nhiều certificate để luân chuyển khóa (rollover). Đừng hardcode private key vào mã Java, đính kèm lên Google Sheet hoặc commit file production secret vào Git.

Ví dụ khi IdP yêu cầu SP ký `AuthnRequest`, có thể bổ sung vào registration `corp`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/rp-signing.key"
                  certificate-location: "file:/run/secrets/saml/rp-signing.crt"
            assertingparty:
              metadata-uri: "https://login.example.org/saml/metadata"
~~~

Đây là **một registration đầy đủ riêng cho trường hợp ký**, không phải khối cần ghép cùng các ví dụ khác. Hai đường `file:/run/secrets/...` chỉ minh họa secret được mount từ môi trường chạy; phải cấp file thật, quyền đọc đúng cho tiến trình và khóa/cert khớp nhau. Định dạng private key thường yêu cầu **PKCS#8** mà Spring Security đọc được. Nếu IdP mã hóa assertion cho SP, thêm **decryption credentials** đúng key/certificate theo chính sách riêng; không tự động dùng khóa ký cho mọi mục đích.

Phía SP cần ràng buộc issuer, audience, recipient/destination, điều kiện thời gian, replay và chữ ký của response/assertion. Không chấp nhận XML chỉ vì chứa email/name hay vì mã Base64 giải mã thành công.

## 10. Viết SecurityFilterChain khi cần tùy chỉnh

Spring Boot có thể auto-configure các bean SAML khi dependency và properties phù hợp. Nếu cần khai báo rõ chính sách ứng dụng, dùng một `SecurityFilterChain` cho Servlet.

Tệp `src/main/java/com/example/saml/SecurityConfig.java`:

~~~java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
~~~

Giải thích:

1. `@Configuration` đăng ký cấu hình; `@Bean SecurityFilterChain` thay thế một số mặc định bảo mật do Boot tự cung cấp. Không cần `WebSecurityConfigurerAdapter`, vì đây là API di sản không dùng trong Spring Security 6.
2. `authorizeHttpRequests` cho phép trang gốc và `/error`; tài nguyên còn lại phải xác thực.
3. `saml2Login` tích hợp SAML authentication request, response filter và provider; các registration từ `spring.security.saml2.relyingparty.registration.*` vẫn có thể do Boot cung cấp.
4. `saml2Metadata` **chủ động bật endpoint SP metadata**; nó hữu ích để cung cấp SP entity ID/ACS/certificate cho IdP. Không giả định dependency một mình đã công bố metadata URL.
5. Lớp này **không phải ứng dụng Java độc lập**: nó phải nằm trong dự án Spring Boot được component scan, có các dependency, Java 17+ và IdP registration hợp lệ. Không chạy riêng `javac SecurityConfig.java` mà thiếu Spring JAR.

Khi thêm nhiều `SecurityFilterChain`, cần hiểu `securityMatcher` và thứ tự chain: nếu chain xử lý ACS hoặc AuthnRequest thiếu `saml2Login`, login sẽ lỗi dù dependency đã có. Mẫu trên minh họa một chain đơn giản cho ứng dụng MVC.

### Các endpoint mặc định cần nhận diện

| URL | Phương thức/vai trò | Cơ chế liên quan |
| --- | --- | --- |
| `/saml2/authenticate/corp` | GET khởi tạo SP-initiated SSO | `Saml2WebSsoAuthenticationRequestFilter` tạo `AuthnRequest` |
| `/login/saml2/sso/corp` | POST nhận `SAMLResponse` theo binding phổ biến | `Saml2WebSsoAuthenticationFilter` chuyển cho authentication provider |
| `/saml2/metadata/corp` | GET metadata SP khi bật `saml2Metadata` | `Saml2MetadataFilter` tạo metadata từ registration |
| `/saml2/service-provider-metadata/corp` | Endpoint alias metadata SP theo cấu hình hỗ trợ | Dùng để trao đổi metadata với IdP |

Đường endpoint có thể được tùy chỉnh; `/login/saml2/sso` không có `registrationId` cũng có thể được framework hỗ trợ theo cơ chế tra registration. Hãy dựa vào Spring Security version và registration thực tế. ACS phải là **địa chỉ public mà browser của người dùng truy cập được**, không phải tên host nội bộ của container.

## 11. Một endpoint kiểm tra principal sau xác thực

Để phân biệt **login đã thành công** với **application chỉ redirect đúng**, có thể xem principal do Spring Security tạo. Tệp `src/main/java/com/example/saml/CurrentUserController.java`:

~~~java
package com.example.saml;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return principal.getName();
    }
}
~~~

Trong dự án Boot có `@SpringBootApplication` ở package cha `com.example` (hoặc `com.example.saml`), bean này được scan. Truy cập `/me` khi chưa xác thực sẽ kích hoạt login theo security chain; **chỉ sau khi đã xác minh SAML Response thành công**, endpoint mới nhận được principal và trả tên. Không có stdout cố định vì name và giá trị response phụ thuộc IdP. Trong sản phẩm thực tế, chỉ trả thuộc tính được phép hiển thị; tránh trả toàn bộ SAML assertion/attributes vào HTTP response hoặc log.

Từ `Saml2AuthenticatedPrincipal` có thể đọc thuộc tính bằng API của Spring Security khi cần ánh xạ quyền nghiệp vụ. **Thuộc tính do IdP phát không tự đồng nghĩa với `ROLE_ADMIN`**: mapping/authorization phải có chính sách cụ thể.

## 12. Khi cần cấu hình registration bằng Java

Nếu metadata không phù hợp để khai báo trong `application.yml`, có thể thay bằng bean `RelyingPartyRegistrationRepository`. Đây là **phương án thay thế Boot properties**, không cần cùng lúc khai báo hai nguồn cho cùng registration.

Ví dụ Java (trong dự án đã có các bean và dependency liên quan):

~~~java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

@Configuration
public class SamlRegistrationConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
        RelyingPartyRegistration corp = RelyingPartyRegistrations
                .fromMetadataLocation("classpath:saml/corp-idp-metadata.xml")
                .registrationId("corp")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }
}
~~~

Điều kiện để chạy là phải có metadata file SAML hợp lệ tại `src/main/resources/saml/corp-idp-metadata.xml`; Spring Boot phải load bean, và IdP phải biết cấu hình SP tương ứng. Đây không phải toàn bộ chương trình với `main`. `InMemoryRelyingPartyRegistrationRepository` thích hợp cho tập registration được khởi tạo lúc startup; nếu cần cấu hình động, cập nhật metadata hoặc đa đối tác phức tạp, hãy thiết kế repository/refresh thích hợp và giải quyết key rotation.

`RelyingPartyRegistration` chứa cả **metadata phía SP** (entityId, ACS, signing/decryption credentials) lẫn **metadata phía IdP** (issuer, SSO endpoint, verification certificates). Không nhầm nó với Java `ClientRegistration` của OAuth 2.0.

## 13. Trao đổi metadata SP–IdP trước khi test

Một cấu hình tối thiểu chỉ đúng khi hai bên có thông tin đối ứng. Quy trình thực tế:

1. Nhận IdP metadata đáng tin: issuer/entity ID, SSO URL, binding và chứng chỉ. Xác minh endpoint metadata đã trao đổi là đúng nhà cung cấp.
2. Cấu hình `registrationId=corp`, dependency và metadata cho Spring SP.
3. Xác định **SP entity ID** và **ACS URL** mà Spring sẽ tạo trong môi trường chạy. Theo convention của Spring Security, SP entity ID thường dùng `{baseUrl}/saml2/service-provider-metadata/{registrationId}`; ACS thường là `{baseUrl}/login/saml2/sso/{registrationId}`, với `{baseUrl}` là scheme/host/port public thực tế. Có thể tùy chỉnh cả hai.
4. Đăng ký SP entity ID và ACS URL **chính xác** tại IdP. Cung cấp SP metadata (nếu IdP hỗ trợ import) và SP signing certificate khi IdP yêu cầu signed AuthnRequest.
5. Kiểm tra IdP cho phép đúng binding/Response Destination/Audience. Đồng hồ các hệ thống cần đồng bộ NTP trong phạm vi sai lệch cho phép.
6. Chỉ sau đó mới thử đăng nhập thật.

Ví dụ nếu hệ thống public là `https://app.example.org`, registration `corp`, bộ thông số SP có thể giống:

~~~text
SP Entity ID:
https://app.example.org/saml2/service-provider-metadata/corp

SP Assertion Consumer Service (ACS):
https://app.example.org/login/saml2/sso/corp

SP-initiated SSO entry:
https://app.example.org/saml2/authenticate/corp

SP metadata endpoint (if enabled):
https://app.example.org/saml2/metadata/corp
~~~

**Địa chỉ giả định chỉ để giải thích mối quan hệ URL.** Trong deployment có reverse proxy hoặc load balancer, nếu Spring thấy backend `http://localhost:8080` thay vì public `https://app.example.org`, metadata/ACS/redirect có thể sai. Cần cấu hình proxy, trusted forwarded headers và URL canonical theo hạ tầng; đừng mở rộng tin tưởng `X-Forwarded-*` từ nguồn không đáng tin.

## 14. Kiểm tra cài đặt theo từng tầng

### Tầng A — build dependency

Gradle:

~~~bash
./gradlew compileJava
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-saml-impl --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn test
mvn dependency:tree -Dincludes=org.opensaml
~~~

Nếu fail ngay ở bước `Could not resolve org.opensaml:...`, tập trung kiểm tra repository, SSL proxy, mirror, VPN/corporate policy, artifact coordinates và version. Không thay cấu hình IdP để xử lý lỗi phân giải dependency.

### Tầng B — khởi động ứng dụng

Trong dự án Boot có entrypoint và `application.yml` hợp lệ:

~~~bash
./gradlew bootRun
~~~

Hoặc dùng cách khởi động chuẩn của dự án. Nếu metadata IdP được tải lúc startup, môi trường phải truy cập được URL đó và tài liệu phải là XML hợp lệ. **Startup thành công chỉ xác nhận app dựng được bean và cấu hình đã đủ khởi tạo**, chưa chứng minh response SAML đã được kiểm tra thành công.

### Tầng C — endpoint AuthnRequest/metadata

Với app local chạy port 8080 và IdP registration hợp lệ:

~~~bash
curl -i "http://localhost:8080/saml2/authenticate/corp"
curl -i "http://localhost:8080/saml2/metadata/corp"
~~~

Ở lệnh đầu, trong cấu hình SP-initiated thông thường, kỳ vọng thấy một redirect tới IdP với `SAMLRequest` (và có thể `RelayState`) trong `Location`. Lệnh thứ hai chỉ có ý nghĩa khi bạn đã bật `saml2Metadata`, kỳ vọng XML metadata SP; mã HTTP có thể khác nếu route/security/môi trường đã thay đổi. `curl` không hoàn thành xác thực vì nó chưa có IdP session và sẽ không tự gửi `SAMLResponse` phù hợp.

### Tầng D — đăng nhập end-to-end bằng browser

Mở browser trong môi trường tích hợp, truy cập `/me` hoặc trang bảo vệ, bật Developer Tools → Network → Preserve log. Theo dõi:

1. Ứng dụng chuyển hướng sang IdP từ `/saml2/authenticate/corp`.
2. IdP xác thực hoặc dùng IdP session sẵn có.
3. Browser nhận form SAML và **POST `SAMLResponse` về ACS** của SP.
4. Spring Security xử lý response bằng provider dựa trên OpenSAML và tạo principal; browser nhận phiên ứng dụng.
5. Truy cập `/me` có phản hồi tên principal như mong đợi.

Kiểm tra cả đường thất bại: response không đúng issuer/audience/signature hoặc không tương quan với request phải bị từ chối. **Không cần và không nên tạo SAMLResponse giả chưa ký để cố làm login thành công**.

## 15. Lỗi build, cấu hình và runtime: xác định đúng lớp

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Could not find org.opensaml:...` / `Could not resolve` | Thiếu Shibboleth releases repository, mirror không có artifact, bị chặn mạng | Kiểm tra URL repository, cấu hình centralized repositories, policy proxy và dependency graph |
| `PKIX path building failed` khi tải artifact/metadata | Java không tin chain TLS hoặc corporate TLS interception | Kiểm tra CA truststore/hạ tầng; **không tắt TLS verification** |
| `NoClassDefFoundError`, `NoSuchMethodError` liên quan OpenSAML | Trộn OpenSAML 4/5, thiếu implementation module, xung đột XML security/JAR | Chạy `dependencyInsight`/`dependency:tree`, so phiên bản theo Spring Security compatibility |
| Boot không tạo SP registration | Sai key YAML, sai indentation, không có metadata hoặc bean bị ghi đè | Kiểm tra `spring.security.saml2.relyingparty.registration.corp.assertingparty` và bean configuration |
| Khởi động fail vì metadata | URL không phải XML, IdP offline, TLS/redirect sai, metadata không đủ thành phần | Xác minh metadata tin cậy và khả năng truy cập tại startup; dùng file đã xác minh khi cần |
| `/saml2/authenticate/corp` không tạo request | Sai registrationId, chain không bật SAML hoặc route bị custom | So cấu hình `corp`, `saml2Login`, servlet chain matcher và path |
| IdP báo unknown service provider | SP entity ID chưa được đăng ký/không khớp | So SP entity ID chính xác với IdP configuration |
| IdP báo invalid ACS/Destination/Recipient | ACS/callback khác URL đã khai báo | So URL public, proxy, HTTPS, port, hostname, path |
| IdP yêu cầu signed `AuthnRequest` | SP thiếu signing private key/certificate hoặc key không khớp | Cấu hình signing credentials và kiểm tra certificate IdP đã tin |
| POST ACS bị 403 | Filter chain/CSRF config sai phạm vi hoặc route không hợp lệ | Rà endpoint SAML và cấu hình CSRF; không tắt CSRF toàn ứng dụng |
| Không thấy state/không khớp `InResponseTo` | Mất phiên SP, cookie bị chặn ở cross-site POST, request repository sai | Kiểm tra cookie SameSite/Secure, session và correlation, đặc biệt khi callback POST |
| `invalid signature` hoặc không tin cert | IdP cert cũ, wrong metadata, response thiếu chữ ký theo chính sách | Kiểm tra ký XML/metadata đã xác minh, kế hoạch cert rollover; không bỏ verify |
| `expired`/NotBefore/NotOnOrAfter | Đồng hồ lệch, response quá hạn, replay | Đồng bộ thời gian, xử lý request mới, không mở rộng tolerance vô hạn |
| Login thành công nhưng `/me` bị 403 | Rule authorization/authority mapping khác authentication | Kiểm tra `SecurityContext`, principal và chính sách ánh xạ roles |
| Có thư viện nhưng vẫn chỉ thấy login mặc định | Chưa có IdP registration hoặc cấu hình chain chưa phù hợp | Rà Boot properties/bean và các filter SAML trước khi tạo redirect thủ công |

**Chẩn đoán nhanh:** nếu error xuất hiện khi resolve dependency, sửa **build/repositories/versions**; nếu startup fail, kiểm tra **metadata/bean/keys**; nếu redirect thất bại, xem **registration/URL/chain**; nếu browser đã POST response nhưng bị từ chối, xem **signature/issuer/audience/time/correlation/cookies**.

## 16. Phân biệt bốn thao tác thường bị gộp nhầm

**Thêm dependency** chỉ cho phép compile/load lớp SAML. **Khởi tạo registration** nói SP tin IdP nào và cần gửi/nhận thông điệp ở đâu. **Đăng ký SP bên IdP** tạo quan hệ tin cậy đối ứng. **Xác minh SAML Response** mới là lúc ứng dụng nhận định người dùng đã xác thực.

Không nên dùng `@RestController` tự nhận `SAMLResponse` rồi Base64 decode XML để tự tạo session: cách đó bỏ qua filter/provider, xử lý chữ ký XML, điều kiện SAML và kiểm tra replay. Spring Security đã có pipeline chuyên dụng.

Ví dụ khái niệm các thành phần khi POST tới ACS:

~~~mermaid
flowchart LR
    B[Browser POST SAMLResponse] --> F[Saml2WebSsoAuthenticationFilter]
    F --> R[RelyingPartyRegistration]
    F --> P[OpenSAML authentication provider]
    R --> P
    P --> V[Verify SAML response and assertions]
    V --> A[Authentication + SecurityContext]
    A --> S[Application session / protected endpoint]
~~~

Sơ đồ chỉ nêu các bước chính; không có nghĩa mỗi kiểm tra đều do đúng một method hay mỗi deployment đều lưu session theo cùng cách.

## 17. Một số ràng buộc bảo mật của việc cài SAML SP

- **Giao tiếp TLS:** metadata URL, login, callback/ACS ở production cần HTTPS, chứng chỉ tin cậy; không tắt hostname validation.
- **Chữ ký và trust:** IdP signing certificate phải được quản lý qua quan hệ tin cậy. Cho phép nhiều certificate khi quay vòng khóa và loại certificate cũ theo quy trình.
- **Private key:** lưu trong secret manager hoặc mount bảo mật; cấp quyền đọc tối thiểu. Không xuất khóa trong log, unit test output hay file nội dung công khai.
- **Phòng replay:** tuân thủ `InResponseTo`, audience restriction, recipient/destination, time bounds và xử lý response ID theo khả năng provider/cấu hình.
- **Cookie phiên trên cross-site POST:** browser có thể không gửi `SameSite=Lax` cookie khi IdP POST SAMLResponse về ACS. Cần chọn chiến lược cookie/session và correlation phù hợp, không bỏ xác minh `InResponseTo`.
- **CSRF:** SAML ACS cần tích hợp đúng với security filter và CSRF exception theo phạm vi. Không dùng `csrf.disable()` toàn ứng dụng như giải pháp mặc định.
- **Phân quyền:** identity claims/attributes phải được ánh xạ thành authorities theo chính sách; xác thực thành công không mặc nhiên trao quyền quản trị.
- **Metadata công bố:** thông tin entity ID, ACS và public certificate có thể cần IdP truy cập; tránh nhúng dữ liệu nội bộ/secret vào SP metadata.
- **Giới hạn log:** không log toàn bộ `SAMLResponse`, private key hoặc assertion có dữ liệu cá nhân; redact trước khi chia sẻ log/HAR.
- **Cập nhật security:** tuân BOM và lịch cập nhật Spring Security/OpenSAML đã kiểm thử; theo dõi CVE và migration khi đổi major version.

## 18. Bài tập thực hành có kiểm chứng

**Bài A — xác định lỗi dependency:** dự án khai báo `implementation 'org.springframework.security:spring-security-saml2-service-provider'` nhưng Gradle báo không tải được một module `org.opensaml`. Cần kiểm tra điều gì trước?  
**Đáp án:** xem repository effective của module, có Shibboleth releases (hoặc mirror cung cấp artifact) không, URL có truy cập và trust TLS đúng không; xem phiên bản dependency và BOM. Không chỉnh ACS hay IdP khi lỗi xảy ra ở build.

**Bài B — phân biệt build và login:** `compileJava` pass, ứng dụng bootRun thành công, nhưng IdP báo “unknown SP”. Điều này chứng minh phần nào và thiếu phần nào?  
**Đáp án:** chứng minh compile và startup khả dụng; thiếu/mismatch SP entity ID hoặc cấu hình SP bên IdP. Cần đối chiếu SP metadata, entity ID và ACS với registration phía IdP.

**Bài C — chọn OpenSAML version:** thấy `org.opensaml:opensaml-saml-impl` được kéo bắc cầu. Có nên thêm version OpenSAML mới nhất vào `dependencies`?  
**Đáp án:** không tự nâng rời; xem version Spring Security/BOM và tài liệu hỗ trợ OpenSAML. Nếu cần migration, thực hiện exclusions, modules và integration tests theo hướng dẫn đúng version.

**Bài D — đọc HTTP:** browser GET `/saml2/authenticate/corp`, nhận 302 tới IdP, sau đó POST `SAMLResponse` về `/login/saml2/sso/corp`; server trả 401/403. Có thể khẳng định thiếu OpenSAML?  
**Đáp án:** chưa thể kết luận. Vì ứng dụng đã dựng được luồng request, kiểm tra signature, issuer, audience, destination, expiry, correlation, cookie/session và filter chain. `NoClassDefFoundError` trong log mới là chứng cứ cụ thể hơn về thiếu/incompatible thư viện.

**Bài E — đăng ký thông số:** IdP yêu cầu SP entity ID và ACS. Với registration `corp` ở `https://app.example.org`, hãy xác định giá trị theo convention phổ biến.  
**Đáp án:** entity ID thường `https://app.example.org/saml2/service-provider-metadata/corp`; ACS thường `https://app.example.org/login/saml2/sso/corp`; phải xác nhận metadata/config thực tế và đảm bảo reverse proxy tạo đúng public URL.

## 19. Checklist hoàn thành thiết lập

- [ ] Ứng dụng là Spring MVC/Servlet và dùng Spring Boot/Spring Security tương thích với JDK.
- [ ] Module `spring-security-saml2-service-provider` được khai báo ở ứng dụng SP với scope runtime đúng.
- [ ] Repository Shibboleth releases hoặc mirror được phép chứa các artifact OpenSAML cần thiết.
- [ ] Dependency graph giải quyết được OpenSAML với version tương thích, không override tùy tiện.
- [ ] IdP metadata/issuer/SSO URL/verification certificate được xác minh và đưa vào registration.
- [ ] Signing/decryption credentials của SP được thiết lập nếu giao thức/chính sách IdP yêu cầu, private key được bảo vệ.
- [ ] `SecurityFilterChain` kích hoạt `saml2Login`, endpoint metadata được bật nếu cần cung cấp metadata cho IdP.
- [ ] SP entity ID và ACS public URL khớp chính xác registration tại IdP và reverse proxy.
- [ ] Dependency build + ứng dụng startup + chuyển hướng AuthnRequest + POST SAMLResponse + principal sau xác minh đều được kiểm tra.
- [ ] Cookie, CSRF, session correlation, XML signature, thời gian, audience, replay và kế hoạch quay vòng chứng chỉ được đánh giá.

## 20. Tài liệu đối chiếu

Các đường dẫn dưới đây là tài liệu tham khảo; khi triển khai, ưu tiên **cùng version** với Spring Security/Spring Boot trong dự án:

- Spring Security — SAML 2.0 Login Overview, dependencies, registration, default endpoints: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security 6.5 — OpenSAML Support và cách chọn OpenSAML 4/5: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html
- Spring Security — SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security — Producing SAML AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Boot — Spring Security / SAML 2.0 Relying Party: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- Gradle — Inspecting Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Maven Dependency Plugin — dependency:tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html

**Điểm cần nhớ:** `spring-security-saml2-service-provider` là điểm tích hợp Spring Security; OpenSAML là lớp triển khai SAML/XML ở dưới; dependency management quyết định phiên bản tương thích; metadata và quan hệ tin cậy IdP–SP quyết định khả năng đăng nhập thực tế.
