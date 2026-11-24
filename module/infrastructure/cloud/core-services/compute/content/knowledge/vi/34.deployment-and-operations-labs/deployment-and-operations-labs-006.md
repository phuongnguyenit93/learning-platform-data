# Đưa nhóm máy sau cân bằng tải và kiểm thử health check

Một ứng dụng chạy trên nhiều máy ảo chỉ đạt tính sẵn sàng khi lưu lượng được phân phối tới các máy có khả năng phục vụ request. Bộ cân bằng tải (load balancer) đứng trước nhóm máy backend, nhận kết nối từ client và chuyển request tới một backend phù hợp. Health check giúp bộ cân bằng tải nhận biết backend nào đang hoạt động, backend nào cần tạm ngừng nhận traffic và khi nào có thể đưa máy trở lại nhóm phục vụ.

Trong bài lab này, bạn sẽ chuẩn bị một nhóm máy backend, tạo backend pool/target group, gắn nhóm máy vào listener của load balancer, cấu hình health check và kiểm thử các trạng thái healthy/unhealthy. Bạn cũng sẽ kiểm tra firewall, traffic draining, logging và cách xử lý khi health check báo lỗi dù ứng dụng vẫn chạy.

Bài học thuộc module **CLOUD_CORE_SERVICES_COMPUTE**, chương **Thực hành triển khai và vận hành**. Trọng tâm là quy trình đưa một nhóm VM/instance vào sau load balancer và xác nhận hoạt động bằng phép thử thực tế. Tên resource và màn hình cấu hình có thể khác nhau giữa AWS, Azure, Google Cloud và các nền tảng khác; bài lab dùng khái niệm chung, kèm ví dụ lệnh Linux và HTTP có thể áp dụng trên nhiều môi trường.

## 1. Mục tiêu và kết quả cần đạt

Sau bài lab, bạn có thể:

- Giải thích quan hệ giữa load balancer, listener, backend pool/target group và health check.
- Chuẩn bị ít nhất hai máy backend có ứng dụng và health endpoint giống nhau.
- Đăng ký backend vào pool và cấu hình listener chuyển traffic tới pool.
- Chọn protocol, port, path, interval, timeout và ngưỡng healthy/unhealthy phù hợp.
- Kiểm tra backend healthy từ góc nhìn load balancer và từ client.
- Tạo lỗi có kiểm soát để xác nhận backend unhealthy bị loại khỏi luồng phục vụ.
- Khôi phục backend và xác nhận máy được đưa trở lại pool.
- Thực hiện draining trước khi dừng hoặc cập nhật backend.
- Đọc log và metrics để tìm nguyên nhân khi probe thất bại.

Kết quả mong đợi: client truy cập một địa chỉ frontend ổn định; load balancer phân phối request tới nhiều backend healthy; khi một backend lỗi, request mới tiếp tục được phục vụ bởi backend còn khỏe; sau khi khôi phục, backend quay lại trạng thái healthy.

## 2. Kiến trúc lab

Mô hình gồm một load balancer và hai backend trong cùng network hoặc các network có định tuyến phù hợp. Client chỉ truy cập frontend của load balancer. Backend nhận traffic ứng dụng từ load balancer và nhận health probe từ nguồn probe được nền tảng quy định.

~~~mermaid
flowchart LR
    C["Client"] -->|HTTP/HTTPS| LB["Load balancer"]
    LB --> L["Listener :80 or :443"]
    L --> P["Backend pool / target group"]
    P --> B1["Backend VM 1"]
    P --> B2["Backend VM 2"]
    LB -. "Health probe" .-> B1
    LB -. "Health probe" .-> B2
    B1 --> APP1["Application + /health"]
    B2 --> APP2["Application + /health"]
~~~

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| Frontend | Địa chỉ IP hoặc DNS mà client truy cập |
| Listener | Nhận kết nối trên protocol/port và áp dụng rule |
| Rule | Chọn backend pool theo host, path hoặc rule mặc định |
| Backend pool/target group | Danh sách VM, IP hoặc endpoint nhận traffic |
| Health probe | Gửi request định kỳ để đánh giá trạng thái backend |
| Backend application | Xử lý request và trả response |
| Security group/firewall | Giới hạn client, load balancer và probe được phép kết nối |

Tên gọi target group, backend pool, backend set hoặc server pool phụ thuộc nhà cung cấp. Trong bài này, các thuật ngữ backend pool và target group cùng chỉ nhóm đích nhận traffic.

## 3. Luồng request và luồng health check

Hai luồng này có liên quan nhưng không giống nhau:

1. Client mở kết nối tới frontend.
2. Listener nhận kết nối và áp dụng rule.
3. Load balancer chọn một backend đang healthy theo thuật toán phân phối.
4. Backend xử lý request và trả response qua load balancer.
5. Độc lập với request của client, health probe gửi request định kỳ tới từng backend.
6. Kết quả probe cập nhật trạng thái backend trong pool.
7. Backend không đạt ngưỡng được đánh dấu unhealthy và không nhận request mới theo behavior của dịch vụ.

~~~mermaid
sequenceDiagram
    participant Client
    participant LB as Load Balancer
    participant VM1 as Backend VM 1
    participant VM2 as Backend VM 2
    Client->>LB: GET /
    LB->>VM1: Forward request
    VM1-->>LB: 200 OK
    LB-->>Client: 200 OK
    LB->>VM1: GET /health
    VM1-->>LB: 200 healthy
    LB->>VM2: GET /health
    VM2-->>LB: 200 healthy
~~~

Không nên suy luận backend healthy chỉ từ việc trang chủ trả về 200 cho một lần truy cập. Health check là phép đo lặp lại, có timeout và ngưỡng; trạng thái của pool phản ánh kết quả theo cấu hình probe và cơ chế của provider.

## 4. Chuẩn bị môi trường

Lab cần:

