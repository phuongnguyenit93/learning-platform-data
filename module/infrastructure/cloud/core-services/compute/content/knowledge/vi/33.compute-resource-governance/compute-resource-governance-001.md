# Quy ước đặt tên, tag và xác định chủ sở hữu workload

Một nền tảng compute có thể chứa hàng trăm ứng dụng, hàng nghìn máy ảo, container, volume, network interface, function và tài nguyên dùng chung. Khi tên tài nguyên không nhất quán, tag thiếu hoặc không rõ ai chịu trách nhiệm, đội vận hành khó tìm đúng workload, đội bảo mật khó liên hệ owner khi phát hiện rủi ro và bộ phận tài chính khó phân bổ chi phí.

Quy ước đặt tên, tag và ownership tạo ra một ngôn ngữ chung để nhận diện tài nguyên trong cloud, data center và edge. Tên giúp con người đọc và tìm tài nguyên; tag bổ sung metadata có thể lọc, tự động hóa và phân bổ; ownership xác định ai chịu trách nhiệm về mục đích, vận hành, bảo mật và chi phí. Ba yếu tố cần được thiết kế cùng nhau và áp dụng nhất quán từ lúc tạo workload tới khi ngừng sử dụng.

## 1. Vì sao cần quản trị tên, tag và ownership?

Nếu một VM chỉ có tên `vm-01`, người vận hành khó biết nó thuộc ứng dụng nào, môi trường nào hoặc có thể dừng được hay không. Nếu VM có tag `application=orders`, `environment=production`, `owner=platform-team`, `cost-center=CC-420` và tên theo quy ước, thông tin cần thiết có thể được tìm thấy nhanh hơn.

Quản trị metadata giúp:

- **Inventory:** tìm và nhóm tài nguyên theo workload, môi trường, region, site hoặc nhóm vận hành.
- **Cost allocation:** phân bổ compute, storage, network và managed service cho sản phẩm hoặc cost center.
- **Incident response:** xác định owner, mức độ quan trọng và kênh liên hệ khi có sự cố.
- **Security governance:** tìm tài nguyên chứa dữ liệu nhạy cảm, thuộc phạm vi kiểm soát hoặc chưa có owner.
- **Automation:** áp dụng backup, patch, monitoring, shutdown schedule và policy theo tag.
- **Lifecycle management:** xác định tài nguyên tạm thời, ngày hết hạn và điều kiện decommission.
- **Compliance/audit:** chứng minh tài nguyên có mục đích, người chịu trách nhiệm và cấu hình quản trị phù hợp.

Tên và tag không tự tạo ra bảo mật hoặc quyền sở hữu pháp lý. Chúng là metadata hỗ trợ quy trình và công cụ; phải kết hợp IAM, policy, inventory, CMDB hoặc service catalog và cơ chế xác minh thực tế.

## 2. Phân biệt tên tài nguyên, tag và owner

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Resource name | Đây là tài nguyên nào, có vai trò gì? | `acme-prod-ap-southeast1-orders-api-vm-01` |
| Tag/label | Tài nguyên có thuộc tính hoặc phân loại nào? | `environment=prod`, `service=orders`, `criticality=high` |
| Owner | Ai chịu trách nhiệm cho workload và quyết định liên quan? | `team-commerce-platform`, `orders-service-owner` |
| Provider resource ID | Nền tảng định danh tài nguyên nào? | ID/ARN/resource URI do provider cấp |
| Service catalog/CMDB record | Workload được quản lý và liên kết với hệ thống nào? | Service ID, repo, runbook, SLO và dependency |

Không dùng tên hiển thị thay cho provider ID. Tên có thể được đổi hoặc trùng trong phạm vi khác nhau; provider ID thường là định danh kỹ thuật ổn định hơn trong phạm vi dịch vụ. Cũng không nên đặt tên người làm owner, vì nhân sự thay đổi và tên tài nguyên không nên phải sửa mỗi khi đổi người phụ trách.

## 3. Nguyên tắc thiết kế quy ước đặt tên

Một naming convention tốt cần dễ đọc, nhất quán, có thể kiểm tra tự động và phù hợp giới hạn của các nền tảng.

Các nguyên tắc chính:

1. **Có cấu trúc rõ:** các thành phần xuất hiện theo thứ tự thống nhất.
2. **Dùng từ vựng được chuẩn hóa:** tên môi trường, region, service và role lấy từ danh mục chung.
3. **Ngắn nhưng đủ nghĩa:** chỉ đưa thuộc tính cần để nhận diện; metadata chi tiết đặt trong tag.
4. **Không chứa bí mật:** không đưa password, token, thông tin cá nhân hoặc dữ liệu nhạy cảm vào tên.
5. **Ổn định theo vòng đời:** tránh nhúng thông tin dễ thay đổi như tên cá nhân, số ticket tạm hoặc ngày deploy vào tên tài nguyên lâu dài.
6. **Tương thích nền tảng:** tuân thủ giới hạn độ dài, ký tự, chữ hoa/thường và tính duy nhất của dịch vụ đích.
7. **Có thể tự động hóa:** naming validator có thể phân tích các segment và từ chối tên sai.
8. **Không giả định tên là duy nhất toàn cầu:** kiểm tra uniqueness trong phạm vi thực tế của dịch vụ, account, subscription, project hoặc region.

