# Private DNS Zone và liên kết với VNet

> **Chương:** Mạng ảo và phân giải tên  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích **Azure Private DNS Zone** là gì, vì sao cần dùng để phân giải tên nội bộ trong Azure Virtual Network (VNet).
2. Phân biệt bản ghi DNS, **virtual network link**, **resolution link** và **registration link**.
3. Mô tả cách máy trong VNet phân giải tên, mối quan hệ giữa zone và nhiều VNet, và giới hạn của VNet peering đối với DNS.
4. Tạo private zone, liên kết với VNet, thêm bản ghi A và xác minh bằng Azure CLI.
5. Hiểu cách kết hợp Private DNS Zone với **Private Endpoint** và **Azure DNS Private Resolver** trong mô hình hybrid.
6. Chẩn đoán lỗi thường gặp và quản lý quyền truy cập, vòng đời bản ghi và chi phí.

## 1. Bài toán: ứng dụng nội bộ cần tên miền ổn định

Giả sử công ty vận hành một hệ thống đặt hàng trên Azure:

- VM hoặc máy chủ chạy API ở địa chỉ riêng `10.20.1.4`.
- Một ứng dụng trong VNet `vnet-app-dev` gọi API này.
- Các môi trường Dev và Prod có địa chỉ IP khác nhau.
- Nhóm vận hành không muốn ghi cố định địa chỉ IP vào mã nguồn.

Ứng dụng nên gọi một tên dễ hiểu như:

~~~text
api.corp.example.com
~~~

Trong VNet Dev, truy vấn có thể cần trả về:

~~~text
api.corp.example.com  →  10.20.1.4
~~~

Ở một môi trường khác, cùng loại dịch vụ có thể dùng tên riêng như `api.prod.corp.example.com` hoặc một private zone khác tùy kiến trúc. Khi IP thay đổi, nhóm vận hành cập nhật bản ghi DNS; ứng dụng không phải sửa cấu hình ở mọi chỗ.

**Azure Private DNS Zone** là dịch vụ lưu trữ và phục vụ các bản ghi DNS dùng trong phạm vi mạng riêng được cấu hình. Private zone được Azure quản lý, nên không phải tự vận hành máy chủ DNS có tính sẵn sàng cao chỉ để phục vụ những tên nội bộ này.

Những vấn đề Private DNS Zone giúp giải quyết:

- Phân giải tên cho workload trong một hoặc nhiều VNet.
- Tách tên logic của dịch vụ khỏi địa chỉ IP riêng.
- Có thể tự động đăng ký bản ghi cho một số máy ảo khi dùng cơ chế registration.
- Hỗ trợ phân giải tên riêng cho dịch vụ truy cập bằng **Azure Private Endpoint**.
- Cho phép xây dựng kiến trúc DNS nội bộ nhiều mạng, nhiều subscription hoặc hybrid khi kết hợp các thành phần chuyển tiếp DNS phù hợp.

**Lưu ý quan trọng:** DNS chỉ dịch tên thành địa chỉ. Có thể phân giải được `10.20.1.4` nhưng vẫn không truy cập được dịch vụ nếu thiếu đường mạng, NSG, firewall hoặc quyền ứng dụng.

## 2. Private DNS Zone là gì?

**DNS zone** là không gian tên chứa các bản ghi DNS thuộc một hậu tố nhất định. Ví dụ, zone `corp.example.com` có thể chứa:

| Record name | Kiểu | Giá trị | Tên đầy đủ (FQDN) |
| --- | --- | --- | --- |
| `api` | A | `10.20.1.4` | `api.corp.example.com` |
| `db` | A | `10.20.2.8` | `db.corp.example.com` |
| `files` | CNAME | `api.corp.example.com` | `files.corp.example.com` |
| `@` | SOA/NS do dịch vụ quản lý | Thông tin zone | `corp.example.com` |

**FQDN** (*Fully Qualified Domain Name*) là tên miền đầy đủ, ví dụ `api.corp.example.com`.

Các khái niệm cần phân biệt:

- **Private DNS Zone:** tài nguyên Azure kiểu `Microsoft.Network/privateDnsZones`, quản lý tập bản ghi DNS riêng.
- **DNS record set:** nhóm bản ghi cùng tên và kiểu, chẳng hạn bản ghi A cho `api`. Một record set có thể chứa nhiều IP.
- **Virtual network link:** tài nguyên nối zone với một VNet để VNet đó có thể phân giải tên trong zone; có thể bật hoặc tắt tự động đăng ký.
- **Azure-provided DNS:** dịch vụ DNS do Azure cung cấp cho các workload trong VNet khi cấu hình mạng sử dụng DNS mặc định của Azure.
- **Custom DNS:** máy chủ DNS do tổ chức tự quản lý hoặc dịch vụ DNS khác; có thể cần conditional forwarding để phân giải các private zone của Azure.

### Private DNS và Public DNS khác nhau thế nào?

| Tiêu chí | Public DNS Zone | Private DNS Zone |
| --- | --- | --- |
| Phạm vi | Tên được phục vụ qua hạ tầng DNS công cộng, theo cấu hình/delegation | Tên được phân giải trong phạm vi mạng có đường DNS riêng phù hợp |
| Dùng VNet link? | Không phải cơ chế chính | Có, để Azure-provided DNS phân giải zone trong VNet |
| Tình huống | Website công cộng, MX cho email | Dịch vụ nội bộ, Private Endpoint |
| Địa chỉ bản ghi | Có thể là IP công cộng hoặc kiểu bản ghi khác | Thường chứa IP riêng nhưng kiểu bản ghi không bị giới hạn chỉ ở IP riêng |
| Quản trị | Phụ thuộc delegation DNS công cộng | Quản lý trong Azure, liên kết với VNet |

