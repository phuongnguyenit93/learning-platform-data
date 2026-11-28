# Mã hóa khi truyền – Thiết kế, kiểm chứng TLS/mTLS và bằng chứng bảo mật

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **mã hóa khi truyền (encryption in transit)** bảo vệ những thuộc tính nào và phân biệt nó với mã hóa khi lưu, chữ ký số, xác thực người dùng và phân quyền ứng dụng.
- Mô tả các thành phần cốt lõi của **TLS**, gồm xác thực máy chủ, chuỗi chứng chỉ, CA/trust store, hostname, bắt tay khóa phiên, mã hóa có xác thực và vòng đời khóa/chứng chỉ.
- Phân biệt **HTTPS, TLS cho kết nối database/broker và mTLS**; hiểu ý nghĩa của TLS termination tại gateway, CDN, service mesh và ranh giới từng hop.
- Thiết kế chuẩn bảo vệ các luồng **client → gateway → service → database/queue/object storage/vendor**, kể cả các kết nối nội bộ, đường quản trị và disaster recovery.
- Nhận biết rủi ro từ **tắt xác minh chứng chỉ, sai audience/hostname, giao thức yếu, plaintext fallback, khóa riêng bị lộ, certificate rotation lỗi, đường bypass và 0-RTT replay**.
- Viết security requirements, tổ chức **positive/negative tests**, xác minh cấu hình runtime và lập hồ sơ bằng chứng theo chuỗi **risk → requirement → control → test → evidence → finding → remediation/retest**.
- Thực hành với Java 17, Spring Boot, JDBC và lập kế hoạch đánh giá liên tục trong module **SECURITY_SECURITY_ASSURANCE**.

## 1. Vì sao cần mã hóa khi truyền?

Giả sử một trình duyệt yêu cầu xem giao dịch tài chính qua mạng công cộng. Nếu request và response đi ở dạng plaintext, một bên có khả năng quan sát đường truyền có thể đọc nội dung. Trong một số tình huống, kẻ tấn công còn có thể can thiệp dữ liệu hoặc giả mạo đầu nhận. Mã hóa khi truyền giúp bảo vệ nội dung **trong lúc dữ liệu đi giữa những điểm được xác định**, đồng thời TLS thích hợp có thể xác minh đầu giao tiếp và phát hiện việc sửa dữ liệu trong kênh.

Nhưng chỉ ghi “ứng dụng dùng HTTPS” **không chứng minh toàn bộ luồng đã được bảo vệ**:

- Browser có thể giao tiếp HTTPS với API gateway, nhưng gateway gọi backend bằng HTTP.
- Service gọi database bằng kết nối plaintext dù public API đã mã hóa.
- Một worker gửi dữ liệu khách hàng tới message broker không mã hóa hoặc chưa xác minh tên broker.
- TLS bị terminate tại load balancer và request tiếp tục qua vùng mạng khác, không có chính sách bảo vệ tương xứng.
- Client bật TLS nhưng bỏ kiểm tra chứng chỉ hoặc hostname, khiến một endpoint giả có thể được chấp nhận.
- API trả dữ liệu sai tenant trên HTTPS: **kênh được bảo vệ**, nhưng authorization vẫn sai.

Trong **SECURITY_SECURITY_ASSURANCE**, “mã hóa khi truyền” là một **security control phải được đánh giá bằng chứng** trong bối cảnh mục tiêu bảo mật, risk scenario, môi trường và phiên bản đã triển khai. Mục tiêu không chỉ là bật một cờ `ssl=true` mà còn **chứng minh những đường cần bảo vệ thực sự được bảo vệ và không thể âm thầm bị hạ cấp**.

### Ba thuộc tính TLS có thể hỗ trợ

| Thuộc tính | TLS mang lại điều gì khi cấu hình/xác minh đúng? | Điều TLS không tự giải quyết |
| --- | --- | --- |
| **Confidentiality** | Dữ liệu ứng dụng không xuất hiện nguyên văn trên đoạn kênh TLS đã bảo vệ | Dữ liệu ở đầu cuối, log, cache, memory, bản export hoặc các đoạn chưa mã hóa |
| **Integrity** | Bên nhận phát hiện được thay đổi trái phép trong bản ghi TLS nhờ cơ chế bảo vệ toàn vẹn | Giá trị sai do chính ứng dụng/actor được xác thực tạo ra |
| **Peer authentication** | Client có thể xác minh máy chủ; mTLS còn có thể xác thực phía client ở kênh | Quyền đọc tài nguyên, tenant ownership, business purpose và danh tính người dùng cuối |

**TLS không đồng nghĩa mã hóa đầu-cuối xuyên mọi thành phần.** Mỗi nơi kết thúc TLS có thể nhìn thấy plaintext trước khi tạo kết nối TLS mới tới điểm kế tiếp. Vị trí termination là **trust boundary** cần mô tả và kiểm soát.

## 2. Thuật ngữ nền tảng

| Khái niệm | Mô tả | Ví dụ |
| --- | --- | --- |
| **TLS (Transport Layer Security)** | Giao thức thiết lập kênh bảo mật giữa các điểm giao tiếp | HTTPS dùng TLS |
| **HTTPS** | HTTP chạy qua kết nối được bảo vệ bằng TLS | Browser gọi `https://api.example.invalid` |
| **TLS server authentication** | Client xác minh danh tính server dựa trên certificate và trust policy | Client xác nhận certificate hợp lệ cho hostname API |
| **mTLS (mutual TLS)** | Hai phía xác thực certificate/identity ở cấp TLS | Service mesh xác thực caller workload bằng cert |
| **Public key certificate** | Tài liệu liên kết public key với danh tính và được ký theo cơ chế PKI | Chứng chỉ X.509 của API server |
| **Private key** | Bí mật cần bảo vệ, được server dùng chứng minh sở hữu khóa trong giao thức | Khóa riêng gắn với server certificate |
| **CA (Certificate Authority)** | Thẩm quyền ký chứng chỉ trong trust hierarchy | CA công cộng hoặc CA riêng của tổ chức |
| **Trust anchor / trust store** | Nguồn khóa/chứng chỉ CA được phía xác minh tin cậy | Java trust store hoặc trust bundle của mesh |
| **SAN (Subject Alternative Name)** | Vùng định danh DNS/IP hoặc URI trong chứng chỉ | `api.example.invalid` |
| **Handshake** | Pha thỏa thuận giao thức/khóa và xác thực peer | TLS 1.3 handshake |
| **Cipher suite** | Tổ hợp thuật toán bảo vệ traffic theo phiên bản TLS | AEAD cipher suite được chính sách cho phép |
| **AEAD** | Mã hóa kết hợp bảo vệ tính toàn vẹn dữ liệu | AES-GCM hoặc ChaCha20-Poly1305 |
| **PFS (forward secrecy)** | Giảm nguy cơ giải mã traffic quá khứ nếu khóa dài hạn bị lộ sau đó, khi handshake dùng trao đổi khóa tạm thời phù hợp | TLS 1.3 thông thường với key exchange tạm thời |
| **SNI** | Tên server do client thông báo trong TLS handshake để chọn cấu hình/certificate | Nhiều virtual hosts trên cùng IP |
| **ALPN** | Thương lượng giao thức ứng dụng trên kênh TLS | HTTP/2 hoặc HTTP/1.1 |
| **TLS termination / re-encryption** | TLS kết thúc tại proxy rồi có thể mở phiên TLS khác tới backend | CDN → load balancer → API |
| **Certificate rotation/renewal** | Cấp lại/thay certificate và có thể thay private key, cập nhật trust đúng lúc | Gia hạn chứng chỉ trước khi hết hạn |

**Có chứng chỉ không có nghĩa kết nối đã được mã hóa.** Một file `server.p12` tồn tại trên đĩa chỉ là cấu hình/credential; cần xác minh thực tế listener, protocol negotiation, client verification và từng đường dữ liệu.

## 3. Mã hóa khi truyền khác mã hóa khi lưu

| Tình huống | Encryption in transit | Encryption at rest |
| --- | --- | --- |
| Client gửi số tiền tới API | Bảo vệ đoạn client–API bằng TLS | Không giải quyết nơi API ghi dữ liệu |
| Service ghi database | TLS cho kết nối app–database | Mã hóa volume/table/column ở database |
| Worker gửi message | TLS cho producer–broker và broker–consumer nếu yêu cầu | Mã hóa storage của broker và bản ghi tồn đọng |
| API upload file | TLS bảo vệ lúc upload | File cần bảo vệ trong object storage, backup và export |
| Backup chuyển sang vùng DR | TLS/tunnel an toàn cho luồng truyền | Bản backup và khóa cần bảo vệ ở điểm đến |

Một hệ thống có thể đạt mã hóa khi lưu nhưng **vẫn truyền plaintext** tới database; hoặc đạt TLS trên mọi hop nhưng vẫn có bucket object storage mở quyền đọc quá rộng. Vì thế cần **control IDs và kết luận riêng** cho lưu, truyền, truy cập, retention và ứng phó sự cố.

## 4. Threat model: kẻ tấn công có thể làm gì trên đường truyền?

### 4.1. Những giả định cần xét

Không nên mô tả “network = trusted” rồi bỏ qua những đoạn nội bộ. Đối tượng tấn công có thể là:
- Bên có khả năng quan sát lưu lượng trên mạng dùng chung hoặc vùng hạ tầng bị cấu hình sai.
- Kẻ thay đổi DNS/route/proxy, cố khiến client nối tới endpoint giả.
- Workload hoặc máy chủ nội bộ bị chiếm; có khả năng gọi một endpoint khác.
- Người có quyền thay ingress, service mesh, trust store hoặc private keys.
- CI runner có quyền cấp/sửa certificate hoặc thay cấu hình TLS.
- Kẻ lợi dụng **fallback** sang HTTP, endpoint cũ, kết nối không xác thực hostname hoặc proxy bypass.

### 4.2. Ví dụ risk scenarios

