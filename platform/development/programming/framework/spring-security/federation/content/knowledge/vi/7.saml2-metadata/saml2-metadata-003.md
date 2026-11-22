# Đọc metadata SAML 2.0 từ classpath, tệp và địa chỉ HTTPS đã được tin cậy

## 1. Mục tiêu và phạm vi

Khi ứng dụng Spring Security tham gia **federation SAML 2.0**, một Service Provider (SP, còn gọi Relying Party/RP) phải biết **Identity Provider (IdP, còn gọi Asserting Party/AP) nào đáng tin**, endpoint Single Sign-On (SSO) nào cần gọi, issuer nào phải chấp nhận và những khóa công khai nào dùng để xác minh chữ ký SAML. Thông tin này thường được trao đổi bằng **SAML metadata XML**.

Bài học giải quyết trực tiếp câu hỏi: **đưa XML metadata IdP vào Spring Security bằng cách nào khi nguồn là classpath, một tệp trên máy chủ hoặc URL HTTPS đã được thẩm định?** Việc đọc metadata mới là bước cấu hình; tính xác thực của nguồn, chữ ký, chính sách cập nhật và kiểm thử phản hồi SAML vẫn cần được xử lý riêng.

Sau bài, bạn có thể:

- Phân biệt **metadata IdP** đầu vào với **metadata SP** đầu ra.
- Nhận biết `EntityDescriptor`, `EntitiesDescriptor`, `IDPSSODescriptor`, `KeyDescriptor`, `SingleSignOnService`, `entityID` và các thuộc tính `Binding`/`Location`.
- Dùng `RelyingPartyRegistrations.fromMetadataLocation(...).registrationId(...).build()` với ba nguồn `classpath:`, `file:` và `https:`.
- Tích hợp nguồn metadata vào một ứng dụng Spring Boot Servlet bằng Spring Security và cấu hình tránh lộ bí mật.
- Đánh giá nguy cơ giả mạo metadata, thay khóa signing certificate, HTTPS giả, SSRF do URL tùy ý và sự cố metadata endpoint.
- Phân biệt snapshot được tải lúc khởi tạo với cách làm mới metadata qua repository/cache; kiểm thử đường đi từ build đến đăng nhập.
- Chẩn đoán lỗi tài nguyên, XML, metadata không khớp, đường dẫn bị sai khi đóng gói JAR và lỗi chứng chỉ.

**Giả định kỹ thuật:** ứng dụng **Spring Boot 3.x và Spring Security 6.x (Servlet/MVC), Java 17 trở lên**. Một số API nâng cao dành cho Spring Security 7.1+ được ghi rõ riêng. Tên miền `idp.example.org` và `app.example.org` trong bài là **ví dụ minh họa**, không phải endpoint IdP đang hoạt động.

## 2. Metadata IdP là gì? Có phải SAML Response không?

**Metadata** là tài liệu mô tả cấu hình federation, không phải bằng chứng một người dùng đã đăng nhập. Metadata IdP thường cung cấp:

| Trường XML | Ý nghĩa với Spring Security SP |
| --- | --- |
| `EntityDescriptor@entityID` | Định danh chính thức của IdP; phải đối chiếu với issuer của SAML Response |
| `IDPSSODescriptor@protocolSupportEnumeration` | Vai trò IdP và giao thức SAML 2.0 hỗ trợ |
| `SingleSignOnService@Binding` | Cách IdP **nhận AuthnRequest**: Redirect/POST tùy cấu hình |
| `SingleSignOnService@Location` | Địa chỉ SSO của IdP |
| `KeyDescriptor use="signing"` | Thông tin public certificate/key dùng cho xác minh chữ ký của IdP |
| `SingleLogoutService` | Endpoint/binding cho Single Logout nếu IdP cung cấp |
| `validUntil`, `cacheDuration` | Thông tin thời hạn/caching metadata theo tài liệu và chính sách liên quan |
| `ds:Signature` (nếu có) | Chữ ký bảo vệ **tài liệu metadata**; khác chữ ký của Response/Assertion |

Ví dụ **cấu trúc XML tối giản** để đọc tên phần tử, chưa đủ để đăng nhập thực vì không có chứng chỉ, ký và cấu hình đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/issuer">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Không dùng tài liệu rút gọn trên làm metadata production**: thiếu khóa xác minh chữ ký và nhiều điều kiện quan hệ tin cậy. Metadata thật thường bao gồm một hay nhiều X.509 certificate dưới `KeyDescriptor` và có thể bao cả `EntitiesDescriptor` với nhiều entity.

Một SAML Response thường theo browser đến Assertion Consumer Service (ACS) khi người dùng đăng nhập; Spring Security xác minh chữ ký assertion/response bằng **public key của IdP đã được tin cậy từ cấu hình**, kiểm tra issuer, audience, destination, thời hạn và các điều kiện. **Đọc được metadata XML chưa chứng minh SAML Response đến từ IdP hợp lệ**.

### Ranh giới SP metadata và IdP metadata

- **IdP metadata đầu vào:** Spring SP nạp nhằm biết IdP phát issuer nào, nhận request ở đâu, ký response bằng chứng chỉ gì.
- **SP metadata đầu ra:** Spring có thể công bố `SPSSODescriptor` với SP entity ID, ACS URL và public certificate của SP để bên IdP đăng ký ứng dụng. Để bật endpoint công bố metadata trong Spring Security, cần `.saml2Metadata(... )` theo cấu hình thích hợp.
- **Metadata URL không phải login URL.** Không thay `metadata-uri` bằng địa chỉ trang login HTML, URL tài nguyên SOAP hay một URL chỉ trả 302 liên tục.

## 3. Cách Spring Security biểu diễn metadata

Ở lớp cấu hình, `RelyingPartyRegistration` mô tả **mối quan hệ giữa một SP và một IdP**. Nó gồm phần SP (entity ID, ACS, khóa signing/decryption nếu cần) và phần IdP (entity ID, SSO location/binding, public verification credentials, v.v.).

Các thành phần hay gặp:

- `RelyingPartyRegistrations`: tiện ích dựng registration từ IdP metadata XML.
- `RelyingPartyRegistrationRepository`: hợp đồng tìm registration theo `registrationId`.
- `InMemoryRelyingPartyRegistrationRepository`: repository chứa registration đã tạo trong bộ nhớ; phù hợp snapshot cấu hình khởi tạo.
- `Saml2WebSsoAuthenticationRequestFilter`: khởi tạo AuthnRequest theo registration.
- `Saml2WebSsoAuthenticationFilter`: xử lý SAMLResponse ở ACS, dùng registration và provider xác minh.
- `OpenSAML`: thư viện xử lý SAML/XML được Spring Security sử dụng ở tầng triển khai.

Cách tạo registration phổ biến:

~~~java
RelyingPartyRegistration registration = RelyingPartyRegistrations
        .fromMetadataLocation("classpath:saml/corp-idp.xml")
        .registrationId("corp")
        .build();
