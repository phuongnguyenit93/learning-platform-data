# Thực hành bảo vệ workload không có IP công khai

> **Chương:** Bảo mật và truy cập mạng  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một máy chủ ứng dụng trong production không nhất thiết phải có địa chỉ IP công khai để phục vụ công việc. VM chạy Java, node GKE hoặc cơ sở dữ liệu có thể chỉ dùng **internal IP**, nhận quản trị thông qua **Identity-Aware Proxy (IAP)**, truy cập Google APIs qua **Private Google Access** và khi thực sự cần ra Internet thì đi qua **Public Cloud NAT**. Cách thiết kế này giảm bề mặt tiếp xúc trực tiếp với Internet, nhưng không tự thay thế firewall, IAM, xác thực ứng dụng, kiểm soát egress hay quan sát hệ thống.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học tìm hiểu Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, tự động hóa phát hành, theo dõi độ tin cậy và chi phí. Bài thực hành của chương **Bảo mật và truy cập mạng** xây dựng một Compute Engine VM không có external IPv4 làm tình huống chính, sau đó phân tích cách áp dụng nguyên tắc tương tự với GKE, Cloud Run và Cloud SQL.

**Kết quả học tập:** Sau bài này, bạn có thể:

1. Giải thích “không có external IP” bảo vệ điều gì và chưa bảo vệ điều gì.
2. Tạo custom VPC/subnet và VM Linux chỉ dùng internal IPv4.
3. Cho phép quản trị SSH qua **IAP TCP forwarding** và **OS Login** với IAM phù hợp, không mở SSH ra `0.0.0.0/0`.
4. Dùng **Private Google Access** để VM có thể tiếp cận Google APIs được hỗ trợ mà không cần external IP.
5. Chỉ bật **Public Cloud NAT** khi workload thật sự cần kết nối outbound tới Internet, hiểu rằng NAT không mở inbound.
6. Kiểm tra firewall, routing, service account, metadata, nhật ký và chính sách tổ chức.
7. Viết checklist xác minh và dọn tài nguyên an toàn sau thực hành.

## 1. Bối cảnh và mô hình đe dọa

Giả sử doanh nghiệp vận hành hệ thống đặt hàng:

- **Compute Engine VM:** tác vụ Java định kỳ lấy dữ liệu và gửi thông điệp; không cần người dùng Internet truy cập trực tiếp.
- **Cloud Run:** API tiếp nhận request theo luồng đã kiểm soát danh tính và ingress.
- **GKE:** các worker nội bộ xử lý đơn hàng.
- **Cloud SQL:** lưu dữ liệu giao dịch, chỉ các workload được cấp quyền mới kết nối.
- **Cloud Storage / Secret Manager / Artifact Registry:** các API/dịch vụ được dùng để lấy tệp, bí mật, image hoặc package.

Mục tiêu là giảm rủi ro **quét cổng, brute-force SSH, truy cập trái phép và data exfiltration** do kết nối không được quản lý. Không cấp public IP cho VM là một lớp phòng vệ tốt, nhưng **không phải biện pháp đơn lẻ đủ an toàn**:

| Rủi ro | Không có external IPv4 giải quyết được gì? | Biện pháp vẫn cần |
| --- | --- | --- |
| Internet gửi gói trực tiếp tới public IP của VM | VM không có địa chỉ external IPv4 để nhận theo đường trực tiếp đó | Firewall ingress, IAP, hạn chế dịch vụ lắng nghe |
| Người nội bộ hoặc mạng VPC khác truy cập trái phép | **Không tự chặn** kết nối private qua VPC/VPN/Interconnect | Firewall, IAM, app authentication, segmentation |
| VM gửi dữ liệu ra Internet | Có thể không có đường outbound trực tiếp; **có NAT hoặc proxy thì vẫn gửi được** | Egress rules, NAT policy, proxy/inspection, IAM, VPC Service Controls khi phù hợp |
| App bị lộ qua external load balancer | VM không có public IP **vẫn có thể là backend của một external LB** | Kiểm tra frontend LB, Cloud Armor, IAP for web, IAM/auth |
| Chiếm service account của workload | Không được giải quyết bằng private IP | IAM tối thiểu, metadata security, credential hygiene |
| Lỗ hổng package hoặc ứng dụng | Không được giải quyết | Patch management, image scanning, logging, hardening |
| Mất truy cập quản trị do sai firewall | Không có IP công khai làm đường SSH trực tiếp không tồn tại | IAP, quyền OS Login, kiểm thử và phương án khôi phục |

### 1.1. Phân biệt “no public IP”, “private workload” và “private service”

- **No external IP on a VM**: network interface VM không có access config external IPv4; cần xem cả IPv6 nếu dùng dual-stack.
- **Private workload**: ngoài địa chỉ, phải xem **ai có thể gọi**, **đi theo đường nào**, **xác thực ra sao**, và **có thể outbound đến đâu**.
- **Private service endpoint**: địa chỉ nội bộ có thể truy cập từ mạng được kết nối, ví dụ internal load balancer hoặc Cloud SQL private IP. Nó không tự là ACL hay IAM policy.
- **Public frontend with private backends**: nhiều ứng dụng Internet vẫn có load balancer public phía trước, còn VM/GKE backend **không có external IP**. Đây là kiến trúc hợp lệ khi doanh nghiệp cần public API có kiểm soát.

**Nguyên tắc:** “Không gắn public IP lên máy” chỉ là một thuộc tính của network interface. Đánh giá **toàn bộ đường ingress, egress, danh tính và dữ liệu** trước khi tuyên bố workload được bảo vệ.

## 2. Kiến trúc thực hành

Ta sẽ tạo một custom VPC và subnet có **Private Google Access**. VM có internal IPv4 nhưng không có external IPv4. Người quản trị có quyền SSH qua IAP; VM có thể gọi Google APIs được hỗ trợ. Public NAT là **tùy chọn**, chỉ thêm khi cần truy cập website/package repository ngoài Google Cloud.

~~~mermaid
flowchart TD
    ADMIN["Kỹ sư có IAM"] -->|"SSH qua TLS/IAP"| IAP["IAP TCP forwarding"]
    IAP -->|"Nguồn 35.235.240.0/20, TCP:22"| FW["VPC firewall ingress có target tag"]
    subgraph VPC["Custom VPC: private-lab-net"]
      FW --> VM["VM Java lab\nInternal IPv4 only\nKhông external IPv4"]
      VM --> PGA["Private Google Access\ntrên subnet"]
      VM --> NAT["Public Cloud NAT\nchỉ khi có nhu cầu egress"]
    end
    PGA --> GOOGLE["Google APIs được hỗ trợ\nví dụ Cloud Storage"]
    NAT --> INTERNET["Internet outbound\nví dụ Debian repository"]
    PEER["Máy khác trong VPC hoặc qua VPN"] -. "Firewall kiểm soát riêng" .-> VM
~~~

### 2.1. Đường đi của từng loại lưu lượng

| Luồng | Đường đi | Điều kiện quan trọng |
| --- | --- | --- |
| Kỹ sư SSH vào VM | Máy kỹ sư → IAP → internal IP VM:22 | IAM IAP + OS Login/SSH, firewall cho nguồn IAP |
| VM gọi Google APIs | Internal IP VM → VPC → Google APIs qua Private Google Access | Bật tại subnet, DNS/route/firewall/API/IAM phù hợp |
| VM tải file từ Internet bất kỳ | Internal IP VM → default route → **Public Cloud NAT** → Internet | Có NAT đúng subnet/region, route và egress allow |
| VM → VM khác trong VPC | Subnet routes của VPC | Firewall ingress/egress, OS/app |
| VM → on-premises | Route qua HA VPN/Interconnect | Đường về, BGP/static route, firewall hai phía |
| Internet → VM trực tiếp | **Không có đường public IP của VM** | Có thể vẫn có LB/proxy frontend riêng; kiểm tra cấu hình |
| Internet → Public Cloud NAT → VM | **Không hỗ trợ kết nối inbound không được khởi tạo từ VM** | NAT dùng cho egress và phản hồi luồng được phép |

**Public NAT không phải public IP gắn lên từng VM.** Cổng NAT có external IP(s) dùng để dịch địa chỉ cho những kết nối được khởi tạo từ workload đủ điều kiện; không cho người dùng Internet SSH trực tiếp tới VM.

## 3. Điều kiện chuẩn bị và giới hạn an toàn của lab

### 3.1. Tài nguyên giả định

