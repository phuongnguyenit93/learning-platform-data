# Phát hiện drift và tiếp nhận tài nguyên đã tồn tại

> **Chương:** Hạ tầng dưới dạng mã  
> **Module:** CLOUD_ARCHITECTURE  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai; cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích infrastructure drift và phân biệt thay đổi ngoài IaC, sai lệch state và thay đổi có chủ ý chưa được ghi nhận.
2. Xác định nguyên nhân và ảnh hưởng của drift tới bảo mật, độ tin cậy, chi phí, khả năng phục hồi và khả năng tái tạo môi trường.
3. Dùng plan/refresh và cơ chế kiểm tra phù hợp để phát hiện sai lệch mà không vô tình áp dụng thay đổi.
4. Phân loại drift cần giữ, cần hoàn nguyên hoặc cần cập nhật vào cấu hình chuẩn.
5. Tiếp nhận (import/adopt) tài nguyên cloud đang tồn tại vào state IaC mà không tạo tài nguyên trùng hoặc phá hủy workload.
6. Thiết kế ownership, state boundary, import workflow, review và safeguards cho quá trình chuyển đổi.
7. Xử lý tài nguyên phụ thuộc nhau, resource có dữ liệu, immutable field hoặc API provider không hỗ trợ import đầy đủ.
8. Tạo quy trình định kỳ để drift có owner, mức độ ưu tiên, thời hạn xử lý và bằng chứng kiểm chứng.

## 1. Infrastructure drift là gì?

Infrastructure as Code (IaC) mô tả hạ tầng mong muốn bằng mã nguồn và công cụ triển khai. Công cụ IaC so sánh cấu hình mong muốn với trạng thái mà provider quan sát được hoặc trạng thái được ghi trong state, rồi đề xuất hành động để đưa hệ thống về trạng thái phù hợp.

**Infrastructure drift** là sai lệch giữa cấu hình/ý định được quản lý và trạng thái thực tế của tài nguyên. Ví dụ:

- Engineer sửa ingress rule trực tiếp trên console để xử lý incident nhưng không cập nhật code.
- Administrator tăng database size hoặc đổi backup retention ngoài pipeline.
- Thao tác khẩn cấp thêm IAM permission rồi bị quên.
- Resource bị xóa thủ công nhưng IaC state vẫn ghi nó tồn tại.
- Một setting đổi do default của provider hoặc phiên bản API mới.
- Resource được tạo bằng script riêng, chưa có state owner.
- Provider hoặc controller thay đổi thuộc tính được công cụ quan sát sau khi reconcile.

Drift không chỉ là vấn đề thẩm mỹ. Nó làm cho lần deploy tiếp theo có thể ghi đè một hotfix cần thiết, xóa tài nguyên đang phục vụ production, hoặc giữ lại quyền quá rộng mà không ai biết. Nó cũng khiến staging/production khác nhau mà không có tài liệu giải thích.

### 1.1. Ba trạng thái cần phân biệt

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| **Desired configuration** | Cấu hình mục tiêu trong repository/module IaC | Firewall chỉ cho phép HTTPS từ gateway |
| **IaC state** | Bản ghi công cụ IaC dùng ánh xạ resource address với resource thật và thuộc tính theo dõi | Resource address ánh xạ tới ID do provider cấp |
| **Actual infrastructure** | Trạng thái provider đang áp dụng | Firewall hiện có thêm rule SSH từ Internet |

Trong Terraform, state là dữ liệu ánh xạ và metadata của resource, không phải bản sao hoàn chỉnh, bất biến của mọi thuộc tính cloud. Terraform refresh/plan đọc provider để so sánh; chi tiết phụ thuộc provider, resource schema, phiên bản và cấu hình.

### 1.2. Drift khác với code change và state change

- **Code change:** sửa HCL/YAML/JSON trong repository; đây là thay đổi mong muốn đã được ghi lại, nhưng chưa chắc đã triển khai.
- **State change:** state được cập nhật sau refresh/import/move/apply; không nhất thiết actual infrastructure đã đổi.
- **Infrastructure drift:** actual infrastructure đã thay đổi so với những gì IaC dự kiến hoặc ghi nhận.
- **Provider normalization/default:** provider trả giá trị đã chuẩn hóa hoặc mặc định; plan có thể hiển thị khác biệt dù không có thao tác thủ công rõ ràng.

Một plan có diff chưa chắc là drift do con người tạo. Cần hiểu computed/default attribute, eventual consistency, provider bug và cách API biểu diễn dữ liệu.

## 2. Nguyên nhân và mức độ ảnh hưởng

### 2.1. Nguồn gốc drift thường gặp

| Nguyên nhân | Ví dụ | Rủi ro |
|---|---|---|
| Thao tác console/CLI trực tiếp | Mở port, sửa route, tăng replica | Không được review, có thể bị ghi đè |
| Quy trình khẩn cấp | Hotfix firewall hoặc quota trong incident | Quên cập nhật mã nguồn sau phục hồi |
| Nhiều công cụ cùng quản lý | IaC và script tự động cùng sửa một resource | Các controller liên tục ghi đè nhau |
| Ownership không rõ | Hai module cùng khai báo một IAM role | Plan không ổn định, xung đột state |
| Provider/API thay đổi | Default hoặc output schema đổi sau upgrade | Diff không mong muốn, thay thế tài nguyên |
| Auto-scaling/controller | Provider tự đổi capacity hoặc replica count | IaC có thể kéo ngược giá trị động |
| Bootstrap thủ công | Resource được tạo trước IaC để chạy dự án | Không có state owner, dễ tạo duplicate |
| State bị lỗi/lệch | State cũ, mất lock, backend restore sai version | Công cụ có thể coi resource thật là resource mới |
| Quản trị nhiều môi trường | Console sửa production nhưng không cập nhật module | Dev/stage/prod dần khác nhau |

