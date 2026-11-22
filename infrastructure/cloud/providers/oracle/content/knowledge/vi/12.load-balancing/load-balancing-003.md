# Listeners, backend sets và backend servers

Trong chương **Cân bằng tải ứng dụng** của module **CLOUD_PROVIDERS_ORACLE**, bài học này giải thích ba thành phần tạo nên đường đi của một yêu cầu qua OCI Load Balancer: listener, backend set và backend server. Người học kết nối cấu hình cân bằng tải với IAM, compartment, VCN, Compute, giám sát và quy trình triển khai ứng dụng có tính sẵn sàng.

Ví dụ xuyên suốt là một ứng dụng chạy trên hai máy Compute trong mạng riêng. Người dùng truy cập một địa chỉ của load balancer; dịch vụ chọn một endpoint ứng dụng để xử lý. Muốn hệ thống hoạt động đúng, cần cấu hình đồng thời cửa nhận kết nối, nhóm phân phối và các endpoint nhận lưu lượng.

## 1. Mục tiêu và phạm vi

Sau bài học, người học có thể:

- Mô tả trách nhiệm và quan hệ giữa listener, backend set và backend server.
- Phân biệt cổng phía client, cổng ứng dụng và cổng health check.
- Tạo một backend set, thêm hai backend và nối listener bằng OCI CLI.
- Kiểm tra cả trạng thái cấu hình, health check và yêu cầu nghiệp vụ.
- Lập quy trình thêm máy, bảo trì một máy và xử lý các lỗi cấu hình phổ biến.

Bài sử dụng **OCI Load Balancer**, với nhóm lệnh **oci lb**. OCI Network Load Balancer là dịch vụ có mô hình và tùy chọn riêng; không lấy các lệnh hoặc giả định của bài áp dụng nguyên trạng cho dịch vụ đó.

Phần thực hành bắt đầu với load balancer và hai máy Compute đã được chuẩn bị. Việc xây dựng toàn bộ VCN hoặc cài đặt một ứng dụng Java hoàn chỉnh không phải điều kiện để hiểu ba thành phần đang học.

## 2. Mô hình ba thành phần

| Thành phần | Câu hỏi mà thành phần trả lời | Ví dụ |
| --- | --- | --- |
| Listener | Client kết nối tới đâu, bằng giao thức và cổng nào? | HTTP tại cổng 8088 của load balancer |
| Backend set | Phân phối tới nhóm nào, theo chính sách và health check nào? | app_bs dùng ROUND_ROBIN và HTTP /ready |
| Backend server | Endpoint cụ thể nào sẽ nhận kết nối từ load balancer? | 10.0.2.10:8080 hoặc 10.0.3.10:8080 |

Listener kiểm tra lưu lượng đi vào địa chỉ của load balancer. Backend set chứa chính sách phân phối, health check và danh sách backend. Backend server được xác định bằng địa chỉ và cổng dịch vụ mà load balancer có thể kết nối. [Nguồn: Listeners](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managinglisteners.htm), [Backend Sets](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingbackendsets.htm), [Backend Servers](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingbackendservers.htm).

~~~mermaid
flowchart LR
    Client["Client thử nghiệm trong VCN"] -->|"HTTP :8088"| Listener["Listener app_http"]
    Listener -->|"Default backend set"| Set["Backend set app_bs"]
    Set -->|"Chọn endpoint"| A["Backend A: 10.0.2.10:8080"]
    Set -->|"Chọn endpoint"| B["Backend B: 10.0.3.10:8080"]
    Check["HTTP health check /ready"] -.-> A
    Check -.-> B
~~~

Sơ đồ thể hiện quan hệ cấu hình, không có nghĩa mỗi yêu cầu phải đi qua thêm một máy chủ tên là “backend set”. Backend set là đối tượng cấu hình logic trong load balancer.

Hai địa chỉ ví dụ đại diện cho hai máy độc lập. Đăng ký cùng một máy bằng nhiều địa chỉ không tạo thêm năng lực hay miền chịu lỗi độc lập.

## 3. Listener: cửa nhận lưu lượng

### Cấu hình cốt lõi

Một listener cần xác định:

- Tên để quản lý trong load balancer.
- Giao thức và cổng nhận kết nối.
- Backend set mặc định.
- Cấu hình TLS khi nhận kết nối bảo mật.
- Cấu hình định tuyến hoặc xử lý yêu cầu nếu ứng dụng cần.

