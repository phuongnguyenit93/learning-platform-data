# validUntil, cacheDuration và chính sách làm mới metadata SAML 2.0

**Module:** Spring Security – federation  
**Nhóm kiến thức:** Metadata SAML2  
**Môi trường minh họa:** Java 17+, Spring Boot 3.x, Spring Security 6.x. Phần sử dụng CachingRelyingPartyRegistrationRepository yêu cầu **Spring Security 6.4+**.

## 1. Vì sao metadata cần thời hạn và chính sách làm mới?

Trong SAML 2.0 federation, Service Provider (SP) và Identity Provider (IdP) trao đổi **metadata XML** để thống nhất định danh (**entityID**), endpoint Single Sign-On, binding, chứng thư ký, cơ chế mã hóa và các thông tin giao thức khác. Khi SP tin một IdP, metadata của IdP là một phần **cấu hình bảo mật**: SP dựa vào đó để chọn endpoint và khóa xác minh SAML Response/Assertion.

Những thông tin đó có thể thay đổi:

- IdP **luân phiên chứng thư ký**: bản metadata cũ có thể không chứa khóa mới, khiến SSO lỗi.
- IdP thay endpoint SSO, binding, entity hoặc cấu hình chính sách: bản metadata cũ có thể dẫn tới sai đường dẫn hoặc sai quan hệ tin cậy.
- Tệp metadata được phân phối qua một federation aggregator: nhiều entity cùng xuất hiện và có thời hạn hiệu lực khác nhau.
- Kết nối tới nguồn metadata gián đoạn, hoặc metadata tải về bị hỏng/chữ ký không hợp lệ: không thể đơn giản thay cấu hình đang dùng bằng nội dung mới.

Hai thuộc tính metadata thường gặp là **validUntil** và **cacheDuration**. Chúng trả lời **hai câu hỏi khác nhau**:

- **validUntil:** “Bản metadata này còn được xem là hợp lệ tới thời điểm nào?” Đây là **giới hạn hiệu lực bắt buộc**; đến hoặc sau mốc đó, metadata hết hiệu lực và **không được tiếp tục sử dụng**.
- **cacheDuration:** “Sau tối đa bao lâu người tiêu thụ nên thử lấy bản metadata mới?” Đây là **chỉ dẫn về độ mới/cache**, dùng để lên lịch thử refresh, không tự biến metadata thành không hợp lệ khi hết thời lượng cache.

**Quy tắc cốt lõi:** Metadata có thể **stale nhưng vẫn valid** sau cacheDuration, nếu chưa hết validUntil và chính sách cục bộ cho phép. Metadata đã vượt validUntil **invalid**, dù cache chưa hết hạn, dù HTTP còn trả 304, và dù bản mới tải về thất bại.

## 2. Dạng XML và ý nghĩa thời gian

Ví dụ metadata của một IdP (đã lược bỏ các phần và certificate thật):

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/saml/company"
    validUntil="2026-11-08T00:00:00Z"
    cacheDuration="PT6H">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

Đây là **XML để đọc hiểu thuộc tính**, không phải metadata đủ để chạy Spring Security SAML2: còn thiếu chứng thư/chi tiết cần cho xác minh chữ ký và trust.

### validUntil – mốc thời gian tuyệt đối

**validUntil="2026-11-08T00:00:00Z"** mang ý nghĩa metadata **phải được coi là hết hiệu lực kể từ 00:00:00 UTC ngày 08/11/2026**. Tại thời điểm chính xác bằng validUntil, điều kiện hợp lệ đã không còn.

- Kiểu dữ liệu theo schema là **xs:dateTime** (ISO 8601/XML Schema, có thể mang timezone).
- Đây là thời hạn của **metadata**, không phải NotOnOrAfter trong SAML Assertion, cũng không tự động là thời hạn HTTP session của người đã đăng nhập.
- Một certificate X.509 có thời hạn **notAfter** của riêng nó; không đánh đồng certificate expiration với metadata validUntil.
- Không kéo dài validUntil bằng cách chỉnh đồng hồ cục bộ, copy XML cũ hay coi HTTP cache còn hạn.
- Đồng hồ máy chủ cần đồng bộ NTP; xử lý UTC chính xác và tránh đổi timezone tùy ý.

### cacheDuration – thời lượng tương đối

**cacheDuration="PT6H"** là một **xs:duration**, nghĩa là metadata gợi ý nên **thử refresh sau khoảng 6 giờ** kể từ lúc tiêu thụ/nhận metadata.

Các mẫu cú pháp:

| Giá trị | Ý nghĩa |
| --- | --- |
| **PT15M** | 15 phút |
| **PT6H** | 6 giờ |
| **P1D** | 1 ngày |
| **P7D** | 7 ngày |
| **P1DT2H** | 1 ngày 2 giờ |
| **P1M** | 1 tháng theo xs:duration; không mặc định là 30 ngày cố định |

