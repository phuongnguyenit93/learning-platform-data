# Cách đọc tài liệu, kiến trúc tham chiếu và danh mục dịch vụ GCP

> **Chương:** Tổng quan Google Cloud  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Google Cloud có nhiều sản phẩm và nhiều loại tài liệu: hướng dẫn bắt đầu, tài liệu cấu hình, tham chiếu API, kiến trúc mẫu, khuyến nghị vận hành và bảng giá. Khi bắt đầu, khó khăn thường không nằm ở việc tìm một dịch vụ có thể chạy ứng dụng, mà ở việc **tìm đúng nguồn thông tin, đọc được các điều kiện áp dụng và so sánh các phương án thiết kế**.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học sẽ tìm hiểu cách tổ chức organization, project, IAM và VPC; lựa chọn Compute Engine, Google Kubernetes Engine (GKE), Cloud Run, lưu trữ và cơ sở dữ liệu; sau đó triển khai, bảo vệ, tự động hóa phát hành, quan sát độ tin cậy và kiểm soát chi phí. Bài học này cung cấp bản đồ tra cứu để sử dụng xuyên suốt các chủ đề đó.

Sau khi học, bạn có thể:

- Chọn đúng loại tài liệu Google Cloud theo câu hỏi đang cần giải quyết.
- Đọc một kiến trúc tham chiếu, nhận ra luồng dữ liệu, ranh giới bảo mật, điểm lỗi và các giả định thiết kế.
- Phân nhóm dịch vụ GCP theo nhu cầu và giải thích được vì sao chọn hoặc loại một phương án.
- Lập một hồ sơ quyết định kiến trúc có dẫn nguồn, điều kiện kiểm chứng và phương án thay thế.

## 1. Bản đồ nguồn tài liệu chính thức

Không có một trang duy nhất trả lời mọi câu hỏi. Cần phân biệt **trang giới thiệu sản phẩm** với **tài liệu kỹ thuật cụ thể** và **kiến trúc tham chiếu**.

