# Quản lý chứng chỉ và vòng đời TLS

Một ứng dụng Java trên Azure nhận HTTPS qua Azure Front Door, đi tiếp đến Application Gateway rồi tới các Pod trên Azure Kubernetes Service (AKS). Khi chứng chỉ TLS của tên miền hết hạn, người dùng có thể gặp cảnh báo trình duyệt dù ứng dụng và database vẫn khỏe mạnh. Khi chứng chỉ đã được gia hạn trong Azure Key Vault nhưng gateway vẫn phục vụ bản cũ, lỗi lại nằm ở cơ chế đồng bộ/triển khai. Nếu kỹ sư xử lý bằng cách tắt kiểm tra chứng chỉ trong Java, hệ thống có thể hoạt động tạm thời nhưng mất cơ chế xác thực danh tính máy chủ.

**Quản lý chứng chỉ và vòng đời TLS** vì vậy không chỉ là thao tác mua/chèn một tệp PFX. Đó là quy trình từ **xác định danh tính và domain**, tạo/nhận **cặp khóa**, yêu cầu **Certificate Authority (CA)** cấp chứng chỉ, bảo vệ khóa riêng, triển khai tại đúng điểm kết thúc TLS, kiểm tra chuỗi tin cậy, theo dõi thời hạn, gia hạn/luân chuyển, xác minh client thực nhận chứng chỉ mới và thu hồi/thay thế khi có sự cố.

Bài học thuộc chương **Secret, khóa và chứng chỉ** của mô-đun **CLOUD_PROVIDERS_AZURE**. Trong lộ trình khám phá Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, compute, storage và dữ liệu, việc bảo vệ TLS là điều kiện cơ bản để triển khai, giám sát, vận hành và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

> **Phạm vi:** Bài dùng thuật ngữ TLS hiện đại và các sản phẩm Azure như **Key Vault, App Service, Azure Front Door, Application Gateway, AKS**. Chính sách thời hạn chứng chỉ công khai, khả năng tự động gia hạn, các loại managed certificate, SKU/tier, API, IAM và lịch đồng bộ có thể thay đổi. Không mặc định mọi dịch vụ Azure có cùng quy trình. Các giá trị hostname, vault, file và đường dẫn là ví dụ lab; không có thao tác nào được thực thi lên Azure khi chỉ đọc bài.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **TLS, HTTPS, X.509 certificate, private key, CA và certificate chain**.
2. Phân biệt **server TLS**, **mutual TLS (mTLS)**, xác thực ứng dụng và phân quyền người dùng.
3. Hiểu **Subject Alternative Name (SAN)**, hostname verification, SNI, Extended Key Usage (EKU), validity và trust store.
4. Phân biệt **certificate, key và secret** trong Azure Key Vault cùng với exportability/HSM.
5. Chọn giữa **Azure-managed certificate** và **bring your own certificate (BYOC)** cho dịch vụ phù hợp.
6. Thiết kế TLS ở **App Service, Azure Front Door, Application Gateway, AKS/Ingress** và kết nối tới backend.
7. Lập kế hoạch cấp mới, kiểm định, phân phối, gia hạn, luân chuyển, thu hồi và khôi phục chứng chỉ.
8. Chẩn đoán TLS handshake, chain, expiration, DNS/SNI và Java truststore bằng các công cụ read-only.
9. Tạo metrics, cảnh báo, runbook và kiểm thử rotation không gián đoạn.
10. Tránh những lỗi như tắt xác minh certificate, làm lộ private key hoặc tin rằng **Private Endpoint = TLS**.

## 1. TLS giải quyết vấn đề gì?

**Transport Layer Security (TLS)** tạo kênh giao tiếp bảo mật giữa client và server, thường dùng cho HTTPS. TLS hiện đại hướng đến:

- **Confidentiality:** mã hóa nội dung trao đổi.
- **Integrity:** phát hiện nội dung bị sửa trong quá trình truyền.
- **Server authentication:** client xác minh server đang giao tiếp là đúng danh tính được cấp chứng chỉ.
- **Optional client authentication:** mTLS cho phép server xác minh certificate của client khi được cấu hình.

~~~text
Browser / Java client
          |
          | HTTPS (TLS)
          v
Azure Front Door / Application Gateway / App Service
          |
          | Có thể có TLS phiên thứ hai
          v
Backend Java API / AKS Pod
~~~

**TLS không tự phân quyền theo người dùng**. Một website có chứng chỉ hợp lệ vẫn có thể có lỗi authorization, dữ liệu trả nhầm tenant hoặc API endpoint dễ bị lạm dụng. HTTPS bảo vệ kênh truyền và xác nhận peer theo mô hình trust, còn **Entra ID, OAuth/OIDC, RBAC, application authorization** giải quyết các lớp khác.

## 2. Thuật ngữ cơ bản trong TLS/PKI

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Public key** | Khóa công khai liên kết với chứng chỉ |
| **Private key** | Khóa riêng phải được bảo vệ, dùng để chứng minh quyền sở hữu khóa |
| **X.509 certificate** | Tài liệu số do CA ký, chứa public key, danh tính và các thuộc tính |
| **Certificate Authority (CA)** | Tổ chức/hệ thống ký và cấp chứng chỉ |
| **Root CA** | Trust anchor, thường có trong client trust store |
| **Intermediate CA** | CA trung gian ký leaf/server certificates |
| **Leaf/server certificate** | Chứng chỉ gắn với endpoint HTTPS cụ thể |
| **CSR** | Certificate Signing Request: yêu cầu CA cấp cert cho public key/danh tính |
| **SAN** | Subject Alternative Name: tên DNS/IP được chứng chỉ xác nhận |
| **SNI** | Server Name Indication: hostname client gửi trong quá trình TLS để chọn chứng chỉ |
| **TLS termination** | Nơi một phiên TLS được giải mã/kết thúc |
| **mTLS** | Hai phía xác thực bằng certificates, theo cấu hình |
| **Trust store** | Tập CA/cert tin cậy của client/server |
| **Key store** | Nơi giữ khóa và chứng chỉ của một bên, theo loại keystore |

**Không nhầm certificate với private key.** Chứng chỉ công khai có thể chia sẻ để client kiểm tra, nhưng **private key tuyệt đối không được đưa vào log, repository hoặc gửi qua chat**.

## 3. Certificate chain hoạt động ra sao?

Trong hệ thống PKI công khai, chứng chỉ server thường được ký bởi CA trung gian, CA trung gian được root CA xác nhận:

~~~text
Trusted Root CA (trust anchor trên client)
           |
           | ký/ủy quyền
           v
Intermediate CA
           |
           | ký
           v
Server certificate: api.example.com
           |
           | dùng private key tương ứng
           v
Azure HTTPS endpoint
~~~

### Client cần kiểm tra những gì?

1. Chữ ký và chuỗi từ leaf đến một trust anchor đáng tin.
2. **Hostname** của URL khớp SAN trong leaf certificate.
3. Thời điểm hiện tại nằm trong **Not Before/Not After** (có tính đến clock).
4. Chứng chỉ dùng đúng mục đích, chẳng hạn serverAuth.
5. Thuật toán và tham số mật mã được TLS stack chấp nhận.
6. Revocation/policy checks theo cơ chế, cấu hình và khả năng của client.

### Server nên gửi chain nào?

Thông thường server gửi leaf và các intermediate cần thiết. Root CA thường đã có ở client và **không nhất thiết phải gửi** trong server certificate chain. Thiếu intermediate có thể làm một số clients báo lỗi trust dù browser khác vẫn hoạt động nhờ cache.

**Không sửa bằng cách thêm leaf certificate của một website lạ vào trust store production** nếu chưa xác minh danh tính/nguồn cấp và quy trình trust.

## 4. Một TLS handshake theo góc nhìn vận hành

~~~text
Client                                   Server / Gateway
   |                                           |
   | ClientHello (TLS versions, ciphers, SNI)  |
   +------------------------------------------>|
   | ServerHello + certificate chain           |
   |<------------------------------------------+
   | Validate chain, hostname, dates, policy   |
   |                                           |
   | Key exchange + handshake verification     |
   |<=========================================>|
   |                                           |
   | Encrypted application data (HTTP)         |
   |<=========================================>|
~~~

Đây là sơ đồ **khái niệm**, không phải thứ tự mọi bản tin TLS 1.2/1.3. TLS 1.3 có handshake/key schedule khác TLS 1.2, và certificate/client-auth exchanges thay đổi theo chế độ.

### Tại sao quan trọng?

- **CertificateExpired** xuất hiện trước khi HTTP request được xử lý xong.
- Lỗi **SNI/hostname** có thể khiến gateway trả chứng chỉ của domain khác.
- **Handshake timeout** khác lỗi application 500.
- Ngay cả khi TLS thành công, backend vẫn có thể trả 401/403/503 vì application.

## 5. TLS 1.2, TLS 1.3 và cấu hình giao thức

Trong những hệ thống hiện đại, ưu tiên **TLS 1.3** khi toàn bộ chuỗi hỗ trợ, duy trì **TLS 1.2** khi cần cho clients được phê duyệt. Vô hiệu hóa các phiên bản lỗi thời theo chính sách bảo mật và khả năng dịch vụ.

| Thành phần | Cần quyết định |
|---|---|
| Front Door/App Gateway/App Service | Minimum TLS version và policy/cipher support theo SKU |
| Backend Java | JDK, JSSE/TLS protocols và server library |
| Java HTTP client | Truststore, hostname verification, TLS compatibility |
| Legacy device | Có yêu cầu phiên bản TLS cũ không; nên cô lập hoặc nâng cấp |
| Compliance | Chính sách FIPS/ciphers/key sizes được phê duyệt |

Không chọn cipher suite dựa trên một bài blog cũ; Azure managed services có mức kiểm soát cipher/policy khác nhau, và các chuẩn bảo mật phát triển theo thời gian.

### TLS termination có thể lặp lại

Client → Front Door là một phiên TLS; Front Door → Application Gateway/Origin có thể là phiên TLS thứ hai; gateway → backend có thể là phiên TLS thứ ba. **Mỗi phiên cần certificate validation và trust boundary phù hợp.**

## 6. SAN, CN và xác minh hostname

Chứng chỉ cho HTTPS phải chứa danh tính endpoint phù hợp. Trong ứng dụng hiện đại, **SAN DNS entries** là cơ chế chính để xác minh hostname; không dựa vào Common Name (CN) đơn độc.

Ví dụ:

~~~text
Certificate SAN:
  DNS:api.example.com
  DNS:catalog.example.com

Client kết nối:
  https://api.example.com      -> tên có trong SAN
  https://admin.example.com    -> không khớp SAN
~~~

### Một số lỗi phổ biến

- URL trỏ tới **IP** nhưng certificate chỉ chứa DNS SAN.
- Dùng CNAME khác nhưng cert không chứa hostname mà client thực truy cập.
- Kết nối tới Private Endpoint bằng IP riêng, bỏ qua FQDN/SNI.
- Dùng wildcard không đúng cấp tên.
- Giao diện quản trị/health endpoint dùng tên miền chưa có trong SAN.

**Không tắt hostname verification** để tránh lỗi. Sửa certificate SAN, hostname, DNS hoặc cách cấu hình client/gateway.

## 7. Wildcard certificate và giới hạn

Chứng chỉ wildcard như **\*.example.com** thường dùng cho các subdomain một cấp, ví dụ **api.example.com** hoặc **shop.example.com**, nhưng không mặc định bao phủ **example.com** hoặc **a.b.example.com**.

### Ưu điểm

- Dùng một chứng chỉ cho nhiều hostname cùng cấp.
- Giảm số chứng chỉ cần triển khai trong một số kiến trúc.
- Thuận tiện khi số subdomain lớn và cơ chế issuance hỗ trợ.

### Rủi ro

- Một private key dùng tại nhiều endpoints làm tăng **blast radius** nếu bị lộ.
- Renewal thất bại ảnh hưởng nhiều services.
- Không phải managed certificate product nào cũng hỗ trợ wildcard.
- Chứng chỉ wildcard không tự cấp quyền DNS hoặc định tuyến cho mọi subdomain.

**Đừng dùng wildcard làm mặc định** nếu mỗi ứng dụng có yêu cầu cô lập private key khác nhau. Có thể chọn leaf certificate riêng cho từng domain khi quản trị tự động hóa đủ tốt.

