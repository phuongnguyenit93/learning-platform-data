# Phát hiện drift, import tài nguyên và kiểm soát thay đổi

## 1. Bài toán: hạ tầng trên Azure thay đổi ngoài mã nguồn

Một nhóm triển khai ứng dụng Java/Spring Boot **orders-api** lên Azure Container Apps. Hạ tầng được mô tả bằng **Bicep** hoặc **Terraform**: resource group, virtual network, private endpoint, Azure Storage, Key Vault, managed identity và Azure Monitor. Trong một sự cố lúc nửa đêm, người trực vận hành bật public network access của Storage account để kiểm tra kết nối, rồi quên đưa về cấu hình cũ. Một kỹ sư khác tạo database từ Azure Portal, còn pipeline IaC chưa khai báo resource này. Sau vài tháng:

- Mã nguồn nói Storage chỉ dùng private access nhưng Azure thực tế đang cho phép public access.
- Pipeline Terraform đề xuất tạo lại hoặc xóa tài nguyên đang chứa dữ liệu quan trọng.
- Bicep what-if có những khác biệt khó giải thích giữa trạng thái mong muốn và cấu hình thực.
- Không ai biết một thay đổi do CI/CD, Azure Policy hay người dùng đã thực hiện.
- Những resource có sẵn chưa được đưa vào vòng đời IaC.
- Việc sửa khẩn cấp trở thành drift âm thầm, làm môi trường staging và production không còn tương đương.

Đó là lý do cần **phát hiện drift**, **adopt/import tài nguyên hiện hữu** và **kiểm soát thay đổi**. Mục tiêu không chỉ là cho công cụ báo “không có diff”, mà là bảo đảm trạng thái production được quản lý có chủ đích, có thể kiểm tra, phục hồi và truy vết mà không gây mất dữ liệu.

Bài thuộc chương **Hạ tầng dưới dạng mã** của module **CLOUD_PROVIDERS_AZURE**. Toàn module khám phá Azure từ subscriptions, resource groups, Microsoft Entra ID, mạng, compute, storage và data services đến triển khai, quan sát, bảo mật và chi phí. Các ví dụ dưới đây kết nối trực tiếp với Azure CLI, Resource Manager, Bicep, Terraform, Azure Policy, Azure Activity Log và pipeline CI/CD. Tên tài nguyên/số liệu là **giả định phục vụ học tập**; không chạy bất kỳ lệnh thay đổi production nếu chưa được cho phép.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **desired state**, **actual state**, **IaC state** và các loại configuration drift.
2. Phân biệt drift do sửa thủ công, thay đổi bởi công cụ khác, default/computed attributes và external automation.
3. Đọc kết quả **az deployment group what-if** với ARM/Bicep và **terraform plan** với Terraform.
4. Hiểu các giới hạn của what-if/plan và không coi mọi diff là thay đổi an toàn.
5. Dùng Azure Activity Log/Policy/Resource Graph làm bằng chứng phụ trợ để tìm nguyên nhân drift.
6. Phân biệt **Bicep existing resource** với việc đưa resource vào quản lý Terraform state.
7. Thiết kế quy trình áp dụng IaC cho tài nguyên Azure được tạo sẵn mà không tạo lại hoặc xóa nhầm.
8. Hiểu **terraform import**, **import block**, **state list/show**, **plan -refresh-only**, **moved blocks** và các tình huống áp dụng.
9. Đề xuất reconciliation khi trạng thái code, Terraform state và Azure thực tế khác nhau.
10. Bảo vệ tài nguyên chứa dữ liệu khỏi replacement/delete ngoài ý muốn.
11. Dùng review/approval, least-privilege RBAC, PIM, Azure Policy và CI/CD gates để kiểm soát thay đổi.
12. Xây quy trình drift detection định kỳ, phân loại mức độ, xử lý ngoại lệ, rollback và audit.
13. Tổ chức các bài lab kiểm chứng drift, import và change control trên **tài nguyên riêng của lab**.

## 3. Ba góc nhìn về một tài nguyên Azure

Với Bicep/ARM, hai góc nhìn chính là **định nghĩa mong muốn** và **tài nguyên Azure hiện có**. Với Terraform, có thêm góc nhìn **state** liên kết địa chỉ resource trong cấu hình với Azure object ID.

~~~mermaid
flowchart LR
    CODE[Git: desired IaC configuration] --> PLAN[Plan / what-if]
    STATE[(Terraform state nếu dùng Terraform)] --> PLAN
    AZURE[(Azure resources: actual state)] --> PLAN
    PLAN --> REVIEW[Review and approval]
    REVIEW --> APPLY[Controlled deployment]
    APPLY --> AZURE
    AZURE --> AUDIT[Activity Log / Policy / Monitor]
    AUDIT --> REVIEW
~~~

| Thành phần | Chứa thông tin gì? | Sai lầm thường gặp |
|---|---|---|
| **Desired state** | Mã Bicep/Terraform và tham số kỳ vọng | Coi file Git là mô tả đầy đủ mọi property Azure |
| **Actual state** | Cấu hình/tài nguyên thực từ Azure APIs | Coi Portal hiển thị mọi setting hoặc mọi thay đổi lịch sử |
| **Terraform state** | Mapping resource addresses, IDs, attributes đã theo dõi | Coi state là backup đầy đủ của Azure database |
| **Deployment history** | Kết quả những lần apply/deploy | Coi một lần deploy thành công là runtime đạt SLO |
| **Activity Log** | Một phần lịch sử management-plane operations | Coi nó lưu đầy đủ mọi data-plane hoặc chứng minh không có drift |
| **Policy compliance** | Đánh giá resource so với Azure Policy rules | Coi policy compliance giống so sánh code IaC cụ thể |

### 3.1. “No changes” nghĩa là gì?

Kết quả Terraform plan hoặc Bicep what-if **không có thay đổi** chỉ cho biết **theo dữ liệu, phạm vi, phiên bản provider/API và những thuộc tính được công cụ so sánh**, không phát hiện diff đáng kể. Nó không tự chứng minh application healthy, secrets không lộ, business dữ liệu đúng hay toàn bộ resource chưa khai báo đã được kiểm soát.

### 3.2. Drift không phải một status Azure duy nhất

“Drift” là khái niệm quản trị cấu hình. Có thể xuất hiện đồng thời drift của:

- Resource settings (firewall, SKU, tags).
- IaC state mapping.
- Quyền RBAC và managed identities.
- Policies, exemptions và diagnostic settings.
- Runtime app settings hoặc image digest.
- Data schema, database state và migration history.

Mỗi loại đòi nguồn bằng chứng và cách remediation khác nhau.

## 4. Phân loại drift theo nguyên nhân

| Loại | Ví dụ | Phân tích |
|---|---|---|
| **Manual drift** | Operator bật public access trên Storage | Có thể là sửa khẩn cấp nhưng không backport |
| **Out-of-band automation** | Một script khác đổi resource tags | Hai nguồn quản lý chưa thống nhất |
| **Provider/API default** | Azure áp default khác mô tả IaC | Có thể gây plan noise dù không có hành động chủ đích |
| **Computed/read-only** | Property chỉ Azure biết lúc runtime | Không phải mọi thay đổi đều có thể áp nguyên như code |
| **Policy remediation** | Azure Policy modify/deployIfNotExists thêm cấu hình | IaC phải hiểu chủ sở hữu policy và desired config |
| **Unmanaged resource** | Người dùng tạo Key Vault chưa có trong IaC | Chưa được IaC quản lý; chưa chắc có “diff” |
| **State drift** | Terraform state thiếu ID hoặc trỏ sai đối tượng | Cần state review/import/move có kiểm soát |
| **Intentional exception** | Firewall mở tạm trong incident | Có thời hạn/owner, cần quyết định backport hay revert |
| **Runtime drift** | Image đang chạy khác digest đã approve | Kiểm tra deploy config và runtime revision |
| **Data drift** | SQL schema bị thay ngoài migration tool | Không dùng Terraform plan đơn lẻ để kết luận |

### 4.1. Drift có thể có chủ ý nhưng vẫn phải được xử lý

Một thay đổi do on-call thực hiện để khôi phục dịch vụ không tự động là “vi phạm”. Tuy nhiên, nó phải có **incident/change ID, người sở hữu, thời hạn và quyết định**: giữ thay đổi bằng việc cập nhật IaC hay trả về cấu hình mong muốn.

### 4.2. Có những khác biệt chỉ là nhiễu

Thứ tự fields, casing, API defaults, các thuộc tính computed/unknown hoặc khác biệt serialization có thể sinh diff khó hiểu. Cần xác minh bằng Azure API/provider docs và test lab; không tắt mọi cảnh báo drift chỉ vì có vài false positives.

## 5. Drift có phải là lỗi bảo mật?

Không phải mọi drift đều là sự cố bảo mật, nhưng một số drift cần ưu tiên rất cao:

- Public network access được mở cho Storage, SQL, Key Vault.
- Role assignment được cấp Owner hoặc quyền data-plane quá rộng.
- Logs/audit/diagnostic settings bị tắt.
- Key Vault soft-delete/purge protection hoặc TLS security settings bị thay đổi.
- Azure Policy exemption không có approval.
- Encryption/access rules thay đổi.
- Private endpoint, route, NSG/firewall tạo đường đi ngoài dự kiến.
- Container image không còn đúng digest đã được kiểm tra.

Drift làm tăng cost nhưng ít nghiêm trọng hơn (ví dụ thêm tag) cần quy trình khác với một lỗ hổng exposure dữ liệu. Hệ thống nên **phân loại rủi ro theo tác động**, không xử lý tất cả diff theo thứ tự alphabet.

## 6. Phạm vi và nguồn sự thật (source of truth)

Tổ chức nên xác định resource ownership rõ ràng:

~~~text
Azure Landing Zone Platform Team:
  management groups, policy assignments, hub network,
  shared DNS, subscription-level IAM

Application Team:
  app runtime, application managed identity,
  application Storage container, monitoring config

Database Team:
  production database provisioning, backups,
  schema/migration workflow

Security Team:
  policy baseline, role exceptions, incident response
~~~

### 6.1. Một resource không nên có nhiều công cụ cùng “apply”

Nếu cả Terraform stack A và Bicep pipeline B cùng độc lập khai báo/cập nhật một Azure Storage account, chúng có thể ghi đè lẫn nhau. Dùng một **owner/source of truth** hoặc phân định property/resource scopes cực kỳ rõ, có integration contract.

### 6.2. IaC không phải nguồn sự thật của mọi dữ liệu

