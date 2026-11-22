# Subnet, IP công cộng và IP riêng

Khi xây dựng một ứng dụng trên Microsoft Azure, các thành phần như máy ảo, dịch vụ web, cơ sở dữ liệu và hệ thống quản trị phải giao tiếp với nhau theo những đường mạng được kiểm soát. Ba khái niệm quan trọng để thiết kế mạng đó là **subnet (mạng con)**, **địa chỉ IP riêng (private IP)** và **địa chỉ IP công cộng (public IP)**.

Ví dụ, một hệ thống bán hàng có thể tiếp nhận người dùng từ Internet thông qua một điểm vào công cộng, trong khi máy chủ xử lý đơn hàng và cơ sở dữ liệu chỉ sử dụng các kết nối riêng. Thiết kế phù hợp giúp giảm bề mặt tấn công, kiểm soát luồng dữ liệu, triển khai mở rộng và giám sát chi phí. Bài học thuộc chương *Mạng ảo và phân giải tên*, đồng thời đặt nền tảng cho các kiến trúc Azure kết hợp Virtual Network, Azure DNS, App Service, máy ảo, lưu trữ và dữ liệu.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích mối quan hệ giữa Azure Virtual Network (VNet), subnet và địa chỉ IP.
2. Đọc và tính số địa chỉ IPv4 trong dải CIDR, kể cả các địa chỉ Azure dành riêng.
3. Phân biệt IP riêng, IP công cộng và cách cấp phát động hoặc tĩnh.
4. Hiểu đường truy cập vào/ra Internet của tài nguyên Azure và vai trò của NAT Gateway, NSG, DNS.
5. Thiết kế các subnet không chồng lấn cho một ứng dụng nhiều lớp.
6. Tạo, xem và kiểm tra VNet, subnet, Public IP bằng Azure portal hoặc Azure CLI.
7. Nhận diện lỗi cấu hình thường gặp và kiểm tra kết nối an toàn.

## 1. VNet, subnet và địa chỉ IP liên hệ với nhau như thế nào?

**Azure Virtual Network (VNet)** là nền tảng mạng riêng logic dành cho tài nguyên Azure. Khi tạo VNet, bạn khai báo một hoặc nhiều dải địa chỉ IP để các thành phần bên trong sử dụng. Sau đó, chia các dải này thành **subnet**, mỗi subnet đại diện cho một phần của không gian địa chỉ VNet.

Ví dụ:

~~~text
VNet: vnet-sales            10.42.0.0/16
  |
  +-- snet-ingress          10.42.0.0/24
  +-- snet-web              10.42.1.0/24
  +-- snet-app              10.42.2.0/24
  +-- snet-private-endpoint 10.42.3.0/27
~~~

Trong thiết kế này, tất cả subnet đều nằm bên trong không gian địa chỉ VNet và không chồng lấn. Một card mạng ảo (Network Interface, thường gọi **NIC**) của máy ảo được kết nối với một subnet. NIC có cấu hình IP để nhận địa chỉ riêng từ dải của subnet đó. Một số dịch vụ được quản lý có cách tích hợp VNet hoặc dùng subnet riêng theo yêu cầu của dịch vụ.

**Subnet không phải một cơ chế tường lửa tự động.** Trong cùng VNet, Azure có định tuyến hệ thống giúp các subnet có thể kết nối tới nhau. Muốn cho phép hoặc chặn từng luồng, cần thiết kế quy tắc mạng như Network Security Group (NSG), Azure Firewall, route table hoặc các tính năng bảo vệ tương ứng.

## 2. Địa chỉ IP và ký hiệu CIDR

Địa chỉ IPv4 có 32 bit, thường được viết dưới dạng bốn số thập phân cách nhau bằng dấu chấm, chẳng hạn **10.42.2.10**. Ký hiệu **CIDR** viết thêm dấu gạch chéo và độ dài tiền tố mạng:

~~~text
10.42.2.0/24
         ^^
       24 bit mạng; còn 8 bit cho địa chỉ trong dải
~~~

Với một dải IPv4 có tiền tố **/p**, tổng số địa chỉ là **2^(32 − p)**. Khi thiết kế subnet trên Azure, cần tính cả những địa chỉ bị nền tảng giữ lại.

