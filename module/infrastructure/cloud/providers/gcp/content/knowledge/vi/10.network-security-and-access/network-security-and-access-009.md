# Secure Web Proxy và kiểm soát truy cập web đi ra

Một ứng dụng Java chạy trên Compute Engine cần tải thư viện từ Internet; một pipeline CI/CD phải kết nối với kho mã nguồn; một nhóm phân tích dữ liệu gọi API đối tác. Nếu mọi workload đều có thể gửi yêu cầu HTTP/HTTPS tới bất kỳ website nào, tổ chức khó phát hiện mã độc liên lạc ra ngoài, hạn chế thất thoát dữ liệu và xác định dịch vụ nào đang gọi endpoint không được phép.

**Secure Web Proxy (SWP)** là dịch vụ proxy web do Google Cloud quản lý, giúp tập trung kiểm soát **lưu lượng HTTP/HTTPS đi ra (egress)**. Thay vì chỉ dựa vào firewall theo IP, người quản trị có thể áp chính sách cho nguồn truy cập, đích đến và thuộc tính request theo khả năng của chế độ triển khai. SWP tiếp nhận yêu cầu, đánh giá policy, mở kết nối mới tới đích khi được phép và ghi log phục vụ điều tra.

Bài thuộc chương **Bảo mật và truy cập mạng** của học phần **CLOUD_PROVIDERS_GCP**. Kiến thức này liên quan đến thiết kế project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, tự động hóa phát hành và theo dõi độ tin cậy, chi phí. Mục tiêu là biết lúc nào chọn SWP, cấu hình ra sao và làm thế nào bảo đảm workload không có đường mạng khác vượt qua lớp kiểm soát.

Sau bài học, bạn có thể:

- Giải thích hướng lưu lượng đi ra và vị trí của Secure Web Proxy.
- Phân biệt **explicit proxy**, **next-hop routing** và **Private Service Connect**.
- Thiết kế gateway security policy có danh tính nguồn, điều kiện đích và **mặc định từ chối**.
- Hiểu giới hạn quan sát HTTPS và mục đích của **TLS inspection**.
- Tạo policy, rule, gateway mẫu qua Google Cloud Console hoặc `gcloud`.
- Kiểm tra proxy bằng `curl`, đọc Cloud Logging và chống bypass.
- Ước lượng chi phí, quản lý thay đổi và xử lý lỗi thường gặp.

## 1. Secure Web Proxy nằm ở đâu trong luồng mạng?

Trong mô hình **explicit proxy**, ứng dụng được cấu hình gửi request qua địa chỉ proxy. Proxy nhận kết nối, kiểm tra policy và chủ động mở kết nối mới tới website hoặc API bên ngoài nếu request được cho phép.

~~~mermaid
flowchart LR
    A["Compute Engine / workload trong VPC"] --> B["Secure Web Proxy theo region"]
    B --> C{"Security policy"}
    C -- "ALLOW" --> D["Egress Internet qua mạng được quản lý"]
    D --> E["Website / API bên ngoài"]
    C -- "DENY" --> F["Từ chối + transaction log"]
    B --> G["Cloud Logging / Monitoring"]
~~~

Ví dụ một ứng dụng gửi request tới `https://api.vendor.example`. Nếu chính sách cho phép nguồn và đích trong phạm vi thuộc tính quan sát được, proxy mới chuyển tiếp. Nếu bị chặn, request không tới API đích. SWP thực thi chính sách trên **lưu lượng thực sự đi qua proxy**.

| Thành phần | Nhiệm vụ | Giới hạn |
|---|---|---|
| **VPC, routes, firewall** | Kiểm soát đường đi và kết nối ở mức mạng | Không tự phân tích đường dẫn URL của HTTP |
| **Cloud NAT** | Cấp đường Internet cho IP private thông qua NAT | Không phải bộ lọc domain/HTTP theo workload identity |
| **Secure Web Proxy** | Kiểm tra HTTP/HTTPS egress theo policy | Không quản lý mọi giao thức hoặc đường bypass |
| **Cloud DNS** | Phân giải tên miền | Không tự ngăn HTTP request tới một domain |
| **Cloud Armor** | Chủ yếu bảo vệ lưu lượng **đi vào** ứng dụng qua load balancer được hỗ trợ | Không thay SWP cho egress |
| **IAM và service account** | Xác định danh tính và quyền Google Cloud API | Không mặc nhiên giới hạn website bất kỳ trên Internet |
| **VPC Service Controls** | Hạn chế truy cập/truyền dữ liệu của các Google Cloud service được hỗ trợ | Không thay proxy lọc web bên ngoài |

Cloud Armor thường chặn lưu lượng của khách hàng **vào** API, trong khi SWP quản lý request từ API **ra** Internet. Hai lớp có thể được sử dụng cùng nhau.

## 2. Khi nào cần SWP?

| Yêu cầu | SWP hỗ trợ | Thành phần bổ sung |
|---|---|---|
| Backend chỉ được gọi API đối tác đã duyệt | Allowlist đích và nguồn | Service account, DNS và mạng |
| Ghi nhận domain/web mà VM truy cập | Transaction logs | Logging, quyền xem log |
| Chặn kết nối tới domain không phê duyệt | Default deny và các rule rõ ràng | Firewall/routes chặn egress trực tiếp |
| Phân biệt nhóm workload | Match theo service account hoặc secure tag khi được hỗ trợ | Quản lý IAM và tags |
| Kiểm tra path/header bên trong HTTPS | TLS inspection | Certificate Authority Service và trust store |
| Tái sử dụng proxy qua nhiều VPC | Private Service Connect hoặc mode được hỗ trợ | Thiết kế host project/PSC |
| Giới hạn số request ra Internet | Service rate limiting policy theo tính năng hỗ trợ | Quota và cơ chế giới hạn trong ứng dụng |