## 8. Validity, expiry và certificate lifetime

Chứng chỉ X.509 có:

- **Not Before:** thời điểm bắt đầu hợp lệ.
- **Not After:** thời điểm hết hiệu lực.
- Thuộc tính key usage, EKU, SAN và issuer.

~~~text
Certificate timeline:
    Issue          Valid period                Expire
      |------------------------------------------|
      |                     |                    |
      |                Renewal window            |
      |                     |                    |
      +---------------------+--------------------+
~~~

### Vì sao không đợi đến ngày hết hạn?

Gia hạn cần thời gian xác thực tên miền/CA, tạo phiên bản mới, deploy qua Azure gateway, cache propagation, rolling restart và kiểm thử. Nếu vừa đổi cert vừa đổi private key, các clients/backend giữ kết nối cũ có thể cần reconnect.

**Thời hạn tối đa của chứng chỉ công khai có thể được CA/browser ecosystem điều chỉnh**; không cố định một con số 1 năm/90 ngày trong runbook mà không kiểm tra quy định và issuer hiện hành.

## 9. Certificate fingerprint, serial number và version

Hai chứng chỉ cùng SAN và cùng CA vẫn có thể khác nhau:

- **Serial number** của chứng chỉ.
- Fingerprint/hash của DER certificate.
- **Not After** và thời hạn mới.
- Public key và private key nếu rekey.
- Issuer/intermediate chain.
- Key Vault certificate version.

Khi xác minh rotation, không chỉ nhìn web “vẫn HTTPS xanh”. Hãy đối chiếu **fingerprint/serial/Not After** tại điểm client truy cập thực tế để chứng minh gateway đã phục vụ bản mới.

### Fingerprint không phải secret

Fingerprint SHA-256 của **public certificate** có thể dùng để đối chiếu trong logs/runbooks, nhưng không đưa private key/password/PFX vào cùng bản ghi.

## 10. TLS và mTLS khác nhau thế nào?

**TLS thông thường:** client xác minh server certificate. **mTLS:** server đồng thời yêu cầu và xác minh client certificate.

~~~text
Server TLS:
  Java client ------ verify server certificate ------> API

Mutual TLS:
  Java client <----- verify server certificate ------> API
  Java client ------ present client certificate -----> API
  API              ------ verify client certificate
~~~

### Khi nào dùng mTLS?

- Service-to-service authentication trong môi trường kiểm soát.
- B2B integration yêu cầu xác thực client certificate.
- API gateway chấp nhận client identities từ CA được tin cậy.
- Một số service mesh hoặc workload identity patterns.

### mTLS không thay OAuth/Entra ID

mTLS xác minh **client sở hữu private key tương ứng chứng chỉ** và thuộc trust policy được chấp nhận. API vẫn cần xác định caller được phép truy cập tài nguyên nào, tenant nào và thực hiện hành động gì. Certificate authentication và OAuth có thể bổ sung cho nhau.

## 11. Ba kiểu khóa/chứng chỉ thường bị nhầm

| Loại | Mục đích | Ví dụ |
|---|---|---|
| **Server TLS certificate** | Client xác minh HTTPS server | api.example.com |
| **Client mTLS certificate** | Server xác minh client | partner-processor |
| **Code signing certificate** | Ký mã/phần mềm | Signing release artifact |
| **Document signing certificate** | Ký tài liệu | Chứng từ số |
| **CA certificate** | Ký/xác minh các chứng chỉ khác | Corporate root CA |

Các loại có **Extended Key Usage (EKU), key usages và trust policy khác nhau**. Không dùng một chứng chỉ chỉ có clientAuth để thay cho serverAuth nếu TLS stack/CA policy không cho phép.

### Nguy cơ dùng chung private key

Dùng cùng một private key cho web server, code signing và mTLS là lựa chọn rủi ro và thường không phù hợp policy. Tách theo mục đích, danh tính, vòng đời và trust boundary.

## 12. Quản lý certificate lifecycle là một state machine

~~~text
Inventory & ownership
         |
         v
Policy: domain, CA, key type, validity, usage
         |
         v
Generate key / CSR / domain validation
         |
         v
Issue certificate / import to approved store
         |
         v
Validate chain, SAN, key pair, EKU and formats
         |
         v
Deploy to TLS endpoints
         |
         v
Monitor serving certificate & expiry
         |
         +---- Renew/rekey -> test -> rotate -> old-version cleanup
         |
         +---- Incident -> revoke/replace -> investigate
         |
         v
Retire certificate and key safely
~~~

### Mỗi bước cần một owner

- **Domain owner:** duy trì DNS/CA validation.
- **PKI/security team:** issuer, algorithm, policy và private-key protection.
- **Platform team:** Key Vault, gateway, ingress, rotation.
- **Service owner:** endpoint behavior và client compatibility.
- **SRE/on-call:** cảnh báo, runbook, rollback và incident response.

**Không nên để chứng chỉ production phụ thuộc vào email cá nhân của một kỹ sư đã nghỉ việc**. Owner, renewal automation và alert receiver cần thuộc quy trình vận hành tổ chức.

## 13. Inventory: muốn gia hạn phải biết đang dùng chứng chỉ nào

Một bảng inventory tối thiểu:

| Trường | Ví dụ |
|---|---|
| Domain/FQDN | api.example.com |
| Environment | production |
| TLS endpoint | Front Door custom domain |
| Upstream/backend TLS | Application Gateway → AKS ingress |
| Issuer | Public CA / corporate CA |
| Certificate SAN | api.example.com |
| Validity | Not Before/Not After từ certificate thật |
| Store/reference | Key Vault certificate/secret version hoặc managed cert |
| Owner | Platform/SRE team |
| Renewal mode | Managed automatic / automated BYOC / manual |
| Alert channel | On-call + security |
| Rotation test date | Lần gần nhất xác minh |
| Blast radius | Những hostnames/apps dùng cùng certificate |

### Vì sao nhiều loại inventory?

Một ứng dụng có thể dùng một chứng chỉ ở Front Door nhưng lại có **chứng chỉ backend khác** tại Application Gateway/AKS. Khi kiểm tra từ Internet, bạn chỉ thấy cert của edge; backend certificate có thể sắp hết hạn mà chưa có cảnh báo nếu không inventory toàn bộ TLS hops.

## 14. Chứng chỉ do Azure quản lý hay tự quản lý?

Có hai nhóm chiến lược phổ biến:

| Cách | Lợi ích | Điều cần kiểm tra |
|---|---|---|
| **Azure-managed certificate** | Azure xử lý cấp/gia hạn ở những endpoints hỗ trợ | Domain eligibility, SKU, SAN/wildcard, renewal dependencies, vendor behavior |
| **BYOC (bring your own certificate)** | Tổ chức kiểm soát CA, tên miền, private key policy và lifecycle | Key Vault, renewal, service sync, network/IAM, handling PFX |
| **Internal/private CA** | Phù hợp mTLS và internal PKI khi clients được provision trust | Trust anchors, distribution, CRL/OCSP, governance |

### Quy tắc chọn

- Với custom public domain và service hỗ trợ managed TLS đầy đủ, managed certificate thường giúp giảm thao tác thủ công.
- Với yêu cầu issuer đặc biệt, mTLS, wildcard hoặc chính sách bảo mật khóa riêng, BYOC có thể cần thiết.
- Với backend private FQDN hoặc internal clients, có thể cần internal CA và cơ chế quản lý trust riêng.

**Không có một “chứng chỉ Azure” dùng được trên mọi dịch vụ**. Front Door, App Service, Application Gateway và AKS có cách cấp, nhập, gắn domain, đọc Key Vault và gia hạn khác nhau.

## 15. Certificate Authority và domain validation

Để một public CA cấp chứng chỉ cho **api.example.com**, requester phải chứng minh có quyền kiểm soát tên miền theo phương pháp CA hỗ trợ, ví dụ:

- **DNS validation:** tạo TXT hoặc các bản ghi theo yêu cầu.
- **HTTP validation:** đặt nội dung xác minh tại đường dẫn/host theo chuẩn và sản phẩm.
- **Email/domain-based method:** tùy CA/chính sách hiện hành.
- **ACME challenges:** HTTP-01 hoặc DNS-01 theo CA/integration.

### Quy trình

~~~text
Domain owner
    |
    +-- Authorize issuance request
    +-- Prove DNS/HTTP control
    |
    v
CA issues signed certificate
    |
    v
Key Vault / managed TLS endpoint
    |
    v
HTTPS serving validation
~~~

Domain validation có thể thất bại vì CNAME/DNS TXT thiếu, DNS propagation, DNS delegation sai, web route bị chặn, CAA policy hoặc domain ownership thay đổi.

### Wildcard và DNS-01

Theo cách sử dụng ACME phổ biến, **DNS-01** là lựa chọn cần thiết cho chứng chỉ wildcard; không mặc định HTTP-01 sẽ đáp ứng mọi wildcard validation. Khi dùng DNS automation, danh tính cập nhật DNS chỉ nên có quyền trong zone cần thiết, không cấp Owner subscription.

## 16. CSR và private key

**CSR (Certificate Signing Request)** chứa public key và các thông tin được CA dùng để xét yêu cầu cấp chứng chỉ; nó được ký bằng private key của requester.

~~~text
Generate private key  ---- never export carelessly ----+
       |                                               |
       v                                               |
Create CSR (public key + requested names)             |
       |                                               |
       v                                               |
CA validates & signs                                   |
       |                                               |
       v                                               |
Leaf certificate + chain                               |
       |                                               |
       +---- paired with same private key -------------+
       |
       v
TLS endpoint
~~~

### Những câu hỏi khi sinh key

1. Ai sinh khóa: Azure Key Vault, HSM, CA, pipeline hay dịch vụ managed certificate?
2. Khóa có **exportable** không, và service đích có yêu cầu exportable PFX?
3. Khóa được bảo vệ/backup theo chính sách nào?
4. Có cần rekey mỗi lần gia hạn không?
5. Khóa thuộc domain/workload/issuer nào?
6. Nếu khóa bị lộ, có thể thay thế toàn bộ endpoints dùng khóa trong bao lâu?

**CSR không chứa private key**, nhưng tệp PFX/PKCS#12 thường **có thể chứa private key** và cần bảo vệ như secret.

## 17. RSA, ECDSA và tương thích client

Các loại public-key algorithms thường dùng trong TLS certificates bao gồm **RSA** và **ECDSA/EC**. Lựa chọn ảnh hưởng tới compatibility, hiệu năng và chính sách bảo mật.

| Tiêu chí | RSA | ECDSA/EC |
|---|---|---|
| Hỗ trợ clients | Rộng, tùy key size/policy | Tốt trên clients hiện đại, cần kiểm tra legacy |
| Kích thước key/signature | Thường lớn hơn theo mức bảo mật tương đương | Thường nhỏ hơn |
| Policy/CA | CA và endpoint phải hỗ trợ | CA và endpoint phải hỗ trợ |
| Azure gateway support | Theo SKU/configuration | Theo SKU/configuration |
| Khả năng rotation | Tùy nền tảng và key management | Tùy nền tảng và key management |

Không hard-code yêu cầu key type từ một hệ thống nếu tất cả clients chưa được kiểm thử. Chọn thuật toán, key size/curve và hash theo policy hiện hành và khả năng của **CA + Azure TLS endpoint + clients**.

### Không tái sử dụng khóa vô thời hạn

Dù một cert được gia hạn với cùng key pair, chiến lược **rekey** định kỳ giúp giới hạn tác động nếu private key bị lộ. Tuy nhiên đổi key có thể ảnh hưởng certificate pinning/private key access, cần test trước.

## 18. Định dạng chứng chỉ: PEM, DER, PFX/PKCS#12

| Định dạng | Thường chứa | Lưu ý |
|---|---|---|
| **PEM** | Cert/public key/private key dạng Base64 bọc header theo nội dung | Kiểm tra file cụ thể có private key hay không |
| **DER** | Bản mã nhị phân ASN.1 của cert/key | Một định dạng encoding, không tự chỉ rõ trust |
| **PFX/PKCS#12** | Container có thể chứa cert chain và private key | Password, quyền truy cập và bảo vệ như secret |
| **JKS** | Java keystore dạng Java-specific | Có thể chuyển sang PKCS12 theo nhu cầu |
| **PKCS#11/HSM** | Giao diện tới private key được bảo vệ | Không mặc định có thể export ra PFX |

