# Frontend, backend service và health check

Một ứng dụng có thể chạy trên nhiều VM Compute Engine, nhiều Pod GKE hoặc nhiều phiên bản Cloud Run. Người dùng chỉ cần truy cập một tên miền như `shop.example.com`, còn hệ thống phải quyết định **nhận yêu cầu ở đâu, chuyển đến dịch vụ nào và backend nào đang đủ khỏe để xử lý**. Google Cloud Load Balancing tách các trách nhiệm đó thành những thành phần có thể quản trị độc lập: **frontend**, **backend service** và **health check**.

Bài học thuộc chương **Cân bằng tải và phân phối nội dung** trong mô-đun `CLOUD_PROVIDERS_GCP`. Khi kết hợp kiến thức organization/project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu và tự động hóa phát hành, bạn có thể triển khai hệ thống an toàn, theo dõi độ tin cậy và kiểm soát chi phí. Bài tập trung vào **Application Load Balancer HTTP(S)**, nhất là *global external Application Load Balancer* dùng mô hình `EXTERNAL_MANAGED`; một số điểm khác biệt của load balancer regional, internal và Network Load Balancer được giải thích riêng để tránh áp dụng sai.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả đường đi của một HTTP(S) request từ DNS đến frontend, URL map, backend service và backend.
2. Phân biệt **forwarding rule**, **target HTTP(S) proxy**, **TLS certificate**, **URL map**, **backend service**, **backend group** và **health check**.
3. Giải thích vai trò của health check và vì sao một backend chạy nhưng không phục vụ được lưu lượng.
4. Nhận biết các loại backend như managed instance group, zonal NEG, serverless NEG và backend bucket.
5. Thiết kế routing theo host/path và giới hạn của chính sách routing khi backend không khỏe.
6. Thực hành các lệnh `gcloud` tạo/kiểm tra các thành phần của một global external Application Load Balancer cho VM instance group.
7. Phân biệt cấu hình health check cho VM/GKE với **ngoại lệ serverless NEG của Cloud Run**.
8. Phân tích lỗi 502/503, TLS, firewall, routing, capacity, logging và chi phí.

## 1. Bức tranh tổng thể của Application Load Balancer

Xét hệ thống thương mại điện tử gồm giao diện web và API, được đặt trong project `commerce-prod`:

~~~mermaid
flowchart LR
    U["Người dùng<br/>https://shop.example.com"]
    DNS["Cloud DNS hoặc DNS khác<br/>shop.example.com → LB IP"]
    FR["Frontend: forwarding rule<br/>Public IP + TCP 443"]
    PROXY["Target HTTPS proxy<br/>TLS certificate"]
    MAP["URL map<br/>/api/* → API<br/>/* → Web"]
    WEB["Backend service: web"]
    API["Backend service: api"]
    HW["Health check: web"]
    HA["Health check: api"]
    BW["Instance group: Web VMs"]
    BA["Zonal NEG hoặc MIG: API"]
    U --> DNS --> FR --> PROXY --> MAP
    MAP --> WEB --> BW
    MAP --> API --> BA
    HW -. "Theo dõi" .-> BW
    HA -. "Theo dõi" .-> BA
~~~

**Đường đi ở trên áp dụng cho ví dụ Application Load Balancer có VM/NEG thông thường.** Nếu backend là **serverless NEG** trỏ đến Cloud Run, backend service **không được gắn health check**. Nếu dùng **backend bucket** để phục vụ đối tượng Cloud Storage, đó là một loại tài nguyên backend khác với backend service.

Một request có thể trải qua các bước:

1. DNS trả về IP công khai của load balancer.
2. **Forwarding rule** nhận kết nối tới IP/protocol/port được cấu hình và trỏ đến **target HTTPS proxy**.
3. **Target proxy** hoàn tất TLS handshake bằng chứng chỉ của tên miền và xử lý HTTP request.
4. **URL map** xét host/path hoặc các quy tắc routing được hỗ trợ để chọn backend service hoặc backend bucket.
5. **Backend service** lựa chọn một backend phù hợp theo cấu hình và tín hiệu sức khỏe/capacity.
6. Backend xử lý yêu cầu; phản hồi được đưa về client qua cơ chế proxy của load balancer.

Điểm mấu chốt: **frontend quyết định client kết nối vào đâu**, **URL map chọn dịch vụ nhận yêu cầu**, còn **backend service quyết định cách phân phối tới nhóm backend**. Health check cung cấp tín hiệu về khả năng phục vụ của backend cho những loại backend có hỗ trợ.

## 2. Frontend: IP, port, forwarding rule và target proxy

**Frontend** là bề mặt người dùng nhìn thấy khi gửi lưu lượng đến load balancer. Tùy loại load balancer, cấu hình thường gồm địa chỉ IP, protocol, port và thành phần nhận/ủy quyền kết nối.

### 2.1. Forwarding rule

**Forwarding rule** có nhiệm vụ gắn một **IP address + protocol + port** với một mục tiêu. Đối với Application Load Balancer, mục tiêu thường là **target HTTP proxy** hoặc **target HTTPS proxy**.

Ví dụ:

~~~text
Tên: shop-https-rule
Phạm vi: global
IP: một địa chỉ IPv4 toàn cục (có thể reserve trước)
Protocol: TCP
Port: 443
Target: shop-https-proxy
~~~

Với global external Application Load Balancer, forwarding rule có thể dùng một IP public toàn cục thuộc network tier phù hợp. **DNS không thay forwarding rule**: DNS chỉ phân giải tên miền về IP; forwarding rule mới xác định cổng/đích xử lý request đến IP đó.

Không nên lẫn `--ports=443` của forwarding rule với cổng ứng dụng trên backend (ví dụ `8080`). Đây là **hai kết nối khác nhau** trong mô hình proxy.

### 2.2. Target HTTP(S) proxy

**Target HTTP proxy** nhận HTTP; **target HTTPS proxy** xử lý kết nối HTTPS và chứng chỉ TLS theo khả năng sản phẩm. Proxy tham chiếu một **URL map** để quyết định routing.

Trong mô hình HTTPS:

- Chứng chỉ TLS phải phù hợp tên miền và ở trạng thái sử dụng được.
- Client kết nối với HTTPS proxy ở frontend.
- Proxy có thể chuyển tiếp tới backend bằng HTTP hoặc HTTPS tùy **backend service protocol**; bật HTTPS ở frontend **không tự biến** giao tiếp backend thành HTTPS.
- Cần kiểm soát redirect HTTP → HTTPS nếu muốn buộc dùng TLS. Redirect là **quy tắc riêng** (thường qua URL map của HTTP frontend), không phải hệ quả tự động của việc tạo HTTPS proxy.

### 2.3. Ví dụ hai frontend cùng phục vụ một website

| Frontend | Thành phần | Hành vi mong muốn |
| --- | --- | --- |
| `http://shop.example.com:80` | Forwarding rule 80 → target HTTP proxy → URL map redirect | Trả redirect sang HTTPS |
| `https://shop.example.com:443` | Forwarding rule 443 → target HTTPS proxy → URL map backend | Phục vụ ứng dụng bằng TLS |

