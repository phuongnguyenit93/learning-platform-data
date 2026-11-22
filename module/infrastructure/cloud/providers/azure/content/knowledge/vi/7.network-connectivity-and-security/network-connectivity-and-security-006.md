# Azure Firewall và quản lý firewall policy

Trong module **CLOUD_PROVIDERS_AZURE**, người học khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Mục tiêu là triển khai, giám sát, bảo vệ và kiểm soát chi phí cho một kiến trúc ứng dụng trên Azure. Ở chương **Kết nối và bảo vệ mạng**, **Azure Firewall** cung cấp điểm kiểm soát lưu lượng tập trung, còn **Firewall Policy** giúp quản lý bộ luật bảo mật theo cấu trúc có thể kiểm toán và tái sử dụng.

Hãy hình dung một công ty có VNet chứa ứng dụng đặt hàng. Máy chủ ứng dụng cần gọi một số API bên ngoài để xác nhận thanh toán, nhưng không nên tự do truy cập mọi địa chỉ Internet. Đội bảo mật cũng muốn hạn chế kết nối giữa các mạng ứng dụng và ghi nhận những luồng bị từ chối. Thay vì duy trì các luật rời rạc trên từng VM, công ty có thể thiết kế Azure Firewall trên đường đi của lưu lượng, rồi dùng Firewall Policy để khai báo những kết nối được phép.

Sau bài học, bạn có thể:

- Giải thích chức năng và giới hạn của Azure Firewall so với NSG, ASG và WAF.
- Mô tả mô hình hub-and-spoke, cách UDR đưa lưu lượng đến firewall và vai trò của DNS proxy.
- Phân biệt Network, Application và DNAT rules, rule collection, rule collection group và Firewall Policy.
- Thiết kế quy tắc ưu tiên, allowlist, deny và kế thừa policy với phạm vi phù hợp.
- Tạo nền tảng Firewall Policy bằng Azure CLI, quản lý rule có quy trình và xác minh đường đi lưu lượng.
- Sử dụng nhật ký, Azure Monitor và công cụ mạng để tìm nguyên nhân khi kết nối không hoạt động.
- Ước lượng những yếu tố chi phí và rủi ro vận hành khi triển khai firewall tập trung.

## 1. Azure Firewall là gì?

**Azure Firewall** là dịch vụ tường lửa mạng được Azure quản lý, có trạng thái (**stateful**), dùng để lọc lưu lượng theo các chính sách truy cập. Bạn có thể triển khai firewall vào một VNet hoặc dùng mô hình được hỗ trợ của Azure Virtual WAN để tập trung kiểm soát lưu lượng cho nhiều workload.

Các khả năng tiêu biểu, tùy SKU và cấu hình, gồm:

- Lọc lưu lượng theo **địa chỉ nguồn/đích, cổng, giao thức** bằng network rules.
- Kiểm soát các kết nối ứng dụng **HTTP/HTTPS theo FQDN** bằng application rules.
- Chuyển tiếp kết nối inbound từ địa chỉ/cổng công khai tới đích nội bộ bằng **Destination NAT (DNAT)** khi kiến trúc hỗ trợ.
- Ghi log các quyết định của rule và cung cấp dữ liệu phục vụ chẩn đoán.
- Áp dụng **threat intelligence filtering** và các khả năng nâng cao như IDPS/TLS inspection ở SKU phù hợp.
- Quản lý luật tập trung bằng **Firewall Policy**, có thể tích hợp với Infrastructure as Code (IaC).

Azure Firewall là một dịch vụ lọc mạng, **không tự buộc mọi gói tin trong VNet phải đi qua nó**. Luồng chỉ được kiểm tra khi mạng định tuyến lưu lượng qua firewall (hoặc khi lưu lượng được chuyển tới địa chỉ công khai của firewall trong một kịch bản inbound phù hợp). Do đó, chính sách đúng nhưng route sai vẫn có thể khiến firewall không quan sát hoặc không chặn được đường đi dự định.

Azure Firewall không thay thế xác thực Microsoft Entra ID, mã hóa TLS, firewall của hệ điều hành, Web Application Firewall hay chính sách bảo vệ dữ liệu. Một kiến trúc an toàn thường dùng nhiều lớp kiểm soát.

## 2. So sánh các thành phần bảo mật mạng

| Thành phần | Nhiệm vụ chính | Phạm vi cần lưu ý |
|---|---|---|
| **Network Security Group (NSG)** | Rule Allow/Deny theo IP, cổng, giao thức, hướng trên subnet hoặc NIC | Phù hợp phân đoạn mạng gần workload; không cung cấp đầy đủ các khả năng lọc ứng dụng theo FQDN |
| **Application Security Group (ASG)** | Gom NIC/IP configuration của VM theo vai trò để làm nguồn/đích của NSG rule | ASG không tự chặn lưu lượng |
| **Azure Firewall** | Điểm kiểm soát stateful tập trung trên những đường mạng được route qua firewall | Cần triển khai, định tuyến, phân quyền, policy và logging phù hợp |
| **Web Application Firewall (WAF)** | Bảo vệ lưu lượng HTTP/HTTPS trước một số loại tấn công lớp ứng dụng | Không thay thế firewall cho mọi giao thức và đường đi của mạng |
| **Route table / UDR** | Quy định nơi gửi gói tin tiếp theo | Định tuyến không đồng nghĩa với quyền Allow/Deny |
| **Private endpoint** | Cung cấp đường truy cập riêng tới dịch vụ được hỗ trợ qua địa chỉ IP trong VNet | Không tự thay thế phân quyền dữ liệu hoặc chính sách firewall của các đường đi khác |

Ví dụ, NSG có thể chỉ cho phép web subnet gọi API subnet qua TCP 8080. Azure Firewall có thể xử lý chính sách outbound tập trung cho nhiều spoke VNet: API chỉ được gọi `api.partner.example` trên HTTPS 443. Nếu ứng dụng web cần bảo vệ trước SQL injection hoặc những mẫu tấn công HTTP, WAF có vai trò riêng ở điểm đón lưu lượng web.

Đặt NSG và Firewall vào cùng kiến trúc không tạo mâu thuẫn: một kết nối vẫn phải được cho phép bởi các biện pháp kiểm soát có hiệu lực trên đường đi. Quyền Allow của Azure Firewall không vượt qua Deny của NSG hoặc firewall trong máy ảo.

## 3. Các thành phần triển khai Azure Firewall

Một cách triển khai phổ biến là **hub-and-spoke**:

```text
                              Internet / dịch vụ ngoài Azure
                                           ^
                                           |
                                      Azure Firewall
                                    (hub VNet, policy)
                                           ^
                                           |
                                      VNet peering
                                           |
                +--------------------------+----------------------+
                |                          |                      |
           Spoke ứng dụng             Spoke dữ liệu         Spoke dùng chung
           10.20.0.0/16              10.30.0.0/16         10.40.0.0/16
                |                          |                      |
           UDR trỏ về firewall khi luồng cần được kiểm tra tập trung
```

