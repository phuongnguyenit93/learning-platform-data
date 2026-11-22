# Quản lý state, khóa đồng thời và phục hồi state

Infrastructure as Code (IaC) mô tả hạ tầng mong muốn bằng mã và công cụ sẽ so sánh mô tả đó với tài nguyên thực tế để tạo kế hoạch thay đổi. Để biết một resource trong cấu hình tương ứng với resource nào đang tồn tại, công cụ cần giữ metadata về lần triển khai trước. Với Terraform/OpenTofu, metadata này được lưu trong **state**.

State thường chứa mapping giữa địa chỉ resource trong cấu hình và định danh resource thực tế, cùng các thuộc tính mà provider đã đọc được. Nó giúp công cụ xác định resource nào cần tạo, cập nhật, thay thế hoặc xóa. Vì vậy, state là một phần quan trọng của hệ thống quản lý hạ tầng. Nếu nhiều người cùng ghi state, state bị mất, bị ghi đè bằng phiên bản cũ hoặc bị lộ, hậu quả có thể ảnh hưởng trực tiếp tới production.

Bài học này thuộc chương **Hạ tầng dưới dạng mã** của module **CLOUD_ARCHITECTURE**. Mục tiêu là thiết kế cách lưu trữ và bảo vệ state, kiểm soát concurrent runs, xử lý drift, backup và khôi phục state; đồng thời hiểu các đánh đổi về độ tin cậy, bảo mật, chi phí và vận hành trong quy trình IaC.

## 1. State là gì và vì sao cần quản lý?

State là dữ liệu quản lý mà IaC engine dùng để ghi nhớ các resource đã được quản lý và liên kết chúng với tài nguyên thực tế. State không phải cấu hình mong muốn và cũng không phải bản backup đầy đủ của cloud account.

Ví dụ cấu hình khai báo một bucket tên logical là uploads. Khi apply thành công, provider tạo bucket có resource ID cụ thể. State ghi lại liên kết từ địa chỉ resource trong module tới ID và metadata của bucket đó.

~~~mermaid
flowchart LR
    CFG["IaC configuration"] --> PLAN["Plan engine"]
    ST[("State snapshot")] --> PLAN
    LIVE["Real cloud resources"] --> REFRESH["Provider refresh / read"]
    REFRESH --> PLAN
    PLAN --> DIFF["Proposed changes"]
    DIFF --> APPLY["Apply"]
    APPLY --> LIVE
    APPLY --> ST
~~~

Không có state phù hợp, engine khó biết resource nào đang được quản lý, resource thực tế có ID gì hoặc một cấu hình mới là resource mới hay muốn quản lý resource cũ.

### 1.1. State giải quyết những việc gì?

- **Resource mapping:** liên kết địa chỉ resource trong cấu hình với ID ở provider.
- **Dependency metadata:** hỗ trợ xác định quan hệ và thứ tự thao tác giữa resource.
- **Attribute tracking:** lưu các thuộc tính đã biết để tính toán thay đổi.
- **Module/resource addressing:** lưu thông tin instance, module path, index hoặc key.
- **Provider association:** giữ thông tin provider/configuration được dùng để quản lý resource.
- **Outputs:** lưu kết quả đầu ra để module hoặc workflow khác có thể tham chiếu.
- **Sensitive values:** trong nhiều trường hợp có thể chứa giá trị nhạy cảm, kể cả khi output được đánh dấu sensitive.

State không phải nơi thay thế source code, variable file, secret manager, cloud inventory hay backup database. Hãy xem state là metadata có tính vận hành và bảo mật cao.

### 1.2. State không phải nguồn chân lý duy nhất

Có ba góc nhìn cần so sánh:
1. **Configuration:** điều nhóm muốn hệ thống có.
2. **State:** điều IaC engine đang ghi nhận thuộc phạm vi quản lý.
3. **Real infrastructure:** điều provider đang có ở thời điểm hiện tại.

Ba góc nhìn có thể lệch nhau. Một admin có thể thay đổi console trực tiếp; state vẫn ghi cấu hình cũ. Một state restore có thể tham chiếu resource đã bị xóa. Một config mới có thể không còn chứa resource đang được state quản lý.

Do đó, state phải được kiểm tra cùng provider inventory, plan, refresh và quy trình change control. Không chỉnh state chỉ để làm cho plan trông sạch nếu chưa hiểu tài nguyên thực tế.

## 2. Cấu trúc địa chỉ resource và mapping

Trong Terraform/OpenTofu, state tham chiếu địa chỉ resource như module path, resource type/name và instance key/index.

Ví dụ minh họa:

~~~hcl
resource "aws_s3_bucket" "uploads" {
  bucket = "booking-uploads-prod"
}

module "network" {
  source = "./modules/network"
}
~~~

Các địa chỉ có thể có dạng:
- aws_s3_bucket.uploads
- module.network.aws_vpc.main
- aws_instance.worker[0]
- aws_instance.worker["batch-a"]

