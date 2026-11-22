# Giảm thiểu tấn công bằng Azure DDoS Protection

> **Chương:** Kết nối và bảo vệ mạng  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Nhận diện các hình thức **Distributed Denial of Service (DDoS)** thường gặp và ảnh hưởng đến tính sẵn sàng của ứng dụng.
2. Giải thích Azure DDoS Protection bảo vệ lưu lượng đến **public IP của tài nguyên Azure** như thế nào và phân biệt cơ chế này với NSG, Azure Firewall, Web Application Firewall (WAF).
3. So sánh lớp bảo vệ hạ tầng mặc định của Azure với lựa chọn **DDoS Network Protection** và **DDoS IP Protection**.
4. Xác định phạm vi cần bảo vệ, liên kết DDoS protection plan với VNet khi dùng Network Protection và kiểm tra cấu hình.
5. Thiết lập tư duy giám sát bằng Azure Monitor, cảnh báo, diagnostic logs và quy trình ứng phó.
6. Lập phương án kiểm chứng có kiểm soát, đánh giá giới hạn kỹ thuật, quản lý quyền và chi phí.

## 1. Vì sao cần giảm thiểu DDoS?

Một API bán hàng có thể được triển khai trên Azure Virtual Machines, Azure Load Balancer hoặc Application Gateway. Ứng dụng hoạt động bình thường với 2.000 request/phút; một ngày, nhiều nguồn trên Internet đồng thời gửi một lượng lớn lưu lượng khiến khách hàng thực không thể truy cập.

Đây có thể là **DDoS**: nhiều nguồn phối hợp hoặc cùng gây ra lưu lượng làm cạn kiệt tài nguyên mạng, khả năng xử lý kết nối hoặc tài nguyên ứng dụng của mục tiêu.

Mục tiêu của kẻ tấn công không nhất thiết là đánh cắp dữ liệu; họ có thể khiến dịch vụ **không còn sẵn sàng**. Một cuộc tấn công DDoS có thể gây:

- Gián đoạn truy cập, tăng độ trễ, timeout hoặc từ chối kết nối.
- Tắc nghẽn băng thông hoặc tiêu hao khả năng xử lý gói tin/kết nối.
- Tăng tải hệ thống backend, gây hiệu ứng dây chuyền giữa gateway, API và cơ sở dữ liệu.
- Giảm doanh thu và uy tín khi các hoạt động quan trọng bị gián đoạn.
- Khó phân biệt lưu lượng tấn công với đợt tăng truy cập hợp lệ nếu thiếu quan sát.

**Giảm thiểu DDoS** không có nghĩa mọi yêu cầu độc hại đều bị chặn hoặc dịch vụ chắc chắn không bao giờ gián đoạn. Mục tiêu là nhận diện và hấp thụ/lọc lưu lượng tấn công, giữ nhiều lưu lượng hợp lệ đi qua nhất có thể, đồng thời duy trì khả năng điều tra và ứng phó.

### DDoS khác một sự cố tăng tải hợp lệ như thế nào?

Cả hai có thể tạo ra CPU cao, kết nối nhiều và độ trễ tăng. Một chiến dịch bán hàng thật cũng có thể làm quá tải ứng dụng. Điều tra cần đối chiếu:

- Biến động lưu lượng theo thời gian, giao thức, IP nguồn, cổng và phân bố nguồn.
- Các chỉ số mạng so với khả năng và đường lưu lượng thông thường.
- Lượng request hợp lệ, kết quả HTTP, tải backend và nhật ký ứng dụng.
- Những thay đổi hệ thống gần thời điểm sự cố như triển khai bản mới hoặc thay đổi firewall.

Không nên xem “lưu lượng tăng” là bằng chứng DDoS nếu chưa có dữ liệu bổ trợ.

## 2. Các lớp tấn công cần phân biệt

DDoS thường được phân loại theo nơi mà cuộc tấn công gây áp lực.

| Nhóm | Ví dụ khái quát | Tác động dự kiến | Lớp phòng vệ chính |
| --- | --- | --- | --- |
| **Volumetric** | Lượng lớn gói UDP hoặc lưu lượng khuếch đại | Chiếm băng thông, gây nghẽn đường vào | Giảm thiểu DDoS ở lớp mạng |
| **Protocol / state exhaustion** | Lượng lớn yêu cầu thiết lập kết nối TCP/SYN | Làm cạn tài nguyên xử lý kết nối | DDoS Protection L3/L4, kiến trúc mạng và cấu hình dịch vụ |
| **Application-layer** | Nhiều yêu cầu HTTP/HTTPS nhằm vào đường dẫn xử lý nặng | Chiếm luồng ứng dụng, CPU, database | WAF, rate limiting, caching, xác thực và thiết kế ứng dụng |
| **Multi-vector** | Kết hợp lưu lượng mạng với yêu cầu tầng ứng dụng | Gây sức ép lên nhiều lớp | Phòng vệ nhiều lớp, quan sát chung, playbook ứng phó |

**L3/L4** là lớp mạng/vận chuyển (IP, TCP, UDP). **L7** là lớp ứng dụng (HTTP, API, hành vi logic ứng dụng). Azure DDoS Protection tập trung giảm thiểu các kiểu tấn công **L3/L4**; để bảo vệ các kiểu HTTP flood hoặc khai thác logic nghiệp vụ cần thêm các cơ chế ứng dụng tương ứng.

Không nên đánh đồng một tấn công DDoS với cố gắng dò mật khẩu, chèn SQL hoặc lợi dụng lỗ hổng mã nguồn. Chúng có thể cùng gây nguy cơ bảo mật nhưng cần tín hiệu phát hiện và biện pháp bảo vệ khác nhau.

## 3. Azure DDoS Protection hoạt động như thế nào?

Microsoft vận hành hạ tầng Azure với năng lực bảo vệ DDoS ở mức nền tảng. **Azure DDoS Protection** là dịch vụ bổ sung các khả năng giảm thiểu, quan sát và quản trị chuyên biệt cho lưu lượng tới những **public IP** được hỗ trợ.

Với tài nguyên được bảo vệ phù hợp, dịch vụ phân tích lưu lượng hướng đến public IP, học mẫu lưu lượng bình thường và phát hiện các dấu hiệu bất thường. Khi phát hiện tấn công vượt ngưỡng bảo vệ, nền tảng kích hoạt quy trình giảm thiểu để lọc lưu lượng tấn công; lưu lượng được đánh giá hợp lệ tiếp tục tới ứng dụng trong khả năng dịch vụ.