Ví dụ **app_http** nhận HTTP ở cổng **8088**, rồi sử dụng **app_bs** làm nhóm mặc định. Tên listener không phải tên DNS và cũng không phải địa chỉ của máy Compute.

Cổng listener và cổng backend phục vụ hai phía khác nhau của kết nối. Client có thể gọi HTTPS tại 443 trong khi ứng dụng chỉ nhận HTTP tại 8080. Không cần đổi ứng dụng sang cổng 443 chỉ vì client dùng cổng đó.

### Default backend set và định tuyến có điều kiện

Listener có một backend set mặc định. Khi bổ sung routing policy, một số yêu cầu có thể được chuyển tới nhóm khác theo điều kiện, chẳng hạn:

| Yêu cầu minh họa | Backend set dự kiến |
| --- | --- |
| Đường dẫn bắt đầu bằng /api/ | api_bs |
| Đường dẫn bắt đầu bằng /assets/ | assets_bs |
| Không khớp quy tắc nào | Nhóm mặc định của listener |

OCI đánh giá routing rule theo thứ tự và dừng tại quy tắc đầu tiên khớp; yêu cầu không khớp được chuyển tới default backend set. Đây là quyết định chọn **nhóm**; chính sách trong nhóm mới chọn **server**. [Nguồn: Routing Policies](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/routing-policy_management.htm).

Trong thực hành cơ bản, chưa gắn routing policy để quan sát rõ đường mặc định. Khi thêm quy tắc sau này, cần kiểm tra cả trường hợp khớp và không khớp.

### Hai chặng TLS cần quyết định riêng

| Phương án minh họa | Client → load balancer | Load balancer → backend |
| --- | --- | --- |
| Kết thúc TLS tại load balancer | HTTPS :443 | HTTP :8080 |
| Mã hóa cả hai chặng | HTTPS :443 | HTTPS :8443 |
| Lab trong mạng riêng của bài | HTTP :8088 | HTTP :8080 |

Cấu hình chứng thư ở listener xử lý phía client. Muốn chặng backend cũng mã hóa, phải cấu hình SSL tương ứng ở backend set và bảo đảm ứng dụng nhận được kết nối TLS. Bật HTTPS ở listener không tự mã hóa chặng sau. [Nguồn: Configuring SSL Handling](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingcertificates.htm).

Khi triển khai HTTPS, kiểm tra tên miền, thời hạn chứng thư, chuỗi tin cậy và cấu hình backend. Không giải quyết lỗi chứng thư production bằng cách yêu cầu người dùng bỏ kiểm tra TLS.

## 4. Backend set: chính sách cho một nhóm endpoint

### Những cấu hình nằm ở cấp nhóm

Backend set kết hợp danh sách server với cách phân phối và cách xác định server sẵn sàng. Những tùy chọn như SSL tới backend và session persistence cũng có thể được đặt ở cấp này. Một backend set có thể liên kết với một hoặc nhiều listener trong OCI Load Balancer. [Nguồn: Backend Sets for Load Balancers](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingbackendsets.htm).

Ví dụ, một nhóm **orders_bs** dành cho dịch vụ đặt hàng có thể có health check và chính sách khác nhóm **reports_bs** phục vụ báo cáo dài. Tách nhóm theo nhu cầu vận hành giúp tránh một thay đổi health check ảnh hưởng mọi dịch vụ.

Không nên chia nhóm chỉ vì muốn đặt tên từng máy. Danh sách máy trong cùng nhóm cần phục vụ được loại yêu cầu mà listener hoặc routing policy gửi tới.

### Chính sách phân phối

Ba chính sách thường gặp trong OCI Load Balancer:

| Giá trị cấu hình | Ý nghĩa chính | Điều cần cân nhắc |
| --- | --- | --- |
| ROUND_ROBIN | Phân phối tuần tự giữa các backend phù hợp, có xét trọng số | Hữu ích với các máy có năng lực và tải tương đối tương đồng |
| LEAST_CONNECTIONS | Ưu tiên backend có ít kết nối đang hoạt động hơn | Số kết nối không biểu diễn đầy đủ CPU hay độ nặng của yêu cầu |
| IP_HASH | Dùng địa chỉ IP nguồn để duy trì lựa chọn backend khi backend còn sẵn sàng | Nhiều người dùng sau NAT có thể cùng chung IP nguồn |

