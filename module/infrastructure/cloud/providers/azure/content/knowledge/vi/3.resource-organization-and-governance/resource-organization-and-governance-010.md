# Theo dõi thay đổi tài nguyên bằng Activity Log

Khi vận hành Azure, việc biết tài nguyên đang tồn tại là chưa đủ. Nhóm vận hành còn cần trả lời được: ai đã tạo, sửa hoặc xóa tài nguyên; thao tác diễn ra khi nào; thao tác thành công hay thất bại; và thay đổi đó thuộc subscription nào. **Azure Activity Log** cung cấp lịch sử các sự kiện ở lớp quản lý Azure để giúp điều tra thay đổi, kiểm tra hoạt động quản trị và phát hiện thao tác bất thường.

Bài học thuộc chương **Tổ chức và quản trị tài nguyên** của module `CLOUD_PROVIDERS_AZURE`. Trong module này, bạn khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; đồng thời học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí cho một kiến trúc ứng dụng.

## 1. Activity Log ghi nhận điều gì?

Azure Activity Log là nhật ký nền tảng do Azure tạo ra, ghi lại các sự kiện ở **control plane** (lớp quản lý tài nguyên). Những sự kiện thường gặp gồm:

- Tạo, cập nhật hoặc xóa tài nguyên, chẳng hạn virtual machine, virtual network, storage account hoặc resource group.
- Thay đổi cấu hình quản lý, ví dụ cập nhật cấu hình mạng hoặc thay đổi thuộc tính của tài nguyên.
- Thay đổi quyền Azure RBAC, chẳng hạn tạo hoặc xóa role assignment.
- Thao tác liên quan đến Azure Policy, autoscale và các hoạt động quản trị khác.
- Sự kiện tình trạng dịch vụ Azure, tình trạng tài nguyên, cảnh báo và khuyến nghị từ nền tảng.

Activity Log được tổ chức theo **subscription**. Một người có quyền đọc nhật ký của subscription có thể xem các sự kiện trong phạm vi được cấp quyền, kể cả khi sự kiện liên quan đến nhiều resource group hoặc loại tài nguyên khác nhau.

### Control plane và data plane

Cần phân biệt Activity Log với nhật ký thao tác bên trong một dịch vụ:

| Loại hoạt động | Ví dụ | Nơi thường tìm thông tin |
|---|---|---|
| Control plane | Tạo storage account, đổi cấu hình firewall, xóa virtual machine, cấp role assignment | Azure Activity Log |
| Data plane | Đọc hoặc ghi blob, truy vấn dữ liệu, truy cập bảng hoặc hàng đợi | Nhật ký tài nguyên/dịch vụ (resource logs), nếu dịch vụ hỗ trợ và đã bật thu thập |

Ví dụ, thao tác tạo storage account được ghi trong Activity Log. Việc một ứng dụng đọc một blob cụ thể thuộc data plane và cần cấu hình nhật ký phù hợp cho dịch vụ lưu trữ. Vì vậy, không nên coi Activity Log là bản ghi đầy đủ mọi hoạt động của ứng dụng.

Activity Log cũng khác với Microsoft Entra audit logs. Entra audit logs ghi lại các thay đổi trong thư mục danh tính, chẳng hạn tạo người dùng hoặc thay đổi nhóm. Activity Log tập trung vào các sự kiện quản lý tài nguyên Azure trong subscription. Khi điều tra một thay đổi quyền, có thể cần đối chiếu cả hai nguồn nếu có thao tác liên quan đến danh tính và tài nguyên.

## 2. Các nhóm sự kiện trong Activity Log

Azure phân loại sự kiện theo category. Các nhóm thường gặp gồm:

