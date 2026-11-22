# DNS, TLS và chứng chỉ cho endpoint serverless

Ứng dụng serverless thường công khai API qua một hostname như api.example.com, nhận webhook từ đối tác hoặc gọi các dịch vụ bên ngoài. Để endpoint hoạt động ổn định và an toàn, cần cấu hình đúng DNS, TLS và chứng chỉ số. DNS giúp client tìm được địa chỉ dịch vụ; TLS bảo vệ kênh truyền và xác thực máy chủ; chứng chỉ cung cấp bằng chứng mật mã để client xác minh hostname đang kết nối.

Ba lớp này có liên quan nhưng không thay thế nhau. DNS trỏ đúng địa chỉ không chứng minh endpoint đáng tin cậy. Chứng chỉ TLS hợp lệ không tự cấp quyền gọi API. Mã hóa TLS không thay thế authorization, kiểm tra chữ ký webhook, bảo vệ dữ liệu khi lưu trữ hoặc xác thực danh tính workload giữa các dịch vụ.

Trong kiến trúc Java serverless, TLS công khai thường được kết thúc tại API gateway, load balancer, CDN hoặc ingress do cloud provider quản lý. Function nhận event sau lớp đó. Khi function gọi database, API đối tác hoặc service nội bộ, Java client lại phải xác minh chứng chỉ của endpoint đích. Vì vậy, cần thiết kế cả đường vào và đường ra, quản lý vòng đời chứng chỉ, kiểm soát DNS và có quy trình xử lý khi DNS hoặc TLS gặp lỗi.

## 1. DNS, TLS và certificate giải quyết vấn đề gì?

| Thành phần | Vai trò | Không giải quyết thay |
|---|---|---|
| DNS | Ánh xạ hostname sang địa chỉ hoặc target dịch vụ | Xác thực danh tính server, mã hóa traffic, authorization |
| TLS | Mã hóa dữ liệu trên đường truyền, bảo vệ integrity và xác thực peer theo chế độ TLS | Quyền truy cập nghiệp vụ, mã hóa dữ liệu at rest |
| Server certificate | Gắn public key với danh tính hostname hoặc tổ chức theo PKI | Xác nhận user có quyền gọi API |
| Client certificate | Cung cấp danh tính mật mã cho client trong mutual TLS | Thay thế mọi kiểm tra authorization |
| IAM / managed identity | Cấp quyền cho workload gọi tài nguyên cloud | Bảo vệ mọi kết nối mạng ngoài TLS |
| API authorization | Kiểm tra caller được phép thực hiện thao tác nào | Thay thế xác minh chứng chỉ và bảo vệ kênh |

Ví dụ, client gọi https://api.example.com. DNS phân giải hostname tới API gateway. Trong TLS handshake, gateway trình bày certificate có SAN bao phủ api.example.com và chứng minh đang sở hữu private key tương ứng. Sau khi TLS thành công, API gateway hoặc function vẫn phải xác thực token, kiểm tra scope và quyền trên resource.

Với webhook, HTTPS bảo vệ đường truyền nhưng không đủ để chứng minh payload được gửi bởi đúng đối tác. Cần xác minh chữ ký webhook hoặc cơ chế xác thực riêng theo hợp đồng tích hợp.

## 2. Đường đi của request tới serverless endpoint

Một kiến trúc public endpoint thường có dạng:

~~~mermaid
flowchart LR
    C["Browser / mobile / partner"] --> R["DNS resolver"]
    R -->|"Hostname -> endpoint"| E["CDN / API Gateway / ingress"]
    E -->|"TLS termination"| T["Managed certificate"]
    E -->|"Authenticated integration"| F["Java function"]
    F --> D[("Database / queue / storage")]
    F -->|"Outbound HTTPS; function verifies peer certificate"| P["Partner API"]
~~~

DNS thường chỉ định target của lớp ingress. Function không nhất thiết có public IP hay hostname riêng. API gateway có thể route theo path, method, stage hoặc API mapping rồi invoke function qua integration nội bộ.

Điều này tạo ra hai đường TLS cần xem xét:

- **Inbound TLS:** client hoặc đối tác kết nối tới public endpoint. Certificate thường được gắn tại gateway, load balancer, CDN hoặc platform ingress.
- **Outbound TLS:** function kết nối tới dependency bên ngoài hoặc service nội bộ. Java HTTP client, database driver hoặc SDK xác minh certificate của endpoint đích.

Nếu kiến trúc có proxy hoặc nhiều hop, xác định TLS kết thúc ở đâu và hop tiếp theo có được mã hóa lại không. Không giả định rằng TLS từ client tới gateway đồng nghĩa mọi traffic từ gateway tới backend đều được mã hóa theo cùng một cách.

## 3. Domain, hostname và DNS record

Domain được đăng ký tại registrar; authoritative DNS zone được quản lý bởi DNS provider. Hai dịch vụ có thể thuộc cùng một nhà cung cấp hoặc khác nhau. Delegation qua NS record quyết định nameserver nào có thẩm quyền trả lời cho zone.

Một số DNS record thường dùng:

