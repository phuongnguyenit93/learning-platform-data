# Xây dựng baseline bảo mật bằng Azure Policy

## 1. Vì sao cần một baseline bảo mật?

Khi vận hành nhiều subscription, resource group, mạng ảo, máy ảo, storage account và dịch vụ dữ liệu trên Microsoft Azure, mỗi nhóm có thể tạo tài nguyên theo cách khác nhau. Một nhóm bật truy cập Internet công khai cho dịch vụ dữ liệu, nhóm khác bỏ quên cấu hình ghi log, còn một số tài nguyên không có thông tin chủ sở hữu. Hệ thống có thể vẫn chạy bình thường nhưng mức độ rủi ro và chi phí kiểm tra thủ công tăng nhanh.

**Baseline bảo mật** là tập hợp các yêu cầu tối thiểu mà một tài nguyên hoặc môi trường phải đáp ứng. Baseline cần được diễn đạt thành quy tắc có thể kiểm tra và có người chịu trách nhiệm. Ví dụ:

- Tài nguyên production chỉ được triển khai tại các region đã phê duyệt.
- Tài nguyên phải có tag xác định môi trường và chủ sở hữu.
- Tài khoản lưu trữ phải dùng cấu hình truyền tải an toàn.
- Các dịch vụ dữ liệu nhạy cảm không được mở truy cập công khai nếu chưa có ngoại lệ.
- Tài nguyên quan trọng cần gửi nhật ký chẩn đoán đến nơi tập trung.
- Các trường hợp chưa đáp ứng baseline phải có người xử lý, thời hạn và bằng chứng chấp nhận rủi ro nếu được miễn trừ.

**Azure Policy** là dịch vụ quản trị dùng để định nghĩa, gán và đánh giá các quy tắc đối với tài nguyên được quản lý thông qua Azure Resource Manager (ARM). Khi phù hợp, Azure Policy còn có thể chặn yêu cầu cấu hình không được phép hoặc hỗ trợ sửa một số cấu hình bị lệch chuẩn.

Mục tiêu của bài học là đi từ yêu cầu bảo mật đến một baseline có thể triển khai, kiểm chứng và vận hành trên Azure, thay vì chỉ tạo một policy đơn lẻ.

## 2. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt Azure Policy với Azure RBAC và Microsoft Defender for Cloud.
2. Giải thích policy definition, initiative, assignment, scope, parameter, effect, compliance và exemption.
3. Thiết kế baseline theo các nhóm kiểm soát, ưu tiên các built-in policy phù hợp.
4. Lập kế hoạch triển khai từ chế độ đánh giá đến chặn vi phạm mà không làm gián đoạn tài nguyên hợp lệ.
5. Viết và đọc một policy definition kiểm tra tag.
6. Hiểu khi nào cần remediation task, managed identity và quyền RBAC.
7. Theo dõi trạng thái tuân thủ, xử lý ngoại lệ và duy trì baseline theo thời gian.

## 3. Azure Policy, RBAC và Defender for Cloud giải quyết những việc gì?

Ba cơ chế này hỗ trợ nhau nhưng không có cùng chức năng.

| Dịch vụ | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Azure RBAC** | Ai được phép thực hiện hành động nào ở scope nào? | Nhóm triển khai được quyền Contributor trên một resource group |
| **Azure Policy** | Tài nguyên được phép cấu hình ra sao, và cấu hình hiện tại có đáp ứng quy định không? | Chặn tạo tài nguyên ở region ngoài danh sách phê duyệt |
| **Microsoft Defender for Cloud** | Môi trường có các phát hiện, khuyến nghị và rủi ro bảo mật nào? | Đánh giá tư thế bảo mật và hiển thị đề xuất khắc phục |

Ví dụ, RBAC cho phép kỹ sư tạo storage account trong resource group. Azure Policy có thể từ chối một yêu cầu tạo storage account không đáp ứng quy định về cấu hình. Defender for Cloud có thể đưa ra khuyến nghị bảo mật liên quan đến tài nguyên hoặc môi trường đó.

Azure Policy cũng không thay thế các chính sách của Microsoft Entra Conditional Access, kiểm soát ứng dụng, quét mã độc, quản lý lỗ hổng hay phân tích log thời gian thực. Khi xây dựng baseline, chỉ đưa vào Azure Policy những kiểm soát thuộc phạm vi mà dịch vụ này có thể đánh giá hoặc thực thi.

