# IAM, uniform bucket-level access và public access prevention

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích **Identity and Access Management (IAM)** kiểm soát quyền trên bucket và object của **Google Cloud Storage**, và phân biệt quyền IAM với **Access Control Lists (ACLs)**.
2. Lựa chọn IAM roles tối thiểu cho ứng dụng Java, người đọc báo cáo, pipeline upload và người quản trị bucket; xác định tác động của role được **kế thừa** từ project, folder và organization.
3. Hiểu chính xác **Uniform bucket-level access (UBLA)**: khi bật, ACL không còn được sử dụng; có quy trình di chuyển từ ACL, hạn chế khi tắt lại và mốc **90 ngày**.
4. Hiểu **Public access prevention (PAP)** ở cấp bucket và organization policy: ngăn quyền công khai qua **allUsers/allAuthenticatedUsers**, nhưng có ngoại lệ quan trọng như **signed URLs** và private bucket access qua sản phẩm được hỗ trợ.
5. Thiết kế quyền theo **managed folders** hoặc IAM Conditions mà không vô tình mở quyền liệt kê hoặc truy cập toàn bộ bucket.
6. Thực hành **gcloud storage** để tạo bucket private, xem và sửa IAM bindings, bật UBLA/PAP, kiểm tra truy cập và chẩn đoán lỗi **400/401/403/412**.
7. Thiết kế bảo mật dữ liệu cho Compute Engine, GKE, Cloud Run, Cloud Storage, CI/CD và ứng dụng Java; đánh giá logging, giám sát, chi phí, độ tin cậy và quy trình thay đổi.

## 1. Bối cảnh: cùng một bucket có nhiều đối tượng cần quyền khác nhau

Giả sử doanh nghiệp **An Lộc** triển khai một hệ thống bán hàng trên Google Cloud:

- **Java API** trên Cloud Run ghi ảnh sản phẩm vào bucket.
- **Ứng dụng xử lý ảnh** trên GKE cần đọc ảnh gốc và ghi ảnh đã tối ưu.
- **Nhân viên phân tích** cần đọc báo cáo CSV hàng tháng.
- **Khách hàng** chỉ được xem ảnh sản phẩm đã công bố, không được tải tài liệu hợp đồng.
- **Pipeline CI/CD** cần upload artifacts nhưng không có quyền xóa dữ liệu sản xuất.

Nếu mọi thành phần cùng có **roles/storage.admin** trên project, chỉ một token bị lộ hoặc cấu hình nhầm cũng có thể ảnh hưởng tới nhiều bucket. Ngược lại, nếu quyền chỉ được cấp cho một object bằng ACL mà sau đó doanh nghiệp bật UBLA, những client phụ thuộc ACL có thể mất quyền ngay.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và database, đồng thời bảo vệ tài nguyên, tự động phát hành, giám sát độ tin cậy và chi phí. Chủ đề này tập trung vào **ai được phép làm gì với dữ liệu Cloud Storage**, cách chuẩn hóa quản lý quyền và cách giảm rủi ro chia sẻ nhầm ra Internet.

**Ba nhóm câu hỏi bảo mật cần giải quyết:**

1. **Ai có quyền?** Tài khoản người dùng, Google Group, service account hoặc principal liên kết.
2. **Quyền áp dụng ở đâu?** Organization, folder, project, bucket, managed folder hoặc object theo cơ chế đang dùng.
3. **Có quy tắc ngăn public exposure không?** UBLA loại bỏ ACL, còn PAP ngăn những quyền IAM/ACL công khai. Hai tính năng giải quyết **hai vấn đề khác nhau**.

## 2. Các khái niệm nền tảng: principal, role, permission, policy và ACL

### 2.1. IAM policy

**IAM allow policy** gồm những **bindings**: mỗi binding gắn một **role** với một hoặc nhiều **principals** và có thể chứa **condition**.

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **Principal** | Danh tính được xét quyền | user:analyst@example.com, group:data-team@example.com, serviceAccount:writer@project.iam.gserviceaccount.com |
| **Permission** | Thao tác cụ thể được phép | storage.objects.get, storage.objects.create, storage.objects.list |
| **Role** | Tập permissions | roles/storage.objectViewer, roles/storage.objectCreator |
| **Binding** | Ai nhận role trên một resource, có thể kèm condition | Nhóm data-team nhận Object Viewer trên bucket reports |
| **Policy inheritance** | Quyền cấp ở tổ tiên có thể áp dụng xuống tài nguyên con | Object Viewer cấp ở project áp dụng cho các bucket của project |
| **IAM Conditions** | Điều kiện CEL giới hạn thời gian hoặc đối tượng resource được hỗ trợ | Chỉ object có prefix reports/ hoặc trước một mốc thời gian |

Ví dụ ý tưởng policy bucket (rút gọn, **không phải file policy đầy đủ để ghi đè**):

~~~yaml
bindings:
  - role: roles/storage.objectViewer
    members:
      - group:analysts@example.com
  - role: roles/storage.objectCreator
    members:
      - serviceAccount:upload-worker@shop-prod-001.iam.gserviceaccount.com
~~~

Trong ví dụ, nhóm analysts có quyền xem/liệt kê objects, còn service account của worker có quyền tạo object mới. Chính xác những permissions áp dụng còn phụ thuộc **resource**, **IAM Conditions**, **IAM deny**, **organization policies** và các ràng buộc liên quan.

### 2.2. ACL (Access Control List)

**Fine-grained access** là chế độ Cloud Storage sử dụng **IAM và ACL song song**. ACL có thể cấp **READER/WRITER/OWNER** theo mô hình Cloud Storage cho bucket hoặc object. Trong một bucket chưa bật UBLA, **chỉ cần IAM hoặc ACL cấp quyền** là request có thể được cho phép, trừ khi có một cơ chế chặn khác được áp dụng.

Ví dụ:

- IAM trên bucket chưa cấp **Object Viewer** cho một tài khoản.
- Nhưng một object riêng có ACL cho tài khoản đó **READER**.
- Nếu không bị chặn bởi cơ chế khác, tài khoản có thể đọc object đó.

Đây là nguồn gây khó kiểm toán: chỉ xem IAM policy của bucket chưa đủ để thấy quyền từ object ACLs. ACL cũng có thể chứa **allUsers** hoặc **allAuthenticatedUsers**, gây public exposure ngoài dự kiến.

### 2.3. Phân biệt hai hệ thống

| Tiêu chí | IAM | ACL |
|---|---|---|
| Nơi áp dụng chính | Organization/folder/project, bucket, managed folder phù hợp | Bucket và từng object trong chế độ fine-grained |
| Granularity | Role/permission phong phú, kế thừa và điều kiện được hỗ trợ | READER/WRITER/OWNER, theo bucket/object |
| Một hệ thống Google Cloud thống nhất | Có | Không; riêng Cloud Storage |
| Có thể cấp theo Google Group/service account | Có | Có những khả năng tương ứng nhưng mô hình khác IAM |
| Tình trạng khi UBLA bật | **Cơ chế cấp quyền chính** | **Bị vô hiệu hóa** |
| Rủi ro quản trị | Cấp role quá rộng ở cấp cao | Quyền từng object phân tán, dễ khó rà soát |

**Nguyên tắc:** với bucket mới, ưu tiên **UBLA + IAM** nếu không có yêu cầu tương thích ACL cụ thể. Với bucket cũ, cần **inventory ACL usage trước khi chuyển**, không bật ngay trên production rồi mới đi tìm người mất quyền.

## 3. Quyền IAM kế thừa như thế nào?

### 3.1. Tài nguyên có phân cấp

~~~mermaid
flowchart TD
    O["Organization"] --> F["Folder"]
    F --> P["Project shop-prod-001"]
    P --> B["Bucket shop-private-docs"]
    B --> M["Managed folder contracts/"]
    M --> X["Objects có prefix contracts/"]
    O -. "IAM role ở tổ tiên có thể kế thừa" .-> X
~~~

Một role cấp trên **project** có thể áp dụng đến nhiều bucket/object. Một role trên **bucket** chỉ ảnh hưởng bucket đó và objects/managed folders bên trong theo permissions. Một role trên **managed folder** chỉ áp dụng tới objects trong prefix tương ứng.

**Quyền thường cộng dồn theo allow policies**: cho nhóm analysts quyền đọc ở cấp project, sau đó không thể “thu hẹp” quyền ấy chỉ bằng cách không cấp quyền trong IAM policy của một bucket. Cần điều chỉnh policy ở tổ tiên, tổ chức tài nguyên khác, hoặc sử dụng cơ chế kiểm soát phù hợp.

### 3.2. Đừng nhầm policy trực tiếp và effective access

~~~text
Project shop-prod-001:
  group:data-team → roles/storage.objectViewer

Bucket shop-private-docs:
  serviceAccount:upload-worker → roles/storage.objectCreator

Kết quả:
  data-team vẫn có quyền đọc object của shop-private-docs
  do role được kế thừa từ project,
  dù IAM policy trực tiếp ở bucket không liệt kê data-team.
~~~

**gcloud storage buckets get-iam-policy** chủ yếu cho biết bindings trực tiếp của bucket, không nhất thiết hiển thị mọi inherited binding. Để kiểm tra quyền thực tế, phải xem cả IAM ở project, folder, organization, IAM deny và các policy khác.

### 3.3. IAM allow, IAM deny và organization policy

**IAM deny policies** là lớp có thể chặn permissions dù IAM allow hoặc ACL đang cấp quyền. Deny policies áp dụng ở **organization/folder/project**, không gắn trực tiếp ở bucket hoặc managed folder.

**Organization Policy Service** còn có thể áp quy tắc như:

- **constraints/storage.publicAccessPrevention**: buộc các bucket trong phạm vi không được cấp public access.
- **constraints/storage.uniformBucketLevelAccess**: yêu cầu bucket mới dùng UBLA và ngăn tắt UBLA trên bucket đã bật, nhưng không tự bật UBLA cho mọi bucket cũ đang tắt.
- Các ràng buộc khác về location, encryption, retention hoặc cách tạo bucket theo chính sách doanh nghiệp.

**Các lớp không thay thế nhau:** IAM quyết định role/permission; UBLA chọn cơ chế cấp quyền; PAP chặn kiểu principal công khai; organization policy đặt guardrail từ cấp quản trị.

## 4. Những Cloud Storage IAM roles cần nhớ

Các role sau minh họa **quyền phổ biến**, không thay thế việc đối chiếu danh sách permissions chính thức.

| Role | Tên | Khả năng cốt lõi | Lưu ý |
|---|---|---|---|
| **Storage Object Viewer** | roles/storage.objectViewer | Đọc object và **liệt kê objects** | Không nên cấp toàn project cho một nhóm chỉ cần đọc một bucket |
| **Storage Object Creator** | roles/storage.objectCreator | Tạo object mới | **Không** đọc, xóa hoặc ghi đè object đã tồn tại theo role này |
| **Storage Object User** | roles/storage.objectUser | Tạo, đọc, cập nhật/xóa object và các thao tác liên quan | Quyền rộng hơn Object Creator; phù hợp worker cần sửa/xóa |
| **Storage Object Admin** | roles/storage.objectAdmin | Kiểm soát rộng các objects | Không nhất thiết cho quyền quản trị mọi cài đặt bucket |
| **Storage Bucket Viewer** | roles/storage.bucketViewer | Đọc bucket/metadata ở phạm vi được cấp | Không đồng nghĩa có quyền tải nội dung object |
| **Storage Admin** | roles/storage.admin | Quản trị buckets, objects và IAM tương ứng theo phạm vi | Quyền mạnh; hạn chế principal và scope |
| **Storage Folder Admin** | roles/storage.folderAdmin | Quản trị managed folders và policy theo quyền của role | Không dùng bừa cho uploader ứng dụng |

### 4.1. Những khác biệt dễ gây lỗi

- **roles/storage.objectCreator** chỉ cho tạo: workflow cần ghi đè cùng object name hoặc xóa object cũ có thể bị **403**, vì Cloud Storage thường cần thêm **storage.objects.delete** để replace.
- **roles/storage.objectViewer** chứa **storage.objects.list**. Nếu yêu cầu chỉ “GET một object có tên đã biết” mà không được phép liệt kê cả bucket, cân nhắc **custom role** và thiết kế đúng resource scope, thay vì áp Object Viewer rộng.
- **roles/storage.admin** ở cấp **project** có thể ảnh hưởng nhiều buckets, mạnh hơn đáng kể so với cấp trên **một bucket**.
- Các **legacy roles/convenience values** tồn tại để hỗ trợ tương thích; hãy kiểm tra khi project có basic roles **Owner/Editor/Viewer**, bởi principal có thể nhận quyền trên bucket rộng hơn dự kiến thông qua chúng.
- Kiểm tra yêu cầu **storage.buckets.getIamPolicy** và **storage.buckets.setIamPolicy** riêng khi quản lý IAM bindings; có quyền đọc object không có nghĩa được sửa policy.

### 4.2. Ma trận phân quyền minh họa

| Principal | Scope nên dùng | Role gợi ý | Không cấp mặc định |
|---|---|---|---|
| Java service ghi ảnh mới | Bucket images-inbox hoặc managed folder riêng | Object Creator | Storage Admin hoặc Editor toàn project |
| Worker tối ưu ảnh, cần đọc và thay thế | Bucket/managed folder đã phân vùng theo mục đích | Object User hoặc custom role phù hợp | Owner toàn project |
| Nhóm phân tích đọc báo cáo | Managed folder reports/ hoặc bucket reports riêng | Object Viewer | Object Admin |
| Pipeline CI upload artifact bất biến | Bucket artifact chỉ dành cho pipeline | Object Creator | Object Admin nếu không cần delete |
| Security team kiểm tra bucket policies | Tài nguyên được quản trị | Reader/role kiểm toán phù hợp | Dùng Owner chỉ để xem log |
| Storage platform admin | Bucket hoặc project đã xác định | Storage Admin khi cần | Admin không giới hạn mọi project |

## 5. Uniform bucket-level access (UBLA) là gì?

### 5.1. Khi bật UBLA

**Uniform bucket-level access** tắt toàn bộ cơ chế **ACL** của bucket và những objects bên trong. Từ đó quyền truy cập được quản lý **bằng IAM** ở những cấp được hỗ trợ.

~~~mermaid
flowchart LR
    REQ["Request đọc object"] --> U{"UBLA?"}
    U -->|Off| BOTH["IAM và ACL đều có thể cấp quyền"]
    U -->|On| ONLY["IAM là cơ chế cấp quyền<br/>ACL bị vô hiệu hóa"]
    BOTH --> O["Đánh giá các guardrails khác"]
    ONLY --> O
    O --> PAP{"PAP và policy khác có chặn?"}
    PAP -->|Có| DENY["Từ chối"]
    PAP -->|Không| RESULT["Cho phép nếu quyền hợp lệ"]
~~~

Hành vi khi UBLA bật:

- Lời gọi **đọc, tạo, sửa bucket ACL hoặc object ACL** qua API không được hỗ trợ nữa, thường trả **400 Bad Request**.
- Quyền từ object ACLs cũ **không còn hiệu lực**.
- Metadata object không còn hiển thị ownership theo mô hình object ACL cũ.
- Với API cấp object IAM/ACL, thao tác tương ứng không áp dụng; cấp quyền qua bucket IAM, managed folder hoặc các phương thức IAM được hỗ trợ.

**UBLA không ngăn public IAM bindings.** Nếu PAP không enforced và một quản trị viên cấp **roles/storage.objectViewer** cho **allUsers** trên bucket, objects có thể trở thành public dù UBLA đang bật.

### 5.2. Những tính năng yêu cầu UBLA

Cloud Storage yêu cầu UBLA cho một số khả năng, trong đó có:

- **Managed folders** và IAM policies đặt lên managed folders.
- **IAM Conditions** được đặt trực tiếp trên bucket.
- **Hierarchical namespace** khi dùng tính năng bucket tương ứng.
- Quyền truy cập cho **Workload Identity Federation** và **Workforce Identity Federation** principals trong Cloud Storage.

Nếu bucket đang ở chế độ fine-grained, việc cấp một federated principal vào IAM/ACL policy không tự khiến quyền đó hoạt động như kỳ vọng; cần chuẩn bị chuyển sang UBLA đúng quy trình.

### 5.3. Mốc 90 ngày: quyết định có thể không đảo ngược

**Không thể tắt UBLA sau khi nó đã bật liên tục 90 ngày** trên bucket. Trong khoảng thời gian ngắn hơn, việc tắt cũng chỉ hợp lệ khi thỏa toàn bộ điều kiện:

1. UBLA đã bật **dưới 90 ngày liên tiếp**.
2. Bucket **không có IAM Conditions trực tiếp** còn tồn tại.
3. Bucket **không chứa managed folders**.
4. Bucket không bị **constraints/storage.uniformBucketLevelAccess** áp đặt việc phải giữ UBLA.

Nếu tắt hợp lệ, Cloud Storage có thể **khôi phục ACL đã lưu trước khi bật**; objects tạo trong thời gian UBLA bật nhận default object ACL theo quy tắc. Đây là một rủi ro: **ACL cũ có thể chứa quyền công khai hoặc quyền không còn muốn giữ**.

**Không coi rollback UBLA là phương án dài hạn.** Hãy chuẩn bị migration và xác nhận quyền trước khi bật, thay vì dựa vào khả năng tắt lại vào ngày thứ 89.

### 5.4. Khi nào nên bật?

**Nên dùng UBLA** cho phần lớn bucket mới, hệ thống microservices, CI/CD, dữ liệu nhạy cảm và môi trường cần IAM thống nhất, đặc biệt khi cần managed folder hoặc IAM Conditions.

**Cần đánh giá kỹ** nếu đang có ứng dụng legacy phụ thuộc object ACL (chẳng hạn upload object kèm **publicRead** ACL hoặc API dùng ObjectAccessControls). Trong trường hợp đó phải sửa ứng dụng hoặc di chuyển quyền sang IAM trước.

## 6. Public access prevention (PAP) là gì?

### 6.1. PAP chặn điều gì?

**Public access prevention** ngăn Cloud Storage bucket/objects cho phép truy cập bằng các principal công khai:

- **allUsers**: bất kỳ ai, kể cả anonymous Internet client.
- **allAuthenticatedUsers**: bất kỳ người dùng/service account xác thực hợp lệ thuộc phạm vi của ký hiệu đó; **không có nghĩa “chỉ nhân viên công ty”**.

Khi PAP có hiệu lực:

- Truy cập dựa trên hai public principals này bị từ chối, thường là **401/403**.
- Cố gắng thêm public IAM binding hoặc ACL có thể bị **412 Precondition Failed**.
- **Public bindings có sẵn** không tự bị xóa mà **bị vô hiệu hóa khi PAP enforced**.
- Khi bỏ PAP mà không dọn public bindings cũ, những quyền đó **có thể có hiệu lực lại**, làm lộ dữ liệu.

### 6.2. Hai cách thực thi PAP