Tên địa chỉ trong cấu hình là định danh logic. Provider resource ID là định danh tài nguyên thực tế. Hai thứ này không giống nhau.

### 2.1. Đổi tên resource không nhất thiết phải tạo lại resource

Nếu đổi địa chỉ trong cấu hình mà không khai báo cho engine biết đó là cùng resource, plan có thể đề xuất destroy địa chỉ cũ rồi create địa chỉ mới. Đối với resource quan trọng, hành vi này có thể gây downtime hoặc mất dữ liệu.

Cần dùng cơ chế refactor address phù hợp với phiên bản công cụ, ví dụ moved block hoặc lệnh state mv theo workflow đã kiểm chứng. Sau thay đổi, review plan để xác nhận engine hiểu đây là chuyển mapping chứ không phải thay thế resource.

### 2.2. Một state hay nhiều state?

Một state lớn quản lý nhiều thành phần tạo ra blast radius lớn và nhiều nhóm phải chia sẻ lock. Nhiều state nhỏ giúp giảm phạm vi thay đổi và ownership, nhưng tăng công sức quản lý dependency và phối hợp.

| Cách tổ chức | Ưu điểm | Rủi ro |
|---|---|---|
| Một state cho toàn môi trường | Dependency trong cùng state dễ biểu diễn | Lock contention, plan lớn, blast radius và quyền rộng |
| State theo domain/workload | Ownership và thay đổi tập trung hơn | Cần quản lý output/remote dependency |
| State theo environment | Cô lập dev/stage/prod | Phải giữ cấu hình và version nhất quán |
| State theo region | Hỗ trợ ownership và failure domain theo region | Cần điều phối resource global và shared service |
| State theo team | Tách quyền và vòng đời vận hành | Có thể chia cắt một dependency logic thành nhiều state |

Không nên chia state chỉ theo số lượng resource. Chọn boundary dựa trên ownership, lifecycle, quyền truy cập, tốc độ thay đổi, dependency và blast radius.

## 3. Local state và remote state

### 3.1. Local state

Mặc định hoặc trong môi trường đơn giản, state có thể được lưu trong file cục bộ trong working directory.

Ưu điểm:
- Dễ bắt đầu và thử nghiệm.
- Không cần backend service riêng.
- Phù hợp bài lab cá nhân hoặc môi trường throwaway.

Hạn chế:
- Không chia sẻ an toàn giữa nhiều người/máy.
- Dễ bị mất khi laptop hỏng hoặc workspace bị xóa.
- Không có locking tập trung nếu workflow không bổ sung cơ chế khác.
- Dễ commit nhầm vào Git.
- Khó audit và áp dụng backup/retention chuẩn.

Không dùng local state làm phương án mặc định cho production team workflow. Không commit state vào repository để thay thế remote backend; state có thể chứa secret và metadata nhạy cảm.

### 3.2. Remote state

Remote backend lưu state ở dịch vụ dùng chung có thể kiểm soát quyền, versioning, encryption, logging và locking theo khả năng hỗ trợ của backend/công cụ.

Ví dụ các lựa chọn thường gặp:
- Object storage có versioning và cơ chế locking được backend hỗ trợ.
- Terraform Cloud/HCP Terraform hoặc nền tảng quản lý state tương ứng.
- Backend HTTP hoặc dịch vụ state chuyên dụng.
- Các backend cloud-native khác theo phiên bản engine và provider.

Lợi ích:
- Một bản state được chia sẻ có kiểm soát giữa các runner.
- Có thể hỗ trợ locking và concurrency control.
- Có thể dùng IAM/workload identity để kiểm soát truy cập.
- Có thể tích hợp encryption, audit log, versioning và backup.
- Giảm rủi ro state chỉ nằm trên máy của một cá nhân.

Remote backend vẫn cần thiết kế. Object storage đơn lẻ không đồng nghĩa có lock an toàn; versioning không ngăn hai writer ghi đè đồng thời; encryption không thay thế authorization.

### 3.3. Kiến trúc remote state điển hình

~~~mermaid
flowchart TB
    DEV["Developer / CI runner"] --> AUTH["Workload identity / IAM"]
    AUTH --> LOCK["Backend lock"]
    LOCK --> STORE[("Remote state storage")]
    STORE --> VER[("Version history / backup")]
    DEV --> CLOUD["Cloud provider APIs"]
    CLOUD --> LIVE["Managed resources"]
    STORE -. "State metadata" .-> DEV
~~~

Runner cần xác thực với backend, lấy lock, đọc state, thực hiện refresh/plan/apply và ghi snapshot mới khi thao tác hoàn tất theo semantics của backend. Quyền backend và quyền provider là hai phạm vi khác nhau; cần kiểm soát cả hai.

## 4. Backend, workspace và environment isolation

