# Network Security Group và Application Security Group

Trong module **CLOUD_PROVIDERS_AZURE**, chúng ta khám phá Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; sau đó học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Ở chương **Mạng ảo và phân giải tên**, hiểu **Network Security Group (NSG)** và **Application Security Group (ASG)** là nền tảng để kiểm soát luồng kết nối trong Azure Virtual Network (VNet).

Hãy hình dung ứng dụng đặt hàng có ba tầng: máy chủ web, API và database. Người dùng chỉ nên truy cập web qua HTTPS; web chỉ cần gọi API trên cổng 8080; API mới được phép kết nối database trên cổng 1433. Nếu tất cả máy ảo nằm trong một VNet mà không kiểm soát kết nối, các tầng có thể giao tiếp rộng hơn dự định. NSG giúp định nghĩa các quy tắc cho phép/từ chối; ASG giúp diễn đạt các quy tắc đó theo vai trò ứng dụng thay vì phải duy trì danh sách IP riêng lẻ.

Sau bài học, bạn có thể:

- Giải thích chức năng, vị trí áp dụng, thứ tự đánh giá và tính stateful của NSG.
- Phân biệt NSG, ASG và các thành phần bảo mật mạng khác của Azure.
- Đọc và thiết kế luật theo nguồn, đích, cổng, giao thức, hướng, hành động và priority.
- Dùng ASG để biểu diễn các tầng ứng dụng có nhiều VM trong cùng VNet.
- Tạo NSG, ASG và các luật bằng Azure CLI; kiểm tra effective security rules và khắc phục lỗi kết nối.
- Nhận diện rủi ro của luật mặc định, cấu hình trùng lặp, mở quyền quá rộng và thay đổi làm gián đoạn dịch vụ.

## 1. NSG là gì và bảo vệ phạm vi nào?

**Network Security Group** là tài nguyên Azure chứa một tập hợp **security rules** để lọc lưu lượng IP đi vào (**inbound**) và đi ra (**outbound**) những thành phần mạng thuộc phạm vi hỗ trợ. Với máy ảo Azure, có thể liên kết NSG với:

1. **Subnet** của VNet, để kiểm soát lưu lượng liên quan tới các giao diện mạng trong subnet đó.
2. **Network Interface (NIC)** của một VM, để áp dụng thêm quy tắc cho giao diện cụ thể.

Một subnet hoặc một NIC chỉ liên kết trực tiếp với **một NSG** tại một thời điểm, nhưng cùng một NSG có thể được liên kết với nhiều subnet/NIC phù hợp. Không cần gắn NSG ở cả hai cấp trong mọi kiến trúc; nên có quy ước rõ ràng để tránh khó tìm nguyên nhân khi một kết nối bị từ chối.

NSG là cơ chế lọc lưu lượng mạng dựa trên các đặc điểm lớp mạng và lớp vận chuyển, chẳng hạn địa chỉ IP, cổng và giao thức. Nó **không** thay thế cơ chế xác thực người dùng, TLS, firewall trong hệ điều hành, Web Application Firewall hay việc kiểm soát lỗ hổng ứng dụng.

### 1.1. Một rule gồm những trường nào?

| Trường | Chức năng | Ví dụ |
|---|---|---|
| `name` | Đặt tên có ý nghĩa cho rule | `Allow-Web-To-Api-8080` |
| `priority` | Thứ tự xét rule; **số nhỏ hơn được xét trước** | `200` |
| `direction` | Hướng lưu lượng | `Inbound` hoặc `Outbound` |
| `access` | Hành động khi khớp rule | `Allow` hoặc `Deny` |
| `protocol` | Giao thức được xét | `Tcp`, `Udp`, `Icmp`, `*` |
| Nguồn | IP/CIDR, service tag hoặc ASG | `10.20.1.0/24`, `VirtualNetwork`, `asg-web` |
| Cổng nguồn | Cổng phía khởi tạo hoặc nguồn gói tin | `*` (thường là cổng động) |
| Đích | IP/CIDR, service tag hoặc ASG | `10.20.2.0/24`, `asg-api` |
| Cổng đích | Cổng ứng dụng nhận kết nối | `443`, `8080`, `1433` |

Ví dụ: một inbound rule có `priority=200`, nguồn `asg-web`, đích `asg-api`, protocol `Tcp`, destination port `8080`, access `Allow` cho phép những kết nối thỏa toàn bộ tiêu chí đó **nếu không có NSG khác chặn trên đường đi**.

Priority của các luật tùy chỉnh trong NSG nằm trong dải **100–4096**. Trong cùng một NSG, mỗi hướng cần những priority khác nhau cho các luật được cấu hình; cùng một priority có thể được sử dụng ở hai hướng inbound và outbound. Một rule có số priority thấp hơn sẽ được xét trước rule có số cao hơn.