**Đừng nhầm chữ M:** **PT15M** là phút; **P1M** là tháng. Chuẩn XML Schema duration còn hỗ trợ năm/tháng, nên không được giả định mọi duration đều chuyển sang số giây cố định bằng **java.time.Duration.parse**. Với month/year phải dùng parser và phép cộng lịch phù hợp; ví dụ Java 17 ở phần sau cố ý minh họa **PT6H** để tránh mơ hồ này.

Để tính thời hạn cache, cần ghi nhớ **thời điểm thu nhận metadata**. cacheDuration không phải một timestamp tuyệt đối và không được cộng tùy tiện vào **validUntil**.

## 3. So sánh validUntil và cacheDuration

| Tiêu chí | validUntil | cacheDuration |
| --- | --- | --- |
| Kiểu | **xs:dateTime** | **xs:duration** |
| Nội dung | Thời điểm tuyệt đối hết hiệu lực metadata | Thời lượng tối đa nên lưu cache trước khi **thử làm mới** |
| Mức độ bắt buộc | **Hard expiration:** hết hạn thì không được sử dụng | **Freshness hint:** hết thời lượng không tự chứng minh metadata không hợp lệ |
| Đồng hồ tham chiếu | So sánh với thời gian hiện tại | Tính từ lúc metadata được thu nhận |
| Khi tải mới thất bại | Nếu đã quá validUntil phải từ chối sử dụng | Có thể tiếp tục dùng bản stale khi còn valid và policy cho phép |
| Quan hệ | Có thể chặn sử dụng trước khi tới lịch refresh | Không được vượt qua hard expiration |
| Khi thiếu thuộc tính | Không có hard expiration do thuộc tính này; cần chính sách cục bộ | Không có chỉ dẫn TTL từ metadata; cần lịch refresh cục bộ |

**Ví dụ:** Metadata được thu nhận lúc **08:00 UTC ngày 07/11/2026**, cacheDuration **PT6H**, validUntil **00:00 UTC ngày 08/11/2026**.

- **08:00:** metadata vừa được nhận và xác minh; có thể đưa vào sử dụng.
- **14:00:** nên thử lấy bản mới theo cacheDuration.
- **14:30:** mạng vẫn lỗi; metadata cũ đã **stale** nhưng **chưa expired**. Việc có tiếp tục dùng tạm hay không phụ thuộc chính sách freshness/failure của tổ chức.
- **00:00 ngày 08/11:** metadata cũ đã **expired**, không thể dùng tiếp, ngay cả khi không có mạng và lần refresh cuối thất bại.

Nếu tổ chức có giới hạn nội bộ nghiêm hơn, ví dụ **local max refresh interval 2 giờ**, nên thử refresh lúc **10:00**, sớm hơn gợi ý của IdP. Đây là chính sách bổ sung; không thay đổi ý nghĩa XML.

## 4. Metadata lồng nhau: EntitiesDescriptor và EntityDescriptor

Trong federation quy mô lớn, tệp XML có thể có phần tử tập hợp **EntitiesDescriptor** bao lấy nhiều **EntityDescriptor**, mỗi entity là một IdP hoặc SP. Các phần tử có thể khai báo validUntil/cacheDuration ở những mức khác nhau.

Ví dụ:

~~~xml
<md:EntitiesDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    Name="TrustedFederation"
    validUntil="2026-11-09T00:00:00Z"
    cacheDuration="PT12H">
  <md:EntityDescriptor
      entityID="https://idp-a.example.org/saml"
      validUntil="2026-11-08T06:00:00Z"
      cacheDuration="PT2H">
    <!-- IDPSSODescriptor, KeyDescriptor, endpoints... -->
  </md:EntityDescriptor>
</md:EntitiesDescriptor>
~~~

- Ở ví dụ này, **entity A có validUntil sớm hơn tập hợp**, nên hạn hiệu lực thực tế của entity A là **06:00 UTC ngày 08/11**.
- **cacheDuration PT2H** ở entity A chặt hơn **PT12H** của nhóm; có thể dùng hạn nhỏ hơn để lập lịch refresh.
- Nếu một entity con khai báo validUntil **muộn hơn** cha, metadata của con **không được dùng để vượt hạn cha**.
- Phải tôn trọng các giới hạn có hiệu lực trên **toàn đường từ root/ancestor đến entity hoặc role đang sử dụng**; không chỉ đọc thuộc tính của phần tử đầu tiên hoặc cuối cùng.

Theo các hiệu đính SAML metadata, thuộc tính ở phần tử con có thể **siết chặt** giới hạn của phần tử cha chứ không được nới rộng hơn. Khi có nhiều giới hạn, xác định **mốc hợp lệ hiệu quả ngắn nhất** theo quy tắc chuẩn. Cần phân biệt quy tắc kế thừa/giới hạn metadata với TTL do HTTP CDN hay cache nội bộ áp đặt.

**Lỗi phổ biến:** Parser chỉ lấy validUntil ở **EntityDescriptor** và bỏ qua validUntil sớm hơn của **EntitiesDescriptor**. Kết quả là ứng dụng tiếp tục tin một entity trong tập metadata đã hết hạn.

## 5. Chính sách làm mới: từ metadata đáng tin đến registration dùng được

Một chính sách hợp lý gồm bốn phần độc lập:

1. **Quyết định được phép tin nguồn:** cấu hình danh sách IdP/federation đã phê duyệt; metadata tải về phải có nguồn gốc/tính toàn vẹn phù hợp chính sách.
2. **Tính hiệu lực:** xác định validUntil hiệu quả, mọi giới hạn ở cấp cha/con, thời gian hiện tại và chính sách hạn sử dụng nội bộ.
3. **Tính lịch refresh:** cacheDuration, local max refresh interval, thời gian cần cập nhật sớm trước expiration và jitter.
4. **Quyết định khi lỗi:** có dùng last-known-good hay không, retry/backoff thế nào, thời điểm phải fail closed và cảnh báo vận hành.

### 5.1. Quy tắc tính lịch refresh

Ký hiệu:

- **tFetch:** thời điểm lưu bản metadata vừa được tải và xác minh.
- **dCache:** cacheDuration có hiệu lực từ XML.
- **dLocal:** khoảng refresh tối đa do tổ chức tự đặt, ví dụ 2 giờ.
- **tExpire:** validUntil hiệu quả; nếu không có thì áp dụng chính sách nội bộ phù hợp.
- **margin:** khoảng dự phòng cập nhật trước khi hết hạn, ví dụ 30 phút.

Công thức định hướng cho lần **thử** refresh tiếp theo:

~~~text
tByCache  = tFetch + dCache
tByPolicy = tFetch + dLocal
tByExpiry = tExpire - margin

tNextRefresh = min(tByCache, tByPolicy, tByExpiry)
~~~

Nếu dCache hoặc tExpire thiếu, loại bỏ nhánh tương ứng rồi áp dụng policy bắt buộc của ứng dụng (ví dụ: refresh tối đa mỗi 2 giờ; từ chối metadata không có validUntil nếu quy định tổ chức yêu cầu nó). Nếu tByExpiry nằm trong quá khứ hoặc metadata đã expired, cần refresh ngay, **không đưa bản hết hạn vào trust store**.

**Công thức là chính sách minh họa**, không phải phép chuyển hóa tự động có sẵn trong Spring. Có thể thêm jitter có giới hạn để nhiều node không refresh cùng thời điểm; jitter không được khiến refresh vượt qua tExpire. Không coi margin là thời gian metadata trở nên invalid sớm theo tiêu chuẩn; nó là thời gian chuẩn bị để tránh outage.

### 5.2. Thuật toán vận hành

~~~text
1. Fetch từ location/issuer được phê duyệt.
2. Xác thực nguồn/tính toàn vẹn metadata; parse XML an toàn.
3. Kiểm tra entityID, endpoint, key, giới hạn validUntil/cacheDuration.
4. Nếu metadata mới không hợp lệ: không publish; giữ bản valid cũ
   theo chính sách và báo lỗi.
5. Nếu hợp lệ: xây RelyingPartyRegistration mới; publish atomically.
6. Ghi fetchedAt, effectiveValidUntil, nextRefreshAt, metadata version/hash.
7. Refresh khi đến hạn; khi lỗi, retry với backoff có giới hạn.
8. Sau validUntil, không được tiếp tục dùng bản metadata expired.
~~~

**Publish atomically** nghĩa là chỉ thay cấu hình đang phục vụ khi **tất cả** bước parse/validate/build thành công; request đang xử lý không nhìn thấy trạng thái nửa cũ nửa mới.

### 5.3. Kiểm soát outage và last-known-good

Trong thực tế, có hai mốc cần phân biệt:

- **Stale:** đã đến tNextRefresh nhưng chưa lấy được bản mới; metadata cũ vẫn trước validUntil.
- **Expired:** thời gian hiện tại đã đạt hoặc vượt tExpire; metadata cũ không còn hợp lệ.

Với stale-but-valid, tổ chức có thể chọn **tiếp tục sử dụng có điều kiện** trong thời gian ngắn, cảnh báo và retry; hoặc nghiêm hơn, từ chối sau một giới hạn stale riêng. Với expired, phải **dừng tin metadata đó**, dù người dùng tạm không đăng nhập được. Không có “emergency flag” nào được tùy tiện bỏ qua validUntil để giữ SSO hoạt động.

Nếu không có validUntil, chuẩn không tự sinh ra một hard expiration; vận hành nên đặt **local maximum lifetime** hoặc chính sách bắt buộc hợp lệ và thời hạn tối đa phù hợp hệ thống. Không suy ra từ việc không có validUntil rằng metadata vĩnh viễn an toàn.

## 6. Phân biệt TTL ở bốn tầng

Trong dự án Spring Security, có thể gặp đồng thời nhiều cơ chế thời gian:

| Tầng | Ví dụ | Cần hiểu |
| --- | --- | --- |
| **SAML XML validUntil** | 2026-11-08T00:00:00Z | Metadata hết hiệu lực tuyệt đối theo SAML |
| **SAML XML cacheDuration** | PT6H | Lịch thử lấy lại XML theo gợi ý nhà phát hành |
| **HTTP cache headers** | Cache-Control: max-age=3600, ETag | Hướng dẫn cache ở tầng HTTP; không làm XML đã expired thành valid |
| **Spring Cache TTL** | Caffeine expireAfterWrite 30 phút | Khi entry repository bị eviction và có request mới, có thể nạp registration lại; **không tự kiểm tra** SAML validUntil |