SWP tập trung vào **web egress HTTP/HTTPS**. Nó không phải VPN/Interconnect, không thay load balancer public cho khách hàng bên ngoài và không xử lý tùy ý mọi giao thức TCP/UDP.

## 3. Ba chế độ đưa lưu lượng đến proxy

### 3.1. Explicit proxy

Ứng dụng hoặc hệ điều hành đặt địa chỉ proxy: ví dụ tham số `--proxy` trong `curl`, biến môi trường `HTTP_PROXY`/`HTTPS_PROXY`, hoặc proxy settings của JVM.

~~~text
Application → IP:port SWP trong VPC → Policy → Internet
~~~

Mô hình này dễ kiểm thử theo từng client, nhưng chương trình không đọc proxy settings có thể đi vòng nếu mạng vẫn cho phép kết nối trực tiếp.

### 3.2. Next-hop mode

Với **next-hop**, các route có thể đưa lưu lượng từ workload đến gateway theo tính năng được hỗ trợ, giảm nhu cầu chỉnh sửa từng ứng dụng. Khi thiết kế cần xét loại route, điểm đến và lưu lượng nội bộ để tránh làm gián đoạn kết nối trong VPC. Một gateway explicit không trở thành next-hop chỉ bằng việc đổi địa chỉ proxy trong ứng dụng.

### 3.3. Private Service Connect (PSC)

SWP có thể được công bố qua **Private Service Connect** để các VPC khác kết nối đến proxy trung tâm. PSC tạo đường truy cập private giữa các mạng được phép, nhưng không tự cấp quyền truy cập mọi website; policy SWP vẫn quyết định request có được chuyển tiếp hay không.

| Chế độ | Nguồn gửi request | Phù hợp với | Cần kiểm tra |
|---|---|---|---|
| Explicit | Ứng dụng đặt địa chỉ proxy | VM và workload có thể thay cấu hình | Proxy settings, firewall, no-proxy |
| Next-hop | Route gửi traffic tới gateway | Nhiều nguồn khó cấu hình client | Route priority, đường nội bộ, giới hạn |
| PSC | Consumer VPC sử dụng endpoint private | Nhiều VPC, mạng tập trung | Endpoint/service attachment, DNS, IAM |

SWP có phạm vi **region**. Chọn region dựa trên nơi chạy workload, nhu cầu nối mạng, độ trễ và tính sẵn sàng. Tài liệu hiện hành còn nêu gateway trong **Shared VPC** phải triển khai ở **host project**, không phải service project; cần phối hợp với đội quản trị mạng.

## 4. Kiến trúc tài nguyên: gateway, policy và mạng

~~~text
Project: platform-egress
├── VPC: prod-network
│   ├── PRIVATE subnet: egress-subnet (region A)
│   └── Proxy-only subnet: REGIONAL_MANAGED_PROXY (region A)
├── Gateway security policy: outbound-policy
│   ├── Rule 10: cho phép nguồn và đích được duyệt
│   ├── Rule 20: cho phép kho dependency cần thiết
│   └── Default: DENY
├── Secure Web Proxy gateway: outbound-proxy
│   ├── IP nội bộ và frontend ports
│   └── Liên kết outbound-policy
└── Managed Cloud NAT / Cloud Logging
~~~

| Tài nguyên | Vai trò | Dễ cấu hình sai ở đâu? |
|---|---|---|
| **Gateway** | Nhận request tại IP/port và thực thi policy | Client không dùng IP đó hoặc gateway chưa sẵn sàng |
| **Gateway security policy** | Chứa các rule web egress thông thường | Không gắn vào gateway hoặc có authorization policy khác |
| **Rule** | Priority, `basicProfile`, `sessionMatcher` và tùy chọn `applicationMatcher` | Match HTTPS như HTTP |
| **PRIVATE subnet** | Subnet tham chiếu khi tạo gateway | Chọn nhầm proxy-only subnet |
| **Proxy-only subnet** | `REGIONAL_MANAGED_PROXY` cấp địa chỉ cho Envoy proxy pool | Chưa tạo hoặc CIDR chồng lấn |
| **Cloud NAT** | Định danh IP công khai cho traffic proxy đi Internet | Nhầm IP VM với public egress IP |
| **Certificate Manager** | Cấp certificate frontend khi client kết nối proxy qua TLS | Nhầm với CA để giải mã HTTPS tới website |
| **Certificate Authority Service** | Tạo CA phục vụ TLS inspection | Client chưa tin CA hoặc ứng dụng certificate pinning |

Khi triển khai SWP, cần có **subnet thường và proxy-only subnet** tại region phù hợp. Proxy-only subnet không được dùng làm giá trị `gateway.subnetwork`. SWP có thể tự tạo **Cloud NAT** và cấp IP egress động; nếu đối tác cần allowlist public IP cố định, phải theo quy trình cấu hình Cloud NAT nâng cao tương ứng.

## 5. Chính sách: deny by default và rule priority

Với **gateway security policy** cho web traffic thông thường:

- `priority`: số nhỏ được đánh giá trước.
- `enabled`: bật/tắt rule.
- `basicProfile`: `ALLOW` hoặc `DENY`.
- `sessionMatcher`: điều kiện session, nguồn và đích theo khả năng mode.
- `applicationMatcher`: điều kiện HTTP chi tiết khi loại lưu lượng và TLS inspection cho phép.
- `tlsInspectionEnabled`: bật giải mã HTTPS cho rule phù hợp khi đã có cấu hình CA/policy.