## 4. Các thành phần của Azure Policy

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **Policy definition** | Định nghĩa một quy tắc, điều kiện và kết quả khi điều kiện khớp | Audit tài nguyên thiếu tag environment |
| **Policy rule** | Phần logic điều kiện if và hành động then | Nếu tag không tồn tại thì audit |
| **Effect** | Cách Azure Policy xử lý đối tượng phù hợp điều kiện | Audit, Deny, Modify, DeployIfNotExists |
| **Parameter** | Giá trị có thể truyền vào khi gán để tái sử dụng definition | Danh sách region cho phép |
| **Initiative / policy set definition** | Nhóm nhiều policy definition thành một bộ kiểm soát | Baseline cho subscription production |
| **Assignment** | Áp dụng policy hoặc initiative ở một scope với giá trị parameter cụ thể | Gán baseline cho management group production |
| **Scope** | Vị trí trong cây quản lý Azure mà assignment có hiệu lực | Management group, subscription, resource group |
| **Compliance state** | Kết quả đánh giá tài nguyên so với quy tắc | Compliant, Non-compliant hoặc trạng thái khác |
| **Remediation task** | Tác vụ xử lý tài nguyên hiện có phù hợp với effect hỗ trợ remediation | Triển khai diagnostic settings còn thiếu |
| **Exemption** | Miễn áp dụng đánh giá tuân thủ theo một ngoại lệ có quản lý | Ngoại lệ có hạn cho dịch vụ di sản |

Quan hệ khái niệm:

~~~mermaid
flowchart TD
    A[Yêu cầu bảo mật] --> B[Policy definitions]
    B --> C[Initiative: Security baseline]
    C --> D[Assignment tại scope]
    E[Parameters] --> D
    D --> F[Azure resources thuộc scope]
    F --> G[Policy evaluation]
    G --> H[Compliance state]
    G --> I[Effects theo quy tắc]
    I --> J[Chặn, audit hoặc hỗ trợ khắc phục]
    H --> K[Báo cáo và rà soát]
    K --> L[Điều chỉnh baseline và ngoại lệ]
~~~

**Definition** mô tả quy tắc; **assignment** mới áp dụng quy tắc vào môi trường cụ thể. Một definition có thể được gán nhiều lần với scope và parameter khác nhau. Một initiative giúp quản lý nhiều definition như một bộ baseline nhất quán.

## 5. Scope, kế thừa và loại trừ

Azure quản lý tài nguyên theo hệ thống phân cấp phổ biến:

~~~text
Tenant
└── Management group
    └── Subscription
        └── Resource group
            └── Resource
~~~

Assignment tại management group thường được kế thừa xuống các subscription và resource group bên dưới. Assignment tại subscription thường ảnh hưởng đến những tài nguyên phù hợp trong subscription đó. Có thể gán chính sách ở scope nhỏ hơn khi yêu cầu khác biệt hợp lý.

Ví dụ: doanh nghiệp có management group chung cho production và gán initiative baseline ở đó. Các subscription production mới được đưa vào nhánh quản lý này sẽ chịu ảnh hưởng của assignment theo phạm vi kế thừa, trừ các quy tắc loại trừ hoặc miễn trừ được cấu hình.

Cần phân biệt ba cơ chế:

- **Scope** xác định phạm vi bắt đầu áp dụng assignment.
- **Exclusion / notScopes** loại bỏ một hoặc nhiều scope con khỏi assignment. Tài nguyên thuộc phạm vi loại trừ không được assignment đó đánh giá theo cách thông thường.
- **Policy exemption** là ngoại lệ được ghi nhận đối với một assignment, có lý do, phân loại và có thể có thời hạn. Cơ chế này giúp quản lý quyết định chấp nhận một sai lệch có kiểm soát.

Không nên dùng danh sách loại trừ tùy tiện để che giấu vi phạm. Nếu một nhóm cần ngoại lệ, hãy ghi rõ tài nguyên, nguyên nhân, người phê duyệt, điều kiện bù đắp và ngày đánh giá lại.

**Lưu ý quyền truy cập:** Azure RBAC quyết định ai được tạo định nghĩa và assignment, ai có thể chỉnh sửa tài nguyên, cũng như ai được thực hiện remediation. Azure Policy không tự cấp mọi quyền cần thiết để sửa tài nguyên.

## 6. Hiểu các effect trước khi lựa chọn

Mỗi definition có effect xác định Azure Policy phản ứng ra sao khi điều kiện trong policy rule được đáp ứng.

| Effect | Hành vi khái quát | Khi nào phù hợp |
|---|---|---|
| **Audit** | Đánh dấu cấu hình không tuân thủ, không chặn yêu cầu tạo/cập nhật chỉ vì effect này | Giai đoạn khảo sát và giám sát |
| **Deny** | Từ chối các thao tác ARM phù hợp điều kiện vi phạm khi chính sách được thực thi | Ngăn cấu hình mới ngoài chuẩn |
| **Disabled** | Không áp dụng logic đánh giá/thực thi của definition theo effect đó | Tắt quy tắc theo mục đích có kiểm soát |
| **Append** | Bổ sung trường được chỉ định vào yêu cầu tài nguyên khi phù hợp | Bổ sung thuộc tính trong một số trường hợp hỗ trợ |
| **Modify** | Thay đổi một số thuộc tính/tag của yêu cầu; có thể hỗ trợ remediation tài nguyên hiện hữu | Chuẩn hóa tag hoặc cấu hình được hỗ trợ |
| **AuditIfNotExists** | Đánh giá sự tồn tại hoặc điều kiện của tài nguyên liên quan | Phát hiện thiếu cấu hình chẩn đoán |
| **DeployIfNotExists** | Khi đáp ứng điều kiện, triển khai tài nguyên liên quan nếu chưa tồn tại theo quy tắc | Hỗ trợ triển khai diagnostic settings còn thiếu |

