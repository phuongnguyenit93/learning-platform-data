# Kiểm soát URL metadata, chuyển hướng HTTP và nguy cơ SSRF trong SAML2

> **Ngữ cảnh:** Spring Security – federation, phần **Metadata SAML2**. Bài tập trung vào việc Service Provider (SP/Relying Party) lấy metadata của Identity Provider (IdP/Asserting Party) từ nguồn tin cậy, cách đối xử với HTTP redirect, và nguy cơ **Server-Side Request Forgery (SSRF)** khi URL metadata do bên ngoài kiểm soát. Bài cũng phân biệt URL công bố SP metadata và các redirect của luồng đăng nhập SAML, vốn có chức năng khác.

## 1. Vì sao URL metadata là ranh giới bảo mật?

Trong federation SAML2, metadata không chỉ là tệp XML mô tả hệ thống: nó mang thông tin quyết định **ứng dụng tin ai và gửi/nhận thông điệp ở đâu**. Metadata IdP thường gồm `entityID`, `IDPSSODescriptor`, endpoint `SingleSignOnService` theo các binding được hỗ trợ, chứng thư X.509 dùng để xác minh chữ ký, và đôi khi endpoint Single Logout. Metadata SP thường gồm `entityID`, `SPSSODescriptor`, `AssertionConsumerService` và chứng thư công khai của SP nếu được cấu hình.

Nếu một ứng dụng cho phép người dùng, tenant hoặc đối tác bất kỳ đưa vào URL metadata rồi backend tự tải, backend đã trở thành một **HTTP client hoạt động bên trong mạng** theo lệnh bên ngoài. Đây là một cửa ngõ SSRF. Đồng thời, nếu metadata tải về được chấp nhận vô điều kiện, đối thủ có thể thay khóa/endpoint IdP mà SP tin tưởng, dẫn tới hậu quả **chiếm quan hệ federation**, ngay cả khi chưa khai thác được truy cập mạng nội bộ.

**Hai loại rủi ro độc lập cần phòng vệ:**

1. **SSRF qua đường tải:** backend gửi HTTP request tới IP/host/đường dẫn không được phép, có thể chạm loopback, mạng nội bộ, service quản trị hoặc cloud instance metadata service.
2. **Đầu độc quan hệ tin cậy:** XML nhận được khiến SP thay `entityID`, SSO URL hoặc public key mà nó sẽ dùng để xác thực `SAMLResponse` từ IdP. Nếu bộ xác minh lấy certificate từ XML không đáng tin, chữ ký của assertion giả cũng có thể được chấp nhận vì chính bên tấn công đã chọn khóa.

Hai lớp kiểm tra này không thay thế nhau. Một URL HTTPS hoàn toàn công khai có thể trả metadata giả; một metadata ký hợp lệ từ nguồn đã đăng ký cũng không cho phép backend tùy ý theo redirect tới host nội bộ.

### 1.1. Xác định đúng các URL và vai trò

| Giá trị/endpoint | Thường do ai sử dụng? | Có được ứng dụng Spring tự tải qua mạng không? | Ý nghĩa |
| --- | --- | --- | --- |
| **IdP metadata location** như `https://idp.partner.example/saml/metadata` | Backend SP hoặc job quản trị/refresh metadata | **Có, nếu cấu hình dùng metadata qua URL** | Nguồn XML xác lập cấu hình IdP |
| **IdP `entityID`** như `https://idp.partner.example/issuer` | Bộ xác minh SAML của SP | **Không tự động chỉ vì có dạng URL** | Định danh logic của IdP; so sánh với issuer trong SAML |
| **`SingleSignOnService Location`** | Trình duyệt chuyển đến IdP khi SP khởi tạo SSO | Chủ yếu là đích của luồng SAML qua browser | Endpoint nhận `AuthnRequest`; vẫn phải được phê duyệt |
| **SP metadata URL** như `https://sp.example.org/saml2/metadata/partner` | IdP/đội vận hành đọc metadata SP | **Là URL SP xuất bản** | Giới thiệu entityID, ACS, chứng thư công khai của SP |
| **SP ACS** như `https://sp.example.org/login/saml2/sso/partner` | Browser POST `SAMLResponse` từ IdP | Không phải URL tải IdP metadata | Endpoint Spring xác minh assertion và tạo phiên |
| **Cloud instance metadata** như `169.254.169.254` | Máy chủ/cloud agent nội bộ | **Không phải SAML metadata** | Có thể mang thông tin hạ tầng/credential; mục tiêu SSRF phổ biến |

**Quy tắc nhớ:** `entityID` là **identifier**, không phải một mệnh lệnh “hãy GET URL này”. Chỉ những URL được thiết kế làm network endpoint mới được dùng làm đích request, và chúng vẫn phải thuộc hợp đồng tin cậy.

## 2. Luồng tải IdP metadata và cách SSRF xuất hiện

Luồng hợp lệ:

```text
[Quản trị viên phê duyệt IdP]
             |
             v
[Cấu hình cố định URL hoặc file metadata]
             |
             v
[Backend SP / job tải metadata]
             |
             | HTTPS GET chỉ tới đích được phép
             v
[IdP metadata endpoint]
             |
             | XML (entityID, SSO endpoints, signing certs)
             v
[Kiểm tra nguồn + tính toàn vẹn + đối tác + cấu trúc]
             |
             v
[RelyingPartyRegistration / repository]
             |
             v
[Xác minh SAMLResponse khi đăng nhập]
```

Luồng sai điển hình:

```text
[User/tenant nhập metadataUrl bất kỳ]
                    |
                    v
[Backend GET metadataUrl]
                    |
                    | Server đầu tiên trả 302 Location: host nội bộ
                    v
[HTTP client tự theo redirect]
                    |
                    v
[127.0.0.1 / mạng private / service quản trị / cloud metadata]
                    |
                    v
[Phản hồi bị lộ hoặc request tạo tác động bên trong mạng]
```

