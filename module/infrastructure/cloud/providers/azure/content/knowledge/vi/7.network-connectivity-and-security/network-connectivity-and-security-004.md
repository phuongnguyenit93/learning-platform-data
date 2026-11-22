# Tổ chức kết nối nhiều chi nhánh bằng Azure Virtual WAN

Một doanh nghiệp có ba văn phòng tại Hà Nội, Đà Nẵng và TP. Hồ Chí Minh, một trung tâm dữ liệu tại chỗ và các ứng dụng chạy trên Azure. Mỗi chi nhánh cần truy cập ứng dụng nội bộ, một số dịch vụ phải đi qua hệ thống kiểm soát bảo mật và doanh nghiệp muốn bổ sung chi nhánh mới mà không phải dựng lại toàn bộ mạng. Nếu thiết lập thủ công nhiều VPN gateway và kết nối riêng giữa các mạng, số lượng liên kết, bảng định tuyến và điểm cần bảo trì sẽ tăng nhanh.

**Azure Virtual WAN** giúp tập trung việc quản lý kết nối từ nhiều chi nhánh, người dùng từ xa và các Virtual Network (VNet) vào các **virtual hub** do Azure quản lý. Bài học này hướng dẫn cách thiết kế topology, chọn công nghệ kết nối, tổ chức định tuyến, bảo mật, dự phòng và vận hành hệ thống nhiều chi nhánh bằng Virtual WAN.

Bài thuộc chương **Kết nối và bảo vệ mạng** của module `CLOUD_PROVIDERS_AZURE`. Module giới thiệu hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; đồng thời hướng dẫn triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Với Virtual WAN, các quyết định mạng phải hỗ trợ cả tính sẵn sàng, bảo mật lẫn khả năng kiểm soát chi phí.

## 1. Kết quả cần đạt

Sau khi học, bạn có thể:

- Giải thích **Virtual WAN**, **virtual hub**, **VPN site**, **S2S VPN**, **ExpressRoute**, **P2S VPN** và **VNet connection**.
- Chọn mô hình phù hợp cho doanh nghiệp có nhiều văn phòng, nhiều region hoặc môi trường hybrid.
- Lập kế hoạch dải IP không chồng lấn cho chi nhánh, hub, VNet ứng dụng và mạng on-premises.
- Thiết kế đường đi của các luồng **branch-to-Azure**, **branch-to-branch** và **VNet-to-VNet** bằng routing trong virtual hub.
- Nêu cách kết hợp Azure Firewall, routing intent, NSG và DNS để bảo vệ các luồng cần thiết.
- Lập phương án dự phòng đường truyền và giám sát theo SLA/nhu cầu hoạt động.
- Thực hiện quy trình cấu hình, kiểm tra và xử lý lỗi ở mức kiến trúc hoặc lab được cấp phép.

## 2. Virtual WAN là gì?

Azure Virtual WAN là dịch vụ mạng có khả năng quản lý tập trung các kết nối đến và giữa các vùng mạng trên Azure. Bạn tạo một **Virtual WAN resource** để tổ chức cấu hình ở phạm vi rộng, rồi triển khai một hoặc nhiều **virtual hub** tại các Azure region cần phục vụ. Các hub là điểm kết nối cho chi nhánh, VNet, người dùng VPN và dịch vụ mạng được hỗ trợ.

| Thành phần | Chức năng | Lưu ý thiết kế |
|---|---|---|
| **Virtual WAN resource** | Tài nguyên quản lý Virtual WAN, bao gồm các virtual hub. | Tài nguyên tổ chức; không phải một tuyến VPN hoặc một subnet truyền thống. |
| **Virtual hub** | Điểm kết nối khu vực do Azure quản lý, cung cấp cơ chế định tuyến và kết nối. | Cần address prefix riêng, region phù hợp, năng lực gateway/hub được hoạch định. |
| **VPN site** | Mô tả một địa điểm on-premises và các đường link tới thiết bị VPN. | Khai báo dải IP chi nhánh, thông tin thiết bị, endpoint công khai, BGP nếu dùng. |
| **Site-to-site (S2S) VPN gateway** | Tạo tunnel IPsec/IKE giữa chi nhánh hoặc data center với hub. | Kiểm tra thiết bị tương thích, thông số tunnel, băng thông và dự phòng. |
| **ExpressRoute gateway** | Kết nối mạng tại chỗ qua ExpressRoute circuit/provider vào virtual hub. | Độ sẵn sàng của nhà cung cấp, peering, bandwidth và route propagation. |
| **Point-to-site (P2S) VPN gateway** | Kết nối người dùng/thiết bị từ xa vào hub. | Cần cấu hình xác thực, client và dải địa chỉ cấp cho người dùng từ xa. |
| **VNet connection** | Gắn VNet ứng dụng hoặc VNet hạ tầng vào virtual hub. | Kiểm tra IP overlap, route tables và bảo mật của workload. |
| **Hub routing** | Quyết định việc học, phân phối và chọn đường đi giữa các kết nối. | Quan trọng cho transit và phân tách luồng mạng. |

**Virtual hub khác VNet thông thường.** Hub là tài nguyên mạng do dịch vụ quản lý với address space và khả năng kết nối riêng. Bạn không xem hub như một VNet spoke để tự tạo VM NIC, tùy ý triển khai subnet ứng dụng hay dùng VNet peering như với một VNet thông thường. Workload nên chạy trong VNet riêng, sau đó kết nối VNet đó vào hub.

### Basic và Standard

Azure Virtual WAN có các lựa chọn như **Basic** và **Standard**, khác nhau về phạm vi tình huống kết nối:

| Nhu cầu | Basic | Standard |
|---|---|---|
| Tập trung S2S VPN đến chi nhánh | Phù hợp với chức năng kết nối cơ bản | Có |
| Kết nối VNet vào hub để xây topology doanh nghiệp phức tạp | Hạn chế hơn; không chọn Basic cho thiết kế transit VNet đa nhánh | Có |
| P2S VPN, ExpressRoute, kết nối giữa các hub/VNet | Không phải phạm vi của Basic | Hỗ trợ theo tính năng và cấu hình |
| Định tuyến transit nhiều kiểu kết nối và mô hình bảo mật hub | Không phải lựa chọn phù hợp | Nền tảng được dùng cho kiến trúc nâng cao |

