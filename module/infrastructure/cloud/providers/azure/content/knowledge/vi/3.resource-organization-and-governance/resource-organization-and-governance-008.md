# Azure Policy, initiative và remediation

Azure Policy là dịch vụ quản trị giúp tổ chức đặt ra và thực thi các quy tắc đối với tài nguyên Azure. Bạn có thể dùng policy để kiểm soát vùng triển khai, yêu cầu tài nguyên có tag, kiểm tra cấu hình bảo mật, giới hạn loại tài nguyên được phép tạo và phát hiện các cấu hình chưa đáp ứng tiêu chuẩn.

Khi số lượng subscription và resource group tăng lên, việc hướng dẫn từng nhóm làm theo một bộ quy tắc sẽ khó duy trì. Azure Policy đưa các quy tắc đó thành định nghĩa có thể gán ở nhiều phạm vi, đánh giá tự động và theo dõi tập trung. Trong hệ sinh thái **CLOUD_PROVIDERS_AZURE**, đây là một phần quan trọng để tổ chức tài nguyên, bảo vệ kiến trúc ứng dụng và quản trị môi trường Azure trên quy mô lớn.

Bài học tập trung vào ba thành phần liên kết với nhau:

- **Policy definition** mô tả một quy tắc cần đánh giá.
- **Initiative** (policy set definition) gom nhiều policy có cùng mục tiêu thành một bộ tiêu chuẩn.
- **Remediation** thực hiện hành động khắc phục đối với tài nguyên hiện có khi policy hỗ trợ cơ chế đó.

## 1. Azure Policy giải quyết vấn đề gì?

Giả sử một công ty có các môi trường phát triển, kiểm thử và sản xuất trên nhiều subscription. Công ty muốn:

- Chỉ triển khai tài nguyên tại một số Azure region được phê duyệt.
- Mỗi resource group và tài nguyên cần có tag `Environment`, `Owner` và `CostCenter`.
- Storage account phải yêu cầu truyền dữ liệu an toàn.
- Không cho phép tạo một số loại tài nguyên ngoài danh mục chuẩn.
- Phát hiện máy ảo hoặc dịch vụ có cấu hình chưa đáp ứng chính sách nội bộ.

Nếu kiểm tra thủ công, mỗi nhóm có thể áp dụng tiêu chuẩn khác nhau và các sai lệch dễ bị bỏ sót. Azure Policy đánh giá tài nguyên theo định nghĩa được gán, ghi nhận trạng thái tuân thủ và có thể ngăn một số yêu cầu tạo hoặc cập nhật tài nguyên.

Azure Policy hoạt động cùng Azure Resource Manager (ARM). Khi một yêu cầu quản lý tài nguyên đi qua ARM, policy được áp dụng tại phạm vi tương ứng có thể đánh giá yêu cầu đó. Ngoài đánh giá trong quá trình tạo hoặc cập nhật, Azure Policy còn đánh giá định kỳ các tài nguyên hiện có để cập nhật dữ liệu tuân thủ.

Azure Policy và Azure role-based access control (Azure RBAC) có vai trò khác nhau:

| Thành phần | Câu hỏi mà thành phần trả lời |
|---|---|
| Azure RBAC | Ai được phép thực hiện hành động nào trên phạm vi nào? |
| Azure Policy | Tài nguyên hoặc yêu cầu thay đổi có đáp ứng quy tắc quản trị hay không? |
| Azure Resource Manager | Yêu cầu quản lý tài nguyên được tiếp nhận và thực thi như thế nào? |

Ví dụ, một người dùng có quyền Contributor vẫn có thể bị policy từ chối khi tạo tài nguyên ở region không được phép. RBAC cho phép người dùng thực hiện thao tác tạo tài nguyên, còn policy kiểm soát cấu hình của tài nguyên đó.

## 2. Các khái niệm cốt lõi

