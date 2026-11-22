# Thiết kế Virtual Machine Scale Sets

## 1. Đặt vấn đề: vì sao cần VMSS?

Một ứng dụng trên Microsoft Azure có thể chạy trên một máy ảo (Virtual Machine, VM), chẳng hạn API Java phục vụ người dùng hoặc worker xử lý tệp trong hàng đợi. Cách triển khai một VM dễ bắt đầu, nhưng phát sinh vấn đề khi lưu lượng tăng, máy bị lỗi hoặc ứng dụng cần nâng cấp mà không được gián đoạn.

Giả sử API đang chạy trên một VM. Khi có chiến dịch bán hàng, số request tăng gấp ba. Quản trị viên có thể tạo thêm hai VM, cài Java, sao chép code, cấu hình mạng rồi đăng ký vào load balancer. Nhưng khi tải giảm, ai sẽ kiểm tra VM nào có thể xóa? Nếu cần vá lỗi hệ điều hành, ai sẽ đảm bảo tất cả VM đang dùng cùng phiên bản? Khi một VM bị hỏng, ai sẽ thay thế?

**Azure Virtual Machine Scale Sets (VMSS)** giúp điều phối một tập hợp VM để mở rộng/thu hẹp năng lực tính toán theo cấu hình và chính sách đã chọn. Nhóm VM có thể phục vụ lưu lượng HTTP, xử lý các message độc lập hoặc thực hiện những tác vụ theo lô.

Trong chương **Compute co giãn và xử lý theo lô**, VMSS kết nối các kiến thức về subscription, resource group, Azure networking, image, Azure Monitor, bảo mật và kiểm soát chi phí thành một kiến trúc có thể vận hành thực tế.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích VMSS khác việc tạo nhiều VM thủ công ở điểm nào.
2. Phân biệt hai orchestration mode **Uniform** và **Flexible**.
3. Thiết kế số lượng instance, VM SKU, Availability Zones, mạng và load balancing.
4. Lựa chọn image, cấu hình startup và nguồn lưu state của ứng dụng.
5. Thiết kế autoscale theo metric hoặc lịch, giới hạn capacity và cooldown.
6. Tổ chức health probes, upgrade, rollback, scale-in và xử lý instance lỗi.
7. Bảo vệ VMSS bằng identity, Azure RBAC, NSG, secret management và giám sát.
8. Tạo một VMSS thử nghiệm, kiểm tra scale-out/scale-in và đánh giá chi phí.

## 2. Khái niệm cốt lõi của Virtual Machine Scale Sets

VMSS là tài nguyên Azure chứa thông tin điều phối các **VM instances**. Tùy mô hình, mỗi instance được tạo theo VM profile chung hoặc được quản lý linh hoạt hơn. Bạn quản lý **desired capacity** thay vì xem mỗi lần thêm hoặc bớt một VM là một dự án hạ tầng riêng biệt.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| VMSS | Tài nguyên quản lý nhóm máy ảo | vmss-api-prod |
| Instance | Một VM thành viên của nhóm | Instance phục vụ API tại zone 1 |
| Capacity | Số VM mục tiêu | 3 |
| VM size / SKU | CPU, RAM, network và giới hạn I/O | Một SKU có 2 vCPU và RAM phù hợp |
| VM image | Hệ điều hành và nền tảng cấu hình ban đầu | Linux image có Java runtime |
| Orchestration mode | Cách điều phối instance | Uniform hoặc Flexible |
| Autoscale | Cơ chế thay đổi capacity | CPU cao thì tăng số VM |
| Upgrade policy | Cách triển khai thay đổi model/image | Nâng cấp theo đợt khi hỗ trợ |
| Health signal | Thông tin VM/ứng dụng đã sẵn sàng chưa | HTTP /health/ready |
| Availability Zones | Phân tán máy giữa các vùng lỗi trong region | Zone 1, 2 và 3 |

Một VM đã **Running** chưa chắc ứng dụng Java trên đó đã phục vụ request. Một VMSS có capacity bằng 4 cũng chưa chắc có 4 backend **healthy**. Vì thế, khi vận hành phải phân biệt **mục tiêu điều phối, trạng thái cấp phát VM và năng lực phục vụ thực tế**.

VMSS không tự sao lưu database, đồng bộ session hoặc bảo đảm ứng dụng chịu được việc bị xóa VM. Các yêu cầu này phải được thiết kế ở tầng ứng dụng và dữ liệu.

## 3. Kiến trúc mẫu của một ứng dụng chạy VMSS

~~~mermaid
flowchart TD
    USER[Khách hàng hoặc ứng dụng gọi API] --> GATEWAY[Load Balancer hoặc Application Gateway]
    subgraph VNET[Azure Virtual Network]
        GATEWAY --> I1[VMSS Instance 1]
        GATEWAY --> I2[VMSS Instance 2]
        GATEWAY --> I3[VMSS Instance N]
        I1 --> DB[(Database dùng chung)]
        I2 --> DB
        I3 --> DB
        I1 --> STORAGE[(Blob Storage / Queue)]
        I2 --> STORAGE
        I3 --> STORAGE
    end
    MON[Azure Monitor Autoscale] --> SCALE[VM Scale Set]
    SCALE --> I1
    SCALE --> I2
    SCALE --> I3
~~~

Ví dụ, đội phát triển triển khai API Java vào VMSS với capacity khởi điểm là 2:

- Các instance sử dụng cùng phiên bản ứng dụng và cung cấp HTTP endpoint.
- Azure Load Balancer hoặc Application Gateway phân phối request đến backend khỏe.
- Database và các tệp quan trọng không nằm duy nhất trên OS disk của một instance.
- Azure Monitor theo dõi các chỉ số để tăng capacity khi tải kéo dài.
- Khi một instance lỗi, ứng dụng vẫn có khả năng phục vụ bằng những instance khác, nếu thiết kế đã có dự phòng.
- Khi scale-in, máy bị loại bỏ không làm mất giao dịch hoặc dữ liệu bền vững.

Sơ đồ trên là mô hình logic. Không bắt buộc phải dùng nhiều tầng ingress. Với L4, thường cân nhắc **Azure Standard Load Balancer**; với route HTTP/HTTPS và WAF, cân nhắc **Application Gateway**; với điều phối ứng dụng toàn cầu, cân nhắc **Azure Front Door**.

## 4. Orchestration mode: Uniform và Flexible

Đây là quyết định kỹ thuật quan trọng, vì hành vi instance, upgrade và cách dùng công cụ quản lý có thể khác nhau.

### 4.1. Uniform orchestration

**Uniform** được thiết kế quanh mô hình quản lý một tập hợp VM có cấu hình chung. Nó thường phù hợp khi toàn bộ instance cần sử dụng cùng VM model, image và quy trình vận hành.

Điểm mạnh:

- Mô hình triển khai tương đối đồng nhất.
- Thuận tiện khi ứng dụng stateless được đóng gói thành cùng một image.
- Hỗ trợ các khả năng VMSS về lifecycle, monitoring, scaling và upgrade theo tính năng của chế độ.

Những điểm cần kiểm tra:

- Thay đổi model chưa nhất thiết tác động tức thời đến từng instance.
- Quy trình cập nhật model/instance khác các VM đơn lẻ.
- Một số khả năng network, placement và quản lý từng máy được giới hạn theo orchestration mode.

### 4.2. Flexible orchestration

**Flexible** hướng tới việc quản lý VM thành viên linh hoạt hơn và cho phép trải nghiệm thao tác gần với các Azure VM thông thường.

Điểm mạnh:

- Có thể thuận lợi khi cần quản lý hoặc quan sát VM thành viên riêng lẻ.
- Hỗ trợ các thiết kế phân bố Availability Zones hoặc phối hợp VM size trong những điều kiện được Azure hỗ trợ.
- Phù hợp với những kịch bản muốn kết hợp capacity management với vòng đời VM tương đối độc lập.

Những điểm cần kiểm tra:

- Không phải mọi lệnh, API, extension, upgrade policy hay automatic repair của Uniform đều áp dụng giống Flexible.
- Một số thao tác có thể dùng tài nguyên Azure VM thành viên thay vì cú pháp quản lý instance của Uniform.
- Cần xác nhận hỗ trợ cho từng VM SKU, region, mode và phiên bản công cụ.

### 4.3. Bảng lựa chọn

| Nhu cầu | Uniform | Flexible |
|---|---|---|
| Nhiều instance có cấu hình gần như giống nhau | Thường phù hợp | Cũng có thể phù hợp |
| Cần quản lý instance gần với VM độc lập | Khả năng theo mô hình Uniform | Thường thuận tiện hơn |
| Tính linh hoạt về kích thước/đặt máy theo hỗ trợ | Không phải mục tiêu chính | Có thể phù hợp hơn |
| Autoscale | Tích hợp theo khả năng của mode | Tích hợp theo khả năng của mode |
| Rolling upgrade | Theo chính sách/tính năng hỗ trợ | Cần kiểm tra luồng hỗ trợ riêng |
| Phân tán zone/fault domain | Cần cấu hình rõ | Cần cấu hình rõ |

**Không có lựa chọn mặc định đúng cho mọi sản phẩm.** Chọn mode dựa trên hành vi và tính năng thực sự cần, không chỉ dựa trên tên. Với bài thực hành nhóm web server đồng nhất, Uniform là một mô hình dễ minh họa nếu môi trường hỗ trợ.

## 5. Thiết kế desired capacity và dự phòng

Để VMSS thực sự co giãn, phải trả lời ba câu hỏi:

1. Cần **bao nhiêu VM tối thiểu** để dịch vụ hoạt động an toàn?
2. Trong giờ cao điểm có thể cần **bao nhiêu VM tối đa**?
3. Khi tăng hoặc giảm, **bao lâu instance thực sự nhận được lưu lượng**?

Ví dụ:

| Tham số | Giá trị minh họa | Lý do |
|---|---:|---|
| Minimum | 2 | Giữ hai bản ứng dụng khi tải thấp |
| Default | 2 | Mức khởi đầu |
| Maximum | 8 | Giới hạn quy mô autoscale |
| Increment | 1 VM | Thay đổi từng bước dễ quan sát |
| Tải cơ sở | 150 requests/giây | Số liệu giả định để thử thiết kế |
| Tải đỉnh | 600 requests/giây | Kịch bản cần scale-out |

Giả sử load test cho thấy một VM xử lý **100 requests/giây** ở mức độ trễ đáp ứng SLO. Tải 600 requests/giây có thể cần ít nhất 6 VM trong điều kiện lý tưởng, cộng mức dự phòng phù hợp. Tuy nhiên, không nên ước tính năng lực bằng phép chia đơn giản rồi bỏ qua database, request dài, session, hiệu ứng warm-up hoặc độ lệch tải.

### 5.1. Không nhầm desired với available

Azure có thể đang tạo VM mới nhưng chưa cài ứng dụng xong. Trong thời gian đó, dashboard cho thấy capacity mục tiêu cao hơn trước nhưng API vẫn chịu tải trên các instance cũ.

**Time-to-ready** là chỉ số cần đo: từ lúc autoscale quyết định tăng capacity đến khi instance mới nhận được request thật và phản hồi thành công.

### 5.2. Minimum không đồng nghĩa HA

Hai VM giúp giảm rủi ro một máy lỗi, nhưng vẫn có thể cùng nằm trong vùng lỗi, cùng phụ thuộc một database không dự phòng hoặc cùng bị hỏng vì image sai. Để có HA cần thiết kế theo lớp và diễn tập sự cố.

## 6. Availability Zones và fault domains

### 6.1. Availability Zones

Một số Azure region hỗ trợ **Availability Zones**, các khu vực hạ tầng có khả năng độc lập về nhiều thành phần như nguồn điện, hệ thống làm mát và mạng. VMSS có thể phân phối instance sang nhiều zone theo mode, VM SKU, cấu hình và khả năng vùng.

Ví dụ thiết kế:

~~~text
Region hỗ trợ nhiều Availability Zones

Zone 1: các instance API
Zone 2: các instance API
Zone 3: các instance API nếu cấu hình cho phép

Load balancing điều phối đến những instance khỏe.
~~~

Đừng chỉ đặt capacity=3 rồi mặc định sẽ có đúng một VM ở mỗi zone. Cần cấu hình và **kiểm tra placement thực tế**.

### 6.2. Fault domains

Fault domain mô tả cách chia các tập tài nguyên để giảm rủi ro từ lỗi phần cứng/hạ tầng chung. Cách phân bố fault domain có thể khác nhau giữa Uniform và Flexible. Hãy xác nhận thông tin từ deployment thực thay vì giả định VMSS tự đáp ứng yêu cầu fault tolerance.

### 6.3. Độ sẵn sàng của downstream service

Nếu tất cả instance ở ba zone cùng gọi một database chỉ phục vụ từ một zone, lỗi database vẫn có thể làm API ngừng hoạt động. Rà soát cả:

- Database redundancy và backup.
- Blob/Queue availability phù hợp.
- DNS và load balancer.
- Identity, Key Vault và network.
- Capacity ở những zone còn lại.

**Multi-zone không thay thế multi-region disaster recovery.** Khi có yêu cầu RPO/RTO cho sự cố toàn region, phải thiết kế riêng dữ liệu, ứng dụng và định tuyến toàn cầu.

## 7. Lựa chọn VM size và loại workload

### 7.1. API/web tier

VMSS thường phù hợp khi các API instance có thể xử lý request độc lập, ứng dụng có health endpoint và trạng thái được lưu ngoài VM.

### 7.2. Background workers