### 1.2. Cách NSG quyết định Allow hay Deny

Azure kiểm tra các rule theo thứ tự priority tăng dần trong hướng lưu lượng tương ứng. **Rule đầu tiên khớp** các tiêu chí sẽ quyết định Allow/Deny; những rule priority thấp hơn về mặt ưu tiên (tức số lớn hơn) không được xét cho luồng đó.

Ví dụ trên cùng NSG:

| Priority | Direction | Source | Destination port | Access |
|---:|---|---|---:|---|
| 100 | Inbound | `10.20.1.5` | `8080` | Deny |
| 200 | Inbound | `10.20.1.0/24` | `8080` | Allow |
| 300 | Inbound | `VirtualNetwork` | `*` | Deny |

Lưu lượng từ `10.20.1.5` đến cổng 8080 bị từ chối bởi luật 100, dù nó cũng thuộc dải nguồn của luật Allow 200. Lưu lượng từ `10.20.1.6` đến cổng 8080 khớp luật 200 và được cho phép. Kết nối nội bộ khác khớp luật Deny 300 bị từ chối.

NSG đánh giá theo các trường được khai báo. **Tên rule không quyết định cách xử lý**: một rule tên `Deny-SSH` nhưng có `access=Allow` vẫn là một luật cho phép.

## 2. Các luật mặc định trong NSG

Khi tạo NSG, Azure có sẵn các **default security rules**. Chúng giúp lưu lượng cơ bản hoạt động, nhưng có thể không đáp ứng yêu cầu cô lập giữa các tầng ứng dụng.

### 2.1. Luật inbound mặc định

| Priority | Tên rule | Ý nghĩa |
|---:|---|---|
| 65000 | `AllowVnetInBound` | Cho phép lưu lượng từ `VirtualNetwork` đến `VirtualNetwork` |
| 65001 | `AllowAzureLoadBalancerInBound` | Cho phép lưu lượng từ service tag `AzureLoadBalancer` |
| 65500 | `DenyAllInBound` | Từ chối lưu lượng inbound còn lại |

### 2.2. Luật outbound mặc định

| Priority | Tên rule | Ý nghĩa |
|---:|---|---|
| 65000 | `AllowVnetOutBound` | Cho phép lưu lượng từ `VirtualNetwork` đến `VirtualNetwork` |
| 65001 | `AllowInternetOutBound` | Cho phép lưu lượng outbound đến `Internet` theo định nghĩa service tag |
| 65500 | `DenyAllOutBound` | Từ chối lưu lượng outbound còn lại |

Các rule mặc định không thể xóa trực tiếp; muốn thay đổi hành vi, hãy tạo **custom rule** có priority cao hơn (giá trị số nhỏ hơn). Quy tắc mặc định `AllowVnetInBound` là lý do thường gặp khiến hai VM trong cùng VNet vẫn giao tiếp được dù bạn mới chỉ thêm một vài luật Allow tùy chỉnh.

**Điểm cần nhớ:** thêm một rule `Allow-Web-To-Api` **không tự động chặn** các nguồn nội bộ khác truy cập API. Để cô lập API, cần một rule Deny phù hợp, được ưu tiên hơn rule mặc định `AllowVnetInBound`. Phải kiểm tra các kết nối quản trị, DNS, health probe và phụ thuộc hợp lệ trước khi triển khai Deny.

Service tag `VirtualNetwork` có thể bao phủ nhiều dải địa chỉ liên quan đến cấu hình kết nối mạng, chẳng hạn dải VNet và các mạng được kết nối theo cơ chế hỗ trợ. Không nên mặc định rằng tag này chỉ chứa đúng một subnet.

## 3. NSG là stateful và được áp dụng ở nhiều cấp

NSG là **stateful**: khi một kết nối được cho phép theo rule phù hợp, lưu lượng phản hồi thuộc kết nối đó được theo dõi và không cần một rule riêng cho từng gói phản hồi ở chiều ngược lại.

Ví dụ, nếu web VM chủ động kết nối API VM từ cổng nguồn động 52000 đến cổng đích TCP 8080, phản hồi của API về cổng 52000 thuộc cùng kết nối được theo dõi. Điều đó **không** có nghĩa API VM có thể chủ động mở một kết nối mới đến web VM nếu không có rule cho phép.

Thay đổi hoặc xóa rule thường ảnh hưởng việc thiết lập **kết nối mới**. Các kết nối đang hoạt động có thể tiếp tục cho đến khi trạng thái luồng kết thúc; không dùng thay đổi NSG như cơ chế duy nhất để cắt ngay mọi phiên kết nối đã tồn tại.

### 3.1. Nếu cả subnet và NIC đều có NSG