Không nên nhầm workspace với một security boundary hoàn chỉnh. Terraform workspaces có thể tạo nhiều state instance cho cùng một cấu hình và backend, nhưng quyền truy cập backend, credentials, network và policy vẫn quyết định ai có thể đọc/ghi.

Các môi trường production thường nên có isolation rõ:
- Backend hoặc namespace riêng theo environment.
- IAM role riêng cho dev/stage/prod.
- State key/prefix riêng, naming rõ và không chồng lấn.
- Pipeline production có approval và protected branch.
- Secret và provider credentials không chia sẻ tùy tiện.
- Policy ngăn runner non-prod ghi state prod.

Một workspace label tên prod không tự tạo quyền bảo vệ production. Nếu cùng một credential có quyền ghi mọi state, isolation theo tên không đủ.

### 4.1. Quy tắc chọn state boundary

Hãy hỏi:
- Ai là owner của resource?
- Những resource nào cần thay đổi cùng một lần?
- Có yêu cầu atomicity giữa các resource không?
- State có chứa dữ liệu nhạy cảm khác nhau không?
- Nhóm nào cần quyền read/write?
- Một lần apply lỗi có thể ảnh hưởng tới bao nhiêu workload?
- State có cần được phục hồi độc lập không?
- Dependency có thể truyền qua output/API thay vì cùng state không?

Tách state thường tăng độc lập nhưng làm mất atomic plan giữa các state. Quy trình pipeline phải định nghĩa thứ tự apply và điều kiện tương thích giữa producer/consumer.

## 5. Khóa state và concurrent runs

Khi hai runner cùng đọc một state version rồi cùng apply, cả hai có thể tính plan dựa trên cùng snapshot cũ. Kết quả ghi có thể ghi đè hoặc làm mất cập nhật của runner còn lại.

**State locking** ngăn nhiều operation ghi state cùng lúc trong backend/cơ chế hỗ trợ. Khi một operation lấy lock, operation khác cần chờ hoặc thất bại có kiểm soát.

~~~mermaid
sequenceDiagram
    participant R1 as Runner A
    participant L as Lock service
    participant S as Remote state
    participant R2 as Runner B
    R1->>L: Acquire lock
    L-->>R1: Lock granted
    R1->>S: Read state version N
    R2->>L: Acquire lock
    L-->>R2: Lock held / wait
    R1->>S: Write state version N+1
    R1->>L: Release lock
    R2->>L: Acquire lock
    L-->>R2: Lock granted
    R2->>S: Read latest state N+1
~~~

Locking không biến mọi thao tác cloud thành transaction nguyên tử. Provider API có thể đã tạo resource trước khi runner gặp lỗi; state write có thể chưa hoàn tất; external admin vẫn có thể thay đổi tài nguyên. Lock bảo vệ concurrency trên state backend trong phạm vi được hỗ trợ.

### 5.1. Lock lifecycle

Một quy trình chuẩn:
1. Runner xác thực backend.
2. Yêu cầu acquire lock.
3. Nếu lock đang giữ, chờ trong giới hạn hoặc dừng với thông tin rõ.
4. Đọc state sau khi có lock.
5. Thực hiện operation theo policy.
6. Ghi state khi operation kết thúc theo semantics công cụ.
7. Release lock.
8. Nếu runner crash, xử lý stale lock theo quy trình được hỗ trợ.

Không xóa lock chỉ vì pipeline đang chờ lâu. Trước khi force-unlock cần xác nhận operation cũ thật sự đã dừng và không còn process/provider operation đang chạy.

### 5.2. Lock ID và force-unlock

Công cụ thường cung cấp lock ID hoặc thông tin owner để chẩn đoán. Khi cần force-unlock:
- Xác định đúng backend và workspace/state.
- Xác minh runner giữ lock đã kết thúc hoặc bị terminate.
- Kiểm tra job/operation phía provider không còn chạy.
- Ghi change/incident ID và người phê duyệt.
- Chỉ sử dụng đúng lock ID của lock bị kẹt.
- Sau unlock, đọc lại state và chạy refresh/plan.
- Không chạy đồng thời một apply khác trong thời gian xác minh.

Force-unlock sai có thể cho phép hai operation ghi state cùng lúc, làm tình hình tệ hơn.

### 5.3. Lock timeout và pipeline queue

Đặt lock timeout dựa trên thời gian operation dự kiến, nhưng giới hạn phải đủ để tránh runner chờ vô hạn. CI/CD có thể serialize apply theo state key hoặc queue job cùng environment. Plan có thể chạy song song trong một số workflow, nhưng apply và bất kỳ operation ghi state nào cần tuân thủ locking semantics.

Một quy tắc hữu ích là tổ chức concurrency theo state boundary:
- Apply cùng một state: tuần tự.
- Apply các state độc lập: có thể chạy song song nếu dependency cho phép.
- Apply producer và consumer state: theo thứ tự tương thích.
- Drift remediation và release apply: không chạy đồng thời trên cùng state.

