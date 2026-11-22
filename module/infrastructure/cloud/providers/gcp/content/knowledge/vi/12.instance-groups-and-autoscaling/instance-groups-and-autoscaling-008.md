# Kết hợp Managed Instance Groups với Cloud Load Balancing

Một website bán lẻ có backend HTTP chạy trên **Compute Engine**. Lúc ít người truy cập, hai máy ảo đã đủ; khi mở chiến dịch khuyến mại, số request tăng gấp nhiều lần, một VM có thể quá tải hoặc một zone có thể gặp sự cố. Nếu chỉ tạo thêm máy ảo thủ công, đội vận hành phải tự cập nhật IP của các máy, giám sát sức khỏe, phân phối traffic và thu hồi máy khi nhu cầu giảm.

**Managed Instance Group (MIG)** và **Cloud Load Balancing** giải quyết hai nửa bổ sung của bài toán: MIG **duy trì và mở rộng một tập VM theo mẫu**, còn load balancer **nhận traffic và chuyển tới backend đủ điều kiện**. Khi phối hợp đúng, hệ thống có thể mở rộng theo tải, thay máy bị lỗi, thực hiện rolling update và sử dụng nhiều zone. Tuy nhiên, không nên xem hai dịch vụ là cơ chế “tự động bảo đảm không downtime”: ứng dụng vẫn cần health endpoint chính xác, lưu trạng thái bền vững, triển khai an toàn, cấu hình mạng/IAM và giám sát chất lượng người dùng.

Bài học thuộc chương **Nhóm máy ảo và tự động mở rộng**, trong mô-đun **CLOUD_PROVIDERS_GCP**. Kiến trúc này liên hệ trực tiếp đến tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, Cloud Storage và Cloud SQL. Qua tình huống triển khai, người học sẽ biết chọn load balancer, bảo vệ backend, tự động hóa phát hành, quản lý độ tin cậy và cân nhắc chi phí.

## 1. Mục tiêu và bản đồ kiến trúc

Sau bài này, bạn có thể:

1. Phân biệt trách nhiệm **instance template**, **MIG**, **autoscaler**, **backend service**, **health check** và **load balancer frontend**.
2. Chọn **zonal MIG** hoặc **regional MIG**, đồng thời hiểu sự khác biệt với cân bằng tải liên vùng.
3. Thiết lập **named port**, gắn MIG làm backend của Application Load Balancer và cấu hình kiểm tra sức khỏe.
4. Giải thích mối quan hệ giữa **autoscaling theo CPU**, **load balancing serving capacity**, và các giới hạn min/max replicas.
5. Thiết kế truy cập backend an toàn qua VPC firewall, TLS, service account và các chính sách liên quan.
6. Tổ chức cập nhật phiên bản, connection draining, autohealing và khắc phục sự cố mà không nhầm lẫn các lớp.

### 1.1. Luồng request từ client tới VM

~~~mermaid
flowchart TB
    U["Client / trình duyệt"] --> FE["Frontend: IP, HTTPS, forwarding rule"]
    FE --> PROXY["Target HTTPS proxy"]
    PROXY --> MAP["URL map: host/path routing"]
    MAP --> BS["Backend service: retail-web-backend"]
    BS --> HC["Health check"]
    BS --> MIG["Managed Instance Group"]
    MIG --> VM1["VM A: web :8080"]
    MIG --> VM2["VM B: web :8080"]
    MIG --> VM3["VM C: web :8080"]
    TEMPLATE["Instance template"] -. "Tạo VM đồng nhất" .-> MIG
    AUTO["Autoscaler"] -. "Điều chỉnh số VM" .-> MIG
    HC -. "Kiểm tra backend" .-> VM1
    HC -.-> VM2
    HC -.-> VM3
~~~

Sơ đồ thể hiện kiến trúc logic của một **Application Load Balancer**; các kiểu Network Load Balancer có data plane và tập thành phần khác. Đặc biệt, health check được backend service sử dụng để xác định instance đủ điều kiện nhận traffic. **MIG autohealing** có thể dùng một health check riêng để quyết định khi nào thay VM, nên không mặc nhiên coi mọi kết quả health check là một hành động xóa máy.

### 1.2. Ai chịu trách nhiệm việc gì?

| Thành phần | Trách nhiệm | Không tự làm |
| --- | --- | --- |
| **Instance template** | Khai báo machine type, image, disk, network, metadata, service account của VM mới. | Không chạy VM khi chưa có MIG hoặc thao tác tạo instance. |
| **MIG** | Quản lý số lượng và cấu hình VM theo template, cập nhật/khôi phục instance theo policy. | Không tự cung cấp địa chỉ IP công khai, TLS hoặc URL routing. |
| **Autoscaler** | Tính số lượng VM mục tiêu từ tín hiệu tải và giới hạn cấu hình. | Không làm ứng dụng stateless hay cấp capacity tức thời. |
| **Backend service** | Gắn instance group/NEG, cấu hình traffic policy, health check và serving capacity. | Không thay thế instance template hoặc tự sửa code VM. |
| **Health check** | Thử mức sẵn sàng của backend theo protocol/port/path. | Không khẳng định toàn bộ nghiệp vụ hoặc database đều đúng. |
| **Load balancer frontend** | Nhận traffic theo địa chỉ và cổng; với Application LB phối hợp proxy, TLS và URL map. | Không tự cấp IAM/database privilege cho ứng dụng. |
| **VPC firewall** | Kiểm soát các gói tin được phép đi tới backend. | Không tự thay đổi routing hoặc endpoint health. |

Mô hình trên thường được áp dụng với **MIG làm instance-group backend**. Đây là lựa chọn khác với **zonal network endpoint groups (NEGs)** dùng IP:port; không gộp hai cách quản lý backend thành một mà chưa xác định chủ sở hữu và tính tương thích.

## 2. Nền tảng Managed Instance Groups

### 2.1. Instance template là nguồn cấu hình VM mới

MIG tạo VM dựa trên **instance template**: loại máy, boot image, disk, labels, network interface, service account, startup script và các thành phần được khai báo. Khi cần phiên bản mới, thường tạo **template mới** rồi cập nhật MIG thay vì sửa từng VM bằng SSH.

Một VM trong MIG nên được thiết kế **có thể bị thay thế**. Nếu sửa code trực tiếp trên VM mà không cập nhật template/image, thay VM hoặc scale-out sẽ làm mất thay đổi. Tương tự, file người dùng hoặc session chỉ lưu ở boot disk cục bộ không phải nguồn trạng thái bền vững cho cả nhóm.

Ứng dụng backend có thể lưu dữ liệu quan trọng tại **Cloud SQL**, object tại **Cloud Storage**, secret tại **Secret Manager** và metrics/logs trong các dịch vụ quản lý tương ứng. Runtime service account chỉ nên có permission cần thiết trên từng tài nguyên.

### 2.2. Zonal MIG và regional MIG

| Tiêu chí | Zonal MIG | Regional MIG |
| --- | --- | --- |
| Phạm vi | Một zone. | Một region, có thể phân phối VM qua nhiều zone được chọn. |
| Tính sẵn sàng | Không tự tránh được sự cố cả zone. | Có thể duy trì backend ở nhiều zone, nếu đủ capacity và policy phù hợp. |
| Cấu hình | Đơn giản cho lab hoặc workload có thể chạy lại. | Cần chọn vùng phân phối, kiểm tra sức chứa và trạng thái đa zone. |
| Autoscaling | Có thể điều chỉnh tổng số VM của nhóm. | Điều chỉnh tổng số VM và phân phối giữa các zone theo cơ chế của nhóm. |
| Phù hợp | Dev/test, batch hoặc trường hợp chấp nhận gián đoạn zone. | Backend production muốn giảm rủi ro phụ thuộc một zone. |

**Regional MIG không vượt qua nhiều region.** Nếu cần dự phòng cả region, có thể xây nhiều regional MIG ở các region khác nhau và sử dụng loại load balancer hỗ trợ định tuyến tới cả hai, cùng thiết kế dữ liệu đa vùng và chính sách failover thích hợp.

