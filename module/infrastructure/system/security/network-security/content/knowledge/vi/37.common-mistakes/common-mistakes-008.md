# Dùng chung một security group cho mọi workload

Trong kiến trúc mạng đám mây, **security group (SG)** là cơ chế kiểm soát lưu lượng được gắn với tài nguyên mạng hoặc workload theo mô hình của nhà cung cấp. Khi triển khai nhanh một môi trường, nhiều nhóm chọn một SG dùng chung, mở đủ các cổng để mọi thành phần hoạt động, rồi gắn nó cho web server, API, database, bastion, batch worker và cả môi trường thử nghiệm. Hệ thống có thể chạy ngay, nhưng nhóm SG này dần tích lũy quyền truy cập của **tất cả workload**.

Đây là một sai lầm phổ biến của chương **Sai lầm thường gặp** trong module **SECURITY_NETWORK_SECURITY**. Nó làm yếu **least privilege**, **network segmentation** và khả năng xác minh ranh giới tin cậy. Trong trường hợp một workload bị xâm nhập, các luồng được mở rộng quá mức có thể tạo điều kiện cho truy cập ngang (lateral movement), tiếp cận dịch vụ dữ liệu và mặt phẳng quản trị. Mục tiêu bài học là hiểu cơ chế, nhận diện sai lầm và thay thế bằng thiết kế rule bám theo **luồng nghiệp vụ được phép**, trong khi vẫn giữ được hoạt động bình thường của hệ thống.

> **Phạm vi thuật ngữ:** phần giải thích chi tiết về phép cộng quyền của nhiều SG, luật stateful và tham chiếu SG lấy mô hình AWS VPC làm ví dụ. Azure Network Security Group (NSG), Google Cloud VPC firewall rule và các giải pháp microsegmentation có cách gắn policy, thứ tự xét rule, hướng lưu lượng và điều kiện đánh giá khác nhau. Không tự áp dụng nguyên xi các đặc tính AWS cho mọi nền tảng.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao một SG dùng chung cho mọi workload thường vi phạm nguyên tắc cấp quyền tối thiểu.
2. Mô tả tác động của các rule allow dùng chung đối với bề mặt tấn công, quan hệ phụ thuộc và sự cố lan truyền ngang.
3. Phân biệt **SG được chia sẻ vì các workload cùng vai trò** với **SG bị dùng chung tùy tiện giữa các vai trò và vùng tin cậy khác nhau**.
4. Thiết kế ma trận nguồn–đích–dịch vụ–hành động, rồi ánh xạ sang SG theo vai trò và môi trường.
5. Hiểu cơ chế hợp quyền khi gắn nhiều SG vào một network interface trong AWS và giới hạn của SG đối với kiểm soát danh tính, DNS, L7.
6. Lập kế hoạch tách SG theo từng bước, kiểm thử luồng hợp lệ và luồng bị cấm, có rollback và giám sát.
7. Định nghĩa owner, căn cứ phê duyệt, quy trình IaC và các phép kiểm tra drift để ngăn sai lầm tái diễn.

## 2. Security group kiểm soát điều gì?

Ở mức khái quát, một SG quy định những kết nối mạng được phép đi vào hoặc đi ra đối với tài nguyên thuộc phạm vi áp dụng. Một rule thường mô tả:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Direction | Lưu lượng inbound hay outbound | Ingress từ ứng dụng tới database |
| Source / destination | CIDR, địa chỉ hoặc SG được phép theo nền tảng | App SG truy cập DB SG |
| Protocol | TCP, UDP hoặc giao thức được hỗ trợ | TCP |
| Port / port range | Cổng dịch vụ của luồng được phép | 443, 5432 |
| Scope | Tài nguyên, interface, tenant/VPC và môi trường áp dụng | Nhóm máy API production |
| Owner / purpose | Chủ dịch vụ và lý do kết nối cần tồn tại | API cần truy vấn PostgreSQL |

### 2.1. Đặc điểm thường gặp của AWS VPC security group

Với SG của **AWS VPC**:

- SG hoạt động như một bộ lọc **stateful**: phản hồi thuộc phiên kết nối đã được phép thường được chấp nhận theo connection tracking, dù chiều phản hồi không có rule mở riêng tương ứng.
- Rule SG là các **quy tắc cho phép**; SG không có rule deny tường minh. Khi không có rule phù hợp, traffic mới sẽ bị chặn theo mặc định đối với chiều đó.
- Khi một network interface được gắn **nhiều SG**, quyền của các SG được **hợp lại (union)**. SG thứ hai không thể dùng để thu hẹp một quyền allow rộng đã được SG thứ nhất mở.
- SG có thể tham chiếu một SG khác làm nguồn/đích trong các trường hợp được nền tảng hỗ trợ. Tham chiếu này giúp quản lý membership theo vai trò mà không phải duy trì thủ công từng địa chỉ IP.
- Rule áp ở cấp ENI/tài nguyên được hỗ trợ; việc gắn SG cho một instance không tự giới hạn mọi loại giao tiếp control plane hay lưu lượng ngoài phạm vi ENI.
- SG mới hoặc SG mặc định có thể có các outbound rule cho phép rộng theo cách tạo và cấu hình. Vì vậy cần **kiểm tra trạng thái rule thực tế**, đặc biệt là egress, thay vì suy từ tên SG.

Ví dụ, một máy API gắn hai SG:

~~~text
SG api-restricted:
  ALLOW inbound tcp/8443 from ALB-SG
  ALLOW outbound tcp/5432 to DB-SG

SG all-workloads:
  ALLOW inbound tcp/22 from USER-SUBNET
  ALLOW inbound tcp/5432 from VPC-CIDR
  ALLOW outbound all to 0.0.0.0/0

Quyền hiệu lực trên máy API = hợp các quyền ALLOW của cả hai SG.
~~~

Dù SG **api-restricted** được thiết kế rất chặt, **all-workloads** vẫn mở các quyền rộng. Gắn một SG chặt hơn **không triệt tiêu** quyền của SG rộng đang tồn tại. Đây là điểm quan trọng khi di chuyển dần từ một nhóm dùng chung sang nhiều nhóm chuyên biệt.

### 2.2. Những điều SG không tự giải quyết

SG không phải hệ thống xác thực người dùng, phân quyền API, firewall ứng dụng, DLP hay IDS/IPS. Cho phép TCP/5432 không chứng minh truy vấn PostgreSQL sẽ thành công; nó chỉ cho phép đường kết nối tương ứng theo semantics nền tảng. Cần bảo vệ bằng xác thực cơ sở dữ liệu, mã hóa, IAM, quản lý secret và ghi log ở các tầng tiếp theo.

SG cũng thường không đưa ra quyết định trực tiếp theo **tên miền đầy đủ (FQDN)** như một secure web gateway chuyên dụng, không nhận diện mọi API route và không thay thế bộ kiểm soát egress ở tầng ứng dụng. Với Azure hoặc GCP, nên đọc riêng tài liệu của nền tảng thay vì coi các đối tượng có tên gần giống là SG hoạt động giống hệt nhau.

