# Kết nối point-to-site và site-to-site bằng VPN Gateway

## 1. Mục tiêu bài học

Một ứng dụng trên Microsoft Azure có thể gồm máy ảo, dịch vụ dữ liệu, subnet riêng, các thành phần ứng dụng và công cụ giám sát. Nhiều thành phần chỉ nên truy cập qua địa chỉ IP riêng trong virtual network (VNet). Tuy nhiên, nhân viên làm việc từ xa và hệ thống tại văn phòng vẫn cần kết nối an toàn đến các tài nguyên đó.

**Azure VPN Gateway** cung cấp khả năng thiết lập đường hầm VPN mã hóa qua Internet, kết nối Azure VNet với thiết bị hoặc máy khách bên ngoài. Hai mô hình quan trọng là:

- **Point-to-Site (P2S):** một thiết bị người dùng, ví dụ laptop của kỹ sư, thiết lập kết nối VPN đến Azure.
- **Site-to-Site (S2S):** thiết bị VPN ở chi nhánh hoặc trung tâm dữ liệu kết nối mạng nội bộ của tổ chức với Azure.

Sau bài học, bạn có thể phân biệt P2S và S2S, thiết kế địa chỉ IP không chồng lấn, chuẩn bị VPN Gateway, cấu hình hai mô hình kết nối, hiểu xác thực và định tuyến, kiểm tra bảo mật/khả dụng và xử lý những lỗi thường gặp.

## 2. So sánh P2S và S2S

| Tiêu chí | Point-to-Site (P2S) | Site-to-Site (S2S) |
|---|---|---|
| Đối tượng | Máy tính cá nhân, thiết bị làm việc từ xa | Mạng văn phòng, chi nhánh, trung tâm dữ liệu |
| Đầu bên ngoài Azure | VPN client trên từng thiết bị | Router hoặc firewall/VPN device của site |
| Mô hình kết nối | Người dùng kết nối theo phiên | Đường hầm giữa hai đầu mạng, thường duy trì liên tục |
| Xác thực | Có thể dùng certificate, Microsoft Entra ID hoặc RADIUS theo giao thức và SKU được hỗ trợ | Thường dùng IPsec/IKE với khóa chia sẻ trước (PSK); có thể kèm BGP cho định tuyến |
| Cấp địa chỉ cho client | Địa chỉ từ P2S client address pool | Dùng các dải mạng có sẵn tại site |
| Quy mô điển hình | Truy cập dành cho cá nhân, đội vận hành, người làm việc từ xa | Liên kết văn phòng với các workload trong Azure |
| Vấn đề cần chú ý | Cài client, danh tính, profile, DNS, route trên máy | Thiết bị tương thích, IP công khai, PSK/IKE, định tuyến hai chiều |

**Ví dụ:** kỹ sư đang ở nhà dùng P2S để SSH hoặc RDP vào VM nội bộ trong Azure. Trong khi đó, một hệ thống ERP tại văn phòng cần gọi API nằm trong Azure VNet qua S2S để toàn mạng nội bộ có đường kết nối thường trực.

P2S và S2S có thể cùng sử dụng một VPN Gateway nếu SKU, cấu hình và các giới hạn sản phẩm cho phép. Chúng giải quyết hai nhu cầu khác nhau, không nhất thiết phải chọn chỉ một mô hình.

## 3. Các thành phần cần hiểu

### 3.1. Azure Virtual Network và subnet

**Virtual Network (VNet)** là không gian mạng riêng trên Azure. Bên trong VNet có các subnet cho workload, ví dụ subnet dành cho VM ứng dụng hoặc cơ sở dữ liệu. Các workload trao đổi qua địa chỉ IP riêng và được kiểm soát bằng route, Network Security Group (NSG), firewall hoặc các chính sách mạng phù hợp.

### 3.2. Virtual network gateway

**Virtual network gateway** thuộc loại **VPN** là tài nguyên Azure cung cấp chức năng thiết lập VPN vào VNet. Loại gateway, SKU và cấu hình quyết định các giao thức, thông lượng, số lượng kết nối và khả năng dự phòng.

Cần phân biệt **VPN gateway** với **ExpressRoute gateway**: ExpressRoute sử dụng kết nối riêng do nhà cung cấp dịch vụ cung cấp; VPN Gateway xây dựng đường hầm mã hóa qua Internet. Với bài học này, ta sử dụng gateway loại VPN.

### 3.3. GatewaySubnet

Azure VPN Gateway cần một subnet dành riêng có tên chính xác là **GatewaySubnet** trong VNet. Subnet này được Azure dùng để triển khai hạ tầng gateway; không đặt VM hoặc các workload ứng dụng vào đây.

Khi lập VNet mới, nên dự trù **GatewaySubnet có prefix /27 hoặc lớn hơn về số địa chỉ**, tùy loại gateway và nhu cầu mở rộng. Ví dụ, subnet /27 chứa nhiều địa chỉ hơn /28. Không nên tạo subnet quá nhỏ rồi phải sửa địa chỉ khi nâng cấp.

Tránh tùy tiện áp NSG hoặc user-defined route lên GatewaySubnet vì có thể gây lỗi cho gateway; phải tuân theo hướng dẫn hỗ trợ của Azure đối với SKU và mô hình triển khai cụ thể.

### 3.4. Public IP của VPN Gateway

Gateway dùng một hoặc nhiều **public IP address** làm điểm kết thúc VPN bên phía Azure. Endpoint công khai cần thiết cho quá trình thiết lập đường hầm qua Internet; nó không có nghĩa các VM trong VNet phải có public IP.

Chọn loại Public IP, SKU và vùng sẵn sàng theo yêu cầu của VPN Gateway hiện hành. Các triển khai mới thường dùng Standard Public IP theo những SKU gateway tương ứng. Một số mô hình active-active cần hai public IP riêng.

### 3.5. Local network gateway cho S2S

**Local network gateway (LNG)** là tài nguyên cấu hình trên Azure mô tả **đầu mạng bên ngoài Azure**, chẳng hạn:

- Public IP hoặc FQDN được hỗ trợ của thiết bị VPN tại văn phòng.
- Các dải địa chỉ IP thuộc mạng văn phòng cần định tuyến qua tunnel.
- Cấu hình BGP của đầu bên ngoài, nếu dùng định tuyến động.

LNG **không phải một máy ảo hoặc VPN appliance được Azure triển khai tại văn phòng**. Thiết bị VPN thật vẫn thuộc hệ thống tại chỗ và cần được cấu hình bởi đội mạng.

### 3.6. Connection

