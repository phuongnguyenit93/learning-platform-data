# Cloud Workstations và môi trường phát triển được quản lý

Trong một nhóm phát triển, mỗi người thường cài đặt Java, Node.js, Docker, IDE, SDK và các thư viện theo cách riêng. Sự khác biệt phiên bản khiến tính năng chạy tốt trên máy người này nhưng lỗi trên máy người khác; nhân viên mới mất nhiều thời gian thiết lập; nhóm bảo mật khó kiểm soát đường truy cập vào tài nguyên đám mây. **Môi trường phát triển được quản lý** giúp chuẩn hóa công cụ, tài nguyên máy, quyền và vòng đời môi trường.

Trong phạm vi học phần **CLOUD_PROVIDERS_GCP**, **Google Cloud Workstations** là dịch vụ cung cấp môi trường phát triển trên Google Cloud với cấu hình được tổ chức quản lý tập trung. Bài học thuộc chương **Công cụ và môi trường GCP**, hỗ trợ người học khi phát triển và thử nghiệm ứng dụng trước khi triển khai lên Compute Engine, GKE hoặc Cloud Run, kết nối Cloud Storage/cơ sở dữ liệu và quản trị IAM, VPC, chi phí, độ tin cậy.

Sau bài học, bạn có thể:

- Giải thích khi nào Cloud Workstations phù hợp với một nhóm phát triển.
- Phân biệt **workstation cluster**, **workstation configuration** và **workstation**.
- Thiết lập môi trường lập trình, truy cập bằng IDE trên trình duyệt hoặc trình soạn thảo cục bộ.
- Thiết kế container image, machine type, persistent directory, mạng và quyền IAM.
- Vận hành Start/Stop, cập nhật môi trường và kiểm soát chi phí.
- Đề xuất quy trình onboarding và triển khai ứng dụng an toàn từ workstation.

## 1. Môi trường phát triển được quản lý giải quyết vấn đề gì?

Môi trường phát triển bao gồm IDE, compiler, build tool, package manager, CLI, container tooling, thông tin xác thực và kết nối đến các hệ thống phụ thuộc. Nếu mỗi lập trình viên tự cấu hình, dự án dễ gặp các lỗi kiểu “chạy trên máy tôi” do thiếu dependency hoặc khác phiên bản.

Một dịch vụ được quản lý cung cấp **mẫu môi trường có thể tái tạo**, cấp phát khi cần, kiểm soát danh tính truy cập và có chính sách chi phí chung. Với Cloud Workstations, nhóm platform có thể duy trì mẫu cho backend Java, frontend hoặc dữ liệu; mỗi developer tạo workstation riêng dựa trên mẫu đó.

| Lựa chọn | Khi phù hợp | Điểm cần cân nhắc |
|---|---|---|
| Máy cục bộ | Cần làm việc ngoại tuyến, phụ thuộc phần cứng cục bộ | Dễ khác cấu hình và khó kiểm soát tập trung |
| **Cloud Shell** | Chạy nhanh lệnh `gcloud`, học GCP, thử nghiệm ngắn | Không được thiết kế chủ yếu để cấp workstation dài hạn với các mẫu tùy biến cho cả nhóm |
| **Cloud Workstations** | Nhiều lập trình viên cần IDE và công cụ nhất quán, quyền/mạng quản lý tập trung | Cần quản trị cấu hình, IAM, mạng và chi phí dịch vụ |
| VM Compute Engine tự quản | Cần kiểm soát đặc biệt ở cấp VM | Nhóm phải tự lo nhiều khía cạnh về cấp phát và vòng đời |
| Dev container cục bộ | Muốn đồng nhất dependencies nhưng chạy trên laptop | Không tự cung cấp lớp quản trị VM, truy cập và mạng trên Google Cloud |

Cloud Workstations là **nơi phát triển và kiểm thử**, không phải dịch vụ dùng để chạy workload production thay cho GKE, Cloud Run hoặc Compute Engine.

## 2. Kiến trúc: Cluster → Configuration → Workstation

Cloud Workstations có ba loại tài nguyên chính:

| Thành phần | Chức năng | Ví dụ |
|---|---|---|
| **Workstation cluster** | Nhóm workstation trong một region, quản lý kết nối VPC và gateway của dịch vụ | `dev-cluster` |
| **Workstation configuration** | Mẫu định nghĩa VM, image, IDE, persistent disk, timeout và các cấu hình vận hành | `java-backend` |
| **Workstation** | Môi trường cá nhân được tạo từ configuration; có thể Start, Stop và Launch | `alice-java` |

~~~text
Google Cloud project: team-dev-tools
└── Region: region được chọn theo người dùng và workload
    └── Workstation cluster: dev-cluster
        ├── Kết nối VPC / subnet / gateway
        ├── Configuration: java-backend
        │   ├── Machine type / quota
        │   ├── IDE + JDK + build tools trong container image
        │   ├── Persistent home directory
        │   ├── IAM / service account / idle timeout
        │   ├── Workstation: alice-java
        │   └── Workstation: bob-java
        └── Configuration: frontend
            ├── IDE + Node.js trong image khác
            └── Workstation: carol-frontend
~~~

**Workstation cluster không phải GKE cluster.** Nó là tài nguyên Cloud Workstations quản lý các môi trường lập trình, có vị trí theo region. Các workstation chạy trên VM Compute Engine trong project, bên trong VM là container chứa editor và công cụ mà configuration quy định.

Một configuration dùng chung cho nhiều workstation. Khi nhóm cập nhật container image hoặc machine type trong configuration, workstation nhận cấu hình mới vào lần khởi động tiếp theo theo cơ chế của dịch vụ. Vì vậy phải kiểm thử thay đổi mẫu, đặc biệt khi có nhiều người đang sử dụng.

### Project, region, mạng và phân tách nhóm

- **Project:** nơi bật API, quản lý IAM, billing và các tài nguyên Workstations.
- **Region:** vị trí cluster. Chọn theo độ trễ, vùng có hỗ trợ dịch vụ, yêu cầu dữ liệu và các dịch vụ cần kết nối.
- **VPC/subnet:** đường mạng để truy cập nguồn dữ liệu hoặc dịch vụ cần dùng.
- **Configuration:** đơn vị phân biệt kiểu máy, môi trường phần mềm và nhiều chính sách sử dụng.

Không cần một cluster cho mỗi developer. Hãy xem xét cluster khác nếu cần region hay kết nối VPC khác; tạo configuration khác nếu nhóm Java và frontend cần dependency, machine type hoặc quyền khác nhau.

## 3. Vòng đời và khả năng lưu dữ liệu

Workstations chạy trên **VM có vòng đời tạm thời**. Developer bật môi trường khi làm việc và dừng khi kết thúc; môi trường phát triển có thể dùng image được quản lý tập trung và persistent home directory để giữ dữ liệu giữa các phiên.

~~~mermaid
flowchart LR
    A[Platform tạo cluster] --> B[Platform tạo configuration]
    B --> C[Cấp quyền developer]
    C --> D[Tạo workstation]
    D --> E[Start và Launch]
    E --> F[Viết code, build, test]
    F --> G[Stop hoặc tự dừng]
    G --> E
    G --> H[Xóa khi không còn sử dụng]
~~~

Khi **Stop**, VM tạm thời bị hủy và trạng thái chạy trong RAM mất. Nếu được cấu hình **persistent home directory**, ổ đĩa được gắn lại khi Start lần sau để giữ mã nguồn và các file trong vùng home. Nếu không có persistent storage, dữ liệu phiên làm việc có thể mất. Chính sách xóa hay giữ persistent disk khi **Delete workstation** do `reclaim policy` quyết định.

| Dữ liệu hoặc trạng thái | Sau Stop/Start |
|---|---|
| Mã nguồn trong home trên persistent disk | Được giữ nếu persistent directory được cấu hình |
| Cấu hình editor và file làm việc trong home | Được giữ nếu lưu ở đúng vùng bền vững |
| Thay đổi trong lớp ghi tạm của container hoặc đường dẫn không bền vững | Có thể mất |
| Process, terminal đang chạy, bộ nhớ RAM | Không được giữ |
| Commit đã push lên kho Git từ xa | Vẫn tồn tại trên kho nguồn |
| Persistent disk sau khi xóa hẳn workstation | Tùy `DELETE` hay `RETAIN` |

