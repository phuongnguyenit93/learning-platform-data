# Kiến trúc VPC toàn cục và subnet theo region

Trong Google Cloud, một hệ thống có thể phục vụ người dùng từ nhiều khu vực, chạy Compute Engine ở một region, GKE ở region khác, Cloud Run kết nối với dịch vụ nội bộ và Cloud SQL lưu dữ liệu tại vị trí được phép. Để các thành phần giao tiếp có kiểm soát, cần hiểu rõ **Virtual Private Cloud (VPC) là tài nguyên toàn cục (global)** nhưng **subnet thuộc một region cụ thể (regional)**.

Đây là nền tảng của chương **VPC và định tuyến** trong module **CLOUD_PROVIDERS_GCP**. Khi hiểu mô hình này, bạn sẽ có thể thiết kế mạng theo môi trường, phân bổ địa chỉ IP hợp lý, phân tích đường đi của gói tin, bảo vệ tài nguyên bằng quy tắc tường lửa, và dự toán ảnh hưởng của kết nối liên region đến độ trễ, độ tin cậy cùng chi phí.

**Mục tiêu học tập**

1. Giải thích được vì sao một VPC có thể chứa nhiều subnet ở các region khác nhau, trong khi từng subnet chỉ thuộc một region.
2. Phân biệt VPC, subnet, NIC của VM, địa chỉ IP, route, firewall, Cloud Router và các dịch vụ kết nối mạng.
3. Thiết kế dải IPv4 cho nhiều môi trường, GKE, VM và dịch vụ managed mà không bị chồng lấn.
4. Mô tả cách lưu lượng đi giữa các subnet cùng VPC, qua VPC Peering, qua VPN/Interconnect và ra Internet.
5. Kiểm tra một thiết kế mạng qua Console hoặc gcloud CLI và nêu được rủi ro về bảo mật, khả dụng, vận hành, chi phí.

## 1. VPC toàn cục: phạm vi logic của một mạng riêng

**VPC network** là một mạng ảo được quản lý ở cấp Google Cloud project và có phạm vi **global**. Một VPC có thể chứa nhiều subnet thuộc các region khác nhau mà không cần tạo một VPC mới cho mỗi region. Các tài nguyên trong VPC dùng định tuyến, chính sách mạng và không gian địa chỉ theo cấu hình của mạng đó.

**Global** trong định nghĩa này mô tả *phạm vi của tài nguyên VPC*, không có nghĩa mọi VM, địa chỉ IP hay dữ liệu ứng dụng đều tự động được nhân bản toàn cầu. VM vẫn thuộc zone; subnet vẫn thuộc region; dịch vụ managed có quy tắc gắn mạng và vị trí riêng.

