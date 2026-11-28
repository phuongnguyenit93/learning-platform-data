# Kiểm kê certificate và phát hiện certificate sắp hết hạn

Một dịch vụ có thể chạy ổn định trong nhiều tháng rồi bất ngờ ngừng phục vụ HTTPS, VPN hoặc xác thực Wi-Fi chỉ vì **certificate (chứng chỉ số) hết hạn**. Mức độ ảnh hưởng có thể vượt ra ngoài một website: API đối tác từ chối kết nối, VPN gateway không xác thực được, thiết bị không vào được mạng 802.1X, hoặc microservice thất bại khi thiết lập mutual TLS (mTLS). Khó khăn lớn nhất thường không phải cách đọc ngày hết hạn, mà là **biết mọi certificate đang tồn tại ở đâu, cái nào thực sự đang được sử dụng, ai chịu trách nhiệm và thay thế nó thế nào trước khi gây gián đoạn**.

**Kiểm kê certificate** là quá trình ghi nhận, đối chiếu và duy trì thông tin vòng đời của chứng chỉ: danh tính, mục đích, chủ sở hữu, điểm triển khai, quan hệ CA, thời hạn, trạng thái và kế hoạch gia hạn. **Phát hiện certificate sắp hết hạn** là xây dựng cơ chế quan sát và cảnh báo có đủ thời gian hành động, sau đó xác minh rằng **chứng chỉ mới đã thực sự phục vụ ở mọi điểm kết thúc kết nối**, không chỉ đã được cấp phát trong hệ thống PKI.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, quản trị certificate liên kết trực tiếp với TLS, VPN, firewall, NAC/802.1X, IDS/IPS, bảo vệ DNS, Wi-Fi, phân đoạn mạng và cloud. Bài này tập trung vào **quan sát, vận hành phòng thủ, tự động hóa có kiểm soát và phản ứng sự cố**. Không yêu cầu truy cập private key của hệ thống thật hoặc thực hiện quét mạng ngoài phạm vi được cấp phép.

> **Nguyên tắc cốt lõi:** Certificate còn hạn trên CA/secret store **không chứng minh** dịch vụ đang dùng certificate ấy; một HTTPS probe PASS từ một địa điểm **không chứng minh** mọi node, hostname, client và đường dự phòng đều PASS.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **certificate inventory**, **asset inventory**, **certificate discovery** và **certificate lifecycle management**.
2. Đọc đúng những trường X.509 liên quan như **Subject, Subject Alternative Name (SAN), Issuer, Serial, Not Before, Not After, fingerprint và Extended Key Usage**.
3. Phân biệt **leaf certificate, intermediate CA, root/trust anchor, server certificate, client certificate** và các trường hợp certificate không dùng cho TLS.
4. Xác định nguồn kiểm kê từ **CA/PKI, load balancer, CDN, reverse proxy, API gateway, VPN, RADIUS/NAC, endpoint, Kubernetes và cloud certificate manager**.
5. Thiết kế **schema kiểm kê, quan hệ certificate–service–endpoint–owner và cơ chế đối soát desired state với observed state**.
6. Tính thời gian còn hiệu lực, phân loại rủi ro, cấu hình **cảnh báo nhiều cấp với owner/escalation** và tránh báo động trùng.
7. Sử dụng các công cụ **OpenSSL, PowerShell, keytool** theo hướng chỉ đọc để thu thập metadata được phép.
8. Thiết kế **quy trình gia hạn, triển khai, kiểm chứng, thu hồi và rollback** mà không làm lộ private key.
9. Điều tra những tình huống **gia hạn thành công nhưng dịch vụ vẫn trình bày chứng chỉ cũ**, chứng chỉ hết hạn ở node dự phòng hoặc trust chain sai.

## 2. Certificate giải quyết vấn đề gì trong mạng?

Một certificate X.509 chứa **khóa công khai, danh tính hoặc các thuộc tính được chứng nhận, thời hạn, thuật toán/chữ ký và các extension**, được ký bởi một CA hoặc có dạng phù hợp với mô hình tin cậy đang sử dụng. Client dựa vào **chuỗi tin cậy và chính sách xác minh** để quyết định có tin khóa công khai đó cho một mục đích nhất định hay không.

~~~text
         PKI / CA hierarchy
                 |
           Root / Trust anchor
                 |
          Intermediate CA
                 |
       +---------+----------+
       |                    |
  TLS server cert      Client/workload cert
       |                    |
  HTTPS/VPN/API         mTLS/802.1X/EAP-TLS
       |                    |
    Server identity     Client identity
       \                    /
         Policy + authorization
~~~

**Certificate không tự cấp quyền nghiệp vụ.** Một client mTLS có chứng chỉ hợp lệ có thể vẫn bị từ chối một API nếu không có authorization. Tương tự, một HTTPS server có certificate hợp lệ vẫn có thể chạy dịch vụ bị lỗi hoặc bị firewall từ chối.

### Những loại certificate trong phạm vi kiểm kê

| Loại | Ví dụ nơi dùng | Cần kiểm kê điều gì? |
|---|---|---|
| **TLS server leaf** | Website, API, proxy, database, VPN portal | SAN, issuer, expiry, điểm kết thúc TLS, trust policy |
| **TLS client leaf** | mTLS API client, service mesh, máy/ứng dụng được quản lý | Định danh client, phạm vi cấp, nơi cài, chủ sở hữu, rotation |
| **802.1X/EAP-TLS** | Laptop, thiết bị Wi-Fi, RADIUS authentication server | Certificate client và server, CA trust, onboarding/offboarding |
| **VPN peer/gateway** | IPsec/IKEv2 hoặc cổng VPN dùng certificate | Peer identity, chain, expiry, rollover và fallback |
| **Intermediate CA** | Issuing CA doanh nghiệp, cấp leaf | Hiệu lực, khả năng phát hành, path building, các CA phụ thuộc |
| **Root/trust anchor** | Enterprise trust store, thiết bị, runtime | Phân phối trust, vòng đời, thay thế có kiểm soát |
| **Các loại X.509 khác** | S/MIME, code signing, ký thiết bị/hệ thống | Chính sách riêng; không gộp tất cả vào TLS server testing |

**SSH host keys, API tokens, OAuth access tokens và mật khẩu không mặc nhiên là X.509 certificates**. Chúng cũng cần quản trị vòng đời nhưng phải đưa vào **inventory/secret-management riêng hoặc mô hình chung có loại đối tượng rõ ràng**, tránh áp một phép kiểm tra Not After cho mọi bí mật.

## 3. Bốn lớp dữ liệu: issued, stored, deployed và observed

Một hệ thống PKI có thể phát hành certificate nhưng chứng chỉ ấy chưa bao giờ được gắn lên dịch vụ. Ngược lại, một ứng dụng có thể đang sử dụng certificate không được ghi trong kho trung tâm.

| Trạng thái cần quan sát | Ví dụ nguồn | Câu hỏi được trả lời |
|---|---|---|
| **Issued** – đã phát hành | CA database, ACME records, PKI portal | CA đã cấp certificate nào, khi nào, cho chủ thể nào? |
| **Stored** – đã lưu trữ | Secret manager, certificate store, keystore, vault | Certificate nào có mặt ở kho hoặc thiết bị? |
| **Deployed** – đã gắn cấu hình | IaC, ingress TLS secret reference, LB listener, gateway policy | Dịch vụ được cấu hình dùng certificate nào? |
| **Observed/served** – đang được trình bày | TLS handshake ở endpoint, synthetic probe, gateway telemetry | Client thật được trình bày certificate nào trên đường kết nối này? |

~~~text
    [PKI / CA issued certificates]
                  |
                  v
       [Secret / Certificate Store]
                  |
                  v
       [Deployment / Config Owner]
          /           |           \
         v            v            v
     [Edge]       [Origin]     [Service mesh]
         |            |            |
         +------------+------------+
                      |
                 [Live probes]
                      |
                 Compare / Alert
                      |
               [Service + Owner]
~~~

**Khoảng trống quan trọng nhất:** CA báo đã cấp chứng chỉ mới, nhưng **node đang phục vụ hoặc đường dự phòng vẫn trình bày certificate cũ**. Vì vậy chỉ đếm chứng chỉ trong kho hoặc chỉ xem ngày ở CA là chưa đủ để bảo vệ availability.

### Certificate không có nghĩa là một endpoint

- Một wildcard/multi-SAN certificate có thể phục vụ **nhiều hostname**.
- Một hostname có thể đi tới **nhiều địa chỉ IP, POP/CDN edge, load balancer và origin**.
- Một gateway có thể có **nhiều certificate được chọn theo SNI/ALPN hoặc chính sách**.
- Một service có thể dùng **server certificate và client certificate** ở các luồng khác nhau.
- Một file keystore có thể chứa nhiều alias; chỉ một alias được app chọn.

Mô hình inventory phải hỗ trợ quan hệ **nhiều–nhiều** và giữ lịch sử theo thời gian.

## 4. Những trường X.509 cần đọc chính xác

