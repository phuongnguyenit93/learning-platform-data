# Phân bổ năng lực bằng capacity reservation

Trong Azure, việc tạo một máy ảo (VM) không chỉ phụ thuộc vào quyền truy cập và số vCPU còn lại trong quota. Vào thời điểm triển khai, nền tảng còn phải có **năng lực tính toán vật lý khả dụng** cho đúng loại máy, vùng (region) và availability zone mà ứng dụng yêu cầu. Khi nhiều hệ thống đồng thời mở rộng trong cùng một khu vực, một yêu cầu tạo hoặc khởi động lại VM từ trạng thái đã giải phóng tài nguyên có thể không được đáp ứng ngay, dù subscription chưa vượt quota.

Đối với workload quan trọng, **Azure On-demand Capacity Reservation** giúp tổ chức đặt trước năng lực tính toán cho những cấu hình VM được hỗ trợ. Azure dành năng lực này cho workload phù hợp ngay cả trong khoảng thời gian chưa có VM sử dụng. Đổi lại, phần năng lực đặt trước nhưng chưa dùng vẫn có thể phát sinh chi phí.

Bài học thuộc chương **Compute co giãn và xử lý theo lô**, trong lộ trình khám phá hệ sinh thái Microsoft Azure từ subscription, resource group, Microsoft Entra ID, mạng ảo đến dịch vụ tính toán, lưu trữ, dữ liệu, giám sát, bảo vệ và kiểm soát chi phí. Trọng tâm là quyết định **khi nào nên giữ sẵn năng lực**, **giữ bao nhiêu**, **phân bổ cho VM/VM Scale Sets thế nào** và **làm sao đo được mức sử dụng cùng chi phí**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao quota, nhu cầu tính toán và năng lực thực tế của Azure là ba vấn đề khác nhau.
2. Phân biệt **On-demand Capacity Reservation**, **Azure Reserved VM Instances**, **Savings Plan** và **Spot VM**.
3. Nhận biết **Capacity Reservation Group**, reservation theo **VM size**, **region**, **availability zone** và số lượng instance.
4. Thiết kế năng lực đặt trước phù hợp với nhu cầu tối thiểu, giờ cao điểm và phương án khôi phục.
5. Mô tả cách tạo capacity reservation, liên kết VM/VM Scale Sets và xác minh số slot đang dùng.
6. Hiểu chi phí cho năng lực chưa sử dụng, giới hạn quota, trạng thái cấp phát và những rủi ro khi thay đổi.
7. Xử lý các tình huống tạo reservation thất bại, VM không khớp SKU/zone, scale-out vượt phần đã đặt trước.
8. Xây dựng quy trình giám sát, ngân sách, tagging và điều chỉnh reservation theo nhu cầu.

## 1. Vấn đề: có quota không đồng nghĩa có năng lực VM

Giả sử một ứng dụng thương mại điện tử dùng máy ảo **Standard_D4s_v5** tại một region Azure. Nhóm vận hành cần khởi động sáu máy trong một availability zone vào thời điểm bắt đầu chương trình khuyến mãi. Subscription có quota đủ 24 vCPU, cấu hình VM và NSG đều hợp lệ, nhưng yêu cầu triển khai vẫn có thể gặp lỗi cấp phát nếu không đủ host tương thích tại đúng khu vực và thời điểm.

Cần tách ba khái niệm:

| Khái niệm | Câu hỏi được trả lời | Điều không được bảo đảm |
|---|---|---|
| **Quota** | Subscription được phép yêu cầu tối đa bao nhiêu tài nguyên/vCPU theo giới hạn áp dụng? | Host vật lý đang sẵn có tại thời điểm cần |
| **On-demand allocation** | Azure có thể cấp ngay một VM cụ thể tại thời điểm tạo/start không? | Có thể cấp lại cùng cấu hình trong tương lai khi năng lực đã được nhả |
| **Capacity reservation** | Azure đã phân bổ năng lực dành riêng cho số lượng VM thuộc cấu hình được hỗ trợ chưa? | Năng lực cho mọi SKU/zone khác hoặc số lượng vượt reservation |

**Quota là giới hạn quản trị, không phải cam kết năng lực.** Tăng quota thường cần thiết khi số lượng VM dự kiến tăng, nhưng tự việc tăng quota không giữ host cho workload. Ngược lại, một reservation cần kiểm tra quota và có thể không được tạo thành công nếu năng lực tại thời điểm đặt trước không khả dụng.

### Vì sao việc dừng VM cần được cân nhắc?

Trong Azure, **stopped (allocated)** và **stopped (deallocated)** không giống nhau. Một VM được **deallocate** thường nhả tài nguyên tính toán để không tiếp tục tính phí compute của VM theo cách thông thường, nhưng khi cần start lại Azure phải cấp phát năng lực.

Nếu workload cần bảo đảm có chỗ cho lần khởi động sau, một **capacity reservation** phù hợp giúp giữ sẵn năng lực dù VM đã deallocate hoặc chưa được tạo. Tuy nhiên, **reservation vẫn có phí khi không có VM sử dụng**. Vì vậy, việc deallocate VM không còn có nghĩa toàn bộ chi phí compute liên quan đều biến mất.

## 2. On-demand Capacity Reservation là gì?

**On-demand Capacity Reservation (ODCR)** là tính năng Azure Compute giúp đặt trước năng lực máy ảo theo cấu hình và phạm vi được hỗ trợ. Sau khi reservation được cấp phát thành công, một số lượng slot tương ứng được dành cho các VM phù hợp, cho đến khi tổ chức điều chỉnh hoặc xóa reservation theo điều kiện sản phẩm.

Mỗi slot có thể hiểu là khả năng phục vụ **một VM đúng kích thước** đã định, không phải một số vCPU trừu tượng có thể thay bằng mọi loại máy.

Ví dụ:

~~~text
Region: Southeast Asia
Availability Zone: 1
VM size: Standard_D4s_v5
Reserved capacity: 4 instances

Tình trạng tại thời điểm A:
  VM đang dùng reservation: 3
  Slot chưa có VM sử dụng: 1

Tình trạng tại thời điểm B:
  VM đang dùng reservation: 4
  Slot chưa có VM sử dụng: 0
~~~

