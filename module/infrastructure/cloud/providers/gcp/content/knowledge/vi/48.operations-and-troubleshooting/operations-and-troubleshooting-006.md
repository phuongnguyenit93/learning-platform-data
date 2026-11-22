# Xử lý lỗi chứng chỉ, DNS và health check của load balancer

Một ứng dụng Java/Spring Boot vẫn chạy tốt trong container hoặc trên máy ảo nhưng người dùng truy cập qua tên miền lại gặp **ERR_CERT_COMMON_NAME_INVALID**, **DNS_PROBE_FINISHED_NXDOMAIN**, **502 Bad Gateway** hoặc **503 Service Unavailable**. Những triệu chứng này có thể xuất phát từ các tầng rất khác nhau: DNS trả về IP cũ, load balancer phục vụ chứng chỉ sai, target proxy chọn sai cấu hình, firewall chặn health check hoặc ứng dụng trả mã HTTP không phù hợp cho đường dẫn kiểm tra sức khỏe. Nếu chỉ khởi động lại Pod hoặc thay DNS ngay khi có lỗi, sự cố có thể kéo dài và gây ảnh hưởng thêm.

Trong chương **Vận hành và xử lý sự cố** của module **CLOUD_PROVIDERS_GCP**, bài học xây dựng một quy trình chẩn đoán có thứ tự cho Google Cloud Load Balancing, Cloud DNS, Certificate Manager, Compute Engine, GKE, Cloud Run và các backend liên quan. Trọng tâm là quan sát và khoanh vùng lỗi trước, phân biệt hành vi của từng loại load balancer, đưa ra thay đổi an toàn và kiểm tra lại bằng bằng chứng thực tế.

Sau bài học, người học có thể:

- Vẽ đường đi của một HTTP(S) request từ DNS tới frontend, TLS proxy, URL map, backend service và ứng dụng.
- Phân loại lỗi DNS, TLS/certificate, routing và backend health từ triệu chứng của client.
- Chẩn đoán Google-managed và self-managed certificates, Certificate Manager, DNS authorization, CAA, SNI và chuỗi chứng chỉ.
- Phân biệt health checks của Application/Network Load Balancer, GKE Ingress và serverless NEG.
- Xác minh IP range health-check probes, firewall, cổng, request path, host header, response code, timeout và threshold.
- Sử dụng `dig`, `nslookup`, `curl`, `openssl`, `gcloud`, Logs Explorer và Cloud Monitoring.
- Xây runbook cho các tình huống lỗi sau thay DNS, đổi chứng chỉ, rollout ứng dụng hoặc sửa firewall.
- Thiết kế kiểm thử trước cutover, cảnh báo hết hạn chứng chỉ, tỷ lệ backend unhealthy và kế hoạch rollback.

## 1. Bức tranh tổng thể: request đi qua những tầng nào?

Với **external Application Load Balancer** có TLS termination tại frontend, đường đi điển hình:

~~~mermaid
flowchart LR
    U[Người dùng] --> DNS[DNS resolver A/AAAA]
    DNS --> VIP[Frontend IP + forwarding rule]
    VIP --> TLS[Target HTTPS proxy + certificate]
    TLS --> Route[URL map / host-path rules]
    Route --> BS[Backend service]
    BS --> BE[Instance group / NEG]
    BE --> APP[Java / Spring API]
    HC[Health-check probers] -.Kiểm tra backend hỗ trợ HC.-> BE
    BE --> DB[(Cloud SQL / service phụ thuộc)]
~~~

Từng điểm trong sơ đồ có cơ chế lỗi và bằng chứng riêng. Một lỗi xảy ra trước khi thiết lập TLS sẽ **không tạo HTTP request log ở backend**. Một lỗi 404 có thể do URL map hoặc do chính Spring Boot trả về. Một backend được đánh dấu healthy không chứng minh mọi endpoint nghiệp vụ đều thành công.

Với **proxy Network Load Balancer**, luồng routing khác: thường không có URL map dựa trên host/path của Application Load Balancer. Với **passthrough Network Load Balancer**, kết nối và health checks cũng khác. Vì vậy, bước đầu tiên luôn là xác định **loại load balancer và backend** chứ không sao chép một checklist dành cho global external Application Load Balancer sang mọi trường hợp.

### 1.1. Các nhóm thành phần

| Thành phần | Công việc chính | Lỗi điển hình |
|---|---|---|
| DNS authoritative/recursive | Biến hostname thành địa chỉ IPv4/IPv6 | NXDOMAIN, SERVFAIL, sai A/AAAA, cache cũ |
| Forwarding rule/VIP | Nhận kết nối ở địa chỉ và port đã cấu hình | Sai IP, sai port, rule không tồn tại |
| TLS target proxy | Chọn chứng chỉ theo SNI, áp SSL policy | Cert sai tên, hết hạn, thiếu chain, handshake failed |
| URL map | Chọn route/backend theo hostname/path | 404, đi nhầm backend, redirect loop |
| Backend service | Phân phối request tới backend hợp lệ | Không có backend đủ healthy, cấu hình timeout |
| Health check | Xác định backend có phục vụ được không | Port/path/host/firewall/trả mã không đạt |
| Backend ứng dụng | Xử lý request thực tế | 500, timeout, thiếu database connection |
| Network/IAM | Cho phép đúng đường kết nối | Firewall deny, Private Service Connect/NEG mismatch |

### 1.2. Ba kiểu lỗi phải tách

1. **Không phân giải được hostname:** dừng ở DNS; chưa cần thay chứng chỉ hay Pod.
2. **Phân giải được nhưng TLS handshake không thành công:** kiểm tra địa chỉ đích, SNI, certificate resource/attachment, chain, policy và phiên bản TLS.
3. **TLS hợp lệ nhưng HTTP trả 4xx/5xx:** kiểm tra URL map, backend health và logs; không mặc định là lỗi chứng chỉ.

Đặt câu hỏi: lỗi xảy ra ở **toàn bộ tên miền**, **một hostname**, **một path**, **một region**, **một loại client**, hay **một phần request**? Phạm vi giúp xác định tầng nghi vấn nhanh hơn việc thử thay đổi ngẫu nhiên.

## 2. Chuẩn bị thông tin trước khi sửa production

Mở incident theo quy trình nội bộ nếu error budget hoặc business SLO bị ảnh hưởng. Thu thập:

- Project ID, region/zone, tên load balancer, loại load balancer và tên frontend IP.
- Domain/FQDN, timestamp UTC, client IP/ASN hoặc khu vực ảnh hưởng.
- HTTP/HTTPS port, giao thức IPv4/IPv6, SNI hostname.
- Frontend forwarding rule, target proxy, URL map, backend service, NEG/instance group.
- Certificate Manager certificate/map hoặc Compute Engine SSL certificate được gắn.
- Health-check type, port, path, host, thresholds, timeout và logging.
- Thay đổi gần nhất: DNS, ingress, SSL policy, certificate rotation, GKE rollout, firewall, IAM, migration.
- Error message nguyên văn, HTTP status, request ID, trace, LB logs và backend logs.

Không gửi token, private key, cookie phiên đăng nhập hoặc dữ liệu khách hàng vào ticket/debug channel. Khi chia sẻ output `openssl`, chỉ cần metadata public certificate chain, issuer, SAN, expiry và kết quả verify; **không đưa private key**.

### 2.1. Bộ lệnh điều tra không phá hủy

~~~bash
# Chỉ đọc thông tin. Thay các placeholder trước khi chạy.
gcloud config get-value project
gcloud compute forwarding-rules list
gcloud compute backend-services list
gcloud compute health-checks list
gcloud certificate-manager certificates list
gcloud compute ssl-certificates list --global
~~~

Các tài nguyên regional cần `--region=REGION` ở những lệnh hỗ trợ, còn global dùng `--global`. Không suy rằng tên backend service giống tên service Kubernetes hoặc Cloud Run. Với Shared VPC/địa hình nhiều project, xác minh project sở hữu forwarding rule, backend và certificate.

### 2.2. Không đổi nhiều tầng một lần

Nếu một lần vừa cập nhật A record, xoay chứng chỉ, thay URL map, sửa firewall và deploy revision mới, rất khó xác định thay đổi nào có tác dụng. Mỗi bước nên có:

1. Giả thuyết cụ thể.
2. Kiểm tra không phá hủy xác nhận hoặc bác bỏ giả thuyết.
3. Phương án sửa nhỏ nhất.
4. Mốc thời gian áp dụng và dự kiến độ trễ lan truyền.
5. Cách rollback và chỉ số xác nhận hồi phục.

## 3. Bảng chẩn đoán nhanh theo triệu chứng

| Triệu chứng client | Tầng ưu tiên kiểm tra | Bằng chứng hữu ích |
|---|---|---|
| `NXDOMAIN` | DNS authoritative/delegation, tên record | `dig +trace`, SOA, NS |
| `SERVFAIL` | DNSSEC, resolver/authoritative, policy | `dig +dnssec`, kiểm tra DS/DNSKEY |
| DNS trả IP cũ | A/AAAA, resolver cache, TTL, delegation | `dig @authoritative` và public resolvers |
| Client IPv4 chạy nhưng IPv6 lỗi | AAAA và frontend IPv6 | `curl -4`, `curl -6`, forwarding rule |
| `ERR_CERT_COMMON_NAME_INVALID` | SNI, SAN, LB IP, certificate map | `openssl s_client -servername` |
| Chứng chỉ hết hạn | Rotation/renewal/cert attachment | `notAfter`, managed status và CA authorization |
| `SSL handshake failure` | TLS version/cipher, cert chain, SNI | `openssl s_client`, SSL policy |
| HTTPS 301/302 loop | URL map, redirect, backend proxy headers | `curl -IL` và app config |
| HTTPS 404 | URL map host/path hoặc ứng dụng | LB statusDetails và backend logs |
| HTTPS 502/503 | Backend health/connection/timeout hoặc LB config | LB logs, backend service get-health, health-check logging |
| Backend `UNHEALTHY` | Port/path/host/status/threshold/firewall | `get-health`, health-check describe, app logs |
| GKE ingress healthy nhưng request lỗi | Readiness vs business endpoint, NEG, rollout | GKE events, Service/EndpointSlice, logs |
| Cloud Run serverless NEG báo lỗi | Service/revision/ingress/auth/cold start | Cloud Run metrics/logs; không tìm LB health check không tồn tại |

Đây là bảng **định hướng**, không phải quy tắc một-một. Một mã 503 có thể do ứng dụng tự trả hoặc do load balancer không chọn được backend; cần phân biệt bằng request log và `statusDetails`.

## 4. DNS: từ registrar đến địa chỉ frontend

### 4.1. Chuỗi phân giải

Với `api.example.com`:

~~~mermaid
flowchart LR
    C[Client] --> R[Recursive resolver]
    R --> Root[Root DNS]
    Root --> TLD[.com nameservers]
    TLD --> NS[Authoritative NS for example.com]
    NS --> RR[A / AAAA / CNAME record]
    RR --> IP[Load balancer VIP]
~~~

Thông thường recursive resolver đã cache nhiều bước và không cần hỏi toàn bộ chuỗi ở mỗi request. Sửa record trong Cloud DNS **không đủ** nếu registrar vẫn delegate domain sang nhà cung cấp DNS khác. Ngoài ra, public zone và private zone cùng tên có thể trả câu trả lời khác nhau theo môi trường.

### 4.2. Chẩn đoán theo tầng

~~~bash
# Kiểm tra record từ resolver mặc định.
dig api.example.com A
dig api.example.com AAAA
dig api.example.com CNAME

# So sánh resolver công cộng.
dig @8.8.8.8 api.example.com A
dig @1.1.1.1 api.example.com A

# Xem authoritative nameserver và đường delegation.
dig example.com NS
dig +trace api.example.com A

# Kiểm tra SOA và TTL.
dig example.com SOA
dig api.example.com A +noall +answer
~~~

Lưu lại cả `ANSWER SECTION`, `AUTHORITY SECTION`, status và TTL. DNS trả record nhưng trỏ **sai forwarding rule IP** vẫn là lỗi; không chỉ xem “có trả IP hay không”.

### 4.3. Cloud DNS

~~~bash
gcloud dns managed-zones list --project=DNS_PROJECT_ID

gcloud dns managed-zones describe ZONE_NAME \
  --project=DNS_PROJECT_ID

gcloud dns record-sets list \
  --zone=ZONE_NAME \
  --project=DNS_PROJECT_ID
~~~

Cloud DNS zone có thể là public hoặc private; private zones có visibility theo VPC. Một record dùng trong private zone không tự được công khai cho Certificate Authority trên internet. Khi certificate cần DNS authorization, phải đặt record xác minh trong **public authoritative DNS** của domain theo cơ chế được chọn.

### 4.4. TTL và negative caching

- TTL của A/AAAA/CNAME cho biết resolver có thể cache record trong bao lâu, nhưng ứng dụng và mạng có thể có cache riêng.
- Trước cutover, giảm TTL từ sớm cho các record cần chuyển để cho phép cache cũ hết hạn.
- NXDOMAIN có thể bị **negative cache** theo SOA, nên thêm record mới không có hiệu lực ngay với mọi resolver.
- Một số resolver/client không tuân thủ TTL chính xác; không hứa cutover tức thời.
- Khi cần xác minh ngay VIP mới, dùng `curl --resolve` để bỏ qua DNS cho riêng phép thử.

Đừng xóa A/AAAA cũ khi chưa hiểu việc cutover đã hoàn tất tới mọi nhóm client và certificate đã sẵn sàng. DNS rollback không tự khôi phục transaction/database state.

### 4.5. IPv6 và dual stack

Một A record đúng nhưng AAAA record trỏ về địa chỉ IPv6 không thuộc LB đang phục vụ có thể khiến một số client dùng IPv6 gặp lỗi. Kiểm tra cả hai:

~~~bash
curl -4 -vI https://api.example.com/health
curl -6 -vI https://api.example.com/health
dig api.example.com A +short
dig api.example.com AAAA +short
~~~

Nếu LB không có IPv6 frontend tương ứng, không để AAAA cũ chỉ tới dịch vụ khác. Nếu cần gỡ AAAA, thực hiện change có kiểm soát vì có thể ảnh hưởng client chỉ hỗ trợ IPv6.

### 4.6. DNSSEC và SERVFAIL

Nếu authoritative DNS được chuyển provider, cần kiểm tra DS record tại registrar và DNSKEY tại DNS zone. DS cũ có thể khiến validating resolvers trả SERVFAIL dù authoritative trả A/AAAA bình thường. Dùng:

~~~bash
dig +dnssec api.example.com A
dig example.com DS
dig example.com DNSKEY
~~~

Không tắt DNSSEC toàn bộ chỉ để “thử nhanh” trên production. Đối chiếu delegation/signing chain và runbook chuyển nhà cung cấp DNS.

## 5. Chứng chỉ TLS: phân biệt các loại resource trên GCP

Trong Google Cloud có ít nhất hai nhóm thường gặp:

1. **Compute Engine SSL certificates** (Classic Certificates), gồm Google-managed và self-managed, được quản lý bằng `gcloud compute ssl-certificates`. Mức hỗ trợ tùy load balancer; không phải mọi LB regional đều dùng được Google-managed loại này.
2. **Certificate Manager certificates**, gồm Google-managed với load balancer authorization hoặc DNS authorization và self-managed. Quản lý bằng `gcloud certificate-manager`, certificate map hoặc gắn trực tiếp vào target proxy theo loại LB.

Một chứng chỉ báo **ACTIVE** chỉ nói việc cấp chứng chỉ thành công; chưa chắc load balancer đang phục vụ nó. Cần kiểm tra **certificate map/entry, hostname selector, target proxy attachment, propagation và client-observed chain**.

### 5.1. Scope khác nhau

| Thành phần | Global | Regional |
|---|---|---|
| Compute Engine Google-managed SSL certificate | Dùng cho các loại LB global được hỗ trợ | Không áp dụng chung cho regional Application LB |
| Certificate Manager Google-managed | Có chứng chỉ global; DNS auth hoặc LB auth theo loại | Có chứng chỉ regional; yêu cầu DNS authorization phù hợp |
| Certificate map | Dùng với các cấu hình global được hỗ trợ | Cách gắn chứng chỉ có thể khác; regional thường gắn trực tiếp vào target proxy |
| Target HTTPS proxy | Có dạng global và regional | Lệnh `gcloud` cần scope phù hợp |

