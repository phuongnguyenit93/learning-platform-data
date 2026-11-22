# Vòng đời start, stop, deallocate và ảnh hưởng chi phí

Trong Azure, một máy ảo (**Azure Virtual Machine — VM**) có thể đang chạy, đã tắt hệ điều hành nhưng vẫn giữ tài nguyên tính toán, hoặc đã được **deallocate** để Azure giải phóng năng lực compute được cấp cho máy. Cả ba trạng thái có thể khiến người dùng cảm thấy “máy không phục vụ ứng dụng”, nhưng tác động đến **hóa đơn**, **địa chỉ mạng**, **khả năng khởi động lại** và **dữ liệu tạm** rất khác nhau.

Ví dụ, đội phát triển có một VM kiểm thử chỉ dùng trong giờ làm việc. Nếu nhân viên đăng nhập Windows và chọn **Shut down**, VM có thể chuyển sang **Stopped (allocated)**: hệ điều hành tắt, nhưng tài nguyên compute vẫn được cấp và **chi phí compute của VM thường vẫn tiếp tục**. Nếu đội dùng Azure Portal để dừng theo cơ chế deallocate, hoặc gọi lệnh **az vm deallocate**, VM chuyển sang **Stopped (deallocated)**: chi phí sử dụng compute theo giờ thông thường ngừng phát sinh, trong khi **OS disk, data disk và nhiều tài nguyên phụ trợ vẫn tính tiền**.

Bài học này thuộc chương **Máy ảo Azure** của module **CLOUD_PROVIDERS_AZURE**. Trong lộ trình học Azure từ subscription và resource group, danh tính, mạng ảo, compute, lưu trữ đến giám sát, bảo mật và kiểm soát chi phí, việc hiểu đúng vòng đời VM giúp tránh lãng phí, đồng thời giữ cho hệ thống có thể khôi phục an toàn.

> **Thông điệp quan trọng nhất:** **Stopped không nhất thiết bằng deallocated; deallocated không có nghĩa mọi chi phí bằng 0; deallocated cũng không đồng nghĩa xóa VM.**

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **PowerState/running**, **PowerState/stopped** và **PowerState/deallocated**, đồng thời không nhầm chúng với provisioning state.
2. Nêu tác động của **Start**, **Stop**, **Deallocate**, **Restart** và **Delete** đối với tài nguyên tính toán, dữ liệu và hóa đơn.
3. Giải thích vì sao tắt máy từ bên trong hệ điều hành khác với deallocate từ Azure.
4. Dùng Azure Portal, Azure CLI và PowerShell để xem trạng thái, start, stop, deallocate và xác minh kết quả.
5. Lập kế hoạch tắt VM development/test ngoài giờ, tránh ảnh hưởng production và ràng buộc ứng dụng.
6. Nhận diện chi phí tiếp tục phát sinh khi VM deallocated: managed disks, backup/snapshot, IP, networking, giám sát hoặc cam kết giá theo mô hình áp dụng.
7. Đánh giá rủi ro đối với **dynamic IP**, **temporary disk**, **ephemeral OS disk**, capacity và lịch khởi động.
8. Theo dõi chi phí bằng Cost Management, thiết kế lịch tự động hóa và biện pháp bảo vệ.
9. Chẩn đoán tình huống VM không lên, vẫn bị tính phí hoặc ứng dụng mất kết nối sau khi start.

## 2. Hai khái niệm quan trọng: power state và provisioning state

Azure quản lý VM ở nhiều lớp. Muốn hiểu vòng đời, trước hết cần phân biệt:

- **Power state (trạng thái nguồn):** nói VM đang chạy, đã tắt nhưng còn được cấp compute hay đã deallocated.
- **Provisioning state (trạng thái cấp phát/cấu hình):** nói thao tác trên tài nguyên Azure đang được thực hiện hoặc đã thành công/thất bại, ví dụ **Creating**, **Updating**, **Succeeded** hoặc **Failed** theo API và thời điểm.

Hai khái niệm **không thay thế nhau**. Một VM có provisioning state **Succeeded** nhưng power state **VM deallocated** là tình trạng hợp lệ: tài nguyên VM vẫn tồn tại và thao tác quản lý gần nhất thành công, nhưng máy không chạy.

### 2.1. Các power state chính

| Power state thông dụng | Hệ điều hành đang chạy? | Compute còn được cấp cho VM? | Chi phí compute sử dụng VM thông thường |
|---|---|---|---|
| **Running** | Có, nếu guest hoạt động bình thường | Có | Có |
| **Stopped / Stopped (allocated)** | Không | **Có** | **Thường vẫn có** |
| **Stopped (deallocated)** | Không | **Không còn giữ compute theo cách cấp phát thông thường** | **Ngừng tính phí compute sử dụng VM** |
| **Starting / Stopping / Deallocating** | Đang chuyển trạng thái | Tùy giai đoạn | Phụ thuộc thời điểm cấp phát và quy tắc metering thực tế |
| **Deleted** | VM resource không còn | Không | Không còn compute của VM đã xóa, nhưng tài nguyên khác có thể còn |

Tên hiển thị trong Azure Portal, phản hồi Azure CLI và API có thể khác đôi chút. Hãy kiểm tra **power state thực tế** thay vì suy đoán từ việc nút Start/Stop có khả dụng hay không.

Một VM còn ở trạng thái **Stopped (allocated)** vẫn giữ năng lực compute để có thể khởi động mà không phải cấp phát lại cùng kiểu như VM đã deallocated. Điều đó giải thích vì sao một VM “không chạy Windows/Linux” vẫn có thể phát sinh chi phí compute.

### 2.2. Sơ đồ chuyển trạng thái

~~~mermaid
flowchart LR
    R["Running<br/>Compute allocated"]
    S["Stopped (allocated)<br/>Guest OS tắt, vẫn giữ compute"]
    D["Stopped (deallocated)<br/>Compute released"]
    R -->|"Stop từ guest OS hoặc az vm stop"| S
    S -->|"az vm start"| R
    R -->|"az vm deallocate"| D
    S -->|"az vm deallocate"| D
    D -->|"az vm start / Portal Start"| R
    R -->|"az vm restart"| R
~~~

Mô hình trên tập trung vào những trạng thái cơ bản. Từng thao tác có thể trải qua trạng thái trung gian và thất bại do quota, capacity, quyền hoặc lỗi hạ tầng. Các VM cấu hình **hibernation** là trường hợp đặc biệt: cần xem điều kiện hỗ trợ, cách bảo toàn memory và tính phí riêng; không coi đó là deallocation thông thường.

### 2.3. “Stopped” có thể gây hiểu lầm

Ví dụ hai thông báo:

~~~text
PowerState/stopped      → VM stopped (allocated)
PowerState/deallocated  → VM deallocated
~~~

Hai trạng thái đều không phục vụ yêu cầu ứng dụng, nhưng **không tương đương** về compute billing. Trên dashboard hoặc ticket vận hành, nên ghi nguyên trạng thái Azure thay vì chỉ ghi “VM off”.

## 3. Thao tác Start: cấp compute và khởi động guest

**Start** yêu cầu Azure chạy VM, bao gồm việc có đủ compute allocation, khởi động hệ điều hành và các dịch vụ trong guest.

### 3.1. Khi Start từ Stopped (allocated)

Compute vẫn đang giữ; Azure khởi động hệ điều hành trên tài nguyên đã được cấp. Dù vậy, ứng dụng chỉ sẵn sàng khi guest OS, các tiến trình phụ thuộc, network và health check hoàn tất.

### 3.2. Khi Start từ Stopped (deallocated)

Azure phải cấp phát năng lực compute phù hợp trước khi VM chạy. Điều này có thể dẫn tới:

- Thời gian start phụ thuộc vào capacity, cấu hình VM, hệ điều hành và extension.
- Khả năng thiếu capacity của VM size tại vùng/zone vào thời điểm đó.
- Thay đổi vị trí chạy bên dưới khiến **temporary/local disk** không còn nội dung cũ.
- Một số địa chỉ IP cấp động có thể thay đổi, tùy NIC/Public IP SKU và allocation setting.
- Sau khi compute được cấp và VM hoạt động, **chi phí compute bắt đầu phát sinh lại** theo quy tắc dịch vụ.

**Không cam kết** VM deallocated luôn start ngay hoặc luôn giữ IP động. Nếu phải phục vụ đúng thời điểm, cần đưa việc warm-up và kiểm tra ứng dụng vào kế hoạch vận hành.

