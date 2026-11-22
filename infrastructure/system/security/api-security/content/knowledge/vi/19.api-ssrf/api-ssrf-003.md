# Allowlist scheme, host, port và destination

Server-side request forgery (SSRF) xảy ra khi API lấy URL hoặc thông tin đích từ dữ liệu do client kiểm soát rồi tự thực hiện kết nối mạng. Ví dụ thường gặp là API tải ảnh theo URL, nhập dữ liệu từ một địa chỉ web, tạo bản xem trước tài liệu, kiểm tra webhook hoặc gọi callback. Nếu server có thể truy cập mạng nội bộ, cloud metadata, control plane hoặc dịch vụ quản trị, kẻ tấn công có thể lợi dụng API làm cầu nối tới những đích mà họ không thể truy cập trực tiếp.

Một lớp phòng thủ quan trọng là allowlist destination: chỉ cho phép kết nối tới scheme, hostname, port và phạm vi đích đã được phê duyệt. Allowlist phải được áp dụng sau khi parse và chuẩn hóa URL, kiểm tra DNS/IP và kiểm soát redirect; đồng thời tầng mạng cần giới hạn egress để request không thể đi tới mạng nội bộ ngoài nhu cầu. Chỉ kiểm tra URL bằng regex hoặc chỉ chặn một vài IP riêng là chưa đủ.

## 1. Xác định bề mặt SSRF trong API

SSRF có thể xuất hiện ở bất kỳ chức năng nào khiến backend chủ động kết nối tới địa chỉ do người gọi lựa chọn hoặc ảnh hưởng:

- Tải ảnh/avatar, video, PDF hoặc tài liệu từ URL.
- Tạo thumbnail, preview, screenshot hoặc trích xuất metadata từ trang web.
- Import dữ liệu từ URL, RSS feed, CSV hoặc tài liệu từ xa.
- Kiểm tra callback URL, webhook endpoint hoặc tích hợp đối tác.
- Gửi request tới dịch vụ bên thứ ba theo tham số do client cung cấp.
- Xử lý URL trong HTML, SVG, CSS, XML hoặc tài liệu có tham chiếu tài nguyên bên ngoài.
- Gọi dịch vụ chuyển đổi, render, scan hoặc phân tích nội dung có khả năng tự tải URL lồng nhau.

Một endpoint có thể không trả response của request outbound cho client mà vẫn có SSRF dạng blind. Kết quả có thể được quan sát qua thời gian phản hồi, log, DNS lookup, callback tới máy chủ của kẻ tấn công hoặc tác động lên dịch vụ nội bộ.

### Ví dụ luồng dễ bị tấn công

~~~http
POST /api/image-preview
Content-Type: application/json

{
  "imageUrl": "https://images.example.test/avatar.png"
}
~~~

Nếu server lấy trực tiếp giá trị imageUrl rồi gọi HTTP client, người dùng có thể thay bằng địa chỉ nội bộ hoặc metadata endpoint. Rủi ro không nằm ở việc client có đăng nhập hay không; nó nằm ở quyền truy cập mạng của backend và việc server có kiểm soát destination trước khi kết nối hay không.

## 2. Allowlist phải bao phủ toàn bộ destination

Một URL không chỉ có hostname. Chính sách nên xem destination là tổ hợp các thành phần:

| Thành phần | Cần kiểm soát | Ví dụ chính sách |
|---|---|---|
| Scheme | Giao thức được phép | Chỉ cho phép https |
| Host | Tên miền hoặc IP đích | Chỉ host chính xác đã đăng ký |
| Port | Cổng TCP được phép | Chỉ 443 hoặc cổng riêng đã phê duyệt |
| DNS/IP | Địa chỉ mà hostname phân giải tới | Chỉ địa chỉ global unicast được phép |
| Redirect | Đích sau mỗi lần chuyển hướng | Tắt redirect tự động hoặc xác minh lại từng hop |
| Path/method | Endpoint và hành động được phép | Chỉ POST tới callback path đã đăng ký |
| Egress route | Đường mạng outbound | Chỉ đi qua egress proxy/firewall được quản lý |