### 2.3. MIG quản lý vòng đời VM

Các hoạt động thường gặp:

- **Scale out:** tạo thêm VM từ template để đạt target size.
- **Scale in:** giảm số instance khi nhu cầu giảm, theo quy tắc autoscaler và chính sách bảo vệ/scale-in.
- **Autohealing:** kiểm tra sức khỏe VM và thử tái tạo VM không khỏe khi chính sách được bật.
- **Rolling update:** thay từng đợt VM sang template/version mới theo giới hạn sẵn sàng và số lượng thay thế.
- **Recreate/repair:** tái tạo VM bị lỗi hoặc lệch khỏi trạng thái mong muốn.

MIG **không tự phục hồi được dữ liệu chỉ lưu trong RAM** hoặc đảm bảo mọi kết nối đang mở còn sống sau khi VM bị thay. Backend phải triển khai graceful shutdown, timeout, retry và cơ chế lưu trạng thái phù hợp.

### 2.4. Named ports: chiếc cầu giữa instance group và backend service

Ví dụ tất cả VM trong MIG chạy web server ở cổng TCP `8080`. Ở cấp group, cấu hình:

~~~text
Managed instance group: retail-web-mig
Named port:             http:8080

Backend service:
  protocol: HTTP
  portName: http
~~~

Với những backend service kiểu proxy/Application LB sử dụng named ports, tên `http` giúp backend service tìm **cổng phục vụ** của VM. Nếu group khai báo `http:8080` nhưng web server chỉ chạy ở `9090`, traffic hoặc health check sẽ gặp lỗi tùy cấu hình.

**Named port không phải firewall rule, không khởi chạy service và không đồng nghĩa mở port ra Internet.** Nó chỉ là ánh xạ tên/cổng phục vụ mà loại load balancer hỗ trợ. Đối với những dạng passthrough Network Load Balancer, cách xác định cổng và backend có thể khác.

## 3. Chọn Cloud Load Balancing phù hợp với MIG

### 3.1. Application hay Network Load Balancer?

Google Cloud có nhiều sản phẩm cân bằng tải. Khi mục tiêu là ứng dụng web HTTP/HTTPS với tên miền, chứng chỉ và host/path routing, **Application Load Balancer** là lựa chọn điển hình. Khi cần cân bằng traffic TCP/UDP ở tầng vận chuyển hoặc bảo toàn đặc tính gói tin, hãy đánh giá những loại **Network Load Balancer** tương ứng.

| Nhu cầu | Phương án cần khảo sát | Lưu ý kiến trúc |
| --- | --- | --- |
| Website public HTTPS, host/path routing | Global external Application Load Balancer. | Frontend/proxy/URL map, backend service và health check. |
| HTTP(S) chỉ phục vụ nội bộ | Internal Application Load Balancer. | VPC, region/cross-region, proxy-only subnet theo loại và quyền mạng. |
| HTTP(S) public cần quy định phạm vi regional | Regional external Application Load Balancer. | Dùng các tài nguyên regional và proxy-only subnet theo yêu cầu. |
| TCP không cần URL routing | Proxy hoặc passthrough Network Load Balancer phù hợp. | Protocol, frontend và kiểu instance-group/NEG backend khác nhau. |
| Nhiều region, một public hostname | Loại global external LB và backend đa region được hỗ trợ. | Từng region cần capacity, data consistency và SLO phù hợp. |

**Không phải tất cả loại load balancer đều hỗ trợ cùng health check, scope, SSL termination, autoscaling signal, session affinity hoặc thuật toán phân phối.** Khi làm theo các lệnh minh họa ở phần sau, ta cố định bài toán ở **global external Application Load Balancer** với MIG backend để tránh ghép nhầm tùy chọn.

### 3.2. Một MIG có thể được dùng cho nhiều mục đích

MIG là nguồn VM phục vụ backend service. Một kiến trúc có thể có nhiều backend service hoặc load balancer tham chiếu một nhóm khi được hỗ trợ, nhưng phải đánh giá:

- Cổng nào thực sự nhận traffic? Named ports có tương ứng từng backend không?
- Health checks có kiểm tra đúng ứng dụng và phạm vi không?
- Autoscaling dựa trên tín hiệu nào và phản ứng của tải tổng hợp ra sao?
- Có nguy cơ một ứng dụng làm quá tải VM dùng chung cho ứng dụng khác không?

Nếu các ứng dụng có vòng đời, quyền, SLA hoặc nhu cầu scale khác nhau, dùng **các MIG riêng** thường giúp vận hành đơn giản và tránh tranh chấp capacity.

### 3.3. Backend service không phải instance group

Trong một backend service, có thể gắn các instance groups hợp lệ ở những zone hoặc region được load balancer hỗ trợ. **Backend service quyết định phân phối traffic và health**, trong khi mỗi MIG quản lý VM của chính nó.

Một global external Application Load Balancer có thể kết nối tới các backend tại nhiều region; điều này không biến một regional MIG thành một nhóm multi-region. Phân tách rõ các ranh giới giúp mô hình dự phòng dễ kiểm tra hơn.

## 4. Chuẩn bị backend trước khi gắn load balancer

### 4.1. Mẫu ứng dụng và health endpoints

Giả sử ứng dụng web lắng nghe trên tất cả interface (`0.0.0.0`) tại cổng `8080`, có hai endpoint:

~~~text
GET /healthz  -> HTTP 200 khi instance đã sẵn sàng nhận traffic
GET /livez    -> HTTP 200 khi process/VM còn hoạt động cơ bản
~~~

**Readiness** (`/healthz`) thường dùng cho backend service load balancer: nếu instance chưa kết nối được các phụ thuộc thiết yếu, có thể không nên gửi request mới. **Liveness** (`/livez`) nên dùng tiêu chí không quá nhạy để tránh MIG autohealing phá hủy một VM chỉ vì một phụ thuộc bên ngoài chập chờn.

Ví dụ:

~~~text
VM đang boot:
  /livez   = 200 nếu process nền tảng chạy
  /healthz = 503 trong lúc tải cấu hình/cache

VM phục vụ bình thường:
  /livez   = 200
  /healthz = 200

VM không thể tiếp nhận traffic mới:
  /healthz = 503
  /livez   = có thể vẫn 200
~~~

Tiêu chí cuối cùng do kiến trúc ứng dụng quyết định. Không để một health check gọi tác vụ nặng, ghi database hoặc gây side effect; lượng probe của load balancer có thể cao khi số VM tăng.

### 4.2. Mẫu khởi tạo ứng dụng trên Linux

Trong lab, có thể dùng startup script tạo HTTP server đơn giản. Ví dụ sau **chỉ phục vụ học tập**; ứng dụng production nên dùng image đã kiểm thử, service manager và quy trình CI/CD:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

apt-get update
apt-get install -y python3
mkdir -p /opt/retail-web

cat >/opt/retail-web/server.py <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/healthz", "/livez"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK\n")
        else:
            payload = f"Retail demo on {socket.gethostname()}\n".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
PY

cat >/etc/systemd/system/retail-web.service <<'UNIT'
[Unit]
Description=Retail web demo
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/retail-web/server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now retail-web.service
~~~

Trong môi trường không có đường egress phù hợp, `apt-get update` có thể lỗi. Với VM không có external IP, cần cấu hình Private Google Access hoặc NAT/đường kết nối đúng cho các dịch vụ/nguồn package tương ứng; PGA không tự cấp quyền truy cập mọi kho Internet. Đối với production, nên đóng gói dependency trong image để VM mới boot nhanh và ít phụ thuộc vào tài nguyên bên ngoài.

### 4.3. Chuẩn bị hạ tầng VPC và quyền

Trước khi chạy lệnh tạo VM:

1. Project và VPC/subnet đã được tạo ở region/zone mục tiêu.
2. Người triển khai có đủ IAM role ở phạm vi thích hợp để tạo templates, MIG, health checks, backend services, URL maps và firewall.
3. Runtime service account riêng cho VM đã có quyền tối thiểu tới Cloud SQL, Cloud Storage hoặc Secret Manager khi ứng dụng cần.
4. Backends có đường egress hợp lệ để lấy package/image và gọi Google APIs; không bắt buộc gắn external IP.
5. Quy tắc firewall cho phép đúng traffic health checker/proxy tới cổng ứng dụng.
6. Có budget, monitoring, kế hoạch dọn tài nguyên lab và kiểm tra quota.