| Trường | Ý nghĩa | Lưu ý khi làm inventory |
|---|---|---|
| **Subject** | Danh tính/thuộc tính chủ thể theo định dạng của chứng chỉ | Không coi CN đủ để xác minh hostname HTTPS hiện đại |
| **SAN** | Tập DNS name, IP hoặc các định danh khác được chứng nhận | Có thể có nhiều tên; wildcard có quy tắc khớp giới hạn |
| **Issuer** | CA ký chứng chỉ theo tên hiển thị | Tên Issuer không đủ để định danh khóa CA duy nhất |
| **Serial number** | Giá trị CA dùng để phân biệt chứng chỉ do mình phát hành | Kết hợp với issuer/CA identity khi định danh |
| **Not Before** | Thời điểm bắt đầu khoảng hiệu lực | Certificate mới có thể chưa có hiệu lực ở thời gian thử |
| **Not After** | Ranh giới kết thúc khoảng hiệu lực | Đây là mốc trọng tâm để cảnh báo hết hạn |
| **Public key / algorithm** | Khóa công khai và thuật toán | Không cần hoặc không được thu private key để đọc trường này |
| **Signature algorithm** | Cách issuer ký certificate | Đối chiếu security baseline, không suy chỉ từ tên CA |
| **Key Usage / EKU** | Mục đích sử dụng được phép trong ngữ cảnh xác minh | ServerAuth và ClientAuth không thay thế authorization ứng dụng |
| **Basic Constraints / CA** | Certificate có được xem là CA và giới hạn path hay không | Rất quan trọng khi kiểm kê intermediate/root |
| **SKI/AKI** | Hỗ trợ liên hệ khóa chủ thể và issuer | Có ích khi nhiều CA cùng tên hoặc có cross-sign |
| **Fingerprint** | Hash của toàn bộ certificate dạng DER | Dùng để so sánh bản certificate; không phải ID của service |

### Fingerprint, serial và alias khác nhau

**SHA-256 fingerprint** định danh chính xác **nội dung của một certificate**. Khi tái phát hành certificate mới, fingerprint thay đổi dù Subject và SAN vẫn giống. **Serial number** chỉ có ý nghĩa kết hợp với CA phát hành. **Alias của keystore** là tên cục bộ do ứng dụng/quản trị viên gán và không nhất thiết giống SAN.

Trong inventory, nên lưu **fingerprint + issuer/serial + SAN + deployment binding** để phân biệt bản cũ/bản mới và xác minh node nào đang sử dụng chúng.

### Không dùng một trường để kết luận trust

Certificate có ngày hợp lệ nhưng vẫn có thể thất bại vì **SAN không khớp, trust store thiếu CA, chain không xây được, EKU không phù hợp, trạng thái thu hồi hoặc thuật toán bị client từ chối**. Kiểm tra hạn dùng là một lớp trong chương trình quản lý PKI, không phải bài kiểm tra bảo mật TLS toàn diện.

## 5. Not Before, Not After, múi giờ và cách tính thời hạn

Khoảng hiệu lực X.509 được xác định bằng **Not Before và Not After** theo quy tắc xác minh của client. Khi giám sát, hãy chuẩn hóa thời điểm về **UTC** để tính toán và lưu kết quả, rồi hiển thị bằng múi giờ người vận hành nếu cần.

### Ví dụ tính toán giả định

~~~text
Not Before (UTC):    2026-07-01 00:00:00Z
Not After  (UTC):    2026-12-31 23:59:59Z
Observed at (UTC):   2026-12-17 00:00:00Z

Remaining = NotAfter - ObservedAt
          = 15 ngày trừ 1 giây
          (đây là thời gian còn lại, không phải ngày lịch làm tròn)
~~~

Đối với cảnh báo:

- **EXPIRED:** thời điểm quan sát đã qua mốc Not After theo quy tắc hiệu lực.
- **NOT_YET_VALID:** hiện tại sớm hơn Not Before.
- **EXPIRING_SOON:** còn trong cửa sổ cảnh báo được xác định **theo rủi ro và lead time**, không phải chuẩn chung bắt buộc cho mọi dịch vụ.
- **VALID_FOR_NOW:** certificate còn trong khoảng thời gian hợp lệ, nhưng chưa thể suy trust/identity PASS.
- **UNKNOWN:** chưa lấy được metadata đáng tin cậy hoặc phép đo thất bại.

**Không làm tròn số ngày theo cách che mất vài giờ cuối.** Một certificate hết hạn lúc nửa đêm UTC có thể được đội vận hành ở Việt Nam nhìn thấy vào buổi sáng theo giờ địa phương. Nếu so sánh chuỗi ngày hiển thị mà không xử lý timezone, alert có thể quá muộn.

### Ba nguồn sai lệch thời gian

1. **Đồng hồ trên hệ thống giám sát sai:** tạo báo động sớm hoặc bỏ sót.
2. **Đồng hồ client/server sai:** certificate có thể bị coi là chưa hiệu lực hoặc hết hạn dù máy khác vẫn kết nối được.
3. **Giờ ghi log không nhất quán:** gây khó liên kết sự kiện deploy, renewal và handshake failure.

Giữ thời gian từ nguồn tin cậy, ghi **timestamp kèm timezone**, và trong incident nhớ xem cả clock skew.

## 6. Xây bản đồ nơi certificate có thể nằm

Kiểm kê bắt đầu từ **điểm sử dụng và hệ thống cấp phát**, không phải từ danh sách file PEM tìm thấy trên một máy.

| Khu vực | Ví dụ certificate | Nguồn inventory/telemetry |
|---|---|---|
| **Public edge** | CDN, WAF, reverse proxy, public LB | Provider/API, listener configuration, SNI live probe |
| **Origin/private app** | API gateway, web server, service TLS | IaC, app config, secret store, internal probe |
| **Mạng nội bộ** | VPN, RADIUS/EAP-TLS, thiết bị quản trị, Wi-Fi controller | Device inventory, controller, PKI, endpoint management |
| **Cloud** | Managed certificate, listener, private endpoint, workload secret | Cloud certificate manager, API audit, load balancer config |
| **Kubernetes/containers** | Ingress TLS Secret, cert-manager Certificate, mesh workloads | Cluster API được cấp quyền, controller events, live service probe |
| **Runtime/OS** | Windows Cert Store, Java keystore, PKCS#12, service trust bundle | MDM/EDR, keytool, OS inventory, app owner |
| **Database/messaging** | Database TLS, message broker, MQTT, queue gateway | Service config, certificate file metadata, authenticated probe |
| **Internal CA** | Intermediate, issuing CA, subordinate CA | CA database, HSM/PKI inventory, trust-store distribution |
| **Khách hàng/đối tác** | Client mTLS cho API, certificate của peer hợp đồng | API management, partner register và owner của contract |
| **DR/backup** | Standby ingress, failover gateway, region dự phòng | Backup IaC, offline manifest, thử failover được duyệt |

**Không mở rộng quét toàn Internet** để tìm tài sản chỉ vì các tên miền giống tên công ty. Phát hiện phải dựa trên **asset inventory, quyền kiểm tra và nguồn dữ liệu đã được phê duyệt**. Scan một mạng lớn hoặc nhiều TLS variants có thể tạo tải/cảnh báo, cần quy trình riêng.

### Chứng chỉ “ẩn” trong tài sản khó thấy

- Chứng chỉ **client** trên laptop, thiết bị mạng, IoT hoặc service account.
- Intermediate CA nằm trong **chain bundle** nhưng không xuất hiện như leaf trên endpoint.
- Keystore Java chứa nhiều alias, nhưng app cấu hình một alias cụ thể.
- TLS trên cổng không mặc định như **8443, 9443** hoặc cổng database.
- Thiết bị ở chi nhánh lâu ngày không cập nhật, dùng CA/certificate đã cũ.
- Các kết nối chỉ xuất hiện lúc **DR, blue/green deploy hoặc failover**.

Vì thế inventory tốt phải có nguồn từ **chủ ứng dụng, cấu hình và vận hành**, không chỉ scanner ở edge.

## 7. Discovery theo hướng ít tác động và có kiểm chứng

Có ba cách thu thập bổ trợ:

1. **API/inventory-based:** đọc certificate đã phát hành, cấu hình listener, secret reference, CA record và asset register.
2. **Host/container-based:** trên máy được quản lý, đọc metadata trong certificate store/keystore được phép, không xuất private key.
3. **Connection-based:** kết nối TLS hợp lệ tới hostname/port cụ thể để quan sát certificate mà server thực sự trình bày.

~~~text
  CA/PKI issued list ----+
                        |
  Secret/store metadata -+--> Normalize --> Link to asset/owner
                        |                       |
  LB/Ingress config -----+                       v
                        |                 Desired deployment
  Live SNI probe --------+                       |
                                                v
                                      Compare observed served cert
                                                |
                                           Drift / expiry alert
~~~

### Tại sao active probe dễ bỏ sót?

- Load balancer có **nhiều backend hoặc node**: một probe chỉ đến một node.
- CDN có **nhiều POP**: nơi thử có thể chưa thấy cert cũ ở nơi khác.
- Một IP phục vụ **nhiều hostname theo SNI**: kết nối thiếu SNI có thể trả certificate mặc định.
- Dịch vụ chỉ reachable qua **VPN, private DNS, IPv6 hoặc mạng quản trị**.
- Endpoint yêu cầu **mTLS**: probe không có client certificate có thể thất bại trước khi thu đủ bằng chứng.
- Một số giao thức dùng **STARTTLS** hoặc quy trình bắt tay riêng, không thể kiểm tra bằng HTTPS handshake mặc định.

**Probe failure không tự đồng nghĩa certificate hết hạn.** Có thể do route, DNS, ACL, mTLS, proxy, application downtime hoặc lỗi công cụ. Ghi trạng thái **UNKNOWN/INCONCLUSIVE** và đối chiếu nhiều nguồn.

### Khi nào không nên probe trực tiếp?

Khi thiết bị nhạy cảm, nhiều phiên TLS gây tải, endpoint không có quyền thử, cổng dùng giao thức riêng hoặc certificate chỉ được phép đọc qua một hệ thống quản lý. Khi đó ưu tiên **API/telemetry và owner confirmation**, rồi thiết kế probe có phê duyệt nếu thật sự cần.

## 8. Schema kiểm kê: từ “file cert” đến “dịch vụ có chủ”

Nên thiết kế **một bản ghi certificate** và **nhiều bản ghi nơi triển khai/điểm quan sát**, thay vì đặt tất cả vào một cột tên máy.

