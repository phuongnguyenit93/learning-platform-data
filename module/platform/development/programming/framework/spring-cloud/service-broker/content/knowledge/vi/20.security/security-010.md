# Kiểm soát dashboard_url, route_service_url và địa chỉ đầu vào

Service broker thường phải trao đổi URL và địa chỉ mạng với nền tảng cloud. Khi provision service instance, broker có thể trả dashboard_url để người dùng mở trang quản trị dịch vụ. Khi tạo route binding, broker có thể trả route_service_url để nền tảng định tuyến request qua route service. Request từ platform hoặc consumer cũng có thể mang hostname, route, endpoint hay địa chỉ IP làm tham số cấu hình.

Những giá trị này ảnh hưởng trực tiếp đến ranh giới mạng. Một URL do caller kiểm soát có thể khiến broker truy cập dịch vụ nội bộ, cloud metadata endpoint hoặc một host ngoài dự kiến (SSRF). Một URL broker trả ra nhưng được ghép từ input không tin cậy có thể tạo open redirect, trỏ người dùng đến domain giả hoặc làm lộ token. Vì vậy, module SPRING_CLOUD_SERVICE_BROKER cần kiểm soát cả nguồn dữ liệu, cách chuẩn hóa, policy cho phép, cách kết nối và nội dung response.

## 1. Phân biệt URL đầu ra và địa chỉ đầu vào

Không phải mọi trường URL trong OSB có cùng nguồn hoặc cùng mục đích:

| Giá trị | Hướng dữ liệu | Mục đích | Rủi ro chính |
|---|---|---|---|
| dashboard_url | Broker trả cho platform trong response provision | Mở dashboard quản trị service instance | Open redirect, host giả, lộ token hoặc thông tin tenant |
| route_service_url | Broker trả trong response route service binding theo contract tương ứng | Cho platform/router biết endpoint route service | Endpoint giả, endpoint không thể truy cập, TLS/auth sai, SSRF nếu broker tự kiểm tra URL |
| bind_resource.route | Platform gửi trong request route binding | Route mà platform muốn gắn với route service | Route giả, host/port không hợp lệ, dữ liệu tenant khác |
| Endpoint/hostname trong parameters | Consumer hoặc platform gửi trong request | Cấu hình đích mà service broker hoặc backend có thể kết nối | SSRF, truy cập mạng nội bộ, DNS rebinding |
| URL do broker cấu hình | Cấu hình triển khai đáng tin cậy | Base URL cho dashboard hoặc route service | Sai cấu hình, domain takeover, certificate không hợp lệ |

dashboard_url và route_service_url thường là URL do broker công bố. Chúng không nên được lấy nguyên văn từ một trường tùy ý trong request. Ngược lại, route hoặc endpoint do platform/consumer gửi là dữ liệu đầu vào; phải xác minh trước khi dùng làm đích kết nối hoặc đưa vào backend configuration.

Chỉ parse một URL không có nghĩa URL đó an toàn. URL có thể hợp lệ về cú pháp nhưng vẫn trỏ tới loopback, private network, link-local, metadata service, host của tenant khác hoặc một domain giả mạo.

## 2. Rủi ro khi xử lý URL và địa chỉ

### Server-Side Request Forgery (SSRF)

SSRF xảy ra khi broker hoặc thành phần backend lấy địa chỉ do caller kiểm soát rồi chủ động gửi HTTP request hoặc mở kết nối tới địa chỉ đó. Kẻ tấn công có thể thử:

- http://127.0.0.1:8080/admin để truy cập dịch vụ chỉ lắng nghe trên loopback.
- Địa chỉ link-local của cloud metadata service.
- Địa chỉ private trong VPC hoặc mạng Kubernetes mà broker có quyền truy cập.
- Một hostname công khai có DNS thay đổi sau khi broker kiểm tra.
- URL redirect từ một host được phép sang host nội bộ.