## 6. Locking không thay thế change coordination

State lock chỉ bảo vệ thao tác của những client dùng cùng lock mechanism. Nó không ngăn:
- Admin thay đổi resource trực tiếp trên console.
- Một pipeline khác dùng backend/key khác.
- Script gọi provider API ngoài IaC.
- Một runner bỏ qua backend lock.
- Hai state khác nhau quản lý cùng một resource.

Do đó cần thêm:
- Quyền cloud hạn chế thay đổi ngoài pipeline.
- Quy trình change management cho production.
- Inventory mapping để tránh hai state cùng quản lý một resource.
- Audit log của provider.
- Policy kiểm tra trước apply.
- Runbook xử lý manual change và drift.
- Ownership rõ cho từng resource domain.

Không đưa cùng một resource vào hai state khác nhau rồi kỳ vọng lock của mỗi state phối hợp được với nhau. Mỗi resource nên có một owner IaC rõ ràng.

## 7. State và dữ liệu nhạy cảm

State có thể lưu các giá trị mà cấu hình đánh dấu sensitive, output nhạy cảm, endpoint nội bộ, resource metadata và đôi khi thông tin credential được provider trả về. Việc ẩn một output khỏi terminal không chứng minh giá trị đó không tồn tại trong state.

### 7.1. Các biện pháp bảo vệ

- Encryption at rest bằng backend/provider và key policy phù hợp.
- TLS/encryption in transit.
- Least privilege: chỉ runner và operator cần thiết được read/write.
- Tách read và write role nếu nền tảng hỗ trợ.
- Không chia sẻ state qua email, chat hoặc artifact công khai.
- Không commit state, backup hoặc plan file nhạy cảm vào Git.
- Redact log và CI output; tránh dump state trong job log.
- Bảo vệ local cache, workspace và runner ephemeral storage.
- Audit mọi lần read/write/delete/version restore nếu backend hỗ trợ.
- Có retention, deletion và access review.
- Xác minh state backup cũng được mã hóa và giới hạn quyền như state chính.

### 7.2. Plan file cũng có thể nhạy cảm

Saved plan có thể chứa thông tin về giá trị và thay đổi dự kiến, kể cả giá trị sensitive. Cần bảo vệ plan artifact:
- Chỉ lưu trong artifact store riêng.
- Giới hạn thời gian tồn tại.
- Không cho người không có quyền apply tải xuống.
- Không dùng plan cũ sau khi state/config thay đổi.
- Re-plan khi plan đã stale hoặc state serial/lineage không khớp.

State và plan cần được coi là dữ liệu production có kiểm soát.

## 8. Versioning, backup và recovery

Remote backend có thể hỗ trợ version history, nhưng versioning không phải backup strategy hoàn chỉnh. Nếu credential bị compromise, attacker có thể xóa state và version history nếu cùng có quyền. Nếu retention lifecycle cấu hình sai, version cũ có thể bị xóa trước khi cần.

Một chiến lược phục hồi cần:
- Versioning hoặc snapshot theo backend.
- Backup độc lập account/project hoặc trust boundary.
- Encryption key có thể truy cập trong DR.
- Retention đã phê duyệt.
- Kiểm tra backup integrity.
- Restore drill định kỳ.
- Inventory state key/workspace và dependency.
- Quy trình chọn đúng recovery point.

### 8.1. State version, serial và lineage

Terraform state có metadata như lineage và serial trong format state. Lineage định danh lịch sử state; serial giúp nhận biết phiên bản snapshot theo cơ chế công cụ. Khi thao tác state thủ công, không tự sửa các trường này để ép engine chấp nhận snapshot.

Engine/backend có thể từ chối ghi một state cũ hơn hoặc state thuộc lineage khác để tránh rollback ngoài ý muốn. Hãy dùng cơ chế backup/restore hoặc state push được hỗ trợ và làm theo thông báo của phiên bản công cụ đang dùng.

### 8.2. Quy trình backup

Có thể định nghĩa:
- Snapshot trước mỗi production apply quan trọng.
- Versioning liên tục tại backend.
- Backup định kỳ sang vùng/account tách biệt.
- Backup trước state migration, import, mv, rm hoặc thao tác state surgery.
- Ghi metadata: state key, environment, workspace, thời gian, commit SHA và change ID.
- Mã hóa và kiểm soát quyền cho bản backup.
- Kiểm tra restore trên môi trường cô lập.

Không lưu một bản backup duy nhất ngay trong cùng bucket/prefix với quyền xóa rộng như state chính rồi coi đó là DR.

## 9. Phục hồi state bị mất hoặc hỏng

Khi state mất hoặc không parse được, dừng mọi pipeline apply liên quan. Không chạy apply mù vì engine có thể nghĩ toàn bộ resource chưa tồn tại và đề xuất tạo trùng hoặc thay thế.

### 9.1. Thứ tự phục hồi an toàn

