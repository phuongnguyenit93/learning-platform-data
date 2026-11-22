# Basic roles, predefined roles và custom roles trong Google Cloud IAM

Trong Google Cloud, một người có thể xem máy ảo Compute Engine nhưng không được xóa máy; một ứng dụng Cloud Run có thể đọc đối tượng trong Cloud Storage nhưng không được thay đổi cấu hình VPC; một pipeline triển khai có thể cập nhật dịch vụ mà không được quản lý quyền của cả project. Những khác biệt này được thiết kế bằng **Identity and Access Management (IAM)**: xác định **ai** được phép thực hiện **hành động nào** trên **tài nguyên nào**, trong **điều kiện nào**.

Bài học thuộc chương **IAM và xác thực** của mô-đun **CLOUD_PROVIDERS_GCP**. Trong hành trình học từ tổ chức project, IAM, VPC tới Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, chọn đúng loại role là nền tảng để bảo vệ tài nguyên, tự động hóa phát hành, vận hành đáng tin cậy và kiểm soát chi phí. Trọng tâm của bài là so sánh ba nhóm role: **basic roles**, **predefined roles** và **custom roles**; hiểu cách hoạt động, biết khi nào dùng và thực hành kiểm tra quyền với `gcloud`.

## 1. Nền tảng: principal, permission, role và policy binding

### 1.1. Xác thực khác với phân quyền

- **Authentication (xác thực):** kiểm tra danh tính của người dùng, ứng dụng hoặc workload. Ví dụ, một lập trình viên đăng nhập bằng tài khoản công ty; một ứng dụng chạy bằng service account.
- **Authorization (phân quyền):** quyết định danh tính đã được xác thực có được gọi một API hoặc thao tác với một tài nguyên cụ thể hay không.

Trong mô hình IAM của Google Cloud, các khái niệm chính gồm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Principal** | Danh tính cần quyền: user, group, service account hoặc danh tính được liên kết qua federation. | `user:lan@example.com`, `group:platform@example.com`, `serviceAccount:orders-runtime@my-prod-project.iam.gserviceaccount.com`. |
| **Permission** | Một quyền thao tác cụ thể, thường có dạng `service.resource.action`. | `compute.instances.get`, `compute.instances.list`. |
| **Role** | Một tập hợp các permission được đặt tên. | `roles/compute.viewer`. |
| **Allow policy / role binding** | Gắn role cho principal trên một tài nguyên hoặc phạm vi tài nguyên; binding có thể kèm IAM Condition. | Nhóm vận hành được gán `roles/compute.viewer` trên project. |
| **Resource** | Đối tượng cần được bảo vệ; có thể nằm dưới organization, folder, project hoặc là tài nguyên của dịch vụ. | Project, bucket Cloud Storage, service account, dịch vụ Cloud Run. |

Không có khái niệm “role = người dùng”. **Role là tập quyền**, còn principal là chủ thể nhận quyền. Việc tạo một role tự nó chưa cấp quyền cho ai; cần có binding phù hợp trong allow policy của tài nguyên hoặc tổ tiên của tài nguyên đó.

### 1.2. Quyền hiệu lực theo cây tài nguyên

Google Cloud sử dụng hệ thống phân cấp tài nguyên. Một binding cấp ở tổ tiên có thể ảnh hưởng tới các tài nguyên con tương ứng, theo hỗ trợ và chính sách của dịch vụ:

~~~mermaid
flowchart TB
    O["Organization"] --> F["Folder: Engineering"]
    F --> P["Project: my-prod-project"]
    P --> VM["Compute Engine VM"]
    P --> RUN["Cloud Run service"]
    P --> BUCKET["Cloud Storage bucket"]
    P --> SQL["Cloud SQL instance"]
    ROLE["Role binding trên Project"] -. "Quyền có thể kế thừa xuống" .-> VM
    ROLE -.-> RUN
    ROLE -.-> BUCKET
    ROLE -.-> SQL
~~~

Ví dụ, nếu một nhóm được cấp role đọc Compute Engine ở cấp project, nhóm thường có thể xem những tài nguyên Compute Engine liên quan trong project đó. Nếu chỉ cần xem một bucket, hãy cân nhắc binding trên **bucket** khi role và dịch vụ hỗ trợ, tránh cấp quyền tương ứng trên toàn project.

Việc một thao tác có được cho phép hay không còn phụ thuộc vào **IAM Conditions**, chính sách từ tổ tiên, IAM deny policies, principal access boundary policies (khi áp dụng), tổ chức và các kiểm soát khác. Sơ đồ chỉ minh họa cơ chế kế thừa của **allow policy**, không diễn đạt mọi điều kiện quyết định quyền hiệu lực.

### 1.3. Một principal có thể có nhiều role

Một người hoặc service account có thể nhận nhiều role từ các binding khác nhau. Khi một role cho phép thao tác cần thiết, thao tác đó có thể được cấp phép theo allow policy; tuy nhiên các chính sách giới hạn hoặc từ chối áp dụng có thể làm kết quả cuối cùng là không được phép.

Ví dụ:

~~~text
Principal: group:dev-team@example.com

Project my-dev-project:
  roles/compute.viewer
  roles/logging.viewer