Nhiều instance đọc message từ Queue Storage hoặc Azure Service Bus. Thêm VM giúp tăng số tác vụ xử lý đồng thời, nhưng cần kiểm soát consumer concurrency, retry và tính idempotent của job.

### 7.3. Batch processing

Mỗi instance thực hiện một phần của workload xử lý dữ liệu. Tác vụ có thể chạy lại hoặc checkpoint thuận lợi hơn khi scale-in, bị thay máy hoặc xử lý lỗi.

### 7.4. Workload không phù hợp để scale trực tiếp

Một ứng dụng lưu database độc quyền trên OS disk, sử dụng local session không thể chia sẻ hoặc cần một primary node duy nhất có thể không phù hợp để tăng số lượng VM giống hệt nhau. Trước khi tạo VMSS, cần giải quyết kiến trúc stateful hoặc chọn nền tảng xử lý khác.

### 7.5. Chọn SKU

Cân nhắc đồng thời:

- vCPU/RAM so với load profile.
- IOPS, disk throughput và network bandwidth.
- Khả năng sẵn có ở region và Availability Zones.
- VCPU quota của subscription/VM family.
- OS disk, data disk, ephemeral OS disk và NVMe/temp disk.
- Chi phí tính toán và các mô hình mua tài nguyên phù hợp.

Một VM SKU có disk IOPS cao không bảo đảm database nhanh hơn nếu nút cổ chai là connection pool, code hoặc network.

## 8. Chọn OS disk, data disk và lưu trữ state

VMSS instances có vòng đời thay đổi thường xuyên. Điều này ảnh hưởng đến lựa chọn nơi ghi dữ liệu.

| Loại dữ liệu | Nên lưu ở đâu? | Lý do |
|---|---|---|
| Hệ điều hành và runtime | OS disk hoặc ephemeral OS disk nếu phù hợp | Tạo VM từ image |
| File cấu hình không chứa secret | Image, cấu hình versioned hoặc nơi quản lý tập trung | Tái tạo nhất quán |
| Session người dùng | Cache/database bên ngoài VM theo thiết kế | Không gắn vào một instance |
| File upload | Blob Storage hoặc dịch vụ bền vững phù hợp | Không mất khi scale-in |
| Database production | Dịch vụ dữ liệu bền vững hoặc hệ thống cluster chuyên biệt | Không lệ thuộc OS disk |
| Job checkpoint | Blob/Queue/database theo ứng dụng | Cho phép chạy lại |
| Cache có thể tái tạo | Temporary/local disk nếu VM hỗ trợ | Không cần giữ bền vững |
| Log quan trọng | Azure Monitor/Log Analytics hoặc đích tập trung | Giữ lại khi VM bị xóa |

**Ephemeral OS disk** có thể hữu ích cho workload stateless và tốc độ tạo lại instance, nhưng không phù hợp nếu thay đổi trên OS disk cần được giữ qua các sự kiện reimage/replace/deallocate theo các ràng buộc của dịch vụ. Tương tự, temporary disk không được xem là nơi lưu dữ liệu quan trọng.

Cần chọn VM size, image và tính năng theo hỗ trợ thực tế trước khi bật ephemeral OS disk.

## 9. Image và cấu hình startup

Để scale-out đáng tin cậy, bạn cần cách tạo instance nhất quán và nhanh.

### 9.1. Các nguồn image

- **Marketplace image:** Linux/Windows sẵn có, sau đó cài ứng dụng.
- **Custom image:** đã chuẩn bị runtime, package và cấu hình.
- **Azure Compute Gallery:** quản lý image definitions/versions, tái sử dụng và phân phối phù hợp với hệ thống có nhiều môi trường.

### 9.2. Image có phiên bản rõ ràng

Một pipeline triển khai tốt:

1. Build artifact ứng dụng Java.
2. Tạo image/package theo phiên bản đã kiểm thử.
3. Chạy kiểm tra bảo mật và tích hợp.
4. Cập nhật VMSS model/nguồn triển khai.
5. Áp dụng upgrade bằng quy trình phù hợp.
6. Kiểm chứng application health.
7. Có phương án rollback về phiên bản trước.

Đừng SSH vào một instance để sửa file rồi coi đó là cấu hình chuẩn. Instance mới khi scale-out hoặc reimage có thể không nhận thay đổi thủ công.

### 9.3. cloud-init và extensions

Với Linux, cloud-init có thể cài package hoặc chạy lệnh khi boot.

Ví dụ cho môi trường thực hành, không phải cấu hình production đầy đủ:

~~~yaml
#cloud-config
package_update: true
packages:
  - nginx
runcmd:
  - systemctl enable nginx
  - systemctl start nginx
~~~

Có thể dùng VM extensions để cấu hình hoặc cài agent theo tính năng được hỗ trợ. Cần cân nhắc thời gian startup, quyền thực thi, log lỗi extension và sự tương thích với orchestration mode.

**Không nhúng password, key hoặc connection string production** trong image, cloud-init hay repository. Dùng managed identity, Key Vault và cơ chế cấp cấu hình an toàn.

## 10. Thiết kế VNet, subnet và load balancing

### 10.1. VNet và subnet

VMSS thường được triển khai vào một subnet trong Azure Virtual Network. Địa chỉ IP của subnet phải đủ cho số instance tối đa, NIC, các tài nguyên khác và phần dự phòng.

Ví dụ:

~~~text
VNet: 10.30.0.0/16
Subnet ứng dụng: 10.30.10.0/24
VMSS: min 2, max 8
~~~

Tùy môi trường, cần tính IP Azure giữ lại và số IP còn có thể cấp phát trong subnet. Một subnet quá nhỏ có thể làm scale-out thất bại dù VM quota vẫn đủ.

### 10.2. Chọn ingress

| Thành phần | Công dụng | Ví dụ |
|---|---|---|
| Azure Standard Load Balancer | L4 TCP/UDP | API trên VMSS với frontend TCP |
| Application Gateway | L7 HTTP/HTTPS, route theo host/path, WAF nếu cấu hình | Web/app có TLS và routing phức tạp |
| Azure Front Door | Dịch vụ phân phối ứng dụng toàn cầu tại edge | Multi-region HTTP/HTTPS |

Không cần ghép cả ba để có VMSS hoạt động. Lựa chọn dựa trên TLS, WAF, quy mô và kiểu lưu lượng.

### 10.3. Backend pool và health probe

Để cân bằng tải hoạt động:

1. Tạo frontend (public hoặc internal).
2. Tạo backend pool cho những VMSS instances.
3. Cấu hình health probe hợp lệ.
4. Tạo rule forward traffic đến cổng ứng dụng.
5. Cấu hình NSG và firewall.
6. Xác minh backend được coi healthy trước khi gửi traffic.

Một VM chưa khởi động ứng dụng không nên nhận request chỉ vì quá trình cấp VM báo thành công.

### 10.4. Outbound traffic

