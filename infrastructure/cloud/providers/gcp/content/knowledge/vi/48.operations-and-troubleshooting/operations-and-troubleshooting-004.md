# Chẩn đoán kết nối bằng Connectivity Tests và Network Intelligence Center

Trong module `CLOUD_PROVIDERS_GCP`, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Chương **Vận hành và xử lý sự cố** giúp biến cấu hình mạng thành bằng chứng có thể kiểm tra, để đội vận hành tìm được điểm packet bị chặn và phân biệt lỗi network với lỗi ứng dụng.

Bài này hướng dẫn sử dụng **Connectivity Tests** và các công cụ trong **Network Intelligence Center** để điều tra kết nối giữa VM, GKE, Cloud Run, load balancer, Cloud SQL, mạng on-premises và Internet. Bạn sẽ chạy một bài test TCP, đọc trace từng bước, đối chiếu firewall/route, kiểm tra giới hạn của live data plane analysis và phối hợp Network Analyzer, Network Topology, Firewall Insights, Flow Analyzer cùng Performance Dashboard.

## 1. Tình huống thực tế và mục tiêu

Giả sử hệ thống Java gồm:

- `orders-api` chạy trên Compute Engine VM trong VPC `orders-vpc`.
- PostgreSQL trên Cloud SQL sử dụng private IP.
- Một nhóm worker trong GKE truy cập API nội bộ qua TCP 8080.
- Mạng văn phòng kết nối với VPC qua Cloud VPN hoặc Cloud Interconnect.

Một bản phát hành mới khiến request từ VM tới API timeout. Nhóm ứng dụng cho rằng firewall đã chặn; nhóm mạng cho rằng ứng dụng không mở port. Thay vì thay đổi rule ngay, đội vận hành cần trả lời:

1. Source endpoint thực sự là VM/interface/IP nào?
2. Destination IP, port và protocol có đúng với request không?
3. Route, firewall, peering, VPN hoặc load balancer nào tham gia đường đi?
4. Connectivity Tests dự đoán packet bị drop ở bước nào?
5. Với kịch bản được hỗ trợ, live data plane probes có tới destination không?
6. Nếu network path hoạt động, lỗi còn lại có thể thuộc DNS, TLS, authentication, application listener hoặc database không?

Mục tiêu nghiệm thu là một kết luận có bằng chứng: **điểm nghẽn, lớp chịu trách nhiệm, thay đổi cần thực hiện và phép thử xác nhận sau khi sửa**.

## 2. Network Intelligence Center gồm những công cụ nào?

**Network Intelligence Center (NIC)** là bộ công cụ quan sát, phân tích và xử lý sự cố mạng Google Cloud. Không phải mọi module đều trả lời cùng một câu hỏi.

| Công cụ | Câu hỏi chính | Dùng khi |
| --- | --- | --- |
| **Connectivity Tests** | Packet dự kiến đi qua những bước nào, và cấu hình có điểm drop nào? | Chẩn đoán một đường kết nối source → destination với protocol/port cụ thể. |
| **Network Analyzer** | Có cấu hình VPC nào sai hoặc dưới mức tối ưu? | Muốn phát hiện tự động lỗi route, firewall, topology, dependency và connectivity. |
| **Network Topology** | Các VPC, VM, hybrid connections và service liên hệ với nhau ra sao? | Cần nhìn sơ đồ topology và traffic metrics theo thời gian. |
| **Firewall Insights** | Firewall rules đang được sử dụng như thế nào? Có rule quá rộng hoặc không cần thiết? | Review firewall hygiene, rule usage và đề xuất siết quyền. |
| **Flow Analyzer** | Luồng traffic thực tế đi giữa các IP/port/protocol nào? | Phân tích VPC Flow Logs theo 5-tuple để tìm top talkers, luồng bất thường hoặc traffic cost. |
| **Performance Dashboard** | Network latency và packet loss giữa các zone/VM ra sao? | Điều tra vấn đề hiệu năng ở lớp mạng sau khi đã xác định endpoint. |
| **Cloud Network Insights** | Hiệu năng ứng dụng và network trên môi trường hybrid/multicloud có vấn đề ở hop nào? | Cần quan sát đường đi end-to-end rộng hơn trong kiến trúc được hỗ trợ. |

~~~mermaid
flowchart TB
    INCIDENT[Incident: timeout / packet loss / unreachable]
    INCIDENT --> CT[Connectivity Tests\nMột đường packet cụ thể]
    INCIDENT --> NA[Network Analyzer\nPhát hiện cấu hình liên tục]
    INCIDENT --> TOPO[Network Topology\nNhìn quan hệ và traffic]
    INCIDENT --> FW[Firewall Insights\nĐánh giá firewall rules]
    INCIDENT --> FLOW[Flow Analyzer\nPhân tích VPC Flow Logs]
    INCIDENT --> PERF[Performance Dashboard\nLatency / packet loss]
    CT --> RCA[Root cause + evidence]
    NA --> RCA
    TOPO --> RCA
    FW --> RCA
    FLOW --> RCA
    PERF --> RCA
    RCA --> FIX[Thay đổi được review]
    FIX --> VERIFY[Chạy lại test + xác minh ứng dụng]
~~~

**Quy tắc chọn công cụ:** nếu cần biết một packet TCP cụ thể có thể đi từ VM A tới VM B qua firewall nào, bắt đầu bằng Connectivity Tests. Nếu cần phát hiện cấu hình mạng sai trên diện rộng, xem Network Analyzer. Nếu cần biết traffic nào thực sự đã đi qua network, xem VPC Flow Logs/Flow Analyzer. Nếu cần biết latency/packet loss giữa zone, xem Performance Dashboard. Các công cụ bổ sung cho nhau, không thay thế nhau.

## 3. Connectivity Tests phân tích điều gì?

Connectivity Tests nhận đầu vào tương đương một **5-tuple không bao gồm source port**:

- Source endpoint và source IP/interface.
- Destination endpoint/IP.
- IP protocol (ví dụ TCP hoặc UDP).
- Destination port (khi dùng TCP/UDP).

Nó phân tích đường packet dự kiến qua VPC, route, firewall, Cloud VPN, VLAN attachment, peering, load balancer và các cấu hình mạng được hỗ trợ. Kết quả có thể trình bày trace theo các bước logic: chọn interface, kiểm tra egress/ingress firewall, tìm route phù hợp, qua network attachment/peering và xác định khả năng tới destination.

### 3.1. Configuration analysis

**Configuration analysis** là mô phỏng dựa trên cấu hình tài nguyên Google Cloud. Công cụ xây dựng mô hình forwarding để trả lời câu hỏi: *với cấu hình hiện tại, packet có thể đi qua các bước này không?*

Nó có ích để tìm:

- Egress firewall rule chặn source.
- Ingress firewall rule chặn destination.
- Không có route phù hợp hoặc route trỏ sai next hop.
- VPC peering/VPN/VLAN attachment không có đường đi phù hợp.
- Cấu hình load balancer hoặc endpoint không tương thích.
- Các cấu hình không nhất quán sau migration hoặc thay đổi network.

Kết quả trace giúp xác định **bước đầu tiên có thể làm packet drop**. Khi đọc, đừng chỉ xem dòng kết luận cuối cùng; mở từng hop và xác định resource, rule, route, priority và network liên quan.

### 3.2. Live data plane analysis

Với một số kịch bản được hỗ trợ, Connectivity Tests còn gửi **nhiều TCP hoặc UDP probe packets** qua data plane thực để kiểm tra packet có đến destination hay không. Kết quả có số probe gửi, số probe tới đích, trạng thái reachability, median và p95 one-way latency.

| Trạng thái live analysis | Số probe đến destination |
| --- | --- |
| **Reachable** | Ít nhất 95% |
| **Unreachable** | Không có probe nào tới đích |
| **Partially reachable** | Có probe tới đích nhưng dưới 95% |

Live analysis hữu ích khi muốn đối chiếu cấu hình với data plane. Tuy nhiên, nó **không phải synthetic application test**: probe TCP/UDP không đăng nhập database, không gọi API HTTP theo hợp đồng nghiệp vụ, không kiểm tra TLS certificate hoặc xác thực người dùng.

### 3.3. Hai kết quả không được nhầm lẫn

| Configuration analysis | Live data plane analysis | Cách diễn giải |
| --- | --- | --- |
| Packet could be delivered | Reachable | Cấu hình được mô phỏng là hợp lệ và probe thực tế cũng tới được đích trong lần đo. Vẫn cần test ứng dụng. |
| Packet could not be delivered | Unreachable | Có vấn đề cấu hình rõ ràng và probe không tới được đích. Bắt đầu từ hop bị drop. |
| Packet could be delivered | Unreachable/Partially reachable | Cấu hình nhìn hợp lệ nhưng data plane có vấn đề, hoặc một số đường/endpoint không được probe đủ. Kiểm tra dynamic state, route, firewall, backend health và các giới hạn probe. |
| Packet could not be delivered | Reachable | Có thể configuration analysis chưa cập nhật, có khác biệt về đường/endpoint, hoặc mô hình cấu hình không đại diện đúng request. Xác minh lại source/destination/interface và chờ propagation. |

**Packet could be delivered không bảo đảm traffic chắc chắn đi qua data plane.** Configuration analysis chỉ kiểm tra các nguyên nhân drop có thể suy ra từ cấu hình và không duy trì trạng thái sức khỏe của toàn bộ hạ tầng production nội bộ của Google. Live probes bổ sung bằng chứng cho những route được hỗ trợ, nhưng cũng có giới hạn về số lượng probe và đường được chọn.

## 4. Endpoint được hỗ trợ và những giới hạn quan trọng

Connectivity Tests hỗ trợ nhiều loại source/destination, nhưng **configuration analysis và live data plane analysis không hỗ trợ hoàn toàn giống nhau**.

| Endpoint | Vai trò có thể kiểm tra | Lưu ý |
| --- | --- | --- |
| Compute Engine VM | Source/destination | Live data plane analysis yêu cầu VM đang chạy; nếu VM có nhiều NIC, chọn đúng interface. |
| GKE cluster control plane | Source/destination theo trường hợp hỗ trợ | Một số loại endpoint chỉ hỗ trợ IP nội bộ; kiểm tra ma trận hỗ trợ và PSC limitation. |
| GKE Pod | Source/destination | Cần đúng cluster, namespace, Pod/IP và port. |
| Cloud Run service/job/revision | Source trong một số kịch bản | Live analysis có điều kiện cấu hình serverless VPC access; kiểm tra support matrix trước khi giả định Direct VPC egress được hỗ trợ. |
| Cloud SQL instance | Source/destination trong trường hợp hỗ trợ | Đối với Cloud SQL ở Google-owned VPC, configuration analysis có thể chỉ trả kết quả tổng thể ở phần cuối, không lộ cấu hình nội bộ của Google. |
| Load balancer forwarding rule | Destination | Kiểm tra VIP/forwarding rule và backend path; probe có thể chọn ngẫu nhiên backend. |
| Internal/external IP | Source/destination | Cần khai báo loại network/IP phù hợp. |
| On-premises IP | Source/destination theo kết nối | Thường liên quan Cloud VPN, Cloud Interconnect hoặc router appliance. |
| Private Service Connect endpoint | Destination trong một số mô hình | Không suy rộng hỗ trợ sang mọi kiểu PSC service. |

Một số giới hạn phải ghi nhớ:

- Với **Cloud SQL và GKE control plane**, một số loại test không hỗ trợ endpoint dùng Private Service Connect; xem ma trận hiện hành cho đúng chiều source/destination.
- Live data plane analysis với Cloud Run source hiện có điều kiện riêng liên quan Serverless VPC Access. Đừng suy ra một kết quả cho Cloud Run service áp dụng được cho mọi revision hoặc mọi kiểu egress.
- Với Google-managed services, Connectivity Tests có thể phân tích đường từ VPC của bạn và trả reachability tổng thể, nhưng không hiển thị chi tiết cấu hình bên trong project/VPC do Google quản lý.
- Với destination là Internet IP, live analysis kiểm tra tới network edge location của Google; điều đó không chứng minh server Internet phía sau đã xử lý request.
- Nếu destination là load balancer có nhiều backend, probe có thể chọn ngẫu nhiên backend. Không đảm bảo mọi backend đều được thử.
- Với ECMP, mỗi probe có thể theo một route ngẫu nhiên; số probe có thể không đủ để thử mọi đường.
- Công cụ không kiểm tra VM được cấu hình hoạt động như router, firewall, NAT gateway hoặc VPN appliance theo cách tổng quát.

Trước khi kết luận "tính năng không hoạt động", hãy kiểm tra loại endpoint, loại network, port, IP family, region và trạng thái tài nguyên có nằm trong support matrix hay không.

## 5. Chuẩn bị project, API và IAM

### 5.1. Bật Network Management API

Connectivity Tests sử dụng **Network Management API**. Bật API trong project chứa test:

~~~bash
gcloud services enable networkmanagement.googleapis.com \
  --project=PROJECT_ID
~~~

Project cần billing hợp lệ và Google Cloud CLI đã cài đặt. Khi mở Connectivity Tests lần đầu trong Console, giao diện cũng có thể yêu cầu bật API.

### 5.2. Role cho người vận hành

Các predefined roles cho Connectivity Tests:

| Role | Quyền chính | Ai nên có |
| --- | --- | --- |
| `roles/networkmanagement.viewer` | List/get test và xem tài nguyên Network Management trong phạm vi role | NOC, auditor, người đọc kết quả |
| `roles/networkmanagement.editor` | Tạo, cập nhật, rerun và xóa Connectivity Tests cùng quyền Network Management liên quan theo role | Network engineer thực hiện chẩn đoán |
| `roles/networkmanagement.admin` | Toàn quyền thao tác Network Management resources | Nhóm platform/network owner có trách nhiệm quản trị |

Một số thao tác còn cần quyền đọc metadata của source/destination resource, project hoặc network; chỉ cấp `roles/networkmanagement.viewer` không có nghĩa người dùng có thể xem mọi resource ở mọi project. Với test cross-project, rà soát IAM ở project chứa test và project chứa endpoint.

Không cấp Network Management Admin cho toàn bộ developer chỉ để họ xem một kết quả. Tách quyền **đọc test**, **tạo/rerun test** và **sửa network/firewall** thành trách nhiệm riêng. Một người tạo Connectivity Test không mặc nhiên cần quyền sửa VPC firewall.

### 5.3. Xác minh danh tính trước khi chạy

~~~bash
gcloud auth list
gcloud config get-value project
gcloud services list \
  --enabled \
  --project=PROJECT_ID
~~~

Kiểm tra principal đang active, project hiện tại và API đã bật. Với CI/CD, dùng Workload Identity Federation hoặc service account impersonation; tránh lưu key JSON dài hạn. Nếu có nhiều project, chỉ định `--project` tường minh cho lệnh để tránh tạo test ở sai project.

## 6. Thực hành lab: VM trong VPC tới VM nội bộ

### 6.1. Sơ đồ lab

Giả sử có hai VM staging trong cùng VPC:

- Source VM: `orders-client`, internal IP `10.10.1.10`.
- Destination VM: `orders-api-vm`, internal IP `10.10.2.20`.
- VPC: `orders-vpc`.
- Destination app lắng nghe TCP `8080`.
- Firewall ingress chỉ cho phép source subnet hoặc service account được phê duyệt.

~~~mermaid
flowchart LR
  SRC[orders-client\n10.10.1.10] -->|TCP 8080| ROUTE[VPC orders-vpc\nroute lookup]
  ROUTE --> FW[Firewall evaluation]
  FW -->|allow| DST[orders-api-vm\n10.10.2.20:8080]
  FW -->|deny| DROP[Packet dropped]
  DST --> APP[Java listener]
~~~

Lab chỉ dùng tài nguyên **staging đã tồn tại**. Không tạo VM, mở firewall hoặc gửi traffic vào production chỉ để thử. Nếu chưa có hai VM, dùng một môi trường đào tạo đã được chuẩn bị hoặc thực hiện phần đọc kết quả mẫu.

### 6.2. Xác minh điều kiện trước test

Trên VM destination, xác nhận ứng dụng có listener TCP 8080 bằng lệnh phù hợp với OS (ví dụ `ss -lntp` trên Linux). Ghi lại internal IP và network interface của cả hai VM.

Kiểm tra firewall rules:

~~~bash
gcloud compute firewall-rules list \
  --project=PROJECT_ID \
  --filter="network:orders-vpc"
~~~

Đọc các trường: direction, priority, source/destination ranges, target tags/service accounts, allowed/denied protocol/ports và disabled state. Đừng chỉ tìm một rule `allow`: một rule khác có priority cao hơn hoặc hierarchical firewall policy có thể thay đổi kết quả.

### 6.3. Tạo Connectivity Test bằng gcloud

Với hai private IP trong cùng VPC, dùng cấu hình tương đương:

~~~bash
gcloud network-management connectivity-tests create orders-client-to-api-8080 \
  --source-ip-address=10.10.1.10 \
  --source-network=projects/PROJECT_ID/global/networks/orders-vpc \
  --source-network-type=GCP_NETWORK \
  --destination-ip-address=10.10.2.20 \
  --destination-port=8080 \
  --protocol=TCP \
  --round-trip \
  --project=PROJECT_ID
~~~