Đối với doanh nghiệp cần **chi nhánh ↔ VNet ứng dụng, chi nhánh ↔ chi nhánh, nhiều hub và bảo mật tập trung**, **Standard Virtual WAN** thường là lựa chọn phù hợp. Cần đối chiếu khả năng hỗ trợ theo khu vực, SKU, gateway và những giới hạn dịch vụ hiện hành trước khi triển khai thật.

## 3. Đọc một kiến trúc nhiều chi nhánh

Xét tình huống doanh nghiệp có ba chi nhánh, một data center, một ứng dụng Production ở Southeast Asia và môi trường dự phòng ở Japan East.

```text
                          On-premises
       ┌─────────────────┬──────────────────┬───────────────────┐
       │                 │                  │                   │
   Hà Nội              Đà Nẵng          TP.HCM            Data center
  10.41.0/20          10.41.16/20       10.41.32/20        10.42.0/16
       │                 │                  │                   │
       └──── S2S VPN ────┴────── S2S VPN ───┘                   │
                         │                                     │
                         │                           ExpressRoute (nếu có)
                         ▼                                     ▼
           ┌─────────────────────────────────────────────────────┐
           │              Virtual WAN (Standard)                 │
           │                                                     │
           │     Virtual Hub - Southeast Asia                    │
           │        Hub IP: 10.240.0.0/23                         │
           │          ├── S2S VPN gateway                        │
           │          ├── ER gateway (nếu sử dụng)               │
           │          └── Hub router / route tables              │
           │                    │                                │
           │                    ├──── VNet Production            │
           │                    │      10.60.0.0/20              │
           │                    │                                │
           │                    └──── Virtual Hub - Japan East  │
           │                           10.240.2.0/23            │
           │                               │                     │
           │                               └── VNet DR           │
           │                                   10.61.0.0/20      │
           └─────────────────────────────────────────────────────┘
```

Đây là sơ đồ logic. Chi nhánh có thể dùng một hoặc nhiều đường Internet/tunnel; ExpressRoute là lựa chọn kết nối riêng từ nhà cung cấp chứ không phải tunnel Internet. Đường hub-to-hub, route propagation và chính sách bảo mật phải được cấu hình, xác minh thực tế để có các luồng transit theo yêu cầu.

**Ý nghĩa các thành phần:**

- **Chi nhánh** dùng thiết bị router/firewall hỗ trợ IPsec/IKE và có thể dùng BGP để trao đổi route.
- **Virtual Hub Southeast Asia** là điểm vào gần các ứng dụng Production; tại đây các kết nối và route được quản lý.
- **VNet Production** chứa workload (web/API, database private, private endpoints) và kết nối vào hub bằng VNet connection.
- **Virtual Hub Japan East** hỗ trợ vùng dự phòng hoặc workload ở region khác trong mô hình multi-hub.
- **Data center** có thể dùng ExpressRoute hoặc S2S VPN tùy mục tiêu, nhà cung cấp và ngân sách.

Lợi ích thiết kế không chỉ là giảm số kết nối thủ công. Nhóm mạng còn có một mô hình chung để quản lý site, route, bảo mật, quan sát lưu lượng và bổ sung chi nhánh theo mẫu thống nhất.

## 4. Khi nào nên chọn Virtual WAN?

Virtual WAN hữu ích khi có nhiều chi nhánh, cần quản trị kết nối tập trung, kết hợp VPN/ExpressRoute/P2S hoặc mở rộng nhiều Azure region.

So sánh ở mức định hướng:

| Tiêu chí | Hub-and-spoke VNet tự quản lý | Azure Virtual WAN |
|---|---|---|
| Điểm kết nối trung tâm | VNet hub với gateway, route và các thành phần bạn tự quản trị nhiều hơn | Virtual hub do Azure quản lý |
| Tích hợp nhiều chi nhánh | Tạo và vận hành gateway, site, peering/route tùy kiến trúc | Mô hình VPN sites và hubs để tổ chức tập trung |
| Transit giữa nhiều region | Thiết kế peering/gateway/routing theo từng topology | Mô hình multi-hub Standard, kiểm soát bằng hub routing |
| Quyền kiểm soát topology | Linh hoạt khi cần tùy biến hạ tầng network appliance/VNet hub | Có các khả năng tích hợp quản lý nhưng phải theo giới hạn của virtual hub |
| Chi phí | Tùy gateway, appliance, peering và dữ liệu truyền | Có chi phí hub, gateways, xử lý/lưu lượng và dịch vụ bổ sung |

Không phải mọi tổ chức đều cần Virtual WAN. Một hệ thống chỉ có một VNet và một đường VPN đơn giản có thể không cần thêm tầng quản trị này. Quyết định dựa trên số site, số region, kiểu transit, bảo mật, khả năng vận hành và mô hình chi phí.

## 5. Lập kế hoạch địa chỉ IP và region

**Quy hoạch địa chỉ là bước đầu tiên trước khi tạo VPN hoặc peering.** Các dải được quảng bá từ chi nhánh, mạng data center, VNet ứng dụng và hub phải được xác minh không chồng lấn theo mô hình kết nối thực tế.

Ví dụ bảng IPAM minh họa:

| Phạm vi | CIDR dự kiến | Ghi chú |
|---|---|---|
| Chi nhánh Hà Nội | `10.41.0.0/20` | LAN tại văn phòng |
| Chi nhánh Đà Nẵng | `10.41.16.0/20` | LAN tại văn phòng |
| Chi nhánh TP. Hồ Chí Minh | `10.41.32.0/20` | LAN tại văn phòng |
| Data center | `10.42.0.0/16` | Có thể gồm các subnet con thực tế |
| Virtual hub Southeast Asia | `10.240.0.0/23` | Dải riêng cấp cho hub |
| Virtual hub Japan East | `10.240.2.0/23` | Không giao nhau với hub thứ nhất |
| VNet Production | `10.60.0.0/20` | Workload chính |
| VNet DR | `10.61.0.0/20` | Workload dự phòng |
| Dải P2S VPN (nếu dùng) | `10.250.0.0/22` | Pool riêng cho VPN client |