## 3. Sai lầm “một SG cho tất cả” xuất hiện như thế nào?

Tình huống giả định: một dự án ban đầu có ba máy, nên nhóm vận hành tạo SG **shared-prod** cho cả web, API và database. Khi thiếu kết nối, họ mở thêm một rule. Sau đó hệ thống có thêm batch worker, bastion, log forwarder, cache, máy CI và dịch vụ thử nghiệm. Mỗi nhóm gặp lỗi kết nối lại xin mở thêm cổng vào **shared-prod**.

~~~text
Ban đầu:
  Web + API + DB -> shared-prod: tcp/443, tcp/5432

Sau nhiều thay đổi:
  Web + API + DB + Batch + Bastion + CI + Cache -> shared-prod
  Inbound: 22, 443, 5432, 6379, 8080, ...
  Outbound: ALL
  Nguồn: VPC CIDR, VPN CIDR, partner CIDR, ...
~~~

Ở thời điểm đầu, một rule có thể thực sự chỉ phục vụ API. Nhưng khi có thêm workload mới gắn cùng SG, **workload mới được hưởng các quyền của rule cũ**, kể cả khi không có nhu cầu sử dụng các cổng đó. Mặt khác, mỗi rule bổ sung cho workload mới lại làm tăng quyền của **mọi workload đã gắn nhóm**.

Sự mở rộng này tạo ra **policy coupling**: thay đổi để hỗ trợ một hệ thống có thể tác động hàng chục hệ thống khác. SG trở thành một tập quyền không còn phản ánh kiến trúc ứng dụng.

### 3.1. Dấu hiệu nhận biết

- Tên nhóm mang tính chung chung như all, common, shared, default, universal nhưng thực tế gắn với nhiều role khác nhau.
- Rule có dải cổng rộng hoặc toàn bộ protocol; source chứa VPC-wide CIDR, nhiều subnet lớn hoặc 0.0.0.0/0 và ::/0 không có biện minh.
- Một SG được gắn cho cả web/public, application/private, database và quản trị.
- Rule database hoặc SSH được cấu hình chỉ để sửa lỗi kết nối của một workload, nhưng được áp cho toàn bộ môi trường.
- Cùng SG được dùng cho production và non-production qua một mô hình quản lý rối; mặc dù một SG AWS nằm trong VPC cụ thể, các bản sao rule mở rộng ở nhiều môi trường vẫn có thể tạo sự phụ thuộc quản trị.
- Không có owner cho từng luồng; không ai biết rule phục vụ ứng dụng nào.
- Gỡ một rule “không sử dụng” gây lỗi bất ngờ ở hệ thống khác.
- Trong IaC, một biến kiểu global_security_group_id được truyền cho phần lớn các module mà không phân loại workload.

## 4. Hậu quả bảo mật và vận hành

| Tác động | Chuỗi nguyên nhân | Hệ quả |
| --- | --- | --- |
| Lateral movement | Một host ít tin cậy được phép kết nối tới cổng nội bộ của nhiều host | Workload bị xâm nhập có thêm đường tiếp cận dịch vụ khác |
| Mở rộng bề mặt tấn công | Cho phép mọi workload nhận traffic trên các cổng vốn chỉ một dịch vụ cần | Cổng quản trị, cache, database dễ bị thăm dò từ vùng không phù hợp |
| Blast radius lớn | Sửa SG chung ảnh hưởng tất cả interface gắn SG | Rule sai có thể mở rộng quyền hoặc chặn hàng loạt workload |
| Không thực thi least privilege | Quyền được cấp theo tập hợp nhu cầu của cả dự án | Không thể giải thích vì sao một workload có quyền nhất định |
| Drift và ngoại lệ khó quản lý | Các rule tạm trộn trong nhóm chung | Khó đặt expiry và thu hồi quyền theo từng ứng dụng |
| Điều tra chậm | Một rule có nhiều workload nhưng không có owner rõ | SOC khó truy nguồn, khó đánh giá traffic hợp lệ |
| Khó tách môi trường | Web, API, DB hoặc staging/prod dùng cùng mẫu rule rộng | Lỗi kiến trúc lặp lại khi mở rộng dự án |
| Rủi ro triển khai | Bổ sung hoặc xóa rule trên nhóm đang dùng chung | Thay đổi nhỏ có thể ảnh hưởng một số lượng lớn hệ thống |

**Blast radius** trong trường hợp này là tập workload chịu tác động khi SG bị cấu hình sai, bị gắn nhầm hoặc một trong các workload đang được cho phép kết nối bị xâm nhập. Blast radius phụ thuộc **đường mạng, dịch vụ đang lắng nghe, IAM và kiểm soát tầng khác**; không thể khẳng định các host đều bị chiếm quyền chỉ vì chúng cùng SG.

## 5. Ví dụ: một workload bị xâm nhập có thể tác động tới đâu?

Giả sử môi trường có bốn nhóm:

| Workload | Chức năng | Đường truy cập thực sự cần |
| --- | --- | --- |
| ALB/public entry | Nhận HTTPS từ người dùng | Internet → ALB TCP/443 |
| API service | Xử lý yêu cầu ứng dụng | ALB → API TCP/8443; API → DB TCP/5432 |
| Database | Lưu dữ liệu nghiệp vụ | Chỉ API → DB TCP/5432; backup có luồng riêng |
| Bastion/management | Truy cập quản trị được kiểm soát | VPN → Bastion SSH; Bastion → host quản trị đúng cổng |

Nếu tất cả bốn workload dùng SG **shared-prod** với inbound 22, 443, 5432, 8443 từ mọi subnet ứng dụng và outbound rộng, một web/API host bị lộ quyền chạy code có thể **thử kết nối** tới những endpoint nội bộ mà lẽ ra nó không cần biết đến.

Cần phân biệt:

- **Network reachability:** SG và routing cho phép gói tin đi tới cổng.
- **Service exposure:** có dịch vụ thực sự lắng nghe trên cổng đó.
- **Authentication/authorization:** có thể đăng nhập hoặc thực thi hành động hay không.
- **Compromise:** có thực sự chiếm quyền hoặc truy xuất dữ liệu không.

Dùng chung SG có thể mở rộng hai lớp đầu; nó không tự chứng minh hai lớp sau đã bị phá vỡ. Vì vậy báo cáo nên nói đúng là **“luồng trái chính sách có thể tiếp cận ở tầng mạng”** nếu đó là kết quả được xác minh.

## 6. Chia sẻ SG khi nào là hợp lý?

**Không phải mọi trường hợp một SG gắn nhiều tài nguyên đều sai.** Vấn đề là gộp các tài nguyên có **nhu cầu truy cập và mức tin cậy khác nhau**.

Một SG có thể hợp lý khi gắn cho nhiều instance hoặc pod node thuộc **cùng vai trò dịch vụ, cùng môi trường, cùng chính sách và cùng vòng đời**. Ví dụ, 20 worker API cùng chạy một bản triển khai và cần giống hệt các luồng ALB → API, API → DB, API → DNS. Dùng chung SG cho nhóm API có thể giảm số policy và bảo đảm chúng nhất quán.