Mỗi lệnh tạo tài nguyên có thể **phát sinh chi phí**. Dùng một project sandbox được phép và kiểm tra kỹ trước khi thực thi.

## 5. Thực hành: tạo MIG và kết nối global external Application Load Balancer

Phần này dùng **Bash** và các tên ví dụ. Lệnh `create`, `set-*`, `add-*` và `update` là **thao tác ghi** trên Google Cloud. Không chạy nguyên bộ lệnh trong production khi chưa kiểm tra quyền, resource naming, tổ chức mạng và đặc tính của phiên bản CLI.

### 5.1. Các thông số minh họa

~~~bash
PROJECT_ID="retail-lab"
REGION="asia-southeast1"
ZONE="asia-southeast1-a"
NETWORK="retail-vpc"
SUBNET="web-subnet"
TEMPLATE="retail-web-v1"
MIG="retail-web-mig-a"
HC="retail-web-health"
BACKEND="retail-web-backend"
~~~

Trong thực tế, lưu các giá trị trong IaC/CI environment phù hợp, tránh hard-code thông tin bí mật vào startup metadata. Các cặp project, region, subnet phải tương thích; nếu dùng Shared VPC, nhiều thao tác network/IAM phải được thực hiện hoặc tham chiếu tại **host project**.

### 5.2. Tạo instance template

Giả sử bạn đã lưu script ở phần 4.2 thành file `bootstrap.sh` trên máy quản trị. Đây là **file do người triển khai tự chuẩn bị**, không phải file dự án được bài học tự tạo.

~~~bash
gcloud compute instance-templates create "$TEMPLATE" \
  --project="$PROJECT_ID" \
  --machine-type=e2-medium \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --network="$NETWORK" \
  --subnet="$SUBNET" \
  --no-address \
  --tags=allow-retail-web \
  --metadata-from-file=startup-script=bootstrap.sh
~~~

Lệnh minh họa chọn Debian và không cấp external IPv4 cho backend. Nếu ứng dụng cần quyền gọi Cloud SQL/Cloud Storage, hãy cấu hình **service account chuyên dụng** và OAuth scopes phù hợp với môi trường; tránh mặc định giao cho VM một service account có đặc quyền rộng.

**Instance template là bản khai báo dùng tạo VM mới.** Đổi script, image hoặc cấu hình mạng nên tạo template mới (`retail-web-v2`) và cập nhật MIG qua quy trình rollout, thay vì kỳ vọng template cũ tự cập nhật các VM đang chạy.

### 5.3. Tạo zonal MIG

~~~bash
gcloud compute instance-groups managed create "$MIG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --template="$TEMPLATE" \
  --base-instance-name=retail-web \
  --size=2

# Đặt tên cổng mà backend service sẽ tham chiếu.
gcloud compute instance-groups managed set-named-ports "$MIG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --named-ports=http:8080

# Xem cấu hình và các VM đang được quản lý (read-only).
gcloud compute instance-groups managed describe "$MIG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

gcloud compute instance-groups managed list-instances "$MIG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"
~~~

MIG có target size bằng 2 không chứng minh **hai VM đã Ready**. VM có thể đang khởi động, startup script lỗi, hết quota hoặc chưa được cấp capacity. Giai đoạn này cần đọc instance logs và kiểm tra ứng dụng có thực sự nghe cổng 8080.

### 5.4. Tạo health check

~~~bash
# WRITE: health check cho backend service global.
gcloud compute health-checks create http "$HC" \
  --project="$PROJECT_ID" \
  --global \
  --port=8080 \
  --request-path=/healthz

# READ-ONLY: kiểm tra cấu hình.
gcloud compute health-checks describe "$HC" \
  --project="$PROJECT_ID" \
  --global
~~~

Với VM backend, load balancer gửi probe theo health check này. Đặt đúng **protocol/path/port**, độ trễ startup và timeout/check interval phù hợp. Endpoint `/healthz` không nên yêu cầu đăng nhập người dùng, nhưng cũng không nên để lộ bí mật hoặc thông tin nội bộ nhạy cảm.

### 5.5. Mở firewall cho health check và traffic backend

Với mô hình **global external Application Load Balancer** dùng Google Front Ends (GFE), tài liệu Google Cloud thường chỉ rõ các dải nguồn cần cho health checker/backend traffic:

~~~text
35.191.0.0/16
130.211.0.0/22
~~~

Một rule minh họa giới hạn cổng và network tag:

~~~bash
gcloud compute firewall-rules create allow-retail-lb-to-web \
  --project="$PROJECT_ID" \
  --network="$NETWORK" \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-ranges=35.191.0.0/16,130.211.0.0/22 \
  --target-tags=allow-retail-web
~~~

**Không sao chép hai dải trên cho mọi load balancer.** Với regional/cross-region internal hoặc external Application Load Balancer chạy trên Envoy, **proxy-only subnet** và các dải health checker tương ứng có thể cần được cho phép. Với Shared VPC, firewall policy thuộc VPC/network host. Ngoài VPC firewall còn có hierarchical firewall policies và firewall trong guest OS.

Không mở `0.0.0.0/0` vào cổng backend chỉ để làm health check chuyển sang xanh. Trong mô hình proxy, backend thường không cần external IP và không cần mở trực tiếp HTTP backend cho toàn Internet.

### 5.6. Tạo backend service và gắn MIG

~~~bash
# WRITE: backend service cho global external Application Load Balancer.
gcloud compute backend-services create "$BACKEND" \
  --project="$PROJECT_ID" \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --protocol=HTTP \
  --port-name=http \
  --health-checks="$HC"

# WRITE: gắn zonal MIG vào backend service.
gcloud compute backend-services add-backend "$BACKEND" \
  --project="$PROJECT_ID" \
  --global \
  --instance-group="$MIG" \
  --instance-group-zone="$ZONE" \
  --balancing-mode=UTILIZATION \
  --max-utilization=0.80

# READ-ONLY: xem cấu hình backend service.
gcloud compute backend-services describe "$BACKEND" \
  --project="$PROJECT_ID" \
  --global
~~~

Trong cấu hình này, `--port-name=http` liên kết với named port `http:8080` trên MIG. `UTILIZATION` và `maxUtilization` tham gia vào cách load balancer xem capacity của backend; chúng **không tự kích hoạt autoscaling**. Muốn autoscale, cần bật autoscaler riêng cho MIG.

Nếu dùng **regional MIG**, tham chiếu backend bằng phạm vi group **region** và chỉ với các backend service/load balancer có hỗ trợ. Nếu dùng regional backend service, đừng giữ `--global` theo ví dụ này.

### 5.7. Tạo HTTP frontend để thử nghiệm

Các lệnh dưới đây tạo một **frontend HTTP không mã hóa** chỉ để minh họa luồng. **Không dùng HTTP cho đăng nhập, session hoặc dữ liệu khách hàng production**; khi triển khai thật hãy dùng **HTTPS proxy với certificate hợp lệ**, forwarding rule cổng 443 và DNS đúng.

~~~bash
gcloud compute url-maps create retail-web-map \
  --project="$PROJECT_ID" \
  --default-service="$BACKEND"

gcloud compute target-http-proxies create retail-web-http-proxy \
  --project="$PROJECT_ID" \
  --url-map=retail-web-map

gcloud compute forwarding-rules create retail-web-http-rule \
  --project="$PROJECT_ID" \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --target-http-proxy=retail-web-http-proxy \
  --ports=80

# READ-ONLY: đọc IP frontend được cấp.
gcloud compute forwarding-rules describe retail-web-http-rule \
  --project="$PROJECT_ID" \
  --global \
  --format="yaml(name,IPAddress,IPProtocol,portRange)"
~~~