Ví dụ PEM certificate:

~~~text
-----BEGIN CERTIFICATE-----
... nội dung public certificate ...
-----END CERTIFICATE-----
~~~

Ví dụ PEM private key (không in nội dung thật):

~~~text
-----BEGIN PRIVATE KEY-----
... dữ liệu bí mật, KHÔNG đưa vào Git/log ...
-----END PRIVATE KEY-----
~~~

**Một tệp có đuôi .pem không tự bảo đảm an toàn**. Nếu chứa private key, nó vẫn là dữ liệu bí mật.

## 19. Azure Key Vault: certificate, key và secret

**Azure Key Vault** cung cấp các nhóm đối tượng có vai trò khác nhau:

~~~text
Azure Key Vault
       |
       +-- Certificates
       |     Certificate metadata, X.509 public part,
       |     issuer/renewal policy and versions
       |
       +-- Keys
       |     Cryptographic key material/operations,
       |     optionally HSM-backed/non-exportable
       |
       +-- Secrets
             Arbitrary secret values; certificate
             backing secret may represent PFX/PEM
             depending on key/export policy
~~~

Khi tạo/import **Key Vault certificate**, dịch vụ có thể liên kết tới các đối tượng **key** và **secret** có cùng certificate identity/version theo cơ chế Key Vault. **Không được giả định mọi certificate có private key exportable trong backing secret**: chính sách exportability, loại khóa/HSM và cách tạo certificate rất quan trọng.

### Quyền đọc không giống nhau

- Quyền xem **certificate metadata** không tự là quyền lấy private-key-bearing secret.
- Một gateway tham chiếu **Key Vault secret** có thể cần quyền **get secret**, không chỉ certificate read.
- Azure management-role **Reader** trên resource group không mặc nhiên đọc được mọi Key Vault data-plane secret.

Sử dụng Azure RBAC hoặc Key Vault access policy theo mô hình được vault hỗ trợ và chính sách tổ chức. Không cấp toàn bộ Key Vault Administrator cho runtime chỉ để đọc một certificate.

## 20. Certificate policy trong Key Vault

Khi tổ chức quản lý chứng chỉ qua Key Vault, chính sách có thể mô tả:

- **Issuer** hoặc kiểu self-signed/CA-integrated theo dịch vụ.
- Subject và **SANs** theo chức năng hỗ trợ.
- **Key type/size/curve**, exportability và key reuse.
- Validity period theo issuer/policy.
- **Lifetime actions**: notification hoặc auto-renew khi issuer/integration hỗ trợ.
- Secret content type như PFX/PEM theo workflow.
- Enabled/disabled, versions và expiration metadata.

### Self-signed khác public CA-signed

Chứng chỉ self-signed được tạo trong Key Vault **không tự được browsers công cộng tin cậy**. Có thể dùng nó cho lab/internal PKI khi trust được quản lý, nhưng không dán self-signed vào public website rồi tắt certificate validation.

### Auto-renew có điều kiện

Key Vault chỉ có thể tự cấp/gia hạn khi **issuer configuration và certificate policy** hỗ trợ đường đi đó. Nếu certificate được import từ external CA mà không có integrated renewal workflow, Key Vault không tự gọi CA và lấy PFX mới chỉ vì expiration sắp đến.

**Một lifetime action gửi email/notification không đồng nghĩa certificate đã gia hạn hoặc đã được Azure gateway triển khai.**

## 21. Key Vault certificate version và secret version

Một chứng chỉ có thể trải qua các phiên bản:

~~~text
Vault certificate: api-tls
    |
    +-- version V1: expires earlier
    |
    +-- version V2: issued/renewed
    |
    +-- version V3: rekeyed and renewed
~~~

Khi service tích hợp Key Vault, cần biết nó tham chiếu:

- **Versionless identifier**: có thể theo dõi phiên bản mới theo cơ chế service integration.
- **Version-specific identifier**: gắn chặt một version; cần cập nhật reference khi rotation.
- **Uploaded PFX**: gateway có thể giữ bản sao đã upload, không tự lấy Key Vault version mới.

### Bẫy nguy hiểm

Key Vault hiển thị certificate V2 còn hạn không có nghĩa Front Door/Application Gateway/Ingress đang phục vụ V2. **Xác nhận deployed/served certificate qua điểm TLS thật** sau khi rollout và cache/propagation.

## 22. Exportable và non-exportable keys

Một **non-exportable key** phù hợp một số quy trình mật mã/HSM khi private key không được xuất ra ngoài. Nhưng nhiều TLS endpoint nhận chứng chỉ dạng **PFX chứa private key**, đặc biệt trong các workflow BYOC truyền thống.

### Nguyên tắc thiết kế

1. Nếu endpoint yêu cầu PFX/private key, không chọn non-exportable key rồi giả định Key Vault sẽ cung cấp PFX có khóa.
2. Nếu security policy bắt buộc key non-exportable, cần chọn service/integration có cơ chế **signing/handshake sử dụng key không xuất** được hỗ trợ, hoặc thay đổi kiến trúc.
3. Nếu import PFX exportable, đặt quyền, audit và retention chặt; tránh tải file về laptop.
4. Managed TLS ở edge có thể giúp giảm việc tổ chức tự phân phối private key.

**Không thể làm một private key không xuất được trở nên exportable bằng cách đổi file extension.** Khả năng này phụ thuộc loại khóa và chính sách lúc tạo/import.

## 23. Managed certificate trên Azure App Service

**Azure App Service** cung cấp các đường cấu hình TLS cho custom domains, trong đó có khả năng **App Service managed certificate** ở những trường hợp đủ điều kiện và các cách nhập/chọn certificates khác.

~~~text
Public DNS custom domain
       |
       v
Azure App Service hostname binding
       |
       +-- App Service managed certificate (nếu đủ điều kiện)
       |
       +-- Imported/BYOC certificate
       |
       v
HTTPS client traffic
~~~

### Managed certificate có ưu điểm gì?

- Giảm thao tác cấp/gia hạn và quản lý file private key tại ứng dụng.
- Có thể tích hợp với hostname binding và platform TLS termination.
- Giảm rủi ro quên thay cert nếu domain/binding và nền tảng vẫn đủ điều kiện.

### Không giả định tính năng áp dụng mọi trường hợp

Kiểm tra **SKU/plan, custom domain ownership/validation, wildcard support, loại hostname, TLS binding và lifecycle** theo tài liệu App Service hiện hành. Đừng dùng App Service managed certificate như một chứng chỉ tổng quát có thể export sang AKS/Java truststore.

### Điều cần theo dõi

- Hostname binding không bị thay đổi ngoài ý muốn.
- Domain validation/DNS còn hợp lệ.
- HTTPS ở custom domain thật có chain và Not After phù hợp.
- Managed renewal không có warning hoặc pending state.

## 24. App Service BYOC và Key Vault

Khi tổ chức dùng certificate của CA/issuer riêng, App Service có những cơ chế nhập/quản lý certificate, bao gồm những luồng hỗ trợ tích hợp Key Vault theo tính năng/plan.

~~~text
Approved CA
     |
     v
Certificate + private key (PFX được bảo vệ)
     |
     v
Azure Key Vault hoặc App Service certificate store
     |
     v
App Service custom hostname + TLS/SSL binding
     |
     v
Client receives server certificate
~~~

### Cần phân biệt

- **Upload/import certificate** có thể tạo một bản certificate ở App Service, không phải mọi thay đổi Key Vault đều được đồng bộ tức thì.
- **App Service Key Vault references cho app settings** (để lấy secret) không đồng nghĩa cơ chế **TLS certificate binding**. Chúng là những tính năng khác nhau.
- Nếu dùng chứng chỉ quản lý bên ngoài, renewal automation phải bao gồm **re-import/sync/bind** theo workflow được hỗ trợ.

### Deployment slots

Slot staging/production có hostname/certificate bindings và application settings khác nhau. Trước swap, kiểm tra custom domain, TLS binding và sticky settings. Không coi swap code là thao tác tự chuyển chứng chỉ sang đúng hostname trong mọi topology.

## 25. Azure Front Door: TLS tại edge

**Azure Front Door** xử lý ingress HTTP(S) toàn cầu ở edge; custom domains có thể dùng **Front Door-managed certificates** hoặc **BYOC** theo SKU/tính năng hỗ trợ.

~~~text
Internet users
      |
      | TLS #1: public custom domain
      v
Azure Front Door (managed cert hoặc BYOC)
      |
      | TLS #2 tới origin nếu cấu hình HTTPS
      v
Application Gateway / App Service / AKS origin
~~~

### Hai chứng chỉ, hai lần kiểm tra

1. **Client → Front Door:** certificate cho public hostname, ví dụ **api.example.com**.
2. **Front Door → origin:** certificate và hostname validation của origin, theo origin configuration.

Public certificate còn hạn không đảm bảo origin certificate còn hạn. Nếu backend/origin certificate hết hạn, Front Door có thể báo origin TLS health/error dù client thấy edge cert hợp lệ.

### Managed certificate

Khi Front Door cấp và gia hạn cert, tổ chức vẫn phải duy trì DNS/domain validation và kiểm tra custom domain trạng thái hoạt động. **Managed không có nghĩa có thể bỏ inventory/monitoring**.

### BYOC

Khi dùng Key Vault-backed certificate, cần đúng Key Vault integration/identity/permissions, certificate format và chính sách rotation. Khả năng tự lấy phiên bản mới, lịch polling và thay đổi provisioning state phải kiểm tra theo SKU/docs.

## 26. Azure Application Gateway: listener và backend TLS

**Application Gateway** thường có HTTPS listener để nhận kết nối client, routing rules và backend HTTP settings cho các backend pools.

~~~text
Client
   |
   | HTTPS #1
   v
Application Gateway HTTPS listener
   | certificate for public/internal host
   |
   +-- Optional WAF/routing
   |
   | HTTPS #2 / re-encryption nếu cấu hình
   v
Backend server / AKS ingress / App Service
   | backend certificate & hostname validation
   v
Java app
~~~

### Những chỗ phải cấu hình

- Listener hostname và certificate phù hợp SAN/SNI.
- TLS policy/minimum version/cipher suite theo SKU.
- Backend protocol **HTTP hoặc HTTPS** theo security requirement.
- Backend hostname/SNI dùng đúng tên chứng chỉ.
- Trust settings/backend trusted root khi dùng private CA.
- Health probe host/header/path phù hợp backend.

**Cấu hình HTTPS listener không tự đảm bảo App Gateway → backend cũng được mã hóa.** Khi yêu cầu end-to-end TLS phải kiểm tra từng hop.

## 27. Application Gateway tích hợp Key Vault

Trong các cấu hình/SKU được hỗ trợ, Application Gateway có thể tham chiếu **certificate nằm trong Azure Key Vault** thay vì chỉ upload PFX thủ công.

~~~text
Key Vault certificate
    |
    v
Key Vault backing secret (PFX có private key, nếu tương thích)
    |
    | Key Vault secret ID/reference
    v
Application Gateway (user-assigned managed identity)
    |
    | authorized secret GET + approved network path
    v
HTTPS listener serves certificate
~~~

### Những điều kiện đáng nhớ

1. Application Gateway SKU/version phải hỗ trợ Key Vault integration.
2. **User-assigned managed identity** được gắn theo workflow hỗ trợ.
3. Identity có quyền truy cập **backing secret** theo RBAC/access policy tương ứng.
4. Chứng chỉ có private key **exportable/usable PFX** theo yêu cầu tích hợp.
5. Key Vault network/firewall/Private Endpoint/DNS cho phép dịch vụ truy cập theo kiến trúc được hỗ trợ.
6. Key Vault resource/secret không bị disable/deleted/expired.
7. Nếu dùng versionless secret ID, kiểm tra cơ chế/lịch lấy phiên bản mới thực tế.

### Sai lầm thường gặp

- Chỉ cấp quyền **Certificate Reader** nhưng gateway cần lấy backing secret.
- Chọn key **non-exportable** rồi trông đợi PFX có private key.
- Tham chiếu **version-specific secret ID**, gia hạn V2 nhưng gateway tiếp tục dùng V1.
- Vault networking khóa đường truy cập từ gateway.
- Xác minh Key Vault V2 mà quên kiểm tra certificate thực ở listener.