Thay project ID, VPC URI, IP và port bằng giá trị thật của staging. Lệnh tạo test và chạy ngay; test được lưu như một tài nguyên Connectivity Test cho đến khi xóa. `--round-trip` yêu cầu phân tích chiều đi và chiều về khi kịch bản hỗ trợ.

Nếu muốn chọn source theo VM cụ thể, dùng URI đầy đủ và source IP thuộc đúng NIC:

~~~bash
gcloud network-management connectivity-tests create orders-client-to-api-8080 \
  --source-instance=projects/PROJECT_ID/zones/ZONE/instances/orders-client \
  --source-ip-address=10.10.1.10 \
  --destination-ip-address=10.10.2.20 \
  --destination-port=8080 \
  --protocol=TCP \
  --round-trip \
  --project=PROJECT_ID
~~~

Với VM nhiều network interfaces, khai báo đúng source interface/IP. Nếu chỉ chỉ định VM URI, một số trường hợp mặc định chọn primary interface; điều này có thể làm test mô phỏng sai đường mà ứng dụng đang dùng.

### 6.4. Xem kết quả

~~~bash
gcloud network-management connectivity-tests describe \
  orders-client-to-api-8080 \
  --project=PROJECT_ID
~~~

Trong kết quả, tìm:

- Source và destination thực tế, IP, protocol, destination port.
- Trạng thái operation và thời gian test.
- Configuration analysis result và các trace steps.
- Route được chọn, firewall rule khớp, network attachment/peering nếu có.
- Bước packet bị drop hoặc kết luận packet có thể được chuyển tiếp.
- Live data plane analysis result nếu route và endpoint được hỗ trợ.

Nếu test vừa tạo nhưng chưa hoàn tất, kiểm tra operation state rồi đọc lại. Nếu có thay đổi network ngay trước test, chờ **20–120 giây** để configuration analysis nhận cấu hình mới. Live data plane analysis không có cùng độ trễ cập nhật cấu hình, vì vậy hai kết quả có thể tạm thời khác nhau.

### 6.5. Chạy lại sau khi sửa

Sau khi một thay đổi đã được review và triển khai trong staging:

~~~bash
gcloud network-management connectivity-tests rerun \
  orders-client-to-api-8080 \
  --project=PROJECT_ID
~~~

So sánh trace trước/sau: bước drop đã biến mất chưa, route có thay đổi ngoài dự kiến không, và live probe có tới destination không. Lưu kết quả trước/sau cùng change ID để phục vụ audit.

## 7. Test từ VM đến Cloud SQL private IP

Đây là một trường hợp thường gặp khi Spring Boot chạy trên Compute Engine hoặc VM trong GKE node network và cần truy cập Cloud SQL.

### 7.1. Kiểm tra cấu hình trước

Xác nhận:

1. Cloud SQL instance có private IP và đúng network/Private Services Access hoặc kết nối private được chọn.
2. VM có route đến private IP và source interface đúng.
3. Firewall/routing cho phép TCP port của database (ví dụ PostgreSQL 5432, MySQL 3306).
4. Database đang hoạt động và có listener.
5. Nếu dùng PSC, kiểm tra Connectivity Tests support matrix cho endpoint cụ thể; không áp dụng kết luận của private-service-access cho mọi PSC topology.

### 7.2. Tạo test với Google-managed service endpoint

~~~bash
gcloud network-management connectivity-tests create orders-vm-to-cloudsql-5432 \
  --source-instance=projects/PROJECT_ID/zones/ZONE/instances/orders-client \
  --source-ip-address=SOURCE_VM_PRIVATE_IP \
  --destination-cloud-sql-instance=projects/DB_PROJECT_ID/instances/SQL_INSTANCE \
  --destination-port=5432 \
  --protocol=TCP \
  --round-trip \
  --project=PROJECT_ID
~~~

`--destination-cloud-sql-instance` nhận resource URI của Cloud SQL instance. Theo mặc định, Connectivity Tests thử private IP của Google-managed service nếu có; nếu không có private IP, công cụ có thể dùng public IP. Xác nhận endpoint đang được test đúng với thiết kế của bạn.

Configuration analysis có thể phân tích egress firewall và route trong VPC của khách hàng, nhưng ở bước đi vào Google-owned VPC của Cloud SQL, kết quả chỉ cung cấp **reachability tổng thể**, không hiển thị cấu hình nội bộ của Google.

### 7.3. Khi Connectivity Test báo packet có thể đến Cloud SQL

Kết quả đó chưa chứng minh PostgreSQL authentication thành công. Chạy thêm một phép thử ở application layer từ VM:

~~~bash
nc -vz PRIVATE_DB_IP 5432
~~~

Sau khi TCP kết nối được, dùng `psql` hoặc JDBC với credential được quản lý an toàn để thực hiện `SELECT 1`. Nếu socket mở nhưng JDBC báo password/authentication/TLS error, đó là vấn đề ở database/application layer chứ không phải route/firewall. Không ghi password vào shell history hoặc log.

## 8. Chẩn đoán đường đi tới Internet và mạng on-premises

### 8.1. VM tới Internet

Kiểm tra source VM có external IP hay đang dùng Cloud NAT, default route `0.0.0.0/0`, firewall egress và DNS resolver. Với test source là internal IP trong VPC:

~~~bash
gcloud network-management connectivity-tests create orders-vm-to-internet-443 \
  --source-ip-address=SOURCE_INTERNAL_IP \
  --source-network=projects/PROJECT_ID/global/networks/orders-vpc \
  --source-network-type=GCP_NETWORK \
  --destination-ip-address=DESTINATION_PUBLIC_IP \
  --destination-port=443 \
  --protocol=TCP \
  --round-trip \
  --project=PROJECT_ID
~~~