SSRF có thể xảy ra **trước cả khi một XML SAML hợp lệ xuất hiện**. Nếu hệ thống trả nội dung/lỗi/độ trễ của request cho người nhập URL, đối thủ có thể học được cấu trúc dịch vụ nội bộ. Kể cả không trả body, SSRF dạng “blind” vẫn có thể gây side effect hoặc tạo dấu hiệu phân biệt host đang hoạt động.

### 2.1. Những nơi dễ vô tình chấp nhận URL bên ngoài

- Form **“Add identity provider”** trong hệ thống đa tenant cho người dùng nhập metadata URL.
- API onboard đối tác nhận JSON có trường `metadataUrl` hoặc `metadata_uri` rồi gọi `RelyingPartyRegistrations.fromMetadataLocation(value)` ngay trong request.
- Scheduler làm mới metadata định kỳ, lấy URL từ database do tenant/admin cấp thấp sửa được.
- Chức năng “Test metadata”, “Validate SAML connection” hoặc “Preview IdP settings” tải URL để kiểm tra.
- Bộ nạp metadata federation aggregate có các URL tham chiếu, import, resolver hoặc tải tài nguyên bên ngoài.
- API nhận “SP metadata URL” của đối tác rồi server chủ động fetch, trong khi mục đích thực tế chỉ cần người quản trị tải file theo đường riêng.

Không nên phỏng đoán rằng một API tải metadata “chỉ phục vụ admin” thì chắc chắn an toàn: tài khoản admin cấp tenant có thể không được phép điều khiển HTTP client đi vào các mạng/credential của hệ thống chủ. Cần tách **quyền cấu hình danh tính** khỏi **quyền điều khiển kết nối mạng**.

### 2.2. Rủi ro kéo theo khi metadata bị thay đổi

Nếu người tấn công thay được IdP metadata, họ có thể cố đưa vào chứng thư X.509 mới dưới `KeyDescriptor use="signing"` hoặc endpoint SSO của họ. SP lấy metadata mới và chấp nhận nó có thể bắt đầu tin assertion do kẻ tấn công ký. Vì thế một lần tải thành công qua HTTPS **không tự cho phép** thay đổi khóa tin cậy của IdP mà không có quy trình kiểm chứng; TLS chỉ giúp xác định/kênh đến máy chủ được truy cập trong điều kiện PKI còn tin cậy, không kiểm tra thẩm quyền thay đổi cấu hình federation.

## 3. Phân biệt ba khái niệm “redirect” rất dễ nhầm

| Tên gọi | Ai thực hiện? | Ví dụ | Liên quan SSRF thế nào? |
| --- | --- | --- | --- |
| **SAML HTTP-Redirect Binding** | SP/IdP hướng **trình duyệt** tới endpoint SSO, truyền thông điệp SAML mã hóa trong URL | Browser tới IdP với `SAMLRequest` và có thể `RelayState` | Là một binding của giao thức SAML; **không đồng nghĩa** backend tự fetch metadata |
| **HTTP 30x khi backend tải metadata** | Máy chủ metadata trả `301`, `302`, `303`, `307` hoặc `308` và `Location` | GET metadata trả 302 đến host/URL mới | Nếu HTTP client tự theo `Location` mà không xác minh lại đích, có thể gây SSRF |
| **Redirect HTTP của ứng dụng/web login** | Web app chuyển browser sang trang login hoặc sau đăng nhập | `302 Location: /login` hoặc tới IdP | Thường không phải SSRF; nhưng `returnUrl`/`RelayState` không được tạo **open redirect** tới miền bất kỳ |

Ở cấp HTTP, một SAML AuthnRequest dùng HTTP-Redirect Binding có thể dùng status 302 để đưa **browser** tới IdP. Nhưng việc backend Spring **tự tải metadata** và tự động follow 302 được điều khiển bởi **HTTP client và chính sách URL của backend**. Hai chuyện khác nhau về actor, tài nguyên và mức tin cậy.

**Cách xử lý an toàn nhất khi tải metadata:** không tự theo HTTP redirect. Nếu IdP chính thức chuyển metadata sang URL mới, yêu cầu người quản trị phê duyệt URL mới, cập nhật allowlist và xác minh lại khóa/issuer. Đừng coi `301 Moved Permanently` là quyền tự động mở rộng trust. Khi có yêu cầu nghiệp vụ phải theo redirect, từng hop phải được xác minh như URL ban đầu, giới hạn số hop, cấm downgrade HTTPS→HTTP và chống DNS rebinding/redirect loop; giải pháp đơn giản hơn vẫn là **fail closed trên mọi 30x**.

## 4. Chính sách kiểm soát URL: ưu tiên cấu hình có nguồn gốc tin cậy

### 4.1. Cấp quyền cho từng đối tác, không cấp quyền cho mọi URL

Với một federation có danh sách IdP hữu hạn, hãy lập danh mục:

| Thuộc tính | Ví dụ minh họa |
| --- | --- |
| Partner / tenant | `partner-a` |
| Registration ID nội bộ | `partner` |
| URL metadata được duyệt | `https://idp.partner.example/saml/metadata` |
| IdP entityID mong đợi | `https://idp.partner.example/issuer` |
| Host/IP/kênh mạng được phép | Do đội hạ tầng phê duyệt, đi qua egress policy cụ thể |
| Chứng thư ký metadata/IdP được tin | Khóa hoặc fingerprint đã duyệt, quy trình rollover |
| Thời hạn kiểm tra/refresh | Theo chính sách, có owner và giám sát |
| Người phê duyệt thay đổi | Chủ quan hệ federation và phụ trách an ninh/IdP |