Lưu lượng phải đi qua các lớp lọc áp dụng cho nó. Khi inbound đến VM, Azure xét lớp NSG của subnet trước, sau đó NSG của NIC. Khi outbound từ VM, thứ tự xét là NSG của NIC trước, rồi NSG của subnet.

```text
Inbound:
Nguồn --> NSG subnet --> NSG NIC --> VM

Outbound:
VM --> NSG NIC --> NSG subnet --> Đích
```

Một kết nối mới phải được phép bởi **tất cả NSG liên quan**. Rule Allow ở NIC không thể ghi đè rule Deny ở subnet, và ngược lại. Thứ tự priority chỉ có ý nghĩa **bên trong từng NSG**, không phải một danh sách priority toàn cục gộp tất cả NSG.

Ví dụ:

- NSG ở subnet cho phép TCP 8080 từ web tier.
- NSG ở NIC API từ chối TCP 8080 từ chính nguồn đó.
- Kết quả: kết nối đến API **bị chặn**, dù NSG của subnet có Allow.

Trong vận hành, nhiều đội chỉ gán NSG ở subnet để quản lý tập trung và giảm số lớp chồng nhau; đội khác dùng NSG tại NIC khi cần ngoại lệ có kiểm soát. Cả hai đều có thể phù hợp nếu trách nhiệm và quy trình cập nhật được xác định rõ.

## 4. ASG là gì?

**Application Security Group** là một cách **nhóm logic các network interface/IP configuration của VM theo vai trò ứng dụng** để sử dụng trong các rule của NSG. Thay vì liệt kê từng địa chỉ IP của web server, bạn có thể khai báo nguồn là `asg-web`.

Ví dụ:

```text
VNet vnet-orders-prod (10.20.0.0/16)
|
+-- subnet-web (10.20.1.0/24)
|    +-- vm-web-01 [asg-web]
|    +-- vm-web-02 [asg-web]
|
+-- subnet-api (10.20.2.0/24)
|    +-- vm-api-01 [asg-api]
|    +-- vm-api-02 [asg-api]
|
+-- subnet-db (10.20.3.0/24)
     +-- vm-db-01  [asg-db]
```

Các tên và IP là ví dụ. ASG định nghĩa **thành viên** theo cấu hình mạng của VM; ASG **không tự lọc lưu lượng**. Muốn enforcement, bạn vẫn phải tạo NSG rule sử dụng ASG và liên kết NSG đó với subnet hoặc NIC có liên quan.

Khi thêm `vm-api-03` vào ASG `asg-api`, những NSG rule hiện có tham chiếu ASG này có thể áp dụng cho VM mới mà không cần sửa rule để bổ sung IP của VM. Đây là lợi ích khi VM tăng/giảm số lượng hoặc được thay thế.

### 4.1. Giới hạn và phạm vi cần hiểu

- ASG áp dụng cho cấu hình IP của NIC của các VM trong phạm vi tính năng hỗ trợ. **Không** thể dùng ASG để tự động gom mọi tài nguyên PaaS như Azure SQL Database, Storage Account hay App Service.
- Các NIC được đưa vào cùng một ASG phải tuân thủ các giới hạn về **cùng virtual network** theo quy tắc của Azure. Khi dùng nhiều VNet/peering, hãy xác minh ràng buộc ASG trước khi thiết kế rule liên mạng.
- Cấu hình ASG không thay thế subnet, route table, NSG hoặc Azure Firewall.
- Một VM có thể tham gia nhiều ASG thông qua các IP configuration được hỗ trợ; cần kiểm tra quota và giới hạn hiện hành theo subscription/region.
- Việc ASG có trong rule chỉ là tiêu chí đối chiếu nguồn hoặc đích; rule vẫn cần direction, access, protocol, port và priority.

Nếu lớp dữ liệu là **Azure SQL Database dạng PaaS**, không nên đặt nó vào `asg-db` như một VM. Khi đó cần chọn cơ chế truy cập phù hợp hơn, chẳng hạn private endpoint, cấu hình networking của Azure SQL, NSG theo phạm vi được hỗ trợ và các kiểm soát danh tính. Trong ví dụ ASG ba tầng bên trên, `vm-db-01` là **máy ảo tự vận hành database**.

## 5. So sánh NSG và ASG

| Tiêu chí | Network Security Group (NSG) | Application Security Group (ASG) |
|---|---|---|
| Bản chất | Bộ luật lọc mạng Allow/Deny | Nhóm logic các giao diện mạng theo vai trò |
| Có trực tiếp chặn gói tin không? | Có, khi NSG gắn vào phạm vi phù hợp | Không |
| Áp dụng vào đâu? | Subnet hoặc NIC | Thành viên NIC IP configuration; được tham chiếu trong NSG rule |
| Quy định cổng và giao thức? | Có | Không |
| Mục đích | Kiểm soát luồng kết nối | Giảm việc phải quản lý danh sách IP cho rule |
| Ví dụ | Chỉ cho phép TCP 8080 từ web sang API | Tập hợp các VM thuộc vai trò `asg-api` |