**Mặc định từ chối** là phương án khởi điểm an toàn: request không khớp rule cho phép sẽ không đi tới website đích.

| Priority | Workload | Đích được duyệt | Quyết định |
|---:|---|---|---|
| 10 | Pipeline build | Registry, mã nguồn và dependency theo danh sách | Allow |
| 20 | Dịch vụ thanh toán | API đối tác thanh toán | Allow |
| 30 | Ứng dụng báo cáo | Endpoint nhận dữ liệu theo hợp đồng | Allow |
| Default | Mọi nguồn/đích khác | Chưa được phê duyệt | Deny |

Đây là **yêu cầu logic**, chưa phải rule có thể áp dụng trực tiếp. Cần ánh xạ danh tính, domain, loại traffic và khả năng match của mode tương ứng.

### Gateway security policy, authorization policy và rate limiting

SWP còn hỗ trợ **authorization policy** để kiểm tra danh tính, frontend mutual TLS hoặc tích hợp extension authorization. Với web traffic tiêu chuẩn, **authorization policy và gateway security policy là hai mô hình chính loại trừ nhau trên cùng gateway**: nếu gắn authorization policy, các gateway security rules hiện có bị bỏ qua. Có thể dùng thêm service rate limiting policy khi tính năng hỗ trợ.

Với lưu lượng từ **AI agent/Agent Gateway**, Google Cloud có hệ thống authorization và extension riêng; phạm vi bài này là traffic web thông thường.

## 6. HTTPS và giới hạn quan sát

Request HTTPS mã hóa nội dung HTTP, bao gồm URL path và header. Proxy không thể tự đọc phần đó chỉ bằng IP/port; khả năng match còn phụ thuộc explicit hoặc next-hop.

| Lưu lượng | Proxy có thể xét gì? | Lưu ý |
|---|---|---|
| HTTP không TLS | Host và các thuộc tính HTTP theo mode | Rule host có thể dùng để minh họa |
| HTTPS không TLS inspection | Thông tin session/nguồn và một số thuộc tính TLS nhìn thấy được theo mode | Không mặc nhiên đọc được URL path/header |
| HTTPS có TLS inspection | Nội dung HTTP đã được giải mã trong phạm vi phù hợp | `sessionMatcher` và `applicationMatcher` cùng CA/trust |

**Giới hạn quan trọng của explicit proxy:** theo tài liệu SWP hiện hành, với **HTTPS không TLS inspection**, hostname matching ở cấp session/application có giới hạn. Không lấy điều kiện `host() == 'partner.example'` dùng cho HTTP rồi khẳng định nó luôn lọc đúng HTTPS trong explicit mode. Với **next-hop**, SWP có thể đánh giá SNI của TLS theo mode được hỗ trợ, nhưng SNI không chứa URL path.

### TLS inspection hoạt động như thế nào?

~~~text
Client -- TLS phiên 1 --> Secure Web Proxy
              Giải mã, kiểm tra policy trên HTTP
Proxy  -- TLS phiên 2 --> Server/API đích
~~~

Proxy đóng vai trò trung gian tin cậy, sử dụng **Certificate Authority Service** để cấp certificate tạm thời theo domain được truy cập. Client phải tin chuỗi CA đó. Để dùng `applicationMatcher` với HTTPS, cần tạo `tlsInspectionPolicy`, CA pool, quyền service agent, liên kết policy và bật `tlsInspectionEnabled` cho rule phù hợp.

Những ràng buộc cần cân nhắc:

1. Client chưa trust root CA thì handshake HTTPS sẽ lỗi.
2. Ứng dụng dùng **certificate pinning** hoặc mutual TLS có thể không tương thích; cần ngoại lệ được review.
3. Dữ liệu nhạy cảm trong request chỉ được kiểm tra/ghi nhận theo chính sách quyền riêng tư.
4. Không nên giải mã toàn bộ website ngoài Internet khi chỉ cần phân tích một số API đích.
5. **Frontend certificate** để client kết nối HTTPS tới proxy khác với **CA của TLS inspection** dùng cho website đích.

## 7. Chuẩn bị VPC, API và quyền

Trước khi tạo **explicit proxy** cho buổi thực hành, cần có project thử nghiệm đã bật billing, VM Linux hoặc workload có thể kết nối proxy, VPC và subnet phù hợp, quyền cấu hình mạng/security policy, cũng như một website thử nghiệm để kiểm tra.

Các API thiết yếu thường gồm **Compute Engine, Network Services, Network Security**; **Certificate Manager** cho frontend certificate, **CA Service** cho TLS inspection nếu sử dụng. Vai trò như `roles/compute.networkAdmin` có thể cần cho quản trị; cấp thêm quyền certificate/CA đúng phạm vi khi cần.

### Tạo hai subnet trong một VPC thử nghiệm

~~~bash
PROJECT_ID="my-egress-project"
REGION="us-central1"
VPC="egress-lab-vpc"
FRONTEND_SUBNET="swp-frontend"
PROXY_SUBNET="swp-proxy-only"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  compute.googleapis.com \
  networkservices.googleapis.com \
  networksecurity.googleapis.com \
  certificatemanager.googleapis.com

gcloud compute networks create "$VPC" --subnet-mode=custom

# Subnet thường: gateway tham chiếu trực tiếp subnet này.
gcloud compute networks subnets create "$FRONTEND_SUBNET" \
  --network="$VPC" --region="$REGION" \
  --range="10.60.0.0/24" --purpose=PRIVATE

