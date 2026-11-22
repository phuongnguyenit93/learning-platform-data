# Thực hành xây dựng VPC riêng cho ứng dụng nhiều tầng

Trong module **CLOUD_PROVIDERS_GCP**, chúng ta sử dụng Google Cloud để tổ chức project, bảo vệ tài nguyên bằng IAM và VPC, triển khai dịch vụ trên Compute Engine, GKE hoặc Cloud Run, lưu dữ liệu, tự động hóa phát hành và theo dõi độ tin cậy lẫn chi phí. Bài thực hành thuộc chương **VPC và định tuyến** này xây dựng một mạng **Virtual Private Cloud (VPC) riêng**, rồi đặt ba tầng ứng dụng vào những subnet khác nhau để kiểm chứng đường đi của lưu lượng và giới hạn truy cập.

Thay vì chỉ vẽ sơ đồ, bạn sẽ tạo VPC custom mode, ba subnet regional, quy tắc firewall, Cloud NAT, ba VM và các dịch vụ HTTP nhỏ. Sau đó, bạn thử cả những kết nối **được phép** và **bị từ chối**, kiểm tra cấu hình bằng gcloud và dọn tài nguyên để tránh phí ngoài dự kiến.

> **Phạm vi lab:** Tầng dữ liệu được **giả lập bằng một dịch vụ HTTP đọc tệp**, giúp quan sát mạng mà không phải mở một cơ sở dữ liệu thật. Đây là môi trường học tập; các đoạn HTTP công khai, quy tắc theo network tag và dữ liệu mẫu cần được nâng cấp về TLS, IAM, bảo mật dữ liệu và HA trước khi dùng trong production.

## 1. Yêu cầu và kết quả mong đợi

Hoàn thành bài, bạn sẽ:

1. Giải thích được **VPC có phạm vi global**, trong khi **subnet có phạm vi regional** và VM thuộc một zone.
2. Tạo một VPC custom mode với ba dải IPv4 private **không chồng lấn**.
3. Chỉ mở đường **Internet → Web → App → Data**, thay vì cho phép mọi tầng nói chuyện với nhau tùy ý.
4. Đặt VM App và Data **không có external IP**, cấp egress ra Internet qua **Cloud NAT** khi cần tải gói.
5. Kết nối quản trị qua **Identity-Aware Proxy (IAP) TCP forwarding** thay vì mở cổng SSH cho toàn Internet.
6. Xác minh route, firewall, IP, dịch vụ và thử nghiệm một kết nối bị chặn có chủ đích.
7. Hiểu cách mở rộng bài lab sang Cloud SQL, GKE, Cloud Run và cách quản lý chi phí, tài nguyên.

### 1.1. Mô hình ba tầng

| Tầng | Tên VM | Subnet | IP nội bộ cố định trong ví dụ | Dịch vụ | Truy cập vào |
| --- | --- | --- | --- | --- | --- |
| **Web / presentation** | `lab3-web` | `lab3-web-subnet` | `10.70.10.10` | Nginx cổng 80 | Internet (chỉ HTTP lab), IAP SSH |
| **App / business logic** | `lab3-app` | `lab3-app-subnet` | `10.70.20.10` | Python HTTP API cổng 8080 | Chỉ mạng Web và IAP SSH |
| **Data / giả lập** | `lab3-data` | `lab3-data-subnet` | `10.70.30.10` | HTTP đọc tệp mẫu cổng 9090 | Chỉ mạng App và IAP SSH |

Tất cả VM nằm trong **một zone mẫu** thuộc region `asia-southeast1` để dễ theo dõi; subnet chứa chúng thuộc cùng **region**. VPC `lab3-vpc` có phạm vi global, cho phép bổ sung subnet tại region khác nếu cần. Các địa chỉ `10.70.x.x` là ví dụ: trước khi chạy trong project thật phải kiểm tra với dải mạng đang tồn tại, VPN, Shared VPC và các kết nối khác.

~~~mermaid
flowchart TB
    User["Trình duyệt Internet"] -->|HTTP :80, lab| Web["Web VM / Nginx<br/>10.70.10.10"]
    Web -->|HTTP :8080| App["App VM / Python<br/>10.70.20.10"]
    App -->|HTTP :9090| Data["Data VM / dịch vụ mẫu<br/>10.70.30.10"]
    IAP["Người quản trị qua IAP"] -. "SSH :22" .-> Web
    IAP -. "SSH :22" .-> App
    IAP -. "SSH :22" .-> Data
    subgraph VPC["VPC lab3-vpc — global"]
      subgraph Region["Region asia-southeast1"]
        Web
        App
        Data
      end
    end
    NAT["Cloud NAT — region"] -->|"Egress khi cần"| Internet["Internet"]
    App -. "Qua NAT" .-> NAT
    Data -. "Qua NAT" .-> NAT
~~~

Sơ đồ biểu diễn **luồng được phép**, không nói rằng mọi đường mạng còn lại tự động bị chặn bởi việc tách subnet. Subnet giúp cấp phát địa chỉ và định tuyến; **firewall** mới là lớp kiểm soát kết nối giữa các VM. Trong lab, các quy tắc ingress có mục tiêu cụ thể, còn egress dùng cấu hình mặc định của VPC.

### 1.2. Thông số mạng

| Tài nguyên | Phạm vi | Giá trị lab |
| --- | --- | --- |
| VPC | Global | `lab3-vpc`, custom mode |
| Region | Regional | `asia-southeast1` |
| Zone | Zonal | `asia-southeast1-b` (kiểm tra có cung cấp máy mẫu) |
| Web subnet | Regional | `10.70.10.0/24` |
| App subnet | Regional | `10.70.20.0/24` |
| Data subnet | Regional | `10.70.30.0/24` |
| VM | Zonal | Ba VM Ubuntu `e2-small` với disk mặc định |
| NAT gateway | Regional | `lab3-nat` trên `lab3-router` |