1. Đóng băng apply và thay đổi thủ công liên quan.
2. Xác định backend, state key, workspace, environment và owner chính xác.
3. Kiểm tra trạng thái backend/version history và audit log.
4. Tìm snapshot/backup hợp lệ gần nhất.
5. Xác minh lineage, serial, timestamp, source commit và environment.
6. Restore vào location hoặc bản sao cô lập trước nếu có thể.
7. Kiểm tra format, checksum và khả năng đọc bằng đúng phiên bản engine tương thích.
8. So sánh resource mapping với provider inventory.
9. Refresh/plan trong chế độ không apply để xác định drift.
10. Review từng thay đổi được đề xuất, nhất là destroy/replace.
11. Chỉ mở lại pipeline sau khi owner phê duyệt và có backup hiện tại.

Nếu backend có version restore, phải xác minh operation có tạo version mới hay ghi đè object theo cách nào. Giữ lại snapshot trước restore để có thể điều tra hoặc quay lại.

### 9.2. State cũ có thể nguy hiểm

State cũ có thể bỏ qua resource mới được tạo trong DR hoặc resource đã được thay thế. Khi plan với snapshot cũ, engine có thể đề xuất tạo trùng, xóa nhầm hoặc thay resource đang phục vụ production.

Không chọn snapshot chỉ vì nó là bản mới nhất theo thời gian file. Chọn bản phù hợp với lineage, apply history, commit/deployment timeline và trạng thái provider. Có thể cần import hoặc reconcile thay vì restore một snapshot cũ.

### 9.3. Khôi phục khi không còn backup

Nếu không có state backup:
- Dừng mọi thao tác ghi hạ tầng bằng IaC.
- Thu thập provider inventory và audit/change history.
- Xác định resource thuộc scope dự án.
- Tạo lại state có kiểm soát bằng import hoặc workflow tương ứng.
- Chia nhỏ theo domain/resource group.
- Plan và review từng resource.
- Không apply plan có hàng loạt create/destroy chưa được giải thích.

Import không tự tạo cấu hình đầy đủ hoặc chứng minh resource phù hợp với desired state. Sau import cần viết/đối chiếu config, refresh và review plan cẩn thận.

## 10. Drift và refresh

**Configuration drift** là khác biệt giữa desired configuration và real infrastructure. Drift có thể do console change, script ngoài IaC, provider default, external controller hoặc một thao tác apply chưa hoàn tất.

State có thể giúp phát hiện drift qua refresh/plan. Cần phân biệt:
- Resource thực tế thay đổi so với state.
- Config thay đổi so với state.
- Provider/API thay đổi default hoặc schema.
- Một resource được quản lý bởi controller khác.
- Một data source được đọc lại nhưng không phải resource do IaC quản lý.

### 10.1. Drift detection

Quy trình:
1. Chạy plan/refresh ở chế độ an toàn theo phiên bản và workflow.
2. Xem resource nào khác biệt.
3. Xác định actor/time qua audit log.
4. Phân loại manual change hợp lệ, emergency change hay unauthorized change.
5. Quyết định đưa thay đổi vào code, revert real resource hay import/reconcile.
6. Chạy plan lại và lưu approval/change record.

Không tự động apply mọi drift. Một thay đổi trực tiếp có thể là emergency fix cần được đưa vào code trước. Apply code cũ ngay có thể xóa hotfix production.

### 10.2. Drift không phải lúc nào cũng là lỗi

Một số thuộc tính thay đổi tự nhiên hoặc do provider quản lý, ví dụ timestamp, generated identifier, autoscaling count hoặc metadata không cần kiểm soát. Cần hiểu schema/provider behavior và dùng lifecycle ignore/change policy chỉ khi có lý do rõ. Ignore quá rộng có thể che giấu thay đổi bảo mật hoặc cấu hình ngoài ý muốn.

## 11. State migration và backend migration

Có thể cần chuyển state từ local sang remote, đổi bucket/key, đổi workspace hoặc chuyển nền tảng quản lý state.

Quy trình migration nên:
1. Dừng apply ở backend cũ.
2. Xác định chính xác state/workspace đang được dùng.
3. Backup state và kiểm tra backup.
4. Cấu hình backend mới và quyền truy cập.
5. Chạy migration bằng cơ chế chính thức của engine.
6. Xác minh state mới cùng lineage/resource mapping.
7. Chạy plan không apply và so sánh kết quả.
8. Cô lập bản cũ để tránh có runner ghi nhầm.
9. Cập nhật pipeline, documentation và ownership.
10. Theo dõi lần apply đầu tiên qua change review nghiêm ngặt.

Không copy file state đang được sử dụng trong lúc apply. Cần lock/maintenance window để tránh snapshot không nhất quán hoặc hai backend cùng trở thành nơi ghi chính.

### 11.1. Tránh dual-primary state

