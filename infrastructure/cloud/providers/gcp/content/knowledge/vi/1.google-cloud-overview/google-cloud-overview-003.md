# Lựa chọn IaaS, PaaS, serverless và dịch vụ được quản lý trên Google Cloud

> **Chương:** Tổng quan Google Cloud  
> **Chủ đề:** Lựa chọn IaaS, PaaS, serverless và dịch vụ được quản lý

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học tìm hiểu Google Cloud từ cấu trúc tổ chức, project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, triển khai tự động, độ tin cậy và chi phí. Bài này kết nối các dịch vụ đó qua một quyết định quan trọng: **đội ngũ sẽ tự quản lý những phần nào của hệ thống, và giao những phần nào cho Google Cloud?**

Không có mô hình nào tốt nhất cho mọi ứng dụng. Một ứng dụng cũ cần tùy chỉnh hệ điều hành có thể phù hợp với máy ảo; một API mới chạy trong container có thể phù hợp với Cloud Run; một nền tảng cần Kubernetes có thể cần GKE; còn dữ liệu giao dịch thường nên đặt trong cơ sở dữ liệu được quản lý thay vì tự cài trên máy ảo.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **IaaS**, **PaaS**, **serverless** và **dịch vụ được quản lý**, đồng thời nhận ra chúng có thể giao nhau.
- So sánh Compute Engine, GKE, App Engine, Cloud Run và Cloud Run functions theo quyền kiểm soát, cách mở rộng, vận hành và chi phí.
- Ghép lựa chọn lớp tính toán với Cloud Storage, Cloud SQL, Firestore, Spanner, BigQuery và các dịch vụ tích hợp phù hợp.
- Giải thích các đánh đổi về IAM, mạng, dữ liệu có trạng thái, độ tin cậy, khả năng chuyển đổi nền tảng và tổng chi phí sở hữu.
- Đề xuất và bảo vệ một kiến trúc Google Cloud cho yêu cầu triển khai thực tế.

## 2. Hiểu đúng các mô hình dịch vụ

### 2.1. IaaS: thuê hạ tầng, tự quản lý nhiều lớp phần mềm

**Infrastructure as a Service (IaaS)** cung cấp máy tính, ổ đĩa, mạng và tài nguyên hạ tầng. Ví dụ điển hình là **Compute Engine**: bạn chọn loại máy ảo (VM), hệ điều hành, ảnh máy, ổ đĩa và cấu hình mạng; Google Cloud vận hành hạ tầng vật lý bên dưới.

Với VM tự quản lý, đội ngũ thường chịu trách nhiệm cập nhật hệ điều hành, cài runtime, bảo mật tiến trình, triển khai ứng dụng, giám sát và thiết kế phục hồi. IaaS hữu ích khi ứng dụng yêu cầu cấu hình hệ điều hành đặc biệt, phần mềm cũ, một tiến trình chạy lâu dài hoặc mức kiểm soát không phù hợp với nền tảng trừu tượng hơn.

**Lưu ý:** IaaS không đồng nghĩa với phải vận hành thủ công. Bạn vẫn có thể dùng instance template, managed instance group (MIG), autoscaling, load balancer và công cụ hạ tầng dưới dạng mã để tự động hóa.

### 2.2. PaaS: tập trung vào ứng dụng và môi trường chạy

**Platform as a Service (PaaS)** cung cấp một nền tảng triển khai với nhiều nhiệm vụ vận hành được trừu tượng hóa. **App Engine** là ví dụ tiêu biểu: nhà phát triển triển khai ứng dụng theo các runtime và cấu hình được hỗ trợ, trong khi nền tảng xử lý nhiều phần của việc cung cấp tài nguyên và triển khai.

Đổi lại, ứng dụng phải tuân theo mô hình runtime, vòng đời và cấu hình của nền tảng. Các môi trường App Engine khác nhau có mức linh hoạt và đặc tính tài nguyên khác nhau; cần kiểm tra yêu cầu thực tế trước khi chọn.

### 2.3. Serverless: không phải tự cấp phát máy chủ cho từng workload

