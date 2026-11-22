# IAM Conditions và cấp quyền có điều kiện trên Google Cloud

> **Chương:** IAM và xác thực  
> **Bài học:** IAM Conditions và cấp quyền có điều kiện  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Quá trình lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí đòi hỏi kiểm soát quyền chặt chẽ: cùng một kỹ sư có thể cần xem log hằng ngày nhưng chỉ cần quyền bổ sung trong thời gian xử lý sự cố.

**IAM Conditions** cho phép kết hợp vai trò IAM với biểu thức điều kiện để quyết định **khi nào** một quyền được cấp. Ví dụ, một nhóm có thể xem log của project đến hết phiên hỗ trợ, hoặc chỉ truy cập một nhóm tài nguyên có tên/nhãn phân loại phù hợp. Quyền cuối cùng vẫn phụ thuộc vào toàn bộ chính sách IAM hiện hành, bao gồm quyền kế thừa, điều kiện trên các binding khác, deny policy và các giới hạn truy cập liên quan.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt IAM role binding thông thường với **conditional role binding** và cách biểu thức điều kiện tham gia đánh giá quyền.
2. Đọc, viết và giải thích điều kiện bằng tập con của **Common Expression Language (CEL)**.
3. Chọn đúng thuộc tính như `request.time`, `resource.type`, `resource.name` và `resource.matchTag()`; nhận ra giới hạn theo dịch vụ và loại policy.
4. Tạo một binding có thời hạn trên project qua Console hoặc `gcloud`, đọc lại, thử quyền và thu hồi an toàn.
5. Phát hiện trường hợp **binding vô điều kiện**, quyền kế thừa hoặc nhiều binding khiến điều kiện mới không tạo ra giới hạn mong muốn.
6. Thiết kế ví dụ cấp quyền cho môi trường development/production, Cloud Storage và đội xử lý sự cố mà không nhầm IAM Conditions với cơ chế bảo vệ mạng hay xác thực.
7. Điều tra lỗi truy cập bằng IAM Policy Troubleshooter, audit log và kiểm tra tài nguyên/thuộc tính được hỗ trợ.

## 2. IAM Conditions nằm ở đâu trong hệ thống IAM?

### 2.1. IAM allow policy và role binding

Trong mô hình IAM thông thường, một **principal** (người dùng, nhóm, service account hoặc danh tính liên kết được hỗ trợ) nhận một **role** trên một tài nguyên. Role chứa nhiều **permission**; các binding trên organization, folder hoặc project có thể được kế thừa bởi tài nguyên con.

~~~text
Organization
└── Folder
    └── Project: gcp-app-prod
        ├── Cloud Run service
        ├── Cloud SQL instance
        ├── Compute Engine VM
        └── Cloud Storage bucket
~~~

Một binding trong allow policy có cấu trúc khái niệm:

~~~yaml
bindings:
  - role: roles/logging.viewer
    members:
      - group:incident-response@example.com
    condition:
      title: TemporaryLogAccess
      description: Chỉ phục vụ đợt xử lý sự cố
      expression: "request.time < timestamp('2027-01-15T18:00:00Z')"
version: 3
~~~

Đây là **đoạn minh họa**, chưa phải policy đầy đủ để dùng trực tiếp cho lệnh ghi đè. Các IAM policy thực tế còn có thể chứa `etag`, nhiều binding và phiên bản policy. Khi sửa policy phải giữ các binding đang có và bảo vệ tính đồng thời bằng cơ chế do API hỗ trợ.

Ở ví dụ, nhóm nhận vai trò `roles/logging.viewer` theo scope gán binding, nhưng **chỉ khi thời điểm truy cập sớm hơn mốc UTC đã định**. Mốc `2027-01-15T18:00:00Z` là giả định cho bài học; khi áp dụng thật, dùng thời hạn do chủ tài nguyên phê duyệt.

### 2.2. Điều kiện không phải một “deny” mặc định

Với **allow policy**, điều kiện gắn vào binding chỉ kiểm soát **binding ấy có cấp quyền hay không**. Nếu điều kiện không đúng, binding không cấp quyền; tuy nhiên, principal vẫn có thể được cấp cùng permission từ binding khác hoặc từ tài nguyên cha.

~~~mermaid
flowchart TD
    R["Principal gọi một API trên tài nguyên"] --> A{"Có binding allow hợp lệ\ncho permission cần thiết?"}
    A -->|Không| N["Không được cấp quyền từ allow"]
    A -->|Có điều kiện| C{"Biểu thức condition = true?"}
    A -->|Binding vô điều kiện| G["Có grant từ allow"]
    C -->|Có| G
    C -->|Không hoặc không đánh giá được| N
    G --> D{"Deny policy / PAB /\nkiểm soát liên quan cho phép?"}
    D -->|Có| Y["Có thể được phép gọi API"]
    D -->|Không| X["Từ chối truy cập"]
    N --> X
~~~

Sơ đồ đơn giản hóa trình tự đánh giá để học; thực tế IAM xét các policy có liên quan theo quy tắc của từng loại. **Điều kiện đúng là cần, nhưng chưa đủ** để gọi API thành công nếu deny policy, Principal Access Boundary (PAB), kiểm soát tổ chức, trạng thái dịch vụ hoặc các yêu cầu khác chặn thao tác.