Khi destination là Internet IP, live data plane analysis có thể chỉ đo đến **Google network edge location**. Kết quả không thay thế `curl` tới hostname, kiểm tra TLS hoặc kiểm tra ứng dụng đích. DNS cũng cần được xác minh riêng: resolve hostname thành IP mong đợi trước khi chạy test.

### 8.2. VPC tới on-premises qua Cloud VPN/Interconnect

Khi test destination là private IP ở mạng on-premises, kiểm tra:

- Route từ VPC đến dải on-premises có được Cloud Router học/quảng bá hoặc cấu hình tĩnh đúng không?
- Cloud VPN tunnel/Interconnect VLAN attachment có trạng thái hoạt động?
- Prefix quảng bá và nhận có bị giới hạn hoặc chồng lấn?
- Firewall ở cả GCP và on-premises có cho phép protocol/port?
- Đường về từ on-premises tới subnet GCP có tồn tại?
- MTU và policy routing có tạo ra lỗi chỉ với packet lớn hoặc một số luồng?

Connectivity Tests mô phỏng các bước network trong Google Cloud và một số trạng thái động như tunnel/route được hỗ trợ. Nó không thể đọc cấu hình firewall của thiết bị on-premises mà bạn không quản lý qua Google Cloud. Kết quả tới VLAN attachment hoặc network edge không đồng nghĩa ứng dụng on-premises đã nhận request.

### 8.3. Chiều đi và chiều về

Một request TCP cần chiều đi đến destination và phản hồi quay về. Dùng `--round-trip` khi phù hợp, nhưng vẫn phải đọc rõ trace từng chiều. Stateful firewall có thể cho phép response traffic dựa trên connection tracking; configuration analysis mô phỏng một số hành vi connection tracking trong trường hợp test khởi tạo outbound, nhưng không thể đọc trực tiếp connection table ở data plane VM.

Nếu chiều đi pass nhưng response không về, điều tra route bất đối xứng, firewall egress/ingress, NAT, appliance và policy ở đầu xa. Không mở cả hai chiều `0.0.0.0/0` như một cách sửa tạm.

## 9. Dùng Network Analyzer để tìm cấu hình sai tự động

**Network Analyzer** liên tục giám sát cấu hình VPC và tạo insights khi phát hiện cấu hình sai hoặc dưới mức tối ưu. Công cụ có thể phân tích topology, firewall, routes, configuration dependencies và connectivity tới dịch vụ/ứng dụng; khi phát hiện lỗi, nó cố gắng liên kết với thay đổi cấu hình gần đây và gợi ý cách khắc phục.

Quy trình:

1. Mở **Network Intelligence Center → Network Analyzer**.
2. Chọn đúng project hoặc phạm vi được hỗ trợ.
3. Lọc insight theo category, severity, resource và thời gian.
4. Mở insight để đọc affected resource, root cause và suggested resolution.
5. Đối chiếu với thay đổi Terraform/Cloud Audit Logs gần nhất.
6. Xác minh bằng Connectivity Tests hoặc test ứng dụng trước khi thay đổi.
7. Sau khi sửa, đợi analyzer cập nhật và xác nhận insight được resolved hoặc không còn tái hiện.

Network Analyzer hữu ích cho **continuous discovery**, nhưng không thay Connectivity Tests trong việc mô phỏng một packet cụ thể. Insight có thể chỉ ra một firewall rule quá rộng, route thiếu hoặc cấu hình dependency; bạn vẫn phải xác định request thật có đi qua resource đó không.

## 10. Dùng Network Topology để hiểu quan hệ và traffic

**Network Topology** trực quan hóa network infrastructure, bao gồm VPC networks, hybrid connectivity, kết nối tới Google-managed services và các metrics traffic liên quan. Với project bật GKE Enterprise, có thể có thêm view về cluster, namespace, workload và Pod.

Dùng khi:

- Không rõ hai workload nằm trong cùng VPC hay qua peering/Shared VPC.
- Cần hiểu traffic liên vùng hoặc tới mạng on-premises.
- Muốn phát hiện một service đang trao đổi dữ liệu với network/region không dự kiến.
- Cần liên hệ topology với throughput hoặc metrics vận hành.

Các bước đọc topology:

1. Chọn project và khoảng thời gian phù hợp.
2. Chọn view infrastructure hoặc GKE Enterprise nếu có.
3. Mở node/edge để xem resource, connection và metrics.
4. Lọc theo network, region, project hoặc resource type.
5. Đối chiếu traffic với architecture diagram và data residency policy.

Network Topology cho thấy quan hệ và traffic, nhưng không thay thế packet trace. Một edge có traffic không chứng minh mọi port/protocol đều được phép; một edge không có traffic cũng có thể do khoảng thời gian, sampling hoặc chưa có workload hoạt động.

## 11. Dùng Firewall Insights và Flow Analyzer

### 11.1. Firewall Insights

**Firewall Insights** giúp hiểu cách VPC firewall rules được sử dụng, tìm rule quá rộng hoặc không cần thiết và đề xuất siết cấu hình. Có thể dùng để rà soát:

- Rule không có traffic match trong thời gian quan sát.
- Rule cho phép dải source rộng hơn nhu cầu.
- Rule bị rule khác shadow hoặc không còn hiệu lực thực tế.
- Rule có mức ưu tiên hoặc target scope không đúng dự kiến.

Không xóa rule chỉ vì chưa thấy traffic trong một khoảng thời gian ngắn. Một rule có thể phục vụ disaster recovery, batch job theo quý hoặc traffic ít thường xuyên. Review với owner, kiểm tra logs và change history trước khi chỉnh sửa.

### 11.2. Flow Analyzer và VPC Flow Logs

**Flow Analyzer** phân tích VPC Flow Logs theo 5-tuple:

\[
(\text{source IP},\ \text{destination IP},\ \text{source port},\ \text{destination port},\ \text{protocol})
\]

