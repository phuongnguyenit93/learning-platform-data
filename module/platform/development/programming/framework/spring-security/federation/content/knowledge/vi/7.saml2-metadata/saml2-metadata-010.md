# Xử lý metadata SAML2 hết hạn, sai cấu trúc hoặc IdP tạm ngừng hoạt động

**SAML 2.0 metadata** là tập thông tin giúp Service Provider (SP, trong Spring Security gọi là *Relying Party*) nhận diện và tin cậy đúng Identity Provider (IdP, hay *Asserting Party*): `entityID`, endpoint SSO/SLO, binding, chứng thư ký/mã hóa và các chính sách giao thức. Khi metadata hết hạn, hỏng cấu trúc hoặc không tải được vì IdP gặp sự cố, ứng dụng cần **tách lỗi và phản ứng theo trạng thái tin cậy hiện có**. Không được giải quyết bằng cách bỏ kiểm tra chữ ký, chấp nhận mọi issuer hoặc dùng tùy tiện metadata đã hết hiệu lực.

Ba thông điệp cốt lõi:

1. **Hết thời hạn cache** và **hết hiệu lực metadata** là hai trạng thái khác nhau: `cacheDuration` thường chỉ thời điểm nên tải lại; `validUntil` quy định giới hạn hiệu lực nghiêm ngặt.
2. **Metadata endpoint không truy cập được** không nhất thiết đồng nghĩa **SSO của IdP đang hỏng**; ngược lại IdP có thể không đăng nhập được dù SP vẫn có metadata hợp lệ.
3. **Bản metadata tốt gần nhất (last known good)** chỉ được sử dụng trong giới hạn được phép: đã thẩm định nguồn/chữ ký/cấu trúc, đúng IdP và còn hiệu lực theo chuẩn và chính sách. Một bản có `validUntil` đã qua **không được tiếp tục sử dụng**.

Bài tập trung vào **Spring Security SAML2 Web Browser SSO**, cách thiết kế refresh an toàn, kiểm thử sự cố và khôi phục. Mã ví dụ minh họa chính sách; những bước thật sự kiểm chứng XML, chữ ký và TLS phải dựa trên thư viện SAML phù hợp.

## 1. Metadata SAML2 dùng để làm gì?

Một IdP có thể công bố tài liệu XML theo SAML 2.0 Metadata. SP tiêu thụ tài liệu đó để khởi tạo hoặc cập nhật cấu hình `RelyingPartyRegistration` và `AssertingPartyMetadata`.

Những thành phần cần nhận biết:

| Thành phần XML | Ý nghĩa điển hình | Rủi ro khi sai |
| --- | --- | --- |
| `md:EntityDescriptor` | Mô tả một SAML entity, có `entityID` | Nhận nhầm hệ thống định danh |
| `md:EntitiesDescriptor` | Tập hợp nhiều entity, có thể lồng nhau | Chọn nhầm entity hoặc bỏ qua quy tắc kế thừa |
| `md:IDPSSODescriptor` | Vai trò IdP cho SSO; mô tả protocol và dịch vụ | SP không tìm được cấu hình đăng nhập phù hợp |
| `md:SingleSignOnService` | Endpoint cùng binding như HTTP-Redirect/HTTP-POST | Redirect sang URL sai hoặc binding không hỗ trợ |
| `md:KeyDescriptor` | Thông tin khóa/chứng thư theo mục đích `signing`/`encryption` | Không kiểm chứng được chữ ký hoặc dùng nhầm khóa |
| `validUntil` | Thời điểm tài liệu/phần tử metadata hết hiệu lực | Dùng thông tin tin cậy sau thời hạn chuẩn cho phép |
| `cacheDuration` | Khoảng thời gian nên cache trước khi thử refresh | Dùng cấu hình cũ quá lâu sau thay đổi tại IdP |

**Không nhầm metadata IdP với metadata SP:** IdP metadata mô tả bên xác thực mà Spring Security sẽ tin; metadata SP mô tả ứng dụng, entity ID và ACS để đăng ký ở IdP. `http.saml2Metadata(...)` có thể xuất **SP metadata**; nó không tự động sửa metadata IdP khi IdP bị lỗi.

**Không nhầm metadata với SAML Response:** metadata cung cấp trust configuration; response/assertion được gửi sau khi IdP xác thực người dùng. Mỗi response vẫn phải được kiểm chứng riêng về issuer, chữ ký, audience, recipient, thời gian và các ràng buộc cần thiết.

## 2. Sự khác nhau giữa validUntil và cacheDuration

Giả sử một IdP phát metadata lúc 08:00 UTC:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.test/saml"
    validUntil="2026-11-08T00:00:00Z"
    cacheDuration="PT4H">
    <!-- Nội dung IdPSSODescriptor, SSO endpoints và keys hợp lệ -->
</md:EntityDescriptor>
~~~

Đây là **mảnh XML để đọc thuộc tính**, chưa phải metadata IdP đầy đủ: không có `md:IDPSSODescriptor`, endpoint hoặc chứng thư. Đừng dùng nguyên mảnh này để chạy SAML.

Nếu SP lấy tài liệu lúc 08:00 UTC:

| Thời điểm | Tình huống | Diễn giải |
| --- | --- | --- |
| 08:00 | Metadata được tải và thẩm định thành công | Có thể tạo bản trusted snapshot |
| 12:00 | Hết `cacheDuration=PT4H` tính từ lúc lấy | Nên thử tải lại; không tự biến metadata thành vô hiệu |
| 12:05 | Endpoint metadata lỗi mạng, bản cũ vẫn có `validUntil` ở tương lai | Theo chính sách, có thể tiếp tục dùng bản đã thẩm định và cảnh báo cần refresh |
| 00:00 ngày 08/11 | Đạt `validUntil` | Metadata hết hiệu lực; không được dùng để thiết lập trust cho SSO mới |
| Sau 00:00 | Endpoint vẫn lỗi và không có metadata khác hợp lệ | Tạm dừng SSO phụ thuộc registration đó; báo lỗi có kiểm soát |

**Lưu ý quan trọng theo OASIS SAML 2.0 Errata 05:**

