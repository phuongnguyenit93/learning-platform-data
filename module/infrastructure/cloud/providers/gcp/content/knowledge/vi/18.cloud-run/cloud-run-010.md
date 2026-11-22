# Direct VPC egress và Serverless VPC Access trong Cloud Run

> **Chương:** Cloud Run  
> **Bài học:** Direct VPC egress và Serverless VPC Access  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học đi từ quản lý project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; mục tiêu là triển khai dịch vụ an toàn, tự động hóa phát hành, giám sát độ tin cậy và kiểm soát chi phí. Với **Cloud Run**, một HTTP API Java chạy trên hạ tầng serverless nhưng đôi khi phải kết nối **Cloud SQL private IP**, Redis, VM nội bộ, hoặc hệ thống on-premises qua VPN/Interconnect. Việc đó đòi hỏi chọn đúng đường **egress (lưu lượng đi ra)**.

Google Cloud có hai phương án chính để Cloud Run service/job đi vào VPC: **Direct VPC egress** và **Serverless VPC Access connector**. Cả hai giải quyết **kết nối từ Cloud Run tới VPC**, không tự công khai hoặc chặn endpoint HTTP của Cloud Run. Bài này giải thích kiến trúc, lệnh triển khai, bảo mật, chi phí, các lỗi thường gặp và một tình huống Java thực tế. Ưu tiên tài liệu tự chứa, ví dụ đủ chạy trong sandbox nhưng không lặp lại phần mạng cơ bản không cần thiết.

**Nguyên tắc lựa chọn:** Với Cloud Run services/jobs, Google Cloud khuyến nghị **Direct VPC egress** khi đáp ứng yêu cầu vì không cần connector riêng. Chỉ chọn **Serverless VPC Access** khi có ràng buộc tính năng, mạng hiện hữu hoặc nhu cầu vận hành khiến connector phù hợp hơn.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt đường **egress tới VPC** với cấu hình **ingress tới Cloud Run**, IAM và quyền truy cập ứng dụng.
2. Giải thích luồng dữ liệu của Direct VPC egress và Serverless VPC Access, cùng giới hạn service/job.
3. Chọn `private-ranges-only` hoặc `all-traffic`, hiểu khi nào cần **Cloud NAT**.
4. Thiết kế subnet cho Direct VPC (**tối thiểu /26**, còn đủ IP khi scale/rolling revision) và connector (**/28 riêng**).
5. Dùng `gcloud run deploy` cấu hình cả hai phương án; đọc lại service revision, VPC, connector.
6. Kết hợp firewall, IAM, DNS, Shared VPC và Cloud SQL private connectivity.
7. Chẩn đoán lỗi timeout, permission, IP exhaustion, startup latency và public egress.
8. Chọn phương án theo **độ trễ, khả năng mở rộng, độ tin cậy và chi phí** của API Java.

## 2. Egress khác ingress: xác định đúng bài toán

~~~mermaid
flowchart LR
    Client["Người dùng / hệ thống gọi API"] -->|"Ingress + auth"| CR["Cloud Run Orders API"]
    CR -->|"Egress vào VPC"| VPC["VPC app-vpc"]
    VPC --> DB["Cloud SQL private IP<br/>hoặc VM/Redis nội bộ"]
    VPC --> Hybrid["Cloud VPN/Interconnect<br/>on-premises"]
    CR -->|"Public egress nếu policy cho phép"| Public["API bên ngoài / Google APIs"]
~~~

- **Ingress:** ai có thể gửi yêu cầu HTTP đến URL Cloud Run? Điều chỉnh bằng `--ingress`, IAM Invoker, Load Balancer, IAP hoặc chính sách ứng dụng.
- **Egress:** khi container Java chủ động kết nối ra DB, Redis hoặc endpoint khác, gói tin đi đường nào?
- **Cloud Run runtime service account:** ứng dụng được quyền gọi **API của Google** nào; **không** tự cấp đường mạng tới IP nội bộ.
- **Firewall/VPC routes:** cho phép luồng IP/port nào đi qua; **không** thay IAM hay xác thực của database.

Đối với **Cloud Run service và job**, Direct VPC là cấu hình **egress**; không biến container thành một VM có địa chỉ inbound cố định. Một số loại tài nguyên Cloud Run khác (như worker pool/instance) có Direct VPC ingress theo tính năng riêng, **không** nên áp suy luận đó cho service HTTP thường.

### 2.1. Khi nào Cloud Run cần VPC egress?

| Đích gọi từ Java | Có cần đường VPC? | Ghi chú |
|---|---|---|
| VM private IP trong cùng VPC | **Có** | Cần route/firewall, cổng dịch vụ và DNS phù hợp |
| Cloud SQL qua **private IP** | **Có** | Còn cần thiết lập private networking của Cloud SQL và xác thực DB |
| Memorystore/Redis private endpoint | Thường **có** | Kiểm tra network và khu vực hỗ trợ |
| Database on-premises qua Cloud VPN/Interconnect | **Có** | Cần route hai chiều, firewall và DNS hybrid |
| Cloud Storage/Pub/Sub qua API Google thông thường | **Không mặc định** | Google APIs có thể được gọi bằng HTTPS qua đường mặc định, IAM vẫn cần |
| API public của đối tác | **Không mặc định** | Nếu phải kiểm soát IP public đầu ra, dùng VPC `all-traffic` + Cloud NAT/static NAT IP |
| Cloud Run nhận request công khai | **Không liên quan egress** | Quyết định bằng ingress, auth và frontend |