Với **regional Google-managed Certificate Manager certificate**, phải dùng **regional, per-project DNS authorization** và scope cùng region. Không tạo global DNS authorization rồi mong gắn cho regional cert.

### 5.2. Kiểm tra Compute Engine managed certificate

~~~bash
gcloud compute ssl-certificates list --global

gcloud compute ssl-certificates describe CERT_NAME \
  --global \
  --format="yaml(name,type,managed.status,managed.domainStatus,expireTime)"
~~~

Các trạng thái đáng chú ý:

- `PROVISIONING`: đang xác minh/cấp chứng chỉ; cần kiểm tra DNS, LB attachment và thời gian lan truyền.
- `ACTIVE`: đã cấp; kiểm tra nó có thực sự được phục vụ không.
- `FAILED_NOT_VISIBLE` ở domain: CA không nhìn thấy domain qua load balancer IP phù hợp.
- `FAILED_CAA_CHECKING` hoặc `FAILED_CAA_FORBIDDEN`: kiểm tra CAA chain và CA được cho phép.
- `FAILED_RATE_LIMITED`: CA giới hạn yêu cầu phát hành, không liên tục tạo chứng chỉ mới vô hạn.

Tên trạng thái ở đây thuộc **Compute Engine SSL certificate**. Không dùng chúng như enum của mọi Certificate Manager resource.

### 5.3. Kiểm tra Certificate Manager certificate

~~~bash
gcloud certificate-manager certificates list --location=global

gcloud certificate-manager certificates describe CERT_NAME \
  --location=global \
  --format="yaml(name,managed.state,managed.provisioningIssue,managed.authorizationAttemptInfo,sanDnsnames,expireTime)"

gcloud certificate-manager dns-authorizations list --location=global
~~~

Với regional certificate, thay `--location=global` bằng region thật. Những trường quan trọng:

- `managed.state=PROVISIONING`: đang xử lý phát hành/gia hạn; đọc `provisioningIssue` và `authorizationAttemptInfo`.
- `managed.state=ACTIVE`: chứng chỉ đã sẵn sàng, nhưng vẫn phải được gắn đúng proxy/map.
- `managed.state=FAILED`: quá trình phát hành/gia hạn thất bại; sửa nguyên nhân và làm theo hướng dẫn tạo resource thay thế, không coi nó tự retry vô hạn.
- `authorizationAttemptInfo.failureReason`: có thể là `CONFIG`, `CAA` hoặc `RATE_LIMITED`.

Tùy biến thể certificate và thời điểm triển khai, lệnh mô tả có thể hiển thị các field khác nhau. Dựa vào output thực của API thay vì giả định mọi field luôn có.

## 6. Google-managed certificate không được cấp hoặc gia hạn

### 6.1. Load balancer authorization

Với **load balancer authorization**, CA cần xác minh domain trỏ tới frontend LB hợp lệ. Kiểm tra:

- A và AAAA cho **tất cả SAN domains** đều trỏ tới các IP frontend đúng; không còn IP cũ hoặc IPv6 rơi vào hệ thống khác.
- Target proxy và forwarding rule đã tồn tại, kết nối 443 được phục vụ.
- Chứng chỉ có cấu hình phù hợp và target proxy có gắn nó theo hướng dẫn sản phẩm.
- DNS authoritative có câu trả lời nhất quán từ nhiều mạng/vị trí.
- CDN/GeoDNS hoặc reverse proxy bên ngoài có thể ngăn domain validation nhiều điểm (MPIC).
- CAA record cho phép CA do Google-managed certificate sử dụng.

Với Google-managed Compute Engine certificates, quá trình cấp có thể mất tới khoảng **60 phút sau khi DNS/LB thay đổi đã lan truyền**, nhưng DNS propagation có thể lâu hơn tùy resolver. Không tạo/chuyển chứng chỉ liên tục khi cấu hình chưa đúng, vì rate limit và backoff có thể kéo dài tình trạng.

### 6.2. DNS authorization

Certificate Manager có **DNS authorization** để chứng minh quyền kiểm soát domain qua CNAME do API tạo. Phù hợp cả khi DNS public chưa trỏ frontend LB hoặc có CDN ở trước.

~~~bash
gcloud certificate-manager dns-authorizations describe AUTH_NAME \
  --location=global
~~~

Trong output, đọc `dnsResourceRecord.name`, `type` và `data`. Tạo **đúng CNAME** ở authoritative public DNS; không tự đoán giá trị từ domain. Kiểm tra:

~~~bash
dig _acme-challenge.example.com CNAME +short
~~~

Với `PER_PROJECT_RECORD`, tên CNAME có hậu tố riêng cho project, **không nhất thiết** chính xác là `_acme-challenge.example.com`; phải copy từ `dnsResourceRecord`. Không tạo cả CNAME và TXT cùng tên bởi DNS standard không cho CNAME cùng tồn tại với RR type khác tại cùng owner name.

Google-managed regional Certificate Manager certificates sử dụng **per-project regional DNS authorization**. Nếu đã cấu hình CNAME đúng nhưng `managed.state` vẫn PROVISIONING, xem authorization attempts và kiểm tra authoritative public DNS thực đang trả lời.

### 6.3. CAA records

CAA cho phép domain owner hạn chế CA nào được phát hành certificate. Xem:

~~~bash
dig example.com CAA
dig api.example.com CAA
~~~

Với **per-project DNS authorization** (bao gồm regional managed certificates), CA được hỗ trợ là **Google Trust Services**, nên CAA phải cho phép `pki.goog`. Với các cơ chế khác, Google có thể dùng `pki.goog` hoặc `letsencrypt.org` theo tài liệu loại cert. CAA ở parent domain cũng có thể ảnh hưởng subdomain theo quy tắc DNS/CAA.

Chỉ sửa record sau khi được domain owner phê duyệt; không xóa mọi hạn chế CAA trên toàn domain để giải quyết một certificate đơn lẻ.

### 6.4. GeoDNS, CDN và MPIC

Trong một số thiết kế GeoDNS, `api.example.com` phân giải thành IP khác nhau tùy vị trí. Certificate Authority kiểm tra từ **nhiều điểm nhìn**; một vị trí trả IP không đúng có thể khiến phát hành hoặc gia hạn thất bại.

Nếu CDN bên thứ ba đứng trước LB, luồng xác minh load balancer authorization có thể không tới được LB. Khi đó cân nhắc **Certificate Manager DNS authorization** thay vì tắt CDN/đưa website về trạng thái không bảo vệ. Thay đổi cần tuân theo kiến trúc và chính sách bảo mật của hệ thống.

## 7. Certificate ACTIVE nhưng client vẫn nhận cert sai

ACTIVE không tự đảm bảo frontend đang dùng certificate đó. Kiểm tra:

1. FQDN/SAN có đúng hostname của client, kể cả wildcard coverage?
2. Client đang phân giải tới đúng forwarding rule IP?
3. Target HTTPS proxy đang gắn **Certificate Manager map** hay **Compute SSL certificate trực tiếp**?
4. Trong certificate map, entry hostname chính xác/wildcard/default có trỏ tới cert mong đợi?
5. Mỗi target proxy (global/regional) có đúng scope và certificate resource?
6. Việc attach và propagation tới GFE đã hoàn tất?
7. Client có truyền **SNI** không? Nếu không, nó có thể nhận default certificate.

### 7.1. Kiểm tra từ client bằng SNI

~~~bash
# Quan sát chain mà LB thực sự trả; không cần private key.
echo | openssl s_client \
  -connect LB_IP:443 \
  -servername api.example.com \
  -showcerts \
  -verify_return_error

# Đọc certificate leaf.
echo | openssl s_client -connect LB_IP:443 \
  -servername api.example.com 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
~~~

Nếu client kết nối qua hostname với SNI nhưng `openssl` không truyền `-servername`, kết quả có thể là **default certificate** và dẫn tới kết luận sai. `CN` không đủ để xác định hợp lệ; cần kiểm tra **SAN**, chain và CA trust. Ví dụ wildcard `*.example.com` không bao phủ apex `example.com` hoặc hostname hai cấp `a.b.example.com`.