Ngược lại, một SG gắn cả bastion, DB, public web và batch worker thường là dấu hiệu sai ranh giới. Hai workload có cùng cổng TCP/443 cũng không nhất thiết nên chia sẻ SG: một workload nhận request Internet, workload kia chỉ gọi API nội bộ; hướng traffic và nguồn/đích tin cậy khác nhau.

### 6.1. Tiêu chí đánh giá trước khi dùng chung

1. Các workload có cùng trust zone, môi trường, purpose và mức nhạy cảm không?
2. Inbound và outbound **tối thiểu cần thiết** có giống nhau không?
3. Chúng có cùng owner, quy trình phê duyệt và chu kỳ thay đổi không?
4. Khi thêm một rule, tất cả workload gắn SG có thực sự cần quyền đó không?
5. Khi một workload bị xâm nhập, policy có ngăn được những đường ngang không cần thiết không?
6. Nhóm có thể di chuyển workload hoặc thu hồi rule mà không ảnh hưởng dịch vụ khác không?

Nếu câu trả lời không rõ, hãy tách SG theo **security role/service boundary** trước khi mở thêm quyền.

## 7. Mô hình thiết kế đúng: một tập policy theo vai trò

Một mô hình đơn giản cho ứng dụng ba tầng là:

~~~mermaid
flowchart LR
    Internet["Người dùng Internet"] -->|"HTTPS 443"| ALB["ALB - SG edge"]
    ALB -->|"HTTPS 8443"| API["API - SG api"]
    API -->|"PostgreSQL 5432"| DB["DB - SG database"]
    VPN["VPN quản trị"] -->|"SSH 22"| BA["Bastion - SG bastion"]
    BA -.->|"Chỉ cổng quản trị đã duyệt"| API
    BA -.->|"Chỉ khi có nhu cầu"| DB
    DB -.->|"Luồng backup đã duyệt"| BK["Backup service"]
~~~

Mô hình này cho phép phân biệt chính xác luồng:

| Nguồn | Đích | Giao thức | Quyết định | Owner/giải thích |
| --- | --- | --- | --- | --- |
| Internet | ALB | TCP/443 | ALLOW | Public HTTPS theo thiết kế ứng dụng |
| ALB SG | API SG | TCP/8443 | ALLOW | Ứng dụng nhận request từ ALB |
| API SG | DB SG | TCP/5432 | ALLOW | API truy cập PostgreSQL |
| Internet | DB SG | TCP/5432 | DENY theo mặc định | Không có truy cập DB công khai |
| Web/guest subnet | Bastion SG | TCP/22 | DENY theo mặc định | Chỉ VPN quản trị mới được vào bastion |
| VPN quản trị | Bastion SG | TCP/22 | ALLOW có điều kiện | Cần IAM/MFA, giám sát và approval |
| API SG | Bất kỳ đích Internet | ALL | Không mặc định cho phép | Xác định riêng nhu cầu egress |
| Batch SG | DB SG | TCP/5432 | Chỉ khi nghiệp vụ yêu cầu | Một luồng độc lập, có owner và review |

Bảng là **ma trận luồng logic**, không phải file cấu hình triển khai cho một nhà cung cấp. SG AWS có rule allow và implicit deny; trong mô hình AWS, các hàng DENY ở đây thường có nghĩa **không tạo ALLOW tương ứng**, đồng thời phải kiểm tra những SG khác, đường routing và lớp kiểm soát bổ sung.

### 7.1. Đặt tên theo vai trò thay vì đặt theo tên dự án chung

Tên gợi ý:

~~~text
prod-public-alb
prod-orders-api
prod-orders-db
prod-batch-reconcile
prod-admin-bastion
nonprod-orders-api
nonprod-orders-db
~~~

Tên là một phần của quản trị, nhưng **không phải bằng chứng bảo mật**. Cần kiểm tra những rule thực sự tồn tại, những network interface đang gắn SG và các đối tượng nguồn/đích mà rule tham chiếu.

### 7.2. Ranh giới quan trọng hơn số lượng SG

Không đặt mục tiêu “mỗi máy một SG” một cách máy móc vì có thể gây bùng nổ chính sách, trùng lặp và mất khả năng quản trị. Đặt mục tiêu **mỗi tập workload có nhu cầu truy cập tương đương một policy dễ giải thích và có owner rõ**. Một ứng dụng lớn có thể cần nhiều SG theo role; nhiều instance đồng vai trò có thể dùng một SG.

## 8. Tham chiếu SG có tác dụng gì?

Trong AWS, rule có thể tham chiếu SG của nguồn/đích theo các trường hợp mà AWS hỗ trợ. Với luồng **API → DB**, rule inbound của DB có thể sử dụng **source SG = api**, thay vì nhập một danh sách IP cố định của từng máy API.

Lợi ích:

- Scale số lượng instance API mà không phải sửa danh sách IP thủ công.
- Quyền được nối với nhóm vai trò, giảm rủi ro IP tái sử dụng.
- Đọc rule dễ hơn: “DB nhận PostgreSQL từ api-sg”, thay vì từ toàn bộ VPC CIDR.
- Tách trách nhiệm: owner của API yêu cầu luồng, owner DB phê duyệt, nhóm mạng triển khai.

**Cảnh báo:** tham chiếu SG **không biến SG thành danh tính người dùng đáng tin tuyệt đối**. Một ENI được gắn thêm vào api-sg có thể mở rộng tập nguồn được phép. Việc gắn/tháo SG, sửa rule, đổi tag hoặc tạo workload mới cần IAM, IaC review và giám sát. Tham chiếu cũng có giới hạn theo VPC/peering/kết nối giữa các mạng, nên phải kiểm tra hỗ trợ thực tế của nền tảng.

Không cho rằng rule inbound tham chiếu SG tự tạo ra egress rule ở nguồn. Trong thiết kế egress hạn chế, phải bảo đảm **cả chiều outbound nguồn và inbound đích** cho phép phiên mới. Phản hồi của phiên đã cho phép được xử lý theo cơ chế stateful của nền tảng.

## 9. Ví dụ cấu hình định hướng (AWS Terraform)

Ví dụ HCL sau chỉ minh họa **luồng PostgreSQL giữa SG của API và SG của DB**. Các SG, VPC, quyền egress và nguồn hạ tầng khác phải được xác định trong bản triển khai thực tế. Không coi snippet này là module hoàn chỉnh có thể áp dụng trực tiếp lên production.

~~~hcl
# Ví dụ AWS provider sử dụng tài nguyên rule riêng.
# Không dùng đồng thời inline rule và dedicated rule resource
# cho cùng một security group khi điều đó tạo xung đột quản lý.

resource "aws_security_group" "api" {
  name        = "prod-orders-api"
  description = "Application tier for Orders API"
  vpc_id      = var.vpc_id

  tags = {
    Application = "orders"
    Environment = "prod"
    Owner       = "orders-platform"
  }
}

resource "aws_security_group" "db" {
  name        = "prod-orders-db"
  description = "Database tier for Orders API"
  vpc_id      = var.vpc_id

  tags = {
    Application = "orders"
    Environment = "prod"
    Owner       = "orders-data"
  }
}