Nó giúp trả lời: VM nào tạo nhiều traffic, destination/port nào được dùng, lưu lượng tăng ở thời điểm nào và có luồng bất thường nào không. Đây là góc nhìn dựa trên **traffic logs đã thu thập**, không phải mô phỏng cấu hình như Connectivity Tests.

Để có dữ liệu:

1. Xác định subnet/network cần theo dõi.
2. Bật VPC Flow Logs theo sampling/aggregation/metadata phù hợp.
3. Đợi dữ liệu được ghi nhận và kiểm tra log scope/retention.
4. Dùng Flow Analyzer để lọc source, destination, port, protocol, project và time window.
5. Nếu cần điều tra chi tiết, mở log entries hoặc export theo pipeline phân tích được duyệt.

Flow Logs có sampling và aggregation; không nên xem một bản ghi là packet capture đầy đủ. Flow Analyzer chỉ phân tích được dữ liệu đã được thu thập, nên khi chưa bật logs hoặc chọn sai subnet, kết quả rỗng không chứng minh network không có traffic.

### 11.3. Khi kết hợp hai công cụ

| Connectivity Tests | Flow Analyzer | Kết luận gợi ý |
| --- | --- | --- |
| Config drop tại firewall | Không có flow record tương ứng | Có thể traffic không tới nơi tạo log; xem source/target subnet và log sampling. |
| Config có thể deliver | Có flow traffic thực tế | Đường có traffic; kiểm tra app listener, TLS/auth và response path. |
| Config có thể deliver | Không có flow traffic | Có thể request không phát sinh, sai source, logging chưa bật hoặc sampling không ghi mẫu. |
| Config drop | Vẫn có flow traffic | Có thể test input sai, flow thuộc luồng khác hoặc configuration analysis chưa cập nhật. Đối chiếu thời gian, 5-tuple và endpoint. |

Không dùng Flow Logs để kết luận IAM hoặc database user có quyền. Flow logs ghi nhận traffic, không chứng minh ứng dụng đã xác thực thành công.

## 12. Dùng Performance Dashboard phân biệt network latency và application latency

**Performance Dashboard** hiển thị packet loss và latency của Google Cloud network, bao gồm hiệu năng giữa các zone nơi có VM. Đây là công cụ để biết có suy giảm ở underlying network hay không và xem lịch sử vấn đề hiệu năng.

Khi API chậm:

1. Kiểm tra application traces để tách thời gian xử lý app, chờ database và network calls.
2. Mở Performance Dashboard, chọn region/zone và khoảng thời gian trùng incident.
3. Xem latency/packet loss giữa zone liên quan.
4. So sánh với Cloud Monitoring metrics của VM, GKE, load balancer hoặc Cloud SQL.
5. Nếu network dashboard ổn định nhưng app latency tăng, điều tra CPU, GC, connection pool, SQL query, retry hoặc thread saturation.
6. Nếu packet loss/latency network tăng, tiếp tục xem route, firewall, hybrid link và thay đổi hạ tầng.

Performance Dashboard không đo đầy đủ thời gian xử lý business logic. Latency thấp giữa hai zone không có nghĩa API sẽ trả lời nhanh nếu database query mất 2 giây hoặc JVM đang bị GC pause.

## 13. Phân tích trace: tìm đúng hop bị drop

Một kết quả Connectivity Test có thể gồm nhiều bước. Khi đọc trace, làm theo trình tự:

1. **Source selection:** kiểm tra source resource, interface, source IP và project. Với VM nhiều NIC, nhầm interface thường dẫn đến mô phỏng sai đường.
2. **Source egress firewall:** xem egress rule, priority, target, protocol/port và hierarchical firewall policies.
3. **Route lookup:** kiểm tra destination prefix, route priority, next hop, peering/VPN/Interconnect hoặc default route.
4. **Network transition:** xác định packet đi qua VPC peering, Cloud VPN, VLAN attachment, load balancer hoặc PSC endpoint nào.
5. **Destination ingress firewall:** xem source range, target tags/service account và rule deny/allow có liên quan.
6. **Google-managed endpoint:** nếu destination là Cloud SQL/GKE control plane, đọc reachability summary và nhớ giới hạn visibility bên trong Google-owned VPC.
7. **Return path:** nếu test round trip, kiểm tra route và firewall chiều phản hồi.
8. **Data plane:** nếu có live analysis, so sánh số probe, reachability và latency với configuration result.

Một trace có thể chỉ ra nhiều route khả thi do ECMP hoặc policy-based routing. Công cụ có thể không biết chính xác hash nội bộ chọn route nào cho từng packet. Hãy dùng live probes, Flow Logs và application-level tests để bổ sung bằng chứng.

## 14. Quy trình xử lý sự cố end-to-end

Dùng checklist này cho incident network:

~~~mermaid
flowchart TD
  A[Nhận báo lỗi: source, dest, time, port] --> B[Kiểm tra DNS và endpoint IP]
  B --> C[Kiểm tra resource/interface/route context]
  C --> D[Run Connectivity Test]
  D --> E{Configuration trace có drop?}
  E -->|Yes| F[Đọc hop, firewall, route, peering, policy]
  E -->|No| G{Live analysis được hỗ trợ?}
  F --> H[Review thay đổi và sửa trong staging]
  G -->|Yes| I[Đối chiếu probe reachability/latency]
  G -->|No| J[Chạy TCP/application test và xem logs]
  I --> K[Network Analyzer / Flow Logs / Topology]
  J --> K
  K --> L[Phân biệt network với TLS/auth/app]
  H --> M[Rerun Connectivity Test]
  L --> M
  M --> N[Kiểm tra request end-to-end]
  N --> O[Ghi RCA, evidence và runbook]
~~~

### 14.1. Thu thập đầu vào trước khi chạy

Mỗi incident cần:

- Project và resource IDs của source/destination.
- Region/zone, network, subnet và NIC.
- Source IP, destination IP hoặc FQDN đã resolve.
- Protocol, destination port và thời điểm xảy ra lỗi.
- Có dùng Cloud NAT, proxy, firewall appliance, PSC, VPN hay Interconnect không?
- Request một chiều hay round-trip; chỉ một VM/Pod hay tất cả workload?
- Lỗi có xảy ra liên tục hay theo thời điểm/traffic peak?

Nếu chưa xác định đúng IP/port, Connectivity Test có thể chạy thành công nhưng không đại diện cho request thật.

### 14.2. Sau khi tìm được điểm drop

1. Lưu test name, trace, thời điểm và ảnh chụp trước thay đổi.
2. Mở Terraform/Cloud Audit Logs để biết rule/route nào vừa đổi.
3. Xác định owner và blast radius của rule.
4. Tạo change đề xuất cụ thể: source range, target, protocol, port, route hoặc policy.
5. Review bảo mật; tránh mở rộng `0.0.0.0/0` hoặc xóa deny rule chung.
6. Triển khai vào staging, đợi configuration analysis nhận thay đổi.
7. Rerun Connectivity Test và test TCP/application.
8. Sau khi xác nhận mới promote change theo quy trình.

**Không sửa nhiều firewall rules cùng lúc** nếu chưa có lý do. Thay đổi một yếu tố có kiểm soát giúp xác định nguyên nhân và rollback dễ hơn.

## 15. Ma trận bài thực hành

| ID | Kịch bản | Công cụ chính | Bằng chứng cần lưu |
| --- | --- | --- | --- |
| CT-01 | VM → VM cùng VPC, TCP 8080 | Connectivity Tests | Trace source, route, firewall, destination |
| CT-02 | VM → Cloud SQL private IP, TCP 5432 | Connectivity Tests + TCP/JDBC | Reachability summary, kết quả `nc`, `SELECT 1` |
| CT-03 | VM → Internet IP, TCP 443 | Connectivity Tests + DNS/curl | Network edge probe, DNS result, TLS response |
| CT-04 | VM → on-premises IP qua VPN | Connectivity Tests + Cloud VPN logs | Route/tunnel/return path |
| CT-05 | GKE Pod → internal service | Connectivity Tests + Flow Logs | Pod IP, namespace, policy/route và 5-tuple |
| CT-06 | Cloud Run → private endpoint | Support matrix + live/real test phù hợp | VPC connector/egress config, TCP result |
| NA-01 | Phát hiện route/firewall misconfiguration | Network Analyzer | Insight, affected resource, recommendation |
| TOPO-01 | Xác minh traffic liên vùng | Network Topology | Graph, throughput, region/edge |
| FW-01 | Tìm rule quá rộng/ít dùng | Firewall Insights | Rule, usage window, owner, review |
| FLOW-01 | Xác định top talkers | Flow Analyzer | 5-tuple, traffic volume và thời gian |
| PERF-01 | Điều tra packet loss giữa zone | Performance Dashboard | Loss/latency chart và time window |

### 15.1. Tiêu chí PASS

- Test dùng đúng source IP/NIC, destination IP, protocol và port.
- Configuration trace xác định được bước drop hoặc đường đi dự kiến.
- Live analysis được ghi rõ **supported/not supported**; không suy ra từ config result.
- Nếu test Cloud SQL, có phép thử TCP và database-level riêng.
- Nếu test on-premises, có bằng chứng từ thiết bị/network owner ở đầu xa.
- Thay đổi firewall/route có owner, ticket và rollback plan.
- Test sau thay đổi không có drop ngoài dự kiến.
- Ứng dụng thực hiện được request thật; log/trace xác nhận cùng thời điểm.
- Incident report phân biệt rõ network issue với app/auth/DNS/TLS issue.

## 16. Các triệu chứng thường gặp và cách phân loại

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `Packet could not be delivered` tại egress | Egress deny, source route hoặc source interface sai | Xem source NIC, egress rule và route match |
| Drop ở ingress destination | Firewall rule thiếu source range, target không khớp hoặc deny priority cao | Kiểm tra target tags/service accounts, hierarchical policy và priority |
| Không có route phù hợp | Thiếu route, subnet/peering không đúng hoặc route propagation | Kiểm tra route table, dynamic routes và Cloud Router |
| VPN tunnel up nhưng test không tới đích | Prefix không được quảng bá/nhận, route return thiếu, firewall on-prem | Kiểm tra BGP routes, tunnel, policy và đầu xa |
| Cloud SQL reachability có thể deliver nhưng JDBC fail | DB user/password/TLS, port listener hoặc database state | Chạy TCP test rồi JDBC/SQL query riêng |
| Configuration pass nhưng live probes fail | Dynamic data plane, ECMP, backend, endpoint hoặc config propagation | Kiểm tra support, probes, backend health và Flow Logs |
| Live probes reachable nhưng ứng dụng timeout | Probe không kiểm tra application protocol/auth; sai DNS/hostname hoặc TLS | Dùng curl/psql/JDBC từ đúng source |
| Test mới chưa thấy firewall change | Configuration analysis chưa nhận cập nhật | Chờ khoảng 20–120 giây rồi rerun |
| Test đến load balancer chập chờn | Nhiều backends và probe chọn ngẫu nhiên | Kiểm tra từng backend, LB logs/health và synthetic test |
| Cloud Run source không có live result | Endpoint/configuration chưa thuộc support matrix | Xem serverless VPC Access và support matrix; chạy test thực tế từ workload |
| Flow Analyzer không có dữ liệu | VPC Flow Logs chưa bật, sai subnet/time window hoặc sampling | Kiểm tra logging configuration và time range |
| Firewall Insights báo rule unused | Traffic ít, sampling/window chưa đại diện hoặc rule phục vụ DR | Review owner, lịch workload và log trước khi xóa |
| Network Analyzer có insight nhưng app vẫn chạy | Insight là cảnh báo cấu hình/suboptimal, không nhất thiết là outage | Xác định severity, affected path và xác minh bằng Connectivity Test |
| Network Topology thiếu edge | Không có traffic trong time window hoặc metrics chưa sẵn sàng | Chọn time range rộng hơn và kiểm tra nguồn telemetry |
| Performance Dashboard bình thường nhưng API chậm | Bottleneck ở JVM, database hoặc downstream | Dùng application trace, GC, CPU, pool và query metrics |

