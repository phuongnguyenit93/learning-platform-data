# DNS hijacking: phát hiện, ứng phó và khôi phục

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt DNS hijacking, DNS cache poisoning, resolver compromise và registrar/domain takeover.
2. Giải thích cách thay đổi DNS có thể chuyển hướng người dùng tới hạ tầng không được phép.
3. Đánh giá tác động tới HTTPS, TLS certificate, HSTS, cookie, origin và browser storage.
4. Nhận biết dấu hiệu DNS bất thường từ browser, endpoint, recursive resolver và authoritative DNS.
5. Thu thập chứng cứ DNS, TLS, HTTP và browser mà không làm mất dữ liệu điều tra.
6. Khoanh vùng sự cố theo domain, record, resolver, mạng, thiết bị và khoảng thời gian.
7. Phối hợp containment với registrar, DNS provider, ISP/resolver và đội vận hành.
8. Khôi phục delegation, DNSSEC, certificate, session và dữ liệu client theo thứ tự an toàn.
9. Phân biệt vai trò và giới hạn của DNSSEC, DoH/DoT, TLS, HSTS và certificate transparency.
10. Xây dựng runbook, tiêu chí kết thúc sự cố và bài diễn tập DNS hijacking.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. DNS hijacking có thể làm người dùng kết nối tới máy chủ ngoài dự kiến. Khi đó, cần đánh giá cả chuỗi phân giải tên, xác thực TLS, nội dung web được browser thực thi và credential/session có thể bị ảnh hưởng.

## 1. DNS hijacking là gì?

DNS (Domain Name System) ánh xạ tên miền như app.example.test sang địa chỉ IP và các loại dữ liệu khác. Browser thường dựa vào resolver để tìm địa chỉ trước khi thiết lập kết nối tới server.

DNS hijacking là hành vi thay đổi hoặc thao túng kết quả phân giải DNS hay cấu hình điều hướng tên miền để người dùng bị đưa tới hạ tầng không được chủ sở hữu domain dự kiến. Tùy điểm bị chiếm quyền, sự cố có thể chỉ ảnh hưởng một mạng, một resolver, một thiết bị hoặc toàn bộ người dùng của domain.

Ví dụ luồng bình thường:

    Người dùng mở https://app.example.test
              |
              v
       Browser / OS resolver
              |
              v
       Recursive DNS resolver
              |
              v
       Authoritative DNS
              |
              v
       IP của dịch vụ hợp lệ
              |
              v
       TLS handshake và xác minh certificate
              |
              v
       HTTP response của ứng dụng

Nếu một bước DNS bị thay đổi, browser có thể nhận địa chỉ IP khác. Tuy nhiên, việc phân giải ra IP khác chưa tự động có nghĩa attacker đã vượt qua TLS. Browser vẫn xác minh certificate theo hostname, trừ khi certificate hợp lệ bị cấp sai, trust store bị can thiệp hoặc người dùng bỏ qua cảnh báo.

### DNS hijacking khác DNS outage

DNS outage khiến tên miền không phân giải được hoặc truy cập thất bại. DNS hijacking có thể vẫn trả lời bình thường nhưng trỏ tới địa chỉ sai. Vì vậy, người dùng có thể thấy một website hoạt động thay vì lỗi rõ ràng.

### DNS hijacking khác HTTP redirect

HTTP redirect xảy ra sau khi browser đã kết nối tới một server và nhận response redirect. DNS hijacking làm thay đổi nơi browser kết nối trước HTTP request. Điều tra cần xác định chuyển hướng xảy ra ở DNS, TLS, HTTP hay JavaScript.

## 2. Các dạng DNS hijacking thường gặp

| Dạng | Điểm bị ảnh hưởng | Phạm vi thường gặp |
| --- | --- | --- |
| Registrar/domain account takeover | Tài khoản đăng ký domain hoặc thao tác delegation | Có thể ảnh hưởng toàn domain |
| Authoritative DNS compromise | Tài khoản hoặc hệ thống DNS authoritative | Các record được quản lý tại zone |
| DNS provider/API key compromise | Control plane hoặc credential của nhà cung cấp DNS | Một hoặc nhiều zone |
| Recursive resolver compromise | Resolver mà client sử dụng | Người dùng của resolver hoặc mạng |
| DNS cache poisoning | Cache của resolver bị đưa dữ liệu sai | Client dùng cache bị ảnh hưởng |
| Router/DHCP DNS manipulation | Cấu hình DNS trên router hoặc DHCP | Thiết bị trong mạng bị ảnh hưởng |
| Endpoint malware/hosts file change | Resolver cục bộ hoặc file hosts | Một thiết bị hoặc nhóm endpoint |
| Rogue Wi-Fi/captive network | DNS được cấp trong mạng không tin cậy | Thiết bị kết nối mạng đó |
| BGP/route hijack liên quan DNS | Đường định tuyến tới resolver/authoritative | Một vùng mạng hoặc nhà cung cấp |

BGP route hijack không phải thay đổi DNS record theo nghĩa hẹp. Tuy nhiên, nó có thể làm lưu lượng tới resolver hoặc authoritative server đi qua tuyến không mong đợi, nên thường được điều tra như một sự cố định tuyến có ảnh hưởng tới DNS.

### Registrar takeover

Attacker chiếm tài khoản registrar hoặc kênh hỗ trợ domain rồi thay nameserver, glue record, contact hoặc cấu hình khóa domain. Nếu delegation bị đổi, authoritative DNS mới có thể kiểm soát toàn bộ record của zone.

### Authoritative DNS compromise

Attacker chiếm tài khoản DNS provider hoặc quyền quản trị zone và sửa A, AAAA, CNAME, MX, TXT, CAA hoặc record khác. Domain vẫn dùng nameserver cũ nhưng dữ liệu trả về bị thay đổi.

### Recursive resolver compromise

Resolver nhận truy vấn từ client và trả lời từ cache hoặc truy vấn authoritative. Nếu resolver bị cấu hình sai, bị chiếm quyền hoặc cache bị poisoning, một nhóm người dùng có thể nhận kết quả sai dù zone authoritative vẫn đúng.

### Local network hoặc endpoint manipulation

Router bị thay đổi DNS, DHCP cấp resolver độc hại, VPN đẩy cấu hình DNS lạ hoặc malware sửa file hosts. Sự cố có thể chỉ xảy ra trên một thiết bị/mạng, trong khi người dùng khác truy cập bình thường.

## 3. Vì sao DNS hijacking quan trọng với browser security?

Browser dùng hostname để xác định origin và kiểm tra TLS. DNS ảnh hưởng địa chỉ kết nối, nhưng không thay đổi trực tiếp quy tắc origin.

### Origin vẫn dựa trên URL

Origin được xác định bởi scheme, host và port. Ví dụ:

    https://app.example.test:443

Nếu app.example.test được phân giải sang IP khác nhưng URL vẫn giữ hostname đó, origin của document vẫn là origin trên. Nếu server giả mạo có certificate hợp lệ cho hostname, nội dung từ server đó có thể chạy trong origin thật và được browser cấp quyền truy cập tương ứng.

Nếu certificate không hợp lệ, browser thông thường hiển thị lỗi TLS và chặn truy cập. Không hướng dẫn người dùng bấm bỏ qua cảnh báo certificate để tiếp tục.

