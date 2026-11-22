# Kết nối mạng bằng VNet peering

Trong Microsoft Azure, một ứng dụng thường không đặt tất cả máy ảo, dịch vụ và dữ liệu vào cùng một Virtual Network (VNet). Nhóm nền tảng có thể vận hành một **hub VNet** chứa dịch vụ dùng chung, trong khi từng ứng dụng hoặc môi trường có **spoke VNet** riêng. Các tài nguyên ở những VNet khác nhau cần trao đổi với nhau bằng địa chỉ IP riêng nhưng vẫn phải tôn trọng phân đoạn mạng và quyền truy cập.

**VNet peering** là cơ chế kết nối trực tiếp hai Azure Virtual Network, cho phép tài nguyên trong các mạng giao tiếp qua hạ tầng mạng Microsoft bằng địa chỉ IP riêng, không phải định tuyến qua Internet công cộng chỉ để đi giữa hai VNet. Bài học này thuộc chương **Mạng ảo và phân giải tên** của module **CLOUD_PROVIDERS_AZURE**, nơi người học xây dựng kiến trúc ứng dụng trên Azure từ subscription và resource group đến mạng, compute, dữ liệu, giám sát, bảo mật và chi phí.

Mục tiêu không chỉ là tạo một liên kết peering có trạng thái Connected, mà còn là thiết kế địa chỉ không chồng lấn, định tuyến hai chiều, phân giải tên và chính sách bảo mật phù hợp, sau đó kiểm thử kết nối và tính toán chi phí vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích VNet peering, local VNet peering và global VNet peering.
- Phân biệt peering với VPN Gateway, ExpressRoute, Private Endpoint và một mạng phẳng duy nhất.
- Thiết kế địa chỉ IP không chồng lấn, nhận biết peering **không có tính bắc cầu (non-transitive)**.
- Hiểu peering hai chiều, các thiết lập **Allow virtual network access**, **Allow forwarded traffic**, **Allow gateway transit** và **Use remote gateways**.
- Tạo peering bằng Azure Portal và Azure CLI; xác minh trạng thái và thử kết nối IP riêng.
- Kiểm tra tác động của Network Security Group (NSG), User Defined Routes (UDR), Network Virtual Appliance (NVA) và DNS.
- Chẩn đoán lỗi kết nối, sửa đổi address space, gỡ peering và cân nhắc chi phí/giới hạn.

## 2. VNet peering là gì?

VNet là ranh giới mạng logic trong Azure, có address space và các subnet chứa network interface của VM hoặc các tài nguyên được tích hợp vào VNet. Mỗi VNet có thể được quản lý độc lập theo subscription, resource group, vùng triển khai và chính sách của tổ chức.

**VNet peering** thiết lập quan hệ kết nối giữa **hai VNet**. Khi được cấu hình phù hợp và không bị chặn bởi chính sách mạng, gói tin có thể đi giữa các tài nguyên bằng địa chỉ IP riêng thông qua mạng backbone của Microsoft.

Peering không tạo ra một VNet hợp nhất: hai mạng vẫn giữ nguyên address space, subnet, NSG, route table, ranh giới quản trị và vòng đời riêng. Peering cũng không phải VPN tunnel được cấu hình bằng thiết bị của khách hàng.

### 2.1. Hai loại peering

| Hình thức | Vị trí hai VNet | Ứng dụng điển hình |
|---|---|---|
| **Virtual network peering** (regional/local) | Hai VNet trong cùng Azure region | Kết nối VNet ứng dụng với VNet dịch vụ chung trong cùng khu vực |
| **Global virtual network peering** | Hai VNet ở các Azure region khác nhau được hỗ trợ | Liên lạc nội bộ giữa ứng dụng triển khai ở các khu vực khác nhau |

Ví dụ:

- **Regional**: hub và spoke cùng ở Southeast Asia.
- **Global**: VNet của ứng dụng ở Southeast Asia cần truy cập dịch vụ riêng ở East Asia.

Hai kiểu này dùng nguyên tắc chung về address space và peering hai chiều. Khả năng hỗ trợ từng khu vực, SKU dịch vụ, đường đi và giá dữ liệu cần được kiểm tra theo tài liệu và bảng giá Azure hiện hành trước khi triển khai production.

### 2.2. Khi nào nên dùng?

VNet peering hữu ích khi:

1. **Tách ứng dụng và môi trường:** VNet cho production, testing hoặc các nhóm nghiệp vụ khác nhau nhưng vẫn cần một số luồng mạng.
2. **Hub–spoke:** các spoke dùng chung DNS resolver, firewall, Bastion hoặc một số dịch vụ nền tảng đặt ở hub.
3. **Tách quyền quản trị:** mỗi nhóm quản lý VNet hoặc resource group của mình, trong khi có kết nối nội bộ đã thỏa thuận.
4. **Kết nối đa khu vực:** các workload phân tán cần trao đổi qua mạng riêng Azure.
5. **Di chuyển/hiện đại hóa ứng dụng:** hệ thống cũ và hệ thống mới đặt trong các VNet khác nhau nhưng có nhu cầu giao tiếp trong một giai đoạn chuyển đổi.

Không nhất thiết dùng peering khi các thành phần đã nằm cùng VNet và có thể giao tiếp bằng subnet, NSG và routing phù hợp. Cũng không nên tạo peering đại trà nếu thực tế chỉ cần truy cập một dịch vụ cụ thể: có thể xem xét Private Endpoint hoặc kiến trúc truy cập dịch vụ phù hợp hơn.

## 3. Điều kiện tiên quyết và giới hạn quan trọng

### 3.1. Address space không được chồng lấn

Đây là điều kiện quan trọng nhất. Hai VNet định peering phải có **dải địa chỉ IP không chồng lấn**, kể cả các địa chỉ chưa cấp cho subnet.

Ví dụ hợp lệ:

| Mạng | Address space | Subnet minh họa |
|---|---|---|
| Hub VNet | 10.10.0.0/16 | snet-shared: 10.10.1.0/24 |
| Spoke ứng dụng Orders | 10.20.0.0/16 | snet-app: 10.20.1.0/24 |
| Spoke dữ liệu | 10.30.0.0/16 | snet-data: 10.30.1.0/24 |

Ví dụ không hợp lệ:

- VNet A: **10.10.0.0/16**.
- VNet B: **10.10.50.0/24**.

Hai mạng chồng lấn vì 10.10.50.0/24 nằm trong 10.10.0.0/16. Đừng chỉ kiểm tra các subnet đang dùng; hãy so sánh toàn bộ address spaces của VNet và dải có thể bổ sung trong tương lai.