**Serverless** nghĩa là nền tảng đảm nhận việc cấp phát và vận hành máy chủ cho workload theo một mô hình sử dụng. **Cloud Run** chạy dịch vụ/container, tác vụ (jobs) và các workload phù hợp mà không buộc đội ngũ quản lý VM hoặc node Kubernetes. **Cloud Run functions** thích hợp cho logic hàm được kích hoạt theo sự kiện hoặc HTTP.

Serverless **không có nghĩa là không có máy chủ**, **không luôn miễn phí khi rảnh**, và **không đảm bảo mọi workload đều về 0 tài nguyên**. Chẳng hạn, cấu hình số instance tối thiểu, đặc tính CPU, kiểu workload và chính sách tính phí có thể tạo chi phí dù lượng request thấp. Ứng dụng vẫn phải xử lý timeout, kết nối cơ sở dữ liệu, lỗi tạm thời, tính idempotent và giới hạn mở rộng.

### 2.4. Dịch vụ được quản lý: một chiều phân loại khác

**Managed service** là dịch vụ mà nhà cung cấp gánh một phần đáng kể công việc vận hành của một thành phần cụ thể, chẳng hạn nâng cấp hạ tầng, sao lưu hoặc khả năng sẵn sàng cao theo cấu hình. Ví dụ: **Cloud SQL** (cơ sở dữ liệu quan hệ), **Cloud Storage** (object storage), **Firestore** (cơ sở dữ liệu tài liệu), **Pub/Sub** (nhắn tin sự kiện) và **BigQuery** (phân tích dữ liệu).

Các nhãn **managed**, **PaaS** và **serverless** không loại trừ nhau. Cloud Run vừa thuộc mô hình serverless vừa là nền tảng được quản lý; Cloud SQL là cơ sở dữ liệu được quản lý nhưng bạn vẫn phải lựa chọn kích thước, cấu hình HA, backup, kết nối và kiểm soát chi phí. Không nên gán cả kiến trúc vào một nhãn rồi suy ra mọi trách nhiệm đều đã được chuyển giao.

### 2.5. Trách nhiệm được chia sẻ thay đổi theo lớp dịch vụ

| Lớp trách nhiệm | Compute Engine (VM) | App Engine / Cloud Run | Dịch vụ dữ liệu được quản lý |
|---|---|---|---|
| Hạ tầng vật lý | Google Cloud | Google Cloud | Google Cloud |
| Hệ điều hành / node của workload | Chủ yếu đội ngũ với VM | Chủ yếu nền tảng | Chủ yếu nền tảng |
| Runtime / bản phụ thuộc của ứng dụng | Đội ngũ | Đội ngũ chịu trách nhiệm mã và phụ thuộc; nền tảng xử lý hạ tầng chạy | Không áp dụng cho mã ứng dụng, trừ logic người dùng cấu hình |
| Mã, phân quyền và dữ liệu | Đội ngũ | Đội ngũ | Đội ngũ quyết định truy cập, mô hình dữ liệu và vòng đời dữ liệu |
| Sao lưu, mở rộng và phục hồi | Đội ngũ thiết kế, có thể dùng dịch vụ hỗ trợ | Nền tảng hỗ trợ mở rộng theo khả năng sản phẩm; ứng dụng vẫn phải chịu lỗi | Google Cloud cung cấp tính năng; đội ngũ phải **bật, cấu hình, kiểm tra** theo mục tiêu |

Bảng thể hiện xu hướng trách nhiệm, không thay thế tài liệu hoặc cam kết dịch vụ cụ thể.

## 3. Bản đồ dịch vụ tính toán trên Google Cloud