NSG trả lời **“luồng nào được phép?”**; ASG trả lời **“những VM nào đóng vai trò nguồn/đích trong luật đó?”**. Chúng thường được dùng **kết hợp**, không phải hai lựa chọn thay thế nhau.

## 6. Thiết kế phân đoạn mạng cho ứng dụng ba tầng

Giả sử workload đặt hàng có:

- Web tier: `vm-web-01`, `vm-web-02`, chỉ phục vụ HTTPS 443 từ một điểm vào đã thiết kế.
- API tier: `vm-api-01`, `vm-api-02`, lắng nghe TCP 8080 và chỉ nhận kết nối mới từ web tier.
- Database tier: `vm-db-01` chạy SQL Server trên VM, lắng nghe TCP 1433 và chỉ nhận kết nối mới từ API tier.
- Các tầng nằm ở ba subnet riêng trong **cùng VNet**; các VM được gán vào ASG tương ứng.

Chính sách dự kiến:

| Nguồn | Đích | Cổng/giao thức | Kết quả mong muốn |
|---|---|---|---|
| Điểm vào web đã được cho phép | `asg-web` | TCP 443 | Allow |
| `asg-web` | `asg-api` | TCP 8080 | Allow |
| `asg-api` | `asg-db` | TCP 1433 | Allow |
| Các nguồn nội bộ khác | `asg-api` | Các cổng khác | Deny theo chính sách cô lập |
| Các nguồn khác | `asg-db` | TCP 1433 và cổng không được duyệt | Deny theo chính sách cô lập |
| Internet bất kỳ | `asg-db` | Bất kỳ | Deny |

Luật chỉ có ý nghĩa khi NSG được gắn với subnet/NIC có các VM tương ứng. Để đạt kết quả, cần xét **cả NSG mặc định** và mọi NSG khác đang áp dụng. Trong ví dụ thực hành sau, chúng ta sẽ tập trung bảo vệ inbound của API; đối với web và database, cần cấu hình các NSG tương ứng theo cùng nguyên tắc.

Một ví dụ inbound cho subnet API:

| Priority | Source | Destination | Port | Access |
|---:|---|---|---|---|
| 200 | `asg-web` | `asg-api` | TCP 8080 | Allow |
| 300 | `VirtualNetwork` | `asg-api` | Any | Deny |
| 65000 (mặc định) | `VirtualNetwork` | `VirtualNetwork` | Any | Allow |

Luật Deny 300 được xét **trước** default Allow 65000, nhờ đó các nguồn nội bộ không được cho phép tường minh sẽ không thể mở kết nối mới đến API. Tuy nhiên, phạm vi `VirtualNetwork` và các luật khác phải được rà soát cẩn thận. Chẳng hạn nếu API cần nhận health probe hoặc kết nối quản trị nội bộ, hãy thiết kế các rule Allow riêng theo nguồn và cổng được phê duyệt, với priority nhỏ hơn luật Deny.

Đây là ví dụ về **network segmentation**, không phải mô hình zero trust hoàn chỉnh. Tiếp tục xác thực dịch vụ, TLS, phân quyền dữ liệu, kiểm soát route và bảo vệ hệ điều hành.

## 7. Thực hành với Azure CLI: tạo NSG và ASG

Các lệnh dưới đây dùng cú pháp **Bash** trong Azure Cloud Shell hoặc môi trường có Azure CLI tương thích. Giả định bạn đã có subscription đang hoạt động, resource group `rg-orders-net-dev`, VNet `vnet-orders-dev`, subnet `snet-api` và hai NIC VM web/API. Các tên chỉ là minh họa. Bạn cần quyền tạo network resources, cập nhật NIC/subnet và NSG. Lệnh có thể thay đổi cấu hình mạng thật; hãy thực hành trong môi trường thử nghiệm hoặc theo quy trình phê duyệt.

### 7.1. Xác nhận subscription và đặt biến

```bash
az account show --output table
az account set --subscription "<subscription-id>"

RG="rg-orders-net-dev"
LOCATION="southeastasia"
VNET="vnet-orders-dev"
API_SUBNET="snet-api"
NSG="nsg-orders-api-dev"
ASG_WEB="asg-orders-web-dev"
ASG_API="asg-orders-api-dev"
WEB_NIC="nic-orders-web-01"
API_NIC="nic-orders-api-01"
```

Trước khi gắn rule, hãy xác minh các NIC và subnet có trong resource group đích và các VM thuộc cùng VNet. Với hạ tầng production, thường nên quản lý cấu hình qua Bicep/ARM template hoặc công cụ Infrastructure as Code thay vì thay đổi thủ công.

### 7.2. Tạo hai ASG