| Dải CIDR | Tổng địa chỉ IPv4 | Azure giữ lại | Địa chỉ có thể cấp cho tài nguyên |
|---|---:|---:|---:|
| /24 | 256 | 5 | 251 |
| /26 | 64 | 5 | 59 |
| /27 | 32 | 5 | 27 |
| /28 | 16 | 5 | 11 |
| /29 | 8 | 5 | 3 |

**Azure dành riêng năm địa chỉ IPv4 trong mỗi subnet:** bốn địa chỉ đầu tiên và địa chỉ cuối cùng. Với subnet **10.42.2.0/24**, các địa chỉ dành riêng là **10.42.2.0** đến **10.42.2.3** và **10.42.2.255**; ví dụ **10.42.2.10** nằm trong phần có thể cấp phát.

Lưu ý: một số dịch vụ yêu cầu kích thước subnet tối thiểu lớn hơn hoặc subnet chuyên dụng. Không nên tạo subnet /29 chỉ vì số lượng tài nguyên hiện tại rất ít; còn phải tính nhu cầu mở rộng, địa chỉ dự phòng, tài nguyên sẽ được thêm vào và yêu cầu của dịch vụ.

### Lập kế hoạch dải địa chỉ

Không gian địa chỉ IPv4 riêng thường sử dụng các dải RFC 1918:

- **10.0.0.0/8**
- **172.16.0.0/12**
- **192.168.0.0/16**

Mỗi subnet phải nằm trong một address space của VNet và không được chồng lấn với subnet khác trong cùng VNet. Khi dự định kết nối VNet khác qua peering, mạng tại chỗ qua VPN hoặc ExpressRoute, cần lên kế hoạch để những mạng cần định tuyến tới nhau cũng không có dải địa chỉ chồng lấn. Nếu dải mạng bị trùng, việc thiết lập kết nối và định tuyến có thể không thực hiện được như mong muốn.

Ví dụ, tránh sử dụng đồng thời **10.42.1.0/24** cho mạng Azure và mạng văn phòng nếu hai bên sẽ kết nối qua VPN. Có thể chọn một dải khác cho subnet Azure hoặc lập kế hoạch chuyển đổi địa chỉ phù hợp trước khi kết nối.

## 3. IP riêng (private IP) trong Azure

**Private IP** là địa chỉ được dùng cho giao tiếp trong VNet và các mạng được kết nối hợp lệ với VNet. Trong thiết kế thông dụng, IP riêng nằm trong những dải RFC 1918. Địa chỉ riêng không được định tuyến trực tiếp trên Internet công cộng.

Ví dụ, một VM chạy API nhận IP **10.42.2.10** trong subnet **snet-app**. VM khác trong VNet, hoặc thiết bị ở mạng tại chỗ đã có kết nối và định tuyến phù hợp, có thể truy cập IP này nếu các quy tắc bảo mật cho phép.

IP riêng được dùng cho nhiều thành phần, tùy dịch vụ:

- NIC của Azure Virtual Machine.
- IP frontend nội bộ của Azure Load Balancer hoặc Application Gateway.
- Private Endpoint kết nối riêng tới dịch vụ được hỗ trợ như Storage hoặc Azure SQL.
- Một số dịch vụ sử dụng VNet injection, subnet delegation hoặc tích hợp mạng riêng theo cơ chế riêng.

### Cấp phát IP riêng động và tĩnh

Với NIC của Azure VM, Azure quản lý cấu hình cấp phát IP riêng:

| Chế độ | Cách hoạt động | Khi nên dùng |
|---|---|---|
| **Dynamic** | Azure chọn một địa chỉ khả dụng trong subnet cho cấu hình IP của NIC | Máy ảo hoặc tài nguyên không cần tự chọn trước một địa chỉ cụ thể |
| **Static** | Bạn chỉ định một địa chỉ IPv4 còn khả dụng và hợp lệ trong subnet | Tài nguyên cần địa chỉ nội bộ dự đoán được, theo yêu cầu kiến trúc |

**Static private IP không có nghĩa là tự cấu hình địa chỉ tùy ý bên trong hệ điều hành.** Với Azure VM, hãy cấu hình phân bổ tại IP configuration của NIC trong Azure, rồi bảo đảm cấu hình hệ điều hành tương thích với cơ chế mạng Azure. Không gán một địa chỉ ngoài subnet, nằm trong nhóm Azure dành riêng hoặc đang được tài nguyên khác sử dụng.