| Nhóm | Trường đề xuất | Ý nghĩa |
|---|---|---|
| **Certificate identity** | Fingerprint SHA-256, serial, issuer identifier | Phân biệt các phiên bản chứng chỉ |
| **Certificate metadata** | Subject, SAN, NotBefore, NotAfter, EKU, algorithm | Xác định mục đích và hạn |
| **PKI source** | CA, trust domain, issuance request/order, source system | Tìm lịch phát hành, gia hạn |
| **Service binding** | Service ID, owner, environment, criticality | Gắn trách nhiệm và tác động |
| **Deployment binding** | Endpoint, SNI, port, protocol, LB listener, secret ID, namespace | Biết nơi certificate được dùng |
| **Observation** | Served fingerprint, observed_at, source/region, verify outcome | Biết client thật nhận certificate nào |
| **Renewal** | Manual/ACME/controller/CA API, lead time, last attempt, next action | Vận hành vòng đời |
| **Incident/change** | Ticket, expiry alert, change window, rollback owner | Truy vết quyết định |
| **Security** | Trust policy, revocation status nếu kiểm được, exception expiry | Không đánh đồng ngày còn hạn với an toàn |
| **Lifecycle** | Active, standby, planned, replaced, revoked, archived | Tránh báo lỗi cho những certificate không còn sử dụng |

### Ví dụ một đối tượng kiểm kê (dữ liệu tổng hợp)

~~~yaml
certificate:
  fingerprint_sha256: "SHA256_EXAMPLE_FINGERPRINT_NOT_REAL"
  subject: "CN=api.example.test"
  san_dns:
    - "api.example.test"
  issuer: "Example Issuing CA"
  serial: "EXAMPLE_SERIAL"
  not_before_utc: "2026-09-01T00:00:00Z"
  not_after_utc: "2026-12-31T23:59:59Z"
  purpose: "serverAuth"
  lifecycle: "active"

service:
  id: "service-api-prod"
  criticality: "high"
  owner_team: "api-platform"
  escalation_group: "oncall-api"

deployment:
  endpoint: "api.example.test:443"
  tls_termination: "public-edge"
  region: "region-a"
  sni: "api.example.test"
  observed_fingerprint: "SHA256_EXAMPLE_FINGERPRINT_NOT_REAL"
  observed_at: "2026-11-28T05:00:00Z"

renewal:
  method: "managed-certificate-workflow"
  last_renewal_check: "2026-11-27T00:00:00Z"
  next_action: "verify-all-edge-nodes"
~~~

Đây **không phải schema tiêu chuẩn của một sản phẩm**; mọi tên miền và giá trị đều minh họa. Trong triển khai thực tế, tách bảng **certificate**, **deployment**, **endpoint**, **service** và **observation history** để hỗ trợ một certificate nhiều điểm triển khai hoặc một endpoint có nhiều certificate theo SNI.

### Quy tắc dữ liệu quan trọng

- Mỗi service phải có **owner chính và escalation owner**, không để “team unknown” mãi.
- Certificate **không còn phục vụ** nhưng vẫn nằm trong kho phải có trạng thái được xác minh, tránh tạo cảnh báo nhầm.
- Certificate **đã thu hồi** không được coi an toàn chỉ vì NotAfter còn xa.
- Nên phân biệt **cert inventory record** với **deployment record**; việc renew tạo fingerprint mới không đồng nghĩa tạo service mới.
- Với secret manager, **không copy private key vào inventory**; chỉ lưu reference/metadata và quyền xem phù hợp.

## 9. Phân loại certificate theo mức độ rủi ro và tác động

Không phải mọi certificate sắp hết hạn có cùng mức ưu tiên. Một leaf trên website public đang có hàng triệu người sử dụng khác với certificate test đã bị thay thế, nhưng một **intermediate CA** phục vụ nhiều hệ thống nội bộ còn có thể tạo tác động lớn hơn leaf đơn lẻ.

| Yếu tố | Rủi ro tăng khi | Ví dụ |
|---|---|---|
| **Criticality** | Dịch vụ doanh thu, IAM, VPN, DNS, database, quản trị | Remote-access VPN không xác thực được |
| **Blast radius** | Nhiều dịch vụ/tài sản phụ thuộc cùng cert/CA | Issuing CA phục vụ EAP-TLS và mTLS |
| **Exposure** | Public, đối tác, nhiều region, thiết bị rải rác | CDN có nhiều hostname/POP |
| **Renewal complexity** | Manual approval, CA ngoài, thiết bị khó cập nhật | Certificate ký tay trên network appliance |
| **Lead time** | Thời gian cấp, triển khai, kiểm thử và rollback dài | Thiết bị cần maintenance window theo quý |
| **Ownership clarity** | Không có owner, tài khoản cũ hoặc phụ thuộc vendor | Webhook đối tác không có người phụ trách |
| **Observability** | Không có probe, log hoặc inventory chính xác | Certificate chỉ nằm ở DR site |
| **Security posture** | Private key nghi bị lộ, CA trust thay đổi, chain sai | Cert chưa hết hạn nhưng phải thu hồi |

### Cần lưu cả thời gian xử lý, không chỉ ngày hết hạn

~~~text
Time to expiry
     |
     +-- Thời gian phát hiện + triage
     +-- Thời gian phê duyệt/issue certificate mới
     +-- Thời gian cập nhật secret/config và rollout
     +-- Thời gian kiểm thử mọi endpoint/client
     +-- Thời gian dự phòng cho lỗi + rollback

Alert lead time phải lớn hơn tổng công việc cần làm
với mức dự phòng phù hợp mức quan trọng của dịch vụ.
~~~

Một certificate còn 14 ngày có thể **khẩn cấp** nếu phải xin phê duyệt vendor trong 3 tuần; một certificate được tự động rotate an toàn mỗi ngày có thể cần alert theo **số lần renewal thất bại và thời gian còn lại**, không chỉ mốc cố định 30 ngày.

## 10. Thiết kế ngưỡng cảnh báo trước hạn

Các ngưỡng có thể bắt đầu bằng **45/30/14/7/1 ngày** hoặc chính sách tương đương, sau đó hiệu chỉnh theo **criticality, renewal lead time, tự động hóa và lịch bảo trì**. Đây là **ví dụ gợi ý**, không phải chuẩn bắt buộc.

| Mức ví dụ | Khi nào tạo? | Hành động chính |
|---|---|---|
| **Planning** | Còn không nhiều hơn 45 ngày, phù hợp hệ thống cần chuẩn bị | Tạo work item, xác nhận owner và phương án renew |
| **Warning** | Còn không nhiều hơn 30 ngày | Xác nhận renewal job, chuẩn bị triển khai/compatibility test |
| **High** | Còn không nhiều hơn 14 ngày | Escalate tới service owner/on-call, xác minh lịch thay |
| **Critical** | Còn không nhiều hơn 7 ngày | Kích hoạt quy trình khẩn cấp, có người theo dõi tới khi verified |
| **Immediate** | Còn không nhiều hơn 1 ngày hoặc đã expired | Incident/ưu tiên tối đa phù hợp ảnh hưởng, xác minh đường thực |
| **Unknown health** | Không có phép quan sát mới hoặc endpoint probe liên tục lỗi | Điều tra khoảng trống telemetry; không gắn nhãn expired khi chưa có bằng chứng |

### Một logic cảnh báo minh họa

~~~text
For each active deployment:
    Find observed served certificate when available
    Compare with approved certificate/PKI metadata
    Calculate remaining lifetime in UTC

    If deployment is active and certificate already expired:
        Raise immediate incident according to service severity
    Else if time remaining <= renewal lead time:
        Select planning/warning/high/critical by policy
        Link to owner, service, endpoint and change ticket

    If observation is stale or missing:
        Raise visibility/inventory health alert separately

    Do not mark renewal complete until
    all required deployment endpoints are verified.
~~~

**Không đánh giá hạn cho mọi certificate trong kho như thể chúng đều active.** Cần xét trạng thái **deployed/observed**, mức tác động và ca thay thế đã được duyệt. Nhưng cũng **không bỏ qua intermediate/root**: những chứng chỉ CA/trust được dùng bởi nhiều hệ thống cần chiến lược và cảnh báo riêng.

### Mốc hết hạn và độ chính xác

Nên tính **remaining seconds** hoặc duration rồi quy về bucket cho dashboard. Không chỉ lưu số ngày dạng số nguyên làm tròn: trường hợp còn 23 giờ không nên hiện thành 1 ngày theo cách khiến người vận hành tưởng còn cả ngày làm việc.

## 11. Alert có chất lượng: gắn certificate với người và hành động

Một alert tốt tối thiểu phải có:

~~~text
Alert type:          CERT_EXPIRING_SOON
Service / owner:     [service ID + team/on-call]
Environment:         [prod/staging/DR]
Certificate:         [SHA-256 fingerprint + issuer/serial]
Deployment:          [FQDN:port/SNI, node/region]
NotAfter UTC:        [timestamp]
Remaining:           [duration]
Data source:         [CA/secret/API/live probe]
Last verified:       [timestamp]
Criticality:         [high/medium/low]
Renewal status:      [scheduled/failed/pending/unknown]
Ticket:              [work item]
Expected action:     [renew, deploy, test, acknowledge]
Escalation:          [on-call/owner]
~~~

### Giảm noise mà không che sự cố

- **Deduplicate** theo certificate + service/deployment + severity window, không tạo hàng trăm ticket vì cùng một fingerprint xuất hiện ở nhiều endpoint.
- Nhưng **không gộp mất coverage**: cần liệt kê những node/edge có certificate khác, cả khi cùng hostname.
- Duy trì trạng thái acknowledgement, owner, next action và lần cập nhật cuối.
- Escalate nếu owner không phản hồi hoặc **renewal job thất bại lặp lại**, không chỉ do đếm ngày.
- Khi certificate đã được thay ở một node nhưng chưa thay ở node khác, giữ alert mở theo **deployment chưa đạt**.
- Các ngoại lệ có thời hạn và người duyệt; không dùng “snooze vô thời hạn” để lờ chứng chỉ production.

