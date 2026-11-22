# Xây dựng kho đăng ký có thể làm mới và đánh giá API hỗ trợ theo phiên bản

> **Module:** Spring Security – federation. **Nhóm kiến thức:** Metadata SAML2. Bài học tập trung vào cách tổ chức một `RelyingPartyRegistrationRepository` có khả năng cập nhật metadata của Identity Provider (IdP) khi ứng dụng đang hoạt động, cách bảo đảm thay đổi không phá vỡ quan hệ tin cậy và cách chọn API chính xác theo phiên bản Spring Security.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích tại sao tải metadata SAML một lần lúc khởi động **không tương đương** với tự làm mới metadata trong suốt thời gian chạy.
2. Phân biệt **metadata phía IdP**, **registration phía SP**, **repository**, **cache**, **scheduler**, **last-known-good snapshot**, **signature/issuer trust**, **metadata expiration** và **credential rotation**.
3. Thiết kế cơ chế refresh kiểm tra trước khi thay thế: nguồn cố định, issuer phù hợp, thông tin đăng ký SP bất biến, tập chứng thư tin cậy hợp lệ, thời hạn sử dụng và chính sách khi nguồn lỗi.
4. Dùng các API lõi có mặt từ Spring Security 6.3 để triển khai một repository do ứng dụng tự quản lý, thay snapshot bằng `AtomicReference`.
5. Biết các API được bổ sung ở **Spring Security 6.4+**, gồm `IterableRelyingPartyRegistrationRepository`, `CachingRelyingPartyRegistrationRepository` và `AssertingPartyMetadataRepository`, đồng thời hiểu khi nào dùng metadata resolver của OpenSAML 5.
6. Không nhầm **refresh theo TTL cache** với **refresh theo `validUntil`/`cacheDuration` của metadata**, cũng không nhầm “nhận được chứng thư mới” với “đã xác minh được tính đáng tin của chứng thư mới”.
7. Lập bộ kiểm thử chứng minh refresh đúng, chịu lỗi mạng, tách tenant, ngăn cấu hình sai và tránh cấp quyền truy cập trái phép.

## 1. Bài toán: đăng nhập đang hoạt động thì IdP đổi metadata

Giả sử ứng dụng **Orders Portal** là SAML2 Service Provider (SP), tin vào IdP của đối tác A. Ban đầu metadata IdP mô tả:

~~~text
IdP entityID:       https://idp.partner-a.example.org/saml
SingleSignOnService https://idp.partner-a.example.org/sso
Signing certs:      certificate A
Metadata source:    https://idp.partner-a.example.org/metadata
~~~

Sau một thời gian, IdP thực hiện **certificate rollover**: phát metadata có certificate A và certificate B trong giai đoạn chồng lấn, rồi cuối cùng chỉ còn B. Có thể IdP cũng thay SSO endpoint hoặc Single Logout endpoint. Nếu SP chỉ đọc metadata khi khởi động, repository vẫn lưu snapshot cũ và xác minh response bằng certificate A; khi IdP ngừng ký bằng A, các lượt login mới có thể thất bại.

Một cách khắc phục tạm là khởi động lại SP sau mỗi lần metadata đổi. Nhưng với nhiều IdP/tenant, việc đó gây gián đoạn, phụ thuộc thao tác thủ công và dễ bỏ sót. Vì vậy cần **refresh** có kiểm soát.

Ngược lại, việc cứ 5 phút tải XML và chấp nhận mọi nội dung mới cũng nguy hiểm. Nếu metadata được phát từ nguồn không đáng tin, certificate mới có thể là khóa của kẻ tấn công; khi đó SP đã vô tình thay **trust anchor** của mình. Cơ chế refresh đúng phải vừa cập nhật kịp thời, vừa bảo toàn nguồn tin cậy, ranh giới tenant, tính nhất quán và khả năng phục hồi.

**Quy tắc tổng quát:** tải → xác minh nguồn/tính hợp lệ → xây registration mới → kiểm tra ràng buộc không được đổi ngoài ý muốn → thay toàn bộ snapshot → quan sát kết quả. Nếu có lỗi, **không công bố snapshot mới**.

## 2. Nắm rõ các đối tượng trước khi lập trình

| Đối tượng | Vai trò | Ai quản lý? | Tại sao quan trọng khi refresh? |
| --- | --- | --- | --- |
| **IdP metadata XML** | Mô tả IdP entity ID, các dịch vụ SSO/SLO, bindings, chứng thư ký/mã hóa; có thể chứa `validUntil`, `cacheDuration`. | IdP hoặc nhà cung cấp metadata được ủy thác. | Nguồn dữ liệu biến động cần kiểm tra trước khi tiêu thụ. |
| **`RelyingPartyRegistration`** | Một cấu hình cặp SP–IdP: registration ID, SP entity ID, ACS, SP credentials, IdP details. | SP kết hợp dữ liệu tin cậy của IdP. | Thay đổi IdP metadata **không được xóa nhầm** SP key/ACS/entity ID. |
| **`RelyingPartyRegistrationRepository`** | Giao diện tra cứu registration theo ID. | Ứng dụng/Spring Boot. | Login, callback và metadata filter cần truy xuất cấu hình hiện tại. |
| **`InMemoryRelyingPartyRegistrationRepository`** | Cấu hình registration lưu trong bộ nhớ, có thể lặp để tạo trang chọn đăng nhập/metadata. | Spring Security cung cấp. | Một instance mới là một snapshot đơn giản, dễ thay nguyên tử. |
| **Refresh source/loader** | Tải, parse metadata và dựng tập registration đề xuất. | Ứng dụng hoặc thư viện OpenSAML. | Tách mạng/parsing ra khỏi đường xử lý HTTP. |
| **Cache/metadata resolver** | Giữ các kết quả gần đây và áp chính sách làm mới. | Spring Cache hoặc OpenSAML tùy phiên bản. | TTL, `validUntil`, retry, eviction có ngữ nghĩa khác nhau. |
| **SP signing/decryption credentials** | Private key/certificate do SP dùng để ký hoặc giải mã. | SP/secret manager. | Không được mất hoặc bị sửa vì refresh metadata **của IdP**. |
| **IdP verification credentials** | Certificate công khai mà SP dùng xác minh assertion/response. | Thuộc trust contract với IdP. | Rotation phải có nguồn tin được xác minh, khoảng chồng lấn và kiểm thử. |

### Metadata URL khác registration ID

`registrationId=partner-a` là một khóa nội bộ của Spring. `entityID=https://idp.partner-a.example.org/saml` là danh tính giao thức của IdP. `metadata URI=https://idp.partner-a.example.org/metadata` là **vị trí tải dữ liệu**. Ba giá trị này có thể khác nhau hoàn toàn.

Khi refresh, không lấy một issuer mới bất kỳ từ XML rồi **âm thầm đổi** ý nghĩa `partner-a`. Nếu business contract không cho phép đổi IdP entity ID, phải giữ nguyên issuer dự kiến và từ chối bản metadata không khớp.

## 3. Vì sao cấu hình tĩnh chưa phải là refresh?

Trong Spring Boot, cách cấu hình đơn giản thường là:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_METADATA_URI}
~~~

Khi khởi tạo bean repository, Spring Boot sử dụng cấu hình/metadata để dựng `RelyingPartyRegistration`. Cấu hình này **không tự cam kết rằng bean được tải lại khi IdP thay đổi metadata**, hoặc Spring Boot sẽ làm mới từng certificate trong phiên đăng nhập đang tồn tại.

Tương tự, đoạn Java:

~~~java
RelyingPartyRegistration registration = RelyingPartyRegistrations
    .fromMetadataLocation("https://idp.partner-a.example.org/metadata")
    .registrationId("partner-a")
    .build();

RelyingPartyRegistrationRepository repository =
    new InMemoryRelyingPartyRegistrationRepository(registration);
~~~

tải/parse metadata để xây **một registration tại thời điểm gọi**; instance `InMemoryRelyingPartyRegistrationRepository` không tự theo dõi URL metadata. Cách này thích hợp cho cấu hình ít thay đổi, nhưng muốn refresh phải tổ chức **lần tải mới** và **cơ chế cập nhật tập registration** hoặc dùng API hỗ trợ mới hơn.

### Phân biệt bốn khái niệm “tự động”

1. **Tự tải metadata tại startup:** cấu hình được dựng một lần khi khởi tạo.
2. **Tự tải lại khi cache miss/eviction:** cache điều khiển thời điểm gọi loader; việc này có thể lazy (chỉ tải sau một request).
3. **Tự làm mới theo hạn metadata:** metadata resolver đọc `validUntil`/`cacheDuration` và lập lịch/áp hạn theo khả năng thư viện.
4. **Tự động vận hành an toàn:** ngoài refresh còn có trust validation, rollback/last-known-good, giới hạn stale, alert, kiểm thử và phối hợp rotation. Có một trong ba cơ chế đầu **chưa đủ** để khẳng định đạt yêu cầu thứ tư.