**Persistent disk không thay thế Git hoặc backup.** Nên để dependency cố định trong container image, lưu code trên repository và không đưa mật khẩu/token vào home hoặc image khi không có biện pháp kiểm soát thích hợp.

### Idle timeout, running timeout và quick start

- **Idle timeout:** tự dừng khi workstation không có hoạt động tương tác sau khoảng thời gian cấu hình.
- **Running timeout:** tự dừng sau khoảng thời gian hoạt động tối đa theo cấu hình.
- **Quick start pool:** giữ sẵn một số VM để giảm thời gian chờ khi mở workstation; có thêm chi phí.

Cần thử nghiệm timeout với quy trình chạy test/build dài; một tác vụ nền vẫn có thể bị ngắt nếu workstation bị dừng theo chính sách. Khi vận hành nhóm, hãy giải thích rõ nơi lưu dữ liệu để developer tránh mất công việc.

## 4. Chuẩn hóa IDE và dependencies với container image

Cloud Workstations cung cấp các base image với editor và công cụ cơ bản. **Cloud Workstations Base Editor** dựa trên Code OSS, hỗ trợ terminal, extension và Cloud Code; dịch vụ cũng hỗ trợ nhiều lựa chọn IDE hoặc truy cập bằng IDE cục bộ/SSH tùy cấu hình.

Với dự án Java, một cấu hình `java-backend` có thể gồm JDK phù hợp, Git, Gradle/Maven, gcloud CLI và extension cho Java. Nhóm platform chọn base image phù hợp rồi tùy biến bằng Dockerfile để môi trường của mọi developer nhất quán.

Ví dụ **minh họa** cách mở rộng một image nền đã được tổ chức phê duyệt (đường dẫn/tên image phải được cấu hình khi build):

~~~dockerfile
ARG BASE_IMAGE
FROM $BASE_IMAGE

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       git curl unzip openjdk-21-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

# Không nhúng secret, token hoặc khóa riêng tư vào image.
# Không ghi cấu hình người dùng vào /home khi build:
# home được mount khi workstation bắt đầu phiên làm việc.
~~~

Đây là mẫu cần điều chỉnh: image nền phải hỗ trợ `apt-get`, đảm bảo entrypoint và quyền người dùng tương thích; trước khi đưa vào nhóm, hãy pin image theo digest, kiểm tra JDK và cấu hình editor. Nếu custom image nằm trong Artifact Registry riêng tư, service account của workstation VM phải có quyền đọc image.

Một chu trình duy trì image tốt gồm: quản lý Dockerfile bằng Git, build bằng pipeline, quét lỗ hổng, chạy thử trên một workstation kiểm thử, sau đó cập nhật configuration và hướng dẫn thành viên khởi động lại. Tránh phụ thuộc `latest` không kiểm soát và tránh cài dependency tùy hứng trong vùng tạm vì lần khởi động sau có thể mất.

## 5. Tạo workstation bằng Google Cloud Console

Điều kiện trước khi tạo:

- Có project đã bật **billing**, đủ quota và quyền quản trị phù hợp.
- Bật **Cloud Workstations API** (`workstations.googleapis.com`).
- Chọn region hỗ trợ dịch vụ và machine type dự kiến.
- Xác định VPC/subnet, gateway, IAM, container image và dung lượng home disk.
- Có Google Group hoặc danh tính sẽ được cấp quyền tạo và sử dụng.

**Bước 1: Tạo cluster.** Trong Console vào **Cloud Workstations → Cluster management → Create**. Nhập tên, chọn region; khi cần dùng mạng riêng, chọn VPC/subnet và public hoặc private gateway phù hợp.

**Bước 2: Tạo configuration.** Vào **Cloud Workstations → Workstation configurations → Create**. Chọn cluster, loại VM, IDE/image, persistent directory, chính sách reclaim và thời gian tự dừng. Xem xét tắt quick start pool để giảm chi phí trong môi trường thử nghiệm.