**Hub VNet** chứa các thành phần mạng dùng chung, chẳng hạn Azure Firewall. **Spoke VNet** chứa workload. VNet peering và các cấu hình routing/forwarding phù hợp cho phép spoke sử dụng điểm kiểm soát trong hub.

### 3.1. AzureFirewallSubnet

Trong mô hình triển khai Azure Firewall trong VNet, firewall cần subnet chuyên dụng có tên **`AzureFirewallSubnet`**. Subnet này phải đáp ứng kích thước và yêu cầu của SKU/kiểu triển khai; hướng dẫn triển khai Azure Firewall thường yêu cầu một dải **/26 hoặc lớn hơn về số lượng địa chỉ** cho subnet này. Không đặt workload VM thông thường vào subnet chuyên dụng đó.

Ví dụ thiết kế minh họa:

| Thành phần | CIDR / địa chỉ | Vai trò |
|---|---|---|
| Hub VNet | `10.10.0.0/16` | Mạng hạ tầng dùng chung |
| `AzureFirewallSubnet` | `10.10.0.0/26` | Subnet chuyên dụng cho Azure Firewall |
| Firewall private IP | `10.10.0.4` | Địa chỉ giả định, dùng minh họa next hop |
| Spoke ứng dụng | `10.20.0.0/16` | Chứa máy chủ API |
| Subnet API | `10.20.1.0/24` | Có route table chuyển lưu lượng cần kiểm soát |

Địa chỉ `10.10.0.4` chỉ là ví dụ. Trong triển khai thật, lấy **private IP đang được Azure Firewall sử dụng** từ cấu hình của firewall; không tự giả định IP cố định đó.

Tùy SKU, mô hình quản trị và khả năng forced tunneling, có thể cần hoặc có lựa chọn cấu hình subnet quản trị **`AzureFirewallManagementSubnet`** cùng các điều kiện mạng liên quan. Không áp dụng một template của SKU này cho SKU khác mà bỏ qua hướng dẫn triển khai tương ứng.

### 3.2. Routing quyết định firewall có nhìn thấy lưu lượng không

Giả sử VM `10.20.1.10` truy cập HTTPS ngoài Internet. Nếu route hiệu lực của subnet chỉ ra next hop trực tiếp ra Internet thay vì firewall, bộ luật egress trên Azure Firewall sẽ **không được thực thi đối với luồng đó**.

Một cấu hình được dùng phổ biến cho egress spoke là route:

```text
Prefix đích:      0.0.0.0/0
Next hop type:    VirtualAppliance
Next hop address: <private-IP-của-Azure-Firewall>
```

Không tùy tiện thêm default route cho mọi subnet. Cần đánh giá yêu cầu outbound của dịch vụ, dịch vụ PaaS, đường đi tới mạng nội bộ, các tuyến chuyên biệt, mạng quản trị, gateway, private endpoints và khả năng **routing đối xứng**. Lưu lượng đi và về lệch đường có thể khiến firewall stateful làm rớt kết nối hoặc khiến quá trình chẩn đoán trở nên khó hiểu.

Trong hub-and-spoke, hãy kiểm tra peering và tùy chọn cho phép lưu lượng được chuyển tiếp (**forwarded traffic**) khi kiến trúc yêu cầu. Mô hình Azure Virtual WAN có cách kiểm soát định tuyến riêng và không nên sao chép nguyên xi các bước VNet peering truyền thống.

### 3.3. Public IP, SNAT và DNAT

Azure Firewall có thể dùng public IP cho các kịch bản phù hợp. Khi kết nối outbound từ IP riêng đi tới Internet thông qua firewall, **Source NAT (SNAT)** có thể chuyển địa chỉ nguồn sang địa chỉ public của firewall theo quy tắc dịch vụ.

**DNAT** là việc chuyển địa chỉ/cổng đích của một kết nối inbound tại firewall sang địa chỉ/cổng của một dịch vụ nội bộ. Ví dụ, kết nối tới public IP của firewall trên TCP 8443 có thể được ánh xạ tới máy chủ nội bộ trên TCP 443 bằng rule cụ thể, nếu mô hình mạng và phiên bản dịch vụ hỗ trợ.

DNAT không đồng nghĩa với xuất bản ứng dụng an toàn: bạn vẫn cần bảo vệ nguồn truy cập, TLS, NSG, hệ điều hành và thường là WAF nếu ứng dụng đón lưu lượng HTTP/HTTPS từ người dùng công cộng. Nên tránh công khai SSH/RDP chỉ vì việc DNAT có vẻ đơn giản.

## 4. Firewall Policy có vai trò gì?

**Azure Firewall Policy** là tài nguyên quản lý tập trung các thiết lập và tập luật của Azure Firewall. Thay vì chỉnh các bộ rule phân tán thủ công, tổ chức có thể quản lý policy như cấu hình được version hóa, review và triển khai theo quy trình.

Mô hình phân cấp khái niệm:

```text
Azure Firewall
   |
   +-- Liên kết Firewall Policy
         |
         +-- Rule Collection Group (priority)
         |     +-- Rule Collection (priority, action, type)
         |     |     +-- Rule 1
         |     |     +-- Rule 2
         |     +-- Rule Collection
         |
         +-- Rule Collection Group khác
         |
         +-- Các thiết lập policy phù hợp với SKU:
               DNS / threat intelligence / TLS inspection / ...
```

**Rule Collection Group (RCG)** gom các rule collections và có priority để sắp xếp. **Rule collection** xác định nhóm rule cùng loại và một hành động (Allow hoặc Deny đối với filter collection; NAT collection dùng hành động chuyển đổi tương ứng). **Rule** mô tả luồng cụ thể mà hệ thống cần đối chiếu.

Ví dụ phân ranh giới trách nhiệm:

| Đối tượng | Ví dụ | Người chịu trách nhiệm |
|---|---|---|
| Firewall Policy | `pol-fw-hub-prod` | Đội nền tảng và bảo mật |
| Rule collection group | `rcg-egress-app-prod` | Đội quản trị policy |
| Application collection | `allow-partner-https` | Chủ sở hữu ứng dụng đề nghị, bảo mật phê duyệt |
| Rule | `Allow-Orders-Partner-Api` | Cho phép API subnet gọi FQDN đã được phê duyệt |

Các cấu hình Firewall Policy có thể chia sẻ giữa nhiều firewall trong giới hạn và tính năng được hỗ trợ. Policy được quản lý riêng với firewall giúp giảm sự khác biệt của cấu hình giữa các môi trường có cùng tiêu chuẩn.

### 4.1. Các SKU và tính năng

Azure Firewall có các lựa chọn **Basic, Standard và Premium** với bộ khả năng và điều kiện triển khai khác nhau. Basic hướng đến các nhu cầu đơn giản hơn; Standard cung cấp nhiều chức năng kiểm soát phổ biến; Premium có các khả năng nâng cao như **TLS inspection** và **IDPS** theo cấu hình, bên cạnh các chức năng tiêu chuẩn được hỗ trợ.

