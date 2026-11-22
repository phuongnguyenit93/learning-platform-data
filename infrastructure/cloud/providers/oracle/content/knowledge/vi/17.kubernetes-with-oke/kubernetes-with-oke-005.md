# OCI VCN-Native Pod Networking và Flannel

Trong chương **Kubernetes với OKE** của module **CLOUD_PROVIDERS_ORACLE**, mạng Pod cần được thiết kế cùng tenancy, compartment, IAM, VCN và Compute. Lựa chọn mạng ảnh hưởng trực tiếp tới số địa chỉ IP phải dự phòng, đường kết nối tới cơ sở dữ liệu Oracle, khả năng giám sát lưu lượng và cách mở rộng cluster.

Bài này giải thích hai mô hình **OCI VCN-Native Pod Networking** và **Flannel overlay**, từ đường đi gói tin đến quy hoạch CIDR và kiểm tra kết nối. Phần thực hành dùng một cluster đã có; các ví dụ không yêu cầu tạo hạ tầng mới để hiểu sự khác biệt.

## 1. Mục tiêu và phạm vi

Sau bài học, bạn có thể:

- Phân biệt IP của worker, IP của Pod, ClusterIP của Service và địa chỉ Kubernetes API endpoint.
- Giải thích vì sao Pod dùng VCN-native có thể được định tuyến trong mạng OCI, trong khi Pod Flannel nằm trong overlay.
- Tính dung lượng địa chỉ cho tăng trưởng, rollout và thay worker.
- Phân biệt định tuyến, quy tắc mạng OCI, NetworkPolicy và quyền quản trị.
- Kiểm tra lần lượt DNS, Service, kết nối Pod và kết nối tới dịch vụ ngoài cluster.

Các ví dụ tập trung vào **IPv4**, Pod thông thường và managed nodes. Pod dùng hostNetwork, virtual nodes và thiết kế nhiều interface cần đối chiếu thêm điều kiện hỗ trợ tương ứng. Bạn nên biết Pod, Service, Deployment, CIDR, subnet và route table.

## 2. CNI làm gì trong mạng Kubernetes?

**Container Network Interface — CNI** là giao diện để hệ thống container tích hợp thành phần cấu hình mạng cho Pod. Trong OKE, loại mạng được chọn khi tạo cluster quyết định plugin phục vụ Pod networking.

Theo tài liệu Oracle được đối chiếu ngày **20/11/2026**, các node pools trong một cluster dùng cùng CNI đã chọn; không đổi trực tiếp plugin đó sau khi tạo cluster. Vì vậy, không thiết kế một managed pool dùng Flannel và một pool khác dùng OCI VCN-native trong cùng cluster để chuyển đổi dần. [Nguồn: Pod Networking](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengpodnetworking.htm).

Cần tách các miền địa chỉ sau:

| Thành phần | Vai trò | Ví dụ minh họa |
| --- | --- | --- |
| VCN CIDR | Không gian địa chỉ mạng OCI | 10.40.0.0/16 |
| Worker subnet | Địa chỉ dùng cho mạng của worker | 10.40.16.0/24 |
| Pod subnet của VCN-native | Địa chỉ VCN được cấp cho Pod | 10.40.32.0/22 |
| Pod CIDR của Flannel | Không gian địa chỉ overlay của Pod | 10.244.0.0/16 |
| Service CIDR | Địa chỉ ảo cho Kubernetes Services | 10.96.0.0/16 |
| API endpoint subnet | Địa chỉ tiếp nhận Kubernetes API | 10.40.0.0/28 |

Các dải trên là ví dụ cho bài học, không phải giá trị mặc định bắt buộc. Khi dùng VCN-native, không tạo thêm Flannel Pod CIDR; khi dùng Flannel, không cần pod subnet VCN-native chỉ để cấp IP cho các Pod thông thường.