IaC mô tả resource configuration và quan hệ quản lý; không phải hệ lưu trạng thái database giao dịch hoặc secret value backup. Để kiểm tra data drift cần migration records, DB schema tools và business validation riêng.

### 6.3. Resource tags chỉ là metadata

Tag **managedBy=terraform** giúp inventory nhưng không ngăn operator sửa tài nguyên. Cần RBAC, policy, IaC pipeline và audit để enforce governance.

## 7. Quản lý drift theo vòng đời

~~~mermaid
flowchart TD
    BASE[Approved IaC baseline] --> SCAN[Scheduled plan / what-if]
    SCAN --> DIFF{Significant difference?}
    DIFF -- No --> LOG[Record clean scan]
    DIFF -- Yes --> CLASS[Classify severity and ownership]
    CLASS --> ROOT[Investigate Activity Log, policy, config]
    ROOT --> DEC{Desired direction?}
    DEC -- Restore approved baseline --> FIX[Reviewed IaC apply]
    DEC -- Accept authorized change --> BACK[Update code + tests + approvals]
    DEC -- Unknown or unsafe --> HOLD[Freeze + incident / escalation]
    FIX --> VERIFY[Readback + health checks]
    BACK --> VERIFY
    HOLD --> VERIFY
    VERIFY --> BASE
~~~

### 7.1. Đầu ra scan phải có cấu trúc

Ghi **subscription, resource group, resource IDs, IaC commit, stack/module, tool/provider version, plan ID/timestamp, summary thay đổi và severity**. Không log sensitive Terraform state hoặc các bí mật khi lưu báo cáo.

### 7.2. Phát hiện không đồng nghĩa tự sửa

Một công cụ báo firewall mismatch không có nghĩa được tự động chạy apply ngay lập tức. Auto-remediation chỉ phù hợp những policy được đánh giá ít rủi ro, có scope hạn chế, đủ observability và rollback.

### 7.3. Quyết định sửa theo hai hướng

- **Azure → theo Git:** revert out-of-band change bằng IaC.
- **Git → theo Azure:** nếu thay đổi được phê duyệt, cập nhật code/parameters và kiểm chứng mới thành baseline.

Tuyệt đối không chỉnh IaC cho khớp mọi trạng thái thực tế một cách tự động vì có thể hợp thức hóa cấu hình không an toàn.

## 8. Những giới hạn của drift detection

Không thể kỳ vọng một lệnh duy nhất quét “tất cả drift Azure” hoàn chỉnh.

### 8.1. Tài nguyên chưa được quản lý có thể không hiện

Bicep what-if mô phỏng template được cung cấp; Terraform plan so sánh resources mà configuration/state quản lý. Một resource mới do người dùng tự tạo ngoài scope có thể không xuất hiện là drift nếu không có inventory/reconciliation riêng.

### 8.2. Provider và API không thấy hết

Có những thuộc tính computed, write-only hoặc phụ thuộc service. Secret values thường không được đọc lại nguyên văn; dynamic platform state cũng không luôn mô tả được bằng IaC.

### 8.3. Một số diff là tác động gián tiếp

Đổi SKU hoặc network config có thể làm restart/recreate, thay IP, gây downtime hoặc mất tương thích dù plan chỉ ghi vài properties. Đánh giá **blast radius** và service-specific implications.

### 8.4. Data-plane drift cần công cụ riêng

AzureActivity thường ghi management-plane, không lưu đầy đủ mọi thay đổi bên trong SQL schema hay Cosmos item. Sử dụng audit logs, migration checksums và DB-specific diagnostics.

## 9. Trước khi quét: xác minh subscription và environment

Ví dụ Azure CLI **chỉ đọc**:

~~~bash
az account show \
  --query '{subscription:id,name:name,tenant:tenantId}' \
  -o table

az resource list \
  --resource-group rg-orders-dev \
  --query '[].{name:name,type:type,location:location}' \
  -o table
~~~

### 9.1. Không dựa vào az account default vô điều kiện

CLI có thể đang trỏ subscription khác với pipeline hoặc Terraform provider. Trước lệnh apply/import, dùng subscription ID đã được phê duyệt và đối chiếu environment tags.

### 9.2. Quyền xem không đồng nghĩa quyền sửa

Người chạy scan có thể chỉ cần read permissions cho Azure resources và quyền đọc state cần thiết; quyền deploy/role assignment nên thuộc job tách biệt có approval.

### 9.3. Đảm bảo resource identity không mơ hồ

Cùng tên Storage/account service có thể xuất hiện ở subscriptions/regions khác nhau tùy loại. Khi đối soát, dùng **full ARM resource ID**, không chỉ display name.

## 10. Bicep/ARM: cách nhìn desired và actual state

**Bicep** được biên dịch thành ARM template và triển khai qua **Azure Resource Manager**. Trong mô hình này, không có một **Terraform-like state file** do Bicep quản lý. Azure Resource Manager và resource providers nắm trạng thái tài nguyên; template/parameters mô tả trạng thái muốn triển khai.

~~~text
main.bicep + environment parameters
        |
ARM what-if API
        |
Current Azure resources
        |
Predicted change set
        |
Reviewed deployment
~~~

### 10.1. Vai trò của what-if

**What-if** dự đoán những thay đổi của một deployment theo scope và template: create, modify, delete, no change, ignore/unsupported diagnostics tùy API/tool version. Nó không thay CI/security gates và không đảm bảo mọi tác động đều được dự đoán chính xác.

### 10.2. ARM deployment không phải luôn xóa resource ngoài template

Trong **incremental deployment mode**, một resource không còn xuất hiện trong template không mặc nhiên bị xóa. Các khả năng quản lý vòng đời khác như deployment stacks có semantics và tùy chọn riêng. Không dùng “xóa khỏi Bicep file” làm chiến lược xóa resource an toàn khi chưa hiểu mode và tính năng đang sử dụng.

### 10.3. Template có thể khai báo subset properties

Nếu template không khai báo property nào đó, behavior khi redeploy phụ thuộc resource provider/API/defaults; không tự suy rằng property bị giữ nguyên hay sẽ reset. Xem what-if và resource docs cụ thể.

## 11. Ví dụ Bicep baseline cho một Storage account lab

~~~bicep
targetScope = 'resourceGroup'

@description('Storage name must be globally unique and valid.')
param storageAccountName string

param location string = resourceGroup().location

param envTag string = 'dev'

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  tags: {
    environment: envTag
    managedBy: 'bicep'
  }
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

output storageId string = storage.id
~~~

**Đây là mã minh họa, không được chạy trên production.** Kiểm tra API version, subscription policy, naming, replication, networking, encryption và backup requirements khi dùng thật.

### 11.1. Vì sao có allowBlobPublicAccess?

Thiết lập ví dụ cấm anonymous blob access cấp account. Nó **không tự tắt public network access endpoint**. Hai thuộc tính này khác nhau; cần đánh giá cả firewall/network rules và authentication/RBAC để hạn chế exposure.

### 11.2. Lưu parameter riêng

Một parameter file cho môi trường lab có thể chứa tên và tags không nhạy cảm; không đưa storage account key/connection string chứa key vào Git.

### 11.3. Mục tiêu test drift

Đầu tiên deploy baseline đã duyệt vào lab, sau đó thay đổi một tag hoặc property không phá dữ liệu bằng Portal trong thời gian thử nghiệm, chạy what-if để quan sát. Luôn xác minh tài nguyên thuộc quyền lab của bạn.

## 12. Bicep what-if: xem trước thay đổi

Tại resource group được phép, Azure CLI có lệnh:

~~~bash
RG='rg-iac-drift-lab'
STORAGE='iacdriftlab001'

az account show \
  --query '{subscription:id,name:name}' -o table

az deployment group what-if \
  --resource-group "$RG" \
  --template-file main.bicep \
  --parameters storageAccountName="$STORAGE"
~~~

**Lệnh chỉ là ví dụ.** File main.bicep cần tồn tại trong dự án của người học; bài học không tạo file đó. Chỉ chạy sau khi chọn đúng subscription và resource group. Quyền ARM deployment/what-if có thể cần nhiều hơn quyền Reader thuần túy tùy resource API.

### 12.1. Đọc predicted changes

- **Create:** tài nguyên được dự đoán cần tạo.
- **Modify:** một số properties khác baseline.
- **Delete:** theo mode/tính năng và scope, cần kiểm tra cực kỳ kỹ.
- **NoChange:** theo dữ liệu mà công cụ đánh giá thì không có thay đổi.
- **Ignore/diagnostic:** công cụ không thể đánh giá chính xác một phần theo API/version.

### 12.2. Lệnh what-if không apply

Một what-if thông thường không triển khai thay đổi; nó trả dự đoán để review. Nhưng có thể phát sinh API calls/permission effects và không phải chứng cứ tuyệt đối rằng apply sau đó sẽ giống 100%.

### 12.3. Không giả định “0 diff” là toàn Azure sạch

Nó chỉ xét template, scope, API và inputs hiện tại. Unmanaged resources, khác biệt ngoài declared properties, data-plane và runtime state cần quét riêng.
## 13. Cách đọc diff Bicep what-if mà không gây hiểu lầm

Giả sử template đặt tag **environment=dev** và Storage account hiện tại bị người dùng đổi thành **environment=temporary**. What-if có thể dự đoán thay đổi tag về baseline. Tuy nhiên trước khi approve:

1. Xác nhận đúng **ARM resource ID**.
2. Xem properties khác cũng thay đổi, không chỉ tag.
3. Phân biệt intentional emergency change và unauthorized drift.
4. Kiểm tra điều kiện service/API có thể gây restart/downtime.
5. Tra Activity Log để biết thời điểm, caller và change correlation.
6. Xác nhận region/subscription/template parameters.
7. Duyệt change rồi mới apply có kiểm soát.
8. Readback tài nguyên thực và chạy smoke tests.

### 13.1. Diff có thể phát sinh từ biểu thức chưa tính được

Bicep/ARM có các hàm tham chiếu runtime và properties được provider tính; what-if có thể không biểu diễn chính xác giá trị dự kiến cho một số trường hợp. Tham khảo trạng thái resource thực và giới hạn tool khi có kết quả nhiễu.

### 13.2. Nếu dự đoán Delete hoặc Replace

Dừng job tự động, yêu cầu owner review và backup/data impact assessment, kể cả khi thay đổi bắt nguồn từ một PR tưởng như chỉ sửa tag. Một Storage account có dữ liệu không thể được xem như một resource có thể recreate tùy ý.

### 13.3. Không bỏ qua toàn bộ what-if bằng một cờ