Không giả định một tính năng có trên tất cả các SKU. Trước khi thiết kế, cần kiểm tra:

- SKU hỗ trợ khả năng và giới hạn throughput nào.
- Điều kiện triển khai VNet/subnet/public IP/management interface tương ứng.
- Khả năng DNS proxy, threat intelligence, FQDN filtering, Web categories, TLS inspection, IDPS, policy inheritance và những giới hạn liên quan.
- Chi phí cố định, xử lý dữ liệu, logging và các nguồn lực mạng phát sinh.

Với **TLS inspection**, cần hiểu cách cấu hình chứng chỉ, vòng đời CA, những loại kết nối được/không được kiểm tra và tác động tới bảo mật, quyền riêng tư và hoạt động ứng dụng. Không bật tính năng này đại trà chỉ để giải quyết một vấn đề định tuyến.

## 5. Ba loại rule của Azure Firewall

### 5.1. Network rules

Network rules điều khiển lưu lượng chủ yếu theo **địa chỉ nguồn, địa chỉ đích, cổng và giao thức** như TCP/UDP. Chúng phù hợp với kết nối cần kiểm soát IP/port cụ thể, chẳng hạn một máy ứng dụng kết nối dịch vụ nội bộ trên TCP 5432.

Ví dụ mô tả:

| Thuộc tính | Giá trị |
|---|---|
| Source | `10.20.1.0/24` |
| Destination | `10.30.2.10` |
| Protocol | TCP |
| Destination port | 5432 |
| Action | Allow |

Nếu dùng FQDN làm đích trong một **network rule** theo khả năng được hỗ trợ, cần thiết kế và bật **DNS proxy** theo yêu cầu của Azure Firewall. Đây là chức năng khác với application rules. Để điều khiển HTTPS theo tên máy chủ, application rules thường phù hợp hơn một network rule Allow TCP 443 đến dải IP rộng.

### 5.2. Application rules

Application rules giúp kiểm soát những kết nối ứng dụng được hỗ trợ, điển hình là HTTP/HTTPS dựa trên **FQDN** và giao thức/cổng tương ứng.

Ví dụ: API trên subnet `10.20.1.0/24` chỉ được gọi `api.partner.example` qua HTTPS TCP 443. Có thể đặt rule trong một **Application Rule Collection** với source là subnet API, protocol HTTPS và target FQDN tương ứng.

Một application rule dựa trên FQDN không nhất thiết kiểm tra toàn bộ nội dung URL hoặc payload HTTPS. Mức quan sát phụ thuộc giao thức, thông tin TLS và tính năng đã bật. Việc giải mã/kiểm tra TLS sâu cần cấu hình và SKU phù hợp. Hãy tránh coi Allow HTTPS theo FQDN là thay thế đánh giá bảo mật API, xác thực, kiểm tra certificate hay bảo vệ dữ liệu.

### 5.3. DNAT rules

DNAT rules ánh xạ **địa chỉ/cổng đích** tại firewall sang địa chỉ/cổng đích mới. Ví dụ:

```text
Nguồn từ bên ngoài (đã giới hạn theo chính sách)
     |
     | Public IP firewall:8443
     v
 Azure Firewall (DNAT rule)
     |
     | 10.20.1.10:443
     v
 Máy chủ web trong spoke
```

DNAT được dùng cho các kịch bản xuất bản kết nối được phép. Cần thiết kế đường trả lời phù hợp, kiểm tra NSG, route, load balancing và khả năng inbound được hỗ trợ theo mô hình Azure Firewall đang dùng. Không nên tự động mở toàn bộ nguồn Internet chỉ để thử nghiệm.

### 5.4. So sánh nhanh

| Loại rule | Điểm xét chính | Tình huống tiêu biểu |
|---|---|---|
| Network | IP / port / protocol, và các tùy chọn được hỗ trợ | Kết nối TCP giữa các subnet, ứng dụng nội bộ tới máy chủ cụ thể |
| Application | FQDN, giao thức ứng dụng được hỗ trợ | Giới hạn website/API outbound theo domain |
| DNAT | Chuyển đổi địa chỉ/cổng đích | Xuất bản một dịch vụ nội bộ qua địa chỉ công khai của firewall |

## 6. Thứ tự xử lý policy và nguyên tắc ưu tiên

Khác với một danh sách rule phẳng, Azure Firewall Policy tổ chức rule theo **loại**, **collection group**, **collection**, rồi **rule**. Mỗi lớp có ý nghĩa riêng.

Những nguyên tắc cần nhớ:

1. Với các rule thông thường, Azure Firewall đánh giá theo loại rule với **DNAT trước, rồi Network, sau đó Application**. Một network rule có thể quyết định luồng trước khi application rule được xét.
2. Trong phạm vi đánh giá tương ứng, **priority có giá trị số nhỏ hơn được ưu tiên hơn**. Rule Collection Group và Rule Collection có các priority riêng; hai con số này không phải một thứ tự phẳng dùng chung cho mọi loại rule.
3. Filter rule collections được cấu hình **Allow** hoặc **Deny**. Một rule khớp và được xử lý sẽ quyết định kết quả của luồng tại lớp đó. Nếu không có rule phù hợp để cho phép, chính sách mặc định là **từ chối**.
4. Với policy inheritance được hỗ trợ, chính sách của **parent policy có thứ tự ưu tiên so với child policy**; child policy không nên được coi là nơi có thể nới lỏng những giới hạn đã được parent đặt ra.
5. Các chức năng như threat intelligence filtering hoặc kiểm tra nâng cao có thể bổ sung quyết định chặn/cảnh báo, vì vậy kết quả thực tế còn phụ thuộc cấu hình policy/SKU.

**Hệ quả thực tế:** nếu tạo một network rule Allow TCP 443 từ toàn bộ API subnet đến mọi địa chỉ Internet, rule này có thể cho phép lưu lượng vượt ra ngoài tập FQDN bạn cố giới hạn bằng application rules. Khi định thiết kế egress theo allowlist FQDN, tránh mở network rule quá rộng ở giao thức/cổng tương ứng.

Ví dụ phân loại collection:

| Tầng policy | Ví dụ | Mục đích |
|---|---|---|
| RCG `rcg-network-required` | Network collection `allow-private-service` | Cho phép kết nối riêng cần thiết theo IP/cổng |
| RCG `rcg-app-egress` | Application collection `allow-approved-sites` | Chỉ cho phép một số FQDN cho HTTP/HTTPS |
| RCG `rcg-inbound-publish` | NAT collection `dnat-published-service` | Xuất bản điểm vào đã được phê duyệt |

Sắp xếp priority có chủ đích, ghi rõ owner và lý do nghiệp vụ của từng rule. Nếu phải thêm một Deny để ngăn nhóm lưu lượng cụ thể, hãy kiểm tra vị trí của Deny trong trình tự xử lý thay vì chỉ chọn một con số priority rất nhỏ rồi giả định nó chặn mọi loại rule.