Zone `corp.example.com` có thể được dùng làm vùng tên nội bộ; tên ví dụ này không khẳng định bạn sở hữu tên miền công cộng `example.com`. Khi thiết kế cho doanh nghiệp thật, nên sử dụng **subdomain do tổ chức kiểm soát** (ví dụ `internal.company.example`) và có kế hoạch tránh trùng tên với DNS công cộng.

Private DNS Zone được tạo như một tài nguyên trong resource group/subscription, nhưng **không nằm “bên trong” một subnet hoặc VNet**. Muốn VNet sử dụng zone qua Azure-provided DNS, phải tạo **virtual network link**.

## 3. Cấu trúc quan hệ giữa zone, VNet và bản ghi

Ví dụ công ty có hai VNet cùng cần phân giải tên nội bộ:

~~~mermaid
flowchart TD
    Z["Private DNS Zone\ncorp.example.com"]
    R["A: api → 10.20.1.4\nA: db → 10.20.2.8"]
    L1["VNet link dev\nregistrationEnabled: false"]
    L2["VNet link ops\nregistrationEnabled: false"]
    V1["VNet: vnet-app-dev"]
    V2["VNet: vnet-ops"]
    C1["VM / ứng dụng Dev"]
    C2["VM / ứng dụng Ops"]
    Z --> R
    Z --> L1 --> V1 --> C1
    Z --> L2 --> V2 --> C2
~~~

Cả hai VNet có thể phân giải `api.corp.example.com` thành `10.20.1.4` **nếu máy khách dùng đường DNS phù hợp**. Tuy nhiên, truy cập từ Ops VNet tới máy chủ Dev còn phụ thuộc mạng có được kết nối và cho phép lưu lượng hay không.

Ba mối quan hệ cần nhớ:

1. **Zone → record set:** zone có các tên và giá trị cần phân giải.
2. **Zone → VNet link:** VNet được liên kết sẽ có phạm vi phân giải tên zone khi sử dụng Azure-provided DNS.
3. **VNet → đường mạng:** peering, routing, VPN/ExpressRoute, NSG hoặc firewall quyết định máy khách có thực sự kết nối tới IP được trả về không.

Một private zone có thể liên kết với nhiều VNet theo các điều kiện và hạn mức dịch vụ hiện hành. Một VNet cũng có thể liên kết với các private zone mang tên khác nhau phù hợp với thiết kế.

### Link không đồng nghĩa với VNet peering

**VNet peering** kết nối các VNet để các endpoint có thể trao đổi dữ liệu theo định tuyến và chính sách. **Private DNS virtual network link** cho phép phân giải tên zone trong một VNet.

Hai cơ chế độc lập:

- Peering **không tự động chuyển tiếp quyền phân giải private zone** cho VNet còn lại.
- DNS link **không tạo route hoặc quyền truy cập mạng** giữa hai VNet.
- Muốn VNet A và B cùng phân giải zone bằng Azure-provided DNS, thường phải tạo link từ **cả A và B** đến zone (hoặc thiết kế DNS forwarding trung tâm thay thế).
- Muốn truy cập IP đích, cần thêm kết nối mạng thực tế.

Ví dụ, sau khi link cả hai VNet, `nslookup api.corp.example.com` trên một VM ở Ops VNet có thể trả `10.20.1.4`, trong khi `curl` đến API vẫn timeout vì không có định tuyến hoặc bị firewall chặn.

## 4. Resolution link và registration link

Khi liên kết zone với VNet, thuộc tính quan trọng là `registrationEnabled`.

| Thuộc tính | Resolution link | Registration link |
| --- | --- | --- |
| `registrationEnabled` | `false` | `true` |
| Phân giải bản ghi của zone | Có | Có |
| Tự động tạo/cập nhật một số A record của VM trong VNet | Không | Có, trong phạm vi tính năng hỗ trợ |
| Đối tượng phù hợp | VNet sử dụng dịch vụ, mạng quản trị, VNet có Private Endpoint | VNet có máy ảo muốn đăng ký hostname tự động |
| Với private zone dành cho Private Endpoint | Thông dụng | Không dùng auto-registration cho Private Endpoint |

### Resolution link: chỉ cần phân giải tên

Với `registrationEnabled: false`, các máy khách trong VNet có thể hỏi Azure DNS về bản ghi có trong zone, nhưng Azure **không tự động đăng ký hostname của các VM thuộc VNet đó** vào zone.

Trường hợp sử dụng:

- Nhiều VNet ứng dụng cùng cần truy cập một API nội bộ.
- VNet có VM vận hành cần phân giải tên máy chủ ở VNet khác.
- Kết nối zone dành cho Private Endpoint với VNet nơi ứng dụng sẽ thực hiện truy vấn.

### Registration link: đăng ký tên VM

Với `registrationEnabled: true`, Azure hỗ trợ tự động quản lý **bản ghi A cho các Azure VM thuộc VNet được liên kết**, bao gồm cập nhật/xóa bản ghi trong những tình huống vòng đời máy ảo được hỗ trợ. Registration link đồng thời có khả năng phân giải tên như resolution link.

