# Policy Analyzer và rà soát quyền trên tài nguyên Google Cloud

Khi một doanh nghiệp vận hành nhiều Google Cloud project, câu hỏi bảo mật không chỉ là “ai được cấp vai trò gì trong project này?”. Quản trị viên còn cần biết **ai có thể truy cập một tài nguyên cụ thể**, quyền được cấp trực tiếp hay **kế thừa từ organization/folder**, và những quyền nào có thể đang mở quá rộng. Những câu hỏi này quan trọng với VM Compute Engine, GKE, Cloud Run, Cloud Storage, BigQuery, Cloud SQL, service account và các API quản trị.

**Policy Analyzer for allow policies** của Google Cloud giúp phân tích các IAM allow bindings theo danh tính, quyền và tài nguyên. Bài học thuộc chương **Quản trị tổ chức** của mô-đun `CLOUD_PROVIDERS_GCP`: ngoài việc lựa chọn dịch vụ, người học cần quản trị IAM/VPC, bảo vệ workload, tự động hóa triển khai, theo dõi độ tin cậy và nhận diện rủi ro vận hành cũng như chi phí. Trọng tâm ở đây là **rà soát quyền trên tài nguyên có căn cứ**, hiểu giới hạn của kết quả phân tích và chuyển kết quả thành hành động quản trị an toàn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Policy Analyzer dùng để trả lời loại câu hỏi nào và dữ liệu đầu vào là gì.
2. Phân biệt **principal, role, permission, resource** và **query scope**.
3. Chạy truy vấn xem ai được cấp quyền đối với một tài nguyên, một principal có những quyền nào, hoặc principal có thể truy cập những tài nguyên nào theo IAM allow policies.
4. Hiểu vai trò của **kế thừa IAM**, nhóm người dùng, điều kiện IAM và khả năng impersonate service account.
5. Dùng Google Cloud Console và `gcloud asset analyze-iam-policy` cho hoạt động rà soát chỉ đọc.
6. Giải thích vì sao kết quả Policy Analyzer **không phải phép kiểm tra quyền truy cập hiệu lực cuối cùng**.
7. Phối hợp Policy Analyzer, Policy Troubleshooter, IAM Recommender và Cloud Asset Inventory trong quy trình rà soát quyền định kỳ.

## 1. Bài toán: ai thực sự có quyền đối với tài nguyên?

Giả sử công ty Atlas có cây tài nguyên:

~~~mermaid
flowchart TD
    O["Organization: Atlas"]
    F1["Folder: Production"]
    F2["Folder: Nonproduction"]
    P1["Project: commerce-prod"]
    P2["Project: commerce-dev"]
    B["Cloud Storage bucket: order-exports"]
    SA["Service account: orders-api"]
    O --> F1
    O --> F2
    F1 --> P1
    F2 --> P2
    P1 --> B
    P1 --> SA
~~~

Đội Security hỏi: **“Ai có quyền đọc dữ liệu trong bucket `order-exports`?”** Nhìn duy nhất IAM policy gắn trực tiếp vào bucket có thể bỏ sót những quyền được cấp từ project, folder hoặc organization.

Ví dụ ba nguồn cấp quyền có thể đồng thời tồn tại:

- Tại **organization**, nhóm `security-auditors@example.com` được gắn vai trò chỉ đọc phù hợp trên phạm vi tổ chức.
- Tại **folder Production**, nhóm `prod-operators@example.com` nhận một vai trò có các permission quản trị cần thiết.
- Tại **bucket**, service account `orders-api@commerce-prod.iam.gserviceaccount.com` được cấp `roles/storage.objectViewer`.

Mỗi IAM allow binding đều gắn một **role** với một hoặc nhiều **principal** ở một phạm vi tài nguyên. Khi được kế thừa, quyền tại cấp trên có thể áp dụng cho tài nguyên con. Nếu một principal thuộc Google Group được cấp quyền, quyền của principal cũng có thể đến từ **thành viên nhóm**, không xuất hiện dưới email cá nhân trong binding.

Một lần kiểm tra `gcloud storage buckets get-iam-policy` hoặc `gcloud projects get-iam-policy` chỉ cho thấy policy trực tiếp của tài nguyên được hỏi. Vì vậy, để rà soát quyền toàn diện cần phân tích cả **nguồn cấp quyền ở ancestor** và xác định **permission cụ thể** cần quan tâm.

## 2. Các khái niệm cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Principal / identity** | Danh tính được cấp quyền: user, group, service account, domain hoặc workload identity | `user:dev@example.com`, `group:auditors@example.com` |
| **Role** | Tập hợp những permission | `roles/storage.objectViewer` |
| **Permission** | Hành động cụ thể được kiểm soát bởi IAM | `storage.objects.get`, `resourcemanager.projects.setIamPolicy` |
| **Allow policy** | Chính sách gồm các role bindings cấp quyền có thể đi kèm điều kiện | Nhóm A được cấp role B trên project C |
| **Resource** | Đối tượng đích: project, bucket, service account và nhiều loại tài nguyên khác | `//cloudresourcemanager.googleapis.com/projects/123456789012` |
| **Ancestor** | Tài nguyên cấp trên trong hierarchy | Organization → Folder → Project |
| **Query scope** | Phạm vi tổ chức/project/folder mà Policy Analyzer được yêu cầu phân tích | `organizations/987654321098` |
| **Condition** | Biểu thức giới hạn khi nào một allow binding áp dụng | Chỉ có hiệu lực trước một thời điểm nhất định |
| **Effective access** | Khả năng thực tế sử dụng permission sau khi tính thêm deny, boundary, policy khác và ngữ cảnh | Một người có allow binding nhưng vẫn bị IAM Deny chặn |

Phân biệt **role** và **permission** là rất quan trọng. Câu hỏi “Ai có `roles/editor`?” khác với “Ai được `storage.objects.get`?”. Permission có thể xuất hiện trong nhiều vai trò khác nhau, bao gồm predefined hoặc custom roles. Khi điều tra một hành động cụ thể, nên tìm theo **permission** nếu biết tên permission đúng.

