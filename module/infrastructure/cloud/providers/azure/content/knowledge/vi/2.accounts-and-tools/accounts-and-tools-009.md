# Dọn dẹp tài nguyên và kiểm tra chi phí sau thực hành

Khi thực hành trên Microsoft Azure, bạn thường tạo máy ảo, mạng ảo, địa chỉ IP công khai, tài khoản lưu trữ, cơ sở dữ liệu hoặc workspace giám sát. Những tài nguyên này có thể tiếp tục phát sinh chi phí sau khi bài thực hành kết thúc, kể cả khi ứng dụng không còn được sử dụng. Vì vậy, hoàn tất một bài lab cần bao gồm cả việc xác định tài nguyên đã tạo, dọn dẹp đúng phạm vi và kiểm tra chi phí phát sinh.

Bài học thuộc chương **Tài khoản và công cụ** của module `CLOUD_PROVIDERS_AZURE`. Module giúp bạn khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; đồng thời học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí cho một kiến trúc ứng dụng. Thói quen dọn dẹp và theo dõi chi phí giúp môi trường thực hành luôn rõ ràng, giảm tài nguyên tồn đọng và tránh những khoản chi không cần thiết.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Lập danh sách tài nguyên đã tạo trong một bài thực hành và xác định đúng subscription, resource group, chủ sở hữu.
- Chọn cách xóa toàn bộ resource group hoặc chỉ xóa các tài nguyên riêng lẻ theo phạm vi an toàn.
- Nhận biết tài nguyên phụ thuộc, tài nguyên mồ côi và các dịch vụ vẫn có thể tính phí khi không hoạt động.
- Xác minh quá trình xóa đã hoàn tất và hiểu những dữ liệu có thể còn được lưu giữ.
- Dùng Azure Cost Management để phân tích chi phí theo thời gian, resource group, tài nguyên và dịch vụ.
- Thiết lập ngân sách, cảnh báo và quy trình kết thúc bài lab có thể lặp lại.

## 1. Vì sao phải dọn dẹp sau thực hành?

Azure tính phí theo loại dịch vụ và cách sử dụng. Một số tài nguyên tính phí theo thời gian được cấp phát, một số theo dung lượng lưu trữ, số giao dịch, lượng dữ liệu truyền, thời gian chạy hoặc lượng dữ liệu được thu thập. Do đó, không sử dụng ứng dụng không đồng nghĩa với việc mọi chi phí đã dừng.

Ví dụ:

- Máy ảo đang chạy phát sinh chi phí tính toán. Khi chỉ tắt hệ điều hành bên trong hoặc chuyển sang trạng thái stopped (allocated), phần tài nguyên tính toán có thể vẫn được tính phí. Deallocate máy ảo thường dừng phần chi phí tính toán, nhưng managed disk, snapshot, địa chỉ IP hoặc các tài nguyên mạng liên quan vẫn có thể phát sinh chi phí.
- Managed disk, snapshot và bản sao lưu có thể tiếp tục tính phí theo dung lượng hoặc chính sách lưu giữ dù máy ảo đã bị xóa.
- Public IP, NAT Gateway, Azure Firewall, Application Gateway và các dịch vụ mạng khác có thể có chi phí theo thời gian cấp phát hoặc mức sử dụng.
- Storage account có thể phát sinh chi phí dung lượng, giao dịch, bản sao dữ liệu, phiên bản blob hoặc dữ liệu còn trong vùng soft delete.
- Log Analytics workspace và các dịch vụ giám sát có thể tính phí theo lượng dữ liệu nạp vào và thời gian lưu giữ.
- Cơ sở dữ liệu có thể tính phí theo compute, dung lượng, cấu hình dự phòng hoặc thời gian được cấp phát, tùy mô hình dịch vụ.

Vì vậy, cần kiểm tra toàn bộ tài nguyên thuộc bài thực hành, kể cả các tài nguyên phụ trợ. Dọn dẹp đúng cách vừa giảm chi phí, vừa hạn chế để lộ dữ liệu thử nghiệm, khóa truy cập, endpoint hoặc cấu hình không còn cần thiết.