~~~

Đoạn này là **mảnh code trong một ứng dụng Java có Spring Security SAML SP**, không thể biên dịch với JDK trống không có dependency. Phương thức `fromMetadataLocation` được Spring Security công bố hỗ trợ **classpath**, **file** và **HTTPS**. Hãy đặt `registrationId("corp")` có ý nghĩa, vì URL nguồn metadata hiếm khi phù hợp làm registration ID.

### Bộ ba cùng một contract

| Nguồn | Giá trị `metadataLocation` | Nơi dữ liệu thực sự tồn tại |
| --- | --- | --- |
| Classpath | `classpath:saml/corp-idp.xml` | `src/main/resources/saml/corp-idp.xml` đã được đóng gói vào classpath |
| Tệp | `file:/etc/myapp/saml/corp-idp.xml` | Tệp trên filesystem của **môi trường chạy ứng dụng** |
| HTTPS tin cậy | `https://idp.example.org/saml/metadata` | Metadata endpoint thật do IdP kiểm soát, qua TLS được xác minh |

**Chuỗi location do SP chọn và tin cậy trước.** Không chấp nhận URL metadata do một người dùng chưa xác thực hoặc request bên ngoài gửi tùy ý rồi dùng nó để xây dựng trust cho SAML: có thể gây SSRF và tin cậy nhầm IdP.

## 4. Nền tảng Gradle/Spring Boot để chạy ví dụ

Ứng dụng phải dùng **Servlet/MVC** và có SAML 2.0 Service Provider module. Nếu dự án Spring Boot đã quản lý phiên bản dependency, trong `build.gradle` module ứng dụng cần cấu hình tương đương:

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

Đây là **đoạn đặt vào build Gradle của dự án hiện có**, không phải toàn bộ `build.gradle`. Nếu tổ chức cấu hình repository trong `settings.gradle`/`dependencyResolutionManagement` hoặc mirror nội bộ, thêm Shibboleth releases theo cơ chế đó; đừng thêm repository dự án bị chính sách chặn. Dependency Spring Security cần theo BOM của Boot để tránh trộn OpenSAML không tương thích.

Với Maven, thêm dependency `org.springframework.security:spring-security-saml2-service-provider` vào POM có BOM tương thích và repository Shibboleth releases khi cần. Bài này tập trung **nguồn metadata**, nên không tự dựng provider SAML từ XML/HTTP.

Đối với ứng dụng WebFlux thuần Reactive, không mặc nhiên áp dụng các Servlet filter và ví dụ ở đây.

## 5. Một cấu hình Java duy nhất cho cả ba loại nguồn

Trong module ứng dụng Boot, tạo tệp `src/main/java/com/example/federation/SamlMetadataConfiguration.java`:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.saml2.provider.service.registration
        .InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrations;

@Configuration
public class SamlMetadataConfiguration {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository(
            Environment environment) {

        String metadataLocation =
                environment.getRequiredProperty("saml.idp.metadata-location");

        RelyingPartyRegistration registration = RelyingPartyRegistrations
                .fromMetadataLocation(metadataLocation)
                .registrationId("corp")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }
}
~~~

> **Giới hạn ví dụ:** lớp trên là Spring `@Configuration` nằm trong dự án Boot đã có `@SpringBootApplication`, đủ dependency SAML, IdP metadata thật và phạm vi component scan bao phủ `com.example.federation`. Nó **không** là chương trình Java độc lập để chạy `javac SamlMetadataConfiguration.java` bằng JDK trống. Không có stdout cố định vì kết quả phụ thuộc môi trường và metadata.

Cách hoạt động:

1. `Environment.getRequiredProperty` yêu cầu ứng dụng có cấu hình `saml.idp.metadata-location`. Thiếu cấu hình khiến startup thất bại rõ ràng, thay vì dùng một IdP bất kỳ.
2. `fromMetadataLocation` nạp và phân tích IdP metadata từ location cho trước theo Spring Security.
3. `registrationId("corp")` gắn một ID ổn định để client/browser dùng URL Spring tương ứng.
4. `InMemoryRelyingPartyRegistrationRepository` giữ registration kết quả; **nó không tự biến thành dịch vụ refresh metadata liên tục**.
5. Spring Boot sẽ dùng bean repository bạn cung cấp thay cho bean auto-configuration tương ứng; không cần tạo thêm bản cấu hình `spring.security.saml2.relyingparty.registration.corp` cạnh tranh cùng ID.

Tạo `src/main/resources/application.yml` cho **một** trong ba lựa chọn sau (chọn một giá trị cho cùng key, không lặp key YAML).

### Chọn nguồn classpath

~~~yaml
saml:
  idp:
    metadata-location: "classpath:saml/corp-idp.xml"
~~~

### Chọn nguồn file hệ điều hành

~~~yaml
saml:
  idp:
    metadata-location: "file:/etc/myapp/saml/corp-idp.xml"
~~~

### Chọn nguồn HTTPS đã được cho phép

~~~yaml
saml:
  idp:
    metadata-location: "https://idp.example.org/saml/metadata"
~~~

Điểm quan trọng: `saml.idp.metadata-location` là **property riêng của ví dụ**, do bean ở trên đọc. Nó **không phải** property auto-configuration SAML của Boot. Một dự án dùng Boot trực tiếp có thể dùng:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp.xml"
~~~

Cấu hình này thuộc **phương án Boot tự tạo RelyingPartyRegistrationRepository**; không đồng thời dùng với bean repository thủ công cho cùng registration. Cấu trúc YAML `assertingparty.metadata-uri` có trong tài liệu Spring Boot/Spring Security các phiên bản tương ứng; hãy đối chiếu version của ứng dụng.

### SecurityFilterChain để nhận SAML login

Nếu dự án cần chain tùy chỉnh, tệp `src/main/java/com/example/federation/SamlSecurityConfiguration.java`:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
~~~

- `saml2Login` thiết lập bộ lọc SSO Servlet; endpoint khởi tạo phổ biến `/saml2/authenticate/corp`, ACS phổ biến `/login/saml2/sso/corp`.
- `saml2Metadata` chủ động bật endpoint **công bố metadata SP** như `/saml2/metadata/corp` để IdP nhập SP metadata; nó **không đọc IdP metadata** hộ cho bean.
- Tên endpoint có thể tùy chỉnh; không thay đổi mặc định nếu IdP/ACS đã đăng ký mà chưa phối hợp.
- Hai tệp `SamlMetadataConfiguration.java` và `SamlSecurityConfiguration.java` là cấu hình ghép được trong cùng dự án; phải có main application, dependency và metadata hợp lệ để chạy.

## 6. Đọc metadata từ classpath

### Cách đưa file vào dự án

Cấu trúc tối thiểu:

~~~text
src/
  main/
    java/
      com/example/federation/
        SamlMetadataConfiguration.java
        SamlSecurityConfiguration.java
    resources/
      application.yml
      saml/
        corp-idp.xml
~~~

Tệp `corp-idp.xml` là **metadata thực do IdP cung cấp**, không phải XML rút gọn tự tạo. Trước khi lưu file vào source repository, xác minh bên cung cấp metadata, entity ID, chứng chỉ và thời hạn. Metadata thường chỉ chứa **public certificate**, không phải private key; dù vậy vẫn phải tuân chính sách thông tin nội bộ và review khi đổi key.

Dùng:

~~~text
classpath:saml/corp-idp.xml
~~~

Spring tìm tài nguyên qua **runtime classpath**, không qua thư mục làm việc hiện tại. Với Gradle hoặc Maven thông thường, nội dung `src/main/resources` được đóng gói dưới classpath; trong executable Spring Boot JAR tài nguyên có thể ở `BOOT-INF/classes/saml/corp-idp.xml`. Đừng chuyển `classpath:` thành đường filesystem giả như `src/main/resources/...` khi chạy ở production.

**Ưu điểm classpath:**

- Metadata đi kèm cùng version của ứng dụng, dễ review, ký/kiểm soát trong chuỗi build.
- Không phụ thuộc network availability của IdP metadata endpoint khi startup.
- Bản dựng container/JAR nhất quán nếu artifact đã được kiểm tra.

**Đổi lại:**

- Khi IdP quay vòng signing certificate hoặc đổi SSO URL, bản snapshot có thể lỗi thời; phải cập nhật file, build và redeploy (hoặc cơ chế riêng).
- Có nguy cơ file khác môi trường nếu developer local và production dùng bản JAR khác.
- Không nên ghi đè file classpath **bên trong executable JAR đang chạy**; đó là immutable artifact.

### Cách kiểm tra file thực sự được đóng gói

Gradle, khi module có task `processResources` và `bootJar`:

~~~bash
./gradlew processResources
./gradlew bootJar
~~~

Sau đó liệt kê JAR bằng `jar tf` (thay đúng tên JAR đã tạo):

~~~bash
jar tf build/libs/my-application.jar
~~~

Tìm `BOOT-INF/classes/saml/corp-idp.xml` trong danh sách file nếu là Boot executable JAR. Không có stdout chung cố định vì tên artifact/task phụ thuộc dự án.

**Lỗi thường gặp:** `FileNotFoundException: class path resource [saml/corp-idp.xml] cannot be opened`. Kiểm tra tên file, chữ hoa/thường (đặc biệt Linux), đường tương đối sau `classpath:`, thư mục `src/main/resources` và cấu hình processResources. Đừng đổi sang URL Internet để “chữa” một lỗi đóng gói.

## 7. Đọc metadata từ tệp trên filesystem

Dùng:

~~~text
file:/etc/myapp/saml/corp-idp.xml
~~~

Đây là URL/resource location trỏ đến **filesystem mà tiến trình Java nhìn thấy tại runtime**. Trong Docker/Kubernetes, đó thường là **đường bên trong container**, không phải đường host của developer.

### Sử dụng phù hợp

- Tệp metadata được cấp bởi config management, volume mount, Kubernetes ConfigMap, hoặc công cụ phát hành cấu hình.
- Ứng dụng có thể thay đổi metadata giữa các lần triển khai mà không cần sửa JAR.
- Đơn vị vận hành muốn quản lý chứng chỉ/trust metadata theo quy trình riêng.

**Không coi “file local” là tự nhiên an toàn.** Nếu một tiến trình hoặc người dùng không được tin cậy có thể sửa file, họ có thể thay issuer/endpoint/chứng chỉ IdP. Đó là thay đổi trust boundary, không chỉ sửa cấu hình bình thường.

### Quy tắc file thực tế

1. Dùng path **tuyệt đối** và xác định, ví dụ `file:/etc/myapp/saml/corp-idp.xml`. Hạn chế path tương đối vì working directory thay đổi giữa IDE/service/container.
2. Đảm bảo file XML tồn tại **trước khi tạo bean repository**, có quyền đọc đối với tài khoản chạy ứng dụng và quyền ghi chỉ dành cho quy trình quản lý cấu hình được ủy quyền.
3. Trong container, kiểm tra mount, namespace, symlink và quyền file; host path không có nghĩa container thấy đúng path.
4. Nếu muốn thay file mà ứng dụng không bắt phải restart, cần cơ chế reload/refresh rõ ràng; **thay file trên đĩa không làm InMemory repository tự dựng lại**.
5. Khi cập nhật file, thường nên viết vào file tạm rồi đổi tên nguyên tử trong cùng filesystem, kiểm tra phiên bản và tính hợp lệ trước khi kích hoạt; tránh để tiến trình đọc file XML mới chỉ ghi được một nửa.
6. Ghi nhận version/nguồn/fingerprint metadata trong hệ thống quản lý thay đổi. Không in toàn bộ certificate/metadata trên log nếu không cần.

**Windows:** URI file có cú pháp khác path Windows thuần (ví dụ định dạng `file:///C:/saml/corp-idp.xml`); sử dụng `Path.toUri()` khi chuyển đổi từ `Path` để hạn chế sai escape hoặc dấu `\\`. Không giả định đường Linux áp dụng cho mọi OS.

### Trường hợp Kubernetes

Một ConfigMap có thể mount metadata ở `/etc/myapp/saml/corp-idp.xml`; người vận hành cập nhật ConfigMap nhưng pod/service có thể giữ đối tượng repository đã dựng lúc boot. Cần chọn **rolling restart** hoặc triển khai refresh đã được thử nghiệm. Ngoài ra, bảo đảm volume mount và file permission nhất quán giữa các replica; nếu một pod dùng key cũ và pod khác dùng key mới, người dùng có thể đăng nhập thất thường.

## 8. Đọc metadata từ HTTPS tin cậy

Dùng:

~~~text
https://idp.example.org/saml/metadata
~~~

Spring Security có thể tải và parse XML metadata từ HTTPS endpoint khi `fromMetadataLocation` được gọi. **HTTPS bảo vệ kết nối vận chuyển và xác nhận chứng chỉ máy chủ theo TLS truststore/hostname verification**, nhưng nó **không tự bảo đảm** rằng endpoint chứa metadata của **đúng đối tác federation**.

Trước khi chấp nhận HTTPS metadata vào trust của SP, cần xác nhận:

- URL được cấp qua kênh giao tiếp chính thức với IdP/đội bảo mật, và **host/path được allow-list**; không lấy URL từ form/HTTP parameter.
- URL có scheme `https`, đúng hostname; TLS certificate chain hợp lệ với truststore của Java; hostname verification không bị vô hiệu.
- Response trả metadata XML kỳ vọng, không phải trang HTML login, trang lỗi của reverse proxy hoặc tài liệu từ endpoint được redirect qua host không được phê duyệt.
- `EntityDescriptor@entityID` đúng entity ID đã xác nhận ngoài luồng; `IDPSSODescriptor`, SSO binding/Location và signing certificate khớp IdP mong đợi.
- Nếu metadata **có chữ ký và yêu cầu xác minh**, trust anchor cho metadata signature phải được cung cấp **độc lập** với nội dung mà metadata vừa tải; không dùng chính một certificate chưa tin trong XML để tự xác nhận XML đó.
- Có chính sách đối với network timeout, HTTP status, metadata XML quá lớn, số entity ngoài dự kiến, metadata hết hạn, HTTP redirects và lịch refresh.
- Chỉ cho phép những endpoint/host cần thiết ở lớp egress proxy/DNS/network; cần tính đến DNS rebinding/SSRF nếu metadata URL có thể thay đổi theo input.

### Vì sao không dùng URL do người dùng nhập?

Nếu ứng dụng cung cấp một API kiểu “đăng ký IdP mới” cho mọi người và gọi `fromMetadataLocation(url)` ngay với URL đó, kẻ xấu có thể ép server truy cập:

- Endpoint nội bộ của cloud/cluster hoặc một service mạng riêng (**SSRF**).
- URL trả về metadata tự tạo với issuer, SSO URL và certificate do kẻ xấu kiểm soát.
- Redirect chain chuyển từ HTTPS hợp lệ sang nguồn khác không được phép.
- XML rất lớn, gây tải tài nguyên hoặc làm startup thất bại.

Muốn hỗ trợ multi-tenant federation động, phải có **quy trình phê duyệt đối tác, allow-list hostname/path, hạn chế egress, xác minh metadata/issuer/signature, rate limit và audit**. Một câu lệnh “chỉ cho URL bắt đầu bằng https://” chưa đủ.

### Phân biệt ba lớp tin cậy

| Lớp | Cần kiểm tra | Điều không thể suy ra |
| --- | --- | --- |
| **Nguồn tải** | Host/path được duyệt, HTTPS hợp lệ, response không bị redirect tới nguồn lạ | HTTPS không tự chứng minh entityID đúng đối tác |
| **Tài liệu metadata** | XML, issuer, hiệu lực, signing key và metadata signature theo chính sách | XML parse thành công không đồng nghĩa XML đáng tin |
| **SAML Response runtime** | Chữ ký response/assertion, issuer, audience, destination, recipient, thời gian, replay/correlation | Metadata đã tin không đồng nghĩa mọi response đều hợp lệ |

Không tắt TLS certificate validation, không bỏ metadata signature validation khi chính sách yêu cầu, và không tắt kiểm tra chữ ký SAML Response chỉ để integration chạy qua.

### Tải bản snapshot một cách có kiểm soát

Nếu tổ chức muốn **thẩm định metadata HTTPS một lần rồi đóng gói làm file**, quản trị viên có thể tải từ URL IdP chính thức bằng công cụ như:

~~~bash
curl --fail --show-error --silent \
  --proto '=https' --proto-redir '=https' \
  --max-time 20 \
  --output corp-idp.xml \
  'https://idp.example.org/saml/metadata'
~~~

Lệnh minh họa chỉ tải file; nó **không tự xác nhận signature/issuer/certificate**. Nếu công cụ theo redirect, cần xem quy tắc redirect và hostname allow-list trước khi dùng file. Hãy xác minh tệp theo quy trình đối tác rồi nhập vào repository/config management; không gọi lệnh này trực tiếp với endpoint ví dụ.

Không đánh đồng SSL pinning, TLS CA trust, signed metadata và signed assertion: chúng bảo vệ **các đối tượng khác nhau**.

## 9. Kiểm tra metadata XML có đúng IdP không?

Khi metadata được nạp, phải hiểu cấu trúc và chọn đúng entity.

### Ví dụ dạng EntityDescriptor

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/issuer">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso/redirect"/>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://idp.example.org/saml/sso/post"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

Cả hai SingleSignOnService ở trên chỉ nói **IdP nhận AuthnRequest** bằng binding nào. Chúng **không** nói SP phải nhận SAMLResponse bằng hai binding đó; ACS của SP và cấu hình phản hồi ở IdP là phần khác. Ví dụ XML vẫn thiếu signing certificate; dùng để đọc cấu trúc, không để đăng nhập.

### Metadata có nhiều entity

Một file có thể chứa `EntitiesDescriptor` với nhiều `EntityDescriptor`. Khi ấy cần lựa chọn **entity ID chính xác** (không lấy entity đầu tiên tùy tiện). Spring Security cung cấp `collectionFromMetadataLocation(... )` để có thể đọc nhiều registration builder, nhưng việc map mỗi builder thành `registrationId` ổn định là trách nhiệm ứng dụng.

Ví dụ minh họa:

~~~java
Collection<RelyingPartyRegistration.Builder> builders =
        RelyingPartyRegistrations.collectionFromMetadataLocation(
                "classpath:saml/partners.xml");
~~~

Đây là **mảnh code**, cần import và nằm trong dự án Spring Security. Dùng cách này khi thực sự quản lý nhiều đối tác; không biến một IdP single-entity thành nhiều registration không cần thiết. Khi chọn, phải xác nhận issuer, SSO Location, signing certificate và phạm vi tenant; không sinh ID ngẫu nhiên ở mỗi lần khởi động nếu muốn URL login ổn định.

### Trường hợp file chứa SPSSODescriptor

Nếu bạn truyền nhầm **metadata SP** (`SPSSODescriptor`) vào `fromMetadataLocation` vốn nhằm tải **IdP metadata** (`IDPSSODescriptor`), registration có thể thiếu thông tin SSO, chứng chỉ IdP hoặc gây lỗi. Sửa nguồn đầu vào, không tự bịa IdP URL từ SP ACS.

## 10. Chữ ký metadata không giống chữ ký Assertion

Có hai quyết định cần tách rõ.

**Quyết định A — có tin tài liệu IdP metadata được nạp không?** Một tệp XML có thể được lấy từ nguồn đáng tin, cấp qua quy trình kiểm duyệt và version control; hoặc có XML signature cần xác minh bằng trust anchor ngoài luồng. Metadata có thể thiếu chữ ký; khi đó phải có kênh và cơ chế khác để xác nhận nguồn/tính toàn vẹn. Nếu URL đã bị thay bằng domain của kẻ tấn công mà bạn tự tin certificate mới trong metadata, toàn bộ SSO trust bị thay đổi.

**Quyết định B — có chấp nhận SAML Response/Assertion gửi trong lần login này không?** Spring Security dùng public verification credential của IdP để kiểm tra chữ ký SAML, đồng thời kiểm tra issuer, destination, audience, thời hạn, SubjectConfirmation và các điều kiện liên quan.