| Khái niệm | Ý nghĩa |
|---|---|
| Policy definition | Định nghĩa một quy tắc, điều kiện đánh giá và effect sẽ áp dụng |
| Policy assignment | Gán một policy hoặc initiative vào một phạm vi cụ thể và cung cấp giá trị tham số |
| Initiative / policy set definition | Tập hợp nhiều policy definition thành một bộ tiêu chuẩn |
| Scope | Phạm vi áp dụng, ví dụ management group, subscription hoặc resource group |
| Exclusion / notScopes | Phạm vi con được loại khỏi một assignment |
| Exemption | Ngoại lệ được ghi nhận có lý do và có thể đặt ngày hết hạn |
| Compliance state | Kết quả đánh giá tuân thủ của tài nguyên đối với policy assignment |
| Remediation task | Tác vụ khắc phục tài nguyên hiện có cho policy có effect hỗ trợ remediation |

Quy trình tổng quát:

1. Tạo hoặc chọn policy definition.
2. Nếu có nhiều quy tắc liên quan, nhóm chúng thành initiative.
3. Tạo assignment tại phạm vi quản trị phù hợp và đặt các tham số.
4. Azure Policy đánh giá tài nguyên, ghi nhận kết quả tuân thủ và thực thi effect.
5. Điều tra tài nguyên không tuân thủ; tạo remediation task nếu policy có thể tự khắc phục.
6. Theo dõi kết quả, xử lý ngoại lệ và cập nhật bộ tiêu chuẩn theo thời gian.

## 3. Policy definition: định nghĩa quy tắc

Policy definition mô tả điều kiện cần đánh giá và hành động tương ứng. Azure có các built-in policy do Microsoft cung cấp. Bạn cũng có thể tạo custom policy để phản ánh tiêu chuẩn riêng của tổ chức.

Một policy definition thường có các thành phần:

- `displayName`: tên hiển thị của quy tắc.
- `description`: giải thích mục đích và phạm vi.
- `mode`: loại tài nguyên mà policy đánh giá.
- `parameters`: các giá trị có thể thay đổi khi tạo assignment.
- `policyRule`: biểu thức `if` xác định tài nguyên hoặc yêu cầu cần xử lý và `then` chỉ định effect.
- `metadata`: thông tin phân loại, phiên bản hoặc thông tin quản trị.

Trong phần `if`, policy dùng các trường và alias để kiểm tra thuộc tính tài nguyên. Alias là đường dẫn do Azure cung cấp để policy truy cập thuộc tính của một loại tài nguyên. Khi viết custom policy, hãy kiểm tra alias có sẵn cho đúng resource provider và API version; không phải thuộc tính nào trong tài liệu ARM cũng có thể dùng trực tiếp làm alias.

### Ví dụ: chỉ cho phép triển khai tại các region được phê duyệt

Định nghĩa sau minh họa policy từ chối yêu cầu tạo hoặc cập nhật tài nguyên có location không nằm trong danh sách cho phép:

```json
{
  "properties": {
    "displayName": "Chỉ cho phép region được phê duyệt",
    "description": "Từ chối tài nguyên nằm ngoài danh sách Azure region cho phép.",
    "policyType": "Custom",
    "mode": "Indexed",
    "metadata": {
      "category": "Locations"
    },
    "parameters": {
      "allowedLocations": {
        "type": "Array",
        "metadata": {
          "displayName": "Các region được phép",
          "description": "Danh sách region Azure được tổ chức phê duyệt."
        }
      }
    },
    "policyRule": {
      "if": {
        "field": "location",
        "notIn": "[parameters('allowedLocations')]"
      },
      "then": {
        "effect": "deny"
      }
    }
  }
}
```

Trong ví dụ này:

- `allowedLocations` là tham số kiểu mảng. Giá trị cụ thể được cung cấp ở bước assignment.
- `field: location` đọc vị trí triển khai của tài nguyên.
- `notIn` kiểm tra location có nằm ngoài danh sách cho phép hay không.
- Effect `deny` từ chối yêu cầu không đáp ứng điều kiện.

Đây là ví dụ minh họa cấu trúc policy. Khi triển khai thực tế, cần kiểm tra mode, alias, loại tài nguyên và các trường hợp ngoại lệ của workload trong phạm vi áp dụng.