### 7.2. Kiểm tra target HTTPS proxy và map

~~~bash
gcloud compute target-https-proxies list
gcloud compute target-https-proxies describe PROXY_NAME --global

gcloud certificate-manager maps list
gcloud certificate-manager maps entries list --map=MAP_NAME
gcloud certificate-manager maps entries describe ENTRY_NAME --map=MAP_NAME
~~~

Với proxy regional, sử dụng `--region=REGION` nếu tài nguyên thuộc regional LB; với Certificate Manager regional, kiểm tra cách gắn trực tiếp được hỗ trợ. Chứng chỉ gắn trực tiếp vào proxy và certificate map có thể tương tác theo quy tắc ưu tiên riêng; khi có certificate map trên proxy, **không giả định** certificate gắn trực tiếp sẽ được chọn như trước.

### 7.3. Self-managed certificate

Kiểm tra:

- Certificate leaf, intermediate chain, issuer và expiry.
- Private key tương ứng với public certificate khi tải lên (chỉ kiểm tra an toàn trên hệ thống được phép; không tiết lộ key).
- Chuỗi PEM đúng thứ tự, không thiếu intermediate.
- SAN đủ hostname và certificate path được attach.
- SSL policy hỗ trợ phiên bản/cipher mà client yêu cầu.
- Certificate rotation đã thực hiện theo nguyên tắc **attach new → verify → remove old**.

Không xóa chứng chỉ cũ ngay sau khi upload chứng chỉ mới. Cần xác minh thời gian lan truyền, client còn dùng IPv4/IPv6 và certificate thực đang được phục vụ trên mọi frontend.

### 7.4. TLS version, cipher và mTLS

Lỗi handshake không chỉ do certificate. Kiểm tra:

- SSL policy tối thiểu TLS 1.2/1.3 theo yêu cầu hệ thống và client.
- Thiết bị/client cũ có hỗ trợ cipher/key algorithm tương ứng không?
- Nếu yêu cầu **mTLS**, CA trust/config verification giữa client và LB được thiết lập ra sao?
- Không hạ bảo mật SSL policy xuống TLS lỗi thời chỉ để một client cũ kết nối mà chưa có đánh giá bảo mật.

TLS frontend từ người dùng tới LB và TLS từ LB tới **HTTPS backend** là hai kết nối khác nhau. Frontend certificate hợp lệ không chứng minh backend TLS đang thành công. Cần kiểm tra đúng phía có lỗi.

## 8. Kiểm tra DNS độc lập với certificate

Lệnh `curl --resolve` ép một hostname dùng IP cụ thể cho phiên kiểm tra, **giữ đúng SNI và Host header**:

~~~bash
curl -vk --resolve api.example.com:443:LB_IP \
  https://api.example.com/health
~~~

**Kết quả chẩn đoán:**

- Nếu truy cập theo tên miền lỗi, nhưng `--resolve` tới LB_IP đúng thành công: tập trung DNS/cache/delegation.
- Nếu cả hai lỗi cert giống nhau: kiểm tra cert đang được LB_IP phục vụ, SNI và cert map.
- Nếu TLS tốt nhưng trả 503: tiếp tục backend/health check, không sửa DNS.
- Nếu thử bằng IP trực tiếp `https://LB_IP` lỗi hostname: đây có thể là hành vi bình thường của chứng chỉ phát hành cho domain, không phải cấu hình sai.

`-k` bỏ qua xác minh chứng chỉ, chỉ nên dùng khi debug; **không dùng nó làm bằng chứng TLS an toàn**. Để xác minh bảo mật cuối cùng, bỏ `-k`:

~~~bash
curl -v --resolve api.example.com:443:LB_IP \
  https://api.example.com/health
~~~

## 9. Health check: load balancer đang đo điều gì?

Health check là phép thử từ hạ tầng Google (hoặc mô hình proxy theo loại LB) tới backend, nhằm quyết định backend có đủ điều kiện nhận traffic. Nó không tự kiểm tra hành trình nghiệp vụ end-to-end và không nhất thiết dùng chính cổng/path mà người dùng đang gọi.

### 9.1. Các dạng health check phổ biến

| Loại health check | Kiểm tra | Lỗi thường gặp |
|---|---|---|
| TCP | Có thể tạo kết nối TCP tới IP:port | Không có listener, firewall deny, wrong port |
| HTTP | Gửi HTTP request tới host/path/port | 301/302, 401, 404, 500, host mismatch |
| HTTPS | TLS + HTTP request tới backend | TLS endpoint/cert behavior, port/path, app error |
| HTTP/2 | Request giao thức HTTP/2 nếu backend hỗ trợ | Protocol mismatch, timeout |
| SSL | Kiểm tra SSL/TLS handshake theo loại backend/LB hỗ trợ | Sai TLS configuration |
| gRPC | Kiểm tra trạng thái gRPC Health Checking Protocol | Không triển khai service/method health tương ứng |

Loại health check được phép phụ thuộc LB/backend và backend service. Không chọn HTTPS health check chỉ vì người dùng gọi HTTPS frontend: LB có thể terminate TLS ở frontend và dùng HTTP backend. Kiểm tra cấu hình thực.

### 9.2. Trạng thái Healthy/Unhealthy

Health checker có ngưỡng:

- `checkIntervalSec`: thời gian giữa các lần probe.
- `timeoutSec`: deadline cho một probe.
- `healthyThreshold`: số lần probe thành công liên tiếp để chuyển Healthy.
- `unhealthyThreshold`: số lần thất bại liên tiếp để chuyển Unhealthy.

Nhiều probe có thể chạy từ nhiều nguồn khác nhau; thời gian chuyển trạng thái không đơn giản bằng một phép nhân cố định. Sau khi sửa firewall hoặc ứng dụng, chờ đủ chu kỳ và quan sát trạng thái/health logs thay vì reload Console liên tục.

### 9.3. Health check phải có hợp đồng rõ

Với Spring Boot Actuator:

- `/actuator/health/liveness`: process có cần restart không?
- `/actuator/health/readiness`: instance có sẵn sàng nhận traffic không?

Không nhất thiết dùng liveness hoặc readiness làm **Google LB health check** ở mọi môi trường. Chọn path dựa trên khả năng chịu lỗi:

- Trả thành công khi instance thật sự có thể nhận request phục vụ user.
- Không bắt buộc xác thực cho probe nếu probe không hỗ trợ credentials; giới hạn truy cập network.
- Không redirect từ HTTP sang HTTPS ngoài ý muốn khi backend probe là HTTP.
- Trả HTTP 200 cho trạng thái đạt theo yêu cầu health-check type; tùy dịch vụ, redirect 301/302 hoặc 204 có thể bị coi thất bại, phải xem chính xác health check expectation.
- Tránh check nhiều dependency không thiết yếu khiến mọi instance cùng unhealthy khi một service phụ trợ lỗi.

## 10. Nguồn health-check probes và firewall

**Không có một dải IP health-check dùng chung cho tất cả LB và backend.** Cần xem bảng *Probe IP ranges and firewall rules* của Google Cloud theo loại Application/Network LB, scope, backend type và IPv4/IPv6.

### 10.1. Những khác biệt quan trọng

| LB/backend | Nguồn health-check probe | Cần chú ý |
|---|---|---|
| Global external Application LB + VM instance group/zonal NEG | IP ranges dành cho Google health check systems | Kiểm tra bảng nguồn hiện hành, ví dụ `35.191.0.0/16` cho cấu hình được tài liệu liệt kê |
| Regional external/internal Application LB + VM/zonal NEG | Google health-check IP ranges theo LB type | **Proxy-only subnet** còn là nguồn traffic data plane cho Envoy, không đồng nhất với health-check probe |
| Hybrid NEG hoặc regional internet NEG | Có thể từ Envoy proxy-only subnet theo sản phẩm | Firewall/network route phải khớp điểm gửi thật |
| External/internal passthrough Network LB | Các dải riêng theo sản phẩm và IPv4/IPv6 | Có những cấu hình khác nguồn Application LB |
| Serverless NEG (Cloud Run) | **Không hỗ trợ LB-level health check** | Xem Cloud Run service/revision/app health và ingress |
| Private Service Connect NEG | Không dùng health-check resource kiểu VM backend | Xem trạng thái PSC/producer/service |