# DB nhận kết nối từ các ENI thuộc SG của API,
# chỉ trên cổng PostgreSQL.
resource "aws_vpc_security_group_ingress_rule" "db_from_api" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.api.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "Approved API to DB access"
}

# Chỉ dùng khi thiết kế API hạn chế egress.
# Dù DB ingress được phép, API outbound vẫn phải được xét.
resource "aws_vpc_security_group_egress_rule" "api_to_db" {
  security_group_id            = aws_security_group.api.id
  referenced_security_group_id = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "API outbound to PostgreSQL"
}
~~~

Để hoàn chỉnh cấu hình phải bổ sung luồng ALB → API, DNS/NTP/observability, backup, health check và các dependency hợp lệ của ứng dụng; loại bỏ egress mặc định quá rộng nếu chính sách yêu cầu giới hạn, theo đúng semantics và phiên bản provider. Cũng cần kiểm tra các SG khác cùng gắn lên ENI. Snippet **không cấu hình xác thực DB**, IAM, KMS, secret rotation hoặc backup.

### 9.1. Điều kiện kiểm chứng của ví dụ

- Instance/API ENI chỉ được gắn những SG theo thiết kế; không còn SG all-workloads làm rộng quyền.
- DB ENI không đồng thời gắn SG mở PostgreSQL cho toàn VPC hoặc Internet.
- API có thể kết nối DB trên TCP/5432; nguồn web/guest không được tiếp cận DB trên cùng cổng nếu không có quyền.
- Các dependency khác của API được xác định, không ngắt DNS, health check hoặc khả năng lấy secret hợp lệ.
- Rule được quản lý ở một nguồn IaC rõ ràng; không trộn nhiều cơ chế quản lý dẫn tới drift.

## 10. Ingress và egress đều phải được thiết kế

Nhiều dự án chỉ siết inbound và để outbound là **ALLOW all**. Điều đó có thể là lựa chọn tạm thời có phê duyệt, nhưng thường không đáp ứng least privilege cho database, secret store, workload xử lý dữ liệu nhạy cảm hoặc môi trường có yêu cầu DLP/egress control.

Cần mô tả **đích outbound hợp lệ** cho từng vai trò:

| Workload | Outbound cần xác nhận | Hướng tiếp cận |
| --- | --- | --- |
| Public ALB | Tới target API/health check theo cổng cụ thể | Giới hạn tới API SG/đích đã được duyệt |
| API | DB, cache, DNS, identity/secrets và dịch vụ nghiệp vụ | Allow theo dependency thực tế, bổ sung proxy/endpoints khi cần |
| DB | Backup, logging, replication và dịch vụ vận hành | Không mở Internet toàn bộ khi không có nhu cầu |
| Batch worker | Queue, DB hoặc object storage theo job | Tách khỏi quyền của API, gắn owner cho từng flow |
| Bastion | Chỉ các endpoint quản trị được phép và log/audit | Không biến bastion thành cầu nối không giới hạn |
| Telemetry agent | Log collector/metrics endpoint | Duy trì đường giám sát qua các vùng bảo vệ |

Khi giới hạn egress, phải khảo sát những kết nối ít thấy như DHCP/DNS, NTP, package mirrors, certificate revocation, metadata service, secret manager, container registry và private cloud endpoints tùy nền tảng. Mỗi dependency cần có căn cứ và kiểm soát thích hợp.

**SG không thay thế firewall ứng dụng/egress gateway để quản lý domain hoặc nội dung tải ra ngoài.** Tại cloud có private endpoint, endpoint policy, DNS policy và dịch vụ giám sát khác, cần phối hợp để tránh cho phép IP rộng chỉ vì nhu cầu truy cập một API.

## 11. Phân biệt security group với subnet, route và NACL

Một thiết kế mạng an toàn thường kết hợp nhiều lớp:

- **Subnet/route:** quyết định đường đi và phạm vi định tuyến; tài nguyên cùng subnet không mặc nhiên có cùng quyền truy cập theo SG.
- **Security group:** kiểm soát kết nối tại tài nguyên/ENI, thường stateful trong AWS.
- **Network ACL:** kiểm soát tại subnet theo cơ chế nền tảng, có thể có deny tường minh và xử lý stateless trong AWS.
- **Firewall/proxy/IDS/IPS:** kiểm tra chính sách thêm ở các ranh giới, nội dung hoặc hành vi bất thường.
- **IAM, workload identity và ứng dụng:** xác nhận ai là người/dịch vụ đang truy cập và được làm gì.

Chỉ tách subnet mà vẫn dùng một SG quá rộng không đủ tạo least privilege. Chỉ tách SG nhưng route cho phép đi qua một đường VPN hoặc TGW mà không áp đúng chính sách cũng có thể tạo quyền ngoài dự kiến. Đánh giá nên xem **toàn bộ đường đi end-to-end**, kể cả VPC peering, Transit Gateway, cloud load balancer, NAT và network virtual appliance.

## 12. Những khác biệt cần lưu ý giữa các nền tảng

| Nền tảng / cơ chế | Điểm cần phân biệt | Hệ quả với thiết kế |
| --- | --- | --- |
| AWS VPC SG | Stateful, rule allow, gắn ENI/tài nguyên phù hợp; nhiều SG được hợp quyền | Một SG rộng gắn thêm có thể vô hiệu hóa ý định giới hạn của SG khác |
| Azure NSG | Rule allow/deny có priority, có thể gắn subnet và network interface theo nền tảng; có default rules | Cần phân tích priority, hướng và hiệu lực giữa subnet/NIC, không dùng công thức union AWS |
| Google Cloud VPC firewall | Rule theo hướng/priority, phạm vi target theo network tags/service accounts hoặc cơ chế mới tương ứng | Kiểm tra target membership và thứ tự xét rule trên kiến trúc GCP |
| Kubernetes NetworkPolicy | Dựa vào pod/namespace selector, behavior tùy CNI và chính sách ingress/egress | Không coi pod selector là SG của AWS; cần hiểu default allow/isolation và policy engine |
| SDN/microsegmentation khác | Rule dựa trên workload identity, label, zone hoặc service | Giữ nguyên mục tiêu least privilege nhưng xác minh semantics của engine |

Sự khác biệt nằm ở **cách áp rule, thứ tự, deny/allow, phạm vi association, state tracking và default rules**. Vì vậy, không sao chép lệnh hoặc cú pháp rule từ cloud này sang cloud khác; dùng một ma trận luồng logic chung, sau đó ánh xạ bằng cơ chế thật của từng nền tảng.

## 13. Quy trình kiểm kê để tìm SG đang bị dùng chung sai cách

Trước khi chia lại nhóm, cần biết **những workload nào đang dùng từng SG** và **rule nào tạo quyền không mong đợi**.

### 13.1. Thu thập tối thiểu