Global frontend có thể dùng IP được cấp động trong lab; với production nên quản lý địa chỉ IP theo tài nguyên và DNS đã thiết kế. Từ ngoài, thử truy cập `http://<FRONTEND_IP>/` chỉ **sau khi** hệ thống đã xuất hiện healthy backends. Nếu lỗi, không vội thay đổi toàn bộ hạ tầng; xem từng lớp theo phần troubleshooting.

### 5.8. Xác minh backend health

~~~bash
# READ-ONLY: kiểm tra trạng thái backends của global backend service.
gcloud compute backend-services get-health "$BACKEND" \
  --project="$PROJECT_ID" \
  --global
~~~

Có thể mất một khoảng thời gian để VM khởi động, health checker hoàn thành probe và trạng thái mới ổn định. Nếu backend không khỏe, kiểm tra ứng dụng có lắng nghe `0.0.0.0:8080`, firewall, named port và health check path trước khi tăng số VM.

## 6. Mở rộng regional MIG cho production nhiều zone

Một zonal MIG không đủ chống sự cố zone. Với ứng dụng production muốn tăng khả năng sẵn sàng, có thể tạo **regional MIG** phân phối VM qua nhiều zone trong cùng region.

~~~mermaid
flowchart TD
    LB["Global external Application Load Balancer"] --> BS["Backend service"]
    BS --> RM["Regional MIG: asia-southeast1"]
    RM --> A["Zone A: 2 VM"]
    RM --> B["Zone B: 2 VM"]
    RM --> C["Zone C: 2 VM"]
    DB["Cloud SQL / durable store"] --> APP["Trạng thái ứng dụng dùng chung"]
    A -.-> APP
    B -.-> APP
    C -.-> APP
~~~

### 6.1. Ví dụ tạo regional MIG

~~~bash
# WRITE: triển khai vào nhiều zone của cùng region.
gcloud compute instance-groups managed create retail-web-regional \
  --project=retail-lab \
  --region=asia-southeast1 \
  --zones=asia-southeast1-a,asia-southeast1-b,asia-southeast1-c \
  --template=retail-web-v1 \
  --base-instance-name=retail-web \
  --size=6

gcloud compute instance-groups managed set-named-ports retail-web-regional \
  --project=retail-lab \
  --region=asia-southeast1 \
  --named-ports=http:8080

# READ-ONLY: xem phân phối VM trong nhóm.
gcloud compute instance-groups managed list-instances retail-web-regional \
  --project=retail-lab \
  --region=asia-southeast1
~~~

Ví dụ này là **một phương án thay thế** cho zonal MIG đã tạo ở phần trước, không yêu cầu triển khai cả hai với tên instance xung đột. Trước khi chuyển backend từ zonal sang regional, phải xác nhận vùng, quota, IP/subnet và chính sách phân phối. Tham số zone phải thuộc region được chọn và được dự án/machine type hỗ trợ.

### 6.2. Gắn regional MIG vào backend service

Một backend service **tương thích** có thể tham chiếu regional MIG:

~~~bash
# WRITE: chỉ dùng khi muốn gắn regional MIG thay cho backend khác
# hoặc khi backend service hỗ trợ thêm backend này theo topology.
gcloud compute backend-services add-backend retail-web-backend \
  --project=retail-lab \
  --global \
  --instance-group=retail-web-regional \
  --instance-group-region=asia-southeast1 \
  --balancing-mode=UTILIZATION \
  --max-utilization=0.80
~~~

Không gắn hai instance groups chứa **cùng tập VM thực tế** hoặc cấu hình backend chồng chéo không được hỗ trợ. Khi muốn di chuyển traffic từ nhóm cũ sang nhóm mới, lên kế hoạch **migration/rollout** kiểm soát, xem khả năng sử dụng backend weights/capacity scalers theo loại load balancer.

### 6.3. Regional MIG chưa phải chiến lược đa region

Nếu muốn chịu được sự cố **cả region**, cần thêm các backend ở region khác và xem:

- Global load balancer có thể dùng backend từ những region đó như thế nào.
- Dữ liệu Cloud SQL/Cloud Storage và các phụ thuộc có sẵn ở region dự phòng không.
- IAM, VPC egress, firewall, TLS, quota và secrets đã được chuẩn bị chưa.
- Latency và chi phí truyền dữ liệu khi client được hướng tới region xa hơn.
- Có kiểm thử failover và kịch bản quay trở về sau sự cố không.

Chỉ đưa VM sang zone khác không bảo vệ được một database chỉ nằm trên một instance hoặc một region duy nhất.

## 7. Autoscaling: từ CPU đến load balancing utilization

### 7.1. Autoscaler thay đổi điều gì?

**MIG autoscaler** quan sát tín hiệu đã cấu hình, tính **recommended size** rồi điều chỉnh số instance trong nhóm, trong khoảng **min/max replicas**. Autoscaler có thể dựa trên CPU utilization, load balancing serving capacity, Cloud Monitoring metrics hoặc schedule tùy loại MIG/tính năng hiện hành.

Ví dụ, một hệ thống thường cần hai VM, cao điểm cần tám VM:

~~~text
Min replicas: 2
Max replicas: 8

10:00 -> 2 VM
12:00 -> 5 VM (tải tăng)
13:00 -> 8 VM (nếu đạt giới hạn)
16:00 -> 3 VM (tải giảm, sau stabilization)
~~~

Sơ đồ chỉ minh họa logic. **Scale out không tức thời**: cần tạo VM, boot image, chạy startup script, khởi động app và health check đủ điều kiện mới nhận traffic. **Scale in cũng có cơ chế ổn định/cooldown** để tránh dao động; chi tiết phụ thuộc cấu hình và sản phẩm.

### 7.2. Autoscaling theo CPU

Đối với backend xử lý chủ yếu bằng CPU, có thể đặt CPU target:

~~~bash
# WRITE: đặt autoscaler với min 2, max 8 VM, mục tiêu CPU 60%.
gcloud compute instance-groups managed set-autoscaling retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --min-num-replicas=2 \
  --max-num-replicas=8 \
  --target-cpu-utilization=0.60
~~~

Target `0.60` được hiểu theo metric CPU utilization của VM theo cơ chế autoscaler, **không phải yêu cầu bảo đảm mọi VM luôn dưới 60% CPU ở mọi thời điểm**. Nếu ứng dụng bị giới hạn bởi network, disk I/O, kết nối database hoặc external API, CPU có thể thấp dù latency cao. Khi đó CPU là tín hiệu scale chưa đủ tốt.

### 7.3. Autoscaling theo HTTP load balancing serving capacity

Với MIG làm backend của HTTP(S) Application Load Balancer có hỗ trợ, autoscaler có thể dựa vào **load balancing utilization**: sử dụng mức tiêu thụ **serving capacity** của backend như tín hiệu quyết định số VM cần thiết.

~~~bash
# WRITE: lựa chọn THAY THẾ cho cấu hình CPU autoscaling trong lab.
# Cần có backend service và serving capacity hợp lệ.
gcloud compute instance-groups managed set-autoscaling retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --min-num-replicas=2 \
  --max-num-replicas=8 \
  --target-load-balancing-utilization=0.70
~~~

Ở mô hình này:

- **Backend service** cần cấu hình capacity/balancing mode phù hợp với loại LB.
- **Autoscaler** quan sát utilization dựa trên LB serving capacity; `0.70` biểu thị mục tiêu 70% của capacity theo mô hình metric đó, **không phải 70% CPU**.
- Capacity mà LB tính có thể phụ thuộc balancing mode và thông số backend (`UTILIZATION`, `RATE`, giới hạn request...) cũng như loại LB; không mặc định rằng mọi backend đều có cùng công thức.
- Một MIG có thể dùng nhiều signals theo những chế độ được hỗ trợ, và autoscaler xét yêu cầu capacity từ các signals đó; không nên chạy nhiều lần `set-autoscaling` với những flags khác nhau rồi nghĩ chúng tự cộng tất cả policy theo ý muốn.

Để chọn target, phải đo quan hệ giữa request rate, latency, mức sử dụng tài nguyên và số VM. Nếu target quá cao, VM có thể quá tải trước khi kịp scale; nếu quá thấp, chi phí tăng do nhiều VM chờ.