**Điểm đo cần đủ mới.** Nếu probe cuối cùng cách đây 20 ngày, không được báo “certificate đang hoạt động còn 40 ngày” như một thông tin thời gian thực.

## 12. Renewal workflow: issue mới chưa phải là deploy thành công

Một vòng đời certificate vận hành có kiểm soát:

~~~text
  [Inventory + Owner]
          |
          v
  [Threshold / Renewal schedule]
          |
          v
  [Issue / Reissue certificate]
          |
          v
  [Validate SAN, chain, key usage]
          |
          v
  [Store private key securely]
          |
          v
  [Deploy to every approved endpoint]
          |
          v
  [Reload / Rotate without undue outage]
          |
          v
  [Live handshake and app tests]
          |
          v
  [Update inventory + close alert]
~~~

**Tách trách nhiệm:** PKI/CA team có thể chịu trách nhiệm phát hành, nhưng application/platform owner chịu trách nhiệm deployment, gateway owner chịu trách nhiệm listener, và SOC/operations cần kết quả kiểm chứng từ điểm quan sát thực.

### Gia hạn thủ công, tự động và managed certificates

| Phương án | Ưu điểm | Rủi ro cần quản lý |
|---|---|---|
| **Manual issuance/renewal** | Linh hoạt với thiết bị cũ và PKI đặc thù | Dễ quên, phụ thuộc cá nhân, cần nhiều bước có lỗi |
| **ACME/automation** | Có thể tự cấp/gia hạn với điều kiện kiểm soát domain | Challenge, DNS, permission, quota, propagation, deploy hook có thể lỗi |
| **Cloud managed certificate** | Nhà cung cấp hỗ trợ cấp/phân phối theo dịch vụ | Không phải mọi loại cert/domain/CA và origin đều tự được quản lý |
| **Internal CA autoenrollment** | Phù hợp nhiều endpoint domain-managed/MDM | Phụ thuộc CA availability, policy, trust distribution |
| **Service mesh/workload identity** | Certificate thường ngắn hạn và luân chuyển theo controller | Controller/identity/clock failure gây ảnh hưởng nhiều service |

**Không đồng nhất tự động renew với tự động deploy.** Một job hoàn tất tại CA nhưng gateway chưa reload hoặc app vẫn gắn secret cũ có thể tiếp tục phục vụ certificate sắp hết hạn.

## 13. ACME, chứng minh quyền và nguồn sự cố gia hạn

**Automated Certificate Management Environment (ACME)** hỗ trợ các quy trình tự động hóa certificate trong những triển khai tương thích. Tùy yêu cầu CA và ứng dụng, kiểm chứng quyền đối với tên có thể dùng những challenge phù hợp.

| Challenge/khâu | Vấn đề cần quan sát |
|---|---|
| **HTTP-01** | Domain HTTP được định tuyến và phục vụ challenge đúng; proxy/WAF/redirect hoặc DNS có thể ảnh hưởng |
| **DNS-01** | Có quyền cập nhật record DNS tương ứng; kiểm tra propagation, split DNS và API permission |
| **TLS-ALPN-01** | Cần endpoint và ALPN challenge đúng; load balancer/proxy có thể ảnh hưởng |
| **CA rate limits/quota** | Retry vòng lặp có thể bị giới hạn, làm chậm phát hành |
| **Certificate issuance** | SAN và issuer/policy đúng, không chỉ trạng thái job SUCCESS |
| **Secret deployment** | File, secret version, listener và workload có reload được không? |
| **Verification** | Mọi hostname/region/route cần phục vụ chứng chỉ mới hay chưa? |

Không phải CA nào cũng hỗ trợ mọi challenge hay tất cả loại certificate. Khi sửa lỗi, cần dựa vào **provider, phiên bản ACME client, cấu hình DNS/HTTP và log của job**.

### Giám sát cả pipeline

Nên tách các trạng thái:

~~~text
RENEWAL_REQUESTED
CA_VALIDATION_PENDING
CERTIFICATE_ISSUED
SECRET_STORED
DEPLOYMENT_IN_PROGRESS
DEPLOYED_NOT_VERIFIED
SERVING_NEW_CERTIFICATE
APPLICATION_VALIDATED
RENEWAL_CLOSED
~~~

Nếu tự động hóa dừng ở **CERTIFICATE_ISSUED**, cảnh báo hết hạn của endpoint **không được đóng**. Ngược lại, một renewal job từng lỗi có thể đã tự phục hồi; cần đối chiếu certificate thực tế đang được trình bày thay vì giữ kết luận “hệ thống lỗi” mãi.

## 14. Kiểm tra metadata certificate bằng OpenSSL

Trong một hệ thống được cấp quyền, **OpenSSL** có thể giúp đọc certificate X.509 public và quan sát một kết nối TLS cụ thể. Những lệnh này **không tạo certificate, không export private key và không thay đổi cấu hình server**. Cần ghi bản OpenSSL vì cú pháp/output có thể khác giữa các phiên bản.

### 14.1. Xem certificate public được cung cấp

~~~bash
openssl version

openssl x509 \
  -in server-public-cert.pem \
  -noout -subject -issuer -serial -dates \
  -fingerprint -sha256

openssl x509 \
  -in server-public-cert.pem \
  -noout -ext subjectAltName
~~~

**server-public-cert.pem** là file chứa certificate công khai được chủ tài sản cho phép kiểm tra, **không phải file private key**. Những thông tin cần ghi gồm fingerprint, issuer, SAN và hai mốc thời gian. Với chain gồm nhiều certificate, phải xác định **leaf hay intermediate** đang được đọc; không nhầm NotAfter của intermediate thành hạn của leaf.

### 14.2. Dùng -checkend để kiểm tra cửa sổ sắp hết hạn

~~~bash
# 2.592.000 giây = 30 ngày; ví dụ ngưỡng cần xác minh theo policy
openssl x509 \
  -in server-public-cert.pem \
  -noout -checkend 2592000
~~~

Ở các phiên bản OpenSSL hỗ trợ tùy chọn này, mã thoát **0** thường cho biết certificate **không hết hạn trong số giây được kiểm tra**, còn mã thoát **khác 0** cho biết certificate đã hết hạn hoặc sẽ hết hạn trong cửa sổ đó; lỗi đọc file cũng có thể tạo mã lỗi. Khi xây script thật, **phân biệt lỗi công cụ/file với kết quả kiểm tra hạn**, không quy mọi lệnh lỗi thành chứng chỉ hết hạn.

### 14.3. Quan sát certificate mà một endpoint đang trình bày

~~~bash
openssl s_client \
  -connect api.example.test:443 \
  -servername api.example.test \
  -verify_hostname api.example.test \
  -verify_return_error \
  -showcerts
~~~

**Phải thay api.example.test bằng endpoint thuộc phạm vi được phép**. Lệnh thiết lập một kết nối tới server và hiển thị certificate được trình bày trong handshake. Tham số **-servername** gửi SNI; **-verify_hostname** kiểm tra định danh DNS; **-verify_return_error** yêu cầu lỗi xác minh được phản ánh ở quá trình bắt tay thay vì đơn giản tiếp tục.

Khi thu bằng chứng:

1. Ghi hostname, port, IP thực sự kết nối, SNI, nguồn mạng và timestamp.
2. Xác định **leaf được trình bày** và các intermediate trong chain.
3. Đối chiếu leaf fingerprint với certificate trong inventory/secret manager.
4. Kiểm tra NotAfter, SAN và kết quả trust/hostname riêng biệt.
5. Nếu endpoint có nhiều node/region, không suy một lần thử là đại diện toàn hệ thống.

**-showcerts hiển thị những certificate peer gửi**, không phải bảo đảm bạn đã thu được chain hoàn chỉnh mà mọi client xây được. Trust store của máy test cũng có thể khác trust store của JVM, điện thoại hoặc thiết bị mạng đang phục vụ người dùng thật.

### 14.4. Kiểm tra qua IP cụ thể nhưng giữ đúng SNI

~~~bash
openssl s_client \
  -connect 192.0.2.20:443 \
  -servername api.example.test \
  -verify_hostname api.example.test \
  -verify_return_error
~~~

**192.0.2.20** là địa chỉ tài liệu, không phải IP để đem đi kiểm thử. Mẫu này minh họa việc **địa chỉ vận chuyển và danh tính hostname có thể khác nhau**. Chỉ thay bằng IP được cấp quyền, chẳng hạn một node trong load balancer do đội mình quản lý.

### Những điều OpenSSL không tự làm giúp

- Không suy được toàn bộ mapping giữa leaf certificate và mọi service nếu không có inventory.
- Không chứng minh certificate có thể được tự động renew hoặc deploy.
- Không xác nhận quyền ứng dụng chỉ từ TLS handshake.
- Không đại diện cho mọi trust store, CDN POP, IPv6 và cổng ứng dụng.
- Không cho phép bỏ qua xác minh hostname/CA để đánh dấu PASS.

## 15. Kiểm kê chỉ đọc trên Windows, Java và thiết bị nội bộ

Nhiều certificate doanh nghiệp nằm trong OS trust store, keystore hoặc thiết bị mạng không được công bố qua HTTPS public. Chỉ sử dụng tài khoản và quyền được phân cho công tác inventory.

### 15.1. Windows Certificate Store

~~~powershell
# Certificate trong Personal store của máy
Get-ChildItem Cert:\LocalMachine\My |
  Select-Object Subject, Issuer, NotBefore, NotAfter, Thumbprint

# Certificate trong Personal store của người dùng hiện tại
Get-ChildItem Cert:\CurrentUser\My |
  Select-Object Subject, Issuer, NotBefore, NotAfter, Thumbprint
~~~

**LocalMachine\My** và **CurrentUser\My** chỉ là những store cụ thể, không phải toàn bộ certificate/trust store của Windows. Một certificate trong store không nhất thiết đang được IIS, VPN client hay RADIUS sử dụng. Cần kiểm tra **binding của dịch vụ** qua nguồn cấu hình được cấp quyền.