**Bài học:** Không cấu hình connector/Direct chỉ vì “dịch vụ Cloud Run phải dùng VPC”. Chỉ đưa lưu lượng qua VPC khi có đích private hoặc nhu cầu định tuyến/kiểm soát egress rõ ràng.

## 3. So sánh nhanh hai phương án

| Tiêu chí | **Direct VPC egress** | **Serverless VPC Access** |
|---|---|---|
| Luồng | Cloud Run nối trực tiếp tới VPC/subnet | Cloud Run đi qua **connector** rồi vào VPC |
| Tài nguyên trung gian | Không có connector riêng | Connector gồm các instance được quản lý |
| Phương án mặc định cho Cloud Run service/job mới | **Ưu tiên khi phù hợp** | Chọn khi Direct không đáp ứng |
| Kích thước địa chỉ | Subnet **/26 hoặc lớn hơn**, thiết kế buffer khi scale | Dải/subnet riêng **/28**, không dùng chung tài nguyên khác |
| Tỷ lệ mở rộng | Theo Cloud Run; subnet phải đủ IP | Connector có min/max instances và throughput hữu hạn |
| Chi phí nền khi Cloud Run scale về 0 | Không có phí connector luôn chạy | Connector có **minimum instances** nên vẫn có chi phí |
| Kiểm soát firewall | Có thể đặt **network tags trên revision**; IP theo subnet | Dùng CIDR /28 hoặc connector tags/rules phù hợp |
| Latency khi cold start | Có thể phát sinh trễ thiết lập network lúc instance khởi động | Connector luôn có năng lực hoạt động, đôi khi lợi cho startup |
| `private-ranges-only` / `all-traffic` | Đều hỗ trợ | Đều hỗ trợ |
| Cloud Run service/job inbound qua VPC | **Không** | **Không** |

**Trade-off chính:** Direct đơn giản và thường tiết kiệm vận hành; connector thêm tài nguyên/chi phí nền nhưng có thể phù hợp một số yêu cầu kết nối hoặc cold-start cụ thể. Không có phương án nào tự thay HTTPS, IAM, firewall hay database authentication.

## 4. Cách định tuyến `private-ranges-only` và `all-traffic`

Hai phương án VPC đều dùng cùng khái niệm egress routing:

~~~mermaid
flowchart TD
    Java["Java service gửi TCP/HTTPS request"] --> Mode{"Cloud Run VPC egress mode"}
    Mode -->|"private-ranges-only"| Private{"Đích thuộc phạm vi internal/private?"}
    Private -->|"Có"| VPCA["VPC/subnet hoặc connector"]
    Private -->|"Không"| Default["Đường egress mặc định của Cloud Run"]
    Mode -->|"all-traffic"| VPCB["Mọi lưu lượng ra VPC"]
    VPCB --> Internal["IP nội bộ, VPN hoặc peering"]
    VPCB --> Public{"Đích public Internet?"}
    Public --> NAT["Cloud NAT / route / firewall<br/>nếu cần public egress"]
    VPCA --> Internal
~~~

### 4.1. `private-ranges-only`

Lưu lượng tới **địa chỉ được Google Cloud phân loại là internal/private** đi qua VPC. Lưu lượng tới public destinations theo đường egress mặc định. Phù hợp khi Java API gọi database private nhưng vẫn truy cập Google APIs hoặc dịch vụ public thông thường.

**Không hiểu nhầm:** một hostname có đuôi nội bộ nhưng DNS trả IP public không mặc nhiên đi qua VPC. Kiểm tra **IP được DNS phân giải**, route và phạm vi đích. Với prefix không thuộc loại private/internal được nhận diện, yêu cầu có thể cần `all-traffic`.

### 4.2. `all-traffic`

Mọi outbound từ Cloud Run được định tuyến qua VPC, gồm cả yêu cầu tới IP public. Đây là lựa chọn khi tổ chức muốn:

- Áp chính sách firewall/network inspection cho toàn bộ egress.
- Dùng **Cloud NAT** với **external IP cố định** để allowlist ở đối tác.
- Định tuyến tất cả traffic qua hạ tầng mạng riêng theo kiến trúc được phê duyệt.

**Quan trọng:** Khi chuyển sang `all-traffic`, nếu VPC **không có cách ra public Internet** thì HTTP request đến API ngoài có thể timeout. Thông thường phải có **Cloud NAT** (và đường đi/firewall thích hợp) hoặc lối đi được thiết kế riêng. Truy cập Google APIs cũng phải xét **Private Google Access**, Private Service Connect hoặc NAT theo thiết kế; đừng giả định cấu hình VPC egress tự cấp Internet.

