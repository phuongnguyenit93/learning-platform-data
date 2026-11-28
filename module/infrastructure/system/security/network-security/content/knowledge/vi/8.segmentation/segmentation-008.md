# Segmentation theo workload: Phân đoạn mạng theo ứng dụng, dịch vụ và luồng dữ liệu

## 1. Vì sao cần phân đoạn theo workload?

**Workload** là một đơn vị thực thi chức năng nghiệp vụ hoặc xử lý dữ liệu: máy ảo chạy ứng dụng, tiến trình trên máy chủ, container, pod Kubernetes, dịch vụ cơ sở dữ liệu, máy chủ xử lý theo lô hoặc chức năng trong môi trường đám mây. Một hệ thống có thể gồm nhiều workload tương tác qua mạng.

**Segmentation theo workload** là cách xác định và thực thi các ranh giới truyền thông dựa trên **vai trò, ứng dụng, môi trường, mức độ nhạy cảm và quan hệ phụ thuộc** của từng workload. Cách tổ chức này giúp triển khai chính sách theo điều gì được phép giao tiếp với điều gì, thay vì phụ thuộc hoàn toàn vào việc máy đang nằm ở subnet hay VLAN nào.

Trong chương **Segmentation** của học phần **SECURITY_NETWORK_SECURITY**, chủ đề này liên hệ trực tiếp với phân đoạn mạng, firewall, xác thực kết nối, VPN, IDS/IPS, giám sát luồng, mô hình hóa mối đe dọa và kiến trúc bảo mật trong hạ tầng cloud. Phân đoạn theo workload đặc biệt hữu ích khi hạ tầng liên tục thay đổi: autoscaling tạo thêm máy, scheduler di chuyển pod, địa chỉ IP được tái cấp và nhiều ứng dụng dùng chung một cụm máy chủ.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt phân đoạn theo mạng (VLAN/subnet) với phân đoạn theo workload và **microsegmentation**.
2. Chuyển một sơ đồ ứng dụng nhiều tầng thành **ma trận luồng cho phép** theo nguồn, đích, cổng và mục đích.
3. Nhận diện các điểm thực thi: host firewall, agent/eBPF, hypervisor, cloud security group, Kubernetes NetworkPolicy và gateway.
4. Giải thích cách dùng nhãn, nhóm động và danh tính workload, cùng những giới hạn về độ tin cậy của chúng.
5. Thiết kế lộ trình triển khai có giám sát, kiểm thử lưu lượng được phép và lưu lượng bị chặn, tránh làm gián đoạn ứng dụng.

## 2. Từ phân đoạn mạng sang phân đoạn workload

### 2.1. Phân đoạn truyền thống theo địa chỉ và vị trí

Trong thiết kế truyền thống, các nhóm máy thường được chia theo **VLAN**, **subnet**, vùng DMZ hoặc VRF. Firewall/ACL cho phép lưu lượng qua ranh giới giữa các vùng. Ví dụ: subnet web được phép gọi subnet ứng dụng qua TCP/8080.

Cách này vẫn có vai trò quan trọng, nhưng có các giới hạn:

- Nếu nhiều dịch vụ khác nhau ở **cùng một subnet**, rule ở ranh giới subnet không phân biệt được từng dịch vụ trong subnet đó nếu lưu lượng không đi qua điểm lọc.
- Một rule rộng từ toàn bộ subnet nguồn đến toàn bộ subnet đích có thể cho phép nhiều kết nối ngoài nhu cầu thực tế.
- Khi workload đổi IP, node hoặc vùng triển khai, rule gắn chặt vào địa chỉ có thể lỗi thời hoặc phải cập nhật liên tục.
- Lưu lượng **east-west** giữa các workload nội bộ có thể không đi qua firewall biên vốn tập trung vào luồng **north-south** với Internet hoặc người dùng.

### 2.2. Phân đoạn theo vai trò và quan hệ ứng dụng

Với segmentation theo workload, quyết định cho phép lý tưởng mang ý nghĩa:

> Workload thuộc nhóm **frontend/production** chỉ được gọi **api/production** tại TCP/8080; **api/production** chỉ được kết nối **database/production** tại TCP/5432 và các dịch vụ hạ tầng đã được phê duyệt.

Nhãn workload hoặc danh tính do hệ thống quản lý có thể giúp áp dụng cùng chính sách cho các instance mới, miễn là việc gắn nhãn và nhận diện được kiểm soát. **Địa chỉ mạng vẫn được sử dụng để chuyển gói**, nhưng không nhất thiết là tiêu chí duy nhất để quản lý rule.