Không export certificate kèm private key, không dùng lệnh thay đổi store và không đưa nội dung private key vào ticket. **Thumbprint** là fingerprint của certificate; nên chuẩn hóa thuật toán hash/format để ghép đúng với inventory.

### 15.2. Java keystore/truststore

~~~bash
keytool -list -v \
  -keystore ./service-truststore.p12 \
  -storetype PKCS12
~~~

Lệnh đọc metadata keystore được cấp quyền, có thể yêu cầu mật khẩu **qua cơ chế nhập an toàn**. Không đặt mật khẩu trong command line hoặc log. Những thông tin có thể xem gồm **alias, entry type, owner/issuer, serial, validity và chain length** tùy loại entry.

**Java runtime có thể dùng keystore hoặc truststore khác với file người quản trị vừa kiểm tra.** Hãy đối chiếu đường dẫn thực trong app configuration, container image, JVM runtime và secret mount. Một certificate hợp lệ nằm trong truststore không chứng minh ứng dụng đang dùng nó làm server certificate.

### 15.3. Thiết bị mạng, VPN và appliance

Đối với firewall, VPN concentrator, RADIUS/NAC, Wi-Fi controller hoặc load balancer:

- Ưu tiên **read-only API/CLI được nhà sản xuất hỗ trợ**.
- Ghi serial/fingerprint, SAN/identity, NotAfter và mục đích/binding.
- Xem certificate dùng cho **management HTTPS, VPN peer, EAP server và mTLS** dưới dạng những role khác nhau.
- Kiểm tra trust chain/CA certificate đi kèm.
- Lưu tình trạng active/standby và cấu hình HA đồng bộ.
- Nếu thiết bị không xuất certificate public một cách an toàn, dùng API metadata hoặc bằng chứng từ kết nối đã được cấp phép.

Không mặc định toàn bộ certificate import lên một thiết bị đều được sử dụng. **Certificate binding** và **đường đang phục vụ** cần được xác minh riêng.

## 16. Cloud và Kubernetes: vì sao đã renew vẫn có thể hết hạn?

Các nền tảng cloud/Kubernetes thường có nhiều lớp lưu certificate:

~~~text
           [CA / Managed Certificate Service]
                         |
                    [Secret Store]
                     /       \
                    v         v
             [Ingress/LB]  [Workload/mTLS]
                    |         |
                 Endpoint    Service mesh
                    |         |
                 TLS probe + workload telemetry
                         |
                  Inventory compare
~~~

### 16.1. Certificate manager của cloud

Nhà cung cấp có thể quản lý cấp/gia hạn một số loại certificate, nhưng **phạm vi hỗ trợ thay đổi theo dịch vụ và loại certificate**. Cần hỏi:

1. Certificate đã được hệ thống provider quản lý gia hạn hay chỉ được **import thủ công**?
2. Certificate được gắn vào những **LB listener, API gateway, CDN distribution hoặc endpoint** nào?
3. Có nhiều **region/account/subscription** không?
4. Origin hoặc máy chủ bên dưới có **TLS riêng** không?
5. Gia hạn có yêu cầu DNS/domain validation vẫn còn hợp lệ không?
6. Khi thay certificate, các node/failover/edge có đồng bộ trong thời gian mong muốn không?

**Managed certificate không có nghĩa tự động quản lý mọi certificate sau gateway.** Không được đóng alert về origin chỉ vì edge certificate còn hạn.

### 16.2. Kubernetes và cert-manager

Nếu cluster có **cert-manager CRD**, thông tin về Certificate resource, trạng thái Ready và renewal events hữu ích:

~~~bash
# Chỉ dùng trên cluster/namespace được cấp quyền
kubectl get certificate -n app-prod
kubectl describe certificate app-api -n app-prod

# Xem ingress references, không đọc secret payload
kubectl get ingress -n app-prod
~~~

**Lưu ý:** Các lệnh trên phụ thuộc cluster có cert-manager, resource/namespace thật và quyền RBAC của tài khoản. Không dùng để quét namespace ngoài phạm vi. Tránh xuất dữ liệu Secret kiểu TLS ra console, đặc biệt trường chứa **tls.key**.

Những chỗ dễ lệch:

- **Certificate Ready=True** nhưng ingress tham chiếu **Secret khác**.
- Secret chứa cert mới nhưng ingress controller **chưa reload** hoặc một replica còn bản cũ.
- Certificate đúng trong cluster A nhưng cluster B/region DR chưa được cập nhật.
- Một **service mesh** cấp chứng chỉ ngắn hạn bằng controller riêng, không thuộc cert-manager nói trên.
- Ingress public certificate hợp lệ nhưng kết nối **ingress → backend** dùng mTLS identity khác đã hết hạn.

### 16.3. Chứng chỉ ngắn hạn

Workload identities đôi khi dùng certificate có lifetime rất ngắn, được rotate tự động. Với những đối tượng này, ngưỡng 30 ngày thường vô nghĩa. Cần theo dõi **thời gian còn lại so với chu kỳ refresh, tỷ lệ rotation thành công, độ mới của secret, controller health và lỗi xác thực của workload**.

**Short-lived không có nghĩa không cần kiểm kê:** cần biết CA/trust domain, workload owner, chính sách refresh và **phạm vi lỗi khi controller ngừng cấp cert**.

## 17. VPN, 802.1X/EAP-TLS và PKI mạng không dây

Certificate expiry ở mạng thường gây tác động khó quan sát từ ngoài Internet. Thiết bị có thể truy cập được Wi-Fi radio nhưng **không hoàn tất xác thực**; VPN gateway có thể còn online nhưng peer hoặc user không lập được kết nối bảo vệ.

| Hệ thống | Certificate cần quản lý | Dấu hiệu khi lỗi |
|---|---|---|
| **IPsec/IKEv2 VPN** | Peer/gateway certificate và CA trust | Xác thực peer thất bại, SA không được thiết lập/đổi khóa lỗi |
| **Remote-access VPN** | Server certificate, client certificate nếu có, chuỗi CA | Client không tin gateway, phiên đăng nhập lỗi |
| **802.1X/EAP-TLS** | Client device certificate, RADIUS server certificate và CA trust | EAP authentication bị từ chối, client không được cấp quyền mạng |
| **WPA2/WPA3-Enterprise** | RADIUS/EAP server identity, client cert nếu EAP-TLS | Lỗi kết nối/auth hoặc client hiện cảnh báo chứng chỉ |
| **Network appliance HTTPS** | Management TLS certificate | Công cụ quản trị/API hoặc automation mất khả năng xác thực |
| **Machine-to-machine mTLS** | Server/client workload certificates | API/service kết nối được mạng nhưng handshake/identity fail |

### Điều kiện đặc biệt của 802.1X

- Không chỉ kiểm tra **certificate máy tính của người dùng**; cần kiểm tra cả **RADIUS server certificate** được client xác minh.
- Chứng chỉ client có thể được cấp qua **MDM/autoenrollment** hoặc PKI nội bộ và tự renew theo quy trình riêng.
- Thiết bị offline lâu ngày có thể **bỏ lỡ vòng gia hạn**; khi quay lại, nó không xác thực để lấy bản cập nhật như bình thường.
- **CA trust rollover** phải được phân phối trước cho các nhóm thiết bị đại diện; không đợi tới ngày hết hạn của CA.
- Có thể cần **đường phục hồi/onboarding có kiểm soát** cho thiết bị không thể vào mạng do chứng chỉ hết hạn, không mở Wi-Fi nội bộ thành mạng không bảo vệ.

### Đối chiếu danh tính và phân quyền

Mất certificate hợp lệ có thể tạo lỗi authentication; **certificate còn hạn** vẫn có thể thuộc **thiết bị đã bị thu hồi hoặc người dùng không còn quyền**. NAC và IAM phải tiếp tục xét tình trạng thiết bị, chứng chỉ bị revoke, role, policy truy cập và thời gian phiên.

## 18. Intermediate CA, root CA và trust anchor rollover

Chương trình quản trị certificate không chỉ nhìn leaf. **Intermediate CA** hết hạn có thể làm client không xây được chuỗi tin cậy cho nhiều dịch vụ. Việc đổi **root/trust anchor** thường phức tạp hơn vì cần cập nhật nhiều trust store, thiết bị và client.

~~~text
             Old Root CA       New Root CA
                  |                 |
        Old Intermediate      New Intermediate
                  |                 |
           Existing leaf      Replacement leaf
                  \                 /
                 Managed trust transition
                     + staged rollout
~~~

### Điều cần biết về CA rollover

1. **NotAfter của CA** phải được giám sát riêng, với lead time dài phù hợp phụ thuộc nhiều hệ thống.
2. Lập danh sách **certificate/ứng dụng được phát hành bởi CA đó**, trust store nào đang tin, và thiết bị nào khó cập nhật.
3. **Cross-signing và nhiều đường xây chain** có thể khiến hai client chọn đường khác nhau; không kết luận từ một file chain đơn lẻ.
4. Một root trong **trust store được xem là trust anchor** có thể được xử lý theo chính sách khác so với intermediate trong path; việc hết hạn root không tự chứng minh mọi client chắc chắn ngừng hoạt động cùng thời điểm.
5. Tập thiết bị offline, firmware cũ, HSM, Java runtime và các cloud service cần kiểm thử tương thích.
6. Giai đoạn **phân phối trust mới → triển khai cert mới → đo tình trạng client → thu hồi trust cũ** phải được lên kế hoạch có phê duyệt.

### Rủi ro nếu thay trust quá sớm hoặc quá muộn

- **Thu hồi root cũ quá sớm:** client chưa nhận root mới có thể mất kết nối hàng loạt.
- **Giữ root không còn được tin quá lâu:** tăng phạm vi khóa/CA có thể bị lạm dụng sau khi hết yêu cầu.
- **Thiếu intermediate trên server:** một số client có cache sẽ chạy, client khác lỗi.
- **Không kiểm chứng client group:** browser public PASS trong khi Java app, RADIUS hoặc thiết bị mạng vẫn FAIL.

