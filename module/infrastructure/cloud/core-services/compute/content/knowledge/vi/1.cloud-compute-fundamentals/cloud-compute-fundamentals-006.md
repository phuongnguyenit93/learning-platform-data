# Region, availability zone và phạm vi lỗi của tài nguyên compute

Khi triển khai tài nguyên compute trên cloud, việc chọn loại máy ảo, số vCPU hay dung lượng bộ nhớ mới chỉ giải quyết một phần bài toán. Vị trí đặt tài nguyên trong **region** và **availability zone (AZ)** quyết định độ trễ đến người dùng, khả năng tiếp tục phục vụ khi hạ tầng gặp sự cố, cách dữ liệu được bảo vệ và chi phí truyền dữ liệu giữa các vị trí.

Một hệ thống có nhiều máy ảo vẫn có thể ngừng hoạt động hoàn toàn nếu tất cả máy nằm trong cùng một vùng lỗi. Ngược lại, phân tán tài nguyên qua nhiều AZ mà không thiết kế lại dữ liệu, mạng và các dịch vụ phụ thuộc cũng chưa tạo ra tính sẵn sàng đầu cuối. Vì vậy, cần hiểu phạm vi của từng tài nguyên và xác định sự cố nào kiến trúc phải chịu đựng được.

Bài học này thuộc chương **Nền tảng cloud compute** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module tập trung vào các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong phạm vi đó, region, AZ và phạm vi lỗi là nền tảng để quyết định tài nguyên compute sẽ được đặt ở đâu và cần dự phòng như thế nào.

## 1. Phạm vi lỗi là gì?

**Phạm vi lỗi (failure domain)** là một phần của hệ thống mà sự cố có thể ảnh hưởng đến các tài nguyên nằm trong phần đó. Nếu một lỗi xảy ra và làm nhiều thành phần cùng mất khả năng hoạt động, các thành phần đó có thể đang chia sẻ một phạm vi lỗi.

Một số phạm vi lỗi thường gặp:

- **Máy chủ vật lý hoặc host:** lỗi phần cứng, nguồn, bộ nhớ, bộ điều khiển lưu trữ hoặc hypervisor có thể làm các máy ảo trên host đó bị ảnh hưởng.
- **Rack hoặc cụm hạ tầng:** sự cố nguồn điện, mạng hoặc thiết bị dùng chung có thể ảnh hưởng đến nhiều host.
- **Availability zone:** sự cố tại một địa điểm hạ tầng độc lập có thể làm các tài nguyên trong AZ đó không truy cập được.
- **Region:** sự cố diện rộng có thể ảnh hưởng đến nhiều AZ và các dịch vụ được triển khai trong region.
- **Dịch vụ dùng chung hoặc cấu hình dùng chung:** lỗi DNS, danh tính và quyền truy cập, hệ thống phân phối bí mật, cấu hình mạng hoặc thao tác thay đổi sai có thể ảnh hưởng đến nhiều region cùng lúc.

Phạm vi lỗi không chỉ là ranh giới địa lý. Một lỗi cấu hình có thể vượt qua ranh giới AZ hoặc region. Ví dụ, nếu tất cả máy chủ ở nhiều AZ đều dùng chung một cấu hình firewall sai, việc phân tán máy chủ không ngăn được sự cố. Tương tự, nếu ứng dụng chạy ở hai region nhưng chỉ sử dụng một dịch vụ xác thực không có phương án dự phòng, dịch vụ xác thực đó vẫn có thể trở thành điểm lỗi chung.

**Blast radius** là phạm vi tác động thực tế của một sự cố. Thiết kế tốt tìm cách giới hạn blast radius: một host lỗi không làm sập toàn bộ ứng dụng; một AZ mất kết nối không làm mất toàn bộ khả năng phục vụ; một region gặp sự cố không khiến doanh nghiệp mất dữ liệu không thể khôi phục.

## 2. Region và availability zone

### 2.1. Region

**Region** là một khu vực địa lý mà nhà cung cấp cloud xây dựng và vận hành hạ tầng để cung cấp dịch vụ. Một region thường bao gồm nhiều AZ, có kết nối mạng giữa chúng và có danh mục dịch vụ, loại máy, dung lượng cùng hạn mức riêng.

Các region có thể cách nhau hàng trăm hoặc hàng nghìn kilomet. Khoảng cách này tạo ra khác biệt về độ trễ mạng, khả năng kết nối, yêu cầu lưu trú dữ liệu và chi phí truyền dữ liệu.