### Luồng khái quát

~~~mermaid
flowchart LR
    U["Người dùng hợp lệ"]
    B["Nguồn lưu lượng tấn công"]
    A["Mạng biên Azure"]
    D{"Phát hiện và\nmitigation DDoS L3/L4"}
    W["Public IP của workload"]
    G["Load Balancer / Application Gateway / VM"]
    APP["Ứng dụng và backend"]
    M["Azure Monitor\nMetrics, alerts, logs"]

    U --> A
    B --> A
    A --> D
    D -->|"Lưu lượng hợp lệ được chuyển tiếp"| W
    D -->|"Lưu lượng bị xác định là tấn công"| X["Bị lọc / giảm thiểu"]
    W --> G --> APP
    D -.-> M
~~~

Đây là sơ đồ kiến trúc ý niệm, không phải bản đồ chính xác của đường truyền hay từng thành phần nội bộ Microsoft. Cơ chế giảm thiểu thực tế được dịch vụ quản lý và có thể khác theo loại tấn công, tài nguyên, cấu hình và gói sử dụng.

### Những đặc điểm cần hiểu

- **Theo public IP được bảo vệ:** hành vi lưu lượng và ngưỡng phát hiện được áp dụng phù hợp với tài nguyên được hỗ trợ, không mặc định rằng mọi tài nguyên trong subscription đều được bảo vệ cùng mức.
- **Tự động khi phát hiện:** không phải chờ quản trị viên đăng nhập thủ công để kích hoạt lọc lưu lượng ở mỗi cuộc tấn công. Tuy nhiên vẫn cần cấu hình dịch vụ bảo vệ từ trước.
- **Giám sát và thông báo:** gói/cấu hình phù hợp có thể phát sinh metric, attack notification, mitigation report/flow log để SOC đánh giá sự cố.
- **Tích hợp hệ sinh thái Azure:** kết hợp với Azure Monitor, cảnh báo và hệ thống xử lý sự cố.
- **Giới hạn phạm vi:** bảo vệ L3/L4 không thay thế bảo mật ứng dụng, phục hồi backend, thiết kế multi-region hoặc kiểm soát quyền truy cập.

### Mối liên hệ với IP riêng trong VNet

Nếu ứng dụng chỉ có **private IP** và không có luồng vào trực tiếp qua public IP thuộc phạm vi hỗ trợ, không nên kết luận cần bật DDoS Network Protection chỉ vì trong VNet có máy chủ. Hãy xác định **đường Internet ingress thực tế**: có thể là public IP của Application Gateway/Load Balancer, một dịch vụ biên được quản lý khác, hoặc không có public endpoint nào.

## 4. Các lựa chọn bảo vệ và phạm vi áp dụng

Khi thiết kế trên Azure, cần phân biệt ba khái niệm thường được nhắc đến:

1. **Bảo vệ DDoS ở mức hạ tầng Azure:** lớp nền tảng cung cấp tự động cho hạ tầng Azure, không yêu cầu tạo riêng một DDoS protection plan.
2. **Azure DDoS Network Protection:** lựa chọn quản trị bảo vệ theo **VNet** thông qua DDoS protection plan; bảo vệ các public IP được hỗ trợ có liên quan tới những tài nguyên trong VNet được bật bảo vệ.
3. **Azure DDoS IP Protection:** lựa chọn bật bảo vệ chuyên biệt theo **public IP** được hỗ trợ khi cần áp dụng cho từng địa chỉ riêng lẻ.

Tên SKU, tính năng chi tiết, phạm vi tương thích và điều khoản có thể được Microsoft điều chỉnh theo thời gian. Trước triển khai production, kiểm tra mô tả và bảng giá hiện hành của gói tại region/subscription đích.

| Tiêu chí | Bảo vệ hạ tầng mặc định | DDoS Network Protection | DDoS IP Protection |
| --- | --- | --- | --- |
| Phạm vi quản trị | Bảo vệ chung của hạ tầng Azure | Các public IP được hỗ trợ trong những VNet liên kết plan | Từng public IP được hỗ trợ và được bật tính năng |
| Cấu hình của khách hàng | Không tạo plan riêng | Tạo DDoS protection plan, liên kết VNet | Cấu hình tại tài nguyên public IP tương ứng |
| Tình huống phù hợp | Mức nền mặc định | Nhiều public IP/VNet, mô hình mạng quy mô lớn | Một hoặc một số ít public IP cần bảo vệ riêng |
| Quan sát/khả năng đi kèm | Không nên mặc định có đầy đủ telemetry chuyên biệt | Có tính năng giám sát và hỗ trợ tùy điều khoản gói | Có tính năng tương ứng theo điều kiện gói |
| Chi phí bổ sung | Không tính phí DDoS Protection chuyên biệt | Theo mô hình giá Network Protection hiện hành | Theo mô hình giá IP Protection hiện hành |

**Không chọn gói chỉ theo số IP mà bỏ qua đặc điểm tài nguyên.** Cần xác minh public IP có được loại bảo vệ đó hỗ trợ không, đường ingress có đi qua địa chỉ ấy không và các tính năng giám sát/hỗ trợ có đáp ứng yêu cầu vận hành hay không.

### Mối quan hệ DDoS Network Protection – VNet – public IP

Một DDoS protection plan là **Azure resource riêng** có thể được dùng để bật DDoS Network Protection cho các VNet phù hợp. Khi VNet liên kết với plan, những **public IP của tài nguyên thuộc diện hỗ trợ trong VNet** trở thành đối tượng áp dụng bảo vệ theo cơ chế của gói.

Điều đó **không có nghĩa** mỗi private IP trong VNet trở thành một public endpoint. Nó cũng không có nghĩa mọi public FQDN của các PaaS toàn cục đều thuộc cùng plan.

Ví dụ:

- Một Application Gateway có frontend public IP ở VNet phục vụ ứng dụng có thể thuộc phạm vi bảo vệ phù hợp của Network Protection.
- Một VM có public IP được hỗ trợ trong VNet có thể là đối tượng bảo vệ.
- Một Azure Front Door endpoint toàn cục là dịch vụ biên được Microsoft quản lý theo kiến trúc riêng; không “gắn” DDoS Network Protection vào Front Door bằng cách link một VNet bất kỳ.

### Network Protection có ích khi nào?

