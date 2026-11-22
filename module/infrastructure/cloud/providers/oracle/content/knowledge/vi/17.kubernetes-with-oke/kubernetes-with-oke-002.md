# Lựa chọn loại cluster và mô hình quản lý worker nodes

Trong chương **Kubernetes với OKE** của module **CLOUD_PROVIDERS_ORACLE**, lựa chọn hạ tầng Kubernetes cần gắn với tenancy, compartment, IAM, VCN, Compute và lưu trữ của Oracle Cloud Infrastructure. Một cluster chạy được ứng dụng mới chỉ là điểm khởi đầu; thiết kế còn phải trả lời ai nâng cấp worker nodes, tài nguyên được mở rộng thế nào, ứng dụng chịu được sự cố nào và ngân sách được kiểm soát ra sao.

Bài này tập trung vào hai quyết định: chọn **basic cluster hoặc enhanced cluster**, sau đó chọn **managed nodes, virtual nodes hoặc self-managed nodes** phù hợp với workload. Các ví dụ hướng đến hệ thống có dịch vụ Java, tác vụ nền và kết nối tới cơ sở dữ liệu Oracle nằm ngoài cluster.

## 1. Mục tiêu và kiến thức đầu vào

Sau bài học, bạn có thể:

- Phân biệt loại cluster với mô hình quản lý worker nodes và cách công khai Kubernetes API endpoint.
- Chọn phương án dựa trên yêu cầu ứng dụng, trách nhiệm vận hành, chi phí và tính sẵn sàng.
- Thiết kế nhóm worker có khả năng thay thế, mở rộng và phân bố workload có chủ đích.
- Kiểm tra cấu hình OCI cùng trạng thái Kubernetes trước khi kết luận kiến trúc đáp ứng yêu cầu.

Bạn nên biết Pod, Deployment, Service, requests/limits, khái niệm node và cách dùng kubectl. Về OCI, cần hiểu compartment là phạm vi tổ chức và phân quyền tài nguyên, VCN cung cấp mạng riêng, còn compute shape mô tả cấu hình máy tính toán.

## 2. Tách ba câu hỏi thường bị gộp chung

Một quyết định về cluster không thay thế các quyết định về worker và mạng.

| Câu hỏi | Các lựa chọn chính | Điều cần xác định |
| --- | --- | --- |
| Cluster dùng tập tính năng nào? | Basic hoặc enhanced | Tính năng OKE, cam kết dịch vụ và phí cluster |
| Ai quản lý hạ tầng chạy Pod? | Managed, virtual hoặc self-managed nodes | Trách nhiệm đối với máy chủ, dung lượng và vòng đời worker |
| Kubernetes API được truy cập từ đâu? | Endpoint riêng hoặc công khai theo cấu hình được hỗ trợ | Đường kết nối quản trị và quy tắc truy cập |

Ví dụ, enhanced cluster vẫn có thể dùng managed nodes. Chọn enhanced không đồng nghĩa mọi Pod chạy theo mô hình serverless. Ngược lại, chọn private endpoint không quyết định worker do Oracle hay đội của bạn quản lý.

**Control plane** tiếp nhận Kubernetes API và điều phối trạng thái cluster. **Data plane** chạy workload. Trong OKE, Oracle vận hành control plane; phần trách nhiệm còn lại thay đổi theo mô hình worker. Tự quản lý worker không biến control plane OKE thành control plane do bạn tự cài đặt. [Nguồn: OKE Concepts](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengclustersnodes.htm).

~~~mermaid
flowchart TD
    A["Yêu cầu ứng dụng và vận hành"] --> B["Chọn loại cluster"]
    B --> C["Basic"]
    B --> D["Enhanced"]
    C --> E["Managed nodes"]
    D --> F["Managed node pools"]
    D --> G["Virtual node pools"]
    D --> H["Self-managed nodes"]
    F --> I["Phân nhóm và định tuyến workload"]
    G --> I
    H --> I
    E --> I
    I --> J["Kiểm tra chi phí, dung lượng và khả năng phục hồi"]
~~~

## 3. Chọn basic cluster hay enhanced cluster

### 3.1. Khác biệt cần biết

| Khả năng | Basic | Enhanced |
| --- | --- | --- |
| Kubernetes cốt lõi, managed node pools | Có | Có |
| Virtual node pools | Không | Có |
| Self-managed nodes | Không | Có |
| Quản lý add-on nâng cao, workload identity | Không có các tính năng enhanced này | Có |
| Node cycling tích hợp cho managed nodes | Không | Có |
| Cam kết dịch vụ | SLO | SLA có bảo đảm tài chính theo điều khoản |