### 7.4. Phân biệt autoscaler target và backend max utilization

Giả sử:

~~~text
Backend service:
  balancingMode: UTILIZATION
  maxUtilization: 0.80

MIG autoscaler:
  targetLoadBalancingUtilization: 0.70
  minNumReplicas: 2
  maxNumReplicas: 8
~~~

Hai con số phục vụ **những mục tiêu khác nhau**:

- `maxUtilization` là **tham số capacity/phân phối tải của backend service**.
- `targetLoadBalancingUtilization` là **mục tiêu của autoscaler** khi đánh giá mức dùng serving capacity.

Chúng không phải hai ngưỡng CPU đặt vào nhau một cách đơn giản. Đọc metrics của backend service/auto scaler đang dùng và thử nghiệm load test để hiệu chỉnh.

### 7.5. Min/max, stabilization và startup time

Trong một ứng dụng production, autoscaler còn cần:

1. **Min replicas** đủ cho tải nền, patch/rolling update và dự phòng khi một VM không khỏe.
2. **Max replicas** theo quota, ngân sách và giới hạn tài nguyên downstream như Cloud SQL connection pool.
3. **Initialization period** gần với thời gian VM chuẩn bị sẵn sàng; tránh diễn giải sai metrics trong lúc boot.
4. **Scale-in stabilization và controls** để không xóa nhanh VM đang phục vụ long-running requests.
5. **Capacity headroom** cho đột biến trước khi VM mới kịp warm up.
6. **Load test** đo số request/second, p95/p99 latency và errors ở các kích thước nhóm.

Autoscaling không thể sửa ứng dụng bị deadlock, memory leak hoặc backend database đã hết connection. Tăng số VM đôi khi khiến database nghẽn nhanh hơn.

### 7.6. Kiểm tra autoscaler

~~~bash
# READ-ONLY: kiểm tra autoscalers.
gcloud compute autoscalers list --project=retail-lab

# READ-ONLY: cấu hình MIG và kích thước mục tiêu.
gcloud compute instance-groups managed describe retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --format="yaml(targetSize,autoscaler,status)"

gcloud compute instance-groups managed list-instances retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a
~~~

Trường CLI trả về có thể khác nhau theo phiên bản API, nhất là thông tin recommended size. Dùng `--format=yaml` để quan sát dữ liệu thực tế trước khi viết script phụ thuộc vào một trường.

## 8. Hai loại health check: load balancing và autohealing

### 8.1. Đừng nhầm “không nên nhận traffic” với “cần thay VM”

Ví dụ một VM đang khởi tạo cache:

- Nó có thể chưa đủ điều kiện nhận traffic HTTP (`/healthz = 503`).
- Nhưng process và guest OS đang hoạt động bình thường (`/livez = 200`).

Load balancer nên **ngừng gửi request mới** nếu `/healthz` thất bại. MIG autohealing không nhất thiết phải thay VM ngay, nhất là khi lỗi chỉ là tình trạng tạm thời của dependency. Hai cơ chế có mục đích khác nhau.

| Cơ chế | Cấu hình chính | Quyết định |
| --- | --- | --- |
| **LB health check** | Gắn trên backend service. | Backend instance có nên nhận traffic không. |
| **MIG autohealing health check** | Gắn trên MIG autohealing policy. | VM có nên được repair/recreate không. |

Có thể dùng cùng health check nếu tiêu chí phù hợp, nhưng trong nhiều hệ thống nên **tách readiness và liveness**, có ngưỡng và initial delay thích hợp để giảm vòng lặp thay máy không cần thiết.

### 8.2. Ví dụ cấu hình autohealing

~~~bash
# WRITE: health check tương đối nhẹ để MIG đánh giá VM.
gcloud compute health-checks create http retail-web-repair-hc \
  --project=retail-lab \
  --global \
  --port=8080 \
  --request-path=/livez

# WRITE: gắn health check vào chính MIG.
gcloud compute instance-groups managed set-autohealing retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --health-check=retail-web-repair-hc \
  --initial-delay=300
~~~

`--initial-delay=300` chỉ minh họa **khoảng chờ ban đầu để VM khởi tạo**; phải đo thời gian boot thật và điều chỉnh. Một VM có startup script mất 8 phút có thể bị coi không khỏe quá sớm nếu đặt delay ngắn.

### 8.3. Những lỗi thiết kế health check

- Health endpoint luôn trả 200 ngay cả khi process chính không hoạt động: LB vẫn gửi traffic vào backend lỗi.
- Endpoint kiểm tra database bằng truy vấn nặng: toàn bộ VM có thể cùng báo unhealthy khi DB chậm.
- Health check dùng path đòi login hoặc token không được health checker cung cấp.
- Ứng dụng chỉ bind `127.0.0.1:8080`, nên health checker từ mạng không tới được.
- Firewall chặn nguồn health checker, dù `curl localhost:8080/healthz` trên VM thành công.
- Autohealing quá nhạy khiến VM liên tục bị recreate, càng làm capacity giảm.

**Luôn kiểm tra từ cả góc nhìn guest OS và backend service.** Kiểm tra localhost chỉ chứng minh process đã mở cổng trên máy, không chứng minh health checker có đường đi tới địa chỉ VPC.

## 9. Rolling update, connection draining và triển khai an toàn

### 9.1. Cập nhật image/template theo phiên bản

Thay đổi mã ứng dụng nên đi theo:

~~~mermaid
flowchart LR
    BUILD["CI tạo image/artifact"] --> TMP["Instance template v2"]
    TMP --> PLAN["Review rollout policy"]
    PLAN --> MIG["MIG rolling update"]
    MIG --> BOOT["VM mới khởi động"]
    BOOT --> H["Health check sẵn sàng"]
    H --> LB["Load balancer nhận traffic"]
    LB --> OBS["Theo dõi latency/errors"]
    OBS --> DEC{"Đạt SLO?"}
    DEC -- "Không" --> RB["Rollback phiên bản"]
    DEC -- "Có" --> DONE["Hoàn tất rollout"]
~~~

Instance template mới **không tự thay các VM cũ ngay**. MIG cần một lệnh cập nhật phiên bản hoặc rollout theo API/CLI/IaC được tổ chức dùng. Đội vận hành cần kiểm soát tốc độ thay máy, số VM tạm thêm và số VM có thể không sẵn sàng trong mỗi đợt.

### 9.2. Ví dụ rolling update có kiểm soát

Giả sử template `retail-web-v2` đã được xây, kiểm thử và đăng ký:

~~~bash
# WRITE: bắt đầu rolling update; chỉ dùng sau khi review template v2.
gcloud compute instance-groups managed rolling-action start-update retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --version=template=retail-web-v2 \
  --max-surge=1 \
  --max-unavailable=0

# READ-ONLY: theo dõi quá trình thay instance.
gcloud compute instance-groups managed list-instances retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a
~~~

Các cờ `max-surge` và `max-unavailable` minh họa mong muốn thay từng ít VM mà duy trì capacity. Cần kiểm tra khả năng cấp tài nguyên theo quota và sự phù hợp với zonal/regional MIG. **Không bảo đảm zero downtime chỉ từ `max-unavailable=0`**: request đang mở, load balancer health và trạng thái ứng dụng vẫn có thể gây lỗi.

### 9.3. Connection draining

Khi VM được loại khỏi backend, đang scale-in hoặc bị thay lúc rollout, có thể còn request đang xử lý. **Connection draining** của backend service giúp backend có một khoảng thời gian xử lý kết nối/tác vụ đang tồn tại theo cách sản phẩm hỗ trợ.

~~~bash
# WRITE: ví dụ đặt thời gian draining 60 giây trên backend service.
gcloud compute backend-services update retail-web-backend \
  --project=retail-lab \
  --global \
  --connection-draining-timeout=60s
~~~

Ứng dụng cũng nên xử lý tín hiệu dừng, ngừng nhận việc mới và hoàn thành/rollback công việc phù hợp. Nếu một request có thể chạy 5 phút nhưng draining timeout chỉ 60 giây, vẫn có nguy cơ request bị cắt. Chọn thời gian theo giao thức, khối lượng tải, chi phí và đặc tính backend.