Việc lọc bớt output noise có thể hữu ích nhưng không được che mất security-relevant changes. Nếu có allowlist các trường thường xuyên thay đổi, phải có owner và audit lý do.

## 14. Import một tài nguyên đã có vào Bicep nghĩa là gì?

**Bicep không có lệnh import vào state tương đương Terraform import.** Thường có hai cách đưa Azure resource sẵn có vào thiết kế:

1. **Reference existing resource** bằng từ khóa **existing** để sử dụng ID/properties và kết nối với resources khác mà không định nghĩa việc tạo/sửa nó.
2. **Adopt as managed resource** bằng cách viết declaration đầy đủ cho resource cùng ID, theo đúng scope/API/permissions và dùng what-if + review trước khi triển khai theo định nghĩa mong muốn.

### 14.1. Ví dụ existing resource

~~~bicep
targetScope = 'resourceGroup'

param storageName string

resource existingStorage 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageName
}

output existingStorageResourceId string = existingStorage.id
~~~

### 14.2. existing không quản lý property của tài nguyên

Từ khóa **existing** làm reference, **không** đồng nghĩa “đã import thành resource được Bicep quản lý”, không tự áp TLS, firewall, tags hay SKU. Nếu muốn sửa resource phải khai báo resource phù hợp và deploy có kiểm soát.

### 14.3. Resource cùng tên nhưng khác scope là resource khác

ARM resource ID bao gồm subscription/resource group/provider/type/name. Phải bảo đảm target scope và resource ID chính xác, nhất là với cross-subscription references.

## 15. Quy trình adopt resource vào Bicep có kiểm soát

Một tài nguyên Storage production được tạo thủ công từ trước, bây giờ nhóm muốn đưa vào IaC.

### Bước 1 — Chọn quyền sở hữu

Xác định đúng IaC repository/module, team owner, environment và người phê duyệt. Kiểm tra đã có Terraform/Deployment Stack/pipeline khác quản lý resource hay chưa.

### Bước 2 — Snapshot metadata và dependency

Lấy Azure resource ID, type, API-relevant properties, tags, RBAC, private endpoints, retention, encryption, locks, diagnostic settings, data lifecycle và application dependencies. Không sao chép key, connection string có secret vào source.

### Bước 3 — Viết Bicep mô tả actual properties được chấp thuận

Khai báo resource và những security/availability properties quan trọng theo API version phù hợp. Dùng parameterization cho nonsecret environment values; không “adopt” bằng cách copy bí mật vào Bicep.

### Bước 4 — What-if chỉ trên đúng scope

Chạy preview; nếu resource được nhận diện cùng ID và muốn tạo/đổi/xóa property, đọc toàn bộ diff. **Không được thấy predicted Create cho tài nguyên production đang tồn tại** rồi tiếp tục mà chưa hiểu sai scope/name/type.

### Bước 5 — Đối chiếu desired vs actual và xử lý diff

Đánh dấu mỗi thay đổi thành:
- Giữ lại như baseline được phê duyệt.
- Đổi về security policy chuẩn.
- Hoãn vì downtime/data migration.
- Không thuộc IaC owner này.

### Bước 6 — Review, apply và readback

Apply qua pipeline được bảo vệ, kiểm tra activity/deployment record, runtime/config changes, metrics và security posture. Bảo tồn rollback/restore plan cho các thay đổi có nguy cơ.

### Bước 7 — Bảo vệ trước drift tiếp theo

Đặt owner, IaC pipeline gates, Azure Policy phù hợp, role boundaries và periodic what-if review.

## 16. Export template/decompile có phải cách import tự động không?

Azure có các công cụ xuất ARM template hoặc **decompile ARM JSON sang Bicep** hỗ trợ khởi tạo mã, nhưng kết quả có thể:

- Thiếu một số properties, children/extension resources hoặc quan hệ phụ thuộc.
- Chứa read-only/computed settings không được deploy trực tiếp.
- Phụ thuộc API version cũ/không còn lý tưởng.
- Chứa tên/IDs hardcode theo production.
- Không phản ánh toàn bộ network, RBAC, secrets hoặc dữ liệu.
- Tạo tài liệu dài, khó modularize và khó quản trị.

### 16.1. Khởi tạo chứ không sao chép nguyên xi

Tập hợp inventory, chọn schema/API version, modularize, xử lý parameters, loại secrets/computed fields, thêm policy, chạy validate/what-if và review từng resource trước khi coi template là nguồn sự thật.

### 16.2. Không đọc secret bằng export

Một ARM template export không phải backup của Key Vault secrets/SQL records hoặc toàn bộ runtime state. Không dùng tính năng này làm thay kế hoạch backup/restore.

### 16.3. Bicep state-less có điểm mạnh và giới hạn

Không phải quản lý Terraform state backend, nhưng vẫn cần deployment history, resource ownership, IaC baseline, detection of unmanaged objects và change management. “Không có state file” không có nghĩa không có drift.

## 17. Terraform: ba thứ cần nhất quán

Terraform sử dụng **configuration**, **state** và **remote infrastructure**.

~~~text
Terraform configuration (resource addresses + desired attributes)
            |
           Plan
            |
Terraform state (tracked Azure IDs, attributes)
            |
Azure Resource Manager / provider reads actual resource
~~~

### 17.1. Resource address khác Azure resource ID

Ví dụ:

- Terraform address: **azurerm_resource_group.lab**
- Azure ARM ID: **/subscriptions/SUB_ID/resourceGroups/rg-iac-lab**

Address là vị trí trong Terraform configuration/state; ARM ID là định danh đối tượng Azure. Import là nối hai khái niệm đó cho resource sẵn có.

### 17.2. Plan dựa trên state đã refresh

Thông thường **terraform plan** đọc remote objects qua provider để làm mới thông tin phù hợp, rồi so sánh với desired config. Provider behavior, permissions và options ảnh hưởng kết quả; không xem plan là bản sao hoàn chỉnh mọi cấu hình Azure.

### 17.3. State chứa dữ liệu nhạy cảm

State có thể lưu thuộc tính nhạy cảm/secret theo resource/provider, ngay cả khi CLI ẩn một số giá trị. Lưu remote backend có encryption, access controls, audit, backup và locking; tuyệt đối không đăng state ra ticket/chat.

## 18. Terraform configuration cho Resource Group lab

Mẫu minh họa với AzureRM provider; provider version là placeholder cần chọn release được phê duyệt.

~~~hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

variable "subscription_id" {
  type = string
}

variable "location" {
  type    = string
  default = "southeastasia"
}

resource "azurerm_resource_group" "lab" {
  name     = "rg-iac-drift-lab"
  location = var.location

  tags = {
    environment = "lab"
    managedBy   = "terraform"
  }
}
~~~

### 18.1. Version và authentication

AzureRM provider versions có yêu cầu khác nhau. Ví dụ minh họa provider 4.x và subscription_id. Khi sử dụng thực, pin version chính xác theo dự án và cấu hình Entra/OIDC/managed identity theo provider documentation của phiên bản chọn.

### 18.2. Chưa chắc resource group đã được tạo

Terraform configuration chỉ mô tả resource; **terraform plan** cho biết đề xuất. Không được chạy apply nếu chưa xác minh resource chưa tồn tại, đúng subscription và quyền quản lý.

### 18.3. Nếu RG đã tồn tại?

Không chạy apply chỉ để thấy lỗi already exists. Chọn quy trình import đúng và review config trước khi Terraform quản lý.

## 19. Terraform drift detection bằng plan

Trong thư mục Terraform lab đã được chuẩn bị:

~~~bash
terraform init
terraform fmt -check
terraform validate
terraform plan -out=drift.tfplan
terraform show drift.tfplan
~~~

### 19.1. terraform plan có thể đề xuất gì?

- **Create (+):** resource có trong config nhưng chưa được state quản lý.
- **Update in-place (~):** Terraform dự đoán sửa một số fields.
- **Destroy (-):** resource trong state không còn trong config hoặc bị remove theo logic.
- **Replace (-/+ hoặc +/-):** Terraform dự đoán destroy/create resource để đáp ứng thay đổi.
- **No changes:** theo provider/config/state hiện hành không thấy thay đổi.

### 19.2. Plan có thể chứa thông tin nhạy cảm

Saved plan files đôi khi chứa attributes/values không nên công khai, kể cả CLI redaction không giống dữ liệu bên trong. Bảo vệ drift.tfplan và **không commit** vào Git. Trong project lab, xóa file tạm khi không còn cần.

### 19.3. Mục tiêu review là rủi ro, không chỉ số lượng diff

Một thay đổi tag nhỏ có thể chấp nhận; một replacement của database hoặc network exposure cần block và escalation. Phải đọc path và resource IDs của proposed change.

### 19.4. Không apply tự động từ một PR untrusted

Terraform plan cho PR nên chạy read-only/limited identity; apply chỉ ở protected environment với approved permissions và trusted source.

## 20. Terraform plan -detailed-exitcode trong CI

Lệnh hữu ích để phát hiện diff:

~~~bash
terraform plan \
  -detailed-exitcode \
  -no-color \
  -out=drift.tfplan
~~~

Các exit codes thường dùng:

| Exit code | Ý nghĩa | Cách diễn giải |
|---|---|---|
| **0** | Không có changes theo plan | Clean cho scope đó |
| **1** | Error khi plan | Scan thất bại, không kết luận sạch |
| **2** | Có changes trong plan | Cần review/classify |

### 20.1. CI shell với set -e cần xử lý đúng code 2

Trong Bash, nếu script bật **set -e**, exit 2 có thể khiến job dừng trước khi ghi báo cáo. Mẫu minh họa:

~~~bash
set +e
terraform plan -detailed-exitcode -no-color -out=drift.tfplan
code=$?
set -e

case "$code" in
  0) echo "No planned changes" ;;
  2) echo "Differences detected; review required" ;;
  *) echo "Terraform plan error"; exit "$code" ;;
esac
~~~

### 20.2. Exit 2 không đồng nghĩa tất cả differences là drift

Một pull request thay đổi IaC hợp pháp cũng làm plan có changes. Drift detection thuần phải so baseline được phê duyệt, resource state và việc có code change hay không. Nếu không phân biệt, pipeline sẽ cảnh báo mọi deployment hợp lệ là “drift”.

### 20.3. Đọc diff dù code là 2

Phân loại update, replace, delete, RBAC/network/data changes và liệu có đụng production hay không. Không coi plan thành công và có diff là permission để apply.

## 21. Terraform refresh-only: có gì khác regular plan?