Không phải cứ nhận một hostname là đã có SSRF. Rủi ro xuất hiện khi broker hoặc một thành phần mà broker điều khiển thực hiện kết nối tới hostname đó. Tuy nhiên, địa chỉ vẫn cần validation nếu được lưu, truyền cho worker, ghi vào cấu hình backend hoặc trả cho platform.

### Open redirect và URL giả mạo

Nếu dashboard_url được ghép từ tham số do caller gửi, kẻ tấn công có thể khiến platform hiển thị link dẫn tới domain giả. Người dùng có thể tin rằng mình đang mở dashboard của broker nhưng thực tế bị chuyển sang website phishing.

Một dạng lỗi thường gặp là nhận returnUrl, redirect, host hoặc domain từ request rồi dùng trực tiếp trong URL response. Chỉ kiểm tra chuỗi bắt đầu bằng https:// là chưa đủ; domain vẫn có thể không thuộc broker.

### Rò rỉ thông tin qua URL

URL có thể bị ghi vào access log, browser history, reverse proxy, trace hoặc referrer. Không đặt password, API key, access token hoặc secret trong query string hay fragment của dashboard_url/route_service_url. Nếu cần token truy cập dashboard, ưu tiên luồng xác thực riêng hoặc signed link có phạm vi và thời hạn ngắn theo policy.

### DNS rebinding và redirect chain

Một hostname có thể phân giải thành IP công khai khi kiểm tra, sau đó phân giải thành IP nội bộ khi client thực hiện kết nối. Đây là DNS rebinding. Tương tự, một URL ban đầu trỏ đến host được cho phép có thể trả redirect đến host bị cấm. Chỉ kiểm tra hostname ban đầu không đủ nếu broker theo redirect hoặc phân giải DNS lại khi kết nối.

## 3. Chính sách cho dashboard_url

dashboard_url là đường dẫn người dùng hoặc platform dùng để mở giao diện dashboard của một service instance. Broker nên tạo URL từ cấu hình tin cậy:

- Base URL được cấu hình bởi operator, ví dụ https://console.example.com.
- Path được tạo từ route cố định của ứng dụng.
- Instance identifier được encode như một path segment.
- Tenant context được lấy từ state đã xác minh, không lấy từ query string tùy ý.
- Không chèn credentials hoặc token lâu dài vào URL.

Ví dụ tạo URL:

~~~java
URI dashboardUri = UriComponentsBuilder
        .fromUriString(dashboardBaseUrl)
        .pathSegment("instances", instanceId, "overview")
        .build()
        .encode()
        .toUri();
~~~

dashboardBaseUrl phải đến từ cấu hình triển khai được kiểm soát, không phải từ request provision. instanceId phải được xác thực theo định dạng và encode đúng như một path segment; không nối chuỗi thủ công vì giá trị chứa /, ?, # hoặc ký tự điều khiển có thể thay đổi cấu trúc URL.

Trước khi trả URL, kiểm tra:

1. Scheme là https trong môi trường production, trừ trường hợp triển khai nội bộ có policy rõ ràng.
2. Host thuộc allowlist domain dashboard đã cấu hình.
3. Không có user-info dạng user:password@host.
4. Port là port được cho phép.
5. Path nằm trong namespace dashboard dự kiến.
6. Query chỉ chứa tham số không nhạy cảm và đã được kiểm soát.
7. Không có fragment hoặc redirect parameter do caller tùy ý đặt.

Nếu dashboard dùng domain riêng theo tenant, ánh xạ tenant sang domain phải được lấy từ registry/configuration tin cậy. Không lấy tenantDomain trong parameters để tạo host. Nếu có custom domain, cần xác minh ownership và trạng thái domain trước khi đưa nó vào response.

Không dùng URL rút gọn hoặc redirector công cộng làm lớp trung gian cho dashboard. Nếu dashboard cần chuyển tiếp đến trang khác, đích chuyển hướng phải được xác định ở server từ instance/tenant state và vẫn áp dụng allowlist.

## 4. Chính sách cho route_service_url

