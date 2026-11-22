# Kiểm soát SSRF từ jwks_uri, metadata và URL do client cung cấp

## 1. Mục tiêu và phạm vi

Trong module `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`, Authorization Server có thể phải truy cập tài nguyên bên ngoài để lấy public key, đọc metadata, giải tham chiếu request object hoặc xử lý thông tin client. Khi URL đích đến từ client hoặc một nguồn chưa được tin cậy, thao tác truy cập đó tạo ra bề mặt tấn công SSRF.

**Server-Side Request Forgery (SSRF)** là kiểu tấn công khiến máy chủ gửi request đến địa chỉ do kẻ tấn công kiểm soát hoặc lựa chọn. Kẻ tấn công có thể lợi dụng quyền mạng của Authorization Server để dò dịch vụ nội bộ, truy cập cloud metadata endpoint, gọi API quản trị hoặc làm lộ dữ liệu từ các hệ thống vốn không truy cập được từ Internet.

Trong OAuth 2.0 và OpenID Connect, các URL đáng chú ý gồm `jwks_uri`, `request_uri`, `sector_identifier_uri` và URL metadata của OpenID Provider bên ngoài. Không phải mọi trường URL trong client metadata đều khiến Authorization Server tự gọi URL đó. Rủi ro chỉ xuất hiện khi một thành phần server-side thực sự dereference, tải nội dung, tạo preview hoặc proxy URL. Vì vậy, bài học bắt đầu từ việc xác định chính xác nơi ứng dụng thực hiện outbound request.

Mục tiêu sau bài học:

- Nhận diện các luồng fetch URL có thể tạo SSRF.
- Phân biệt URL dùng để điều hướng trình duyệt với URL được máy chủ tải về.
- Xác thực URL, DNS, địa chỉ IP, redirect và TLS trước khi truy cập.
- Giới hạn quyền outbound ở tầng ứng dụng và hạ tầng mạng.
- Thiết kế việc lấy JWKS/metadata an toàn trong Spring Authorization Server.
- Kiểm thử DNS rebinding, redirect, IPv4/IPv6, cloud metadata và các biến thể URL.

## 2. SSRF trong Authorization Server

### 2.1. Luồng tấn công cơ bản

Giả sử client đăng ký metadata sau:

```json
{
  "client_id": "example-client",
  "jwks_uri": "https://keys.example.net/jwks.json"
}
```

Khi Authorization Server cần xác minh chữ ký của client assertion hoặc một thông điệp ký bởi client, thành phần xác minh có thể tải JWK Set từ `jwks_uri`. Nếu client được phép thay URL bằng một địa chỉ tùy ý, kẻ tấn công có thể đăng ký:

```text
http://169.254.169.254/latest/meta-data/
```

Nếu server truy cập URL mà không kiểm soát đích, request có thể đi đến metadata service của cloud hoặc một dịch vụ nội bộ khác. Kẻ tấn công không cần kết nối trực tiếp đến mạng nội bộ; chính Authorization Server trở thành điểm trung gian.

```mermaid
flowchart TD
    A[Attacker đăng ký client với URL độc hại] --> B[Authorization Server lưu metadata]
    B --> C[Luồng xác minh cần tải JWKS hoặc metadata]
    C --> D[HTTP client gửi outbound request]
    D --> E{Đích đến có được kiểm soát?}
    E -- Không --> F[Dò mạng nội bộ hoặc cloud metadata]
    E -- Có --> G[Chỉ truy cập đích được phép]
```

SSRF có thể là blind SSRF: kẻ tấn công không đọc được response trực tiếp nhưng vẫn khiến server gọi endpoint nội bộ, gây thay đổi trạng thái, kích hoạt tác vụ hoặc tạo tín hiệu qua thời gian phản hồi và log.

### 2.2. Vì sao Authorization Server có quyền mạng đáng chú ý?

Authorization Server thường kết nối tới database, cache, KMS/HSM, secret manager, service discovery, hệ thống quản trị và các API nội bộ. Một request SSRF có thể thừa hưởng vị trí mạng và một phần quyền truy cập của workload này.

Rủi ro tăng khi:

- Workload có thể truy cập cloud instance metadata hoặc container control plane.
- HTTP client tự động theo redirect đến một host khác.
- Server chấp nhận URL từ dynamic client registration mà không có chính sách.
- DNS được phân giải nhiều lần, cho phép DNS rebinding.
- Request gửi kèm cookie, Authorization header hoặc credential mặc định.
- Response được trả về client hoặc ghi log mà không kiểm soát.
- Một endpoint fetch được gọi lặp lại với tần suất cao, gây DoS hoặc cạn connection.

SSRF không chỉ là vấn đề của HTTP. Các thư viện xử lý URL có thể hỗ trợ nhiều scheme hoặc protocol. Với luồng lấy metadata/JWKS, chỉ cho phép HTTPS và HTTP client được kiểm soát; không chuyển URL tùy ý cho các API hỗ trợ `file:`, `jar:`, `ftp:`, `gopher:` hoặc protocol khác.