## 2. Chuẩn bị trước khi xóa

Trước khi thực hiện lệnh xóa, hãy xác định rõ phạm vi và mục đích của từng tài nguyên. Một subscription có thể chứa môi trường học tập của nhiều người hoặc các dịch vụ dùng chung; không nên suy luận rằng mọi tài nguyên trong subscription đều thuộc bài lab của bạn.

### Xác nhận subscription và resource group

Trong Azure CLI, kiểm tra subscription đang được chọn:

```bash
az account show --output table
```

Nếu cần chuyển sang subscription được cấp cho bài lab:

```bash
az account set --subscription "<subscription-id-or-name>"
```

Kiểm tra lại subscription sau khi chuyển. Sau đó xem thông tin resource group:

```bash
az group show \
  --name rg-lab-demo \
  --query "{name:name, location:location, tags:tags, id:id}" \
  --output json
```

Tên `rg-lab-demo` chỉ là ví dụ. Hãy thay bằng tên resource group thực tế của bài thực hành.

### Liệt kê tài nguyên bên trong resource group

Lệnh sau hiển thị tên, loại, khu vực và Resource ID của các tài nguyên trong nhóm:

```bash
az resource list \
  --resource-group rg-lab-demo \
  --query "[].{Name:name, Type:type, Location:location, Id:id}" \
  --output table
```

Nếu bài lab có sử dụng tag để đánh dấu tài nguyên, có thể lọc theo tag:

```bash
az resource list \
  --tag "purpose=training" \
  --query "[].{Name:name, ResourceGroup:resourceGroup, Type:type, Id:id}" \
  --output table
```

Tag chỉ là metadata giúp phân loại và tìm kiếm. Tag không tự động xóa tài nguyên, không ngăn phát sinh chi phí và không chứng minh rằng người gắn tag là chủ sở hữu duy nhất. Hãy đối chiếu tag với nội dung bài lab, thời gian tạo, người phụ trách và các thành phần đang dùng chung.

Một quy ước hữu ích là gắn tag ngay khi tạo tài nguyên, ví dụ:

| Tag | Ví dụ giá trị | Mục đích |
|---|---|---|
| `owner` | `student01` | Nhận diện người phụ trách |
| `purpose` | `training` | Phân biệt tài nguyên thực hành |
| `environment` | `lab` | Phân biệt môi trường lab với dev, staging hoặc production |
| `expiresOn` | `2026-11-30` | Ghi ngày dự kiến kết thúc sử dụng |
| `project` | `azure-basics` | Nhóm tài nguyên theo bài học hoặc dự án |

Ngày hết hạn trong tag chỉ có tác dụng ghi chú nếu chưa có quy trình tự động đọc và xử lý tag đó.

### Kiểm tra tài nguyên dùng chung và khóa xóa

Trước khi xóa resource group, xác nhận nhóm đó được tạo riêng cho bài thực hành và không chứa tài nguyên đang được nhóm khác sử dụng. Nếu chỉ một vài tài nguyên thuộc bài lab nằm trong resource group dùng chung, hãy xóa từng tài nguyên đã xác định thay vì xóa cả nhóm.

Resource lock có thể ngăn thao tác xóa hoặc sửa đổi. Kiểm tra các lock ở cấp resource group:

```bash
az lock list \
  --resource-group rg-lab-demo \
  --output table
```

Lock `CanNotDelete` ngăn xóa tài nguyên; lock `ReadOnly` hạn chế cả thao tác cập nhật. Nếu có lock, cần xác định ai quản lý và lý do bảo vệ trước khi thay đổi. Không xóa lock chỉ để làm cho lệnh dọn dẹp chạy được khi chưa được phép.

## 3. Chọn cách dọn dẹp phù hợp

Có hai cách phổ biến: xóa toàn bộ resource group chuyên dùng cho bài lab hoặc xóa riêng các tài nguyên thuộc bài thực hành. Chọn cách dựa trên ranh giới sở hữu và phạm vi sử dụng.