SLO là mục tiêu mức dịch vụ; SLA quy định cam kết và cơ chế theo điều khoản của nhà cung cấp. SLA của dịch vụ OKE không tự tạo cam kết sẵn sàng cho toàn bộ ứng dụng. [Nguồn: Comparing Enhanced Clusters with Basic Clusters](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcomparingenhancedwithbasicclusters_topic.htm).

### 3.2. Khi nào cân nhắc basic

Basic phù hợp để đánh giá khi yêu cầu chỉ cần Kubernetes cốt lõi với managed nodes, chẳng hạn môi trường học hoặc thử nghiệm có ngân sách nhỏ. Hãy ghi rõ nhu cầu đang loại trừ: chưa dùng virtual nodes, chưa cần workload identity của OKE và chấp nhận quy trình quản lý worker tương ứng.

Đây là một quyết định theo yêu cầu. Một môi trường nhỏ nhưng bắt buộc dùng workload identity vẫn có lý do chọn enhanced; số lượng Pod ít không phải tiêu chí đủ để chọn basic.

### 3.3. Khi nào cân nhắc enhanced

Enhanced đáng xem xét khi cần các khả năng như quản lý add-on chi tiết, giảm công việc thay thế node qua node cycling, dùng virtual nodes hoặc bổ sung self-managed nodes. Với production, hãy đưa yêu cầu hỗ trợ dịch vụ và vận hành vào bản đánh giá cùng với chi phí.

Không nên chọn enhanced rồi mặc định các tính năng sẽ tự được cấu hình đúng. Quyền IAM của workload, chính sách cập nhật add-on và cách phân bố ứng dụng vẫn cần thiết kế, kiểm thử.

### 3.4. Nâng loại cluster không phải kế hoạch quay lui

Oracle cho phép nâng basic cluster đủ điều kiện VCN-native lên enhanced; enhanced không thể hạ trực tiếp về basic. Cần kiểm tra điều kiện cluster hiện có trước khi lập kế hoạch chuyển đổi. [Nguồn: Working with Enhanced Clusters and Basic Clusters](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengworkingwithenhancedclusters.htm).

Nếu yêu cầu kinh doanh đòi hỏi quay về một kiến trúc khác, kế hoạch phải bao gồm cluster đích, triển khai lại workload, xử lý dữ liệu và chuyển lưu lượng. Không coi thao tác đổi loại cluster là một công tắc có thể bật tắt tùy ý.

## 4. Managed nodes: OKE hỗ trợ vòng đời, bạn vẫn quản lý worker

### 4.1. Mô hình hoạt động

Managed nodes là worker trên OCI Compute trong tenancy của bạn, được OKE tạo và tổ chức thành **managed node pools**. Một pool mô tả cấu hình để cấp worker, chẳng hạn shape, image, phiên bản Kubernetes, số node và vị trí triển khai.

Trong mô hình này, đội vận hành vẫn cần theo dõi sức khỏe node, điều chỉnh dung lượng và áp dụng cập nhật. Oracle cung cấp dịch vụ, image và công cụ hỗ trợ; trách nhiệm cập nhật worker không biến mất vì tên gọi có chữ managed. [Nguồn: Support and Shared Responsibilities](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengsupportsharedresponsibilities.htm).

Managed nodes thường là phương án khởi đầu để đánh giá khi ứng dụng cần hệ sinh thái Kubernetes rộng, thành phần chạy theo node hoặc khả năng cấu hình máy chủ trong phạm vi OKE hỗ trợ.

### 4.2. Thiết kế worker có thể thay thế

Một node pool nên được xem như mẫu tạo worker có thể tái lập. Tránh để hoạt động của ứng dụng phụ thuộc vào gói phần mềm được cài thủ công qua SSH trên một máy duy nhất.

Ví dụ, nếu node mới phải có một cấu hình bổ sung, hãy đưa cấu hình vào cơ chế image hoặc khởi tạo được hỗ trợ, có quản lý phiên bản. Đồng thời đưa labels cần cho scheduling vào cấu hình cấp node. Khi thay worker, node mới phải đạt cùng yêu cầu mà không cần nhớ lại các thao tác thủ công trước đó.

Với dữ liệu, xác định phần nào là tạm thời và phần nào cần lưu bền vững. Một file quan trọng chỉ nằm trên hệ thống file cục bộ của worker sẽ tạo rủi ro khi worker bị thay.

### 4.3. Thay cấu hình pool chưa đồng nghĩa worker đã đổi

Thay phiên bản Kubernetes cấu hình cho pool không tự nâng phiên bản đang chạy trên các managed nodes hiện hữu. Cần áp dụng quy trình thay thế hoặc nâng cấp worker phù hợp. [Nguồn: Updating a Managed Node Pool](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/update-node-pool.htm).