Trong ví dụ, slot dự trữ cho **Standard_D4s_v5** không mặc nhiên dùng được cho **Standard_E4s_v5**, một VM size khác, hoặc cho một availability zone khác. Những ràng buộc chính xác phải được đối chiếu với loại reservation và tính năng SKU đang hỗ trợ.

### “On-demand” nghĩa là gì?

“On-demand” nói đến việc tổ chức **yêu cầu đặt trước khi cần**, thay vì cam kết trước một hợp đồng giảm giá theo thời hạn một năm hoặc ba năm. Nó **không** có nghĩa năng lực luôn khả dụng để đặt. Azure vẫn phải tìm được capacity phù hợp vào lúc tạo/tăng reservation.

Khi đặt thành công, capacity được giữ cho đến khi thay đổi hoặc giải phóng theo điều kiện tương ứng. Bạn vẫn phải **trả phí cho reservation còn hiệu lực** theo cách tính phí của dịch vụ, kể cả khi chưa đặt VM vào slot.

## 3. Cấu trúc tài nguyên: Group, Reservation và VM

Azure quản lý năng lực đặt trước bằng các tài nguyên quản lý:

- **Capacity Reservation Group (CRG):** nhóm logic chứa một hay nhiều capacity reservation.
- **Capacity Reservation:** reservation cụ thể cho **VM size**, **số lượng** và **region/availability zone** tương ứng.
- **Virtual Machine/Virtual Machine Scale Set:** workload có thể được liên kết để tiêu thụ năng lực thuộc group khi cấu hình thỏa yêu cầu.

Sơ đồ:

~~~text
Azure subscription
  |
  +-- Resource group: rg-compute-capacity
        |
        +-- Capacity Reservation Group: crg-sales-prod
              |
              +-- Reservation: cr-d4s-zone1
              |     VM size: Standard_D4s_v5
              |     Zone: 1
              |     Quantity: 4
              |     Used: 3, Unused: 1
              |
              +-- Reservation: cr-d4s-zone2
                    VM size: Standard_D4s_v5
                    Zone: 2
                    Quantity: 3
                    Used: 2, Unused: 1

VM hoặc VMSS đã liên kết cùng CRG
  -> chỉ tiêu thụ reservation khớp size/zone và điều kiện hỗ trợ
~~~

**CRG không tự tạo VM.** Khi group đã tồn tại nhưng chưa có reservation được cấp phát, group chưa đại diện cho năng lực VM sẵn dùng. Khi reservation đã được tạo mà VM chưa liên kết, năng lực có thể đang **nhàn rỗi nhưng vẫn tính phí**.

### Region và availability zone

- **Region** là vùng Azure triển khai năng lực, ví dụ **southeastasia**. Reservation ở một region không bảo đảm cấp phát ở region khác.
- **Availability zone (AZ)** là miền lỗi riêng trong region hỗ trợ AZ. Một VM được cấu hình zone cụ thể phải được ghép với năng lực phù hợp ở zone đó.
- **VM size/SKU** xác định loại tài nguyên tính toán. Không giả định được thay đổi từ D-series sang E-series hoặc từ kích thước này sang kích thước khác mà vẫn giữ quyền dùng slot cũ.
- **Số lượng (capacity)** là số VM của cấu hình tương ứng được đặt trước, không phải tổng số vCPU tự do cho mọi VM.

Sự hỗ trợ của zone, SKU, family, tính năng VM, cách chia sẻ giữa tài nguyên hoặc subscription và vùng Azure có thể thay đổi. Cần kiểm tra ma trận hỗ trợ, quota và tính năng hiện hành trước khi thiết kế.

### Cần gắn reservation vào VM thế nào?

Trong mô hình thông dụng, VM tham chiếu đến **Capacity Reservation Group** bằng cấu hình của tài nguyên VM. Azure đối chiếu VM size/zone với reservation tương ứng trong group.

Việc chỉ đặt VM **cùng resource group** hoặc **cùng VNet** với CRG **không** có nghĩa VM tự sử dụng reservation. Cần chọn group hoặc cấu hình liên kết theo cách được Azure hỗ trợ, sau đó **xác minh liên kết và số lượng đang tiêu thụ**.

## 4. Phân biệt capacity reservation với các lựa chọn tài chính/tính toán

Tên gọi “reservation” dễ gây nhầm giữa đặt **năng lực** và đặt **chiết khấu**.

| Dịch vụ hoặc cơ chế | Mục tiêu chính | Có giữ capacity vật lý phù hợp? | Đặc điểm chi phí |
|---|---|---|---|
| **On-demand Capacity Reservation** | Giảm rủi ro không có capacity khi cần chạy VM đúng cấu hình | Có, khi reservation đã được cấp phát thành công | Trả tiền cho năng lực đã đặt, kể cả phần chưa dùng |
| **Azure Reserved VM Instances** | Giảm chi phí compute đủ điều kiện nhờ cam kết sử dụng theo kỳ hạn | Không tự bảo đảm capacity tại thời điểm triển khai | Cơ chế giảm giá theo cam kết và điều kiện áp dụng |
| **Azure Savings Plan for Compute** | Giảm chi phí compute đủ điều kiện nhờ cam kết chi tiêu | Không tự giữ capacity | Chiết khấu theo điều kiện cam kết chi tiêu |
| **Spot VM** | Tận dụng capacity dư thừa với mức giá thấp hơn theo điều kiện Spot | Không; có thể bị thu hồi | Chi phí thấp hơn nhưng rủi ro bị eviction |
| **VM chạy on-demand thông thường** | Cấp phát khi cần và trả tiền theo sử dụng | Không giữ slot sau khi giải phóng | Tính theo thời gian/loại VM và tài nguyên kèm theo |

Một doanh nghiệp có thể có cả **Reserved VM Instance** để tối ưu giá và **Capacity Reservation** để giải quyết rủi ro cấp phát. Đây là hai quyết định độc lập. Khả năng một loại chiết khấu được áp dụng cho VM hoặc năng lực đã đặt phụ thuộc điều kiện billing cụ thể; **không suy ra rằng đã mua RI thì tự động có capacity**, cũng không suy ra ODCR tự mang lại mức giảm giá RI.

### Không nhầm ODCR với VM Scale Sets