| Record | Công dụng | Ví dụ |
|---|---|---|
| A | Ánh xạ hostname sang IPv4 | api.example.com → 203.0.113.10 |
| AAAA | Ánh xạ hostname sang IPv6 | api.example.com → 2001:db8::10 |
| CNAME | Alias một hostname tới hostname khác | api.example.com → gateway.provider.example |
| ALIAS / ANAME / flattening | Cung cấp alias ở apex domain theo tính năng DNS provider | example.com → service target |
| TXT | Xác minh domain, cấu hình chính sách hoặc thông tin khác | token xác minh domain |
| CAA | Giới hạn CA nào được phép phát hành certificate cho domain | Chỉ cho phép CA được tổ chức chọn |
| NS | Delegation zone tới nameserver | ns1.dns-provider.example |
| SOA | Metadata và thông tin quản trị zone | Primary NS, serial, timers |

Không phải DNS provider nào cũng hỗ trợ ALIAS hoặc ANAME. DNS chuẩn không cho phép CNAME ở zone apex (ví dụ example.com) vì apex đã có các record bắt buộc như SOA và NS. Nếu cần trỏ apex tới target dạng hostname, dùng ALIAS/ANAME hoặc CNAME flattening của nhà cung cấp DNS, hoặc thiết kế endpoint ở subdomain.

Không tạo A record bằng cách lấy một IP tạm thời từ dịch vụ serverless nếu nhà cung cấp yêu cầu alias tới hostname/target quản lý. IP có thể thay đổi khi nền tảng scale hoặc bảo trì. Dùng custom domain integration và record target mà dịch vụ cung cấp.

## 4. TTL, caching và DNS propagation

TTL (time to live) là khoảng thời gian resolver được phép cache một DNS answer. TTL thấp giúp thay đổi record được nhìn thấy sớm hơn, nhưng làm tăng số truy vấn tới authoritative DNS. TTL cao giảm query load nhưng kéo dài thời gian một số client tiếp tục dùng địa chỉ cũ sau cutover.

DNS propagation thường được mô tả như thể có một khoảng thời gian toàn cầu đồng nhất, nhưng thực tế là nhiều resolver cache answer độc lập. Thời gian quan sát thay đổi phụ thuộc TTL cũ, negative caching, resolver, client và DNS provider.

Khi chuyển endpoint:

1. Kiểm tra record hiện tại và TTL đang được công bố.
2. Nếu cần, giảm TTL trước thời điểm chuyển với đủ thời gian để cache cũ hết hạn.
3. Chuẩn bị endpoint mới, certificate và routing trước khi thay DNS.
4. Kiểm tra endpoint mới bằng hostname và TLS đúng.
5. Cập nhật record.
6. Theo dõi request trên endpoint cũ và mới trong giai đoạn chuyển tiếp.
7. Giữ endpoint cũ hoạt động đủ lâu để các resolver còn cache answer cũ được xử lý.

Giảm TTL ngay trước cutover không xóa các answer đã được resolver cache theo TTL cũ. Vì vậy, cần lên kế hoạch trước. TTL cũng không điều khiển thời gian certificate hết hạn hoặc thời gian browser cache HSTS.

Resolver có thể cache cả câu trả lời âm (negative caching) khi hostname chưa tồn tại. Nếu tạo record sau khi client đã nhận NXDOMAIN, một số client có thể tiếp tục thấy lỗi trong một khoảng thời gian. Hãy kiểm tra cả authoritative answer và recursive resolver.

Trong Java, DNS có thể được cache ở hệ điều hành, runtime JVM và HTTP client/connection pool. Một kết nối keep-alive đang mở có thể tiếp tục dùng địa chỉ cũ dù DNS record đã thay đổi. Với endpoint cần failover, quản lý connection lifetime và DNS caching theo runtime/client thực tế; không đặt TTL JVM về 0 một cách tùy tiện vì có thể làm tăng DNS traffic và latency.

## 5. DNS routing cho serverless và nhiều vùng

DNS có thể định tuyến client tới endpoint theo nhiều chính sách:

- **Simple routing:** một hostname trỏ tới một target.
- **Weighted routing:** phân chia traffic giữa nhiều target theo trọng số.
- **Latency-based routing:** chọn target có latency mạng dự kiến thấp hơn theo vị trí resolver.
- **Geolocation / geoproximity:** định tuyến theo vị trí địa lý hoặc quy tắc vùng.
- **Failover routing:** chuyển sang target dự phòng khi health check và policy cho phép.

Các chính sách này hữu ích khi triển khai nhiều Region hoặc blue/green endpoint. Tuy nhiên, DNS failover không phải chuyển đổi tức thì. Resolver cache có thể tiếp tục dùng answer cũ; health check có độ trễ; client connection có thể được giữ lâu; application retry có thể gửi lại request.

Với serverless API nhiều Region, cần đồng bộ data strategy, idempotency và event processing. Nếu DNS chuyển client từ Region A sang Region B nhưng database chỉ có ở A, endpoint mới có thể vẫn phụ thuộc vào một đường mạng xa hoặc không sẵn sàng.

Không dùng DNS weighted routing như một cơ chế canary duy nhất nếu cần kiểm soát traffic theo user/session hoặc theo request. DNS thường định tuyến ở cấp hostname và resolver cache có thể khiến phân phối thực tế khác tỷ lệ cấu hình. API gateway, CDN hoặc application-level routing có thể phù hợp hơn.

## 6. DNSSEC, CAA và quyền kiểm soát domain