### 3.3. Start không đồng nghĩa ứng dụng đã Healthy

Power state **Running** chỉ cho biết VM đang chạy theo Azure. Dịch vụ web, database, message consumer hoặc scheduled job có thể chưa sẵn sàng.

Checklist sau start:

1. VM chuyển sang Running.
2. Hệ điều hành, Azure VM Agent và extension cần thiết hoạt động.
3. Ổ dữ liệu cần thiết được mount hoặc gắn drive letter đúng.
4. Network interface, DNS, firewall, NSG và route hoạt động.
5. Ứng dụng có thể kết nối tới database, Key Vault và dependency.
6. Health endpoint, readiness/liveness probe hoặc một phép thử nghiệp vụ thành công.
7. Log và telemetry không có lỗi startup nghiêm trọng.

Với workload có nhiều tầng, cần start theo **thứ tự phụ thuộc**, thay vì gọi Start cùng lúc cho tất cả rồi đánh giá thành công dựa vào power state.

## 4. Stop: tắt hệ điều hành nhưng có thể giữ compute

**Stop**, trong ngữ cảnh Azure CLI **az vm stop** hoặc shutdown từ guest OS, thường chuyển VM về trạng thái **Stopped (allocated)**.

### 4.1. Tắt từ bên trong guest OS

Các ví dụ:

Trên Linux:

~~~bash
sudo shutdown -h now
~~~

Trên Windows, người quản trị có thể chọn **Shut down** từ Start menu hoặc dùng PowerShell phù hợp:

~~~powershell
Stop-Computer -Force
~~~

Điều đó tắt hệ điều hành. Nó **không yêu cầu Azure giải phóng compute allocation** theo nghĩa deallocate. Vì thế **không dùng thao tác shutdown trong Windows/Linux làm bằng chứng tiết kiệm chi phí compute**.

Lệnh PowerShell có **-Force** chỉ là ví dụ về hành vi guest shutdown, có thể ảnh hưởng tiến trình đang mở; không sử dụng bừa bãi với workload còn giao dịch.

### 4.2. Stop từ Azure CLI

~~~bash
az vm stop \
  --resource-group "<resource-group>" \
  --name "<vm-name>"
~~~

Đây là **power off/stop** của VM, không phải lệnh deallocate. Với VM thông thường, trạng thái sau khi hoàn tất là **VM stopped** và compute vẫn được cấp.

Có thể dùng khi cần tạm dừng hệ điều hành nhưng có yêu cầu giữ tài nguyên được cấp; tuy nhiên tổ chức phải chấp nhận chi phí tương ứng.

### 4.3. Stop từ Azure Portal có thể khác Stop từ CLI

Đây là điểm phải ghi nhớ: thao tác **Stop** được chọn tại **Azure Portal** thông thường thực hiện việc dừng và **deallocate** VM, khác với việc shutdown từ hệ điều hành hoặc gọi **az vm stop**.

Vì UI, trạng thái trung gian và cách quản lý dịch vụ có thể thay đổi, cách kiểm tra đáng tin cậy là:

1. Thực hiện thao tác đã chọn.
2. Chờ chuyển trạng thái hoàn tất.
3. Xem lại **Power state** từ Portal/CLI/API.
4. Xác nhận hiển thị **VM deallocated** nếu mục tiêu là ngừng tính phí compute.

**Không kết luận “đã tiết kiệm” chỉ vì nhìn thấy chữ Stop trong lịch sử thao tác.**

## 5. Deallocate: giải phóng compute allocation

**Deallocate** là thao tác trọng tâm khi muốn dừng sử dụng compute của VM và giảm chi phí ngoài giờ.

~~~bash
az vm deallocate \
  --resource-group "<resource-group>" \
  --name "<vm-name>"
~~~

Sau khi deallocate hoàn tất, VM thường chuyển về **Stopped (deallocated)** hoặc **VM deallocated**.

### 5.1. Điều gì thay đổi?

- **Compute:** tài nguyên tính toán được giải phóng khỏi VM; compute usage thông thường không tiếp tục tính phí khi VM deallocated.
- **Tài nguyên VM:** VM resource, cấu hình kích thước, image reference, metadata, tags và các tham chiếu tới disk/NIC vẫn tồn tại.
- **Managed OS disk/data disk:** thường **vẫn tồn tại và dữ liệu vẫn được lưu**; tiếp tục phát sinh chi phí của disk theo cấu hình.
- **Temporary/local disk:** nội dung **không được bảo đảm giữ lại**; phải coi là dữ liệu có thể mất khi deallocate/redeploy.
- **Ephemeral OS disk:** là trường hợp riêng sử dụng lưu trữ cục bộ của host; cần hiểu khả năng dữ liệu bị mất/reimage sau deallocation hoặc thay đổi host.
- **Địa chỉ IP động:** có thể thay đổi sau vòng deallocate/start; kiểm tra cách cấu hình từng loại IP.
- **Capacity:** khi start lại có thể gặp lỗi thiếu tài nguyên của VM size/zone tại thời điểm cấp phát mới.

### 5.2. Điều gì không thay đổi tự động?

Deallocate **không** tự động:

- Xóa các managed disk hoặc snapshot.
- Xóa backup và chính sách retention.
- Xóa Network Interface, Public IP, Load Balancer, NAT Gateway, Azure Bastion.
- Xóa Azure Monitor log hoặc các dữ liệu đã thu thập.
- Hủy Reserved VM Instance/Savings Plan hoặc các khoản cam kết.
- Xóa dữ liệu và secret khỏi tài nguyên khác.
- Dừng mọi dịch vụ Azure mà ứng dụng sử dụng, như Azure SQL Database, Storage Account hoặc Key Vault.
- Thu hồi quyền truy cập RBAC, reset mật khẩu hoặc đóng lỗ hổng bảo mật.

Deallocate vì vậy thường là lựa chọn **giảm chi phí compute**, không phải thủ tục **ngừng hệ thống hoàn toàn và xóa sạch hóa đơn**.

### 5.3. Có nên Stop trước rồi Deallocate?

Với workload có dữ liệu đang ghi, ưu tiên **quiesce** ứng dụng: dừng nhận yêu cầu mới, hoàn thành hoặc hủy giao dịch có kiểm soát, flush dữ liệu và đóng dịch vụ theo trình tự phù hợp.

Sau đó thực hiện deallocate bằng cơ chế Azure. Việc có cần thêm thao tác guest shutdown trước hay không phụ thuộc yêu cầu của ứng dụng và runbook; mục tiêu cuối cùng vẫn phải kiểm tra **VM deallocated**.

Không nên dựa vào deallocation như một cơ chế snapshot nhất quán của database. Nếu cần backup application-consistent, thực hiện backup/checkpoint theo công cụ tương ứng.

## 6. Restart, Redeploy, Reimage và Delete không phải cùng thao tác

Các thao tác thường dễ bị nhầm với Start/Stop:

| Thao tác | Mục tiêu | Lưu ý quan trọng |
|---|---|---|
| **Restart** | Khởi động lại VM/guest | VM vẫn dùng compute; không phải cách tiết kiệm chi phí |
| **Stop (allocated)** | Tắt guest nhưng giữ allocation | Thường vẫn bị tính phí compute |
| **Deallocate** | Dừng VM và giải phóng compute | Ngừng compute usage, vẫn có các chi phí khác |
| **Redeploy** | Chuyển VM sang host khác để khắc phục một số lỗi hạ tầng | Có downtime; temporary data và placement có thể thay đổi |
| **Reimage** | Tái tạo OS disk theo cơ chế của loại VM | Có thể làm mất thay đổi ở OS disk; cần kế hoạch bảo vệ dữ liệu |
| **Delete VM** | Xóa tài nguyên VM | Disk, NIC, Public IP có thể bị giữ lại hoặc xóa tùy cấu hình delete options và quy trình |

Nếu chỉ cần giảm hóa đơn VM dev/test, **deallocate** thường đúng mục tiêu hơn delete. Nếu muốn ngừng dịch vụ lâu dài và xóa chi phí đĩa, có thể cần quy trình **backup/export → xác nhận giữ dữ liệu → delete resource và các dependency** theo chính sách tổ chức.

**Delete** là thao tác có rủi ro dữ liệu và cấu hình cao hơn rất nhiều so với deallocate. Không dùng để thử tối ưu chi phí khi chưa xác định chính xác tài nguyên sẽ bị xóa theo delete options.

## 7. Bảng tổng hợp: trạng thái VM và chi phí