## 3. Xác định các URL có thể tạo outbound request

### 3.1. `jwks_uri`

`jwks_uri` là URL mà một bên công bố để bên còn lại lấy JSON Web Key Set. Trong bối cảnh client authentication, Authorization Server có thể dùng URL này để lấy public key của client khi xác minh JWT client assertion hoặc thông điệp ký bởi client, tùy grant, cấu hình và phiên bản thư viện.

Đây là điểm cần kiểm soát kỹ vì:

- Giá trị có thể được khai báo trong client metadata hoặc dynamic client registration.
- Request có thể xảy ra trong luồng nhạy cảm như token endpoint.
- URL có thể được cache, refresh hoặc gọi lại khi `kid` chưa được tìm thấy.
- Một `jwks_uri` bị thay đổi có thể làm thay đổi nguồn khóa được tin cậy.

Không nhầm `jwks_uri` của client với JWKS endpoint của chính Authorization Server. JWKS của server thường được tạo từ `JWKSource`/key management của server và công bố qua metadata; URL của client là nguồn public key bên ngoài mà server có thể cần truy cập.

### 3.2. `request_uri`

OAuth 2.0 Request Parameter và OpenID Connect cho phép request object được truyền trực tiếp hoặc tham chiếu qua `request_uri`. Nếu Authorization Server hỗ trợ dereference request URI, nó sẽ tải nội dung từ URL đó. Khi URL do client hoặc người gọi authorization request cung cấp, đây là một nguồn SSRF tiềm năng.

Chính sách an toàn có thể yêu cầu Request Object truyền trực tiếp hoặc qua Pushed Authorization Requests (PAR), giới hạn `request_uri` theo allowlist và áp dụng cơ chế xác minh client trước khi dereference. Không fetch một URL tùy ý chỉ vì nó xuất hiện trong authorization request.

### 3.3. `sector_identifier_uri`

OpenID Connect sử dụng `sector_identifier_uri` trong một số trường hợp để lấy danh sách redirect URI phục vụ pairwise subject identifier. OpenID Provider có thể tải JSON từ URL này để kiểm tra các redirect URI liên quan.

Nếu Authorization Server thực hiện bước tải này, URL phải qua cùng chính sách outbound an toàn. Response cần được giới hạn kích thước, parse như JSON theo schema mong đợi và kiểm tra danh sách URI. Không cho phép parser hoặc xử lý nội dung dẫn đến truy cập URL thứ hai ngoài dự kiến.

### 3.4. Metadata của OpenID Provider và Identity Provider bên ngoài

Trong mô hình federation hoặc khi Authorization Server đóng vai trò relying party với một upstream OpenID Provider, ứng dụng có thể tải discovery document từ issuer đã cấu hình, sau đó sử dụng `jwks_uri`, `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint` hoặc `end_session_endpoint` trong metadata.

Thông thường issuer upstream phải đến từ cấu hình quản trị đáng tin cậy hoặc quy trình onboarding có kiểm soát. Nếu cho phép tenant hoặc người dùng nhập issuer URL tùy ý rồi server tự discovery, bước discovery và các URL endpoint được metadata trả về trở thành nguồn SSRF. Cần xác minh issuer chính xác và kiểm soát từng outbound destination trước khi dùng.

Không giả định mọi endpoint trong discovery document đều được Authorization Server gọi. Ví dụ, authorization endpoint thường được browser/client điều hướng đến; userinfo endpoint có thể do OIDC client gọi. Chỉ các URL được chính server thực sự gọi mới là outbound sink trực tiếp, nhưng các URL khác vẫn cần validation theo vai trò sử dụng và có thể trở thành rủi ro nếu có proxy, health check hoặc preview service.

### 3.5. URL khác trong client metadata

| Trường | Cách sử dụng thường gặp | SSRF khi nào? |
|---|---|---|
| `jwks_uri` | Server lấy public key của client | Có khi server dereference URL |
| `request_uri` | Server lấy Request Object theo tham chiếu | Có khi tính năng dereference được bật |
| `sector_identifier_uri` | Server lấy danh sách redirect URI cho pairwise subject | Có khi server tải tài liệu JSON |
| `issuer` | Định danh issuer; discovery có thể được khởi tạo từ issuer | Có khi server tự tải metadata từ URL này |
| `authorization_endpoint` | Client/browser điều hướng người dùng | Thường không phải server-side fetch trong luồng authorization redirect |
| `token_endpoint` | OAuth client gửi token request | Chỉ là SSRF nếu một thành phần server-side của hệ thống này tự gọi endpoint |
| `userinfo_endpoint` | OIDC client lấy user claims | Có nếu server đóng vai RP hoặc proxy gọi endpoint |
| `logo_uri`, `client_uri`, `policy_uri`, `tos_uri` | Hiển thị hoặc điều hướng người dùng | Có nếu server tạo preview, tải ảnh, kiểm tra URL hoặc proxy nội dung |
| `redirect_uris`, `post_logout_redirect_uris` | Trình duyệt được chuyển hướng về client | Không phải SSRF chỉ vì URL được lưu; nguy cơ chính là open redirect/redirect URI validation |