| Dịch vụ | Mô hình phù hợp | Kiểm soát và công sức vận hành | Workload thường phù hợp | Điểm cần cân nhắc |
|---|---|---|---|---|
| **Compute Engine** | IaaS | Kiểm soát VM/OS cao; đội ngũ quản lý nhiều lớp | Ứng dụng legacy, phần mềm cần OS riêng, tiến trình chuyên biệt | Patch, image, scale, bảo mật OS, HA |
| **GKE Standard** | Kubernetes được quản lý | Kiểm soát cấu hình cluster/node cao; phải vận hành Kubernetes và node pool | Nền tảng nhiều service cần API Kubernetes, operator, chính sách chuyên sâu | Độ phức tạp cluster, node, nâng cấp và chi phí nền |
| **GKE Autopilot** | Kubernetes được quản lý với mức tự động hóa hạ tầng cao hơn | Giảm gánh nặng node; vẫn quản lý workload và tài nguyên Kubernetes | Cần Kubernetes nhưng muốn giảm quản trị node | Giới hạn cấu hình/khả năng tương thích và cách tính chi phí theo cấu hình |
| **App Engine** | PaaS | Triển khai theo runtime và môi trường được hỗ trợ | Web app/API phù hợp mô hình App Engine | Ràng buộc runtime, cấu hình, khả năng chuyển đổi |
| **Cloud Run** | Serverless container | Đưa image và cấu hình dịch vụ/job; không quản lý máy chủ | HTTP API, web app, xử lý sự kiện, job theo đợt | Timeout, concurrency, cold start, tài nguyên tạm thời, kết nối DB |
| **Cloud Run functions** | Serverless function | Viết hàm và cấu hình trigger | Webhook/logic nhỏ, xử lý sự kiện theo mục đích rõ ràng | Trigger, retry, idempotency, giới hạn thực thi |

**GKE không tự động là phương án tốt hơn khi có nhiều microservice.** Nếu từng service chỉ cần HTTP/container tiêu chuẩn, Cloud Run vẫn có thể đơn giản hơn. Chọn GKE khi thật sự cần hệ sinh thái, API, controller hoặc cách vận hành của Kubernetes.

## 4. Quy trình lựa chọn lớp tính toán

Trước khi chọn sản phẩm, hãy ghi lại yêu cầu theo các câu hỏi sau:

1. **Có cần quyền kiểm soát hệ điều hành, driver, kernel hoặc tiến trình nền đặc biệt không?** Nếu có, xem xét Compute Engine.
2. **Có phụ thuộc API Kubernetes, Helm/operator, service mesh, scheduler hoặc cấu trúc cluster không?** Nếu có, đánh giá GKE Standard và Autopilot.
3. **Ứng dụng có thể đóng gói thành container, nhận HTTP/event hoặc chạy job có điểm kết thúc không?** Nếu có, thử Cloud Run trước.
4. **Ứng dụng có hợp mô hình runtime và quy trình triển khai của App Engine không?** Nếu có, App Engine là một lựa chọn PaaS hợp lý.
5. **Logic chỉ là một hàm phản hồi HTTP/sự kiện?** Cloud Run functions có thể rút gọn triển khai.
6. **Có trạng thái cần giữ bền vững không?** Chọn storage/database riêng; không dựa vào bộ nhớ hoặc hệ thống tệp tạm thời của instance để lưu dữ liệu nghiệp vụ.

~~~mermaid
flowchart TD
    A["Bắt đầu: yêu cầu của workload"] --> B{"Cần kiểm soát OS/VM đặc biệt?"}
    B -->|Có| C["Compute Engine"]
    B -->|Không| D{"Phụ thuộc Kubernetes API/operator?"}
    D -->|Có| E["Đánh giá GKE Standard / Autopilot"]
    D -->|Không| F{"Container HTTP, sự kiện hoặc job?"}
    F -->|Có| G["Cloud Run"]
    F -->|Không| H{"Hợp runtime và mô hình App Engine?"}
    H -->|Có| I["App Engine"]
    H -->|Không| J{"Logic hàm đơn giản theo HTTP/event?"}
    J -->|Có| K["Cloud Run functions"]
    J -->|Không| L["Rà lại yêu cầu và phương án triển khai"]
    C --> M["Chọn storage, database, IAM, mạng, SLO và chi phí"]
    E --> M
    G --> M
    I --> M
    K --> M
    L --> M
~~~

Sơ đồ là **bộ lọc ban đầu**, không phải thuật toán thay thế thiết kế. Ví dụ một API dùng container vẫn có thể cần GKE vì yêu cầu operator, hoặc VM vì phụ thuộc phần mềm không thể container hóa.

### 4.1. Các tiêu chí buộc phải so sánh