**Connection** là đối tượng liên kết Azure VPN Gateway với Local Network Gateway trong mô hình S2S và lưu các cài đặt cần thiết, chẳng hạn khóa chia sẻ trước. Trạng thái connection giúp kiểm tra đường hầm đã được thiết lập hay chưa.

Trong P2S, máy khách sử dụng cấu hình VPN client và phương thức xác thực đã cấu hình trên virtual network gateway; không cần tạo Local Network Gateway riêng cho từng laptop.

## 4. Kiến trúc tham chiếu dùng chung P2S và S2S

Giả sử tổ chức có ứng dụng chạy trong một Azure VNet, người dùng làm việc từ xa và chi nhánh có hệ thống nội bộ.

~~~mermaid
flowchart LR
    A[Laptop nhân viên P2S] -->|VPN mã hóa qua Internet| GW[Azure VPN Gateway]
    B[Mạng văn phòng 172.16.10.0/24] --> FW[Router hoặc Firewall VPN]
    FW -->|IPsec/IKE S2S qua Internet| GW
    subgraph AZ[Azure VNet 10.20.0.0/16]
        GW --> GS[GatewaySubnet]
        GS --> APP[Subnet ứng dụng 10.20.1.0/24]
        APP --> VM[VM hoặc dịch vụ dùng IP riêng]
    end
~~~

Sơ đồ biểu diễn luồng kết nối ở mức logic; gateway hoạt động với mạng Azure và không phải một router VM do người dùng tự đặt vào subnet ứng dụng. Các nhánh P2S và S2S đều có thể hướng đến workload được phép trong VNet.

Ví dụ kế hoạch địa chỉ:

| Thành phần | Dải địa chỉ mẫu | Mục đích |
|---|---|---|
| Azure VNet | 10.20.0.0/16 | Không gian mạng Azure |
| Subnet ứng dụng | 10.20.1.0/24 | VM và workload |
| GatewaySubnet | 10.20.255.0/27 | Dành riêng cho Azure VPN Gateway |
| Mạng văn phòng | 172.16.10.0/24 | Site tại chỗ kết nối bằng S2S |
| P2S client address pool | 172.20.10.0/24 | Cấp địa chỉ cho máy khách P2S |
| Public IP thiết bị văn phòng | 203.0.113.10 | Giá trị minh họa cho điểm VPN S2S |

**203.0.113.10** thuộc dải địa chỉ dành cho tài liệu ví dụ, không phải endpoint thật có thể dùng để thiết lập tunnel. Trong môi trường thực tế, thay bằng địa chỉ public của thiết bị VPN hoặc phương án định danh endpoint được Azure hỗ trợ.

Các dải riêng nêu trên là ví dụ. Bạn phải kiểm tra để các prefix **không chồng lấn**, bao gồm mạng Azure, văn phòng, chi nhánh khác, mạng máy khách và cả mạng LAN tại nơi người dùng kết nối. Nếu trùng dải, hệ điều hành hoặc router có thể chọn sai đường đi, kể cả khi VPN báo Connected.

## 5. Những quyết định cần chốt trước khi triển khai

### 5.1. Phạm vi truy cập

Liệt kê chính xác dịch vụ cần truy cập và từ đâu. Ví dụ:

- Laptop kỹ sư → VM quản trị trong subnet riêng.
- Mạng văn phòng → API nội bộ trong Azure.
- VNet Azure → máy chủ dữ liệu tại văn phòng, nếu cần lưu lượng hai chiều.

Không nên mở toàn bộ mạng chỉ vì VPN đã được mã hóa. Hãy cấu hình quyền người dùng, NSG, Azure Firewall và firewall trên hệ điều hành/workload theo đúng nhu cầu.

### 5.2. Quy hoạch địa chỉ

Lập bảng địa chỉ cho VNet, GatewaySubnet, các subnet đích, site tại chỗ, P2S pool và các mạng peered VNet. Kiểm tra cả những subnet sẽ xuất hiện trong tương lai. Việc xử lý trùng dải sau khi vận hành thường khó hơn nhiều so với chọn đúng từ đầu.

Nếu dải địa chỉ ở hai site đã chồng lấn, cần cân nhắc đánh lại IP hoặc cơ chế VPN NAT trên mô hình và SKU được hỗ trợ. Không mặc định VPN tự giải quyết được trùng địa chỉ.

### 5.3. Chọn gateway type, VPN type và SKU

Đối với hệ thống cần cả P2S lẫn S2S, thông thường nên chọn **VPN Gateway loại VPN, VPN type RouteBased**. Một số thiết bị hoặc tình huống S2S cũ dùng PolicyBased, nhưng loại này có giới hạn tính năng và không phải lựa chọn chung cho cả hai mô hình.

Chọn SKU gateway theo:

- Các giao thức và phương thức xác thực P2S được hỗ trợ.
- Số lượng kết nối P2S/S2S đồng thời cần thiết.
- Mức thông lượng ước tính và mô hình lưu lượng.
- Nhu cầu BGP, active-active, zone redundancy.
- Khả năng đáp ứng của region, các giới hạn và chi phí.

SKU và tính năng có thể thay đổi theo thời điểm. Hãy kiểm tra bảng **VPN Gateway SKU / feature support** chính thức trước khi chốt. Không suy luận mọi SKU đều hỗ trợ Entra ID authentication, OpenVPN, IKEv2, BGP hoặc active-active như nhau.

### 5.4. Khả năng kết nối tại văn phòng

Đối với S2S, router hoặc firewall tại văn phòng phải hỗ trợ bộ cấu hình IPsec/IKE tương thích với Azure. Đội mạng cần biết public IP của hai phía, prefix mạng, khóa chia sẻ, thuật toán và thông số IKE/IPsec, cũng như route trả về Azure.

Nếu thiết bị tại văn phòng nằm sau NAT, cần xác nhận thiết kế NAT traversal, public endpoint và khả năng thiết lập phiên từ cả hai phía. Kiểm tra đường Internet và firewall cho lưu lượng điều khiển VPN, thường liên quan đến UDP 500/4500 đối với IKE/IPsec NAT traversal, theo giao thức và cấu hình thực tế.

### 5.5. Danh tính và thiết bị P2S

Đối với P2S, cần chọn cơ chế xác thực theo yêu cầu:

- **Certificate authentication:** phát hành certificate hợp lệ và quản lý vòng đời khóa.
- **Microsoft Entra ID authentication:** trải nghiệm đăng nhập danh tính qua **OpenVPN** và Azure VPN Client trong những cấu hình được hỗ trợ.
- **RADIUS authentication:** dùng máy chủ RADIUS và luồng xác thực được thiết kế phù hợp.

Sự hỗ trợ phụ thuộc protocol, SKU, hệ điều hành và VPN client. Không thể chọn tùy ý một phương thức xác thực rồi dùng mọi loại client.