| Chủ thể ký | Đối tượng được ký | Mục tiêu |
| --- | --- | --- |
| Nhà phát hành metadata có thẩm quyền | Metadata XML | Chứng minh metadata đúng nguồn và chưa bị sửa theo trust policy |
| IdP | SAML Response / Assertion | Cho SP kiểm tra tính toàn vẹn/nguồn phát hành thông điệp xác thực |
| SP nếu IdP yêu cầu | AuthnRequest | Cho IdP kiểm tra request từ SP |
| Web server TLS | Kết nối HTTPS | Cho client kiểm tra server TLS và bảo vệ kênh truyền |

**Không lấy chứng chỉ ký SAML Response trong metadata chưa được tin để tự xác nhận tính đáng tin của metadata.** Cần bootstrapping trust theo quy trình thẩm định.

### API làm mới/xác minh metadata ở Spring Security mới

Ở Spring Security phiên bản có `AssertingPartyMetadataRepository` và `OpenSaml5AssertingPartyMetadataRepository` (được mô tả trong tài liệu Spring Security 7.1), một repository chuyên về IdP metadata có thể dùng cơ chế OpenSAML `MetadataResolver` để xử lý hết hạn/làm mới.

Tài liệu phân biệt:

- `OpenSaml5AssertingPartyMetadataRepository.fromTrustedMetadataLocation("https://...").build()`: hướng tiếp cận với metadata **được coi là đã tin qua nguồn/location theo chính sách**; xem tài liệu version để hiểu ngữ nghĩa.
- `OpenSaml5AssertingPartyMetadataRepository.withMetadataLocation("https://...").verificationCredentials(...).build()`: cho phép cung cấp **credentials độc lập để xác minh metadata signature**.
- Theo tài liệu, **nếu không cung cấp verification credentials cho cấu hình xác minh này, component sẽ không thực hiện signature validation**. Không nhầm tên “trusted” với việc hệ thống tự xác thực một chữ ký metadata bằng khóa ngoài luồng mà bạn chưa cung cấp.

Các API nêu trên là tùy chọn nâng cao, **không bắt buộc** để hiểu/triển khai cách đọc metadata cơ bản trên Spring Security 6.x. Nếu cần chúng, chọn đúng version hỗ trợ, API signature và lifecycle; tuyệt đối không sao chép API 7.1 sang bản 6.1 mà không kiểm tra tương thích.

## 11. Metadata hết hạn, refresh, certificate rollover

Một cấu hình đọc đúng hôm nay có thể lỗi sau vài tuần khi IdP thay SSO URL/chứng chỉ. Tệp metadata thường có các thuộc tính:

- `validUntil`: mốc metadata không nên tiếp tục được chấp nhận sau thời điểm được quy định; cần xem validation/expiry behavior của implementation.
- `cacheDuration`: gợi ý thời gian cache theo metadata profile; không phải đảm bảo Spring Boot tự gọi URL theo chu kỳ.
- `KeyDescriptor` chứa nhiều signing certificate: IdP có thể công bố đồng thời **khóa cũ và mới** trong giai đoạn rollover.
- Signed metadata có thể thay đổi metadata signing key theo quy trình riêng, không nhất thiết đồng thời với SAML Response signing key.

### Hành vi của ba nguồn

| Nguồn | Đổi metadata ở IdP có cập nhật ứng dụng ngay? | Cách vận hành hợp lý |
| --- | --- | --- |
| Classpath snapshot | **Không**; nội dung gắn với artifact | Review file mới → build → deploy → test |
| File filesystem + InMemory repository | **Không tự reload** chỉ vì file trên disk đổi | Thay file có kiểm tra → restart hoặc làm mới repository được thiết kế |
| HTTPS + `fromMetadataLocation` + InMemory repository | Không giả định tự refresh sau khi bean tạo | Chính sách refresh/cache rõ ràng, hoặc restart có kiểm soát |
| Dynamic metadata repository có expiry-aware resolver | Có thể làm mới theo cơ chế resolver/cache implementation | Bổ sung trust/signature, expiry, timeout, failure policy và kiểm thử vận hành |

**Mẫu operational timeline khi IdP quay vòng cert:**

1. IdP công bố metadata đã kiểm chứng có khóa **hiện tại và khóa mới**, thông báo thời điểm chuyển.
2. SP nhập metadata mới vào trust config/refresh repository, vẫn giữ được credential cũ trong giai đoạn overlap khi chính sách cho phép.
3. Test SSO với assertion ký bằng từng key trong phạm vi hỗ trợ/trust; theo dõi log xác minh.
4. Khi IdP ngừng dùng key cũ và thông tin công bố đã ổn định, loại key cũ theo change management.
5. Không “sửa gấp” bằng cách bỏ kiểm tra chữ ký hoặc chấp nhận mọi certificate đi kèm response.

### CachingRelyingPartyRegistrationRepository

Spring Security cũng có cách dựng repository từ **supplier** và **cache**:

~~~java
Supplier<IterableRelyingPartyRegistrationRepository> delegate = () ->
        new InMemoryRelyingPartyRegistrationRepository(
                RelyingPartyRegistrations
                        .fromMetadataLocation("https://idp.example.org/saml/metadata")
                        .registrationId("corp")
                        .build());

CachingRelyingPartyRegistrationRepository registrations =
        new CachingRelyingPartyRegistrationRepository(delegate);

registrations.setCache(cacheManager.getCache("saml-registrations"));
~~~

Đây là **đoạn cấu hình chuyên biệt** tham khảo tài liệu Spring Security, cần import, bean `CacheManager` hợp lệ và xử lý lifecycle trong dự án. `CacheManager` cần cấu hình TTL/eviction; việc refresh phụ thuộc **lúc entry bị loại khỏi cache** và lúc supplier được gọi lại, không phải một promise rằng IdP được tải lại theo lịch cố định. Khi remote URL down vào lúc cache miss, có thể phát sinh lỗi; cần chính sách có kiểm chứng về failure, retry và “last known good” theo an ninh (không chấp nhận metadata quá hạn chỉ vì tiện vận hành).

## 12. Dùng InputStream khi metadata đến từ nguồn khác

Ba location là cách dễ hiểu nhất, nhưng khi XML được lấy qua API nội bộ có kiểm soát, database hoặc artifact store, Spring Security còn có builder nhận `InputStream`. Ví dụ bean trong dự án có nguồn XML **đã xác minh**:

~~~java
package com.example.federation;

import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.ClassPathResource;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrations;

public final class SamlMetadataLoader {

    private SamlMetadataLoader() {
    }

    public static RelyingPartyRegistration fromResource() throws IOException {
        ClassPathResource resource =
                new ClassPathResource("saml/corp-idp.xml");

        try (InputStream input = resource.getInputStream()) {
            return RelyingPartyRegistrations
                    .fromMetadata(input)
                    .registrationId("corp")
                    .build();
        }
    }
}
~~~