Với công việc nền lâu hoặc xử lý hàng đợi, không phụ thuộc hoàn toàn vào connection draining của HTTP load balancer; hãy dùng checkpoint, idempotency và cơ chế giao lại job.

### 9.4. Blue/green và canary

Đối với thay đổi lớn, đội vận hành có thể duy trì:

- **Blue MIG** chạy bản đang ổn định.
- **Green MIG** chạy bản mới và đã vượt qua smoke/health checks.
- **Backend services hoặc cơ chế URL traffic splitting** theo khả năng load balancer để điều phối traffic.

Khi triển khai canary, theo dõi riêng lỗi/latency của bản mới; đừng đánh giá chung nếu tỷ lệ traffic quá thấp hoặc request mix khác biệt. Tính năng chia trọng số, capacity scaler và session affinity phụ thuộc loại load balancer; phải kiểm tra cụ thể trước khi chọn công cụ rollout.

## 10. Tình huống production: website bán lẻ đa zone

### 10.1. Yêu cầu nghiệp vụ

Giả sử `shop.example.com` phục vụ người mua hàng:

- Frontend HTTPS public, backend web trên Compute Engine.
- Giờ thấp điểm vài trăm request/phút, cao điểm tăng nhanh theo chiến dịch.
- Yêu cầu chịu lỗi của một VM và giảm rủi ro khi một zone gặp sự cố.
- Dữ liệu đơn hàng nằm ở **Cloud SQL**, ảnh sản phẩm ở **Cloud Storage**.
- Nhóm DevOps phát hành phiên bản mới qua CI/CD, không dùng SSH sửa từng VM.
- Phải theo dõi latency, tỷ lệ lỗi và chi phí VM/load balancer.

### 10.2. Thiết kế đề xuất

| Thành phần | Lựa chọn minh họa | Lý do |
| --- | --- | --- |
| Frontend | Global external Application Load Balancer HTTPS. | TLS, một domain, URL routing, backend đa zone. |
| Nhóm VM | Regional MIG trong `asia-southeast1` qua ít nhất hai zone. | Giảm phụ thuộc một zone. |
| Instance template | Image ứng dụng đã kiểm thử, `e2-*` hoặc loại máy phù hợp load test. | VM mới đồng nhất, boot nhanh. |
| Named port | `http:8080`. | Backend service tìm đúng cổng ứng dụng. |
| Backend health | `/healthz` trên HTTP 8080. | Chỉ chuyển request tới instance sẵn sàng. |
| MIG autohealing | `/livez` và initial delay phù hợp. | Thay VM thực sự lỗi mà không quá nhạy. |
| Autoscaler | Min capacity cho tải nền, max theo quota/cost, tín hiệu CPU/LB sau benchmark. | Cân bằng chi phí và latency. |
| Dữ liệu | Cloud SQL/Storage/Secret Manager, không dùng boot disk làm kho dữ liệu duy nhất. | VM thay được mà không mất dữ liệu. |
| Networking | Backend không có external IP nếu không cần, egress tối thiểu và firewall theo loại LB. | Hạn chế bề mặt tấn công. |
| Observability | Backend health, requests/5xx, p95/p99, autoscaler/MIG, Cloud SQL bottlenecks. | Phát hiện nguyên nhân thật và đánh giá SLO. |

### 10.3. Đường đi của một request

~~~mermaid
sequenceDiagram
    participant C as Browser
    participant L as HTTPS Load Balancer
    participant B as Backend service
    participant V as VM trong regional MIG
    participant D as Cloud SQL
    C->>L: GET /products/42
    L->>B: URL map chọn web backend
    B->>B: Chọn healthy VM theo capacity
    B->>V: HTTP tới named port
    V->>D: Truy vấn dữ liệu theo danh tính/DB auth
    D-->>V: Kết quả
    V-->>C: HTTP response đi qua load balancer
~~~

Sơ đồ lược bỏ nhiều bước mạng, TLS và quyền. VM phải có **đường kết nối database, authentication và quyền SQL**, không chỉ cần load balancer healthy. Nếu Cloud SQL quá tải, mở rộng MIG bằng thêm VM có thể làm vấn đề kết nối database nghiêm trọng hơn.

### 10.4. Diễn tập ba sự cố

**VM chết:** một instance ngừng phục vụ `/healthz`. Load balancer ngừng dùng backend theo health criteria; MIG autohealing có thể thay VM khi kiểm tra lỗi tương ứng. Quan sát thời gian thay thế và năng lực của VM còn lại.

**Một zone không sẵn có:** regional MIG còn những VM ở zone khác nếu capacity và phân phối đã được thiết kế. Kiểm thử số request lỗi, hệ thống phụ thuộc và cách MIG phục hồi phân phối sau sự cố.

**Traffic tăng gấp nhiều lần:** autoscaler cần thời gian tạo VM; đo p95/p99 latency trong giai đoạn warm-up, theo dõi max replicas và quota. Nếu DB connection pool bị tràn, tăng VM không phải giải pháp duy nhất.

## 11. Bảo mật, IAM và trách nhiệm vận hành

### 11.1. Phân tách danh tính

Không dùng một service account quyền rộng cho cả CI/CD và runtime:

| Principal | Nhiệm vụ | Quyền cần thiết |
| --- | --- | --- |
| **CI/CD deployer** | Tạo template, cập nhật MIG và backend config theo quy trình. | Role được giới hạn cho các tài nguyên hạ tầng cần chỉnh, quyền sử dụng service account khi áp dụng. |
| **VM runtime service account** | Gọi Cloud Storage, Cloud SQL Admin APIs hoặc Secret Manager khi app cần. | Permission tối thiểu trên đúng dữ liệu/API; database privileges tách riêng. |
| **SRE/on-call** | Xem logs, health, metrics và điều tra instance. | Viewer/monitoring/logging thích hợp, quyền bảo trì có kiểm soát. |
| **Network/security team** | Quản lý firewall, certificates, Cloud Armor/policies. | Vai trò chuyên trách và phê duyệt thay đổi nhạy cảm. |

Quyền truy cập dữ liệu không được sinh ra từ việc ứng dụng nằm sau HTTPS load balancer. **TLS frontend bảo vệ đường client–LB**, còn từ load balancer tới backend dùng protocol và chính sách mạng riêng; có thể chọn các phương án mã hóa backend nếu yêu cầu hỗ trợ.

### 11.2. Cloud Armor, IAP, Cloud CDN

Tùy loại Application Load Balancer:

- **Cloud Armor** có thể bảo vệ ứng dụng trước một số dạng traffic độc hại và áp chính sách truy cập tại edge.
- **Identity-Aware Proxy** có thể phù hợp ứng dụng nội bộ cần xác thực người dùng, theo topology và tính tương thích.
- **Cloud CDN** hữu ích cho ảnh/tài nguyên cacheable, nhưng cần cache policy để không vô tình cache dữ liệu cá nhân hoặc nội dung giỏ hàng.

Không mặc định mọi tính năng đều có thể bật đồng thời trên cùng backend service; kiểm tra hỗ trợ theo loại load balancer, giao thức và sản phẩm hiện tại.

### 11.3. Trạng thái và session

Một kiến trúc scale-out tốt nên **hạn chế lưu session trên RAM của VM**. Khi request tiếp theo được đưa sang VM khác hoặc một VM bị thay, session có thể không còn.

Các lựa chọn gồm token/session phù hợp được xác minh phía server, kho lưu phiên dùng chung hoặc mô hình ứng dụng stateless. **Session affinity** của load balancer có thể hỗ trợ một số trường hợp, nhưng không phải cam kết một user luôn gắn với một VM sau lỗi, rollout hay scaling. Không dùng affinity thay cho thiết kế trạng thái bền vững.

## 12. Giám sát: VM khỏe chưa đủ, người dùng phải thành công

### 12.1. Các tín hiệu cần theo dõi

