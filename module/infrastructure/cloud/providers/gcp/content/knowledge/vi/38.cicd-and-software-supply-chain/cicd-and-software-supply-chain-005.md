# Private pools và truy cập tài nguyên mạng riêng khi build

Một pipeline CI/CD có thể cần tải mã nguồn từ Git server nội bộ, cài dependency từ package registry riêng, chạy kiểm thử với cơ sở dữ liệu không có public IP hoặc triển khai ứng dụng vào cụm Kubernetes chỉ có private endpoint. Build chạy trong môi trường mặc định của dịch vụ thường không có đường mạng trực tiếp tới những tài nguyên đó. Mở public endpoint cho từng hệ thống chỉ để phục vụ build làm tăng bề mặt tấn công và tạo thêm công việc vận hành.

**Cloud Build private pools** cung cấp nhóm worker được Google Cloud quản lý riêng cho tổ chức. Khi kết nối private pool với VPC bằng Private Services Access, worker có thể giao tiếp với tài nguyên nội bộ qua địa chỉ IP nội bộ. Nhờ vậy, pipeline có thể truy cập private repository, registry nội bộ, database, private secret store endpoint hoặc runtime trong mạng được kết nối.

Trong module CLOUD_PROVIDERS_GCP, private pools kết nối CI/CD với VPC, IAM, Shared VPC, Cloud DNS, Cloud VPN, Cloud Interconnect và VPC Service Controls. Mô tả module tập trung vào việc khám phá project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; private pools là cách đưa quy trình build vào cùng ranh giới mạng và bảo mật đó.

Sau bài học này, bạn có thể:

- Phân biệt default pool và private pool của Cloud Build.
- Mô tả service producer network và kết nối VPC peering qua Private Services Access.
- Chọn dải IP cho private pool, tránh xung đột CIDR và cấu hình firewall.
- Tạo private pool bằng Google Cloud CLI và chọn pool trong cloudbuild.yaml.
- Cấu hình DNS riêng, Shared VPC và truy cập mạng on-premises.
- Hiểu giới hạn transitive peering khi kết nối tới dịch vụ Google-managed trong VPC khác.
- Phân biệt quyền quản lý worker pool, quyền yêu cầu build và quyền runtime của build.
- Giới hạn public egress, áp dụng VPC Service Controls và kiểm tra kết nối.

## 1. Default pool và private pool

### Default pool

Khi chạy build mà không chỉ định worker pool, Cloud Build sử dụng môi trường worker mặc định do Google quản lý. Mỗi build chạy trong môi trường được cô lập và có thể truy cập Internet công khai. Môi trường mặc định phù hợp với pipeline không cần tùy chỉnh sâu về worker hoặc truy cập tài nguyên nằm sau firewall của VPC.

### Private pool

Private pool là nhóm worker chuyên dụng theo cấu hình của khách hàng, nhưng vẫn do Cloud Build quản lý. Bạn không phải tự tạo, vá lỗi hay mở rộng VM worker. Pool có thể tự co giãn theo nhu cầu build và về 0 khi không có công việc. Bạn có thể cấu hình machine type, dung lượng disk, region, dải IP nội bộ và tùy chọn egress.

Điểm cần hiểu rõ: tên private pool không có nghĩa worker tự động nằm trong VPC của bạn. Worker được lưu trú trong một **service producer network** do Google sở hữu. Nếu muốn worker truy cập private resource trong VPC, bạn cần tạo kết nối private giữa service producer network và VPC đó.

| Khả năng | Default pool | Private pool |
|---|---|---|
| Google quản lý worker | Có | Có |
| Cấu hình machine type và disk | Giới hạn hơn | Linh hoạt hơn |
| Truy cập Internet công khai | Có | Có thể cấu hình |
| Kết nối vào VPC để truy cập private resource | Không có cấu hình peering tương đương | Có, qua Private Services Access |
| Tắt public IP của worker | Không phải cấu hình tương đương | Có thể dùng NO_PUBLIC_EGRESS |
| Tích hợp VPC Service Controls | Giới hạn theo mô hình mặc định | Có thể cấu hình private pool trong perimeter |

Hãy chọn private pool khi build cần truy cập private network, cần kiểm soát egress, cần machine type/disk riêng hoặc cần tuân thủ chính sách bảo mật của tổ chức. Nếu pipeline chỉ tải mã nguồn công khai, build image và đẩy image lên registry công khai, default pool có thể đã đủ.