| Category | Nội dung | Ví dụ tình huống cần theo dõi |
|---|---|---|
| `Administrative` | Các thao tác quản trị trên tài nguyên và cấu hình Azure. | Tạo, cập nhật, xóa tài nguyên; thay đổi role assignment. |
| `Security` | Sự kiện liên quan đến bảo mật do nền tảng phát ra. | Một số sự kiện bảo mật hoặc cảnh báo bảo mật từ dịch vụ Azure. |
| `ServiceHealth` | Sự kiện tình trạng dịch vụ Azure. | Sự cố dịch vụ, bảo trì hoặc thông báo ảnh hưởng đến dịch vụ. |
| `ResourceHealth` | Tình trạng sức khỏe của tài nguyên cụ thể. | Tài nguyên bị ảnh hưởng hoặc chuyển sang trạng thái không khả dụng. |
| `Alert` | Sự kiện liên quan đến cảnh báo của Azure. | Cảnh báo được kích hoạt hoặc thay đổi trạng thái. |
| `Recommendation` | Khuyến nghị do dịch vụ Azure cung cấp. | Khuyến nghị tối ưu hoặc cải thiện cấu hình. |
| `Policy` | Sự kiện đánh giá hoặc thực thi Azure Policy. | Tài nguyên không tuân thủ hoặc bị từ chối bởi chính sách. |
| `Autoscale` | Sự kiện liên quan đến autoscale. | Một quy tắc tự động mở rộng hoặc thu hẹp số lượng instance. |

Khi mục tiêu là kiểm tra ai đã thay đổi cấu hình, hãy bắt đầu với `Administrative`. Nếu sự kiện liên quan đến việc một thao tác bị chính sách từ chối, hãy xem thêm `Policy`. Nếu ứng dụng bị ảnh hưởng bởi sự cố nền tảng, kiểm tra `ServiceHealth` và `ResourceHealth`.

## 3. Đọc một sự kiện Activity Log

Mỗi sự kiện chứa các trường mô tả thời điểm, chủ thể, thao tác, tài nguyên và kết quả. Tên trường hiển thị trong Azure Portal có thể khác cách đặt tên trong JSON hoặc bảng Log Analytics.

| Trường | Ý nghĩa | Câu hỏi giúp trả lời |
|---|---|---|
| `eventTimestamp` | Thời điểm sự kiện xảy ra theo UTC. | Thay đổi xảy ra lúc nào? |
| `submissionTimestamp` | Thời điểm sự kiện được gửi/ghi nhận vào hệ thống nhật ký. | Khi nào sự kiện được đưa vào Activity Log? |
| `caller` | Danh tính hoặc chủ thể khởi tạo thao tác, có thể là người dùng, service principal hoặc danh tính workload. | Ai hoặc thành phần nào đã thực hiện? |
| `operationName` | Tên thao tác mà resource provider thực hiện. | Đã gọi hành động quản lý nào? |
| `status` | Trạng thái của thao tác, ví dụ Started, Succeeded hoặc Failed. | Thao tác thành công hay thất bại? |
| `resourceId` | Đường dẫn định danh tài nguyên Azure bị tác động. | Tài nguyên nào bị thay đổi? |
| `resourceGroupName` | Tên resource group liên quan, nếu có. | Tài nguyên thuộc nhóm nào? |
| `correlationId` | Mã dùng để liên kết các sự kiện có liên quan trong một luồng thao tác. | Những sự kiện nào thuộc cùng một lần thực hiện? |
| `level` | Mức độ sự kiện, chẳng hạn Informational, Warning hoặc Error. | Sự kiện có mức độ nào? |
| `properties` | Các thuộc tính bổ sung tùy theo loại sự kiện và resource provider. | Có thêm chi tiết nào về thao tác? |

Không phải sự kiện nào cũng có đủ mọi trường hoặc cùng một cấu trúc `properties`. Khi điều tra, hãy mở phần chi tiết hoặc JSON của sự kiện thay vì giả định mọi event có cùng dữ liệu.

### Phân biệt thời điểm xảy ra và thời điểm ghi nhận

`eventTimestamp` cho biết thời điểm thao tác xảy ra; `submissionTimestamp` cho biết thời điểm sự kiện được gửi vào hệ thống nhật ký. Hai mốc có thể khác nhau. Khi dựng dòng thời gian, hãy dùng thời điểm sự kiện làm mốc chính và lưu ý độ trễ ghi nhận nếu cần đối chiếu với log của ứng dụng hoặc hệ thống bên ngoài.

