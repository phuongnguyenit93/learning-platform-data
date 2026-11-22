# Thiết kế địa chỉ IP cho Azure Virtual Network

Một ứng dụng trên Azure thường có nhiều thành phần: web/API, dịch vụ dữ liệu, máy ảo quản trị, private endpoint và đường kết nối đến hệ thống tại doanh nghiệp. Nếu đặt địa chỉ IP theo cảm tính, các mạng rất dễ **trùng dải**, thiếu chỗ cho tài nguyên mở rộng hoặc phải thay đổi cấu hình khi kết nối VNet bằng peering, VPN hay ExpressRoute. Thiết kế IP từ đầu giúp tổ chức tài nguyên rõ ràng, dễ phân vùng bảo mật và giảm gián đoạn khi mở rộng.

Đây là bài học thuộc chương **Mạng ảo và phân giải tên** của module `CLOUD_PROVIDERS_AZURE`. Phạm vi module đi từ subscription, resource group, Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; đồng thời hướng dẫn triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng trên Microsoft Azure. Bài này tập trung vào **quy hoạch địa chỉ IP của Azure Virtual Network (VNet)**, làm nền tảng cho các phần định tuyến, DNS, kết nối riêng và quản trị mạng tiếp theo.

## 1. Mục tiêu của một thiết kế địa chỉ IP tốt

Sau bài học, bạn có thể:

- Phân biệt **VNet address space**, **subnet prefix**, **private IP** và **public IP**.
- Đọc ký hiệu CIDR và tính số địa chỉ IPv4 có thể sử dụng trong subnet Azure.
- Chọn dải địa chỉ riêng không chồng lấn với VNet khác và mạng on-premises dự kiến kết nối.
- Phân bổ subnet theo vai trò workload và yêu cầu của các dịch vụ Azure.
- Dự trù địa chỉ cho autoscale, private endpoints, dịch vụ được ủy quyền subnet và mở rộng dài hạn.
- Kiểm tra kế hoạch bằng Azure Portal hoặc Azure CLI trước khi triển khai.

**Nguyên tắc xuyên suốt:** thiết kế từ phạm vi kết nối toàn tổ chức xuống VNet rồi mới chia subnet. Một CIDR hợp lệ về mặt cú pháp chưa chắc phù hợp với kiến trúc thực tế.

## 2. VNet address space, subnet và địa chỉ IP

**Azure Virtual Network** là mạng riêng ảo được quản lý trong Azure. Mỗi VNet có một hoặc nhiều khối địa chỉ IP; trong khối đó, bạn tạo các **subnet** để phân chia tài nguyên theo chức năng, chính sách và yêu cầu kết nối.

Ví dụ:

```text
VNet: vnet-prod-app (10.60.16.0/20)
│
├── snet-app       10.60.16.0/23   Web, API, ứng dụng
├── snet-data      10.60.20.0/24   Thành phần dữ liệu riêng
├── snet-pe        10.60.22.0/24   Private endpoints
├── snet-integrate 10.60.23.0/24   Tích hợp dịch vụ PaaS
└── snet-ops       10.60.24.0/26   Công cụ vận hành

Các phần dải địa chỉ còn lại: để dành cho tăng trưởng.
```

Trong ví dụ này:

- `10.60.16.0/20` là **address space** được gán cho VNet.
- `10.60.16.0/23` là một **subnet prefix**, phải nằm trọn trong address space của VNet.
- Mỗi NIC, VM hoặc private endpoint phù hợp có thể sử dụng một **private IP** trong subnet, theo cách Azure và dịch vụ cấp phát.
- **Public IP** dùng để kết nối qua Internet hoặc làm điểm đầu của dịch vụ công khai; public IP không được tạo bằng cách chọn một địa chỉ tùy ý trong dải RFC 1918.

Một VNet có thể có nhiều address space tách biệt; các subnet phải thuộc address space của VNet và không được chồng lấn nhau. Hai subnet trong cùng VNet không thể dùng chung vùng địa chỉ.

### IP của VNet có phải một địa chỉ duy nhất?

Không. Địa chỉ như `10.60.16.0/20` mô tả **toàn bộ khoảng IP**, không phải IP gắn cho một thiết bị. VNet không phải một máy chủ cần một IP duy nhất. Các giao diện mạng và tài nguyên bên trong subnet mới sử dụng các địa chỉ cụ thể.

## 3. CIDR và cách tính số địa chỉ IPv4

CIDR (Classless Inter-Domain Routing) viết địa chỉ mạng dưới dạng `địa_chỉ/prefix_length`. Với IPv4, phần trước dấu `/` là địa chỉ gốc; phần sau cho biết số bit mạng trong tổng 32 bit.

Ví dụ:

- `10.60.16.0/20`: 20 bit mạng, 12 bit host → 2^(32−20) = **4.096 địa chỉ IPv4**.
- `10.60.16.0/23`: 23 bit mạng, 9 bit host → **512 địa chỉ**.
- `10.60.20.0/24`: 24 bit mạng, 8 bit host → **256 địa chỉ**.

Công thức:

```text
Số IPv4 trong khối CIDR = 2^(32 - prefix_length)
Số IPv4 có thể dùng trong subnet Azure = tổng số IPv4 - 5
```

Công thức thứ hai dùng cho **subnet IPv4 Azure** vì nền tảng giữ lại năm địa chỉ của mỗi subnet. Không áp dụng phép trừ đó để tính một “VNet IP pool” tổng thể hay để tính IPv6.

| CIDR | Tổng IPv4 | Có thể cấp cho tài nguyên trong subnet Azure | Tình huống tham khảo |
|---|---:|---:|---|
| `/29` | 8 | 3 | Phạm vi kỹ thuật rất nhỏ; nhiều dịch vụ không hỗ trợ hoặc không phù hợp |
| `/28` | 16 | 11 | Môi trường rất nhỏ khi dịch vụ cho phép |
| `/27` | 32 | 27 | Subnet nhỏ hoặc một số subnet hạ tầng chuyên dụng |
| `/26` | 64 | 59 | Workload hoặc subnet chuyên dụng cần tối thiểu lớn hơn |
| `/25` | 128 | 123 | Nhóm VM quy mô vừa |
| `/24` | 256 | 251 | Subnet ứng dụng phổ biến |
| `/23` | 512 | 507 | Nhóm ứng dụng có nhu cầu nhiều IP |
| `/22` | 1.024 | 1.019 | Khối lớn, dự phòng autoscale hoặc yêu cầu cao |

**Lưu ý:** bảng cho biết giới hạn địa chỉ lý thuyết sau phần dự trữ của Azure; không phải cam kết rằng một dịch vụ bất kỳ sẽ chạy trên subnet nhỏ nhất đó. Một số dịch vụ có yêu cầu kích thước subnet và điều kiện triển khai riêng.

### Tính khoảng bắt đầu và kết thúc

Khối `10.60.16.0/20` gồm các địa chỉ từ `10.60.16.0` đến `10.60.31.255`. Vì /20 tương ứng 16 giá trị ở octet thứ ba, các khối liền kề là:

- `10.60.0.0/20` → `10.60.0.0` đến `10.60.15.255`.
- `10.60.16.0/20` → `10.60.16.0` đến `10.60.31.255`.
- `10.60.32.0/20` → `10.60.32.0` đến `10.60.47.255`.
- `10.60.48.0/20` → `10.60.48.0` đến `10.60.63.255`.

Địa chỉ gốc của khối CIDR phải đúng ranh giới bit của prefix. Chẳng hạn, `10.60.17.0/20` **không** là địa chỉ mạng gốc hợp lệ cho khối /20 bắt đầu tại octet thứ ba là 17; khối tương ứng thực tế bắt đầu ở `10.60.16.0/20`.

## 4. Năm địa chỉ Azure dành riêng trong mỗi subnet IPv4

Azure dành riêng **bốn địa chỉ đầu tiên và địa chỉ cuối cùng** trong mỗi subnet IPv4. Chúng không khả dụng để gán cho máy ảo hoặc tài nguyên người dùng.

Với subnet `10.60.20.0/24`:

| Địa chỉ | Trạng thái |
|---|---|
| `10.60.20.0` | Dành riêng bởi Azure |
| `10.60.20.1` | Dành riêng; địa chỉ gateway mặc định |
| `10.60.20.2` | Dành riêng cho nền tảng Azure |
| `10.60.20.3` | Dành riêng cho nền tảng Azure |
| `10.60.20.4` đến `10.60.20.254` | Có thể cấp phát tùy dịch vụ và trạng thái sử dụng |
| `10.60.20.255` | Dành riêng bởi Azure |

Vì vậy, /24 có **251**, không phải 254 địa chỉ có thể cấp cho tài nguyên. Tương tự, /26 có 59 địa chỉ khả dụng và /23 có 507.

Năm địa chỉ này được giữ lại **ở từng subnet**, không phải chỉ giữ một lần ở cấp VNet. Nếu chia một khối lớn thành nhiều subnet nhỏ, số địa chỉ dành riêng cộng dồn sẽ tăng. Đây là một lý do không nên chia subnet quá vụn khi không có nhu cầu quản trị rõ ràng.

## 5. Chọn dải IP riêng và tránh trùng mạng

Các vùng IPv4 riêng được định nghĩa trong RFC 1918:

| Dải riêng | Phạm vi tương ứng | Gợi ý |
|---|---|---|
| `10.0.0.0/8` | `10.0.0.0` – `10.255.255.255` | Dễ phân chia nhiều vùng lớn cho doanh nghiệp |
| `172.16.0.0/12` | `172.16.0.0` – `172.31.255.255` | Lựa chọn bổ sung khi mạng 10/8 đã được sử dụng |
| `192.168.0.0/16` | `192.168.0.0` – `192.168.255.255` | Thường gặp ở văn phòng nhỏ, mạng nhà hoặc lab |