Enhanced hỗ trợ node cycling cho managed nodes. Tùy thao tác, OKE có thể cordon và drain rồi thay boot volume hoặc thay instance; cần kiểm tra những thuộc tính được áp dụng trong từng chế độ. [Nguồn: Performing an In-Place Worker Node Update by Cycling Nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengupgradingimageworkernode_topic-Performing_an_InPlace_Worker_Node_Update_By_Cycling_an_Existing_Node_Pool.htm).

- **Cordon:** ngăn scheduler đặt Pod mới lên node theo cơ chế thông thường.
- **Drain:** di chuyển workload thông qua quy trình eviction phù hợp.
- **Thay thế:** đưa worker đáp ứng cấu hình mong muốn vào phục vụ.

Một quy trình cập nhật hợp lý cần có dung lượng dự phòng, kiểm tra Pod Ready và điều kiện dừng khi lỗi. Không lấy việc work request hoàn tất làm bằng chứng duy nhất rằng người dùng vẫn truy cập ứng dụng bình thường.

## 5. Virtual nodes: giảm vận hành máy chủ, kiểm tra tương thích ở mức Pod

### 5.1. Điều gì thay đổi?

Virtual nodes cung cấp mô hình serverless cho hạ tầng worker và chỉ dùng với enhanced cluster. Oracle quản lý lớp worker; bạn tập trung vào Pod và ứng dụng. Hạ tầng virtual nodes chạy trong tenancy của dịch vụ OKE, thay vì là tập máy Compute do bạn quản lý như managed nodes. [Nguồn: Comparing Managed Nodes with Virtual Nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcomparingmanagednodeswithvirtualnodes_topic.htm).

Điều này giảm công việc quản lý máy chủ nhưng không chuyển trách nhiệm về mã nguồn, container image, cấu hình bảo mật ứng dụng hay kết nối cơ sở dữ liệu sang Oracle.

### 5.2. Requests/limits trở thành đầu vào quan trọng

Với virtual nodes, cấp CPU và bộ nhớ được xét ở mức Pod. Quy tắc cấp tài nguyên có xem xét cấu hình từng container và overhead; không nên giả định số lượng bộ nhớ khai báo luôn bằng đúng toàn bộ lượng được cấp hoặc tính phí. [Nguồn: Resources Allocated to Pods Provisioned by Virtual Nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengvirtualnodepodresourceallocation.htm).

Với Java, hãy đo bộ nhớ thực tế của tiến trình, gồm heap, metaspace, thread stacks và phần native. Ví dụ, đặt heap bằng toàn bộ memory limit có thể khiến container vượt giới hạn dù heap chưa đầy. Cần thử tải với cấu hình tài nguyên dự kiến trước khi so sánh chi phí giữa các mô hình.

### 5.3. Những giới hạn ảnh hưởng trực tiếp đến lựa chọn

Theo bảng hỗ trợ của Oracle được đối chiếu ngày **20/11/2026**:

- Virtual nodes dùng OCI VCN-Native Pod Networking.
- Không hỗ trợ DaemonSet, privileged container hoặc hostPath.
- Không cung cấp SSH và custom cloud-init cho worker.
- PVC được hỗ trợ với File Storage; Block Volume PVC không được hỗ trợ.
- Một số tích hợp ingress, metrics và quan sát cần cách triển khai riêng.

Các giới hạn có thể thay đổi; kiểm tra workload cùng phiên bản dịch vụ thực tế. [Nguồn: Comparing Virtual Nodes with Managed Nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcomparingvirtualwithmanagednodes_topic.htm).

Vì vậy, API stateless có dữ liệu nằm trong dịch vụ bên ngoài là ứng viên để thử virtual nodes. Một hệ thống bắt buộc có agent bảo mật kiểu DaemonSet cần đánh giá managed nodes, hoặc thay cách đáp ứng yêu cầu bảo mật trước khi chuyển workload.

Không kết luận mọi StatefulSet đều không dùng được, cũng không kết luận mọi PVC đều được hỗ trợ. Loại tài nguyên Kubernetes, storage backend và khả năng tích hợp cụ thể phải được xem cùng nhau.

## 6. Self-managed nodes: tự cấp Compute và chịu trách nhiệm tích hợp

### 6.1. Khác managed nodes ở điểm nào?

Self-managed node là worker trên Compute instance hoặc instance pool do bạn tạo qua dịch vụ Compute rồi đưa vào OKE. Các node này không thuộc OKE managed node pool hay virtual node pool. Đây thường được gọi là Bring Your Own Nodes, trong phạm vi hạ tầng OCI và điều kiện OKE hỗ trợ. [Nguồn: OKE Concepts](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengclustersnodes.htm).