**Đừng giả định thời gian đồng bộ cố định cho mọi deployment**. Hãy dùng tài liệu theo SKU/tính năng, kiểm tra trạng thái listener và chủ động xác minh qua TLS handshake thật sau rotation.

## 28. AKS và điểm kết thúc TLS

Ứng dụng Java/Spring Boot chạy trong AKS có nhiều khả năng nhận traffic:

- HTTPS kết thúc tại **Azure Front Door/Application Gateway**, sau đó chuyển đến Pod bằng HTTP hoặc HTTPS.
- HTTPS kết thúc tại **Ingress controller** bên trong/đi kèm AKS.
- HTTPS kết thúc tại **Gateway API implementation** hoặc một application proxy được hỗ trợ.
- Pod Java tự phục vụ HTTPS, thích hợp một số mô hình end-to-end hoặc mTLS.
- **Service mesh** tạo TLS/mTLS nội bộ theo cơ chế/mesh đang dùng.

~~~text
                      Internet
                         |
                         v
                    Front Door
                         |
                 HTTPS / origin cert
                         v
                    App Gateway
                         |
                 HTTPS / internal cert
                         v
                     AKS Ingress
                         |
                 HTTP / HTTPS / mTLS
                         v
                    Spring Boot Pod
~~~

### Chọn nơi kết thúc TLS

| Vị trí | Ưu điểm | Điểm cần chú ý |
|---|---|---|
| **Front Door** | Edge HTTPS, routing/WAF theo SKU | Origin TLS và domain validation riêng |
| **Application Gateway** | L7 ingress, WAF/routing tích hợp Azure | Listener và backend TLS configuration |
| **AKS ingress** | Điều khiển certificate/hosts theo Kubernetes | Secret rotation và controller reload |
| **Pod Java** | TLS tới ứng dụng, kiểm soát trust trực tiếp | Keystore distribution, CPU, cert hot reload |
| **Service mesh** | mTLS workload-to-workload | CA/trust rotation, mesh policy và quản trị phức tạp |

Đừng triển khai đồng thời nhiều TLS terminators mà không vẽ sơ đồ rõ: mỗi điểm kết thúc là một **trust boundary** và có thể có chứng chỉ khác nhau.

## 29. Kubernetes TLS Secret: cấu trúc và rủi ro

Với Ingress controller hỗ trợ Secret kiểu Kubernetes, một TLS Secret thường có:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: catalog-tls
  namespace: catalog-lab
type: kubernetes.io/tls
data:
  tls.crt: BASE64_LEAF_AND_CHAIN_PLACEHOLDER
  tls.key: BASE64_PRIVATE_KEY_PLACEHOLDER
~~~

**Đây là manifest minh họa; các giá trị placeholder không phải Base64 hợp lệ để deploy.** Trong môi trường lab, dùng công cụ/cert controller được phê duyệt để tạo Secret, không commit private key vào Git.

### Những điểm quan trọng

- **tls.crt** thường cần leaf certificate và intermediates phù hợp thứ tự mà ingress/controller hỗ trợ.
- **tls.key** chứa private key tương ứng với leaf.
- Ingress resource tham chiếu Secret trong phạm vi namespace theo cơ chế controller.
- Namespace/RBAC ảnh hưởng quyền đọc Secret; không phải ai có quyền xem Deployment cũng được đọc Secret.
- Base64 là **encoding**, không phải bảo mật hay mã hóa.
- Encryption-at-rest của Kubernetes Secret và quyền truy cập etcd cần được kiểm soát.

### Khi thay Secret

Không mặc định controller sẽ reload đúng lúc trên mọi phiên bản. Một số controllers theo dõi Secret và cập nhật certificate động; những triển khai khác có thể cần reload/rollout. **Test serving certificate từ endpoint** mới là nghiệm thu, không phải chỉ nhìn Secret đã đổi.

## 30. cert-manager: tự động hóa chứng chỉ trong Kubernetes

**cert-manager** là một controller phổ biến trong Kubernetes để quản lý cấp/gia hạn Certificates theo cấu hình **Issuer/ClusterIssuer** và nguồn cấp (ACME, CA, Vault và các integrations hỗ trợ).

~~~text
Kubernetes Certificate resource
           |
           v
cert-manager controller
           |
           +--> Issuer / ClusterIssuer
           |        |
           |        +--> ACME/public CA
           |        +--> Internal/private CA
           |
           v
TLS Secret containing issued certificate/key
           |
           v
Ingress/Gateway controller uses Secret
~~~

### Những gì cert-manager giúp thực hiện

- Theo dõi yêu cầu cấp chứng chỉ và hạn dùng.
- Tự động tạo/điều phối CSR/challenges theo issuer.
- Gia hạn trước khi hết hạn theo configuration.
- Cập nhật Kubernetes Secret khi có phiên bản mới.
- Cung cấp status/events để giám sát issuance failures.

### Những gì vẫn cần thiết kế

- Quyền DNS solver và việc bảo vệ API token khi dùng DNS-01.
- Issuer config, allowed domains, CAA/validation.
- Ingress controller có reload cert mới thực sự không.
- Private-key rotation policy, certificate chain và CA trust.
- HA của controller, quota ACME/rate limits và disaster recovery.
- Version compatibility giữa Kubernetes, ingress, cert-manager và issuer.

**cert-manager không phải dịch vụ TLS certificate do Azure quản lý chung cho mọi endpoint**; nó quản lý resources theo Kubernetes và external issuers mà cluster cài đặt.

## 31. AKS Key Vault Secrets Store CSI Driver

Trong AKS, **Secrets Store CSI Driver** với Azure Key Vault provider có thể mount secrets/certificates/keys vào Pod theo các tính năng hỗ trợ.

~~~text
Azure Key Vault certificate/secret
           |
           | Workload identity / managed identity
           v
AKS Key Vault CSI provider
           |
           +--> Pod-mounted files
           |
           +--> Optional synced Kubernetes Secret
           |    nếu cấu hình/supported
           v
Ingress or Java application
~~~

### Các câu hỏi khi dùng để cấp TLS certificate

1. Certificate ở Key Vault có đúng format và private key dùng được?
2. CSI provider truy cập Key Vault qua identity nào?
3. Pod mount được file nào: **certificate, private key, PFX**?
4. Nếu ingress chỉ đọc Kubernetes Secret, có cần **secret sync** không?
5. Secret đồng bộ có được tạo khi Pod cần mount và lifecycle thế nào?
6. Auto-rotation có được bật và interval/semantics ra sao?
7. Khi file mount thay đổi, Java/ingress có reload certificate không?
8. Key Vault private networking/DNS có hoạt động từ nodes/pods không?

### Mấu chốt về refresh

CSI rotation có thể cập nhật nội dung volume hoặc synced Secret theo cơ chế hỗ trợ, **nhưng Spring Boot/Tomcat/Netty không tự động tải lại keystore chỉ vì một file đổi**. Cần có reload logic hoặc controlled restart. Không coi “Key Vault đã có V2” là đủ.

## 32. AGIC, Gateway controller và ingress ownership

Khi ứng dụng dùng **Application Gateway Ingress Controller (AGIC)** hoặc một Gateway integration của Azure, cấu hình TLS có thể do gateway/controller/Ingress resources phối hợp quản lý.

### Tránh mô hình ownership mâu thuẫn

~~~text
Team A trực tiếp cập nhật Application Gateway certificate
        |
        v
Controller lại reconcile gateway từ Kubernetes desired state
        |
        v
Manual change có thể bị ghi đè hoặc gây drift
~~~

Lựa chọn một **source of truth** cho listener/certificate binding:

- IaC/Bicep/Terraform và controller boundary rõ ràng.
- Ingress/Gateway resources nếu controller thực sự sở hữu.
- Key Vault certificate/secret versions theo tích hợp được hỗ trợ.

Không sửa cả Azure Portal và Kubernetes annotation cho cùng listener mà không biết precedence/reconciliation. Kiểm tra phiên bản integration và ownership trước khi triển khai rotation.

## 33. HTTPS chỉ ở edge có đủ không?

Một kiến trúc có thể:

~~~text
Browser --HTTPS--> Front Door --HTTP--> Backend
~~~

hoặc:

~~~text
Browser --HTTPS--> Front Door --HTTPS--> Application Gateway
        --HTTPS--> AKS ingress --HTTP/mTLS--> Java Pod
~~~

**Không có câu trả lời áp dụng cho mọi môi trường.** Phân tích:

- Có yêu cầu mã hóa từng hop theo compliance không?
- Các hop đi trên mạng công cộng, private VNet hay kết nối xuyên vùng?
- Origin certificates và trust chain được quản lý bởi ai?
- Backend TLS termination có làm mất client authentication context không?
- Header chuyển danh tính client có thể bị spoof nếu backend nhận trực tiếp không?

### Không đặt niềm tin vào header client tự khai báo

Nếu edge đã xác thực mTLS rồi gửi header như **X-Client-Cert**, backend chỉ nên tin header khi đường tới edge được bảo vệ và headers từ clients trực tiếp bị loại bỏ. **Một HTTP header không tự chứng minh client có certificate hợp lệ**.

## 34. Java TLS: truststore và keystore

Ứng dụng Java dùng **JSSE** hoặc thư viện HTTP/framework dựa trên JVM TLS stack (tùy implementation). Hai khái niệm:

| Thành phần | Nội dung | Mục đích |
|---|---|---|
| **Truststore** | Root/intermediate CA hoặc trust anchors đáng tin | Xác minh server/client certificates |
| **Keystore** | Private key và certificate chain của phía local | Trình diện certificate khi server TLS/mTLS |

### Ví dụ đường đi

~~~text
Spring Boot Java client
       |
       +-- Truststore: corporate CA để xác minh api.internal
       |
       +-- Keystore: client private key + cert nếu dùng mTLS
       |
       v
HTTPS API
~~~

### Default JDK truststore

Nhiều HTTPS endpoints công cộng được xác minh bằng các root CA có sẵn trong JDK truststore. Không tự import leaf certificate của mọi dịch vụ Azure vào truststore trừ khi có lý do chính đáng. Với internal/private CA cần cấu hình đúng trust anchors theo chính sách.

**Không dùng trust-all TrustManager/HostnameVerifier** hoặc cấu hình “insecureSkipVerify” trong production để né lỗi TLS.

## 35. Spring Boot HTTPS server và keystore

Một ứng dụng Spring Boot có thể phục vụ HTTPS trực tiếp bằng SSL bundle hoặc những thuộc tính SSL của server được phiên bản Spring Boot hỗ trợ.

Ví dụ cấu hình **server.ssl** với file PKCS12 đã được provision trong container filesystem (chỉ dùng khi endpoint Java trực tiếp kết thúc TLS):

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: "file:/run/tls/server-keystore.p12"
    key-store-type: PKCS12
    key-store-password: "${TLS_KEYSTORE_PASSWORD}"
~~~

### Điều kiện

- File **server-keystore.p12** phải chứa key pair + certificate chain hợp lệ.
- **TLS_KEYSTORE_PASSWORD** phải được cung cấp qua secret injection/Key Vault integration, không commit.
- Cấu hình key alias/key password nếu keystore yêu cầu.
- Ingress/Service/probes phải trỏ đúng port và protocol.
- Kiểm tra hostname, cert validity, trust và Spring Boot version.
- Quản lý restart/hot reload khi file được thay; **server.ssl** không bảo đảm hot-reload tự động trên mọi runtime/version.

Nếu TLS đã kết thúc tại Application Gateway và backend chỉ cần HTTP theo policy, không nhất thiết mở HTTPS trực tiếp ở mỗi Java Pod. Nhưng nếu compliance yêu cầu end-to-end TLS, phải thiết kế backend trust đầy đủ.

## 36. Spring Boot SSL bundles

Những phiên bản Spring Boot hiện đại có **SSL bundles** để gom cấu hình trust material/keystore/PEM theo một tên và tái sử dụng ở những thành phần hỗ trợ.

~~~text
Spring Boot SSL bundle: partner-api-client
        |
        +-- Trust material (trusted CA)
        +-- Client key/cert (for mTLS, if needed)
        |
        v
RestClient / WebClient / service connection
   (chỉ nếu client integration hỗ trợ bundle)
~~~

### Lợi ích

- Tách TLS settings khỏi logic nghiệp vụ.
- Có thể tái sử dụng cấu hình giữa các clients/servers hỗ trợ.
- Giảm việc thiết lập global JVM truststore cho mọi outbound connection.