Cloud Storage bucket dev-artifacts:
  roles/storage.objectViewer
~~~

Nhóm có thể xem thông tin máy ảo, xem logs thuộc phạm vi được cấp và đọc đối tượng trong bucket liên quan. Nhóm **không mặc nhiên** được thay đổi máy ảo, đọc mọi bucket trong tổ chức hoặc xem dữ liệu bí mật của mọi dịch vụ.

## 2. Basic roles: Viewer, Editor và Owner

### 2.1. Basic roles là gì?

**Basic roles** (còn gọi là *primitive roles* trong nhiều tài liệu cũ) là ba role rất rộng có từ các phiên bản đầu của Google Cloud IAM:

| Role | Định danh | Năng lực chính | Rủi ro khi dùng rộng |
| --- | --- | --- | --- |
| **Viewer** | `roles/viewer` | Xem thông tin của nhiều loại tài nguyên. | Có thể truy cập nhiều metadata hơn nhu cầu công việc; không bảo đảm quyền xem mọi nội dung dữ liệu. |
| **Editor** | `roles/editor` | Xem và thay đổi nhiều loại tài nguyên. | Phạm vi thay đổi lớn, có thể dẫn tới sự cố vận hành hoặc chi phí; không tương đương với toàn quyền IAM. |
| **Owner** | `roles/owner` | Quyền quản trị rất rộng trên project, bao gồm khả năng quản lý nhiều cấu hình quyền. | Nếu cấp nhầm hoặc tài khoản bị chiếm đoạt, tác động có thể lan ra phần lớn project. |

Role cơ bản **không đồng nghĩa mọi permission của mọi dịch vụ**. Google Cloud có những permission không nằm trong basic roles, và các dịch vụ có thể có quy tắc riêng về dữ liệu, quyền hoặc phạm vi tài nguyên. Đặc biệt, đừng giả định `roles/viewer` cho phép đọc toàn bộ dữ liệu khách hàng hay `roles/editor` cho phép thay đổi tất cả IAM policy.

Ví dụ trong một project thương mại điện tử, gán `roles/editor` cho người chỉ cần quan sát cấu hình VM có thể cho phép họ thay đổi nhiều tài nguyên không liên quan. Nếu nhiệm vụ chỉ là xem Compute Engine, `roles/compute.viewer` thường phù hợp hơn.

### 2.2. Vì sao tránh basic roles trong production?

Basic roles có ưu điểm đơn giản, nhưng khi project chứa VPC, GKE, Cloud Run, Cloud SQL, Cloud Storage và các tài nguyên quản trị khác, một role rộng gây khó khăn:

1. **Khó thực hiện nguyên tắc quyền tối thiểu:** một nhiệm vụ nhỏ có thể nhận thêm hàng loạt permission không cần thiết.
2. **Khó xác định phạm vi tác động:** khi tài nguyên hoặc dịch vụ mới được bổ sung, các permission khả dụng của role rộng có thể thay đổi theo cơ chế IAM.
3. **Dễ nhầm quyền xem với quyền sử dụng dữ liệu:** xem cấu hình bucket và đọc đối tượng trong bucket là những thao tác khác nhau.
4. **Tăng rủi ro từ danh tính bị lộ:** đặc biệt khi quyền rộng được cấp cho service account dùng trong hệ thống tự động.
5. **Khó kiểm toán:** lý do nghiệp vụ của một role như `Editor` thường không cụ thể bằng một role theo chức năng.

Với hệ thống production, nên bắt đầu từ các **predefined roles** có phạm vi phù hợp. Chỉ cân nhắc basic roles trong các tình huống thực sự cần và đã được phê duyệt, chẳng hạn một số nhiệm vụ quản trị project có kiểm soát. Không mặc định cấp `Editor` cho lập trình viên hoặc service account chỉ vì đó là cách nhanh nhất để tránh lỗi `PERMISSION_DENIED`.

### 2.3. Minh họa sai và đúng

**Yêu cầu:** một thành viên nhóm vận hành cần xem tình trạng VM để đối chiếu cảnh báo.

~~~text
Không phù hợp:
  principal = user:operator@example.com
  role      = roles/editor
  scope     = project production

Phù hợp hơn:
  principal = group:vm-observers@example.com
  role      = roles/compute.viewer
  scope     = project chứa VM cần quan sát
~~~

Nếu người vận hành cần thêm quyền xem metric hay logs, có thể bổ sung role chuyên trách của Cloud Monitoring hoặc Cloud Logging ở đúng phạm vi, sau khi xác nhận các permission cần thiết. Không nên mở rộng thành `Editor` chỉ để xử lý một nhu cầu quan sát bổ sung.

## 3. Predefined roles: role dựng sẵn theo nghiệp vụ

### 3.1. Đặc điểm

**Predefined roles** là các role được Google tạo và duy trì theo sản phẩm, tài nguyên hoặc nhóm chức năng. Chúng thường có định danh dạng:

~~~text
roles/<service>.<roleName>
~~~

Ví dụ:

| Nhu cầu | Role dựng sẵn có thể xem xét | Ghi chú |
| --- | --- | --- |
| Xem VM Compute Engine | `roles/compute.viewer` | Phù hợp khi chỉ cần đọc metadata Compute Engine theo phạm vi được cấp. |
| Quản trị máy ảo | `roles/compute.instanceAdmin.v1` | Có thể thay đổi nhiều tài nguyên VM; kiểm tra chính xác permission trước khi cấp. |
| Sử dụng một service account để chạy workload | `roles/iam.serviceAccountUser` | Có quyền `iam.serviceAccounts.actAs` theo phạm vi cấp; không nên cấp trên toàn project nếu chỉ cần một service account. |
| Gọi dịch vụ Cloud Run có xác thực IAM | `roles/run.invoker` | Thường cấp trên dịch vụ Cloud Run cần gọi; điều kiện triển khai và cấu hình truy cập vẫn cần xem xét. |
| Đọc đối tượng Cloud Storage | `roles/storage.objectViewer` | Cân nhắc cấp trên bucket cụ thể nếu cần truy cập dữ liệu của bucket đó. |
| Quản lý đối tượng Cloud Storage | `roles/storage.objectAdmin` | Quyền rộng trên các object ở phạm vi được cấp; không đồng nghĩa quản trị mọi cấu hình bucket. |
| Kết nối tới Cloud SQL thông qua cơ chế yêu cầu quyền IAM phù hợp | `roles/cloudsql.client` | Là một phần của điều kiện kết nối; **không thay thế** database authentication và database privileges. |
| Xem thông tin cụm GKE | `roles/container.clusterViewer` | Liên quan đến thông tin cụm; quyền thao tác với Kubernetes API có thể còn cần Kubernetes RBAC. |
| Xem logs | `roles/logging.viewer` | Một số logs nhạy cảm có kiểm soát truy cập bổ sung. |
| Xem metrics và cấu hình giám sát | `roles/monitoring.viewer` | Phù hợp nhiệm vụ quan sát, nhưng không tự cấp quyền sửa cảnh báo/dashboard. |

Danh sách trên là **ứng viên ban đầu**, không phải bản phân quyền đủ cho mọi workload. Ví dụ, một pipeline triển khai Compute Engine có thể cần vừa quản lý VM vừa được phép *act as* service account gắn vào máy; quyền quản trị VM không tự cấp mọi quyền liên quan đến danh tính của máy. Các role được Google bổ sung hoặc thay đổi theo thời gian, vì vậy hãy đọc danh sách permission mới nhất của từng role trước khi quyết định.

### 3.2. Role ở cấp dịch vụ và ranh giới dữ liệu

Predefined roles thể hiện một cách phân chia công việc:

- **Người xem cấu hình** khác với **người sửa cấu hình**.
- **Người có quyền gọi dịch vụ** khác với **người triển khai phiên bản mới**.
- **Người quản lý bucket** khác với **người chỉ đọc object**.
- **Người xem metadata Cloud SQL** khác với **danh tính kết nối vào database** và **người có quyền SQL trên các bảng**.
- **Người quản lý tài nguyên GKE bằng Google Cloud API** khác với **người được phép tạo/sửa Pod trong Kubernetes API**; với GKE phải đánh giá cả Cloud IAM lẫn Kubernetes RBAC theo cơ chế xác thực và ủy quyền đang sử dụng.

Đây là nguyên tắc quan trọng khi ứng dụng sử dụng nhiều sản phẩm. Chọn role đúng chức năng giúp hệ thống vừa vận hành được vừa giảm rủi ro lộ dữ liệu hoặc thay đổi nhầm tài nguyên.

### 3.3. Kiểm tra permission bên trong role

Dùng Google Cloud CLI để xem role dựng sẵn:

~~~bash
# Xem chi tiết quyền trong role đọc Compute Engine.
gcloud iam roles describe roles/compute.viewer \
  --format="yaml(name,title,description,includedPermissions,stage)"

# Xem role cho phép gọi Cloud Run.
gcloud iam roles describe roles/run.invoker \
  --format="yaml(name,title,description,includedPermissions,stage)"
~~~

Các trường quan trọng:

| Trường | Ý nghĩa |
| --- | --- |
| `name` | Định danh đầy đủ của role. |
| `title` | Tên hiển thị dễ đọc. |
| `description` | Mục đích của role. |
| `includedPermissions` | Danh sách permission mà role bao gồm tại thời điểm kiểm tra. |
| `stage` | Trạng thái vòng đời của role, ví dụ GA hoặc giai đoạn khác nếu có. |

Không dựa hoàn toàn vào tên role để suy đoán quyền. Một role có chữ “admin” không nhất thiết cho phép quản trị mọi dịch vụ trong project, và một role có chữ “viewer” vẫn có thể làm lộ metadata nhạy cảm nếu cấp phạm vi quá rộng.

## 4. Custom roles: tạo tập permission theo nhu cầu

### 4.1. Khi nào cần custom role?

**Custom roles** là role do tổ chức hoặc nhóm quản trị định nghĩa bằng cách chọn các permission được hỗ trợ. Chúng giải quyết trường hợp những role dựng sẵn đều chứa nhiều quyền hơn mức công việc thực sự yêu cầu.