Điểm phân biệt này giúp tránh áp dụng nhầm biện pháp. `redirect_uri` cần kiểm tra khớp chính xác theo OAuth/OIDC và chính sách client; nó không nên được server tải về để “kiểm tra tồn tại”. Ngược lại, `jwks_uri` phải được bảo vệ như một outbound request nếu server sẽ dereference nó.

## 4. Nguyên tắc phòng thủ SSRF

Một thiết kế tốt có nhiều lớp. Không dựa vào một biểu thức kiểm tra URL đơn giản.

1. **Giảm số URL được fetch:** chỉ bật tính năng dereference thật sự cần thiết; ưu tiên cấu hình tĩnh hoặc allowlist.
2. **Xác minh URL trước khi dùng:** scheme, host, port, userinfo, fragment, định dạng và chính sách tên miền.
3. **Xác minh địa chỉ mạng:** từ chối địa chỉ loopback, private, link-local, multicast, reserved và dải nội bộ của hạ tầng.
4. **Bảo vệ DNS và kết nối:** ngăn DNS rebinding và bảo đảm kết nối đến đúng địa chỉ đã kiểm tra.
5. **Kiểm soát redirect:** tắt redirect tự động hoặc xác minh lại mọi hop.
6. **Giới hạn HTTP request:** timeout, response size, content type, concurrency, rate limit và số lần retry.
7. **Không gửi credential ngoài dự kiến:** không forward cookie, bearer token, client secret hoặc header từ inbound request.
8. **Giới hạn egress ở mạng:** chặn workload truy cập metadata endpoint và mạng nội bộ không cần thiết.
9. **Giám sát và kiểm thử:** ghi nhận metadata an toàn, cảnh báo đích bị chặn và kiểm thử biến thể URL/DNS.

Không có một kiểm tra đơn lẻ nào thay thế các lớp còn lại. URL hợp lệ về cú pháp vẫn có thể phân giải đến IP nội bộ; hostname công khai có thể redirect đến địa chỉ private; DNS an toàn tại thời điểm đăng ký có thể đổi trước lúc kết nối.

## 5. Xác thực URL trước khi fetch

### 5.1. Phân tích URI theo chuẩn

Không dùng kiểm tra chuỗi kiểu `startsWith("https://")` hoặc regex đơn giản. Parse bằng URI parser, sau đó kiểm tra từng thành phần:

- Chỉ chấp nhận scheme `https` cho các URL metadata/JWKS production.
- Host phải tồn tại và được chuẩn hóa theo quy tắc hostname/IDN.
- Từ chối userinfo như `https://user:pass@host/`.
- Từ chối fragment và các dạng URL không nằm trong profile được hỗ trợ.
- Chỉ chấp nhận port mặc định hoặc port được allowlist.
- Không cho phép IP literal trừ khi có chính sách riêng cho một đích đã xác định.
- Giới hạn độ dài URL và tên miền; từ chối hostname nội bộ theo quy ước của môi trường.

Ví dụ URL có thể đánh lừa kiểm tra chuỗi:

```text
https://trusted.example@127.0.0.1/admin
https://trusted.example.evil.invalid/jwks
https://trusted.example:443@169.254.169.254/latest/meta-data/
http://127.1/
http://2130706433/
http://[::1]/
```

Trong URL đầu tiên, `trusted.example` là userinfo, còn host thực tế là `127.0.0.1`. Các dạng địa chỉ IPv4 rút gọn/số nguyên và IPv6 có thể né được bộ lọc chỉ tìm chuỗi `127.0.0.1`. Hãy dùng parser và thư viện kiểm tra địa chỉ đã được duy trì, không tự viết bộ chuẩn hóa IP bằng regex.

### 5.2. Allowlist theo hostname và port

Nếu chỉ có một số client hoặc issuer đã biết, allowlist hostname cụ thể là lựa chọn tốt nhất. Ví dụ, chỉ chấp nhận `keys.partner.example` trên cổng 443 cho một client đã được phê duyệt.

Allowlist cần so sánh hostname đã canonicalize, ranh giới domain chính xác và port. Không dùng phép so sánh hậu tố ngây thơ như `host.endsWith("partner.example")`, vì `notpartner.example` hoặc `partner.example.attacker.invalid` có thể bị chấp nhận sai nếu logic không kiểm tra ranh giới nhãn DNS.

