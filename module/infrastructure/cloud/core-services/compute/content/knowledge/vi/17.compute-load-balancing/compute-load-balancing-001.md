# Cân bằng tải lớp 4 và lớp 7 cho các nhóm workload

Khi một ứng dụng chạy trên nhiều máy ảo, container hoặc nhóm compute, hệ thống cần phân phối lưu lượng tới các instance phù hợp. Cân bằng tải (load balancing) giúp chia tải, loại node không khỏe mạnh khỏi đường phục vụ, hỗ trợ mở rộng ngang và tạo một điểm truy cập ổn định cho người dùng. Tuy nhiên, bộ cân bằng tải lớp 4 và lớp 7 xử lý lưu lượng ở các mức khác nhau, vì vậy không thể chọn chỉ dựa trên tên dịch vụ hoặc số lượng máy.

Lớp 4 (L4) hoạt động chủ yếu theo thông tin kết nối và giao thức truyền tải như TCP hoặc UDP. Lớp 7 (L7) hiểu giao thức ứng dụng như HTTP, HTTPS, WebSocket hoặc gRPC khi được hỗ trợ. L4 thường phù hợp với luồng TCP/UDP cần thông lượng cao, độ trễ thấp hoặc không phụ thuộc vào nội dung ứng dụng. L7 phù hợp khi cần định tuyến theo hostname, path, header, cookie hoặc các thuộc tính của request.

Bài học này giải thích cách hai loại cân bằng tải hoạt động, cách chọn cho các nhóm workload và cách cấu hình health check, TLS, session persistence, draining, quan sát và bảo mật. Sau bài học, bạn có thể:

- Phân biệt điểm quan sát và cách phân phối lưu lượng của L4 với L7.
- Chọn loại load balancer cho web/API, database, gRPC, WebSocket, UDP và workload xử lý nền.
- Chọn thuật toán phân phối và chính sách session phù hợp với đặc tính ứng dụng.
- Thiết kế health check, connection draining và rollout để tránh gửi traffic tới node lỗi.
- Hiểu cách TLS termination, client IP, proxy header và network policy ảnh hưởng tới kiến trúc.
- Đánh giá khả năng mở rộng, tính sẵn sàng và chi phí của một tầng cân bằng tải trên đám mây.

## 1. Load balancer nằm ở đâu trong kiến trúc compute?

Một load balancer thường đứng trước một nhóm backend. Người dùng hoặc hệ thống gọi tới một địa chỉ ổn định; load balancer chọn backend khỏe mạnh và chuyển lưu lượng tới đó. Backend có thể là VM, container, pod, service hoặc một nhóm máy được quản lý.

~~~mermaid
flowchart LR
    C["Client / người dùng"] --> E["Địa chỉ dịch vụ"]
    E --> LB["Load balancer"]
    LB --> A["Backend A"]
    LB --> B["Backend B"]
    LB --> D["Backend C"]
    A --> DB[("Database / storage dùng chung")]
    B --> DB
    D --> DB
~~~

Load balancer có thể là dịch vụ managed của nhà cung cấp cloud, proxy chạy trên VM/container hoặc thành phần trong nền tảng điều phối. Dù cách triển khai khác nhau, các trách nhiệm thường gặp gồm:

- Nhận lưu lượng tại địa chỉ và cổng được công bố.
- Chọn backend dựa trên thuật toán và trạng thái sức khỏe.
- Chuyển tiếp kết nối hoặc request tới backend.
- Theo dõi timeout, lỗi kết nối và health check.
- Áp dụng chính sách TLS, routing, logging hoặc giới hạn lưu lượng nếu sản phẩm hỗ trợ.

Load balancer không tự động làm ứng dụng có khả năng mở rộng. Nếu tất cả backend dùng chung một database đã bão hòa, thêm backend có thể làm database quá tải nhanh hơn. Cân bằng tải cần đi cùng capacity planning, autoscaling, cache, queue, database scaling và quan sát hệ thống.

## 2. Cân bằng tải lớp 4 hoạt động như thế nào?

L4 xử lý lưu lượng dựa trên thông tin tầng vận chuyển và mạng, thường gồm địa chỉ IP nguồn/đích, cổng nguồn/đích và giao thức TCP hoặc UDP. Với TCP, load balancer chọn một backend khi thiết lập kết nối rồi chuyển tiếp dữ liệu của kết nối đó tới backend đã chọn.

L4 không cần hiểu nội dung HTTP. Một kết nối TCP có thể mang nhiều HTTP request qua keep-alive; nếu L4 chỉ phân phối theo kết nối, các request trên cùng kết nối vẫn đi tới cùng backend. Điều này khác với L7 proxy có thể kết thúc HTTP connection và chọn backend cho từng request.

### Đặc điểm chính