| Đặc điểm | Phân đoạn theo VLAN/subnet | Phân đoạn theo workload |
| --- | --- | --- |
| Đơn vị quản lý chính | Dải mạng, vùng, interface | Ứng dụng, dịch vụ, nhóm pod/VM, vai trò |
| Biến động địa chỉ | Thường phải cập nhật subnet/IP hoặc nhóm địa chỉ | Có thể dùng nhãn/nhóm động được quản lý |
| Lưu lượng nội bộ cùng subnet | Có thể không đi qua điểm lọc | Có thể lọc ở host, hypervisor, node hoặc workload |
| Độ chi tiết | Thường theo zone và subnet | Có thể đến mức nhóm dịch vụ hoặc endpoint |
| Phụ thuộc kỹ thuật | Switching/routing, VRF, firewall | Tùy nền tảng: agent, host firewall, cloud rule, CNI, v.v. |
| Vai trò trong phòng vệ | Tạo ranh giới mạng nền tảng | Giới hạn quan hệ kết nối bên trong và giữa các vùng |

Hai phương pháp **bổ sung cho nhau**. Workload segmentation không loại bỏ nhu cầu quản trị route, VLAN, VRF, mạng quản trị, kết nối site-to-site hoặc firewall tại các vùng tin cậy lớn.

### 2.3. Segmentation và microsegmentation

**Microsegmentation** thường chỉ việc áp dụng chính sách phân đoạn ở độ chi tiết nhỏ, gần với từng workload hoặc nhóm workload, thay vì chỉ chia mạng thành vài vùng rộng. Tên gọi không bảo đảm một cách triển khai cụ thể: có nền tảng lọc ở host, ở hypervisor, tại NIC ảo, ở node Kubernetes hoặc tại thành phần mạng khác.

Điều cần đánh giá là **điểm thực thi có nhìn thấy và kiểm soát luồng thực tế không**, rule có đủ chi tiết cho nhu cầu nghiệp vụ không, và thay đổi cấu trúc triển khai có duy trì chính sách không.

## 3. Mô hình ứng dụng ba tầng

Xét một ứng dụng gồm:

- **Frontend**: tiếp nhận yêu cầu người dùng qua ingress/reverse proxy.
- **API**: xử lý nghiệp vụ và gọi cơ sở dữ liệu.
- **Database**: lưu dữ liệu nghiệp vụ, không cần nhận kết nối trực tiếp từ frontend.
- **DNS/telemetry**: dịch vụ nền mà một số workload cần để phân giải tên và gửi thông tin giám sát.

~~~mermaid
flowchart LR
    U[Người dùng] -->|HTTPS 443| G[Ingress / Reverse proxy]
    G -->|HTTPS hoặc HTTP nội bộ| F[Frontend]
    F -->|TCP 8080| A[API]
    A -->|TCP 5432| D[(Database)]
    F -. Không có quyền DB .-> D
    A -->|DNS 53| DNS[Resolver]
    A -->|Telemetry theo policy| O[Collector]
~~~

Sơ đồ là **luồng ứng dụng được dự kiến**; cổng giữa ingress và frontend phụ thuộc cách triển khai thực tế. Mũi tên đứt nét thể hiện quan hệ **không được cho phép**, không phải một kết nối đã xảy ra.

### 3.1. Ma trận kết nối làm nguồn sự thật

Trước khi tạo rule, mô tả **vì sao từng luồng cần tồn tại**:

| Workload nguồn | Workload đích | Giao thức / cổng đích | Mục đích | Chính sách |
| --- | --- | --- | --- | --- |
| Ingress | Frontend | TCP/443 hoặc cổng nội bộ thực tế | Chuyển yêu cầu web | Allow |
| Frontend | API | TCP/8080 | Gọi nghiệp vụ | Allow |
| API | Database | TCP/5432 | Truy vấn dữ liệu | Allow |
| Workload cần DNS | Resolver nội bộ | UDP/TCP 53 | Phân giải tên | Allow có giới hạn |
| Workload có agent giám sát | Collector | TCP/cổng cấu hình | Telemetry | Allow có giới hạn |
| Frontend | Database | TCP/5432 | Không có quan hệ nghiệp vụ | Deny |
| Development | Database production | Mọi cổng | Không có nhu cầu kết nối trực tiếp | Deny |
| Mọi nguồn khác | Cổng quản trị của workload | SSH/RDP/management API | Không thuộc kênh quản trị được phê duyệt | Deny |

**Deny theo mặc định** cần có các rule allow bổ sung cho health check, DNS, đồng bộ thời gian, certificate retrieval, service discovery, giám sát, backup, quản trị và luồng phản hồi khi thực sự cần. Không tự đoán chúng từ tên ứng dụng: hãy đối chiếu với log và kiến trúc.

### 3.2. Kiểm soát theo cả chiều đi và chiều về

Nếu frontend được phép gọi API, thường cần:

1. Rule cho luồng mới từ frontend đến API.
2. Các điểm kiểm soát outbound tại frontend và inbound tại API, nếu cả hai đều được áp dụng.
3. Cho phép lưu lượng phản hồi theo cơ chế **stateful** hoặc cấu hình hai chiều thích hợp nếu điểm lọc stateless.
4. Kiểm tra đường mạng và NAT/proxy để rule đối chiếu với **địa chỉ và danh tính quan sát được tại điểm thực thi**.