# Proxy-only subnet: dùng bởi Envoy proxy pool.
gcloud compute networks subnets create "$PROXY_SUBNET" \
  --network="$VPC" --region="$REGION" \
  --range="10.61.0.0/23" \
  --purpose=REGIONAL_MANAGED_PROXY --role=ACTIVE
~~~

Các lệnh trên **chỉ minh họa**; không chạy nguyên xi trong production. Phải chọn CIDR không chồng lấn, giới hạn quyền và biết rằng tài nguyên có thể phát sinh chi phí. Với Shared VPC, sử dụng host project/VPC đã được nhóm platform cấp thay vì tạo mạng khác để né quy định.

## 8. Tạo policy, rule và gateway bằng gcloud

Ví dụ sử dụng các file YAML như **mẫu nội dung học tập**. Thay `PROJECT_ID`, `REGION` và IP bằng dữ liệu thực. Ở đây chỉ cấu hình rule kiểm tra **HTTP không mã hóa**; ví dụ không đại diện cho bộ lọc HTTPS production.

### Bước 1. Tạo gateway security policy

~~~yaml
# policy.yaml
name: projects/PROJECT_ID/locations/REGION/gatewaySecurityPolicies/outbound-policy
description: Test egress policy
~~~

~~~bash
gcloud network-security gateway-security-policies import outbound-policy \
  --source=policy.yaml \
  --location="$REGION"
~~~

### Bước 2. Thêm rule HTTP

~~~yaml
# allow-http.yaml
name: projects/PROJECT_ID/locations/REGION/gatewaySecurityPolicies/outbound-policy/rules/allow-http-wikipedia
description: Allow plain HTTP to the test website
enabled: true
priority: 10
basicProfile: ALLOW
sessionMatcher: host() == 'www.wikipedia.org'
~~~

~~~bash
gcloud network-security gateway-security-policies rules import allow-http-wikipedia \
  --source=allow-http.yaml \
  --location="$REGION" \
  --gateway-security-policy=outbound-policy
~~~

**Không suy ra HTTPS cũng được mở:** để lọc HTTPS theo hostname/path ở explicit mode phải xét TLS inspection và các thuộc tính được hỗ trợ. Không nên thêm `ALLOW all` chỉ để vượt qua lỗi chặn website của production.

### Bước 3. Tạo gateway

~~~yaml
# gateway.yaml
name: projects/PROJECT_ID/locations/REGION/gateways/outbound-proxy
type: SECURE_WEB_GATEWAY
addresses: ["10.60.0.10"]
ports: [443]
gatewaySecurityPolicy: projects/PROJECT_ID/locations/REGION/gatewaySecurityPolicies/outbound-policy
network: projects/PROJECT_ID/global/networks/egress-lab-vpc
subnetwork: projects/PROJECT_ID/regions/REGION/subnetworks/swp-frontend
routingMode: EXPLICIT_ROUTING_MODE
~~~

~~~bash
gcloud network-services gateways import outbound-proxy \
  --source=gateway.yaml \
  --location="$REGION"
~~~

`10.60.0.10` chỉ là IP minh họa trong subnet; khi tạo thật phải chọn IP còn trống hoặc để dịch vụ phân bổ. SWP hiện hỗ trợ tối đa **năm frontend ports** và không thể sửa danh sách này sau khi tạo gateway. Nếu client ở region khác, có thể chọn `allowGlobalAccess` **khi tạo** gateway theo tính năng được hỗ trợ.

### Bước 4. Đọc lại chính sách và gateway

~~~bash
gcloud network-security gateway-security-policies describe outbound-policy \
  --location="$REGION"

gcloud network-security gateway-security-policies rules list \
  --gateway-security-policy=outbound-policy \
  --location="$REGION"

gcloud network-services gateways describe outbound-proxy \
  --location="$REGION"
~~~

Các tham số chính xác có thể khác theo phiên bản Cloud CLI; kiểm tra `gcloud network-security ... --help` và `gcloud network-services ... --help`. Việc tạo gateway/policy có thể phát sinh chi phí.

### Bước 5. Kiểm thử từ VM Linux

~~~bash
PROXY_IP="10.60.0.10"

# Host được rule HTTP cho phép.
curl -v --proxy "http://$PROXY_IP:443" \
  "http://www.wikipedia.org/"

# Host không nằm trong allowlist, kỳ vọng bị từ chối.
curl -v --proxy "http://$PROXY_IP:443" \
  "http://example.org/"
~~~

Một response `200` hoặc redirect `301/302` từ website được phép cho biết request đã đi qua proxy tới đích; mã phản hồi phụ thuộc website thật. Nếu `curl` hiển thị mã `000`, thường là lỗi kết nối/TLS/DNS, chưa đủ căn cứ kết luận rule DENY.

**Hai mối quan hệ TLS khác nhau:** ví dụ dùng `http://` để client kết nối tới proxy. Nếu client dùng `https://` tới proxy, cần certificate frontend phù hợp. Điều này khác với việc SWP **giải mã HTTPS giữa client và website đích** qua TLS inspection.

## 9. Cấu hình workload Java sử dụng explicit proxy

Với Java, cơ chế proxy phụ thuộc thư viện HTTP đang dùng. Một số API Java networking có thể sử dụng các system properties sau:

~~~bash
java \
  -Dhttp.proxyHost=10.60.0.10 \
  -Dhttp.proxyPort=443 \
  -Dhttps.proxyHost=10.60.0.10 \
  -Dhttps.proxyPort=443 \
  -jar app.jar