### 2.3. Bốn trường hợp dễ nhầm

| Trạng thái | Kết quả cần hiểu |
|---|---|
| Chỉ có một binding có điều kiện và điều kiện `true` | Binding đó cấp role trong phạm vi của nó, miễn không bị kiểm soát khác chặn |
| Chỉ có binding có điều kiện nhưng điều kiện `false` hoặc thiếu thuộc tính trong ngữ cảnh | Binding không cấp quyền theo cơ chế allow |
| Có thêm binding **vô điều kiện** cấp cùng permission | Binding vô điều kiện vẫn có thể cấp quyền dù binding có điều kiện hết hạn |
| Có binding allow hợp lệ nhưng deny policy hoặc PAB chặn | Yêu cầu vẫn bị từ chối theo đánh giá policy cuối cùng |

Ví dụ: bạn thêm binding tạm thời `roles/logging.viewer` cho `alice@example.com`, nhưng Alice đã có `roles/logging.viewer` vô điều kiện từ nhóm khác tại organization. Khi điều kiện hết hạn, Alice **vẫn có quyền xem log** từ binding kế thừa. Muốn giới hạn thời gian thực sự, phải rà soát **đường cấp quyền hiệu lực**, không chỉ nhìn binding mới nhất.

## 3. Cấu trúc biểu thức và ngôn ngữ CEL

Điều kiện IAM thường có ba thuộc tính:

| Trường | Bắt buộc? | Ý nghĩa |
|---|---|---|
| `title` | Có | Tên giúp nhận diện điều kiện, ví dụ `IncidentAccessUntilJan15` |
| `description` | Không | Mục đích nghiệp vụ, ticket, người phê duyệt, mốc hết hạn |
| `expression` | Có | Biểu thức logic CEL đánh giá theo ngữ cảnh của yêu cầu |

CEL ở IAM Conditions hỗ trợ một **tập con** của ngôn ngữ CEL, gồm toán tử so sánh, hàm theo loại dữ liệu và toán tử logic. Không thể tự ý gọi hàm JavaScript, Python, truy vấn HTTP hoặc dữ liệu bên ngoài khi đánh giá quyền.

### 3.1. Phép so sánh và logic

~~~cel
// Ví dụ A: Quyền chỉ có hiệu lực trước một thời điểm.
request.time < timestamp('2027-01-15T18:00:00Z')

// Ví dụ B: Quyền chỉ có hiệu lực trong một khoảng thời gian.
request.time >= timestamp('2027-01-10T00:00:00Z') &&
request.time < timestamp('2027-01-15T18:00:00Z')

// Ví dụ C: Loại tài nguyên khớp và tên có prefix xác định.
resource.type == 'compute.googleapis.com/Instance' &&
resource.name.startsWith('projects/example-proj/zones/asia-southeast1-a/instances/dev-')
~~~

Ba đoạn biểu thức trên được trình bày để đọc hiểu; comment `//` là lời giải thích trong ví dụ, khi nhập vào Condition editor hãy dùng **biểu thức hợp lệ**, không sao chép nhiều ví dụ vào một trường.

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| `&&` | AND: tất cả mệnh đề phải đúng | Thời gian **và** resource type |
| `\|\|` | OR: có ít nhất một mệnh đề đúng | Nhóm tài nguyên A **hoặc** B |
| `!` | NOT: phủ định | `!resource.matchTag(...)` |
| `==`, `!=` | Bằng/khác | `resource.type == '...'` |
| `<`, `<=`, `>`, `>=` | So sánh | `request.time < timestamp('...')` |
| `startsWith()`, `endsWith()` | So tiền tố/hậu tố của chuỗi ở thuộc tính hỗ trợ | `resource.name.startsWith('projects/...')` |

Dùng dấu ngoặc `(...)` để tránh hiểu sai thứ tự ưu tiên, nhất là khi kết hợp `&&` và `\|\|`. Một điều kiện với toán tử OR quá rộng có thể mở rộng quyền ngoài ý định:

~~~cel
// Chỉ minh họa rủi ro: quyền có thể được cấp nếu EITHER mệnh đề đúng.
resource.matchTag('123456789012/environment', 'dev') ||
request.time < timestamp('2027-01-15T18:00:00Z')
~~~

Nếu mong muốn “**phải là môi trường dev và chưa hết hạn**”, cần dùng `&&`.

### 3.2. Thời gian và múi giờ

`request.time` biểu thị thời điểm xử lý yêu cầu. So sánh với `timestamp('...Z')` thường dễ kiểm toán vì `Z` biểu thị UTC. Với lịch làm việc theo giờ địa phương, CEL có các hàm lấy thành phần thời gian và tham số múi giờ được hỗ trợ, nhưng phải kiểm tra cụ thể biểu thức và xử lý ngày nghỉ/đổi giờ nếu liên quan.

Ví dụ thời hạn tại Việt Nam: **18:00 ngày 15/01/2027 (UTC+7)** tương đương **11:00 UTC ngày 15/01/2027**. Muốn hết hạn tại 18:00 giờ Việt Nam, biểu thức dùng:

~~~cel
request.time < timestamp('2027-01-15T11:00:00Z')
~~~