Bài thực hành dùng những giá trị minh họa sau; hãy thay bằng ID được phép sử dụng, **không sao chép sang production**:

| Mục | Giá trị lab |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| Region | `asia-southeast1` (Singapore) |
| Zone | `asia-southeast1-a` |
| VPC | `private-lab-net` |
| Subnet | `private-lab-subnet` |
| IPv4 subnet range | `10.70.0.0/24` |
| VM | `private-app-vm` |
| Network tag | `iap-ssh` |
| Firewall rule cho IAP | `allow-iap-ssh-private-lab` |
| Cloud Router (tùy chọn) | `private-lab-router` |
| Cloud NAT (tùy chọn) | `private-lab-nat` |

Dải `10.70.0.0/24` chỉ dùng nếu **không trùng** với subnet, mạng peered hay mạng on-premises hiện có. Một project GCP có thể đã có chính sách tổ chức hạn chế tạo VPC, firewall, VM hoặc NAT. Khi đó báo người quản trị thay vì vượt policy.

### 3.2. IAM cần thiết

| Công việc | Quyền/role thường cần |
| --- | --- |
| Tạo VPC, subnet, firewall | Quyền quản trị mạng tương ứng, ví dụ `roles/compute.networkAdmin` và `roles/compute.securityAdmin` tùy tác vụ |
| Tạo VM | Quyền Compute Engine instance create và dùng subnet/disk, thường nằm trong `roles/compute.instanceAdmin.v1` hoặc vai trò tùy chỉnh |
| SSH qua IAP | `roles/iap.tunnelResourceAccessor` trên resource phù hợp, quyền đọc VM khi cần |
| Đăng nhập Linux bằng OS Login | `roles/compute.osLogin` hoặc `roles/compute.osAdminLogin` nếu cần sudo |
| Dùng service account gắn lên VM (nếu có) | `roles/iam.serviceAccountUser` trên service account và quyền tạo/gắn VM phù hợp |
| Quản lý NAT | Quyền tạo/sửa Cloud Router/NAT trong project/VPC |
| Đọc logs/metrics | Quyền Logging/Monitoring tương ứng |
| Bật APIs | `serviceusage.services.enable` và quyền project thích hợp |

**Hai lớp khác nhau:** IAP kiểm soát *ai được tạo TCP tunnel*, còn OS Login hoặc cơ chế SSH của VM kiểm soát *ai đăng nhập vào OS*. Được cấp IAP role chưa đủ nếu VM từ chối SSH. Quyền IAM còn phụ thuộc tổ chức, quyền trên service account, policy và cấu hình của project.

**Thiết kế lab với danh tính VM:** Ở ví dụ tạo VM ban đầu, sử dụng `--no-service-account --no-scopes` vì chưa chạy ứng dụng gọi Google APIs bằng danh tính máy. Khi cần truy cập Cloud Storage, có thể tạo/gắn **service account riêng** với quyền chính xác trên bucket để thử nghiệm. Tránh cấp Editor/Owner cho default service account hoặc lưu khóa JSON trên VM.

### 3.3. Chi phí và việc thay đổi hạ tầng

Các lệnh `create`, `update` và `delete` bên dưới **thực sự thay đổi tài nguyên**, được đưa ra để học và chỉ nên chạy trong sandbox được phê duyệt. Compute Engine VM, persistent disk, Public Cloud NAT, external IP của NAT, Logging và lưu lượng mạng **có thể phát sinh phí**. Không cần tạo tài nguyên nếu chỉ học lý thuyết: có thể đọc bảng/sơ đồ rồi trình bày cách kiểm chứng.

Trước khi bắt đầu:

- Có ngân sách/budget alert và thời gian thực hành được thống nhất.
- Chỉ dùng project thử nghiệm, không sửa firewall/route của ứng dụng đang chạy.
- Kiểm tra tên VPC/subnet/VM/NAT chưa bị workload khác sử dụng.
- Không chạy lệnh xóa khi chưa xác nhận **đây là tài nguyên do chính bài lab tạo**.
- Giữ log lệnh thực thi, kết quả và phương án rollback.

## 4. Bước 0 — Xác minh project, API và cấu hình CLI

Các lệnh dưới đây chỉ đọc:

~~~bash
gcloud version
gcloud auth list
gcloud config get-value project
gcloud projects describe LAB_PROJECT_ID

# Các API đã bật
gcloud services list --enabled --project=LAB_PROJECT_ID
~~~

Đặt project rõ ràng trong từng lệnh tạo tài nguyên. Nếu chưa có APIs cần thiết, người quản trị được phép có thể bật:

~~~bash
# Thao tác thay đổi project; chỉ chạy trong lab được cấp quyền
gcloud services enable compute.googleapis.com iap.googleapis.com \
  --project=LAB_PROJECT_ID
~~~

Ngoài APIs, cần billing account hợp lệ và quota cho Compute Engine. Không bật API hàng loạt nếu lab đã có đầy đủ hoặc project không thuộc phạm vi bạn quản lý.

**Kiểm tra vùng:** `asia-southeast1-a` là zone thuộc region `asia-southeast1`; firewall/VPC là tài nguyên ở phạm vi VPC, subnet/NAT là regional, VM là zonal. Dùng nhất quán region/zone để tránh “VM không thuộc subnet” hoặc “NAT ở sai region”.

## 5. Bước 1 — Tạo VPC và subnet private

Tạo **custom-mode VPC** để kiểm soát rõ subnet và CIDR:

~~~bash
gcloud compute networks create private-lab-net \
  --subnet-mode=custom \
  --project=LAB_PROJECT_ID
~~~

Tạo subnet và bật **Private Google Access** cho subnet:

~~~bash
gcloud compute networks subnets create private-lab-subnet \
  --network=private-lab-net \
  --region=asia-southeast1 \
  --range=10.70.0.0/24 \
  --enable-private-ip-google-access \
  --project=LAB_PROJECT_ID
~~~

Xác minh bằng lệnh **chỉ đọc**:

~~~bash
gcloud compute networks describe private-lab-net \
  --project=LAB_PROJECT_ID

gcloud compute networks subnets describe private-lab-subnet \
  --region=asia-southeast1 \
  --format="yaml(name,ipCidrRange,privateIpGoogleAccess,network)" \
  --project=LAB_PROJECT_ID

gcloud compute routes list \
  --project=LAB_PROJECT_ID \
  --filter="network:private-lab-net"
~~~

**Kết quả mong đợi:** VPC ở subnet mode `CUSTOM`; subnet có CIDR đã chọn; `privateIpGoogleAccess: true`; các subnet routes có thể được liệt kê. Với custom VPC theo thiết lập thông thường, có default `0.0.0.0/0` đến default Internet gateway. **Default route không tự cấp public IP cho VM**.

### 5.1. Private Google Access không có nghĩa “mở Internet”

Private Google Access cho VM **không có external IP** truy cập những Google APIs/services có địa chỉ IP được hỗ trợ. Nó là một thuộc tính **subnet**, không phải external IP hay NAT gateway.

Các điều kiện cần:

- Giao diện mạng VM ở đúng subnet đã bật Private Google Access.
- Route tới dải IP Google APIs có **next hop default internet gateway** như yêu cầu sản phẩm; dù tên next hop có từ “Internet”, lưu lượng đến Google APIs theo cơ chế này vẫn **ở trong mạng Google**.
- DNS phân giải Google APIs đúng, đặc biệt khi dùng VIP riêng.
- Firewall egress không chặn IP/port cần thiết.
- API của dịch vụ đã bật và **service account có IAM phù hợp** nếu yêu cầu dữ liệu có xác thực.

Không coi Private Google Access là đường truy cập cho bất kỳ website hay kho phần mềm nào. Một VM có thể gọi Cloud Storage API (nếu đã cấp quyền) nhưng vẫn **không tải được một tệp từ Internet tùy ý** khi chưa có NAT/proxy.

## 6. Bước 2 — Giới hạn SSH ingress chỉ từ IAP

### 6.1. Firewall ingress mặc định trong custom VPC

Trong Google Cloud VPC, các **implied firewall rules** thông thường là:

- **Deny ingress** theo mặc định nếu không có allow rule hiệu lực hơn.
- **Allow egress** theo mặc định nếu không có deny rule/policy ưu tiên cao hơn.

Đây là hành vi mạng mặc định ở tầng VPC firewall, **không đồng nghĩa** tất cả VPC đều an toàn: mạng `default` có thể chứa các rule tạo sẵn (ví dụ SSH/RDP) rộng hơn. Do đó lab dùng một **custom VPC** mới và chỉ tạo quy tắc SSH từ IAP.