**TTL của repository không bằng SAML cacheDuration nếu bạn không chủ động liên kết hai chính sách.** Một cache Caffeine đặt 30 phút chỉ nói rằng item được eviction sau khoảng đó; code loader có thể lấy lại **cùng metadata đã hết hạn** nếu không có validation riêng.

Tương tự:

- **HTTP 304 Not Modified:** server nói nội dung chưa đổi; không gia hạn giá trị **validUntil** đã ký hoặc công bố trong XML cũ.
- **Certificate notAfter:** thời hạn chứng thư X.509, độc lập với thời hạn metadata và hạn SAML Assertion.
- **SAML Assertion Conditions.NotOnOrAfter:** hạn dùng assertion **trong một lần login**; không phải lịch refresh IdP metadata.
- **HTTP session expiration:** thời gian người dùng ở ứng dụng; metadata hết hạn không tự làm trình duyệt logout theo một cơ chế chuẩn chung, nhưng các **lần xác thực mới** không được chấp nhận dựa trên metadata expired.

## 7. Spring Security: tạo registration từ metadata và giới hạn của cấu hình tĩnh

Cách đơn giản trong Spring Security 6.x:

~~~java
@Bean
RelyingPartyRegistrationRepository relyingPartyRegistrations() {
    RelyingPartyRegistration company =
        RelyingPartyRegistrations
            .fromMetadataLocation(
                "classpath:metadata/company-idp.xml")
            .registrationId("company")
            .build();

    return new InMemoryRelyingPartyRegistrationRepository(company);
}
~~~

Đây là **đoạn Spring Bean** đặt trong lớp **@Configuration**, không phải class độc lập. Cần module **spring-security-saml2-service-provider**. Ý nghĩa:

- **fromMetadataLocation** đọc XML từ vị trí đã cấu hình để xây builder.
- **build()** tạo một registration gồm cấu hình SP và IdP.
- **InMemoryRelyingPartyRegistrationRepository** giữ registration trong bộ nhớ cho đến khi được thay đổi bằng cơ chế khác.

**Repository tĩnh không tự reload metadata theo cacheDuration/validUntil.** Nếu ứng dụng giữ bean này nhiều ngày trong khi IdP thay khóa ký, bản metadata cũ có thể khiến signature validation thất bại hoặc vi phạm giới hạn thời gian metadata. Khi dùng classpath snapshot, muốn cập nhật thường cần bản artifact/redeploy hoặc cơ chế thay repository riêng.

**Giới hạn trách nhiệm:** Spring Security đảm nhiệm luồng SAML2 login, nhưng việc nạp metadata từ location không đồng nghĩa đã có **chính sách refresh + trust verification + kiểm tra validUntil hoàn chỉnh**. Phần này cần được thiết kế và xác nhận rõ theo phiên bản/framework thực tế.

## 8. Spring Security 6.4+: CachingRelyingPartyRegistrationRepository

Từ **Spring Security 6.4**, có class **CachingRelyingPartyRegistrationRepository** (package **org.springframework.security.saml2.provider.service.registration**). Nó gọi một loader khi cache miss và dựa vào **Spring Cache** để quyết định vòng đời entry.

### 8.1. Ví dụ Spring Boot dùng cache TTL

Các dependency trong **pom.xml** (sử dụng Spring Boot 3.x BOM/parent với Spring Security **6.4+** tương thích):

~~~xml
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
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
  </dependency>
  <dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
  </dependency>
</dependencies>
~~~

Trong **src/main/java/com/example/saml/SamlSecurityConfig.java**:

~~~java
package com.example.saml;

import java.time.Duration;
import java.util.function.Supplier;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.CachingRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.IterableRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties() {
        Supplier<IterableRelyingPartyRegistrationRepository> loader = () -> {
            RelyingPartyRegistration company =
                RelyingPartyRegistrations
                    .fromMetadataLocation(
                        "https://idp.example.org/company/metadata")
                    .registrationId("company")
                    .build();
            return new InMemoryRelyingPartyRegistrationRepository(company);
        };

        CachingRelyingPartyRegistrationRepository repository =
            new CachingRelyingPartyRegistrationRepository(loader);

        CaffeineCache cache = new CaffeineCache(
            "samlRegistrations",
            Caffeine.newBuilder()
                .expireAfterWrite(Duration.ofMinutes(30))
                .build());
        repository.setCache(cache);

        return repository;
    }

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Đặc điểm thật của đoạn mã:**