### Hạn chế

- Không phải mọi Azure SDK, JDBC driver, gRPC client hoặc Redis client tự hiểu Spring SSL bundle.
- Thuộc tính Spring Boot SSL bundle **không làm các Azure service clients tự đổi HTTP client** nếu integration chưa wiring bundle.
- Cơ chế reload/hot swap của bundle và hỗ trợ PEM/PKCS12 khác nhau theo Spring Boot version.

Khi code dùng Azure SDK client builder, cần xem SDK **HttpClient/SSL context** có hỗ trợ cấu hình trust cụ thể không, thay vì áp dụng một property Spring rồi giả định đã có hiệu lực.

## 37. Java TLS client: đừng thay thế HTTPS bằng HTTP

Trong một SDK/HTTP client Java, xác minh certificate server cần:

1. Dùng URL/endpoint **https://**.
2. Giữ hostname/FQDN đúng certificate SAN.
3. Tin cậy CA chain qua JDK/system/custom truststore được quản lý.
4. Không tắt peer/hostname verification.
5. Chỉ gửi mTLS client certificate khi dịch vụ yêu cầu.

### Một lỗi nguy hiểm

Ứng dụng gặp **javax.net.ssl.SSLHandshakeException** tới Key Vault private endpoint, kỹ sư đổi URL sang HTTP hoặc dùng HTTP client “trust-all”. Azure Key Vault data-plane yêu cầu HTTPS; làm vậy vừa không giải quyết đúng lỗi vừa phá security model.

### Kết hợp với Entra ID

Token Entra và TLS giải quyết các vấn đề khác nhau: TLS bảo vệ đường truyền/xác minh server; token xác thực client identity và quyền API. Không coi **có access token** là lý do bỏ qua hostname verification.

## 38. Private Endpoint, DNS và SNI

Azure Private Endpoint giúp tạo đường mạng riêng đến dịch vụ Azure hỗ trợ. Nhưng **client nên tiếp tục kết nối bằng FQDN chính thức** theo tài liệu dịch vụ:

~~~text
Java client:
  https://vault-name.vault.azure.net
         |
         | DNS resolves via approved private DNS path
         v
  Private Endpoint IP
         |
         | TLS SNI/hostname = vault-name.vault.azure.net
         v
  Azure Key Vault service
~~~

### Tại sao không hard-code private IP?

- Certificate SAN thường khớp FQDN, không khớp IP riêng.
- SNI giúp dịch vụ chọn certificate/route đúng.
- IP private có thể thay đổi khi tái tạo endpoint.
- Làm rối failover và khả năng audit.

**Private Endpoint không phải VPN, TLS certificate hay IAM role**. Nó chỉ là thành phần mạng. Cần cấu hình private DNS, NSG/UDR/firewall và identity đúng.

## 39. Kiểm tra bằng OpenSSL: handshake công khai (read-only)

Chạy những lệnh sau **trên host/endpoint bạn có quyền kiểm tra**; chúng chỉ thực hiện TLS handshake/đọc chứng chỉ, không thay cấu hình Azure.

~~~bash
HOST="api.example.com"

openssl s_client \
  -connect "$HOST:443" \
  -servername "$HOST" \
  -verify_return_error \
  -showcerts < /dev/null
~~~

### Bạn quan sát những gì?

- Leaf certificate của hostname thật.
- Issuer và intermediate certificates.
- TLS version/cipher được thương lượng.
- Chain verification errors (nếu có).
- Chứng chỉ server đang phục vụ phiên bản nào.

### Giới hạn

- Lệnh với serverName chỉ kiểm một hostname/SNI tại một điểm mạng.
- Load balancer có nhiều nodes/regions; một lần kết nối không đại diện mọi node.
- Certificate chain “verify OK” không tự chứng minh application authorization.
- Không kết luận wildcard/bindings khác đã đúng chỉ từ một host.

## 40. Kiểm tra ngày hết hạn và SAN bằng OpenSSL

Nếu đã có **public certificate PEM** được trích xuất/lưu theo quy trình lab:

~~~bash
openssl x509 -in leaf.pem \
  -noout -subject -issuer -dates -serial

openssl x509 -in leaf.pem \
  -noout -ext subjectAltName

openssl x509 -in leaf.pem \
  -noout -fingerprint -sha256
~~~

### Kiểm tra có còn hạn trong một khoảng thời gian

OpenSSL có tùy chọn **-checkend**, kiểm tra chứng chỉ có hết hạn trong số giây chỉ định không:

~~~bash
# 30 ngày, chỉ đọc public certificate:
openssl x509 -in leaf.pem -noout -checkend 2592000
~~~

Kết quả exit code phù hợp có thể đưa vào một hệ thống cảnh báo, nhưng production monitoring nên giám sát **certificate thực được serving ở HTTPS endpoint** chứ không chỉ đọc PEM từ thư mục local.

### Chain validation

Khi có bộ tệp CA đáng tin đã được xác minh:

~~~bash
openssl verify \
  -CAfile approved-root-ca.pem \
  -untrusted intermediate-ca.pem \
  leaf.pem
~~~

**Đừng lấy CA bất kỳ từ Internet rồi đặt làm trusted root** chỉ vì lệnh verify trước đó thất bại. Kiểm tra issuer/policy/trust store/chain theo quy trình security.

## 41. SNI và certificate được trả sai hostname

Một shared listener có thể phục vụ nhiều domains:

~~~text
api.example.com       -> cert A
admin.example.com     -> cert B
shop.example.com      -> cert C
          |
          v
       Same edge IP
          |
          v
 SNI selects certificate
~~~

### Chẩn đoán

Kết nối tới IP hoặc thiếu SNI có thể nhận default certificate khác. Dùng:

~~~bash
openssl s_client \
  -connect "edge.example.com:443" \
  -servername "api.example.com" \
  -showcerts < /dev/null
~~~

Lệnh này chỉ phù hợp nếu **edge.example.com** thực sự là địa chỉ endpoint được phép và route tới cùng listener; không lấy ví dụ làm lệnh áp cho mọi CDN. Điều quan trọng là **-servername phải là hostname cần kiểm thử**.

### DNS không thể thay chứng chỉ

Một CNAME alias trỏ tới Front Door/App Service không có nghĩa certificate được tự cấp cho alias đó. Phải thêm custom domain binding/validation và bảo đảm SAN/managed cert theo cơ chế dịch vụ.

## 42. Java keytool: truststore và certificate inspection

Trong Java ecosystem, **keytool** giúp kiểm tra certificate/truststore. Với Java runtime hỗ trợ:

~~~bash
# Chỉ đọc public certificate file:
keytool -printcert -file leaf.pem

# Liệt kê thông tin keystore lab theo quyền phù hợp:
keytool -list -v \
  -keystore truststore-lab.p12 \
  -storetype PKCS12
~~~

### Những điều cần chú ý

- Không đưa keystore password lên command line ở nơi process listing/history có thể bị đọc.
- Không in dump PKCS12/private key.
- Không sửa global **cacerts** của JDK production trực tiếp để né một lỗi.
- Dùng truststore có owner/CA policy và kế hoạch rotation.

### Lệnh import root CA chỉ trong lab

~~~bash
# GHI vào truststore lab, KHÔNG dùng trên JDK system cacerts:
keytool -importcert \
  -alias approved-lab-root \
  -file approved-lab-root.pem \
  -keystore truststore-lab.p12 \
  -storetype PKCS12
~~~

Trước khi import, phải xác minh fingerprint/issuer/root CA qua kênh tin cậy. Nếu người tấn công cung cấp một root CA giả, việc import đó khiến toàn bộ kết nối được truststore sử dụng có nguy cơ bị giả mạo.

## 43. TLS handshake lỗi trong Java

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| **PKIX path building failed** | CA chain không được trust hoặc thiếu intermediate | Truststore, issuer, chain |
| **No subject alternative names matching** | Hostname không có trong SAN | URL/FQDN/SNI, certificate SAN |
| **CertificateExpiredException** | Leaf/intermediate hết hạn | Not After của từng cert |
| **CertificateNotYetValidException** | Not Before chưa tới hoặc system clock sai | UTC clock/NTP, validity |
| **handshake_failure** | TLS policy/cipher/clientAuth mismatch | Version, suites, mTLS |
| **bad_certificate** | Client certificate/key/trust mismatch | Client keystore, CA, EKU |
| **UnknownHostException** | DNS hoặc tên host sai | Private DNS, resolver |
| **ConnectTimeoutException** | Route/port/firewall chặn | TCP, NSG/UDR, egress |
| **HTTP 401/403** | TLS đã thành công, lỗi auth/application policy | Entra token, IAM, API permissions |

### Debug TLS mà không lộ bí mật

JSSE hỗ trợ diagnostics qua **javax.net.debug** trong một số tình huống, nhưng log handshake chi tiết có thể chứa nhiều metadata nhạy cảm và tạo volume lớn. Chỉ bật trong môi trường kiểm soát, không xuất logs tùy tiện, và tắt sau điều tra.

**Không gộp mọi lỗi SSLHandshakeException vào một lời khuyên “import cert vào cacerts”.** Nhiều lỗi là SAN/SNI/cipher/mTLS, không phải thiếu trusted root.

## 44. Read-only Azure CLI: Key Vault certificate inventory

Khi có quyền đọc metadata của Key Vault lab, có thể dùng các lệnh sau:

~~~bash
az account show \
  --query "{subscription:id,tenant:tenantId}" \
  -o json

az keyvault certificate list \
  --vault-name "<LAB_VAULT>" \
  --query "[].{id:id,enabled:attributes.enabled,expires:attributes.expires}" \
  -o table

az keyvault certificate show \
  --vault-name "<LAB_VAULT>" \
  --name "<LAB_CERT_NAME>" \
  --query "{id:id,enabled:attributes.enabled,expires:attributes.expires}" \
  -o json
~~~

### Bảo mật

- Các lệnh hiển thị **certificate metadata**, không xuất backing PFX/private key.
- Không dùng lệnh **az keyvault secret show** để đọc/download certificate private-key-bearing secret khi chỉ cần xác minh expiry.
- Khi vault dùng private networking, máy chạy CLI cần đường mạng/DNS hợp lệ.
- Danh sách chứng chỉ là inventory của **vault**, chưa chứng minh gateway dùng đúng version.

Nếu CLI trả **Forbidden**, kiểm tra tenant, data-plane role/access policy, firewall và service state. Đừng tự nâng quyền toàn subscription để vượt lỗi.

## 45. Read-only Azure CLI: TLS binding metadata

Đối với Application Gateway lab có quyền đọc management plane:

~~~bash
az network application-gateway ssl-cert list \
  --gateway-name "<LAB_GATEWAY>" \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --query "[].{name:name,secretId:keyVaultSecretId,state:provisioningState}" \
  -o table
~~~

Lệnh này giúp thấy listener certificate references theo API/CLI version hỗ trợ, nhưng:

- Không hiện chứng chỉ đang được serving từ mọi frontend IP/node.
- Không khẳng định gateway đã refresh backing secret mới.
- Một số thuộc tính phụ thuộc gateway SKU/CLI version.
- Cần kiểm tra thêm listener/hostname/rule mappings.

### Quy trình kiểm chứng đầy đủ

1. Xem Key Vault certificate/secret version metadata.
2. Xem gateway TLS certificate reference và provisioning state.
3. Kết nối HTTPS tới frontend hostname thực bằng OpenSSL/curl.
4. Đối chiếu SAN, chain, fingerprint, Not After.
5. Kiểm tra backend/origin TLS health nếu có.

**Đọc metadata Azure chưa thay thế được end-to-end TLS handshake test**.

## 46. Java: đọc thời hạn một chứng chỉ PEM (không có private key)

Để kiểm tra một **public X.509 certificate file** trong Java, có thể dùng API chuẩn JDK:

~~~java
import java.io.FileInputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