DNSSEC cho phép resolver xác minh tính toàn vẹn và nguồn gốc của DNS data thông qua chữ ký số của zone. Nó giúp giảm nguy cơ giả mạo hoặc sửa đổi DNS response trên đường phân giải. DNSSEC không mã hóa truy vấn DNS, không xác thực API caller và không thay thế TLS.

CAA record cho phép domain owner chỉ định certificate authority nào được phép phát hành certificate cho domain. CAA giúp giảm nguy cơ CA không được tổ chức chấp thuận phát hành certificate, nhưng cần cấu hình đúng CA và các issuer parameter cần thiết. Nếu CAA không cho phép CA đang dùng, việc cấp mới hoặc gia hạn certificate có thể thất bại.

Các biện pháp quản trị domain:

- Bật MFA và bảo vệ tài khoản registrar/DNS provider.
- Dùng role riêng và quyền tối thiểu cho thay đổi DNS.
- Bật registry lock hoặc domain lock nếu registrar hỗ trợ.
- Ghi audit trail cho thay đổi NS, A/AAAA, CNAME, TXT và CAA.
- Bảo vệ DNS API token như secret; giới hạn zone và action.
- Dùng DNSSEC khi kiến trúc và provider hỗ trợ, quản lý rollover key có kế hoạch.
- Kiểm tra CAA trước khi yêu cầu certificate.
- Duy trì quyền sở hữu domain và quy trình khôi phục tài khoản registrar.

DNS record là cấu hình hạ tầng có ảnh hưởng lớn. Một thay đổi sai có thể chuyển traffic tới endpoint không thuộc quyền kiểm soát, làm gián đoạn API hoặc khiến certificate validation thất bại.

## 7. TLS handshake và vai trò của certificate

TLS (Transport Layer Security) thiết lập một kênh truyền được mã hóa giữa hai peer. Trong HTTPS, TLS thường xác thực server với client bằng certificate. Sau khi handshake thành công, dữ liệu ứng dụng được bảo vệ về confidentiality và integrity trên kết nối đó.

Ở mức khái niệm, handshake thực hiện các việc:

1. Client và server thương lượng phiên bản TLS và cipher suite phù hợp.
2. Client gửi hostname trong Server Name Indication (SNI) khi kết nối tới server dùng nhiều domain.
3. Server trình bày certificate chain phù hợp với hostname.
4. Client kiểm tra chain, thời hạn, hostname và trust anchor.
5. Hai bên thực hiện key exchange và xác lập session keys.
6. Traffic ứng dụng được mã hóa và kiểm tra integrity bằng các thuật toán của TLS.

TLS 1.2 và TLS 1.3 là các phiên bản thường được sử dụng hiện nay. Ưu tiên TLS 1.3 khi cả hai phía hỗ trợ; nếu cần tương thích, dùng TLS 1.2 với cipher suite an toàn. Không bật TLS 1.0/1.1 cho endpoint public mới trừ khi có ngoại lệ tương thích được phê duyệt và kiểm soát.

TLS bảo vệ kết nối tới peer mà client đã xác minh. Nếu client bỏ qua hostname verification hoặc tin mọi certificate, kênh có thể được mã hóa nhưng vẫn kết nối tới kẻ tấn công. Không bao giờ khắc phục lỗi certificate bằng cách tắt xác minh chứng chỉ trong production.

## 8. Certificate chain, SAN, wildcard và SNI

Certificate server chứa public key, subject/issuer metadata, thời hạn và extension như Subject Alternative Name (SAN). Client kiểm tra hostname cần truy cập có nằm trong SAN hay không, đồng thời xây dựng chain từ leaf certificate qua intermediate CA tới trust root mà client tin cậy.

Một số khái niệm:

- **Leaf certificate:** certificate gắn với endpoint hoặc hostname.
- **Intermediate CA:** CA trung gian ký certificate của endpoint.
- **Root CA:** trust anchor được client tin cậy.
- **SAN:** danh sách hostname hoặc danh tính mà certificate bao phủ.
- **Wildcard certificate:** certificate bao phủ hostname theo wildcard, ví dụ *.example.com.
- **SNI:** hostname client gửi trong TLS handshake để server chọn certificate phù hợp khi một IP phục vụ nhiều hostname.

Wildcard *.example.com thường bao phủ api.example.com nhưng không bao phủ example.com hoặc v2.api.example.com. Nếu cần apex domain và subdomain, certificate phải có SAN tương ứng hoặc một certificate khác.

Certificate chain cần đầy đủ intermediate certificate theo yêu cầu client. Nếu server chỉ gửi leaf certificate và thiếu intermediate, một số client có thể không xây dựng được trust chain dù certificate đã được CA phát hành đúng.

SNI giúp gateway hoặc ingress chọn đúng certificate khi nhiều custom domain cùng dùng một địa chỉ. Client cũ không gửi SNI có thể không tương thích với endpoint virtual hosting hiện đại; đây là trường hợp cần cân nhắc khi phục vụ thiết bị legacy.

## 9. Các loại certificate và lựa chọn phù hợp

| Loại | Đặc điểm | Trường hợp dùng |
|---|---|---|
| Domain Validated (DV) | CA xác minh quyền kiểm soát domain | Public API, website, webhook |
| Organization Validated (OV) | Có thêm xác minh tổ chức | Endpoint cần thông tin tổ chức theo policy |
| Extended Validation (EV) | Quy trình xác minh tổ chức nghiêm ngặt hơn | Một số yêu cầu tổ chức/tuân thủ cụ thể |
| Wildcard | Bao phủ subdomain theo wildcard | Nhiều endpoint cùng domain |
| SAN / multi-domain | Một certificate bao phủ nhiều hostname cụ thể | Gateway phục vụ nhiều domain |
| Private CA certificate | Được CA nội bộ ký | Service nội bộ, private endpoint, mTLS |
| Self-signed | Tự ký, không có trust chain công khai mặc định | Lab hoặc hệ thống kiểm thử có trust distribution riêng |