**ClusterIP không phải IP của Pod.** Service cung cấp điểm truy cập logic tới các backend, thường được theo dõi qua EndpointSlices. Một Service thông thường giữ địa chỉ truy cập trong suốt vòng đời của nó dù các Pod phía sau thay đổi. [Nguồn: Kubernetes Service](https://kubernetes.io/docs/concepts/services-networking/service/).

Do đó, một Pod có IP định tuyến được trong VCN không làm ClusterIP tự trở thành địa chỉ VCN. Cũng không nên dùng IP của một Pod cụ thể làm địa chỉ cấu hình lâu dài cho ứng dụng khác.

## 3. Flannel: mạng overlay chạy trên mạng worker

### 3.1. Cách cấp địa chỉ và truyền gói tin

Flannel cấp địa chỉ Pod từ một không gian overlay riêng, không lấy địa chỉ Pod từ VCN CIDR. Trong mô hình OKE này, Pod overlay không được truy cập trực tiếp từ một Compute instance bên ngoài cluster chỉ nhờ định tuyến VCN. Flannel dùng được với managed nodes và self-managed nodes trong phạm vi hỗ trợ; không dùng với virtual node pools. [Nguồn: Using the flannel CNI plugin](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengpodnetworking_topic-flannel_CNI_plugin.htm).

Xét ví dụ hai Pod trên hai worker:

~~~text
Worker A: 10.40.16.10
Pod A:    10.244.1.5

Worker B: 10.40.16.11
Pod B:    10.244.2.9
~~~

Đường truyền liên node có thể hình dung thành hai lớp:

1. Gói tin bên trong biểu diễn kết nối từ Pod A tới Pod B.
2. Lớp truyền overlay đưa gói tin qua mạng worker A tới worker B.
3. Worker đích xử lý lớp overlay và chuyển gói tin tới Pod B.

Trong Flannel của OKE, cơ chế VXLAN tạo lớp đóng gói này. VCN vận chuyển lưu lượng giữa các worker, còn overlay xử lý địa chỉ Pod phía trong. [Nguồn: Large Cluster Best Practices](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Large-Scale-Clusters-best-practices.htm).

~~~mermaid
flowchart LR
    A["Pod A<br/>10.244.1.5"] --> B["Worker A<br/>10.40.16.10"]
    B --> C["Gói overlay qua mạng VCN"]
    C --> D["Worker B<br/>10.40.16.11"]
    D --> E["Pod B<br/>10.244.2.9"]
~~~

Sơ đồ minh họa lưu lượng **khác node**. Hai Pod cùng node có thể sử dụng đường truyền cục bộ; không dùng kết quả kiểm tra cùng node để khẳng định mạng liên node đã hoạt động.

### 3.2. Hệ quả thiết kế

Flannel giúp tách ngân sách địa chỉ Pod khỏi ngân sách địa chỉ VCN. Tuy nhiên, vẫn phải dự phòng đủ worker IP, overlay CIDR, Service CIDR và dung lượng mạng của máy chủ.

Nếu một máy ứng dụng ngoài cluster cần gọi order-api, phương án thông thường là một điểm truy cập Service/Ingress/load balancer phù hợp. Chỉ thêm route tới 10.244.0.0/16 không biến Flannel thành VCN-native hay tự tạo được đường truyền hai chiều.

Đối với Pod gọi database bên ngoài, cần xác minh cách egress và masquerade đang hoạt động. Nếu đường đi có SNAT, database nhìn thấy địa chỉ sau dịch. Khi cấu hình allowlist hoặc điều tra lỗi, dùng địa chỉ quan sát thực tế; không mặc định database luôn thấy nguyên IP overlay.

### 3.3. Overlay không đồng nghĩa mã hóa hoặc cô lập hoàn toàn

Đóng gói gói tin và mã hóa nội dung là các cơ chế khác nhau. Không coi VXLAN là thay thế cho TLS giữa ứng dụng và database.

Tương tự, việc Pod nằm trong overlay không tự thực thi quy tắc “frontend được gọi backend, namespace khác bị chặn”. Muốn điều khiển ở mức workload, cần cơ chế policy có thực thi phù hợp với cluster.

## 4. OCI VCN-Native: Pod nhận địa chỉ trong mạng VCN

### 4.1. Mô hình cơ bản

OCI VCN-Native Pod Networking cấp IP Pod từ không gian địa chỉ VCN. Tài nguyên trong VCN, VCN được kết nối và mạng on-premises có thể định tuyến tới IP Pod khi đường mạng cùng các quy tắc truy cập cho phép.

Với managed nodes, mạng worker dùng primary VNIC; mạng Pod dùng các secondary VNIC theo cấu hình được hỗ trợ. Pod subnet là private regional subnet. [Nguồn: Using the OCI VCN-Native Pod Networking CNI plugin](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengpodnetworking_topic-OCI_CNI_plugin.htm).

Ví dụ:

~~~text
Worker A: 10.40.16.10
Pod A:    10.40.32.20

Worker B: 10.40.16.11
Pod B:    10.40.32.21
~~~

Lưu lượng Pod A tới Pod B đi theo tích hợp mạng VCN, thay vì cần thêm lớp overlay Flannel. Đường truyền vẫn có thành phần mạng trên host và các quy tắc tương ứng; từ “native” không có nghĩa mọi kiểm tra trên worker đều có thể bỏ qua.

~~~mermaid
flowchart LR
    A["Pod A<br/>10.40.32.20"] --> B["Mạng Pod qua VNIC"]
    B --> C["VCN và quy tắc truy cập"]
    C --> D["Mạng Pod qua VNIC"]
    D --> E["Pod B<br/>10.40.32.21"]
    C --> F["Database private endpoint<br/>khi có đường mạng và quyền"]
~~~

### 4.2. Định tuyến được chưa có nghĩa truy cập được

Một client ở mạng on-premises muốn gọi Pod cần giải quyết đồng thời:

- Địa chỉ nguồn và đích không xung đột với không gian địa chỉ đang dùng.
- Kết nối mạng và route cho cả chiều đi lẫn chiều về.
- Các lớp lọc mạng cho phép đúng giao thức và cổng.
- Ứng dụng đang lắng nghe ở interface, cổng phù hợp.
- Xác thực và TLS đúng với thiết kế ứng dụng.

Giả sử TCP tới IP Pod thành công nhưng yêu cầu HTTPS thất bại do hostname không khớp chứng thư. Khi đó, đường truyền IP đã hoạt động; sửa route table không giải quyết được lỗi tên máy trong TLS.

VCN-native cũng không có nghĩa Pod được cấp public IP để internet truy cập trực tiếp. Phương án công khai ứng dụng vẫn phải thiết kế rõ điểm vào và lớp bảo vệ.

### 4.3. Không áp dụng một con số IP/VNIC cũ cho mọi cấu hình

OCI đã bổ sung khả năng gắn nhiều secondary VNIC profiles cho Pod networking. Mỗi profile có cấu hình subnet, NSG và phân bổ IP riêng; khả năng này yêu cầu VCN-native, đồng thời chịu giới hạn shape và các điều kiện dịch vụ. [Nguồn: OKE support for multiple secondary VNIC attachments](https://docs.oracle.com/en-us/iaas/releasenotes/conteng/conteng-Generic-VNIC-attachments.htm).

Khi dùng các profile này, cần tính theo cấu hình **ipCount**, năng lực mạng của shape, giới hạn Pod thực tế và phiên bản CNI. Nếu dùng Application Resources để chọn profile, dung lượng khả dụng còn phụ thuộc profile được yêu cầu. Nhiều interface cho một Pod qua Multus là thiết kế khác với chọn một profile cho đường mạng chính. [Nguồn: Attaching Multiple Secondary VNICs for Pod Networking](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengAttaching_Multiple_VNICs.htm).

Vì vậy, đừng lấy một công thức mật độ Pod từ tài liệu cũ rồi áp dụng cho mọi node pool. Trước khi chọn shape hoặc tăng max-pods, phải kiểm tra cả dung lượng IP được cấu hình lẫn phiên bản và tính năng đang dùng.

## 5. So sánh và chọn mô hình theo yêu cầu

| Tiêu chí | OCI VCN-Native | Flannel |
| --- | --- | --- |
| Không gian IP Pod | Thuộc VCN | Overlay riêng |
| Kết nối trực tiếp từ mạng ngoài cluster | Có thể định tuyến khi đáp ứng điều kiện | Không cung cấp khả năng trực tiếp tương đương |
| Ngân sách IP VCN | Cần tính cả địa chỉ phục vụ Pod | Chủ yếu tính tài nguyên OCI, còn Pod dùng overlay |
| Đường truyền khác worker | Tích hợp mạng VCN | Có lớp đóng gói overlay |
| Quan sát ở lớp VCN | Có thể liên hệ lưu lượng với IP Pod tại điểm quan sát phù hợp | Cần kết hợp thông tin worker và lớp overlay |
| Yêu cầu vận hành nổi bật | Dung lượng subnet, VNIC, IP allocation | Overlay CIDR, mạng liên worker và đóng gói |
| Virtual node pools | Phương án mạng được yêu cầu | Không phù hợp |

Điều kiện virtual nodes được mô tả trong quy trình tạo virtual node pools của Oracle. [Nguồn: Creating Virtual Nodes and Virtual Node Pools](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcreatingvirtualnodes_topic.htm).

Các tình huống sau minh họa cách áp dụng, không phải kết luận mặc định cho mọi cluster:

- **Đội mạng cần theo dõi và quản lý luồng Pod trong kiến trúc OCI:** đánh giá VCN-native, đồng thời xác minh cách nhận diện workload khi Pod thay địa chỉ.
- **Không gian IP VCN hạn chế, ứng dụng chủ yếu giao tiếp trong cluster:** đánh giá Flannel cùng ngân sách overlay và nhu cầu kết nối ngoài cluster.
- **Hệ thống dự kiến dùng virtual nodes:** đưa yêu cầu VCN-native vào thiết kế ngay từ đầu.
- **Ứng dụng có yêu cầu thông lượng hoặc độ trễ chặt:** thử nghiệm cùng workload, cùng shape, cùng topology và mức tải. Không kết luận chỉ từ việc có hoặc không có overlay.
- **Cluster lớn hoặc mạng nhiều interface:** đối chiếu tài liệu riêng cho quy mô và tính năng đó; phạm vi bài này không thay thế thiết kế chi tiết.

Oracle cũng khuyến nghị chọn CNI theo yêu cầu địa chỉ và đặc tính ứng dụng. [Nguồn: Networking Best Practices](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengbestpractices_topic-Networking-best-practices.htm).

## 6. Quy hoạch CIDR và dung lượng IP

### 6.1. Ngăn chồng lấn từ đầu

Với Flannel, VCN CIDR không được chồng với Pod CIDR và Service CIDR. Với VCN-native, Pod dùng subnet trong VCN, còn Service CIDR phải tách khỏi VCN. Cũng cần tránh xung đột với mạng được kết nối như on-premises. [Nguồn: IPv4 CIDR Blocks and Kubernetes Engine](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengcidrblocks.htm).

Ví dụ một kế hoạch IPv4:

| Mục đích | Dải minh họa | Ghi chú |
| --- | --- | --- |
| VCN | 10.40.0.0/16 | Chứa các subnet OCI của ví dụ |
| API endpoint | 10.40.0.0/28 | Tách địa chỉ quản trị |
| Load balancer | 10.40.1.0/24 | Chọn private/public theo cách truy cập ứng dụng |
| Worker | 10.40.16.0/24 | Tính cả node tạo thêm lúc cập nhật |
| Pod VCN-native | 10.40.32.0/22 | Chỉ dùng trong phương án VCN-native |
| Pod Flannel | 10.244.0.0/16 | Chỉ dùng trong phương án Flannel |
| Kubernetes Service | 10.96.0.0/16 | Tách khỏi các mạng đã nêu |
| On-premises | 172.20.0.0/16 | Giả định để kiểm tra kết nối hybrid |

Bảng không chứng minh các dải này còn trống trong tenancy của bạn. Phải đối chiếu với kế hoạch địa chỉ của tổ chức và các kết nối hiện có.

Ví dụ, nếu on-premises đã dùng 10.244.0.0/16, việc lấy dải đó làm overlay có thể khiến một Pod định tuyến sai khi gọi một máy ngoài cluster trùng địa chỉ. Overlay không loại bỏ bài toán xung đột IP.

### 6.2. Tính theo đỉnh tài nguyên, không chỉ theo Pod đang chạy

Với VCN-native, cần ước tính địa chỉ **được cấp hoặc giữ chỗ** theo cơ chế hiện hành, thay vì chỉ đếm Pod Running. Một khung tính:

~~~text
Ngân sách pod subnet tối thiểu =
    địa chỉ Pod được phân bổ cho các worker tại thời điểm đỉnh
  + địa chỉ VNIC và tài nguyên cùng dùng subnet chưa nằm trong phần trên
  + địa chỉ do nền tảng giữ lại
  + dự phòng tăng trưởng và sai lệch ước tính
~~~

Điểm đỉnh có thể xảy ra khi:

- Cluster Autoscaler tăng worker.
- Deployment tạo Pod mới trước khi Pod cũ kết thúc.
- Quy trình cập nhật giữ đồng thời worker cũ và mới.
- Một pool khác dùng chung pod subnet mở rộng.
- Pod hoặc worker mất nhiều thời gian hoàn tất thu hồi tài nguyên.

Một cluster còn CPU không đảm bảo còn IP. Ngược lại, subnet còn nhiều IP không chứng minh shape hoặc cấu hình worker cho phép nhận thêm Pod.

### 6.3. Ví dụ sizing VCN-native

Giả sử một thiết kế đã xác nhận tương thích có:

- Tối đa 20 worker khi tải cao.
- Thêm tối đa 4 worker tạm thời trong quá trình cập nhật.
- Ngân sách cấp IP phục vụ Pod đã xác nhận là 32 địa chỉ mỗi worker, cho cùng pod subnet.

Phần địa chỉ phục vụ Pod tại đỉnh là:

~~~text
Worker tại đỉnh = 20 + 4 = 24
Ngân sách IP Pod = 24 × 32 = 768 địa chỉ
~~~

Với một subnet IPv4 một CIDR theo mô hình thông thường, OCI giữ lại ba địa chỉ. Ví dụ /23 có 512 địa chỉ tổng, còn 509 trước các phân bổ khác; /22 có 1.024 địa chỉ tổng, còn 1.021. [Nguồn: Identify VCN Topology and Specifications](https://docs.oracle.com/en/solutions/oci-best-practices-networking/identify-vcn-topology-and-specifications1.html).

Theo các giả định này:

- /23 không đủ cho riêng ngân sách 768 IP Pod.
- /22 còn 253 địa chỉ sau phần IP Pod và ba địa chỉ giữ lại.
- Phải trừ tiếp phần địa chỉ VNIC, tài nguyên dùng chung hoặc phân bổ khác chưa được tính.

Đây là phép tính minh họa. Con số 32 không phải mặc định bắt buộc của OKE, cũng không phải cam kết mỗi worker luôn dùng đúng 32 địa chỉ. Lấy cấu hình và số liệu tiêu thụ thực tế để thay vào phép tính; nếu một địa chỉ đã nằm trong ngân sách đã đo thì không cộng lần hai.

Đối với nhiều pod subnets hoặc VNIC profiles, lập ngân sách cho từng subnet và từng nhóm cấp phát. Tổng IP toàn VCN còn dư không giúp được một profile đã cạn địa chỉ trong subnet của nó.

### 6.4. Flannel cũng có giới hạn do cách chia dải

Theo mô hình IPv4 Flannel trong tài liệu OKE, mỗi worker được cấp một khối /25 từ Pod CIDR. Vì thế, tổng số IP toàn overlay không phải số Pod có thể sử dụng tùy ý trên mọi node. [Nguồn: IPv4 CIDR Blocks and Kubernetes Engine](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengcidrblocks.htm).

Ví dụ tự tính:

~~~text
Pod CIDR /20 có 4.096 địa chỉ
Mỗi khối /25 có 128 địa chỉ

Số khối /25 trong /20 = 4.096 / 128 = 32
~~~

Nếu kế hoạch cần 30 worker thường trực và 4 worker tạm thời, 32 khối không đủ cho 34 worker, dù số Pod đang chạy còn ít. Đây là giới hạn theo phân hoạch địa chỉ của ví dụ; số node được hỗ trợ cuối cùng còn chịu các giới hạn OKE khác.

Worker cũng có giới hạn số Pod, CPU và bộ nhớ riêng. Không lấy 128 địa chỉ của một /25 làm số Pod vận hành mục tiêu trên node.

## 7. Thiết kế đường truyền và các lớp kiểm soát

### 7.1. Mỗi lớp trả lời một câu hỏi khác nhau

| Lớp | Câu hỏi |
| --- | --- |
| OCI IAM | Chủ thể nào được tạo hoặc thay đổi tài nguyên OCI? |
| Kubernetes RBAC | Chủ thể nào được thao tác tài nguyên Kubernetes? |
| Route | Gói tin có đường tới đích và quay về không? |
| NSG/security list | Lớp mạng OCI có cho phép luồng đó không? |
| NetworkPolicy có engine thực thi | Những Pod nào được giao tiếp theo chính sách Kubernetes? |
| Ứng dụng và TLS | Kết nối có đúng giao thức, danh tính và quyền nghiệp vụ không? |

Một tài khoản có quyền xem Pod không vì thế được gọi database. Một route tồn tại không thay thế rule cho phép kết nối. Một rule mạng cho phép TCP cũng không thay thế việc xác thực người dùng.

Trong tenancy có mạng và cluster ở các compartment khác nhau, cần xác định chủ thể nào sử dụng subnet, quản lý các thành phần mạng và cấp tài nguyên. Phân quyền đúng phạm vi; không mở rộng quyền toàn tenancy chỉ để bỏ qua lỗi thiếu quyền mà chưa xác định thao tác bị từ chối.

### 7.2. NSG và security list không thay thế route

Security list áp dụng theo subnet; NSG gắn với nhóm VNIC hoặc tài nguyên được hỗ trợ. Khi cùng dùng nhiều NSG và security lists, cần xem tổng hợp các rule cho phép đang áp dụng; một rule rộng ở nơi khác có thể vẫn cho phép lưu lượng. Stateful và stateless cũng khác nhau về xử lý lưu lượng phản hồi. [Nguồn: Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Với VCN-native, hãy kiểm tra đúng VNIC hoặc profile phục vụ Pod. Sửa NSG của primary VNIC worker chưa chắc tác động tới đường mạng Pod cần sửa.

Với Flannel, rule ở lớp VCN phải cho phép luồng phục vụ mạng liên worker. Không suy ra NSG có thể hiểu labels Kubernetes bên trong gói overlay và thực thi trực tiếp chính sách frontend/backend.

Oracle công bố bộ yêu cầu mạng cho API endpoint, worker và Pod theo từng mô hình. Cần áp dụng đủ các luồng nền tảng, gồm giao tiếp API, kubelet, khám phá đường truyền và các phụ thuộc dịch vụ. Một rule ứng dụng đơn lẻ không thay thế cấu hình OKE hoàn chỉnh. [Nguồn: Network Resource Configuration](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengnetworkconfig.htm).

### 7.3. Egress tới internet và dịch vụ Oracle

NAT Gateway cho tài nguyên không có public IP mở kết nối ra internet và nhận lưu lượng phản hồi. Nó không cung cấp một điểm vào internet tùy ý cho Pod. [Nguồn: NAT Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/NATgateway.htm).

Service Gateway cung cấp đường riêng tới các Oracle services được hỗ trợ qua Oracle Services Network. Nó không phải đường thay thế chung cho mọi đích internet hoặc mọi private endpoint. [Nguồn: Access to Oracle Services](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/servicegateway.htm).

Một bảng kiểm tra theo luồng có thể như sau:

| Luồng | Điều phải xác minh |
| --- | --- |
| Worker kéo container image | Đường mạng từ worker, DNS và xác thực registry |
| Pod gọi API công khai | Egress của Pod theo mô hình CNI, route và quy tắc mạng |
| Pod gọi Oracle service | Endpoint cụ thể và đường truy cập dịch vụ phù hợp |
| Pod gọi Oracle Database private endpoint | Phân giải tên private, route hai chiều, rule database và TLS |
| Client gọi ứng dụng từ ngoài cluster | Điểm vào đã công bố, backend khỏe và đường phản hồi |

Nếu container không kéo được image, ứng dụng chưa bắt đầu chạy. Khi đó, kiểm tra đường mạng từ worker và registry trước khi đổ lỗi cho egress của mã ứng dụng.

### 7.4. NetworkPolicy phải có cơ chế thực thi

Tạo được tài nguyên NetworkPolicy không chứng minh traffic đã bị chặn. Cluster cần thành phần thực thi tương thích. Các policy cho phép có tính cộng dồn; phải xét cả các policy khác đang chọn cùng Pod. [Nguồn: Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

Oracle có hướng dẫn dùng Calico làm network policy engine cho các cấu hình OKE phù hợp. Điều này là bổ sung chính sách, không phải tự thay CNI cấp IP của cluster. Không áp dụng quy trình cho managed nodes vào virtual nodes mà chưa kiểm tra hỗ trợ. [Nguồn: Installing Calico and Setting Up Network Policies](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengsettingupcalico.htm).

Ví dụ sau dành cho lab đã có policy engine hoạt động. Nó chọn Pod mang label app=order-api trong namespace net-lab, cho phép ingress TCP/8080 từ Pod mang label app=frontend trong cùng namespace:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: order-api-from-frontend
  namespace: net-lab
spec:
  podSelector:
    matchLabels:
      app: order-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8080
~~~

Mẫu không cấu hình egress, không chọn mọi Pod trong namespace và chưa mô tả các luồng health check hoặc quản trị. Cần đánh giá các luồng đó trước khi dùng cho ứng dụng thực.

Để kiểm tra tác dụng, gửi cùng một yêu cầu từ frontend và từ một Pod khác không được chọn. Kết quả âm chỉ có ý nghĩa khi đã biết ứng dụng đích khỏe, kết nối trước policy hoạt động và không có rule khác cho phép.

## 8. Thực hành quan sát cấu hình mạng trên OKE

### 8.1. Điều kiện

Người thực hành cần OCI CLI đã xác thực đúng tenancy, profile, region; quyền đọc cluster, node pool và subnet; kubeconfig đúng cluster; cùng đường kết nối tới Kubernetes API.

Phần kiểm tra lưu lượng giả định môi trường lab đã có namespace net-lab, Pod client-a, Pod chạy order-api và Service order-api. Client cần có công cụ kiểm tra phù hợp. Đây là tài nguyên giả định của bài, không phải tài nguyên OKE tự tạo.

### 8.2. Đọc cấu hình từ OCI

Các lệnh PowerShell sau chỉ đọc cấu hình. Thay các giá trị giữ chỗ bằng tài nguyên được giao trong lab.

~~~powershell
$ClusterId = "<OCID_CLUSTER>"
$NodePoolId = "<OCID_MANAGED_NODE_POOL>"
$SubnetId = "<OCID_SUBNET_CAN_KIEM_TRA>"

oci ce cluster get --cluster-id $ClusterId
oci ce node-pool get --node-pool-id $NodePoolId
oci network subnet get --subnet-id $SubnetId
~~~

Nguồn lệnh: [cluster get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ce/cluster/get.html), [node-pool get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ce/node-pool/get.html), [subnet get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/subnet/get.html).

Ghi lại:

- Loại CNI trong cấu hình Pod networking: OCI_VCN_IP_NATIVE hoặc FLANNEL_OVERLAY.
- VCN, worker subnets và cấu hình mạng Pod liên quan.
- Shape, giới hạn Pod và IP allocation theo cấu hình thực tế.
- CIDR, route table và security lists của subnet.
- NSG của những VNIC hoặc profile thực sự nằm trên đường cần kiểm tra.

Không lấy việc một subnet có tên chứa “pod” làm bằng chứng cluster đang dùng VCN-native. Tên là nhãn do người vận hành đặt; cấu hình và địa chỉ thực tế mới là căn cứ.

### 8.3. Đối chiếu Kubernetes

~~~powershell
kubectl config current-context
kubectl get nodes -o wide
kubectl get nodes -o custom-columns='NAME:.metadata.name,PODCIDR:.spec.podCIDR,PODS:.status.allocatable.pods'
kubectl get pods -A -o wide
kubectl get daemonsets -n kube-system
kubectl get events -n kube-system --sort-by=.metadata.creationTimestamp
~~~

Với Pod thông thường trong ví dụ:

- VCN-native: đối chiếu Pod IP với các CIDR của pod subnet/profile.
- Flannel: đối chiếu Pod IP với overlay Pod CIDR.
- Đối chiếu Pod với node đang chạy để phân biệt cùng node và khác node.

PodCIDR trên Node có thể không cung cấp cùng ý nghĩa trong mọi CNI. Một trường không có giá trị không đủ để kết luận lỗi mạng. Tương tự, không chỉ dựa vào tên DaemonSet để suy ra toàn bộ trạng thái CNI; cần xem cấu hình add-on và phiên bản thực tế.

### 8.4. Kiểm tra theo đường truyền

Trước tiên xác nhận backend và Service:

~~~powershell
kubectl get pods -n net-lab -o wide
kubectl get service order-api -n net-lab -o wide
kubectl get endpointslices -n net-lab -l kubernetes.io/service-name=order-api -o wide
kubectl get networkpolicies -n net-lab
~~~

Nếu image client có nslookup và wget, có thể dùng:

~~~powershell
kubectl exec -n net-lab client-a -- nslookup order-api.net-lab.svc.cluster.local
kubectl exec -n net-lab client-a -- wget -qO- -T 5 http://order-api:8080/health
~~~

Ví dụ giả định Service lắng nghe 8080 và ứng dụng có đường dẫn /health. Thay bằng cổng, tên miền cluster và endpoint thực tế. Không diễn giải việc image thiếu công cụ thành lỗi CNI.

Lập bảng kiểm tra:

| Bước | Mục đích | Gợi ý đọc kết quả |
| --- | --- | --- |
| Gọi ứng dụng bằng Pod IP cùng node | Kiểm tra ứng dụng và đường cục bộ | Thành công chưa chứng minh liên node |
| Gọi Pod IP khác node | Kiểm tra đường truyền liên worker | So sánh với cùng node để thu hẹp phạm vi |
| Gọi bằng ClusterIP | Kiểm tra thêm lớp Service | Đối chiếu EndpointSlices và port/targetPort |
| Gọi bằng DNS Service | Kiểm tra thêm phân giải tên | Phân biệt lỗi DNS với lỗi TCP |
| Gọi database từ môi trường ứng dụng | Kiểm tra kết nối ngoài cluster | Tách timeout, từ chối TCP, TLS và lỗi đăng nhập |

Khi kiểm tra Pod IP, lấy địa chỉ hiện tại từ kết quả Kubernetes và gọi đúng cổng container. Khi kiểm tra Service, dùng đúng Service port. Hai cổng có thể khác nhau.

Một số đường quản trị như kubectl port-forward không đi qua toàn bộ đường truy cập của client ứng dụng. Thành công qua port-forward không chứng minh đường mạng từ một Pod khác, load balancer hoặc on-premises đã hoạt động.

## 9. Chẩn đoán theo triệu chứng

### 9.1. Pod chưa khởi động được mạng

Nếu sự kiện có FailedCreatePodSandBox hoặc lỗi CNI/IPAM:

1. Lấy thông báo đầy đủ và thời điểm xảy ra.
2. Xác định node, pool và phiên bản CNI liên quan.
3. Với VCN-native, kiểm tra IP allocation, subnet còn địa chỉ, VNIC và quyền thao tác liên quan.
4. Với Flannel, kiểm tra trạng thái thành phần mạng, cấp khối overlay và node.
5. So sánh với một Pod mới tạo thành công trên node khác để tìm phạm vi lỗi.

Tăng CPU request hoặc số replica không xử lý trực tiếp lỗi cấp địa chỉ. Việc xóa rồi tạo lại Pod liên tục cũng có thể làm mất dấu sự kiện mà chưa sửa nguyên nhân.

### 9.2. Cùng node chạy được, khác node thất bại

Triệu chứng này gợi ý kiểm tra đường truyền liên node và cấu hình riêng của node lỗi:

- Flannel: tình trạng overlay, forwarding và khả năng truyền gói giữa worker.
- VCN-native: đường mạng của Pod VNIC/profile và các quy tắc đang áp dụng.
- Cả hai: policy workload, firewall trên host và khác biệt cấu hình giữa các node.

Không tự mở tất cả cổng ra internet để thử. Trước hết xác định nguồn, đích, giao thức và lớp đang từ chối; áp dụng thay đổi đúng phạm vi của lab.

### 9.3. DNS đúng nhưng kết nối ứng dụng thất bại

Phân giải tên chỉ chứng minh một phần đường truyền DNS. Cần kiểm tra tiếp:

- Service có chọn đúng labels không?
- Có backend Ready phù hợp không?
- Service port có ánh xạ đúng targetPort không?
- Tiến trình có lắng nghe trên địa chỉ phù hợp không?
- TCP có bị chặn trước khi tới ứng dụng không?

Nếu truy cập bằng Pod IP thành công nhưng ClusterIP thất bại, ưu tiên kiểm tra lớp Service và thành phần xử lý Service trong cấu hình cluster đang dùng.

### 9.4. Kết nối nhỏ được, truyền dữ liệu lớn bị treo

Đây là tình huống cần xem xét MTU, Path MTU Discovery, ICMP và các lớp tunnel trên toàn tuyến. Overlay có overhead đóng gói; tuyến hybrid cũng có thể thêm lớp truyền riêng.

Không thay một giá trị MTU trên toàn cluster chỉ từ triệu chứng này. Cần đo và đối chiếu đường truyền thực, vì lỗi cũng có thể đến từ timeout, proxy hoặc ứng dụng.

### 9.5. Dùng flow logs đúng giới hạn

VCN Flow Logs giúp đối chiếu luồng mạng với trạng thái accepted/rejected tại lớp VCN. Nó không thay thế application logs hoặc chứng minh giao dịch nghiệp vụ thành công. [Nguồn: Flow Logs](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/vcn-flow-logs.htm).

Khi không tìm thấy bản ghi, kiểm tra enablement point, capture filter, sampling và khoảng thời gian. Không có bản ghi chưa đủ chứng minh không có gói tin. [Nguồn: Enabling Flow Logs](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/vcn-flow-logs-enable.htm).

Với VCN-native, liên hệ IP Pod với namespace, workload và thời điểm tồn tại của Pod. Với Flannel, có thể cần thêm dữ liệu trên host để nối luồng giữa worker với Pod phía trong overlay. Giữ thông tin thời gian nhất quán giữa các nguồn log.

## 10. Tự động hóa, chi phí và khả năng phục hồi

Đưa CNI, CIDR, route và các quy tắc liên quan vào cấu hình hạ tầng có quản lý phiên bản. Khi dùng Terraform hoặc OCI Resource Manager, kiểm tra kế hoạch thay đổi để nhận diện tài nguyên sẽ bị thay thế và dung lượng cần trong quá trình chuyển đổi.

Một bộ biến hạ tầng nên thể hiện rõ:

~~~text
pod_network_model
vcn_address_ranges
worker_subnet_ids
pod_subnet_ids_or_profiles
service_cidr
flannel_pod_cidr_if_used
expected_peak_nodes
update_surge_nodes
pod_ip_budget
network_security_groups
~~~

Đây là danh sách khái niệm cho thiết kế, không phải tên thuộc tính bắt buộc của OCI provider. Chỉ cấu hình các trường phù hợp với mô hình đã chọn; tránh truyền cả hai bộ giá trị như thể cluster chạy đồng thời hai CNI.

Chi phí cần đánh giá gồm Compute do mật độ Pod, khả năng giữ tài nguyên nhàn rỗi, lưu lượng qua các tuyến, điểm truy cập ứng dụng, log và công sức vận hành. Không kết luận một mô hình luôn rẻ hơn chỉ vì giảm số IP VCN hoặc bỏ lớp overlay.

Về tính sẵn sàng, kiểm tra ít nhất các kịch bản:

- Tải cao xảy ra đúng lúc thay worker, làm tăng nhu cầu IP.
- Một nhóm worker mất và Pod cần chuyển sang nhóm còn lại.
- Mạng tới database lỗi trong khi Pod-to-Pod vẫn bình thường.
- DNS lỗi nhưng kết nối tới địa chỉ đã biết vẫn hoạt động.
- Thu hồi Pod/worker chậm làm lượng địa chỉ sử dụng cao hơn dự kiến.

Khi cần chuyển từ Flannel sang VCN-native hoặc ngược lại, lập kế hoạch cluster đích: tạo hạ tầng mạng phù hợp, triển khai lại workload, kiểm tra storage và policy, chuyển lưu lượng rồi mới giải phóng cluster nguồn. Kế hoạch quay lui phải giữ được điểm truy cập và dữ liệu cần thiết trong cửa sổ chuyển đổi.

## 11. Ví dụ quyết định cho ứng dụng Java dùng Oracle Database

Giả sử một hệ thống có order-api, worker xử lý đơn hàng và Oracle Database private endpoint. Đội mạng muốn quan sát luồng ứng dụng trong OCI; số Pod dự kiến tăng theo giờ cao điểm.

Một phương án để đánh giá là VCN-native với pod subnet có dự phòng cho autoscaling và thay worker. Database vẫn được truy cập bằng tên và endpoint dịch vụ phù hợp, thay vì lưu một IP Pod cố định trong cấu hình phía đối tác.

Bản quyết định cần có các bằng chứng sau:

| Quyết định | Bằng chứng |
| --- | --- |
| Dùng VCN-native | Đáp ứng nhu cầu địa chỉ và quản lý luồng trong VCN |
| Cấp đủ IP | Có phép tính theo worker tại đỉnh, IP allocation và tài nguyên dùng chung |
| Kết nối database riêng | DNS, route hai chiều, rule mạng, TLS và xác thực đều được kiểm tra |
| Cô lập workload | Policy engine và các policy được kiểm tra bằng trường hợp được phép/bị chặn |
| Theo dõi mạng | Liên hệ được flow logs, Pod, node và thời điểm xảy ra lỗi |
| Kiểm soát chi phí | Đo tải, mật độ Pod và chi phí hạ tầng đi kèm |
| Có phương án phục hồi | Mô tả rõ hành vi khi thiếu IP, mất worker hoặc lỗi tuyến database |

Nếu tổ chức không còn đủ không gian IP VCN, cần đánh giá lại kế hoạch địa chỉ hoặc phương án Flannel cùng cách công bố dịch vụ. Quyết định mới phải giữ nguyên các mục tiêu ứng dụng, bảo mật và vận hành đã đặt ra.

## 12. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Flannel không cần quy hoạch IP | Vẫn phải quy hoạch overlay, worker và Service CIDR |
| Pod VCN-native là Pod có public IP | Địa chỉ Pod trong bài là private IP của VCN |
| Cùng subnet thì mọi luồng tự được cho phép | Còn các rule mạng, policy và trạng thái ứng dụng |
| Mỗi Pod luôn có một VNIC riêng | Pod IP được quản lý qua cơ chế VNIC/IP allocation của cấu hình đang dùng |
| Một giới hạn Pod/VNIC áp dụng cho mọi phiên bản | Kiểm tra shape, CNI, profile và cấu hình max-pods thực tế |
| Route tới Flannel Pod CIDR là đủ để truy cập ngoài cluster | Overlay cần cách kết nối/công bố dịch vụ phù hợp |
| NetworkPolicy tạo thành công là đã có cô lập | Phải có engine thực thi và kiểm tra cả các policy cộng dồn |
| DNS trả lời là ứng dụng đã truy cập được | Cần kiểm tra tiếp Service, TCP, TLS và quyền ứng dụng |
| Đổi CNI bằng cách thêm pool mới | Lựa chọn CNI thuộc thiết kế cluster; cần kế hoạch chuyển sang cluster phù hợp |
| Node còn CPU thì nhận thêm Pod được | Còn giới hạn IP, Pod count và những ràng buộc scheduling khác |

Lựa chọn mạng cho OKE cần được giải thích bằng đường đi gói tin và ngân sách địa chỉ cụ thể. Khi bạn chỉ ra được nguồn IP, lớp định tuyến, lớp cho phép lưu lượng và cách quan sát lỗi, thiết kế mới đủ cơ sở để mở rộng và vận hành trong hạ tầng OCI.