| Mục tiêu | Lựa chọn gợi ý |
|---|---|
| Java → Cloud SQL private IP, còn gọi Pub/Sub/Cloud Storage qua API thông thường | `private-ranges-only` |
| Java → private VM, không có nhu cầu quản lý public egress | `private-ranges-only` |
| Đối tác yêu cầu allowlist **một external IP** | `all-traffic` + Cloud NAT với static external IP được quản lý |
| Tất cả outbound phải qua firewall/proxy | `all-traffic` và hạ tầng egress được cấu hình đầy đủ |

## 5. Direct VPC egress: kiến trúc và subnet sizing

~~~mermaid
flowchart LR
    CR["Cloud Run revision<br/>Orders API"] -->|"Direct VPC egress"| SUB["Subnet cr-egress-subnet<br/>10.42.0.0/24"]
    SUB --> VM["Backend VM private IP"]
    SUB --> DB["Cloud SQL private connection"]
    SUB --> VPN["VPN/Interconnect"]
    SUB --> NAT["Cloud NAT<br/>chỉ khi public traffic đi VPC"]
~~~

Cloud Run nhận **IPv4 tạm từ subnet**; địa chỉ không cố định theo instance. Subnet phải thuộc **cùng region** với Cloud Run service/job. Bạn có thể dùng nhiều services/jobs chung subnet nếu đủ IP.

### 5.1. Bẫy cấp phát IP khi scale

Theo hướng dẫn hiện hành:

- Subnet Direct VPC egress phải có dải IPv4 **/26 hoặc lớn hơn** (ví dụ /24 có nhiều địa chỉ hơn /26).
- Cloud Run cấp phát địa chỉ theo **khối /28** để tăng tốc scale.
- Với **service**, trạng thái ổn định có thể dùng khoảng **2 lần số container instances**. Sau scale-down, IP còn được giữ **tối đa khoảng 20 phút**.
- Khi **rolling update** chạy đồng thời revision cũ và mới, nhu cầu IP có thể tăng mạnh. Thiết kế ít nhất **2× tổng số instances cùng tồn tại**, cộng buffer.
- Với **job**, mỗi task có nhu cầu IP và thời gian giữ sau khi hoàn thành; phải tính cả **concurrent tasks** và executions chồng lấp.
- Sau khi bỏ liên kết, có thể cần **1–2 giờ** để Cloud Run nhả hết địa chỉ trước khi xóa subnet.

**Ví dụ sizing:** revision cũ tối đa 40 instances và revision mới tối đa 40 instances cùng xuất hiện. Nếu giữ buffer theo hệ số 2, nên dự trù tối thiểu `(40 + 40) × 2 = 160` địa chỉ, chưa tính tài nguyên khác dùng subnet. Subnet **/24** thường là điểm xuất phát hợp lý hơn /26 cho tình huống này. Không dùng trực tiếp một địa chỉ IP gán cho instance để cấu hình allowlist lâu dài.

### 5.2. Kiểm tra subnet và VPC

Giả sử nhóm mạng đã tạo:

~~~text
Project:  PROJECT_ID
Region:   asia-southeast1
VPC:      app-vpc
Subnet:   cr-egress-subnet (10.42.0.0/24)
Backend:  private IP ở subnet/routing hợp lệ
Image:    asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0
~~~

Các lệnh sau chỉ đọc:

~~~bash
gcloud compute networks describe app-vpc --project=PROJECT_ID

gcloud compute networks subnets describe cr-egress-subnet \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud run services list \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Nếu dùng **Shared VPC**, subnet có thể thuộc **host project** khác service project; cần cấp quyền **Compute Network User** hoặc quyền tương ứng trên subnet cho đúng Cloud Run/service identity theo hướng dẫn. Đừng tự đổi VPC host project hoặc cấp Owner để vượt lỗi deployment.

## 6. Thực hành A — Triển khai Cloud Run bằng Direct VPC egress

**Điều kiện:** Cloud Run API/Compute API đã sẵn sàng, image Java tồn tại, VPC và subnet đã được tạo, người triển khai có IAM cần thiết; backend private đang hoạt động. Lệnh dưới **thay đổi Cloud Run service** và có thể phát sinh phí. Không dùng project production nếu chưa được duyệt.

~~~bash
gcloud run deploy orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0 \
  --network=app-vpc \
  --subnet=cr-egress-subnet \
  --network-tags=cr-orders-egress \
  --vpc-egress=private-ranges-only \
  --no-allow-unauthenticated
~~~

**Ý nghĩa:**

- `--network` và `--subnet`: kết nối **trực tiếp** tới VPC/subnet trong region.
- `--network-tags`: gắn tag lên **revision** để áp firewall egress theo tag, khi loại firewall hỗ trợ.
- `--vpc-egress=private-ranges-only`: chỉ traffic nội bộ đi qua VPC.
- `--no-allow-unauthenticated`: yêu cầu xác thực khi gọi Cloud Run service; **không phải tham số VPC egress**.
- `--image`: Docker/OCI image từ Artifact Registry, không phải đường dẫn Maven JAR.

Đọc lại cấu hình:

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Trong output tìm **VPC access: Network, Subnet, Egress**, và xem revision hiện tại. Vì network tags thuộc revision, nếu traffic vẫn chuyển tới revision cũ, cần kiểm tra cấu hình của từng revision, không chỉ latest.