### 6.2. Tạo rule SSH với nguồn IAP

Theo tài liệu IAP TCP forwarding, phạm vi IPv4 Google IAP sử dụng là **`35.235.240.0/20`**. Chỉ cho phép TCP/22 từ dải này đến VM có tag `iap-ssh`:

~~~bash
gcloud compute firewall-rules create allow-iap-ssh-private-lab \
  --network=private-lab-net \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --rules=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags=iap-ssh \
  --enable-logging \
  --project=LAB_PROJECT_ID
~~~

**Ý nghĩa từng điều kiện:**

| Trường | Giá trị lab | Mục đích |
| --- | --- | --- |
| `--direction=INGRESS` | Lưu lượng đến VM | Không thay thế egress control |
| `--source-ranges` | `35.235.240.0/20` | Chỉ cho phép kết nối từ IAP TCP forwarding ở IPv4 |
| `--rules=tcp:22` | SSH | Không mở mọi cổng |
| `--target-tags=iap-ssh` | VM lab có tag đó | Không ảnh hưởng mọi VM trong VPC |
| `--enable-logging` | Ghi log rule được khớp | Hữu ích cho quan sát, có thể có phí |

Trong production, nên xem **target service account, secure tags/firewall policies** và IAM quản lý tags, bởi tài khoản có quyền sửa VM tags có thể thay đổi tập đích của network tag. Không cấp quyền rộng để thay tag nhằm vượt qua quy tắc.

**Không tạo** rule `tcp:22` từ `0.0.0.0/0` để “sửa tạm SSH”. Với IAP, hai đầu cần kiểm tra là **IAM authorization** và **firewall từ dải IAP**, không phải mở SSH công khai.

## 7. Bước 3 — Tạo VM không có external IP

Tạo VM Linux gắn vào subnet lab:

~~~bash
# Lệnh CREATE, chỉ chạy trong sandbox đã phê duyệt
gcloud compute instances create private-app-vm \
  --zone=asia-southeast1-a \
  --machine-type=e2-micro \
  --subnet=private-lab-subnet \
  --no-address \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --tags=iap-ssh \
  --metadata=enable-oslogin=TRUE \
  --no-service-account \
  --no-scopes \
  --project=LAB_PROJECT_ID
~~~

**Các lựa chọn bảo mật chính:**

- `--no-address`: VM không được gắn external **IPv4** khi tạo.
- `--subnet`: chọn mạng private thay vì để CLI quyết định theo default.
- `--metadata=enable-oslogin=TRUE`: bật **OS Login** để quản lý đăng nhập SSH bằng IAM. Các chính sách project/tổ chức vẫn có thể áp dụng.
- `--no-service-account --no-scopes`: VM chưa có danh tính Google API để thử lab mạng; khi cần gọi Google APIs có xác thực phải dùng service account được cấp quyền tối thiểu.
- `--tags=iap-ssh`: VM thuộc mục tiêu firewall rule SSH từ IAP.
- Debian 12 và kích thước e2-micro là ví dụ; kiểm tra hỗ trợ zone, quota, chi phí và hệ điều hành doanh nghiệp yêu cầu.

**Không coi** `--no-address` là kiểm soát IPv6 tổng quát. Lab dùng subnet IPv4-only. Trong môi trường dual-stack, cần kiểm tra external IPv6 và mọi network interface để tránh bỏ sót đường public khác.

### 7.1. Kiểm chứng external IP vắng mặt

~~~bash
gcloud compute instances describe private-app-vm \
  --zone=asia-southeast1-a \
  --format="yaml(name,status,networkInterfaces,metadata.items)" \
  --project=LAB_PROJECT_ID

gcloud compute instances list \
  --filter="name=private-app-vm" \
  --format="table(name,zone,networkInterfaces[0].networkIP,networkInterfaces[0].accessConfigs[0].natIP)" \
  --project=LAB_PROJECT_ID
~~~

**Kết quả mong đợi:** Có internal IPv4 thuộc `10.70.0.0/24`; không có external NAT IP trong interface/access config. Nếu kết quả bảng rút gọn khó đọc, mở toàn bộ `networkInterfaces` trong JSON/YAML để phân biệt IP nội bộ, external IPv4 và IPv6.

### 7.2. SSH qua IAP và OS Login

Người đăng nhập cần được cấp **IAP-secured Tunnel User** và **OS Login**/OS Admin Login tương ứng. Với một số luồng CLI và quyền quản trị Compute Engine, tài liệu còn yêu cầu quyền đọc/instance admin hoặc Service Account User nếu VM có service account. Hãy kiểm tra lỗi IAM và xin đúng quyền trên resource thay vì cấp Owner.

~~~bash
# Lệnh khởi tạo kết nối SSH, không dùng external IP
gcloud compute ssh private-app-vm \
  --zone=asia-southeast1-a \
  --tunnel-through-iap \
  --project=LAB_PROJECT_ID
~~~

**Đường đi:** máy kỹ sư → IAP qua kênh mã hóa → internal IP VM:22 → SSH service trong guest OS. IAP xác thực **người tạo tunnel**; Linux OS Login/SSH xác thực **người đăng nhập hệ điều hành**. Một bước thành công không có nghĩa bước còn lại chắc chắn thành công.

Trong VM, có thể kiểm tra:

~~~bash
hostname
ip -4 addr show
ip route
whoami
~~~

Trong lab, **không** in credential, access token của metadata server hoặc private key lên terminal rồi đưa vào tài liệu. Khi đã SSH được, dùng tài khoản với đặc quyền tối thiểu, chỉ chạy sudo khi bài thực hành thật sự cần.

### 7.3. Không có external IP nhưng IAP vẫn truy cập được như thế nào?

IAP TCP forwarding dùng hạ tầng Google làm cửa vào đã xác thực và kết nối với **internal IP** của VM qua nguồn IAP được firewall cho phép. Điều này **không yêu cầu** VM có external IP hay Public NAT. Nếu VPC deny ingress từ `35.235.240.0/20` hoặc IAM không đủ, SSH vẫn thất bại.

Nếu doanh nghiệp đã có Cloud VPN hoặc Interconnect, kỹ sư có thể truy cập internal VM qua đường riêng được cấp phép thay cho IAP. Nhưng phải xem IAM, VPC firewall, guest OS và chính sách doanh nghiệp; VPN không tự cấp quyền SSH.

## 8. Bước 4 — Kiểm chứng Private Google Access, trước khi thêm NAT

Sau khi SSH vào VM, dùng các lệnh chỉ đọc và kiểm tra mạng:

~~~bash
# Xác định IP nội bộ của VM
ip -4 addr show

# Kiểm tra phân giải DNS đến dịch vụ Google
getent ahostsv4 storage.googleapis.com

# Thử kết nối HTTPS; HTTP 4xx vẫn có thể chứng minh có phản hồi mạng
curl -I --connect-timeout 8 https://storage.googleapis.com

# Thử endpoint Internet công cộng không thuộc Google API
curl -I --connect-timeout 8 https://example.com
~~~

**Cách giải thích kết quả:**

- `storage.googleapis.com` có thể trả HTTP 400/403 tùy request và auth; điều đó khác với DNS failure, timeout hoặc TLS handshake failure.
- Nếu Private Google Access, DNS, route và firewall đều đúng, VM có thể tiếp cận Google APIs được hỗ trợ **không cần NAT**; nhưng để đọc bucket riêng cần service account và IAM.
- Trước khi tạo NAT, truy cập Internet tùy ý từ VM chỉ có internal IPv4 thường **không thành công**, dù VPC có default route.
- Kết quả Internet đôi khi khác nếu tổ chức đã cấu hình proxy, Cloud NAT, Private Service Connect, gateway hoặc tuyến khác cho subnet. Hãy kiểm tra kiến trúc thực, không khẳng định timeout luôn xảy ra.

### 8.1. Kiểm tra metadata server, không tiết lộ token

VM có thể truy vấn metadata server nội bộ để đọc cấu hình cơ bản:

~~~bash
curl -sS \
  -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/name
~~~

**Không truy vấn rồi đăng công khai metadata access token**, SSH keys, thông tin nhạy cảm hoặc các tài liệu cấu hình chứa secret. Metadata server có đường mạng đặc biệt; truy cập được metadata **không phải** bằng chứng VM có Internet access.

### 8.2. Private Google Access và IAM là hai điều kiện độc lập