## 3. Policy Analyzer làm việc như thế nào?

**Policy Analyzer for allow policies** thuộc bộ công cụ Policy Intelligence và sử dụng khả năng phân tích IAM policies của **Cloud Asset Inventory**. Bạn cung cấp một **analysis query** để tìm role bindings theo các tiêu chí:

- **Principal:** ai đang được phân tích?
- **Access:** role hoặc permission nào?
- **Resource:** tài nguyên đích nào?
- **Scope:** phân tích trong organization, folder hay project nào?
- **Condition context:** trong một số trường hợp, thời điểm giả định để đánh giá điều kiện IAM.

Thông thường chỉ cần chỉ định một hoặc hai tiêu chí tìm kiếm; các trường còn lại trở thành phần cần khám phá trong kết quả.

~~~mermaid
flowchart LR
    Q["Câu hỏi rà soát quyền"] --> S["Chọn query scope"]
    S --> I["Chọn principal (tùy chọn)"]
    I --> A["Chọn role / permission (tùy chọn)"]
    A --> R["Chọn resource (tùy chọn)"]
    R --> C["Policy Analyzer đọc các IAM allow bindings liên quan"]
    C --> K["Kết quả: binding, principal, access, resource, condition"]
    K --> V["Đánh giá giới hạn và xác minh tiếp nếu cần"]
~~~

### 3.1. Ba loại câu hỏi điển hình

| Câu hỏi nghiệp vụ | Trường truy vấn nên cung cấp | Nội dung cần xem |
| --- | --- | --- |
| Ai được phép đọc bucket chứa dữ liệu xuất đơn hàng? | Resource + permission `storage.objects.get` | Principal, nhóm, binding và tài nguyên gắn policy |
| Developer A có vai trò nào đối với project production? | Principal + resource | Những role bindings phù hợp và nơi cấp quyền |
| Service account triển khai có thể thay đổi tài nguyên nào? | Principal + permission quan trọng | Danh sách resource/binding trong phạm vi phân tích |
| Ai có quyền thay đổi IAM policy project? | Permission `resourcemanager.projects.setIamPolicy` | Principal được cấp quyền, đặc biệt quyền rộng ở cấp cao |
| Ai có thể impersonate service account triển khai? | Service account resource + permission impersonation và tùy chọn phân tích impersonation | Quyền đại diện danh tính và chuỗi cấp quyền tiềm năng |

**Không nên dùng query quá rộng làm mặc định.** Một organization có nhiều project, nhóm và policy có thể tạo kết quả lớn. Nên bắt đầu từ tài nguyên và permission cần điều tra rồi mở rộng phạm vi khi có lý do.

### 3.2. Query scope khác resource filter

**Scope** quyết định tập IAM allow policies mà truy vấn được phép/phải xem: tại organization, folder hoặc project đó và phần tài nguyên con trong phạm vi. **Resource filter** xác định tài nguyên bạn muốn biết quyền đối với nó.

Ví dụ:

- Scope là `projects/commerce-prod`: truy vấn chủ yếu xem policies trong project và những tài nguyên con được hỗ trợ.
- Scope là `organizations/987654321098`, filter là project `commerce-prod`: phân tích có thể xét thêm allow bindings ở ancestor (organization/folder) tác động tới project đó.

Điểm dễ bỏ sót: nếu chỉ chạy scope ở **project**, kết quả có thể chưa bao quát các binding **được gắn ở folder/organization cấp trên**. Khi cần kết luận toàn bộ quyền được kế thừa của một tài nguyên, hãy chọn scope đủ cao và có quyền xem phù hợp.

## 4. Giới hạn của Policy Analyzer: chỉ phân tích IAM allow policies

Đây là giới hạn quan trọng nhất của bài. Policy Analyzer for allow policies phân tích **những quyền được IAM allow bindings cấp theo policy**, không tự đánh giá đầy đủ mọi cơ chế kiểm soát truy cập có thể khiến lời gọi API thành công hoặc thất bại.

Theo tài liệu Google Cloud, công cụ này **không tính** một số lớp kiểm soát như:

- **IAM Deny policies**.
- **IAM Principal Access Boundary (PAB) policies**.
- **Kubernetes RBAC** trong GKE.
- **Cloud Storage ACLs** và **Cloud Storage public access prevention**.
- Các điều kiện, giới hạn riêng của dịch vụ hoặc bối cảnh request nằm ngoài phạm vi phân tích allow policy.

Ví dụ người dùng được gắn vai trò chứa `storage.objects.get` từ organization, nhưng một IAM Deny policy chặn permission đó tại tài nguyên liên quan. **Policy Analyzer vẫn có thể liệt kê allow binding**, dù yêu cầu đọc object thực tế bị từ chối.

~~~mermaid
flowchart TD
    A["IAM allow binding phù hợp"] --> B["Policy Analyzer có thể liệt kê quyền"]
    B --> C["Kiểm tra IAM Deny / PAB / điều kiện khác"]
    C --> D{"Kiểm soát cuối cùng cho phép?"}
    D -->|Có| E["Có thể tiếp tục kiểm tra yêu cầu API thực tế"]
    D -->|Không| F["Request bị từ chối dù có allow binding"]
~~~

Vì vậy, khi viết báo cáo, dùng câu **“được cấp quyền theo IAM allow policy”** thay vì khẳng định chắc chắn **“có thể truy cập tài nguyên”**. Nếu câu hỏi là tại sao một principal sử dụng một permission cụ thể bị chặn, phối hợp với **Policy Troubleshooter**.

### 4.1. Kế thừa IAM

Policy Analyzer có thể phân tích các binding liên quan trong hierarchy khi **scope** đủ bao quát. Ví dụ nhóm vận hành được gắn role tại folder Production; không có binding trực tiếp trong project nhưng vẫn có grant được kế thừa. Truy vấn từ scope organization có thể chỉ ra nơi grant bắt nguồn.

### 4.2. IAM Conditions