public final class CertificateExpiryLab {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: CertificateExpiryLab <public-cert.pem>");
        }

        CertificateFactory factory =
            CertificateFactory.getInstance("X.509");

        X509Certificate certificate;
        try (FileInputStream in = new FileInputStream(args[0])) {
            certificate = (X509Certificate) factory.generateCertificate(in);
        }

        Date now = new Date();
        certificate.checkValidity(now);

        Instant expiration = certificate.getNotAfter().toInstant();
        long daysRemaining = Duration.between(
            Instant.now(), expiration).toDays();

        System.out.println("Subject: " +
            certificate.getSubjectX500Principal().getName());
        System.out.println("Issuer: " +
            certificate.getIssuerX500Principal().getName());
        System.out.println("Not After: " + expiration);
        System.out.println("Days remaining (whole days): " + daysRemaining);
    }
}
~~~

### Giới hạn quan trọng của ví dụ

- **checkValidity() chỉ kiểm thời gian** trên leaf certificate; không tự chứng minh chain, SAN, EKU, revocation hoặc khóa riêng hợp lệ.
- Không cần nhập hoặc ghi private key.
- Có thể ném CertificateExpiredException/CertificateNotYetValidException.
- Duration.toDays() làm tròn về số ngày nguyên; với alert production nên tính thời gian chính xác hơn và dùng UTC/NTP.
- Nếu file là PEM bundle nhiều certificates, **generateCertificate** như ví dụ chỉ lấy một certificate, không tự kiểm tra toàn chain.
- Đây là kiểm tra **file đã có**, không xác minh endpoint Azure đang serving cùng certificate đó.

## 47. Gia hạn: lịch và ngưỡng cảnh báo

Một kế hoạch minh họa theo thời gian trước hạn:

~~~text
T - 60 ngày: cảnh báo sớm / owner kiểm tra CA + domain validation
T - 30 ngày: renew/rekey và deploy vào staging
T - 14 ngày: xác minh production listeners/origins
T -  7 ngày: escalated on-call nếu chưa có cert mới
T -  1 ngày : incident/contingency nếu vẫn có nguy cơ hết hạn
T = 0      : không được để endpoint serving cert expired
~~~

**Các mốc này là ví dụ vận hành**, không phải SLA của Azure/CA. Với certificate validity ngắn hơn, yêu cầu renewal và validation phải được tự động hóa với ngưỡng khác. Với domain validation phức tạp hoặc change window dài, bắt đầu sớm hơn.

### Hai loại expiry cần theo dõi

1. **Certificate inventory expiry:** Key Vault / CA / certificate manager cho biết Not After của phiên bản lưu.
2. **Serving certificate expiry:** endpoint công khai/nội bộ thực sự trình diện Not After khi client handshake.

Sự sai khác giữa hai loại này chính là một nguồn downtime TLS điển hình.

## 48. Quy trình gia hạn không gián đoạn

Một workflow an toàn:

1. **Xác định phạm vi:** SANs, hosts, gateways, mTLS clients/backends, current fingerprint.
2. **Kiểm tra issuer/domain validation:** DNS/CAA, CA integration, owner.
3. **Tạo certificate mới:** chọn key reuse/rekey theo policy.
4. **Lưu vào nơi được duyệt:** Key Vault certificate/secret hoặc managed TLS service.
5. **Kiểm tra trước triển khai:** chain, hostname/SAN, EKU, Not Before/After, key pair và format.
6. **Triển khai staging:** dùng test hostname/traffic được phép, thử client thực.
7. **Update references/bindings:** versionless hoặc pinned version theo integration.
8. **Rollout từng phần:** gateway nodes/regions, ingress/controllers hoặc Pods.
9. **Xác minh serving fingerprint** tại các endpoints thực, backend health và metrics.
10. **Giữ phương án rollback** hợp lệ trong cửa sổ chuyển đổi.
11. **Dọn phiên bản cũ** sau khi hết phụ thuộc và chính sách retention/incident được đáp ứng.

### Certificate mới không nhất thiết đồng nghĩa dịch vụ mới

Nếu cert mới đúng cùng domain nhưng public key khác, đa số HTTPS clients công cộng vẫn hoạt động nếu chain hợp lệ và không có pinning bất thường. Nhưng các clients có certificate pinning/CA trust hạn chế hoặc mTLS trust mapping riêng có thể cần update trước.

**Không xóa V1 trước khi biết mọi consumer đã chuyển khỏi V1**; nhưng cũng không giữ private keys hết vòng đời vô hạn không có mục đích.

## 49. Phân biệt renewal, reissue, rekey và rotation

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Renewal** | Lấy chứng chỉ có hiệu lực mới cho cùng hoặc danh tính tương ứng |
| **Reissue** | Cấp lại chứng chỉ trong những tình huống như sửa metadata hoặc thay đổi theo issuer |
| **Rekey** | Tạo cặp public/private key mới |
| **Rotation** | Thay certificate/key đang được workload thực sự sử dụng |
| **Revocation** | CA đánh dấu certificate không còn được tin cậy theo cơ chế revocation |
| **Retirement** | Gỡ chứng chỉ/khóa và quyền khi không còn nhu cầu |

### Mấu chốt

Gia hạn tạo V2 trong Key Vault chưa phải **rotation** nếu listener vẫn serving V1. **Rekey** khác renewal vì thay private key; việc thay key có thể cần phân phối/reload keystore riêng.

## 50. CA root/intermediate rotation: khó hơn leaf rotation

Đổi **leaf certificate** thường không cần cập nhật root trust store nếu CA chain mới vẫn được clients tin cậy. Nhưng đổi **root hoặc intermediate CA** có thể ảnh hưởng toàn bộ các clients đã pin trust anchors hoặc dùng private PKI.

~~~text
Old trust:
  Root A -> Intermediate A -> Server V1

New trust:
  Root B -> Intermediate B -> Server V2

Migration:
  Trust Root A + Root B tạm thời trên clients
       |
       v
  Deploy server V2/chain mới
       |
       v
  Verify all clients
       |
       v
  Retire Root A trust sau cutover
~~~

### Runbook CA rollover

1. Inventory clients: JVM, IoT, legacy OS, partners, service mesh.
2. Phân phối **new trust anchor** trước khi server đổi CA chain.
3. Xác minh clients có thể validate chain mới.
4. Chuyển server certificate/issuer với thời gian chồng lấn hợp lý.
5. Theo dõi handshake errors và auth failures.
6. Thu hồi trust cũ theo risk assessment và lịch phê duyệt.

**Không xóa root CA cũ khỏi tất cả truststores cùng lúc trước khi chuyển xong hệ thống**, cũng không giữ root đã bị compromise chỉ để tránh lỗi.

## 51. Certificate pinning và rủi ro khi rotation

Một số ứng dụng di động, IoT hoặc B2B integrations dùng **certificate/public key pinning**. Pinning có thể làm client từ chối certificate mới ngay cả khi public CA/chain hợp lệ.

### Trường hợp thường gặp

~~~text
Client pins fingerprint của leaf V1
        |
        v
Server gia hạn + rekey -> leaf V2
        |
        v
Client từ chối V2 dù CA tin cậy
~~~

### Nguyên tắc

- Chỉ dùng pinning khi có yêu cầu bảo mật/khả năng vận hành đủ mạnh.
- Có backup pins hoặc kế hoạch thay pin theo cơ chế an toàn phù hợp.
- Không pin một leaf certificate sẽ hết hạn sớm mà không có ứng dụng cập nhật.
- Kiểm thử ứng dụng cũ và offline clients trước khi rekey.
- Không giảm bảo mật bằng cách vô hiệu hóa toàn bộ TLS verification khi pin không khớp.

Pinning không phải tính năng bắt buộc của HTTPS; sử dụng thiếu quy trình rotation có thể tự gây outage trên thiết bị khó cập nhật.

## 52. Thu hồi chứng chỉ khi private key bị lộ

Khi private key có dấu hiệu bị lộ, gia hạn thông thường là **không đủ**. Cần một quy trình incident:

1. **Kích hoạt incident response** và xác định certificate/private key nào bị ảnh hưởng.
2. **Ngăn truy cập không phù hợp** tới PFX/Key Vault secret/CI artifact/storage.
3. **Sinh key pair mới** trong hệ thống được duyệt.
4. **Yêu cầu CA cấp certificate mới** với domain/SAN đúng.
5. **Triển khai và kiểm tra** cert/key mới tại tất cả TLS endpoints.
6. **Yêu cầu CA revoke certificate bị compromise** theo quy trình issuer.
7. **Thu hồi quyền/credentials liên quan**, kiểm tra logs/audit và truy vết nguồn lộ.
8. Kiểm tra các copies/backups có chứa khóa cũ theo retention/security policy.
9. Đóng incident sau khi xác nhận clients tin cậy cert mới và rủi ro đã được xử lý.

### Revocation có thay thế rotation không?

**Không.** Revocation state có thể được clients xử lý khác nhau qua OCSP/CRL/caching/soft-fail policy. Khi khóa bị lộ, phải **thay certificate/key trên endpoint** và xử lý trust theo kế hoạch, không chỉ gửi yêu cầu revoke rồi tiếp tục phục vụ chứng chỉ cũ.

## 53. OCSP, CRL và revocation checking

**Certificate Revocation List (CRL)** và **Online Certificate Status Protocol (OCSP)** là các cơ chế CA/client ecosystem sử dụng để biểu thị/chứng minh trạng thái thu hồi trong những cấu hình nhất định.

### Những điều nên hiểu đúng

- Không phải mọi client/browser/JVM xử lý revocation giống nhau.
- OCSP stapling và OCSP/CRL availability phụ thuộc endpoint/issuer/client.
- Một hệ thống có thể soft-fail khi không kiểm tra được revocation, tùy chính sách.
- Thời gian propagation/cache của thông tin revocation không tức thời ở mọi nơi.
- Môi trường private PKI cần tự thiết kế nguồn CRL/OCSP và khả năng truy cập.

Không mô tả **revocation là biện pháp đảm bảo lập tức mọi client từ chối cert cũ**. Đối với private key compromise phải kết hợp key replacement, server rollout, client trust policy và incident management.

## 54. TLS expiry alerts và quản lý tín hiệu

Một chiến lược monitoring nhiều lớp:

~~~text
Key Vault certificate expiration metadata
          |
          +--> Azure monitoring/event/alert path
          |
Public HTTPS endpoints
          |
          +--> External HTTPS certificate probes
          |
Internal origin/AKS endpoints
          |
          +--> Internal TLS certificate probes
          |
          v
SRE alerting + ticket + on-call + escalation
~~~

### Những tín hiệu cần có

| Signal | Vì sao cần |
|---|---|
| **Days until expiry** | Gia hạn trước deadline |
| **Serving cert fingerprint** | Chứng minh rotation đã tới endpoint |
| **SAN/hostname mismatch** | Phát hiện certificate sai binding |
| **Chain validation failures** | Thiếu intermediate/CA trust |
| **TLS handshake error rate** | Phát hiện lỗi protocol/trust/clientAuth |
| **Key Vault certificate operation status** | Renewal/import failure |
| **Key Vault/Managed Identity access errors** | Gateway không fetch được secret |
| **Gateway/ingress reload state** | Certificate V2 đã được nạp chưa |
| **Backend origin TLS health** | Phát hiện cert hết hạn ở hop nội bộ |
| **Domain validation/DNS status** | Renewal automation phụ thuộc DNS |

### Không chỉ cảnh báo “còn 30 ngày”

Hệ thống có thể đã tự renew V2 nhưng endpoint vẫn serving V1. Khi đó alert từ Key Vault có thể yên lặng trong khi Internet clients sắp bị lỗi. **Cần ít nhất một probe độc lập tại địa chỉ HTTPS đang sử dụng**, và probe riêng cho backend internal khi security boundary cho phép.

## 55. Sử dụng Azure Monitor/Event Grid phù hợp

Azure Key Vault có các event/monitoring integrations cho vòng đời certificate theo loại vault/resource/tính năng. Có thể phối hợp **Event Grid → Azure Function/Logic App → Teams/on-call/ticketing** hoặc Azure Monitor alerts.

~~~text
Key Vault certificate lifecycle event
           |
           v
Event Grid subscription
           |
           v
Function / Logic App
           |
           +--> Ticket + assigned owner
           +--> On-call notification
           +--> Optional approved renewal automation
~~~

### Tính bền vững của alert

- Xem **event types** thực có hỗ trợ trong Key Vault/resource.
- Có retry và DLQ/error handling nếu integration hỗ trợ.
- Gắn certificate resource ID, version, event time và owner.
- Tránh thông báo chỉ gửi tới email cá nhân không được giám sát.
- Tự động renew/deploy là **write operation có tác động**, cần bảo vệ identity và điều kiện idempotency.
- Kết hợp scheduled probes để dự phòng event subscription bị lỗi.