Allowlist theo host là cần thiết nhưng có thể chưa đủ. Một host được phép có thể cung cấp open redirect, endpoint proxy hoặc nội dung khiến một dịch vụ khác tiếp tục tải URL ngoài dự kiến. Với tích hợp có rủi ro cao, giới hạn cả path, HTTP method và loại request.

Ưu tiên destination được đăng ký trước trong cấu hình server hoặc bản ghi tích hợp đã được xác minh. Nếu nghiệp vụ cho phép người dùng tự nhập URL, cần quy trình xác minh và kiểm soát chặt hơn; không coi URL do user cung cấp là đáng tin chỉ vì user đã đăng nhập.

## 3. Chỉ cho phép scheme cần thiết

Scheme quyết định cách client xử lý destination và có thể mở rộng bề mặt truy cập ngoài HTTP.

Với API fetch tài nguyên Internet thông thường, ưu tiên chỉ cho phép:

~~~text
https
~~~

Chỉ hỗ trợ http nếu có nhu cầu nghiệp vụ rõ ràng và đã đánh giá rủi ro downgrade, nghe lén hoặc sửa nội dung trên đường truyền. Không chấp nhận scheme không cần thiết như:

- file: có thể truy cập file cục bộ nếu client hỗ trợ.
- ftp: mở thêm giao thức và hành vi xác thực/truyền dữ liệu.
- gopher: từng được dùng để tạo request tới dịch vụ nội bộ theo cú pháp đặc thù.
- jar:, data:, javascript: hoặc scheme riêng do thư viện hỗ trợ: có thể kích hoạt cơ chế xử lý không mong muốn.
- Các scheme custom hoặc protocol handler được cài thêm trong runtime.

Không chỉ kiểm tra URL bắt đầu bằng chuỗi "https://". Hãy parse URL bằng thư viện URI/URL đáng tin cậy, lấy scheme đã parse, chuẩn hóa chữ hoa/thường theo quy tắc giao thức và so khớp với allowlist chính xác. Từ chối URL tương đối, URL thiếu scheme hoặc URI parser không xác định được host một cách rõ ràng.

Không tự thêm https vào URL thiếu scheme theo kiểu đoán. Việc tự sửa đầu vào có thể khiến các parser khác nhau hiểu destination khác nhau.

## 4. Chuẩn hóa và allowlist hostname

### 4.1. So khớp hostname chính xác

Nếu chỉ cho phép dịch vụ ảnh tại images.example.test, allowlist nên chứa đúng hostname đó. Không dùng phép so khớp con chuỗi như:

~~~text
host.contains("example.test")
~~~

Cách này có thể chấp nhận attacker-example.test hoặc example.test.attacker.invalid.

Nếu thực sự cần cho phép subdomain, so khớp theo ranh giới nhãn DNS:

~~~text
host == "example.test"
OR host.endsWith(".example.test")
~~~

Quy tắc suffix chỉ đúng sau khi hostname được parse và canonicalize. Không áp dụng trực tiếp lên URL thô. Wildcard subdomain làm tăng rủi ro nếu người khác có thể tạo subdomain, chiếm subdomain bị bỏ quên hoặc điều khiển DNS. Ưu tiên host cụ thể cho từng đối tác.

### 4.2. Chuẩn hóa hostname trước khi so khớp

Tên miền có thể được viết với chữ hoa/thường, dấu chấm cuối, Unicode/IDN hoặc các biểu diễn khác nhau. Trước khi so sánh, cần:

1. Parse URI bằng parser chuẩn; không tự tách host bằng phép cắt chuỗi.
2. Lấy hostname đã parse, từ chối userinfo và authority mơ hồ.
3. Chuẩn hóa hostname theo quy tắc DNS: chữ thường, xử lý trailing dot nhất quán.
4. Với tên miền quốc tế hóa, chuyển sang ASCII A-label bằng IDNA với profile phù hợp và dùng cùng một cách chuẩn hóa ở lúc đăng ký lẫn lúc kiểm tra.
5. So khớp với allowlist canonical đã lưu.
6. Từ chối ký tự điều khiển, khoảng trắng bất thường, backslash hoặc dạng authority mà parser không xử lý rõ ràng.

Không tự viết bộ parser URL bằng regex. Không dùng một parser để kiểm tra nhưng dùng parser khác để kết nối nếu hai parser có thể diễn giải URL khác nhau.

### 4.3. Từ chối userinfo và URL mơ hồ

URL có thể chứa thông tin user/password trước dấu @:

~~~text
https://trusted.example.test@attacker.invalid/path
~~~

Hostname thực là attacker.invalid. Một phép kiểm tra chuỗi đơn giản có thể nhầm trusted.example.test là host. Từ chối URL có userinfo nếu nghiệp vụ không cần xác thực kiểu này.

Cũng cần từ chối hoặc xử lý rõ các trường hợp:

- Nhiều dấu @ hoặc authority bất thường.
- Hostname có percent-encoding hoặc ký tự phân cách không chuẩn.
- Backslash được parser này coi như dấu slash nhưng parser khác coi là ký tự host.
- IPv4 viết ở dạng số nguyên, octal, hexadecimal hoặc dạng rút gọn không chuẩn.
- IPv6 literal có zone identifier như %eth0 nếu không có nhu cầu rõ ràng.
- Fragment không cần thiết; fragment thường không gửi lên server nhưng có thể tạo khác biệt trong xử lý ở client.

Đừng cố sửa các URL mơ hồ thành URL "có vẻ hợp lệ". Từ chối chúng giúp tránh parser differential và bypass allowlist.

### 4.4. Cẩn thận với wildcard và domain do khách hàng quản lý

Nếu allowlist là *.customer.example, cần biết ai có quyền tạo và xóa subdomain. Một subdomain đã bị bỏ quên, CNAME tới dịch vụ bên thứ ba hoặc domain có thể được đăng ký lại có thể bị chiếm. Không cấp quyền outbound rộng cho toàn bộ domain chỉ vì domain gốc thuộc đối tác.

Với webhook, nên lưu URL endpoint sau quy trình đăng ký, xác minh quyền kiểm soát domain và phê duyệt tích hợp. Khi domain hoặc endpoint thay đổi, cần xác minh lại và ghi audit.

## 5. Giới hạn port

Port quyết định dịch vụ nào trên host sẽ nhận request. Chỉ allowlist hostname nhưng cho phép mọi port có thể biến API thành công cụ quét hoặc truy cập dịch vụ quản trị.

Ví dụ, với HTTPS Internet thông thường:

~~~text
443
~~~

Chính sách có thể từ chối mọi port khác, kể cả khi hostname hợp lệ. Nếu đối tác yêu cầu port riêng, thêm port cụ thể vào cấu hình tích hợp và chỉ áp dụng cho đúng host đó.

Quy tắc cần làm rõ:

- Port mặc định của scheme được xử lý nhất quán; với HTTPS thường là 443.
- Nếu URL ghi port tường minh, so khớp với port allowlist.
- Từ chối port 0, port ngoài phạm vi hợp lệ và các port không được phê duyệt.
- Không cho client tùy ý chọn port theo request.
- Không dùng một allowlist port toàn cục rộng cho mọi hostname nếu mỗi đối tác có yêu cầu khác nhau.

Không nên giả định chỉ port thấp hoặc port cao là nguy hiểm. Dịch vụ nội bộ có thể chạy ở bất kỳ port nào; chính sách nên là allowlist port cần thiết, không phải danh sách deny vài port phổ biến.

## 6. Kiểm tra DNS và địa chỉ IP đích