Ngay cả khi địa chỉ động thường ổn định trong vòng đời của một NIC, ứng dụng vẫn nên dùng DNS hoặc cấu hình service discovery thay vì cố định địa chỉ IP vào mã nguồn.

### IP riêng có giao tiếp qua các subnet được không?

Có. Các subnet trong cùng một VNet thường có thể định tuyến với nhau thông qua route hệ thống mặc định. Việc một kết nối có thành công hay không còn phụ thuộc:

- NSG ở subnet và/hoặc NIC, gồm hướng vào và hướng ra.
- Route table và thiết bị trung gian như Azure Firewall nếu đã cấu hình.
- Tường lửa hệ điều hành, cổng dịch vụ và tiến trình đang lắng nghe.
- Phân giải DNS và quyền xác thực ở lớp ứng dụng.

Ví dụ, VM tại **10.42.1.10** trong **snet-web** có thể truy cập API **10.42.2.10:443** trong **snet-app** khi định tuyến và chính sách cho phép. Tách hai máy vào hai subnet giúp áp chính sách theo lớp, nhưng tự việc tách subnet không chặn lưu lượng.

## 4. IP công cộng (public IP) trong Azure

**Public IP** là địa chỉ có thể được định tuyến trên Internet và được dùng khi một tài nguyên hoặc frontend cần giao tiếp qua mạng công cộng. Azure cung cấp **Public IP Address** như một tài nguyên riêng để gắn với thành phần hỗ trợ, ví dụ:

- IP configuration của NIC máy ảo.
- Frontend của public Azure Load Balancer.
- Application Gateway dùng frontend công cộng.
- Azure NAT Gateway hoặc các dịch vụ mạng được hỗ trợ khác.

Với tài nguyên **Public IP Standard**, địa chỉ được cấp phát theo chế độ **static**. Khi tạo tài nguyên, có thể chọn phiên bản IP, region và những tùy chọn khả dụng phù hợp với dịch vụ và kiến trúc. Các tùy chọn về zone và phạm vi triển khai phụ thuộc loại Public IP và vùng hỗ trợ.

**Có Public IP không đồng nghĩa một máy chủ đã mở toàn bộ cổng ra Internet.** Lưu lượng thực tế còn chịu tác động của NSG, tường lửa hệ điều hành, cấu hình dịch vụ, định tuyến và các lớp bảo vệ khác. Tuy nhiên, việc gắn Public IP tạo thêm điểm truy cập mạng cần được kiểm soát. Không nên cấp Public IP cho từng VM chỉ để quản trị thuận tiện.

### Public IP được gắn ở đâu?

Đối với VM, địa chỉ riêng thuộc IP configuration trên NIC; Public IP, nếu được dùng trực tiếp, được liên kết tới cấu hình IP của NIC đó. Public IP **không thuộc dải địa chỉ riêng của subnet**. Một subnet có thể chứa nhiều NIC dùng private IP nhưng không có bất kỳ Public IP nào.

Ví dụ:

~~~text
Internet
   |
Public IP (ví dụ: địa chỉ do Azure cấp)
   |
Frontend Application Gateway hoặc Load Balancer
   |
VNet: 10.42.0.0/16
   |
VM ứng dụng: 10.42.2.10 (private IP)
~~~

Ở đây, người dùng kết nối tới frontend công cộng. VM ứng dụng phía sau vẫn chỉ cần IP riêng. Frontend tiếp nhận và chuyển tiếp lưu lượng theo cấu hình, trong khi NSG và các lớp bảo vệ khác giới hạn đường truy cập được phép.

## 5. So sánh IP riêng và IP công cộng

| Tiêu chí | IP riêng | IP công cộng |
|---|---|---|
| Phạm vi sử dụng | Trong VNet và các mạng được kết nối/định tuyến phù hợp | Có thể được định tuyến trên Internet |
| Nguồn địa chỉ | Một dải địa chỉ thuộc subnet, với tài nguyên dùng subnet | Được Azure cấp dưới dạng Public IP resource hoặc bởi dịch vụ |
| Có thể trùng giữa các tổ chức? | Có, ở các mạng độc lập không kết nối | Địa chỉ đang sử dụng cần duy nhất trên Internet công cộng |
| Cấu hình trên VM | IP configuration của NIC | Public IP liên kết với cấu hình NIC nếu VM cần Public IP trực tiếp |
| Ứng dụng phổ biến | API nội bộ, cơ sở dữ liệu, backend | Điểm vào web, load balancer công cộng, địa chỉ NAT đầu ra |
| Yêu cầu kiểm soát | NSG, route, firewall, quyền ứng dụng | Thêm kiểm soát truy cập Internet, firewall, TLS và theo dõi tấn công |
| Chi phí | Thường là phần của cấu hình mạng/tài nguyên liên quan; các dịch vụ mạng đi kèm có thể tính phí | Public IP và dịch vụ liên quan có thể phát sinh phí theo cấu hình và thời gian sử dụng |

