# VPC Network Peering và giới hạn truyền tuyến

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích **VPC Network Peering** kết nối hai mạng VPC trong Google Cloud bằng địa chỉ IP nội bộ như thế nào, và phân biệt kết nối trực tiếp với **truyền tuyến bắc cầu (transitive routing)**.
2. Nhận biết route nào được trao đổi mặc định, route nào cần **export/import custom routes**, route nào không thể trao đổi qua peering.
3. Thiết kế kết nối giữa các project dùng dải IP không chồng lấn; kiểm tra trạng thái peering, route nhập/xuất, route thực sự có hiệu lực và quy tắc firewall.
4. Phân tích các giới hạn liên quan đến xung đột CIDR, route priority, Cloud Router, on-premises, IPv6 và quota của **peering group**.
5. Lựa chọn mô hình kết nối phù hợp cho các hệ thống Compute Engine, GKE, Cloud Run, cơ sở dữ liệu, dịch vụ nội bộ và môi trường hybrid.

## 1. Vấn đề thực tế: hai mạng riêng cần liên lạc

Một doanh nghiệp có thể tách Google Cloud thành nhiều project:

- **Project ứng dụng** chạy API Java trên Compute Engine hoặc các workload sử dụng VPC.
- **Project dịch vụ dùng chung** chứa VM xử lý dữ liệu, bộ nhớ đệm hoặc các endpoint nội bộ.
- **Project phân tích** chạy tác vụ truy cập dữ liệu qua kết nối riêng.

Việc tách project hỗ trợ phân quyền IAM, quản trị ngân sách, chia sẻ trách nhiệm và tổ chức tài nguyên. Tuy nhiên, các VM nằm trong **hai mạng VPC khác nhau** không tự động liên lạc qua địa chỉ IP nội bộ chỉ vì hai project thuộc cùng một tổ chức.

**VPC Network Peering** tạo kết nối giữa **hai VPC network** trong Google Cloud. Sau khi hai phía thiết lập peering hợp lệ, chúng có thể trao đổi các loại route được hỗ trợ để tài nguyên ở VPC này gửi gói tin đến dải địa chỉ ở VPC kia bằng đường mạng riêng của Google. Hai VPC vẫn được quản trị độc lập; peering không tự sao chép IAM hay firewall rules.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, kiến thức peering là nền tảng khi thiết kế mạng cho Compute Engine, GKE, Cloud Run kết nối VPC, hệ thống lưu trữ/cơ sở dữ liệu và các đợt phát hành tự động. Thiết kế đúng giúp ứng dụng tìm được đường đi, có khả năng mở rộng và kiểm soát rủi ro bảo mật, độ tin cậy và chi phí.

### Mô hình ban đầu

Giả sử có hai mạng **custom mode VPC** với các dải subnet không chồng lấn:

| Thành phần | Project | VPC | Dải subnet IPv4 minh họa | Mục đích |
|---|---|---|---|---|
| Ứng dụng | app-dev-001 | vpc-app | 10.10.0.0/16 | API và VM ứng dụng |
| Dịch vụ dùng chung | shared-svc-001 | vpc-shared | 10.20.0.0/16 | Cache, backend nội bộ |

Các project ID và CIDR trong bài là **giả định**. Khi triển khai, cần dùng ID và dải mạng thực đã được quy hoạch, đồng thời kiểm tra địa chỉ của tất cả peer hiện tại và những kết nối dự kiến về sau.

~~~mermaid
flowchart LR
    subgraph P1["Project app-dev-001"]
      A["VPC app<br/>10.10.0.0/16<br/>VM ứng dụng"]
    end
    subgraph P2["Project shared-svc-001"]
      B["VPC shared<br/>10.20.0.0/16<br/>Backend nội bộ"]
    end
    A <-->|"VPC Network Peering<br/>subnet routes"| B
~~~

Để ứng dụng gọi backend ở địa chỉ **10.20.x.x**, cần tối thiểu: kết nối peering **ACTIVE**, route đích có hiệu lực, firewall cho phép lưu lượng và dịch vụ đang lắng nghe đúng IP/cổng. Chỉ tạo kết nối peering chưa chứng minh ứng dụng sẽ giao tiếp thành công.

## 2. VPC Network Peering hoạt động ở cấp nào?

### 2.1. Đối tượng kết nối là VPC, không phải subnet đơn lẻ

Một peering connection ghép **hai VPC network**. Theo chính sách route exchange, mạng này học các đường tới subnet của mạng kia. Phạm vi này khác với việc tạo một tunnel VPN giữa hai máy, hay chỉ mở cổng đến một dịch vụ.

Peering có thể được dùng giữa VPC ở **hai project khác nhau**, kể cả khi thuộc những tổ chức Google Cloud khác nhau nếu các chính sách tổ chức cho phép. Mỗi bên quản lý các cấu hình peering của mình.

### 2.2. Hai phía phải khai báo tương ứng

Đối với thao tác tạo peering bằng **gcloud/Console**, quản trị viên VPC A tạo một cấu hình hướng đến VPC B; quản trị viên VPC B tạo một cấu hình tương ứng hướng lại VPC A.

| Trạng thái | Ý nghĩa |
|---|---|
| **INACTIVE** | Chưa có cấu hình phía bên kia tương ứng, hoặc kết nối chưa được thiết lập |
| **ACTIVE** | Hai VPC đã thiết lập kết nối peering |

Một số công cụ hạ tầng như Terraform có thể quản lý cả hai cấu hình trong một quy trình, nhưng không làm thay đổi nguyên tắc hai phía cùng xác nhận kết nối. Trạng thái **ACTIVE** chỉ cho biết quan hệ peering đã thiết lập; vẫn phải kiểm tra hiệu lực route và firewall.

### 2.3. VPC vẫn độc lập về quản trị và bảo mật