### 2.2. Drift ảnh hưởng nhiều trụ cột

- **Reliability:** route, subnet, database parameter, backup schedule hoặc autoscaling policy đổi ngoài kế hoạch.
- **Security:** security group mở rộng, IAM policy cấp thêm quyền, public endpoint được bật.
- **Cost:** database tier, NAT, storage retention hoặc log volume tăng không được theo dõi.
- **Operations:** responder không biết cấu hình thực tế khác code; rollback không tái tạo được môi trường.
- **Performance:** CPU/memory limit, cache size, connection pool hoặc autoscaling threshold lệch.
- **Compliance:** encryption, retention, region hoặc audit setting không còn đáp ứng chính sách.

Không phải mọi drift đều nghiêm trọng như nhau. Một tag mô tả hoặc thuộc tính do provider chuẩn hóa có thể ít ảnh hưởng hơn việc bỏ tắt encryption hay mở database ra Internet. Cần phân loại theo tác động thực tế, khả năng khai thác, blast radius và mức độ khẩn cấp.

## 3. Cách phát hiện drift

### 3.1. Vòng lặp detect–assess–reconcile

~~~mermaid
flowchart TD
    A[Desired config + IaC state] --> D[Refresh / Plan / Drift scan]
    B[Actual cloud resources] --> D
    D --> E{Difference found?}
    E -->|No| OK[Record clean result]
    E -->|Yes| F[Classify drift and impact]
    F --> G{Approved desired change?}
    G -->|No, accidental| R[Reconcile actual to code]
    G -->|Yes, retain| C[Update code to accepted reality]
    G -->|Unknown| I[Investigate owner / audit / incident]
    I --> F
    R --> V[Review plan and validate]
    C --> V
    V --> A
~~~

Drift scan chỉ phát hiện sai lệch; nó không tự quyết định cấu hình nào đúng. Hành động reconcile cần owner, review và hiểu tác động.

### 3.2. Terraform plan và refresh-only

Với Terraform, quy trình kiểm tra thường dùng:

~~~bash
# Xem thay đổi dự kiến sau khi refresh thông tin từ provider.
terraform plan

# Chỉ đề xuất cập nhật state theo trạng thái provider quan sát được.
terraform plan -refresh-only
~~~

Lệnh plan thường refresh thông tin resource được quản lý trước khi tạo kế hoạch thay đổi, tùy cấu hình và cờ sử dụng. Cờ refresh-only tạo plan nhằm cập nhật state/output theo actual infrastructure mà không đề xuất thay đổi remote object như plan apply thông thường. Hành vi chi tiết phụ thuộc phiên bản và provider.

Không dùng apply refresh-only như thao tác vô hại khi chưa review. Nó có thể ghi nhận actual state vào state và output, khiến drift trở thành trạng thái được Terraform ghi nhận; điều đó **không cập nhật desired configuration trong code**. Nếu drift là vi phạm policy, chỉ refresh state có thể làm mất tín hiệu sai lệch ở lần plan tiếp theo.

Ví dụ kiểm tra không áp dụng:

~~~bash
terraform init
terraform validate
terraform plan -refresh-only -out=drift-review.tfplan
terraform show drift-review.tfplan
~~~

Chạy trong đúng workspace/backend và phiên bản provider đã xác định. File plan có thể chứa thông tin nhạy cảm, cần lưu trữ và phân quyền phù hợp. Validate kiểm tra cú pháp/cấu trúc nhưng không tự chứng minh hạ tầng thực tế không drift.

### 3.3. Refresh-only, normal plan và apply khác nhau

| Lệnh/hoạt động | Mục đích | Có thay đổi hạ tầng từ plan không? |
|---|---|---|
| plan | So desired config với state/provider và đề xuất hành động | Không, chỉ lập kế hoạch |
| plan với refresh-only | Xem state/output cần cập nhật theo actual | Không |
| apply với refresh-only | Ghi nhận thay đổi được refresh vào state/output | Không chủ đích thay đổi remote resource, nhưng thay đổi state |
| apply thông thường | Thực hiện kế hoạch tạo/sửa/thay thế/xóa resource | Có thể |
| plan với refresh=false | Bỏ refresh provider trong lần plan theo hành vi phiên bản hỗ trợ | Không phát hiện drift mới từ provider trong lần chạy đó |

Refresh=false không phải cách kiểm tra drift; nó dùng trong một số tình huống cần tránh refresh, nhưng output có thể dựa trên state cũ. Phải hiểu trạng thái và mục đích trước khi dùng.

### 3.4. Phát hiện drift tự động

Tùy công cụ và cloud, có thể dùng:

- Lịch chạy plan/drift scan trong pipeline định kỳ.
- Config/asset inventory và policy evaluation từ cloud provider.
- Audit log để phát hiện thay đổi do principal, console hoặc automation thực hiện.
- Security posture/configuration management để tìm setting vi phạm baseline.
- Event notification khi resource bị sửa/xóa hoặc policy thay đổi.
- So sánh IaC repository, state inventory và cloud inventory.

Drift scan định kỳ không thay thế event-driven alert cho thay đổi nhạy cảm. Với IAM, public exposure, encryption và network boundary, nên có policy guardrail phát hiện gần thời gian thực nếu nền tảng hỗ trợ.

### 3.5. Hạn chế của drift detection