Đối với VM kiểu pay-as-you-go thông thường:

| Loại chi phí / tài nguyên | Running | Stopped (allocated) | Stopped (deallocated) |
|---|---|---|---|
| **VM compute usage** | Có | **Có** | **Không**, theo cơ chế deallocation |
| **Managed OS disk** | Có | Có | **Có** |
| **Managed data disk** | Có | Có | **Có** |
| **Snapshot/backup** | Nếu được cấu hình | Vẫn có thể có | **Vẫn có thể có** |
| **Standard Public IP** | Theo SKU và trạng thái của IP resource | Theo SKU/cấu hình | **Có thể vẫn tính phí** nếu còn cấp giữ IP |
| **Load Balancer/NAT Gateway/Bastion/Firewall** | Theo dịch vụ | Vẫn có thể tính phí | **Vẫn có thể tính phí** |
| **Azure Monitor/Log Analytics** | Theo phát sinh và retention | Theo dữ liệu lưu/thu thập | Dữ liệu đã thu thập vẫn có thể tính phí |
| **Reserved Instance/Savings Plan commitment** | Theo cam kết đã mua | Cam kết vẫn tồn tại | **Cam kết vẫn tồn tại** |

Đây là bảng khái niệm, không phải hóa đơn hoặc quy tắc giá duy nhất. Một số VM plan/license, Dedicated Host, Capacity Reservation hoặc sản phẩm Marketplace có mô hình tính phí riêng. Kiểm tra điều khoản của SKU, hợp đồng và thông tin sử dụng trong Cost Management.

### 7.1. Vì sao managed disks vẫn tính tiền?

Managed disk là **tài nguyên lưu trữ tách biệt** với compute của VM. Khi deallocate, Azure không tự xóa nội dung của OS disk/data disk. Việc giữ dữ liệu để start lại sau này cần dung lượng lưu trữ.

Mức phí có thể phụ thuộc vào:

- Loại disk: Standard HDD, Standard SSD, Premium SSD, Premium SSD v2, Ultra Disk...
- Dung lượng được cấp phát và cách SKU tính phí.
- Cấu hình hiệu năng IOPS/throughput ở những loại disk có thể cấu hình riêng.
- Redundancy, region, snapshot và các cơ chế backup.
- Những tính năng khác được bật theo mô hình tính phí dịch vụ.

Vì vậy, VM deallocated vài tháng vẫn có thể tạo ra **hóa đơn lưu trữ đáng kể** nếu gắn nhiều đĩa lớn.

### 7.2. Public IP và địa chỉ mạng

Địa chỉ IP nên được xét thành hai vấn đề:

1. **Tính ổn định:** một địa chỉ cấp động có thể đổi sau deallocation/reallocation, tùy loại tài nguyên và cấu hình. Static IP giúp giữ địa chỉ khi resource còn tồn tại theo điều kiện SKU.
2. **Chi phí:** một Public IP resource vẫn có thể phát sinh phí riêng, kể cả khi VM không chạy; phụ thuộc SKU và mô hình tính phí.

Không giả định địa chỉ IP tĩnh miễn phí, cũng không mặc định mọi IP động đều thay đổi sau mỗi lần start. Hãy kiểm tra NIC IP configuration, public IP resource và chính sách DNS thực tế.

Tốt hơn hết, ứng dụng production nên dùng DNS/tên dịch vụ và kiến trúc load balancing phù hợp thay vì hard-code một public IP động của VM.

### 7.3. VM reservations, savings plans và license

**Azure Reservations** hoặc **Savings Plans** là những mô hình cam kết giá/sử dụng có điều kiện. Nếu VM mục tiêu deallocated:

- Có thể ngừng phát sinh usage compute riêng của VM đó.
- Khoản **cam kết đã mua** thường vẫn tiếp tục tồn tại theo hợp đồng.
- Lợi ích cam kết có thể áp dụng cho tài nguyên đủ điều kiện khác hoặc có phần chưa được sử dụng.

Vì vậy **chi phí hiển thị của một VM giảm** không bảo đảm **tổng số tiền tổ chức phải trả** giảm đúng bằng số giờ compute trong mọi trường hợp. Nếu dùng Windows Server, SQL Server, Dedicated Host hay phần mềm Marketplace, phải kiểm tra license và điều khoản riêng.

### 7.4. Deallocated không phải bảo mật hoàn toàn

VM tắt vẫn là tài nguyên cloud có disk, cấu hình, network resource và quyền quản lý. Người có quyền thích hợp vẫn có thể thao tác trên VM hoặc disk, tạo snapshot, đổi role assignment, v.v.

Khi VM không chạy:

- Giữ RBAC theo least privilege.
- Bảo vệ disk bằng cơ chế mã hóa phù hợp.
- Quản lý snapshot/backup và quyền của danh tính liên quan.
- Giữ network rule/NSG đúng trạng thái mong muốn.
- Tiếp tục giám sát hoạt động control plane qua Activity Log.

Không coi Stop/Deallocate là biện pháp ngăn truy cập dữ liệu tương đương xóa khóa mã hóa hoặc thu hồi credential.

## 8. Tình huống minh họa: VM development chỉ cần giờ hành chính

Một nhóm dùng VM kiểm thử chạy trung bình **8 giờ mỗi ngày**, **22 ngày trong một tháng 30 ngày**. Ngoài khoảng thời gian đó, không có người dùng và không có công việc batch phải chạy.

Để minh họa, giả sử **đơn giá compute quy ước là 0,25 USD/giờ**. Đây là số giả định cho bài toán, **không phải bảng giá Azure**. Một tháng 30 ngày có 720 giờ.

| Phương án | Giờ compute sử dụng theo ví dụ | Compute cost giả định |
|---|---:|---:|
| Chạy/giữ compute suốt tháng | 720 | 180 USD |
| Deallocate ngoài giờ, chỉ chạy 8 giờ × 22 ngày | 176 | 44 USD |
| Phần compute usage có thể tránh | **544** | **136 USD** |

Công thức đơn giản:

~~~text
Compute hours cần dùng = 8 giờ/ngày × 22 ngày = 176 giờ
Compute hours cả tháng    = 30 ngày × 24 giờ   = 720 giờ
Giờ tránh cấp compute     = 720 - 176          = 544 giờ

Compute usage ước lượng nếu chạy liên tục = 720 × 0,25 = 180 USD
Compute usage nếu chỉ chạy khi cần        = 176 × 0,25 =  44 USD
Chênh lệch compute usage                  = 136 USD
~~~

**Chưa tính** thời gian warm-up, giờ thao tác phát sinh, disk, Public IP, backup, monitoring, network, license hoặc khoản cam kết giá. Giá thực tế theo region, VM size và mô hình mua có thể khác đáng kể.

### 8.1. Chi phí tổng không bằng compute cost

Một mô hình dự toán dễ hiểu:

~~~text
Tổng chi phí =
    VM compute usage
  + Managed OS/data disks
  + Backup và snapshot
  + Public IP / Load Balancer / các dịch vụ mạng liên quan
  + Monitoring và log retention
  + License/Marketplace/commitment theo hợp đồng
  + Các dịch vụ khác của workload
~~~

Deallocate tác động trực tiếp nhất tới **compute usage**; các mục còn lại phải xem xét riêng.

### 8.2. Chênh lệch giữa hiệu quả kỹ thuật và hiệu quả tiền mặt

Nếu nhóm đã mua Savings Plan/Reservation và vẫn trả khoản cam kết cố định, việc dừng một VM có thể giúp **giảm usage được quy cho VM** nhưng khoản tiền tổ chức chi ra trong kỳ chưa giảm tương ứng nếu cam kết không được dùng lại.

Khi báo cáo FinOps, nên phân biệt:

- **Usage reduction:** giảm số giờ máy được cấp compute.
- **Billed compute reduction:** thay đổi các khoản phí thực tế.
- **Commitment utilization:** phần cam kết đã mua được dùng hiệu quả đến đâu.
- **Total workload cost:** tổng của compute, storage, network, logging và dịch vụ liên quan.

## 9. Xem trạng thái VM bằng Azure Portal

Trong Azure Portal:

1. Vào **Virtual machines**.
2. Chọn đúng subscription/resource group và VM.
3. Xem mục **Status/Power state** trên trang Overview.
4. Nếu cần, mở phần **Properties** hoặc **Activity Log** để xem thao tác gần nhất.
5. Khi quản lý nhiều VM, lọc theo resource group, tag hoặc power state được giao diện hỗ trợ.
6. Xác nhận **Stopped (deallocated)** đối với VM chủ đích giảm compute usage.