### Policy parameter và assignment

Tham số giúp một định nghĩa được tái sử dụng ở nhiều môi trường. Ví dụ, cùng một policy có thể được gán cho subscription phát triển với hai region và subscription sản xuất với ba region được phê duyệt.

Giá trị tham số được truyền vào assignment, không cần tạo một policy definition mới cho từng subscription. Điều này giúp giữ quy tắc thống nhất trong khi vẫn cho phép cấu hình khác nhau theo môi trường.

### Những effect thường gặp

Effect xác định Azure Policy xử lý một yêu cầu hoặc tài nguyên như thế nào.

| Effect | Hành vi |
|---|---|
| `Audit` | Ghi nhận tài nguyên không đáp ứng quy tắc, không chặn yêu cầu |
| `Deny` | Từ chối yêu cầu tạo hoặc cập nhật không đáp ứng quy tắc |
| `Append` | Bổ sung thuộc tính vào yêu cầu tạo hoặc cập nhật khi thuộc tính hỗ trợ effect này |
| `Modify` | Sửa một số thuộc tính được hỗ trợ, thường dùng cho tag hoặc thuộc tính có alias modifiable |
| `AuditIfNotExists` | Kiểm tra sự tồn tại của tài nguyên liên quan; ghi nhận vi phạm nếu không tìm thấy |
| `DeployIfNotExists` | Triển khai tài nguyên liên quan khi điều kiện yêu cầu không được đáp ứng |
| `Disabled` | Tắt effect của policy trong assignment tương ứng |

Một số điểm cần nhớ:

- `Audit` thích hợp khi tổ chức muốn khảo sát hiện trạng trước khi áp dụng quy tắc nghiêm ngặt.
- `Deny` có tác động trực tiếp tới quy trình triển khai. Cần đánh giá workload trước khi bật.
- `Append` và `Modify` không áp dụng được cho mọi thuộc tính. Khả năng sửa phụ thuộc alias và giới hạn của effect.
- `AuditIfNotExists` và `DeployIfNotExists` dùng để kiểm tra hoặc tạo tài nguyên liên quan, chẳng hạn chẩn đoán, cấu hình bảo vệ hoặc một thành phần phụ trợ.
- `DeployIfNotExists` và `Modify` có thể cần managed identity cùng quyền Azure RBAC phù hợp khi triển khai hoặc remediation.
- `Append` và `Deny` tác động đến yêu cầu tạo/cập nhật; chúng không tự sửa tất cả tài nguyên đã tồn tại.

Có thể triển khai policy theo lộ trình: bắt đầu bằng `Audit`, xem báo cáo và điều chỉnh phạm vi; sau khi các nhóm đã xử lý sai lệch, chuyển sang effect thực thi như `Deny` nếu phù hợp.

## 4. Assignment và phạm vi áp dụng

Policy definition chỉ mô tả quy tắc. Để quy tắc có hiệu lực tại môi trường, bạn phải tạo policy assignment.

Azure Policy hỗ trợ các phạm vi quản trị chính:

- **Management group:** áp dụng cho các subscription nằm trong hệ thống phân cấp của management group.
- **Subscription:** áp dụng trong một subscription.
- **Resource group:** áp dụng trong một resource group và các tài nguyên thuộc phạm vi đó.
- **Resource:** trong các trường hợp được hỗ trợ, assignment có thể áp dụng ở phạm vi một tài nguyên cụ thể.

Một assignment thường xác định:

- Policy definition hoặc initiative được gán.
- Scope áp dụng.
- Các giá trị tham số.
- Các phạm vi loại trừ nếu có.
- Enforcement mode.
- Managed identity và vị trí identity khi effect cần triển khai hoặc sửa tài nguyên.

### Chọn scope phù hợp

Giả sử công ty có ba subscription: `sub-dev`, `sub-test` và `sub-prod`. Quy tắc về region và tag bắt buộc có thể được gán tại management group chứa cả ba subscription. Một quy tắc chỉ dành cho production có thể được gán riêng tại `sub-prod`.