| Risk ID | Kịch bản | Hậu quả | Hướng control |
| --- | --- | --- | --- |
| **RISK-TLS-01** | Browser gửi credential hoặc dữ liệu cá nhân qua HTTP | Lộ nội dung/phiên trong phạm vi network attacker | Bắt buộc HTTPS, không gửi dữ liệu nhạy cảm trên HTTP, HSTS khi phù hợp |
| **RISK-TLS-02** | Service gọi backend plaintext sau khi gateway terminate TLS | Lộ/đổi dữ liệu ở mạng giữa các service | TLS hoặc mTLS trên hop cần bảo vệ, chặn plaintext |
| **RISK-TLS-03** | Client bỏ xác minh certificate/hostname | Có thể chấp nhận endpoint giả trong điều kiện tấn công | Trusted CA + SAN/hostname verification, negative tests |
| **RISK-TLS-04** | Worker tin mọi certificate từ trust store tự tạo không kiểm soát | Endpoint giả trong trust scope | Quản trị trust bundle, phân quyền và review |
| **RISK-TLS-05** | Private key server hoặc client bị rò | Mạo danh peer/đánh cắp kết nối trong điều kiện liên quan | Key protection, short-lived credentials, rotation, incident response |
| **RISK-TLS-06** | Cert hết hạn trong production | Mất kết nối và gián đoạn nghiệp vụ; có thể tạo áp lực tắt validation | Monitoring, renewal, overlap rollout, rollback an toàn |
| **RISK-TLS-07** | mTLS không được áp dụng trên một admin API phụ | Đường bypass tới nghiệp vụ nhạy cảm | Inventory listeners/routes và thử truy cập không có client cert |
| **RISK-TLS-08** | Kết nối PostgreSQL dùng TLS nhưng không verify server identity | Rủi ro kết nối sai backend nếu network bị can thiệp | verify-full hoặc cơ chế tương đương của driver |
| **RISK-TLS-09** | Kênh mã hóa tốt nhưng API trả dữ liệu tenant B cho tenant A | Lộ dữ liệu dù TLS hoạt động | Object-level authorization, negative tests |
| **RISK-TLS-10** | TLS được thiết lập nhưng proxy ghi raw Authorization header vào logs | Credential lộ ở điểm kết thúc TLS | Source logging policy, redaction, log access tests |

### Một sơ đồ đường gây hại

~~~mermaid
flowchart LR
    CLIENT["Client / Browser"] -->|"TLS A"| EDGE["CDN / API Gateway"]
    EDGE -->|"HTTP không mã hóa?"| APP["Spring Boot API"]
    APP -->|"TLS B?"| DB[("Database")]
    APP -->|"TLS C?"| BROKER["Message Broker"]
    BROKER -->|"TLS D?"| WORKER["Worker"]
    WORKER -->|"TLS E?"| STORE[("Object Storage")]
    EDGE --> OBS["Gateway logs / traces"]
    APP --> OBS
    ATTACKER["Network attacker / compromised workload"] -. "Quan sát, chuyển hướng, bypass" .-> APP
~~~

Mỗi nhãn TLS A/B/C/D/E là **một claim khác nhau**. Quan sát TLS A thành công không thể suy ra B, C, D, E đều mã hóa và xác minh peer. Log tại các endpoint cũng là một **đường phơi lộ dữ liệu khác** dù đường truyền TLS đã được bảo vệ.

## 5. TLS hoạt động như thế nào ở mức cần cho security assurance?

Không cần tự viết crypto để vận hành TLS, nhưng cần hiểu các bước đủ để xác định control và test phù hợp.

### 5.1. Bắt tay TLS 1.3 – diễn giải đơn giản

~~~mermaid
sequenceDiagram
    participant C as TLS Client
    participant S as TLS Server
    C->>S: ClientHello (phiên bản/khả năng, key share, SNI/ALPN khi có)
    S-->>C: ServerHello + key share
    Note over C,S: Hai phía tạo khóa phiên từ trao đổi khóa phù hợp
    S-->>C: EncryptedExtensions + Certificate + CertificateVerify + Finished
    Note over C: Kiểm tra certificate, hostname, trust, chữ ký và Finished
    C->>S: Finished
    C->>S: Application data được bảo vệ
    S-->>C: Application data được bảo vệ
~~~

Đây là hình dung luồng **full handshake TLS 1.3 với xác thực máy chủ bằng certificate**. TLS 1.3 có những trường hợp khác như PSK/resumption và mTLS, với trình tự mở rộng hoặc rút gọn. Không nên dùng sơ đồ như packet capture chính xác cho mọi phiên.

### 5.2. Certificate và xác thực peer

Client phải giải quyết ít nhất:

1. **Certificate chain có dẫn tới trust anchor phù hợp?**
2. **Certificate có còn hiệu lực** và phù hợp mục đích server authentication theo chính sách?
3. **Tên đích kết nối có khớp với định danh được phép trong SAN?** Không chỉ so sánh một string tự khai trong request.
4. **Giao thức, thuật toán và kích thước khóa** có được phép theo chính sách hiện hành?
5. **Có điều kiện bổ sung** như revocation policy, key usage, pinning/trust domain hay yêu cầu chứng chỉ tổ chức không?
6. **Ứng dụng có thật sự chấm dứt kết nối** nếu validation thất bại, hay silently fallback?

Một **chứng chỉ đã được ký bởi CA được tin** không tự chứng minh đây là **đúng host**: hostname/SAN verification vẫn cần thiết. Ngược lại, tên host trông đúng trong URL không chứng minh chứng chỉ được issuer tin cậy cấp.

### 5.3. Khóa công khai và khóa phiên

TLS thường dùng kỹ thuật **khóa bất đối xứng** và certificate để phục vụ xác thực/thiết lập tin cậy, rồi sử dụng **khóa phiên đối xứng** để bảo vệ phần lớn application data. TLS 1.3 sử dụng bộ mã hóa có xác thực (AEAD) theo cấu hình thương lượng.

**Không nên giải thích TLS đơn giản là “server gửi public key, client mã hóa toàn bộ dữ liệu bằng public key”.** Cách mô tả đó không phản ánh chính xác các giao thức TLS hiện đại, nhất là việc hai phía trao đổi khóa tạm thời và tạo traffic keys.

### 5.4. Forward secrecy và giới hạn

Với key exchange tạm thời phù hợp, việc **khóa riêng dài hạn bị lộ trong tương lai** không mặc nhiên cho phép giải mã toàn bộ traffic quá khứ đã ghi lại. Tuy nhiên, forward secrecy **không bảo vệ** nếu endpoint bị chiếm khi đang xử lý plaintext, nếu traffic keys bị lấy vào thời điểm đó, hoặc khi kênh bị terminate ở proxy không được tin cậy.

### 5.5. TLS và HTTP/3

HTTPS có thể dùng HTTP/1.1 hoặc HTTP/2 qua TLS trên TCP; HTTP/3 dùng **QUIC**, tích hợp cơ chế bắt tay/bảo vệ dựa trên TLS 1.3 nhưng **không phải TLS chạy qua một luồng TCP thông thường**. Khi kiểm tra, phải xét giao thức transport và proxy thực tế, không dựa vào một port scan TCP duy nhất để kết luận mọi đường HTTPS đều được bao phủ.

## 6. Những điều TLS không tự bảo vệ

| Giới hạn | Vì sao quan trọng? | Control bổ sung |
| --- | --- | --- |
| Plaintext tại hai endpoint | TLS bảo vệ kênh, endpoint đọc dữ liệu sau giải mã | Host security, secret handling, access control, monitoring |
| Proxy termination | Proxy/CDN có thể nhìn request/response và tạo hop mới | Trust boundary, proxy IAM, re-encryption, logging policy |
| Metadata mạng | IP/port, kích thước/lịch traffic, và có thể thông tin tên đích tùy giao thức/cấu hình vẫn quan sát được | Data minimization, kiến trúc/mạng, công nghệ bảo vệ metadata khi phù hợp |
| API phân quyền sai | TLS không quyết định tenant/object/action | App authorization, negative tests |
| Server bị chiếm | Kẻ tấn công ở endpoint có thể lấy dữ liệu sau giải mã | Runtime/IAM controls, threat detection, blast-radius limit |
| Client gửi tới nhầm endpoint tin cậy | Một đích có cert hợp lệ của chính nó có thể không phải đích nghiệp vụ mong muốn | Allowlist destination, service identity và business-level validation |
| Dữ liệu ghi log | Proxy/app có thể ghi raw payload sau TLS termination | Structured logging, redaction at source, permissions/retention |
| Dữ liệu ở backup/storage | TLS không xử lý dữ liệu khi ngừng truyền | Encryption at rest, key/retention/access controls |
| Dịch vụ ngoài phạm vi test | Có thể tồn tại admin port, legacy API hay direct IP | Asset/route inventory, bypass tests |

**TLS không phải authorization.** Một caller dùng mTLS với chứng chỉ hợp lệ vẫn cần kiểm tra **principal → action → resource → conditions** theo chính sách nghiệp vụ và IAM.

## 7. TLS, HTTPS, mTLS và các môi trường triển khai

### 7.1. HTTPS ở public entry point

Với một API công khai:

- Client phải dùng **HTTPS** cho các thao tác mang thông tin nhạy cảm.
- Certificate server phải được cấp và xác minh cho hostname mà client đang gọi.
- Có chính sách giao thức/cipher được phép, quản lý redirect và **HSTS** cho website/browser khi phù hợp.
- Cookie phiên cần các thuộc tính bảo vệ như **Secure**, HttpOnly/SameSite theo mô hình, và không gửi token nhạy cảm qua URL.
- HTTP endpoint cũ, cổng phụ và asset hostnames phải được inventoried; không chỉ kiểm tra trang chủ.
- Đường từ CDN/WAF/load balancer về origin phải được đánh giá riêng.

**Redirect từ HTTP sang HTTPS không mã hóa request HTTP đầu tiên.** Không thiết kế luồng để browser gửi mật khẩu hoặc token qua HTTP rồi mới redirect. HSTS có thể giảm rủi ro chuyển sang HTTP cho trình duyệt đã biết chính sách; thiết kế và triển khai preload cần cân nhắc phạm vi domain, độ sẵn sàng HTTPS và vận hành.

### 7.2. TLS trên kết nối nội bộ