Mô hình này hữu ích khi cần tổ hợp shape và image hoặc quy trình cấp phát mà managed node pool không đáp ứng. Có nhu cầu GPU chưa đủ để kết luận phải dùng self-managed: trước hết kiểm tra shape, image và khả năng managed nodes tại region đang chọn.

### 6.2. Điều kiện và công việc cần nhận

Self-managed nodes yêu cầu enhanced cluster, image phù hợp và phiên bản Kubernetes tương thích. CNI cũng có điều kiện riêng; kiểm tra bộ điều kiện hiện hành thay vì cho rằng một image Linux bất kỳ đều có thể gia nhập OKE. [Nguồn: Prerequisites for Self-Managed Node Creation](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengprereqsforselfmanagednodes.htm).

Quy trình tạo node bao gồm cấp Compute và bootstrap để kết nối tới cluster đích, với thông tin endpoint và chứng thư phù hợp. [Nguồn: Creating Self-Managed Nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcreatingselfmanagednodes.htm).

Đội sở hữu phương án cần mô tả được toàn bộ vòng đời:

1. Tạo máy với đúng mạng, image, quyền và cấu hình bootstrap.
2. Xác nhận worker gia nhập cluster, báo Ready và có labels dự kiến.
3. Theo dõi lỗi bootstrap, hết dung lượng và sai cấu hình.
4. Cập nhật image, hệ điều hành và thành phần Kubernetes theo phạm vi hỗ trợ.
5. Drain, loại bỏ node và thu hồi Compute theo đúng trình tự.
6. Tạo lại node từ cấu hình có quản lý phiên bản để chứng minh khả năng phục hồi.

Tự động mở rộng Compute instance pool không tự chứng minh rằng các Pod đã có thêm worker dùng được. Cần xác nhận cả quá trình gia nhập Kubernetes và quy trình scale-in có xử lý workload an toàn.

## 7. Bảng lựa chọn theo tình huống

Bảng sau là gợi ý thiết kế dựa trên các đặc tính đã trình bày; cần xác nhận bằng yêu cầu và thử nghiệm của hệ thống cụ thể.

| Tình huống | Phương án nên đánh giá trước | Bằng chứng cần thu thập |
| --- | --- | --- |
| Lab Kubernetes nhỏ, dùng tính năng cốt lõi | Basic + managed nodes | Chi phí toàn bộ lab và cách thay worker |
| Production có agent theo node, cần quản lý add-on | Enhanced + managed nodes | Agent chạy đúng, cập nhật node không gây gián đoạn vượt mức cho phép |
| API stateless biến động mạnh, muốn giảm vận hành máy chủ | Enhanced + virtual nodes | Tương thích Pod, mạng, metrics, thời gian khởi động và chi phí |
| Cần tổ hợp Compute/image đặc thù | Enhanced + self-managed nodes nếu được hỗ trợ | Bootstrap tái lập được và đội vận hành xử lý được vòng đời |
| Workload có yêu cầu khác nhau | Enhanced với các nhóm worker phù hợp | Quy tắc scheduling rõ ràng và quan sát tách được từng nhóm |

Một cluster dùng nhiều mô hình worker là phương án có thể đánh giá, nhưng làm tăng số nhánh cần kiểm thử. Đặt mục tiêu rõ cho từng nhóm, chẳng hạn một nhóm phục vụ nền tảng và một nhóm chạy API đủ điều kiện serverless. Không kỳ vọng Pod tự chuyển sang mô hình khác khi các điều kiện scheduling hoặc tính năng không tương thích.

## 8. Tổ chức node pools và đặt workload đúng chỗ

### 8.1. Chia pool theo yêu cầu có ý nghĩa

Các lý do thường đáng cân nhắc để tách managed node pools gồm kiến trúc CPU, đặc tính CPU/bộ nhớ, thành phần bắt buộc trên host và lịch bảo trì. Ví dụ:

| Nhóm dự kiến | Workload | Điều cần kiểm tra |
| --- | --- | --- |
| General | API Java và dịch vụ thông thường | Dung lượng khi tăng replica và khi bảo trì |
| Memory | Tác vụ dùng nhiều bộ nhớ | Bộ nhớ native, thời gian GC và khả năng đóng gói Pod |
| Specialized | Tính toán cần phần cứng hoặc cấu hình riêng | Shape, image, driver và phạm vi hỗ trợ |
| Platform | Thành phần vận hành phù hợp | Tài nguyên tối thiểu và mức độ cô lập mong muốn |