## 6. Tạo Azure VPN Gateway dùng chung

Các bước dưới đây mô tả quy trình bằng **Azure Portal**. Tên trường có thể thay đổi theo phiên bản giao diện.

1. Tạo một **Resource group** cho bài thực hành, ví dụ **rg-vpn-lab**, tại region đã chọn.
2. Tạo **VNet** với address space **10.20.0.0/16**.
3. Tạo subnet ứng dụng **10.20.1.0/24** và subnet đặc biệt tên **GatewaySubnet** có prefix **10.20.255.0/27**.
4. Tạo **Public IP** đáp ứng yêu cầu của SKU gateway.
5. Vào **Create a virtual network gateway**, chọn:
   - **Gateway type:** VPN.
   - **VPN type:** Route-based.
   - **SKU:** một SKU hỗ trợ đầy đủ P2S/S2S theo thiết kế đã xác nhận.
   - **Virtual network:** VNet vừa tạo.
   - **Public IP address:** Public IP dành cho gateway.
6. Xác nhận region, cấu hình zone/active-active nếu có và triển khai.
7. Đợi trạng thái tài nguyên cho biết gateway đã được cấp phát hoàn tất trước khi cấu hình kết nối.

Quá trình cấp phát VPN Gateway có thể kéo dài hơn đáng kể so với việc tạo một subnet hoặc NSG. Không nên kết luận lỗi chỉ vì thao tác chưa hoàn tất ngay. Trong môi trường thực tế, cần tính thời gian triển khai vào kế hoạch thay đổi và ước tính chi phí tài nguyên ngay cả khi tunnel chưa có lưu lượng.

**Quan trọng:** VPN Gateway phải nằm trong VNet mà bạn muốn kết nối, sử dụng GatewaySubnet của chính VNet đó. Tạo một Public IP thông thường hoặc chỉ bật VPN trong thiết lập của máy ảo không thay thế bước tạo virtual network gateway.

## 7. Thiết lập Site-to-Site VPN

S2S kết nối hai mạng qua một đường hầm IPsec/IKE. Ở phía Azure, bạn cần VPN Gateway, một Local Network Gateway mô tả site tại chỗ và một Connection; phía văn phòng cần thiết bị VPN hoạt động.

### 7.1. Tạo Local Network Gateway

Giả sử site tại chỗ có:

- Public IP: **203.0.113.10** (chỉ là mẫu, thay bằng IP thật).
- LAN: **172.16.10.0/24**.
- Thiết bị hỗ trợ IKE/IPsec tương thích Azure.

Trong Azure Portal, tạo **Local network gateway**:

1. Chọn resource group và tên, ví dụ **lng-branch**.
2. Nhập IP công khai hoặc FQDN nếu cấu hình đang dùng hỗ trợ.
3. Khai báo address space **172.16.10.0/24** của mạng bên ngoài.
4. Nếu thiết kế dùng BGP, cung cấp thông tin BGP peer theo yêu cầu.
5. Lưu rồi kiểm tra lại IP và prefix.

Address prefixes của Local Network Gateway dùng để định tuyến đến các mạng ở phía bên ngoài Azure khi sử dụng mô hình prefix tĩnh. Khai báo sai có thể dẫn đến VPN báo kết nối nhưng lưu lượng không tới đúng mạng đích.

### 7.2. Tạo Connection

Trong Azure Portal:

1. Mở VPN Gateway vừa tạo rồi vào mục **Connections**.
2. Thêm connection mới với loại **Site-to-site (IPsec)**.
3. Chọn **Virtual network gateway** và **Local network gateway** tương ứng.
4. Thiết lập **shared key (PSK)** có độ mạnh phù hợp.
5. Nếu dùng BGP hoặc IPsec/IKE policy tùy chỉnh, nhập tham số phù hợp với cả hai phía.
6. Tạo connection và kiểm tra trạng thái.

**Không đặt PSK thật vào repository, tài liệu chia sẻ công khai hoặc command history.** Hãy lưu và trao đổi bí mật qua cơ chế quản lý bí mật của tổ chức; ví dụ có thể dùng Azure Key Vault và quy trình phân quyền thích hợp. Hai thiết bị đầu cuối phải dùng cùng PSK theo cấu hình kết nối.

### 7.3. Cấu hình thiết bị VPN tại văn phòng

Trên router/firewall của site, đội mạng cần cấu hình tương ứng:

- Remote peer: public IP của Azure VPN Gateway.
- Local peer: public IP/NAT endpoint của site.
- IKE/IPsec parameters tương thích; lựa chọn cụ thể theo thiết bị và cấu hình được Azure hỗ trợ.
- PSK trùng với connection trong Azure.
- Local network: 172.16.10.0/24.
- Remote network: 10.20.0.0/16 hoặc các prefix cụ thể được thiết kế.
- Route và các quy tắc firewall cho lưu lượng hai chiều.

Tùy thiết bị, mô hình policy-based IPsec tại chỗ có thể yêu cầu traffic selector hoặc crypto ACL đặc thù ngay cả khi Azure Gateway là RouteBased. Cần xác nhận khả năng tương tác giữa hai phía, thay vì dựa vào tên gọi trên giao diện của thiết bị.

### 7.4. Kiểm tra S2S

Sau khi tạo tunnel:

1. Xem connection status trên Azure và trạng thái IKE/IPsec SA ở router.
2. Từ máy trong mạng văn phòng, kiểm tra kết nối đến IP riêng của workload Azure ở cổng dịch vụ được phép.
3. Nếu cần lưu lượng từ Azure về văn phòng, kiểm tra chiều ngược lại.
4. Xác nhận NSG, firewall, hệ điều hành và các route không chặn lưu lượng.
5. Kiểm tra DNS nếu sử dụng tên máy hoặc tên miền nội bộ.
6. Ghi lại trạng thái và bằng chứng từ cả hai đầu tunnel.

**Connected không bảo đảm ứng dụng truy cập được.** Nó chỉ cho biết kết nối VPN có thể đã được thiết lập; route, return path và các bộ lọc bảo mật vẫn có thể sai.

## 8. Thiết lập Point-to-Site VPN

P2S cho phép từng máy khách tạo phiên VPN vào Azure. Azure VPN Gateway cấp cho mỗi client một địa chỉ từ **P2S address pool**. Client dùng profile kết nối phù hợp và phải vượt qua cơ chế xác thực được cấu hình.

### 8.1. Cấu hình chung cho P2S

Trong Azure Portal:

1. Mở virtual network gateway đã cấp phát.
2. Chọn phần **Point-to-site configuration**.
3. Cấu hình **Address pool** khác với các prefix VNet, site tại chỗ và mạng client, ví dụ **172.20.10.0/24**.
4. Chọn **Tunnel type / protocol** được SKU và client hỗ trợ.
5. Chọn phương thức **Authentication type** phù hợp.
6. Nhập các thông tin chứng chỉ, Microsoft Entra ID hoặc RADIUS tùy lựa chọn.
7. Lưu cấu hình rồi tải client profile/package thích hợp.
8. Cài đặt/cấu hình VPN client trên máy được phép và thử kết nối.

Các phương thức bên dưới được giải thích riêng vì thao tác thiết lập không giống nhau.

### 8.2. Xác thực bằng chứng chỉ

Cơ chế chứng chỉ thường dùng khi bạn muốn kiểm soát thiết bị hoặc người dùng thông qua hạ tầng chứng chỉ do tổ chức quản lý:

1. Chuẩn bị chứng chỉ gốc (root certificate) phù hợp để tin cậy trên Azure Gateway.
2. Tải **phần chứng chỉ công khai** của root certificate lên cấu hình P2S theo định dạng được yêu cầu; không tải khóa riêng của root CA lên Portal.
3. Phát hành client certificate được ký bởi root hợp lệ cho thiết bị/người dùng.
4. Cài client certificate cùng khóa riêng của chính client vào kho chứng chỉ của hệ điều hành phù hợp.
5. Tải VPN client configuration package và thiết lập kết nối.
6. Xác minh có thể kết nối, rồi kiểm tra luồng thu hồi chứng chỉ theo quy trình tổ chức khi người dùng hoặc thiết bị không còn hợp lệ.

**Không phát tán root CA private key.** Nếu khóa cấp phát bị lộ, khả năng mạo danh client có thể tăng mạnh. Một bài thực hành đơn giản có thể dùng chứng chỉ thử nghiệm; môi trường thực tế cần quy trình quản lý khóa, vòng đời và thu hồi chứng chỉ.

### 8.3. Xác thực bằng Microsoft Entra ID

Với kịch bản người dùng đăng nhập bằng danh tính tổ chức, Azure VPN Gateway có thể hỗ trợ **Microsoft Entra ID authentication qua OpenVPN** kết hợp **Azure VPN Client**, tùy SKU, hệ điều hành và yêu cầu cấu hình hiện hành.

Quy trình:

1. Xác nhận VPN Gateway/SKU, giao thức OpenVPN và client platform được hỗ trợ.
2. Chọn Microsoft Entra ID làm phương thức xác thực P2S.
3. Cấu hình tenant, audience và issuer theo chỉ dẫn hiện hành của Azure cho tenant của tổ chức; không tự suy đoán các URI hoặc app ID.
4. Cấu hình kiểm soát danh tính phù hợp, bao gồm Conditional Access nếu thuộc phạm vi hỗ trợ và chính sách tổ chức.
5. Tải cấu hình Azure VPN Client từ Azure Portal, import profile trên máy.
6. Chọn kết nối và đăng nhập bằng danh tính được phép.
7. Xác minh máy nhận địa chỉ P2S, có route đến VNet và kết nối thành công đến workload được cho phép.

Mô hình này thường phù hợp với đội nhân viên dùng tài khoản Microsoft Entra ID, nhưng không nên cho rằng việc đăng nhập Entra ID tự động mang lại quyền truy cập mọi ứng dụng trong VNet. Quyền ở tầng mạng và tầng ứng dụng vẫn cần cấu hình riêng.

### 8.4. Xác thực bằng RADIUS

Nếu tổ chức có hạ tầng RADIUS, Azure VPN Gateway có thể được cấu hình gửi yêu cầu xác thực đến máy chủ RADIUS theo giao thức và kiểu kết nối được hỗ trợ. Cần bảo đảm đường mạng từ gateway tới RADIUS server, cấu hình shared secret của RADIUS và khả năng truy cập/dự phòng của hệ thống xác thực.

RADIUS có thể tích hợp với phương án xác thực nội bộ của doanh nghiệp; tuy nhiên, không nên chọn chỉ vì hệ thống đã có RADIUS. Hãy đánh giá hỗ trợ của client, giao thức VPN, khả năng sẵn sàng và yêu cầu an ninh.

## 9. Phân phối VPN client profile và kiểm soát thiết bị

Sau khi cấu hình P2S, **VPN client configuration** cung cấp thông tin kết nối như gateway endpoint, tunnel settings và route tùy phương thức xác thực. Cách tải và import có thể khác giữa Azure VPN Client và client tích hợp sẵn của hệ điều hành.

Trước khi đưa vào sử dụng:

- Chỉ phân phối cấu hình cho thiết bị hoặc người dùng được phép.
- Không gửi kèm private key và mật khẩu qua kênh không an toàn.
- Kiểm tra tương thích phiên bản client với phương thức xác thực.
- Cập nhật cấu hình client nếu thay đổi prefix VNet, mạng peered, địa chỉ hoặc cài đặt gateway mà loại client yêu cầu tải lại profile.
- Thiết lập DNS nội bộ hoặc cơ chế phân giải tên thích hợp nếu workload dùng private endpoint/private DNS.
- Hướng dẫn người dùng ngắt VPN khi kết thúc công việc và báo cáo thiết bị bị mất.

Không nên dựa vào nút **Connected** trên VPN client làm kết quả kiểm thử cuối cùng. Client phải nhận IP, có route phù hợp và truy cập được đúng ứng dụng đích.

## 10. Định tuyến hai chiều và nguyên nhân VPN nối được nhưng không truyền dữ liệu

Một đường hầm VPN được thiết lập chỉ giải quyết phần **đường đi được mã hóa**. Gói dữ liệu vẫn phải được định tuyến đến đích và gói trả lời phải tìm được đường quay lại.

### 10.1. Đường đi S2S

Ví dụ máy văn phòng **172.16.10.25** muốn kết nối VM Azure **10.20.1.10**:

1. Máy văn phòng gửi gói tin đến gateway nội bộ của LAN.
2. Router tại site nhận thấy **10.20.0.0/16** thuộc mạng ở đầu bên kia S2S và gửi qua IPsec tunnel.
3. Azure VPN Gateway đưa lưu lượng vào VNet.
4. NSG, firewall và hệ điều hành của VM cho phép hay từ chối cổng dịch vụ.
5. VM gửi gói phản hồi đến **172.16.10.25**; Azure phải có route quay lại site qua VPN Gateway.

Nếu đường về thiếu, truy cập có thể thất bại dù gói chiều đi đến được VM. Tương tự, nếu thiết bị tại site không có route tới VNet, tunnel vẫn có thể báo Connected nhưng không có lưu lượng hữu ích.

