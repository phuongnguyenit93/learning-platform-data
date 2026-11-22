# Gọi Azure Resource Manager REST API

Azure Resource Manager (ARM) là lớp quản lý thống nhất của Azure. Khi tạo resource group, triển khai máy ảo, thay đổi cấu hình mạng hoặc xem danh sách tài nguyên trong subscription, các công cụ như Azure Portal, Azure CLI, Azure PowerShell, SDK và template triển khai đều gửi yêu cầu tới lớp quản lý này. Ngoài các công cụ đó, bạn có thể gọi trực tiếp **Azure Resource Manager REST API** bằng HTTP để tự động hóa quy trình, tích hợp Azure với hệ thống khác hoặc tìm hiểu chính xác một thao tác quản trị đang diễn ra như thế nào.

Bài học này hướng dẫn cách xác thực bằng Microsoft Entra ID, xây dựng URL và request, thực hiện các thao tác phổ biến, theo dõi tác vụ bất đồng bộ và xử lý lỗi khi gọi ARM REST API. Nội dung đặt trong phạm vi quản lý subscription, resource group, danh tính và các dịch vụ thuộc hệ sinh thái Microsoft Azure.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của ARM và phân biệt management plane với data plane.
- Lấy access token phù hợp từ Microsoft Entra ID và hiểu vai trò của Azure RBAC.
- Xây dựng request theo resource ID, HTTP method và API version.
- Dùng REST API để đọc, tạo, cập nhật và xóa tài nguyên Azure.
- Theo dõi tác vụ dài, xử lý phân trang, throttling và lỗi HTTP.
- Bảo vệ thông tin xác thực và áp dụng quyền tối thiểu khi tự động hóa.

## 1. Azure Resource Manager REST API là gì?

ARM là control plane của Azure: lớp tiếp nhận và điều phối các thao tác quản trị tài nguyên. ARM cung cấp một giao diện quản lý thống nhất cho nhiều loại tài nguyên, chẳng hạn Virtual Machines, Virtual Networks, Storage Accounts, Azure SQL và resource groups.

REST API cho phép client gửi HTTP request đến endpoint quản lý Azure. Một request thường xác định:

- **Endpoint**: máy chủ ARM, thường là `https://management.azure.com` đối với Azure public cloud.
- **Resource ID**: đường dẫn định danh subscription, resource group hoặc tài nguyên cần thao tác.
- **API version**: phiên bản hợp đồng API của resource provider.
- **HTTP method**: hành động cần thực hiện như GET, PUT, PATCH, DELETE hoặc POST.
- **Headers và body**: thông tin xác thực, định dạng nội dung và dữ liệu gửi lên nếu thao tác yêu cầu.

Ví dụ, Azure Portal khi tạo resource group cũng gửi yêu cầu quản lý tương ứng tới ARM. Khi bạn gọi REST API trực tiếp, bạn chủ động xây dựng request thay vì nhờ Portal hoặc CLI tạo request hộ.

### Management plane và data plane

Hai loại endpoint này có mục đích khác nhau:

| Loại | Mục đích | Ví dụ |
|---|---|---|
| **Management plane** | Tạo, cấu hình, liệt kê hoặc xóa tài nguyên Azure. | Tạo Storage Account, thay đổi cấu hình VM, tạo resource group qua `management.azure.com`. |
| **Data plane** | Đọc hoặc ghi dữ liệu mà dịch vụ đang lưu trữ hay xử lý. | Đọc blob từ `https://<storage-account>.blob.core.windows.net`, truy vấn dữ liệu trong database hoặc gửi message vào queue. |

Ví dụ, ARM REST API có thể tạo Storage Account và cấu hình redundancy. Để tải một blob bên trong tài khoản đó, ứng dụng gọi Blob Storage data-plane API. Hai thao tác có thể dùng cùng một danh tính Microsoft Entra ID nhưng cần token audience, quyền RBAC và endpoint phù hợp với dịch vụ tương ứng.

## 2. Cấu trúc một REST request

Một request quản lý tài nguyên thường có dạng:

```http
<METHOD> https://management.azure.com/<resource-id>?api-version=<api-version> HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json

<JSON body nếu method yêu cầu>
```