Với dynamic registration công khai, allowlist cố định có thể không khả thi. Khi đó phải dùng chính sách egress proxy/firewall, chặn dải IP không công khai và kiểm soát DNS/redirect tại thời điểm kết nối. Việc đăng ký client thành công không có nghĩa URL của client đã trở thành đáng tin cậy.

### 5.3. Chặn IP không công khai và địa chỉ nhạy cảm

Sau khi phân giải hostname, kiểm tra mọi địa chỉ A và AAAA. Từ chối các địa chỉ không phải global unicast theo chính sách mạng, gồm tối thiểu:

| Nhóm địa chỉ | Ví dụ/dải thường cần chặn |
|---|---|
| IPv4 loopback | `127.0.0.0/8` |
| IPv4 private | `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` |
| IPv4 link-local | `169.254.0.0/16`, gồm cloud metadata thường gặp |
| IPv4 shared address | `100.64.0.0/10` |
| IPv4 unspecified/reserved/multicast | `0.0.0.0/8`, `224.0.0.0/4`, `240.0.0.0/4` và các dải đặc biệt khác |
| IPv6 loopback/unspecified | `::1/128`, `::/128` |
| IPv6 unique local | `fc00::/7` |
| IPv6 link-local/multicast | `fe80::/10`, `ff00::/8` |
| IPv4-mapped IPv6 | Địa chỉ IPv4 nhúng trong IPv6, cần kiểm tra địa chỉ IPv4 bên trong |

Danh sách trên chỉ là ví dụ các dải cần chú ý, không phải danh sách đầy đủ. Nên dùng thư viện hoặc chính sách dựa trên registry địa chỉ đặc biệt của IANA và bổ sung các CIDR nội bộ riêng của tổ chức. Cũng cần xét NAT64, service mesh, Kubernetes service CIDR, VPN và các dải mạng cloud riêng.

Chặn riêng cloud metadata endpoint và các dải link-local ở tầng network. Các địa chỉ metadata có thể khác nhau theo cloud/platform; không chỉ dựa vào một IP duy nhất.

Nếu một hostname trả về nhiều IP, không chọn ngẫu nhiên một địa chỉ hợp lệ rồi bỏ qua các địa chỉ bị cấm. Chính sách an toàn là từ chối hostname khi bất kỳ kết quả phân giải nào không đáp ứng chính sách, hoặc chỉ kết nối qua proxy có khả năng áp dụng policy cho địa chỉ thực tế.

## 6. DNS rebinding và kiểm soát kết nối thực tế

### 6.1. DNS rebinding

DNS rebinding xảy ra khi hostname ban đầu phân giải thành địa chỉ công khai để vượt qua bước kiểm tra, nhưng ở lần phân giải sau lại trả về địa chỉ nội bộ. Nếu ứng dụng kiểm tra DNS rồi để HTTP client tự phân giải lại, hai thao tác có thể sử dụng hai kết quả khác nhau.

Ví dụ:

1. Khi đăng ký, `attacker.example` phân giải thành IP công khai.
2. URL vượt qua kiểm tra.
3. Khi Authorization Server thực hiện fetch, DNS trả về `127.0.0.1` hoặc IP metadata.
4. HTTP client kết nối đến đích nội bộ.

Do đó, kiểm tra DNS một lần tại thời điểm đăng ký là chưa đủ.

### 6.2. Gắn kiểm tra với địa chỉ được kết nối

Biện pháp mạnh cần bảo đảm địa chỉ IP thực tế được dùng cho socket chính là địa chỉ đã được kiểm tra. Có thể thực hiện qua:

- Egress proxy có khả năng tự phân giải DNS, áp dụng IP policy và kết nối đến địa chỉ đã được xác minh.
- HTTP client có resolver/transport tùy chỉnh, ghim kết quả phân giải an toàn vào kết nối, đồng thời vẫn xác minh TLS hostname với hostname gốc.
- Network policy/firewall chặn các dải private, loopback, link-local, metadata và mạng quản trị ngay cả khi ứng dụng bị bypass.

Không chỉ gọi `InetAddress.getAllByName()` để kiểm tra rồi tạo request bằng HTTP client mặc định. Cách đó vẫn có khoảng trống time-of-check/time-of-use nếu HTTP client phân giải lại hostname. Nếu không thể kiểm soát DNS-to-connect một cách chắc chắn, hãy đặt outbound fetch sau egress proxy được bảo vệ.

### 6.3. TLS hostname verification

Khi kết nối đến IP đã pin, TLS vẫn phải xác minh certificate cho hostname trong URL. Không tắt hostname verification, không dùng trust-all certificate manager và không bỏ qua lỗi certificate để “khắc phục” lỗi kết nối.

Nếu dùng proxy, phải xác định rõ TLS được kết thúc ở proxy hay ở ứng dụng. Proxy không được làm mất xác minh danh tính đích hoặc cho phép client tùy ý tunnel đến mạng nội bộ.

## 7. Redirect, HTTP header và nội dung response

### 7.1. Redirect