- Caffeine entry được eviction khoảng **30 phút sau lúc ghi**, dựa vào cấu hình cache và thời điểm truy cập tiếp theo.
- Khi một lookup sau eviction xảy ra, repository gọi **loader** và đọc lại metadata từ URL. Đây là **lazy reload**, không bảo đảm background refresh đúng giờ.
- URL **https://idp.example.org/company/metadata** là minh họa, phải đổi thành metadata URL **được tổ chức phê duyệt**. Nếu không có IdP thật, login không thể hoàn tất.
- Nếu nhà phát hành không reachable khi loader chạy, việc lấy registration mới có thể ném exception/ảnh hưởng login; code trên **không triển khai last-known-good, retry, validation validUntil, kiểm tra XML signature hay kiểm soát XML fetch**.
- **Mốc 30 phút là TTL cục bộ**, không có phép đọc tự động các thuộc tính **validUntil/cacheDuration** rồi cấu hình cache tương ứng trong snippet.
- Đối với production, đặt một **lớp tải/xác minh metadata có chính sách và deadline**, thay cho loader minh họa, và thiết kế hành vi fail closed khi không còn bản hợp lệ.

**Quan trọng:** CachingRelyingPartyRegistrationRepository mặc định có thể dùng cache không hết hạn nếu bạn **không cấu hình cache TTL**; bản thân tên có chữ “Caching” không chứng minh metadata luôn được làm mới.

### 8.2. Khi cần refresh đúng hạn, không đợi user login

Với yêu cầu vận hành nghiêm ngặt, nên có một **metadata refresh service** hoặc repository tùy biến:

1. Chạy tác vụ theo lịch đã tính từ cacheDuration, validUntil và local cap.
2. Fetch trong thread/tác vụ riêng, không chặn request người dùng vô hạn vì mạng.
3. Xác minh metadata mới và xây toàn bộ registration trong vùng tạm.
4. Chỉ publish phiên bản mới theo cơ chế atomic swap khi đã đạt tất cả kiểm tra.
5. Tiếp tục phục vụ bản cũ **khi stale nhưng còn valid** nếu policy cho phép; retry bằng backoff và cảnh báo.
6. Dừng tin bản cũ tại validUntil, kể cả khi background service thất bại.
7. Theo dõi và cảnh báo remaining validity; chạy trước dự phòng cho certificate rotation.

Ví dụ **không tự gán lịch @Scheduled cố định 30 phút** rồi mặc định là an toàn cho mọi IdP. Với metadata khác nhau, lịch cần xét **mốc nhỏ nhất** giữa hạn cache, policy và hard expiration.

### 8.3. Hỗ trợ đa IdP

Mỗi IdP có thể có **validUntil**, **cacheDuration**, certificate và mức SLA khác nhau. Repository đa IdP cần theo dõi từng registration/entity riêng; một IdP hỏng metadata không nhất thiết khiến toàn bộ hệ thống SSO dừng. Chỉ phục vụ những registration còn metadata hợp lệ. Nếu một tập metadata (**EntitiesDescriptor**) cùng được ký và chứa nhiều IdP, phải tuân thủ hạn hiệu lực/giới hạn của cả tập cùng từng con.

## 9. Java 17: ví dụ runnable tính deadline refresh

Chương trình dưới đây **chỉ minh họa cách tính mốc thời gian** từ thông tin đã được một parser/trust validator cung cấp. Nó **không tải XML, không xác minh XML signature và không tự tạo RelyingPartyRegistration**. Dùng các giá trị UTC cố định để stdout có thể kiểm tra được.

**Tệp: MetadataRefreshPolicy.java**

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;

public final class MetadataRefreshPolicy {

    private MetadataRefreshPolicy() { }

    public static Instant nextRefresh(
            Instant fetchedAt,
            Duration cacheDuration,
            Duration localMaxInterval,
            Instant effectiveValidUntil,
            Duration safetyMargin) {

        if (cacheDuration.isNegative()
                || cacheDuration.isZero()
                || localMaxInterval.isNegative()
                || localMaxInterval.isZero()
                || safetyMargin.isNegative()) {
            throw new IllegalArgumentException("Invalid refresh policy");
        }
        if (!fetchedAt.isBefore(effectiveValidUntil)) {
            throw new IllegalArgumentException("Metadata already expired");
        }

        Instant byCache = fetchedAt.plus(cacheDuration);
        Instant byPolicy = fetchedAt.plus(localMaxInterval);
        Instant byExpiry = effectiveValidUntil.minus(safetyMargin);

        Instant planned = List.of(byCache, byPolicy, byExpiry)
                .stream()
                .min(Instant::compareTo)
                .orElseThrow();

        return planned.isBefore(fetchedAt) ? fetchedAt : planned;
    }

    public static boolean isUsable(
            Instant now, Instant effectiveValidUntil) {
        return now.isBefore(effectiveValidUntil);
    }

    public static void main(String[] args) {
        Instant fetchedAt =
            Instant.parse("2026-11-07T08:00:00Z");
        Instant validUntil =
            Instant.parse("2026-11-08T00:00:00Z");

        Instant next = nextRefresh(
            fetchedAt,
            Duration.parse("PT6H"),
            Duration.ofHours(4),
            validUntil,
            Duration.ofMinutes(30));

        System.out.println("refreshAt=" + next);
        System.out.println("validAtRefresh="
            + isUsable(next, validUntil));
        System.out.println("validAtExpiration="
            + isUsable(validUntil, validUntil));
    }
}
~~~