Không giả định một event “near expiry” đồng nghĩa CA đã tự cấp chứng chỉ mới. Event có thể chỉ là tín hiệu để owner tiến hành hành động.

## 56. Chi phí và rủi ro vận hành TLS

| Thành phần | Nguồn chi phí/rủi ro |
|---|---|
| **Public CA certificate** | Phí CA/validation theo hình thức cấp |
| **Managed TLS service** | SKU/tier/lượt yêu cầu/gateway theo sản phẩm |
| **Azure Key Vault** | Operations, loại vault/keys/HSM và networking |
| **Private Endpoint** | Endpoint/network/data processing theo pricing |
| **Application Gateway/Front Door** | Gateway/edge processing và egress theo pricing |
| **AKS cert-manager/CSI** | Controller/Pods, secrets, DNS challenges, vận hành |
| **Azure Monitor/Log Analytics** | Monitoring ingestion/retention/probes |
| **Incident downtime** | SLO, hỗ trợ khách hàng, mất doanh thu |

### Vì sao automation đáng đầu tư?

Một cert hết hạn gây outage có thể tốn hơn nhiều so với việc tự động hóa inventory, renewal và deployment. Tuy nhiên automation sai có thể phát hành nhầm domain, xóa secret version hoặc cập nhật listener sai; vì vậy **idempotency, least privilege, staged rollout và verification** là điều kiện thiết kế.

### Không ghi giá cố định

Phí Azure Key Vault operations, gateway tiers và public CA certificates thay đổi theo hình thức mua, region và thời điểm. Dự toán qua **Azure Pricing Calculator** và hợp đồng/giá CA hiện hành thay vì sử dụng một bảng USD giả định.

## 57. Bảo vệ private key và an toàn supply chain

### Những nơi dễ rò rỉ PFX/private key

- Repository Git hoặc commit history.
- Docker image layers.
- Kubernetes Secret manifest trong source, kể cả đã Base64.
- CI logs, deployment variables, IaC state/plan.
- File share cá nhân hoặc email attachment.
- Debug dump, heap dump, log của application.
- Laptop developer hoặc backup không mã hóa.

### Thực hành

1. Ưu tiên managed certificate/Key Vault/HSM theo yêu cầu và integration support.
2. Nếu phải export PFX, tối thiểu hóa số lần/phạm vi, có approval/audit và xóa bản trung gian an toàn.
3. Cấp quyền **get secret** cho đúng gateway identity, không mọi developer.
4. Phân tách dev/staging/prod key material và Key Vault.
5. Có key rotation/compromise runbook.
6. Hạn chế quyền exec/log/backup với thành phần lưu private key.
7. Quét secrets trong CI, nhưng không đưa private key thật vào công cụ scan công khai.

**Không dùng cùng một certificate/private key production trong mọi môi trường** chỉ vì DNS SAN giống nhau; blast radius và quyền cần được tách.

## 58. CI/CD và IaC cho chứng chỉ

Một hệ thống có thể quản lý cấu hình endpoint qua **Bicep, ARM, Terraform, Helm, Kubernetes manifests hoặc GitOps**.

~~~text
Git (không chứa private key)
       |
       +-- Hostname and TLS policy
       +-- Key Vault secret identifier (không chứa secret value)
       +-- Identity/RBAC references
       +-- Ingress/Gateway listener config
       |
       v
CI validation + approval
       |
       v
Deploy TLS binding to staging
       |
       v
OpenSSL/health validation
       |
       v
Controlled production rollout
~~~

### Không lưu private key vào IaC

Một template có thể đọc password/PFX từ file input và vô tình đưa vào **plan/state/deployment logs**. Tách private key material vào secret management, dùng approved references và đảm bảo công cụ CI không echo inputs.

### Desired state và drift

Nếu kỹ sư thay certificate qua Portal, controller/IaC có thể ghi đè khi reconcile. Sau emergency hotfix cần cập nhật desired state hoặc rollback có chủ đích, không để production tồn tại hai nguồn cấu hình mâu thuẫn.

### Validation pipeline

- Lint/validate IaC/Ingress resources.
- Kiểm tra hostname/SAN dự kiến, CA/issuer.
- Đảm bảo certificate chưa hết hạn và private key pair hợp lệ.
- Kiểm tra Key Vault reference identity/format.
- Test staging endpoints và backend origin.
- Bảo đảm rollback artifacts/reference còn hoạt động.

## 59. Disaster recovery: certificate là một phần của DR

Khi tái tạo một Azure region, một gateway hoặc cluster có thể cần chứng chỉ trước khi phục vụ HTTPS. Một hệ thống DR tốt phải biết:

1. Certificate/key lưu ở đâu, ai có quyền dùng?
2. Nếu Key Vault không khả dụng ở thời điểm failover, có đường thay thế được phê duyệt không?
3. Managed certificate có tự có ở region/gateway mới không?
4. DNS/domain validation có chấp nhận endpoint DR không?
5. Key Vault soft delete/purge protection/backup/recovery policy đã phù hợp?
6. Ingress/Gateway listeners có được IaC tái tạo đúng secret reference không?
7. Truststore của clients đã có CA/chain cần thiết?
8. Backend mTLS client certificates được rotate/reissue thế nào?

### Không coi backup public certificate là backup toàn bộ TLS service

Public PEM có thể có ở nhiều nơi, nhưng **private key mới là tài liệu nhạy cảm cần sử dụng đúng cách**. Nếu private key là non-exportable HSM key, DR phải dựa trên cơ chế service/replication/recovery được hỗ trợ, không giả định có thể copy PFX.

## 60. Runbook xử lý certificate hết hạn tại gateway

Tình huống: người dùng báo lỗi **NET::ERR_CERT_DATE_INVALID** khi truy cập **api.example.com**.

### Bước 1: xác minh

~~~bash
HOST="api.example.com"
openssl s_client \
  -connect "$HOST:443" \
  -servername "$HOST" \
  -verify_return_error \
  -showcerts < /dev/null
~~~

Xác minh **Not After**, leaf SAN/chain và xem đang kết nối tới Front Door hay Application Gateway. Kiểm tra DNS hiện tại, region/client network và server time.

### Bước 2: phân tích inventory

- Cert hết hạn nằm ở edge hay backend?
- Gateway dùng managed certificate hay Key Vault BYOC?
- Key Vault đã có bản mới hay chưa?
- Reference có versionless hay pinned version?
- Gateway/ingress đã reload không?

### Bước 3: khắc phục trong phạm vi cho phép

- Nếu cert mới đã có, cập nhật/khôi phục approved binding/refresh theo tài liệu dịch vụ.
- Nếu chưa có, yêu cầu issuer renewal/reissue qua quy trình khẩn cấp đã phê duyệt.
- Nếu do SNI sai, sửa listener/hostname binding thay vì cấp mới không cần thiết.
- Không chuyển HTTP plaintext hoặc tắt certificate verification để che lỗi.

### Bước 4: kiểm chứng

- HTTPS handshake với hostname và chain hợp lệ.
- Fingerprint/Not After đã đổi đúng.
- Các regions/clients kiểm tra không còn lỗi.
- Backend health, p95 và 5xx ổn định.
- Ghi timeline/owner/root cause và cải thiện cảnh báo.

## 61. Lab A: kiểm chứng một public HTTPS endpoint

**Mục tiêu:** đọc chứng chỉ công khai qua mạng mà không thay tài nguyên Azure.

### Điều kiện

- Có endpoint HTTPS lab hoặc domain do tổ chức cho phép kiểm thử.
- Có OpenSSL trên máy được phê duyệt.
- Không sử dụng domain của người khác để chạy load scan.

### Thực hiện

1. Chọn hostname **tls-lab.example.com** đã cấu hình trong môi trường lab; tên trong bài là placeholder, không phải endpoint thực.
2. Chạy **openssl s_client** với **-servername** và **-verify_return_error**.
3. Ghi issuer, Not Before, Not After, SAN và TLS version.
4. Trích xuất/copy public leaf cert bằng quy trình lab, không tải private key.
5. Chạy **openssl x509 -noout -dates -ext subjectAltName**.
6. Kiểm tra **-checkend** cho 30 ngày.
7. Đối chiếu server certificate fingerprint với inventory.
8. Chỉ ghi public metadata cần thiết vào báo cáo, không in secrets.

### Nghiệm thu

| Kiểm tra | PASS khi |
|---|---|
| Hostname | SAN chứa FQDN cần truy cập |
| Trust | Chain tới trusted root được kiểm chứng |
| Validity | Certificate còn hạn tại thời điểm test |
| Protocol | TLS version đáp ứng policy |
| SNI | Client nhận đúng leaf cho hostname |
| Fingerprint | Khớp inventory/version đang serving |
| Secrets | Không có private key/password trong outputs |

## 62. Lab B: Key Vault certificate metadata và vòng đời

**Mục tiêu:** nhận biết Key Vault certificate policy, version và expiry **bằng quyền đọc**.

### Chuẩn bị

- Key Vault lab có certificate public/self-signed dành riêng cho lab.
- Azure CLI và identity được cấp **certificate metadata read** phù hợp.
- Đường mạng/vault firewall được cấu hình đúng.
- Không dùng vault production chỉ để khám phá.

### Các bước

1. Dùng **az account show** xác định subscription/tenant.
2. Dùng **az keyvault certificate list** để lấy tên và expiration metadata.
3. Dùng **az keyvault certificate show** cho một certificate lab.
4. Xem **policy/issuer/validity** theo CLI/Portal hỗ trợ.
5. Xác định certificate có bao nhiêu versions.
6. Giải thích sự khác nhau giữa certificate metadata, backing secret và cryptographic key.
7. Tìm xem lifetime action là notification hay auto-renew.
8. Không truy xuất/download secret PFX/private key.
9. Ghi owner/expiry/renewal mode vào inventory giả định.

### Câu hỏi

Nếu certificate V2 đã xuất hiện trong vault nhưng Application Gateway vẫn serving V1, hai thành phần nào cần kiểm tra tiếp?

**Đáp án định hướng:** Kiểm tra gateway Key Vault secret reference (versionless/pinned), identity/network và cơ chế refresh; sau đó kiểm tra certificate thật qua HTTPS listener.

## 63. Lab C: AKS certificate rotation trên namespace thử nghiệm

**Mục tiêu:** hiểu **Kubernetes TLS Secret/Ingress** và tách trạng thái Secret khỏi trạng thái certificate đang serving.

### Điều kiện

- AKS/Kubernetes namespace lab, quyền RBAC giới hạn và ingress controller tương thích.
- Public test domain hoặc internal hostname lab được phép.
- Certificate do test CA/ACME staging/issuer phê duyệt.
- Không dùng private key production.

### Quy trình

1. Tạo Certificate/Issuer với cert-manager hoặc tải certificate lab qua quy trình được phép.
2. Xác nhận Secret kiểu **kubernetes.io/tls** và Ingress/Gateway tham chiếu đúng.
3. Dùng OpenSSL từ client lab kiểm tra leaf fingerprint/expiry.
4. Gia hạn hoặc reissue trong môi trường test theo issuer/automation.
5. Quan sát Secret version/data thay đổi.
6. Xác minh ingress/controller đã reload; nếu không, dùng approved reconciliation/restart workflow.
7. Dùng OpenSSL từ nhiều Pod/client/path để xác nhận serving fingerprint mới.
8. Theo dõi ingress 4xx/5xx, handshake failures và readiness.
9. Kiểm tra private key không xuất hiện trong Git/CI/logs.
10. Cleanup test resources và ghi bài học rotation vào runbook.

### Không làm trong bài thực hành

- Không **revoke** production certificate để mô phỏng sự cố.
- Không xóa Kubernetes Secret của service production.
- Không reset Key Vault access policy production.
- Không mở public network access hoặc tắt TLS verification cho nhanh.

## 64. Lab D: Java client truststore và lỗi CA

**Mục tiêu:** kiểm tra vì sao Java client có thể không tin internal CA mặc dù kết nối TCP thành công.

### Chuẩn bị

- Java 17+ lab, **public certificates của CA lab được xác thực nguồn**.
- Một TLS service lab dùng internal CA.
- Keystore/truststore dành riêng cho bài thực hành.

### Thực hiện