VMSS instances có thể cần tải package, lấy secret, kết nối database hoặc gửi telemetry. Nên thiết kế đường outbound rõ ràng, ví dụ NAT Gateway hoặc firewall tùy yêu cầu. Tránh phụ thuộc implicit/default outbound access vì hành vi khác nhau theo loại mạng và chính sách nền tảng.

Không cần public IP riêng cho từng instance chỉ để cập nhật package. Nếu không có lý do đặc biệt, quản trị VM qua Azure Bastion hoặc đường truy cập private được kiểm soát.

## 11. Kiểm tra sức khỏe: readiness và liveness

Một VM có thể chạy tốt nhưng ứng dụng Java chưa khởi động, bị deadlock hoặc không kết nối được dependency. Vì thế cần phân biệt:

| Tín hiệu | Ý nghĩa |
|---|---|
| Provisioning state | Azure đã cấp VM thành công chưa? |
| Liveness | Process/application còn hoạt động không? |
| Readiness | Có đủ điều kiện nhận request mới không? |
| Load balancer health | Backend có đạt tiêu chí để nhận kết nối không? |
| Application health for VMSS | Tín hiệu ứng dụng phục vụ một số quy trình repair/upgrade theo hỗ trợ |

Một ứng dụng có thể triển khai:

~~~text
GET /health/live  -> 200 khi process còn hoạt động
GET /health/ready -> 200 khi ứng dụng sẵn sàng nhận traffic
~~~

Trong giai đoạn boot, readiness nên báo chưa sẵn sàng cho đến khi startup và các dependency thiết yếu hoàn tất.

**Không làm health endpoint luôn trả HTTP 200 cho có.** Nếu API mất khả năng xử lý nghiệp vụ chính, tín hiệu health phải giúp hệ thống phát hiện. Tuy vậy, cũng không nên coi một dependency phụ không quan trọng bị chậm là lý do làm tất cả instance unhealthy đồng loạt.

### 11.1. Application Health Extension và repair

VMSS có thể dùng Application Health Extension hoặc những cơ chế health tương ứng trong cấu hình hỗ trợ để giúp rolling upgrades và automatic repairs. Những hành vi restart/reimage/replace, grace period và điều kiện cần phụ thuộc mode/OS/SKU.

Đối với workload stateless, thay thế instance không khỏe thường phù hợp. Với workload có dữ liệu duy nhất nằm trên máy, repair có thể làm mất dữ liệu hoặc tăng lỗi.

## 12. Autoscale của VMSS

**Azure Monitor autoscale** có thể điều chỉnh capacity khi các điều kiện metric hoặc lịch thỏa mãn, tùy kiểu VMSS và tính năng được hỗ trợ.

~~~mermaid
flowchart LR
    METRIC[CPU / queue metric / schedule] --> RULE[Autoscale rules]
    RULE --> DECIDE{Tăng hay giảm?}
    DECIDE -->|Scale-out| MORE[Tạo thêm instance]
    DECIDE -->|Scale-in| LESS[Giảm instance]
    MORE --> READY[Boot, khởi tạo và healthy]
    LESS --> DRAIN[Ngừng nhận việc, kết thúc VM]
    READY --> BACKEND[Backend pool]
    DRAIN --> BACKEND
~~~

### 12.1. Capacity bounds

- **Minimum:** số instance thấp nhất mục tiêu autoscale được đặt cho môi trường.
- **Maximum:** giới hạn capacity tự động.
- **Default:** capacity mặc định trong cơ chế profile khi các điều kiện tương ứng không áp dụng.

Số instance thực tế có thể khác desired capacity trong lúc nâng cấp hoặc thất bại do quota, disk, image, NIC hay zone.

### 12.2. Metric-based autoscale

Ví dụ về chính sách:

- CPU trung bình vượt **70% trong 10 phút** → tăng 1 VM.
- CPU trung bình dưới **30% trong 20 phút** → giảm 1 VM.
- Chờ **cooldown** giữa các hành động để hệ thống có thời gian ổn định.

Đây chỉ là các ngưỡng minh họa. Khi ứng dụng tắc nghẽn ở database, CPU có thể thấp dù request timeout tăng. Có thể dùng custom metrics hoặc những metric khác có ý nghĩa hơn nếu công cụ hỗ trợ.

### 12.3. Scheduled autoscale

Khi biết trước giờ cao điểm hoặc ca chạy batch, có thể dùng lịch để đặt mục tiêu capacity hoặc thay đổi profile theo thời gian. Hãy kiểm tra timezone, ngày nghỉ, mức sử dụng thực tế và hành vi khi một quy tắc lịch kết thúc.

### 12.4. Manual capacity

Có thể tăng/giảm thủ công bằng Portal hoặc CLI khi được phép. Nếu autoscale đang hoạt động, giá trị thủ công có thể bị điều chỉnh trở lại theo quy tắc; đừng coi thao tác manual là cấu hình cố định lâu dài.

## 13. Thiết kế quy tắc autoscale tránh dao động

Một rule kém có thể tạo vòng lặp: CPU tăng → thêm VM → CPU giảm → xóa VM → CPU lại tăng. Việc tạo/xóa VM liên tục vừa tốn chi phí vừa ảnh hưởng phiên và cache.

Ví dụ cấu hình mục tiêu:

| Thuộc tính | Giá trị học tập |
|---|---|
| Min / Default / Max | 2 / 2 / 8 |
| Scale-out | CPU avg > 70% trong 10 phút |
| Scale-out action | +1 VM |
| Scale-in | CPU avg < 30% trong 20 phút |
| Scale-in action | -1 VM |
| Cooldown | 10 phút |
| Số instance không được xóa tự động | Xác định nếu có workload đặc biệt |

Để rule ổn định hơn:

1. Tách ngưỡng tăng và giảm đủ xa.
2. Dùng thời gian quan sát có ý nghĩa.
3. Tính đến thời gian boot và JVM warm-up.
4. Thu hẹp capacity chậm hơn mở rộng nếu đang có request dài.
5. Duy trì minimum cho mức tải cơ sở.
6. Dùng health và error rate để xác nhận scale-out thực sự có ích.
7. Theo dõi chi phí khi capacity chạm maximum kéo dài.

Metric có thể đến trễ hoặc không có dữ liệu; cần hiểu hành vi fallback/điều kiện của profile thực tế trước khi đưa vào production.

## 14. Capacity planning cho API Java

Giả sử một VM xử lý tối đa 120 request/s dưới giới hạn độ trễ ứng dụng chấp nhận được.

~~~text
Lưu lượng thực tế: 480 request/s
Năng lực lý thuyết mỗi VM: 120 request/s
Số VM lý thuyết: 480 / 120 = 4 VM
~~~

Con số trên không có dự phòng. Khi một VM gặp lỗi hoặc instance đang upgrade, 3 VM còn lại có thể không đủ. Ngoài ra:

- Database có thể không chịu thêm kết nối.
- JVM warm-up và cache cần thời gian.
- Request không có chi phí CPU bằng nhau.
- Một client có thể giữ connection lâu.
- Load balancer có độ lệch phân phối.
- VM size có giới hạn network và disk I/O.