Thay vì nhận cả một URL từ người dùng, client có thể chỉ gửi **partnerId** đã được định danh, rồi server **lấy URL cấu hình từ danh mục do quản trị viên có thẩm quyền kiểm soát**. Điều này tránh nhiều lỗi parser, userinfo (`user@host`), đổi scheme, port, path hoặc query.

Nếu thật sự cần onboarding IdP mới bởi tenant, hãy dùng luồng **đề xuất → xác minh → duyệt → kích hoạt**. Không tải URL mới bằng một worker có quyền truy cập toàn bộ mạng nội bộ ngay trong request public.

### 4.2. Khi bắt buộc nhận URL, phải giới hạn nhiều lớp

1. **Scheme:** bắt buộc `https` cho môi trường thật; từ chối `http`, `file`, `jar`, `ftp`, `gopher`, `data` và scheme không được phê duyệt. `classpath:` chỉ dành cho tài nguyên đóng gói do ứng dụng kiểm soát, không phải scheme để tenant tùy ý chọn.
2. **Hostname/FQDN:** so khớp với allowlist **chính xác**, không dùng `contains("trusted.example")` hoặc `endsWith("trusted.example")` thiếu kiểm tra ranh giới dấu chấm. Tên tương tự `trusted.example.attacker.invalid` không được chấp nhận.
3. **Port:** chỉ dùng port TLS đã duyệt, thông thường 443; cấm các port quản trị, database và ngẫu nhiên.
4. **Path/query:** dùng path/URL cố định trong cấu hình; không ghép raw path/query từ dữ liệu đầu vào để tạo URL tải.
5. **Userinfo/fragment:** không cho phép `username:password@host`, fragment bất thường, URL rỗng hoặc parser ambiguity. Nếu chính sách chỉ cho phép một canonical URL, **so sánh nguyên URL đã duyệt** và tạo request từ canonical URI đó.
6. **IP đích thực tế:** qua DNS có thể xuất hiện IP loopback, private, link-local, unique-local IPv6, multicast hoặc address thuộc cloud metadata service; chính sách mạng phải quyết định IP hợp lệ và **buộc kết nối tới IP đã xác minh** hoặc chặn tại egress. Kiểm tra DNS trước rồi HTTP client tự resolve lại có thể bị **DNS rebinding / TOCTOU**.
7. **HTTP redirect:** tắt tự follow và xử lý 30x là lỗi có kiểm soát. Không chấp nhận chuyển từ HTTPS sang HTTP.
8. **Trung gian mạng:** nếu HTTP client đi qua proxy, forward proxy/egress gateway cũng phải thực thi allowlist đích và không cho tunnel vượt chính sách.
9. **Response:** giới hạn kích thước, thời gian connect/read, content type chấp nhận được, số lần thử lại và tốc độ refresh. Chỉ xử lý XML qua parser/bộ thư viện SAML an toàn.
10. **Tác vụ tải:** chạy dưới service account không có quyền đọc credential/metadata cloud không cần thiết, hạn chế quyền outbound và cô lập khỏi API quản trị nội bộ.

**Không dùng blacklist đơn lẻ.** Danh sách cấm vài IP như `127.0.0.1` hay `169.254.169.254` rất dễ thiếu IPv6, subnet nội bộ, alias DNS hoặc dạng biểu diễn IP khác. Trong mạng thực tế có nhu cầu IdP private, danh mục IP/private endpoint phải được **phê duyệt riêng** và cô lập, không đặt quy tắc “cấm mọi private IP” khiến tích hợp hợp lệ thất bại rồi bị tắt kiểm tra.

### 4.3. DNS rebinding là lỗi thời điểm kết nối, không chỉ lỗi cú pháp

Một triển khai dễ sai:

```text
1. Resolve idp.partner.example -> IP công khai
2. Kiểm tra IP công khai, đánh dấu an toàn
3. HTTP client resolve lại hostname sau đó
4. Lần DNS thứ hai trả IP nội bộ
5. HTTP client kết nối IP nội bộ
```

Đây là race giữa **kiểm tra DNS** và **kết nối thực tế**. Cách giảm thiểu có thể gồm egress proxy chỉ cho các host/đích được phép, resolver đã kiểm soát, connection pinning tới IP được xác minh mà vẫn giữ SNI/Host và kiểm tra certificate đúng tên miền, hoặc tầng mạng chặn kết nối tới dải mạng cấm. **Java `HttpClient` trong ví dụ bên dưới không tự cung cấp pinning IP cho mọi trường hợp**. Vì thế kiểm tra URI + tắt redirect trong code là cần thiết nhưng **chưa đủ** nếu domain được phép có thể bị kiểm soát DNS.

## 5. Spring Security: hai hướng cấu hình metadata khác nhau

### 5.1. Nạp IdP metadata từ URL do quản trị viên đã phê duyệt

Spring Security hỗ trợ xây `RelyingPartyRegistration` từ địa chỉ metadata, ví dụ:

```java
RelyingPartyRegistration registration =
    RelyingPartyRegistrations
        .fromMetadataLocation("https://idp.partner.example/saml/metadata")
        .registrationId("partner")
        .build();
```

Đây là **đoạn mã minh họa**, dùng trong ứng dụng Spring Security có dependency `spring-security-saml2-service-provider` và imports phù hợp. Phương thức `fromMetadataLocation` đọc metadata theo location đã cung cấp. Khi location là URL mạng, **thao tác tải diễn ra từ backend** theo khả năng của resource/client mà thư viện sử dụng. Không truyền `request.getParameter("metadataUrl")` hoặc trường JSON của tenant trực tiếp vào lời gọi này.

**Quan trọng:** Không suy đoán rằng API nạp metadata của Spring tự động triển khai đầy đủ chính sách chống SSRF của tổ chức. Hành vi HTTP redirect, timeout, proxy, XML/metadata refresh và xác minh chữ ký phụ thuộc phiên bản, cấu hình và API cụ thể; cần kiểm thử và bao bọc bằng cơ chế chính sách phù hợp.