| Dữ liệu | Câu hỏi cần trả lời |
| --- | --- |
| SG ID, name, VPC, owner, environment | Ai quản lý SG, nằm ở vùng nào? |
| ENI và tài nguyên gắn SG | SG có áp cho API, DB, bastion, cache, serverless hoặc tài nguyên khác? |
| Ingress/egress và tham chiếu SG | Rule nào cấp quyền, nguồn/đích và cổng cụ thể? |
| Source/destination object, prefix list | Quyền có mở rộng qua object động hoặc CIDR lớn không? |
| Tag ứng dụng, role, owner | Những workload nào có trách nhiệm/vòng đời khác nhau? |
| Snapshot và version IaC | Cấu hình đang áp dụng có khớp nguồn khai báo không? |
| Flow logs, service telemetry | Những luồng nào được dùng thực tế? Có giới hạn đo nào? |
| Ticket/change và thời hạn | Vì sao rule mở, có thuộc ngoại lệ tạm thời không? |

Có thể xem SG và ENI trên AWS qua API/CLI **read-only** với quyền phù hợp. Ví dụ sau chỉ dùng ID dạng ký hiệu; thay bằng ID thuộc tài khoản được phép kiểm tra:

~~~bash
# Xem rule và thông tin của SG mục tiêu.
aws ec2 describe-security-groups --group-ids sg-EXAMPLE

# Xác định những ENI đang gắn SG đó.
aws ec2 describe-network-interfaces \
  --filters Name=group-id,Values=sg-EXAMPLE
~~~

Lệnh trên **không** kiểm tra đầy đủ những dịch vụ phụ thuộc hoặc chứng minh một luồng được phép đã được sử dụng. Đối với tài khoản lớn, cần xử lý pagination, nhiều region/account và dữ liệu thay đổi theo thời gian. Không quét hoặc thay đổi tài nguyên ngoài phạm vi.

### 13.2. Nhận diện tình huống đáng quan tâm

- SG được gắn lên nhiều loại tài nguyên không cùng role/owner/trust zone.
- SG có ingress từ 0.0.0.0/0 hoặc ::/0 vào port quản trị hay DB, không có lý do rõ.
- SG có self-reference với phạm vi quá rộng mà nhiều loại workload cùng là thành viên.
- Rule mở tới subnet/VPC CIDR thay vì tập nguồn cần thiết.
- Egress mở toàn bộ trên workload có dữ liệu nhạy cảm mà chưa có quyết định rủi ro.
- Rule và association không có trong IaC hoặc khác nguồn khai báo.
- Rule dùng chung bởi production và môi trường thấp hơn qua những policy sao chép tùy tiện.
- Một SG bị thêm vào ENI ngoài kiến trúc mà không có change record.

**Self-referencing SG không mặc nhiên sai.** Một số cluster hoặc nhóm cùng vai trò cần giao tiếp nội bộ. Nhưng nếu SG gộp DB và web, self-reference có thể cho phép các máy cùng nhóm giao tiếp vượt nhu cầu. Phải xác minh port cụ thể và luồng nội bộ cần thiết.

## 14. Không lấy hit count làm căn cứ duy nhất để xóa rule

Trong AWS, VPC Flow Logs có thể cung cấp metadata lưu lượng ở cấp ENI/subnet/VPC theo cấu hình: địa chỉ, cổng, protocol, số byte/gói, khoảng thời gian và trạng thái ACCEPT/REJECT. Tuy nhiên:

- Flow log không lưu toàn bộ payload; nó không thay thế packet capture hoặc log ứng dụng.
- ACCEPT không tự chỉ ra **rule SG cụ thể nào** đã cho phép gói.
- REJECT có thể xuất phát từ các lớp lọc hoặc điều kiện khác; cần đối chiếu thêm cấu hình.
- Có trường hợp log không đầy đủ hoặc bị giới hạn theo dịch vụ/loại traffic và khoảng thời gian.
- Một rule chỉ dùng cho disaster recovery, tác vụ cuối quý hoặc luồng batch có thể không có hit trong cửa sổ ngắn.

Không suy rằng “30 ngày không có kết nối tới TCP/5432” đồng nghĩa quyền DB có thể xóa ngay. Trước hết đối chiếu schedule, owner, luồng dự phòng, log ứng dụng và khả năng rollback. Trong các trường hợp có rủi ro cao, cân nhắc kiểm thử canary hoặc môi trường staging.

## 15. Phân loại rủi ro của SG dùng chung

Không mọi SG chung đều có cùng mức độ nghiêm trọng. Đánh giá theo:

1. **Trust boundary bị gộp:** public/private, guest/management, dev/prod, partner/internal.
2. **Độ rộng của quyền:** ANY protocol, CIDR rất lớn, port quản trị, database/cache, outbound toàn Internet.
3. **Độ quan trọng dữ liệu:** workload có PII, tài sản thanh toán, bí mật hệ thống, khóa ứng dụng hay không.
4. **Số lượng và loại tài nguyên chịu ảnh hưởng:** cùng một role hay nhiều role khác biệt, số lượng ENI và ứng dụng.
5. **Đường đi thực tế:** route, NACL, service listening, firewall bổ sung, IAM và xác thực còn bảo vệ gì.
6. **Khả năng quan sát:** có owner, flow telemetry, log, detection và change control không.
7. **Khả năng khắc phục:** có staging, canary, backup policy và kế hoạch rollback không.

| Phát hiện minh họa | Ưu tiên tham khảo | Căn cứ |
| --- | --- | --- |
| SG chung cho public web, DB và bastion; SSH/DB mở rộng tới Internet | Rất cao | Nhiều trust boundary và dịch vụ đặc quyền bị lộ |
| API và DB dùng SG chung có self-reference toàn bộ TCP trong VPC | Cao | Dễ mở đường ngang và khó chứng minh least privilege |
| Nhiều worker API production đồng vai trò dùng chung SG app-only | Có thể hợp lý | Cần xác minh nhu cầu thực tế tương đồng |
| Một SG “shared-egress” cho nhiều role, outbound all; egress qua proxy bắt buộc | Cần phân tích | Phải xem proxy/routing, owner và chính sách dữ liệu |
| Rule có tag Owner nhưng nhóm đã giải thể và policy mở rộng | Cần điều tra ưu tiên | Ownership không còn giá trị; nguy cơ tích lũy quyền |

Các mức là ví dụ định tính; không gán CVSS hay khẳng định có exploit khi chưa có bằng chứng về đường truy cập và điều kiện cụ thể.

## 16. Kế hoạch tách SG mà không làm gián đoạn ứng dụng

Thay đổi một SG đang được hàng trăm ENI sử dụng có thể làm đứt kết nối. Đặc biệt, nếu thêm SG chặt lên ENI nhưng chưa tháo SG rộng, **quyền vẫn còn rộng**; nếu tháo quá sớm, ứng dụng có thể mất một dependency chưa kiểm kê.

Nên triển khai theo từng giai đoạn có thể đối chiếu và rollback.

### Giai đoạn A — Lập baseline