Một URL công khai có thể trả `301`, `302`, `307` hoặc `308` trỏ đến `http://127.0.0.1`, địa chỉ metadata hoặc hostname khác. Nếu HTTP client tự theo redirect, kiểm tra URL ban đầu không bảo vệ được request cuối.

Đối với JWKS và metadata, lựa chọn đơn giản nhất thường là tắt redirect. Nếu giao thức hoặc hạ tầng bắt buộc redirect, mỗi `Location` phải được parse và xác minh lại đầy đủ: scheme, host, port, DNS, IP, TLS và chính sách egress. Giới hạn số hop và phát hiện vòng lặp. Không chuyển Authorization header hoặc credential qua redirect sang host khác.

### 7.2. Không gửi credential ngoài dự kiến

Outbound request để tải public JWKS/metadata thông thường không cần cookie của người dùng, session cookie, bearer token của inbound request hay database credential. Tạo HTTP client chuyên dụng, không chia sẻ cookie jar, không kế thừa header từ request hiện tại và không bật ambient authentication.

Nếu một giao thức cần xác thực với nguồn metadata, credential phải được gắn với một host đã được quản trị tin cậy và không được forward theo redirect. Tránh dùng chung HTTP client đã cấu hình credential nội bộ cho cả URL do client cung cấp.

### 7.3. Giới hạn response

Một endpoint độc hại có thể trả body rất lớn, JSON lồng sâu, số lượng JWK quá lớn hoặc response không kết thúc. Cần giới hạn:

- Connect timeout, response timeout và tổng thời gian xử lý.
- Số byte tối đa đọc từ response, kể cả khi dùng streaming.
- Content-Type và định dạng được hỗ trợ.
- Độ sâu JSON, số phần tử, số lượng key và kích thước từng trường.
- Số kết nối đồng thời, số lần retry và tần suất refresh theo client.
- Tỷ lệ lỗi và thời gian cache để tránh fetch liên tục.

Với JWKS, chỉ chấp nhận cấu trúc JWK Set đúng chuẩn, key type và thuật toán được phép. Không dùng `kid`, `jku` hoặc `x5u` trong một JWT chưa tin cậy để tự động mở thêm URL fetch khác nếu chưa có chính sách rõ ràng. `kid` là giá trị chọn key trong tập đã tin cậy, không phải URL.

## 8. Thiết kế fetch an toàn trong Spring

### 8.1. Tập trung outbound fetch vào một thành phần

Không để từng provider hoặc controller tự tạo `RestTemplate`, `RestClient`, `WebClient` rồi gọi URL trực tiếp. Tạo một service có trách nhiệm rõ ràng, ví dụ `SafeMetadataFetcher`, để mọi luồng dereference URL đi qua cùng policy.

Hợp đồng khái niệm:

```java
public interface SafeMetadataFetcher {

    byte[] fetchJwks(URI jwksUri, ClientId clientId);

    byte[] fetchSectorIdentifier(URI sectorIdentifierUri, ClientId clientId);

    byte[] fetchRequestObject(URI requestUri, ClientId clientId);
}
```

Đây là API minh họa, không phải interface có sẵn của Spring Authorization Server. Trong triển khai thực tế, nên trả kiểu dữ liệu đã parse/validate thay vì `byte[]` tùy tiện, để caller không quên giới hạn kích thước hoặc kiểm tra schema.

Service nên phối hợp các bước:

1. Lấy metadata đã lưu của đúng client và xác định tính năng nào được phép fetch.
2. Parse URI và áp dụng allowlist/policy.
3. Thực hiện resolve/egress validation gắn với kết nối thực tế.
4. Gửi request bằng HTTP client chuyên dụng, redirect tắt.
5. Giới hạn thời gian, response size và content type.
6. Parse theo schema mong đợi và kiểm tra nội dung.
7. Cache theo client/URL/version với TTL có giới hạn.
8. Trả lỗi an toàn nếu policy hoặc fetch thất bại.

### 8.2. Cấu hình HTTP client không tự theo redirect

Với Java `HttpClient`, có thể tắt redirect tự động và đặt timeout ở client/request. Ví dụ minh họa:

```java
HttpClient httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder(validatedUri)
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/jwk-set+json, application/json")
        .GET()
        .build();
```

Đoạn mã chỉ minh họa timeout và redirect policy. Nó **không tự giải quyết DNS rebinding, IP filtering, giới hạn body, egress firewall hay schema validation**. Không đưa URL chưa qua policy vào `validatedUri`. Cần dùng transport/proxy có thể thực thi kiểm soát địa chỉ đích thực tế; nếu dùng `BodyHandlers.ofInputStream()`, phải tự đọc có giới hạn byte và đóng stream đúng cách.

### 8.3. Tích hợp với Spring Authorization Server