Một VM không có service account như lab vẫn có thể **kiểm tra kết nối HTTPS** tới API, nhưng không thể gọi thao tác Google API yêu cầu danh tính hợp lệ. Nếu muốn làm bài lab mở rộng:

1. Tạo một service account dành riêng cho VM bằng quy trình IAM của project.
2. Chỉ cấp role cần thiết, ví dụ `roles/storage.objectViewer` **trên đúng bucket thử nghiệm**.
3. Gắn service account lên VM theo quy trình được phê duyệt và chọn OAuth scope phù hợp (IAM vẫn quyết định quyền).
4. Dùng client library/CLI để đọc **một object kiểm thử không nhạy cảm**.
5. Thu hồi quyền sau lab nếu không còn cần.

Không dùng khóa service account JSON tải về máy để “sửa” thiếu quyền khi môi trường đã hỗ trợ attached service account/metadata identity.

## 9. Bước 5 — Public Cloud NAT cho kết nối Internet outbound (tùy chọn)

VM không có external IPv4 vẫn có thể cần cập nhật Debian packages, tải thư viện Maven hoặc gọi một endpoint bên thứ ba. **Public Cloud NAT** là giải pháp outbound phổ biến, không thay đổi thiết kế “VM private”.

### 9.1. Khi nào nên thêm Public NAT?

| Nhu cầu | Có cần Public NAT? | Ghi chú |
| --- | --- | --- |
| SSH quản trị qua IAP | **Không** | IAP TCP dùng internal IP của VM |
| Truy cập Google APIs có Private Google Access hợp lệ | **Không nhất thiết** | Kiểm tra API, DNS, route và IAM |
| Truy cập một VM private khác cùng VPC | **Không** | Dùng subnet route, firewall |
| Gọi API công cộng bên thứ ba | **Có thể** | Public NAT/proxy/egress gateway được phê duyệt |
| Cập nhật OS từ mirror ngoài Google | **Có thể** | Xem chính sách package mirror, proxy hoặc NAT |
| Nhận kết nối SSH tự phát từ Internet | **Không** | Public NAT không cung cấp inbound public endpoint |
| Bật dịch vụ public API thông qua external Load Balancer | **Không vì riêng LB** | Đường ingress phục vụ qua frontend LB, không qua NAT outbound |

### 9.2. Tạo Cloud Router và NAT

**Các lệnh sau tạo tài nguyên có phí.** Chỉ chạy khi nhóm đã đồng ý cung cấp Internet egress cho subnet lab:

~~~bash
gcloud compute routers create private-lab-router \
  --network=private-lab-net \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud compute routers nats create private-lab-nat \
  --router=private-lab-router \
  --region=asia-southeast1 \
  --nat-custom-subnet-ip-ranges=private-lab-subnet \
  --auto-allocate-nat-external-ips \
  --project=LAB_PROJECT_ID
~~~

Cấu hình trên chỉ chọn **primary IPv4 range của một subnet** trong region, thay vì bật NAT cho mọi subnet trong project. Trong hệ thống thật cần xem các secondary IP ranges của GKE, Cloud Run Direct VPC egress, port allocation, NAT IP pool và capacity trước khi chọn phạm vi NAT.

**Cloud Router là tài nguyên cấu hình được dùng để quản lý NAT**, không phải VM xử lý packet hay bắt buộc phải có BGP peer. Public NAT là một dịch vụ phân tán của Google Cloud; các gói không đi qua một Cloud Router VM.

### 9.3. Kiểm tra NAT và kết nối

~~~bash
# Đọc cấu hình Public NAT
gcloud compute routers nats describe private-lab-nat \
  --router=private-lab-router \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

# Xem trạng thái NAT và mapping hiện có
gcloud compute routers get-nat-mapping-info private-lab-router \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

Sau đó SSH vào VM qua IAP và thử:

~~~bash
curl -I --connect-timeout 8 https://example.com
~~~

Nếu thành công, đó là dấu hiệu outbound Internet đã hoạt động. Lưu ý phải có route phù hợp (thường `0.0.0.0/0` có next hop default Internet gateway), egress firewall cho phép, NAT đúng source IP/subnet/region và địa chỉ IP NAT đủ ports. Khi cấu hình egress deny-all, thêm NAT **không tự mở** rule firewall.

**Không nhập IP NAT vào access config của VM.** NAT external IP thuộc cổng NAT và khác external IP gắn trên NIC. Kiểm tra lại `networkInterfaces` của VM: không có external IP ngay cả khi NAT hoạt động.

### 9.4. Public NAT không phải cơ chế giới hạn đích truy cập

Một NAT gateway cho phép **dịch địa chỉ** khi route/firewall cho phép outbound; bản thân nó không phải danh sách URL cho phép. Nếu VM không có external IP nhưng egress allow-all và NAT ra Internet, mã độc trên VM vẫn có thể gọi endpoint công cộng. Muốn hạn chế exfiltration cần **egress controls**, proxy/secure web gateway, DNS policies và IAM phù hợp với yêu cầu, thay vì chỉ “cài NAT xong là an toàn”.

## 10. Kiểm soát egress: không chỉ “không có external IP”

### 10.1. Vì sao không thể chỉ dựa vào Cloud NAT?

Cloud NAT là dịch vụ dịch địa chỉ khi workload kết nối đến đích phù hợp. Nếu một VPC vẫn có quy tắc **implied allow egress**, việc thêm NAT có thể làm **nhiều đích Internet** trở nên truy cập được. Trong production, cần xác định:

- Những **đích IP/port** nào workload được gọi?
- Các Google APIs có thể đi qua **Private Google Access/PSC** mà không cần Internet tùy ý không?
- Những package dependencies có thể được tải qua mirror/proxy doanh nghiệp không?
- Có cần egress NAT IP tĩnh để đối tác allowlist không?
- Các lệnh kiểm thử cần tránh tiết lộ thông tin nào (metadata, secrets, payload, URL)?
- Ai có quyền thay firewall, tags, Cloud Router và NAT?
- Có thể phát hiện luồng outbound đến đích lạ bằng logs/monitoring không?

**Quan trọng:** VPC firewall rules hoạt động chủ yếu trên các thuộc tính mạng như IP, protocol và port; nó **không cung cấp kiểm soát website/domain ở lớp HTTP** như một secure web proxy. Cho phép TCP/443 tới `0.0.0.0/0` vẫn rất rộng.

### 10.2. Egress allowlist: thứ tự ưu tiên rule

Nếu tổ chức áp dụng **deny-all egress** cho một nhóm VM, cần tạo rule **allow cụ thể có priority cao hơn** (số priority thấp hơn) cho các luồng bắt buộc. Ví dụ lý luận:

| Egress rule | Priority | Destination | Protocol | Kết quả |
| --- | ---: | --- | --- | --- |
| Allow đến dịch vụ Google APIs được phê duyệt | 900 | Dải IP/VIP theo thiết kế | TCP/443 | Cho phép các kết nối khớp |
| Allow kết nối nội bộ đến DB | 900 | Dải DB private cụ thể | TCP/5432 | Cho phép theo nhu cầu nghiệp vụ |
| Deny outbound khác | 1000 | `0.0.0.0/0` | All | Chặn các luồng không được phép |

**Đây là sơ đồ policy, không phải script áp dụng ngay.** Trước khi tạo rule thật cần kiểm tra traffic DNS, metadata server, monitoring agent, patching, certificate retrieval, LB health, logging, các policy cấp tổ chức và những dependency bắt buộc. Một deny-all áp dụng nhầm có thể làm workload mất khả năng khởi động/khôi phục.

Khi dùng Private Google Access với `private.googleapis.com` hoặc `restricted.googleapis.com`, IP đích và DNS mapping phải tuân theo hướng dẫn Google; đừng lấy một IP bất kỳ rồi ghi vào rule. Nếu có nhu cầu Zero Trust ở mức đích/URL hay kiểm soát rò rỉ dữ liệu, cần kiến trúc bổ sung được tổ chức phê duyệt.

### 10.3. VPC firewall, hierarchical firewall và IAM

Cần phân biệt:

1. **VPC firewall rules**: kiểm soát ingress/egress với VM network interfaces theo nguồn, đích, protocol/port và target.
2. **Hierarchical firewall policies / network firewall policies**: chính sách có thể kế thừa từ organization/folder hoặc áp dụng ở phạm vi mạng; kiểm tra thứ tự đánh giá và những rule do đội trung tâm quản lý.
3. **IAM**: kiểm soát *ai được tạo/sửa tài nguyên* hoặc *ai được gọi Google API*; IAM không thay thế firewall mạng cho mọi kết nối TCP.
4. **OS/app authentication**: ví dụ SSH bằng OS Login, database credential/IAM DB auth, OAuth/JWT cho API.
5. **VPC Service Controls**: bảo vệ ranh giới truy cập một tập Google managed services được hỗ trợ; không phải một firewall cho mọi địa chỉ Internet.