**terraform plan -refresh-only** tập trung thể hiện những thay đổi **giữa trạng thái đã theo dõi và đối tượng remote** sau refresh, không lập kế hoạch để buộc remote resources về configuration như regular plan.

~~~bash
terraform plan -refresh-only
~~~

### 21.1. Khi nào hữu ích?

- Điều tra manual/out-of-band changes.
- Kiểm tra state có outdated attributes.
- Đối chiếu resource remote với state đã lưu.
- Giảm nhiễu từ planned configuration changes khi tìm nguồn drift.

### 21.2. Không đồng nghĩa sửa hạ tầng

**plan -refresh-only** chỉ dự đoán việc refresh state. Nó không tự cập nhật Azure resources và không tự quyết định rằng thay đổi remote là hợp lệ.

### 21.3. Cẩn thận với apply -refresh-only

**terraform apply -refresh-only** có thể cập nhật state theo remote mà không sửa resource, khiến tracking/baseline bị thay đổi. Không dùng như shortcut “làm drift biến mất”; cần owner review và plan vì có thể hợp thức hóa manual modifications trong state.

### 21.4. Không dùng -refresh=false để che drift

Tắt refresh có thể làm plan dựa trên thông tin stale. Một plan không có changes khi không đọc Azure actual state không phải bằng chứng cấu hình sạch.

## 22. Terraform import (CLI): nối object hiện hữu với state

Giả sử RG **rg-iac-drift-lab** đã tồn tại trong Azure và chưa có trong Terraform state. Configuration đã khai báo đúng address **azurerm_resource_group.lab**.

~~~bash
terraform import \
  azurerm_resource_group.lab \
  "/subscriptions/SUBSCRIPTION_ID/resourceGroups/rg-iac-drift-lab"
~~~

### 22.1. CLI import làm gì?

Đưa Azure resource hiện có vào Terraform state tại address đã chọn qua provider import semantics. **Không có nghĩa Terraform đã kiểm tra hoặc viết đầy đủ code** để mô tả mọi thuộc tính mong muốn.

### 22.2. Import khác apply

Import không phải thao tác để “tạo một RG mới”. Nó khai báo ownership/tracking trong Terraform state đối với RG đã tồn tại. Sau import, **terraform plan** có thể vẫn đề xuất thay đổi hoặc thay thế nếu config không khớp actual fields.

### 22.3. Điều kiện tiên quyết

- Đúng subscription/tenant/provider configuration.
- Địa chỉ Terraform chưa tracking object khác.
- Azure object thực sự tồn tại.
- Người thực hiện có quyền đọc resource và quyền ghi state backend.
- Resource không đang bị Terraform workspace/stack khác quản lý.
- Đã chụp backup/snapshot state theo policy.
- Có owner approval cho adoption.

### 22.4. Xác minh ngay sau import

~~~bash
terraform state list
terraform state show azurerm_resource_group.lab
terraform plan
~~~

Nếu plan dự đoán replacement/delete, dừng lại để điều chỉnh config/migration plan. Không apply mù chỉ vì import đã thành công.

## 23. Terraform import block: cách khai báo adoption trong mã

Từ Terraform 1.5, có thể dùng **import block** trong HCL để đưa import vào workflow plan/apply có review:

~~~hcl
import {
  to = azurerm_resource_group.lab
  id = "/subscriptions/SUBSCRIPTION_ID/resourceGroups/rg-iac-drift-lab"
}
~~~

Tài nguyên đích cần có **resource configuration** thích hợp, trừ các workflows được provider/tool cho phép sinh cấu hình có kiểm soát.

### 23.1. Lợi thế so với CLI import

- Import intent hiển thị trong pull request.
- Plan thể hiện các import actions, có review/approval.
- Phù hợp change control và audit.
- Có thể kết hợp config generation theo khả năng Terraform version/provider.

### 23.2. Import block không phải bảo vệ dữ liệu tự động

Nếu code khai báo sai location/SKU/name, plan có thể đề xuất sửa hoặc replace. Import phải được review với actual state và business risk giống mọi thay đổi IaC.

### 23.3. Không duplicate ownership

Một Azure resource không nên được import vào hai Terraform states độc lập rồi apply từ hai nơi. Hai stacks có thể ghi đè nhau hoặc attempt destroy cùng resource.

## 24. Terraform generated config: bước khởi tạo, không phải mã production

Một workflow có thể sử dụng import block và **terraform plan -generate-config-out=...** trên các phiên bản Terraform hỗ trợ để đề xuất resource configuration cho imported object.

Ví dụ minh họa:

~~~bash
terraform plan \
  -generate-config-out=generated-resources.tf
~~~

### 24.1. Chỉ chạy khi chuẩn bị import hợp lệ

File generated-resources.tf là đầu ra **tại dự án lab**, không phải file sẽ được tạo bởi bài học này. Lệnh có requirements/limitations theo Terraform/provider; cần xem errors nếu resource đã có config hoặc provider không hỗ trợ đủ.

### 24.2. Generated config có thể chứa noise/attributes không nên version hóa

Xem properties thực, bỏ read-only/computed defaults không cần, tách variables/modules, kiểm tra secrets và provider/API compatibility. Không commit nguyên một generated file chưa kiểm tra.

### 24.3. Plan sạch sau import chưa đảm bảo policy đã đúng

Có thể actual resource đang cho phép anonymous access hoặc thiếu diagnostics. “Adopt exactly as is” chỉ là bước đầu. Sau đó phải đối chiếu organizational baseline rồi thực hiện change có phê duyệt.

### 24.4. Đừng dùng import block để đổi ID tài nguyên

Import nối address tới ID; nếu resource ID khác mục tiêu, kiểm tra scope và ownership. Thay đổi ID/scope có thể đòi một migration riêng, không giải quyết bằng nhập bừa object mới.

## 25. Terraform state list/show và sự khác nhau với resource reality

~~~bash
terraform state list
terraform state show azurerm_resource_group.lab
~~~

### 25.1. State show cho biết gì?

Những attributes mà Terraform đang tracking theo provider state. Nó không tự chứng minh tất cả Azure properties đã được đọc mới nhất tại thời điểm query; cần plan/refresh hoặc Azure API read để đối chiếu.

### 25.2. Dùng Azure API để xác minh ID/property quan trọng

Ví dụ Azure CLI:

~~~bash
az group show \
  --name rg-iac-drift-lab \
  --query '{id:id,name:name,location:location,tags:tags}' \
  -o json
~~~

### 25.3. Không sửa state thủ công để hết diff

State operations là thao tác ownership có thể nguy hiểm. Nên dùng import/moved/refactor và backup/review theo quy trình; chỉnh state hoặc xóa resource address tùy tiện có thể làm Terraform mất quản lý đối tượng đang quan trọng.

### 25.4. Terraform state là dữ liệu mật

Giới hạn người có quyền backend, encryption/locking/audit, backup có kiểm soát và không đưa output có secret vào issue hoặc pipeline public artifact.
## 26. Refactor Terraform address: moved block khác import

Giả sử trước kia một Storage account ở Terraform address **azurerm_storage_account.data**, sau đó refactor vào module **module.storage.azurerm_storage_account.this** nhưng Azure resource vẫn giữ nguyên.

### 26.1. Đây không phải một tài nguyên mới

Nếu chỉ đổi address mà không hướng dẫn state migration, Terraform có thể đề xuất destroy old address và create new address. Cần xử lý **resource address move** bằng moved block hoặc state move hợp lệ.

~~~hcl
moved {
  from = azurerm_storage_account.data
  to   = module.storage.azurerm_storage_account.this
}
~~~

### 26.2. moved khác import

- **moved**: chuyển một object đã được state quản lý sang address mới trong configuration.
- **import**: đưa object Azure đã tồn tại nhưng chưa được state hiện tại quản lý vào address.
- **data source**: đọc một đối tượng đã có, không biến nó thành Terraform-managed resource.

### 26.3. State mv vẫn có use case đặc biệt

**terraform state mv** có thể dùng trong state operations theo quy trình, nhưng moved blocks giúp ghi ý định refactor trong code để plan/review rõ ràng hơn. Phải chú ý module addresses, for_each/count, imports và ownership boundaries.

### 26.4. Đổi state backend là một migration riêng

Di chuyển resource addresses trong cùng state không đồng nghĩa chuyển backend hoặc chia stack. Backend migration có yêu cầu lock/backup/permissions và reconcile độc lập; không chạy hai writers song song trong quá trình chuyển.

## 27. Terraform state rm: tại sao phải thận trọng?

**terraform state rm** ngừng tracking một resource address trong state hiện tại mà không trực tiếp xóa Azure resource theo semantics của lệnh. Điều này **không phải** biện pháp sửa drift thông thường.

### 27.1. Nếu xóa state address nhưng config vẫn còn

Lần plan tiếp có thể đề xuất tạo resource mới. Nếu Azure object đã tồn tại và provider không cho adopt ngầm, apply có thể fail hoặc gây tác động không mong muốn. Không dùng state rm để làm plan “không thấy lỗi”.

### 27.2. Khi chuyển quyền quản lý giữa stacks

Quy trình cần:

1. Chọn source/destination state và owners.
2. Snapshot cả hai state, kiểm tra locking.
3. Freeze mọi apply liên quan trong migration window.
4. Cập nhật config và xác nhận Azure ID được giữ.
5. Dùng state transfer/import/move approach phù hợp, có review.
6. Chạy plan **cả hai stacks** để chắc không còn destroy/create không mong muốn.
7. Verify source stack không quản lý lại, destination stack track đúng resource.
8. Kết thúc freeze và ghi change record.

### 27.3. Không xóa resource khỏi state rồi bỏ mặc không có owner

Đó là tạo unmanaged resource, tăng khả năng cấu hình drift, không phải giảm drift. Nếu chủ đích chuyển sang Bicep, cần xác định Bicep module/owner đang quản lý trước khi gỡ Terraform ownership.

## 28. Remote Terraform state trên Azure Storage

Một backend AzureRM cho Terraform có thể dùng Azure Blob Storage làm remote state. Ví dụ **cấu hình backend giả định**:

~~~hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-tfstate-platform"
    storage_account_name = "tfstateplatform001"
    container_name       = "state"
    key                  = "orders/prod.tfstate"
    use_azuread_auth     = true
  }
}
~~~

**Chỉ dùng sau khi** Storage account/container đã được provision an toàn và backend auth/role assignments theo Terraform version/support thực tế. Tên Storage phải hợp lệ, duy nhất và được kiểm tra.

### 28.1. State locking