- `cacheDuration` là **khuyến nghị thời gian cache trước lần làm mới tiếp theo**. Cần tính từ **thời điểm thật sự lấy được metadata**, không nhầm với `IssueInstant` của SAML Response.
- Cache đến hạn chưa chứng minh metadata vô hiệu. Khi thiếu `validUntil`, một bản quá hạn cache vẫn có thể còn hợp lệ về mặt giao thức; tổ chức có thể áp dụng chính sách tuổi tối đa nghiêm hơn.
- `validUntil` là giới hạn hiệu lực **cứng**: đến thời điểm đó phải coi metadata là không hợp lệ. Nếu phần tử cha `EntitiesDescriptor` có thời hạn sớm hơn phần tử con, thời hạn hữu hiệu còn bị giới hạn bởi phần tử cha.
- **Không cộng thêm “grace period” sau `validUntil`** chỉ vì IdP đang ngừng hoạt động. Nếu muốn duy trì dịch vụ, phải chuẩn bị nguồn metadata dự phòng **vẫn hợp lệ** và được xác minh.

### Nếu metadata thiếu validUntil hoặc cacheDuration?

Không phải tài liệu nào cũng có cả hai thuộc tính. Thiếu `validUntil` không mặc nhiên có nghĩa “vĩnh viễn tin cậy”, và thiếu `cacheDuration` không có nghĩa “không cần cập nhật”. Bên tiêu thụ phải có **chính sách vận hành** về chu kỳ refresh, tuổi metadata tối đa, nguồn tin cậy, thời gian đổi khóa và xử lý lỗi.

Ví dụ tổ chức đặt trần tuổi bản snapshot là 24 giờ khi không có `validUntil`. Đây là **quy tắc triển khai riêng**, không phải con số bắt buộc của SAML. Nếu giới hạn nội bộ đến trước giới hạn giao thức, áp dụng giới hạn nghiêm hơn.

## 3. Phân loại sự cố trước khi xử lý

Có nhiều lỗi khác nhau dù người dùng có thể chỉ thấy “Không đăng nhập SSO được”:

| Loại lỗi | Ví dụ nguyên nhân | Có cần loại bỏ bản cũ không? |
| --- | --- | --- |
| **Metadata hết `validUntil`** | IdP không cập nhật ngày hiệu lực kịp | **Có**, không tiếp tục tin bản hết hiệu lực |
| **Cache đến hạn** | `cacheDuration` đã qua | Không tự động; kiểm tra giới hạn hiệu lực và policy |
| **XML sai cấu trúc** | XML lỗi, sai namespace, thiếu `IDPSSODescriptor`, thiếu endpoint cần thiết | Từ chối bản mới; có thể giữ bản cũ còn hợp lệ |
| **Metadata chữ ký sai** | Thay đổi nội dung, certificate trust không khớp, signature validation fail | Từ chối bản mới; tuyệt đối không bỏ kiểm tra |
| **Metadata không tải được** | HTTP 404/5xx, DNS, TLS handshake, timeout, proxy | Không biết nội dung mới; cân nhắc bản đã kiểm chứng còn hiệu lực |
| **IdP SSO endpoint không hoạt động** | IdP bảo trì, lỗi dịch vụ xác thực hoặc redirect | Metadata hợp lệ không khiến login mới thành công |
| **IdP đổi khóa/chứng thư** | Rotation không đồng bộ giữa metadata và SAMLResponse | Đồng bộ trust trước khi chấp nhận chữ ký mới |
| **Cấu hình SP sai** | ACS, Entity ID, binding/issuer, reverse proxy URL lệch | Phải sửa registration/config; refresh mù không giải quyết |

Để chẩn đoán chính xác, phân biệt **metadata retrieval**, **metadata validation**, **SAML request initiation**, **IdP authentication** và **SAML Response validation**. Chúng tương ứng các bước hệ thống và dấu hiệu lỗi khác nhau.

## 4. Luồng tải và làm mới metadata an toàn

~~~text
                  Cần tạo/cập nhật SAML registration
                               |
                     Tải từ nguồn đã cho phép
                               |
                +--------------+--------------+
                |                             |
           Tải thành công                 Tải thất bại
                |                             |
         Kiểm tra bảo mật             Bản trusted cache còn
          XML / signature             hiệu lực và policy cho?
          entityID / endpoints               |
          validUntil / keys             +-----+-----+
                |                       |           |
            +---+----+                 Có          Không
            |        |                 |           |
          Đạt      Không đạt     Dùng bản cũ,   Tạm ngừng SSO
            |        |            cảnh báo và    registration đó
            |        |            retry có hạn
            v        |
       Atomic replace| 
       trusted config|
                     v
               Từ chối bản mới
                     |
           Bản cũ còn hợp lệ?
              |           |
             Có          Không
              |           |
          Dùng cũ,      Tạm ngừng
          cảnh báo       login mới
~~~

Các bước nên thực hiện theo thứ tự:

1. **Kiểm soát nguồn:** IdP metadata URL phải xuất phát từ cấu hình/quy trình quản trị tin cậy. Dùng TLS hợp lệ, domain allowlist nếu nhận URL động, timeout và giới hạn kích thước.
2. **Tải vào vùng tạm:** tải tài liệu mới ra khỏi cấu hình đang phục vụ; lỗi tải không được xóa ngay bản đang dùng nếu bản đó vẫn hợp lệ.
3. **Parse an toàn:** dùng parser XML của thư viện SAML, chặn external entities/DTD không cần thiết, giới hạn kích thước/độ sâu, phát hiện tài liệu sai định dạng.
4. **Kiểm tra tính đúng đắn:** chọn đúng `entityID`, role `IDPSSODescriptor`, protocol SAML 2.0, endpoint, binding được hỗ trợ và credential cần thiết.
5. **Kiểm tra tin cậy:** xác minh metadata signature **nếu chính sách yêu cầu** bằng trust anchor được cấu hình độc lập. Không lấy certificate chưa tin cậy ngay trong metadata và gọi đó là đã xác minh nguồn phát hành.
6. **Kiểm tra thời hạn:** tính `validUntil` hữu hiệu từ phần tử liên quan và các phần tử cha, cùng tuổi nội bộ và chính sách refresh.
7. **Chỉ thay thế sau khi hợp lệ:** xây candidate `RelyingPartyRegistration`, kiểm tra cấu hình SP/IdP và cập nhật toàn bộ snapshot phù hợp; tránh trạng thái key mới đi với endpoint cũ.
8. **Ghi audit & metrics:** timestamp thành công gần nhất, tuổi snapshot, thời điểm hết hạn, số lần lỗi và lý do đã được làm sạch; bảo vệ không để lộ credential.
9. **Retry có kiểm soát:** exponential backoff và jitter, giới hạn số request; nếu IdP hỏng, không để mọi request login đồng loạt tải metadata.