Một số trạng thái có thể cần thời gian chuyển đổi sau khi bấm Stop hoặc Start. Không thao tác lại liên tục chỉ vì Portal chưa refresh ngay lập tức.

### 9.1. Cách dùng nút Start và Stop

- **Start:** yêu cầu VM chạy và cấp compute khi cần.
- **Stop trên Portal:** thường dừng và deallocate, nhưng cần kiểm tra Power state cuối cùng.
- **Restart:** khởi động lại, không phải cách deallocate.

Các vị trí nút thay đổi theo phiên bản Portal; **điều cần xác minh là state cuối cùng**, không phải nhãn lệnh trong giao diện.

### 9.2. Đọc thông tin tài nguyên liên quan

Trước khi deallocate VM quan trọng, xem:

- OS/data disks và loại disk.
- NIC, private IP, Public IP và allocation method.
- VM size, availability zone/set, capacity constraints.
- Tình trạng backup, monitoring và cảnh báo.
- Các resource phụ thuộc như load balancer, Application Gateway hoặc database.
- Tag chủ sở hữu và lịch vận hành.

Một VM không còn được người dùng truy cập trực tiếp vẫn có thể chạy job, agent, scheduled task hoặc tác vụ bảo trì nền. Không deallocate chỉ vì CPU thấp ở một thời điểm.

## 10. Azure CLI: kiểm tra trạng thái, start, stop và deallocate

Các ví dụ sau dùng **Bash** trong Azure Cloud Shell hoặc shell đã cài Azure CLI. Những placeholder phải được thay bằng tài nguyên thật. **Chỉ thao tác trên VM do bạn được phép quản lý, ưu tiên môi trường lab**.

### 10.1. Chọn đúng subscription và VM

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-vm-lab"
VM="vm-demo-01"
~~~

Kiểm tra VM có tồn tại và xem trạng thái:

~~~bash
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "{name:name,location:location,provisioningState:provisioningState,powerState:powerState,size:hardwareProfile.vmSize}" \
  --output json
~~~

**Power state** từ tùy chọn **--show-details** là một cách đọc thuận tiện. Cũng có thể xem instance view:

~~~bash
az vm get-instance-view \
  --resource-group "$RG" \
  --name "$VM" \
  --query "statuses[?starts_with(code, 'PowerState/')].{code:code,status:displayStatus}" \
  --output table
~~~

Ví dụ trạng thái được trả về có thể chứa:

~~~text
PowerState/running       VM running
PowerState/stopped       VM stopped
PowerState/deallocated   VM deallocated
~~~

Đây là **các giá trị minh họa**, không phải kết quả đã chạy trên subscription thực. Nếu lệnh không hiển thị dữ liệu, hãy kiểm tra quyền, tên VM, trạng thái instance view và phiên bản CLI.

### 10.2. Start VM

~~~bash
az vm start \
  --resource-group "$RG" \
  --name "$VM"
~~~

Kiểm tra sau khi lệnh hoàn tất:

~~~bash
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "powerState" \
  --output tsv
~~~

Kỳ vọng thấy **VM running** sau khi trạng thái ổn định. Tiếp tục kiểm tra health của ứng dụng; command hoàn tất không đồng nghĩa mọi dịch vụ trong guest đã sẵn sàng.

### 10.3. Stop nhưng giữ compute allocated

~~~bash
az vm stop \
  --resource-group "$RG" \
  --name "$VM"
~~~

Đọc lại trạng thái:

~~~bash
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "powerState" \
  --output tsv
~~~

Thông thường kỳ vọng **VM stopped**, **không phải VM deallocated**. Vì vậy đây **không phải lệnh tiết kiệm compute ngoài giờ**.

### 10.4. Deallocate để giải phóng compute

~~~bash
az vm deallocate \
  --resource-group "$RG" \
  --name "$VM"
~~~

Sau khi hoàn tất:

~~~bash
az vm get-instance-view \
  --resource-group "$RG" \
  --name "$VM" \
  --query "statuses[?starts_with(code, 'PowerState/')].{code:code,status:displayStatus}" \
  --output table
~~~

Kỳ vọng **PowerState/deallocated**. Chỉ khi trạng thái deallocated được xác nhận mới nên ghi nhận rằng bước giải phóng compute đã hoàn tất về mặt kỹ thuật.

### 10.5. Liệt kê trạng thái của cả resource group

~~~bash
az vm list \
  --resource-group "$RG" \
  --show-details \
  --query "[].{name:name,powerState:powerState,vmSize:hardwareProfile.vmSize,location:location}" \
  --output table
~~~

Dùng cách này trước khi lập kế hoạch auto-shutdown để tránh bỏ sót VM. Nếu muốn lọc theo nhiều subscription, hãy chạy đúng quyền và scope; không mặc định một kết quả từ resource group đại diện toàn tổ chức.

### 10.6. Khi dùng --no-wait

Một số lệnh hỗ trợ **--no-wait** để trả quyền điều khiển về shell trước khi thao tác hoàn tất. Ví dụ:

~~~bash
az vm deallocate \
  --resource-group "$RG" \
  --name "$VM" \
  --no-wait
~~~

Lúc này lệnh đã gửi yêu cầu, **không chứng minh VM đã deallocated**. Scheduler/runbook phải có bước theo dõi trạng thái cuối cùng và xử lý timeout, lỗi hoặc thao tác trùng.

Đặc biệt, không gửi Start ngay sau một yêu cầu Deallocate chưa hoàn tất mà không kiểm tra state; các thao tác thay đổi power liên tiếp có thể gây xung đột.

## 11. Azure PowerShell và thao tác trong guest OS

Với môi trường dùng module **Az PowerShell**, các lệnh điển hình:

~~~powershell
Connect-AzAccount
Set-AzContext -SubscriptionId "<subscription-id>"

$rg = "rg-vm-lab"
$vm = "vm-demo-01"

# Đọc thông tin VM và instance status
Get-AzVM -ResourceGroupName $rg -Name $vm -Status

# Start VM
Start-AzVM -ResourceGroupName $rg -Name $vm

# Stop và deallocate theo hành vi thông thường của Stop-AzVM
Stop-AzVM -ResourceGroupName $rg -Name $vm
~~~

Trong **Az PowerShell**, **Stop-AzVM** theo hành vi thông thường sẽ deallocate VM. Tùy chọn **-StayProvisioned** dành cho tình huống muốn VM dừng nhưng **vẫn giữ allocation**:

~~~powershell
Stop-AzVM -ResourceGroupName $rg -Name $vm -StayProvisioned
~~~

Do đó, **Stop-AzVM không đồng nghĩa mặc định với az vm stop của Azure CLI**. Đây là khác biệt rất quan trọng khi chuyển script giữa Bash/Azure CLI và PowerShell.

So sánh:

| Cách thao tác | Kết quả thường hướng tới | Có phải deallocate? |
|---|---|---|
| Linux **shutdown -h now** bên trong VM | Stopped (allocated) | Không |
| Windows **Shut down** trong guest | Stopped (allocated) | Không |
| **az vm stop** (Azure CLI) | Stopped (allocated) | Không |
| **az vm deallocate** (Azure CLI) | Stopped (deallocated) | Có |
| **Stop** ở Azure Portal | Thông thường Stopped (deallocated) | Thường có; xác minh state |
| **Stop-AzVM** không có StayProvisioned | Thông thường Stopped (deallocated) | Có |
| **Stop-AzVM -StayProvisioned** | Stopped (allocated) | Không |

Luôn đối chiếu hành vi của **phiên bản công cụ và loại VM** đang dùng, thay vì suy từ từ khóa “stop” một cách máy móc.

## 12. Cảnh báo về dữ liệu: OS disk, data disk, temporary disk

Một số thao tác start/deallocate dẫn tới thay đổi tài nguyên compute bên dưới. Vì vậy cần phân biệt ba loại lưu trữ.

### 12.1. Managed OS disk

VM dùng **managed OS disk** thông thường lưu hệ điều hành trên tài nguyên đĩa được quản lý, tách khỏi host compute. Khi deallocate, OS disk được giữ lại nếu không xóa resource tương ứng.

Ví dụ:

- Cấu hình ứng dụng trên OS disk vẫn còn sau deallocate/start thông thường.
- Log/secret tạm thời trên OS disk cũng vẫn còn, vì vậy **deallocation không xóa dữ liệu nhạy cảm**.
- Phí OS disk vẫn có thể tiếp tục phát sinh.