Trong Spring Authorization Server, `RegisteredClientRepository` lưu metadata client. Tùy phiên bản và luồng xác thực, `RegisteredClient.getClientSettings().getJwkSetUrl()` có thể được thành phần xác minh client assertion sử dụng để lấy public key từ xa. Một số cấu hình dùng `JwtClientAssertionDecoderFactory` để tạo decoder phù hợp cho client.

Khi bật `private_key_jwt` hoặc tính năng cần public key từ `jwks_uri`, cần xác minh implementation của đúng phiên bản thư viện để biết chính xác lúc nào JWK Set được tải, cache ra sao và cách thay HTTP transport/resolver. Không giả định rằng `RegisteredClientRepository` tự kiểm tra SSRF chỉ vì metadata đã được lưu hợp lệ.

Các điểm cần kiểm soát:

- Validate `jwks_uri` ở thời điểm đăng ký hoặc cập nhật client.
- Validate lại tại thời điểm fetch; metadata có thể cũ hoặc DNS có thể thay đổi.
- Cấu hình JWK resolver/HTTP transport qua một policy tập trung.
- Không cho phép client thay `jwks_uri` tùy ý mà không có quy trình xác minh và audit.
- Giữ nguyên xác minh chữ ký, `iss`, `sub`, `aud`, `exp`, `iat`, `jti` và các kiểm tra client authentication khác.
- Xử lý lỗi fetch theo hướng fail-closed: không chấp nhận assertion khi không lấy được khóa cần thiết.

`JWKSource` của Authorization Server dùng để quản lý khóa ký của chính server là một mối quan tâm khác. Không thay thế nó bằng nguồn URL do client cung cấp và không cho phép `jku` trong JWT chưa xác minh quyết định nguồn khóa tin cậy.

### 8.4. Discovery metadata và issuer upstream

Nếu ứng dụng hỗ trợ liên kết upstream IdP, cấu hình issuer nên đến từ quản trị viên hoặc quy trình onboarding tenant được kiểm soát. Discovery client cần dùng cùng outbound fetch policy. Sau khi tải metadata, kiểm tra `issuer` trong document khớp chính xác issuer mong đợi; sau đó kiểm tra các URL endpoint mà thành phần server sẽ gọi.

Không tự động tin tất cả URL trong metadata chỉ vì JSON được tải qua HTTPS. HTTPS chứng minh kết nối đến hostname đó, không chứng minh hostname đó là issuer được phép cho tenant. Cần xác minh issuer, tenant binding, signing key và endpoint policy.

### 8.5. Không dùng URL client làm nguồn cấu hình tùy tiện

Không chuyển URL từ registration request trực tiếp vào:

- `RestTemplate.getForObject(url, ...)` hoặc `RestClient.get().uri(url)`.
- `WebClient.get().uri(url)` mà không qua policy.
- HTTP client dùng chung có cookie hoặc Authorization header.
- Image proxy, link preview, favicon fetcher, health checker hoặc webhook tester.
- XML/JSON parser có khả năng tự tải external resource.

Các thành phần phụ như giao diện quản trị hoặc dịch vụ preview cũng phải dùng chính sách outbound riêng. Không cho phép admin UI tạo preview của `logo_uri` hoặc `client_uri` bằng server fetch tùy ý.

## 9. Cache, rate limit và khả năng phục hồi

JWKS và metadata thường không cần tải lại ở mọi request. Cache hợp lý giúp giảm SSRF surface, giảm tải endpoint đối tác và hạn chế DoS.

- Cache theo client/issuer và URL đã xác minh; không để một client ghi đè cache của client khác.
- Tôn trọng `Cache-Control` trong giới hạn policy của server; áp dụng TTL tối thiểu/tối đa phù hợp.
- Giới hạn refresh đồng thời cho cùng một client/URL bằng single-flight hoặc lock phân tán.
- Chỉ refresh khi hết TTL, khi cần `kid` mới hoặc theo lịch có giới hạn; tránh một token request gây nhiều fetch.
- Rate limit theo client, tenant, host đích và địa chỉ nguồn.
- Dùng circuit breaker/backoff để endpoint lỗi không khiến server retry liên tục.
- Có chính sách stale key có kiểm soát; không tiếp tục tin key đã bị thu hồi chỉ vì upstream không truy cập được.
- Khi URL hoặc metadata bị thay đổi, vô hiệu cache cũ theo quy trình có audit.

Nếu fetch thất bại, không dùng một key bất kỳ trong cache hoặc bỏ qua xác minh chữ ký để duy trì availability. Chính sách fallback phải phân biệt lỗi tạm thời với key rotation và tình huống có dấu hiệu xâm phạm.

## 10. Phòng thủ ở tầng hạ tầng mạng

Application validation có thể có lỗi. Network egress control là lớp phòng thủ độc lập và rất quan trọng.