**Azure Virtual Machine Scale Sets (VMSS)** giúp triển khai và mở rộng nhiều VM, còn capacity reservation chỉ giữ sẵn năng lực phù hợp. Một autoscale rule có thể yêu cầu tăng từ 4 lên 8 VM, nhưng nếu số lượng capacity reservation thấp hơn nhu cầu, phần mở rộng vượt phạm vi đặt trước **không được ODCR bảo đảm**.

Khả năng liên kết VMSS với CRG và hành vi cấp phát thực tế phải được kiểm tra theo **orchestration mode, SKU, vùng và điều kiện hỗ trợ**. ODCR không tự đặt ngưỡng min/max instances hoặc tự kích hoạt scale-out.

### Không nhầm ODCR với Availability Zones hay Availability Sets

Availability Zone và những lựa chọn phân tán máy giúp quản lý **failure domain**. Capacity reservation giúp có **năng lực VM sẵn để cấp phát**. Một reservation tại zone 1 không phải là phương án dự phòng zone 2; muốn chịu lỗi cả zone, ứng dụng còn cần phân bố VM, dữ liệu, mạng, load balancing và kế hoạch khôi phục phù hợp.

## 5. Khi nào nên dùng capacity reservation?

**Phù hợp** khi workload có yêu cầu cao về khả năng khởi tạo hoặc khởi động lại VM trong những tình huống cụ thể:

1. **Dịch vụ quan trọng theo giờ cao điểm:** hệ thống thanh toán cần tối thiểu một số instance cố định sẵn có trong mỗi zone.
2. **Khởi động workload theo lịch:** máy phục vụ báo cáo hoặc batch có thể deallocate ngoài giờ nhưng cần có khả năng start lại đúng size/zone trước thời hạn.
3. **Khôi phục sau sự cố:** tổ chức muốn giữ năng lực tại địa điểm dự phòng, đồng thời chấp nhận chi phí duy trì capacity chưa sử dụng.
4. **Mở rộng một tầng dịch vụ nhạy với thiếu capacity:** giữ trước phần baseline của những VM size khó thay thế hoặc có nhu cầu tăng đột biến.
5. **Chuyển đổi lớn theo kế hoạch:** cần bảo đảm có chỗ trước khi chuyển VM vào một region/zone hoặc thay đổi kiến trúc, trong phạm vi tính năng hỗ trợ.

**Thường chưa cần** khi workload nhỏ, VM size linh hoạt, dễ đổi region/zone, không có thời hạn khởi động chặt chẽ hoặc chi phí giữ capacity nhàn rỗi cao hơn ảnh hưởng kinh doanh của việc cấp phát thất bại.

### Đặt trước để phục vụ nhu cầu nào?

Cần phân biệt:

- **Baseline:** mức năng lực tối thiểu phải có chắc chắn theo yêu cầu của hệ thống.
- **Burst:** phần tăng thêm trong đợt cao điểm; có thể không cần đặt trước nếu chấp nhận rủi ro cấp phát.
- **DR headroom:** năng lực dự phòng cho sự kiện khôi phục; có thể gần như không được sử dụng trong vận hành bình thường nhưng vẫn có phí.

Không nên lấy số máy lớn nhất từng dùng rồi mặc định đặt trước toàn bộ quanh năm. Mục tiêu là tìm mức reservation phù hợp **rủi ro nghiệp vụ** và **ngân sách**.

## 6. Bài toán tính số slot cần đặt trước

Giả sử API dùng VM **Standard_D4s_v5**, được phân bổ vào hai availability zone. Dữ liệu đo nhu cầu:

| Thời điểm | Zone 1 | Zone 2 | Tổng |
|---|---:|---:|---:|
| Ban đêm | 2 VM | 2 VM | 4 |
| Giờ làm việc | 3 VM | 3 VM | 6 |
| Cao điểm | 5 VM | 4 VM | 9 |

Nhóm ứng dụng xác định SLO cần **tối thiểu ba VM mỗi zone** trong trường hợp phải thay hoặc khởi động lại VM. Một kế hoạch có thể là:

~~~text
Reservation Standard_D4s_v5:
  Zone 1: 3 slots
  Zone 2: 3 slots
  Total : 6 slots

Night:
  Zone 1: 2 VM dùng, 1 slot nhàn rỗi
  Zone 2: 2 VM dùng, 1 slot nhàn rỗi

Business hours:
  Zone 1: 3 VM dùng, 0 slot nhàn rỗi
  Zone 2: 3 VM dùng, 0 slot nhàn rỗi

Peak:
  Tổng cần 9 VM; chỉ 6 slot thuộc phạm vi đã đặt trước.
  Năng lực còn lại phải được giải quyết bằng phương án scale phù hợp.
~~~

**Lưu ý:** Đây là ví dụ kế hoạch, không phải cam kết rằng ba VM vượt reservation chắc chắn được cấp. Khi VMSS hoặc quy trình triển khai yêu cầu nhiều hơn phần năng lực đã đặt, phải xác minh cách dịch vụ xử lý allocation, quota và khả năng thay đổi group/size theo kiến trúc.

### Công thức lập kế hoạch

Với mỗi tổ hợp cấu hình **(region, zone, VM size)**, chọn:

~~~text
reservedSlots = baselineCapacity + approvedSafetyBuffer

unusedSlotsAtTimeT = max(0, reservedSlots - associatedRunningVMsAtTimeT)

coverageAtTimeT = min(1, reservedSlots / requiredVMsAtTimeT)
~~~

Đây là **chỉ số quản trị tự tính**, không phải công thức tính phí hoặc thuộc tính API chính thức. Với 3 slot và 2 VM đang tiêu thụ, số slot nhàn rỗi là 1. Nếu nhu cầu tăng lên 5 VM thì tỷ lệ năng lực được giữ sẵn chỉ là 3/5, còn việc cấp phát 2 VM vượt phần reservation phụ thuộc các điều kiện khác.

Đừng gom slot của nhiều availability zone rồi coi chúng có thể thay thế nhau. Cần báo cáo **theo từng zone và size**, vì hệ thống cần đúng địa điểm đặt VM.

### Quota và kích thước VM

Một reservation cho **4 VM x 4 vCPU** gắn với yêu cầu năng lực tính toán và giới hạn quota theo loại VM/region áp dụng. Trước khi lập kế hoạch, phải kiểm tra **quota vCPU tổng** và **quota VM family** khi được áp dụng; Azure có thể từ chối tạo/tăng capacity nếu giới hạn hoặc capacity hiện tại không đáp ứng.