Assignment ở scope cha có thể được kế thừa xuống scope con. Do đó, khi điều tra một tài nguyên không tuân thủ, hãy xem cả assignment trực tiếp và assignment được kế thừa.

### Exclusion và exemption

Hai cơ chế này phục vụ những mục đích khác nhau:

- **Exclusion** (thường cấu hình bằng `notScopes` trên assignment) loại một scope con khỏi phạm vi đánh giá của assignment. Đây là quyết định cấu hình phạm vi.
- **Exemption** tạo một bản ghi ngoại lệ có thể kiểm toán cho một policy assignment hoặc một số policy trong initiative. Exemption có thể ghi lý do, danh mục và ngày hết hạn.

Exemption thường phù hợp hơn khi một workload cần ngoại lệ có kiểm soát. Ví dụ, một ứng dụng cũ chưa thể bật cấu hình mã hóa theo yêu cầu trong giai đoạn di chuyển. Nhóm phụ trách có thể đề xuất exemption có thời hạn, ghi lý do và kế hoạch khắc phục.

Không nên loại trừ cả subscription chỉ để xử lý một tài nguyên riêng lẻ. Hãy giới hạn ngoại lệ ở phạm vi nhỏ nhất có thể và đặt thời hạn xem xét.

### Enforcement mode

Assignment có thể dùng enforcement mode `DoNotEnforce` để đánh giá policy mà chưa thực thi effect. Chế độ này hữu ích khi thử nghiệm một policy mới hoặc quan sát tác động trước khi bật enforcement.

Khi chuyển sang enforcement mặc định, các effect như `Deny` có thể bắt đầu chặn yêu cầu mới. Hãy thông báo cho nhóm phát triển và vận hành trước khi thay đổi assignment ở môi trường quan trọng.

## 5. Initiative: gom policy thành một bộ tiêu chuẩn

Initiative, còn gọi là policy set definition, là tập hợp nhiều policy definition có liên quan. Thay vì tạo nhiều assignment rời rạc, bạn có thể gán một initiative để triển khai một bộ tiêu chuẩn thống nhất.

Ví dụ, initiative “Baseline bảo mật cho workload” có thể chứa:

1. Policy yêu cầu storage account sử dụng truyền dữ liệu an toàn.
2. Policy kiểm tra tài nguyên có tag sở hữu.
3. Policy kiểm tra cấu hình chẩn đoán.
4. Policy giới hạn region triển khai.
5. Policy kiểm tra cấu hình bảo mật của máy ảo.

Initiative có các policy reference để nhận diện từng policy thành viên. Initiative cũng có thể khai báo tham số chung rồi ánh xạ tham số đó tới các policy con. Nhờ vậy, người quản trị có thể cấu hình một lần ở assignment của initiative.

Ví dụ cấu trúc rút gọn:

```json
{
  "properties": {
    "displayName": "Baseline quản trị workload",
    "policyType": "Custom",
    "description": "Tập hợp các quy tắc nền tảng cho workload.",
    "metadata": {
      "category": "Governance"
    },
    "parameters": {
      "allowedLocations": {
        "type": "Array",
        "metadata": {
          "displayName": "Các region được phép"
        }
      }
    },
    "policyDefinitions": [
      {
        "policyDefinitionId": "<POLICY_DEFINITION_RESOURCE_ID>",
        "policyDefinitionReferenceId": "approved-locations",
        "parameters": {
          "allowedLocations": {
            "value": "[parameters('allowedLocations')]"
          }
        }
      }
    ]
  }
}
```

Đây là ví dụ rút gọn để minh họa cách initiative tham chiếu policy definition và ánh xạ tham số. Khi tạo initiative hoàn chỉnh, mỗi phần tử trong `policyDefinitions` cần trỏ tới policy definition hợp lệ; các tham số được ánh xạ phải tương thích với định nghĩa được tham chiếu.

### Lợi ích của initiative