Không chọn EV chỉ vì nghĩ rằng nó tự làm API an toàn hơn. TLS security phụ thuộc vào xác minh certificate, private key, protocol, cipher, endpoint và authorization; loại validation không thay thế kiểm soát ứng dụng.

Public certificate thường được cấp qua ACME hoặc dịch vụ managed certificate của cloud/CDN. Private CA phù hợp với hệ thống nội bộ khi tổ chức quản lý được trust distribution, issuance và revocation. Không dùng self-signed certificate tùy tiện cho public endpoint vì client sẽ không tin cậy mặc định.

## 10. Quy trình cấp certificate cho custom domain

Một quy trình điển hình:

1. Chọn hostname, ví dụ api.example.com.
2. Xác định nơi kết thúc TLS: API gateway, CDN, load balancer hoặc ingress.
3. Yêu cầu certificate từ managed certificate service hoặc CA.
4. Chứng minh quyền kiểm soát domain bằng DNS validation hoặc challenge phù hợp.
5. Chờ certificate ở trạng thái issued/active.
6. Gắn certificate với custom domain tại ingress/gateway.
7. Tạo DNS record trỏ hostname tới target do provider cung cấp.
8. Cấu hình API mapping, base path hoặc route tới đúng backend.
9. Kiểm tra TLS chain, hostname, HTTP route và authorization.
10. Theo dõi renewal và expiration.

Với DNS validation, CA thường yêu cầu tạo một CNAME hoặc TXT record chứa token. Giữ record validation theo hướng dẫn của CA; một số dịch vụ cần record tồn tại để tự động gia hạn. Xóa record sau khi cấp certificate có thể khiến lần renewal tiếp theo thất bại.

Với HTTP-01 challenge, CA cần truy cập một đường dẫn xác minh trên endpoint. Cần bảo đảm gateway, redirect và firewall không chặn challenge. Wildcard certificate thường yêu cầu DNS-01 challenge vì HTTP-01 không chứng minh được quyền wildcard theo cùng cách.

Không trỏ DNS production sang gateway trước khi custom domain và certificate đã sẵn sàng nếu điều đó làm client nhận lỗi TLS hoặc route chưa tồn tại. Có thể xác minh endpoint bằng hostname staging hoặc môi trường thử nghiệm trước cutover.

## 11. TLS termination tại API gateway hoặc ingress

Trong serverless, gateway thường là nơi tiếp nhận kết nối HTTPS và giữ private key của certificate. Gateway xác minh SNI/hostname, kết thúc TLS rồi chuyển request qua integration tới function.

Ví dụ:

~~~text
Client
  |
  | HTTPS + certificate for api.example.com
  v
API Gateway / CDN / Ingress
  |
  | Authenticated integration
  v
Java Function
~~~

Managed certificate giúp provider vận hành private key, gia hạn và gắn certificate với custom domain. Private key của public endpoint không cần được copy vào JAR hoặc environment variable của function.

Nếu gateway và backend giao tiếp qua mạng công cộng hoặc một trust boundary khác, cần xem xét mã hóa hop tiếp theo và xác thực backend. Với private integration, kiểm tra network boundary, security group/firewall và identity. Không dựa vào header như X-Forwarded-Proto hoặc X-Forwarded-Host từ client nếu gateway chưa loại bỏ và ghi đè giá trị do client gửi.

Nếu function nhận thông tin client certificate hoặc identity qua header do gateway chuyển tiếp, chỉ tin metadata được gateway xác thực và bảo vệ. Chặn client tự gửi header cùng tên; gateway phải xóa header đầu vào và tạo header mới sau khi xác minh.

## 12. Custom domain cho các nền tảng serverless

Các nền tảng khác nhau có mô hình custom domain riêng. Dù tên tài nguyên khác nhau, quy trình chung vẫn là: cấp certificate, xác minh domain, liên kết hostname với ingress/API và cấu hình DNS.

| Nền tảng | Điểm kết thúc TLS thường gặp | Cấu hình cần chú ý |
|---|---|---|
| AWS API Gateway + Lambda | API Gateway custom domain hoặc CloudFront | Certificate phù hợp với endpoint type/Region, API mapping, DNS alias |
| Azure Functions | App Service front end/custom domain hoặc ingress theo hosting model | Custom domain, managed certificate hoặc certificate binding, DNS validation |
| Google Cloud Functions / Cloud Run functions | HTTPS endpoint do nền tảng quản lý hoặc custom domain qua lớp ingress phù hợp | Domain mapping hoặc load balancer, managed certificate, DNS record |
| Container-based serverless | Managed ingress/load balancer | Certificate binding, hostname routing và revision traffic |

Một số giới hạn là đặc thù nhà cung cấp. Ví dụ, dịch vụ có thể yêu cầu certificate ở một Region cụ thể, loại endpoint cụ thể hoặc một resource khác đứng trước function để hỗ trợ custom domain. Hãy kiểm tra tài liệu của đúng API gateway, Region và hosting plan trước khi tạo certificate.