**Được tăng quota không có nghĩa reservation sẽ tạo thành công.** Nếu hệ thống cần capacity gấp, hãy chuẩn bị kế hoạch thử zone khác, VM size tương đương khi ứng dụng cho phép và liên hệ bộ phận hỗ trợ theo quy trình hợp lệ.

## 7. Chi phí: phần năng lực không dùng vẫn được tính

Quy tắc kinh tế quan trọng: **Capacity reservation không phải chỗ giữ miễn phí**.

Thông thường, Azure tính chi phí compute tương ứng với những slot đã đặt trước theo cách định giá ODCR. Khi một VM phù hợp sử dụng slot, chi phí compute liên quan được phản ánh theo cơ chế billing của VM và reservation, nhằm tránh hiểu sai là phải trả **hai lần tiền compute** cho cùng một slot đang dùng. Các khoản như disk, network và dịch vụ phụ trợ vẫn có thể có chi phí riêng.

### Ví dụ định lượng

Giả sử minh họa:

- Giá compute **giả định** của một VM đủ điều kiện: **0,25 USD/giờ**.
- Reservation: **4 slot**.
- Số VM đang tiêu thụ slot: **3 VM**.
- Slot chưa dùng: **1 slot**.

Khi đó, cách hình dung **chi phí compute tổng của năng lực đã giữ**:

~~~text
3 slot đang dùng x 0,25 USD/giờ = 0,75 USD/giờ
1 slot chưa dùng x 0,25 USD/giờ = 0,25 USD/giờ
Tổng minh họa                  = 1,00 USD/giờ
~~~

Nếu để 4 slot nhưng không có VM sử dụng, phần capacity nhàn rỗi vẫn có chi phí tương ứng. Khi muốn giảm phí, cần giảm hoặc xóa reservation theo điều kiện hỗ trợ, không chỉ dừng VM.

**0,25 USD/giờ chỉ là giả định học tập**, không phải bảng giá Azure tại Southeast Asia hay cho Standard_D4s_v5. Việc áp dụng RI/Savings Plan, đồng tiền hóa đơn, quy tắc tính phí theo SKU, zone, region và tài nguyên kèm theo phải được đối chiếu với giá hiện hành.

### Chi phí còn có gì?

- OS/data disks, snapshot, backup và dung lượng lưu trữ.
- Public IP, NAT Gateway, Load Balancer/Application Gateway và lưu lượng mạng.
- Azure Monitor/Log Analytics, agents và các dịch vụ bảo mật.
- License phần mềm và cơ chế tính phí hình ảnh có license.
- Chi phí VM dùng vượt reservation khi được cấp thành công.
- Năng lực reserve dư ở size hoặc zone không còn dùng.

Gắn **tag** cho group và reservation, ví dụ **application**, **environment**, **costCenter**, **owner**. Theo dõi **Azure Cost Management**, ngân sách, chi phí reservation nhàn rỗi và báo cáo nhu cầu thực tế để ra quyết định điều chỉnh.

## 8. Quy trình lập kế hoạch triển khai

### Bước 1: kiểm kê workload

Ghi nhận từng workload:

| Thông tin | Ví dụ | Vì sao cần |
|---|---|---|
| Tên workload | sales-api | Xác định nhu cầu và chủ sở hữu |
| Subscription | sub-sales-prod | Đúng phạm vi quyền/quota/chi phí |
| Region | southeastasia | Reservation và VM phải phù hợp khu vực |
| Zone | 1 và 2 | Nhu cầu capacity tách theo zone |
| VM size | Standard_D4s_v5 | Slot gắn với size cụ thể |
| Baseline | 3 VM/zone | Mức năng lực cần giữ |
| Burst | 2 VM bổ sung | Cần phương án cho phần vượt baseline |
| Thời gian | 24/7 hoặc theo lịch | Ước tính phần nhàn rỗi |
| Recovery objective | Ví dụ khởi tạo lại trong thời hạn đã chấp thuận | Xác định mức độ cần reserve |

Nếu VM chạy theo lô chỉ cần khởi động ba ngày mỗi tháng, hãy cân đối giữa phí giữ capacity cả tháng và chi phí kinh doanh khi không thể khởi động đúng thời điểm.

### Bước 2: kiểm tra hỗ trợ và quota

Kiểm tra VM size, region, zone, subscription, quy định loại VM và phiên bản tính năng. Một số loại VM, hình thức cấp phát hoặc tổ hợp tính năng có thể không hỗ trợ ODCR. Không mặc định Spot, Dedicated Host, mọi VMSS mode hoặc các VM chuyên dụng đều có thể dùng cùng cách.

Nếu quota chưa đủ, cần xin nâng quota theo quy trình. Nếu cấu hình reservation không được hỗ trợ, chọn kiến trúc khác thay vì cố gán group.

### Bước 3: phân tích chi phí của mức reserve

Tính theo từng size/zone:

- Số slot cần.
- Thời gian reservation dự kiến có hiệu lực.
- Số giờ slot sẽ **được sử dụng** và **nhàn rỗi**.
- Phần chi phí compute dự kiến và dịch vụ kèm theo.
- Chi phí cơ hội khi không đặt và không thể triển khai trong cao điểm.

Phương án được phê duyệt nên có owner của workload và owner ngân sách. **Tạo reservation đã có thể phát sinh phí ngay cả trước khi deploy VM**, nên không tạo thử trong production mà chưa được đồng ý.

### Bước 4: tạo và kiểm tra reservation

Trong Azure portal hoặc công cụ IaC được hỗ trợ, tạo CRG, sau đó thêm reservation theo VM size/zone/quantity đã tính. Chờ trạng thái cấp phát thành công rồi mới xem slot đó là sẵn sàng.

Nếu tạo thất bại vì thiếu capacity, việc cùng một mẫu deploy lại nhiều lần không chứng minh lần sau sẽ thành công. Cần kiểm tra điều kiện khu vực, quota, size, zone và phương án thay thế.

### Bước 5: liên kết VM hoặc VMSS

Cấu hình các VM/VMSS phù hợp để tham chiếu đến CRG theo tính năng hỗ trợ. Đối chiếu size, location, zone, subscription/resource ownership và những điều kiện phần cứng/triển khai khác.