### 10.2. Đường đi P2S

Ví dụ laptop nhận địa chỉ **172.20.10.5** từ pool P2S:

1. VPN client thêm các route phù hợp với cấu hình đã nhận.
2. Lưu lượng đi đến IP riêng trong VNet được gửi qua tunnel.
3. Azure VPN Gateway đưa lưu lượng tới subnet đích.
4. Workload trả lời về địa chỉ client qua đường định tuyến của hệ thống.

**Split tunneling** thường chỉ đưa lưu lượng đến các prefix được công bố qua VPN; lưu lượng Internet thông thường vẫn dùng đường Internet của máy khách. Mô hình **forced tunneling** hoặc các tuyến tùy chỉnh cần cấu hình riêng và phụ thuộc VPN protocol/client. Không tự giả định mọi profile P2S đều đẩy toàn bộ Internet traffic vào Azure.

### 10.3. DNS là một bước riêng

Một ứng dụng có thể truy cập được bằng IP **10.20.1.10** nhưng thất bại khi gọi **api.internal.example** vì máy client không dùng đúng DNS server hoặc không có khả năng phân giải private DNS zone.

Cần thiết kế DNS cho cả P2S và S2S, ví dụ Azure DNS Private Resolver, DNS server trong Azure hay hệ thống DNS tại chỗ được phép. Thiết lập DNS không tự phát sinh chỉ vì đã có đường hầm.

### 10.4. NSG, firewall và route

Chỉ mở các luồng cần thiết:

- NSG tại subnet/VM đích cho phép nguồn P2S pool hoặc LAN on-prem tương ứng.
- Azure Firewall/NVA (nếu sử dụng) có rule và route thích hợp.
- Firewall của máy ảo cho phép cổng ứng dụng.
- Router/firewall on-prem cho phép cả chiều đi và chiều về.
- UDR không vô tình chuyển lưu lượng trả lời sang một next hop không phù hợp.

Nếu chỉ dùng ICMP ping, hãy nhớ một số hệ điều hành và firewall mặc định chặn ICMP. Hãy kiểm thử bằng **cổng TCP/UDP mà ứng dụng thực tế sử dụng** kết hợp kiểm tra route và log.

## 11. BGP và định tuyến tĩnh trên S2S

Với một chi nhánh nhỏ, danh sách prefix được nhập trên Local Network Gateway có thể đủ. Khi có nhiều site, nhiều dải mạng hoặc yêu cầu thay đổi route thường xuyên, doanh nghiệp có thể cân nhắc **Border Gateway Protocol (BGP)**.

**Định tuyến tĩnh:**

- Các prefix mạng tại site được khai báo thủ công.
- Dễ hiểu với topology nhỏ.
- Cần cập nhật cấu hình khi mạng tại site thay đổi.

**BGP:**

- Azure VPN Gateway và thiết bị tại chỗ có thể trao đổi thông tin định tuyến động nếu gateway SKU và thiết bị hỗ trợ.
- Cần cấu hình ASN, địa chỉ BGP peer và tham số kết nối tương thích.
- Giúp quản lý sự thay đổi prefix và một số kịch bản đa site/phục hồi.
- Không thay thế thiết kế tránh trùng prefix hoặc kiểm soát bảo mật.

Ví dụ, nếu văn phòng bổ sung mạng **172.16.20.0/24**, cấu hình tĩnh yêu cầu cập nhật các prefix liên quan; BGP có thể quảng bá tuyến theo thiết kế. Tuy nhiên, BGP quảng bá sai hoặc quá rộng cũng có thể gây mất kết nối diện rộng. Kiểm tra tuyến đã học và giới hạn quảng bá là phần quan trọng của quá trình vận hành.

## 12. Kết hợp P2S, S2S và VNet peering

Một tổ chức có thể sử dụng một VNet trung tâm (hub) chứa Azure VPN Gateway, còn các VNet ứng dụng khác là spoke. Khi đó cần hiểu:

- P2S và S2S cùng đi vào hub gateway chỉ khi SKU và giao thức cho phép cấu hình đồng thời.
- **VNet peering** không mặc nhiên chuyển tiếp mọi kết nối xuyên spoke hoặc tới mạng on-prem.
- Một số thiết kế dùng **gateway transit** qua peering; phải cấu hình đúng các tùy chọn ở hai phía và kiểm tra điều kiện sử dụng remote gateway.
- Nếu P2S client cần truy cập cả on-prem thông qua S2S, phải xác minh route tới mạng on-prem, đường trả về **P2S address pool**, khả năng hỗ trợ của gateway và firewall ở site.
- Thay đổi mạng peered hoặc prefix có thể đòi hỏi cập nhật/thử lại profile P2S để client nhận các route mới.

Không nên mô tả hub-spoke hoặc P2S-to-S2S transit như chức năng tự động. Đây là thiết kế mạng có điều kiện về định tuyến, peering, gateway và khả năng hỗ trợ của dịch vụ.

## 13. Cấu hình S2S ban đầu bằng Azure CLI

Azure CLI có thể hỗ trợ triển khai hạ tầng theo cách lặp lại. Ví dụ dưới đây dùng **bash** và các prefix trong bài học; chỉ chạy trong môi trường thử nghiệm được phép. Các giá trị như public IP văn phòng, PSK và SKU cần được thay bằng giá trị được phê duyệt.

### 13.1. Tạo resource group, VNet và GatewaySubnet

~~~bash
az login
az account set --subscription "<subscription-id>"

az group create \
  --name rg-vpn-lab \
  --location southeastasia

az network vnet create \
  --resource-group rg-vpn-lab \
  --name vnet-vpn-lab \
  --location southeastasia \
  --address-prefixes 10.20.0.0/16 \
  --subnet-name snet-app \
  --subnet-prefixes 10.20.1.0/24

az network vnet subnet create \
  --resource-group rg-vpn-lab \
  --vnet-name vnet-vpn-lab \
  --name GatewaySubnet \
  --address-prefixes 10.20.255.0/27
~~~

### 13.2. Tạo Public IP và VPN Gateway

~~~bash
az network public-ip create \
  --resource-group rg-vpn-lab \
  --name pip-vpn-gateway \
  --location southeastasia \
  --sku Standard \
  --allocation-method Static

az network vnet-gateway create \
  --resource-group rg-vpn-lab \
  --name vng-vpn-lab \
  --location southeastasia \
  --public-ip-addresses pip-vpn-gateway \
  --vnet vnet-vpn-lab \
  --gateway-type Vpn \
  --vpn-type RouteBased \
  --sku VpnGw1
~~~