Những ví dụ cũ thường nêu `35.191.0.0/16` và `130.211.0.0/22`; **không được cấp allow theo hai dải này một cách vô điều kiện** hoặc bỏ qua các dải hiện hành khác như IPv6/passthrough LB. Chọn đúng range trong tài liệu cho chính LB đang dùng.

### 10.2. Firewall cho backend VM

Ví dụ cú pháp một allow rule (chỉ áp dụng khi đã xác minh nguồn probe):

~~~bash
gcloud compute firewall-rules create allow-selected-hc \
  --network=VPC_NAME \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-ranges=VERIFIED_PROBE_CIDR \
  --target-tags=allow-app-hc
~~~

`VERIFIED_PROBE_CIDR` là **placeholder**, không được chạy nguyên văn. Rule cần đúng VPC, đúng target (network tag hoặc service account), đúng backend port, đúng scope. Firewall policy ở cấp organization/folder/VPC và firewall/iptables của guest OS có thể vẫn deny. Tránh mở `0.0.0.0/0` vào application port chỉ để health check pass.

### 10.3. Proxy-only subnet không phải health-check subnet

Regional internal/external Application Load Balancers dựa trên Envoy cần **proxy-only subnet**. Traffic frontend-to-backend có thể xuất phát từ proxy-only subnet, trong khi probes tới VM/zonal NEG có thể từ dải health-check riêng. Một backend có thể healthy nhưng request thật vẫn bị chặn bởi firewall chưa cho phép traffic từ proxy-only subnet.

Quy trình kiểm tra phải gồm **hai đường**:

1. Health checker → backend: probe có vào đúng port không?
2. Envoy proxy → backend: traffic application có được firewall/network cho phép không?

Không dùng kết quả `get-health HEALTHY` làm bằng chứng tất cả network flows đều thông.

## 11. Đọc cấu hình và trạng thái backend bằng gcloud

### 11.1. Xác định health check được gắn

~~~bash
gcloud compute backend-services describe BACKEND_SERVICE \
  --global \
  --format="yaml(name,protocol,portName,healthChecks,backends,timeoutSec,logConfig)"

gcloud compute health-checks describe HEALTH_CHECK \
  --global
~~~

Đối với regional backend, thay `--global` bằng `--region=REGION`. Với legacy health check hoặc Network LB dùng cấu hình khác, xác minh đúng resource type thay vì ép lệnh global.

Kiểm tra:

- Backend service đang tham chiếu health check nào?
- Health-check port cố định hay `USE_SERVING_PORT`?
- Instance group có **named port** trùng `portName` của backend service?
- Với zonal NEG, endpoint IP:port có đúng và ứng dụng có listener?
- Timeout và request path có hợp đồng với app?

### 11.2. Đọc backend health

~~~bash
gcloud compute backend-services get-health BACKEND_SERVICE --global

# Regional backend:
gcloud compute backend-services get-health BACKEND_SERVICE \
  --region=REGION
~~~

Kết quả giúp xác định backend instance/group nào Healthy/Unhealthy và phạm vi ảnh hưởng. Nếu mọi backend cùng Unhealthy sau một firewall change, kiểm tra firewall trước khi restart app. Nếu chỉ một instance Unhealthy, kiểm tra instance logs, process, port và tài nguyên của node đó.

### 11.3. Kiểm tra trực tiếp trong VM

Ví dụ Linux VM có application port 8080:

~~~bash
ss -lntp | grep ':8080'
curl -v --max-time 5 http://127.0.0.1:8080/healthz

# Kiểm tra qua IP nội bộ chỉ khi đường mạng và IAM cho phép.
curl -v --max-time 5 http://BACKEND_PRIVATE_IP:8080/healthz
~~~

Loopback thành công không chứng minh ứng dụng đang bind `0.0.0.0` hoặc địa chỉ backend IP, và không chứng minh Google probe đi qua firewall được. Phải kết hợp listener, host firewall, VPC firewall, health-check logs và get-health.

## 12. Health check sai path, port, Host hoặc status code

### 12.1. Port mismatch

Các tình huống:

- Health check gửi port 80 nhưng app lắng nghe 8080.
- Backend service portName là `http` nhưng instance group named port mapping chưa khai báo.
- NEG IP:port từ Pod khác với port container thực.
- Service Kubernetes `port`, `targetPort`, `nodePort` bị nhầm.

Kiểm tra cấu hình cả 4 lớp: health check → backend service → instance group/NEG → application listener. Với instance group, xác minh named port:

~~~bash
gcloud compute instance-groups managed get-named-ports MIG_NAME \
  --zone=ZONE
~~~

Lệnh áp dụng MIG zonal; regional MIG có cách gọi/flag tương ứng. Không mặc định backend port luôn lấy từ health-check port.

### 12.2. Path mismatch

Ví dụ health check gọi `GET /` nhưng Spring Boot chỉ phục vụ `/actuator/health`. Nếu `/` trả 404, backend bị đánh dấu unhealthy dù API chính chạy tốt.

Kiểm tra path bằng curl từ môi trường được phép:

~~~bash
curl -i http://BACKEND_PRIVATE_IP:8080/
curl -i http://BACKEND_PRIVATE_IP:8080/actuator/health/readiness
~~~

Sửa health-check request path sang endpoint được ứng dụng duy trì ổn định; không tạo một route bất kỳ luôn trả 200 nếu nó không phản ánh khả năng phục vụ.

### 12.3. Host header và virtual host

Một backend có thể route theo hostname, ví dụ `Host: api.internal.example.com`. Health check mặc định gửi Host theo cơ chế của loại health check, có thể khác domain ngoài. Khi app/web server chỉ trả 200 cho virtual host được cấu hình, probe nhận 404.

Test:

~~~bash
curl -i \
  -H 'Host: api.internal.example.com' \
  http://BACKEND_PRIVATE_IP:8080/healthz
~~~

Đặt host field của health check theo yêu cầu nếu loại probe hỗ trợ. Không dùng domain public làm Host cho backend nội bộ mà chưa kiểm tra redirect/HSTS/host validation.

### 12.4. Authentication và redirect

Nếu Spring Security bảo vệ `/actuator/health` bằng đăng nhập/OAuth, health checker không có bearer token và sẽ nhận 401/403. Có thể tạo health endpoint riêng, trả thông tin tối thiểu, chỉ cho probe qua network và không lộ thông tin nhạy cảm.

Nếu HTTP backend tự redirect sang HTTPS bằng 301/302 nhưng health checker HTTP chờ 200, backend có thể bị coi unhealthy. Chọn probe protocol tương ứng hoặc loại trừ path `/healthz` khỏi redirect khi an toàn. Không hủy TLS toàn bộ để test health.

### 12.5. Readiness quá nghiêm ngặt

Nếu readiness gọi đến mọi dịch vụ ngoài (email, analytics, third-party API) thì sự cố nhỏ có thể khiến tất cả instance cùng trả 503, làm LB mất toàn bộ healthy capacity. Chỉ đưa dependency **thật sự cần cho việc nhận request** vào readiness; liveness thường nên đơn giản và tránh tạo restart storm.

## 13. GKE: Ingress, Service, Pod readiness và NEG

GKE có nhiều cơ chế expose ứng dụng: Ingress/Gateway với Application Load Balancer, Service type LoadBalancer (passthrough Network LB), standalone NEG, service mesh. Chúng **không** có cùng cơ chế health-check.

### 13.1. Với GKE Ingress

Điều tra:

~~~bash
kubectl get ingress -A
kubectl describe ingress INGRESS_NAME -n NAMESPACE
kubectl get services -n NAMESPACE
kubectl describe service SERVICE_NAME -n NAMESPACE
kubectl get pods -n NAMESPACE -o wide
kubectl get endpointslices -n NAMESPACE
kubectl describe pod POD_NAME -n NAMESPACE
~~~

Trong Cloud Console → Load Balancing, truy tới backend service và health check do GKE controller tạo; xem `get-health`. Một Pod `Ready=True` không tự đảm bảo health check của Google Load Balancer đã đúng cấu hình và chuyển Healthy.