- **IAM roles** trên VPC A không được cấp tự động cho quản trị viên VPC B.
- **VPC firewall rules** và **firewall policies** không được đồng bộ qua peering.
- Một firewall rule của VPC A không thể dùng **network tag** hoặc **service account** của VM thuộc VPC B để nhận dạng VM đó theo cách dùng với VM cùng VPC.
- **Compute Engine internal DNS names** do hệ thống tạo trong một VPC không tự được phân giải từ VPC peer. Nếu cần phân giải tên giữa mạng, thiết kế DNS riêng, ví dụ các cơ chế Cloud DNS phù hợp.
- Peering không tự cấp quyền truy cập Google Cloud API, bucket Cloud Storage hay database: những dịch vụ này còn có xác thực, IAM và phương thức kết nối riêng.

## 3. Route exchange là gì?

**Route** xác định đích IP và cách gói tin được chuyển tiếp. Đối với peering, các route có nguồn gốc ở mạng A có thể được **export** từ A và **import** vào B; B làm tương tự ở chiều ngược lại.

~~~mermaid
flowchart LR
    SA["Subnet hoặc custom route<br/>có nguồn gốc ở VPC A"] --> EA["A: export route"]
    EA --> IB["B: import route"]
    IB --> RB{"Route có hiệu lực<br/>ở VPC B?"}
    RB -->|Có| OK["Có đường tới prefix đích"]
    RB -->|Bị loại hoặc bị lấn| NO["Không dùng route đó"]
~~~

**Export** và **import** là hai quyết định từ hai phía. VPC A bật export custom routes **không đủ** nếu VPC B chưa bật import tương ứng. Ngược lại, nếu VPC B bật import nhưng VPC A không export thì B cũng không nhận các custom routes đó.

Phải phân biệt **được quảng bá/được xem là ứng viên nhập** với **được đưa vào bảng route hiệu lực**. Một route có thể xuất hiện trong danh sách incoming nhưng không được sử dụng do trùng hoặc xung đột với route khác.

## 4. Các loại route được trao đổi và những giới hạn bắt buộc

### 4.1. Bảng tổng quan

| Loại route | Mặc định qua peering | Điều kiện/cờ điều khiển | Ghi chú quan trọng |
|---|---|---|---|
| **IPv4 subnet route dùng dải private**: cả primary/secondary ranges | **Luôn export và import** | Không có cờ tắt riêng cho loại này | Các subnet giữa hai VPC peered không được chồng lấn |
| **IPv4 subnet route dùng dải public được sử dụng riêng** (*privately used public IP*) | **Export mặc định**, import **tắt mặc định** | **--export-subnet-routes-with-public-ip** và **--import-subnet-routes-with-public-ip** | Phải phân biệt với địa chỉ public Internet thông thường |
| **IPv6 subnet route**, internal hoặc external | **Không trao đổi trong peering IPv4-only** | Cả hai phía đặt **--stack-type=IPV4_IPV6** | Cần subnet/VM hỗ trợ IPv6 và chính sách tổ chức cho phép |
| **Custom static IPv4 route** không gắn network tag và không có next hop default Internet gateway | **Tắt mặc định** | Bên nguồn **--export-custom-routes**; bên nhận **--import-custom-routes** | Chỉ các next hop và điều kiện route hợp lệ mới được trao đổi |
| **Dynamic IPv4 route** do Cloud Router học | **Tắt mặc định** | Export/import custom routes ở đúng hai phía | Chịu ảnh hưởng dynamic routing mode và giới hạn route |
| **Custom IPv6 static/dynamic route** thuộc loại hỗ trợ | **Tắt mặc định** | Peering dual-stack và export/import custom routes | Kiểm tra loại next hop, region và điều kiện IPv6 |
| **Static route có network tags** | **Không** | Không có cờ để trao đổi | Route gắn tag chỉ có hiệu lực trong phạm vi định nghĩa của nó |
| **Static route dùng next hop default Internet gateway** | **Không** | Không có cờ để trao đổi | Không được xem peering như phương thức chia sẻ default Internet gateway |
| **Policy-based route** | **Không** | Peering không hỗ trợ trao đổi | Cần thiết kế routing thích hợp khác nếu ứng dụng cần |
| **Route đã được nhập từ một VPC peer khác** | **Không** | Không thể bật để xuất lại qua peering | Nền tảng của tính **không truyền tuyến bắc cầu** |

Hai điều thường gây hiểu lầm:

1. **Subnet IPv4 private routes luôn được trao đổi.** Không cần bật **--export-custom-routes** chỉ để VM ở VPC A truy cập subnet private của VPC B.
2. **Custom static/dynamic routes không được trao đổi mặc định.** Việc bật **--export-custom-routes** mới là một nửa điều kiện; mạng nhận vẫn phải bật **--import-custom-routes**.

### 4.2. Khi nào cần custom routes?

Ví dụ VPC B có kết nối Cloud VPN hoặc Cloud Interconnect đến hệ thống on-premises **172.20.0.0/16**. Cloud Router ở B học prefix on-premises và tạo **dynamic route**. Nếu muốn VM ở VPC A đi qua B để đến on-premises, B cần **export custom routes**, A cần **import custom routes**.

Điều này cho phép A dùng **route có nguồn gốc tại B** để đến hệ thống ngoài Google Cloud, với các điều kiện về đường đi và tuyến trả về. Nó **không** có nghĩa B được phép nhận route từ VPC C rồi phát tiếp route đó đến A.

### 4.3. Tại sao không thể bật/tắt từng subnet private route?

VPC Network Peering cung cấp một số công tắc cho **nhóm route** (subnet public sử dụng riêng, custom routes, IPv6). Với các subnet IPv4 private, route được trao đổi mặc định và không có điều khiển export/import cho từng dải riêng lẻ. Nếu cần tách hẳn khả năng nhìn thấy các prefix, phải xem lại **phân đoạn VPC, phương thức kết nối và chính sách mạng** thay vì kỳ vọng một quy tắc import riêng cho một subnet.

## 5. Giới hạn quan trọng nhất: VPC Network Peering không truyền tuyến bắc cầu