### 12.2. Managed data disk

**Managed data disk** chứa dữ liệu được chủ động gắn với VM và thường vẫn tồn tại khi VM deallocate. Tuy nhiên:

- Nếu ứng dụng dùng database, cần bảo đảm thao tác ghi được flush trước khi dừng.
- Khi VM start lại, kiểm tra disk attachment, drive letter, mount point và dịch vụ phụ thuộc.
- Thao tác delete VM có thể liên quan đến delete options riêng cho data disk.
- Chỉ có disk tồn tại không thay thế yêu cầu snapshot/backup và kiểm thử restore.

### 12.3. Temporary/local disk

Một số VM size có ổ tạm hoặc lưu trữ cục bộ gắn với host. Nội dung loại disk này **không được bảo đảm bền vững** khi deallocate, redeploy, thay host hoặc một số thao tác hạ tầng.

Do đó:

- Không lưu database chính hoặc dữ liệu không thể tái tạo trên temporary disk.
- Không dùng thư mục tạm là vị trí duy nhất của file cần phục hồi.
- Có thể dùng temporary disk cho cache/scratch đã thiết kế để tái tạo.
- Sau start, kiểm tra ứng dụng đã tạo lại thư mục tạm, phân quyền và dữ liệu cache cần thiết.

### 12.4. Ephemeral OS disk là trường hợp khác

**Ephemeral OS disk** dùng local storage theo loại VM/kiểu triển khai được hỗ trợ, có đặc điểm vòng đời và dữ liệu khác managed OS disk. Không được áp dụng nguyên tắc “OS disk luôn được giữ khi deallocate” của managed disk cho ephemeral OS disk.

Nếu workload dùng ephemeral OS disk, phải thiết kế máy **có thể tái tạo từ image**, không phụ thuộc dữ liệu ghi thêm duy nhất trên OS disk, và đọc rõ hành vi deallocate/reimage/redeploy trong tài liệu của cấu hình đó.

## 13. Địa chỉ IP, DNS và network khi start lại

Sau deallocation, một số thành phần networking tiếp tục tồn tại như resource, nhưng thuộc tính runtime có thể thay đổi tùy loại cấu hình.

### 13.1. Private IP

Azure NIC có thể dùng **dynamic private IP allocation** hoặc cấu hình địa chỉ private tĩnh trong subnet. Khi workload cần đích có IP nhất quán, hãy đánh giá việc dùng private IP tĩnh hoặc DNS/nội bộ theo nhu cầu.

Đừng viết ứng dụng gắn chặt vào một địa chỉ động rồi giả định sẽ giữ nguyên mãi sau deallocate/start. Đồng thời, không nên cấp static private IP tùy tiện nếu tổ chức đã có hệ thống quy hoạch địa chỉ.

### 13.2. Public IP

Phải xem **Public IP resource** của VM và **allocation method/SKU**:

- Một số cấu hình dynamic IP có thể không giữ địa chỉ sau deallocate.
- Static Public IP thường giữ địa chỉ nếu tài nguyên còn tồn tại và cấu hình hỗ trợ.
- Public IP resource có thể tiếp tục phát sinh phí, kể cả VM đã deallocated.
- Với VM ở sau Load Balancer hoặc NAT Gateway, địa chỉ mà client nhìn thấy có thể thuộc dịch vụ khác, không phải NIC của VM.

Với production, ưu tiên thiết kế domain name, private endpoint, load balancer hoặc ingress thích hợp; tránh phụ thuộc vào public IP động cấp trực tiếp cho VM.

### 13.3. NSG và firewall

Deallocate không tự xóa NSG rule hoặc firewall policy. Khi VM start lại, cấu hình có thể vẫn chặn port vì một thay đổi quản trị xảy ra trong lúc VM tắt.

Các lỗi phổ biến sau start:

- NSG chỉ cho phép IP cũ.
- DNS record vẫn trỏ IP trước khi VM được cấp phát lại.
- Backend pool/health probe chưa chuyển Healthy.
- UDR/NVA/firewall chặn luồng của VM.
- Guest firewall hoặc ứng dụng không lắng nghe port.

Không sửa bằng cách mở tạm **Any/Any** trên production. Hãy kiểm tra theo luồng nguồn–đích–port và effective rules/routes.

## 14. Start VM có thể thất bại sau deallocate

Deallocate giải phóng compute allocation, vì vậy một yêu cầu Start sau đó có thể cần cấp phát lại trên hạ tầng phù hợp.

### 14.1. Các nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Start thất bại vì capacity | VM size/zone hiện thiếu năng lực cấp phát | Kiểm tra lỗi cụ thể, thời điểm khác, size/zone khác theo kế hoạch được phê duyệt |
| Start bị từ chối bởi policy | Azure Policy, deny assignment hoặc quyền chưa đủ | Kiểm tra Azure Activity Log, scope RBAC và policy |
| VM chạy nhưng ứng dụng lỗi | Service/dependency chưa ready, DNS/IP đổi | Kiểm tra guest boot, service logs, health probe, IP và DNS |
| Startup mất nhiều thời gian | OS update, extension, disk mount, warm-up | Đặt timeout hợp lý và giám sát tiến trình |
| Disk/mount không sẵn | Lỗi attachment, filesystem hoặc cấu hình guest | Xem instance view, OS log và disk configuration |
| Scheduler không start được VM | Managed identity, scope, quyền hoặc lịch sai | Kiểm tra runbook execution, authentication, timezone và quyền |
| Deallocate xong vẫn thấy chi phí | Disk, IP, backup, license/commitment hoặc độ trễ dữ liệu Cost Management | Phân tách meter và đối chiếu thời điểm |
| VM bị tự động bật lại | Automation khác, script, policy vận hành hoặc operator | Kiểm tra Activity Log và các nguồn tự động hóa |

### 14.2. Capacity và tính sẵn sàng

Nếu workload quan trọng yêu cầu phục vụ bất kỳ lúc nào, việc deallocate mỗi tối có thể không phù hợp vì:

- Không thể bảo đảm cùng một host/placement.
- Start có độ trễ và đôi lúc không thành công do thiếu capacity.
- Hệ thống phải có health check và xử lý warm-up.
- Availability SLA chỉ có ý nghĩa theo điều kiện dịch vụ khi VM/các instance được triển khai và vận hành đúng mô hình.

Nếu yêu cầu phải giữ năng lực compute hoặc khả năng khởi động cao, cân nhắc thiết kế khác, phù hợp với ngân sách như Reserved Capacity/On-demand Capacity Reservation khi được hỗ trợ — nhưng các giải pháp giữ capacity có thể **tiếp tục có phí**.

Đừng hứa rằng VM deallocated có khả năng khôi phục tức thời với RTO=0.

## 15. Lịch tự động tắt/bật VM dev/test

Mục tiêu phổ biến là tự động **deallocate ngoài giờ** và **start trước giờ làm việc**.

Ví dụ lịch cho nhóm development:

~~~text
Thứ Hai – Thứ Sáu:
    08:15  Start VM
    08:30  Kiểm tra ứng dụng sẵn sàng
    18:00  Thông báo / kiểm tra job đang chạy
    18:30  Deallocate VM

Cuối tuần:
    Giữ VM ở trạng thái Deallocated, trừ khi có yêu cầu đã duyệt
~~~

Thời điểm chỉ là ví dụ. Cần xác định timezone (ví dụ Asia/Ho_Chi_Minh) và kiểm tra cách nền tảng scheduling xử lý UTC, giờ mùa hè hoặc lịch ngày lễ nếu áp dụng.

### 15.1. Auto-shutdown của Azure Portal

Với VM và cấu hình hỗ trợ, Azure Portal có khả năng **Auto-shutdown** cho giờ xác định. Đây là công cụ hữu ích để giảm lãng phí của VM dev/test.

Cần kiểm tra:

- VM nào và subscription nào có cấu hình này.
- Giờ tắt, timezone và cảnh báo trước khi tắt nếu được hỗ trợ.
- Auto-shutdown thực tế có đưa VM về **Stopped (deallocated)** không.
- Có job chạy đêm, patch window hoặc người dùng cần truy cập ngoài giờ không.
- Ai được phép thay đổi hoặc tắt lịch này.

Auto-shutdown **không tự động giải quyết toàn bộ bài toán auto-start**. Để có cả start và deallocate theo lịch, thường cần thêm giải pháp tự động hóa phù hợp.