## 4. Thiết kế một kho đăng ký có thể làm mới

### 4.1. Sơ đồ các luồng dữ liệu

~~~text
                    Control plane (không ở HTTP request thread)
IdP metadata URL ---> [1] Fetch với TLS/timeouts/allow-list
                             |
                         [2] Parse XML
                             |
                  [3] Verify trust + metadata signature
                             |
                    [4] Validate issuer/expiry
                             |
                  [5] Gắn SP entityID, ACS, keys
                             |
                  [6] Build candidate snapshot
                             |
              +------ success? -----------------+
              |                                 |
             YES                               NO
              |                                 |
      [7] Atomic publish                  Keep old snapshot
              |                            + alert + bound age
              v
         AtomicReference
              |
              v
  RelyingPartyRegistrationRepository
          /           |            \
   AuthnRequest      ACS/login      SP metadata
       lookup         lookup          lookup
~~~

**Control plane** làm việc tải, xây và phát hành registration. **Data plane** xử lý request SSO và chỉ đọc snapshot đã được công bố. Nhờ đó user request không phải chờ mỗi lần mạng IdP chậm.

### 4.2. Sáu tính chất cần bảo đảm

1. **Nhất quán:** mỗi lookup nhìn một bản registration hoàn chỉnh; không “nửa cert cũ nửa endpoint mới”.
2. **Thất bại an toàn:** fetch/parse/verify thất bại không được ghi snapshot rỗng hay cấp quyền rộng.
3. **Trust cố định:** chỉ lấy metadata từ nguồn và issuer đã được quản trị phê duyệt; không để request quyết định URL tải.
4. **Tính mới có giới hạn:** snapshot cũ có thể được giữ trong một khoảng phục hồi, nhưng quá hạn cho phép phải ngừng chấp nhận đăng nhập mới và cảnh báo.
5. **Quyền SP ổn định:** SP entity ID, ACS, signing/decryption keys là cấu hình SP; metadata IdP không được tự ý thay đổi chúng.
6. **Quan sát và kiểm thử:** biết last refresh success/failure, tuổi snapshot, issuer, số certificate và hiệu lực; không log private key hay raw assertion.

### 4.3. Trạng thái hệ thống khi refresh

| Sự kiện | Hành vi khuyến nghị | Tránh |
| --- | --- | --- |
| Metadata mới hợp lệ, cùng issuer, trust pass | Xây và thay **toàn bộ** snapshot. | Sửa mutable collection đang được nhiều request đọc. |
| Metadata giống hệt bản đang có | Có thể cập nhật mốc kiểm tra thành công, giữ cấu hình không đổi. | Coi mọi lần fetch là một cuộc đổi khóa. |
| HTTP timeout, XML malformed, chữ ký metadata không hợp lệ | Giữ last-known-good; ghi sự kiện lỗi và retry theo backoff. | Xóa kho hoặc chấp nhận XML sai. |
| Metadata trả về issuer khác | Từ chối candidate, alert thay đổi trust contract. | Tự đổi issuer của `partner-a`. |
| Cert mới xuất hiện trong giai đoạn rollover hợp lệ | Chấp nhận theo chính sách trust, kiểm chứng cả cert cũ/mới trong giai đoạn phù hợp. | Xóa cert cũ khi IdP vẫn ký bằng nó. |
| Metadata quá hạn hoặc last-known-good quá cũ | Fail closed cho login mới, alert và làm rõ chiến lược khôi phục. | Tin bản stale vô hạn. |
| Đang có AuthnRequest trước refresh, response đến sau refresh | Đối chiếu request/state và xử lý có kiểm soát khả năng cert/endpoint chuyển tiếp. | Tắt kiểm tra chữ ký, audience, correlation để đăng nhập được. |

## 5. Đánh giá API theo phiên bản Spring Security

**Đừng dùng Javadoc của “current” để suy ra code ở ứng dụng dùng bản cũ chắc chắn biên dịch.** Xác định phiên bản thực từ Spring Boot dependency management hoặc Gradle/Maven dependency tree, sau đó mở tài liệu đúng nhánh.

| Nền tảng/API | Trạng thái và vai trò | Cách ứng dụng |
| --- | --- | --- |
| **Spring Security 5.4+** – `RelyingPartyRegistrations.fromMetadataLocation(String)` | Utility dựng `RelyingPartyRegistration.Builder` từ địa chỉ metadata. | Dùng cho lần tải mới; **không phải scheduler**. |
| **Spring Security 5.6+** – `RelyingPartyRegistrations.fromMetadata(InputStream)` | Xây builder từ stream metadata do ứng dụng nạp. | Phù hợp XML trong DB/blob, caller phải đóng stream. |
| **Spring Security 5.7+** – `collectionFromMetadataLocation` | Lấy collection builder khi metadata có nhiều EntityDescriptor/IdP. | Lọc issuer mong muốn trước khi gán stable registration ID. |
| **Spring Security 6.3** (thường đi cùng **Boot 3.3**) | Có `RelyingPartyRegistrationRepository`, `InMemoryRelyingPartyRegistrationRepository`, builder/metadata utility; chưa có lớp caching/metadata repo chuyên dụng của 6.4. | Custom repository + atomic snapshot/scheduler hoặc reload có kiểm soát. |
| **Spring Security 6.4+** (thường cùng **Boot 3.4**) – `IterableRelyingPartyRegistrationRepository` | Giao diện vừa lookup vừa iterable, giới thiệu ở 6.4. | Hỗ trợ login picker/SP metadata và tích hợp repo rõ kiểu. |
| **Spring Security 6.4+** – `CachingRelyingPartyRegistrationRepository` | Bộ bọc lazy loading qua Spring Cache, giới thiệu ở 6.4. | Reload dựa trên eviction/TTL **của cache đã cấu hình**. |
| **Spring Security 6.4+** – `AssertingPartyMetadataRepository` và `RelyingPartyRegistration.withAssertingPartyMetadata(...)` | Phân tách nguồn IdP metadata khỏi cấu hình phía SP. | Dễ dùng resolver refresh theo hiệu lực metadata. |
| **Spring Security 6.4+ / OpenSAML 5** – `OpenSaml5AssertingPartyMetadataRepository` | Cung cấp metadata resolver hỗ trợ refresh theo hạn của metadata, các tùy chọn xác minh chữ ký metadata. | Chọn khi runtime thật dùng OpenSAML 5 và đã cấu hình trust đúng. |
| **Spring Security 7.x** | API 6.4-style tiếp tục được document; đã thay đổi baseline OpenSAML và có thêm tiện ích ở một số minor. | Kiểm tra migration guide/Javadoc 7.x cụ thể, đừng sao chép thẳng code 6.3. |

**Ba lưu ý phiên bản:**

- Spring Boot `3.3.x` quản lý một bộ Spring Security `6.3.x` điển hình; Boot `3.4.x` quản lý `6.4.x`. Override BOM, plugin và dependency riêng có thể khiến phiên bản thực khác con số dự kiến.
- `CachingRelyingPartyRegistrationRepository` có **Since: 6.4**. Copy nó vào dự án Spring Security 6.3 thường sinh lỗi `cannot find symbol`; giải pháp là custom repo như mục 6, hoặc nâng cấp dependency đồng bộ.
- `AssertingPartyMetadataRepository` cũng có **Since: 6.4**. `OpenSaml5AssertingPartyMetadataRepository` cần thành phần OpenSAML 5 phù hợp trên classpath; chỉ thấy tên class trong tài liệu mới chưa phải bằng chứng runtime đang có nó.

### 5.1. Cách xác định phiên bản đang chạy

Với Gradle có wrapper:

~~~bash
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat` nếu dự án dùng wrapper Windows. Kiểm tra output **phiên bản đã resolve** sau dependency management, không chỉ nhìn version trong `build.gradle`.

Có thể kiểm tra class file hoặc dependency JAR tương ứng cho:

~~~text
org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository
org.springframework.security.saml2.provider.service.registration.CachingRelyingPartyRegistrationRepository
org.springframework.security.saml2.provider.service.registration.AssertingPartyMetadataRepository
~~~

Kiểm tra khả năng tồn tại class và method qua Javadoc đúng version và thử compile trong CI trước khi quyết định kiến trúc.

## 6. Ví dụ chạy được với Java 17 + Spring Boot 3.3.x: repository snapshot có refresh

Đây là **một ứng dụng Servlet SP hoàn chỉnh về mặt source/build**, dựa vào API có trong dòng Spring Security 6.3. Phần đăng nhập SAML thật cần metadata IdP hợp lệ, endpoint mạng, registration của SP phía IdP và chứng thư/keys phù hợp. Thiết kế minh họa **tải lại metadata theo lịch, giữ bản gần nhất hợp lệ và không dùng snapshot quá già**.

> **Ranh giới bảo mật:** Mẫu 6.3 này chứng minh cơ chế snapshot/atomic refresh với **metadata URL HTTPS được quản trị tin cậy** và **expected issuer cố định**. Nó chưa tự hiện thực kiểm tra **chữ ký XML của metadata** hoặc `validUntil` và `cacheDuration` ở cấp XML. Nếu nguồn yêu cầu xác minh chữ ký metadata, sử dụng metadata được xác minh trước khi dựng registration hoặc chuyển sang resolver có hỗ trợ (mục 8); không đưa nguyên mẫu này vào production để tin certificate mới từ nguồn chưa được xác minh.

### 6.1. Cấu trúc dự án

~~~text
refreshable-saml-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/samlrefresh/
    │   ├── SamlRefreshApplication.java
    │   ├── SecurityConfig.java
    │   ├── RefreshingRegistrationRepository.java
    │   └── DemoController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'refreshable-saml-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    maven {
        url 'https://build.shibboleth.net/maven/releases/'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Shibboleth Maven repository có thể cần cho một số dependency OpenSAML của dòng Spring Security; xem version và tài liệu dependency đúng release. **Không kéo Spring Security 6.4/7.x vào dự án Boot 3.3 chỉ vì muốn một API mới** mà chưa kiểm tra tương thích cả dependency graph.

### 6.2. Spring Boot main bật scheduler

`src/main/java/com/example/samlrefresh/SamlRefreshApplication.java`:

~~~java
package com.example.samlrefresh;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@SpringBootApplication
public class SamlRefreshApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlRefreshApplication.class, args);
    }
}
~~~

`@EnableScheduling` cho phép `@Scheduled` chạy tác vụ làm mới định kỳ. Không có nó, annotation scheduler trong ví dụ có thể không được kích hoạt.

### 6.3. Cấu hình nguồn metadata và chính sách

`src/main/resources/application.yml`:

~~~yaml
saml:
  partner:
    registration-id: partner-a
    metadata-location: ${PARTNER_A_METADATA_URL}
    expected-idp-entity-id: ${PARTNER_A_ENTITY_ID}
    sp-entity-id: ${SP_ENTITY_ID}
    acs-url: ${SP_ACS_URL}
    refresh-delay-ms: 900000
    refresh-initial-delay-ms: 900000
    max-stale-seconds: 86400
~~~

Các biến môi trường này cần được quản trị viên cung cấp:

| Biến | Ví dụ chỉ để hiểu ý nghĩa |
| --- | --- |
| `PARTNER_A_METADATA_URL` | `https://idp.partner-a.example.org/metadata` |
| `PARTNER_A_ENTITY_ID` | `https://idp.partner-a.example.org/saml` |
| `SP_ENTITY_ID` | `https://orders.example.org/saml2/service-provider-metadata/partner-a` |
| `SP_ACS_URL` | `https://orders.example.org/login/saml2/sso/partner-a` |

`refresh-delay-ms` là thời gian chờ sau mỗi lần chạy scheduler (15 phút). `max-stale-seconds` giới hạn tuổi snapshot dựa trên **thời điểm refresh thành công gần nhất** (minh họa: 24 giờ). Đây là **giới hạn vận hành do SP đặt**, **không thay thế `validUntil` của metadata**. Với URL local và HTTP, ví dụ cố ý yêu cầu HTTPS để giữ ranh giới an toàn; dùng một IdP test có HTTPS nếu muốn chạy login thực.

### 6.4. Repository: không sửa bản đang phục vụ request

`src/main/java/com/example/samlrefresh/RefreshingRegistrationRepository.java`:

~~~java
package com.example.samlrefresh;

import java.net.URI;
import java.time.Instant;
import java.util.Collections;
import java.util.Iterator;
import java.util.concurrent.atomic.AtomicReference;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.stereotype.Component;

@Component
public final class RefreshingRegistrationRepository
        implements RelyingPartyRegistrationRepository,
                   Iterable<RelyingPartyRegistration> {

    private static final Logger log =
        LoggerFactory.getLogger(RefreshingRegistrationRepository.class);

    private record Snapshot(
            InMemoryRelyingPartyRegistrationRepository repository,
            Instant loadedAt) {
    }

    private final String registrationId;
    private final String metadataLocation;
    private final String expectedIdpEntityId;
    private final String spEntityId;
    private final String acsUrl;
    private final long maxStaleSeconds;

    private final AtomicReference<Snapshot> current = new AtomicReference<>();

    public RefreshingRegistrationRepository(
            @Value("${saml.partner.registration-id}") String registrationId,
            @Value("${saml.partner.metadata-location}") String metadataLocation,
            @Value("${saml.partner.expected-idp-entity-id}") String expectedIdpEntityId,
            @Value("${saml.partner.sp-entity-id}") String spEntityId,
            @Value("${saml.partner.acs-url}") String acsUrl,
            @Value("${saml.partner.max-stale-seconds:86400}") long maxStaleSeconds) {

        this.registrationId = registrationId;
        this.metadataLocation = metadataLocation;
        this.expectedIdpEntityId = expectedIdpEntityId;
        this.spEntityId = spEntityId;
        this.acsUrl = acsUrl;
        this.maxStaleSeconds = maxStaleSeconds;

        requireHttps("metadata-location", metadataLocation);
        requireHttps("sp-entity-id", spEntityId);
        requireHttps("acs-url", acsUrl);

        if (maxStaleSeconds <= 0) {
            throw new IllegalArgumentException("max-stale-seconds must be > 0");
        }

        // Startup phải có bản metadata tin cậy đầu tiên.
        // Nếu tải/parse/validate thất bại, không dựng repository rỗng.
        current.set(loadCandidate());
    }

    private static void requireHttps(String name, String value) {
        URI uri = URI.create(value);
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null) {
            throw new IllegalArgumentException(
                name + " must be an absolute HTTPS URI");
        }
    }

    private Snapshot loadCandidate() {
        // Mỗi lần gọi là một lần xây registration mới từ IdP metadata.
        RelyingPartyRegistration registration = RelyingPartyRegistrations
            .fromMetadataLocation(metadataLocation)
            .registrationId(registrationId)
            .entityId(spEntityId)
            .assertionConsumerServiceLocation(acsUrl)
            .build();

        // IdP không được âm thầm thay danh tính đã ký hợp đồng.
        String actualIssuer = registration.getAssertingPartyDetails()
            .getEntityId();
        if (!expectedIdpEntityId.equals(actualIssuer)) {
            throw new IllegalStateException(
                "Unexpected SAML IdP entity ID");
        }

        // Không công bố registration không có credential xác minh.
        if (registration.getAssertingPartyDetails()
                .getVerificationX509Credentials().isEmpty()) {
            throw new IllegalStateException(
                "SAML IdP has no verification credentials");
        }

        InMemoryRelyingPartyRegistrationRepository repository =
            new InMemoryRelyingPartyRegistrationRepository(registration);

        return new Snapshot(repository, Instant.now());
    }

    @Scheduled(
        fixedDelayString = "${saml.partner.refresh-delay-ms:900000}",
        initialDelayString =
            "${saml.partner.refresh-initial-delay-ms:900000}"
    )
    public synchronized void refresh() {
        try {
            Snapshot candidate = loadCandidate();

            // Chỉ publish sau khi toàn bộ candidate đã qua kiểm tra.
            current.set(candidate);
            log.info("SAML registration {} refresh succeeded", registrationId);
        }
        catch (RuntimeException ex) {
            // Keep last-known-good; tuyệt đối không thay bằng empty repo.
            log.warn("SAML registration {} refresh failed: {}",
                registrationId, ex.getClass().getSimpleName());
        }
    }

    private Snapshot usableSnapshot() {
        Snapshot snapshot = current.get();

        if (snapshot == null) {
            return null;
        }

        Instant deadline =
            snapshot.loadedAt().plusSeconds(maxStaleSeconds);

        // Dừng login mới nếu bản cuối cùng đã vượt ngưỡng stale.
        if (!Instant.now().isBefore(deadline)) {
            return null;
        }

        return snapshot;
    }

    @Override
    public RelyingPartyRegistration findByRegistrationId(String id) {
        Snapshot snapshot = usableSnapshot();
        return snapshot == null
            ? null
            : snapshot.repository().findByRegistrationId(id);
    }

    @Override
    public Iterator<RelyingPartyRegistration> iterator() {
        Snapshot snapshot = usableSnapshot();
        return snapshot == null
            ? Collections.emptyIterator()
            : snapshot.repository().iterator();
    }
}
~~~