1. **Cấp bucket:** cài **publicAccessPrevention: enforced** trên bucket.
2. **Cấp organization/folder/project:** dùng organization policy constraint **storage.publicAccessPrevention** để áp xuống mọi bucket thuộc phạm vi.

Trạng thái metadata của bucket:

| Giá trị | Ý nghĩa | Điều cần kiểm tra |
|---|---|---|
| **enforced** | Chính bucket bật PAP | PAP có hiệu lực dù policy cấp trên cho phép public |
| **inherited** | Theo organization policy của project/folder/org | Phải đọc **effective organization policy** để biết PAP có hiệu lực hay không |

**inherited không đồng nghĩa public access được bật**. Nó chỉ có nghĩa quyết định dựa vào policy kế thừa. Một bucket metadata **inherited** vẫn có thể đang được bảo vệ bởi policy cấp tổ chức.

### 6.3. Những gì PAP **không** chặn

| Trường hợp | PAP có chặn theo đúng cơ chế này không? | Giải thích |
|---|---|---|
| Anonymous GET chỉ dựa vào allUsers | **Có**, khi PAP enforced | Không còn quyền public qua allUsers |
| Authenticated request chỉ dựa vào allAuthenticatedUsers | **Có**, khi PAP enforced | Ký hiệu này quá rộng, không phải nhóm nội bộ |
| Người dùng cụ thể có IAM Object Viewer | **Không chỉ vì PAP** | Danh tính được cấp đích danh vẫn có thể truy cập |
| Google Group nội bộ được cấp Object Viewer | **Không chỉ vì PAP** | Còn tùy IAM và policies khác |
| **Signed URL** còn hiệu lực, do principal có quyền ký và quyền dữ liệu phù hợp tạo | **Không** | Signed URLs là hình thức ủy quyền có phạm vi/thời hạn, không dựa vào allUsers |
| **Private bucket access qua Cloud Load Balancing/Cloud CDN** được hỗ trợ | **Không** | Có cơ chế truy cập riêng theo kiến trúc sản phẩm |
| Object đã được cache công khai trước khi bật PAP | **Không xóa ngay cache bên ngoài** | Có thể vẫn được phục vụ cho đến khi TTL/cache purge có hiệu lực |

Đây là điểm đặc biệt quan trọng: **PAP không đồng nghĩa mọi người trên Internet không thể tải dữ liệu bằng bất kỳ phương thức nào**. Signed URLs vẫn có thể được dùng bởi người sở hữu link; ứng dụng có backend được cấp quyền cũng có thể phát nội dung ra ngoài. Cần kiểm soát **người ký, thời hạn, đường phát hành dữ liệu, cache và các endpoint ứng dụng**.

### 6.4. Độ trễ enforcement

Cloud Storage cho phép đọc lại trạng thái PAP sau khi cập nhật một cách nhất quán mạnh, nhưng **việc thực thi có thể mất đến 10 phút**. Object đã được cache bên ngoài có thể tồn tại đến hết TTL hoặc lúc cache được invalidate. Trong ứng phó sự cố lộ dữ liệu, việc bật PAP là một bước, **không thay thế đánh giá cache, thu hồi credentials và xử lý dữ liệu đã bị tải xuống**.

## 7. UBLA và PAP: hai chính sách độc lập, kết hợp thế nào?

| UBLA | PAP enforced | Quyền từ ACL | Public IAM binding | Mục tiêu / rủi ro |
|---|---|---|---|---|
| **Tắt** | **Tắt/không áp dụng** | Có thể cấp quyền | Có thể cấp quyền | Fine-grained legacy, rủi ro public từ cả ACL/IAM |
| **Bật** | **Tắt/không áp dụng** | Không có hiệu lực | **Vẫn có thể cấp** | IAM tập trung nhưng **chưa ngăn public** |
| **Tắt** | **Bật** | ACL không công khai vẫn có thể cấp quyền | Public binding bị vô hiệu hóa/từ chối | Chặn public nhưng vẫn duy trì ACL legacy |
| **Bật** | **Bật** | Không có hiệu lực | Public binding bị vô hiệu hóa/từ chối | **Baseline phù hợp cho bucket private**, IAM tập trung + public guardrail |

### 7.1. Quyết định theo nhu cầu

- **Dữ liệu nội bộ, hợp đồng, backup, logs:** mặc định cân nhắc **UBLA ON + PAP enforced**.
- **Dữ liệu được cố ý công khai:** tách bucket riêng, đánh giá IAM allUsers được phê duyệt khi PAP không áp dụng; hoặc chọn **private bucket + Cloud CDN** theo tính năng, tránh vô tình làm toàn bộ bucket public.
- **Ứng dụng legacy dùng object ACL:** lập kế hoạch migrate, sau đó dùng UBLA; nếu yêu cầu tạm thời cần ACL, vẫn có thể dùng PAP làm lớp chặn public.

**Câu hỏi kiểm tra:** “Tôi đã bật UBLA rồi, vậy ai cũng không đọc được ảnh?” Sai. Nếu IAM grant cho **allUsers** và PAP không enforced, ảnh vẫn có thể public.

## 8. Managed folders và IAM Conditions: quyền tinh hơn trong bucket

### 8.1. Prefix giả lập không tự có IAM policy

Cloud Storage object có thể tên **reports/2026/sales.csv** nhưng **reports/** trong bucket flat namespace thường chỉ là prefix. Chỉ đặt tên có dấu **/** không tự tạo ranh giới quyền.

**Managed folder** là một Cloud Storage resource có thể gắn IAM policy cho nhóm objects có cùng prefix. UBLA phải bật trước khi tạo managed folder.

~~~text
Bucket company-data (UBLA = ON)
├── contracts/     managed folder → Legal Team: Object Viewer
│   ├── contract-1001.pdf
│   └── contract-1002.pdf
├── reports/       managed folder → Analysts: Object Viewer
│   └── sales-2026.csv
└── images/        managed folder → Image worker: Object Creator
    └── sku-1001.jpg
~~~