### DNS không tự cấp certificate

Thay đổi A/AAAA/CNAME không tự động tạo ra certificate hợp lệ. Attacker cần một certificate được browser tin cậy cho hostname đó, hoặc phải chiếm trust store/endpoint, khai thác một cấu hình xác minh sai hay dựa vào người dùng bỏ qua cảnh báo.

Một số quy trình cấp certificate dùng DNS challenge. Nếu attacker kiểm soát DNS authoritative, họ có thể có khả năng chứng minh quyền kiểm soát domain trong một số quy trình ACME/CA. Vì vậy, kiểm tra certificate transparency và lịch sử cấp certificate là một phần của incident response.

### Cookie và session

Cookie được áp dụng theo hostname/domain, path, thuộc tính Secure và các quy tắc cookie khác, không gắn trực tiếp với IP mà DNS trả về.

Nếu browser kết nối tới một server khác nhưng vẫn xác minh được TLS cho hostname thật, request có thể mang cookie áp dụng cho hostname đó. Server giả mạo có thể nhận credential được browser gửi nếu TLS và routing đã bị vượt qua.

Nếu TLS handshake thất bại, browser không nên gửi HTTP request và cookie qua kết nối không xác thực. Người dùng không được bypass certificate warning.

### HttpOnly không bảo vệ trước server giả mạo có TLS hợp lệ

HttpOnly ngăn JavaScript của trang đọc cookie qua document.cookie. Nó không ngăn browser tự gửi cookie trong HTTP request tới hostname hợp lệ. Nếu attacker điều khiển server đích và có thể hoàn tất TLS hợp lệ cho hostname, HttpOnly không ngăn server nhận cookie trong request.

### Web Storage và IndexedDB

localStorage, sessionStorage và IndexedDB gắn với origin/storage key, không gắn với IP. DNS hijacking đơn thuần không làm server ở origin khác đọc được storage.

Tuy nhiên, nếu attacker có thể phục vụ nội dung dưới đúng hostname với TLS hợp lệ, script độc hại có thể chạy trong origin đó và truy cập Web Storage/IndexedDB theo quyền browser. Đây là lý do cần đánh giá cả DNS, TLS và nội dung được phân phối.

### Service Worker và cache

Service Worker được đăng ký theo origin và scope. Nếu origin bị phục vụ nội dung độc hại với TLS hợp lệ, cần điều tra khả năng script được phân phối, service worker được cập nhật và cache bị ảnh hưởng.

Không giả định flush DNS sẽ xóa HTTP cache, Cache Storage hoặc service worker. Đây là các lớp độc lập cần kiểm tra riêng.

## 4. Dấu hiệu nhận biết sự cố

Không có một chỉ báo duy nhất đủ chứng minh DNS hijacking. Cần đối chiếu nhiều nguồn.

### Dấu hiệu từ người dùng/browser

- Một số người dùng thấy certificate warning bất thường.
- Trang đăng nhập có nội dung hoặc thương hiệu khác.
- Browser chuyển tới hostname/IP không mong đợi.
- DNS resolution chậm, thất bại hoặc trả kết quả không ổn định.
- Chỉ người dùng trong một mạng/VPN/ISP bị ảnh hưởng.
- Có yêu cầu đăng nhập lại hoặc MFA bất thường.
- Trang tải script, iframe hoặc resource từ domain lạ.
- Hành vi khác nhau giữa browser dùng Secure DNS và resolver hệ điều hành.

### Dấu hiệu từ DNS telemetry

- A/AAAA/CNAME thay đổi ngoài change window.
- Nameserver hoặc DS record bị thay đổi.
- TTL thay đổi bất thường.
- DNSSEC validation chuyển từ secure sang bogus/indeterminate.
- Resolver trả lời khác nhau giữa các vùng.
- Query tới domain có NXDOMAIN hoặc SERVFAIL bất thường.
- DNS query bị chuyển tới resolver chưa được phê duyệt.
- MX/TXT/CAA bị sửa ngoài kế hoạch.

### Dấu hiệu từ TLS/certificate

- Certificate subject/SAN, issuer hoặc fingerprint thay đổi bất thường.
- Certificate mới xuất hiện trong Certificate Transparency logs.
- Certificate cấp cho hostname từ CA không thường dùng.
- Certificate validity window không phù hợp với release.
- TLS handshake thất bại ở một số mạng.
- HSTS hoặc certificate pinning policy của ứng dụng báo lỗi.

Không dựa riêng vào issuer hoặc fingerprint. CDN, load balancer và certificate rotation hợp lệ cũng có thể thay đổi certificate. Đối chiếu với change record, CA, CT log và hạ tầng.

### Dấu hiệu từ ứng dụng

- Login success giảm hoặc session reset tăng.
- Tăng lỗi API/CORS do request tới endpoint khác.
- Content-Security-Policy violation tăng đột biến.
- Script hoặc iframe source không nằm trong inventory.
- Tăng redirect, form submit hoặc request tới host lạ.
- User báo thấy dữ liệu hoặc nội dung của phiên khác.

## 5. Phân biệt sự cố theo lớp

Một trong những bước quan trọng nhất là xác định nơi kết quả bị thay đổi.

| Lớp | Câu hỏi điều tra | Công cụ/nguồn |
| --- | --- | --- |
| URL/application | Có redirect từ app không? | Browser address bar, Network |
| Browser cache/service worker | Nội dung cũ hay worker cũ có can thiệp không? | DevTools Application |
| Endpoint hosts file | Hostname có bị override cục bộ không? | Endpoint forensic, OS config |
| Local router/DHCP/VPN | Resolver nào được cấp? | Network config, DHCP/VPN logs |
| Recursive resolver | Các resolver trả cùng answer không? | dig/nslookup, resolver logs |
| Authoritative DNS | Zone data và delegation có đúng không? | DNS provider audit, authoritative query |
| Registrar/registry | Nameserver/DS/glue có bị đổi không? | Registrar audit, registry/WHOIS/RDAP |
| Routing | Tuyến tới resolver/authoritative có bất thường không? | Network telemetry, ISP/NOC |
| TLS/PKI | Certificate có hợp lệ cho hostname không? | Browser security panel, openssl, CT |

### Redirect HTTP không phải DNS hijacking

Trong Network, nếu response 301/302/307/308 từ server hợp lệ chuyển hướng tới domain khác, đó là redirect ở tầng HTTP. Kiểm tra Location header, application logic và server logs.

Nếu browser kết nối tới IP sai ngay từ đầu nhưng URL không đổi, cần kiểm tra DNS/resolver/hosts/network.

### Browser cache không phải DNS cache

DNS cache giữ kết quả phân giải tên trong một khoảng thời gian. HTTP cache giữ response tài nguyên. Cache Storage giữ response do ứng dụng/service worker quản lý. Xóa một loại không xóa các loại còn lại.

### Resolver khác nhau trả lời khác nhau

Kết quả có thể khác hợp lệ do geo DNS, CDN, split-horizon DNS, ECS hoặc propagation. So sánh cần ghi resolver, thời điểm, mạng, TTL, CNAME chain và DNSSEC status. Không kết luận hijacking chỉ vì hai resolver trả IP khác nhau.

## 6. Quy trình ứng phó sự cố