## 7. Parent và child Firewall Policy

Đối với những SKU và cấu hình **hỗ trợ policy inheritance**, có thể xây dựng chính sách theo tầng:

```text
Policy nền tảng (parent)
  +-- Ràng buộc an ninh chung
  +-- Các quy tắc mạng bắt buộc của tổ chức
          |
          +-- Policy ứng dụng A (child)
          |      +-- Cho phép domain đối tác A
          |
          +-- Policy ứng dụng B (child)
                 +-- Cho phép domain đối tác B
```

Parent policy thường được quản lý bởi đội bảo mật, còn child policy có thể do đội vận hành ứng dụng quản lý trong phạm vi được ủy quyền. Mục tiêu là **tái sử dụng những kiểm soát chung** và cho phép mỗi workload có các rule phù hợp.

Ví dụ, parent policy có thể chặn một đích mạng không được phép trên phạm vi tổ chức; các nhóm ứng dụng không nên dựa vào việc thêm Allow trong child policy để vô hiệu hóa Deny đó. Phải xét cả loại rule, thứ tự đánh giá và điều kiện inheritance cụ thể.

Khi dùng inheritance:

- Chọn SKU và quan hệ parent-child được Azure hỗ trợ.
- Xác định ai sở hữu parent policy và ai được sửa child policy.
- Đặt tên và priority có quy ước; tránh collection quá rộng hoặc trùng mục đích.
- Tài liệu hóa những ngoại lệ và quy trình phê duyệt.
- Kiểm thử kết quả sau thay đổi parent vì một thay đổi có thể ảnh hưởng nhiều firewall/workload.
- Theo dõi policy nào đang được liên kết với từng firewall trước khi xóa hoặc thay thế.

Trong tổ chức nhỏ, một policy riêng cho mỗi firewall có thể đủ dễ quản lý. Chỉ dùng hệ thống phân cấp khi lợi ích tái sử dụng và phân quyền vượt trội chi phí phức tạp.

## 8. DNS proxy và kiểm soát lưu lượng theo FQDN

Khi ứng dụng gọi một hostname như `api.partner.example`, DNS trước tiên chuyển hostname đó thành một hoặc nhiều địa chỉ IP. Nếu workload dùng một DNS resolver khác với Azure Firewall, kết quả phân giải có thể không đồng nhất theo thời điểm hoặc theo vùng mạng. Điều này đặc biệt cần chú ý khi dùng **FQDN trong network rules**.

**DNS proxy** cho phép Azure Firewall nhận yêu cầu DNS của các client và chuyển tiếp tới DNS server đã cấu hình. Khi bật và cấu hình đúng, firewall có thể dựa trên thông tin phân giải mà nó quan sát để hỗ trợ lọc FQDN trong network rules theo khả năng của dịch vụ.

Các bước thiết kế:

1. Chọn DNS server upstream phù hợp: Azure-provided DNS hoặc resolver tùy chỉnh của tổ chức theo kiến trúc.
2. Bật DNS proxy trên firewall/policy theo SKU và quy trình được hỗ trợ.
3. Cấu hình workload hoặc VNet gửi truy vấn DNS đến private IP của Azure Firewall khi thiết kế yêu cầu DNS proxy.
4. Kiểm tra phân giải tên trên máy nguồn và kết quả rule trong firewall logs.
5. Kiểm tra các đường đi DNS khác, caching, split-horizon DNS, private DNS zone và private endpoint khi sử dụng.

**DNS proxy không thay thế Application Rule**. Application rule có thể kiểm tra hostname ứng dụng theo các thông tin phù hợp của lưu lượng HTTP/HTTPS, trong khi FQDN của network rule được phân giải thành địa chỉ IP. Với IP dùng chung cho nhiều tên miền, một network rule cho phép địa chỉ IP có thể không mang ý nghĩa hạn chế tên miền giống application rule.

Không dùng tên miền không rõ nguồn gốc hoặc tập wildcard quá rộng làm allowlist. Đối với ứng dụng có DNS thay đổi thường xuyên, kiểm tra hành vi thực tế cùng với giới hạn của Firewall Policy và SDK/client.

## 9. Thiết kế chính sách egress cho ứng dụng đặt hàng

Giả sử hệ thống thương mại điện tử được đặt trong spoke VNet và định tuyến outbound qua Azure Firewall trong hub. API cần kết nối tới một dịch vụ đối tác để xác thực giao dịch; nó đồng thời cần kết nối nội bộ tới database. Các luồng còn lại không có trong danh sách được phê duyệt sẽ bị từ chối.

### 9.1. Ma trận lưu lượng

| Nguồn | Đích | Giao thức/cổng | Chính sách đề xuất |
|---|---|---|---|
| Subnet API `10.20.1.0/24` | `api.partner.example` | HTTPS 443 | Application Allow, domain đích cụ thể |
| Subnet API `10.20.1.0/24` | DB VM `10.30.2.10` | TCP 5432 | Network Allow nếu luồng được định tuyến qua firewall |
| Subnet API `10.20.1.0/24` | Internet không thuộc allowlist | Bất kỳ | Không có Allow phù hợp, bị từ chối theo mặc định |
| Subnet thử nghiệm | Database production | TCP 5432 | Không tạo rule Allow; nếu cần đặt Deny tường minh để thể hiện policy |
| Máy quản trị được phê duyệt | Điểm quản trị được hỗ trợ | Cổng tối thiểu | Quy tắc riêng theo quy trình quản trị an toàn |

`api.partner.example` là tên miền minh họa, không phải một endpoint đang được Azure xác thực hay yêu cầu phải truy cập. Nếu partner thực tế dùng nhiều domain cho xác thực, redirect hoặc phân phối nội dung, nhóm triển khai cần xác minh chính xác danh sách domain và đường đi trước khi tạo rule.

Sơ đồ đường đi outbound:

```text
orders-api (10.20.1.10)
        |
        | DNS phân giải, ứng dụng kết nối HTTPS 443
        v
Subnet route table: 0.0.0.0/0 -> Firewall private IP
        |
        v
Azure Firewall + Policy
        |
        +-- Application Allow khớp api.partner.example -> Internet
        |
        +-- Không khớp Allow -> Deny, ghi nhận theo logging
```

Sơ đồ mô tả một luồng egress. Đường đi thực tế cần kiểm tra **effective routes**, peering, NSG, DNS, NAT và firewall trong host. Đối với kết nối nội bộ tới DB, route `0.0.0.0/0` chưa chắc bắt được lưu lượng nếu có tuyến cụ thể hơn hoặc peering route; cần thêm hoặc điều chỉnh route phù hợp trong kiến trúc nếu chính sách yêu cầu đi qua firewall.

### 9.2. Vì sao không nên tạo Network Allow toàn Internet cổng 443?

Giả sử policy có:

- Network Allow: `10.20.1.0/24` → `*`, TCP 443.
- Application Allow: `10.20.1.0/24` → `api.partner.example`, HTTPS 443.