route_service_url là endpoint route service broker công bố trong response binding tương ứng để nền tảng/router biết nơi chuyển request. Nó phải trỏ đến route service do broker quản lý hoặc một endpoint đã được operator phê duyệt.

Các yêu cầu quan trọng:

- Host và port đến từ cấu hình deployment hoặc service registry tin cậy.
- Endpoint có thể được platform/router truy cập theo topology mạng đã thiết kế.
- Dùng HTTPS/TLS; certificate phải hợp lệ với hostname mà platform kết nối.
- Xác thực giữa router/platform và route service bằng cơ chế được hỗ trợ, không dựa vào một URL bí mật duy nhất.
- Không đưa token dài hạn, password hoặc private key vào query string.
- Không trả địa chỉ loopback hoặc hostname chỉ phân giải được trong container broker nếu router không thể truy cập.
- Không lấy URL từ parameters hoặc header do consumer gửi rồi trả nguyên vào response.

Route service thường nằm trong một mạng hoặc namespace khác với broker. Một endpoint hợp lệ từ góc nhìn process broker có thể không thể truy cập từ router; ngược lại, endpoint có thể truy cập từ router nhưng không nên được broker gọi trực tiếp. Cần xác định rõ thành phần nào là client của URL và kiểm tra reachability trong đúng network path.

Nếu route service chạy nhiều replica hoặc có ingress riêng, hãy công bố một stable service endpoint/load balancer thay vì pod IP hoặc địa chỉ tạm thời. Không trả địa chỉ IP nội bộ của một pod nếu platform cần endpoint ổn định.

## 5. Kiểm tra địa chỉ đầu vào

Địa chỉ đầu vào có thể là hostname, IP, URI hoặc route tùy theo service plan. Trước khi dùng, broker phải biết chính xác loại dữ liệu được chấp nhận. Tránh một field chung tên endpoint mà lúc thì chứa URL, lúc chứa hostname, lúc chứa host:port.

Một schema rõ ràng có thể tách:

| Field | Kiểu | Ví dụ | Kiểm tra |
|---|---|---|---|
| endpointHost | Hostname hoặc IP | db.customer.example | Host syntax, domain policy, IP/CIDR policy |
| endpointPort | Integer | 5432 | Trong phạm vi port hợp lệ và allowlist |
| endpointScheme | Enum | https | Chỉ nhận scheme được hỗ trợ |
| route | Route/hostname theo contract | orders.apps.example.net | Validate domain và quyền sở hữu route |
| callbackUrl | Absolute URI | https://hooks.example.net/events | URI policy, host allowlist và SSRF protection |

Không tự động chuyển một chuỗi không rõ định dạng thành URL bằng cách thêm https://. Việc này có thể làm một input sai schema trở thành đích kết nối hợp lệ ngoài dự kiến.

### Kiểm tra hostname

Hostname nên được chuẩn hóa trước khi so sánh:

- Bỏ dấu chấm cuối nếu policy coi FQDN có trailing dot và không có trailing dot là cùng hostname.
- Chuyển IDN sang ASCII bằng quy trình IDNA nhất quán trước khi so sánh allowlist.
- So sánh hostname theo quy tắc DNS không phân biệt hoa thường.
- Không dùng kiểm tra endsWith("example.com") đơn giản; evil-example.com hoặc example.com.attacker.test có thể vượt qua logic sai.
- Nếu cho phép subdomain, kiểm tra ranh giới label, ví dụ hostname bằng example.com hoặc kết thúc bằng .example.com.
- Từ chối wildcard hoặc ký tự điều khiển nếu schema không hỗ trợ chúng.

### Kiểm tra IP và port

Nếu input cho phép IP literal:

- Parse IPv4 và IPv6 bằng parser chuẩn, không dựa vào regex đơn giản.
- Kiểm tra CIDR theo policy của service/tenant.
- Xử lý IPv4-mapped IPv6 và dạng biểu diễn IPv6 khác nhau.
- Từ chối zone identifier IPv6 nếu không có use case được phê duyệt.
- Kiểm tra port theo allowlist của dịch vụ; không cho phép mọi port chỉ vì nằm trong khoảng 1–65535.
- Xem xét loopback, unspecified, link-local, multicast, broadcast, reserved và các dải private theo topology.

