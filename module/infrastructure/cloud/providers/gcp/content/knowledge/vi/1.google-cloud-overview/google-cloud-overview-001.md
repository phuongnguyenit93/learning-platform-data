# Google Cloud trong hệ sinh thái điện toán đám mây

> **Chương:** Tổng quan Google Cloud  
> **Phạm vi:** Mô-đun **CLOUD_PROVIDERS_GCP** giới thiệu cách tổ chức tài nguyên Google Cloud, quản lý IAM và VPC, lựa chọn Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; đồng thời kết nối triển khai tự động với vận hành tin cậy và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích điện toán đám mây tạo ra giá trị gì và Google Cloud nằm ở đâu trong hệ sinh thái đó.
2. Phân biệt mô hình IaaS, PaaS, nền tảng container và serverless qua mức độ quản lý hạ tầng.
3. Mô tả quan hệ giữa organization, folder, project, billing account, IAM, region, zone và VPC.
4. Chọn sơ bộ dịch vụ tính toán, lưu trữ, dữ liệu và kết nối phù hợp với một yêu cầu thực tế.
5. Phác thảo một hệ thống có bảo mật, triển khai, giám sát, phục hồi và quản lý chi phí ngay từ thiết kế.

## 1. Điện toán đám mây giải quyết vấn đề gì?

Trong mô hình tự vận hành hạ tầng (on-premises), một tổ chức thường phải mua máy chủ, bố trí trung tâm dữ liệu, cấp điện, thiết lập mạng, bảo trì phần cứng và dự đoán trước nhu cầu năng lực. Nếu lượng truy cập tăng đột ngột, việc mua và lắp đặt thêm máy có thể mất nhiều thời gian; nếu nhu cầu giảm, phần cứng vẫn nằm đó.

**Điện toán đám mây (cloud computing)** cung cấp năng lực xử lý, lưu trữ, mạng và các dịch vụ nền tảng qua giao diện lập trình hoặc bảng điều khiển. Nhóm phát triển có thể cấp phát tài nguyên theo nhu cầu, tự động hóa cấu hình và trả chi phí theo cơ chế của từng dịch vụ. Cloud không mặc nhiên rẻ hơn hay an toàn hơn: hiệu quả phụ thuộc vào cách chọn kiến trúc, phân quyền và vận hành.

Một số giá trị chính:

- **Tốc độ:** tạo môi trường thử nghiệm hoặc triển khai sản phẩm mà không cần chờ mua thiết bị.
- **Co giãn:** tăng, giảm số phiên bản xử lý theo tải, trong giới hạn quota và cấu hình.
- **Phân bố địa lý:** đặt tài nguyên ở khu vực gần người dùng hoặc phục vụ yêu cầu lưu trú dữ liệu.
- **Dịch vụ quản lý sẵn:** sử dụng cơ sở dữ liệu, hàng đợi, giám sát và bảo mật dưới dạng dịch vụ.
- **Tự động hóa:** mô tả hạ tầng và quy trình phát hành bằng mã, giảm thao tác thủ công.

Ví dụ: một sàn thương mại điện tử có 200 lượt truy cập mỗi phút vào ngày thường nhưng tăng nhiều lần trong đợt khuyến mãi. Thay vì thiết kế mọi máy chủ cho mức tải đỉnh quanh năm, nhóm có thể sử dụng một dịch vụ chạy ứng dụng tự co giãn, kết hợp cơ sở dữ liệu có khả năng chịu tải và cơ chế cache. Tuy vậy, cơ sở dữ liệu, giới hạn kết nối, chi phí mạng và các dịch vụ phụ thuộc vẫn cần được thiết kế cho tải cao.

### 1.1. Những mô hình cung cấp dịch vụ

| Mô hình | Bên sử dụng chủ yếu quản lý | Nhà cung cấp chủ yếu quản lý | Ví dụ trong Google Cloud |
|---|---|---|---|
| **IaaS** (Infrastructure as a Service) | Hệ điều hành khách, bản vá, runtime, ứng dụng, dữ liệu | Phần cứng vật lý, lớp ảo hóa, nền tảng hạ tầng | **Compute Engine** |
| **PaaS** (Platform as a Service) | Mã ứng dụng, cấu hình triển khai, dữ liệu và quyền truy cập | Phần lớn runtime và hạ tầng thực thi | **App Engine** |
| **Container orchestration** | Container, workload Kubernetes, chính sách và cấu hình cụm theo chế độ sử dụng | Thành phần hạ tầng hoặc một phần việc quản trị Kubernetes | **Google Kubernetes Engine (GKE)** |
| **Serverless / managed containers** | Ứng dụng hoặc container, cấu hình truy cập, kết nối, dữ liệu | Cấp phát hạ tầng và cơ chế thực thi, co giãn ở mức dịch vụ | **Cloud Run** |
| **SaaS** (Software as a Service) | Người dùng, dữ liệu, cấu hình nghiệp vụ và quyền chia sẻ | Phần lớn ứng dụng và hạ tầng | **Google Workspace** (sản phẩm SaaS thuộc hệ sinh thái Google, không phải dịch vụ triển khai trong Google Cloud) |