Network rule có thể quyết định Allow trước khi đến application rule. Vì vậy application allowlist đã mất ý nghĩa đối với các lưu lượng khớp network rule quá rộng. Một cấu hình rõ hơn là chỉ tạo network rule cho các đích **thực sự cần IP/port**, còn HTTP/HTTPS egress theo tên miền sử dụng application rules.

### 9.3. Quy tắc Deny tường minh và deny mặc định

Azure Firewall mặc định từ chối lưu lượng không được rule phù hợp cho phép. Do đó không cần tạo một Deny catch-all trong mọi collection chỉ để có tác dụng mặc định. Tuy nhiên, tổ chức có thể dùng Deny tường minh cho một tập đích, một giao thức hoặc một nhóm nguồn cụ thể nhằm thực hiện chính sách và hỗ trợ kiểm toán.

Khi thêm Deny, cần xem xét thứ tự theo **loại rule và cấu trúc policy**. Một Deny đặt sai vị trí có thể chặn cả luồng hợp lệ hoặc không hoạt động như người thiết kế dự đoán.

## 10. Thực hành tạo Firewall Policy và định tuyến bằng Azure CLI

Phần thực hành dùng cú pháp **Bash** trong Azure Cloud Shell hoặc máy có Azure CLI tương thích. Đây là ví dụ thiết kế có điều kiện: giả sử đội nền tảng đã tạo hub VNet, spoke VNet, kết nối mạng cần thiết, firewall tương ứng và subnet ứng dụng. Các biến phải được thay bằng giá trị thật trong môi trường thực hành. Chỉ thực hiện thao tác thay đổi route trên môi trường thử nghiệm hoặc theo quy trình thay đổi được phê duyệt vì route sai có thể gây mất kết nối.

### 10.1. Xác nhận subscription và tạo policy

```bash
az account show --output table
az account set --subscription "<subscription-id>"

RG="rg-network-hub-dev"
LOCATION="southeastasia"
POLICY="pol-azfw-hub-dev"
RCG="rcg-egress-dev"

az network firewall policy create \
  --resource-group "$RG" \
  --name "$POLICY" \
  --location "$LOCATION" \
  --sku Standard
```

Lệnh tạo **Firewall Policy** ở SKU Standard. Nó **không tự triển khai một Azure Firewall đang xử lý lưu lượng**. Nếu firewall chưa có, bạn phải tạo Azure Firewall phù hợp trong VNet/Virtual WAN, đáp ứng các điều kiện subnet, IP, SKU và liên kết policy theo quy trình triển khai được hỗ trợ.

Kiểm tra tài nguyên policy:

```bash
az network firewall policy show \
  --resource-group "$RG" \
  --name "$POLICY" \
  --output json
```

### 10.2. Tạo Rule Collection Group

```bash
az network firewall policy rule-collection-group create \
  --resource-group "$RG" \
  --policy-name "$POLICY" \
  --name "$RCG" \
  --priority 200
```

Group vừa tạo là một container để bổ sung các rule collections. Trước khi cho phép lưu lượng ứng dụng, hãy lập bảng yêu cầu và cấu hình bộ luật chính xác bằng Azure Portal hoặc IaC.

Ví dụ cấu hình dự kiến, trình bày ở dạng **đặc tả nghiệp vụ minh họa** (không phải YAML trực tiếp có thể import vào Azure):

```yaml
policy: pol-azfw-hub-dev
ruleCollectionGroup: rcg-egress-dev
groupPriority: 200
collections:
  - name: allow-partner-https
    type: Application
    priority: 200
    action: Allow
    rules:
      - name: Allow-Orders-Partner
        sourceAddresses: ["10.20.1.0/24"]
        protocols: ["Https:443"]
        targetFqdns: ["api.partner.example"]
  - name: allow-private-db
    type: Network
    priority: 300
    action: Allow
    rules:
      - name: Allow-Api-To-Db
        sourceAddresses: ["10.20.1.0/24"]
        destinationAddresses: ["10.30.2.10"]
        destinationPorts: ["5432"]
        protocols: ["TCP"]
```

Đặc tả này là tài liệu để review rule. Khi nhập qua **Azure Portal**, mở Firewall Policy → **Rule collection groups** → chọn group → thêm các collection cùng rules tương ứng. Khi triển khai bằng **Bicep, ARM hoặc Terraform**, cần chuyển thông số sang schema chính xác của provider/API version đang sử dụng, kiểm tra tính hợp lệ và xem trước thay đổi trước khi áp dụng.

Đừng nhầm `priority` của collection group với `priority` của collection. Ở ví dụ trên, group priority là 200; các collection có priority riêng là 200 và 300. Không nên cho rằng Application collection 200 luôn được xét trước Network collection 300: **loại rule vẫn quyết định thứ tự đánh giá**.

### 10.3. Liên kết Firewall Policy với firewall

Trong Azure Portal, chọn **Azure Firewall** cần quản lý, xác nhận SKU và mô hình triển khai, sau đó gán hoặc thay đổi policy theo mục cấu hình phù hợp. Kiểm tra:

1. Firewall đang gắn policy nào.
2. Policy có chứa đúng collection groups và rules được phê duyệt chưa.
3. Các cảnh báo, logging và thiết lập DNS/threat intelligence có phù hợp không.
4. Đội nào có quyền sửa policy và đội nào chỉ có quyền xem.

Việc cập nhật policy có thể ảnh hưởng đồng thời nhiều firewall đang liên kết. Vì vậy, với production nên xem trước sự khác biệt và triển khai theo thứ tự môi trường, có bước kiểm thử sau mỗi lần thay đổi.

### 10.4. Tạo UDR đưa lưu lượng spoke qua firewall

Giả sử firewall đã được triển khai và private IP thật của nó đã được xác nhận. **Giá trị dưới đây là ví dụ**:

```bash
SPOKE_RG="rg-orders-dev"
SPOKE_VNET="vnet-orders-dev"
APP_SUBNET="snet-api"
ROUTE_TABLE="rt-orders-egress"
FW_PRIVATE_IP="10.10.0.4"

az network route-table create \
  --resource-group "$SPOKE_RG" \
  --name "$ROUTE_TABLE" \
  --location "$LOCATION"

az network route-table route create \
  --resource-group "$SPOKE_RG" \
  --route-table-name "$ROUTE_TABLE" \
  --name default-via-firewall \
  --address-prefix 0.0.0.0/0 \
  --next-hop-type VirtualAppliance \
  --next-hop-ip-address "$FW_PRIVATE_IP"
```

Sau khi đã kiểm tra đường đi kết nối tới hub và phạm vi tác động, liên kết route table với subnet:

```bash
az network vnet subnet update \
  --resource-group "$SPOKE_RG" \
  --vnet-name "$SPOKE_VNET" \
  --name "$APP_SUBNET" \
  --route-table "$ROUTE_TABLE"
```