Một registration từ metadata không có nghĩa **bất kỳ signing certificate nào có trong XML đều đáng tin**. Cần xác thực nguồn, kiểm tra entityID mong đợi, xác nhận nguồn khóa đáng tin, điều kiện làm mới và kiểm soát thay đổi. Với metadata ký, phải cấu hình **trust anchor/verification credential** thích hợp; không tự cho rằng chỉ vì XML có `Signature` thì chữ ký đã được verify với khóa độc lập đáng tin cậy.

### 5.2. Khóa nguồn metadata vào resource `classpath` đã được phê duyệt

Đối với IdP ít thay đổi hoặc phòng lab có bản metadata đã được kiểm tra, cách dễ quản trị hơn là lấy XML qua kênh quản trị đáng tin cậy, kiểm tra ngoại tuyến rồi đóng gói cùng release.

File: `src/main/resources/saml/idp-partner-approved.xml` (bản XML **thật, nguyên vẹn, đã được phê duyệt**, không phải file mới tự tạo từ claim của người dùng).

Cấu hình Java Spring Security 6+/Java 17+ sau đây tạo registration từ file classpath và bật SAML login/metadata; mã thuộc dự án Spring Boot có Spring Web và `spring-security-saml2-service-provider`, **không phải chương trình tự chạy bằng `javac` thuần**.

```java
package com.example.samlmetadata;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
    RelyingPartyRegistrationRepository relyingParties() {
        RelyingPartyRegistration partner =
            RelyingPartyRegistrations
                .fromMetadataLocation("classpath:saml/idp-partner-approved.xml")
                .registrationId("partner")
                .build();
        return new InMemoryRelyingPartyRegistrationRepository(partner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/").permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/saml2/authenticate/**",
                    "/saml2/metadata",
                    "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**")
                    .permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/login/saml2/sso",
                    "/login/saml2/sso/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
```

**Giải thích:**

- Spring lấy cấu hình IdP từ `classpath` khi tạo bean; không có URL IdP metadata lấy từ request hoặc các tenant khác.
- `registrationId` là `partner`, được dùng để phân biệt registration; nó **không phải URL mạng** và không được tự suy ra thành host cần fetch.
- `saml2Login` xử lý AuthnRequest và `SAMLResponse`; `saml2Metadata` **công bố metadata của SP**. Hai DSL phục vụ chiều dữ liệu khác nhau.
- Các endpoint công khai trong ví dụ vẫn đi qua SecurityFilterChain; `permitAll` không bỏ qua kiểm tra chữ ký SAML ở ACS.
- Metadata XML dù nằm trên classpath vẫn phải được kiểm chứng từ nguồn tin cậy, kiểm tra `entityID` và chứng thư trước khi build; cập nhật file cần đi qua quy trình review/CI/CD. Không tự coi “đã nằm trên classpath” là bằng chứng metadata đúng.
- Cấu hình này không tự xử lý giải mã assertion, request signing hay SLO nếu IdP yêu cầu; cần cấu hình RP tương ứng sau khi thỏa thuận với IdP.

**Khác biệt về vòng đời:** Cách nạp classpath giúp tránh outbound metadata fetch tùy ý ở runtime, đổi lại cần quy trình cập nhật certificate/endpoint khi IdP xoay khóa. Một cơ chế dynamic refresh là hợp lệ nếu dùng dữ liệu/nguồn đã phê duyệt và có xác minh trước khi thay trust store, nhưng không nên cho refresh tự kích hoạt bởi URL đến từ người dùng.

## 6. Mẫu Java 17+ cho HTTP client tải URL được duyệt và từ chối redirect

Ví dụ dưới đây có **một URL metadata cố định**. Nó trình diễn cách giới hạn HTTP redirect, timeout, kích thước body, và **không dùng URL của request đầu vào để tạo network request**. Đích `idp.partner.example` là miền ví dụ; class có thể biên dịch độc lập bằng JDK 17+, nhưng để thực sự tải được metadata cần thay **hằng số được quản trị phê duyệt** bằng endpoint HTTPS hợp lệ, bảo đảm egress/TLS/CA tin cậy và xử lý XML sau khi tải.

File `ApprovedMetadataFetch.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class ApprovedMetadataFetch {
    private static final URI APPROVED =
        URI.create("https://idp.partner.example/saml/metadata");

    private static final int MAX_BYTES = 1024 * 1024;

    private ApprovedMetadataFetch() {
    }

    // Chỉ dùng để minh họa allowlist exact URL; luôn fetch bằng APPROVED.
    static boolean isApproved(String candidate) {
        return APPROVED.toASCIIString().equals(candidate);
    }

    static byte[] fetchApproved() throws IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NEVER)
            .connectTimeout(Duration.ofSeconds(3))
            .build();

        HttpRequest request = HttpRequest.newBuilder(APPROVED)
            .timeout(Duration.ofSeconds(8))
            .header("Accept", "application/samlmetadata+xml, application/xml")
            .GET()
            .build();

        HttpResponse<InputStream> response =
            client.send(request, HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {

            // Bao gồm 301, 302, 303, 307 và 308: tất cả đều bị từ chối.
            if (response.statusCode() != 200) {
                throw new IOException(
                    "Metadata fetch returned HTTP " + response.statusCode());
            }

            byte[] buffer = new byte[8192];
            int total = 0;
            int n;

            while ((n = body.read(buffer)) != -1) {
                total += n;
                if (total > MAX_BYTES) {
                    throw new IOException("Metadata exceeds byte limit");
                }
                output.write(buffer, 0, n);
            }

            return output.toByteArray();
        }
    }

    public static void main(String[] args) {
        System.out.println(isApproved(
            "https://idp.partner.example/saml/metadata"));
        System.out.println(isApproved(
            "http://idp.partner.example/saml/metadata"));
        System.out.println(isApproved(
            "https://idp.partner.example/other"));
        System.out.println(isApproved(
            "https://idp.partner.example/saml/metadata?next=1"));
    }
}
```