Một số effect và tình huống sử dụng khác có thể được Azure bổ sung theo thời gian. Không phải mọi effect đều phù hợp mọi loại tài nguyên hoặc mọi thuộc tính; hãy kiểm tra policy definition và alias tương ứng.

### 6.1. Audit trước, Deny sau

Nếu một tổ chức đã có hàng nghìn tài nguyên, việc chuyển thẳng sang Deny có thể chặn những triển khai đang hoạt động. Cách tiếp cận an toàn hơn là:

1. Đánh giá bằng Audit hoặc cấu hình assignment với enforcement mode phù hợp cho giai đoạn quan sát.
2. Xem số lượng và nguyên nhân vi phạm.
3. Phân loại tài nguyên đang tồn tại, yêu cầu nghiệp vụ và ngoại lệ thật sự.
4. Điều chỉnh phạm vi, parameter, quy trình triển khai hoặc chuẩn hóa cấu hình.
5. Thử nghiệm quy tắc ngăn chặn trong môi trường nhỏ.
6. Kích hoạt thực thi chặn ở production sau khi đánh giá tác động.

**Deny không tự xóa hoặc sửa tài nguyên đã tồn tại.** Tài nguyên cũ vẫn có thể bị đánh dấu non-compliant, còn một thao tác tạo/cập nhật mới có thể bị chặn nếu không đáp ứng quy tắc.

### 6.2. Modify và DeployIfNotExists cần thêm bước vận hành

Effect **Modify** và **DeployIfNotExists** có thể liên quan tới managed identity của policy assignment và các role assignment đủ quyền để thao tác trên tài nguyên mục tiêu. Thông tin quyền thường được khai báo qua roleDefinitionIds trong chi tiết policy; nhóm vận hành cần cấu hình đúng quyền và scope, ưu tiên quyền tối thiểu.

Đối với **tài nguyên đã tồn tại**, việc bật assignment không có nghĩa mọi cấu hình cũ được sửa ngay. Thường cần tạo **remediation task** để xử lý non-compliant resources phù hợp. Hãy giám sát kết quả task và kiểm chứng các thay đổi thực tế. Triển khai diagnostic settings còn phụ thuộc đích log, loại tài nguyên hỗ trợ và những quyền cần thiết.

### 6.3. Enforcement mode và effect

Assignment có thiết lập **enforcement mode**. Trong một số kịch bản, **DoNotEnforce** cho phép đánh giá tuân thủ trong khi không thực thi các hành động của effect được kiểm soát bởi chế độ này. **Default** sử dụng cơ chế thực thi theo cấu hình chính sách.

Không nên đồng nhất **DoNotEnforce** với **Disabled**. Một lựa chọn thuộc assignment, lựa chọn còn lại là effect trong definition. Cả hai có hệ quả khác nhau với đánh giá, triển khai và báo cáo.

## 7. Chuyển yêu cầu bảo mật thành baseline có thể đo lường

Một baseline tốt bắt đầu từ rủi ro và yêu cầu nghiệp vụ. Mỗi kiểm soát nên trả lời được: áp dụng cho loại tài nguyên nào, tiêu chí đạt là gì, cách phát hiện vi phạm, ai xử lý và ngoại lệ được quản lý thế nào.

Ví dụ baseline tối thiểu cho ứng dụng chạy trong một số subscription Azure:

| Mã | Kiểm soát | Cách đánh giá dự kiến | Phạm vi đề xuất |
|---|---|---|---|
| SEC-01 | Chỉ triển khai tài nguyên ở region được phê duyệt | Allowed locations, hiệu lực theo giai đoạn | Các subscription production |
| SEC-02 | Tài nguyên có tag environment, owner và costCenter khi loại tài nguyên hỗ trợ | Tag audit/modify thích hợp | Resource groups và tài nguyên taggable |
| SEC-03 | Storage account yêu cầu truyền dữ liệu bảo mật và cấu hình TLS phù hợp | Built-in policy về HTTPS/TLS, kiểm tra tính năng/SKU | Storage accounts |
| SEC-04 | Hạn chế truy cập mạng công khai đối với dịch vụ dữ liệu nhạy cảm | Policy về public network access theo loại dịch vụ | Cơ sở dữ liệu và storage được xác định |
| SEC-05 | Bật diagnostic settings theo yêu cầu vận hành | AuditIfNotExists, DeployIfNotExists nếu có hỗ trợ | Dịch vụ có khả năng gửi diagnostics |
| SEC-06 | Hạn chế một số cấu hình hoặc SKU không được phê duyệt | Policy về loại tài nguyên/SKU cho phép nếu phù hợp | Môi trường có ràng buộc bảo mật rõ ràng |