Không tách một pool chỉ vì có thêm namespace. Quá nhiều pool nhỏ có thể tạo dung lượng nhàn rỗi và tăng công việc cập nhật. Ngược lại, gom mọi workload vào một cấu hình duy nhất có thể khiến các nhóm tranh chấp tài nguyên hoặc bị ràng buộc bởi lịch nâng cấp khác nhau.

Nếu dùng Arm và x86, kiểm tra container image cùng các thư viện native theo đúng kiến trúc. Một ứng dụng Java vẫn có thể phụ thuộc thư viện native, công cụ giám sát hoặc binary không có bản tương ứng.

### 8.2. Phối hợp labels, selector và taints

Ví dụ, cấu hình nhóm worker thông thường mang label **learning.example.com/pool=general**. Workload dùng nodeSelector tương ứng sẽ chỉ có thể được đặt lên node thỏa label cùng các điều kiện scheduling khác.

Nếu một nhóm máy cần dành cho workload chuyên biệt, có thể phối hợp taint và toleration. **Toleration chỉ cho phép Pod vượt qua taint tương ứng; nó không buộc Pod phải chạy trên nhóm đó.** Muốn buộc chọn nhóm, cần thêm selector hoặc node affinity phù hợp. [Nguồn: Kubernetes Taints and Tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/).

Labels và taints là công cụ scheduling, không thay thế ranh giới bảo mật. Yêu cầu cô lập mạnh còn liên quan tới quyền, mạng, chính sách workload và đôi khi cả việc tách cluster.

## 9. Dung lượng, autoscaling và tính sẵn sàng

### 9.1. Tách tăng Pod khỏi tăng worker

Với managed nodes, HPA điều chỉnh số replica theo tín hiệu được cấu hình; Cluster Autoscaler có thể điều chỉnh số worker của các managed node pools được cấu hình tương ứng. Hai vòng điều khiển giải quyết hai bài toán khác nhau.

Với virtual nodes, mở rộng tài nguyên phục vụ Pod không vận hành như tăng số VM của managed pool. Không dùng Kubernetes Cluster Autoscaler cho virtual nodes theo hỗ trợ hiện hành; vẫn phải quản lý giới hạn, quota và dung lượng logic của virtual node pools. [Nguồn: Scaling Kubernetes Clusters and Node Pools](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengscalingkubernetesclustersnodepools.htm).

Một Pod Pending chưa đủ chứng minh thiếu CPU. Nó có thể không có node thỏa selector, vướng taint, thiếu IP, chưa gắn được volume hoặc bị ràng buộc topology. Tăng worker sai nhóm sẽ không giải quyết được nguyên nhân đó.

### 9.2. Ví dụ tính dung lượng cho managed nodes

Giả sử một dịch vụ cần tối đa 24 Pod, mỗi Pod request **500m CPU và 1Gi bộ nhớ**. Sau khi dành tài nguyên cho hệ thống và thành phần theo node, mỗi worker còn **3 CPU và 6Gi allocatable** cho dịch vụ.

~~~text
Tổng CPU requests       = 24 × 0,5 = 12 CPU
Tổng memory requests    = 24 × 1   = 24Gi

Số Pod tối đa mỗi node = min(3 / 0,5; 6 / 1) = 6
Số node tối thiểu       = ceil(24 / 6) = 4
~~~

Bốn worker là kết quả tính theo requests trong các giả định trên. Đó chưa phải thiết kế chịu sự cố: khi một worker mất, ba worker còn lại chỉ chứa được 18 Pod theo cùng giả định.

Nếu muốn chịu mất một worker mà vẫn đủ chỗ cho 24 Pod, cần ít nhất năm worker có cấu hình này. Nếu region có ba availability domains và mục tiêu là chịu mất một AD, phương án sáu worker chia đều hai worker mỗi AD còn lại bốn worker sau sự cố, đủ 24 Pod về mặt dung lượng lý thuyết.

Đây là ví dụ tự xây dựng để minh họa cách suy luận, không phải sizing mặc định cho OCI. Kết quả thực tế còn phụ thuộc phân bố Pod, giới hạn IP, thành phần nền tảng, volume topology và khả năng cấp shape trong region. Không đồng nhất số OCPU trong tên cấu hình OCI với CPU unit Kubernetes mà chưa kiểm tra kiến trúc và allocatable thực tế.

### 9.3. Phân bố lỗi phải đi cùng phân bố Pod

Tạo nhiều worker không đảm bảo các replica của cùng dịch vụ đã phân tán. Dùng topology spread hoặc quy tắc affinity phù hợp, đồng thời kiểm tra labels topology của node thực tế.

Với topology spread, **DoNotSchedule** có thể giữ Pod Pending để bảo toàn ràng buộc; **ScheduleAnyway** ưu tiên phân bố nhưng cho phép lịch chạy linh hoạt hơn. Chọn theo mức ưu tiên giữa phân tán và khả năng đặt Pod trong lúc thiếu tài nguyên. [Nguồn: Kubernetes Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/).