Lệnh này chỉ là ví dụ cho lưu lượng khớp `0.0.0.0/0`. Những route cụ thể hơn có thể được ưu tiên, nên phải kiểm tra effective routes trên NIC thực tế. Ngoài ra, đổi route table có thể ảnh hưởng các tuyến đã được thiết kế trước đó. Với subnet đã tồn tại route table, không được tạo/gắn bảng thay thế một cách tùy tiện mà phải hòa giải đầy đủ các route đang được sử dụng.

### 10.5. Xác minh các đối tượng sau triển khai

```bash
az network firewall policy rule-collection-group show \
  --resource-group "$RG" \
  --policy-name "$POLICY" \
  --name "$RCG" \
  --output json

az network route-table route list \
  --resource-group "$SPOKE_RG" \
  --route-table-name "$ROUTE_TABLE" \
  --output table

az network vnet subnet show \
  --resource-group "$SPOKE_RG" \
  --vnet-name "$SPOKE_VNET" \
  --name "$APP_SUBNET" \
  --query "{name:name,routeTable:routeTable.id}" \
  --output json
```

Kiểm tra policy và route table là cần thiết nhưng chưa đủ. Cần xác nhận bằng **effective route**, kết nối từ VM nguồn và log trên firewall rằng lưu lượng thực sự đi qua đúng điểm kiểm soát và khớp rule dự kiến.

## 11. Giám sát, diagnostic settings và truy vấn log

Một chính sách bảo mật chỉ hữu ích khi nhóm vận hành có thể biết **rule nào đã quyết định**, luồng nào bị từ chối và thay đổi nào làm phát sinh lỗi.

Azure Firewall có thể gửi dữ liệu chẩn đoán qua **Diagnostic settings** đến các đích được hỗ trợ, chẳng hạn **Log Analytics workspace**, storage hoặc Event Hub tùy nhu cầu lưu trữ và tích hợp. Khi dùng bảng log dành riêng cho tài nguyên, các bảng thường gặp bao gồm:

| Bảng Log Analytics | Thông tin tiêu biểu |
|---|---|
| `AZFWNetworkRule` | Các kết quả liên quan đến network rule |
| `AZFWApplicationRule` | Các kết quả liên quan đến application rule |
| `AZFWNatRule` | Các sự kiện liên quan đến NAT rule |
| `AZFWThreatIntel` | Sự kiện liên quan đến threat intelligence |

Tên bảng và cấu trúc log phụ thuộc loại diagnostic settings, thời điểm và cách gửi dữ liệu. Nếu môi trường sử dụng kiểu log cũ, dữ liệu có thể được lưu theo mô hình `AzureDiagnostics`; khi đó truy vấn phải điều chỉnh cho cấu trúc thực tế.

Ví dụ KQL cơ bản với bảng resource-specific:

```kusto
AZFWApplicationRule
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
| take 50
```

Để quan sát network rules:

```kusto
AZFWNetworkRule
| where TimeGenerated > ago(1h)
| summarize Events=count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
```

Ví dụ thứ hai đếm sự kiện mỗi 5 phút; nó không chứng minh có bao nhiêu request nghiệp vụ thành công. Muốn phân tích lỗi phải mở chi tiết trường action, nguồn, đích, rule/collection và đối chiếu nhật ký ứng dụng.

Quy trình log vận hành nên gồm:

- Bật đúng category cần thiết và kiểm tra dữ liệu thực sự đến workspace.
- Có chính sách lưu giữ log phù hợp với nhu cầu điều tra và chi phí.
- Hạn chế quyền xem log vì thông tin kết nối có thể phản ánh hạ tầng và hành vi ứng dụng.
- Thiết lập alert cho số lượng Deny bất thường, luồng kết nối mới đáng ngờ hoặc sự kiện bảo mật quan trọng.
- Theo dõi thay đổi trên Firewall Policy bằng Azure Activity Log cùng hệ thống CI/CD/IaC để biết ai thay rule và vào thời điểm nào.

## 12. Chẩn đoán khi ứng dụng không kết nối được

Giả sử `orders-api` không thể gọi `https://api.partner.example` sau khi bật Azure Firewall. Hãy xác định lỗi có phát sinh ở DNS, định tuyến, policy, NSG hay chính ứng dụng.

### 12.1. Quy trình điều tra từng bước

1. **Xác minh triệu chứng:** ghi thời điểm, IP nguồn, hostname đích, giao thức, cổng, mã lỗi và môi trường. Kiểm tra ứng dụng đã gửi request hay chưa.
2. **Kiểm tra DNS:** từ host nguồn, xác nhận hostname phân giải được; đối chiếu resolver và DNS proxy nếu dùng.
3. **Kiểm tra effective routes:** xác nhận next hop của IP đích thực sự đi qua Azure Firewall. Không suy luận chỉ từ route table gắn subnet, vì route hiệu lực có thể khác do tuyến cụ thể hơn.
4. **Kiểm tra policy đang liên kết:** firewall có đang sử dụng đúng policy, collection group và rule phiên bản dự kiến không?
5. **Tìm sự kiện trong log:** dựa vào IP, thời điểm, FQDN, port, rule và action để xác định Allow/Deny hoặc không có log.
6. **Xét các lớp lọc khác:** NSG ở NIC/subnet, firewall hệ điều hành, network appliance khác và các rule ở service đích.
7. **Kiểm tra TLS và ứng dụng:** certificate, proxy, SNI/Host header, DNS caching, timeout, endpoint partner và lỗi HTTP.
8. **Thực hiện thay đổi nhỏ có kiểm soát:** sửa rule đúng mục đích, triển khai qua pipeline, kiểm thử lại và theo dõi log.

### 12.2. Bảng suy luận nhanh

| Hiện tượng | Nguyên nhân có thể | Điểm cần kiểm tra |
|---|---|---|
| Không có log cho request tại firewall | Lưu lượng không đi qua firewall hoặc diagnostics chưa cấu hình | Effective routes, peering, forwarded traffic, diagnostic settings |
| Có log `Deny` | Không có Allow phù hợp; rule Deny ưu tiên; network rule quyết định trước app rule | Loại rule, RCG, collection priority, policy parent/child, FQDN/port |
| Log `Allow` nhưng request timeout | NSG, route trả lời, service đích, host firewall hoặc kết nối không đối xứng | Network Watcher, route hai chiều, ứng dụng đích |
| DNS thất bại hoặc sai IP | DNS proxy/upstream/Private DNS/caching | Resolver, VNet DNS, DNS proxy và kết quả phân giải |
| Chỉ một vài domain hoặc URL lỗi | Allowlist thiếu endpoint phụ, TLS/SNI hoặc khác biệt loại rule | Domain đích thực tế, redirect, certificate, rule logs |
| Đột ngột nhiều ứng dụng cùng lỗi | Policy dùng chung vừa thay, mạng hub hoặc firewall có sự cố | Activity Log, policy revision, Azure Service Health, metrics/logs |

**Lưu ý:** Nếu firewall cho phép lưu lượng ở lớp mạng, điều đó không chứng minh request HTTP sẽ được chấp nhận. Dịch vụ đích có thể trả 401/403 do danh tính, 429 do giới hạn hoặc lỗi ứng dụng khác.