Nếu một allow binding có **điều kiện**, Policy Analyzer trả về thông tin condition. Một số điều kiện liên quan thuộc tính tài nguyên có thể được đánh giá tự động; điều kiện dựa vào thời gian cần cung cấp **access time** qua CLI/API để đánh giá tại thời điểm giả định.

Khi không đủ ngữ cảnh để đánh giá, kết quả có thể được đánh dấu **`CONDITIONAL`**. Không được xem `CONDITIONAL` là tương đương `TRUE`. Điều kiện có thể là căn cứ để yêu cầu kiểm chứng bổ sung.

### 4.3. Độ tươi của dữ liệu và tính đầy đủ

Policy Analyzer dựa trên Cloud Asset API, có độ tươi dữ liệu theo **best effort**; thay đổi IAM gần đây thường xuất hiện sau một khoảng thời gian nhưng có thể chưa được phản ánh ngay. Truy vấn Console còn có thể bị giới hạn thời gian và hiển thị **kết quả chưa đầy đủ**. API có trường `fullyExplored` báo khả năng khám phá đầy đủ của kết quả phân tích; nên xem khi dùng kết quả để tự động hóa hoặc làm bằng chứng kiểm toán.

Nếu mới thu hồi một role lúc 10:01, kết quả phân tích lúc 10:02 vẫn có thể phản ánh trạng thái trước đó. Đừng dựa riêng vào một bản chụp để xác nhận một thay đổi quyền vừa được áp dụng.

## 5. Phân biệt Policy Analyzer với những công cụ liên quan

| Công cụ | Câu hỏi chính | Giới hạn/cách dùng |
| --- | --- | --- |
| **Policy Analyzer for allow policies** | Ai được gắn role/permission nào đối với tài nguyên nào qua IAM allow? | Phân tích binding, inheritance và một số conditions; không đánh giá đầy đủ deny/PAB |
| **Policy Troubleshooter** | Principal X có sử dụng được permission Y trên resource Z theo các chính sách được hỗ trợ không, và vì sao? | Hữu ích cho câu hỏi một principal–permission–resource, gồm allow/deny/PAB tùy hỗ trợ |
| **IAM Recommender** | Những quyền nào có thể giảm theo tín hiệu sử dụng và thông tin phân tích? | Là gợi ý; cần xem workload, chu kỳ công việc và yêu cầu vận hành trước khi áp dụng |
| **Cloud Asset Inventory / Policy Search** | Những IAM policies/tài nguyên nào tồn tại trong phạm vi? | Hữu ích để kiểm kê; một binding riêng chưa chắc phản ánh quyền được kế thừa |
| **`gcloud ... get-iam-policy`** | Policy trực tiếp gắn tại tài nguyên này là gì? | Không tự đưa ra bức tranh toàn bộ hierarchy |
| **Organization Policy Analyzer** | Các Organization Policy constraints/ràng buộc có hiệu lực hoặc ảnh hưởng thế nào? | Phục vụ ràng buộc cấu hình tổ chức, khác IAM allow bindings |
| **Cloud Audit Logs** | Hành động API nào đã diễn ra, do principal nào thực hiện, trong phạm vi log được bật/ghi nhận? | Là dấu vết thực tế; không thay thế kiểm kê quyền được cấp |

Những công cụ này bổ sung cho nhau. Khi rà soát rủi ro “ai có thể thay đổi policy”, thường bắt đầu từ Policy Analyzer. Khi một nhóm vừa bị lỗi `403 PERMISSION_DENIED`, Policy Troubleshooter phù hợp hơn để phân tích quyền đối với một yêu cầu cụ thể.

## 6. Chuẩn bị quyền và môi trường phân tích

Để đọc chính sách và chạy phân tích, tài khoản cần quyền phù hợp trên **query scope**; một vai trò thường được dùng là **Cloud Asset Viewer** (`roles/cloudasset.viewer`). Nếu phân tích custom IAM roles, có thể cần **Role Viewer** (`roles/iam.roleViewer`). Khi chạy bằng Google Cloud CLI, có thể cần **Service Usage Consumer** (`roles/serviceusage.serviceUsageConsumer`) trên consumer project.

Các permission liên quan tới Cloud Asset IAM Policy Analysis gồm:

~~~text
cloudasset.assets.analyzeIamPolicy
cloudasset.assets.searchAllIamPolicies
cloudasset.assets.searchAllResources
~~~

Ngoài ra, cần:

- **Cloud Asset API** được bật ở project sử dụng API nếu chưa bật.
- Tài khoản/ADC phù hợp với cách gọi qua Console, CLI hoặc API.
- Định danh organization/folder/project chính xác.
- Quyền liên quan đến Google Workspace group hoặc custom roles nếu muốn mở rộng thông tin.
- Hiểu giới hạn quota, tính năng và chi phí truy vấn; với môi trường lớn nên kiểm tra tài liệu giá và giới hạn hiện hành.

**Nguyên tắc phân quyền:** người cần audit toàn organization phải được cấp quyền đọc ở phạm vi tương ứng theo chính sách tổ chức, không cần `roles/owner` chỉ để xem kết quả. Nếu quyền chỉ cho phép phạm vi project, không nên diễn giải kết quả như một cuộc kiểm toán organization đầy đủ.

## 7. Thực hành trên Google Cloud Console

Giả sử nhóm Security muốn biết những principal được cấp quyền quản trị IAM trên một project production.

1. Mở Google Cloud Console và vào trang **Policy analyzer** trong nhóm Policy Intelligence.
2. Trong khu vực phân tích policy, chọn **Create custom query**.
3. Chọn **query scope** đủ cao để bao gồm các ancestor cần xét; ví dụ organization nếu cần truy vết quyền kế thừa.
4. Chọn **Permission** và nhập `resourcemanager.projects.setIamPolicy`; nếu giao diện hỗ trợ, thêm filter **Resource** là project cần kiểm tra.
5. Chạy truy vấn, xem kết quả theo principal, role binding, nguồn policy và tài nguyên được ảnh hưởng.
6. Nếu có nhóm, điều kiện hoặc service account, xem các tùy chọn mở rộng, giữ lại phạm vi và ngữ cảnh phân tích.
7. Kiểm tra trạng thái hoàn tất của truy vấn. Nếu giao diện báo kết quả chưa đầy đủ, không kết luận danh sách cuối cùng là đầy đủ.
8. Ghi nhận kết quả để làm đầu vào cho người sở hữu IAM review, không tự sửa quyền chỉ dựa trên một truy vấn.