| Tầng | Tín hiệu | Câu hỏi |
| --- | --- | --- |
| Frontend LB | Requests, HTTP 4xx/5xx, TLS errors, latency. | Người dùng có truy cập được không? |
| Backend service | Số instance healthy/unhealthy, request distribution, backend latency. | Lỗi đến từ backend nào? |
| MIG | Target size, actual size, recreation, rolling update state. | Có đủ VM sẵn sàng theo chính sách không? |
| Autoscaler | Recommended/current capacity, signal CPU/LB, min/max saturation. | Có bị giới hạn hoặc tăng/giảm quá chậm không? |
| VM | CPU, memory, disk I/O, startup logs, process health. | Tài nguyên guest có bị nghẽn không? |
| Dependency | Cloud SQL connections/latency, Cloud Storage errors, cache saturation. | Điểm nghẽn có nằm ngoài VM không? |
| Nghiệp vụ | Checkout success rate, p95/p99 latency, lỗi thanh toán. | SLO đầu cuối có đạt không? |

Các chỉ số autoscaler có thể không xuất hiện ngay sau khi tạo tài nguyên. Khi phân tích, kiểm tra **thời gian cập nhật metrics, thời gian warm-up và tình trạng health**. Đặt alerts theo tác động người dùng thay vì chỉ báo động khi một VM bị thay.

### 12.2. Những cảnh báo nên có

- Healthy backend count xuống dưới capacity tối thiểu trong một khoảng đáng kể.
- Tỷ lệ 5xx/p95 latency tăng vượt SLO.
- Autoscaler chạm `maxNumReplicas` trong khi request backlog tiếp tục tăng.
- MIG không đạt target size do quota hoặc lỗi startup.
- Quá nhiều lần autohealing/recreate trong cùng một khoảng thời gian.
- Độ trễ/connection errors từ Cloud SQL tăng sau scale-out.
- Ngân sách VM/load balancing/logging có xu hướng vượt ngưỡng.

Một request HTTP lỗi trong lúc deployment chưa đủ làm cảnh báo khẩn; cần xem tỷ lệ, độ dài sự cố, mức độ ảnh hưởng và cam kết SLO thực tế.

### 12.3. Kiểm tra bằng lệnh đọc

~~~bash
# READ-ONLY: xem các nhóm VM.
gcloud compute instance-groups managed list \
  --project=retail-lab

# READ-ONLY: xem cấu hình MIG và instance trạng thái.
gcloud compute instance-groups managed describe retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a

gcloud compute instance-groups managed list-instances retail-web-mig-a \
  --project=retail-lab \
  --zone=asia-southeast1-a

# READ-ONLY: kiểm tra backend service và health.
gcloud compute backend-services describe retail-web-backend \
  --project=retail-lab --global

gcloud compute backend-services get-health retail-web-backend \
  --project=retail-lab --global

# READ-ONLY: kiểm tra autoscaler và các health checks.
gcloud compute autoscalers list --project=retail-lab
gcloud compute health-checks list --project=retail-lab
~~~

Những lệnh này giả định tài nguyên ví dụ đã được tạo. Nếu bạn triển khai bằng regional scope, tham số `--region` thay vì `--global`/`--zone` được dùng tùy API cụ thể. Kết quả không đầy đủ nếu tài khoản chưa có IAM permission xem tài nguyên.

## 13. Troubleshooting: xử lý từ phía ngoài vào trong

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra trước |
| --- | --- | --- |
| Frontend không nhận HTTP(S) | DNS/forwarding rule sai, IP/chứng chỉ/TLS/proxy chưa đúng. | Forwarding rule, target proxy, URL map, DNS và certificate. |
| LB trả `502` hoặc `503` | Backend unhealthy, VM chưa chạy app, timeout, hết capacity hoặc route sai. | Backend service `get-health`, VM logs, health check và network. |
| MIG có 2 VM nhưng `get-health` báo unhealthy | Startup script lỗi, app không bind cổng, named port hoặc health path sai. | `list-instances`, port, path, boot logs. |
| `curl localhost:8080/healthz` được nhưng LB không thấy healthy | Firewall nguồn health checker/proxy bị chặn hoặc backend protocol/port mismatch. | VPC firewall, health check config, named ports. |
| Autoscaler không scale dù latency cao | Tín hiệu CPU/LB không phản ánh nghẽn, autoscaler chưa bật hoặc đã tới max. | Autoscaler config, metrics, max replicas, DB bottleneck. |
| VM mới tạo nhưng không nhận traffic | Startup chưa xong, health check đang unhealthy, wrong network/tag. | Guest logs, readiness, health, firewall. |
| MIG liên tục thay VM | Autohealing `/livez` quá nhạy, initial delay nhỏ, image lỗi. | Autohealing health check, repair events, startup duration. |
| Rolling update làm giảm capacity | Surge/unavailable policy, quota thiếu, app startup lâu, draining không đủ. | Rolling update state, instance health, backend logs. |
| VM giảm sau giờ cao điểm nhưng người dùng lỗi | Scale-in quá nhanh, session cục bộ, request dài bị cắt. | Stabilization, connection draining, session design. |
| Scale-out khiến Cloud SQL quá tải | Mỗi VM mở nhiều DB connections hoặc pool không giới hạn. | DB metrics, connection pooling, max replicas. |
| Chi phí không giảm khi traffic thấp | Min replicas cao, VM/disk còn tồn tại, LB/logging/egress vẫn tính phí. | Cloud Billing, MIG target, disk, network. |
| Health xanh nhưng checkout thất bại | Health endpoint không kiểm tra luồng nghiệp vụ hoặc dependency. | SLI nghiệp vụ, Cloud SQL, ứng dụng và end-to-end synthetic tests. |

### 13.1. Sáu bước điều tra hữu ích

1. **Frontend:** xác định đúng IP, port, TLS, target proxy và URL map.
2. **Backend service:** kiểm tra instance group đã gắn đúng, scope global/regional và named port.
3. **Health check:** đọc path/port/protocol và kết quả `get-health`.
4. **Mạng:** kiểm tra firewall và route từ nguồn load balancer/proxy tới IP backend.
5. **VM/MIG:** xem process, startup script, instance status, autohealing, autoscaler và rolling update.
6. **Ứng dụng:** đối chiếu logs, request ID, database, Cloud Storage và tỷ lệ hoàn thành nghiệp vụ.

Đừng sửa autoscaler hoặc tăng min replicas nếu bản chất là một health check sai cổng. Ngược lại, đừng mở toàn bộ firewall chỉ vì backend chưa healthy.

## 14. Độ tin cậy, năng lực và chi phí

### 14.1. Tăng số VM không đồng nghĩa tăng throughput tuyến tính

Một ứng dụng có thể đạt 100 request/giây trên một VM, nhưng 10 VM chưa chắc đạt 1.000 request/giây. Nguyên nhân:

- Database có giới hạn số kết nối hoặc truy vấn.
- Shared cache, rate limits hoặc dịch vụ bên ngoài là điểm nghẽn.
- Truyền dữ liệu liên zone/region làm tăng latency/chi phí.
- Session affinity phân phối không đều.
- Một phần workload không thể chạy song song hiệu quả.

Hãy benchmark theo **throughput hữu dụng với p95/p99 latency và lỗi trong giới hạn**; không chỉ dùng mức CPU hoặc số instance.

### 14.2. Các thành phần của chi phí

~~~text
Chi phí tổng ≈
  CPU/RAM VM theo loại máy và thời gian chạy
  + boot/data disks và snapshots
  + load balancer và lưu lượng xử lý
  + data transfer giữa vùng/ra ngoài
  + Cloud Logging/Monitoring, network services
  + dịch vụ dữ liệu (Cloud SQL/Storage/Cache)
  + dự phòng/surge capacity trong rollout
~~~

Đây là mô hình tư duy, không phải công thức tính hóa đơn chính thức. Một MIG autoscale từ 2 đến 8 VM có thể tối ưu giờ thấp điểm, nhưng **min replicas, disks, load balancer và các tài nguyên phụ trợ vẫn phát sinh chi phí**. Theo dõi chi phí trên mỗi request hoặc mỗi giao dịch thành công thay vì chỉ chi phí mỗi VM.