Các thành phần có thể dùng chung IP public khi loại forwarding rule và tổ hợp IP/port/protocol cho phép. **Không công khai HTTP 80** chỉ vì frontend HTTPS tồn tại; hãy chủ động thiết kế redirect hoặc không mở cổng 80.

## 3. URL map: quyết định yêu cầu đi đến ứng dụng nào

Một frontend có thể phục vụ nhiều đường dẫn hoặc nhiều hostname. **URL map** phân tích các thuộc tính HTTP được hỗ trợ để chọn **backend service**, **backend bucket** hoặc thực hiện một hành động như redirect.

Ví dụ:

| Yêu cầu | Quy tắc routing | Đích |
| --- | --- | --- |
| `https://shop.example.com/` | Route mặc định | Backend service `web-backend` |
| `https://shop.example.com/api/orders` | Path prefix `/api/*` | Backend service `orders-api-backend` |
| `https://static.example.com/logo.svg` | Host `static.example.com` | Backend bucket hoặc backend service phục vụ static content |
| `http://shop.example.com/checkout` | URL map HTTP redirect | HTTPS frontend |

### 3.1. URL map không kiểm tra sức khỏe backend

URL map trả lời: **request thuộc route nào?** Backend service trả lời: **backend nào có thể xử lý request đã được route?** Nếu route `/api/*` trỏ tới API backend service mà mọi endpoint của nhóm đó đều unhealthy, URL map **không mặc nhiên chuyển request sang web backend**.

~~~mermaid
flowchart TD
    R["HTTP request /api/orders"] --> M["URL map chọn orders-api-backend"]
    M --> S{"Backend service có backend đủ điều kiện?"}
    S -->|Có| B["Phân phối request tới backend phù hợp"]
    S -->|Không| E["Request có thể thất bại; xem lỗi LB"]
~~~

Muốn có hành vi fallback, retry, traffic splitting hoặc failover, cần **cấu hình đúng tính năng được loại load balancer và backend hỗ trợ**, đồng thời kiểm thử. Không suy ra fallback chỉ từ sự tồn tại của hai backend services.

### 3.2. Các cơ chế routing có thể dùng

Tùy loại Application Load Balancer và chế độ triển khai, routing có thể dựa trên:

- Hostname/host rule.
- URL path hoặc path prefix.
- Header, query parameter và các route rules nâng cao khi được hỗ trợ.
- Redirect, rewrite hoặc weighted traffic splitting theo tính năng tương ứng.

Ví dụ trong giai đoạn phát hành, nhóm có thể dùng tỷ lệ lưu lượng tới phiên bản canary nếu loại load balancer và backend hỗ trợ; phần trăm request **không tương đương** phần trăm người dùng duy nhất và phải được giám sát như một quyết định rollout.

## 4. Backend service: chính sách phân phối tới backend

**Backend service** là cấu hình trung tâm quyết định load balancer kết nối với các backend như thế nào. Một backend service có thể là **global hoặc regional** tùy loại load balancer; cấu hình của nó phải tương thích với forwarding rule, load balancing scheme và backend types.

Những trường quan trọng thường gồm:

| Thuộc tính | Vai trò | Điều cần kiểm tra |
| --- | --- | --- |
| **Protocol** | Giao thức proxy dùng tới backend (HTTP, HTTPS, HTTP/2 hoặc kiểu hỗ trợ) | Backend có thực sự phục vụ giao thức đó không? |
| **Backends** | Instance group hoặc network endpoint group (NEG) được gắn | Có đúng group, zone/region, số endpoint? |
| **Health check** | Kiểm tra backend VM/endpoint theo cách hỗ trợ | Path, port, response và firewall phù hợp? |
| **Balancing mode** | Cách diễn giải capacity theo utilization/rate/connection tùy loại backend và LB | Có tương thích backend type không? |
| **Timeout** | Thời gian xử lý backend request theo cơ chế hỗ trợ | API dài có bị timeout? |
| **Session affinity** | Gợi ý duy trì client cùng backend theo chính sách hỗ trợ | Có cần stateful session hay nên stateless? |
| **Connection draining** | Cho kết nối đang hoạt động một khoảng kết thúc khi rút backend | Có phù hợp rollout/scale down? |
| **Logging** | Quan sát kết nối, lỗi, độ trễ | Có bật và đặt mức log phù hợp chi phí? |
| **Cloud CDN/Cloud Armor** | Cache hoặc chính sách bảo vệ lưu lượng ở các cấu hình hỗ trợ | Có phù hợp loại backend và phạm vi triển khai? |

Không phải thuộc tính nào cũng áp dụng cho mọi backend. **Serverless NEG** không hỗ trợ cấu hình health check và không dùng các balancing mode thông thường như `UTILIZATION`/`RATE`/`CONNECTION` để phân phối theo cách của VM backends.

### 4.1. Backend là tài nguyên gì?

| Backend | Ví dụ | Health check của backend service |
| --- | --- | --- |
| **Managed instance group (MIG)** | Nhóm VM Compute Engine tự mở rộng | Thường dùng health check cho VM |
| **Unmanaged instance group** | Nhóm VM được vận hành thủ công | Thường dùng health check cho VM |
| **Zonal NEG với endpoint VM IP:port** | `GCE_VM_IP_PORT`, thường dùng với container/workload phù hợp | Health check theo endpoint/port được hỗ trợ |
| **Serverless NEG** | Cloud Run, một số dịch vụ serverless khác | **Không hỗ trợ gắn health check** |
| **Backend bucket** | Cloud Storage bucket dùng làm backend nội dung tĩnh | Không phải backend service và không gắn health check VM |

Với GKE, controller của Ingress hoặc Gateway API có thể tạo/quản lý backend services và health checks. Sửa tay các tài nguyên do controller quản lý có thể bị ghi đè khi controller reconcile; hãy cấu hình bằng cơ chế Kubernetes/GKE thích hợp.

### 4.2. Named ports cho instance group

Với **proxy load balancer** dùng instance group backend, `backend service` thường dùng một **named port**, ví dụ `http`, và instance group ánh xạ tên đó thành số cổng thực tế.

~~~text
Frontend forwarding rule: TCP 443
  → HTTPS proxy
  → URL map
  → backend service: port-name=http
  → instance group: http=8080
  → VM backend: TCP 8080
~~~

Named port **không phải** frontend port. Nếu backend service có `--port-name=http` nhưng instance group không có mapping `http:8080`, proxy có thể không biết cổng ứng dụng đúng.

**Named ports không áp dụng giống nhau cho mọi NEG.** Với `GCE_VM_IP_PORT`, port là một phần của endpoint; với serverless NEG, endpoint được đại diện theo dịch vụ serverless thay vì cổng VM.

### 4.3. Backend service không phải chính VM hoặc Cloud Run service

Tạo backend service chưa có nghĩa có máy chủ hoạt động. Bạn còn phải **gắn backend group**, cấu hình application listener, firewall, health check nếu hỗ trợ và đảm bảo ứng dụng chạy đúng endpoint.