- Xử lý ở mức kết nối hoặc luồng, không cần phân tích path, header hay nội dung ứng dụng.
- Có thể hỗ trợ TCP và UDP; phạm vi giao thức cụ thể tùy sản phẩm.
- Thường có overhead xử lý thấp và phù hợp với lưu lượng lớn.
- Có thể giữ nguyên hoặc truyền thông tin IP nguồn theo cơ chế của nền tảng.
- Phù hợp với giao thức tùy chỉnh, database proxy ở tầng TCP, game server hoặc dịch vụ không dùng HTTP.

### Các cách chuyển tiếp thường gặp

- **Proxy/connection termination:** load balancer nhận kết nối từ client và tạo một kết nối riêng tới backend. Nó quản lý hai phía của kết nối.
- **Direct server return (DSR) hoặc routing gần với pass-through:** một số giải pháp chuyển gói tới backend theo cách để backend trả lời client trực tiếp hoặc giữ đường dữ liệu ít qua proxy hơn. Mô hình này yêu cầu cấu hình mạng và địa chỉ IP đặc thù.
- **NAT-based forwarding:** thay đổi địa chỉ hoặc cổng trong gói tin để chuyển tới backend; đường trả về phải đi qua cơ chế tương ứng để duy trì trạng thái kết nối.

Không phải mọi cloud L4 load balancer đều hỗ trợ mọi chế độ. Cần kiểm tra tài liệu của sản phẩm về source IP preservation, proxy protocol, cross-zone balancing, connection limits và cách xử lý return traffic.

### Khi nào nên dùng L4?

- TCP service không phải HTTP, chẳng hạn một số dịch vụ database hoặc giao thức nội bộ.
- UDP workload như DNS, game traffic hoặc telemetry khi nền tảng hỗ trợ giao thức và yêu cầu đó.
- Dịch vụ cần thông lượng cao và không cần định tuyến theo nội dung request.
- Ứng dụng tự xử lý TLS hoặc cần TLS pass-through để backend kết thúc mã hóa.
- Luồng kết nối dài hoặc giao thức tùy chỉnh mà L7 proxy không hỗ trợ đầy đủ.

L4 không tự hiểu người dùng đang gọi API nào, request nào cần backend nào hoặc header nào biểu thị tenant. Nếu cần routing theo nội dung HTTP, hãy cân nhắc L7.

## 3. Cân bằng tải lớp 7 hoạt động như thế nào?

L7 load balancer hoạt động như một proxy hiểu giao thức ứng dụng. Với HTTP/HTTPS, nó có thể kết thúc kết nối từ client, đọc hostname, path, method, header hoặc cookie rồi quyết định backend. Khi chuyển tiếp, proxy thường tạo một kết nối khác tới backend.

Ví dụ, cùng một địa chỉ dịch vụ có thể định tuyến:

- api.example.com/orders tới nhóm xử lý đơn hàng.
- api.example.com/catalog tới nhóm danh mục.
- admin.example.com tới nhóm giao diện quản trị.
- /v2/ tới phiên bản API mới trong một giai đoạn canary.

### Khả năng thường gặp

- **Host-based routing:** chọn backend theo hostname.
- **Path-based routing:** chọn backend theo đường dẫn URL.
- **Header hoặc method routing:** chọn backend dựa trên HTTP header hoặc method nếu sản phẩm hỗ trợ.
- **Cookie/session affinity:** giữ một client hoặc phiên ở cùng backend trong một khoảng thời gian.
- **TLS termination:** giải mã TLS ở proxy để kiểm tra HTTP và áp dụng chính sách ứng dụng.
- **HTTP-aware health check:** gửi request tới một endpoint cụ thể và kiểm tra mã trạng thái hoặc nội dung phản hồi theo khả năng sản phẩm.
- **Request-level policy:** áp dụng redirect, header rewrite, giới hạn request hoặc rule bảo vệ nếu được hỗ trợ.

Khả năng cụ thể khác nhau giữa các nhà cung cấp và sản phẩm. Một số tính năng như WAF, gRPC routing, WebSocket, HTTP/3 hoặc kiểm tra nội dung phản hồi có thể là tính năng riêng hoặc cần cấu hình bổ sung.

### TLS termination và mã hóa tới backend

Khi L7 kết thúc TLS, client thiết lập TLS với load balancer. Proxy giải mã request, áp dụng routing và có thể thiết lập TLS mới tới backend. Cần quyết định rõ:

- **TLS termination tại load balancer:** đơn giản hóa quản lý chứng chỉ ở backend, nhưng dữ liệu giữa load balancer và backend cần được bảo vệ bằng mạng riêng hoặc TLS tiếp tục nếu yêu cầu bảo mật đòi hỏi.
- **TLS re-encryption:** client mã hóa tới load balancer và load balancer mã hóa lại tới backend. Cần quản lý chứng chỉ, xác minh danh tính backend và trust chain.
- **TLS pass-through:** load balancer chuyển tiếp luồng mã hóa mà không giải mã nội dung. Khi đó, nó không thể định tuyến theo path/header bên trong HTTP được mã hóa; hành vi này thường gần với cân bằng tải L4.

Tên gọi listener và tính năng TLS ở mỗi nền tảng có thể khác nhau. Hãy xác minh chính xác nơi TLS được kết thúc và nơi dữ liệu ở dạng rõ.

## 4. So sánh L4 và L7

| Tiêu chí | L4 | L7 |
|---|---|---|
| Thông tin dùng để chọn backend | IP, port, protocol, flow/connection | Host, path, method, header, cookie và ngữ cảnh ứng dụng |
| Đơn vị phân phối | Thường là kết nối hoặc flow | Có thể là request, stream hoặc phiên theo giao thức |
| Giao thức phổ biến | TCP, UDP và giao thức tầng vận chuyển được hỗ trợ | HTTP, HTTPS, WebSocket, gRPC và giao thức ứng dụng được hỗ trợ |
| Đọc nội dung HTTP | Không | Có khi proxy kết thúc/giải mã giao thức |
| TLS | Có thể pass-through hoặc kết thúc TLS tùy sản phẩm | Thường kết thúc TLS để đọc HTTP; có thể mã hóa lại tới backend |
| Định tuyến theo URL | Không | Có |
| Độ phức tạp xử lý | Thường thấp hơn | Cao hơn do phân tích giao thức và áp dụng policy |
| Khả năng quan sát | Kết nối, byte, flow, reset và timeout | Có thể có request, status code, latency, host/path và header đã chọn |
| Tình huống phù hợp | TCP/UDP, giao thức tùy chỉnh, luồng lớn | Web, API, định tuyến nhiều dịch vụ và chính sách HTTP |

Không nên kết luận L4 luôn nhanh hơn trong mọi trường hợp hoặc L7 luôn có độ trễ cao không chấp nhận được. Hiệu năng thực tế phụ thuộc kích thước instance, số kết nối, TLS, tính năng bật, kích thước request, thuật toán và tải. Hãy benchmark trên traffic đại diện.

## 5. Chọn loại cân bằng tải cho từng nhóm workload

| Nhóm workload | Lựa chọn thường phù hợp | Lý do và điểm cần kiểm tra |
|---|---|---|
| Website và REST API | L7 | Cần host/path routing, TLS termination, HTTP health check và request metrics |
| Nhiều microservice HTTP | L7 hoặc kết hợp L7 với service mesh | Có thể route theo host/path/header; tránh tạo quá nhiều hop proxy |
| Database dùng TCP | L4 hoặc database-aware proxy chuyên dụng | Cần giữ kết nối TCP; kiểm tra giới hạn connection, timeout và failover |
| SSH/RDP hoặc giao thức TCP riêng | L4 hoặc access gateway chuyên dụng | Không cần phân tích HTTP; phải kiểm soát nguồn truy cập và thời gian phiên |
| DNS hoặc UDP service | L4 hỗ trợ UDP | Kiểm tra timeout, flow handling, packet size và khả năng giữ trạng thái |
| Game server | L4 hoặc giải pháp chuyên dụng | Có thể dùng UDP/TCP, session dài và yêu cầu latency thấp |
| WebSocket | L7 có hỗ trợ WebSocket hoặc L4 | L7 có thể áp dụng routing HTTP khi upgrade; cần timeout và connection draining phù hợp |
| gRPC | L7 có hỗ trợ HTTP/2/gRPC hoặc L4 | L7 cho routing theo service/method khi được hỗ trợ; L4 giữ nguyên luồng TCP |
| GPU inference API | L7 thường hữu ích; L4 có thể dùng ở tầng trước | L7 có thể route theo endpoint/model/version; cần cân nhắc request duration và stream |
| Batch worker đọc queue | Queue và worker autoscaling thường là cơ chế chính | Một load balancer HTTP không thay thế phân phối message và acknowledgement |

### Workload stateless và stateful

Với workload stateless, bất kỳ backend khỏe mạnh nào cũng có thể xử lý request tiếp theo vì trạng thái cần thiết được lưu ngoài instance hoặc mang theo request. Đây là trường hợp dễ cân bằng tải và autoscale nhất.

Với workload stateful, phiên hoặc dữ liệu có thể gắn với một backend. Có ba cách tiếp cận:

1. Đưa trạng thái ra hệ thống dùng chung như database, cache hoặc session store.
2. Dùng consistent hashing hoặc định tuyến theo khóa để cùng một nhóm dữ liệu thường đi tới cùng backend.
3. Dùng session affinity khi ứng dụng thật sự cần gắn client với backend trong thời gian giới hạn.