Lệnh biên dịch/chạy **chỉ phần chính sách thuần Java** (không gọi HTTP, không cần Spring):

```bash
javac --release 17 ApprovedMetadataFetch.java
java ApprovedMetadataFetch
```

Stdout chính xác:

```text
true
false
false
false
```

**Điều mã đã làm:**

- Chỉ tạo request tới hằng `APPROVED`, **không** dùng `candidate` để làm địa chỉ tải.
- `Redirect.NEVER` không tự theo bất kỳ status 30x; `response.statusCode() != 200` biến redirect thành lỗi.
- Có timeout kết nối, timeout request và giới hạn số byte XML trong body khi đọc.
- Mặc định Java HTTPS client vẫn kiểm tra chứng thư TLS bằng trust store đã cấu hình; không gọi trust-all manager hoặc bỏ hostname verification.
- Đóng stream khi thành công hay lỗi; không in nội dung body/token ra console.

**Điều mã cố ý chưa làm và vì sao phải có lớp bảo vệ bổ sung:**

- Chưa xử lý **DNS rebinding** hoặc buộc kết nối tới IP đã phê duyệt; bắt buộc có DNS/egress policy kiểm soát đường tới miền được phép.
- Chưa parse XML, kiểm tra `entityID`, chứng thư/metadata signature, `validUntil` hoặc chính sách rollover; **không truyền `byte[]` vừa tải trực tiếp thành trust store** nếu chưa qua bước đánh giá.
- Chưa xử lý retry/cache/ETag, metadata lớn hợp lệ hoặc giới hạn tài nguyên ngoài bộ nhớ; chọn ngưỡng tối đa dựa trên IdP thật và chính sách hệ thống.
- Chưa kiểm tra `Content-Type`, response encoding hoặc bảo đảm XML an toàn; `Content-Type` chỉ là một tín hiệu, không phải xác minh bảo mật.
- Chưa cho phép IdP private endpoint; trường hợp đó cần phương án kết nối/allowlist rõ ràng ở tầng mạng, không tự bỏ tất cả hạn chế.
- Chưa chuyển động logic URL allowlist thành một dịch vụ phân quyền onboarding; một hằng số minh họa không thay thế quản lý cấu hình cấp doanh nghiệp.

### 6.1. Vì sao không tự gọi `fromMetadataLocation(candidate)`?

Ví dụ **không nên viết** trong một API public:

```java
// Minh họa anti-pattern, không dùng trong production:
String url = request.getParameter("metadataUrl");
RelyingPartyRegistration registration = RelyingPartyRegistrations
    .fromMetadataLocation(url)
    .registrationId("tenant")
    .build();
```

Không chỉ có rủi ro network: đối thủ có thể đưa metadata do mình kiểm soát vào registration, từ đó quyết định issuer/certificate mà SP chấp nhận. Không cho các chức năng `onboard`, `preview` hoặc `validate` biến quyền nhập chuỗi thành quyền **thiết lập niềm tin xác thực**.

Kiến trúc đúng cho đa tenant:

```text
Tenant gửi yêu cầu tích hợp
          |
          v
Lưu yêu cầu với trạng thái "pending"
          |
          v
Đội phê duyệt kiểm tra chủ sở hữu IdP, issuer, metadata URL,
chứng thư, IP/egress và quyền dữ liệu
          |
          v
Job tải từ URI được duyệt, không follow redirect,
giới hạn timeout/size, xác minh XML/trust
          |
          v
Lưu version metadata đã phê duyệt
          |
          v
Tạo/cập nhật registration tương ứng
          |
          v
Giám sát và quản lý refresh/rollover
```

## 7. Kiểm soát XML và tính toàn vẹn của metadata SAML2

SSRF qua URL là một phần của bài toán. Khi có dữ liệu XML, ứng dụng phải hiểu nội dung đó **là cấu hình xác thực có thẩm quyền**.

### 7.1. Cấu trúc và trường cần rà soát