“Trong VPC” hoặc “trên Kubernetes” chưa tự chứng minh kênh an toàn. Cần xem những mạng/host nào có thể quan sát traffic và những công cụ/hạ tầng nào được tin; theo threat model, nên áp dụng TLS hoặc mTLS phù hợp cho service-to-service, database, broker, cache và các đường quản trị.

Trường hợp một nền tảng đã cung cấp đường mã hóa hạ tầng có chứng cứ, tổ chức có thể đánh giá hiệu lực và phạm vi của cơ chế đó, nhưng không được mặc định **mọi** service path đã được bảo vệ chỉ vì sản phẩm cung cấp tính năng encryption.

### 7.3. mTLS cho service identity

Ở mTLS, server cũng yêu cầu/kiểm tra certificate của phía client; điều này có thể cung cấp **peer workload identity** ở kênh. Tuy nhiên:

- Certificate phải được cấp đúng workload và có vòng đời quản trị.
- Phải xác minh client identity theo một trust mapping/CA thích hợp.
- **Authorization** phải map identity đã được xác thực vào action/resource cụ thể.
- Nếu mTLS kết thúc ở sidecar/proxy, backend cần một **cách nhận identity đáng tin** hoặc kiểm tra quyền tại proxy theo mô hình đã được duyệt.
- Nếu tồn tại direct route bỏ qua proxy, phải chặn hoặc áp dụng authN/authZ tương đương.

**Dùng chung một client certificate cho mọi service** làm giảm khả năng phân biệt workload và tăng blast radius nếu private key bị lộ.

### 7.4. Khi nào không nên chỉ tin mTLS?

mTLS giữa `report-api` và `export-worker` không đảm bảo `export-worker` có quyền xuất báo cáo của tenant B chỉ vì nó đã kết nối. Nếu worker nhận message từ queue chứa `tenantId` do nguồn không tin cậy đưa vào, phải kiểm tra **job ownership, authorization, scope và dữ liệu** ở tầng ứng dụng.

## 8. Ranh giới TLS termination, reverse proxy và service mesh

### 8.1. Các kiểu đường truyền

~~~mermaid
flowchart LR
    BROWSER["Browser"] -->|"TLS 1"| EDGE["CDN / Ingress"]
    EDGE -->|"TLS 2 hoặc HTTP"| API["Spring Boot API"]
    API -->|"mTLS 3"| WORKER["Internal Worker"]
    API -->|"TLS 4"| DATABASE[("Database")]
    API -->|"TLS 5"| BROKER["Message Broker"]
    WORKER -->|"TLS 6"| OBJECT[("Object Storage")]
~~~

Các nhãn 1–6 **không ngầm tồn tại**. Assessor phải thu evidence về từng hop, cả khi traffic đi qua private link, proxy sidecar hay egress gateway.

### 8.2. Terminate tại ingress

Khi TLS kết thúc ở ingress:
- Ingress thấy plaintext request/response, nên nó là **điểm tin cậy** có quyền/giám sát cần quản trị.
- Ingress có thể tái mã hóa tới API bằng một TLS session mới; certificate của API phải được ingress xác minh theo chính sách.
- Nếu ingress gọi API bằng HTTP, cần **lập risk scenario và quyết định rõ ràng** về tính chấp nhận được của hop đó theo yêu cầu áp dụng; không được ghi “end-to-end encrypted”.
- Header `X-Forwarded-Proto` hoặc `X-Client-Cert` có thể được proxy thêm, nhưng backend không được tin các header này từ client không đáng tin nếu chưa khóa direct access/thiết lập trust phù hợp.

### 8.3. Service mesh

Một service mesh có thể tự cấp chứng chỉ ngắn hạn cho workload và dùng mTLS giữa proxies. Nhưng:

1. Mesh có bao phủ **mọi workload và mọi port** trong scope không?
2. Có namespace, bypass, host-network hoặc route direct nào không qua sidecar/ambient dataplane?
3. Chế độ permissive/optional có chấp nhận plaintext không?
4. Identity được gắn đúng ServiceAccount/workload, có quyền sửa mapping không?
5. Policy authorization/ingress/egress thực tế ở proxy là gì?
6. Telemetry có xác minh được TLS negotiation cho từng đường quan trọng không?
7. Trust domain, CA rotation và certificate expiry có được kiểm soát không?

Một dashboard “mTLS enabled” là **tín hiệu cấu hình**, chưa chứng minh mọi application path được mã hóa hoặc rằng mọi peer được cấp quyền nghiệp vụ.

### 8.4. Egress và bên thứ ba

Service gọi vendor API hoặc object storage cần xác minh certificate và hostname đích theo client library thực dùng, không chỉ làm phép test từ laptop. Nếu bắt buộc qua egress proxy, đánh giá:
- Ai xác minh certificate ở chỗ nào?
- Có TLS interception hay terminate/re-encrypt không?
- Proxy có quyền đọc raw payload và giữ log không?
- Có đường ra ngoài qua IP/proxy khác không?
- Vendor thay certificate/CA thì xử lý trust và outage ra sao?

**“Bên nhận có HTTPS” không đủ** nếu service sử dụng tùy chọn bỏ qua certificate validation hoặc dùng một URL HTTP ở fallback path.

## 9. Lựa chọn giao thức và cấu hình TLS theo chính sách

Không nên đưa ra bảng “cipher suite tốt vĩnh viễn” áp dụng không điều kiện; thuật toán, thư viện và yêu cầu bên ngoài thay đổi theo thời gian. Tổ chức cần có **security standard đã phê duyệt**, tham chiếu phiên bản cụ thể và kiểm thử môi trường thực tế.

### Những nguyên tắc ổn định

- Ưu tiên phiên bản TLS hiện đại được chính sách/phần mềm hỗ trợ; **TLS 1.3** thường là lựa chọn phù hợp cho hệ thống mới. **TLS 1.2** có thể cần trong môi trường tương thích nếu cấu hình và chính sách cho phép.
- Không cho phép những giao thức lỗi thời như SSLv2/SSLv3 hoặc TLS 1.0/1.1 trong hệ thống mới, trừ khi có đánh giá ngoại lệ thực sự hợp lệ theo yêu cầu áp dụng; **không báo chuẩn đã đạt** nếu vẫn phải chấp nhận phiên bản yếu.
- Dùng các bộ thuật toán **authenticated encryption** phù hợp với phiên bản TLS và thư viện đã được kiểm chứng.
- Kiểm tra hostname và trust chain ở **mọi client path**; không xử lý certificate error bằng cách `trustAll`.
- Định nghĩa rõ **policy cho client authentication**, key/cert type, CA trust bundle và cấp phát khóa.
- Nếu phải hỗ trợ legacy client, xác định phạm vi, thời hạn, control bù trừ và kế hoạch hiện đại hóa. Chấp nhận TLS yếu là **điều kiện rủi ro**, không phải cải tiến bảo mật.

### Hai nhóm lỗi nghiêm trọng

**Nhóm A — Có TLS nhưng không có xác thực đích đáng tin:** TLS encryption có thể bảo vệ kênh tới một endpoint do attacker điều khiển nếu client tin sai certificate/hostname. Phải test invalid CA, wrong hostname, expired cert.

**Nhóm B — Có xác thực đích nhưng không có coverage:** một route hoặc listener plaintext còn hoạt động, tạo đường bypass. Phải inventory mọi endpoint/hop và kiểm thử đường bị cấm, không chỉ test kết nối chính.

## 10. Quản lý certificate và private key

Một chương trình mã hóa khi truyền cần nhìn certificate/key như **tài sản bảo mật có vòng đời**, không phải file cấp một lần rồi quên.

### 10.1. Vòng đời chuẩn

~~~mermaid
flowchart TD
    A["Service identity + hostname + owner"] --> B["Cấp key/certificate theo policy"]
    B --> C["Lưu key an toàn, triển khai và thiết lập trust"]
    C --> D["Client/server validate + vận hành"]
    D --> E["Monitor expiry, rotation, revocation signals"]
    E --> F{"Có thay đổi/hết hạn/compromise?"}
    F -- "Renew/rotate" --> B
    F -- "Compromised/decommission" --> G["Thu hồi/giới hạn trust, thay khóa, kiểm chứng"]
    G --> H["Dỡ credential và review evidence"]
    F -- "Chưa" --> D
~~~

### 10.2. Quản lý khóa riêng

- **Không đưa private key vào repository, container image, build log hoặc ticket**.
- Dùng secret management/volume/bảo vệ filesystem phù hợp với workload, hạn chế quyền đọc.
- Xác định ai được phép cấp, xem, thay và thu hồi; tách quyền theo rủi ro.
- Nêu yêu cầu **key generation**, bảo quản và tình huống key compromise; có thể sử dụng HSM/KMS hoặc dịch vụ quản trị chứng chỉ theo kiến trúc.
- Tránh dùng cùng private key cho nhiều môi trường, nhất là production với development.
- Bảo vệ bản sao key ở backup và quá trình di chuyển/mount vào workload.
- Với client cert mTLS, key bị lộ có thể giúp mạo danh client trong scope; phải có incident response và kiểm thử revoke/rotation.

### 10.3. Đường tin cậy của chứng chỉ

Client sử dụng trust store hoặc trust bundle để xác minh chain. **Thêm một CA mới** có thể làm tăng số danh tính được tin, nên cần review.

- Public-facing endpoints thường dựa trên CA công cộng được thiết bị/client hỗ trợ; internal services có thể dùng private CA/mesh trust domain.
- Với private CA, phải có quy trình phân phối/cập nhật trust roots, tách ranh giới môi trường và bảo vệ quyền phát hành.
- Khi rotate CA/root, cân nhắc giai đoạn **trust overlap** để client vẫn kết nối đúng certificate trong lúc chuyển; test cả chấp nhận cert mới và từ chối cert không còn được phép.
- Đừng dùng tắt xác minh certificate/hostname làm “giải pháp tạm” khi CA chưa được import.
- **Certificate pinning** có thể giảm một số rủi ro theo threat model nhưng tạo nguy cơ outage khi rotate; không áp dụng máy móc mà không có kế hoạch rollover.