Đây là sơ đồ học tập, không phải gợi ý rằng các máy và vùng này luôn rẻ nhất, miễn phí hoặc phù hợp với luật lưu trú dữ liệu. Chọn project lab riêng và dọn tài nguyên ở cuối bài.

## 2. Chuẩn bị môi trường, quyền và chi phí

Bạn cần:

- Một **Google Cloud project** có Cloud Billing account hoạt động, đã được phép tạo VM, VPC, subnet, firewall và Cloud NAT. Không dùng project production.
- **gcloud CLI** đã cài và đăng nhập; ví dụ lệnh dùng Bash trên Linux/macOS hoặc Cloud Shell. Trong PowerShell, cách khai báo biến khác.
- Quyền IAM thích hợp để bật API, tạo Compute Engine/networking, quản lý firewall và dùng IAP. Để SSH qua IAP có thể cần `roles/iap.tunnelResourceAccessor` cùng quyền đăng nhập VM (ví dụ OS Login khi được cấu hình), quyền truy cập instance và thiết lập liên quan.
- Ngân sách được phê duyệt: **VM, persistent disk, external IPv4, Cloud NAT, lưu lượng mạng** và log có thể tính phí. Budget alert giúp theo dõi nhưng không tự chặn hóa đơn.
- Môi trường không có những tài nguyên hiện hữu cùng tên hoặc dải địa chỉ. Nếu đã tồn tại, cần dừng lại và sử dụng tên/dải khác theo sơ đồ IP của tổ chức.

Các lệnh **thực thi tạo/xóa tài nguyên** bên dưới dành cho người học chạy trong project lab được phê duyệt. Bài viết chỉ trình bày lệnh; việc đọc bài không tự tạo hạ tầng.

### 2.1. Khai báo biến và xác nhận project

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export REGION="asia-southeast1"
export ZONE="asia-southeast1-b"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project
gcloud projects describe "$PROJECT_ID" --format="value(projectId)"
~~~

Thay `YOUR_LAB_PROJECT_ID` bằng Project ID đã xác minh. Việc chọn project ở CLI rất quan trọng: nếu đang trỏ sang production, toàn bộ ví dụ phía sau có thể làm thay đổi project sai.

### 2.2. Kiểm tra API và năng lực vùng

~~~bash
gcloud services list --enabled \
  --filter="name:(compute.googleapis.com OR iap.googleapis.com)"

gcloud compute machine-types describe e2-small --zone="$ZONE"
~~~

Nếu chưa bật Compute Engine API hoặc IAP API, người có quyền tương ứng có thể bật trong project lab:

~~~bash
gcloud services enable compute.googleapis.com iap.googleapis.com
~~~

Thao tác bật API có thể cần quyền như `serviceusage.services.enable`. API được bật không có nghĩa mọi quota, hạn mức hoặc quyền tạo VM đã đầy đủ. Nếu tổ chức dùng OS Login, cần thêm quyền OS Login và cấu hình liên quan trước khi thử SSH.

## 3. Tạo VPC custom mode và ba subnet

### 3.1. Tạo mạng VPC

~~~bash
gcloud compute networks create lab3-vpc \
  --subnet-mode=custom \
  --bgp-routing-mode=regional
~~~

**Vì sao chọn custom mode?** Chúng ta muốn chủ động quyết định nơi đặt subnet và dải IP của từng tầng. Tạo VPC ở custom mode không tự sinh subnet. `--bgp-routing-mode=regional` áp dụng cho cách hoạt động của những **dynamic routes** liên quan trong VPC; trong bài này không cấu hình BGP.

### 3.2. Tạo subnet Web, App và Data trong cùng region

~~~bash
gcloud compute networks subnets create lab3-web-subnet \
  --network=lab3-vpc \
  --region="$REGION" \
  --range=10.70.10.0/24

gcloud compute networks subnets create lab3-app-subnet \
  --network=lab3-vpc \
  --region="$REGION" \
  --range=10.70.20.0/24 \
  --enable-private-ip-google-access

gcloud compute networks subnets create lab3-data-subnet \
  --network=lab3-vpc \
  --region="$REGION" \
  --range=10.70.30.0/24 \
  --enable-private-ip-google-access
~~~

`--enable-private-ip-google-access` hỗ trợ kiểu truy cập Google APIs đủ điều kiện từ tài nguyên không có external IP; nó **không thay thế Cloud NAT cho kết nối tới Internet nói chung**. Trong lab, App và Data sẽ dùng NAT khi cần truy cập các kho gói công khai.

### 3.3. Xác minh vị trí và CIDR

~~~bash
gcloud compute networks describe lab3-vpc \
  --format="yaml(name,subnetworks,autoCreateSubnetworks,routingConfig)"

gcloud compute networks subnets list \
  --filter="network:lab3-vpc"

gcloud compute networks subnets describe lab3-app-subnet \
  --region="$REGION"
~~~

Bạn phải thấy ba subnet cùng thuộc `lab3-vpc`, nhưng từng subnet là tài nguyên regional và có dải CIDR riêng. Nếu tạo thêm subnet ở region khác, hãy giữ sơ đồ địa chỉ **không trùng lặp**. VM tại zone thuộc region khác không thể trực tiếp chọn một subnet tại Singapore.

## 4. Tạo Cloud NAT cho hai tầng private

VM App và Data sẽ không có external IP. Để chúng chủ động kết nối ra Internet khi cài gói hoặc tải bản cập nhật, dùng **Public Cloud NAT** trong cùng region. Cloud NAT phục vụ những luồng outbound đủ điều kiện và traffic phản hồi; nó **không mở cổng inbound công khai** đến VM.

~~~bash
gcloud compute routers create lab3-router \
  --network=lab3-vpc \
  --region="$REGION"