`api-version` là tham số quan trọng. ARM cần biết phiên bản hợp đồng của API mà client muốn sử dụng; không nên bỏ qua tham số này hoặc tự đoán phiên bản. Mỗi resource provider có lịch phát hành API riêng. Hãy chọn phiên bản được tài liệu chính thức của loại tài nguyên công bố, ưu tiên phiên bản ổn định cho môi trường production và đánh giá kỹ nếu phải dùng phiên bản preview.

Một số HTTP method thường gặp:

| Method | Ý nghĩa thường dùng trong ARM | Ví dụ |
|---|---|---|
| `GET` | Đọc một tài nguyên hoặc liệt kê tài nguyên. | Xem thông tin resource group hoặc danh sách VM. |
| `PUT` | Tạo mới hoặc thay thế cấu hình tài nguyên tại một resource ID. | Tạo resource group hoặc tạo Storage Account. |
| `PATCH` | Cập nhật một phần thuộc tính nếu API của tài nguyên hỗ trợ. | Thay đổi một số tags hoặc cấu hình. |
| `DELETE` | Yêu cầu xóa tài nguyên. | Xóa resource group hoặc VM. |
| `POST` | Thực hiện action hoặc operation do resource provider cung cấp. | Start, stop hoặc deallocate VM thông qua action endpoint. |

Ý nghĩa cụ thể của method và body phụ thuộc vào endpoint. Không phải mọi tài nguyên đều hỗ trợ PATCH, và POST có thể kích hoạt một hành động có tác động thực tế. Luôn kiểm tra tài liệu của operation trước khi gọi.

### Resource ID

Resource ID xác định vị trí logic của một tài nguyên trong Azure. Một số dạng phổ biến:

```text
/subscriptions/{subscriptionId}
/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}
/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/{resourceProviderNamespace}/{resourceType}/{resourceName}
```

Ví dụ resource ID của một máy ảo:

```text
/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-app/providers/Microsoft.Compute/virtualMachines/vm-api
```

Trong đó:

- `subscriptionId` xác định subscription chứa tài nguyên.
- `resourceGroups/rg-app` xác định resource group.
- `Microsoft.Compute` là namespace của resource provider.
- `virtualMachines/vm-api` xác định loại tài nguyên và tên VM.

Resource ID thường được dùng làm phần đường dẫn sau hostname ARM. Với tài nguyên con, đường dẫn có thể có thêm các cặp loại/tên, vì vậy hãy lấy đúng ID từ phản hồi API hoặc tài liệu thay vì tự rút gọn.

## 3. Xác thực bằng Microsoft Entra ID

ARM không dùng username/password được nhúng trực tiếp trong request. Client cần lấy **access token** do Microsoft Entra ID cấp và gửi token đó trong header:

```http
Authorization: Bearer <access-token>
```

Token phải dành cho Azure Resource Manager. Với Azure public cloud, resource audience thường là `https://management.azure.com/`. Token lấy cho Microsoft Graph hoặc cho Blob Storage không thể tùy ý thay thế token ARM.

### Lấy token bằng Azure CLI

Để thực hành trên máy cá nhân, đăng nhập bằng Azure CLI:

```bash
az login
az account list --output table
az account set --subscription "<subscription-id-hoac-ten>"
```

Sau đó lấy subscription ID hiện tại và access token dành cho ARM:

```bash
SUBSCRIPTION_ID=$(az account show --query id --output tsv)
TOKEN=$(az account get-access-token \
  --resource https://management.azure.com/ \
  --query accessToken \
  --output tsv)
```

Các lệnh trên dùng phiên đăng nhập Azure CLI của người thực hành. Token có thời hạn; nếu request nhận lỗi token hết hạn, hãy lấy token mới. Không ghi token vào source code, commit vào Git, gửi qua chat hoặc lưu trong log.

### Danh tính người dùng và danh tính ứng dụng

Trong môi trường tự động hóa, không nên phụ thuộc vào tài khoản cá nhân của kỹ sư. Có thể sử dụng:

- **Service principal**: danh tính ứng dụng trong Microsoft Entra ID, thường dùng với workload chạy ngoài Azure hoặc pipeline. Ưu tiên chứng thư hoặc workload federation khi phù hợp; nếu dùng client secret, lưu trong secret store và xoay vòng theo chính sách.
- **Managed identity**: danh tính do Azure quản lý cho tài nguyên hỗ trợ, ví dụ VM, App Service hoặc Azure Functions. Ứng dụng có thể xin token mà không phải tự lưu client secret.
- **Workload identity federation**: cho phép workload ở hệ thống hỗ trợ trao đổi token tin cậy với Microsoft Entra ID mà không cần lưu secret dài hạn.

Với mọi loại danh tính, hai điều kiện cần được đáp ứng: danh tính phải lấy được token hợp lệ cho ARM và phải có quyền thực hiện operation trên đúng phạm vi tài nguyên.

## 4. Azure RBAC quyết định request được phép làm gì

Access token xác định danh tính và các thông tin xác thực liên quan; Azure Role-Based Access Control (Azure RBAC) quyết định danh tính đó được phép thực hiện hành động nào trên phạm vi nào. Có token hợp lệ không đồng nghĩa request chắc chắn được chấp nhận.

Quyền có thể được gán ở nhiều scope:

1. Management group.
2. Subscription.
3. Resource group.
4. Resource cụ thể.

Quyền được kế thừa từ scope cha xuống scope con theo mô hình Azure RBAC. Ví dụ, một danh tính có vai trò phù hợp tại resource group có thể quản lý tài nguyên thuộc resource group đó mà không cần được cấp quyền trên toàn subscription.

Khi thiết kế tích hợp, hãy chọn role có tập action tối thiểu cần thiết. `Reader` thường phù hợp với nhu cầu chỉ đọc metadata quản lý; các thao tác tạo, cập nhật hoặc xóa cần role có quyền tương ứng. `Contributor` có phạm vi rộng và không nên được cấp chỉ vì muốn thử một request. Nếu cần quyền tùy chỉnh, có thể xây dựng custom role theo các operation cần thiết và kiểm tra thêm điều kiện như Azure Policy, deny assignment hoặc khóa tài nguyên.

Một số mã phản hồi thường gặp:

- `401 Unauthorized`: token thiếu, sai audience, hết hạn hoặc không hợp lệ.
- `403 Forbidden`: danh tính đã được xác thực nhưng không có quyền phù hợp, hoặc bị chặn bởi chính sách/điều kiện ở scope liên quan.
- `404 Not Found`: resource ID, tên tài nguyên, subscription hoặc endpoint không đúng; cũng cần kiểm tra tài nguyên có tồn tại trong scope đang gọi hay không.

## 5. Gọi API đọc và tạo resource group

Ví dụ sau dùng Bash, Azure CLI và `curl`. Bạn cần có Azure CLI, `curl`, quyền phù hợp trên subscription và đã đăng nhập thành công. Thay tên resource group hoặc region theo môi trường thực hành của bạn.

### Đọc danh sách resource group

Sau khi đã thiết lập `SUBSCRIPTION_ID` và `TOKEN` như phần trước, gọi:

```bash
curl --request GET \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourcegroups?api-version=2021-04-01" \
  --header "Authorization: Bearer ${TOKEN}" \
  --header "Accept: application/json"
```

Request này gọi operation liệt kê resource group trong subscription. Phản hồi thành công thường có mã HTTP `200` và JSON chứa thuộc tính `value`, là danh sách resource group. Nếu danh sách dài, phản hồi có thể chứa `nextLink`; xem phần phân trang bên dưới để lấy đủ kết quả.

### Tạo resource group

Tạo resource group là một thao tác `PUT` vào resource ID của nhóm tài nguyên:

```bash
curl --request PUT \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourcegroups/rg-rest-demo?api-version=2021-04-01" \
  --header "Authorization: Bearer ${TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{
    "location": "southeastasia",
    "tags": {
      "environment": "learning",
      "managedBy": "rest-api"
    }
  }'
```

Body JSON chỉ định region và tags. Thay `southeastasia` bằng region đáp ứng yêu cầu của bạn. Nếu request thành công, phản hồi trả về thông tin resource group vừa tạo hoặc cập nhật. Hãy kiểm tra `id`, `name`, `location` và `tags` trong kết quả.