Ngược lại, một VM trả HTTP 200 từ bên trong VPC chưa có nghĩa backend được load balancer xem là healthy; health check có thể gặp lỗi DNS/route/firewall/port hoặc timeout khác.

## 5. Health check: phát hiện backend nào đủ điều kiện nhận traffic

**Health check** là các probe định kỳ từ hệ thống Google Cloud tới backend để xác định khả năng trả lời. Một health check có thể dùng HTTP, HTTPS, TCP, SSL, HTTP/2 hoặc gRPC theo loại load balancer/backend được hỗ trợ. Trong ví dụ HTTP backend trên VM, probe HTTP là lựa chọn dễ hiểu.

~~~mermaid
sequenceDiagram
    participant HC as Google Cloud health checker
    participant VM as VM backend :8080
    participant LB as Backend service
    HC->>VM: GET /healthz
    VM-->>HC: HTTP 200 OK
    HC->>LB: Backend healthy sau ngưỡng phù hợp
    Note over VM: Ứng dụng dừng hoặc không sẵn sàng
    HC->>VM: GET /healthz
    VM--xHC: Timeout hoặc HTTP non-200
    HC->>LB: Backend unhealthy sau ngưỡng thất bại
~~~

Health check thường sử dụng:

- **Protocol:** HTTP/TCP/HTTPS/gRPC, phải tương thích cách backend phản hồi.
- **Port:** cổng probe; có thể là fixed port hoặc cơ chế lựa chọn khác được hỗ trợ.
- **Request path:** với HTTP(S), ví dụ `/healthz`.
- **Check interval:** khoảng cách giữa các probe từ mỗi checker.
- **Timeout:** thời gian đợi kết quả của một probe.
- **Healthy threshold:** số lần probe thành công liên tiếp cần thiết trước khi đánh dấu healthy.
- **Unhealthy threshold:** số lần probe thất bại liên tiếp trước khi đánh dấu unhealthy.

### 5.1. Thiết kế endpoint `/healthz` đúng mục đích

Ví dụ ứng dụng web trên VM phục vụ:

~~~http
GET /healthz HTTP/1.1
Host: shop.example.com

HTTP/1.1 200 OK
Content-Type: text/plain

ok
~~~

Probe HTTP thông thường kỳ vọng **mã 200**; redirect sang login, lỗi 401/403/404 hoặc mã 5xx có thể làm probe thất bại. Nếu ứng dụng chuyển tất cả HTTP sang HTTPS, hãy cân nhắc dùng health check HTTPS hoặc tạo endpoint HTTP probe phù hợp, tránh bị redirect ngoài dự kiến.

Endpoint sức khỏe nên:

1. Trả lời nhanh và ổn định ở thời điểm backend đủ sẵn sàng nhận request.
2. Không yêu cầu token người dùng hoặc login cho probe, đồng thời bảo vệ bằng firewall nguồn probe và phạm vi cần thiết.
3. Không chạy truy vấn database nặng cho **mỗi** health check.
4. Phản ánh những phụ thuộc thiết yếu nếu ứng dụng không thể phục vụ khi thiếu chúng.
5. Tránh làm mọi backend cùng bị đánh dấu unhealthy khi một dịch vụ phụ không quan trọng tạm thời lỗi.

**Readiness khác liveness:** readiness cho biết instance có sẵn sàng nhận request; liveness cho biết tiến trình có cần được khởi động lại không. Health check của load balancer chủ yếu phục vụ quyết định **phân phối traffic**. Autohealing của MIG và probe của Kubernetes có thể cần mục đích, timeout và ngưỡng khác nhau.

### 5.2. Health check không phải giao dịch đầu cuối

Một backend `/healthz` trả 200 chưa chắc route `/api/orders` hoạt động đúng. Probe có thể chỉ kiểm tra tiến trình HTTP trong khi database bị lỗi ở một API riêng. Vì vậy, health check cần kết hợp:

- **Synthetic HTTP tests** cho những luồng nghiệp vụ quan trọng.
- Metrics `5xx`, latency và request count.
- Tracing và logs của ứng dụng.
- Cảnh báo saturation, queue depth, database connection và tài nguyên.
- Mục tiêu SLO, error budget và runbook xử lý.

### 5.3. Ngoại lệ: Cloud Run qua serverless NEG

Đối với **serverless NEG** kết nối Cloud Run với Application Load Balancer, Google Cloud **không hỗ trợ health checks** trong backend service. Bạn **không cấu hình** health check HTTP cho backend service này; việc sử dụng Cloud Run runtime, lỗi ứng dụng và chức năng giám sát của dịch vụ cần được xem theo cơ chế riêng. Một số mô hình hỗ trợ **outlier detection** để giảm việc gửi request mới đến backend serverless có biểu hiện lỗi, nhưng đó **không phải một HTTP health check truyền thống**.

Nếu trong hướng dẫn Cloud Run bạn thấy bước “Tạo backend service”, đừng tự thêm `--health-checks` chỉ vì ví dụ Compute Engine làm như vậy.

## 6. Health check phụ thuộc firewall và đường đi

Đối với VM hoặc zonal NEG trong global external Application Load Balancer, backend phải cho phép Google Cloud health check probes và luồng proxy phù hợp. **Không nên mở rộng ingress `0.0.0.0/0` đến cổng ứng dụng chỉ để sửa lỗi health check.**

Theo tài liệu Cloud Load Balancing, những nguồn IPv4 liên quan cho **global external Application Load Balancer** với VM/zonal NEG backend gồm:

~~~text
35.191.0.0/16
130.211.0.0/22
~~~

Việc cho phép dải nào còn phụ thuộc **loại LB**, loại backend, IPv4/IPv6, proxy architecture và những quy tắc firewall khác. Với health check của một số managed global external Application Load Balancer, tài liệu nêu nguồn IPv4 probe `35.191.0.0/16`; dải `130.211.0.0/22` vẫn liên quan GFE proxy traffic đến VM/zonal NEG và các cấu hình khác. Vì vậy khi tạo firewall nên đối chiếu **bảng loại LB cụ thể**, cho đúng source ranges và cổng backend.

**Regional external Application Load Balancer** sử dụng Envoy proxy và cần thêm **proxy-only subnet** để backend nhận traffic từ proxy; firewall thường phải cho phép cả health check source ranges và proxy-only subnet tương ứng. Đừng bê nguyên firewall setup của global load balancer sang regional load balancer.

### 6.1. Một nguyên nhân thường gặp của trạng thái unhealthy

VM có ứng dụng đang nghe `127.0.0.1:8080` nhưng health checker kết nối vào địa chỉ NIC nội bộ của VM. Ứng dụng chỉ bind loopback nên probe không vào được. Cần để ứng dụng bind đúng IP giao diện, ví dụ `0.0.0.0:8080` nếu phù hợp thiết kế, đồng thời giới hạn nguồn bằng firewall.

Các nguyên nhân khác gồm port sai, URL path không tồn tại, HTTP redirect/HTTPS mismatch, timeout quá ngắn, backend vừa khởi động, instance group rỗng hoặc firewall rule áp dụng sai network tag.