| Tiêu chí | Câu hỏi cụ thể | Tác động đến lựa chọn |
|---|---|---|
| Quyền kiểm soát | Có cần OS tùy chỉnh, agent đặc biệt, quyền root hay mạng rất chuyên biệt? | Ưu tiên VM/GKE khi dịch vụ trừu tượng hơn không hỗ trợ |
| Mô hình workload | Request ngắn, job theo đợt, tiến trình dài hạn, GPU hay nhiều kết nối đồng thời? | Quyết định loại dịch vụ và giới hạn thực thi cần kiểm tra |
| Độ biến thiên tải | Tải liên tục hay tăng đột biến theo giờ/sự kiện? | Autoscaling/serverless hữu ích với tải biến thiên; VM có thể hợp tải ổn định |
| Trạng thái | Có cần filesystem bền vững, giao dịch SQL, dữ liệu phiên hay queue? | Tách state sang Cloud Storage/DB/queue phù hợp |
| Độ tin cậy | SLO, RTO, RPO, yêu cầu multi-zone/multi-region ra sao? | Ảnh hưởng HA, replication, backup, failover và thiết kế app |
| Bảo mật và kết nối | Dữ liệu phải kết nối private hay có ràng buộc compliance? | Xem IAM, VPC, ingress/egress, mã hóa và audit |
| Năng lực vận hành | Đội ngũ có kinh nghiệm quản lý Linux/Kubernetes? | Có thể ưu tiên dịch vụ được quản lý để giảm thao tác |
| Tổng chi phí | Tính cả compute nhàn rỗi, cluster, DB, storage, egress và công vận hành chưa? | So sánh workload thật, không chỉ giá một đơn vị compute |
| Khả năng di chuyển | Ứng dụng có cần chạy ngoài Google Cloud sau này? | Container chuẩn thường linh hoạt hơn khi ít phụ thuộc API đặc thù |

## 5. Chọn dịch vụ dữ liệu và tích hợp cùng lớp tính toán

Lựa chọn compute chỉ giải quyết **nơi chạy mã**. Dữ liệu, sự kiện và công việc nền cần có kiến trúc tương ứng.

| Nhu cầu | Dịch vụ có thể xem xét | Nguyên tắc chọn |
|---|---|---|
| Ảnh, tệp, bản xuất, backup dạng object | **Cloud Storage** | Lưu object trong bucket; thiết kế quyền truy cập, lớp lưu trữ, vòng đời và vị trí dữ liệu |
| Giao dịch SQL với PostgreSQL/MySQL/SQL Server | **Cloud SQL** | Ưu tiên khi cần RDBMS quen thuộc; cấu hình HA, backup/PITR theo khả năng engine và yêu cầu |
| PostgreSQL tương thích, cần tính năng/hiệu năng dành cho workload doanh nghiệp | **AlloyDB for PostgreSQL** | Đánh giá theo nhu cầu hiệu năng, tương thích và chi phí |
| Dữ liệu quan hệ cần mở rộng phân tán quy mô lớn | **Spanner** | Xem yêu cầu giao dịch, phân tán địa lý và mô hình dữ liệu; tránh chọn chỉ vì “lớn” |
| Dữ liệu tài liệu linh hoạt cho ứng dụng | **Firestore** | Phù hợp truy cập theo document/index; thiết kế query và chi phí thao tác |
| Phân tích trên tập dữ liệu lớn, báo cáo SQL/warehouse | **BigQuery** | Dùng cho analytical workloads; không xem như thay thế trực tiếp OLTP |
| Cache và trạng thái truy cập nhanh | **Memorystore** | Tăng tốc độ truy cập; dữ liệu nguồn quan trọng vẫn cần nơi lưu bền vững |
| Phân phối sự kiện bất đồng bộ | **Pub/Sub** | Thiết kế consumer idempotent, retry và xử lý thông điệp trùng lặp |
| Hàng đợi tác vụ HTTP cần điều tiết thực thi | **Cloud Tasks** | Phù hợp giao việc có kiểm soát tốc độ/retry tới worker |
| Lịch định kỳ | **Cloud Scheduler** | Kích hoạt công việc đúng lịch; phối hợp Cloud Run jobs khi công việc cần hoàn tất theo đợt |