Khi chọn region, cần xem xét:

- Người dùng và hệ thống gọi dịch vụ đang ở đâu, độ trễ chấp nhận được là bao nhiêu.
- Dữ liệu có yêu cầu lưu trữ hoặc xử lý tại một quốc gia, lãnh thổ hay khu vực cụ thể không.
- Dịch vụ, loại máy ảo, GPU, hệ điều hành và tính năng cần dùng có sẵn tại region đó không.
- Hạn mức tài nguyên, năng lực dự phòng và khả năng mở rộng có đáp ứng nhu cầu không.
- Kết nối tới hệ thống tại chỗ, đối tác hoặc các dịch vụ cloud khác có phù hợp không.
- Giá compute, lưu trữ, truyền dữ liệu và các khoản phí liên quan.

Tên region thường gắn với một địa danh hoặc mã định danh do nhà cung cấp quy ước. Tuy nhiên, tên region không đủ để suy ra chính xác phạm vi pháp lý, ranh giới quốc gia hoặc cam kết về nơi dữ liệu được xử lý. Với yêu cầu tuân thủ, cần kiểm tra tài liệu và điều khoản của từng dịch vụ.

### 2.2. Availability zone

**Availability zone (AZ)** là một vị trí hạ tầng được thiết kế để có mức độ độc lập nhất định với các AZ khác trong cùng region. Nhà cung cấp thường bố trí các AZ với nguồn điện, hệ thống làm mát và kết nối mạng riêng để giảm khả năng một sự cố cục bộ ảnh hưởng đồng thời đến tất cả AZ.

Một AZ có thể bao gồm một hoặc nhiều trung tâm dữ liệu. Vì vậy, không nên mặc định rằng một AZ luôn tương đương với đúng một tòa nhà hoặc một trung tâm dữ liệu.

Các AZ trong cùng region thường có kết nối mạng tốc độ cao và độ trễ thấp để hỗ trợ triển khai phân tán. Tuy vậy, truyền dữ liệu giữa AZ vẫn có thể phát sinh chi phí và độ trễ; cần kiểm tra chính sách giá của nhà cung cấp.

Tên gọi và cách biểu diễn AZ khác nhau giữa các nền tảng:

| Nền tảng | Cách tổ chức phổ biến |
|---|---|
| AWS | Region gồm nhiều Availability Zones; mỗi AZ là một hoặc nhiều địa điểm hạ tầng độc lập. |
| Microsoft Azure | Region có thể hỗ trợ Availability Zones; các zone là những vị trí vật lý riêng biệt trong region. |
| Google Cloud | Region gồm nhiều zones; zone là phạm vi triển khai tài nguyên trong region. |

Các khái niệm trên có mục đích tương tự nhưng không phải lúc nào cũng có ngữ nghĩa, danh mục dịch vụ hoặc cam kết SLA giống hệt nhau. Khi chuyển kiến trúc giữa các nhà cung cấp, cần kiểm tra lại cách dịch vụ cụ thể triển khai tính sẵn sàng.

### 2.3. Phân biệt region, AZ và phạm vi toàn cục

Có thể hình dung thứ bậc triển khai như sau:

~~~mermaid
flowchart TB
    G["Phạm vi toàn cục<br/>Global services hoặc điểm điều phối toàn cầu"]
    R1["Region A"]
    R2["Region B"]
    Z11["AZ A1"]
    Z12["AZ A2"]
    Z13["AZ A3"]
    Z21["AZ B1"]
    Z22["AZ B2"]
    G --> R1
    G --> R2
    R1 --> Z11
    R1 --> Z12
    R1 --> Z13
    R2 --> Z21
    R2 --> Z22
~~~

- **Phạm vi toàn cục (global):** tài nguyên hoặc mặt phẳng điều phối có thể được quản lý trên nhiều region. Một dịch vụ mang nhãn global vẫn có thể có giới hạn, phụ thuộc hoặc thành phần dữ liệu nằm ở một phạm vi cụ thể.
- **Phạm vi region (regional):** tài nguyên được tạo trong một region và thường có thể phục vụ nhiều AZ trong region đó.
- **Phạm vi AZ (zonal):** tài nguyên gắn với một AZ cụ thể. Nếu AZ gặp sự cố, tài nguyên có thể không sử dụng được từ các AZ khác.