## 7. Các bước chọn cấu hình thực tế

Khi thiết kế ingress cho ứng dụng, dùng bảng sau để tránh nhầm trách nhiệm:

| Câu hỏi | Thành phần phải quyết định |
| --- | --- |
| Website nhận tại IP và cổng nào? | Forwarding rule/frontend |
| Dùng HTTPS, chứng chỉ ở đâu? | Target HTTPS proxy + TLS certificate |
| `/api/*` đến nhóm nào, `/*` đến nhóm nào? | URL map |
| Gửi tới MIG hay NEG nào, bằng giao thức/cổng gì? | Backend service + backend attachment |
| Backend có đang đủ khỏe để nhận request? | Health check, **nếu backend type hỗ trợ** |
| Người dùng nào được gọi API private? | IAM/ứng dụng/xác thực, không chỉ LB |
| Giảm request độc hại, DDoS ứng dụng? | Cloud Armor/WAF ở cấu hình hỗ trợ |
| Cache đối tượng tĩnh gần người dùng? | Cloud CDN/backend bucket hoặc backend service hỗ trợ |
| Quan sát 5xx, latency và phân phối request? | Cloud Monitoring/Logging + metrics ứng dụng |
| Giảm giá thành và scale phù hợp? | LB pricing, backend autoscaling, CDN/cache, budgets |

### 7.1. Quyết định global hay regional

Không phải Application Load Balancer nào cũng có cùng phạm vi:

- **Global external Application Load Balancer**: frontend public toàn cục (theo chế độ được hỗ trợ), dùng hạ tầng global của Google; phù hợp website phục vụ nhiều khu vực.
- **Regional external Application Load Balancer**: frontend/Envoy proxy theo region, có **proxy-only subnet**, backend/routing trong phạm vi hỗ trợ của region.
- **Internal Application Load Balancer**: frontend dùng địa chỉ nội bộ cho lưu lượng nội bộ hoặc mạng được kết nối theo kiến trúc được hỗ trợ.
- **Network Load Balancer**: phục vụ lớp TCP/UDP hoặc proxy network với ngữ nghĩa khác; không áp nguyên mô hình URL map HTTP path routing cho passthrough network LB.

Chọn loại LB dựa vào **nguồn client, phạm vi backend, giao thức, tính năng routing, yêu cầu bảo mật, tính sẵn sàng và chi phí**.

## 8. Thực hành gcloud: global external Application Load Balancer với VM backend

Bài lab minh họa frontend → URL map → backend service → health check. Giả sử bạn đã có:

- Project `PROJECT_ID` đã bật Compute Engine API, billing phù hợp và IAM quản trị mạng/compute cần thiết.
- Một **managed instance group** tên `web-mig` trong zone `asia-southeast1-b` thuộc VPC `commerce-vpc`.
- VM trong group phục vụ HTTP trên port `8080` và trả `200 OK` tại `/healthz`.
- VM có network tag `lb-backend` (hoặc bạn điều chỉnh firewall target theo service account/tags thực tế).
- Group có backend còn hoạt động, thuộc mạng và phạm vi triển khai phù hợp.

**Các lệnh tạo LB, reserve IP và liên quan VM có thể phát sinh chi phí.** Chỉ chạy trong project lab được cấp phép. Tên trong ví dụ không tự sinh ra MIG/VPC/VM: nếu chưa có, cần tạo chúng theo bài thực hành Compute Engine trước.

### Bước 1: Kiểm tra cấu hình và named port của instance group

~~~bash
gcloud auth list
gcloud config set project PROJECT_ID

gcloud compute instance-groups managed describe web-mig \
  --zone=asia-southeast1-b \
  --project=PROJECT_ID

# Thiết lập mapping http → 8080 cho các VM thuộc MIG
gcloud compute instance-groups managed set-named-ports web-mig \
  --zone=asia-southeast1-b \
  --named-ports=http:8080 \
  --project=PROJECT_ID
~~~

Named port được dùng khi backend service proxy kết nối tới instance group. Nó không thay thế việc ứng dụng thật sự lắng nghe ở port 8080.

### Bước 2: Tạo HTTP health check

~~~bash
gcloud compute health-checks create http shop-hc \
  --port=8080 \
  --request-path=/healthz \
  --check-interval=10s \
  --timeout=5s \
  --healthy-threshold=2 \
  --unhealthy-threshold=2 \
  --project=PROJECT_ID
~~~

Ý nghĩa: probe HTTP port 8080, path `/healthz`. Hai lần probe thành công hoặc thất bại liên tiếp (theo phân tích của hệ thống health checking) ảnh hưởng trạng thái health. Đây là thông số minh họa, không nên mặc định dùng mọi môi trường production.

### Bước 3: Cho phép nguồn health checker/proxy tới VM backend

~~~bash
gcloud compute firewall-rules create allow-shop-lb-backend \
  --network=commerce-vpc \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-ranges=35.191.0.0/16,130.211.0.0/22 \
  --target-tags=lb-backend \
  --project=PROJECT_ID
~~~

Đây là cấu hình **minh họa cho global external Application Load Balancer với VM backend**, cần rà soát theo loại LB và các hierarchical/network firewall policies đang áp dụng. Không cho phép nguồn quá rộng và không tự thay đổi security policy production chỉ để qua bài lab.

### Bước 4: Tạo backend service và gắn instance group

~~~bash
gcloud compute backend-services create shop-web-backend \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --protocol=HTTP \
  --port-name=http \
  --health-checks=shop-hc \
  --project=PROJECT_ID

gcloud compute backend-services add-backend shop-web-backend \
  --global \
  --instance-group=web-mig \
  --instance-group-zone=asia-southeast1-b \
  --balancing-mode=UTILIZATION \
  --max-utilization=0.8 \
  --project=PROJECT_ID
~~~

Backend service tham chiếu tới health check, dùng protocol HTTP và named port `http`. Lệnh add-backend gắn MIG trong zone được chỉ định. Balancing mode và utilization của ví dụ dùng cho instance group hỗ trợ tương ứng; **không sử dụng những cờ này cho serverless NEG**.

### Bước 5: Tạo URL map

~~~bash
gcloud compute url-maps create shop-url-map \
  --default-service=shop-web-backend \
  --global \
  --project=PROJECT_ID
~~~

URL map có default service `shop-web-backend`. Trong mô hình thực, có thể thêm host/path matcher để chuyển `/api/*` đến backend service API khác. Ví dụ bài lab dùng một default backend để dễ xác minh đường request.

### Bước 6: Tạo HTTP target proxy và frontend

Để đơn giản hóa bài lab, bước đầu dùng **HTTP port 80**. Production nên triển khai HTTPS với chứng chỉ hợp lệ và cấu hình redirect hoặc không mở HTTP tùy chính sách.

~~~bash
# Reserve một global IPv4 cho frontend
gcloud compute addresses create shop-lb-ip \
  --global \
  --ip-version=IPV4 \
  --network-tier=PREMIUM \
  --project=PROJECT_ID