Đối với **VM hiện có**, thay đổi liên kết có thể đòi hỏi thao tác deallocate hoặc tái triển khai tùy cấu hình và API. Không thực hiện trên production nếu chưa có change window và kế hoạch khôi phục.

### Bước 6: nghiệm thu và vận hành

Xác nhận:

1. Reservation đã provision thành công.
2. VM thực sự được liên kết với đúng group.
3. Số lượng VM tiêu thụ và slot chưa dùng khớp kế hoạch.
4. VM còn đạt health check và ứng dụng hoạt động.
5. Monitoring, cost alerts và runbook điều chỉnh capacity đã được thiết lập.

## 9. Thao tác bằng Azure portal

Tên menu có thể thay đổi theo phiên bản portal, nhưng luồng thực hiện cơ bản:

1. Đăng nhập **Azure portal**, chọn đúng tenant và subscription.
2. Tìm **Capacity reservation groups** hoặc mục **Capacity reservations** trong dịch vụ máy ảo/Compute.
3. Chọn tạo **Capacity Reservation Group**; nhập resource group, tên nhóm và region phù hợp.
4. Trong group, chọn thêm capacity reservation cho **VM size**, **availability zone nếu áp dụng** và **số lượng slot**.
5. Đọc thông tin quota/giới hạn và xác nhận chi phí trước khi tạo.
6. Chờ reservation ở trạng thái provisioned/allocated theo giao diện của dịch vụ.
7. Tạo VM hoặc điều chỉnh VM được hỗ trợ để chọn **Capacity Reservation Group** phù hợp.
8. Xem các VM liên kết và báo cáo capacity đang dùng/chưa dùng trong group.

Với môi trường sản xuất, nên mô tả cấu hình bằng ARM/Bicep/Terraform để đảm bảo review, phát hiện thay đổi ngoài ý muốn và có thể lặp lại trên các environment. Cấu hình trong portal là cách tốt để học và kiểm tra trực quan, không thay thế quản trị thay đổi.

### Ví dụ cấu trúc khai báo dạng khái niệm

~~~yaml
# Pseudoconfiguration để thảo luận kiến trúc — KHÔNG phải manifest Azure hợp lệ.
capacityReservationGroup:
  name: crg-sales-prod
  location: southeastasia
  reservations:
    - name: cr-zone1-d4s
      vmSize: Standard_D4s_v5
      zone: "1"
      count: 3
    - name: cr-zone2-d4s
      vmSize: Standard_D4s_v5
      zone: "2"
      count: 3

virtualMachine:
  name: vm-sales-01
  size: Standard_D4s_v5
  zone: "1"
  capacityReservationGroup: crg-sales-prod
~~~

Ví dụ nhấn mạnh các trường **size**, **zone**, **count** và **group association** phải đồng nhất. Khi triển khai thật, dùng schema ARM/Bicep/Terraform của Azure đang hỗ trợ; không sao chép pseudoconfiguration như một file thực thi.

## 10. Kiểm tra cấu hình bằng Azure CLI

Ví dụ sử dụng Azure CLI để **đọc trạng thái** của group, reservation và VM. Những tên dưới đây là giả định; trước khi chạy cần chọn subscription đúng và có quyền đọc tài nguyên.

### Chọn subscription

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --query "{name:name,id:id}" --output table
~~~

### Liệt kê group và xem chi tiết

~~~bash
az capacity reservation group list \
  --resource-group "rg-compute-capacity" \
  --output table

az capacity reservation group show \
  --resource-group "rg-compute-capacity" \
  --name "crg-sales-prod" \
  --output json
~~~

### Liệt kê reservation trong group

~~~bash
az capacity reservation list \
  --resource-group "rg-compute-capacity" \
  --capacity-reservation-group "crg-sales-prod" \
  --output json

az capacity reservation show \
  --resource-group "rg-compute-capacity" \
  --capacity-reservation-group "crg-sales-prod" \
  --name "cr-zone1-d4s" \
  --output json
~~~

Trong kết quả, quan sát **SKU**, zone, capacity, provisioning state, thông tin capacity được sử dụng/khả dụng và những VM liên kết nếu API có cung cấp. Tên trường kết quả có thể khác theo phiên bản Azure CLI/API và loại reservation; không nên viết bộ giám sát chỉ dựa vào một trường chưa xác minh.

### Kiểm tra VM size và zone

~~~bash
az vm show \
  --resource-group "rg-sales-prod" \
  --name "vm-sales-01" \
  --query "{name:name,size:hardwareProfile.vmSize,zones:zones,capacityReservation:capacityReservation}" \
  --output json
~~~

Kiểm tra VM có tham chiếu đúng group và khớp reservation, không chỉ khớp tên hiển thị. Nếu VM hiện tại không được liên kết, việc nó đang ở đúng region/zone/size chưa đủ để xác nhận nó đã tiêu thụ slot.

### Khi nào nên sử dụng lệnh ghi?

Azure CLI có các nhóm lệnh quản lý capacity reservation để tạo, cập nhật và xóa tài nguyên khi phiên bản CLI hỗ trợ. Vì đây là các thao tác có thể phát sinh phí hoặc ảnh hưởng VM, trong bài thực hành nên **chỉ dùng lệnh đọc**; những lệnh tạo/sửa cần được review bởi chủ sở hữu và kiểm tra help/schema ở phiên bản CLI đang dùng:

~~~bash
az capacity reservation group -h
az capacity reservation -h
az vm update -h
~~~

Không sử dụng một lệnh thay đổi group hoặc quantity trong production trước khi xác nhận ảnh hưởng tới các VM đã liên kết và điều kiện hỗ trợ của Azure.

## 11. Capacity reservation với VM Scale Sets và xử lý batch

### VMSS: giữ sẵn mức baseline

Một hệ thống có VM Scale Set với:

~~~text
VMSS: vmss-api-prod
Min instances: 3
Expected peak: 10
VM size: Standard_D4s_v5
Selected zones: theo thiết kế
Capacity reservation: 3 slot cho phần nền phù hợp
~~~

Ý nghĩa của kế hoạch này: nhóm muốn giảm rủi ro không đủ capacity cho **ba instance nền**. Các instance tăng thêm khi cao điểm không tự nhiên được bảo đảm chỉ vì scale set liên kết reservation.