Quy trình nên được điều phối bởi incident commander hoặc người được giao quyền. Các bước dưới đây có thể chạy song song khi đội ngũ và chứng cứ cho phép.

    Detect
      |
      v
    Declare / assign owner
      |
      v
    Preserve evidence
      |
      v
    Scope affected domain, resolver, network and users
      |
      v
    Contain registrar / DNS / resolver / endpoint
      |
      v
    Restore trusted DNS and validate TLS
      |
      v
    Revoke exposed sessions and rotate credentials
      |
      v
    Verify browser state and application integrity
      |
      v
    Monitor, communicate and close

Không thay đổi DNS hàng loạt trước khi ghi lại record, delegation, audit log và thời gian quan sát nếu việc trì hoãn không làm tăng thiệt hại. Trong tình huống đang gây rò rỉ hoặc chiếm tài khoản, containment khẩn cấp có thể cần ưu tiên; hãy ghi lại ai quyết định và dữ liệu nào còn có thể bảo toàn.

## 7. Bước 1 — Declare incident và thiết lập điều phối

### Xác nhận tín hiệu ban đầu

Thu thập:

- Domain và subdomain bị nghi ảnh hưởng.
- URL đầy đủ đã redaction query/fragment.
- Thời điểm phát hiện và timezone.
- Browser, version và OS.
- Mạng/VPN/ISP và resolver đang dùng.
- Certificate warning hoặc fingerprint quan sát được.
- DNS answer và TTL.
- Nhóm người dùng bị ảnh hưởng.
- Thao tác người dùng đã thực hiện sau khi thấy bất thường.

### Phân loại mức độ

Mức độ phụ thuộc domain, dữ liệu và phạm vi:

| Mức | Ví dụ |
| --- | --- |
| Critical | Domain đăng nhập/payment bị chiếm quyền; có bằng chứng credential/session bị thu thập |
| High | Authoritative DNS hoặc registrar bị kiểm soát; nhiều người dùng bị chuyển hướng |
| Medium | Một resolver hoặc mạng nội bộ trả answer sai; chưa thấy compromise diện rộng |
| Low | Một endpoint có hosts file/router cấu hình sai; đã cô lập và không có dấu hiệu lan rộng |

Đây là ví dụ phân loại, không thay thế severity model của tổ chức.

### Phân công vai trò

- Incident commander điều phối quyết định và timeline.
- DNS/domain owner liên hệ registrar và DNS provider.
- Network team kiểm tra resolver, DHCP, VPN và routing.
- Security team phân tích TLS, endpoint, session và telemetry.
- Application team đánh giá browser behavior và nội dung được phục vụ.
- Legal/privacy/comms tham gia nếu có dữ liệu hoặc người dùng bị ảnh hưởng.

### Ghi timeline

Ghi mọi hành động có timestamp UTC:

- Ai phát hiện.
- DNS record/delegation trước và sau.
- Khi nào provider được liên hệ.
- Khi nào credential bị thu hồi.
- Khi nào DNS được khôi phục.
- Khi nào certificate/session được xử lý.
- Khi nào các vùng xác nhận truy cập bình thường.

## 8. Bước 2 — Bảo toàn chứng cứ

Trước khi flush cache, reset router, đổi nameserver hoặc xóa browser profile, thu thập chứng cứ có thể mất. Nếu sự cố đang hoạt động và gây thiệt hại, containment có thể được ưu tiên nhưng cần ghi rõ trade-off.

### Chứng cứ DNS

- DNS answer A, AAAA, CNAME, NS, SOA, MX, TXT, CAA và DS/DNSKEY nếu liên quan.
- TTL và thời điểm truy vấn.
- Resolver được hỏi.
- Trạng thái DNSSEC validation.
- Nameserver delegation và glue record.
- Zone export hoặc snapshot từ DNS provider.
- Audit log thay đổi record/API key/user.
- Registrar account audit, nameserver/DS change history.

### Chứng cứ TLS/HTTP

- Certificate chain, SAN, issuer, validity và fingerprint.
- TLS version/cipher nếu cần.
- HTTP status, Location header và response headers.
- Screenshot đã che dữ liệu cá nhân.
- Network log hoặc HAR đã redaction.
- CSP violation và security telemetry.
- Server/CDN/load balancer logs.

### Chứng cứ endpoint/network

- DNS server list từ OS.
- DHCP lease và router config.
- VPN client config.
- hosts file và file metadata.
- Endpoint security alerts/processes.
- Resolver logs, firewall logs và packet capture nếu có quyền.
- BGP/route telemetry từ network provider khi có dấu hiệu route hijack.

### Chứng cứ browser

- URL/origin, browser version và thời điểm.
- Certificate details từ browser security UI.
- DevTools Network và Console.
- Service worker registration/scope/state.
- Cache Storage và HTTP cache state.
- Extension list nếu có khả năng extension gây chuyển hướng.
- Secure DNS setting và resolver mode.

Không thu thập profile browser hoặc storage cá nhân vượt quá phạm vi. Cookie, Authorization header, localStorage token, form body và URL query có thể là credential/PII; redaction trước khi chia sẻ.

### Bảo toàn tính toàn vẹn

- Ghi nguồn, người thu thập và thời điểm.
- Lưu bản gốc ở nơi hạn chế truy cập.
- Tính hash cho file evidence khi quy trình yêu cầu.
- Làm việc trên bản sao để phân tích.
- Ghi mọi thao tác đã thay đổi trạng thái hệ thống.
- Đồng bộ thời gian các nguồn log theo UTC.

## 9. Bước 3 — Khoanh vùng DNS và resolver

Mục tiêu là tìm điểm đầu tiên có câu trả lời sai.

### So sánh nhiều resolver

Trên hệ thống được phép, có thể dùng công cụ truy vấn DNS chỉ đọc:

    nslookup app.example.test

Hoặc:

    dig app.example.test A
    dig app.example.test AAAA
    dig app.example.test CNAME
    dig app.example.test NS
    dig app.example.test SOA

Truy vấn resolver cụ thể:

    dig @RESOLVER_IP app.example.test A

Thay RESOLVER_IP bằng resolver được tổ chức phê duyệt. Không truy vấn hạ tầng không thuộc phạm vi kiểm tra.

### So sánh authoritative answer

Lấy nameserver authoritative từ delegation đã xác minh rồi truy vấn trực tiếp để đối chiếu. Ghi lại:

- Server được hỏi.
- Answer và additional section.
- TTL.
- Authority section.
- DNSSEC flags nếu công cụ hiển thị.
- Thời điểm và mạng nguồn.

Nếu authoritative answer đã sai, điều tra zone/provider/registrar. Nếu authoritative đúng nhưng một recursive resolver trả answer khác, tập trung vào resolver cache, forwarding, policy hoặc poisoning.

### Kiểm tra delegation

Kiểm tra NS tại parent zone, nameserver tại child zone, glue record và DS record. Thay đổi delegation có thể khiến việc sửa record trong DNS provider cũ không có tác dụng vì resolver đang hỏi nameserver khác.

### Kiểm tra cache và TTL

TTL cho biết resolver có thể cache record trong thời gian nào theo quy tắc DNS. Một số resolver có thể giữ stale data theo cơ chế riêng khi authoritative không phản hồi. Negative caching cũng có thể giữ NXDOMAIN/NODATA.