- Resource schema/provider có thể không expose mọi field.
- API có eventual consistency hoặc trả dữ liệu đã chuẩn hóa.
- Một số thuộc tính là computed/ephemeral hoặc do autoscaler điều khiển.
- Data source đọc thông tin không đồng nghĩa IaC sở hữu resource đó.
- Resource ngoài state sẽ không tự xuất hiện trong plan của state đó.
- Drift scan có thể bị giới hạn bởi API quota, quyền đọc hoặc backend lock.
- Provider upgrade có thể làm diff thay đổi dù actual không bị người vận hành sửa.

Vì vậy, báo cáo “no drift” chỉ có ý nghĩa trong phạm vi resource, field, provider, permission và state đã quét.

## 4. Đánh giá drift trước khi sửa

### 4.1. Bốn câu hỏi trước khi reconcile

1. **Actual đang khác ở đâu?** Xác định resource, thuộc tính, thời điểm và giá trị cũ/mới.
2. **Ai hoặc automation nào đã đổi?** Xem audit event, change ticket, deployment và incident timeline.
3. **Trạng thái nào đúng theo nghiệp vụ/chính sách?** Code có thể đã lỗi thời; actual có thể là hotfix được phê duyệt.
4. **Hành động nào an toàn?** Revert actual, cập nhật code, import resource, điều chỉnh ignore/lifecycle hay cần migration?

Không chạy apply chỉ vì plan đỏ. Trước tiên xác định replacement, destroy/create, force-new attribute, data loss, downtime và dependency graph.

### 4.2. Phân loại và quyết định

| Loại drift | Ví dụ | Cách xử lý điển hình |
|---|---|---|
| Unauthorized/unsafe | IAM mở quyền admin, DB public | Xử lý theo incident/policy; khôi phục baseline an toàn, ghi audit |
| Emergency hotfix còn cần | Tăng capacity để xử lý tải | Xác nhận owner, cập nhật code/module rồi plan |
| Desired change đã được duyệt | Thêm subnet/route theo change request | Cập nhật IaC, review và reconcile |
| Provider/computed difference | Trường output chuẩn hóa | Kiểm tra provider schema/version và diff semantics |
| Dynamic field do controller sở hữu | Replica count do autoscaler điều khiển | Chọn một source of truth; cấu hình ownership/ignore đúng scope |
| Unknown/unowned resource | Resource tạo từ console không rõ owner | Inventory, phân loại, tìm consumer và owner trước khi import/xóa |
| State mapping sai/mất | Resource thật tồn tại nhưng state không ghi nhận | Kiểm tra backend/workspace, backup state và import có kiểm soát |

### 4.3. Ignore changes không phải cách chữa mọi drift

Terraform hỗ trợ lifecycle ignore_changes cho những thuộc tính mà hệ thống bên ngoài có chủ đích điều khiển. Ví dụ:

~~~hcl
resource "example_service" "api" {
  name     = "booking-api"
  min_size = 2
  max_size = 20

  lifecycle {
    # Autoscaler là owner của desired capacity trong ví dụ này.
    ignore_changes = [desired_capacity]
  }
}
~~~

Chỉ dùng khi đã chỉ rõ controller nào sở hữu thuộc tính, cách giám sát giá trị, giới hạn min/max và cách khôi phục khi controller lỗi. Ignore quá rộng làm mất khả năng phát hiện drift; tránh ignore_changes = all như cách né plan khó hiểu.

### 4.4. Khôi phục về code hay chấp nhận actual?

**Reconcile actual về code** phù hợp khi thay đổi trái phép, không an toàn hoặc không được phê duyệt. Ví dụ rule mở SSH công khai phải được loại bỏ theo incident/security process.

**Cập nhật code để phản ánh actual** phù hợp khi thay đổi đã được phê duyệt và trở thành mục tiêu mới. Ví dụ database được tăng tier để đáp ứng tăng trưởng có chủ đích; cập nhật module và biến đầu vào trước khi pipeline quản lý tiếp.

Trong cả hai trường hợp, thay đổi phải qua review, plan, phê duyệt phù hợp và post-change validation. Đừng dùng state refresh đơn lẻ để che drift nếu source of truth trong code vẫn sai.

## 5. Tiếp nhận tài nguyên cloud đã tồn tại vào IaC

### 5.1. Vì sao cần import/adopt?

Nhiều hệ thống không bắt đầu từ IaC. Một tổ chức có thể đã có VPC/VNet, subnet, route table, security group, database production, bucket chứa tài liệu khách hàng, IAM role, KMS key, certificate, cluster, load balancer, DNS record hoặc queue được tạo thủ công.

Xóa rồi tạo lại thường không khả thi: có thể mất dữ liệu, đổi endpoint, gián đoạn dịch vụ, phá liên kết hoặc tạo chi phí lớn. **Import/adoption** đưa resource đang tồn tại vào phạm vi quản lý IaC bằng cách ánh xạ resource identity vào địa chỉ resource trong cấu hình/state.

Import không có nghĩa công cụ tự biết toàn bộ cấu hình đúng và sinh ra module hoàn chỉnh. Thường phải viết resource declaration, import ID, đọc thuộc tính thực, bổ sung module/variables và kiểm tra plan cho tới khi không có thay đổi ngoài dự kiến.

### 5.2. Import cần những gì?

Trước khi import, xác định:

- Provider, account/project/subscription và region chính xác.
- Resource ID duy nhất theo API/provider.
- Workspace/backend/state đang là owner dự kiến.
- Resource address trong code, có thể nằm trong module hoặc instance keyed.
- Những field bắt buộc và field có thể computed/default.
- Dependency và resource con được quản lý độc lập hay theo parent.
- Ai hiện sở hữu thay đổi và pipeline nào có thể ghi resource.
- Backup/export/rollback nếu import hoặc lần apply tiếp theo có vấn đề.