Các giá trị chính sách trên được Oracle mô tả trong [cấu hình policy cho Load Balancer](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengconfiguringloadbalancersnetworkloadbalancers-subtopic.htm).

Không dùng mười lần refresh trình duyệt để khẳng định lưu lượng phải chia đúng 5–5. Kết nối được tái sử dụng, session persistence, trọng số và tình trạng backend đều có thể ảnh hưởng quan sát. Đánh giá bằng nhiều yêu cầu có kiểm soát cùng log phía server.

### Session persistence

Ứng dụng có thể cần đưa các yêu cầu cùng phiên về một backend. Tuy nhiên, gắn phiên không làm dữ liệu trong bộ nhớ của một máy trở nên sẵn sàng trên máy khác.

Ví dụ, nếu giỏ hàng chỉ nằm trong RAM của backend A, việc A lỗi vẫn có thể làm mất giỏ hàng dù load balancer chuyển yêu cầu sang B. Kiến trúc cần quyết định nơi lưu trạng thái dùng chung hoặc khả năng phục hồi phiên, thay vì chỉ bật một tùy chọn ở backend set.

Với lab kiểm tra phân phối, giữ cấu hình session persistence đơn giản và ghi rõ có bật hay không. Khi kết quả khác dự kiến, kiểm tra cookie và kết nối trước khi đổi policy.

## 5. Backend server: endpoint thực sự phục vụ

### Danh tính IP và cổng

Các backend sau là ba endpoint khác nhau:

~~~text
10.0.2.10:8080
10.0.2.10:9090
10.0.3.10:8080
~~~

Hai endpoint đầu có thể là hai tiến trình trên cùng một máy. Load balancer cần biết đúng cổng ứng dụng, không chỉ biết máy Compute nào đang chạy.

Trong cùng VCN, sử dụng private IP phù hợp giúp load balancer kết nối tới dịch vụ nội bộ. Quyền truy cập mạng, route và firewall vẫn phải cho phép đường đi. Việc thêm một địa chỉ vào backend set không tự mở cổng trên hệ điều hành. [Nguồn: Backend Servers for Load Balancers](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingbackendservers.htm).

Nếu ứng dụng chỉ bind vào 127.0.0.1, thao tác gọi ngay trên máy có thể thành công nhưng load balancer vẫn không truy cập được. Cần cấu hình địa chỉ bind phù hợp với mạng riêng và giới hạn quyền truy cập bằng các lớp kiểm soát mạng.

### Weight, drain, offline và backup

| Thuộc tính | Ý nghĩa vận hành |
| --- | --- |
| Weight | Điều chỉnh tỷ trọng phân phối theo policy; không phải phần trăm CPU được cấp |
| Drain | Ngừng kết nối TCP mới và yêu cầu HTTP mới không gắn phiên tới backend để phục vụ bảo trì |
| Offline | Ngăn load balancer chuyển lưu lượng tới backend đó |
| Backup | Chỉ sử dụng khi tất cả backend thông thường không được đánh dấu backup đều thất bại health check |

Với drain, cần chú ý các yêu cầu gắn phiên và kết nối đang tồn tại. Không coi việc bật drain là bằng chứng mọi công việc trên máy đã hoàn tất. Backend backup cũng không tương thích với policy IP_HASH. [Nguồn: Editing a Backend Server](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/update_backend_server.htm).

Backup trong một backend set là vai trò phân phối tới server dự phòng, không tự triển khai một phương án phục hồi liên vùng cho ứng dụng.

Một backend có health check OK vẫn có thể không nhận yêu cầu như kỳ vọng vì đang offline, drain, backup hoặc không thuộc nhóm mà listener đang sử dụng. Vì vậy, chẩn đoán phải đọc cả health lẫn cấu hình.

## 6. Health check: kiểm tra đúng khả năng phục vụ

### TCP và HTTP kiểm tra điều gì?

TCP health check xác nhận khả năng thiết lập kết nối TCP. HTTP health check gửi yêu cầu tới đường dẫn đã cấu hình rồi kiểm tra mã phản hồi hoặc nội dung. Kết quả được dùng để đưa backend ra khỏi và trở lại vòng phân phối khi tình trạng thay đổi. [Nguồn: Health Check Policies](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/load_balancer_health_management.htm).