Cần xác minh chính xác **orchestration mode**, supported VM types, zone distribution, policy cập nhật và hành vi scale khi reservation hết slot. Để đạt SLO, có thể cần tăng số slot hoặc sử dụng nhiều cấu hình/zone, nhưng phải tính chi phí giữ năng lực chưa dùng.

### Workload batch

Giả sử một pipeline xử lý báo cáo chạy từ 1 giờ tới 4 giờ sáng, cần 12 VM cùng kích thước để kịp SLA. Nếu thiếu năng lực vào đúng thời điểm, hàng đợi công việc tăng và kết quả được giao muộn.

Hai lựa chọn:

- **Không đặt trước:** tiết kiệm chi phí giữ slot khi không chạy, nhưng phải có phương án chờ retry, đổi VM size hoặc xử lý muộn.
- **Đặt trước một phần/toàn bộ:** trả phí giữ capacity cả thời gian reservation có hiệu lực, đổi lại giảm rủi ro thiếu slot phù hợp.

Nếu công việc chịu được gián đoạn và chạy lại, có thể đánh giá Spot VM như lựa chọn tối ưu chi phí; Spot **không** dùng để đảm bảo capacity cho deadline cứng. Một kiến trúc batch tốt cần queue, checkpoint, retry, idempotency và theo dõi tiến độ ngoài quyết định đặt trước năng lực.

### Không coi số slot như lịch autoscaling

Capacity reservation không tự quyết định:

- Khi nào khởi động batch.
- Khi nào tăng/giảm instance.
- Có bao nhiêu task chạy đồng thời.
- Có checkpoint/rollback hay không.
- Job nào có ưu tiên cao hơn.

Các quyết định này thuộc scheduler, VMSS autoscale, Azure Batch hoặc hệ thống điều phối ứng dụng tương ứng.

## 12. Chiến lược dự phòng đa zone và disaster recovery

### Đặt trước tại nhiều zone

Một ứng dụng cần duy trì khả năng phục vụ nếu một zone không khả dụng có thể đặt reservation ở hai hoặc nhiều zone được hỗ trợ. Tuy nhiên, việc có slot tại zone 2 **không tự chuyển** VM hoặc dữ liệu từ zone 1 sang zone 2 khi zone 1 gặp sự cố.

Cần kết hợp:

1. Phân bố ứng dụng vào các zone.
2. Load balancer/Application Gateway hay cơ chế định tuyến phù hợp.
3. Replica và failover dữ liệu đúng RPO/RTO.
4. Kiểm thử VM/image/configuration ở zone dự phòng.
5. Năng lực compute và quota cho đúng SKU/zone.
6. Quy trình giám sát và chuyển đổi khi xảy ra sự cố.

### Dự phòng region

Reservation gắn với region của nó. Nếu workload dự kiến khôi phục ở một region thứ hai, việc đặt capacity ở region chính **không** bảo đảm region phụ.

Ví dụ một kiến trúc standby:

~~~text
Primary: Southeast Asia
  VM running: 4
  Reservation matching: 4

Secondary: một Azure region khác
  Standby VM running: 0
  Reservation matching: 4 (nếu được cấp phát và có hỗ trợ)
  Dữ liệu/image/network/runbook: phải chuẩn bị riêng
~~~

Phần reservation tại secondary có thể **gây phí ngay khi chưa có VM**. Nó chỉ giải quyết khía cạnh sẵn năng lực VM; nếu backup chưa thể restore, mạng thiếu kết nối hoặc DNS chưa có kế hoạch, ứng dụng vẫn không đáp ứng RTO.

### Phân tách lỗi placement với lỗi ứng dụng

Capacity Reservation không khắc phục:

- Guest OS hỏng, image không tương thích hoặc VM extension thất bại.
- Cơ sở dữ liệu không khôi phục được hoặc storage không truy cập được.
- NSG, DNS, route hoặc firewall cấu hình sai.
- Hết quota/tài nguyên khác ngoài phạm vi được bảo đảm.
- Lỗi logic của ứng dụng hoặc mã triển khai.

Cần kiểm tra **nhiều lớp** chứ không dùng trạng thái reservation như bằng chứng toàn bộ hệ thống sẵn sàng.

## 13. Thay đổi số lượng reservation và giải phóng capacity

Nhu cầu ứng dụng thay đổi theo thời gian. Nhóm vận hành cần có quy trình điều chỉnh:

### Tăng số slot

1. Xác định size/zone cần tăng và lý do.
2. Kiểm tra quota/giới hạn và ngân sách.
3. Yêu cầu tăng capacity theo công cụ hỗ trợ.
4. Chỉ coi số lượng mới là có hiệu lực khi Azure xác nhận cấp phát thành công.
5. Kiểm tra lại VM/VMSS usage và chi phí.

**Tăng quantity không được bảo đảm thành công**, vì Azure vẫn cần capacity bổ sung phù hợp.

### Giảm số slot

1. Kiểm tra số lượng VM đang **tiêu thụ reservation**.
2. Tính số slot có thể giảm mà không làm vi phạm ràng buộc của tài nguyên đang dùng.
3. Xem các VM dự kiến start/redeploy trong những ngày tới.
4. Thay đổi theo phương án được Azure hỗ trợ và có phê duyệt.
5. Xác minh usage và xem chi phí thay đổi sau chu kỳ billing.

Không giả định có thể giảm quantity **xuống thấp hơn số VM đang dùng**. Azure có những ràng buộc bảo vệ và trạng thái association phải được xử lý trước khi thu hẹp hoặc xóa.

### Xóa capacity reservation

Xóa slot đặt trước là quyết định **giải phóng năng lực**. Các VM hoặc VMSS đang tham chiếu/cần reservation có thể ngăn xóa hoặc cần được di chuyển/rút liên kết theo trình tự hợp lệ.

Quy trình an toàn là kiểm tra những VM liên kết, lên kế hoạch thay thế, xác minh ứng dụng không còn cần capacity được bảo đảm, rồi xóa từng reservation theo hướng dẫn hỗ trợ trước khi xóa group rỗng. Không xem việc xóa CRG tương đương deallocate VM và không dùng lệnh xóa hàng loạt để thử nghiệm.

## 14. Giám sát capacity và chi phí

Trong một subscription có nhiều workload, cần theo dõi capacity reservation như một tài nguyên vận hành độc lập.