Ví dụ đội kiểm kê máy ảo chỉ cần:

~~~text
compute.instances.get
compute.instances.list
~~~

Những permission này cho phép xem thông tin các instance theo điều kiện IAM. Nếu chưa có predefined role phù hợp với phạm vi mong muốn, nhóm quản trị có thể xây custom role “VM Inventory Reader”, rồi gán role đó cho principal ở phạm vi phù hợp.

Custom role **không tự tạo ra permission mới**. Nó chỉ tập hợp các permission có thể đưa vào custom role, theo danh sách hỗ trợ của Google Cloud. Không phải mọi permission đều được hỗ trợ; một số permission có giới hạn hoặc phụ thuộc cấp tài nguyên.

### 4.2. Cấp tổ chức và cấp project

Custom role có thể được tạo ở cấp **organization** hoặc **project**:

| Cấp độ định nghĩa | Định danh minh họa | Phù hợp khi |
| --- | --- | --- |
| Organization | `organizations/123456789012/roles/vmInventoryReader` | Muốn dùng cùng một định nghĩa role trong nhiều project thuộc tổ chức, theo phạm vi cấp quyền được hỗ trợ. |
| Project | `projects/my-prod-project/roles/vmInventoryReader` | Vai trò gắn với nhu cầu của một project cụ thể. |

**Cấp nơi role được định nghĩa không phải phạm vi quyền tự động nhận được.** Role cấp organization không có nghĩa principal lập tức được phép xem mọi project. Phạm vi quyền phụ thuộc vào **nơi binding được cấp** và các chính sách áp dụng. Ngược lại, tạo role mà không có binding sẽ không trao permission cho bất kỳ principal nào.

### 4.3. Các bước thiết kế custom role

1. **Viết mô tả nhiệm vụ:** người được cấp quyền phải làm gì, trên những loại tài nguyên nào?
2. **Xác định permission tối thiểu:** dùng tài liệu permission và thử trên môi trường được kiểm soát; tránh đoán chỉ từ tên API.
3. **Kiểm tra permission có hỗ trợ custom role:** không phải permission nào cũng được đưa vào custom role.
4. **Chọn nơi định nghĩa:** project nếu nhu cầu chỉ nằm ở đó; organization nếu định nghĩa cần được quản lý tập trung và sử dụng trong nhiều project.
5. **Đặt tên và người sở hữu:** ID role ổn định, title dễ hiểu, description chỉ rõ phạm vi nghiệp vụ.
6. **Tạo role và cấp binding ở phạm vi nhỏ nhất phù hợp**, sau đó kiểm thử các thao tác phải được phép và phải bị từ chối.
7. **Định kỳ xem xét:** kiểm tra permission không còn cần thiết, tính tương thích và những thay đổi từ dịch vụ Google Cloud.

Nếu predefined role đã đáp ứng công việc với phạm vi chấp nhận được, dùng role đó thường giúp giảm chi phí quản lý custom role. Custom role có thêm trách nhiệm duy trì, kiểm thử và xử lý thay đổi permission trong suốt vòng đời của ứng dụng.

### 4.4. Ví dụ tạo role chỉ đọc kiểm kê VM

Các lệnh sau **minh họa thay đổi IAM**; chỉ chạy trong project thử nghiệm được phép và sau khi người quản trị xác nhận các permission cần thiết. Biến môi trường và địa chỉ email là giá trị mẫu, cần thay theo tổ chức.

~~~bash
# Bash: thay ID project bằng project thực sự được quản lý.
PROJECT_ID="my-prod-project"

# Tạo role tùy chỉnh ở cấp project.
gcloud iam roles create vmInventoryReader \
  --project="$PROJECT_ID" \
  --title="VM Inventory Reader" \
  --description="Read VM instance metadata for approved inventory work" \
  --permissions="compute.instances.get,compute.instances.list" \
  --stage=GA

# Kiểm tra lại định nghĩa role vừa tạo.
gcloud iam roles describe vmInventoryReader \
  --project="$PROJECT_ID" \
  --format="yaml(name,title,description,includedPermissions,stage)"
~~~

Ví dụ `compute.instances.get` và `compute.instances.list` chỉ mô tả nhiệm vụ đọc thông tin VM cơ bản. Nếu công cụ kiểm kê còn gọi API khác, hiển thị thêm thuộc tính hoặc cần đọc metadata của project, có thể phải bổ sung permission thích hợp. Hãy kiểm tra kết quả thực tế thay vì cấp ngay quyền sửa tài nguyên.

Sau khi xác nhận phạm vi và nhóm sử dụng, một binding ở cấp project có thể được thêm như sau:

~~~bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="group:vm-auditors@example.com" \
  --role="projects/$PROJECT_ID/roles/vmInventoryReader"
~~~

Lệnh này **thay đổi chính sách IAM thực tế** nếu được thực thi với đủ quyền. Dùng nhóm thay vì cấp rời rạc cho nhiều người giúp quản trị thành viên tập trung hơn. Binding ở project có thể cấp quyền đọc các instance phù hợp trong project đó; nếu chỉ cần một tài nguyên hẹp hơn, cần xem loại tài nguyên và role có hỗ trợ cấp binding ở phạm vi nhỏ hơn hay không.