### Đọc một resource group theo tên

```bash
curl --request GET \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourcegroups/rg-rest-demo?api-version=2021-04-01" \
  --header "Authorization: Bearer ${TOKEN}" \
  --header "Accept: application/json"
```

Ví dụ này minh họa cách gọi API theo resource ID. Trong môi trường thực tế, hãy chọn API version được tài liệu của operation tương ứng hỗ trợ. API version của Resource Groups không nhất thiết giống API version của Virtual Machines hoặc Storage.

## 6. Đọc hoặc thao tác với tài nguyên thuộc resource provider

Các loại tài nguyên được quản lý bởi resource provider. Ví dụ, VM thuộc namespace `Microsoft.Compute`, virtual network thuộc `Microsoft.Network`, còn storage account thuộc `Microsoft.Storage`.

Một request đọc VM có dạng:

```bash
curl --request GET \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/rg-app/providers/Microsoft.Compute/virtualMachines/vm-api?api-version=2024-03-01" \
  --header "Authorization: Bearer ${TOKEN}" \
  --header "Accept: application/json"
```

Trong ví dụ, API version `2024-03-01` minh họa phiên bản của Microsoft.Compute cho thao tác VM. Trước khi dùng, hãy kiểm tra phiên bản được hỗ trợ cho operation và loại tài nguyên tại thời điểm triển khai. Không dùng một API version chung cho tất cả resource provider.

Để tạo hoặc cập nhật một tài nguyên, thường dùng `PUT` tới resource ID của tài nguyên với body đúng schema. Để thay đổi một phần thuộc tính, dùng `PATCH` nếu operation hỗ trợ. Để gọi action như khởi động VM, resource provider thường công bố một action endpoint dùng `POST`, ví dụ đường dẫn có dạng:

```text
POST /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Compute/virtualMachines/{vmName}/start?api-version={api-version}
```

Đường dẫn minh họa này không thay thế tài liệu operation: API version, body, quyền cần có và hành vi bất đồng bộ phải được xác nhận theo phiên bản Compute API đang dùng. Một số action không có body, nhưng vẫn cần header xác thực và quyền phù hợp.

## 7. Phân trang khi đọc danh sách

Một operation liệt kê có thể trả về một phần kết quả thay vì toàn bộ danh sách. Nếu JSON phản hồi có trường `nextLink`, client phải gọi URL đó để lấy trang kế tiếp, tiếp tục cho tới khi không còn `nextLink`.

```json
{
  "value": [
    { "name": "rg-app", "location": "southeastasia" }
  ],
  "nextLink": "https://management.azure.com/..."
}
```

`nextLink` thường chứa các tham số tiếp tục truy vấn. Hãy dùng URL do server trả về thay vì tự tạo token phân trang hoặc tự tăng offset. Khi gọi URL tiếp theo, vẫn gửi access token trong header. Nếu dùng thư viện HTTP, nên lặp cho đến khi `nextLink` không còn; nếu bỏ qua trường này, báo cáo hoặc tác vụ đồng bộ có thể chỉ xử lý được một phần tài nguyên.

## 8. Tác vụ bất đồng bộ và polling

Một số thao tác quản lý mất thời gian, chẳng hạn tạo VM, thay đổi cấu hình hạ tầng hoặc xóa tài nguyên lớn. ARM có thể trả về `202 Accepted` để cho biết request đã được tiếp nhận và operation vẫn đang chạy. Mã `202` không có nghĩa tài nguyên đã sẵn sàng.

Phản hồi có thể chứa một hoặc cả hai header:

- `Azure-AsyncOperation`: URL dùng để kiểm tra trạng thái operation.
- `Location`: URL liên quan đến operation hoặc kết quả cuối cùng, tùy API.
- `Retry-After`: khoảng thời gian client nên chờ trước lần kiểm tra tiếp theo.

Quy trình tổng quát:

1. Gửi request quản lý và đọc HTTP status cùng response headers.
2. Nếu operation hoàn tất ngay, xử lý response theo hợp đồng API.
3. Nếu nhận `202 Accepted`, lưu URL polling được trả về và khoảng chờ `Retry-After` nếu có.
4. Gọi URL trạng thái bằng token phù hợp, chờ theo chỉ dẫn của server và lặp lại khi trạng thái vẫn đang chạy.
5. Chỉ báo thành công khi trạng thái cuối cùng là `Succeeded` hoặc API xác nhận tài nguyên đã đạt trạng thái mong muốn. Nếu trạng thái là `Failed` hoặc `Canceled`, đọc chi tiết lỗi và xử lý phù hợp.

Ví dụ response từ một endpoint trạng thái có thể có dạng:

```json
{
  "status": "InProgress"
}
```

Các trạng thái cụ thể và header được trả về phụ thuộc operation. Client cần xử lý cả trường hợp không có `Azure-AsyncOperation`, có `Location`, hoặc API trả kết quả hoàn tất ngay. Tránh polling liên tục; tuân thủ `Retry-After` để giảm tải và tránh bị throttling.

## 9. Xử lý lỗi, throttling và cập nhật đồng thời

Khi gọi REST API, cần kiểm tra cả HTTP status code lẫn nội dung JSON trả về. ARM thường cung cấp thông tin lỗi trong cấu trúc có `error.code`, `error.message` và đôi khi có `error.details` hoặc `target`.

| HTTP status | Ý nghĩa thường gặp | Cách xử lý |
|---|---|---|
| `400 Bad Request` | Body, tham số hoặc cấu hình không hợp lệ. | Kiểm tra schema, API version, giá trị enum và trường bắt buộc. |
| `401 Unauthorized` | Token không hợp lệ, hết hạn hoặc sai audience. | Lấy token mới cho ARM và kiểm tra danh tính đang dùng. |
| `403 Forbidden` | Thiếu quyền hoặc bị chính sách chặn. | Kiểm tra role assignment, scope, Azure Policy và deny assignment. |
| `404 Not Found` | Không tìm thấy tài nguyên hoặc operation. | Kiểm tra subscription, resource ID, tên và API endpoint. |
| `409 Conflict` | Trạng thái hiện tại xung đột với thao tác yêu cầu. | Đọc mã lỗi chi tiết, kiểm tra operation đang chạy và trạng thái tài nguyên. |
| `429 Too Many Requests` | Request vượt giới hạn hoặc bị throttling. | Tôn trọng `Retry-After`, giảm tốc độ và dùng exponential backoff có jitter khi phù hợp. |
| `5xx` | Lỗi tạm thời ở dịch vụ hoặc hạ tầng. | Ghi nhận request ID, retry có giới hạn với backoff nếu operation an toàn để thử lại. |

Không nên retry tất cả lỗi giống nhau. Lỗi xác thực hoặc quyền thường cần sửa cấu hình, còn throttling và một số lỗi dịch vụ tạm thời có thể thử lại. Với thao tác tạo/cập nhật, cần hiểu tính idempotent của operation trước khi tự động gửi lại; đặc biệt không gửi lặp action có tác động phụ nếu chưa biết trạng thái lần gọi trước.

### ETag và optimistic concurrency

Một số API trả về `etag` để nhận diện phiên bản hiện tại của tài nguyên. Khi API hỗ trợ, client có thể gửi `If-Match` với ETag đã đọc để chỉ cập nhật nếu tài nguyên chưa bị thay đổi bởi client khác. Nếu ETag không còn khớp, server có thể trả `412 Precondition Failed`; khi đó hãy đọc lại tài nguyên, đối chiếu thay đổi rồi quyết định cập nhật tiếp.

Ví dụ header:

```http
If-Match: "<etag-da-doc-tu-resource>"
```

Không phải mọi resource provider hoặc operation đều hỗ trợ ETag theo cùng cách. Chỉ dùng cơ chế này khi tài liệu API xác nhận có hỗ trợ.

## 10. Bảo mật khi tích hợp ARM REST API

Access token là thông tin nhạy cảm. Bất kỳ ai lấy được token có thể thử thực hiện các operation trong phạm vi quyền mà token đại diện. Hãy áp dụng các nguyên tắc sau:

- Cấp Azure RBAC theo quyền tối thiểu và scope hẹp nhất có thể.
- Dùng managed identity hoặc workload identity federation khi môi trường hỗ trợ; hạn chế client secret dài hạn.
- Lưu secret và chứng thư trong secret manager phù hợp, không đưa vào source code hoặc file cấu hình công khai.
- Không ghi access token, client secret hoặc dữ liệu nhạy cảm vào log. Log request ID, thời gian, endpoint đã loại bỏ dữ liệu bí mật và kết quả cần thiết để điều tra.
- Dùng HTTPS và xác minh chứng thư TLS; không tắt kiểm tra TLS để xử lý lỗi kết nối.
- Tách quyền giữa môi trường development, staging và production; xem xét phê duyệt cho các thao tác xóa hoặc thay đổi lớn.
- Theo dõi hoạt động quản trị qua Azure Activity Log và hệ thống giám sát của tổ chức.

Ngoài RBAC, request có thể bị ảnh hưởng bởi Azure Policy, resource locks và các quy tắc quản trị khác. Ví dụ, một danh tính có quyền xóa theo RBAC vẫn có thể không xóa được tài nguyên đang bị khóa ở scope tương ứng.

## 11. Khi nào nên gọi REST API trực tiếp?

Azure CLI, Azure PowerShell và SDK thường đơn giản hơn khi thực hiện tác vụ phổ biến vì chúng hỗ trợ xác thực, tham số và một phần logic xử lý lỗi. REST API trực tiếp hữu ích khi:

- Bạn cần một operation chưa được CLI hoặc SDK phiên bản hiện tại cung cấp thuận tiện.
- Bạn đang tích hợp Azure với một hệ thống có thể gửi HTTP request.
- Bạn cần kiểm tra request, response, header hoặc API version để gỡ lỗi.
- Bạn muốn hiểu rõ giao thức mà công cụ quản trị đang sử dụng.

Với triển khai hạ tầng lặp lại, Bicep, ARM template hoặc Terraform thường giúp mô tả trạng thái mong muốn, review thay đổi và tái sử dụng cấu hình. REST API phù hợp cho tích hợp hoặc thao tác cụ thể; không nhất thiết phải tự viết HTTP cho mọi tài nguyên nếu công cụ cấp cao đã đáp ứng tốt nhu cầu.

## 12. Bài thực hành

Thực hiện trong subscription thử nghiệm mà bạn có quyền quản lý:

1. Đăng nhập Azure CLI và chọn subscription đúng.
2. Lấy access token dành cho `https://management.azure.com/`.
3. Gọi GET để liệt kê resource group, kiểm tra HTTP status và trường `value`.
4. Tạo resource group `rg-rest-demo` bằng PUT với region phù hợp và một vài tags.
5. Gọi GET theo resource group ID để xác minh kết quả.
6. Nếu danh sách có `nextLink`, gọi tiếp cho tới khi lấy đủ trang.
7. Thử gọi một request với API version sai trong môi trường thử nghiệm và đọc cấu trúc lỗi trả về; sau đó sửa lại API version.
8. Xóa resource group thử nghiệm chỉ khi chắc chắn nó không chứa tài nguyên cần giữ và danh tính có quyền phù hợp.

Sau thực hành, bạn nên giải thích được vì sao token ARM khác token Blob Storage, vì sao token hợp lệ vẫn có thể nhận `403`, vì sao `202 Accepted` chưa phải kết quả hoàn tất và vì sao cần theo dõi `nextLink`.

## Kết luận

Azure Resource Manager REST API cung cấp giao diện HTTP để quản lý tài nguyên Azure. Một request đúng cần có endpoint và resource ID chính xác, API version được hỗ trợ, access token dành cho ARM, quyền Azure RBAC phù hợp cùng method và body theo hợp đồng của operation. Khi vận hành, client cần xử lý phân trang, tác vụ bất đồng bộ, throttling, lỗi và cập nhật đồng thời; đồng thời bảo vệ token và chỉ cấp quyền tối thiểu. Nắm được các thành phần này giúp bạn tích hợp Azure vào pipeline và ứng dụng quản trị một cách có kiểm soát.