## 2. Kiến trúc kết nối mạng

Private pool chạy trong service producer network. Private Services Access tạo một kết nối giữa VPC của khách hàng và service producer network bằng VPC Network Peering. Sau khi kết nối hoạt động, worker có thể gửi traffic tới các subnet hoặc private endpoint có route và firewall phù hợp trong VPC đã peering.

~~~mermaid
flowchart LR
    A[Cloud Build trigger hoặc người dùng] --> B[Cloud Build service]
    B --> C[Private pool workers]
    subgraph G[Google-owned service producer network]
        C
    end
    G <-->|Private Services Access / VPC peering| V[VPC của tổ chức]
    subgraph N[Customer VPC]
        V --> R[Private repository]
        V --> D[Database nội bộ]
        V --> K[Private GKE endpoint hoặc runtime]
        V --> S[Secret / artifact service]
    end
~~~

Kết nối này sử dụng địa chỉ IP nội bộ. Bạn không cần tạo public IP cho database hoặc Git server chỉ để worker có thể truy cập. Tuy nhiên, kết nối mạng không tự cấp quyền đọc repository, database hoặc secret; firewall, DNS và IAM vẫn phải được cấu hình riêng.

### Hai kiểu cấu hình mạng

1. **Dùng service producer network mặc định:** không cấu hình peering tới VPC khách hàng. Pool vẫn có machine type và disk tùy chỉnh, đồng thời có thể truy cập Internet theo egress đã chọn. Dùng cách này nếu build không cần private resources.
2. **Kết nối service producer network với VPC:** khai báo VPC cần peering và dải IP dành cho worker. Dùng cách này nếu build phải truy cập private resource trong VPC.

### Private Services Access và VPC Network Peering

Private Services Access thực hiện các bước chính:

1. Bật Service Networking API trong project quản lý VPC.
2. Chọn một dải CIDR chưa được dùng và reserve dải đó cho service producer.
3. Tạo private connection tới Service Networking API.
4. Cấu hình private pool sử dụng VPC đã kết nối và dải IP dành cho worker.

Dải CIDR được reserve là vùng địa chỉ dành cho service producer. Dải IP cấu hình trong private pool là phần địa chỉ worker được phép sử dụng bên trong allocation đó. Hai giá trị này có quan hệ chứa nhau; không được chọn tùy ý hoặc trùng với subnet, route, mạng on-premises hay allocation của dịch vụ khác.

## 3. Lập kế hoạch địa chỉ IP

Trước khi tạo kết nối, hãy kiểm kê:

- Các subnet hiện có trong VPC.
- Các dải CIDR của VPC được peering.
- Dải mạng on-premises được quảng bá qua Cloud VPN hoặc Cloud Interconnect.
- Các dải IP đã reserve cho Private Services Access khác.
- Dải IP mà công cụ build hoặc container sử dụng bên trong worker.
- Số build đồng thời và số worker cần cấp phát.

Cloud Build dành riêng các dải 192.168.10.0/24 và 172.17.0.0/16 cho Docker bridge network. Tránh dùng những dải này làm địa chỉ đích của tài nguyên mà builder cần truy cập, vì overlap có thể khiến traffic đi sai đường hoặc không tới được đích.

Ví dụ thiết kế minh họa:

| Thành phần | Dải IP mẫu | Mục đích |
|---|---|---|
| VPC ứng dụng | 10.20.0.0/16 | Subnet của VM, GKE node và workload |
| Allocation Private Services Access | 10.90.0.0/16 | Vùng dành cho service producer |
| Worker range của private pool | 10.90.0.0/24 | IP nội bộ được cấp cho worker pool |
| Mạng on-premises | 10.120.0.0/16 | Mạng trung tâm dữ liệu qua VPN hoặc Interconnect |

Đây chỉ là ví dụ. Phải xác nhận các dải không overlap với bất kỳ mạng nào đang được kết nối và đủ dung lượng cho số worker dự kiến.

### Chọn kích thước allocation và worker range

Với allocation cho Private Services Access, Google Cloud yêu cầu tối thiểu một khối /24 và khuyến nghị /16 cho nhiều dịch vụ Google. Prefix nhỏ hơn về mặt số học, ví dụ /16, chứa nhiều địa chỉ hơn /24.