Những dòng trên là **ví dụ thiết kế**, không chứng minh mọi built-in policy đều có mặt hoặc hỗ trợ mọi loại tài nguyên tại thời điểm triển khai. Phải tra cứu policy definition cụ thể, tham số, mode, effect, phiên bản và phạm vi hỗ trợ.

Cũng cần hiểu giới hạn: một policy yêu cầu tag không bảo đảm giá trị tag là đúng; policy kiểm tra bật log không bảo đảm log được giữ đủ lâu; cấu hình HTTPS không thay thế kiểm tra danh tính, bí mật và phân quyền dữ liệu.

## 8. Ưu tiên built-in policy và lập initiative

Azure cung cấp nhiều **built-in policy definitions** và **built-in initiatives**. Chúng là điểm khởi đầu hữu ích vì có các quy tắc phổ biến đã được đóng gói. Tuy nhiên, bạn vẫn cần đánh giá policy có phù hợp với môi trường, dịch vụ và tiêu chuẩn nội bộ hay không.

Quy trình lựa chọn:

1. Vào **Azure Portal → Policy → Definitions**.
2. Lọc theo loại **Built-in**, category hoặc từ khóa của kiểm soát.
3. Mở definition và đọc description, policy rule, mode, parameter, effect được hỗ trợ và các giới hạn.
4. Đối chiếu với yêu cầu SEC-01 đến SEC-06; ghi lại policyDefinitionId dùng cho từng kiểm soát.
5. Nếu không có built-in phù hợp, cân nhắc định nghĩa **Custom** với phạm vi và điều kiện rõ ràng.
6. Tạo **initiative** gom các definition tương ứng thành một baseline có tên, phiên bản và mô tả mục tiêu.
7. Chỉ định parameter tại initiative hoặc assignment theo môi trường, ví dụ danh sách location và tên tag bắt buộc.

Ví dụ đặt tên theo mục đích:

- **baseline-prod-security-v1**: tập hợp kiểm soát áp dụng cho production.
- **baseline-dev-security-v1**: biến thể có tham số hoặc yêu cầu khác cho môi trường phát triển.
- **SEC-01-allowed-locations**: mã nội bộ ánh xạ đến definition được chọn.

Tên mã kiểm soát do tổ chức đặt để theo dõi vòng đời, không phải định danh policy có sẵn của Microsoft. Nên lưu ánh xạ từ mã kiểm soát đến policy definition, owner, phiên bản và rationale để tránh nhầm lẫn khi built-in policy thay đổi.

## 9. Ví dụ một custom policy definition: audit tag environment

Để hiểu cấu trúc cơ bản, dưới đây là ví dụ policy definition ở dạng JSON có thể dùng làm cơ sở xây dựng definition khi cần tùy chỉnh. Mục tiêu: phát hiện tài nguyên hỗ trợ tag nhưng thiếu tag **environment**.

~~~json
{
  "properties": {
    "displayName": "Audit resources without environment tag",
    "description": "Mark taggable resources without the required environment tag.",
    "policyType": "Custom",
    "mode": "Indexed",
    "parameters": {
      "tagName": {
        "type": "String",
        "metadata": {
          "displayName": "Required tag name"
        },
        "defaultValue": "environment"
      }
    },
    "policyRule": {
      "if": {
        "field": "[concat('tags[', parameters('tagName'), ']')]",
        "exists": "false"
      },
      "then": {
        "effect": "audit"
      }
    }
  }
}
~~~

Giải thích từng phần:

- **properties** chứa mô tả và các thành phần của định nghĩa.
- **policyType: Custom** cho biết đây là policy do tổ chức định nghĩa.
- **mode: Indexed** hướng đến những loại tài nguyên có hỗ trợ tag và location theo cơ chế Index; không phải kiểm tra tổng quát mọi loại tài nguyên.
- **parameters.tagName** cho phép thay tên tag mà không phải viết lại logic.
- **field** sử dụng biểu thức Policy để truy cập tag theo tên được truyền vào.
- **exists: false** chọn tài nguyên không có tag cần kiểm tra.
- **effect: audit** đánh dấu vi phạm; không tự bổ sung tag và không từ chối thao tác tạo tài nguyên.

**Giới hạn của ví dụ:** policy này chỉ kiểm tra *sự tồn tại* của tag, không kiểm tra nội dung tag hợp lệ hay giá trị rỗng. Để yêu cầu giá trị thuộc một danh sách cho phép hoặc bảo vệ riêng resource group, cần thiết kế quy tắc phù hợp và kiểm tra mode/alias. Không nên gán ví dụ trên cho toàn doanh nghiệp rồi coi đó là một baseline bảo mật hoàn chỉnh.