**VpnGw1** là SKU mang tính minh họa; khả năng cung cấp, phiên bản SKU và sự phù hợp với P2S/S2S hoặc tính năng yêu cầu phải được kiểm tra trước khi chạy. Nếu cần zone-redundant hoặc active-active, thiết kế resource/Public IP và tham số có thể khác ví dụ này.

### 13.3. Khai báo site tại chỗ

~~~bash
az network local-gateway create \
  --resource-group rg-vpn-lab \
  --name lng-branch \
  --location southeastasia \
  --gateway-ip-address 203.0.113.10 \
  --local-address-prefixes 172.16.10.0/24
~~~

**Không thể dùng 203.0.113.10 làm VPN peer thật**: đây là IP ví dụ. Chỉ sau khi thay bằng endpoint site thật, cấu hình router và khóa chia sẻ mới có thể tạo một tunnel S2S hoạt động.

### 13.4. Tạo connection và xem trạng thái

Lệnh sau minh họa các tham số cơ bản. Trong production, không nên truyền PSK bí mật trực tiếp trên dòng lệnh vì có thể lưu trong history hoặc log; hãy dùng phương án quản lý bí mật và quy trình triển khai được tổ chức chấp thuận.

~~~bash
az network vpn-connection create \
  --resource-group rg-vpn-lab \
  --name conn-branch \
  --location southeastasia \
  --vnet-gateway1 vng-vpn-lab \
  --local-gateway2 lng-branch \
  --shared-key "<lab-only-shared-key>"

az network vpn-connection show \
  --resource-group rg-vpn-lab \
  --name conn-branch \
  --query "{name:name,status:connectionStatus}" \
  --output json
~~~

Đây là kịch bản dùng prefix tĩnh và không cấu hình BGP. Nếu cần BGP hoặc IPsec/IKE policy riêng, hãy áp dụng tham số phù hợp với phiên bản CLI và thiết bị VPN thực tế.

Không đưa lệnh xóa cả resource group vào pipeline production; sau bài lab, chỉ dọn những tài nguyên thử nghiệm đã được kiểm kê và cho phép xóa.

## 14. Bảo mật VPN Gateway trong vận hành

Dù lưu lượng VPN được mã hóa, bảo mật toàn hệ thống vẫn phụ thuộc nhiều lớp:

**Xác thực:**

- P2S nên dùng phương thức xác thực phù hợp, quản lý MFA/Conditional Access khi được hỗ trợ.
- Certificate phải được phát hành, lưu giữ và thu hồi theo quy trình.
- S2S PSK cần đủ mạnh, được quản lý như bí mật và luân chuyển có kiểm soát.

**Phân vùng mạng:**

- Không cấp truy cập rộng hơn những dịch vụ người dùng/site cần.
- Sử dụng NSG, Azure Firewall, firewall host và quy tắc ứng dụng để giới hạn nguồn/cổng.
- Phân tách môi trường thử nghiệm và production nếu yêu cầu rủi ro khác nhau.

**Quản trị Azure:**

- Dùng Azure RBAC để hạn chế người có thể thay đổi gateway, connection, VPN client authentication và resource group.
- Bảo vệ các tài khoản quản trị bằng Microsoft Entra ID, MFA và cơ chế đặc quyền có thời hạn như PIM khi phù hợp.
- Ghi nhận thay đổi gateway, tunnel và cấu hình mạng bằng Azure Activity Log, diagnostic logs và quy trình change management.

**Vận hành thiết bị:**

- Kiểm tra bản vá firmware và cấu hình IKE/IPsec của firewall on-prem.
- Bảo vệ private key và cấu hình client; thu hồi quyền đối với thiết bị bị mất.
- Không coi VPN là thay thế cho authorization trong ứng dụng và dịch vụ dữ liệu.

## 15. Khả dụng cao và phục hồi sự cố

### 15.1. Dự phòng gateway trong một region

Azure VPN Gateway là dịch vụ được quản lý và có cơ chế dự phòng tùy SKU/cấu hình. Một số mô hình hỗ trợ **active-active**, trong đó các gateway instance có public IP riêng và site tại chỗ thiết lập nhiều tunnel để tăng khả năng duy trì kết nối.

Để mô hình active-active thực sự đem lại lợi ích, thiết bị on-prem phải hỗ trợ và được cấu hình tương ứng cho các tunnel. Chỉ tạo thêm một public IP mà không cấu hình đầu bên kia sẽ không tạo đường dự phòng hoàn chỉnh.

Một số gateway SKU và region hỗ trợ triển khai có tính sẵn sàng theo availability zone. Tính năng này phụ thuộc loại SKU và thiết kế Public IP/GatewaySubnet; kiểm tra tài liệu sản phẩm trước khi chọn.

### 15.2. Đường Internet và thiết bị tại chỗ

Nếu chi nhánh chỉ có một đường Internet và một firewall, site vẫn có điểm lỗi đơn dù Azure có nhiều instance VPN. Để tăng khả dụng đầu cuối, có thể cần hai kết nối Internet, thiết bị VPN dự phòng hoặc nhiều tunnel/route theo thiết kế được hỗ trợ.

### 15.3. Sự cố toàn region

Dự phòng trong cùng region không đồng nghĩa khả năng hoạt động khi cả region gặp sự cố. Hệ thống quan trọng có thể cần VNet và gateway ở region thứ hai, dữ liệu và ứng dụng dự phòng, cùng quy trình chuyển tuyến được kiểm thử. Thiết kế này làm tăng chi phí và độ phức tạp.

Cần đặt rõ **RTO** (thời gian khôi phục mục tiêu) và **RPO** (mức mất dữ liệu tối đa có thể chấp nhận) cho toàn ứng dụng. VPN chỉ là một thành phần của phương án DR; đường hầm kết nối không tự sao chép cơ sở dữ liệu hoặc khởi chạy dịch vụ dự phòng.

## 16. Giám sát, chẩn đoán và cảnh báo

Những chỉ dấu nên theo dõi:

| Nhóm dữ liệu | Điều cần kiểm tra |
|---|---|
| Connection status | S2S tunnel đang Connected hay Disconnected; lịch sử thay đổi |
| Gateway và tunnel metrics | Lưu lượng ingress/egress, trạng thái và các số liệu kết nối được SKU cung cấp |
| Diagnostic logs | Thông tin thương lượng IKE/IPsec, tunnel, route hoặc sự kiện gateway theo danh mục hỗ trợ |
| Azure Activity Log | Ai thay đổi gateway, connection, public IP hoặc tài nguyên liên quan |
| BGP routes/status | Prefix đã học/quảng bá, trạng thái phiên BGP nếu sử dụng |
| Client/endpoint logs | Lỗi xác thực, import profile, DNS hoặc route của P2S client |
| Thiết bị on-prem | IKE SA, IPsec SA, packet counters, route và firewall drop |