# Tạo HTTP target proxy tham chiếu URL map
gcloud compute target-http-proxies create shop-http-proxy \
  --url-map=shop-url-map \
  --global \
  --project=PROJECT_ID

# Forwarding rule lắng nghe HTTP 80
gcloud compute forwarding-rules create shop-http-rule \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --network-tier=PREMIUM \
  --address=shop-lb-ip \
  --target-http-proxy=shop-http-proxy \
  --ports=80 \
  --project=PROJECT_ID
~~~

**Đây là lệnh tạo tài nguyên thật**, chỉ thực hiện trong lab đã được cấp phép. Không dùng HTTP đơn thuần làm frontend công khai cho dữ liệu nhạy cảm hoặc credential production.

### Bước 7: Kiểm tra từng thành phần

~~~bash
# Frontend / public IP
gcloud compute addresses describe shop-lb-ip \
  --global --project=PROJECT_ID

gcloud compute forwarding-rules describe shop-http-rule \
  --global --project=PROJECT_ID

# URL map, backend service và health check
gcloud compute target-http-proxies describe shop-http-proxy \
  --global --project=PROJECT_ID

gcloud compute url-maps describe shop-url-map \
  --global --project=PROJECT_ID

gcloud compute backend-services describe shop-web-backend \
  --global --project=PROJECT_ID

gcloud compute backend-services get-health shop-web-backend \
  --global --project=PROJECT_ID

gcloud compute health-checks describe shop-hc \
  --global --project=PROJECT_ID
~~~

Lệnh `get-health` giúp xem trạng thái sức khỏe backend từ góc nhìn của backend service. Kết quả có thể cần một khoảng thời gian để phản ánh sau khi vừa tạo hoặc thay đổi cấu hình.

Nếu backend healthy, lấy IP từ lệnh `addresses describe` và thử:

~~~bash
curl -i http://LOAD_BALANCER_IP/
~~~

Hãy dùng **địa chỉ IP thực tế** thay cho `LOAD_BALANCER_IP`. Nếu yêu cầu cần Host header do ứng dụng kiểm tra, truyền hostname dự kiến theo cấu hình. Một HTTP response từ load balancer là bằng chứng đường frontend hoạt động, nhưng vẫn cần kiểm tra routing và trạng thái backend.

### Bước 8: Chuyển sang HTTPS cho production

Khi có tên miền và chứng chỉ TLS hợp lệ:

1. Cấu hình chứng chỉ Google-managed hoặc phương án Certificate Manager/Compute SSL certificate thích hợp.
2. Tạo **target HTTPS proxy** trỏ tới URL map và tham chiếu chứng chỉ.
3. Tạo **forwarding rule port 443** trỏ tới HTTPS proxy, có thể dùng cùng IP nếu các điều kiện sử dụng IP/port/protocol cho phép.
4. Đặt DNS record của hostname trỏ đúng frontend IP; hoàn tất xác minh/hiệu lực chứng chỉ.
5. Nếu cần HTTP → HTTPS redirect, cấu hình **HTTP URL map redirect** riêng và liên kết qua target HTTP proxy của port 80.
6. Thử TLS handshake, hostname, redirect, routing và backend health sau khi phát hành.

**HTTPS frontend khác backend protocol.** Nếu yêu cầu TLS end-to-end, cần chủ động chọn HTTPS/HTTP2 backend theo khả năng hỗ trợ và cấu hình chứng chỉ/kết nối phù hợp.

## 9. Health check với GKE: controller có thể quản lý cho bạn

Trong GKE, Ingress/Gateway controller có thể tạo hoặc điều chỉnh backend service, health check, URL map và các tài nguyên load balancing theo Kubernetes manifests. Ví dụ một `Ingress` trỏ đến một Kubernetes `Service` có thể sinh ra các thành phần Google Cloud tương ứng.

Đặc biệt khi dùng container-native load balancing, GKE có thể dùng **zonal NEG** với endpoint dạng **Pod IP:port** thay vì instance group node.

~~~mermaid
flowchart LR
    IN["GKE Ingress / Gateway"]
    LB["Application Load Balancer"]
    BS["Backend service"]
    NEG["Zonal NEG: Pod IP:port"]
    P1["Pod 1"]
    P2["Pod 2"]
    HC["Health check"]
    IN -. "Controller quản lý" .-> LB
    LB --> BS --> NEG
    NEG --> P1
    NEG --> P2
    HC -. "Kiểm tra" .-> NEG
~~~

### 9.1. Phân biệt ba lớp sức khỏe

| Thành phần | Ví dụ | Quyết định |
| --- | --- | --- |
| **Kubernetes readiness probe** | Pod đã khởi tạo và sẵn sàng xử lý | Pod có nên được đưa vào endpoint của Kubernetes Service? |
| **Kubernetes liveness probe** | Tiến trình bị kẹt và cần khởi động lại? | Kubelet có nên restart container? |
| **Google Cloud LB health check** | Endpoint backend trả lời probe từ LB? | LB có nên gửi traffic qua backend đó? |

Chúng liên quan nhưng **không phải một**. Đặt liveness probe quá nhạy có thể tạo vòng restart; health check LB quá nhạy có thể làm traffic bị rút khỏi cả nhóm trong lúc ứng dụng khởi động.

Cách cấu hình health check với GKE có thể liên quan đến `BackendConfig`, `HealthCheckPolicy` hoặc hành vi controller khác nhau theo loại Ingress/Gateway và phiên bản/feature. Khi GKE đang quản lý tài nguyên LB, hãy sửa **cấu hình nguồn** trên Kubernetes thay vì chỉ chỉnh tay health check trên Google Cloud Console.

## 10. Health check với Cloud Run: ngoại lệ cần nhớ

Application Load Balancer có thể trỏ đến Cloud Run thông qua **serverless NEG**. Tuy nhiên backend service có serverless NEG **không được cấu hình health check**.

~~~mermaid
flowchart LR
    C["Client HTTPS"]
    F["Frontend + TLS + URL map"]
    B["Backend service"]
    S["Serverless NEG"]
    R["Cloud Run service"]
    C --> F --> B --> S --> R
~~~

Một số điểm cần kiểm tra:

- Cloud Run service đã được triển khai đúng region và đang xử lý yêu cầu phù hợp.
- NEG liên kết đúng Cloud Run service; backend service chỉ dùng những tùy chọn hỗ trợ serverless NEG.
- Cloud Run ingress settings và xác thực phù hợp với mô hình frontend load balancer.
- Xem metrics lỗi, latency, Cloud Run request logs, startup/liveness probes ở runtime và Cloud Load Balancing request logs.
- Khi lỗi tăng, cân nhắc những tính năng như outlier detection nếu loại LB/NEG hỗ trợ; **đừng thêm HTTP health check của VM**.

Khi backend là Cloud Run, đừng suy luận “không có health check resource” tức cấu hình sai: đây là giới hạn thiết kế của **serverless NEG backend**.

## 11. Health check, balancing mode và khả năng chịu tải

Backend được đánh dấu **healthy** chỉ cho biết nó đáp ứng điều kiện probe. Backend vẫn có thể quá tải khi nhận lượng request lớn, vì vậy **backend service** còn có cơ chế phân phối/capacity.