Một tiến trình có thể mở cổng nhưng chưa phục vụ được giao dịch. Vì vậy, cần chọn phép kiểm tra phù hợp với loại dịch vụ, thay vì chỉ chọn kiểm tra dễ thành công nhất.

Trong ví dụ, mỗi backend cung cấp:

~~~text
GET /ready
HTTP status: 200 khi có thể nhận yêu cầu
HTTP status khác 200 khi chủ động báo chưa sẵn sàng

GET /
Nội dung giả lập có tên node, chẳng hạn app-a hoặc app-b
~~~

Tên **/ready** là hợp đồng của ứng dụng ví dụ, không phải endpoint OCI tự tạo. Ứng dụng phải thực sự triển khai đường dẫn đó.

### Ba cổng thường bị nhầm

| Vai trò cổng | Giá trị trong lab | Nơi sử dụng |
| --- | --- | --- |
| Listener port | 8088 | Client gọi load balancer |
| Backend traffic port | 8080 | Load balancer chuyển yêu cầu tới ứng dụng |
| Health check port | 8080 | Dịch vụ kiểm tra GET /ready |

Health check có thể dùng cổng riêng nếu kiến trúc cần, nhưng thành công trên cổng quản trị riêng chưa chứng minh cổng phục vụ người dùng hoạt động. Khi không chỉ định cổng health check, OCI CLI cho phép sử dụng thông tin cổng của từng backend. [Nguồn: backend-set create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-set/create.html).

Trong bài, đặt rõ health check port 8080 để dễ kiểm tra và chỉ đưa các backend cùng cổng vào nhóm.

### Chọn điều kiện và độ nhạy

Cấu hình minh họa:

~~~text
protocol = HTTP
port = 8080
path = /ready
expected status = 200
interval = 10000 ms
timeout = 3000 ms
retries = 3
~~~

Interval là khoảng giữa các lần kiểm tra; timeout giới hạn thời gian chờ phản hồi; retries ảnh hưởng quyết định tình trạng backend. Không lấy phép nhân đơn giản từ các giá trị này làm cam kết thời gian phát hiện lỗi của cả ứng dụng. [Nguồn: cấu hình health check của backend set](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingbackendsets_topic-Creating_Backend_Sets.htm).

Endpoint readiness nên rẻ để gọi, có thời gian xử lý ổn định và không tiết lộ dữ liệu nhạy cảm. Tránh dùng trang đăng nhập, endpoint luôn redirect hoặc trang tĩnh luôn trả 200 dù ứng dụng đã hỏng.

Nếu health check phụ thuộc cơ sở dữ liệu dùng chung, cần đánh giá tình huống lỗi cơ sở dữ liệu làm toàn bộ máy cùng bị báo chưa sẵn sàng. Quyết định kiểm tra phụ thuộc nào phải dựa trên loại yêu cầu mà ứng dụng còn phục vụ được khi phụ thuộc đó lỗi.

## 7. Chuẩn bị thực hành trong OCI

### Tài nguyên và hợp đồng ứng dụng

Chuẩn bị:

- Một **private OCI Load Balancer** trong VCN lab, đã ở trạng thái hoạt động.
- Hai máy Compute có private IP mẫu **10.0.2.10** và **10.0.3.10**; thay bằng IP thật.
- Ứng dụng HTTP trên cổng 8080 ở cả hai máy.
- Đường dẫn /ready và nội dung nhận diện node theo mô tả bên trên.
- Một máy thử nghiệm có đường mạng tới địa chỉ private của load balancer.
- OCI CLI và danh tính được cấp quyền trong đúng compartment.

Không chạy lệnh tạo lại listener hoặc backend set nếu tên đó đang được một ứng dụng khác sử dụng. Ví dụ dưới đây dùng tên mới trong môi trường lab đã xác định.

### IAM và quyền mạng là hai lớp riêng

Ví dụ policy cấp quyền quản lý load balancer trong compartment riêng:

~~~text
Allow group Default/LoadBalancerLabOperators to manage load-balancers in compartment LoadBalancingLab
~~~

Thay domain, nhóm và compartment theo môi trường thật. Nếu cần quản lý thêm mạng, Compute, chứng thư hoặc log, phải có quyền tương ứng. Cấp quyền load balancer không tự cấp toàn bộ các quyền đó. Oracle có ví dụ phân quyền riêng cho quản lý và cập nhật load balancer trong [Common Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm).