Import thường thay đổi state; một số workflow còn tạo file cấu hình hoặc plan. Cần làm ở branch/workspace được kiểm soát và backup state trước.

## 6. Quy trình adoption an toàn

### 6.1. Quy trình tổng thể

~~~mermaid
flowchart TD
    A[Inventory existing resource] --> B[Confirm owner, account, region and consumers]
    B --> C[Choose state boundary and resource address]
    C --> D[Back up state and lock change window]
    D --> E[Write matching IaC resource configuration]
    E --> F[Import resource identity into state]
    F --> G[Run refresh-only and normal plan]
    G --> H{Plan has unexpected actions?}
    H -->|Yes| I[Reconcile arguments, provider schema and dependencies]
    I --> G
    H -->|No, no-op or approved diff| J[Review and approve ownership]
    J --> K[CI/CD manages resource going forward]
~~~

Mục tiêu thường là đạt một plan không thay đổi remote resource sau import (no-op) trước khi pipeline quản lý thường xuyên. Có thể chấp nhận diff có chủ đích nhưng phải hiểu rõ thao tác, downtime và data impact.

### 6.2. Bước 1 — Inventory và xác nhận owner

Lập danh sách tài nguyên:

| Trường | Ví dụ |
|---|---|
| Resource | Production database instance |
| Provider identity | Account/project + region |
| Resource ID | ID lấy từ provider API |
| Current owner | Data Platform Team |
| Consumers | Booking API, reporting jobs |
| Data/risk | Customer data, backup enabled |
| Dependency | KMS key, subnet, security group |
| Change authority | Approved infrastructure pipeline |
| Import target | Resource address trong module data |
| Criticality | Tier 0 |

Không import resource chỉ vì tìm thấy nó trong account. Resource có thể thuộc dịch vụ khác, vendor, nền tảng do nhóm khác quản lý hoặc resource tạm thời. Phải có xác nhận owner và hợp đồng ownership trước khi thay đổi.

### 6.3. Bước 2 — Chọn state boundary

Một state nên có ranh giới trách nhiệm và blast radius hợp lý. Có thể chia theo environment, domain/service ownership, lifecycle/permission boundary, region/cell hoặc tần suất thay đổi.

Không gom mọi resource của công ty vào một state nếu điều đó khiến một lỗi plan/apply ảnh hưởng toàn bộ hệ thống hoặc cần cấp quyền quá rộng. Cũng không chia quá nhỏ đến mức dependency và output wiring trở nên khó vận hành.

### 6.4. Bước 3 — Khai báo resource trước khi import

Ví dụ Terraform minh họa:

~~~hcl
resource "aws_s3_bucket" "customer_documents" {
  bucket = "company-customer-documents-prod"

  # Các thuộc tính khác cần được khai báo theo
  # cấu hình hiện tại và policy đã phê duyệt.
}
~~~

Đây là ví dụ giả định dùng AWS provider; cấu hình thực tế cần theo đúng provider version và resource schema hiện tại. Resource block không đầy đủ có thể khiến plan đề xuất đổi thuộc tính hoặc tạo thêm resource liên quan. Với bucket, cần xem encryption, versioning, public access, lifecycle, ownership controls và policy.

### 6.5. Bước 4 — Import bằng CLI

Với workflow Terraform CLI truyền thống:

~~~bash
terraform import aws_s3_bucket.customer_documents company-customer-documents-prod
~~~

Lệnh này ánh xạ resource ID vào resource address trong state của workspace đang chọn. Nó không tự tạo đầy đủ resource configuration trong file .tf; người vận hành phải khai báo block tương ứng và xác minh plan.

Trước khi chạy:

- Kiểm tra workspace/backend tương ứng.
- Xác nhận provider alias, account và region.
- Backup state và bảo đảm backend locking hoạt động.
- Kiểm tra resource address chưa được state quản lý.
- Xác nhận ID chính xác và import syntax của provider.

Sau import:

~~~bash
terraform state show aws_s3_bucket.customer_documents
terraform plan -refresh-only
terraform plan
~~~

Lệnh state show giúp xem thuộc tính state đã ghi. Normal plan vẫn cần đọc kỹ vì field chưa khai báo, default, policy và resource phụ thuộc có thể tạo diff.

### 6.6. Bước 5 — Import bằng cấu hình khai báo

Các phiên bản Terraform hỗ trợ import block trong cấu hình, cho phép review import như một phần workflow plan/apply:

~~~hcl
import {
  to = aws_s3_bucket.customer_documents
  id = "company-customer-documents-prod"
}
~~~

Khai báo resource tương ứng và import block, sau đó chạy plan để xem Terraform sẽ import resource nào và có đề xuất thay đổi nào khác. Chỉ apply sau khi review. Cú pháp, hỗ trợ generate configuration và hành vi phụ thuộc phiên bản Terraform; kiểm tra tài liệu đúng version.

Import block có lợi cho workflow review/audit trong Git. Khi import hoàn tất, block có thể được giữ hoặc loại bỏ theo quy ước repository; ownership nằm ở state và resource configuration.

### 6.7. Bước 6 — Đạt trạng thái no-op có chủ đích

Sau import, plan có thể:

- **No changes:** cấu hình và actual đã khớp trong phạm vi provider quan sát.
- **In-place update:** một số thuộc tính cấu hình khác actual; cần xác định có chủ đích không.
- **Replace:** thuộc tính immutable/force-new khác; có thể tạo resource mới và destroy resource cũ.
- **Destroy:** resource trong state nhưng cấu hình bị xóa hoặc không còn khai báo.
- **Create:** resource block mới chưa được import đúng địa chỉ hoặc thiếu state mapping.