**Kiểm kê CA cần có quan hệ phụ thuộc tới các certificate và trust store**, không chỉ một hàng “Root NotAfter”.

## 19. Revocation và Certificate Transparency không thay thế inventory

**Hết hạn (expiration)** khác **thu hồi (revocation)**:

- Certificate hết hạn khi đi qua ranh giới hiệu lực được quy định.
- Certificate có thể bị **revoked trước NotAfter** vì lộ khóa, sai cấp phát hoặc lý do khác.
- Client xử lý revocation theo chính sách/khả năng khác nhau, ví dụ **CRL, OCSP, OCSP stapling** hoặc cơ chế riêng.
- Có những môi trường không thể quan sát revocation đầy đủ từ một probe.

**Certificate Transparency (CT)** là nguồn thông tin bổ sung cho chứng chỉ TLS công khai trong phạm vi áp dụng, giúp phát hiện chứng chỉ được phát hành cho domain ngoài dự kiến. Tuy vậy:

1. CT **không phải danh sách đầy đủ các private PKI certificates** của tổ chức.
2. Certificate xuất hiện trong CT **không chứng minh** đang được triển khai.
3. Không phải mọi trường SAN của một chứng chỉ tìm được đều thuộc tài sản mà nhóm khảo sát có quyền quản trị.
4. Dữ liệu CT, CA inventory và live TLS scan có **vai trò khác nhau**; cần liên kết chứ không thay thế lẫn nhau.

Trong phát hiện certificate sắp hết hạn, **NotAfter từ bản đang phục vụ** là tín hiệu mạnh cho đoạn TLS đó. CT và CA giúp phát hiện **cấp phát mới/bất thường** hoặc thiếu inventory, nhưng không tự xác nhận một endpoint đang dùng certificate nào.

## 20. Phân biệt false positive, false negative và khoảng trống quan sát

| Tình huống | Có thể bị hiểu nhầm | Cách xác minh |
|---|---|---|
| Certificate đã **retired** vẫn còn trong vault | Alert sắp hết hạn dù không còn dùng | Xem deployment binding và owner xác nhận |
| Probe thiếu SNI | Server trả default certificate sắp hết hạn | Gửi đúng hostname/SNI được phép |
| CDN nhiều POP/region | Probe PASS ở vùng A, nhưng vùng B vẫn dùng cert cũ | Đối chiếu provider API và các nguồn probe được duyệt |
| Keystore có nhiều alias | Đọc cert hết hạn không phải alias đang dùng | Kiểm tra runtime service binding |
| Cloud managed certificate mới đã issued | Tưởng hoàn tất renew trong khi listener còn cert cũ | Kiểm tra served fingerprint từng endpoint |
| Certificate chain gồm intermediate cũ | Tưởng leaf đang hết hạn hoặc ngược lại | Phân biệt leaf và từng CA certificate |
| Client trust store khác | Một máy PASS, thiết bị khác FAIL | Kiểm tra trust chain và client classes |
| Dịch vụ không reachable | Tự báo cert expired khi không thấy handshake | Phân loại UNKNOWN + telemetry mạng |
| SSL inspection proxy có certificate riêng | Ghi nhận nhầm fingerprint của origin | Ghi rõ điểm nhìn và termination hop |
| Cert ngắn hạn được rotate mỗi giờ | Cảnh báo sát hạn liên tục dù automation khỏe | Theo dõi rotation SLA, issuer/controller health |

**False positive** khiến đội vận hành bớt tin alert, nhưng **false negative** có thể làm gián đoạn dịch vụ quan trọng. Đừng giải quyết noise bằng cách bỏ giám sát toàn bộ wildcard/short-lived certificates; hãy cải thiện **binding, trạng thái sử dụng, lead time và phương pháp đối chiếu**.

### Hai loại bằng chứng nên giữ riêng

- **Certificate fact:** một fingerprint cụ thể có NotAfter và Issuer như thế nào.
- **Deployment fact:** tại thời điểm và nguồn đo nào, một endpoint/SNI đã phục vụ fingerprint đó.

Khi không có bằng chứng thứ hai, kết luận chỉ nên là **“certificate trong inventory sắp hết hạn”**, không được khẳng định “người dùng đang nhận certificate sắp hết hạn”.

## 21. Thiết kế giám sát theo luồng dữ liệu nhiều nguồn

Một hệ thống giám sát liên tục nên có các bước:

~~~text
        [CA / Cloud / Vault / OS / Kubernetes]
                           |
                     Collect metadata
                           |
               Normalize certificate facts
                           |
                  Match certificate ID
                           |
              Link service + owner + deployments
                           |
         +-----------------+------------------+
         |                                    |
   Check issued/stored age               Live TLS probes
   and renewal job status               (approved endpoints)
         |                                    |
         +-----------------+------------------+
                           |
                     Compare / Deduplicate
                           |
              Expiry + Drift + Visibility alerts
                           |
                 Owner notification / Ticket
                           |
                   Verified replacement
~~~

### Các yêu cầu vận hành

- Collector chỉ nhận **quyền tối thiểu**, không cần đọc private key để xem metadata certificate.
- Dữ liệu API, trust chain, endpoint và owner phải có **timestamp/source**.
- Cảnh báo **stale observation** khi không probe được hoặc collector ngừng hoạt động.
- Không chỉ giám sát public TLS; thêm những dịch vụ **chỉ reachable qua VPN/internal DNS**.
- Có mapping từ service tới **business owner, on-call, region, trust domain và policy**.
- Tách **inventory drift alert** (bản phục vụ khác bản dự kiến) khỏi **expiry alert**.
- Chú ý **quyền riêng tư**: client cert subject có thể chứa username/device ID, log cần giảm dữ liệu và kiểm soát retention.

### Ví dụ các trạng thái kiểm soát

| Trạng thái | Nghĩa vận hành |
|---|---|
| **HEALTHY_VERIFIED** | Bản triển khai được quan sát, thời hạn và policy phù hợp theo phạm vi test |
| **EXPIRING** | Bản active nằm trong lead-time alert |
| **EXPIRED** | Bản active đã vượt NotAfter và có bằng chứng đáng tin |
| **ROTATED_UNVERIFIED** | Cert mới đã được issue/deploy nhưng chưa xác minh toàn bộ điểm phục vụ |
| **DEPLOYMENT_DRIFT** | Served fingerprint khác desired/approved version |
| **OBSERVATION_STALE** | Không có dữ liệu đo mới đủ tin |
| **RETIRED_CONFIRMED** | Certificate không còn thuộc active service sau xác minh |
| **INCONCLUSIVE** | Bằng chứng mâu thuẫn hoặc chưa đủ |

**Mục tiêu cuối không phải làm mọi certificate “xanh” trong kho**, mà là bảo đảm các kết nối hợp lệ vẫn xác thực đúng danh tính và không bị gián đoạn do vòng đời certificate.

## 22. Runbook xử lý certificate sắp hết hạn hoặc đã hết hạn

### Giai đoạn 1 — Triage

1. Xác nhận **certificate fingerprint, issuer, NotAfter**, dữ liệu quan sát và thời gian UTC.
2. Tìm **service/owner/criticality/endpoint/SNI** liên quan.
3. Phân biệt certificate **đang phục vụ, chỉ nằm trong kho, đã retired hay thuộc CA**.
4. Kiểm tra **renewal job, ticket, trạng thái deployment và các node còn dùng bản cũ**.
5. Xem health người dùng/API và log TLS handshake, không suy outage từ NotAfter của một file bất kỳ.

### Giai đoạn 2 — Đánh giá tác động

- **Public edge:** có nhiều hostname/region/POP bị ảnh hưởng không?
- **Origin/private:** edge vẫn tốt nhưng proxy–origin hoặc service mesh có lỗi mTLS không?
- **RADIUS/VPN:** certificate nào khiến thiết bị/người dùng không thể xác thực?
- **CA/trust:** nhiều service dựa vào một intermediate hoặc root sắp hết hạn không?
- **Client versions:** chỉ một số JVM, mobile OS hoặc thiết bị cũ bị lỗi trust không?
- **Dự phòng:** node standby/DR có certificate cũ sẽ gây lỗi khi failover không?

### Giai đoạn 3 — Khắc phục có phê duyệt

1. Xác định cách renew phù hợp (ACME, PKI nội bộ, cloud managed, vendor).
2. Kiểm tra **SAN, chain, EKU, issuer, thuật toán và trust compatibility** của bản mới.
3. Cấp và bảo vệ private key theo secret-management policy, không sao chép qua ticket.
4. Triển khai theo thứ tự an toàn, có **canary/rolling/HA plan** khi nền tảng hỗ trợ.
5. Xác minh reload, listener/ingress binding, route, SNI và vùng dự phòng.
6. Với nghi ngờ lộ khóa, tuân theo quy trình **revocation/incident response**; không rollback về khóa đã bị lộ hoặc xâm phạm.

### Giai đoạn 4 — Xác minh end-to-end

- Certificate mới **đang được trình bày** ở từng điểm kết thúc đã cam kết.
- Hostname/trust chain và mục đích sử dụng được client phù hợp xác minh.
- mTLS/802.1X/VPN auth hoặc ứng dụng nghiệp vụ thực sự hoàn tất.
- Không tạo lỗi mới trên IPv4/IPv6, trong VPN, ở origin/DR hoặc những client đại diện.
- Cảnh báo được đóng dựa trên **bằng chứng deployment**, không chỉ sau khi nhấn nút Renew.

### Giai đoạn 5 — Hậu kiểm

Lưu nguyên nhân gốc, thay đổi, thời gian phát hiện/phục hồi, owner/escalation, lỗ hổng inventory, cách cập nhật automation và các phép kiểm thử hồi quy. Khi một dịch vụ mất owner hoặc chỉ có manual renewal, ưu tiên sửa **quy trình sở hữu/vòng đời** chứ không chỉ gia hạn thêm một lần.