Không dùng duy nhất InetAddress.isSiteLocalAddress() làm SSRF defense. Cần policy IP/CIDR đầy đủ và kiểm soát egress ở network layer. Private IP không phải lúc nào cũng sai: service broker có thể hợp lệ khi kết nối database nội bộ trong VPC. Chỉ cho phép dải private cụ thể nếu service/tenant được ủy quyền, không mở toàn bộ private ranges một cách mặc định.

## 6. Chống SSRF khi broker phải kết nối đến địa chỉ đầu vào

Nếu broker thực hiện health check, webhook validation, import, proxy hoặc kết nối tới endpoint do caller cung cấp, áp dụng nhiều lớp bảo vệ:

1. **Schema validation:** chỉ nhận loại địa chỉ mà use case cần; từ chối URL có user-info hoặc scheme không hỗ trợ.
2. **Allowlist:** ưu tiên domain, port hoặc CIDR đã được operator/tenant đăng ký và xác minh.
3. **DNS validation:** phân giải hostname và kiểm tra tất cả địa chỉ trả về; không chấp nhận hostname có bất kỳ kết quả không phù hợp với policy.
4. **Connection pinning:** bảo đảm client kết nối tới IP đã được kiểm tra hoặc dùng egress proxy có policy; tránh kiểm tra một IP rồi để client tự phân giải lại một IP khác.
5. **Redirect policy:** tắt tự động follow redirect, hoặc xác minh lại scheme/host/IP/port ở mọi hop.
6. **Network egress:** chặn truy cập metadata endpoint, control plane, loopback và mạng quản trị không cần thiết ở firewall, security group hoặc egress gateway.
7. **Timeout và giới hạn:** giới hạn connect/read timeout, response size, số redirect, số lần retry và tổng thời gian.
8. **Audit:** ghi host đã chuẩn hóa, policy decision và correlation ID; không ghi credential hoặc full URL chứa secret.

DNS validation cần được thực hiện gần thời điểm kết nối. Nếu client tự resolve lại hostname sau khi broker kiểm tra, DNS rebinding vẫn có thể xảy ra. Một cách mạnh hơn là dùng HTTP client/egress proxy có khả năng kiểm soát DNS resolution và IP đích thực tế. Không tự viết socket client hoặc DNS parser nếu có thư viện và network control đã được kiểm chứng.

Nếu URL chỉ được lưu và chuyển cho một backend khác, backend đó cũng phải áp dụng policy. Validation ở broker không đủ nếu worker hoặc provider adapter phân giải hostname lại ở thời điểm sau.

## 7. Chống open redirect và host header injection

Không dùng trực tiếp Host, X-Forwarded-Host hoặc Forwarded từ request để tạo dashboard_url hay route_service_url, trừ khi reverse proxy tin cậy đã xác thực và chuẩn hóa chúng theo cấu hình rõ ràng.

Một số nguyên tắc:

- Cấu hình trusted proxy và danh sách proxy được phép gửi forwarded headers.
- Không tin X-Forwarded-Host từ internet client trực tiếp.
- Tạo URL tuyệt đối từ base URL đã cấu hình, không dựa vào Host header tùy ý.
- Nếu hỗ trợ redirect parameter, chỉ chấp nhận relative path trong namespace nội bộ hoặc host nằm trong allowlist.
- Không cho phép URL dạng //attacker.example, backslash bất thường hoặc scheme-relative reference.
- Kiểm tra sau canonicalization để tránh bypass bằng percent-encoding, dấu chấm hoặc ký tự Unicode.

Ví dụ logic không an toàn:

~~~java
String dashboardUrl =
        "https://" + request.getHeader("Host")
                + "/instances/" + instanceId;
~~~

Host header có thể bị caller kiểm soát nếu request đi qua proxy chưa được cấu hình tin cậy. Hãy lấy dashboardBaseUrl từ application configuration hoặc service registry đã xác minh.