Azure Blob Storage backend có cơ chế lock phù hợp với Azure Blob leases; giúp ngăn hai Terraform applies đồng thời trên cùng state. Không tắt locking trong production để vượt lỗi mà chưa điều tra session/owner.

### 28.2. State encryption và access control

Giữ private endpoint/network controls khi cần, Entra RBAC data-plane, encryption và backup/versioning theo chính sách. **Chỉ cần quyền đọc hoặc sửa state cũng có thể lộ thông tin nhạy cảm**; đừng chia sẻ backend với người không cần biết.

### 28.3. State của dev và prod phải được cô lập hợp lý

Dùng separate keys/containers/accounts và identities theo trust boundary. Tách key không thay permission separation nếu một principal vẫn được quyền đọc mọi blob trong account.

### 28.4. Khi state lock bị treo

Xác nhận job nào còn chạy, Azure resource/lease và owner. Không force-unlock khi vẫn có apply đang hoạt động; gây concurrent writers và state corruption.

## 29. Dùng Azure Activity Log để điều tra nguyên nhân

Azure Activity Log ghi các **management-plane events** của Azure subscription, hữu ích để hỏi ai/điều gì đã thao tác với resource hoặc role.

Ví dụ truy vấn bằng Azure CLI khi có quyền:

~~~bash
az monitor activity-log list \
  --resource-group rg-iac-drift-lab \
  --offset 7d \
  --query '[].{time:eventTimestamp,operation:operationName.value,caller:caller,status:status.value}' \
  -o table
~~~

### 29.1. Đọc timeline đúng nguồn

Nếu Terraform plan thấy network property khác, tìm write operations gần thời điểm drift. Đối chiếu correlation/activity ID, caller, deployment name và pipeline runs.

### 29.2. Activity Log không chứng minh toàn bộ sự thật

Nó không ghi hết data-plane changes như mọi SQL DDL hoặc mọi Key Vault secret read; retention/khả năng tìm lịch sử cũng phụ thuộc dịch vụ và cấu hình export. Nếu cần lưu lâu hơn, phải có logging/audit architecture riêng.

### 29.3. Phân biệt user và managed identity

Caller có thể là service principal, managed identity, automation hoặc người dùng. Cần lần theo credential/CI run/approval để xác định hành động thực sự, không vội kết luận một tên principal chung là người trực tiếp sửa.

### 29.4. Clock và eventual consistency

Có thể có độ trễ ingest giữa khi thay đổi xảy ra và khi event xuất hiện trong logs. Giữ UTC timeline và kiểm tra nhiều nguồn khi điều tra.

## 30. Azure Policy: ngăn drift chứ không chỉ phát hiện

**Azure Policy** có thể evaluate resource compliance và áp các effects theo policy definition/assignment, ví dụ **Audit, Deny, Modify, DeployIfNotExists** khi có hỗ trợ.

### 30.1. Audit khác Deny

- **Audit**: ghi/đánh giá một resource không tuân thủ, không tự ngăn thao tác.
- **Deny**: chặn những operation phù hợp điều kiện deny.
- **Modify/DeployIfNotExists**: có thể sửa/bổ sung cấu hình trong các điều kiện và identity/permission phù hợp.

### 30.2. Policy không thay IaC

Policy nói baseline chung như “không bật public blob access”; Bicep/Terraform nói resource cụ thể cần SKU, subnet, tags ra sao. Một Azure resource tuân thủ policy nhưng khác config IaC vẫn có thể drift.

### 30.3. Exemption là ngoại lệ có kiểm soát

Policy exemption cần lý do, owner, phạm vi, thời hạn và monitoring. Không exempt toàn subscription để CI deploy được một test resource mà không xác định root cause.

### 30.4. Modify effect có thể tạo thay đổi ngoài IaC

Nếu Azure Policy tự bổ sung tag hoặc setting, Terraform/Bicep có thể nhìn thấy khác biệt sau deploy. Phối hợp baseline IaC với policy effects, tránh vòng lặp ghi đè qua lại.

## 31. Azure Resource Graph và inventory tài nguyên chưa được quản lý

IaC drift detection có thể bỏ sót **unmanaged resources**. Azure Resource Graph hữu ích cho inventory xuyên subscriptions theo quyền, tags, types và resource IDs.

Ví dụ Azure Resource Graph KQL:

~~~kusto
Resources
| where type =~ 'microsoft.storage/storageaccounts'
| project id, name, resourceGroup, subscriptionId, location, tags
| order by subscriptionId asc, resourceGroup asc
~~~

### 31.1. Inventory chưa phải drift kết luận

Một Storage account không có tag managedBy có thể là legacy resource có owner, hoặc tag bị thiếu. Cần so sánh với CMDB/IaC ownership catalog và approved exceptions trước khi gọi là unmanaged.

### 31.2. Quy trình phát hiện unmanaged objects

1. Quét resources theo subscriptions/scope được cho phép.
2. Lấy id, type, RG, owner tags, create/update indicators khi có.
3. Đối soát với Git IaC resource declarations và Terraform state.
4. Điều tra resources không có owner, không tự xóa.
5. Quyết định import/adopt, chuyển ownership hoặc decommission có approval.
6. Theo dõi kết quả và ngân sách của unmanaged resources.

### 31.3. Resource Graph có thể không cung cấp mọi nested property

Khi cần xác minh firewall, diagnostic settings hoặc data-plane access, dùng đúng Azure resource provider API/dedicated diagnostics thay vì nghĩ một query Resources liệt kê hết.

## 32. RBAC và PIM: giảm out-of-band changes

**Microsoft Entra ID** và **Azure RBAC** quyết định ai có thể quản trị resources ở subscription/resource group/resource scopes. **Privileged Identity Management (PIM)** giúp quản lý privileged activation theo tổ chức/tính năng được cấp phép.

### 32.1. Phân quyền vai trò

| Vai trò | Quyền phù hợp | Không nên có mặc định |
|---|---|---|
| Developer | Dev/test deployment scoped; read diagnostics | Production Owner |
| SRE on-call | Đọc logs, quyền khẩn cấp có approval/PIM | Tự sửa prod vô hạn |
| Platform engineer | IaC/network/policy scoped | Data-plane business secrets không cần |
| Security engineer | Policy/RBAC review/incident response | Build artifact publisher không cần |
| CI/CD identity | Deploy đúng resources/stage | Owner toàn management group |
| Runtime managed identity | Data-plane permissions đúng workload | Resource Management Contributor |

### 32.2. Giảm quyền chỉnh tay trên production

Protected pipelines với service principals/managed identities riêng, approvals và audit trail làm thay đổi production truy vết tốt hơn. Có thể cần break-glass path trong sự cố, nhưng phải giới hạn thời gian, ghi lý do và reconcile IaC.

### 32.3. Tách quyền tạo role assignments

Một CI job deploy Container App không nhất thiết cần quyền gán quyền IAM. Nếu pipeline vừa build code vừa tự cấp Owner cho mình, rủi ro supply-chain escalation tăng mạnh.

### 32.4. Data-plane RBAC khác management-plane

Được quyền sửa Storage account ARM properties không tự cấp quyền đọc mọi blob. Ngược lại, có data-plane Reader không tự cho quyền thay firewall/policy.

## 33. Azure Resource Locks: tránh xóa nhầm

Azure Resource Manager có cơ chế **resource locks** như **CanNotDelete** hoặc **ReadOnly** ở scopes hỗ trợ.

### 33.1. CanNotDelete giúp gì?

Giảm khả năng xóa resources ngoài ý muốn, kể cả trong một số tình huống pipeline có quyền ghi. Nhưng người có quyền quản lý lock phù hợp có thể thay lock; đây không phải security perimeter độc lập.

### 33.2. ReadOnly có thể phá hoạt động quản trị hợp lệ

Một số dịch vụ thực hiện operations ghi ở management plane ngay cả khi người dùng nghĩ là “đọc” hoặc muốn duy trì hoạt động. Áp ReadOnly lock tùy tiện có thể làm deployment/backup/integration lỗi.

### 33.3. Locks không thay backups

Khóa xóa không bảo vệ khỏi mọi hỏng dữ liệu hoặc thay đổi data-plane. Cần backup/restore tests, versioning/immutability theo service và DR plan.

### 33.4. IaC thay resource có lock

Nếu plan có destroy/recreate với resource đang khóa, apply có thể fail; **không gỡ lock và bấm apply lại theo phản xạ**. Review vì sao muốn replace, bảo vệ dữ liệu và duyệt migration.

## 34. Change control: ai được thay cái gì, lúc nào?

Một yêu cầu thay đổi IaC nên có:

~~~text
Change ID:
Resource / subscription / RG:
IaC repository + commit:
Reason / business impact:
Expected plan (create, update, replace, delete):
Security/network/RBAC implications:
Data loss and backup assessment:
Cost/quota implications:
Approvers and maintenance window:
Verification / success criteria:
Rollback or forward-fix plan:
Owner / due date:
~~~

### 34.1. Risk-based approvals

- **Low:** thay tag ít tác động, có tests/auto approval nếu policy cho phép.
- **Medium:** đổi SKU, service settings, scaling có budget impact.
- **High:** mở public access, IAM privileged, database replacement, xóa resource hoặc DR change.

### 34.2. Review kế hoạch trước apply

Một plan chỉ chứa vài dòng có thể thay public access hoặc xóa toàn bộ dữ liệu. Điều quan trọng là **semantic change**, scope và blast radius, không phải số dòng diff.

### 34.3. Approval không đồng nghĩa mọi apply sẽ giống plan

Nếu giữa lúc duyệt và apply Azure actual state hoặc Git source thay đổi, plan/what-if có thể stale. Cần revalidation hoặc apply chính xác saved artifact ở phiên bản/provider phù hợp và kiểm soát thời gian giữa plan–apply.

### 34.4. Đóng vòng thay đổi

Sau apply, đọc lại resource properties, kiểm tra metrics/health/security controls, lưu deployment ID và theo dõi có tiếp tục drift không.

## 35. Protected CI/CD pipeline cho drift detection

Một kiến trúc:

~~~mermaid
flowchart LR
    SCHED[Scheduled drift scan] --> READ[Read-only Azure identity / state]
    READ --> PLAN[Terraform plan / Bicep what-if]
    PLAN --> REPORT[Redacted diff + severity]
    REPORT --> APPROVE{Reviewed and approved?}
    APPROVE -- No --> TICKET[Ticket and investigation]
    APPROVE -- Yes --> APPLY[Protected apply identity]
    APPLY --> VERIFY[Resource readback + smoke/security checks]
    VERIFY --> AUDIT[Change record / alert]
~~~