Sau migration, chỉ một backend được coi là authoritative. Nếu backend cũ vẫn cho runner ghi, hai state có thể phân kỳ. Hãy thu hồi quyền ghi hoặc đánh dấu backend cũ read-only/archive sau khi migration được xác minh.

## 12. State operations: mv, rm, import và push

State command có thể tác động trực tiếp tới mapping. Chúng không thay thế thao tác provider API theo nghĩa thông thường nhưng có thể làm engine ngừng quản lý, quản lý nhầm hoặc khôi phục một snapshot khác.

| Thao tác | Mục đích | Rủi ro |
|---|---|---|
| State mv | Chuyển địa chỉ mapping | Sai destination hoặc nhầm workspace |
| State rm | Bỏ resource khỏi state | Resource vẫn tồn tại nhưng IaC không còn quản lý |
| Import | Thêm resource thực tế vào state | Sai ID, duplicate ownership hoặc config lệch |
| State push | Ghi snapshot state vào backend | Ghi đè snapshot hiện tại nếu sai |
| Force-unlock | Gỡ lock bị kẹt | Concurrent writer nếu lock cũ còn hoạt động |
| Refresh/plan | Đối chiếu state với provider | Provider read có thể có side effect/giới hạn theo tool, và plan không phải backup |

### 12.1. Quy tắc trước mọi state surgery

- Xác minh environment/workspace/backend/state key.
- Chụp backup và kiểm tra có thể đọc.
- Ghi change ID và mục đích.
- Đảm bảo không có apply khác đang chạy.
- Dùng đúng resource address và resource ID.
- Preview hoặc dùng command có chế độ kiểm tra nếu hỗ trợ.
- Review output trước khi xác nhận.
- Chạy plan sau thay đổi để kiểm tra hệ quả.
- Lưu audit trail và owner.
- Có recovery path nếu mapping sai.

Không sửa JSON state bằng text editor như một giải pháp thông thường. State format là dữ liệu do công cụ quản lý; thay đổi trực tiếp có thể làm hỏng metadata hoặc tạo snapshot không hợp lệ. Chỉ thực hiện surgery khi tài liệu engine yêu cầu và có quy trình được review.

## 13. CI/CD và concurrency governance

Trong tổ chức, state thường được dùng bởi developer, platform team và nhiều pipeline. Cần một chính sách thống nhất.

### 13.1. Pipeline apply

Một pipeline production có thể gồm:
- Validate và format.
- Static/security/policy checks.
- Init đúng backend/workspace.
- Plan với version tool/provider được pin.
- Publish plan artifact được bảo vệ.
- Approval theo environment.
- Xác minh plan chưa stale.
- Apply với lock.
- Lưu result, state metadata và change ID.
- Post-apply verification.

Approval không nên kéo dài đến mức plan đã cũ. Nếu state thay đổi sau plan, tạo plan mới thay vì apply artifact cũ mù quáng.

### 13.2. Serialize theo state key

Ví dụ:
- pipeline prod/network và prod/app dùng cùng một state: phải serialize.
- pipeline dev và prod dùng state/backend identity riêng: có thể chạy song song.
- hai module tách state nhưng cùng thay đổi một shared resource: cần ownership/process chung vì lock riêng không phối hợp.

Dùng CI/CD concurrency group theo environment/state key nếu nền tảng hỗ trợ. Backend lock vẫn là lớp bảo vệ bổ sung, không phải lý do bỏ queue hoặc ownership policy.

### 13.3. Pin tool và provider versions

Version upgrade có thể thay đổi state schema, provider behavior hoặc plan semantics. Trước upgrade:
- Đọc release note và migration guide.
- Pin phiên bản Terraform/OpenTofu và provider.
- Backup state.
- Thử trên non-production.
- Kiểm tra plan và state format compatibility.
- Có phương án downgrade/restore phù hợp; không giả định binary cũ đọc được state đã nâng cấp.

## 14. State trong môi trường đa vùng và DR

State cũng cần có khả năng phục hồi nếu backend/region gặp sự cố. Nhưng không nên tạo nhiều bản state active đồng thời để “dự phòng”.

Cần xác định:
- Backend chính nằm ở failure domain nào?
- Có versioning/replication/backup sang region khác không?
- Khi failover, region DR dùng cùng state backend hay snapshot đã restore?
- Làm sao bảo đảm chỉ một nơi có quyền apply?
- State restore có khớp với resource hiện tại sau sự cố không?
- Credential, KMS và lock service có sẵn ở DR không?
- Pipeline có thể chạy khi source control/registry/CI chính lỗi không?

Trong DR, có thể khôi phục state snapshot ở region khác nhưng phải fence backend cũ hoặc loại bỏ quyền ghi trước khi mở pipeline mới. Hai backend cùng cho ghi có thể tạo split-brain ở lớp quản lý hạ tầng, ngay cả khi workload data plane vẫn khỏe.

## 15. Observability cho state và backend