Giả sử ba VPC được kết nối:

~~~mermaid
flowchart LR
    A["VPC A<br/>10.10.0.0/16"] <-->|"Peering A–B"| B["VPC B<br/>10.20.0.0/16"]
    B <-->|"Peering B–C"| C["VPC C<br/>10.30.0.0/16"]
    A -.- C
~~~

Khi **A ↔ B** và **B ↔ C** đều ACTIVE:

| Lưu lượng | Có đường đi trực tiếp thông qua các peering đã khai báo? | Tại sao? |
|---|---|---|
| VM A → subnet B | **Có thể** | A nhận subnet routes của B |
| VM B → subnet C | **Có thể** | B nhận subnet routes của C |
| VM A → subnet C **qua B** | **Không** | B không export tiếp peering subnet route nhận từ C cho A |
| VM C → subnet A **qua B** | **Không** | B không export tiếp peering subnet route nhận từ A cho C |
| VM A ↔ C sau khi thêm peering A–C trực tiếp | **Có thể** | Có route exchange trực tiếp, nếu CIDR, firewall và các điều kiện khác hợp lệ |

**Không truyền tuyến** là thuộc tính thiết kế. Không thể khắc phục bằng cách:

- Bật **--export-custom-routes** ở B để cố xuất lại route mà B đã **import từ C**.
- Bật **--import-custom-routes** ở A rồi giả định A sẽ học route của C.
- Chỉ mở firewall cho cả ba VPC.
- Chỉnh route priority nhằm buộc B làm router chuyển tiếp A → C thông qua peering.

Những thao tác đó không làm peering routes trở thành route có nguồn gốc tại B.

### 5.1. Khi cần nhiều VPC giao tiếp với nhau

Cân nhắc các phương án sau theo quy mô và mục tiêu:

| Thiết kế | Trường hợp phù hợp | Đánh đổi cần đánh giá |
|---|---|---|
| **Peering trực tiếp cho từng cặp cần liên lạc** | Ít VPC, chỉ vài quan hệ mạng rõ ràng | Quản lý nhiều kết nối, dải IP, firewall và quota khi số VPC tăng |
| **Shared VPC** | Nhiều project cần dùng chung một mạng được quản trị tập trung | Thay đổi mô hình sở hữu mạng, quyền IAM và quản trị host/service project |
| **Network Connectivity Center (NCC)** | Cần topology hub/spoke hoặc kết nối quy mô lớn theo tính năng NCC hỗ trợ | Cấu hình, quota, chi phí và chính sách riêng của NCC; cần kiểm tra điều kiện route và loại spoke |
| **Private Service Connect (PSC)** | Bên tiêu thụ chỉ cần truy cập một dịch vụ riêng thay vì toàn bộ IP space của VPC | Thiết lập theo service/endpoint; mô hình producer/consumer khác peering |
| **Cloud VPN / Cloud Interconnect** | Kết nối hybrid, multi-cloud hoặc tới mạng bên ngoài Google Cloud | BGP, route advertisement, băng thông, HA và vận hành kết nối |

Không có lựa chọn nào tự bảo đảm quyền truy cập và độ tin cậy: mỗi mô hình vẫn cần IAM, DNS, firewall, route, giám sát và đánh giá chi phí riêng.

## 6. Một ngoại lệ dễ hiểu sai: đi tới on-premises qua VPC trung gian

**Không truyền tuyến giữa các peering** không đồng nghĩa VPC A không thể dùng đường **Cloud VPN/Interconnect của B** để tới mạng on-premises.

Giả sử:

- **VPC A**: subnet 10.10.0.0/16, chạy ứng dụng.
- **VPC B**: subnet 10.20.0.0/16, sở hữu Cloud VPN và Cloud Router.
- **On-premises**: mạng 172.20.0.0/16.
- **A ↔ B**: peering trực tiếp, không có VPC C trong đường đi.

~~~mermaid
flowchart LR
    A["VPC A<br/>10.10.0.0/16"] <-->|"Peering<br/>A import custom route<br/>B export custom route"| B["VPC B<br/>10.20.0.0/16<br/>Cloud Router"]
    B <-->|"Cloud VPN hoặc Interconnect<br/>BGP"| O["On-premises<br/>172.20.0.0/16"]
~~~

Điều kiện cần gồm:

1. **B học 172.20.0.0/16** dưới dạng local dynamic route từ Cloud Router hoặc có local custom route hợp lệ đến on-premises.
2. **B export custom routes**, đồng thời **A import custom routes**, để route 172.20.0.0/16 có thể có hiệu lực trong A.
3. **On-premises có route trở về 10.10.0.0/16**, thường thông qua cấu hình quảng bá prefix phù hợp trên Cloud Router của B. Cloud Router không mặc nhiên quảng bá subnet của peer A đến on-premises theo ý người triển khai.
4. Firewall ở các phía, chính sách định tuyến và kết nối hybrid cho phép đúng luồng.
5. Các mạng dùng dải IP không xung đột; vùng triển khai của các route động phù hợp với dynamic routing mode.

Lúc này A đi được đến **on-premises** vì B export một **local dynamic route** của B. Không phải vì B đang xuất tiếp peering route nhận từ một VPC thứ ba.

Nếu thêm **VPC C** cũng peered với B, cả A và C có thể học route đến **on-premises** qua B theo cấu hình. Nhưng **A vẫn không tự đi được đến subnet C qua B**, bởi subnet C là peering route nhận vào B.

## 7. CIDR không được chồng lấn và quy hoạch IP

### 7.1. Hai subnet peered không được overlap

Google Cloud từ chối tạo peering nếu subnet route có dải địa chỉ trùng, chứa nhau hoặc nằm trong nhau theo quy tắc kiểm tra overlap.

Ví dụ:

| VPC A | VPC B | Có thể peering theo điều kiện IP này? |
|---|---|---|
| 10.10.0.0/16 | 10.20.0.0/16 | **Có thể**, hai prefix tách nhau |
| 10.10.0.0/16 | 10.10.1.0/24 | **Không**, B nằm trong A |
| 10.10.0.0/16 | 10.10.0.0/16 | **Không**, giống nhau |
| 10.10.0.0/24 | 10.10.1.0/24 | **Có thể**, hai /24 không chồng lấn |

Điều này áp dụng cả **primary và secondary IPv4 subnet ranges**. Khi mở rộng VPC đang peered, Google Cloud còn kiểm tra xung đột của subnet mới với các subnet routes đã có liên quan. Bởi vậy đội mạng cần **đăng ký cấp phát CIDR** cho toàn bộ project, kể cả các vùng GKE Pods/Services hoặc dải dự kiến bổ sung.

### 7.2. Vì sao hai auto mode VPC không phù hợp để peering?

Các **auto mode VPC networks** tạo subnet trong tập địa chỉ mặc định có cấu trúc trùng nhau; vì vậy **không thể peering hai auto mode VPC**. Thực hành lâu dài thường dùng **custom mode VPC** với CIDR đã được quy hoạch trước. Nếu peering auto mode với custom mode, vẫn phải kiểm tra dải subnet của custom mode để không gây overlap với dải mà auto mode sử dụng.

### 7.3. Custom routes và subnet routes cũng có quy tắc xung đột

Không chỉ subnet đối subnet: một custom static route ở VPC A có thể cản việc nhập subnet route từ B nếu prefix của nó bằng hoặc nằm trong dải subnet route đó. Ngược lại, một peering custom route cũng không được phép có đích bằng hoặc nằm trong local subnet route của VPC nhận ở các trường hợp Google Cloud quy định.

**Không nên cố giải quyết bằng thay priority** khi xung đột loại route khiến thao tác tạo peering/route bị từ chối. Cần đọc quy tắc route interactions và thay đổi quy hoạch IP hoặc mô hình kết nối.

## 8. Route selection: imported không có nghĩa là được chọn

Google Cloud tính toán **effective routes** dựa trên các route cục bộ, route nhận từ peer, destination prefix, loại route, vùng và cơ chế ưu tiên. Khi chẩn đoán, hãy xem route nào thật sự được sử dụng.

### 8.1. Prefix và nguồn route quan trọng hơn giả định về priority

Ví dụ VPC A có local route phù hợp với một đích, đồng thời nhập một route từ peer. Nếu A đã có route local với cùng đích hoặc đích cụ thể hơn theo quy tắc chọn đường, route nhận từ peer có thể bị bỏ qua.

Một bẫy khác: A peered với B và C; **B và C cùng quảng bá một prefix custom route cụ thể nhất**. Trong một số trường hợp, Google Cloud dùng thuật toán nội bộ để chọn một peer trước khi xét route priority, người dùng **không thể cấu hình kết quả lựa chọn peer đó**. Tránh dựa vào hai peer quảng bá cùng prefix để thiết kế failover có thứ tự theo priority.

### 8.2. Local route, peering route và route từ Cloud Router

| Nguồn | Ví dụ | Điều cần xác minh |
|---|---|---|
| **Local subnet route** | 10.10.0.0/16 thuộc VPC A | Dải subnet thật sự ở A, không overlap |
| **Peering subnet route** | 10.20.0.0/16 từ VPC B | Peering ACTIVE, loại subnet route được phép import |
| **Local static route** | Route tới appliance trong VPC A | Destination và next hop, tag, khả năng xung đột |
| **Peering static route** | Custom route của VPC B | Export/import custom bật đúng chiều; next hop thuộc loại hỗ trợ |
| **Local dynamic route** | Cloud Router A học prefix từ VPN | Regional/global dynamic routing mode và next hop |
| **Peering dynamic route** | Cloud Router B học 172.20.0.0/16; A nhập | Export/import custom, region, route conflict và quota |

Không có nguyên tắc đơn giản “route priority thấp luôn thắng mọi route khác”. Quy tắc chọn route còn phụ thuộc loại route, độ dài prefix và các bước xử lý trước khi so priority. Với sự cố phức tạp, tra tài liệu **VPC route selection order** và xem bảng **Effective routes** thay vì suy từ một cột priority.

### 8.3. Dynamic routing mode ảnh hưởng tuyến động

Cloud Router có thể học tuyến qua BGP, nhưng tuyến động được áp dụng tại những region nào còn phụ thuộc **dynamic routing mode** của VPC đang học tuyến và cách Google Cloud xử lý route động nhập từ peering.

- **Regional dynamic routing**: tuyến học được áp dụng theo phạm vi region được quy định.
- **Global dynamic routing**: cho phép sử dụng tuyến học ở nhiều region theo quy tắc của dịch vụ, có tính đến lựa chọn route và giá trị ưu tiên.

Khi VM ở region khác không đi được đến on-premises dù VM cùng region đi được, hãy kiểm tra **dynamic routing mode**, vùng nhận route, Cloud Router và bảng effective routes tại từng region.

## 9. Quota và giới hạn peering group

VPC Network Peering có **quota theo VPC** và các quota theo **peering group**. Với một VPC X, peering group của X gồm **chính X và những VPC peered trực tiếp với X**; không tự mở rộng sang tất cả VPC có đường kết nối qua nhiều hop.

Ví dụ:

~~~text
VPC A ↔ VPC B ↔ VPC C

Peering group nhìn từ A: {A, B}
Peering group nhìn từ B: {A, B, C}
Peering group nhìn từ C: {B, C}
~~~

### 9.1. Những quota cần quan sát

- **Peerings per network**: số kết nối peering trên mỗi VPC.
- **Subnet ranges per peering group**: số dải subnet cục bộ và từ các peer liên quan.
- **Static routes per peering group**: giới hạn tổng route static theo phạm vi peering group.
- **Dynamic routes per region per peering group**: số tuyến động có thể được lập trình tại mỗi region.

