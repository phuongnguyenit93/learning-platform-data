# VPC Service Controls và xây dựng service perimeter

Khi doanh nghiệp lưu dữ liệu đơn hàng trên Cloud Storage hoặc phân tích dữ liệu khách hàng trong BigQuery, **IAM** quyết định danh tính nào được phép đọc hay sửa dữ liệu. Tuy nhiên, nếu một credential có quyền bị đánh cắp, người sở hữu credential đó có thể tìm cách gọi API từ môi trường không được tin cậy hoặc sao chép dữ liệu sang một project khác. **VPC Service Controls (VPC SC)** bổ sung một lớp bảo vệ: tạo **service perimeter** quanh các tài nguyên Google Cloud và kiểm soát những lời gọi API đi qua ranh giới đó.

Bài học thuộc chương **Bảo mật và truy cập mạng** trong mô-đun `CLOUD_PROVIDERS_GCP`. Sau khi học tổ chức project, IAM và VPC, người học có thể áp dụng kiến thức này khi xây dựng hệ thống với Compute Engine, GKE, Cloud Run, Cloud Storage, BigQuery và cơ sở dữ liệu; qua đó chọn dịch vụ phù hợp, bảo vệ dữ liệu, kiểm soát phát hành và theo dõi độ tin cậy cùng chi phí.

VPC Service Controls **không phải firewall mạng**, không phải lớp thay thế IAM và cũng không hỗ trợ mọi Google Cloud API. Bài viết hướng dẫn mô hình thiết kế, quy trình triển khai bằng **dry-run trước khi enforced**, cách định nghĩa ingress/egress và kỹ thuật xử lý lỗi mà không vô tình làm gián đoạn workload.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích rủi ro rò rỉ dữ liệu mà VPC Service Controls giúp giảm thiểu và các giới hạn còn lại.
2. Phân biệt **access policy**, **service perimeter**, **restricted services**, **protected resources**, **access levels**, **ingress/egress rules** và **VPC accessible services**.
3. Thiết kế perimeter cho một hoặc nhiều Google Cloud project, hiểu tác động tới ứng dụng và CI/CD.
4. Nhận biết khi nào yêu cầu phải vượt ranh giới và cách chỉ mở đúng danh tính, nguồn, dịch vụ, phương thức, đích.
5. Thiết kế truy cập riêng tới Google APIs với `restricted.googleapis.com` khi phù hợp.
6. Tạo cấu hình dry-run, đọc violation logs và xây dựng tiêu chí chuyển sang enforced.
7. Chẩn đoán lỗi `403` liên quan perimeter mà không nhầm với lỗi IAM, DNS, firewall hoặc quota.
8. Lập checklist vận hành, thay đổi và khôi phục an toàn cho môi trường production.

## 1. Vì sao IAM không phải lớp bảo vệ dữ liệu duy nhất?

Giả sử nhóm Commerce có:

- Project `commerce-secure` chứa bucket `order-exports` và tập dữ liệu BigQuery nhạy cảm.
- Service account `orders-etl@commerce-secure.iam.gserviceaccount.com` được IAM cấp quyền đọc dữ liệu cần thiết.
- Project `experiments-sandbox` chỉ dùng cho thử nghiệm, nằm ngoài vùng dữ liệu nhạy cảm.
- Một đối tượng không được phép lấy được access token còn hiệu lực của service account ETL.

Nếu chỉ dựa trên IAM, đối tượng đó có thể thử sử dụng quyền đã được cấp từ một nơi không tin cậy. VPC Service Controls có thể giúp chặn những lời gọi tới **dịch vụ được bảo vệ** hoặc những hành vi vượt **service perimeter** không phù hợp với policy.

~~~mermaid
flowchart LR
    O["Client không được tin cậy<br/>hoặc project sandbox"]
    P["Service perimeter: data-secure"]
    S["Project: commerce-secure"]
    G["Cloud Storage / BigQuery<br/>restricted services"]
    W["Workload hợp lệ<br/>trong perimeter"]
    O -->|"Không khớp ingress policy"| X["Bị từ chối bởi VPC SC"]
    W -->|"Yêu cầu hợp lệ"| P
    P --> S --> G
~~~

Điều cần nhấn mạnh:

- **IAM** kiểm tra danh tính và permission trên tài nguyên.
- **VPC SC** kiểm soát ranh giới truy cập đối với **API/dịch vụ được hỗ trợ và được cấu hình hạn chế**.
- **VPC firewall, routing, DNS, TLS** kiểm soát hoặc bảo đảm đường truyền ở lớp mạng và ứng dụng.
- **Application security, data classification, audit và DLP** vẫn cần thiết để bảo vệ dữ liệu toàn diện.

**Cảnh báo:** Perimeter không bảo đảm ngăn mọi hình thức rò rỉ dữ liệu. Ví dụ, một workload được phép đọc dữ liệu có thể đưa nội dung đã đọc đến một đích ngoài qua kênh không được VPC SC kiểm soát. Vì thế cần kết hợp kiểm soát egress mạng, proxy, IAM tối thiểu, logging và quy trình ứng phó sự cố.

## 2. VPC Service Controls bảo vệ cái gì?

VPC SC cho phép tạo **ranh giới bảo mật logic** quanh những Google Cloud resources thuộc phạm vi được cấu hình. Khi lời gọi API liên quan tới dịch vụ đã đặt trong danh sách **restricted services**, chính sách perimeter được đánh giá để xác định yêu cầu có được vượt ranh giới hay không.

### 2.1. Các thành phần cốt lõi

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| **Access policy** | Cấp tổ chức chứa các access levels và service perimeters; quản lý bởi Access Context Manager | Policy của organization Atlas |
| **Regular service perimeter** | Xác định những project hoặc VPC network được bảo vệ và các dịch vụ cần hạn chế | `data-secure` |
| **Protected resources** | Project hoặc VPC network được khai báo thuộc perimeter theo tính năng hỗ trợ | `projects/111111111111` |
| **Restricted services** | Danh sách API của những sản phẩm tích hợp VPC SC cần kiểm soát ở ranh giới | `storage.googleapis.com`, `bigquery.googleapis.com` |
| **Access level** | Điều kiện truy cập theo context, chẳng hạn nguồn IP, thuộc tính thiết bị hoặc danh tính theo khả năng hỗ trợ | Truy cập từ môi trường được doanh nghiệp duyệt |
| **Ingress policy** | Quy định API client **bên ngoài** được phép gọi tài nguyên **bên trong** perimeter bằng hoạt động nào | Partner uploader ghi object vào bucket |
| **Egress policy** | Quy định yêu cầu liên quan nguồn **bên trong** đến tài nguyên **bên ngoài** perimeter | Job được phép ghi dữ liệu tổng hợp sang project báo cáo |
| **VPC accessible services** | Hạn chế những Google APIs được truy cập từ VPC networks ở trong perimeter | Chỉ các dịch vụ được phê duyệt |
| **Enforced configuration** | Chính sách chặn yêu cầu vi phạm | Chặn API call không được phép |
| **Dry-run configuration** | Đánh giá chính sách dự kiến, ghi violation nhưng không chặn vì bản dry-run | Thử tác động trước production |

### 2.2. Scope của perimeter và resource hierarchy