Một IP riêng không tự bảo đảm tài nguyên được bảo vệ: lỗi phân quyền hoặc quy tắc mạng quá rộng vẫn có thể gây rủi ro. Một IP công cộng cũng không đồng nghĩa có lỗ hổng bảo mật, nhưng cần có lý do nghiệp vụ và kiểm soát bảo vệ tương ứng.

## 6. Đường đi của lưu lượng vào và ra Internet

Nên phân biệt **inbound** (Internet đi vào workload) với **outbound** (workload truy cập ra Internet).

### Lưu lượng vào (inbound)

Một ứng dụng web có thể cần tiếp nhận HTTPS từ khách hàng trên Internet. Thay vì cấp Public IP cho từng máy chủ ứng dụng, mô hình phổ biến là đặt một điểm vào công cộng được kiểm soát, chẳng hạn Application Gateway hoặc Azure Load Balancer có cấu hình frontend và listener phù hợp.

Luồng minh họa:

~~~text
Người dùng trên Internet
        |
        v
Public IP / frontend HTTPS
        |
        v
Application Gateway (subnet dành riêng theo yêu cầu)
        |
        v
Máy chủ hoặc dịch vụ backend dùng private IP
        |
        v
Cơ sở dữ liệu chỉ có đường truy cập riêng
~~~

Nếu VM cần cổng quản trị, hãy cân nhắc Azure Bastion, VPN hoặc kết nối quản trị riêng thay cho việc mở trực tiếp RDP/SSH ra Internet. Với dịch vụ PaaS, điểm vào công cộng có thể được dịch vụ quản lý riêng mà không cần tạo một Public IP nằm trong resource group của bạn.

### Lưu lượng ra (outbound)

VM chỉ có IP riêng vẫn có thể cần truy cập repository để cập nhật phần mềm, gọi API của đối tác hoặc gửi dữ liệu tới endpoint công cộng. Tùy thiết kế mạng, kết nối outbound có thể dùng:

- **Azure NAT Gateway:** cung cấp đường đi outbound được quản lý cho subnet, sử dụng Public IP hoặc Public IP Prefix gắn với NAT Gateway; không tạo một đường inbound tự phát tới VM.
- **Azure Firewall:** kiểm soát và ghi log lưu lượng theo chính sách, khi định tuyến được thiết kế qua firewall.
- **Load Balancer outbound rules** hoặc cơ chế outbound được dịch vụ hỗ trợ.

Không nên dựa vào khả năng outbound mặc định không được khai báo rõ, vì hành vi phụ thuộc cấu hình và các thay đổi của nền tảng. Với production, nên xác định rõ egress IP, nhu cầu allowlist, lưu lượng được phép và chi phí dữ liệu đầu ra.

**NAT Gateway giúp nhiều private VM dùng một hoặc một nhóm Public IP cho outbound.** Các máy vẫn giữ private IP riêng, trong khi dịch vụ Internet phía ngoài thấy địa chỉ công cộng phía NAT. Điều này không có nghĩa VM sẽ tự động chấp nhận kết nối từ Internet đi vào.

## 7. Subnet, NSG, route table và DNS

Subnet là đơn vị tổ chức địa chỉ IP, nhưng kiến trúc mạng an toàn phải phối hợp thêm các thành phần khác.

### Network Security Group (NSG)

NSG chứa các quy tắc cho phép hoặc từ chối lưu lượng dựa trên nguồn, đích, cổng, giao thức và hướng truyền. NSG có thể liên kết với subnet và/hoặc NIC. Ví dụ:

- Chỉ cho phép HTTPS từ frontend tới backend ở cổng cần thiết.
- Không cho phép Internet truy cập trực tiếp tới subnet ứng dụng.
- Giới hạn giao thức quản trị tới địa chỉ hoặc mạng đáng tin cậy.