~~~

Đây là **mẫu cấu hình client**; không bảo đảm mọi thư viện Java đều tuân thủ. Apache HttpClient, OkHttp, gRPC hoặc SDK riêng có thể cần proxy settings khác. Với HTTPS, rule và trust cần được thiết kế như mục 6 và 8; chỉ có rule HTTP minh họa thì HTTPS có thể bị từ chối.

Trong môi trường hỗ trợ các biến proxy:

~~~bash
export HTTP_PROXY="http://10.60.0.10:443"
export HTTPS_PROXY="http://10.60.0.10:443"

# Chỉ bỏ qua proxy với đích nội bộ được duyệt.
export NO_PROXY="localhost,127.0.0.1,metadata.google.internal"
~~~

`NO_PROXY` là ngoại lệ ở **phía client**. Nếu cấu hình quá rộng như `*` hoặc mọi domain ngoài Internet, client có thể bỏ proxy khi đường mạng cho phép. Các runtime khác nhau có thể diễn giải `NO_PROXY` khác nhau; phải thử bằng đúng ứng dụng và thư viện đang sử dụng.

Với GKE, thêm proxy settings vào Pod chỉ tác động đến thành phần có đọc settings. Các luồng pull image, kubelet hoặc control-plane có thể đi theo đường riêng và cần được xác minh độc lập. Với Cloud Run, sử dụng kết nối VPC như **Direct VPC egress** khi phù hợp để app có đường mạng đến proxy, đồng thời cấu hình HTTP client; kết nối VPC **không tự ép** tất cả HTTP request đi qua SWP.

## 10. Chống bypass: proxy settings phải đi cùng mạng

**Chỉ đặt proxy trong ứng dụng không tạo ra ranh giới bảo mật tuyệt đối.** Nếu workload có external IP, Cloud NAT hoặc route đi thẳng Internet, chương trình bỏ qua proxy có thể vẫn gửi request ra ngoài.

Kiểm soát cần thiết:

1. **Giới hạn egress trực tiếp** bằng thiết kế VPC, firewall và route phù hợp, chỉ giữ đường tới gateway cùng các dịch vụ nội bộ được phê duyệt.
2. **Rà soát ngoại lệ**: DNS, metadata server, token services, Google APIs hoặc các dịch vụ nền tảng có thể cần đường mạng riêng; tránh chặn mù quáng khiến workload không khởi động.
3. **Kiểm chứng hai đường**: gửi request có cấu hình proxy để thấy allow/deny và thử kết nối trực tiếp không dùng proxy để xác minh không thể bypass ngoài phạm vi cho phép.
4. **Tách danh tính và quản trị:** workload không tự do sửa service account, secure tag hoặc rule bảo mật nhằm nhận quyền egress rộng hơn.
5. **Kiểm tra multi-VPC/PSC:** mọi nguồn thực phải đi tới đúng proxy và đúng policy, không nối nhầm vào gateway thử nghiệm.
6. **Không làm gián đoạn phát hành:** kiểm thử Git, registry, package manager, Cloud DNS và các dịch vụ vận hành khi chuyển sang default deny.

Ngay cả khi proxy cho phép kết nối tới domain một đối tác, API đích vẫn cần cơ chế authentication và authorization. **Cho phép egress không đồng nghĩa được phép đọc hoặc sửa dữ liệu bên ngoài.**

## 11. Bật TLS inspection khi yêu cầu lọc HTTPS chi tiết

Giả sử hệ thống chỉ được truy cập `https://partner.example/reports` nhưng muốn chặn `https://partner.example/upload`. Hai path nằm trong phần HTTP đã được mã hóa bằng TLS; filter ở mức domain/session không đủ để phân biệt. Cần **TLS inspection** để có thể xét `applicationMatcher` đúng mức hỗ trợ.

Quy trình tổng quát:

~~~text
Xác định nguồn và domain được phép giải mã
  → Chuẩn bị CA pool và CA trong Certificate Authority Service
  → Cấp quyền service agent dùng CA pool
  → Tạo tlsInspectionPolicy theo region
  → Liên kết với gateway security policy
  → Tạo sessionMatcher + applicationMatcher
  → Đặt tlsInspectionEnabled: true ở rule cần giải mã
  → Phân phối CA trust cho client
  → Kiểm thử TLS, certificate pinning và các ngoại lệ
~~~

Ví dụ **minh họa cú pháp rule**, chưa thể import độc lập nếu chưa chuẩn bị CA và inspection policy:

~~~yaml
# inspection-rule.yaml
name: projects/PROJECT_ID/locations/REGION/gatewaySecurityPolicies/outbound-policy/rules/allow-partner-reports
description: Allow a reviewed HTTPS path only
enabled: true
priority: 20
basicProfile: ALLOW
sessionMatcher: host() == 'partner.example'
applicationMatcher: request.path.startsWith('/reports')
tlsInspectionEnabled: true
~~~

Lưu ý `host()` và các điều kiện của session cần tương thích với **chế độ explicit/next-hop** và đặc tính request. Không áp lại ví dụ này cho mọi HTTPS traffic mà không kiểm tra host matching theo tài liệu hiện hành. Đối với client certificate pinning, mutual TLS hoặc dữ liệu cần bảo vệ đặc biệt, hãy xác định ngoại lệ được review trước khi enforce.

TLS inspection có thể cần thêm chi phí CA Service, tác động handshake và trust chain. Quản trị CA phải gồm quyền tối thiểu, quản lý khóa, rotation và quy trình thu hồi. Không ghi payload HTTPS được giải mã vào log nếu không có nhu cầu và quyền xử lý dữ liệu phù hợp.