Trường peeredNetworkIpRange của private pool có thể để trống để Cloud Build tự cấp một range mặc định /24. Nếu chỉ định range, CIDR phải nằm trong allocation đã reserve và prefix size không vượt quá /29. Một /24 có 254 địa chỉ host có thể dùng; một /29 chỉ có 6 địa chỉ host khả dụng. Số worker tối đa bị giới hạn bởi số IP khả dụng trong range.

Không nên chọn /29 chỉ để tiết kiệm địa chỉ khi pool có thể chạy nhiều build đồng thời. Hãy ước lượng concurrency, nhu cầu mở rộng và số IP dự phòng trước khi tạo pool.

## 4. Chuẩn bị API và IAM

### API cần bật

Trong project tạo private pool, bật Cloud Build API. Trong project chứa VPC, bật Service Networking API. Nếu dùng Cloud DNS private zone hoặc DNS peering, bật thêm Cloud DNS API trong project quản lý DNS.

~~~bash
gcloud services enable cloudbuild.googleapis.com \
  --project=PRIVATEPOOL_PROJECT_ID

gcloud services enable servicenetworking.googleapis.com \
  --project=NETWORK_PROJECT_ID

gcloud services enable dns.googleapis.com \
  --project=NETWORK_PROJECT_ID
~~~

Thay các giá trị mẫu bằng project ID thật. Principal bật API cần quyền serviceusage.services.enable, thường được cấp qua Service Usage Admin.

### Phân biệt ba danh tính

Private pool có ba nhóm quyền cần tách biệt:

| Danh tính | Vai trò thường dùng | Mục đích |
|---|---|---|
| Người hoặc service account quản trị pool | Cloud Build WorkerPool Owner: roles/cloudbuild.workerPoolOwner | Tạo, cập nhật, xem và xóa worker pool |
| Người hoặc service account yêu cầu build | Cloud Build WorkerPool User: roles/cloudbuild.workerPoolUser | Gửi build chạy trên pool |
| Service account thực thi các bước build | Các role theo tài nguyên đích, ví dụ Artifact Registry Reader hoặc quyền truy cập Secret Manager | Đọc dependency, lấy secret, ghi artifact hoặc triển khai ứng dụng |

Người tạo private connection trong project mạng cần quyền Compute Network Admin (roles/compute.networkAdmin) hoặc custom role tương đương. Quyền này áp dụng cho thao tác reserve IP và quản lý private connection.

### Build từ project khác với project chứa pool

Cloud Build cho phép build được khởi chạy từ project khác với project chứa private pool. Khi gọi build qua gcloud CLI hoặc API, cấp roles/cloudbuild.workerPoolUser trên project chứa pool cho user hoặc service account yêu cầu build.

Với trigger chạy ở project khác, cấp WorkerPool User cho service account được trigger sử dụng trên project chứa pool. Nếu trigger và pool cùng project, không cần cấp quyền cross-project này theo quy trình trigger thông thường.

Ví dụ cấp quyền cho service account của trigger:

~~~bash
gcloud projects add-iam-policy-binding PRIVATEPOOL_PROJECT_ID \
  --member="serviceAccount:BUILD_TRIGGER_SA" \
  --role="roles/cloudbuild.workerPoolUser"
~~~

Quyền dùng worker pool không đồng nghĩa với quyền đọc dữ liệu. Service account thực thi build vẫn cần role riêng để truy cập Artifact Registry, Secret Manager, GKE, database hoặc các tài nguyên đích. VPC peering cũng không thay thế IAM.

## 5. Tạo Private Services Access cho VPC

Ví dụ sau tạo kết nối từ service producer network của Cloud Build tới VPC tên ci-vpc trong project mạng. Chọn một allocation không overlap với các subnet hoặc route hiện có.

### Bước 1: Reserve dải IP

~~~bash
export NETWORK_PROJECT_ID="shared-network-prod"
export NETWORK_NAME="ci-vpc"
export RESERVED_RANGE_NAME="cloudbuild-private-pool"

gcloud compute addresses create "$RESERVED_RANGE_NAME" \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --description="Private Services Access range for Cloud Build" \
  --network="$NETWORK_NAME" \
  --project="$NETWORK_PROJECT_ID"
~~~

Lệnh trên để Google Cloud chọn một khối /16 còn trống. Nếu tổ chức đã quy hoạch CIDR, có thể chỉ định thêm --addresses với địa chỉ bắt đầu phù hợp. Không chọn CIDR chỉ dựa trên ví dụ mà chưa kiểm tra route và allocation hiện tại.