Không kỳ vọng mọi người dùng thấy record mới ngay khi sửa authoritative. Ghi TTL cũ, TTL mới và thời gian hết cache ước tính; xác minh từ nhiều resolver và vùng mạng.

### Flush cache có chọn lọc

Sau khi bảo toàn evidence và xác định lớp cache, có thể flush DNS cache tại endpoint/resolver theo runbook quản trị. Lệnh và quyền cần thiết khác nhau theo OS/browser.

Flush DNS cache không:

- Xóa HTTP cache.
- Xóa Cache Storage.
- Unregister service worker.
- Xóa cookie hoặc Web Storage.
- Sửa delegation hoặc authoritative record.

Không dùng flush cache như bằng chứng duy nhất rằng sự cố đã hết.

## 10. Bước 4 — Kiểm tra registrar và authoritative DNS

Nếu nameserver, DS, glue hoặc zone record bị thay đổi trái phép, khôi phục quyền kiểm soát ở control plane trước khi chỉ sửa một record đơn lẻ.

### Kiểm tra registrar

Xác minh:

- Account owner và contact email/phone.
- Login history và MFA events.
- Nameserver delegation.
- DS/DNSSEC settings.
- Domain lock/registry lock.
- Transfer status và authorization changes.
- API key hoặc delegated access.
- Thay đổi billing/support contact.

### Containment tài khoản registrar

- Dùng thiết bị sạch và kênh truy cập đã xác minh.
- Thu hồi session và API credential nghi bị lộ.
- Đổi mật khẩu mạnh, bật MFA phishing-resistant nếu hỗ trợ.
- Bật registrar/registry lock theo khả năng.
- Thu hồi delegated users không còn cần.
- Liên hệ support qua kênh chính thức đã xác minh độc lập.
- Yêu cầu freeze transfer hoặc change nếu registrar cung cấp quy trình khẩn cấp.

Không dùng số điện thoại hoặc link được gửi trong email nghi giả mạo; xác minh contact từ hợp đồng hoặc portal chính thức.

### Kiểm tra DNS provider

- Audit log của zone.
- Record history/version.
- User, role và API token.
- Automation/CI credential.
- DNSSEC signing status.
- Nameserver assignment.
- Provider account recovery events.
- Change request và ticket gần thời điểm incident.

### Khôi phục record

So sánh với nguồn chuẩn được phê duyệt như zone export đã ký, infrastructure-as-code hoặc change record. Khôi phục các record cần thiết:

- A/AAAA/CNAME cho web/API.
- NS/SOA và delegation.
- MX và các record email.
- TXT cho SPF, DKIM, DMARC và domain verification.
- CAA.
- DS/DNSKEY nếu dùng DNSSEC.
- Record ACME challenge nếu quy trình cấp certificate cần.

Không copy toàn bộ zone từ một bản backup chưa xác minh; có thể đưa record độc hại hoặc cấu hình cũ trở lại. Review từng thay đổi và owner.

### Bảo vệ API và automation

Nếu DNS được quản lý qua Terraform/CI/CD:

- Rotate API token và secret có thể bị lộ.
- Kiểm tra pipeline, runner và service account.
- Review commit, deployment và audit event.
- Hạn chế token theo zone và quyền record.
- Dùng approval cho thay đổi delegation/DS/CAA.
- Kiểm tra drift giữa code và provider.

## 11. Bước 5 — Xử lý recursive resolver, router và endpoint

Nếu authoritative DNS vẫn đúng, điều tra nơi client nhận answer sai.

### Recursive resolver

- Xác định resolver do DHCP, VPN, browser Secure DNS hay cấu hình thủ công cung cấp.
- Kiểm tra forwarding và upstream.
- Xem query/response log.
- Kiểm tra cache entry và DNSSEC validation.
- Kiểm tra cấu hình policy rewrite hoặc block page.
- Cô lập resolver bị compromise khỏi client.
- Chuyển sang resolver tin cậy theo quy trình network.

Không thay DNS server hàng loạt bằng một resolver public chưa được tổ chức phê duyệt; việc đó có thể phá split DNS, policy nội bộ hoặc logging.

### Router và DHCP

- Xác minh firmware và admin account.
- Kiểm tra DNS server được cấp trong DHCP.
- Kiểm tra WAN/LAN DNS config.
- Kiểm tra remote management và UPnP theo policy.
- Rotate admin password và credential cloud management.
- Cập nhật firmware từ vendor chính thức.
- Thay router nếu không thể khôi phục trust.

### Endpoint

- Kiểm tra hosts file và metadata thay đổi.
- Kiểm tra DNS client configuration.
- Kiểm tra VPN/agent profile.
- Quét malware/EDR và process đáng ngờ.
- Kiểm tra extension hoặc proxy local.
- Cô lập endpoint nếu có dấu hiệu compromise rộng hơn DNS.
- Khôi phục từ image sạch khi cần.

Không chỉ xóa một dòng hosts file rồi đóng incident nếu chưa xác định tiến trình hoặc malware đã sửa nó.

## 12. Bước 6 — TLS, certificate và HSTS

DNS đúng là chưa đủ. Cần xác nhận browser đang nhận certificate và nội dung đúng.

### Kiểm tra certificate

Với từng hostname bị ảnh hưởng:

- Subject Alternative Name có bao gồm hostname không?
- Chain có được trust store của browser chấp nhận không?
- Issuer có hợp lệ theo PKI và change record không?
- Not Before/Not After có phù hợp không?
- Certificate mới có xuất hiện trong CT log không?
- Có certificate bất thường được cấp trong khoảng incident không?
- Private key có thể đã bị lộ không?

Certificate hợp lệ không tự chứng minh server là hạ tầng đúng. Nếu attacker kiểm soát DNS và quy trình xác minh domain, certificate vẫn có thể hợp lệ về mặt PKI nhưng không thuộc deployment được tổ chức mong muốn.

### Certificate Transparency

CT logs cho phép phát hiện certificate công khai được cấp cho domain. Kiểm tra certificate mới, SAN bất thường, issuer và thời điểm. CT là nguồn phát hiện, không phải cơ chế thu hồi certificate và không chứng minh private key bị compromise.

### Thu hồi hoặc thay certificate

Nếu certificate/private key bị compromise hoặc cấp sai:

1. Xác định CA và certificate serial.
2. Liên hệ CA theo quy trình incident.
3. Yêu cầu revoke khi có căn cứ.
4. Tạo key pair mới trên hạ tầng sạch.
5. Cấp certificate mới sau khi domain control được khôi phục.
6. Deploy chain mới và kiểm tra mọi edge/region.
7. Theo dõi OCSP/CRL/browser behavior theo CA và browser hỗ trợ.

Không chỉ thay certificate mà giữ private key nghi bị lộ.

### HSTS

HTTP Strict Transport Security yêu cầu browser dùng HTTPS cho host đã ghi nhận policy. HSTS có thể ngăn downgrade HTTP và giảm cơ hội người dùng bỏ qua một số lỗi kết nối không an toàn.

HSTS không xác minh DNS answer có trỏ tới server đúng hay không. Nếu attacker có certificate được browser tin cậy cho hostname, HSTS vẫn kết nối HTTPS tới server đó.