Không giả định Function URL hoặc default hostname của một nền tảng có thể nhận custom domain trực tiếp. Trong một số kiến trúc cần đặt API gateway, CDN hoặc load balancer phía trước để quản lý domain, certificate, WAF và routing.

## 13. Gia hạn, rotation và thu hồi certificate

Certificate có thời hạn. Nếu hết hạn, client tuân thủ TLS sẽ từ chối kết nối hoặc hiển thị cảnh báo. Gia hạn cần được coi là quy trình vận hành quan trọng giống deploy code.

Với managed certificate:

- Giữ DNS validation record theo hướng dẫn provider.
- Bảo đảm domain vẫn trỏ và đáp ứng điều kiện gia hạn của dịch vụ.
- Theo dõi trạng thái renewal và expiration.
- Cảnh báo trước ngày hết hạn đủ lâu để xử lý lỗi.
- Kiểm tra certificate mới đã được gắn vào đúng domain/slot/region.
- Xác minh chain sau khi gia hạn.

Với certificate tự quản lý:

1. Yêu cầu certificate mới trước khi certificate cũ hết hạn.
2. Cài certificate và private key mới vào secret store hoặc ingress.
3. Xác minh SAN, chain và key pair khớp nhau.
4. Chuyển endpoint sang certificate mới.
5. Kiểm thử client thực tế.
6. Giữ certificate cũ trong khoảng rollback hợp lý.
7. Thu hồi certificate cũ nếu bị lộ hoặc không còn được phép sử dụng.
8. Xóa private key cũ theo quy trình quản lý khóa.

Rotation nên có giai đoạn overlap để client và server không bị lệch trust. Với mTLS, cập nhật trust bundle theo hướng chấp nhận cả certificate cũ và mới trong thời gian chuyển tiếp, sau đó loại bỏ CA hoặc client certificate cũ khi mọi client đã hoàn tất rotation.

Không đợi tới ngày hết hạn mới bắt đầu gia hạn. Theo dõi certificate expiry bằng service metric, inventory hoặc scanner được phê duyệt. Cảnh báo cần chỉ rõ hostname, resource, issuer, expiry date và owner.

## 14. Bảo vệ private key và certificate material

Certificate public không phải secret, nhưng private key phải được bảo vệ nghiêm ngặt. Nếu private key bị lộ, attacker có thể giả mạo endpoint cho tới khi certificate bị thu hồi hoặc hết hạn và client cập nhật trust.

Nguyên tắc:

- Ưu tiên managed certificate và private key management của provider khi phù hợp.
- Không commit private key, PFX password hoặc truststore password vào repository.
- Không đưa private key vào Lambda/Function package hoặc image.
- Dùng Key Vault, Secrets Manager, HSM hoặc certificate store được quản lý theo kiến trúc.
- Giới hạn quyền đọc/export private key; bật audit và alert.
- Mã hóa secret at rest và giới hạn thời gian cache trong process.
- Dùng quyền riêng cho automation cấp/gia hạn certificate.
- Không gửi private key qua chat, log, artifact hoặc pipeline output.

Nếu platform yêu cầu upload PFX/PEM, kiểm tra file có private key, certificate chain và password đúng. Chỉ cấp quyền cho pipeline hoặc identity triển khai cần thực hiện thao tác đó. Nếu managed service có thể giữ key không exportable, ưu tiên cách này để giảm phạm vi lộ khóa.

## 15. Mutual TLS (mTLS) cho API và webhook

TLS thông thường xác thực server với client. **Mutual TLS** yêu cầu cả client và server trình bày certificate để xác thực lẫn nhau trong handshake.

mTLS có thể phù hợp khi:

- Chỉ các đối tác hoặc thiết bị có certificate được cấp mới được kết nối.
- API B2B cần danh tính máy ở tầng kết nối.
- Service-to-service trong môi trường có PKI và trust distribution được quản lý.
- Gateway cần từ chối client không thuộc trust bundle trước khi chuyển request vào function.

mTLS không tự xác định user hoặc quyền nghiệp vụ. Sau khi client certificate hợp lệ, gateway/function vẫn cần ánh xạ subject/SAN hoặc certificate identity sang partner/client record, kiểm tra trạng thái thu hồi và authorization theo API/resource.

Quản lý mTLS cần có:

- CA hoặc trust bundle được kiểm soát.
- Quy trình cấp, gia hạn, rotation và thu hồi client certificate.
- Mapping certificate identity với client/tenant.
- Giới hạn thuật toán và key size theo policy.
- Theo dõi certificate sắp hết hạn và client bị từ chối.
- Cách cập nhật trust bundle mà không làm gián đoạn toàn bộ đối tác.

Nếu dùng API gateway managed mTLS, xác minh chính xác header/context mà gateway cung cấp cho backend và cách chặn header giả mạo từ client. Nếu gateway kết thúc mTLS, TLS client identity cần được chuyển tiếp qua kênh tin cậy tới function.

## 16. TLS cho outbound request từ Java function

Khi Java function gọi HTTPS endpoint công khai, JDK thường dùng truststore mặc định để xác minh certificate chain và hostname. Nếu endpoint dùng certificate từ public CA được JVM tin cậy, thường không cần tự cấu hình SSLContext.