gcloud compute routers nats create lab3-nat \
  --router=lab3-router \
  --router-region="$REGION" \
  --nat-all-subnet-ip-ranges \
  --auto-allocate-nat-external-ips
~~~

Cloud Router ở đây là tài nguyên regional cần cho cấu hình NAT; không yêu cầu tạo BGP session cho ví dụ NAT này. `--nat-all-subnet-ip-ranges` bao phủ những dải subnet phù hợp trong **region của NAT**, không có nghĩa một NAT ở Singapore sẽ tự phục vụ VM tại mọi region của VPC global.

Ở môi trường thật, nên xem xét NAT theo những dải subnet cụ thể, quota, khả năng cạn port và chi phí xử lý lưu lượng. Dùng `nat-all-subnet-ip-ranges` trong lab để giảm số tham số khi thực hành.

Kiểm tra:

~~~bash
gcloud compute routers nats describe lab3-nat \
  --router=lab3-router \
  --router-region="$REGION"
~~~

## 5. Thiết lập firewall theo từng tầng

VPC custom mode có **implied deny ingress** và **implied allow egress**, trừ khi chính sách hoặc rule khác có ưu tiên cao hơn tác động. Mặc định không có nghĩa mọi VM trong cùng VPC được phép gọi mọi cổng của nhau. Ta tạo bốn quy tắc ingress có phạm vi rõ ràng:

| Quy tắc | Nguồn cho phép | Đích áp dụng | Cổng |
| --- | --- | --- | --- |
| `lab3-allow-iap-ssh` | `35.235.240.0/20` — dải IAP TCP forwarding | Ba VM có network tag tương ứng | TCP 22 |
| `lab3-allow-web-http` | `0.0.0.0/0` — Internet, chỉ cho bài lab | Web | TCP 80 |
| `lab3-allow-web-to-app` | `10.70.10.0/24` | App | TCP 8080 |
| `lab3-allow-app-to-data` | `10.70.20.0/24` | Data | TCP 9090 |

### 5.1. Mở SSH quản trị qua IAP

~~~bash
gcloud compute firewall-rules create lab3-allow-iap-ssh \
  --network=lab3-vpc \
  --direction=INGRESS \
  --priority=1000 \
  --allow=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags=lab3-web,lab3-app,lab3-data
~~~

Quy tắc chỉ cho phép kết nối SSH tới các target VM từ dải IP của IAP; người thao tác **vẫn phải có quyền IAM và thông tin đăng nhập VM phù hợp**. Một firewall rule không tự tạo quyền truy cập vào hệ điều hành.

### 5.2. Mở HTTP công khai duy nhất ở tầng Web

~~~bash
gcloud compute firewall-rules create lab3-allow-web-http \
  --network=lab3-vpc \
  --direction=INGRESS \
  --priority=1000 \
  --allow=tcp:80 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=lab3-web
~~~

Chỉ dùng HTTP công khai để **kiểm thử dữ liệu mẫu, không chứa bí mật**. Trong production nên dùng HTTPS, load balancer có bảo vệ phù hợp, chứng chỉ TLS, quy tắc chỉ cho phép nguồn đã được đánh giá và cơ chế hạn chế truy cập ứng dụng.

### 5.3. Chỉ cho Web gọi App và App gọi Data

~~~bash
gcloud compute firewall-rules create lab3-allow-web-to-app \
  --network=lab3-vpc \
  --direction=INGRESS \
  --priority=1000 \
  --allow=tcp:8080 \
  --source-ranges=10.70.10.0/24 \
  --target-tags=lab3-app

gcloud compute firewall-rules create lab3-allow-app-to-data \
  --network=lab3-vpc \
  --direction=INGRESS \
  --priority=1000 \
  --allow=tcp:9090 \
  --source-ranges=10.70.20.0/24 \
  --target-tags=lab3-data
~~~

**Quan trọng:** source CIDR cho phép mọi máy có IP thích hợp trong subnet nguồn gọi tầng đích ở cổng đó. Đây là giới hạn **theo mạng con**, chưa phải cấp phép theo danh tính ứng dụng. Trong thiết kế production, cân nhắc thu hẹp hơn bằng nguồn/đích được hỗ trợ (như service account hoặc chính sách firewall thích hợp), kết hợp xác thực ở tầng ứng dụng và cơ chế review network tag. Người có quyền gắn tag vào VM có thể ảnh hưởng tới các rule đang nhắm đến tag ấy.

Đến đây các subnet đã có **subnet routes** do Google Cloud tự tạo. Không cần thiết lập static route hoặc VPC Peering giữa ba subnet vì chúng nằm trong cùng VPC. Tuy nhiên, có route không đồng nghĩa firewall sẽ cho phép mọi lưu lượng.

## 6. Tạo ba VM, mỗi VM thuộc subnet tương ứng

Để dễ hiểu, ba VM đều được tạo trong `asia-southeast1-b` và dùng image Debian 12. Mỗi VM có một giao diện mạng, gắn với subnet thuộc cùng region. `lab3-web` sẽ có **ephemeral external IP** theo cấu hình mặc định của lệnh tạo VM một NIC; App và Data dùng `--no-address` để không có external IP.

~~~bash
# Tầng Web: có external IP để trình duyệt gọi HTTP lab
gcloud compute instances create lab3-web \
  --zone="$ZONE" \
  --machine-type=e2-small \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --subnet=lab3-web-subnet \
  --private-network-ip=10.70.10.10 \
  --tags=lab3-web

# Tầng App: chỉ có internal IP
gcloud compute instances create lab3-app \
  --zone="$ZONE" \
  --machine-type=e2-small \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --subnet=lab3-app-subnet \
  --private-network-ip=10.70.20.10 \
  --no-address \
  --tags=lab3-app