## 17. Vận hành định kỳ và quản lý chi phí

### 17.1. Hằng ngày/tuần

- Xem Network Analyzer insights mới và các thay đổi severity cao.
- Theo dõi firewall rule changes và các rule có quyền rộng.
- Điều tra packet loss/latency bất thường giữa các zone hoặc qua hybrid links.
- Kiểm tra VPC Flow Logs đã bật đúng subnet, metadata và retention.
- Review Connectivity Tests còn lưu; đặt naming convention theo source/destination/port và ticket.
- Rà soát test không còn dùng và xóa theo quy trình để danh sách không nhiễu.

### 17.2. Chi phí và dữ liệu

Connectivity Tests tạo resource test tồn tại đến khi bị xóa; không nên tạo hàng nghìn test một lần rồi bỏ quên. Flow Logs, Logging, metrics, dashboard và các module Network Intelligence Center có điều kiện giá/usage riêng. Trước khi bật logging trên toàn bộ subnet:

1. Ước tính traffic volume và sampling rate.
2. Chọn aggregation interval/metadata phù hợp mục tiêu.
3. Đặt log retention và sink destination theo yêu cầu audit.
4. Dùng Flow Analyzer cho câu hỏi cụ thể, không giữ mọi metadata vô thời hạn nếu không cần.
5. Theo dõi chi phí log ingestion, storage, query và network egress.

### 17.3. Quản trị thay đổi

Connectivity Test là bằng chứng phân tích, không phải change approval. Mọi thay đổi firewall, route, peering, VPN, PSC hoặc DNS cần:

- Owner chịu trách nhiệm.
- Mô tả source/destination/port được phép.
- Lý do nghiệp vụ và security review.
- Kế hoạch test trước/sau.
- Rollback plan.
- Kết quả Connectivity Tests và application-level validation.
- Ghi nhận thời gian, project và change ID.

## 18. Checklist hoàn thành bài học

- [ ] Giải thích được Network Intelligence Center và vai trò của từng module.
- [ ] Phân biệt configuration analysis với live data plane analysis.
- [ ] Hiểu input 5-tuple và chọn đúng source interface, destination, protocol, port.
- [ ] Biết live analysis dùng TCP/UDP probes và ngưỡng Reachable 95%.
- [ ] Hiểu giới hạn probe với ECMP, nhiều load balancer backends và Google-managed services.
- [ ] Biết bật `networkmanagement.googleapis.com` và cấp IAM role tối thiểu.
- [ ] Tạo, describe, rerun và list Connectivity Tests bằng gcloud.
- [ ] Đọc được trace và xác định hop firewall/route/peering bị drop.
- [ ] Biết chờ propagation 20–120 giây sau thay đổi configuration.
- [ ] Kiểm tra VM-to-VM, VM-to-Cloud SQL, Internet và hybrid connectivity.
- [ ] Phân biệt reachability TCP với DNS, TLS, database auth và application behavior.
- [ ] Dùng Network Analyzer để tìm misconfiguration liên tục.
- [ ] Dùng Network Topology để hiểu network graph và traffic.
- [ ] Dùng Firewall Insights để review rule usage trước khi thay đổi.
- [ ] Dùng Flow Analyzer với VPC Flow Logs và 5-tuple.
- [ ] Dùng Performance Dashboard để đối chiếu latency/packet loss giữa zone.
- [ ] Có change ticket, rollback plan và bằng chứng trước/sau.
- [ ] Quản lý test resources, Flow Logs retention và chi phí phù hợp.

## Tài liệu tham khảo

- [Network Intelligence Center overview](https://docs.cloud.google.com/network-intelligence-center/docs/overview) — tổng quan các module Network Intelligence Center.
- [Connectivity Tests overview](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) — configuration analysis, live data plane, endpoints và limitations.
- [Create and run Connectivity Tests](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/how-to/running-connectivity-tests) — tạo test trên Console, gcloud và các tình huống VM, Cloud SQL, GKE, Cloud Run, hybrid.
- [gcloud connectivity-tests create](https://docs.cloud.google.com/sdk/gcloud/reference/network-management/connectivity-tests/create) — cú pháp và các endpoint flags.
- [gcloud connectivity-tests commands](https://docs.cloud.google.com/sdk/gcloud/reference/network-management/connectivity-tests) — list, create, describe, rerun, update và delete.
- [Connectivity Tests roles and permissions](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/access-control) — Network Management Admin, Editor, Viewer và permissions.
- [Enable the Network Management API](https://docs.cloud.google.com/network-intelligence-center/docs/reference/enable-api) — bật API và IAM.
- [Network Analyzer overview](https://docs.cloud.google.com/network-intelligence-center/docs/network-analyzer/overview) — automatic insights, root cause và recommendations.
- [Network Topology overview](https://docs.cloud.google.com/network-intelligence-center/docs/network-topology/overview) — topology, hybrid connections và traffic metrics.
- [Firewall Insights overview](https://docs.cloud.google.com/network-intelligence-center/docs/firewall-insights/overview) — firewall rule usage và optimization.
- [Flow Analyzer overview](https://docs.cloud.google.com/network-intelligence-center/docs/flow-analyzer/overview) — phân tích VPC Flow Logs theo 5-tuple.
- [Performance Dashboard overview](https://docs.cloud.google.com/network-intelligence-center/docs/performance-dashboard/overview) — latency và packet loss giữa zone.
- [VPC Flow Logs](https://docs.cloud.google.com/vpc/docs/flow-logs) — bật, cấu hình, sampling và lưu lượng log.