### 12.3. Không dùng Allow-All để sửa lỗi

Mở `Any → Any` hoặc cả subnet đi `Any:443` có thể làm sự cố biến mất nhưng cũng vô hiệu hóa mục tiêu kiểm soát egress. Khi tìm lỗi:

- Dùng IP/FQDN, cổng và phạm vi nguồn chính xác.
- Kiểm tra một thay đổi nhỏ trong môi trường thử nghiệm.
- Đặt hạn sử dụng cho ngoại lệ tạm thời và có owner chịu trách nhiệm.
- Sau khi xác định nguyên nhân, thu hồi quyền thử nghiệm không còn cần thiết.

## 13. Vận hành Firewall Policy như một sản phẩm có vòng đời

Một policy thường được nhiều đội sử dụng và có khả năng ảnh hưởng đến nhiều ứng dụng. Vì vậy, cần quy trình từ **đề xuất → review → triển khai → xác minh → ngừng rule**.

### 13.1. Chuẩn hóa yêu cầu mở kết nối

Mỗi yêu cầu cần ít nhất:

| Trường | Ví dụ |
|---|---|
| Workload và môi trường | `orders-api`, production |
| Source | `10.20.1.0/24` hoặc IP Group phù hợp |
| Destination | `api.partner.example` |
| Protocol và port | HTTPS 443 |
| Mục đích | Gửi yêu cầu xác thực giao dịch |
| Owner | Đội ứng dụng đặt hàng |
| Thời hạn | Dài hạn hoặc có ngày hết hạn |
| Quy trình kiểm thử | Kết nối hợp lệ được phép; đích khác bị chặn |

Đối với nhiều địa chỉ nguồn hoặc đích có cùng mục đích, có thể đánh giá **IP Groups** được Azure Firewall hỗ trợ để tái sử dụng tập địa chỉ trong những rule phù hợp. Tuy nhiên, chỉ gom IP có cùng trách nhiệm và phạm vi truy cập; thay đổi một IP Group dùng chung có thể tác động nhiều rule.

### 13.2. Quản lý bằng IaC và source control

Một quy trình lành mạnh có thể gồm:

1. Developer hoặc đội vận hành gửi yêu cầu kết nối và bằng chứng nhu cầu.
2. Đội bảo mật đánh giá tính tối thiểu của nguồn, đích, port, loại rule và ảnh hưởng policy parent/child.
3. Thay đổi được thực hiện trong repository IaC (Bicep/ARM/Terraform phù hợp), kèm mô tả và mã yêu cầu.
4. Pipeline kiểm tra syntax/schema, đối chiếu policy hiện tại và thực hiện **what-if/plan** theo công cụ được hỗ trợ.
5. Áp dụng trước ở môi trường kiểm thử với route và NSG tương đương về mặt logic.
6. Triển khai theo quy trình production, xác minh bằng logs và bài kiểm thử kết nối.
7. Lưu lại kết quả và loại bỏ rule không còn sử dụng theo lịch rà soát.

Nếu tổ chức chỉnh policy qua Portal, vẫn cần quản lý thay đổi và đồng bộ lại cấu hình IaC để tránh **configuration drift**. Khi policy được chia sẻ giữa nhiều firewall, kiểm thử hồi quy phải bao phủ ít nhất các luồng quan trọng của những workload bị ảnh hưởng.

### 13.3. Tên và priority dễ hiểu

Ví dụ đặt tên:

- Policy: `pol-fw-hub-prod`.
- Group: `rcg-egress-payments`.
- Collection: `app-allow-approved-partners`.
- Rule: `Allow-Orders-To-Payment-Api`.

Quy ước tốt giúp truy vết kết quả trong log và gắn rule với owner. Cần dành khoảng priority để chèn rule mới theo kế hoạch, đồng thời hiểu rằng priority **không thay đổi thứ tự loại rule**.

Không đặt toàn bộ rule của mọi team vào một collection khổng lồ nếu điều đó làm khó review. Ngược lại, không nhất thiết tạo riêng một collection cho mỗi endpoint. Hãy chọn nhóm theo chủ sở hữu, phạm vi, hành động và vòng đời giống nhau.

### 13.4. An toàn khi thay đổi và rollback

Khi một rule mới có thể chặn egress của nhiều ứng dụng:

- Duy trì danh sách đường đi mạng và kết nối quan trọng trước thay đổi.
- Thử rule trong môi trường không production, xác nhận cả luồng Allow và Deny.
- Có bản cấu hình/commit trước thay đổi và quy trình quay lại được thử nghiệm.
- Tránh thay nhiều tầng routing, NSG và Firewall Policy trong cùng một đợt nếu không cần.
- Theo dõi thời điểm triển khai để đối chiếu log và phản hồi từ ứng dụng.

Xóa policy hoặc rule collection khi còn firewall/workload phụ thuộc có thể gây mất kết nối. Trước khi dọn cấu hình, xác nhận tất cả liên kết và lưu lượng sử dụng.

## 14. Khả năng sẵn sàng, bảo mật và chi phí

Azure Firewall là dịch vụ được Azure quản lý nhưng vẫn phải được thiết kế theo khả năng sẵn sàng và giới hạn của SKU, khu vực và phương thức triển khai. Khi chọn kiến trúc:

- Kiểm tra **availability zones** và tính năng sẵn có theo Azure region/SKU.
- Xem xét tác động của sự cố hub tới các spoke phụ thuộc, kể cả đường outbound và kết nối liên mạng.
- Xác định yêu cầu mở rộng, throughput, số kết nối, kiểm soát DNS và logging.
- Kiểm tra Azure Service Health, metrics/logs và quy trình khôi phục; không mặc định mọi lỗi mạng đều do firewall policy.
- Cân nhắc kiến trúc nhiều region và routing dự phòng nếu ứng dụng có mục tiêu khôi phục tương ứng.

### 14.1. Những yếu tố làm tăng chi phí

Chi phí Azure Firewall thường chịu ảnh hưởng từ **thời gian triển khai/hoạt động và lượng dữ liệu được xử lý** theo cách tính của SKU. Tùy kiến trúc, còn có thể phát sinh phí public IP, VNet peering, dữ liệu truyền, workspace lưu log, Azure Monitor, gateway và những dịch vụ mạng bổ sung.

Một bảng dự toán thực tế nên ghi:

| Hạng mục | Cần ước lượng |
|---|---|
| Firewall SKU | Basic/Standard/Premium và đơn giá theo khu vực |
| Thời gian hoạt động | Số giờ của firewall được triển khai |
| Dữ liệu được xử lý | Khối lượng GB/TB egress, ingress và luồng liên mạng đi qua firewall |
| Network charges | Public IP, peering, gateway hoặc lưu lượng truyền theo thiết kế |
| Monitoring | Log ingestion, retention, query/alert theo cấu hình |
| Khả năng nâng cao | Yêu cầu tính năng Premium và chi phí vận hành liên quan |