Giá trị quota cụ thể phụ thuộc loại quota, project, region và giới hạn hiệu lực của nhóm peering; **không nên sao chép một con số cố định** vào thiết kế lâu dài. Hãy kiểm tra **IAM & Admin → Quotas & System Limits**, tài liệu VPC quotas và quota metrics của môi trường thật.

### 9.2. Khi vượt quota route có thể xảy ra điều gì?

Một số trường hợp quá giới hạn khiến thao tác bị từ chối. Đặc biệt, khi đạt giới hạn **dynamic routes per region per peering group**, có thể có route động từ peering **không được lập trình vào effective routes** dù kết nối peering vẫn tồn tại. Google Cloud dùng cơ chế nội bộ để loại những peering dynamic routes vượt mức, nên không thể dự đoán chính xác route nào sẽ bị bỏ.

Hậu quả: **peering ACTIVE nhưng một số prefix không truy cập được**. Khi chẩn đoán, phải xem quota, region và các route bị suppress, không chỉ nhìn trạng thái ACTIVE.

### 9.3. Quota và chi phí không phải một khái niệm

VPC Network Peering dùng giá truyền dữ liệu theo chính sách mạng Google Cloud; đường đi riêng không có nghĩa mọi byte truyền giữa hai VPC đều miễn phí. Khi thiết kế kết nối nhiều project và môi trường, ước lượng traffic giữa VPC, vùng địa lý và kết nối hybrid; kiểm tra billing/usage phù hợp. Quota chủ yếu giới hạn số lượng đối tượng hoặc tuyến, **không phải mức trần hóa đơn**.

## 10. Thực hành gcloud: tạo và kiểm tra kết nối A ↔ B

Phần này dùng hai VPC đã tồn tại, các subnet không trùng nhau và quyền quản trị mạng được cấp tương ứng. **Chỉ chạy các lệnh tạo/cập nhật trên môi trường thực hành được phép**.

| Tham số | Giá trị giả định |
|---|---|
| Project A | app-dev-001 |
| VPC A | vpc-app |
| Project B | shared-svc-001 |
| VPC B | vpc-shared |
| Peering ở A | app-to-shared |
| Peering ở B | shared-to-app |
| Region minh họa để quan sát routes | asia-southeast1 |

### Bước 1 — Kiểm tra trước khi tạo

~~~bash
# Đọc thông tin hai VPC; phải thay bằng ID thực
gcloud compute networks describe vpc-app --project=app-dev-001
gcloud compute networks describe vpc-shared --project=shared-svc-001

# Xem subnet và dải IP trước khi đối chiếu overlap
gcloud compute networks subnets list --project=app-dev-001
gcloud compute networks subnets list --project=shared-svc-001

# Xem các peering đang có
gcloud compute networks peerings list --project=app-dev-001
gcloud compute networks peerings list --project=shared-svc-001
~~~

Kiểm tra đủ **primary và secondary IP ranges**; nếu có nhiều VPC peering, rà soát cả các tuyến được nhập từ peer khác và quota của peering group. Xác nhận chính sách tổ chức như **constraints/compute.restrictVpcPeering** có cho phép hai VPC kết nối hay không.

### Bước 2 — Tạo một đầu peering tại VPC A

~~~bash
gcloud compute networks peerings create app-to-shared \
  --project=app-dev-001 \
  --network=vpc-app \
  --peer-project=shared-svc-001 \
  --peer-network=vpc-shared
~~~

Nếu B chưa có cấu hình tương ứng, kết nối chưa ACTIVE. Việc này không nên được xem là lỗi nếu hai đội đang triển khai theo lịch tách biệt.

### Bước 3 — Tạo đầu còn lại tại VPC B

~~~bash
gcloud compute networks peerings create shared-to-app \
  --project=shared-svc-001 \
  --network=vpc-shared \
  --peer-project=app-dev-001 \
  --peer-network=vpc-app
~~~

Các lệnh trên tạo peering **IPv4 theo cấu hình mặc định**, đủ để trao đổi subnet IPv4 private routes trong ví dụ. Nếu muốn thêm custom routes, cấu hình riêng ở hai phía theo phần dưới.

### Bước 4 — Xác nhận ACTIVE

~~~bash
gcloud compute networks peerings list --project=app-dev-001
gcloud compute networks peerings list --project=shared-svc-001

gcloud compute networks describe vpc-app \
  --project=app-dev-001 \
  --format="yaml(peerings)"
~~~

Kiểm tra tên peer, network, project và trạng thái. Sau khi ACTIVE, xem **route thực sự có hiệu lực** trước khi chạy kiểm thử connectivity.

### Bước 5 — Kiểm tra route import/export

~~~bash
# Từ góc nhìn VPC A: các route là ứng viên nhập từ B
gcloud compute networks peerings list-routes app-to-shared \
  --project=app-dev-001 \
  --network=vpc-app \
  --region=asia-southeast1 \
  --direction=incoming

# Từ góc nhìn VPC A: các route xuất từ A sang B
gcloud compute networks peerings list-routes app-to-shared \
  --project=app-dev-001 \
  --network=vpc-app \
  --region=asia-southeast1 \
  --direction=outgoing
~~~

**Quan trọng:** kết quả **list-routes** là danh sách **route exports và import candidates**; lệnh này không đánh giá hết các trường hợp xung đột khi Google Cloud quyết định route cuối cùng. Để biết route nào được sử dụng hoặc bị suppress, mở **VPC Network → Routes → Effective routes** trong Console và chọn VPC/region cần xem.

### Bước 6 — Kiểm tra firewall và connectivity

Giả sử ứng dụng VM ở A cần kết nối TCP/443 đến dịch vụ ở B. Quản trị viên B cần tạo **ingress allow rule** phù hợp chỉ cho dải nguồn 10.10.0.0/16, đến những VM/đích thích hợp; quản trị viên A cần kiểm tra egress rules và các chính sách áp dụng.

Ví dụ firewall minh họa ở VPC B (chỉ triển khai sau khi xác nhận danh sách máy nhận dịch vụ):