Các dải này chỉ dùng để minh họa; khi triển khai, cần kiểm tra các VNet, site, kết nối đối tác và vùng mạng có thể sẽ liên thông trong tương lai.

### Tại sao phải cấp riêng dải IP cho virtual hub?

Virtual hub dùng dải IP riêng để vận hành các thành phần kết nối và định tuyến được quản lý. Địa chỉ của hub phải được cấp phát theo yêu cầu dịch vụ; đây **không** phải nơi đặt subnet của máy ảo ứng dụng.

Kích thước khối nên tính từ số và loại gateway, các tích hợp cần thiết và khả năng mở rộng. Ví dụ `/23` có thể là lựa chọn lập kế hoạch; điều kiện prefix tối thiểu hoặc thay đổi hub address space tùy tính năng dịch vụ phải đối chiếu tài liệu hiện hành. Không chọn dải quá nhỏ hoặc dải dùng chung với chi nhánh khác chỉ vì tiết kiệm IP.

### Chọn region cho hub

Đặt hub ở các region phục vụ kết nối và workload trọng yếu, đồng thời cân nhắc:

- Độ trễ của người dùng tại chi nhánh đến ứng dụng.
- Nơi chạy workload và phương án dự phòng region.
- Khu vực có sẵn tính năng gateway/bảo mật cần dùng.
- Luồng dữ liệu xuyên region và chi phí phát sinh.
- Khả năng sử dụng ExpressRoute circuit/provider tại địa điểm liên quan.

Một hub ở region gần người dùng **không bảo đảm** độ trễ thấp nhất cho mọi luồng; vẫn phải đo hiệu năng tuyến end-to-end, nhất là khi dữ liệu phải đi qua firewall hoặc region khác.

## 6. Mô hình hóa chi nhánh thành VPN site

Trong Virtual WAN, **VPN site** đại diện cho một địa điểm kết nối. Khi tạo site, bạn khai báo thông tin cần thiết cho các đường link tại địa điểm đó, chẳng hạn:

1. Tên site, mô tả, địa lý hoặc nhóm phụ trách.
2. Prefix mạng LAN của chi nhánh cần quảng bá.
3. Thông tin thiết bị VPN tại site (vendor/model, khi phù hợp).
4. Public IP hoặc endpoint của thiết bị, thông tin mỗi ISP/link.
5. Băng thông link dự kiến và cấu hình BGP nếu sử dụng.
6. Virtual hub/gateway mà site sẽ kết nối đến.

Một site có thể được mô hình hóa với nhiều liên kết thiết bị/ISP tùy kiểu kết nối được hỗ trợ. Điều này cho phép bạn mô tả một chi nhánh có mạng dự phòng thay vì tạo bảng cấu hình thiếu liên kết tới cùng một site.

### Static routing hay BGP?

| Cơ chế | Lợi thế | Điều cần lưu ý |
|---|---|---|
| **Static** | Đơn giản với môi trường nhỏ, prefix ít và ít thay đổi. | Khi mở rộng chi nhánh hoặc đổi prefix, route phải được cập nhật và kiểm thử. |
| **BGP** | Trao đổi tuyến động, phù hợp nhiều prefix và thay đổi đường truyền. | Cần chuẩn bị ASN, BGP peers, route filter, xác thực/chính sách thiết bị và hiểu quảng bá route. |

Với nhiều chi nhánh, BGP thường giảm công việc quản lý route thủ công, nhưng chỉ phát huy hiệu quả khi các tuyến được quảng bá chính xác. Không quảng bá tùy tiện một supernet lớn hoặc default route `0.0.0.0/0` khi chưa thống nhất mô hình định tuyến.

### Chuẩn bị thiết bị chi nhánh

Kiểm tra khả năng tương thích IPsec/IKE, thuật toán bảo mật, NAT traversal, public endpoint, tính năng BGP và cấu hình tunnel theo yêu cầu VPN gateway. Cần xác minh nhà mạng cho phép lưu lượng cần thiết và thiết bị có đủ năng lực mã hóa ở lưu lượng thực tế.

Các thông số tunnel/IPsec/IKE và shared key phải được truyền qua kênh quản lý bí mật của tổ chức; không chèn khóa dùng thực tế vào bài tập, mã nguồn hoặc ticket công khai.

## 7. Chọn S2S VPN, ExpressRoute hay P2S

Ba công nghệ giải quyết các kiểu truy cập khác nhau:

### Site-to-site VPN

**S2S VPN** tạo tunnel mã hóa IPsec/IKE giữa địa điểm on-premises và VPN gateway trong virtual hub qua các mạng truyền dẫn phù hợp, thường là Internet.

Phù hợp khi:

- Chi nhánh có kết nối Internet ổn định và thiết bị VPN tương thích.
- Cần triển khai nhanh các site mới.
- Cần đường dự phòng cho đường kết nối riêng.
- Muốn quản lý tập trung các VPN sites và tunnels.

Những yếu tố cần thử nghiệm: băng thông hiệu dụng sau mã hóa, độ trễ, packet loss, khả năng failover của link và router, route convergence, số session và chất lượng hai ISP.

### ExpressRoute

**ExpressRoute** sử dụng kết nối riêng thông qua nhà cung cấp tới hạ tầng Microsoft. Phù hợp với trung tâm dữ liệu hoặc site có nhu cầu băng thông, tính ổn định và yêu cầu mạng riêng cao.

Cần thiết kế circuit, peering và route rõ ràng. ExpressRoute không tự thay thế mọi lớp bảo mật ứng dụng và không đồng nghĩa lưu lượng đã được mã hóa đầu cuối trong mọi trường hợp. Nếu tổ chức yêu cầu mã hóa, hãy đánh giá cơ chế bảo vệ phù hợp.

### Point-to-site VPN

**P2S VPN** cho laptop/thiết bị của người dùng từ xa kết nối vào hạ tầng mạng Azure, khác với S2S VPN giữa hai hệ thống mạng.

