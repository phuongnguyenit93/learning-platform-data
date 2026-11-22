# Managed instance groups theo zone và region

Giả sử một ứng dụng Java đang chạy trên một máy ảo Compute Engine. Khi số lượng người dùng tăng, máy có thể quá tải; nếu VM bị lỗi hoặc zone gặp sự cố, website ngừng phục vụ. Tạo thủ công vài VM khác giúp tăng năng lực xử lý, nhưng nhóm vận hành lại phải tự đồng bộ phiên bản phần mềm, thay máy hỏng và cập nhật từng VM. **Managed instance groups (MIGs)** giải quyết bài toán đó bằng cách quản lý nhiều máy ảo như một nhóm có cấu hình, số lượng và vòng đời thống nhất.

Trong Google Cloud, MIG có thể được triển khai tại **một zone (zonal MIG)** hoặc **nhiều zone trong cùng một region (regional MIG)**. Sự khác nhau này ảnh hưởng trực tiếp tới khả năng chịu lỗi, phân bổ công suất, quota, chi phí và thiết kế load balancing. Đây là trọng tâm của bài học thuộc chương **Nhóm máy ảo và tự động mở rộng** của học phần **CLOUD_PROVIDERS_GCP**: lựa chọn dịch vụ Google Cloud, bảo vệ tài nguyên bằng IAM/VPC, triển khai ứng dụng, tự động hóa phát hành, theo dõi độ tin cậy và chi phí.

Sau bài này, bạn có thể:

- Phân biệt **zonal MIG**, **regional MIG** và **unmanaged instance group**.
- Tạo và sử dụng **instance template**, hiểu tính bất biến và vòng đời của các máy được quản lý.
- Chọn số zone, target distribution shape và chính sách phân phối phù hợp.
- Phân biệt **autoscaling**, **autohealing**, **load balancing** và **rolling updates**.
- Tạo MIG bằng Console hoặc `gcloud`, quan sát số VM thực tế và lỗi cấp phát.
- Thiết kế một dịch vụ Java có khả năng chịu lỗi zone, đáp ứng traffic tăng và kiểm soát chi phí.

## 1. MIG là gì?

**Managed instance group** là một tài nguyên Compute Engine quản lý một tập VM dựa trên cấu hình chung, thông thường là **instance template**. MIG có thể chủ động tạo VM, thay thế VM lỗi, điều chỉnh số lượng khi bật autoscaler và cập nhật cấu hình qua rolling update.

~~~mermaid
flowchart TD
    A["Instance template: OS, machine type, network, startup"] --> B["Managed instance group"]
    B --> C["VM instance 1"]
    B --> D["VM instance 2"]
    B --> E["VM instance 3"]
    F["Autoscaler: tải và min/max"] --> B
    G["Autohealing: application health check"] --> B
    H["Updater: template v2 / rolling update"] --> B
    I["Load Balancer"] --> C
    I --> D
    I --> E
~~~

### Các khái niệm cơ bản

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Instance template** | Bản mẫu VM: machine type, boot disk, image, NIC, service account, startup script | `java-api-template-v1` |
| **MIG manager** | Tài nguyên điều phối VM theo cấu hình, target size và policy | `orders-api-mig` |
| **Target size** | Số lượng VM mà nhóm muốn duy trì khi không có autoscaler, hoặc số do autoscaler quyết định | 6 |
| **Managed instance** | VM do MIG quản lý; tên thường có hậu tố riêng | `orders-api-x7k2` |
| **Autoscaler** | Điều chỉnh số VM theo CPU, load-balancing capacity, metrics hoặc lịch | Min 3, max 12 |
| **Autohealing** | Phát hiện VM không khỏe theo health check và thay thế theo policy | HTTP `/healthz` không trả thành công |
| **Updater** | Thực hiện thay đổi VM theo template/versions và mức độ gián đoạn cho phép | Rolling update v1 → v2 |
| **Load balancer** | Phân phối request đến các instance khỏe trong nhóm | External Application Load Balancer |

**MIG không tự là load balancer.** MIG quản lý VM; load balancer nhận và phân phối traffic tới các VM mà MIG cung cấp làm backend. **MIG cũng không mặc định có đủ mọi cơ chế**: autoscaling, application-based autohealing và cân bằng tải cần cấu hình tương ứng để hoạt động như mong muốn.

### MIG và unmanaged instance group

| Đặc điểm | Managed instance group | Unmanaged instance group |
|---|---|---|
| Tạo nhiều VM từ một mẫu | Có | Quản trị VM riêng |
| Autoscaling bằng MIG autoscaler | Hỗ trợ khi cấu hình cho loại workload tương thích | Không theo cơ chế MIG |
| Tự sửa lỗi VM theo health check | Có thể bật autohealing | Không có cơ chế MIG autohealing |
| Rolling update từ instance template | Hỗ trợ | Phải phối hợp quá trình thay VM riêng |
| VM khác nhau tùy ý | Bị ràng buộc bởi cấu hình nhóm, có ngoại lệ được hỗ trợ | Linh hoạt hơn |
| Phù hợp | Fleet VM tương đối đồng nhất, có thể thay thế | Tập VM khác nhau cần nhóm để quản trị hoặc làm backend |

MIG thích hợp nhất cho workload **stateless** như web frontend/API worker; cũng có các tính năng **stateful MIG** cho workload cần giữ một số tài nguyên/trạng thái, nhưng có hạn chế đáng kể với autoscaling và quản lý rolling update. Không nên hiểu việc đặt database vào MIG là tự động có replication, backup hoặc high availability ở cấp dữ liệu.

## 2. Zone và region: nền tảng của quyết định thiết kế

Một **region** là khu vực địa lý do Google Cloud cung cấp, thường chứa nhiều **zone**. Zone là miền triển khai có hạ tầng độc lập ở mức được dịch vụ thiết kế; dù cùng region, không nên giả định mọi zone có cùng mức sẵn có của machine type, GPU hoặc quota.

~~~text
Region: us-central1
├── Zone: us-central1-a
│   ├── VM A1
│   └── VM A2
├── Zone: us-central1-b
│   ├── VM B1
│   └── VM B2
└── Zone: us-central1-c
    ├── VM C1
    └── VM C2
~~~