**Phân biệt OLTP và OLAP:** Cloud SQL/Spanner xử lý giao dịch ứng dụng tùy đặc tính; BigQuery dành cho truy vấn phân tích. Đừng chuyển toàn bộ thao tác ghi/cập nhật từng đơn hàng sang BigQuery chỉ vì dữ liệu có thể trở nên lớn.

**Phân biệt Pub/Sub và Cloud Tasks:** Pub/Sub phù hợp phát sự kiện cho một hoặc nhiều consumer; Cloud Tasks phù hợp xếp hàng và điều tiết những lệnh gọi tác vụ cụ thể. Với cả hai, retry có thể làm xử lý lặp lại, nên lưu khóa idempotency hoặc áp dụng cơ chế chống ghi trùng khi cần.

## 6. Tình huống: xây dựng hệ thống đơn hàng trực tuyến

### 6.1. Yêu cầu ban đầu

Một nhóm phát triển xây dựng API đặt hàng, giao diện web, nhập dữ liệu sản phẩm mỗi đêm và gửi thông báo khi đơn hàng thành công. Tải tăng mạnh khi có chiến dịch, đội ngũ nhỏ, không cần tùy chỉnh kernel hay API Kubernetes. Dữ liệu đơn hàng cần giao dịch SQL, ảnh sản phẩm cần lưu bền vững.

Một thiết kế khởi đầu hợp lý:

- **Cloud Run service** chạy API/container, autoscale theo lưu lượng, áp dụng xác thực cho các endpoint cần bảo vệ.
- **Cloud SQL for PostgreSQL** chứa đơn hàng và các giao dịch; chọn HA, backup, khôi phục theo mục tiêu nghiệp vụ.
- **Cloud Storage** lưu ảnh và tệp xuất; ứng dụng chỉ lưu tham chiếu object trong DB.
- **Pub/Sub** truyền sự kiện `OrderCreated` tới consumer gửi thông báo; consumer chống xử lý trùng lặp.
- **Cloud Scheduler + Cloud Run jobs** thực hiện nhập dữ liệu theo lịch; job phải an toàn khi chạy lại.
- **Cloud Logging / Cloud Monitoring** cung cấp log, metric và cảnh báo; **Cloud Billing budgets** cảnh báo ngân sách.

~~~mermaid
flowchart LR
    User["Người dùng"] --> Api["Cloud Run: Orders API"]
    Api --> Db[("Cloud SQL PostgreSQL")]
    Api --> Obj[("Cloud Storage")]
    Api --> Topic["Pub/Sub: OrderCreated"]
    Topic --> Consumer["Cloud Run: Consumer"]
    Cron["Cloud Scheduler"] --> Job["Cloud Run Job: Nhập dữ liệu"]
    Job --> Db
    Api -. "Log / metric" .-> Obs["Cloud Logging + Monitoring"]
    Consumer -. "Log / metric" .-> Obs
    Job -. "Log / metric" .-> Obs
~~~

**Đây là kiến trúc minh họa, chưa phải sơ đồ mạng sản xuất.** Cần bổ sung lựa chọn vùng, ingress, load balancing/WAF nếu có, phương thức xác thực, kết nối Cloud SQL, quyền service account, Secret Manager, backup và quy trình khôi phục.

### 6.2. Vì sao chọn Cloud Run ở điểm xuất phát?

API có thể chạy trong container, không cần node Kubernetes và biến động lưu lượng theo chiến dịch. Cloud Run giảm công quản trị VM/cluster và hỗ trợ tự mở rộng theo cấu hình. Cloud SQL đáp ứng giao dịch quan hệ; Cloud Storage giữ object ngoài vòng đời instance.

Tuy vậy, **khả năng mở rộng API không đồng nghĩa cơ sở dữ liệu cũng mở rộng vô hạn**. Khi tăng số instance/concurrency phải kiểm soát connection pool, giới hạn kết nối của DB, truy vấn tốn tài nguyên và số lượng consumer. Hãy kiểm thử tải, đặt giới hạn instance thích hợp và theo dõi p95/p99 latency cùng lỗi DB.

### 6.3. Khi nào đổi phương án?