Session affinity không thay thế thiết kế lưu trữ bền vững. Nếu backend bị lỗi hoặc bị scale-in, phiên có thể mất hoặc người dùng phải đăng nhập lại. Với hệ thống quan trọng, nên thiết kế khả năng phục hồi phiên thay vì phụ thuộc hoàn toàn vào sticky session.

## 6. Thuật toán phân phối backend

Load balancer có thể dùng nhiều thuật toán. Tên và hành vi cụ thể tùy sản phẩm.

### Round robin

Chọn lần lượt backend theo vòng. Phù hợp khi backend có năng lực tương đương và request có chi phí tương đối đồng đều. Nếu request có thời gian xử lý rất khác nhau hoặc backend khác cấu hình, round robin có thể làm một node bị quá tải.

### Weighted round robin

Phân phối theo trọng số. Backend lớn hơn hoặc đã được benchmark có thể nhận tỷ lệ request cao hơn. Trọng số cần dựa trên năng lực đo được và được cập nhật khi cấu hình backend thay đổi.

### Least connections

Ưu tiên backend có ít kết nối đang hoạt động hơn. Phù hợp khi kết nối có thời gian sống khác nhau, nhưng số kết nối không luôn tương đương với lượng công việc. Một kết nối idle có thể tồn tại lâu, còn một request ngắn có thể tiêu thụ nhiều CPU.

### Least outstanding requests

Với L7, một số proxy có thể chọn backend có ít request đang xử lý nhất. Cách này phù hợp hơn khi thời gian xử lý request khác nhau, nhưng cần tính tới giới hạn đồng thời và chi phí đo trạng thái.

### Hash theo client hoặc khóa

Hash địa chỉ client, cookie hoặc một khóa ứng dụng để chọn backend ổn định. Có thể hỗ trợ cache locality hoặc session affinity. Nếu dùng IP client, nhiều người dùng sau NAT có thể bị gom về cùng backend. Consistent hashing giúp giảm số ánh xạ bị thay đổi khi thêm/bớt backend, nhưng không loại bỏ nhu cầu xử lý khi node hỏng.

### Random và power of two choices

Chọn ngẫu nhiên hoặc chọn hai backend rồi lấy backend có tải thấp hơn. Một số hệ thống dùng biến thể này để tránh phải duy trì thứ tự chính xác toàn cụm. Hãy xem thuật toán thực tế của sản phẩm và đánh giá bằng benchmark.

| Thuật toán | Khi phù hợp | Rủi ro cần lưu ý |
|---|---|---|
| Round robin | Backend đồng nhất, request gần tương đương | Không phản ánh tải hiện tại |
| Weighted | Backend có năng lực khác nhau | Trọng số lỗi thời làm lệch tải |
| Least connections | Kết nối dài, số kết nối phản ánh tương đối tải | Kết nối idle có thể làm sai tín hiệu |
| Least outstanding requests | HTTP request có thời gian xử lý không đều | Cần proxy theo dõi request đang chạy |
| Hash/consistent hash | Cần affinity hoặc locality | Hot key/client có thể làm nóng một backend |

## 7. Health check: chỉ gửi traffic tới backend khỏe mạnh

Health check giúp load balancer biết backend có thể nhận traffic hay không. Cần phân biệt:

- **Liveness:** tiến trình còn sống và có thể tiếp tục chạy không?
- **Readiness:** backend đã sẵn sàng nhận request mới chưa?
- **Dependency health:** database, cache hoặc dịch vụ phụ thuộc có hoạt động không?

Health check của load balancer thường nên kiểm tra readiness ở mức đủ để xác định backend có thể phục vụ. Nếu kiểm tra mọi dependency một cách quá nhạy, sự cố tạm thời ở một dependency dùng chung có thể khiến toàn bộ backend bị loại cùng lúc. Điều đó có thể làm sự cố lớn hơn.

Một health check cần xác định:

- Giao thức và cổng kiểm tra.
- Đường dẫn HTTP nếu là L7.
- Khoảng thời gian giữa các lần kiểm tra.
- Timeout cho mỗi lần kiểm tra.
- Số lần thất bại liên tiếp trước khi đánh dấu unhealthy.
- Số lần thành công để đưa backend trở lại healthy.
- Mã trạng thái hoặc điều kiện phản hồi được chấp nhận.

Các thông số nên dựa trên thời gian khởi động và mức độ ổn định của workload. Timeout quá ngắn tạo false positive; timeout quá dài khiến backend lỗi tiếp tục nhận traffic lâu hơn.

### Health check không phải kiểm tra toàn diện