- Chỉ cho phép Authorization Server kết nối đến các dịch vụ outbound cần thiết.
- Chặn truy cập đến loopback, private CIDR, link-local, metadata IP, Kubernetes control plane, database subnet và management subnet.
- Dùng egress proxy để kiểm tra hostname, DNS resolution, IP đích, port và redirect.
- Tách workload Authorization Server khỏi workload quản trị và database bằng network segmentation.
- Không cấp quyền cloud IAM rộng cho process chỉ cần tải public JWKS.
- Nếu nền tảng hỗ trợ, yêu cầu IMDSv2 hoặc cơ chế tương đương, giới hạn hop count và chặn metadata endpoint từ workload không cần truy cập.
- Kiểm tra IPv4, IPv6, NAT64, service mesh và proxy bypass; không chỉ cấu hình một firewall rule cho IPv4.

Network policy cần được kiểm thử từ đúng container/pod/process chạy Authorization Server. Kiểm thử từ máy developer không chứng minh rằng egress policy của workload production đã có hiệu lực.

## 11. Xử lý lỗi và thông tin trả về

Không tiết lộ chi tiết nội bộ khi URL bị từ chối hoặc fetch thất bại. API quản trị có thể trả lỗi như “URL metadata không đáp ứng chính sách truy cập” kèm correlation ID. Không trả stack trace, IP nội bộ, response body từ endpoint bị gọi hoặc credential.

Tại token endpoint, nếu không lấy được JWK cần thiết để xác minh client assertion, từ chối xác thực theo lỗi OAuth phù hợp. Không coi lỗi DNS, timeout hoặc HTTP 500 từ `jwks_uri` là lý do để bỏ qua chữ ký.

Log an toàn nên ghi:

- Client ID đã được xác minh hoặc mã tham chiếu nội bộ.
- Loại URL (`JWKS`, `REQUEST_OBJECT`, `SECTOR_IDENTIFIER`, `DISCOVERY`).
- Host đã chuẩn hóa hoặc mã policy, không ghi query string có thể chứa secret.
- Lý do bị chặn (private IP, scheme, port, redirect, timeout, response size).
- Thời gian, correlation ID và kết quả.

Không log URL đầy đủ nếu query string có thể chứa token hoặc chữ ký. Không log response body, authorization header hoặc cookie. Metric nên dùng label có cardinality thấp, không dùng URL tùy ý làm label.

## 12. Kiểm thử SSRF

Kiểm thử cần chạy trong môi trường cô lập, có endpoint giả lập và không truy cập dịch vụ metadata production. Dùng test server nội bộ để xác nhận ứng dụng từ chối trước khi request đến đích.

| Kịch bản | Kết quả mong đợi |
|---|---|
| `jwks_uri` dùng HTTPS đến hostname allowlist | Fetch thành công và parse JWKS hợp lệ |
| `jwks_uri` dùng `http://` | Bị từ chối theo policy HTTPS |
| URL chứa userinfo hoặc fragment | Bị từ chối |
| URL trỏ loopback/private/link-local | Bị từ chối |
| URL trỏ cloud metadata IP | Bị chặn ở ứng dụng và network egress |
| Hostname phân giải ra cả public và private IP | Bị từ chối hoặc bị egress proxy chặn |
| DNS đổi từ public sang private sau registration | Kết nối thực tế vẫn bị chặn |
| Public URL redirect sang private IP | Redirect bị tắt hoặc hop tiếp theo bị từ chối |
| IPv4 dạng số nguyên/rút gọn hoặc IPv6 loopback | Bị chuẩn hóa và từ chối |
| URL dùng port không được phép | Bị từ chối |
| Endpoint trả body quá lớn hoặc không kết thúc | Dừng đọc theo giới hạn và timeout |
| Endpoint trả sai content type hoặc JSON sai schema | Bị từ chối |
| JWKS có quá nhiều key hoặc key không được hỗ trợ | Bị từ chối theo giới hạn parser/policy |
| Client gửi `jku`/`x5u` tùy ý trong JWT | Không được dùng để tạo outbound fetch ngoài policy |
| Nhiều token request đồng thời cần cùng JWKS | Cache/single-flight ngăn fetch bùng nổ |
| Upstream JWKS tạm thời lỗi | Không bỏ qua xác minh chữ ký; xử lý lỗi theo policy |
| Outbound proxy không khả dụng | Fail-closed với thao tác cần fetch |
| `redirect_uri` trỏ đến địa chỉ nội bộ | Được xử lý bằng redirect URI validation; server không fetch URL để kiểm tra |

Nên có integration test cho:

- DNS resolver giả có thể trả các tập A/AAAA khác nhau theo thời điểm.
- HTTP server giả trả redirect đến loopback hoặc link-local.
- Response body vượt giới hạn và response chậm.
- Kiểm tra request không mang Authorization/Cookie từ inbound request.
- Cache isolation giữa hai client có cùng `kid` nhưng khác JWKS.
- Việc thay `jwks_uri` yêu cầu quyền quản trị, audit và vô hiệu cache cũ.