Các yếu tố cần phối hợp:

- **Balancing mode:** ví dụ utilization, rate hoặc connection tùy loại backend/LB.
- **Capacity scaler:** giới hạn tỷ lệ capacity mà nhóm backend được sử dụng khi loại backend hỗ trợ.
- **Autoscaling:** MIG/GKE/Cloud Run tự điều chỉnh số instance/pod theo metric và chính sách tương ứng.
- **Connection draining:** giúp hạn chế gián đoạn khi gỡ backend hoặc scale down.
- **Timeout:** không được quá ngắn so với request hợp lệ, cũng không nên quá dài để che giấu lỗi.
- **Session affinity:** chỉ bật khi có lý do; không biến dịch vụ stateful thành hệ thống có tính sẵn sàng cao một cách tự động.

~~~mermaid
flowchart TD
    A["Backend đủ khỏe theo health check"] --> B{"Còn capacity để nhận request?"}
    B -->|Có| C["Nhận lưu lượng theo balancing policy"]
    B -->|Không| D["Cần thêm capacity, giới hạn traffic hoặc xử lý quá tải"]
    C --> E["Metrics độ trễ, 5xx và saturation"]
    D --> E
    E --> F["Điều chỉnh autoscaling, policy hoặc kiến trúc"]
~~~

**Không thay health check bằng autoscaler.** Một nhóm VM có số lượng instance lớn vẫn có thể unhealthy nếu port/firewall sai; ngược lại một nhóm healthy vẫn có thể có latency xấu do tải cao.

## 12. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra ưu tiên |
| --- | --- | --- |
| Tên miền không truy cập được | DNS chưa trỏ đúng IP frontend, propagation hoặc cấu hình certificate | DNS record, forwarding rule, IP address, TLS certificate |
| Frontend nhận được TCP nhưng HTTPS lỗi | Chứng chỉ chưa active/không khớp hostname, target proxy sai | TLS handshake, certificate, URL map của proxy |
| Request `/api/*` đi vào web backend | URL map thiếu/misconfigured host/path matcher | URL map, route precedence và default backend |
| Backend service báo unhealthy | `/healthz` trả non-200, sai port, timeout, firewall | `get-health`, log app, đường probe, tags |
| VM `curl localhost` được nhưng LB không được | App chỉ bind loopback, firewall chặn probe | Listener `0.0.0.0`, NIC IP, firewall nguồn LB |
| `502` hoặc `503` | Backend unavailable, connection reset, timeout, protocol mismatch hoặc cấu hình khác | LB request logs, status details, health, backend logs |
| Tạo backend service xong nhưng không nhận request | Chưa add backend hoặc chưa nối URL map/proxy/forwarding rule | Kiểm tra từng liên kết trong chuỗi |
| Health check không xuất hiện với Cloud Run | Dùng serverless NEG, không hỗ trợ health check | Kiểm tra serverless NEG và metrics/runtime logs |
| GKE pod healthy nhưng LB unhealthy | Khác biệt giữa readiness, LB check, NEG port/firewall | Ingress/Gateway controller, NEG endpoints, backend health |
| Chỉ regional LB thất bại tới backend | Thiếu proxy-only subnet hoặc ingress firewall tương ứng | Regional Envoy source ranges và route/firewall |
| Lỗi sau khi deploy bản mới | Instance chưa ready, health check quá sớm hoặc shutdown quá nhanh | Startup/readiness, rolling update, draining |
| Lưu lượng tăng nhưng không tăng throughput | Capacity/scaling policy, backend saturation, quota | Metrics CPU/latency/rate, autoscaling, backend service config |

### 12.1. Quy trình phân tích theo đường đi của request

~~~mermaid
flowchart TD
    A["Client gặp lỗi"] --> B{"DNS trả đúng frontend IP?"}
    B -->|Không| C["Sửa DNS / IP record"]
    B -->|Có| D{"Forwarding rule và target proxy đúng?"}
    D -->|Không| E["Kiểm tra listener, TLS, target proxy"]
    D -->|Có| F{"URL map trỏ đúng backend?"}
    F -->|Không| G["Kiểm tra host/path/default routing"]
    F -->|Có| H{"Backend type là serverless NEG?"}
    H -->|Có| I["Kiểm tra Cloud Run ingress, logs, latency, NEG"]
    H -->|Không| J{"LB backend healthy?"}
    J -->|Không| K["Kiểm tra port, path, firewall và health checker"]
    J -->|Có| L["Kiểm tra capacity, timeout, 5xx và ứng dụng"]
~~~

**Lưu ý:** Một số HTTP status trả về từ chính ứng dụng; một số lỗi do load balancer tạo. Với lỗi 502/503 cần phân biệt qua logging/status details, tránh chỉ dựa vào mã lỗi.

### 12.2. Khi nào nên xem firewall?

Nếu backend là Compute Engine instance group hoặc GKE zonal NEG, probe và traffic proxy phải đến được port ứng dụng. Kiểm tra:

1. VPC và subnet của backend.
2. Target network tags hoặc service account của firewall rule.
3. Source ranges đúng với loại LB.
4. Protocol và backend port đúng.
5. Firewall policies ở cấp organization/folder/network nếu có.
6. Process thực sự lắng nghe IP/port cần thiết.

Với **serverless NEG**, không áp dụng firewall rule health check VM tương tự. Với **regional Envoy-based LB**, traffic từ proxy-only subnet cần được cho phép tới backend tương ứng.

## 13. Logging, monitoring và SLO

Một load balancer hoạt động tốt cần quan sát ở cả frontend và backend. Những tín hiệu nên theo dõi:

| Tín hiệu | Câu hỏi |
| --- | --- |
| **Request count / rate** | Lưu lượng đang tăng đột ngột ở hostname/path nào? |
| **Response code class 2xx/4xx/5xx** | Lỗi đến từ client, proxy hay backend? |
| **Backend latency** | Thời gian xử lý ở backend có tăng? |
| **Total latency** | Trải nghiệm người dùng chịu ảnh hưởng thế nào? |
| **Backend health** | Có bao nhiêu VM/NEG endpoint đang healthy? |
| **Timeout/connection errors** | Kết nối tới backend có bị reset hoặc chậm? |
| **Backend capacity** | Instance/pod có đủ để nhận lưu lượng? |
| **TLS failures/certificate status** | HTTPS frontend có cấu hình hợp lệ không? |
| **Cloud Armor events** | Lưu lượng có bị chặn bởi policy bảo mật không? |
| **Cloud CDN cache metrics** | Tỷ lệ hit/miss và độ trễ nội dung tĩnh có hợp lý? |

Cloud Logging cho phép ghi request logs theo khả năng cấu hình của load balancer. Health checks và backend metrics có nguồn dữ liệu riêng; không phải mọi chi tiết đều xuất hiện trong cùng một log record.