Không nên giả định mọi sản phẩm firewall, Kubernetes NetworkPolicy và ACL đều xử lý trạng thái hoặc thứ tự rule theo cùng một cách. Hãy kiểm tra semantics của nền tảng được dùng.

## 4. Nhận diện và phân nhóm workload

### 4.1. Bộ thuộc tính giúp tổ chức chính sách

Một inventory hữu ích có thể ghi:

| Thuộc tính | Giá trị ví dụ | Vì sao cần |
| --- | --- | --- |
| Application | order-service | Liên kết các thành phần cùng nghiệp vụ |
| Role | frontend / api / database | Định nghĩa quan hệ kết nối |
| Environment | dev / staging / prod | Tránh luồng xuyên môi trường |
| Data classification | public / internal / restricted | Đặt ranh giới bảo vệ dữ liệu |
| Owner | Nhóm vận hành dịch vụ | Phê duyệt và chịu trách nhiệm |
| Deployment | VM / Pod / managed database | Chọn điểm thực thi phù hợp |
| Location | VPC, subnet, namespace, cluster | Hiểu route và vùng kiểm soát |
| Criticality | low / medium / high | Ưu tiên quản lý và giám sát |

**Nguyên tắc:** nhãn giúp tổ chức chính sách, nhưng **không tự là bằng chứng xác thực**. Một người có quyền sửa nhãn hoặc metadata có thể cố thay đổi nhóm áp dụng. Cần kiểm soát quyền tạo/sửa nhãn, namespace, service account và cấu hình agent bằng cơ chế quản trị và audit phù hợp.

### 4.2. Nhóm tĩnh, nhóm động và danh tính workload

- **Nhóm tĩnh** dùng danh sách IP hoặc máy cụ thể: dễ kiểm tra với số lượng nhỏ, nhưng dễ lỗi thời trong autoscaling.
- **Nhóm động** dựa trên tag/label/metadata do hệ thống quản lý: thích hợp khi instance được tạo hoặc xóa thường xuyên, nhưng yêu cầu kiểm soát vòng đời và quyền thay đổi metadata.
- **Danh tính workload** có thể gắn với service account, chứng chỉ ngắn hạn, identity của runtime hoặc cơ chế tương đương. Danh tính mật mã có thể hỗ trợ xác thực dịch vụ, nhưng chỉ có ích khi bên thực thi policy **xác minh được danh tính đó**.

Một rule L3/L4 dựa trên Kubernetes pod label **không tự động xác thực bằng mật mã** peer của một phiên. Nếu cần bảo đảm dịch vụ đích thực sự là workload đã được xác nhận danh tính, hãy bổ sung TLS/mTLS, xác thực giữa dịch vụ và kiểm soát danh tính tương ứng.

## 5. Những điểm thực thi segmentation

| Điểm thực thi | Mô hình áp dụng | Ưu điểm | Giới hạn cần đánh giá |
| --- | --- | --- | --- |
| Host firewall | Rule ngay trong hệ điều hành VM/server | Gần tiến trình, bảo vệ ngay trên host | Quản lý số lượng lớn khó nếu cấu hình thủ công |
| Agent hoặc eBPF | Policy tại kernel/host/node | Có thể kiểm soát và quan sát traffic ở điểm đầu/cuối | Cần kiểm tra quyền agent, khả năng tương thích, ranh giới host |
| Hypervisor / virtual switch | Lọc traffic giữa các VM | Không phụ thuộc hoàn toàn vào guest OS | Phụ thuộc nền tảng ảo hóa và mô hình quản trị |
| Cloud security group | Gắn với VM/NIC/nhóm tài nguyên theo nhà cung cấp | Tích hợp vòng đời cloud | Mức chi tiết và semantics khác nhau giữa nhà cung cấp |
| Kubernetes CNI / NetworkPolicy | Chọn pod và quy định các luồng ingress/egress | Phù hợp scheduler và vòng đời pod | Cần CNI hỗ trợ; NetworkPolicy chuẩn có phạm vi hạn chế |
| Firewall/Gateway giữa vùng | Kiểm soát lưu lượng qua phân đoạn mạng | Phù hợp biên tin cậy, giám sát tập trung | Có thể không thấy lưu lượng cùng vùng không qua gateway |
| Service mesh | Policy danh tính và giao thức giữa dịch vụ | Có thể thêm mTLS và kiểm soát L7 | Không thay thế kiểm soát mạng L3/L4 hoặc lưu lượng ngoài mesh |

**Chú ý thứ tự:** một allow tại host chưa đủ khi security group hoặc ACL chặn trước đó; một allow ở cloud cũng không đảm bảo host có socket lắng nghe. Lưu lượng đi qua nhiều điểm thực thi cần thỏa tất cả chính sách có hiệu lực.

### 5.1. Chính sách mạng và danh tính dịch vụ là hai lớp

Giả sử API chỉ được giao tiếp với DB qua TCP/5432. Quy tắc mạng thực thi ranh giới đó, nhưng vẫn cần:

- DB xác thực đúng tài khoản hoặc danh tính client và chỉ cấp quyền dữ liệu cần thiết.
- Kết nối được bảo vệ bằng TLS khi chính sách yêu cầu, chứng chỉ được quản lý và xác minh.
- Bí mật truy cập được lưu giữ an toàn, luân chuyển theo quy trình.
- Logging ghi nhận cả **kết nối mạng** lẫn **truy vấn/thao tác quan trọng** trong ứng dụng.

Mô hình **Zero Trust** nhấn mạnh kiểm tra điều kiện truy cập liên tục và theo ngữ cảnh, không mặc nhiên tin cậy chỉ vì cùng subnet hay cùng cluster. Segmentation theo workload hỗ trợ giới hạn phạm vi giao tiếp, nhưng tự nó không triển khai đầy đủ Zero Trust.

## 6. Ví dụ với Kubernetes NetworkPolicy

Kubernetes NetworkPolicy là một cơ chế mô tả **lưu lượng nào được phép tới/từ các pod được chọn**. Việc thực thi phụ thuộc plugin mạng **CNI có hỗ trợ NetworkPolicy**. Khi không có thành phần thực thi tương ứng, việc tạo đối tượng NetworkPolicy có thể không tạo ra hiệu quả chặn như mong đợi.

### 6.1. Những khái niệm cần nắm

- **podSelector:** chọn pod chịu tác động trong namespace chứa NetworkPolicy.
- **namespaceSelector:** chọn namespace của nguồn hoặc đích, tùy vị trí được khai báo.
- **ingress / egress:** mô tả hướng truy cập vào và ra của pod được chọn.
- **policyTypes:** chỉ rõ kiểu chính sách áp dụng cho pod (Ingress, Egress).
- **ports:** hạn chế protocol và cổng đích khi rule hỗ trợ.
- **ipBlock:** chọn CIDR để mô tả địa chỉ IP; cần xét NAT, địa chỉ pod và semantics thực tế của mạng trước khi dùng.

**Các policy chuẩn được cộng gộp:** nếu một pod được chọn bởi nhiều NetworkPolicy cùng hướng, traffic được phép khi **ít nhất một rule allow phù hợp** từ các policy đó cho hướng liên quan. NetworkPolicy chuẩn **không có deny rule tường minh với thứ tự ưu tiên** như một số firewall khác. Khi một pod bị cô lập cho cả ingress và egress, một kết nối cần được cho phép ở hai phía liên quan.

### 6.2. Bước 1: Thiết lập default deny trong namespace thử nghiệm

Ví dụ sau chỉ áp dụng trong namespace **lab-segmentation** được quản trị và đã kiểm tra plugin CNI. Nó chọn tất cả pod trong namespace và cô lập cả inbound lẫn outbound, cho đến khi có các policy allow tương ứng.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-both
  namespace: lab-segmentation
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Quy tắc này **có thể cắt DNS, health checks, service discovery, ingress controller, monitoring và các kết nối ứng dụng** nếu không chuẩn bị các policy cho phép. Nó cũng không tự bảo vệ host networking của node hay mọi loại traffic đặc biệt do CNI xử lý. Vì vậy chỉ thử trong lab có khả năng khôi phục và có ma trận luồng rõ ràng.

### 6.3. Bước 2: API chỉ nhận từ frontend, chỉ gọi DB và DNS

Giả sử frontend, API, database nằm cùng namespace **lab-segmentation**, lần lượt có label **app: frontend**, **app: api**, **app: database**. DNS của cluster nằm trong **kube-system**, có label pod **k8s-app: kube-dns**. Đây là **giả định để minh họa**: tên, nhãn và đường DNS thực tế phải kiểm tra tại cụm.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-allowed-flows
  namespace: lab-segmentation
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: database
      ports:
        - protocol: TCP
          port: 5432
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

**Đọc chính sách:**

1. Chỉ pod có nhãn **app: api** trong namespace trên bị chọn.
2. Rule ingress cho phép pod **app: frontend** **trong cùng namespace** truy cập cổng TCP/8080 của API.
3. Rule egress cho phép API gọi pod **app: database** cùng namespace tại TCP/5432.
4. Rule egress DNS dùng **namespaceSelector và podSelector trong cùng một phần tử** để chọn DNS pod thuộc namespace kube-system; UDP/TCP 53 được cho phép.
5. Các kết nối khác từ/đến pod API bị cô lập theo hướng tương ứng, trừ khi có **NetworkPolicy khác cũng cho phép**.

**Quan trọng:** cấu hình trên chỉ mô tả rule của **API**. Vì namespace có default deny, frontend còn cần egress đến API, database còn cần ingress từ API, và ingress controller cần luồng hợp lệ đến frontend. Nếu muốn ứng dụng chạy, mỗi workload bị cô lập phải có chính sách tương ứng với **đường đi thực tế**. Kubernetes NetworkPolicy cũng không kiểm soát quyền gọi API của Kubernetes, quyền sửa label hay xác thực DB.

### 6.4. Kiểm tra YAML và policy thực tế