Với endpoint nội bộ dùng private CA, cần đưa CA certificate vào truststore được quản lý và cấu hình HTTP client sử dụng truststore đó. Không cài leaf certificate tạm thời nếu có thể trust private root/intermediate CA theo chính sách PKI; điều này giúp rotation leaf certificate dễ hơn.

Ví dụ tạo HttpClient với PKCS12 truststore:

~~~java
char[] password = System.getenv("TLS_TRUSTSTORE_PASSWORD")
        .toCharArray();

KeyStore trustStore = KeyStore.getInstance("PKCS12");

try (InputStream input = Files.newInputStream(
        Path.of("/mnt/secrets/partner-truststore.p12"))) {
    trustStore.load(input, password);
}

TrustManagerFactory trustManagerFactory =
        TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
        );
trustManagerFactory.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(
        null,
        trustManagerFactory.getTrustManagers(),
        new SecureRandom()
);

HttpClient client = HttpClient.newBuilder()
        .sslContext(sslContext)
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://partner.internal.example"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);
~~~

Ví dụ giả định file truststore đã được mount hoặc tải an toàn từ secret/configuration store, và các import cùng exception handling đã được bổ sung. Truststore này cần chứa đầy đủ CA mà client phải tin cậy. Nếu chỉ chứa private CA mà ứng dụng còn gọi public endpoint, hãy dùng truststore kết hợp phù hợp hoặc cấu hình client riêng theo nhóm endpoint; không vô tình loại bỏ các public trust root cần thiết.

JDK HttpClient thực hiện hostname verification mặc định. Không tắt hostname verification và không tạo TrustManager chấp nhận mọi certificate để “sửa nhanh” lỗi PKIX. Nếu certificate không hợp lệ, sửa chain, hostname, truststore hoặc DNS target.

## 17. Java client certificate và outbound mTLS

Nếu partner yêu cầu client certificate, Java client cần keystore chứa client certificate cùng private key. Truststore vẫn dùng để xác minh certificate của server; keystore dùng để chứng minh danh tính client. Hai vai trò khác nhau.

Ví dụ khởi tạo SSLContext với cả KeyManager và TrustManager:

~~~java
KeyStore clientKeyStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(
        Path.of("/mnt/secrets/client-identity.p12"))) {
    clientKeyStore.load(input, keyPassword);
}

KeyManagerFactory keyManagerFactory =
        KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm()
        );
keyManagerFactory.init(clientKeyStore, keyPassword);

KeyStore serverTrustStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(
        Path.of("/mnt/secrets/server-truststore.p12"))) {
    serverTrustStore.load(input, trustPassword);
}

TrustManagerFactory trustManagerFactory =
        TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
        );