### Xóa resource group dành riêng cho bài lab

Nếu resource group được tạo riêng cho một bài thực hành và đã xác nhận không còn tài nguyên cần giữ, xóa cả nhóm là cách gọn nhất. Thao tác này yêu cầu Azure xóa các tài nguyên nằm trong resource group đó.

```bash
az group delete \
  --name rg-lab-demo \
  --subscription "<subscription-id>" \
  --yes \
  --no-wait
```

Trong lệnh trên:

- `--name` chỉ rõ resource group cần xóa.
- `--subscription` giúp giới hạn đúng subscription, tránh thao tác nhầm khi tài khoản có nhiều subscription.
- `--yes` xác nhận thao tác trong CLI.
- `--no-wait` cho phép lệnh trả về mà không chờ toàn bộ quá trình xóa kết thúc.

Xóa resource group là thao tác có ảnh hưởng lớn: tất cả tài nguyên nằm trong nhóm có thể bị xóa cùng với nhóm. Dữ liệu hoặc cấu hình cần giữ phải được sao lưu hoặc chuyển đi trước. Tài nguyên được tham chiếu từ nhóm nhưng nằm ở resource group khác không tự động bị xóa; chúng cần được kiểm tra riêng.

### Xóa từng tài nguyên

Trong môi trường dùng chung, liệt kê và xác nhận từng tài nguyên cần xóa. Có thể xóa bằng Resource ID:

```bash
az resource delete \
  --ids "/subscriptions/<subscription-id>/resourceGroups/rg-shared-lab/providers/Microsoft.Network/publicIPAddresses/pip-lab-temp"
```

Lấy Resource ID từ kết quả `az resource list` để tránh ghép sai đường dẫn. Khi xóa từng tài nguyên, kiểm tra quan hệ phụ thuộc trước. Ví dụ, network interface có thể gắn với máy ảo; public IP có thể gắn với network interface hoặc load balancer; disk có thể được giữ lại sau khi máy ảo bị xóa. Một số thao tác xóa tài nguyên cha có thể bị từ chối nếu còn liên kết hoặc tài nguyên con chưa được xử lý.

### Dừng tạm thời hay xóa?

Nếu cần tiếp tục bài lab vào buổi sau, có thể dừng hoặc deallocate một số tài nguyên thay vì xóa. Với máy ảo, ví dụ:

```bash
az vm deallocate \
  --resource-group rg-lab-demo \
  --name vm-lab-demo
```

Deallocate giải phóng phần năng lực tính toán của máy ảo và thường dừng chi phí compute trong thời gian máy ở trạng thái deallocated. Managed disk, snapshot, backup, địa chỉ IP và các dịch vụ liên quan vẫn có thể tính phí. Hãy kiểm tra trạng thái máy ảo và mô hình tính phí của từng dịch vụ.

| Lựa chọn | Khi phù hợp | Điều cần lưu ý |
|---|---|---|
| Xóa resource group | Nhóm được tạo riêng cho một bài lab đã kết thúc | Xóa tất cả tài nguyên trong nhóm; kiểm tra dữ liệu và tài nguyên dùng chung trước |
| Xóa từng resource | Resource group có tài nguyên của nhiều bài hoặc nhiều nhóm | Phải xác định đúng Resource ID và xử lý quan hệ phụ thuộc |
| Deallocate hoặc tạm dừng | Sẽ tiếp tục sử dụng tài nguyên sau đó | Một số thành phần vẫn tính phí; không phải dịch vụ nào cũng có trạng thái dừng |
| Giữ lại có thời hạn | Cần lưu kết quả hoặc chờ đánh giá | Đặt người phụ trách và ngày dọn dẹp cụ thể; theo dõi chi phí trong thời gian giữ |

## 4. Xác minh sau khi xóa

Gửi yêu cầu xóa thành công không luôn đồng nghĩa mọi tài nguyên đã biến mất ngay lập tức. Một số thao tác chạy bất đồng bộ; dịch vụ có thể cần thời gian để hoàn tất việc giải phóng tài nguyên.