Trong Portal, khi tạo custom policy definition, giao diện có thể yêu cầu nhập nội dung JSON theo định dạng của trình biên tập. Hãy kiểm tra các trường mà giao diện quản lý riêng trước khi dán toàn bộ cấu trúc có **properties**.

## 10. Gán initiative vào scope và cấu hình tham số

Sau khi đã có initiative **baseline-prod-security-v1**, nhóm quản trị có thể áp dụng nó ở subscription thử nghiệm trước, rồi mở rộng theo management group production khi đã xác minh hành vi.

Trong **Azure Portal → Policy → Assignments → Assign policy**:

1. Chọn **Scope** phù hợp, ví dụ subscription thử nghiệm.
2. Chọn **Policy definition / initiative** muốn áp dụng.
3. Đặt tên và mô tả assignment giúp phân biệt phiên bản baseline.
4. Xem xét **Exclusions**; chỉ loại trừ scope có lý do rõ ràng.
5. Cấu hình **Parameters** như allowed locations, tag name hoặc effect nếu definition hỗ trợ.
6. Cân nhắc **Enforcement mode** trong giai đoạn khảo sát.
7. Nếu initiative có **Modify** hoặc **DeployIfNotExists**, cấu hình managed identity và role assignment theo hướng dẫn tương ứng.
8. Xem lại tab Review, xác nhận scope/parameter/hiệu lực, rồi tạo assignment.
9. Theo dõi kết quả compliance sau khi đánh giá.

Ví dụ, cùng một initiative có thể nhận danh sách allowed locations khác nhau giữa môi trường phát triển và production. Khi quản lý bằng IaC, lưu rõ giá trị parameter trong mã cấu hình thay vì nhập thủ công nhiều lần.

**Cảnh báo về kế thừa:** assignment ở management group có thể ảnh hưởng đến nhiều subscription thuộc nhánh. Trước khi áp dụng Deny ở cấp cao, kiểm kê đầy đủ các nhóm ứng dụng và kiểm thử triển khai của họ.

## 11. Kiểm tra kết quả tuân thủ

Sau khi assignment được tạo, Azure Policy đánh giá những tài nguyên liên quan theo cơ chế dịch vụ. Dữ liệu compliance không nhất thiết cập nhật tức thì; thao tác tạo/cập nhật, thay đổi assignment hoặc chu kỳ đánh giá có thể kích hoạt đánh giá lại.

Trong **Azure Portal → Policy → Compliance**, bạn có thể:

1. Chọn scope và assignment/initiative.
2. Xem tổng quan số lượng tài nguyên compliant và non-compliant.
3. Mở một policy cụ thể để thấy những tài nguyên không đáp ứng.
4. Xem lý do, điều kiện và thuộc tính liên quan khi dữ liệu có sẵn.
5. Xác định nhóm sở hữu tài nguyên và tạo kế hoạch xử lý.
6. Đánh giá lại sau khi đã sửa hoặc sau khi scan cập nhật.

Các trạng thái có thể bao gồm **Compliant**, **Non-compliant**, **Exempt**, **Conflicting**, **Not started**, **Not registered** hoặc các trạng thái tương tự tùy trường hợp và giao diện. Không phải mọi tài nguyên đều luôn có kết quả đánh giá; phạm vi, kiểu policy, điều kiện existence, độ trễ và dữ liệu được lập chỉ mục đều có thể ảnh hưởng.

Một báo cáo baseline có thể có cấu trúc:

| Kiểm soát | Tài nguyên cần đánh giá | Vi phạm | Owner xử lý | Hạn khắc phục |
|---|---:|---:|---|---|
| SEC-01 Region | 120 | 3 | Cloud Platform | Theo mức độ ưu tiên |
| SEC-02 Tag | 120 | 18 | Từng nhóm ứng dụng | Theo kế hoạch chuẩn hóa |
| SEC-03 HTTPS/TLS | 28 | 2 | Storage Team | Theo mức độ rủi ro |
| SEC-05 Diagnostic settings | 35 | 7 | Observability Team | Theo kế hoạch logging |

Các con số trên chỉ là minh họa. Khi tổng hợp kết quả thật, ghi rõ scope, thời điểm xuất báo cáo, filter, phiên bản initiative và các exemption có hiệu lực. Tổng phần trăm compliant không thể được coi là chứng nhận hệ thống an toàn tuyệt đối.

## 12. Remediation: xử lý tài nguyên đã tồn tại

Đối với policy có effect thích hợp, **remediation task** có thể giúp đưa tài nguyên non-compliant về trạng thái mong muốn. Ví dụ: một policy DeployIfNotExists được thiết kế để triển khai diagnostic settings còn thiếu và gửi log về Log Analytics workspace được chỉ định.

Quy trình thực tế:

1. Xác định policy và loại tài nguyên hỗ trợ remediation.
2. Kiểm tra điều kiện đánh giá, deployment template/operations trong definition và các parameter như workspace ID.
3. Cấu hình managed identity cho assignment khi policy yêu cầu.
4. Cấp các vai trò tối thiểu mà remediation cần để sửa hoặc tạo cấu hình liên quan.
5. Kiểm tra tài nguyên sẽ bị tác động và phê duyệt thay đổi theo quy trình.
6. Tạo **remediation task** trong trải nghiệm Azure Policy.
7. Theo dõi task để phát hiện các tài nguyên thành công, thất bại hoặc bị bỏ qua.
8. Kiểm tra trực tiếp tài nguyên và đích log; sau đó đối chiếu compliance state khi được cập nhật.

**Phân biệt:** Audit và Deny không tự sửa vi phạm cũ. Modify và DeployIfNotExists có thể hỗ trợ remediation tùy định nghĩa và loại tài nguyên; việc hỗ trợ không đồng nghĩa mọi trường hợp đều có thể khắc phục tự động.

Lỗi remediation hay gặp là identity thiếu quyền, resource provider không hỗ trợ thuộc tính cần sửa, deployment template không phù hợp, thiếu tham số đích log hoặc điều kiện tồn tại được định nghĩa sai. Kiểm tra kết quả task và chi tiết deployment trước khi chạy lại hàng loạt.

## 13. Quản lý ngoại lệ mà vẫn kiểm soát được rủi ro

Có những trường hợp cần tiếp tục chạy tài nguyên đang khác baseline, chẳng hạn hệ thống di sản chưa hỗ trợ cấu hình mới. Thay vì âm thầm bỏ scope khỏi baseline, tổ chức nên ghi nhận quyết định bằng **policy exemption** khi phù hợp.

Một exemption có thể gồm:

- Assignment và phạm vi tài nguyên được miễn.
- **Exemption category**, chẳng hạn **Waiver** (chấp nhận ngoại lệ theo quyết định) hoặc **Mitigated** (rủi ro đã được xử lý bằng biện pháp khác).
- Lý do kinh doanh/kỹ thuật và bằng chứng liên quan.
- Owner, người phê duyệt, mã thay đổi hoặc ticket nội bộ.
- Thời gian hết hiệu lực, nếu phù hợp với chính sách tổ chức.
- Biện pháp bù đắp và kế hoạch đưa tài nguyên về baseline.

Ví dụ: ứng dụng cũ chỉ hoạt động ở region chưa nằm trong danh sách mới. Nhóm vận hành đề xuất exemption có hạn, ghi giải pháp chuyển vùng và mốc kiểm tra tiếp theo. Đến hạn, phải gia hạn theo quy trình hoặc khắc phục sai lệch.

**Exemption không làm thay đổi bản thân cấu hình tài nguyên.** Nó thể hiện một quyết định quản trị đối với đánh giá chính sách. Khi ngoại lệ kết thúc, cần kiểm tra lại tác động của assignment và các thao tác triển khai tiếp theo.

## 14. Duy trì baseline bằng Policy as Code

Một baseline lớn không nên chỉ tồn tại dưới dạng thao tác bấm thủ công trong Portal. Quản lý bằng mã giúp xem lại thay đổi, triển khai nhất quán và phục hồi cấu hình.

Các thành phần nên quản lý có phiên bản:

- Custom policy definitions và policy rule.
- Initiatives cùng danh sách policy definition được tham chiếu.
- Assignments theo management group/subscription/resource group.
- Parameters theo từng môi trường.
- Exclusions, exemptions và metadata theo quy trình được kiểm soát.
- Tài liệu ánh xạ kiểm soát với yêu cầu bảo mật và owner.

Công cụ thường dùng là **Bicep/ARM** hoặc Terraform với quy trình CI/CD phù hợp. Ví dụ lệnh kiểm tra triển khai Bicep tại subscription khi đã có file template được nhóm chuẩn bị:

~~~bash
az deployment sub what-if \
  --location southeastasia \
  --template-file security-baseline.bicep
~~~

Lệnh minh họa trên giả định nhóm đã có template Bicep hợp lệ. **What-if** giúp xem các thay đổi dự kiến nhưng không thay thế kiểm thử hành vi thực tế của policy trên tài nguyên đích. Việc áp dụng template cần được kiểm soát qua quy trình phê duyệt và triển khai riêng.

Khi built-in policy thay đổi hoặc tổ chức cập nhật chuẩn bảo mật, cần kiểm tra ảnh hưởng tới định nghĩa, parameter, hiệu ứng và trạng thái compliance; tránh coi tên policy trùng nhau là đủ để bảo đảm hành vi không thay đổi.

## 15. Azure CLI để kiểm tra policy đã gán

Trong môi trường có Azure CLI và tài khoản đã đăng nhập, bạn có thể xem những assignment hiện có:

~~~bash
az login
az account set --subscription "<subscription-id>"

az policy assignment list \
  --scope "/subscriptions/<subscription-id>" \
  --output table
~~~

Kiểm tra trạng thái tổng hợp của policy tại subscription:

~~~bash
az policy state summarize \
  --subscription "<subscription-id>" \
  --output json
~~~

Liệt kê một số kết quả policy state để phân tích:

~~~bash
az policy state list \
  --subscription "<subscription-id>" \
  --top 20 \
  --output json
~~~

Yêu cầu đánh giá lại tại resource group nếu cần:

~~~bash
az policy state trigger-scan \
  --resource-group "rg-baseline-lab"
~~~

Các lệnh được minh họa với placeholder, yêu cầu có quyền và phần mở rộng/công cụ được hỗ trợ trong phiên bản Azure CLI đang sử dụng. Lệnh **trigger-scan** yêu cầu đánh giá lại nhưng kết quả không phải lúc nào cũng xuất hiện tức thì. Khi làm báo cáo, luôn ghi thời điểm quét, thời điểm truy vấn và scope.

Các lệnh đọc trạng thái cũng phụ thuộc quyền truy cập. Nếu kết quả trống, hãy kiểm tra scope và assignment trước khi kết luận không có policy nào được áp dụng.

## 16. Kịch bản triển khai baseline cho hệ thống sản xuất

Giả sử công ty có ứng dụng thương mại điện tử trên Azure, gồm API, VM, VNet, Azure Storage và một dịch vụ cơ sở dữ liệu. Các tài nguyên nằm trong nhiều resource group của subscription production.

### Giai đoạn A: Đánh giá hiện trạng

- Liệt kê subscription, resource group và loại tài nguyên.
- Kiểm tra region, tag, cấu hình mạng công khai và diagnostic settings.
- Xác định các ngoại lệ có lý do hợp lệ.
- Chọn một tập kiểm soát ban đầu: SEC-01 đến SEC-05.
- Xác định người chịu trách nhiệm và mức ưu tiên sửa từng sai lệch.

### Giai đoạn B: Thử nghiệm

- Tạo initiative baseline và gán tại subscription sandbox.
- Dùng hiệu ứng Audit hoặc chế độ thử nghiệm phù hợp để đánh giá mà chưa chặn các quy trình hợp lệ.
- Triển khai một tài nguyên đúng chuẩn và một tài nguyên cố ý thiếu tag.
- Xác minh logic compliance nhận diện đúng đối tượng.
- Thử Deny trên một policy đã hiểu rõ, trong phạm vi thử nghiệm.
- Kiểm tra rằng deployment hợp lệ không bị chặn và thông báo lỗi vi phạm dễ hiểu.

### Giai đoạn C: Áp dụng có kiểm soát

- Triển khai initiative tại scope production đã phê duyệt.
- Bật Deny với những yêu cầu quan trọng và đã kiểm thử.
- Dùng Modify/DeployIfNotExists khi có policy, quyền và template phù hợp.
- Tạo remediation task cho tài nguyên cũ được chọn.
- Theo dõi các hoạt động bị từ chối và phản hồi của nhóm ứng dụng.

### Giai đoạn D: Vận hành liên tục

- Đưa compliance report vào lịch kiểm tra thường kỳ.
- Mở công việc xử lý với owner và thời hạn cho từng vi phạm quan trọng.
- Theo dõi exemption và đánh giá lại trước khi hết hạn.
- Cập nhật baseline khi thêm dịch vụ, region hoặc yêu cầu bảo mật.
- Dùng kiểm soát phiên bản và review khi thay đổi effect, scope hoặc danh sách policy.

Mục tiêu không phải đạt một con số báo cáo đẹp bằng cách loại trừ mọi tài nguyên khó xử lý; mục tiêu là giảm rủi ro thực tế và cung cấp bằng chứng rõ ràng cho từng quyết định.

## 17. Các lỗi thiết kế thường gặp

**Gán Deny quá sớm ở management group.** Các nhóm có thể bị chặn triển khai trước khi hiểu tác động. Hãy bắt đầu ở scope thử nghiệm, kiểm tra deployment pipeline và rollout theo giai đoạn.

**Chọn policy theo tên mà không xem rule.** Một built-in policy có thể có parameter hoặc effect khác kỳ vọng; phải đọc definition và kiểm tra behavior.

**Nhầm compliance với hoàn toàn an toàn.** Azure Policy có giới hạn phạm vi, đặc biệt với dữ liệu, quyền truy cập trong ứng dụng và các cấu hình không thể quan sát qua ARM.

**Tin rằng assignment tự sửa mọi tài nguyên.** Remediation cho tài nguyên hiện hữu có thể cần task, identity, quyền và một deployment hợp lệ.