Lệnh **chỉ đọc** (cần quyền truy cập cụm lab):

~~~bash
# Xem các NetworkPolicy và pod đã được chọn
kubectl -n lab-segmentation get networkpolicy
kubectl -n lab-segmentation get pods --show-labels

# Kiểm tra rule đã triển khai và selector
kubectl -n lab-segmentation describe networkpolicy api-allowed-flows

# Kiểm tra DNS pod và nhãn thực tế của cụm
kubectl -n kube-system get pods --show-labels
~~~

**Kiểm thử lưu lượng** cần thực hiện từ các pod/máy thử do nhóm quản trị tạo, theo danh sách nguồn và đích được phép. Ví dụ, chỉ khi hai phía đã có rule tương ứng, frontend mới nên kết nối được API:8080, API mới nên kết nối được DB:5432, và frontend không nên kết nối trực tiếp DB:5432. Kiểm tra cả DNS, giám sát và các phụ thuộc nền khác.

Không nên kết luận NetworkPolicy có hiệu lực chỉ vì Kubernetes API đã chấp nhận YAML. Cần xác nhận CNI thực thi chính sách và chạy **kiểm thử allow và deny** từ các nguồn khác nhau.

### 6.5. Giới hạn quan trọng của NetworkPolicy chuẩn

- NetworkPolicy chuẩn mô tả chủ yếu **L3/L4**; chính sách theo URL, HTTP method, FQDN hoặc danh tính mTLS không thuộc khả năng bảo đảm chung của API chuẩn.
- Việc kết hợp NAT với ClusterIP, NodePort, LoadBalancer, ingress và đường truyền qua node có thể làm IP nguồn/đích quan sát được khác nhau tùy CNI và điểm thực thi.
- Traffic đến/từ node, **hostNetwork pod**, đường service mesh, DNS proxy hoặc tunnel có thể cần kiểm soát bổ sung.
- Không nên giả định một rule theo **ipBlock** áp dụng thống nhất cho IP pod ở mọi CNI.
- Thay đổi nhãn pod hoặc namespace có thể làm thay đổi tập đối tượng được phép. Cần bảo vệ quyền sửa metadata bằng RBAC, admission policy và quản trị triển khai.
- Nếu dùng IPv6 hoặc dual-stack, cần xác minh cách CNI thực thi với cả hai họ địa chỉ, không suy ra từ kiểm thử IPv4.

## 7. Segmentation theo workload trên VM và cloud

### 7.1. Nhóm theo vai trò thay vì từng địa chỉ máy

Trong hệ thống dùng VM, một thiết kế thủ công có thể ghi “VM A được truy cập IP của VM B”. Khi autoscaling tạo VM mới, cách quản lý này tăng số rule và dễ sót.

Một cách phù hợp hơn với nền tảng hỗ trợ là:

- Nhóm **frontend-prod** gồm các VM frontend production.
- Nhóm **api-prod** gồm các VM API production.
- Nhóm **db-prod** gồm các DB server production.
- Rule cho phép frontend-prod đến api-prod trên cổng dịch vụ; api-prod đến db-prod tại cổng DB.

Cloud có thể dùng security group hoặc cơ chế nhóm tài nguyên làm điểm tham chiếu nguồn/đích. Khả năng tham chiếu nhóm, hiệu lực rule, statefulness và hướng policy tùy nhà cung cấp; không thể bê nguyên cú pháp hoặc hành vi từ cloud này sang cloud khác.

**Quản trị vòng đời:** hệ thống cấp phát VM nên gắn đúng tag/nhóm theo vai trò và môi trường ngay khi tạo, thu hồi khi hủy, và ghi log thay đổi. Với workload bị gán sai nhóm, segmentation có thể tạo ra quyền truy cập không mong muốn, dù rule nhóm đúng về mặt cú pháp.

### 7.2. Mạng nhiều vùng và kết nối hybrid

Workload có thể chạy đồng thời on-premises, nhiều VPC/VNet, nhiều cloud hoặc qua VPN site-to-site. Lúc đó cần hiểu:

1. Route và cơ chế phân giải tên giữa các môi trường.
2. Tại đâu các nguồn/đích bị đổi IP qua NAT hoặc proxy.
3. Rule trên host, cloud firewall, gateway và tunnel nào cùng áp dụng.
4. Điểm giám sát nào quan sát được toàn bộ kết nối và những điểm mù do mã hóa.
5. Làm sao gắn workload vào nhóm chính sách khi chuyển môi trường.

VPN chỉ tạo một đường truyền được bảo vệ theo cấu hình; nó không tự cấp quyền mọi workload ở hai đầu truy cập lẫn nhau. Cần kết hợp network segmentation và xác thực dịch vụ.

## 8. Phân tích mối đe dọa và khả năng di chuyển ngang

Trong **threat modeling**, một giả định hữu ích là một workload nào đó có thể bị xâm phạm. Mục tiêu segmentation là giới hạn những hệ thống khác mà kẻ tấn công có thể tiếp cận tiếp theo.