Kiểm tra resource group còn tồn tại hay không:

```bash
az group exists --name rg-lab-demo
```

Kết quả `false` cho biết resource group không còn tồn tại trong subscription đang được CLI sử dụng. Nếu lệnh xóa được chạy với `--no-wait`, hãy kiểm tra lại sau một khoảng thời gian. Nếu nhóm vẫn tồn tại, xem trạng thái và thông báo lỗi:

```bash
az group show --name rg-lab-demo --output json
```

Nếu cần kiểm tra một tài nguyên cụ thể:

```bash
az resource show --ids "<resource-id>" --output json
```

Lệnh truy vấn có thể trả lỗi nếu tài nguyên đã bị xóa hoặc không còn quyền đọc. Kết hợp kết quả với danh sách tài nguyên trong resource group và trạng thái trên Azure Portal để xác nhận.

### Tìm tài nguyên còn sót lại

Sau khi xóa resource group, rà soát các tài nguyên liên quan có thể được tạo ở scope khác hoặc được cấu hình để tồn tại độc lập. Những ví dụ thường cần kiểm tra gồm:

- Managed disk, snapshot và image được giữ lại sau khi xóa máy ảo.
- Public IP, network interface, load balancer, NAT Gateway hoặc network security resource không còn được gắn với workload.
- Storage account, container, blob version và dữ liệu soft-deleted.
- Backup vault, recovery point và chính sách lưu giữ bản sao lưu.
- Log Analytics workspace, Application Insights hoặc diagnostic setting gửi dữ liệu đến một workspace khác.
- Private DNS zone, DNS record, route table hoặc tài nguyên mạng nằm trong resource group riêng.
- Dịch vụ hoặc tài nguyên được tạo bởi một bài lab khác nhưng có liên kết đến môi trường vừa xóa.

Không phải mọi thành phần kể trên đều chắc chắn còn tồn tại sau khi xóa resource group; danh sách này là gợi ý để kiểm tra theo kiến trúc thực tế. Hãy đối chiếu Resource ID, quan hệ phụ thuộc và chủ sở hữu trước khi xóa phần còn lại.

### Dữ liệu và chính sách lưu giữ

Xóa tài nguyên quản lý không phải lúc nào cũng đồng nghĩa dữ liệu bị xóa vĩnh viễn ngay lập tức. Một số dịch vụ hỗ trợ soft delete, immutable retention, backup hoặc giữ dữ liệu trong một khoảng thời gian. Key Vault, storage, backup vault và dịch vụ dữ liệu có thể có cơ chế bảo vệ riêng. Cần xem chính sách của dịch vụ và yêu cầu lưu giữ của tổ chức trước khi kết luận dữ liệu đã được loại bỏ hoàn toàn.

Nếu bài lab có tạo secret, access key, certificate hoặc thông tin đăng nhập thử nghiệm, hãy kiểm tra vòng đời của chúng và thu hồi hoặc xoay vòng theo quy trình phù hợp. Không ghi secret vào file báo cáo, log hoặc nội dung bài học.

## 5. Kiểm tra chi phí bằng Azure Cost Management

Sau khi dọn dẹp, dùng Azure Cost Management để xem chi phí đã phát sinh và xác định tài nguyên nào đóng góp nhiều nhất. Người dùng cần quyền xem dữ liệu chi phí tại scope tương ứng; quyền quản lý tài nguyên không nhất thiết đồng nghĩa có quyền xem thông tin billing.

### Mở Cost Analysis

Trong Azure Portal:

1. Mở **Cost Management + Billing**.
2. Chọn billing scope, subscription hoặc resource group phù hợp với phạm vi bài lab.
3. Mở **Cost analysis**.
4. Chọn khoảng thời gian bao gồm thời điểm bắt đầu và kết thúc thực hành.
5. Chọn cách nhóm dữ liệu như Resource, Resource group, Service name hoặc Meter.
6. Áp dụng bộ lọc theo subscription, resource group, resource, service hoặc tag nếu dữ liệu hỗ trợ.