## 23. Case study 1: CA đã gia hạn nhưng node dự phòng vẫn dùng certificate cũ

**Bối cảnh giả định:** API production **api.example.test** được phục vụ qua hai vùng cloud, có load balancing và đường failover. Certificate được gia hạn qua certificate manager. Dashboard CA báo issuance thành công, nhưng một số API client đột ngột gặp lỗi xác thực sau khi một vùng bị chuyển tải.

### Bằng chứng ban đầu (giả định)

~~~text
Service:               api.example.test
Primary region:        region-a
Standby region:        region-b
CA renewal job:        SUCCESS
New cert fingerprint:  FP_NEW_EXAMPLE
Old cert fingerprint:  FP_OLD_EXAMPLE
Old NotAfter:          2026-11-28T03:00:00Z
Region-a served cert:  FP_NEW_EXAMPLE
Region-b served cert:  FP_OLD_EXAMPLE
Incident symptom:      một số TLS handshake fail sau failover
Business impact:       API requests timeout / TLS errors tăng
~~~

**Dữ liệu này minh họa nguy cơ “renewed but not fully deployed”**, không nói tới một hệ thống thật.

### Các giả thuyết cần kiểm tra

1. Secret đã cập nhật ở region A nhưng **replication/certificate binding của region B chưa cập nhật**.
2. Gateway B đã nhận secret mới nhưng **process chưa reload**.
3. Một listener/SNI hostname ở B vẫn tham chiếu certificate alias cũ.
4. Client của một nhóm đối tác có trust store khác, gây lỗi độc lập với expiry.
5. DNS/traffic steering thay đổi đưa request tới một điểm phục vụ chưa có trong danh sách kiểm tra.

### Chuỗi kiểm chứng

1. Ghi thời gian, lỗi TLS đầy đủ, IP/region/POP và SNI của request thất bại.
2. Kiểm tra leaf fingerprint và NotAfter mà mỗi điểm **thực sự trình bày**.
3. So sánh certificate manager, secret store và listener/ingress configuration với dữ liệu served.
4. Xem lịch rollout, reload và các sự kiện failover/HA.
5. Triển khai bản mới ở node B qua quy trình được duyệt; kiểm tra cả handshake và API transaction.
6. Sau khắc phục, kiểm tra region A/B, các hostname và đường fallback.
7. Chỉnh monitor thành **theo deployment/node và trạng thái served**, không chỉ theo CA issuance status.

**Kết luận khi đã xác minh:** API outage có thể phát sinh do **node dự phòng tiếp tục phục vụ bản certificate đã hết hạn**, dù issuance mới ở CA thành công. Giải pháp mang tính hệ thống là tăng khả năng kiểm chứng **từng điểm phục vụ** và tự động hóa rollout/owner tracking.

## 24. Case study 2: thiết bị Wi-Fi không thể xác thực sau kỳ nghỉ

**Bối cảnh giả định:** Nhân viên trở lại sau kỳ nghỉ dài. Một nhóm laptop quản lý bởi MDM không kết nối được SSID doanh nghiệp dùng EAP-TLS; các laptop khác vẫn vào được. RADIUS server còn hoạt động, Wi-Fi radio và DHCP hạ tầng không ghi nhận lỗi diện rộng.

### Các giả thuyết cần phân biệt

- Certificate client đã **hết hạn khi thiết bị offline**, không hoàn tất autoenrollment.
- Chứng chỉ RADIUS server đã được thay, nhưng **trust store của nhóm laptop chưa cập nhật CA**.
- MDM profile trỏ sai certificate alias/identity sau thay đổi.
- NTP/time của thiết bị không đúng.
- NAC/802.1X policy không còn cấp quyền cho nhóm user/device.
- Lỗi radio/roaming hoặc DNS/route khác khiến trải nghiệm bị hiểu nhầm là auth issue.

### Cách xử lý

1. Lấy mã lỗi EAP/RADIUS và timestamp, không tự kết luận từ câu “không vào được Wi-Fi”.
2. Đọc certificate metadata của **client thiết bị và RADIUS server**, đối chiếu issuer, EKU, NotAfter và trust.
3. Kiểm tra autoenrollment/MDM job, lịch offline và certificate lifecycle record.
4. Xác minh thiết bị vẫn thuộc quyền quản lý và user còn quyền truy cập.
5. Thực hiện phục hồi certificate qua **đường onboarding được phê duyệt**, không bỏ xác thực 802.1X toàn doanh nghiệp.
6. Kiểm thử nối mạng, phân đoạn VLAN, DNS và ứng dụng sau khi certificate hợp lệ.

**Bài học:** Certificate inventory cần bao phủ cả **client-side certificates**, không chỉ web server; cần cách phục hồi cho thiết bị không thể vào mạng để tự gia hạn.

## 25. Bài thực hành an toàn: phân loại expiry từ dữ liệu tổng hợp

Bài thực hành sử dụng **bảng giả lập**, không cần quét mạng, xin certificate từ CA thật hoặc truy cập private key. Thời điểm giả định của bài tập: **2026-12-01 00:00:00 UTC**.

| ID | Tài sản | NotAfter (UTC) | Trạng thái | Observed/deployment | Câu hỏi |
|---|---|---|---|---|---|
| **CERT-A** | Public API edge | 2026-12-06 00:00 | Active | Served fingerprint xác minh hôm nay | Ưu tiên nào? |
| **CERT-B** | Website staging cũ | 2026-12-03 00:00 | Retired (chưa xác nhận) | Không có probe mới 40 ngày | Có nên tự đóng? |
| **CERT-C** | Issuing CA cho VPN/Wi-Fi | 2027-01-10 00:00 | Active | Nhiều client phụ thuộc | Lead time nào phù hợp? |
| **CERT-D** | Cloud managed API | 2026-12-20 00:00 | Active | CA báo mới; node DR chưa xác minh | Đóng renewal được chưa? |
| **CERT-E** | mTLS client workload | 2026-12-01 02:00 | Active, short-lived | Controller rotate theo giờ, log mới nhất trễ | Alert theo tiêu chí nào? |
| **CERT-F** | Internal API origin | 2026-11-30 00:00 | Active | Edge→origin lỗi handshake | Cần xác minh gì ngay? |

### Nhiệm vụ

1. Phân loại từng trường hợp theo **EXPIRED / EXPIRING / OBSERVATION_STALE / ROTATED_UNVERIFIED / INCONCLUSIVE** phù hợp; một trường hợp có thể cần nhiều tín hiệu.
2. Xếp thứ tự xử lý theo **criticality, blast radius, time-to-fix**, không chỉ ngày hết hạn.
3. Viết **một alert** cho CERT-A với đủ owner, endpoint, fingerprint, NotAfter và next action.
4. Với CERT-B, cần bằng chứng gì để gọi **RETIRED_CONFIRMED**?
5. Với CERT-C, vì sao lịch CA rollover cần chuẩn bị sớm hơn một server leaf thông thường?
6. Với CERT-D, những nguồn dữ liệu nào chứng minh node DR đã phục vụ cert mới?
7. Với CERT-E, vì sao một ngưỡng cảnh báo 30 ngày không hữu ích? Nên đo controller/rotation thế nào?
8. Với CERT-F, khi nào có thể kết luận outage do expiry, khi nào vẫn là **INCONCLUSIVE**?

### Mẫu biên bản kiểm thử

~~~text
Exercise / Incident ID: PKI-EXPIRY-01
Assessment time UTC:   [timestamp]
Certificate ID:        [fingerprint + issuer/serial]
Service / criticality: [service, owner, role]
NotBefore / NotAfter:  [UTC]
Lifecycle status:      [active / retired / unknown]
Deployment points:     [hostname/port/SNI/node/region]
Last observed:         [timestamp + collection source]
Currently served:      [fingerprint or not verified]
Renewal state:         [issued/stored/deployed/verified]
User/application:      [success/error]
Assessment:            [PASS/FAIL/INCONCLUSIVE]
Next action / owner:    [responsible person/team]
Evidence:              [approved metadata, not private keys]
~~~

### Tiêu chí hoàn thành bài lab

Người học không cần “đoán đúng một câu trả lời” khi thiếu bằng chứng; cần biết **gắn nhãn UNKNOWN/INCONCLUSIVE**, yêu cầu dữ liệu nào trước khi chặn/đổi cấu hình, và giải thích **vì sao cùng một ngày hết hạn có thể tạo mức rủi ro khác nhau**.

## 26. Ma trận kiểm thử hệ thống kiểm kê và cảnh báo