**Bước 3: Cấp quyền.** Ở phần users/permissions, thêm Google Group của developer được phép tạo workstation. Kiểm tra quyền của service account nếu có custom image riêng tư hoặc cần truy cập API GCP.

**Bước 4: Developer tạo workstation.** Vào **Cloud Workstations → Workstations → Create**, chọn configuration và nhập tên môi trường cá nhân.

**Bước 5: Launch và kiểm tra.** Developer bấm **Launch** để mở IDE trên trình duyệt. Thử terminal, clone một repository, chạy build; sau đó Stop, Start lại và kiểm tra dữ liệu trong home.

Tạo cluster và cấu hình có thể mất thời gian. Nếu không tạo được, xem lỗi IAM, quota, API, mạng hoặc các ràng buộc Organization Policy. Cần chọn phương án private cluster theo thiết kế của nhóm mạng; việc chọn private endpoint có thể đòi hỏi DNS, Private Service Connect và đường truy cập riêng.

## 6. Ví dụ CLI: tạo một workstation cơ bản

Đoạn sau dùng **Bash**, là mẫu thao tác thử nghiệm. Thay project ID và region bằng giá trị phù hợp; lệnh thật có thể tạo tài nguyên tính phí.

~~~bash
PROJECT_ID="my-dev-tools-project"
REGION="us-central1"
CLUSTER="dev-cluster"
CONFIG="java-dev"
WORKSTATION="dev-alice"

# Chọn project và bật Workstations API.
gcloud config set project "$PROJECT_ID"
gcloud services enable workstations.googleapis.com

# Tạo cluster (cấu hình gateway mặc định để thực hành).
gcloud workstations clusters create "$CLUSTER" \
  --region="$REGION"

# Tạo configuration: Code OSS, máy 4 vCPU, home disk 50 GB,
# tự dừng sau 1 giờ không tương tác và không giữ VM quick start.
gcloud workstations configs create "$CONFIG" \
  --cluster="$CLUSTER" \
  --region="$REGION" \
  --machine-type=e2-standard-4 \
  --container-predefined-image=codeoss \
  --pd-disk-type=pd-balanced \
  --pd-disk-size=50 \
  --idle-timeout=3600 \
  --pool-size=0

# Tạo môi trường cá nhân từ configuration.
gcloud workstations create "$WORKSTATION" \
  --cluster="$CLUSTER" \
  --config="$CONFIG" \
  --region="$REGION"

# Khởi động khi cần sử dụng.
gcloud workstations start "$WORKSTATION" \
  --cluster="$CLUSTER" \
  --config="$CONFIG" \
  --region="$REGION"
~~~

Sau khi Start, mở Console để Launch. Lệnh này chưa thay thế việc phân quyền cho người khác: administrator phải gán IAM cần thiết ở đúng phạm vi. Người học nên xem `gcloud workstations ... --help` trước khi chạy vì cờ cấu hình và giá trị mặc định có thể được cập nhật.

## 7. IAM: phân tách quyền quản trị, sử dụng và truy cập GCP

Quyền dùng IDE khác với quyền truy cập tài nguyên Google Cloud từ terminal hoặc ứng dụng trong workstation.

| Vai trò/nhóm | Quyền hoặc cách dùng | Phạm vi đề xuất |
|---|---|---|
| Platform Admin | `roles/workstations.admin`: quản lý cluster, configuration và workstation | Project chuyên về công cụ phát triển, cấp hạn chế |
| Developer tạo môi trường | `roles/workstations.workstationCreator`: tạo workstation từ cấu hình được cho phép | Configuration hoặc project phù hợp |
| Developer sử dụng môi trường | `roles/workstations.user`: Start/Stop/sử dụng workstation | Workstation của người đó |
| Quyền xem hoạt động | `roles/workstations.operationViewer` khi cần theo tài liệu IAM | Project |
| Danh tính chạy code | Service account hoặc danh tính được Google Cloud hỗ trợ | Chỉ các dịch vụ và tài nguyên dev cần thiết |

Theo quy trình tạo thông thường, người dùng tạo workstation qua vai trò Creator được cấp quyền User trên workstation họ tạo. Điều này không tự cấp quyền triển khai Cloud Run hay xem dữ liệu trong Cloud Storage.

Các nguyên tắc:

1. Gán quyền vào **Google Group** thay vì từng cá nhân khi quản lý nhóm đông người.
2. Developer dùng quyền creator/user, không mặc định là admin toàn project.
3. Service account của VM được cấp **quyền tối thiểu**; nếu image ở Artifact Registry riêng tư thì cần quyền đọc image.
4. Tách danh tính người lập trình với danh tính **CI/CD triển khai production**; không gán quyền production chỉ để chạy demo.
5. Không ghi service-account key, token hoặc mật khẩu vào image, repository hay script trong home.
6. Xem xét quyền truy cập cổng của workstation khi chạy web server nội bộ; không tự động cho phép truy cập công khai.

Với thư viện gọi Google Cloud API, phải hiểu ứng dụng đang dùng credential nào (ví dụ Application Default Credentials) và kiểm tra đúng IAM trên **tài nguyên đích**. Có quyền vào workstation không bảo đảm có quyền đến một database hoặc bucket.

## 8. Thiết kế mạng và bảo mật

Workstation có thể cần tải dependencies từ Internet, lấy image từ Artifact Registry hoặc gọi database và microservice trong VPC. Vì vậy, chọn gateway, VPC và egress là quyết định kiến trúc quan trọng.

| Cấu hình | Mục đích | Kiểm tra |
|---|---|---|
| **Public gateway** | Cách truy cập qua endpoint dịch vụ từ mạng công cộng khi được cho phép | Google authentication/IAM, giới hạn cổng và kiểm soát egress |
| **Private gateway/cluster** | Truy cập gateway thông qua đường mạng private | VPC, DNS, Private Service Connect, định tuyến/VPN hoặc kết nối doanh nghiệp |
| **Disable public IP cho VM** | Giảm bề mặt kết nối trực tiếp trên Internet | Cloud NAT hoặc Private Google Access theo nhu cầu truy cập API/dịch vụ |

Public gateway **không có nghĩa ai cũng được vào IDE**: quyền truy cập vẫn phải được xác thực và kiểm soát. Ngược lại, private gateway không tự đảm bảo toàn bộ hệ thống an toàn nếu firewall, service account hoặc quyền đến dữ liệu quá rộng.

Ví dụ backend cần database chỉ có private IP:

- Đặt workstation trong VPC/subnet có tuyến kết nối đến database.
- Cấu hình firewall chỉ cho phép nguồn và cổng thật sự cần.
- Dùng DNS và network access phù hợp cho các API Google Cloud và Artifact Registry.
- Cấp quyền truy cập database cho đúng danh tính; tách credential của dev và production.
- Tránh sao chép dữ liệu sản xuất vào workstation khi chưa có biện pháp bảo vệ và quyền sử dụng rõ ràng.

Một số ràng buộc Organization Policy có thể ảnh hưởng việc tạo VM image và Private Service Connect. Cần kiểm tra yêu cầu của Cloud Workstations trước khi thiết lập cluster tại tổ chức có chính sách mạng chặt.

## 9. Từ môi trường phát triển đến triển khai Cloud Run/GKE

Ví dụ nhóm xây dựng REST API Java và triển khai bằng Cloud Run:

~~~text
Developer
  → Cloud Workstations (code, debug, unit test)
  → Git repository + pull request
  → CI/CD (build, security checks, test)
  → Artifact Registry (image đã được xét duyệt)
  → Cloud Run: dev → staging → production
  → Cloud Logging / Cloud Monitoring
~~~

Sau khi nhóm platform đã chuẩn bị JDK và build tool:

~~~bash
java -version
git clone https://github.com/example-org/sample-java-api.git
cd sample-java-api

# Ví dụ khi repository có Gradle Wrapper.
./gradlew test
./gradlew bootRun
~~~

URL và tên repository chỉ để minh họa. Nếu dùng Maven Wrapper, nhóm có thể chạy `./mvnw test`. Khi cần xem ứng dụng web chạy trong workstation, dùng tính năng preview/port forwarding theo cấu hình cho phép.