~~~mermaid
flowchart TD
    O["Organization Atlas<br/>Access Context Manager policy"]
    F["Folder Production"]
    P["Project commerce-secure<br/>number: 111111111111"]
    Q["Project analytics-secure<br/>number: 222222222222"]
    X["Project experiments-sandbox<br/>ngoài perimeter"]
    SP["Regular perimeter: data-secure"]
    O --> F
    F --> P
    F --> Q
    O --> X
    SP -. "Bảo vệ theo membership đã cấu hình" .-> P
    SP -. "Bảo vệ theo membership đã cấu hình" .-> Q
~~~

**Perimeter không đơn giản là một folder IAM.** Dù sơ đồ organization/folder giúp quản trị, membership của perimeter phải được xác định theo **project number** hoặc VPC network full resource name theo khả năng hỗ trợ. Một project di chuyển giữa folders không nên được giả định sẽ tự vào/ra perimeter theo cách tương đương với kế thừa IAM.

Trong một access policy, project thường chỉ thuộc **một regular perimeter trong cấu hình enforced** và tối đa một regular perimeter trong cấu hình dry-run tương ứng. Khi đưa project đang sử dụng vào một perimeter mới, phải kiểm tra membership hiện có và kế hoạch di chuyển; tránh xung đột hoặc thay đổi ngoài dự kiến.

### 2.3. Protected service khác với enabled service

Bật Cloud Storage API trên project là hành động quản lý **Service Usage**. Thêm `storage.googleapis.com` vào **restricted services** là hành động yêu cầu VPC SC áp dụng chính sách ranh giới đối với API được tích hợp. Hai việc không thay thế nhau.