Cần chạy **load test** để đo throughput, p95/p99 latency, error rate và resource usage. Sau đó đặt min/max và thresholds dựa trên SLO, không dựa vào phép tính lý thuyết đơn giản.

## 15. VM mới được tạo như thế nào khi scale-out?

Quy trình chung:

~~~text
Azure Monitor quyết định tăng capacity
  -> Azure kiểm tra quota/zone capacity
  -> Cấp VM, NIC và disk
  -> Boot OS từ image
  -> Chạy cloud-init/extension/startup
  -> Ứng dụng tải cấu hình và khởi động
  -> Readiness/health đạt điều kiện
  -> Load balancer đưa instance vào backend nhận request
~~~

Số VM có thể tăng trong Azure Portal trước khi ứng dụng đáp ứng request. Các điểm lỗi thường thấy:

- VCPU quota không đủ.
- SKU không còn capacity tại zone.
- Image version lỗi hoặc không thể truy cập.
- Subnet thiếu IP.
- VM không có outbound để tải dependency.
- Managed identity thiếu quyền đọc Key Vault.
- Database/firewall không cho kết nối.
- Health probe sai path hoặc port.
- Startup script lỗi nhưng không được giám sát.

**Time-to-ready** là mốc cần đo. Nếu mất nhiều phút tạo instance, cần capacity dự phòng và scale-out đủ sớm; tăng capacity chỉ sau khi người dùng gặp lỗi sẽ không đạt mục tiêu trải nghiệm.

## 16. Scale-in an toàn và xử lý công việc đang chạy

Scale-in giảm tài nguyên và chi phí, nhưng có thể kết thúc instance đang xử lý công việc.

### 16.1. HTTP workload

- Dùng khả năng drain/connection handling mà ingress hỗ trợ.
- Instance sắp bị kết thúc ngừng nhận request mới theo phương án được thiết kế.
- Session không được phụ thuộc bộ nhớ một instance duy nhất.
- Request quan trọng phải có cơ chế retry an toàn và idempotent khi cần.

### 16.2. Queue worker

- Ngừng nhận job mới trước khi tắt.
- Cho phép hoàn thành job đang chạy trong khoảng thời gian hợp lệ.
- Chỉ xác nhận hoàn tất message sau khi dữ liệu đã ghi bền vững.
- Nếu worker bị dừng đột ngột, message có thể được phát lại; worker phải chịu được retry.
- Với công việc dài, checkpoint ra storage có độ bền phù hợp.

### 16.3. Instance protection

Một số chế độ/cấu hình VMSS hỗ trợ bảo vệ instance khỏi scale-in hoặc các thao tác cụ thể. Chỉ dùng cho các trường hợp thực sự cần; nếu bảo vệ quá nhiều máy, autoscale có thể không giảm được capacity, gây tăng chi phí.

### 16.4. Dữ liệu local

Không lưu duy nhất dữ liệu ứng dụng quan trọng trên OS disk, ephemeral OS disk hoặc temporary disk của một instance có thể bị thay thế. Scale-in, reimage và replace có thể xóa các thay đổi local.

## 17. Stateless application và stateful dependencies

Một **stateless tier** có thể xử lý request ở bất kỳ instance nào. State cần duy trì được chuyển sang dịch vụ phù hợp:

| Trạng thái | Nơi lưu phù hợp |
|---|---|
| Session hoặc cache quan trọng | Cache ngoài VM hoặc database tùy kiến trúc |
| Dữ liệu giao dịch | Azure SQL, managed database hoặc hệ thống bền vững |
| File upload | Blob Storage hoặc lưu trữ có quản lý |
| Queue và retry | Queue Storage/Service Bus tùy tính năng |
| Secret | Azure Key Vault và identity phù hợp |
| Log/audit | Azure Monitor hoặc đích log tập trung |

Nếu toàn bộ VM trong nhóm cùng phụ thuộc một dịch vụ dữ liệu không có HA, thêm VM chỉ tăng compute chứ không làm ứng dụng chịu lỗi tổng thể.

Một kiến trúc thực tế cần xác định **RPO, RTO và failure domain** không chỉ cho VMSS mà cả database, storage, network và identity.

## 18. Upgrade và quản lý phiên bản

Thay đổi VMSS model/image không đồng nghĩa mọi instance lập tức được thay đổi theo cùng cách. Hành vi phụ thuộc orchestration mode và upgrade policy.

Những khái niệm thường gặp:

- **Manual:** người vận hành chủ động áp dụng thay đổi tới instance.
- **Automatic:** Azure áp dụng theo chính sách tự động tương ứng.
- **Rolling:** cập nhật theo nhóm/batch với các điều kiện health và giới hạn liên quan, khi được hỗ trợ.

Không mặc định cả ba chế độ có cùng khả năng và hành vi cho Uniform, Flexible, mọi SKU và mọi region.

### 18.1. Quy trình rollout

1. Build image/package ứng dụng mới.
2. Xác minh bản mới trong môi trường staging.
3. Cập nhật model theo cơ chế tương thích.
4. Áp dụng nâng cấp trên nhóm nhỏ hoặc batch nếu tính năng hỗ trợ.
5. Kiểm tra health, error rate, latency, resource usage.
6. Tiếp tục nếu đạt tiêu chí; dừng/rollback khi phát hiện lỗi.
7. Kiểm tra instance count và image version sau rollout.

### 18.2. Rollback và database migration

Rollback code không tự rollback được schema database. Nếu version mới thay đổi dữ liệu không tương thích, chạy trộn version cũ/mới trong rolling upgrade có thể lỗi. Cần chiến lược schema migration tương thích ngược và kế hoạch phục hồi dữ liệu riêng.

### 18.3. Reimage/replace

Reimage và replace có thể xóa thay đổi cục bộ và tạo lại môi trường OS/ứng dụng theo cấu hình nguồn. Hãy thiết kế workload để những thao tác này có thể thực hiện mà không mất dữ liệu cần duy trì.

## 19. Automatic repairs và upgrade là hai việc khác nhau

| Mục tiêu | Công cụ/cơ chế | Ý nghĩa |
|---|---|---|
| Scale theo tải | Autoscale | Tăng/giảm capacity |
| Nâng cấp ứng dụng/OS | Upgrade policy, deployment pipeline | Đưa version mới vào nhóm |
| Xử lý instance không khỏe | Health và repair theo khả năng được hỗ trợ | Phục hồi instance bị lỗi |

Một image lỗi có thể khiến tất cả instance mới thất bại; tự động sửa bằng cách tạo thêm instance dùng cùng image sẽ không giải quyết gốc rễ. Tương tự, autoscale có thể tăng số VM khi database nghẽn mà không giúp xử lý nhiều request hơn.

Cần monitoring và runbook để nhận diện lỗi hạ tầng, lỗi image, lỗi ứng dụng và lỗi downstream service.