Ranh giới trách nhiệm khác nhau theo sản phẩm. Chẳng hạn, GKE có các chế độ quản lý khác nhau; dùng GKE không có nghĩa mọi bản vá, bảo mật workload và cấu hình Kubernetes đều do Google chịu trách nhiệm. Cloud Run bỏ phần lớn công việc quản trị máy chủ nhưng vẫn yêu cầu người phát triển bảo mật mã nguồn, thư viện, định danh và dữ liệu.

### 1.2. Mô hình triển khai: public, private, hybrid và multicloud

- **Public cloud:** tài nguyên được cung cấp qua nền tảng của nhà cung cấp như Google Cloud, Amazon Web Services (AWS) hoặc Microsoft Azure.
- **Private cloud:** môi trường đám mây dành riêng cho một tổ chức, thường do tổ chức hoặc đối tác vận hành.
- **Hybrid cloud:** kết nối và vận hành thống nhất giữa hệ thống tại chỗ và cloud; phù hợp khi phải giữ một phần dữ liệu hoặc ứng dụng trong trung tâm dữ liệu riêng.
- **Multicloud:** dùng dịch vụ từ nhiều nhà cung cấp cloud, thường vì yêu cầu hệ thống, địa lý, năng lực chuyên biệt hoặc chiến lược kinh doanh.

Hybrid và multicloud có thể tăng tính linh hoạt nhưng làm bài toán định danh, mạng, quan sát, chi phí và quản trị phức tạp hơn. Không nên chọn chúng chỉ vì kỳ vọng rằng việc chuyển đổi ứng dụng giữa các nền tảng sẽ hoàn toàn tự động.

## 2. Google Cloud đứng ở đâu trong hệ sinh thái?

**Google Cloud** là danh mục dịch vụ đám mây của Google, bao gồm hạ tầng tính toán, mạng, lưu trữ, dữ liệu, trí tuệ nhân tạo, bảo mật và công cụ phát triển/vận hành. Google Cloud Platform (GCP) là cách gọi phổ biến đối với các dịch vụ nền tảng này. Trong thực tế, người học sẽ thường gặp cả hai cách gọi.

Google Cloud, AWS và Azure cùng cung cấp các năng lực cốt lõi như máy ảo, Kubernetes, cơ sở dữ liệu quản lý, mạng riêng ảo, cân bằng tải, log và hệ thống phân tích. Khác biệt nằm ở cách tổ chức tài nguyên, API, cơ chế cấp quyền, tích hợp dịch vụ, định giá, khu vực hiện diện và trải nghiệm vận hành. Tên dịch vụ tương tự không bảo đảm hành vi hoặc giá thành giống nhau.

| Nhu cầu chung | Google Cloud | Ví dụ dịch vụ tương ứng ở nền tảng khác |
|---|---|---|
| Máy ảo | Compute Engine | AWS EC2; Azure Virtual Machines |
| Kubernetes quản lý | GKE | Amazon EKS; Azure Kubernetes Service |
| Chạy container với ít quản trị máy chủ | Cloud Run | AWS App Runner/Fargate; Azure Container Apps (khác biệt về mô hình và khả năng) |
| Lưu trữ đối tượng | Cloud Storage | Amazon S3; Azure Blob Storage |
| Cơ sở dữ liệu quan hệ quản lý | Cloud SQL | Amazon RDS; Azure SQL Database (khác biệt về engine và tính năng) |
| Kho dữ liệu phân tích | BigQuery | Amazon Redshift; Microsoft Fabric Warehouse |
| Giám sát và log | Cloud Monitoring, Cloud Logging | Amazon CloudWatch; Azure Monitor |

Bảng là **ánh xạ nhu cầu**, không phải cam kết tương đương 1:1. Khi đánh giá nhà cung cấp, hãy so sánh các tiêu chí có thể đo: yêu cầu SLA và vị trí dữ liệu, dịch vụ quản lý sẵn, năng lực của đội ngũ, chi phí tổng thể, đường truyền dữ liệu và độ khó di chuyển.

## 3. Cấu trúc tài nguyên: từ tổ chức đến dự án

Một điểm đặc trưng cần nắm trước khi triển khai Google Cloud là **project**. Dịch vụ thường được tạo và quản lý trong một project; project cũng là nơi gắn API, quota, nhiều chính sách IAM và thông tin phân bổ chi phí.

~~~mermaid
flowchart TD
    O["Organization (nếu có)"] --> F["Folder: nhóm sản phẩm / phòng ban"]
    F --> P1["Project: shop-dev"]
    F --> P2["Project: shop-prod"]
    P2 --> R1["Cloud Run"]
    P2 --> R2["Cloud SQL"]
    P2 --> R3["VPC và tài nguyên mạng"]
    B["Billing account"] -. "Liên kết thanh toán" .-> P1
    B -. "Liên kết thanh toán" .-> P2
~~~