**IAM ở managed folders là cộng dồn với quyền của tổ tiên**. Nếu Analyst có Object Viewer ở **bucket**, họ vẫn có quyền đọc **contracts/** dù managed folder contracts/ không cấp gì cho họ. Muốn cách ly dữ liệu nhạy cảm, phải tránh grant rộng ở bucket/project hoặc tách bucket/project.

### 8.2. IAM Conditions theo tên object

Khi UBLA bật, có thể dùng **IAM Condition** trên bucket để grant cho một nhóm objects theo prefix:

~~~text
resource.name.startsWith(
  'projects/_/buckets/company-data/objects/reports/'
)
~~~

Condition dạng này có ích khi người dùng chỉ cần đọc một tập object xác định. Tuy nhiên **storage.objects.list** là phép gọi thực hiện trên **bucket resource**, nên condition phụ thuộc object name **không thể dùng một mình để giới hạn danh sách object khi list bucket**.

**Lựa chọn:** nếu muốn một policy trực quan cho cả nhóm objects, dùng **managed folder IAM**; với nhu cầu data isolation mạnh và quyền bucket-level như list/manage, cân nhắc **tách nhiều buckets**.

### 8.3. Hai điều cần phân biệt

| Cơ chế | Vai trò | Lưu ý |
|---|---|---|
| **IAM Condition trên bucket** | Cho phép một role khi điều kiện resource/time đạt | UBLA cần bật; semantics của list khác get object |
| **Managed folder IAM** | Gắn policy cho nhóm objects theo prefix | UBLA cần bật; quyền của bucket/project vẫn kế thừa |
| **Hierarchical namespace folder** | Biểu diễn thư mục thật trong bucket HNS | Khác managed folder và flat prefix, dù có thể kết hợp |
| **Object ACL** | Quyền riêng từng object trong fine-grained mode | Bị vô hiệu hóa khi bật UBLA |

### 8.4. IAM deny không đặt trực tiếp lên managed folder

IAM deny policies đặt ở **project/folder/organization**, không phải trực tiếp trên bucket hay managed folder; managed folder không dùng làm resource trong điều kiện deny theo cách giới hạn tài nguyên con trực tiếp. Vì vậy **thiết kế phân quyền nên bắt đầu từ ranh giới bucket/project hợp lý**, không kỳ vọng “deny một prefix” luôn sửa được project-level allow đã cấp quá rộng.

## 9. Phân quyền không dùng service account key dài hạn

Trong ứng dụng Java trên Compute Engine, GKE hoặc Cloud Run, danh tính chạy ứng dụng nên là **service account gắn với workload**, với role tối thiểu trên bucket hay managed folder.

~~~mermaid
flowchart LR
    APP["Java API trên Cloud Run"] --> ADC["Application Default Credentials"]
    ADC --> SA["Service account của workload"]
    SA --> IAM["IAM binding trên bucket/managed folder"]
    IAM --> GCS["Cloud Storage objects"]
~~~

Các nguyên tắc:

1. **Không hardcode JSON private key** trong source code, Docker image hay YAML manifest.
2. Gắn service account đúng môi trường **dev/staging/prod**, tránh dùng cùng quyền rộng cho mọi stage.
3. Với runner ngoài Google Cloud, dùng **Workload Identity Federation** khi phù hợp để tránh key dài hạn; **UBLA** phải bật trên bucket để các federated principals được hỗ trợ.
4. Dùng **Application Default Credentials** trong Google Cloud Java Client Library.
5. Không dùng **public IAM bindings** như một cách tránh lỗi 403 khi app thiếu quyền.
6. Xác định quyền **đọc, list, create, overwrite, delete** khác nhau. Upload với **Object Creator** có thể thành công với tên mới nhưng thất bại khi ghi đè.

### Signed URLs vẫn cần bảo vệ

Một backend có thể tạo **V4 signed URL** cho khách hàng tải object trong một khoảng thời gian. PAP không chặn signed URLs, vì chúng được ủy quyền bằng chữ ký và quyền thích hợp của principal ký.

Các lưu ý:

- Chỉ ký **object và method cần thiết**.
- Thời gian hiệu lực tối thiểu phù hợp; tránh log URL đầy đủ vì link chứa thông tin có thể dùng lại.
- Người nhận link có thể chia sẻ lại link trong thời gian hiệu lực; signed URL **không xác minh danh tính của mỗi người cầm link**.
- Thu hồi quyền ký hoặc đổi cơ chế access không bảo đảm tức thì thu hồi mọi signed URL đã phát; chuẩn bị kế hoạch nếu link bị lộ.
- Đánh giá chi phí **egress và operations** khi khách hàng tải nhiều.

## 10. Organization policies: guardrail ở cấp cao hơn

### 10.1. Hai constraint thường dùng

| Constraint | Tác dụng | Cần hiểu rõ |
|---|---|---|
| **constraints/storage.publicAccessPrevention** | Chặn quyền công khai cho các buckets thuộc phạm vi khi enforced | Bucket metadata inherited vẫn có thể chịu PAP |
| **constraints/storage.uniformBucketLevelAccess** | Yêu cầu bucket mới có UBLA; ngăn tắt UBLA nếu đã bật | Không tự động chuyển mọi bucket cũ chưa có UBLA sang ON |

Ví dụ:

~~~text
Organization: company.example
  └── Folder production
       └── Project shop-prod-001
            ├── Bucket private-contracts (UBLA, PAP)
            └── Bucket internal-reports   (UBLA, PAP)

Org policy trên folder production:
  storage.publicAccessPrevention = enforced
  storage.uniformBucketLevelAccess = enforced
~~~

Người quản trị bucket **không thể tự bỏ PAP** nếu organization policy cấp trên đang enforced. Việc quản trị organization policy yêu cầu IAM role thích hợp và change control riêng.

### 10.2. Policies áp dụng có thể có độ trễ

Thay đổi organization constraints có thể cần thời gian lan truyền; tài liệu Google Cloud nêu độ trễ thực thi có thể đến **10 phút** trong một số trường hợp. Kiểm tra trạng thái và thử access thực tế. Không kết luận “đã bảo vệ mọi object” chỉ vì lệnh set policy trả thành công.

### 10.3. Phạm vi áp dụng và ngoại lệ

Nếu dữ liệu thực sự phải được công bố công khai, đừng nới PAP toàn organization chỉ để một bucket images hoạt động. Hãy thiết kế kiến trúc **private access qua CDN/load balancer** nếu đáp ứng nhu cầu, hoặc quản trị ngoại lệ policy ở phạm vi hẹp được đánh giá/phê duyệt. Với project không thuộc organization, không thể dựa vào org policy; phải bật PAP trực tiếp trên bucket cần bảo vệ.

## 11. Thực hành CLI A: tạo bucket private theo baseline

**Mục tiêu:** tạo một bucket của project lab với **UBLA ON + PAP enforced**, sau đó cấp quyền đọc và upload đúng người dùng. Các project, bucket và service account bên dưới là **giả định**; thay bằng tài nguyên có quyền hợp lệ.

| Tham số | Giá trị ví dụ | Mục đích |
|---|---|---|
| Project | **shop-dev-001** | Môi trường lab |
| Bucket | **shop-private-docs-REPLACE-UNIQUE** | Tên phải duy nhất toàn cầu |
| Location | **asia-southeast1** | Chọn theo residency/latency/giá |
| Data reader | **group:analysts@example.com** | Quyền xem báo cáo |
| Upload worker | **serviceAccount:upload-worker@shop-dev-001.iam.gserviceaccount.com** | Chỉ tạo object mới |

### Bước 1 — Kiểm tra ngữ cảnh gcloud

~~~bash
gcloud config get-value project
gcloud auth list
gcloud projects describe shop-dev-001
~~~

Xác nhận đang đăng nhập đúng tài khoản quản trị được phép và không dùng project production một cách vô ý. Muốn tạo bucket cần quyền tạo bucket trên project; muốn sửa bucket IAM cần quyền **storage.buckets.setIamPolicy** ở phạm vi phù hợp.

### Bước 2 — Tạo bucket với UBLA và PAP

~~~bash
gcloud storage buckets create \
  gs://shop-private-docs-REPLACE-UNIQUE \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access \
  --public-access-prevention
~~~

**Đây là thao tác tạo tài nguyên có thể phát sinh chi phí.** Không dùng tên bucket đã tồn tại; không nên coi các project/domain trong ví dụ là tài nguyên thực.

### Bước 3 — Xem UBLA/PAP ở bucket

~~~bash
gcloud storage buckets describe gs://shop-private-docs-REPLACE-UNIQUE \
  --format="default(uniform_bucket_level_access)"

gcloud storage buckets describe gs://shop-private-docs-REPLACE-UNIQUE \
  --format="default(public_access_prevention)"

gcloud storage buckets get-iam-policy \
  gs://shop-private-docs-REPLACE-UNIQUE
~~~

Kết quả cần được đọc cùng **effective organization policy** và project IAM, vì quyền kế thừa có thể không hiện trong output bucket IAM trực tiếp.

### Bước 4 — Cấp quyền đọc cho nhóm phân tích

~~~bash
gcloud storage buckets add-iam-policy-binding \
  gs://shop-private-docs-REPLACE-UNIQUE \
  --member="group:analysts@example.com" \
  --role="roles/storage.objectViewer"
~~~

**Object Viewer có thể list toàn bộ objects** trong bucket. Chỉ dùng ví dụ này nếu bucket được thiết kế dành riêng cho nhóm analysts. Nếu bucket chứa dữ liệu nhiều nhóm, hãy dùng managed folder hoặc tách bucket và quyền phù hợp.

### Bước 5 — Cấp quyền upload cho service account

~~~bash
gcloud storage buckets add-iam-policy-binding \
  gs://shop-private-docs-REPLACE-UNIQUE \
  --member="serviceAccount:upload-worker@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"
~~~

Lệnh trên không tạo service account. Service account phải tồn tại và workload được phép sử dụng nó; yêu cầu **storage.objects.create** sẽ được xét khi thực thi. **Không cấp Storage Admin chỉ để upload một object mới**.

### Bước 6 — Đọc lại policy

~~~bash
gcloud storage buckets get-iam-policy \
  gs://shop-private-docs-REPLACE-UNIQUE
~~~

Kiểm tra **hai bindings đã được thêm**, không có public principal ngoài ý muốn, và role không rộng hơn thiết kế. Nếu CLI báo thiếu quyền, không tăng role toàn project theo phản xạ; xác định permission cụ thể đang thiếu.

### Bước 7 — Kiểm tra public access từ phía ngoài

Giả sử bạn đã upload một object test **healthcheck.txt** bằng danh tính được phép. Khi PAP enforced, một yêu cầu anonymous trực tiếp:

~~~bash
curl -I "https://storage.googleapis.com/shop-private-docs-REPLACE-UNIQUE/healthcheck.txt"
~~~

Kỳ vọng request **không được lấy nội dung như public object** (thường 401/403), nhưng mã chính xác còn phụ thuộc endpoint, header, cache và sự tồn tại của object. **Không dựa vào một HEAD request thành công/thất bại duy nhất để chứng minh hoàn chỉnh security posture**; cần kiểm tra IAM/PAP và các đường phát nội dung khác.

### Bước 8 — Thay đổi policy nhỏ, có kiểm soát

Nếu nhóm analysts không còn cần quyền trên bucket:

~~~bash
gcloud storage buckets remove-iam-policy-binding \
  gs://shop-private-docs-REPLACE-UNIQUE \
  --member="group:analysts@example.com" \
  --role="roles/storage.objectViewer"
~~~

Thao tác này **chỉ gỡ binding cụ thể**, không thay thế toàn bộ IAM policy như lệnh **set-iam-policy**. Nếu user vẫn đọc được sau khi gỡ, kiểm tra **quyền kế thừa ở project/folder/org**, principal khác hoặc signed URL thay vì kết luận lệnh xóa thất bại.

## 12. Thực hành CLI B: bật UBLA/PAP cho bucket đã tồn tại

**Tình huống:** bucket **legacy-docs-REPLACE-UNIQUE** được tạo nhiều năm trước với fine-grained ACL. Mục tiêu là chuyển sang quyền IAM và chặn public access, không làm gián đoạn workflow vẫn đang dùng ACL.

### 12.1. Bước 1 — Inventory trước khi thay đổi

~~~bash
gcloud storage buckets describe gs://legacy-docs-REPLACE-UNIQUE \
  --format="default(uniform_bucket_level_access)"

gcloud storage buckets describe gs://legacy-docs-REPLACE-UNIQUE \
  --format="default(public_access_prevention)"

gcloud storage buckets get-iam-policy \
  gs://legacy-docs-REPLACE-UNIQUE
~~~

Đồng thời cần:

- Xem bucket/object **ACLs và default object ACL** khi UBLA còn tắt bằng Console/API hoặc công cụ tương thích.
- Xem project/folder/org IAM policies có grants được kế thừa.
- Ghi nhận các job gọi **getAcl, setAcl, predefinedAcl, publicRead** hoặc sửa owner của object.
- Kiểm tra các service accounts, cross-project jobs và client libraries đang sử dụng bucket.
- Phân tích xem các objects có yêu cầu **quyền khác nhau theo từng object**, không thể chuyển thẳng một binding toàn bucket.

### 12.2. Bước 2 — Dùng Cloud Monitoring nhận diện ACL còn được dùng

Trong **Cloud Monitoring → Metrics Explorer**:

1. Chọn resource type **GCS Bucket**.
2. Chọn nhóm metric **Authz → ACLs usage**.
3. Metric là **storage.googleapis.com/authz/acl_operations_count**.
4. Lọc theo bucket liên quan, nhóm theo **acl_operation**.
5. Tìm trường hợp **OBJECT_ACCESS_REQUIRED_OBJECT_ACL**, tức đã có request cần quyền ACL riêng để được truy cập.

Nếu count lớn hơn 0, phải xác định caller/object ACL cần được thay bằng IAM. Giá trị 0 giảm rủi ro nhưng **không chứng minh không có workflow chưa chạy**; metric lưu dữ liệu sử dụng ACL trong tối đa khoảng **24 tháng**, không thể đảm bảo phản ánh tất cả batch job rất hiếm.

### 12.3. Bước 3 — Lập bản đồ chuyển ACL sang IAM

| Quyền cũ | Chuyển đổi cần cân nhắc | Bẫy |
|---|---|---|
| Object ACL **READER** cho một user | IAM Object Viewer/legacy Object Reader ở phạm vi thích hợp | Gán Viewer toàn bucket có thể cho đọc **mọi object**, rộng hơn ACL cũ |
| Object ACL **OWNER** | IAM role chứa permissions cần thiết, giới hạn resource | Không mặc nhiên cấp Storage Admin |
| Default object ACL áp cho object mới | Bucket/managed folder IAM bindings cho uploader và readers | Object Creator không cho overwrite |
| ACL public trên một vài ảnh | Tách bucket nội dung công khai hoặc private delivery/signed URLs | UBLA không có object ACL; PAP sẽ chặn public IAM |
| ACL theo team hoặc prefix | **Managed folder IAM**, IAM Conditions hoặc nhiều buckets | Cần UBLA trước; quyền kế thừa vẫn hiệu lực |

Việc mapping 1:1 không luôn khả thi. Đôi khi cách đúng là **tách dữ liệu vào nhiều buckets** trước khi bật UBLA, thay vì biến quyền đọc một file thành quyền đọc cả kho dữ liệu.

### 12.4. Bước 4 — Chuyển workflow sang IAM và kiểm thử

Thực hiện trên staging hoặc một tập object đại diện:

1. Cấp IAM bindings tối thiểu trước khi bỏ ACL.
2. Đảm bảo các service accounts thực sự có quyền **storage.objects.get/create/list/delete** cần thiết.
3. Sửa ứng dụng legacy để không ghi hoặc đọc object ACL.
4. Kiểm thử positive cases cho các reader/writer được cho phép.
5. Kiểm thử negative cases cho principal không được phép và những paths ngoài phạm vi.
6. Lưu snapshot/export policy phục vụ change review; tránh đưa token hay dữ liệu nhạy cảm vào báo cáo.

### 12.5. Bước 5 — Bật UBLA

~~~bash
# Có tác động lên quyền truy cập của bucket hiện hữu.
gcloud storage buckets update \
  gs://legacy-docs-REPLACE-UNIQUE \
  --uniform-bucket-level-access
~~~

Sau khi bật, yêu cầu dựa hoàn toàn vào object ACL sẽ bị từ chối. Bởi vậy phải chọn maintenance/change window và có người hỗ trợ xử lý quyền, theo dõi 403/400 từ ứng dụng sau khi triển khai.

### 12.6. Bước 6 — Bật PAP và dọn public IAM bindings

~~~bash
gcloud storage buckets update \
  gs://legacy-docs-REPLACE-UNIQUE \
  --public-access-prevention
~~~

**Không nên dừng ở lệnh này:** nếu public IAM/ACL cũ tồn tại, PAP chỉ **vô hiệu hóa** chúng. Với bucket UBLA ON, hãy rà soát và **gỡ public IAM bindings** đã còn sót; ghi nhận chúng để tránh tái lộ khi PAP bị đổi trong tương lai.

Ví dụ lệnh gỡ **một** binding public nếu nó thực sự đang tồn tại trong policy của bucket:

~~~bash
gcloud storage buckets remove-iam-policy-binding \
  gs://legacy-docs-REPLACE-UNIQUE \
  --member=allUsers \
  --role=roles/storage.objectViewer
~~~

Lệnh trên chỉ là ví dụ gỡ role phổ biến. Cần xem mọi bindings và IAM Conditions; có thể có các role công khai khác. Nếu đang bị organization policy bảo vệ, **không nới policy cấp trên** chỉ để làm các bước kiểm thử.

### 12.7. Bước 7 — Kiểm chứng và rollback

~~~bash
gcloud storage buckets describe gs://legacy-docs-REPLACE-UNIQUE \
  --format="default(uniform_bucket_level_access,public_access_prevention)"

gcloud storage buckets get-iam-policy \
  gs://legacy-docs-REPLACE-UNIQUE
~~~

Kiểm tra trên **data plane** (tài khoản ứng dụng thật), không chỉ readback metadata:

- Đúng danh tính có quyền: upload/download/list theo thiết kế.
- Danh tính không có quyền: bị từ chối đúng.
- Truy cập anonymous: không đọc được object private.
- Những client legacy còn gọi ObjectAccessControls phải được chuyển đổi.

**Rollback UBLA có điều kiện rất chặt:** chỉ dưới 90 ngày bật liên tục, không còn managed folders/bucket IAM Conditions và không có org constraint bắt buộc UBLA. Tắt UBLA có thể phục hồi ACL cũ, nên phải review lại public exposure. **Không chủ động tắt PAP** để xử lý sự cố access nếu chưa kiểm tra rủi ro từ các public bindings tồn lưu.

## 13. Thực hành CLI C: managed folder cho nhóm tài liệu

**Tình huống:** bucket **company-docs-REPLACE-UNIQUE** đã bật UBLA/PAP. Nhóm pháp chế chỉ cần đọc objects bên dưới **contracts/**, không được đọc dữ liệu ở **payroll/**.

**Tiền đề quan trọng:** principal pháp chế **không có Object Viewer ở project hay bucket** bao trùm tất cả objects. Nếu đang có role rộng ở tổ tiên, cấp role trên managed folder **không làm thu hẹp** quyền ấy.

### 13.1. Tạo managed folder

~~~bash
# Bucket phải có UBLA và principal phải đủ quyền quản lý managed folder
gcloud storage managed-folders create \
  gs://company-docs-REPLACE-UNIQUE/contracts/
~~~

Managed folder là resource khác với chuỗi prefix đơn thuần. Tên phải kết thúc bằng **/** và tuân thủ quy tắc tên của Cloud Storage.