```bash
az network asg create \
  --resource-group "$RG" \
  --name "$ASG_WEB" \
  --location "$LOCATION"

az network asg create \
  --resource-group "$RG" \
  --name "$ASG_API" \
  --location "$LOCATION"
```

Lấy Resource ID để sử dụng tường minh ở các thao tác tiếp theo:

```bash
ASG_WEB_ID=$(az network asg show \
  --resource-group "$RG" --name "$ASG_WEB" \
  --query id --output tsv)

ASG_API_ID=$(az network asg show \
  --resource-group "$RG" --name "$ASG_API" \
  --query id --output tsv)
```

### 7.3. Gán NIC IP configuration vào ASG

Giả sử mỗi NIC đã có IP configuration tên `ipconfig1`. Bạn cần xác nhận tên thực tế trong môi trường của mình trước khi chạy.

```bash
az network nic ip-config list \
  --resource-group "$RG" \
  --nic-name "$WEB_NIC" \
  --output table

az network nic ip-config list \
  --resource-group "$RG" \
  --nic-name "$API_NIC" \
  --output table
```

Sau đó cập nhật membership:

```bash
az network nic ip-config update \
  --resource-group "$RG" \
  --nic-name "$WEB_NIC" \
  --name ipconfig1 \
  --application-security-groups "$ASG_WEB_ID"

az network nic ip-config update \
  --resource-group "$RG" \
  --nic-name "$API_NIC" \
  --name ipconfig1 \
  --application-security-groups "$ASG_API_ID"
```

Nếu một IP configuration vốn đã thuộc ASG khác và vẫn cần giữ membership đó, phải kiểm tra hành vi của lệnh cập nhật và khai báo đầy đủ các nhóm cần giữ; đừng vô tình làm mất membership hiện hữu. Bổ sung các VM web/API khác vào ASG tương ứng theo cùng cách.

### 7.4. Tạo NSG và các rule cho API

```bash
az network nsg create \
  --resource-group "$RG" \
  --name "$NSG" \
  --location "$LOCATION"

az network nsg rule create \
  --resource-group "$RG" \
  --nsg-name "$NSG" \
  --name Allow-Web-To-Api-8080 \
  --priority 200 \
  --direction Inbound \
  --access Allow \
  --protocol Tcp \
  --source-asgs "$ASG_WEB_ID" \
  --source-port-ranges "*" \
  --destination-asgs "$ASG_API_ID" \
  --destination-port-ranges 8080
```

Rule trên cho phép **kết nối mới** TCP 8080 từ thành viên ASG web đến thành viên ASG API, nhưng chưa ngăn các kết nối khác được rule mặc định cho phép. Để tạo ranh giới kiểm soát nội bộ cho API, có thể thêm một Deny được ưu tiên cao hơn default:

```bash
az network nsg rule create \
  --resource-group "$RG" \
  --nsg-name "$NSG" \
  --name Deny-Other-VNet-To-Api \
  --priority 300 \
  --direction Inbound \
  --access Deny \
  --protocol "*" \
  --source-address-prefixes VirtualNetwork \
  --source-port-ranges "*" \
  --destination-asgs "$ASG_API_ID" \
  --destination-port-ranges "*"
```

**Cảnh báo triển khai:** Rule Deny 300 có thể chặn nhiều kết nối nội bộ ngoài dự kiến nếu thiếu các luật Allow cụ thể. Trước khi áp dụng vào production, xác nhận nguồn DNS, kiểm tra sức khỏe, công cụ quản trị, backup, dịch vụ giám sát và các kết nối vận hành cần thiết. Nếu có NSG trên NIC API, kiểm tra thêm rule tại NIC vì luật Allow ở subnet không thể vượt qua một luật Deny ở NIC.

### 7.5. Gắn NSG vào subnet API

```bash
az network vnet subnet update \
  --resource-group "$RG" \
  --vnet-name "$VNET" \
  --name "$API_SUBNET" \
  --network-security-group "$NSG"
```

Thao tác này bảo vệ subnet API và có thể ảnh hưởng đến **mọi** NIC liên quan đến subnet. Nếu subnet chứa VM không thuộc `asg-api`, một số luồng của chúng vẫn có thể được phép bởi luật mặc định; do đó không nên xem đây là chính sách đầy đủ cho mọi tài nguyên trong subnet. Hãy kiểm kê toàn bộ subnet, các NSG hiện tại và yêu cầu kết nối trước khi cập nhật.

## 8. Kiểm tra cấu hình và luồng mạng thực tế

### 8.1. Đọc lại rule và liên kết