Nên chọn một chuẩn chữ thường, dùng dấu gạch ngang để phân tách segment khi dịch vụ hỗ trợ. Một số dịch vụ yêu cầu tên không có dấu gạch ngang, chỉ cho phép chữ-số hoặc bắt buộc duy nhất toàn cầu; khi đó cần adapter theo loại tài nguyên thay vì ép một biểu thức tên áp dụng cho mọi dịch vụ.

## 4. Mẫu cấu trúc tên workload và tài nguyên

Một mẫu tổng quát có thể là:

```text
<org>-<environment>-<location>-<workload>-<component>-<resource-role>-<sequence>
```

Ý nghĩa từng segment:

| Segment | Ví dụ | Mục đích |
|---|---|---|
| `org` | `acme` | Đơn vị hoặc tổ chức quản lý |
| `environment` | `prod`, `stg`, `dev`, `test` | Phân biệt môi trường |
| `location` | `apse1`, `dc01`, `plant07` | Region, data center hoặc site theo danh mục |
| `workload` | `orders`, `telemetry`, `billing` | Tên workload/service chuẩn hóa |
| `component` | `api`, `worker`, `db`, `cache` | Thành phần trong workload |
| `resource-role` | `vm`, `disk`, `lb`, `queue` | Loại/vai trò tài nguyên |
| `sequence` | `01`, `02` | Phân biệt các instance cùng vai trò |

Ví dụ:

```text
acme-prod-apse1-orders-api-vm-01
acme-prod-apse1-orders-worker-vm-02
acme-prod-apse1-orders-db-disk-01
acme-stg-apse1-orders-api-lb-01
acme-prod-plant07-telemetry-edge-gateway-03
```

Mẫu này là quy ước nội bộ minh họa, không phải cú pháp bắt buộc của cloud provider. Có thể bỏ segment không cần thiết hoặc rút ngắn mã location theo danh mục. Không đưa tất cả thuộc tính vào tên; owner, cost center, data classification, repo URL, expiry và business criticality nên nằm trong tag hoặc service catalog.

## 5. Danh mục giá trị chuẩn

Các segment chỉ hữu ích khi mọi đội dùng cùng từ vựng. Nên duy trì danh mục được phê duyệt cho:

- Environment: `prod`, `stg`, `dev`, `test`, `sandbox`, `dr`.
- Component: `api`, `web`, `worker`, `scheduler`, `batch`, `db`, `cache`, `gateway`.
- Resource role: `vm`, `node`, `disk`, `nic`, `lb`, `queue`, `bucket`, `function`.
- Location: mã region, data center, edge site và availability zone theo inventory.
- Organization/team: mã team hoặc business unit đã đăng ký.
- Workload/service: service ID hoặc slug duy nhất trong service catalog.

Tránh tạo nhiều biến thể cho cùng một ý nghĩa, ví dụ `production`, `prod`, `prd` và `live` cùng được dùng cho production. Chọn một giá trị chuẩn và có mapping khi tích hợp hệ thống cũ.

Các giá trị cần có mô tả và owner của taxonomy. Khi thêm environment hoặc location mới, cập nhật schema/validator trước khi cho phép pipeline tạo tài nguyên.

## 6. Giới hạn tên theo từng loại tài nguyên

Tên của VM, bucket, disk, network interface, DNS record và Kubernetes object có thể có giới hạn khác nhau. Một số dịch vụ yêu cầu tên duy nhất toàn cầu; một số chỉ yêu cầu duy nhất trong project hoặc resource group. Một số phân biệt chữ hoa/thường, số khác tự chuyển về chữ thường.

Trước khi áp dụng naming convention, cần lập bảng compatibility:

| Thuộc tính cần kiểm tra | Câu hỏi |
|---|---|
| Độ dài tối đa/tối thiểu | Mẫu tên có vượt giới hạn của loại tài nguyên không? |
| Ký tự hợp lệ | Có chấp nhận dấu gạch ngang, dấu chấm hoặc underscore không? |
| Chữ hoa/thường | Tên có phân biệt case không hay bị chuẩn hóa? |
| Phạm vi uniqueness | Duy nhất trong account, region, project hay toàn cầu? |
| Reserved word | Có từ khóa hoặc tiền tố bị cấm không? |
| Tên immutable | Có loại tài nguyên không cho đổi tên sau khi tạo không? |
| Tác động tới endpoint | Đổi tên có làm thay đổi DNS, URL, policy hoặc tham chiếu không? |

Không giả định có thể đổi tên mọi tài nguyên. Với resource name immutable, cần tạo tài nguyên mới, chuyển workload/dữ liệu và decommission tài nguyên cũ theo kế hoạch.

## 7. Tên ổn định và tên theo lần triển khai

Không phải mọi tài nguyên đều có cùng vòng đời.

- **Stable resource:** database, storage account, network, service endpoint có vòng đời dài; tên nên gắn với workload và vai trò ổn định.
- **Replica/instance:** VM hoặc worker node được thay thế thường xuyên; có thể dùng sequence hoặc ID ngắn.
- **Ephemeral resource:** build runner, task container, temporary disk hoặc job; có thể thêm run ID/time bucket nếu cần truy vết.
- **Release artifact:** image/package nên dùng version và digest thay vì đổi tên tài nguyên đang chạy.