Khi phân tích, nên xem ít nhất hai góc độ:

- **Chi phí theo resource group hoặc tag:** giúp khoanh vùng chi phí của bài thực hành, nhất là khi mỗi lab có resource group hoặc tag riêng.
- **Chi phí theo resource hoặc service:** giúp nhận diện máy ảo, disk, storage, dịch vụ mạng, cơ sở dữ liệu hoặc giám sát đang chiếm phần lớn ngân sách.

Ví dụ, nếu resource group `rg-lab-demo` được dành riêng cho một bài lab, lọc Cost Analysis theo resource group đó rồi nhóm theo Resource để xem từng tài nguyên. Tiếp tục nhóm theo Service name hoặc Meter để hiểu khoản phí thuộc compute, storage, network hay giao dịch.

### Hiểu các cách hiển thị chi phí

Cost Analysis có thể cung cấp các kiểu xem chi phí khác nhau tùy scope và loại hợp đồng:

- **Actual cost** thể hiện chi phí được ghi nhận trên dữ liệu billing trong kỳ. Đây là góc nhìn hữu ích để đối chiếu khoản phí xuất hiện trên hóa đơn hoặc dữ liệu chi phí thực tế.
- **Amortized cost** phân bổ chi phí của một số cam kết mua trước, chẳng hạn reservation hoặc savings plan, theo mức sử dụng trong thời gian tương ứng. Cách xem này giúp phân tích chi phí sử dụng theo tài nguyên và workload.

Khi so sánh hai biểu đồ, hãy kiểm tra loại cost, khoảng thời gian, currency, scope và bộ lọc. Không cộng hoặc so sánh các biểu đồ có phạm vi hoặc phương pháp phân bổ khác nhau mà chưa hiểu khác biệt.

### Vì sao chi phí chưa về 0 ngay sau khi xóa?

Dữ liệu Cost Management có thể được cập nhật trễ so với thao tác tạo hoặc xóa tài nguyên. Một khoản phí hiển thị sau khi dọn dẹp có thể thuộc thời gian tài nguyên còn tồn tại, dữ liệu sử dụng chưa được tổng hợp, hoặc một thành phần độc lập vẫn đang hoạt động.

Khi thấy chi phí sau thời điểm xóa:

1. Mở rộng khoảng thời gian để xem chi phí bắt đầu từ ngày nào.
2. Kiểm tra theo Resource, Service name và Meter để xác định nguồn phát sinh.
3. Đối chiếu Resource ID và thời điểm tạo/xóa trong lịch sử hoạt động hoặc nhật ký triển khai.
4. Kiểm tra các tài nguyên phụ trợ còn tồn tại, kể cả ở resource group khác.
5. Chờ dữ liệu billing cập nhật rồi kiểm tra lại; nếu khoản phí bất thường vẫn tồn tại, đối chiếu chi tiết sử dụng và liên hệ bộ phận quản trị billing.

Không nên kết luận có lỗi tính phí chỉ từ một biểu đồ tức thời. Hãy xét khoảng thời gian tính phí, độ trễ dữ liệu và các khoản phí cam kết hoặc dịch vụ có chu kỳ riêng.

## 6. Ngân sách, cảnh báo và kiểm soát chi phí

Azure Cost Management hỗ trợ tạo budget ở những scope được hỗ trợ, chẳng hạn subscription hoặc resource group. Budget đặt ra ngưỡng theo dõi chi phí trong một kỳ, ví dụ hàng tháng.

Một budget có thể cấu hình:

- Scope: subscription hoặc resource group cần theo dõi.
- Amount: số tiền ngân sách dự kiến.
- Reset period: chu kỳ theo dõi, thường là monthly, quarterly hoặc annually tùy nhu cầu.
- Start và end date: khoảng thời gian áp dụng.
- Alert threshold: ngưỡng cảnh báo, ví dụ 50%, 80% hoặc 100% ngân sách.
- Action group hoặc người nhận thông báo: nơi tiếp nhận cảnh báo theo cấu hình được hỗ trợ.