```bash
az network nsg rule list \
  --resource-group "$RG" \
  --nsg-name "$NSG" \
  --output table

az network vnet subnet show \
  --resource-group "$RG" \
  --vnet-name "$VNET" \
  --name "$API_SUBNET" \
  --query "{name:name,nsg:networkSecurityGroup.id}" \
  --output json

az network nic ip-config show \
  --resource-group "$RG" \
  --nic-name "$API_NIC" \
  --name ipconfig1 \
  --query "{name:name,asgs:applicationSecurityGroups}" \
  --output json
```

Xem cấu hình ở cả nơi **định nghĩa rule** (NSG), nơi **gắn enforcement** (subnet/NIC) và nơi **xác định thành viên** (ASG trên NIC IP configuration).

### 8.2. Effective security rules và IP flow verify

Rule bạn nhìn thấy trong một NSG chưa chắc là toàn bộ chính sách có hiệu lực trên một VM. Azure Network Watcher có các công cụ:

- **Effective security rules:** tổng hợp rule liên quan đến NIC, bao gồm các NSG áp dụng ở cấp NIC và subnet.
- **IP flow verify:** đánh giá một luồng IP theo thông tin nguồn/đích, hướng, giao thức và cổng, rồi trả kết quả Allow/Deny cùng rule phù hợp.
- **Connection troubleshoot:** kiểm tra khả năng kết nối giữa nguồn và đích trong phạm vi hỗ trợ, hữu ích khi nguyên nhân có thể nằm ngoài NSG.

Một lệnh tham khảo để xem effective NSG trên NIC:

```bash
az network nic list-effective-nsg \
  --resource-group "$RG" \
  --name "$API_NIC" \
  --output json
```

Các thao tác chẩn đoán có thể yêu cầu VM đang chạy, quyền phù hợp và tính năng Network Watcher sẵn sàng. Khi kiểm tra một luồng, hãy ghi đủ **IP nguồn, cổng nguồn, IP đích, cổng đích, giao thức và hướng**; thiếu một thông số có thể dẫn đến kết luận sai.

### 8.3. Ma trận kiểm thử

Với bài toán ba tầng, sau khi đã thiết lập đầy đủ NSG ở các subnet/NIC cần thiết:

| Thao tác thử | Kết quả dự kiến | Nếu khác dự kiến |
|---|---|---|
| Web → API, TCP 8080 | Cho phép | Kiểm tra ASG web/API, hai cấp NSG, route, firewall máy chủ, process lắng nghe |
| Web → API, TCP 22 | Từ chối nếu không thuộc rule Allow đặc biệt | Kiểm tra rule mặc định `AllowVnetInBound` và thứ tự rule |
| VM nội bộ không thuộc web → API, TCP 8080 | Từ chối | Kiểm tra rule Deny 300 và các Allow priority thấp hơn về số |
| API → DB VM, TCP 1433 | Chỉ cho phép nếu rule DB được cấu hình đúng | Kiểm tra NSG tại DB; bài lab API chưa tự cấu hình rule DB |
| Internet → DB VM | Từ chối theo chính sách DB | Kiểm tra public IP, NSG, routes và những đường vào thực tế |

Lệnh `curl` hoặc `nc` từ VM nguồn có thể giúp kiểm thử cổng phù hợp, nhưng kiểm thử thành công hay thất bại còn chịu ảnh hưởng bởi ứng dụng có lắng nghe hay không, hệ điều hành, DNS, route, load balancer và cơ chế mạng khác. Network Watcher giúp tách riêng quyết định của NSG khỏi vấn đề ứng dụng.

## 9. NSG, ASG, Azure Firewall và WAF khác nhau ở đâu?

| Thành phần | Mục đích chính | Điều không nên kỳ vọng |
|---|---|---|
| **NSG** | Lọc kết nối theo IP, port, protocol, direction, rule priority | Không phân tích đầy đủ HTTP request hoặc bảo vệ OWASP ở lớp ứng dụng |
| **ASG** | Nhóm NIC theo vai trò để tham chiếu trong NSG rules | Không tự Allow/Deny hay tự gắn vào subnet |
| **Azure Firewall** | Chính sách bảo mật mạng tập trung, kiểm soát lưu lượng theo tính năng và phiên bản dịch vụ | Không thay thế RBAC, danh tính workload hoặc mọi biện pháp bảo mật host |
| **Web Application Firewall (WAF)** | Bảo vệ lưu lượng HTTP/HTTPS trước các mẫu tấn công web khi được tích hợp vào dịch vụ hỗ trợ | Không tự giới hạn mọi kết nối TCP giữa các VM |
| **Route table / UDR** | Quy định đường đi của lưu lượng | Không phải danh sách Allow/Deny có ý nghĩa như NSG |

Đừng nhầm **DNS resolution** với **network authorization**. DNS chỉ giúp client tìm địa chỉ của dịch vụ. NSG không phân quyền theo tên miền/FQDN một cách tổng quát như một firewall ứng dụng có tính năng tương ứng. Nếu nhu cầu là lọc outbound theo FQDN hoặc phân tích lớp 7, cần đánh giá dịch vụ phù hợp thay vì cố dùng ASG.