- **Chuyển sang Compute Engine:** nhà cung cấp phần mềm bắt buộc OS/driver đặc biệt hoặc dịch vụ cần mô hình VM lâu dài.
- **Chuyển sang GKE:** nhiều đội đã chuẩn hóa Kubernetes, cần operator/controller, chính sách workload hoặc cấu trúc cluster mà Cloud Run không đáp ứng.
- **Đánh giá App Engine:** ứng dụng khớp runtime và cách quản lý version/traffic của App Engine; đội ngũ muốn vận hành theo mô hình PaaS đó.
- **Đánh giá Spanner/AlloyDB:** khi yêu cầu giao dịch, quy mô, phân tán hoặc đặc tính PostgreSQL vượt giới hạn phương án hiện tại và đã có số liệu chứng minh nhu cầu.

Chuyển nền tảng chỉ nên thực hiện sau khi quan sát bottleneck, ràng buộc kỹ thuật và tổng chi phí chuyển đổi.

## 7. Triển khai minh họa một API lên Cloud Run

Giả sử đã có container image `orders-api:1.0.0` trong **Artifact Registry**, project và API cần thiết đã được cấu hình, cùng một service account dành riêng cho dịch vụ. Có thể triển khai từ Cloud Shell hoặc môi trường đã thiết lập `gcloud`:

~~~bash
gcloud run deploy orders-api \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:1.0.0 \
  --region=asia-southeast1 \
  --service-account=orders-api@PROJECT_ID.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --min-instances=0 \
  --max-instances=10 \
  --concurrency=40 \
  --timeout=60s
~~~

Thay `PROJECT_ID` bằng ID project thật. Repo image, service account và các quyền phù hợp phải **tồn tại trước**; nếu API cần truy cập Cloud SQL, Cloud Storage hoặc Pub/Sub, cấp quyền IAM tối thiểu cho danh tính chạy dịch vụ và cấu hình kết nối tương ứng. Lệnh trên bảo vệ truy cập bằng cơ chế xác thực của Cloud Run; một client muốn gọi dịch vụ cần danh tính và quyền gọi phù hợp.

Các con số `10` instance, `40` request đồng thời/instance và `60s` timeout chỉ là **giả định thực hành**, không phải cấu hình tối ưu cho mọi API. Thử nghiệm tải thực tế phải xác nhận bộ nhớ, CPU, giới hạn kết nối, timeout, tốc độ phản hồi và số lần retry. Chú ý không lưu dữ liệu đơn hàng trong filesystem tạm thời của container.

Nếu workload là nhập dữ liệu theo lịch, nên xem **Cloud Run jobs** thay vì cố giữ một HTTP request mở cho toàn bộ batch. Nếu hành vi là phản ứng với sự kiện nhỏ, đánh giá **Cloud Run functions** hoặc Cloud Run service được kích hoạt qua cơ chế sự kiện phù hợp.

## 8. Bảo mật, mạng và tổ chức tài nguyên

Việc chọn ít vận hành hơn **không chuyển giao trách nhiệm bảo vệ dữ liệu ứng dụng**. Thiết kế tối thiểu cần gồm:

1. **Ranh giới tổ chức/project:** phân chia project theo môi trường và phạm vi quản trị; áp dụng IAM ở mức phù hợp, tránh cấp quyền toàn project cho mọi service.
2. **Danh tính workload:** mỗi service dùng service account riêng, chỉ có quyền cần thiết; ưu tiên danh tính ngắn hạn và tích hợp IAM thay vì lưu khóa service account dài hạn trong code.
3. **Ingress và egress:** xác định API công khai hay riêng tư, kiểm tra hướng truy cập VPC, DNS, firewall và kết nối đến database private. Cloud Run cần cấu hình đường ra VPC thích hợp khi truy cập tài nguyên private.
4. **Bí mật và dữ liệu:** quản lý credentials bằng **Secret Manager** hoặc cơ chế phù hợp; cấu hình mã hóa, quyền bucket, retention, audit và chính sách backup.
5. **Chuỗi triển khai:** xây dựng image qua pipeline, lưu tại Artifact Registry, quét/phê duyệt artifact theo chính sách, triển khai có kiểm soát và có kế hoạch rollback.
6. **Quan sát và sự cố:** liên kết log có cấu trúc, metric, trace, cảnh báo, SLO và runbook; diễn tập phục hồi dữ liệu.