Với resource chứa dữ liệu production, không chấp nhận replace/destroy trong lần adoption nếu chưa có kế hoạch migration, backup, endpoint/cutover và approval rõ ràng. No-op là mục tiêu tốt cho bước đầu vì nó chứng minh IaC có thể quản lý resource mà không cần thay đổi actual.

## 7. Resource phụ thuộc và thứ tự import

### 7.1. Import theo dependency graph

~~~mermaid
flowchart TD
    VPC[VPC / VNet] --> SUB[Subnets]
    VPC --> RT[Route Tables]
    RT --> ASSOC[Route Associations]
    VPC --> SG[Security Groups]
    SUB --> DB[(Database)]
    SG --> DB
    KMS[KMS Key] --> DB
    KMS --> BK[Backup Vault]
    DB --> APP[Application Service]
    SUB --> APP
~~~

Thông thường cần import resource nền và network trước, sau đó resource phụ thuộc. Tuy nhiên, một số provider/resource có ID độc lập nên có thể import song song sau khi state boundary đã rõ. Không giả định mọi quan hệ API đều thể hiện bằng Terraform dependency; một reference chỉ là chuỗi ID chưa chắc tạo dependency graph.

### 7.2. Một resource có thể có nhiều tài nguyên con

Một parent cloud resource có thể quản lý inline nhiều thuộc tính hoặc child resource độc lập. Phải đọc mô hình provider:

- Child được quản lý inline trong parent hay bằng resource riêng?
- Có nguy cơ hai resource block cùng quản lý một cấu hình không?
- Import parent có lấy hết child state hay không?
- Khi plan, provider có coi child bị thiếu là cần xóa không?

Ví dụ route table có thể chứa inline routes hoặc route resources riêng tùy provider/version. Không khai báo đồng thời hai cách quản lý cùng một route nếu provider yêu cầu một owner duy nhất.

### 7.3. Import state không phải clone resource

Import không copy database, bucket hoặc network sang vùng mới. Nó chỉ liên kết resource address trong state với resource ID hiện tại. Nếu muốn tạo môi trường mới, cần module/configuration và thao tác apply phù hợp. Phân biệt import với:

- **Data source:** đọc thông tin resource mà state không sở hữu.
- **State move:** đổi địa chỉ resource trong state mà không import resource mới.
- **Resource replacement:** hủy resource cũ và tạo resource mới.
- **Migration:** di chuyển dữ liệu/workload sang resource đích.

## 8. Tiếp nhận resource có dữ liệu và rủi ro cao

### 8.1. Database production

Trước khi import database:

- Xác nhận provider ID, engine/version, parameter group, subnet group và security boundary.
- Ghi nhận backup/PITR, encryption/KMS, retention, replication và maintenance window.
- Kiểm tra field nào immutable/force-new.
- Không thay đổi identifier, storage encryption hoặc network access ngoài kế hoạch.
- Đối chiếu endpoint và connection string để tránh app bị trỏ nhầm.
- Có change window, state backup và kế hoạch rollback.

Import thành công không có nghĩa database được bảo vệ đầy đủ. Phải xác minh backup, restore, monitoring và IAM vẫn hoạt động.

### 8.2. IAM và security group

Import các resource bảo mật có thể phơi bày policy quá rộng hoặc diff gây khóa truy cập. Cần:

- Giữ ít nhất một đường quản trị/break-glass được kiểm chứng.
- So sánh policy document thực với code theo semantics, không chỉ format.
- Phân biệt policy do service owner quản lý với policy gắn từ platform/security.
- Không apply rule đóng cổng quản trị/endpoint đang cần cho migration.
- Kiểm tra principal đang dùng resource trước khi xóa statement hoặc attachment.
- Bật audit và có người review security changes độc lập.

### 8.3. Resource có state nội bộ hoặc dữ liệu ngoài

Queue, broker, secret, key, certificate, bucket và managed database có thể chứa state hoặc dữ liệu mà thao tác replace/delete ảnh hưởng trực tiếp. Một số resource có giá trị nhạy cảm hoặc không thể export lại:

- Secret plaintext có thể không được provider trả về sau khi tạo.
- Private key có thể không export được từ HSM/KMS.
- Certificate và DNS có thể liên kết với nhiều consumer.
- Queue có backlog; tạo lại queue có thể làm mất message.
- Bucket có version/object retention; destroy có thể bị chặn hoặc xóa dữ liệu.

Nếu provider không đọc lại được giá trị secret, không điền placeholder rồi apply khiến secret bị rotate ngoài kế hoạch. Dùng resource/data source và workflow secret manager phù hợp, tách metadata khỏi secret material.

## 9. Trường hợp import không khả dụng hoặc không phù hợp

### 9.1. Provider không hỗ trợ import

Nếu provider resource không hỗ trợ import, các lựa chọn:

- Dùng data source để tham chiếu resource bên ngoài mà không nhận quyền quản lý lifecycle.
- Dùng provider/API/CLI khác có khả năng adoption được hỗ trợ.
- Tạo lại resource mới nếu nghiệp vụ cho phép migration và downtime.
- Chờ hoặc đóng góp hỗ trợ vào provider, trong khi tiếp tục quản lý resource khác.
- Quản lý một phần bằng module wrapper nhưng xác định rõ ownership thủ công.

Không giả mạo state thủ công bằng cách sửa JSON state nếu công cụ/provider không hỗ trợ. State là dữ liệu quan trọng; thao tác thủ công có thể làm hỏng mapping, lineage và metadata. Chỉ dùng quy trình state manipulation được tài liệu hóa và backup.

### 9.2. Data source hay resource?