NSG cũng không quyết định người dùng nào đăng nhập ứng dụng, không tự mã hóa kết nối và không thay thế nguyên tắc least privilege cho tài khoản dịch vụ, Key Vault hoặc database.

## 10. Các lỗi cấu hình thường gặp

**Chỉ thêm Allow rồi tưởng các nguồn khác bị chặn.** NSG có `AllowVnetInBound` mặc định. Hãy xem cả luật mặc định và thêm Deny có thứ tự phù hợp khi cần phân đoạn lưu lượng.

**Tưởng ASG tự bảo vệ VM.** ASG chỉ là nhóm thành viên. Không có NSG rule tham chiếu ASG và không gắn NSG ở nơi phù hợp thì ASG không tạo ranh giới lọc.

**Dùng cổng nguồn giống cổng đích.** Khi web gọi API TCP 8080, cổng nguồn thường là cổng động, không phải 8080. Rule inbound thường để `source-port-ranges="*"`, giới hạn cổng đích theo dịch vụ.

**Quên NSG ở NIC khi đã Allow ở subnet.** Lưu lượng có thể vẫn bị chặn ở lớp NIC. Xem effective rules của NIC, đừng chỉ đọc một NSG.

**Deny quá rộng.** Một Deny nội bộ có thể vô tình chặn quản trị, health check hoặc dịch vụ cần thiết. Xác định danh sách phụ thuộc và thử nghiệm trước khi cập nhật production.

**Không xem xét kết nối đang tồn tại.** NSG stateful nên thay đổi rule chưa chắc cắt ngay các phiên đã thiết lập. Muốn xử lý sự cố an ninh phải phối hợp biện pháp ở ứng dụng, host và mạng.

**Giả định ASG hoạt động như bộ lọc cho toàn bộ PaaS.** ASG chủ yếu phục vụ NIC IP configuration của VM trong phạm vi hỗ trợ. Dịch vụ PaaS cần dùng khả năng networking và identity tương ứng.

**Xem rule Allow là bảo đảm kết nối thành công.** Route, DNS, network appliance, Windows/Linux firewall, trạng thái máy và ứng dụng lắng nghe vẫn quyết định việc kết nối có hoạt động hay không.

**Cấp truy cập quản trị từ `Any`.** Các cổng như SSH/RDP cần được kiểm soát chặt, ưu tiên giải pháp quản trị an toàn như Azure Bastion, kết nối riêng hoặc cơ chế truy cập tạm thời phù hợp. Không mở rộng Internet chỉ để thử nghiệm nhanh.

## 11. Quy trình xây dựng chính sách NSG/ASG cho production

1. **Lập bản đồ luồng kết nối:** xác định workload, nguồn/đích, protocol, cổng, hướng và chủ sở hữu cho từng luồng.
2. **Phân loại vai trò:** quyết định ASG nào tương ứng với tập VM có cùng quyền mạng; tách ASG khi nhu cầu khác nhau.
3. **Xác định điểm enforcement:** chọn NSG ở subnet, NIC hoặc cả hai theo quy ước quản trị; kiểm kê các NSG hiện hữu.
4. **Thiết kế allowlist:** khai báo chính xác các luồng cần thiết. Kiểm tra những Allow mặc định có thể làm chính sách rộng hơn dự định.
5. **Thêm Deny có kiểm soát:** đặt priority và phạm vi rõ ràng, giữ các luồng hạ tầng hợp lệ.
6. **Triển khai qua IaC:** quản lý thứ tự, đặt tên, rule priority, ASG membership và NSG associations bằng phiên bản có thể review.
7. **Xác minh trước và sau thay đổi:** kiểm tra effective rules, IP flow verify, kết nối thật và ứng dụng; theo dõi cảnh báo sau triển khai.
8. **Giám sát và rà soát:** lưu tài liệu các ngoại lệ, rà soát các rule `Any`, dọn rule/ASG không còn sử dụng và cập nhật khi VM được mở rộng.

Với những thay đổi có thể làm mất kết nối vào máy chủ, hãy xác định đường truy cập khôi phục độc lập và phương án rollback trước khi áp dụng.

## 12. Bài tập thực hành

Một VNet `10.30.0.0/16` có:

- `snet-web`: `vm-web-01` và `vm-web-02` thuộc `asg-web`.
- `snet-api`: `vm-api-01` thuộc `asg-api`.
- `snet-db`: `vm-db-01` thuộc `asg-db` (database chạy trên VM).

Yêu cầu nghiệp vụ: web gọi API qua TCP 8080; API gọi DB qua TCP 1433. Những VM còn lại không được tùy ý mở kết nối đến hai tầng này.