**Đừng suy đoán tất cả sản phẩm GCP đều được VPC SC bảo vệ.** Danh sách và các hạn chế tích hợp thay đổi theo dịch vụ và thời gian. Trước khi triển khai, kiểm tra [Supported products and limitations](https://cloud.google.com/vpc-service-controls/docs/supported-products) cho từng API. Một sản phẩm có tích hợp cũng có thể có phương thức, tác vụ hoặc luồng tích hợp bị giới hạn.

## 3. Khi một lời gọi bị chặn: vị trí nguồn, đích và dịch vụ

Hãy xem ba tình huống:

| Luồng | Ý nghĩa từ góc nhìn perimeter | Cách thiết kế |
| --- | --- | --- |
| ETL chạy trong project `commerce-secure` đọc bucket trong cùng perimeter | Truy cập nội bộ cùng ranh giới với dịch vụ được bảo vệ | IAM và policy liên quan vẫn phải cho phép |
| Laptop bên ngoài perimeter dùng `gcloud storage` đọc bucket trong perimeter | **Ingress**: client bên ngoài truy cập tài nguyên bên trong | Access level hoặc ingress rule hẹp, kèm IAM |
| Job trong perimeter ghi kết quả sang project `experiments-sandbox` ngoài perimeter | **Egress**: từ nguồn/tài nguyên bên trong ra tài nguyên ngoài | Egress rule phù hợp và kiểm soát nguồn/đích |

**Ingress và egress của VPC SC không được định nghĩa đơn giản theo chiều di chuyển byte dữ liệu.** Chúng mô tả chiều truy cập và mối quan hệ của API client, resource với ranh giới. Chẳng hạn **đọc** object từ trong perimeter bởi client bên ngoài vẫn là ingress; **ghi** dữ liệu sang một project ngoài perimeter có thể là egress.

### 3.1. Lời gọi liên quan nhiều tài nguyên

Một lệnh copy object từ bucket trong perimeter A sang bucket ngoài perimeter A có thể liên quan **hai tài nguyên và một API method**. Phải xét policy theo **toàn bộ các tài nguyên tham gia**.

Khi đích nằm trong **perimeter B khác**, có thể cần:

- **Egress rule** thích hợp của perimeter A.
- **Ingress rule** thích hợp của perimeter B.
- Thêm egress/ingress liên quan nếu API thao tác trên nhiều tài nguyên hoặc các hướng truy cập khác nhau.
- IAM cho service account, dữ liệu nguồn và đích; VPC SC không tự cấp permission.

~~~mermaid
flowchart LR
    A["Perimeter A<br/>Project dữ liệu nguồn"]
    EA["Egress policy A"]
    IB["Ingress policy B"]
    B["Perimeter B<br/>Project đích"]
    A --> EA --> IB --> B
    IAM["IAM và chính sách dịch vụ"]
    IAM -. "Vẫn được kiểm tra" .-> B
~~~

Một rule egress tại A **không tự ghi đè** ingress policy của B. Khi thiết kế chia sẻ dữ liệu giữa các nhóm, phải thống nhất chính sách của cả hai bên.

## 4. Perimeter và ba lớp bảo vệ khác

| Cơ chế | Câu hỏi nó trả lời | Không nên nhầm với |
| --- | --- | --- |
| **IAM allow/deny** | Danh tính có quyền gọi API/hành động trên resource không? | Biên truy cập theo nguồn–đích của VPC SC |
| **VPC Service Controls** | Yêu cầu tới **restricted service** có được đi qua biên logic không? | Firewall TCP/UDP thông thường |
| **VPC firewall rules** | Gói mạng từ nguồn nào đến đích/cổng nào được phép? | Quyền đọc object Cloud Storage |
| **Cloud NAT** | Tài nguyên private có dịch IP để kết nối ra Internet được không? | Danh sách restricted services |
| **Private Google Access / Private Service Connect** | Làm sao workload private tới Google APIs qua đường riêng phù hợp? | VPC SC access policy |
| **Cloud Armor** | HTTP client traffic đến endpoint được bảo vệ có bị chặn theo security policy không? | Quản lý ingress/egress của Google API services |
| **Organization Policy** | Loại cấu hình hạ tầng nào tổ chức cho phép? | Perimeter kiểm soát API data boundary |
| **Cloud Audit Logs** | Những hành động/vi phạm nào đã được ghi nhận? | Cấu hình quyền truy cập |

**Một lời gọi Cloud Storage thành công thường cần cả IAM hợp lệ, đường mạng hoạt động và VPC SC cho phép nếu dịch vụ/tài nguyên thuộc perimeter.** Nhận `403` không đủ để kết luận nguyên nhân thuộc một lớp cụ thể.

## 5. Enforced và dry-run: chọn cách triển khai an toàn

VPC SC có hai cách đánh giá cấu hình:

### 5.1. Enforced mode

Cấu hình **enforced** chặn request tới dịch vụ được bảo vệ khi vi phạm perimeter. Ví dụ máy phát triển ngoài perimeter không phù hợp ingress policy có thể nhận:

~~~text
Error 403: Request is prohibited by organization's policy.
~~~

Với production, bật enforced thiếu chuẩn bị có thể làm hỏng pipeline CI/CD, truy vấn BigQuery từ notebook, thao tác Cloud Storage từ ứng dụng khác project, export logging hoặc quy trình sao lưu.

### 5.2. Dry-run mode

**Dry-run** cho phép mô phỏng cấu hình: ghi log các request **sẽ bị từ chối nếu policy được enforce** nhưng **không tự chặn** vì chính cấu hình dry-run đó.

~~~mermaid
flowchart TD
    A["Đề xuất một perimeter mới"] --> B["Tạo cấu hình dry-run"]
    B --> C["Chạy workload và các use case thực tế"]
    C --> D["Thu thập VPC SC dry-run violations"]
    D --> E["Phân loại traffic hợp lệ / không hợp lệ"]
    E --> F{"Có call hợp lệ bị dự báo chặn?"}
    F -->|Có| G["Sửa thiết kế, ingress/egress, access levels"]
    G --> C
    F -->|Không| H["Phê duyệt thay đổi, lên kế hoạch enforce"]
    H --> I["Theo dõi 403/violation sau khi enforce"]
~~~

Cần hiểu rõ: một perimeter có thể có cấu hình **enforced và dry-run** song song. Dry-run dùng để thử **thay đổi so với** enforced; những yêu cầu đã bị cấu hình enforced chặn sẽ không “được thả qua” chỉ vì dry-run cho phép. Access levels không có bản dry-run riêng: nếu muốn thử điều kiện access level mới, hãy tạo access level riêng rồi tham chiếu nó trong dry-run.

**Dry-run an toàn hơn nhưng không thay thế kiểm thử chức năng.** Một job chỉ chạy cuối tháng, luồng disaster recovery, service agent hoặc pipeline ít dùng có thể không phát sinh log trong giai đoạn dry-run ngắn.

## 6. Thiết kế perimeter cho hệ thống dữ liệu

Giả sử doanh nghiệp có bốn nhóm tài nguyên:

| Project giả định | Vai trò | Lựa chọn thiết kế |
| --- | --- | --- |
| `commerce-secure` | Bucket và BigQuery chứa dữ liệu nhạy cảm | Trong perimeter `data-secure` |
| `analytics-secure` | ETL và BigQuery báo cáo nội bộ | Trong cùng perimeter nếu phù hợp mức tin cậy |
| `ci-deploy` | Pipeline triển khai ngoài phạm vi dữ liệu | Ngoài perimeter; ingress rule hẹp nếu có API call hợp lệ |
| `experiments-sandbox` | Thử nghiệm không chứa dữ liệu thật | Ngoài perimeter; mặc định không được truy cập dữ liệu protected |

### 6.1. Thiết kế theo ranh giới tin cậy, không theo thói quen

Nếu hai project có cùng mức bảo vệ, trao đổi dữ liệu thường xuyên và cùng owner, đưa chúng vào cùng perimeter có thể giảm số cross-boundary rules. Nhưng không nên gom **mọi project của organization** vào một perimeter để tránh viết policy; điều đó có thể làm ranh giới bảo vệ mất ý nghĩa.

Một phương án:

~~~mermaid
flowchart TB
    subgraph DATA["Service perimeter data-secure"]
        P1["commerce-secure"]
        P2["analytics-secure"]
        S1["Cloud Storage"]
        S2["BigQuery"]
        P1 --> S1
        P2 --> S2
    end
    CI["CI/CD project hoặc provider ngoài"]
    DEV["Developer laptop"]
    EXP["experiments-sandbox"]
    CI -. "Ingress rule hạn chế" .-> DATA
    DEV -. "Chỉ nếu được phê duyệt" .-> DATA
    DATA -. "Egress chỉ cho luồng xuất được duyệt" .-> EXP
~~~

Các đường nét đứt trong sơ đồ là **khả năng được kiểm soát bằng policy**, không phải đường được cho phép mặc định.

### 6.2. Nhận diện mọi phụ thuộc trước khi enforce

Một project dữ liệu có thể phụ thuộc vào:

- Cloud Run/Compute Engine/GKE gọi Storage/BigQuery từ cùng hoặc khác project.
- BigQuery jobs, scheduled queries và dataset cross-project.
- Dataflow/Cloud Composer/managed services và các **service agents**.
- CI/CD pipeline, Terraform/GitOps, workload identity federation.
- Log sinks, security tooling, sao lưu/khôi phục và export dữ liệu.
- Nhân viên vận hành dùng Console, Cloud Shell, máy cá nhân hoặc VPN.
- API đến project bên ngoài hoặc dịch vụ không hỗ trợ VPC SC.

Với **managed services**, service agent và service-to-service calls có thể có cơ chế VPC SC riêng; phải đối chiếu giới hạn trong tài liệu sản phẩm. **Không tự thêm wildcard/ANY_IDENTITY để chữa mọi `403`**.

## 7. Ingress policy: cho phép nguồn ngoài đi vào có điều kiện

**Ingress rule** có hai phần chính:

- `ingressFrom`: **nguồn API client** và **danh tính** được phép.
- `ingressTo`: **restricted services/operations** và **tài nguyên đích trong perimeter**.

Các điều kiện ở hai phần đều phải phù hợp. Có thể có nhiều rules; một yêu cầu chỉ cần khớp một rule phù hợp trong tập ingress, đồng thời phải qua những lớp quyền khác.

### 7.1. Ví dụ ingress theo service account và project nguồn

Giả sử service account `partner-import@partner-ingest.iam.gserviceaccount.com` chạy trong project `partner-ingest` (project number `333333333333`), được phép **tạo object** ở một bucket thuộc project `commerce-secure` (project number `111111111111`). Ví dụ YAML **để minh họa rule**:

~~~yaml
- title: "partner-object-upload"
  ingressFrom:
    identities:
      - serviceAccount:partner-import@partner-ingest.iam.gserviceaccount.com
    sources:
      - resource: projects/333333333333
  ingressTo:
    resources:
      - projects/111111111111
    operations:
      - serviceName: storage.googleapis.com
        methodSelectors:
          - permission: storage.objects.create
~~~

Giá trị và permission cần kiểm tra tính hỗ trợ theo **VPC SC method restrictions** của dịch vụ. Nguồn service account còn phải có **IAM permission thật** để tạo object vào bucket, và ứng dụng phải chạy từ ngữ cảnh nguồn đúng. Rule không tự cấp `roles/storage.objectCreator`.

**Lưu ý:** Mẫu YAML này là nội dung bài học, **không phải file YAML được tạo tự động**; chỉ khi có quyền và quy trình phê duyệt mới đưa nó vào cấu hình perimeter thực tế.

### 7.2. Access levels trong ingress

Access levels được tạo trong **Access Context Manager**, có thể thể hiện điều kiện về IP nguồn, thiết bị hoặc ngữ cảnh theo hỗ trợ. Ingress rule có thể tham chiếu access level thay vì cho phép một source project.

Ví dụ cách diễn đạt chính sách:

> Chỉ cho phép các tài khoản người dùng cụ thể, từ nguồn mạng được phê duyệt và thỏa điều kiện access level, đọc dữ liệu của project protected qua API được cho phép.

**Không dùng `ANY_IDENTITY`, `accessLevel: "*"` và toàn bộ methods/resources chỉ để “tránh lỗi”.** Những giá trị này có thể mở ranh giới rộng hơn chủ ý. Nếu phải dùng ngoại lệ rộng để xử lý sự cố, hãy kiểm soát thời hạn và owner, sau đó thu hẹp ngay khi có thể.

### 7.3. Ingress không phải luật HTTP inbound

Ingress của VPC SC **không mở một cổng TCP** từ Internet tới VM, GKE Pod hay Cloud Run URL. Nó mô tả **khả năng gọi Google Cloud API thuộc phạm vi VPC SC** từ bên ngoài perimeter. Cổng 443 của một application load balancer vẫn phải được bảo vệ bằng kiến trúc ingress/network/app riêng.

## 8. Egress policy: kiểm soát yêu cầu liên quan tài nguyên ngoài perimeter

**Egress rule** mô tả:

- `egressFrom`: danh tính hoặc nguồn trong perimeter được phép thực hiện yêu cầu.
- `egressTo`: API/operation và những resource đích bên ngoài perimeter được phép.

Ví dụ ETL service account trong `analytics-secure` được phép **ghi object tổng hợp đã được kiểm duyệt** sang project báo cáo `finance-reports` (project number `444444444444`):

~~~yaml
- title: "publish-approved-reports"
  egressFrom:
    identities:
      - serviceAccount:etl-exporter@analytics-secure.iam.gserviceaccount.com
  egressTo:
    resources:
      - projects/444444444444
    operations:
      - serviceName: storage.googleapis.com
        methodSelectors:
          - permission: storage.objects.create
~~~

Ví dụ là một **policy ý tưởng theo principal, permission và target project**. Trong thực tế cần xác minh request có phát sinh các API/method phụ trợ khác không, dữ liệu có được phép xuất không và project đích thuộc perimeter nào.

Nếu `finance-reports` nằm trong **perimeter khác**, phải xem **ingress policy của perimeter nhận**. Ngoài VPC SC, IAM của bucket đích vẫn phải cấp quyền ghi phù hợp.

### 8.1. Rule không thay cơ chế duyệt dữ liệu

Egress rule cho phép **một loại lời gọi API**, không tự biết một object có chứa dữ liệu cá nhân, bí mật hoặc dữ liệu đã được tổng hợp an toàn hay chưa. Với dữ liệu nhạy cảm, cần kết hợp quy trình duyệt, phân loại dữ liệu, DLP và audit. Khi có khả năng, xuất qua pipeline được thiết kế sẵn và ít quyền thay vì cấp quyền ghi tới mọi bucket ngoài perimeter.

### 8.2. Perimeter bridges

Một số tài liệu/cấu hình hiện hữu có **perimeter bridge** cho những kịch bản trao đổi giữa perimeters. Với thiết kế mới, hãy cân nhắc **ingress/egress rules cụ thể** vì chúng giúp giới hạn danh tính, dịch vụ và hành động. Không dùng bridge như cách mở toàn bộ trao đổi mà không đánh giá hệ quả bảo mật và giới hạn sản phẩm hiện hành.

## 9. VPC accessible services: còn một lớp giới hạn API ở bên trong

**VPC accessible services** có thể giới hạn những Google APIs mà các client ở VPC network thuộc perimeter được truy cập, thay vì chỉ xem dịch vụ nào bị bảo vệ khi đi qua ranh giới.

Ví dụ nhóm bảo mật chọn chỉ cho các workload trong VPC sử dụng những API được phê duyệt, chẳng hạn Cloud Storage và Cloud Logging, nhằm giảm bề mặt truy cập ra các dịch vụ khác.

**Phân biệt:**

- **Restricted services:** những dịch vụ mà perimeter áp dụng các quy tắc bảo vệ qua biên.
- **VPC accessible services:** những dịch vụ client ở VPC trong perimeter được phép sử dụng theo chính sách bổ sung.

Không mặc định bật giới hạn VPC accessible services cho toàn bộ workload. Một ứng dụng có thể cần IAM Credentials API, Artifact Registry hoặc dịch vụ khác khi phát hành; nếu thiếu API trong allowlist, nó có thể gặp lỗi dù IAM đúng.

Các dịch vụ được cho phép nên được lập dựa trên **dependency inventory**, không chỉ nhìn hai API dữ liệu chính. Một số cơ chế cho phép biểu thức `RESTRICTED-SERVICES` để tham chiếu tập dịch vụ đã được restricted, nhưng cần xác minh điều kiện của tính năng.

## 10. Kết nối riêng với restricted.googleapis.com

Một perimeter logic không có nghĩa mọi gói tin tự chuyển sang đường mạng riêng. Nếu workload dùng private IP trong VPC muốn gọi Google APIs mà giảm khả năng đi qua những API ngoài phạm vi VPC SC, có thể thiết kế **Private Google Access** kết hợp **restricted VIP**.

### 10.1. Restricted VIP và private VIP

| DNS/VIP | IPv4 range | Mục đích điển hình |
| --- | --- | --- |
| `restricted.googleapis.com` | `199.36.153.4/30` | Truy cập các Google APIs/services hỗ trợ VPC SC qua đường riêng; chặn dịch vụ không được hỗ trợ trên restricted VIP |
| `private.googleapis.com` | `199.36.153.8/30` | Truy cập phần lớn Google APIs qua đường riêng, kể cả một số dịch vụ chưa hỗ trợ VPC SC |
| Endpoint mặc định `*.googleapis.com` | Phụ thuộc DNS/service | Không tự mang những giới hạn của restricted VIP |

**Restricted VIP không tự thay IAM hoặc ingress/egress policies.** Các request tới dịch vụ bị VPC SC bảo vệ vẫn chịu kiểm tra perimeter cho dù sử dụng endpoint khác; restricted VIP là **lớp giảm nguy cơ rò rỉ bổ sung** bằng cách hạn chế các API không hỗ trợ VPC SC trên đường đó.

Nếu workload bắt buộc dùng một dịch vụ không hỗ trợ VPC SC, `private.googleapis.com` hoặc Private Service Connect với `all-apis` có thể phù hợp, nhưng cần xem **service patterns** và các biện pháp bù trừ vì việc cho phép nhiều API ngoài VPC SC làm tăng bề mặt rủi ro.

### 10.2. Các phần cần cấu hình

Đối với VM có internal IP trong subnet private:

1. Bật **Private Google Access** cho subnet phù hợp.
2. Cấu hình **Cloud DNS private zone/response policy** theo tài liệu để các Google API domains cần thiết phân giải về `restricted.googleapis.com`.
3. Bảo đảm route tới `199.36.153.4/30` có next hop **default internet gateway** theo mô hình Google Cloud. Mặc dù tên next hop như vậy, lưu lượng tới restricted VIP vẫn đi trong mạng Google, không ra Internet công cộng.
4. Cho phép egress firewall phù hợp tới restricted VIP TCP 443 và những dải khác nếu tài liệu dịch vụ yêu cầu.
5. Kiểm tra DNS, route, TLS, identity/IAM và kết quả VPC SC.
6. Với truy cập hybrid qua Cloud VPN/Interconnect, xem quy trình **Private Google Access for on-premises hosts** tương ứng.

~~~mermaid
flowchart LR
    VM["Private VM/GKE workload"]
    DNS["Private DNS mapping<br/>*.googleapis.com"]
    VIP["restricted.googleapis.com<br/>199.36.153.4/30"]
    API["Supported Google APIs"]
    PER["VPC SC perimeter evaluation"]
    VM --> DNS --> VIP --> API
    API --> PER
~~~

**Không nhầm `default internet gateway` trong route với việc gửi request ra Internet công cộng.** Tuy nhiên, để khóa đường Internet khác, phải quản trị các route/firewall còn lại riêng. Không cắt toàn bộ default route khi chưa có đường phù hợp đến restricted VIP; nếu làm sai, workload có thể mất khả năng gọi Google APIs.

### 10.3. Cloud NAT không giải quyết tất cả

Cloud NAT giúp workload private có Internet egress theo cấu hình; nó **không tự bảo đảm chỉ gọi những Google APIs được VPC SC hỗ trợ**. Vì vậy, khi yêu cầu chính là bảo vệ dữ liệu qua Google APIs, hãy ưu tiên đánh giá restricted VIP, VPC egress controls, IAM và perimeter thay vì chỉ dựa vào NAT IP.

## 11. Áp dụng với Compute Engine, GKE, Cloud Run và CI/CD

| Loại workload | Cần kiểm tra về VPC SC | Điểm dễ bỏ sót |
| --- | --- | --- |
| **Compute Engine VM** | Project/VPC membership, danh tính VM, restricted services, đường DNS/VPC | VM có IAM đúng nhưng route/DNS sai hoặc không khớp perimeter |
| **GKE workload** | Project cluster, Workload Identity Federation, các API được gọi và nguồn mạng | KSA/IAM SA, service agents, artifact fetching, node/Pod egress |
| **Cloud Run** | Project service, VPC egress cấu hình, Google APIs và tích hợp sản phẩm | Không phải mọi request tới URL Cloud Run đều là một lời gọi API thuộc restricted services |
| **Cloud Storage** | Bucket project, principal, method `objects.get/create`, luồng cross-project | Copy object có thể chạm nhiều tài nguyên/perimeters |
| **BigQuery** | Project chạy job, datasets, kết nối/export qua dịch vụ liên quan | Jobs và dữ liệu nằm ở project khác nhau |
| **CI/CD/Terraform** | Vị trí runner, identity, API deploy và service agents | Pipeline ngoài perimeter có thể cần ingress rule phù hợp |
| **External developer/Cloud Shell** | Nguồn API client, access level, danh tính, API method | Truy vấn Console/CLI bị 403 dù chủ tài khoản có role IAM |
| **On-premises/hybrid** | Nguồn qua VPN/Interconnect, landing-zone VPC, IP context, Private Google Access | Network connectivity không tự cấp quyền perimeter |

### 11.1. Đừng nhầm ranh giới API với HTTP ingress ứng dụng

Một Cloud Run service có thể nhận request HTTP từ client theo **Cloud Run ingress settings** và IAM xác thực của chính service. VPC SC bảo vệ những API/tài nguyên được tích hợp và được restricted, **không mặc nhiên thay thế** kiểm soát URL ứng dụng, API Gateway, Cloud Armor hay HTTPS load balancer.

### 11.2. Service agents và hệ thống tự động

Nhiều dịch vụ managed có service agents hoặc sử dụng nhiều API khác nhau thay mặt bạn. Ví dụ pipeline gửi dữ liệu đến BigQuery có thể đọc object Cloud Storage từ project khác, ghi logs vào project tập trung và sử dụng key qua Cloud KMS. Nếu chỉ whitelist principal của ứng dụng chính, những luồng nền hợp lệ vẫn có thể bị chặn.

Lập **dependency map**: principal thực tế, nơi chạy, API methods, project nguồn–đích, điều kiện mạng, lịch chạy và owner của từng tích hợp. Không cấp `ANY_SERVICE_ACCOUNT` ở mọi nơi như một lối tắt.

## 12. Thực hành an toàn: chuẩn bị dry-run cho service perimeter

**Các lệnh ở phần này là ví dụ để chạy trong môi trường thử nghiệm có quyền quản trị tổ chức, không dành cho tài khoản học viên trên project tùy ý.** Tạo hoặc thay đổi service perimeter là thay đổi policy cấp tổ chức, có thể tác động nhiều project và gây sự cố nếu chọn nhầm project. Hãy có phê duyệt của team Cloud Security.

### 12.1. Kiểm tra quyền, access policy và project number

Access Context Manager được quản lý theo tổ chức. Bạn cần quyền quản lý service perimeters/Access Context Manager tương ứng và phải xác định đúng **access policy ID**.

~~~bash
# Xem identity và project CLI; không làm thay đổi IAM
gcloud auth list
gcloud config get-value project

# Liệt kê access policies bạn có quyền nhìn thấy
gcloud access-context-manager policies list

# Xem các perimeters thuộc một access policy
gcloud access-context-manager perimeters list \
  --policy=ACCESS_POLICY_ID
~~~

Với resource member, dùng **project number** trong chuỗi `projects/PROJECT_NUMBER`, **không dùng project ID tùy ý**. Trước khi triển khai, xác minh project hiện thuộc perimeter nào và liệu policy có cấu hình enforced/dry-run khác cần bảo tồn.

### 12.2. Mẫu tạo dry-run perimeter

Ví dụ giả định:

~~~text
Access policy ID: 123456789012
Perimeter name: CommerceDataTrial
Project numbers: 111111111111,222222222222
Restricted services: storage.googleapis.com,bigquery.googleapis.com
Mode: dry-run only
~~~

Lệnh minh họa:

~~~bash
gcloud access-context-manager perimeters dry-run create CommerceDataTrial \
  --perimeter-title="Commerce Data Trial" \
  --perimeter-type=regular \
  --perimeter-resources=projects/111111111111,projects/222222222222 \
  --perimeter-restricted-services=storage.googleapis.com,bigquery.googleapis.com \
  --policy=123456789012
~~~

Lệnh này **tạo cấu hình dry-run**; không tạo bucket/project hay service account. Tuy nhiên, nó vẫn **ghi vào Access Context Manager policy** và có thể bị từ chối nếu quyền, quota, membership hoặc tổ chức không phù hợp. Thực hiện chỉ khi được phê duyệt. Với access policy đã có enforced perimeter, hãy kiểm tra kế hoạch cập nhật **dry-run configuration** hiện có thay vì tạo thêm perimeter mới một cách tùy tiện.

**Tập dịch vụ bên trên chỉ là ví dụ phục vụ bài học**, không phải danh sách đủ để bảo vệ production. Tài liệu Google Cloud khuyến nghị xác định mọi supported services liên quan và các tích hợp phụ trợ trước khi enforce.

### 12.3. Kiểm tra cấu hình đã tạo

~~~bash
gcloud access-context-manager perimeters describe CommerceDataTrial \
  --policy=123456789012

gcloud access-context-manager perimeters list \
  --policy=123456789012
~~~

Trong cấu hình, phân biệt **`status`** (enforced config) với **`spec`** và **`useExplicitDryRunSpec`** (dry-run config/API), thay vì chỉ nhìn một field rồi suy luận chính sách đã được enforce hay chưa.

### 12.4. Thử các use case hợp lệ

Cho nhóm ứng dụng chạy một bộ tác vụ đại diện:

- VM/GKE/Cloud Run trong perimeter đọc object trong bucket protected.
- BigQuery job nội bộ đọc dữ liệu thuộc dự án được phê duyệt.
- Pipeline CI/CD thực hiện deploy hợp lệ.
- Developer chạy thao tác CLI được phép theo quy trình.
- Backup/restore, log sink và service agents hoạt động.
- Luồng gửi dữ liệu hợp lệ sang project bên ngoài được kiểm soát.

Sau đó, chủ sở hữu cùng nhóm Security xem các violation dry-run, phân loại luồng bắt buộc, đề xuất ingress/egress tối thiểu và lặp lại cho tới khi không còn vi phạm ngoài ý muốn trong phạm vi đã kiểm thử.

## 13. Đọc violation logs của VPC Service Controls

VPC SC cung cấp thông tin vi phạm qua **Cloud Audit Logs**, trong đó nhiều trường liên quan nằm ở `protoPayload.metadata`.

Một số trường cần xem:

| Trường metadata | Vai trò |
| --- | --- |
| `dryRun` | Cho biết đây là log đánh giá dry-run hay vi phạm enforced |
| `violationReason` | Lý do vi phạm perimeter |
| `resourceNames` | Những tài nguyên liên quan |
| `vpcServiceControlsUniqueId` | Mã định danh vi phạm để đối chiếu |
| `vpcServiceControlsTroubleshootToken` | Token phục vụ công cụ phân tích vi phạm |
| `securityPolicyInfo` | Thông tin perimeter/policy liên quan |
| `egressViolations` | Chi tiết những trường hợp egress bị vi phạm nếu có |

Trường còn lại có thể cung cấp principal, method, service, project hoặc nguồn truy cập, tùy service và cách log được ghi. Một số thông tin có thể bị ẩn/redacted vì lý do bảo mật hoặc quyền.

### 13.1. Lọc log dry-run

Trong **Logs Explorer**, dùng truy vấn khởi đầu:

~~~text
log_id("cloudaudit.googleapis.com/policy")
AND severity="ERROR"
AND protoPayload.metadata.dryRun=true
~~~

Hoặc với CLI:

~~~bash
gcloud logging read \
  'log_id("cloudaudit.googleapis.com/policy") AND severity="ERROR" AND protoPayload.metadata.dryRun=true' \
  --project=PROJECT_ID \
  --limit=50
~~~

Truy vấn cho kết quả tại **phạm vi logs bạn có quyền xem**. Một project có thể không hiển thị mọi vi phạm của toàn tổ chức. Với nhiều project, có thể dùng **aggregated log sink** vào đích bảo vệ và phân quyền phù hợp; việc xuất logs, BigQuery storage và queries có thể phát sinh chi phí.

### 13.2. Lọc vi phạm enforced

Nếu ứng dụng nhận lỗi 403 sau khi áp dụng policy, xem Policy Audit Logs và tìm violation reason. Trong hệ thống, từ ngữ lỗi thường gặp có thể liên quan:

- `RESOURCE_NOT_IN_SAME_SERVICE_PERIMETER`: các tài nguyên liên quan không cùng một perimeter trong một yêu cầu.
- Không khớp **ingress rule** hoặc **access level** cho client bên ngoài.
- Không khớp **egress rule** khi gọi tới resource bên ngoài.
- Thay đổi perimeter chưa hoàn tất propagation.

Tên mã lỗi và cấu trúc chi tiết có thể khác nhau theo dịch vụ/API và thời điểm; **không dùng một chuỗi log đơn lẻ làm nguồn xác định duy nhất**.

### 13.3. Trình tự xử lý violation

~~~mermaid
flowchart TD
    A["Có 403 hoặc dry-run violation"] --> B["Xác định service, API method, principal và source"]
    B --> C["Xác định project/resource đích, perimeter membership"]
    C --> D{"IAM và mạng đã đúng?"}
    D -->|Không| E["Sửa IAM/DNS/route/firewall theo nguyên nhân"]
    D -->|Có| F{"Ingress, egress hay cross-perimeter?"}
    F --> G["Kiểm tra rule từ → tới, permission và identity"]
    G --> H["Thử rule hẹp trong dry-run"]
    H --> I["Đánh giá rủi ro rồi phê duyệt enforced change"]
~~~

**Không chữa lỗi bằng cách xóa project khỏi perimeter, tắt VPC SC hoặc cho phép mọi principal** trừ khi đó là biện pháp ứng phó khẩn cấp đã được phê duyệt, có người chịu trách nhiệm và kế hoạch hoàn nguyên.

## 14. Phân biệt các lỗi 403: IAM, VPC SC và dịch vụ

Cùng một mã HTTP `403 PERMISSION_DENIED` có thể do nhiều nguyên nhân.

| Dấu hiệu | Khả năng | Cách kiểm tra |
| --- | --- | --- |
| Message nêu `organization's policy` và có VPC SC violation trong Policy Audit Logs | Bị service perimeter chặn | Xem ingress/egress, source context, membership, restricted service |
| Message nêu thiếu `storage.objects.get` hoặc quyền tương tự, không có dấu hiệu VPC SC | IAM thiếu permission hoặc policy deny | Xem IAM bindings, IAM Deny và Policy Troubleshooter |
| Không phân giải được hostname Google API | Cloud DNS/Private Google Access lỗi | DNS private zone, restricted VIP, resolver |
| TCP timeout thay vì HTTP response | Route, firewall, private connectivity, proxy/egress | VPC routes, firewall logs, Connectivity Tests |
| `401 UNAUTHENTICATED` | Credential/ADC/token không hợp lệ | Xác thực workload, service account, token |
| Service không hỗ trợ VPC SC qua restricted VIP | API bị chặn trên đường VIP | Kiểm tra supported products; thiết kế private VIP/PSC + compensating controls |
| Chỉ bị lỗi sau khi thay đổi policy | Propagation hoặc phạm vi rule sai | So sánh enforced/dry-run, thời điểm, rollback plan |
| Dữ liệu trong một project, BigQuery job trong project khác | Yêu cầu cross-project/multiple resources | Xác minh project job và dataset, ingress/egress hai phía |

Cấu hình service perimeter có thể mất thời gian để propagation. Google Cloud nêu việc cập nhật perimeter có thể cần **tới khoảng 30 phút** để có hiệu lực trên toàn hệ thống; không nên đánh giá trạng thái bảo vệ từ một lời gọi thử ngay sau thay đổi.

### 14.1. Tại sao “đăng nhập đúng tài khoản” vẫn lỗi?

Một developer có role `roles/storage.objectViewer` trên bucket nhưng đang chạy `gcloud` từ laptop ngoài perimeter. **IAM có thể cho phép**, trong khi **ingress policy không cho phép nguồn và danh tính đó**, nên request vẫn bị chặn. Phải phân tích đủ **identity + source context + method + resource + perimeter**, không chỉ tài khoản đăng nhập.

### 14.2. Tại sao “ứng dụng chạy trong cùng VPC” vẫn lỗi?

Có thể project hoặc VPC không thuộc đúng perimeter, gọi API đích không ở cùng perimeter, dùng service agent ngoài scope, hoặc request liên quan resource khác ngoài perimeter. **Cùng subnet/VPC hoặc có VPN** không tự chứng minh lời gọi được VPC SC chấp thuận.

## 15. Chuyển sang enforced có kiểm soát

Trước khi enforce perimeter production:

1. **Chốt phạm vi:** project numbers, VPC networks (nếu áp dụng), supported services, loại dữ liệu, owner.
2. **Chốt sơ đồ luồng API:** các workload, principal, tài nguyên trong/ngoài, method và hoạt động phát hành.
3. **Kiểm tra dry-run:** bao phủ ngày thường, job định kỳ, sự cố giả lập, backup/restore, CI/CD và quản trị.
4. **Thu hẹp ngoại lệ:** bỏ `ANY_IDENTITY`, `accessLevel: "*"` hoặc mọi API nếu không thật sự cần.
5. **Kiểm tra IAM/network:** VPC SC là lớp bổ sung, không tự sửa quyền hoặc đường mạng.
6. **Chuẩn bị giám sát:** logs, dashboard `403`, alerting, owner trực sự cố và quyền xem violations.
7. **Chuẩn bị rollback:** có thể điều chỉnh ingress/egress, quay lại policy trước khi thay đổi hoặc kế hoạch xử lý sự cố có phê duyệt.
8. **Thực hiện change management:** thống nhất thời gian, người phê duyệt và người xác nhận sau triển khai.
9. **Theo dõi sau khi enforce:** kiểm chứng các luồng đã duyệt và ghi nhận mọi denied request.
10. **Định kỳ review:** khi thêm project, thay đổi pipeline, service account hoặc tích hợp Google Cloud API.

**Không coi “không có dry-run violation” là bằng chứng hoàn toàn an toàn** nếu workload thực tế chưa được chạy trong giai đoạn quan sát.

### 15.1. Runbook khi một ứng dụng production bị chặn

- Ghi thời điểm, project, API method, principal, full resource name và request ID nếu có.
- Kiểm tra VPC SC violation logs, effective perimeter membership và cấu hình enforced.
- Xác định đó là luồng hợp lệ hay hành động bị chặn có chủ đích.
- Nếu hợp lệ, thiết kế rule **hẹp nhất** để khôi phục mà không mở toàn bộ biên.
- Thử giải pháp qua dry-run hoặc môi trường giống production khi có thể.
- Áp dụng thay đổi theo quy trình khẩn cấp; theo dõi kết quả sau propagation.
- Cập nhật dependency inventory và kiểm tra vì sao luồng này chưa được nhận diện.

## 16. Bảo vệ dữ liệu không đồng nghĩa ngăn mọi egress

Một sai lầm nguy hiểm là nghĩ rằng đặt project vào perimeter sẽ ngăn **mọi** đường dữ liệu ra ngoài.

VPC Service Controls quản lý ranh giới của **những dịch vụ Google Cloud được hỗ trợ, qua các API/luồng tích hợp**. Nó không mặc định kiểm soát:

- Mọi lưu lượng TCP/UDP đến Internet từ VM/GKE.
- Tự động chặn việc ứng dụng lấy dữ liệu hợp lệ rồi gửi qua HTTP tới máy chủ ngoài.
- Mọi Google Cloud service chưa có tích hợp VPC SC.
- IAM sai cấu hình, service account key bị lộ hoặc bucket/public sharing ở những đường ngoài phạm vi bảo vệ.
- Dữ liệu đã được xuất từ trước khi policy có hiệu lực.

Để giảm rủi ro toàn diện, nên kết hợp:

| Lớp | Biện pháp |
| --- | --- |
| **Danh tính** | Service account riêng, ADC/WIF, IAM tối thiểu, giới hạn impersonation |
| **Dữ liệu** | Phân loại, retention, encryption, DLP, kiểm soát sharing và export |
| **API boundary** | VPC SC với restricted services, ingress/egress tối thiểu |
| **Mạng** | Egress firewall, proxy, Cloud NAT khi cần, restricted VIP/Private Service Connect |
| **Ứng dụng** | Authentication, authorization, validation, kiểm soát outbound endpoints |
| **Vận hành** | Audit logs, alert, incident response, policy review và rollout có kiểm chứng |

### 16.1. VPC SC có làm tăng chi phí không?

Để triển khai perimeter, có thể cần bật logging, export logs, Cloud DNS, network connectivity hoặc các dịch vụ hỗ trợ khác. **Không giả định mọi thành phần triển khai đều miễn phí.** Chi phí tổng thể cũng bị ảnh hưởng bởi kiến trúc mạng, workload, BigQuery queries, logging storage và công sức vận hành. Hãy xem pricing của từng dịch vụ liên quan và lập **Cloud Billing budget** cho môi trường lab.

Lưu ý: sai perimeter policy có thể gây gián đoạn deploy hoặc tác vụ nền, ảnh hưởng **độ tin cậy** nhiều hơn chi phí trực tiếp. Vì vậy dry-run và rollout kiểm soát là khoản đầu tư vận hành quan trọng.

## 17. Tình huống tổng hợp: bảo vệ dữ liệu đơn hàng

Nhóm Commerce đang chuẩn bị đưa dữ liệu đơn hàng vào production:

- `commerce-secure`: lưu object hóa đơn và bảng giao dịch.
- `analytics-secure`: chạy ETL nội bộ và dashboard.
- `ci-deploy`: pipeline triển khai từ bên ngoài.
- `sandbox-dev`: thử nghiệm, không được đọc dữ liệu thật.
- `audit-logs`: dự án tập trung giám sát.

### 17.1. Phương án kiến trúc

~~~mermaid
flowchart TB
    subgraph PER["Regular service perimeter: commerce-data"]
        A["commerce-secure<br/>Cloud Storage"]
        B["analytics-secure<br/>BigQuery + ETL"]
        A -->|"Luồng hợp lệ nội bộ"| B
    end
    CI["ci-deploy<br/>CI/CD bên ngoài"]
    SB["sandbox-dev"]
    LOG["audit-logs<br/>Log collection"]
    CI -. "Ingress chỉ các API cần thiết" .-> PER
    PER -. "Egress có điều kiện nếu cần" .-> LOG
    SB --> DENY["Không được mở truy cập chỉ để dùng tiện"]
~~~

**Thiết kế đề xuất:**

1. Xác định chính xác hai project dữ liệu nào cần cùng perimeter và các dịch vụ hỗ trợ cần restricted.
2. Lập danh sách thao tác CI/CD thật sự cần trên những project protected; nếu có thể, tách quyền quản trị triển khai khỏi quyền truy cập dữ liệu.
3. Xác định các luồng dịch vụ tự động như log sinks, service agents, backups.
4. Tạo **dry-run**, chạy bộ kiểm thử và kiểm tra violation logs.
5. Chỉ tạo ingress/egress rules cho những luồng được business owner chấp thuận.
6. Cấu hình IAM hẹp và mạng private/restricted VIP theo nhu cầu.
7. Chuyển enforced sau change review, theo dõi chức năng cùng độ trễ request.
8. Rà soát lại khi thêm GKE/Cloud Run, Dataflow hoặc project mới.

### 17.2. Các câu hỏi bảo mật phải trả lời

| Câu hỏi | Tiêu chí chấp nhận |
| --- | --- |
| Developer có thể đọc dữ liệu thật từ laptop không? | Chỉ nếu chính sách cho phép theo danh tính, nguồn và operation; mặc định không |
| CI/CD có quyền tạo service nhưng không đọc object không? | Tách vai trò IAM và API methods, thử quyền tối thiểu |
| Job ETL có được xuất dữ liệu sang project sandbox không? | Mặc định không; ngoại lệ phải có owner/phê duyệt và giới hạn đích |
| Một service agent cần ghi logs ra ngoài perimeter thì sao? | Xác định principal/đích thực tế, tạo rule hẹp theo tài liệu |
| Sai policy ảnh hưởng production được phát hiện ra sao? | Dry-run, Policy Audit Logs, SLO và runbook |
| Khi thay đổi resource hierarchy có phải cập nhật perimeter không? | Kiểm tra membership và dependency thực tế; không suy ra từ folder |

## 18. Bài tập tự kiểm tra

**Câu 1.** Một developer có `roles/storage.objectViewer` nhưng gọi bucket protected từ laptop nhận lỗi VPC SC `403`. Có phải IAM đã cấu hình sai?

*Đáp án gợi ý:* Chưa chắc. IAM có thể đủ nhưng ingress policy/access level không cho phép API client từ ngoài perimeter. Xem nguồn gọi, identity, method, resource và violation log.

**Câu 2.** Copy object từ bucket trong perimeter A sang bucket trong perimeter B. Chỉ thêm egress policy ở A có luôn đủ không?

*Đáp án gợi ý:* Không. Các perimeter liên quan phải cho phép request theo yêu cầu API; có thể cần ingress rule ở B và kiểm tra thêm phương thức/các tài nguyên tham gia cùng IAM.

**Câu 3.** Trong VPC SC, ingress/egress có đồng nghĩa với hướng chuyển dữ liệu lên/xuống qua NIC của VM không?

*Đáp án gợi ý:* Không. Hướng được xác định theo API client và resources so với ranh giới perimeter, không đơn thuần theo byte gửi hay nhận.

**Câu 4.** Vì sao nên chạy dry-run trước enforced?

*Đáp án gợi ý:* Dry-run ghi request sẽ vi phạm nếu enforced mà không chặn vì policy dry-run. Nhóm có thể thu thập bằng chứng, thử CI/CD, xử lý tích hợp và chuẩn bị rollback.

**Câu 5.** Dry-run báo không có vi phạm sau 20 phút. Có thể khẳng định production sẽ không gặp sự cố không?

*Đáp án gợi ý:* Không. Job theo lịch, hoạt động phục hồi, quy trình hiếm gặp hoặc service agents có thể chưa được thử.

**Câu 6.** `restricted.googleapis.com` có tự cấp quyền đọc Cloud Storage không?

*Đáp án gợi ý:* Không. Đó là con đường/API VIP hạn chế hỗ trợ VPC SC; IAM và chính sách perimeter vẫn được kiểm tra.

**Câu 7.** Một VM có thể gửi dữ liệu đã đọc hợp lệ qua HTTPS tới máy chủ Internet không được bảo vệ bởi VPC SC. Điều gì còn thiếu trong thiết kế?

*Đáp án gợi ý:* VPC SC không kiểm soát mọi egress TCP/HTTP. Cần thiết kế egress firewall/proxy, chính sách ứng dụng, DLP và giám sát để giảm rủi ro.

**Câu 8.** Một nhóm bật restricted services là Cloud Storage và BigQuery, nhưng workload cần Artifact Registry để triển khai. Nên xử lý thế nào?

*Đáp án gợi ý:* Xác định Artifacts/API dependencies, kiểm tra tích hợp VPC SC và cấu hình VPC accessible services/restricted VIP phù hợp. Không mở `ANY_IDENTITY` hoặc toàn bộ APIs tùy tiện.

**Câu 9.** Phải dùng project ID hay project number khi định nghĩa `--perimeter-resources=projects/...` trong gcloud?

*Đáp án gợi ý:* Dùng **project number** theo định dạng mà Access Context Manager yêu cầu, ví dụ `projects/111111111111`.

**Câu 10.** Một project đang trong enforced perimeter A. Có nên tạo luôn enforced perimeter B chứa project đó để thử cấu hình mới không?

*Đáp án gợi ý:* Không. Cần xem quy tắc membership, dùng dry-run hoặc quy trình di chuyển được quản trị thay vì tạo enforced membership trùng lặp.

**Câu 11.** Vì sao một rule `ANY_IDENTITY` kết hợp mọi nguồn và mọi operation rủi ro dù API vẫn cần IAM?

*Đáp án gợi ý:* Nó làm ranh giới perimeter rất rộng, loại bỏ nhiều lợi ích kiểm soát bổ sung và mở đường cho identity bị đánh cắp có IAM phù hợp. Nên giới hạn principal, source, API, operation và resource.

**Câu 12.** Sau khi enforce policy, Cloud Run job bị `403` khi gọi BigQuery nhưng VM khác trong cùng project hoạt động. Bạn kiểm tra gì?

*Đáp án gợi ý:* Principal thực tế, API method, tài nguyên liên quan (job project/dataset project), VPC SC source context, ingress/egress, IAM, DNS/egress config và violation logs; không suy ra chỉ từ việc cùng project.

## 19. Checklist triển khai và vận hành

- [ ] Đã xác định rõ **dữ liệu cần bảo vệ**, owner và mức độ nhạy cảm.
- [ ] Đã chọn đúng organization access policy và project numbers.
- [ ] Đã kiểm tra membership enforced/dry-run hiện tại, không trùng project.
- [ ] Đã đối chiếu **supported services và limitations** cho mọi API quan trọng.
- [ ] Đã lập danh sách principal, nguồn, tài nguyên, API methods và service agents.
- [ ] Đã rà soát Cloud Run/GKE/VM/CI/CD, logs, backup, BigQuery jobs và hoạt động quản trị.
- [ ] Đã thiết kế ingress/egress tối thiểu, có owner cho mỗi ngoại lệ.
- [ ] Đã cân nhắc access levels và VPC accessible services.
- [ ] Đã kiểm tra DNS, routes, firewall và restricted VIP nếu dùng đường mạng riêng.
- [ ] Đã chạy dry-run đủ thời gian và đủ use cases; phân tích violation logs.
- [ ] Đã chuẩn bị change window, giám sát, quyền xử lý sự cố và rollback.
- [ ] Đã xác nhận các workload quan trọng sau khi enforce và sau propagation.
- [ ] Đã đưa review perimeter vào quy trình thêm project và tự động hóa phát hành.
- [ ] Đã lập kế hoạch logging, vận hành, quota và chi phí liên quan.

## 20. Những điều cần nhớ

- **VPC Service Controls là lớp kiểm soát ranh giới Google Cloud APIs/dữ liệu được hỗ trợ**, bổ sung chứ không thay IAM.
- **Regular service perimeter** xác định protected resources và restricted services theo cấu hình; không đồng nghĩa với một VPC firewall hay một folder IAM.
- **Ingress/egress** diễn tả hướng API request so với perimeter và các resource tham gia, không chỉ chiều dữ liệu truyền đi.
- **Cross-perimeter** có thể cần policy của tất cả perimeters liên quan; IAM vẫn phải cho phép hành động.
- **Dry-run trước enforced** là bước quan trọng để giảm rủi ro phá vỡ CI/CD, dịch vụ quản lý và các luồng nghiệp vụ.
- **Restricted VIP** hỗ trợ đường riêng tới các dịch vụ được VPC SC hỗ trợ; vẫn cần DNS, routes, firewall, IAM và perimeter policy.
- **Quan sát vi phạm** qua Policy Audit Logs, principal, method, source, resource và violation reason, thay vì nới lỏng toàn bộ policy khi gặp lỗi 403.
- **Bảo vệ toàn diện** còn cần giới hạn Internet egress, credential, ứng dụng, dữ liệu, audit và kiểm soát chi phí.

Khi xây dựng hệ thống Google Cloud có dữ liệu quan trọng, hãy luôn trả lời: **“Tài nguyên nào nằm trong ranh giới? API nào được bảo vệ? Ai được gọi từ đâu, đến đâu, bằng phương thức nào? Làm sao kiểm chứng rằng perimeter vừa chặn hành vi không mong muốn vừa không làm đứt luồng nghiệp vụ hợp lệ?”**

## Tài liệu tham khảo chính thức

- [VPC Service Controls overview](https://cloud.google.com/vpc-service-controls/docs/overview)
- [Service perimeter details and configuration](https://cloud.google.com/vpc-service-controls/docs/service-perimeters)
- [Supported products and limitations](https://cloud.google.com/vpc-service-controls/docs/supported-products)
- [Create service perimeters](https://cloud.google.com/vpc-service-controls/docs/create-service-perimeters)
- [Ingress and egress rules](https://cloud.google.com/vpc-service-controls/docs/ingress-egress-rules)
- [Configuring ingress and egress policies](https://cloud.google.com/vpc-service-controls/docs/configuring-ingress-egress-policies)
- [Dry run mode for service perimeters](https://cloud.google.com/vpc-service-controls/docs/dry-run-mode)
- [Best practices for enabling VPC Service Controls](https://cloud.google.com/vpc-service-controls/docs/enable)
- [VPC Service Controls audit logging](https://cloud.google.com/vpc-service-controls/docs/audit-logging)
- [Troubleshoot VPC Service Controls](https://cloud.google.com/vpc-service-controls/docs/troubleshooting)
- [Private Google Access with VPC Service Controls](https://cloud.google.com/vpc-service-controls/docs/private-connectivity)
- [Configure Private Google Access](https://cloud.google.com/vpc/docs/configure-private-google-access)