### 14.3. Chọn giới hạn dựa trên SLO

Ví dụ sau chỉ là dữ liệu giả định để lập kế hoạch:

| Tham số | Giá trị giả định | Cần kiểm chứng |
| --- | --- | --- |
| Latency SLO | 95% request dưới 300 ms. | Đã đo từ phía client hay chỉ backend? |
| Tải nền | 200 request/phút. | Mức min capacity đủ không? |
| Tải cao điểm | 3.000 request/phút. | VM nào chịu được bao nhiêu request ở p95 mong muốn? |
| VM warm-up | 2 phút. | Startup script, image download và health probes? |
| Min/max replicas | 2/8. | Quota, cost, khả năng chịu lỗi và DB connection pool? |
| Độ trễ scale-out | Nhiều phút tùy hạ tầng. | Có cần schedule/min headroom trước chiến dịch không? |

Đừng chọn `maxNumReplicas=8` chỉ vì một số tròn; cần chứng minh qua load test và tác động tới downstream. Autoscaling tối ưu **tài nguyên tính toán**, nhưng SLO yêu cầu thiết kế toàn chuỗi request.

## 15. Bài tập thực hành

### Bài 1 — Vai trò từng thành phần

Một kỹ sư nói: “MIG đã có ba VM, vậy HTTPS load balancer tự có frontend và URL map.” Hãy giải thích vì sao nhận định sai. Liệt kê các tài nguyên cần có từ frontend đến backend, và MIG chịu trách nhiệm phần nào.

**Gợi ý:** MIG quản lý VM; frontend IP/forwarding rule, proxy, URL map, backend service, health checks và firewall thuộc cấu hình load balancing/network khác.

### Bài 2 — Named port mismatch

Trong MIG, named port là `http:8080`; process lại nghe `9090`, health check dùng `8080`. Hãy giải thích vì sao MIG VM vẫn `RUNNING` nhưng backend unhealthy. Đề xuất cách sửa mà không mở firewall rộng.

### Bài 3 — Chọn autoscaler signal

Website gọi Cloud SQL rất nhiều, latency tăng khi có 200 concurrent requests nhưng CPU của VM chỉ 25%. Autoscaler theo CPU 60% có thể phản ứng thế nào? Có nên tăng VM vô hạn không?

**Gợi ý:** CPU target có thể không kích hoạt scale-out; cần kiểm tra connection pool, SQL latency và xem load balancing/custom metric phù hợp. Thêm VM có thể tạo thêm DB connections.

### Bài 4 — Zonal vs regional MIG

Một webshop cần chịu lỗi một zone tại `asia-southeast1`. Hãy chọn zonal hay regional MIG và giải thích giới hạn. Nếu muốn tiếp tục hoạt động khi cả region lỗi, còn cần những gì ngoài MIG?

### Bài 5 — LB health check và autohealing

VM không kết nối được Cloud SQL trong 20 giây; `/healthz` trả 503 nhưng `/livez` vẫn 200. Load balancer và MIG autohealing nên phản ứng như thế nào để vừa tránh gửi traffic lỗi vừa không tạo vòng lặp replace VM?

### Bài 6 — Diễn tập rolling update

MIG có min size 2, bản v1 đang chạy tốt. Hãy lập trình tự phát hành v2, kiểm tra health, đặt surge/unavailable, connection draining, đo p95/5xx và rollback khi vượt ngưỡng. Vì sao `max-unavailable=0` chưa đủ để hứa zero downtime?

### Bài 7 — Tính năng lực phục vụ

Một VM chịu ổn định khoảng 150 request/phút tại SLO đã định; tải cao điểm 600 request/phút. Về mặt năng lực đơn giản, cần ít nhất bao nhiêu VM khỏe? Vì sao trong thực tế còn phải bổ sung headroom, dự phòng lỗi một VM, thời gian warm-up và giới hạn Cloud SQL?

**Gợi ý:** 600 / 150 = 4 VM khỏe trong điều kiện lý tưởng; production phải tính thêm các yếu tố nêu trên.

### Bài 8 — Giảm chi phí giờ thấp điểm

Bạn có budget giới hạn nhưng muốn sẵn sàng khi lượng traffic tăng nhanh. Hãy đề xuất min/max replicas, một tín hiệu autoscale có thể quan sát được, một phương án warm-up trước chiến dịch và bộ metrics để kiểm chứng rằng chi phí giảm mà SLO không bị ảnh hưởng.

## 16. Checklist vận hành và tài liệu chính thức

| Hạng mục | Điều cần đạt trước khi đưa vào production |
| --- | --- |
| **Thiết kế backend** | Instance template có version, startup ổn định, ứng dụng stateless hoặc dùng lưu trữ bền vững. |
| **MIG** | Chọn zonal/regional đúng yêu cầu, có target capacity và dự phòng phù hợp. |
| **Named ports** | Mapping trùng cổng ứng dụng và backend service. |
| **Loại load balancer** | Chọn đúng external/internal, Application/Network, global/regional theo nhu cầu. |
| **Backend service** | Group gắn đúng scope, balancing mode/capacity và health checks hợp lệ. |
| **Firewall** | Cho phép đúng nguồn health checker/proxy, đúng port, hạn chế truy cập trực tiếp. |
| **TLS/DNS** | HTTPS/certificate, forwarding rule và DNS khớp frontend production. |
| **Autohealing** | Có health check phù hợp, initial delay và kiểm thử fail/recovery. |
| **Autoscaling** | Min/max dựa trên load test, signal phản ánh tải, policy scale-in phù hợp. |
| **Rollout** | Image/template bất biến, rolling update và rollback, connection draining. |
| **Security** | IAM tối thiểu cho deployer, runtime service account và đội vận hành. |
| **Dependency** | Cloud SQL, Cloud Storage, secrets, network egress đủ capacity và quyền. |
| **Observability** | LB 5xx, latency, backend health, MIG state, autoscaler và SLI nghiệp vụ. |
| **Cost** | Theo dõi VM/disk/LB/egress/logging, alerts và chi phí mỗi giao dịch. |
| **Resilience** | Diễn tập VM loss/zone loss, kiểm tra có đường phục hồi dữ liệu và capacity. |

Tài liệu Google Cloud cần đối chiếu với phiên bản hiện hành:

- [Managed instance groups overview](https://cloud.google.com/compute/docs/instance-groups)
- [Create managed instance groups](https://cloud.google.com/compute/docs/instance-groups/creating-groups-of-managed-instances)
- [MIG autoscaling overview](https://cloud.google.com/compute/docs/autoscaler)
- [Autoscale based on HTTP(S) load balancing serving capacity](https://cloud.google.com/compute/docs/autoscaler/scaling-based-on-load-balancing)
- [MIG autohealing](https://cloud.google.com/compute/docs/instance-groups/autohealing-instances-in-migs)
- [Rolling out updates to MIGs](https://cloud.google.com/compute/docs/instance-groups/rolling-out-updates-to-managed-instance-groups)
- [Cloud Load Balancing overview](https://cloud.google.com/load-balancing/docs/load-balancing-overview)
- [External Application Load Balancer overview](https://cloud.google.com/load-balancing/docs/https)
- [Health checks concepts](https://cloud.google.com/load-balancing/docs/health-check-concepts)
- [Firewall rules for load balancing](https://cloud.google.com/load-balancing/docs/firewall-rules)
- [gcloud compute instance-groups managed](https://cloud.google.com/sdk/gcloud/reference/compute/instance-groups/managed)
- [gcloud compute backend-services](https://cloud.google.com/sdk/gcloud/reference/compute/backend-services)

**Điểm cần nhớ:** MIG quản lý **vòng đời và số lượng VM**; Cloud Load Balancing quản lý **đường vào và phân phối traffic đến backend khỏe**; autoscaler điều chỉnh **capacity theo tín hiệu tải**. Hệ thống chỉ thực sự sẵn sàng khi chúng được nối đúng qua named ports, backend services, health checks và firewall, đồng thời ứng dụng có quy trình phát hành, lưu trạng thái và quan sát SLO rõ ràng.