## 12. Vận hành cùng Compute Engine, GKE, Cloud Run và CI/CD

| Môi trường | Cách kết nối proxy | Điều phải kiểm thử |
|---|---|---|
| **Compute Engine** | Proxy settings trong ứng dụng hoặc route next-hop được hỗ trợ | Firewall, subnet, nguồn identity, request có/không proxy |
| **GKE** | Proxy settings trong Pod hoặc đường mạng theo kiến trúc | Runtime container, DNS, image pull và giao tiếp control plane |
| **Cloud Run** | Đường VPC đến gateway + cấu hình HTTP client trong service | Direct VPC egress/connector, chế độ egress, IAM và kết nối |
| **Build/CI/CD** | Workload network và cấu hình proxy phù hợp | Source repository, Maven/Gradle, artifact registry, token API |

**Compute Engine:** có thể bắt đầu bằng VM lab để kiểm tra dễ dàng với `curl`. Production nên dùng service account riêng theo ứng dụng, không chia sẻ một identity quyền egress cao cho toàn bộ VM.

**GKE:** kiểm soát HTTP từ Pod không tự bảo đảm các luồng điều khiển cluster đi cùng đường. Nếu đặt policy chặt, hãy thử rollout, pull image, DNS resolution và kết nối tới Google APIs khi node mới được tạo.

**Cloud Run:** việc service có VPC connector hoặc Direct VPC egress không có nghĩa mọi request HTTP sử dụng proxy. Phải kiểm tra library thực tế; chế độ `all-traffic` và `private-ranges-only` có ảnh hưởng đến đường mạng tùy kiến trúc.

**CI/CD:** source control, package repositories và các domain CDN phụ trợ đôi khi không nằm trong một hostname. Nên thu thập traffic thực tế qua lab rồi phê duyệt những đích cần thiết, thay vì mở wildcard quá rộng trong production.

## 13. Phân quyền quản trị và kiểm soát thay đổi

Tạo gateway, sửa security policy và quản lý certificate/CA là những thao tác nhạy cảm. Không nên cấp mọi quyền cho developer chỉ để họ gọi được API bên ngoài.

| Vai trò tổ chức | Trách nhiệm | Quyền phù hợp |
|---|---|---|
| **Platform/network admin** | VPC, subnet, gateway, PSC, next-hop | Network administration trong project/host project |
| **Security team** | Duyệt allowlist, TLS inspection, danh tính nguồn | Quyền chỉnh policy có kiểm soát, lưu audit |
| **Application owner** | Đề nghị domain, path, port cần sử dụng | Quyền đọc, tạo request/pull request |
| **CI/CD service account** | Áp IaC sau review | Chỉ các quyền sửa tài nguyên SWP đã phê duyệt |
| **SRE/auditor** | Xem metric, log và điều tra | Cloud Logging/Monitoring viewer phù hợp |

Theo tài liệu Google Cloud, `roles/compute.networkAdmin` được dùng cho nhiều bước triển khai SWP; `roles/certificatemanager.editor` hoặc vai trò tương đương có thể cần khi quản lý certificate frontend. TLS inspection còn có quyền riêng với CA Service và Network Security service agent. Hãy kiểm tra **quyền hiệu lực**, kể cả IAM kế thừa từ Folder/Organization, thay vì cấp `Owner` để giải quyết mọi lỗi.

Một vòng thay đổi sản xuất:

~~~text
Application team yêu cầu domain/URL mới
  → Security đánh giá lý do, dữ liệu và phạm vi
  → Sửa policy bằng mã nguồn/PR
  → Review match expression + priority + plan
  → Kiểm thử với allowed và denied requests
  → Áp production bằng CI/CD identity
  → Xem transaction logs và business metrics
  → Thu hồi ngoại lệ hết hạn
~~~

Nếu rule mới làm ứng dụng mất kết nối, rollback nên trả policy về phiên bản đã được kiểm thử, đồng thời xác định nguyên nhân từ log. Không cần xóa toàn bộ SWP để giải quyết một rule sai. Với TLS inspection, rollback còn liên quan phân phối certificate/trust và các ngoại lệ ứng dụng.

## 14. Cloud Logging, Monitoring và kiểm tra policy

SWP cung cấp **proxy transaction logs** và Cloud Audit Logs. Audit Logs giúp xác định danh tính sửa gateway/policy; transaction logs mô tả request đã đi qua proxy, nguồn, đích, kết quả policy và độ trễ.

Trong **Logs Explorer**, truy vấn giao dịch proxy:

~~~text
logName="projects/PROJECT_ID/logs/networkservices.googleapis.com%2Fgateway_requests"
resource.type="networkservices.googleapis.com/Gateway"
~~~

Tìm các request bị deny theo định dạng log được tài liệu mô tả:

~~~text
logName="projects/PROJECT_ID/logs/networkservices.googleapis.com%2Fgateway_requests"
jsonPayload.policy_evaluation_results.policy_action="DENY"
~~~

Field thực tế có thể khác theo loại gateway, policy và cấu trúc log. Nếu không thấy kết quả, xác minh project chứa gateway, quyền Cloud Logging, thời gian truy vấn và log entry mẫu. Với một số định dạng policy cũ, kết quả có thể xuất hiện ở `enforcedGatewaySecurityPolicy`.