Một hệ thống có 6 VM phân tán 2-2-2 thường có rủi ro khác đáng kể so với 6 VM đều ở zone `us-central1-a`. Nếu zone A mất khả dụng, các VM ở B và C có thể tiếp tục phục vụ. Tuy nhiên, ứng dụng, load balancer, database và mọi dịch vụ phụ thuộc cũng phải được thiết kế để chịu lỗi thì tính sẵn sàng đầu cuối mới được cải thiện.

## 3. Zonal MIG và regional MIG

| Tiêu chí | **Zonal MIG** | **Regional MIG** |
|---|---|---|
| Vị trí VM | Một zone | Nhiều zone đã chọn trong cùng region |
| Khả năng chịu lỗi zone | Không tự duy trì phục vụ khi toàn zone mất khả dụng | Các VM ở zone còn khỏe có thể tiếp tục xử lý |
| Mức điều phối | Một zone, dễ dự đoán vị trí | Phân phối theo target distribution shape |
| Quota/capacity | Phụ thuộc zone cụ thể | Có thể tận dụng nhiều zone, tùy distribution policy |
| Tính năng MIG cốt lõi | Template, autohealing, autoscaling, updates | Các tính năng tương ứng và tùy chọn phân phối theo zone |
| Giới hạn số VM mặc định | 1.000 VM | 2.000 VM |
| Trường hợp thường gặp | Dev, batch gắn một zone, workload có yêu cầu locality | Web/API production cần chịu lỗi một zone |

Các giới hạn VM nêu trên là **giới hạn mặc định được Google Cloud công bố**, có thể thay đổi theo cấu hình và chính sách tăng giới hạn; không đồng nghĩa quota dự án đã cho phép tạo từng ấy VM. 

### Khi chọn zonal MIG

- Môi trường dev/test có mục tiêu giảm phức tạp và chấp nhận rủi ro mất zone.
- Batch worker chỉ cần xử lý trong một zone vì dữ liệu đặt cùng zone.
- Cần kiểm soát chặt vị trí VM hoặc machine type chỉ có tại một zone.
- Nhóm đang học MIG trước khi xây kiến trúc nhiều zone.

### Khi chọn regional MIG

- Website và API phục vụ khách hàng cần giảm ảnh hưởng khi một zone lỗi.
- Muốn phân bổ tải Compute Engine qua các zone trong cùng region.
- Muốn tăng khả năng tìm tài nguyên sẵn có hoặc tận dụng reservation phù hợp.
- Sẵn sàng thiết kế external/internal load balancer, health checks và ứng dụng stateless.

**Regional MIG không phải multi-region MIG.** Nó chỉ triển khai trong **một region**. Nếu cả region mất khả dụng, một regional MIG đơn lẻ không duy trì dịch vụ ở region khác. Để chịu lỗi region, thông thường phải có triển khai riêng ở nhiều region và một mô hình phân phối/chuyển đổi lưu lượng phù hợp.

### Chọn zone của regional MIG khi tạo

Với regional MIG, có thể chọn các zone được phép dùng ngay khi tạo nhóm; nếu không chỉ định, Google Cloud thường chọn ba zone theo cấu hình mặc định. **Không thể thay đổi danh sách zone đã chọn bằng cách chỉnh trực tiếp regional MIG sau khi tạo**; cần hoạch định trước, hoặc xây lại nhóm/migration nếu muốn dùng zone khác. 

Không chỉ cân nhắc tên zone: kiểm tra hỗ trợ machine type, persistent disk, GPU/reservation nếu dùng; cấu hình subnet phải thuộc đúng region và không thể tùy ý thay network/subnet của MIG sau khi nó đã được tạo.

## 4. Regional MIG phân phối VM như thế nào?

Một regional MIG có **target distribution shape** quy định cách chọn zone khi tạo/xóa VM. Không nên đánh đồng “regional” với “luôn chia đều”.

| Shape | Cách chọn zone | Phù hợp |
|---|---|---|
| **EVEN** (mặc định) | Cố duy trì số instance mục tiêu giữa các zone chênh không quá 1 | API/web serving cần phân bố đều, HA |
| **BALANCED** | Cố phân bố tương đối đều nhưng ưu tiên zone còn capacity | Serving/batch cần chống cạn capacity tốt hơn |
| **ANY** | Chọn zone theo tài nguyên sẵn có và tận dụng reservation, không ưu tiên phân bố đều | Batch, workload ít đòi hỏi HA theo zone |
| **ANY_SINGLE_ZONE** | Đưa toàn bộ VM vào một zone được chọn | Tác vụ cần locality/độ trễ giữa VM thấp, chấp nhận rủi ro zone |



**Ví dụ với 6 VM, 3 zone:** `EVEN` hướng tới 2-2-2; `BALANCED` có thể thành 3-2-1 khi thiếu tài nguyên rồi điều chỉnh theo điều kiện; `ANY` có thể chênh nhiều hơn; `ANY_SINGLE_ZONE` đưa toàn bộ vào một zone. Đây là ví dụ minh họa phân bố, không cam kết hệ thống sẽ đặt đúng các tỷ lệ đó trong mọi thời điểm.

Điểm cần hiểu sâu:

- `EVEN` giữ mục tiêu phân bố nhưng **không bảo đảm cả 6 VM đều RUNNING** nếu một zone thiếu capacity; có thể thấy VM chưa tạo được trong zone cần thiết.
- `BALANCED` có thể đưa nhiều VM hơn vào zone còn nguồn lực, hữu ích với thiếu quota/capacity cục bộ.
- `ANY` và `ANY_SINGLE_ZONE` **không bảo đảm** ứng dụng còn chạy khi zone lớn nhất/chosen zone bị lỗi.
- Khi dùng `BALANCED` hoặc `ANY_SINGLE_ZONE`, cần tắt **proactive instance redistribution** theo điều kiện của Google Cloud; kiểm tra khả năng hỗ trợ autoscaling, canary update và instance flexibility cho từng shape. 
- **Instance flexibility** cho phép chọn machine type thay thế theo thứ tự ưu tiên khi được hỗ trợ, ví dụ `e2-standard-4` hoặc `n2-standard-4`, nhưng không hỗ trợ trên shape `EVEN`. 

### Proactive instance redistribution

Với regional MIG, **proactive redistribution** (mặc định bật khi phù hợp) chủ động cố đưa nhóm về phân bố mong muốn giữa các zone. Điều này có thể khiến MIG tạo/xóa một số instance trong quá trình tái cân bằng.