**Không phải cứ nằm trong RFC 1918 là dùng được.** Trước khi chốt dải VNet, hãy kiểm tra địa chỉ của:

1. Các VNet hiện có trong tất cả subscription, region, tenant hoặc tổ chức sẽ kết nối.
2. Mạng tại văn phòng, trung tâm dữ liệu và các site on-premises kết nối qua VPN/ExpressRoute.
3. Mạng của đối tác, nhà cung cấp hoặc dự án có peering/kết nối riêng dự kiến.
4. Hệ thống container, mạng dành cho workload và các dải IP được dịch vụ quản lý yêu cầu.
5. Phạm vi có thể được thêm vào trong tương lai hoặc được dự trữ cho nền tảng mạng chung.

Khi hai mạng sử dụng các khối CIDR **chồng lấn**, việc định tuyến và thiết lập kết nối trực tiếp có thể bị cản trở. Azure VNet peering không hỗ trợ address space chồng lấn. Với kết nối hybrid hoặc mạng đối tác, trùng dải có thể tạo tuyến mơ hồ và buộc phải thiết kế lại hoặc triển khai giải pháp dịch địa chỉ phức tạp.

Ví dụ: VNet dùng `10.60.16.0/20` sẽ chồng lấn với `10.60.20.0/24` vì /24 hoàn toàn nằm bên trong /20. Ngược lại, `10.60.16.0/20` và `10.60.32.0/20` không giao nhau.

**Quyết định quan trọng:** dùng một bảng đăng ký dải IP (IPAM) ở phạm vi tổ chức để tránh hai nhóm triển khai độc lập cùng chọn một CIDR. Bảng này nên ghi chủ sở hữu, mục đích, môi trường, region, subscription, VNet, các route cần kết nối và trạng thái sử dụng/dự phòng.

## 6. Thiết kế địa chỉ từ quy mô tổ chức đến subnet

Trình tự khuyến nghị:

1. **Định nghĩa topology:** mạng hub-spoke, nhiều VNet độc lập, multi-region hay kết nối hybrid.
2. **Đăng ký khối tổng:** dành ra một pool địa chỉ ở cấp tổ chức, ví dụ `10.60.0.0/16`, sau khi xác minh không xung đột.
3. **Chia cho các VNet:** dùng khối riêng cho hub, Production, Staging và Development.
4. **Chia subnet trong từng VNet:** tách theo vai trò workload và yêu cầu kỹ thuật.
5. **Để dư địa tăng trưởng:** giữ các khối trống có ghi chú, không dùng hết chỉ vì còn địa chỉ.
6. **Xem lại cùng nhóm mạng, bảo mật và ứng dụng:** xác minh nhu cầu kết nối, dịch vụ đặc thù và lộ trình mở rộng.

### Ví dụ phân bổ VNet theo môi trường

Giả sử doanh nghiệp đã xác nhận pool `10.60.0.0/16` không xung đột với các mạng cần kết nối.

| VNet | CIDR | Vai trò |
|---|---|---|
| `vnet-hub` | `10.60.0.0/20` | Thành phần kết nối chung, VPN/ExpressRoute, dịch vụ mạng nếu có |
| `vnet-prod-app` | `10.60.16.0/20` | Ứng dụng Production |
| `vnet-test-app` | `10.60.32.0/20` | Kiểm thử, UAT |
| `vnet-dev-app` | `10.60.48.0/20` | Phát triển |
| Khối chưa gán | Phần còn lại của `10.60.0.0/16` | VNet mới, region khác hoặc mở rộng theo quy hoạch |

Mỗi /20 có 4.096 địa chỉ về mặt lý thuyết. Dải này chỉ là ví dụ học tập; tổ chức nên chọn kích thước VNet theo nhu cầu thực thay vì mặc định mọi VNet phải là /20. Nếu có nhiều region, có thể thêm một cấp phân bổ theo region trước khi chia theo môi trường.

### Ví dụ chia subnet cho Production

Trong `vnet-prod-app = 10.60.16.0/20`:

| Subnet hoặc vùng dự phòng | CIDR | IPv4 khả dụng trong subnet | Mục đích |
|---|---|---:|---|
| `snet-app` | `10.60.16.0/23` | 507 | Ứng dụng/VM cần mở rộng |
| Dự phòng cho ứng dụng | `10.60.18.0/23` | Chưa cấp phát | Để mở rộng bằng subnet mới hoặc thiết kế di chuyển phù hợp |
| `snet-data` | `10.60.20.0/24` | 251 | Thành phần dữ liệu dùng private IP |
| Dự phòng cho dữ liệu | `10.60.21.0/24` | Chưa cấp phát | Nhu cầu tương lai |
| `snet-private-endpoints` | `10.60.22.0/24` | 251 | Private endpoints của các dịch vụ |
| `snet-integration` | `10.60.23.0/24` | 251 | Dịch vụ tích hợp VNet theo yêu cầu triển khai |
| `snet-ops` | `10.60.24.0/26` | 59 | Máy hoặc công cụ quản trị |
| Dự phòng khác | Phần còn lại của `10.60.16.0/20` | Chưa cấp phát | Thêm subnet, tăng trưởng hoặc workload mới |

Các subnet minh họa **không chồng lấn** và đều nằm trong /20. Các dòng “Dự phòng” là khoảng địa chỉ **chưa tạo subnet**, nên không có ý nghĩa “IPv4 khả dụng” ở thời điểm hiện tại.

Lưu khoảng địa chỉ liền kề có thể hữu ích trong quy hoạch, nhưng **không bảo đảm** Azure cho phép tăng kích thước trực tiếp một subnet đã có tài nguyên. Thực tế thường phải tạo subnet mới và chuyển tài nguyên theo kế hoạch. Hãy xem yêu cầu của dịch vụ trước khi thiết kế thay đổi.

### Minh họa ranh giới phân bổ

```text
Pool tổ chức: 10.60.0.0/16
|
+-- HUB          10.60.0.0/20
+-- PRODUCTION   10.60.16.0/20
|   +-- APP            10.60.16.0/23
|   +-- APP RESERVED   10.60.18.0/23
|   +-- DATA           10.60.20.0/24
|   +-- DATA RESERVED  10.60.21.0/24
|   +-- PRIVATE EP     10.60.22.0/24
|   +-- INTEGRATION    10.60.23.0/24
|   +-- OPS            10.60.24.0/26
|   +-- FUTURE         vùng chưa phân bổ
+-- TEST         10.60.32.0/20
+-- DEVELOPMENT  10.60.48.0/20
+-- FUTURE       các khối còn lại
```

Pool tổ chức chỉ là **quy ước quy hoạch IPAM**, không nhất thiết là một VNet thật. Mỗi VNet là thực thể riêng ở Azure và có address space được tạo cụ thể.

## 7. Tính công suất subnet theo tải đỉnh và tăng trưởng

Một subnet phải đủ địa chỉ cho **mức sử dụng lớn nhất**, không chỉ số tài nguyên đang chạy.

Giả sử subnet ứng dụng dự kiến có:

- 120 địa chỉ cho VM hoặc giao diện mạng hiện có.
- 80 địa chỉ cho lượt scale-out cao nhất.
- 40 địa chỉ dự phòng cho nâng cấp hoặc triển khai song song.

Tổng nhu cầu là **240 IP có thể cấp phát**. /24 có 251 địa chỉ khả dụng nên đáp ứng về mặt số lượng, nhưng chỉ còn 11 địa chỉ dự phòng cho tình huống ngoài kế hoạch. Chọn /23 với 507 IP khả dụng có thể phù hợp hơn nếu có kế hoạch tăng trưởng và nguồn địa chỉ cho phép.

Một phương pháp khác là chọn tỷ lệ dự phòng. Với nhu cầu đỉnh 300 IP và mong muốn chừa 25% **công suất cấp phát**:

```text
Công suất yêu cầu >= 300 / (1 - 0,25) = 400 IP
/24 -> 251 IP khả dụng: không đủ
/23 -> 507 IP khả dụng: phù hợp về số lượng
```

Tỷ lệ dự phòng 25% chỉ là **giả định minh họa**, không phải quy định mặc định của Azure. Quyết định cuối cùng phụ thuộc vào kế hoạch autoscale, quy trình triển khai xanh/xanh (blue-green), số lượng instance tối đa, tài nguyên dự phòng và yêu cầu thực tế của dịch vụ.

### Các yếu tố làm nhu cầu IP thay đổi

- **VM/NIC:** mỗi cấu hình NIC và secondary IP có thể tiêu thụ thêm địa chỉ trong subnet.
- **Private endpoint:** endpoint thường cần một private IP từ subnet được chọn; nhiều dịch vụ hoặc subresource có thể cần nhiều endpoint.
- **Ứng dụng PaaS với VNet Integration:** mức tiêu thụ IP, subnet delegation và yêu cầu khi scale/upgrade phụ thuộc từng dịch vụ.
- **AKS:** cách tính IP tùy network plugin, chế độ Azure CNI/overlay, số node, pod và nâng cấp cụm; không áp một công thức chung cho mọi cấu hình.
- **Thiết bị mạng ảo và nền tảng:** firewall, gateway hoặc thành phần quản lý có subnet chuyên dụng, yêu cầu số địa chỉ tối thiểu riêng.