### 4.5. Cập nhật và ngừng sử dụng custom role

Trong vòng đời custom role, người quản trị có thể cập nhật title, description hoặc permission và theo dõi các trạng thái của role theo hỗ trợ từ Google Cloud. Việc thêm một permission vào custom role **có thể mở rộng quyền cho mọi principal đang được gán role đó** ngay khi chính sách có hiệu lực. Do vậy:

- Xem danh sách binding đang dùng role trước khi thay đổi.
- Phân tích tác động khi thêm hoặc bớt permission, bao gồm hệ thống CI/CD và tác vụ chạy định kỳ.
- Kiểm thử trên môi trường có phạm vi nhỏ và lập kế hoạch hoàn tác hoặc thay thế nếu cần.
- Kiểm tra phụ thuộc trước khi vô hiệu hóa hoặc xóa role; việc xóa không thay thế quy trình thu hồi binding và xác minh quyền hiệu lực.

Một custom role được tạo phù hợp ở thời điểm ban đầu vẫn có thể trở nên quá rộng hoặc quá hẹp khi API và nghiệp vụ thay đổi.

## 5. So sánh ba nhóm role

| Tiêu chí | Basic roles | Predefined roles | Custom roles |
| --- | --- | --- | --- |
| Ai định nghĩa? | Google Cloud. | Google Cloud. | Tổ chức hoặc quản trị viên được ủy quyền. |
| Ví dụ | `roles/viewer`, `roles/editor`, `roles/owner`. | `roles/compute.viewer`, `roles/run.invoker`. | `projects/PROJECT_ID/roles/vmInventoryReader`. |
| Mức độ chuyên biệt | Thấp, phạm vi rất rộng. | Theo sản phẩm/chức năng. | Do người quản trị chọn permission được hỗ trợ. |
| Mức công quản lý | Ít về mặt định nghĩa, nhưng rủi ro cấp quá quyền. | Thấp; Google duy trì permission. | Cao hơn; cần theo dõi, kiểm thử và cập nhật. |
| Khả năng đáp ứng least privilege | Thường kém. | Thường là lựa chọn đầu tiên. | Hữu ích khi predefined roles vẫn quá rộng. |
| Thay đổi permission | Google quản lý. | Google quản lý. | Quản trị viên quản lý trong giới hạn hỗ trợ. |
| Sử dụng điển hình | Một số tình huống quản trị đặc biệt, phạm vi chặt chẽ. | Người dùng, nhóm vận hành, ứng dụng và pipeline theo chức năng. | Nhiệm vụ đặc thù yêu cầu tập permission nhỏ hơn. |

Quy tắc chọn role có thể diễn đạt bằng sơ đồ:

~~~mermaid
flowchart TD
    A["Liệt kê hành động và tài nguyên thực sự cần"] --> B{"Có predefined role phù hợp?"}
    B -- "Có" --> C["Chọn role chuyên trách"]
    B -- "Không hoặc quá rộng" --> D{"Permission hỗ trợ custom role?"}
    D -- "Có" --> E["Thiết kế custom role"]
    D -- "Không" --> F["Điều chỉnh quy trình hoặc phân tách quyền; đánh giá phương án khác"]
    C --> G["Cấp binding ở phạm vi nhỏ nhất phù hợp"]
    E --> G
    F --> G
    G --> H["Kiểm thử và rà soát định kỳ"]
~~~

Sơ đồ là hướng dẫn thiết kế, không phải quy tắc cứng. Trước khi tạo role mới, cũng nên xem có thể chia nhiệm vụ thành hai danh tính hoặc hai bước vận hành để tránh phải gộp những quyền nhạy cảm hay không.

## 6. Tình huống triển khai: phân quyền cho một hệ thống bán hàng

Một đội triển khai backend trên **Cloud Run**, lưu giao dịch trong **Cloud SQL**, dùng **Cloud Storage** cho ảnh sản phẩm, duy trì một số VM Compute Engine và cụm **GKE** cho các workload khác. Họ muốn bảo vệ tài nguyên khi tự động hóa phát hành và vẫn đủ khả năng quan sát sự cố.

### 6.1. Xác định principal theo trách nhiệm