Công ty vận hành ba VNet thuộc Dev, Staging và Prod, chứa nhiều public IP phục vụ các dịch vụ quan trọng. Nhóm mạng muốn dùng cơ chế bảo vệ quản lý theo VNet, tập trung giám sát và thống nhất quy trình vận hành. Đây là tình huống đáng đánh giá DDoS Network Protection.

### IP Protection có ích khi nào?

Một ứng dụng nhỏ chỉ có một public IP trực tiếp được hỗ trợ và chưa cần triển khai plan quản trị nhiều VNet. Khi đó có thể đánh giá DDoS IP Protection theo địa chỉ IP. Hãy xác minh SKU public IP, region, kiểu tài nguyên và tính năng đi kèm ở thời điểm triển khai.

## 5. Kết hợp DDoS Protection với những lớp bảo vệ khác

Các thành phần bảo mật Azure có mục tiêu khác nhau:

| Cơ chế | Vai trò chính | Điều không tự giải quyết |
| --- | --- | --- |
| **Azure DDoS Protection** | Nhận diện và giảm thiểu flood L3/L4 vào public IP được hỗ trợ | Lỗ hổng ứng dụng, auth abuse, HTTP flood đặc thù |
| **Network Security Group (NSG)** | Cho phép/từ chối lưu lượng mạng theo quy tắc IP, port, protocol, direction | Không thay thế hệ thống giảm thiểu DDoS quy mô lớn |
| **Azure Firewall** | Kiểm soát, ghi log và áp dụng chính sách luồng mạng theo khả năng SKU | Không mặc định thay thế dịch vụ giảm thiểu DDoS hay WAF cho mọi luồng |
| **Web Application Firewall (WAF)** | Lọc các mối đe dọa HTTP/HTTPS, quy tắc ứng dụng và một số cơ chế kiểm soát lưu lượng | Không phải lớp hấp thụ tất cả dạng flood L3/L4 |
| **Azure Front Door** | Điểm vào toàn cục, định tuyến/caching và các tính năng bảo vệ tại biên tùy cấu hình | Không tự làm backend an toàn nếu backend còn mở đường truy cập ngoài ý muốn |
| **Azure Monitor / Log Analytics** | Quan sát metric, log, tạo alert và điều tra | Không phải cơ chế lọc DDoS tự thân |
| **Autoscale / caching / redundancy** | Tăng độ chịu tải, hạn chế điểm nghẽn | Không phải giải pháp chặn lưu lượng tấn công và có thể làm tăng chi phí |

### Ví dụ phòng vệ nhiều lớp cho ứng dụng thương mại điện tử

~~~mermaid
flowchart TD
    INTERNET["Client trên Internet"]
    EDGE["Điểm vào: public IP / gateway / edge phù hợp"]
    DDOS["DDoS mitigation L3/L4\ntrên public IP được bảo vệ"]
    WAF["WAF / quy tắc HTTP\nrate limiting, managed rules"]
    APP["App tier / API"]
    DB["Database qua mạng riêng"]
    OBS["Azure Monitor\ncảnh báo và incident process"]
    INTERNET --> EDGE
    EDGE -.-> DDOS
    EDGE --> WAF --> APP --> DB
    DDOS -.-> OBS
    WAF -.-> OBS
    APP -.-> OBS
~~~

Đây là mô hình chức năng. Với ứng dụng dùng Azure Front Door làm entrypoint, cơ chế bảo vệ biên phải được cấu hình theo khả năng của Front Door; không thể suy luận rằng tất cả các hộp trong sơ đồ là những tài nguyên riêng có thể mắc nối tiếp tùy ý.

**Nguyên tắc thiết kế:** xác định entrypoint trước rồi chọn cơ chế DDoS/WAF đúng với **tài nguyên thực tế**. Nếu không kiểm soát được truy cập công cộng tới origin, kẻ tấn công có thể đi trực tiếp tới origin và bỏ qua lớp WAF ở biên.

## 6. Khảo sát phạm vi bảo vệ trước khi bật dịch vụ

Giả sử hệ thống gồm:

- Subscription `prod-subscription`.
- VNet `vnet-web-prod`, subnet `snet-appgw` chứa Application Gateway.
- Public IP `pip-appgw-prod` dùng làm frontend cho truy cập Internet.
- API chạy trong subnet riêng, database dùng Private Endpoint.
- Một số dịch vụ khác phục vụ người dùng thông qua Azure Front Door.

Không nên bật bảo vệ đồng loạt mà chưa có sơ đồ ingress.

### Bảng khảo sát mẫu

| Thành phần | Internet ingress? | Public IP trong VNet? | Hướng đánh giá bảo vệ |
| --- | --- | --- | --- |
| Application Gateway `pip-appgw-prod` | Có | Có, nếu cấu hình frontend như mô tả | DDoS Network/IP Protection theo hỗ trợ + WAF |
| VM API chỉ có private IP | Không trực tiếp | Không | Bảo vệ đường vào upstream, NSG và ứng dụng |
| Azure SQL qua Private Endpoint | Không trực tiếp qua endpoint riêng | Không phải public IP của VM | Private networking, xác thực và giám sát |
| Azure Front Door endpoint | Có | Không phải public IP bên trong VNet ứng dụng | Dùng khả năng bảo vệ biên của Front Door + WAF |
| Một public IP riêng cho dịch vụ mạng được hỗ trợ | Có | Tùy cách triển khai | Xác minh hỗ trợ Network/IP Protection |

**Câu hỏi cần trả lời trước khi tạo DDoS plan:**

1. Public IP nào đang nhận lưu lượng từ Internet, thuộc subscription/region/resource nào?
2. Public IP đó gắn với VNet nào, có dùng Standard SKU hoặc điều kiện bắt buộc khác của loại bảo vệ không?
3. Những luồng nào đang đi qua public IP và các protocol/port nào phải được phục vụ?
4. Có nhiều VNet và bao nhiêu IP thực sự cần bảo vệ chuyên biệt?
5. Ai chịu trách nhiệm chi phí, vận hành alert, xử lý sự cố và quản lý quyền cấu hình?
6. Có thành phần L7 cần WAF, rule ứng dụng hoặc caching riêng không?

Dữ liệu này là đầu vào để lựa chọn phương án có ý nghĩa hơn việc bật dịch vụ theo tên gọi.

## 7. Bật Azure DDoS Network Protection cho VNet

Phần này mô tả **một cách cấu hình minh họa**, không yêu cầu người đọc thực sự tạo tài nguyên có tính phí. Các cú pháp và tham số CLI có thể thay đổi theo phiên bản; dùng Azure CLI được hỗ trợ và kiểm tra trợ giúp lệnh trong môi trường của bạn.