- **Quản lý tập trung:** một assignment có thể triển khai nhiều quy tắc cùng mục tiêu.
- **Tái sử dụng:** cùng một initiative có thể được gán cho nhiều subscription hoặc management group.
- **Nhất quán:** các nhóm dùng chung một bộ tiêu chuẩn và cách đặt tên.
- **Báo cáo:** trạng thái tuân thủ có thể được xem theo initiative và từng policy thành viên.
- **Dễ phát triển:** có thể cập nhật bộ tiêu chuẩn theo phiên bản và quy trình quản trị thay đổi.

Không nên gom mọi policy vào một initiative duy nhất. Hãy nhóm theo mục tiêu dễ hiểu, chẳng hạn baseline bảo mật, tiêu chuẩn tagging, quản trị chi phí hoặc yêu cầu tuân thủ của một workload. Initiative quá lớn có thể gây khó khăn khi phân quyền, triển khai theo giai đoạn và phân tích kết quả.

## 6. Remediation: khắc phục tài nguyên không tuân thủ

Kết quả non-compliant cho biết tài nguyên đang vi phạm quy tắc. Kết quả này không có nghĩa Azure Policy đã tự động sửa tài nguyên.

**Remediation** là quá trình thực hiện hành động khắc phục cho tài nguyên hiện có. Khả năng remediation phụ thuộc vào effect của policy:

- Policy dùng `DeployIfNotExists` có thể triển khai tài nguyên liên quan còn thiếu.
- Policy dùng `Modify` có thể sửa các thuộc tính được hỗ trợ trên tài nguyên hiện có.
- Policy chỉ dùng `Audit` hoặc `Deny` không tự sửa tài nguyên cũ. Nhóm vận hành cần cập nhật tài nguyên theo hướng dẫn hoặc dùng một policy có effect hỗ trợ remediation.

### Managed identity và quyền cần thiết

Với `DeployIfNotExists` hoặc `Modify`, assignment có thể cần managed identity để thực hiện thay đổi. Identity đó phải được cấp quyền Azure RBAC cần thiết tại phạm vi tài nguyên sẽ được khắc phục.

Trong policy definition, phần cấu hình effect có thể khai báo các role definition ID cần thiết. Khi tạo assignment, người quản trị phải bảo đảm managed identity nhận đủ các role tương ứng tại scope phù hợp. Việc tạo identity mà không cấp quyền cần thiết sẽ khiến remediation thất bại.

Nguyên tắc cấp quyền:

- Chỉ cấp các role mà policy thực sự cần.
- Giới hạn phạm vi ở subscription hoặc resource group liên quan nếu có thể.
- Xem xét quyền triển khai template và quyền sửa tài nguyên đích.
- Kiểm tra identity của assignment và role assignment trước khi chạy remediation.
- Theo dõi quyền của identity khi policy hoặc phạm vi triển khai thay đổi.

Không dùng tài khoản người dùng cá nhân làm danh tính remediation lâu dài. Managed identity gắn với assignment giúp hành động tự động có danh tính riêng và có thể kiểm soát bằng Azure RBAC.

### Tạo remediation task

Remediation task thường được tạo sau khi assignment đã tồn tại, policy đã đánh giá tài nguyên và managed identity đã được cấp quyền.

Quy trình thực hiện:

1. Mở Azure Policy, vào Compliance và chọn assignment có tài nguyên non-compliant.
2. Xem chi tiết policy để xác định effect có hỗ trợ remediation không.
3. Kiểm tra managed identity của assignment và các role được cấp.
4. Chọn remediation cho policy hoặc policy reference tương ứng.
5. Xác định phạm vi và tài nguyên cần khắc phục.
6. Tạo remediation task và theo dõi trạng thái, số lượng tài nguyên thành công hoặc thất bại.
7. Đánh giá lại compliance để xác nhận kết quả.

Trong Azure Portal, thao tác thường được thực hiện từ trang Policy assignment hoặc chi tiết compliance. Tên mục có thể thay đổi theo giao diện portal và loại policy.

Có thể quản lý remediation bằng Azure CLI. Ví dụ dưới đây minh họa việc tạo task ở phạm vi resource group cho một assignment đã có:

```bash
az policy remediation create --name "remediate-workload" --policy-assignment "<POLICY_ASSIGNMENT_ID>" --resource-group "<RESOURCE_GROUP_NAME>"
```

Để xem thông tin task:

```bash
az policy remediation show --name "remediate-workload" --resource-group "<RESOURCE_GROUP_NAME>"
```

Các placeholder cần được thay bằng ID assignment và resource group thực tế. Phạm vi remediation phải phù hợp với scope của assignment và tài nguyên cần xử lý. Với assignment ở scope subscription hoặc management group, hãy chọn tham số scope tương ứng theo lệnh Azure CLI đang sử dụng.

Remediation có thể chạy bất đồng bộ và mất thời gian tùy số lượng tài nguyên. Một task thất bại không nhất thiết có nghĩa policy definition sai; có thể identity thiếu quyền, template triển khai lỗi, tài nguyên không còn tồn tại hoặc cấu hình không thể sửa tự động.

### Remediation không thay thế việc đánh giá

Sau remediation, hãy kiểm tra kết quả của task và chạy hoặc chờ một lần đánh giá compliance tiếp theo. Một số thay đổi cần thời gian để được Azure Policy ghi nhận.

Nếu tài nguyên vẫn non-compliant:

- Kiểm tra remediation task có thất bại hay bỏ qua tài nguyên không.
- Xem lỗi chi tiết của deployment hoặc thao tác sửa.
- Xác nhận identity được cấp đúng role và scope.
- Kiểm tra điều kiện policy, alias và giá trị tham số.
- Xác nhận tài nguyên đã thực sự đạt cấu hình yêu cầu.

Remediation không thể khắc phục mọi vi phạm. Với một số trường hợp, cần cập nhật ứng dụng, thay đổi kiến trúc hoặc thực hiện thao tác thủ công có kiểm soát.

## 7. Theo dõi compliance và điều tra vi phạm

Azure Policy cung cấp dữ liệu tuân thủ theo assignment và tài nguyên. Trạng thái giúp người quản trị biết quy tắc nào đang được đáp ứng, quy tắc nào bị vi phạm và trường hợp nào cần điều tra thêm.

Một số trạng thái thường gặp:

- **Compliant:** tài nguyên đáp ứng policy hoặc điều kiện đánh giá không phát hiện vi phạm.
- **Non-compliant:** tài nguyên không đáp ứng policy.
- **Exempt:** tài nguyên được áp dụng exemption hợp lệ cho policy tương ứng.
- **Conflict:** có xung đột giữa các policy hoặc quy tắc áp dụng cần được điều tra.
- **Not started / Unknown / Error:** kết quả chưa được tạo, chưa xác định hoặc đánh giá gặp lỗi.

Không nên coi trạng thái chưa có kết quả là trạng thái compliant. Hãy kiểm tra thời điểm đánh giá, phạm vi assignment và lỗi của policy trước khi kết luận.

### Xem compliance bằng Azure Portal

Trong Azure Portal:

1. Tìm dịch vụ Policy.
2. Mở trang Compliance để xem tổng quan.
3. Lọc theo subscription, management group hoặc assignment.
4. Chọn assignment để xem các policy thành viên.
5. Chọn tài nguyên non-compliant để đọc lý do và chi tiết thuộc tính vi phạm.
6. Tạo exemption hoặc remediation nếu phù hợp với quy trình quản trị.

### Xem trạng thái bằng Azure CLI

Liệt kê assignment tại một subscription:

```bash
az policy assignment list --scope "/subscriptions/<SUBSCRIPTION_ID>" --output table
```

Xem các policy state gần đây:

```bash
az policy state list --subscription "<SUBSCRIPTION_ID>" --top 50 --output table
```

Yêu cầu Azure Policy thực hiện một lượt đánh giá lại tại subscription:

```bash
az policy state trigger-scan --subscription "<SUBSCRIPTION_ID>"
```