Vì mỗi dịch vụ có cách cấp IP khác nhau, hãy lập **bảng nhu cầu theo dịch vụ** trước khi chọn CIDR. Không dùng công thức “mỗi workload = một IP” nếu kiến trúc có nhiều NIC, pod, private endpoint hoặc giai đoạn triển khai song song.

## 8. Subnet chuyên dụng và các giới hạn dịch vụ

Một số dịch vụ yêu cầu **tên subnet cụ thể**, **kích thước tối thiểu** hoặc **delegation**. Đây là các ràng buộc thiết kế, không chỉ là quy ước đặt tên.

| Thành phần | Điều cần kiểm tra khi thiết kế |
|---|---|
| **VPN/ExpressRoute gateway** | Subnet có tên `GatewaySubnet`; cần kích thước phù hợp loại gateway và quy mô mở rộng. Với thiết kế mới, thường ưu tiên tối thiểu /27 hoặc lớn hơn theo yêu cầu dịch vụ. |
| **Azure Bastion** | Subnet chuyên dụng có tên `AzureBastionSubnet`; kiểm tra kích thước tối thiểu, thường /26 cho triển khai mới và yêu cầu SKU. |
| **Azure Firewall** | Subnet `AzureFirewallSubnet`, thường yêu cầu /26 hoặc lớn hơn; một số mô hình còn cần `AzureFirewallManagementSubnet`. |
| **Private endpoints** | Chọn subnet có đủ IP cho từng endpoint và kiểm tra chính sách mạng/NSG, định tuyến, DNS của Private Link. |
| **App Service VNet Integration và PaaS tương tự** | Xem yêu cầu subnet delegation, kích thước tối thiểu và IP cần thêm khi scale hoặc nâng cấp. |
| **AKS** | Thiết kế theo network plugin, số node/pod và cơ chế nâng cấp cụ thể, có thể cần nhiều subnet/vùng địa chỉ. |

Các yêu cầu về CIDR và tính năng có thể thay đổi theo SKU và phiên bản dịch vụ. Khi triển khai thật, đối chiếu tài liệu dịch vụ Azure đang dùng. Không đưa mọi thành phần chung vào một subnet chỉ vì còn nhiều địa chỉ.

**Hub-spoke:** nếu gateway, Bastion hoặc Firewall nằm trong hub, không nhất thiết tạo những subnet chuyên dụng đó ở mọi spoke. Dành địa chỉ ở đúng VNet chứa dịch vụ và kiểm tra các điều kiện route, peering, DNS liên quan.

## 9. Private IP động, tĩnh và vòng đời tài nguyên

Azure thường cấp private IP cho NIC từ subnet. Có hai cách cấu hình phổ biến:

- **Dynamic:** Azure tự chọn địa chỉ từ pool còn trống của subnet. Đây là cách phù hợp với nhiều workload có vòng đời linh hoạt.
- **Static:** khai báo một private IP cụ thể, **nằm trong subnet** và **không thuộc năm địa chỉ Azure dự trữ**, cho NIC hoặc tài nguyên hỗ trợ.

Địa chỉ static hữu ích khi có cấu hình phụ thuộc vào IP cụ thể, nhưng cần quản lý vòng đời và tránh gán trùng. Với ứng dụng có khả năng scale hoặc thay thế instance thường xuyên, nên ưu tiên DNS, service discovery, load balancer hoặc private endpoint phù hợp thay vì cấu hình cố định IP của từng VM.

**Private IP không đồng nghĩa với khả năng truy cập qua Internet.** Việc outbound ra Internet phụ thuộc vào tuyến đường, NAT Gateway, firewall hoặc cơ chế egress khác. Public IP hoặc địa chỉ NAT được thiết kế riêng và không phải một phần của CIDR subnet private.

Không thay IP, xóa subnet hoặc thu hẹp prefix của hệ thống đang chạy nếu chưa kiểm tra các tài nguyên phụ thuộc và lập kế hoạch thay đổi. Một số thao tác có thể bị Azure chặn khi subnet đang được sử dụng; một số thao tác khác có thể gây gián đoạn.

## 10. Mối quan hệ giữa địa chỉ IP, routing, bảo mật và DNS

Thiết kế IP là điều kiện cần cho mạng vận hành tốt, nhưng **không tự tạo ra tuyến đường hoặc quyền truy cập**.

### Định tuyến và kết nối

- **VNet peering:** các address space được peering phải không trùng nhau. Peering nối hai VNet nhưng không mặc nhiên làm mọi peering thành mạng định tuyến bắc cầu.
- **VPN/ExpressRoute:** dải Azure và on-premises cần được phối hợp từ đầu; xác nhận route được quảng bá và các CIDR đối tác.
- **UDR (user-defined route):** dùng khi cần điều khiển hướng đi của lưu lượng qua firewall hoặc network virtual appliance.
- **Network Security Group (NSG):** kiểm soát kết nối ở subnet/NIC; việc hai tài nguyên có IP trong dải hợp lệ không chứng minh chúng được phép trao đổi lưu lượng.