Trong sự cố, một firewall allow rule của project có thể bị **policy cấp cao hơn** chặn. Không tự thêm rule mở rộng trước khi hiểu thứ tự các policy hiện hành.

### 10.4. Organization Policy hạn chế VM external IP

Google Cloud cung cấp organization policy constraint:

~~~text
constraints/compute.vmExternalIpAccess
~~~

Có thể giới hạn việc gắn external IP lên VM ở phạm vi được quản trị. Đây là biện pháp **phòng ngừa cấu hình sai cho tài nguyên về sau**, nhưng cần nhớ:

- Chính sách không tự gỡ external IP của VM đã có trước khi áp dụng.
- Áp dụng lên tài nguyên VM thuộc phạm vi project/org policy; cũng có thể tác động GKE nodes, managed instance groups hoặc dịch vụ dựa trên VM ở project đó.
- Nếu rollout mà chưa kiểm tra autoscaling và autohealing, có thể làm MIG/GKE không tạo thêm instance.
- Trong Shared VPC, việc đặt constraint ở host project **không tự áp lên VM của service projects** khác.
- Vẫn cần kiểm soát load balancers, external IPv6, các public endpoints của sản phẩm khác và IAM.

Policy này cần được thiết kế cùng đội tổ chức/security, triển khai có thử nghiệm và rollback. **Không bật đại trà trong lab** để tránh ảnh hưởng ngoài phạm vi bài.

## 11. Các đường truy cập private đến dịch vụ Google Cloud

Không phải mọi sản phẩm có chữ “private” đều dùng cùng một cơ chế. Cần phân biệt **truy cập Google APIs** với **truy cập một dịch vụ có private IP**.

| Cơ chế | Đích đến | Thường dùng với | Điều kiện chính |
| --- | --- | --- | --- |
| **Private Google Access (PGA)** | Địa chỉ của các Google APIs/services hỗ trợ trên hạ tầng Google | VM không external IP gọi Cloud Storage, Secret Manager, một số APIs | Bật theo subnet, DNS/route/firewall, IAM |
| **Private Service Connect (PSC) for Google APIs** | Endpoint có **internal IP** trong VPC trỏ tới bộ APIs được hỗ trợ | Muốn kiểm soát đường truy cập APIs qua endpoint VPC | Tạo endpoint/forwarding rule, DNS, bundle `all-apis`/`vpc-sc`, IAM |
| **Private services access (PSA)** | Dịch vụ managed chạy trong mạng producer được kết nối theo cơ chế riêng | Một số cấu hình Cloud SQL private IP và dịch vụ managed | Địa chỉ IP được cấp, service networking connection, IAM |
| **PSC to managed service** | Endpoint private để truy cập service producer được hỗ trợ | Cloud SQL PSC, dịch vụ được publish qua PSC | Service attachment/endpoint, DNS, quyền, cấu hình service |
| **Cloud VPN / Interconnect** | Private IP ở mạng on-premises/hybrid | DB/ERP nội bộ, hệ thống dữ liệu | Route hai chiều, BGP/tunnel/circuit, firewall |
| **Public Cloud NAT** | Đích Internet qua NAT IP | Cập nhật OS, API bên thứ ba | Đúng subnet/region, route, egress allow |

Một VM **không có external IP** có thể dùng nhiều cơ chế trong bảng, tùy từng **địa chỉ đích**. Việc một luồng dùng PGA không có nghĩa luồng khác đến Cloud SQL private IP tự đi qua PGA.

### 11.1. Google APIs với default domain, private và restricted VIPs

Google cung cấp nhiều cách kết nối đến `googleapis.com`. Hai VIP hay gặp trong thiết kế private:

| Tên | IPv4 VIP range | Ý nghĩa |
| --- | --- | --- |
| `private.googleapis.com` | `199.36.153.8/30` | Truy cập hầu hết Google APIs/services được hỗ trợ, kể cả dịch vụ không hỗ trợ VPC Service Controls |
| `restricted.googleapis.com` | `199.36.153.4/30` | Chỉ cho những APIs/services có hỗ trợ VPC Service Controls |

Để sử dụng VIPs, cần **cấu hình DNS** mapping domain cần dùng, **routes** đến các dải Google APIs, và **egress firewall** phù hợp theo hướng dẫn. Việc bật PGA ở subnet **không tự thiết lập tất cả DNS records** cho hai VIP này.

Một số dịch vụ có tên miền khác như `pkg.dev`, `*.run.app` hoặc Artifact Registry có thể yêu cầu cấu hình DNS bổ sung tùy cách truy cập. Lưu ý hai VIPs hỗ trợ những giao thức/endpoint có điều kiện, không coi chúng là đường truyền thay thế Internet cho mọi website. Đặc biệt `restricted.googleapis.com` không cung cấp mọi Google API, nên dùng sai có thể gây lỗi ứng dụng.

**Đường đến Google APIs qua PGA yêu cầu next hop default internet gateway**, nhưng gói theo dịch vụ được hỗ trợ **không cần đi ra Internet công cộng**. Kiểm tra route và firewall khi thiết lập egress policy tùy chỉnh.

### 11.2. IAM của service account là điểm kiểm soát độc lập

Ví dụ VM Java cần tải một object trên Cloud Storage:

~~~mermaid
flowchart LR
    APP["Ứng dụng Java trên VM\nkhông external IP"] --> NET["PGA/PSC và network policy"]
    NET --> API["Cloud Storage API"]
    ID["Attached service account"] -. "Token qua metadata server" .-> APP
    API --> IAM["IAM kiểm tra quyền với bucket/object"]
    IAM --> OBJ["Object được phép đọc"]
~~~

Có đường mạng tới API **không** mang lại quyền đọc object. Nếu VM dùng service account bị cấp quyền quá rộng, dữ liệu vẫn có nguy cơ bị truy cập khi ứng dụng bị khai thác. Chỉ cấp `roles/storage.objectViewer` hoặc role nhỏ hơn thích hợp trên đúng tài nguyên; xem IAM Conditions, VPC Service Controls và quy định dữ liệu khi cần.

### 11.3. Cloud SQL private IP và managed services

Cloud SQL có thể dùng private connectivity, nhưng luồng kết nối DB qua **private IP** sử dụng cơ chế như **Private Services Access** hoặc **Private Service Connect** tùy cấu hình, **không phải** Private Google Access thông thường.

Cần kiểm tra riêng:

- Cloud SQL instance có còn **public IPv4** không? Một instance có private IP vẫn có thể có public IP nếu cấu hình cho phép.
- Application VM/GKE/Cloud Run có đường mạng đến private endpoint và DNS đúng không?
- DB user/IAM DB authentication, TLS, secret và network policy có phù hợp?
- Có thể dùng Cloud SQL connector/proxy theo phương thức được hỗ trợ, nhưng **đừng mặc định** connector tự giải quyết private route khi client không có kết nối VPC.
- Có được phép dùng PSC/private services access qua Shared VPC và VPC peering theo thiết kế không?

Nếu tổ chức muốn hạn chế Cloud SQL public IP, Google có các **organization policies** khác với `compute.vmExternalIpAccess`, ví dụ `constraints/sql.restrictPublicIp`. Không suy constraint dành cho Compute Engine áp dụng cho mọi managed database.

## 12. Mở rộng nguyên tắc sang GKE và Cloud Run

### 12.1. GKE: private nodes và điều khiển cluster

Với **GKE private nodes**, node VMs có internal IP và không được gắn external IP theo cấu hình. Nhưng thiết kế GKE còn cần:

- **Control plane endpoint:** có thể sử dụng DNS-based access hoặc private endpoint tùy loại cluster/chế độ cấu hình; việc node private **không tự chứng minh control plane chỉ truy cập nội bộ**.
- **Node ↔ Google APIs/Artifact Registry:** cần Private Google Access, Cloud NAT hoặc phương án truy cập private phù hợp.
- **Node/pod egress:** cần xem IP alias ranges, phạm vi NAT bao gồm primary/secondary ranges, Kubernetes NetworkPolicy nếu được hỗ trợ và firewall ở VPC.
- **Services ingress:** GKE có thể tạo external load balancer cho Service/Ingress dù node không có external IP.
- **Identity:** Workload Identity Federation for GKE (nếu dùng) giúp pod nhận danh tính phù hợp mà không chia sẻ khóa JSON; IAM phải giới hạn theo workload.
- **Control plane to nodes, health checks và quản trị:** không áp dụng deny-all mù quáng cho mọi subnet hoặc node tags.