**Cơ chế hoạt động của ví dụ:**

- `current` chỉ giữ **một tham chiếu tới snapshot gồm repository và thời điểm nạp**. Request đọc bằng `AtomicReference.get()` thấy bản cũ hoặc mới hoàn chỉnh; không thấy object đang bị chỉnh sửa giữa chừng.
- `loadCandidate()` tạo `RelyingPartyRegistration` mới, gán **registrationId**, **SP entity ID** và **ACS** từ cấu hình của SP, sau đó kiểm tra IdP issuer và số lượng verification credentials.
- `refresh()` chỉ gọi `current.set(candidate)` **khi mọi bước xây candidate thành công**. Khi nguồn metadata lỗi, log một lỗi không tiết lộ XML/chứng thư và giữ last-known-good.
- `usableSnapshot()` trả `null` nếu bản cuối vượt max stale. Với `findByRegistrationId` trả `null`, xử lý login nên thất bại an toàn theo đường xử lý thiếu registration; HTTP response chính xác tùy cấu hình Spring Security. Không xem đây là “cấp lại login tự động”.
- `Iterable<RelyingPartyRegistration>` giúp các thành phần cần liệt kê registration (chẳng hạn login picker/metadata) nhìn snapshot hiện hành. `iterator()` tạo iterator từ bản đã đọc, không từ một map đang bị mutate.
- Mẫu dùng **một IdP entity descriptor/registration**. Nếu metadata nguồn chứa nhiều entity, phải chọn đúng issuer theo tiêu chí ổn định; `collectionFromMetadataLocation` có thể cần hơn `fromMetadataLocation` (mục 9).

**Điều mẫu chưa xử lý đầy đủ cho production:**

1. `RelyingPartyRegistrations.fromMetadataLocation` không tự cung cấp chính sách kiểm tra chữ ký metadata của doanh nghiệp trong đoạn code này. TLS/issuer check **không tương đương kiểm tra chữ ký XML metadata**.
2. Chưa phân tích và áp `validUntil`, `cacheDuration` ở metadata; `maxStaleSeconds` chỉ là giới hạn độc lập. Trong production, ngừng sử dụng **theo mốc sớm hơn** giữa hạn metadata đã xác minh và hạn vận hành SP.
3. Không điều chỉnh read/connect timeout/backoff của metadata loader mặc định. Với metadata từ mạng, cần fetcher có timeout, giới hạn kích thước, redirect allow-list, kiểm soát tốc độ, circuit breaker hoặc dùng resolver chuyên dụng.
4. Một số luồng SAML có request đã tạo trước refresh. Khi thay chứng thư/SSO endpoint, cần giai đoạn chồng lấn và kiểm thử tương thích in-flight requests; repository “đổi nguyên tử” không tự giải quyết mọi vấn đề liên kết state.
5. Ứng dụng chạy nhiều instance có thể refresh ở thời điểm khác nhau. Production cần versioned metadata/distribution hoặc cơ chế giám sát trạng thái mỗi node.
6. Nếu IdP yêu cầu SP ký AuthnRequest hoặc giải mã Assertion, phải đưa **SP signing/decryption credentials** vào builder, không chỉ từ IdP metadata. Ví dụ này giả định IdP cho phép request không ký và response không mã hóa với cấu hình test phù hợp.

Những giới hạn trên cần xử lý trước khi kết luận hệ thống có thể refresh **an toàn trong production**.

### 6.5. SecurityFilterChain

`src/main/java/com/example/samlrefresh/SecurityConfig.java`:

~~~java
package com.example.samlrefresh;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

Do đã có bean `RefreshingRegistrationRepository` triển khai `RelyingPartyRegistrationRepository`, Spring Boot có thể dùng repository đó thay cho bean repository auto-configured. **Đừng khai báo đồng thời một bean repository thủ công và mặc định trông đợi Spring Boot hợp nhất nó với registrations trong `spring.security.saml2.relyingparty.registration`**. Nếu muốn nhiều registration, xây chúng trong repository của mình.

### 6.6. Controller quan sát SAML principal

`src/main/java/com/example/samlrefresh/DemoController.java`:

~~~java
package com.example.samlrefresh;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Open /private to start SAML 2.0 login";
    }

    @GetMapping("/private")
    public Map<String, Object> privatePage(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("nameId", principal.getName());
        result.put("registrationId",
            principal.getRelyingPartyRegistrationId());
        return result;
    }
}
~~~

Đây là endpoint học tập. `NameID`/registration ID là thông tin định danh SAML đã được xử lý; không trả về raw `SAMLResponse`, private keys hoặc các attributes nhạy cảm. **Principal đã xác thực không mặc nhiên có quyền nghiệp vụ**; trong hệ thống thực phải kiểm tra quyền local/tenant ở endpoint và service.

### 6.7. Chạy và kiểm tra thực tế

Cần bộ IdP test **đã tin cậy** công bố metadata HTTPS, SP entity ID/ACS đúng, signing profile phù hợp, và các biến môi trường:

~~~text
PARTNER_A_METADATA_URL=https://idp.partner-a.example.org/metadata
PARTNER_A_ENTITY_ID=https://idp.partner-a.example.org/saml
SP_ENTITY_ID=https://orders.example.org/saml2/service-provider-metadata/partner-a
SP_ACS_URL=https://orders.example.org/login/saml2/sso/partner-a
~~~

Các URL chỉ để giải thích cấu trúc. Thay bằng endpoint thực trước khi chạy. Nếu dùng Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể chạy `.\gradlew.bat bootRun`. Khi IdP/metadata URL không tồn tại hoặc không thể tải, **ứng dụng không hoàn tất startup**; đây là hành vi chủ đích tránh khởi chạy một SP chưa có registration tin cậy.

Với môi trường tích hợp đúng:

1. Mở `/` để kiểm tra endpoint public. Chuỗi trả về chính xác là `Open /private to start SAML 2.0 login`.
2. Mở `/saml2/metadata/partner-a` và đối chiếu SP entity ID, ACS, bindings và chứng thư SP nếu có.
3. Mở `/private`: Spring Security chuyển browser qua flow SAML2; IdP trả response có chữ ký và assertion hợp lệ về ACS.
4. Kiểm tra JSON của `/private`: `nameId` phụ thuộc tài khoản thật, `registrationId` là `partner-a`.
5. Thực hiện certificate rollover **ở IdP test**, xác minh scheduler tiếp tục cập nhật; trước khi đi production phải có kiểm thử chữ ký metadata, validUntil và quy trình rollover.

Trong demo, việc scheduler gọi thành công có nghĩa **đã xây và công bố registration mới từ nguồn được cấu hình**; không phải bằng chứng toàn bộ chính sách production trust đã được thực hiện.

## 7. Vì sao dùng snapshot nguyên tử mà không sửa object tại chỗ?

Giả sử có 100 request AuthnRequest và SAMLResponse đồng thời với tác vụ refresh. Nếu mutable map chứa registration đang được cập nhật lần lượt, request số 1 có thể thấy cert B nhưng ACS cũ, request số 2 thấy IdP entity ID mới với tenant cũ, hoặc iterator bị thay đổi giữa lúc duyệt.

**Đừng sửa `HashMap`/`ArrayList` đang được request đọc rồi kỳ vọng nó nhất quán.** Tạo dữ liệu mới **độc lập**, kiểm tra toàn bộ trước, sau đó đổi một pointer.

~~~java
// Minh họa riêng logic publish; không phải một class độc lập.
AtomicReference<Map<String, RelyingPartyRegistration>> state =
    new AtomicReference<>(Map.of());

// Trong refresh thread:
Map<String, RelyingPartyRegistration> candidates = loadAndValidate();
state.set(Map.copyOf(candidates));

// Trong request thread:
RelyingPartyRegistration selected = state.get().get("partner-a");
~~~

Ví dụ này chỉ diễn đạt **chiến lược**, phần chạy đầy đủ nằm ở mục 6. Khi có nhiều registration, nên xây map **toàn bộ** rồi đổi nguyên tử một lần; không cập nhật từng tenant vào map đang có nếu yêu cầu transaction toàn cục. Nếu muốn các tenant refresh độc lập, cần thiết kế version/validation và ranh giới đồng bộ riêng cho từng tenant, tránh làm IdP A bị lỗi kéo sập B.

### 7.1. Không giữ instance repository cũ vô hạn

