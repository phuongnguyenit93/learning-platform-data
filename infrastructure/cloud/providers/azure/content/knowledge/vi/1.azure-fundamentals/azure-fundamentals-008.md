# Quota, giới hạn dịch vụ và yêu cầu tăng hạn mức

## 1. Vì sao cần kiểm tra quota trước khi triển khai Azure?

Một ứng dụng có thể được thiết kế đúng, cấu hình mạng hợp lệ và có đầy đủ quyền truy cập nhưng vẫn không tạo được tài nguyên mới vì thiếu quota. Điều này thường xuất hiện khi tăng số lượng máy ảo, mở rộng môi trường kiểm thử, triển khai phiên bản mới song song với phiên bản cũ hoặc kích hoạt hệ thống dự phòng.

Trong chương **Nền tảng Azure**, quản lý quota nối liền kiến thức về subscription, resource group và Microsoft Entra ID với việc triển khai, giám sát và kiểm soát chi phí. Người vận hành cần xác định chính xác tài nguyên nào bị giới hạn, giới hạn áp dụng ở đâu và có thể thay đổi bằng cách nào.

Sau bài học này, bạn có thể:

- Phân biệt quota với capacity, giới hạn hiệu năng và throttling.
- Xác định phạm vi của một hạn mức thay vì chỉ nhìn tên dịch vụ.
- Đọc usage và limit để tính phần dung lượng còn lại.
- Lập kế hoạch hạn mức cho mở rộng, triển khai và phục hồi.
- Chuẩn bị, gửi và xác minh một yêu cầu tăng quota.
- Đưa kiểm tra quota vào quy trình vận hành ứng dụng Azure.

Các số liệu trong ví dụ dưới đây được tạo để minh họa cách tính, **không phải hạn mức mặc định của Azure**. Hạn mức thực tế phải được kiểm tra trong đúng subscription, region và tài liệu của dịch vụ đang sử dụng.

## 2. Những khái niệm dễ nhầm lẫn

### 2.1. Quota, usage và limit

**Quota** là cơ chế giới hạn lượng tài nguyên hoặc mức tiêu thụ trong một phạm vi xác định. **Limit** là giá trị trần hiện được áp dụng cho quota đó. **Usage** là lượng đã được tính vào bộ đếm tại thời điểm quan sát.

Ví dụ một quota vCPU có usage bằng 24 và limit bằng 32:

```text
Phần còn lại = limit - usage = 32 - 24 = 8 vCPU
Tỷ lệ sử dụng = usage / limit × 100% = 75%
```

Con số 75% ở đây là tỷ lệ sử dụng **hạn mức**, không phải CPU utilization bên trong máy ảo. Một VM ít xử lý công việc vẫn có thể chiếm quota theo kích thước tài nguyên của nó.