### 13.2. BackendConfig, readinessProbe và suy diễn health check

Với GKE Ingress, cách chọn health check có thể dựa vào **BackendConfig** hoặc suy ra từ Pod readiness probe tại thời điểm tạo backend. Việc sửa readiness probe trong Deployment sau đó **không nhất thiết tự cập nhật health-check resource** đã tạo trên LB. Nếu cần cấu hình ổn định, dùng BackendConfig theo hướng dẫn GKE.

Ví dụ **BackendConfig** rút gọn cho GKE Ingress:

~~~yaml
apiVersion: cloud.google.com/v1
kind: BackendConfig
metadata:
  name: api-hc
spec:
  healthCheck:
    type: HTTP
    requestPath: /actuator/health/readiness
    port: 8080
    checkIntervalSec: 10
    timeoutSec: 5
    healthyThreshold: 2
    unhealthyThreshold: 3
~~~

Gắn BackendConfig qua annotation trên đúng Kubernetes Service port. Port trong BackendConfig phải phù hợp backend mode (container-native NEG vs instance group). Đây là ví dụ cấu trúc, cần đối chiếu phiên bản GKE và LB type cụ thể trước khi áp dụng.

### 13.3. Pod và network

- Pod có thể `Ready=True` nhưng ứng dụng chỉ bind localhost, không thể nhận kết nối tới Pod IP.
- Service selector sai khiến EndpointSlice không chứa Pod đang phục vụ.
- NEG endpoint chưa được đồng bộ sau rollout.
- NetworkPolicy/VPC firewall hoặc policy mesh có thể chặn probe.
- Startup lâu khiến health checker đánh dấu unhealthy trước khi ứng dụng sẵn sàng.
- Rolling update có thể tạm thời không đủ replica healthy nếu cấu hình surge/unavailable, HPA hoặc PodDisruptionBudget chưa phù hợp.

### 13.4. Service type LoadBalancer

GKE `Service(type=LoadBalancer)` thường dùng passthrough Network LB; health check có thể trỏ `nodePort` và chịu ảnh hưởng `externalTrafficPolicy`.

Với `externalTrafficPolicy: Local`, node không có Pod Ready cục bộ **có thể cố ý bị xem là unhealthy**. Đừng sửa bằng cách ép mọi node nhận traffic khi thiếu Pod; hãy kiểm tra placement, replica, readiness, DaemonSet, service selector và chính sách locality.

## 14. Cloud Run backend và serverless NEG: ngoại lệ quan trọng

Nếu external Application Load Balancer dùng **serverless NEG** tới Cloud Run, backend này **không dùng load balancer health-check resource giống instance group/zonal NEG**. Không đi tìm firewall probe đến Cloud Run để sửa `unhealthy`.

Khi Cloud Run sau LB trả 4xx/5xx:

- Xác minh serverless NEG tham chiếu đúng service, region và project.
- Xác minh Cloud Run revision đã deploy/ready, ingress và authentication.
- Xem Cloud Run request logs, instance startup, memory/CPU, concurrency và max instances.
- Kiểm tra Cloud Run lắng nghe `PORT`, bind `0.0.0.0`, có thể hoàn thành startup.
- Kiểm tra service-to-service IAM và việc frontend có thể gọi backend trong cấu hình đã triển khai.
- Đối chiếu URL map host/path rule, serverless NEG và default backend.

Cloud Run có startup/liveness probes và các cơ chế nhận biết readiness ở tầng platform. Chúng **không** đồng nghĩa có một `gcloud compute health-checks` gắn vào serverless NEG. Đây là lỗi khái niệm thường làm đội vận hành tốn thời gian.

## 15. URL map, routing và lỗi 404/502/503

Nếu DNS đúng và TLS thành công nhưng HTTP trả lỗi, kiểm tra đường routing:

~~~bash
gcloud compute forwarding-rules describe FORWARDING_RULE --global
gcloud compute target-https-proxies describe PROXY_NAME --global
gcloud compute url-maps describe URL_MAP_NAME --global
gcloud compute backend-services describe BACKEND_SERVICE --global
~~~

Thay scope bằng regional nếu LB regional. Với external passthrough Network LB, không có URL map như ví dụ này.

### 15.1. Host/path mismatch

Giả sử URL map có:

- `api.example.com/v1/*` → `api-v1-backend`.
- `api.example.com/v2/*` → `api-v2-backend`.
- Default service → static frontend.

Nếu client gửi `www.example.com/v2/orders`, hostname có thể không khớp host rule nên request đi default backend, dù TLS vẫn thành công. Phải kiểm tra **Host header** và path thực, không chỉ tên backend được kỳ vọng.

### 15.2. 502 và 503 không cùng một nguyên nhân

- **502:** thường liên quan LB không lấy được response hợp lệ từ backend, kết nối backend bị đóng/timeout/protocol mismatch.
- **503:** có thể liên quan không chọn được backend healthy, capacity/connection issue, hoặc chính ứng dụng trả 503.
- **404:** có thể do URL map không match hoặc app không có route.

Đừng suy nguyên nhân chỉ từ mã HTTP. Trong Cloud Load Balancing request logs, đọc `jsonPayload.statusDetails` (nếu có) để phân biệt lỗi do backend trả với lỗi do LB xử lý, cùng `httpRequest.status`, latency và backend/forwarding rule context.

Ví dụ truy vấn Logs Explorer với LB global external:

~~~text
resource.type="http_load_balancer"
httpRequest.status>=500
~~~

Loại monitored resource của regional Application LB có thể khác (ví dụ regional external LB). Phải chọn đúng resource type từ log hiện có; bật request logging/sampling phù hợp để đủ bằng chứng mà không vượt ngân sách.

### 15.3. Backend timeout và draining

Khi request dài/streaming:

- Backend service timeout có thể không phù hợp request processing time.
- Client có timeout ngắn hơn LB hoặc ngược lại.
- Keepalive giữa proxy và backend có thể không khớp.
- Drain/rolling deployment có thể đóng connection đang phục vụ.
- GKE rolling update hoặc MIG recreate có thể tạm giảm healthy endpoints.

Khắc phục dựa trên latency distribution, request semantics và SLO; không đơn giản tăng mọi timeout lên vô hạn.

## 16. Bảo mật TLS khi sửa lỗi

### 16.1. Không dùng các “cách sửa nhanh” gây rủi ro

- Không dùng `curl -k` để tuyên bố kết nối đã an toàn.
- Không tắt certificate validation trong Java HTTP client production.
- Không upload private key vào chat, ticket hoặc repository.
- Không hạ SSL policy xuống TLS 1.0/1.1 chỉ vì client cũ.
- Không mở firewall port app cho `0.0.0.0/0` khi chỉ cần probe/proxy subnet được phép.
- Không xóa CAA/DNSSEC bảo vệ domain khi chưa hiểu nguyên nhân.
- Không thay nhiều DNS/proxy/cert resources cùng lúc khi đang incident.

### 16.2. Bảo vệ mTLS/identity

Nếu backend hoặc frontend yêu cầu mutual TLS:

- Kiểm tra đúng nơi terminate TLS.
- Xác nhận trust store/client CA và danh tính workload.
- Phân biệt cert dùng cho người dùng tới LB với cert dùng cho LB tới backend.
- Giữ audit logs của thay đổi cert map, SSL policy, forwarding rules và firewall.

Thay chứng chỉ nên có quy trình **issue → attach → verify from client → observe → detach old**, cân nhắc thời gian propagation. Không nhầm “resource tồn tại” với “đang được phục vụ”.

## 17. Bộ lệnh chẩn đoán end-to-end

Đây là checklist command mang tính **read-only** cho trường hợp external HTTPS Application LB global với instance group backend. Hãy thay placeholder và scope khi áp dụng; không phải mọi command hợp lệ với mọi LB.

~~~bash
# 1) DNS và chứng chỉ ở phía client.
dig api.example.com A +short
dig api.example.com AAAA +short
dig api.example.com CAA
curl -vI https://api.example.com/
echo | openssl s_client -connect LB_IP:443 -servername api.example.com