## 20. Bảo mật VMSS

### 20.1. Identity và Azure RBAC

Ưu tiên **managed identity** cho ứng dụng khi cần đọc Blob, truy cập Key Vault hoặc API Azure hỗ trợ Microsoft Entra authentication. Cấp vai trò Azure RBAC theo nguyên tắc quyền tối thiểu.

Ví dụ: một API chỉ tải file từ Blob Storage không cần Owner của cả subscription.

### 20.2. Truy cập quản trị

Hạn chế SSH/RDP trên Internet; cân nhắc Azure Bastion, private network hoặc cơ chế quản lý máy an toàn. Tài khoản có quyền đổi VMSS model, image hoặc capacity có thể ảnh hưởng toàn hệ thống, nên phải có kiểm soát quyền/approval/PIM khi phù hợp.

### 20.3. Bảo vệ hệ điều hành

- Dùng image cập nhật, có quy trình patch.
- Cấu hình NSG và firewall để chỉ mở cổng cần thiết.
- Không hardcode secret vào image/cloud-init.
- Cân nhắc Defender for Cloud và Azure Policy để đánh giá bảo mật.
- Thu thập audit/guest logs tập trung.
- Kiểm tra các quyền truy cập Storage/DB qua private endpoint và DNS khi phù hợp.

### 20.4. Outbound an toàn

Dùng NAT Gateway hoặc một phương án egress được kiểm soát nếu ứng dụng cần kết nối ngoài. Không tùy tiện gắn public IP lên tất cả instances vì mục tiêu quản trị.

## 21. Giám sát hiệu năng và trạng thái instance

| Loại dữ liệu | Chỉ số ví dụ | Câu hỏi trả lời |
|---|---|---|
| VMSS capacity | Desired vs running/provisioning/healthy | Nhóm có đủ máy phục vụ không? |
| Compute | CPU, RAM guest metrics, network, disk | Thiếu tài nguyên ở đâu? |
| Application | Request rate, latency, error rate, JVM metrics | Người dùng có bị ảnh hưởng không? |
| Autoscale history | Scale decisions, cooldown, lỗi | Vì sao instance tăng/giảm? |
| Health/repair | Instance unhealthy, repair actions | Có VM lỗi lặp lại không? |
| Deployment | Image/extension errors, upgrade states | Release có thành công không? |
| Dependencies | DB latency, queue backlog, storage errors | Nút cổ chai ngoài VMSS ở đâu? |
| Cost | Số VM theo SKU/region, disk, IP, NAT, logs | Có chi phí bất thường không? |

**CPU thấp không đồng nghĩa hệ thống chưa cần scale.** API có thể đang chờ database hoặc network; queue backlog vẫn tăng. Ngược lại CPU cao do lỗi vòng lặp trong code không nhất thiết được giải quyết bằng thêm VM.

Có thể cấu hình Azure Monitor alerts khi:

- Healthy instance count thấp hơn mức an toàn.
- Scale-out thất bại vì quota.
- Capacity chạm maximum liên tục.
- 5xx/error rate tăng sau upgrade.
- Một instance bị repair nhiều lần.
- Queue backlog hoặc job latency vượt SLO.

Các chỉ số guest memory hoặc application metrics có thể cần agent/instrumentation riêng; không nên giả định Azure Portal luôn có sẵn.

## 22. Kiểm soát chi phí và quota

Chi phí của một VMSS không chỉ là số lượng VM.

| Hạng mục | Ví dụ chi phí |
|---|---|
| Compute | VM SKU, số instance, thời gian chạy |
| OS/data disks | Managed disk theo loại và dung lượng |
| Network | Load Balancer, Public IP, NAT Gateway, Firewall, bandwidth |
| Image | Lưu/nhân bản image trong Azure Compute Gallery |
| Monitoring | Log ingestion, retention và công cụ giám sát |
| Dữ liệu | Database, Blob, Queue, cache, backup |

Autoscale giúp giảm thời gian chạy VM dư thừa ở tải thấp, nhưng vẫn có mức **minimum capacity** và các tài nguyên đi kèm có thể tiếp tục phát sinh chi phí.

### 22.1. Quota và actual capacity

Subscription có quota vCPU theo region và VM family. Khi chạm quota hoặc không còn capacity tại zone, yêu cầu scale-out có thể thất bại. Hãy:

1. Kiểm tra quota trước ngày ra mắt.
2. Theo dõi lỗi scaling/provisioning.
3. Chọn SKU và region có khả năng cung ứng phù hợp.
4. Đặt maximum không vượt quá kế hoạch ngân sách.
5. Tạo cảnh báo Azure Cost Management.
6. Cân nhắc các mô hình giá phù hợp cho tải thường trực và batch.

### 22.2. Spot VM cho batch

**Azure Spot VMs** có thể phù hợp với workload chịu được eviction, như chuyển đổi file, rendering hoặc xử lý theo lô có checkpoint. Không dùng Spot làm nơi duy nhất chứa dịch vụ cần liên tục nếu không có phương án chịu lỗi và capacity thay thế.

Chính sách Spot, phối hợp regular/Spot, giá và cơ chế eviction phụ thuộc các tính năng được Azure hỗ trợ trong mode/SKU đang dùng.

## 23. Azure Portal: tạo một VMSS thử nghiệm

**Điều kiện:** có subscription và quyền tạo VMSS/network/disk, VM family còn quota, có ngân sách lab được duyệt, và không dùng môi trường production.

Quy trình:

1. Trong **Azure Portal**, mở **Virtual Machine Scale Sets → Create**.
2. Chọn subscription và resource group riêng, ví dụ **rg-vmss-lab**.
3. Đặt tên **vmss-api-lab**, chọn region và orchestration mode theo thiết kế.
4. Chọn image Linux được hỗ trợ và VM size phù hợp ngân sách.
5. Đặt số instance khởi điểm **2**.
6. Nếu region/SKU cho phép, cấu hình phân bố Availability Zones.
7. Cấu hình SSH key hoặc phương thức quản trị an toàn.
8. Chọn VNet/subnet đủ IP cho mức capacity tối đa.
9. Chọn ingress phù hợp, kết nối backend pool và health probe.
10. Thiết lập cloud-init/extension có nội dung ứng dụng thử nghiệm.
11. Kiểm tra network, disk, identity và chi phí ước tính trước khi tạo.
12. Chờ triển khai hoàn thành, xem trạng thái instances.
13. Xác minh hai backend thực sự healthy và phục vụ một URL thử nghiệm.

Với bài lab ban đầu, có thể dùng Nginx như một web server đơn giản; khi chuyển sang API Java phải kiểm tra JVM startup, health và dependency thật.

## 24. Azure CLI: quan sát và thay đổi capacity

Lệnh minh họa dành cho VMSS **đã tồn tại**. Hãy thay tên resource group/scale set theo lab.

~~~bash
az login
az account set --subscription "<subscription-id>"