### 6.1. Thử `all-traffic` trên môi trường đã có NAT

Khi VPC đã có phương án outbound phù hợp:

~~~bash
gcloud run deploy orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0 \
  --network=app-vpc \
  --subnet=cr-egress-subnet \
  --network-tags=cr-orders-egress \
  --vpc-egress=all-traffic \
  --no-allow-unauthenticated
~~~

Không chạy lệnh này chỉ để “bật bảo mật cao hơn” nếu chưa kiểm tra đường tới **Cloud Storage, Artifact Registry, API đối tác, DNS, Cloud SQL**, route và firewall. Nó có thể làm dịch vụ ngừng gọi được các endpoint công khai.

### 6.2. Đọc địa chỉ được Cloud Run sử dụng

~~~bash
gcloud compute addresses list \
  --project=PROJECT_ID \
  --filter="purpose=SERVERLESS"
~~~

Đây là địa chỉ IP **dành cho hệ thống serverless**; không nên sửa/xóa thủ công. Nếu deploy báo thiếu IP subnet, mở rộng dải phụ thuộc và kế hoạch capacity theo tài liệu, không tìm cách gỡ các IP đang dùng.

## 7. Serverless VPC Access connector: khi nào cần?

Connector là tài nguyên quản lý kết nối mạng trung gian, gắn với **một VPC và region**. Cloud Run service/job dùng connector để gửi outbound vào mạng tương ứng.

~~~mermaid
flowchart LR
    CR["Cloud Run Java service"] --> C["Serverless VPC Access connector<br/>cr-java-conn"]
    C --> R["Dải IP riêng /28<br/>10.42.10.0/28"]
    R --> V["VPC app-vpc"]
    V --> DB["Private backend / Cloud SQL"]
    V --> NAT["Cloud NAT nếu all-traffic"]
~~~

Connector phù hợp khi:

- Có workload hoặc nền tảng serverless chưa áp dụng Direct VPC theo tính năng hiện hành.
- Tổ chức đã chuẩn hóa connector, có yêu cầu vận hành cụ thể và chấp nhận phí nền.
- Đo lường cold-start/kết nối Direct VPC và Cloud NAT cho thấy connector đáp ứng SLO tốt hơn.

**Không chọn connector chỉ vì có từ trước.** Connector có các instance tối thiểu; phí vẫn phát sinh khi Cloud Run scale về zero.

### 7.1. Subnet và giới hạn connector

- Cần **/28 không chồng lấn**, có thể chỉ định subnet /28 trống hoặc CIDR /28 chưa dùng để Google Cloud tạo subnet.
- Connector và Cloud Run service/job phải ở **cùng region**; VPC nằm ở project/phạm vi Shared VPC được hỗ trợ.
- Connector có **min-instances** (thường từ 2) và **max-instances** theo giới hạn hỗ trợ; các máy connector có kích thước `f1-micro`, `e2-micro` hoặc `e2-standard-4`.
- Connector có thể tăng số instance khi tải tăng nhưng **không tự scale-down lại** theo mô hình thông thường; cân nhắc capacity/cost.
- Giao thức hỗ trợ khác Direct: connector hiện **không hỗ trợ IPv6**; kiểm tra yêu cầu TCP/UDP/ICMP.
- Một connector bão hòa throughput có thể tăng latency/timeout cho nhiều services cùng dùng.

## 8. Thực hành B — Tạo connector và chuyển Cloud Run service

**Ví dụ có tác động và tốn phí:** giả định `10.42.10.0/28` chưa được dùng trong VPC, nằm khác dải của subnet Direct VPC và các mạng VPN/peering. Tạo connector bằng Google Cloud CLI:

~~~bash
gcloud compute networks vpc-access connectors create cr-java-conn \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --network=app-vpc \
  --range=10.42.10.0/28 \
  --min-instances=2 \
  --max-instances=3 \
  --machine-type=e2-micro
~~~

Chờ connector đạt trạng thái `READY` và xác nhận:

~~~bash
gcloud compute networks vpc-access connectors describe cr-java-conn \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Khi sử dụng **existing subnet /28**, dùng `--subnet=SUBNET_NAME` thay cho cặp `--network`/`--range` theo cú pháp phù hợp; với Shared VPC có thể cần `--subnet-project=HOST_PROJECT_ID` và role trên host project.

Triển khai revision sử dụng connector:

~~~bash
gcloud run deploy orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0 \
  --vpc-connector=cr-java-conn \
  --vpc-egress=private-ranges-only \
  --no-allow-unauthenticated
~~~

**Lưu ý khi chuyển phương thức:** Không duy trì **Direct network/subnet flags** và **connector flag** trong cùng một revision. Khi sửa Cloud Run service đã có, kiểm tra cấu hình revision mới đã thay thế thông số Direct, không chỉ copy một dòng cờ rồi giả định mọi annotation cũ được gỡ đúng.

### 8.1. Kiểm tra connector và traffic

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud compute networks vpc-access connectors describe cr-java-conn \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Đọc **connector name, region, state, min/max capacity** và monitor **throughput/instance count**. Nếu sử dụng nhiều Cloud Run services chung connector, tổng throughput có thể ảnh hưởng tất cả; cần capacity planning thay vì nhìn một service riêng.