- Một virtual network/VPC/VNet có subnet cho load balancer và backend.
- Hai VM Linux có thể truy cập qua SSH hoặc công cụ quản trị.
- Một load balancer layer 7 cho HTTP/HTTPS hoặc layer 4 nếu ứng dụng yêu cầu TCP.
- Quyền tạo listener, backend pool/target group và health probe.
- Quyền chỉnh security group/network security group/firewall.
- Một client có thể truy cập frontend và chạy curl.

Đặt tên dễ nhận biết:

| Resource | Tên lab |
|---|---|
| Load balancer | lb-compute-lab |
| Backend pool | pool-app-lab |
| Backend 1 | app-vm-01 |
| Backend 2 | app-vm-02 |
| Listener | listener-http |
| Health endpoint | /health |

Không sử dụng địa chỉ IP hoặc tên resource ví dụ làm giá trị thực tế nếu chưa được cấp trong môi trường của bạn. Ghi lại IP private của từng backend và DNS/IP frontend sau khi tạo resource.

### 4.1. Kiểm tra network trước khi cấu hình

Xác nhận:

- Backend nằm trong subnet/VPC/VNet có thể được load balancer tiếp cận.
- Route table có đường đi hợp lệ.
- Network ACL hoặc firewall không chặn traffic giữa load balancer và backend.
- Backend có thể resolve DNS hoặc truy cập dependency mà health endpoint cần.
- Client có đường đi tới frontend.
- Không dùng public IP backend nếu kiến trúc không yêu cầu.

Nếu load balancer là internal, client phải ở network có route tới frontend. Nếu là internet-facing, chỉ frontend được public; backend vẫn nên ở private subnet khi phù hợp.

## 5. Chuẩn bị hai backend đồng nhất

Hai máy cần chạy cùng ứng dụng, cùng phiên bản và cùng contract của endpoint. Nếu app-vm-01 trả response khác app-vm-02, việc kiểm thử phân phối tải sẽ khó diễn giải.

Ví dụ dưới đây dùng Nginx trên Ubuntu/Debian để tạo một backend HTTP đơn giản. Trên cả hai máy:

~~~bash
sudo apt-get update
sudo apt-get install -y nginx
sudo systemctl enable --now nginx
~~~

Trên backend thứ nhất, tạo nội dung nhận diện:

~~~bash
echo "served-by=app-vm-01" | sudo tee /var/www/html/index.html
echo "healthy" | sudo tee /var/www/html/health
sudo systemctl status nginx --no-pager
~~~

Trên backend thứ hai, chỉ thay tên node:

~~~bash
echo "served-by=app-vm-02" | sudo tee /var/www/html/index.html
echo "healthy" | sudo tee /var/www/html/health
sudo systemctl status nginx --no-pager
~~~

Kiểm tra trực tiếp trên từng máy:

~~~bash
curl -i http://127.0.0.1/
curl -i http://127.0.0.1/health
~~~

Kết quả mong đợi: trang chủ trả HTTP 200 cùng tên node tương ứng; /health trả HTTP 200 và body healthy. Nếu service không chạy, xem log:

~~~bash
sudo journalctl -u nginx -n 50 --no-pager
sudo tail -n 50 /var/log/nginx/error.log
~~~

Trong ứng dụng thật, endpoint /health cần được triển khai trong application server hoặc reverse proxy theo đúng readiness contract. File tĩnh chỉ phù hợp với bước lab network cơ bản; nó không chứng minh ứng dụng, database hay dependency đã sẵn sàng.

## 6. Thiết kế health endpoint

Health endpoint là giao diện nhỏ để một thành phần khác kiểm tra khả năng phục vụ của ứng dụng. Nó nên nhanh, ổn định, không yêu cầu đăng nhập tương tác và không trả thông tin nhạy cảm.

Các loại endpoint thường gặp:

| Endpoint | Mục đích | Nội dung kiểm tra |
|---|---|---|
| /health/live | Process còn sống | Event loop/process không bị treo |
| /health/ready | Có thể nhận traffic | App đã khởi tạo và dependency bắt buộc sẵn sàng |
| /health | Endpoint đơn giản cho load balancer | Trạng thái phục vụ theo contract đã chọn |
| /metrics | Thu thập metrics | Không nên dùng làm health probe thông thường |

Với VM sau load balancer, endpoint readiness thường phù hợp hơn liveness vì câu hỏi cần trả lời là máy có thể phục vụ request mới hay không. Nếu ứng dụng có khởi động chậm, có thể cần startup probe hoặc grace period để tránh loại máy trong lúc khởi tạo hợp lệ.

### 6.1. Readiness khác liveness

- **Liveness:** tiến trình còn hoạt động và có thể tiếp tục chạy không?
- **Readiness:** ứng dụng đã sẵn sàng nhận request chưa?
- **Startup:** ứng dụng đã hoàn thành giai đoạn khởi động chưa?

Load balancer thường cần readiness. Nếu dùng liveness làm probe, một process còn sống nhưng chưa nạp cấu hình hoặc chưa kết nối database có thể bị nhận traffic quá sớm.

### 6.2. Dependency check

Chỉ đưa dependency vào readiness nếu thiếu dependency đó thật sự khiến request không thể phục vụ. Ví dụ:

- Database chính không kết nối được và mọi request đều cần database: readiness nên báo lỗi.
- Dịch vụ analytics phụ trợ tạm thời lỗi nhưng request chính vẫn hoạt động: không nhất thiết đánh dấu toàn bộ backend unhealthy.
- Một node phụ thuộc vào cache có fallback: readiness nên phản ánh khả năng phục vụ thực tế, không chỉ trạng thái cache.

Nếu tất cả backend đồng loạt đánh dấu unhealthy do một dependency dùng chung, load balancer có thể không còn đích healthy. Cần cân nhắc cách provider xử lý khi toàn bộ target unhealthy và thiết kế probe để tránh loại toàn cụm vì một dependency không thiết yếu.

### 6.3. Hợp đồng response

Định nghĩa rõ:

- HTTP status code thành công, thường là 200.
- Timeout tối đa để hoàn thành probe.
- Body có cần kiểm tra hay chỉ status code.
- Redirect có được chấp nhận không.
- Endpoint có hỗ trợ đúng HTTP method mà probe gửi không.
- Host header, TLS và virtual host có yêu cầu gì.

Không trả 200 cho mọi path. Endpoint health phải phản ánh trạng thái có ý nghĩa; một trang lỗi generic không nên bị hiểu nhầm là healthy.

## 7. Tạo backend pool và đăng ký máy

Backend pool lưu danh sách đích mà listener có thể chuyển request tới. Tùy dịch vụ, thành viên có thể được khai báo bằng instance ID, NIC, private IP, hostname hoặc một instance group/scale set. Chọn kiểu thành viên tương thích với loại load balancer và network.

Quy trình chung:

1. Tạo backend pool/target group.
2. Chọn protocol backend (HTTP hoặc HTTPS) và port ứng dụng (ví dụ 80).
3. Chọn loại backend target phù hợp: instance, IP hoặc group.
4. Đăng ký private IP hoặc instance của app-vm-01 và app-vm-02.
5. Xác nhận hai máy xuất hiện trong danh sách backend.
6. Cấu hình listener/rule chuyển request tới pool.

### 7.1. Chọn port và protocol

Frontend và backend không nhất thiết dùng cùng port. Ví dụ client truy cập HTTPS trên 443, load balancer kết thúc TLS và chuyển HTTP tới backend port 80. Nếu yêu cầu mã hóa end-to-end, dùng HTTPS giữa load balancer và backend, quản lý certificate và xác minh tên host phù hợp.

| Chặng | Ví dụ | Ghi chú |
|---|---|---|
| Client → frontend | HTTPS 443 | TLS certificate gắn với listener |
| Load balancer → backend | HTTP 80 | TLS termination tại load balancer |
| Health probe → backend | HTTP 80, /health | Probe dùng đúng port/path đã cấu hình |

Không mở port backend ra Internet chỉ để health check hoạt động. Probe thường đi từ hạ tầng load balancer hoặc dải địa chỉ probe được provider công bố.

### 7.2. Đăng ký theo instance group hoặc autoscaling group

Nếu backend được quản lý bởi instance group, VM scale set hoặc autoscaling group, ưu tiên tích hợp pool với nhóm máy khi nền tảng hỗ trợ. Thành viên mới có thể tự động được đăng ký và thành viên bị xóa có thể được gỡ khỏi pool.

Nếu đăng ký thủ công từng IP, cần cập nhật pool khi VM thay địa chỉ hoặc bị thay thế. Quy trình này dễ tạo stale target và bỏ sót máy mới khi scale out.

### 7.3. Phân phối tải

Các thuật toán phổ biến:

- Round robin: lần lượt chọn backend theo thứ tự.
- Least connections: ưu tiên backend có ít kết nối đang mở.
- Weighted distribution: phân phối theo trọng số capacity.
- Consistent hashing: giữ request cùng key gần cùng backend, hữu ích với một số kiểu session affinity.

Session persistence/stickiness có thể giữ client ở một backend trong thời gian nhất định. Nó ảnh hưởng cách quan sát phân phối tải; một client lặp lại request không nhất thiết luân phiên giữa các node. Khi kiểm thử round robin, tắt stickiness nếu policy và ứng dụng cho phép.

## 8. Cấu hình listener và rule

Listener nhận traffic tại frontend theo protocol và port. Rule xác định pool nhận traffic. Với một ứng dụng đơn giản, dùng rule mặc định chuyển toàn bộ request tới pool-app-lab.

Kiểm tra:

- Frontend IP/DNS đã được cấp.
- Listener đang ở trạng thái enabled.
- Protocol/port frontend khớp client.
- Certificate hợp lệ nếu dùng HTTPS.
- Default action trỏ tới đúng backend pool.
- Rule host/path không vô tình chuyển request sang pool khác.
- Backend protocol/port khớp với dịch vụ đang lắng nghe.

Nếu dùng layer 7, có thể định tuyến theo host hoặc path, ví dụ /api tới pool API và /static tới pool web. Nếu dùng layer 4, load balancer thường phân phối kết nối TCP/UDP mà không đọc HTTP path.

## 9. Cấu hình health probe

Probe phải mô phỏng đủ gần điều kiện tối thiểu để backend nhận request thật, nhưng không nên quá nặng hoặc phụ thuộc vào các dịch vụ không thiết yếu.

### 9.1. Các tham số chính

| Tham số | Ý nghĩa | Cách chọn |
|---|---|---|
| Protocol | HTTP, HTTPS hoặc TCP | Chọn theo giao thức backend và cách kiểm tra |
| Port | Port probe kết nối | Dùng port ứng dụng hoặc port health riêng |
| Path | Đường dẫn HTTP | Ví dụ /health hoặc /health/ready |
| Interval | Khoảng cách giữa các probe | Cân bằng phát hiện lỗi và probe overhead |
| Timeout | Thời gian chờ một probe | Lớn hơn response bình thường, nhỏ hơn interval |
| Healthy threshold | Số lần thành công liên tiếp để phục hồi | Tránh flap khi app mới khởi động |
| Unhealthy threshold | Số lần lỗi liên tiếp để đánh dấu unhealthy | Cân bằng tốc độ loại máy và false positive |
| Success codes | HTTP status được xem là thành công | Thường chỉ 200 hoặc dải code đã định nghĩa |
| Grace period | Thời gian chờ sau khi khởi động | Dành cho app cần warm-up |

Giá trị cụ thể phụ thuộc load balancer. Không sao chép một bộ thông số cho mọi ứng dụng; hãy căn cứ thời gian khởi động, latency bình thường, SLA và hành vi của provider.

### 9.2. Ví dụ cấu hình lab