trustManagerFactory.init(serverTrustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(
        keyManagerFactory.getKeyManagers(),
        trustManagerFactory.getTrustManagers(),
        new SecureRandom()
);
~~~

Đây là phần khởi tạo TLS; dùng SSLContext đó trong HttpClient như ví dụ trước. Private key password và truststore password phải được lấy từ secret manager, không hardcode. Không log nội dung keystore hoặc private key.

Với nhiều đối tác có certificate khác nhau, cân nhắc client riêng theo partner hoặc chọn identity theo policy rõ ràng. Không tự động gửi cùng một client certificate tới mọi host; điều đó có thể làm lộ danh tính máy cho bên không liên quan.

## 18. Java truststore, keystore và lỗi thường gặp

| Thành phần | Chứa gì | Dùng để |
|---|---|---|
| Truststore | CA certificate hoặc certificate được tin cậy | Xác minh certificate của server/peer |
| Keystore | Private key và certificate chain của client/server | Trình bày danh tính trong TLS, ký hoặc giải mã theo mục đích |
| PEM | Dạng text cho certificate/key | Trao đổi certificate và key theo định dạng hỗ trợ |
| PKCS12 (.p12/.pfx) | Container có thể chứa certificate, chain và private key | Lưu identity hoặc trust material có password |
| JKS | Java KeyStore format | Lưu key/certificate trong Java ecosystem |

Một số lỗi thường gặp:

- **PKIX path building failed:** client không xây dựng được chain tới trust root; có thể thiếu intermediate hoặc CA không nằm trong truststore.
- **No subject alternative DNS name matching:** hostname URL không có trong SAN của certificate.
- **Certificate expired / not yet valid:** thời hạn certificate không hợp lệ hoặc clock của môi trường sai.
- **Received fatal alert: handshake_failure:** protocol, cipher, client certificate hoặc cấu hình handshake không tương thích.
- **unknown_ca:** peer không tin CA của certificate bên kia, thường gặp trong mTLS.
- **bad_certificate:** certificate sai định dạng, hết hạn, thiếu key usage hoặc không đạt policy.
- **Connection timed out:** có thể là DNS, route, firewall, security group, proxy hoặc endpoint không phản hồi; không nhất thiết là lỗi certificate.

Không giải quyết các lỗi này bằng trust-all. Hãy xác định peer nào gửi lỗi, kiểm tra hostname, chain, truststore, thời gian hệ thống, protocol và route mạng.

## 19. DNS và TLS trong private networking

Không phải endpoint serverless nào cũng public. Function có thể gọi database private, internal API, service trong VPC/VNet hoặc private endpoint của dịch vụ cloud.

Private DNS zone cho phép hostname nội bộ phân giải thành địa chỉ private trong network được liên kết. Split-horizon DNS có thể trả lời khác nhau cho cùng hostname tùy resolver ở public hay private network.

Khi cấu hình private DNS:

- Liên kết zone với đúng VPC/VNet hoặc network cần truy cập.
- Xác minh resolver của function có thể truy vấn zone.
- Kiểm tra DNS forwarding nếu dùng custom DNS server.
- Tránh hostname trùng hoặc record shadowing giữa public và private zone.
- Dùng hostname nằm trong SAN của certificate, kể cả khi DNS trả về IP private.
- Không dùng IP trực tiếp nếu certificate được cấp cho hostname.
- Kiểm tra route, security group, firewall, NACL và private endpoint policy.

DNS private không phải cơ chế authorization. Một workload resolve được hostname không có nghĩa nó được phép gọi service. Cần IAM/managed identity, token hoặc mTLS cùng network policy phù hợp.

Với private CA, client Java phải trust CA đó. Private DNS và private certificate cần được quản lý cùng nhau: hostname có thể resolve đúng nhưng TLS vẫn thất bại nếu SAN hoặc trust chain không khớp.

## 20. DNS caching, connection reuse và serverless runtime

Execution environment serverless có thể được tái sử dụng. Java function thường tái sử dụng HTTP client và connection pool để giảm chi phí handshake, DNS lookup và TCP setup. Điều này có lợi cho latency nhưng cần xử lý endpoint thay đổi hoặc connection idle bị đóng.

Một số tình huống:

- DNS record đổi nhưng JVM hoặc resolver còn cache answer cũ.
- Connection keep-alive còn mở tới IP cũ.
- Gateway đóng idle connection; lần gọi tiếp theo nhận reset.
- Certificate được rotation nhưng client giữ connection TLS cũ trong thời gian dài.
- Private DNS zone được cập nhật nhưng runtime mới chưa resolve theo record mới.

Các nguyên tắc:

- Tái sử dụng HTTP client thread-safe giữa các invocation khi phù hợp.
- Cấu hình connection idle timeout và maximum lifetime theo dependency.
- Retry an toàn với lỗi connection reset, nhưng chỉ cho operation idempotent hoặc có idempotency key.
- Cho phép client tạo connection mới sau DNS hoặc certificate rotation.
- Đặt connect, read và overall timeout.
- Không cache IP vĩnh viễn trong application code.
- Theo dõi DNS failure, connection pool exhaustion và TLS handshake error.

Không giảm DNS cache TTL một cách cực đoan để xử lý mọi sự cố. Trước tiên xác định resolver nào cache answer, connection pool có giữ socket cũ không và provider có hỗ trợ hostname target ổn định hay không.

## 21. HSTS, redirect và các header bảo mật cho public endpoint

HTTP Strict Transport Security (HSTS) cho phép server yêu cầu browser chỉ truy cập domain qua HTTPS trong một thời gian. HSTS giúp giảm nguy cơ downgrade hoặc truy cập HTTP ngoài ý muốn, nhưng chỉ có tác dụng với user agent hỗ trợ và sau khi nhận header hợp lệ.

Ví dụ header:

~~~text
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Chỉ dùng includeSubDomains khi mọi subdomain liên quan đều hỗ trợ HTTPS ổn định. Không bật preload hoặc thời hạn dài mà chưa kiểm tra toàn bộ domain tree; cấu hình sai có thể khiến subdomain không truy cập được.

Các thực hành khác:

- Redirect HTTP sang HTTPS tại gateway/ingress.
- Không để backend tạo absolute URL HTTP do tin forwarded header giả mạo.
- Cấu hình cookie Secure, HttpOnly và SameSite phù hợp nếu endpoint dùng cookie.
- Cấu hình CORS theo origin cần thiết; CORS không phải authorization.
- Dùng WAF/rate limit khi endpoint public cần chống abuse.
- Chỉ bật TLS protocol và cipher suite được tổ chức chấp thuận.
- Không cho phép certificate mismatch hoặc mixed content ở client browser.

Redirect HTTP sang HTTPS không mã hóa request đầu tiên nếu client gửi dữ liệu nhạy cảm qua HTTP. Với API nhạy cảm, yêu cầu client dùng HTTPS ngay từ đầu và cân nhắc HSTS cho browser traffic.

## 22. Kiểm thử DNS, TLS và certificate trước phát hành

Một số công cụ kiểm tra hữu ích:

### Kiểm tra DNS

~~~bash
dig api.example.com A
dig api.example.com AAAA
dig api.example.com CNAME
dig +trace api.example.com
nslookup api.example.com
~~~

Kiểm tra authoritative nameserver và recursive resolver khi kết quả khác nhau. Với CAA:

~~~bash
dig example.com CAA
~~~

Với private DNS, chạy truy vấn từ đúng VPC/VNet hoặc môi trường có cùng resolver path; kiểm tra từ laptop public không chứng minh private zone hoạt động.

### Kiểm tra TLS handshake và certificate chain

~~~bash
openssl s_client \
  -connect api.example.com:443 \
  -servername api.example.com \
  -showcerts \
  -verify_return_error
~~~

Tham số -servername gửi SNI. Kiểm tra subject/SAN, issuer, thời hạn, chain và kết quả verify. Nếu cần kiểm tra HTTP response:

~~~bash
curl -Iv https://api.example.com/health
~~~

Không dùng curl -k như cách xác minh production; tùy chọn đó bỏ qua certificate verification và có thể che giấu lỗi.

### Kiểm tra Java keystore

~~~bash
keytool -list -v \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
~~~

Không đưa password vào command line hoặc shell history. Dùng prompt hoặc secret handling phù hợp. Không in private key ra terminal hoặc log.

### Kịch bản test cần có

1. Hostname đúng và certificate hợp lệ.
2. Hostname không nằm trong SAN phải thất bại.
3. Certificate hết hạn hoặc chưa có hiệu lực phải bị từ chối.
4. Chain thiếu intermediate phải được phát hiện.
5. CA không tin cậy phải bị từ chối.
6. mTLS thiếu hoặc sai client certificate phải bị từ chối.
7. DNS record mới và cũ được kiểm tra trong giai đoạn cutover.
8. Private DNS được kiểm tra từ đúng network.
9. Certificate rotation không làm gián đoạn client.
10. Endpoint vẫn kiểm tra authorization sau khi TLS thành công.

## 23. Xử lý sự cố DNS và TLS

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| NXDOMAIN | Thiếu record, sai zone/delegation hoặc negative cache | Kiểm tra NS, authoritative answer, record và resolver cache |
| SERVFAIL | DNSSEC validation, authoritative DNS hoặc upstream lỗi | Kiểm tra DNSSEC chain, nameserver và SOA |
| DNS trả target cũ | TTL/cache chưa hết hoặc connection pool giữ socket | Kiểm tra TTL cũ, resolver và connection lifetime |
| Certificate mismatch | SAN không bao phủ hostname hoặc SNI sai | Kiểm tra URL hostname, SNI và certificate binding |
| Certificate expired | Renewal thất bại hoặc certificate cũ chưa được thay | Kiểm tra expiry, validation record và deployment binding |
| PKIX path building failed | CA không tin cậy hoặc thiếu intermediate | Kiểm tra chain và Java truststore |
| mTLS unknown_ca | Client/server không trust CA phía kia | Kiểm tra trust bundle và certificate chain |
| Handshake timeout | Network, proxy, protocol hoặc peer chậm | Kiểm tra route, firewall, TLS version và endpoint |
| API trả 403 sau TLS | Authorization, WAF hoặc policy từ chối | Kiểm tra token, scope, resource policy và gateway logs |
| Renewal không chạy | DNS validation record bị xóa hoặc CAA chặn CA | Kiểm tra CNAME/TXT validation, CAA và issuer |

Phân biệt lỗi phân giải DNS, lỗi TCP connection, lỗi TLS handshake và lỗi HTTP authorization. Chúng xảy ra ở các tầng khác nhau; xem đúng log và metric giúp tránh thay đổi certificate khi nguyên nhân thực tế là route hoặc IAM.

## 24. Checklist DNS và TLS cho production

Trước khi công khai endpoint serverless, hãy xác nhận:

1. Domain thuộc quyền kiểm soát của tổ chức và registrar account được bảo vệ?
2. Authoritative DNS zone, NS delegation và record target đã đúng?
3. A/AAAA/CNAME/ALIAS phù hợp với loại endpoint và apex/subdomain?
4. TTL phù hợp với kế hoạch cutover và failover?
5. DNSSEC và CAA có được cấu hình theo policy không?
6. Certificate SAN bao phủ mọi hostname cần phục vụ?
7. Certificate chain có đầy đủ intermediate và trust anchor phù hợp?
8. TLS 1.2/1.3 và cipher suite được cấu hình theo baseline?
9. TLS termination point đã được xác định rõ?
10. Các hop gateway-to-backend có yêu cầu TLS hoặc private networking riêng?
11. Managed certificate có tự gia hạn và validation record còn tồn tại?
12. Certificate expiry có metric/cảnh báo và owner xử lý?
13. Private key được giữ trong managed certificate service hoặc secret store?
14. mTLS có trust bundle, identity mapping, rotation và revocation process?
15. Java client xác minh chain và hostname, không dùng trust-all?
16. Private CA được phân phối qua truststore được quản lý?
17. Private DNS, resolver, VPC/VNet link và egress route đã được kiểm tra?
18. HTTP client connection pool và DNS cache có phù hợp với failover/rotation?
19. HSTS, redirect, cookie và security headers được cấu hình đúng nếu có browser client?
20. Có test DNS, TLS, certificate rotation, mTLS, authorization và cutover?

## Kết luận

DNS giúp client tìm được endpoint; TLS thiết lập kênh truyền được mã hóa và xác thực peer; certificate cung cấp danh tính mật mã cho hostname hoặc client. Trong serverless, public TLS thường kết thúc tại gateway, CDN hoặc ingress do provider quản lý, trong khi Java function vẫn phải xác minh TLS khi gọi dependency bên ngoài hoặc service nội bộ.

Hãy quản lý custom domain, DNS record, TTL, CAA và DNSSEC như tài nguyên hạ tầng; cấp certificate đúng hostname, giữ chain đầy đủ, tự động gia hạn và bảo vệ private key. Với Java, dùng truststore/keystore theo đúng vai trò, giữ hostname verification, cấu hình timeout và quản lý connection reuse. Cuối cùng, kết hợp TLS với IAM/managed identity, authorization và kiểm tra chữ ký webhook để bảo vệ toàn bộ request từ lúc phân giải tên miền tới khi function thực hiện nghiệp vụ.