Đối với mạng, kiểm tra các đường đi sau:

| Nguồn → đích | Cho phép trong lab |
| --- | --- |
| Máy thử nghiệm → load balancer | TCP 8088 |
| Load balancer → hai backend | TCP 8080 |
| Luồng health check → hai backend | TCP 8080 theo cấu hình /ready |
| Đường phản hồi | Cho phép theo mô hình stateful hoặc quy tắc chiều về tương ứng |

Có thể dùng NSG của load balancer và NSG của ứng dụng để giới hạn kết nối trong VCN. Đồng thời kiểm tra security list, route và firewall hệ điều hành; một lớp cho phép không bù được lớp khác đang chặn.

Không cần mở cổng 8080 của backend cho toàn Internet để client truy cập qua listener. Với private load balancer, máy chạy CLI hoặc trình duyệt ở ngoài mạng không tự có đường truy cập chỉ nhờ sở hữu thông tin xác thực OCI.

## 8. Tạo backend set, backend và listener bằng PowerShell

Các lệnh sau chỉ là nội dung thực hành; thay biến mẫu trước khi chạy trên OCI. Chạy tuần tự, đợi thay đổi trước hoàn tất rồi mới gửi thay đổi phụ thuộc trên cùng load balancer.

### Khai báo biến

~~~powershell
$Region = 'THAY_REGION'
$LoadBalancerId = 'THAY_OCID_LOAD_BALANCER'
$BackendSetName = 'app_bs'
$ListenerName = 'app_http'
$BackendIps = @('10.0.2.10', '10.0.3.10')
$BackendPort = 8080
$ListenerPort = 8088
~~~

OCID load balancer và region phải thuộc cùng tài nguyên. Backend set name là tên trong load balancer, không phải OCID của compartment.

### Tạo backend set

~~~powershell
$CreateSetArgs = @(
    'lb', 'backend-set', 'create',
    '--region', $Region,
    '--load-balancer-id', $LoadBalancerId,
    '--name', $BackendSetName,
    '--policy', 'ROUND_ROBIN',
    '--health-checker-protocol', 'HTTP',
    '--health-checker-port', '8080',
    '--health-checker-url-path', '/ready',
    '--health-checker-return-code', '200',
    '--health-checker-interval-in-ms', '10000',
    '--health-checker-timeout-in-ms', '3000',
    '--health-checker-retries', '3',
    '--wait-for-state', 'SUCCEEDED',
    '--max-wait-seconds', '300'
)
oci @CreateSetArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Tao backend set chua duoc xac nhan thanh cong'
}
~~~

Các tham số health checker thuộc backend set. Lúc này nhóm chưa có server nhận lưu lượng; tạo nhóm thành công chưa chứng minh ứng dụng sẵn sàng. [Tham chiếu OCI CLI: backend-set create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-set/create.html).

### Thêm hai backend

~~~powershell
foreach ($BackendIp in $BackendIps) {
    $CreateBackendArgs = @(
        'lb', 'backend', 'create',
        '--region', $Region,
        '--load-balancer-id', $LoadBalancerId,
        '--backend-set-name', $BackendSetName,
        '--ip-address', $BackendIp,
        '--port', "$BackendPort",
        '--weight', '1',
        '--backup', 'false',
        '--drain', 'false',
        '--offline', 'false',
        '--wait-for-state', 'SUCCEEDED',
        '--max-wait-seconds', '300'
    )
    oci @CreateBackendArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Them backend $BackendIp chua duoc xac nhan thanh cong"
    }
}
~~~

Hai máy có weight 1, đều tham gia phục vụ bình thường khi đủ điều kiện. Việc thêm một backend đăng ký địa chỉ và cổng; không khởi động hoặc cài đặt ứng dụng trên Compute. [Tham chiếu OCI CLI: backend create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend/create.html).

### Tạo listener liên kết tới nhóm

~~~powershell
$CreateListenerArgs = @(
    'lb', 'listener', 'create',
    '--region', $Region,
    '--load-balancer-id', $LoadBalancerId,
    '--name', $ListenerName,
    '--protocol', 'HTTP',
    '--port', "$ListenerPort",
    '--default-backend-set-name', $BackendSetName,
    '--wait-for-state', 'SUCCEEDED',
    '--max-wait-seconds', '300'
)
oci @CreateListenerArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Tao listener chua duoc xac nhan thanh cong'
}
~~~