Biên dịch và chạy (cần JDK 17+):

~~~bash
javac MetadataRefreshPolicy.java
java MetadataRefreshPolicy
~~~

**Stdout chính xác:**

~~~text
refreshAt=2026-11-07T12:00:00Z
validAtRefresh=true
validAtExpiration=false
~~~

Diễn giải: IdP gợi ý cache 6 giờ, tổ chức đặt maximum 4 giờ, deadline còn 16 giờ; do vậy **12:00 UTC** là mốc refresh sớm nhất. Tại đúng validUntil, **isUsable** trả false.

**Giới hạn cố ý của ví dụ:** hàm nhận **Duration** đã được chuẩn hóa. Java **Duration.parse("PT6H")** dùng được cho giờ/phút/ngày ISO-8601 phù hợp; không giả vờ parse toàn bộ **xs:duration** (đặc biệt **P1M** theo tháng). Một hệ thống sản xuất phải dùng parser XML Schema phù hợp và xác định calendar semantics trước khi truyền duration đã chuyển đổi. Khi metadata thiếu validUntil, cần áp dụng policy riêng, không truyền một timestamp vô hạn. Với metadata lồng nhau, **effectiveValidUntil** là hạn đã chọn đúng theo ancestor/child.

## 10. Trình tự refresh ở production

~~~mermaid
flowchart TD
    A[Nhận metadata từ nguồn đã duyệt] --> B{Nguồn và chữ ký hợp lệ?}
    B -- Không --> F[Giữ bản cũ nếu còn hợp lệ, cảnh báo]
    B -- Có --> C{XML, issuer và điều kiện thời gian hợp lệ?}
    C -- Không --> F
    C -- Có --> D[Build registration mới]
    D --> E[Publish atomic, lên lịch refresh]
    F --> G{Bản cũ còn trước validUntil?}
    G -- Có --> H[Chính sách có thể cho dùng stale, retry backoff]
    G -- Không --> I[Từ chối dùng metadata expired, báo động]
~~~

Cần thực hiện cụ thể các bước sau.

### Giai đoạn 1 – Fetch an toàn

- Chỉ kết nối **metadata location được duyệt trước**, không dùng URL tùy ý do browser gửi để tránh SSRF và mở trust ngoài ý muốn.
- Dùng **HTTPS**, kiểm tra TLS certificate/host, giới hạn redirect, timeout, response size và tốc độ tải.
- Nếu metadata ký XML, kiểm tra **metadata signature** theo khóa trust anchor/quy trình federation; không mặc định rằng tải HTTPS từ một URL nào đó đồng nghĩa nội dung được ký hợp lệ hoặc tự cấp trust cho certificate nằm trong chính XML.
- Chặn **XXE**, external entities và phân tích XML nguy hiểm bằng parser được cấu hình an toàn.
- Ghi audit thời điểm fetch, nguồn, phiên bản/hash, trạng thái xác minh.

### Giai đoạn 2 – Validate

- Chọn đúng **entityID** IdP đã duyệt; kiểm tra endpoint, binding, key usages, chứng thư xác minh và chính sách SP.
- Phân tích **validUntil** với timezone; tính hạn hiệu lực sau khi xét ancestor/child, không lấy duy nhất root hoặc entity con.
- Phân tích **cacheDuration** kiểu xs:duration. Áp dụng giới hạn nhỏ hơn từ metadata và policy nội bộ.
- Từ chối metadata **đã expired**, không có certificate/endpoint cần thiết hoặc vi phạm chính sách trust.
- Kiểm tra việc thay đổi certificate, endpoint hay issuer có nằm trong kế hoạch rotation/phê duyệt hay không; không tin thay đổi bất thường chỉ vì tệp XML parse thành công.
- Nếu dùng HTTP conditional request, **304** vẫn phải đối chiếu validUntil còn lại của cached XML.

### Giai đoạn 3 – Publish và schedule

- Build **RelyingPartyRegistration** từ XML được phép tin.
- Đảm bảo **registrationId, SP entityID, ACS, signing/decryption credentials** ổn định, không vô tình đổi theo IdP metadata.
- Atomic replace repository/cache entry với phiên bản mới; không xóa bản hiện hành rồi mới thử load.
- Tính **nextRefreshAt** từ cacheDuration, local cap, validUntil-margin, có jitter an toàn.
- Giới hạn tốc độ retry, dùng exponential backoff với mức trần; không để backoff đi qua hard expiration mà không cảnh báo.
- Phát metrics: lần refresh thành công, tuổi metadata, giây còn lại tới validUntil, số lỗi liên tiếp, certificate rollover.

### Giai đoạn 4 – Khi lỗi hoặc hết hạn