~~~mermaid
flowchart LR
    Attacker[Đối tượng tấn công] -->|Chiếm quyền frontend| FE[Frontend]
    FE -->|Luồng nghiệp vụ hợp lệ| API[API]
    FE -. Chặn TCP 5432 .-> DB[(Database)]
    API -->|Luồng DB được phép| DB
    FE -. Chặn quản trị .-> ADM[Máy quản trị]
~~~

**Điểm mấu chốt:** segmentation giới hạn đường di chuyển ngang nhưng không bảo đảm loại bỏ mọi rủi ro. Nếu frontend được phép gọi API mà API có lỗi xác thực/ủy quyền, kẻ tấn công vẫn có thể lợi dụng **đường được phép** để gây hại. Đó là lý do cần bảo vệ cả API, danh tính workload, bí mật kết nối, kiểm tra input và quyền ở DB.

| Kịch bản rủi ro | Thiết kế segmentation hỗ trợ thế nào? | Biện pháp bổ sung |
| --- | --- | --- |
| Frontend bị xâm phạm muốn truy cập DB trực tiếp | Chặn kết nối frontend → DB | Xác thực DB, giới hạn quyền API |
| Máy dev tìm cách gọi dữ liệu production | Tách nhóm môi trường, deny cross-environment | IAM, quy trình cấp quyền và kiểm toán |
| Workload mới triển khai nhầm mở cổng quản trị | Default deny inbound, chỉ cho từ mạng quản trị | Quản trị cấu hình, quản lý khóa/chứng chỉ |
| Pod tự gắn nhãn để vào nhóm được phép | Hạn chế ai được sửa nhãn hoặc tạo pod | RBAC, admission control, audit |
| Agent kiểm soát bị tắt/hỏng | Cảnh báo host mất khả năng thực thi policy | Quản lý endpoint, cơ chế fail-safe được thiết kế trước |
| Luồng qua proxy phá vỡ định danh nguồn gốc | Phân đoạn theo kết nối thực tới proxy/backend | Xác thực hop, log correlation, proxy policy |

Khả năng **east-west visibility** từ flow logs, agent, eBPF hoặc IDS/NDR giúp xác minh rằng không có những mối quan hệ ngoài ma trận. Tuy nhiên lưu lượng đã mã hóa có thể giới hạn quan sát nội dung ứng dụng; metadata lưu lượng không tự chứng minh ý định tấn công.

## 9. Quy trình triển khai từ quan sát đến thực thi

Thay đổi segmentation có thể ngắt ứng dụng nếu áp dụng chặn trước khi hiểu luồng thật. Một quy trình thực tế nên chia thành các bước rõ ràng.

### Bước 1. Kiểm kê workload và ranh giới tin cậy

Gắn từng workload với ứng dụng, owner, môi trường, vai trò, dữ liệu xử lý, điểm triển khai, IP/hostname, cách xác thực và hệ thống phụ thuộc. Chú ý workload ngắn hạn, job định kỳ, backup, database managed, máy quản trị và endpoint tích hợp từ đối tác.

### Bước 2. Thu thập dữ liệu luồng có phạm vi

Quan sát log host/network firewall, NetFlow/IPFIX, cloud flow logs, CNI/agent telemetry, log ứng dụng và service inventory. Ghi **nguồn → đích → giao thức/cổng → thời điểm → khối lượng → người sở hữu**. Cần nhìn đủ khoảng thời gian để thấy batch job, backup, báo cáo tháng hoặc các luồng ít xuất hiện.

**Không chuyển mọi lưu lượng quan sát được thành quyền vĩnh viễn.** Lưu lượng thực tế có thể chứa thử quét, cấu hình sai hoặc sự kiện bất thường. Mỗi luồng nên được owner xác nhận là có mục đích nghiệp vụ.

### Bước 3. Mô hình hóa ma trận allow

Nhóm theo chức năng, phân loại dữ liệu, môi trường và chiều truy cập; xác định ngoại lệ có thời hạn. Rule nên thể hiện đúng mục đích, ví dụ API truy cập DB production, thay vì cho cả subnet ứng dụng truy cập mọi cổng ở subnet DB.

### Bước 4. Chọn điểm thực thi và chuẩn bị phương án khôi phục

Xác định từng luồng đi qua host firewall, CNI, security group, gateway, service mesh hay kết hợp. Kiểm tra độ bao phủ với VM/container/pod, IPv6, NAT, overlay, host networking và endpoint nằm ngoài quản trị. Chuẩn bị rollback/console quản trị trước khi chặn các luồng đang dùng.

### Bước 5. Thử nghiệm ở chế độ quan sát nếu nền tảng hỗ trợ

Một số sản phẩm có chế độ monitor/simulate policy; Kubernetes NetworkPolicy chuẩn **không định nghĩa chế độ audit/dry-run cho toàn bộ hành vi gói mạng**. Nếu nền tảng có công cụ dự đoán thay đổi, dùng nó kết hợp với thử nghiệm trong lab/staging.

### Bước 6. Triển khai theo vòng nhỏ