Cần xem xét loại xác thực, chứng chỉ hoặc Microsoft Entra ID theo tính năng được hỗ trợ, client VPN, pool địa chỉ cấp cho người dùng, split tunneling và quyền truy cập tài nguyên. P2S thường là nhu cầu mở rộng của kiến trúc Standard, không phải thành phần bắt buộc để kết nối các chi nhánh cố định.

### Chọn công nghệ theo nhu cầu

| Tình huống | Giải pháp thường cân nhắc |
|---|---|
| 20 chi nhánh có 2 ISP, cần truy cập ứng dụng Azure | S2S VPN qua Virtual WAN và thiết kế dự phòng |
| Data center cần kết nối riêng tới Azure | ExpressRoute, có thể bổ sung S2S VPN làm phương án dự phòng |
| Nhân viên làm từ xa trên laptop | P2S VPN hoặc mô hình truy cập ứng dụng phù hợp |
| Nhiều VNet ứng dụng ở các region | VNet connections và multi-hub Standard |
| Chi nhánh cần trao đổi dữ liệu trực tiếp qua Azure | Hub routing và route propagation phù hợp; kiểm tra đường transit |

## 8. Định tuyến trong virtual hub

Một kết nối VPN “Connected” hoặc tunnel báo “Up” **chưa đủ chứng minh ứng dụng truy cập được**. Lưu lượng còn cần route chiều đi/chiều về, kiểm soát firewall, DNS và chính sách của workload.

Trong Standard Virtual WAN, virtual hub sử dụng cơ chế định tuyến để kết nối các loại network connection. Những khái niệm quan trọng gồm:

- **Route table:** nhóm tuyến dùng để quyết định đường đi của lưu lượng.
- **Association:** xác định route table được một connection sử dụng khi gửi traffic vào hub.
- **Propagation:** xác định các route của connection sẽ được quảng bá vào route table nào.
- **Label:** tên nhóm logic có thể hỗ trợ quản lý việc propagation đến nhiều route tables.
- **Default route table:** bảng định tuyến mặc định cho một số mô hình kết nối, cần xem cấu hình thực tế.
- **None route table:** lựa chọn không tuyên truyền route theo cách cấu hình hỗ trợ; không nên xem là biện pháp bảo mật duy nhất.
- **Routing intent/policy:** cơ chế chỉ định đường đi cho một số nhóm lưu lượng như private hoặc Internet thông qua giải pháp bảo mật được hỗ trợ.

Các route tables, labels, propagation và routing intent có ràng buộc tương thích riêng. Không mặc định rằng có thể kết hợp mọi tùy chọn route hoặc override hành vi bảo mật bằng một bảng route tùy ý.

### Ví dụ các luồng cần hỗ trợ

| Nguồn | Đích | Yêu cầu | Các kiểm tra chính |
|---|---|---|---|
| Chi nhánh Hà Nội | `10.60.0.0/20` (Production) | Được phép, qua điểm kiểm soát nếu quy định | Route branch→hub→VNet; route chiều về; firewall/NSG; DNS |
| Chi nhánh Đà Nẵng | Chi nhánh Hà Nội | Chỉ dịch vụ đã được phép | Branch-to-branch transit, route propagation, chính sách phân đoạn |
| Data center | VNet Production | Kết nối riêng/ổn định | ExpressRoute/VPN, BGP, route preference, bảo mật hai chiều |
| VNet DR | VNet Production | Đồng bộ theo ứng dụng | Inter-hub routing, port cần thiết, độ trễ và lưu lượng liên vùng |
| Laptop VPN | Ứng dụng nội bộ | Theo danh tính và quyền | P2S pool, xác thực, route, DNS, authorization |

### Lưu lượng chi nhánh → ứng dụng

Với một gói tin từ máy tại Hà Nội tới private IP máy chủ ở Production:

1. Router chi nhánh chọn tunnel/đường đến Azure cho prefix `10.60.0.0/20`.
2. S2S VPN gateway tại hub tiếp nhận gói và hub router chọn route tới VNet connection phù hợp.
3. Nếu có routing intent hoặc bảo mật trung tâm, luồng có thể được chuyển qua điểm kiểm soát theo chính sách.
4. NSG/firewall/host firewall của workload quyết định gói có được phép hay không.
5. Đường trả về cần tồn tại, phù hợp với kiểm tra trạng thái kết nối và không gây bất đối xứng ngoài thiết kế.

Nếu chỉ có route chiều đi, ping hoặc TCP thường vẫn thất bại. Khi dùng thiết bị kiểm soát stateful, đường đi và đường về cần được thiết kế tránh chuyển qua các firewall khác nhau nếu chúng không chia sẻ trạng thái theo cách hỗ trợ.

### Branch-to-branch và hub-to-hub

Ở mô hình Standard, Virtual WAN hỗ trợ transit giữa các kết nối và giữa các virtual hubs trong phạm vi tính năng được cấu hình. Tuy nhiên, khả năng liên thông thực tế phụ thuộc **association, propagation, routing policy, gateway và kiểm soát bảo mật**. Đừng xem việc hai chi nhánh cùng kết nối một Virtual WAN là bằng chứng chúng sẽ trao đổi dữ liệu được.

Nếu tổ chức yêu cầu **chi nhánh không được truy cập trực tiếp lẫn nhau**, cần thiết kế phân đoạn route và chính sách firewall rõ ràng, kiểm thử các lưu lượng bị từ chối. Route isolation không thay cho kiểm soát lớp ứng dụng.

## 9. Tổ chức bảo mật trong Virtual WAN

Virtual WAN giúp đưa mạng về mô hình quản lý nhất quán; **bản thân việc tạo hub không tự động lọc mọi lưu lượng**. Cần xác định nơi và cách áp dụng kiểm tra bảo mật.

### Secure virtual hub

Bạn có thể kết hợp Virtual WAN Standard với các cơ chế bảo mật được hỗ trợ, chẳng hạn Azure Firewall trong một **secured virtual hub**. Với kiến trúc có routing intent và routing policies, một số luồng **private traffic** hoặc **Internet traffic** có thể được điều hướng qua giải pháp kiểm soát bảo mật được tích hợp phù hợp.