1. Chụp snapshot cấu hình và association SG đang áp dụng, kèm thời gian, revision/commit.
2. Lập danh sách mọi workload bị ảnh hưởng, owner ứng dụng, owner bảo mật và người vận hành.
3. Xác định luồng mạng hợp lệ inbound/outbound: API, DB, DNS, authentication, metrics, backup, deployment, health check.
4. Ghi số liệu baseline: tỷ lệ request thành công, latency, lỗi TCP, flow log ACCEPT/REJECT và alert.
5. Xác nhận phạm vi, maintenance window, phương án quay lại, kênh quản trị khi mất kết nối.

### Giai đoạn B — Thiết kế rule mới

1. Tạo ma trận luồng cho từng role/trust zone và môi trường.
2. Ánh xạ sang SG mới có owner, purpose và ticket.
3. Ưu tiên nguồn/đích SG theo vai trò nếu nền tảng hỗ trợ đúng đường mạng; tránh CIDR quá rộng.
4. Định nghĩa outbound cần thiết, đặc biệt trên DB, batch và workload có dữ liệu nhạy cảm.
5. Kiểm tra các security control khác: NACL, route, NAT, VPN/TGW, WAF, IDS/IPS và application authentication.
6. Dùng IaC review và static policy checks để bảo đảm không thêm quyền vô ý.

### Giai đoạn C — Canary và chuyển từng nhóm

1. Chọn một workload đại diện có thể khôi phục dễ, không phải database production quan trọng nhất.
2. Gắn SG mới; xác minh luồng hợp lệ trong khi SG cũ còn tồn tại. Kết quả này **chỉ kiểm tra quyền còn đủ cho ứng dụng**, chưa chứng minh các luồng cấm đã bị chặn.
3. Trong cửa sổ được phê duyệt, **tháo SG chung** khỏi ENI canary và giữ SG chuyên biệt, không vượt quá giới hạn nền tảng và điều kiện vận hành.
4. Chạy phép thử dương (luồng phải ALLOW) và âm (luồng phải DENY) từ đúng vùng nguồn.
5. Theo dõi lỗi ứng dụng, trạng thái kết nối hiện hữu, flow logs, alert và xác nhận của owner.
6. Nếu thất bại, khôi phục đúng cấu hình SG đã lưu và xác minh dịch vụ. Không thêm allow-all tạm thời theo phản xạ.
7. Mở rộng theo từng nhóm workload khi canary đạt, rồi mới giải phóng rule/SG cũ.

### Giai đoạn D — Đóng thay đổi

- Đối chiếu ENI association cuối cùng với mục tiêu; không còn workload cần tách gắn SG chung.
- Đối chiếu SG rule với ticket/IaC và review của chủ dịch vụ.
- Kiểm tra cả IPv4/IPv6, VPN, môi trường DR, HA/failover và các job theo lịch.
- Xóa SG không còn dùng **theo change được phê duyệt**, chỉ sau khi xác nhận không còn association hoặc reference.
- Cập nhật inventory, owner, sơ đồ luồng, kết quả test và cơ chế giám sát drift.

**Điểm quan trọng:** mỗi bước phải phân biệt kết quả “app vẫn chạy” với kết quả “đường không được phép thực sự bị chặn”. Hai mục tiêu cần hai phép kiểm thử khác nhau.

## 17. Mẫu bảng kiểm thử trước và sau khi tách nhóm

Giả sử owner xác nhận hệ thống ba tầng chỉ cần các luồng trong bảng:

| Nguồn kiểm thử | Đích | Phép thử | Trước sửa giả định | Sau sửa mong đợi |
| --- | --- | --- | --- | --- |
| Internet | ALB TCP/443 | HTTPS tới ứng dụng | ALLOW | ALLOW |
| ALB | API TCP/8443 | Request chức năng | ALLOW | ALLOW |
| API | DB TCP/5432 | Kết nối DB được xác thực | ALLOW | ALLOW |
| Public test host | DB TCP/5432 | TCP connect có giới hạn | Có thể tới được do SG chung | DENY tại network boundary |
| User VLAN | Bastion TCP/22 | TCP connect | Có thể tới được | DENY theo policy |
| VPN quản trị | Bastion TCP/22 | SSH hợp lệ với tài khoản test | ALLOW | ALLOW có MFA và audit phù hợp |
| Batch | DB TCP/5432 | Job đã được duyệt nếu tồn tại | Chưa đánh giá | ALLOW chỉ theo nhu cầu |
| API | Đích Internet không được phê duyệt | Egress TCP thử nghiệm có giới hạn | Có thể ALLOW | DENY theo chính sách |

Các kết quả “trước” là giả định để dạy phân tích, **không phải bằng chứng một hệ thống thật**. Phép kiểm thử mạng chỉ nên thực hiện với host, cổng, thời gian và mức tải đã được cho phép. Không thử mật khẩu hoặc khai thác dịch vụ chỉ để chứng minh segmentation.

### 17.1. Cách diễn giải kết quả

- TCP open chứng minh đường có thể tiếp cận ở điểm đo; chưa chứng minh xác thực yếu hoặc dịch vụ có lỗ hổng.
- TCP filtered/timeout từ một nguồn chưa chứng minh tất cả nguồn đều bị chặn.
- Có log ACCEPT nhưng ứng dụng lỗi có thể do TLS, IAM, DB credentials hoặc route phụ; cần phân biệt tầng mạng và tầng ứng dụng.
- Việc thêm SG mới mà chưa tháo SG cũ khiến phép thử DENY không có ý nghĩa nghiệm thu.
- Nếu firewall/NACL khác đã chặn traffic, có thể khó khẳng định SG mới riêng nó đã chặn; cần xem effective path và kết quả thực thi theo tiêu chí đã đặt.

## 18. Quản lý ownership và vòng đời SG

Mỗi SG cần có chủ chịu trách nhiệm và căn cứ tạo/duy trì. Các trường gợi ý:

~~~yaml
# Metadata minh họa cho inventory, không phải file cloud policy.
security_group_id: sg-EXAMPLE-API
name: prod-orders-api
environment: prod
service: orders-api
role: application
owner_team: orders-platform
security_policy_owner: cloud-network-security
business_purpose: "ALB to API; API to Orders DB"
approved_flows:
  - "alb-sg -> api-sg tcp/8443"
  - "api-sg -> db-sg tcp/5432"
change_reference: CHG-EXAMPLE-021
last_reviewed_at: "2026-11-28"
next_review_due: "2027-02-28"
status: VERIFIED
~~~

Trong hệ thống thật, nên quản lý dữ liệu này tại IaC repository, resource tags và inventory có kiểm soát; một số giá trị như danh sách flow đầy đủ hoặc hồ sơ phê duyệt phù hợp hơn với CMDB/ticket thay vì tag ngắn.

Cần phân biệt:

- **Application owner:** xác nhận nhu cầu kết nối.
- **Cloud/network security owner:** xác nhận policy và ranh giới.
- **Platform operator:** triển khai cấu hình và xử lý sự cố.
- **Approver/risk owner:** phê duyệt ngoại lệ và chấp nhận rủi ro còn lại.

Khi một workload mới được gắn vào SG, cần đánh giá **toàn bộ quyền hiệu lực**, chứ không chỉ thêm tag Owner. Khi một ứng dụng bị decommission, phải kiểm tra rule và reference của nó trên những SG khác trước khi xóa.