Ví dụ Cloud Run bị cấu hình công khai khi API chỉ dành cho nội bộ là **lỗi quản trị truy cập** dù máy chủ do Google vận hành. Ngược lại, một VM được patch đầy đủ vẫn có thể không an toàn nếu firewall hoặc IAM cấp quyền quá rộng.

## 9. Độ tin cậy và chi phí: so sánh toàn hệ thống

### 9.1. Độ tin cậy

Cần xác định **SLO** (mục tiêu chất lượng), **RTO** (thời gian khôi phục cho phép) và **RPO** (mức mất dữ liệu tối đa chấp nhận được) trước khi chốt kiến trúc. Tự động mở rộng chỉ giải quyết một phần khả năng chịu tải; còn phải xét:

- **Lỗi vùng/zone:** vùng đặt workload, khả năng phân tán, failover và đường truy cập DB.
- **State và giao dịch:** backup có thể khôi phục thật, migration/schema rollback và xác nhận tính nhất quán.
- **Độ trễ khi scale:** cold start của workload theo request, khởi tạo pool DB, warm-up và ngưỡng concurrency.
- **Sự kiện bất đồng bộ:** retry, dead-letter handling khi phù hợp, idempotency, thứ tự xử lý nếu nghiệp vụ yêu cầu.
- **Phụ thuộc bên ngoài:** timeout, exponential backoff có giới hạn, circuit breaker và khả năng suy giảm chức năng có kiểm soát.

Không nên tuyên bố kiến trúc “high availability” chỉ vì chọn dịch vụ managed. Nhiều tính năng HA/backup/replication phụ thuộc vào tier, vùng và cấu hình thực tế.

### 9.2. Chi phí

Tổng chi phí sở hữu gồm **compute + database + storage + network egress + log/monitoring + backup + thời gian vận hành và sự cố**. Với cùng ứng dụng:

| Lựa chọn | Nguồn chi phí cần theo dõi | Rủi ro dễ bỏ sót |
|---|---|---|
| Compute Engine | VM chạy theo cấu hình, đĩa, địa chỉ IP/mạng, load balancer | VM nhàn rỗi vẫn phát sinh phí, patch và HA cần công vận hành |
| GKE | Tài nguyên workload/node hoặc cơ chế tính phí của mode, cluster, mạng và lưu trữ | Chừa dư capacity, overhead Kubernetes, addon và vận hành |
| App Engine | Tài nguyên/instance và cơ chế tính phí theo môi trường | Số instance, cấu hình scale và dịch vụ phụ trợ |
| Cloud Run | CPU, bộ nhớ, request và cấu hình billing/instance theo loại workload | Min instances, concurrency kém hiệu quả, egress, DB không scale theo API |
| Cloud SQL và dịch vụ dữ liệu | Instance/capacity, lưu trữ, backup, I/O và mạng tùy dịch vụ | DB và backup vẫn có chi phí khi API ít request |

Đừng kết luận serverless luôn rẻ hơn VM: workload có lưu lượng liên tục và yêu cầu tài nguyên ổn định có thể cho kết quả khác. Hãy lập **hai đến ba phương án theo lưu lượng đo được**, xem đơn giá hiện hành bằng công cụ định giá của Google Cloud, gắn nhãn tài nguyên, thiết lập budget/alert và rà lại định kỳ.

## 10. Các mẫu quyết định và sai lầm thường gặp

| Tình huống | Điểm xuất phát hợp lý | Điều cần kiểm chứng |
|---|---|---|
| Ứng dụng Java cũ cần cấu hình OS, agent đặc thù | Compute Engine | Khả năng đóng gói lại và chi phí vận hành VM |
| REST API stateless, tải biến động, đóng gói container | Cloud Run | Timeout, cold start, pool kết nối và giới hạn scale |
| Nhiều service cần Kubernetes operator, CRD, policy riêng | GKE Standard hoặc Autopilot | Tính tương thích workload, kỹ năng Kubernetes, yêu cầu node |
| Web app hợp runtime App Engine, muốn phiên bản và phân luồng traffic | App Engine | Giới hạn runtime và môi trường chạy |
| Hàm nhỏ xử lý upload hoặc sự kiện | Cloud Run functions | Trigger, retry, quyền truy cập và idempotency |
| Báo cáo tổng hợp dữ liệu lớn | BigQuery kết hợp pipeline nạp dữ liệu | Mẫu truy vấn, độ trễ cập nhật và chi phí xử lý |
| Đơn hàng giao dịch SQL | Cloud SQL, rồi đánh giá lựa chọn khác khi có số liệu | Khả năng chịu tải, backup, HA và mô hình truy cập |