### Các chỉ số cần theo dõi

| Chỉ số | Cách hiểu và hành động |
|---|---|
| Reserved instance count | Tổng slot được dành theo VM size và zone |
| Associated/consuming VM count | Bao nhiêu VM đang tiêu thụ reservation ở phạm vi cần kiểm tra |
| Unused reserved slots | Slot đã trả phí nhưng không có VM sử dụng |
| Utilization rate | Used/reserved; tỷ lệ thấp kéo dài cần rà soát ngân sách |
| Allocation/association failures | Lỗi tạo/tăng capacity hoặc VM không khớp group |
| VMSS desired vs actual instances | Phát hiện scale-out không đạt yêu cầu |
| VM provisioning/start failures | Phân biệt thiếu capacity với lỗi quota/image/network |
| Cost by reservation/group/tag | Xác định workload giữ năng lực nhàn rỗi nhiều |
| Planned vs actual peak demand | Kiểm tra mức baseline và buffer có hợp lý |

Ví dụ:

~~~text
CRG: crg-sales-prod
Zone 1 / Standard_D4s_v5
  Reserved: 4
  Used    : 3
  Unused  : 1
  Utilization: 75%

Zone 2 / Standard_D4s_v5
  Reserved: 3
  Used    : 3
  Unused  : 0
  Utilization: 100%
~~~

Nếu utilization liên tục thấp ở zone 1, xem lại nhu cầu thay thế và thời gian cao điểm trước khi giảm slot. Nếu thường xuyên sát 100% và workload bị thiếu capacity khi mở rộng, đánh giá tăng capacity/zone khác chứ không chỉ tăng quota.

### Azure Monitor và Activity Log

Theo dõi thay đổi group/reservation qua **Azure Activity Log** và cơ chế alert/audit phù hợp. Dùng những thuộc tính capacity/association mà Azure hỗ trợ qua portal, Resource Manager hoặc API để tính usage; không khẳng định mọi chỉ số minh họa đều là metric Azure Monitor mặc định với cùng tên.

Nên cảnh báo khi:

- Reservation bị thay đổi quantity hoặc bị xóa ngoài quy trình.
- VM/VMSS không còn tham chiếu CRG cần thiết.
- Một lỗi tạo/tăng capacity xảy ra trong giai đoạn triển khai quan trọng.
- Chỉ số unused capacity cao trong nhiều ngày.
- Chi phí reservation vượt ngân sách được phê duyệt.

### Quản trị quyền và thay đổi

Tạo, thay đổi hoặc xóa capacity reservation là thao tác trên **Azure control plane**. Áp dụng Azure RBAC để giới hạn ai được phép thay đổi group và reservation, đồng thời dùng policy/approval và Infrastructure as Code khi phù hợp.

Không đặt bí mật ứng dụng vào tags hoặc tên reservation. Dữ liệu như cost center, application name và owner phải theo chuẩn tổ chức, không tiết lộ thông tin nhạy cảm.

## 15. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tạo được reservation | Region/zone/SKU thiếu năng lực, quota không đủ hoặc loại VM không hỗ trợ | Xem mã lỗi, subscription quota, vùng và VM size; chuẩn bị size/zone thay thế |
| Tạo CRG thành công nhưng không thấy capacity | Chỉ mới có group; chưa tạo reservation hoặc reservation chưa cấp phát thành công | Kiểm tra các reservation con và provisioning state |
| VM không dùng slot đã đặt | VM chưa liên kết CRG hoặc size/zone không khớp | Xem VM model, group reference, zone và SKU |
| VM có thể tạo nhưng reservation không được tiêu thụ | VM cấp phát theo đường khác hoặc association chưa có hiệu lực | Kiểm tra trạng thái liên kết và usage trên reservation |
| Tăng số slot thất bại | Không còn capacity phù hợp hoặc quota không đáp ứng | Kiểm tra failure detail; cân nhắc kế hoạch thay thế |
| Scale set không đạt desired instances | VMSS config/zone, quota, reservation hoặc allocation khác không phù hợp | So sánh model, trạng thái instance, hoạt động scale và event |
| VM deallocated nhưng chi phí vẫn còn | Reservation chưa dùng vẫn được tính phí | Xem số slot idle và billing của reservation |
| Không giảm/xóa được reservation | Có VM đang tiêu thụ hoặc tham chiếu, ràng buộc quantity | Kiểm tra associated VMs và tài liệu thay đổi/xóa |
| VM lỗi dù slot còn trống | Sai size/zone, image/cấu hình VM/agent/network hoặc trạng thái không phù hợp | So sánh yêu cầu VM với reservation, đọc lỗi chi tiết |
| Dự phòng không kích hoạt sau sự cố | Có capacity nhưng thiếu image, dữ liệu, network, DNS hoặc runbook | Kiểm thử end-to-end khả năng phục hồi |

### Quy trình chẩn đoán

1. Xác định **subscription, resource group, region, availability zone, VM size** thực tế của VM.
2. Đọc **provisioning state** và quantity của reservation đúng group.
3. Xác minh VM/VMSS đã được **associated** theo cấu hình hỗ trợ.
4. Kiểm tra quota, VM family và các ràng buộc tài nguyên còn lại.
5. Xem lỗi cấp phát cụ thể từ Azure, không kết luận ngay rằng “hết quota” hoặc “Azure thiếu capacity”.
6. Kiểm tra trạng thái image/OS disk/VM Agent/network nếu provisioning VM có thành phần lỗi khác.
7. Khi sửa xong, xác minh VM chạy đúng và slot usage thay đổi như dự kiến.

Không nên mở rộng nhóm capacity bất chấp ngân sách chỉ vì một lỗi chưa được phân loại. Cũng không nên giảm quantity vội vàng nếu đang tiến gần một đợt scale-out hoặc diễn tập khôi phục.

## 16. Bài tập tình huống: hệ thống xử lý đơn hàng

Một doanh nghiệp chạy API trên Azure với yêu cầu:

- Region chính: **Southeast Asia**.
- VM size: **Standard_D4s_v5**, giả định được hỗ trợ với cấu hình dự kiến.
- Hai availability zone được chọn.
- Mỗi zone cần **hai VM** trong giờ thấp điểm, **ba VM** khi làm việc và tối đa **năm VM** vào mùa cao điểm.
- Mất khả năng khởi động ba VM nền ở mỗi zone làm vi phạm SLO.
- Doanh nghiệp sẵn sàng trả phí cho capacity nhàn rỗi nhưng muốn tránh đặt trước toàn bộ mười VM quanh năm.