## 8. Canonicalization và parsing URI

Không validate URL bằng regex đơn lẻ. Parser URI giúp tách scheme, authority, host, port, path, query và fragment để policy kiểm tra từng thành phần.

Một ví dụ kiểm tra cơ bản:

~~~java
public URI validateDashboardUrl(URI uri, Set<String> allowedHosts) {
    if (!"https".equalsIgnoreCase(uri.getScheme())) {
        throw new InvalidEndpointException("HTTPS is required");
    }
    if (uri.getHost() == null || uri.getUserInfo() != null) {
        throw new InvalidEndpointException("Invalid URL authority");
    }

    String host = IDN.toASCII(uri.getHost()).toLowerCase(Locale.ROOT);
    if (!allowedHosts.contains(host)) {
        throw new InvalidEndpointException("Host is not allowed");
    }

    if (uri.getPort() != -1 && uri.getPort() != 443) {
        throw new InvalidEndpointException("Port is not allowed");
    }
    if (uri.getFragment() != null) {
        throw new InvalidEndpointException("Fragments are not allowed");
    }

    return uri;
}
~~~

Đây chỉ là ví dụ cho URL dashboard với allowlist host chính xác. Ứng dụng thực tế cần xử lý URI malformed, IDN, trailing dot, IPv6 literal, path policy, query policy, encoded separators và default port trước khi so sánh. Với endpoint do caller gửi để broker kết nối, cần thêm DNS/IP/redirect/egress checks ở phần trước; đoạn code trên không phải một SSRF defense hoàn chỉnh.

Canonicalization phải được áp dụng nhất quán ở bước validate, lưu trữ, so sánh allowlist và kết nối. Không validate chuỗi đã decode nhưng sau đó gửi chuỗi gốc cho client khác parse theo quy tắc khác. Tránh decode nhiều lần hoặc encode path segment thủ công gây double-decoding.

## 9. Xây dựng response URL an toàn trong Spring

Một factory có thể nhận base URL từ cấu hình và instance state đã xác minh:

~~~java
@Component
public class DashboardUrlFactory {

    private final URI dashboardBaseUri;

    public DashboardUrlFactory(URI dashboardBaseUri) {
        this.dashboardBaseUri = validateConfiguredBase(dashboardBaseUri);
    }

    public URI create(String instanceId) {
        return UriComponentsBuilder.fromUri(dashboardBaseUri)
                .pathSegment("instances", instanceId, "overview")
                .build()
                .encode()
                .toUri();
    }
}
~~~

dashboardBaseUri được bind từ application configuration. validateConfiguredBase là hàm kiểm tra cấu hình cần được triển khai theo allowlist và scheme policy. Cấu hình phải được xác thực khi ứng dụng khởi động để lỗi URL không xuất hiện giữa một request provision.

Response mapper chỉ nhận URI đã được factory tạo:

~~~java
return CreateServiceInstanceResponse.builder()
        .dashboardUrl(dashboardUrlFactory.create(instance.id()).toString())
        .build();
~~~

Đây là ví dụ theo kiểu builder của Spring Cloud Open Service Broker; chữ ký model cần khớp phiên bản dependency. Không để response mapper nhận một URL tùy ý từ parameters rồi tự quyết định độ tin cậy.

## 10. Bảo vệ route và địa chỉ do platform gửi

Với route binding, platform có thể gửi route trong bind_resource. Broker nên kiểm tra route theo contract của nền tảng tích hợp:

- Route phải có dạng hợp lệ và thuộc domain/zone mà platform quản lý.
- Nếu route gắn với application hoặc tenant, xác minh caller có quyền bind route đó.
- Không chấp nhận route chứa scheme, user-info, path hoặc port nếu schema chỉ cho phép hostname.
- Không cho phép route của tenant khác hoặc domain không được đăng ký.
- Không tự truy cập route để kiểm tra sống nếu chưa có SSRF policy.
- Lưu route đã chuẩn hóa và liên kết với binding ID để unbind/reconcile chính xác.