### 7.1. Chuẩn bị

Bạn cần:

- Một Azure subscription được phép dùng để thực hành.
- Resource group dành cho quản trị bảo mật, ví dụ `rg-security-prod`, đã tồn tại.
- Một VNet có tài nguyên public IP cần bảo vệ, ví dụ `vnet-web-prod` ở `rg-network-prod`.
- Quyền Azure RBAC phù hợp để quản lý DDoS protection plan và cập nhật VNet liên quan.
- Đánh giá chi phí/budget và phê duyệt thay đổi nếu là môi trường thật.

Kiểm tra ngữ cảnh CLI:

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Chọn subscription khi đã biết chắc Subscription ID cần dùng.
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

Xác minh VNet đã có:

~~~bash
az network vnet show \
  --resource-group rg-network-prod \
  --name vnet-web-prod \
  --query "{id:id, name:name, location:location}" \
  --output json
~~~

Nếu VNet không tồn tại, dừng lại để xác nhận scope. **Không tạo VNet mới chỉ để che một lỗi chọn nhầm subscription**.

### 7.2. Tạo DDoS protection plan

Câu lệnh minh họa:

~~~bash
az network ddos-protection create \
  --resource-group rg-security-prod \
  --name ddos-plan-prod

# Lấy Resource ID của plan thay vì tự ghép chuỗi.
PLAN_ID=$(az network ddos-protection show \
  --resource-group rg-security-prod \
  --name ddos-plan-prod \
  --query id \
  --output tsv)

echo "$PLAN_ID"
~~~

Lệnh `az network ddos-protection create` tạo **tài nguyên plan có thể tính phí**. Chỉ thực thi khi có quyền và đã chấp thuận chi phí. Plan không bảo vệ một VNet chỉ bằng việc tồn tại; cần liên kết theo cơ chế Network Protection.

### 7.3. Liên kết DDoS protection plan với VNet

~~~bash
az network vnet update \
  --resource-group rg-network-prod \
  --name vnet-web-prod \
  --ddos-protection true \
  --ddos-protection-plan "$PLAN_ID"
~~~

Khi hoàn thành, VNet được cấu hình sử dụng DDoS plan cho phạm vi tài nguyên được hỗ trợ. Nếu gặp lỗi quyền, region, subscription hoặc plan không hợp lệ, phải kiểm tra nguyên nhân trước khi thử lại; không nên cấp Owner toàn subscription như cách khắc phục mặc định.

### 7.4. Xác nhận cấu hình

~~~bash
az network vnet show \
  --resource-group rg-network-prod \
  --name vnet-web-prod \
  --query "{name:name, ddosEnabled:enableDdosProtection, planId:ddosProtectionPlan.id}" \
  --output json
~~~

Kỳ vọng `ddosEnabled` là `true` và `planId` trỏ tới protection plan vừa tạo.

Có thể kiểm tra thêm bằng **Azure portal → Virtual networks → [VNet] → DDoS protection** hoặc trang thiết lập tương ứng trong giao diện hiện hành.

**Kiểm tra cấu hình không đồng nghĩa kiểm tra khả năng giảm thiểu thực tế:** thấy plan được liên kết chỉ xác nhận điều kiện cấu hình; cần telemetry và phương án thử nghiệm được phê duyệt để đánh giá vận hành.

### 7.5. Khi chọn IP Protection thay vì Network Protection

Với **DDoS IP Protection**, trọng tâm cấu hình là từng **public IP resource** được hỗ trợ. Trong Azure portal, tìm phần cấu hình DDoS protection của public IP và chọn chế độ phù hợp theo tùy chọn hiện có. Không dùng lệnh liên kết VNet tới plan của Network Protection để suy ra rằng một public IP ngoài phạm vi hỗ trợ đã được bật IP Protection.

Sau khi cấu hình, kiểm tra chính **public IP** ở tài nguyên đích, rồi đối chiếu hướng lưu lượng Internet thực tế. Dưới đây là lệnh đọc thông tin tổng thể của public IP:

~~~bash
az network public-ip show \
  --resource-group rg-network-prod \
  --name pip-appgw-prod \
  --output json
~~~

Xem SKU, địa chỉ, cấu hình DDoS (nếu được schema của tài nguyên/phiên bản hỗ trợ) và sự liên kết tới frontend của dịch vụ thực sự nhận lưu lượng. Các phiên bản API có thể biểu diễn thiết lập DDoS theo trường khác nhau; không suy ra trạng thái bảo vệ chỉ từ tên public IP.

### 7.6. Không xóa plan đang phục vụ workload

Nếu sử dụng một plan cho nhiều VNet, phải kiểm tra toàn bộ những VNet đang liên kết trước khi thay đổi hoặc xóa plan. Tắt/bỏ bảo vệ trên VNet production có thể làm thay đổi tư thế phòng thủ và điều khoản dịch vụ.

Đối với môi trường lab được phép dọn dẹp, hãy tháo liên kết khỏi các VNet theo hướng dẫn sản phẩm, xác minh không còn phụ thuộc và chỉ sau đó xóa plan. Kiểm tra phát sinh chi phí sau thực hành theo dữ liệu Cost Management. Đừng dùng tác vụ xóa hàng loạt trong một subscription chưa được giới hạn rõ.

## 8. Giám sát tấn công với Azure Monitor

Bảo vệ có hiệu quả vận hành khi nhóm có thể trả lời: **có tấn công hay không, bắt đầu lúc nào, lưu lượng bị lọc bao nhiêu, khách hàng có bị ảnh hưởng, và hệ thống đã phục hồi chưa?**

### 8.1. Các loại tín hiệu hữu ích

Với public IP/gói hỗ trợ tương ứng, những nhóm telemetry thường được dùng gồm:

| Nhóm tín hiệu | Dùng để trả lời | Lưu ý |
| --- | --- | --- |
| **DDoS attack status** | Public IP có đang được xác định ở trạng thái tấn công không? | Phụ thuộc metric có được phát hành cho tài nguyên không |
| **Inbound traffic / packet metrics** | Lưu lượng và tốc độ gói vào tăng mạnh khi nào? | So sánh với baseline và thời gian của ứng dụng |
| **Forwarded/dropped traffic trong mitigation** | Có bao nhiêu gói/lưu lượng được chuyển tiếp hoặc bị lọc? | Không đồng nhất “dropped” với lỗi ứng dụng |
| **DDoS protection notifications** | Khi nào có thông báo bắt đầu/kết thúc giảm thiểu? | Thường cần cấu hình diagnostic settings |
| **Mitigation reports** | Tổng hợp thông tin cuộc tấn công và giảm thiểu | Phụ thuộc loại log/gói được hỗ trợ |
| **Mitigation flow logs** | Các thông tin luồng lưu lượng trong lúc giảm thiểu | Cần cân nhắc dung lượng log và quyền truy cập |
| **Ứng dụng và gateway** | Latency, HTTP 5xx, saturation, success rate ra sao? | Phải đối chiếu để đánh giá tác động người dùng |