Một ví dụ SLO cho web API: **99,9% request thành công** trong kỳ đo theo định nghĩa cụ thể về kết quả thành công và ngoại lệ. Để đo đúng, cần định nghĩa rõ denominator, những status code tính là lỗi và nơi lấy dữ liệu. SLO khác trạng thái “mọi backend healthy”: backend có thể healthy nhưng vẫn tạo lỗi nghiệp vụ.

### 13.1. Đọc báo cáo lỗi có thứ tự

Khi gặp `502`/`503`:

1. Ghi thời điểm, hostname, đường dẫn, request ID/trace ID nếu có.
2. Kiểm tra frontend certificate, URL map và backend service đích.
3. Đọc `get-health` (nếu health check được hỗ trợ) và metrics trạng thái healthy.
4. Đối chiếu load balancer request logs với logs của VM/GKE/Cloud Run.
5. Kiểm tra firewall, protocol, cổng, timeout, connection draining và capacity.
6. Xác định nguyên nhân và thực hiện rollback hoặc scale khi cần; xác minh lại SLO.

Không đưa token truy cập, private key hay dữ liệu khách hàng vào log chẩn đoán.

## 14. Bảo mật và IAM quanh các thành phần

Load balancer giải quyết nhận/routing/phân phối traffic, không tự cung cấp mọi lớp an ninh. Thiết kế phù hợp cần có:

- **HTTPS và TLS certificate** cho client-facing frontend.
- **Cloud Armor** khi loại LB và backend hỗ trợ để kiểm soát một số dạng lưu lượng độc hại.
- **Firewall** giới hạn đường từ health checker/proxy tới VM/NEG.
- **IAM** để hạn chế ai được tạo forwarding rule, đổi URL map, gắn backend service, chỉnh health check hoặc quản lý chứng chỉ.
- **Application authentication/authorization** cho những API yêu cầu user/service identity.
- **Secret Manager/runtime identity** cho ứng dụng backend, không nhúng service account key trong config frontend.
- **Cloud Audit Logs** để xem các thay đổi cấu hình hạ tầng theo phạm vi hỗ trợ.

### 14.1. Thay URL map cũng là thay đổi bảo mật

Nếu ai đó chỉnh `/admin/*` sang một backend công khai khác hoặc đổi host rule, lưu lượng có thể đi sai dịch vụ. Quyền cập nhật URL map, target proxy, certificate, backend service và forwarding rule cần được kiểm soát như thay đổi hạ tầng production.

### 14.2. Load balancer không tự làm backend private “an toàn”

VM backend có thể còn external IP hoặc một firewall ingress rộng. Khi đó client có thể có đường truy cập **vượt qua** load balancer và Cloud Armor. Hãy cân nhắc loại bỏ external IP không cần thiết, thu hẹp firewall và xác minh tuyến truy cập trực tiếp theo kiến trúc.

Với Cloud Run, cần chú ý ingress settings và cơ chế ngăn truy cập trực tiếp vào URL `run.app` nếu yêu cầu bắt buộc đi qua load balancer. Cấu hình phải phù hợp khả năng của Cloud Run và load balancer; đừng giả định chỉ thêm serverless NEG sẽ tự chặn toàn bộ đường vào khác.

## 15. Tình huống triển khai: Web trên MIG, API trên Cloud Run, assets trên Cloud Storage

Công ty Atlas vận hành hệ thống:

- `shop.example.com` phục vụ web frontend từ managed instance group.
- `shop.example.com/api/*` chạy Cloud Run.
- `static.example.com/*` trả tệp ảnh và JavaScript từ Cloud Storage.

Có thể thiết kế:

~~~mermaid
flowchart TD
    CLIENT["Internet client"] --> FE["HTTPS frontend<br/>IP + certificate + target proxy"]
    FE --> UM["URL map"]
    UM -->|shop.example.com /*| WEB["Backend service web"]
    WEB --> MIG["MIG Web VMs"]
    H["Health check /healthz"] -.-> MIG
    UM -->|shop.example.com /api/*| API["Backend service api"]
    API --> NEG["Serverless NEG → Cloud Run"]
    UM -->|static.example.com| BUCKET["Backend bucket → Cloud Storage"]
    CDN["Cloud CDN (nếu cấu hình)"] -. "Cache hỗ trợ" .-> BUCKET
~~~

**Ba đích có cơ chế sức khỏe khác nhau:**

1. **Web MIG:** backend service có health check HTTP; chỉ nhận traffic trên VM đáp ứng tiêu chí.
2. **Cloud Run:** backend service gắn serverless NEG, **không có health check**; dùng Cloud Run metrics và ứng dụng để đánh giá.
3. **Cloud Storage backend bucket:** đường phục vụ nội dung tĩnh qua backend bucket, **không gắn HTTP health check của VM**.

Đối với static content, có thể bật **Cloud CDN** theo cấu hình hỗ trợ để cache gần người dùng, giảm backend requests hoặc cải thiện latency. Nhưng Cloud CDN không tự giải quyết việc cache nội dung riêng tư: phải thiết kế cache key, cache-control, invalidation và bảo mật dữ liệu đúng yêu cầu.

### 15.1. Bảo đảm phát hành không gián đoạn

Khi rollout bản web mới:

1. Tạo/khởi động instance mới trong MIG và đợi ứng dụng sẵn sàng.
2. Để health check xác nhận backend đủ khỏe trước khi nhận traffic.
3. Phân phối request qua backend service theo policy.
4. Gỡ instance cũ với connection draining/rolling update phù hợp.
5. Theo dõi errors/latency trước và sau rollout; rollback nếu vượt ngưỡng chấp nhận.

Với Cloud Run, việc điều phối revision/traffic splitting diễn ra theo cơ chế Cloud Run, có thể kết hợp với routing phía LB khi phù hợp. Không sao chép nguyên các ngưỡng health check của VM sang serverless NEG.

## 16. Chi phí và chọn cấu hình phù hợp

Một Application Load Balancer có thể phát sinh chi phí từ forwarding rules, xử lý dữ liệu, egress và những thành phần backend liên quan theo bảng giá thực tế. Thêm Cloud CDN, Cloud Armor, Cloud Logging, instance group/VM hoặc các dịch vụ backend cũng có thể phát sinh phí riêng.

| Quyết định | Ảnh hưởng chi phí/công sức |
| --- | --- |
| Global hay regional load balancer | Khác phạm vi, hạ tầng proxy và mô hình phí được hỗ trợ |
| Nhiều frontend/forwarding rules | Có thể tăng số cấu hình và chi phí tương ứng |
| Backend VM và MIG autoscaling | VM/CPU/RAM/disk/network tính phí theo mức sử dụng |
| Cloud Run backend | Dịch vụ serverless tính phí theo mô hình Cloud Run và các cấu hình liên quan |
| CDN | Có thêm phí cache/egress nhưng có thể giảm request tới backend |
| Logging quá chi tiết | Có thể tăng lượng logs và chi phí lưu/truy vấn |
| Health check quá dày | Tăng lưu lượng probe và tác động backend; cần chọn interval hợp lý |

Không có công thức một giá cố định cho mọi load balancer. Hãy xem **Cloud Load Balancing pricing**, bảng giá backend, Google Cloud Pricing Calculator và tạo **Cloud Billing budgets** cho project lab. Budget cảnh báo, không tự tắt load balancer.

### 16.1. Khi kết thúc lab cần dọn gì?

Nếu lab dùng các tài nguyên trong phần 8, cần kiểm tra và dọn có kiểm soát theo thứ tự phụ thuộc:

1. Xác minh chính xác project lab, URL map, proxy, forwarding rule, backend service, MIG.
2. Gỡ/xóa forwarding rule và target proxy/URL map lab khi không còn consumer.
3. Gỡ backend attachment và xóa backend service/health check lab sau khi xác nhận không dùng chung.
4. Xóa MIG/VM hoặc nguồn thử nghiệm nếu được phép; kiểm tra disk, image và IP còn tồn tại.
5. Giải phóng địa chỉ public đã reserve riêng nếu không còn dùng.
6. Xem lại chi phí sau độ trễ dữ liệu billing.

**Không xóa backend service hoặc health check đang được load balancer production dùng chung.** Danh sách cleanup là hướng dẫn kiểm kê, không phải lệnh tự động thực hiện.

## 17. Bài tập tự kiểm tra

**Câu 1.** Người dùng gọi `https://shop.example.com/api/orders`. Thành phần nào quyết định route `/api/*` đến API backend: forwarding rule hay URL map?

*Gợi ý:* **URL map**. Forwarding rule xác định IP/port và target proxy cho kết nối đầu vào.

**Câu 2.** Frontend phục vụ HTTPS port 443, nhưng VM chạy HTTP ở port 8080. Điều này có hợp lệ không?

*Gợi ý:* Có thể hợp lệ. Target HTTPS proxy xử lý kết nối từ client; backend service/proxy tạo kết nối tới backend theo protocol/port được cấu hình. Để TLS tới backend cần cấu hình giao thức backend tương ứng.

**Câu 3.** Tại sao VM trả `200` với `curl http://127.0.0.1:8080/healthz` nhưng backend service vẫn báo unhealthy?

*Gợi ý:* Ứng dụng có thể chỉ bind loopback, firewall chặn nguồn probe, named port sai, path/timeout khác, hoặc instance group chưa được gắn đúng.

**Câu 4.** Một backend service trỏ Cloud Run bằng serverless NEG. Bạn có nên tạo HTTP health check và gắn vào backend service đó không?

*Gợi ý:* Không. Google Cloud không hỗ trợ health check cho serverless NEG backends.

**Câu 5.** Khi tất cả VM của API backend unhealthy, URL map có tự gửi `/api/*` sang web backend không?

*Gợi ý:* Không mặc định. URL map chọn backend service theo routing rules; fallback/failover cần được cấu hình đúng tính năng hỗ trợ.

**Câu 6.** Với global external Application Load Balancer dùng VM backend, bạn mở ingress `0.0.0.0/0` tới port backend để health check qua. Cách này có phù hợp không?

*Gợi ý:* Không nên. Hãy xác định đúng source ranges của health checker/GFE theo tài liệu và giới hạn firewall đến port/backend cần thiết.

**Câu 7.** Nhóm GKE dùng Ingress controller tạo health check Google Cloud. Sau khi chỉnh trực tiếp trên Console, cấu hình lại thay đổi. Vì sao?

*Gợi ý:* Controller có thể reconcile các tài nguyên do nó quản lý. Hãy chỉnh nguồn cấu hình GKE/Kubernetes theo cơ chế Ingress/Gateway phù hợp.

**Câu 8.** Cloud Run service có nhiều request lỗi nhưng không có health check resource trong backend service. Có phải load balancer bị thiếu thành phần?

*Gợi ý:* Không, nếu backend là serverless NEG. Kiểm tra Cloud Run ingress, request logs, revision, latency và metrics, cùng cấu hình LB.

**Câu 9.** Một forwarding rule lắng nghe port 80, target HTTP proxy tham chiếu URL map, URL map có default service. Tại sao vẫn nhận lỗi khi truy cập?

*Gợi ý:* Có thể thiếu backend group, named port sai, health check unhealthy, firewall chặn, protocol mismatch, timeout hoặc ứng dụng chưa chạy. Kiểm tra toàn bộ chuỗi.

**Câu 10.** Khi chọn cân bằng tải toàn cục so với regional, điều gì cần kiểm tra thêm cho regional external Application Load Balancer?

*Gợi ý:* Regional Envoy proxy thường cần proxy-only subnet và firewall cho lưu lượng từ proxy-only subnet đến backend, ngoài health check sources và các điều kiện regional.

## 18. Checklist ghi nhớ

- [ ] Xác định đúng loại load balancer: global/regional, external/internal, Application/Network.
- [ ] Frontend có IP/port/protocol/forwarding rule phù hợp.
- [ ] Target proxy tham chiếu đúng URL map và chứng chỉ TLS hợp lệ nếu dùng HTTPS.
- [ ] URL map có default backend và các host/path rules đúng kỳ vọng.
- [ ] Backend service dùng đúng protocol, backend group và cổng; named port khớp instance group.
- [ ] Health check đúng protocol/path/port/threshold nếu loại backend hỗ trợ.
- [ ] **Không gắn health check với serverless NEG.**
- [ ] Firewall cho phép nguồn health checker/proxy ở đúng port; regional LB có proxy-only subnet khi cần.
- [ ] Quan sát health, 5xx, latency và capacity; phân biệt readiness của app với health check của LB.
- [ ] Rà soát HTTPS, IAM, Cloud Armor, Cloud CDN và khả năng truy cập trực tiếp backend.
- [ ] Có ngân sách, owner, quy trình rollback và cleanup cho môi trường thử nghiệm.

**Ba câu hỏi quan trọng khi triển khai một ứng dụng mới:** *Client kết nối ở frontend nào? URL map chọn backend service nào? Backend đó được xác định đủ khỏe và đủ capacity bằng cơ chế gì?* Trả lời rõ ba câu hỏi giúp triển khai Compute Engine/GKE/Cloud Run tin cậy hơn và phát hiện lỗi sớm hơn.

## Tài liệu tham khảo chính thức

- [External Application Load Balancer overview](https://cloud.google.com/load-balancing/docs/https)
- [Forwarding rules overview](https://cloud.google.com/load-balancing/docs/forwarding-rule-concepts)
- [Target proxies overview](https://cloud.google.com/load-balancing/docs/target-proxies)
- [URL maps overview](https://cloud.google.com/load-balancing/docs/url-map-concepts)
- [Backend services overview](https://cloud.google.com/load-balancing/docs/backend-service)
- [Health checks overview](https://cloud.google.com/load-balancing/docs/health-check-concepts)
- [Firewall rules for load balancing](https://cloud.google.com/load-balancing/docs/firewall-rules)
- [Serverless NEGs](https://cloud.google.com/load-balancing/docs/negs/serverless-neg-concepts)
- [Global external Application Load Balancer with VM instance groups](https://cloud.google.com/load-balancing/docs/https/setup-global-ext-https-compute)
- [Cloud Load Balancing pricing](https://cloud.google.com/load-balancing/pricing)