- **Organization:** nút gốc về mặt tổ chức và quản trị, thường gắn với miền danh tính của doanh nghiệp; tài khoản cá nhân có thể tạo project mà không có organization.
- **Folder:** nhóm project và folder con theo phòng ban, môi trường hoặc phạm vi quản trị; folder chỉ tồn tại dưới organization.
- **Project:** đơn vị triển khai và quản lý nhiều tài nguyên, chứa định danh project, cấu hình API, quota, ranh giới quản trị và thông tin tính phí.
- **Resource:** các đối tượng như máy ảo, bucket, database, service hoặc mạng.
- **Billing account:** thực thể thanh toán được liên kết với project; không phải nút cha của project trong cây tài nguyên.

Ví dụ nên tách **shop-dev**, **shop-staging** và **shop-prod** để dễ kiểm soát quyền, quota, ngân sách và vòng đời triển khai. Đây là một cách tổ chức hữu ích, không phải quy tắc bắt buộc cho mọi hệ thống.

### 3.1. Identity and Access Management (IAM)

IAM trả lời ba câu hỏi: **Ai** (principal) được phép **làm gì** (permission/role) trên **tài nguyên nào** (scope)? Principal có thể là người dùng, nhóm hoặc service account. Quyền thường được gom trong role; policy binding gắn principal với role tại một phạm vi tài nguyên.

Ví dụ:

| Chủ thể | Phạm vi | Quyền dự kiến |
|---|---|---|
| Nhóm phát triển | Project phát triển | Quyền triển khai và xem log phù hợp công việc |
| Pipeline phát hành | Dịch vụ cần triển khai ở production | Quyền triển khai giới hạn, gắn với danh tính của pipeline |
| Ứng dụng Cloud Run | Bucket lưu hóa đơn | Chỉ quyền đọc/ghi đúng dữ liệu cần thiết |
| Nhóm kiểm toán | Project production | Quyền xem cấu hình và audit log theo nhiệm vụ |

Quyền trên organization hoặc folder có thể được kế thừa xuống các project và tài nguyên con. Vì vậy, một binding có phạm vi quá rộng có thể ảnh hưởng tới nhiều môi trường. Nên ưu tiên **role định nghĩa sẵn với quyền vừa đủ**, cấp quyền cho nhóm khi phù hợp, rà soát định kỳ và tránh gán Owner/Editor cho ứng dụng. Service account là danh tính của workload, không phải mật khẩu dùng chung; ưu tiên cơ chế danh tính ngắn hạn thay vì tạo và phát tán khóa service account dài hạn.

### 3.2. API, quota và chính sách tổ chức

Một số dịch vụ cần **bật API** trong project trước khi sử dụng. Quota giới hạn số lượng tài nguyên hoặc tốc độ yêu cầu và có thể khác theo dịch vụ, project, khu vực. Việc có quyền IAM không đồng nghĩa project còn quota hoặc đã có quyền sử dụng API tương ứng.

**Organization Policy** giúp áp đặt ràng buộc quản trị như giới hạn vị trí tài nguyên hoặc các kiểu cấu hình được phép. Chính sách cấp tổ chức có thể khiến một thao tác bị từ chối dù người thực hiện có role IAM thích hợp. Đây là hành vi mong muốn trong một môi trường có quản trị tập trung.

## 4. Region, zone và mạng: dữ liệu nằm ở đâu, đi bằng đường nào?

Google Cloud có hạ tầng tại nhiều vị trí địa lý. **Region** là một khu vực địa lý; **zone** là một miền triển khai trong region. Một số tài nguyên có phạm vi **global**, một số **regional**, và một số **zonal**. Phạm vi chính xác tùy dịch vụ.

- **Compute Engine VM** thường được tạo trong một zone; có thể tổ chức nhiều VM ở các zone khác nhau để giảm rủi ro lỗi một zone.
- **Cloud Run service** được triển khai tại region được chọn; nền tảng quản lý hạ tầng chạy dịch vụ, nhưng kiến trúc đa region vẫn cần thiết nếu yêu cầu chịu được lỗi toàn region.
- **VPC network** là tài nguyên có phạm vi global của Google Cloud, còn **subnet** là tài nguyên regional.
- **Cloud Storage bucket** hỗ trợ các lựa chọn vị trí như region, dual-region hoặc multi-region tùy cấu hình; vị trí bucket là một quyết định lưu trú dữ liệu và chi phí.

Không có một region tối ưu cho mọi dự án. Cần đánh giá độ trễ tới người dùng, quy định lưu trú dữ liệu, khả dụng của dịch vụ/loại tài nguyên, phương án khôi phục và chi phí truyền dữ liệu. Các region hay zone không được suy từ tên dự án; hãy kiểm tra danh mục dịch vụ hỗ trợ khi triển khai.

### 4.1. Các thành phần mạng thường gặp