Trong Azure portal, có thể xem các metric liên quan tại public IP/Monitor. Tên metric chính xác, khả năng lọc chiều dữ liệu và mức cung cấp tùy tài nguyên/gói, do đó nên chọn từ danh sách metric thực tế thay vì tự tạo tên metric trong dashboard.

### 8.2. Cấu hình diagnostic settings

Ở public IP được bảo vệ theo loại dịch vụ hỗ trợ:

1. Mở **Diagnostic settings** ở tài nguyên nguồn hoặc cấu hình giám sát DDoS thích hợp.
2. Chọn những loại log DDoS được cung cấp, chẳng hạn **DDoSProtectionNotifications**, **DDoSMitigationReports** và **DDoSMitigationFlowLogs** khi chúng xuất hiện.
3. Chọn đích được tổ chức phê duyệt, ví dụ **Log Analytics workspace**, tài khoản lưu trữ hoặc Event Hubs theo khả năng tính năng.
4. Xác minh log thực sự xuất hiện sau khi có sự kiện thuộc loại đó; không có log mitigation lúc không bị tấn công có thể là hành vi bình thường.
5. Đặt lưu giữ, quyền truy cập và chi phí theo yêu cầu điều tra.

Các nhóm log có thể xuất hiện ở bảng/chế độ truy vấn khác nhau tùy pipeline. Một truy vấn KQL khởi đầu trong workspace đang dùng bảng `AzureDiagnostics` có thể là:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(7d)
| where Category in (
    "DDoSProtectionNotifications",
    "DDoSMitigationReports",
    "DDoSMitigationFlowLogs"
  )
| project TimeGenerated, ResourceId, Category
| order by TimeGenerated desc
~~~

Truy vấn này **chỉ chạy khi dữ liệu được đưa vào bảng AzureDiagnostics theo schema tương ứng**. Nếu workspace dùng bảng riêng hoặc chưa có log, cần kiểm tra danh sách tables, connector, diagnostic settings và tài liệu schema thực tế. Không nên cố tạo dữ liệu bằng cách phát sinh lưu lượng tấn công ngoài quy trình được phép.

### 8.3. Tạo cảnh báo phục vụ trực vận hành

Một quy trình cảnh báo mẫu:

- **Trigger:** public IP báo trạng thái đang chịu tấn công DDoS, hoặc xuất hiện notification về mitigation, tùy metric/log được hỗ trợ.
- **Điều kiện bổ sung:** kiểm tra mức độ nghiêm trọng và mức tác động khách hàng qua application metrics.
- **Action:** Azure Monitor Action Group thông báo SOC/NOC hoặc hệ thống incident.
- **Tương quan:** gắn public IP, VNet, subscription, endpoint ứng dụng và thời điểm UTC.
- **Đóng cảnh báo:** ghi nhận thời điểm kết thúc, phục hồi ứng dụng và những hành động được thực hiện.

Ví dụ thiết kế:

~~~text
Signal:     Metric "Under DDoS attack or not" (nếu được cung cấp)
Scope:      pip-appgw-prod
Condition:  Trạng thái được xác định là có tấn công
Action:     Thông báo nhóm SOC/NOC
Context:    Subscription, public IP, VNet, ứng dụng, UTC
Next:       Kiểm tra 5xx, latency, throughput và user impact
~~~

Đây là **mẫu logic**, không phải lệnh API/ARM có thể chạy nguyên văn. Khi tạo metric alert, cần chọn **metric và biểu thức điều kiện thực tế** trong Azure Monitor ở scope của public IP.

### 8.4. Vì sao chỉ số DDoS chưa đủ để đánh giá sự cố?

Kịch bản A: DDoS mitigation đang hoạt động, phần lớn traffic độc hại bị loại bỏ và HTTP success rate vẫn ổn định. Ở góc độ người dùng, hệ thống có thể vẫn hoạt động tốt.

Kịch bản B: Không có metric DDoS rõ ràng nhưng API timeout vì backend database quá tải. Vấn đề có thể do lỗi ứng dụng, tăng trưởng truy cập hợp lệ hoặc L7 flood; bật thêm L3/L4 protection không tự sửa được backend.

Muốn kết luận cần **cả dữ liệu chống DDoS lẫn SLI/SLO của ứng dụng**: tỷ lệ request thành công, p95/p99 latency, lỗi timeout, CPU, connection saturation, mức sử dụng database.

## 9. Quy trình ứng phó một sự kiện DDoS

Giả sử lúc 14:05 UTC, metric cho public IP `pip-appgw-prod` chuyển sang trạng thái đang chịu DDoS và khách hàng phản ánh timeout.

### Bước 1 — Triage và xác nhận phạm vi

- Ghi lại thời gian bắt đầu, public IP, ứng dụng, VNet, subscription, gói bảo vệ và người trực.
- Xác minh cảnh báo đến từ DDoS telemetry thật hay chỉ một ngưỡng CPU/network.
- Xem gateway/VM/application logs để biết người dùng hợp lệ có bị ảnh hưởng không.
- Đối chiếu các thay đổi hạ tầng gần thời điểm đó.

### Bước 2 — Xây dựng timeline

| Mốc UTC giả định | Quan sát | Giải thích cần kiểm chứng |
| --- | --- | --- |
| 14:00 | Request thành công bình thường | Baseline của ứng dụng |
| 14:05 | Lưu lượng vào public IP tăng mạnh | Có thể là DDoS hoặc sự kiện lưu lượng khác |
| 14:06 | Metric/notification DDoS cho thấy mitigation | Hạ tầng đang phân loại và xử lý lưu lượng |
| 14:07 | Một phần gói bị drop, latency tăng | Cần đối chiếu lượng hợp lệ và năng lực backend |
| 14:20 | Lưu lượng giảm, tỷ lệ lỗi trở lại bình thường | Có thể đã phục hồi, cần theo dõi tái diễn |