Không dùng `2027-01-15T18:00:00Z` nếu nghiệp vụ muốn 18:00 giờ Việt Nam; cách viết đó sẽ hết hạn vào 01:00 sáng hôm sau theo giờ Việt Nam.

## 4. Các nhóm thuộc tính cần biết

| Nhóm | Thuộc tính / hàm tiêu biểu | Cách dùng phù hợp | Cảnh báo |
|---|---|---|---|
| **Thời gian** | `request.time` | Truy cập có thời hạn, cửa sổ hỗ trợ | Có hỗ trợ rộng trong allow conditions; dùng UTC minh bạch |
| **Loại tài nguyên** | `resource.type` | Giới hạn role tới kiểu tài nguyên cụ thể | Giá trị type phải đúng tên chính thức |
| **Tên tài nguyên** | `resource.name` | Chỉ tên hoặc nhóm tên có tiền tố/hậu tố | Chỉ có ở loại tài nguyên được hỗ trợ; format khác nhau |
| **Dịch vụ** | `resource.service` | Phạm vi dịch vụ khi được hỗ trợ | Không thay thế kiểm tra resource type nếu dựa vào name |
| **Resource Manager tags** | `resource.matchTag()`, `resource.hasTagKey()` | Phân biệt môi trường/nhóm tài nguyên bằng tag | Là **tags**, khác labels; cần cấu hình thừa kế đúng |
| **Access level / HTTP** | `request.auth.access_levels`, `request.host`, `request.path` | Một số tình huống **IAP** được hỗ trợ | Không có ý nghĩa phổ quát cho mọi API Google Cloud |
| **Destination IP/port** | `destination.ip`, `destination.port` | Điều kiện **IAP TCP tunneling** | Không phải cơ chế lọc IP chung cho IAM |
| **API-specific** | `api.getAttribute(...)` | Ràng buộc theo API/phép gọi được hỗ trợ | Chỉ dùng với permission và dịch vụ được tài liệu chỉ rõ |

**Phân biệt tags và labels:** Resource Manager **tags** được thiết kế để áp dụng chính sách trên hệ thống phân cấp tài nguyên và có cú pháp như `resource.matchTag('123456789012/environment', 'dev')`. **Labels** là metadata quản trị/chi phí trên tài nguyên và không tự biến thành thuộc tính `resource.matchTag`. Không thay tags bằng labels rồi kỳ vọng IAM tự hiểu.

### 4.1. Giới hạn khi dùng `resource.name`

Đây là một trong các lỗi dễ gây hiểu nhầm nhất. Dạng tên tài nguyên trong CEL **không nhất thiết là tên hiển thị** trong Console và **không dùng ký tự đại diện `*`** như glob thông thường.

Ví dụ tên của một VM:

~~~cel
resource.type == 'compute.googleapis.com/Instance' &&
resource.name.startsWith(
  'projects/example-proj/zones/asia-southeast1-a/instances/dev-'
)
~~~

Điều kiện chỉ dựa trên `resource.name` có thể thất bại nếu permission được kiểm tra trên một kiểu tài nguyên **không hỗ trợ thuộc tính name**. Google Cloud khuyến nghị giới hạn theo **`resource.type`** khi kiểm tra tên. Nếu một role có cả permission đọc VM, disk, instance template, network hoặc IAM ở nhiều lớp, điều kiện trên `Instance` có thể làm các tác vụ phụ trở nên không khả dụng.

**Bài học:** Hãy kiểm tra từng permission mà thao tác yêu cầu, loại tài nguyên dùng để đánh giá permission đó và bảng thuộc tính được hỗ trợ. Không kết luận “VM bắt đầu bằng dev- thì mọi thao tác quản trị VM đều hoạt động” chỉ vì một biểu thức nhìn có vẻ đúng.

## 5. Tình huống A: cấp quyền xem log có thời hạn

**Bối cảnh:** đội xử lý sự cố cần quyền xem log trên project `training-incident` đến hết ca trực. Đội không cần sửa dịch vụ và không cần quyền xem log sau thời hạn. Một nhóm Google `incident-response@example.com` được dùng làm principal để dễ quản trị thành viên.

**Phương án:** gán `roles/logging.viewer` có điều kiện `request.time < ...` ngay trên project, với thời hạn được phê duyệt.

### 5.1. Tạo bằng Google Cloud Console

1. Trong Console, chọn đúng project sandbox `training-incident`.
2. Vào **IAM & Admin → IAM**, chọn **Grant access** hoặc sửa binding thích hợp.
3. Thêm principal `group:incident-response@example.com` và role **Logs Viewer** (`roles/logging.viewer`).
4. Tại phần IAM Condition, chọn tạo điều kiện; đặt title `IncidentReadOnlyUntilJan15`, description nêu ticket/owner và deadline.
5. Trong **Condition editor**, nhập:

~~~cel
request.time < timestamp('2027-01-15T18:00:00Z')
~~~

6. Dùng linter/kiểm tra cú pháp nếu Console cung cấp, lưu điều kiện, kiểm tra thông tin rồi **Save** thay đổi IAM.
7. Xác nhận IAM policy đã có binding/condition đúng role, principal và thời hạn. Sau đó thử quyền trong một tài khoản có phạm vi được giao.