Ví dụ, tên `acme-prod-apse1-orders-api-vm-01` có thể tồn tại qua nhiều lần deploy nếu VM ổn định. Nếu mỗi release tạo một VM mới, nên dùng deployment ID hoặc sequence có quy tắc thu hồi rõ ràng, không tái sử dụng tên theo cách làm nhầm lẫn lịch sử.

Timestamp trong tên có thể hữu ích cho artifact tạm nhưng thường không nên dùng cho tài nguyên lâu dài. Thời điểm tạo đã có trong metadata của provider; nếu cần lọc theo thời gian, dùng tag `created-at` hoặc inventory record.

## 8. Tag là gì và tag khác label ra sao?

Tag là cặp key-value gắn với tài nguyên để phân loại, tìm kiếm, tự động hóa hoặc phân bổ chi phí. Một số hệ thống gọi metadata tương tự là label, annotation hoặc resource property. Semantics và giới hạn khác nhau theo nền tảng:

- **Tag/label có thể dùng để lọc và policy:** ví dụ `environment=prod`.
- **Annotation thường chứa metadata bổ sung:** ví dụ repo URL, ticket hoặc thông tin triển khai; có thể không dùng để phân bổ chi phí.
- **Provider resource ID/name:** định danh kỹ thuật do nền tảng quản lý, không phải tag.
- **Kubernetes label:** cặp key-value dùng cho selector và grouping; annotation phù hợp với metadata không dùng để chọn object.

Không phải mọi tag đều được provider đưa vào billing export. Nếu cần cost allocation, kiểm tra tag key nào phải được kích hoạt hoặc ánh xạ trong hệ thống billing. Một tag có thể tồn tại trên tài nguyên nhưng không xuất hiện trong báo cáo chi phí nếu chưa được cấu hình ở billing layer.

## 9. Bộ tag tối thiểu nên có

Một bộ tag nền tảng có thể gồm:

| Key | Ví dụ | Mục đích |
|---|---|---|
| `org` | `acme` | Đơn vị sở hữu |
| `environment` | `prod` | Môi trường |
| `workload` | `orders` | Nhóm workload |
| `service` | `orders-api` | Service cụ thể |
| `owner-team` | `team-commerce-platform` | Nhóm kỹ thuật chịu trách nhiệm |
| `business-owner` | `commerce-operations` | Đơn vị nghiệp vụ chịu trách nhiệm |
| `cost-center` | `CC-420` | Phân bổ tài chính |
| `managed-by` | `terraform` | Cách quản lý/provision tài nguyên |
| `criticality` | `high` | Mức độ quan trọng |
| `data-classification` | `confidential` | Phân loại dữ liệu |
| `created-at` | `2026-11-22` | Thời điểm tạo theo format chuẩn |
| `lifecycle` | `permanent` | Vòng đời tài nguyên |

Không nhất thiết mọi tag đều bắt buộc cho mọi loại resource. Ví dụ, một network interface có thể kế thừa metadata workload từ VM; một tài nguyên shared service có thể dùng owner của platform team và tag `shared=true`. Cần quy định trường nào mandatory, conditional hoặc optional.

Tên key nên thống nhất chữ thường và dấu gạch ngang hoặc quy tắc camelCase, tránh trộn `OwnerTeam`, `owner_team`, `owner-team` và `ownerTeam` cho cùng ý nghĩa. Giá trị nên dùng mã chuẩn, không tự do nhập các biến thể.

## 10. Tag ownership và trách nhiệm kỹ thuật

Không nên chỉ có một tag `owner` chung chung nếu tổ chức cần phân biệt trách nhiệm. Một workload thường có nhiều vai trò:

- **Business owner:** chịu trách nhiệm mục tiêu nghiệp vụ, ngân sách và mức độ ưu tiên.
- **Technical/service owner:** chịu trách nhiệm kiến trúc, backlog kỹ thuật và vòng đời service.
- **Operations/on-call team:** xử lý cảnh báo, sự cố và vận hành hàng ngày.
- **Security owner/contact:** phối hợp xử lý lỗ hổng, quyền truy cập và kiểm soát bảo mật.
- **Cost owner:** chịu trách nhiệm ngân sách hoặc cost center; có thể là business owner hoặc đại diện tài chính.

Với workload nhỏ, một team có thể đảm nhận nhiều vai trò. Metadata vẫn nên thể hiện rõ ai là business owner và team nào trực tiếp vận hành, thay vì chỉ ghi tên một cá nhân.

Giá trị owner nên trỏ tới group, team slug, service catalog ID hoặc địa chỉ liên hệ chức năng được duy trì. Tránh email cá nhân làm định danh duy nhất vì người phụ trách có thể nghỉ việc hoặc đổi nhóm. Có thể lưu kênh liên hệ/on-call trong service catalog thay vì tag nếu tag bị giới hạn kích thước hoặc công khai rộng.

## 11. Xác định owner ở cấp workload trước khi tạo resource

Ownership nên được xác định ở cấp workload/service, sau đó truyền xuống các tài nguyên thành phần. Trước khi tạo production workload, cần có:

1. Service/workload ID và mô tả mục đích.
2. Business owner và technical owner.
3. Team vận hành/on-call và kênh liên hệ.
4. Cost center hoặc budget owner.
5. Mức độ criticality và SLO/SLA.
6. Data classification và yêu cầu tuân thủ.
7. Repository, pipeline, runbook và service catalog record.
8. Dependency chính và phạm vi môi trường/site.

Nếu workload chưa có owner rõ ràng, không nên mặc định platform team chịu trách nhiệm cho logic nghiệp vụ chỉ vì platform team tạo VM hoặc cluster. Platform team có thể sở hữu hạ tầng dùng chung; team sản phẩm vẫn chịu trách nhiệm ứng dụng và dữ liệu của mình.

## 12. RACI và ranh giới trách nhiệm

RACI giúp làm rõ ai thực hiện, ai chịu trách nhiệm cuối cùng, ai được tham vấn và ai cần được thông báo.

| Hoạt động | Business owner | Service owner | Platform/Operations | Security | Finance/FinOps |
|---|---|---|---|---|---|
| Xác định mục đích và criticality | A | R | C | C | I |
| Đặt tên service/workload | C | A/R | C | I | I |
| Tạo resource qua IaC/pipeline | I | A | R | C | I |
| Duy trì tag owner/service | C | A/R | R cho tag nền tảng | C | C |
| Xử lý incident ứng dụng | I | A/R | R theo hạ tầng | C | I |
| Xử lý lỗ hổng | I | R | R theo platform | A/C theo policy | I |
| Theo dõi và duyệt ngân sách | A | R | C | I | R/C |
| Decommission workload | A | R | R cho resource | C | C |

RACI là ví dụ; tổ chức cần xác định một vai trò Accountable cho từng hoạt động và không để trách nhiệm bị bỏ trống. Có thể cần thêm data owner, privacy officer, vendor owner hoặc site operator với workload đặc thù.

## 13. Phân biệt owner, creator và operator

Người tạo tài nguyên không nhất thiết là owner lâu dài. Ví dụ, kỹ sư platform có thể chạy pipeline tạo VM cho team thương mại. Creator là identity của pipeline hoặc người khởi tạo; owner là service/team chịu trách nhiệm về workload; operator là đội vận hành nền tảng hoặc on-call theo ranh giới đã thống nhất.

Không dùng `created-by` để thay `owner-team`. Có thể lưu cả hai:

- `created-by`: user/service principal/pipeline đã tạo resource.
- `owner-team`: nhóm chịu trách nhiệm lâu dài.
- `business-owner`: đơn vị nghiệp vụ.
- `managed-by`: Terraform, CloudFormation, Pulumi, Ansible hoặc controller.

`created-by` hữu ích cho audit và điều tra, nhưng có thể chứa identity kỹ thuật hoặc user ID không phù hợp để công khai. Giới hạn quyền đọc và retention theo chính sách tổ chức.

## 14. Tag cho cost allocation và FinOps

Để phân bổ chi phí, mỗi resource có thể cần tag `cost-center`, `product`, `service`, `environment` và `owner-team`. Shared resource cần quy tắc phân bổ riêng.

Ví dụ:

```text
resource: acme-prod-apse1-orders-api-vm-01
org=acme
environment=prod
workload=orders
service=orders-api
owner-team=team-commerce-platform
business-owner=commerce-operations
cost-center=CC-420
product=commerce
managed-by=terraform
```

Một số khoản chi phí không thể gắn trực tiếp với một workload, chẳng hạn NAT gateway, cluster control plane, logging backend hoặc shared network. Có thể phân bổ theo:

- Lượng dữ liệu hoặc số request thực tế.
- Số node/instance hoặc tỷ lệ capacity được cấp.
- Tỷ lệ sử dụng theo metric đo được.
- Số team/service sử dụng theo thỏa thuận.
- Một cost center shared/platform chịu phần chi phí nền.

Quy tắc cần được công bố và áp dụng ổn định. Nếu phân bổ theo tỷ lệ ước tính, cần ghi rõ đó là showback/chargeback theo mô hình phân bổ, không phải usage trực tiếp đo được.

## 15. Tag phục vụ bảo mật và compliance

Metadata có thể giúp policy engine và security tooling xác định cách bảo vệ workload. Một số tag thường hữu ích:

- `data-classification`: `public`, `internal`, `confidential`, `restricted`.
- `criticality`: `low`, `medium`, `high`, `mission-critical`.
- `compliance-scope`: mã phạm vi kiểm soát đã được tổ chức định nghĩa.
- `backup-policy`: tên policy backup được phê duyệt.
- `patch-ring`: nhóm cập nhật hệ điều hành.
- `exposure`: `public`, `private`, `isolated` theo taxonomy nội bộ.
- `recovery-tier`: phân loại mục tiêu phục hồi.

Tag không thay thế cấu hình thực tế. `data-classification=confidential` không tự mã hóa disk; `exposure=private` không tự chặn Internet; `backup-policy=daily` không chứng minh backup đã chạy hoặc restore được. Policy engine cần kiểm tra và thực thi cấu hình tương ứng, còn monitoring cần xác minh trạng thái thực tế.