Timeline chỉ là ví dụ. Không gán chắc nguyên nhân cho từng mốc nếu chưa có bản ghi hỗ trợ.

### Bước 3 — Theo dõi hiệu quả giảm thiểu

Xem tương quan lưu lượng trước, trong và sau mitigation:

- Đường biểu đồ inbound traffic, forwarded/dropped, attack status.
- Ứng dụng còn xử lý request hợp lệ hay không.
- Có tín hiệu tấn công L7 trong WAF/application logs không.
- Sự cố có xảy ra ở nhiều public IP hoặc region không.
- Khách hàng bị ảnh hưởng ở mức nào, các tuyến/region có khác nhau không.

### Bước 4 — Phối hợp các nhóm

- **NOC/network team:** xác nhận ingress, routing, NSG, firewall, nguồn telemetry.
- **SOC/security team:** xem loại tấn công, mức độ, bằng chứng và hoạt động có liên quan.
- **App/SRE team:** đo SLO, tối ưu tài nguyên, kiểm tra autoscale, caching và ứng dụng.
- **Điều phối sự cố:** ghi tác động, truyền thông và xin phê duyệt thay đổi nếu cần.

Với gói và điều kiện hỗ trợ tương ứng, doanh nghiệp có thể liên hệ các kênh hỗ trợ/ứng phó DDoS của Microsoft theo quyền lợi dịch vụ và quy trình đã ký kết. Không nên mặc định mọi gói đều có cùng mức hỗ trợ chuyên biệt.

### Bước 5 — Hành động phù hợp với bằng chứng

Những biện pháp có thể cân nhắc:

- Giữ nguyên cấu hình DDoS Protection khi dịch vụ đang giảm thiểu và giám sát trạng thái.
- Tinh chỉnh WAF/rate limiting cho HTTP/HTTPS khi có bằng chứng L7 và đã xem xét false positive.
- Tăng khả năng chịu tải ứng dụng hoặc giảm truy vấn tốn kém ở backend khi cần, không dựa hoàn toàn vào autoscale.
- Hạn chế trực tiếp đường vào origin ngoài dự kiến; bảo đảm lưu lượng hợp lệ vẫn đi qua.
- Dùng quy trình thay đổi được phê duyệt cho firewall/route, tránh chặn diện rộng nhầm người dùng.

**Không tùy ý thay public IP, xóa gateway hoặc vô hiệu hóa toàn bộ Internet access giữa một đợt tấn công.** Các thay đổi này có thể gây gián đoạn lớn hơn và làm mất khả năng theo dõi.

### Bước 6 — Khôi phục và rút kinh nghiệm

Sau khi traffic và SLO ổn định, ghi lại:

1. Mốc phát hiện, bắt đầu/kết thúc mitigation, thời điểm dịch vụ phục hồi.
2. Public IP, nguồn dữ liệu, dashboard, alert và bản ghi liên quan.
3. Mức độ tác động, đặc trưng lưu lượng, phản ứng của từng lớp bảo vệ.
4. Hành động thực hiện, người phê duyệt, thay đổi cấu hình và kết quả.
5. Khoảng trống observability, quyền truy cập và đề xuất điều chỉnh.

Không đóng incident chỉ vì metric “under attack” chuyển về 0 nếu ứng dụng vẫn không đáp ứng SLO.

## 10. Kiểm chứng hiệu quả bảo vệ một cách an toàn

Kiểm thử DDoS khác với kiểm thử tải ứng dụng thông thường. **Không tự tạo lưu lượng flood vào IP public** chỉ để xem hệ thống có chặn được hay không. Việc đó có thể gây gián đoạn hoặc vi phạm chính sách sử dụng dịch vụ.

### Mục tiêu kiểm chứng cần đạt

Một kế hoạch kiểm chứng thực tế phải xác nhận:

- Đúng public IP, VNet và SKU đã được đưa vào phạm vi bảo vệ.
- Azure Monitor và Action Group nhận được tín hiệu như thiết kế.
- SOC/NOC biết xem dashboard, mở ticket và phối hợp.
- Ứng dụng có SLI/SLO và phép đo phục hồi độc lập với metric DDoS.
- Runbook chỉ rõ người quyết định thay đổi WAF, firewall, routing hoặc mở rộng hệ thống.
- Các thành phần không được bảo vệ đã được nhận diện và có phương án phòng vệ riêng.

### Kiểm thử không tạo lưu lượng tấn công

Có thể thực hiện ngay cả trong môi trường lab:

1. **Kiểm tra cấu hình** từ Azure portal/CLI và lập bảng các public IP thực sự được bảo vệ.
2. **Kiểm tra observability**: metric tồn tại ở scope phù hợp, diagnostic settings có đích và quyền cần thiết.
3. **Kiểm tra đường thông báo** bằng cơ chế test Action Group hoặc tạo một cảnh báo mô phỏng từ nguồn kiểm thử không gây tải.
4. **Diễn tập tabletop**: nhân sự nhận một tình huống giả định và giải thích cách điều tra theo runbook.
5. **Kiểm tra phục hồi ứng dụng** bằng những phép thử tải hợp lệ, riêng biệt, trong giới hạn được phê duyệt.

Nếu thực sự cần thử nghiệm giảm thiểu DDoS, chỉ sử dụng **quy trình, nhà cung cấp mô phỏng và hình thức thử được Microsoft hỗ trợ và chủ sở hữu dịch vụ phê duyệt**, trong cửa sổ thử nghiệm có điều phối. Không giả định mọi công cụ load test có thể mô phỏng DDoS hoặc chứng minh khả năng chống tấn công.

### Tiêu chí đánh giá sau diễn tập

| Tiêu chí | Câu hỏi đánh giá |
| --- | --- |
| Độ chính xác inventory | Có thiếu public IP/entrypoint nào trong phạm vi không? |
| Phát hiện | Metric/log có hiện đúng sự kiện được kỳ vọng không? |
| Thông báo | Đúng nhóm trực nhận cảnh báo và có đủ ngữ cảnh không? |
| Điều tra | Nhóm có phân biệt DDoS, HTTP flood và lỗi backend không? |
| Ứng phó | Ai được phép thay đổi, khôi phục và truyền thông? |
| Tác động | Có đo được mức phục hồi của người dùng hợp lệ không? |
| Chi phí | Có thể ước tính chi phí bảo vệ và các thành phần liên quan không? |

## 11. Tổ chức quyền truy cập và chi phí

### 11.1. Phân quyền tối thiểu