**Nhiệm vụ:**

1. Lập bảng các rule inbound cần thiết cho subnet API và DB, gồm priority, source ASG, destination ASG, cổng, Allow/Deny.
2. Giải thích vì sao không thể chỉ tạo hai rule Allow và bỏ qua `AllowVnetInBound`.
3. Mô tả cách gán `vm-web-02` vào ASG mà không thay đổi rule đích.
4. Nếu NSG subnet API Allow nhưng NSG NIC API Deny 8080, dự đoán kết quả.
5. Nếu kết nối web → API vẫn thất bại dù IP flow verify cho biết Allow, hãy nêu ít nhất ba nguyên nhân cần kiểm tra.

**Hướng giải:** với API, dùng Allow từ `asg-web` đến `asg-api` trên TCP 8080, sau đó Deny nguồn nội bộ còn lại đến API; với DB, dùng Allow từ `asg-api` đến `asg-db` trên TCP 1433, sau đó Deny các nguồn khác theo chính sách. Xem kỹ thứ tự rule và giữ kết nối vận hành hợp lệ. Gán ASG trên IP configuration của VM mới; không cần thêm IP VM vào NSG rule. Hai cấp NSG đều phải cho phép luồng. Nếu hiệu lực NSG cho phép mà kết nối vẫn lỗi, kiểm tra route, DNS, firewall trong VM và service có lắng nghe cổng hay không.

## 13. Câu hỏi tự kiểm tra

**1. NSG và ASG cái nào trực tiếp Allow/Deny lưu lượng?** NSG. ASG chỉ được dùng làm tiêu chí nguồn/đích trong NSG rule.

**2. Rule priority 120 hay 300 được xét trước?** Priority 120, vì số nhỏ hơn có mức ưu tiên cao hơn.

**3. Vì sao mặc định VM trong cùng VNet có thể kết nối dù chỉ có NSG mới tạo?** Vì NSG mặc định có `AllowVnetInBound` và `AllowVnetOutBound`.

**4. Có cần rule inbound chiều ngược lại cho gói phản hồi của một kết nối outbound đã cho phép không?** Thông thường không; NSG theo dõi trạng thái luồng. Một kết nối mới do phía ngược lại chủ động vẫn cần được đánh giá theo rules.

**5. Gắn một VM vào ASG có tự động chặn traffic khác không?** Không. Phải có NSG rule sử dụng ASG và NSG được áp dụng tại subnet/NIC phù hợp.

**6. Azure SQL Database PaaS có thể được xử lý như một VM thuộc `asg-db` không?** Không. Phải thiết kế bằng khả năng networking của PaaS và các cơ chế hỗ trợ, chẳng hạn private endpoint khi phù hợp.

## 14. Checklist triển khai

- [ ] Đã có sơ đồ VNet, subnet, NIC và luồng kết nối được phép.
- [ ] Đã phân biệt kết nối inbound, outbound và lưu lượng phản hồi stateful.
- [ ] Đã liệt kê cả **custom rules** và **default rules**, đặc biệt `AllowVnetInBound`.
- [ ] Các priority không trùng nhau trong cùng hướng của NSG.
- [ ] Rule giới hạn đúng nguồn, đích, giao thức và cổng cần thiết.
- [ ] Thành viên ASG nằm trong phạm vi VNet được hỗ trợ và gán đúng NIC IP configuration.
- [ ] NSG đã gắn với đúng subnet/NIC; đã kiểm tra các NSG chồng nhau.
- [ ] Đã lưu các Allow cần thiết trước khi áp dụng Deny nội bộ.
- [ ] Đã xác minh effective rules và thử các kết nối được phép/bị chặn.
- [ ] Đã chuẩn bị rollback, giám sát và cách truy cập quản trị an toàn.
- [ ] Đã quản lý cấu hình bằng IaC hoặc một quy trình thay đổi có thể kiểm toán.

## Kết luận

**NSG** là nơi Azure đánh giá các rule Allow/Deny theo hướng, nguồn, đích, cổng, giao thức và priority. **ASG** giúp định nghĩa thành viên theo vai trò ứng dụng để các rule ít phụ thuộc vào địa chỉ IP của từng VM. Khi kết hợp hai cơ chế đúng cách, bạn có thể phân đoạn mạng giữa web, API và database, đồng thời mở rộng hoặc thay thế VM mà vẫn giữ chính sách kết nối nhất quán.

Trong vận hành thực tế, hãy luôn đọc cả các rule mặc định, xét đầy đủ NSG ở subnet và NIC, kiểm tra luồng có hiệu lực bằng Network Watcher và duy trì các biện pháp bảo vệ ở các lớp khác. Thiết kế mạng an toàn cần đi cùng danh tính, TLS, nhật ký, giám sát, khôi phục và quản trị thay đổi của kiến trúc Azure.