### 35.1. Tách scan job và apply job

Scan cần read/plan permissions phù hợp, **không tự có quyền production write** nếu không cần. Apply chạy với identity khác tại protected environment, có reviewer phù hợp.

### 35.2. Scheduled scan cadence

Tùy rủi ro, có thể chạy hàng ngày cho production security-critical IaC, mỗi tuần với môi trường ít thay đổi, và ngay sau emergency change. Cadence là quyết định theo policy/SLO; không có một chu kỳ đúng cho tất cả.

### 35.3. Báo cáo không chứa state/secret

Chỉ xuất summary, resource IDs đã được kiểm soát quyền, change types, severity, tool versions và links tới private run artifacts. Không upload raw Terraform plan/state vào public tickets.

### 35.4. Không biến drift thành alert noise

Có owner, dedup key, severity, suppression có hết hạn và cảnh báo khi scan bị lỗi. Một lần plan exit 1 phải báo “scan failed”, không thông báo “no drift”.

## 36. Drift scan output có cấu trúc và audit

Một báo cáo mẫu:

~~~json
{
  "environment": "production",
  "subscription": "SUBSCRIPTION_ID",
  "iacCommit": "COMMIT_SHA",
  "stack": "orders-platform",
  "tool": "terraform",
  "scanStatus": "DIFFERENCES_FOUND",
  "scannedAtUtc": "2026-11-20T10:00:00Z",
  "counts": {
    "update": 2,
    "replace": 0,
    "delete": 0
  },
  "highestSeverity": "HIGH",
  "reviewRequired": true
}
~~~

Đây là **schema ví dụ**, không phải native JSON output được bảo đảm của Azure/Terraform. Report generator phải đọc plan đúng, redact secrets và map counts/risks theo rules của tổ chức.

### 36.1. Không lưu secret trong resource detail

Terraform JSON plan có thể chứa sensitive sections. Chỉ cho trusted parser đọc, không đưa raw output vào Slack/issue công khai.

### 36.2. Gắn báo cáo với code và environment

Commit hash, resource group, subscription, tool/provider versions và plan run ID giúp người điều tra phân biệt thay đổi hợp pháp trong Git với drift ngoài Git.

### 36.3. Lưu clean scan cũng hữu ích

Báo cáo “no changes” theo định kỳ có thể chứng minh pipeline quan sát đang chạy. Nhưng vẫn cần cảnh báo nếu scan bị tắt nhiều ngày hoặc mất quyền Azure.

## 37. Policy trong pipeline: chặn các thay đổi phá dữ liệu

Đề xuất các quy tắc trước production apply:

- Block destroy/replace cho production database/storage nếu không có explicit data-impact approval.
- Block mở public network access hoặc anonymous blob access không hợp lệ.
- Block privileged role assignments không có security approval.
- Block xóa diagnostics, alerts hoặc backup policies quan trọng.
- Block region, SKU hoặc tags ngoài Azure Policy baseline.
- Require import/ownership review khi adopt existing resources.
- Require plan refresh nếu quá nhiều thời gian hoặc infrastructure đã đổi từ lúc approve.
- Require smoke/readback after deploy.

### 37.1. Dùng policy-as-code khi phù hợp

OPA/Rego, Terraform policy tooling hoặc kiểm tra JSON plan tùy platform là các cách triển khai custom gate. Azure Policy giúp enforce một số điều kiện tại control plane; kết hợp thay vì tin một tool duy nhất.

### 37.2. Tránh false confidence

Policy parser có thể hiểu sai unknown values, module boundaries hoặc API provider semantics. Kiểm tra regression tests cho policy và manual review đối với high-risk planned replacements.

### 37.3. Cách xử lý trường hợp ngoại lệ

Ghi change ID, risk acceptance, compensating controls, owner, expiry và rollback plan. Không dùng “skip all policies” không giới hạn để chạy production.
## 38. Runbook: Terraform plan muốn thay thế database production

**Tình huống:** một pull request chỉ đổi tags nhưng Terraform plan của Azure SQL hoặc Storage hiển thị **-/+ replacement**.

### Bước 1 — Dừng apply

Không merge hoặc chạy apply trước khi phân tích. Nếu là production, yêu cầu thêm approval từ resource owner/data team. Không gỡ resource lock để “cho job chạy”.

### Bước 2 — Xác minh đúng environment

Kiểm tra subscription ID, RG, Terraform backend key, workspace/stack, provider configuration, module address và CI identity.

### Bước 3 — Xem nguyên nhân thay thế

Trong plan, field nào **forces replacement**? Có location, name, resource group, subnet, SKU, storage account type hoặc property immutable thay đổi không? Đọc provider/service-specific implications.

### Bước 4 — Xem state mapping

So **terraform state show** với Azure resource ID thực. Resource address có bị đổi mà thiếu moved block? Có import nhầm object ở subscription khác không? Có thay provider version không?

### Bước 5 — Kiểm tra dữ liệu và dependencies

Chụp data/backup/restore posture theo chính sách. Xem Private Endpoint, DNS, apps đang sử dụng, database clients, Key Vault references và RPO/RTO.

### Bước 6 — Chọn hướng sửa

- Nếu sai IaC config: sửa lại baseline và chạy plan.
- Nếu refactor address: dùng moved block/state migration thích hợp.
- Nếu một thay đổi chủ đích bắt buộc replacement: thiết kế migration song song, data copy/sync, cutover và rollback.
- Nếu phải import lại: review resource ownership và state; không xóa state tùy tiện.

### Bước 7 — Review plan mới

Xác nhận chỉ còn thay đổi cho phép, không có xóa/recreate ngoài ý muốn; đính kèm plan summary/approval, không đính kèm secrets.

### Bước 8 — Apply có kiểm soát và validate

Theo maintenance/change window; verify resource IDs, app connections, health, logs/alerts, dữ liệu, billing và drift scan sau đó.

## 39. Runbook: Portal hotfix tạo drift ngoài Git

**Tình huống:** trong incident, on-call sửa Azure firewall hoặc tăng VM size trực tiếp. Sau đó Terraform/Bicep báo drift.

### Bước 1 — Ghi nhận thay đổi

Tập hợp incident ID, timestamp UTC, người thực hiện/principal, resource ID, property trước/sau, lý do và tác động.

### Bước 2 — Xác định thay đổi có còn cần thiết?

Một hotfix chỉ cần 30 phút có thể trả về baseline. Một thay đổi cần giữ lâu có thể yêu cầu IaC cập nhật và review mới.

### Bước 3 — Đối chiếu policy/security

Firewall có mở public access không? Key Vault/Storage diagnostics có bị tắt không? Role assignments có quá rộng? Nếu rủi ro cấp cao, kích hoạt incident/security process chứ không chỉ sửa tag.

### Bước 4 — Đọc diff từ IaC

Chạy what-if/plan ở đúng scope. Kiểm tra những changes khác có thể xuất hiện đồng thời, không chỉ property hotfix.

### Bước 5 — Chọn hướng reconcile

- **Revert Azure về Git:** apply baseline nếu an toàn.
- **Backport Azure thay đổi vào Git:** tạo PR, test/approve rồi apply để xác nhận desired state.
- **Temporary exception:** ghi expiry, owner và scan/alert.

### Bước 6 — Đóng incident

Readback properties, validate network/service SLO, xác nhận drift cleared hoặc exception tracked; không dừng ở “terraform plan code 0” nếu logs/health chưa kiểm tra.

## 40. Runbook: import nhầm resource hoặc state backend

**Tình huống:** sau terraform import, plan thấy resource ở subscription khác hoặc muốn delete object mới.

### Bước 1 — Đừng chạy apply

Có thể là sai ARM ID, sai provider alias, wrong resource address hoặc backend key không đúng.

### Bước 2 — Freeze writes

Dừng mọi Terraform applies liên quan để không có race condition. Xác định người đang giữ state lock.

### Bước 3 — Snapshot và kiểm tra

Lấy backup state từ backend theo chính sách. Đọc config address, state list/show, ARM ID, provider/subscription. Không in secrets ra chat/ticket.

### Bước 4 — Xác định mapping thực

Một address chỉ nên track object intended. Nếu wrong object đã được đưa vào state, cần migration/removed ownership procedure có review, không tự xóa object Azure.

### Bước 5 — Sửa kế hoạch

Điều chỉnh import target/address/ID, module references, role/scope; có thể cần import lại theo quy trình. Chạy plan và kiểm tra không có unexpected destroy/recreate.

### Bước 6 — Readback

Kiểm tra state và resource Azure cùng trỏ đúng ID; nguồn quản lý cũ không còn tiếp tục apply. Chạy policy/health tests trước khi giải phóng freeze.

### Bước 7 — Khắc phục nguyên nhân

Thêm kiểm tra subscription/backend key/ARM ID trong pipeline, import block được review, identity limited scope và runbook cho state operations.

## 41. Chi phí, quota và hiệu năng của drift detection

Một hệ thống drift scan cũng có chi phí vận hành:

- CI runners/agents khi chạy kế hoạch định kỳ.
- Azure API requests, Resource Graph inventory và diagnostics.
- Storage backend cho Terraform state/versioning/backup.
- Log Analytics ingestion/retention và ticket/alert integrations.
- Thời gian review của engineers.
- Thay đổi resource do remediation: SKU, network, backup, logging có thể làm thay bill.

### 41.1. Drift scan không cần scale bằng số Pod

Quét IaC ở subscription/resource scope, không chạy một scan riêng mỗi AKS Pod. Scope chiến lược là module/stack/environment cùng resource ownership.

### 41.2. Cảnh báo quan trọng hơn số lần quét

Một hourly scan tạo 10.000 tickets duplicate có thể làm SRE bỏ qua sự cố thật. Chọn cadence theo mức độ nguy hiểm, dedup, risk classification và thông báo khi scan failed.

### 41.3. Cost drift là trường hợp quan trọng

Một người đổi SKU, bật multi-region replication hoặc quên xóa preview resources có thể tăng chi phí không nằm trong IaC baseline. Kết hợp **Azure Cost Management budgets/alerts**, tag ownership và resource inventory.

### 41.4. Drift diff không phải hóa đơn

What-if/plan dự đoán config changes, không tự cung cấp báo giá chính xác. Để ước lượng cần pricing calculator, usage baselines, billing scopes và service-specific cost impacts.

## 42. Kiểm thử change control: happy path và failure path

Hệ thống IaC không chỉ cần chứng minh deploy thành công; cần chứng minh **deploy không hợp lệ bị chặn**.