Đây là thao tác **thay đổi quyền IAM thật** và yêu cầu `resourcemanager.projects.getIamPolicy`, `resourcemanager.projects.setIamPolicy` cùng các permission cần thiết; chỉ làm trên project được phép và có phê duyệt.

### 5.2. Tạo bằng gcloud trong Cloud Shell

~~~bash
# Ví dụ: thay PROJECT_ID và nhóm trước khi thực thi.
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:incident-response@example.com" \
  --role="roles/logging.viewer" \
  --condition="title=IncidentReadOnlyUntilJan15,description=Approved incident window,expression=request.time < timestamp('2027-01-15T18:00:00Z')"
~~~

Mẫu `--condition` gồm các cặp `title=...`, `description=...` và `expression=...`. Biểu thức có dấu phẩy có thể cần cách phân tách/escape riêng của `gcloud`; kiểm tra `gcloud help` trên phiên bản đang dùng. Ví dụ được viết cho môi trường Bash/Cloud Shell; PowerShell trên máy Windows có cách xuống dòng khác.

Để **đọc lại** các binding trên project:

~~~bash
gcloud projects get-iam-policy PROJECT_ID --format=json
~~~

Kiểm tra JSON trả về có đúng `role`, `members` và `condition.title/description/expression`. Không được chỉ dựa vào thông báo “lệnh thành công”: còn phải kiểm tra **principal có quyền hiệu lực hay không** trong tình huống truy cập thực tế.

### 5.3. Kiểm thử theo kịch bản

| Tình huống thử | Kỳ vọng từ binding mới | Điều kiện cần xác minh |
|---|---|---|
| Thành viên nhóm, trước hạn, xem log có quyền đọc | Binding có thể cấp `roles/logging.viewer` | Đúng project, đúng nhóm, không bị deny/PAB |
| Thành viên nhóm, sau hạn | Binding **không còn cấp** role | Không có binding vô điều kiện/nhóm khác cấp cùng permission |
| Người không ở nhóm | Binding không cấp quyền | Có thể vẫn có role từ nơi khác |
| Thành viên nhóm cố sửa/xóa log | Role Logs Viewer không cấp quyền ghi/chỉnh tương ứng | Cần kiểm tra thêm các role khác được gán |
| Lệnh chạy ngay sau khi cấp quyền | Có thể có độ trễ đồng bộ IAM | Chờ cơ chế propagation; thử lại có ghi nhận thời gian |

Đối với xử lý sự cố production, cân nhắc **Privileged Access Manager (PAM)** nếu tổ chức cần luồng yêu cầu/phê duyệt và truy cập đặc quyền có thời hạn, thay vì liên tục cấp và thu hồi thủ công.

## 6. Tình huống B: chỉ truy cập môi trường development qua Resource Manager tags

**Bối cảnh:** nhóm QA cần xem tài nguyên thuộc `environment=dev` trong phạm vi folder chứa nhiều project. Môi trường production không được nằm trong phạm vi binding mới.

Giả sử organization có ID số `123456789012`, tag key `environment` và tag value `dev`, đã được tạo/cấu hình đúng theo cơ chế Resource Manager tags.

~~~cel
resource.matchTag('123456789012/environment', 'dev')
~~~

Biểu thức kiểm tra **tag hiệu lực** của tài nguyên trong bối cảnh được hỗ trợ. Nếu muốn có thêm hạn:

~~~cel
resource.matchTag('123456789012/environment', 'dev') &&
request.time < timestamp('2027-01-15T18:00:00Z')
~~~

**Cần làm trước khi triển khai:**

- Đảm bảo tag key/value có tồn tại và dùng đúng namespaced name hoặc ID theo hướng dẫn Google Cloud. Tag có thể được thừa kế từ organization/folder/project tùy cấu hình.
- Xác định role **chỉ đọc** phù hợp; gán role tại scope có thể chứa các resource dev cần xem.
- Kiểm tra các **binding không điều kiện** của principal tại organization/folder/project khác; điều kiện tag này không thể tự thu hồi chúng.
- Xác thực cách service đánh giá tag, các quyền bổ sung dùng cho liệt kê và hành vi khi resource chưa được gắn tag.
- Không xem tag như phương tiện thay thế cho VPC firewall, cấu hình Cloud Run ingress, Cloud SQL private networking hoặc kiểm soát lưu trú dữ liệu.

Nếu một project dev bị gắn nhầm tag `environment=prod`, yêu cầu có thể bị từ chối hoặc hoạt động không như mong muốn. Quyền sửa tag và quyền đổi policy tag phải được kiểm soát riêng, tránh một người tự thay tag để mở rộng quyền.

## 7. Tình huống C: điều kiện theo tên object trong Cloud Storage

**Bối cảnh:** nhóm tài liệu được phép đọc file trong bucket `academy-training-assets` theo nguyên tắc cấp quyền tối thiểu.

Ví dụ điều kiện chỉ khớp tài nguyên **object** dưới tiền tố `objects/materials/`:

~~~cel
resource.type == 'storage.googleapis.com/Object' &&
resource.name.startsWith(
  'projects/_/buckets/academy-training-assets/objects/materials/'
)
~~~

Đọc biểu thức:

- `resource.type` kiểm tra loại tài nguyên là Cloud Storage **Object**.
- `resource.name` dùng **định dạng tên tài nguyên** của Cloud Storage, không dùng `gs://...`.
- `startsWith` chỉ khớp tên bắt đầu bằng chuỗi; đối tượng `objects/materials-v2/foo.pdf` **không** nằm trong `objects/materials/`.
- Không dùng ký tự đại diện `*` vì `resource.name` không hiểu wildcard theo cú pháp đó.

**Giới hạn quan trọng về quyền liệt kê:** một role như `roles/storage.objectViewer` có các permission được đánh giá ở nhiều cấp; ví dụ `storage.objects.list` thường được đánh giá ở **bucket**, còn đọc nội dung object được đánh giá ở **object**. Điều kiện chỉ cho phép `resource.type == Object` có thể cho phép truy cập object theo tên đã biết nhưng **không cho phép liệt kê**. Nếu cần liệt kê theo cấu trúc thư mục, xem xét **managed folders**, IAM ở scope tương ứng và giải pháp được Cloud Storage hỗ trợ, thay vì ngầm mở quyền liệt kê toàn bucket.

**Không suy diễn:** điều kiện theo prefix không thay cho việc chọn đúng scope cho bucket, cấu hình uniform bucket-level access, đường dẫn thực tế và các chính sách bảo vệ dữ liệu khác. Kiểm tra yêu cầu `get` và `list` riêng trong môi trường thử nghiệm.

## 8. Phân biệt điều kiện ở allow, deny và Principal Access Boundary

Tên “IAM Conditions” có thể xuất hiện trong các loại policy khác nhau. Không copy một biểu thức từ allow binding sang deny rule mà không kiểm tra thuộc tính được hỗ trợ và **ý nghĩa kết quả**.

| Vị trí condition | Khi nào điều kiện ảnh hưởng quyền? | Thuộc tính điển hình | Lưu ý |
|---|---|---|---|
| **Allow policy role binding** | Cấp role nếu biểu thức `true` | Time, resource attributes, tags và một số API/IAP attributes | Điều kiện `false`/không đánh giá được không tạo grant |
| **Deny policy deny rule** | Áp dụng deny nếu biểu thức `true` **hoặc không thể đánh giá** | Resource tags theo hỗ trợ hiện hành | Không dùng các ví dụ `request.time` của allow một cách máy móc |
| **PAB policy binding** | Quyết định policy PAB áp dụng cho principal set nào | `principal.type`, `principal.subject` | Điều kiện của binding PAB không phải grant role |
| **Unified Access Policies (UAP)** | Điều kiện phụ thuộc loại rule, quyền và service | Thuộc tính IAM hoặc thuộc tính do dịch vụ cung cấp | Tình trạng hỗ trợ/phát hành có thể khác nhau; kiểm tra tài liệu hiện hành |

Ví dụ **deny** với tag môi trường production:

~~~cel
resource.matchTag('123456789012/environment', 'prod')
~~~

Điều kiện này chỉ có ý nghĩa như một phần của **deny rule được cấu hình đầy đủ**, cùng danh sách principal và permission bị từ chối. Nó không tự tạo deny chỉ bằng cách viết chuỗi CEL. Deny có cơ chế ưu tiên riêng; không được dùng biểu thức deny như thể đó là một allow condition.

**PAB** xác định tài nguyên mà principal đủ điều kiện được truy cập theo chính sách biên truy cập; nó không tự cấp permission. **Organization Policy** đặt các ràng buộc quản trị cấu hình. **VPC Service Controls** bổ sung biên bảo vệ dữ liệu cho các dịch vụ được hỗ trợ. Đây là những lớp bổ trợ cần chọn theo bài toán, không xem là cú pháp khác của một role binding có điều kiện.

## 9. Cách IAM Conditions ảnh hưởng đến Compute Engine, GKE, Cloud Run và dữ liệu

Trong thực tế, điều kiện phải phục vụ một thao tác cụ thể. Khi thiết kế mô-đun Google Cloud, dùng các câu hỏi sau để tránh chọn sai thuộc tính:

| Workload / dịch vụ | Mục tiêu truy cập thường gặp | Điểm cần kiểm tra trước khi áp điều kiện |
|---|---|---|
| **Compute Engine** | Quản trị VM dev- hoặc chỉ xem VM trong thời gian hỗ trợ | Nhiều operation còn cần quyền trên disk, template, network; resource type/name nào được đánh giá? |
| **GKE** | Truy cập API quản lý cluster với điều kiện IAM | Quyền quản lý GKE từ IAM khác quyền Kubernetes RBAC bên trong cluster; condition không thay thế RBAC |
| **Cloud Run** | Chỉ service account cụ thể được gọi hoặc triển khai service | Chọn đúng `roles/run.invoker`/quyền deploy và scope; ingress và xác thực HTTP vẫn phải cấu hình |
| **Cloud Storage** | Đọc object trong một nhóm tài liệu | Phân biệt object `get` với bucket `list`, định dạng resource.name và quyền trên managed folder |
| **Cloud SQL** | Quản lý instance hoặc kết nối dữ liệu | Quyền IAM quản trị Cloud SQL khác quyền tài khoản DB và kết nối mạng |
| **BigQuery** | Truy vấn dataset/table có điều kiện | Kiểm tra scope dataset/table, row/column security khi cần; không coi IAM Condition là row filter |
| **Secret Manager** | Đọc một secret trong thời gian xử lý sự cố | Kiểm tra permission và định dạng tên secret/version, không gán quyền trên toàn project khi không cần |
| **CI/CD** | Service account có quyền triển khai trong thời hạn | Gắn role tối thiểu cho pipeline; hạn chế quyền impersonation và log thao tác |