Nếu có chồng lấn, cần lập kế hoạch đổi địa chỉ hoặc dùng kiến trúc trung gian thích hợp. VNet peering không tự thực hiện NAT để giải quyết dải địa chỉ trùng nhau.

### 3.2. Peering được tạo cho cả hai hướng

Với hai VNet **A** và **B**, thường cần hai peering resource:

- Peering **A → B** được tạo trên VNet A.
- Peering **B → A** được tạo trên VNet B.

Cả hai được thiết lập phù hợp thì trạng thái kết nối có thể là **Connected**. Nếu chỉ tạo một phía, có thể thấy trạng thái **Initiated** hoặc chưa hoàn chỉnh; không nên xem đó là một kết nối hai chiều sẵn sàng sử dụng. Azure Portal có thể giúp tạo đồng thời cả hai phía khi tài khoản đủ quyền, còn lệnh CLI bên dưới tạo riêng từng hướng.

Peering là quan hệ giữa hai VNet, **không** cần tạo từng liên kết cho từng subnet.

### 3.3. Peering không có tính bắc cầu

Đây là điểm thường gây nhầm lẫn trong kiến trúc hub–spoke.

~~~mermaid
flowchart LR
    A["Spoke A<br/>10.20.0.0/16"] <-->|Peering| H["Hub<br/>10.10.0.0/16"]
    H <-->|Peering| B["Spoke B<br/>10.30.0.0/16"]
    A -. "Không tự động có route trực tiếp" .- B
~~~

Nếu A peering với Hub và B cũng peering với Hub, **A không tự động kết nối tới B**. Muốn A giao tiếp với B, có thể:

- Tạo thêm **peering trực tiếp A ↔ B** nếu phù hợp với mô hình quản trị.
- Thiết kế **NVA hoặc Azure Firewall ở hub** và các UDR/thiết lập forwarded traffic phù hợp để định tuyến qua hub.
- Dùng dịch vụ kết nối/chuyển tiếp khác theo nhu cầu, chẳng hạn Azure Virtual WAN.

Không giả định rằng chỉ bật Allow forwarded traffic sẽ tạo đầy đủ routing bắc cầu. Nó cho phép một loại lưu lượng đã được chuyển tiếp qua peering; vẫn phải có các route, thiết bị xử lý và quy tắc bảo mật phù hợp.

### 3.4. Quyền để tạo peering

Người thao tác phải có quyền phù hợp để cấu hình peering ở các VNet liên quan, chẳng hạn vai trò **Network Contributor** tại phạm vi thích hợp hoặc custom role có những operation cần thiết. Nếu các VNet nằm ở subscription khác nhau, quyền cần được cấp tại từng phía tương ứng.

Peering qua subscription và một số trường hợp khác tenant có thể thực hiện khi điều kiện ủy quyền đáp ứng. Không được giả định một tài khoản có Network Contributor ở VNet A sẽ tự có quyền chỉnh sửa VNet B. Cần phối hợp với chủ sở hữu phía kia và cơ chế cấp quyền/cấu hình mà Azure hỗ trợ.

### 3.5. Peering không tự vô hiệu hóa NSG hay firewall

Khi thêm peering:

- NSG trên subnet và NIC vẫn được đánh giá.
- Azure Firewall, NVA, route table và hệ thống kiểm soát mạng vẫn có thể chặn hoặc chuyển hướng gói tin.
- Phần mềm firewall trong hệ điều hành vẫn kiểm soát kết nối đến tiến trình.
- Ứng dụng vẫn phải lắng nghe ở đúng IP/port và cho phép người gọi truy cập.

Đặc biệt, một số rule mặc định của NSG sử dụng service tag **VirtualNetwork**, mà tập địa chỉ hiệu lực có thể bao gồm những VNet được peering. Do vậy, peering có thể mở rộng phạm vi giao tiếp thực tế nếu dựa hoàn toàn vào rule mặc định. Với production, hãy kiểm tra effective security rules và thiết lập allow/deny có chủ đích.

## 4. Mô hình tham chiếu hub–spoke

Giả sử tổ chức triển khai dịch vụ đặt hàng **Orders** trong một Azure subscription. Đội nền tảng dùng hub để vận hành những dịch vụ chung; đội ứng dụng quản lý spoke riêng. Mục tiêu là cho một VM hoặc ứng dụng ở spoke truy cập máy chủ dịch vụ nội bộ trong hub qua địa chỉ IP riêng.

~~~mermaid
flowchart TB
    subgraph Azure["Azure Subscription"]
      subgraph HubRG["rg-network-hub"]
        subgraph HubVnet["vnet-hub — 10.10.0.0/16"]
          HubSubnet["snet-shared — 10.10.1.0/24"]
          Shared["Dịch vụ nội bộ<br/>10.10.1.10:443"]
          HubSubnet --- Shared
        end
      end
      subgraph AppRG["rg-orders-prod"]
        subgraph SpokeVnet["vnet-orders-prod — 10.20.0.0/16"]
          AppSubnet["snet-app — 10.20.1.0/24"]
          App["Workload Orders<br/>10.20.1.10"]
          AppSubnet --- App
        end
      end
      HubVnet <-->|"Hai peering đối xứng"| SpokeVnet
    end
~~~

| Thành phần | Giá trị minh họa | Vai trò |
|---|---|---|
| Subscription | subscription hiện tại | Chứa hai VNet |
| Resource group hub | rg-network-hub | Sở hữu hạ tầng mạng dùng chung |
| Hub VNet | vnet-hub, 10.10.0.0/16 | Cung cấp subnet dịch vụ chung |
| Resource group ứng dụng | rg-orders-prod | Sở hữu tài nguyên ứng dụng |
| Spoke VNet | vnet-orders-prod, 10.20.0.0/16 | Chứa workload Orders |
| Luồng cần kiểm thử | 10.20.1.10 → 10.10.1.10:443 | HTTPS nội bộ từ ứng dụng đến dịch vụ |

Đây là sơ đồ và giá trị minh họa, không phải tài nguyên đã được tạo. Các địa chỉ .10 chỉ hợp lệ nếu chưa cấp cho tài nguyên khác trong subnet, và dịch vụ đích thật sự lắng nghe trên TCP/443.

### 4.1. Cần chuẩn bị gì?