`AtomicReference` chỉ đảm bảo **visibility và atomicity của pointer**, không giữ một giao dịch SAML xuyên mọi request. Tại thời điểm T0 SP phát AuthnRequest theo registration A, đến T1 metadata đổi, T2 Response quay về; nếu bên SP đã loại bỏ hoàn toàn certificate A, response ký bằng A có thể thất bại. Điều này có thể đúng theo chính sách hoặc gây gián đoạn.

Vì vậy khi rollover, phải phối hợp:

- Metadata IdP công bố **cả cert cũ và mới** trong thời gian quá độ nếu quy trình cho phép.
- SP nhận certificate mới qua nguồn đáng tin, kiểm thử chữ ký response của cả hai khóa trong giai đoạn overlap.
- Không tự giữ khóa cũ quá `validUntil`/trust policy chỉ để “không gián đoạn”.
- Có kế hoạch xóa chứng thư cũ sau thời điểm IdP ngừng sử dụng, kiểm tra hành vi với in-flight request, SLO và các instance chưa refresh.

## 8. Spring Security 6.4+: API cache và metadata repository chuyên dụng

Mục này **không thuộc code runnable cho Boot 3.3/Spring Security 6.3 ở mục 6**. Chỉ áp dụng sau khi dependency tree thật sự có Spring Security 6.4+ và phiên bản OpenSAML phù hợp.

### 8.1. `CachingRelyingPartyRegistrationRepository`: refresh theo eviction

Ở Spring Security **6.4+**, có thể cung cấp một loader tạo repository từ metadata và bọc bằng `CachingRelyingPartyRegistrationRepository`:

~~~java
// Ví dụ 6.4+, thuộc một @Configuration; không ghép trực tiếp
// với bean RefreshingRegistrationRepository của ví dụ 6.3.
@Bean
RelyingPartyRegistrationRepository samlRegistrations(CacheManager cacheManager) {

    CachingRelyingPartyRegistrationRepository registrations =
        new CachingRelyingPartyRegistrationRepository(() ->
            new InMemoryRelyingPartyRegistrationRepository(
                RelyingPartyRegistrations
                    .fromMetadataLocation("https://idp.example.org/metadata")
                    .registrationId("partner-a")
                    .build()
            )
        );

    registrations.setCache(cacheManager.getCache("samlRegistrations"));
    return registrations;
}
~~~

Những import cần bổ sung trong class `@Configuration` này là `org.springframework.cache.CacheManager` và các class SAML registration của Spring Security. Đây là **mảnh code cấu hình dùng trong chương trình 6.4+** có cache manager đã được thiết lập, không phải một lớp Java độc lập.

**Cực kỳ quan trọng:** cache mặc định có thể là `ConcurrentMapCache` **không tự hết hạn**. Nếu không cấu hình TTL/eviction, code trên vẫn có nguy cơ giữ metadata cũ vô hạn. Loader chạy khi cache yêu cầu dữ liệu mới; **cache expire không nhất thiết tự đẩy refresh trước khi người dùng truy cập**.

Quyết định cách xử lý lỗi lần tải lại, stale window và nhiều tenant là việc của thiết kế cache/controller, không phải một lời đảm bảo chung của API. Không dùng `NoOpCache` trong production rồi cho phép mỗi login fetch metadata qua mạng.

Một cấu hình vận hành cần chỉ rõ:

~~~text
Cache key            registrationId / issuer theo mô hình tin cậy
TTL                  thời hạn cache được vận hành chấp nhận
Eviction              thời điểm/sự kiện làm tải lại
Refresh semantics     lazy on next lookup hay proactive refresh
Failure behavior      retain LKG? fail closed? retry/backoff?
Metadata validity     không vượt validUntil; kiểm soát cacheDuration
Trust                 HTTPS + chữ ký metadata/anchor nếu profile yêu cầu
Metrics               hit/miss, last-success, last-failure, stale-age
~~~

`CachingRelyingPartyRegistrationRepository` giải quyết **caching lookup/loader**; nó không tự quyết định mọi chính sách SAML trust của tổ chức.

### 8.2. `AssertingPartyMetadataRepository`: tách phía IdP khỏi phía SP

Từ Spring Security 6.4, API `AssertingPartyMetadataRepository` chuyên cho **metadata của IdP**, còn `RelyingPartyRegistrationRepository` kết hợp metadata ấy với thông tin **SP sở hữu**.

Lợi ích:

- Một IdP metadata có thể dùng để dựng registration theo chính sách SP tương ứng, tránh trộn data trust của IdP với private keys/ACS của SP.
- Có thể thay metadata resolver mà không sửa luồng SAML login.
- Metadata resolver chuyên dụng có thể đọc hạn hiệu lực và làm mới nền theo khả năng triển khai, thay vì chỉ một lần tải thủ công.
- Có thể kiểm tra chữ ký metadata khi đã cung cấp trust anchor đúng.

Ví dụ **Spring Security 6.4+ với OpenSAML 5 được chọn đúng trên classpath**:

~~~java
// Mảnh code minh họa API 6.4+; các cấu hình SP vẫn phải hoàn thiện.
AssertingPartyMetadataRepository assertingParties =
    OpenSaml5AssertingPartyMetadataRepository
        .fromTrustedMetadataLocation(
            "https://idp.partner-a.example.org/metadata")
        .build();

AssertingPartyMetadata metadata =
    assertingParties.findByEntityId(
        "https://idp.partner-a.example.org/saml");

if (metadata == null) {
    throw new IllegalStateException("Expected IdP metadata missing");
}

RelyingPartyRegistration registration =
    RelyingPartyRegistration
        .withAssertingPartyMetadata(metadata)
        .registrationId("partner-a")
        .entityId("https://orders.example.org/saml2/sp/partner-a")
        .assertionConsumerServiceLocation(
            "https://orders.example.org/login/saml2/sso/partner-a")
        .build();
~~~

Đây là **đoạn ghép API cho học tập**, không phải chương trình login độc lập. Trong production, phần xây registration cần giữ signing/decryption credentials, SLO, binding và chính sách của SP. Đồng thời phải quản lý metadata resolver/cache lifecycle (kể cả đóng resources nếu implementation yêu cầu) và xử lý khi find không thấy issuer kỳ vọng.

#### `fromTrustedMetadataLocation` khác `withMetadataLocation(...).verificationCredentials(...)`

Hãy phân biệt rõ:

- `fromTrustedMetadataLocation(url)` nói rằng **nguồn/metadata được tổ chức coi là đáng tin** để tải. Không tự mặc định rằng method này **xác minh chữ ký XML metadata bằng một khóa do bạn pin**.
- `withMetadataLocation(url).verificationCredentials(credentials -> ...)` cho phép cấu hình các credential tin cậy **để xác minh chữ ký metadata**; theo tài liệu Spring Security, nếu không cung cấp credentials, implementation **không thực hiện signature validation cho metadata**.
- **Certificate của metadata signer** có thể được quản lý khác certificate mà IdP dùng để ký các SAML Assertion. Cần xác định trust contract và chiến lược rotation của cả hai.

Sơ đồ ranh giới:

~~~text
Trust anchor đã duyệt (metadata signer cert)
                |
                v
       Verify signed IdP metadata
                |
                v
   New IdP SSO endpoints / signing certs
                |
                v
   Update trusted RelyingPartyRegistration
                |
                v
      Verify SAML Response/Assertion
~~~

Không tự chứng minh trust bằng cách lấy certificate “vừa được công bố” trong chính một tài liệu chưa xác minh rồi dùng certificate đó xác minh chính tài liệu ấy.

### 8.3. So sánh ba hướng refresh

| Hướng | Khi nào dùng | Lợi điểm | Bạn vẫn phải tự quản lý |
| --- | --- | --- | --- |
| **Custom atomic snapshot** (6.3+) | Đang ở Boot 3.3/Sec 6.3, cần cơ chế tương thích và tự quyết định chính sách. | Rõ điểm commit/rollback, dễ kiểm tra trạng thái. | Fetch timeout, metadata signature, expiry, retry, multi-node sync, vận hành. |
| **CachingRelyingPartyRegistrationRepository** (6.4+) | Muốn lazy loading/eviction qua Spring Cache. | Ít boilerplate hơn cho cache và lookup. | TTL, eviction, thời điểm refresh, lỗi cache miss, metadata trust. |
| **AssertingPartyMetadataRepository/OpenSAML resolver** (6.4+) | Muốn tách dữ liệu IdP và refresh theo expiry metadata; có thể xác minh signed metadata. | Sát mô hình metadata, hỗ trợ refresh phức tạp. | Trust anchor, cấu hình SP riêng, lifecycle, kiểm soát tenant và version thư viện. |