Tên nút/nhãn có thể thay đổi theo phiên bản Console; tài liệu chính thức ở cuối bài cung cấp đường dẫn để đối chiếu.

### Mẹo thiết kế query

Đừng bắt đầu bằng “liệt kê toàn bộ quyền trong organization” nếu câu hỏi là “ai có thể thay đổi IAM của một project?”. Hãy lọc **resource + permission** trước, sau đó mở rộng nhóm/role chỉ khi cần để điều tra. Cách này giúp giảm khối lượng kết quả và dễ gắn hành động với rủi ro thực tế.

## 8. Thực hành bằng Google Cloud CLI

Các lệnh trong phần này **chỉ phân tích/đọc**, không sửa IAM. Chúng cần Cloud Asset API, quyền thích hợp và tài khoản đã đăng nhập.

### 8.1. Kiểm tra tài khoản và định danh

~~~bash
gcloud auth list
gcloud config get-value project
gcloud organizations list
~~~

Giá trị ví dụ sau chỉ dùng minh họa:

~~~text
Organization ID: 987654321098
Project ID: commerce-prod-example
Project number: 123456789012
Principal: user:reviewer@example.com
~~~

**Project ID khác project number.** Khi dùng `--project` ở scope, có thể dùng ID hoặc number theo hỗ trợ của command. Với `--full-resource-name`, phải dùng định dạng **full resource name** của loại tài nguyên, không chỉ nhập display name.

### 8.2. Ai có quyền thay đổi IAM policy của project?

~~~bash
gcloud asset analyze-iam-policy \
  --organization=987654321098 \
  --full-resource-name="//cloudresourcemanager.googleapis.com/projects/123456789012" \
  --permissions="resourcemanager.projects.setIamPolicy"
~~~

Truy vấn sử dụng scope organization để xem các allow bindings liên quan, kể cả quyền có thể được kế thừa. Câu hỏi tương đương: **“Theo IAM allow policies, principal nào được cấp permission `resourcemanager.projects.setIamPolicy` đối với project này?”**

Khi xem kết quả, tìm role binding chứa permission, nơi policy được gắn và principal liên quan; xác minh rằng resource name và project number đúng đích.

### 8.3. Một người có những quyền nào trong project?

~~~bash
gcloud asset analyze-iam-policy \
  --organization=987654321098 \
  --full-resource-name="//cloudresourcemanager.googleapis.com/projects/123456789012" \
  --identity="user:reviewer@example.com"
~~~

Truy vấn này tìm allow bindings phù hợp với principal được chỉ định đối với project. Khi cần khám phá **tư cách thành viên group** và vai trò do group cấp, phải xem thiết lập **group expansion**, quyền xem thành viên nhóm và những giới hạn liên quan. Không mặc định tìm một email cá nhân sẽ tự liệt kê mọi quyền nó có gián tiếp qua group mà không có cấu hình/phương pháp kiểm chứng phù hợp.

### 8.4. Service account có được cấp một permission trên những tài nguyên nào?

~~~bash
gcloud asset analyze-iam-policy \
  --organization=987654321098 \
  --identity="serviceAccount:deploy-bot@commerce-prod-example.iam.gserviceaccount.com" \
  --permissions="resourcemanager.projects.setIamPolicy"
~~~

Truy vấn theo principal + permission giúp phát hiện những allow bindings cấp quyền thay đổi policy trên tài nguyên trong phạm vi organization. Để giảm kết quả, có thể chuyển sang một folder/project scope khi mục tiêu kiểm tra hẹp, nhưng phải hiểu rằng quyền được gắn ở ancestor nằm ngoài scope có thể không được đưa vào.

### 8.5. Kiểm tra quyền theo thời gian của conditional binding

~~~bash
gcloud asset analyze-iam-policy \
  --organization=987654321098 \
  --identity="user:temporary-reviewer@example.com" \
  --full-resource-name="//cloudresourcemanager.googleapis.com/projects/123456789012" \
  --access-time="2026-11-20T09:00:00Z"
~~~

`--access-time` cung cấp thời điểm giả định (RFC 3339/ISO 8601 có múi giờ) để công cụ đánh giá loại điều kiện thời gian được hỗ trợ. Không phải mọi loại IAM Condition đều có thể kết luận chỉ bằng một thời điểm; đọc kết quả `TRUE`/`CONDITIONAL` và ngữ cảnh.

### 8.6. Điều tra khả năng impersonate service account

Tùy chọn nâng cao của CLI cho phép phân tích tiếp các đường impersonation được phản ánh trong IAM allow policies:

~~~bash
gcloud asset analyze-iam-policy \
  --organization=987654321098 \
  --permissions="storage.objects.get" \
  --analyze-service-account-impersonation
~~~

Trong phân tích bổ sung, Policy Analyzer có thể xét các permission liên quan đến việc đại diện service account như `iam.serviceAccounts.getAccessToken`, `iam.serviceAccounts.signJwt` và `iam.serviceAccounts.actAs`. **Các permission này phục vụ những cơ chế khác nhau**; một binding `actAs` không tự chứng minh principal có thể trực tiếp lấy OAuth access token bằng IAM Credentials API.

Dùng kết quả impersonation như **tín hiệu cần điều tra** rồi xác minh lại IAM và cơ chế phát hành credential thực tế. Với organization lớn, truy vấn impersonation không lọc tài nguyên có thể sinh rất nhiều kết quả; nên thêm resource hoặc permission filter thích hợp trước khi chạy.

### 8.7. Khi nào bật các tùy chọn mở rộng?

Một số tùy chọn được hỗ trợ bởi CLI/API:

| Tùy chọn | Tác dụng | Điều cần lưu ý |
| --- | --- | --- |
| `--expand-groups` | Mở rộng group thành thành viên khi có quyền/điều kiện thích hợp | Có giới hạn số thành viên, nested group và quyền xem group; chỉ hiệu quả ở các kiểu query phù hợp |
| `--expand-roles` | Hiển thị permissions trong vai trò | Có điều kiện sử dụng; tài liệu nêu chỉ khả dụng khi query không chỉ định roles/permissions |
| `--expand-resources` | Liệt kê tài nguyên con liên quan trong kết quả | Có giới hạn số tài nguyên; không bảo đảm mở rộng hết cây lớn |
| `--analyze-service-account-impersonation` | Phân tích thêm những principal có đường impersonation thích hợp | Không thay thế kiểm chứng quyền hiệu lực |
| `--access-time` | Cung cấp ngữ cảnh thời gian để đánh giá IAM Condition | Không thể đánh giá mọi điều kiện chỉ bằng thời gian |

Không cần bật tất cả tùy chọn cho mọi truy vấn. Hãy bật đúng thứ đang giải quyết câu hỏi và ghi lại phương án query để người khác tái lập kết quả.

## 9. Đọc kết quả phân tích sao cho đúng

Một truy vấn Policy Analyzer có thể trả về thông tin như:

- **Binding:** vai trò được cấp, các principal trong binding và IAM Condition nếu có.
- **Policy attachment:** tài nguyên nơi binding được gắn.
- **Access:** role/permission liên quan tới câu hỏi.
- **Resources:** tài nguyên được nhắm đến hoặc những tài nguyên con liên quan khi bật expansion.
- **Principal/group details:** danh tính phù hợp và thông tin mở rộng được phép xem.
- **Condition evaluation:** giá trị `TRUE`, `CONDITIONAL` hoặc trạng thái khác theo ngữ cảnh/cơ chế hỗ trợ.
- **Exploration/completeness:** truy vấn đã khám phá đầy đủ kết quả hay chưa (đặc biệt trong API).

Ví dụ kết quả minh họa có thể được diễn giải:

~~~text
Scope: organizations/987654321098
Resource: //cloudresourcemanager.googleapis.com/projects/123456789012
Permission: resourcemanager.projects.setIamPolicy

Binding source: organizations/987654321098
Role: roles/resourcemanager.projectIamAdmin
Principal: group:platform-admins@example.com
Condition: none
Interpretation:
  Nhóm platform-admins được cấp một allow binding có permission liên quan
  ở cấp organization, nên cần rà soát phạm vi kế thừa xuống project.
~~~

Đây chỉ là **ví dụ diễn giải**, không phải phản hồi API thực tế. Khi làm việc với dữ liệu thật, role ID, resource name, condition và IAM bindings cần lấy từ hệ thống.

### 9.1. Kết quả trống có ý nghĩa gì?

**“Không tìm thấy binding trong kết quả này”** chỉ là nhận xét về truy vấn với scope, filter, quyền xem, tùy chọn expansion, thời điểm và độ tươi dữ liệu hiện tại. Chưa đủ để khẳng định “không ai có quyền” khi:

- Scope không bao gồm ancestor nơi quyền được cấp.
- Principal nhận quyền gián tiếp qua group hoặc service account impersonation.
- Query đã hết thời gian hoặc bị giới hạn kết quả.
- Dữ liệu Cloud Asset chưa phản ánh cập nhật mới.
- Tài nguyên bị kiểm soát bởi cơ chế riêng khác IAM allow.
- Tài khoản chạy truy vấn thiếu quyền xem thông tin cần thiết.

Báo cáo audit cần giữ lại các điều kiện này, đặc biệt khi sử dụng kết quả như bằng chứng để phê duyệt thay đổi.

## 10. Rà soát nhóm, điều kiện và service account

### 10.1. Google Group và danh tính gián tiếp

Nếu binding cấp quyền cho `group:platform-admins@example.com`, Policy Analyzer có thể báo group thay vì từng người. Muốn biết user cụ thể nào nằm trong nhóm, cần xem membership hoặc dùng **group expansion** khi đáp ứng quyền/giới hạn.

Dù đã expand, vẫn cần chú ý nhóm lồng nhau và trạng thái membership tại thời điểm rà soát. Không nên giả định nhóm được quản trị tốt chỉ từ tên hiển thị; hãy xác định chủ sở hữu, quy trình cấp quyền và lịch kiểm tra thành viên.

### 10.2. Conditional bindings

Ví dụ một allow binding chỉ có hiệu lực trước một thời điểm nhất định. Để đánh giá, cần cung cấp context. Nếu kết quả là `CONDITIONAL`, người rà soát phải tiếp tục xác minh trước khi kết luận quyền đó có hiệu lực trong mọi tình huống.

Một review thực tế nên ghi:

| Trường | Ví dụ |
| --- | --- |
| Principal | `group:prod-operators@example.com` |
| Role/permission | Quyền đọc metadata project |
| Nơi cấp | Folder Production |
| Resource chịu ảnh hưởng | Project Commerce production |
| Condition | Chỉ áp dụng trong cửa sổ cho phép |
| Kết quả Analyzer | `CONDITIONAL` |
| Việc tiếp theo | Xác minh condition và dùng Policy Troubleshooter với tình huống cụ thể |

### 10.3. Service account và impersonation

Một service account có thể được cấp quyền đọc bucket; đồng thời principal khác có quyền **đại diện** service account đó theo các cơ chế IAM. Rà soát chỉ email của service account sẽ không phát hiện hết các tuyến truy cập tiềm năng.

Ví dụ trong hệ thống CI/CD: `deploy-bot` có quyền triển khai Cloud Run nhưng developer chỉ được cấp quyền impersonate service account trong môi trường dev. Nếu không kiểm tra tuyến impersonation và scope, một đường cấp quyền ngoài dự kiến có thể bị bỏ sót.

Cần phân biệt **được phép gắn service account vào workload**, **được tạo access token đại diện service account** và **được cấp role đối với tài nguyên đích**. Chúng là những permission và điều kiện khác nhau.