Endpoint readiness nên nhẹ, ổn định và không tạo tác động phụ. Nó không nên chạy truy vấn nặng hoặc kiểm tra hàng loạt dependency với mỗi lần probe. Các kiểm tra sâu hơn có thể được thực hiện bởi hệ thống giám sát riêng.

Với L4, health check có thể chỉ kiểm tra TCP connection tới cổng. TCP accept thành công không chứng minh ứng dụng xử lý request đúng. Nếu cần kiểm tra logic HTTP, dùng L7 health check hoặc synthetic monitoring ở tầng ứng dụng.

## 8. Session persistence, kết nối dài và draining

### Sticky session

Sticky session giúp các request từ cùng client hoặc session quay lại cùng backend. Cách thực hiện có thể dựa trên cookie do load balancer phát hành, cookie của ứng dụng hoặc hash theo thuộc tính client.

Chỉ bật sticky session khi có lý do rõ ràng. Nó có thể làm mất cân bằng tải nếu một backend nhận nhiều phiên hoạt động hơn, gây khó scale-in và giảm khả năng phân phối lại sau lỗi. Session store dùng chung thường giúp giảm phụ thuộc vào affinity.

### Kết nối dài

WebSocket, gRPC streaming, SSH và một số giao thức TCP duy trì kết nối lâu. Khi một kết nối đã được gắn với backend, load balancer thường không chuyển phần còn lại của kết nối sang backend khác nếu node đích gặp sự cố. Ứng dụng cần có cơ chế reconnect, retry có backoff và khôi phục phiên phù hợp.

Kiểm tra idle timeout, maximum connection lifetime và keepalive ở cả client, load balancer, proxy trung gian và backend. Timeout không đồng nhất có thể làm kết nối bị đóng bất ngờ.

### Connection draining và deregistration delay

Khi bảo trì hoặc scale-in, không nên xóa backend ngay khi nó còn đang xử lý request. Quy trình graceful removal thường gồm:

1. Đánh dấu backend không nhận kết nối hoặc request mới.
2. Chờ request đang chạy hoàn tất trong thời gian drain được cấu hình.
3. Cho phép ứng dụng hoàn tất công việc, flush dữ liệu và đóng kết nối.
4. Kết thúc instance hoặc container sau khi hết thời gian chờ.

Nếu workload có request kéo dài hơn drain timeout, cần quyết định có cho phép kết thúc cưỡng bức hay không và thiết kế client retry. Với queue worker, dùng cơ chế visibility timeout, acknowledgement và graceful shutdown phù hợp thay vì chỉ dựa vào HTTP connection draining.

## 9. TLS, chứng chỉ và bảo vệ lưu lượng

Với L7 HTTPS, load balancer thường quản lý chứng chỉ cho hostname được công bố. Cần theo dõi ngày hết hạn, tự động gia hạn nếu có thể và bảo đảm mọi hostname cần thiết đều có chứng chỉ phù hợp.

Khi mã hóa lại tới backend:

- Xác minh certificate của backend theo trust chain và hostname/SAN.
- Dùng phiên bản TLS và cipher suite được tổ chức chấp nhận.
- Bảo vệ private key và giới hạn quyền truy cập.
- Cân nhắc mutual TLS nếu cần xác thực hai chiều giữa proxy và backend.
- Không ghi token, cookie, Authorization header hoặc payload nhạy cảm vào log.

Với L4 TLS pass-through, backend chịu trách nhiệm kết thúc TLS và quản lý chứng chỉ. Load balancer không thể đọc nội dung mã hóa để route theo HTTP path. Nếu dùng TLS termination ở L4, hãy xác minh tính năng cụ thể; thuật ngữ listener của nhà cung cấp có thể không hoàn toàn trùng với cách phân loại theo OSI.

## 10. Bảo toàn địa chỉ IP client và proxy header

Ứng dụng có thể cần biết IP gốc của client để audit, rate limit hoặc áp dụng chính sách. Khi load balancer proxy kết nối, backend thường thấy địa chỉ của proxy thay vì client.

Một số cách truyền thông tin:

- **Source IP preservation:** backend nhận được IP nguồn gốc ở tầng mạng nếu kiến trúc hỗ trợ.
- **PROXY protocol:** proxy gửi metadata client IP/port ở phần đầu kết nối; backend phải được cấu hình để hiểu giao thức này.
- **X-Forwarded-For:** header HTTP chứa địa chỉ client và chuỗi proxy; thường dùng với L7.
- **Forwarded header:** header chuẩn hóa thông tin proxy theo cấu trúc HTTP.