- Lỗi tạm thời **trước validUntil:** bản cũ vẫn có thể hợp lệ; quyết định stale-while-revalidate theo policy, ghi log/metric và retry.
- Lỗi chữ ký hoặc issuer mismatch: không publish bản mới; xác minh nguồn/sự cố bảo mật, không tự thay trust anchor.
- **Đã đạt validUntil:** dừng dùng metadata đó cho xác thực mới; cần can thiệp hoặc nguồn metadata hợp lệ mới.
- Khi IdP cấp nhiều chứng thư trong thời gian overlap, lưu cả những verification keys được phê duyệt để tránh cắt đứt SSO trong giai đoạn đổi khóa.
- Khi cập nhật metadata thay endpoint, phối hợp với IdP và kiểm tra SAML Response validation; không biến refresh thành cách bỏ xác minh chữ ký/Audience.

## 11. Chiến lược retry/backoff, jitter và monitoring

Giả sử có một federation gồm 50 SP replicas. Nếu tất cả đều tải metadata lúc 00:00 theo cacheDuration giống nhau, dịch vụ IdP có thể bị quá tải. Có thể phân phối thời điểm **thử** refresh:

- Lập lịch với **jitter nhỏ có kiểm soát** nhưng không đẩy lần refresh qua giới hạn hiệu lực.
- Khi tải thất bại, retry theo khoảng 1, 2, 4, 8 phút... tới mức trần do ứng dụng quy định, có jitter và timeout.
- Sau vài lần liên tiếp thất bại, tăng mức cảnh báo; khi deadline gần kề cần paging/on-call thay vì chỉ ghi INFO.
- Không đánh đồng việc HTTP 200 với thành công: chỉ tính **refresh_success** khi đã xác minh XML, hạn hiệu lực và build registration.
- Không cần cố tình làm mới trên mọi HTTP request; dùng cache/repository có chính sách để tránh tải mạng và parse XML liên tục.

Metric đề xuất:

| Metric | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| **saml_metadata_last_success_timestamp** | Lúc fetch/verify/build thành công gần nhất | Phát hiện nguồn lâu không cập nhật |
| **saml_metadata_validity_seconds_remaining** | Số giây trước effective validUntil | Cảnh báo trước hard expiration |
| **saml_metadata_refresh_failure_total** | Tổng số refresh thất bại | Đo tình trạng mạng/IdP/validation |
| **saml_metadata_stale_seconds** | Bao lâu đã trôi qua kể từ lịch refresh dự kiến | Quan sát tình trạng stale được phép |
| **saml_metadata_current_version/hash** | Định danh phiên bản metadata đã duyệt | Audit rotation và rollback |
| **saml_metadata_certificate_rotation_pending** | IdP đang chuẩn bị đổi khóa không | Theo dõi overlap trước khi bỏ khóa cũ |

Các metric trên là **đề xuất tên**, không phải built-in metric mặc định của Spring Security.

## 12. Tình huống và bài tập

### A. Hết cacheDuration nhưng chưa hết validUntil

Metadata tải lúc 08:00, cacheDuration PT2H, validUntil 23:00. Lúc 10:05 không tải được metadata mới.

**Phân tích:** Bản đang dùng đã stale theo chỉ dẫn cache nhưng vẫn trước hard expiration. Tổ chức **có thể** cho phép dùng last-known-good trong khoảng giới hạn và retry; phải xác minh rằng bản đó đã được tin cậy từ trước. Không tuyên bố metadata hết hiệu lực chỉ vì đã qua 10:00.

### B. Hết validUntil nhưng cache chưa hết

Metadata có validUntil 11:00 và cacheDuration PT12H; nhận bản lúc 08:00. Lúc 11:00 chưa có bản mới.

**Phân tích:** Metadata **không hợp lệ từ 11:00**; không được giữ để xử lý SSO mới đến 20:00 chỉ vì TTL cache chưa hết. hard expiration thắng mọi cache policy.

### C. Aggregator hết hạn sớm hơn một IdP con

EntitiesDescriptor validUntil 18:00; EntityDescriptor của IdP A có validUntil 23:00.

**Phân tích:** Giới hạn ở cấp cha chặt hơn, nên IdP A không thể được sử dụng sau 18:00 dựa vào aggregate đó.

### D. Thay certificate IdP trong đêm

Metadata cũ có verification key K1, metadata mới chứa K1 và K2 phục vụ rotation; một thời gian sau IdP chỉ ký bằng K2.

**Phân tích:** SP nên refresh và xác minh metadata **trước** lúc K2 bắt đầu được dùng; cần kế hoạch overlap certificate và giám sát. Giữ bản cũ cho đến validUntil mà không bao giờ refresh có thể gây outage dù metadata đó chưa hết hạn.

### E. HTTP 304 khi XML expired

IdP trả 304 Not Modified sau validUntil 00:00 của bản XML cũ.

**Phân tích:** 304 không tạo ra validUntil mới. Nội dung cũ vẫn hết hạn; SP phải dừng tin nó hoặc nhận metadata mới hợp lệ từ nguồn được phê duyệt.

### F. Metadata không có validUntil

Một IdP chỉ công bố cacheDuration PT1H, không có validUntil. Có hợp lệ vĩnh viễn không?

**Phân tích:** Theo thuộc tính validUntil, không có hard expiration tương ứng; nhưng hệ thống không nên coi cấu hình đó luôn tin cậy. Chính sách có thể **yêu cầu validUntil bắt buộc** hoặc giới hạn lifetime/tần suất refresh và thời gian stale tối đa. Không tự cộng cacheDuration thành validUntil theo nghĩa chuẩn.