Sơ đồ nguyên tắc:

```text
Chi nhánh / VPN site
        │
        ▼
  VPN gateway tại hub
        │
        ▼
  Hub routing / routing policy
        │
        ▼
  Firewall / security service (khi cấu hình)
        │
        ▼
  VNet workload → NSG/host policy → ứng dụng
```

Định tuyến qua firewall phải được **cấu hình và xác minh**; các chi tiết phụ thuộc loại hub, tính năng và dịch vụ bảo mật. Không coi sơ đồ trên là đường đi mặc định của mọi Virtual WAN.

### Các lớp kiểm soát

- **IPsec/IKE:** bảo vệ tunnel S2S VPN qua đường truyền phù hợp.
- **BGP và route policy:** kiểm soát route nhận/quảng bá, tránh lan truyền mạng không mong muốn.
- **Azure Firewall hoặc NVA tích hợp được hỗ trợ:** kiểm soát luồng cần inspect theo chính sách.
- **NSG:** lọc lưu lượng trong subnet/NIC của workload VNet.
- **Identity và authorization:** xác định người dùng, service principal hoặc workload nào được phép sử dụng ứng dụng.
- **Private endpoints và DNS:** giúp truy cập dịch vụ PaaS qua private IP khi được cấu hình đúng.
- **Logging/monitoring:** cung cấp bằng chứng cho vận hành và điều tra bảo mật.

Đừng dùng một quy tắc firewall `Allow Any Any` chỉ để kiểm tra connectivity rồi để nguyên trong Production. Hãy xác định cặp nguồn–đích, giao thức, cổng và lý do nghiệp vụ cụ thể.

## 10. DNS khi nhiều chi nhánh truy cập ứng dụng Azure

Kết nối IP thành công vẫn có thể không dùng được ứng dụng nếu tên miền không phân giải đúng. Một số hệ thống dùng private endpoints hoặc tên nội bộ và cần giải quyết DNS xuyên mạng.

Ví dụ ứng dụng sử dụng tên `api.internal.example` và Azure SQL private endpoint. Chi nhánh cần:

1. Có tuyến đến IP đích trong VNet hoặc endpoint liên quan.
2. Phân giải tên nội bộ qua DNS của doanh nghiệp hoặc Azure DNS Private Resolver theo thiết kế.
3. Cấu hình DNS forwarding từ site on-premises tới resolver phù hợp, nếu chọn cách này.
4. Liên kết các private DNS zones tới VNet cần sử dụng theo khả năng hỗ trợ.
5. Kiểm tra firewall/NSG và đường quay về khi dùng DNS và ứng dụng.

**Virtual WAN không thay thế hệ thống thiết kế DNS nội bộ.** Việc có tunnel VPN và route không bảo đảm hostname private tự động phân giải. Hãy kiểm thử cả truy vấn DNS và kết nối đến IP đã phân giải.

## 11. Thiết kế dự phòng và khả năng phục hồi

Một kiến trúc nhiều chi nhánh phải xét sự cố của ISP, thiết bị on-premises, tunnel VPN, gateway, hub và cả region ứng dụng.

### Nhiều đường ISP và tunnel

Chi nhánh quan trọng nên xem xét:

- Hai đường kết nối độc lập hoặc hai ISP khi khả thi.
- Thiết bị VPN dự phòng hoặc cơ chế high availability tại site.
- Nhiều VPN site links/tunnels theo mô hình được dịch vụ hỗ trợ.
- BGP để phát hiện/điều chỉnh route khi có sự cố, kết hợp với thiết kế path preference rõ ràng.
- Kiểm thử rớt một ISP, một thiết bị hoặc một tunnel có ảnh hưởng tới phiên ứng dụng hay không.

Không mặc định “có hai tunnel” là hệ thống đã resilient. Nếu cả hai phụ thuộc cùng một modem, đường cáp, nguồn điện hoặc router, rủi ro điểm lỗi đơn vẫn còn.

### Multi-hub, multi-region

Với workload phục vụ nhiều khu vực hoặc có yêu cầu DR, triển khai nhiều virtual hub và kết nối VNet tại các region tương ứng. Xác định:

- Nhánh nào ưu tiên hub nào ở trạng thái bình thường.
- Khi mất hub/region, đường dự phòng hoạt động bằng route nào và ai thay đổi cấu hình.
- Dịch vụ ứng dụng/DB ở region dự phòng có thực sự sẵn sàng và nhất quán dữ liệu không.
- RTO/RPO và độ trễ chấp nhận được theo ứng dụng.
- Băng thông và chi phí khi traffic chuyển sang vùng khác.

**Multi-hub không tự tạo DR cho ứng dụng.** Nếu cơ sở dữ liệu hoặc ứng dụng chỉ triển khai ở một region, một đường mạng dự phòng không bảo đảm dịch vụ tiếp tục hoạt động khi region chính gặp sự cố.

### Quy trình thử nghiệm failover

1. Đo độ trễ, packet loss, tốc độ truyền và trạng thái route lúc bình thường.
2. Thực hiện thay đổi có kiểm soát trong khung bảo trì/lab, ví dụ vô hiệu hóa một đường ISP.
3. Quan sát BGP/tunnel states, route hội tụ và thời gian gián đoạn ứng dụng.
4. Kiểm tra lại đường trả về, DNS, các phiên TCP và kết quả từ chi nhánh.
5. Khôi phục cấu hình, ghi lại thời gian phục hồi, cảnh báo và hành động cải tiến.

## 12. Quy trình triển khai trên Azure Portal

Một trình tự triển khai theo từng lớp giúp giảm lỗi cấu hình và dễ khoanh vùng khi gặp sự cố.

### Giai đoạn A: Chuẩn bị

Thu thập danh sách site, subnet địa phương, thiết bị VPN, IP WAN/ISP, khả năng BGP, bandwidth, các region, địa chỉ VNet, yêu cầu bảo mật và danh sách luồng ứng dụng. Chọn subscription, resource group, region và quyền quản trị phù hợp.