Allowlist hostname không đảm bảo hostname luôn trỏ tới địa chỉ an toàn. DNS có thể trả về IP nội bộ, thay đổi giữa các lần lookup hoặc bị kiểm soát bởi bên thứ ba.

### 6.1. Chặn địa chỉ không được phép

Sau khi chuẩn hóa hostname và xác nhận host nằm trong allowlist, phân giải tất cả bản ghi A và AAAA cần dùng. Từ chối destination nếu bất kỳ địa chỉ đích nào thuộc vùng không được phép theo chính sách.

Các nhóm cần chặn đối với fetch Internet thông thường gồm:

- IPv4 private (RFC 1918).
- Loopback, link-local, unspecified và multicast.
- Shared address space và các dải special-purpose không định tuyến công khai.
- IPv6 loopback, link-local, unique-local và multicast.
- IPv4-mapped IPv6 có thể biểu diễn địa chỉ IPv4 bị cấm.
- Địa chỉ metadata của cloud và các địa chỉ quản trị/hạ tầng đặc biệt.
- Các IP nội bộ, VPN, service network hoặc dải egress không được phê duyệt của tổ chức.

Nên dùng thư viện/nguồn phân loại IP được duy trì theo IANA special-purpose registries và chính sách mạng của tổ chức. Không chỉ kiểm tra ba dải RFC 1918 rồi coi mọi IP còn lại là an toàn. Phải kiểm tra cả IPv4 lẫn IPv6; không bỏ qua AAAA chỉ vì môi trường thường dùng IPv4.

Với use case chỉ cần truy cập một tập destination cố định, cách an toàn hơn là allowlist chính xác các IP/host được phê duyệt và kiểm soát egress. Không cho phép IP literal tùy ý trừ khi địa chỉ đó được đăng ký rõ ràng.

### 6.2. Kiểm tra toàn bộ kết quả DNS

Nếu một hostname trả về nhiều A/AAAA records, phải đánh giá toàn bộ địa chỉ có thể được client chọn. Không chỉ kiểm tra địa chỉ đầu tiên rồi để HTTP client tự chọn một địa chỉ khác.

CNAME chain cũng cần được xem xét. Host được allowlist có thể là alias trỏ tới một hostname khác; cuối cùng cần đánh giá IP mà kết nối sẽ sử dụng. Giới hạn số bước CNAME và xử lý lỗi/loop DNS theo cách fail closed.

Nếu bất kỳ địa chỉ có thể được sử dụng nào không đạt policy, từ chối request hoặc chỉ kết nối tới tập địa chỉ đã xác minh theo một cơ chế pinning an toàn. Không để client âm thầm chọn một địa chỉ khác ngoài tập đã kiểm tra.

### 6.3. Chống DNS rebinding và TOCTOU

DNS rebinding xảy ra khi hostname ban đầu phân giải tới IP công khai để vượt qua kiểm tra, rồi trả về IP nội bộ ở lần phân giải tiếp theo khi HTTP client thực sự kết nối. Đây là vấn đề time-of-check/time-of-use (TOCTOU).

Luồng không an toàn:

1. Ứng dụng resolve hostname.
2. Kiểm tra IP trả về là public.
3. Ứng dụng gọi HTTP client bằng hostname.
4. HTTP client tự resolve lại và kết nối tới IP nội bộ.

Để giảm rủi ro:

- Dùng resolver/HTTP transport có khả năng kết nối tới chính IP đã xác minh, trong khi vẫn giữ hostname gốc cho TLS SNI, certificate verification và HTTP Host.
- Hoặc chuyển outbound qua egress proxy kiểm tra DNS và IP ngay tại thời điểm mở kết nối.
- Không để HTTP client resolve lại hostname theo một đường không được kiểm soát sau khi ứng dụng đã kiểm tra.
- Kiểm tra lại địa chỉ khi tạo kết nối mới; không cho connection pool tái sử dụng một kết nối đã vượt khỏi chính sách hoặc đổi đích không rõ ràng.
- Dùng DNS resolver tin cậy và giới hạn cache theo chính sách; cache dài không thay thế kiểm tra tại connect time.