Phạm vi của tài nguyên là thuộc tính của từng dịch vụ. Không thể kết luận mọi tài nguyên mạng đều regional hoặc mọi tài nguyên lưu trữ đều zonal chỉ dựa vào tên gọi. Hãy kiểm tra tài liệu dịch vụ, đặc biệt là phạm vi tạo tài nguyên, phạm vi gắn kết và cách tài nguyên phục hồi khi AZ hoặc region gặp sự cố.

## 3. Phạm vi của các tài nguyên cloud thường dùng

Một ứng dụng compute thường gồm nhiều loại tài nguyên. Mỗi loại có phạm vi và hành vi lỗi riêng.

| Tài nguyên | Phạm vi thường gặp | Điều cần kiểm tra |
|---|---|---|
| Máy ảo (VM/instance) | Thường được đặt trong một AZ cụ thể thuộc một region | Có thể tạo lại ở AZ khác không; image, quota và loại máy có sẵn ở đó không. |
| Image máy ảo | Thường được quản lý hoặc sao chép theo region | Image có được sao chép sang region dự phòng và có tương thích với loại máy ở đó không. |
| Block volume/disk | Có thể là zonal hoặc có cơ chế sao chép regional | Có thể gắn vào VM ở AZ khác không; cần snapshot, replicate hay restore để chuyển vùng. |
| Object storage | Thường được chọn theo region hoặc lớp vị trí lưu trữ | Dữ liệu được sao chép trong phạm vi nào; có bản sao ở region khác không. |
| VPC/VNet và subnet | Phạm vi thay đổi theo nhà cung cấp; mạng ảo có thể regional, còn subnet có thể gắn với AZ hoặc trải rộng trong region | Phạm vi subnet, route table, gateway, firewall và kết nối liên vùng. |
| Load balancer | Có thể zonal, regional hoặc global | Health check, phân phối tải qua AZ, khả năng tiếp tục nhận lưu lượng khi một AZ lỗi. |
| Địa chỉ IP và NAT gateway | Có thể gắn với một AZ hoặc một region | Đường đi của lưu lượng khi AZ lỗi; khả năng chuyển IP hoặc tạo gateway dự phòng. |
| Kubernetes cluster/node pool | Control plane và node pool có thể có phạm vi khác nhau | Node nằm ở những AZ nào; control plane, persistent volume và scheduler xử lý lỗi ra sao. |
| Serverless function | Thường được triển khai theo region, hạ tầng bên dưới do nhà cung cấp quản lý | Mức dự phòng được dịch vụ cam kết; giới hạn concurrency, quota và phạm vi của các dịch vụ phụ thuộc. |
| Cơ sở dữ liệu managed | Có thể hỗ trợ triển khai đơn AZ, đa AZ hoặc sao chép liên region | Cơ chế failover, đồng bộ dữ liệu, RPO/RTO và quyền kiểm soát vị trí bản sao. |

Bảng này mô tả các mô hình thường gặp, không phải quy tắc áp dụng cho mọi nhà cung cấp. Ví dụ, một loại disk có thể chỉ gắn được với VM trong cùng AZ; loại khác có thể hỗ trợ sao chép hoặc gắn kết ở phạm vi rộng hơn. Tên dịch vụ tương tự nhau cũng không bảo đảm cùng khả năng.

### 3.1. Máy ảo và image

Máy ảo thường được tạo trong một region và một AZ. Khi host hoặc AZ gặp sự cố, máy ảo có thể ngừng hoạt động. Muốn phục hồi ở AZ khác, hệ thống cần có đủ thành phần để tạo lại máy: image, cấu hình khởi động, network, quyền truy cập, dữ liệu và quota.

Image có thể được sao chép giữa các AZ hoặc region tùy nền tảng. Nên quản lý image theo phiên bản và tự động hóa quá trình tạo VM để việc khôi phục không phụ thuộc vào thao tác thủ công hoặc cấu hình chỉ tồn tại trên máy cũ.

### 3.2. Container và Kubernetes

Trong hệ thống container, cluster có thể trải rộng trên nhiều AZ. Node pool có thể được đặt ở một hoặc nhiều zone; scheduler phân phối pod dựa trên node khả dụng, nhãn topology và các ràng buộc được cấu hình.

Để chịu được lỗi AZ, cần:

- Có đủ node và năng lực CPU, bộ nhớ ở các AZ còn lại.
- Chạy nhiều replica cho workload cần tính sẵn sàng.
- Cấu hình topology spread hoặc pod anti-affinity để tránh đặt mọi replica trên cùng một node hoặc cùng một AZ.
- Bảo đảm load balancer và đường mạng vẫn chuyển lưu lượng tới các pod còn hoạt động.
- Kiểm tra persistent volume có ràng buộc với zone hay không.

Ví dụ Deployment dưới đây minh họa việc phân phối pod theo nhãn zone. Đây là cấu hình Kubernetes; hiệu quả thực tế còn phụ thuộc số node, nhãn topology và chính sách lập lịch của cluster.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: api
      containers:
        - name: api
          image: registry.example.com/api:1.0.0
          ports:
            - containerPort: 8080
~~~

Với ràng buộc DoNotSchedule, scheduler có thể từ chối tạo pod nếu không thể duy trì mức phân phối yêu cầu. Đây là hành vi cần cân nhắc khi một zone không có node hoặc thiếu tài nguyên. Đội vận hành phải lựa chọn chính sách phù hợp giữa phân tán nghiêm ngặt và khả năng tiếp tục xếp lịch khi một zone không còn khả dụng.

### 3.3. Serverless và dịch vụ managed

Serverless giúp người dùng không phải tự quản lý host hay chọn từng máy chủ vật lý. Tuy nhiên, việc nhà cung cấp quản lý hạ tầng không có nghĩa mọi phụ thuộc đều tự động có dự phòng đa AZ hoặc đa region.

Một function triển khai ở một region vẫn có thể phụ thuộc vào database, queue, object storage, secret manager hoặc API chỉ khả dụng ở phạm vi hẹp hơn. Cần đọc cam kết khả dụng của từng dịch vụ và thiết kế lại các phụ thuộc quan trọng.

## 4. Các mô hình triển khai theo phạm vi lỗi

### 4.1. Một AZ

Mọi máy compute chính được đặt trong một AZ. Mô hình này đơn giản, dễ vận hành và có thể phù hợp với môi trường phát triển, thử nghiệm, tác vụ có thể chạy lại hoặc workload chấp nhận gián đoạn.

Nhược điểm là sự cố AZ có thể làm toàn bộ workload ngừng hoạt động. Chạy nhiều VM trong cùng AZ giúp giảm phụ thuộc vào một VM hoặc một host, nhưng không bảo vệ được trước sự cố ảnh hưởng đến cả AZ.

### 4.2. Nhiều AZ trong cùng region

Ứng dụng được triển khai trên ít nhất hai AZ trong một region. Nếu một AZ gặp sự cố, các replica ở AZ còn lại có thể tiếp tục phục vụ.

~~~mermaid
flowchart TB
    U["Người dùng"] --> LB["Regional load balancer"]
    LB --> A1
    LB --> A2
    subgraph R["Region"]
      subgraph Z1["AZ 1"]
        A1["API replica 1"]
        W1["Worker replica 1"]
      end
      subgraph Z2["AZ 2"]
        A2["API replica 2"]
        W2["Worker replica 2"]
      end
      DB["Database có cơ chế dự phòng đa AZ"]
      A1 --> DB
      A2 --> DB
    end
~~~

Để mô hình này hoạt động đúng:

1. **Phân tán compute:** đặt replica ở các AZ khác nhau. Nếu tất cả replica vẫn tập trung ở một AZ, hệ thống chưa chịu được lỗi AZ.
2. **Có năng lực dự phòng:** các AZ còn lại phải đủ CPU, bộ nhớ, số node, quota và băng thông để nhận tải khi một AZ mất.
3. **Phân phối lưu lượng:** load balancer phải kiểm tra sức khỏe của backend và ngừng gửi lưu lượng đến thành phần không hoạt động.
4. **Bảo vệ dữ liệu:** database, cache, queue và volume phải có cơ chế dự phòng phù hợp. Một ứng dụng stateless đa AZ vẫn có thể ngừng hoạt động nếu database chỉ có một bản duy nhất ở AZ bị lỗi.
5. **Xử lý phiên và trạng thái:** không lưu session hoặc file quan trọng chỉ trên ổ đĩa cục bộ của một replica. Dùng kho lưu trữ hoặc dịch vụ chia sẻ có phạm vi sẵn sàng phù hợp.
6. **Kiểm tra khả năng phục hồi:** thử mô phỏng mất một AZ, theo dõi thời gian phát hiện, chuyển lưu lượng và ổn định trở lại.