Điều này hữu ích khi VM thường xuyên được tạo hoặc xóa. Tuy nhiên:

- **Không áp dụng cho mọi tài nguyên Azure.** Việc tạo App Service, Azure SQL Database hay Private Endpoint không đương nhiên kích hoạt cơ chế đăng ký VM.
- Không sử dụng tính năng tự đăng ký VM để thay thế **Private DNS zone group** dành cho Private Endpoint.
- Các giới hạn liên kết, trùng tên và đặc điểm hostname cần được kiểm tra theo thiết kế và tài liệu sản phẩm đang áp dụng.
- Không nên mặc định VM sẽ có tên theo cách ứng dụng mong muốn nếu hostname và quy ước DNS chưa được thiết kế.

**Quy tắc lựa chọn:** Nếu chỉ cần một VNet **đọc** bản ghi trong zone, dùng resolution link. Chỉ bật auto-registration khi thực sự cần và đã hiểu cách VM được đăng ký.

## 5. Luồng phân giải tên từ máy trong VNet

Giả sử:

- Zone: `corp.example.com`.
- Record: `api.corp.example.com A 10.20.1.4`.
- VNet: `vnet-app-dev` đã được liên kết với zone.
- VM sử dụng thiết lập DNS mặc định của Azure.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng trong VNet
    participant DNS as Azure-provided DNS
    participant Zone as Private DNS Zone
    participant API as API 10.20.1.4
    App->>DNS: Tra api.corp.example.com
    DNS->>Zone: Tìm record trong zone đã liên kết
    Zone-->>DNS: A = 10.20.1.4
    DNS-->>App: Trả IP riêng
    App->>API: Kết nối tới 10.20.1.4
    Note over App,API: Kết nối chỉ thành công nếu mạng và bảo mật cho phép
~~~

Trong VNet sử dụng Azure DNS mặc định, Azure-provided DNS có thể xử lý bản ghi thuộc private zone đã link. Địa chỉ dịch vụ DNS do Azure cung cấp thường được tài liệu hóa là `168.63.129.16`; đây là địa chỉ nền tảng đặc biệt, **không phải máy chủ DNS công cộng để thiết bị bất kỳ trên Internet truy vấn**.

### Nếu máy dùng custom DNS thì sao?

VNet có thể được cấu hình DNS server riêng, chẳng hạn một domain controller của Active Directory hoặc dịch vụ DNS doanh nghiệp. Khi đó:

- Máy khách thường gửi truy vấn tới **custom DNS**, không tự hỏi Azure-provided DNS.
- Custom DNS cần biết cách phân giải zone nội bộ; một mẫu thiết kế là **conditional forwarding** những hậu tố thích hợp qua DNS forwarder trong Azure hoặc **Azure DNS Private Resolver**.
- Khi dùng DNS forwarder trên Azure VM, điểm forward tới Azure DNS (`168.63.129.16`) cần có **ngữ cảnh VNet được link với private zone**.
- DNS từ mạng on-premises không nên được thiết kế forward trực tiếp đến `168.63.129.16`. Thay vào đó, dùng inbound endpoint của Private Resolver hoặc máy forwarder có thể nhận truy vấn qua kết nối riêng được cấu hình.

**Dấu hiệu chẩn đoán:** Một VNet đã link zone nhưng `nslookup` vẫn trả `NXDOMAIN` hoặc bản ghi công cộng. Hãy kiểm tra DNS server thực tế của máy khách trước khi thay đổi zone.

### DNS caching và TTL

DNS resolver và ứng dụng có thể cache câu trả lời đến khi hết **TTL** (*Time To Live*). Sau khi thay đổi bản ghi, kết quả ở các máy khách có thể chưa cập nhật đồng thời.

Nên chọn TTL theo tốc độ thay đổi IP và nhu cầu ổn định; không mặc định rằng cập nhật bản ghi đồng nghĩa mọi máy sẽ thấy IP mới ngay lập tức.

## 6. Thực hành tạo Private DNS Zone và link với VNet bằng Azure CLI

Ví dụ dưới đây dùng tên giả định và dải IP nội bộ. Phần tạo zone/record/link **là thao tác thay đổi tài nguyên có thể phát sinh chi phí**; chỉ chạy trong subscription thực hành được phép. Các lệnh dưới đây giả định VNet `vnet-app-dev` đã tồn tại trong resource group `rg-app-dev` và bạn có đủ quyền trên cả zone lẫn VNet.

### 6.1. Chuẩn bị subscription và định danh mạng

Trước khi thay đổi, xác nhận subscription hiện tại:

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Nếu cần, chọn đúng subscription đã được phân công.
az account set --subscription "<SUBSCRIPTION_ID>"

# Lấy resource ID để liên kết đúng VNet, kể cả khi zone ở resource group khác.
VNET_ID=$(az network vnet show \
  --resource-group rg-app-dev \
  --name vnet-app-dev \
  --query id \
  --output tsv)

echo "$VNET_ID"
~~~

Đầu ra phải có dạng:

~~~text
/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-app-dev/providers/Microsoft.Network/virtualNetworks/vnet-app-dev
~~~

Nếu không lấy được VNet ID, hãy kiểm tra tên, subscription và quyền đọc VNet; đừng đoán Resource ID.

### 6.2. Tạo zone

Trong resource group dành cho DNS đã tồn tại, ví dụ `rg-dns-lab`:

~~~bash
az network private-dns zone create \
  --resource-group rg-dns-lab \
  --name corp.example.com