Budget là công cụ theo dõi và thông báo. **Budget alert không tự động dừng máy ảo, xóa tài nguyên hoặc chặn chi tiêu** khi vượt ngưỡng. Nếu muốn tự động xử lý, cần một quy trình riêng có kiểm soát, quyền phù hợp và cơ chế bảo vệ tài nguyên dùng chung.

Các biện pháp kiểm soát bổ sung:

- Dùng Azure Policy để yêu cầu tag, giới hạn khu vực hoặc kiểm soát loại SKU phù hợp với môi trường học tập.
- Tạo resource group riêng cho từng bài lab hoặc nhóm người học, đặt quy ước tên và ngày hết hạn.
- Ước lượng chi phí trước khi triển khai bằng Azure Pricing Calculator; đây là ước tính theo giả định đầu vào, không phải hóa đơn cam kết.
- Xem khuyến nghị tối ưu chi phí của Azure Advisor nếu subscription có dữ liệu phù hợp.
- Kiểm tra chi phí định kỳ trong Cost Analysis và dùng Cost Management exports nếu cần lưu dữ liệu phân tích dài hạn.
- Hạn chế thời gian chạy máy ảo, database hoặc dịch vụ mạng có chi phí cố định; xóa tài nguyên khi bài lab hoàn tất.
- Đặt thời gian lưu log, backup, snapshot và dữ liệu thử nghiệm theo đúng nhu cầu.

## 7. Quy trình kết thúc một bài lab có thể lặp lại

Áp dụng quy trình sau vào cuối mỗi buổi thực hành:

| Bước | Việc cần làm | Kết quả mong đợi |
|---|---|---|
| 1. Xác nhận scope | Kiểm tra tenant, subscription, resource group và người sở hữu | Biết chính xác môi trường đang thao tác |
| 2. Kiểm kê | Liệt kê tài nguyên, Resource ID, tag và quan hệ phụ thuộc | Có danh sách tài nguyên cần giữ hoặc xóa |
| 3. Bảo toàn dữ liệu cần thiết | Xuất cấu hình, lưu kết quả học tập và sao lưu dữ liệu được phép giữ | Không mất kết quả cần dùng tiếp |
| 4. Dọn dẹp | Xóa resource group riêng hoặc xóa từng tài nguyên đã xác nhận | Tài nguyên tạm thời được loại bỏ |
| 5. Xác minh | Kiểm tra resource group, tài nguyên còn sót, lock và trạng thái xóa | Không còn tài nguyên lab ngoài dự kiến |
| 6. Kiểm tra chi phí | Mở Cost Analysis, lọc theo scope và thời gian, xem chi phí theo resource | Xác định khoản phí của buổi thực hành |
| 7. Ghi nhận | Lưu thời điểm dọn dẹp, kết quả xác minh và chi phí quan sát được | Có dấu vết để đối chiếu và cải thiện lần sau |

Ví dụ nhóm học viên triển khai một máy ảo, virtual network và storage account trong `rg-lab-demo`. Cuối buổi, nhóm kiểm tra đúng subscription, liệt kê ba tài nguyên cùng các thành phần phụ trợ, xác nhận không có dữ liệu cần giữ, rồi xóa resource group. Sau khi `az group exists` trả về `false`, nhóm lọc Cost Analysis theo resource group và khoảng thời gian của buổi học. Nếu chi phí vẫn xuất hiện, nhóm kiểm tra ngày sử dụng, disk hoặc IP ở scope khác và chờ dữ liệu billing cập nhật trước khi báo cáo kết quả.

## 8. Lỗi thường gặp khi dọn dẹp và kiểm tra chi phí