Hai cách triển khai phổ biến:

- **Active-active:** nhiều AZ cùng xử lý lưu lượng bình thường. Cần bảo đảm dữ liệu và trạng thái có thể được chia sẻ hoặc đồng bộ đúng cách.
- **Active-standby:** một AZ hoặc nhóm tài nguyên dự phòng chờ tiếp quản khi thành phần chính lỗi. Cần xác định cách phát hiện lỗi, kích hoạt dự phòng và tránh hai phía cùng ghi dữ liệu ngoài ý muốn.

### 4.3. Nhiều region

Multi-region triển khai ứng dụng hoặc bản sao dữ liệu tại nhiều region. Mô hình này có thể giảm tác động của sự cố diện rộng tại một region, hỗ trợ người dùng ở nhiều khu vực địa lý hoặc đáp ứng yêu cầu khôi phục thảm họa.

~~~mermaid
flowchart TB
    U["Người dùng"] --> G["Global DNS / traffic manager"]
    G --> R1
    G --> R2
    subgraph R1["Region chính"]
      A1["Application"]
      D1["Database primary"]
      A1 --> D1
    end
    subgraph R2["Region dự phòng"]
      A2["Application standby hoặc active"]
      D2["Database replica"]
      A2 --> D2
    end
    D1 -. "Replication" .-> D2
~~~

Multi-region có chi phí và độ phức tạp cao hơn multi-AZ. Đội ngũ phải giải quyết đồng bộ dữ liệu qua khoảng cách địa lý, định tuyến lưu lượng, quản lý bí mật và cấu hình, quota ở region dự phòng, cũng như nguy cơ xung đột khi hai region cùng ghi dữ liệu.

Không nên mặc định rằng một hệ thống đa region luôn hoạt động active-active. Có thể chọn:

- **Active-passive:** region chính xử lý tải, region dự phòng được chuẩn bị để tiếp quản.
- **Active-active:** nhiều region cùng phục vụ người dùng; dữ liệu cần cơ chế phân vùng, đồng bộ hoặc xử lý xung đột phù hợp.

Cần phân biệt:

- **High availability (HA):** duy trì hoặc nhanh chóng khôi phục dịch vụ khi có lỗi thường gặp, chẳng hạn host hoặc AZ.
- **Disaster recovery (DR):** khôi phục dịch vụ sau sự cố lớn như mất toàn bộ region, mất dữ liệu hoặc lỗi diện rộng.

Multi-AZ thường là nền tảng cho HA trong một region. Multi-region thường được cân nhắc cho DR hoặc yêu cầu phục vụ toàn cầu. Một hệ thống có thể cần cả hai, nhưng quyết định phải xuất phát từ mục tiêu kinh doanh và mức gián đoạn chấp nhận được.

## 5. RPO, RTO và tính sẵn sàng

Khi thiết kế dự phòng, cần chuyển yêu cầu kinh doanh thành các mục tiêu có thể đo lường.

- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận được để khôi phục dịch vụ sau sự cố.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể chấp nhận bị mất, thường biểu diễn bằng khoảng thời gian.

Ví dụ, một hệ thống có RTO 30 phút và RPO 5 phút cần có khả năng khôi phục dịch vụ trong vòng 30 phút và chỉ chấp nhận mất tối đa khoảng 5 phút dữ liệu theo mục tiêu đã đặt. Đây là mục tiêu thiết kế minh họa; kết quả thực tế phụ thuộc cơ chế sao chép, backup, quy trình failover và kết quả diễn tập.

Sao chép đồng bộ thường giảm nguy cơ mất dữ liệu đã xác nhận ghi nhưng có thể tăng độ trễ và phụ thuộc kết nối. Sao chép bất đồng bộ thường phù hợp hơn với khoảng cách xa nhưng có thể có độ trễ sao chép, dẫn tới RPO lớn hơn 0. Backup hỗ trợ khôi phục dữ liệu nhưng không tự động thay thế cơ chế HA, vì quá trình restore có thể mất thời gian.

SLA của nhà cung cấp là cam kết theo điều kiện dịch vụ cụ thể. SLA không tự bảo đảm kiến trúc của khách hàng đạt RTO hoặc RPO mong muốn. Cần đọc điều kiện áp dụng, phạm vi đo, ngoại lệ và yêu cầu cấu hình của dịch vụ.

## 6. Cách chọn region và AZ