Nếu ứng dụng có tác vụ dài hoặc dữ liệu gắn với từng VM, việc di chuyển quá chủ động có thể gây gián đoạn. Cân nhắc tắt redistribution khi trường hợp sử dụng và shape cho phép, đồng thời đánh giá rủi ro phân bố không đều. **Redistribution không đồng nghĩa autoscaling**: một cơ chế đổi vị trí/phân bố VM, cơ chế kia đổi **tổng số** VM.

## 5. Instance template: bản mẫu máy ảo

Muốn tạo MIG, cần một **instance template** định nghĩa cấu hình VM. Ví dụ:

~~~text
Instance template: java-api-v1
├── machine type: e2-medium
├── boot disk: Debian Linux (hoặc custom image)
├── network/subnet: app-vpc / app-subnet
├── service account: java-api-runtime@...
├── tags/labels: java-api, environment=dev
├── metadata/startup-script: khởi động ứng dụng và health endpoint
└── image/version: artifact đã được kiểm tra
~~~

Một template có thể là **global** hoặc **regional**, tùy cách tạo. Với zonal MIG, dùng template phù hợp; với regional MIG, template phải hợp lệ trong tất cả zone mà nhóm định dùng hoặc được kết hợp tính năng phân phối phù hợp. Template **bất biến**: nếu cần sửa boot image, startup script hoặc machine type, thường tạo template mới và triển khai phiên bản mới vào MIG.

### Cần bảo đảm VM có thể khởi động giống nhau

- Dùng image/container artifact phiên bản cố định; tránh dựa vào bản `latest` thay đổi âm thầm.
- Startup script nên idempotent, có log, và lỗi khởi động phải thể hiện qua health check.
- Không đặt bí mật trong image, startup script hoặc instance metadata; dùng Secret Manager và danh tính workload khi phù hợp.
- Mỗi VM cần service account **quyền tối thiểu** cho Cloud Storage, Pub/Sub, Logging hoặc API thực tế.
- Dữ liệu phiên người dùng để ở database, object storage hoặc cache dùng chung thay vì trên boot disk có thể bị thay thế.
- Thiết lập shutdown/graceful termination và xử lý tín hiệu dừng cho ứng dụng trước rolling update/scale-in.

**Không lưu dữ liệu sống duy nhất trên VM stateless.** Autohealing hay rolling update có thể xóa và tạo lại VM; disk tạm, process và bộ nhớ trong RAM mất. Stateful MIG cho phép giữ một số resource stateful nhưng không thay cho thiết kế backup/replication của database.

## 6. Cách tạo zonal và regional MIG trong Console

Điều kiện: có project bật billing và Compute Engine API, một instance template phù hợp, quota CPU/disk/IP, VPC/subnet và quyền IAM. Với template gắn service account, người tạo cũng cần quyền được phép sử dụng service account đó.

1. Mở **Compute Engine → Instance groups → Create instance group**.
2. Chọn **New managed instance group** (stateless khi xây web/API thông thường).
3. Chọn hoặc tạo instance template; nhập tên MIG và số lượng VM mục tiêu.
4. Với **zonal MIG**, chọn **Single zone**, region và một zone cụ thể.
5. Với **regional MIG**, chọn **Multiple zones**, region và những zone cần dùng; chọn target distribution shape (thường bắt đầu với **Even** khi xây API HA).
6. Xem xét các phần **autoscaling**, **autohealing**, **instance lifecycle**, rolling update và tên instance.
7. Bấm **Create**, chờ operation hoàn thành; xem danh sách managed instances và tình trạng VM theo từng zone.

Chú ý: giao diện Console có thể bật autoscaling mặc định cho nhóm stateless; nếu cần bài lab giữ size cố định, kiểm tra chế độ autoscaling thay vì suy luận từ `target size` ban đầu. Việc tạo VM sẽ phát sinh chi phí.

## 7. Thực hành gcloud: tạo instance template và hai loại MIG

Ví dụ sau là **mẫu thao tác** trên project lab, không được chạy trên production khi chưa rà soát quota, quyền và chi phí. Thay Project ID, VPC, subnet, zone và đường dẫn file script bằng tài nguyên thật. Chỉ tạo **một trong hai** MIG tùy mục tiêu; hai ví dụ độc lập có thể tạo nhiều VM và phát sinh tiền.

### 7.1. Tạo instance template

Một VM web demo cần có ứng dụng đáp ứng HTTP/health check. Giả sử thư mục người thực hành có file `startup.sh` sau:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

# Mẫu lab cần Internet egress hoặc mirror nội bộ để cài packages.
apt-get update
apt-get install -y nginx
echo "Hello from a managed VM" >/var/www/html/index.html
echo "ok" >/var/www/html/healthz
systemctl enable --now nginx
~~~

Tạo template chung cho các VM:

~~~bash
PROJECT_ID="my-mig-lab-project"
REGION="us-central1"
ZONE="us-central1-a"
VPC="app-vpc"
SUBNET="app-subnet"
TEMPLATE="web-template-v1"

gcloud config set project "$PROJECT_ID"
gcloud services enable compute.googleapis.com

# app-vpc và app-subnet phải được tạo trước, phù hợp với REGION.
# --no-address hạn chế public IP của VM; cần NAT/egress phù hợp
# nếu startup script tải packages từ Internet.
gcloud compute instance-templates create "$TEMPLATE" \
  --machine-type=e2-medium \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --network="$VPC" \
  --subnet="$SUBNET" \
  --no-address \
  --tags=mig-web \
  --metadata-from-file=startup-script=./startup.sh

gcloud compute instance-templates describe "$TEMPLATE"
~~~

**Môi trường lab:** script cài Nginx từ kho Debian. Nếu VM không có external IP và không có Cloud NAT/đường egress phù hợp, startup script sẽ không tải được packages. Trong production, nên dùng **custom image hoặc artifact đã được build sẵn** để giảm thời gian tạo VM, tránh rủi ro repository ngoài và cho phép triển khai có thể tái lập.

### 7.2. Tạo zonal MIG

~~~bash
ZONAL_MIG="web-zonal-mig"

gcloud compute instance-groups managed create "$ZONAL_MIG" \
  --zone="$ZONE" \
  --template="$TEMPLATE" \
  --size=3 \
  --base-instance-name=web-zonal

gcloud compute instance-groups managed describe "$ZONAL_MIG" \
  --zone="$ZONE"