| Thuộc tính | Giá trị minh họa |
|---|---|
| Protocol | HTTP |
| Port | 80 |
| Path | /health |
| Interval | 10 giây |
| Timeout | 3 giây |
| Unhealthy threshold | 3 lần liên tiếp |
| Healthy threshold | 2 lần liên tiếp |
| Success code | 200 |

Với interval 10 giây và unhealthy threshold 3, thời gian phát hiện lỗi không phải lúc nào cũng chính xác 30 giây. Thời điểm probe tiếp theo, timeout, cách provider tính threshold và số health checker cùng chạy đều ảnh hưởng thời gian thực tế.

### 9.3. HTTP probe và TCP probe

- TCP probe chỉ xác nhận có thể thiết lập kết nối tới port; nó không chứng minh HTTP handler hoặc ứng dụng trả kết quả đúng.
- HTTP probe xác nhận endpoint phản hồi theo status/path đã cấu hình.
- HTTPS probe kiểm tra đường TLS và HTTP; certificate, SNI hoặc trust chain có thể làm probe lỗi nếu cấu hình không phù hợp.

Nếu cần xác nhận ứng dụng có thể phục vụ request, HTTP readiness probe thường có ý nghĩa hơn TCP port check. Nếu giao thức không phải HTTP, TCP probe có thể là lựa chọn phù hợp.

## 10. Cấu hình firewall và security group

Một backend có thể chạy ứng dụng bình thường nhưng vẫn bị đánh dấu unhealthy nếu probe không thể tới được port. Đây là nguyên nhân thường gặp khi chuyển từ kiểm tra localhost sang kiểm tra qua load balancer.

Thiết kế rule theo nguyên tắc chỉ cho phép nguồn cần thiết:

| Đích | Nguồn | Port | Mục đích |
|---|---|---:|---|
| Frontend load balancer | Client/network được phép | 80/443 | Request ứng dụng |
| Backend VM | Security group/subnet của load balancer hoặc probe ranges | 80 | Traffic ứng dụng và health probe |
| Backend VM | Bastion/management network | 22 | SSH quản trị nếu cần |

Nếu provider dùng security group reference, ưu tiên cho phép source là security group của load balancer. Nếu health probe dùng dải địa chỉ riêng, cần thêm đúng dải probe được provider công bố. Không mở toàn bộ port 80/443 cho mọi địa chỉ Internet.

### 10.1. Kiểm tra service đang lắng nghe

Trên mỗi backend:

~~~bash
sudo ss -lntp
sudo systemctl is-active nginx
curl -i http://127.0.0.1/health
~~~

Xác nhận Nginx lắng nghe trên interface mà load balancer có thể truy cập, không chỉ loopback. Kiểm tra firewall hệ điều hành như ufw/firewalld cùng security group ở cloud; cả hai lớp đều có thể chặn kết nối.

### 10.2. Kiểm tra từ một máy trong cùng network

Từ một VM kiểm thử có route tới backend:

~~~bash
curl -i --connect-timeout 3 http://BACKEND_PRIVATE_IP/health
~~~

Thay BACKEND_PRIVATE_IP bằng địa chỉ private thực tế. Nếu curl từ máy cùng network không kết nối được, xử lý route/firewall/service trước khi điều tra cấu hình load balancer.

### 10.3. Health probe có thể có nguồn riêng

Một số nền tảng gửi probe từ node/instance của load balancer, một số dùng dải IP probe hoặc service tag riêng. Đừng giả định source IP của probe giống source IP request client. Kiểm tra tài liệu provider và log firewall để xác định nguồn thực tế.

## 11. Gắn backend pool vào listener

Sau khi backend pool và probe được tạo:

1. Mở cấu hình listener của load balancer.
2. Chọn listener HTTP/HTTPS mà client sẽ truy cập.
3. Đặt default action hoặc routing rule chuyển tới pool-app-lab.
4. Xác nhận backend protocol/port là HTTP:80 trong ví dụ.
5. Lưu cấu hình và chờ provider áp dụng.
6. Mở trang backend health/target health của pool.
7. Xác nhận app-vm-01 và app-vm-02 lần lượt chuyển sang healthy.

Nếu pool không có backend healthy, một số load balancer sẽ trả lỗi gateway/service unavailable; một số có thể có behavior fail-open hoặc vẫn thử gửi tới target unhealthy tùy sản phẩm và cấu hình. Hãy kiểm tra behavior thực tế, không coi việc thấy request tới backend unhealthy là bằng chứng probe không hoạt động.

### 11.1. Trạng thái thường gặp

| Trạng thái | Ý nghĩa thường gặp | Hành động |
|---|---|---|
| Initial/Unknown | Chưa đủ lần probe hoặc chưa có kết quả | Chờ probe và xem event |
| Healthy | Đạt điều kiện thành công | Có thể nhận traffic |
| Unhealthy | Probe thất bại vượt threshold | Kiểm tra reason, port, path, app và firewall |
| Draining | Đang kết thúc kết nối hiện hữu | Chờ connection drain hoàn tất |
| Unused/Not in service | Chưa được gắn listener/rule hoặc chưa active | Kiểm tra liên kết pool-listener |

Tên và ý nghĩa trạng thái chính xác khác nhau giữa các provider.

## 12. Kiểm thử phân phối tải qua frontend

Chỉ bắt đầu khi cả hai backend đã healthy. Từ client có đường đi tới frontend:

~~~bash
curl -i http://LOAD_BALANCER_DNS_OR_IP/
~~~

Lặp nhiều request để quan sát backend được chọn:

~~~bash
for i in {1..20}; do
  curl -s http://LOAD_BALANCER_DNS_OR_IP/
done
~~~

Thay LOAD_BALANCER_DNS_OR_IP bằng DNS hoặc IP frontend thực tế. Với round robin và không bật session stickiness, kết quả thường cho thấy cả app-vm-01 và app-vm-02. Không yêu cầu số lần xuất hiện bằng nhau tuyệt đối vì connection reuse, thuật toán, health state, weight và lưu lượng đồng thời có thể làm phân phối lệch.