Việc pin IP phải giữ nguyên kiểm tra TLS với hostname được yêu cầu. Không tắt hostname verification hoặc bỏ xác minh certificate để "làm cho IP pinning hoạt động".

## 7. Xử lý redirect an toàn

Một URL ban đầu được allowlist có thể trả về redirect tới destination khác:

~~~http
HTTP/1.1 302 Found
Location: http://169.254.169.254/
~~~

Nếu HTTP client tự động follow redirect, kiểm tra ban đầu không còn bảo vệ request tiếp theo.

Có hai lựa chọn:

1. **Tắt redirect tự động:** phù hợp nhất khi nghiệp vụ không cần redirect.
2. **Cho phép redirect có kiểm soát:** đọc Location, parse lại URL, kiểm tra scheme/host/port/DNS/IP và policy path/method cho từng hop trước khi kết nối tiếp.

Nếu cho phép redirect:

- Đặt số hop tối đa nhỏ.
- Không cho phép downgrade từ HTTPS xuống HTTP.
- Không giữ Authorization, Cookie, Proxy-Authorization hoặc credential của request trước khi chuyển sang host khác.
- Không chuyển tiếp body nhạy cảm sang destination mới.
- Kiểm tra relative redirect bằng cách resolve với base URI rồi áp dụng đầy đủ allowlist.
- Chặn vòng lặp và redirect tới scheme không được phép.
- Áp dụng DNS/IP validation và kết nối pinning ở từng hop.

Không coi redirect giữa hai hostname cùng domain là an toàn nếu subdomain có thể do bên khác kiểm soát.

## 8. Kiểm soát egress ở tầng mạng

Application allowlist giúp xác định request nghiệp vụ được phép, còn network egress policy giới hạn nơi workload có thể kết nối. Hai lớp cần phối hợp.

- Chạy service fetcher trong network segment riêng, không có quyền truy cập trực tiếp database hoặc management plane nếu không cần.
- Chặn outbound tới private, loopback, link-local, metadata, control-plane và service network.
- Chỉ mở egress tới proxy hoặc destination cần thiết.
- Egress proxy nên kiểm tra host, port, DNS resolution và IP ngay trước khi kết nối.
- Không cho request do client điều khiển tự chọn proxy qua query/header.
- Kiểm soát biến môi trường HTTP_PROXY, HTTPS_PROXY, ALL_PROXY và NO_PROXY; không để input bên ngoài thay đổi routing.
- Chặn UDP hoặc giao thức khác nếu fetcher chỉ cần HTTPS/TCP.
- Tách workload xử lý URL khỏi workload chứa credential hoặc quyền truy cập nhạy cảm.

Network policy có thể chặn một lớp SSRF ngay cả khi một endpoint quên kiểm tra URL. Tuy nhiên, egress proxy cũng cần cấu hình đúng; nếu proxy cho phép CONNECT tới mọi host/port thì nó có thể trở thành đường vòng.

## 9. Giới hạn request và dữ liệu trả về

Destination hợp lệ không có nghĩa response của nó an toàn hoặc rẻ để xử lý. Một host allowlist có thể trả file rất lớn, response chậm, redirect chain dài hoặc nội dung khiến parser tiêu hao CPU.

Với mọi outbound fetch, giới hạn:

- Connect timeout, TLS handshake timeout và tổng request deadline.
- Read timeout và thời gian không có dữ liệu.
- Tổng response bytes, kể cả sau giải nén.
- Số redirect và số lần retry.
- Content-Type và định dạng thực tế cần xử lý.
- Số lượng phần tử, độ sâu parser và thời gian parse.
- HTTP method và header được phép.
- Số request đồng thời theo user, tenant và global capacity.