### 10.4. Hết hạn và gián đoạn dịch vụ

Một chứng chỉ hết hạn có thể khiến service production không gọi được database hoặc vendor. Cần:
1. Inventory hostname/service/client identities, expiry và owner.
2. Cảnh báo trước theo **ngưỡng do chính sách quy định**, không mặc định một số ngày cố định.
3. Tự động hóa renewal khi phù hợp, có rollback và test.
4. Xác nhận process thực sự **load certificate/key mới**; thay file không nhất thiết làm server reload.
5. Kiểm tra certificate chain, SAN, key usage, trust của client và đường API sau rotation.
6. Không tự gia hạn “thành công” chỉ vì job lấy certificate mới chạy xanh; kiểm tra effective runtime certificate.

### 10.5. Revocation và sự cố

Các cơ chế kiểm tra trạng thái certificate/revocation có thể khác nhau theo client, PKI và chính sách; **không mặc định mọi TLS client sẽ kiểm tra CRL/OCSP hoặc fail-closed** trong mọi môi trường. Trong phản ứng sự cố key compromise, cần xem **thời gian còn hiệu lực, các hệ thống tin cậy, proxy cache, certificate pinning, trust store, key rotation và quyền của các workload liên quan**.

Nếu nghi lộ private key, không chỉ thay certificate mới rồi đóng finding. Cần điều tra phạm vi lộ, thay key, xử lý trust của khóa cũ theo cơ chế khả thi, rà soát credentials và phát hiện lạm dụng trong khoảng phơi lộ.

## 11. Java 17: client HTTPS an toàn theo cơ chế mặc định

Java 17 có `java.net.http.HttpClient` hỗ trợ HTTPS với cơ chế trust và xác minh tên peer theo cấu hình TLS của JVM. Khi không có yêu cầu đặc biệt, **tránh tự cài SSLContext/TrustManager tùy biến**, vì một lỗi nhỏ có thể vô hiệu hóa xác minh server identity.

### 11.1. Ví dụ HttpClient có ràng buộc HTTPS

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import javax.net.ssl.SSLSession;

public final class HttpsClientCheck {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    public record Result(
            int httpStatus,
            String tlsProtocol,
            String cipherSuite,
            String peerPrincipal) {}

    public static void requireHttps(URI uri) {
        if (uri == null || !"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null) {
            throw new IllegalArgumentException(
                    "Endpoint phải là URL HTTPS có hostname");
        }
    }

    public Result probe(URI uri)
            throws IOException, InterruptedException {
        requireHttps(uri);

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        SSLSession session = response.sslSession()
                .orElseThrow(() -> new IllegalStateException(
                        "Không có thông tin phiên TLS"));

        return new Result(
                response.statusCode(),
                session.getProtocol(),
                session.getCipherSuite(),
                session.getPeerPrincipal().getName());
    }
}
~~~

**Ý nghĩa:** wrapper từ chối URL HTTP từ đầu, không tự theo redirect sang endpoint khác, và lấy thông tin phiên TLS **sau khi client thực hiện xác thực theo trust configuration đang dùng**. HTTP 401 hoặc 403 có thể vẫn cho thấy TLS handshake đã thành công; HTTP status **không tự là kết quả kiểm tra authorization toàn diện**.

**Các giới hạn quan trọng:**

- Code không tuyên bố một protocol/cipher là PASS theo mọi chính sách. Assessor phải so `tlsProtocol`/`cipherSuite` với baseline được phê duyệt.
- Cơ chế trust phụ thuộc **runtime JVM, trust store, system properties và mọi tùy biến ứng dụng**. Phải kiểm tra không ai vô hiệu hóa hostname/certificate verification ở cấu hình khác.
- Đây là yêu cầu HTTP demo gửi GET; không nên gửi dữ liệu thật trong phép thử. Đừng coi `probe` đã test mọi path hoặc mọi proxy/region.
- Client kết nối một endpoint thành công không chứng minh gateway → backend, service → database, broker và những cổng khác đều dùng TLS.
- Không ghi `SSLSession` hoặc cert chain có chứa thông tin không cần thiết vào log sản xuất; chỉ thu metadata cần cho evidence.
- Test integration về **wrong CA, wrong hostname, expired certificate, protocol không được phép, redirect plaintext** phải được tổ chức ở môi trường test có quyền và test server phù hợp.

### 11.2. Unit tests xác minh chính sách scheme

~~~java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.net.URI;
import org.junit.jupiter.api.Test;

class HttpsClientCheckTest {

    @Test
    void acceptsHttpsUri() {
        assertDoesNotThrow(() -> HttpsClientCheck.requireHttps(
                URI.create("https://api.example.invalid/reports")));
    }

    @Test
    void rejectsPlainHttpUri() {
        assertThrows(IllegalArgumentException.class,
                () -> HttpsClientCheck.requireHttps(
                        URI.create("http://api.example.invalid/reports")));
    }

    @Test
    void rejectsRelativeUri() {
        assertThrows(IllegalArgumentException.class,
                () -> HttpsClientCheck.requireHttps(
                        URI.create("/internal/reports")));
    }
}
~~~

Unit tests **không thực hiện kết nối TLS**. Chúng chỉ chứng minh logic không cho gửi qua scheme HTTP nếu tất cả đường gọi thực sự dùng wrapper. Cần integration và runtime tests để chứng minh chương trình không có client khác âm thầm bỏ qua xác thực.

### 11.3. Những anti-pattern nên từ chối

Không dùng các cách làm sau trong hệ thống thật:
- `TrustManager` luôn trả “trust” cho mọi certificate.
- Bỏ kiểm tra hostname hoặc cho phép mọi tên host.
- Dùng `curl -k` / client flag tương đương rồi coi kết quả là bằng chứng TLS chuẩn.
- Cho phép HTTP fallback nếu handshake HTTPS lỗi.
- Copy private key production vào repository để CI “dễ kết nối”.
- Tắt certificate verification với lời giải thích “đây là mạng nội bộ”.

Nếu test environment dùng CA tự ký, giải pháp phù hợp thường là **cấp một CA thử được quản trị và thêm CA đó vào trust store dành cho test**, vẫn kiểm tra SAN/hostname. Không dùng một bypass chung rồi quên gỡ khi deploy.

## 12. Spring Boot: TLS cho inbound service

### 12.1. Embedded server TLS – minh họa

Trong một ứng dụng Spring Boot với embedded server hỗ trợ SSL, có thể cấu hình như sau:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: "file:/etc/report-service/tls/server.p12"
    key-store-type: "PKCS12"
    key-store-password: ${SERVER_TLS_KEYSTORE_PASSWORD}
~~~

Ví dụ dùng placeholder biến môi trường lấy từ một cơ chế cấp secret phù hợp. **Không hardcode password/key** vào file cấu hình, commit, build artifact hoặc log. Đường file và certificate trong keystore phải khớp hostname thực mà client gọi.

**Điểm cần kiểm chứng:**
- Lớp runtime nào terminate TLS? Embedded server, ingress, sidecar hay load balancer?
- Có listener HTTP song song hoặc cổng quản trị/direct-IP mở mà không có chính sách tương ứng?
- Certificate đang được phục vụ có đúng SAN/chain/expiry và key usage không?
- Backend có yêu cầu mTLS cho client không, nếu tiêu chuẩn đòi hỏi?
- Secret/password được mount/cấp bởi ai, có quyền đọc đúng phạm vi không?
- Có health/metrics được bảo vệ phù hợp không?
- File/cert rotation có được server reload, và client có tiếp tục verify đúng không?

**Đừng bật TLS trong ứng dụng chỉ để “cho đủ checkbox” nếu kiến trúc đã xác định termination khác mà không có đánh giá tổng thể.** Cần xây dựng bản đồ các hop và đảm bảo mỗi hop có control tương xứng.

### 12.2. mTLS ở embedded server

Khi cần xác thực certificate phía client ở embedded server, có thể cần các cấu hình như `server.ssl.client-auth: need` và trust store của client CA theo version Spring Boot/container được sử dụng. Nhưng **mTLS chỉ có ý nghĩa nếu client certificate được kiểm tra và map sang workload identity/authorization đúng**. Nếu TLS termination xảy ra ở gateway/mesh, mTLS có thể được thực thi ở đó, không phải trực tiếp trong controller.

Không tự tin một header `X-Client-Cert` được truyền vào backend nếu client có thể gửi header đó qua direct route hoặc ingress không lọc header. Cần thiết kế cách truyền authenticated identity qua boundary đã bảo vệ.

### 12.3. Cấu hình chỉ là design/implementation evidence

Kết luận `server.ssl.enabled=true` trong source **không chứng minh production đã load cấu hình đó**. Profiles, environment variables, gateway và bản deploy khác có thể override. Phải đối chiếu **effective server configuration và handshake thực tế** ở đúng endpoint, runtime và thời gian.

## 13. TLS cho PostgreSQL, broker và các kết nối outbound

### 13.1. PostgreSQL JDBC – ví dụ cơ chế xác minh

Với PostgreSQL JDBC driver, `sslmode=verify-full` là một cách yêu cầu TLS đồng thời xác minh chứng chỉ và hostname server theo cơ chế driver. Ví dụ URL với CA file cụ thể:

~~~yaml
spring:
  datasource:
    url: "jdbc:postgresql://db.prod.example.internal:5432/reporting?sslmode=verify-full&sslrootcert=/etc/report-service/ca/db-ca.pem"
    username: "report_service"
    password: ${REPORT_DB_PASSWORD}
~~~

**Chỉ là minh họa**, không phải template tương thích mọi phiên bản driver/PKI. Hệ thống thật cần xác nhận:
- DB hostname đúng với **SAN** của certificate server.
- CA file/trust được cấp đúng scope, cập nhật và bảo vệ.
- Driver thực dùng `sslmode=verify-full` (hoặc tương đương), không bị override bởi URL/option khác.
- Kết nối DB thực tế từ ứng dụng đang dùng TLS và reject server không đúng.
- Credential DB lấy từ secret management phù hợp, không commit.
- Database, replica, failover endpoint và job backup cũng được bảo vệ theo risk.