Vì vậy, **private GKE nodes ≠ private GKE cluster endpoint ≠ không có public Service**. Ba ý này cần được kiểm tra độc lập.

Lệnh chỉ đọc gợi ý:

~~~bash
gcloud container clusters list --project=PROJECT_ID

gcloud container clusters describe CLUSTER_NAME \
  --location=CLUSTER_LOCATION \
  --project=PROJECT_ID \
  --format="yaml(privateClusterConfig,networkConfig,masterAuthorizedNetworksConfig,endpoint)"
~~~

Trường hiện ra có thể khác giữa GKE Standard/Autopilot, chế độ tạo cluster và phiên bản API. Luôn kiểm tra phần endpoint settings hiện hành trong Console, không chỉ dựa một thuộc tính cũ.

### 12.2. Cloud Run: không có VM public IP không đồng nghĩa endpoint private

Cloud Run là dịch vụ serverless và người dùng không trực tiếp quản một VM NIC có public IP như Compute Engine. Tuy nhiên, một **Cloud Run service theo mặc định có endpoint `run.app` và ingress cho phép nguồn Internet đến service**, trong khi IAM authentication vẫn có thể chặn lời gọi chưa được cấp quyền.

Để tạo dịch vụ **nội bộ**:

- Cấu hình **ingress = internal** nếu chỉ cho các nguồn được Cloud Run coi là internal.
- Hoặc **internal and Cloud Load Balancing** khi cần đường qua load balancer công khai có kiểm soát Cloud Armor/IAP.
- Kiểm soát **Invoker IAM** / yêu cầu authentication; việc đổi ingress không thay thế authentication.
- Có thể **vô hiệu hóa default `run.app` URL** nếu kiến trúc và các dịch vụ tích hợp không phụ thuộc URL này. Việc tắt URL mặc định có thể ảnh hưởng Cloud Scheduler, Eventarc, Pub/Sub và các trigger khác.
- Định nghĩa **outbound VPC connectivity** riêng: Direct VPC egress hoặc connector được hỗ trợ để gọi DB/private VPC.

Ví dụ **thay đổi trên dịch vụ đã có**, chỉ dùng khi đã được cho phép:

~~~bash
# Thay đổi cấu hình ingress, không tạo một service mới
gcloud run services update SERVICE_NAME \
  --region=REGION \
  --ingress=internal \
  --project=PROJECT_ID
~~~

Một dịch vụ đã ingress internal vẫn cần IAM và có thể cần VPC setup để client nội bộ thực sự gọi được. **Không dùng `--allow-unauthenticated`** trong lab production chỉ để “sửa” lỗi 403 nếu chưa hiểu tài khoản caller.

Nếu Cloud Run cần ra Internet **qua Public NAT của VPC**, với **Direct VPC egress**, tài liệu yêu cầu định tuyến `all-traffic` và NAT đúng source subnet. Lựa chọn `private-ranges-only` không định tuyến mọi lưu lượng Internet qua NAT trong VPC. Một mẫu cấu hình có thể là:

~~~text
Cloud Run egress (Direct VPC):
  VPC network: private-lab-net
  Subnet:       private-lab-subnet (đúng region)
  Egress:       all-traffic
  NAT:          đúng subnet và endpoint capacity
  Firewall:     cho phép đích thật sự cần
~~~

Đừng nhầm **ingress controls** (ai được gọi Cloud Run) với **egress controls** (Cloud Run có thể gọi đích nào).

### 12.3. Tài nguyên công khai khác có thể tồn tại phía trước

Một hệ thống có thể dùng:

~~~text
Internet
   ↓
External Application Load Balancer (public frontend)
   ↓
Backend VM/GKE/Cloud Run không gắn external IPv4
   ↓
Cloud SQL private endpoint
~~~

Đây **không phải** “hệ thống không có bất kỳ điểm public nào”. Nó có public frontend chủ động phục vụ request, nhưng backend private được bảo vệ bằng network rules, authentication và web protection. Cách dùng Cloud Armor, TLS certificate, CDN, IAP for HTTP(S) và load balancer health checks phụ thuộc loại frontend.

**Không sử dụng Public Cloud NAT để xuất bản website**. NAT dành cho các kết nối outbound được hỗ trợ; public ingress cần load balancer/proxy và kiểm soát ứng dụng phù hợp.

## 13. Giám sát, kiểm chứng và chẩn đoán

### 13.1. Bộ lệnh read-only từ máy quản trị

~~~bash
# VM và các giao diện mạng
gcloud compute instances describe private-app-vm \
  --zone=asia-southeast1-a \
  --format="json(networkInterfaces,serviceAccounts,metadata)" \
  --project=LAB_PROJECT_ID

# Subnet có bật Private Google Access không?
gcloud compute networks subnets describe private-lab-subnet \
  --region=asia-southeast1 \
  --format="value(privateIpGoogleAccess)" \
  --project=LAB_PROJECT_ID

# Firewall rules liên quan lab
gcloud compute firewall-rules list \
  --filter="network:private-lab-net" \
  --project=LAB_PROJECT_ID

# Route VPC
gcloud compute routes list \
  --filter="network:private-lab-net" \
  --project=LAB_PROJECT_ID

# NAT (nếu đã tạo)
gcloud compute routers nats describe private-lab-nat \
  --router=private-lab-router \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

Nếu `firewall-rules list` không cho thấy hierarchical firewall policies, cần xem các policy có hiệu lực qua Console hoặc công cụ chuyên biệt. Không kết luận không có deny khi một câu lệnh chỉ liệt kê VPC firewall rules.

### 13.2. Công cụ quan sát hữu ích

| Công cụ | Quan sát được | Giới hạn cần nhớ |
| --- | --- | --- |
| **VPC Flow Logs** | Metadata các luồng của subnet/endpoint được hỗ trợ | Sampling/aggregation; không phải packet capture đầy đủ |
| **Firewall Rules Logging** | Luồng khớp những rule được bật logging | Chỉ log theo rule và cơ chế hỗ trợ |
| **Cloud NAT Logs/Metrics** | Kết nối NAT, errors/drops/port allocation tùy cấu hình | Có thể chưa bật logs; phí log và giới hạn dữ liệu |
| **Cloud Audit Logs** | Ai thay network/firewall/VM/Org Policy | Cấu hình data access logging và quyền xem có thể khác |
| **Network Intelligence Center – Connectivity Tests** | Phân tích cấu hình đường đi, firewall, next hops | Có API/IAM riêng; không thay thế mọi phép đo end-to-end |
| **Cloud Monitoring** | VM uptime, CPU, NAT/network metrics, alerting | Cần metric phù hợp, dashboard không tự bảo vệ tài nguyên |
| **OS Login / IAP audit data** | Danh tính quản trị và hoạt động truy cập được ghi nhận | Cần kiểm tra phạm vi audit, retention và chính sách logging |

Khi bắt đầu lab, firewall rule cho IAP đã bật logging. **Cloud NAT logging cần cấu hình riêng** nếu muốn thấy các log NAT; không suy rằng tạo NAT mặc định có đầy đủ log từng kết nối.

### 13.3. Bảng xử lý sự cố