Workstation dùng để **viết và kiểm tra mã**; Git là nguồn lưu lịch sử; CI/CD chịu trách nhiệm build có thể lặp lại và phát hành bằng danh tính riêng; Cloud Run hoặc GKE chạy workload. Không nên coi workstation của một developer là nơi duy nhất tạo artifact production hoặc giữ bí mật triển khai.

## 10. Chi phí, tự động dừng và phân bổ ngân sách

Chi phí Workstations gồm nhiều phần, không chỉ máy ảo đang chạy:

| Khoản phí | Khi phát sinh | Biện pháp |
|---|---|---|
| VM Compute Engine | Khi workstation chạy | Chọn máy vừa đủ, sử dụng Start/Stop |
| Phí quản lý workstation theo vCPU | Trong thời gian workstation hoạt động | Idle/running timeout và loại VM phù hợp |
| Persistent disk | Có thể tiếp tục tính cả khi workstation Stop | Dung lượng hợp lý; xóa disk không còn dùng |
| Cluster/control plane | Khi cluster tồn tại kể cả lúc mọi workstation đang dừng | Tránh tạo cluster dư thừa |
| Quick start pool | VM giữ sẵn để khởi động nhanh | Đặt pool nhỏ hoặc 0 khi không cần |
| Network, image registry và dịch vụ khác | Tùy hạ tầng phụ trợ | Theo dõi billing theo SKU, project và nhãn |

~~~text
Chi phí tổng (ước lượng)
  = VM compute giờ hoạt động
  + phí quản lý theo vCPU × giờ workstation hoạt động
  + persistent disk
  + phí cluster theo giờ tồn tại
  + quick start pool, network và dịch vụ bổ trợ (nếu có)
~~~

Giả sử 10 developer chỉ dùng workstation trong giờ làm việc: nếu không dừng, mỗi máy có thể chạy cả đêm và cuối tuần. Auto-sleep giảm thời gian máy hoạt động nhưng **không loại bỏ phí persistent disk và cluster**. Nếu cần giảm chi phí hơn, nên rà soát disk còn tồn tại, kích thước VM, các cluster chỉ dùng cho thử nghiệm và số VM trong quick start pool.

Có thể gắn nhãn để phân tích chi phí:

~~~yaml
team: backend
environment: development
service: java-api
cost_center: engineering
~~~

Thiết lập Cloud Billing budgets và alerts; cần nhớ **budget alert không mặc nhiên dừng tài nguyên**. Giá cụ thể phụ thuộc region, máy, SKU và thời điểm, vì vậy dùng biểu phí chính thức để tính trước khi chọn cấu hình.

## 11. Sự cố phổ biến và hướng kiểm tra

| Triệu chứng | Khả năng gây ra lỗi | Kiểm tra |
|---|---|---|
| Developer không thấy configuration | Sai project, region hoặc thiếu IAM | Kiểm tra project/cluster và Creator/Operation Viewer |
| Không tạo được workstation | Thiếu quyền, API chưa bật, quota hoặc cấu hình sai | Kiểm tra lỗi API và quota Compute Engine |
| Start chậm hoặc thất bại | Image lớn, không tải được image, thiếu capacity | Kiểm tra image URI, service account, region/zone |
| Custom image bị từ chối | VM service account thiếu Artifact Registry Reader | Kiểm tra quyền kéo image |
| Không vào được môi trường private | DNS, private endpoint, PSC hoặc đường mạng | Kiểm tra từ mạng người dùng tới gateway |
| Không kết nối được database | Firewall/VPC/DNS hoặc IAM/credential | Kiểm tra từng lớp mạng và xác thực |
| File mất sau khi Stop/Start | Đã lưu bên ngoài persistent directory | Kiểm tra mount path và chính sách lưu trữ |
| IDE ngắt khi build lâu | Idle/running timeout hoặc mất kết nối | Kiểm tra cấu hình timeout và log |
| Đã Stop nhưng vẫn tốn tiền | Disk hoặc cluster vẫn được tính phí | Xem billing theo SKU và tài nguyên còn tồn tại |

Đội vận hành cần quy định ai tạo/xóa workstation, ai bảo trì image, quy trình thu hồi tài nguyên khi nhân viên chuyển nhóm, cách xử lý dữ liệu còn lưu trên persistent disk và cách tăng quota khi nhu cầu tăng.