gcloud compute instance-groups managed list-instances "$ZONAL_MIG" \
  --zone="$ZONE"
~~~

Kết quả mong đợi: nhóm cố tạo 3 VM trong `us-central1-a`. Nếu tất cả VM được cấp phát và script chạy xong, có thể truy cập HTTP bên trong mạng phù hợp khi firewall cho phép. Nếu cả zone gặp sự cố, MIG **không tự chuyển các VM của zonal MIG sang zone khác**.

### 7.3. Tạo regional MIG

~~~bash
REGIONAL_MIG="web-regional-mig"
ZONES="us-central1-a,us-central1-b,us-central1-c"

gcloud compute instance-groups managed create "$REGIONAL_MIG" \
  --region="$REGION" \
  --zones="$ZONES" \
  --template="$TEMPLATE" \
  --size=6 \
  --target-distribution-shape=even

gcloud compute instance-groups managed describe "$REGIONAL_MIG" \
  --region="$REGION"

gcloud compute instance-groups managed list-instances "$REGIONAL_MIG" \
  --region="$REGION"
~~~

Với `EVEN`, size 6 và ba zone, mục tiêu thường là **2 VM mỗi zone**. Đây là **tổng số 6 VM trên toàn regional MIG**, không phải 6 VM trong mỗi zone. Nếu gặp quota/capacity shortage tại một zone, hãy kiểm tra trạng thái managed instances và lỗi operation, đừng mặc định nhóm đã sẵn sàng chỉ vì lệnh tạo tài nguyên thành công.

> **Chú ý về quyền truy cập:** với VM không có external IP, muốn phục vụ traffic Internet cần thêm load balancer hợp lệ và firewall tương ứng. Tạo MIG chưa tự tạo DNS, TLS certificate hoặc external Application Load Balancer.

## 8. Autoscaling: thay đổi tổng số VM theo tải

**Autoscaler** thay đổi **target size** của một MIG dựa trên các tín hiệu được hỗ trợ như CPU utilization, load-balancing serving capacity, Cloud Monitoring metric hoặc lịch. Với regional MIG, số lượng min/max là **tổng số VM của nhóm**, không phải giới hạn lặp lại riêng cho mỗi zone.

Giả sử web API có CPU trung bình tăng cao trong giờ cao điểm. Nhóm đặt:

- **Minimum replicas:** 6 — giữ capacity tối thiểu, phân tán qua ba zone.
- **Maximum replicas:** 18 — giới hạn mức mở rộng tương ứng quota và ngân sách.
- **CPU target:** 0,65 (65%) — autoscaler cố giữ mức sử dụng CPU gần mục tiêu, không phải hard cap.
- **Initialization period:** 180 giây — cho ứng dụng thời gian khởi động trước khi đánh giá tín hiệu scaling.

~~~bash
gcloud compute instance-groups managed set-autoscaling "$REGIONAL_MIG" \
  --region="$REGION" \
  --min-num-replicas=6 \
  --max-num-replicas=18 \
  --target-cpu-utilization=0.65 \
  --cool-down-period=180
~~~

Ở lệnh CLI này, `--cool-down-period` là tên cờ lịch sử cho **initialization period** của autoscaler, không phải khoảng thời gian mà hệ thống luôn “khóa” mọi scale-in/scale-out. Kiểm tra thời gian khởi động thật để chọn giá trị, không đặt theo cảm tính. Google Cloud có thêm cơ chế stabilization, scale-in control và predictive autoscaling nhằm hạn chế hành vi co giãn gây gián đoạn.

### Autoscaling không tuyến tính tuyệt đối

Nếu mỗi VM khỏe có thể phục vụ khoảng 100 requests/giây, điều đó **không** chứng minh sáu VM đáp ứng chắc chắn 600 requests/giây. Thông lượng còn phụ thuộc loại request, database, contention, garbage collection, network và backlog. CPU target 65% là một tín hiệu, không phải phép đổi trực tiếp từ QPS sang số VM.

Ngoài ra:

- Tăng VM cần thời gian tạo disk, boot OS, chạy startup script, khởi động JVM và qua health check.
- Scale-out có thể thất bại nếu **quota CPU, disk, IP**, địa chỉ subnet hoặc capacity trong zone không đủ.
- Scale-in có thể hủy VM đang xử lý request nếu ứng dụng thiếu drain/graceful shutdown.
- Khi workload bottleneck ở database, thêm VM không nhất thiết tăng throughput; có thể làm database quá tải nhanh hơn.
- Nếu traffic có đỉnh rõ theo lịch, cân nhắc **scaling schedule** hoặc chuẩn bị capacity trước giờ cao điểm.
- Autoscaling của MIG có **giới hạn** khi dùng stateful configuration; không áp cấu hình stateless lên stateful MIG khi chưa đọc các hạn chế.

**Phân biệt:** autoscaling thay đổi **số VM**; autohealing thay **VM lỗi** để duy trì nhóm; rolling update thay **phiên bản cấu hình**. Các cơ chế có thể xảy ra cùng lúc và cần giám sát riêng.

## 9. Autohealing: thay thế VM không khỏe

MIG có thể cấu hình **application-based autohealing**. Một health check HTTP/HTTPS/TCP phù hợp đánh giá khả năng hoạt động của ứng dụng; khi một VM liên tục không khỏe, MIG có thể **repair bằng cách recreate** VM đó.

~~~text
VM của MIG được tạo từ template
      ↓
OS khởi động, startup script chạy, ứng dụng Java sẵn sàng
      ↓
Health check kiểm tra /healthz
  ├── HEALTHY   → VM được giữ
  └── UNHEALTHY → MIG thay thế VM theo autohealing policy
      ↓
VM mới được tạo từ template và kiểm tra lại
~~~

### Health check cho autohealing khác load balancing

| Health check | Mục tiêu | Độ nhạy |
|---|---|---|
| **Load balancer health check** | Xác định backend có nhận traffic ngay lúc này không | Có thể kiểm tra nhanh và nghiêm ngặt |
| **MIG autohealing health check** | Xác định VM có nên bị thay thế hay không | Thường nên thận trọng hơn, tránh vòng lặp recreate |

**Dùng cùng một health check cho cả hai có thể gây tác động xấu** nếu ngưỡng quá nghiêm hoặc ứng dụng khởi động lâu. Ví dụ backend mới khởi động JVM trong 120 giây: load balancer tạm thời không gửi traffic là hợp lý, nhưng autohealing recreate VM sau 15 giây sẽ khiến ứng dụng không bao giờ hoàn tất quá trình khởi động.