### Bước 2: Tạo private connection

~~~bash
gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges="$RESERVED_RANGE_NAME" \
  --network="$NETWORK_NAME" \
  --project="$NETWORK_PROJECT_ID"
~~~

Lệnh khởi tạo một long-running operation. Theo dõi operation tới khi hoàn tất thành công trước khi tạo private pool:

~~~bash
gcloud services vpc-peerings list \
  --network="$NETWORK_NAME" \
  --project="$NETWORK_PROJECT_ID"
~~~

Có thể xem allocation đã tạo:

~~~bash
gcloud compute addresses list \
  --global \
  --filter="purpose=VPC_PEERING" \
  --project="$NETWORK_PROJECT_ID"
~~~

Không xóa private connection khi còn private pool phụ thuộc vào nó. Nếu xóa kết nối, build có thể bị treo ở trạng thái queued rồi timeout do worker không còn đường kết nối dự kiến. Hãy xóa các private pool phụ thuộc trước, sau đó mới tháo kết nối theo quy trình.

## 6. Tạo private pool

### Tạo tệp cấu hình pool

Tệp cấu hình private pool và tệp cloudbuild.yaml có mục đích khác nhau:

- Tệp private pool config mô tả mạng, egress và cấu hình worker pool.
- Tệp Cloud Build config mô tả các bước build, image, artifact, timeout và pool được dùng để chạy build.

Ví dụ private-pool.yaml:

~~~yaml
privatePoolV1Config:
  networkConfig:
    egressOption: NO_PUBLIC_EGRESS
    peeredNetwork: projects/shared-network-prod/global/networks/ci-vpc
    peeredNetworkIpRange: 10.90.0.0/24
  workerConfig:
    machineType: e2-standard-4
    diskSizeGb: 200
    workerRelease: stable
~~~

Trong ví dụ:

- peeredNetwork là resource URL của VPC chứa tài nguyên nội bộ.
- peeredNetworkIpRange là dải worker nằm bên trong allocation đã reserve.
- machineType và diskSizeGb điều chỉnh tài nguyên worker.
- workerRelease chọn kênh phát hành worker; stable là lựa chọn minh họa.
- NO_PUBLIC_EGRESS tạo worker không có public IP và ngăn truy cập trực tiếp tới public IP, trừ khi được cấu hình qua proxy phù hợp.

Nếu build cần truy cập Internet công khai để tải dependency, hãy thiết kế đường egress được phê duyệt trước khi chọn NO_PUBLIC_EGRESS. Có thể dùng repository mirror nội bộ hoặc proxy do tổ chức quản lý. Không nên tắt public egress rồi kỳ vọng worker vẫn tự tải package từ Internet.

### Bước 2: Tạo worker pool

~~~bash
export PRIVATEPOOL_PROJECT_ID="ci-platform-prod"
export PRIVATEPOOL_ID="ci-private-pool"
export REGION="asia-southeast1"

gcloud services enable cloudbuild.googleapis.com \
  --project="$PRIVATEPOOL_PROJECT_ID"

gcloud builds worker-pools create "$PRIVATEPOOL_ID" \
  --project="$PRIVATEPOOL_PROJECT_ID" \
  --region="$REGION" \
  --config-from-file=private-pool.yaml
~~~

Tài khoản chạy lệnh cần roles/cloudbuild.workerPoolOwner trên project chứa pool và quyền cần thiết trên project mạng để thiết lập kết nối. Pool chỉ có thể dùng sau khi tạo thành công và cấu hình network đã sẵn sàng.

Kiểm tra trạng thái:

~~~bash
gcloud builds worker-pools describe "$PRIVATEPOOL_ID" \
  --project="$PRIVATEPOOL_PROJECT_ID" \
  --region="$REGION"
~~~

## 7. Chọn private pool cho một build

Trong cloudbuild.yaml, chỉ định tên đầy đủ của pool trong options.pool.name:

~~~yaml
steps:
  - name: "asia-southeast1-docker.pkg.dev/ci-platform-prod/ci-tools/db-check:1.0"
    entrypoint: bash
    args:
      - "-c"
      - |
        pg_isready -h 10.20.4.15 -p 5432 -d appdb

options:
  pool:
    name: "projects/ci-platform-prod/locations/asia-southeast1/workerPools/ci-private-pool"
  logging: CLOUD_LOGGING_ONLY