| Thành phần | Vai trò | Điều cần lưu ý |
|---|---|---|
| **VPC** | Không gian mạng logic để kết nối các tài nguyên hỗ trợ VPC | Thiết kế dải IP, phân đoạn và quyền quản trị mạng |
| **Subnet** | Dải địa chỉ IP ở cấp region | Tránh chồng lấn dải địa chỉ khi kết nối on-premises |
| **Firewall rules / policies** | Kiểm soát lưu lượng theo hướng, đích và điều kiện được hỗ trợ | Chỉ mở cổng, nguồn và đích thực sự cần thiết |
| **Cloud Load Balancing** | Phân phối lưu lượng đến các backend | Lựa chọn loại load balancer phù hợp giao thức, phạm vi và backend |
| **Cloud DNS** | Quản lý phân giải tên miền | Phân biệt public zone và private zone |
| **Cloud NAT** | Cấp khả năng kết nối ra ngoài cho các tài nguyên được hỗ trợ mà không cần IP công khai trực tiếp | Không tự động làm cho tài nguyên có thể nhận kết nối vào từ Internet |
| **Cloud VPN / Cloud Interconnect** | Kết nối mạng riêng với trung tâm dữ liệu hoặc mạng ngoài | Quan tâm băng thông, dự phòng, định tuyến và mã hóa |

Một lỗi phổ biến là nghĩ rằng tạo VPC sẽ khiến mọi dịch vụ tự động có thể truy cập riêng tư tới nhau. Trên thực tế, cần cấu hình phù hợp với loại dịch vụ, đường đi mạng, firewall, danh tính và phương thức kết nối. Chẳng hạn, khi Cloud Run truy cập Cloud SQL qua địa chỉ riêng, phải tính tới kết nối VPC được hỗ trợ, cấu hình database và phân quyền liên quan.

## 5. Bản đồ dịch vụ Google Cloud theo nhu cầu

### 5.1. Tính toán và thực thi ứng dụng

| Dịch vụ | Phù hợp khi | Đổi lại cần cân nhắc |
|---|---|---|
| **Compute Engine** | Cần kiểm soát hệ điều hành, phần mềm đặc thù, máy ảo hoặc cách triển khai hiện hữu | Phải tự quản nhiều phần của OS, bản vá, lịch cập nhật và năng lực máy |
| **GKE** | Có nhiều dịch vụ container, yêu cầu điều phối Kubernetes, chính sách và hệ sinh thái K8s | Cần năng lực vận hành Kubernetes; độ phức tạp cao hơn ứng dụng đơn giản |
| **Cloud Run** | API HTTP, ứng dụng web, worker/container theo sự kiện, tải thay đổi | Mô hình stateless là lựa chọn tự nhiên; cần thiết kế riêng cho trạng thái, kết nối, timeout và cold start |
| **App Engine** | Muốn triển khai ứng dụng trong môi trường PaaS với mô hình runtime mà dịch vụ hỗ trợ | Bị ràng buộc bởi môi trường, cấu hình và các khả năng của nền tảng |
| **Batch** | Công việc xử lý theo lô, có thể xếp lịch/chạy khi cần | Cần quản lý thời điểm chạy, dữ liệu đầu vào/đầu ra và tài nguyên tính toán |

**Cách suy nghĩ:** bắt đầu từ đặc điểm workload thay vì bắt đầu từ tên sản phẩm. Nếu một nhóm nhỏ có một API container không trạng thái, Cloud Run có thể giảm đáng kể công việc vận hành. Nếu cần phần mềm cũ phụ thuộc OS hoặc driver đặc biệt, Compute Engine có thể dễ chuyển đổi hơn. Nếu nhiều nhóm cần Kubernetes và các thành phần điều phối phức tạp, GKE đáng cân nhắc.

### 5.2. Lưu trữ, cơ sở dữ liệu và phân tích

| Nhu cầu | Dịch vụ thường khảo sát | Câu hỏi quyết định |
|---|---|---|
| Ảnh, video, tài liệu, bản sao lưu dạng đối tượng | **Cloud Storage** | Vị trí lưu, lớp lưu trữ, vòng đời đối tượng, quyền truy cập, tần suất đọc |
| Ổ đĩa cho máy ảo | **Persistent Disk / Hyperdisk** theo loại được hỗ trợ | IOPS, throughput, độ trễ, kích thước, phạm vi và chi phí |
| Hệ thống file dùng chung | **Filestore** | Cần giao thức file/NFS, hiệu năng và mô hình truy cập nào? |
| SQL giao dịch truyền thống | **Cloud SQL** | Engine hỗ trợ, kết nối, HA, backup, số lượng kết nối, quy mô |
| Cơ sở dữ liệu quan hệ phân tán quy mô lớn | **Spanner** | Cần độ nhất quán giao dịch và mở rộng theo mô hình phân tán hay không? |
| Dữ liệu tài liệu / ứng dụng tương tác | **Firestore** | Kiểu truy vấn, mô hình document, index và số lần đọc/ghi |
| Dữ liệu khóa rộng, truy cập tốc độ cao ở quy mô lớn | **Bigtable** | Thiết kế row key và mẫu truy vấn có phù hợp không? |
| Phân tích dữ liệu quy mô lớn bằng SQL | **BigQuery** | Workload phân tích, mức quét dữ liệu, partition, clustering, chi phí truy vấn |
| Cache dữ liệu truy cập thường xuyên | **Memorystore** | TTL, invalidation, giới hạn bộ nhớ và lỗi cache |