| Tín hiệu | Điều cần tìm |
|---|---|
| Denied requests tăng mạnh | Policy vừa thay đổi, workload mới hoặc hành vi bất thường |
| Request tới domain lạ | Dependency mới, cấu hình sai hoặc khả năng bị xâm nhập |
| HTTP 403 do proxy | Policy deny; đối chiếu match/action |
| Lỗi kết nối hoặc `curl` mã `000` | Route, firewall, TLS, DNS hoặc gateway readiness |
| Latency tăng | Proxy capacity, TLS inspection, Internet đích hoặc network |
| Request/response bytes tăng | Download lớn, trao đổi bất thường và rủi ro chi phí |
| Proxy logs thấp trong khi Internet egress lớn | Có thể tồn tại bypass hoặc nguồn không đi qua gateway |

Cloud Monitoring cung cấp metric cho resource `networkservices.googleapis.com/Gateway`, gồm request count, bytes và dữ liệu hiệu năng tùy cấu hình. Có thể tạo dashboard, alert theo deny rate, latency, lỗi và lưu lượng. Vì log có thể chứa hostname, path, danh tính và metadata nguồn, cần giới hạn quyền xem và thời gian lưu giữ.

**SWP chỉ ghi nhận request mà nó đã xử lý.** Nếu ứng dụng bỏ proxy và vẫn có route Internet trực tiếp, các request bypass sẽ không xuất hiện trong transaction logs của SWP.

## 15. Chi phí, độ tin cậy và giới hạn

Phí SWP thường gồm **gateway-hours** và **khối lượng dữ liệu được xử lý**. Ngoài ra, có thể phát sinh phí Cloud NAT, network, Certificate Manager, CA Service, Cloud Logging và tracing tùy thiết kế. Kiểm tra biểu phí chính thức tại thời điểm ước lượng thay vì cố định con số theo tài liệu cũ.

~~~text
Chi phí dự toán
  ≈ số giờ các gateway hoạt động × đơn giá
  + số GiB proxy xử lý × đơn giá dữ liệu
  + phí network / NAT / CA / certificate / logging / trace nếu có
~~~

| Quyết định | Ảnh hưởng |
|---|---|
| Dùng ít gateway tập trung | Dễ quản trị nhưng có thể tăng độ trễ và phạm vi sự cố |
| Mỗi region có gateway riêng | Tối ưu độ trễ, nhưng tăng giờ gateway và công việc quản trị |
| Bật TLS inspection | Thêm CA, xử lý TLS và yêu cầu trust |
| Ghi transaction logs thời gian dài | Hỗ trợ audit nhưng tăng lưu trữ, chi phí và yêu cầu quyền riêng tư |
| Dùng static egress IP | Giúp đối tác allowlist, phải quản lý IP/NAT |

Các **giới hạn hiện hành** cần kiểm tra:

- SWP hỗ trợ **IPv4**, chưa hỗ trợ IPv6.
- Hỗ trợ HTTP/0.9, 1.0, 1.1, 2.0; **HTTP/3 không được hỗ trợ** theo tài liệu tổng quan.
- Explicit proxy chỉ quản lý traffic của client thực sự cấu hình sử dụng.
- Tính năng có thể khác theo mode, region hoặc giai đoạn phát hành.
- TLS inspection có yêu cầu trust, tương thích certificate và chính sách dữ liệu.
- Trong Shared VPC, gateway nằm ở **host project** theo tài liệu hiện hành.

Cloud Billing budget/alerts dùng để theo dõi chi phí; **budget alert không tự ngắt gateway hoặc dừng mọi traffic**. Với hệ thống quan trọng, nên có kế hoạch điều chỉnh route/policy khi gateway không khả dụng, bảo đảm không tự động mở đường egress trái quy định bảo mật.

## 16. Những sự cố thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra đầu tiên |
|---|---|---|
| Không kết nối được IP:port proxy | Sai subnet, route, firewall, region hoặc gateway chưa sẵn sàng | Gateway describe, VPC route, firewall |
| HTTP đến website allow bị DENY | `sessionMatcher` sai, policy chưa gắn, rule bị tắt | Rules list và transaction logs |
| HTTP chạy, HTTPS bị DENY | Host rule của explicit HTTPS không TLS inspection không áp như HTTP | Mode, inspection policy, session attributes |
| `curl` lỗi certificate | TLS frontend hoặc inspection CA không được client trust | `curl -v` và trust store |
| Vẫn truy cập domain cấm được | Workload bỏ proxy và có route Internet trực tiếp | Test không proxy, Cloud NAT/firewall |
| CI/CD không tải được dependency | Chưa allow đầy đủ registry và domain phụ thuộc | Request logs từ đúng build workload |
| Đối tác từ chối public IP | NAT egress IP chưa nằm allowlist | Managed Cloud NAT/static IP |
| Latency tăng khi inspection | TLS handshake, CA, ứng dụng hoặc Internet đích | Metrics/logs và CA Service |
| Không thấy proxy request log | Sai project hoặc request không đi qua proxy | Logs Explorer và đường kết nối |
| Đã ngừng workload vẫn có phí | Gateway còn tồn tại và tiếp tục tính giờ | Billing theo SKU và gateway |

**Ví dụ:** backend có rule `host() == 'partner.example'` trong explicit mode, HTTP test thành công nhưng HTTPS bị chặn. Không nên sửa bằng cách `ALLOW all`. Hãy kiểm tra khả năng match HTTPS theo mode, xác định cần TLS inspection hay mô hình khác, kiểm thử từ chính HTTP client của ứng dụng rồi mới thay policy.

## 17. Tình huống triển khai cho ba nhóm workload

Một doanh nghiệp thương mại điện tử có:

- **Payments trên GKE** gọi API thanh toán ngoài tổ chức.
- **Catalog trên Compute Engine** tải dữ liệu từ nhà cung cấp.
- **CI/CD pipeline** tải dependencies Java và image từ registry.

~~~text
                 VPC: ecommerce-prod
       Payments (GKE)     Catalog (VM)     CI/CD
                  \           |           /
                   \          |          /
                  Proxy settings / routing
                             ↓
                 Secure Web Proxy (region)
                             ↓
                       Egress policy
                /                             \
         Approved vendor APIs           Approved registries
                             ↓
                       Managed Cloud NAT
                             ↓
                           Internet
~~~

Nhóm platform quản trị gateway, mạng và NAT; nhóm Security kiểm tra allowlist, nhu cầu TLS inspection và log; application owners gửi yêu cầu khi thêm API mới. CI/CD áp chính sách sau review. SRE theo dõi deny rate, latency, dữ liệu xử lý và chi phí theo gateway.

Nếu Payments cần lọc path HTTPS, nhóm kiểm tra yêu cầu mTLS/certificate pinning của nhà cung cấp trước khi bật TLS inspection. Nếu đối tác chỉ cho phép vài IP egress, cấu hình static NAT IP theo hướng dẫn SWP. Nếu pipeline cần nhiều CDN host của package manager, quan sát domain thật từ lab để lập danh sách phù hợp, tránh mở wildcard toàn bộ Internet.

## 18. Checklist trước khi đưa SWP vào production

- [ ] Đã phân biệt egress HTTP/HTTPS với ingress load balancing.
- [ ] Đã chọn explicit, next-hop hoặc PSC theo yêu cầu nguồn workload và mạng.
- [ ] Có PRIVATE subnet và proxy-only subnet không chồng CIDR trong region hỗ trợ.
- [ ] Project/Shared VPC host project, quyền IAM và Billing account đã được chuẩn bị.
- [ ] Gateway liên kết policy chính xác, rule rõ nguồn/đích/priority và default deny.
- [ ] Hiểu giới hạn host matching của HTTPS theo chế độ triển khai.
- [ ] Nếu dùng TLS inspection: có CA pool, inspection policy, trust và ngoại lệ phù hợp.
- [ ] Firewall/route giảm nguy cơ client bỏ proxy đi thẳng Internet.
- [ ] Kiểm thử allow và deny từ đúng workload và đúng runtime.
- [ ] DNS, Google APIs, registry, IAM và CI/CD vẫn hoạt động.
- [ ] Có logs, metrics và alert cho deny/latency/bytes/cost.
- [ ] Public egress IP tương thích allowlist của đối tác.
- [ ] Có quy trình review, rollback và quản lý policy bằng mã nguồn.
- [ ] Đã dự toán phí gateway, xử lý dữ liệu, NAT, CA và logs.

**Bài tập vận dụng:** Một nhóm chạy API Java trên Compute Engine, thanh toán trên GKE và pipeline CI/CD. Công ty yêu cầu chỉ truy cập API đối tác và registry đã duyệt; mọi website khác đều phải bị chặn.

1. Vẽ VPC, PRIVATE subnet, proxy-only subnet, SWP gateway, NAT và đường đi của các workload.
2. Chọn explicit hoặc next-hop và giải thích cách kiểm chứng không có bypass.
3. Lập bảng danh tính workload, đích được phép, priority và quyết định default.
4. Viết một `policy.yaml`, một rule `ALLOW` và một `gateway.yaml` theo mô hình Cloud SWP.
5. Giải thích vì sao rule host HTTP chưa đủ để lọc HTTPS trong explicit mode.
6. Nếu chỉ cho phép `/reports` của một HTTPS domain, liệt kê thành phần TLS inspection cần thiết.
7. Viết hai lệnh `curl` để thử allow/deny; mô tả cách đọc transaction logs.
8. Đề xuất static egress IP, metric/alerts và rollback khi policy mới chặn build pipeline.

## Tài liệu tham khảo chính thức

- [Secure Web Proxy overview](https://cloud.google.com/secure-web-proxy/docs/overview) — chế độ, kiến trúc và giới hạn.
- [Initial setup steps](https://cloud.google.com/secure-web-proxy/docs/initial-setup-steps) — API, IAM, VPC và proxy-only subnet.
- [Quickstart: explicit proxy](https://cloud.google.com/secure-web-proxy/docs/quickstart) — policy, rule, gateway và test.
- [Policies and rules](https://cloud.google.com/secure-web-proxy/docs/policies-and-rules-overview) — gateway security, authorization, rate limiting.
- [Configure gateway security rules](https://cloud.google.com/secure-web-proxy/docs/configure-rules) — CEL và giới hạn HTTPS.
- [Enable TLS inspection](https://cloud.google.com/secure-web-proxy/docs/enable-tls-inspection) — CA, policy và trust.
- [TLS inspection overview](https://cloud.google.com/secure-web-proxy/docs/tls-inspection-overview) — hoạt động và ngoại lệ.
- [Use Cloud NAT for Secure Web Proxy](https://cloud.google.com/secure-web-proxy/docs/use-cloud-nat-for-swp) — public egress IP.
- [Logs, metrics, and traces](https://cloud.google.com/secure-web-proxy/docs/monitor-logs) — quan sát hoạt động.
- [View proxy transaction logs](https://cloud.google.com/secure-web-proxy/docs/view-proxy-transaction-logs) — log schema và truy vấn.
- [Secure Web Proxy pricing](https://cloud.google.com/secure-web-proxy/pricing) — phí gateway và dữ liệu.