Preload list có thể bảo vệ trước lần truy cập đầu tiên với domain đã được preload, nhưng không phải mọi domain đều nằm trong danh sách. Kiểm tra includeSubDomains và preload trước khi thay đổi vì cấu hình sai có thể làm các subdomain không hỗ trợ HTTPS bị lỗi.

### Không bypass TLS warning

Trong incident, không hướng dẫn người dùng tiếp tục qua interstitial certificate warning, cài certificate lạ hoặc tắt kiểm tra TLS. Dùng thiết bị/mạng sạch và xác minh hostname/certificate trước khi đăng nhập.

## 13. Bước 7 — DNSSEC, DoH và DoT: vai trò và giới hạn

Các cơ chế này bảo vệ những phần khác nhau của chuỗi DNS.

### DNSSEC

DNSSEC cho phép resolver xác thực tính toàn vẹn và nguồn gốc dữ liệu DNS qua chuỗi chữ ký từ trust anchor tới zone. Khi validation hoạt động, dữ liệu bị sửa trên đường truyền hoặc cache có thể bị phát hiện nếu chữ ký không hợp lệ.

DNSSEC không mã hóa DNS query và không che giấu domain người dùng truy vấn. Nó cũng không ngăn quản trị viên authoritative hoặc registrar bị chiếm quyền tạo ra dữ liệu được ký hợp lệ.

### DS/DNSKEY chain

Khi triển khai DNSSEC, parent zone chứa DS liên kết tới key của child zone. Nếu DS và DNSKEY không khớp sau thay đổi, resolver validating có thể trả SERVFAIL. Khi khôi phục, cần phối hợp thứ tự cập nhật DS, DNSKEY và signer theo quy trình provider.

Không xóa DS một cách vội vàng chỉ để làm domain phân giải lại. Điều đó có thể tắt validation và che giấu nguyên nhân. Thực hiện theo runbook DNSSEC và xác minh với registrar/provider.

### DoH và DoT

DNS over HTTPS (DoH) và DNS over TLS (DoT) mã hóa kết nối giữa client và resolver. Chúng giảm khả năng mạng trung gian đọc hoặc sửa query/response trên đường truyền.

DoH/DoT không tự xác thực rằng resolver có trả dữ liệu authoritative đúng hay không. Nếu resolver bị compromise hoặc cố ý trả lời sai, mã hóa transport không giải quyết được vấn đề đó. DNSSEC validation và trust vào resolver vẫn quan trọng.

### Browser Secure DNS

Browser có thể dùng Secure DNS riêng thay resolver do OS/VPN cấp. Vì vậy:

- Browser A có thể truy cập đúng trong khi ứng dụng khác bị ảnh hưởng.
- Browser có thể bỏ qua split DNS nội bộ nếu cấu hình sai.
- Policy enterprise có thể ép resolver hoặc tắt Secure DNS.
- Secure DNS provider có thể khác nhau giữa profile/browser.

Khi điều tra, ghi nhận resolver thực tế của browser và OS. Không chỉ xem DNS server trong network adapter.

## 14. Bước 8 — Đánh giá tác động tới browser và ứng dụng

Sau khi xác định khoảng thời gian DNS bị sai, lập danh sách hostname và luồng browser có thể bị ảnh hưởng.

### Xác định host và chức năng

Ví dụ:

| Host | Chức năng | Dữ liệu cần đánh giá |
| --- | --- | --- |
| app.example.test | Web application | Session, form, dữ liệu người dùng |
| login.example.test | Identity/login | Password, MFA flow, authorization code |
| api.example.test | API | Request body, token, response data |
| static.example.test | JavaScript/CSS | Code được browser tải và thực thi |
| files.example.test | Download/upload | File, metadata, nội dung |
| mail.example.test | Webmail | Email và session |

Danh sách thực tế phải lấy từ inventory và DNS zone, không suy đoán theo tên host.

### Đánh giá session và credential

Nếu có khả năng browser đã kết nối tới server giả mạo với TLS được chấp nhận:

- Xác định cookie/session có thể đã được gửi.
- Xác định form login hoặc MFA có thể đã bị giả mạo.
- Xác định access/refresh token có thể đã được nhập hoặc gửi.
- Xác định API request và dữ liệu response có thể bị quan sát.
- Xác định OAuth/OIDC redirect và authorization code có thể bị lộ.
- Xác định cookie Domain rộng có ảnh hưởng subdomain nào.

Không kết luận credential bị lộ chỉ từ DNS record sai. Cần ghép thời gian DNS, TLS, HTTP, endpoint và user telemetry.

### Đánh giá cookie

Kiểm tra:

- Host-only hay Domain cookie.
- Domain có bao phủ subdomain khác không.
- Secure, HttpOnly và SameSite.
- Thời gian sống và Max-Age.
- Cookie session có bị rotate/revoke không.
- Cookie Partitioned có được dùng trong third-party context không.

Nếu có khả năng cookie bị gửi tới hạ tầng ngoài kiểm soát, revoke session server-side và rotate session identifier theo quy trình.

### Đánh giá OAuth/OIDC

Kiểm tra redirect URI, issuer, authorization endpoint, token endpoint, state, nonce và PKCE. DNS hijacking ở login/identity hostname có thể ảnh hưởng luồng đăng nhập và callback. Thu hồi authorization grant hoặc token khi threat model cho thấy cần thiết.

### Đánh giá dữ liệu client

Kiểm tra:

- localStorage/sessionStorage.
- IndexedDB.
- Cache Storage.
- Service worker.
- HTTP cache.
- Downloaded files.
- Browser autofill/password manager interactions.

Không xóa toàn bộ storage ngay khi bắt đầu điều tra. Bảo toàn chứng cứ cần thiết, sau đó làm sạch theo phạm vi user/host đã bị ảnh hưởng.

## 15. Bước 9 — Containment

Containment phụ thuộc điểm bị chiếm quyền. Có thể cần nhiều hành động đồng thời.

### Domain/registrar

- Khóa thay đổi domain/transfer theo khả năng.
- Thu hồi session/API key bị compromise.
- Bật MFA và registrar lock.
- Khôi phục nameserver, DS và glue record đã xác minh.
- Liên hệ registrar/registry qua kênh chính thức.

### Authoritative DNS/provider

- Thu hồi credential và token.
- Khóa user không hợp lệ.
- Khôi phục record từ nguồn chuẩn.
- Bật change approval và audit.
- Kiểm tra toàn bộ zone, không chỉ A record của website.
- Tạm dừng automation có khả năng ghi đè zone.

### Recursive resolver/network

- Cô lập resolver bị compromise.
- Chuyển client sang resolver đã xác minh.
- Chặn đường truy cập tới resolver độc hại theo policy.
- Khôi phục DHCP/VPN/router config.
- Phối hợp ISP hoặc network provider nếu có route hijack.

### Endpoint

- Cô lập thiết bị có malware.
- Thu hồi proxy/VPN profile độc hại.
- Khôi phục hosts file và resolver config từ baseline tin cậy.
- Reimage thiết bị nếu không thể xác nhận integrity.

### Browser/application