Ví dụ, nếu spoke Production dùng `10.60.16.0/20` còn data center đã dùng `10.60.20.0/24`, kết nối hybrid có thể khó định tuyến vì các khối chồng lấn. Việc thêm NSG rule không giải quyết xung đột CIDR.

### DNS và Private Link

Khi dùng private endpoints cho Storage, SQL hoặc các dịch vụ Azure khác, client cần phân giải hostname đến **đúng private IP**. Thiết kế phải tính cả:

1. Subnet có đủ IP cho endpoint.
2. Private DNS zone phù hợp với dịch vụ.
3. Liên kết (virtual network link) hoặc mô hình DNS forwarder/resolver tới VNet cần phân giải.
4. Khả năng phân giải tên của client on-premises nếu đi qua kết nối hybrid.

DNS có thể phân giải đúng tên nhưng không có route/NSG phù hợp vẫn không kết nối được. Ngược lại, IP không trùng nhưng DNS trỏ về public endpoint cũng có thể khiến lưu lượng đi không đúng đường thiết kế.

## 11. IPv6 và dual stack

Azure hỗ trợ các kịch bản **IPv4/IPv6 dual stack** cho VNet và một số dịch vụ. Khi cần IPv6, hãy lập kế hoạch riêng cho địa chỉ IPv6 thay vì áp dụng công thức IPv4.

Trong thiết kế IPv6 trên Azure, VNet và subnet cần dùng prefix IPv6 theo các kích thước mà nền tảng hỗ trợ; subnet IPv6 thường được quy hoạch theo khối **/64**, trong khi vùng địa chỉ VNet lớn hơn. Xác minh yêu cầu hiện hành của Azure và **khả năng hỗ trợ IPv6 của từng dịch vụ** trước khi triển khai, đặc biệt với load balancer, firewall, gateway, private endpoint và các tích hợp PaaS.

Các câu hỏi quan trọng:

- Ứng dụng thực sự cần IPv6 cho client Internet hay lưu lượng nội bộ?
- Dịch vụ và tuyến kết nối hybrid có hỗ trợ IPv6 end-to-end không?
- DNS cần bản ghi `A`, `AAAA` hay cả hai?
- Bảo mật, giám sát và quy tắc định tuyến đã được thiết kế cho cả IPv4 và IPv6 chưa?

Đối với một kiến trúc đang dùng IPv4 hoàn toàn, không nên bật IPv6 chỉ để “dự phòng” khi chưa đánh giá phụ thuộc. Khi có nhu cầu dual stack, hãy thiết kế và kiểm tra riêng các luồng IPv6.

## 12. Kiểm tra và triển khai ví dụ bằng Azure CLI

Các lệnh dưới đây là **ví dụ**, sử dụng resource group `rg-network-lab`, region `southeastasia` và địa chỉ của bảng Production. Thay tên và subscription cho đúng môi trường lab trước khi chạy. Lệnh tạo VNet/subnet thay đổi tài nguyên Azure; thực hiện trong môi trường được phép và kiểm tra quy trình chi phí của tổ chức.

### Bước 1: Xác nhận subscription và tenant

```bash
az account show --query "{Name:name,Subscription:id,Tenant:tenantId}" --output table
```

Nếu không đúng subscription được giao, dùng Subscription ID chính xác:

```bash
az account set --subscription "<SUBSCRIPTION_ID>"
```

### Bước 2: Tạo VNet và subnet đầu tiên

Giả sử resource group `rg-network-lab` **đã tồn tại** trong đúng subscription:

```bash
az network vnet create \
  --resource-group "rg-network-lab" \
  --location "southeastasia" \
  --name "vnet-prod-app" \
  --address-prefixes "10.60.16.0/20" \
  --subnet-name "snet-app" \
  --subnet-prefixes "10.60.16.0/23"
```

Đây chỉ là ví dụ triển khai VNet/subnet. Không nên dùng tên Production thật cho môi trường thử nghiệm của một tổ chức khi chưa được cấp quyền.

### Bước 3: Tạo subnet không trùng lấn

```bash
az network vnet subnet create \
  --resource-group "rg-network-lab" \
  --vnet-name "vnet-prod-app" \
  --name "snet-data" \
  --address-prefixes "10.60.20.0/24"
```

Có thể tạo các subnet khác theo bảng quy hoạch sau khi xem xét delegation và các ràng buộc đặc thù.

### Bước 4: Đọc lại address space và subnet

```bash
az network vnet show \
  --resource-group "rg-network-lab" \
  --name "vnet-prod-app" \
  --query "{VNet:name,AddressSpaces:addressSpace.addressPrefixes}" \
  --output json
```