| Triệu chứng | Khả năng | Cách kiểm tra |
| --- | --- | --- |
| `gcloud compute ssh` báo `Permission denied` | Thiếu role IAP, OS Login hoặc quyền Compute Engine/service account | Kiểm tra user đang active, IAM policy và OS Login metadata |
| SSH qua IAP bị timeout | Thiếu firewall ingress từ `35.235.240.0/20`, sshd không chạy hoặc VM lỗi | Kiểm tra firewall target tags, VM health, port 22 và IAP |
| SSH hoạt động khi VM có public IP nhưng không hoạt động khi bỏ IP | Tool đang SSH trực tiếp, chưa dùng `--tunnel-through-iap` | Kiểm tra IAP role/firewall và đường kết nối |
| VM có IP ngoài dù đã nghĩ là “private” | Tạo VM không dùng `--no-address`, nhiều NIC hoặc external IPv6 | Xem toàn bộ `networkInterfaces`/accessConfigs |
| `curl storage.googleapis.com` timeout trước NAT | PGA chưa bật, route/DNS/firewall sai hoặc Google API không được hỗ trợ | Xem `privateIpGoogleAccess`, DNS và next hop |
| Google API trả 403 | Network đi được nhưng IAM/token/bucket permission sai | Kiểm tra service account, OAuth scopes và IAM |
| Package update từ internet thất bại | Không có NAT/proxy, route, DNS hoặc egress bị deny | Kiểm tra NAT subnet/region, default route, log và proxy |
| NAT đã tạo mà Internet vẫn timeout | VM không nằm trong NAT source ranges, sai region, port exhaustion, firewall | Xem NAT config/mapping/logs, route `0.0.0.0/0` |
| VM vẫn truy cập Internet dù không external IP | Có NAT, proxy hoặc egress gateway được cấu hình | Kiểm tra kiến trúc outbound; đây không nhất thiết là lỗi |
| VM private bị truy cập từ ứng dụng ngoài | External load balancer/proxy/VPN/Peering hoặc firewall private đang cho phép | Truy vết ingress frontend và resource thực tế |
| Cloud SQL private IP không kết nối được | PSA/PSC chưa đúng, route/firewall, DB auth hoặc DNS | Kiểm tra Cloud SQL network configuration và IAM DB |
| Cloud Run có thể gọi từ Internet | Ingress `all` hoặc frontend public có chủ đích; auth có thể khác | Kiểm tra ingress và Invoker IAM, không suy từ IP của container |
| GKE node không tải được container image | NAT/PGA, DNS `pkg.dev`, registry IAM, node scope hoặc policy | Kiểm tra từng tầng: DNS, network, auth, repository |
| Log không thấy luồng | Logging chưa bật, sampling, policy khác hoặc data mới chưa có | Xem cấu hình Logging và metric tương ứng |

### 13.4. Chẩn đoán theo tầng, không sửa bừa cấu hình

~~~mermaid
flowchart TD
    START["Workload private báo lỗi kết nối"] --> SRC["Xác định nguồn, đích, IP, protocol, port"]
    SRC --> ADDR{"VM có external IP ngoài ý muốn?"}
    ADDR -- "Có" --> FIX["Kiểm tra yêu cầu và thay đổi có kiểm soát"]
    ADDR -- "Không" --> INOUT{"Ingress hay egress?"}
    INOUT -- "Ingress SSH" --> IAP["Kiểm tra IAP IAM + OS Login + firewall TCP22"]
    INOUT -- "Google API" --> PGA["Kiểm tra PGA, DNS, route, IAM"]
    INOUT -- "Internet outbound" --> NAT["Kiểm tra NAT source subnet/region, route, egress"]
    INOUT -- "Private service" --> PSC["Kiểm tra private IP, PSA/PSC, DNS và app auth"]
    IAP --> FINAL["Đo lại từ đúng client và đọc logs"]
    PGA --> FINAL
    NAT --> FINAL
    PSC --> FINAL
    FIX --> FINAL
~~~

**Quy tắc an toàn:** Khi một API trả `403`, không nên mở firewall `0.0.0.0/0` ngay; có thể đường mạng đã hoạt động nhưng thiếu IAM. Khi có timeout, không nên cấp Owner ngay; có thể routing hoặc firewall đang chặn. Phân biệt network, authentication, authorization và ứng dụng.

## 14. Bảng kiểm chứng lab có thể chấm điểm

Sau khi thực hiện, ghi kết quả thực tế vào bảng:

| Kiểm tra | Cách xác minh | Kết quả mong đợi |
| --- | --- | --- |
| VM không có external IPv4 | `gcloud compute instances describe` | Internal IPv4 tồn tại; `accessConfigs` không có external NAT IP |
| SSH không mở trực tiếp trên Internet | Firewall rule + VM interface | Không có public VM IP; không có rule mở SSH rộng |
| SSH qua IAP | `gcloud compute ssh --tunnel-through-iap` | Chỉ người có IAM + OS Login đăng nhập được |
| PGA trên subnet | `gcloud compute networks subnets describe` | `privateIpGoogleAccess=true` |
| Google API reachability | DNS + HTTPS đến API được hỗ trợ | Có phản hồi mạng, auth tùy IAM |
| VM truy cập Internet trước NAT | `curl` website công khai | Thường không đi được trong custom VPC lab chưa có egress |
| VM truy cập Internet sau NAT | Cấu hình NAT + `curl` | Nếu route/firewall cho phép, outbound thành công |
| VM vẫn không có external IP sau NAT | Describe networkInterfaces | External IP trên VM vẫn không xuất hiện |
| Firewall rule đúng nguồn | Describe `allow-iap-ssh-private-lab` | Chỉ nguồn IAP và đích tag lab TCP:22 |
| IAM không quá rộng | Xem IAM grants | Không cần Owner/Editor cho người thử nghiệm hoặc VM |
| Logs | Logs/Monitoring trong phạm vi bật | Có chứng cứ SSH/IAP và điều tra mạng |
| Dọn tài nguyên | List VM/VPC/router/NAT và chi phí | Không còn tài nguyên của bài lab, không đụng tài nguyên khác |

**Tình huống kiểm thử bảo mật:** Một người không có IAP role thử SSH phải bị từ chối ở lớp IAP, dù firewall cho phép dải IAP. Người đã có IAP role nhưng không có OS Login cũng không được đăng nhập Linux. Đây là minh chứng **defense in depth**, không chỉ “ẩn địa chỉ IP”.

## 15. Dọn tài nguyên sau thực hành

**Chỉ xóa tài nguyên đúng tên đã được tạo bởi bài lab và không có người khác sử dụng.** Các lệnh sau có tác động phá hủy; không chạy trên production và không dùng wildcard.

Trước khi xóa, kiểm tra:

~~~bash
gcloud compute instances list \
  --filter="name=private-app-vm" --project=LAB_PROJECT_ID

gcloud compute routers list \
  --filter="name=private-lab-router" --project=LAB_PROJECT_ID

gcloud compute networks list \
  --filter="name=private-lab-net" --project=LAB_PROJECT_ID
~~~

Nếu **đã tạo Public NAT** trong phần tùy chọn, xóa NAT trước khi xóa Cloud Router:

~~~bash
gcloud compute routers nats delete private-lab-nat \
  --router=private-lab-router \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud compute routers delete private-lab-router \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

Xóa VM (nên kiểm tra persistent disk, snapshot, reserved IP, backup trước khi xác nhận):

~~~bash
gcloud compute instances delete private-app-vm \
  --zone=asia-southeast1-a \
  --project=LAB_PROJECT_ID
~~~

Sau khi chắc chắn không còn VM hoặc tài nguyên nào sử dụng firewall/subnet, xóa đúng rule, subnet và VPC do lab tạo:

~~~bash
gcloud compute firewall-rules delete allow-iap-ssh-private-lab \
  --project=LAB_PROJECT_ID

gcloud compute networks subnets delete private-lab-subnet \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud compute networks delete private-lab-net \
  --project=LAB_PROJECT_ID
~~~

Lệnh xóa sẽ yêu cầu xác nhận. Nếu không tạo NAT thì **bỏ qua các lệnh xóa NAT/router**. Nếu có tài nguyên khác đã dùng mạng lab, **không cố xóa cưỡng ép**; điều tra quyền sở hữu và liên hệ người quản trị.

**Kiểm tra chi phí còn sót:** VM đã xóa không có nghĩa mọi persistent disk/snapshot, log, image, reserved external IP của NAT hoặc dịch vụ phụ trợ đều đã dọn sạch. Dùng Billing Reports/Budgets và danh sách tài nguyên để xác minh. Không xóa toàn bộ project nếu project chứa công việc khác.

## 16. Tình huống mở rộng: công ty cần API public nhưng không để lộ backend

Một công ty triển khai website đặt hàng:

~~~mermaid
flowchart LR
  U["Người dùng Internet"] --> ALB["External Application Load Balancer"]
  ALB --> WAF["Cloud Armor / IAP nếu áp dụng"]
  WAF --> API["Backend Cloud Run hoặc GKE\nkhông public IP trên node"]
  API --> DB["Cloud SQL private endpoint"]
  API --> LOG["Cloud Logging/Monitoring"]
  DEV["Kỹ sư"] --> IAP["IAP TCP forwarding"] --> VM["Compute Engine worker\nkhông external IP"]
  VM --> NAT["Public Cloud NAT cho outbound khi cần"]
~~~