Một metadata URL có thể phục vụ nhiều entity trong `EntitiesDescriptor`. Phải chọn đúng entity được quản trị chấp nhận, không tự dùng entity đầu tiên khi có nhiều mục.

## 5. Metadata sai cấu trúc: không chỉ là XML parse error

Có ít nhất ba nhóm thất bại cần phân biệt:

### 5.1. XML không thể parse

Các ví dụ: file bị cắt, thẻ đóng mở sai, namespace không đúng, encoding không hợp lệ, entity/DTD bất thường, nội dung HTML lỗi 500 được trả về thay cho XML.

Phản ứng: **từ chối tài liệu mới và ghi lỗi về nguồn/parse**; nếu bản đã xác minh trước đó còn hợp lệ thì có thể tiếp tục phục vụ bằng bản đó theo chính sách. Không tự sửa XML bằng cách đoán missing tags hoặc bỏ parse validation trong production.

### 5.2. XML đúng cú pháp nhưng sai semantic SAML

Ví dụ:

- `EntityDescriptor` không có `entityID` kỳ vọng.
- Không có `IDPSSODescriptor` phù hợp với SAML 2.0.
- Không có `SingleSignOnService` usable, hoặc chỉ có binding ứng dụng không hỗ trợ.
- Trả metadata của IdP khác, tenant khác hoặc môi trường staging thay cho production.
- Không có verification credential đủ dùng theo chính sách.
- `validUntil` đã qua hoặc các phần tử cha giới hạn sớm hơn.
- Signing/encryption certificate được công bố nhưng không tương thích với chính sách key/algorithm của SP.

Phản ứng: đánh dấu **VALIDATION_FAILED**, không thêm registration hoặc thay thế cấu hình đang tin cậy. Không “sửa” bằng cách bỏ yêu cầu issuer/audience.

### 5.3. XML đúng semantic nhưng không còn đáng tin cậy

Metadata bị sửa trái phép, chữ ký không hợp lệ, chứng thư ký metadata không thuộc trust anchor, TLS trust thất bại, hoặc chain source không khớp hợp đồng với IdP. Có thể file vẫn có SSO URL và certificate “đẹp” nhưng **không được chấp nhận**.

Một `KeyDescriptor` bên trong file cung cấp public keys để SP kiểm tra chữ ký SAML về sau; nó **không tự chứng minh metadata file do IdP thật phát hành**. Cần nguồn/transport đáng tin và/hoặc xác minh **chữ ký metadata với trust anchor đã cấu hình trước**.

**Chính sách quan trọng:** Khi metadata mới không hợp lệ, giữ nguyên trusted snapshot (nếu vẫn được phép) và phát cảnh báo. Không cho phép một response SAML được xác minh bằng cert mới chỉ vì cert xuất hiện trong tài liệu chưa thẩm định.

## 6. Khi metadata endpoint của IdP tạm không truy cập được

Ví dụ HTTPS `https://idp.example.test/metadata` trả HTTP 503 trong lúc SP cần refresh.

**Tình huống A — có snapshot tin cậy còn hiệu lực:** có thể tiếp tục dùng **cấu hình IdP đã được xác thực trước đó** cho tới hạn `validUntil` và giới hạn nội bộ; lên lịch retry/backoff. Lưu ý đây là cách giảm gián đoạn **chỉ khi SSO endpoint thực tế vẫn hoạt động**. Không có cache hoặc không có ngày hiệu lực hợp lệ thì không tự bịa IdP config.

**Tình huống B — không có snapshot hoặc snapshot đã hết hiệu lực:** từ chối tạo trust/registration cho IdP đó và báo lỗi login có kiểm soát. Có thể hệ thống Spring Boot không khởi động nếu bean `RelyingPartyRegistration` tải metadata ở startup và thất bại; khi vận hành cần thiết kế startup behavior rõ ràng, có bản metadata tin cậy phù hợp policy nếu cần chống outage.

**Tình huống C — đã thay cert nhưng metadata endpoint hỏng:** bản snapshot có thể còn `validUntil` và chưa hết thời hạn cache, nhưng nếu IdP ký response bằng cert mới không nằm trong danh sách trusted verification cert, response **phải bị từ chối**. Không tắt signature verification. Nhóm vận hành cần liên hệ IdP hoặc áp dụng cập nhật chứng thư được xác minh ngoài luồng theo quy trình đã phê duyệt.

**Tình huống D — chỉ mạng riêng của một SP bị lỗi:** kiểm tra DNS/proxy/firewall/TLS từ chính môi trường ứng dụng, không suy luận “toàn IdP down” chỉ vì một máy chủ không tải được metadata.

### Bản cached metadata có thể cũ nhưng vẫn hợp lệ

Đã qua `cacheDuration` mà tải lại không thành công là tình huống “**stale for refresh**”; không đồng nghĩa “**invalid**” khi `validUntil` chưa qua. Tuy nhiên tổ chức vẫn cần giới hạn tuổi tối đa, alert và ghi nhận rõ các rủi ro của cấu hình cũ (IdP chuyển endpoint hoặc xoay khóa trong thời gian cache).

Ngược lại, một bản quá `validUntil` là **expired/invalid**, không thể viện dẫn “outage grace period” để tiếp tục cho phép SSO mới.

## 7. Khi chính dịch vụ IdP SSO hoặc xác thực không hoạt động

Phân biệt rõ ba endpoint:

| Thành phần | Triệu chứng | Có thể làm gì? |
| --- | --- | --- |
| **IdP metadata endpoint** | SP không refresh được cấu hình | Dùng trusted snapshot còn hiệu lực, retry/cảnh báo |
| **IdP SingleSignOnService** | Browser redirect lỗi, timeout hoặc trang IdP lỗi | Login mới không thành công qua IdP đó; hiển thị sự cố |
| **IdP SingleLogoutService** | Không thực hiện được SAML SLO | Thiết kế logout cục bộ và trạng thái phiên theo policy; không giả vờ SLO hoàn tất toàn hệ thống |

**Dù metadata được tải hoàn hảo, IdP SSO bị down thì trình duyệt vẫn không thể hoàn tất xác thực mới** qua IdP đó. Không có “cache login success” thay thế cho việc xác thực.

### Người dùng đang có phiên Spring Security thì sao?

Một phiên SP đã được xác thực trước khi IdP bị lỗi **có thể tiếp tục hoạt động** theo chính sách session, timeout và phân quyền của SP. Điều này không tự động đúng trong mọi ứng dụng: một số chức năng phụ thuộc API/token từ IdP hoặc chính sách reauthentication có thể không còn khả dụng.

- Không tự logout toàn bộ người dùng chỉ vì health check metadata endpoint thất bại, trừ khi chính sách an toàn yêu cầu.
- Không tự gia hạn vô thời hạn các phiên hiện có hoặc cấp thêm quyền chỉ vì không thể xác minh lại IdP.
- Nếu thao tác yêu cầu **fresh authentication, MFA step-up hoặc reauthorization ở IdP**, phải chờ IdP phục hồi hoặc dùng cơ chế thay thế đã được phê duyệt.
- Xác thực lại sau logout hoặc khi session hết hạn có thể thất bại trong thời gian outage.

### Nhiều IdP: failover có điều kiện

Nếu ứng dụng có `corp` và `partner`, IdP corp down **không tự cho phép** nhân viên corp đăng nhập qua partner. IdP dự phòng chỉ có thể sử dụng khi:

1. Được cấu hình trước như một trust relationship hợp lệ.
2. Có quy tắc account linking và tenant mapping đã được xác minh.
3. Đạt chính sách assurance, MFA và authorization tương ứng.
4. Không tạo cơ chế bypass ranh giới tổ chức hoặc chiếm quyền người dùng.

Không âm thầm đổi registrationId rồi tin rằng hai IdP đại diện cùng một danh tính.

## 8. Spring Security: những thành phần liên quan

Trong ứng dụng Spring Boot/Spring Security SAML2:

| Thành phần | Vai trò | Điều cần lưu ý khi lỗi metadata |
| --- | --- | --- |
| `RelyingPartyRegistration` | Cấu hình một cặp SP–IdP | Phải xây từ dữ liệu đã được thẩm định |
| `RelyingPartyRegistrationRepository` | Tra cứu cặp registration | Thiếu/sai registration có thể làm login lỗi |
| `InMemoryRelyingPartyRegistrationRepository` | Giữ registration trong process | Không tự tải lại metadata khi nguồn đổi |
| `RelyingPartyRegistrations.fromMetadataLocation` | Tạo registration từ IdP metadata | Tải/parse lúc xây registration, có thể lỗi startup |
| `CachingRelyingPartyRegistrationRepository` | Lazy load/cache registrations từ backing repository | Cách làm mới phụ thuộc **cache eviction policy** |
| `AssertingPartyMetadataRepository` | Trừu tượng truy xuất metadata phía IdP | Có thể dùng implementation có refresh, expiry-aware và metadata signature validation |
| `OpenSaml5AssertingPartyMetadataRepository` | Implementation dựa vào OpenSAML 5 | Hỗ trợ metadata resolver có thể tự refresh theo hiệu lực, tùy cấu hình/version |
| `saml2Login` | Bộ lọc/luồng đăng nhập SAML | Không tự biến metadata lỗi thành response hợp lệ |
| `saml2Metadata` | Xuất **SP metadata** | Không phải cơ chế chữa lỗi IdP metadata |

API metadata repository và OpenSAML 5 có thể có ở các phiên bản Spring Security nhất định. Kiểm tra tài liệu cùng **version** của ứng dụng trước khi dùng; không tự copy code Spring Security 7 sang Spring Security 5.

### 8.1. Cấu hình đơn giản: metadata tĩnh, một IdP

Ví dụ **Spring Boot 3.x / Spring Security 6.x, Java 17+**, ứng dụng Servlet Web có module `spring-security-saml2-service-provider`.