Không dùng tag để ghi dữ liệu nhạy cảm như tên khách hàng, số tài khoản, email cá nhân, token hoặc chi tiết sự cố bảo mật. Tag có thể hiển thị trong console, API, billing export và log rộng hơn dự kiến.

## 16. Tag lifecycle và metadata thời gian

Metadata vòng đời giúp phân biệt tài nguyên lâu dài và tài nguyên tạm thời.

| Key | Ví dụ | Cách dùng |
|---|---|---|
| `lifecycle` | `permanent`, `temporary`, `ephemeral` | Xác định vòng đời dự kiến |
| `created-at` | `2026-11-22` | Phân tích tuổi tài nguyên |
| `expires-at` | `2026-12-15` | Thời hạn review/xóa tài nguyên tạm |
| `environment` | `dev`, `test`, `prod` | Áp dụng policy môi trường |
| `change-ticket` | `CHG-12345` | Liên kết thay đổi được phê duyệt |
| `backup-policy` | `prod-db-30d` | Ánh xạ tới chính sách backup |

Không tự động xóa chỉ dựa trên `expires-at` nếu tài nguyên có thể chứa dữ liệu quan trọng hoặc tag có thể sai. Quy trình cleanup cần kiểm tra owner, trạng thái workload, backup, dependency, retention và phê duyệt theo policy. Tài nguyên temporary không có owner vẫn cần một team chịu trách nhiệm dọn dẹp.

## 17. Tag inheritance và tài nguyên dùng chung

Một workload gồm nhiều resource: VM, disk, NIC, load balancer, queue, log group và backup. Nếu chỉ tag VM, các tài nguyên phụ có thể không xuất hiện trong báo cáo chi phí hoặc inventory theo workload.

Có thể áp dụng các cách:

- Pipeline tạo tất cả resource với cùng metadata workload.
- Module IaC nhận `common_tags`/labels và truyền cho resource hỗ trợ tag.
- Controller kế thừa tag từ parent hoặc workload object nếu nền tảng hỗ trợ.
- Inventory job phát hiện child resource thiếu tag và đề xuất sửa.
- Shared resource dùng owner riêng và tag `shared=true` cùng quy tắc phân bổ.

Không giả định tag tự động kế thừa từ resource group, project, cluster hoặc VM xuống mọi tài nguyên con. Hành vi phụ thuộc provider và loại resource. Cần kiểm tra billing export và inventory thực tế.

Với Kubernetes, label trên Pod template không tự động trở thành cloud tag trên mọi volume hoặc load balancer được provision. Cloud controller và CSI driver có thể có cơ chế tag riêng; phải cấu hình và xác minh.

## 18. Quy ước Kubernetes labels và annotations

Kubernetes dùng label để chọn và nhóm object; annotation để lưu metadata bổ sung. Một bộ label phổ biến có thể gồm:

```yaml
metadata:
  labels:
    app.kubernetes.io/name: orders-api
    app.kubernetes.io/instance: orders-prod
    app.kubernetes.io/component: api
    app.kubernetes.io/part-of: commerce
    app.kubernetes.io/managed-by: helm
    environment: prod
    owner-team: team-commerce-platform
  annotations:
    company.example.com/repository: https://git.example.com/commerce/orders-api
    company.example.com/runbook: https://docs.example.com/runbooks/orders-api
    company.example.com/cost-center: CC-420
```

Ví dụ dùng domain giả lập `company.example.com`; cần thay bằng domain được tổ chức sở hữu. Label có giới hạn về ký tự và độ dài, còn annotation phù hợp với giá trị dài hơn như URL hoặc metadata không dùng cho selector. Không đưa secret vào cả label lẫn annotation.

Label selector nên ổn định trong vòng đời controller. Không dùng tag thay đổi thường xuyên như version build hoặc owner cá nhân trong selector nếu thay đổi sẽ làm object không còn khớp selector của Deployment/Service.

## 19. Chuẩn hóa key, kiểu dữ liệu và giá trị tag

Tag schema cần định nghĩa:

- Key chính xác và mô tả ý nghĩa.
- Kiểu giá trị: enum, mã định danh, ngày ISO 8601, URL hoặc boolean.
- Trường bắt buộc/điều kiện áp dụng.
- Danh sách giá trị được phép.
- Quyền sửa và nguồn dữ liệu chuẩn.
- Có được kế thừa hay phải khai báo trực tiếp.
- Có được đưa vào billing export hay không.
- Retention và xử lý khi owner/team thay đổi.

Ví dụ schema rút gọn:

| Key | Kiểu | Required | Giá trị/validation |
|---|---|---:|---|
| `environment` | Enum | Có | `prod`, `stg`, `dev`, `test`, `sandbox`, `dr` |
| `workload` | Slug | Có | Khớp service catalog ID |
| `owner-team` | Team ID | Có | Phải tồn tại trong directory/service catalog |
| `business-owner` | Business unit ID | Có với production | Mã đơn vị hợp lệ |
| `cost-center` | Finance code | Có với resource tính phí | Mã còn hiệu lực |
| `managed-by` | Enum/string | Có | `terraform`, `helm`, `operator`, `manual-approved` |
| `criticality` | Enum | Có với production | `low`, `medium`, `high`, `mission-critical` |
| `data-classification` | Enum | Có khi lưu/xử lý dữ liệu | Giá trị theo policy dữ liệu |
| `expires-at` | Date | Có với temporary | `YYYY-MM-DD` và có owner review |