**Không tự gắn nhãn “API tốt nhất” ngoài ngữ cảnh.** Nếu chỉ cần một IdP tĩnh, cấu hình Boot YAML có thể đủ. Nếu cần metadata thường xuyên thay đổi, resolver expiry-aware là lựa chọn đáng xem xét khi phiên bản hỗ trợ; nếu đang ở 6.3, custom repo minh bạch là hướng kỹ thuật khả dụng.

## 9. Metadata nhiều IdP và nhiều tenant

Một XML metadata có thể chứa `EntitiesDescriptor` gồm nhiều `EntityDescriptor`. Nếu dùng `fromMetadataLocation` nhưng giả định “luôn chỉ có một IdP”, bạn có thể chọn nhầm entity hoặc khiến registration bị lỗi khi phía đối tác mở rộng metadata.

Với API hỗ trợ collection:

~~~java
// Minh họa ý tưởng chọn đúng issuer; đoạn này là một method
// được đặt trong class quản trị cấu hình, không phải file Java riêng.
RelyingPartyRegistration selectPartnerRegistration(String metadataLocation) {

    return RelyingPartyRegistrations
        .collectionFromMetadataLocation(metadataLocation)
        .stream()
        .map(builder -> builder.registrationId("partner-a").build())
        .filter(reg -> "https://idp.partner-a.example.org/saml"
            .equals(reg.getAssertingPartyDetails().getEntityId()))
        .findFirst()
        .orElseThrow(() ->
            new IllegalStateException("Expected IdP not found"));
}
~~~

Đoạn trên cần import các class Spring Security registration; khi dùng với các metadata chứa issuer trùng nhiều lần, cần **phát hiện duplicate/ambiguous descriptors** và fail closed, không chỉ `findFirst()`. Cần gắn lại SP entity ID, ACS và credentials vào kết quả cuối theo policy; snippet chỉ minh họa tiêu chí lọc issuer.

### 9.1. Thiết kế registry nhiều tenant

~~~text
trusted_partners
---------------
registration_id     expected_idp_entity_id             metadata_url
partner-a           https://idp-a.example.org/saml      https://idp-a.example.org/meta
partner-b           https://idp-b.example.org/saml      https://idp-b.example.org/meta

runtime_snapshot
----------------
version
created_at
registrations[partner-a] -> trusted RP-A
registrations[partner-b] -> trusted RP-B
~~~

Trong DB quản trị, `registration_id`, `expected_idp_entity_id` và metadata URL phải có quy tắc sửa đổi và phê duyệt; **không chấp nhận URL tùy ý từ HTTP request**. Trước mỗi lần refresh:

1. Xác định danh sách đối tác đã được duyệt.
2. Nạp metadata riêng theo đối tác/issuer tin cậy.
3. Xác minh chữ ký/nguồn/expiration và các invariant của từng entry.
4. Gắn SP data tương ứng đúng registration ID; không cấp chung signing/decryption key sai tenant.
5. Publish map bất biến cùng version và timestamp; nếu một IdP lỗi, áp chính sách cập nhật độc lập từng tenant hoặc từ chối cả batch một cách có chủ đích.
6. Các lookup dùng đúng version/snapshot đã công bố, không trộn cert hoặc issuer giữa partner A/B.
7. Mỗi tài khoản local liên kết với **issuer + định danh chủ thể + tenant context**, không dùng NameID/email đơn thuần làm quyền truy cập.

## 10. Hiệu lực metadata: `validUntil`, `cacheDuration` và last-known-good

Ví dụ metadata có các thuộc tính:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.partner-a.example.org/saml"
    validUntil="2030-05-01T12:00:00Z"
    cacheDuration="PT30M">
    <!-- IDPSSODescriptor, KeyDescriptor, endpoints... -->
</md:EntityDescriptor>
~~~

Đây là **XML minh họa cấu trúc**, không chứa chữ ký metadata thật.

- `validUntil` nói bản metadata **không nên được coi còn hiệu lực sau mốc này** theo quy tắc SAML metadata và chính sách bên nhận. Nếu có ở cấp `EntitiesDescriptor` và `EntityDescriptor`, cần áp dụng các hạn phù hợp, không chỉ đọc một nhánh tùy ý.
- `cacheDuration="PT30M"` là **gợi ý thời lượng cache**; không đồng nghĩa metadata tự biến mất đúng giây thứ 1800, cũng không buộc scheduler luôn gọi mỗi 30 phút bất kể hạn hiệu lực.
- **Cache TTL** của Spring Cache là một chính sách khác; TTL quá dài có thể giữ bản metadata hết hạn, TTL quá ngắn có thể gây tải nhiều hoặc outage.
- **Last-known-good** là chiến lược chịu lỗi nguồn tạm thời. Nó **không phải giấy phép** tiếp tục tin metadata đã hết hiệu lực vô hạn. Nếu bản ký đã hết `validUntil`, phải áp chính sách nghiêm ngặt và có cơ chế khôi phục có kiểm soát.

Đề xuất tính mốc tiếp theo theo logic:

~~~text
next_check_at   = min(now + operational_refresh_interval,
                      metadata_recommended_refresh_time)

latest_usable_at = min(metadata_valid_until,
                       last_success_at + max_operational_staleness)
~~~

Đây là **công thức thiết kế**, không phải API Java có sẵn trả trực tiếp hai giá trị. Nếu metadata không có `validUntil`/`cacheDuration`, áp chính sách giới hạn phù hợp và hợp đồng IdP; không giả định vô hạn. Khi network lỗi có thể retry với backoff và jitter nhưng không vượt `latest_usable_at`.

### 10.1. Tại sao không fetch metadata theo từng HTTP request?

- IdP metadata endpoint có thể chậm hoặc tạm ngừng; login chịu latency và timeout liên tục.
- Traffic lớn tạo bão yêu cầu tới IdP.
- Một attacker có thể gây tải nếu ứng dụng ghép URL metadata từ request.
- Không thể đảm bảo request đang xác thực thấy một snapshot nhất quán nếu xây registration khác nhau từng bước.

Do vậy dùng cache/snapshot với TTL, proactive refresh và trusted source. Metadata fetch là thao tác **control plane**, không phải bước phải thực hiện trong mọi lần gọi API.

## 11. Chính sách certificate rollover

Một metadata mới có thể chứa nhiều `KeyDescriptor`, với `use="signing"` hoặc không ghi `use` tùy profile. SP cần hiểu certificate nào dùng để xác minh SAML response/assertion, certificate nào dành cho encryption, và certificate nào ký **metadata XML** nếu metadata có chữ ký.

Một quá trình tốt:

~~~text
T0: IDP metadata chứa cert A; IdP ký bằng A.
T1: IDP metadata chứa A + B; SP refresh/verify, tin A + B trong policy.
T2: IdP bắt đầu ký bằng B; SP vẫn xác minh hợp lệ.
T3: Hết overlap và request đang bay; IdP xóa A theo lịch đã duyệt.
T4: SP refresh/verify; ngừng tin A khi điều kiện thu hồi đạt.
~~~

Không nên thay một lần trực tiếp A → B nếu IdP còn đang ký bằng A. Ngược lại, không nên giữ A vô thời hạn nếu IdP đã tuyên bố khóa này bị compromise hoặc hết trust.

**Xác minh metadata là lớp riêng** với xác minh assertion: phải có cơ chế tin nguồn công bố certificate mới, nếu không một metadata URL bị kiểm soát bởi kẻ tấn công có thể làm SP chấp nhận response ký bởi khóa giả.

### 11.1. Private key của SP không thuộc metadata của IdP

Một ứng dụng có thể dùng SP signing key cho AuthnRequest và SP decryption key cho EncryptedAssertion. Khi refresh **IdP** metadata, không được làm mất:

- SP entity ID và ACS URL đã đăng ký.
- SP signing credentials (private key + certificate).
- SP decryption credentials.
- Policy yêu cầu AuthnRequest ký, SLO, hostname/tenant restrictions.
- Local authorization mapping và quyền nghiệp vụ.

Nếu sử dụng `RelyingPartyRegistration.Builder` từ IdP metadata, bổ sung/giữ thông tin SP mỗi lần dựng candidate. “Builder từ metadata” không phải “toàn bộ registration sản xuất đã hoàn chỉnh”.