| Nguồn | Đọc khi nào? | Thứ cần tìm |
| --- | --- | --- |
| [Google Cloud Documentation](https://docs.cloud.google.com/docs) | Bắt đầu tìm hiểu hoặc tra cứu theo dịch vụ | Overview, khái niệm, hướng dẫn, điều kiện tiên quyết, troubleshooting |
| [Get started with Google Cloud](https://docs.cloud.google.com/docs/get-started) | Chưa có môi trường hoặc chưa quen công cụ | Cách thiết lập tổ chức, project, xác thực, công cụ dòng lệnh |
| [Danh mục sản phẩm](https://cloud.google.com/products) và [Products at a glance](https://docs.cloud.google.com/docs/product-list) | Muốn biết Google Cloud có dịch vụ nào cho một nhu cầu | Tên sản phẩm hiện hành, mục đích chính, nhóm chức năng |
| [Cloud Architecture Center](https://docs.cloud.google.com/architecture) | Đang thiết kế, đánh giá hoặc di chuyển hệ thống | Kiến trúc tham chiếu, lựa chọn topology, hướng dẫn thiết kế |
| [Well-Architected Framework](https://docs.cloud.google.com/architecture/framework) | Cần rà soát chất lượng thiết kế | Vận hành, bảo mật, độ tin cậy, chi phí, hiệu năng, bền vững |
| Hướng dẫn quản trị của từng dịch vụ | Muốn triển khai và vận hành thực tế | IAM, mạng, cấu hình, giới hạn, backup, monitoring |
| API/CLI reference và code samples | Cần tích hợp ứng dụng hoặc tự động hóa | Tham số, kiểu dữ liệu, phiên bản API, phản hồi và mã lỗi |
| Pricing, quotas, locations, release notes, SLA | Chuẩn bị triển khai production hoặc đánh giá thay đổi | Đơn giá, giới hạn, khu vực hỗ trợ, thay đổi tính năng, cam kết dịch vụ |

**Nguyên tắc chọn nguồn:** Trang sản phẩm giải thích dịch vụ *dùng để làm gì*; overview giải thích *cách dịch vụ vận hành*; guide chỉ *cách thực hiện*; API reference xác định *cú pháp chính xác*; tài liệu kiến trúc giải thích *khi nào và vì sao nên kết hợp các dịch vụ*. Khi các trang có độ khái quát khác nhau, hãy dùng tài liệu kỹ thuật và điều kiện cụ thể của dịch vụ để quyết định triển khai.

### 1.1. Tìm tài liệu bằng câu hỏi, không chỉ bằng tên sản phẩm

Ví dụ, với yêu cầu “API xử lý giao dịch, ít người vận hành, lúc cao điểm tăng tải”, nên chia thành các câu hỏi:

1. **Compute:** Cần máy ảo, nền tảng container có Kubernetes hay dịch vụ chạy ứng dụng được quản lý? Xem [Choose a compute option](https://docs.cloud.google.com/docs/compute-area/choose-compute-options).
2. **Dữ liệu:** Giao dịch cần SQL và tính nhất quán ở mức nào? Xem tổng quan Cloud SQL, AlloyDB hoặc Spanner trước khi so sánh tính năng.
3. **Kết nối:** Ứng dụng cần public HTTPS, truy cập private hay tích hợp hệ thống nội bộ?
4. **Bảo mật:** Ai có thể gọi API? Ứng dụng sử dụng danh tính nào để truy cập cơ sở dữ liệu và Secret Manager?
5. **Vận hành và chi phí:** Có giới hạn đồng thời, hạn ngạch, điểm lỗi, cảnh báo, cơ chế dự phòng hoặc chi phí duy trì nào?

Câu hỏi đúng sẽ dẫn đến đúng trang hơn so với việc chỉ tìm “best Google Cloud service”.

### 1.2. Quy trình đọc một bộ tài liệu sản phẩm

Đối với mỗi dịch vụ mới, hãy đọc theo thứ tự:

1. **Overview và concepts:** hiểu tài nguyên chính, mô hình quản lý, phạm vi toàn cầu/vùng/zone.
2. **When to use / use cases:** xác định trường hợp phù hợp và các giới hạn thiết kế.
3. **Before you begin / quickstart:** ghi nhận API cần bật, project, billing, vai trò IAM và công cụ.
4. **How-to guides:** kiểm tra các cấu hình liên quan đến mạng, danh tính, dữ liệu, triển khai.
5. **Security và operations:** kiểm tra quyền tối thiểu, sao lưu, quan sát, xử lý lỗi, nâng cấp.
6. **Quotas, pricing, SLA, release notes:** kiểm tra khả năng mở rộng, chi phí, tính khả dụng theo khu vực và tính năng mới.
7. **API/CLI reference:** chỉ khi cần triển khai tự động hoặc cần biết chính xác tham số.

Đọc phần cảnh báo trong tài liệu: tính năng **Preview** có thể có điều kiện vận hành khác tính năng được hỗ trợ chính thức; ví dụ trong quickstart thường ưu tiên chạy được nhanh, chưa đủ các yêu cầu bảo mật và vận hành production.

### 1.3. Ghi lại điều kiện áp dụng và độ mới của tài liệu

Một lựa chọn kiến trúc có thể đúng ở vùng triển khai này nhưng không phù hợp tại vùng khác. Khi ghi chú, luôn lưu:

- URL trang nguồn và ngày kiểm tra; chú ý ngày cập nhật/review nếu trang có hiển thị.
- Phiên bản API, chế độ triển khai, trạng thái phát hành của tính năng.
- Region/zone được hỗ trợ, hạn ngạch và giới hạn có ảnh hưởng đến hệ thống.
- Phạm vi quyền IAM, cách xác thực, yêu cầu kết nối mạng và mã hóa.
- Giả định tính tải, RTO/RPO, SLA, số lượng request, lưu lượng dữ liệu.
- Giá trị cần đo thực tế sau thử nghiệm, không biến con số ví dụ trong tài liệu thành cam kết.

**Ví dụ ghi chú ngắn:**

| Thuộc tính | Ví dụ ghi nhận cho một ứng dụng |
| --- | --- |
| Yêu cầu | API HTTPS, dữ liệu quan hệ, tải biến động |
| Phương án đang xét | Cloud Run + Cloud SQL |
| Câu hỏi cần kiểm chứng | Thời gian khởi động, giới hạn kết nối cơ sở dữ liệu, khả năng truy cập private |
| Điều kiện | Region chung giữa ứng dụng và dữ liệu; quyền kết nối đúng; cơ chế backup phù hợp |
| Nguồn cần đọc | Cloud Run overview, Cloud SQL connections, IAM, pricing, quotas |
| Cách xác nhận | Load test, đo độ trễ p95, kiểm tra log và dự toán chi phí |

## 2. Hiểu “bối cảnh Google Cloud” trước khi đọc sơ đồ

Một sơ đồ kỹ thuật có thể thiếu thông tin quản trị. Tuy nhiên, tổ chức tài nguyên, quyền và mạng quyết định hệ thống có thể được triển khai an toàn hay không.

### 2.1. Phân cấp tài nguyên

Mô hình thường gặp:

~~~text
Organization (đại diện đơn vị)
└── Folder (tùy chọn: phòng ban, môi trường hoặc nhóm)
    ├── Project: app-dev
    │   ├── Cloud Run service
    │   └── Cloud Storage bucket
    └── Project: app-prod
        ├── Cloud Run service
        └── Cloud SQL instance
~~~

- **Organization** là gốc quản trị của doanh nghiệp nếu có tổ chức Google Cloud; không phải mọi tài khoản thực hành đều có organization.
- **Folder** nhóm tài nguyên theo đơn vị, ứng dụng hoặc môi trường và chỉ được dùng bên dưới organization.
- **Project** là đơn vị nền tảng để sở hữu và quản lý phần lớn tài nguyên dịch vụ, API, quyền và theo dõi chi phí.
- **Billing account** liên kết với project để thanh toán, nhưng là một khái niệm quản lý riêng, không phải một tầng thư mục nằm bên dưới project.

Chính sách IAM và một số chính sách tổ chức có thể được kế thừa theo phân cấp. Quyền cấp quá rộng tại organization hoặc folder có thể ảnh hưởng nhiều project. Xem [Resource hierarchy](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy).

### 2.2. Phân biệt phạm vi tài nguyên

| Khái niệm | Hiểu đúng | Hệ quả thiết kế |
| --- | --- | --- |
| **Global** | Có phạm vi quản lý toàn cục, tùy loại tài nguyên | Không mặc định đồng nghĩa dữ liệu được nhân bản toàn cầu |
| **Region** | Khu vực địa lý gồm các zone | Chọn theo độ trễ, nơi lưu dữ liệu, dịch vụ có sẵn, chi phí |
| **Zone** | Một khu vực triển khai trong region | Chạy trong một zone có thể chịu tác động nếu zone đó gặp sự cố |
| **VPC network** | Mạng ảo có phạm vi global trong Google Cloud | Các subnet của VPC có phạm vi regional; thiết kế route, firewall, địa chỉ cần kiểm tra |
| **Service account** | Danh tính mà workload sử dụng | Cấp vai trò tối thiểu theo tác vụ, tránh sử dụng thông tin xác thực dài hạn không cần thiết |

**Ví dụ:** Một API ở một region kết nối đến database ở region khác có thể phát sinh độ trễ truyền dữ liệu và chi phí liên vùng. Khi xem sơ đồ, đừng chỉ ghi “Cloud Run → Cloud SQL”; hãy hỏi chúng nằm ở đâu, dùng kết nối nào và có đáp ứng mục tiêu khôi phục sau sự cố không.

## 3. Đọc một kiến trúc tham chiếu như thế nào?

**Kiến trúc tham chiếu** là phương án mẫu để học cấu trúc và các quyết định thiết kế trong một ngữ cảnh xác định. Nó có thể gồm sơ đồ, mô tả luồng xử lý, thành phần dịch vụ, cấu hình tham khảo, hướng dẫn triển khai và các đánh đổi. Không nên hiểu sơ đồ mẫu là một bản triển khai production hoàn chỉnh cho mọi hệ thống.

Cloud Architecture Center tập hợp nhiều loại nội dung khác nhau:

- **Architecture fundamentals:** nền tảng như Well-Architected, kiểu triển khai theo zone/region/nhiều region, landing zone.
- **Reference architectures:** cách phối hợp dịch vụ để giải một bài toán cụ thể.
- **Blueprints hoặc implementation guides:** chi tiết thiết lập và chính sách có thể tái sử dụng.
- **Architecture decision guidance:** khung chọn giữa các mô hình, nền tảng và phương án thay thế.

### 3.1. Sáu câu hỏi phải trả lời khi nhìn một sơ đồ

1. **Bài toán và giả định là gì?** Số người dùng, độ trễ, tải, trạng thái dữ liệu, yêu cầu pháp lý, kỹ năng đội ngũ.
2. **Luồng yêu cầu và dữ liệu đi đâu?** Ai gọi ai, giao tiếp đồng bộ hay bất đồng bộ, lưu dữ liệu ở đâu?
3. **Ranh giới tin cậy nằm ở đâu?** Thành phần public/private, xác thực đầu vào, IAM giữa các dịch vụ, xử lý bí mật.
4. **Phạm vi lỗi là gì?** Một instance, zone, region hay nhà cung cấp? Có dự phòng, backup, phục hồi?
5. **Ai vận hành phần nào?** Khách hàng quản lý hệ điều hành, cluster, ứng dụng, database hay chỉ cấu hình?
6. **Giới hạn và chi phí tăng theo yếu tố nào?** Request, vCPU/RAM, thời gian hoạt động, lưu trữ, kết nối, egress.

Nếu chưa trả lời được một câu hỏi, hãy ghi thành **giả định cần xác minh**. Đó là đầu vào cho phần thiết kế tiếp theo.

### 3.2. Ví dụ: kiến trúc ứng dụng web có xử lý sự kiện

Sơ đồ dưới đây là **minh họa học tập**, không thay thế thiết kế mạng/IAM cụ thể:

~~~mermaid
flowchart TD
    U[Người dùng] --> LB[HTTPS Load Balancer]
    LB --> API[Cloud Run: API]
    API --> DB[(Cloud SQL: dữ liệu giao dịch)]
    API --> OBJ[(Cloud Storage: tệp)]
    API --> MQ[Pub/Sub: sự kiện]
    MQ --> WORKER[Cloud Run: worker]
    WORKER --> DB
    API -. log và metric .-> OBS[Cloud Logging / Monitoring]
    WORKER -. log và metric .-> OBS
~~~

Đọc sơ đồ theo trình tự:

- **Đường đồng bộ:** Người dùng gọi API qua HTTPS load balancer tới Cloud Run; API truy cập Cloud SQL và Cloud Storage. Đưa load balancer phía trước Cloud Run là một cấu hình cần thiết lập cụ thể (chẳng hạn qua serverless NEG), không mặc nhiên tồn tại.
- **Đường bất đồng bộ:** API gửi sự kiện lên Pub/Sub; worker tiếp nhận và xử lý. Cần thiết kế xử lý lặp an toàn (idempotency), retry và trường hợp thông điệp không xử lý được. Đường giao Pub/Sub đến worker cần cấu hình tích hợp/đăng ký nhận phù hợp.
- **Dữ liệu:** Cloud SQL dùng cho quan hệ và giao dịch; Cloud Storage dùng cho đối tượng như ảnh/tệp; không thay thế lẫn nhau.
- **Bảo mật:** Xác định ai có thể gọi API, service account của API/worker, quyền truy cập bucket, kết nối database và cách quản lý secret.
- **Độ tin cậy:** Xem chính sách backup, khả năng sẵn sàng cao của database, timeout/retry, giới hạn truy cập cùng lúc và cảnh báo.
- **Chi phí:** Xem giờ hoạt động hoặc mức sử dụng của database, tài nguyên Cloud Run, số thông điệp, dữ liệu lưu và lưu lượng mạng.

**Điều không suy ra được chỉ từ hình vẽ:** Cloud SQL đã bật HA hay chưa, bucket có chính sách lifecycle nào, truy cập Cloud Run có private hay public, cấu hình WAF/TLS, vùng đặt tài nguyên, cơ chế bí mật, ngưỡng cảnh báo và mục tiêu SLO. Cần đọc phần diễn giải/cấu hình đi kèm.

### 3.3. Các kiểu kiến trúc thường gặp

| Mẫu | Đặc điểm | Câu hỏi đáng kiểm tra |
| --- | --- | --- |
| Web/API nhiều tầng | Entry point, compute, database, cache | API có state không? Cần pool kết nối? Cache xử lý nhất quán thế nào? |
| Event-driven | Producer, broker, consumer xử lý bất đồng bộ | Delivery semantics, retry, idempotency, thứ tự sự kiện |
| Dữ liệu phân tích | Nguồn dữ liệu, ingestion, xử lý, kho phân tích | Batch hay stream, chất lượng dữ liệu, lưu trữ và bảo mật |
| Container platform | Nhiều service trên Kubernetes | Ai quản cluster, policy, autoscaling, nâng cấp và mạng? |
| Hybrid/migration | Kết nối hệ thống hiện hữu với cloud | Băng thông, định tuyến, danh tính, đồng bộ, khả năng rollback |
| Multi-region / DR | Có vùng dự phòng hoặc phân phối yêu cầu | RTO/RPO, đồng bộ dữ liệu, failover, chi phí vận hành |

Một mẫu chỉ hữu ích khi mục tiêu và điều kiện của nó tương đồng với hệ thống cần thiết kế. Ví dụ, multi-region giúp giải quyết một số yêu cầu độ tin cậy hoặc độ trễ nhưng làm tăng độ phức tạp đồng bộ dữ liệu, kiểm thử phục hồi và chi phí.

## 4. Danh mục dịch vụ GCP theo nhu cầu

Google Cloud có nhiều dịch vụ và tên gọi có thể thay đổi theo thời gian. Bảng dưới đây là **bản đồ định hướng**, không phải danh sách sản phẩm đầy đủ hay thay thế tài liệu tính năng mới nhất.

| Nhu cầu | Dịch vụ tiêu biểu | Khi nào nên khảo sát? |
| --- | --- | --- |
| Máy ảo và kiểm soát hệ điều hành | **Compute Engine** | Ứng dụng cần VM, quyền cấu hình OS hoặc chuyển workload truyền thống |
| Container và điều phối | **Google Kubernetes Engine (GKE)** | Có nhiều workload cần Kubernetes, policy/orchestration và hệ sinh thái Kubernetes |
| Ứng dụng/container không muốn quản cluster | **Cloud Run** | HTTP service, worker, job hoặc workload phù hợp mô hình được quản lý |
| Lưu trữ tệp/đối tượng | **Cloud Storage** | Ảnh, tệp, backup object, dữ liệu thô, static assets |
| Lưu trữ gắn với VM / hệ thống tệp | **Persistent Disk/Hyperdisk**, **Filestore** | Block device cho VM hoặc chia sẻ file theo nhu cầu ứng dụng |
| Cơ sở dữ liệu quan hệ | **Cloud SQL**, **AlloyDB**, **Spanner** | SQL/giao dịch với yêu cầu khác nhau về khả năng tương thích, hiệu năng và mở rộng |
| NoSQL và cache | **Firestore**, **Bigtable**, **Memorystore** | Document, truy cập dữ liệu quy mô lớn theo khóa, cache/in-memory |
| Phân tích và pipeline | **BigQuery**, **Dataflow**, **Pub/Sub** | Kho phân tích, xử lý batch/stream, truyền sự kiện |
| Mạng và phân phối | **VPC**, **Cloud Load Balancing**, **Cloud DNS**, **Cloud CDN**, **Cloud NAT**, **Cloud VPN**, **Cloud Interconnect** | Kết nối, định tuyến, DNS, phân phối nội dung, kết nối hybrid |
| Danh tính và bảo mật | **IAM**, **Organization Policy**, **Secret Manager**, **Cloud KMS**, **Security Command Center** | Phân quyền, chính sách tập trung, bí mật, khóa, theo dõi rủi ro |
| CI/CD và hạ tầng | **Cloud Build**, **Artifact Registry**, **Cloud Deploy**, **Infrastructure Manager/Terraform** | Build, lưu artifact, phân phối bản phát hành, hạ tầng dạng mã |
| Vận hành và chi phí | **Cloud Logging**, **Cloud Monitoring**, **Cloud Trace**, **Cloud Billing** | Thu log/metric/trace, tạo cảnh báo, xem chi phí và lập ngân sách |

### 4.1. Lựa chọn compute: Compute Engine, GKE hay Cloud Run?

| Tiêu chí | Compute Engine | GKE | Cloud Run |
| --- | --- | --- | --- |
| Đơn vị chính | VM | Cluster và workload Kubernetes | Service, job và workload được hỗ trợ |
| Kiểm soát hạ tầng | Cao, tự quản nhiều thành phần OS | Quản workload Kubernetes; mức quản node khác nhau giữa Standard và Autopilot | Chủ yếu quản code/container, cấu hình và quyền |
| Tăng/giảm tải | Thiết lập instance group/autoscaling khi phù hợp | Autoscaling pod/node theo cấu hình | Cơ chế scale của nền tảng theo đặc tính workload |
| Phù hợp điển hình | Ứng dụng cần hệ điều hành/VM cụ thể | Nhiều ứng dụng cần Kubernetes | Web API, backend, background processing với ít quản trị hạ tầng |
| Cần kiểm tra | Patch, image, firewall, HA | Cluster operations, policy, networking, cost | Timeout, concurrency, cold start, kết nối mạng, scaling, giới hạn |

**Cách quyết định:** Nếu workload không đòi hỏi điều phối Kubernetes hay quản trị OS, nên đánh giá Cloud Run trước để giảm công sức vận hành. Nếu cần Kubernetes và các đặc tính của nó, đánh giá GKE Autopilot/Standard. Nếu cần kiểm soát VM, hãy khảo sát Compute Engine. Đây là điểm xuất phát; quyết định cuối phải dựa trên các giới hạn kỹ thuật và bài kiểm thử.

### 4.2. Lựa chọn dữ liệu: bắt đầu từ kiểu truy cập

- **Cloud SQL:** cơ sở dữ liệu quan hệ được quản lý, thích hợp ứng dụng cần MySQL, PostgreSQL hoặc SQL Server với phạm vi mở rộng phù hợp.
- **AlloyDB:** cơ sở dữ liệu tương thích PostgreSQL, đáng khảo sát khi yêu cầu về hiệu năng và quy mô khác với lựa chọn Cloud SQL thông thường.
- **Spanner:** cơ sở dữ liệu quan hệ có khả năng mở rộng theo chiều ngang, phù hợp khi cần đặc tính phân tán và khả năng mở rộng đặc thù.
- **Firestore:** cơ sở dữ liệu document, phù hợp mô hình truy cập document và ứng dụng cần đồng bộ theo mô hình dịch vụ.
- **Bigtable:** cơ sở dữ liệu NoSQL theo khóa cho khối lượng lớn và thông lượng cao; không dùng như một database SQL giao dịch thông thường.
- **BigQuery:** kho dữ liệu phân tích; không chọn làm nơi xử lý giao dịch trực tuyến chỉ vì cũng truy vấn được bằng SQL.
- **Cloud Storage:** object storage cho tệp và dữ liệu; không có cùng mô hình giao dịch với cơ sở dữ liệu quan hệ.

Các câu hỏi quan trọng gồm: dạng dữ liệu, ràng buộc giao dịch, kiểu truy vấn, độ trễ, tốc độ tăng dung lượng, yêu cầu sao lưu, tương thích ứng dụng hiện có và mô hình giá.

### 4.3. Phân biệt thành phần tích hợp

**Pub/Sub** truyền thông điệp/sự kiện giữa các thành phần; **Eventarc** hỗ trợ định tuyến một số loại sự kiện đến đích được hỗ trợ; **Workflows** điều phối các bước tác vụ/API; **Cloud Scheduler** kích hoạt công việc theo lịch. Không nên gộp các dịch vụ này thành một khái niệm “job queue” duy nhất. Chọn theo nguồn kích hoạt, mô hình nhận/xử lý, yêu cầu retry và khả năng quan sát.

### 4.4. Mạng, danh tính và vận hành đi cùng mọi sản phẩm

Việc lựa chọn compute/database không thể tách khỏi các thành phần nền:

- **Project, IAM và Organization Policy**: ai được cấu hình, ai được gọi và ràng buộc nào được áp đặt.
- **VPC, subnet, firewall, route, load balancing**: đường lưu lượng đi qua đâu và có thể truy cập từ đâu.
- **Secret Manager/KMS**: cách giữ bí mật và quản lý khóa thay vì nhúng credential vào source code.
- **Logging, Monitoring và alerting**: làm sao biết hệ thống còn hoạt động, có quá tải hoặc chi phí tăng bất thường.
- **Cloud Billing**: chi phí phụ thuộc cả compute, database, storage, dữ liệu truyền và lưu lượng truy cập.

## 5. Từ danh mục dịch vụ đến quyết định có thể kiểm chứng

Đừng bắt đầu bằng danh sách “dịch vụ phổ biến nhất”. Hãy bắt đầu bằng các thuộc tính của workload:

| Câu hỏi | Dẫn tới quyết định |
| --- | --- |
| Ứng dụng stateless hay stateful? | Compute độc lập hay cần lưu trạng thái và chiến lược phiên |
| Request đồng bộ hay xử lý nền? | API/service hay message-based worker, scheduler, workflow |
| Cần VM/OS hay Kubernetes? | Compute Engine, GKE hoặc Cloud Run |
| Dữ liệu có quan hệ và transaction không? | Nhóm SQL thay vì object store/warehouse |
| Cần bảo vệ dữ liệu như thế nào? | IAM, quản lý secret, mã hóa, mạng, lưu trữ và backup |
| Mục tiêu SLO, RTO, RPO? | Chính sách HA, backup, khôi phục, đa vùng và kiểm thử |
| Dự báo tải và chi phí ra sao? | Giới hạn scale, storage tier, egress, dự toán, cảnh báo |
| Đội ngũ có thể vận hành mức nào? | Mức dịch vụ được quản lý và phạm vi tự quản |

Một **hồ sơ quyết định kiến trúc (ADR)** ngắn có thể gồm:

~~~text
Quyết định: Chọn Cloud Run cho API đặt chỗ
Bối cảnh: API HTTPS, tải biến động, nhóm vận hành nhỏ
Lựa chọn đã xem xét: Compute Engine, GKE, Cloud Run
Lý do: Phù hợp mô hình service được quản lý; không yêu cầu Kubernetes
Điều kiện: Kiểm chứng timeout, concurrency, kết nối Cloud SQL và IAM
Đánh đổi: Phụ thuộc giới hạn nền tảng; cần thử nghiệm cold start và tải
Độ tin cậy: Kiểm tra HA/backup cho dữ liệu; đặt SLO và cảnh báo
Chi phí: So sánh dự toán theo tải thật, database, logs và egress
Nguồn: URL tài liệu + ngày tra cứu
Kết quả thử nghiệm: Sẽ bổ sung sau load test và review bảo mật
~~~

Điểm giá trị của ADR là **lý do và điều kiện áp dụng**, không phải chỉ tên dịch vụ cuối cùng.

## 6. Tình huống xuyên suốt: thiết kế dịch vụ đặt lịch

Một nhóm phát triển cần xây dựng ứng dụng đặt lịch cho khách hàng:

- API HTTPS, lưu đơn đặt lịch và trạng thái thanh toán; cần giao dịch nhất quán.
- Tải thông thường thấp, có đợt tăng đột biến; nhóm không chuyên vận hành Kubernetes.
- Người dùng tải ảnh minh họa; gửi thông báo xác nhận có thể xử lý bất đồng bộ.
- Có môi trường thử nghiệm và production tách biệt; cần theo dõi lỗi, độ trễ, chi phí.

**Bước 1 — Tóm tắt yêu cầu:** Xác định mục tiêu độ trễ (ví dụ p95), khối lượng yêu cầu dự kiến, quy mô dữ liệu, dữ liệu nhạy cảm, ngân sách, RTO/RPO. Các giá trị phải do sản phẩm và vận hành thống nhất; không suy từ kiến trúc mẫu.

**Bước 2 — Chọn nền tảng ứng dụng:** Cloud Run là ứng viên đầu tiên vì workload là API và nhóm muốn giảm công việc quản hạ tầng. GKE được cân nhắc nếu về sau phát sinh nhu cầu Kubernetes cụ thể; Compute Engine thích hợp khi có yêu cầu VM hoặc OS riêng.

**Bước 3 — Chọn lưu trữ:** Cloud SQL là ứng viên cho dữ liệu giao dịch quan hệ; Cloud Storage dùng cho ảnh/tệp. Cần kiểm tra số kết nối cơ sở dữ liệu khi Cloud Run scale, timeout, cơ chế backup và phương án phục hồi. Với yêu cầu cao hơn, so sánh thêm AlloyDB/Spanner theo bài toán cụ thể.

**Bước 4 — Tách tác vụ nền:** API phát sự kiện vào Pub/Sub và worker xử lý thông báo. Thiết kế idempotency bằng mã sự kiện/mã giao dịch vì tác vụ có thể được giao lại; quy định retry, dead-letter hoặc xử lý ngoại lệ nếu cần.

**Bước 5 — Bảo vệ tài nguyên:** Sử dụng service account riêng cho API và worker, cấp quyền tối thiểu, đặt secret ngoài mã nguồn, giới hạn đường mạng, xem xét xác thực người dùng và kiểm soát đầu vào. Tách project dev/prod giúp phân định tài nguyên, quyền và chi phí.

**Bước 6 — Triển khai và vận hành:** Dùng Artifact Registry để lưu image, Cloud Build/Cloud Deploy hoặc pipeline phù hợp để phát hành, Cloud Logging/Monitoring để theo dõi, xác lập dashboard và alert cho lỗi, độ trễ, tỷ lệ thành công và chi phí.

**Bước 7 — Đánh giá kiến trúc:** Thử nghiệm tăng tải, mất kết nối database, retry sự kiện, khôi phục backup, phân quyền và dự toán theo mức sử dụng thực tế. Mọi kiến trúc tham chiếu đều phải đi qua bước này trước production.

### 6.1. Minh họa cách tra cứu tài nguyên hiện có với gcloud

Các lệnh sau **chỉ đọc** thông tin của project mà tài khoản có quyền truy cập, giúp đối chiếu kiến trúc được vẽ với tài nguyên thực tế. Thay các giá trị chữ hoa bằng ID/region của môi trường và đăng nhập Google Cloud CLI trước khi chạy.

~~~bash
# Xem thông tin project
gcloud projects describe PROJECT_ID

# Xem các API đang được bật
gcloud services list --enabled --project=PROJECT_ID

# Xem Cloud Run services của một region
gcloud run services list --region=REGION --project=PROJECT_ID

# Xem các mạng VPC
gcloud compute networks list --project=PROJECT_ID

# Xem các bucket mà tài khoản được phép liệt kê
gcloud storage buckets list --project=PROJECT_ID
~~~

Nếu lệnh trả lỗi quyền truy cập, hãy xác minh IAM trước; không tự cấp vai trò rộng chỉ để lệnh chạy thành công. Danh sách rỗng cũng có thể do chọn sai project/region hoặc tài nguyên thuộc dịch vụ khác.

### 6.2. Những điểm cần quan sát sau triển khai

| Tín hiệu | Ý nghĩa | Hành động khi bất thường |
| --- | --- | --- |
| Tỷ lệ lỗi HTTP / lỗi nghiệp vụ | Trải nghiệm và khả năng phục vụ | Truy vết log, dependency, thay đổi phát hành |
| Độ trễ p50/p95/p99 | Mức đáp ứng người dùng | Xem cold start, database, network và tải |
| Số instance, concurrent request, DB connections | Áp lực mở rộng | Kiểm tra giới hạn và pool kết nối |
| Số lần retry, tồn đọng sự kiện | Chất lượng xử lý nền | Kiểm tra worker, idempotency, lỗi đầu vào |
| Dung lượng và tốc độ tăng dữ liệu | Dự báo storage và backup | Cấu hình vòng đời dữ liệu, dự trù chi phí |
| Chi phí theo project/service | Hiệu quả và rủi ro vượt ngân sách | So sánh baseline, dự báo và nguồn phát sinh |

**Lưu ý chi phí:** Cảnh báo ngân sách dùng để thông báo khi đạt ngưỡng; không nên mặc định rằng mọi budget alert sẽ tự dừng mọi dịch vụ. Tài liệu Cloud Billing hiện phân biệt các loại budget và phạm vi áp dụng, vì vậy phải đọc điều kiện cụ thể trước khi dùng ngân sách làm cơ chế kiểm soát chi tiêu.

## 7. Dùng Well-Architected Framework để phản biện phương án

Google Cloud Well-Architected Framework hiện tổ chức hướng dẫn theo sáu trụ cột. Áp dụng mỗi trụ cột như một nhóm câu hỏi rà soát:

| Trụ cột | Câu hỏi phản biện cho ứng dụng đặt lịch |
| --- | --- |
| **Operational excellence — Vận hành** | Ai nhận cảnh báo? Có runbook, rollback, quan sát, lịch kiểm tra backup? |
| **Security, privacy and compliance — Bảo mật** | IAM có tối thiểu? Dữ liệu cá nhân nằm ở đâu? Secret và audit log được quản lý thế nào? |
| **Reliability — Độ tin cậy** | SLO/RTO/RPO là gì? Phụ thuộc database có điểm lỗi đơn không? Đã thử phục hồi? |
| **Cost optimization — Chi phí** | Thành phần nào chạy liên tục? Có dự báo, gắn nhãn tài nguyên và tối ưu dữ liệu truyền không? |
| **Performance optimization — Hiệu năng** | Đo p95 trong giờ cao điểm chưa? Database/concurrency có đáp ứng tải không? |
| **Sustainability — Bền vững** | Tài nguyên có được chọn đúng kích thước? Có xóa workload và dữ liệu không cần thiết? |

Sáu trụ cột này không phải sáu dịch vụ. Chúng là cách đặt câu hỏi để tìm điểm yếu trong một phương án kỹ thuật. Khi có yêu cầu ngành hoặc kỹ thuật đặc thù, xem thêm các **perspectives** liên quan của framework.

## 8. Các lỗi thường gặp khi đọc tài liệu và kiến trúc GCP

1. **Thấy mẫu kiến trúc và triển khai nguyên xi.** Mẫu có điều kiện về tải, vùng, bảo mật hoặc mục tiêu khác. Cần phân tích lại cho workload.
2. **Chọn dịch vụ chỉ theo tên sản phẩm.** Nên so sánh dữ liệu, kiểu truy cập, giới hạn, mô hình vận hành và giá.
3. **Nhầm SQL transaction với data warehouse.** Cloud SQL/AlloyDB/Spanner giải các bài toán khác BigQuery; SQL là ngôn ngữ, không đủ xác định mục tiêu hệ thống.
4. **Cho rằng managed service nghĩa là không cần vận hành.** Vẫn phải cấu hình IAM, network, backup, giới hạn, quan sát, kiểm tra lỗi và chi phí.
5. **Bỏ qua region, zone và truyền dữ liệu.** Có thể tác động lớn đến độ trễ, rủi ro gián đoạn, yêu cầu lưu trú dữ liệu và giá.
6. **Sao chép lệnh quickstart vào production.** Kiểm tra lại quyền, tài khoản dịch vụ, kết nối public, cấu hình dự phòng và cách quản lý secret.
7. **Bỏ qua phiên bản và trạng thái tính năng.** Kiểm tra release notes, vị trí hỗ trợ, giới hạn và ngày cập nhật trang.
8. **Đồng nhất giá dự kiến với chi phí thực tế.** Phải đo thêm lưu lượng, lưu trữ, log, egress, chi phí nền và tăng trưởng.

## 9. Bài thực hành tự kiểm tra

**Bài toán:** Một công ty cần tiếp nhận dữ liệu đơn hàng từ API, lưu giao dịch, xử lý tạo báo cáo hằng ngày và gửi email sau khi có đơn hàng mới. Đội vận hành nhỏ; dữ liệu cần sao lưu và chi phí phải được theo dõi.

Hãy thực hiện theo trình tự:

1. Tìm trang Documentation và Architecture Center phù hợp; ghi tối thiểu ba URL kèm lý do chọn.
2. Vẽ sơ đồ gồm đầu vào, compute, database, kênh sự kiện, nơi xử lý báo cáo và quan sát.
3. Chọn giữa Cloud Run/GKE/Compute Engine; giải thích ít nhất hai đánh đổi.
4. Phân biệt kho giao dịch với kho phân tích; quyết định có cần BigQuery ngay từ đầu không.
5. Liệt kê tối thiểu năm câu hỏi chưa biết cần xác minh trước production.
6. Ghi một ADR ngắn với quyết định, giả định, rủi ro, kiểm chứng và phương án thay thế.

**Gợi ý đối chiếu:** Phương án khả thi có thể là Cloud Run tiếp nhận API, Cloud SQL lưu đơn hàng, Pub/Sub phân phối sự kiện, worker gửi email, Cloud Scheduler/Workflows cho báo cáo định kỳ, BigQuery nếu nhu cầu phân tích đủ rõ. Cần kiểm chứng tính nhất quán, cách kích hoạt xử lý, quyền truy cập, backup, retry và giá. Đây chỉ là một phương án, không phải đáp án bắt buộc.

### Checklist trước khi chốt một lựa chọn GCP

- [ ] Tôi mô tả được workload và yêu cầu phi chức năng có thể đo được.
- [ ] Tôi xác định được tài liệu overview, hướng dẫn, API, hạn ngạch, giá và release notes.
- [ ] Tôi biết phạm vi organization/project, IAM, mạng, region/zone liên quan.
- [ ] Tôi giải thích được dữ liệu đi qua các thành phần như thế nào.
- [ ] Tôi đã so sánh ít nhất một phương án thay thế và ghi rõ đánh đổi.
- [ ] Tôi đã xem các yêu cầu bảo mật, sao lưu, khôi phục, quan sát và chi phí.
- [ ] Tôi có kế hoạch kiểm thử và cập nhật ADR khi kết quả thực tế khác giả định.

## 10. Nguồn tham khảo để tiếp tục học

Tất cả các nguồn dưới đây là trang chính thức của Google Cloud; khi dùng cho dự án thực tế cần kiểm tra trạng thái tính năng, giới hạn và giá tại thời điểm triển khai.

- [Google Cloud Documentation](https://docs.cloud.google.com/docs) — cổng tài liệu chính.
- [Get started with Google Cloud](https://docs.cloud.google.com/docs/get-started) — thiết lập môi trường và công cụ.
- [Products and Services](https://cloud.google.com/products) và [Products at a glance](https://docs.cloud.google.com/docs/product-list) — bản đồ sản phẩm.
- [Cloud Architecture Center](https://docs.cloud.google.com/architecture) và [Architecture fundamentals](https://docs.cloud.google.com/architecture/fundamentals) — tài liệu kiến trúc.
- [Google Cloud Well-Architected Framework](https://docs.cloud.google.com/architecture/framework) — khung đánh giá thiết kế.
- [Choose a compute option](https://docs.cloud.google.com/docs/compute-area/choose-compute-options) — hỗ trợ chọn nền tảng tính toán.
- [About resource hierarchy](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy) — tổ chức tài nguyên.
- [Create and manage budgets and budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets) — theo dõi và kiểm soát chi phí.
- [Google Cloud pricing](https://cloud.google.com/pricing) — tìm bảng giá và công cụ ước tính.

**Điểm cần giữ lại:** Đọc tài liệu theo câu hỏi kỹ thuật, đọc sơ đồ theo luồng dữ liệu và ranh giới vận hành, rồi chọn dịch vụ dựa trên yêu cầu có thể kiểm chứng. Một quyết định tốt có nguồn tham khảo, giả định rõ ràng, đánh đổi được ghi lại và kết quả thử nghiệm chứng minh.