Bắt đầu ở nhóm workload ít rủi ro hoặc một ứng dụng có ma trận rõ, triển khai rule, kiểm tra sức khỏe dịch vụ rồi mở rộng. Tránh thay toàn bộ chính sách của nhiều môi trường cùng lúc. Có chủ sở hữu xác nhận chức năng nghiệp vụ vẫn hoạt động sau thay đổi.

### Bước 7. Kiểm thử tích cực và tiêu cực

**Kiểm thử tích cực:** frontend → API thành công; API → DB thành công; DNS, metrics, health probes và backup còn hoạt động.

**Kiểm thử tiêu cực:** frontend → DB bị từ chối; development → DB production bị từ chối; workload khác không được truy cập management port. Ghi **nguồn kiểm thử**, endpoint, thời gian, policy được kỳ vọng và kết quả.

### Bước 8. Giám sát drift và quản lý ngoại lệ

Theo dõi workload không được gán nhóm, tag thay đổi bất thường, rule allow quá rộng, rule hết hạn, số lượng deny tăng, lỗi ứng dụng sau triển khai và các đường đi mới. Có owner, lý do và ngày hết hạn cho ngoại lệ; định kỳ thu hẹp rule không còn cần thiết.

## 10. Chẩn đoán khi workload không thể giao tiếp

Thứ tự kiểm tra giúp tránh việc mở tạm mọi rule:

~~~mermaid
flowchart TD
    A[Lỗi kết nối giữa workload] --> B{Đích đang chạy và listen?}
    B -->|Không| C[Kiểm tra workload, readiness, socket]
    B -->|Có| D{DNS, service discovery, route phù hợp?}
    D -->|Không| E[Kiểm tra DNS, service, endpoint, network]
    D -->|Có| F{Selector và policy có khớp?}
    F -->|Không| G[Kiểm tra nhãn, namespace, IP, rule hai phía]
    F -->|Có| H{Điểm thực thi có chặn?}
    H -->|Có| I[Đối chiếu log host, CNI, cloud, gateway]
    H -->|Không| J[Kiểm tra TLS, chứng chỉ, xác thực, ứng dụng]
~~~

Những lỗi phổ biến:

- **Quên DNS:** pod/VM không phân giải được tên dù cổng ứng dụng đã mở. Cần kiểm tra resolver thực tế, cả UDP và TCP 53 khi được dùng.
- **Sai nhãn hoặc namespace:** policy chọn nhầm nhóm pod hoặc không chọn gì; rule namespaceSelector kết hợp podSelector không đúng như dự kiến.
- **Chỉ mở một phía:** frontend được phép egress nhưng API bị deny ingress; với cơ chế thực thi khác, cần xét statefulness và chiều phản hồi.
- **Sai cổng đích:** Service chuyển cổng đến targetPort khác; phải hiểu điều kiện khớp cổng thực tế theo triển khai CNI.
- **Nguồn bị NAT/proxy:** IP nhìn thấy ở điểm thực thi không còn là IP client ban đầu.
- **Thêm workload mới:** autoscaling tạo pod/VM không có tag hoặc nhãn đúng, dẫn đến quyền truy cập bất ngờ.
- **Health/monitoring bị chặn:** chính sách chỉ bao quát đường nghiệp vụ chính, bỏ sót probe, telemetry hoặc backup.
- **Container/hostNetwork:** lưu lượng theo đường mạng của node, không chịu cùng quy tắc pod thông thường.
- **IPv4 được, IPv6 không được:** chính sách/route hoặc điểm thực thi thiếu kiểm tra dual-stack.

Khi điều tra, luôn đối chiếu **nguồn thực tế, đích thực tế, giao thức/cổng, thời điểm, điểm thực thi và chính sách hiệu lực**. Việc không thấy log deny không đồng nghĩa không bị chặn vì logging có thể bị tắt hoặc lưu ở nơi khác.

## 11. Các thước đo vận hành

Một chương trình segmentation theo workload cần được đánh giá bằng kết quả kiểm soát, không chỉ số lượng policy:

| Thước đo | Cách dùng | Điều cần cảnh giác |
| --- | --- | --- |
| Tỷ lệ workload được phân nhóm đúng | Đo độ đầy đủ của inventory và metadata | Nhãn đầy đủ nhưng chưa chắc đáng tin |
| Tỷ lệ luồng được owner phê duyệt | So ma trận với lưu lượng được quan sát | Không tự động coi mọi lưu lượng phát hiện là hợp lệ |
| Số rule mở rộng ngoài nhu cầu | Tìm broad allow, any-to-any, ngoại lệ quá hạn | Rule ít chưa chắc an toàn hơn |
| Kết quả kiểm thử allow/deny | Chứng minh chính sách có tác dụng theo nguồn và đích đã thử | Không ngoại suy vượt phạm vi kiểm thử |
| Drift sau thay đổi triển khai | Phát hiện IP, nhãn hoặc topology đổi làm thay policy | Cần đối chiếu với CI/CD và inventory |
| Sự cố vận hành do policy | Theo dõi downtime, rollback, lỗi DNS/health | Thắt chặt quá nhanh có thể gây gián đoạn |
| Độ bao phủ log/telemetry | Bảo đảm có bằng chứng điều tra | Mã hóa và điểm quan sát có thể gây mù thông tin |