~~~bash
gcloud compute firewall-rules create allow-app-to-shared-https \
  --project=shared-svc-001 \
  --network=vpc-shared \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:443 \
  --source-ranges=10.10.0.0/16 \
  --target-tags=shared-https
~~~

Rule trên chọn **target VM trong chính VPC B** có network tag **shared-https**; **source-ranges** biểu diễn IP nguồn VPC A. Không thử dùng tag của VM ở A làm source tag của firewall rule tại B vì tag không được nhận diện xuyên VPC theo cách đó.

Kiểm tra từ một VM A được phép đến **địa chỉ nội bộ thật** của backend B, sau đó đối chiếu:

1. DNS/địa chỉ đích có đúng không?
2. Route tới prefix của B có hiệu lực tại nơi gói tin xuất phát?
3. Firewall ingress ở B và egress ở A có cho phép?
4. Backend có lắng nghe TCP/443, chứng chỉ hoặc chính sách xác thực phù hợp?
5. Nếu vẫn lỗi, **Connectivity Tests**, VPC Flow Logs (nếu bật) và log ứng dụng có ghi nhận nguyên nhân không?

## 11. Thực hành custom routes: cho VPC A đi tới on-premises qua B

Trong ví dụ này, **VPC B đã có Cloud VPN/Interconnect và Cloud Router**, đồng thời đã học route tới **172.20.0.0/16**. Ta chỉ minh họa thao tác peering; **không tạo VPN/Cloud Router tự động**.

### Bước 1 — B export custom routes

~~~bash
gcloud compute networks peerings update shared-to-app \
  --project=shared-svc-001 \
  --network=vpc-shared \
  --export-custom-routes
~~~

### Bước 2 — A import custom routes

~~~bash
gcloud compute networks peerings update app-to-shared \
  --project=app-dev-001 \
  --network=vpc-app \
  --import-custom-routes
~~~

### Bước 3 — Kiểm chứng ở A

~~~bash
gcloud compute networks peerings list-routes app-to-shared \
  --project=app-dev-001 \
  --network=vpc-app \
  --region=asia-southeast1 \
  --direction=incoming
~~~

Sau đó kiểm tra **Effective routes** tại region có VM A. Prefix **172.20.0.0/16** phải được lựa chọn hợp lệ, không bị loại bởi conflict hoặc quota. Nếu thiếu, xem Cloud Router ở B có học tuyến hay không, B có export không, A có import không, dynamic routing mode và các route suppression.

### Bước 4 — Không quên tuyến trả về

On-premises phải biết đường về **10.10.0.0/16**. Nếu dùng Cloud Router với custom advertisement, cấu hình để Cloud Router của B quảng bá các prefix được phê duyệt của A đến mạng on-premises. Đảm bảo router on-premises nhận và dùng tuyến trở lại, policy cho phép và firewall ở cả hai phía hợp lệ.

**Kiểm thử đầy đủ phải đi cả hai chiều**. Nhìn thấy route đi ở VPC A chưa chứng minh máy on-premises có route trả về hoặc quyền kết nối tương ứng.

### Bước 5 — Nếu hai phía cùng cần custom routes

Chỉ khi cần chia sẻ custom routes **cả hai chiều**, cả hai bên mới đồng thời cấu hình **--export-custom-routes** và **--import-custom-routes**. Không nên bật rộng khi chỉ cần một chiều; việc nhập thêm prefix có thể làm thay đổi effective routes và tăng mức sử dụng quota.

## 12. Các giới hạn ngoài route exchange

### 12.1. IPv6 phải được bật đúng cách

Peering mặc định có **stack type IPv4-only**. Muốn trao đổi IPv6 subnet routes, cả hai phía cần cấu hình dual-stack (**IPV4_IPV6**) và các subnet/VM phải có địa chỉ IPv6 phù hợp. Muốn trao đổi **IPv6 custom routes** còn cần bật export/import custom routes ở đúng chiều.

~~~bash
# Minh họa cập nhật phía A
gcloud compute networks peerings update app-to-shared \
  --project=app-dev-001 \
  --network=vpc-app \
  --stack-type=IPV4_IPV6

# Minh họa cập nhật phía B
gcloud compute networks peerings update shared-to-app \
  --project=shared-svc-001 \
  --network=vpc-shared \
  --stack-type=IPV4_IPV6
~~~

Không áp dụng thao tác này nếu chưa kiểm tra chính sách IPv6 của tổ chức, các CIDR và loại subnet, quy tắc firewall và quyền quản trị.

### 12.2. DNS không tự lan truyền qua peering

Một máy A truy cập được IP **10.20.0.5** nhưng không phân giải được tên nội bộ do Compute Engine tạo cho VM B là tình huống có thể gặp. Đó là vấn đề **DNS**, không phải bằng chứng peering không trao đổi route.

Nếu cần dùng tên dịch vụ chung, thiết kế Cloud DNS private zones, DNS peering hoặc chính sách phân giải phù hợp theo phạm vi hệ thống. Không giả định peering tự chia sẻ mọi tên máy hoặc mọi private zone.

### 12.3. Không tự chia sẻ Internet egress hoặc Cloud NAT

Static route trỏ đến **default Internet gateway** không được export qua VPC Network Peering. Không nên kỳ vọng một VPC có Cloud NAT hay Internet gateway sẽ tự làm cổng ra Internet cho peer chỉ vì đã peering.

Nếu kiến trúc cần egress tập trung, phải đánh giá các mô hình định tuyến, appliance, load balancing, NAT và sản phẩm mạng hỗ trợ cụ thể. Đây là một bài toán khác với việc trao đổi subnet routes mặc định.

### 12.4. Tên peering giống nhau không có nghĩa chung một policy

Hai phía có cấu hình riêng và cờ route exchange riêng. Việc một bên đổi **import custom routes** hoặc **stack type** có thể làm thay đổi khả năng liên lạc. Nên quản lý bằng IaC, review và cảnh báo drift thay vì chỉ dựa vào thao tác Console thủ công.

## 13. Chẩn đoán: peering ACTIVE nhưng không thông mạng