**Giới hạn thường gặp:** IAM Conditions điều khiển **permission trên Google Cloud resource**, không mặc định can thiệp vào logic phân quyền người dùng cuối trong API Java/Spring Boot của bạn. Ứng dụng vẫn cần xác thực JWT/session và kiểm tra authorization ở cấp nghiệp vụ; GKE có Kubernetes RBAC; Cloud SQL có quyền của hệ quản trị CSDL.

## 10. Kiểm tra, gỡ lỗi và quản lý vòng đời

### 10.1. Checklist trước khi cấp

1. Ghi nhu cầu rõ ràng: **ai** (principal), **hành động gì** (permission/role), **ở đâu** (resource/scope), **khi nào** và **vì sao**.
2. Chọn **predefined/custom role ít quyền nhất** đáp ứng thao tác, tránh `roles/owner` và `roles/editor`.
3. Chọn điều kiện có thể kiểm toán: time, resource type/name hoặc tags đúng nơi hỗ trợ.
4. Liệt kê tất cả **binding hiệu lực** có thể cấp cùng permission, kể cả quyền đến từ group và tổ tiên organization/folder/project.
5. Kiểm tra resource format, dịch vụ hỗ trợ và các quyền phụ của thao tác.
6. Đặt title/description chứa bối cảnh, owner và thời hạn; gắn ticket theo quy trình nội bộ.
7. Kiểm thử trong sandbox trước, ghi kế hoạch thu hồi hoặc phương án khôi phục nếu người dùng bị khóa quyền.

### 10.2. Dùng Policy Troubleshooter

**Policy Troubleshooter for IAM** hỗ trợ điều tra theo bộ ba:

- **Principal:** ai gọi API (user/group/service account hoặc danh tính liên quan).
- **Permission:** quyền nguyên tử như `logging.logEntries.list` hoặc permission thực tế mà thao tác yêu cầu.
- **Resource:** tài nguyên đang kiểm tra theo định dạng thích hợp.

Troubleshooter tổng hợp các allow/deny/PAB policy liên quan và giải thích vì sao quyền được cho phép hoặc bị từ chối theo dữ liệu có thể quan sát. Khi điều kiện phụ thuộc thời gian hoặc thuộc tính ngữ cảnh, vẫn phải xác minh **ngữ cảnh yêu cầu** và có thể thử thao tác thật trong sandbox. Quyền truy cập vào trình gỡ lỗi và khả năng nhìn thấy policy cũng chịu IAM.

**Không nhầm:**
- `PERMISSION_DENIED` không luôn là lỗi của chính IAM Condition; có thể thiếu role, sai tài khoản, deny/PAB, API chưa được bật hoặc ràng buộc dịch vụ.
- `NOT_FOUND` không chứng minh tài nguyên chưa tồn tại nếu quyền xem bị giới hạn.
- Thay đổi policy IAM có thể cần thời gian đồng bộ; đừng dùng vòng lặp cấp quyền rộng hơn để “sửa nhanh”.

### 10.3. Audit log và kiểm soát thay đổi

Với quyền truy cập được cấp theo tình huống, nên ghi lại:

| Thuộc tính | Ví dụ dữ liệu cần lưu |
|---|---|
| Requester và approver | Người yêu cầu, nhóm phê duyệt |
| Principal và role | `group:incident-response@example.com` + `roles/logging.viewer` |
| Scope | Project ID hoặc resource cụ thể |
| Condition | Title, expression, UTC expiry |
| Evidence | Ticket, lý do nghiệp vụ, phiên bản policy trước/sau |
| Validation | Đã thử allow/deny case nào, thời điểm nào |
| Cleanup | Người phụ trách thu hồi, ngày xử lý, kết quả readback |

Kiểm tra **Cloud Audit Logs** cho thay đổi IAM policy theo chế độ log và khả năng dịch vụ hỗ trợ. Chỉ lưu thông tin cần thiết và kiểm soát ai xem được audit log, vì log có thể chứa định danh và metadata nhạy cảm.

### 10.4. Thu hồi role đúng cách

Khi không còn cần quyền, nên **xóa binding tạm thời** hoặc thu hồi principal khỏi binding theo quy trình, rồi xác minh lại. **Không xóa riêng trường `condition`** nếu mục tiêu là thu hồi: việc biến một binding có điều kiện thành binding vô điều kiện có thể **mở rộng quyền vĩnh viễn**.

Nếu sửa policy thông qua API/JSON, dùng quy trình **read–modify–write** và giữ `etag`, `version` cùng tất cả binding khác. Với condition trong allow policy, dùng phiên bản policy hỗ trợ conditions (thường là **version 3**). Tránh đọc policy, xóa mất `condition` hoặc vô tình ghi đè thay đổi của đồng nghiệp.