| Thành phần | Phạm vi | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| **VPC network** | Global | \`prod-vpc\` | Mạng ảo có thể kết nối subnet ở nhiều region. |
| **Subnet (subnetwork)** | Regional | \`prod-app-sg\` tại \`asia-southeast1\` | Dải địa chỉ IP được dùng trong một region của VPC. |
| **Compute Engine VM** | Zonal | VM ở \`asia-southeast1-b\` | Giao diện mạng sử dụng subnet thuộc region của zone đó. |
| **Static internal IPv4 address** | Thường gắn với phạm vi regional/subnet tương ứng | IP nội bộ của VM | Phải thuộc dải và quy tắc cấp phát của subnet liên quan. |
| **Firewall rules của VPC** | Được định nghĩa trên VPC (global đối với các VPC firewall rules truyền thống) | Quy tắc cho phép TCP đến một nhóm VM | Có thể tác động tới các VM mục tiêu ở nhiều region; cần đặt target và nguồn phù hợp. |
| **Route trong VPC** | Là thành phần định tuyến của mạng VPC | Subnet route, static route, dynamic route | Xác định next hop hoặc cách gửi lưu lượng; hiệu lực của từng loại route có quy tắc riêng. |
| **Cloud Router** | Regional | Router ở \`asia-southeast1\` | Trao đổi thông tin định tuyến động với mạng kết nối; phạm vi quảng bá/học route phụ thuộc routing mode. |

> Cần phân biệt **quản trị toàn cục** với **hạ tầng chạy tại một vị trí**. VPC là global; tạo VM trong VPC không khiến VM chạy ở nhiều region, và cùng VPC không loại bỏ rủi ro mất một region.

### 1.1. Quan hệ giữa VPC, subnet và VM

Giả sử có một VPC \`prod-vpc\` với hai subnet:

~~~mermaid
flowchart TB
    subgraph VPC["VPC prod-vpc — phạm vi global"]
      subgraph SG["Region asia-southeast1"]
        SGA["Subnet prod-app-sg<br/>10.20.0.0/20"]
        VM1["VM tại zone asia-southeast1-b<br/>10.20.0.10"]
        VM2["VM tại zone asia-southeast1-c<br/>10.20.0.11"]
        SGA --- VM1
        SGA --- VM2
      end
      subgraph JP["Region asia-northeast1"]
        JPA["Subnet prod-app-jp<br/>10.40.0.0/20"]
        VM3["VM tại một zone của region<br/>10.40.0.10"]
        JPA --- VM3
      end
    end
    SGA -. "Lưu lượng nội bộ xuyên region<br/>theo route và chính sách" .- JPA
~~~

Trong sơ đồ:

- Hai subnet cùng thuộc **một VPC** nhưng thuộc **hai region khác nhau**.
- VM ở những zone khác nhau của **cùng region** có thể dùng cùng một subnet regional nếu cấu hình VM phù hợp.
- VM thuộc region khác **không** gắn NIC trực tiếp vào subnet của region Singapore; nó cần subnet thuộc region của VM.
- Các subnet có dải IP khác nhau, không chồng lấn trong cùng VPC.
- Việc có đường định tuyến nội bộ **không tự bảo đảm** VM giao tiếp được: quy tắc firewall, chính sách tổ chức và firewall/hệ điều hành ở máy còn có thể chặn lưu lượng.

### 1.2. Một VPC không đồng nghĩa một zone hoặc một subnet

Đây là hai nhầm lẫn phổ biến:

**Nhầm lẫn 1:** “Subnet theo region nên muốn chạy đa region phải tạo nhiều VPC.” Không đúng. Một VPC có thể chứa các subnet riêng biệt tại mỗi region cần triển khai.

**Nhầm lẫn 2:** “VPC global nên chỉ cần một subnet dùng cho toàn thế giới.” Không đúng. Một subnet gắn với *một region*; không thể dùng cùng một subnet regional làm subnet trực tiếp của VM ở region khác.

Thay vì xem subnet là một mạng con kéo dài qua mọi region, hãy nghĩ về VPC như **khung kết nối logic chung**, còn subnet là **phần không gian địa chỉ được cấp phát cho một vùng cụ thể**.

## 2. Hai chế độ tạo subnet: auto mode và custom mode

Khi tạo VPC, Google Cloud có hai chế độ subnet IPv4:

| Chế độ | Cách subnet được tạo | Phù hợp với |
| --- | --- | --- |
| **Auto mode** | Google Cloud tự tạo subnet với dải IPv4 đã quy định ở các region được hỗ trợ; có thể tự thêm subnet ở region mới theo cơ chế sản phẩm. | Thử nghiệm hoặc làm quen khi không cần kiểm soát chặt sơ đồ địa chỉ. |
| **Custom mode** | Người thiết kế chủ động tạo subnet theo region, dải IPv4 và secondary ranges cần dùng. | Hầu hết thiết kế production, multi-region, hybrid cloud, GKE và mạng cần phối hợp địa chỉ. |

Auto mode sử dụng sơ đồ địa chỉ riêng được Google Cloud thiết kế sẵn. Việc tạo một VPC auto mode có thể làm phát sinh subnet ngoài những region thực sự dùng, làm tăng xác suất xung đột dải IP khi kết nối với mạng doanh nghiệp. Khi cần kiểm soát mạng và IP, **custom mode** thường dễ quản lý hơn.

VPC auto mode có thể được chuyển thành custom mode; việc chuyển đổi ngược lại không phải thao tác tương đương, tự do áp dụng cho bất kỳ VPC custom mode nào. Trước khi thay đổi chế độ của mạng đang sử dụng, phải kiểm tra giới hạn sản phẩm và các kết nối hiện có.

### 2.1. Quy hoạch primary và secondary IPv4 ranges

Mỗi subnet có một **primary IPv4 range**. Tùy thiết kế, subnet có thể có **secondary IPv4 ranges**, chẳng hạn để cấp IP cho Pod và Service trong cụm GKE VPC-native.

Ví dụ một kế hoạch địa chỉ:

| Môi trường/region | Subnet | Primary range | Secondary ranges (khi cần) |
| --- | --- | --- | --- |
| Production, Singapore | \`prod-app-sg\` | \`10.20.0.0/20\` | \`10.21.0.0/16\` cho Pod; \`10.22.0.0/20\` cho Service |
| Production, Tokyo | \`prod-app-jp\` | \`10.40.0.0/20\` | Thiết kế riêng nếu có GKE tại Tokyo |
| Development, Singapore | \`dev-app-sg\` trên VPC dev riêng | \`10.60.0.0/20\` | Dải phụ chỉ tạo khi nhu cầu xuất hiện |

Các địa chỉ là **ví dụ học tập**. Khi áp dụng thật, phải đối chiếu với mạng doanh nghiệp qua VPN/Interconnect, mạng VPC được peering, các mạng quản trị, vị trí dịch vụ managed và kế hoạch tăng trưởng.

Những nguyên tắc đáng nhớ:

1. **Không chồng lấn dải IPv4** giữa primary và secondary subnet ranges trong cùng VPC. Khi kết nối giữa các VPC hoặc với on-premises, phải kiểm tra thêm xung đột địa chỉ trên những mạng định kết nối.
2. **Dự trữ khả năng tăng trưởng:** IP cho VM, node GKE, Pod, Service và các dịch vụ khác có cách cấp phát khác nhau. Dải IP nhỏ có thể cản trở mở rộng, ngay cả khi CPU hoặc quota còn đủ.
3. **Không suy từ kích thước CIDR ra chính xác số IP dùng được:** Google Cloud dành lại các địa chỉ trong mỗi primary IPv4 range cho chức năng hệ thống; số IP dùng được còn phụ thuộc loại tài nguyên.
4. **Ưu tiên dải địa chỉ private phù hợp:** chẳng hạn RFC 1918 IPv4 khi dùng cho các ứng dụng thông thường; một số dải và chức năng đặc biệt có điều kiện riêng.
5. **Có sơ đồ IP cấp tổ chức:** thể hiện VPC, môi trường, region, subnet, secondary ranges, mạng peering và kết nối hybrid, cùng người chịu trách nhiệm phê duyệt.

### 2.2. Phân bổ IP là quyết định lâu dài

Nếu đặt các subnet gần hết địa chỉ ngay khi thiết kế, hệ thống sẽ khó mở rộng instance group, cluster GKE hoặc các nhóm máy cần IP nội bộ. Một số thao tác mở rộng primary IPv4 range của subnet được hỗ trợ theo điều kiện; **không nên mặc định có thể dễ dàng thu nhỏ, đổi dải hoặc di chuyển toàn bộ IP mà không ảnh hưởng tài nguyên**.

Ví dụ, subnet dành cho node GKE không có secondary Pod range đủ lớn có thể giới hạn số node/Pod. Khi quy hoạch, cần xem cơ chế cấp phát Pod IP theo cluster mode, số Pod/node, các dải GKE cho Service và kế hoạch nâng cấp, thay vì chỉ ước lượng từ số node ban đầu.

## 3. Định tuyến trong VPC toàn cục hoạt động như thế nào?

**Route** xác định nơi gửi lưu lượng dựa trên địa chỉ đích và những thuộc tính được hệ thống định tuyến xét tới. Trong một VPC, route có thể đến từ subnet, cấu hình tĩnh, cơ chế động hoặc các đường đi được sản phẩm kết nối cung cấp.

### 3.1. Subnet routes tự động

Khi tạo subnet, Google Cloud tự tạo các **subnet routes** để nhận biết dải địa chỉ của subnet trong VPC. Nhờ đó, các VM tại những subnet khác nhau **trong cùng VPC** có đường định tuyến nội bộ tới địa chỉ nội bộ tương ứng, kể cả khi subnet nằm ở các region khác nhau.

~~~mermaid
flowchart LR
    A["VM A<br/>10.20.0.10"] --> S1["Subnet Singapore<br/>10.20.0.0/20"]
    S1 --> R["Định tuyến nội bộ của VPC"]
    R --> S2["Subnet Tokyo<br/>10.40.0.0/20"]
    S2 --> B["VM B<br/>10.40.0.10"]
    F["Firewall / network policy"] -. "Có thể cho phép hoặc chặn" .-> R
~~~

Đường đi này **không cần VPN hoặc VPC Peering** vì cả hai subnet đã ở cùng một VPC. Lưu lượng được xử lý bằng hạ tầng mạng của Google Cloud, nhưng truyền dữ liệu giữa các region vẫn có độ trễ và có thể phát sinh phí. Luôn đối chiếu quy tắc giá và tình huống cụ thể.

Nếu VM A muốn kết nối TCP đến VM B, cần đủ các yếu tố:

- VM B có IP đích chính xác và dịch vụ đang lắng nghe.
- Có route hiệu lực tới dải đích.
- Quy tắc VPC firewall và chính sách mạng liên quan cho phép lưu lượng đến VM B (và egress nếu bị giới hạn).
- Firewall của hệ điều hành hoặc của ứng dụng không chặn cổng.

**Có route không đồng nghĩa được phép truy cập.** Routing quyết định *đi về đâu*, firewall và các lớp ủy quyền quyết định *có được đi hay không*.

### 3.2. Routes và firewall là hai lớp độc lập

| Thành phần | Câu hỏi giải quyết | Ví dụ |
| --- | --- | --- |
| Route | Gói tin gửi tới next hop hoặc đích mạng nào? | Đích \`10.40.0.0/20\` đi tới subnet ở Tokyo. |
| VPC firewall rule / firewall policy | Lưu lượng có được cho phép dựa trên hướng, nguồn, đích, giao thức, cổng và đối tượng mục tiêu không? | Chỉ cho phép TCP 5432 từ nhóm VM ứng dụng tới nhóm cơ sở dữ liệu cần thiết. |
| Network tag / service account target | Firewall rule nhắm tới VM nào? | Target một nhóm VM backend thay vì toàn bộ VPC. |
| IAM | Ai được quyền quản lý cấu hình mạng, hoặc gọi API Google Cloud? | Nhóm mạng được sửa firewall, nhóm app chỉ xem cấu hình. |
| Quy tắc ứng dụng/hệ điều hành | Tiến trình có chấp nhận yêu cầu không? | PostgreSQL cần xác thực người dùng và quyền trong database. |

VPC firewall rules truyền thống có phạm vi mạng và có thể tác động đến các VM mục tiêu ở nhiều region; chúng không tự tách chính sách chỉ vì bạn tạo hai subnet tại hai region. Vì vậy phải chủ động giới hạn **source**, **target**, cổng và ứng dụng. Một số khả năng firewall nâng cao có cấp độ và cơ chế áp dụng khác, cần chọn đúng sản phẩm.

### 3.3. Static routes, default route và dynamic routes

Ngoài subnet routes, bạn có thể gặp:

- **Static routes:** cấu hình tĩnh đích và next hop cho những mục đích như đưa traffic qua thiết bị mạng ảo (appliance) hoặc đường kết nối được hỗ trợ.
- **Default route:** thường là đường đích \`0.0.0.0/0\` với next hop là default Internet gateway, tùy cấu hình mạng. Route này **không tự cấp IP công khai** hoặc bảo đảm mọi VM có thể ra Internet.
- **Dynamic routes:** được học/trao đổi qua **Cloud Router** từ các kết nối được hỗ trợ như Cloud VPN hoặc Cloud Interconnect và có phạm vi hiệu lực phụ thuộc dynamic routing mode.

Trong Google Cloud, **Cloud Router là regional**, còn VPC có cài đặt **dynamic routing mode**. Với chế độ **regional** hoặc **global**, phạm vi mà các dynamic routes được áp dụng và thông tin được quảng bá qua BGP sẽ khác nhau. Cần đọc tài liệu định tuyến động hiện hành khi triển khai hybrid hoặc nhiều region; không suy rằng vì VPC global thì mọi dynamic route đều tự xuất hiện ở tất cả region.

Subnet routes khác static routes do người quản trị tạo: subnet routes được hệ thống quản lý theo subnet, không phải đối tượng để xóa tùy ý mà vẫn giữ subnet hoạt động bình thường.

## 4. Lưu lượng nội bộ và Internet: những dịch vụ phải phân biệt

Địa chỉ nội bộ của VM, đường đi ra Internet và kết nối đến dịch vụ Google Cloud là những nhu cầu khác nhau. Đặt VM trong subnet chỉ là bước đầu của thiết kế.

### 4.1. Private IP, external IP và Cloud NAT

VM có thể có IP nội bộ trong subnet mà **không có external IP**. Đây là lựa chọn phổ biến cho backend hoặc máy xử lý không cần nhận kết nối trực tiếp từ Internet. Tuy nhiên, nếu VM cần tải bản cập nhật từ một kho công khai hoặc gọi API ngoài Google Cloud, phải có đường egress thích hợp.

**Cloud NAT** có thể cung cấp cơ chế dịch địa chỉ cho các kết nối outbound đủ điều kiện từ những tài nguyên không có external IP. Với Public NAT, thiết kế Cloud NAT gắn với **region**, **Cloud Router** và những subnet/dải IP được chỉ định. Cloud NAT không tự tạo endpoint công khai để Internet chủ động mở kết nối inbound tới VM.

~~~mermaid
flowchart LR
    VM["VM không có external IP<br/>subnet region A"] --> RT["Đường egress hợp lệ"]
    RT --> NAT["Public Cloud NAT<br/>region A"]
    NAT --> NET["Dịch vụ Internet bên ngoài"]
    USER["Người dùng Internet"] -. "Không tự tạo kết nối inbound qua NAT" .-> VM
~~~

Cloud NAT khác với tường lửa: việc dịch địa chỉ hoặc có default route chưa đủ nếu chính sách egress chặn traffic. Tương tự, Cloud NAT regional tại region A **không mặc nhiên** phục vụ trực tiếp tài nguyên nằm ở region B; cần xem cấu hình NAT, phạm vi subnet và sản phẩm phù hợp từng region.

### 4.2. Private Google Access

**Private Google Access** là một khả năng cho tài nguyên đủ điều kiện, chẳng hạn VM chỉ có IP nội bộ, truy cập các Google APIs và dịch vụ được hỗ trợ thông qua đường đi mà sản phẩm cho phép. Thiết lập này liên quan tới subnet và còn phụ thuộc DNS, routing và firewall.

Private Google Access **không biến mọi trang Internet thành dịch vụ nội bộ**. Ví dụ, cho phép truy cập một số API Google Cloud không đồng nghĩa VM có thể tải thư viện từ một website bên ngoài mà không cần đường Internet egress khác. Cần kiểm tra tình huống truy cập \`private.googleapis.com\`, \`restricted.googleapis.com\` hoặc các cơ chế sản phẩm tương ứng nếu tổ chức áp dụng yêu cầu dữ liệu/mạng nghiêm ngặt.

### 4.3. Cloud Run và GKE sử dụng VPC khác nhau

- **Compute Engine:** VM có NIC gắn với subnet thích hợp trong region của zone nơi VM chạy.
- **GKE:** cluster và node sử dụng mạng VPC theo mô hình triển khai; với **VPC-native**, địa chỉ Pod và Service thường được tổ chức bằng secondary ranges, với các chi tiết cấp phát tùy cấu hình GKE.
- **Cloud Run:** Cloud Run là dịch vụ serverless theo region. **Không nên hình dung container Cloud Run là VM có NIC thường trực trong subnet.** Khi cần egress đến địa chỉ nội bộ trong VPC, có các cơ chế như **Direct VPC egress** hoặc **Serverless VPC Access connector** theo tính năng/region được hỗ trợ.
- **Cloud SQL:** có thể cung cấp đường kết nối private theo cấu hình; cần kiểm tra **private services access**, cơ chế kết nối và vùng dữ liệu. Không mặc định tạo subnet VPC là Cloud SQL tự xuất hiện trong dải subnet đó.

Ví dụ: một Cloud Run service ở Singapore cần gọi database qua private IP. Cần xác định dịch vụ hỗ trợ cách kết nối VPC nào, cấu hình mạng egress trong region phù hợp, quy tắc firewall, định tuyến, và cách truy cập private IP của database. Nếu service đặt tại region khác, độ trễ và chi phí lưu lượng xuyên region trở thành yếu tố thiết kế.

## 5. Một VPC nhiều region khác gì nhiều VPC kết nối với nhau?

Không phải mọi nhóm ứng dụng đều phải nằm trong cùng một VPC. Khi có yêu cầu cô lập môi trường, chia trách nhiệm, kết nối với doanh nghiệp hoặc tách các vùng tin cậy, người thiết kế cần chọn cấu trúc mạng phù hợp.

| Mô hình | Điểm mạnh | Điều kiện và hạn chế |
| --- | --- | --- |
| **Một VPC, nhiều subnet theo region** | Thiết kế mạng logic chung; có subnet routes tự động cho các dải thuộc VPC; dễ tổ chức kết nối giữa các ứng dụng thuộc cùng miền quản trị. | Phải kiểm soát firewall xuyên region, quy hoạch IP chung và tác động của quyền quản trị VPC. |
| **Nhiều VPC độc lập** | Cô lập địa chỉ, cấu hình mạng và trách nhiệm quản trị rõ hơn. | Mặc định không có kết nối IP nội bộ trực tiếp giữa các VPC; tích hợp cần một giải pháp kết nối. |
| **VPC Network Peering** | Kết nối IP nội bộ giữa hai VPC theo quy tắc peering; giữ VPC riêng. | Không có tính bắc cầu (non-transitive), cần kiểm tra dải IP, trao đổi route, quota và firewall ở cả hai bên. |
| **Shared VPC** | VPC và subnet được quản trị tập trung trong **host project**, trong khi tài nguyên thuộc các **service projects** được ủy quyền có thể sử dụng mạng chung. | Cần thiết lập quyền, liên kết host/service project, quy trình quản trị và tổ chức phù hợp; không làm project trở thành một project duy nhất. |
| **Cloud VPN / Cloud Interconnect** | Kết nối với hệ thống bên ngoài Google Cloud hoặc những mạng cần đường truyền chuyên dụng. | Cần cấu hình kết nối, BGP/route, bảo mật, HA, vùng và chi phí; không giống kết nối subnet tự động trong cùng VPC. |

### 5.1. Khi nào một VPC xuyên region là hợp lý?

Ví dụ công ty quản lý chung hệ thống ứng dụng nội bộ, chỉ có một nhóm mạng chịu trách nhiệm và muốn chạy dự phòng tại Singapore và Tokyo. Một VPC custom mode có hai subnet regional giúp:

1. Phân bổ địa chỉ theo từng region trong một sơ đồ thống nhất.
2. Kết nối nội bộ giữa những workload cùng VPC mà không phải xây dựng peering riêng giữa chính hai subnet đó.
3. Áp chính sách firewall và vận hành mạng nhất quán, đồng thời phân biệt target/source theo nhóm workload.
4. Thêm subnet mới khi có region phục vụ người dùng mới, sau khi đối chiếu IP, bảo mật và chi phí.

Tuy vậy, chung VPC có thể tạo **phạm vi ảnh hưởng quản trị lớn**: một thay đổi firewall hoặc cấu hình route sai có thể ảnh hưởng nhiều region. Cần tách quyền IAM và áp quy trình review mạng.

### 5.2. Khi nào nên tách VPC?

Tách VPC thường hợp lý nếu các môi trường có mức độ tin cậy khác biệt, tổ chức vận hành độc lập, yêu cầu kiểm soát egress khác nhau hoặc cần cô lập rủi ro cấu hình. Ví dụ, môi trường nghiên cứu thử nghiệm nhận mã từ bên ngoài không nên tự nhiên được xem như cùng miền tin cậy với ứng dụng chứa dữ liệu production.

Không nên nhầm **tách project** với **tách mạng**. Hai project có thể dùng chung mạng qua Shared VPC; ngược lại, một project có thể chứa nhiều VPC độc lập. Quyền IAM, firewall, các luồng kết nối và phân loại dữ liệu phải được xác định cụ thể.

### 5.3. Shared VPC cho nhiều project

Một kiến trúc doanh nghiệp có thể trông như sau:

~~~mermaid
flowchart TB
    O["Organization"]
    O --> H["Host project: net-prod<br/>quản trị Shared VPC"]
    O --> S1["Service project: checkout-prod"]
    O --> S2["Service project: catalog-prod"]
    H --> V["Shared VPC global"]
    V --> A["Subnet app-sg — region A"]
    V --> B["Subnet app-jp — region B"]
    S1 -. "Sử dụng subnet được cấp quyền" .-> A
    S2 -. "Sử dụng subnet được cấp quyền" .-> B
~~~

Hạ tầng mạng thuộc host project; workload có thể nằm trong service project. Nhóm quản trị mạng kiểm soát subnet/route/firewall theo quyền được giao, trong khi nhóm phát triển chỉ được triển khai tài nguyên lên subnet thích hợp. Đây là cách **tách nhiệm vụ** giữa quản trị mạng và quản trị workload, nhưng vẫn giữ một sơ đồ địa chỉ và mạng chung.

Shared VPC không thay thế các nguyên tắc bảo mật. Người được phép tạo VM trên một subnet không nên được tự động sửa toàn bộ firewall của VPC hoặc cấp quyền mạng cho người khác.

### 5.4. VPC Peering và giới hạn chuyển tiếp

Khi hai VPC có peering, các subnet của chúng có thể được định tuyến qua kết nối peering theo các điều kiện được hỗ trợ. Nhưng nếu:

- VPC A peering với VPC B;
- VPC B peering với VPC C;

thì **không có nghĩa A có kết nối tới C thông qua B**. VPC Network Peering không hoạt động như một router bắc cầu tự động giữa mọi VPC. Hệ thống cần kết nối A↔C phải được thiết kế với một mô hình kết nối phù hợp và kiểm tra đầy đủ chính sách bảo mật.

Cần kiểm tra **độ chồng lấn IP** trước khi thiết lập peering. Không thể dựa vào firewall để sửa một sơ đồ định tuyến có các dải mạng không tương thích. Firewall của hai mạng cũng không được xem là một policy tự động chia sẻ sau khi peering.

## 6. Thiết kế mạng theo độ trễ, khả dụng và chi phí

Kiến trúc VPC global không biến mọi lưu lượng xuyên region thành giao tiếp cục bộ. Với workload thời gian thực, chọn vị trí subnet/ứng dụng cần cân bằng cả đường dữ liệu và mục tiêu phục hồi.

### 6.1. Đặt thành phần thường gọi nhau ở vị trí phù hợp

Giả sử frontend ở Singapore, API ở Singapore nhưng database ở Tokyo. Hai vùng có thể giao tiếp trong cùng VPC qua private IP nếu route/firewall đúng, song các truy vấn tuần tự xuyên region vẫn phát sinh thời gian truyền mạng. Nếu API gọi database nhiều lần trong một yêu cầu, độ trễ được cộng dồn.

Một thiết kế phù hợp có thể đặt API gần database cho các tác vụ cần giao tiếp liên tục, sau đó phân phối traffic đến người dùng theo mô hình load balancing thích hợp. Điều này cần được kiểm chứng bằng **p95/p99 đầu cuối** và số lần gọi giữa dịch vụ, thay vì chỉ đo ping giữa hai VM.

### 6.2. Dự phòng zone và region

Subnet có phạm vi regional nên có thể được dùng bởi VM ở các zone khác nhau trong cùng region. Nhờ đó, một nhóm VM phân tán nhiều zone trong cùng region có thể cùng hoạt động trên subnet phù hợp.

Mất cả region là loại sự cố khác: việc VPC tồn tại global không tự di chuyển VM, GKE node hay dữ liệu sang region khác. Muốn khôi phục ở region B, thường phải chuẩn bị:

- Subnet và dải IP đủ lớn tại region B; quy tắc firewall và đường kết nối phù hợp.
- Compute/GKE/Cloud Run, load balancer hoặc thành phần chuyển traffic theo thiết kế.
- Cơ chế sao lưu/nhân bản dữ liệu, điều kiện tuân thủ vị trí dữ liệu.
- Quy trình khởi động dịch vụ dự phòng, cấu hình IAM, secret, quota và giám sát.
- Kiểm thử **RTO** (thời gian khôi phục) và **RPO** (mức mất dữ liệu tối đa) theo nhu cầu nghiệp vụ.

**VPC global hỗ trợ tổ chức kết nối multi-region; nó không tự tạo hệ thống ứng dụng multi-region có khả dụng cao.**

### 6.3. Nhận biết chi phí mạng

Một VPC không thu phí chỉ vì tồn tại theo cùng một cách với VM chạy liên tục, nhưng lưu lượng và các dịch vụ mạng liên quan có thể phát sinh chi phí:

| Thành phần | Hạng mục cần dự toán |
| --- | --- |
| Truyền dữ liệu giữa region | Lưu lượng giữa backend, database, replication hoặc backup; xem bảng giá theo hướng và dịch vụ cụ thể. |
| Cloud NAT | Phí theo cấu hình và dữ liệu được xử lý tùy loại NAT, cùng chi phí dữ liệu outbound liên quan. |
| Load balancing | Chi phí thành phần cân bằng tải, quy tắc/processing và dữ liệu theo sản phẩm cụ thể. |
| Cloud VPN / Interconnect | Phí tunnel/attachment, truyền dữ liệu, địa điểm và cấu hình dự phòng. |
| Logging, Flow Logs, monitoring | Dung lượng log/metric và phí lưu trữ, xử lý hoặc phân tích theo cấu hình. |

Không suy rằng IP nội bộ trong một VPC sẽ miễn phí truyền dữ liệu giữa các region. Phải đọc bảng giá hiện hành và đo traffic thực tế theo chiều, vị trí, loại kết nối.

## 7. Ví dụ tạo VPC custom mode và subnet regional bằng gcloud

Phần này trình bày một bài thực hành có thể áp dụng trong project thử nghiệm được cấp quyền. **Các lệnh tạo VPC, subnet là thao tác ghi có thể phát sinh cấu hình mạng**; chỉ chạy trong project được phép và sau khi kiểm tra dải IP với sơ đồ mạng hiện có. Trong ví dụ, ta thiết kế một VPC dành cho production, có subnet tại Singapore và Tokyo.

### 7.1. Xác định sơ đồ trước khi tạo

Giả định:

| Tham số | Giá trị ví dụ |
| --- | --- |
| Project | \`PROJECT_ID\` — thay bằng project ID thực |
| VPC | \`prod-vpc\`, subnet mode = custom |
| Dynamic routing mode | Regional, vì ví dụ chưa cần trao đổi BGP toàn vùng |
| Subnet tại Singapore | \`prod-app-sg\` — \`asia-southeast1\` — \`10.20.0.0/20\` |
| Secondary range cho GKE tại Singapore | \`pods\` = \`10.21.0.0/16\`; \`services\` = \`10.22.0.0/20\` |
| Subnet tại Tokyo | \`prod-app-jp\` — \`asia-northeast1\` — \`10.40.0.0/20\` |

Sơ đồ dành cho mục đích học tập, không hàm ý hai region này là lựa chọn phù hợp cho mọi doanh nghiệp. Cần kiểm tra dịch vụ có hỗ trợ vị trí, yêu cầu lưu trú dữ liệu, chi phí và quota trước khi triển khai thật.

### 7.2. Tạo một VPC global

~~~bash
# Chọn đúng project thử nghiệm (thay PROJECT_ID bằng giá trị thật)
gcloud config set project PROJECT_ID

# Tạo VPC custom mode, không yêu cầu Google Cloud tự tạo subnet
gcloud compute networks create prod-vpc \
  --subnet-mode=custom \
  --bgp-routing-mode=regional
~~~

VPC \`prod-vpc\` là tài nguyên global. Tại thời điểm vừa tạo, **custom mode không tự sinh subnet regional**; bạn cần tạo từng subnet tại những region dự kiến sử dụng.

### 7.3. Tạo subnet tại Singapore

~~~bash
gcloud compute networks subnets create prod-app-sg \
  --network=prod-vpc \
  --region=asia-southeast1 \
  --range=10.20.0.0/20 \
  --secondary-range=pods=10.21.0.0/16,services=10.22.0.0/20 \
  --enable-private-ip-google-access
~~~

Ý nghĩa:

- \`--network=prod-vpc\`: subnet thuộc VPC toàn cục đã tạo.
- \`--region=asia-southeast1\`: xác định phạm vi regional của subnet.
- \`--range=10.20.0.0/20\`: primary IPv4 range dành cho tài nguyên được cấp IP chính từ subnet.
- \`--secondary-range=...\`: hai dải phụ đã đặt tên, có thể được sử dụng cho cấu hình GKE phù hợp.
- \`--enable-private-ip-google-access\`: bật tính năng Private Google Access tương ứng cho subnet; hiệu quả thực tế còn phụ thuộc cấu hình DNS, route, firewall và dịch vụ đích.

Tạo secondary range **chưa tạo cluster GKE** và chưa tự phân bổ Pod. Việc ánh xạ range vào cluster cần thực hiện khi cấu hình cluster VPC-native theo tài liệu GKE.

### 7.4. Tạo subnet tại Tokyo

~~~bash
gcloud compute networks subnets create prod-app-jp \
  --network=prod-vpc \
  --region=asia-northeast1 \
  --range=10.40.0.0/20
~~~

Subnet Tokyo vẫn thuộc **cùng mạng \`prod-vpc\`**, nhưng có primary range riêng và là tài nguyên của region \`asia-northeast1\`.

### 7.5. Kiểm tra bằng lệnh chỉ đọc

~~~bash
# Mạng VPC và chế độ subnet / định tuyến
gcloud compute networks describe prod-vpc

# Danh sách subnet trong project và region tương ứng
gcloud compute networks subnets list

# Chi tiết subnet Singapore
gcloud compute networks subnets describe prod-app-sg \
  --region=asia-southeast1

# Các route mà lệnh Compute Engine routes list có thể hiển thị
gcloud compute routes list

# Các VPC firewall rules trong project
gcloud compute firewall-rules list
~~~

Hãy xác minh \`prod-app-sg\` và \`prod-app-jp\` đều tham chiếu \`prod-vpc\`, nhưng có region và primary range riêng. Đồng thời xem subnet routes đã được tạo tự động tương ứng với dải IP của các subnet.

Không nên coi \`gcloud compute routes list\` là ảnh chụp đầy đủ của mọi **dynamic route** hiệu lực trong tất cả trường hợp. Khi có Cloud Router/BGP, phải sử dụng thêm thông tin trạng thái Cloud Router, cấu hình peer, dynamic routing mode và công cụ kiểm thử kết nối phù hợp.

### 7.6. Cần cấu hình firewall trước khi thử giao tiếp

Trong custom VPC mới, các **implied firewall rules** vẫn có hiệu lực theo cơ chế của Google Cloud: ingress bị từ chối nếu không có quy tắc cho phép phù hợp, còn egress được cho phép theo mặc định trừ khi có quy tắc hoặc chính sách ưu tiên khác. Không nên lấy các quy tắc có sẵn của **default VPC** làm giả định cho custom VPC do mình tạo.

Nếu muốn VM ở hai subnet trao đổi qua TCP, cần thiết kế rule cho phép có giới hạn:

- Nguồn nào được kết nối? Ví dụ chỉ dải của application subnet tại Singapore.
- Đích nào được nhận? Ví dụ các VM database có service account hoặc network tag được chỉ định.
- Cổng và giao thức nào? Ví dụ TCP 5432 cho một ứng dụng PostgreSQL, nếu đó đúng là cổng được dùng.
- Giao tiếp có thực sự cần xuyên region không? Nếu chỉ cần sao chép dữ liệu, có thể chọn cơ chế managed replication riêng.
- Có policy cấp tổ chức, rule deny, firewall của hệ điều hành hoặc cơ chế phân quyền ứng dụng nào ngăn kết nối không?

Không tạo quy tắc ingress \`0.0.0.0/0\` cho tất cả các cổng chỉ để “xác minh mạng chạy được”. Quyền truy cập cần giới hạn theo nhóm workload thực sự cần giao tiếp.

## 8. Phân tích một số lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Không chọn được subnet Singapore khi tạo VM ở Tokyo | Subnet regional; VM ở zone Tokyo không dùng subnet thuộc Singapore. | Kiểm tra zone của VM, region của subnet; tạo/chọn subnet thuộc cùng region. |
| Không tạo được subnet vì dải IP chồng lấn | Primary/secondary CIDR xung đột với dải trong cùng VPC hoặc vi phạm điều kiện sản phẩm. | Kiểm tra toàn bộ subnet ranges trước khi chọn địa chỉ khác. |
| Hai VM khác subnet cùng VPC không kết nối TCP được | Firewall ingress/egress, OS firewall, dịch vụ chưa lắng nghe, sai IP hoặc policy. | Xem route, effective firewall policies, port và cấu hình tiến trình; thử Connectivity Tests khi được hỗ trợ. |
| VM không có external IP không truy cập Internet được | Thiếu đường egress/NAT, default route, DNS, firewall hoặc cấu hình NAT sai region/subnet. | Kiểm tra mục tiêu truy cập, Public NAT, Cloud Router/NAT, route, firewall và DNS. |
| VM không có external IP gọi Google APIs thất bại | Private Google Access chưa bật hoặc DNS/route/firewall/API permission chưa phù hợp. | Kiểm tra cấu hình subnet, DNS cho miền dịch vụ, đường đi và IAM/service account. |
| Route học từ VPN có ở một region nhưng không có hiệu lực tại region khác | Dynamic routing mode hoặc cấu hình Cloud Router/BGP chưa đáp ứng yêu cầu. | Kiểm tra chế độ regional/global, BGP advertisements và learned routes. |
| Peering A↔B, B↔C nhưng A không tới C | Peering không bắc cầu tự động. | Thiết kế kết nối A↔C hoặc giải pháp truyền tải/định tuyến phù hợp. |
| GKE tăng node nhưng không tăng được số Pod | Thiếu IP ở secondary Pod range hoặc giới hạn cấp phát/quota. | Kiểm tra kích thước dải Pod, thiết lập số Pod/node và năng lực mở rộng được hỗ trợ. |
| VPC global nhưng dịch vụ vẫn ngừng khi region lỗi | VM, cluster, database hoặc backend còn chạy duy nhất tại region gặp sự cố. | Thiết kế dự phòng workload, dữ liệu, lưu lượng và kiểm thử DR riêng. |
| Phí mạng tăng khi thêm region | Lưu lượng giữa region, backup/replication, NAT, load balancer hoặc VPN phát sinh thêm. | Phân tích billing theo dịch vụ và chiều dữ liệu; đo traffic thực tế. |

### 8.1. Trình tự điều tra một luồng mạng bị lỗi

Với kết nối \`VM-A → VM-B\`, hãy đi theo thứ tự:

1. **Xác định nguồn và đích:** Project ID, VPC, subnet, region, zone, địa chỉ IP, cổng, protocol và dịch vụ lắng nghe.
2. **Kiểm tra đường đi:** VM có NIC đúng VPC/subnet không? Dải đích có subnet route hoặc route được hỗ trợ không? Có dynamic routing mode liên quan không?
3. **Kiểm tra chính sách:** Firewall rules/policies, network tags/service accounts, hướng ingress/egress và thứ tự ưu tiên.
4. **Kiểm tra phía đích:** VM đang chạy, ứng dụng lắng nghe trên IP/cổng đúng, firewall hệ điều hành, database user và xác thực nếu cần.
5. **Quan sát bằng công cụ:** VPC Flow Logs, Firewall Rules Logging, Connectivity Tests hoặc những log của dịch vụ đang được hỗ trợ/cấu hình.
6. **Kiểm tra sau khi sửa:** Chỉ cho phép đúng luồng mong muốn, rồi kiểm thử rằng những đích không được cấp phép vẫn bị chặn.

**VPC Flow Logs** có phạm vi, chế độ thu thập và chi phí phụ thuộc cấu hình; log có thể lấy mẫu, không nên mặc định là bản ghi đầy đủ của mọi packet. **Connectivity Tests** giúp phân tích đường đi dự kiến và một số tình huống kiểm thử thực tế theo tính năng hiện hành; kết quả phải được đối chiếu với trạng thái ứng dụng đích.

## 9. Bài thực hành: thiết kế mạng cho nền tảng học trực tuyến

Một công ty triển khai nền tảng học Java lên Google Cloud:

- Người học chủ yếu ở Đông Nam Á, nhưng có nhóm truy cập từ Nhật Bản.
- API chạy trên Cloud Run; job nền có thể chạy trên Compute Engine hoặc GKE.
- Dữ liệu học tập được lưu trong Cloud SQL và Cloud Storage theo chính sách vị trí dữ liệu.
- Hệ thống cần tách môi trường dev và prod, có dự phòng một phần khi region chính gặp sự cố.
- Nhóm mạng muốn quản lý dải IP và policy tập trung; nhóm ứng dụng chịu trách nhiệm triển khai.

**Yêu cầu 1 — Vẽ kiến trúc.** Chọn một trong hai phương án: một VPC production có subnet tại hai region; hoặc Shared VPC cho các service project. Giải thích phạm vi **global** của VPC, **regional** của subnet, và vị trí của VM/GKE/Cloud Run.

**Yêu cầu 2 — Quy hoạch địa chỉ.** Dùng dải IPv4 riêng không chồng lấn cho subnet ứng dụng của từng region, thêm dải Pod/Service nếu chọn GKE VPC-native. Dự trữ IP cho mức tăng trưởng gấp đôi; ghi rõ lý do chọn kích thước CIDR và giới hạn cần kiểm chứng.

**Yêu cầu 3 — Đường đi của gói tin.** Với một VM tại Singapore gọi VM khác tại Tokyo, ghi rõ route, chính sách firewall, nơi có thể phát sinh độ trễ/phí mạng. Trả lời có cần VPN hay VPC Peering cho hai subnet cùng VPC không.

**Yêu cầu 4 — Egress.** Một VM không có external IP cần gọi Google Cloud API và một kho mã bên ngoài Internet. Đề xuất riêng giải pháp cho từng nhu cầu; phân biệt Private Google Access với Cloud NAT.

**Yêu cầu 5 — Khả dụng.** Mô tả điều gì xảy ra nếu một zone Singapore lỗi, và điều gì xảy ra nếu cả Singapore region lỗi. Nêu rõ tại sao chỉ có VPC global và subnet tại Tokyo chưa đủ để đảm bảo API/DB dự phòng hoạt động.

**Yêu cầu 6 — An toàn và vận hành.** Chỉ định nhóm được quản lý VPC/firewall, nhóm được triển khai workload trên subnet và nhóm được đọc Flow Logs. Đề xuất ba ca kiểm thử bảo mật kết nối trước khi đưa hệ thống lên production.

### Gợi ý đánh giá

Một phương án có cơ sở khi chứng minh được:

- VPC global có thể phục vụ nhiều region; mỗi subnet regional có CIDR rõ ràng và không chồng lấn.
- VM gắn subnet đúng region; GKE và Cloud Run được kết nối theo cách mà từng sản phẩm hỗ trợ.
- Route nội bộ và firewall được phân biệt; không dùng quy tắc cho phép rộng toàn VPC chỉ để giải quyết lỗi.
- Egress Internet được thiết kế có chủ đích; Private Google Access không được nhầm là đường ra Internet tổng quát.
- Thiết kế dự phòng giải quyết cả workload, dữ liệu, IAM, quota, traffic, RTO/RPO và vị trí lưu trữ, ngoài sơ đồ mạng.
- Độ trễ, băng thông, lưu lượng xuyên region và chi phí được đo/ước tính từ workload đại diện.

### Câu hỏi tự kiểm tra

**1. VPC có phạm vi toàn cục, vậy một subnet có thể chứa VM từ hai region không?**  
Không. Một subnet thuộc một region; các VM trong những zone thuộc cùng region có thể dùng subnet đó nếu cấu hình phù hợp.

**2. Hai subnet ở hai region trong cùng một VPC có phải tạo peering để giao tiếp IP nội bộ không?**  
Không. VPC có subnet routes để định tuyến giữa các dải subnet; quyền truy cập thực tế vẫn phụ thuộc firewall và các lớp khác.

**3. Cloud Router đặt ở một region có nghĩa dynamic routes luôn tự hoạt động ở mọi region trong VPC không?**  
Không. Cần xét dynamic routing mode regional/global, cách học/quảng bá route và các giới hạn được hỗ trợ.

**4. Bật Cloud NAT có cho phép người dùng Internet chủ động kết nối đến VM không có external IP không?**  
Không. Public Cloud NAT phục vụ những luồng egress đủ điều kiện và traffic phản hồi; nó không phải dịch vụ công bố endpoint inbound.

**5. Chuyển từ một subnet sang hai subnet regional đã tạo được tính sẵn sàng multi-region chưa?**  
Chưa. Phải triển khai/nhân bản workload và dữ liệu, điều chỉnh traffic, kiểm thử failover và đáp ứng mục tiêu RTO/RPO.

## Tài liệu Google Cloud tham khảo

- **VPC networks:** https://cloud.google.com/vpc/docs/vpc — khái niệm VPC, subnet mode, địa chỉ và phạm vi global/regional.
- **VPC subnets:** https://cloud.google.com/vpc/docs/subnets — primary/secondary ranges, giới hạn, Private Google Access và thao tác subnet.
- **VPC routes:** https://cloud.google.com/vpc/docs/routes — subnet routes, static routes và dynamic routes.
- **VPC firewall rules:** https://cloud.google.com/firewall/docs/firewalls — mô hình kiểm soát traffic và nguyên tắc firewall.
- **Cloud Router:** https://cloud.google.com/network-connectivity/docs/router/concepts/overview — BGP và định tuyến động cho kết nối mạng.
- **Cloud NAT:** https://cloud.google.com/nat/docs/overview — hành vi NAT, tính regional và kết nối outbound.
- **Shared VPC:** https://cloud.google.com/vpc/docs/shared-vpc — host/service project và phân quyền dùng mạng.
- **VPC Network Peering:** https://cloud.google.com/vpc/docs/vpc-peering — kết nối VPC và các giới hạn về route/địa chỉ.
- **Private Google Access:** https://cloud.google.com/vpc/docs/private-google-access — khả năng truy cập Google APIs và yêu cầu mạng.
- **VPC Flow Logs:** https://cloud.google.com/vpc/docs/using-flow-logs — quan sát lưu lượng mạng.
- **Network Connectivity Tests:** https://cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview — phân tích đường đi và kiểm tra kết nối.
- **Network pricing:** https://cloud.google.com/vpc/network-pricing — tra cứu bảng giá và các trường hợp tính phí.

Quy tắc địa chỉ, danh sách region hỗ trợ, hành vi dynamic routing, các lựa chọn kết nối serverless và chi phí có thể thay đổi. Khi triển khai thật, cần đối chiếu tài liệu theo sản phẩm, kiểm tra chính sách tổ chức và thử nghiệm đường đi thực tế trước khi đưa hệ thống vào phục vụ người dùng.