Trường **--default-backend-set-name** hoàn tất liên kết từ listener tới nhóm. Cổng 8088 cần được cho phép trên đường client tới load balancer. [Tham chiếu OCI CLI: listener create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/listener/create.html).

Nếu CLI hết thời gian chờ, kiểm tra work request trước khi chạy lại. Timeout của máy gọi chưa chứng minh thao tác OCI đã bị hủy; chạy lại có thể gặp tài nguyên đã tồn tại hoặc thay đổi vẫn đang thực hiện.

### Tra cứu work request khi cần

Lấy work request ID của thao tác từ phản hồi CLI hoặc Console:

~~~powershell
$WorkRequestId = 'THAY_WORK_REQUEST_ID'
$WorkRequestArgs = @(
    'lb', 'work-request', 'get',
    '--region', $Region,
    '--work-request-id', $WorkRequestId
)
oci @WorkRequestArgs
~~~

Chỉ tiếp tục khi thao tác liên quan đã hoàn tất đúng trạng thái. Nếu thất bại, đọc chi tiết lỗi trước khi sửa hoặc gửi lại. [Tham chiếu OCI CLI: work-request get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/work-request/get.html).

## 9. Kiểm chứng theo ba lớp

### Lớp cấu hình

Trên Console, đọc lại:

1. Listener app_http có đúng HTTP, cổng 8088 và default backend set app_bs.
2. app_bs có đúng policy, đường dẫn /ready và cổng health check.
3. Danh sách backend chứa đúng hai cặp IP:8080.
4. Các cờ weight, backup, drain và offline đúng với mục đích lab.

Một lỗi tên nhóm có thể làm listener hợp lệ về mặt tồn tại nhưng dẫn lưu lượng tới nhóm khác với dự kiến. Bằng chứng kiểm tra phải nêu rõ tên nhóm, không chỉ chụp trạng thái chung của load balancer.

### Lớp sức khỏe backend

~~~powershell
$SetHealthArgs = @(
    'lb', 'backend-set-health', 'get',
    '--region', $Region,
    '--load-balancer-id', $LoadBalancerId,
    '--backend-set-name', $BackendSetName
)
oci @SetHealthArgs

$BackendHealthArgs = @(
    'lb', 'backend-health', 'get',
    '--region', $Region,
    '--load-balancer-id', $LoadBalancerId,
    '--backend-set-name', $BackendSetName,
    '--backend-name', '10.0.2.10:8080'
)
oci @BackendHealthArgs
~~~

Dùng kết quả nhóm để tìm backend cần điều tra, sau đó xem chi tiết từng backend. Kết quả kiểm tra từ cả thành phần primary và standby của load balancer có thể góp vào trạng thái sức khỏe; khi thấy Warning cần đọc chi tiết thay vì chỉ gọi thử ứng dụng từ một máy. [Tham chiếu sức khỏe backend set](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-set-health/get.html), [chi tiết sức khỏe backend](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/get_backend-server-health.htm).

Không đánh đồng màu xanh ở backend với việc client đã truy cập được listener. Hai luồng có nguồn, cổng và điều kiện mạng khác nhau.

### Lớp yêu cầu ứng dụng

Chạy từ máy thử nghiệm có đường tới private load balancer:

~~~powershell
$LoadBalancerAddress = 'THAY_PRIVATE_IP_LOAD_BALANCER'
$ApplicationUri = 'http://{0}:{1}/' -f $LoadBalancerAddress, $ListenerPort

1..20 | ForEach-Object {
    $Response = Invoke-WebRequest -Uri $ApplicationUri -UseBasicParsing
    [pscustomobject]@{
        StatusCode = $Response.StatusCode
        Body = $Response.Content
    }
}
~~~

Đối chiếu nội dung app-a/app-b với access log ở ứng dụng. Bài kiểm tra giúp quan sát phân phối; không yêu cầu hai máy xuất hiện xen kẽ tuyệt đối trong mọi lần gọi.

Với HTTPS có tên miền, kiểm tra bằng đúng tên mà chứng thư bao phủ. Gọi trực tiếp IP rồi bỏ qua xác minh chứng thư không thay thế được kiểm tra đường truy cập thật của người dùng.

## 10. Bảo trì một backend theo từng bước