```bash
az network vnet subnet list \
  --resource-group "rg-network-lab" \
  --vnet-name "vnet-prod-app" \
  --query "[].{Name:name,AddressPrefix:addressPrefix,AddressPrefixes:addressPrefixes}" \
  --output table
```

Hai lệnh `show` và `list` là lệnh đọc cấu hình, dùng để đối chiếu subnet thực tế với bảng thiết kế. Nếu đang làm trên subscription đã có tài nguyên, ưu tiên chạy các lệnh đọc này trước mọi thao tác tạo/sửa.

### Kiểm tra bằng Azure Portal

Trong Azure Portal:

1. Chọn đúng tenant và subscription.
2. Mở **Virtual networks** và chọn VNet liên quan.
3. Xem **Address space** để xác nhận CIDR của VNet.
4. Mở **Subnets** để kiểm tra tên, prefix và dịch vụ liên quan.
5. Đối chiếu tất cả prefix với bảng IPAM, đặc biệt với mạng hub, peerings và kết nối hybrid.

Azure có thể từ chối lệnh nếu prefix không thuộc address space, subnet đã chồng lấn, thiếu quyền hoặc dịch vụ yêu cầu cấu hình khác. Hãy đọc lỗi và đối chiếu thiết kế trước khi thay một prefix ngẫu nhiên cho “đúng cú pháp”.

## 13. Các lỗi thiết kế thường gặp

| Vấn đề | Hậu quả có thể xảy ra | Cách phòng tránh |
|---|---|---|
| Hai VNet sắp peer dùng CIDR chồng lấn | Không thể peering theo thiết kế hoặc khó định tuyến | Kiểm tra phạm vi toàn tổ chức trước khi cấp CIDR |
| VNet Azure trùng mạng văn phòng | Route hybrid mơ hồ, phải tái đánh địa chỉ hoặc thiết kế NAT | Thu thập toàn bộ CIDR on-premises và các site trước |
| Chọn /28 vì chỉ có vài VM hiện tại | Hết IP khi scale hoặc tạo endpoint | Tính nhu cầu đỉnh và dự phòng theo dịch vụ |
| Quên năm địa chỉ Azure dành riêng | Dự trù công suất nhiều hơn thực tế | Tính 2^(32−prefix) − 5 cho mỗi subnet IPv4 |
| Dùng subnet chung cho dịch vụ cần delegation riêng | Triển khai PaaS thất bại hoặc không đáp ứng ràng buộc | Kiểm tra subnet requirements của từng dịch vụ |
| Chia subnet quá nhỏ và quá nhiều | Lãng phí nhiều địa chỉ dự trữ, quản lý phức tạp | Chia theo ranh giới quản trị và nhu cầu thực tế |
| Không chừa vùng tăng trưởng | Buộc tạo VNet/subnet mới hoặc di chuyển tài nguyên gấp | Dự phòng các khối liền kề và một phần pool tổ chức |
| Chỉ quy hoạch IP mà bỏ qua DNS | Private endpoint tồn tại nhưng ứng dụng không phân giải đúng | Thiết kế private DNS zone và liên kết VNet |
| Dùng IP static của VM trong cấu hình ứng dụng | Phụ thuộc vòng đời VM, khó thay thế và scale | Ưu tiên DNS, load balancing hoặc private endpoint |
| Tự thay prefix trên mạng đang chạy | Có thể gián đoạn, thao tác bị hạn chế hoặc gây sai route | Đánh giá phụ thuộc, lên kế hoạch thay đổi/migration |

## 14. Bài thực hành: lập IP plan cho ứng dụng ba tầng

**Bối cảnh:** Nhóm cần triển khai hệ thống gồm web/API, xử lý dữ liệu, private endpoints và thành phần quản trị. Hệ thống sẽ kết nối một VNet hub có sẵn; môi trường on-premises dùng những dải địa chỉ khác đã được bộ phận mạng xác nhận. Một pool địa chỉ đã được phê duyệt là `10.72.0.0/16`.

**Yêu cầu giả định:**

- Production cần ít nhất 180 IP cho web/API ở tải đỉnh, chưa tính dự phòng.
- Nhóm dữ liệu cần 70 IP.
- Private endpoints dự kiến 24 IP, có kế hoạch tăng lên 60.
- Hạ tầng vận hành cần 15 IP.
- Giữ ít nhất 25% công suất cấp phát chưa dùng ở subnet web/API.
- Mỗi thành phần có subnet độc lập; chuẩn bị thêm vùng trống cho tăng trưởng.
- Tất cả CIDR phải không chồng lấn với hub hoặc on-premises.

### Lời giải tham khảo

Giả sử dành riêng `10.72.16.0/20` cho VNet ứng dụng:

| Subnet | CIDR đề xuất | IP khả dụng | Đánh giá |
|---|---|---:|---|
| `snet-web` | `10.72.16.0/23` | 507 | 180 IP đỉnh và >=25% dự phòng |
| `snet-data` | `10.72.18.0/24` | 251 | 70 IP và tăng trưởng |
| `snet-pe` | `10.72.19.0/24` | 251 | 60 endpoint tương lai |
| `snet-ops` | `10.72.20.0/26` | 59 | 15 IP vận hành |
| Vùng chưa dùng | Phần còn lại của `10.72.16.0/20` | Chưa cấp phát | Subnet mới hoặc mở rộng theo kế hoạch |

Ở đây, /23 là lựa chọn dư dả cho web/API, chứ không phải kích thước tối thiểu bắt buộc. Với 180 IP và dự phòng ít nhất 25% công suất, cần công suất >= 180/0,75 = 240 IP; /24 có 251 IP khả dụng cũng đủ về số lượng. Tuy nhiên, /23 có thể hợp lý hơn khi cân nhắc khả năng autoscale vượt giả định hoặc triển khai song song. Việc chọn /23 hay /24 cuối cùng nên dựa trên kế hoạch tăng trưởng và mức ưu tiên sử dụng pool địa chỉ của tổ chức.

Với `snet-pe`, hãy xác nhận số **private endpoint thực tế**, không chỉ số dịch vụ logic: một dịch vụ có thể tạo nhiều endpoint tùy nhu cầu kết nối đến các subresource. Nếu một dịch vụ cần subnet chuyên dụng hoặc delegation, phải điều chỉnh sơ đồ theo ràng buộc đó.

### Tiêu chí hoàn thành bài thực hành

- Các CIDR đúng ranh giới mạng và nằm trong VNet `10.72.16.0/20`.
- Không có subnet chồng lấn; vùng trống vẫn còn để phân bổ.
- Công suất đã trừ năm IP dành riêng cho Azure ở **mỗi subnet**.
- Đã so sánh với hub, VPN/ExpressRoute, on-premises và network peerings dự kiến.
- Nêu được nhu cầu của private endpoints, DNS và các subnet chuyên dụng nếu sử dụng.
- Lập được bảng IPAM ghi owner, environment, region, subscription, prefix và trạng thái dự phòng.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Subnet IPv4 `10.20.8.0/24` trong Azure có bao nhiêu địa chỉ có thể gán cho tài nguyên?

A. 254  
B. 256  
C. 251

**Đáp án: C.** 256 địa chỉ tất cả, trừ năm địa chỉ được Azure dành riêng.

**Câu 2.** VNet A là `10.60.16.0/20`, VNet B là `10.60.20.0/24`. Có phù hợp để peering trực tiếp không?

**Đáp án:** Không. B nằm bên trong phạm vi của A nên hai address space chồng lấn.

**Câu 3.** Hai subnet `10.60.16.0/23` và `10.60.18.0/23` có chồng lấn không?

**Đáp án:** Không. Subnet đầu phủ octet thứ ba 16–17, subnet thứ hai phủ 18–19; hai khối liền nhau nhưng không giao nhau.

**Câu 4.** Một hệ thống dự kiến tối đa 300 IP và muốn 25% công suất khả dụng còn trống. /24 có đủ không?

**Đáp án:** Không. Cần ít nhất 300/0,75 = 400 IP khả dụng. /24 chỉ có 251; /23 có 507 nên đủ theo công thức quy hoạch.

**Câu 5.** Khi dùng private endpoint cho một Azure Storage account, chỉ cần chọn IP và không cần quan tâm DNS?

**Đáp án:** Sai. Client cần phân giải hostname tới private IP đúng; phải xem xét private DNS zone, liên kết VNet và DNS forwarding nếu có hybrid.

**Câu 6.** Có nên đặt `GatewaySubnet` trong mọi spoke VNet?

**Đáp án:** Không nhất thiết. Chỉ tạo subnet chuyên dụng trong VNet có gateway theo kiến trúc; hub-spoke thường tập trung dịch vụ kết nối ở hub, tùy thiết kế và ràng buộc của nền tảng.

**Câu 7.** Một subnet đã cấp hết IP. Có thể mặc định đổi /24 thành /23 mà không ảnh hưởng tài nguyên đang chạy không?

**Đáp án:** Không. Việc sửa prefix phụ thuộc ranh giới địa chỉ còn trống, resource hiện có và giới hạn dịch vụ. Cần đánh giá và lập kế hoạch mở rộng hoặc chuyển tài nguyên sang subnet mới.

Một bản thiết kế địa chỉ IP tốt không chỉ là các khối CIDR không chồng lấn. Nó còn phải phản ánh topology toàn tổ chức, nhu cầu công suất của Azure services, dự phòng tăng trưởng và mối liên hệ với routing, bảo mật và DNS. Khi các quyết định này được ghi lại trong IPAM ngay từ đầu, việc triển khai và vận hành mạng ảo sẽ dễ kiểm soát hơn.