NSG là bộ lọc lưu lượng mạng, không thay thế xác thực người dùng, phân quyền ứng dụng, WAF hoặc cơ chế bảo vệ dữ liệu.

### Route table và peering

Azure tạo những tuyến hệ thống mặc định để giao tiếp trong VNet. Có thể dùng **User Defined Route (UDR)** để điều hướng lưu lượng qua firewall hoặc appliance. Khi hai VNet cần giao tiếp, **VNet peering** có thể cung cấp kết nối giữa chúng nếu thỏa điều kiện và cấu hình tương ứng.

Việc có tuyến mạng không bảo đảm có quyền truy cập. Quy tắc NSG, firewall, cấu hình endpoint và quyền ứng dụng vẫn quyết định lưu lượng có được chấp nhận hay không.

### DNS không đồng nghĩa với IP

**DNS** chuyển tên thành thông tin địa chỉ theo bản ghi phù hợp. Trong mạng Azure:

- Bản ghi DNS công cộng có thể đưa người dùng tới frontend dùng Public IP.
- Tên nội bộ có thể phân giải về private IP qua dịch vụ DNS phù hợp.
- **Azure Private DNS Zone** thường được kết hợp với Private Endpoint để phân giải tên dịch vụ PaaS về địa chỉ riêng.

Ví dụ, người dùng truy cập **shop.example.com** và nhận địa chỉ công cộng của frontend. Ứng dụng phía trong truy cập cơ sở dữ liệu qua tên DNS được cấu hình để phân giải về IP của Private Endpoint. Việc thay đổi IP có thể đòi hỏi cập nhật bản ghi DNS hoặc cấu hình DNS tích hợp; vì vậy nên thiết kế theo tên dịch vụ khi có thể.

## 8. Thiết kế subnet cho ứng dụng ba lớp

Giả sử một hệ thống bán hàng có tầng tiếp nhận HTTPS, tầng xử lý API và kết nối riêng tới Azure SQL Database. Một kế hoạch địa chỉ có thể như sau:

| Thành phần | Subnet | CIDR | Mục đích |
|---|---|---|---|
| Frontend Application Gateway | snet-ingress | 10.42.0.0/24 | Dành riêng cho gateway theo yêu cầu triển khai |
| Web hoặc máy chủ giao diện | snet-web | 10.42.1.0/24 | Chạy các thành phần phục vụ web bằng private IP |
| API nội bộ | snet-app | 10.42.2.0/24 | Chạy backend và chỉ mở cổng cần thiết |
| Private Endpoint | snet-private-endpoints | 10.42.3.0/27 | Chứa IP riêng để truy cập dịch vụ PaaS hỗ trợ Private Link |

Các subnet cùng nằm trong **10.42.0.0/16**, mỗi subnet có một CIDR riêng. Có thể sử dụng sơ đồ logic sau:

~~~text
                    INTERNET
                       |
                  Public IP
                       |
          Application Gateway / HTTPS
            snet-ingress (10.42.0/24)
                       |
                    Private IP
                       |
             Web (10.42.1.0/24)
                       |
               HTTPS nội bộ
                       |
             API (10.42.2.0/24)
                       |
                 Private DNS
                       |
            Private Endpoint (IP riêng)
            snet-private-endpoints
                       |
                Azure SQL Database
~~~

Đối với phần dịch vụ PaaS, subnet và cơ chế kết nối có thể khác tùy loại tài nguyên. Ví dụ, Azure App Service có cơ chế VNet Integration cho outbound và Private Endpoint cho inbound riêng; không nên coi App Service như một VM tự có NIC trong bất kỳ subnet nào. Khi triển khai thực tế, xem yêu cầu về subnet delegation, kích thước subnet, Private Endpoint và quyền truy cập của từng dịch vụ.

Các quyết định bảo mật cần ghi nhận:

1. Tầng nào cần địa chỉ công cộng, tầng nào chỉ cần IP riêng?
2. Những subnet nào cần trao đổi dữ liệu và trên cổng nào?
3. Luồng outbound nào cần NAT Gateway hoặc firewall?
4. Nên phân giải DNS cho frontend và dịch vụ PaaS ra sao?
5. Nên dự phòng bao nhiêu địa chỉ cho tăng trưởng và dịch vụ bổ sung?
6. Các dải CIDR có xung đột với VNet khác hoặc mạng văn phòng không?