**Không coi `ssl=true` là bằng chứng đủ cho việc xác thực hostname**, vì ý nghĩa từng flag và default khác nhau giữa driver/nền tảng. Xem đúng hợp đồng của library đang triển khai và test behavior.

### 13.2. Message broker/queue

Với Kafka, RabbitMQ hay broker khác, cần xét **ít nhất hai chiều**:

1. Producer → broker: TLS và xác thực server, client auth theo chính sách.
2. Broker → consumer: một kênh khác, có TLS, xác thực và ủy quyền tương ứng.

Nếu broker cluster có replication/inter-broker traffic hoặc management API, cần inventory các luồng đó. `SSL`, `SASL_SSL` và mTLS có ý nghĩa cấu hình khác nhau tùy sản phẩm; không thể đưa một chuỗi cấu hình áp dụng cho tất cả.

**TLS không tự giải quyết authorization của topic/queue.** Một producer được xác thực đúng vẫn cần policy publish đúng topic; consumer cần quyền đọc phù hợp. Message payload có thể còn ở disk/DLQ sau truyền và cần các control retention/at-rest khác.

### 13.3. Outbound object storage và vendor

Kiểm tra service client thực sự kết nối endpoint HTTPS, verify certificate/hostname và không chuyển sang URL HTTP khi SDK lỗi. Cần xét proxy, DNS override, bucket URL, signed URL, retry và khả năng một custom HTTP transport đã bị cấu hình trust-all.

Nếu dùng certificate pinning hoặc trust store riêng với vendor, phải có cơ chế **rotation và incident response** phù hợp để không kéo theo outage và không dẫn đến việc tắt verification khi vendor đổi certificate.

## 14. 0-RTT, resumption và nguy cơ replay

TLS hiện đại có cơ chế **session resumption** và trong một số mô hình hỗ trợ gửi dữ liệu sớm (*early data/0-RTT*). Việc bảo vệ kênh không đồng nghĩa loại bỏ mọi khả năng **replay** của yêu cầu ứng dụng.

- 0-RTT trong TLS 1.3 có những giới hạn chống replay; **không mặc định dùng cho yêu cầu tạo giao dịch/thay đổi trạng thái**.
- Với request thay đổi dữ liệu, cân nhắc tắt/chặn early data hoặc áp dụng chính sách phù hợp, kèm idempotency/anti-replay ở tầng ứng dụng.
- Không dùng “request gửi qua TLS 1.3” làm lý do bỏ kiểm tra token expiry, nonce, authorization hay tính duy nhất của giao dịch.
- Nếu proxy/CDN tự bật chế độ này, cần kiểm tra chính sách tại nơi terminate và hành vi upstream.

**Ví dụ:** nếu `POST /payments` được chấp nhận bằng replay, một attacker có thể tạo tác động nghiệp vụ dù nội dung không bị đọc trên đường truyền. TLS và business idempotency là **hai mục tiêu khác nhau**.

## 15. Mã hóa khi truyền và bài toán quản lý khóa

Trong chương **Mã hóa và khóa**, cần phân biệt:

| Loại khóa/credential | Vai trò | Điểm assurance |
| --- | --- | --- |
| Khóa riêng của TLS server | Chứng minh sở hữu danh tính server trong handshake phù hợp | Bảo quản, cấp phát, rotation, mất key, expiry |
| Chứng chỉ public và CA chain | Để bên nhận kiểm chứng public key/danh tính | Trust anchor, SAN, validity và policy |
| Session/traffic keys | Bảo vệ nội dung traffic của một phiên | Protocol/cipher phù hợp, PFS, endpoint exposure |
| Client private key (mTLS) | Chứng minh client workload identity | Phân tách workload, lưu key, revoke, identity mapping |
| CA root/intermediate key | Có quyền ký certificate trong trust domain | Hạn chế đặc quyền, tách trách nhiệm, HSM/PKI management |
| API key/OAuth token trên TLS | Xác thực/ủy quyền ở lớp ứng dụng | Không được log, scope nhỏ, rotation/revocation |
| KMS key mã hóa dữ liệu lưu | Bảo vệ dữ liệu at rest/application | Không nhầm với TLS traffic keys |

### Hai vấn đề thường bị nhầm

**Mã hóa kênh** không có nghĩa **data encryption key** của database được xử lý bởi TLS. Một key nằm trong KMS phục vụ encryption at rest có vòng đời và quyền khác TLS server private key.

**mTLS client certificate** xác thực một peer, nhưng việc thực hiện một API hành động vẫn phải kiểm tra **business authorization**. Giữ một client cert còn hạn trong lúc gỡ service account có thể khiến dịch vụ vẫn kết nối được nếu chưa có chính sách revoke/authorization đúng.

## 16. Security requirements cho encryption in transit

Các yêu cầu phải mô tả **đối tượng, hành vi, scope, tiêu chí nghiệm thu và bằng chứng**. Ví dụ dưới đây không phải bảng nghĩa vụ cố định của một chuẩn bên ngoài.

| ID | Yêu cầu có thể kiểm chứng | Control/đầu mối | Evidence cần thu |
| --- | --- | --- | --- |
| **TLS-REQ-01** | Các endpoint public mang dữ liệu nhạy cảm chỉ xử lý request qua HTTPS được xác thực | Edge/gateway TLS policy | Endpoint inventory, HTTP negative test, handshake report |
| **TLS-REQ-02** | Client xác minh server CA/trust, SAN/hostname, lifetime và policy thuật toán | TLS client library config | Negative invalid-CA/wrong-host/expired-cert tests |
| **TLS-REQ-03** | Các kết nối app→DB/broker/vendor trong scope áp dụng TLS phù hợp | Driver/SDK/network config | Connection tests, effective config, runtime session evidence |
| **TLS-REQ-04** | Những hop sau TLS termination được bảo vệ theo risk/standard đã duyệt | Re-encryption hoặc mTLS, topology controls | Route map, ingress→backend test và segmentation |
| **TLS-REQ-05** | Không có HTTP/plaintext fallback trái chính sách trên routes/listeners | Deny policy, redirect + HTTPS enforcement | Negative HTTP/bypass tests từ vùng mạng đại diện |
| **TLS-REQ-06** | Nếu yêu cầu mTLS, peer client phải được xác thực và map vào service identity được phép | CA/client cert trust, mesh policy | Valid/invalid/no-cert tests, identity/authorization evidence |
| **TLS-REQ-07** | Private keys và trust roots được quản lý đúng owner, quyền và vòng đời | Secret manager/PKI, IAM, rotation | Inventory, access review, renewal/rotation tests |
| **TLS-REQ-08** | TLS policy và chứng chỉ đang hiệu lực có giám sát hết hạn, thuật toán và drift | Observability/PKI monitoring | Alert test, effective cert snapshot, review |
| **TLS-REQ-09** | Thay ingress, proxy, client, certificate hoặc CA kích hoạt retest | CI/change management | Change ID, config diff, test/deploy refs |
| **TLS-REQ-10** | TLS termination points không log raw secrets/data ngoài phạm vi | Logging/data minimization | Synthetic marker tests, log source coverage |
| **TLS-REQ-11** | Workload sau khi được xác thực vẫn bị giới hạn theo quyền tài nguyên | App/service authorization, IAM | Positive/negative action/resource/tenant tests |
| **TLS-REQ-12** | Assessor có thể truy vết từng claim tới môi trường/phiên bản/routing thật | Evidence register | Risk-control-test-evidence mapping, reviewer signoff |

Khi yêu cầu **chỉ TLS 1.3** hay một giới hạn certificate cụ thể, tổ chức cần lấy từ **security standard áp dụng**, đưa phiên bản vào yêu cầu và test chính xác. Không ghi cứng con số không có căn cứ vào mọi tài sản.

## 17. Test plan: xác minh cả mã hóa lẫn danh tính

### 17.1. Positive, negative và failure-mode tests

| Test ID | Tình huống | Expected result |
| --- | --- | --- |
| **TLS-T01** | HTTPS endpoint hợp lệ, cert đúng hostname, CA tin cậy | Handshake thành công, giao thức/cipher theo policy |
| **TLS-T02** | Gọi endpoint bằng HTTP trực tiếp | Không truyền dữ liệu nhạy cảm dưới HTTP; endpoint/redirect theo rule |
| **TLS-T03** | Server test đưa cert từ CA không được tin | Client từ chối |
| **TLS-T04** | Server test đưa cert sai SAN/hostname | Client từ chối |
| **TLS-T05** | Server test dùng cert hết hạn/chưa hiệu lực | Client từ chối theo policy |
| **TLS-T06** | Client yêu cầu phiên bản/protocol không được phép | Handshake bị từ chối |
| **TLS-T07** | mTLS endpoint không có client certificate | Bị từ chối trước thao tác cần quyền |
| **TLS-T08** | mTLS client certificate từ CA/identity không được cấp quyền | Bị từ chối bởi trust policy hoặc authorization |
| **TLS-T09** | Gọi backend trực tiếp qua cổng HTTP không theo ingress | Bị chặn hoặc xử lý theo ngoại lệ có phạm vi được phê duyệt |
| **TLS-T10** | Kết nối PostgreSQL TLS với server đúng certificate/hostname | Thành công; actual driver session đáp ứng rule |
| **TLS-T11** | Kết nối PostgreSQL tới server giả/sai hostname | Không tiếp tục ở chế độ verify-full |
| **TLS-T12** | Producer/consumer kết nối broker | TLS và peer identity đúng cho cả các luồng trong scope |
| **TLS-T13** | Rotate cert/CA theo kế hoạch | Cert mới có hiệu lực; client không tắt verification; cert cũ xử lý đúng rule |
| **TLS-T14** | Certificate gần hết hạn hoặc renewal job thất bại | Alert đến owner theo thời hạn/cơ chế policy |
| **TLS-T15** | Gateway TLS terminate, backend không xác thực | Phát hiện khoảng trống hoặc xác minh control được phê duyệt cho hop đó |
| **TLS-T16** | SDK outbound nhận HTTP redirect hoặc endpoint HTTP fallback | Không gửi token/payload nhạy cảm qua channel trái policy |
| **TLS-T17** | Proxy/APM bật raw body logging khi xử lý TLS | Bị phát hiện; secrets và dữ liệu nhạy cảm không được ghi trái rule |
| **TLS-T18** | Client có cert mTLS hợp lệ nhưng user/resource không có quyền | Authorization vẫn từ chối |
| **TLS-T19** | Thay route, port, hostname hoặc thêm HTTP/3 endpoint | Bản đồ đường truyền và tests được cập nhật |
| **TLS-T20** | Trust store hoặc scanner mất quyền/dữ liệu nguồn | INCONCLUSIVE/FAIL theo rule, không tự ghi PASS |
| **TLS-T21** | Một key/cert bị đánh dấu compromised | Quy trình revoke/rotate, kiểm tra trust và evidence đã kích hoạt |
| **TLS-T22** | 0-RTT/early data tới thao tác không idempotent | Không chấp nhận rủi ro replay trái chính sách |
| **TLS-T23** | DR/failover chuyển kết nối sang hostname/region khác | CA/SAN/trust/TLS và IAM tiếp tục được kiểm chứng |
| **TLS-T24** | Service mesh có workload ngoài scope hoặc permissive mode | Bypass/plaintext được phát hiện, báo finding/limitation |