Không chuyển tiếp toàn bộ header của request inbound. Đặc biệt không gửi Authorization, Cookie, session ID, API key hoặc internal service token tới destination do người dùng chọn. Nếu cần xác thực với đối tác, dùng credential được gắn với đúng integration record và audience/host đã đăng ký.

Không trả nguyên response body từ destination về client nếu body có thể chứa dữ liệu nội bộ, header nhạy cảm hoặc thông tin kỹ thuật. Chỉ trích xuất dữ liệu cần thiết, validate schema và áp dụng output filtering.

## 10. Thiết kế destination registry thay vì nhận URL tự do

Với tích hợp lâu dài, nên lưu destination được phê duyệt trong registry phía server:

~~~json
{
  "integrationId": "partner-image-service",
  "scheme": "https",
  "host": "images.partner.example",
  "port": 443,
  "allowedPaths": ["/v1/assets/"],
  "allowedMethods": ["GET"],
  "enabled": true
}
~~~

Client chỉ gửi integration ID và tài nguyên cần lấy:

~~~http
POST /api/integrations/partner-image-service/fetch
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "assetPath": "/v1/assets/avatar-42.png"
}
~~~

Server tra cứu cấu hình tin cậy, kiểm tra principal có quyền sử dụng integration, ghép path an toàn và thực hiện request. Không nhận một URL tùy ý rồi cố xác minh trong từng request nếu nghiệp vụ có thể dùng destination registry.

Nếu bắt buộc nhận URL đầy đủ, kiểm tra URL với policy của đúng integration/tenant. Không cho một tenant sửa allowlist dùng chung hoặc đăng ký host có thể truy cập nội bộ. Việc thêm destination cần xác minh quyền kiểm soát domain, owner, mục đích, port, path và thời hạn phê duyệt.

### 10.1. Xây dựng URL từ path đã kiểm tra

Không nối chuỗi tùy tiện:

~~~java
String target = baseUrl + request.path();
~~~

Nếu path chứa //attacker.invalid, encoded separator hoặc path traversal, kết quả có thể khác dự kiến. Dùng URI builder, kiểm tra path segment, từ chối absolute URI trong trường path và xác minh kết quả cuối cùng vẫn nằm trong origin đã đăng ký.

Nếu destination yêu cầu query parameter, allowlist tên parameter và kiểm tra giá trị; không cho client ghi đè host, port hoặc scheme qua một cấu trúc URL lồng nhau.

## 11. Ví dụ thiết kế trong Java/Spring

Đoạn dưới minh họa cách tạo HTTP client không tự động follow redirect và có timeout:

~~~java
HttpClient httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
~~~

Cấu hình này chỉ xử lý redirect và connect timeout. Nó **không tự tạo SSRF protection**: ứng dụng vẫn phải parse URL, xác minh scheme/host/port, kiểm tra DNS/IP và bảo đảm transport kết nối tới địa chỉ đã được xác minh.

Có thể tách policy thành các thành phần rõ ràng:

~~~java
public interface DestinationPolicy {
    ValidatedDestination validate(
            URI requestedUri,
            IntegrationPolicy integrationPolicy);
}

public interface SafeOutboundClient {
    OutboundResponse get(ValidatedDestination destination);
}
~~~

ValidatedDestination nên là kiểu dữ liệu chỉ được tạo bởi policy sau khi kiểm tra thành công. Không cung cấp constructor công khai cho controller hoặc deserialize nó trực tiếp từ JSON. HTTP client chỉ nhận đối tượng đã xác minh, không nhận chuỗi URL tùy ý.

Một luồng xử lý tổng quát:

~~~java
public PreviewResponse createPreview(
        UUID integrationId,
        PreviewRequest request,
        AuthenticatedPrincipal principal) {

    IntegrationPolicy policy =
            integrationService.requireUsableIntegration(
                    principal, integrationId);

    URI uri = uriBuilder.buildFromApprovedBaseAndPath(
            policy.baseUri(), request.assetPath());

    ValidatedDestination destination =
            destinationPolicy.validate(uri, policy);

    OutboundResponse response =
            safeOutboundClient.get(destination);

    return previewParser.parseWithLimits(response);
}
~~~