Nếu region chỉ có một AD, phân bố qua fault domains giúp giảm một số dạng lỗi trong AD nhưng không thay thế khả năng chịu mất toàn bộ AD hoặc region.

### 9.4. PDB hỗ trợ bảo trì, không chống được mọi sự cố

PodDisruptionBudget có thể hạn chế số Pod bị gián đoạn qua các hoạt động eviction tự nguyện có tôn trọng PDB. Nó không ngăn máy chủ hỏng và không tự tạo tài nguyên dự phòng. [Nguồn: Kubernetes Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/).

Ví dụ, ba replica với minAvailable bằng hai cho phép xử lý một Pod trong điều kiện bình thường. Nếu chỉ còn hai Pod khỏe, lần drain tiếp theo có thể bị chặn. Cần xác định nguyên nhân, khôi phục replica hoặc bổ sung dung lượng theo quy trình; cưỡng bức loại bỏ node có thể khiến mục tiêu sẵn sàng thất bại.

## 10. Đưa IAM, mạng, lưu trữ và cơ sở dữ liệu vào quyết định

Lựa chọn worker phải phù hợp với kiến trúc OCI tổng thể. Trước khi chốt, làm rõ các điểm sau:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Compartment và IAM | Ai được tạo, thay đổi, xem và xóa cluster hoặc Compute? Quyền có đúng phạm vi tài nguyên không? |
| Kubernetes RBAC | Ai được thao tác namespace, Deployment, Secret và node qua Kubernetes API? |
| VCN, subnet và NSG | Đường kết nối quản trị, worker, Pod, registry và dịch vụ phụ thuộc có hoạt động không? |
| IP và quota | Khi mở rộng hoặc tạo worker thay thế, còn địa chỉ và hạn mức phù hợp không? |
| Storage | Workload dùng tạm thời, File Storage hay Block Volume? Mô hình worker có hỗ trợ đúng tích hợp đó không? |
| Oracle Database | Đường mạng, TLS, thông tin xác thực và connection pool có phù hợp với số replica tối đa không? |

Phân quyền tạo cluster qua OCI IAM và quyền thao tác tài nguyên Kubernetes là hai phạm vi cần xem xét riêng. Tương tự, quyền của người vận hành node và quyền ứng dụng truy cập OCI cần được thiết kế theo chủ thể thực hiện công việc, tránh dùng quyền rộng của máy chủ làm mặc định cho mọi Pod.

Nếu API Java kết nối tới Autonomous Database hoặc một dịch vụ Oracle Database bên ngoài OKE, việc tăng replica làm tăng tổng số connection có thể được mở. Ví dụ, 24 replica với pool tối đa 20 connection tạo khả năng mở tới 480 connection. Đây là phép tính trần cấu hình, không phải số connection luôn hoạt động; vẫn cần kiểm tra khả năng chịu tải của database.

Tăng worker không giải quyết tình trạng cạn connection ở database. Ngược lại, autoscaling không có giới hạn phù hợp có thể làm vấn đề trầm trọng hơn.

## 11. So sánh chi phí toàn bộ phương án