Việc xem metric, tạo alert, thay đổi DDoS plan, cập nhật VNet hoặc public IP có thể đòi hỏi **những quyền Azure RBAC khác nhau**.

Mô hình vận hành đề xuất:

| Nhóm | Nhu cầu | Phạm vi gợi ý |
| --- | --- | --- |
| Security/SOC | Xem alert, log, hỗ trợ điều tra | Read/monitoring trên resource và workspace liên quan |
| Network team | Quản trị VNet, public IP, DDoS plan | Quyền network và protection plan theo scope được phê duyệt |
| Application/SRE | Xem SLO, xử lý lỗi app và phối hợp | Quyền app/monitoring theo môi trường |
| Cost owner/FinOps | Xem báo cáo chi phí, kiểm tra budget | Quyền Cost Management phù hợp |

Một người đọc được biểu đồ DDoS **không cần mặc nhiên có quyền thay đổi** network configuration. Ngược lại, quyền Contributor trên một resource group không đồng nghĩa có thể liên kết tài nguyên ở resource group/subscription khác nếu thiếu quyền tại scope đó.

### 11.2. Các thành phần có thể phát sinh chi phí

- **DDoS Network Protection:** mô hình phí plan và các yếu tố tính phí bổ sung theo điều khoản hiện hành.
- **DDoS IP Protection:** mô hình phí theo public IP được bảo vệ và điều kiện dịch vụ.
- **Log Analytics/Azure Monitor:** lưu trữ, nạp log, truy vấn hoặc phát cảnh báo theo dịch vụ và cấu hình.
- **Application Gateway/WAF/Front Door:** tính phí riêng theo mô hình của sản phẩm.
- **Lưu lượng, năng lực ứng dụng và độ dự phòng:** autoscale, mạng, compute và lưu trữ có thể thay đổi chi phí trong sự cố.

Một số quyền lợi liên quan đến bảo vệ chi phí khi xảy ra DDoS hoặc hỗ trợ chuyên biệt có thể gắn với gói và điều kiện cụ thể. **Không coi mọi thiệt hại hoặc mọi chi phí tăng cao là tự động được bồi hoàn.** Kiểm tra hợp đồng, phạm vi đủ điều kiện, cách đăng ký/đề nghị và hồ sơ sự cố cần lưu.

Để dự toán:

1. Liệt kê các public IP đủ điều kiện và số VNet cần bảo vệ.
2. Chọn mô hình Network hoặc IP theo nhu cầu và tính năng.
3. Tra **Azure Pricing Calculator** và điều khoản ở region liên quan.
4. Xem thêm phí WAF/Front Door, monitoring và vận hành.
5. Thiết lập budget/alert trong **Microsoft Cost Management**.
6. Theo dõi biến động sau khi bật bảo vệ và khi tăng số lượng public IP.

### 11.3. Rủi ro khi thiết kế sai

| Sai lầm | Hệ quả |
| --- | --- |
| Bật Network Protection trên một VNet không chứa Internet ingress mục tiêu | Chi phí và tư thế bảo vệ có thể không phục vụ đúng hệ thống |
| Cho rằng bảo vệ mọi PaaS endpoint chỉ bằng một DDoS plan | Bỏ sót entrypoint thực tế hoặc gắn sai công nghệ |
| Chỉ bật DDoS L3/L4 mà bỏ WAF/giới hạn truy cập app | Thiếu phòng vệ khi HTTP/HTTPS bị lạm dụng |
| Không kiểm tra khả năng công khai của backend | Traffic có thể bỏ qua tầng edge dự kiến |
| Không có alert và thông tin người trực | Khó điều phối dù mitigation tự động hoạt động |
| Thay đổi firewall diện rộng khi hoảng loạn | Chặn nhầm khách hàng hợp lệ |
| Không kiểm soát phí plan và dữ liệu giám sát | Chi phí không được dự tính |
| Xóa plan/link khi đang dùng chung nhiều VNet | Thay đổi bảo vệ của workload khác ngoài ý định |

## 12. Bài thực hành phân tích kiến trúc

**Bối cảnh giả lập:** Một doanh nghiệp có hệ thống API thương mại trên Azure:

- `vnet-prod`: chứa Application Gateway với public IP `pip-appgw-prod`.
- Backend API dùng private IP trong subnet riêng.
- Azure SQL sử dụng Private Endpoint, không có truy cập public theo thiết kế.
- Front Door phục vụ nội dung tĩnh và chuyển một phần truy cập tới hệ thống ứng dụng.
- Nhóm quản trị muốn giảm rủi ro DDoS và theo dõi tác động tới người dùng.

### Phần A — Xác định đường vào và cơ chế bảo vệ

Điền phương án sơ bộ:

| Đối tượng | Có Internet ingress? | Phòng vệ ưu tiên |
| --- | --- | --- |
| `pip-appgw-prod` | Có | DDoS Network/IP Protection nếu đủ điều kiện; WAF |
| VM/API private IP | Không trực tiếp | Bảo vệ ingress upstream, NSG, auth và SLO |
| SQL qua Private Endpoint | Không trực tiếp | Private network access, auth và giám sát |
| Front Door endpoint | Có | Bảo vệ biên và WAF của Front Door theo cấu hình |

Giải thích vì sao **một DDoS plan gắn `vnet-prod` không tự động biến Front Door endpoint thành một public IP thuộc VNet**.

### Phần B — Đọc cấu hình và tạo phương án

Với quyền đọc, học viên chạy:

~~~bash
az account show \
  --query "{subscription:name, id:id}" \
  --output json

az network vnet show \
  --resource-group rg-network-prod \
  --name vnet-prod \
  --query "{name:name, enabled:enableDdosProtection, plan:ddosProtectionPlan.id}" \
  --output json

az network public-ip show \
  --resource-group rg-network-prod \
  --name pip-appgw-prod \
  --output json
~~~

Các tên là ví dụ, cần thay bằng tên thực tế trong lab có quyền. Nếu tài nguyên không tồn tại, **không tạo tài nguyên ngoài phạm vi bài thực hành**; dùng bảng giả lập dưới đây để suy luận:

~~~json
{
  "vnet": "vnet-prod",
  "enableDdosProtection": true,
  "ddosProtectionPlan": {
    "id": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-security-prod/providers/Microsoft.Network/ddosProtectionPlans/ddos-plan-prod"
  },
  "publicIp": "pip-appgw-prod",
  "publicIpSku": "Standard",
  "ingress": "Application Gateway"
}
~~~