1. Có Azure subscription và quyền tạo/đọc VNet, peering; các quyền cần thiết ở cả hai đầu.
2. Hai VNet đã tạo, address spaces không trùng nhau.
3. Subnet, VM/ứng dụng kiểm thử và dịch vụ đích đã được triển khai nếu muốn thử lưu lượng.
4. Biết resource group, tên VNet và resource ID ở từng phía.
5. NSG, firewall, route table, DNS và quy tắc ứng dụng đã được kiểm tra.
6. Đánh giá chi phí dữ liệu peering và các tài nguyên phát sinh trong lúc thực hành.

Nếu chưa có hai VNet, có thể tạo trong môi trường sandbox được tổ chức phê duyệt. Không thử sửa peering hoặc routing trên production nếu chưa có sơ đồ kết nối, phương án rollback và quy trình thay đổi.

## 5. Thiết lập peering bằng Azure Portal

Các bước sau mô tả luồng thao tác phổ biến; nhãn và vị trí nút có thể thay đổi khi Azure Portal được cập nhật:

1. Mở Azure Portal, tìm **Virtual networks**.
2. Chọn **vnet-hub**.
3. Trong phần cài đặt của VNet, mở mục **Peerings**, sau đó chọn **Add**.
4. Đặt tên peering ở phía hub, ví dụ **hub-to-orders**.
5. Chọn remote virtual network **vnet-orders-prod**. Nếu hai VNet ở subscription khác nhau, chọn đúng subscription/tenant và dùng cơ chế định danh phù hợp.
6. Cấu hình cho phép truy cập mạng ảo theo thiết kế. Trong mô hình trực tiếp cơ bản, cho phép lưu lượng VNet giữa hai mạng.
7. Nếu Portal cung cấp tùy chọn tạo peer ở phía remote, đặt tên **orders-to-hub** và tạo cả hai phía khi đủ quyền.
8. Kiểm tra danh sách peerings ở **cả hai VNet** và trạng thái kết nối.
9. Sau khi trạng thái đạt **Connected**, tiếp tục kiểm tra NSG, route, DNS và khả năng kết nối thực tế.

Không bật **gateway transit** hoặc **forwarded traffic** chỉ vì muốn peering hoạt động. Hai tùy chọn này dành cho những luồng đặc biệt và cần thêm điều kiện như trình bày ở phần sau.

## 6. Tạo và kiểm tra peering bằng Azure CLI

CLI phù hợp với việc lặp lại cấu hình, dùng trong pipeline và lưu các bước thực hành thành tài liệu. Ví dụ dưới đây chạy theo cú pháp **Bash** trong Azure Cloud Shell hoặc máy có Azure CLI.

### 6.1. Xác nhận subscription và lấy resource ID

~~~bash
# Đăng nhập nếu chưa có phiên
az login

# Chọn subscription dành cho bài thực hành
az account set --subscription "<subscription-id>"
az account show --output table

HUB_RG="rg-network-hub"
HUB_VNET="vnet-hub"
APP_RG="rg-orders-prod"
APP_VNET="vnet-orders-prod"

HUB_ID=$(az network vnet show \
  --resource-group "$HUB_RG" \
  --name "$HUB_VNET" \
  --query id --output tsv)

APP_ID=$(az network vnet show \
  --resource-group "$APP_RG" \
  --name "$APP_VNET" \
  --query id --output tsv)

printf "Hub ID: %s\nSpoke ID: %s\n" "$HUB_ID" "$APP_ID"
~~~

Xác nhận các ID không rỗng và đúng đối tượng trước khi tạo. Nếu ở hai subscription, cần lấy từng resource ID trong ngữ cảnh subscription thích hợp, bằng tùy chọn **--subscription** hoặc cấu hình Azure CLI tương ứng, và có quyền ở cả hai phía.

### 6.2. Kiểm tra address spaces

~~~bash
az network vnet show \
  --ids "$HUB_ID" \
  --query "{name:name,location:location,addressSpace:addressSpace.addressPrefixes}" \
  --output json

az network vnet show \
  --ids "$APP_ID" \
  --query "{name:name,location:location,addressSpace:addressSpace.addressPrefixes}" \
  --output json
~~~

Kỳ vọng thấy hai dải **10.10.0.0/16** và **10.20.0.0/16**, hoặc các dải khác đã được phê duyệt và không trùng nhau. Nếu phát hiện trùng địa chỉ, dừng quy trình thiết lập để thiết kế lại.

### 6.3. Tạo peering từ hub đến spoke

~~~bash
az network vnet peering create \
  --resource-group "$HUB_RG" \
  --vnet-name "$HUB_VNET" \
  --name "hub-to-orders" \
  --remote-vnet "$APP_ID" \
  --allow-vnet-access
~~~

Tham số **--remote-vnet** nhận resource ID của VNet phía còn lại. Tùy chọn **--allow-vnet-access** dùng để cho phép truy cập qua VNet peering trong mô hình cơ bản.

### 6.4. Tạo peering ngược từ spoke đến hub

~~~bash
az network vnet peering create \
  --resource-group "$APP_RG" \
  --vnet-name "$APP_VNET" \
  --name "orders-to-hub" \
  --remote-vnet "$HUB_ID" \
  --allow-vnet-access
~~~

Sau khi tạo đủ hai phía, đọc trạng thái:

~~~bash
az network vnet peering list \
  --resource-group "$HUB_RG" \
  --vnet-name "$HUB_VNET" \
  --output table

az network vnet peering list \
  --resource-group "$APP_RG" \
  --vnet-name "$APP_VNET" \
  --output table
~~~

Để xem kỹ một peering:

~~~bash
az network vnet peering show \
  --resource-group "$HUB_RG" \
  --vnet-name "$HUB_VNET" \
  --name "hub-to-orders" \
  --query "{state:peeringState,remote:remoteVirtualNetwork.id,allowVnetAccess:allowVirtualNetworkAccess,allowForwarded:allowForwardedTraffic,gatewayTransit:allowGatewayTransit,useRemoteGateways:useRemoteGateways}" \
  --output json
~~~

Mục tiêu của ví dụ cơ bản là trạng thái **Connected** ở cả hai phía. Nếu chỉ có một peering, thiếu quyền trên một đầu hoặc remote VNet không đúng, hãy khắc phục trước khi kiểm thử truyền dữ liệu.

### 6.5. Có thể tạo VNet trước bằng CLI không?

Trong một lab trống, các lệnh sau minh họa việc tạo VNet, resource group và subnet. Chỉ chạy khi bạn có quyền, đã kiểm tra address space trong tổ chức và chấp nhận các tài nguyên thực hành sẽ được tạo:

~~~bash
# Ví dụ: hai nhóm tài nguyên tại cùng region
az group create --name rg-network-hub --location southeastasia
az group create --name rg-orders-prod --location southeastasia

az network vnet create \
  --resource-group rg-network-hub \
  --name vnet-hub \
  --location southeastasia \
  --address-prefixes 10.10.0.0/16 \
  --subnet-name snet-shared \
  --subnet-prefixes 10.10.1.0/24

az network vnet create \
  --resource-group rg-orders-prod \
  --name vnet-orders-prod \
  --location southeastasia \
  --address-prefixes 10.20.0.0/16 \
  --subnet-name snet-app \
  --subnet-prefixes 10.20.1.0/24
~~~

Lệnh tạo VNet không tự tạo VM hoặc dịch vụ kiểm thử. Một peering **Connected** cũng chưa chứng minh có ứng dụng ở hai đầu có thể trao đổi với nhau.

## 7. Những tùy chọn peering cần hiểu chính xác

Azure cung cấp nhiều thuộc tính peering ngoài tên và remote VNet. Không nên bật tất cả mặc định.

| Thuộc tính / tùy chọn CLI | Ý nghĩa | Khi nên dùng |
|---|---|---|
| **Allow virtual network access** / **--allow-vnet-access** | Cho phép truy cập tài nguyên trong VNet phía kia qua peering | Kết nối IP riêng trực tiếp giữa hai VNet |
| **Allow forwarded traffic** / **--allow-forwarded-traffic** | Chấp nhận lưu lượng **được chuyển tiếp** từ VNet được peering | Khi traffic đi qua NVA/Azure Firewall hoặc thiết bị chuyển tiếp đã được thiết kế |
| **Allow gateway transit** / **--allow-gateway-transit** | Cho phép mạng peer sử dụng gateway trong VNet này theo điều kiện hỗ trợ | Hub có VPN Gateway/ExpressRoute gateway muốn chia sẻ đường kết nối |
| **Use remote gateways** / **--use-remote-gateways** | Yêu cầu VNet dùng gateway của VNet được peering | Spoke muốn dùng gateway ở hub thay vì gateway của chính mình |

### 7.1. Cho phép VNet access không đồng nghĩa cho phép mọi gói tin

Ngay cả khi VNet access được bật ở cả hai phía, NSG, route table, firewall OS và ứng dụng vẫn quyết định kết nối cụ thể có hoạt động không. Người dùng cần xác định **nguồn, đích, giao thức, port và chiều lưu lượng**, không chỉ trạng thái peering.

### 7.2. Forwarded traffic: lưu lượng qua thiết bị trung gian

Giả sử một Azure Firewall ở hub nhận lưu lượng từ Spoke A rồi chuyển tiếp đến Spoke B. Để mô hình này hoạt động, thường phải:

- Có các peering giữa từng spoke và hub.
- Bật **Allow forwarded traffic** ở các peering/hướng cần tiếp nhận lưu lượng được chuyển tiếp.
- Cấu hình **UDR** trên các subnet phù hợp để chuyển lưu lượng tới private IP của firewall/NVA.
- Đảm bảo thiết bị có thể forwarding và chính sách firewall cho phép luồng cần thiết.
- Kiểm tra **đường đi và đường về** để tránh routing bất đối xứng.
- Kiểm tra NSG và các yêu cầu về DNS.

Chỉ bật forwarded traffic không tạo router và không tạo transit route tự động.

### 7.3. Gateway transit: dùng gateway của hub

Mô hình thông dụng: hub có VPN Gateway hoặc ExpressRoute gateway nối đến mạng doanh nghiệp; spoke muốn dùng đường này để liên lạc với on-premises.

~~~mermaid
flowchart LR
    O["On-premises"] <-->|VPN/ExpressRoute| G["Gateway ở hub VNet"]
    G --- H["Hub VNet"]
    H <-->|Peering với gateway transit| S["Spoke VNet"]
~~~

Các điều kiện chung cần xét:

1. Hub có gateway phù hợp và cấu hình định tuyến đáp ứng nhu cầu.
2. Peering **hub → spoke** bật **Allow gateway transit**.
3. Peering **spoke → hub** bật **Use remote gateways**.
4. Spoke không đồng thời có một virtual network gateway riêng không tương thích với việc dùng remote gateway, và không thể dùng nhiều remote gateway theo cách peering thông thường.
5. Các route on-premises, phạm vi địa chỉ, chính sách truy cập và đường trả về phải được kiểm tra.

Gateway transit khác hoàn toàn forwarded traffic. Gateway transit phục vụ việc sử dụng virtual network gateway của VNet peer trong những cấu hình hỗ trợ; forwarded traffic phục vụ các gói tin đã đi qua một thiết bị chuyển tiếp.

Trước khi bật trên production, xem khả năng hỗ trợ của kiểu gateway, vùng triển khai và dịch vụ kết nối cụ thể. Không tự suy diễn rằng một gateway bất kỳ đều có thể chia sẻ cho mọi spoke.

## 8. Routing: vì sao Connected vẫn chưa đủ?

Khi peering được thiết lập, Azure cập nhật đường định tuyến hệ thống thích hợp cho các prefix ở phía VNet peer. Tài nguyên trong VNet A có thể thấy route đến địa chỉ của VNet B với next hop kiểu **VNet peering**.

Tuy nhiên, **User Defined Route (UDR)**, tuyến từ gateway, chính sách và khả năng forwarding có thể làm thay đổi đường đi dự kiến. Luôn kiểm tra effective routes trên network interface của workload thay vì chỉ suy luận từ sơ đồ.

### 8.1. Đường đi trực tiếp

Với ví dụ cơ bản, gói tin từ **10.20.1.10** đến **10.10.1.10** đi qua peering giữa spoke và hub nếu:

- Hai VNet được peering thành công.
- VNet access được cho phép.
- Route hiệu lực hướng traffic đến prefix mạng bên kia qua peering.
- NSG và firewall cho phép TCP/443.
- Máy dịch vụ hub có địa chỉ IP đúng và lắng nghe cổng 443.

Không cần public IP cho hai máy chỉ để phục vụ giao tiếp qua VNet peering.

### 8.2. Trường hợp UDR chuyển hướng qua firewall

Nếu muốn toàn bộ traffic spoke đến hub đi qua firewall, có thể cấu hình UDR với next hop **Virtual appliance** và private IP của firewall trên subnet liên quan. Tuy nhiên, phải thiết kế cả route phản hồi, policy và vùng địa chỉ cho phép để không vô tình chặn DNS, các endpoint nền tảng hoặc lưu lượng quản trị thiết yếu.