az network private-dns zone show \
  --resource-group rg-dns-lab \
  --name corp.example.com \
  --output json
~~~

Tạo zone **chưa tự động làm zone có hiệu lực với mọi VNet**. Bước tiếp theo cần tạo link.

### 6.3. Tạo resolution link

~~~bash
az network private-dns link vnet create \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --name link-vnet-app-dev \
  --virtual-network "$VNET_ID" \
  --registration-enabled false
~~~

Xác minh link:

~~~bash
az network private-dns link vnet list \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --output table
~~~

Các trường cần xem gồm tên link, trạng thái provisioning, VNet liên kết và chế độ registration. Nếu cần thêm VNet khác, tạo link thứ hai tới đúng VNet ID, với tên link duy nhất trong zone. Link có thể đi qua resource group hoặc subscription phù hợp khi quyền và chính sách cho phép; không nhất thiết phải đặt zone cùng resource group với VNet.

### 6.4. Tạo bản ghi A cho một API nội bộ

~~~bash
# Tạo record set với TTL 300 giây.
az network private-dns record-set a create \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --name api \
  --ttl 300

# Thêm địa chỉ IPv4 riêng của API.
az network private-dns record-set a add-record \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --record-set-name api \
  --ipv4-address 10.20.1.4

# Xem lại bản ghi vừa tạo.
az network private-dns record-set a show \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --name api \
  --output json
~~~

Trong zone `corp.example.com`, record set `api` tạo tên đầy đủ:

~~~text
api.corp.example.com  A  10.20.1.4
~~~

IP `10.20.1.4` chỉ là ví dụ; bản ghi thực tế phải trỏ tới địa chỉ của một endpoint tồn tại và được định tuyến đúng.

### 6.5. Xác minh trong VNet

Đăng nhập vào một VM được phép quản trị nằm trong `vnet-app-dev` và sử dụng Azure-provided DNS, sau đó chạy:

~~~bash
# Công cụ có thể có tùy hệ điều hành.
nslookup api.corp.example.com

# Trên Linux, nếu đã có dig:
dig api.corp.example.com A +short
~~~

Kết quả kỳ vọng:

~~~text
10.20.1.4
~~~

Lệnh `az network private-dns record-set a show` xác nhận **bản ghi tồn tại**. `nslookup` từ một VM trong VNet xác nhận **đường phân giải của máy khách** thực sự hoạt động. Đây là hai phép kiểm tra khác nhau.

Nếu VM dùng custom DNS, bước này chỉ thành công sau khi custom DNS được cấu hình forwarding đúng như mô tả ở mục 5.

### 6.6. Khi nào dùng registration link?

Ở một VNet chuyên chạy VM mà bạn muốn đăng ký hostname tự động, tạo link với `--registration-enabled true` thay vì `false`:

~~~bash
# VNET_VM_ID phải là resource ID của VNet dành cho VM,
# không sử dụng tên VNet thực nếu chưa xác nhận.
az network private-dns link vnet create \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --name link-vnet-vm-registration \
  --virtual-network "$VNET_VM_ID" \
  --registration-enabled true
~~~

Đây là **lựa chọn thay thế trong một thiết kế có VNet phù hợp**, không phải yêu cầu bắt buộc của bài thực hành. Trước khi chạy, thiết lập `VNET_VM_ID` cho VNet thực sự cần tự đăng ký và kiểm tra các liên kết hiện có để tránh cấu hình xung đột.

### 6.7. Dọn dẹp tài nguyên thực hành

Khi không còn dùng và đã xác minh đây là tài nguyên lab, gỡ các link của zone trước, sau đó xóa các record set do lab tạo và zone (nếu zone không phục vụ workload khác). Có thể sử dụng Azure portal hoặc các lệnh quản trị tương ứng. **Không xóa private zone đang phục vụ nhiều VNet/Private Endpoint** vì việc mất khả năng phân giải tên có thể làm gián đoạn ứng dụng.

## 7. Private DNS Zone và Private Endpoint

Một ứng dụng thường cần kết nối **Azure Storage, Azure SQL, Key Vault** hoặc dịch vụ PaaS qua IP riêng. Khi dùng **Azure Private Endpoint**, kết nối đến dịch vụ được đưa vào VNet bằng một network interface có IP riêng.

Trong trường hợp này, DNS rất quan trọng: ứng dụng vẫn dùng tên dịch vụ quen thuộc, nhưng tên đó cần phân giải thành **IP của private endpoint** từ nơi ứng dụng chạy.

### Ví dụ: Azure Blob Storage qua Private Endpoint

Giả sử storage account có tên `stappdemo001`, private endpoint được cấp IP `10.20.3.5`. Ứng dụng gọi:

~~~text
stappdemo001.blob.core.windows.net
~~~

Trong cấu hình Private Link được hỗ trợ, chuỗi CNAME của tên dịch vụ công cộng có thể dẫn đến tên thuộc hậu tố Private Link:

~~~text
stappdemo001.blob.core.windows.net
  → stappdemo001.privatelink.blob.core.windows.net
  → 10.20.3.5
~~~

Bản ghi A riêng thường nằm trong zone:

~~~text
privatelink.blob.core.windows.net
~~~

Ví dụ record set:

~~~text
stappdemo001  A  10.20.3.5
~~~

Các zone và subresource được hỗ trợ khác nhau theo từng dịch vụ; **phải chọn đúng DNS zone được Microsoft quy định cho loại Private Endpoint**. Một số dịch vụ có nhiều subresource với các zone khác nhau.