## 12. Tình huống thiết kế: onboarding 20 backend developer

Một doanh nghiệp phát triển API Java trên Cloud Run. Developer mới mất nhiều thời gian cài JDK/Gradle và cấu hình máy; mỗi người có phiên bản khác nhau. Nhóm phải truy cập database thử nghiệm qua VPC, nhưng không được tiếp cận database production.

Giải pháp đề xuất:

1. Tạo project dev-tools được quản lý bằng IAM và billing.
2. Tạo cluster trong region phù hợp, kết nối VPC nơi có database dev.
3. Xây dựng configuration `java-backend` với image đã kiểm duyệt, JDK, Gradle, Code OSS, persistent home và timeout.
4. Cấp Creator cho Google Group backend theo phạm vi thích hợp; mỗi người tạo workstation cá nhân.
5. Thiết lập service account với quyền dev tối thiểu; CI/CD dùng danh tính riêng để phát hành lên Cloud Run.
6. Quản lý image bằng Git/pipeline, quét lỗi bảo mật, chạy thử bản cập nhật trước khi phát hành.
7. Theo dõi số workstation hoạt động, chi phí cluster/VM/disk, quota và quyền truy cập.

Cách này rút ngắn quá trình thiết lập và giảm chênh lệch công cụ. Tuy nhiên, nhóm vẫn cần review quyền, vận hành network, kiểm soát chi phí và xóa tài nguyên khi developer rời dự án.

**Khi chưa cần Cloud Workstations:** nhóm rất nhỏ chỉ chạy vài lệnh `gcloud` có thể phù hợp Cloud Shell; dự án yêu cầu làm việc ngoại tuyến liên tục có thể ưu tiên môi trường cục bộ; workload cần cấu hình VM đặc biệt có thể chọn VM tự quản. Quyết định phải dựa trên yêu cầu quản trị, bảo mật, mạng và tổng chi phí.

## 13. Checklist và bài tập

- [ ] Project đã bật API, billing, quota và có owner rõ ràng.
- [ ] Region/cluster/VPC/gateway phù hợp với nơi người dùng và dịch vụ đích.
- [ ] Configuration mô tả machine type, image, IDE và persistent directory.
- [ ] Image có quy trình build, pin phiên bản, quét lỗ hổng và cập nhật.
- [ ] IAM Admin, Creator, User và service account được cấp đúng phạm vi.
- [ ] Không lưu secret trong image hoặc code; không dùng quyền production mặc định.
- [ ] Đã kiểm tra Start, Launch, Stop, Start lại và bảo toàn file trong home.
- [ ] Idle timeout, running timeout, quick start pool và reclaim policy đã được quyết định.
- [ ] Có giám sát chi phí, nhãn phân bổ, quy trình thu hồi workstation.

**Bài tập vận dụng:** Hãy thiết kế Cloud Workstations cho 8 backend developer Java và 4 frontend developer. Backend cần kết nối database dev có private IP, frontend chỉ cần chạy và preview web app. Hãy đề xuất số cluster, configuration, VM type, image, persistent disk, IAM, VPC, idle timeout và phương án tối ưu chi phí. Sau đó mô tả đường đi từ code trên workstation qua CI/CD đến Cloud Run mà không cần cấp cho từng developer quyền triển khai production.

## Tài liệu tham khảo chính thức

- [Cloud Workstations overview](https://cloud.google.com/workstations/docs/overview) — khái niệm và vòng đời.
- [Create a workstation cluster](https://cloud.google.com/workstations/docs/create-cluster) — mạng và region.
- [Create a workstation configuration](https://cloud.google.com/workstations/docs/create-configuration) — VM, image, disk, phân quyền.
- [Customize container images](https://cloud.google.com/workstations/docs/customize-container-images) — xây dựng và cập nhật image.
- [Access control with IAM](https://cloud.google.com/workstations/docs/access-control) — phân quyền người dùng.
- [Cloud Workstations pricing](https://cloud.google.com/workstations/pricing) — các thành phần tính phí.
- [gcloud workstations reference](https://cloud.google.com/sdk/gcloud/reference/workstations) — cú pháp lệnh hiện hành.