# 2) Frontend, TLS proxy và URL map.
gcloud compute forwarding-rules list --global
gcloud compute target-https-proxies describe PROXY_NAME --global
gcloud compute url-maps describe URL_MAP_NAME --global

# 3) Certificate resource (chọn đúng một hoặc cả hai nếu hệ thống dùng).
gcloud compute ssl-certificates describe CERT_NAME --global
gcloud certificate-manager certificates describe CERT_NAME --location=global
gcloud certificate-manager maps entries list --map=MAP_NAME

# 4) Backend và health check.
gcloud compute backend-services describe BACKEND_SERVICE --global
gcloud compute backend-services get-health BACKEND_SERVICE --global
gcloud compute health-checks describe HEALTH_CHECK --global

# 5) Compare with direct-IP test preserving Host/SNI.
curl -v --resolve api.example.com:443:LB_IP https://api.example.com/
~~~

Kết quả nên lưu vào incident ticket với timestamp UTC và phân quyền thích hợp. Đừng copy nguyên command từ tài liệu rồi chạy ở project mặc định không mong muốn: đặt `--project` khi cần và xác nhận scope.

## 18. Runbook: HTTPS domain ngừng hoạt động sau đổi DNS/chứng chỉ

**Tình huống:** `api.example.com` dùng global external Application LB, Certificate Manager Google-managed certificate và GKE NEG. Trong lúc đổi DNS provider, một số người dùng thấy chứng chỉ cũ, số khác gặp DNS lỗi.

### Bước 1: xác nhận tác động

- Ghi client networks/vị trí, tần suất lỗi, SLO và thời điểm bắt đầu.
- Phân biệt NXDOMAIN, TLS error và HTTP 5xx.
- Kiểm tra user-facing endpoint bằng IPv4 và IPv6.

### Bước 2: DNS

- Xem NS tại registrar và `dig +trace`.
- So sánh A/AAAA ở authoritative với forwarding rule VIP.
- Kiểm tra DS/DNSKEY nếu DNSSEC bật.
- Đối chiếu TTL, negative caching và thời điểm thay zone.
- Nếu có GeoDNS/CDN, xác minh tất cả public responses phù hợp certificate authorization.

### Bước 3: certificate

- Mở Certificate Manager, xem `managed.state` và authorization attempt.
- Kiểm tra CNAME DNS authorization/CAA nếu dùng.
- Kiểm tra certificate map entry của đúng hostname và target proxy.
- Dùng `openssl -servername` tới VIP mới/cũ để xem cert leaf/SAN/expiry.
- Không xóa cert cũ khi chưa chứng minh cert mới được phục vụ.

### Bước 4: backend

- Nếu TLS đã đúng mà API vẫn 503, xem URL map/backend service, `get-health` và GKE Pod/NEG.
- Tách khả năng health probe bị chặn firewall khỏi lỗi app readiness.
- Theo dõi Cloud Load Balancing và GKE request logs sau thay đổi.

### Bước 5: mitigation

- Nếu chỉ DNS sai và VIP cũ còn phục vụ an toàn, xem rollback delegation/record theo runbook và TTL đã biết.
- Nếu cert mới chưa ACTIVE, giữ frontend/cert cũ đang còn hợp lệ trong thời gian cho phép.
- Nếu backend unhealthy sau rollout, rollback revision/Deployment khi có đủ evidence và điều kiện dữ liệu.
- Không rollback DNS vào hệ thống đã bị decommission hoặc chứa dữ liệu cũ không được đồng bộ.

### Bước 6: kiểm chứng hoàn tất

1. DNS authoritative và public resolver trả IP mong đợi; cả A và AAAA đúng.
2. TLS verify thành công, SAN/chain/expiry đúng, không dùng `-k`.
3. URL map chọn đúng backend.
4. Backend health đạt ngưỡng; không còn 502/503 tăng.
5. p95/p99, error budget và chỉ số nghiệp vụ trở lại mức chấp nhận.
6. Theo dõi một khoảng soak period, ghi lại thời gian lan truyền và action items.

## 19. Thực hành Java/Spring Boot: health endpoint đúng nghĩa

### 19.1. Cấu hình Actuator

Với Spring Boot đã bật Spring Boot Actuator dependency:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
~~~

Ví dụ truy cập từ môi trường có quyền:

~~~bash
curl -is http://127.0.0.1:8080/actuator/health/readiness
curl -is http://127.0.0.1:8080/actuator/health/liveness
~~~

Nếu workload có Spring Security, cần cấu hình matcher và quyền truy cập health endpoint tương thích health checker; không mở toàn bộ Actuator endpoints ra Internet. Nếu dùng Cloud Run, cần phân biệt startup/liveness probes của Cloud Run với health check của Application LB có serverless NEG (không hỗ trợ loại này).

### 19.2. Dependency health: khi nào nên báo DOWN?

Một readiness group có thể cần kiểm tra khả năng kết nối database nếu hầu hết request đều bắt buộc dùng database. Tuy nhiên:

- Nếu Cloud SQL gặp outage toàn vùng, cho tất cả instance `Unhealthy` không tự làm hệ thống có database khả dụng.
- Với chức năng read-only/cache vẫn dùng được, có thể trả degraded behavior thay vì loại tất cả backends.
- Liveness không nên buộc vào trạng thái database bên ngoài, tránh restart storm.
- Không trả 200 vô điều kiện khi ứng dụng đã không nhận request.

Sự cân bằng phải được quyết định theo hợp đồng readiness, SLO, circuit breaker và chính sách failover cụ thể.

### 19.3. Ví dụ lỗi sau rollout

Spring Boot mới chuyển route readiness từ `/health` sang `/actuator/health/readiness`. GKE backend service vẫn kiểm tra `/health`, khiến tất cả Pod mới bị xem Unhealthy. Quy trình sửa đúng:

1. Đọc health-check config đang dùng trên LB.
2. Xác minh `/health` trả 404 và path mới trả 200 trên Pod IP.
3. Chọn sửa BackendConfig/health check hoặc duy trì alias path theo change control.
4. Rollout lần lượt, đợi health chuyển Healthy trước khi giảm replica cũ.
5. Xem LB logs, p99 và error budget.

Không restart toàn cluster khi chỉ có route health check đã đổi.

## 20. Cloud Monitoring, Logging và cảnh báo

### 20.1. Những chỉ số nên có

| Đối tượng | Metric/biến quan sát | Ý nghĩa |
|---|---|---|
| Public endpoint | DNS resolution success, TLS expiry, HTTP success | Đo end-to-end từ client/synthetic |
| Load balancer | Request rate, 4xx/5xx, backend latency | Triệu chứng từ frontend |
| Backend service | Healthy/unhealthy backend count, utilization | Capacity thực được chọn |
| Health check | Probe successes/failures, state transitions | Sai firewall, path, port hoặc app |
| Certificate | Expiration, managed status, authorization failure | Nguy cơ outage khi rotate/renew |
| GKE/MIG | Pod/instance readiness, CPU, OOM/restarts | Health application |
| Cloud Run | Request errors, instance count, startup failures | Serverless backend health |
| DNS | DNS error rate, authoritative/recursive probes | NXDOMAIN/SERVFAIL, sai delegation |

Không phải mọi chỉ số có sẵn cùng tên/scope trên mọi LB/backend. Tạo dashboard sau khi kiểm tra monitored resource và metric thực trong **Metrics Explorer**, không viết alert trên một metric mà loại LB đó không phát hành.

### 20.2. Logs Explorer

Ví dụ lọc request 5xx trên global external Application LB:

~~~text
resource.type="http_load_balancer"
httpRequest.status>=500
~~~

Phân tích `jsonPayload.statusDetails`, backend name, latency và request ID. Với GKE/GCE/Cloud Run, mở logs tương ứng để xác định backend có nhận request hay không. Trong nhiều cấu hình, logging/sampling của LB phải được bật trước; thiếu log không đồng nghĩa không có request.

### 20.3. Synthetic probes và SLO

Tạo probe bên ngoài hạ tầng LB để đo:

- DNS resolve (A/AAAA, DNSSEC khi phù hợp).
- TLS certificate SAN/chain/expiry bằng hostname thật.
- GET một endpoint HTTP 200 ổn định.
- Business transaction tối thiểu nếu cần.