Một lỗi phổ biến là route chiều đi qua firewall nhưng chiều về đi trực tiếp hoặc qua gateway khác. Khi xử lý lỗi, hãy kiểm tra từng chiều và trạng thái kết nối trên thiết bị.

### 8.3. Kiểm tra effective routes

Nếu workload là VM với network interface phù hợp, có thể dùng CLI xem effective route table:

~~~bash
az network nic show-effective-route-table \
  --resource-group "<vm-resource-group>" \
  --name "<nic-name>" \
  --output table
~~~

Tính năng đọc effective routes có thể yêu cầu trạng thái VM, quyền và điều kiện hỗ trợ tương ứng. Hãy tìm route dành cho prefix peer, next hop và các tuyến UDR hoặc gateway có độ ưu tiên ảnh hưởng đến kết nối. Nếu route không xuất hiện, kiểm tra peering state và address space synchronization.

## 9. NSG, firewall và phạm vi tin cậy

Peering chỉ cung cấp **khả năng kết nối cấp mạng**; không nên biến điều đó thành quyền truy cập ứng dụng không kiểm soát.

### 9.1. NSG rule trong tình huống mẫu

Nếu dịch vụ ở hub sử dụng TCP/443 và chỉ workload trong spoke được phép gọi, hãy thiết kế rule có phạm vi nguồn và đích cụ thể. Chẳng hạn:

| Tiêu chí | Giá trị minh họa |
|---|---|
| Hướng | Inbound |
| Protocol | TCP |
| Source address | 10.20.1.0/24 |
| Destination address | 10.10.1.10 hoặc subnet dịch vụ phù hợp |
| Destination port | 443 |
| Action | Allow |
| Priority | Nhỏ hơn rule deny áp dụng phù hợp |

Không mở toàn bộ cổng quản trị 22/3389 từ mọi VNet peer nếu không có nhu cầu. Khi đã có allow có chủ đích, cần đánh giá các rule rộng hơn ở cả subnet và NIC, nhất là mặc định VirtualNetwork.

NSG là stateful với các kết nối hiện hành theo cách dịch vụ hỗ trợ; vẫn phải rà soát chiều lưu lượng khởi tạo, tường lửa trung gian và route trả về.

### 9.2. Azure Firewall ở hub

Một hub có Azure Firewall có thể tập trung kiểm soát luồng giữa nhiều VNet. Nhưng firewall không tự động được đặt trên đường đi chỉ vì VNet peering với hub. Cần UDR thích hợp, peering forwarded traffic và cấu hình policy.

Nếu hai spoke có peering trực tiếp hoặc một route khác, traffic có thể không đi qua firewall như ý định. Phải xem effective routes và kiểm thử để xác nhận đường đi thực tế.

### 9.3. Phân tách vùng tin cậy

Đối với môi trường production và development:

- Cân nhắc có cần peering trực tiếp hay chỉ cần truy cập qua endpoint dịch vụ.
- Dùng NSG và firewall để thu hẹp nguồn và cổng.
- Tách danh tính và quyền quản trị giữa các nhóm.
- Không coi VNet peering là một hàng rào xác thực người dùng.
- Sử dụng TLS hoặc cơ chế mã hóa ứng dụng khi chính sách yêu cầu bảo mật dữ liệu khi truyền; không coi peering là sự thay thế tự động cho mã hóa tầng ứng dụng.

## 10. DNS: giao tiếp IP được chưa có nghĩa tên miền phân giải được

Một workload thường gọi dịch vụ bằng tên như **api.orders.internal** thay vì địa chỉ IP. Sau khi peering Connected, bạn có thể ping hoặc kết nối bằng địa chỉ IP riêng nhưng vẫn không thể truy cập bằng tên.

VNet peering chủ yếu giải quyết **khả năng tiếp cận IP và routing**, không tự thiết lập một hệ thống DNS dùng chung để giải quyết mọi tên máy trong các VNet.

### 10.1. Azure-provided DNS

Azure-provided DNS hỗ trợ phân giải theo ngữ cảnh VNet, nhưng **không tự động bảo đảm phân giải tên máy ở VNet được peering** chỉ vì peering đã tạo. Cần thiết kế DNS thích hợp khi các dịch vụ phải gọi nhau bằng hostname.

### 10.2. Private DNS Zone

Một cách phổ biến là dùng Azure Private DNS Zone và liên kết zone với các VNet cần phân giải.

~~~mermaid
flowchart TD
    Z["Private DNS Zone<br/>orders.internal"] --> L1["Virtual Network Link: vnet-hub"]
    Z --> L2["Virtual Network Link: vnet-orders-prod"]
    L1 --> H["Workload ở hub"]
    L2 --> S["Workload ở spoke"]
    S -->|Tra cứu api.orders.internal| Z
~~~

Lưu ý:

- Cần có record phù hợp (A, CNAME hoặc record khác theo nhu cầu).
- Liên kết zone đến các VNet cần truy vấn; tính năng đăng ký tự động chỉ áp dụng trong những điều kiện được hỗ trợ, không phải mọi tên dịch vụ được tạo tự động.
- Nếu dùng custom DNS server hoặc Azure DNS Private Resolver, phải cấu hình forwarder và đường mạng đến DNS phù hợp.
- NSG/firewall và routing cần cho phép truy vấn DNS khi đi đến DNS server tùy chỉnh.
- Private Endpoint thường đòi hỏi cấu hình DNS private phù hợp để hostname của dịch vụ trỏ đến private IP được cấp.

### 10.3. Quy trình kiểm tra DNS

1. Trên workload ở spoke, tra cứu hostname bằng **nslookup** hoặc **dig**.
2. Ghi lại DNS server đang được dùng.
3. Xác minh kết quả trỏ tới IP riêng dự kiến.
4. Kiểm tra zone/link/record và cấu hình forwarder nếu trả về NXDOMAIN hoặc IP không mong muốn.
5. Sau khi DNS trả lời đúng, thử kết nối đến port của dịch vụ và kiểm tra chứng chỉ TLS.

Không dùng việc phân giải tên thành công làm bằng chứng rằng firewall cho phép port ứng dụng. DNS chỉ xác định đích, còn đường kết nối thực tế phải được kiểm thử riêng.

## 11. Kiểm thử kết nối end-to-end

Sau khi peering đạt Connected, hãy xác nhận kết nối theo thứ tự để dễ xác định lớp gây lỗi.

### 11.1. Bước A: xác nhận peering