## 19. Ngăn anti-pattern tái diễn bằng IaC và policy-as-code

Các nguyên tắc nên đưa vào pipeline:

- **Module theo role/service:** module ALB, API, DB, bastion có SG mặc định khác nhau.
- **Review thay đổi quyền:** một rule mới phải có source, destination, service, purpose, owner và ticket.
- **Không allow-all mặc định:** yêu cầu ngoại lệ có thời hạn và risk approval khi cần mở rộng.
- **Phân tách môi trường:** production, staging và development có biến thể policy được review riêng.
- **Kiểm tra associations:** phát hiện SG chung được gắn bất ngờ vào ENI có role khác, hoặc DB nhận SG public.
- **Kiểm tra CIDR và port rủi ro:** cảnh báo 0.0.0.0/0, ::/0, 22/3389/5432/6379 mở rộng và outbound ANY ở vùng nhạy cảm.
- **Policy drift detection:** so sánh rule/association đang áp dụng với IaC và ticket, kể cả thay đổi trực tiếp trên console.
- **Quy trình ngoại lệ:** có owner, lý do, TTL, kế hoạch rollback và ngày tái đánh giá.

Một rule kiểm tra chính sách ở dạng **mã giả**:

~~~text
FOR every workload W:
    groups = effective_associated_security_groups(W)
    rules  = union_of_effective_allow_rules(groups)

    REQUIRE W.role and W.owner are known
    REQUIRE each allow rule maps to an approved flow
    FLAG any rule that crosses a trust boundary without approval
    FLAG public management/database ports
    FLAG shared-group membership across incompatible roles
    FLAG broad egress without a documented exception

    DO NOT automatically delete on a flag:
        open review, verify dependencies, approve change, retest
~~~

Cần viết engine hiểu semantics của từng cloud. Đặc biệt, **union** ở đây minh họa cách hợp quyền AWS khi có nhiều SG; không dùng thuật toán này cho Azure NSG, GCP firewall và Kubernetes NetworkPolicy mà không điều chỉnh.

## 20. Giám sát và phản ứng với sự cố liên quan SG

Tách SG làm giảm bề mặt kết nối nhưng không loại bỏ hoàn toàn tấn công. Cần phối hợp:

- Cloud audit log: ai tạo/sửa rule và gắn SG vào tài nguyên, từ nguồn thao tác nào.
- Network flow log: đường liên lạc giữa các vùng có xuất hiện ngoài ma trận không.
- IDS/IPS/NDR: hành vi quét nội bộ, lưu lượng bất thường và tín hiệu lateral movement.
- EDR và audit ứng dụng: tiến trình tạo kết nối, thất bại xác thực, thay đổi service.
- IAM/SIEM: quyền sửa SG, phát hiện sửa policy trái pipeline và tương quan change ticket.
- Dashboard: số SG chung nhiều role, số workload còn gắn SG cũ, số rule broad, owner chưa xác nhận và drift tồn đọng.

Nếu phát hiện một database SG bất ngờ nhận inbound từ 0.0.0.0/0, cần xác minh **effective reachability** qua route, public address, NACL và firewall khác, nhưng không chờ đến khi có truy cập trái phép mới xử lý rule sai thiết kế. Sử dụng quy trình quản lý sự cố hoặc thay đổi khẩn theo mức rủi ro và quyền hạn.

### 20.1. Những chỉ số nên theo dõi

| Chỉ số | Ý nghĩa | Giới hạn diễn giải |
| --- | --- | --- |
| Số SG gắn workload khác role | Phát hiện nhóm chia sẻ thiếu tách biệt | Cần kiểm tra quyền có thật sự khác nhau không |
| Số ENI gắn SG broad | Đo phạm vi ảnh hưởng của một nhóm rộng | Không tự chứng minh lỗ hổng có thể khai thác |
| Số rule public-to-management/database | Theo dõi bề mặt rủi ro cao | Cần phân loại endpoint và kiểm soát khác |
| Tỷ lệ SG có owner và flow approval | Đo chất lượng quản trị | Owner phải được xác minh, không chỉ có tag |
| Số SG/association ngoài IaC | Phát hiện drift | Cần phân biệt thay đổi khẩn hợp lệ |
| Tỷ lệ canary migration đạt test dương/âm | Đo hiệu quả chuyển đổi | Phải có đúng nguồn và vị trí kiểm thử |
| Số ngoại lệ egress quá hạn | Theo dõi quyền tồn đọng | Cần xét dependency và quy trình thu hồi |

## 21. Các sai lầm khi sửa sai lầm

| Cách sửa chưa đúng | Vì sao chưa đạt | Điều chỉnh phù hợp |
| --- | --- | --- |
| Chỉ đổi tên shared-prod thành api-sg | Quyền và thành viên không đổi | Tách association và rule theo role thực tế |
| Thêm SG chặt hơn nhưng vẫn giữ SG rộng | AWS hợp quyền ALLOW của các SG | Tháo SG rộng theo migration được kiểm thử |
| Một SG cho từng instance bất kể role | SG sprawl, trùng rule, khó bảo trì | Dùng SG chung cho workload có quyền tương đương |
| Chặn toàn bộ outbound bất ngờ | Làm hỏng DNS, secrets, update, logging, backup | Kiểm kê dependency rồi chuyển từng bước |
| Xóa rule chỉ vì zero hits 7 ngày | Có thể phá batch/DR/luồng ít dùng | Review owner, lịch sử, canary và rollback |
| Dùng CIDR toàn VPC thay SG tham chiếu | Tăng membership được phép quá mức | Ưu tiên role-based reference khi hỗ trợ |
| Dùng SG reference nhưng ai cũng được gắn SG nguồn | Thành viên nguồn có thể mở rộng không kiểm soát | Quản lý quyền attach SG và IaC change |
| Chỉ thử kết nối hợp lệ | Không xác nhận đường không được phép bị chặn | Bổ sung phép thử DENY từ nguồn đúng |
| Tách SG nhưng quên NAT/VPN/IPv6 | Một đường phụ có thể vẫn mở | Đánh giá mọi route và address family liên quan |
| Bỏ qua số lượng SG limit/quota | Migration có thể không gắn được nhóm mới | Kiểm tra hạn mức nền tảng và kế hoạch đổi ENI |
| Rule SG đúng nhưng ứng dụng vẫn dùng mật khẩu mặc định | Có bề mặt bảo mật lớp trên chưa xử lý | Phối hợp IAM, xác thực, secrets, patch và monitoring |
| Không cập nhật tài liệu và owner | Sau vài tháng rule lại mở rộng tùy tiện | Inventory, attestation, policy-as-code và review liên tục |

## 22. Tình huống vận hành để phân tích

### Tình huống A — Thêm cổng Redis làm mở quyền cho cả DB

Một nhóm batch worker cần kết nối Redis TCP/6379, nên kỹ sư thêm inbound vào SG chung vốn đang gắn cả API, DB và bastion. Sau thay đổi, các workload khác cũng có quyền mạng tương ứng.