- Tạm dừng login hoặc giao dịch nhạy cảm trên host chưa xác minh nếu cần.
- Cảnh báo người dùng không nhập credential khi certificate bất thường.
- Revoke session/token nghi bị lộ.
- Rotate OAuth client secret/API key nếu có bằng chứng exposure.
- Tạm vô hiệu hóa luồng bị chuyển hướng nếu cần bảo vệ người dùng.

Không xóa dữ liệu browser hàng loạt hoặc buộc người dùng cài certificate mới trước khi xác minh nguyên nhân và phạm vi.

## 16. Bước 10 — Khôi phục DNS và xác minh

Khôi phục không chỉ là thấy website mở được. Phải xác minh delegation, record, DNSSEC, TLS, nội dung và luồng nghiệp vụ.

### DNS recovery checklist

1. Registrar account và contact đã được bảo vệ.
2. Nameserver delegation khớp cấu hình chuẩn.
3. Glue record đúng nếu có.
4. DS/DNSKEY chain hợp lệ nếu dùng DNSSEC.
5. A/AAAA/CNAME và record ứng dụng đã được review.
6. MX/TXT/CAA và record liên quan cũng được kiểm tra.
7. TTL và cache propagation được theo dõi.
8. Nhiều resolver độc lập trả kết quả phù hợp.
9. Authoritative query khớp zone đã phê duyệt.
10. Audit log không còn thay đổi trái phép.

### TLS recovery checklist

- Certificate có SAN đúng.
- Chain được browser tin cậy.
- Private key mới nếu key cũ nghi bị lộ.
- Certificate bất thường được điều tra/revoke.
- CDN/edge/region đều phục vụ certificate đúng.
- HSTS policy không bị downgrade.
- Không yêu cầu người dùng bypass warning.

### Browser recovery checklist

- URL giữ hostname đúng.
- Không còn redirect ngoài dự kiến.
- DevTools Network cho thấy endpoint đúng.
- CSP/security header đúng.
- Không có script hoặc iframe lạ.
- Service worker script URL và scope đúng.
- Cache Storage không còn response độc hại.
- Cookie/session cũ đã được revoke nếu cần.

### Kiểm tra nội dung và code

DNS/TLS được khôi phục không đảm bảo origin chưa từng phục vụ nội dung độc hại. So sánh static assets, build hash, deployment artifact, CSP header và application code với bản phát hành tin cậy. Điều tra khả năng script hoặc service worker đã được cập nhật trong thời gian sự cố.

## 17. Làm sạch browser state và session

Thực hiện sau khi đã bảo toàn chứng cứ và xác định phạm vi.

### Session invalidation

- Revoke server-side session.
- Rotate session identifier.
- Thu hồi refresh token và access token khi cần.
- Thu hồi authorization grant có nguy cơ.
- Bắt buộc xác thực lại từ thiết bị/mạng sạch.
- Theo dõi login bất thường và MFA fatigue.

### Cookie cleanup

Xóa cookie liên quan theo host/domain/path sau khi session server-side đã bị revoke. Xóa cookie phía client mà không revoke server-side có thể không vô hiệu hóa credential đã bị sao chép.

### Web Storage và IndexedDB

Nếu origin có thể đã phục vụ JavaScript độc hại, đánh giá dữ liệu lưu phía client. Xóa hoặc reset storage theo application namespace/host bị ảnh hưởng; bảo đảm dữ liệu offline cần thiết đã được đồng bộ và evidence cần thiết đã được bảo toàn.

### Service worker và Cache Storage

1. Xác định registration theo origin/scope.
2. Kiểm tra script URL và version.
3. Unregister worker bị nghi compromise theo runbook.
4. Xóa Cache Storage entry liên quan sau khi bảo toàn evidence.
5. Reload từ origin đã xác minh.
6. Kiểm tra worker mới được cài từ build tin cậy.

Unregister service worker không tự động xóa Cache Storage. Xóa cache cũng không đảm bảo mọi tab đang mở đã ngừng dùng worker/controller cũ; kiểm tra client đang hoạt động.

### Browser profile

Chỉ reset profile khi cần thiết và đã cân nhắc tác động tới password manager, certificate, extension, evidence và dữ liệu người dùng. Trong một số sự cố endpoint, reimage thiết bị có thể đáng tin cậy hơn việc xóa thủ công một vài browser item.

## 18. Truyền thông với người dùng và đối tác

Thông điệp phải chính xác về điều đã biết và điều còn điều tra.

### Hướng dẫn người dùng trong thời gian incident

- Không bỏ qua certificate warning.
- Không nhập lại password hoặc MFA vào trang có dấu hiệu bất thường.
- Không cài certificate/profile hoặc extension theo hướng dẫn không xác minh.
- Tạm dừng giao dịch nhạy cảm nếu domain chưa được xác nhận an toàn.
- Dùng kênh hỗ trợ chính thức để báo URL, thời điểm và browser.
- Không gửi cookie/token hoặc HAR nguyên trạng.

### Thông báo khi credential có thể bị ảnh hưởng

Nếu evidence cho thấy credential/session có thể đã được gửi tới hạ tầng không tin cậy, thông báo hành động cụ thể: revoke session, đổi mật khẩu từ thiết bị sạch, reset MFA/recovery factor nếu cần và kiểm tra giao dịch bất thường.

Không yêu cầu đổi mật khẩu hàng loạt chỉ vì có một resolver trả lời sai nếu chưa đánh giá khả năng credential exposure. Ngược lại, không trì hoãn revoke khi đã có bằng chứng session bị thu thập.

### Registrar/DNS provider/CA/ISP

Chuẩn bị:

- Domain và zone ID.
- Account/tenant liên quan.
- Timeline UTC.
- Record/delegation trước và sau.
- Evidence đã redaction.
- Request hỗ trợ cụ thể: freeze, restore, audit log, revoke token, validate DNSSEC hoặc certificate.

Chỉ dùng support contact từ portal/hợp đồng/kênh đã xác minh.

## 19. Giám sát sau khôi phục

Theo dõi trong khoảng thời gian phù hợp với TTL, session lifetime, mức độ ảnh hưởng và chu kỳ nghiệp vụ.

### DNS monitoring

- A/AAAA/CNAME/NS/DS/CAA/MX/TXT drift.
- Nameserver/delegation change.
- DNSSEC validation status.
- Resolver diversity và regional answer.
- TTL bất thường.
- NXDOMAIN/SERVFAIL spike.
- Query tới resolver không được phê duyệt.

### TLS monitoring

- Certificate issuance mới trong CT logs.
- SAN/issuer/validity changes.
- TLS handshake failures.
- HSTS behavior và HTTPS downgrade attempt.
- Certificate deployment consistency trên CDN/edge.

### Browser/application monitoring

- Login và MFA anomalies.
- Session creation/revocation.
- Redirect và referrer bất thường.
- CSP violation và script source mới.
- API endpoint drift.
- Service worker version.
- User reports và support cases.

### Alert có owner

Mỗi alert cần:

- Severity.
- Người/đội chịu trách nhiệm.
- Runbook.
- Threshold và suppression.
- Kênh escalation.
- Điều kiện đóng alert.

Không gửi URL có token hoặc raw cookie vào dashboard/chat.

## 20. Phân tích nguyên nhân gốc và cải tiến

Sau containment, xác định nguyên nhân gốc:

- Phishing hoặc credential reuse.
- MFA không đủ mạnh.
- API token có quyền quá rộng.
- Registrar lock không bật.
- DNS provider account không có least privilege.
- CI/CD secret bị lộ.
- Resolver/router firmware lỗi thời.
- Endpoint malware.
- DNSSEC không triển khai hoặc cấu hình sai.
- Monitoring không phát hiện record/delegation drift.
- Quy trình change approval thiếu kiểm soát.

### Cải tiến phòng ngừa

| Khu vực | Cải tiến |
| --- | --- |
| Registrar | MFA phishing-resistant, registry lock, contact verification |
| DNS provider | RBAC, scoped API token, audit log, approval cho delegation |
| DNSSEC | Signing/rollover runbook, giám sát DS/DNSKEY validation |
| Resolver | Trusted resolver, DNSSEC validation, logging và patching |
| Router/DHCP | Firmware update, admin MFA, cấu hình DNS có kiểm soát |
| Endpoint | EDR, hosts file monitoring, hạn chế local admin |
| TLS | Certificate monitoring, private key protection, CT alert |
| Browser | HSTS, CSP, hạn chế extension, secure update |
| Application | Session rotation, token scope/lifetime, anti-phishing UX |
| Operations | Change management, tabletop exercise và contact tree |

### DNSSEC không thay registrar security

DNSSEC có thể phát hiện dữ liệu DNS bị sửa mà không có chữ ký hợp lệ. Nếu attacker chiếm quyền zone signing key hoặc control plane có thể ký record mới, dữ liệu giả vẫn có thể hợp lệ theo DNSSEC. Bảo vệ registrar/provider credential vẫn cần thiết.

### HSTS không thay DNS integrity

HSTS buộc HTTPS nhưng không xác định server nào là server đúng. Kết hợp DNSSEC, TLS validation, certificate monitoring và quản trị domain mới tạo được nhiều lớp kiểm soát.

## 21. Runbook phản ứng nhanh

### 0–15 phút: xác minh và điều phối

- [ ] Ghi domain/hostname, URL đã redaction và thời điểm UTC.
- [ ] Xác định user, browser, OS, network và resolver bị ảnh hưởng.
- [ ] Kiểm tra certificate warning/fingerprint.
- [ ] Mở incident và chỉ định incident commander.
- [ ] Hướng dẫn người dùng không bypass TLS warning.
- [ ] Bảo toàn DNS answer, header và log đầu tiên.

### 15–60 phút: khoanh vùng và containment

- [ ] So sánh resolver, authoritative answer và delegation.
- [ ] Kiểm tra registrar/DNS provider audit.
- [ ] Kiểm tra DHCP/router/VPN/hosts file nếu phạm vi cục bộ.
- [ ] Thu hồi credential/API token bị compromise.
- [ ] Freeze domain change/transfer nếu cần.
- [ ] Cô lập resolver/endpoint bị compromise.
- [ ] Xác định hostname và user có thể bị ảnh hưởng.

### 1–4 giờ: khôi phục trust

- [ ] Khôi phục delegation và zone từ nguồn chuẩn.
- [ ] Xác minh DS/DNSKEY nếu dùng DNSSEC.
- [ ] Xác minh certificate và thay key nếu nghi bị lộ.
- [ ] Theo dõi TTL/propagation trên nhiều resolver.
- [ ] Kiểm tra response header, redirect và asset integrity.
- [ ] Revoke session/token theo bằng chứng exposure.

### Sau khôi phục

- [ ] Làm sạch service worker/cache/storage theo phạm vi.
- [ ] Xác nhận user có thể đăng nhập an toàn từ thiết bị sạch.
- [ ] Theo dõi DNS/TLS/login/CSP telemetry.
- [ ] Hoàn tất evidence và timeline.
- [ ] Thông báo người dùng/đối tác theo mức ảnh hưởng.
- [ ] Viết post-incident review và giao owner cải tiến.

Mốc thời gian chỉ là khung tham khảo; ưu tiên severity, evidence và quy trình incident response của tổ chức.

## 22. Ma trận kiểm thử và diễn tập

Chỉ thực hiện trên lab, staging hoặc domain do tổ chức kiểm soát. Không thử poisoning hoặc thay đổi DNS của bên thứ ba.

| Ca kiểm thử | Cách diễn tập an toàn | Kết quả mong đợi |
| --- | --- | --- |
| Record drift | Thay record trong zone lab theo change đã duyệt | Monitoring phát hiện thay đổi và owner nhận alert |
| Resolver mismatch | Dùng resolver lab trả answer khác có chủ đích | Runbook xác định resolver gây sai |
| Authoritative mismatch | Dùng zone test với record sai | So sánh recursive/authoritative tìm đúng lớp |
| Delegation change | Mô phỏng trong domain lab | Registrar/delegation alert được kích hoạt |
| DNSSEC bogus | Dùng zone lab có DS/DNSKEY không khớp | Validating resolver báo lỗi phù hợp |
| DoH difference | So sánh OS resolver và browser Secure DNS trong lab | Ghi nhận resolver thực tế từng context |
| TLS mismatch | Dùng certificate test sai hostname | Browser chặn và người dùng không bypass |
| CT monitoring | Cấp certificate test cho domain lab | CT alert phát hiện certificate mới |
| HSTS | Kiểm tra host test có policy | Browser nâng request theo policy |
| Cookie/session | Dùng account giả trong staging | Session có thể revoke và rotate |
| Storage cleanup | Tạo dữ liệu giả trong Web Storage/IDB/cache | Runbook xóa đúng dữ liệu test |
| Service worker | Deploy worker test mới trong staging | Version/scope được xác minh và cache cleanup |
| Hosts file | Thay entry trong endpoint lab | EDR/config monitoring phát hiện |
| DHCP/router | Thay resolver trong mạng lab | Network monitoring phát hiện DNS server lạ |
| Incident communication | Diễn tập thông báo certificate warning | Người dùng không nhập credential/bypass |
| Recovery | Khôi phục zone snapshot đã ký | Nhiều resolver và browser xác nhận đúng |

### Tiêu chí hoàn thành diễn tập

- Phát hiện được thay đổi trong thời gian mục tiêu.
- Xác định được lớp gây sai.
- Evidence được lưu với timestamp và nguồn.
- Registrar/DNS provider contact hoạt động.
- DNS/TLS được khôi phục theo runbook.
- Session và token được xử lý đúng threat model.
- Browser state được kiểm tra mà không làm mất evidence.
- Người dùng nhận được thông báo rõ ràng.
- Action item có owner và deadline.