### Tạo health check HTTP

~~~bash
HC="mig-app-health"

gcloud compute health-checks create http "$HC" \
  --port=80 \
  --request-path=/healthz

gcloud compute health-checks describe "$HC"
~~~

Với MIG, mở **Compute Engine → Instance groups → tên MIG → Edit → Instance lifecycle and autohealing**, chọn health check và cấu hình **Initial delay** phù hợp (ví dụ 180 giây sau khi xác minh thời gian boot). Bật autohealing sau khi đã kiểm tra endpoint và firewall. Chính sách autohealing cũng có thể được cấu hình qua API/IaC; lệnh `gcloud beta ... set-autohealing` cũ đã có cảnh báo deprecated trong CLI, nên tránh dùng nó làm ví dụ mặc định.

**Bài học quan trọng:** health check phải kiểm tra **khả năng phục vụ của chính ứng dụng**. Nhưng đừng đặt kiểm tra quá phụ thuộc vào một dịch vụ ngoài hoặc database đang bị lỗi toàn cục, vì nó có thể khiến cả nhóm VM bị recreate liên tục khi lỗi không nằm ở VM.

### Initial delay và firewall

Initial delay cho phép VM hoàn tất khởi động trước khi những lần health check thất bại dẫn đến repair. Cần cấu hình:

- VM startup script và ứng dụng thực sự lắng nghe cổng/đường dẫn được health check.
- Firewall cho phép **nguồn health-check probes** phù hợp loại load balancer/health check.
- Giá trị initial delay đủ cho image pull, Java warmup, migration không chặn startup và cache load.
- Độ nhạy failure threshold hợp lý; tránh reset VM do một lần jitter mạng.

Nếu health check chưa hoạt động, đừng bật autohealing hàng loạt ở production. Hãy xem trạng thái health của một nhóm thử nghiệm trước.

## 10. Kết hợp regional MIG với load balancer

Một **regional MIG** quản lý nhóm VM qua zone; **Application Load Balancer** nhận request của khách hàng, chọn backend phù hợp và gửi đến VM khỏe. Với web/API Java stateless, kiến trúc điển hình là:

~~~mermaid
flowchart TD
    A["Người dùng / Cloud DNS"] --> B["External Application Load Balancer"]
    B --> C["Backend service"]
    C --> D["Regional MIG: us-central1"]
    D --> E["Zone a: VM1, VM2"]
    D --> F["Zone b: VM3, VM4"]
    D --> G["Zone c: VM5, VM6"]
    E --> H["Database hoặc Storage dùng chung"]
    F --> H
    G --> H
~~~

Các bước triển khai ở mức kiến trúc:

1. Cấu hình startup script/image để mọi VM sẵn sàng phục vụ cùng phiên bản API.
2. Đặt service port và **named port** của MIG nếu loại backend service yêu cầu, ví dụ `http:80`.
3. Tạo backend service và health check cho load balancer; thêm MIG làm backend.
4. Tạo URL map, frontend, certificate TLS và forwarding rule theo loại load balancer.
5. Chỉ cho phép các nguồn proxy/health check cần thiết đến VM qua firewall; VM không có public IP trực tiếp nếu không cần.
6. Trỏ Cloud DNS vào frontend IP của load balancer.
7. Kiểm tra traffic bình thường, lỗi một VM và ảnh hưởng khi một zone không khả dụng trong thử nghiệm có kiểm soát.

Ví dụ gán named port:

~~~bash
gcloud compute instance-groups managed set-named-ports "$REGIONAL_MIG" \
  --region="$REGION" \
  --named-ports=http:80
~~~

Lệnh này **không tự tạo load balancer**. Backend service, health check, firewall và chứng chỉ phải được thiết kế riêng. Nếu dùng Cloud Armor, nó bảo vệ request **đi qua backend service được gắn policy**; không bảo vệ một đường truy cập trực tiếp ngoài load balancer.

### Thiết kế để chịu lỗi một zone

Giả sử một regional MIG có 6 VM chia đều 2-2-2; một VM có năng lực thử tải 100 RPS trong điều kiện cụ thể. Nếu zone A mất khả dụng, hệ thống còn 4 VM ở B/C, tổng năng lực tham khảo 400 RPS. Nếu mức cần phục vụ lúc đó là 500 RPS, ứng dụng **vẫn có thể quá tải** dù regional MIG còn hoạt động.

Vì vậy, cần **overprovision** hoặc dự phòng capacity:

- Đặt số VM tối thiểu đủ để các zone còn lại gánh được tải mục tiêu khi một zone mất.
- Đảm bảo database, load balancer và cache không thành single point of failure.
- Xem xét giới hạn region/zone CPU quota và instance capacity khi autoscaler muốn tạo bù.
- Thiết kế request idempotency, retries có giới hạn, circuit breaker và graceful shutdown cho API.

**Regional MIG không bảo đảm thời gian phục hồi bằng 0.** Health checks, VM creation, warmup và cache có thể mất thời gian; khả năng duy trì phục vụ phụ thuộc công suất còn lại.

## 11. Rolling updates: triển khai phiên bản mới có kiểm soát

Một MIG dùng template `web-template-v1`. Khi nhóm phát hành ứng dụng Java phiên bản v2, nên tạo **instance template mới**; không cần chỉnh bằng tay từng VM.

~~~text
Template v1 → MIG đang chạy
      ↓
Build image/phiên bản v2 + template v2
      ↓
Kiểm tra rollout policy và quota
      ↓
Thay lần lượt một số VM v1 bằng VM v2
      ↓
Health check OK → tiếp tục đợt kế tiếp
      ↓
Toàn bộ VM trên các zone được cập nhật
~~~

Các tùy chọn chính:

| Tham số | Ý nghĩa | Hệ quả |
|---|---|---|
| `maxSurge` | Số VM bổ sung vượt target size được phép tạo khi update | Tăng tốc nhưng cần quota và phát sinh phí |
| `maxUnavailable` | Số VM có thể không sẵn sàng trong quá trình update | Giá trị nhỏ giảm gián đoạn nhưng rollout chậm |
| `minimalAction` | Mức thay đổi tối thiểu được thực hiện cho VM | Có thể refresh, restart hoặc replace tùy thay đổi |
| `replacementMethod` | Chiến lược tạo VM thay thế | Có thể đổi tên VM hoặc recreate giữ tên theo điều kiện |
| `proactive / opportunistic` | Cập nhật chủ động mọi VM hay khi có cơ hội/được yêu cầu | Ảnh hưởng thời gian rollout và cách xử lý rủi ro |