Một IdP metadata hợp lệ thường dùng `EntityDescriptor` có `entityID` và `IDPSSODescriptor`. Ví dụ giản lược về cấu trúc, **không phải tài liệu XML có thể dùng để login thực tế**:

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.partner.example/issuer">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <!-- Public X.509 certificate data would appear here -->
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.partner.example/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
```

Trước khi đưa vào `RelyingPartyRegistrationRepository`, kiểm tra:

1. `entityID` đúng **định danh IdP đã ký kết**, không chọn tùy tiện phần tử đầu tiên khi XML chứa nhiều `EntityDescriptor`.
2. `IDPSSODescriptor` tồn tại, đúng SAML 2.0 protocol và chứa những binding/SSO endpoint được hỗ trợ/phê duyệt.
3. `KeyDescriptor` thuộc issuer được tin, certificate còn phù hợp với chính sách, không có thay khóa bất thường; phân biệt certificate dùng **verify chữ ký SAML** với certificate dùng **verify chữ ký metadata** khi có.
4. `validUntil`, `cacheDuration` hoặc cơ chế refresh được áp dụng đúng (khi có), đồng thời có tiêu chí từ chối phiên bản quá hạn/bị thu hồi theo chính sách.
5. XML được parser bằng thư viện SAML uy tín, vô hiệu hóa các tính năng external entity/DTD không cần thiết; đặt giới hạn parser, độ sâu, kích thước và thời gian.
6. Không tải thêm URL từ `Location`, `entityID` hoặc phần tử tham chiếu chỉ vì chúng xuất hiện trong XML; mỗi kết nối phụ phải có mục đích và allowlist riêng.
7. So sánh **diff** giữa metadata mới/cũ; đổi signing certificate, issuer, endpoint hoặc SLO bindings là thay đổi nhạy cảm cần được kiểm duyệt/ghi nhận.

### 7.2. Metadata signature không phải lúc nào cũng được xác minh mặc định

Spring Security hỗ trợ API metadata repository để xác minh chữ ký với **verification credentials** được tin trước, ví dụ khả năng của `OpenSaml5AssertingPartyMetadataRepository` trong tài liệu tương ứng. **Không được suy ra rằng XML có chữ ký thì Spring đã kiểm tra chữ ký bằng khóa độc lập đáng tin**. Tài liệu Spring lưu ý: khi không cung cấp credentials xác minh cho API repository đó, nó **không thực hiện signature validation**.

Điều quan trọng là xác định **trust anchor độc lập**: certificate hoặc khóa công khai metadata signing đã xác nhận qua kênh tổ chức, TLS server được xác thực, hoặc bản metadata được phê duyệt và pin. Nếu chỉ lấy chính certificate nằm trong XML chưa tin cậy để tự xác minh chữ ký của XML đó, một file giả tự ký vẫn có thể “verify thành công” về mặt toán học nhưng không chứng minh nó thuộc IdP đã thỏa thuận.

**Phân biệt thêm:** Signing certificate trong IdP metadata được SP dùng để kiểm tra **SAMLResponse/Assertion**, còn metadata signing certificate dùng để xác minh tính toàn vẹn/nguồn của **tài liệu metadata** khi mô hình có ký metadata. Hai chứng thư có thể giống hoặc khác tùy chính sách IdP; không tự đánh đồng.

### 7.3. XXE có thể biến parser XML thành một kênh SSRF khác

Ngay cả khi URL tải metadata được chặn cứng, XML độc hại chứa **external entity** hoặc DTD tham chiếu tài nguyên có thể khiến parser chưa cấu hình an toàn tự đọc file/network. Dùng OpenSAML và parser framework theo cấu hình secure; nếu phải tự parse XML, tắt DTD/external entities và external schema/stylesheet nếu không cần, hạn chế bộ nhớ và parse time. Tránh ghi lại nguyên XML/tokens khi gặp lỗi.

**Sơ đồ phòng thủ:** (1) kiểm tra URL và kết nối → (2) nhận body giới hạn → (3) parse XML an toàn → (4) xác minh issuer/keys/metadata signature theo trust anchor → (5) chỉ sau đó mới cập nhật registration. Thiếu bước nào cũng có thể làm mất ranh giới tin cậy.

## 8. Refresh metadata và xoay certificate mà không mở lỗ hổng

Metadata IdP thường phải được cập nhật khi IdP đổi certificate ký assertion, endpoint SSO hoặc chính sách SLO. Việc chỉ tắt refresh vĩnh viễn có thể gây lỗi đăng nhập khi certificate cũ hết hiệu lực, nhưng refresh tùy ý theo URL người dùng lại tạo SSRF và rủi ro bị đầu độc trust.

Quy trình đề xuất:

1. Lưu metadata **phiên bản hiện tại** cùng issuer, URL/nguồn, fingerprint, thời gian tải và người/luồng phê duyệt.
2. Refresh bằng job có lịch và **egress riêng**, chỉ dùng nguồn đã duyệt. HTTP redirect mới hoặc đổi domain làm job thất bại và tạo cảnh báo.
3. Kiểm tra HTTPS, XML, issuer, metadata signature/trust và thay đổi certificate. Bảo đảm bản tải về đúng **partner** và không ghi đè registration khác.
4. Xác định metadata mới là bản được phê duyệt hay chờ review. Nếu cần tự động thay khóa, đặt quy tắc rõ ràng: trust anchor độc lập, kiểm tra signature, phạm vi thay đổi và giai đoạn overlap.
5. Cập nhật repository **nguyên tử**, tránh để request đăng nhập nhìn thấy registration đang sửa dở hoặc certificate nửa cũ/nửa mới.
6. Có rollback rõ ràng và giám sát: lỗi chữ ký SAML, metadata fetch 30x, diff issuer/certificate, chứng thư sắp hết hạn, stale metadata và phản hồi 5xx từ IdP.
7. Khi fetch thất bại, **không fallback sang URL vừa xuất hiện trong redirect** và không “trust all certificate” để khôi phục. Chính sách dùng cache trước đó hay ngừng tạo phiên mới phải dựa trên hạn hiệu lực và mức rủi ro đã quyết định.
8. Nếu issuer/khóa bị nghi xâm nhập, tạm dừng quan hệ tin cậy và xử lý phiên đã tạo, không coi việc thay tệp XML là đủ để thu hồi danh tính giả đã được chấp nhận.

Ở hệ đa tenant, nên tách signing credential, issuer và lịch refresh theo partner; đừng chia sẻ một file metadata động cho tất cả tenants nếu nội dung và quyền quản trị khác nhau.

## 9. Xuất bản SP metadata: quản lý URL, redirect và header công khai

Spring Security có thể công bố metadata SP bằng DSL:

```java
http
    .saml2Login(Customizer.withDefaults())
    .saml2Metadata(Customizer.withDefaults());