## 9. Firewall, IAM, Shared VPC và DNS

### 9.1. Network source khác nhau giữa hai phương án

| Nội dung | Direct VPC egress | Serverless VPC Access |
|---|---|---|
| Source IP khi tới VPC | Địa chỉ tạm trong subnet Direct | IP của connector /28 |
| Định danh firewall egress | **Network tags của Cloud Run revision** hoặc subnet/source ranges tùy policy | Connector tag/CIDR và firewall rules tương ứng |
| Rule ingress trên backend VM | Phải cho phép source subnet và đúng port khi cần | Phải cho phép CIDR connector và đúng port khi cần |
| IAM triển khai | Quyền Cloud Run, VPC subnet/Shared VPC | Quyền Cloud Run + quản lý/sử dụng connector, host project nếu Shared VPC |
| Giới hạn khác | Thiếu IP khi scale, thiếu quyền subnet | Connector chưa `READY`, thiếu capacity/throughput |

**Ví dụ backend VM** có network tag `internal-backend` và đang nghe TCP/8081; chỉ trong sandbox, có thể tạo ingress allow rule theo subnet Direct:

~~~bash
gcloud compute firewall-rules create allow-cr-to-backend-lab \
  --project=PROJECT_ID \
  --network=app-vpc \
  --direction=INGRESS \
  --priority=900 \
  --action=ALLOW \
  --rules=tcp:8081 \
  --source-ranges=10.42.0.0/24 \
  --target-tags=internal-backend
~~~

Rule trên **cho phép cả subnet /24**, không chỉ riêng Orders API; nếu subnet chia sẻ nhiều workload, cần bổ sung policy phân đoạn và kiểm soát ở phía backend. Khi chuyển sang connector, nguồn sẽ là `10.42.10.0/28` và phải cập nhật rule tương ứng. Không mở `0.0.0.0/0` vào database port chỉ để giải quyết timeout.

Đối với Direct VPC egress, có thể dùng **network tags trên revision** để kiểm soát firewall **egress** tinh hơn; nếu đang áp chính sách deny-all, phải xác nhận đường tới DNS/Google APIs và backend được cho phép. **Allow rule bổ sung không đảm bảo hạn chế truy cập** nếu network đã có default egress allow hoặc rule khác rộng hơn.

### 9.2. IAM tách biệt

- **Deployer:** cần permission thay đổi Cloud Run và sử dụng network/subnet/connector theo phạm vi.
- **Runtime service account:** cần quyền API/Cloud SQL IAM hoặc Secret Manager theo workload; role này **không tự mở firewall**.
- **Backend:** xác thực bằng database credential/mTLS/IAM riêng, kể cả khi source đã nằm trong VPC.
- **Shared VPC:** host project sở hữu subnet; service project chứa Cloud Run. Cloud Run service agent/các principal tương ứng cần quyền subnet theo hướng dẫn, không dùng `roles/owner` làm giải pháp mặc định.

### 9.3. DNS, Private Service Connect và hybrid

Khi Java kết nối bằng hostname:

1. Xác định hostname thực sự resolve thành IP **private** hay **public**.
2. Kiểm tra Cloud DNS private zone/peering/forwarding có được liên kết và cấu hình đúng VPC.
3. Nếu đích on-premises, kiểm tra route đi về, VPN/Interconnect, firewall hai phía và DNS forwarding.
4. Nếu dùng Private Service Connect, kiểm tra endpoint private và DNS trỏ đúng endpoint.
5. Nếu `all-traffic`, kiểm tra public destinations cần NAT hoặc Google APIs đi qua Private Google Access/PSC phù hợp.

Không dùng DNS workaround đưa IP public vào cấu hình để né chính sách private networking; lỗi DNS và lỗi TCP nên được điều tra riêng.

## 10. Java API: kiểm thử đường TCP tới backend private

Giả sử Orders API chạy trên Cloud Run và cần kết nối một TCP backend (PostgreSQL hoặc test server) trong VPC. Việc kiểm tra **TCP handshake** giúp phân biệt “không tới được IP:port” với lỗi **database authentication**.

Một hàm Java 17 dùng chuẩn JDK:

~~~java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

public final class EgressProbe {
    private EgressProbe() {}

    public static boolean canConnect() {
        String host = System.getenv("TARGET_HOST");
        String portText = System.getenv("TARGET_PORT");
        if (host == null || portText == null) {
            throw new IllegalStateException("Missing TARGET_HOST or TARGET_PORT");
        }
        int port = Integer.parseInt(portText);

        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), 2_000);
            return true;
        } catch (IOException error) {
            return false;
        }
    }
}
~~~

Dùng hàm này trong **endpoint chẩn đoán đã bảo vệ bằng IAM**, không cho caller chỉ định host/port tùy ý để tránh SSRF/port scanning. Biến `TARGET_HOST`/`TARGET_PORT` chỉ chứa đích đã được quản trị. Thực thi trong request là tiện cho lab, nhưng production nên dùng healthcheck có giới hạn tần suất, retry/backoff và telemetry rõ ràng.