Ví dụ bắt đầu rolling update của regional MIG:

~~~bash
NEW_TEMPLATE="web-template-v2"

gcloud compute instance-groups managed rolling-action start-update \
  "$REGIONAL_MIG" \
  --region="$REGION" \
  --version="template=$NEW_TEMPLATE" \
  --type=proactive \
  --max-surge=3 \
  --max-unavailable=0
~~~

`maxUnavailable=0` kết hợp `maxSurge>0` nhằm giữ công suất trong lúc thay VM. Tuy nhiên, nếu quota/capacity không đủ để tạo surge VM, rollout có thể không tiến triển. Với một số hình thức update hoặc stateful group, các tùy chọn có giới hạn. Cần **xem trạng thái managed instances và errors**, không kết luận lệnh được chấp nhận nghĩa là ứng dụng đã triển khai xong.

Trước khi rollout production, nên:

1. Kiểm thử image/template v2 ở dev hoặc staging.
2. Xem ứng dụng có chịu được hai phiên bản cùng hoạt động trong thời gian chuyển tiếp không.
3. Dùng cấu hình health check/readiness đủ ổn định.
4. Đánh giá quota cho `maxSurge` tại mỗi zone.
5. Theo dõi HTTP 5xx, latency, CPU, log và business metrics trong suốt rollout.
6. Lưu template/ảnh cũ để có thể bắt đầu **roll back** về phiên bản trước.

Với một số target distribution shape, **canary update hai phiên bản không được hỗ trợ**; tra cứu tài liệu theo shape trước khi lên kế hoạch canary. Nếu rollback, MIG có thể phải thay VM thêm một lần nữa; rollback không tức thời và dữ liệu nằm trên VM vẫn có thể mất.

## 12. Quyền IAM, mạng và bảo mật

Một nhóm triển khai MIG có thể cần các nhóm quyền sau:

| Tác vụ | Quyền/role cần xem xét | Lưu ý |
|---|---|---|
| Tạo template, MIG, resize, update | Các permission Compute Engine về `instanceTemplates` và `instanceGroupManagers`, thường thuộc `roles/compute.instanceAdmin.v1` | Hạn chế phạm vi project hoặc tài nguyên |
| Dùng service account trên VM | `iam.serviceAccounts.actAs`, ví dụ `roles/iam.serviceAccountUser` trên đúng service account | Không cấp trên mọi service account |
| Dùng subnet Shared VPC | Network User hoặc quyền tương ứng trên subnet được cấp | MIG phải được phép sử dụng mạng đích |
| Tạo health check, backend service, firewall | Các quyền Compute/Network Admin cần thiết | Tách người vận hành LB với người deploy app |
| Truy cập Artifact Registry/Secret Manager | Vai trò đọc trên đúng resource đích cho **VM runtime identity** | Không nhúng token vào startup script |
| Xem tình trạng, logs, metrics | Viewer/Monitoring/Logging permissions phù hợp | Giữ log có thời gian lưu và quyền xem đúng |

**Nhận diện quyền thực thi:** service account của VM, danh tính tạo MIG và service account CI/CD triển khai có thể **khác nhau**. Người dùng có quyền tạo VM không tự có quyền đọc secret của ứng dụng, và runtime service account không nên có quyền sửa MIG hay IAM project nếu không cần.

Ở mức mạng:

- Để VM không có external IP khi không cần nhận request trực tiếp.
- Dùng firewall chỉ cho phép nguồn health checks/proxy/load balancer thích hợp; không mở cổng `0.0.0.0/0` chỉ để sửa lỗi tạm thời.
- Nếu bootstrap cần tải packages, cấu hình Cloud NAT hoặc đường đến kho nội bộ/Google APIs theo thiết kế.
- Đặt dữ liệu nghiệp vụ ở database/Cloud Storage; không ghi secret hoặc dữ liệu quan trọng vào boot disk có thể bị recreate.
- Kiểm tra Organization Policy và hạn chế region/machine type; IAM cho phép không bảo đảm thao tác tạo VM được policy tổ chức chấp nhận.

## 13. Quan sát vận hành và xử lý sự cố

Với MIG, phải theo dõi cả **trạng thái nhóm** lẫn **trạng thái ứng dụng**, bởi một nhóm đạt target size có thể vẫn chứa nhiều VM không phục vụ request.

### Các lệnh chỉ đọc

~~~bash
# Xem cấu hình và target size.
gcloud compute instance-groups managed describe "$REGIONAL_MIG" \
  --region="$REGION"

# Liệt kê VM trong từng zone và trạng thái hành động hiện tại.
gcloud compute instance-groups managed list-instances "$REGIONAL_MIG" \
  --region="$REGION"

# Xem thông tin các MIG trong project.
gcloud compute instance-groups managed list

# Xem cấu hình autoscaler nếu đã bật.
gcloud compute autoscalers list
~~~

Với regional MIG, autoscaler là tài nguyên theo region; hãy dùng bộ lọc/describe phù hợp để tránh nhầm autoscaler zonal với regional. Có thể kiểm tra thêm operations và Audit Logs cho lỗi tạo VM, rolling update, permission hoặc thay đổi cấu hình.

### Các metric nên theo dõi

| Chỉ số | Tình huống cần phát hiện |
|---|---|
| **Target size vs số VM RUNNING/healthy** | Cần 6 VM nhưng chỉ tạo được 4 |
| **Phân phối VM theo zone** | Shape không còn phân bố như thiết kế hoặc một zone lỗi |
| **Current action: creating/recreating/verifying** | Tốc độ tạo VM và hành vi updater |
| **CPU/memory, request rate** | Tải tăng và nhu cầu autoscaling |
| **HTTP 5xx, latency, SLO** | Ứng dụng quá tải dù số VM tăng |
| **Health check status và repair count** | VM bị recreate liên tục do cấu hình sai |
| **Quota/stockout errors** | Autoscaler có mục tiêu cao nhưng zone không còn capacity |
| **Thời gian boot/readiness** | Instance khởi động chậm, ảnh hưởng đến scale-out |
| **VM-hours, disk, network, LB/Logging cost** | Vượt chi phí dự kiến khi autoscale hoặc update có surge |