Nếu tổ chức dùng nhiều cloud, có thể duy trì canonical schema nội bộ rồi ánh xạ sang key/tag của từng provider. Tránh đổi nghĩa cùng một key giữa các nền tảng.

## 20. Enforce naming và tagging bằng policy as code

Quy ước chỉ có hiệu lực khi được áp dụng ở điểm tạo tài nguyên. Có thể triển khai nhiều lớp:

1. **Template/IaC module:** tự tạo tên và tag chuẩn từ input đã kiểm tra.
2. **CI validation:** kiểm tra tên, required tags, enum và owner trước khi apply.
3. **Admission policy:** kiểm tra Kubernetes object khi tạo/cập nhật.
4. **Cloud policy:** từ chối hoặc audit resource thiếu tag/naming theo khả năng provider.
5. **Inventory scan:** tìm tài nguyên tạo ngoài pipeline hoặc thiếu metadata.
6. **Remediation:** bổ sung tag có thể xác minh hoặc tạo ticket cho owner.

Ví dụ logic validation khái niệm:

```python
REQUIRED_TAGS = {
    "environment",
    "workload",
    "owner-team",
    "cost-center",
    "managed-by",
}

def validate_resource(resource):
    tags = resource.tags or {}
    missing = REQUIRED_TAGS - set(tags)
    if missing:
        raise ValueError(f"Missing required tags: {sorted(missing)}")

    if tags["environment"] not in {"prod", "stg", "dev", "test", "sandbox", "dr"}:
        raise ValueError("Unsupported environment")

    if not team_exists(tags["owner-team"]):
        raise ValueError("Unknown owner team")

    validate_resource_name(resource.name, resource.kind)
```

Đây là pseudocode, không phải policy có thể chạy trực tiếp. Trong triển khai thực tế, `team_exists` và `validate_resource_name` cần truy vấn danh mục chuẩn; validator phải xử lý resource không hỗ trợ tag và ngoại lệ có thời hạn.

Nên bắt đầu ở chế độ audit để phát hiện tác động, sau đó chuyển sang enforce cho resource mới. Với production hiện hữu, cần migration plan để bổ sung metadata trước khi bật policy từ chối.

## 21. Quản lý ngoại lệ

Một số tài nguyên không thể tuân thủ đầy đủ naming/tag do giới hạn provider, tài nguyên legacy hoặc yêu cầu vendor. Ngoại lệ cần có:

- Resource ID và lý do cụ thể.
- Owner chịu trách nhiệm.
- Policy nào không thể đáp ứng và tác động.
- Biện pháp thay thế để vẫn tìm kiếm, phân bổ chi phí và liên hệ được owner.
- Người phê duyệt và thời hạn hết hiệu lực.
- Kế hoạch khắc phục hoặc review lại.

Không tạo tag `exception=true` rồi bỏ qua vô thời hạn. Ngoại lệ cần được theo dõi, cảnh báo khi hết hạn và có báo cáo theo team/service.

## 22. Xác định và duy trì owner trong vòng đời workload

Ownership không kết thúc sau lúc tạo resource. Cần cập nhật khi service đổi team, tách/ghép sản phẩm, chuyển vendor hoặc ngừng hoạt động.

Quy trình vòng đời:

1. Đăng ký workload/service trong catalog.
2. Chỉ định business owner, technical owner và operations contact.
3. Chọn workload ID, naming segments và tag schema.
4. Tạo resource qua pipeline/IaC với metadata chuẩn.
5. Đồng bộ ownership vào inventory, monitoring, cost reporting và runbook.
6. Review định kỳ owner, cost center, criticality và data classification.
7. Khi chuyển giao, cập nhật catalog và tag trong cùng change window.
8. Khi decommission, xác minh dữ liệu, backup, dependency và tài nguyên phụ trước khi xóa.

Có thể review ownership theo quý hoặc khi có thay đổi tổ chức/service. Với production critical, cần kiểm tra owner/on-call thường xuyên hơn theo policy.

## 23. Phát hiện workload không có owner

Một tài nguyên thiếu tag `owner-team` có thể là orphan resource, nhưng cũng có thể là resource con chưa được tag hoặc shared infrastructure. Không nên tự động gán tất cả tài nguyên không rõ owner cho team platform.

Quy trình xử lý:

- Tìm resource group/project, network attachment, volume attachment, deployment và billing context liên quan.
- Đối chiếu naming, tag còn lại, service catalog, IaC state và audit log.
- Xác định workload/service parent và team chịu trách nhiệm.
- Liên hệ owner ứng viên để xác nhận.
- Bổ sung tag/catalog sau khi có bằng chứng.
- Nếu không xác định được, tạo ticket cho governance team với deadline và trạng thái `unowned`.
- Chỉ cô lập hoặc decommission theo policy sau khi đánh giá tác động và dữ liệu.

Một báo cáo orphan resource nên có resource ID, type, region/site, age, cost estimate, attachment, candidate workload, confidence và next action. Điều này giúp ưu tiên xử lý tài nguyên tốn kém hoặc có rủi ro bảo mật.