```

Các endpoint mặc định thường là:

- `GET /saml2/metadata` — metadata của tập RP registration.
- `GET /saml2/metadata/{registrationId}` — metadata của một RP cụ thể.
- `GET /saml2/service-provider-metadata/{registrationId}` — URL tương thích cho RP đó.

**Đây là chiều IdP/đối tác lấy metadata do SP công bố**, khác với việc Spring backend tải metadata của IdP. Endpoint public metadata trả XML công khai của SP; nếu không có tính năng nhận một URL từ người dùng để fetch, endpoint ấy **không tự là SSRF**. Tuy nhiên, vẫn cần kiểm soát:

- Metadata công bố phải chứa `entityID`, ACS, binding và certificate công khai đúng SP/tenant.
- Không để `{baseUrl}` do Host/`X-Forwarded-Host` từ client không tin cậy quyết định. Cấu hình canonical HTTPS host và trusted proxy để tránh phát metadata chứa ACS/issuer do người ngoài điều khiển.
- Nếu có nhiều tenant, có thể giới hạn khả năng enumerate registrations qua `/saml2/metadata`, công bố per-tenant theo chính sách hoặc phân phối metadata qua kênh quản trị.
- Đừng chèn private signing key, secret, session cookie hoặc raw assertion vào SP metadata.
- Tạo security headers và authorization cho các URL công khai theo yêu cầu; sử dụng `permitAll()` thay vì bỏ qua toàn bộ SecurityFilterChain khi phù hợp.
- Nếu reverse proxy đưa endpoint metadata qua `301/302` từ HTTP sang HTTPS, IdP downloader **có thể không tự follow**; hãy cấp URL HTTPS cuối cùng trực tiếp, thống nhất FQDN và tránh redirect chain không cần thiết.

Nếu app tự làm endpoint kiểu `GET /metadata?url=...` và backend fetch XML theo tham số, đó là **proxy/fetcher có nguy cơ SSRF**, không phải endpoint xuất SP metadata chuẩn. Đừng tạo nó chỉ để “tiện debug”.

### 9.1. Cẩn thận với Host header và reverse proxy

Ví dụ khi Spring đặt sau reverse proxy TLS termination, URL public có thể là `https://sp.example.org` còn upstream là `http://app:8080`. Nếu app tin `X-Forwarded-Proto`/`X-Forwarded-Host` do client tự gửi, nó có thể phát metadata với `entityID`/ACS sai. Cần proxy xóa forwarded headers từ client, chèn giá trị chính xác và backend chỉ cho request từ proxy đáng tin. Sau triển khai, GET metadata thật và đối chiếu SAML entityID/ACS với cấu hình IdP.

Việc metadata SP xuất ra URL sai thường gây **mismatch `Destination`/`Recipient` hoặc đăng nhập vòng lặp**, không thể sửa bằng cách bỏ kiểm tra SAML signature hoặc bật all-permit.

## 10. Threat model và ma trận kiểm thử SSRF

| Kiểm thử/đầu vào lab | Kết quả phải đạt | Bằng chứng cần giữ |
| --- | --- | --- |
| URI HTTPS metadata chính xác trong allowlist | Chỉ gửi request tới endpoint đã duyệt, xử lý đúng XML sau validation | Audit partnerId, đích đã duyệt, kết quả xác minh |
| `http://` thay `https://` | Từ chối vì sai scheme | Lỗi policy không làm request outbound |
| Cùng host nhưng port/path/query không phê duyệt | Từ chối | Không có kết nối tới đích tự chọn |
| Host trông giống tên đối tác nhưng có thêm hậu tố | Từ chối | Unit test parser/allowlist |
| URL có `userinfo@host`, IP literal, IPv6 loopback, hostname nội bộ | Từ chối nếu ngoài chính sách | Không gọi network khi bị từ chối |
| Endpoint được phép trả HTTP `301/302/303/307/308` với `Location` khác | **Không follow**, trả lỗi có kiểm soát | Log status, không chứa bí mật của redirect target |
| Endpoint HTTPS trả `Location: http://...` | Không tự downgrade sang HTTP | Không có HTTP request thứ hai |
| DNS của host được phép trỏ IP private/link-local/loopback trái chính sách | Chặn ở tầng kết nối/egress | Counter, firewall/egress-deny log, kiểm tra IPv4+IPv6 |
| XML chứa external entity/DTD cần fetch URL ngoài | Parser không thực hiện fetch | Test XXE trong sandbox, không đọc file/network |
| XML sai issuer, sai chữ ký metadata hoặc certificate chưa được duyệt | Không cập nhật trust/repository | Diff/validation failure, giữ bản metadata trước theo chính sách |
| XML hợp lệ nhưng đổi signing key bất ngờ | Chờ phê duyệt hoặc quy trình rollover đáng tin | Audit key fingerprint, sự kiện approval |
| Response metadata quá lớn, chậm, never-ending stream | Hết timeout/quota, đóng kết nối | Metric timeout/size, không OOM |
| SP metadata endpoint được truy cập qua Host header giả | Không sinh entityID/ACS theo host do attacker chỉ định | Kết quả đối chiếu canonical HTTPS URL |
| Người chưa login gọi `/saml2/metadata/partner` | Theo chính sách công bố, chỉ nhận **SP public metadata** | Không lộ private key/secret/assertion |

**Cách thử an toàn:** dùng server giả, proxy/MockWebServer/WireMock hoặc sandbox do nhóm kiểm thử kiểm soát. Mô phỏng `Location` và XML độc hại; kiểm tra HTTP client có thật sự **không tạo kết nối thứ hai**. Không cần gửi request tới hệ thống quản trị/cloud metadata thật để chứng minh đã chống SSRF.

Nếu kiểm thử egress được triển khai trên Kubernetes/VM/cloud, kiểm tra ở **đường kết nối thực tế** của pod/container, bao gồm forward proxy và IPv6, không chỉ dựa vào phép so sánh hostname trong unit test.