Nên chọn vị trí dựa trên yêu cầu của workload và các dịch vụ mà workload phụ thuộc.

### Bước 1: Xác định người dùng và độ trễ

Đặt compute gần người dùng hoặc hệ thống gọi dịch vụ để giảm độ trễ. Với ứng dụng phục vụ nhiều khu vực, có thể dùng nhiều region hoặc lớp phân phối toàn cầu. Tuy nhiên, cần đo độ trễ đầu cuối thay vì chỉ đo khoảng cách địa lý: DNS, mạng, database và API phụ thuộc đều ảnh hưởng đến thời gian phản hồi.

### Bước 2: Xác định yêu cầu về dữ liệu và tuân thủ

Làm rõ dữ liệu nào được phép lưu trữ, xử lý và sao chép ở đâu. Kiểm tra vị trí bản sao backup, log, snapshot, khóa mã hóa và dữ liệu do dịch vụ managed tạo ra. Việc chọn region cho compute không tự động bảo đảm mọi dữ liệu liên quan đều nằm trong cùng phạm vi.

### Bước 3: Đặt mục tiêu sẵn sàng và phục hồi

Xác định workload cần chịu được lỗi nào:

- Chỉ cần phục hồi khi một VM hoặc host lỗi.
- Cần tiếp tục phục vụ khi một AZ lỗi.
- Cần khôi phục khi cả region không khả dụng.
- Cần hoạt động liên tục ở nhiều khu vực địa lý.

Mục tiêu càng cao thường đòi hỏi nhiều bản sao, nhiều năng lực dự phòng, kiểm thử thường xuyên và chi phí vận hành lớn hơn.

### Bước 4: Kiểm tra dịch vụ, loại máy và quota

Không phải region nào cũng có đủ mọi loại instance, GPU, dịch vụ managed hoặc tính năng. Kiểm tra quota cho VM, vCPU, địa chỉ IP, load balancer, disk, node và các dịch vụ phụ thuộc. Với workload quan trọng, cần xác minh region hoặc AZ dự phòng có thể cấp đủ tài nguyên trong tình huống failover, không chỉ ở điều kiện bình thường.

### Bước 5: Đánh giá dữ liệu và các phụ thuộc

Lập danh sách database, cache, queue, object storage, DNS, IAM, KMS, secret manager, registry, monitoring và các API bên ngoài. Xác định phạm vi lỗi của từng thành phần. Một thành phần có phạm vi hẹp hơn ứng dụng có thể trở thành điểm lỗi chung.

### Bước 6: Tính tổng chi phí

Chi phí không chỉ là giá VM. Cần tính cả:

- Tài nguyên dự phòng luôn chạy hoặc được giữ sẵn.
- Lưu trữ nhiều bản và snapshot.
- Truyền dữ liệu giữa AZ hoặc region.
- Load balancer, gateway, NAT và kết nối liên vùng.
- Sao chép database và backup.
- Logging, monitoring và kiểm thử DR.
- Công sức vận hành, tự động hóa và xử lý sự cố.

Multi-AZ thường tăng chi phí do cần thêm năng lực và có thể phát sinh phí truyền dữ liệu liên AZ. Multi-region thường tốn hơn nữa vì cần bản sao compute, dữ liệu và mạng ở nhiều nơi. Đổi lại, các khoản chi này có thể giảm thiệt hại do gián đoạn dịch vụ. Cần so sánh với tác động kinh doanh của downtime thay vì chỉ so sánh hóa đơn compute.

### Bảng định hướng lựa chọn

| Nhu cầu | Mô hình thường phù hợp | Điểm cần xác minh |
|---|---|---|
| Phát triển, thử nghiệm, tác vụ có thể chạy lại | Một AZ | Có thể tạo lại nhanh; dữ liệu thử nghiệm không phải dữ liệu duy nhất. |
| API hoặc dịch vụ cần tiếp tục phục vụ khi một AZ lỗi | Nhiều AZ trong một region | Replica, load balancer, dữ liệu, quota và capacity dự phòng. |
| Hệ thống cần khôi phục khi region chính gặp sự cố | Nhiều AZ kết hợp DR liên region | RPO/RTO, bản sao dữ liệu, DNS/traffic failover và diễn tập. |
| Ứng dụng phục vụ người dùng toàn cầu | Nhiều region hoặc kiến trúc phân phối toàn cầu | Độ trễ, đồng bộ dữ liệu, định tuyến, tuân thủ và chi phí. |
| Batch hoặc worker có thể chạy lại | Một hoặc nhiều AZ tùy thời hạn hoàn thành | Khả năng retry, checkpoint, hàng đợi và giới hạn thời gian xử lý. |