## 11. Quy trình rà soát quyền định kỳ

Một lần chạy truy vấn là bước đầu; giá trị của Policy Analyzer đến từ quy trình có người phụ trách, tiêu chí rủi ro và kiểm chứng sau thay đổi.

~~~mermaid
flowchart TD
    A["Chọn tài nguyên nhạy cảm và owner"] --> B["Xác định principal / permission cần rà soát"]
    B --> C["Chạy Policy Analyzer với scope phù hợp"]
    C --> D["Ghi binding, nguồn cấp, condition, kết quả đầy đủ"]
    D --> E{"Có quyền rộng hoặc đường truy cập đáng ngờ?"}
    E -->|Có| F["Xác minh bằng Policy Troubleshooter, owner và audit"]
    E -->|Không| G["Lưu bằng chứng và lập lịch review"]
    F --> H["Đề xuất quyền tối thiểu / thay đổi có kiểm soát"]
    H --> I["Thực hiện sau phê duyệt theo quy trình"]
    I --> J["Kiểm chứng sau khi thay đổi và ghi quyết định"]
    J --> G
~~~

### Bước 1: Chọn phạm vi và mức độ quan trọng

Ưu tiên tài nguyên chứa dữ liệu nhạy cảm, service account triển khai, project production hoặc những permission có khả năng làm thay đổi cấu hình IAM/ứng dụng. Rà soát toàn organization có ích nhưng nên đi từ **câu hỏi cụ thể**.

Ví dụ ba kiểm tra định kỳ:

1. Ai được cấp `resourcemanager.projects.setIamPolicy` trên các project production?
2. Ai có thể đọc Cloud Storage bucket chứa dữ liệu khách hàng theo IAM allow?
3. Ai có thể impersonate những service account có quyền deploy Cloud Run hoặc quản trị GKE?

### Bước 2: Lấy baseline

Lưu ít nhất: thời điểm query, scope, filters, tùy chọn expansion, trạng thái hoàn tất, principal, role, permission, nguồn binding và người rà soát. Nếu phải cung cấp bằng chứng kiểm toán, lưu kết quả qua cơ chế được tổ chức duyệt thay vì chia sẻ toàn bộ danh sách quyền ngoài phạm vi cần thiết.

### Bước 3: Phân loại vấn đề

| Phát hiện | Rủi ro có thể có | Câu hỏi cần xác minh |
| --- | --- | --- |
| Role rộng ở organization | Quyền lan xuống nhiều project | Có cần phạm vi toàn organization hay chỉ folder? |
| Project production nhận quyền từ folder không phù hợp | Phân quyền theo môi trường bị lệch | Project đang nằm đúng parent chưa? |
| Nhóm có hàng trăm thành viên | Nhiều người có quyền gián tiếp | Membership nào còn cần, ai là owner nhóm? |
| Quyền impersonate service account nhiều đặc quyền | Có thể mở thêm tuyến truy cập | Principal có thật sự cần impersonation không? |
| Conditional grant không xác định | Khó đánh giá khi nào quyền có hiệu lực | Cần thêm access time hoặc context nào? |
| Không còn workload dùng một role | Dư thừa quyền có thể giảm | Có job theo lịch/đường khôi phục nào vẫn dùng? |

### Bước 4: Xác minh trước khi thay đổi

Dùng Policy Troubleshooter cho trường hợp một principal, permission và resource cụ thể; đối chiếu IAM Deny, PAB và policy riêng của dịch vụ khi cần. Nếu đề xuất xóa role, hãy kiểm tra với owner workload và lịch chạy job để tránh gián đoạn.

Quyền tối thiểu cần dựa vào **nhu cầu công việc thật**, không chỉ vào mức sử dụng được nhìn thấy trong một khoảng thời gian ngắn. Một permission chỉ dùng khi khôi phục thảm họa vẫn có thể là quyền hợp lệ, nhưng nên được kiểm soát theo cơ chế phù hợp.

### Bước 5: Thay đổi có kiểm soát và kiểm chứng

Sau khi người có thẩm quyền chấp thuận, thay đổi IAM tại **nơi role binding được cấp**. Nếu quyền đến từ organization, xóa role ở project không làm mất binding kế thừa. Nếu quyền đến từ group, xử lý membership có thể phù hợp hơn việc xóa binding cả nhóm.

Chạy lại query sau khi dữ liệu cập nhật, kiểm tra các request của workload liên quan và ghi lại lý do giữ hoặc thu hồi quyền. Đừng coi thời điểm chạy lại query tức thì là xác nhận cuối cùng vì Cloud Asset có độ trễ.

## 12. Tình huống thực tế: trước khi triển khai Cloud Run production

Nhóm Commerce muốn triển khai `orders-api` trên Cloud Run tại project `commerce-prod`, dùng Cloud Storage và Cloud SQL. Security yêu cầu xác nhận không có quyền triển khai hoặc quản trị rộng ngoài dự kiến.

**Cấu trúc dự kiến:**

~~~text
Organization: Atlas
└── Folder: Production
    └── Project: commerce-prod
        ├── Cloud Run: orders-api
        ├── Service account: orders-runtime
        ├── Cloud SQL: orders-db
        └── Cloud Storage: order-exports
~~~

**Bộ câu hỏi rà soát:**

| Đối tượng | Cần xác minh | Vì sao |
| --- | --- | --- |
| Project `commerce-prod` | Ai được `resourcemanager.projects.setIamPolicy`? | Phòng thay đổi IAM ngoài ý muốn |
| Service account `orders-runtime` | Ai có quyền impersonate/gắn vào workload? | Ngăn lạm dụng danh tính có quyền dữ liệu |
| Bucket `order-exports` | Ai được `storage.objects.get`? | Rà soát đường đọc dữ liệu nhạy cảm |
| CI/CD deployer | Có những role/permission nào trong production? | Giới hạn quyền triển khai |
| Group Production Operators | Những người nào là thành viên? | Giảm quyền gián tiếp ngoài ý muốn |