### 15.2. Azure Automation, Logic Apps, Functions hoặc scheduler

Một kiến trúc tự động hóa có thể gồm:

~~~mermaid
flowchart TD
    S["Scheduler theo lịch làm việc"] --> I["Managed identity / danh tính thực thi"]
    I --> Q{"Tag và scope được duyệt?"}
    Q -->|Có| A["Runbook: start hoặc deallocate"]
    Q -->|Không| E["Bỏ qua + ghi nhận lý do"]
    A --> V["Xác minh Power state"]
    V --> H["Health check / cảnh báo"]
    H --> L["Log và báo cáo chi phí"]
~~~

Nguyên tắc thiết kế:

1. Dùng **managed identity** hoặc principal được quản lý, không nhúng password/secret vào source code.
2. Chỉ cấp những quyền cần thiết ở scope đúng VM/resource group.
3. Chỉ chọn VM được chủ sở hữu **opt-in**, ví dụ qua tag đã chuẩn hóa.
4. Có danh sách loại trừ production, VM chạy đêm, backup hoặc job quan trọng.
5. Có thông báo trước khi tắt và quy trình hoãn lịch.
6. Đảm bảo retry có giới hạn, tránh thao tác trùng và xung đột giữa lịch.
7. Log thao tác, state cuối cùng, lỗi và người chịu trách nhiệm.
8. Thực hiện health check sau start; không coi power state Running là hoàn tất.
9. Kiểm tra chi phí của Automation/Logic Apps/monitoring nếu có.

### 15.3. Tránh “quét rồi tắt” mọi VM

Một scheduler tự động deallocate mọi VM trong subscription lúc 18:00 là rủi ro. Có thể làm gián đoạn:

- Production web/API VM.
- Database hoặc batch processing đang chạy.
- CI/CD runner đang thực hiện build.
- VM phục vụ dịch vụ công cộng theo múi giờ khác.
- VM backup/restore hoặc bảo trì theo lịch.
- Máy đang phục vụ phiên hỗ trợ khách hàng.

Nên dùng nguyên tắc **explicit opt-in**, chẳng hạn tag **Schedule=office-hours**, cùng tag **Owner**, **Environment**, **Timezone** và lịch được phê duyệt. Tuy nhiên, tag là metadata do người có quyền có thể sửa; scheduler vẫn phải kết hợp RBAC và policy loại trừ phù hợp.

## 16. Mẫu runbook thủ công an toàn bằng Azure CLI

Trước khi tự động hóa, hãy thử quy trình **một VM**. Ví dụ dưới đây chỉ áp dụng cho VM lab với tên/scope chính xác, không quét toàn subscription.

### 16.1. Xem state trước khi hành động

~~~bash
az login
az account set --subscription "<subscription-id>"

RG="rg-vm-lab"
VM="vm-demo-01"

az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "{name:name,powerState:powerState}" \
  --output json
~~~

### 16.2. Thực hiện deallocate ngoài giờ

Trước khi chạy, xác nhận không có batch job/backup/transaction quan trọng, ứng dụng đã được shutdown an toàn và người phụ trách đồng ý.

~~~bash
az vm deallocate \
  --resource-group "$RG" \
  --name "$VM"

az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "powerState" \
  --output tsv
~~~

Kỳ vọng **VM deallocated**. Nếu vẫn là Running/Stopping hoặc lệnh lỗi, **không đánh dấu quy trình thành công**.

### 16.3. Start trước giờ làm việc

~~~bash
az vm start \
  --resource-group "$RG" \
  --name "$VM"

az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --show-details \
  --query "powerState" \
  --output tsv
~~~

Tiếp theo xác minh ứng dụng, ví dụ nếu có web service trên VM:

~~~bash
# Chỉ là phép thử minh họa; dùng DNS/tên dịch vụ và TLS thực tế
curl --fail --show-error --max-time 10 https://app.example.internal/health
~~~

Hostname chỉ là ví dụ. Kiểm tra thêm DNS, đường mạng, certificate, firewall và các dependency. Nếu không có quyền mạng đến service, dùng kênh health check được tổ chức phê duyệt thay vì công khai endpoint mới.

### 16.4. Tiêu chí cho script production

Một script production nên có những bước **không thể bỏ qua**:

- Kiểm tra VM tồn tại, đúng subscription/resource ID và tag đã duyệt.
- Không thao tác nếu VM không thuộc nhóm scheduler quản lý.
- Kiểm tra state và tránh lệnh thừa.
- Giới hạn timeout, retry và concurrency.
- Trước deallocate, xác nhận maintenance/backup/job safety.
- Chờ state cuối cùng và ghi rõ result/exception.
- Sau start, kiểm tra health của ứng dụng.
- Phát cảnh báo nếu VM không deallocated đúng lịch hoặc không sẵn sàng sau start.

Ví dụ pseudo-code:

~~~text
for each approved VM in schedule:
    if maintenance exception or outside approved scope:
        SKIP and LOG

    if action == deallocate:
        confirm quiesce conditions
        request deallocate if appropriate
        verify PowerState/deallocated
        alert if not reached

    if action == start:
        request start if appropriate
        verify PowerState/running
        run application health check
        alert if not healthy
~~~

Pseudo-code này minh họa ý tưởng, **không phải script chạy trực tiếp**.

## 17. Kiểm soát quyền cho scheduler

Một automation được phép start/deallocate VM đang điều khiển hạ tầng production/test, vì vậy cần **least privilege**.

### 17.1. Các phạm vi cần phân biệt

| Scope | Khả năng tác động |
|---|---|
| Một VM | Chỉ VM cụ thể |
| Resource group chứa VM | Có thể tác động nhiều VM trong nhóm tùy role |
| Subscription | Có thể tác động tài nguyên trên phạm vi rộng |
| Management group | Phạm vi quản trị nhiều subscription, chỉ dùng nếu thực sự cần |

Đối với lab, có thể cấp quyền trên một resource group dành riêng. Đối với production, cân nhắc custom role chứa các action cần thiết như **Microsoft.Compute/virtualMachines/start/action**, **deallocate/action** và những quyền đọc phù hợp, thay vì cấp Owner toàn subscription.

Quyền tạo/chỉnh sửa Automation account, role assignment và quyền trên VM là những phạm vi trách nhiệm khác nhau. Nếu scheduler dùng managed identity, phải cấp đúng role assignment cho identity đó; việc tạo identity không tự cho quyền thao tác VM.

### 17.2. Audit và bảo vệ khỏi lịch ngoài ý muốn

- Giữ log của người/identity đã gửi yêu cầu Start/Stop/Deallocate.
- Dùng Azure Activity Log để xem các thao tác trên resource.
- Đặt cảnh báo khi production VM bị deallocated ngoài change window.
- Giới hạn người được sửa tag schedule, runbook và role assignment.
- Có cơ chế tạm ngưng automation khi sự cố hoặc phải chạy job ngoài giờ.
- Theo dõi drift: trạng thái thực tế khác trạng thái scheduler mong đợi.

Không dựa vào một lời nhắc trong tên VM như **-prod** hay **-test** để quyết định dừng. Dùng metadata và danh sách owner được kiểm soát.

## 18. Kiểm tra chi phí sau khi deallocate

Để xác minh kết quả FinOps, chỉ đọc power state là chưa đủ. Cần đối chiếu dữ liệu billing/usage.

### 18.1. Azure Cost Management

Trong Azure Portal:

1. Mở **Cost Management + Billing** hoặc **Cost Management** theo phạm vi có quyền.
2. Vào **Cost analysis**.
3. Chọn đúng subscription/resource group hoặc filter theo resource ID/tag, tùy dữ liệu sẵn có.
4. Chọn khoảng thời gian trước và sau khi áp dụng lịch.
5. Nhóm theo **service name**, **resource**, **meter** hoặc các dimension hiện hữu.
6. Phân biệt phí **Virtual Machines compute** với **Managed Disks**, **Backup**, **Networking** và dịch vụ khác.
7. Kiểm tra ảnh hưởng của reservation/savings plan và cách chi phí được phân bổ.
8. Ghi nhận baseline và kết quả thay đổi sau khi dữ liệu usage cập nhật.

Dữ liệu chi phí có thể có **độ trễ ingestion**. Không kết luận “deallocate không hiệu quả” chỉ vì biểu đồ vừa mới thao tác vẫn hiển thị phí của khoảng trước đó.

### 18.2. Ví dụ dashboard tối thiểu