Lập bảng địa chỉ, bảng luồng được phép, kế hoạch failover và ngân sách trước khi tạo các gateway có thể phát sinh chi phí.

### Giai đoạn B: Tạo Virtual WAN và hubs

1. Vào [Azure Portal](https://portal.azure.com/) và mở **Virtual WANs**.
2. Tạo Virtual WAN resource với subscription, resource group, tên và loại **Standard** nếu kiến trúc cần các kết nối nâng cao.
3. Tạo **virtual hub** ở region chính, cấp địa chỉ CIDR riêng đã được duyệt.
4. Chọn và triển khai VPN gateway của hub với năng lực phù hợp khi cần S2S VPN; thêm ExpressRoute/P2S gateway nếu thực tế sử dụng.
5. Nếu cần, tạo hub thứ hai tại region dự phòng và thiết kế kết nối giữa các hubs.

Việc tạo hub/gateway có thể cần thời gian triển khai đáng kể và có chi phí ngay cả khi chưa có nhiều traffic. Chỉ tạo các thành phần đã được duyệt trong kiến trúc.

### Giai đoạn C: Khai báo site và tạo S2S VPN connections

1. Tạo **VPN site** cho Hà Nội, Đà Nẵng, TP. Hồ Chí Minh.
2. Nhập địa chỉ mạng LAN, thông tin device và link/public IP.
3. Chọn virtual hub/VPN gateway cần kết nối, tạo VPN connections và thiết lập BGP nếu mô hình yêu cầu.
4. Lấy cấu hình do Azure cung cấp phù hợp với thiết bị VPN hoặc đối chiếu theo tài liệu vendor.
5. Cấu hình thiết bị tại chi nhánh bằng các thông số tunnel và routing tương ứng.
6. Xác minh tunnel và BGP đạt trạng thái mong muốn.

Khi dùng ExpressRoute, thêm bước cấu hình circuit và kết nối circuit với ExpressRoute gateway phù hợp. P2S cần cấu hình người dùng, phương thức xác thực và VPN client riêng.

### Giai đoạn D: Kết nối VNet và kiểm soát routing

1. Tạo hoặc chọn VNet Production với prefix không trùng mạng khác.
2. Tạo VNet connection từ VNet đó vào virtual hub.
3. Xác định route table association và propagation cho connection.
4. Cấu hình chính sách bảo mật/routing intent theo thiết kế nếu dùng secured hub.
5. Kiểm tra route giữa chi nhánh–VNet, giữa các chi nhánh được phép và các VNet ở region khác.
6. Cấu hình DNS và các quy tắc workload (NSG/host firewall).

### Giai đoạn E: Kiểm thử trước nghiệm thu

- Từng chi nhánh truy cập được ứng dụng đúng hostname và cổng dịch vụ.
- Luồng bị cấm giữa các chi nhánh hoặc nhóm mạng thực sự bị chặn.
- Hoạt động failover của ISP/tunnel được kiểm thử theo quy trình.
- Log, metrics và alert rules có tín hiệu được quan sát.
- Số liệu băng thông/độ trễ và chi phí dự kiến phù hợp yêu cầu nghiệp vụ.

Không nên cho rằng việc Portal hiển thị “Connected” là đủ để nghiệm thu; cần kiểm thử ứng dụng end-to-end.

## 13. Kiểm tra cấu hình bằng Azure CLI

Sau khi triển khai Portal, Azure CLI giúp kiểm tra tài nguyên và dùng dữ liệu cho quy trình vận hành. Các lệnh dưới đây là **read-only**, không tạo gateway hay tunnel. Hãy thay resource group và subscription phù hợp.

### Xác nhận subscription

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table
```

### Liệt kê Virtual WAN

```bash
az network vwan list \
  --resource-group "rg-connectivity" \
  --output table
```

### Liệt kê virtual hubs

```bash
az network vhub list \
  --resource-group "rg-connectivity" \
  --output table
```

### Liệt kê các VPN sites

```bash
az network vpn-site list \
  --resource-group "rg-connectivity" \
  --output table
```

### Kiểm tra một hub cụ thể

```bash
az network vhub show \
  --resource-group "rg-connectivity" \
  --name "vhub-sea" \
  --output json
```

Các lệnh liệt kê cấu hình không chứng minh tuyến traffic vận hành đúng. Để kiểm tra tình trạng link, routes thực tế, gateway và lưu lượng, hãy kết hợp thông tin trong Azure Portal, metrics, diagnostic logs và công cụ giám sát của thiết bị on-premises. Khả năng/đối số của một số lệnh Virtual WAN nâng cao phụ thuộc phiên bản Azure CLI và extension; đối chiếu `az network ... --help` trước khi tự động hóa.

## 14. Giám sát và xử lý sự cố kết nối

Các nhóm cần theo dõi gồm: **trạng thái tunnel**, **BGP routes**, **VPN/ER gateway metrics**, **hub routing**, **traffic/packet loss/latency**, **health của thiết bị ISP**, **DNS** và **log bảo mật**.

Nguồn quan sát thường dùng:

- Trang **Virtual WAN**, **Virtual hub**, **VPN site** và **VPN connection** trong Portal.
- **Azure Monitor metrics** và alerts của các gateway/dịch vụ được hỗ trợ.
- **Diagnostic settings/logs** được gửi tới Log Analytics, Storage hoặc Event Hubs tùy tính năng.
- **Effective routes** hoặc chế độ xem route của virtual hub (theo khả năng cung cấp của Portal/API).
- Log, trạng thái BGP/IPsec và số liệu ISP ở router/firewall chi nhánh.
- Kiểm thử DNS, TCP/HTTPS và application monitoring tại nguồn–đích.

### Bảng xử lý sự cố

| Hiện tượng | Nguyên nhân thường gặp | Cách khoanh vùng |
|---|---|---|
| Tunnel S2S không lên | Public IP sai, mismatch IKE/IPsec, shared key, NAT hoặc ISP | Kiểm tra thông số hai đầu, thiết bị và log VPN gateway |
| Tunnel lên nhưng không truy cập được ứng dụng | Thiếu route, route chiều về, NSG/firewall chặn hoặc DNS sai | So sánh effective routes, kiểm tra từ nguồn tới IP rồi hostname |
| Một chi nhánh truy cập được, chi nhánh khác không | Site prefix/BGP propagation khác nhau, policy phân đoạn | So sánh cấu hình của hai sites và các route tables |
| Truy cập được theo IP nhưng không được theo hostname | Thiếu DNS forwarding, private zone link hoặc bản ghi sai | Tra DNS từ chính máy tại chi nhánh, kiểm tra resolver |
| Traffic đi vòng qua region không mong muốn | Association/propagation hoặc đường ưu tiên chưa phù hợp | Xem hub routes, BGP quảng bá, chính sách routing |
| Một ISP mất là toàn chi nhánh ngừng truy cập | Thiếu đường/tunnel dự phòng hoặc route failover không hội tụ | Kiểm thử backup link và trạng thái BGP |
| Ứng dụng timeout nhưng VPN vẫn xanh | Hết capacity, packet loss, firewall state, lỗi workload | Đo lưu lượng, latency, gateway metrics, ứng dụng và firewall |
| Branch-to-branch ngoài dự kiến | Route propagation quá rộng, thiếu chính sách phân đoạn | Xem route table association/propagation và chính sách bảo mật |

### Quy trình điều tra nhanh

1. **Xác định phạm vi:** site nào, hostname/IP nào, port nào, thời điểm và loại luồng.
2. **Kiểm tra đường truyền:** ISP/device, trạng thái tunnel, BGP, gateway health.
3. **Kiểm tra route hai chiều:** prefix nguồn–đích và chiều về, hub route tables, route được quảng bá.
4. **Kiểm tra bảo mật:** Azure Firewall/NVA, NSG, ACL on-premises, host firewall.
5. **Kiểm tra DNS:** phân giải hostname từ máy thật ở chi nhánh.
6. **Đối chiếu thay đổi gần nhất:** site link, route, policy, VNet connection hoặc firmware.
7. **Ghi bằng chứng:** request time, IP, route, log, cảnh báo và thời gian khôi phục.

## 15. Chi phí và quản trị vận hành

Virtual WAN hỗ trợ giảm công sức tự quản lý nhiều gateway, nhưng cần **dự toán chi phí theo kiến trúc**. Thành phần chi phí có thể gồm:

| Nhóm | Yếu tố ảnh hưởng |
|---|---|
| Virtual hubs | Số lượng, loại/tính năng và thời gian sử dụng |
| VPN/ExpressRoute/P2S gateways | Năng lực triển khai, gateway scale units, thời gian và loại kết nối |
| Data transfer/routing | Lưu lượng giữa sites, VNet, hub, region và những mức phí liên quan |
| ExpressRoute | Circuit/provider, bandwidth, mô hình tính phí đã chọn |
| Azure Firewall/giải pháp bảo mật | Dịch vụ bảo mật và lưu lượng được xử lý |
| Log Analytics và giám sát | Dung lượng ingest, retention, alerts và lưu trữ |

Không có một giá cố định đúng cho mọi Virtual WAN. Trước khi triển khai, dùng **Azure Pricing Calculator** và báo giá mạng/provider hiện hành để dự toán với số hubs, số site links, gateway capacity, lưu lượng tháng và giải pháp bảo mật cụ thể. Đặc biệt cần xem tác động của **hub bổ sung ở region dự phòng** và **traffic chuyển vùng**.

### Cách tổ chức quản trị

Thiết lập và duy trì:

- **Bảng site inventory:** site owner, ISP, thiết bị, firmware, public endpoint, subnet, BGP ASN.
- **Bảng IPAM:** CIDR của các hub, VNet, site, P2S và các prefix dự phòng.
- **Bảng connectivity matrix:** nguồn, đích, port, có cần qua firewall hay không, nhóm phê duyệt.
- **Runbook:** chuẩn cấu hình thiết bị, xử lý tunnel down, thay đổi route, quay lui và failover.
- **Monitoring baseline:** tunnel uptime, packet loss, RTT, throughput, route stability và tình trạng ứng dụng.
- **Quy trình quản lý thay đổi:** phân quyền quản trị, kiểm tra route trước/sau và lưu nhật ký thay đổi.

Với tổ chức có nhiều subscription hoặc nhóm vận hành, cần thống nhất trách nhiệm ai quản lý hub, ai quản lý VPN site, ai phê duyệt security policy và ai vận hành từng VNet/workload.

## 16. Bài thực hành: thiết kế Virtual WAN cho ba chi nhánh

**Bối cảnh:** Doanh nghiệp có ba văn phòng Việt Nam và hai ứng dụng tại hai region Azure. Các văn phòng đều cần truy cập ứng dụng Production, nhưng chỉ Hà Nội và TP. Hồ Chí Minh được phép truy cập hệ thống nghiệp vụ đặt tại nhau. Trung tâm dữ liệu on-premises có kết nối ExpressRoute. Mỗi chi nhánh có hai đường Internet.

Thông tin giả định:

| Thành phần | Thông số |
|---|---|
| Hà Nội | `10.41.0.0/20`, hai ISP |
| Đà Nẵng | `10.41.16.0/20`, hai ISP |
| TP. Hồ Chí Minh | `10.41.32.0/20`, hai ISP |
| Data center | `10.42.0.0/16` |
| Hub chính Southeast Asia | `10.240.0.0/23` |
| Hub dự phòng Japan East | `10.240.2.0/23` |
| VNet Production | `10.60.0.0/20` |
| VNet DR | `10.61.0.0/20` |

### Nhiệm vụ

1. Chọn loại Virtual WAN phù hợp với S2S VPN, ExpressRoute, VNet connections và multi-hub.
2. Vẽ sơ đồ hai hub, ba sites, data center và hai VNet ứng dụng.
3. Xác nhận mọi CIDR không chồng lấn và chọn hub chính theo khu vực.
4. Mô tả VPN site và hai link cho từng chi nhánh; xác định có sử dụng BGP không.
5. Viết connectivity matrix: chi nhánh → Production, data center → Production, Hà Nội ↔ TP. Hồ Chí Minh, Đà Nẵng ↔ Hà Nội (bị cấm).
6. Mô tả route association/propagation để hỗ trợ các đường được phép và biện pháp firewall để chặn đường không được phép.
7. Nêu cách truy cập hostname nội bộ và private endpoints bằng DNS.
8. Đề xuất failover ISP/tunnel/hub và cách xác minh ứng dụng còn hoạt động.
9. Xây dựng danh sách log, metric, cảnh báo và yếu tố ngân sách cần theo dõi.

### Lời giải tham khảo

**Lựa chọn:** Virtual WAN **Standard** vì cần nhiều kiểu kết nối, VNet transit và multi-hub. Trong cấu hình thật, kiểm tra hỗ trợ của gateway và bảo mật ở các region đã chọn.

**Đường đi chính:** ba VPN sites dùng S2S VPN đến hub Southeast Asia; data center kết nối với hub qua ExpressRoute gateway; VNet Production kết nối hub chính, VNet DR kết nối hub Japan East. Việc định tuyến inter-hub được kiểm chứng cho lưu lượng DR theo đúng thiết kế.

**Routing và phân đoạn:** các chi nhánh được quảng bá các prefix không trùng; route tới Production được phân phối đến các kết nối cần thiết. Đường Hà Nội ↔ TP. Hồ Chí Minh chỉ được phép qua chính sách định tuyến và kiểm tra bảo mật. Đà Nẵng ↔ Hà Nội bị từ chối bằng phân đoạn route và chính sách firewall tương ứng. Không coi route isolation là kiểm soát an ninh đủ mạnh nếu ứng dụng có dữ liệu nhạy cảm.

**Khả năng sẵn sàng:** mỗi site có link dự phòng, theo dõi trạng thái tunnel và tuyến BGP, kiểm thử lỗi một ISP. VNet DR và application DR phải được chuẩn bị độc lập với routing; khi mất region chính, phải xác minh cả ứng dụng và data layer.

**Tiêu chí nghiệm thu:**

- Cả ba chi nhánh vào được ứng dụng Production bằng **hostname** và đúng port.
- Hà Nội và TP. Hồ Chí Minh liên thông theo những dịch vụ được phép.
- Đà Nẵng không truy cập được subnet/dịch vụ nội bộ Hà Nội bị cấm.
- Mất một đường Internet không làm mất toàn bộ truy cập quá thời gian phục hồi được chấp nhận.
- Route chiều đi/chiều về, BGP, firewall logs và DNS đều có bằng chứng.
- Bảng chi phí có các mục hub, gateway, data processing, ExpressRoute, bảo mật và logs.

## 17. Tự kiểm tra kiến thức

**Câu 1.** Vì sao doanh nghiệp có nhiều chi nhánh và VNet ở nhiều region thường chọn Virtual WAN Standard?

A. Vì Basic mặc nhiên có tất cả loại kết nối và hub-to-hub transit.  
B. Vì Standard hỗ trợ mô hình VNet connections, multi-hub và các kiểu kết nối nâng cao theo cấu hình.  
C. Vì Standard làm mọi firewall rule không còn cần thiết.

**Đáp án: B.** Phạm vi tính năng Standard phù hợp các topology phức tạp hơn, nhưng vẫn cần thiết kế route và bảo mật.

**Câu 2.** Định danh nào trong Virtual WAN đại diện cho chi nhánh gồm các subnet LAN và link ISP?

**Đáp án:** **VPN site**. Các link và prefix chi nhánh được khai báo như một phần của mô hình site.

**Câu 3.** Tunnel S2S đã lên nhưng nhân viên không truy cập được ứng dụng bằng hostname. Nên kiểm tra gì?

**Đáp án:** Route hai chiều, BGP/association/propagation, firewall/NSG và đặc biệt **DNS** tại chi nhánh; trạng thái tunnel không bảo đảm truy cập ứng dụng.

**Câu 4.** Hai site có prefix `10.41.0.0/20` và `10.41.8.0/21`. Thiết kế có vấn đề gì?

**Đáp án:** Hai dải chồng lấn vì `10.41.8.0/21` nằm trong `10.41.0.0/20`. Cần quy hoạch lại hoặc có giải pháp xử lý rõ ràng trước khi định tuyến.

**Câu 5.** Khi dùng ExpressRoute, có thể mặc định dữ liệu luôn được mã hóa đầu cuối như VPN IPsec không?

**Đáp án:** Không. ExpressRoute là kết nối riêng qua provider; việc mã hóa cần được xem xét độc lập theo yêu cầu bảo mật.

**Câu 6.** Hai chi nhánh cùng kết nối Virtual WAN có chắc chắn được phép truy cập trực tiếp lẫn nhau không?

**Đáp án:** Không. Điều đó tùy routing, propagation, association và security policies. Cần cấu hình đúng rồi kiểm thử cả luồng được phép và bị cấm.

**Câu 7.** Nếu có hai tunnel nhưng cả hai đi qua một router vật lý, rủi ro gì vẫn tồn tại?

**Đáp án:** Router là một điểm lỗi đơn. Cần đánh giá dự phòng thiết bị, ISP, nguồn và đường vật lý chứ không chỉ số tunnel.

**Câu 8.** Một virtual hub thứ hai ở region khác đã đủ để bảo đảm DR ứng dụng chưa?

**Đáp án:** Chưa. Cần triển khai workload/data layer dự phòng, lập kế hoạch đồng bộ, RTO/RPO, DNS và cơ chế failover thực tế.

Virtual WAN giúp doanh nghiệp **tổ chức nhiều chi nhánh theo một kiến trúc kết nối có thể quản lý tập trung**. Để vận hành đáng tin cậy, nhóm kỹ thuật vẫn phải thiết kế địa chỉ không trùng lấn, route hai chiều, phân đoạn bảo mật, DNS, dự phòng và đo lường lưu lượng. Giá trị của dịch vụ thể hiện rõ nhất khi thêm một chi nhánh mới theo cùng bộ nguyên tắc mà vẫn kiểm soát được đường đi, mức độ truy cập và chi phí.