Theo dõi:
- Lock acquisition success/failure và wait duration.
- Stale lock count/age.
- State read/write errors và latency.
- Backend availability và throttling.
- Snapshot/version creation.
- Backup age và backup verification result.
- Restore drill success/failure.
- State size và tốc độ tăng.
- Concurrent run attempts.
- Plan/apply duration và failure.
- Drift count/age theo environment.
- Unauthorized read/write/delete attempts.

Không log state contents. Dashboard nên theo dõi metadata và audit event, không dump sensitive attributes. Alert khi backup quá cũ, lock bị giữ quá lâu, state write fail hoặc backend access policy bị thay đổi.

## 16. Đánh đổi theo Well-Architected

| Khía cạnh | Thiết kế tốt | Rủi ro cần quản lý | Bằng chứng |
|---|---|---|---|
| **Độ tin cậy** | Remote state, locking, versioning, tested restore | State loss/corruption, concurrent write, stale snapshot | Restore drill, lock tests, backup checks |
| **Bảo mật** | Encryption, least privilege, isolated backend, audit | State/plan lộ secret, state bị xóa hoặc sửa | IAM review, access logs, secret scanning |
| **Hiệu quả hiệu năng** | State boundary phù hợp, plan/apply có kiểm soát | State quá lớn, lock contention, plan dài | State size, lock wait, apply duration |
| **Tối ưu chi phí** | Chỉ lưu version/backup theo nhu cầu và phân tầng retention | Retention quá dài, backend request/storage | Storage cost, backup inventory |
| **Vận hành xuất sắc** | Owner, runbook, pipeline serialization, drift workflow | Manual state surgery, dual backend, không có recovery | Change audit, runbook, restore test |
| **Bền vững** | Right-size state, cleanup artifact/backup đúng policy | State/history tăng không kiểm soát | Lifecycle review, storage growth |

Các đánh đổi:
- Remote backend tăng độ tin cậy nhóm nhưng thêm dependency và chi phí.
- State nhỏ giảm blast radius và contention nhưng tăng coordination giữa state.
- Locking ngăn concurrent writes nhưng một operation treo có thể chặn cả nhóm.
- Versioning hỗ trợ recovery nhưng không thay backup độc lập.
- Read-only access rộng giúp plan/discovery nhưng có thể lộ sensitive data.
- DR replication của state tăng khả năng phục hồi nhưng phải tránh dual-writer.

## 17. Quy trình thiết kế state management

Architecture review nên đi theo các bước:

1. **Xác định owner và scope:** resource nào thuộc state nào, ai chịu trách nhiệm?
2. **Chọn backend:** local cho lab, remote cho team/production; kiểm tra lock và version support.
3. **Định nghĩa boundary:** theo environment, domain, team hoặc region dựa trên lifecycle và blast radius.
4. **Thiết kế access policy:** tách runner identity, operator read, break-glass và backup admin.
5. **Bảo vệ dữ liệu:** encryption, TLS, retention, audit và xử lý secret.
6. **Thiết kế locking:** serialize apply theo state key, timeout và stale lock runbook.
7. **Quản lý plan/apply:** pin version, approval, stale plan check và CI concurrency group.
8. **Backup/versioning:** định nghĩa snapshot, backup độc lập và retention.
9. **Recovery:** test restore, lineage/serial, inventory reconciliation và import.
10. **Drift handling:** phát hiện, phân loại, đưa manual change vào code hoặc revert.
11. **Migration:** backup, lock, migrate và xác minh backend mới.
12. **DR:** kiểm tra region/account dự phòng, KMS, pipeline và single-writer control.
13. **Observability:** lock, backend, backup age, restore drill, state access và drift metrics.
14. **Kiểm thử:** concurrent run, runner crash, backend outage, stale backup, corrupt state và failback.

### Checklist trước production

| Hạng mục | PASS khi |
|---|---|
| Backend | Remote backend được chọn và owner rõ |
| Locking | Backend lock được hỗ trợ và test concurrent |
| Isolation | Environment/state boundary và IAM độc lập |
| Sensitive data | State/plan được mã hóa, access restricted |
| Backup | Versioning và backup độc lập có retention |
| Restore | Có restore drill và inventory reconciliation |
| Pipeline | Apply serialized theo state, approval và stale-plan check |
| Drift | Có lịch detect và owner xử lý |
| State surgery | Có backup/change control/plan review |
| DR | Có backend recovery và single-writer plan |
| Observability | Theo dõi lock, state write, backup, drift và access |
| Documentation | Runbook, owner, escalation và recovery steps rõ |

## 18. ADR minh họa — Remote state cho Booking Platform