## 9. Thực hành tạo VNet và subnet bằng Azure CLI

Ví dụ dưới đây tạo một môi trường mạng đơn giản trong **region Southeast Asia**. Các lệnh mang tính minh họa và chỉ nên chạy trong subscription được phép sử dụng. Xác nhận chi phí và quota trước khi tạo tài nguyên, đặc biệt nếu thêm Public IP hoặc dịch vụ mạng trả phí.

### Bước 1: chọn subscription và tạo resource group thử nghiệm

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az group create \
  --name rg-network-lab \
  --location southeastasia
~~~

Nên sử dụng resource group dành riêng cho bài thực hành. Subscription ID trong ví dụ là placeholder và phải thay bằng subscription được cấp quyền.

### Bước 2: tạo VNet và subnet đầu tiên

~~~bash
az network vnet create \
  --resource-group rg-network-lab \
  --name vnet-sales \
  --location southeastasia \
  --address-prefixes 10.42.0.0/16 \
  --subnet-name snet-web \
  --subnet-prefixes 10.42.1.0/24
~~~

Lệnh tạo VNet có address space **10.42.0.0/16** và subnet web **10.42.1.0/24**.

### Bước 3: thêm subnet API và Private Endpoint

~~~bash
az network vnet subnet create \
  --resource-group rg-network-lab \
  --vnet-name vnet-sales \
  --name snet-app \
  --address-prefixes 10.42.2.0/24

az network vnet subnet create \
  --resource-group rg-network-lab \
  --vnet-name vnet-sales \
  --name snet-private-endpoints \
  --address-prefixes 10.42.3.0/27
~~~

Trong thực hành này, các subnet chỉ mới được tạo để minh họa CIDR. Chưa có VM, Private Endpoint, NSG hoặc rule truy cập nào được triển khai; việc đặt tên subnet không tự tạo những dịch vụ đó.

### Bước 4: kiểm tra cấu hình mạng

~~~bash
az network vnet show \
  --resource-group rg-network-lab \
  --name vnet-sales \
  --query "{name:name,addressSpace:addressSpace.addressPrefixes,location:location}" \
  --output json

az network vnet subnet list \
  --resource-group rg-network-lab \
  --vnet-name vnet-sales \
  --output table
~~~

Kiểm tra tên subnet, dải CIDR và tính không chồng lấn. Nếu một subnet bị tạo sai dải, cần xem trạng thái sử dụng IP và ràng buộc của những tài nguyên đã gắn vào trước khi thay đổi.

### Bước 5: tạo một Public IP minh họa

~~~bash
az network public-ip create \
  --resource-group rg-network-lab \
  --name pip-lab \
  --location southeastasia \
  --sku Standard \
  --allocation-method Static

az network public-ip show \
  --resource-group rg-network-lab \
  --name pip-lab \
  --query "{name:name,ip:ipAddress,sku:sku.name}" \
  --output table
~~~

Public IP vừa tạo là một **tài nguyên độc lập**. Nó chưa được gắn vào NIC, Load Balancer hoặc Application Gateway, và chưa tự tạo điểm truy cập ứng dụng. Public IP có thể phát sinh chi phí kể cả khi chưa phục vụ lưu lượng; hãy xóa sau khi kiểm tra nếu không còn sử dụng.

### Bước 6: dọn dẹp sau thực hành

~~~bash
az network public-ip delete \
  --resource-group rg-network-lab \
  --name pip-lab
~~~

Chỉ khi **rg-network-lab** là resource group dành riêng cho bài thực hành và đã xác nhận không còn tài nguyên cần giữ, mới xóa cả group cùng các subnet/VNet bên trong:

~~~bash
az group delete \
  --name rg-network-lab \
  --yes
~~~

Xóa resource group cũng xóa các tài nguyên thuộc group đó và có thể không phục hồi được. Sau khi dọn dẹp, hãy kiểm tra Azure Cost Management nếu cần theo dõi các khoản chi phí đã phát sinh.

## 10. Thao tác tương đương trong Azure portal

Nếu sử dụng giao diện web:

1. Đăng nhập **Azure portal**, kiểm tra đúng tenant và subscription.
2. Mở **Virtual networks**, chọn **Create** và điền resource group, tên VNet, region.
3. Khai báo address space, chẳng hạn **10.42.0.0/16**, rồi tạo các subnet không chồng lấn.
4. Xem lại cấu hình trước khi tạo. Khi VNet đã tồn tại, có thể mở mục **Subnets** để thêm hoặc chỉnh subnet tùy trạng thái tài nguyên.
5. Mở **Public IP addresses** để xem hoặc tạo Public IP resource theo SKU, region và tùy chọn hỗ trợ.
6. Chỉ liên kết Public IP tới NIC hoặc frontend của dịch vụ nếu có nhu cầu ingress/egress đã được thiết kế và đã áp dụng bảo mật phù hợp.

Tên tab và biểu mẫu trên portal có thể thay đổi theo phiên bản giao diện. Các nguyên tắc cần giữ nguyên là: CIDR hợp lệ, phạm vi subscription chính xác, IP public gắn đúng mục đích và chính sách lưu lượng rõ ràng.

## 11. Chẩn đoán lỗi mạng thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tạo được subnet | CIDR nằm ngoài VNet, chồng lấn hoặc không đáp ứng yêu cầu dịch vụ | Kiểm tra address space và các prefix đang dùng |
| Không gán được private IP tĩnh | Địa chỉ bị Azure giữ lại, đã dùng hoặc không thuộc subnet | Kiểm tra IP configuration của NIC và danh sách IP trong subnet |
| VM ở hai subnet không kết nối được | NSG, UDR, tường lửa hệ điều hành hoặc service không lắng nghe | Kiểm tra effective security rules, route và cổng dịch vụ |
| Có Public IP nhưng không truy cập được VM | Thiếu quy tắc inbound, firewall chặn, dịch vụ chưa chạy hoặc frontend chưa liên kết đúng | Kiểm tra NSG, NIC/frontend, IP và cổng ứng dụng |
| VM chỉ có private IP không truy cập Internet | Chưa có phương án outbound phù hợp hoặc egress bị chặn | Kiểm tra NAT Gateway, firewall, route, DNS và rule outbound |
| Truy cập PaaS vẫn qua địa chỉ công cộng | DNS hoặc Private Endpoint chưa được thiết lập đúng | Kiểm tra kết quả phân giải tên, Private DNS Zone và đường mạng |
| Peering/VPN không định tuyến như dự kiến | CIDR chồng lấn, route sai hoặc cấu hình gateway/peering chưa đủ | Đối chiếu address space, effective routes và cấu hình kết nối |

Các công cụ và màn hình hữu ích gồm **Network Watcher**, **effective routes**, **effective security rules**, kiểm tra kết nối, log NSG hoặc firewall khi được bật và các công cụ DNS như **nslookup** hoặc **dig**. Khi chẩn đoán, cần kiểm tra cả hai chiều của lưu lượng, không chỉ kiểm tra máy nguồn.

Ví dụ: VM web không gọi được API qua **10.42.2.10:443**. Trình tự hợp lý là xác nhận DNS hoặc IP đích, kiểm tra API đang lắng nghe cổng 443, xem NSG tại NIC/subnet, xem route và firewall hệ điều hành, sau đó kiểm tra kết quả kết nối. Không nên mở mọi cổng hoặc tắt NSG chỉ để làm cho bài kiểm thử tạm thời thành công.

## 12. Những hiểu lầm cần tránh

**“Tạo hai subnet là đã cách ly hoàn toàn hai ứng dụng.”** Subnet giúp phân chia địa chỉ và áp chính sách; luồng mạng giữa chúng vẫn có thể được định tuyến nếu không có quy tắc ngăn chặn.

**“IP riêng có thể truy cập trực tiếp từ bất cứ đâu trên Internet.”** Private IP không được định tuyến trực tiếp trên Internet công cộng; cần một đường kết nối phù hợp như VPN, peering hoặc endpoint/frontend trung gian và các quyền tương ứng.

**“VM cần Public IP thì mới tải bản cập nhật được.”** VM có private IP có thể dùng NAT Gateway, firewall hoặc giải pháp outbound được hỗ trợ, nên không cần Public IP riêng chỉ để truy cập ra ngoài.

**“Public IP đã được tạo thì web server tự động hoạt động.”** Public IP là tài nguyên địa chỉ. Còn phải liên kết với frontend hoặc NIC, cấu hình listener, đường mạng và các quy tắc bảo mật.