### 17.2. Cách thu evidence đáng tin

Một TLS scan chạy từ laptop chỉ quan sát **đường mạng của laptop tại thời điểm test**. Nó không tự đại diện:
- Service gọi backend từ Pod/region khác.
- Kết nối database trong private network.
- Traffic nội bộ sau proxy termination.
- HTTP/3 qua QUIC/UDP.
- Alternate listener ở cổng quản trị.
- Endpoint phục vụ một hostname khác, hoặc cấu hình client bỏ verification.

Phải kết hợp **cấu hình desired + actual**, **kiểm thử đường có quyền**, và **runtime session/certificate evidence** theo từng nguồn.

### 17.3. Lệnh kiểm tra thủ công trong môi trường được cấp phép

Ví dụ trên máy có OpenSSL phù hợp:

~~~bash
openssl s_client \
  -connect api.example.invalid:443 \
  -servername api.example.invalid \
  -verify_hostname api.example.invalid \
  -verify_return_error
~~~

Lệnh minh họa giúp **quan sát TLS handshake và chain/hostname verification ở phía client**, với điều kiện trust anchors của công cụ được cấu hình đúng. Nó **không phải cuộc audit đầy đủ** và không tự kiểm chứng các hop nội bộ hoặc mức độ an toàn của toàn ứng dụng. Không dùng `-verify 0` hoặc bypass verification để chứng minh control đạt.

Không kết nối tới tài sản bên ngoài mà bạn không được phép kiểm tra; dùng môi trường/endpoint đã được cấp quyền. Không lưu private key hay bearer token vào log test.

### 17.4. Kiểm tra sau thay đổi

Ví dụ sau khi thay certificate:
1. Xác nhận private key mới/hiện có được quản lý đúng policy.
2. Đối chiếu certificate đang được serve trên **từng endpoint trong inventory**, không chỉ file đã cập nhật.
3. Kiểm tra hostname, CA chain, expiry, protocol và client handshake từ điểm mạng đại diện.
4. Kiểm tra mTLS trust/identity mapping nếu có.
5. Thử app-to-DB, broker, vendor và các client/phiên bản quan trọng.
6. Kiểm tra monitoring và sự kiện lỗi trong rollout.
7. Lưu deployment/config IDs, thời gian, reviewer và các kết quả negative.
8. Nếu xuất hiện failure/bypass, tạo finding, xử lý và **retest**, không chỉ đổi dashboard xanh.

## 18. Trình bày kết luận assurance theo đúng phạm vi

Một claim quá rộng là:

> “Mọi dữ liệu của hệ thống đều được mã hóa an toàn khi truyền.”

Câu này khó chứng minh vì hệ thống có nhiều path, endpoint, client version và bên thứ ba. Một claim tốt hơn:

> **CLAIM-TLS-01:** Trong phạm vi `report-api` production deployment `D-2026-11-28`, các client HTTP được hỗ trợ kết nối qua HTTPS với server certificate có CA/hostname/validity phù hợp; gateway tới `report-api` và `report-api` tới `reporting-db` dùng kênh TLS theo baseline phiên bản được duyệt. Các endpoint và kết nối nằm ngoài phạm vi được liệt kê riêng.

**Điểm cần kiểm chứng:** claim chỉ có thể đạt nếu có hiện vật cho tất cả các đoạn được tuyên bố; không dựa vào một screenshot HTTPS ở browser.

### Chuỗi truy vết

~~~text
RISK-TLS-02: Plaintext ở hop ingress → backend
  -> OBJ-CONF-01: Không tiết lộ dữ liệu nhạy cảm trên đường truyền cần bảo vệ
  -> TLS-REQ-04: Hop sau TLS termination phải bảo vệ theo policy
  -> CTRL-TLS-04: Re-encryption + peer certificate verification
  -> TLS-T09/T15: Bypass/plaintext test từ zone được phê duyệt
  -> EV-TLS-04: Route map + config runtime + test + deployment ID
  -> FIND-TLS-04: Backend HTTP vẫn reachable ngoài điều kiện được phép
  -> REMED-TLS-04: Giới hạn route và bổ sung TLS, deploy, retest
  -> RISK-REVIEW-04: Residual risk, exception và quyết định có thẩm quyền
~~~

### Mẫu YAML evidence record

Các giá trị trong dấu `<...>` là placeholder, **không phải bằng chứng đã được kiểm tra**:

~~~yaml
assessment_id: TLS-ASSURANCE-001
module: SECURITY_SECURITY_ASSURANCE
standard_ref: "<TLS_BASELINE_ID_AND_VERSION>"
environment: production
service: report-api
claim_id: CLAIM-TLS-01
risk_ids: [RISK-TLS-01, RISK-TLS-02, RISK-TLS-03]
requirement_ids: [TLS-REQ-01, TLS-REQ-02, TLS-REQ-03, TLS-REQ-04]
control_ids: [CTRL-TLS-01, CTRL-TLS-04]
scope:
  asset_inventory_ref: "<ENDPOINT_AND_HOP_INVENTORY>"
  paths:
    - "browser -> api-gateway"
    - "api-gateway -> report-api"
    - "report-api -> reporting-db"
  hostnames: ["<AUTHORIZED_SERVICE_NAMES>"]
  excluded_paths: "<KNOWN_NOT_ASSESSED_ENDPOINTS_OR_REGIONS>"
architecture:
  trust_boundary_ref: "<APPROVED_DFD>"
  termination_points: ["<PROXIES_LOAD_BALANCERS_INGRESSES>"]
  certificate_owner: "<PKI_OWNER>"
  trust_store_policy_ref: "<APPROVED_TRUST_CONFIGURATION>"
implementation:
  code_commit: "<GIT_COMMIT>"
  artifact_digest: "<IMAGE_OR_BUILD_DIGEST>"
  deployment_id: "<ACTUAL_PRODUCTION_DEPLOYMENT>"
  config_snapshot_ref: "<RUNTIME_TLS_AND_ROUTE_CONFIGURATION>"
  certificate_metadata_ref: "<SANITIZED_CERT_CHAIN_AND_EXPIRY>"
verification:
  tested_at: "<ISO_8601_UTC>"
  test_ids: [TLS-T01, TLS-T02, TLS-T03, TLS-T04, TLS-T09, TLS-T10]
  positive_result_ref: "<TRUSTED_ENDPOINT_HANDSHAKE>"
  negative_result_refs:
    - "<WRONG_CA_AND_HOSTNAME_REJECTION>"
    - "<HTTP_OR_BYPASS_REJECTION>"
  observed_protocols_ref: "<NEGOTIATED_PROTOCOL_REPORT>"
  result: "<PASS_FAIL_INCONCLUSIVE>"
  reviewer: "<AUTHORIZED_ASSESSOR>"
control_operations:
  certificate_rotation_ref: "<LAST_VERIFIED_RENEWAL>"
  expiry_alert_ref: "<ALERT_TEST_AND_OWNER>"
  incident_response_ref: "<KEY_COMPROMISE_RUNBOOK>"
findings: ["<FINDING_IDS_IF_ANY>"]
exceptions: ["<APPROVED_EXCEPTION_IDS_IF_ANY>"]
residual_risk: "<RISK_REVIEW_RATIONALE>"
limitations: "<GAPS_IN_PATHS_TIME_OR_CLIENT_COVERAGE>"
reassessment_triggers:
  - "Certificate/key/CA/issuer/trust store change"
  - "New endpoint, proxy, mesh, client, DB, broker or DR region"
  - "Security incident, vulnerability, expired certificate or drift"
~~~

### Ba lớp bằng chứng

| Lớp | Hiện vật | Hạn chế |
| --- | --- | --- |
| **Design** | DFD, security standard, approved TLS baseline, PKI design | Chưa chứng minh đã triển khai |
| **Implementation/test** | IaC, Spring Boot config, JDBC parameters, CI/integration tests | Chưa chứng minh runtime thực không drift |
| **Operational effectiveness** | TLS handshake từ zone thích hợp, cert metadata, effective route/IAM, negative tests, rotation event | Không chứng minh các endpoint/môi trường chưa thử |

Một bản ghi certificate expiry có thể chứng minh **thời hạn cert** nhưng không chứng minh client thực sự xác thực hostname hoặc traffic trong hop đang dùng TLS. Cần nêu **mục tiêu của từng evidence** và không ghép những hiện vật thiếu liên quan thành một kết luận PASS.

## 19. Trạng thái assessment và xử lý ngoại lệ

| Trạng thái | Nghĩa | Cách xử lý |
| --- | --- | --- |
| **PASS** | Có evidence đầy đủ trong phạm vi rằng yêu cầu được đáp ứng | Giữ scope, phiên bản, thời điểm và reviewer |
| **FAIL** | Quan sát thấy sai, ví dụ plaintext bypass hoặc client chấp nhận cert giả | Finding, ưu tiên rủi ro, remediation, retest |
| **INCONCLUSIVE** | Không đủ evidence hoặc thiếu path/zone/client coverage | Không tự đánh dấu PASS; bổ sung kiểm chứng |
| **NOT_RUN/OVERDUE** | Hoạt động kiểm tra/rotation chưa chạy hoặc quá lịch | Triage và đánh giá rủi ro khoảng trống |
| **EXCEPTION_APPROVED** | Quyết định có thẩm quyền cho một sai lệch trong điều kiện/thời hạn cụ thể | Giữ trạng thái kỹ thuật riêng và theo dõi residual risk |