Theo bảng giá Oracle, basic cluster có phí dịch vụ cluster bằng không; enhanced cluster và virtual node có các đơn vị tính phí riêng. Compute, lưu trữ và các dịch vụ đi kèm vẫn phải được tính theo sử dụng thực tế. Không suy ra toàn bộ hệ thống miễn phí từ giá basic cluster. [Nguồn: Oracle Cloud Price List](https://www.oracle.com/cloud/price-list/).

Có thể lập mô hình ước tính:

~~~text
Managed:
  phí cluster
  + Compute của worker theo thời gian
  + boot volumes và lưu trữ dữ liệu
  + mạng, cân bằng tải và quan sát

Virtual:
  phí enhanced cluster
  + phí virtual nodes
  + CPU/bộ nhớ được cấp cho Pod theo quy tắc tính phí
  + lưu trữ, mạng, cân bằng tải và quan sát

Self-managed:
  phí enhanced cluster
  + Compute và các tài nguyên liên quan
  + công sức vận hành, tự động hóa và xử lý sự cố
~~~

Các biểu thức này là khung so sánh, không phải hóa đơn hay công thức tính phí đầy đủ. Lấy đơn giá, quy tắc cấp tài nguyên và điều kiện hợp đồng tại thời điểm dự toán; đo cùng một workload với cùng mục tiêu hiệu năng để so sánh.

Với workload ổn định, managed nodes được đóng gói Pod hợp lý có thể tận dụng tài nguyên tốt. Với workload biến động, virtual nodes có thể giảm phần công việc giữ và mở rộng worker. Kết quả phụ thuộc cấu hình thực tế, tài nguyên cấp cho Pod và các chi phí cố định; không có mô hình luôn rẻ hơn trong mọi tình huống.

Đưa cả đêm, cuối tuần, giai đoạn rollout và dung lượng dự phòng vào dự toán. Gắn tags phục vụ theo dõi chi phí, thiết lập ngân sách và cảnh báo theo phạm vi được hỗ trợ. Cảnh báo ngân sách cần đi kèm người chịu trách nhiệm xử lý; nó không tự thu nhỏ cluster khi vượt ngưỡng.

## 12. Thực hành: kiểm tra phương án trên cluster đã có

Phần này dùng cluster trong môi trường học đã được cấp quyền. Các lệnh OCI dưới đây chỉ đọc cấu hình; chúng không tạo cluster hoặc phát sinh worker mới. OCI CLI phải được xác thực đúng tenancy, profile và region. kubectl phải trỏ tới kubeconfig tương ứng, có đường mạng tới Kubernetes API và quyền cần thiết.

### 12.1. Kiểm tra loại cluster và các node pools

Ví dụ dùng PowerShell; thay các giá trị OCID bằng tài nguyên của môi trường học.

~~~powershell
$ClusterId = "<OCID_CLUSTER>"
$CompartmentId = "<OCID_COMPARTMENT_CHUA_NODE_POOLS>"

oci ce cluster get --cluster-id $ClusterId --query "data.type" --raw-output
oci ce node-pool list --compartment-id $CompartmentId --cluster-id $ClusterId --all
oci ce virtual-node-pool list --compartment-id $CompartmentId --cluster-id $ClusterId --all

kubectl config current-context
kubectl get nodes -o wide
kubectl get nodes -L learning.example.com/pool,kubernetes.io/arch,topology.kubernetes.io/zone
~~~

Nguồn lệnh: [cluster get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ce/cluster/get.html), [node-pool list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ce/node-pool/list.html), [virtual-node-pool list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ce/virtual-node-pool/list.html).

Đọc kết quả theo từng lớp:

- Trường type cho biết loại cluster; không suy ra nó chỉ từ số node.
- Danh sách managed và virtual node pools cho biết các pool mà API trả về trong compartment đã truy vấn và quyền đang có.
- Self-managed nodes không xuất hiện như một managed node pool; cần đối chiếu node trong Kubernetes với Compute inventory và cấu hình bootstrap của đội sở hữu.
- Node Ready thể hiện một phần sức khỏe Kubernetes; nó chưa chứng minh workload đặt được lên node đó.

Nếu node pools ở các compartment khác nhau, truy vấn từng compartment phù hợp. Danh sách rỗng không tự chứng minh cluster không có worker: trước hết kiểm tra phạm vi truy vấn và quyền.

### 12.2. Ví dụ định tuyến workload vào managed pool

Giả sử các managed nodes đích đã được cấp label **learning.example.com/pool=general** trong cấu hình tạo node. Ví dụ sau là **mẫu manifest**, cần thay image bằng image ứng dụng đã kiểm thử và cấu hình quyền kéo image nếu dùng registry riêng. Mẫu chưa bao gồm Service, probes, Secret hay kết nối database.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: default
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      nodeSelector:
        learning.example.com/pool: general
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: order-api
      containers:
        - name: order-api
          image: "<OCIR_IMAGE_DA_KIEM_THU>"
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "1"
              memory: "2Gi"
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: order-api
  namespace: default
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: order-api
~~~

Manifest minh họa ba quyết định: chọn nhóm worker bằng label, ưu tiên phân tán qua hostname và hạn chế eviction tự nguyện bằng PDB. Vì dùng ScheduleAnyway, ba replica vẫn có thể không nằm trên ba node khác nhau khi điều kiện scheduling hạn chế.

Không dùng nguyên mẫu này để kết luận workload đã tương thích với virtual nodes. Nếu đổi mô hình worker, cần đánh giá lại tính năng Pod, mạng, storage, resource allocation và cách thu thập metrics.

### 12.3. Quan sát sau khi triển khai trong lab

Sau khi người thực hành áp dụng manifest đã hoàn thiện vào môi trường học, có thể kiểm tra:

~~~powershell
kubectl rollout status deployment/order-api -n default
kubectl get pods -n default -l app=order-api -o wide
kubectl get pdb order-api -n default
kubectl get events -n default --sort-by=.metadata.creationTimestamp
~~~

Nếu Pod Pending, lấy tên Pod từ kết quả rồi chạy kubectl describe pod với đúng namespace. Đọc sự kiện scheduling để phân biệt thiếu tài nguyên với không khớp selector, taint hoặc vấn đề tích hợp khác.

Nếu cần xem CPU/bộ nhớ sử dụng qua kubectl top, trước hết xác nhận metrics pipeline đã được triển khai và hoạt động với mô hình worker đang dùng. Không diễn giải lỗi thiếu metrics là bằng chứng node không chạy được ứng dụng.

### 12.4. Tiêu chí hoàn thành thực hành

Kết quả cần có bằng chứng rằng:

1. Loại cluster đúng với yêu cầu đã ghi.
2. Mô hình worker thực tế khớp phương án đã chọn.
3. Pod được đặt vào nhóm dự kiến và đạt trạng thái sẵn sàng phù hợp.
4. Dung lượng dự phòng đã được tính cho kịch bản lỗi cụ thể.
5. Quyền, đường mạng và giới hạn dịch vụ phụ thuộc đã được kiểm tra.
6. Chi phí được ước tính cho cả tải bình thường, tải cao và quá trình cập nhật.

Không cần tạo thêm cluster để hoàn thành bài nếu môi trường hiện tại đã đủ dữ liệu cho việc so sánh và kiểm tra.

## 13. Mẫu quyết định kiến trúc ngắn gọn

Ví dụ sau là đề xuất cho một hệ thống giả định, không phải cấu hình mặc định của OKE.

| Mục | Quyết định và lý do |
| --- | --- |
| Workload | API Java kết nối Oracle Database bên ngoài cluster; có agent vận hành theo node |
| Loại cluster | Enhanced để dùng các khả năng quản lý cần thiết và đáp ứng yêu cầu dịch vụ |
| Worker ban đầu | Managed nodes, vì nhóm cần thành phần theo node và muốn dùng vòng đời node pool |
| Phân bố | Theo AD hoặc fault domain sẵn có, đi kèm quy tắc phân bố Pod và tính đủ dung lượng sau lỗi |
| Mở rộng | HPA cho replica; quản lý dung lượng managed pools với giới hạn rõ ràng |
| Cập nhật | Image và phiên bản có quản lý; kiểm tra khả năng drain, dự phòng tài nguyên và quan sát sau thay node |
| Phân quyền | Quyền quản trị OCI và Kubernetes đúng phạm vi; quyền ứng dụng truy cập dịch vụ được thiết kế riêng |
| Chi phí | Theo dõi Compute, cluster, lưu trữ, mạng và quan sát; có ngân sách cùng người xử lý cảnh báo |
| Điều kiện xem xét lại | Agent được thay đổi, workload đủ điều kiện virtual nodes hoặc có yêu cầu Compute đặc thù |

Một quyết định tốt phải chỉ ra điều kiện có thể làm nó thay đổi. Ví dụ, nếu agent theo node không còn bắt buộc, một nhóm API có thể được thử trên virtual nodes; việc chuyển chỉ được chấp nhận sau khi đáp ứng mục tiêu hiệu năng, khả năng quan sát và ngân sách.

## 14. Những sai lầm cần nhận diện

| Nhận định | Cách xử lý đúng |
| --- | --- |
| Enhanced đồng nghĩa tất cả worker là serverless | Xác định riêng loại cluster và từng mô hình worker |
| Managed nodes tự chịu trách nhiệm toàn bộ bản vá | Giao rõ người sở hữu cập nhật, kiểm tra và thay worker |
| Có ba replica thì chịu được mất một AD | Kiểm tra vị trí replica, dung lượng còn lại và dịch vụ phụ thuộc |
| HPA tăng Pod sẽ luôn có máy để chạy | Kiểm tra cả dung lượng worker, quota, IP và điều kiện scheduling |
| Chỉ cần sửa phiên bản của node pool | Xác minh phiên bản thực tế trên worker sau quy trình cập nhật |
| Mọi PVC đều chuyển nguyên sang virtual nodes | Đối chiếu storage backend và khả năng hỗ trợ |
| Self-managed nodes giảm phí vận hành vì chủ động hơn | Tính cả công sức bootstrap, cập nhật, thay thế và xử lý sự cố |
| Chuyển mô hình worker chỉ cần sửa selector | Kiểm thử lại toàn bộ yêu cầu Pod và các tích hợp liên quan |

Khi lựa chọn phương án cho OKE, hãy ghi rõ tập tính năng cluster cần dùng, phần vòng đời worker mà đội nhận quản lý, cùng bằng chứng về dung lượng, chi phí và khả năng phục hồi. Đó là cơ sở để triển khai hạ tầng OCI có phân quyền, giám sát và tự động hóa phù hợp với ứng dụng thực tế.