**Không nhầm BigQuery với cơ sở dữ liệu giao dịch của website.** BigQuery tối ưu cho phân tích tập dữ liệu và truy vấn tổng hợp, còn luồng tạo đơn hàng trực tuyến thường cần một cơ sở dữ liệu giao dịch như Cloud SQL hoặc một lựa chọn OLTP khác.

### 5.3. Tích hợp, phát hành và vận hành

- **Pub/Sub:** truyền sự kiện bất đồng bộ giữa bên phát và bên nhận; các consumer cần xử lý lặp và lỗi một cách an toàn.
- **Cloud Tasks / Cloud Scheduler:** xếp hàng công việc có mục tiêu hoặc kích hoạt theo lịch, tùy kiểu bài toán.
- **Dataflow:** xử lý luồng và theo lô cho pipeline dữ liệu; **BigQuery** lưu và truy vấn dữ liệu phân tích.
- **Artifact Registry:** lưu trữ image/container và artifact phục vụ phát hành.
- **Cloud Build, Cloud Deploy:** tự động hóa build và hoạt động đưa phiên bản qua các môi trường theo khả năng của từng công cụ.
- **Cloud Logging, Cloud Monitoring, Cloud Trace:** thu thập log, số liệu, cảnh báo và dấu vết phân tán để chẩn đoán.
- **Secret Manager, Cloud KMS:** quản lý bí mật và khóa mã hóa theo mục đích sử dụng.

Một ứng dụng production hầu như không chỉ có một dịch vụ compute: nó thường cần quản trị định danh, mạng, dữ liệu, phân phối thay đổi, đo lường và phục hồi sự cố.

## 6. Trách nhiệm bảo mật được chia như thế nào?

Google bảo vệ cơ sở hạ tầng mà họ vận hành; khách hàng vẫn chịu trách nhiệm cho **cách cấu hình và sử dụng** tài nguyên, danh tính, ứng dụng và dữ liệu. Phạm vi cụ thể phụ thuộc dịch vụ.

| Lớp bảo vệ | Compute Engine | Cloud Run |
|---|---|---|
| Bảo trì phần cứng vật lý | Nhà cung cấp | Nhà cung cấp |
| Hệ điều hành và runtime thực thi | Khách hàng chịu nhiều trách nhiệm hơn | Phần hạ tầng/runtime do nền tảng quản lý nhiều hơn, tùy mô hình triển khai |
| Lỗ hổng mã ứng dụng và dependency | Khách hàng | Khách hàng |
| IAM, service account, dữ liệu và secret | Khách hàng cấu hình và quản trị | Khách hàng cấu hình và quản trị |
| Quy tắc truy cập mạng, kiểm soát đầu vào API | Khách hàng | Khách hàng |
| Sao lưu, khôi phục và khả năng chịu lỗi nghiệp vụ | Khách hàng thiết kế | Khách hàng thiết kế |

Các thực hành tối thiểu cho bài toán cloud:

1. **Ít quyền nhất:** quyền của người vận hành, pipeline và ứng dụng phải phục vụ đúng tác vụ.
2. **Danh tính workload:** sử dụng service account/danh tính được quản lý, ưu tiên token ngắn hạn và Workload Identity Federation nếu tích hợp hệ thống bên ngoài.
3. **Quản lý secret:** không đưa mật khẩu, khóa API và thông tin nhạy cảm vào mã nguồn, image hoặc log.
4. **Giới hạn truy cập mạng:** chỉ mở giao diện công khai cần thiết; kiểm soát inbound, outbound và kết nối tới database.
5. **Mã hóa và quản trị dữ liệu:** xem xét yêu cầu mã hóa, nơi lưu dữ liệu, thời gian lưu, phân loại dữ liệu và quyền truy cập.
6. **Audit và phát hiện bất thường:** bật/giữ các loại audit log cần thiết, theo dõi thay đổi quyền và cấu hình quan trọng.
7. **Kiểm thử phục hồi:** backup chỉ có giá trị khi có thể khôi phục và biết thời gian phục hồi thực tế.

Ví dụ: một ứng dụng Cloud Run cần ghi hóa đơn vào bucket không nên dùng tài khoản có quyền Owner trên toàn project. Nó nên chạy bằng service account riêng, chỉ có quyền tối thiểu trên bucket đích, và lấy thông tin kết nối database từ cơ chế quản lý secret phù hợp.

## 7. Kiến trúc minh họa: website đặt hàng nhỏ

Giả sử một nhóm xây dựng website đặt hàng: khách tải giao diện qua HTTPS, tạo đơn hàng, tải ảnh sản phẩm và nhận email xác nhận. Yêu cầu: dễ mở rộng khi tải tăng, có khả năng truy vết lỗi và tránh quản lý máy chủ nếu chưa cần.