Một số **anti-pattern** đáng tránh:

- Chọn GKE chỉ vì dự án có microservice, trong khi không cần tính năng Kubernetes.
- Dùng VM để tự cài database mà chưa xem xét tính năng backup, patch và HA của dịch vụ managed.
- Xem Cloud Run là nơi lưu dữ liệu bền vững trong ổ đĩa cục bộ của instance.
- Cho phép autoscale compute không giới hạn trong khi Cloud SQL có giới hạn kết nối.
- Cho rằng mọi message chỉ xử lý đúng một lần; bỏ qua idempotency và retry.
- Bật truy cập công khai hoặc cấp IAM rộng vì nghĩ nền tảng sẽ tự bảo vệ toàn bộ ứng dụng.
- So sánh phương án chỉ theo đơn giá compute, bỏ qua vận hành, mạng và dữ liệu.

## 11. Bài tập thiết kế

**Bài toán:** Một công ty cần triển khai hệ thống hỗ trợ khách hàng gồm API Java, giao diện web, tệp đính kèm, dữ liệu ticket quan hệ và job gửi email theo lịch. Lượng truy cập tăng đột biến vào giờ hành chính. Đội có ba lập trình viên, chưa có chuyên gia Kubernetes; dữ liệu không được mất quá mức RPO do nghiệp vụ xác định.

Hãy đề xuất:

1. Lớp tính toán cho API/web và một phương án thay thế, giải thích theo quyền kiểm soát, kiểu tải và năng lực vận hành.
2. Nơi lưu ticket và tệp đính kèm, cùng chính sách backup/khôi phục sẽ kiểm tra.
3. Phương thức chạy job theo lịch và xử lý retry an toàn.
4. Cách chia project/môi trường, IAM/service account, ingress và kết nối database.
5. Ba tín hiệu vận hành và ba nguồn chi phí quan trọng cần theo dõi.
6. Điều kiện có thể khiến nhóm chuyển từ giải pháp khởi đầu sang GKE hoặc Compute Engine.

**Gợi ý tự đối chiếu:** Một lời giải có cơ sở có thể bắt đầu từ **Cloud Run + Cloud SQL + Cloud Storage + Cloud Scheduler/Cloud Run jobs**, bổ sung monitoring, backup và quyền IAM tối thiểu. Chuyển sang GKE/VM phải được giải thích bằng ràng buộc thật. Không có điểm cộng cho việc chọn nhiều dịch vụ hơn.

## 12. Checklist trước khi chốt kiến trúc

- [ ] Đã ghi rõ workload (HTTP, event, batch, stateful), nhu cầu OS/Kubernetes và các giới hạn runtime.
- [ ] Đã phân tách compute khỏi dữ liệu bền vững, chọn đúng dịch vụ cho giao dịch, object, phân tích và sự kiện.
- [ ] Đã mô tả trách nhiệm của đội đối với ứng dụng, IAM, secret, mạng, backup và khôi phục.
- [ ] Đã xác định SLO, RTO, RPO và thử nghiệm scale, lỗi, retry, khôi phục DB.
- [ ] Đã so sánh tổng chi phí theo tải dự kiến và đặt cảnh báo ngân sách.
- [ ] Đã ghi rõ giả định, điểm cần benchmark và điều kiện đổi kiến trúc.

**Nguyên tắc cuối cùng:** Chọn mức trừu tượng **cao nhất đáp ứng được các ràng buộc thực tế** và đội ngũ có thể vận hành tin cậy; kiểm chứng bằng thử nghiệm, dữ liệu tải, bảo mật và chi phí. Đây là cơ sở để tiếp tục học cách tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, storage/database và tự động hóa triển khai trên Google Cloud.