**Đánh giá:** rule giải quyết một dependency nhưng được áp cho quá nhiều tài nguyên. **Hướng sửa:** tách SG riêng cho Redis và batch theo role; dùng tham chiếu nhóm/đích cụ thể, giữ rule theo chủ sở hữu và kiểm thử nguồn không được phép không thể tiếp cận Redis.

### Tình huống B — SG API mới rất chặt nhưng scanner vẫn thấy SSH mở

Nhóm vận hành tạo api-restricted chỉ cho TCP/8443 từ ALB rồi gắn thêm vào API. Kết quả kiểm thử vẫn thấy TCP/22 từ VLAN người dùng tới API.

**Đánh giá:** cần xem toàn bộ SG gắn ENI. Nếu shared-prod vẫn cho SSH từ VLAN người dùng, SG mới không thu hẹp quyền trong AWS. **Hướng sửa:** lập kế hoạch tháo SG chung, xác minh đường quản trị hợp lệ và chạy lại phép thử DENY.

### Tình huống C — Xóa nhóm chung khiến API mất DNS

Nhóm bảo mật tách SG nhưng chỉ khai báo ALB → API và API → DB, bỏ qua dependency DNS và secret manager. Khi tháo SG cũ, ứng dụng không phân giải được tên DB hoặc không lấy được credential.

**Đánh giá:** lỗi do kiểm kê dependency thiếu, không phải vì least privilege không khả thi. **Hướng sửa:** khôi phục theo kế hoạch rollback, bổ sung luồng tối thiểu tới resolver/endpoint phù hợp, kiểm thử staging/canary và thử lại.

### Tình huống D — Production và staging dùng template “allow internal all”

Hai môi trường có VPC riêng nhưng đều sao chép mẫu mở toàn bộ traffic trong CIDR nội bộ. Các workload staging có cùng khả năng tiếp cận lẫn nhau như production dù không có nhu cầu.

**Đánh giá:** dù không gắn **cùng một SG ID**, đây vẫn là **tái sử dụng một policy quá rộng**. **Hướng sửa:** thiết kế ma trận theo vai trò và môi trường, dùng module IaC tham số hóa đúng nguồn/đích, bổ sung rule kiểm tra không mở blanket internal access.

### Tình huống E — SG shared chỉ dùng cho các API replica

Một service có 15 replica API đồng nhất, cùng security requirements, cùng owner và đều gắn prod-orders-api. Không có DB hoặc bastion gắn SG này. Rule chỉ cho nhận request từ ALB SG và kết nối tới các dependency đã duyệt.

**Đánh giá:** dùng chung SG là hợp lý vì các workload có cùng vai trò và nhu cầu. Tiếp tục duy trì owner, kiểm tra association và thay đổi quyền theo quy trình.

### Tình huống F — Một SG mở 0.0.0.0/0 nhưng DB không có public IP

Scanner ngoài Internet không truy cập được DB, và nhóm dự án cho rằng rule an toàn.

**Đánh giá:** kết quả không tiếp cận được từ Internet tại thời điểm kiểm thử là một lớp thông tin; rule SG quá rộng vẫn tăng quyền có thể từ những nguồn có route tới DB hoặc khi topology thay đổi. Cần đánh giá network reachability từ các vùng thực tế, rồi thu hẹp tới SG nguồn hợp lệ, không chỉ dựa vào public IP.

## 23. Checklist thiết kế trước khi triển khai

- [ ] Mỗi workload có role, môi trường, owner và dữ liệu nhạy cảm được phân loại.
- [ ] Có ma trận source–destination–protocol–port cho luồng ứng dụng thực tế.
- [ ] SG cùng tên/ID chỉ được chia sẻ cho workload có quyền tương đương.
- [ ] Không dùng SG chung cho DB, public entry, bastion và workload người dùng khi trust boundary khác nhau.
- [ ] Đã kiểm tra mọi SG gắn trên ENI để xác định quyền ALLOW hiệu lực trong AWS.
- [ ] Rule quản trị, database/cache và Internet exposure được giới hạn theo nguồn cần thiết.
- [ ] Egress, IPv6 và các dependency DNS/identity/logging/backup đã được review.
- [ ] SG reference được dùng khi phù hợp và quyền gắn thành viên SG nguồn được kiểm soát.
- [ ] Có owner, ticket, business purpose và lịch review cho rule quan trọng.
- [ ] IaC có review, policy-as-code và phát hiện drift.
- [ ] Quy trình canary/migration có rollback và người xử lý sự cố.
- [ ] Kiểm thử dương/âm đã chạy sau khi **SG chung thực sự được tháo**.
- [ ] Security groups trong DR, HA và các đường mạng phụ cũng được kiểm tra.
- [ ] Kết quả có bằng chứng: ENI association, rule ID, log, thời gian và người xác nhận.

## 24. Câu hỏi tự kiểm tra

1. Vì sao một SG api-restricted không chặn được TCP/22 nếu một SG khác trên cùng ENI đã cho phép TCP/22 trong AWS?
2. Trường hợp nào nhiều instance dùng chung một SG lại là thiết kế hợp lý?
3. Vì sao chia SG theo *mỗi máy* không nhất thiết tốt hơn chia theo *role và trust boundary*?
4. Một rule inbound DB tham chiếu source SG api đem lại lợi ích gì so với cho phép toàn bộ VPC CIDR? Rủi ro quản lý membership còn lại là gì?
5. Vì sao chỉ kiểm tra inbound không đủ cho workload có dữ liệu nhạy cảm?
6. Nếu API vẫn chạy sau khi gắn SG mới nhưng chưa tháo SG chung, điều gì đã và chưa được chứng minh?
7. Những dependency thường bị quên khi thu hẹp egress là gì?
8. Vì sao zero hit trong một khoảng ngắn không đủ chứng minh rule có thể xóa?
9. Sự khác nhau quan trọng giữa AWS VPC SG và Azure NSG khi phân tích rule chồng lấn là gì?
10. Sau khi tháo SG chung, cần kiểm chứng những luồng ALLOW và DENY nào để vừa bảo đảm availability vừa giữ segmentation?
11. Làm thế nào phát hiện khi một workload mới gắn vào SG api dù không thuộc service đó?
12. Bằng chứng nào cho thấy quá trình migration đã hoàn tất thay vì chỉ đổi tên hoặc thêm SG mới?

**Ghi nhớ:** sai lầm **dùng chung một security group cho mọi workload** xuất phát từ việc cấp quyền theo tập hợp nhu cầu của nhiều hệ thống thay vì theo **vai trò, môi trường và ranh giới tin cậy**. Một SG chỉ nên được chia sẻ khi các workload có yêu cầu truy cập thực sự tương đương. Trong AWS, nhiều SG gắn cùng ENI được hợp quyền ALLOW, vì vậy một nhóm quá rộng không thể bị một nhóm chặt hơn vô hiệu hóa. Thiết kế và khắc phục đúng đòi hỏi ma trận luồng rõ ràng, SG theo role, kiểm soát membership, egress phù hợp, thử nghiệm dương/âm sau khi tháo SG cũ và quản trị rule bằng owner, IaC và kiểm soát thay đổi.