**“Có thể chọn bất kỳ IP tĩnh nào trong subnet.”** Phải chọn địa chỉ hợp lệ, chưa được dùng và không nằm trong năm IPv4 Azure dành riêng.

**“DNS và IP là cùng một thứ.”** DNS là cơ chế phân giải tên; địa chỉ IP là thông tin dùng để định tuyến và giao tiếp. Một tên DNS có thể ánh xạ sang những địa chỉ khác nhau theo thiết kế.

**“Địa chỉ riêng không bao giờ gây xung đột.”** Các VNet độc lập có thể dùng dải trùng nhau, nhưng khi cần kết nối trực tiếp giữa chúng hoặc với mạng tại chỗ, dải CIDR chồng lấn có thể gây trở ngại định tuyến.

## 13. Bài tập thực hành và tự kiểm tra

### Tình huống

Bạn được giao thiết kế mạng Azure cho ứng dụng quản lý kho gồm frontend HTTPS, backend API, một VM xử lý tác vụ nội bộ và Azure Storage dùng qua Private Endpoint. Tổ chức có sẵn VNet **10.60.0.0/16** và có kế hoạch kết nối mạng văn phòng **192.168.100.0/24** qua VPN.

Hãy:

1. Đề xuất ít nhất ba subnet không chồng lấn cho những nhóm tài nguyên cần sử dụng VNet.
2. Tính số địa chỉ có thể cấp cho subnet **10.60.10.0/27** trên Azure.
3. Xác định thành phần nào cần điểm vào công cộng và thành phần nào chỉ nên có private IP.
4. Đề xuất phương án cho VM nội bộ truy cập Internet để cập nhật phần mềm mà không cấp Public IP trực tiếp.
5. Nêu các luồng mạng cần cho phép bằng NSG và các luồng nên từ chối.
6. Giải thích vì sao cần cấu hình DNS riêng cho Storage Private Endpoint.

Một phương án hợp lý có thể dùng subnet riêng cho frontend gateway, subnet backend và subnet Private Endpoint; VM tác vụ nội bộ chỉ dùng IP riêng; egress qua NAT Gateway hoặc firewall; frontend HTTPS là điểm tiếp nhận công cộng được kiểm soát. Với **10.60.10.0/27**, có **32** địa chỉ IPv4, Azure giữ lại **5**, còn **27** địa chỉ có thể cấp cho tài nguyên. Cần điều chỉnh kích thước subnet nếu dịch vụ dự kiến sử dụng có yêu cầu riêng.

### Câu hỏi tự kiểm tra

1. VNet, subnet và IP riêng khác nhau ở điểm nào?
2. Vì sao **10.42.1.0/24** và **10.42.1.128/25** không thể dùng làm hai subnet độc lập trong cùng VNet?
3. Một subnet /26 có bao nhiêu địa chỉ IPv4 có thể cấp cho tài nguyên trên Azure?
4. Với NIC của VM, khác biệt giữa private IP động và tĩnh là gì?
5. Public IP Standard được dùng ở những loại frontend nào? Việc tạo Public IP có tự mở cổng vào VM không?
6. Khi VM không có Public IP, có những cách nào để thiết kế lưu lượng outbound?
7. Vì sao cần NSG dù đã tách web và API thành hai subnet?
8. DNS cho Private Endpoint có vai trò gì đối với ứng dụng truy cập dịch vụ PaaS?
9. Vì sao nên tránh CIDR chồng lấn giữa VNet Azure và mạng tại chỗ sắp kết nối?

## Tài liệu tham khảo

- Microsoft Learn — *What is Azure Virtual Network?*: https://learn.microsoft.com/azure/virtual-network/virtual-networks-overview
- Microsoft Learn — *Add, change, or delete a virtual network subnet*: https://learn.microsoft.com/azure/virtual-network/virtual-network-manage-subnet
- Microsoft Learn — *IP address types and allocation methods in Azure*: https://learn.microsoft.com/azure/virtual-network/ip-services/public-ip-addresses
- Microsoft Learn — *Private IP addresses for Azure*: https://learn.microsoft.com/azure/virtual-network/ip-services/private-ip-addresses
- Microsoft Learn — *Azure NAT Gateway*: https://learn.microsoft.com/azure/nat-gateway/nat-overview
- Microsoft Learn — *Network Security Groups*: https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview
- Microsoft Learn — *Azure Private Endpoint*: https://learn.microsoft.com/azure/private-link/private-endpoint-overview