| Cách khai báo | Ownership | Phù hợp khi |
|---|---|---|
| Managed resource + import | IaC chịu trách nhiệm lifecycle/config theo schema provider | Nhóm muốn quản lý thay đổi của resource |
| Data source | IaC chỉ đọc metadata, không quản lifecycle | Resource do team/provider khác sở hữu |
| External reference/ID input | Consumer nhận ID từ contract bên ngoài | Ownership nằm ở platform hoặc account khác |

Không import mọi thứ vào một state chỉ vì có thể. Với shared DNS zone, central KMS key hoặc network nền do platform sở hữu, team ứng dụng có thể chỉ cần data source/reference và hợp đồng dependency.

### 9.3. Resource bị quản lý bởi công cụ khác

Nếu Kubernetes operator, autoscaler, policy controller hoặc cloud service tự điều khiển resource, xác định rõ field ownership:

- Tool nào là source of truth cho từng thuộc tính?
- Controller có ghi lại liên tục không?
- IaC quản lifecycle hay chỉ tạo bootstrap?
- Cần ignore_changes hay tách resource?
- Ai xử lý drift do controller?

Hai controller cùng ghi một field sẽ tạo vòng lặp reconcile, plan không ổn định và hành vi khó dự đoán.

## 10. Quản lý state an toàn trong quá trình adoption

### 10.1. State là tài sản nhạy cảm

State có thể chứa resource ID, endpoint, output và trong một số trường hợp giá trị nhạy cảm hoặc secret. Bảo vệ state bằng:

- Backend remote có encryption và access control.
- Versioning/backup và lịch sử thay đổi.
- Locking để tránh hai pipeline cùng ghi.
- Least privilege theo workspace/project/environment.
- Audit và kiểm soát ai đọc state.
- Không commit state hoặc plan có dữ liệu nhạy cảm vào Git.

Không lưu state local trên máy cá nhân rồi coi đó là state chuẩn. Trước adoption, xác định đúng backend/workspace; import vào sai workspace có thể tạo mapping sai hoặc dẫn tới resource duplicate khi pipeline khác chạy.

### 10.2. Backup state và recovery

Trước thay đổi state:

1. Dừng pipeline có thể đồng thời apply cùng state.
2. Xác nhận backend, workspace, lock và version.
3. Tạo/kiểm chứng state backup theo quy trình backend.
4. Ghi serial/lineage hoặc metadata state cần thiết theo công cụ.
5. Thực hiện import/move có review.
6. Xác minh state mapping và normal plan.
7. Mở lại pipeline sau khi owner xác nhận.

Restore state cũ có thể làm công cụ quên resource đã được import hoặc quay lại mapping trước đó trong khi actual không đổi. Khi khôi phục state, phải so sánh actual và plan trước mọi apply.

### 10.3. Không để nhiều state quản lý cùng một resource

Một cloud resource nên có một lifecycle owner trong một state, trừ khi công cụ có mô hình ownership/delegation được thiết kế rõ. Hai state cùng import một resource có thể cạnh tranh thay đổi và xóa. Lập inventory resource ID → state address để phát hiện duplicate ownership.

Nếu cần chuyển owner giữa state/module:

- Dùng workflow state move/remove/import hoặc cơ chế chính thức phù hợp phiên bản.
- Xác nhận source state không còn quản lý resource trước khi destination quản lý.
- Tránh cửa sổ hai pipeline cùng có quyền apply.
- Chạy plan ở cả hai state trước/sau.
- Không destroy resource trong bước chuyển ownership.

## 11. Quy trình xử lý drift trong vận hành

### 11.1. Severity và SLA xử lý

| Mức | Ví dụ | Phản ứng |
|---|---|---|
| Critical | Public database, tắt encryption, IAM admin ngoài ý muốn | Incident/security response ngay; cô lập hoặc khôi phục theo runbook |
| High | Backup retention giảm, route production sai, quota bị đổi gây outage risk | Owner xác nhận nhanh, change có kiểm soát |
| Medium | Capacity/parameter lệch, tag/monitoring thiếu, policy không theo baseline | Ticket có deadline và review |
| Low | Metadata/tag mô tả hoặc khác biệt không ảnh hưởng runtime | Batch cleanup/standardization |

Mức độ phụ thuộc risk policy và business impact. Không tự động revert mọi drift trước khi biết thay đổi có thể là mitigation hợp lệ trong incident đang diễn ra.

### 11.2. Drift register

Mỗi finding nên lưu:

| Trường | Mục đích |
|---|---|
| finding_id | Mã phát hiện |
| resource_id/address | Resource thật và địa chỉ IaC |
| attribute | Field bị lệch |
| desired/actual | Giá trị mục tiêu và thực tế đã giảm nhạy cảm |
| detected_at/source | Thời điểm và công cụ phát hiện |
| change_actor | Principal/audit event nếu xác định được |
| severity/impact | Mức độ và phạm vi ảnh hưởng |
| decision | Revert, accept/update code, ignore with owner, investigate |
| owner/due_date | Người/nhóm và deadline |
| validation | Plan, test, audit hoặc policy check sau xử lý |

Không đưa secret, token hoặc private value đầy đủ vào drift ticket. Chỉ ghi metadata cần thiết hoặc hash/redacted representation.

### 11.3. Quy trình reconcile

1. Xác nhận finding không phải false positive từ provider normalization hoặc dynamic field.
2. Xác định actor/change ticket và owner resource.
3. Đánh giá rủi ro, blast radius, downtime và data loss.
4. Quyết định source of truth là code hay actual.
5. Tạo change/incident record và branch cập nhật.
6. Chạy plan trong đúng environment, review destroy/replace/force-new.
7. Apply theo approval; có thể cần maintenance window hoặc staged rollout.
8. Kiểm tra actual, SLI, security policy và dependency.
9. Đóng finding với evidence và cập nhật runbook nếu cần.