~~~

Ví dụ sử dụng một image công cụ đã được lưu trong Artifact Registry và kiểm tra kết nối TCP tới PostgreSQL private IP. Build service account phải có quyền đọc image và quyền cần thiết để thực hiện các thao tác khác. Đảm bảo image công cụ đã có sẵn trong registry có thể truy cập được; với pool không có public egress, không nên phụ thuộc vào image chỉ có trên registry công khai.

Gửi build vào đúng region:

~~~bash
gcloud builds submit \
  --project="application-build-prod" \
  --region="asia-southeast1" \
  --config="cloudbuild.yaml" \
  .
~~~

Pool có thể ở project khác với project khởi chạy build. Khi đó, tên pool trong cloudbuild.yaml phải trỏ tới đúng project chứa pool và principal yêu cầu build phải có WorkerPool User trên project đó.

## 8. Cấu hình firewall và route

Private Services Access tạo kết nối và trao đổi route subnet, nhưng không tự mở mọi cổng trên firewall. Bạn vẫn phải cho phép traffic từ dải worker tới đúng private resource.

### Firewall ingress

Ví dụ, nếu PostgreSQL có private IP 10.20.4.15 và lắng nghe TCP 5432, firewall rule ở VPC đích cần cho phép nguồn là dải worker của private pool:

| Thuộc tính | Ví dụ |
|---|---|
| Direction | Ingress |
| Source range | 10.90.0.0/24 |
| Destination | VM hoặc workload chạy database |
| Protocol/port | TCP 5432 |
| Action | Allow |

Không mở toàn bộ VPC cho mọi cổng. Hãy tạo rule theo workload, port và source range cần thiết. Nếu dùng firewall rule theo target tag hoặc service account, xác nhận tài nguyên đích thực sự mang tag hoặc identity tương ứng.

### Route và dải địa chỉ

VPC peering không phải VPN site-to-site tổng quát. Service producer network mặc định học subnet routes từ VPC của bạn. Nếu cần truy cập mạng on-premises qua Cloud VPN hoặc Cloud Interconnect, cần cấu hình trao đổi custom routes phù hợp để service producer network học được route tới mạng on-premises và phía on-premises có route quay về dải allocation/private pool.

Khi bật export custom routes trên private connection, hãy kiểm tra các route được quảng bá và tránh overlap với các dải dành cho Private Google Access. Trên phía on-premises, quảng bá các prefix cần thiết qua Cloud Router/BGP hoặc cấu hình route tương ứng. VPN tunnel hoặc VLAN attachment phải kết thúc ở cùng VPC (hoặc Shared VPC) với private connection vì VPC Network Peering không hỗ trợ transitive routing.

### Không có transitive peering

Giả sử:

1. Private pool peering với VPC A.
2. VPC A peering với VPC B.
3. Database hoặc private GKE endpoint nằm trong VPC B.

Worker của private pool không tự động đi xuyên qua VPC A để tới VPC B. VPC Network Peering không truyền route xuyên qua một VPC trung gian. Với private GKE control plane, control plane nằm trong project do Google quản lý và kết nối với VPC của khách hàng qua Private Service Connect; vì vậy peering từ private pool và kết nối PSC của GKE không tự tạo thành một đường truyền tiếp. Tài liệu Cloud Build hướng dẫn kết nối hai VPC do khách hàng quản lý bằng Cloud VPN để hoàn tất route, hoặc dùng DNS-based endpoint của GKE nếu đáp ứng yêu cầu.

Đây là nguyên nhân phổ biến khiến worker truy cập được VM trong VPC trực tiếp peering nhưng không truy cập được private endpoint của một dịch vụ Google-managed được peering vào cùng VPC.

## 9. DNS riêng cho private resources

Nếu build dùng hostname như git.corp.example.com hoặc db.corp.example.com, kết nối IP chưa đủ; worker cần phân giải đúng tên miền. Cloud DNS private zone mặc định chỉ hiển thị cho các VPC network được gắn vào zone. Để service producer network phân giải tên từ private zone, có thể cấu hình DNS peering với DNS suffix tương ứng.

Ví dụ:

~~~bash
gcloud services peered-dns-domains create cloudbuild-corp-dns \
  --network="ci-vpc" \
  --dns-suffix="corp.example.com." \
  --project="NETWORK_PROJECT_ID"