### G. Caffeine cache 30 phút và IdP metadata cacheDuration PT6H

Có phải Spring tự tôn trọng PT6H?

**Phân tích:** Không. TTL cache 30 phút do developer cấu hình, không tự suy ra từ metadata XML. Sau eviction, loader chạy khi có lookup; nếu sử dụng cùng metadata expired hoặc không validate XML, cache mới vẫn có thể chứa cấu hình không còn phù hợp.

### H. Last-known-good hết hạn, nhưng business yêu cầu không được mất SSO

**Phân tích:** Không thể coi yêu cầu uptime là lý do tự vô hiệu hóa validUntil và signature validation. Giải pháp vận hành là refresh sớm, nhiều nguồn phân phối đáng tin, alert trước deadline, coordinated rollover, phương án IdP dự phòng đã phê duyệt và chính sách xử lý phiên hiện có. Không “fix” bằng cách sửa XML expiry thủ công.

### I. validUntil trùng đúng thời điểm hiện tại

Tại **2026-11-08T00:00:00Z**, metadata validUntil cũng là mốc đó.

**Phân tích:** Đã expired. Kiểm tra hợp lệ cần **now.isBefore(validUntil)**, không phải **now <= validUntil**.

### J. Metadata mới có issuer lạ nhưng chữ ký XML xác minh theo một khóa mới nằm trong chính metadata

**Phân tích:** Không tự mở rộng trust. Phải xác minh metadata qua trust anchor/nguồn được phê duyệt và giới hạn entityID. Một attacker tự tạo XML và tự ký bằng khóa trong XML không tạo ra quan hệ federation đáng tin cậy.

## 13. Checklist trước khi triển khai

- [ ] Đã xác định **IdP metadata source và trust anchor** được phê duyệt; TLS, XML signature/validation theo chính sách.
- [ ] Parser xử lý chính xác **xs:dateTime**, **xs:duration**, timezone và validUntil/cacheDuration của root/ancestor/entity.
- [ ] **validUntil** được thực thi như hard expiration; cacheDuration chỉ dùng cho lịch thử refresh.
- [ ] Có **local max refresh interval** và yêu cầu/giới hạn cho metadata không có validUntil.
- [ ] Có **safety margin** để cập nhật trước expiry; có jitter/backoff không vượt hard deadline.
- [ ] Repository Spring Security thực sự có cơ chế **reload**; không nhầm InMemory repository với metadata refresher.
- [ ] Nếu dùng CachingRelyingPartyRegistrationRepository, đã cấu hình cache TTL/eviction và hiểu **reload lazy**.
- [ ] Khi refresh fail, dùng last-known-good **chỉ khi còn valid** và local stale policy cho phép.
- [ ] Việc publish registration mới là **atomic**; không chấp nhận XML/certificate/issuer chưa xác minh.
- [ ] Có kế hoạch **certificate rotation**, nhiều khóa hợp lệ trong overlap và rollback đã duyệt.
- [ ] Thử các trường hợp stale-but-valid, expired, missing validUntil, parent earlier expiry, HTTP 304, lỗi metadata signature và IdP unavailable.
- [ ] Có alert **trước validUntil** và quy trình xử lý outage, không ghi token/SAMLResponse/private key vào log.
- [ ] Phân biệt **metadata lifetime**, **certificate lifetime**, **SAML Assertion lifetime** và **browser session lifetime**.

**Ghi nhớ cuối bài:** **validUntil là giới hạn không được vượt; cacheDuration là lời nhắc cần làm mới.** Trong Spring Security, việc gọi **RelyingPartyRegistrations.fromMetadataLocation(...)** mới chỉ xây được cấu hình từ metadata; muốn SSO bền vững cần thêm một vòng đời tải, xác minh, cache, refresh, retry và fail closed đúng chuẩn.

## 14. Tài liệu chuẩn

- [OASIS SAML 2.0 Metadata Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): định nghĩa EntityDescriptor, EntitiesDescriptor, validUntil, cacheDuration.
- [OASIS SAML 2.0 Errata 05 – HTML](https://docs.oasis-open.org/security/saml/v2.0/errata05/csd01/saml-v2.0-errata05-csd01.html): làm rõ khác biệt cache expiration và metadata invalidity; giới hạn cấp cha/con.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistrations, repository và CachingRelyingPartyRegistrationRepository.
- [Spring Security 6.5 API – CachingRelyingPartyRegistrationRepository](https://docs.spring.io/spring-security/site/docs/6.5.3/api/org/springframework/security/saml2/provider/service/registration/CachingRelyingPartyRegistrationRepository.html): bộ nhớ cache, constructor, setCache và mặc định.
- [Spring Security – SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): IdP/SP metadata, registration và metadata endpoints.
- [Shibboleth Identity Provider – Metadata Management Best Practices](https://shibboleth.atlassian.net/wiki/spaces/IDP5/pages/3199507429): quản trị metadata remote, rotation, refresh và expiration.