### 11.4. Ngăn tái phát

- Hạn chế quyền sửa production console; dùng JIT/break-glass có audit.
- Áp dụng policy-as-code và guardrail ở organization/account.
- Tích hợp drift scan vào lịch định kỳ và cảnh báo event thay đổi nhạy cảm.
- Chuẩn hóa module/paved road để giảm nhu cầu thao tác ngoài IaC.
- Bắt buộc emergency change có follow-up code change và owner.
- Tách quyền read/plan/apply; production apply qua pipeline có review.
- Theo dõi drift recurrence theo team/resource type để xử lý nguyên nhân.

Mục tiêu không phải cấm tuyệt đối thao tác khẩn cấp qua console. Trong incident, hành động trực tiếp có thể giảm tác động nhanh nhất. Điều bắt buộc là ghi nhận, có người phê duyệt và đưa trạng thái đã chấp nhận trở lại source of truth sau đó.

## 12. Pipeline IaC cho drift và import

### 12.1. Pipeline kiểm tra định kỳ

~~~mermaid
flowchart LR
    SCHED[Scheduled trigger] --> INIT[Init pinned providers]
    INIT --> VAL[Validate + policy checks]
    VAL --> PLAN[Refresh-only / normal plan]
    PLAN --> REPORT[Store redacted report]
    REPORT --> GATE{Critical drift?}
    GATE -->|Yes| PAGE[Notify owner / incident policy]
    GATE -->|No| TICKET[Create or update drift finding]
    PAGE --> REG[Drift register]
    TICKET --> REG
    REG --> FIX[Reviewed reconciliation change]
~~~

Pipeline scan nên chỉ có quyền đọc cần thiết và quyền truy cập state phù hợp. Không để job drift scan tự apply thay đổi. Với production, tách plan và apply, bắt buộc review cho thay đổi rủi ro cao.

### 12.2. Pipeline tiếp nhận tài nguyên

~~~text
1. Resource owner requests adoption.
2. Verify account / region / resource ID / consumers.
3. Verify target backend, workspace and state lock.
4. Back up state and freeze conflicting automation.
5. Add resource declaration and import mapping in a branch.
6. Run validate and plan; inspect import and any diff.
7. Apply import only after approval.
8. Run refresh-only and normal plan again.
9. Require no-op or explicitly approved changes.
10. Merge and register the new IaC owner.
~~~

Đây là quy trình tham chiếu, không phải script chạy trực tiếp. Cú pháp, lệnh và hành vi import cần khớp phiên bản Terraform/provider và resource cụ thể.

### 12.3. Gate cần có

- Correct account/project, region và workspace.
- Resource ID chưa được state khác quản lý.
- State backup và lock đã sẵn sàng.
- Import address tồn tại trong code và không xung đột.
- Plan không có destroy/replace ngoài dự kiến.
- Có owner, change ticket và approval.
- Security policy, backup và monitoring được kiểm tra.
- Sau import, normal plan no-op hoặc diff còn lại được giải thích.

## 13. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Thấy diff là apply ngay | Có thể destroy/replace resource production | Phân loại diff và xem dependency/data impact |
| Chỉ chạy plan một state nhỏ | Không phát hiện resource ngoài state | Kết hợp inventory, audit và policy scan |
| Refresh state rồi coi drift đã hết | State nhận actual nhưng code vẫn sai | Cập nhật source of truth hoặc reconcile actual |
| Import rồi apply ngay | Config thiếu có thể sửa hoặc thay thế resource | Đạt no-op/approved plan trước |
| Import nhầm workspace/account | State quản lý resource sai scope | Xác minh backend, workspace, alias, region |
| Hai state cùng import một resource | Cạnh tranh thay đổi hoặc destroy | Một lifecycle owner, inventory mapping |
| Import resource không có owner | Tạo trách nhiệm mơ hồ | Xác nhận owner và consumer trước |
| Dùng ignore_changes quá rộng | Drift nghiêm trọng bị che | Ignore đúng field do controller sở hữu |
| Không backup state | Khó phục hồi mapping khi thao tác sai | Backup/lock/versioning trước thay đổi |
| Tự sửa JSON state | Hỏng lineage/schema hoặc mapping | Dùng lệnh state/import được hỗ trợ |
| Không đọc force-new/immutable field | Plan có thể thay resource gây downtime/data loss | Review replacement và migration plan |
| Quên policy/backup khi import DB/bucket | Resource được quản lý nhưng chưa an toàn | Security/backup acceptance criteria |
| Import resource đã bị tool khác quản lý | Hai controller ghi đè nhau | Làm rõ ownership và source of truth |
| Không có scan định kỳ | Drift tồn tại lâu, tích lũy | Scheduled scan, audit event và owner SLA |

## 14. Bài thực hành: tiếp nhận hạ tầng cloud đang chạy vào IaC

**Tình huống:** Một nền tảng đặt lịch đang chạy production trên cloud. VPC, subnet, security group, relational database, object storage và IAM role được tạo qua console trong giai đoạn đầu. Nhóm muốn chuẩn hóa bằng Terraform nhưng không thể tạo lại database hoặc bucket vì đang chứa dữ liệu thật. Một số thay đổi khẩn cấp từng được thực hiện trực tiếp và chưa ghi nhận.

Hãy lập kế hoạch adoption và drift management:

1. **Inventory:** liệt kê resource ID, account/region, owner, consumer, classification, dependency và criticality.
2. **State boundary:** chia state theo network, data và application/platform; giải thích quyền và blast radius của từng state.
3. **Drift discovery:** xác định cách dùng plan/refresh-only, cloud audit log, inventory và policy scan; phân biệt drift với computed/default fields.
4. **Classification:** phân loại public exposure, encryption, IAM, backup, capacity và tag drift theo severity.
5. **Import selection:** chọn resource có thể quản lifecycle; resource shared chỉ dùng data source/reference khi phù hợp.
6. **Terraform config:** viết resource block/import mapping cho một bucket hoặc security group test; ghép provider version và ID chính xác.
7. **State safety:** backup state, locking, workspace verification và kiểm tra resource duplicate ownership.
8. **No-op gate:** chạy refresh-only và normal plan; giải thích mọi in-place update, replace hoặc destroy.
9. **Reconciliation:** chọn drift cần revert, drift được chấp nhận và cập nhật code; có approval và evidence.
10. **Operations:** định nghĩa lịch scan, drift register, owner SLA, alert critical và follow-up sau emergency change.

### Bảng adoption mẫu

| Resource | Quyết định | Owner/state | Kiểm tra trước khi import |
|---|---|---|---|
| VPC và subnet | Managed resource nếu team network chuyển ownership | Network state / Platform | CIDR, peering, routes, endpoint |
| Security group | Managed resource | Network/app state theo boundary | Ingress/egress, active connections |
| Production DB | Import có kiểm soát | Data state / Data Platform | Backup, encryption, parameter, endpoint, force-new fields |
| Customer document bucket | Import có kiểm soát | Data state / Data Platform | Object/version, policy, lifecycle, encryption |
| Shared IAM role | Có thể chỉ reference nếu platform sở hữu | Platform state | Trust policy và consumer |

### Bảng drift register mẫu

| Finding | Actual khác desired | Mức | Quyết định | Owner/evidence |
|---|---|---|---|---|
| SG-01 | Có rule SSH từ Internet công khai | Critical | Xác minh incident rồi loại bỏ theo security process | Network owner, audit event |
| DB-02 | Backup retention thấp hơn baseline | High | Khôi phục policy sau khi kiểm tra business retention | Data owner, plan + backup check |
| APP-03 | Desired capacity tăng do autoscaler | Medium/expected | Xác định controller ownership, không ignore rộng | Service owner, autoscaler metric |
| BUCKET-04 | Tag cost-center thiếu | Low | Cập nhật code/tag theo change | Data owner, policy scan |

**Tiêu chí hoàn thành:** Người review hiểu resource nào đã được tiếp nhận, resource nào chỉ được tham chiếu, state nào sở hữu lifecycle, drift nào được sửa/giữ và vì sao. Plan không chứa destroy/replace ngoài phê duyệt; backup/state mapping, policy và hoạt động production được kiểm chứng.

## 15. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi về drift và resource adoption | Bằng chứng |
|---|---|---|
| **Operational Excellence** | Có inventory, owner, scan định kỳ, drift register và pipeline adoption? | Plan report, change log, no-op proof, runbook |
| **Security** | Drift IAM/network/encryption có được phát hiện và xử lý ưu tiên? | Policy scan, audit event, access review |
| **Reliability** | Adoption có tránh replace/downtime, state có backup/lock và resource có restore? | State backup, dependency plan, restore test |
| **Performance Efficiency** | Drift capacity/scale/network có làm thay đổi latency hoặc saturation? | Metrics trước/sau, load test, capacity review |
| **Cost Optimization** | Resource ngoài IaC/orphan/oversized có được nhận diện và owner? | Cloud inventory, cost tag, rightsizing review |
| **Sustainability** | Có dọn tài nguyên mồ côi và cấu hình dư thừa theo lifecycle? | Resource inventory, utilization và deletion approval |

IaC chỉ cải thiện vận hành khi tổ chức duy trì source of truth, quyền sở hữu và cách kiểm soát thay đổi. Import không phải chiến thắng nếu state đã có resource nhưng pipeline có thể xóa nó; drift scan không hữu ích nếu finding không có owner hoặc bị tự động ghi nhận mà không đánh giá tính đúng đắn.

## 16. Khung ghi nhớ

- **Drift** là sai lệch giữa cấu hình mong muốn, state và hạ tầng thực tế; cần phân biệt drift thật với provider default/computed và field do controller quản lý.
- **Phát hiện không đồng nghĩa sửa:** plan/scan tạo bằng chứng; owner đánh giá và chọn reconcile.
- **Refresh-only** cập nhật state theo actual; nó không tự sửa code và không chứng minh actual an toàn.
- **Import/adoption** ánh xạ resource đang tồn tại vào địa chỉ IaC/state; không tạo bản sao và không tự sinh cấu hình hoàn chỉnh.
- **State boundary và một lifecycle owner** ngăn nhiều pipeline/state cùng quản lý một resource.
- **No-op plan hoặc diff được phê duyệt** là cổng quan trọng trước khi giao resource cho pipeline quản lý thường xuyên.
- **Resource có dữ liệu, key, IAM và network** cần review đặc biệt vì replacement hoặc policy change có thể gây mất dữ liệu/gián đoạn.
- **Drift register, audit, scan định kỳ và follow-up sau emergency change** giữ cho code và actual không lệch dần theo thời gian.

Phát hiện drift và tiếp nhận tài nguyên đã tồn tại là hai mặt của cùng một bài toán ownership: tổ chức phải biết tài nguyên nào đang chạy, ai chịu trách nhiệm và cấu hình nào là nguồn chuẩn. Khi inventory, state, code và quy trình thay đổi được kết nối, IaC có thể tiếp quản hạ tầng đang hoạt động an toàn, đồng thời giúp những sai lệch mới được phát hiện, đánh giá và xử lý trước khi trở thành sự cố.