Đây là **lớp helper cần Spring Security/OpenSAML/Spring Resource trên classpath**. Nó không tự chạy với `java SamlMetadataLoader` vì không có `main()` và không tạo IdP thật. Quan trọng là `try-with-resources` đóng stream đúng cách; metadata được parse trước khi stream đóng.

API `fromMetadata(InputStream)` cho phép tách **quá trình lấy/kiểm duyệt nguồn XML** khỏi **quá trình Spring dựng registration**. Đây không phải lý do để tải XML từ URL tùy ý do client cung cấp. Nếu sử dụng database, vẫn phải có nguồn tin cậy, chữ ký/trust và chính sách rollover.

## 13. Java 17 chạy độc lập: kiểm tra chính sách location trước khi nạp

Để thấy location có thể đến từ **ba nguồn nhưng đều cần phê duyệt**, ví dụ Java 17 dưới đây kiểm tra ba location được phép theo **allow-list cố định** và từ chối host HTTPS khác. Nó **không thực hiện network request**, **không phân tích XML** và **không thay thế kiểm tra TLS, metadata signature hay SAML Response**.

Tệp `MetadataLocationPolicyDemo.java`:

~~~java
import java.net.URI;
import java.util.Set;

public class MetadataLocationPolicyDemo {

    private static final Set<String> APPROVED_LOCAL = Set.of(
            "classpath:saml/corp-idp.xml",
            "file:/etc/myapp/saml/corp-idp.xml"
    );

    static void requireApproved(String location) {
        if (APPROVED_LOCAL.contains(location)) {
            return;
        }

        URI uri = URI.create(location);
        boolean approvedHttps =
                "https".equalsIgnoreCase(uri.getScheme()) &&
                "idp.example.org".equalsIgnoreCase(uri.getHost()) &&
                "/saml/metadata".equals(uri.getRawPath()) &&
                uri.getPort() == -1 &&
                uri.getRawUserInfo() == null &&
                uri.getRawQuery() == null &&
                uri.getRawFragment() == null;

        if (!approvedHttps) {
            throw new IllegalArgumentException("Unapproved metadata location");
        }
    }