**Giả định phát hiện:** query phát hiện nhóm `dev-all@example.com` được cấp một role rộng tại organization, role này chứa permission quản trị đối với project production. Để xử lý:

1. Xác nhận binding gốc nằm ở organization hay folder nào.
2. Kiểm tra liệu role có thực sự chứa permission trong cấu hình hiện tại không.
3. Phân tích thành viên nhóm và điều kiện IAM liên quan.
4. Dùng Policy Troubleshooter với một principal cụ thể để xem ảnh hưởng của allow/deny/PAB.
5. Trao đổi với owner và lập thay đổi IAM tại scope thích hợp: thu hẹp scope, thay role hoặc điều chỉnh nhóm.
6. Sau thay đổi, thử lại pipeline deploy hợp lệ và xác minh không có đường truy cập ngoài ý muốn.

Cách này phù hợp với bài học GCP rộng hơn: khi triển khai Compute Engine, GKE, Cloud Run hoặc truy cập Cloud SQL/Storage, IAM review là phần của việc bảo vệ tài nguyên và duy trì độ tin cậy. Quyền quá rộng có thể gây rủi ro bảo mật và chi phí (ví dụ tạo tài nguyên ngoài dự kiến); quyền bị thu hồi nhầm có thể làm CI/CD hoặc ứng dụng ngừng hoạt động.

## 13. Truy vấn lớn, export và báo cáo

Khi organization có nhiều project và hàng nghìn IAM bindings, một truy vấn tương tác có thể bị giới hạn thời gian hoặc số lượng kết quả. Policy Analyzer hỗ trợ phân tích **long-running** để xuất kết quả sang BigQuery hoặc Cloud Storage thông qua API `analyzeIamPolicyLongrunning`.

Các điểm cần chuẩn bị:

- Xác định scope và filter đủ hẹp để trả lời câu hỏi kiểm toán.
- Cấp quyền đọc policy cần thiết và quyền ghi vào nơi xuất kết quả.
- Phân quyền cho BigQuery dataset hoặc Cloud Storage bucket chứa dữ liệu phân tích; bản thân danh sách IAM cũng là dữ liệu nhạy cảm về cấu trúc tổ chức.
- Đánh giá quota, giới hạn query, thời gian chạy và **chi phí** của tính năng theo tài liệu hiện hành.
- Xác minh trạng thái hoàn thành, độ tươi và thông tin còn thiếu trước khi chuyển dữ liệu thành báo cáo chính thức.

Ví dụ schema logic cho báo cáo nội bộ (minh họa, không phải output chuẩn của API):

~~~text
review_id
analysis_time
analysis_scope
resource_full_name
principal
role
permission
attached_policy_resource
condition
completeness
review_owner
decision
next_review_date
~~~

Lưu thêm **query options** giúp người kiểm toán khác tái hiện ý nghĩa kết quả. Đặc biệt, không nên cộng số dòng của một lần expand group với số binding rồi coi đó là số quyền độc lập; một grant có thể được biểu diễn thành nhiều principal sau expansion.

## 14. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| “Policy Analyzer nói có quyền tức API chắc chắn cho phép.” | Bỏ qua deny/PAB và cơ chế truy cập khác | Dùng đúng câu “theo IAM allow”; xác minh bằng Policy Troubleshooter |
| “Tôi đã xem IAM ở project nên biết mọi quyền kế thừa.” | Bỏ sót grant tại folder/organization | Chọn query scope đủ cao và xem nguồn binding |
| “Không có tên người dùng trong binding tức họ không có quyền.” | Bỏ sót thành viên group hoặc đường impersonation | Kiểm tra group membership và impersonation |
| “Mọi IAM Condition đều được đánh giá đầy đủ.” | Kết luận sai về quyền tại thời điểm cụ thể | Cung cấp ngữ cảnh và đọc trạng thái `CONDITIONAL` |
| “Kết quả trống nghĩa là chắc chắn không ai truy cập.” | Bỏ qua giới hạn scope, dữ liệu và quyền xem | Kiểm tra query, độ hoàn tất và phương pháp khác |
| “Rà soát càng rộng càng tốt.” | Kết quả nhiều, khó phân tích, tốn tài nguyên | Bắt đầu từ permission/resource rủi ro cao |
| “Thu hồi grant ở project là đủ.” | Grant kế thừa vẫn còn | Thay đổi tại nguồn binding thực sự |
| “Sau khi xóa role, query phải lập tức đổi.” | Dễ hiểu nhầm do độ trễ dữ liệu | Chờ cập nhật và xác minh bằng phương pháp phù hợp |
| “Policy Analyzer cũng kiểm tra Organization Policy constraints.” | Nhầm lớp quản trị | Dùng công cụ Organization Policy Analyzer cho câu hỏi về constraint |
| “Vai trò chưa được sử dụng gần đây thì có thể xóa ngay.” | Có thể gây lỗi cho job định kỳ hoặc khôi phục | Kết hợp owner review, usage signals và kế hoạch kiểm thử |

## 15. Bài tập tự kiểm tra

**Câu 1.** Nhóm `prod-operators` nhận role tại folder Production. Không có binding nào gắn trực tiếp vào project `commerce-prod`. Nhóm có thể vẫn được cấp quyền trên project theo IAM allow không?

*Gợi ý:* Có, nếu binding kế thừa phù hợp. Dùng Policy Analyzer với scope bao gồm folder/organization cần xét, thay vì chỉ xem IAM policy trực tiếp trên project.

**Câu 2.** Policy Analyzer trả kết quả một user được cấp permission `storage.objects.get` đối với bucket. Có thể kết luận người đó đọc được mọi object trong mọi trường hợp không?

*Gợi ý:* Không. Policy Analyzer for allow policies không đánh giá đầy đủ deny, PAB, ACL và mọi cơ chế dịch vụ; phải kiểm tra thêm ngữ cảnh và quyền hiệu lực.

**Câu 3.** Bạn cần biết **vì sao** `user:dev@example.com` nhận `403` khi gọi API trên một resource cụ thể. Nên dùng công cụ nào trước?