**Câu hỏi:**

1. Những dữ liệu nào cho thấy VNet đã được cấu hình Network Protection?
2. Tại sao vẫn cần kiểm tra public IP đang thực sự được Application Gateway dùng?
3. Một VM private IP trong `vnet-prod` có được tự động gắn public IP hay không?
4. Front Door và endpoint SQL private nên được đánh giá theo phạm vi bảo vệ nào?

**Gợi ý:** `enableDdosProtection=true` và plan ID là bằng chứng về cấu hình VNet, nhưng không chứng minh toàn bộ lưu lượng hệ thống đi qua public IP được bảo vệ.

### Phần C — Điều tra một biểu đồ mô phỏng

Nhóm quan sát số liệu sau trong sự kiện giả định:

| Thời điểm (UTC) | Lưu lượng vào public IP | Trạng thái DDoS | HTTP 5xx | p95 latency |
| --- | --- | --- | --- | --- |
| 09:00 | Bình thường | Không | 0,2% | 180 ms |
| 09:05 | Tăng mạnh | Có | 1,0% | 300 ms |
| 09:10 | Cao, có mitigation | Có | 1,5% | 420 ms |
| 09:20 | Trở lại gần baseline | Không | 0,3% | 190 ms |

Từ bảng trên:

1. Nhóm đã có tín hiệu gì về DDoS và khả năng ảnh hưởng khách hàng?
2. Có thể khẳng định toàn bộ lưu lượng bất thường bị chặn thành công không?
3. Cần bổ sung metric hoặc log nào để đánh giá tác dụng của mitigation?
4. Nếu HTTP 5xx tiếp tục tăng sau 09:20 dù attack status về 0, bước điều tra tiếp theo là gì?

**Đáp án tham khảo:**

- Có sự trùng thời gian giữa trạng thái DDoS và tăng lỗi/latency; cần xác minh tương quan bằng dữ liệu gốc.
- Chưa. Cần forwarded/dropped telemetry, mitigation report và dữ liệu application để đánh giá chất lượng lọc.
- Thu thập log DDoS, lưu lượng, số gói bị lọc/chuyển tiếp, WAF/application/gateway logs, request success rate.
- Điều tra app/backend, kết nối DB, saturation và các thay đổi hệ thống; không nên coi mọi lỗi còn lại đều do DDoS.

### Phần D — Lập runbook 5 bước

Hãy viết runbook ngắn dùng khi **public IP sản xuất được báo đang chịu DDoS**:

1. Xác nhận tài nguyên và thời điểm bắt đầu.
2. Kiểm tra DDoS status cùng SLI/SLO của ứng dụng.
3. Kiểm tra phát hiện L7 và khả năng backend quá tải.
4. Thông báo đúng nhóm, phê duyệt các thay đổi cần thiết.
5. Xác nhận phục hồi, lưu timeline và cập nhật bài học.

Bài thực hành tập trung vào **quan sát và quyết định**, không phát sinh lưu lượng DDoS thật.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Azure DDoS Protection có thay thế được WAF khi ứng dụng bị tấn công bằng rất nhiều HTTP request hợp lệ về cú pháp không?

**Trả lời:** Không. DDoS Protection tập trung giảm thiểu L3/L4; bảo vệ L7 cần WAF/rate limiting và thiết kế ứng dụng tùy hành vi.

**Câu 2.** Doanh nghiệp đã bật DDoS Network Protection trên `vnet-prod`. Một website chạy hoàn toàn phía sau Front Door có đương nhiên nằm trong phạm vi plan ấy không?

**Trả lời:** Không thể kết luận như vậy. Front Door là dịch vụ edge với kiến trúc bảo vệ riêng; phải xác định thực tế đường ingress và origin.

**Câu 3.** Sự khác biệt chính giữa Network Protection và IP Protection là gì?

**Trả lời:** Network Protection quản trị theo VNet thông qua protection plan cho các public IP được hỗ trợ; IP Protection được cấu hình theo từng public IP đủ điều kiện. Khả năng và phí thực tế phải đối chiếu gói hiện hành.

**Câu 4.** Một public IP đã được bảo vệ nhưng ứng dụng vẫn trả HTTP 503 vì database quá tải. Có nghĩa DDoS Protection không hoạt động không?

**Trả lời:** Không nhất thiết. Cần xem metric DDoS cùng application metrics; 503 có thể do vấn đề tầng ứng dụng hoặc tài nguyên backend, không phải cơ chế lọc L3/L4.

**Câu 5.** Vì sao nên bật diagnostic settings và alert ngay từ trước khi có tấn công?

**Trả lời:** Để khi xảy ra sự kiện, nhóm có tín hiệu và dữ liệu truy vết kịp thời. Chỉ tạo log/alert sau sự cố có thể bỏ lỡ dữ liệu không được lưu trước đó.

**Câu 6.** Có nên dùng công cụ tạo flood Internet để kiểm thử một public IP sản xuất?

**Trả lời:** Không. Chỉ thử nghiệm theo hình thức được nhà cung cấp hỗ trợ, đúng quy trình phê duyệt, có điều phối và kiểm soát tác động.

**Câu 7.** Vì sao cần kiểm tra chi phí trước khi tạo protection plan?

**Trả lời:** Các gói bảo vệ có mô hình phí riêng, bên cạnh chi phí monitoring và kiến trúc ứng dụng. Kế hoạch triển khai phải tính đúng tài nguyên đủ điều kiện và phạm vi cần bảo vệ.

## Ghi nhớ

- **DDoS** đe dọa tính sẵn sàng; các cuộc tấn công có thể ở L3/L4, L7 hoặc kết hợp.
- **Azure DDoS Protection** tập trung phòng vệ L3/L4 cho **public IP Azure được hỗ trợ**; không thay thế WAF, NSG, firewall hoặc thiết kế ứng dụng ổn định.
- **Network Protection** gắn với VNet qua protection plan; **IP Protection** tập trung vào từng public IP phù hợp. Phải xác định đúng Internet ingress.
- Theo dõi **attack status, mitigation metrics/logs và SLO ứng dụng** cùng lúc để đánh giá tác động thực tế.
- Chuẩn bị **alert, phân quyền, runbook và dự toán** trước sự cố; kiểm thử qua kênh hợp lệ và có phê duyệt.
- Trong một cuộc tấn công, ưu tiên giữ dịch vụ hoạt động, dựa vào bằng chứng để phối hợp và thay đổi cấu hình, rồi đánh giá lại sau khi khôi phục.