| Test | Mong đợi |
|---|---|
| PR đổi tag ở nonprod | Plan được review, apply đúng scope |
| PR mở public blob access | Policy/security gate chặn hoặc đòi approved exception |
| PR xóa production database | Block destructive change đến khi có data impact plan |
| Drift scan khi Azure không thể truy cập | Scan FAILED, không báo no drift |
| Terraform plan exit code 2 | Tạo report khác biệt, không tự apply |
| Terraform backend lock active | Job chờ/fail có thông báo; không force-unlock |
| Import sai ARM ID | Dừng trước apply, xem state và resource mapping |
| Unmanaged resource mới | Inventory phát hiện và tạo ownership ticket |
| Emergency Portal change | Incident + drift review + backport/revert |
| Azure Policy Modify thay tag | Tìm nguồn policy, xử lý baseline |
| Sửa code giữa plan và apply | Replan/re-approval theo policy |
| Runtime app unhealthy sau IaC | Dừng rollout/rollback hoặc forward-fix |

### 42.1. Test trong lab, không diễn tập phá prod

Muốn thử force replacement, sử dụng một resource lab không chứa dữ liệu thật, hoặc mock policy parser bằng plan JSON fixture. Đừng gây downtime production chỉ để xác minh gate.

### 42.2. Logs và metadata dùng để chứng minh

Ghi test run ID, resource ID, plan summary, approval/no-approval và final state. Không cần xuất toàn bộ state/secret values thành báo cáo.
## 43. Lab 1: phát hiện Bicep drift bằng what-if

**Chỉ làm trên Azure subscription/resource group lab của chính bạn.** Bài thực hành không yêu cầu hoặc cho phép sửa hạ tầng production.

### A. Chuẩn bị

1. Chọn subscription lab và xác nhận bằng **az account show**.
2. Tạo resource group riêng, ví dụ **rg-iac-drift-lab**.
3. Chuẩn bị Bicep template tương tự mục 11.
4. Chọn Storage name hợp lệ, duy nhất và có thể dọn sau lab.
5. Chọn role/identity có quyền deploy đúng RG lab.
6. Đảm bảo không có dữ liệu nghiệp vụ thật trong Storage.

### B. Thiết lập baseline

Trong thư mục chứa **main.bicep** thực do bạn tạo cho lab:

~~~bash
RG='rg-iac-drift-lab'
STORAGE='replacewithuniquelabname'

az account show --query '{id:id,name:name}' -o table

az deployment group what-if \
  --resource-group "$RG" \
  --template-file main.bicep \
  --parameters storageAccountName="$STORAGE"

# Chỉ sau review và xác nhận resource lab:
az deployment group create \
  --resource-group "$RG" \
  --template-file main.bicep \
  --parameters storageAccountName="$STORAGE"
~~~

**Không chạy khối lệnh nếu RG/Storage chưa được xác nhận thuộc lab**. Bicep không được tạo trong repository của bài học này; các lệnh là hướng dẫn cho project thực hành của học viên.

### C. Tạo một thay đổi ngoài IaC ít rủi ro

Trong Azure Portal, chỉ thay **tag environment** trên đúng Storage account lab từ **dev** thành **manual-test**. Không bật public access, không xóa resource, không đổi network firewall hoặc encryption để thử drift.

### D. Phát hiện

Chạy lại **az deployment group what-if** cùng inputs, quan sát tag diff và resource ID. Ghi:

| Thuộc tính | Mong đợi |
|---|---|
| Subscription/RG | Trùng môi trường lab |
| Resource ID | Storage lab chính xác |
| Current tag | manual-test |
| Desired tag | dev |
| Planned change | Cập nhật tag về baseline |
| Rủi ro | Low, không có delete/replace |
| Review | Chấp thuận revert hoặc sửa code với lý do |

### E. Reconcile

Sau approval lab, chạy deployment để khôi phục tag baseline (hoặc cập nhật template nếu thay đổi hợp lệ). Đọc lại actual tags trong Portal/Azure CLI, sau đó what-if để xác minh không còn diff dự kiến.

### F. Cleanup

Xóa các tài nguyên **chỉ khi đã xác minh là lab độc lập và được phép xóa**. Không dùng wildcard xóa nhiều resource groups, không xóa cả resource group shared.

### G. Tiêu chí đạt

Bạn chỉ rõ vì sao Bicep **existing** không tự quản lý tags, what-if là dự đoán trước apply và việc thay đổi tag phải được phân loại/duyệt thay vì tự sửa production.

## 44. Lab 2: import Resource Group đã tồn tại vào Terraform

### A. Tình huống

Một resource group **rg-iac-drift-lab** do Portal tạo trước. Nhóm chuyển quyền quản lý RG sang Terraform nhưng phải giữ nguyên resource ID và không phá các resource bên trong.

### B. Preflight

1. Xác nhận RG thuộc subscription lab bằng Azure CLI/Portal.
2. Ghi ARM resource ID đầy đủ.
3. Đảm bảo state backend/stack khác không đang quản lý RG.
4. Chọn resource address **azurerm_resource_group.lab**.
5. Tạo Terraform configuration hợp lệ cho provider, RG name/location và tags.
6. Xác minh quyền đọc Azure, quyền backend và locking.
7. Snapshot state nếu đây là backend đã có resources khác.

### C. CLI import

Chạy trong project Terraform lab đã được cấu hình:

~~~bash
terraform init
terraform fmt -check
terraform validate

terraform import \
  azurerm_resource_group.lab \
  "/subscriptions/SUBSCRIPTION_ID/resourceGroups/rg-iac-drift-lab"

terraform state list
terraform state show azurerm_resource_group.lab
terraform plan
~~~

### D. Review sau import

Nếu RG thực có **tags khác config**, plan có thể báo update; đây là thay đổi cần review, không phải bằng chứng import thất bại. Nếu plan dự đoán **replace/delete**, dừng và kiểm tra resource address, ID, provider alias, location/config.

### E. Cách khác: import block

Thay vì CLI import, có thể định nghĩa **import block** như mục 23 trong một branch được review rồi chạy plan/apply đúng workflow. **Không chạy cả hai phương pháp liên tiếp cho cùng address** nếu đối tượng đã được import thành công.

### F. Kết quả mong đợi

| Kiểm tra | Phải xác nhận |
|---|---|
| Azure resource ID | Không thay đổi |
| Terraform resource address | Trỏ đúng RG |
| State backend | Đúng project/env |
| Second owner | Không có |
| Unexpected replacement | Không |
| Drift assessment | Chỉ những diff có thể giải thích |
| Approval | Có record trước apply |

### G. Tiêu chí đạt

Import thành công **không** có nghĩa config hoàn chỉnh. Người học phải chứng minh sau import, Terraform state, code và Azure actual được đối soát; không có hướng dẫn xóa dữ liệu hay tạo lại RG.

## 45. Lab 3: chuyển Terraform resource address bằng moved block

### A. Tình huống

Terraform state đã quản lý một resource **azurerm_resource_group.lab**. Nhóm đổi kiến trúc module và muốn address mới **module.foundation.azurerm_resource_group.this** nhưng không đổi RG trên Azure.

### B. Các bước

1. Tạo module foundation với resource RG tương đương.
2. Chuyển cấu hình RG từ root module vào child module.
3. Viết **moved block** đúng old/new addresses, tương tự mục 26.
4. Chạy **terraform fmt**, **terraform validate** và **terraform plan**.
5. Kiểm tra plan thể hiện resource move theo version/tool support, **không destroy/create** RG.
6. Review provider configurations/module parameters.
7. Chỉ apply sau khi được duyệt trên lab.
8. Readback state list và Azure RG ID.

### C. Trường hợp thất bại

Nếu plan dự đoán destroy/create, kiểm tra moved block, provider alias, module resource type, for_each/count addresses và configuration mismatches; không apply để “xem có sao không”.

### D. Bài học

Refactor trong Terraform code có thể thay **logical address** nhưng không bắt buộc thay **Azure resource ID**. Moved block thể hiện ý định migration; import dùng khi resource chưa thuộc state này.

## 46. Lab 4: xây drift scan và change gate trên CI

**Mục tiêu:** lập pipeline kiểm tra differences mà không cấp quyền apply production cho PR jobs.

### A. Thiết kế pipeline

~~~text
Scheduled trigger / protected PR
      |
Checkout approved IaC commit
      |
Authenticate read-only identity
      |
Validate source / provider versions
      |
Terraform plan -detailed-exitcode
  or ARM/Bicep what-if
      |
Parse/redact findings
      |
Classify high-risk changes
      |
Open private report / approval
      |
Protected apply job (separate identity)
      |
Readback + smoke/security checks
~~~

### B. Tập test cases

- Clean plan → scan success, no diff.
- Plan returns 2 → diff report, not auto apply.
- Plan returns 1 → scanner error, incident/report.
- High-risk delete → blocked until explicit approval.
- Unknown plan attributes → flagged for review, not silently ignored.
- Backend locked by another job → no force-unlock.
- Wrong subscription in env variables → fail fast before any write.
- Resource created ngoài IaC → inventory reconciliation ticket.
- Scheduled job stopped → monitoring detects missing scan.

### C. Báo cáo kết quả

| Input | Kỳ vọng |
|---|---|
| Git commit hash | Traceable |
| Subscription/RG | Explicit, verified |
| Terraform/provider/CLI versions | Recorded |
| Plan status | Clean / difference / error |
| Diff summary | Sanitized |
| Risk score | Derived from approved policy |
| Approver | Named role/change record |
| Apply status | Protected, separate identity |
| Post-apply verification | Azure state + application health |

### D. Tiêu chí đạt

Pipeline không tiết lộ state/secret; unauthenticated/untrusted jobs không thể apply; scan error không bị báo là môi trường sạch; review tập trung vào destructive/security-impacting changes.

## 47. Case study: import một Storage production do người dùng tạo

Giả sử một Storage account chứa dữ liệu thật được tạo trong Portal, có private endpoints, soft delete, backup, diagnostic settings và SAS consumers. Team quyết định chuyển vào IaC.

### 47.1. Những điều không nên làm

- Copy toàn bộ ARM export rồi apply không review.
- Thấy Terraform plan **-/+** nhưng vẫn approve vì “đang chuyển sang IaC”.
- Dùng **terraform state rm** để bỏ qua lỗi.
- Gỡ CanNotDelete lock chỉ để bước deploy xanh.
- Tắt firewall hoặc đưa account key vào Git để build pass.
- Vừa nhập object vào Terraform vừa để Bicep stack cũ tiếp tục quản lý cùng resource.
- Coi việc import thành công là đã kiểm chứng backup/retention/network.
- Chạy lab hoặc migration trên tài nguyên có dữ liệu người dùng mà không có change approval.