### 13.2. Cấp quyền trên managed folder

~~~bash
gcloud storage managed-folders add-iam-policy-binding \
  gs://company-docs-REPLACE-UNIQUE/contracts/ \
  --member="group:legal@example.com" \
  --role="roles/storage.objectViewer"
~~~

IAM của managed folder áp dụng cho objects bắt đầu bằng prefix **contracts/**. Không cần làm từng object ACL. Nếu managed folders lồng nhau, quyền được kế thừa/cộng dồn theo phân cấp hỗ trợ.

### 13.3. Kiểm tra policy và thực tế

~~~bash
gcloud storage managed-folders get-iam-policy \
  gs://company-docs-REPLACE-UNIQUE/contracts/

gcloud storage buckets get-iam-policy \
  gs://company-docs-REPLACE-UNIQUE
~~~

Thực hiện các phép thử bằng identity thật của legal user:

| Phép thử | Kỳ vọng |
|---|---|
| GET **contracts/contract-001.pdf** | Thành công nếu object tồn tại, đủ IAM và các guardrails khác |
| GET **payroll/salary.csv** | Bị từ chối nếu không có quyền kế thừa khác |
| DELETE **contracts/contract-001.pdf** | Bị từ chối với Object Viewer |
| Public GET object thuộc contracts/ | Bị từ chối khi PAP enforced |
| List toàn bộ bucket | Phải xác minh theo quyền thực tế; không được tự suy rằng folder viewer được phép khám phá tất cả prefixes |

**Dùng managed folder khi thực sự có nhiều objects thuộc cùng một nhóm quyền**, không phải vì muốn thay thế mọi phân đoạn bucket/project. Nếu dữ liệu có mức nhạy cảm khác biệt lớn, tách thành buckets/projects riêng giúp kiểm soát quyền kế thừa và retention rõ hơn.

## 14. IAM Conditions theo prefix và thời gian

Trong một bucket **UBLA ON**, có thể gắn điều kiện vào IAM binding khi muốn một quyền chỉ áp dụng cho object phù hợp.

### 14.1. Ví dụ: chỉ đọc objects báo cáo

Điều kiện CEL:

~~~text
resource.name.startsWith(
  'projects/_/buckets/company-docs-REPLACE-UNIQUE/objects/reports/'
)
~~~

Có thể dùng với IAM binding của principal thích hợp. Ví dụ minh họa cấu trúc IAM Condition để review:

~~~yaml
title: ReportsPrefixOnly
description: Chỉ áp dụng quyền lên các object thuộc reports/
expression: "resource.name.startsWith('projects/_/buckets/company-docs-REPLACE-UNIQUE/objects/reports/')"
~~~

Khi sử dụng **gcloud storage buckets add-iam-policy-binding** có thể truyền file condition bằng **--condition-from-file**. Ví dụ giả định người vận hành đã lưu đúng cấu trúc trên thành **reports-condition.yaml**:

~~~bash
gcloud storage buckets add-iam-policy-binding \
  gs://company-docs-REPLACE-UNIQUE \
  --member="group:report-auditors@example.com" \
  --role="roles/storage.objectViewer" \
  --condition-from-file=reports-condition.yaml
~~~

**Giới hạn:** vì **storage.objects.list** được kiểm tra ở **bucket resource**, một điều kiện chỉ khớp object resource name **không cho phép list tùy ý trong reports/ một cách giống get**. Cần thiết kế quyền liệt kê phù hợp hoặc dùng managed folder với đúng khả năng sản phẩm, rồi thử từng API.

### 14.2. Điều kiện hết hạn quyền

~~~text
request.time < timestamp('2027-01-01T00:00:00Z')
~~~

Điều kiện có thể phù hợp khi cấp quyền tạm cho đối tác audit. Tuy nhiên IAM Conditions **không xóa binding khi hết hạn**; policy vẫn lưu binding. Cần cleanup định kỳ và đối chiếu IAM policy versions, đặc biệt với công cụ dùng **set-iam-policy**.

### 14.3. Đừng dùng sai thuộc tính CEL

Cloud Storage bucket IAM Conditions chỉ hỗ trợ một tập thuộc tính tương ứng, phổ biến như **resource.name, resource.type, request.time**. Không giả định mọi context property như **device posture, client IP, request.path** đều được hỗ trợ trong Cloud Storage IAM binding.

Nếu muốn kiểm soát theo mạng, xét sản phẩm và cơ chế được hỗ trợ như **VPC Service Controls**, bucket IP filtering hoặc kiến trúc mạng phù hợp. Không sao chép nguyên IAM Condition dành cho IAP rồi kỳ vọng Cloud Storage hiểu cùng trường request.

## 15. Tình huống thiết kế: công bố nội dung nhưng bucket vẫn private

Một ứng dụng bán hàng cần cho khách hàng xem ảnh sản phẩm công khai, đồng thời lưu hợp đồng và báo cáo riêng tư.

### 15.1. Cách dễ sai

Đặt ảnh và hợp đồng trong cùng bucket rồi cấp:

~~~text
member: allUsers
role: roles/storage.objectViewer
scope: toàn bộ bucket
~~~

Nếu PAP không enforced, binding đó có thể cho **mọi người đọc/liệt kê objects** thuộc bucket, bao gồm cả dữ liệu không nên public. Bật UBLA không ngăn tình huống này.

### 15.2. Phương án tách trách nhiệm

~~~mermaid
flowchart LR
    CUSTOMER["Khách hàng"] --> EDGE["HTTPS LB / Cloud CDN hoặc signed URL"]
    EDGE --> IMG["Bucket product-media<br/>UBLA + kiểm soát public"]
    API["Java API trên Cloud Run"] --> PRIVATE["Bucket private-contracts<br/>UBLA + PAP"]
    ANALYST["Nhóm phân tích được ủy quyền"] --> REPORT["Bucket reports<br/>UBLA + PAP"]
    CI["Pipeline deploy"] --> ART["Bucket artifacts<br/>UBLA + PAP"]
~~~

| Bucket | Dữ liệu | Chính sách gợi ý | Cách truy cập |
|---|---|---|---|
| **product-media** | Ảnh sản phẩm đã phê duyệt | UBLA; PAP có thể enforced nếu dùng private bucket access/CDN hoặc signed URLs theo kiến trúc hỗ trợ | Frontend được phát qua cơ chế phù hợp |
| **private-contracts** | Hợp đồng khách hàng | UBLA ON, PAP enforced | Backend service account và người dùng nội bộ có quyền |
| **reports** | Báo cáo doanh thu | UBLA ON, PAP enforced | Nhóm phân tích theo managed folder/bucket IAM |
| **artifacts** | Package CI/CD | UBLA ON, PAP enforced | Pipeline service account và runner được ủy quyền |

**Không nên nới PAP ở cả project** chỉ để public một số ảnh. Có thể dùng **private bucket access** qua load balancer/CDN được hỗ trợ, hoặc signed URL trong quy trình kiểm soát. Nếu thật sự cần object công khai trực tiếp, hãy tách bucket riêng và thực hiện ngoại lệ theo chính sách tổ chức được phê duyệt.

### 15.3. Khi nào dùng signed URLs?

Signed URL phù hợp cho:

- Khách hàng tải một hợp đồng riêng sau khi ứng dụng đã kiểm tra họ được phép.
- Đối tác upload file vào **một object path được định trước**, trong thời gian ngắn.
- Trình duyệt tải file dung lượng lớn trực tiếp mà backend không phải proxy mọi byte.

Thiết kế cần đánh giá **thời gian sống, ký GET/PUT theo method, HTTPS, Content-Type nếu ký, quyền người ký, audit và rủi ro URL bị chia sẻ**. PAP không vô hiệu hóa signed URL, nên **không thể coi signed URL là phương thức bị chặn trong chính sách không cho public IAM**.

## 16. Ví dụ ứng dụng Java và pipeline CI/CD

### 16.1. Java trên Cloud Run upload bằng Application Default Credentials

Giả sử Java API chỉ được upload object mới trong bucket private. Service account của Cloud Run có **roles/storage.objectCreator** trên bucket thích hợp.

~~~java
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PrivateDocumentUploader {
    private final Storage storage =
        StorageOptions.getDefaultInstance().getService();

    public void uploadOnce(String bucket, String objectName, Path file)
            throws Exception {
        BlobInfo target = BlobInfo.newBuilder(bucket, objectName)
            .setContentType("application/pdf")
            .build();

        // Dành cho object nhỏ trong bài học; production nên dùng streaming.
        byte[] data = Files.readAllBytes(file);
        storage.create(
            target,
            data,
            Storage.BlobTargetOption.doesNotExist()
        );
    }
}
~~~

**Điểm bảo mật quan trọng:**

- Java client dùng **ADC**, không cần tải JSON key lên Cloud Run.
- **doesNotExist()** tránh vô tình ghi đè object đã tồn tại; cần xử lý lỗi điều kiện object đã tồn tại thay vì retry vô hạn.
- **Object Creator** đủ để tạo mới, nhưng không cấp quyền download/delete. Nếu ứng dụng phải trả lại nội dung, cần thiết kế thêm role đọc phù hợp ở bucket/managed folder, hoặc tách read service.
- Với file lớn, không đọc toàn bộ vào RAM như ví dụ; sử dụng **streaming/resumable uploads** được client library hỗ trợ.
- Tên **objectName** cần được validate để không cho người dùng nhập tên thuộc prefix của đối tượng khác trong cùng bucket theo cách vượt logic phân quyền ứng dụng.

### 16.2. CI/CD bên ngoài Google Cloud

Ví dụ GitHub Actions build ảnh/artefact rồi upload lên một bucket chỉ dành cho release:

1. Cấu hình **Workload Identity Federation** giữa GitHub OIDC và Google Cloud, giới hạn repo/branch/environment đáng tin cậy.
2. Dùng **service account dành cho deploy**, được cấp IAM role tối thiểu trên artifacts bucket.
3. Bật **UBLA** để access của federated principal hoạt động đúng phạm vi Cloud Storage hỗ trợ.
4. Bật **PAP** vì artifacts không cần quyền công khai.
5. Dùng generation preconditions hoặc tên artifact bất biến theo version/hash để tránh ghi đè giữa hai pipeline.
6. Kiểm tra quyền âm tính: fork/repo/branch không được phép không thể upload hoặc đọc artifacts nhạy cảm.

**Không dùng allAuthenticatedUsers** để CI/CD “có quyền mà không cần xác thực chi tiết”. Giá trị đó không chỉ giới hạn ở tổ chức và có thể bao gồm các chủ thể đã xác thực ngoài doanh nghiệp.

### 16.3. Điểm khác nhau giữa dữ liệu và control plane

| Hoạt động | Nhóm quyền cần nghĩ đến | Cảnh báo |
|---|---|---|
| Upload object mới | storage.objects.create | Object Creator không nhất thiết cho đọc hoặc overwrite |
| GET object | storage.objects.get | Còn phụ thuộc IAM allow/deny và PAP nếu truy cập bằng public principal |
| List objects | storage.objects.list | Thường kiểm tra trên bucket, khác get theo object name |
| Delete object | storage.objects.delete | Rủi ro mất dữ liệu; cân nhắc soft delete/versioning |
| Xem bucket metadata | storage.buckets.get | Không đồng nghĩa có quyền xem nội dung |
| Sửa bucket IAM | storage.buckets.setIamPolicy | Quyền mạnh hơn object read/write |
| Chỉnh UBLA/PAP | storage.buckets.update và quyền liên quan | Ảnh hưởng nhiều client; cần review và quyền thích hợp |

## 17. Audit logs, giám sát và phát hiện cấu hình rủi ro

### 17.1. Phân loại tín hiệu

| Nguồn | Dùng để làm gì | Lưu ý |
|---|---|---|
| **Cloud Audit Logs Admin Activity** | Theo dõi các thay đổi quản trị như IAM/policy | Kiểm tra project và định danh caller |
| **Data Access audit logs** | Theo dõi truy cập object khi bật và theo phạm vi hỗ trợ | Có thể phải bật riêng; có quota/chi phí logging |
| **Cloud Monitoring ACL usage metric** | Xác định phụ thuộc ACL trước khi bật UBLA | Metric **authz/acl_operations_count** không phải danh sách mọi identity trong lịch sử |
| **Security Command Center findings** khi cấu hình phù hợp | Phát hiện bucket public hoặc security misconfiguration | Tùy plan, coverage và detector được bật |
| **IAM Policy Analyzer/Troubleshooter** theo quyền và dịch vụ hỗ trợ | Điều tra principal có quyền do policy nào | Phải xét quyền kế thừa và deny |
| **Cloud Billing reports** | Xem chi phí lưu trữ, operations và egress | Chi phí log/kiểm toán có thể tăng theo mức sử dụng |

### 17.2. Bộ cảnh báo nên có

- Thay đổi **public access prevention** hoặc **uniform bucket-level access** trên bucket production.
- IAM policy có binding mới với **allUsers** hoặc **allAuthenticatedUsers**; kể cả PAP đang bật, đây vẫn là cấu hình nguy hiểm nếu PAP bị gỡ sau này.
- Tài khoản không thuộc nhóm quản trị cố sửa **setIamPolicy** nhiều lần.
- Tăng đột ngột 403/401 trên object GET/PUT sau một change.
- Data Access logs hoặc network egress tăng bất thường ở bucket nhạy cảm.
- Các access keys, service accounts hoặc signed URLs phát hành theo quy trình không mong muốn.

### 17.3. Audit logging không phải kho bằng chứng tuyệt đối

Theo tài liệu, **truy cập tới objects công khai** không được Cloud Audit Logs ghi đầy đủ như truy cập được ủy quyền cụ thể. Khi bật PAP, một số request trước đây công khai có thể trở thành request đã xác thực/được log; volume Data Access logs có thể tăng. Điều này ảnh hưởng đến **quy trình kiểm toán và chi phí**, không chỉ trạng thái bảo mật.

Không lưu access tokens, signed URLs đầy đủ hoặc nội dung tài liệu nhạy cảm trong application logs. Khi cần điều tra, kết hợp logs từ app, load balancer/CDN, Cloud Storage và IAM changes.

## 18. Troubleshooting: đọc đúng mã lỗi và ranh giới quyền

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| **403 Forbidden** khi Java GET object | Service account thiếu **storage.objects.get**, IAM deny hoặc policy khác chặn | ADC identity, bucket/project inherited IAM, deny, resource name |
| **403** khi pipeline overwrite object | Chỉ có **Object Creator**, thiếu delete hoặc precondition gây lỗi | Quyền create/delete, generation conditions, object existence |
| **400 Bad Request** khi set/get Object ACL | Bucket có **UBLA ON** | Dừng gọi ACL APIs, chuyển sang IAM |
| **412 Precondition Failed** khi cấp **allUsers** | PAP enforced ở bucket hoặc organization | PAP bucket state, org policy; không nới public để vượt guardrail |
| IAM bucket có vẻ không cấp đọc nhưng user vẫn GET | Role từ project/folder/org, hoặc client dùng signed URL | Effective IAM, group membership, signed link và caches |
| Bật UBLA xong client cũ mất quyền | Client dựa vào object ACL hoặc set ACL khi upload | Metric ACL usage, mapping sang IAM, sửa SDK/API calls |
| Metadata bucket ghi **PAP inherited** | Org policy có thể đang enforced hoặc không | Kiểm tra effective org policy thay vì suy từ chữ inherited |
| Đã bật PAP nhưng CDN/browser vẫn hiển thị nội dung cũ | Object còn trong cache ngoài | Cache-Control/TTL, CDN invalidation theo quy trình |
| Đã bật PAP nhưng signed URL vẫn tải được | **Hành vi đúng theo thiết kế** | Kiểm tra người phát hành signed URL, TTL, scope |
| Managed folder role cấp rồi nhưng legal vẫn đọc payroll | Đã có Object Viewer ở project/bucket hoặc nhóm khác | Kiểm tra inherited IAM, không chỉ managed-folder policy |
| IAM Condition theo prefix không list được bucket | **storage.objects.list** dùng bucket resource name | Thiết kế managed folder/list permissions hoặc tách bucket |
| Không thể tắt UBLA | Đã 90 ngày, có managed folder/condition hoặc org policy | Kiểm tra bốn điều kiện trước khi rollback |
| Không tạo được managed folder | UBLA OFF hoặc thiếu role/quyền | Bucket UBLA, roles/storage.folderAdmin và path |
| Anonymous request được trả 404 thay vì 403 | Không thấy object, endpoint/caching hoặc phản hồi được che giấu | Xác minh policy và kết quả trên object test có tồn tại |
| Signed URL báo 403 | Link hết hạn, signature sai, principal ký không có quyền, object không tồn tại | Signer, method, timestamp, object, headers |
| Update bucket báo thiếu quyền dù đọc object được | Thiếu **storage.buckets.update/setIamPolicy** | Phân biệt data plane và control plane |

### 18.1. Quy trình khoanh vùng lỗi

1. **Caller là ai?** User, service account, workload identity, anonymous hay signed URL?
2. **Thao tác gì?** GET, LIST, CREATE, overwrite, DELETE, ACL hoặc bucket IAM update?
3. **Resource nào?** Bucket, managed folder, object path chính xác, generation nếu có?
4. **UBLA/PAP ở trạng thái nào?** Đọc metadata bucket và effective organization policy.
5. **IAM nào cấp quyền?** Direct bucket IAM, managed folder IAM, inherited project/folder/org hoặc conditional binding?
6. **Có chặn khác không?** IAM deny, VPC Service Controls, retention hold, bucket IP filtering, encryption key policy?
7. **Kết quả thử âm tính ra sao?** Một identity không được phép phải thật sự bị từ chối; không chỉ kiểm tra đường được phép.
8. **Vừa có thay đổi gì?** IAM propagation, PAP enforcement, cache, bucket policy, CI/CD rollout và client library upgrade.

Không sửa sự cố access bằng cách cấp **roles/editor/owner** cho cả project hoặc tắt **PAP** nếu chưa biết nguyên nhân.

## 19. Tình huống tổng hợp: bảo vệ dữ liệu bán hàng

Doanh nghiệp **Hải Phong** có ba dự án:

- **shop-dev-001:** môi trường thử nghiệm.
- **shop-prod-001:** API Java, Cloud Run, GKE và bucket production.
- **security-ops-001:** hệ thống giám sát, workflow rà soát thay đổi IAM.

Cần quản lý bốn nhóm dữ liệu:

1. **Product images**: khách hàng cần xem được.
2. **Invoices và contracts**: thông tin cá nhân, chỉ backend và người có vai trò hợp lệ được truy cập.
3. **Reports**: nhóm phân tích truy cập trong phạm vi quyền.
4. **CI artifacts**: pipeline được phép upload, runtime chỉ được download khi thực sự cần.

### 19.1. Đề xuất cấu trúc buckets

| Bucket | UBLA | PAP | Chủ thể được cấp quyền | Lý do |
|---|---|---|---|---|
| shop-product-media | ON | Enforced nếu dùng private delivery/signed URLs phù hợp | Media publisher; distribution path đã thiết kế | Không mở vô tình cả bucket ra Internet |
| shop-private-invoices | ON | Enforced | Invoice API service account, nhóm kiểm toán theo phạm vi | Dữ liệu nhạy cảm, quyền chặt |
| shop-internal-reports | ON | Enforced | Nhóm phân tích hoặc managed folder IAM | Dễ review, không lộ cross-team |
| shop-build-artifacts | ON | Enforced | CI uploader và deployment runtime | Artifacts là supply chain input |

**Project-level IAM:** hạn chế cấp Storage Object Viewer/Storage Admin rộng trên production project, vì nó có thể làm mất ý nghĩa phân chia bucket theo domain.

### 19.2. Một tình huống sai chính sách

Một kỹ sư thấy trình duyệt không tải được ảnh và thêm **allUsers:roles/storage.objectViewer** cho **shop-product-media**, nhưng PAP đang enforced.

Kết quả:

- Lệnh có thể bị từ chối với **412**.
- Không nên tắt PAP để lệnh thành công. Phải xác định **đường phân phối ảnh** mà kiến trúc đã chọn: signed URL, private bucket access/CDN theo cấu hình hỗ trợ hoặc public bucket có ngoại lệ được phê duyệt.
- Nếu cố cấp allUsers ở bucket chứa invoices, phạm vi lộ dữ liệu có thể nghiêm trọng; một bucket riêng cho public assets là biện pháp tổ chức cần thiết.

### 19.3. Một tình huống migration gây gián đoạn

Bucket reports cũ có một file **sensitive/monthly.csv** chỉ cấp ACL READER cho kế toán. Người vận hành bật UBLA và cấp **roles/storage.objectViewer** ở **project** để “khôi phục quyền nhanh”.

Hệ quả:

- Client ACL-only có thể truy cập lại, nhưng role project khiến họ nhìn thấy những buckets khác.
- Đây là **privilege escalation ngoài chủ đích**. Cần thu hồi role quá rộng và cấp quyền đúng scope bằng managed folder hoặc tách bucket.
- Trước khi sửa chính sách production phải kiểm tra ai đang dùng dữ liệu, rollback theo quy trình và log mọi thay đổi.

### 19.4. Ma trận nghiệm thu

| Test | Kỳ vọng |
|---|---|
| Cloud Run invoice service GET hóa đơn được cấp | Thành công |
| Một service account của dev GET hóa đơn production | Bị từ chối |
| Khách hàng không có signed URL GET hóa đơn trực tiếp | Bị từ chối |
| Khách hàng có signed URL đúng scope/thời hạn tải một file | Thành công nếu signer/authorization đúng |
| CI uploader tạo artifact version mới | Thành công |
| CI uploader dùng Object Creator ghi đè artifact cũ | Không được theo role tối thiểu |
| Anonymous GET bucket contracts/reports | Bị từ chối khi PAP enforced |
| Kỹ sư cố thêm allUsers trên bucket protected | Bị PAP chặn |
| Team analysts đọc báo cáo nhưng không đọc invoices | Đúng nếu không có inherited role rộng |
| Tắt UBLA sau 90 ngày liên tục | Không được |
| Audit/logs | Có bằng chứng quản trị policy và data access trong phạm vi logging được bật |

### 19.5. Vận hành sau phát hành

- Định kỳ rà soát **IAM bindings cấp project/bucket/managed folder**, các groups và service accounts không còn sử dụng.
- Giám sát **public access posture**, thay đổi PAP/UBLA và vi phạm IAM.
- Theo dõi **egress/download volume**, vì bucket riêng tư nhưng bị tải lớn qua signed URLs hoặc backend vẫn có thể phát sinh chi phí đáng kể.
- Tập diễn tập **thu hồi quyền khi token/signing capability bị lộ** và xử lý thông tin đã bị cache/phát tán.
- Duy trì backup/soft delete/versioning/retention phù hợp; IAM/PAP không phải cơ chế khôi phục dữ liệu sau xóa hoặc corruption.

## 20. Bài tập thực hành và đáp án gợi ý

### Bài tập A — Phân biệt UBLA và PAP

Cho bucket **assets** có:

- UBLA = **ON**.
- PAP = **inherited**, nhưng organization policy không enforce PAP.
- IAM binding **allUsers → roles/storage.objectViewer** trên bucket.

**Câu hỏi:** Objects có thể được đọc công khai không? Bật UBLA có giúp chặn quyền allUsers này không?

**Đáp án:** Có thể public nếu không có cơ chế chặn khác. UBLA chỉ vô hiệu hóa ACL; IAM binding allUsers vẫn hiệu lực khi PAP không enforced.

### Bài tập B — Phân quyền upload

Service account **uploader** chỉ có **roles/storage.objectCreator** trên bucket private.

| Hoạt động | Kết quả dự kiến chỉ từ role đó |
|---|---|
| Tạo object có tên chưa tồn tại | **Cho phép** |
| GET object vừa upload | **Không có quyền từ role đó** |
| List toàn bucket | **Không có quyền từ role đó** |
| Overwrite object cũ | **Không có quyền phù hợp để replace** |
| Delete object | **Không có quyền từ role đó** |

Trong hệ thống thật, phải xét thêm các roles từ IAM policy khác. Nếu use case cần overwrite, hãy cấp chính xác permissions cần thiết sau khi review hoặc dùng object name mới/versioned.

### Bài tập C — Migrate ACL sang UBLA

Một bucket lưu 50.000 objects. Có:

- Một số objects được cấp ACL riêng cho bộ phận kế toán.
- Một job upload dùng predefined ACL **publicRead**.
- IAM trên bucket mới chỉ có người quản trị.

Hãy lập kế hoạch trước khi bật UBLA.

**Gợi ý đáp án:**

1. Inventory default/object ACL và **ACL usage metric**.
2. Xác định objects cần access khác nhau, tách buckets hoặc managed folder/prefix sau khi chuẩn bị.
3. Sửa job **publicRead** sang luồng phân phối thích hợp; không giả định publicRead hoạt động trong UBLA.
4. Cấp IAM tối thiểu, thử positive và negative cases.
5. Bật UBLA, đọc lại trạng thái, giám sát 400/403.
6. Bật PAP cho private data, xóa public IAM binding còn sót.
7. Ghi nhận giới hạn rollback dưới 90 ngày và chính sách tổ chức.

### Bài tập D — Xử lý báo lỗi 412

Một pipeline cố tạo IAM binding **allUsers Object Viewer** cho bucket đã bật PAP và nhận **412 Precondition Failed**.

**Câu hỏi:** Đây có phải lỗi thiếu quyền IAM của service account không? Nên khắc phục thế nào?

**Đáp án:** Không nhất thiết. Đây thường là phản hồi từ PAP ngăn public binding. Xác minh mục tiêu phân phối nội dung: dùng signed URL/private bucket delivery khi phù hợp hoặc giải quyết ngoại lệ qua quy trình bảo mật; không cấp Owner/Editor hay tắt PAP tùy tiện.

### Bài tập E — Managed folder và quyền kế thừa

Trong project **finance-prod**, nhóm **all-staff** được cấp Object Viewer ở cấp project. Bucket **finance-data** có managed folder **payroll/**, nhưng bạn chỉ cấp role đó cho nhóm **payroll-team** ở managed folder.

**Câu hỏi:** all-staff có còn quyền đọc payroll không?

**Đáp án:** Có thể có, vì role Object Viewer cấp ở project áp dụng xuống bucket/objects. Managed folder IAM **không trừ** quyền đã kế thừa. Phải sửa grant ở tổ tiên hoặc tách dữ liệu và policy theo ranh giới đúng.

### Bài tập F — Signed URL dưới PAP

Một hợp đồng được giữ trong bucket UBLA + PAP. Backend phát signed URL hợp lệ 10 phút cho khách hàng.

**Câu hỏi:** Link có bị PAP chặn không? Khách hàng có thể chuyển tiếp link cho người khác không?

**Đáp án:** PAP không chặn signed URL theo thiết kế. Người có URL hợp lệ có thể dùng nó trong phạm vi method/object/thời hạn; phải coi signed URL như bearer credential, đặt TTL ngắn, chỉ phát sau khi ứng dụng xác thực và kiểm soát rủi ro leak.

### Bài tập G — Chẩn đoán cuối tuần

Sau thay đổi bảo mật, API Java không tải được invoice; log có 403. Trong Console bucket IAM không thấy service account của API, nhưng nhóm vận hành nói API đã được cấp quyền ở project.

**Hãy kiểm tra:**

1. Đang dùng service account nào thực sự qua ADC?
2. Role từ project còn hiệu lực không, có IAM Condition/deny không?
3. Bucket có managed folder IAM nào không?
4. VPC Service Controls, retention hoặc CMEK có ảnh hưởng không?
5. Đường truy cập là API trực tiếp hay signed URL?
6. Có job/cấu hình nào vừa bật UBLA hoặc PAP làm thay đổi hành vi không?

**Đáp án định hướng:** 403 có thể do nhiều lớp. Đối chiếu caller, permission, resource, inherited roles và các guardrails; không sửa bằng cách công khai bucket.

## 21. Tổng kết và tài liệu tham khảo

**Tám nguyên tắc cần ghi nhớ:**

1. **IAM** xác định principal được phép thực hiện hành động nào; quyền có thể được **kế thừa** từ project/folder/organization và cộng dồn với quyền ở bucket/managed folder.
2. **Fine-grained ACL mode** cho phép IAM và ACL hoạt động song song, dễ có quyền ẩn ở từng object. **UBLA** tắt ACL và thống nhất quyền theo IAM.
3. **UBLA sau 90 ngày liên tục không thể tắt**. Trước khi migrate phải inventory ACL usage, chuyển IAM tương đương và thử workflow.
4. **UBLA không ngăn public IAM**; muốn chặn allUsers/allAuthenticatedUsers cần **PAP** hoặc ranh giới bảo vệ tương đương được thiết kế đúng.
5. **PAP ở cấp bucket enforced hoặc inherited từ org policy**; khi enforced, public IAM/ACL bị chặn/vô hiệu hóa nhưng bindings cũ không tự bị xóa.
6. **Signed URLs và private bucket delivery có thể hoạt động khi PAP bật**. PAP không thay thế kiểm soát phân phối dữ liệu, signed URL TTL, IAM, mạng hay application authorization.
7. **Managed folders/IAM Conditions** cho phân quyền theo nhóm object, nhưng vẫn chịu quyền IAM kế thừa; **storage.objects.list** có semantics theo bucket cần kiểm thử riêng.
8. **Bảo mật đáng tin cậy cần policy + test + audit + vận hành:** phân quyền tối thiểu, tách dữ liệu nhạy cảm, giám sát cấu hình và chuẩn bị rollback/khôi phục.

**Tài liệu Google Cloud chính thức để tra cứu:**

1. [Overview of Cloud Storage access control](https://docs.cloud.google.com/storage/docs/access-control) — chọn uniform hay fine-grained.
2. [Identity and Access Management for Cloud Storage](https://docs.cloud.google.com/storage/docs/access-control/iam) — policies, hierarchy, conditions và caveat.
3. [Cloud Storage IAM roles](https://docs.cloud.google.com/storage/docs/access-control/iam-roles) — permissions cụ thể theo role.
4. [Uniform bucket-level access](https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access) — hành vi, 90 ngày, managed folders và migration.
5. [Use uniform bucket-level access](https://docs.cloud.google.com/storage/docs/using-uniform-bucket-level-access) — bật/tắt/xác minh và metric ACL usage.
6. [Public access prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention) — enforced/inherited, signed URLs và các ngoại lệ.
7. [Use public access prevention](https://docs.cloud.google.com/storage/docs/using-public-access-prevention) — Console/gcloud và org policy.
8. [Organization policy constraints for Cloud Storage](https://docs.cloud.google.com/storage/docs/org-policy-constraints) — storage.publicAccessPrevention và storage.uniformBucketLevelAccess.
9. [Manage IAM policies on buckets](https://docs.cloud.google.com/storage/docs/access-control/using-iam-permissions) — CLI roles/conditions.
10. [Managed folders](https://docs.cloud.google.com/storage/docs/managed-folders) — phân quyền theo group object.
11. [Manage IAM for managed folders](https://docs.cloud.google.com/storage/docs/access-control/using-iam-for-managed-folders) — gcloud và chú ý kế thừa.
12. [IAM permissions for Cloud Storage](https://docs.cloud.google.com/storage/docs/access-control/iam-permissions) — quyền get/list/create/delete/setIamPolicy.
13. [Cloud Storage troubleshooting](https://docs.cloud.google.com/storage/docs/troubleshooting) — lỗi quyền, policy và public access.