# Tầng Data: chỉ có internal IP
gcloud compute instances create lab3-data \
  --zone="$ZONE" \
  --machine-type=e2-small \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --subnet=lab3-data-subnet \
  --private-network-ip=10.70.30.10 \
  --no-address \
  --tags=lab3-data
~~~

### 6.1. Kiểm tra địa chỉ IP sau tạo VM

~~~bash
gcloud compute instances list \
  --filter="name~^lab3-" \
  --format="table(name,zone,networkInterfaces[0].networkIP,status)"

gcloud compute instances describe lab3-web \
  --zone="$ZONE" \
  --format="yaml(networkInterfaces,tags)"

gcloud compute instances describe lab3-app \
  --zone="$ZONE" \
  --format="yaml(networkInterfaces,tags)"

gcloud compute instances describe lab3-data \
  --zone="$ZONE" \
  --format="yaml(networkInterfaces,tags)"
~~~

Xác minh ba địa chỉ nội bộ khớp bảng thiết kế, mỗi VM thuộc đúng subnet và App/Data **không có accessConfigs cung cấp external IPv4**. Kiểm tra tên network tag trong kết quả, vì firewall rule sẽ chỉ áp dụng cho VM có tag đích.

Nếu một instance không tạo được, hãy đọc thông báo lỗi: có thể do quota, hết IP, không đủ quyền, trùng tên, sai dải subnet, zone không hỗ trợ máy hoặc chính sách tổ chức. **Không cần xóa và tạo lại cả VPC** để khắc phục một lỗi quota đơn lẻ.

### 6.2. SSH bằng IAP để không mở port 22 công khai

Lần lượt vào từng VM từ Cloud Shell hoặc máy có gcloud:

~~~bash
# Mở phiên SSH tới Data VM
gcloud compute ssh lab3-data \
  --zone="$ZONE" \
  --tunnel-through-iap
~~~

Khi hoàn tất công việc trên VM, gõ `exit` để trở lại shell chạy gcloud, rồi truy cập VM khác với tên tương ứng.

~~~bash
gcloud compute ssh lab3-app --zone="$ZONE" --tunnel-through-iap
gcloud compute ssh lab3-web --zone="$ZONE" --tunnel-through-iap
~~~

Những lệnh trên **mở phiên tương tác theo từng lần gọi**; không dán cả hai lệnh liên tiếp nếu chưa thoát khỏi phiên trước. Nếu IAP SSH lỗi, kiểm tra API, firewall từ `35.235.240.0/20`, vai trò IAP, quyền đăng nhập VM, OS Login/SSH key, cấu hình network tag và thông báo lỗi. IAP TCP forwarding không thay thế quyền vào hệ điều hành.

## 7. Khởi chạy dịch vụ mẫu theo thứ tự Data → App → Web

Mục tiêu là tạo một chuỗi yêu cầu kiểm chứng được:

`trình duyệt → Nginx Web:80 → App:8080 → Data:9090 → App → Web → trình duyệt`.

Nội dung tầng Data là một tệp văn bản không chứa thông tin nhạy cảm. Tầng App dùng Python standard library để đọc tệp qua HTTP và trả về kết quả. Tầng Web dùng Nginx làm reverse proxy. Các ví dụ đều chạy trên Debian 12; lệnh trong mỗi phần được thực hiện **bên trong VM tương ứng**, không phải trên máy đang gọi gcloud.

### 7.1. Trên VM Data: phục vụ tệp mẫu ở cổng 9090

Đăng nhập:

~~~bash
gcloud compute ssh lab3-data --zone="$ZONE" --tunnel-through-iap
~~~

**Trong shell của VM Data**, cài Python và tạo dữ liệu mẫu:

~~~bash
sudo apt-get update
sudo apt-get install -y python3 curl
sudo install -d -m 755 /opt/lab3-data
printf 'records=demo-only\n' | sudo tee /opt/lab3-data/records.txt >/dev/null
~~~

Tạo dịch vụ systemd để tiếp tục chạy khi phiên SSH thoát:

~~~bash
sudo tee /etc/systemd/system/lab3-data.service >/dev/null <<'UNIT'
[Unit]
Description=Lab 3-tier data simulator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=www-data
ExecStart=/usr/bin/python3 -m http.server 9090 --bind 10.70.30.10 --directory /opt/lab3-data
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now lab3-data.service
sudo systemctl status lab3-data.service --no-pager
curl -fsS http://10.70.30.10:9090/records.txt
~~~

Kết quả mong đợi của lệnh `curl` cuối:

~~~text
records=demo-only
~~~

Dịch vụ chỉ phục vụ dữ liệu giả lập. Không dùng `python3 -m http.server` để cung cấp dữ liệu thật, vì nó không cung cấp đầy đủ chức năng xác thực, kiểm soát truy cập, TLS và bảo vệ dữ liệu của một dịch vụ database chuyên dụng.

Thoát phiên VM Data bằng `exit`.

### 7.2. Trên VM App: gọi Data và trả về kết quả ở cổng 8080

Đăng nhập:

~~~bash
gcloud compute ssh lab3-app --zone="$ZONE" --tunnel-through-iap
~~~

**Trong shell của VM App**, cài Python và kiểm tra app subnet có thể truy cập Data:

~~~bash
sudo apt-get update
sudo apt-get install -y python3 curl
curl -fsS --connect-timeout 3 http://10.70.30.10:9090/records.txt
~~~

Lệnh cuối phải nhận `records=demo-only`. Nếu thất bại, kiểm tra dịch vụ Data, route, firewall `lab3-allow-app-to-data`, địa chỉ IP thực và local firewall trước khi viết app.

Tạo API mẫu:

~~~bash
sudo install -d -m 755 /opt/lab3-app
sudo tee /opt/lab3-app/server.py >/dev/null <<'PY'
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