| Tình huống | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Xóa nhầm resource group | Chọn sai subscription hoặc tên nhóm | Kiểm tra `az account show`, xác minh tên và Resource ID trước khi xóa |
| Lệnh xóa bị từ chối | Có resource lock, thiếu quyền hoặc còn phụ thuộc | Kiểm tra lock, role assignment và thông báo lỗi cụ thể |
| Resource group vẫn tồn tại sau lệnh xóa | Xóa đang chạy bất đồng bộ hoặc một tài nguyên không xóa được | Kiểm tra lại trạng thái, mở chi tiết lỗi và xử lý tài nguyên bị chặn |
| Máy ảo đã xóa nhưng vẫn có phí | Disk, snapshot, backup, IP hoặc tài nguyên liên quan còn tồn tại | Kiểm kê tài nguyên phụ trợ và kiểm tra chi phí theo Resource/Meter |
| Đã dọn dẹp nhưng Cost Analysis vẫn hiển thị chi phí | Dữ liệu billing cập nhật trễ hoặc khoản phí phát sinh trước lúc xóa | Kiểm tra khoảng thời gian, loại cost và chờ dữ liệu được cập nhật |
| Không xem được Cost Analysis | Thiếu quyền Cost Management hoặc chọn sai billing scope | Yêu cầu cấp quyền đọc chi phí tại scope phù hợp hoặc chọn đúng scope |
| Chi phí cao dù tài nguyên ít được dùng | SKU lớn, dịch vụ tính phí theo thời gian, lưu trữ hoặc dữ liệu truyền | Xem chi tiết Meter, cấu hình dịch vụ và lựa chọn SKU phù hợp |

## 9. Tự kiểm tra

**Câu 1.** Vì sao một máy ảo đã tắt vẫn có thể liên quan đến chi phí Azure?

**Đáp án:** Nếu máy ảo chưa deallocate, phần compute có thể vẫn được tính phí. Ngay cả khi đã deallocate hoặc xóa máy ảo, managed disk, snapshot, backup, IP và dịch vụ mạng liên quan vẫn có thể phát sinh chi phí.

**Câu 2.** Khi nào nên xóa cả resource group?

**Đáp án:** Khi resource group được tạo riêng cho bài lab, đã xác nhận không có tài nguyên dùng chung hoặc dữ liệu cần giữ và đã kiểm tra đúng subscription. Nếu nhóm chứa tài nguyên của nhiều người hoặc workload khác, chỉ xóa những tài nguyên được xác nhận thuộc bài lab.

**Câu 3.** Lệnh `az group delete --no-wait` có đảm bảo việc xóa đã hoàn tất ngay khi lệnh trả về không?

**Đáp án:** Không. `--no-wait` cho phép CLI trả về mà không chờ quá trình xóa kết thúc. Cần kiểm tra lại bằng `az group exists` hoặc Azure Portal.

**Câu 4.** Budget alert có tự động ngăn subscription tiếp tục phát sinh chi phí không?

**Đáp án:** Không. Budget tạo cảnh báo khi đạt ngưỡng. Muốn tự động dừng hoặc xử lý tài nguyên cần xây dựng quy trình riêng có kiểm soát.

**Câu 5.** Vì sao Cost Analysis vẫn có thể hiển thị chi phí sau khi resource group đã bị xóa?

**Đáp án:** Dữ liệu billing có thể cập nhật trễ và khoản phí hiển thị có thể thuộc thời gian tài nguyên còn hoạt động. Cũng cần kiểm tra tài nguyên phụ trợ ở scope khác hoặc khoản phí có chu kỳ riêng.

## Kết luận

Một bài thực hành Azure chỉ thực sự kết thúc khi tài nguyên được kiểm kê, dọn dẹp đúng phạm vi, trạng thái xóa được xác minh và chi phí được đối chiếu. Hãy xác nhận subscription và quyền sở hữu trước khi xóa; kiểm tra cả tài nguyên phụ trợ, dữ liệu lưu giữ và dịch vụ có thể tiếp tục tính phí; sau đó dùng Cost Analysis, budget và cảnh báo để theo dõi mức sử dụng. Khi duy trì quy trình này cho từng bài lab, bạn sẽ quản lý môi trường Azure rõ ràng hơn, giảm tài nguyên tồn đọng và kiểm soát ngân sách hiệu quả.