### Nhiệm vụ

1. Xác định mức reservation tối thiểu cho mỗi zone.
2. Giải thích vì sao không nên dùng một reservation zone 1 để thay cho capacity zone 2.
3. Mô tả các CRG/reservation cần tạo, gồm size, zone và quantity.
4. Nêu cách cấu hình VM/VMSS để thực sự sử dụng reservation.
5. Đề xuất xử lý khi mùa cao điểm cần thêm hai VM mỗi zone mà capacity reservation chỉ giữ ba slot.
6. Giả sử mức giá compute minh họa là 0,30 USD/slot-giờ, tính chi phí phần capacity đặt trước khi chạy hai VM mỗi zone.
7. Liệt kê các thông số cần giám sát để biết reservation đang dư hoặc thiếu.
8. Nêu điều kiện cần kiểm tra trước khi giảm quantity và các bước nghiệm thu phục hồi sau sự cố.

### Gợi ý lời giải

Để bảo đảm **ba VM nền mỗi zone**, có thể cân nhắc:

~~~text
Standard_D4s_v5 / Southeast Asia
  Zone 1: reserve 3
  Zone 2: reserve 3
  Total : reserve 6

Off-peak: 2 VM dùng ở mỗi zone
  Used = 4
  Unused = 2
  Reservation footprint = 6 slots

Business hours: 3 VM dùng mỗi zone
  Used = 6
  Unused = 0

Peak: 5 VM mỗi zone
  Required = 10
  Reserved = 6
  Ngoài reservation = 4 VM chưa được phần đặt trước bảo đảm
~~~

Với **giá giả định 0,30 USD/slot-giờ**, mức compute tương ứng cho 6 slot là **1,80 USD/giờ**: khi off-peak, bốn slot đang dùng và hai slot chưa dùng. Kết quả này không phải chi phí Azure thực; chưa gồm disk, network, chiết khấu, thuế hoặc những dịch vụ khác.

Để phục vụ cao điểm, nhóm có thể đặt tăng slot trong thời gian cần thiết **nếu Azure cấp phát được**, hoặc dùng khả năng scale on-demand phù hợp và có phương án fallback (size/zone/giảm tốc độ nhận job) theo yêu cầu nghiệp vụ. Không có giải pháp nào biến sáu slot thành bảo đảm cho mười VM.

## 17. Checklist trước khi triển khai production

| Nội dung | Bằng chứng cần có |
|---|---|
| Mục tiêu | Baseline, burst, RTO/RPO hoặc deadline batch được thống nhất |
| Phạm vi | Subscription, resource group, region và zone đã kiểm tra |
| SKU | VM size/family và tính năng VM được hỗ trợ |
| Quota | Quota vCPU/family đủ và khả năng cấp phát đã được xác minh |
| Cấu trúc | CRG và reservation theo size/zone/quantity rõ ràng |
| Association | VM/VMSS tham chiếu đúng group và matching slot |
| Nghiệm thu | Reservation provision thành công, used/unused đúng kỳ vọng |
| Scale | Phương án khi nhu cầu vượt phần capacity đã đặt trước |
| Bảo mật | RBAC, change approval, tagging và audit |
| Độ sẵn sàng | Nhiều zone/region, image, data, network, failover được kiểm thử |
| Tài chính | Đã dự toán idle cost, báo giá, budget và chi phí tài nguyên kèm |
| Theo dõi | Có bảng usage, chi phí, cảnh báo thay đổi capacity |
| Thay đổi | Có quy trình tăng/giảm/xóa và xử lý VM đang dùng |

## 18. Câu hỏi tự kiểm tra

1. Vì sao quota còn dư không bảo đảm VM được cấp phát ngay?
2. Capacity Reservation Group khác với Capacity Reservation riêng lẻ ra sao?
3. Tại sao reservation cho VM size này không tự dùng được cho mọi size khác?
4. Sự khác nhau giữa đặt trước năng lực và mua Reserved VM Instances để giảm giá là gì?
5. Tạo CRG thành công có chứng minh đã giữ được slot VM chưa?
6. VM cùng region và resource group với reservation có tự dùng slot không?
7. Vì sao phải theo dõi reservation theo từng availability zone?
8. Dừng/deallocate VM khi có ODCR có giúp loại bỏ mọi khoản phí compute liên quan không?
9. Một reservation giữ bốn slot, hai VM đang dùng: có bao nhiêu slot nhàn rỗi?
10. VMSS cần mười instance nhưng chỉ có sáu slot đặt trước: có thể kết luận gì và không thể kết luận gì?
11. Khi nào nên cân nhắc ODCR cho batch chạy theo lịch, và khi nào on-demand/Spot có thể phù hợp hơn?
12. Tại sao capacity reservation ở region chính không bảo đảm năng lực DR ở region phụ?
13. Trước khi xóa reservation, phải kiểm tra những VM hoặc liên kết nào?
14. Những thông tin nào giúp phân biệt lỗi quota, lỗi không đủ capacity và lỗi cấu hình VM?
15. Bạn sẽ tính toán và theo dõi chi phí idle reservation bằng những số liệu nào?

## Tài liệu tham khảo

- Microsoft Learn — *On-demand Capacity Reservation overview*: https://learn.microsoft.com/azure/virtual-machines/capacity-reservation-overview
- Microsoft Learn — *Create capacity reservations*: https://learn.microsoft.com/azure/virtual-machines/capacity-reservation-create
- Microsoft Learn — *Associate a VM with a capacity reservation*: https://learn.microsoft.com/azure/virtual-machines/capacity-reservation-associate-vm
- Microsoft Learn — *Modify capacity reservations*: https://learn.microsoft.com/azure/virtual-machines/capacity-reservation-change
- Microsoft Learn — *Virtual Machines documentation*: https://learn.microsoft.com/azure/virtual-machines/
- Microsoft Learn — *Azure quotas*: https://learn.microsoft.com/azure/quotas/
- Microsoft Learn — *Azure Cost Management documentation*: https://learn.microsoft.com/azure/cost-management-billing/