Synthetic probe nên chạy từ nhiều vị trí/mạng khi có yêu cầu availability toàn cầu. Đừng chỉ dựa vào internal health check vì nó không kiểm tra DNS và frontend certificate.

### 20.4. Alert noise

Page khi có tác động thực tới người dùng hoặc hết healthy capacity; ticket/notify cho cert sắp hết hạn, certificate renewal lỗi, DNS drift. Khi gửi alert, bao gồm domain, LB type, project, frontend VIP, backend service, region, runbook URL và owner.

## 21. Kịch bản phân tích và bài tập

### Tình huống A: Certificate `PROVISIONING` quá lâu

Một domain vừa chuyển từ registrar cũ sang Cloud DNS, Certificate Manager cert vẫn PROVISIONING. Trình bày:

1. Kiểm tra NS/DS/SOA, authoritative DNS và public resolver.
2. Kiểm tra DNS authorization CNAME thật từ `dnsResourceRecord`.
3. Kiểm tra CAA và failure reason; nếu per-project auth, CA cho phép là `pki.goog`.
4. Kiểm tra `managed.state`, authorization attempts và expiry của cert cũ.
5. Lập kế hoạch attach new/verify/detach old; không xóa cert đang phục vụ.

### Tình huống B: DNS IPv4 tốt, IPv6 lỗi chứng chỉ

`curl -4` thành công, `curl -6` trả certificate khác. Dùng `dig AAAA`, forward-rule IPv6 inventory, `openssl -servername` tới từng VIP và so sánh cert map attachments. Đề xuất cách sửa AAAA hoặc frontend IPv6, kèm kế hoạch rollback và TTL.

### Tình huống C: GKE rollout khiến backend 0/X Healthy

Ứng dụng đổi Spring Actuator path. Ingress/BackendConfig vẫn probe path cũ. Xác định:

- Lệnh đọc backend health và health-check config.
- Cách chứng minh Pod mới trả 200 tại path mới.
- Cách rollout có bảo vệ availability.
- Vì sao readinessProbe đổi không tự đảm bảo LB health check đổi.

### Tình huống D: LB healthy nhưng user nhận 503

Regional external Application LB dùng VM backend. Health check từ dải Google đã pass nhưng firewall không cho traffic từ proxy-only subnet. Phân tích hai đường riêng (probe và actual traffic), firewall policy và `statusDetails`; không nới firewall toàn Internet.

### Tình huống E: Cloud Run qua serverless NEG

Backend không có health check resource nhưng API 503 khi traffic tăng. Kiểm tra Cloud Run revision, startup, max instances, concurrency, database pool, ingress/auth và logs; giải thích vì sao không tạo `gcloud compute health-checks` cho serverless NEG.

## 22. Checklist production trước khi thay DNS/chứng chỉ/LB

### Trước thay đổi

- [ ] Xác định LB type, scope (global/regional) và backend type.
- [ ] Ghi lại forwarding rule IP, target proxy, certificate/map, URL map, backend service.
- [ ] Có danh sách hostname/SAN, A/AAAA/CNAME/CAA và authoritative NS.
- [ ] DNSSEC/delegation được kiểm tra; TTL được giảm trước cutover nếu cần.
- [ ] Chứng chỉ mới ACTIVE và được attach đúng, cert cũ vẫn sẵn sàng rollback.
- [ ] Health check phù hợp app: port/path/Host/HTTP status/threshold.
- [ ] Firewall/NetworkPolicy cho đúng probe CIDRs và proxy-only subnet nếu áp dụng.
- [ ] Có kiểm thử frontend TLS, DNS, backend health và synthetic request.
- [ ] Có change owner, time window, rollback, incident contact và SLO guardrails.

### Trong thay đổi

- [ ] Ghi timestamp và diff config.
- [ ] Thay một nhóm cấu hình mỗi lần, quan sát propagation.
- [ ] Xác minh `curl --resolve` đúng SNI và TLS verify không dùng `-k`.
- [ ] Kiểm tra DNS resolver/IPv6, URL map và backend `get-health`.
- [ ] Theo dõi LB error rates, health-check logs và backend logs.
- [ ] Không bỏ qua lỗi hệ thống chỉ vì health check báo Healthy.
- [ ] Không mở firewall/giảm TLS security vô điều kiện.

### Sau thay đổi

- [ ] Tên miền trả đúng IP từ authoritative và nhiều resolver.
- [ ] TLS chain, issuer, SAN, expiry và SNI đúng.
- [ ] Ứng dụng đạt HTTP success/business SLO.
- [ ] Backend đủ healthy capacity qua rollout và failover.
- [ ] Certificate renewal/DNS authorization không còn lỗi.
- [ ] Có alert hết hạn cert, DNS drift, unavailable backend và 5xx.
- [ ] Đã cập nhật runbook, asset inventory và postmortem/action items.
- [ ] Cleanup chứng chỉ/forwarding rules cũ **sau** khi xác nhận không còn tham chiếu.

## 23. Tài liệu tham khảo chính thức

- [Cloud Load Balancing overview](https://cloud.google.com/load-balancing/docs/load-balancing-overview)
- [Health checks overview và probe source ranges](https://cloud.google.com/load-balancing/docs/health-check-concepts)
- [Tạo và sử dụng health checks](https://cloud.google.com/load-balancing/docs/health-checks)
- [Troubleshooting Application Load Balancers](https://cloud.google.com/load-balancing/docs/https/troubleshooting)
- [Load balancing logging và statusDetails](https://cloud.google.com/load-balancing/docs/https/https-logging-monitoring)
- [Google-managed Compute Engine SSL certificates](https://cloud.google.com/load-balancing/docs/ssl-certificates/google-managed-certs)
- [Troubleshoot SSL certificates](https://cloud.google.com/load-balancing/docs/ssl-certificates/troubleshooting)
- [Certificate Manager troubleshooting](https://cloud.google.com/certificate-manager/docs/troubleshooting)
- [Certificate Manager global DNS authorization](https://cloud.google.com/certificate-manager/docs/deploy-google-managed-dns-auth)
- [Certificate Manager regional managed certificates](https://cloud.google.com/certificate-manager/docs/deploy-google-managed-regional)
- [Manage Certificate Manager certificate maps](https://cloud.google.com/certificate-manager/docs/map-entries)
- [Cloud DNS troubleshooting](https://cloud.google.com/dns/docs/troubleshooting)
- [Cloud DNS DNSSEC overview](https://cloud.google.com/dns/docs/dnssec)
- [GKE Ingress health checks](https://cloud.google.com/kubernetes-engine/docs/troubleshooting/ingress-health-checks)
- [GKE Service type LoadBalancer](https://cloud.google.com/kubernetes-engine/docs/concepts/service-load-balancer)
- [GKE BackendConfig CRD](https://cloud.google.com/kubernetes-engine/docs/how-to/ingress-configuration)
- [Cloud Run with external Application Load Balancer](https://cloud.google.com/load-balancing/docs/https/setting-up-https-serverless)
- [Cloud Monitoring documentation](https://cloud.google.com/monitoring/docs)
- [Cloud Logging documentation](https://cloud.google.com/logging/docs)
- [Spring Boot Actuator health endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)

## 24. Tổng kết

Để xử lý lỗi chứng chỉ, DNS và load balancer health check trên GCP, hãy **đi từ ngoài vào trong**: xác minh DNS và địa chỉ frontend; kiểm tra TLS/SNI/certificate resource cùng attachment; xác nhận URL map và backend service; đọc health-check configuration và trạng thái backend; cuối cùng kiểm tra port, firewall, Pod/instance và ứng dụng. Đồng thời phải hiểu ngoại lệ giữa global/regional Application LB, proxy/passthrough Network LB, GKE Ingress và Cloud Run serverless NEG.

Giải pháp tốt là thay đổi **đúng tầng có bằng chứng lỗi**, không làm suy yếu bảo mật hoặc availability, và xác minh lại từ góc nhìn khách hàng bằng DNS, TLS và synthetic HTTP checks. Khi kết hợp một runbook có rollback, Cloud Logging/Monitoring, certificate rotation an toàn và kiểm thử rollout, đội vận hành sẽ giảm được cả thời gian phát hiện lẫn nguy cơ tái diễn sự cố.