## 11. Lỗi phổ biến và dấu hiệu chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Metadata URL ban đầu trông hợp lệ nhưng app kết nối host khác | HTTP client follow 30x, DNS thay đổi, proxy rewrite | Tắt redirects, áp chính sách đích từng hop và tại egress; kiểm tra log network |
| Spring startup treo/lỗi khi IdP metadata không reachable | Nạp remote metadata trong lúc tạo `RelyingPartyRegistration`; timeout hoặc DNS/proxy | Thử nguồn đã duyệt, kiểm tra timeout, dùng bản classpath đã phê duyệt khi phù hợp |
| Lỗi “Could not resolve” hoặc metadata không parse được | URL trả HTML login/SSO page, 30x sang trang khác, XML sai | Không follow/parse HTML; dùng endpoint metadata chính thức hoặc file IdP tin cậy |
| Đổi metadata thành công nhưng SAMLResponse sai chữ ký | Certificate mismatch, IdP rollover, metadata bị thay, SP cache cũ | Kiểm tra certificate từ IdP và quy trình rollover, không bỏ signature check |
| Metadata URL được cấp qua form tenant rồi có request tới IP nội bộ | SSRF từ nhập URL, redirect, DNS hoặc XML parser | Tắt tính năng fetch tùy ý, chặn egress nội bộ, kiểm tra parser/tenant quyền |
| Metadata có XML signature nhưng không được đảm bảo nguồn | Signature verification không cấu hình trust anchor | Thiết lập credential xác minh độc lập hoặc phê duyệt file theo kênh quản trị |
| SP metadata trả URL HTTP hoặc host lạ | Proxy forwarded headers/`{baseUrl}` chưa chuẩn | Cấu hình canonical URL/proxy trust; kiểm tra XML thực |
| IdP báo metadata SP không tải được vì redirect | SP trả HTTP→HTTPS 301/302, IdP downloader không follow | Cấp URL HTTPS cuối cùng, tránh link chuyển tiếp |
| Certificate TLS của IdP không được Java tin | CA/truststore lỗi, hostname mismatch, cert hết hạn | Cài trust anchor hợp lệ, kiểm tra chain/SAN/clock, không disable TLS |
| Kết nối thất bại sau đổi IP/DNS hợp lệ | Egress allowlist cũ, chính sách IP pin chưa cập nhật | Cập nhật danh mục đích qua change review, không nới ra toàn Internet |
| Metadata refresh bị lặp quá nhiều | Scheduler retry không giới hạn, chu kỳ cache sai | Giới hạn timeout/retry, backoff và alert; bảo vệ IdP khỏi lưu lượng bất thường |

**Chuỗi tự kiểm tra:**

```text
1. Metadata đang được TẢI từ IdP hay được SP CÔNG BỐ?
2. Nguồn URL do ai nhập, ai được sửa và ai phê duyệt?
3. URL có khớp scheme/host/port/path/query trong allowlist?
4. HTTP client có tự theo 30x hoặc dùng proxy/redirect ngoài chính sách?
5. DNS và kết nối thực tế có thể chạm loopback/private/link-local?
6. Body có bị giới hạn size/time và parse XML an toàn?
7. EntityID, signing cert và metadata signature đã xác minh với trust độc lập?
8. Bản metadata mới có thay quyền tin cậy, endpoint hoặc cert không?
9. SAML login, issuer/audience/ACS và metadata SP thực tế có vẫn khớp?
```

## 12. Checklist trước khi cho phép metadata refresh trong production

- [ ] Chỉ các partner/IdP đã phê duyệt mới có URL metadata active; người dùng thường không nhập URL để backend fetch.
- [ ] Endpoint HTTPS có host, port, path/query cố định; không chấp nhận userinfo/scheme/port/host tùy ý.
- [ ] HTTP client không theo 30x; timeout, kích thước body, retry và resource quota có giới hạn.
- [ ] DNS/egress policy chặn các kết nối bị cấm, cả IPv4/IPv6, proxy, loopback, private/link-local và cloud instance metadata.
- [ ] XML parser an toàn trước XXE/external entity, XML quá sâu/quá lớn; không truy cập tham chiếu URL không được duyệt.
- [ ] Kiểm tra entityID và loại metadata đúng IdP; certificate signing thay đổi được review hoặc theo cơ chế metadata signature trust anchor.
- [ ] Kết quả tải chưa được dùng làm `RelyingPartyRegistration` cho đến khi đạt policy và trạng thái phê duyệt.
- [ ] Refresh có version, audit, cảnh báo, cache/expiry/rollover, rollback và xử lý outage rõ ràng.
- [ ] `saml2Metadata` công bố SP metadata đúng canonical HTTPS host và đúng tenant, không lộ bí mật.
- [ ] Test từ chối redirect, URI giả mạo, DNS rebinding, XXE, XML sai issuer, certificate không tin cậy và metadata quá lớn.
- [ ] Incident playbook có cách đình chỉ một IdP/registration, ngừng nhận assertion và xử lý session đã tạo khi metadata bị đầu độc.

**Thông điệp cuối:** URL metadata là một phần của **quyền thiết lập quan hệ tin cậy**. Spring Security giúp parse SAML metadata và tạo registration, nhưng ứng dụng vẫn phải kiểm soát **ai được phép chọn nguồn metadata**, **đích HTTP client thật sự kết nối tới**, **redirect và XML**, và **khóa/chứng thư nào được xem là tin cậy**. Khi triển khai đúng, một đối tác chỉ có thể cập nhật metadata trong ranh giới đã thỏa thuận; không thể dùng tính năng cấu hình SSO để biến backend thành proxy tới mạng nội bộ.

## 13. Tài liệu đối chiếu

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — `RelyingPartyRegistrations.fromMetadataLocation`, `fromMetadata(InputStream)`, repository và các endpoint SAML.
- [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html) — parse IdP metadata, publish SP metadata, xác minh chữ ký metadata bằng verification credentials.
- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) — HTTP-Redirect Binding và metadata.
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — allowlist, HTTP redirects, DNS rebinding và defense in depth.
- [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html) — bảo vệ XML parser khỏi XXE.
- [MITRE CWE-918 — Server-Side Request Forgery](https://cwe.mitre.org/data/definitions/918.html) — định nghĩa và mô hình lỗ hổng SSRF.