| KPI | Cách xác định | Ý nghĩa |
|---|---|---|
| Tỷ lệ VM dev/test được deallocate ngoài giờ | Số VM đúng state / số VM có lịch | Mức tuân thủ chính sách |
| Compute hours giảm | Giờ allocated trước – sau | Hiệu quả kỹ thuật |
| Compute cost thực tế | Billing theo meter và kỳ | Tác động tài chính |
| Disk cost còn lại | Chi phí OS/data disk | Vì sao tổng bill chưa về 0 |
| Start success rate | Số lần start + health đạt / số lần thử | Chất lượng trải nghiệm |
| Thời gian từ Start đến Healthy | Theo log ứng dụng | Khả năng đáp ứng giờ làm việc |
| VM tự bật ngoài lịch | Activity Log/scheduler events | Rủi ro phát sinh thêm phí |

KPI chỉ có ý nghĩa khi có **danh sách máy thuộc phạm vi** và **thời gian quan sát** rõ ràng. Không lấy chi phí của toàn subscription làm thước đo duy nhất nếu còn nhiều dịch vụ khác đang thay đổi.

### 18.3. Nếu VM deallocated mà hóa đơn không giảm như kỳ vọng

Kiểm tra theo thứ tự:

1. VM có thật sự ở **PowerState/deallocated** trong khoảng giờ dự kiến không?
2. Scheduler có khởi động lại do nhầm timezone hay có Automation khác không?
3. Các VM khác trong resource group có vẫn chạy không?
4. Hóa đơn đang nhìn **compute usage**, **commitment** hay tổng cost?
5. Managed disks, snapshot, Public IP, Load Balancer, Bastion và log retention còn tồn tại không?
6. Có chi phí marketplace/license hoặc Reserved Instance/Savings Plan đã cam kết không?
7. Dữ liệu Cost Management đã cập nhật đủ kỳ chưa?
8. VM có bị tăng size hoặc thay đổi workload khiến giờ chạy ít hơn nhưng đơn giá cao hơn không?

Không khẳng định VM vẫn tiêu thụ compute chỉ vì tổng tiền của resource group chưa bằng 0.

## 19. Trường hợp production, HA và các VM được quản lý tự động

### 19.1. Production có SLA cao

Nếu một VM phục vụ ứng dụng 24/7, deallocate để tiết kiệm ngoài giờ thường không phù hợp. Có thể cân nhắc:

- Dùng kiến trúc có nhiều instance, health probe và khả năng chịu lỗi zone phù hợp.
- Scale out/in theo tải bằng công nghệ hỗ trợ thay vì dừng một VM đơn lẻ đột ngột.
- Right-size VM, tối ưu disk, cam kết giá phù hợp sau khi đo tải.
- Kết hợp managed services hoặc serverless cho tác vụ không cần VM cố định.
- Thiết kế maintenance window và failover.

Đừng hy sinh RTO/SLO và độ sẵn sàng production chỉ để giảm số giờ máy chạy.

### 19.2. Virtual Machine Scale Sets (VMSS)

VMSS có mô hình quản lý **số instance mong muốn**, autoscaling, health và upgrade riêng. Một thao tác power state trên từng instance có thể bị controller/autoscale thay đổi.

Với VMSS:

- Xác định muốn giảm **instance count** hay dừng một instance cụ thể.
- Kiểm tra orchestration mode, autoscale rules và health policy.
- Tính phí disk, image, networking và resource còn tồn tại.
- Không dùng script deallocate VM độc lập áp dụng mù quáng cho mọi VMSS instance.

### 19.3. Batch workload, CI/CD và VM dùng theo yêu cầu

Đối với VM chỉ chạy một pipeline hoặc job định kỳ, có thể:

- Start trước giờ chạy.
- Chờ health/agent sẵn sàng.
- Thực hiện job, xác nhận trạng thái hoàn thành và upload artifact/log cần giữ.
- Dừng dịch vụ có kiểm soát.
- Deallocate.
- Theo dõi state cuối cùng và cảnh báo khi thao tác thất bại.

Cách này giảm khả năng **tắt máy khi job chưa hoàn tất**. Nhưng lịch phải tính đến retry hoặc job kéo dài ngoài dự kiến.

### 19.4. Hibernation khác deallocate thông thường

Một số loại VM/OS hỗ trợ **hibernation**, trong đó trạng thái bộ nhớ có thể được lưu theo cơ chế dịch vụ trước khi VM không còn chạy. Đây không phải tính năng mặc định của mọi VM.

Nếu muốn tiếp tục phiên làm việc nhanh hơn so với khởi động ứng dụng từ đầu, cần kiểm tra:

- VM size, OS và loại disk được hỗ trợ.
- Yêu cầu vùng lưu memory state và khả năng disk.
- Trạng thái power thực tế và cách metering.
- Hạn chế khi thay đổi VM hoặc cấu hình.
- Quy trình resume và bảo mật dữ liệu.

Không coi hibernation và **az vm deallocate** tương đương về mặt dữ liệu trong bộ nhớ.

## 20. Các lỗi thường gặp và cách khắc phục

| Hiện tượng | Sai lầm/nguyên nhân phổ biến | Cách xử lý |
|---|---|---|
| VM đã Shut down trong Windows nhưng vẫn có compute cost | VM ở **Stopped (allocated)** | Deallocate bằng Azure, xác minh PowerState/deallocated |
| az vm stop hoàn tất nhưng compute vẫn tính phí | Lệnh stop không giải phóng allocation | Dùng az vm deallocate nếu phù hợp |
| Portal ghi Stopped nhưng khó xác định chi phí | Nhầm nhãn với trạng thái chi tiết | Đọc power state bằng instance view/CLI |
| az vm deallocate trả lệnh sớm nhưng VM chưa deallocated | Dùng --no-wait hoặc trạng thái trung gian | Chờ/poll đến state cuối và kiểm tra lỗi |
| VM không Start lại | Capacity, quota, quyền, policy hoặc lỗi deployment | Xem thông báo lỗi, Activity Log và các giới hạn VM size/zone |
| VM Start nhưng truy cập RDP/SSH thất bại | IP/DNS thay đổi, NSG, firewall, boot chưa xong | Kiểm tra NIC/Public IP, effective rules, boot diagnostics |
| VM Running nhưng web/API chưa Healthy | Service chưa lên, dependency chưa sẵn | Kiểm tra guest logs và health probe |
| Dữ liệu cache mất sau deallocate | Dùng temporary disk hoặc ephemeral OS disk | Chuyển dữ liệu cần giữ sang persistent storage, phục hồi cache |
| Disk cost vẫn còn | Managed disk/snapshot không bị xóa | Đánh giá storage costs và vòng đời dữ liệu |
| Public IP cost vẫn còn | IP resource tiếp tục tồn tại | Xem SKU, nhu cầu giữ IP và chính sách xóa an toàn |
| VM ngoài giờ lại tự bật | Automation khác, người vận hành hoặc lịch sai | Activity Log, runbook logs, timezone và RBAC |
| Scheduler tắt nhầm production | Scope/tag/owner hoặc exclusion policy sai | Dừng automation, phục hồi và thêm opt-in/guardrails |
| Savings Plan không làm tổng bill giảm ngay | Cam kết vẫn tồn tại | Phân tích commitment utilization và chi phí phân bổ |
| Backup/monitoring lỗi sau deallocation | Dịch vụ phụ thuộc guest agent/VM online | Kiểm tra hỗ trợ, lịch backup và cảnh báo riêng |
| VM start lại chậm | Extension, boot, capacity hoặc warm-up | Đo time-to-healthy, tối ưu khởi động và lịch Start sớm hơn |

### 20.1. Trường hợp lệnh trả lỗi

Không tự lặp Start/Stop/Deallocate với tần suất cao. Một quy trình an toàn:

1. Đọc lỗi đầy đủ từ CLI/Portal.
2. Kiểm tra thao tác quản lý có còn chạy không.
3. Đọc instance view và provisioning state.
4. Xem Activity Log quanh thời điểm lỗi.
5. Xác minh quyền/scope Azure RBAC và policy.
6. Kiểm tra quota/capacity/region nếu có mã lỗi allocation.
7. Chọn biện pháp được phép theo runbook, tránh xóa disk hoặc VM để sửa lỗi không rõ nguyên nhân.
8. Sau khi khắc phục, xác minh trạng thái cuối cùng, health và chi phí.

## 21. Bảo vệ dữ liệu và quy trình shutdown an toàn