az vmss show \
  --resource-group rg-vmss-lab \
  --name vmss-api-lab \
  --query "{name:name,capacity:sku.capacity,vmSize:sku.name,orchestrationMode:orchestrationMode}" \
  --output json
~~~

Với mode hỗ trợ API quản lý VMSS instances:

~~~bash
az vmss list-instances \
  --resource-group rg-vmss-lab \
  --name vmss-api-lab \
  --output table
~~~

Thay đổi desired capacity bằng lệnh minh họa:

~~~bash
az vmss scale \
  --resource-group rg-vmss-lab \
  --name vmss-api-lab \
  --new-capacity 3
~~~

Lưu ý: lệnh và cách quản lý VM thành viên có thể khác theo orchestration mode. Với Flexible, kiểm tra CLI/API thích hợp trước khi thao tác; không mặc định mọi lệnh Uniform đều tương thích.

**Scale thành công về mặt lệnh không chứng minh VM mới đã healthy.** Theo dõi provisioning, health, trạng thái backend và request thật sau đó.

Nếu autoscale đã bật, bộ điều khiển có thể tiếp tục thay đổi capacity theo profile. Khi thực hành scale manual, ghi lại rule đang hoạt động để không hiểu nhầm.

## 25. Autoscale policy minh họa

Đây là pseudoconfiguration diễn đạt một chính sách học tập, **không phải YAML có thể triển khai trực tiếp lên Azure**:

~~~yaml
autoscale:
  minInstances: 2
  defaultInstances: 2
  maxInstances: 8
  rules:
    - metric: "Percentage CPU"
      condition: "average > 70% during 10 minutes"
      action: "increase by 1 instance"
      cooldown: "10 minutes"
    - metric: "Percentage CPU"
      condition: "average < 30% during 20 minutes"
      action: "decrease by 1 instance"
      cooldown: "10 minutes"
  schedule:
    note: "Có thể bổ sung profile giờ cao điểm"
~~~

Để thực thi, dùng cấu hình Azure Monitor Autoscale của Azure Portal, Bicep/ARM hoặc CLI theo schema thật của phiên bản hiện hành.

### 25.1. Cách kiểm tra quy tắc

1. Xác minh metric nguồn có dữ liệu.
2. Tạo tải thử có giới hạn trong sandbox.
3. Đợi đủ cửa sổ quan sát.
4. Kiểm tra autoscale history và scale action.
5. Theo dõi VM mới từ provisioning đến application readiness.
6. Ngừng tải và quan sát cooldown/scale-in.
7. Ghi nhận error rate và chi phí, không chỉ số VM.

Không stress test không kiểm soát trên subscription dùng chung. Giới hạn max capacity, thời gian tạo tải và ngân sách.

## 26. Ví dụ triển khai worker xử lý theo lô

Một hệ thống xử lý ảnh có hàng nghìn file đầu vào:

~~~mermaid
flowchart TD
    SRC[Blob input] --> Q[Queue công việc]
    Q --> VMSS[VMSS workers]
    VMSS --> OUT[Blob output]
    VMSS --> MET[Queue backlog và processing metrics]
    MET --> AUTO[Autoscale]
    AUTO --> VMSS
~~~

### 26.1. Quy tắc xử lý

- Mỗi message có ID công việc và tham chiếu file.
- Worker nhận message, xử lý rồi ghi output bền vững.
- Chỉ xóa/ack message sau khi ghi kết quả thành công.
- Nếu instance bị ngắt, message có thể được xử lý lại.
- Worker phải idempotent để retry không tạo duplicate sai.
- Với job dài, checkpoint và xử lý timeout phù hợp.

### 26.2. Scale theo backlog

CPU có thể không phù hợp nếu worker chờ I/O nhiều. Số message chờ hoặc tuổi message có thể phản ánh nhu cầu tốt hơn. Nếu dùng metric custom hoặc một thành phần adapter, xác minh cơ chế xuất metric và khả năng Azure Monitor autoscale nhận được tín hiệu đó.

### 26.3. Khi nào dùng Spot?

Phù hợp khi job có thể khởi động lại; không phù hợp nếu mất một VM dẫn tới mất toàn bộ kết quả không thể tạo lại. Quy trình retry phải chịu được eviction đột ngột.

## 27. Checklist vận hành rolling upgrade

Trước đợt nâng cấp:

- Có image/package version rõ ràng và đã thử nghiệm.
- Instance mới có startup/readiness đáng tin cậy.
- Load balancer loại backend unhealthy khỏi luồng mới.
- Capacity tối thiểu đủ phục vụ trong lúc một batch bị thay.
- Database schema hỗ trợ trạng thái chạy đồng thời version cũ và mới.
- Có stop condition theo error rate/latency.
- Có rollback plan và người trực.
- Đã kiểm tra hỗ trợ rolling upgrade theo orchestration mode đang dùng.

Trong đợt nâng cấp, theo dõi từng batch và **không tiếp tục tự động nếu health không đạt** theo chính sách đã đặt.

Sau nâng cấp, đối chiếu image version thực tế và capacity/health của toàn bộ instance. Ghi lại incident nếu xảy ra hành vi ngoài dự kiến.

## 28. Các lỗi phổ biến

### 28.1. VMSS không tăng số VM

Có thể quy tắc chưa vượt ngưỡng, cooldown đang còn, maximum đã đạt, quota thiếu, region/zone thiếu capacity, subnet hết địa chỉ hoặc image/extension lỗi. Kiểm tra autoscale decisions và provisioning events.

### 28.2. VM mới không nhận request

Thường do app chưa chạy, readiness chưa đạt, backend pool chưa đúng, NSG chặn hoặc health probe dùng sai port/path. Đừng sửa bằng cách tắt health probe một cách tùy tiện.

### 28.3. Tăng VM nhưng API càng chậm

Một database đã hết connection pool hoặc bị lock có thể trở nên quá tải khi nhiều VM cùng truy cập. Kiểm tra dependency trước khi tiếp tục scale-out.

### 28.4. Scale-in gây mất dữ liệu

Ứng dụng lưu file quan trọng trên disk local, job bị kết thúc không checkpoint hoặc message bị ack trước khi ghi output. Cần sửa quy trình state/retry và thiết kế drain.

### 28.5. Model đã cập nhật nhưng instances vẫn ở version cũ

Kiểm tra upgrade policy và trạng thái rollout. Thay model không nhất thiết tự thay image/software của VM hiện có.

### 28.6. Chỉ có một VM khỏe sau lỗi zone

Phân bố zone chưa đúng hoặc các dependency dùng chung cũng bị lỗi. Kiểm tra placement thật và toàn bộ đường ứng dụng, không chỉ VMSS.

### 28.7. Chi phí tăng bất ngờ

Autoscale có thể giữ capacity gần maximum, instance không khỏe bị tạo lại liên tục hoặc disk/log/NAT phát sinh chi phí. Theo dõi actual capacity, Azure Cost Management và scale events.