Azure có các quota cho nhiều loại tài nguyên; không tồn tại một con số quota duy nhất đại diện cho toàn bộ subscription. Tổng quan cơ chế và các điểm truy cập được mô tả trong [Azure Quotas overview](https://learn.microsoft.com/en-us/azure/quotas/quotas-overview).

### 2.2. Các loại giới hạn và hướng xử lý

| Khái niệm | Ý nghĩa thực tế | Hướng xử lý phù hợp |
| --- | --- | --- |
| Quota có thể điều chỉnh | Trần hiện tại có quy trình đề nghị tăng | Xác định mức cần dùng rồi gửi yêu cầu theo dịch vụ |
| Giới hạn tối đa cố định | Ràng buộc không có cơ chế tăng thông thường | Thay cách phân chia tài nguyên hoặc thiết kế kiến trúc |
| Giới hạn theo SKU hoặc tier | Khả năng của gói dịch vụ đang chọn | Đánh giá nâng tier, đổi SKU hoặc phân tải |
| Capacity | Tài nguyên vật lý Azure có thể cấp tại nơi yêu cầu | Xem xét size, zone hoặc region khác phù hợp |
| Giới hạn tốc độ yêu cầu | Số thao tác được chấp nhận trong một khoảng thời gian | Giảm đồng thời, điều tiết lưu lượng và retry đúng cách |
| Giới hạn hiệu năng | Trần throughput, IOPS, kết nối hoặc khả năng xử lý | Đo nút thắt và tối ưu hoặc mở rộng đúng thành phần |

Thuật ngữ **soft limit** thường nói về trần có thể xin điều chỉnh; **hard limit** thường nói về trần tối đa. Tuy nhiên, tên gọi trên giao diện không đủ để kết luận. Phải đọc điều kiện của chính dịch vụ. Việc một mục không cho tăng trực tiếp trong Quotas có thể có nghĩa là cần đi qua hỗ trợ; điều đó không chứng minh rằng mọi giới hạn cố định đều tăng được. Đối chiếu [Azure subscription and service limits, quotas, and constraints](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/azure-subscription-service-limits).

### 2.3. Quota, quyền truy cập và chi phí là ba việc riêng

Quyền Azure RBAC trả lời câu hỏi danh tính nào được thực hiện một thao tác. Quota trả lời phạm vi đó còn cho phép cấp thêm bao nhiêu tài nguyên. Một người có quyền tạo VM vẫn có thể bị chặn vì thiếu vCPU quota.

Việc tăng quota tự nó không tạo thêm tài nguyên và không làm ứng dụng tự mở rộng. Yêu cầu tăng quota không thu phí; chi phí phát sinh theo tài nguyên sử dụng và mô hình tính phí liên quan. Tham khảo [ghi chú về chi phí của Azure Quotas](https://learn.microsoft.com/en-us/azure/quotas/quotas-overview).

Vì vậy, nên quản trị đồng thời:

- Quyền triển khai và thay đổi tài nguyên.
- Hạn mức đủ cho nhu cầu đã dự báo.
- Giới hạn mở rộng của ứng dụng và quy trình theo dõi chi phí.

Không dùng số vCPU quota như một phép quy đổi trực tiếp thành ngân sách tiền: các SKU, đĩa, lưu trữ, dữ liệu truyền và dịch vụ đi kèm có cách tính khác nhau.

## 3. Xác định đúng phạm vi của hạn mức

Một hạn mức chỉ có ý nghĩa khi đi kèm phạm vi và đơn vị. Hồ sơ kiểm tra nên ghi tối thiểu:

```text
Subscription:
Resource provider hoặc dịch vụ:
Region hoặc phạm vi toàn cục:
Tên quota / bộ đếm:
VM family, SKU hoặc tier nếu áp dụng:
Đơn vị:
Usage:
Limit:
Thời điểm lấy số liệu:
```

Azure áp dụng các quota ở nhiều phạm vi khác nhau, tùy loại tài nguyên; có giới hạn theo subscription, region hoặc resource group. Khi lỗi xảy ra, phải đọc tên bộ đếm và phạm vi trong thông báo. Xem [cách xác định quota bị vượt](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-resource-quota).

### 3.1. Resource group không tạo ra quota subscription mới

Giả sử `rg-orders-prod` và `rg-orders-test` cùng dùng một subscription và cùng triển khai VM trong một region. Nếu bị chặn bởi quota vCPU cấp subscription theo region, tạo thêm resource group sẽ không tạo thêm phần hạn mức độc lập cho loại quota đó.

Tương tự, chuyển một VM sang availability zone khác trong cùng region không làm thay đổi phạm vi của quota vCPU cấp region. Đổi zone có thể liên quan đến khả năng cấp phát, nhưng đó là bài toán capacity.

Đây là suy luận từ phạm vi của quota: cách xử lý phải thay đổi đúng yếu tố nằm trong phạm vi bộ đếm, hoặc làm tăng limit của chính bộ đếm đó.

### 3.2. Lập danh sách các phụ thuộc của ứng dụng

Với một ứng dụng web chạy trên Azure, nên lập bảng các thành phần cần kiểm tra trước khi mở rộng:

| Thành phần dự kiến | Nội dung cần tra cứu |
| --- | --- |
| VM hoặc VM Scale Sets | vCPU, VM family, số lượng VM và nhu cầu triển khai tạm |
| AKS sử dụng node VM | vCPU của các node pool, node tạm khi nâng cấp và tài nguyên mạng |
| Virtual Network và kết nối | Các bộ đếm tài nguyên mạng và không gian địa chỉ IP còn lại |
| Storage | Số tài khoản, dung lượng và mục tiêu hiệu năng của loại lưu trữ |
| Dịch vụ cơ sở dữ liệu | SKU, dung lượng, kết nối, thông lượng và quy trình thay đổi tương ứng |
| Danh tính ứng dụng | Quyền Azure RBAC cần thiết và các giới hạn liên quan của dịch vụ danh tính |
| Công cụ triển khai | Tần suất gọi API, mức đồng thời và chính sách retry |

Bảng này là danh sách kiểm tra thiết kế, không khẳng định tất cả mục đều có thể tăng bằng một yêu cầu Quotas. Chẳng hạn, thiếu địa chỉ IP trong subnet cần xem lại thiết kế mạng; tăng vCPU quota không giải quyết được vấn đề đó.

## 4. Hiểu hai tầng vCPU quota của Compute

Đối với standard VM, Azure kiểm tra vCPU quota theo hai tầng trong mỗi subscription và region:

1. **Total Regional vCPUs**: tổng vCPU trong region.
2. **VM-family vCPUs**: vCPU thuộc họ VM tương ứng.

VM mới phải nằm trong cả hai hạn mức. Tăng quota tổng vùng mà họ VM vẫn thiếu thì việc tạo VM vẫn bị chặn. Khi yêu cầu tăng quota họ VM được chấp thuận, Azure có cơ chế tăng quota tổng vùng liên quan; sau xử lý vẫn nên kiểm tra lại cả hai giá trị. Xem [Increase VM-family vCPU quotas](https://learn.microsoft.com/en-us/azure/quotas/per-vm-quota-requests).

### 4.1. Ví dụ tổng vùng đủ nhưng họ VM thiếu

Giả sử một subscription có số liệu sau:

| Bộ đếm | Usage hiện tại | Limit | Phần còn lại |
| --- | ---: | ---: | ---: |
| Total Regional vCPUs | 48 | 64 | 16 |
| Một họ VM mục tiêu | 24 | 32 | 8 |

Ứng dụng muốn thêm bốn VM, mỗi VM có 4 vCPU:

```text
Nhu cầu thêm = 4 × 4 = 16 vCPU

Tổng vùng sau triển khai = 48 + 16 = 64
Họ VM sau triển khai     = 24 + 16 = 40

64 <= 64: đạt điều kiện tổng vùng
40 > 32: không đạt điều kiện họ VM
```

Không thể kết luận triển khai thành công chỉ vì hàng Total Regional vCPUs còn đủ 16. Cần tăng hạn mức họ VM, giảm số VM mới hoặc đánh giá một họ VM khác đáp ứng yêu cầu ứng dụng.

### 4.2. Các điểm cần kiểm tra thêm

- **Spot có quota riêng.** Không lấy phần còn lại của standard quota để suy ra khả năng tạo Spot VM. Tra cứu [Spot vCPU quotas](https://learn.microsoft.com/en-us/azure/quotas/spot-quota).
- **Số VM và số vCPU là các bộ đếm khác nhau.** Cần đọc đúng đơn vị của từng hàng.
- **Không giả định deallocate giải phóng vCPU quota.** Tài liệu Compute tính quota với cả VM allocated và deallocated. Kiểm tra usage thực tế trước và sau thay đổi; chỉ xóa VM không còn cần sau khi đã xét dữ liệu, cấu hình và quy trình phục hồi. Tham khảo [Check vCPU quotas](https://learn.microsoft.com/en-us/azure/virtual-machines/quotas).

Một VM dùng ít CPU không tự trả lại vCPU quota. Nếu muốn giảm nhu cầu cấu hình, phải đánh giá thay đổi kích thước hoặc loại bỏ tài nguyên thừa theo quy trình vận hành.

## 5. Kiểm tra usage và limit trước khi thay đổi

### 5.1. Kiểm tra trong Azure portal

Một luồng kiểm tra thông dụng là:

1. Xác nhận đang ở đúng Microsoft Entra directory và subscription.
2. Tìm **Quotas** trong portal, chọn resource provider phù hợp.
3. Mở **My quotas**, lọc subscription và region.
4. Tìm bộ đếm cần kiểm tra; ghi lại usage, limit, đơn vị và khả năng yêu cầu tăng.
5. Với Compute, đọc cả tổng vùng và họ VM dự định dùng.
6. Đối chiếu những dịch vụ không xuất hiện trong luồng này bằng trang usage hoặc limits riêng.

Tên nút và cách sắp xếp có thể khác theo provider. Luồng gửi yêu cầu được Microsoft mô tả tại [Request a quota increase in the Azure portal](https://learn.microsoft.com/en-us/azure/quotas/quickstart-increase-quota-portal).

Nên chụp số liệu đủ phạm vi thay vì chỉ chép một giá trị như “còn 8”. Giá trị đó cần đi kèm tên quota, đơn vị, subscription, region và thời điểm kiểm tra.

### 5.2. Ví dụ Azure CLI chỉ đọc dữ liệu

Các lệnh dưới đây dành cho PowerShell có Azure CLI đã đăng nhập. Thay subscription ID bằng giá trị thực và chọn region của môi trường cần kiểm tra:

```powershell
$subscriptionId = '<subscription-id>'
$region = 'southeastasia'

az account show --subscription $subscriptionId --query "{Subscription:name,SubscriptionId:id,TenantId:tenantId}" --output table

az vm list-usage --subscription $subscriptionId --location $region --output table

az vm list-usage --subscription $subscriptionId --location $region --query "[].{Quota:name.localizedValue,Key:name.value,Used:currentValue,Limit:limit,Unit:unit}" --output table
```

Lệnh `az vm list-usage` lấy dữ liệu usage của Compute tại region chỉ định, không đại diện cho mọi hạn mức của Azure. Tham khảo [Azure CLI: az vm list-usage](https://learn.microsoft.com/en-us/cli/azure/vm#az-vm-list-usage).

Trong kết quả:

- `name.localizedValue` là tên hiển thị để đọc.
- `name.value` là tên định danh của bộ đếm, hữu ích khi lưu cấu hình kiểm tra.
- `currentValue` là usage được trả về.
- `limit` là trần hiện áp dụng.
- `unit` giúp tránh nhầm số tài nguyên với số vCPU.

Các trường được mô tả trong [Compute Usage REST API](https://learn.microsoft.com/en-us/rest/api/compute/usage/list).

Khi cần kiểm tra usage tài nguyên mạng tại cùng region:

```powershell
az network list-usages --subscription $subscriptionId --location $region --output table
```

Tham khảo [Check Azure network resource usage against limits](https://learn.microsoft.com/en-us/azure/networking/check-usage-against-limits). Lệnh này cũng không thay thế việc kiểm tra dung lượng địa chỉ IP trong subnet hoặc các giới hạn chi tiết của từng cấu hình mạng.

### 5.3. Đọc số liệu có ngữ cảnh

Usage là ảnh chụp của hệ thống tại một thời điểm. Trong môi trường dùng chung, một pipeline khác có thể cấp phát tài nguyên sau khi bạn kiểm tra.

Do đó, kiểm tra trước triển khai giúp phát hiện thiếu hụt sớm nhưng không giữ chỗ quota cho riêng một lần chạy. Với các đợt thay đổi lớn, cần điều phối lịch triển khai và cộng cả nhu cầu của các đội dùng chung subscription.

Nếu limit bằng 0, không tính tỷ lệ bằng phép chia thông thường. Ghi nhận rõ trạng thái, kiểm tra điều kiện sử dụng quota đó và luồng hỗ trợ của dịch vụ trước khi đưa vào kế hoạch.

## 6. Tính hạn mức theo nhu cầu cực đại

Một lỗi lập kế hoạch phổ biến là chỉ tính số tài nguyên ở trạng thái chạy ổn định. Hạn mức cần đáp ứng cả đỉnh tạm thời trong quá trình thay đổi.

Các nguồn làm tăng nhu cầu gồm:

- Autoscale lên mức tối đa đã thiết kế.
- Tài nguyên cũ và mới tồn tại đồng thời trong blue-green deployment.
- VM hoặc node bổ sung khi rolling upgrade.
- Môi trường kiểm thử đang chạy song song.
- Khôi phục hoặc chuyển tải từ một môi trường gặp sự cố.

### 6.1. Công thức lập kế hoạch

Với một bộ đếm cụ thể:

```text
Nhu cầu đỉnh =
    usage của tài nguyên được giữ lại
  + tài nguyên mới cùng tồn tại ở thời điểm cao nhất
  + nhu cầu phát sinh khác trong cùng phạm vi
```

Không cộng lặp tài nguyên cũ đã nằm trong usage hiện tại. Nếu workload mới thay thế workload cũ, phải mô hình hóa thời điểm hai phiên bản cùng tồn tại.

Có thể dùng tỷ lệ sử dụng mục tiêu để tạo khoảng trống vận hành:

```text
Limit mục tiêu >= ceil(nhu cầu đỉnh / tỷ lệ sử dụng mục tiêu)
```

Ví dụ chọn tỷ lệ sử dụng mục tiêu 80% nghĩa là muốn nhu cầu đỉnh chiếm tối đa 80% hạn mức. Đây là lựa chọn lập kế hoạch trong ví dụ, không phải quy định bắt buộc của Azure. Với tài nguyên cấp phát theo nhóm, còn cần làm tròn phù hợp với kích thước VM hoặc đơn vị tăng mà dịch vụ hỗ trợ.

### 6.2. Ví dụ có phần tài nguyên tạm khi triển khai

Tiếp tục ví dụ ở phần 4:

- Họ VM mục tiêu hiện dùng 24 vCPU.
- Các họ VM khác dùng 24 vCPU và giữ nguyên.
- Ứng dụng sẽ tăng lên 10 VM cùng họ, mỗi VM 4 vCPU.
- Khi cập nhật, quy trình có thể tạo thêm tối đa hai VM tạm.
- VM cũ không còn sử dụng được loại bỏ theo đúng quy trình.

Tính nhu cầu:

```text
Họ VM ở trạng thái ổn định = 10 × 4 = 40 vCPU
Phần tạm khi cập nhật      =  2 × 4 =  8 vCPU
Đỉnh của họ VM            = 40 + 8 = 48 vCPU

Đỉnh tổng vùng            = 24 + 48 = 72 vCPU

Nếu dùng mức mục tiêu 80%:
Limit họ VM tối thiểu      = ceil(48 / 0.8) = 60 vCPU
Limit tổng vùng tối thiểu  = ceil(72 / 0.8) = 90 vCPU
```

Kết quả cho thấy tổng quota 64 đủ cho trạng thái ổn định `24 + 40`, nhưng không đủ cho đỉnh cập nhật 72. Quota họ VM 32 thậm chí chưa đủ cho trạng thái ổn định.

Các giá trị 60 và 90 là đầu vào lập kế hoạch. Phải gửi theo đơn vị và lựa chọn thực tế mà Azure cung cấp, rồi xác minh hạn mức được duyệt đáp ứng cả hai điều kiện. Không nhập 28 với ý nghĩa “tăng từ 32 lên 60” khi biểu mẫu yêu cầu **new limit**; ở đó cần nhập tổng hạn mức mong muốn là 60.

### 6.3. Dự phòng ở region khác

Nếu một ứng dụng có phương án phục hồi sang region thứ hai, cần tính quota cho subscription và region đích riêng. Việc tăng ở region chính không tự tăng tất cả region khác. Đây là đặc tính được nêu trong [Increase regional vCPU quotas](https://learn.microsoft.com/en-us/azure/quotas/regional-quota-requests).

Trong kế hoạch phục hồi, hãy ghi tải mà region đích phải tiếp nhận, các workload vốn đã chạy tại đó và số tài nguyên cần trong lúc phục hồi. Một vùng dự phòng gần như không có usage vẫn có thể thiếu quota cho đợt chuyển tải lớn.

## 7. Chuẩn bị yêu cầu tăng hạn mức

### 7.1. Điều kiện và quyền thao tác

Theo quickstart Azure Quotas, luồng yêu cầu trong portal áp dụng cho subscription trả phí và cần tài khoản có vai trò Contributor hoặc vai trò bao gồm quyền tương đương. Không suy ra rằng Owner là lựa chọn duy nhất; với mô hình phân quyền tùy chỉnh, đội quản trị cần đối chiếu đúng thao tác và phạm vi cần cấp. Xem [điều kiện yêu cầu tăng quota](https://learn.microsoft.com/en-us/azure/quotas/quickstart-increase-quota-portal).

Khả năng tạo yêu cầu hỗ trợ là phần quyền cần kiểm tra riêng khi luồng xử lý chuyển sang support. Không có nút thao tác có thể xuất phát từ quyền, loại subscription hoặc chính quota được chọn, thay vì chỉ có một nguyên nhân.

### 7.2. Dữ liệu nên có trước khi gửi

| Thông tin | Mục đích |
| --- | --- |
| Subscription ID và tenant liên quan | Xác định đúng môi trường và danh tính quản trị |
| Dịch vụ, region, tên quota, đơn vị | Xác định đúng bộ đếm cần thay đổi |
| Usage và limit hiện tại | Cho biết tình trạng thực tế |
| Tổng limit mong muốn | Tránh nhầm với số lượng tăng thêm |
| VM family hoặc SKU liên quan | Tránh gửi nhầm họ VM |
| Nhu cầu ổn định và nhu cầu đỉnh | Giải thích cách tính mức yêu cầu |
| Ngày dự kiến sử dụng | Hỗ trợ sắp xếp triển khai |
| Phương án thay thế | Chuẩn bị nếu không được cấp mức mong muốn |

Ví dụ nội dung yêu cầu dùng các số liệu đã tính:

```text
Mục đích: mở rộng ứng dụng xử lý đơn hàng và cập nhật có VM tạm.
Subscription: <subscription-id>
Region: southeastasia
Loại tài nguyên: standard VM
Quota họ VM: <tên/định danh họ VM thực tế>
Hiện tại: usage 24 vCPU, limit 32 vCPU
Tổng limit họ VM đề nghị: 60 vCPU

Đỉnh họ VM dự kiến:
10 VM x 4 vCPU + 2 VM tạm x 4 vCPU = 48 vCPU.

Tổng vùng:
Các họ khác dùng 24 vCPU.
Đỉnh dự kiến 72 vCPU; mức lập kế hoạch tổng vùng là 90 vCPU.

Ngày cần sử dụng: <ngày dự kiến>
Phương án dự phòng: <size/region đã được đánh giá tương thích>
```

Không gửi mật khẩu, access token, connection string hoặc thông tin khách hàng trong phần giải thích nhu cầu. Subscription ID và mã yêu cầu cần được xử lý theo quy trình thông tin của tổ chức.

### 7.3. Gửi và theo dõi

Luồng tổng quát:

1. Mở Quotas và chọn đúng subscription, provider, region.
2. Chọn quota; nếu có luồng điều chỉnh trực tiếp, nhập tổng limit mong muốn.
3. Kiểm tra lại thông tin và gửi yêu cầu.
4. Lưu mã yêu cầu và trạng thái.
5. Nếu quota không có luồng tăng trực tiếp hoặc yêu cầu chưa được đáp ứng, dùng luồng hỗ trợ được cung cấp.
6. Chờ kết quả và đọc lại usage/limit tại đúng phạm vi.
7. Chỉ triển khai theo kế hoạch đã phê duyệt sau khi giá trị thực tế phù hợp.

Có những yêu cầu được xử lý nhanh, nhưng không nên coi thời gian duyệt là một hằng số cho mọi dịch vụ hoặc mọi region. Quyết định cấp quota phụ thuộc việc xét duyệt; việc có hạn mức cũng không bảo đảm capacity. Microsoft mô tả các điều kiện này trong [Quotas overview](https://learn.microsoft.com/en-us/azure/quotas/quotas-overview).

Yêu cầu gửi thành công chưa đồng nghĩa với limit đã thay đổi. Cần phân biệt các trạng thái:

```text
Đã gửi -> Đang xử lý -> Được chấp thuận hoặc không đáp ứng
                                  |
                                  v
                    Đọc lại limit thực tế
                                  |
                                  v
                     Kiểm tra kế hoạch triển khai
```

Nếu kết quả chỉ đáp ứng một phần, tính lại headroom và nhu cầu đỉnh. Tránh gửi nhiều yêu cầu trùng nhau mà không theo dõi quan hệ giữa các mã yêu cầu.

## 8. Phân biệt quota error, capacity error và throttling

Tăng quota đúng là một biện pháp khắc phục; tăng quota theo phản xạ cho mọi lỗi triển khai lại dễ làm chậm xử lý.

### 8.1. Bảng chẩn đoán

| Dấu hiệu | Kiểm tra tiếp | Cách xử lý ban đầu |
| --- | --- | --- |
| Chi tiết lỗi nêu quota, usage, limit hoặc vCPU cần thêm | Phạm vi và bộ đếm bị vượt | Giảm nhu cầu, giải phóng tài nguyên phù hợp hoặc đề nghị tăng đúng quota |
| Quota còn đủ nhưng lỗi nói không cấp phát được size tại nơi chọn | SKU, region, zone và ràng buộc triển khai | Đánh giá phương án cấp phát khác |
| HTTP 429 | Mã lỗi lồng bên trong, header và thao tác liên quan | Xử lý theo nguyên nhân; điều tiết và retry khi thích hợp |
| Authorization hoặc quyền bị từ chối | Danh tính, Azure RBAC và phạm vi thao tác | Điều chỉnh quyền theo quy trình |
| Policy chặn cấu hình | Policy assignment và lý do từ chối | Chọn cấu hình đáp ứng policy hoặc xử lý ngoại lệ hợp lệ |
| SKU không hỗ trợ thuộc tính cần dùng | Tài liệu và cấu hình dịch vụ | Đổi SKU, tier hoặc cách triển khai |

Các tên lỗi cụ thể có thể khác theo provider. Không dùng một mã lỗi cấp ngoài làm bằng chứng duy nhất. Với lỗi deployment, xem lỗi con, tài nguyên đích, region, mã tương quan và thời điểm xảy ra.

### 8.2. Quota không giữ chỗ capacity

Quota cho phép subscription cấp tài nguyên trong giới hạn đã duyệt; capacity là khả năng thực tế của Azure tại nơi cấp phát. Còn quota vẫn có thể gặp thiếu capacity.

Nếu cần đánh giá một size, zone hoặc region thay thế, phải kiểm tra thêm tương thích ứng dụng, hiệu năng, mạng, dữ liệu và yêu cầu phục hồi. Trường hợp cần cơ chế giữ chỗ tài nguyên, nghiên cứu **On-demand Capacity Reservation** theo điều kiện hỗ trợ và chi phí riêng. Tham khảo [Quota and capacity](https://learn.microsoft.com/en-us/azure/virtual-machines/quotas#quota-and-capacity).

Không đổi region chỉ để vượt qua lỗi mà bỏ qua độ trễ tới cơ sở dữ liệu, đường truyền và yêu cầu nơi lưu dữ liệu.

### 8.3. Throttling cần điều tiết nhịp gọi

Khi Azure Resource Manager giới hạn tốc độ, phản hồi có thể là HTTP `429 Too Many Requests` cùng `Retry-After`. Cần đọc chi tiết vì một số provider cũng dùng 429 cho tình huống tạm thời khác. Xem [Azure Resource Manager throttling](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/request-limits-and-throttling).

Hướng thiết kế client và pipeline:

- Tuân thủ `Retry-After` khi được trả về.
- Dùng backoff có giới hạn và jitter để nhiều client không retry cùng lúc.
- Giới hạn số thao tác đồng thời và giảm truy vấn lặp không cần thiết.
- Kiểm tra cơ chế retry sẵn có của SDK để tránh nhiều tầng retry chồng nhau.
- Với thao tác thay đổi tài nguyên, kiểm tra trạng thái trước khi lặp lại để tránh tạo công việc trùng.

Tăng vCPU quota không tự làm tăng tốc độ gọi API. Ngược lại, retry liên tục cũng không giải quyết một quota tài nguyên đã hết: điều kiện usage vượt limit chưa thay đổi.

## 9. Giám sát quota như một phần vận hành

### 9.1. Theo dõi cả phần trăm và phần còn lại

Hai quota cùng sử dụng 80% có thể có ý nghĩa rất khác:

```text
Quota A: usage 8, limit 10     -> còn 2
Quota B: usage 800, limit 1000 -> còn 200
```

Nếu một đợt mở rộng cần 16 đơn vị, cảnh báo theo phần trăm không đủ để xác định khả năng triển khai. Nên theo dõi đồng thời:

- Tỷ lệ usage/limit.
- Headroom tuyệt đối.
- Nhu cầu tăng trong đợt triển khai tiếp theo.
- Tốc độ tăng usage.
- Trạng thái và ngày dự kiến cần kết quả của yêu cầu tăng quota.

Một tín hiệu thực dụng trước triển khai là:

```text
Headroom hiện tại < nhu cầu tăng cực đại của đợt thay đổi
=> kế hoạch hiện tại chưa đủ điều kiện quota.
```

Điều kiện này cần được đánh giá cho từng bộ đếm liên quan, không chỉ tổng vCPU.

### 9.2. Cảnh báo có người chịu trách nhiệm

Ví dụ một đội chọn các mức nội bộ sau:

| Tình huống | Hành động |
| --- | --- |
| Usage vượt mức cảnh báo sớm của đội | Xem dự báo tăng trưởng và lịch triển khai |
| Phần còn lại thấp hơn nhu cầu đợt mở rộng sắp tới | Điều chỉnh kế hoạch hoặc gửi yêu cầu tăng |
| Region phục hồi chưa đủ quota theo kế hoạch | Ghi nhận rủi ro phục hồi và xử lý trước diễn tập |
| Yêu cầu tăng gần ngày cần dùng nhưng chưa có kết quả | Kích hoạt phương án thay thế đã đánh giá |

Azure có luồng tạo quota alert cho các quota được hỗ trợ. Cần xác minh quyền tạo alert, quyền đọc của managed identity và phạm vi dữ liệu. Không suy rộng khả năng giám sát gần thời gian thực cho mọi provider; tài liệu nêu giới hạn hỗ trợ của dữ liệu quota. Tham khảo [Create alerts for quotas](https://learn.microsoft.com/en-us/azure/quotas/how-to-guide-monitoring-alerting).

Một alert chỉ có ích khi đội nhận biết ai xử lý, hành động nào cần làm và khi nào phải chuyển cấp. Sau khi tạo, kiểm tra đường nhận thông báo, trạng thái rule và khả năng đọc dữ liệu của identity.

### 9.3. Đưa quota vào kiểm tra trước triển khai

Với pipeline có nhu cầu cấp thêm tài nguyên, có thể thiết kế bước kiểm tra:

```text
Đọc subscription và region từ cấu hình đích
    -> Lấy usage/limit của các quota liên quan
    -> Tính nhu cầu cực đại theo kế hoạch thay đổi
    -> So sánh từng quota
    -> Báo rõ quota thiếu và mức tối thiểu cần có
    -> Chỉ tiếp tục khi điều kiện triển khai được đáp ứng
```

Kết quả kiểm tra nên có cấu trúc:

```text
Quota: <định danh bộ đếm>
Scope: <subscription + region + family nếu có>
Used: 24
Limit: 32
AdditionalPeakRequired: 24
ProjectedPeak: 48
Result: INSUFFICIENT
```

Không coi bước này là giao dịch đặt chỗ. Trước các thao tác cấp phát lớn, vẫn cần phối hợp với những pipeline dùng chung phạm vi. Nếu tăng quota được tự động hóa, tách rõ hành động **gửi yêu cầu** với điều kiện **limit đã có hiệu lực**.

## 10. Chọn giải pháp khi không tăng được hạn mức

Tùy nguyên nhân, các lựa chọn có thể gồm:

1. **Loại bỏ tài nguyên không còn cần.** Xác minh chủ sở hữu, dữ liệu và phụ thuộc trước khi xóa; sau đó đọc lại usage.
2. **Giảm mức cấp phát quá dư.** Dựa trên số đo để đánh giá resize, số replica hoặc lịch chạy môi trường thử nghiệm.
3. **Giảm phần tăng tạm của triển khai.** Cân đối với thời gian cập nhật và mức sẵn sàng mà ứng dụng yêu cầu.
4. **Chọn họ VM hoặc SKU khác.** Kiểm tra CPU, RAM, kiến trúc bộ xử lý, khả năng đĩa, mạng và hiệu năng thực tế.
5. **Phân chia workload hợp lý.** Chỉ thay subscription hoặc region khi mô hình quản trị, mạng, dữ liệu và vận hành cho phép.
6. **Điều chỉnh thiết kế.** Với giới hạn cố định, xem lại cách phân vùng, chia tài khoản hoặc phân tải theo tài liệu dịch vụ.

Không có lựa chọn nào mặc nhiên phù hợp cho mọi ứng dụng. Ví dụ giảm số VM tạm có thể giảm nhu cầu quota nhưng kéo dài thời gian cập nhật; thay region có thể thêm độ trễ và yêu cầu đồng bộ dữ liệu.

Nếu chạm giới hạn tối đa cố định, một yêu cầu support có thể giúp làm rõ phương án hỗ trợ. Không lập kế hoạch dựa trên giả định rằng support sẽ luôn nâng được trần kỹ thuật.

## 11. Bài thực hành kiểm tra hạn mức bằng thao tác đọc

Mục tiêu thực hành là tạo một bản đánh giá quota cho môi trường, không tạo VM và không gửi yêu cầu tăng.

### Chuẩn bị

Có subscription được phép xem, quyền đọc dữ liệu liên quan và Azure CLI đã đăng nhập hoặc quyền truy cập Azure portal.

### Thực hiện

1. Ghi subscription, tenant và region cần đánh giá.
2. Chạy `az vm list-usage` hoặc xem Compute trong Quotas.
3. Chọn một họ VM mà ứng dụng dự kiến sử dụng; ghi cả quota họ VM và tổng vùng.
4. Tính nhu cầu giả định cho ba VM mới, mỗi VM 4 vCPU.
5. Tính thêm tình huống có một VM tạm khi cập nhật.
6. Với từng bộ đếm, ghi usage, limit, nhu cầu thêm và giá trị sau thay đổi.
7. Soạn nháp yêu cầu tăng nếu thiếu; dừng trước thao tác gửi.

Bảng kết quả có thể dùng dạng sau:

| Quota | Usage quan sát | Limit quan sát | Tăng cực đại dự kiến | Sau thay đổi | Đủ/Thiếu |
| --- | ---: | ---: | ---: | ---: | --- |
| Tổng vCPU vùng | Điền từ môi trường | Điền từ môi trường | 16 | Usage + 16 | So sánh với limit |
| Họ VM mục tiêu | Điền từ môi trường | Điền từ môi trường | 16 | Usage + 16 | So sánh với limit |

Ở đây 16 vCPU gồm `3 × 4` cho ba VM mới và `1 × 4` cho VM tạm. Nếu thực tế là thay thế VM cũ, hãy dựng lại dòng thời gian để tính đúng số VM cùng tồn tại.

Kết quả đạt yêu cầu khi người khác có thể xác định lại đúng phạm vi, hiểu cách tính và nhận biết quota nào cần điều chỉnh từ bản ghi của bạn.

## 12. Các nguyên tắc cần ghi nhớ

- Luôn gắn quota với phạm vi, đơn vị và thời điểm kiểm tra.
- Với standard VM, đọc cả tổng vCPU vùng và quota họ VM.
- Tính nhu cầu đỉnh của mở rộng, cập nhật và phục hồi.
- Nhập tổng limit mong muốn khi biểu mẫu yêu cầu new limit.
- Chờ kết quả và đọc lại limit thực tế trước khi coi yêu cầu đã đáp ứng.
- Phân biệt thiếu quota, thiếu capacity và throttling để chọn cách xử lý.
- Kết hợp giám sát hạn mức với quyền triển khai, kế hoạch chi phí và người chịu trách nhiệm vận hành.