~~~mermaid
flowchart LR
    APP["Ứng dụng trong VNet"]
    RES["DNS resolver\ncó đường phân giải private zone"]
    ZONE["Private DNS Zone\nprivatelink.blob.core.windows.net"]
    PE["Private Endpoint\n10.20.3.5"]
    ST["Azure Storage\nstappdemo001"]
    APP -->|"Query storage FQDN"| RES
    RES -->|"Private Link tên nội bộ"| ZONE
    ZONE -->|"A = 10.20.3.5"| APP
    APP -->|"Kết nối IP riêng"| PE --> ST
~~~

**Các bước triển khai theo logic:**

1. Tạo private endpoint cho đúng storage account và subresource (`blob`).
2. Chọn hoặc tạo private zone `privatelink.blob.core.windows.net`.
3. Liên kết private zone với VNet có máy khách cần phân giải tên (hoặc thiết lập đường DNS forwarding phù hợp).
4. Cấu hình **Private DNS zone group** cho private endpoint khi sử dụng tích hợp tự động được hỗ trợ để quản lý record tương ứng.
5. Từ workload trong VNet, kiểm tra rằng **tên dịch vụ gốc** phân giải thành IP riêng của private endpoint.
6. Kiểm tra kết nối tới dịch vụ và chính sách truy cập của dịch vụ.

### Private DNS zone group khác registration link

| Cơ chế | Đối tượng | Tác dụng chính |
| --- | --- | --- |
| **Registration link** của zone | Azure VM trong VNet gắn link | Tự động đăng ký A record cho VM khi được hỗ trợ |
| **Private DNS zone group** của private endpoint | Tài nguyên private endpoint | Quản lý bản ghi DNS private cho dịch vụ PaaS theo tích hợp hỗ trợ |
| **Resolution link** của zone | VNet có máy khách | Cho phép Azure-provided DNS phân giải bản ghi của zone |

Với Private Endpoint, cấu hình phổ biến là **zone group + resolution links**, không phải bật auto-registration VM.

### Những nhầm lẫn nguy hiểm ở Private Link

- **Có private endpoint không có nghĩa DNS đã đúng.** Kết nối có thể vẫn phân giải tới địa chỉ công cộng nếu zone/link/forwarder sai.
- **Có DNS A record riêng không có nghĩa Private Endpoint đã được tạo.** DNS không tự bảo vệ kết nối dữ liệu.
- **Không nên tự tạo tràn lan cùng tên zone cho nhiều endpoint mà không có kế hoạch dùng chung.** Các bản ghi có thể khó quản lý hoặc xung đột khi nhiều VNet và nhiều endpoint cùng một dịch vụ.
- **Không nên tự ý sửa/xóa record do zone group quản lý**, vì tích hợp có thể cập nhật record theo vòng đời private endpoint.
- Private Endpoint còn chịu ảnh hưởng của **network routing, NSG, DNS, cài đặt dịch vụ và xác thực/ủy quyền**; kiểm tra từng lớp khi xử lý sự cố.

## 8. Nhiều VNet, hub-spoke và DNS hybrid

### 8.1. Hai VNet độc lập cùng dùng một zone

Một zone `corp.example.com` có thể được link tới `vnet-dev` và `vnet-ops` để hai mạng cùng phân giải bản ghi. Nếu máy ở `vnet-ops` cần truy cập endpoint `10.20.1.4` trong `vnet-dev`, phải có kết nối mạng thực tế như peering hoặc đường routing phù hợp.

**Peering không làm các link DNS được kế thừa**. Thiết kế giải quyết DNS cần được xem xét riêng cho từng VNet.

### 8.2. Hub-spoke dùng Azure-provided DNS

Trong mô hình hub-spoke, các workload có thể chạy ở những spoke VNets, còn network firewall hoặc shared services ở hub VNet. Nếu từng spoke dùng Azure-provided DNS và cần phân giải zone, cách đơn giản là **link zone trực tiếp với các spoke đó**.

Không nên giả định chỉ link zone với hub rồi peering mọi spoke là tất cả spoke đều phân giải được bản ghi. Cũng không cần tạo zone mới trong mỗi spoke nếu một zone chung đáp ứng đúng nhu cầu và ranh giới quản trị.

### 8.3. Hub-spoke với custom DNS

Nếu doanh nghiệp dùng DNS server riêng trong hub, máy ở spoke có thể hỏi DNS hub. Khi đó:

- VNet của máy chủ DNS forwarder phải có cách phân giải zone cần phục vụ.
- Máy chủ DNS cần được cấu hình conditional forwarding đúng hậu tố.
- Network/NSG cần cho phép lưu lượng DNS UDP/TCP 53 theo thiết kế.
- Cần tính đến tính sẵn sàng, đường truyền và quyền vận hành của máy chủ DNS.

Mọi link đến zone không tự khắc phục được sự cố nếu máy khách chỉ hỏi custom DNS mà custom DNS không biết đi tiếp đâu.

### 8.4. Hybrid: từ on-premises tới private zone trong Azure

Máy chủ tại trung tâm dữ liệu có thể muốn truy vấn `api.corp.example.com` trong Azure qua VPN hoặc ExpressRoute.

**Azure DNS Private Resolver** hỗ trợ triển khai DNS forwarding có quản lý, thường dùng:

- **Inbound endpoint:** một địa chỉ IP riêng trong VNet để DNS server từ mạng khác có kết nối riêng gửi truy vấn tới Azure.
- **Outbound endpoint:** thành phần gửi truy vấn qua **DNS forwarding ruleset** tới các DNS server đích theo quy tắc.
- **Forwarding ruleset:** ánh xạ hậu tố tên miền tới đích chuyển tiếp và liên kết ruleset với các VNet cần áp dụng.

Một luồng ví dụ:

~~~mermaid
flowchart LR
    ONP["Máy chủ nội bộ\non-premises"]
    AD["DNS doanh nghiệp\nconditional forward"]
    VPN["VPN / ExpressRoute"]
    IN["Private Resolver\ninbound endpoint trong hub"]
    Z["Private DNS Zone\ncorp.example.com"]
    APP["API trong Azure\n10.20.1.4"]
    ONP --> AD --> VPN --> IN
    IN -->|"Tra private zone đã link với resolver VNet"| Z
    Z -->|"10.20.1.4"| ONP
    ONP -.->|"Kết nối dữ liệu qua mạng riêng"| APP
~~~

Zone cần được liên kết thích hợp với VNet nơi luồng phân giải thông qua resolver diễn ra. Máy DNS on-premises chuyển tiếp tới **IP inbound endpoint có thể định tuyến qua mạng riêng**, không gửi trực tiếp đến `168.63.129.16`.

Trong chiều ngược lại, một ứng dụng Azure muốn phân giải tên AD/on-prem có thể cần **outbound endpoint + forwarding ruleset** trỏ đến DNS doanh nghiệp. Cấu hình này độc lập với việc tạo private zone và chỉ cần khi có nhu cầu.

### 8.5. Phân biệt DNS Private Resolver và Private DNS Zone

- **Private DNS Zone** là **nơi lưu trữ các record**.
- **Private DNS Resolver** là **thành phần xử lý/chuyển tiếp truy vấn DNS** giữa các môi trường theo kiến trúc cần thiết.
- **VNet peering/VPN/ExpressRoute** tạo kết nối truyền dữ liệu giữa các mạng, nhưng **không tự động tạo quy tắc phân giải DNS**.

## 9. Thiết kế thực tế: đặt tên, tổ chức tài nguyên và bảo mật

### 9.1. Quy ước tên

Một chiến lược đặt tên tốt giúp tránh xung đột giữa môi trường và giảm tác động khi di chuyển dịch vụ.

Ví dụ:

| Phạm vi | Zone hoặc FQDN ví dụ | Lý do |
| --- | --- | --- |
| Ứng dụng nội bộ chung | `corp.example.com` | Dễ chia sẻ giữa nhiều VNet |
| Hệ thống Dev | `dev.corp.example.com` | Tách vòng đời bản ghi khỏi Prod |
| Hệ thống Prod | `prod.corp.example.com` | Hạn chế tác động đổi bản ghi Dev |
| Blob Storage private endpoint | `privatelink.blob.core.windows.net` | Tuân theo hậu tố Private Link của dịch vụ |
| Tên dịch vụ | `api.prod.corp.example.com` | Dễ nhận diện môi trường và chức năng |

Nên dùng subdomain thuộc miền tổ chức quản lý. Hạn chế chọn hậu tố trùng với tên ngoài ý muốn hoặc một vùng mà các máy chủ DNS khác đang quản trị không thống nhất.

### 9.2. Vị trí quản trị và quyền

Private zone là Azure resource độc lập. Có thể đặt zone trong một resource group quản lý mạng dùng chung, còn VNet và workload ở resource group khác. Các thao tác quản trị có thể cần quyền trên **private zone, VNet và private endpoint**, tùy hành động.

Áp dụng Azure RBAC:

- Nhóm quản trị mạng được phép tạo/đổi zone và VNet link theo phạm vi thích hợp.
- Nhóm ứng dụng chỉ được cập nhật bản ghi mà họ thực sự cần quản lý, qua cơ chế quyền đã thiết kế.
- Người truy vấn trong VNet **không tự động có quyền thay đổi DNS resource** chỉ vì VNet được liên kết.
- Hạn chế thay đổi thủ công record của private endpoint khi record được quản lý tự động.

Vì zone có thể phục vụ nhiều môi trường, mọi thay đổi hoặc xóa zone cần được đánh giá tác động chéo các VNet.

### 9.3. DNS không thay thế bảo mật mạng

Một private zone **không tự làm dịch vụ trở nên riêng tư hoặc an toàn**. Nếu máy chủ vẫn lộ public endpoint và firewall cho phép, thay đổi DNS không chặn đường truy cập công cộng.

Cần phối hợp:

- Network security group (NSG) và routing.
- Azure Firewall hoặc firewall tương đương nếu kiến trúc sử dụng.
- Private Endpoint với cấu hình public network access thích hợp khi dịch vụ hỗ trợ.
- Xác thực và phân quyền tại ứng dụng/dịch vụ.
- Nhật ký DNS, log kết nối và các cơ chế giám sát theo khả năng sản phẩm.

Private DNS Zone phục vụ **name resolution**, không phải chính sách firewall.

### 9.4. Lưu ý chi phí

Các thành phần có thể ảnh hưởng ngân sách:

| Thành phần | Nguồn phát sinh chi phí cần kiểm tra |
| --- | --- |
| Azure Private DNS | Số zone được lưu trữ, số DNS query và các điều kiện tính phí hiện hành |
| Azure DNS Private Resolver | Inbound/outbound endpoint, forwarding ruleset và mức sử dụng theo cơ chế giá áp dụng |
| VNet peering/VPN/ExpressRoute | Lưu lượng kết nối mạng, cổng hoặc kết nối theo mô hình tính phí |
| VM DNS forwarder tự quản lý | Máy ảo, đĩa, networking và vận hành |
| Private Endpoint | Tài nguyên endpoint và lưu lượng theo giá dịch vụ tương ứng |

**Giá thực tế phụ thuộc region và chính sách giá đang áp dụng.** Không dùng bản ghi DNS nhiều lần hay chỉ dựa trên số VNet link để tự suy ra tổng hóa đơn.

## 10. Xử lý sự cố DNS theo từng lớp

Khi ứng dụng không tìm được tên hoặc kết nối thất bại, nên kiểm tra từ **bản ghi → liên kết → DNS client → đường mạng → dịch vụ**.

| Triệu chứng | Khả năng thường gặp | Cách kiểm chứng |
| --- | --- | --- |
| `NXDOMAIN` từ VM | Zone chưa link, record không có, sai FQDN, DNS server khác đang trả lời | Kiểm tra record, VNet link và DNS server thực tế |
| `nslookup` trả IP công cộng | Máy hỏi public/custom DNS; cấu hình private zone hoặc forwarding chưa đúng | So sánh truy vấn từ VM ở VNet link, kiểm tra Private Endpoint DNS |
| Đúng IP riêng nhưng kết nối timeout | Thiếu route, NSG/firewall chặn, endpoint không hoạt động | Kiểm tra network path và TCP reachability |
| VNet A phân giải được, VNet B không | Chỉ A có DNS link; peering không mang theo link DNS | Kiểm tra mỗi VNet và mô hình DNS của B |
| Tên VM chưa tự xuất hiện | Link đang là resolution; VM chưa được hỗ trợ đăng ký hoặc chưa đúng VNet | Kiểm tra `registrationEnabled` và vòng đời VM |
| Máy on-prem không phân giải zone Azure | Chưa có conditional forwarder, inbound resolver hoặc kết nối | Kiểm tra IP DNS đích và network path qua VPN/ER |
| Trả IP cũ sau khi cập nhật | Cache client/resolver hoặc TTL | So sánh bản ghi trong zone và thời gian TTL |
| Private Endpoint có nhưng DNS sai | Chưa cấu hình zone group, sai private zone hoặc VNet link | Kiểm tra record A, zone group và FQDN ứng dụng đang dùng |
| Query tới máy chủ DNS phản hồi khác nhau | Chưa đồng nhất hệ thống DNS/custom server, forwarding hoặc cache | Ghi lại server trả lời, cấu hình từng DNS server |

### Quy trình chẩn đoán mẫu

**Bước 1: Kiểm tra record trên Azure.**

~~~bash
az network private-dns record-set a show \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --name api \
  --output json
~~~

Nếu record không có hoặc IP sai, sửa nguồn dữ liệu zone theo quy trình quản trị.

**Bước 2: Kiểm tra các virtual network links.**

~~~bash
az network private-dns link vnet list \
  --resource-group rg-dns-lab \
  --zone-name corp.example.com \
  --output json
~~~

Xác nhận đúng VNet cần phân giải, trạng thái link và registration mode.

**Bước 3: Xem máy đang hỏi DNS nào.**

Trên Linux:

~~~bash
cat /etc/resolv.conf
nslookup api.corp.example.com
~~~

`/etc/resolv.conf` có thể chỉ hiển thị local stub resolver (ví dụ systemd-resolved); khi cần phải xem cấu hình DNS upstream thực sự bằng công cụ của hệ điều hành, như `resolvectl status`. Trên Windows dùng `ipconfig /all` và `nslookup` để xem thông tin DNS.

**Bước 4: Đối chiếu địa chỉ trả về với kết nối.**

Nếu DNS đúng `10.20.1.4` nhưng API không truy cập được, kiểm tra port, định tuyến, NSG, firewall, máy chủ/dịch vụ và xác thực; tiếp tục sửa DNS có thể không giải quyết được.

**Bước 5: Ghi nhận TTL và phạm vi.**

Thử từ hai VM khác nhau có cùng/different DNS path và ghi thời điểm kiểm tra. Từ laptop ngoài Azure không được thiết kế truy cập DNS nội bộ, `nslookup` thất bại có thể là bình thường.

## 11. Bài thực hành tổng hợp: hai VNet dùng chung DNS nội bộ

### Bối cảnh

Một ứng dụng gồm API nội bộ ở Dev VNet và một máy vận hành ở Ops VNet:

- Zone: `corp.example.com`.
- Dev VNet: `vnet-app-dev`, VM API có IP `10.20.1.4`.
- Ops VNet: `vnet-ops`, máy vận hành cần phân giải `api.corp.example.com`.
- Hai VNet có thể được kết nối bằng peering theo cấu hình mạng và quyền được phê duyệt.

### Yêu cầu

1. Vẽ sơ đồ gồm một private zone, hai VNet link và bản ghi A cho `api`.
2. Quyết định hai link nên bật `registrationEnabled` hay không; giải thích dựa trên nhu cầu.
3. Dùng lệnh ở mục 6 để tạo zone, bản ghi A và link cho Dev. Với Ops, liên kết bằng một resource ID VNet khác đã xác minh.
4. Từ VM trong từng VNet, chạy `nslookup api.corp.example.com` và ghi IP trả về.
5. Thử kết nối tới API bằng cổng hợp lệ và kiểm tra khác biệt giữa **phân giải tên** và **khả năng kết nối mạng**.
6. Thảo luận điều gì xảy ra khi xóa link Ops, khi thay IP bản ghi hoặc khi Ops dùng custom DNS mà chưa cấu hình forwarding.