### Ví dụ một finding

**FIND-TLS-01:** gateway nhận HTTPS nhưng route tới `report-api` bằng HTTP ở một namespace production không thuộc ngoại lệ được phê duyệt.

Các bước:
1. Xác minh **đường, namespace, source/destination, dữ liệu, actor, thời gian** và liệu route còn dùng không.
2. Đánh giá rủi ro: ai có thể quan sát/sửa traffic trên hop, có dữ liệu nhạy cảm không, có control hạ tầng nào đã được xác minh?
3. Thiết kế biện pháp sửa phù hợp: TLS re-encryption/mTLS hoặc cơ chế được phê duyệt; không mặc định bật một flag là đủ.
4. Triển khai theo change management; kiểm tra certificate/hostname/trust và network path.
5. Thử positive hợp lệ và negative plaintext/direct-bypass.
6. Kiểm tra không phá health checks, rollout và failover theo kiến trúc.
7. Lưu runtime config, test results, deployment ID, reviewer và scope.
8. Đóng finding khi có **retest chứng minh control đạt**, hoặc xử lý theo quyết định rủi ro riêng; không tự chuyển FAIL sang PASS vì ticket đã đóng.

### Compensating control không tự bằng primary control

Trong một legacy service chưa hỗ trợ TLS ở hop cụ thể, có thể cân nhắc network isolation/tunnel bảo vệ, workload segmentation và detection như các **ứng viên biện pháp giảm rủi ro**. Nhưng phải chứng minh chúng xử lý đúng đường gây hại, không có bypass, có quyền phê duyệt, thời hạn và lộ trình sửa chính. Không tự tuyên bố “ở private subnet nên tương đương TLS” khi yêu cầu bắt buộc là mã hóa và xác thực peer.

## 20. Vận hành liên tục: certificate, config và drift

Security assurance cho TLS là **một hoạt động liên tục**, không chỉ kiểm tra một lần khi khởi tạo dịch vụ.

### Trigger cần đánh giá lại

| Trigger | Câu hỏi cần xác minh | Evidence cập nhật |
| --- | --- | --- |
| Thêm endpoint/hostname/region | Endpoint có TLS, đúng cert và trong inventory không? | Route list, handshake, SAN/CA test |
| Thay ingress/CDN/load balancer | TLS terminate ở đâu, hop tiếp theo bảo vệ thế nào? | DFD/config diff, runtime traffic tests |
| Thay HTTP client/JDK/library | Default trust, protocol, redirect và hostname verification còn đúng? | Dependency/build, integration negatives |
| Thay PostgreSQL driver/DB endpoint | verify-full và CA trust có còn áp dụng? | Effective connection config, spoof/hostname test |
| Thay broker/queue/storage | Kênh truyền, authN/authZ và retention của payload | Connection matrix, access tests |
| Rotate leaf certificate | Client verify được cert mới, cũ xử lý đúng không? | Cert metadata, handshake, renewal record |
| Rotate CA/trust bundle | Có trust overlap, cert cũ hết tin đúng thời điểm? | Trust config, positive/negative tests |
| Compromised private key | Blast radius, thời gian phơi lộ, revoke/rotation và incident | Incident evidence, trust update, retest |
| Enable service mesh/permissive | Có đường plaintext hoặc identity mapping sai? | Mesh policy, bypass test, telemetry |
| Thay DR/failover | TLS/cert DNS đúng tại region dự phòng? | Failover rehearsal, RTO/RPO và TLS verification |
| Mất scanner/collector | Dashboard còn thấy đủ nguồn để chấm PASS không? | Source health, coverage, finding |
| Audit finding/exception hết hạn | Có còn residual risk cần quyết định lại? | Remediation, retest, approval |

### Dashboard đúng nên thể hiện

- **% hops được inventoried** và % hops đã có kiểm chứng TLS.
- Endpoint/certificate gần hết hạn, owner và thời gian còn lại.
- Protocol/cipher ngoài chính sách trên **đường đang chạy**.
- Route plaintext hoặc client bypass verification đã phát hiện.
- Mức bao phủ integration/negative tests theo environment/version.
- Tuổi và kết quả của runtime evidence; lần rotation/retest gần nhất.
- Findings/exception chưa đóng, deadline và thẩm quyền chấp nhận rủi ro.
- Tình trạng nguồn scan và telemetry; **INCONCLUSIVE khi nguồn mất dữ liệu**.

Không đưa ra KPI “100% cert chưa hết hạn” rồi suy ra “mã hóa khi truyền an toàn”: certificate còn hạn vẫn có thể sai hostname, client bỏ verification hoặc proxy gọi backend HTTP.

## 21. Phân vai và quyền ra quyết định

| Vai trò | Trách nhiệm | Evidence điển hình |
| --- | --- | --- |
| **Service Owner / Tech Lead** | Liệt kê luồng dữ liệu, endpoint, mục tiêu bảo vệ và dependency | DFD, inventory, requirement mapping |
| **Developer** | Client/server TLS sử dụng thư viện an toàn, không bypass trust; test tích hợp | Source/PR, Java/JUnit tests, build refs |
| **Platform/Ops/SRE** | Ingress, proxy, service mesh, TLS policies, cert deployment, database/broker connectivity | Runtime configs, cert inventory, monitoring, rotation |
| **PKI/IAM/Secrets Team** | CA, trust roots, certificate/key issuance, quyền và lifecycle | PKI policy, key access review, rotation records |
| **Security/AppSec** | Threat model, standard, negative tests, chứng minh control effectiveness | Risk register, test plans, findings |
| **Data/Privacy Owner** | Phân loại dữ liệu đi qua kênh, đánh giá ảnh hưởng và chia sẻ | Data catalog, purpose và sensitivity mapping |
| **Risk Owner / Thẩm quyền** | Quyết định xử lý hoặc chấp nhận residual risk trong quyền hạn | Exception/risk treatment, expiry |
| **Assessor/Audit** | Đánh giá design và operating effectiveness, giới hạn, retest | Assessment/evidence register, reviewer record |

Một tổ chức nhỏ có thể gộp vai trò, nhưng cần chỉ rõ **ai cấp/tin CA, ai triển khai, ai kiểm chứng, ai review và ai có quyền chấp nhận rủi ro**. Không để người đang gặp outage tự quyết định “tắt SSL verification” mà không có cơ chế kiểm soát/phê duyệt phù hợp.

## 22. Case study: HTTPS xanh nhưng backend còn plaintext

### Bối cảnh

Một nền tảng thương mại điện tử chạy Java/Spring Boot:
- Browser gọi `https://shop.example.invalid` qua CDN.
- CDN kết thúc TLS rồi gọi một API gateway.
- Gateway kết nối `orders-api`.
- `orders-api` dùng PostgreSQL và xuất event sang message broker.
- `export-worker` tiêu thụ event để tạo CSV khách hàng.
- DR region có một bản sao database và một ingress dự phòng.

Dashboard ban đầu ghi “HTTPS enabled: PASS”, nhưng audit kỹ thuật tìm thấy:

1. Gateway tới `orders-api` đang dùng HTTP vì cấu hình legacy.
2. JDBC URL chứa `ssl=true` nhưng chưa xác minh cấu hình hostname/trust thực tế.
3. Consumer ở một namespace gửi message tới broker qua listener plaintext.
4. Java client kết nối vendor dùng một custom `TrustManager` từng được viết để bỏ certificate verification trong test; cấu hình đó đã vào production.
5. Chứng chỉ ingress DR sắp hết hạn và không có owner.
6. Gateway có chế độ debug ghi raw `Authorization` header.
7. Một API quản trị có direct IP route không qua gateway.

### Phân tích findings

| Finding | Vì sao nguy hiểm? | Bằng chứng/test cần |
| --- | --- | --- |
| **F-TLS-01:** HTTP gateway→backend | HTTPS ở browser không bảo vệ hop sau termination | Route/traffic config, backend HTTPS/mTLS handshake, bypass test |
| **F-TLS-02:** DB TLS chưa verify hostname | Có TLS chưa chắc kết nối đúng DB | JDBC effective settings, wrong-host/CA tests |
| **F-TLS-03:** broker listener plaintext | Data khách hàng có thể nằm trong traffic không bảo vệ | Listener inventory, producer/consumer config và runtime tests |
| **F-TLS-04:** trust-all client | Endpoint giả có thể được chấp nhận | Code review, invalid-CA/hostname negatives, deployed client |
| **F-TLS-05:** DR certificate thiếu owner | Rủi ro outage khi failover | Inventory/expiry monitoring, failover + TLS test |
| **F-TLS-06:** token trong gateway log | TLS termination đưa secret vào kho log | Logging config, marker tests, incident assessment |
| **F-TLS-07:** direct IP admin route | Bypass gateway/mTLS/policy được tuyên bố | Route map, direct access negative test, IAM authorization |

### Hướng khắc phục có kiểm soát

1. **Lập inventory luồng:** mọi host, cổng, proxy, DB, broker, DR, vendor và actor; phân loại dữ liệu đi qua.
2. **Ưu tiên các exposure nghiêm trọng:** route plaintext chứa dữ liệu khách hàng, trust-all verification, direct admin path, token log.
3. **Thiết kế chuẩn theo từng hop:** xác thực server CA/hostname, TLS/re-encryption hoặc mTLS theo trust model, không có fallback trái policy.
4. **Sửa client và driver:** loại bỏ custom trust-all, dùng trust store được quản trị, kiểm tra driver xác minh hostname.
5. **Sửa ingress/broker:** đóng listener không được phép, tăng coverage tới backend/consumer, kiểm tra đường bypass.
6. **Sửa logging:** ngừng log raw token; đánh giá khoảng dữ liệu đã lộ, rotate/revoke nếu cần theo incident workflow.
7. **Quản lý certificate DR:** xác định owner và hệ thống tự động renewal/alert, test failover theo phạm vi có quyền.
8. **Triển khai và retest:** kiểm tra certificate đúng tên, wrong-CA/wrong-host rejection, mọi hop, direct route và nguồn log.
9. **Ghi evidence:** config snapshot, deployment/image digest, test run, reviewer, limitations và residual risk.
10. **Đóng findings đúng cách:** không chuyển PASS chỉ vì một kết nối HTTPS thành công; phải có bằng chứng từng control.