~~~mermaid
flowchart LR
    U["Người dùng"] --> LB["HTTPS Load Balancer"]
    LB --> APP["Cloud Run: API"]
    APP --> DB[("Cloud SQL: đơn hàng")]
    APP --> OBJ[("Cloud Storage: ảnh")]
    APP --> Q["Pub/Sub: sự kiện đặt hàng"]
    Q --> WORKER["Cloud Run: xử lý sự kiện"]
    APP -. "Lấy bí mật" .-> SEC["Secret Manager"]
    APP -. "Log / metrics" .-> OBS["Cloud Logging / Monitoring"]
    WORKER -. "Log / metrics" .-> OBS
~~~

Luồng xử lý:

1. Người dùng gọi API qua HTTPS; load balancer định tuyến tới backend Cloud Run đã cấu hình.
2. API xác thực yêu cầu, kiểm tra quyền và ghi giao dịch vào Cloud SQL.
3. Hình ảnh được lưu trong Cloud Storage, với cơ chế cấp quyền và phân phối phù hợp.
4. Khi đơn hàng được tạo thành công, hệ thống phát sự kiện lên Pub/Sub để xử lý công việc không cần chặn phản hồi HTTP.
5. Worker được cấu hình nhận sự kiện, xử lý gửi thông báo; khi nhận lại cùng một thông điệp vẫn phải tránh gửi/ghi trùng.
6. Log, metric và alert hỗ trợ phát hiện tăng lỗi, độ trễ hoặc bất thường về tỷ lệ yêu cầu thành công.

Đây là **sơ đồ logic**, không hàm ý các kết nối đều hoạt động mặc định. Khi hiện thực cần cấu hình xác thực giữa các dịch vụ, kết nối riêng tới Cloud SQL nếu dùng private IP, cách cấp URL ảnh, chính sách retry/dead-letter, chứng chỉ HTTPS và tùy chọn backend của load balancer. Không nhất thiết phải dùng load balancer riêng: Cloud Run cũng có endpoint HTTPS do nền tảng cung cấp; chọn phương án theo yêu cầu hostname, điều hướng, chính sách bảo vệ và hệ thống hiện có.

### Các quyết định cần ghi lại trước khi triển khai

| Câu hỏi | Lựa chọn ban đầu trong ví dụ | Cần kiểm chứng |
|---|---|---|
| Môi trường nào? | Project riêng cho dev và prod | Quyền IAM, quota, billing, chính sách tổ chức |
| Nơi triển khai? | Một region gần nhóm người dùng chính | Độ trễ, cư trú dữ liệu, dịch vụ sẵn có, vùng dự phòng |
| Backend chạy ở đâu? | Cloud Run | Độ trễ khởi động, CPU/bộ nhớ, concurrency, kết nối |
| Đơn hàng lưu ở đâu? | Cloud SQL | Khả năng HA, backup, connection pooling, giới hạn giao dịch |
| Ảnh lưu ở đâu? | Cloud Storage | Truy cập công khai hay ký URL, vòng đời, chi phí egress |
| Xử lý email? | Pub/Sub + worker | Idempotency, retry, thời gian xử lý, giám sát thông điệp lỗi |
| Phát hành? | CI/CD, image trong Artifact Registry | Quyền pipeline, quét lỗ hổng, triển khai từng môi trường |
| Độ tin cậy? | Alert theo lỗi và độ trễ; quy trình restore | SLO, RTO, RPO, phương án chịu lỗi region |

## 8. Chọn dịch vụ từ yêu cầu, không từ độ nổi tiếng

Trước khi quyết định, xác định các thuộc tính sau:

- **Loại tải:** HTTP, gRPC, batch, stream, long-running, stateful hay stateless?
- **Quy mô:** lưu lượng trung bình/đỉnh, giới hạn latency, số lượng kết nối, kích thước dữ liệu?
- **Độ tin cậy:** mục tiêu sẵn sàng, thời gian gián đoạn chấp nhận được (RTO), mức mất dữ liệu tối đa (RPO)?
- **An ninh và tuân thủ:** ai truy cập, dữ liệu nằm ở đâu, có yêu cầu mạng riêng, kiểm toán hay mã hóa đặc biệt?
- **Năng lực vận hành:** đội ngũ có kinh nghiệm máy ảo/Kubernetes hay muốn giảm quản trị?
- **Chi phí tổng:** compute, database, lưu trữ, mạng ra, log, license, thời gian vận hành và dự phòng?

Một số tình huống:

**Tình huống A — API mới, nhỏ, tải biến động:** cân nhắc Cloud Run + Cloud SQL/Firestore tùy dữ liệu. Sự đơn giản của triển khai không thay thế việc thiết kế database và kiểm soát cold start.

**Tình huống B — phần mềm nội bộ cũ phụ thuộc hệ điều hành:** Compute Engine thường là bước di chuyển thực tế. Khi hệ thống ổn định, có thể đánh giá tách chức năng và hiện đại hóa từng phần.

**Tình huống C — nhiều microservice đã chuẩn hóa trên Kubernetes:** GKE có lợi nếu cần khả năng điều phối và quản trị thống nhất. Đánh đổi là độ phức tạp, nâng cấp cụm và vận hành workload.

**Tình huống D — phân tích clickstream và báo cáo:** Pub/Sub hoặc cơ chế ingest phù hợp → Dataflow (khi cần xử lý) → BigQuery. Phân biệt pipeline phân tích với database giao dịch phục vụ API.