### Đáp án mẫu và kỳ vọng

| Câu hỏi | Đáp án |
| --- | --- |
| Hai link nên dùng loại nào? | **Resolution** (`registrationEnabled=false`) vì chỉ cần đọc record; không yêu cầu đăng ký VM |
| VM Dev phân giải tên ra gì? | `10.20.1.4` nếu bản ghi/link/DNS client đúng |
| VM Ops có thể phân giải tên không? | Có, nếu link Ops đúng và máy hỏi DNS có đường tới zone |
| Phân giải được thì API có chắc hoạt động? | Không; cần peering/routing, NSG/firewall và dịch vụ |
| Xóa Ops link sẽ thế nào? | Máy dùng Azure DNS trong Ops không còn quyền phân giải qua link đó, trừ khi có giải pháp DNS khác; cache có thể còn tác dụng nhất thời |
| Thay record A tác động ra sao? | Câu trả lời mới theo TTL/cache, có thể ảnh hưởng mọi VNet đang dùng cùng zone |
| Ops dùng custom DNS nhưng chưa forward? | Truy vấn có thể không tìm đúng record mặc dù zone vẫn được link |

### Câu hỏi nâng cao: chuyển API sang Private Endpoint

Nếu thay vì VM API, ứng dụng dùng Blob Storage qua Private Endpoint, cần thay đổi những gì?

- Zone phải dùng **tên Private Link phù hợp với dịch vụ**, chẳng hạn `privatelink.blob.core.windows.net` cho Blob.
- Bản ghi tương ứng được quản lý qua **private DNS zone group** nếu dùng tích hợp được hỗ trợ.
- Workload tiếp tục gọi **tên dịch vụ gốc**, ví dụ `stappdemo001.blob.core.windows.net`, và kiểm tra nó phân giải về private endpoint IP.
- Các VNet chứa máy khách được cấu hình resolution link hoặc đường DNS forwarding phù hợp.
- Vẫn kiểm tra routing, firewall, xác thực và cấu hình public network access của dịch vụ.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Private DNS Zone đã tạo nhưng không liên kết với VNet nào. VM trong VNet tự động phân giải được record bằng Azure-provided DNS không?

**Đáp án:** Không nên giả định là có. Cần VNet link tương ứng hoặc một thiết kế DNS forwarding có thể phân giải zone đó.

**Câu 2.** Bật VNet peering giữa Dev và Prod có khiến Prod tự động dùng private zone đã liên kết với Dev không?

**Đáp án:** Không. Peering là kết nối mạng, còn quyền phân giải zone qua Azure-provided DNS đến từ VNet link hoặc đường DNS khác được cấu hình.

**Câu 3.** `registrationEnabled=true` có tự đăng ký Private Endpoint vào zone không?

**Đáp án:** Không. Auto-registration trong VNet link phục vụ VM theo phạm vi hỗ trợ. Private Endpoint có cơ chế Private DNS zone group riêng.

**Câu 4.** `nslookup` trả đúng IP riêng nhưng ứng dụng vẫn timeout. Bạn kiểm tra gì tiếp theo?

**Đáp án:** Kiểm tra IP/port đích, route, peering/VPN, NSG/firewall và tình trạng dịch vụ. DNS đã giải được một phần của vấn đề.

**Câu 5.** Máy trong VNet dùng DNS server doanh nghiệp và không phân giải được private zone dù link có tồn tại. Vì sao?

**Đáp án:** Máy hỏi custom DNS; server này chưa có khả năng trả lời hoặc forward truy vấn tới Azure DNS qua ngữ cảnh được cấu hình đúng.

**Câu 6.** Máy chủ on-prem có thể đặt conditional forward trực tiếp tới `168.63.129.16` để giải quyết mọi Private DNS Zone của Azure không?

**Đáp án:** Không nên thiết kế như vậy. Đây là địa chỉ DNS nền tảng của Azure với yêu cầu ngữ cảnh VNet; phía on-prem thường cần forward tới Azure DNS Private Resolver inbound endpoint hoặc DNS forwarder trong Azure có kết nối mạng phù hợp.

## Ghi nhớ

- **Private DNS Zone** là nơi quản lý bản ghi DNS riêng; **VNet link** kết nối zone với mạng sử dụng nó.
- **Resolution link** giúp phân giải tên; **registration link** đồng thời bật tính năng tự đăng ký bản ghi VM được hỗ trợ.
- **VNet peering không tự tạo DNS link**, và DNS link không tự tạo đường mạng.
- Với **Private Endpoint**, dùng đúng hậu tố Private Link, DNS zone group và resolution link/forwarding để trả IP riêng cho tên dịch vụ.
- Khi dùng **custom DNS** hoặc hệ thống on-premises, cần thiết kế forwarding; Azure DNS Private Resolver giúp kết nối các miền DNS trong kiến trúc hybrid.
- Kiểm tra lỗi theo thứ tự **record → link → DNS client/forwarder → IP → network/security → ứng dụng**, đồng thời quản trị quyền, TTL, chi phí và ảnh hưởng của thay đổi DNS.