Những chỉ số này nên được xem theo ứng dụng, môi trường và thời kỳ, không dùng như chứng nhận rằng hệ thống đã hết nguy cơ tấn công.

## 12. Bài thực hành thiết kế chính sách

**Tình huống:** một hệ thống đặt ba nhóm workload **web-prod**, **api-prod**, **db-prod** trong một môi trường production. Web gọi API qua TCP/8080; API gọi DB qua TCP/5432. Nhóm dev chạy trong môi trường khác và không cần truy cập DB production. API cần DNS và gửi log tới collector nội bộ.

Hãy lập policy theo hướng:

| Luồng | Kỳ vọng | Lý do |
| --- | --- | --- |
| web-prod → api-prod:8080 | Allow | Giao tiếp nghiệp vụ |
| api-prod → db-prod:5432 | Allow | Truy cập dữ liệu theo vai trò |
| web-prod → db-prod:5432 | Deny | Không có quan hệ trực tiếp |
| dev → db-prod:5432 | Deny | Tách môi trường phát triển và sản xuất |
| api-prod → DNS nội bộ:53 | Allow theo nhu cầu | Phân giải tên |
| api-prod → collector:port được phê duyệt | Allow | Thu thập giám sát |
| unknown workload → cổng quản trị | Deny | Chặn quản trị trái phép |

### Câu hỏi tự kiểm tra

1. Tại sao một rule “toàn bộ subnet web được truy cập toàn bộ subnet DB” có thể quá rộng?
2. Workload đổi IP khi autoscaling thì nhóm chính sách dựa trên label/tag có thể giúp gì? Điều kiện để tin cậy tag là gì?
3. Vì sao Kubernetes default-deny mà không có policy DNS có thể làm ứng dụng lỗi, dù các cổng nghiệp vụ đã được mở?
4. Nếu pod API được allow egress đến DB nhưng DB không có allow ingress, kết quả kỳ vọng là gì khi hai pod đều bị cô lập?
5. Một attacker chiếm được frontend nhưng không truy cập DB trực tiếp được: segmentation đã giảm nguy cơ gì, và còn đường rủi ro nào?
6. Làm thế nào kiểm chứng chính sách có hiệu lực, thay vì chỉ thấy đối tượng rule tồn tại trong hệ thống quản trị?

**Gợi ý:** (1) Rule cấp quyền cả cho máy không có quan hệ nghiệp vụ. (2) Chính sách đi theo nhóm workload khi IP đổi, nhưng quyền sửa nhãn phải được kiểm soát. (3) Truy vấn tên tới DNS bị chặn. (4) Kết nối bị chặn tại ingress của DB, trừ khi policy khác cho phép. (5) Giảm đường di chuyển ngang trực tiếp, nhưng attacker vẫn có thể lợi dụng luồng frontend → API hợp lệ. (6) Thử allow/deny từ đúng nguồn, đối chiếu log điểm thực thi và sức khỏe ứng dụng.

## 13. Tổng kết

**Segmentation theo workload** dùng vai trò và quan hệ nghiệp vụ để giới hạn kết nối giữa các thành phần, đồng thời giữ sự liên tục khi workload thay đổi vị trí hoặc địa chỉ. Muốn áp dụng đúng cần **inventory**, **ma trận luồng được phê duyệt**, **điểm thực thi thực sự nhìn thấy lưu lượng**, **kiểm soát danh tính/metadata**, thử nghiệm allow/deny và giám sát drift.

Trong **SECURITY_NETWORK_SECURITY**, đây là một thành phần của phòng vệ nhiều lớp: segmentation giúp hạn chế di chuyển ngang, firewall quyết định lưu lượng mạng, VPN bảo vệ các đường truyền theo cấu hình, xác thực và phân quyền kiểm soát việc sử dụng dịch vụ, còn IDS/IPS và telemetry giúp quan sát hành vi bất thường. Phòng vệ hiệu quả hình thành khi những lớp đó vận hành nhất quán trên hệ thống on-premises, container và cloud.

### Tài liệu tra cứu

- **NIST SP 800-207 — Zero Trust Architecture**: tư duy về ranh giới tin cậy, tài nguyên và yêu cầu truy cập.
- **NIST SP 800-125B — Secure Virtual Network Configuration for Virtual Machine (VM) Protection**: bảo vệ mạng ảo của môi trường VM.
- **Kubernetes Documentation — Network Policies**: policyTypes, podSelector, namespaceSelector, ingress/egress và các giới hạn của API chuẩn.
- **Kubernetes Documentation — Services, Networking, DNS**: đường đi Service, discovery và các thành phần mạng liên quan.
- **NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy**: nguyên tắc xây dựng và quản trị luật firewall.