Azure Monitor có thể thu thập metrics và diagnostic logs theo cấu hình. Một số loại log yêu cầu tạo **diagnostic settings** để gửi tới Log Analytics workspace, Storage hoặc đích phù hợp. Danh mục log/metric có thể khác theo gateway và phiên bản dịch vụ.

Cảnh báo hữu ích gồm: tunnel bị ngắt quá ngưỡng, lưu lượng tụt bất thường, số lần xác thực thất bại tăng hoặc thay đổi cấu hình gateway ngoài cửa sổ bảo trì. Cần điều chỉnh ngưỡng theo mô hình vận hành và tránh mặc định rằng mọi lần P2S client ngắt kết nối đều là sự cố nghiêm trọng.

## 17. Hướng dẫn xử lý lỗi S2S

### 17.1. Tunnel chưa Connected

Kiểm tra theo thứ tự:

1. Azure VPN Gateway đã Provisioning Succeeded chưa?
2. Public IP của Azure gateway và site on-prem có đúng không?
3. Đường Internet và firewall có cho phép lưu lượng IKE/IPsec theo thiết kế không?
4. Hai phía có dùng cùng PSK và cấu hình IKE/IPsec tương thích không?
5. Thiết bị tại site có đúng chế độ route/traffic selector hoặc peer config không?
6. Có lỗi thương lượng trong VPN Gateway diagnostic logs hoặc log thiết bị tại chỗ không?

Nếu hai phía sai PSK hoặc tham số IKE, lưu lượng chưa vào được đường hầm. Khi đó thay đổi NSG của workload không giải quyết lỗi thiết lập tunnel.

### 17.2. Tunnel Connected nhưng ứng dụng không truy cập được

Kiểm tra:

- Local Network Gateway đã khai báo đúng prefix on-prem?
- Router on-prem đã có route đến prefix VNet?
- VNet/subnet có route trả về on-prem?
- Có mạng trùng prefix hoặc route ưu tiên đi đường khác?
- NSG, firewall trung gian và host firewall cho phép cổng ứng dụng?
- DNS có phân giải tên dịch vụ thành đúng IP riêng?
- Có NAT hoặc traffic selector không tương thích?
- Khi dùng BGP, tuyến có thực sự được quảng bá và học đúng không?

Phân biệt kiểm tra **bằng IP** và **bằng tên DNS**. Một kiểm tra ICMP thất bại không đủ khẳng định đường mạng hỏng vì ping có thể bị chặn có chủ đích.

### 17.3. Tunnel chập chờn hoặc chậm

Xem thông lượng gateway so với SKU, chất lượng đường truyền Internet, MTU/MSS, packet loss, độ trễ, thay đổi IKE SA và giới hạn của firewall. Kiểm tra kết quả từ hai đầu theo cùng khoảng thời gian trước khi kết luận nghẽn nằm trong Azure.

## 18. Hướng dẫn xử lý lỗi P2S

**Không kết nối được VPN:** kiểm tra profile, endpoint, phiên bản VPN client, giao thức, chứng chỉ hoặc Entra ID/RADIUS authentication, quyền người dùng và mạng cục bộ có chặn giao thức không.

**Client báo authentication failed:** xác minh certificate còn hiệu lực và có private key tương ứng; hoặc xem tenant/audience/issuer và điều kiện Microsoft Entra ID nếu sử dụng. Với RADIUS, kiểm tra máy chủ, shared secret, chính sách chấp nhận và kết nối mạng.

**Connected nhưng không có route đến VNet:** kiểm tra P2S address pool, bảng route trên máy, route được profile công bố, trùng địa chỉ IP và việc profile có được tải lại sau khi đổi cấu hình VNet hay không.

**Truy cập được IP nhưng không truy cập được tên:** kiểm tra DNS được cấp cho client và đường mạng tới DNS server hoặc private resolver.

**Không truy cập được hệ thống tại văn phòng qua S2S:** kiểm tra đây có phải một kịch bản transit được hỗ trợ không, cả chiều P2S → on-prem và đường trả về đến P2S pool, firewall và route của on-prem.

**Chỉ một số người dùng gặp lỗi:** so sánh phiên bản client, chính sách xác thực, tình trạng chứng chỉ, địa chỉ mạng LAN tại nơi họ kết nối và bảng route của từng thiết bị.

Một bảng điều tra ngắn:

| Triệu chứng | Cần kiểm tra trước | Bằng chứng hữu ích |
|---|---|---|
| Authentication failed | Danh tính, certificate, Entra ID/RADIUS | VPN client log, sự kiện xác thực |
| Không nhận IP P2S | Gateway P2S config, client profile | Cấu hình pool, client status |
| Không tới được VM | Route, NSG/firewall, IP đích | Route table, flow log/host log, TCP test |
| Chỉ lỗi phân giải tên | DNS nội bộ và client DNS | nslookup/dig với DNS server cụ thể |
| Có lúc mất kết nối | Mạng máy khách, gateway và protocol | Timestamp, gateway metrics, client log |

## 19. Hiểu chi phí và giới hạn kỹ thuật

VPN Gateway không phải kết nối VPN miễn phí chỉ vì chưa có người dùng truy cập. Hóa đơn có thể gồm:

- Chi phí cấp phát/chạy gateway theo SKU và thời gian sử dụng.
- Truyền dữ liệu theo cấu trúc giá áp dụng cho VPN và Azure.
- Tài nguyên liên quan như Public IP, Log Analytics và lưu trữ log.
- Hạ tầng router/firewall, đường Internet và vận hành tại site.
- Chi phí các gateway và kết nối dự phòng nếu mở rộng đa region hoặc active-active.

Lựa chọn SKU nên dựa trên số người dùng P2S đồng thời, số tunnel S2S, lưu lượng dự kiến, giao thức và yêu cầu dự phòng. Thông lượng công bố của SKU là thông số tham chiếu; hiệu năng thực tế còn chịu ảnh hưởng giao thức, kích thước gói, chất lượng Internet và thiết bị tại chỗ.

Trước khi thực hành, đặt ngân sách cảnh báo trong Azure Cost Management và biết cách dọn tài nguyên lab. Chỉ dọn các tài nguyên được phép xóa; việc xóa VPN Gateway hay GatewaySubnet trong môi trường đang hoạt động có thể ngắt kết nối của nhiều ứng dụng.

## 20. Bài thực hành tích hợp

**Bối cảnh:** đội vận hành cần cho phép một laptop kết nối đến một VM dùng IP riêng, đồng thời tạo kết nối S2S thử nghiệm đến một firewall tương thích trong phòng lab.