### 47.2. Quy trình nên làm

1. Lập inventory và owner/source-of-truth catalog.
2. Đọc ARM resource ID, config, tags, network, encryption, backup, auth, RBAC và dependencies.
3. Quyết định IaC engine/state/module/identity quản lý.
4. Chụp backup/state snapshot theo chính sách.
5. Viết config nhất quán với actual state, đồng thời ghi nhận security gaps.
6. Chạy what-if/plan/import block trên protected workflow.
7. Review mọi create/replace/delete và unknown diff.
8. Adopt theo quy trình; không đồng thời thay security properties lớn trong cùng bước nếu làm khó rollback.
9. Readback và kiểm tra apps/Storage operations, logs, private DNS, costs.
10. Mở PR tiếp theo sửa những drift/security gaps được phê duyệt.
11. Bật periodic detection, restrict manual write access và ghi ownership.
12. Kiểm chứng backup/restore và change-control documentation.

### 47.3. Vì sao adoption và remediation nên tách?

Tách hai thay đổi giúp xác định lỗi phát sinh do state/resource ownership hay do cấu hình bảo mật mới. Với production, việc thay đồng thời state, network, identity và SKU có thể làm root cause khó truy vết.

### 47.4. Tiêu chí thành công

Sau adoption, một owner IaC rõ, mọi diff được giải thích, không có unexpected resource replacement, ứng dụng vẫn truy cập qua private path, dữ liệu không mất và các thay đổi mới đi qua review/CI.
## 48. Checklist production: drift, import và change control

- [ ] Mỗi resource/stack có owner và nguồn sự thật IaC xác định.
- [ ] Đã kiểm tra không có hai IaC stacks cùng ghi một Azure resource.
- [ ] Subscription ID, RG, tenant và resource ID được xác minh trước scan/apply.
- [ ] CI scan và apply jobs có identities/scopes riêng.
- [ ] Không cấp Azure Owner toàn subscription cho job chỉ cần deploy app.
- [ ] Terraform backend state có encryption, RBAC, backup, versioning theo policy.
- [ ] State locking hoạt động; không tắt lock hoặc force-unlock tùy tiện.
- [ ] State files, saved plans và build logs không lộ secrets.
- [ ] Bicep/ARM what-if chạy trước thay đổi đáng kể.
- [ ] Terraform plan chạy với provider/toolchain versions được kiểm soát.
- [ ] Plan exit code 1 được xử lý là error, không phải no drift.
- [ ] Plan code 2 được đưa vào review/risk classification, không tự apply.
- [ ] Đã phân biệt regular plan với refresh-only plan.
- [ ] Không dùng -refresh=false để ẩn drift.
- [ ] Không dùng apply -refresh-only để mặc nhiên hợp thức hóa thay đổi remote.
- [ ] Mọi diff replace/delete có data impact assessment và owner approval.
- [ ] Database/Storage stateful resources có backup/restore plan trước migration.
- [ ] Không gỡ resource lock chỉ để pipeline chạy xanh.
- [ ] Bicep existing chỉ dùng reference, không được ghi nhận sai là full adoption.
- [ ] Adoption Bicep có resource ID/scope/API đúng và what-if readback.
- [ ] Terraform import có đúng ARM ID, resource address, provider và backend.
- [ ] Sau import luôn chạy state list/show và full terraform plan.
- [ ] Không import object đã thuộc state/stack khác mà chưa chuyển ownership.
- [ ] Refactor Terraform address dùng moved block/state migration thích hợp.
- [ ] Không dùng state rm để sửa drift khi không hiểu hệ quả.
- [ ] IaC code có parameters nonsecret và Azure security baseline.
- [ ] Unmanaged resources được inventory qua Azure Resource Graph hoặc CMDB.
- [ ] Azure Activity Log/Policy records được dùng để phân tích nguyên nhân.
- [ ] Có policy guardrail cho public access, network, IAM và diagnostics.
- [ ] Azure Policy exceptions có owner, expiry và audit trail.
- [ ] PIM/break-glass privileges được giới hạn và xem xét sau incident.
- [ ] PR có CODEOWNERS/reviewers và tests/policy checks.
- [ ] Prod apply có protected environment, scope chính xác và approvals.
- [ ] Plan/source được tái kiểm tra nếu thay đổi sau khi duyệt.
- [ ] Drift scan có lịch, owner, báo cáo và alert khi scan không chạy.
- [ ] False positives/known exceptions được kiểm soát, không suppress vô hạn.
- [ ] Có phân loại severity theo security/data/cost impact.
- [ ] Diff reports có commit, provider version, timestamp và resource IDs.
- [ ] Không export raw state/secret vào ticket/Slack/public CI artifacts.
- [ ] Emergency Portal changes có incident record và backport/revert plan.
- [ ] Sau apply có readback actual Azure properties và smoke tests.
- [ ] Có monitoring cho data-plane, application health và cost changes.
- [ ] Quy trình cleanup chỉ xóa đúng lab/preview resources được cho phép.
- [ ] Có runbook khi import nhầm state, wrong subscription hoặc planned replacement.
- [ ] Đã thử recovery/rollback hoặc forward-fix trên môi trường phù hợp.
- [ ] Có lịch review IaC ownership, access permissions và drift exceptions.

## 49. Câu hỏi tự kiểm tra

1. Desired state, actual state và Terraform state khác nhau ở điểm gì?
2. Vì sao một resource không nằm trong IaC có thể không hiện trong drift plan?
3. Manual drift khác out-of-band automation drift ra sao?
4. Computed/read-only properties gây plan noise như thế nào?
5. Azure Policy Modify có thể làm IaC và Azure khác nhau không?
6. “No changes” có bảo đảm cấu hình Azure hoàn toàn an toàn không?
7. Vì sao cần dùng full ARM resource ID khi import?
8. Bicep/ARM what-if dự đoán những gì và có giới hạn gì?
9. Bicep có Terraform-like state file riêng không?
10. Từ khóa Bicep existing có quản lý firewall và tags không?
11. Làm sao adopt một resource đã tồn tại vào Bicep?
12. Vì sao ARM export/decompile không tạo IaC production-ready ngay?
13. Incremental ARM deployment có tự xóa mọi resource vắng trong template không?
14. Khi Bicep what-if báo Delete, cần những kiểm tra gì?
15. Terraform address khác Azure ARM resource ID ở đâu?
16. Terraform plan +, ~, - và -/+ biểu thị gì?
17. Khi plan có 0 diff, có nghĩa tất cả resource đều được quản lý không?
18. Exit codes 0, 1, 2 của terraform plan -detailed-exitcode khác nhau thế nào?
19. Vì sao exit code 2 phải được xử lý riêng khi script dùng set -e?
20. terraform plan -refresh-only khác regular plan ra sao?
21. terraform apply -refresh-only có sửa Azure resource không?
22. Vì sao -refresh=false có thể che drift?
23. Terraform import có tự viết config đầy đủ không?
24. Sau import, tại sao Terraform vẫn có thể đề xuất replacement?
25. Import block có lợi thế audit/review gì so với CLI import?
26. Khi nào có thể dùng -generate-config-out?
27. Một resource có nên thuộc hai Terraform state độc lập không?
28. Terraform moved block khác import block như thế nào?
29. terraform state rm có trực tiếp xóa Azure resource không và rủi ro là gì?
30. Terraform state backend có thể chứa secrets không?
31. Vì sao cần locking khi có nhiều pipeline Terraform?
32. Tại sao một saved plan file không nên được public?
33. Azure Activity Log có thể giúp điều tra drift theo cách nào?
34. AzureActivity có ghi mọi thao tác data-plane của Azure SQL không?
35. Azure Resource Graph giúp tìm unmanaged resource như thế nào?
36. Azure Policy compliance khác IaC drift detection ở điểm gì?
37. Audit/Deny/Modify/DeployIfNotExists có mục đích khác nhau ra sao?
38. Azure Resource Lock có thay backup/restore plan không?
39. Khi nào nên dùng PIM/break-glass và xử lý sau incident thế nào?
40. Một CI plan job có cần quyền apply production không?
41. Vì sao một approved plan có thể stale trước khi apply?
42. Những changes nào phải chặn nếu thiếu data impact approval?
43. Nếu plan báo replace database khi PR chỉ đổi tag, cần làm gì?
44. Nếu nhập nhầm Resource Group vào state backend prod, bước đầu tiên là gì?
45. Khi nào backport manual hotfix vào Git và khi nào revert về baseline?
46. Làm sao kiểm tra một drift scan thật sự hoạt động đều?
47. Vì sao cost drift không luôn lộ ra ở một code diff nhỏ?
48. Cách ngăn pipeline auto-remediation làm tăng blast radius là gì?
49. Sau khi apply hết drift, cần xác minh gì ngoài plan clean?
50. Thế nào là kiểm soát thay đổi IaC hoàn chỉnh?

## 50. Tổng kết

**Phát hiện drift, import tài nguyên và kiểm soát thay đổi** là ba hoạt động gắn chặt với nhau trong việc quản trị hạ tầng Azure bằng mã. Drift detection so sánh **baseline được phê duyệt** với **tài nguyên Azure thực tế** theo phạm vi và giới hạn công cụ; không phải mọi diff đều là lỗi, nhưng những thay đổi ảnh hưởng **network exposure, IAM, dữ liệu, backup, logging và chi phí** phải được đánh giá theo rủi ro.

Với **Bicep/ARM**, dùng **what-if** để dự đoán deployment changes; từ khóa **existing** chỉ tạo reference, còn đưa một resource có sẵn vào quản lý yêu cầu khai báo đúng resource, đối chiếu configuration và deploy có review. Với **Terraform**, cần hiểu cấu hình, state và remote object: **plan**, **refresh-only**, **import**, **import blocks**, **moved blocks** và backend locking nhằm duy trì mapping đáng tin mà không vô tình destroy/recreate tài nguyên đang có dữ liệu.

Một quy trình production tốt không tự sửa mọi khác biệt. Nó sử dụng **source of truth và ownership rõ, Entra RBAC/PIM, Azure Policy, protected CI/CD, đánh giá plan, approvals, audit trail, readback/health checks, cùng runbook rollback hoặc forward-fix**. Kết hợp Azure Monitor, Activity Log, Resource Graph và Cost Management giúp phát hiện thay đổi ngoài ý muốn, xác định nguyên nhân và bảo vệ một kiến trúc Azure có thể tái lập, an toàn và kiểm soát được chi phí.