## 24. Shared workload và platform ownership

Một số tài nguyên phục vụ nhiều workload như Kubernetes cluster, shared NAT, observability platform, image registry, DNS, transit gateway và CI runner. Không thể gán chúng cho một ứng dụng duy nhất.

Với shared resource:

- Đặt `owner-team` là team platform chịu trách nhiệm kỹ thuật.
- Đặt `business-owner` hoặc `service` là platform/shared-services nếu phù hợp taxonomy.
- Đánh dấu `shared=true` hoặc `allocation-model=shared`.
- Xác định consumer teams hoặc service catalog dependencies.
- Công bố quy tắc phân bổ chi phí.
- Xác định SLA/SLO và kênh incident của dịch vụ nền.

Team platform sở hữu service nền và capacity của nó; consumer team vẫn chịu trách nhiệm về cách workload của họ sử dụng dịch vụ và chi phí có thể quy thuộc. Ranh giới này cần được ghi trong service catalog và operational agreement.

## 25. Quyền thay đổi tag và audit

Nếu mọi người đều có thể sửa `owner-team`, `cost-center` hoặc `data-classification`, metadata có thể bị thay đổi để né policy hoặc làm sai báo cáo. Cần xác định ai được sửa từng trường.

Gợi ý kiểm soát:

- Owner team có thể đề xuất thay đổi metadata service của mình.
- Finance/FinOps quản lý danh mục cost center và phê duyệt thay đổi tài chính.
- Security/data governance quản lý taxonomy classification và compliance scope.
- Platform team duy trì naming/tag schema và policy enforcement.
- Automation identity được quyền ghi các tag do pipeline quản lý.
- Audit log lưu ai/thành phần nào thay đổi tag, thời điểm và giá trị trước/sau.

Không cấp quyền sửa tag rộng chỉ để giúp automation chạy dễ dàng. Có thể tách quyền theo key hoặc dùng pipeline identity được giới hạn vào resource scope.

## 26. Báo cáo governance và chỉ số chất lượng metadata

Để biết quy ước có được thực hiện hay không, nên đo:

| Chỉ số | Cách hiểu |
|---|---|
| Naming compliance | Tỷ lệ resource có tên khớp convention theo loại resource |
| Mandatory tag coverage | Tỷ lệ resource có đủ tag bắt buộc |
| Owner coverage | Tỷ lệ workload/resource có owner team hợp lệ |
| Cost allocation coverage | Tỷ lệ chi phí được gán cost center/service/team |
| Unknown/orphan spend | Chi phí của resource chưa xác định owner |
| Stale owner records | Owner/team không còn tồn tại hoặc không xác nhận định kỳ |
| Expired temporary resources | Resource tạm đã quá hạn review |
| Policy violation age | Thời gian từ lúc phát hiện đến lúc khắc phục |
| Shared cost allocation coverage | Tỷ lệ shared cost có quy tắc phân bổ rõ |

Theo dõi xu hướng theo team, environment, region và resource type. Một tỷ lệ coverage cao không có nghĩa dữ liệu đúng; cần kiểm tra ngẫu nhiên owner, cost center và service mapping với catalog/audit record.

## 27. Ví dụ: chuẩn hóa workload orders trên cloud và edge

Giả sử workload `orders` có API chạy trên cloud, worker tại data center và gateway đồng bộ tại một số cửa hàng. Service catalog ghi:

| Thuộc tính | Giá trị |
|---|---|
| Workload | `orders` |
| Business owner | `commerce-operations` |
| Technical owner | `team-commerce-platform` |
| On-call | `commerce-platform-oncall` |
| Cost center | `CC-420` |
| Criticality | `high` |
| Data classification | `confidential` |
| Repository | `commerce/orders` |
| Runbook | `runbooks/orders` |

Tên tài nguyên có thể là:

```text
acme-prod-apse1-orders-api-vm-01
acme-prod-dc01-orders-worker-vm-02
acme-prod-store014-orders-edge-gateway-01
```

Các tag chung:

```text
environment=prod
workload=orders
owner-team=team-commerce-platform
business-owner=commerce-operations
cost-center=CC-420
criticality=high
data-classification=confidential
managed-by=terraform
```

Tag site/location và resource role có thể khác theo môi trường. Secret và device certificate được cấp riêng cho từng gateway, không nằm trong tag hoặc image. Chi phí cloud API, worker on-prem và edge fleet được báo cáo riêng nhưng liên kết cùng workload ID để tổng hợp TCO.

Nếu team vận hành đổi từ `team-commerce-platform` sang team mới, service catalog được cập nhật trước; pipeline sau đó đồng bộ tag cho resource đang hoạt động. Audit log giữ lại lịch sử chuyển giao. Không cần đổi toàn bộ resource name nếu naming convention không phụ thuộc tên team.

## 28. Ví dụ policy kiểm tra tên và tag trong CI

Một pipeline IaC có thể kiểm tra metadata trước khi tạo resource:

```yaml
workload:
  org: acme
  environment: prod
  location: apse1
  service: orders-api
  ownerTeam: team-commerce-platform
  businessOwner: commerce-operations
  costCenter: CC-420
  managedBy: terraform
  criticality: high
```