Mục tiêu của kiến trúc này không phải **loại bỏ mọi IP công khai**: ứng dụng vẫn có một public frontend phục vụ khách hàng. Nhưng **backend worker/DB** không cần lộ trực tiếp. Những ranh giới quan trọng:

1. **Public frontend**: TLS, authentication, DDoS/WAF protection và hạn chế đường bypass đến backend.
2. **Private workload network**: chỉ các source được phép gọi backend, route và egress có kiểm soát.
3. **Data plane**: DB private, IAM/credential và encryption phù hợp.
4. **Management plane**: IAP/OS Login, IAM role tối thiểu, audit logs.
5. **Outbound**: PGA/PSC cho Google APIs; NAT/proxy cho Internet được phê duyệt.
6. **Reliability**: health checks, retry, autoscaling, monitoring và rollout an toàn.
7. **Cost**: firewall logs, Cloud NAT, private endpoints, load balancer, egress, monitoring.

**Ví dụ quyết định kỹ thuật:** “Tắt external IP trên worker VM” là một yêu cầu rõ, nhưng **không đủ để chứng minh dữ liệu không bị xuất ra ngoài** nếu worker vẫn có quyền IAM đọc mọi bucket và egress Internet không bị kiểm soát. Giải pháp phải phối hợp network policy, service identity, quyền dữ liệu, logs và quy trình phê duyệt thay đổi.

## 17. Câu hỏi ôn tập và đáp án định hướng

1. **VM không có external IP có thể SSH qua IAP không?** Có, nếu IAP IAM, OS Login/SSH và firewall cho nguồn IAP được cấu hình đúng.
2. **Vì sao không mở TCP/22 từ 0.0.0.0/0?** Làm rộng nguồn mạng được phép thử kết nối, không phù hợp mục tiêu giảm exposure.
3. **Vì sao Private Google Access không giống Cloud NAT?** PGA dành cho Google APIs/services được hỗ trợ; NAT dùng dịch địa chỉ cho outbound phù hợp, thường tới Internet.
4. **Thêm NAT có khiến VM sở hữu public IP?** Không, external IP được dùng ở NAT gateway, không gắn vào VM NIC.
5. **NAT có cho phép Internet SSH ngược vào private VM?** Không cho kết nối inbound không do workload khởi tạo.
6. **PGA có tự cấp IAM đọc Cloud Storage không?** Không. Network reachability và resource authorization là hai lớp độc lập.
7. **Tại sao cloud VM không có external IP vẫn có thể bị khai thác?** Có thể truy cập qua private VPC/VPN/LB, service account quá quyền hoặc ứng dụng có lỗ hổng.
8. **Cloud Run không có VM public IP có mặc nhiên private không?** Không; phải xem ingress, run.app URL, load balancer frontend và Invoker IAM.
9. **GKE private nodes có nghĩa Service LoadBalancer không thể public?** Không, public frontend vẫn có thể được tạo nếu cấu hình cho phép.
10. **Cloud SQL private IP có dùng Private Google Access không?** Không theo cơ chế thông thường; cần PSA/PSC và đường network của dịch vụ.
11. **Vì sao egress allow-all + Public NAT chưa phải zero trust?** Vì workload vẫn có thể gọi nhiều đích Internet; cần policy và data access control.
12. **Khi 403 xuất hiện, cần thêm firewall allow không?** Chưa chắc; đó thường là lỗi IAM/auth, phải kiểm tra tầng network riêng.
13. **IAP role và OS Login role có tương đương nhau không?** Không; một cái cho tunnel, một cái cho login OS.
14. **Constraint cấm VM external IP có gỡ địa chỉ đã tồn tại không?** Không áp dụng hồi tố theo tài liệu; cần xử lý từng tài nguyên cũ.
15. **Khi dọn lab, có nên xóa nguyên project không?** Không nếu có tài nguyên/nhóm khác; chỉ xóa đúng tài nguyên lab đã kiểm chứng.

## 18. Checklist an toàn trước khi dùng mô hình cho production

- [ ] Đã phân loại workload: internal-only, public frontend/private backend, hay hybrid.
- [ ] Không có external IPv4/IPv6/NIC không mong muốn; đã kiểm tra mọi interface.
- [ ] Đã rà soát public frontends, Cloud Run ingress, GKE Services/Ingress và Cloud SQL public IP.
- [ ] IAP, OS Login và IAM quản trị chỉ cấp cho đúng nhóm/người/tài nguyên.
- [ ] Firewall ingress/egress và hierarchical policies theo nguyên tắc least privilege.
- [ ] Private Google Access/PSC/PSA được chọn đúng theo loại Google API hoặc managed service.
- [ ] Cloud NAT chỉ phục vụ subnets/regions/sources cần thiết, không dùng làm firewall.
- [ ] Service accounts có quyền tối thiểu; không sử dụng khóa JSON không cần thiết.
- [ ] Có logging/monitoring, audit trail và cảnh báo thay đổi network/IAM.
- [ ] Có test từ nguồn/đích thật, kiểm tra DNS, route, firewall, IAM, TLS và ứng dụng.
- [ ] Có kế hoạch patching an toàn cho VM private không có Internet tự do.
- [ ] Có budget cho VM, disk, NAT, logs, egress và endpoints.
- [ ] Có rollback và runbook khi IAP/NAT/Private Google Access không hoạt động.

## 19. Tài liệu chính thức của Google Cloud

Các trang dưới đây nên được kiểm tra khi triển khai thực tế vì loại endpoint, vai trò IAM, lệnh CLI, IPv6 và yêu cầu bảo mật có thể thay đổi:

- [Connect to Linux VMs using IAP](https://docs.cloud.google.com/compute/docs/connect/ssh-using-iap) — SSH đến VM không có external IP.
- [Use IAP for TCP forwarding](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding) — dải nguồn IAP, firewall, IAM.
- [Configure OS Login](https://docs.cloud.google.com/compute/docs/oslogin/set-up-oslogin) — IAM và đăng nhập Linux.
- [VPC firewall rules](https://docs.cloud.google.com/firewall/docs/firewalls) — implied rules, priorities và phạm vi.
- [Private Google Access overview](https://docs.cloud.google.com/vpc/docs/private-google-access) — điều kiện truy cập APIs từ VM private.
- [Configure Private Google Access](https://docs.cloud.google.com/vpc/docs/configure-private-google-access) — subnet, DNS, routes, `private.googleapis.com`/`restricted.googleapis.com`.
- [Private access options for services](https://docs.cloud.google.com/vpc/docs/private-access-options) — PGA, PSC, private services access.
- [Public Cloud NAT overview](https://docs.cloud.google.com/nat/docs/public-nat) — NAT outbound và các giới hạn.
- [Set up Public NAT](https://docs.cloud.google.com/nat/docs/set-up-manage-network-address-translation) — Cloud Router và NAT gateway.
- [Compute Engine: create VMs](https://docs.cloud.google.com/compute/docs/instances/create-start-instance) — VM private và network interfaces.
- [Restrict VM external IP with organization policy](https://docs.cloud.google.com/compute/docs/ip-addresses/configure-static-external-ip-address#restrict_external_ip_addresses_to_specific_instances) — constraint `compute.vmExternalIpAccess`.
- [GKE private clusters](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/private-cluster-concept) — private nodes và control plane access.
- [Cloud Run ingress](https://docs.cloud.google.com/run/docs/securing/ingress) — internal vs external ingress và default URL.
- [Cloud Run Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc) — all-traffic, private-ranges-only.
- [Cloud NAT interactions with Cloud Run](https://docs.cloud.google.com/nat/docs/nat-product-interactions) — nguồn NAT với Direct VPC egress.
- [Cloud SQL private IP](https://docs.cloud.google.com/sql/docs/mysql/configure-private-ip) — private connectivity của managed database.
- [VPC Flow Logs](https://docs.cloud.google.com/vpc/docs/flow-logs) — network flow metadata.
- [Connectivity Tests](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) — mô phỏng đường đi và kiểm tra cấu hình.

**Điểm cốt lõi:** **VM không có external IP chỉ là lớp phòng vệ đầu tiên.** Một workload thực sự được bảo vệ phải có **đường vào được xác thực (IAP hoặc frontend kiểm soát), đường ra tối thiểu (PGA/PSC/NAT có kiểm soát), IAM/service identity đúng phạm vi, firewall phù hợp và khả năng quan sát**. Hãy kiểm chứng từng luồng theo nguồn–đích, quyền và trạng thái ứng dụng, thay vì dùng sự vắng mặt của public IP làm bằng chứng duy nhất.