Tệp `src/main/java/com/example/security/SamlSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
        RelyingPartyRegistration corp = RelyingPartyRegistrations
            .fromMetadataLocation("classpath:saml/corp-idp-metadata.xml")
            .registrationId("corp")
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/healthz").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

**Điều kiện:** cần file metadata IdP **hợp lệ và đáng tin** trong `src/main/resources/saml/corp-idp-metadata.xml`, IdP đã đăng ký SP Entity ID và ACS, và chứng thư/cấu hình ký tương thích. Nếu IdP yêu cầu ký AuthnRequest hoặc gửi encrypted assertion, phải bổ sung signing/decryption credentials của SP. Class trên là cấu hình dự án Spring Boot, **không phải chương trình độc lập** chạy bằng lệnh `javac`/`java`; không có stdout cố định.

**Giới hạn của ví dụ:** khi `fromMetadataLocation` đọc classpath lúc tạo bean, Spring lưu một snapshot cấu hình trong InMemory repository. Nếu IdP xoay khóa lúc runtime, **nó không tự theo dõi metadata mới**. Sự cố sai XML có thể làm lỗi tạo registration/startup; vì vậy cần quản trị metadata, kiểm tra trước khi deploy và có kế hoạch rollback.

### 8.2. CachingRelyingPartyRegistrationRepository: cách làm mới có điều kiện

Spring Security hỗ trợ `CachingRelyingPartyRegistrationRepository`: cung cấp một loader/supplier tạo `IterableRelyingPartyRegistrationRepository`, rồi cấu hình cache có eviction phù hợp.

Sơ đồ triển khai:

~~~text
Spring SAML filters
       |
       v
CachingRelyingPartyRegistrationRepository
       |
  Cache còn hiệu lực theo TTL?
       |                   |
      Có                 Không
       |                   |
   Registration        Loader metadata đã cấu hình
       |                   |
       |             Tải + thẩm định + build
       |                   |
       +---------<---------+
                   |
           Lookup registrationId
~~~

**Không lầm tưởng class Caching tự xác định policy `validUntil` cho mọi metadata.** Cache repository ủy quyền eviction cho Spring Cache; cache mặc định có thể không tự hết hạn. Nếu cache eviction đã xảy ra mà loader cần metadata từ URL đang down, lookup có thể lỗi nếu không có cơ chế last-known-good đúng chuẩn. Thiết kế TTL và snapshot validation độc lập với logic cache; không dùng TTL để hợp thức hóa metadata có `validUntil` đã qua.

Ví dụ thiết kế (không phải source code đầy đủ của cache manager):

~~~text
trustedSource: https://idp.example.test/metadata
registrationId: corp
cacheTTL: theo chính sách tổ chức, không vượt giới hạn dùng metadata
onRefresh:
  fetch -> verify source/signature -> parse and validate
  if valid: publish new registration atomically
  if failed: keep previously verified snapshot only while still valid
  otherwise: make corp SSO unavailable with controlled error
~~~

**Điểm cần phân biệt:** cache repository giúp tránh tải lại liên tục và tạo cơ hội refresh, nhưng việc phát hiện metadata quá hạn/không hợp lệ và lựa chọn last-known-good vẫn phải được bảo đảm bởi thành phần metadata/policy thích hợp.

### 8.3. AssertingPartyMetadataRepository cho nhu cầu refresh và signature

Tài liệu Spring Security hiện đại mô tả `AssertingPartyMetadataRepository` như một cách quản lý riêng metadata IdP. Implementation dựa OpenSAML như `OpenSaml5AssertingPartyMetadataRepository` có thể dùng `MetadataResolver` để làm mới theo expiry và hỗ trợ kiểm tra chữ ký metadata bằng **verification credentials được cấu hình**.

**Cảnh báo quan trọng:** phương thức có tên `fromTrustedMetadataLocation` diễn đạt giả định rằng **nguồn đã tin cậy**, không đồng nghĩa mọi metadata được kiểm chứng cryptographic signature mà không có cấu hình khác. Tài liệu nêu rõ: nếu không cung cấp verification credentials, thành phần có thể **không thực hiện metadata signature validation**. Chỉ cấu hình được nguồn HTTPs vẫn cần đánh giá phù hợp với chính sách trust.

Trong hệ thống nhiều tenant, hãy bảo đảm repository biết mapping **registrationId → đúng IdP entityID**, chứ không tự coi registrationId luôn bằng entityID trong metadata. Việc một ví dụ tài liệu dùng chung chuỗi là lựa chọn minh họa, không phải quy tắc SAML.

## 9. Thiết kế last-known-good đúng chuẩn

Một bản **last-known-good (LKG)** là snapshot metadata đã qua các bước kiểm tra cần thiết trong **một thời điểm trước đó**. Nó chỉ có thể giúp hệ thống khi nguồn mới lỗi mà bản cũ vẫn đáng tin và chưa hết hiệu lực.

Bản snapshot nên kèm thông tin:

| Trường | Vai trò |
| --- | --- |
| `entityId` | Bảo đảm đây đúng IdP đã được phê duyệt |
| `retrievedAt` | Tính thời gian cache và thời điểm kiểm tra cập nhật |
| `validUntilEffective` | Giới hạn hiệu lực cứng của bản metadata theo SAML |
| `refreshAfter` | Mốc thử tải lại từ `cacheDuration` hoặc policy |
| `verifiedSource` | Nguồn HTTPS hoặc trust anchor đã thẩm định |
| `signatureVerified` / `trustValidated` | Kết quả thẩm định theo chính sách |
| `ssoEndpoints` và `verificationCredentials` | Cấu hình để xây registration |
| `metadataVersionHash` | Nhận diện phiên bản, giúp audit sự thay đổi |
| `lastRefreshError` | Lý do tải mới thất bại (được làm sạch) |

### Quy tắc quyết định

- **Có metadata mới hợp lệ:** kiểm tra toàn bộ trước, sau đó thay snapshot atomically và cập nhật cache.
- **Metadata mới hỏng hoặc không tải được, LKG còn hiệu lực:** giữ nguyên LKG theo chính sách; cảnh báo, retry sau backoff.
- **LKG vừa hết cacheDuration nhưng chưa hết validUntil:** vẫn có thể dùng nếu policy cho phép; phải ưu tiên refresh và theo dõi tuổi snapshot.
- **LKG hết validUntil hoặc vượt hard maximum age nội bộ:** từ chối dùng để khởi tạo login SAML mới. Khôi phục bằng nguồn metadata hợp lệ đã được xác minh.
- **Không có LKG ở lần khởi động đầu tiên:** SP chưa có cơ sở tin cậy cho IdP; không tạo registration bằng XML bất kỳ từ Internet.
- **IdP SSO endpoint down:** LKG không giúp xác thực mới; phản hồi lỗi đăng nhập theo chính sách.

**Ghi chú về lưu trữ:** LKG có thể nằm trong cấu hình/deployment hoặc kho nội bộ được bảo vệ. Nếu lưu lâu dài, phải có integrity, access control, audit, bảo mật backup và expiration policy. Không để client browser cung cấp bản metadata LKG.

## 10. Ví dụ Java 17 độc lập: quyết định khi metadata hỏng

Đoạn Java sau **biên dịch và chạy được bằng Java 17+**. Nó minh họa tầng ra quyết định **sau khi một thư viện SAML đã kiểm chứng nguồn, cấu trúc, chữ ký và validUntil**. Đây không phải trình phân tích XML hoặc kiểm tra chữ ký. Quy tắc mô phỏng yêu cầu snapshot đã được tin cậy và chưa đến `validUntil`, đồng thời kiểm tra khả năng dùng IdP SSO.

Tệp **MetadataPolicyDemo.java**:

~~~java
import java.time.Instant;

public class MetadataPolicyDemo {

    record TrustedSnapshot(
            Instant validUntil,
            Instant refreshAfter,
            boolean trustValidated) {}

    static String decide(TrustedSnapshot snapshot,
                         Instant now,
                         boolean latestFetchSucceeded,
                         boolean idpSsoAvailable) {
        if (snapshot == null || !snapshot.trustValidated()) {
            return "BLOCK: no trusted metadata";
        }
        if (!now.isBefore(snapshot.validUntil())) {
            return "BLOCK: metadata expired";
        }
        if (!idpSsoAvailable) {
            return "BLOCK: IdP SSO unavailable";
        }
        if (!latestFetchSucceeded
                && !now.isBefore(snapshot.refreshAfter())) {
            return "ALLOW: valid cache, refresh failed, alert";
        }
        return "ALLOW: trusted metadata and SSO available";
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T12:05:00Z");

        TrustedSnapshot valid = new TrustedSnapshot(
                Instant.parse("2026-11-08T00:00:00Z"),
                Instant.parse("2026-11-07T12:00:00Z"),
                true);

        TrustedSnapshot expired = new TrustedSnapshot(
                Instant.parse("2026-11-07T12:00:00Z"),
                Instant.parse("2026-11-07T11:00:00Z"),
                true);

        System.out.println(decide(valid, now, false, true));
        System.out.println(decide(expired, now, false, true));
        System.out.println(decide(valid, now, true, false));
        System.out.println(decide(null, now, false, true));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MetadataPolicyDemo.java
java MetadataPolicyDemo
~~~

Stdout **chính xác**:

~~~text
ALLOW: valid cache, refresh failed, alert
BLOCK: metadata expired
BLOCK: IdP SSO unavailable
BLOCK: no trusted metadata
~~~

Giải thích:

- Mẫu 1: cache cần refresh từ 12:00, refresh thất bại, nhưng đến 12:05 vẫn trước `validUntil` ngày hôm sau. Demo cho phép dùng snapshot **nếu policy hỗ trợ** và phát cảnh báo.
- Mẫu 2: thời điểm hiện tại đã vượt `validUntil=12:00`, nên dù đã có trusted snapshot cũ cũng phải chặn.
- Mẫu 3: metadata hợp lệ nhưng IdP SSO không sẵn sàng; không thể thực hiện login mới qua IdP.
- Mẫu 4: chưa có metadata tin cậy, không được tự tin cậy một IdP chưa xác minh.

**Các giả định cần triển khai trong hệ thống thật:** sample chưa tính clock skew, cache hierarchy `EntitiesDescriptor`, max-age nội bộ, DNS/network status, XML signature, key rollover và workflow refresh. Cờ `trustValidated` là **kết quả đã được thẩm định bởi thành phần đáng tin**, không phải tham số lấy từ HTTP request. Trong thực tế không thể phát hiện IdP availability chính xác chỉ bằng một boolean; cần timeout, health checks và kết quả SAML flow.

## 11. Giám sát và cảnh báo để xử lý trước khi xảy ra gián đoạn

Không nên đợi khách hàng báo lỗi login mới biết metadata đã sắp hết hạn. Có thể theo dõi các chỉ số:

| Metric/event | Mục đích |
| --- | --- |
| `saml_metadata_refresh_success_time` | Lần cập nhật thành công gần nhất |
| `saml_metadata_refresh_failures_total` | Lỗi tải, parse, trust validation theo loại |
| `saml_metadata_effective_valid_until` | Thời điểm hết hiệu lực cứng |
| `saml_metadata_age_seconds` | Tuổi snapshot hiện hành |
| `saml_idp_sso_failures_total` | Dấu hiệu login IdP không thành công |
| `saml_assertion_signature_failures_total` | Phát hiện đứt gãy trust/rotation hoặc hoạt động bất thường |
| `saml_metadata_cert_expiry_days` | Theo dõi X.509 certificate được quản trị sử dụng |
| `saml_registration_active` | Trạng thái đăng ký có đủ trust để tiếp nhận login mới |

Đây là **tên chỉ số minh họa do hệ thống tự định nghĩa**, không phải metrics mặc định có sẵn của Spring Security Actuator.

Thiết lập cảnh báo theo **khoảng thời gian còn lại đến hạn**, không chỉ trạng thái “valid/invalid”:

1. Trước hạn `validUntil` đủ sớm để phối hợp với IdP, tự làm mới và kiểm tra chữ ký/cert.
2. Khi số lần refresh thất bại tăng liên tục hoặc thời gian từ lần refresh thành công vượt chính sách.
3. Khi metadata mới có issuer/endpoint/certificate khác đáng kể so với bản đã duyệt, nhất là thay đổi không có lịch rotation.
4. Khi IdP SSO login liên tiếp thất bại trong lúc metadata fetch thành công; tránh nhầm với parser error.
5. Khi số lần assertion signature validation thất bại đột ngột tăng sau certificate rotation.

**Không log** toàn bộ SAML assertion, private key, session cookie, chứng cứ MFA hay dữ liệu cá nhân trong metadata/Response; ghi registrationId, loại lỗi, timestamp, hash phiên bản và correlation ID đã làm sạch.

## 12. Quy trình ứng phó sự cố (runbook)

### A. Metadata đạt validUntil hoặc đã hết hạn

1. Xác định `registrationId`, IdP entityID, `validUntil` hữu hiệu và nguồn metadata.
2. Kiểm tra đồng hồ server/UTC và thời hạn ở phần tử cha, tránh đọc nhầm `cacheDuration` là expiry.
3. Yêu cầu IdP công bố metadata **mới, hợp lệ, nguồn/chữ ký đáng tin**; kiểm chứng issuer, endpoints, certificates.
4. Cập nhật registration atomically hoặc triển khai cấu hình mới sau khi QA.
5. Thử một login mới và kiểm tra response signature, audience/recipient; không chỉ kiểm tra endpoint metadata trả 200.
6. Nếu chưa có metadata hợp lệ, **tạm dừng SSO mới cho IdP đó** và hiển thị thông báo rõ ràng.

### B. Metadata tải được nhưng XML malformed hoặc semantic sai

1. Ghi loại lỗi (`MALFORMED_XML`, `MISSING_IDPSSO_DESCRIPTOR`, `ENTITY_ID_MISMATCH`, `METADATA_SIGNATURE_INVALID`...).
2. Cô lập candidate mới, không thay trusted snapshot đang hoạt động.
3. Kiểm tra HTTP Content-Type, response code, redirect, gzip/encoding, XML namespaces, cấu trúc entity và binding.
4. Liên hệ IdP để sửa artifact hoặc source, kiểm tra nguồn giả/misconfiguration.
5. Chỉ triển khai lại sau khi candidate thẩm định thành công.
6. Nếu LKG vẫn hợp lệ, có thể tiếp tục login theo policy; nếu hết hiệu lực thì tạm dừng.

### C. Metadata endpoint trả 404/503 hoặc timeout

1. Kiểm tra DNS, TLS, proxy, firewall, HTTP status, chứng thư máy chủ và endpoint IdP thực.
2. Đối chiếu IdP SSO endpoint độc lập: có thể metadata URL hỏng nhưng login vẫn chạy bằng bản LKG.
3. Nếu LKG hợp lệ, bật backoff/circuit breaker với cảnh báo và thời hạn tối đa rõ ràng.
4. Nếu LKG hết `validUntil`, ngừng tin cậy metadata đó; không mở “grace” tùy ý.
5. Kiểm tra rotation đang diễn ra; tránh dùng certificate cũ khi IdP đã ký bằng certificate mới mà SP chưa tin.
6. Khi nguồn trở lại, refresh và xác nhận login mới trước khi đóng incident.

### D. IdP SSO không thể xác thực người dùng

1. Kiểm tra redirect đến IdP, trang login IdP, binding và AuthnRequest.
2. Phân biệt lỗi mạng/IdP 5xx với lỗi `InvalidSignature`, `NoAuthnContext`, `InResponseTo`, `Audience` ở phía SP.
3. Thông báo người dùng không thể thực hiện đăng nhập mới qua IdP này vào thời điểm hiện tại.
4. Các phiên SP hiện có chỉ được tiếp tục theo chính sách session và authorization đã được thiết kế.
5. Nếu có IdP dự phòng, chỉ dùng khi ràng buộc danh tính, assurance và chính sách của tổ chức cho phép.
6. Sau khôi phục, kiểm tra từ khởi động AuthnRequest đến callback ACS và quyền nghiệp vụ.

### E. Cert rollover làm validation thất bại

1. Đối chiếu certificate mà IdP đang **dùng để ký SAML Response** với verification certificates mà SP tin cậy trong registration.
2. Kiểm tra metadata mới có đúng nguồn, đúng issuer, đúng khoảng hiệu lực và khóa được phê duyệt.
3. Trong giai đoạn chuyển giao, nếu IdP cho phép, quản lý đồng thời certificate cũ/mới theo kế hoạch.
4. Cập nhật trusted metadata/cert, làm mới repository và thử login.
5. Không chọn phương án tắt signature verification hoặc bỏ qua audience.

## 13. Những lỗi thường gặp trong Spring Security

| Biểu hiện | Phân tích khả dĩ | Hành động |
| --- | --- | --- |
| Ứng dụng lỗi startup khi tạo `RelyingPartyRegistration` | `fromMetadataLocation` gặp URL không truy cập được hoặc metadata parse lỗi | Dùng source tin cậy có kế hoạch refresh; kiểm tra startup config |
| `findByRegistrationId` trả null | Không có registration hợp lệ hoặc key sai | Kiểm tra mapping `registrationId` và repository |
| Bật caching nhưng metadata không bao giờ làm mới | Cache không eviction hoặc loader chỉ đọc snapshot cũ | Thiết kế TTL/eviction và nguồn refresh |
| Bản metadata mới có `validUntil` đã qua | IdP công bố metadata hết hiệu lực hoặc chọn nhầm entity | Từ chối, yêu cầu metadata mới |
| URL metadata trả XML nhưng không tìm thấy IdPSSODescriptor | Nhầm SP metadata hoặc sai profile/entity | Trỏ đúng IdP metadata |
| Metadata signature validation fail | Sai trust anchor, XML bị sửa hoặc rotation chưa phối hợp | Dừng candidate mới; xác minh metadata và chứng thư |
| Browser redirect đến 503 | IdP SSO dịch vụ đang lỗi | Không sửa bằng bỏ verify; xác nhận tình trạng IdP |
| Assertion signature fail sau rotation | SP verification key chưa cập nhật | Làm mới trusted metadata đúng quy trình |
| `InResponseTo` hoặc `Recipient` không khớp | State/callback URL/ACS cấu hình sai | Kiểm tra AuthnRequest, SP Entity ID, ACS, reverse proxy |
| Khách hàng có phiên SP dùng được nhưng login mới lỗi | Local session hoạt động, IdP không xác thực mới | Quản lý thông báo và session theo policy |
| Login trả `403` sau khi SAML xác thực | Authorization của ứng dụng từ chối | Kiểm tra role/tenant/object-level permissions, không đánh đồng metadata với quyền |
| Endpoint SP metadata vẫn trả 200 nhưng IdP down | SP metadata endpoint hoạt động độc lập | Theo dõi riêng IdP SSO và validation |

### Những cách xử lý sai cần tránh

- Bỏ metadata signature verification chỉ để chấp nhận tài liệu mới.
- Cho phép certificate không tin cậy hoặc bỏ qua SAML Response signature.
- Dùng mọi SAML entity có tên gần giống hoặc chọn entity đầu tiên.
- Bỏ kiểm tra audience, recipient, InResponseTo hoặc thời gian.
- Tiếp tục sử dụng metadata đã qua `validUntil` chỉ vì IdP đang outage.
- Tắt toàn bộ auth cho API hoặc admin console khi IdP ngừng hoạt động.
- Tin rằng đổi cache TTL đồng nghĩa đã xử lý rotation hay IdP 503.
- Đọc metadata URL do người dùng truyền tùy ý mà không kiểm soát SSRF/nguồn tin cậy.

## 14. Các tình huống tự đánh giá

**Câu 1:** Metadata được tải lúc 08:00, `cacheDuration=PT4H`, `validUntil=00:00` hôm sau. Lúc 12:05 tải lại lỗi. Có thể dùng bản cũ không?

**Đáp án:** Bản đã được thẩm định vẫn chưa hết `validUntil`; theo OASIS, quá hạn cache không tự làm metadata vô hiệu. Có thể tiếp tục dùng nếu chính sách của tổ chức cho phép, đồng thời cảnh báo/retry. Không dùng sau `validUntil`.

**Câu 2:** IdP gửi XML parse được nhưng `entityID` là IdP của môi trường thử nghiệm. Có được chấp nhận vì SSL vẫn hợp lệ?

**Đáp án:** Không. TLS không thay việc kiểm tra entityID, trust context và issuer đúng của registration.

**Câu 3:** SP có metadata hợp lệ và certificate mới, nhưng trang login IdP trả 503. Có thể dùng metadata cache để xác thực người dùng mới không?

**Đáp án:** Không. Metadata chỉ là cấu hình tin cậy; login mới vẫn cần IdP thực hiện luồng xác thực SAML hoặc cơ chế dự phòng đã duyệt.

**Câu 4:** Metadata không có `validUntil` và cacheDuration đã qua. Nó có bắt buộc vô hiệu theo SAML không?

**Đáp án:** Không chỉ vì cacheDuration. Tuy nhiên bên tiêu thụ phải có chính sách refresh/tuổi tối đa; thiếu validUntil không phải quyền tin vĩnh viễn.

**Câu 5:** Sau certificate rotation, IdP phát SAML Response bằng key không có trong trusted metadata. Có nên disable signature verification tạm?

**Đáp án:** Không. Cần cập nhật chứng thư từ nguồn đáng tin và kiểm chứng lại để duy trì ranh giới tin cậy.

**Câu 6:** Một lần tải metadata mới trả XML sai, nhưng bản LKG còn hiệu lực. Có nên thay repository bằng bản lỗi?

**Đáp án:** Không. Giữ bản đã kiểm chứng, ghi cảnh báo và thử lại; chỉ thay khi candidate mới thỏa yêu cầu bảo mật.

**Câu 7:** Người dùng đã đăng nhập Portal và có SP HttpSession còn hợp lệ, sau đó IdP down. Có phải lập tức hủy mọi phiên SP?

**Đáp án:** Không mặc nhiên. Phiên SP có vòng đời và chính sách riêng; nếu cần xác thực lại hoặc reauthorization thì thao tác đó có thể bị chặn.

## 15. Checklist triển khai sản xuất

- [ ] Chỉ lấy metadata từ IdP/URL được cấp phép và kiểm chứng HTTPS hoặc metadata signature bằng trust anchor phù hợp.
- [ ] Xác định đúng `entityID`, `IDPSSODescriptor`, binding, SSO endpoint và X.509 verification credentials.
- [ ] Thực thi `validUntil` hữu hiệu; phân biệt rõ với `cacheDuration` và chính sách tuổi metadata nội bộ.
- [ ] XML parser chống XXE/DTD và giới hạn độ lớn tài liệu; bảo vệ metadata URL khỏi SSRF.
- [ ] Candidate mới qua parse/semantic/signature/trust/time validation **trước** khi thay bản hiện hành.
- [ ] Có snapshot LKG tin cậy và chỉ dùng khi vẫn hợp lệ, có alert, TTL/retry/backoff phù hợp.
- [ ] Phân biệt outage metadata endpoint và outage IdP SSO; có thông báo login lỗi hợp lý.
- [ ] Theo dõi certificate rollover, cấu hình signing/verification và metadata cập nhật đúng thời điểm.
- [ ] Khi dùng InMemory, hiểu nó không tự refresh; nếu dùng Caching, cấu hình eviction và expiry policy riêng.
- [ ] Với metadata repository dựa OpenSAML, chọn trust model và metadata signature verification đúng theo phiên bản API.
- [ ] Không chấp nhận SAML Response sai issuer, signature, audience/recipient, time hoặc tenant dù IdP đang lỗi.
- [ ] Không cho phép failover sang IdP khác khi chưa có account mapping và authorization được phê duyệt.
- [ ] Giám sát refresh age, validUntil, lỗi parse/trust, login failure, certificate expiry và sự cố IdP.
- [ ] Có runbook và kiểm thử hỗn loạn: IdP 503, DNS/TLS fail, XML malformed, signature sai, validUntil expired, key rotation, SSO endpoint down.
- [ ] Có kế hoạch phục hồi/downtime khi không còn trusted metadata hợp lệ; không nới lỏng security controls để tăng availability.

## 16. Kết luận

Với SAML2 federation, **metadata là dữ liệu bảo mật điều khiển quan hệ tin cậy**. Khi **cache đến hạn**, ưu tiên refresh nhưng có thể dùng bản đã kiểm chứng còn hiệu lực theo policy. Khi **validUntil đã qua**, không được dùng metadata hết hạn. Khi **metadata sai cấu trúc/chữ ký**, từ chối bản mới và chỉ giữ bản LKG còn hợp lệ. Khi **IdP SSO down**, metadata cache không thay thế được xác thực mới; phiên SP hiện có do chính sách ứng dụng quyết định.

Trong Spring Security, `RelyingPartyRegistrationRepository` phải luôn cung cấp registration dựa trên thông tin đáng tin. `InMemoryRelyingPartyRegistrationRepository` phù hợp cấu hình ổn định; refresh chủ động, caching policy hoặc `AssertingPartyMetadataRepository` có metadata resolver phù hợp là lựa chọn khi vận hành IdP thay đổi thường xuyên. Không đánh đổi xác minh SAML/metadata lấy sự tiện lợi khi sự cố xảy ra.

### Tài liệu tham khảo chính thức

- **OASIS SAML 2.0 Metadata**: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- **OASIS SAML 2.0 Errata 05**, mục E94 (phân biệt metadata caching và validity): https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html
- **Spring Security – SAML 2.0 Login Overview**, phần registration, InMemory và Caching: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- **Spring Security – SAML 2.0 Metadata**, phần AssertingPartyMetadataRepository và signature: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- **Spring Security – Authenticating SAML Responses**: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- **Spring Security – CachingRelyingPartyRegistrationRepository API**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/CachingRelyingPartyRegistrationRepository.html