MIG có thể xuất các chỉ số phân bổ instance qua zone/machine type trong Console, đặc biệt hữu ích khi dùng `BALANCED`, `ANY` hoặc instance flexibility. Cloud Monitoring/Logging giúp thiết lập dashboard, alert và điều tra.

### Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| Không tạo được MIG | Template sai, thiếu IAM, zone/region sai | Lỗi operation và quyền Compute Engine |
| MIG tạo nhưng ít VM hơn target | Quota, capacity, subnet IP, machine type không sẵn | List instances, quota/stockout errors theo zone |
| Regional MIG không chia đều | Shape `BALANCED/ANY`, redistribution tắt, zone thiếu tài nguyên | `targetDistributionShape` và phân phối theo zone |
| VM luôn bị recreate | Health check không khớp port/path, firewall chặn probe, startup lâu | Health status, boot log, initial delay |
| VM RUNNING nhưng LB trả 502/503 | Load balancer health check, firewall, named port hoặc app chưa sẵn sàng | Backend health, port và ứng dụng |
| Autoscaler không tăng VM | Tín hiệu CPU không vượt mục tiêu, max replicas/quota chạm trần | Autoscaler configuration và metrics |
| Autoscaler co giảm quá sớm | Stabilization/scale-in config, workload theo đợt, chưa drain | Nhìn lịch sử metrics và policy |
| Rolling update bị dừng | Thiếu surge quota, image mới lỗi, VM không healthy | Update status, VM errors, startup script |
| VM mất file sau update | Lưu dữ liệu trên disk/đường dẫn tạm của instance stateless | Kiến trúc storage, backup và stateful policy |
| Hóa đơn tăng mạnh | Min quá cao, surge VM, disk/network/LB/Logging | Billing theo SKU, MIG size, policy |

Một ví dụ dễ gặp: nhóm cập nhật startup script để chạy Java API, nhưng script cần truy cập package registry qua Internet trong khi VM không có external IP và VPC chưa có Cloud NAT. Các VM đều xuất hiện rồi thất bại khởi động; autohealing liên tục thay máy nhưng không sửa được nguyên nhân. Cách xử lý là kiểm tra boot logs, mạng egress và artifact có sẵn, **không** tăng `maxReplicas`.

## 14. Chi phí và bài toán dự phòng theo zone

MIG không có nghĩa là “nhiều máy miễn phí”. Tổng chi phí chịu ảnh hưởng bởi VM compute, persistent disk, network traffic, load balancer, image build, logging/monitoring và những dịch vụ phụ thuộc. Autoscaler giúp dùng tài nguyên tương ứng tải nhưng **minimum replicas** và capacity dự phòng vẫn có chi phí.

Mô hình ước lượng:

~~~text
Chi phí theo tháng
  ≈ tổng VM-hours × đơn giá machine type
  + boot/persistent disk
  + network egress / interzone transfer nếu có
  + load balancing / external IP / health-check-related usage nếu áp dụng
  + logging, monitoring và dịch vụ bổ trợ
~~~

| Quyết định | Lợi ích | Chi phí/đánh đổi |
|---|---|---|
| Zonal MIG 3 VM | Đơn giản, số VM ít | Mất zone có thể mất toàn dịch vụ |
| Regional MIG 6 VM (2-2-2) | Phân bố theo nhiều zone | Nhiều VM duy trì hơn nếu muốn dự phòng |
| `minReplicas=6`, `maxReplicas=18` | Mở rộng khi traffic tăng | Phí 6 VM tối thiểu; có thể tới 18 VM |
| `maxSurge=3` khi update | Giữ năng lực phục vụ trong rollout | Có thể tạm tính phí thêm 3 VM |
| Shape `BALANCED` | Linh hoạt khi zone thiếu capacity | Phân bố không đều và cần xem policy |
| Image tối ưu boot nhanh | Scale-out đáp ứng nhanh hơn | Cần pipeline build/patch image |

Không mặc định dự phòng đủ 100% cho mọi tình huống. Hãy dùng **traffic forecast + load test + SLO** để tính số VM tối thiểu nếu cần chịu lỗi một zone. Ví dụ với ba zone và yêu cầu giữ đủ capacity khi mất một zone, phải đảm bảo capacity tại **hai zone còn lại** đáp ứng mức tải quan trọng; nếu không, tăng min size, giảm tải hoặc thêm cơ chế chuyển lưu lượng theo phương án kinh doanh.

Đặt **Cloud Billing budget/alerts**, xem chi phí theo project/labels và kiểm tra giá Compute Engine, disks, load balancing theo region. Budget alert **không tự ngắt autoscaler**; dùng `maxReplicas` và quota phù hợp để giới hạn quy mô, nhưng vẫn phải giám sát các nguồn chi phí không nằm trong MIG.

## 15. Tình huống: API Java cần sẵn sàng khi một zone lỗi

Một công ty thương mại điện tử muốn chạy dịch vụ `orders-api` trên Compute Engine. Traffic thay đổi theo giờ; ứng dụng truy cập Cloud SQL và Cloud Storage; công ty yêu cầu một zone lỗi không làm toàn API ngừng hoạt động.

### Phương án A: Zonal MIG

- 4 VM trong `us-central1-a`.
- Có autoscaler, autohealing và load balancer.
- Tạo/duy trì đơn giản; có thể xử lý một VM lỗi.
- **Rủi ro:** nếu toàn zone A mất khả dụng, tất cả VM cùng bị ảnh hưởng; autoscaling và autohealing trong **cùng zone** không loại bỏ rủi ro đó.

### Phương án B: Regional MIG

- 6 VM chia qua `us-central1-a/b/c`, shape `EVEN`.
- Tối thiểu 6, tối đa 18 VM theo CPU hoặc serving capacity phù hợp.
- External Application Load Balancer phân phối HTTP tới VM khỏe.
- Autohealing xử lý VM lỗi; updater phát hành template mới có giới hạn surge/unavailable.
- Cloud SQL được thiết kế HA phù hợp, Cloud Storage dùng location/consistency theo nhu cầu; ứng dụng không giữ session duy nhất trên VM.
- Cloud Monitoring theo dõi HTTP SLO, backend health, zone distribution và costs.