~~~

DNS suffix phải là tên miền đầy đủ và kết thúc bằng dấu chấm. Bật Cloud DNS API trước khi cấu hình. Chỉ chia sẻ suffix mà worker cần tra cứu; tránh chuyển tiếp toàn bộ không gian DNS nội bộ nếu không cần.

Kiểm tra lần lượt:

- Hostname có bản ghi A/AAAA phù hợp trong private zone.
- Private zone gắn với VPC mà private pool đã peering.
- DNS peering sử dụng đúng suffix.
- Firewall và route cho phép kết nối tới IP được trả về.
- Không có bản ghi public trùng tên làm client phân giải nhầm endpoint.

## 10. Shared VPC và mạng on-premises

### Shared VPC

Trong kiến trúc Shared VPC, host project sở hữu VPC, subnet, firewall và route; service project tạo private pool. Để dùng private pool với Shared VPC:

1. Gắn project chứa private pool vào host project có Shared VPC.
2. Reserve allocation và tạo Private Services Access connection trong host project.
3. Chọn Shared VPC đó làm peeredNetwork trong cấu hình pool.
4. Cấp quyền network administration cho nhóm quản lý host project.
5. Đảm bảo project chứa pool và project host thuộc cùng organization theo yêu cầu của Cloud Build.

Không tạo allocation ở service project rồi kỳ vọng host project tự nhìn thấy. Allocation và private connection thuộc VPC project sở hữu network.

### Kết nối tới on-premises

Nếu private resource nằm trong trung tâm dữ liệu, VPC có thể kết nối tới mạng on-premises bằng Cloud VPN hoặc Cloud Interconnect. Để worker truy cập:

- VPC phải có route tới các subnet on-premises qua VPN/Interconnect.
- Private connection phải export các custom routes cần thiết sang service producer network.
- Phía on-premises phải có route quay về dải IP của private pool.
- Firewall on-premises phải cho phép source range của worker tới port dịch vụ.
- DNS nội bộ phải được cấu hình để worker phân giải tên dịch vụ.
- Cần kiểm tra MTU, BGP route, firewall stateful và chiều traffic phản hồi.

Nếu tổ chức có nhiều VPC peering, hãy thiết kế đường kết nối rõ ràng thay vì giả định các mạng có thể truyền tiếp route qua nhau. Dùng VPN hoặc Interconnect ở vị trí phù hợp khi cần kết nối các mạng do tổ chức quản lý.

## 11. Kiểm soát egress và bảo vệ chuỗi cung ứng

### PUBLIC_EGRESS và NO_PUBLIC_EGRESS

Trường egressOption điều khiển public IP/egress của worker:

| Giá trị | Hành vi | Khi dùng |
|---|---|---|
| PUBLIC_EGRESS | Worker có public IP và có thể truy cập public Internet | Build cần tải dependency hoặc image từ nguồn công khai |
| NO_PUBLIC_EGRESS | Worker không có public IP; không thể trực tiếp egress tới public IP nếu không qua proxy | Build cần giới hạn public egress hoặc nằm trong VPC Service Controls perimeter |

Nếu không khai báo egressOption trong pool config, public egress được bật. NO_PUBLIC_EGRESS giúp giảm đường thoát dữ liệu ra Internet, nhưng không thay thế firewall, IAM hoặc kiểm soát dữ liệu trong build. Hãy chuẩn bị dependency mirror, Artifact Registry, proxy và đường truy cập Google APIs phù hợp với thiết kế mạng.

### VPC Service Controls

VPC Service Controls tạo security perimeter cho những dịch vụ Google Cloud được hỗ trợ, giúp hạn chế truy cập dữ liệu từ ngoài perimeter. Private pool có thể được cấu hình trong perimeter; tài liệu Cloud Build hướng dẫn đặt egressOption thành NO_PUBLIC_EGRESS cho cấu hình này.

VPC Service Controls bổ sung lớp kiểm soát ở cấp dịch vụ. Nó không thay thế firewall ingress/egress, quyền IAM, service account của build hoặc xác thực tới database. Hãy kiểm tra ingress/egress policy, project nằm trong perimeter và API mà pipeline sử dụng.

### Static egress IP