Không tin cậy X-Forwarded-For từ bất kỳ client nào trên Internet. Chỉ chấp nhận header do proxy tin cậy ghi đè hoặc bổ sung, xác định rõ hop nào được tin cậy và loại bỏ header giả do client gửi. Nếu backend có thể truy cập trực tiếp từ Internet, kẻ tấn công có thể tự đặt header giả và làm sai log hoặc chính sách IP.

## 11. Cân bằng tải cho VM, container và serverless

| Nền tảng compute | Cách tích hợp thường gặp | Điểm cần quan tâm |
|---|---|---|
| VM | L4/L7 listener chuyển tới target group hoặc backend pool | Health check, instance registration, zone, drain và autoscaling |
| Container | L7 ingress/gateway hoặc L4 service tùy nền tảng | Pod readiness, endpoint discovery, rollout, service mesh và node drain |
| Kubernetes | Service, Ingress hoặc Gateway API kết hợp controller/cloud LB | Phân biệt health của node, pod và application; tránh double load balancing không cần thiết |
| Serverless | HTTP gateway hoặc managed load balancer hỗ trợ function/service target | Concurrency quota, cold start, timeout, payload limit và retry |
| Batch/queue worker | Message broker phân phối job tới consumer | Backpressure, visibility timeout, retry, dead-letter queue và autoscaling theo queue depth |

### VM và autoscaling group

Khi VM mới được tạo, hệ thống cần đăng ký nó vào backend pool và chỉ gửi traffic sau khi health check đạt. Khi scale-in, instance nên được deregister và drain trước khi bị hủy. Tích hợp giữa autoscaling và load balancer cần xử lý trường hợp VM khởi động chậm hoặc boot thất bại.

### Container và Kubernetes

Khi pod được tạo, readiness probe quyết định pod có được đưa vào endpoint phục vụ hay không. Ingress hoặc gateway có thể định tuyến HTTP tới service; Service L4 có thể phân phối TCP/UDP tới các pod. Cần hiểu rõ controller đang tạo load balancer nào và traffic đi qua bao nhiêu lớp proxy.

Nếu vừa có cloud L7 load balancer, vừa có ingress controller và service mesh, mỗi lớp thêm hop, health check, timeout và log. Kiến trúc nhiều tầng có thể hữu ích cho ranh giới bảo mật hoặc routing, nhưng cần xác định trách nhiệm của từng tầng và tránh cấu hình trùng lặp.

### Serverless

Serverless thường dùng gateway hoặc load balancer được quản lý để nhận HTTP request rồi gọi function hoặc service. Cần kiểm tra timeout, payload size, concurrency quota, cold start, retry và giới hạn request. Nếu request kéo dài hoặc stream, xác minh nền tảng có hỗ trợ giao thức và thời lượng phiên đó không.

### Worker xử lý nền

Không nên đặt một L4/L7 load balancer trước mọi loại workload. Worker xử lý batch thường lấy job từ queue. Message broker chịu trách nhiệm phân phối, acknowledgement, retry và backpressure. Autoscaling worker có thể dựa trên queue depth, age of oldest message hoặc tốc độ hoàn thành.

## 12. Thiết kế nhiều tầng L4 và L7

Có thể kết hợp L4 và L7 khi cần tách điểm vào mạng khỏi định tuyến ứng dụng:

~~~mermaid
flowchart TD
    C["Client"] --> L4["L4: TCP/UDP entry"]
    L4 --> L7["L7: HTTP gateway"]
    L7 --> API["API service"]
    L7 --> WEB["Web service"]
    L7 --> ADMIN["Admin service"]
    API --> DATA[("Shared data services")]
    WEB --> DATA
    ADMIN --> DATA
~~~

Ví dụ, L4 cung cấp địa chỉ TCP ổn định hoặc phân phối kết nối qua nhiều proxy L7; L7 thực hiện TLS termination, host/path routing và policy HTTP. Cách này có thể tăng khả năng mở rộng hoặc tạo ranh giới mạng rõ ràng, nhưng cũng thêm độ trễ và điểm cần giám sát.

Khi thiết kế nhiều tầng, hãy xác định:

- Tầng nào sở hữu public IP và tiếp nhận Internet traffic?
- Tầng nào kết thúc TLS?
- Tầng nào ghi nhận client IP và tạo proxy header?
- Health check từ tầng trước kiểm tra tầng sau bằng cách nào?
- Timeout và retry được cấu hình ra sao để tránh retry storm?
- Có bao nhiêu hop giữa client và backend?
- Khi một tầng lỗi, hệ thống còn đường phục vụ dự phòng không?

## 13. Khả năng sẵn sàng và mở rộng

Load balancer cần được triển khai có dự phòng theo kiến trúc của nhà cung cấp hoặc qua nhiều instance/zone. Cần xem xét:

- Phân phối backend qua nhiều availability zone nếu workload hỗ trợ.
- Health check độc lập cho từng backend và giám sát chính load balancer.
- Capacity giới hạn kết nối, request/giây, TLS handshake và bandwidth.
- Khả năng scale của proxy khi số kết nối hoặc lưu lượng tăng.
- Dự phòng DNS, certificate, target registration và control plane.
- Ảnh hưởng khi một zone mất kết nối hoặc một nhóm backend cùng unhealthy.

### Cross-zone load balancing

Một số nền tảng cho phép load balancer ở một zone gửi traffic tới backend ở zone khác. Cách này có thể cải thiện khả năng phân phối khi một zone thiếu backend, nhưng tăng lưu lượng liên zone, độ trễ và chi phí truyền dữ liệu. Cần so sánh phân phối đều toàn cụm với cân bằng cục bộ theo zone.

### Autoscaling và load balancing

Load balancer thường cung cấp metrics như request count, active connections, target response time hoặc unhealthy host count. Autoscaler có thể dùng các metrics này để tăng/giảm capacity. Tuy nhiên:

- Chọn metric phù hợp với loại workload; request count có thể không phản ánh chi phí xử lý nếu request có độ nặng khác nhau.
- Đặt cooldown hoặc stabilization window để tránh scale lên xuống liên tục.
- Tính thời gian khởi động, tải image, warm-up và readiness của backend mới.
- Giữ capacity dự phòng trong lúc node cũ drain.
- Bảo đảm dependency phía sau như database và queue cũng chịu được tải tăng.

Load balancer phân phối tải hiện có; autoscaler thay đổi số lượng tài nguyên. Hai cơ chế bổ trợ nhau nhưng có trách nhiệm khác nhau.

## 14. Quan sát và xử lý sự cố load balancer

Theo dõi cả metrics của load balancer và backend:

| Chỉ số | Ý nghĩa |
|---|---|
| Request/connection count | Lưu lượng được nhận và phân phối |
| Active connections | Số kết nối hiện tại; hữu ích với TCP/WebSocket |
| Healthy/unhealthy targets | Số backend đủ điều kiện nhận traffic |
| Backend response time | Thời gian backend phản hồi theo định nghĩa sản phẩm |
| 4xx/5xx hoặc reset | Lỗi client, lỗi backend hoặc proxy |
| Rejected/queued connections | Hết capacity hoặc giới hạn kết nối |
| TLS handshake failures | Lỗi chứng chỉ, protocol hoặc tài nguyên TLS |
| Bytes in/out | Băng thông và xu hướng truyền dữ liệu |
| Distribution per target | Phát hiện backend nhận tải lệch |

Khi có sự cố, đi theo thứ tự:

1. Xác định phạm vi: toàn dịch vụ, một vùng, một hostname/path hay một backend.
2. Kiểm tra listener, rule, certificate và trạng thái load balancer.
3. Kiểm tra số backend healthy, health check result và target registration.
4. Kiểm tra log access/error, timeout, reset và mã trạng thái.
5. Kiểm tra backend trực tiếp trong mạng quản trị để phân biệt lỗi proxy với lỗi ứng dụng.
6. Kiểm tra dependency, capacity, autoscaling và thay đổi gần nhất.
7. Khôi phục bằng cách sửa rule, đưa backend khỏe mạnh vào pool hoặc rollback thay đổi đã xác định.

Không loại backend khỏi pool chỉ vì một metric tạm thời tăng nếu chưa hiểu nguyên nhân. Health check quá nhạy có thể tạo hiện tượng tất cả backend bị loại cùng lúc; cần có cơ chế fail-open/fail-closed phù hợp với sản phẩm và mức độ rủi ro của dịch vụ.

## 15. Bảo mật cho tầng cân bằng tải

- Chỉ công bố listener và protocol cần thiết.
- Giới hạn nguồn truy cập quản trị; không dùng listener public cho cổng quản trị nội bộ.
- Dùng security group/firewall giữa load balancer và backend để chỉ chấp nhận traffic từ nguồn proxy hợp lệ.
- Bảo vệ backend khỏi truy cập trực tiếp nếu kiến trúc yêu cầu mọi request phải đi qua L7 policy hoặc WAF.
- Quản lý TLS certificate, private key, rotation và quyền truy cập.
- Chỉ tin proxy header từ proxy được xác thực hoặc dải mạng đáng tin cậy.
- Không ghi thông tin xác thực, token, cookie hoặc payload nhạy cảm vào access log.
- Dùng rate limit, WAF hoặc DDoS protection khi phù hợp và theo dõi false positive.
- Ghi nhận thay đổi listener, routing rule, target group và certificate.

L7 có thể hỗ trợ WAF hoặc kiểm tra request, nhưng không thay thế bảo mật ở ứng dụng, danh tính, phân quyền và network segmentation. L4 cũng cần bảo vệ khỏi flood, connection exhaustion và nguồn traffic không được phép.