Đừng tính phí chỉ dựa trên số lượng firewall rules. Dữ liệu đi qua firewall và thời gian dịch vụ tồn tại là các yếu tố quan trọng. Hãy dùng **Azure Pricing Calculator** và thông tin giá hiện hành của vùng triển khai để lập dự toán, sau đó theo dõi **Cost Management** nhằm so sánh dự toán với chi phí thực tế.

### 14.2. Khi nào nên dùng firewall tập trung?

Firewall tập trung thường mang lại lợi ích khi tổ chức có nhiều workload/VNet, cần kiểm soát egress nhất quán, điểm ghi log chung, phân quyền rule có quy trình hoặc tập luật dùng lại. Với hệ thống nhỏ, chi phí và độ phức tạp của firewall có thể lớn so với nhu cầu, nên cần so sánh với NSG, network access controls của dịch vụ đích và các lựa chọn mạng khác.

Quyết định chọn giải pháp phải dựa vào yêu cầu bảo mật và đường đi lưu lượng, không chỉ vì đã có sẵn một loại tài nguyên Azure.

## 15. Bài tập thực hành

### Tình huống

Công ty có:

- `spoke-orders`: API trong subnet `10.20.1.0/24`.
- `spoke-analytics`: công cụ báo cáo trong subnet `10.40.1.0/24`.
- Azure Firewall trong hub, private IP `10.10.0.4` (giả định).
- API chỉ được phép gọi `api.partner.example` bằng HTTPS 443.
- Công cụ báo cáo cần gọi một DB VM trong mạng riêng trên TCP 5432.
- Hai spoke không được truy cập Internet tùy ý.

**Yêu cầu:**

1. Vẽ đường đi outbound và đề xuất UDR cần thiết, giải thích vì sao phải kiểm tra effective routes.
2. Chọn Network hay Application Rule Collection cho từng luồng và ghi rõ source, destination, protocol, port, action.
3. Giải thích lỗi thiết kế nếu xuất hiện Network Allow từ cả hai subnet tới `Any` trên TCP 443.
4. Đề xuất ít nhất ba thông tin phải có trong log hoặc hồ sơ sự cố khi API không gọi được domain đối tác.
5. Nêu một cách tổ chức parent/child policy khi đội bảo mật muốn giữ những giới hạn chung, còn đội ứng dụng chỉ được thêm allowlist theo nghiệp vụ.
6. Phân tích thay đổi nào trong router/NSG/DNS có thể gây lỗi dù firewall rule đã Allow.

**Gợi ý giải:** dùng application rule cho HTTPS theo FQDN; dùng network rule cho kết nối TCP 5432 tới IP DB VM. Định tuyến các đường cần kiểm tra qua firewall, có thể cần tuyến cụ thể cho lưu lượng nội bộ. Không tạo network rule `Any:443` vì dễ làm mất hiệu lực mục tiêu lọc FQDN. Theo dõi IP nguồn, hostname/đích, thời điểm, loại rule, action, route và DNS. Parent policy chứa giới hạn chung; child chỉ chứa những quyền ứng dụng bổ sung được phép theo cơ chế hỗ trợ.

### Câu hỏi tự kiểm tra

**1. Tạo Firewall Policy có tự chặn egress của tất cả VM không?** Không. Policy phải được gắn đúng firewall và lưu lượng phải đi qua firewall theo định tuyến thực tế.

**2. Vì sao application rule Allow theo FQDN có thể chưa hạn chế được mọi HTTPS?** Network rule Allow rộng có thể xử lý luồng trước application rule; ngoài ra phải kiểm tra route, kết nối khác và khả năng quan sát FQDN.

**3. DNAT được dùng cho việc gì?** Chuyển đổi địa chỉ/cổng đích của kết nối tới địa chỉ/cổng của dịch vụ nội bộ trong các trường hợp được hỗ trợ.

**4. RCG priority có phải con số duy nhất quyết định mọi thứ tự rule không?** Không. Rule type và collection priority cũng ảnh hưởng tới thứ tự.

**5. Nếu firewall log Allow nhưng ứng dụng timeout, cần kiểm tra gì?** Effective routes, chiều trả lời, NSG, firewall host, DNS, endpoint, TLS và trạng thái ứng dụng.

**6. Vì sao phải thận trọng khi đổi parent policy?** Một thay đổi có thể ảnh hưởng nhiều child policy/firewall và do đó tác động đồng thời nhiều workload.

## 16. Checklist trước khi đưa Azure Firewall vào production

- [ ] Đã xác định mục tiêu kiểm soát, số lượng spoke, các luồng inbound/outbound và yêu cầu inter-VNet.
- [ ] Đã chọn SKU theo khả năng cần thiết, vùng triển khai và dự toán chi phí.
- [ ] Đã bố trí subnet chuyên dụng và các thành phần public/private IP theo yêu cầu triển khai.
- [ ] Đã kiểm tra VNet peering/Virtual WAN, forwarded traffic, UDR và **effective routes**.
- [ ] Đã lập ma trận nguồn, đích, protocol, cổng, owner và thời hạn cho mỗi luồng.
- [ ] Đã phân biệt Network, Application và DNAT rules; hiểu thứ tự xử lý rule.
- [ ] Đã tránh Network Allow quá rộng khiến application allowlist mất ý nghĩa.
- [ ] Đã kiểm tra DNS, DNS proxy và các phụ thuộc private DNS/endpoint nếu sử dụng.
- [ ] Đã phân quyền quản lý policy, thiết kế parent/child policy nếu cần và SKU hỗ trợ.
- [ ] Đã sử dụng IaC, kiểm soát thay đổi, review và chuẩn bị rollback.
- [ ] Đã cấu hình diagnostic settings, Log Analytics, thời hạn lưu log và cảnh báo.
- [ ] Đã kiểm thử các trường hợp Allow và Deny, bao gồm kết nối thật và những lớp NSG/host khác.
- [ ] Đã xem xét độ sẵn sàng, khôi phục, throughput, chi phí data processing và khả năng mở rộng.

## Kết luận

**Azure Firewall** thực thi kiểm soát mạng tập trung trên những lưu lượng được đưa qua nó. **Firewall Policy** giúp tổ chức quy tắc thành các rule collection groups, collections và rules, có thể quản lý tập trung, kiểm toán và triển khai bằng IaC. Network rules xử lý các nhu cầu IP/port/protocol; application rules hỗ trợ kiểm soát FQDN của các kết nối ứng dụng; DNAT rules phục vụ các kịch bản chuyển đổi đích được hỗ trợ.

Để kiến trúc hoạt động đúng, cần kết hợp **Firewall Policy + routing + DNS + NSG + giám sát**. Khi một luồng bị từ chối, hãy dựa trên effective routes và firewall logs để xác định chính xác điểm chặn. Một chính sách tốt cần diễn đạt nhu cầu kết nối tối thiểu, có owner, được thử nghiệm và được duy trì cùng vòng đời ứng dụng.