## 11. Những lỗi thiết kế phổ biến

| Lỗi | Hậu quả | Biện pháp đúng |
|---|---|---|
| Thêm điều kiện vào role nhưng principal đã có grant vô điều kiện | Quyền vẫn tồn tại sau hạn | Kiểm tra toàn bộ effective access và binding kế thừa |
| Gán điều kiện cho basic role `roles/owner`, `roles/editor`, `roles/viewer` | Không được hỗ trợ cho conditional allow binding | Dùng role định nghĩa sẵn khác hoặc custom role thích hợp |
| Gán condition cho `allUsers` hoặc `allAuthenticatedUsers` trong allow binding | Cú pháp/khả năng không được hỗ trợ trong trường hợp này | Thiết kế cơ chế xác thực và member được hỗ trợ |
| Chỉ dùng `resource.name` với role nhiều kiểu resource | Một số permission không được cấp hoặc hành vi không mong đợi | Ghép `resource.type` và thử từng permission |
| Dùng `*` để wildcard tên resource | Điều kiện không hoạt động như glob | Dùng `startsWith()`, `endsWith()` và đúng format |
| Dùng **labels** thay **tags** | `resource.matchTag` không có dữ liệu phù hợp | Cấu hình Resource Manager tags |
| Dùng `request.ip` như thuộc tính IAM phổ quát | Không có thuộc tính chung như vậy cho mọi Google Cloud API | Dùng IAP/access levels/biện pháp mạng được hỗ trợ |
| Dùng điều kiện allow `request.time` trong deny policy | Sai nhóm thuộc tính được hỗ trợ | Kiểm tra attribute reference theo policy type |
| Chỉ thử `get` mà quên `list` | Console/CLI không liệt kê được dù biết tên object | Kiểm tra permission ở cả bucket và object |
| Xóa condition thay vì xóa binding | Vô tình tạo grant vô điều kiện | Thu hồi binding/principal đúng cách |
| Dùng điều kiện IAM để thay thế authorization nội bộ của API | Lộ hoặc chặn nhầm dữ liệu nghiệp vụ | Thiết kế kiểm tra quyền trong ứng dụng và từng dịch vụ |

## 12. Thực hành có hướng dẫn: thiết kế chính sách cho nhóm ứng cứu

**Bài toán:** Công ty có project `retail-prod` chứa Cloud Run Orders API, Cloud SQL, Cloud Storage và log tập trung. Nhóm ứng cứu sự cố `ir-team@example.com` cần được **xem log từ 10/01/2027 đến trước 15/01/2027 18:00 giờ Việt Nam**, và tuyệt đối không cần quyền sửa workload. Project đã có các binding khác.

### Bước 1 — Chuyển yêu cầu thành IAM

| Thành phần | Thiết kế |
|---|---|
| Principal | `group:ir-team@example.com` |
| Scope | Project `retail-prod` (sandbox mô phỏng trước) |
| Role | `roles/logging.viewer` |
| Mốc bắt đầu | 10/01/2027 00:00 giờ Việt Nam = 09/01/2027 17:00 UTC |
| Mốc kết thúc | 15/01/2027 18:00 giờ Việt Nam = 15/01/2027 11:00 UTC |
| Kiểm soát bổ sung | Rà quyền từ nhóm khác, audit thay đổi, theo dõi hết hạn |

Biểu thức:

~~~cel
request.time >= timestamp('2027-01-09T17:00:00Z') &&
request.time < timestamp('2027-01-15T11:00:00Z')
~~~

Hai mốc dùng `>=` và `<` để tránh mơ hồ về việc quyền có hiệu lực đúng ở thời điểm biên. Trong bài thực hành thật, thay các mốc ví dụ bằng thời gian được phê duyệt.

### Bước 2 — Dự báo kết quả

| Yêu cầu | Theo binding mới |
|---|---|
| Thành viên nhóm IR truy cập 12/01/2027 | Có thể được role Logs Viewer cấp quyền |
| Thành viên nhóm IR truy cập 09/01/2027 lúc 16:59 UTC | Không được cấp quyền từ binding này |
| Thành viên nhóm IR truy cập 15/01/2027 lúc 11:00 UTC | Không được cấp quyền từ binding này |
| Nhân viên ngoài nhóm IR truy cập 12/01/2027 | Không được cấp quyền từ binding này |
| Thành viên nhóm IR cố thay đổi Cloud SQL | Role này không tự cấp quyền quản trị Cloud SQL |
| Người IR có thêm quyền vô điều kiện từ organization | Có thể vẫn xem log qua đường cấp quyền khác |

### Bước 3 — Tự kiểm tra

1. Xác nhận timezone UTC và tương đương giờ Việt Nam của hai mốc.
2. Kiểm tra title, description và sự hiện diện của **cả hai** điều kiện thời gian.
3. Xem IAM policy của project và policy kế thừa; phát hiện principal/nhóm khác có grant chồng lấn.
4. Mô phỏng các ca “trước hạn”, “trong hạn”, “ngay tại hạn kết thúc”, “ngoài nhóm”.
5. Dùng Policy Troubleshooter cho permission đọc log và tài nguyên phù hợp, kết hợp kiểm tra thực tế khi có quyền.
6. Ghi owner phụ trách thu hồi binding; không xóa field `condition` để thu hồi.