## 12. Lỗi vận hành và cách khoanh vùng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và khắc phục |
| --- | --- | --- |
| SAML login hoạt động sau restart nhưng lỗi vài ngày sau | Chỉ tải metadata một lần, cert đã xoay. | Kiểm tra thời điểm snapshot/rotation, thiết kế refresh đúng. |
| Dự án Boot 3.3 báo không tìm thấy `CachingRelyingPartyRegistrationRepository` | API mới ở Spring Security 6.4. | Giữ custom repo 6.3 hoặc nâng Boot/Sec đồng bộ. |
| Đã dùng caching repo nhưng cert không đổi | Cache mặc định không TTL hoặc chưa eviction. | Kiểm tra cache implementation/TTL, thời điểm loader chạy. |
| IdP metadata thay đổi mà SSO filter vẫn thấy bản cũ | Repository/bean khác đang được inject, hoặc current snapshot chưa đổi. | Xác minh đúng bean `RelyingPartyRegistrationRepository` và refresh success. |
| Refresh chạy, nhưng đăng nhập bắt đầu fail | Issuer/ACS/SSO/binding/cert không khớp, metadata có lỗi. | Kiểm tra candidate validation, diff các field đã duyệt; rollback if invalid. |
| Sau rollover response ký bằng khóa mới không hợp lệ | Chưa cập nhật verifying cert, chưa overlap, metadata cũ. | Phối hợp rollout A+B và kiểm tra chứng thư tin cậy. |
| Metadata bị chặn bởi proxy/timeout | Endpoint/timeout/TLS/network. | Fetcher có timeout, retry/backoff, alert; giữ LKG có hạn. |
| `validUntil` đã qua nhưng cache vẫn trả registration | TTL cache vượt hiệu lực metadata. | Enforce expiry-aware policy ngoài cache. |
| Dùng `fromTrustedMetadataLocation` nhưng nghĩ đã verify XML Signature | Nhầm “trusted source” với signature verification. | Cấu hình metadata signature credential nếu yêu cầu; kiểm chứng thực tế. |
| Cache nhiều IdP trả nhầm issuer | Cache key/registration ID không phân biệt tenant, mapping sai. | Dùng khóa ổn định, validation exact entity ID, tách trust contracts. |
| Metadata trả về HTML login page | Sai URL hoặc IdP yêu cầu tương tác browser. | Dùng metadata endpoint machine-readable, kiểm tra XML/binding. |
| Reload bất ngờ làm mất SP signing key | Candidate builder chỉ có IdP details, bỏ sót SP-owned config. | Tách SP config bất biến và gắn lại mỗi lần refresh. |
| Refresh thành công nhưng local user có quyền sai | Nhầm metadata với hệ thống phân quyền. | Identity link và authorization độc lập, không map external group bừa bãi. |
| XML có nhiều entity descriptor | Dùng parser chọn nhầm entry. | Chọn đúng expected issuer, phát hiện duplicate. |
| IdP gửi metadata chưa ký, endpoint HTTPS bị kiểm soát | Trust anchor phụ thuộc hoàn toàn endpoint. | Xây trust contract, pin nguồn, ký và xác minh metadata hoặc duyệt thay đổi cert qua kênh ngoài. |
| Tất cả instance bị chậm mỗi 15 phút | Scheduler đồng bộ cùng lúc, bão fetch. | Jitter, scheduler phối hợp hoặc snapshot distribution. |
| Login mới bị chặn vì max-stale | Refresh lỗi quá hạn cho phép; fail closed đã hoạt động. | Khắc phục nguồn/trust và xử lý incident; không nâng max-stale vô hạn. |

### Phân biệt lỗi authentication với lỗi authorization

Nếu metadata sai, SP thường không thể xác minh assertion; đó là **lỗi xác thực/liên kết SAML**. Nếu assertion hợp lệ nhưng tài khoản local không có quyền đọc đơn hàng hoặc thuộc tenant khác, trả 403 là **quyết định phân quyền**, không phải lỗi refresh metadata. Đừng tăng quyền nội bộ để che lỗi metadata hoặc nới kiểm tra SAML để che lỗi permission.

## 13. Kiểm thử đúng cơ chế refresh

Một bộ QA có giá trị phải kiểm tra cả hành vi **trước, trong và sau refresh**, không chỉ xác nhận scheduler đã log một dòng.

### 13.1. Ma trận kiểm thử

| ID | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| R01 | Startup với metadata hợp lệ, issuer/ACS đúng, certificate tin cậy. | Repository tạo snapshot đầu, `partner-a` có thể được tra cứu. |
| R02 | IdP publish metadata mới hợp lệ, cùng issuer và cert B bổ sung. | Refresh candidate thành công; snapshot mới được dùng cho lookup sau publish. |
| R03 | Một loạt request lookup chạy đồng thời lúc refresh. | Mỗi request thấy registration hoàn chỉnh của một version; không có lỗi concurrent modification. |
| R04 | Metadata URL timeout, 5xx hoặc trả XML malformed. | Không publish bản lỗi; giữ bản gần nhất hợp lệ cho tới hạn cho phép; có alert. |
| R05 | Metadata trả entity ID của đối tác khác. | Candidate bị từ chối; registration cũ không bị thay. |
| R06 | Metadata thiếu verifying credential bắt buộc. | Candidate bị từ chối theo policy, không tạo registration tin vào mọi chữ ký. |
| R07 | Metadata hết `validUntil`. | Không dùng metadata hết hạn để xác thực, kể cả cache vẫn còn entry. |
| R08 | Metadata có `cacheDuration` ngắn hơn TTL Spring Cache. | Expiry-aware policy thực thi mốc chặt hơn. |
| R09 | Giai đoạn cert A+B, IdP lần lượt ký bằng A rồi B. | Cả hai response hợp lệ trong overlap đã duyệt, sau đó ngừng tin A theo lịch. |
| R10 | Cặp request/response đang bay khi refresh xảy ra. | Không bỏ qua `InResponseTo`, Recipient, Audience và chữ ký; hành vi rollover đã định rõ. |
| R11 | `partner-a` và `partner-b` có cùng NameID. | Lookup giữ ranh giới issuer/registration/tenant, không lẫn quyền. |
| R12 | SP entity ID/ACS bị đổi trong metadata IdP. | SP-owned fields vẫn lấy từ cấu hình SP; không bị ghi đè. |
| R13 | LKG vượt max-stale hoặc hạn metadata. | Fail closed với login mới, cảnh báo; không fallback sang issuer tùy ý. |
| R14 | Dùng Boot3.3/Sec6.3 và build code có class 6.4. | Build báo lỗi API thiếu; không nâng độc lập một JAR tùy tiện. |
| R15 | Dùng Spring Cache nhưng cache không TTL. | Kiểm thử phát hiện metadata không được refresh tự động. |
| R16 | Metadata response bị thay bằng certificate của attacker. | Signature metadata/trust policy ngăn publish candidate. |

R07/R08/R16 **không được coi là đã đáp ứng bởi mẫu 6.3 ở mục 6** vì mã mẫu chưa triển khai signature/`validUntil` parsing. Chúng là các cổng QA bắt buộc khi nâng thành hệ thống production hoặc dùng resolver có khả năng tương ứng.

### 13.2. Cách tạo test fixture kiểm soát được

Không cần tấn công IdP thật. Trong một môi trường thử nghiệm biệt lập:

1. Dựng IdP test hoặc metadata fixture **được ký bằng khóa test có trust anchor biết trước**.
2. Chuẩn bị phiên bản V1 với cert A, V2 với A+B, V3 chỉ B. Giữ **issuer cố định**.
3. Chuẩn bị bản lỗi V4 sai issuer, V5 metadata malformed, V6 đã hết `validUntil`, V7 có XML signature không hợp lệ.
4. Cho loader dùng một metadata endpoint test thuộc allow-list, thay nội dung có chủ đích.
5. Trigger refresh theo scheduler hoặc phương thức phục vụ integration test, quan sát snapshot trước/sau và phản hồi SAML thực qua IdP test.
6. Xác nhận rằng thử nghiệm thất bại không làm “nới” validation ký số, recipient, audience, replay và authorization.

Với test concurrency, dùng nhiều thread chạy lookup trong khi luồng refresh công bố các snapshots đã xác minh; mục tiêu là không có dữ liệu trộn lẫn. Với production, theo dõi vòng đời **từng node** và thời điểm các node chấp nhận cert mới, tránh tình trạng một node chấp nhận B còn node khác chỉ nhận A.

## 14. Nâng cấp phiên bản: quyết định từ yêu cầu thật

### Khi đang ở Boot 3.3 / Spring Security 6.3

Có thể tiếp tục dùng:

- `RelyingPartyRegistrationRepository`, `InMemoryRelyingPartyRegistrationRepository`.
- `RelyingPartyRegistrations.fromMetadataLocation` hoặc `fromMetadata(InputStream)` khi loader cần kiểm soát nguồn và dữ liệu.
- Scheduler do ứng dụng quản lý, `AtomicReference` hoặc snapshot immutable được publish an toàn.
- Chính sách xác minh metadata/expiry riêng hoặc một lớp fetch+verify đáng tin cậy trước khi tạo builder.