| Principal / công việc | Role có thể xem xét | Phạm vi đề xuất | Cần kiểm chứng thêm |
| --- | --- | --- | --- |
| Nhóm chỉ xem VM | `roles/compute.viewer` | Project chứa VM phải quan sát. | Có cần thêm quyền xem logs/metrics hay không. |
| Nhân viên trực vận hành | `roles/logging.viewer`, `roles/monitoring.viewer` | Project liên quan đến dịch vụ cần trực. | Logs nhạy cảm, quyền cảnh báo và quy trình truy cập khi sự cố. |
| Pipeline triển khai Cloud Run | Role triển khai thích hợp như `roles/run.developer`; thêm `roles/iam.serviceAccountUser` trên runtime service account khi cần *act as*. | Project đích và service account liên quan. | Quyền đối với registry/artifact, networking và các bước trong pipeline. |
| Runtime service account của Cloud Run | `roles/cloudsql.client` nếu dùng cơ chế kết nối cần role này; role đọc object tương ứng khi cần Cloud Storage. | Project/instance hoặc bucket theo hỗ trợ của dịch vụ. | Xác thực vào database và quyền SQL; ranh giới object và dữ liệu nhạy cảm. |
| Thành phần chỉ gọi API Cloud Run có xác thực | `roles/run.invoker` | Dịch vụ Cloud Run cần gọi. | Cơ chế xác thực token và phương án gọi giữa dịch vụ. |
| Nhóm kiểm kê VM theo nghiệp vụ riêng | Custom role chỉ chứa permission đọc cần thiết. | Project hoặc tài nguyên được hỗ trợ. | Các API metadata bổ sung phục vụ công cụ kiểm kê. |
| Quản trị IAM | Role quản trị IAM chuyên trách, theo phân cấp nhiệm vụ. | Tài nguyên hoặc phần của tổ chức được giao. | Quy trình phê duyệt, MFA, ghi audit và khả năng leo thang đặc quyền. |

Đây là **bản phác thảo**. Role cụ thể phải xuất phát từ API, tài nguyên, hành động và trách nhiệm thực tế. Ví dụ service account chạy Cloud Run không nên giữ quyền triển khai phiên bản mới chỉ vì pipeline sử dụng role tương tự. Tách **deployment identity** khỏi **runtime identity** giúp hạn chế thiệt hại nếu ứng dụng bị khai thác.

### 6.2. Sự khác biệt giữa quyền triển khai và quyền chạy

Giả sử pipeline cần triển khai phiên bản Cloud Run mới. Có hai danh tính:

~~~text
CI/CD deployer
  |-- quyền triển khai Cloud Run ở project/service phù hợp
  |-- quyền actAs trên runtime service account khi cần
  '-- quyền đọc artifact/image phù hợp để thực hiện phát hành

Cloud Run runtime service account
  |-- quyền kết nối Cloud SQL theo phương thức sử dụng
  '-- quyền đọc object trong bucket ứng dụng
~~~

Pipeline được phép triển khai **không có nghĩa** runtime service account cũng phải được phép triển khai. Và `roles/iam.serviceAccountUser` (khả năng dùng danh tính để gắn vào workload theo hành động hỗ trợ) **không giống** `roles/iam.serviceAccountTokenCreator` (có các quyền tạo thông tin xác thực/tokens theo phạm vi được cấp). Quyền liên quan tới service account cần được đánh giá kỹ vì có thể mở đường tới các quyền mà service account đang sở hữu.

### 6.3. Kiểm tra nguyên tắc quyền tối thiểu

Với mỗi principal, lập một bảng kiểm tra:

| Ca kiểm tra | Kết quả mong muốn |
| --- | --- |
| Nhóm quan sát gọi API liệt kê Compute Engine instance. | Được phép. |
| Nhóm quan sát thử xóa một VM. | Bị từ chối. |
| Runtime Cloud Run đọc object thuộc bucket ứng dụng. | Được phép nếu đúng resource và điều kiện. |
| Runtime Cloud Run đọc object của bucket tài chính khác. | Bị từ chối. |
| Pipeline triển khai phiên bản của dịch vụ được giao. | Được phép. |
| Pipeline thay đổi IAM policy của toàn organization. | Bị từ chối. |

Các ca từ chối có thể được kiểm tra bằng công cụ phân tích policy, môi trường sandbox hoặc những phương pháp không gây thay đổi dữ liệu. Không cần thử lệnh xóa tài nguyên production chỉ để chứng minh rằng người dùng thiếu quyền.

## 7. Kiểm tra và quản lý role bằng gcloud

### 7.1. Xem role trong IAM policy của project

~~~bash
PROJECT_ID="my-prod-project"

# Đọc IAM allow policy của project.
gcloud projects get-iam-policy "$PROJECT_ID" \
  --format="yaml(bindings)"
~~~

Một bản ghi binding có thể có dạng minh họa:

~~~yaml
bindings:
- members:
  - group:vm-observers@example.com
  role: roles/compute.viewer
- members:
  - serviceAccount:orders-runtime@my-prod-project.iam.gserviceaccount.com
  role: roles/cloudsql.client
~~~

Kết quả này chỉ mô tả **binding trực tiếp trên project** theo truy vấn; nó không phản ánh đầy đủ tất cả các role được kế thừa từ folder/organization hoặc chính sách cấp ở tài nguyên con. Nếu principal sử dụng IAM Conditions, binding còn có điều kiện; khi điều tra quyền hiệu lực cần xem toàn bộ policy liên quan.

Lệnh `get-iam-policy` cũng yêu cầu permission đọc IAM policy tương ứng. Người có quyền xem VM chưa chắc được quyền xem tất cả binding IAM trên project.

### 7.2. Xem predefined role và custom role

~~~bash
# Đọc định nghĩa của một predefined role.
gcloud iam roles describe roles/storage.objectViewer \
  --format="yaml(name,title,includedPermissions,stage)"

# Liệt kê custom roles được định nghĩa trong project.
gcloud iam roles list --project="$PROJECT_ID"