### 12.1. Kiểm tra response và log

- Response client phải là HTTP 200.
- Body phải thể hiện backend xử lý request.
- Access log trên cả hai máy phải có request khi thuật toán phân phối cho phép.
- Health dashboard phải tiếp tục hiển thị cả hai máy healthy.
- Không có spike 5xx hoặc timeout bất thường.

Nếu chỉ thấy một backend, kiểm tra pool membership, weight, stickiness, thuật toán, listener rule và health state trước khi kết luận load balancer không phân phối tải.

### 12.2. Kiểm thử nhiều kết nối

HTTP keep-alive có thể giữ nhiều request trên cùng một kết nối backend. Để quan sát lựa chọn backend dễ hơn, mở nhiều kết nối riêng hoặc dùng client không tái sử dụng kết nối khi thử nghiệm. Không dùng một lần curl duy nhất để đánh giá thuật toán.

## 13. Kiểm thử backend unhealthy có kiểm soát

Mục tiêu là chứng minh load balancer nhận biết một backend không còn sẵn sàng và ngừng gửi request mới tới máy đó. Chỉ thực hiện trong môi trường lab hoặc cửa sổ kiểm thử đã được phê duyệt.

### 13.1. Làm hỏng health endpoint của backend thứ nhất

Trên app-vm-01:

~~~bash
sudo mv /var/www/html/health /var/www/html/health.disabled
curl -i http://127.0.0.1/health
~~~

Lệnh curl trực tiếp phải nhận 404. Trang chủ vẫn có thể trả 200; điều này giúp minh họa rằng application page và readiness endpoint có thể có kết quả khác nhau.

Chờ đủ số lần probe lỗi theo interval, timeout và unhealthy threshold đã cấu hình. Theo dõi backend health dashboard hoặc event để xác nhận app-vm-01 chuyển sang unhealthy.

### 13.2. Xác nhận traffic tránh backend lỗi

Từ client, gửi nhiều request tới frontend:

~~~bash
for i in {1..20}; do
  curl -s http://LOAD_BALANCER_DNS_OR_IP/
done
~~~

Trong cấu hình thông thường, request mới sẽ chỉ được gửi tới app-vm-02 khi app-vm-01 bị đánh dấu unhealthy. Kiểm tra log cả hai máy và trạng thái pool để xác nhận.

### 13.3. Khôi phục backend

Trên app-vm-01:

~~~bash
sudo mv /var/www/html/health.disabled /var/www/html/health
curl -i http://127.0.0.1/health
~~~

Chờ số lần probe thành công liên tiếp theo healthy threshold. Xác nhận app-vm-01 trở lại healthy rồi gửi request qua frontend để kiểm tra nó được nhận traffic trở lại.

### 13.4. Kiểm thử lỗi process

Có thể kiểm thử bằng cách dừng Nginx trên một backend:

~~~bash
sudo systemctl stop nginx
~~~

Khi hoàn tất, khởi động lại:

~~~bash
sudo systemctl start nginx
sudo systemctl is-active nginx
~~~

Kiểm thử này gây gián đoạn request thực trên backend đó. Không chạy trên production nếu chưa có maintenance window và đủ capacity ở các backend còn lại.

## 14. Kiểm thử ngưỡng và thời gian phát hiện lỗi

Health check là phép đo theo chu kỳ, không phải phát hiện tức thời. Cần đo thời gian từ lúc endpoint bắt đầu lỗi đến lúc pool chuyển unhealthy, và từ lúc endpoint phục hồi đến lúc pool chuyển healthy.

Ghi nhận:

- Thời điểm bắt đầu lỗi.
- Timestamp của từng probe nếu nền tảng cung cấp.
- Thời điểm trạng thái chuyển unhealthy.
- Số request client nhận 5xx/timeout trong giai đoạn chuyển trạng thái.
- Thời điểm khôi phục endpoint.
- Thời điểm backend chuyển healthy.

### 14.1. Tác động của interval, timeout và threshold

Interval ngắn giúp phát hiện nhanh hơn nhưng tạo nhiều probe hơn. Timeout quá ngắn có thể đánh dấu nhầm backend chậm là unhealthy; timeout quá dài kéo dài phát hiện lỗi. Unhealthy threshold thấp phản ứng nhanh nhưng dễ false positive; threshold cao ổn định hơn nhưng chậm loại backend lỗi.

Ví dụ, với interval 10 giây, timeout 3 giây và threshold 3, thời gian phát hiện có thể nằm trong khoảng vài chu kỳ probe cộng thời gian timeout, tùy thời điểm lỗi xuất hiện so với probe kế tiếp và cách provider tính lần thất bại.

### 14.2. Tránh health flapping

Health flapping là trạng thái backend liên tục chuyển healthy/unhealthy. Nguyên nhân có thể là CPU quá tải, GC pause, dependency chập chờn, probe timeout quá thấp hoặc endpoint phụ thuộc dịch vụ không ổn định.

Để giảm flapping:

- Dùng threshold đủ lớn để lọc lỗi thoáng qua.
- Đặt timeout dựa trên latency bình thường và p99 của endpoint.
- Giữ endpoint health nhẹ và ít phụ thuộc.
- Tách readiness khỏi liveness.
- Theo dõi CPU, memory, connection pool và dependency latency.
- Không tăng interval/threshold chỉ để che giấu lỗi ứng dụng kéo dài.

## 15. Connection draining và deregistration

Khi cần cập nhật hoặc dừng một backend, hãy ngừng gửi kết nối mới tới máy đó và cho các kết nối đang chạy đủ thời gian hoàn tất. Cơ chế này thường được gọi là connection draining, deregistration delay hoặc graceful removal.

Quy trình:

1. Đưa backend vào trạng thái draining hoặc deregister khỏi pool.
2. Load balancer ngừng chọn backend cho request/kết nối mới theo behavior của dịch vụ.
3. Kết nối hiện hữu được phép hoàn thành trong khoảng drain timeout.
4. Theo dõi active connections và request đang xử lý.
5. Sau khi drain hoàn tất, dừng service hoặc thay thế VM.
6. Đăng ký backend mới hoặc đưa backend đã cập nhật trở lại pool.

### 15.1. Chọn drain timeout

Drain timeout phải phù hợp với thời gian request dài nhất được hỗ trợ, thời gian upload/download, WebSocket hoặc streaming. Timeout quá ngắn có thể ngắt request; quá dài làm rollout chậm và giữ tài nguyên lâu.

Nếu ứng dụng có request kéo dài không giới hạn, cần giới hạn thời gian request hoặc có cơ chế client reconnect. WebSocket/streaming cần kiểm thử riêng vì hành vi draining khác request HTTP ngắn.

### 15.2. Không dùng health failure thay cho draining

Dừng process đột ngột làm health probe thất bại nhưng có thể cắt kết nối đang chạy. Draining là thao tác chủ động để ngừng nhận kết nối mới trong khi cho phép kết nối hiện tại kết thúc.

## 16. Rolling deployment và tích hợp autoscaling

Khi cập nhật phiên bản ứng dụng, không nên cập nhật đồng thời toàn bộ backend nếu cần duy trì availability.

Một rollout đơn giản:

1. Tạo hoặc cập nhật một backend mới.
2. Chờ service khởi động và readiness endpoint trả thành công.
3. Đăng ký backend mới vào pool.
4. Chờ backend healthy.
5. Chuyển một phần traffic hoặc đưa backend vào pool theo policy.
6. Drain và gỡ backend cũ.
7. Lặp lại với các backend còn lại.
8. Kiểm tra error rate, latency và health state sau rollout.

~~~mermaid
flowchart TD
    A["Create or update one backend"] --> B["Start application"]
    B --> C["Local readiness passes"]
    C --> D["Register in backend pool"]
    D --> E["Load balancer marks healthy"]
    E --> F["Serve traffic / observe"]
    F --> G["Drain old backend"]
    G --> H["Deregister and replace"]
    H --> I["Repeat for next backend"]
~~~

### 16.1. Autoscaling group

Khi backend được quản lý bởi autoscaling group hoặc VM scale set:

- Instance mới chỉ nên nhận traffic sau khi bootstrap hoàn tất và readiness đạt.
- Instance bị scale-in nên được drain trước khi terminate.
- Health check của load balancer có thể được tích hợp với health state của autoscaling group.
- Cần phân biệt EC2/VM instance health với application health.
- Cấu hình grace period để instance có đủ thời gian khởi động.

Nếu autoscaling coi một probe lỗi tạm thời là instance unhealthy và tự động thay máy, có thể tạo vòng lặp terminate/recreate. Kiểm tra health check type, grace period và lifecycle hook của nền tảng.

### 16.2. Không scale chỉ theo health state

Health check cho biết backend có phục vụ được hay không; nó không trực tiếp đo nhu cầu tải. Autoscaling thường dựa trên CPU, request count, queue depth, latency hoặc metric tùy ứng dụng. Kết hợp health state để tránh đưa máy lỗi vào pool, và dùng capacity metrics để quyết định số lượng backend.

## 17. Bảo mật health check và backend traffic

Health endpoint cần đủ thông tin để kiểm tra nhưng không nên trở thành nguồn rò rỉ cấu hình hoặc dependency nội bộ.

Thực hành:

- Chỉ expose endpoint probe trong network cần thiết.
- Không trả credential, connection string, secret hoặc stack trace.
- Không cho phép endpoint thay đổi trạng thái hệ thống.
- Giới hạn phương thức HTTP cần thiết, thường là GET hoặc HEAD tùy probe.
- Dùng TLS cho backend traffic khi yêu cầu bảo mật end-to-end.
- Quản lý certificate, trust chain và hostname validation.
- Cho phép đúng source của load balancer/probe trong firewall.
- Bảo vệ trang quản trị và endpoint debug riêng biệt.
- Ghi log probe ở mức vừa đủ, tránh tạo log volume quá lớn.

### 17.1. Host header và virtual host

Một số HTTP server chọn site theo Host header. Nếu probe gửi IP hoặc hostname khác với hostname ứng dụng, server có thể trả 404/421 dù app đang hoạt động.

Kiểm tra cấu hình probe có thể đặt Host header hay không. Nếu không, dùng endpoint mặc định trên virtual host hoặc thiết kế route health không phụ thuộc hostname.

### 17.2. Authentication

Health probe thường không đăng nhập bằng credential người dùng. Không bảo vệ endpoint bằng OAuth login flow hoặc redirect tới trang đăng nhập. Thay vào đó, giới hạn network source và chỉ trả trạng thái tối thiểu. Nếu nền tảng hỗ trợ custom header hoặc authenticated probe, quản lý secret theo cơ chế chuyên dụng và rotation.

## 18. Metrics và quan sát vận hành

Health state cho biết backend đang được coi là healthy hay unhealthy. Để hiểu nguyên nhân và ảnh hưởng, cần kết hợp metrics của load balancer, backend và ứng dụng.

| Lớp | Chỉ số nên theo dõi |
|---|---|
| Load balancer | Healthy host count, unhealthy host count, request count, 4xx/5xx, target response time |
| Backend | CPU, memory, disk, network, active connections, process status |
| Application | Request rate, error rate, latency p50/p95/p99, queue depth |
| Dependency | Database connection/errors, cache latency, external API failures |
| Deployment | Instance launch time, bootstrap duration, drain duration, rollout status |

### 18.1. Cảnh báo

Thiết lập alert khi:

- Healthy backend count thấp hơn ngưỡng tối thiểu.
- Tất cả backend trong pool đều unhealthy.
- Một backend flapping nhiều lần trong khoảng ngắn.
- Target 5xx hoặc latency tăng đột biến.
- Request rate tập trung bất thường vào một backend.
- Autoscaling tạo máy liên tục nhưng không healthy.
- Drain timeout thường xuyên hết hạn.