## 23. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Thấy IP khác là kết luận hijacking | CDN/geo DNS có thể trả IP khác hợp lệ | So sánh resolver, CNAME, TTL, region và change record |
| Chỉ sửa A record | Delegation hoặc nameserver vẫn bị chiếm | Kiểm tra registrar, NS, DS, glue và toàn zone |
| Chỉ flush DNS cache | HTTP cache, service worker và session vẫn còn | Kiểm tra từng lớp browser/OS/resolver |
| Bypass certificate warning | Credential có thể gửi tới server không tin cậy | Dừng truy cập và xác minh TLS |
| Nghĩ HSTS ngăn mọi DNS hijacking | Server có cert hợp lệ vẫn có thể nhận kết nối | Kết hợp DNSSEC, PKI và monitoring |
| Nghĩ DoH chứng minh answer đúng | Resolver mã hóa vẫn có thể trả answer sai | Đánh giá resolver trust và DNSSEC |
| Nghĩ DNSSEC ngăn registrar takeover | Kẻ chiếm signing/control plane có thể ký dữ liệu mới | Bảo vệ registrar, key và provider account |
| Nghĩ HttpOnly ngăn server giả nhận cookie | Browser vẫn gửi cookie nếu TLS hợp lệ cho host | Revoke session và xử lý certificate/DNS |
| Chỉ thay certificate | Private key cũ hoặc DNS control plane vẫn bị lộ | Rotate key, revoke cert và khôi phục domain control |
| Xóa toàn bộ browser storage ngay | Mất evidence và dữ liệu offline | Preserve evidence rồi cleanup có phạm vi |
| Không kiểm tra MX/TXT/CAA | Email và certificate validation vẫn bị ảnh hưởng | Review toàn bộ zone record |
| Coi CT log là bằng chứng compromise tuyệt đối | Có thể là issuance hợp lệ | Correlate CA, owner, deployment và thời gian |
| Không kiểm tra Service Worker | Nội dung/cache cũ có thể tiếp tục ảnh hưởng | Kiểm tra registration, script URL và Cache Storage |
| Dùng resolver public tùy ý | Có thể phá split DNS và policy nội bộ | Dùng resolver được phê duyệt |
| Đóng incident ngay khi DNS trả đúng | Credential, TLS hoặc browser state còn rủi ro | Xác minh end-to-end và theo dõi sau khôi phục |

## 24. Câu hỏi củng cố

**Câu 1.** DNS hijacking khác HTTP redirect thế nào?

**Giải đáp:** DNS hijacking làm thay đổi nơi hostname được phân giải trước kết nối; HTTP redirect là response từ server sau khi browser đã kết nối và gửi request.

**Câu 2.** DNS trả IP khác có đồng nghĩa attacker đọc được HTTPS traffic không?

**Giải đáp:** Không. Browser xác minh certificate cho hostname. Attacker cần có khả năng hoàn tất TLS được browser tin cậy hoặc chiếm trust/endpoint; không được bypass certificate warning.

**Câu 3.** DNSSEC bảo vệ điều gì?

**Giải đáp:** Xác thực tính toàn vẹn và nguồn gốc dữ liệu DNS qua chuỗi chữ ký. Nó không mã hóa query và không ngăn quản trị zone bị chiếm quyền ký dữ liệu sai.

**Câu 4.** DoH/DoT có thay DNSSEC không?

**Giải đáp:** Không. DoH/DoT mã hóa transport tới resolver; DNSSEC xác thực dữ liệu DNS. Hai cơ chế bảo vệ các phần khác nhau.

**Câu 5.** HSTS có ngăn DNS hijacking không?

**Giải đáp:** Không. HSTS buộc HTTPS cho host đã có policy, nhưng không xác minh server đích là hạ tầng đúng nếu certificate vẫn hợp lệ.

**Câu 6.** Vì sao HttpOnly không đủ trong sự cố DNS hijacking?

**Giải đáp:** HttpOnly ngăn JavaScript đọc cookie, nhưng browser vẫn gửi cookie theo host/path/policy. Server giả mạo có TLS hợp lệ cho hostname vẫn có thể nhận request mang cookie.

**Câu 7.** Vì sao cần kiểm tra Service Worker sau sự cố?

**Giải đáp:** Service worker và Cache Storage có vòng đời riêng; nội dung hoặc cache độc hại có thể còn sau khi DNS đã được khôi phục.

**Câu 8.** Khi nào cần revoke session?

**Giải đáp:** Khi evidence cho thấy hoặc threat model xác định cookie/token có thể đã được gửi tới hạ tầng không tin cậy. Revoke server-side, không chỉ xóa cookie client.

**Câu 9.** Vì sao phải kiểm tra MX, TXT và CAA?

**Giải đáp:** DNS hijacking có thể ảnh hưởng email, domain verification, certificate issuance và các dịch vụ khác ngoài website.

**Câu 10.** Điều kiện nào cho phép đóng incident?

**Giải đáp:** DNS/delegation/DNSSEC và TLS đã được xác minh, credential/session được xử lý, browser state được kiểm tra, monitoring ổn định và các action item có owner.

## 25. Tổng kết

DNS hijacking có thể bắt nguồn từ registrar, authoritative DNS, recursive resolver, router/DHCP, endpoint hoặc đường định tuyến. Phản ứng hiệu quả phải xác định nơi đầu tiên có dữ liệu sai, bảo toàn evidence và khôi phục control plane tương ứng. Không kết luận chỉ từ một IP khác hoặc một lần truy vấn; cần so sánh resolver, authoritative answer, delegation, TTL, DNSSEC và vùng mạng.

Trong browser security, DNS là một phần của chuỗi trust. Origin được xác định bởi URL, TLS xác minh hostname và certificate, cookie được gửi theo host/policy, còn Web Storage và service worker gắn với origin/storage key. Nếu attacker phục vụ nội dung dưới hostname thật với certificate được tin cậy, script có thể hoạt động trong origin đó. HttpOnly, HSTS, DoH và DNSSEC đều có ích nhưng mỗi cơ chế có giới hạn riêng.

Runbook cần phối hợp registrar, DNS provider, network, endpoint, CA và application team. Sau khi khôi phục record và certificate, đánh giá session/token, cookie, Web Storage, IndexedDB, Cache Storage và service worker theo phạm vi. Chỉ đóng incident khi DNS/TLS/browser behavior đã ổn định, credential exposure đã được xử lý và monitoring có thể phát hiện thay đổi tái diễn.

## Tài liệu tham khảo

1. [ICANN — Domain Name Registration Data Lookup (RDAP)](https://lookup.icann.org/): tra cứu thông tin đăng ký domain công khai.
2. [ICANN — DNSSEC](https://www.icann.org/resources/pages/dnssec-2012-02-25-en): tổng quan DNSSEC và chuỗi xác thực.
3. [IETF RFC 4033 — DNS Security Introduction and Requirements](https://www.rfc-editor.org/rfc/rfc4033): kiến trúc và yêu cầu DNSSEC.
4. [IETF RFC 7858 — DNS over TLS](https://www.rfc-editor.org/rfc/rfc7858): bảo vệ transport DNS bằng TLS.
5. [IETF RFC 8484 — DNS Queries over HTTPS](https://www.rfc-editor.org/rfc/rfc8484): DNS over HTTPS.
6. [IETF RFC 6797 — HTTP Strict Transport Security](https://www.rfc-editor.org/rfc/rfc6797): HSTS và hành vi browser.
7. [CA/Browser Forum — Baseline Requirements](https://cabforum.org/working-groups/server/baseline-requirements/): yêu cầu cấp và quản lý TLS certificate.
8. [Certificate Transparency](https://certificate.transparency.dev/): giám sát certificate issuance công khai.
9. [CISA — DNS Infrastructure Tampering](https://www.cisa.gov/news-events/alerts): hướng dẫn và cảnh báo về rủi ro hạ tầng DNS.
10. [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): cấu hình TLS và xác thực kết nối.