1. Dùng **keytool -printcert** xem leaf public certificate.
2. Dùng OpenSSL kiểm tra SAN, issuer, chain.
3. Chạy Java HTTPS client lab với default truststore (kết quả có thể là lỗi trust nếu root CA không có).
4. Xác minh CA lab fingerprint qua kênh đáng tin.
5. Import **chỉ CA lab đã duyệt** vào truststore-lab.p12, không sửa global cacerts.
6. Cấu hình ứng dụng lab sử dụng truststore mới theo JSSE/HTTP client chính xác.
7. Chạy lại request HTTPS và quan sát kết quả.
8. Thử tên host không nằm trong SAN để chứng minh import CA **không thay thế hostname verification**.
9. Xóa/trả lại cấu hình lab và lưu báo cáo.

### Bài học

Tin cậy đúng root CA giúp kiểm tra chain, nhưng **hostname, validity, EKU, algorithms và revocation policy** vẫn là phần của TLS validation. Không giải quyết mọi lỗi bằng import certificate.

## 65. Case study: retail API đa tầng trên Azure

Một doanh nghiệp có:

- **Azure Front Door** phục vụ **api.shop.example.com**.
- **Application Gateway** chuyển hướng tới AKS.
- **AKS ingress** dùng certificate nội bộ cho traffic HTTPS.
- **Spring Boot** gọi Azure Key Vault và Azure SQL qua Private Endpoints.
- Một đối tác B2B dùng **mTLS** khi gọi một API riêng.
- Certificate công khai được cấp từ public CA qua Key Vault BYOC cho một số endpoints, phần còn lại dùng Azure-managed TLS.
- Một nhóm dùng cert-manager cho những certificates nội bộ trong AKS.
- SRE có SLO uptime và yêu cầu rotation không gián đoạn.

### Sự cố giả định

Ngày gia hạn, Key Vault có certificate V3 với Not After mới, nhưng một phần người dùng nhận certificate V2 sắp hết hạn. Đồng thời, Java Pods báo **PKIX path building failed** khi gọi backend mới được đổi intermediate CA.

### Nhiệm vụ thiết kế

1. Vẽ toàn bộ TLS hops từ browser tới Pod và API/Key Vault/SQL.
2. Chỉ ra nơi có public CA certificate và nơi dùng internal CA.
3. Phân biệt Front Door edge certificate với origin certificate.
4. Kiểm tra App Gateway listener Key Vault secret reference, managed identity và vault network.
5. Giải thích vì sao cert V3 trong vault chưa bảo đảm listener phục vụ V3.
6. Thiết kế probe để xác minh fingerprint mỗi TLS endpoint/region.
7. Tìm nguyên nhân PKIX trên Java khi intermediate chain đổi.
8. Thiết kế truststore CA rollover không cần tắt SSL checks.
9. Lập plan renewal/rotation tách public certificates và mTLS clients.
10. Chọn quản trị Key Vault/CSI/cert-manager sao cho không có ownership conflict.
11. Đề xuất expiry alerts cho Key Vault và serving endpoints.
12. Thiết kế blast-radius isolation cho wildcard/private keys.
13. Xác định khi nào cần revoke certificate và rekey.
14. Thiết kế CI/CD/IaC và rollback khi listener/new cert không hoạt động.
15. Tính các loại chi phí, không chỉ phí mua chứng chỉ.

### Hướng giải tham khảo

~~~text
Browser
  |
  | Public HTTPS certificate for api.shop.example.com
  v
Azure Front Door
  |
  | HTTPS to origin / origin hostname validation
  v
Application Gateway
  |
  | Internal HTTPS certificate/trusted root as configured
  v
AKS ingress
  |
  | HTTP/HTTPS/mTLS theo policy
  v
Spring Boot API
  |
  +--> Key Vault private DNS + TLS + Entra token
  +--> Azure SQL FQDN + JDBC TLS + database auth
~~~

**Hai nhánh chẩn đoán song song:**

- **Key Vault V3 nhưng edge V2:** kiểm tra Key Vault secret ID/format, gateway integration, identity/network, refresh/rollout và TLS probe thực.
- **Java PKIX:** kiểm tra issuer/intermediate chain mới, JDK truststore, CA rollover, SAN/SNI và hostname; không bật trust-all.

**Kết quả mong muốn:** các endpoints serving certificate hợp lệ, đúng host, chain và Not After; mTLS clients vẫn xác thực; mã Java không cần tắt certificate checks; SRE có inventory và runbook cho lần gia hạn kế tiếp.

## 66. Checklist production

| Nhóm | Điều kiện đạt |
|---|---|
| Inventory | Mọi public/internal TLS endpoints, owner và certificate ID rõ |
| Domain/SAN | Hostname/SNI, DNS/CAA và ownership đúng |
| PKI | Public/internal CA policy, trust chain/EKU hợp lệ |
| Key material | Private keys không ở Git/logs, exportability/HSM phù hợp |
| Key Vault | Certificate/key/secret quyền và policy đúng |
| IAM | Managed identity, RBAC/access policy tối thiểu |
| Networking | Private DNS, TLS, firewall/Private Endpoint phù hợp |
| Managed TLS | Eligibility, auto-renew và domain validation được theo dõi |
| BYOC | Issuance/renewal/import/deploy được tự động hóa hoặc có runbook |
| App Service | Hostname binding, TLS policy, slot semantics đúng |
| Front Door | Edge cert và origin TLS được kiểm chứng riêng |
| Application Gateway | Listener cert, Key Vault secret reference và backend trust đúng |
| AKS | Ingress/controller/CSI/cert-manager ownership và reload test đạt |
| Java | Truststore/keystore, hostname verification, JDK support |
| mTLS | Client identity, CA trust, auth mapping và rotation test |
| Monitoring | Expiry, fingerprint, SAN, handshake failures, origin health |
| Alerts | Owner/on-call, escalation và independent probes |
| Rotation | Staging, rollout, serving fingerprint verification, rollback |
| Revocation | Key compromise runbook, CA revoke và key replacement |
| CA rollover | Old/new trust overlap, client compatibility validation |
| CI/CD | Không lưu PFX/private key trong build/state/logs |
| DR | Chứng chỉ/key recovery hoặc reissue strategy được thử |
| Costs | CA, Key Vault, gateways, network và monitor/incident cost |
| Compliance | TLS version/algorithms/data residency theo policy hiện hành |

## 67. Câu hỏi tự kiểm tra

1. TLS giải quyết những vấn đề bảo mật gì và không giải quyết vấn đề gì?
2. X.509 certificate khác private key như thế nào?
3. Leaf, intermediate và root CA liên hệ ra sao?
4. Vì sao client cần kiểm tra SAN thay vì chỉ CN?
5. SNI giúp gì khi nhiều domains dùng chung một edge IP?
6. Vì sao không nên kết nối Private Endpoint bằng IP trực tiếp?
7. TLS 1.2 và 1.3 nên được lựa chọn theo tiêu chí nào?
8. mTLS có thay thế authorization ở application không?
9. Wildcard certificate có bao phủ mọi subdomain mọi cấp không?
10. Not Before và Not After khác nhau như thế nào?
11. Fingerprint có phải private information không?
12. Renewal, rekey, rotation và revocation khác nhau ra sao?
13. Vì sao V2 certificate trong Key Vault chưa chắc đã deployed?
14. Azure-managed cert khác BYOC ở trách nhiệm vận hành nào?
15. Public CA cần xác minh quyền sở hữu domain bằng cách nào?
16. Vì sao ACME DNS-01 thường cần cho wildcard certificates?
17. CSR có chứa private key không?
18. PEM, DER và PKCS#12 khác nhau ở điểm nào?
19. Tại sao backing secret Key Vault certificate có thể chứa PFX?
20. Key Vault certificate/key/secret permissions có thể khác nhau thế nào?
21. Non-exportable HSM key có mặc định dùng được với gateway yêu cầu PFX không?
22. Self-signed certificate trong Key Vault có được browser công cộng tự tin cậy không?
23. App Service managed certificate có thể export sang AKS không?
24. App Service Key Vault app-setting reference khác TLS hostname binding như thế nào?
25. Front Door edge TLS và origin TLS dùng cùng chứng chỉ bắt buộc không?
26. App Gateway HTTPS listener có tự mã hóa backend connection không?
27. App Gateway muốn đọc Key Vault-backed TLS certificate cần điều kiện gì?
28. Khi dùng Key Vault versionless reference, còn bước kiểm chứng nào?
29. Kubernetes TLS Secret thường chứa những khóa dữ liệu nào?
30. Base64 của Kubernetes Secret có phải encryption không?
31. cert-manager tự động hóa những phần nào và không tự làm phần nào?
32. CSI Driver cập nhật file có khiến Spring Boot tự reload keystore không?
33. Truststore và keystore Java khác nhau thế nào?
34. Vì sao import CA không tự sửa hostname mismatch?
35. Dùng **openssl s_client** cần tham số nào để gửi SNI?
36. **openssl x509 -checkend** giúp kiểm tra điều gì?
37. Vì sao probe certificate từ Internet không thấy lỗi cert origin?
38. CA rollover cần làm gì trên clients trước khi đổi server chain?
39. Certificate pinning có thể làm rotation thất bại ra sao?
40. Revocation có bảo đảm mọi browser lập tức từ chối cert bị lộ không?
41. Khi private key bị lộ, những bước nào bắt buộc ngoài renewal?
42. Vì sao cần cả Key Vault expiry alert và serving-endpoint probe?
43. TLS handshake errors và HTTP 403 khác nhau như thế nào?
44. Tại sao không dùng TrustManager trust-all trong production?
45. Một hệ thống DR cần những dữ liệu/cấu hình TLS nào để hoạt động trở lại?

## Tài liệu tham khảo

- Microsoft Learn — *Azure Key Vault certificates overview*: https://learn.microsoft.com/azure/key-vault/certificates/about-certificates
- Microsoft Learn — *Renew Azure Key Vault certificates*: https://learn.microsoft.com/azure/key-vault/certificates/overview-renew-certificate
- Microsoft Learn — *Import a certificate into Key Vault*: https://learn.microsoft.com/azure/key-vault/certificates/tutorial-import-certificate
- Microsoft Learn — *Azure Key Vault RBAC*: https://learn.microsoft.com/azure/key-vault/general/rbac-guide
- Microsoft Learn — *Key Vault Event Grid overview*: https://learn.microsoft.com/azure/key-vault/general/event-grid-overview
- Microsoft Learn — *App Service TLS/SSL certificates*: https://learn.microsoft.com/azure/app-service/configure-ssl-certificate
- Microsoft Learn — *App Service TLS/SSL bindings*: https://learn.microsoft.com/azure/app-service/configure-ssl-bindings
- Microsoft Learn — *Azure Front Door custom-domain HTTPS*: https://learn.microsoft.com/azure/frontdoor/standard-premium/how-to-configure-https-custom-domain
- Microsoft Learn — *Application Gateway TLS termination*: https://learn.microsoft.com/azure/application-gateway/ssl-overview
- Microsoft Learn — *Application Gateway and Key Vault certificates*: https://learn.microsoft.com/azure/application-gateway/key-vault-certs
- Microsoft Learn — *Application Gateway end-to-end TLS*: https://learn.microsoft.com/azure/application-gateway/ssl-overview
- Microsoft Learn — *AKS Key Vault CSI Driver*: https://learn.microsoft.com/azure/aks/csi-secrets-store-driver
- Microsoft Learn — *AKS CSI secret rotation*: https://learn.microsoft.com/azure/aks/csi-secrets-store-configuration-options
- cert-manager documentation: https://cert-manager.io/docs/
- Kubernetes — *TLS Secrets*: https://kubernetes.io/docs/concepts/configuration/secret/#tls-secrets
- Kubernetes — *Ingress*: https://kubernetes.io/docs/concepts/services-networking/ingress/
- Spring Boot — *SSL bundles*: https://docs.spring.io/spring-boot/reference/features/ssl.html
- RFC 5280 — *X.509 Public Key Infrastructure*: https://www.rfc-editor.org/rfc/rfc5280
- RFC 8446 — *TLS 1.3*: https://www.rfc-editor.org/rfc/rfc8446
- Let's Encrypt — *Challenge types*: https://letsencrypt.org/docs/challenge-types/
- OWASP — *Transport Layer Security Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html
- Oracle — *keytool documentation*: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