~~~bash
az network vnet peering show \
  --resource-group rg-network-hub \
  --vnet-name vnet-hub \
  --name hub-to-orders \
  --query "{state:peeringState,remote:remoteVirtualNetwork.id}" \
  --output json

az network vnet peering show \
  --resource-group rg-orders-prod \
  --vnet-name vnet-orders-prod \
  --name orders-to-hub \
  --query "{state:peeringState,remote:remoteVirtualNetwork.id}" \
  --output json
~~~

Cả hai cần tham chiếu đúng VNet và có trạng thái **Connected**.

### 11.2. Bước B: xác nhận route

Kiểm tra effective routes từ NIC của VM ứng dụng, đặc biệt route tới **10.10.0.0/16**. Nếu có UDR, cần hiểu vì sao next hop có thể không còn là VNet peering.

### 11.3. Bước C: thử kết nối TCP

Trên một VM Linux ở spoke có công cụ phù hợp:

~~~bash
# Kết nối TCP/443 đến dịch vụ riêng ở hub
nc -vz -w 5 10.10.1.10 443

# Nếu dịch vụ HTTPS thực sự hoạt động trên đích
curl -vk --connect-timeout 5 https://10.10.1.10/
~~~

Tùy công cụ và chứng chỉ, gọi HTTPS bằng địa chỉ IP có thể báo hostname mismatch; đó là lỗi xác thực tên máy/TLS, không nhất thiết là lỗi routing. Để xác minh chuẩn, gọi bằng hostname hợp lệ và chứng chỉ phù hợp thay vì bỏ qua xác thực TLS. Chỉ dùng tùy chọn **-k** để chẩn đoán trong lab, không dùng trong ứng dụng production.

Trên Windows có thể thử:

~~~powershell
Test-NetConnection -ComputerName 10.10.1.10 -Port 443
~~~

Một số máy không phản hồi ICMP/ping do firewall, vì vậy ping thất bại **không đủ** kết luận VNet peering bị lỗi. Ưu tiên thử đúng protocol và port đang được ứng dụng sử dụng.

### 11.4. Bước D: kiểm tra ứng dụng

Ngay cả khi TCP/443 mở, yêu cầu HTTP vẫn có thể thất bại vì hostname, authentication, certificate, backend health hoặc chính sách ứng dụng. Hãy thu thập log phía client và server để tách lỗi tầng mạng khỏi lỗi tầng ứng dụng.

### 11.5. Công cụ chẩn đoán của Azure

- **Network Watcher – Connection troubleshoot:** kiểm tra khả năng kết nối từ một nguồn Azure đến đích được hỗ trợ và hỗ trợ định vị chặng lỗi.
- **Network Watcher – IP flow verify:** hỗ trợ xác định rule NSG cho phép/chặn một luồng IP, tùy tài nguyên hỗ trợ.
- **Effective security rules:** xem các rule NSG hiệu lực trên NIC.
- **Effective routes:** xác định đường đi do system routes, UDR và tuyến liên quan.
- **NSG flow logs hoặc cơ chế ghi log mạng phù hợp:** xem dấu vết lưu lượng nếu đã cấu hình và được hỗ trợ, lưu ý các thay đổi dịch vụ/khả năng logging theo thời gian.

Không tự giả định Network Watcher hay mọi loại log đã bật. Khi dùng công cụ, kiểm tra điều kiện hỗ trợ, region, quyền và chi phí lưu trữ.

## 12. Các lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra / khắc phục |
|---|---|---|
| Không tạo được peering | Address spaces chồng lấn | So sánh toàn bộ address spaces, không chỉ các subnet hiện có |
| Không tạo được remote peer | Thiếu quyền ở subscription/VNet bên kia | Kiểm tra Azure RBAC trên cả hai VNet và phối hợp owner |
| Trạng thái **Initiated** | Mới có một phía hoặc phía remote chưa hoàn tất | Tạo/kiểm tra peering ngược và remote VNet ID |
| Trạng thái **Disconnected** | Peering ở một phía đã bị xóa hoặc quan hệ không còn đồng bộ | Xác minh hai phía, dọn peering lỗi và tạo lại theo quy trình |
| **Connected** nhưng không kết nối TCP được | NSG, firewall OS, ứng dụng chưa lắng nghe hoặc route sai | Kiểm tra effective rules, routes và service listener |
| Chỉ một chiều kết nối được | Rule hoặc route không đối xứng, host firewall/ứng dụng | Kiểm tra cả chiều đi lẫn chiều trả về |
| Spoke A không gọi được Spoke B qua hub | Peering không bắc cầu | Thêm peering trực tiếp hoặc thiết kế NVA/UDR/forwarded traffic |
| Có IP nhưng không truy cập bằng hostname | DNS zone/record/link/forwarder chưa đúng | Kiểm tra resolver, zone link và kết quả nslookup |
| VM gọi được IP nhưng HTTPS báo lỗi | Sai hostname/chứng chỉ hoặc chính sách TLS | Kiểm tra SNI, DNS và chứng chỉ của ứng dụng |
| Thêm prefix mới nhưng không thấy route | Peering cần đồng bộ address space | Kiểm tra prefix mới, tránh overlap, đồng bộ peering theo hướng dẫn Azure |
| Vào on-premises từ spoke không được | Chưa cấu hình gateway transit, route, gateway hoặc on-prem route | Kiểm tra allow gateway transit, use remote gateways và đường trả về |
| Traffic không qua Azure Firewall | Chưa có UDR hoặc next hop không đúng | Kiểm tra effective routes trên các subnet và tính đối xứng |
| Bất ngờ phát sinh chi phí | Dữ liệu peering, global transfer hoặc firewall/gateway hoạt động | Xem Cost Management và bảng giá theo region |

### 12.1. Nhận biết trạng thái

- **Initiated:** quan hệ ở phía kia chưa hoàn chỉnh hoặc mới cấu hình một đầu.
- **Connected:** hai đầu peering được thiết lập thành công, nhưng chưa bảo đảm traffic ứng dụng đi được.
- **Disconnected:** một đầu của quan hệ có thể đã bị xóa hoặc cấu hình không còn đầy đủ; cần kiểm tra lại thay vì giả định sẽ tự khôi phục.

Tên và trạng thái cụ thể cần đối chiếu thông tin hiện hành của Azure, nhất là khi đang thay đổi địa chỉ, cấu hình hoặc peering trong những đợt triển khai lớn.

## 13. Thay đổi địa chỉ sau khi đã peering