**Tình huống E — kết nối trung tâm dữ liệu doanh nghiệp:** cần lập kế hoạch IP, định tuyến, IAM và đường kết nối Cloud VPN/Interconnect trước khi di chuyển dữ liệu. Mạng hybrid có thể trở thành điểm nghẽn nếu chỉ quan tâm máy chủ đích.

## 9. Triển khai, theo dõi độ tin cậy và chi phí

### 9.1. Vòng đời từ mã nguồn đến production

~~~mermaid
flowchart LR
    C["Commit + review"] --> T["Test + build"]
    T --> A["Artifact Registry"]
    A --> D["Deploy vào dev/staging"]
    D --> G["Kiểm tra và phê duyệt"]
    G --> P["Triển khai production"]
    P --> O["Metrics, logs, traces"]
    O --> R["Điều chỉnh / rollback"]
~~~

Ở mỗi bước, xác định danh tính nào được phép hành động, lưu artifact nào đã triển khai và cách quay lại phiên bản ổn định. Hạ tầng nên được mô tả bằng công cụ quản lý cấu hình/hạ tầng dưới dạng mã phù hợp với đội ngũ, có review và quản lý thay đổi. Không nên để môi trường production chỉ tồn tại dưới dạng các thao tác thủ công không ghi nhận.

### 9.2. Đo độ tin cậy bằng tín hiệu nghiệp vụ

Một hệ thống đang chạy chưa chắc đang phục vụ người dùng tốt. Các chỉ số nền tảng cần liên hệ với mục tiêu dịch vụ:

- **Availability / error rate:** tỷ lệ yêu cầu thành công và loại lỗi nào ảnh hưởng người dùng.
- **Latency:** độ trễ p50/p95/p99 thay vì chỉ dùng số trung bình.
- **Traffic:** request/giây, công việc trong hàng đợi, lượng dữ liệu vào/ra.
- **Saturation:** CPU, memory, số kết nối database, giới hạn concurrency hoặc quota.
- **Business signals:** tỷ lệ đặt hàng thành công, thời gian xử lý đơn, tỷ lệ xử lý thông báo thất bại.

Ví dụ đặt mục tiêu nội bộ: “99,9% yêu cầu tạo đơn hợp lệ thành công trong một khoảng đo đã xác định”, sau đó định nghĩa rõ yêu cầu hợp lệ, thời gian quan sát, cách tính và điều kiện loại trừ. Dùng mục tiêu đó để đặt cảnh báo, xây dựng runbook và xác định ngân sách lỗi (error budget) nếu phù hợp. Chỉ số mục tiêu nội bộ này không phải SLA mặc định của Google Cloud.

### 9.3. Chi phí vận hành không chỉ là giá máy

Chi phí có thể đến từ thời gian CPU/bộ nhớ sử dụng, instance luôn bật, lưu trữ, số lần thao tác với dữ liệu, truy vấn, log và **truyền dữ liệu ra ngoài hoặc giữa một số vị trí/dịch vụ**. Chi phí thay đổi theo cấu hình, vị trí, mức sử dụng và bảng giá hiện hành; không nên dùng một con số cố định cho mọi dự án.

Thực hành hữu ích:

1. Gắn **billing account** chính xác và phân chia project theo môi trường hoặc sản phẩm khi có lợi cho quản trị.
2. Thiết lập **budget và alert** từ đầu; cảnh báo ngân sách không mặc nhiên giới hạn hoặc dừng chi tiêu.
3. Gắn **label** cho tài nguyên hỗ trợ label để phân bổ chi phí theo đội/nghiệp vụ; xem báo cáo chi tiết khi cần.
4. Chọn kích thước và chính sách co giãn theo số liệu thực, tắt tài nguyên thử nghiệm không còn dùng.
5. Thiết lập vòng đời dữ liệu và thời hạn giữ log phù hợp; rà soát egress và các truy vấn phân tích tốn kém.
6. Xem xét chi phí dự phòng, backup và phục hồi như một phần của chi phí sở hữu hệ thống.

**Cân bằng quan trọng:** cấu hình quá tiết kiệm có thể làm hệ thống lỗi khi tăng tải; cấu hình dư thừa quá mức lại gây lãng phí. Quyết định cần dựa trên mục tiêu dịch vụ và kết quả quan sát.

## 10. Thực hành khám phá project bằng Google Cloud CLI

Bài thực hành dưới đây tập trung vào **lệnh đọc** để người học hiểu cấu trúc project trước khi triển khai tài nguyên có tính phí. Cần cài **gcloud CLI**, đăng nhập tài khoản được cấp quyền và biết project ID của môi trường thực hành.

~~~bash
# Xác nhận tài khoản, project đang dùng
gcloud auth list
gcloud config list

# Xem thông tin project, không thay đổi tài nguyên
gcloud projects describe YOUR_PROJECT_ID

# Liệt kê API đã bật trong project
gcloud services list --enabled --project=YOUR_PROJECT_ID