| Test ID | Tình huống | Kỳ vọng |
|---|---|---|
| **PKI-01** | Certificate active còn dưới warning lead time | Có alert đúng service/owner, không bị bỏ qua |
| **PKI-02** | Certificate expired đang được endpoint phục vụ | Escalation/incident theo impact, đầy đủ endpoint evidence |
| **PKI-03** | Chứng chỉ retired đã được xác nhận | Không tạo production outage alert, vẫn có audit/history |
| **PKI-04** | Secret mới đã cấp nhưng listener chưa reload | Không tự đóng; trạng thái DEPLOYED_NOT_VERIFIED/DRIFT |
| **PKI-05** | Một CDN/DR node còn cert cũ | Alert liệt kê đúng node và fingerprint khác biệt |
| **PKI-06** | Endpoint cần SNI | Probe dùng đúng hostname, không nhầm cert mặc định |
| **PKI-07** | Host có IPv4 và IPv6 | Kiểm tra coverage theo cả address family được hỗ trợ |
| **PKI-08** | mTLS yêu cầu client certificate | Probe fail được phân loại đúng, không tự báo leaf expired |
| **PKI-09** | JVM/Windows trust store khác nhau | Báo rõ client trust basis và kết quả từng nhóm |
| **PKI-10** | Issuing CA/intermediate sắp hết hạn | Cảnh báo CA riêng và liệt kê dịch vụ phụ thuộc |
| **PKI-11** | Renewal job fail nhưng vẫn đủ thời hạn | Ghi lỗi automation và owner xử lý trước expiry |
| **PKI-12** | Rotation của short-lived workload | Dùng ngưỡng phù hợp vòng đời và phát hiện controller ngừng hoạt động |
| **PKI-13** | Collector mất quyền/không thể đọc API | Cảnh báo visibility gap, không báo giả là chứng chỉ hết hạn |
| **PKI-14** | Client cert 802.1X của thiết bị offline hết hạn | Có quy trình phát hiện và onboarding phục hồi hợp lệ |
| **PKI-15** | Certificate thay đổi fingerprint nhưng SAN/service giữ nguyên | Inventory giữ continuity theo service/deployment |
| **PKI-16** | Thay cert trong môi trường production | Mọi endpoint cần phục vụ chứng chỉ mới được xác minh, không giảm SLO |
| **PKI-17** | Chứng chỉ bị revoked trước NotAfter | Không coi VALID_FOR_NOW chỉ từ ngày hết hạn |
| **PKI-18** | Endpoint handshake lỗi do DNS/firewall | Gắn INCONCLUSIVE/NETWORK_FAILURE thay vì EXPIRED |
| **PKI-19** | Owner đổi bộ phận hoặc rời tổ chức | Alert không rơi vào hộp thư vô chủ, có escalation path |
| **PKI-20** | CA trust rollover được phê duyệt | Client đại diện và đường failover tiếp tục xác thực đúng |

**Chỉ kiểm thử trên hệ thống được phép**, ưu tiên staging/lab với certificate giả lập cho trường hợp hết hạn hoặc trust sai. Không cố tạo expired certificate trên production, không rút root CA của thiết bị người dùng và không ép failover ngoài change window.

## 27. Những sai lầm phổ biến

| Sai lầm | Vì sao gây rủi ro | Cách làm đúng |
|---|---|---|
| Chỉ nhìn certificate đã phát hành ở CA | Có thể còn bản cũ tại LB/edge | Ghép issued–stored–deployed–observed |
| Chỉ scan HTTPS public | Bỏ sót mTLS, VPN, Wi-Fi, RADIUS, origin và DR | Kiểm kê theo asset + service owner |
| Coi một hostname là một certificate cố định | SNI, CDN POP, nhiều node và region có thể khác | Lưu nhiều deployment bindings |
| Dùng CN thay SAN để kiểm tra hostname | Hostname verification hiện đại dựa chủ yếu trên SAN | Đọc SAN và dùng phép xác minh phù hợp |
| Nghĩ NotAfter còn hạn chứng minh TLS an toàn | Trust chain, EKU, revocation, hostname có thể sai | Tách expiry khỏi TLS posture |
| Đếm số ngày theo giờ địa phương không nhất quán | Alert sai lệch gần thời điểm hết hạn | Chuẩn hóa UTC, lưu timestamp |
| Đặt warning 30 ngày cho tất cả certificate | Short-lived/multi-year/manual workflows rất khác nhau | Ngưỡng theo rotation/lead-time/risk |
| Đóng alert ngay khi renewal job SUCCESS | Triển khai hoặc reload có thể chưa hoàn tất | Xác minh served fingerprint |
| Bỏ qua node dự phòng | Failover có thể kích hoạt certificate hết hạn | Kiểm tra HA, DR và mọi region |
| Tưởng có certificate trong keystore là app đang dùng | Alias/binding có thể khác | Xác minh config/runtime và endpoint |
| Bỏ qua intermediate/root CA | Mất trust có thể ảnh hưởng nhiều service | CA dependency mapping và rollover plan |
| Dùng cert public làm bằng chứng danh tính user | TLS server cert không xác nhận end-user | IAM/authorization riêng |
| Tắt certificate verification để tránh outage | Mất xác thực server, tăng nguy cơ MITM | Khắc phục chain/identity/trust đúng cách |
| Lưu private key trong inventory | Lộ bí mật bảo mật | Chỉ lưu metadata và secret reference |
| Báo expired khi probe timeout | Có thể DNS/firewall/VPN lỗi | Trạng thái UNKNOWN và điều tra lớp mạng |
| Coi CT là danh mục đầy đủ của PKI | CT không bao phủ private PKI và cert chưa triển khai | Kết hợp nhiều nguồn |
| Dùng certificate chung cho nhiều thiết bị | Không thể thu hồi/quy trách nhiệm riêng | Ưu tiên danh tính thiết bị/workload riêng phù hợp |
| Không có owner/escalation | Alert không được hành động dù phát hiện sớm | Gắn trách nhiệm và SLO xử lý |
| Rollback sang key đã lộ | Khôi phục dịch vụ nhưng tái mở rủi ro | Kế hoạch thay key an toàn và incident response |
| Không kiểm thử luồng DENY | Có thể vô tình mở quyền sau sửa TLS/mTLS | Kiểm tra cả quyền hợp lệ và bị từ chối |

## 28. Câu hỏi tự kiểm tra

1. Tại sao certificate đã cấp phát thành công chưa đủ chứng minh website đang phục vụ certificate mới?
2. Phân biệt **issued, stored, deployed, observed/served** bằng một ví dụ CDN có hai vùng.
3. Những trường X.509 nào tối thiểu cần đọc để biết certificate đang kiểm tra là bản nào và sắp hết hạn không?
4. Vì sao **SAN** quan trọng hơn Subject CN khi xác minh tên HTTPS hiện đại?
5. **Not Before** và **Not After** có ý nghĩa gì? Vì sao phải chuẩn hóa thời gian về UTC?
6. Fingerprint khác serial, issuer và keystore alias như thế nào?
7. Tại sao một certificate có NotAfter còn xa vẫn có thể bị client từ chối?
8. Dùng **openssl x509 -checkend** thế nào và phải xử lý lỗi file/công cụ ra sao để không báo expired giả?
9. Khi dùng **openssl s_client**, vì sao cần truyền đúng **-servername**?
10. Vì sao một node/CDN POP khác có thể trả certificate cũ dù DNS hostname giống nhau?
11. Những nguồn inventory nào bổ sung cho public TLS scan để bao phủ **mTLS, EAP-TLS và VPN**?
12. Khi dùng **Windows Certificate Store** hoặc **Java keystore**, vì sao certificate có mặt chưa chứng minh đang được ứng dụng sử dụng?
13. Tại sao chứng chỉ intermediate CA sắp hết hạn thường cần lead time và dependency mapping lớn hơn leaf thông thường?
14. Root CA được xem là trust anchor có xử lý expiry hoàn toàn giống intermediate CA trên mọi client không?
15. Certificate Transparency giúp phát hiện điều gì và không thể xác nhận điều gì?
16. Đối với short-lived certificate tự rotate mỗi giờ, nên theo dõi những metric nào thay vì ngưỡng 30 ngày?
17. Vì sao một client Wi-Fi EAP-TLS sau kỳ nghỉ dài có thể mất quyền mạng dù SSID và RADIUS đang hoạt động?
18. Nếu certificate manager báo SUCCESS nhưng ingress chưa reload, alert nên hiển thị trạng thái gì?
19. Những bước nào giúp điều tra một handshake failure mà không tự động kết luận do certificate expired?
20. Khi gia hạn certificate cho API production, phải kiểm chứng cả **client hợp lệ và client không có quyền** như thế nào?
21. Hãy thiết kế alert bao gồm certificate identity, owner, endpoint, last observed, lead time và next action.
22. Sau khi sửa certificate cho region A, cần bằng chứng nào để xác nhận cả DR region B đã an toàn?
23. Nếu một private key bị lộ, vì sao không nên chỉ gia hạn rồi tiếp tục dùng lại quy trình cũ mà không đánh giá incident response?
24. Trong bài thực hành giả lập, vì sao CERT-B có thể là false positive còn CERT-F cần xử lý khẩn?

## 29. Ghi nhớ trọng tâm

**Kiểm kê certificate là kiểm kê mối quan hệ giữa chứng chỉ, PKI, tài sản, điểm triển khai và người chịu trách nhiệm theo thời gian.** Thấy certificate còn hạn trong CA hoặc secret store chưa đủ: phải đối chiếu **issued, stored, deployed và observed**, đặc biệt ở CDN, origin, ingress, load balancer, gateway VPN, 802.1X, service mesh và đường DR. Thông tin trọng yếu gồm **SAN, issuer, fingerprint/serial, NotBefore, NotAfter theo UTC, trust policy, lifecycle, service owner và served fingerprint**.

**Phát hiện sắp hết hạn chỉ có ích khi tạo ra hành động trước lúc người dùng bị ảnh hưởng.** Ngưỡng phải dựa vào **criticality, blast radius, thời gian gia hạn–triển khai–kiểm thử, khả năng tự động hóa và chất lượng telemetry**; CA/root, short-lived workload và manual appliance không thể dùng một ngưỡng giống nhau. Cảnh báo phải gắn owner, nguồn bằng chứng, endpoint, thời điểm quan sát, kế hoạch renew và escalation; **không đóng chỉ vì CA báo SUCCESS** nếu chưa xác minh bản mới tại mọi điểm phục vụ liên quan.

Kiểm thử có phép bằng **OpenSSL, PowerShell, keytool, API của cloud/Kubernetes và live TLS probes** giúp củng cố inventory nhưng không cần đọc private key hoặc quét mạng ngoài quyền. Sau khi sửa, hãy xác nhận **hostname/trust, mTLS/VPN/EAP-TLS, giao dịch ứng dụng, đường dự phòng và quy tắc phân quyền**. Kết luận cuối cùng phải phân biệt **đã quan sát, chưa thể kiểm chứng và đã phục hồi thành công**, vì **certificate lifecycle là bài toán an ninh và availability cùng lúc**.