**Diễn giải kết quả:**

- `true`: Cloud Run đã thiết lập TCP đến host:port; **chưa chứng minh** JDBC authentication, SSL, SQL query hoặc quyền dữ liệu thành công.
- `false`: có thể do DNS, route, firewall, service không nghe port hoặc timeout; xem log an toàn và connectivity tương ứng.
- Nếu TCP thành công nhưng PostgreSQL trả `password authentication failed`, sửa cơ chế xác thực DB, không thay VPC egress.

Đối với **Cloud SQL private IP**, cần thêm phương án private networking của Cloud SQL (ví dụ Private Services Access hoặc PSC theo sản phẩm/kiến trúc), IAM/quyền DB và JDBC TLS/Auth Proxy/connector nếu được chọn. Không tạo Cloud SQL private IP chỉ bằng cách gắn subnet cho Cloud Run.

## 11. Chọn phương án cho hệ thống Java thực tế

**Bối cảnh:** `orders-api` chạy trên Cloud Run, dùng Cloud SQL PostgreSQL private IP, Cloud Storage để lưu hóa đơn và một API thanh toán công khai.

| Nhu cầu | Phương án đề xuất | Lý do |
|---|---|---|
| Tới Cloud SQL private IP | Direct VPC egress, `private-ranges-only` | Không cần connector, network route nội bộ |
| Cloud Storage/Google APIs | Gọi HTTPS bằng runtime IAM | Không bắt buộc đưa qua VPC nếu không có chính sách all-traffic |
| API thanh toán public | Đường public mặc định nếu được cho phép | Không cần NAT nếu vẫn dùng private-only egress |
| API thanh toán yêu cầu allowlist public IP | Direct VPC `all-traffic` + Cloud NAT static IP | Cho phép bên thứ ba nhận diện IP NAT ổn định |
| SLO startup rất nhạy, kiểm thử Direct+NAT cho thấy chậm | Cân nhắc connector + NAT | Đánh đổi latency với connector baseline cost |
| GKE/Compute Engine có sẵn VPC Shared | Direct/connector theo IAM Shared VPC | Phải có quyền subnet và route/firewall |

### 11.1. Một số bẫy khi chuyển phương án

- Đổi `private-ranges-only` thành `all-traffic` mà không thiết kế NAT khiến API thanh toán lỗi.
- Dùng subnet Direct /26 sát hết IP rồi rolling deployment tạo revision mới: service có thể bị giới hạn scale.
- Đổi sang connector nhưng không sửa firewall từ nguồn Direct subnet sang CIDR /28 của connector.
- Kết luận Cloud Run không truy cập được DB do “chưa bật network” trong khi DB chỉ nghe `127.0.0.1` hoặc chưa có private endpoint.
- Tăng concurrency/max-instances để xử lý timeout network, gây **cạn Cloud SQL connections** hoặc thiếu IP nhanh hơn.
- Xem **HTTP request vào Cloud Run** như một phần của outbound VPC; thực chất ingress và egress là hai cấu hình riêng.

## 12. Quan sát, troubleshooting và rollback

### 12.1. Quy trình chẩn đoán theo lớp

~~~mermaid
flowchart TD
    E["Java gọi backend thất bại"] --> D{"DNS resolve đúng IP?"}
    D -->|"Không"| DNS["Cloud DNS/forwarding/hostname"]
    D -->|"Có"| Route{"IP private/internal?"}
    Route -->|"Có"| VPC["Kiểm tra VPC egress method<br/>subnet/connector/route"]
    Route -->|"Không"| NET["private-only hay all-traffic?<br/>NAT/Private Google Access"]
    VPC --> FW{"Firewall hai chiều,<br/>backend listen port?"}
    NET --> FW
    FW -->|"Chưa"| FIX["Sửa đúng route/firewall/service"]
    FW -->|"Đủ"| AUTH["TLS, DB auth, IAM và app logs"]
~~~

### 12.2. Lệnh kiểm tra an toàn

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud compute networks subnets describe cr-egress-subnet \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud compute networks vpc-access connectors describe cr-java-conn \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud compute firewall-rules list --project=PROJECT_ID

gcloud run services logs read orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --limit=100
~~~

Chỉ đọc connector nếu thực sự có connector đó. Dùng **Cloud Monitoring**, **VPC Flow Logs** (nếu đã bật trên subnet), **Firewall Rules Logging**, **Cloud NAT logs** và **Cloud SQL logs** để đối chiếu source/destination, timing và policy. Không ghi secrets, JDBC password hoặc access token vào Cloud Logging.

### 12.3. Ma trận nguyên nhân