Pipeline có thể tạo tên từ các trường đã chuẩn hóa, kiểm tra team ID và cost center trong danh mục, rồi truyền tag vào module. Giá trị này là input cấu hình, không phải secret.

Một quy trình CI nên:

1. Validate schema và required field.
2. Kiểm tra enum và pattern của slug.
3. Xác minh owner/team/cost center tồn tại.
4. Tạo resource name theo resource-specific rule.
5. Render IaC plan và hiển thị diff metadata.
6. Chặn production apply nếu thiếu trường bắt buộc hoặc owner không hợp lệ.
7. Ghi release/change ID và actor của pipeline vào audit.

Không nên chỉ dựa vào regex tên để suy ra toàn bộ metadata. Tên có thể cũ hoặc bị giới hạn bởi provider; tag/catalog mới là nguồn dữ liệu có cấu trúc cho owner, cost và classification.

## 29. Những sai lầm thường gặp

- **Đưa quá nhiều thông tin vào tên:** tên dài, dễ vượt giới hạn và nhanh lỗi thời. Đưa metadata chi tiết vào tag/catalog.
- **Dùng tên người làm owner:** nhân sự thay đổi khiến metadata lỗi thời. Dùng team/service ID và contact group.
- **Dùng `created-by` thay owner:** người tạo có thể chỉ là pipeline hoặc kỹ sư platform. Tách creator và owner.
- **Tag tự do không có taxonomy:** `prod`, `production`, `prd` làm báo cáo phân mảnh. Chuẩn hóa enum và validator.
- **Cho rằng tag tự kế thừa:** resource con không có tag nên chi phí không được phân bổ. Xác minh propagation và tag trực tiếp khi cần.
- **Coi tag security là enforcement:** tag `private` không tự chặn traffic. Policy phải kiểm tra cấu hình thực tế.
- **Đặt tên theo region nhưng bỏ site/fault domain cần thiết:** khó tìm tài nguyên edge hoặc data center. Dùng location code từ inventory.
- **Đổi tên resource tùy tiện:** endpoint hoặc dependency có thể bị ảnh hưởng. Kiểm tra khả năng rename và migration.
- **Tự động xóa resource thiếu tag:** có thể xóa nhầm production hoặc shared service. Điều tra owner và dependency trước.
- **Không review owner sau tái tổ chức:** alert và incident đi tới team cũ. Đồng bộ catalog và tag theo change.
- **Không phân bổ shared cost:** các team không thấy phần sử dụng của mình. Công bố allocation model.
- **Chỉ enforce ở cloud console:** tài nguyên tạo qua API/IaC hoặc edge không được kiểm soát. Enforce ở pipeline và inventory.

## 30. Checklist triển khai governance

**Naming convention**

- [ ] Có mẫu tên chung và segment được định nghĩa.
- [ ] Environment, location, workload, component và resource role dùng danh mục chuẩn.
- [ ] Có quy tắc ký tự, độ dài, case và uniqueness theo từng loại resource.
- [ ] Tên không chứa secret, PII hoặc thông tin dễ lỗi thời.
- [ ] Có cách xử lý tài nguyên immutable và tên của resource ephemeral.

**Tag schema**

- [ ] Có canonical key, kiểu dữ liệu, enum và mô tả cho từng tag.
- [ ] Có required/conditional/optional tag theo resource/workload.
- [ ] Owner-team, business-owner, cost-center, environment và workload được xác định.
- [ ] Có tag phục vụ lifecycle, criticality, classification và managed-by khi cần.
- [ ] Không lưu secret hoặc dữ liệu nhạy cảm trong tag/label/annotation.
- [ ] Đã xác minh tag propagation và billing activation.

**Ownership**

- [ ] Workload có service catalog record và business owner.
- [ ] Có technical owner, operations/on-call và kênh liên hệ.
- [ ] Phân biệt owner, creator, operator và shared platform owner.
- [ ] RACI xác định rõ trách nhiệm incident, security, cost và decommission.
- [ ] Có quy trình chuyển giao và review owner định kỳ.

**Enforcement và vận hành**

- [ ] IaC/template tự sinh tên và tag theo schema.
- [ ] CI/admission/cloud policy validate metadata trước khi tạo resource.
- [ ] Inventory phát hiện missing tag, invalid owner, orphan và expired resource.
- [ ] Ngoại lệ có lý do, approver, owner và ngày hết hạn.
- [ ] Audit log ghi thay đổi tag/ownership.
- [ ] Có báo cáo naming compliance, tag coverage, owner coverage và unallocated spend.
- [ ] Cleanup có kiểm tra dependency, backup, retention và phê duyệt.

Quy ước đặt tên giúp nhận diện tài nguyên; tag cung cấp metadata có cấu trúc; ownership xác định ai chịu trách nhiệm xuyên suốt vòng đời workload. Khi tổ chức chuẩn hóa taxonomy, xác định owner ở cấp service, áp dụng tag qua IaC/pipeline và kiểm tra inventory định kỳ, nền tảng compute sẽ dễ tìm kiếm, phân bổ chi phí, bảo vệ và vận hành hơn trên cloud, data center và edge.