**Kết luận:** nếu yêu cầu chính là chịu lỗi zone, **regional MIG** thường hợp lý hơn một zonal MIG đơn lẻ. Nhưng việc chọn region có thể cần xét độ trễ tới người dùng, data residency, chi phí truyền dữ liệu và sự sẵn có của machine type. Khi muốn chịu lỗi region, doanh nghiệp phải thiết kế **nhiều deployment ở nhiều region**, không chỉ tăng số VM trong một regional MIG.

### Bảng quyết định nhanh

| Câu hỏi | Khuyến nghị |
|---|---|
| Môi trường thử nghiệm, chịu được sự cố zone? | Bắt đầu với zonal MIG |
| Production web/API yêu cầu chịu lỗi một zone? | Regional MIG, thường shape `EVEN` hoặc `BALANCED` theo capacity |
| Batch cần tìm capacity/reservations hơn là cân bằng zone? | Regional MIG với `ANY` khi phù hợp |
| Job cần VM cùng một zone để giảm độ trễ liên máy? | Cân nhắc `ANY_SINGLE_ZONE` và chấp nhận rủi ro zone |
| Database có dữ liệu cần tồn tại qua VM recreation? | Thiết kế storage/HA riêng; không mặc định dùng stateless MIG |
| Yêu cầu phục hồi khi cả region lỗi? | Kiến trúc multi-region với nhiều MIG/backend và chiến lược failover |

## 16. Checklist thiết kế và triển khai

- [ ] Đã xác định workload stateless hay cần cấu hình stateful.
- [ ] Đã chọn zonal hoặc regional MIG dựa trên yêu cầu chịu lỗi zone.
- [ ] Với regional MIG, danh sách zone được chọn đúng từ đầu.
- [ ] Target distribution shape phù hợp capacity, tính sẵn sàng và loại workload.
- [ ] Đã kiểm tra machine type, image, subnet, quota và reservation trong các zone.
- [ ] Template có phiên bản, startup có log, secrets không nhúng vào disk/metadata.
- [ ] Service account runtime và pipeline deployment tuân nguyên tắc quyền tối thiểu.
- [ ] Autoscaler có `minReplicas`, `maxReplicas`, tín hiệu và initialization period hợp lý.
- [ ] Autohealing có health check đủ thận trọng, initial delay và firewall đúng.
- [ ] Load balancer health check, named port và backend service đã được kiểm chứng.
- [ ] Có phương án chịu lỗi một zone với **capacity còn lại** đủ cho tải quan trọng.
- [ ] Rolling update có quota surge, health verification, rollback và giám sát.
- [ ] Logs/metrics báo target size, VM health, zone distribution, 5xx, latency và chi phí.
- [ ] Có kế hoạch dừng/xóa tài nguyên lab để không bị tính phí ngoài dự kiến.

**Bài tập thực hành:** Nhóm triển khai API Java trên Compute Engine, đỉnh traffic dự kiến 900 RPS và có ba zone trong một region. Kết quả load test cho thấy mỗi VM phục vụ ổn định khoảng 150 RPS ở mức CPU mục tiêu khi database còn khỏe. Hãy:

1. Giải thích vì sao zonal MIG 6 VM không đáp ứng yêu cầu chịu lỗi một zone.
2. Đề xuất **số VM tối thiểu của regional MIG** để khi mất một trong ba zone, hai zone còn lại vẫn đủ 900 RPS trong điều kiện giả định; nêu rõ phép tính và phần dự phòng.
3. Chọn `EVEN` hay `BALANCED` khi máy e2 đôi lúc thiếu capacity một zone và giải thích đánh đổi.
4. Viết lệnh `gcloud` tạo regional MIG từ template và bật autoscaling CPU với min/max hợp lý.
5. Thiết kế health endpoint, autohealing initial delay và load balancer health check riêng.
6. Chọn `maxSurge`, `maxUnavailable` khi phát hành v2, nêu quota bổ sung cần có và cách rollback.
7. Liệt kê dashboard/alerts và những nguồn chi phí phải theo dõi.
8. Nếu cả region mất khả dụng, mô tả vì sao regional MIG không đủ và cần bổ sung kiến trúc gì.

*Gợi ý cách tính:* nếu ba zone có phân phối đều và mỗi VM đáp ứng 150 RPS trong giả định, cần ít nhất 6 VM khỏe **ở hai zone còn lại** khi một zone mất. Với phân phối đều 3-3-3, sau mất một zone còn 6 VM; vì vậy nhóm có thể cân nhắc tối thiểu 9 VM cho bài toán lý tưởng này, nhưng nên dành thêm biên an toàn cho jitter, rollout, health, quota và database bottleneck. Kết quả thực tế cần xác minh bằng load test và diễn tập lỗi.

## Tài liệu tham khảo chính thức

- [Managed instance groups overview](https://cloud.google.com/compute/docs/instance-groups) — MIG, autoscaling, autohealing và cập nhật.
- [Basic scenarios for creating MIGs](https://cloud.google.com/compute/docs/instance-groups/creating-groups-of-managed-instances) — lựa chọn mô hình và giới hạn.
- [Create a zonal MIG](https://cloud.google.com/compute/docs/instance-groups/create-zonal-mig) — thao tác Console/CLI.
- [Create a regional MIG](https://cloud.google.com/compute/docs/instance-groups/distributing-instances-with-regional-instance-groups) — tạo nhóm nhiều zone.
- [About regional MIGs](https://cloud.google.com/compute/docs/instance-groups/regional-migs) — khả năng chịu lỗi, phân bố và hạn chế.
- [Regional MIG target distribution shapes](https://cloud.google.com/compute/docs/instance-groups/regional-mig-distribution-shape) — EVEN/BALANCED/ANY/ANY_SINGLE_ZONE.
- [Set target distribution shape](https://cloud.google.com/compute/docs/instance-groups/regional-mig-set-target-distribution-shape) — cờ CLI và ràng buộc với redistribution.
- [Set up autohealing](https://cloud.google.com/compute/docs/instance-groups/autohealing-instances-in-migs) — health checks và initial delay.
- [Automatically apply configuration updates](https://cloud.google.com/compute/docs/instance-groups/rolling-out-updates-to-managed-instance-groups) — rolling update, surge và unavailable.
- [Autoscaling managed instance groups](https://cloud.google.com/compute/docs/autoscaler) — CPU/metric/schedule và scale-in controls.
- [Compute Engine pricing](https://cloud.google.com/compute/all-pricing) — VM, disk và các thành phần chi phí.