| Triệu chứng | Gợi ý nguyên nhân | Bước xử lý |
|---|---|---|
| Cloud Run deploy báo không dùng được subnet | Sai region, IAM Shared VPC hoặc org policy | So service region, subnet region và quyền service agent |
| Direct deploy báo thiếu địa chỉ IPv4 | Subnet quá nhỏ/hết IP, rolling revisions chồng lấp | Xem `purpose=SERVERLESS`, capacity và buffer |
| Connector không `READY` | CIDR /28 trùng, quyền/API, thiếu tài nguyên hoặc quota | Describe connector, kiểm tra subnet và event |
| Private backend timeout | Firewall, route, backend không nghe hoặc DNS | Kiểm tra nguồn Direct subnet/connector CIDR |
| Gọi Google APIs lỗi sau `all-traffic` | Thiếu NAT/PGA/PSC, route hoặc firewall | Kiểm tra đường public và Google API reachability |
| API đối tác nhận IP bất định | Đang dùng default egress hoặc NAT IP không cố định | Dùng all-traffic + static NAT IP theo thiết kế |
| Cold start tăng khi bật Direct | Thiết lập kết nối VPC có trễ | Startup probe có retry, đo SLO, cân nhắc connector |
| Latency tăng khi connector bận | Connector đạt throughput/instance cap | Monitoring throughput, tăng capacity hoặc chuyển Direct |
| Cloud SQL trả `permission denied` / auth failure | IAM/DB credential/TLS, không nhất thiết network | Xem DB logs và lỗi JDBC |
| Public client gọi Cloud Run bị 403 | Ingress/IAM Invoker | Không đổi egress để sửa lỗi inbound |

### 12.4. Rollback an toàn

Thay đổi Direct/connector tạo cấu hình/revision mới cho service. Trước khi chuyển production traffic:

1. Ghi revision hiện tại, lưu cấu hình đã được duyệt và baseline latency.
2. Tạo revision mới, thử backend private, Google APIs và public partner endpoints.
3. Dùng **traffic splitting** hoặc quy trình canary nếu service hỗ trợ và nhóm đã chuẩn bị.
4. Theo dõi lỗi kết nối, p95/p99, startup time, concurrency, Cloud SQL connection usage.
5. Nếu không đạt, chuyển traffic về **revision cũ** đã xác minh; lưu ý connector/subnet cũ phải còn hoạt động.
6. Sau khi không còn revision cần dùng, mới thu hồi connector và subnet theo trình tự dependency.

Không xóa connector đang dùng: dịch vụ khác có thể vẫn tham chiếu đến nó, và thao tác xóa connector không phải lúc nào cũng hiển thị cảnh báo đầy đủ về consumers.

## 13. Chi phí, độ tin cậy và dọn dẹp

| Thành phần | Direct VPC egress | Serverless VPC Access |
|---|---|---|
| Baseline connector compute | Không có | **Có**, min instances chạy dù Cloud Run scale-to-zero |
| IP planning | Subnet đủ lớn và địa chỉ có thời gian giữ | CIDR /28 riêng; connector capacity |
| Networking usage | Phí VPC traffic/egress liên quan | Phí traffic/egress và connector instances |
| Cloud NAT khi `all-traffic` | Có thể cần, có phí riêng | Có thể cần, có phí riêng |
| Logging/monitoring | Theo dữ liệu thu thập | Theo dữ liệu + telemetry connector |
| Vận hành | Quản trị subnet/IP/firewall/revision | Quản trị connector health, max scaling, firewall |

**Khuyến nghị ra quyết định:** so sánh theo **chi phí mỗi request đạt SLO** và **thời gian thiết lập kết nối ở đỉnh tải**, không chỉ giá CPU. Direct thường giảm tài nguyên trung gian, nhưng cần cấp đủ IPv4 và kiểm soát cold-start. Connector có baseline cost, nên chỉ dùng khi lợi ích thật được đo.

**Dọn sandbox** theo thứ tự: kiểm tra revision/service nào đang dùng connector/subnet → chuyển hoặc xóa revision thử nghiệm → xóa connector không còn consumer → chờ giải phóng IP Direct → xóa firewall rule/subnet/VPC được tạo riêng nếu không còn dùng. Không xóa VPC chung hoặc Cloud NAT production. Kiểm tra Billing vì disk, NAT/IP/logging có thể tiếp tục tính phí dù service scale về 0.

## 14. Bài tập và câu hỏi tự đánh giá

### Bài 1 — Chọn egress

Java API cần gọi **Cloud SQL private IP** và **Cloud Storage public API**. Không có yêu cầu kiểm tra mọi outbound qua VPC. Chọn Direct hay connector, `private-ranges-only` hay `all-traffic`? Giải thích.

**Gợi ý:** Direct + private-only thường đủ; service account vẫn cần IAM cho Cloud Storage.

### Bài 2 — Nhu cầu IP

Một Cloud Run service dùng Direct có revision cũ 50 instances và revision mới 50 instances cùng chạy trong đợt rollout. Dùng quy tắc buffer ~2 IP/instance, cần dự trù tối thiểu bao nhiêu địa chỉ và vì sao không dùng subnet /26?

**Gợi ý:** khoảng 200 IP chưa tính buffer/tài nguyên khác; subnet /24 hợp lý hơn.

### Bài 3 — NAT và IP cố định

Đối tác chỉ cho phép public egress IP `203.0.113.10`. Java service dùng `private-ranges-only` và Cloud NAT đã tạo.

**Hỏi:** traffic tới API đối tác có bắt buộc qua NAT không? Cần đổi những gì?

**Gợi ý:** không; default public egress có thể bỏ qua VPC. Phải dùng all-traffic, NAT static external IP và route/firewall đúng. Địa chỉ ví dụ thuộc dải tài liệu.