| Triệu chứng | Nguyên nhân hay gặp | Kiểm tra thực tế |
|---|---|---|
| Không tạo được peering | CIDR subnet overlap, policy tổ chức cấm peer, sai tên mạng/project | Dải primary/secondary, **restrictVpcPeering**, đối tượng VPC |
| Peering mãi **INACTIVE** | Thiếu cấu hình đối ứng hoặc cấu hình trỏ sai network | Cả hai đầu peering, project và VPC |
| ACTIVE nhưng A không tới subnet B | Firewall, route xung đột, sai đích IP, workload không lắng nghe | Effective routes, firewall, connectivity test |
| A đến B được, A đến C qua B thất bại | **Peering không bắc cầu** | Đối chiếu topology; không mong B tái export peering route C |
| A không đi được on-prem qua B | B chưa export custom, A chưa import, B chưa học route, thiếu tuyến về | BGP/Cloud Router, incoming routes, effective routes, return route |
| Một region truy cập on-prem được, region khác không | Dynamic routing mode và route applicability theo region | Effective routes của từng region, Cloud Router |
| list-routes thấy prefix nhưng traffic vẫn sai | Imported route là ứng viên nhưng bị suppress hoặc chọn route khác | Console **Effective routes**, trạng thái suppression, conflict |
| Mất một số prefix sau khi thêm peer | Quota peering group hoặc route conflicts | Quota metrics, dynamic routes per region, peering group |
| VM dùng IP truy cập được nhưng tên không phân giải | DNS nội bộ không tự chia sẻ qua peering | DNS configuration, private zones, DNS peering |
| Bật export/import custom mà Internet không đi qua B | Default Internet gateway route không được trao đổi | Kiến trúc egress/NAT, loại next hop của route |
| Tưởng tag/SA của VM A dùng được trong firewall B | Network tags/service accounts không được tham chiếu xuyên VPC | Source IP range, target tag nội bộ của B, chính sách riêng |
| Bật IPv6 nhưng không có route IPv6 | Một phía chưa dual-stack, subnet IPv6 thiếu, policy cản | Stack type cả hai, IPv6 subnet và effective route |

### Quy trình điều tra theo từng lớp

1. **Topology:** dữ liệu phải đi A→B hay A→C qua B? Nếu cần bắc cầu, dừng và thiết kế lại.
2. **IP:** hai prefix có overlap? Local subnet và custom route có xung đột?
3. **Peering:** hai phía ACTIVE? Các tùy chọn export/import đúng theo loại route?
4. **Routing:** prefix có xuất hiện trong incoming? Có được chọn trong **effective routes** tại đúng region?
5. **Quota:** dynamic/static routes hoặc peering group đã đạt ngưỡng chưa?
6. **Security:** firewall ingress/egress, authentication và policy của dịch vụ đích.
7. **End-to-end:** DNS, listener, route trở về, log và phép thử ứng dụng.

Một thay đổi cần có **kết quả kiểm thử trước/sau**. Đừng vội bật toàn bộ custom routes hoặc nới firewall 0.0.0.0/0 để làm cho phép thử qua được.

## 14. Tình huống thiết kế: mạng dịch vụ chung, dữ liệu và on-premises

Doanh nghiệp **An Khang** có:

- **VPC app**, 10.10.0.0/16: API bán hàng trên VM và một số workload Cloud Run kết nối VPC.
- **VPC shared**, 10.20.0.0/16: backend nội bộ; Cloud Router kết nối on-premises 172.20.0.0/16.
- **VPC analytics**, 10.30.0.0/16: workload xử lý dữ liệu riêng.

Nhóm yêu cầu:

1. API app gọi backend trong shared qua IP riêng.
2. Analytics gọi backend trong shared, nhưng **không cần** truy cập app.
3. Cả app và analytics cần truy cập một hệ thống on-premises đã đi qua Cloud VPN của shared.
4. Tất cả liên lạc phải có chính sách firewall, logging và trách nhiệm quản trị rõ ràng.

### 14.1. Topology đề xuất cho yêu cầu hiện tại

~~~mermaid
flowchart LR
    APP["VPC app<br/>10.10.0.0/16"] <-->|"Peering"| SH["VPC shared<br/>10.20.0.0/16<br/>Cloud Router"]
    AN["VPC analytics<br/>10.30.0.0/16"] <-->|"Peering"| SH
    SH <-->|"VPN / BGP"| ON["On-premises<br/>172.20.0.0/16"]
    APP -.- AN
~~~

Trong mô hình:

- App và analytics đều học **subnet routes private** của shared, nên có thể kết nối backend B nếu firewall cho phép.
- Shared học các subnet app và analytics qua **hai peering trực tiếp**.
- Shared có thể export **local dynamic route** đến 172.20.0.0/16 cho app và analytics. Mỗi mạng nhận cần import custom routes.
- Cloud Router tại shared quảng bá **các prefix app và analytics** cần thiết đến on-premises theo quy tắc và route advertisement phù hợp; firewall và BGP phải cho phép phản hồi.
- App và analytics **không tự liên lạc trực tiếp qua shared**. Điều này phù hợp yêu cầu cách ly hiện tại.

### 14.2. Bảng kiểm chứng trước production

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Các subnet app/shared/analytics không overlap | PASS |
| Hai peering app–shared và analytics–shared ACTIVE | PASS |
| App → backend shared; analytics → backend shared | Thành công theo cổng được phép |
| App → analytics qua shared | **Không có route peering bắc cầu** |
| Prefix on-premises trong app/analytics effective routes | Có khi cấu hình custom route đúng |
| On-premises → prefix app/analytics | Có tuyến trả về và firewall hợp lệ |
| Tài nguyên trong mỗi project tách IAM | Không phát sinh cấp quyền xuyên project |
| Quota route/peering group tại shared còn dung lượng | Có dự phòng mở rộng |
| Cloud Monitoring/VPC logs và kiểm thử kết nối | Có người chịu trách nhiệm nhận lỗi |
| Ước tính traffic giữa VPC và on-premises | Được đưa vào dự toán chi phí |