# Xem chi tiết custom role ở cấp project.
gcloud iam roles describe vmInventoryReader \
  --project="$PROJECT_ID" \
  --format="yaml(name,title,description,includedPermissions,stage)"
~~~

Nếu role không tồn tại hoặc tài khoản thiếu quyền đọc metadata, lệnh có thể trả lỗi. Không suy ra custom role đã bị xóa chỉ từ việc truy vấn bằng sai project hay organization.

### 7.3. Ví dụ binding và thu hồi quyền

Chỉ thực hiện các lệnh sau khi có quyền quản trị IAM và thay đúng tài nguyên, nhóm, role:

~~~bash
# Cấp quyền đọc Compute Engine cho một nhóm trên project.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="group:vm-observers@example.com" \
  --role="roles/compute.viewer"

# Thu hồi chính binding tương ứng khi không còn nhu cầu.
gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
  --member="group:vm-observers@example.com" \
  --role="roles/compute.viewer"
~~~

Những lệnh này cập nhật **allow policy** của project; trước khi thay đổi policy có điều kiện hoặc policy phức tạp, cần kiểm tra cú pháp và các binding hiện hữu để thao tác đúng mục tiêu. Việc xóa một binding không chứng minh principal hết quyền, vì có thể còn binding khác ở tổ tiên hoặc tại tài nguyên.

### 7.4. Điều tra khi gặp `PERMISSION_DENIED`

Khi CLI hoặc workload báo lỗi quyền, kiểm tra theo trình tự:

1. **Principal nào thật sự gọi API?** Tài khoản người dùng, service account runtime, pipeline hay danh tính federation?
2. **Thao tác đòi permission nào?** Dựa vào API, tài liệu dịch vụ và chi tiết lỗi; một thao tác có thể cần nhiều permission.
3. **Resource nào bị kiểm tra quyền?** Project, service account, bucket, dịch vụ Cloud Run hoặc tài nguyên con.
4. **Binding có ở đúng phạm vi không?** Role project chưa chắc đáp ứng thao tác trên resource ngoài project hoặc ngoài vùng kiểm soát.
5. **Có điều kiện hoặc chính sách hạn chế nào không?** IAM Conditions, deny, principal access boundary, organization policy, VPC Service Controls hoặc cơ chế authorization khác có thể ảnh hưởng.
6. **Role có đủ permission không?** Đọc `includedPermissions`, dùng Policy Troubleshooter / Policy Analyzer nếu phù hợp và có quyền truy cập.
7. **Có cần quyền hệ thống đích ngoài Cloud IAM không?** Ví dụ database privileges của Cloud SQL hay Kubernetes RBAC của GKE.

Không khắc phục `PERMISSION_DENIED` bằng cách cấp `roles/owner` hay `roles/editor` trước khi xác định nguyên nhân. Cách làm đó che đi quyền còn thiếu, làm tăng phạm vi đặc quyền và gây khó cho lần kiểm toán sau.

## 8. Nguyên tắc thiết kế role an toàn và dễ vận hành

### 8.1. Bảy quy tắc thực hành

1. **Gắn quyền với nhiệm vụ:** lập danh sách những API và tài nguyên thật sự cần thay vì hỏi “cần role nào cho cả nhóm kỹ thuật”.
2. **Ưu tiên predefined role phù hợp:** sau đó đánh giá custom role nếu vẫn cấp quá rộng; hạn chế basic roles trong hệ thống sản xuất.
3. **Giảm phạm vi binding:** nếu chỉ cần một bucket, service hoặc service account, cân nhắc cấp trực tiếp tại tài nguyên đó khi được hỗ trợ.
4. **Ưu tiên group cho nhân sự:** tránh khó theo dõi do cấp từng người. Với workload, sử dụng service account và cơ chế xác thực phù hợp, giảm dùng khóa dài hạn.
5. **Phân tách nhiệm vụ nhạy cảm:** người phát hành, người phê duyệt thay đổi IAM và runtime application có thể cần những principal khác nhau.
6. **Ghi nhận và kiểm toán thay đổi:** dùng Cloud Audit Logs theo cấu hình và phạm vi áp dụng; xem xét đề xuất từ IAM Recommender và kiểm tra trước khi điều chỉnh quyền.
7. **Rà soát định kỳ:** quyền từng cần thiết cho môi trường test hoặc chiến dịch ngắn hạn có thể không còn phù hợp sau khi triển khai ổn định.

IAM Conditions có thể giúp giới hạn một số binding bằng thuộc tính được hỗ trợ (chẳng hạn thời gian hoặc thuộc tính tài nguyên), nhưng chúng **không thay thế** việc chọn role và phạm vi phù hợp. Không phải mọi resource hoặc permission đều hỗ trợ cùng một loại điều kiện.

### 8.2. Role gắn với độ tin cậy và chi phí như thế nào?

IAM ảnh hưởng trực tiếp tới hành vi vận hành:

- Cấp quá ít quyền cho CI/CD có thể khiến phát hành thất bại vào thời điểm nhạy cảm; vì vậy cần kiểm thử quy trình phát hành với đúng danh tính sử dụng thật.
- Cấp quá rộng cho runtime service account có thể làm sự cố ứng dụng lan sang dữ liệu hoặc dịch vụ khác.
- Vai trò quản trị rộng có thể cho phép tạo tài nguyên tốn chi phí hoặc thay đổi mạng ảnh hưởng đến ứng dụng; cần đi kèm governance, budget alert và kiểm soát thay đổi.
- Phân quyền xem logs, metrics và cấu hình phù hợp giúp người trực sự cố điều tra mà không phải giữ quyền thay đổi sản phẩm không liên quan.

Tuy nhiên, **IAM không phải giải pháp duy nhất** cho bảo mật, chi phí hoặc độ tin cậy. VPC/firewall, secret management, chính sách tổ chức, giám sát, backup và quy trình vận hành vẫn cần được thiết kế phối hợp.

## 9. Bài tập thực hành và câu hỏi kiểm tra

### Bài 1 — Chọn role cho người chỉ xem máy ảo

Một nhóm chỉ được xem trạng thái VM trong project `my-prod-project` và không được tạo, sửa hoặc xóa VM. Nên bắt đầu với role nào?

**Gợi ý:** xem `roles/compute.viewer`; đọc `includedPermissions` để xác nhận thao tác cần dùng. `roles/editor` là phạm vi quá rộng.

### Bài 2 — Chọn role cho một dịch vụ đọc ảnh

Ứng dụng Cloud Run chỉ cần đọc ảnh trong bucket `product-images`. Nên cấp role nào và ở đâu?

**Gợi ý:** cân nhắc `roles/storage.objectViewer` trên bucket `product-images` cho runtime service account, khi cấu hình IAM bucket hỗ trợ và dữ liệu thực sự cần truy cập. Không tự cấp quyền trên toàn project.

### Bài 3 — Predefined role không đủ hẹp

Một công cụ kiểm kê chỉ gọi API lấy danh sách VM và đọc chi tiết một VM. Hãy đề xuất một custom role cấp project.

~~~text
Role ID: vmInventoryReader
Permissions:
  compute.instances.list
  compute.instances.get
~~~

Sau khi thiết kế, kiểm tra permission được hỗ trợ và các API bổ sung mà công cụ thực sự gọi. Phân biệt **tạo định nghĩa role** với **cấp binding role cho group**.

### Bài 4 — Chẩn đoán lỗi phân quyền

Pipeline có quyền cập nhật Cloud Run nhưng lỗi khi chọn runtime service account. Những gì cần kiểm tra?

**Gợi ý:** kiểm tra danh tính pipeline, quyền `iam.serviceAccounts.actAs` trên đúng service account và phạm vi binding; xem cách triển khai thực tế cùng điều kiện IAM. Không mặc định tăng thành `Owner`.

### Bài 5 — So sánh quyền hiệu lực

Một người có `roles/compute.viewer` trên project qua một group và có thêm custom role đọc metadata trên cùng project. Vì sao không thể kết luận chính xác toàn bộ quyền chỉ từ tên hai role?

**Gợi ý:** cần xem `includedPermissions`, binding ở ancestor/resource, IAM Conditions, deny policies và những cơ chế quản trị khác. Role được gán cũng có thể thay đổi nội dung theo thời gian.

## 10. Tổng kết và tài liệu tra cứu

Ba loại role phục vụ các nhu cầu khác nhau:

- **Basic roles** là những tập permission rất rộng (`Viewer`, `Editor`, `Owner`); hạn chế sử dụng vì khó bảo đảm quyền tối thiểu.
- **Predefined roles** do Google duy trì theo dịch vụ và nhiệm vụ; thường là lựa chọn đầu tiên khi phân quyền.
- **Custom roles** do tổ chức tự chọn permission được hỗ trợ; phù hợp khi role dựng sẵn vẫn rộng hơn nhu cầu, đổi lại phải quản lý vòng đời role.

Điều quan trọng nhất là **khớp principal, hành động, tài nguyên và phạm vi binding**. Thiết kế đúng giúp người dùng đủ quyền làm việc, service account đủ quyền thực thi, đội phát hành tự động hóa an toàn và đội vận hành quan sát được hệ thống mà không phải sở hữu đặc quyền ngoài nhiệm vụ.

Tài liệu chính thức nên kiểm tra khi triển khai trên project thật:

- [Understanding roles — Google Cloud IAM](https://cloud.google.com/iam/docs/understanding-roles)
- [Create and manage custom roles](https://cloud.google.com/iam/docs/creating-custom-roles)
- [Grant, change, and revoke access](https://cloud.google.com/iam/docs/granting-changing-revoking-access)
- [IAM permissions reference](https://cloud.google.com/iam/docs/permissions-reference)
- [Google Cloud CLI: iam roles](https://cloud.google.com/sdk/gcloud/reference/iam/roles)
- [Troubleshoot access — IAM](https://cloud.google.com/iam/docs/troubleshoot-access)

Khi có nghi ngờ về permission hoặc điều kiện cấp quyền, hãy kiểm tra định nghĩa role và policy thực tế theo tài liệu mới nhất của dịch vụ. Danh sách quyền, khả năng cấp binding ở từng cấp tài nguyên và các tính năng IAM có thể thay đổi qua thời gian.