Giả sử muốn nâng cấp app-a trong khi app-b tiếp tục phục vụ. Trước hết phải xác nhận app-b đủ khỏe và đủ năng lực nhận tải còn lại.

### Đưa backend vào drain

Trong lab này, backend A ban đầu có weight 1 và cả backup/offline đều false:

~~~powershell
$DrainArgs = @(
    'lb', 'backend', 'update',
    '--region', $Region,
    '--load-balancer-id', $LoadBalancerId,
    '--backend-set-name', $BackendSetName,
    '--backend-name', '10.0.2.10:8080',
    '--weight', '1',
    '--backup', 'false',
    '--offline', 'false',
    '--drain', 'true',
    '--wait-for-state', 'SUCCEEDED',
    '--max-wait-seconds', '300'
)
oci @DrainArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Can kiem tra lai thao tac drain truoc khi bao tri'
}
~~~

UpdateBackend yêu cầu truyền các giá trị weight, backup, offline và drain. Với tài nguyên thật, đọc cấu hình hiện tại và giữ đúng các giá trị cần giữ; không sao chép các giá trị của lab một cách mù quáng. Có thể sử dụng ETag và **--if-match** khi cần tránh ghi đè thay đổi đồng thời. [Tham chiếu OCI CLI: backend update](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend/update.html).

### Chờ và triển khai

Sau khi drain:

1. Quan sát kết nối và yêu cầu đang chạy trên app-a.
2. Xử lý trường hợp phiên gắn, WebSocket hoặc tác vụ dài theo thiết kế ứng dụng.
3. Dừng dịch vụ một cách có kiểm soát khi đã đạt điều kiện bảo trì.
4. Nâng cấp và khởi động lại ứng dụng.
5. Xác minh /ready, phiên bản ứng dụng và một yêu cầu nghiệp vụ.
6. Bỏ drain bằng một thao tác update với các giá trị đã kiểm tra.
7. Quan sát lỗi và độ trễ khi máy nhận tải trở lại.

Không chỉ đợi một khoảng thời gian tùy ý rồi tắt máy. Điều kiện chuyển bước cần dựa trên hành vi thực tế của ứng dụng và giới hạn thời gian đã thống nhất.

Trong production, thay đổi policy của cả backend set cũng cần được lập kế hoạch: Oracle lưu ý thao tác này có thể gián đoạn lưu lượng và làm rơi kết nối đang hoạt động. [Nguồn: Editing a Backend Set](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingbackendsets_topic-Editing_Backend_Sets.htm).

## 11. Phân tích sự cố theo đường đi yêu cầu

| Triệu chứng | Thứ tự kiểm tra gợi ý |
| --- | --- |
| Client không kết nối được listener | DNS hoặc IP, private/public, route, ingress listener, đúng cổng |
| Backend health OK nhưng truy cập thất bại | Listener, default backend set, routing policy, đường client tới listener |
| Tất cả backend bị báo lỗi | Health check port/path/protocol, ứng dụng bind, NSG, firewall và route |
| Chỉ một backend bị lỗi | Tiến trình và /ready trên máy đó, IP/port đăng ký, quyền mạng của subnet |
| Backend OK nhưng không thấy yêu cầu | Offline, drain, backup, session persistence, policy và nhóm thực sự được chọn |
| Chỉ đường dẫn nào đó bị lỗi | Routing rule, thứ tự khớp và hợp đồng URL của dịch vụ nhận |
| HTTPS lỗi dù HTTP nội bộ tốt | Chứng thư listener, tên miền, chuỗi tin cậy; SSL backend nếu được bật |
| Lỗi khi tải tăng | Năng lực backend còn lại, kết nối, timeout và giới hạn của load balancer |

Oracle mô tả trường hợp health check đều OK nhưng listener không truyền được lưu lượng, cũng như tình huống security rule chặn nguồn health check. Có thể xem địa chỉ nguồn health check trong chi tiết backend để điều tra. [Nguồn: Understanding Load Balancer Health Issues](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/understanding_health_issues.htm).

Các mã lỗi HTTP cần được đối chiếu với log để biết thành phần nào tạo ra. Không kết luận mọi phản hồi 5xx đều do load balancer hoặc mọi timeout đều do health check.

Một trình tự điều tra hữu ích:

~~~text
Client
  → địa chỉ và cổng listener
  → listener và routing policy
  → backend set được chọn
  → trạng thái và thuộc tính backend
  → kết nối mạng tới IP:port
  → ứng dụng và phụ thuộc
~~~

Chỉ thay đổi một yếu tố có chủ đích mỗi lần và ghi lại thời điểm. Mở rộng đồng loạt mọi security rule có thể che nguyên nhân thật và làm mất giới hạn mạng cần thiết.

## 12. Thiết kế tính sẵn sàng và kiểm soát chi phí

Hai backend giúp tiếp tục phục vụ khi một máy không nhận yêu cầu, với điều kiện máy còn lại đủ năng lực và các phụ thuộc vẫn hoạt động. Hãy bố trí các máy theo miền chịu lỗi phù hợp với region và kiểm thử tình huống mất một máy.

Có thể đánh giá năng lực dự phòng bằng giả định:

~~~text
Tải lúc một máy dừng
  phải nhỏ hơn năng lực phục vụ an toàn
  của các backend còn đủ điều kiện nhận lưu lượng
~~~

Ví dụ giả định mỗi máy chỉ nên xử lý tối đa 100 yêu cầu/giây trong giới hạn độ trễ của ứng dụng. Với tổng tải 150 yêu cầu/giây, hai máy có thể vận hành bình thường nhưng một máy còn lại không đáp ứng mục tiêu khi máy kia bảo trì. Đây là bài toán năng lực, không phải lỗi listener.

Load balancer cũng không tự đồng bộ phiên trong RAM, dữ liệu cục bộ hoặc trạng thái giao dịch giữa các máy. Với ứng dụng Oracle Database, cần kiểm tra pool kết nối và hành vi khi phụ thuộc cơ sở dữ liệu lỗi hoặc chậm.

Về chi phí và vận hành:

- Chọn năng lực load balancer theo số liệu lưu lượng và mục tiêu dự phòng.
- Tính cả Compute, log, giám sát và lượng dữ liệu truyền phù hợp kiến trúc.
- Tách tên backend set hoặc listener khi có lý do định tuyến và vận hành rõ ràng.
- Đặt thời hạn giữ log phù hợp, đồng thời giữ bằng chứng cần cho điều tra.
- Dọn tài nguyên lab khi đã xác nhận không còn phụ thuộc.

Không suy ra “thêm listener” đồng nghĩa “thêm một máy load balancer” hoặc một khoản phí độc lập cố định. Đánh giá chi phí dựa trên tài nguyên và biểu giá thực tế tại thời điểm triển khai.

## 13. Bài thực hành củng cố

Dùng môi trường lab để hoàn thành:

1. Vẽ đường đi từ client qua listener tới một backend cụ thể, ghi rõ ba cổng.
2. Tạo app_bs, đăng ký hai máy và liên kết app_http.
3. Lưu bằng chứng cấu hình, health check và phản hồi từ cả hai node.
4. Làm /ready của một máy trả mã không đạt, quan sát chuyển trạng thái và hành vi ứng dụng.
5. Khôi phục máy, rồi thử drain để so sánh tình huống bảo trì có chủ đích.
6. Chỉ đổi default backend set trong một môi trường thử nghiệm có nhóm thứ hai; giải thích kết quả trước và sau.
7. Đánh giá khả năng đáp ứng tải khi chỉ còn một backend.

Sản phẩm cần có là sơ đồ cấu hình, danh sách endpoint, phạm vi mạng/IAM, kết quả kiểm tra và quy trình bảo trì. Một ảnh trạng thái load balancer hoạt động chưa thay thế được các bằng chứng đó.

Khi kết thúc, khôi phục các cấu hình đã thay để thử lỗi, xác định tài nguyên cần giữ và chỉ dọn đúng phần lab do mình quản lý.

## 14. Các điểm cần nắm vững

Listener xác định nơi nhận kết nối và nhóm mặc định. Backend set xác định cách chọn và kiểm tra nhóm server. Backend server là địa chỉ ứng dụng cụ thể với cổng và các thuộc tính tham gia phục vụ.

Khi triển khai hoặc sửa lỗi, đi theo đúng quan hệ đó, đồng thời kiểm tra mạng và ứng dụng. Một cấu hình đáng tin cậy phải được chứng minh bằng việc yêu cầu đi qua đúng listener, tới đúng nhóm và nhận phản hồi hợp lệ từ backend sẵn sàng.