Đánh giá lại có thể mất thời gian. Sau khi trigger scan, hãy kiểm tra dữ liệu compliance sau khi quá trình đánh giá cập nhật; không giả định kết quả đã thay đổi ngay lập tức.

Khi cần báo cáo, nên lọc theo assignment, policy definition, resource ID hoặc khoảng thời gian để xác định nguyên nhân và nhóm chịu trách nhiệm. Với môi trường lớn, có thể tích hợp dữ liệu Azure Policy với các công cụ quản trị và giám sát để theo dõi xu hướng vi phạm.

## 8. Exemption và quản trị ngoại lệ

Không phải mọi tài nguyên đều có thể đáp ứng mọi policy ngay lập tức. Một số workload cũ, yêu cầu tương thích hoặc ràng buộc kỹ thuật có thể cần thời gian chuyển đổi.

Azure Policy hỗ trợ policy exemption để ghi nhận ngoại lệ có kiểm soát. Hai danh mục exemption thường dùng là:

- **Waiver:** tổ chức chấp thuận miễn áp dụng policy cho phạm vi được nêu.
- **Mitigated:** mục tiêu của policy đã được đáp ứng bằng một biện pháp thay thế hoặc kiểm soát khác.

Một exemption nên có:

- Tên và mô tả rõ ràng.
- Policy assignment liên quan.
- Phạm vi nhỏ nhất cần thiết.
- Danh mục exemption và lý do.
- Người hoặc nhóm chịu trách nhiệm.
- Ngày hết hạn nếu ngoại lệ chỉ có hiệu lực trong một giai đoạn.
- Bằng chứng hoặc tham chiếu tới quyết định phê duyệt theo quy trình nội bộ.

Exemption không thay đổi nội dung policy definition và không cấp quyền Azure RBAC. Nó ghi nhận rằng một phạm vi được miễn khỏi đánh giá của assignment theo exemption đã cấu hình.

Hãy rà soát exemption định kỳ. Khi hết thời hạn hoặc điều kiện ngoại lệ không còn, cần gỡ exemption và xác nhận tài nguyên đáp ứng policy.

## 9. Ví dụ triển khai một bộ quản trị

Giả sử nhóm nền tảng cần áp dụng baseline cho các workload mới trong subscription sản xuất.

**Mục tiêu**

- Chỉ cho phép hai Azure region đã được phê duyệt.
- Bắt buộc có tag `Owner` và `Environment`.
- Storage account phải bật truyền dữ liệu an toàn.
- Ghi nhận tài nguyên thiếu cấu hình chẩn đoán để nhóm vận hành xử lý.

**Thiết kế**

1. Chọn built-in policy phù hợp cho yêu cầu bảo mật storage và chẩn đoán.
2. Tạo custom policy kiểm tra tag bắt buộc và danh sách region.
3. Gom các policy thành initiative “Production workload baseline”.
4. Gán initiative ở subscription sản xuất, truyền danh sách region và tham số tag.
5. Bắt đầu với các quy tắc kiểm tra bằng `Audit` nếu cần đánh giá hiện trạng.
6. Theo dõi compliance, thông báo cho nhóm sở hữu tài nguyên và xử lý các vi phạm.
7. Chuyển các quy tắc đã ổn định sang `Deny` khi cần ngăn cấu hình sai phát sinh mới.
8. Với policy triển khai cấu hình chẩn đoán bằng `DeployIfNotExists`, cấu hình managed identity và cấp role cần thiết.
9. Tạo remediation task cho tài nguyên hiện có, sau đó kiểm tra deployment và compliance.
10. Ghi nhận các trường hợp ngoại lệ bằng exemption có lý do, phạm vi và thời hạn.

**Kết quả mong đợi**