    public static void main(String[] args) {
        for (String location : new String[] {
                "classpath:saml/corp-idp.xml",
                "file:/etc/myapp/saml/corp-idp.xml",
                "https://idp.example.org/saml/metadata",
                "https://unknown.example.org/saml/metadata"
        }) {
            try {
                requireApproved(location);
                System.out.println("APPROVED: " + location);
            } catch (IllegalArgumentException ex) {
                System.out.println("REJECTED: " + location);
            }
        }
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac MetadataLocationPolicyDemo.java
java MetadataLocationPolicyDemo
~~~

Stdout **chính xác**:

~~~text
APPROVED: classpath:saml/corp-idp.xml
APPROVED: file:/etc/myapp/saml/corp-idp.xml
APPROVED: https://idp.example.org/saml/metadata
REJECTED: https://unknown.example.org/saml/metadata
~~~

Bài học từ code:

- Chỉ chấp nhận **đúng giá trị cấu hình** được phê duyệt; kiểm tra `startsWith("https://")` không đủ.
- Không nhận mọi path file hoặc host theo wildcard. Khi sản phẩm có nhiều IdP, quản lý danh sách phê duyệt theo đối tác và deployment.
- Hàm này chỉ kiểm tra **chuỗi URL ban đầu**. Nếu client HTTP tự theo redirect, DNS bị can thiệp hoặc XML trả về không đúng entity, vẫn phải có kiểm soát network, TLS, redirect, issuer và signature.
- Việc in ra `APPROVED` không có nghĩa server đã tải được XML hay metadata đã được xác minh; đây chỉ là bài tập tiền xử lý cấu hình.

## 14. Trình tự kiểm tra ba đường nạp

### A. Kiểm tra classpath

1. Đặt **metadata IdP thật** tại `src/main/resources/saml/corp-idp.xml`.
2. Xác nhận byte file và entity ID từ IdP đã được kiểm duyệt; nếu tổ chức quản lý fingerprint, so fingerprint do nguồn đáng tin cung cấp.
3. Cấu hình `classpath:saml/corp-idp.xml`.
4. Build/đóng gói, kiểm tra file có trong runtime classpath/JAR; sau đó khởi động.
5. Thử GET `/saml2/authenticate/corp` bằng browser hoặc HTTP client có môi trường IdP test; phải nhận hướng dẫn đi đúng SSO URL theo metadata.

### B. Kiểm tra file filesystem

1. Tạo/tải XML đã kiểm duyệt tới **đúng máy/container**.
2. Cấp quyền đọc cho user chạy Java; hạn chế quyền ghi cho tiến trình khác.
3. Cấu hình `file:/etc/myapp/saml/corp-idp.xml`.
4. Xác nhận mount/path/quyền đọc và startup.
5. Cập nhật file có backup/version, restart hoặc refresh có kiểm chứng; thử đăng nhập sau cập nhật.

### C. Kiểm tra HTTPS

1. Nhận URL metadata từ IdP qua kênh chính thức, đưa host/path vào allow-list.
2. Kiểm tra endpoint từ môi trường chạy Java, không chỉ từ laptop: DNS, TLS truststore, firewall, proxy, redirects, HTTP status, MIME/contents.
3. Đối chiếu issuer, SSO URL, certificate và thời hạn với thông số IdP đã xác minh.
4. Cấu hình `https://idp.example.org/saml/metadata` với Java/Spring.
5. Khởi động app, đánh giá failure khi URL down/timeout và cách theo dõi/refresh trong production.
6. Thử end-to-end SSO và quy trình cert rotation trong môi trường test.

**Giới hạn QA:** startup thành công chứng minh đọc/parse metadata và tạo bean ở một mức độ, **không** khẳng định xác minh được mọi SAML assertion. Cần một cuộc đăng nhập thành công qua IdP test; và cần bảo đảm assertion sai chữ ký, issuer/audience hoặc thời hạn bị từ chối.

## 15. Quan sát đúng log và endpoint

Với SP registration `corp`, một sơ đồ request phổ biến:

~~~mermaid
sequenceDiagram
    participant D as Deployed Spring SP
    participant M as Metadata source
    participant B as Browser
    participant I as IdP
    D->>M: Load and parse IdP metadata (startup / refresh)
    M-->>D: IdP issuer, SSO endpoint, certificates
    B->>D: GET /private
    D-->>B: Redirect to /saml2/authenticate/corp
    B->>D: GET /saml2/authenticate/corp
    D-->>B: Redirect / form AuthnRequest to IdP
    B->>I: SAML AuthnRequest
    I-->>B: Login / existing IdP session
    B->>D: POST SAMLResponse to ACS
    D->>D: Verify with trusted IdP registration
    D-->>B: App session on success
~~~

Đường **SP → metadata source** là thao tác tải/cấu hình, không phải lần browser đăng nhập nào cũng gọi metadata URL. Đường **browser ↔ IdP ↔ SP** là Web Browser SSO front-channel. Không dùng Network tab của browser để tìm HTTP request do backend Java gọi tới metadata URL; tra server logs, metrics hoặc network trace phía server.

Khi debug, được phép ghi **đường dẫn tài nguyên không nhạy cảm, registrationId, issuer được phê duyệt, HTTP status và timestamp**, nhưng đừng log raw SAMLResponse, session cookie, private key hay toàn bộ assertions có thông tin cá nhân. Trong multi-tenant, kiểm soát log tránh để người dùng xem được danh sách đối tác không dành cho họ.

### Kiểm tra metadata SP được công bố

Nếu bật `.saml2Metadata(Customizer.withDefaults())`, Spring Security có thể trả SP metadata tại:

~~~text
GET /saml2/metadata/corp
GET /saml2/service-provider-metadata/corp
~~~

Metadata này cho IdP biết SP entity ID/ACS. Nó **khác** URL cấu hình `https://idp.example.org/saml/metadata` để SP đọc IdP metadata. Kiểm tra SP metadata hữu ích vì ACS public URL, entity ID và certificate phải được IdP đăng ký đúng.

## 16. Lỗi phổ biến và cách sửa đúng tầng

| Hiện tượng | Nơi cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `ClassPathResource cannot be opened` | Classpath/JAR | Tên file, chữ hoa thường, resource processing và path sau `classpath:` |
| File không tồn tại hoặc Permission denied | Filesystem/container | Mount path và user chạy JVM; path tuyệt đối, quyền đọc |
| `UnknownHostException`, connection timeout | HTTPS/network | DNS, firewall, egress, proxy và URL IdP được duyệt |
| `PKIX path building failed` | HTTPS/TLS | Truststore/CA/cert chain của endpoint; **không tắt TLS verification** |
| HTTP 301/302 tới login page khi lấy metadata | HTTPS endpoint/redirect | Xác nhận đúng metadata URL; không chấp nhận HTML/redirect sang host lạ |
| HTTP 401/403 metadata URL | IdP access policy | Phối hợp IdP về endpoint chính thức và phương thức xác thực hợp lệ |
| Parse error, XML malformed | Nội dung file/response | Kiểm tra XML đúng định dạng, mã hóa, namespace và tải file trọn vẹn |
| Không có `IDPSSODescriptor` | Nhầm SP metadata hoặc entity | Đổi đúng nguồn IdP metadata |
| `Multiple entity/registration ambiguous` | `EntitiesDescriptor` | Chọn entity ID được duyệt, ID ổn định; tránh lấy ngẫu nhiên |
| Sai issuer sau khi SSO | IdP entity ID | So `Issuer` với entity ID được xác nhận, không sửa validation để cho qua |
| Sai SSO binding/URL | Metadata và cấu hình IdP | So `SingleSignOnService@Binding/Location` với AuthnRequest |
| SAML assertion signature invalid | Signing credential IdP | So cert mới/cũ, issuer, certificate metadata được tin cậy và cơ chế rollover |
| SP metadata/ACS trỏ vào localhost | Reverse proxy/forwarded headers | Dùng public scheme/host/port và trusted proxy configuration |
| Build pass nhưng login fail | Runtime federation | Kiểm tra IdP registration, ACS, audience, thời gian, cookie và chữ ký |
| Update XML nhưng app vẫn dùng cert cũ | Snapshot/repository lifecycle | Restart/redeploy hoặc refresh được thiết kế, không chờ reload “tự nhiên” |
| Người dùng phải logout/login liên tục | Cookie/SSO state | Xem session SP, SameSite cookie cross-site POST, correlation, không đoán do metadata |
| Metadata file sửa được bởi service không tin cậy | Local trust boundary | Giới hạn quyền ghi, ownership, version và audit; nhập lại snapshot đã kiểm tra |
| Metadata URI thay bằng URL nội bộ | Dynamic registration/SSRF | Allow-list host/path, hạn chế egress, thẩm định đối tác trước khi nạp |

Phân loại lỗi theo **thời điểm**:

1. **Build dependency fail:** vấn đề JAR/OpenSAML/repository, chưa liên quan metadata XML.
2. **Startup fail khi nạp metadata:** vấn đề đường dẫn, network, TLS, nội dung XML, entity/method.
3. **Redirect tới IdP fail:** vấn đề SSO URL/binding, SP entity ID, signing request hoặc reverse proxy.
4. **Response về ACS nhưng bị từ chối:** vấn đề issuer, signing credentials, audience, destination, time, correlation, cookies hoặc assertion policy.
5. **Sau đổi metadata mới fail:** ưu tiên so version/refresh và key rotation; không mặc định đó là lỗi trình duyệt.

## 17. Tình huống trước–sau: triển khai qua Kubernetes

**Trước:** developer chạy local thành công vì có `src/main/resources/saml/corp-idp.xml`, nhưng CI dựng image mới và production định dùng `file:/opt/metadata/corp.xml` mà chưa mount volume. Service fail lúc startup.

**Cách sửa đúng:**

1. Thống nhất nguồn runtime: nếu muốn image immutable thì dùng classpath; nếu muốn cấu hình theo môi trường thì mount volume/file có kiểm chứng.
2. Khi chọn file, bảo đảm mỗi pod có `/etc/myapp/saml/corp-idp.xml` đúng nội dung và startup user có quyền đọc; cấu hình đúng URI `file:/etc/myapp/saml/corp-idp.xml`.
3. Thay metadata file qua quy trình publish atomically, audit version và rollout. Xác minh issuer/cert/SSO URL trước khi chuyển pod sang bản mới.
4. Test đăng nhập từ browser qua public URL, xác minh ACS nhận POST và phiên SP được tạo.

**Kết luận kỹ thuật:** `classpath:` hay `file:` là **lựa chọn nơi giữ snapshot**; không tự quyết định SAML có đáng tin hay không. Trust và vòng đời metadata phải được quản lý riêng.

## 18. Tình huống trước–sau: IdP đổi signing certificate

**Trước:** SP tải metadata HTTPS một lần lúc khởi tạo và giữ `InMemoryRelyingPartyRegistrationRepository`. IdP đổi certificate sau khi ứng dụng chạy nhiều ngày, dẫn tới SAML Response ký bằng key mới bị từ chối.

**Phân tích:**

- Nếu metadata HTTPS đã đổi nhưng SP chưa reload, SP còn public verification key cũ.
- Nếu metadata đã được reload nhưng chữ ký vẫn lỗi, kiểm tra issuer, signature thực tế, entity ID và chain of trust. Metadata mới từ URL bất ngờ **không tự được tin**.
- Nếu IdP chuyển đột ngột không có overlap, cần phối hợp phát hành metadata/rollback an toàn; đừng bỏ signature validation.

**Cách xử lý:** thiết kế **overlap certificates**, kiểm tra metadata mới bằng nguồn đáng tin, rồi cập nhật snapshot/refresh theo quy trình. Với cached/dynamic repository, nêu rõ eviction, expiry, failure policy và cách quan sát cert rollover. SAML login thành công mới xác nhận cơ chế tích hợp hoạt động trong thực tế.

## 19. Bài tập tự kiểm tra và đáp án

**Bài 1.** Trong dự án Boot, bạn đặt `src/main/resources/saml/corp-idp.xml` rồi cấu hình `file:src/main/resources/saml/corp-idp.xml`. Chạy IDE được nhưng Docker fail. Vì sao?

**Đáp án:** location `file:` phụ thuộc working directory/filesystem lúc chạy. Nếu mục tiêu là file đóng gói, dùng `classpath:saml/corp-idp.xml`; nếu mục tiêu là file ngoài JAR, mount đường tuyệt đối trong container và dùng `file:/...`.

**Bài 2.** Một metadata URL HTTPS trả 200 và XML parse thành công, nhưng issuer không đúng đối tác đã đăng ký. Có được dùng metadata đó để cấu hình login không?

**Đáp án:** không. Phải xác minh issuer/entity ID, SSO endpoint, certificates và nguồn tin cậy trước khi chấp nhận. HTTPS chỉ xác thực kết nối tới host được chỉ định, không chứng minh đó là IdP mà doanh nghiệp định dùng.

**Bài 3.** Dev thêm `RelyingPartyRegistrations.fromMetadataLocation("https://...")` và InMemory repository. Sau hai tuần, IdP đổi signing certificate nhưng app không tự cập nhật. Đây có phải lỗi JDK không?

**Đáp án:** không có bằng chứng. InMemory repository giữ registration được dựng; cần refresh/rebuild rõ ràng hoặc có quy trình redeploy. Đồng bộ metadata/credential theo thông báo IdP.

**Bài 4.** Metadata XML có `SPSSODescriptor` nhưng không có `IDPSSODescriptor`, lập trình viên dùng làm IdP metadata. Điều gì sai?

**Đáp án:** đó là mô tả SP, không phải IdP; không thể suy IdP SSO service và ký IdP từ ACS SP. Nhập đúng IdP metadata.

**Bài 5.** Một quản trị viên tải metadata từ đúng URL nhưng không biết public certificate nào được dùng để ký XML metadata. Có thể lấy certificate bất kỳ từ chính file chưa tin và coi đó là chứng cứ độc lập không?

**Đáp án:** không. Đó là vòng tin cậy tự chứng minh. Cần trust anchor/certificate được cung cấp, xác minh qua kênh độc lập hoặc sử dụng quy trình nguồn artifact đã được phê duyệt; theo chính sách xác minh metadata signature nếu bắt buộc.

**Bài 6.** Đang dùng config `spring.security.saml2.relyingparty.registration.corp.assertingparty.metadata-uri` nhưng đồng thời tự định nghĩa bean repository trỏ sang IdP khác. Tại sao rủi ro?

**Đáp án:** Boot có thể back off auto-configuration khi bean repository riêng đã có; người vận hành tưởng cấu hình YAML điều khiển IdP nhưng thực tế bean riêng mới được dùng. Chọn một nguồn cấu hình và kiểm tra issuer/endpoint sau startup.

**Bài 7.** Browser không hiển thị request GET đến metadata IdP trong Network tab, dù ứng dụng vẫn login được. Có thiếu bước metadata?

**Đáp án:** không. SP server có thể đã nạp metadata lúc startup hoặc qua file/classpath. Browser không phải bên tải mọi metadata; luồng login front-channel riêng với luồng cấu hình ở backend.

**Bài 8.** Một SP vừa nạp metadata file mới sau khi IdP thông báo cert rollover. Kiểm tra tối thiểu nào cần làm?

**Đáp án:** metadata nguồn/issuer/SSO/cert đã được thẩm định; SP registration đúng; SP signing/ACS không bị sửa sai; login test với SAMLResponse hợp lệ và lỗi ký/issuer không được chấp nhận; pod/version mới dùng cùng snapshot.

## 20. Checklist quyết định nguồn metadata

- [ ] Đã xác minh đối tác và đúng entity ID của **IdP**, không nhầm metadata SP.
- [ ] Tài liệu chứa các endpoint/binding SSO và verification certificates cần thiết, đúng SAML 2.0.
- [ ] Có quy trình xác minh nguồn và metadata signature/trust anchor theo chính sách.
- [ ] Nếu classpath: XML nằm trong JAR/classpath và có release/version có thể audit.
- [ ] Nếu file: đường tuyệt đối, mount/permission/quy trình cập nhật được kiểm thử trên môi trường chạy.
- [ ] Nếu HTTPS: endpoint được allow-list, TLS hợp lệ, redirect/SSRF/network timeout được kiểm soát.
- [ ] Không dùng metadata URL do client chưa được duyệt nhập tùy ý để tạo trust.
- [ ] `registrationId` cố định, không đánh đồng với `entityID` của IdP.
- [ ] Đã chọn rõ **Boot property auto-configuration** hoặc **repository bean tự cung cấp**.
- [ ] Có kế hoạch cache/expiry/reload và xử lý signed certificate rollover.
- [ ] Không in raw SAML assertion, cookie, private key hoặc dữ liệu định danh nhạy cảm trong log.
- [ ] Đã thử build, startup, redirect đúng IdP, callback ACS và kiểm tra chữ ký/issuer/audience/thời gian.
- [ ] Đã chuẩn bị rollback khi metadata mới lỗi hoặc IdP endpoint không thể truy cập.

## 21. Ghi nhớ

**Classpath** là metadata snapshot đóng gói cùng ứng dụng; **file** là metadata snapshot nằm trên filesystem runtime; **HTTPS** là metadata từ endpoint IdP phải được kiểm chứng và quản lý như một nguồn trust. Cả ba đi vào cùng API Spring Security:

~~~java
RelyingPartyRegistrations.fromMetadataLocation(location)
        .registrationId("corp")
        .build();
~~~

Cấu hình này chỉ có ý nghĩa khi metadata **đúng đối tác**, certificate được xử lý tin cậy và lifecycle không để ứng dụng giữ metadata quá hạn. Người dùng chỉ được coi là đăng nhập sau khi Spring Security kiểm tra thành công **SAML Response/Assertion**, không chỉ vì metadata tải được.

### Tài liệu tham khảo

- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — SAML 2.0 Metadata, xác minh chữ ký và repository refresh: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security API — `RelyingPartyRegistrations` (hỗ trợ classpath/file/HTTPS): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrations.html
- Spring Security — SAML 2.0 AuthnRequests và metadata SSO: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Boot — SAML 2.0 Single Logout configuration minh họa `assertingparty.metadata-uri`: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- OASIS — SAML 2.0 Metadata for the OASIS Security Assertion Markup Language: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