Các thành phần phải bảo đảm:

- requireUsableIntegration kiểm tra quyền chức năng, tenant và trạng thái tích hợp.
- buildFromApprovedBaseAndPath không cho path thay đổi authority.
- DestinationPolicy chuẩn hóa và kiểm tra toàn bộ destination, DNS/IP và port.
- SafeOutboundClient dùng IP đã xác minh hoặc egress proxy có policy, giữ TLS hostname verification và không follow redirect tự động.
- parseWithLimits giới hạn response bytes, content type, parser depth và thời gian xử lý.

Đây là cấu trúc minh họa, không phải implementation hoàn chỉnh có thể copy nguyên xi. Các chi tiết DNS pinning, IP range classification và connection pooling phụ thuộc HTTP transport và hạ tầng; nên dùng thư viện được duy trì hoặc egress proxy chuyên dụng thay vì tự viết socket resolver.

## 12. Logging, audit và xử lý lỗi

Ghi lại đủ thông tin để điều tra nhưng không làm lộ credential hoặc dữ liệu nhạy cảm:

- Principal/client/tenant ID đã xác minh.
- Integration ID và destination policy ID.
- Scheme, hostname canonical, port và kết quả allowlist.
- IP đã xác minh ở mức phù hợp với chính sách log.
- Redirect bị chặn, DNS result bị từ chối và lý do policy.
- Request ID, thời gian kết nối, bytes nhận, timeout và status outbound.
- Người tạo/sửa destination registry, thời điểm, lý do và phê duyệt.

Không log raw Authorization, cookie, API key, URL chứa userinfo, query token hoặc signed URL. Query string có thể chứa thông tin cá nhân hoặc secret; cần redact trước khi log.

Response cho client nên tổng quát, ví dụ 400 cho URL không hợp lệ hoặc 403 khi integration không được phép. Không trả IP nội bộ, DNS record, tên service, network topology, stack trace hoặc chi tiết rule firewall. Lỗi DNS/connection timeout có thể được ghi nhận nội bộ với request ID để điều tra.

## 13. Kiểm thử allowlist và SSRF

Kiểm thử phải xác minh destination thực tế mà server kết nối tới, không chỉ kiểm tra kết quả validator. Dùng DNS/test server và mạng giả lập trong môi trường kiểm thử được kiểm soát.