Public IP gắn với private pool khi public egress được bật không phải địa chỉ tĩnh do khách hàng kiểm soát. Nếu một dịch vụ bên ngoài yêu cầu allowlist một IP nguồn cố định, có thể dựng proxy/NAT gateway do tổ chức quản lý và định tuyến traffic qua gateway đó. Cách này cần thiết kế route, firewall, địa chỉ external IP và proxy; không nên giả định private pool có thể tự nhận một public IP cố định.

### Bảo vệ dependency và secret

- Lưu base image và dependency quan trọng trong Artifact Registry hoặc mirror nội bộ.
- Dùng build service account riêng, chỉ cấp quyền đọc artifact, lấy secret và ghi output cần thiết.
- Truy cập Secret Manager qua IAM và API phù hợp; không ghi secret vào log hoặc build argument có thể bị hiển thị.
- Pin image theo digest và kiểm tra nguồn builder.
- Tách pool theo mức độ tin cậy hoặc môi trường khi build của nhiều nhóm có quyền truy cập khác nhau.
- Dùng VPC Service Controls và egress policy để giảm nguy cơ exfiltration, đồng thời ghi log và giám sát truy cập.
- Hạn chế build script chạy lệnh tùy ý trên dữ liệu production; review nguồn mã và trigger.

## 12. Kiểm tra kết nối theo từng lớp

Khi build không truy cập được private resource, kiểm tra theo thứ tự sau:

1. **Pool:** build có thực sự chạy trong đúng private pool và region không?
2. **IAM dùng pool:** user hoặc trigger service account có roles/cloudbuild.workerPoolUser trên project chứa pool khi cần không?
3. **Peering:** Private Services Access connection có trạng thái hoạt động không?
4. **CIDR:** dải worker có nằm trong allocation và không overlap với subnet/route khác không?
5. **Route:** VPC có route tới destination và có route phản hồi về worker không?
6. **Firewall:** source range của pool có được phép tới đúng port trên tài nguyên đích không?
7. **DNS:** hostname có resolve ra private IP mong muốn không?
8. **IAM runtime:** build service account có quyền truy cập resource không?
9. **Egress:** pool có NO_PUBLIC_EGRESS trong khi build đang cố tải image hoặc package từ Internet không?
10. **Transitive peering:** đích có nằm sau một VPC peering khác hoặc một Google-managed service producer network không?

### Một số lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tạo pool báo network chưa peered với Service Networking API | Chưa tạo private connection hoặc tạo sai VPC/project | Kiểm tra Service Networking API, allocation và VPC peering list |
| Build chạy nhưng timeout khi kết nối private IP | Firewall, route hoặc CIDR không đúng | Kiểm tra source range, port, route hai chiều và VPC Flow Logs |
| Hostname không phân giải | Private zone chưa gắn đúng VPC hoặc thiếu DNS peering | Kiểm tra Cloud DNS zone, suffix và bản ghi |
| Truy cập VM trực tiếp được nhưng không tới private GKE/Cloud SQL | Dịch vụ đích có service producer network riêng; không có transitive peering | Dùng kiến trúc VPN/Interconnect, PSC hoặc endpoint DNS được dịch vụ hỗ trợ |
| Build không tải được image/package công khai | Pool dùng NO_PUBLIC_EGRESS | Dùng mirror nội bộ hoặc proxy/egress được phê duyệt |
| Build từ project khác không dùng được pool | Thiếu roles/cloudbuild.workerPoolUser | Cấp quyền cho principal yêu cầu build hoặc trigger service account trên pool project |
| Build truy cập mạng được nhưng API trả permission denied | Build service account thiếu IAM | Cấp role trên resource đích, kiểm tra đúng service account được build sử dụng |
| Build bị queued rồi timeout sau thay đổi mạng | Private connection bị xóa hoặc peering không còn hoạt động | Khôi phục kết nối hoặc tạo lại theo quy trình; không xóa PSA khi pool còn phụ thuộc |
| Pool tạo được nhưng không đủ worker đồng thời | Worker IP range quá nhỏ | Tăng range trong giới hạn cho phép và tính lại số IP usable |

## 13. Thực hành kiểm tra private database

Giả sử nhóm phát triển cần chạy migration test tới PostgreSQL có private IP trong VPC. Thiết kế tối thiểu:

1. Tạo private pool ở region gần database.
2. Kết nối pool với VPC qua Private Services Access.
3. Reserve worker range không overlap với subnet và route.
4. Cho phép ingress TCP 5432 từ worker range tới database.
5. Tạo private DNS record nếu muốn dùng hostname thay cho IP.
6. Cấp quyền Artifact Registry Reader cho build service account để lấy image kiểm thử.
7. Cấp secret access theo phạm vi cần thiết nếu password lấy từ Secret Manager.
8. Đưa build vào private pool bằng options.pool.name.
9. Chạy pg_isready hoặc một kiểm tra kết nối có timeout ngắn.
10. Sau khi xác nhận kết nối, chạy migration test bằng tài khoản database có quyền tối thiểu.

Không đưa password database vào cloudbuild.yaml hoặc command line. Lấy secret trong bước build bằng cơ chế được Cloud Build hỗ trợ và giới hạn quyền truy cập cho build service account.

## 14. Checklist trước khi dùng private pool trong production

- [ ] Xác định chính xác private resource mà build cần truy cập.
- [ ] Chọn region và project sở hữu private pool.
- [ ] Bật Cloud Build API và Service Networking API đúng project.
- [ ] Reserve allocation không overlap với VPC, on-premises và các range hiện có.
- [ ] Tạo Private Services Access connection và xác nhận trạng thái.
- [ ] Cấu hình peeredNetwork và worker IP range trong private pool.
- [ ] Chọn PUBLIC_EGRESS hoặc NO_PUBLIC_EGRESS theo dependency và chính sách.
- [ ] Cấp WorkerPool Owner cho người quản trị pool.
- [ ] Cấp WorkerPool User cho principal gọi build qua CLI/API và cho trigger service account khi trigger ở project khác với project chứa pool.
- [ ] Cấp IAM riêng cho build service account trên resource đích.
- [ ] Cấu hình firewall chỉ cho source range và port cần thiết.
- [ ] Kiểm tra route, route phản hồi và transitive peering.
- [ ] Cấu hình DNS peering nếu dùng private hostname.
- [ ] Kiểm tra Shared VPC hoặc hybrid connectivity nếu có.
- [ ] Có kế hoạch mirror dependency, image và proxy nếu tắt public egress.
- [ ] Kiểm thử build và lưu log/VPC Flow Logs để điều tra.
- [ ] Không xóa private connection khi còn pool phụ thuộc.

## 15. Kết luận

Cloud Build private pools cho phép đưa worker build tới gần các tài nguyên nội bộ mà vẫn giữ mô hình worker do Google quản lý. Private Services Access kết nối service producer network với VPC qua VPC Network Peering; sau đó route, firewall, DNS và IAM quyết định build có thể truy cập tài nguyên nào.

Triển khai thành công cần phối hợp bốn lớp: kết nối mạng, phân giải tên, quyền của build service account và chính sách egress. Đặc biệt, phải tính đến giới hạn không có transitive peering khi truy cập dịch vụ Google-managed hoặc mạng VPC khác. Khi các lớp này được cấu hình và kiểm thử riêng, private pool có thể hỗ trợ pipeline an toàn để build, test và deploy ứng dụng trong môi trường GCP có tài nguyên mạng riêng.

## Tài liệu tham khảo

- [Private pools overview – Cloud Build](https://docs.cloud.google.com/build/docs/private-pools/private-pools-overview)
- [Set up private pools in a VPC network](https://docs.cloud.google.com/build/docs/private-pools/set-up-private-pool-to-use-in-vpc-network)
- [Create and manage private pools](https://docs.cloud.google.com/build/docs/private-pools/create-manage-private-pools)
- [Private pool configuration file schema](https://docs.cloud.google.com/build/docs/private-pools/private-pool-config-file-schema)
- [Run builds in a private pool](https://docs.cloud.google.com/build/docs/private-pools/run-builds-in-private-pool)
- [Using Cloud Build in a private network](https://docs.cloud.google.com/build/docs/private-pools/use-in-private-network)
- [Access private GKE clusters with Cloud Build private pools](https://docs.cloud.google.com/build/docs/private-pools/accessing-private-gke-clusters-with-cloud-build-private-pools)
- [Use VPC Service Controls with private pools](https://docs.cloud.google.com/build/docs/private-pools/using-vpc-service-controls)
- [Configure private services access](https://docs.cloud.google.com/vpc/docs/configure-private-services-access)
- [Cloud Build IAM roles and permissions](https://docs.cloud.google.com/build/docs/iam-roles-permissions)
- [Troubleshoot Cloud Build](https://docs.cloud.google.com/build/docs/troubleshooting)