> **Bối cảnh:** Ba team cùng quản lý network, application và database của Booking Platform. Hiện state nằm trên laptop của một kỹ sư và thỉnh thoảng hai người apply gần như cùng lúc.
>
> **Phương án A:** Tiếp tục local state và chia sẻ file qua repository. Dễ bắt đầu nhưng dễ commit secret, mất file, ghi đè và thiếu lock tập trung.
>
> **Phương án B:** Remote backend có encryption, versioning, locking và access policy; state tách theo environment và domain ownership.
>
> **Quyết định minh họa:** Chọn B. Network, platform và application có state boundary rõ; shared resource chỉ có một owner. Production apply chạy qua CI identity với approval.
>
> **Locking:** Backend lock kết hợp pipeline concurrency group theo state key. Force-unlock chỉ qua runbook và incident/change ID.
>
> **Recovery:** Backup trước production apply quan trọng, versioning và copy độc lập; restore drill định kỳ trong workspace cô lập.
>
> **Security:** Runner có quyền read/write state cần thiết; developer read access được giới hạn; archive admin tách khỏi workload role.
>
> **Kiểm chứng:** Hai apply đồng thời, runner crash giữ lock, backend outage, restore snapshot cũ, drift từ console và state migration rehearsal.
>
> **Điều kiện xem xét lại:** State split gây dependency coordination quá lớn hoặc backend locking/availability không đáp ứng yêu cầu.

## 19. Bài tập thực hành: xử lý state hỏng và concurrent apply

Một nhóm quản lý production network bằng Terraform/OpenTofu. Remote state nằm trong object storage, bật versioning nhưng chưa có backup độc lập. CI có hai pipeline:
- Pipeline A chạy apply thay đổi route table.
- Pipeline B chạy apply cập nhật security group.

Cả hai cùng dùng một state nhưng pipeline chưa serialize. Một runner mất kết nối sau khi provider tạo resource; pipeline báo lỗi và lock vẫn tồn tại. Sau đó một admin cập nhật route trực tiếp trên console. Một tuần sau, state object bị ghi nhầm bằng một snapshot cũ.

**Yêu cầu:**
1. Xác định rủi ro từ concurrent apply và vì sao lock backend phải được kiểm chứng.
2. Thiết kế quy trình xác minh stale lock trước force-unlock.
3. Xác định cách phục hồi state version đúng và xác minh lineage/serial.
4. Đối chiếu resource thực tế sau lần apply bị gián đoạn.
5. Xử lý manual route change và drift.
6. Thiết kế backup độc lập và quyền xóa/version restore.
7. Đề xuất CI concurrency group và state ownership.
8. Lập kế hoạch restore drill và các alert cần có.

### Hướng giải quyết

- Dừng mọi apply tới state network. Kiểm tra runner A/B, process/provider operation, backend lock metadata và cloud audit; không force-unlock chỉ vì job báo lỗi.
- Khi xác nhận runner đã kết thúc, ghi change/incident ID, dùng đúng lock ID qua cơ chế công cụ hỗ trợ và sau đó refresh/plan.
- Chọn version snapshot theo apply history, lineage, serial, commit SHA và provider inventory; không chọn chỉ theo timestamp.
- Restore vào bản sao cô lập trước, kiểm tra state parse được và mapping resource ID. So sánh với cloud inventory và audit event.
- Đối với apply gián đoạn, xác định resource nào provider đã tạo nhưng state chưa ghi; cân nhắc import/reconcile, không apply mù.
- Điều tra route change: nếu hợp lệ, cập nhật config và review plan; nếu trái phép hoặc không mong muốn, revert theo change approval.
- Serialize apply theo state key bằng pipeline concurrency group và giữ backend lock làm lớp kiểm soát.
- Tạo backup cross-account hoặc trust boundary, mã hóa và hạn chế xóa; test restore định kỳ.
- Alert cho concurrent run, lock age, backend write failure, backup age, state version change bất thường và drift.

### Câu hỏi tự kiểm tra

1. State khác configuration và real infrastructure như thế nào?
2. Vì sao local state không phù hợp với team production workflow?
3. Remote backend có tự động bảo đảm locking không?
4. State lock ngăn loại concurrency nào và không ngăn được thay đổi nào?
5. Vì sao không nên force-unlock khi chưa xác minh runner cũ đã dừng?
6. Versioning khác backup độc lập ra sao?
7. Lineage và serial giúp bảo vệ điều gì khi restore?
8. Vì sao state cũ có thể tạo plan nguy hiểm?
9. Khi nào import phù hợp hơn restore snapshot?
10. Vì sao cùng một resource không nên được quản lý bởi hai state?
11. Làm sao xử lý manual change mà không ghi đè hotfix production?
12. Sau khi restore state, cần kiểm tra gì trước khi mở lại apply?

State management tốt không chỉ là chọn nơi lưu một file. Nó phải **duy trì mapping đáng tin giữa cấu hình và hạ tầng thực tế, ngăn concurrent writers, bảo vệ dữ liệu nhạy cảm, lưu recovery point độc lập và có quy trình đối soát trước khi tiếp tục apply**. Remote backend, locking, versioning và backup chỉ phát huy tác dụng khi đi cùng ownership, CI/CD governance, drift management và restore drills đã được kiểm chứng.