## 13. Câu hỏi tự đánh giá

1. **Binding X** cấp `roles/storage.objectViewer` vô điều kiện cho nhóm A ở folder; **binding Y** cấp cùng role có điều kiện trên một bucket con. Khi Y hết hạn, quyền từ X có tự mất không? Vì sao?
2. Trong allow policy, điều kiện trả về `false`. Điều đó có đồng nghĩa với một **explicit deny** đối với principal không?
3. Vì sao khi kiểm tra `resource.name` cần quan tâm `resource.type` và danh sách resource được hỗ trợ?
4. So sánh `resource.matchTag('123456789012/environment','dev')` với labels `env=dev` trên một VM.
5. Vì sao điều kiện chỉ cho `Object` có thể làm lệnh `list` trong bucket thất bại?
6. Trong chính sách deny và PAB policy binding, ý nghĩa và tập thuộc tính có giống allow binding không?
7. Một kỹ sư muốn giới hạn quyền IAM theo IP trên mọi Google Cloud API bằng `request.ip`. Thiết kế này có chính xác không? Nêu phương án cần tìm hiểu.
8. Bạn đã thêm quyền có điều kiện nhưng người dùng vẫn truy cập được sau thời hạn. Hãy nêu trình tự kiểm tra.

**Gợi ý đáp án:**

1. Không; grant vô điều kiện từ folder vẫn có thể cấp cùng permission.
2. Không; binding ấy không cấp role, nhưng principal có thể được cấp từ binding khác.
3. Vì các loại tài nguyên/permission không cùng hỗ trợ `name`; type giúp xác định đúng ngữ cảnh.
4. IAM tag là Resource Manager tag có cú pháp và cơ chế chính sách; labels không tương đương.
5. `storage.objects.list` thường được đánh giá ở bucket, không phải object; cần xem quyền và scope riêng.
6. Không; deny conditions chủ yếu hỗ trợ resource tags và có quy tắc đánh giá khác, PAB điều kiện áp dụng policy theo principal.
7. Không; xem các thuộc tính IAP, access levels hoặc biện pháp kiểm soát mạng theo dịch vụ.
8. Tìm binding vô điều kiện/nhóm khác/quyền kế thừa; kiểm tra principal, scope, expiry UTC, loại permission và policy hiệu lực, rồi dùng Troubleshooter.

## 14. Checklist áp dụng IAM Conditions

- [ ] Đã xác định principal, role/permission, scope và mục tiêu điều kiện.
- [ ] Đã chọn role tối thiểu và xác định các quyền đi kèm.
- [ ] Đã kiểm tra những binding có thể cấp quyền tương đương, cả ở tổ tiên.
- [ ] Đã dùng đúng CEL, timezone UTC, `resource.type` và định dạng resource.name.
- [ ] Đã phân biệt Resource Manager **tags** với labels và kiểm tra thừa kế.
- [ ] Đã kiểm tra khả năng hỗ trợ thuộc tính cho đúng service, resource type và policy type.
- [ ] Đã xác minh điều kiện không thay thế deny/PAB, network policy và authorization nghiệp vụ.
- [ ] Đã kiểm thử cả ca được phép và bị từ chối, kể cả mốc hết hạn.
- [ ] Đã lưu bối cảnh phê duyệt, dấu vết thay đổi và người phụ trách thu hồi.
- [ ] Đã đọc lại IAM policy sau thay đổi và không vô tình chuyển binding thành vô điều kiện.

## 15. Tài liệu chính thức

Cú pháp và phạm vi thuộc tính có thể được Google Cloud cập nhật. Khi thực thi trên dự án thực tế, đối chiếu tài liệu và help của phiên bản đang dùng:

- [Overview of IAM Conditions](https://docs.cloud.google.com/iam/docs/conditions-overview)
- [Attribute reference for IAM Conditions](https://docs.cloud.google.com/iam/docs/conditions-attribute-reference)
- [Resource attributes for IAM Conditions](https://docs.cloud.google.com/iam/docs/conditions-resource-attributes)
- [Manage conditional role bindings](https://docs.cloud.google.com/iam/docs/managing-conditional-role-bindings)
- [gcloud projects add-iam-policy-binding](https://docs.cloud.google.com/sdk/gcloud/reference/projects/add-iam-policy-binding)
- [Troubleshoot IAM-related policies](https://docs.cloud.google.com/iam/docs/troubleshoot-policies)
- [IAM policy types and evaluation](https://docs.cloud.google.com/iam/docs/policy-types)

**Điểm cần nhớ:** IAM Conditions là công cụ **thu hẹp tình huống cấp quyền của một binding**, với biểu thức phải đúng trong ngữ cảnh được hỗ trợ. Bảo mật hiệu quả đòi hỏi kiểm tra **toàn bộ quyền hiệu lực**, sử dụng role tối thiểu, thử các ca biên và quản lý vòng đời binding. Từ nền tảng đó, đội triển khai Google Cloud có thể bảo vệ tài nguyên Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu trong khi vẫn đáp ứng nhu cầu vận hành, phát hành và xử lý sự cố.