DATA_URL = "http://10.70.30.10:9090/records.txt"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return

        try:
            with urlopen(DATA_URL, timeout=3) as upstream:
                records = upstream.read(128).decode("utf-8").strip()
        except Exception:
            self.send_error(502, "Data tier unavailable")
            return

        body = ("app-tier-ok; " + records + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

ThreadingHTTPServer(("10.70.20.10", 8080), Handler).serve_forever()
PY
~~~

Đăng ký dịch vụ systemd:

~~~bash
sudo tee /etc/systemd/system/lab3-app.service >/dev/null <<'UNIT'
[Unit]
Description=Lab 3-tier application simulator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=www-data
ExecStart=/usr/bin/python3 /opt/lab3-app/server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now lab3-app.service
sudo systemctl status lab3-app.service --no-pager
curl -fsS http://10.70.20.10:8080/
~~~

Kết quả mong đợi:

~~~text
app-tier-ok; records=demo-only
~~~

VM App **không truy cập Data bằng external IP**; đây là một kết nối đến IP nội bộ nằm ở subnet khác trong **cùng VPC**. Subnet routes cung cấp đường đi, còn firewall cho phép TCP 9090 từ dải App tới VM Data.

Thoát VM App bằng `exit`.

### 7.3. Trên VM Web: Nginx chuyển request tới App

Đăng nhập:

~~~bash
gcloud compute ssh lab3-web --zone="$ZONE" --tunnel-through-iap
~~~

**Trong shell của VM Web**, cài và cấu hình Nginx:

~~~bash
sudo apt-get update
sudo apt-get install -y nginx curl

sudo tee /etc/nginx/sites-available/default >/dev/null <<'NGINX'
server {
    listen 80 default_server;
    server_name _;

    location / {
        proxy_pass http://10.70.20.10:8080;
        proxy_connect_timeout 3s;
        proxy_read_timeout 5s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINX

sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
curl -fsS http://localhost/
~~~

Kết quả mong đợi:

~~~text
app-tier-ok; records=demo-only
~~~

Ở đây Web không cần truy cập trực tiếp Data. Nginx chỉ chuyển yêu cầu tới `10.70.20.10:8080`; App gọi Data ở `10.70.30.10:9090` và trả về kết quả.

Thoát VM Web. Từ **shell bên ngoài các VM**, lấy external IP của Web và thử từ trình duyệt hoặc curl:

~~~bash
WEB_IP="$(gcloud compute instances describe lab3-web \
  --zone="$ZONE" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')"

printf 'Public web IP: %s\n' "$WEB_IP"
curl -fsS "http://$WEB_IP/"
~~~

Nếu mọi thành phần đã khởi chạy, phản hồi là `app-tier-ok; records=demo-only`. Kết quả này chứng minh **chuỗi ba tầng được phép** hoạt động, chưa chứng minh hệ thống đủ an toàn để phục vụ dữ liệu thật. Bài lab dùng HTTP không mã hóa và một IP công khai tạm thời; không truyền mật khẩu, khóa hoặc dữ liệu khách hàng qua endpoint.

## 8. Kiểm thử cả đường đi được phép và bị từ chối

Không nên đánh giá firewall chỉ qua một kết quả HTTP thành công. Một thiết kế nhiều tầng đạt yêu cầu khi **đúng đường cần thiết hoạt động** và **những kết nối trái phép không đi tới đích**.

### 8.1. Ma trận kiểm thử

| Nguồn | Đích | Cổng | Kỳ vọng | Căn cứ |
| --- | --- | --- | --- | --- |
| Internet | Web external IP | TCP 80 | **Cho phép** | `lab3-allow-web-http` |
| Web VM | App internal IP | TCP 8080 | **Cho phép** | `lab3-allow-web-to-app` |
| App VM | Data internal IP | TCP 9090 | **Cho phép** | `lab3-allow-app-to-data` |
| Web VM | Data internal IP | TCP 9090 | **Bị chặn** | Data chỉ cho phép nguồn thuộc App subnet |
| Data VM | App internal IP | TCP 8080 | **Bị chặn** | App chỉ cho phép nguồn thuộc Web subnet |
| Internet | App hoặc Data external IP | Bất kỳ | **Không có endpoint IPv4 công khai** | Hai VM được tạo với `--no-address` |
| Người quản trị qua IAP | VM có tag thích hợp | TCP 22 | **Chỉ khi có IAM/SSH quyền tương ứng** | IAP source range và VM login |

Đây là kỳ vọng của **project lab chỉ chứa những rule được tạo trong bài**. Nếu có chính sách firewall cấp tổ chức, các rule khác, nhiều NIC hoặc quy tắc ưu tiên cao hơn, kết quả có thể khác. Luôn đọc **effective firewall policies** khi kiểm tra trong tổ chức đã vận hành.

### 8.2. Thử kết nối thành công

Trên VM Web (mở SSH từ shell gcloud rồi chạy lệnh trong VM):

~~~bash
curl -fsS --connect-timeout 3 http://10.70.20.10:8080/
~~~

Kỳ vọng: `app-tier-ok; records=demo-only`. Điều này chứng minh Web → App được phép, App đã gọi Data thành công.

Trên VM App:

~~~bash
curl -fsS --connect-timeout 3 http://10.70.30.10:9090/records.txt
~~~

Kỳ vọng: `records=demo-only`. Nếu App và Data nằm trong cùng VPC nhưng ở hai subnet, Google Cloud vẫn có đường subnet route đến đích. Không cần thêm VPC Peering hoặc VPN nội bộ cho hai subnet này.

### 8.3. Thử kết nối bị chặn

Trên VM Web:

~~~bash
# Kỳ vọng timeout: Web KHÔNG được kết nối trực tiếp với Data
curl --verbose --connect-timeout 3 --max-time 5 \
  http://10.70.30.10:9090/records.txt
~~~

Trên VM Data:

~~~bash
# Kỳ vọng timeout: Data KHÔNG được khởi tạo kết nối tới App:8080
curl --verbose --connect-timeout 3 --max-time 5 \
  http://10.70.20.10:8080/
~~~

Lệnh `curl` ở phép thử âm **dự kiến trả mã lỗi/timeout**; đó là bằng chứng cần phân tích, không phải bước buộc phải sửa. Nếu thay vì timeout lại nhận được dữ liệu, hãy xem lại các rule áp trên subnet/VM, route và chính sách ở cấp cao hơn.

**Lưu ý về firewall có trạng thái:** Data vẫn được phép **trả gói phản hồi** cho kết nối mà App đã khởi tạo hợp lệ. Không thể lấy luồng phản hồi này làm bằng chứng Data được quyền tự ý bắt đầu một kết nối mới tới App.

### 8.4. Kiểm tra cấu hình mạng từ gcloud

Từ shell Cloud Shell hoặc máy dùng gcloud, sau khi đã thoát các phiên SSH:

~~~bash
# Xem VPC, subnet và dải CIDR
gcloud compute networks describe lab3-vpc
gcloud compute networks subnets list --filter="network:lab3-vpc"

# Xem các route được liệt kê bởi Compute Engine
gcloud compute routes list --filter="network:lab3-vpc"

# Xem những rule ingress đã tạo
gcloud compute firewall-rules list --filter="network:lab3-vpc"

# Đối chiếu subnet và network tag của một VM
gcloud compute instances describe lab3-data \
  --zone="$ZONE" \
  --format="yaml(networkInterfaces,tags)"
~~~

Route của các subnet không yêu cầu người học tự tạo static route. Tuy nhiên, danh sách từ `gcloud compute routes list` không phải lúc nào cũng thể hiện đầy đủ mọi đường đi hiệu lực của các hình thức định tuyến động hoặc sản phẩm mạng nâng cao. Khi lab phức tạp hơn, hãy dùng thông tin Cloud Router, effective firewall và **Connectivity Tests** trong Network Intelligence Center (nếu hỗ trợ tình huống đang xét).

### 8.5. Kiểm tra log khi một tầng không phản hồi

Nếu Web trả HTTP 502, hãy kiểm tra từ gần đích nhất:

1. Từ App VM, `curl` Data để xác nhận tầng dữ liệu đang hoạt động.
2. Từ Web VM, `curl` App để xác nhận kết nối và phản hồi của tầng ứng dụng.
3. Trên App VM, đọc `sudo systemctl status lab3-app` và `sudo journalctl -u lab3-app -n 40 --no-pager`.
4. Trên Data VM, đọc `sudo systemctl status lab3-data` và `sudo journalctl -u lab3-data -n 40 --no-pager`.
5. Trên Web VM, đọc `sudo nginx -t` và `sudo journalctl -u nginx -n 40 --no-pager`.
6. Đối chiếu đúng IP, cổng, zone, network tag, ingress firewall, local firewall, server bind address và quyền IAM khi truy cập công cụ.

| Lỗi quan sát | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Không tạo được VM | Quota, thiếu quyền, zone/loại máy không phù hợp, trùng tên hoặc IP | Đọc lỗi gcloud; xác minh project, subnet, khả năng zone và quota |
| SSH qua IAP không vào được | IAP API/IAM, rule TCP22, OS Login hoặc SSH key, tag sai | Xác minh cả IAP permission và quyền đăng nhập VM |
| App/Data không tải được gói | Cloud NAT sai region/phạm vi, thiếu default route, DNS, firewall egress | Kiểm tra NAT, subnet, route và thông báo apt |
| Web nhận 502 | App service lỗi, cổng 8080 bị chặn hoặc App không gọi được Data | Kiểm tra App/Data theo từng chặng và journalctl |
| Web truy cập thẳng Data vẫn được | Rule ingress quá rộng hoặc có policy cho phép khác | Xem effective firewall, source CIDR, target và ưu tiên rule |
| VM App có external IP | Đã tạo nhầm thiếu `--no-address` | Đọc `networkInterfaces.accessConfigs`; sửa cấu hình theo quy trình thay đổi |
| Đường App → Data có route nhưng timeout | Rule ingress, firewall hệ điều hành hoặc Data service không lắng nghe | Kiểm tra cả đường mạng và service cổng 9090 |

Các log có thể chứa địa chỉ IP và thông tin hạ tầng; chỉ chia sẻ ở phạm vi cần thiết. Nếu bật VPC Flow Logs hoặc Firewall Rules Logging để quan sát sâu hơn, hãy tính mức lấy mẫu, cấu hình thu thập, lưu giữ dữ liệu và chi phí Logging.

## 9. Phân tích những quyết định thiết kế

### 9.1. Vì sao cần ba subnet khi tất cả cùng một VPC?

Một VPC có thể chứa các subnet ở cùng hoặc khác region. Trong lab, ba subnet cùng region tạo ranh giới **quy hoạch IP, vị trí và tổ chức tài nguyên** cho Web, App, Data. Nhưng subnet **không phải thiết bị firewall vật lý**; nếu tạo rule ingress rộng, Web vẫn có thể kết nối trực tiếp Data qua subnet route.

Chúng ta chọn ba subnet để người học dễ nhìn luồng và bộ lọc nguồn CIDR. Trong production, có thể dùng subnet chung với phân quyền theo service account và quy tắc mạng tinh hơn, hoặc tách VPC để tăng mức cô lập. Quyết định dựa trên miền tin cậy, phân công quản trị và yêu cầu kiểm soát cụ thể.

### 9.2. Vì sao App và Data không có external IP?

Ứng dụng tầng trong không cần trực tiếp nhận yêu cầu từ Internet. Không cấp external IP giảm bề mặt kết nối công khai; IAP cho phép quản trị và NAT cho các kết nối outbound cần thiết. Tuy nhiên, **không có external IP không đồng nghĩa đã an toàn**: một VM trong VPC vẫn có thể bị truy cập từ đường mạng nội bộ hoặc hệ thống peering/hybrid nếu firewall và danh tính không được quản lý.

### 9.3. Vì sao Cloud NAT không thay thế firewall?

Cloud NAT xử lý **dịch địa chỉ cho egress đủ điều kiện**. Nó không bảo đảm ứng dụng ở App chỉ nói chuyện với một tên miền Internet, không thực hiện xác thực và không tự giới hạn vai trò IAM. Để kiểm soát đích outbound cần kết hợp firewall egress, proxy hoặc giải pháp phù hợp với yêu cầu; có thể cần kiểm tra DNS và lưu lượng mã hóa.

### 9.4. Nếu chuyển sang dịch vụ managed thì sao?

Bài lab dùng VM để dễ thấy NIC và route. Khi thiết kế kiến trúc thực tế, cần xét cơ chế kết nối riêng của dịch vụ:

| Thành phần có thể thay | Lựa chọn Google Cloud | Khác biệt cần chú ý |
| --- | --- | --- |
| VM Web | External Application Load Balancer + backend trên VM/GKE/Cloud Run | HTTPS, certificate, health check, backend service và firewall health check phù hợp |
| VM App | Cloud Run | Egress vào VPC qua Direct VPC egress hoặc Serverless VPC Access theo cấu hình được hỗ trợ; Cloud Run không phải VM gắn NIC như ví dụ |
| App chạy container | GKE VPC-native | Node subnet và secondary IP ranges cho Pod/Service phải quy hoạch đủ dung lượng |
| VM Data giả lập | Cloud SQL qua private IP | Cần cấu hình private services access hoặc phương thức private connectivity được hỗ trợ; IP Cloud SQL không mặc nhiên được cấp trực tiếp từ `lab3-data-subnet` |
| Truy cập tài nguyên trong tổ chức nhiều project | Shared VPC | Host project sở hữu VPC/subnet, service project chạy workload với IAM được phân quyền |

Đổi từ tầng dữ liệu giả lập sang Cloud SQL còn cần quản lý user database, secret, backup, HA, khả năng mở rộng và kết nối an toàn. **Firewall cho phép TCP đến database không tự cấp quyền đọc bảng hoặc truy vấn.**

### 9.5. VPC riêng có giúp chịu lỗi region không?

VPC là **global**, nhưng ba VM hiện đều chạy tại một zone của cùng region. Mất zone hoặc region có thể làm mất toàn bộ chuỗi Web → App → Data. Muốn thiết kế HA, cần chọn thêm vùng khả dụng/region, cân bằng tải, triển khai replica phù hợp và cơ chế phục hồi dữ liệu. Đặt VPC global hoặc tạo thêm subnet ở region khác **chưa tự động** tạo backend chạy ở đó.

Khi mở rộng, cần xác định mục tiêu SLO, **RTO** (thời gian phục hồi) và **RPO** (mức mất dữ liệu chấp nhận). Đồng thời kiểm tra lưu trú dữ liệu, phí mạng xuyên region và khả năng failover thực tế.

## 10. Theo dõi chi phí và dọn toàn bộ tài nguyên lab

Các tài nguyên dưới đây có thể phát sinh phí ngay cả khi bạn không truy cập website:

- VM và boot persistent disk khi VM còn tồn tại hoặc tài nguyên lưu trữ chưa xóa.
- External IPv4 của Web và địa chỉ public NAT theo chính sách giá hiện hành.
- Cloud NAT và lưu lượng được xử lý, truyền dữ liệu Internet hoặc giữa các region.
- Cloud Logging/Flow Logs và những tài nguyên được tạo bổ sung khi mở rộng lab.

Ghi lại tên tài nguyên, project, region và thời điểm thử nghiệm. **Budget alert không phải giới hạn cứng**: hãy tự kiểm tra và xóa tài nguyên khi hoàn thành.

### 10.1. Kiểm tra trước khi xóa

Từ shell gcloud bên ngoài VM:

~~~bash
gcloud config get-value project
gcloud compute instances list --filter="name~^lab3-"
gcloud compute networks list --filter="name=lab3-vpc"
gcloud compute firewall-rules list --filter="network:lab3-vpc"
gcloud compute routers nats list \
  --router=lab3-router \
  --router-region="$REGION"
~~~

**Xác nhận lại tên project và các tài nguyên đúng của lab.** Nếu nhiều người dùng chung project hoặc tên tài nguyên đã được một nhóm khác tiếp quản, dừng thao tác xóa và đối chiếu người sở hữu. Các lệnh dưới đây chỉ dành cho những tài nguyên **bạn vừa tạo trong lab này**.

### 10.2. Xóa theo thứ tự phụ thuộc

~~~bash
# 1. Xóa ba VM thuộc đúng zone của lab
gcloud compute instances delete \
  lab3-web lab3-app lab3-data \
  --zone="$ZONE" --quiet

# 2. Xóa bốn ingress firewall rules của lab
gcloud compute firewall-rules delete \
  lab3-allow-iap-ssh \
  lab3-allow-web-http \
  lab3-allow-web-to-app \
  lab3-allow-app-to-data \
  --quiet

# 3. Xóa NAT trước Cloud Router
gcloud compute routers nats delete lab3-nat \
  --router=lab3-router \
  --router-region="$REGION" \
  --quiet

gcloud compute routers delete lab3-router \
  --region="$REGION" --quiet

# 4. Xóa subnet sau khi VM không còn dùng đến
gcloud compute networks subnets delete \
  lab3-web-subnet lab3-app-subnet lab3-data-subnet \
  --region="$REGION" --quiet

# 5. Xóa VPC sau khi đã xóa mọi thành phần phụ thuộc
gcloud compute networks delete lab3-vpc --quiet
~~~

Nếu một lệnh xóa lỗi, đọc thông báo về tài nguyên phụ thuộc và **chỉ xử lý đúng phần còn sót của lab**. Không thay bằng lệnh xóa mọi VM, mọi VPC hoặc xóa project đang dùng chung.

Xác minh sau cùng:

~~~bash
gcloud compute instances list --filter="name~^lab3-"
gcloud compute networks list --filter="name=lab3-vpc"
gcloud compute firewall-rules list --filter="network:lab3-vpc"
~~~

Khi ba truy vấn không còn hiển thị tài nguyên lab, tiếp tục kiểm tra trong Console nếu bạn có tạo thêm disk, IP đặt trước, log sink hoặc tài nguyên mở rộng ngoài hướng dẫn. Chi phí đã phát sinh trước khi xóa vẫn có thể xuất hiện trong báo cáo sau một khoảng trễ ghi nhận.

## 11. Bài tập mở rộng và câu hỏi tự kiểm tra

**Bài tập 1 — Giới hạn nguồn theo danh tính.** Tìm cách thay firewall rule theo dải `10.70.10.0/24` bằng mô hình kiểm soát chặt hơn đối với máy Web phù hợp. Nêu rủi ro khi người có quyền tạo VM hoặc gắn network tag có thể làm thay đổi đối tượng được rule cho phép.

**Bài tập 2 — Tách môi trường.** Thiết kế thêm mạng `dev-vpc` để thử nghiệm; so sánh cách tổ chức bằng hai VPC riêng và bằng Shared VPC cho các service project. Mô tả người nào được quyền tạo subnet và ai được phép triển khai workload.

**Bài tập 3 — Chạy ở hai region.** Nếu muốn có Web và App tại một region dự phòng, bạn cần thêm subnet và những thành phần nào? Phân tích định tuyến, firewall, load balancing, replication, quota, RTO/RPO và phí truyền dữ liệu.

**Bài tập 4 — Tự động hóa phát hành.** Nếu chuyển App sang Cloud Run, vẽ lại luồng HTTP và con đường egress đến private IP của database. Xác định runtime service account và quyền IAM tối thiểu thay vì dùng tài khoản quản trị trên tất cả dịch vụ.

**Bài tập 5 — Điều tra lỗi.** Hãy dự đoán kết quả khi tạm bỏ quy tắc `lab3-allow-web-to-app`: người dùng bên ngoài sẽ thấy gì? Đường từ App tới Data còn hoạt động độc lập không? Đọc lại ma trận firewall trước khi đưa ra đáp án.

### Câu hỏi ôn tập

1. **VPC global có khiến mọi subnet trở thành global?** Không. VPC global, subnet regional, VM zonal.
2. **Tạo ba subnet có tự động chặn Web gọi thẳng Data?** Không. Cần firewall và các chính sách kiểm soát truy cập phù hợp.
3. **App không có external IP có tải gói từ Internet được không?** Có thể, nếu có đường egress hợp lệ như Cloud NAT, route, DNS và firewall phù hợp.
4. **Bật Cloud NAT có mở inbound Internet tới App?** Không. Public Cloud NAT phục vụ outbound đủ điều kiện và lưu lượng phản hồi.
5. **IAP SSH có cần IAM và quyền đăng nhập VM không?** Có. Firewall mở TCP 22 cho dải IAP chỉ là một phần điều kiện.
6. **Tại sao cần phép thử bị từ chối?** Vì kết nối hợp lệ hoạt động chưa đủ chứng minh dữ liệu và tầng nội bộ đã được cô lập.
7. **Trong production có nên giữ dịch vụ Data giả lập qua HTTP như lab?** Không. Phải dùng dịch vụ dữ liệu phù hợp, mã hóa, xác thực, backup, giới hạn IAM và thiết kế HA.

## Tài liệu chính thức để đối chiếu

- [VPC networks](https://cloud.google.com/vpc/docs/vpc): VPC global, subnet regional và phạm vi route.
- [VPC subnets](https://cloud.google.com/vpc/docs/subnets): quy hoạch CIDR, subnet mode và Private Google Access.
- [VPC firewall rules](https://cloud.google.com/firewall/docs/firewalls): ingress/egress, target, source và implied rules.
- [Cloud NAT overview](https://cloud.google.com/nat/docs/overview): NAT regional, outbound và giới hạn.
- [Connect to Linux VMs using IAP](https://cloud.google.com/compute/docs/connect/ssh-using-iap): IAM, firewall, IAP TCP forwarding và SSH.
- [Shared VPC](https://cloud.google.com/vpc/docs/shared-vpc): tách trách nhiệm mạng và workload giữa host/service project.
- [Cloud Run VPC networking](https://cloud.google.com/run/docs/configuring/vpc-direct-vpc): kết nối serverless với mạng riêng.
- [Cloud SQL private IP](https://cloud.google.com/sql/docs/mysql/configure-private-ip): kết nối database managed qua private IP theo sản phẩm.
- [VPC network pricing](https://cloud.google.com/vpc/network-pricing) và [Compute Engine pricing](https://cloud.google.com/compute/all-pricing): kiểm tra phí theo region và loại tài nguyên.

Lệnh gcloud, vai trò IAM, danh sách sản phẩm hỗ trợ theo region và giá có thể thay đổi. Trước khi chạy trên project thật, hãy đối chiếu tài liệu hiện hành, quyền được cấp và sơ đồ mạng của tổ chức. Thực hành thành công khi vừa gọi được chuỗi **Web → App → Data**, vừa chứng minh Web **không thể gọi trực tiếp** Data, rồi **xóa hết tài nguyên lab** sau khi hoàn tất.