## 7. Ví dụ thiết kế

### Ví dụ A: API stateless cần chịu được lỗi AZ

Một API phục vụ khách hàng có thể triển khai ba replica trên ba AZ trong cùng region. Regional load balancer chỉ gửi lưu lượng tới replica khỏe mạnh. Auto scaling có thể bổ sung replica ở các AZ còn khả dụng.

Database được cấu hình theo mô hình có dự phòng đa AZ. Session và file người dùng được lưu trong các dịch vụ phù hợp với phạm vi sẵn sàng yêu cầu. Hệ thống monitoring theo dõi lỗi theo AZ để đội vận hành biết khi một vùng không còn nhận tải.

Khi thiết kế, cần thử tình huống mất một AZ và xác minh:

- Hai AZ còn lại đủ năng lực xử lý tải đỉnh hay không.
- Replica được phân phối đúng và tự phục hồi hay không.
- Load balancer loại backend lỗi trong thời gian chấp nhận được hay không.
- Database vẫn đọc/ghi được và dữ liệu không bị mất ngoài RPO đã đặt hay không.
- Các thành phần như NAT, DNS, secret manager và queue có tiếp tục hoạt động hay không.

### Ví dụ B: VM có disk gắn với một AZ

Một VM chạy ứng dụng có dữ liệu trên zonal disk. Nếu AZ chứa VM và disk gặp sự cố, tạo VM mới ở AZ khác chưa chắc có thể gắn trực tiếp disk cũ. Phương án phục hồi có thể cần snapshot, bản sao disk hoặc cơ chế replication mà dịch vụ lưu trữ hỗ trợ.

Bài học ở đây là phải thiết kế cả compute và dữ liệu. Có image VM ở AZ khác nhưng không có bản sao dữ liệu phù hợp vẫn không thể khôi phục ứng dụng đúng trạng thái.

### Ví dụ C: DR sang region thứ hai

Một hệ thống giao dịch đặt region A làm region chính và chuẩn bị region B làm nơi khôi phục. Dữ liệu được sao chép bất đồng bộ sang B. Khi region A gặp sự cố, quy trình DR xác minh trạng thái bản sao, chuyển workload sang B và cập nhật định tuyến người dùng.

Trước khi công bố hệ thống đã sẵn sàng DR, đội ngũ cần diễn tập toàn bộ quy trình: cấp compute, mở kết nối mạng, lấy bí mật, xác nhận dữ liệu, chuyển lưu lượng, kiểm tra chức năng và ghi nhận thời gian khôi phục. Cũng cần xác định cách quay lại region chính sau sự cố để tránh ghi dữ liệu đồng thời ở hai phía.

## 8. Những sai lầm thường gặp

**Chạy nhiều VM trong cùng AZ rồi coi là đa AZ.** Nhiều VM có thể giảm rủi ro lỗi một máy, nhưng vẫn chia sẻ phạm vi lỗi của AZ. Cần xác minh vị trí thực tế của từng instance.

**Chỉ phân tán tầng ứng dụng.** App có thể chạy ở nhiều AZ nhưng database, queue, disk, NAT hoặc dịch vụ xác thực lại chỉ có một điểm triển khai. Khi điểm đó lỗi, toàn hệ thống vẫn bị ảnh hưởng.

**Cho rằng autoscaling tự xử lý được lỗi AZ.** Autoscaling chỉ tạo thêm tài nguyên nếu có quota, capacity, cấu hình và thời gian khởi tạo phù hợp. Nếu mọi node pool chỉ nằm trong AZ bị lỗi, autoscaling không thể tự tạo năng lực ở AZ khác.

**Cho rằng multi-AZ đồng nghĩa multi-region.** Nhiều AZ trong một region thường giúp chống lỗi cục bộ. Chúng không tự bảo vệ trước sự cố ảnh hưởng toàn region.

**Coi backup cùng region là đủ cho mọi tình huống.** Backup cùng region có thể hữu ích khi lỗi dữ liệu hoặc tài nguyên, nhưng có thể không đáp ứng yêu cầu nếu cả region mất khả năng truy cập. Cần xác định phạm vi sao lưu theo kịch bản phục hồi.