**Điều kiện:** có Azure subscription được phép tạo VPN Gateway, chi phí được phê duyệt, VNet chưa có gateway xung đột, một thiết bị VPN on-prem có public endpoint thật và quyền cấu hình ở cả hai phía.

### Phần A — Thiết kế

1. Vẽ topology gồm laptop P2S, Azure VPN Gateway, mạng phòng lab và VM riêng.
2. Chọn các prefix không chồng lấn. Dùng bảng địa chỉ ở mục 4 làm mẫu.
3. Chọn SKU RouteBased có thể hỗ trợ phương thức xác thực P2S và kết nối S2S dự kiến.
4. Xác định cổng ứng dụng được phép truy cập và các rule NSG/firewall cần thiết.

### Phần B — Triển khai S2S

1. Tạo VNet, GatewaySubnet và VPN Gateway.
2. Khai báo Local Network Gateway với endpoint IP thật của site và prefix LAN thật.
3. Tạo VPN connection, lưu PSK ở nơi an toàn.
4. Cấu hình router/firewall tại site theo IPsec/IKE được hỗ trợ.
5. Xác minh tunnel Connected.
6. Dùng một TCP connection được cho phép để xác minh gói đi và gói trả về giữa site và VM Azure.

### Phần C — Triển khai P2S

1. Đặt P2S client pool không trùng mạng khác.
2. Chọn certificate hoặc Entra ID theo khả năng hỗ trợ của SKU/client và chính sách lab.
3. Cấu hình xác thực, tải và import profile.
4. Kết nối từ laptop, kiểm tra địa chỉ được cấp.
5. Xem route và thử kết nối tới VM qua IP riêng.
6. Thử tên DNS nội bộ; nếu thất bại, bổ sung đúng cấu hình DNS rồi kiểm tra lại.

### Phần D — Kiểm chứng và dọn dẹp

1. Lưu lại hai kết quả: trạng thái tunnel S2S và trạng thái P2S client.
2. Ghi kết quả kiểm tra route, DNS, port và các log cần thiết.
3. Tắt hoặc ngắt phiên P2S thử nghiệm.
4. Dọn các tài nguyên thử nghiệm không còn cần và theo dõi Cost Management.
5. Viết báo cáo ngắn mô tả lý do P2S và S2S dùng các đầu kết nối và cơ chế xác thực khác nhau.

**Nếu chưa có thiết bị VPN tại chỗ**, bạn vẫn có thể thực hành P2S hoặc hoàn thành phần thiết kế S2S và mô tả cấu hình router yêu cầu. Không nên giả lập việc S2S Connected khi chưa có site thực và thiết bị tương thích.

## 21. Những sai lầm thường gặp

- **Dùng mạng trùng prefix:** VNet, LAN hoặc P2S pool chồng lấn gây lỗi định tuyến khó phát hiện.
- **Không tạo GatewaySubnet đúng tên:** Azure VPN Gateway cần subnet dành riêng với tên chính xác.
- **Chọn SKU theo giá mà bỏ qua giao thức:** một số phương thức P2S hoặc tính năng HA/BGP chỉ có ở cấu hình/SKU phù hợp.
- **Nhầm Local Network Gateway là VPN endpoint do Azure triển khai:** LNG chỉ mô tả site đối tác.
- **Chỉ cấu hình đầu Azure trong S2S:** thiết bị văn phòng phải có cấu hình khớp và route đúng.
- **Chọn protocol P2S không khớp client:** cách xác thực certificate, Entra ID, RADIUS và client cần đồng bộ.
- **Cho rằng Connected đồng nghĩa thông ứng dụng:** vẫn phải kiểm tra NSG, firewall, DNS và tuyến về.
- **Không cập nhật profile sau đổi mạng:** máy P2S có thể tiếp tục dùng route hoặc thông tin cũ.
- **Bỏ quên PSK và certificate:** lộ hoặc hết hạn thông tin xác thực làm tăng rủi ro hoặc ngắt kết nối.
- **Không dự trù chi phí gateway:** tài nguyên có thể phát sinh phí khi chưa có lưu lượng.
- **Đánh giá HA chỉ ở Azure:** đường Internet và router của site cũng có thể là điểm lỗi đơn.

## 22. Câu hỏi tự kiểm tra

1. Vì sao mô hình P2S thích hợp cho một kỹ sư làm việc từ xa, còn S2S thích hợp hơn để nối toàn bộ mạng văn phòng?
2. GatewaySubnet khác subnet ứng dụng ở điểm nào?
3. Local Network Gateway giữ thông tin gì và nó có phải thiết bị VPN thật không?
4. Nếu Azure và văn phòng dùng cùng dải 10.20.0.0/16, bạn cần xử lý vấn đề nào trước khi tạo tunnel?
5. Một S2S connection đã Connected nhưng VM không trả lời yêu cầu TCP. Bạn sẽ kiểm tra route, NSG và firewall theo thứ tự nào?
6. Tại sao P2S client có thể truy cập VM bằng IP nhưng thất bại qua private DNS name?
7. P2S xác thực bằng Microsoft Entra ID có thể dùng tùy ý mọi protocol và client không?
8. Khi mở rộng từ một chi nhánh sang nhiều chi nhánh, BGP và mô hình HA có thể hỗ trợ những vấn đề gì?
9. Tại sao một gateway trong Azure vẫn không bảo đảm khả dụng khi site chỉ có một router và một đường Internet?
10. Khi dùng cùng VPN Gateway cho P2S và S2S, làm sao kiểm tra một laptop P2S có thể truy cập mạng on-prem qua đường S2S?

## 23. Ghi nhớ

**Point-to-Site** tạo đường hầm từ từng thiết bị người dùng vào Azure VNet; **Site-to-Site** nối mạng tại chỗ với Azure qua thiết bị VPN và IPsec/IKE. Cả hai đều dựa trên việc chọn đúng Azure VPN Gateway, thiết kế các dải IP không chồng lấn và cấu hình định tuyến hai chiều.

Đối với P2S, hãy chú trọng phương thức xác thực, protocol/client, address pool, profile và DNS. Đối với S2S, hãy chú trọng Local Network Gateway, public endpoint, PSK/IKE, prefix tại chỗ và thiết bị router/firewall đối tác. Khi vận hành, cần theo dõi kết nối, log, route, kiểm soát truy cập và chi phí; nếu VPN báo Connected nhưng ứng dụng không hoạt động, hãy kiểm tra toàn bộ đường đi đến dịch vụ và chiều trả lời trước khi thay đổi cấu hình ngẫu nhiên.