### Bài 4 — Connector /28

Doanh nghiệp có VPC dùng subnet `10.42.0.0/24` cho Direct. Kỹ sư định tạo connector trên `10.42.0.0/28` mà chưa kiểm tra.

**Hỏi:** có dùng được không và cần làm gì?

**Gợi ý:** CIDR connector không được trùng dải đã sử dụng; chọn /28 riêng chưa có resource/route overlap.

### Bài 5 — Lỗi 403 và timeout

Sau deploy, Cloud Run gọi backend private thành công qua TCP, nhưng JDBC trả `password authentication failed`. Người vận hành đề xuất cấp role Network Admin và mở firewall toàn VPC.

**Hỏi:** có hợp lý không? Lớp lỗi nào phải sửa?

**Gợi ý:** network kết nối được, cần xem xác thực database/secret/SSL; không mở quyền rộng.

### Bài 6 — Khả năng khôi phục

Nhóm chuyển từ connector sang Direct; p99 startup latency tăng, đồng thời subnet hết IP khi rolling update. Hãy viết phương án xử lý gồm **đo startup**, **bổ sung IP**, **canary/rollback**, và đánh giá khi nào giữ connector hợp lý.

**Gợi ý:** sizing theo peak revisions; startup probe và metrics; đánh đổi connector cost với SLO.

### Bài 7 — Phân biệt ingress và egress

Service dùng `--no-allow-unauthenticated` và Direct VPC `all-traffic`. Người ngoài được gửi request chưa xác thực tới URL Cloud Run hay không? Một VM trong cùng VPC có tự kết nối vào **địa chỉ instance** của Cloud Run service không?

**Gợi ý:** IAM Invoker vẫn được thực thi; Cloud Run service không biến thành VM nhận inbound direct qua VPC chỉ vì cấu hình egress.

## 15. Checklist trước khi triển khai production

- [ ] Có lý do thật để Cloud Run truy cập private network hoặc kiểm soát public egress.
- [ ] Đã chọn Direct VPC egress trước khi dùng connector, trừ khi có yêu cầu khác.
- [ ] Phân biệt cấu hình ingress, IAM Invoker và runtime service account với VPC egress.
- [ ] Region Cloud Run khớp region subnet/connector; Shared VPC permissions hợp lệ.
- [ ] Direct subnet **ít nhất /26**; capacity tính cả peak, rolling revisions và thời gian giữ IP.
- [ ] Connector dùng **/28 riêng**, đủ min/max throughput, có dự toán phí nền.
- [ ] `private-ranges-only` hoặc `all-traffic` được chọn theo toàn bộ destinations.
- [ ] Nếu `all-traffic`, đã kiểm tra Cloud NAT, Google APIs routing, DNS và public egress IP.
- [ ] Firewall allow/deny đặt đúng source subnet hoặc connector range, đúng port.
- [ ] Cloud SQL/Redis/on-prem endpoint có private network và return route phù hợp.
- [ ] Java app có connection timeout, retry/backoff, pooling và log không lộ secrets.
- [ ] Đã kiểm thử cả private/backend, Google APIs và external partner theo SLO.
- [ ] Đã đo throughput, cold start, lỗi connector/IP exhaustion, Cloud NAT và chi phí.
- [ ] Có canary/revision rollback và quy trình thu hồi connector/subnet an toàn.

## 16. Tài liệu chính thức

Kiểm tra giới hạn region, IP allocation, connector machine types và cú pháp CLI theo thời điểm triển khai:

- [Cloud Run — Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc)
- [Cloud Run — Connect with Serverless VPC Access connectors](https://docs.cloud.google.com/run/docs/configuring/vpc-connectors)
- [VPC — Serverless VPC Access overview](https://docs.cloud.google.com/vpc/docs/serverless-vpc-access)
- [VPC — Configure Serverless VPC Access](https://docs.cloud.google.com/vpc/docs/configure-serverless-vpc-access)
- [Cloud Run — VPC with Shared VPC](https://docs.cloud.google.com/run/docs/configuring/shared-vpc-direct-vpc)
- [Cloud NAT overview](https://docs.cloud.google.com/nat/docs/overview)
- [Cloud SQL — Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud Run — Service ingress settings](https://docs.cloud.google.com/run/docs/securing/ingress)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Serverless VPC Access pricing](https://cloud.google.com/vpc/docs/serverless-vpc-access#pricing)

**Điểm cần nhớ:** **Direct VPC egress** nối Cloud Run service/job vào VPC **không cần connector**, thường là lựa chọn ưu tiên; **Serverless VPC Access** thêm một connector có chi phí nền và giới hạn capacity nhưng vẫn hữu ích trong các tình huống phù hợp. Chọn `private-ranges-only` hay `all-traffic` quyết định **đường đi của traffic public**, nên khi định tuyến toàn bộ qua VPC thường phải thiết kế **Cloud NAT/Google APIs routing**. Kết nối tốt phụ thuộc đồng thời vào **subnet/IP, firewall, IAM, DNS, backend và ứng dụng Java**, và phải được xác minh bằng traffic thực cùng quy trình rollback.