Các workload mới được kiểm soát ngay từ lúc triển khai; tài nguyên cũ được phát hiện và xử lý theo lộ trình; nhóm nền tảng có thể xem trạng thái tuân thủ theo subscription và initiative. Việc áp dụng từng giai đoạn giúp giảm rủi ro làm gián đoạn ứng dụng đang vận hành.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Tài nguyên bị từ chối khi triển khai | Có assignment dùng effect `Deny` và yêu cầu không đáp ứng điều kiện | Đọc lỗi policy, xác nhận scope và tham số, cập nhật cấu hình hoặc xin exemption đúng quy trình |
| Tài nguyên vẫn non-compliant sau khi sửa | Chưa có lượt đánh giá mới, policy vẫn phát hiện thuộc tính vi phạm hoặc sửa sai tài nguyên | Trigger scan nếu cần, xem chi tiết compliance và kiểm tra lại điều kiện |
| Remediation task thất bại | Managed identity thiếu role, deployment template lỗi hoặc alias không hỗ trợ sửa | Đọc lỗi task/deployment, kiểm tra role assignment, scope và cấu hình policy |
| Initiative có policy thành viên không hoạt động như mong đợi | Tham số chưa ánh xạ đúng hoặc policy reference không đúng | Kiểm tra tham số initiative, policy reference ID và assignment |
| Không thấy tài nguyên trong báo cáo | Sai scope, tài nguyên ngoài phạm vi, exclusion hoặc evaluation chưa hoàn tất | Kiểm tra assignment kế thừa, notScopes, thời điểm đánh giá và loại tài nguyên |
| Policy mới chặn workload hiện tại | Chuyển sang effect thực thi khi chưa khảo sát tác động | Dùng Audit hoặc DoNotEnforce để đánh giá trước, lập kế hoạch sửa và chỉ bật enforcement sau khi xác nhận |

Khi điều tra, hãy bắt đầu từ assignment có hiệu lực đối với tài nguyên, kiểm tra policy definition và tham số, rồi mới xem remediation hoặc exemption. Cách này giúp xác định đúng lớp cấu hình gây ra vấn đề.

## 11. Thực hành

Thực hiện bài tập trên subscription thử nghiệm mà bạn được phép quản trị:

1. Mở Azure Policy và tìm một built-in policy kiểm tra vị trí triển khai hoặc tag.
2. Đọc policy definition, xác định điều kiện `if`, effect và các tham số.
3. Tạo assignment ở một resource group thử nghiệm hoặc scope phù hợp.
4. Chọn effect kiểm tra như `Audit` hoặc enforcement mode `DoNotEnforce` để quan sát trước.
5. Tạo hoặc chọn một tài nguyên đáp ứng và một tài nguyên không đáp ứng điều kiện trong môi trường thử nghiệm.
6. Mở Compliance và xác định trạng thái của từng tài nguyên.
7. Thử tạo một initiative chứa từ hai policy có liên quan và gán initiative ở scope thử nghiệm.
8. Nếu policy có effect `DeployIfNotExists` hoặc `Modify`, kiểm tra yêu cầu managed identity và quyền cần thiết; chỉ tạo remediation sau khi xác nhận quyền và phạm vi.
9. Ghi lại lý do của một trường hợp ngoại lệ giả định và mô tả cách tạo exemption có thời hạn.
10. Sau khi hoàn thành, xóa assignment thử nghiệm hoặc thu hồi các cấu hình thử nghiệm theo quy trình của môi trường.

**Tiêu chí hoàn thành:** bạn giải thích được policy definition khác assignment như thế nào; biết cách initiative gom các policy; phân biệt exclusion và exemption; đọc được compliance state; và xác định được khi nào remediation có thể tự động khắc phục tài nguyên hiện có.

## Kết luận

Azure Policy giúp tổ chức chuyển các tiêu chuẩn quản trị thành quy tắc có thể gán, đánh giá và theo dõi trên Azure. Policy definition mô tả từng quy tắc, initiative gom các quy tắc thành bộ tiêu chuẩn, còn assignment quyết định phạm vi và tham số áp dụng. Compliance cho biết mức độ đáp ứng; remediation hỗ trợ sửa tài nguyên hiện có khi effect và quyền của managed identity cho phép. Kết hợp các thành phần này với Azure RBAC, exemption có thời hạn và quy trình rà soát giúp tổ chức duy trì môi trường Azure nhất quán, an toàn và có thể kiểm toán.