Cloud Foundry, Kubernetes ingress và các nền tảng khác có mô hình route/host khác nhau. Đừng áp dụng một regex hostname chung cho mọi platform. Đặt validation sau một platform-specific adapter: adapter chuyển request platform thành ValidatedRoute nội bộ; domain service chỉ nhận kiểu đã được xác minh.

Nếu service broker cho phép endpoint bên ngoài làm parameters, cần có policy riêng theo service plan. Ví dụ, một plan chỉ cho phép database endpoint thuộc private CIDR của tenant; plan khác chỉ cho phép hostname đã đăng ký trong endpoint registry. Không cho mọi plan tự do kết nối tới bất kỳ host nào.

## 11. Phân tách validation, authorization và network policy

Ba bước này giải quyết các câu hỏi khác nhau:

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Syntax/schema validation | Giá trị có đúng định dạng không? | Hostname hợp lệ, port là integer |
| Authorization/policy | Caller có quyền sử dụng địa chỉ này không? | Tenant chỉ được dùng endpoint đã đăng ký |
| Network enforcement | Kết nối thực tế có thể đi tới đâu? | Egress firewall chặn metadata và control-plane network |

Một URL có thể hợp lệ về cú pháp nhưng caller không có quyền sử dụng. Một URL được policy cho phép vẫn có thể bị DNS rebinding hoặc redirect dẫn đến IP không an toàn. Một policy đúng trong code vẫn cần network egress controls để giới hạn tác động nếu code có lỗi.

Không coi validation là thay thế cho authorization. Không coi authorization là thay thế cho egress firewall. Các lớp cần bổ trợ nhau.

## 12. Quản lý secret và dữ liệu nhạy cảm trong URL

URL thường xuất hiện trong log, trace, metrics, error report, browser history và hệ thống monitoring. Vì vậy:

- Không đặt password, access token, API key hoặc private key trong URL.
- Không ghi full callback URL nếu query có thể chứa token.
- Redact query parameters nhạy cảm trước khi log, nhưng tốt nhất là không cho secret đi vào URL ngay từ đầu.
- Không đưa signed dashboard URL vào metric label hoặc audit event dài hạn.
- Nếu signed link là bắt buộc, đặt TTL ngắn, scope đúng instance/tenant, audience cụ thể và có thể revoke.
- Không dùng instance ID đơn thuần như secret để cấp quyền truy cập dashboard.
- Không trả URL nội bộ có thông tin topology hoặc tên service account.

Nếu dashboard_url chỉ giúp điều hướng đến trang đăng nhập, để dashboard tự xác thực người dùng theo SSO/OIDC hoặc cơ chế nền tảng. Nếu cần deep link có token, token phải ngắn hạn và chỉ cấp quyền tối thiểu; không tái sử dụng broker API credential.

## 13. Xử lý lỗi và phản hồi an toàn

Khi địa chỉ không hợp lệ hoặc không được phép, trả lỗi validation/policy theo mapping của OSB và framework. Không trả chi tiết mạng nội bộ hoặc kết quả DNS đầy đủ cho caller.

| Tình huống | Hành vi |
|---|---|
| URL sai cú pháp hoặc scheme không hỗ trợ | Từ chối validation |
| Host không thuộc allowlist | Từ chối policy, không kết nối |
| Host phân giải đến IP bị cấm | Từ chối SSRF policy |
| DNS không phân giải được | Từ chối hoặc trả lỗi dependency phù hợp; không fallback sang địa chỉ tùy ý |
| Redirect sang host khác | Dừng hoặc xác minh lại toàn bộ policy trước mỗi hop |
| TLS certificate không hợp lệ | Không bỏ qua xác minh certificate |
| Dashboard base URL cấu hình sai | Fail fast khi khởi động hoặc không công bố dashboard URL |
| Route service endpoint không thể truy cập từ router | Không công bố endpoint chưa sẵn sàng; sửa topology/health trước |