### Kết luận assurance có thể viết

> Trong phạm vi các luồng `browser→edge`, `edge→orders-api`, `orders-api→database` và `orders-api→broker` ở production deployment được đánh giá, TLS đã được xác minh theo tiêu chuẩn áp dụng, các certificate không hợp lệ bị từ chối trong negative tests có kiểm soát, và không còn plaintext direct route thuộc phạm vi. Luồng DR/vendor/legacy chưa kiểm chứng được ghi riêng.

Kết luận này **chỉ hợp lệ khi có hiện vật thực** cho các đường được nêu, không được lấy lời mô tả case study làm kết quả audit của hệ thống thật.

## 23. Bài tập thực hành

**Tình huống:** tổ chức có dịch vụ `payment-api` bằng Spring Boot, `billing-worker`, PostgreSQL, message broker, API gateway và vendor fraud service. Trong đợt review:

- Client→gateway dùng HTTPS, nhưng gateway→payment-api có một hop HTTP.
- Một microservice dùng `HttpClient` với custom trust store nhưng không có owner/review.
- Kết nối DB dùng flag `ssl=true` không rõ có verify hostname.
- Broker có cổng SSL và cổng plaintext, cả hai đều có thể truy cập từ worker.
- mTLS chỉ áp dụng cho một số Pod; namespace khác dùng permissive mode.
- Certificate service sắp hết hạn và renewal job chạy nhưng ứng dụng không tự reload.
- Debug log của proxy có Authorization header.
- DR region có hostname khác với SAN của certificate hiện tại.

### Yêu cầu

1. Vẽ **DFD có ranh giới tin cậy và các điểm TLS termination** cho toàn luồng thanh toán.
2. Viết ít nhất **sáu risk scenarios** có actor, data, path và hậu quả; phân biệt network confidentiality với authorization.
3. Xác định **security requirements** cho client/gateway/backend/DB/broker/vendor và DR; nêu control owners.
4. Thiết kế **tám negative tests**, ít nhất gồm plaintext route, invalid CA, wrong hostname, missing client cert, direct-bypass, protocol downgrade, expired certificate và broker plaintext.
5. Đưa ra phương án **rotation cert/CA** tránh outage nhưng không tắt verification; chỉ rõ evidence runtime chứng minh cert mới được dùng.
6. Phân tích vì sao `ssl=true`, “HTTPS xanh” và dashboard mesh “mTLS enabled” **chưa đủ để chấm PASS toàn bộ**.
7. Viết **assurance record** có risk/requirement/control/test/evidence IDs, actual deployment, hostnames, certificate metadata, reviewer, kết luận và limitations.
8. Đề xuất cách xử lý proxy log chứa token mà không sao chép thêm raw secrets vào ticket.
9. Khi DR failover, cần kiểm tra lại những hop, hostnames, trust stores và service identities nào?
10. Chỉ rõ ai có quyền quyết định ngoại lệ khi chưa thể nâng cấp một legacy service lên TLS và hồ sơ ngoại lệ phải có điều kiện gì.

### Hướng giải mẫu

| Vấn đề | Điều cần khắc phục | Bằng chứng |
| --- | --- | --- |
| Gateway→backend HTTP | Re-encryption/mTLS hoặc giải pháp đáp ứng policy; chặn bypass | Route map, handshake, negative test |
| Trust store không owner | Quản lý CA, quyền thay và test wrong CA/host | Trust policy, config, invalid-cert rejection |
| DB `ssl=true` mơ hồ | Dùng cơ chế verify-full phù hợp driver/PKI | JDBC config, handshake và wrong-host test |
| Broker plaintext | Kiểm kê producer/consumer, đóng hoặc cô lập listener trái policy | Listener inventory, connection policy, negative test |
| Mesh permissive | Tăng enforcement ở workload trong scope, xác minh no-plain route | Mesh config, runtime telemetry, bypass test |
| Cert không reload | Thiết kế reload/rollout, kiểm chứng cert mới thực được serve | Rotation run, cert metadata/expiry, client test |
| Token trong proxy log | Bỏ raw header, đánh giá incident và rotate/revoke khi cần | Sanitized config/test và timeline |
| DR SAN không khớp | Chỉnh issuance và hostname/trust tương ứng, test failover | DR endpoint handshake và continuity evidence |

**Câu hỏi nâng cao:** một đội áp dụng mTLS tới mọi workload nhưng vẫn cho `billing-worker` có quyền đọc tất cả tài khoản ngân hàng và xuất dữ liệu mọi tenant. Liệu control mã hóa khi truyền có thể PASS trong phạm vi đã kiểm tra không, trong khi **security assurance tổng thể vẫn FAIL**?

**Định hướng:** có thể PASS cho **transport encryption/peer authentication** ở các đường đã kiểm chứng, nhưng **least privilege/object authorization** là control khác và chưa đạt. Không dùng sức mạnh của mTLS để hợp thức hóa quyền truy cập quá rộng.

## 24. Những sai lầm thường gặp

| Ngộ nhận | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| “Có ổ khóa trên browser là mọi service được mã hóa.” | Chỉ phản ánh đường client tới endpoint đang xem | Inventoried hops, route tests và runtime evidence |
| “Gateway có TLS nên backend HTTP luôn an toàn.” | Proxy terminate, plaintext có thể đi qua boundary khác | Đánh giá hop/risk, re-encryption/mTLS khi cần |
| “Tự ký cert nghĩa là phải tắt validation.” | Có thể cấu hình trust anchor thử và giữ SAN verification | Managed test CA/trust store, negative tests |
| “Có cert ký bởi CA là đủ.” | Phải xác minh đúng hostname, thời hạn và policy | Chain/SAN/usage/expiry, handshake tests |
| “Hostname check làm khó dev, production bật sau.” | Test không tìm được lỗi, dễ lọt trust-all code | Xác thực ở mọi môi trường với PKI phù hợp |
| “mTLS đồng nghĩa có quyền vào mọi API nội bộ.” | Xác thực peer không thay object/resource authorization | Principal mapping và policy checks |
| “TLS 1.3 giải quyết gian lận giao dịch.” | Replay/idempotency và business authorization thuộc lớp khác | Transaction controls, anti-replay khi cần |
| “ssl=true nghĩa là verify server identity.” | Cấu hình driver khác nhau, flag mơ hồ | Verify-full/tương đương và wrong-host tests |
| “Có file certificate mới là rotation xong.” | Server có thể chưa reload hoặc client chưa tin CA mới | Runtime cert, client tests, expiry alert |
| “Chứng chỉ chưa hết hạn nghĩa là kênh an toàn.” | Sai SAN/CA, weak protocol, bypass hoặc private key lộ | Policy + tests + operational evidence |
| “Mạng nội bộ không cần mã hóa hay xác thực.” | Compromised workload/insider có thể quan sát, giả mạo | Threat model và bảo vệ theo boundary |
| “Mesh dashboard báo xanh là không có plaintext.” | Per-workload và per-route policy có thể khác | Permissive/bypass validation |
| “TLS giúp token không lộ ở log.” | Điểm terminate nhìn thấy plaintext, log có thể ghi token | Source logging policy và test |
| “TLS thành công chứng minh API phân quyền đúng.” | TLS không kiểm tra tenant/object/action | Security authorization tests độc lập |
| “Có scan một IP là đủ chứng minh toàn bộ hệ thống.” | Còn hostname, zone, port, proxy, DB, broker, QUIC | Inventory + multi-zone tests + limitations |
| “Cert expired chỉ là vấn đề availability.” | Có thể dẫn tới bypass verification trong lúc xử lý sự cố | PKI lifecycle, no-bypass rule, incident response |
| “Exception được duyệt tức control PASS.” | Chấp nhận residual risk khác hiệu lực kỹ thuật | Giữ trạng thái thực và approval riêng |
| “Đã sửa manifest thì finding có thể đóng.” | Bản chạy/route có thể vẫn sai hoặc chưa deploy | Actual runtime config, test, reviewer |
| “Không thấy plaintext trong capture tức không có.” | Capture có thể sai interface/zone, thiếu nguồn | Coverage/health, kết luận INCONCLUSIVE nếu thiếu |

## Ghi nhớ

- **Mã hóa khi truyền** bảo vệ dữ liệu **trên đoạn kết nối đã được xác thực và mã hóa**; không thay mã hóa khi lưu, object authorization, bảo vệ log hoặc security controls tại endpoint.
- **TLS đúng cần xác minh peer identity**: certificate chain, trust anchor, SAN/hostname, thời hạn và thuật toán theo chính sách; chỉ dùng HTTPS hoặc `ssl=true` không đủ bằng chứng.
- **Mỗi TLS termination và hop** là một đơn vị cần phân tích, triển khai và kiểm thử riêng: client, ingress, service, database, broker, storage, vendor và DR.
- **mTLS xác thực cả client và server**, nhưng vẫn cần map workload identity vào quyền hạn và ngăn các đường bypass.
- **Private keys, CAs, certificates và trust stores** có owner, quyền, rotation/renewal, cảnh báo hết hạn và quy trình khi compromise; cert mới phải được xác minh **đang có hiệu lực tại runtime**.
- **Mã hóa khi truyền là một control trong chuỗi security assurance**: risk → security requirement → control → positive/negative tests → evidence → audit finding → remediation/retest.
- **Không có evidence đủ không được tự kết luận PASS**; phải báo đúng FAIL/INCONCLUSIVE, giới hạn scope và residual risk, rồi đánh giá lại khi có thay đổi mạng, workload, issuer, cert, SDK, gateway hoặc hệ thống dự phòng.