### 14.3. Nếu yêu cầu thay đổi thành “app phải nói chuyện analytics”

Lựa chọn đơn giản với số VPC ít là tạo **peering app–analytics trực tiếp** sau khi kiểm tra CIDR, quota và firewall. Nếu số VPC tăng mạnh hoặc cần kiến trúc kết nối trung tâm có truyền tuyến theo chính sách, cân nhắc **NCC/Shared VPC/PSC** tùy loại workload và phạm vi truy cập, thay vì cố biến B thành điểm transit bằng peering.

## 15. Bài tập thực hành

### Bài tập A — Dự đoán route exchange

Có ba VPC:

| VPC | Subnet route | Custom route |
|---|---|---|
| A | 10.1.0.0/16 | Không có |
| B | 10.2.0.0/16 | Dynamic 172.16.40.0/24 học từ Cloud VPN |
| C | 10.3.0.0/16 | Không có |

Peering **A–B**, **B–C** ACTIVE, nhưng **A–C không peering**. B export custom routes ở cả hai kết nối; A và C import custom routes.

**Hãy trả lời:**

1. A có học subnet route 10.2.0.0/16 của B không?
2. A có tự học subnet route 10.3.0.0/16 của C qua B không?
3. A có thể học 172.16.40.0/24 không? Ngoài route đi, cần kiểm tra điều gì để liên lạc được với on-premises?
4. Nếu B tắt export custom routes, A có còn đường đến 172.16.40.0/24 qua peering không?
5. Nếu A và C muốn nói chuyện trực tiếp, có những phương án kiến trúc nào?

**Đáp án định hướng:** (1) Có, với subnet IPv4 private và không xung đột; (2) Không, vì peering không bắc cầu; (3) Có thể, nếu dynamic route của B đủ điều kiện và không bị loại, kèm route trả về, firewall, BGP/region; (4) Không thông qua custom route exchange này; (5) peering trực tiếp A–C hoặc đánh giá mô hình mạng khác phù hợp.

### Bài tập B — Tìm lỗi trong thay đổi production

Một kỹ sư ghi trong change request:

> “Hai peering đã ACTIVE. Tôi bật export custom ở B, mọi subnet của C sẽ được export qua B sang A. Không cần kiểm tra firewall và route trả về vì peering là hai chiều.”

Chỉ ra ít nhất **bốn lỗi** trong lập luận và viết lại kế hoạch kiểm chứng.

**Gợi ý:** cần phân biệt route của B với route nhận từ C, kiểm tra import ở A, hiệu lực route theo region, firewall của mỗi VPC, tuyến trả về của mạng đích, xung đột prefix và quota. Tính hai chiều của quan hệ peering không có nghĩa mọi tuyến custom được trao đổi hai chiều hay toàn bộ dịch vụ tự mở.

### Bài tập C — Viết lệnh kiểm tra

Với peering **app-to-shared** trong VPC **vpc-app**, project **app-dev-001** và region **asia-southeast1**, hãy viết:

1. Lệnh liệt kê peering trong project.
2. Lệnh xem network và peering state.
3. Lệnh liệt kê các **incoming route candidates**.
4. Vị trí trong Console để xem **effective routes** và route bị suppress.
5. Cách kiểm tra vì sao prefix **172.20.0.0/16** không có hiệu lực.

**Gợi ý:** dùng **gcloud compute networks peerings list**, **gcloud compute networks describe**, **gcloud compute networks peerings list-routes ... --direction=incoming**; sau đó kiểm tra effective routes, Cloud Router, export/import custom, dynamic routing mode, route conflict và quota.

## 16. Ghi nhớ và tài liệu tham khảo

**Những nguyên tắc cần nhớ:**

1. VPC Network Peering kết nối **hai VPC**; mỗi phía có cấu hình quản trị riêng và cần peering **ACTIVE**.
2. **Subnet IPv4 private routes được trao đổi mặc định**; **custom static/dynamic routes** chỉ được trao đổi nếu phía nguồn export và phía nhận import phù hợp.
3. **Peering không bắc cầu**: A–B và B–C không cho phép A đi tới C qua B bằng route exchange; B không được export tiếp route đã nhập từ C.
4. **IPv6, privately used public IPv4, tagged static routes, default Internet gateway và policy-based routes** có quy tắc khác nhau; không giả định mọi route đều được chia sẻ.
5. **CIDR overlap, route conflict, quota peering group, dynamic routing mode và firewall** có thể khiến peering ACTIVE nhưng traffic vẫn thất bại.
6. **List-routes là danh sách xuất/ứng viên nhập**, còn **Effective routes** cho biết route thực sự được dùng hoặc bị suppress.
7. Nếu cần đi tới on-premises qua một peer, phải có **custom route hợp lệ cùng đường trở về**; điều này khác với transit giữa ba VPC qua peering.

**Tài liệu Google Cloud chính thức:**

1. [VPC Network Peering — Overview, routes and limitations](https://docs.cloud.google.com/vpc/docs/vpc-peering) — nguyên tắc peering, route exchange, non-transitivity và route interactions.
2. [Set up and manage VPC Network Peering](https://docs.cloud.google.com/vpc/docs/using-vpc-peering) — lệnh gcloud tạo, cập nhật và liệt kê incoming/outgoing routes.
3. [About peering connections](https://docs.cloud.google.com/vpc/docs/about-peering-connections) — trạng thái ACTIVE/INACTIVE và quản lý hai phía.
4. [VPC routes](https://docs.cloud.google.com/vpc/docs/routes) — phân loại route, route selection và xung đột route.
5. [VPC quotas and limits](https://docs.cloud.google.com/vpc/docs/quota) — peering group, static/dynamic route limits và quota hiệu lực.
6. [VPC network overview](https://docs.cloud.google.com/vpc/docs/overview) — so sánh VPC Network Peering và Shared VPC.