### 28.8. Managed identity không lấy được secret

Kiểm tra role assignments, chính sách Key Vault, Private Endpoint, DNS, outbound và startup order. Không nhúng secret vào image để bỏ qua lỗi quyền.

## 29. Bài thực hành theo giai đoạn

**Bối cảnh:** một API/web service mẫu chạy trên VMSS trong resource group lab. Mục tiêu là quan sát scale-out, scale-in và khả năng phục vụ ứng dụng.

### Giai đoạn A: thiết kế

1. Vẽ topology gồm VNet, subnet, VMSS, ingress, health endpoint và dịch vụ dữ liệu giả.
2. Chọn Uniform/Flexible và nêu lý do.
3. Chọn 2 instance ban đầu, mức min 2, max 4.
4. Chọn image Linux phổ biến và VM SKU đáp ứng lab.
5. Xác định giới hạn ngân sách và kế hoạch cleanup.

### Giai đoạn B: triển khai

1. Tạo VMSS ở Azure Portal.
2. Cài và khởi động web service trên mọi instance.
3. Kết nối backend pool/probe đúng quy trình.
4. Kiểm tra từng instance healthy và endpoint chung trả nội dung.
5. Xác minh không cần public IP riêng cho mỗi VM nếu ingress đã có.

### Giai đoạn C: scale manual

1. Tăng capacity từ 2 lên 3.
2. Ghi thời điểm thao tác, provisioning và readiness.
3. Xác minh instance thứ ba nhận request.
4. Giảm về 2 khi không còn job quan trọng.
5. Kiểm tra ứng dụng vẫn đáp ứng sau scale-in.

### Giai đoạn D: autoscale

1. Bật cấu hình autoscale với min 2 và max 4.
2. Đặt metric CPU và ngưỡng an toàn phù hợp lab.
3. Tạo tải ngắn, có giới hạn.
4. Theo dõi autoscale history, số instance và health.
5. Dừng tải, chờ cooldown và đánh giá scale-in.

### Giai đoạn E: nâng cấp

1. Chuẩn bị thay đổi nhỏ ở web page/version.
2. Chọn cơ chế update phù hợp mode và cấu hình đang dùng.
3. Quan sát phiên bản trên các instance sau rollout.
4. Ghi điều kiện dừng hoặc rollback nếu health lỗi.

### Giai đoạn F: báo cáo và dọn tài nguyên

1. Ghi bảng capacity mục tiêu/thực tế ở các mốc thời gian.
2. Ghi time-to-ready, lỗi ứng dụng, trạng thái probe.
3. Đánh giá quota và chi phí.
4. Dọn các tài nguyên **thuộc riêng bài lab** sau khi kiểm tra quyền sở hữu và phụ thuộc.
5. Không xóa tài nguyên chung trong subscription.

**Tiêu chí hoàn thành:** hiểu được VMSS điều phối capacity, nhưng load balancer và health mới quyết định instance có thật sự nhận lưu lượng; ứng dụng phải xử lý được việc một instance biến mất.

## 30. Checklist trước khi triển khai production

- [ ] Đã chọn orchestration mode đúng với tính năng cần thiết.
- [ ] Image/package có version rõ ràng và kế hoạch rollback.
- [ ] VM SKU, quota và zone capacity được xác minh.
- [ ] Minimum capacity và autoscale thresholds dựa trên load test/SLO.
- [ ] VNet/subnet đủ IP cho quy mô tối đa.
- [ ] Ingress, NSG, egress và DNS được thiết kế đúng.
- [ ] Health/readiness phản ánh khả năng phục vụ thực.
- [ ] VM startup và time-to-ready được đo.
- [ ] Scale-in có phương án kết thúc request/job an toàn.
- [ ] Session và dữ liệu quan trọng không nằm duy nhất trên VM.
- [ ] Managed identity và quyền RBAC là tối thiểu.
- [ ] Có monitoring cho autoscale, VM, app và downstream.
- [ ] Đã thử mất một instance và kế hoạch HA theo zone.
- [ ] Upgrade policy, rolling health và rollback đã được kiểm tra.
- [ ] Có alert cho scale failure, capacity max, unhealthy VM và 5xx.
- [ ] Có ngân sách, giới hạn scale, quản lý snapshot/disk và kế hoạch cleanup.
- [ ] Có chiến lược DR riêng nếu yêu cầu chịu lỗi toàn region.

## 31. Câu hỏi tự kiểm tra

1. VMSS mang lại khả năng nào hơn việc tạo ba Azure VM thủ công?
2. Uniform và Flexible khác nhau như thế nào ở cách quản trị instance?
3. Vì sao capacity=3 không tự bảo đảm một instance nằm ở mỗi Availability Zone?
4. Khi VM mới được provisioned nhưng health chưa đạt, nó có nên nhận HTTP request không?
5. Vì sao CPU cao không luôn đồng nghĩa phải thêm VM?
6. Cooldown và khoảng cách giữa ngưỡng scale-out/scale-in giúp gì?
7. Khi scale-in một queue worker, những cơ chế nào giúp không mất job?
8. Stateless API nên lưu session và file upload ở đâu?
9. Vì sao chỉnh file thủ công trên một VMSS instance không phải cách triển khai ứng dụng tốt?
10. Nếu deployment model đã cập nhật mà instance chưa đổi, phải kiểm tra gì?
11. Managed identity và Azure RBAC có vai trò nào trong việc VMSS truy cập Storage và Key Vault?
12. Một nhóm API dùng Spot VM có những rủi ro nào?
13. Bạn sẽ theo dõi metric và log nào để phát hiện scale-out không đạt mục tiêu?
14. Khi database là nút cổ chai, việc tăng số VM có thể làm tình hình xấu đi như thế nào?
15. Để đánh giá VMSS thực sự có HA, ngoài instance count còn cần xem các thành phần nào?

## 32. Tổng kết

**Azure Virtual Machine Scale Sets** hỗ trợ điều phối nhiều máy ảo và thay đổi capacity để đáp ứng nhu cầu tính toán. Tuy nhiên, **VMSS chỉ quản lý hạ tầng**: ứng dụng cần stateless hoặc quản lý state đúng cách; hệ thống cần mạng và ingress phù hợp, health signal đáng tin cậy, image được quản lý phiên bản, quy trình scale-in/upgrade an toàn và theo dõi bằng Azure Monitor.

Trong thiết kế Azure, hãy kết hợp **VMSS + load balancing + autoscale + Availability Zones + managed identity/RBAC + Storage/Database + monitoring + Cost Management**. Đừng chỉ kiểm tra số VM được tạo; hãy đo **time-to-ready**, khả năng phục vụ khi một instance mất, chất lượng ứng dụng trong lúc scale-in/upgrade và chi phí khi tải thay đổi. Đó là nền tảng cho kiến trúc compute co giãn, có thể bảo vệ và vận hành ổn định.