**Chỉ đọc SLA mà không thử failover.** Cam kết dịch vụ không thay thế việc kiểm tra kiến trúc, runbook và dữ liệu của chính ứng dụng. Chỉ diễn tập mới cho thấy quy trình có đạt RTO/RPO hay không.

**Không tính chi phí liên vùng.** Sao chép dữ liệu, gọi dịch vụ qua AZ và định tuyến qua region có thể làm tăng chi phí. Cần theo dõi lưu lượng và cấu hình đường đi dữ liệu phù hợp.

**Để cấu hình chung trở thành điểm lỗi chung.** Một thay đổi sai trong IAM, DNS, firewall, secret hoặc pipeline triển khai có thể ảnh hưởng đến nhiều AZ hoặc region. Cần quản lý thay đổi, phân quyền và khả năng rollback.

## 9. Checklist trước khi triển khai

- [ ] Chọn region dựa trên người dùng, độ trễ, dữ liệu, dịch vụ sẵn có và chi phí.
- [ ] Xác định workload cần chịu được lỗi host, AZ hay cả region.
- [ ] Ghi nhận phạm vi của VM, disk, network, load balancer và dịch vụ managed.
- [ ] Phân phối replica qua các AZ phù hợp; kiểm tra topology và anti-affinity.
- [ ] Xác minh quota và capacity ở các AZ hoặc region dự phòng.
- [ ] Kiểm tra database, cache, queue, object storage và cơ chế bảo vệ dữ liệu.
- [ ] Xác định RTO, RPO, SLA và SLO liên quan.
- [ ] Tự động hóa triển khai, cấu hình, phục hồi và chuyển lưu lượng.
- [ ] Theo dõi sức khỏe và lưu lượng theo region/AZ.
- [ ] Diễn tập lỗi AZ và quy trình DR; ghi lại thời gian và kết quả thực tế.
- [ ] Ước tính chi phí compute, lưu trữ, truyền dữ liệu, backup và vận hành.

## 10. Ghi nhớ

- **Region** là phạm vi địa lý cung cấp dịch vụ cloud; lựa chọn region ảnh hưởng đến độ trễ, dữ liệu, dịch vụ sẵn có và chi phí.
- **Availability zone** là phạm vi hạ tầng độc lập tương đối trong một region; triển khai nhiều AZ giúp giảm tác động của sự cố cục bộ.
- **Phạm vi tài nguyên** có thể là zonal, regional hoặc global và phải được kiểm tra theo từng dịch vụ.
- **Tính sẵn sàng đầu cuối** phụ thuộc vào toàn bộ chuỗi compute, mạng, lưu trữ, danh tính và dịch vụ phụ thuộc.
- **Multi-AZ** thường phục vụ HA trong region; **multi-region** thường phục vụ DR hoặc nhu cầu phân phối toàn cầu.
- Một kiến trúc chỉ được xem là có khả năng phục hồi khi đã xác định RTO/RPO, có đủ năng lực dự phòng và được kiểm thử trong tình huống lỗi thực tế.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Region | Khu vực địa lý nơi nhà cung cấp cloud cung cấp một tập hợp dịch vụ và hạ tầng. |
| Availability zone (AZ) | Vị trí hạ tầng độc lập tương đối trong một region, được dùng để phân tán tài nguyên. |
| Zone | Phạm vi triển khai theo zone; cách gọi và ngữ nghĩa cụ thể phụ thuộc nhà cung cấp. |
| Failure domain | Phạm vi mà một sự cố có thể tác động tới các thành phần cùng nằm trong đó. |
| Blast radius | Phạm vi tác động thực tế của sự cố đối với hệ thống. |
| Zonal resource | Tài nguyên gắn với một AZ hoặc zone cụ thể. |
| Regional resource | Tài nguyên được quản lý trong phạm vi một region. |
| Multi-AZ | Kiến trúc phân tán tài nguyên qua nhiều AZ trong cùng region. |
| Multi-region | Kiến trúc sử dụng nhiều region. |
| HA | High availability, khả năng duy trì hoặc nhanh chóng khôi phục dịch vụ khi có lỗi. |
| DR | Disaster recovery, khả năng khôi phục hệ thống sau sự cố lớn. |
| RTO | Thời gian mục tiêu tối đa để khôi phục dịch vụ. |
| RPO | Mức mất dữ liệu tối đa có thể chấp nhận, thường tính theo thời gian. |