*Gợi ý:* Policy Troubleshooter phù hợp để kiểm tra principal–permission–resource và phân tích allow/deny/PAB được hỗ trợ. Policy Analyzer hữu ích để tìm những binding được cấp trên diện rộng.

**Câu 4.** Một IAM Condition dựa trên thời điểm truy cập xuất hiện trong kết quả dưới dạng `CONDITIONAL`. Nó có chắc đúng tại mọi thời điểm không?

*Gợi ý:* Không. Cần cung cấp `--access-time` hoặc ngữ cảnh tương ứng nếu loại điều kiện được hỗ trợ và đọc kết quả đánh giá.

**Câu 5.** Tại sao gán role vào một group có thể khiến danh sách người thực sự hưởng quyền nhiều hơn danh sách email xuất hiện trong IAM policy?

*Gợi ý:* Group binding áp dụng qua membership; có thể có nhóm lồng nhau và membership thay đổi theo thời gian. Cần group expansion/kiểm tra nhóm với quyền phù hợp.

**Câu 6.** Truy vấn ở scope project không tìm thấy admin grant, nhưng Security nghi ngờ grant đến từ organization. Điều chỉnh nào hữu ích nhất?

*Gợi ý:* Chạy lại ở scope organization (hoặc ancestor đủ rộng) và lọc project/permission cụ thể để tìm grant kế thừa.

**Câu 7.** Một principal được phép dùng `iam.serviceAccounts.actAs` trên service account. Điều đó có đồng nghĩa principal chắc chắn gọi được IAM Credentials API để lấy OAuth token của service account không?

*Gợi ý:* Không. `actAs` và `getAccessToken` là những permission khác nhau, phục vụ những hành động khác nhau. Phải phân tích cơ chế sử dụng cụ thể.

**Câu 8.** Sau khi chuyển quyền ở project production, kết quả Policy Analyzer trong vài phút đầu vẫn hiển thị binding cũ. Nên kết luận thay đổi thất bại?

*Gợi ý:* Chưa. Cloud Asset API có độ tươi theo best effort. Đối chiếu policy nguồn và chờ kết quả cập nhật, kết hợp kiểm tra hành vi cần thiết.

**Câu 9.** Khi nào nên sử dụng long-running analysis và xuất kết quả ra BigQuery/Cloud Storage?

*Gợi ý:* Khi quy mô kết quả lớn, cần phân tích kiểm toán chi tiết hoặc truy vấn tương tác chưa đầy đủ; phải kiểm soát quyền, hạn mức, chi phí và mức độ nhạy cảm của dữ liệu xuất.

## 16. Checklist thực hành rà soát quyền

- [ ] Ghi rõ câu hỏi bảo mật: principal, permission, resource nào cần xem?
- [ ] Xác định organization/folder/project scope đủ bao quát grant kế thừa.
- [ ] Kiểm tra tài khoản phân tích có quyền đọc policy cần thiết.
- [ ] Dùng filter cụ thể; không truy vấn quá rộng khi không cần.
- [ ] Ghi nơi gắn binding, role/permission, principal và IAM Condition.
- [ ] Kiểm tra group membership, đường impersonation và các tùy chọn expansion nếu có.
- [ ] Kiểm tra độ đầy đủ và độ tươi của kết quả.
- [ ] Với quyết định truy cập cụ thể, đối chiếu deny/PAB bằng Policy Troubleshooter khi thích hợp.
- [ ] Trao đổi với owner workload trước khi đề xuất giảm quyền.
- [ ] Kiểm chứng sau thay đổi theo phạm vi, thời điểm và phương pháp phù hợp.
- [ ] Lưu quyết định, nguồn bằng chứng, người thực hiện và chu kỳ review tiếp theo.

## 17. Những điều cần nhớ

- **Policy Analyzer for allow policies** trả lời câu hỏi về IAM allow bindings theo **ai – quyền gì – tài nguyên nào**.
- **Scope** quyết định nơi công cụ tìm policies; muốn xét grant kế thừa phải chọn phạm vi đủ cao.
- **Kết quả không phải quyền hiệu lực cuối cùng** vì còn IAM Deny, Principal Access Boundary, IAM Conditions và các cơ chế truy cập của dịch vụ.
- **Group, service account impersonation và custom roles** có thể khiến quyền gián tiếp khó nhận biết.
- **Policy Troubleshooter** phù hợp khi cần xem một principal có thể sử dụng một permission trên một resource cụ thể theo những policy được hỗ trợ hay không.
- Rà soát quyền phải gắn với **owner, bằng chứng, tác động tới workload và xác minh sau thay đổi**.

Khi triển khai Compute Engine, GKE, Cloud Run, Cloud Storage, Cloud SQL hoặc CI/CD trong mô-đun Google Cloud, hãy đặt ba câu hỏi trước khi cấp quyền: **“Ai thật sự cần quyền này? Quyền nên nằm ở project, folder hay tài nguyên cụ thể? Làm sao phát hiện và thu hồi quyền khi không còn cần?”** Policy Analyzer hỗ trợ trả lời bằng dữ liệu IAM allow; quy trình quản trị tốt biến dữ liệu đó thành quyết định an toàn.

## Tài liệu tham khảo chính thức

- [Policy Analyzer for allow policies — Overview](https://cloud.google.com/policy-intelligence/docs/policy-analyzer-overview)
- [Analyze allow policies](https://cloud.google.com/policy-intelligence/docs/analyze-iam-policies)
- [gcloud asset analyze-iam-policy](https://cloud.google.com/sdk/gcloud/reference/asset/analyze-iam-policy)
- [Cloud Asset Inventory API: analyzeIamPolicy](https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/analyzeIamPolicy)
- [IAM Policy Troubleshooter](https://cloud.google.com/policy-intelligence/docs/troubleshoot-access)
- [Policy Intelligence overview](https://cloud.google.com/policy-intelligence/docs/overview)
- [Cloud Asset Inventory roles and permissions](https://cloud.google.com/asset-inventory/docs/roles-permissions)