### 18.2. Correlation

Khi điều tra một lần probe thất bại, đối chiếu timestamp giữa:

- Health check event của load balancer.
- Application access/error log.
- System journal.
- Firewall/security group flow log.
- CPU/memory/network metrics.
- Deployment hoặc configuration change.

Nếu thời điểm lỗi trùng với rollout, thay đổi firewall hoặc rotation certificate, đó là đầu mối quan trọng để khoanh vùng.

## 19. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Backend luôn unhealthy | Port/path sai, service không chạy, firewall chặn | Curl localhost, curl private IP, xem probe reason và firewall log |
| Local health trả 200 nhưng LB báo unhealthy | Route, security group, probe source, Host header hoặc TLS | Kiểm tra từ cùng network, flow log, probe configuration |
| Backend healthy nhưng client nhận 502/503 | App lỗi ở route thật, backend protocol sai, pool/rule sai | Gọi path ứng dụng trực tiếp, xem target response và listener rule |
| Chỉ một backend nhận traffic | Backend khác unhealthy, stickiness, weight hoặc connection reuse | Xem target state, thuật toán và session affinity |
| Backend liên tục flapping | Timeout thấp, tải cao, dependency chập chờn | Đối chiếu p99 latency, CPU, dependency và threshold |
| Sau deploy không có backend healthy | Bootstrap chậm, health path chưa sẵn sàng, grace period thiếu | Xem startup log, readiness và lifecycle event |
| Backend không quay lại healthy | Endpoint chưa phục hồi, cache trạng thái, probe sai hoặc threshold chưa đủ | Curl trực tiếp, xem probe history và chờ healthy threshold |
| Scale-in gây mất request | Không drain hoặc drain timeout quá ngắn | Kiểm tra deregistration lifecycle và request duration |

### 19.1. Trình tự điều tra

Đi từ thấp lên cao để tránh thay đổi nhiều lớp cùng lúc:

1. Process/service có chạy không?
2. Port có lắng nghe trên interface đúng không?
3. Endpoint có trả status code đúng trên localhost không?
4. Endpoint có truy cập được từ một VM cùng network không?
5. Firewall/security group có cho phép nguồn probe không?
6. Probe protocol/port/path/Host header có đúng không?
7. Backend có được đăng ký vào đúng pool không?
8. Pool có được gắn vào listener/rule không?
9. Client có truy cập đúng frontend không?

Không tăng threshold hoặc chuyển probe sang TCP chỉ để làm dashboard xanh nếu nguyên nhân gốc là ứng dụng không thể phục vụ request.

## 20. Ánh xạ sang các nền tảng cloud

Các nền tảng dùng tên gọi và khả năng khác nhau. Bảng dưới đây giúp tìm đúng khái niệm tương ứng; khi triển khai, cần kiểm tra tính năng và giới hạn của dịch vụ đang sử dụng.

| Khái niệm | AWS | Microsoft Azure | Google Cloud |
|---|---|---|---|
| Layer 7 load balancer | Application Load Balancer | Application Gateway | Application Load Balancer |
| Layer 4 load balancer | Network Load Balancer | Azure Load Balancer | Network Load Balancer |
| Backend pool | Target group | Backend pool | Backend service / instance group |
| Backend membership | EC2 instance, IP hoặc target type phù hợp | VM/NIC/IP tùy SKU và cấu hình | Instance group hoặc NEG |
| Health check | Target group health check | Probe | Health check |
| Listener/rule | Listener và listener rule | Listener và routing rule | Forwarding rule, target proxy, URL map |
| Scale integration | Auto Scaling group | Virtual Machine Scale Sets | Managed instance group |

Không phải mọi load balancer layer 4 đều kiểm tra HTTP path. Ví dụ, một Network Load Balancer có thể dùng TCP health check thay vì HTTP readiness path tùy cấu hình target group. Chọn loại dịch vụ theo yêu cầu protocol, routing, TLS, source IP preservation và khả năng health check.

### 20.1. AWS Application Load Balancer

Một cấu hình phổ biến gồm ALB, listener HTTP/HTTPS, target group kiểu instance hoặc IP và health check HTTP tới path /health. EC2 instance được đăng ký trực tiếp hoặc tích hợp với Auto Scaling group.

Khi kiểm tra, xem target health reason code và bảo đảm security group của EC2 cho phép traffic từ security group của ALB tới port ứng dụng. Nếu bật deregistration delay, kiểm thử thời gian drain trước khi terminate instance.

### 20.2. Azure Application Gateway hoặc Load Balancer

Application Gateway layer 7 dùng backend pool, listener, routing rule và health probe HTTP/HTTPS. Azure Load Balancer layer 4 dùng backend pool và health probe theo protocol được hỗ trợ như TCP, HTTP hoặc HTTPS tùy SKU/configuration.

Network Security Group cần cho phép traffic từ Application Gateway/health probe service tag theo hướng dẫn của dịch vụ. Kiểm tra probe status, backend health và effective routes.

### 20.3. Google Cloud Load Balancing

Google Cloud Load Balancing dùng backend service và health check, với backend có thể là managed instance group hoặc network endpoint group tùy loại load balancer. Firewall rule phải cho phép dải nguồn health check và proxy-only subnet nếu kiến trúc yêu cầu.

Kiểm tra trạng thái backend service, health check và firewall rule. Với một số loại proxy load balancer, traffic tới backend có thể đi từ proxy-only subnet; đừng chỉ cho phép dải health check mà quên dải proxy traffic.

## 21. Biên bản kiểm thử lab

Ghi lại cấu hình và kết quả để lần triển khai sau có thể so sánh:

| Trường | Giá trị cần ghi |
|---|---|
| Environment | Account/project/subscription và environment |
| Load balancer | Resource ID, loại dịch vụ, frontend DNS/IP |
| Listener | Protocol, port, certificate và routing rule |
| Backend pool | Tên, protocol, port và target type |
| Backend nodes | Instance ID, private IP, zone và machine type |
| Health check | Protocol, port, path, interval, timeout, thresholds |
| Firewall | Security group/NSG/firewall rule và probe source |
| Healthy test | Timestamp, backend state và client response |
| Failure test | Loại lỗi, thời điểm tạo lỗi, thời điểm unhealthy |
| Recovery test | Thời điểm khôi phục, thời điểm healthy |
| Drain test | Drain timeout, active connections và kết quả |
| Evidence | Screenshot/dashboard, log, request ID và metrics |

### 21.1. Ma trận test đề xuất

| Test | Thao tác | Kết quả mong đợi |
|---|---|---|
| T1 - Baseline | Hai backend chạy và health endpoint trả 200 | Cả hai healthy |
| T2 - Traffic | Gửi nhiều request qua frontend | Request được phân phối tới backend healthy |
| T3 - Probe failure | Làm /health trên VM1 trả 404 | VM1 chuyển unhealthy sau threshold |
| T4 - Failover | Tiếp tục gửi request khi VM1 unhealthy | VM2 tiếp tục phục vụ request mới |
| T5 - Recovery | Khôi phục /health trên VM1 | VM1 trở lại healthy |
| T6 - Process stop | Dừng service trên VM1 | Probe thất bại và VM1 bị loại theo threshold |
| T7 - Draining | Deregister VM2 khi đang có request | Request hiện tại được xử lý theo drain policy |
| T8 - Rollout | Đưa backend mới vào pool rồi gỡ backend cũ | Luôn còn đủ backend healthy theo capacity plan |

Với mỗi test, ghi pass/fail và evidence. Nếu kết quả khác mong đợi, lưu probe reason và timestamp trước khi thay đổi cấu hình.

## 22. Những lỗi thường gặp khi đưa máy vào sau load balancer

- Backend chỉ lắng nghe trên 127.0.0.1 nên load balancer không thể kết nối.
- Security group cho phép client nhưng không cho phép source của load balancer/probe.
- Probe dùng sai port hoặc path.
- Endpoint trả 301/302, 401, 403 hoặc 404 trong khi success code chỉ chấp nhận 200.
- Host header không khớp virtual host.
- HTTPS probe thất bại do certificate, SNI hoặc trust chain.
- Health endpoint phụ thuộc quá nhiều dịch vụ và làm cả pool unhealthy khi một dependency phụ lỗi.
- Grace period ngắn hơn thời gian bootstrap thực tế.
- Session stickiness khiến thử nghiệm phân phối tải bị hiểu nhầm.
- Backend pool chưa gắn đúng listener/rule.
- VM bị terminate trước khi connection draining hoàn tất.
- Autoscaling group không đồng bộ membership với backend pool.
- Chỉ nhìn trạng thái VM running mà không kiểm tra application readiness.
- Tăng threshold để che giấu ứng dụng chậm thay vì xử lý bottleneck.

## 23. Checklist hoàn thành lab

Trước khi kết thúc, xác nhận:

- [ ] Có ít nhất hai backend chạy cùng phiên bản ứng dụng.
- [ ] Mỗi backend trả HTTP 200 cho health endpoint.
- [ ] Ứng dụng lắng nghe trên interface/port mà load balancer có thể truy cập.
- [ ] Backend pool chứa đúng instance/IP và đúng port.
- [ ] Listener/rule trỏ tới backend pool chính xác.
- [ ] Firewall chỉ cho phép nguồn cần thiết, gồm cả probe.
- [ ] Cả hai backend được load balancer đánh dấu healthy.
- [ ] Client truy cập frontend và nhận response thành công.
- [ ] Đã quan sát request tới nhiều backend.
- [ ] Đã tạo lỗi probe có kiểm soát và xác nhận backend unhealthy.
- [ ] Backend còn khỏe tiếp tục phục vụ request mới.
- [ ] Đã khôi phục backend và xác nhận nó trở lại healthy.
- [ ] Đã kiểm thử draining trước khi dừng hoặc thay backend.
- [ ] Đã lưu cấu hình, timestamp, log và evidence.
- [ ] Đã kiểm tra không để lại rule firewall hoặc resource lab ngoài ý muốn.

## 24. Dọn dẹp tài nguyên lab

Sau khi lưu evidence:

1. Gỡ hoặc tắt listener/frontend nếu không còn sử dụng.
2. Deregister backend khỏi pool theo quy trình draining.
3. Dừng và xóa VM lab nếu không cần giữ lại.
4. Xóa target group/backend pool, health check và load balancer khi không còn phụ thuộc.
5. Xóa security rule tạm thời và địa chỉ IP public không cần thiết.
6. Kiểm tra disk, snapshot, log và IP còn tính phí.
7. Xác nhận không xóa nhầm resource dùng chung hoặc resource của workload khác.

Nếu lab dùng môi trường dùng chung, chỉ xóa resource có owner/tag lab đã xác nhận. Không xóa network, security group hoặc image dùng chung chỉ vì được tạo trong cùng buổi thực hành.

## 25. Ghi nhớ

Đưa nhóm máy sau load balancer gồm chuẩn bị backend đồng nhất, tạo backend pool, đăng ký VM/instance, cấu hình listener/rule và cho phép đúng network path. Health check phải kiểm tra khả năng phục vụ thực tế qua readiness endpoint, với protocol, port, path, timeout, interval và threshold phù hợp.

Kiểm thử không dừng ở trạng thái healthy. Hãy tạo lỗi có kiểm soát, xác nhận backend unhealthy ngừng nhận request mới, quan sát backend còn khỏe tiếp tục phục vụ, rồi khôi phục và kiểm tra máy quay lại pool. Khi bảo trì, dùng draining để bảo vệ kết nối hiện hữu. Kết hợp health state với metrics, log và inventory để phát hiện lỗi, tránh false positive và vận hành rolling deployment an toàn.