Không dựa vào unit test của hàm `validateUrl` để kết luận SSRF đã được khắc phục. Cần kiểm tra request thực tế và policy ở network egress.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Rủi ro | Cách khắc phục |
|---|---|---|
| Tin `jwks_uri` vì client đã đăng ký | Client đăng ký vẫn có thể độc hại hoặc bị chiếm quyền | Validate URL và egress tại thời điểm fetch |
| Chỉ kiểm tra hostname khi đăng ký | DNS có thể thay đổi trước khi kết nối | Bảo vệ DNS-to-connect và network egress |
| Chỉ chặn `127.0.0.1` bằng regex | Bỏ sót IP rút gọn, IPv6 và dải private khác | Dùng parser và IP policy đầy đủ |
| Cho HTTP client tự theo redirect | URL công khai chuyển hướng vào mạng nội bộ | Tắt redirect hoặc xác minh lại từng hop |
| Chỉ dùng `InetAddress` trước khi fetch | HTTP client có thể phân giải lại DNS | Pin địa chỉ thực tế hoặc dùng egress proxy |
| Dùng HTTP client có sẵn credential nội bộ | SSRF có thể gửi credential đến host tấn công | Client riêng, không ambient auth/cookie |
| Không giới hạn response | DoS qua body lớn, JSON sâu hoặc slow response | Timeout, byte limit và parser limit |
| Fetch JWKS ở mọi token request | DoS và tăng cơ hội khai thác | Cache, single-flight và rate limit |
| Tin mọi URL trong discovery metadata | Metadata có thể trỏ đến endpoint nội bộ hoặc sai issuer | Xác minh issuer và endpoint policy |
| Fetch `redirect_uri` để kiểm tra | SSRF và sai mô hình OAuth redirect | So khớp URI theo quy tắc OAuth; không fetch |
| Ghi URL đầy đủ vào log | Rò rỉ query token/chữ ký và dữ liệu nội bộ | Log host/policy code đã chuẩn hóa |
| Chỉ dựa vào application firewall | Lỗi code có thể bypass policy | Bổ sung network egress deny-by-default |

## 14. Checklist triển khai

- [ ] Đã kiểm kê tất cả điểm server-side fetch URL trong Authorization Server và thành phần phụ trợ.
- [ ] Đã phân biệt URL điều hướng trình duyệt với URL server thực sự dereference.
- [ ] `jwks_uri`, `request_uri`, `sector_identifier_uri` và issuer discovery có policy riêng.
- [ ] Chỉ bật tính năng fetch URL khi có yêu cầu nghiệp vụ rõ ràng.
- [ ] URI được parse chuẩn; scheme, host, port, userinfo và fragment được kiểm tra.
- [ ] Có allowlist hostname khi khả thi; nếu không, có IP policy và egress proxy.
- [ ] Chặn loopback, private, link-local, metadata, reserved và CIDR nội bộ cho IPv4/IPv6.
- [ ] DNS validation gắn với địa chỉ kết nối thực tế; đã phòng DNS rebinding.
- [ ] Redirect bị tắt hoặc mỗi hop được xác minh lại toàn bộ.
- [ ] TLS certificate và hostname verification luôn được bật.
- [ ] HTTP client không forward cookie, bearer token hoặc credential ngoài dự kiến.
- [ ] Có connect/response timeout, response byte limit, parser limit và concurrency limit.
- [ ] JWKS/metadata được cache, rate limit và refresh có kiểm soát.
- [ ] Không dùng `jku`/`x5u` từ JWT chưa xác minh để mở URL fetch tùy ý.
- [ ] Network egress chặn metadata endpoint và subnet quản trị không cần thiết.
- [ ] Log/metric không chứa URL query nhạy cảm, token, cookie hoặc response body.
- [ ] Có integration test cho redirect, DNS rebinding, IP variants, IPv6 và body lớn.
- [ ] Thư viện Spring/Spring Security/Spring Authorization Server đúng phiên bản đã được rà soát về hành vi fetch/cache.

## 15. Kết luận

SSRF trong Authorization Server thường xuất hiện khi server dereference URL do client hoặc metadata bên ngoài cung cấp. `jwks_uri`, `request_uri`, `sector_identifier_uri` và issuer discovery là các điểm cần xem xét theo đúng tính năng được bật. Phòng thủ phải kết hợp xác thực URI, kiểm tra IP, chống DNS rebinding, kiểm soát redirect, giới hạn HTTP response và network egress. Trong Spring Authorization Server, cần rà soát cách phiên bản đang dùng lấy JWK Set từ `RegisteredClient` và tích hợp mọi outbound fetch qua policy tập trung. Đăng ký client hoặc tải metadata thành công không tự biến URL thành nguồn đáng tin cậy; chỉ chấp nhận dữ liệu sau khi xác minh cả nguồn, kết nối và nội dung.