## 16. Ví dụ: phân phối traffic cho hệ thống đặt hàng

Một hệ thống đặt hàng có ba nhóm workload:

- Website và REST API nhận HTTPS từ người dùng.
- Một dịch vụ TCP nội bộ nhận kết nối từ hệ thống kho cũ.
- Worker xử lý tác vụ gửi email và cập nhật trạng thái từ queue.

Thiết kế phù hợp có thể gồm:

1. **L7 public load balancer** nhận HTTPS, quản lý chứng chỉ, route /api/orders tới API service và / tới web service.
2. **L4 internal load balancer** phân phối kết nối TCP của hệ thống kho tới nhóm backend tương ứng trong private network.
3. **Message queue** phân phối job tới email/status workers; autoscaler điều chỉnh số worker theo queue depth và tuổi message cũ nhất.

Với API, nhóm dùng health endpoint readiness, theo dõi p95 latency và 5xx, drain backend trước khi deploy. Với dịch vụ TCP nội bộ, nhóm theo dõi active connections, reset và timeout; client cần reconnect khi backend bị thay thế. Với worker, nhóm dùng acknowledgement và retry có backoff để không mất job khi worker dừng.

Thiết kế này tránh ép mọi loại workload qua cùng một cơ chế. HTTP cần routing theo request, TCP nội bộ cần chuyển tiếp kết nối, còn job nền cần phân phối message có trạng thái.

## 17. Checklist trước khi triển khai load balancer

- [ ] Đã mô tả protocol, loại request, thời gian sống kết nối và tải dự kiến.
- [ ] Đã chọn L4, L7 hoặc kết hợp dựa trên nhu cầu routing và xử lý giao thức.
- [ ] Đã xác định listener, hostname, port, protocol và backend pool.
- [ ] Thuật toán phân phối phù hợp với năng lực và tính đồng nhất của backend.
- [ ] Health check phản ánh readiness và không quá nhạy với dependency dùng chung.
- [ ] Có chính sách session affinity rõ ràng và có lý do sử dụng.
- [ ] Timeout, keepalive, maximum connection lifetime và draining phù hợp.
- [ ] TLS termination/pass-through/re-encryption được xác định rõ.
- [ ] Client IP và proxy header được xử lý an toàn.
- [ ] Security group, firewall và route chỉ cho phép luồng cần thiết.
- [ ] Backend có capacity và trải trên các zone phù hợp.
- [ ] Autoscaling không tạo dao động hoặc làm quá tải dependency.
- [ ] Có metrics, logs, alert và runbook xử lý lỗi.
- [ ] Đã thử nghiệm failover, backend unhealthy, deploy và scale-in.

## 18. Bài tập vận dụng

Một nền tảng compute có ba dịch vụ:

1. API HTTP phục vụ khách hàng, cần route theo hostname và path.
2. Dịch vụ truyền dữ liệu TCP nội bộ, mỗi kết nối có thể kéo dài 45 phút.
3. Worker xử lý job bất đồng bộ, số lượng job tăng mạnh theo giờ.

Hãy đề xuất cơ chế phân phối cho từng dịch vụ và trả lời:

- Dịch vụ nào nên dùng L7, dịch vụ nào phù hợp với L4?
- Vì sao queue phù hợp hơn load balancer HTTP cho worker xử lý job?
- Cần cấu hình health check và connection draining thế nào cho dịch vụ TCP dài?
- API cần xử lý TLS, client IP và readiness ra sao?
- Những metrics nào giúp phát hiện một backend bị quá tải hoặc phân phối lệch?

Gợi ý: dùng L7 cho API để route theo host/path và kiểm tra readiness HTTP; dùng L4 cho TCP service nếu giao thức không cần phân tích nội dung, đồng thời thiết kế reconnect và drain dài phù hợp. Dùng message queue cùng acknowledgement/retry cho worker. Theo dõi request/connection count, active connections, healthy targets, p95 latency, error/reset, queue depth và tuổi job cũ nhất.

## Kết luận

L4 phân phối lưu lượng chủ yếu theo kết nối và giao thức vận chuyển, phù hợp với TCP/UDP và các workload không cần đọc nội dung ứng dụng. L7 hiểu HTTP hoặc giao thức ứng dụng được hỗ trợ, cho phép route theo hostname, path, header và áp dụng chính sách ở mức request. Việc chọn đúng tầng cần dựa trên giao thức, trạng thái workload, thời gian sống kết nối, yêu cầu TLS, khả năng quan sát và cách mở rộng. Health check, draining, bảo mật mạng và thiết kế phục hồi của client quyết định load balancing có giúp dịch vụ duy trì tính sẵn sàng trong thực tế hay không.