Đôi khi ứng dụng cần bổ sung subnet và address space. Ví dụ spoke dùng 10.20.0.0/16 và muốn mở rộng thêm **10.21.0.0/16**.

Các bước an toàn:

1. Kiểm tra toàn bộ sơ đồ cấp phát IP của tổ chức và các VNet peer để bảo đảm prefix bổ sung không trùng.
2. Kiểm tra ảnh hưởng đến routing, NSG, firewall, DNS, gateway và hệ thống on-premises.
3. Cập nhật address space của VNet theo quy trình được hỗ trợ.
4. Đồng bộ peering nếu Azure yêu cầu để các bên nhận prefix mới.
5. Kiểm tra effective routes, NSG và kết nối thực tế.

CLI hỗ trợ thao tác đồng bộ peering trong những trường hợp tương ứng:

~~~bash
az network vnet peering sync \
  --resource-group rg-network-hub \
  --vnet-name vnet-hub \
  --name hub-to-orders

az network vnet peering sync \
  --resource-group rg-orders-prod \
  --vnet-name vnet-orders-prod \
  --name orders-to-hub
~~~

Việc bổ sung hoặc thay đổi prefix không phải lúc nào cũng cần xóa/recreate peering. Nhưng cần kiểm tra điều kiện hỗ trợ của kiểu thay đổi, tài nguyên phụ thuộc và trạng thái hệ thống. Không tự sửa prefix trên production khi chưa có kế hoạch chuyển địa chỉ.

## 14. So sánh VNet peering với các phương án kết nối khác

| Công nghệ | Mục đích chính | Điểm phân biệt |
|---|---|---|
| **VNet peering** | Kết nối IP riêng giữa hai Azure VNet | Đường kết nối trực tiếp trên backbone; mỗi VNet giữ cấu hình riêng; không bắc cầu mặc định |
| **VPN Gateway / VNet-to-VNet VPN** | Kết nối qua VPN tunnel trong những tình huống phù hợp | Có gateway và VPN/IPsec; cách vận hành, hiệu năng và chi phí khác peering |
| **ExpressRoute** | Kết nối riêng giữa hạ tầng doanh nghiệp và dịch vụ Microsoft | Thường dùng cho mạng on-premises/hybrid; không thay thế mặc định cho mọi quan hệ VNet |
| **Azure Virtual WAN** | Quản trị kết nối nhiều site/branch/VNet ở quy mô rộng | Có hub và dịch vụ định tuyến được quản lý theo mô hình riêng |
| **Private Endpoint / Private Link** | Truy cập một tài nguyên/dịch vụ cụ thể qua private IP | Không tự tạo kết nối full-mesh giữa hai VNet; thường cần DNS riêng |
| **NVA / Azure Firewall + UDR** | Kiểm tra, lọc và chuyển tiếp lưu lượng theo chính sách | Cần thiết kế định tuyến và phí vận hành; thường bổ sung cho peering |
| **Cùng một VNet** | Các subnet nằm chung một VNet | Đơn giản hơn khi không có nhu cầu tách ranh giới mạng VNet |

Hãy chọn phương án dựa trên nhu cầu: kết nối bao nhiêu mạng, truy cập toàn mạng hay chỉ một dịch vụ, định tuyến bắc cầu, mã hóa bắt buộc, chính sách bảo mật, khả năng mở rộng, chi phí và trách nhiệm vận hành.

## 15. Thiết kế production: hiệu năng, sẵn sàng và chi phí

### 15.1. Hiệu năng và độ trễ

VNet peering phù hợp với lưu lượng IP riêng có thông lượng tốt, nhưng hiệu năng thực tế vẫn phụ thuộc vào:

- Region của các VNet và khoảng cách địa lý.
- Kích thước và giới hạn mạng của VM/dịch vụ ở hai đầu.
- Băng thông, latency của ứng dụng, TCP và số kết nối đồng thời.
- NSG, UDR, firewall/NVA và đường đi thêm vào.
- Giới hạn nền tảng hoặc ràng buộc của dịch vụ sử dụng.

Không hứa hẹn rằng global peering sẽ có độ trễ như cùng region. Hãy kiểm thử bằng workload đại diện và thu thập kết quả trước khi quyết định kiến trúc nhạy cảm với độ trễ.

### 15.2. Availability và thay đổi cấu hình

VNet peering là dịch vụ kết nối được Azure quản lý, nhưng ứng dụng vẫn cần thiết kế sẵn sàng cao cho thành phần của mình. Với dịch vụ quan trọng:

- Xác định tác động khi thay đổi route, peering, DNS hoặc firewall.
- Triển khai gateway, firewall/NVA và DNS theo mô hình sẵn sàng phù hợp nếu những thành phần này nằm trên đường đi.
- Duy trì giám sát thời gian phản hồi, tỷ lệ kết nối lỗi và trạng thái các dịch vụ đích.
- Có runbook rollback cho UDR, rule NSG và các thay đổi peering.

### 15.3. Chi phí

Không giả định peering miễn phí chỉ vì không phải tạo VPN Gateway. Azure tính phí theo mô hình và khu vực áp dụng cho **dữ liệu qua VNet peering**, trong đó regional và global peering có thể có mức giá hoặc cách áp dụng khác nhau. Những thành phần khác như Azure Firewall, VPN Gateway, Private DNS Resolver và dữ liệu logging có mô hình phí riêng.

Ví dụ phân tích chi phí:

- Xác định lượng GB/tháng đi giữa VNet hub và VNet spoke theo **mỗi chiều**.
- Xác định hai region của luồng nếu là global peering.
- Đối chiếu bảng giá Azure VNet peering hiện hành cho vùng và kiểu kết nối cụ thể.
- Cộng chi phí firewall/gateway/giám sát nếu luồng thực tế đi qua chúng.
- Theo dõi chi phí bằng Azure Cost Management sau triển khai.

Không đưa ra đơn giá cố định khi chưa kiểm tra region, bảng giá và thời điểm áp dụng.

### 15.4. Khả năng mở rộng và vòng đời

Khi số lượng spoke tăng, số peering, UDR, rule, private DNS link và quyền quản trị cũng tăng. Một kiến trúc chỉ có hai VNet có thể cấu hình thủ công; hệ thống hàng chục hoặc hàng trăm VNet nên dùng Infrastructure as Code và cân nhắc mô hình quản trị mạng tập trung.

Quy trình thay đổi nên gồm:

1. Quản lý quy hoạch địa chỉ IP tập trung để tránh overlap.
2. Có tên peering nhất quán theo nguồn–đích.
3. Lưu cấu hình peering, route, NSG và DNS trong hạ tầng-as-code khi phù hợp.
4. Review pull request để phát hiện đường kết nối không cần thiết.
5. Kiểm thử connectivity và security trước/sau triển khai.
6. Theo dõi chi phí, owner và ngày hết hạn của những liên kết tạm thời.

## 16. Dọn dẹp tài nguyên thực hành và xử lý sự cố gỡ peering

Nếu chỉ thực hành kết nối giữa hai VNet dùng riêng cho lab, hãy xóa quan hệ peering ở **cả hai đầu** khi không còn cần:

~~~bash
az network vnet peering delete \
  --resource-group rg-network-hub \
  --vnet-name vnet-hub \
  --name hub-to-orders

az network vnet peering delete \
  --resource-group rg-orders-prod \
  --vnet-name vnet-orders-prod \
  --name orders-to-hub
~~~

Sau đó kiểm tra danh sách peering ở cả hai VNet. Không tự xóa VNet, subnet hoặc resource group của production. Nếu các VNet được tạo riêng cho lab, chỉ xóa khi xác nhận không có tài nguyên hoặc dữ liệu cần giữ, đã kiểm tra các dependency và được chủ sở hữu phê duyệt.

Nếu đang xử lý một peering **Disconnected** do phía remote đã bị xóa, hãy rà soát từng đầu và tạo lại quan hệ sau khi cấu hình đã thống nhất. Tránh để lại peering mồ côi hoặc route thủ công hướng đến thiết bị không còn tồn tại.

## 17. Checklist trước khi đưa vào production

- [ ] Hai VNet có address spaces không trùng nhau và đã dự phòng kế hoạch mở rộng.
- [ ] Owner, subscription, resource group và quyền tạo peering ở hai bên đã được xác nhận.
- [ ] Cả hai hướng peering được tạo, trỏ đúng resource ID và có trạng thái Connected.
- [ ] Mọi luồng cần thiết đã được liệt kê theo nguồn, đích, port, protocol và yêu cầu xác thực.
- [ ] NSG, firewall của hệ điều hành và rule ứng dụng chỉ cho phép traffic cần thiết.
- [ ] Effective routes của chiều đi/chiều về phù hợp, nhất là khi có UDR và firewall.
- [ ] Không giả định peering có tính bắc cầu giữa nhiều spoke.
- [ ] Chỉ bật forwarded traffic/gateway transit khi kiến trúc thực sự yêu cầu và đã kiểm chứng.
- [ ] DNS private/custom DNS được thiết kế và phân giải hostname thành IP đúng.
- [ ] Đã kiểm thử kết nối TCP/ứng dụng, TLS và đường truy cập bị từ chối.
- [ ] Đã đánh giá rủi ro thay đổi, rollback, hiệu năng và chi phí.
- [ ] Cấu hình đã được ghi vào IaC/tài liệu và có người chịu trách nhiệm vận hành.

## 18. Bài tập thực hành

### Bài 1: Kết nối hai VNet cùng region

Tạo hai VNet lab có address spaces không trùng nhau, ví dụ 10.10.0.0/16 và 10.20.0.0/16. Thiết lập peering hai chiều bằng Azure CLI, xác nhận trạng thái Connected, sau đó mô tả các điều kiện bổ sung để một VM ở spoke kết nối tới dịch vụ TCP/443 ở hub.

**Tiêu chí đạt:** có đầy đủ hai peering, địa chỉ không trùng, trạng thái đúng, biết kiểm tra NSG/route/port, không kết luận chỉ dựa trên Connected.

### Bài 2: Phân tích mạng hub–spoke ba VNet

Hub dùng 10.10.0.0/16, Spoke A dùng 10.20.0.0/16 và Spoke B dùng 10.30.0.0/16. A và B đều peering với hub nhưng không gọi được nhau.

Hãy giải thích tính không bắc cầu của peering. Đề xuất hai kiến trúc để A gọi B và so sánh tác động của chúng đến routing, chi phí và bảo mật.

### Bài 3: Chẩn đoán DNS

Workload ở spoke kết nối tới **10.10.1.10:443** thành công nhưng gọi **api.orders.internal** thất bại.

Lập danh sách phép kiểm tra DNS client, zone, record, virtual network link, DNS server và chứng chỉ. Giải thích vì sao tạo thêm một NSG allow rule không nhất thiết giải quyết lỗi này.

### Bài 4: Thiết kế gateway transit

Hub VNet có VPN Gateway nối tới on-premises. Spoke chưa có gateway riêng và cần truy cập subnet on-premises. Vẽ sơ đồ và mô tả ý nghĩa của Allow gateway transit ở hub, Use remote gateways ở spoke, route chiều về và giới hạn khi spoke đang có gateway riêng.

### Câu hỏi tự kiểm tra

1. Vì sao hai VNet có dải IP chồng lấn không thể peering trực tiếp?
2. Hai VNet ở hai Azure region khác nhau có thể peering trong điều kiện phù hợp không?
3. Peering Connected có đồng nghĩa TCP/443 sẽ hoạt động không?
4. Ba VNet A–Hub–B có tự động giao tiếp A↔B qua hub không?
5. Allow forwarded traffic có tự động tạo NVA/route bắc cầu không?
6. Khi nào nên dùng Private Endpoint thay vì peering toàn VNet?
7. Vì sao phải thiết kế DNS riêng cho tên dịch vụ ở peered VNet?
8. Khi mở rộng address space, tại sao phải kiểm tra peering synchronization và effective routes?
9. Regional peering và global peering có thể ảnh hưởng đến chi phí như thế nào?

## 19. Tài liệu tham khảo

- [Azure Virtual Network peering — Microsoft Learn](https://learn.microsoft.com/azure/virtual-network/virtual-network-peering-overview)
- [Create, change or delete a virtual network peering](https://learn.microsoft.com/azure/virtual-network/virtual-network-manage-peering)
- [Azure virtual network traffic routing](https://learn.microsoft.com/azure/virtual-network/virtual-networks-udr-overview)
- [Azure Network Security Groups](https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview)
- [Azure Private DNS](https://learn.microsoft.com/azure/dns/private-dns-overview)
- [Azure VPN Gateway: Configure gateway transit for virtual network peering](https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-peering-gateway-transit)
- [Network Watcher connection troubleshoot](https://learn.microsoft.com/azure/network-watcher/network-watcher-connectivity-overview)
- [Azure Virtual Network pricing](https://azure.microsoft.com/pricing/details/virtual-network/)