### Caller không phải lúc nào cũng là con người

Trường `caller` có thể đại diện cho tài khoản người dùng, ứng dụng, service principal hoặc một danh tính được dịch vụ sử dụng. Nếu thấy tên ứng dụng hoặc danh tính tự động hóa, hãy đối chiếu với lịch triển khai, pipeline hoặc cấu hình workload identity. Không nên kết luận một cá nhân đã thao tác chỉ từ tên hiển thị của một service principal.

`correlationId` đặc biệt hữu ích khi một hành động tạo ra nhiều sự kiện ở các bước khác nhau. Hãy dùng mã này để tìm các event liên quan thay vì chỉ lọc theo một tên tài nguyên.

## 4. Xem Activity Log trong Azure Portal

Bạn có thể xem nhật ký ở cấp subscription hoặc từ trang của một tài nguyên cụ thể.

### Xem nhật ký của subscription

1. Đăng nhập [Azure Portal](https://portal.azure.com/) bằng tài khoản có quyền đọc Activity Log.
2. Mở **Monitor** rồi chọn **Activity log**. Bạn cũng có thể mở **Subscriptions**, chọn subscription cần kiểm tra và chọn **Activity log**.
3. Xác nhận đúng tenant và subscription. Đối chiếu Subscription ID nếu có nhiều subscription tên gần giống nhau.
4. Chọn khoảng thời gian cần điều tra.
5. Lọc theo subscription, resource group, resource, category, operation, status hoặc caller tùy theo mục tiêu.
6. Chọn một sự kiện để xem phần tóm tắt và chi tiết JSON.

### Xem nhật ký của một tài nguyên

1. Mở tài nguyên cần điều tra, ví dụ một virtual machine hoặc storage account.
2. Trong menu tài nguyên, chọn **Activity log**.
3. Đặt khoảng thời gian và xem các thao tác liên quan đến tài nguyên đó.
4. Mở từng event để kiểm tra caller, operation, status, timestamp và correlation ID.

### Ví dụ điều tra một thay đổi

Giả sử một virtual network trong môi trường Production bất ngờ có cấu hình thay đổi. Bạn có thể:

1. Mở Activity Log của subscription Production và đặt khoảng thời gian từ lúc phát hiện sự cố trở về trước.
2. Lọc category `Administrative`, resource group chứa virtual network và các thao tác cập nhật liên quan.
3. Tìm event có operation phù hợp, sau đó kiểm tra `caller`, `eventTimestamp` và `status`.
4. Nếu caller là tài khoản tự động hóa, đối chiếu `correlationId` và thời điểm với pipeline triển khai.
5. Mở các event cùng correlation ID để xem toàn bộ chuỗi thao tác.
6. Ghi lại Subscription ID, resource ID, thời gian UTC, caller, operation, trạng thái và bằng chứng JSON cần thiết.

Activity Log cho biết thao tác quản lý đã được yêu cầu và kết quả của thao tác. Nhật ký này có thể không chứa đầy đủ giá trị cấu hình cũ và mới của từng thuộc tính. Nếu cần biết chính xác thuộc tính nào đã đổi từ giá trị nào sang giá trị nào, hãy dùng thêm tính năng Change Analysis/Change history hoặc cơ chế theo dõi cấu hình phù hợp với loại tài nguyên.

## 5. Truy vấn Activity Log bằng Azure CLI

Azure CLI hữu ích khi cần tìm kiếm lặp lại, lưu kết quả hoặc đưa việc kiểm tra vào quy trình vận hành.

### Liệt kê sự kiện trong một khoảng thời gian

```bash
az monitor activity-log list \
  --subscription "<SUBSCRIPTION_ID>" \
  --start-time "<START_UTC>" \
  --end-time "<END_UTC>" \
  --query "[].{Time:eventTimestamp, Caller:caller, Operation:operationName.localizedValue, Status:status.localizedValue, Resource:resourceId, Correlation:correlationId}" \
  --output table
```

Thay các placeholder bằng Subscription ID và thời gian UTC theo định dạng ISO 8601, ví dụ `2026-11-20T08:00:00Z`. Chọn khoảng thời gian phù hợp với sự cố và kiểm tra lại subscription trước khi chạy lệnh.

### Giới hạn theo resource group

```bash
az monitor activity-log list \
  --subscription "<SUBSCRIPTION_ID>" \
  --resource-group "rg-app-prod" \
  --start-time "<START_UTC>" \
  --end-time "<END_UTC>" \
  --output table
```

Có thể dùng thêm `--caller`, `--status`, `--resource-id` hoặc `--correlation-id` để thu hẹp kết quả. Khi cần lọc theo một thao tác cụ thể, hãy xem tên operation thực tế trong event trước khi dùng tên đó làm điều kiện truy vấn.

### Kiểm tra context trước khi truy vấn

```bash
az account show --query "{Name:name, SubscriptionId:id, TenantId:tenantId}" --output table
```

Đối chiếu Subscription ID và Tenant ID với môi trường cần điều tra. Việc truy vấn Activity Log không thay đổi tài nguyên, nhưng chọn sai subscription có thể khiến bạn bỏ sót sự kiện hoặc kết luận sai về môi trường.

## 6. Truy vấn bằng Azure PowerShell

Nếu nhóm vận hành dùng Azure PowerShell, `Get-AzActivityLog` cho phép lấy các event theo thời gian và phạm vi tài nguyên:

```powershell
$start = (Get-Date).ToUniversalTime().AddHours(-24)
$end = (Get-Date).ToUniversalTime()

Get-AzActivityLog -StartTime $start -EndTime $end -ResourceGroupName "rg-app-prod" |
    Select-Object EventTimestamp, Caller, OperationName, Status, ResourceId, CorrelationId |
    Sort-Object EventTimestamp -Descending
```

Đảm bảo PowerShell đang sử dụng đúng Azure context trước khi truy vấn:

```powershell
Get-AzContext | Format-List Account, Tenant, Subscription, Environment
```

Kết quả của Azure CLI và Azure PowerShell phụ thuộc vào context hiện hành của từng công cụ. Hãy xác nhận subscription và tenant trong công cụ mà bạn đang sử dụng.

## 7. Lưu trữ và phân tích Activity Log dài hạn

Activity Log có thể xem trực tiếp trong Azure trong **90 ngày** gần nhất. Nếu cần lưu lâu hơn, phân tích tập trung hoặc đáp ứng yêu cầu kiểm toán, hãy cấu hình xuất log sang đích lưu trữ phù hợp.

### Cấu hình Diagnostic settings

1. Trong Azure Portal, mở **Monitor** rồi chọn **Activity log**; tìm phần **Diagnostic settings** hoặc chức năng xuất Activity Log.
2. Tạo diagnostic setting ở phạm vi subscription cần theo dõi.
3. Chọn các category cần xuất, chẳng hạn `Administrative`, `Security`, `Policy`, `ServiceHealth` hoặc `ResourceHealth` tùy yêu cầu.
4. Chọn một hoặc nhiều đích đến được hỗ trợ: Log Analytics workspace, Storage account hoặc Event Hubs.
5. Lưu cấu hình và xác minh dữ liệu bắt đầu xuất hiện ở đích đến.

Diagnostic setting của Activity Log được cấu hình ở cấp subscription. Việc bật diagnostic setting cho một resource riêng lẻ để thu thập resource logs không tự động thay thế cấu hình xuất Activity Log của subscription.

### Chọn đích đến theo nhu cầu

| Đích đến | Khi nào nên dùng | Điều cần cân nhắc |
|---|---|---|
| **Log Analytics workspace** | Tìm kiếm bằng KQL, tạo workbook, dashboard và cảnh báo dựa trên truy vấn. | Chi phí ingestion và retention; cần kiểm soát quyền truy cập workspace. |
| **Storage account** | Lưu giữ log dài hạn hoặc phục vụ quy trình lưu trữ và kiểm toán. | Chính sách vòng đời, bảo vệ dữ liệu, quyền truy cập và thời gian lưu giữ. |
| **Event Hubs** | Chuyển sự kiện đến hệ thống phân tích hoặc SIEM bên ngoài. | Cần consumer phù hợp, quản lý throughput và bảo vệ endpoint. |

Chọn category theo mục tiêu giám sát để tránh gửi dữ liệu không cần thiết. Nếu có yêu cầu kiểm toán, hãy thống nhất thời gian lưu giữ, quyền đọc, quy trình truy xuất và cách bảo vệ log với nhóm bảo mật hoặc quản trị nền tảng.

### Phân tích dữ liệu trong Log Analytics bằng KQL

Khi Activity Log được gửi tới Log Analytics workspace, các bản ghi thường có trong bảng `AzureActivity`. Ví dụ truy vấn các thao tác quản trị thành công hoặc thất bại trong 24 giờ gần nhất:

```kusto
AzureActivity
| where TimeGenerated >= ago(24h)
| where CategoryValue == "Administrative"
| project TimeGenerated, Caller, OperationNameValue, ActivityStatusValue, ResourceGroup, ResourceId, CorrelationId
| order by TimeGenerated desc
```

Để tập trung vào các thao tác thất bại, có thể dùng:

```kusto
AzureActivity
| where TimeGenerated >= ago(7d)
| where CategoryValue == "Administrative"
| where ActivityStatusValue == "Failure"
| project TimeGenerated, Caller, OperationNameValue, ActivityStatusValue, ResourceId, CorrelationId
| order by TimeGenerated desc
```

Tên cột và giá trị có thể khác giữa các nguồn dữ liệu hoặc phiên bản schema. Nếu truy vấn báo không tìm thấy cột, hãy mở **Schema** của bảng `AzureActivity` trong workspace để xác nhận tên trường thực tế. Không nên suy diễn rằng một truy vấn không trả kết quả đồng nghĩa không có thay đổi; hãy kiểm tra khoảng thời gian, category, subscription và việc xuất log trước.

## 8. Tạo cảnh báo khi có thay đổi quan trọng

Đọc nhật ký sau khi sự cố xảy ra giúp điều tra; cảnh báo dựa trên Activity Log giúp nhóm phản ứng sớm khi có thao tác nhạy cảm.

Ví dụ, nhóm có thể tạo Activity Log alert cho các tình huống:

- Có role assignment mới được tạo trong subscription Production.
- Một tài nguyên quan trọng bị xóa.
- Thao tác quản trị bị thất bại nhiều lần hoặc bị Azure Policy từ chối.
- Có sự kiện Service Health ảnh hưởng đến dịch vụ đang sử dụng.

Quy trình khái quát trong Portal:

1. Mở **Monitor** → **Alerts** và tạo alert rule mới.
2. Chọn scope là subscription hoặc phạm vi được yêu cầu.
3. Chọn signal/condition thuộc **Activity Log**.
4. Lọc theo category, operation, resource group, resource, status hoặc caller để giới hạn đúng sự kiện cần phát hiện.
5. Gắn **Action group** để gửi thông báo hoặc kích hoạt quy trình phản ứng.
6. Đặt tên, mức độ nghiêm trọng và mô tả rõ mục đích của alert rule.
7. Kiểm tra rule bằng một sự kiện thử nghiệm phù hợp hoặc xác minh điều kiện với nhóm vận hành.

Ví dụ, một cảnh báo về thay đổi role assignment có thể lọc category `Administrative` và operation `Microsoft.Authorization/roleAssignments/write`. Hãy xác nhận operation name thực tế từ event trong môi trường của bạn trước khi lưu điều kiện. Tránh tạo cảnh báo quá rộng vì nhiều thao tác quản trị bình thường có thể làm tăng số lượng thông báo.

Action group quyết định cách thông báo được gửi. Cần kiểm tra người nhận, kênh liên lạc và quy trình xử lý để cảnh báo đến đúng nhóm chịu trách nhiệm. Không gửi thông báo chứa thông tin nhạy cảm đến các kênh không được phép.

## 9. Quy trình điều tra thay đổi tài nguyên

Khi phát hiện thay đổi ngoài dự kiến, hãy thực hiện theo trình tự nhất quán để giữ lại đủ bằng chứng:

1. **Khoanh vùng:** xác định subscription, resource group, resource ID và khoảng thời gian xảy ra thay đổi.
2. **Tìm event:** lọc `Administrative` và các operation có liên quan; mở chi tiết event và JSON.
3. **Xác định chủ thể:** kiểm tra `caller`, danh tính ứng dụng hoặc workload, và đối chiếu với quyền được cấp.
4. **Xác định kết quả:** đọc `status`, `level`, `eventTimestamp` và `submissionTimestamp`.
5. **Liên kết chuỗi thao tác:** tìm các event cùng `correlationId` hoặc `operationId` để hiểu trình tự.
6. **Đối chiếu hoạt động hợp lệ:** kiểm tra lịch triển khai, pipeline, yêu cầu thay đổi và thông báo bảo trì.
7. **Đánh giá tác động:** kiểm tra trạng thái hiện tại của tài nguyên và log của dịch vụ liên quan.
8. **Lưu bằng chứng:** ghi lại các trường quan trọng, truy vấn đã dùng, thời gian UTC và nguồn dữ liệu.
9. **Xử lý và theo dõi:** thực hiện quy trình khôi phục hoặc ứng phó sự cố đã được tổ chức phê duyệt; theo dõi event tiếp theo để xác nhận kết quả.

Không vội kết luận một thay đổi là trái phép chỉ vì caller không quen thuộc. Có thể đó là service principal của pipeline, managed identity hoặc thao tác do nền tảng thực hiện. Hãy đối chiếu danh tính, correlation ID, thời gian và lịch triển khai trước khi kết luận.

## 10. Giới hạn và thực hành tốt

- Activity Log tập trung vào control plane; bật resource logs riêng cho các dịch vụ cần theo dõi data plane.
- Dữ liệu mặc định chỉ có thể xem trong 90 ngày. Cấu hình xuất log nếu yêu cầu lưu trữ dài hơn.
- Activity Log cho biết thao tác và trạng thái, nhưng không phải lúc nào cũng chứa đầy đủ bản diff cấu hình cũ/mới.
- Một số sự kiện có thể được gửi vào nhật ký trễ; xem cả event time và submission time khi đối chiếu.
- Quyền xem Activity Log và quyền cấu hình diagnostic settings là khác nhau. Cấp quyền theo nguyên tắc tối thiểu cần thiết.
- Chọn đúng tenant và subscription trước khi điều tra hoặc tạo cảnh báo.
- Bảo vệ workspace, storage account và Event Hubs nhận log; log có thể chứa định danh người dùng, tài nguyên và thông tin vận hành nhạy cảm.
- Kiểm tra định kỳ diagnostic settings và alert rules để phát hiện cấu hình bị thiếu hoặc đích đến không còn hoạt động.

Với tài nguyên quan trọng, nên kết hợp Activity Log với Azure Policy, Change Analysis, resource logs, Entra audit logs và hệ thống quản lý thay đổi của tổ chức. Mỗi nguồn bổ sung một góc nhìn khác nhau, giúp việc kiểm tra và điều tra có căn cứ hơn.

## 11. Bài thực hành: điều tra thay đổi trong resource group

Giả sử nhóm nhận được báo cáo rằng một storage account trong `rg-app-prod` đã thay đổi cấu hình mạng vào buổi sáng. Bạn được giao tìm sự kiện liên quan và ghi lại bằng chứng.

**Thông tin đầu vào giả định**

| Thuộc tính | Giá trị |
|---|---|
| Subscription | `Production` |
| Resource group | `rg-app-prod` |
| Tài nguyên | Storage account của ứng dụng |
| Category ưu tiên | `Administrative` |
| Khoảng thời gian | Từ lúc phát hiện sự cố trở về trước, theo UTC |

**Các bước thực hiện**

1. Xác nhận Tenant ID và Subscription ID của môi trường Production.
2. Mở Activity Log ở subscription hoặc trang của storage account; chọn khoảng thời gian phù hợp.
3. Lọc category `Administrative` và resource group `rg-app-prod`.
4. Tìm event cập nhật cấu hình của storage account; mở chi tiết JSON.
5. Ghi lại `eventTimestamp`, `caller`, `operationName`, `status`, `resourceId` và `correlationId`.
6. Tìm các event khác cùng correlation ID để xác định chuỗi thao tác.
7. Đối chiếu caller với pipeline hoặc yêu cầu thay đổi đã được phê duyệt.
8. Nếu cần xác định chính xác thuộc tính mạng nào thay đổi, tra cứu Change Analysis/Change history hoặc nguồn cấu hình có lưu trạng thái trước và sau.

**Mẫu ghi nhận kết quả**

| Trường | Nội dung cần điền |
|---|---|
| Subscription ID | ID đã xác minh |
| Resource ID | Đường dẫn đầy đủ của storage account |
| Event time (UTC) | Thời điểm event xảy ra |
| Caller | Người dùng hoặc danh tính workload |
| Operation | Tên thao tác quản lý |
| Status | Kết quả thao tác |
| Correlation ID | Mã liên kết các event liên quan |
| Bằng chứng bổ sung | Event JSON, pipeline run hoặc change record |
| Nhận định | Thay đổi hợp lệ, cần xác minh thêm hoặc có dấu hiệu bất thường |

Bài thực hành hoàn tất khi bạn xác định được event liên quan, giải thích được chủ thể và kết quả thao tác, đồng thời ghi lại bằng chứng để người khác có thể kiểm tra lại. Nếu không tìm thấy event, hãy xác nhận lại subscription, thời gian UTC, bộ lọc, quyền đọc và trạng thái xuất log trước khi kết luận.

## 12. Tự kiểm tra kiến thức

**1. Một storage account được tạo mới. Bạn nên tìm sự kiện ở đâu?**

- A. Chỉ trong nhật ký truy cập blob của ứng dụng.
- B. Trong Activity Log của subscription, với category quản trị phù hợp.
- C. Chỉ trong Microsoft Entra sign-in logs.

Đáp án: **B**. Tạo storage account là thao tác control plane nên được ghi trong Activity Log.

**2. Activity Log cho biết ai đã gọi thao tác và trạng thái thành công, nhưng bạn cần biết giá trị thuộc tính trước và sau thay đổi. Nên làm gì?**

- A. Giả định toàn bộ giá trị cũ và mới luôn nằm trong Activity Log.
- B. Dùng Change Analysis/Change history hoặc nguồn theo dõi cấu hình phù hợp với tài nguyên.
- C. Chỉ xem tên subscription.

Đáp án: **B**. Activity Log là lịch sử sự kiện quản trị; dữ liệu so sánh thuộc tính có thể cần nguồn chuyên biệt.

**3. Vì sao cần xuất Activity Log sang Log Analytics hoặc Storage account?**

- A. Vì dữ liệu Activity Log mặc định có thời gian xem 90 ngày và việc xuất giúp lưu giữ hoặc phân tích dài hạn.
- B. Vì Activity Log chỉ ghi được khi đã tạo workspace.
- C. Vì xuất log sẽ tự động cấp quyền Owner cho người vận hành.

Đáp án: **A**. Xuất log cho phép lưu giữ theo chính sách và phân tích tập trung sau thời gian mặc định.

**4. Trường nào giúp liên kết nhiều sự kiện thuộc cùng một luồng thao tác?**

- A. `resourceGroupName`.
- B. `correlationId`.
- C. `level`.

Đáp án: **B**. `correlationId` giúp tìm các event liên quan đến cùng một thao tác hoặc luồng xử lý.

**5. Một event có caller là service principal. Có thể kết luận một nhân viên cụ thể đã thao tác không?**

Đáp án: Không. Service principal đại diện cho ứng dụng hoặc workload. Cần đối chiếu danh tính ứng dụng, pipeline, managed identity và correlation ID trước khi xác định nguồn gốc hành động.

Khi biết cách lọc, đọc, lưu trữ và cảnh báo từ Activity Log, bạn có thể theo dõi thay đổi ở lớp quản lý Azure có hệ thống hơn, hỗ trợ điều tra sự cố và tăng khả năng kiểm soát hoạt động trên từng subscription.