Đừng copy API 6.4 vào dự án 6.3 và xem compiler error là lỗi thư viện. Nếu cần tính năng expiry-aware sâu mà không muốn tự triển khai, cân nhắc nâng cấp có kế hoạch.

### Khi ở Boot 3.4+ / Spring Security 6.4+

Ưu tiên đánh giá:

1. `CachingRelyingPartyRegistrationRepository` nếu yêu cầu chính là lazy lookup theo cache TTL.
2. `AssertingPartyMetadataRepository` + OpenSAML metadata resolver nếu cần thông tin expiry của metadata hoặc signature verification.
3. `IterableRelyingPartyRegistrationRepository` cho nguồn cần vừa lookup vừa enumerate.
4. `RelyingPartyRegistration.withAssertingPartyMetadata` để dựng RP registration từ metadata riêng, gắn SP-owned fields đúng chỗ.
5. Cấu hình Spring Cache/metadata resolver và tests về eviction, expiry, trust; không coi sự hiện diện API là bằng chứng cơ chế hoạt động.

### Khi chuyển sang Spring Security 7.x

Kiểm tra **migration guide, Java baseline, OpenSAML dependency và Javadoc 7.x** chính xác. Các ví dụ trong bài dùng baseline 6.3 để bảo đảm học viên phân biệt được **API lõi lâu đời** và **API mới từ 6.4**; không hứa rằng toàn bộ source của 6.3 sẽ tự biên dịch trên mọi 7.x mà không điều chỉnh.

Cách ra quyết định:

~~~text
Need automatic refresh?
  |
  +-- Không --> Boot metadata-uri / static repository
  |
  +-- Có --> Đang dùng Spring Security < 6.4?
               |
               +-- Có --> custom repository + scheduler + strict trust checks
               |
               +-- Không --> Cần expiry-aware metadata?
                            |
                            +-- Có --> AssertingPartyMetadataRepository/
                            |          OpenSAML metadata resolver
                            |
                            +-- Không --> Cache eviction có thể đủ:
                                       CachingRelyingPartyRegistrationRepository
                                       + bounded TTL + failure policy
~~~

Đây là **sơ đồ lựa chọn kiến trúc**, còn việc kiểm thử trust, rollover, expiry, multi-tenant và authn request correlation là yêu cầu chung của tất cả phương án.

## 15. Những hiểu lầm cần tránh

**“`fromMetadataLocation` tự reload khi URL thay đổi.”** Không. Lời gọi dựng builder tại một thời điểm; muốn cập nhật cần lời gọi tải lại và repository thay đổi hoặc API cache/resolver hỗ trợ.

**“Bọc trong `InMemoryRelyingPartyRegistrationRepository` thì tự đổi cert.”** Không. In-memory repository thường giữ các registration mà bạn đã tạo; nó không phải metadata fetcher nền.

**“`CachingRelyingPartyRegistrationRepository` mặc định tự refresh mỗi 15 phút.”** Sai. Mặc định cache có thể không expiry; thời gian và cách evict do cấu hình cache quyết định.

**“`AssertingPartyMetadataRepository` có từ Spring Security 6.3.”** Sai. Giao diện được giới thiệu ở **6.4**. Từ 6.4 còn có cache và Iterable repo chuyên dụng.

**“`fromTrustedMetadataLocation` bảo đảm XML metadata được ký đúng.”** Không được suy ra như vậy. Cần cấu hình chính sách ký metadata và verification credentials nếu mô hình tin cậy yêu cầu.

**“HTTPS đủ để mọi signing cert mới là an toàn.”** TLS bảo vệ kênh tới endpoint đã tin cậy; khi endpoint/CDN hoặc quy trình quản trị metadata bị chiếm quyền, trust vẫn có thể bị phá. Metadata signature/approval và monitoring là lớp bổ sung tùy yêu cầu.

**“Khi fetch lỗi cứ xóa cache để hệ thống tự tải lại.”** Việc đó có thể đưa mọi request vào mạng hoặc khiến không còn registration. Cần last-known-good có hạn, backoff và fail-closed policy.

**“`cacheDuration` chính là `validUntil`.”** Không. Một bên nói về khuyến nghị cache, bên kia là giới hạn hiệu lực metadata.

**“Refresh cert IdP cũng là refresh private key SP.”** Không. IdP verification credentials và SP signing/decryption credentials có quyền sở hữu và quy trình xoay khác nhau.

**“IdP ký assertion hợp lệ tức mọi quyền nghiệp vụ đã được cấp.”** Không. Spring Security xác thực danh tính SAML; tài khoản local, tenant, role, permission và quyền trên tài nguyên do ứng dụng quyết định.

## 16. Checklist vận hành và kết quả cần đạt

- [ ] Xác định đúng Spring Security, Spring Boot, OpenSAML **runtime versions**, đối chiếu Javadoc theo version.
- [ ] Mỗi `registrationId` có metadata URL/issuer **được phép và phê duyệt**; không lấy URL từ request.
- [ ] Xác thực nguồn metadata, TLS, XML signature/trust anchors nếu áp dụng; hạn chế redirects, kích thước, timeout.
- [ ] Không tự động coi chứng thư mới từ metadata chưa xác minh là trusted.
- [ ] Khi dựng candidate, kiểm tra IdP entity ID, SSO/bindings, verification credentials, expiry và các policy riêng.
- [ ] SP entity ID, ACS, signing/decryption credentials và SLO configuration được áp lại mỗi lần refresh.
- [ ] Snapshot mới được publish nguyên tử; các request không đọc cấu hình cập nhật dở.
- [ ] Lỗi tải/parse/xác minh không ghi đè snapshot tốt; có cảnh báo và backoff.
- [ ] Last-known-good có thời gian tồn tại tối đa; không chấp nhận metadata hết hạn vô hạn.
- [ ] Cấu hình đa tenant có khóa, issuer và certificate riêng; không trộn trust boundaries.
- [ ] Cert rollover A+B có overlap phù hợp; kiểm thử request đang bay và callback.
- [ ] Mọi instance đều theo dõi version/last refresh; có kịch bản restart hoặc failover.
- [ ] Có tests R01–R16 hoặc những test tương đương; đánh dấu rõ các cổng chưa được triển khai.
- [ ] SP metadata endpoint, AuthnRequest, ACS response signature và authorization của ứng dụng được kiểm thử độc lập.
- [ ] Không ghi SAMLResponse, private key, raw assertion hoặc dữ liệu định danh nhạy cảm vào log.

### Ghi nhớ

**Kho đăng ký SAML2 có thể làm mới là một bộ phận quản lý quan hệ tin cậy, không chỉ là một cache HTTP.** Muốn refresh đúng, cần phân biệt IdP metadata và SP-owned registration, xác minh nguồn và hiệu lực của candidate, công bố snapshot nhất quán, bảo đảm chính sách khi thất bại, và chọn API hợp với version đang thực sự chạy. **Spring Security 6.3** làm được với repository do ứng dụng quản lý; **6.4+** cung cấp thêm caching và metadata repository để giảm phần tự triển khai.

### Tài liệu chính thức

- [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistrationRepository`, Boot bean override, caching và multi-tenancy.
- [Spring Security – SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): `AssertingPartyMetadataRepository`, OpenSAML resolver, signature verification và SP metadata.
- [Spring Security 6.4 – API CachingRelyingPartyRegistrationRepository](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/saml2/provider/service/registration/CachingRelyingPartyRegistrationRepository.html): Javadoc nêu `Since: 6.4` và cache mặc định.
- [Spring Security 6.4 – API AssertingPartyMetadataRepository](https://docs.spring.io/spring-security/site/docs/6.4.5/api/org/springframework/security/saml2/provider/service/registration/AssertingPartyMetadataRepository.html): `Since: 6.4`.
- [Spring Security 6.3 – API InMemoryRelyingPartyRegistrationRepository](https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/saml2/provider/service/registration/InMemoryRelyingPartyRegistrationRepository.html): repository có thể được duyệt theo `Iterable`.
- [Spring Security – API RelyingPartyRegistrations](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrations.html): `fromMetadataLocation`, `fromMetadata(InputStream)` và `collectionFromMetadataLocation`.
- [Spring Boot 3.3 – SAML2 Configuration](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): property namespace và tự cấu hình SP trong Boot.
- [OASIS SAML 2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): `EntityDescriptor`, `EntitiesDescriptor`, `validUntil`, `cacheDuration`, `KeyDescriptor`.