| Nhóm | Đầu vào/tình huống | Kết quả mong đợi |
|---|---|---|
| Scheme | https được allowlist | Được tiếp tục nếu các kiểm tra khác đạt |
| Scheme không hỗ trợ | file, ftp, gopher, data hoặc scheme custom | Bị từ chối trước khi kết nối |
| Host chính xác | Host đã đăng ký | Chỉ được phép trong policy tương ứng |
| Host suffix giả | trusted.example.attacker.invalid | Bị từ chối |
| Userinfo | trusted.example@attacker.invalid | Bị từ chối hoặc parse thành host thật rồi từ chối |
| Host Unicode/IDN | Dạng Unicode và A-label tương ứng | Chuẩn hóa nhất quán, chỉ khớp entry đã đăng ký |
| Host trailing dot/case | EXAMPLE.TEST. | Canonicalize theo một quy tắc và so khớp chính xác |
| Authority mơ hồ | Backslash, percent-encoding hoặc nhiều dấu @ | Bị từ chối |
| IP literal | Private/loopback/link-local IPv4 hoặc IPv6 | Bị từ chối |
| IPv4 dạng thay thế | Integer, octal, hexadecimal hoặc dạng rút gọn | Bị từ chối hoặc chuẩn hóa rồi áp IP policy |
| Port | Port 443 đã duyệt | Được phép nếu host cũng hợp lệ |
| Port không duyệt | Port 22, 2375, 8080 hoặc port khác không được đăng ký | Bị từ chối |
| DNS A/AAAA | Host resolve tới public IP | Chỉ kết nối tới IP đã xác minh |
| Mixed DNS answer | Một public IP và một private IP | Fail closed hoặc chỉ dùng tập IP được pin theo policy |
| CNAME | Alias kết thúc ở IP nội bộ | Bị từ chối |
| DNS rebinding | IP thay đổi giữa validation và connect | Transport/proxy ngăn kết nối tới IP chưa xác minh |
| Redirect | Host allowlist redirect sang host khác | Redirect bị tắt hoặc destination mới được kiểm tra đầy đủ |
| Redirect downgrade | HTTPS redirect sang HTTP | Bị từ chối |
| Proxy | Client gửi header/URL yêu cầu proxy khác | Không thay đổi egress route |
| Response size | Destination trả body quá lớn hoặc gzip bomb | Bị dừng theo giới hạn |
| Timeout | Destination kết nối/chờ response quá lâu | Request bị timeout, giải phóng tài nguyên |
| Credential forwarding | Destination do client chọn | Không nhận Authorization/cookie/internal token của inbound request |
| Path manipulation | Path chứa absolute URL, encoded slash hoặc traversal | Không thể đổi authority hoặc thoát path allowlist |

Ngoài test unit cho parser và policy, cần integration test qua HTTP client thật, DNS resolver, connection pool và egress proxy đang dùng. Kiểm tra rằng địa chỉ được xác minh chính là địa chỉ nhận kết nối. Thực hiện negative test với cả IPv4 và IPv6.

## 14. Checklist thiết kế trước khi phát hành

- [ ] Endpoint outbound đã được nhận diện trong inventory và có mục đích nghiệp vụ rõ ràng.
- [ ] Ưu tiên destination registry; URL tự do chỉ được nhận khi thật sự cần.
- [ ] Scheme được allowlist, mặc định chỉ HTTPS.
- [ ] Hostname được parse, canonicalize và so khớp chính xác; không dùng substring.
- [ ] IDN, trailing dot, userinfo, backslash, percent-encoding và authority mơ hồ được xử lý rõ.
- [ ] Port chỉ gồm port cần thiết cho đúng destination.
- [ ] DNS A/AAAA và CNAME chain được kiểm tra; private, loopback, link-local, metadata và special-purpose IP bị chặn.
- [ ] Chống DNS rebinding bằng IP pinning ở connect time hoặc egress proxy có kiểm tra.
- [ ] TLS certificate và hostname verification luôn được giữ.
- [ ] Redirect tự động bị tắt hoặc từng hop được xác minh lại đầy đủ.
- [ ] HTTP method, path, header, request body và credential forwarding bị giới hạn.
- [ ] Response bytes, decompression, parser depth, timeout, concurrency và retry có giới hạn.
- [ ] Egress firewall/proxy chặn mạng nội bộ và chỉ mở destination cần thiết.
- [ ] Destination registry có owner, quy trình xác minh, phê duyệt, audit và thu hồi.
- [ ] Log không chứa raw token, cookie, API key hoặc signed URL.
- [ ] Có test IPv4/IPv6, mixed DNS, CNAME, redirect, DNS rebinding và địa chỉ nội bộ.

Allowlist SSRF cần xác định rõ scheme, host, port và destination được phép, sau đó bảo đảm request thực tế không thể đi tới địa chỉ khác qua DNS, redirect hoặc proxy. Kiểm soát ở ứng dụng quyết định destination nào phù hợp với nghiệp vụ; kiểm soát egress giới hạn mạng mà workload có thể chạm tới; giới hạn response và parser bảo vệ tài nguyên khi destination hợp lệ vẫn trả nội dung độc hại. Kết hợp các lớp này mới tạo được ranh giới outbound đáng tin cậy cho API.