Một thao tác Deallocate ảnh hưởng cả workload, không chỉ hóa đơn. Với VM chạy database hoặc hệ thống có giao dịch:

### 21.1. Checklist trước khi tắt

- [ ] Đã thông báo người dùng hoặc đặt maintenance window.
- [ ] Đã ngừng tiếp nhận yêu cầu ghi mới nếu ứng dụng cần.
- [ ] Đã hoàn tất hoặc xử lý các job/transaction dở dang.
- [ ] Đã flush dữ liệu và checkpoint/backup theo quy trình ứng dụng.
- [ ] Đã xác nhận không có restore, patch hoặc deployment đang chạy.
- [ ] Đã xác nhận dữ liệu cần giữ không nằm duy nhất trên temporary disk.
- [ ] Đã ghi lại VM ID, power state, IP và người thực hiện.
- [ ] Đã chuẩn bị cách khôi phục nếu start lại thất bại.

### 21.2. Checklist sau khi Start

- [ ] Power state đã là Running và provisioning không báo lỗi nghiêm trọng.
- [ ] OS/data disks, drive letters và mounts đúng.
- [ ] DNS/IP và kết nối mạng hợp lệ.
- [ ] Identity, secret và authentication vẫn hoạt động.
- [ ] Database/queue/file service có thể nhận traffic.
- [ ] Health check nghiệp vụ thành công.
- [ ] Log/alert không báo lỗi liên tục.
- [ ] Lịch backup, monitoring và automation trở lại bình thường.

**Nhấn mạnh:** disk persistence không đồng nghĩa consistency của ứng dụng; cần thực hiện quy trình bảo vệ dữ liệu ở lớp workload.

## 22. Checklist tối ưu chi phí VM toàn nhóm

- [ ] Đã phân loại VM production, dev, test, sandbox và workload chạy theo lịch.
- [ ] Có owner, SLA, khung giờ hoạt động và phụ thuộc hệ thống rõ ràng.
- [ ] Người vận hành phân biệt Stopped (allocated) với Stopped (deallocated).
- [ ] Đã kiểm tra Stop từ Portal, CLI, PowerShell và guest OS không cùng nghĩa.
- [ ] VM cần tiết kiệm được **deallocate**, không chỉ shutdown guest.
- [ ] Script đợi state cuối và ghi lỗi, không chỉ kiểm tra exit code của yêu cầu bất đồng bộ.
- [ ] Disk, Public IP, backup, logging, license và commitments được tính riêng.
- [ ] Dynamic IP và temporary/ephemeral disk được đánh giá trước khi deallocate.
- [ ] Có health check và kế hoạch xử lý thiếu capacity sau Start.
- [ ] Scheduler chỉ điều khiển VM đã opt-in, có quyền tối thiểu và loại trừ production.
- [ ] Múi giờ, ngày nghỉ, tác vụ batch và lịch bảo trì được xét đến.
- [ ] Có baseline compute hours và báo cáo Cost Management trước/sau.
- [ ] Dữ liệu quan trọng có backup, restore test và shutdown runbook.
- [ ] Các thao tác bất thường được giám sát qua Activity Log.
- [ ] Đã đánh giá right-sizing và các mô hình sử dụng compute khác khi VM cần chạy liên tục.

## 23. Bài tập thực hành

### Bài 1: Giải thích sự khác biệt

Một Linux VM bị tắt bằng:

~~~bash
sudo shutdown -h now
~~~

VM không trả lời SSH nữa. Hãy trả lời:

1. Trạng thái power state nào có khả năng xuất hiện?
2. Compute usage billing có chắc đã dừng không?
3. Lệnh Azure CLI nào cần dùng để deallocate?
4. Hai lệnh nào có thể dùng để kiểm tra trạng thái cuối?
5. Những chi phí nào tiếp tục phát sinh sau deallocate?

### Bài 2: Thực hành ba trạng thái

Trong resource group lab có một VM với **managed OS disk** và không lưu dữ liệu quan trọng trên temporary disk:

1. Xem state bằng **az vm show --show-details**.
2. Start và chờ Running.
3. Thực hiện **az vm stop** và đọc trạng thái.
4. Thực hiện **az vm deallocate** và đọc trạng thái.
5. Start lại và kiểm tra dữ liệu trên managed OS disk.
6. Giải thích vì sao không dùng dữ liệu temporary disk làm bằng chứng persistence.

Không thử với VM production hoặc máy có job đang chạy.

### Bài 3: Tính giờ compute có thể tránh

Một VM dùng trong 10 giờ/ngày, 20 ngày/tháng. Giả sử tháng có 30 ngày:

- Có bao nhiêu giờ được cấp compute nếu VM chạy liên tục?
- Có bao nhiêu giờ compute usage khi chỉ start trong giờ sử dụng và deallocate ngoài giờ?
- Nếu compute rate quy ước là 0,30 USD/giờ, chênh lệch là bao nhiêu?
- Vì sao kết quả không bằng tổng tiền tiết kiệm thực tế nếu có Managed Disks và Savings Plan?

### Bài 4: Thiết kế lịch tự động hóa

Nhóm QA có 6 VM thử nghiệm. Hãy thiết kế:

- Tag để opt-in schedule và ghi owner/timezone.
- Lịch Start trước giờ làm việc và Deallocate ngoài giờ.
- Nguyên tắc tránh dừng VM đang chạy kiểm thử.
- RBAC tối thiểu cho managed identity.
- Bước xác minh PowerState và health.
- Alert nếu VM không deallocated đúng lịch hoặc không Start được.

### Bài 5: Chẩn đoán hóa đơn

Sau khi lên lịch Stop lúc 18:00, Cost Management vẫn cho thấy tổng phí của resource group còn đáng kể. Hãy lập bảng phân tích các meter: VM compute, OS/data disk, Public IP, backup, log và commitment. Đề xuất cách chứng minh VM đã deallocated đúng giờ.

### Bài 6: Đánh giá rủi ro Start thất bại

Một ứng dụng nội bộ cần sẵn sàng trước 08:30. VM được deallocate cuối ngày, nhưng sáng hôm sau Azure báo thiếu capacity cho VM size/zone. Nêu cách ứng phó hiện tại và thiết kế lâu dài để cân bằng chi phí với SLO mà không hứa hẹn deallocate luôn có thể start tức thời.

### Câu hỏi tự kiểm tra

1. Một VM provisioning state Succeeded có thể power state Deallocated không?
2. Stop từ guest OS có làm ngừng chi phí compute VM thông thường không?
3. Azure CLI **az vm stop** khác **az vm deallocate** thế nào?
4. Stop từ Azure Portal và Stop-AzVM mặc định thường tạo trạng thái gì?
5. Managed disks có bị xóa khi VM deallocated không?
6. Vì sao cần tránh lưu dữ liệu quan trọng trên temporary disk?
7. Tại sao static Public IP vẫn có thể tính phí khi VM deallocated?
8. Vì sao không nên dùng Running làm điều kiện duy nhất xác nhận ứng dụng sẵn sàng?
9. VM đã được deallocated có thể Start thất bại vì lý do nào?
10. Vì sao reservation/savings plan làm bài toán tiết kiệm chi phí phức tạp hơn?
11. Khi nào nên dùng automation có lịch thay vì thao tác Stop thủ công?
12. Delete VM có giống deallocate về dữ liệu và chi phí không?

## 24. Tài liệu tham khảo

- [Azure Virtual Machines — States and billing](https://learn.microsoft.com/azure/virtual-machines/states-billing)
- [Azure CLI: az vm command reference](https://learn.microsoft.com/cli/azure/vm)
- [Azure PowerShell: Start-AzVM](https://learn.microsoft.com/powershell/module/az.compute/start-azvm)
- [Azure PowerShell: Stop-AzVM](https://learn.microsoft.com/powershell/module/az.compute/stop-azvm)
- [Azure VM ephemeral OS disks](https://learn.microsoft.com/azure/virtual-machines/ephemeral-os-disks)
- [Azure Managed Disks overview](https://learn.microsoft.com/azure/virtual-machines/managed-disks-overview)
- [Azure Cost Management overview](https://learn.microsoft.com/azure/cost-management-billing/costs/overview-cost-management)
- [Azure Reservations overview](https://learn.microsoft.com/azure/cost-management-billing/reservations/save-compute-costs-reservations)
- [Azure Virtual Machines pricing](https://azure.microsoft.com/pricing/details/virtual-machines/)