**Bỏ qua chi phí và tác động vận hành.** Diagnostic settings có thể tạo thêm lưu lượng và chi phí log; các cấu hình chặn mạng công khai có thể yêu cầu sửa ứng dụng, DNS hoặc private endpoint.

**Cấp quá nhiều quyền cho identity remediation.** Chỉ cấp quyền cần thiết theo scope đã xác định, đánh giá thường xuyên và theo dõi các thay đổi do automation tạo ra.

**Không ghi rõ ngoại lệ.** Exclusions hoặc exemptions không có thời hạn và owner dễ biến thành khoảng trống lâu dài trong baseline.

**Không kiểm soát khác biệt giữa các môi trường.** Production và development có thể cần tham số khác nhau, nhưng các ngoại lệ phải được mô tả rõ và có review.

## 18. Bài thực hành: tạo baseline tag ở scope thử nghiệm

**Yêu cầu:** bạn có quyền tạo policy definition/assignment ở môi trường sandbox, có một resource group thử nghiệm và ít nhất một tài nguyên hỗ trợ tag.

**Bước 1.** Chọn kiểm soát: mọi tài nguyên hỗ trợ tag trong resource group phải có tag **environment**.

**Bước 2.** Tạo custom definition với effect **Audit** dựa trên JSON ở mục 9, hoặc chọn built-in policy tương đương sau khi xác minh rule.

**Bước 3.** Gán policy vào resource group thử nghiệm, không thêm exclusion, bảo đảm hiệu ứng đang ở chế độ kiểm tra thích hợp.

**Bước 4.** Tạo hoặc sử dụng hai tài nguyên thử nghiệm thuộc loại policy hỗ trợ: một tài nguyên có tag **environment=dev**, một tài nguyên không có tag này. Tránh tạo tài nguyên tốn phí không cần thiết.

**Bước 5.** Chạy đánh giá hoặc chờ policy compliance cập nhật, sau đó mở danh sách tài nguyên tương ứng trong **Policy → Compliance**.

**Bước 6.** Kiểm tra tài nguyên thiếu tag có được báo non-compliant trong khi tài nguyên có tag đáp ứng kiểm tra hay không. Nếu chưa thấy, xem scope, mode, trạng thái indexing và thời gian đánh giá.

**Bước 7.** Bổ sung tag cho tài nguyên chưa đạt bằng công cụ quản trị hợp lệ. Đánh giá lại và theo dõi đến khi kết quả phản ánh thay đổi.

**Bước 8.** Ghi lại ID của definition/assignment, scope, effect, số tài nguyên đạt/không đạt, thời điểm đánh giá và nguyên nhân nếu kết quả khác kỳ vọng.

**Bước 9.** Xóa tài nguyên thử nghiệm và assignment/definition dành riêng cho bài lab khi không còn cần, theo quyền và quy trình quản lý môi trường thử nghiệm.

**Tiêu chí hoàn thành:** người học giải thích được tại sao assignment có thể phát hiện tài nguyên thiếu tag, tại sao Audit không tự sửa lỗi, và tại sao cần đúng scope, mode cùng loại tài nguyên hỗ trợ.

## 19. Câu hỏi tự kiểm tra

1. Chính sách SEC-01 nên gán ở management group hay resource group khi áp dụng cho toàn bộ production? Lựa chọn đó ảnh hưởng đến kế thừa như thế nào?
2. Vì sao policy definition chưa đủ để bảo vệ tài nguyên nếu chưa có assignment?
3. Khác biệt về tác động giữa **Audit**, **Deny** và **DeployIfNotExists** là gì?
4. Khi assignment DeployIfNotExists đã bật nhưng một số tài nguyên cũ vẫn thiếu diagnostic settings, cần kiểm tra gì?
5. Khi nào nên dùng exemption thay vì exclusion trong một trường hợp lệch chuẩn có thời hạn?
6. Tại sao baseline Azure Policy không thể thay thế Azure RBAC, Conditional Access hoặc Defender for Cloud?
7. Bạn sẽ ghi lại những trường nào để có thể kiểm toán một ngoại lệ sau sáu tháng?

## 20. Tổng kết

**Azure Policy giúp chuyển yêu cầu bảo mật thành các quy tắc có thể đánh giá và thực thi trên tài nguyên Azure.** Một baseline có tính vận hành cần có định nghĩa chính xác, initiative, assignment ở scope phù hợp, parameter theo môi trường, lựa chọn effect có kiểm soát, báo cáo compliance, remediation và quản lý exemption.

Hãy xây dựng baseline từ các yêu cầu đo lường được, ưu tiên built-in policy đã kiểm tra, thử nghiệm ở scope nhỏ, đánh giá tác động trước khi bật Deny và quản lý vòng đời bằng mã. Kết hợp Azure Policy với RBAC, Microsoft Entra ID, giám sát và quy trình quản trị thay đổi để bảo vệ kiến trúc ứng dụng Azure một cách nhất quán.