# Xem các mạng VPC đã cấu hình
gcloud compute networks list --project=YOUR_PROJECT_ID

# Xem subnet và region tương ứng
gcloud compute networks subnets list --project=YOUR_PROJECT_ID

# Xem dịch vụ Cloud Run ở một region đã chọn
gcloud run services list --region=YOUR_REGION --project=YOUR_PROJECT_ID
~~~

Thay **YOUR_PROJECT_ID** và **YOUR_REGION** bằng giá trị được cấp. Một số lệnh liệt kê có thể yêu cầu API tương ứng đã bật và quyền xem tài nguyên. Nếu không có project được cấp, hãy dừng ở phần khái niệm hoặc dùng project thực hành đã được người quản trị chuẩn bị; không cần tạo tài nguyên có phí chỉ để hoàn thành bài.

Khi quan sát kết quả, tự trả lời:

- Một project có bao nhiêu VPC? Mỗi subnet thuộc region nào?
- Những API nào đã bật? Dịch vụ nào có thể chưa được kích hoạt?
- Tài khoản đang sử dụng có thể xem project nhưng không thể xem tài nguyên cụ thể không? Điều đó phản ánh điều gì về IAM?
- Một Cloud Run service có hiển thị ở mọi region khi dùng lệnh liệt kê theo region không?

### Ví dụ phát hành có kiểm soát (tham khảo, không bắt buộc thực hiện)

Giả sử repo đã có ứng dụng được Cloud Run source deployment hỗ trợ, project có billing, các API liên quan đã được bật và danh tính triển khai có đủ quyền. Một bước phát hành có thể trông như sau:

~~~bash
# Thực hiện trong thư mục mã nguồn ứng dụng.
# Lệnh này có thể tạo tài nguyên tính phí: chỉ chạy ở project được phép.
gcloud run deploy demo-api \
  --source . \
  --region=YOUR_REGION \
  --project=YOUR_PROJECT_ID \
  --no-allow-unauthenticated
~~~

Cờ **--no-allow-unauthenticated** yêu cầu truy cập có xác thực thay vì mở dịch vụ công khai. Lệnh triển khai từ nguồn có thể sử dụng các dịch vụ build và lưu artifact của Google Cloud; cấu hình quyền của người triển khai và service account runtime cũng cần được kiểm tra. Khi tạo ứng dụng thật, phải quyết định rõ cách kiểm thử endpoint, quản lý phiên bản, rollback, secret, mạng riêng và quyền gọi service.

## 11. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Serverless nghĩa là không có máy chủ.” | Máy chủ vẫn tồn tại, nhưng nhà cung cấp chịu trách nhiệm quản lý một phần lớn hạ tầng thực thi. |
| “Đưa ứng dụng lên cloud là tự có high availability.” | Cần cấu hình phù hợp, thiết kế dự phòng, kiểm thử sao lưu/khôi phục và loại bỏ điểm lỗi đơn. |
| “Có quyền Owner thì mọi thao tác đều chạy được.” | API, quota, chính sách tổ chức, điều kiện dịch vụ và các quyền liên quan vẫn có thể chặn thao tác. |
| “VPC là global nên mọi subnet cũng global.” | VPC có phạm vi global, subnet có phạm vi regional. |
| “Dùng Cloud Run thì không cần quan tâm đến bảo mật.” | IAM, mã ứng dụng, secret, dữ liệu và cấu hình truy cập vẫn thuộc trách nhiệm của đội ứng dụng. |
| “BigQuery thay thế mọi hệ quản trị SQL.” | BigQuery hướng tới phân tích, không thay cho thiết kế OLTP phù hợp. |
| “Đã tạo budget thì chắc chắn không vượt ngân sách.” | Budget alert là công cụ quan sát/cảnh báo, không tự động là trần chi phí cứng. |
| “Dùng nhiều cloud luôn tránh được phụ thuộc nhà cung cấp.” | Multicloud cũng tạo thêm phụ thuộc vào công cụ tích hợp, năng lực vận hành và khả năng di chuyển dữ liệu. |

## 12. Kết nối với lộ trình học tiếp theo

Bức tranh tổng quan giúp sắp xếp các kỹ năng theo thứ tự hợp lý: trước hết là **tổ chức project, IAM và billing** để kiểm soát phạm vi; tiếp theo là **VPC, region/zone và kết nối**; sau đó chọn **Compute Engine, GKE hoặc Cloud Run** theo workload, kết hợp **Cloud Storage và cơ sở dữ liệu** theo mô hình dữ liệu. Cuối cùng, cần luyện **tự động hóa phát hành, bảo mật, monitoring, backup, tối ưu chi phí và phản ứng sự cố**.

Khi gặp một bài toán mới, hãy bắt đầu bằng việc mô tả luồng dữ liệu, yêu cầu nghiệp vụ, rủi ro và những việc đội ngũ có khả năng vận hành. Từ đó mới quyết định sử dụng dịch vụ Google Cloud nào. Tư duy này giúp triển khai được hệ thống có thể kiểm chứng, mở rộng, bảo vệ và duy trì lâu dài trong hệ sinh thái điện toán đám mây.