Không trả lỗi chi tiết như IP nội bộ bị chặn bởi firewall rule nào cho caller. Dùng thông báo công khai ngắn và ghi chi tiết policy decision trong log nội bộ có kiểm soát.

## 14. Kiểm thử URL policy và SSRF

Kiểm thử cần bao phủ parser, policy và đường kết nối thực tế:

| Nhóm | Input/tình huống | Kết quả mong đợi |
|---|---|---|
| Scheme | http://host khi chỉ cho HTTPS | Từ chối |
| Authority | URL có user:pass@host | Từ chối |
| Host allowlist | console.example.com | Chấp nhận nếu cấu hình cho phép |
| Host giả | console.example.com.attacker.test | Từ chối |
| Suffix bypass | evil-example.com | Từ chối |
| Local address | Loopback, link-local, metadata IP | Từ chối nếu không có policy đặc biệt được phê duyệt |
| Private endpoint | Private CIDR đã đăng ký cho tenant | Chỉ chấp nhận đúng plan/tenant policy |
| IPv6 | IPv6 literal, IPv4-mapped IPv6, zone ID | Chuẩn hóa và áp dụng CIDR policy |
| DNS rebinding | DNS đổi từ public sang private | Kết nối vẫn bị chặn bởi pinning/egress policy |
| Redirect | Host allowlisted trả 302 sang host cấm | Không follow hoặc từ chối hop mới |
| Encoded path | %2f, %5c, %2e%2e và double encoding | Không vượt path namespace |
| Host header | Host hoặc forwarded header do client giả mạo | Không ảnh hưởng dashboard base URL |
| Secret leakage | Token trong query, log hoặc error | Secret không được phát tán |
| Route ownership | Route thuộc tenant khác | Từ chối authorization |
| Reachability | Router không thể truy cập route_service_url | Không công bố endpoint sai topology |

Unit test cho URI parser không đủ để chứng minh chống SSRF. Cần integration test với DNS giả lập, HTTP server redirect, IPv4/IPv6 test network và egress policy ở môi trường triển khai. Không dùng endpoint metadata thật trong test; mô phỏng địa chỉ bằng test fixture hoặc network sandbox.

## 15. Những sai lầm thường gặp

- Lấy dashboard_url từ request parameters hoặc Host header.
- Trả route_service_url từ URL do consumer cung cấp.
- Chỉ kiểm tra chuỗi bắt đầu bằng https://.
- Dùng regex đơn giản thay cho URI parser và domain boundary checks.
- Cho phép mọi private IP hoặc port vì service broker cần kết nối mạng nội bộ.
- Kiểm tra DNS một lần rồi để HTTP client tự resolve lại.
- Tự động follow redirect mà không kiểm tra host/IP mới.
- Bỏ qua TLS certificate error để kết nối cho được.
- Đưa token hoặc password vào query string.
- Chỉ kiểm tra route syntax mà không kiểm tra tenant ownership.
- Dùng một policy hostname chung cho Cloud Foundry, Kubernetes và mọi service plan.
- Nghĩ rằng validation trong broker đủ thay thế egress firewall.

## Kết luận

dashboard_url và route_service_url là các URL broker công bố, nên được tạo từ cấu hình hoặc service registry tin cậy và kiểm tra scheme, host, port, path cùng dữ liệu nhạy cảm trước khi trả. Route, hostname và endpoint do platform/consumer gửi là input không tin cậy; phải được parse, chuẩn hóa, kiểm tra quyền và áp dụng policy mạng trước khi broker hoặc worker kết nối tới chúng. Chống SSRF cần allowlist, kiểm tra DNS/IP, kiểm soát redirect, connection pinning và egress firewall; chống open redirect cần tránh tin Host header và URL do caller cung cấp. Kết hợp validation theo platform, authorization theo tenant, TLS và kiểm thử các trường hợp DNS/redirect giúp service broker Spring Cloud công bố endpoint ổn định mà không mở đường truy cập vào mạng nội bộ hoặc làm lộ dữ liệu khách hàng.
