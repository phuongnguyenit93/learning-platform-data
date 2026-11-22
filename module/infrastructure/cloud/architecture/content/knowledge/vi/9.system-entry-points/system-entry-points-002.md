# Cân bằng tải lớp vận chuyển và lớp ứng dụng

Một ứng dụng triển khai trên đám mây thường có nhiều bản sao API, web server hoặc dịch vụ TCP/UDP. Người dùng chỉ biết một tên miền, nhưng hệ thống phải chọn đúng máy phục vụ, ngừng chuyển lưu lượng đến máy lỗi và mở rộng khi tải tăng. **Load balancer (bộ cân bằng tải)** là thành phần tại điểm vào giúp phân phối lưu lượng giữa các đích phù hợp với chính sách và tình trạng hoạt động.

Không phải bộ cân bằng tải nào cũng xử lý lưu lượng theo cùng một cách. Hai nhóm thường được nhắc đến là **cân bằng tải lớp vận chuyển (Layer 4, L4)** và **cân bằng tải lớp ứng dụng (Layer 7, L7)**. Chúng khác nhau chủ yếu ở **thông tin có thể quan sát và sử dụng để ra quyết định định tuyến**, từ đó kéo theo đánh đổi về tính năng, bảo mật, hiệu năng, chi phí và vận hành.

Bài học thuộc phần **Điểm vào hệ thống** của học phần thiết kế kiến trúc đám mây. Khi thiết kế từ yêu cầu nghiệp vụ đến mạng, compute, dữ liệu và mô hình triển khai, việc chọn L4 hay L7 cần gắn với **giao thức thực tế, trải nghiệm người dùng, độ tin cậy, khả năng mở rộng, mức bảo vệ và năng lực vận hành**. Đây cũng là những câu hỏi có thể đưa vào một vòng đánh giá theo nguyên tắc Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt L4 và L7 theo thông tin định tuyến, giao thức, chức năng và giới hạn.
- Thiết kế điểm vào cho HTTP/HTTPS, gRPC, WebSocket, TCP và UDP dựa trên yêu cầu cụ thể.
- Giải thích TLS termination, TLS passthrough, health check, session affinity và connection draining.
- Phân tích rủi ro khi cân bằng tải qua nhiều instance, subnet, availability zone hoặc region.
- Thiết kế luồng quan sát, kiểm soát truy cập, dự phòng và ước lượng năng lực phục vụ.
- So sánh các dịch vụ load balancing cloud theo **tính năng cần dùng**, rồi kiểm chứng bằng thử tải và thử lỗi.

## 1. Bộ cân bằng tải nằm ở đâu trong kiến trúc?

Giả sử ứng dụng đặt lịch có ba bản sao Booking API. Khách hàng truy cập qua một hostname, chẳng hạn <code>booking.example.com</code>, thay vì cần biết địa chỉ của từng instance. DNS trả về điểm truy cập thích hợp, load balancer nhận kết nối hoặc yêu cầu, chọn backend còn đủ điều kiện và chuyển lưu lượng.

~~~mermaid
flowchart LR
    U["Browser / Mobile"] --> DNS["DNS: booking.example.com"]
    DNS --> LB["Public load balancer"]
    LB --> A1["Booking API A"]
    LB --> A2["Booking API B"]
    LB --> A3["Booking API C"]
    A1 --> DB[("Database")]
    A2 --> DB
    A3 --> DB
~~~

Sơ đồ cho biết **đường đi logic**. DNS không nhất thiết chuyển tiếp từng request: client thường dùng DNS để tìm endpoint rồi kết nối trực tiếp đến địa chỉ được phân giải. Trên cloud, endpoint có thể là địa chỉ ảo, nhiều địa chỉ, một tên do nhà cung cấp quản lý hoặc lớp mạng phân tán.

Load balancer giải quyết một số vấn đề:

1. **Phân phối lưu lượng** đến tập backend, tránh để client phụ thuộc trực tiếp vào một địa chỉ máy ứng dụng.
2. **Chọn backend đủ điều kiện** qua health check hoặc tín hiệu do hệ thống cung cấp.
3. **Tách địa chỉ công khai khỏi backend**, giúp thêm/bớt instance hoặc thay đổi cách triển khai mà không phải đổi URL người dùng.
4. **Hỗ trợ vận hành**, ví dụ draining kết nối khi phát hành, quan sát lỗi, phân phối lưu lượng giữa phiên bản theo tính năng được hỗ trợ.
5. **Đặt ranh giới bảo mật**, kết hợp TLS, phân vùng mạng, policy, WAF hoặc các cơ chế khác tùy loại load balancer.

Tuy nhiên, load balancer **không tự bảo đảm ứng dụng stateless, database chịu tải hoặc hệ thống chịu được sự cố toàn vùng**. Nếu cả ba API cùng phụ thuộc một database không có phương án phục hồi phù hợp, database vẫn là điểm lỗi quan trọng.

## 2. L4 và L7 khác nhau ở đâu?

Theo mô hình OSI, **lớp 4** tương ứng tầng vận chuyển (thường là TCP/UDP), còn **lớp 7** là tầng ứng dụng (HTTP, các giao thức ứng dụng khác). Trong thực tế, tên sản phẩm cloud có thể là *Network Load Balancer*, *Application Load Balancer*, *Gateway*, *Reverse Proxy* hoặc *Ingress*. Phải xem **khả năng cụ thể của sản phẩm**, vì tên gọi không luôn biểu thị chính xác mọi chức năng.

| Khía cạnh | Load balancer lớp 4 (L4) | Load balancer lớp 7 (L7) |
| --- | --- | --- |
| Thông tin định tuyến cơ bản | Địa chỉ IP, port, protocol, trạng thái kết nối; có thể dùng đặc điểm luồng | Host, path, method, header, cookie và các thuộc tính HTTP được hỗ trợ |
| Đơn vị phân phối thường gặp | Kết nối TCP hoặc luồng/flow UDP | HTTP request hoặc luồng ứng dụng theo khả năng triển khai |
| Giao thức | Thường dùng cho TCP/UDP, và một số dịch vụ có hỗ trợ TLS listener | Thường dùng cho HTTP/HTTPS; một số hỗ trợ HTTP/2, gRPC, WebSocket |
| Host/path routing | Không định tuyến theo nội dung HTTP trong mô hình L4 thuần túy | Có thể định tuyến theo tên miền và đường dẫn |
| TLS | Có thể passthrough hoặc xử lý TLS ở listener nếu được hỗ trợ | Thường terminate TLS để đọc HTTP; có thể kết nối TLS tiếp đến backend |
| HTTP features | Thường không trực tiếp áp dụng rule theo URL/header | Có thể hỗ trợ redirect, rewrite, header rule, authentication, WAF hoặc rate limit tùy sản phẩm |
| Health check | Có thể kiểm tra TCP/port; một số hỗ trợ kiểm tra ở mức HTTP | Thường kiểm tra HTTP status/path và điều kiện phản hồi |
| Quan sát | Kết nối, packet/byte, reset, port, flow | Có thêm request rate, status code, route, latency HTTP khi được bật |
| Đánh đổi | Ít phụ thuộc ngữ nghĩa ứng dụng; thích hợp giao thức phi HTTP | Nhiều khả năng điều khiển lưu lượng web; cần xét tài nguyên xử lý và độ phức tạp cấu hình |

**Một lưu ý quan trọng:** phân loại L4/L7 mô tả *cách cân bằng tải xử lý lưu lượng*, không phải tuyên bố “L4 luôn nhanh hơn”, “L7 luôn chậm” hoặc “L4 không thể làm TLS”. Một L4 service có thể hỗ trợ TLS termination mà vẫn không hỗ trợ quy tắc route theo HTTP path. Khả năng, độ trễ và chi phí phải đo trên dịch vụ cloud và workload cụ thể.

### L4: lựa chọn backend từ thông tin vận chuyển

Ví dụ một client mở TCP tới <code>tcp.example.com:5672</code>. L4 load balancer chuyển kết nối đó đến một backend còn khỏe phù hợp. Khi kết nối tồn tại, các gói tin của cùng luồng cần tiếp tục được chuyển nhất quán đến đúng backend để giữ trạng thái TCP.

~~~mermaid
sequenceDiagram
    participant C as TCP client
    participant L as L4 load balancer
    participant B as TCP backend
    C->>L: Kết nối TCP tới IP:port
    L->>B: Mở/chuyển tiếp luồng tới backend được chọn
    B-->>C: Dữ liệu trả về qua đường định tuyến thích hợp
    Note over L,B: Backend được chọn theo connection/flow
~~~

L4 không cần hiểu URL <code>/appointments</code> bên trong HTTPS để chọn backend. Đó là lợi thế khi phục vụ giao thức TCP tùy biến, cơ sở dữ liệu qua proxy phù hợp hoặc một số giao thức UDP. Việc cân bằng **UDP flow** còn phụ thuộc timeout và cách nhà cung cấp định danh flow; UDP không có kết nối theo cơ chế TCP.

### L7: lựa chọn backend theo thông tin ứng dụng

Ví dụ cùng một tên miền có thể phục vụ:

- <code>GET /api/slots</code> → nhóm Booking API.
- <code>POST /api/bookings</code> → nhóm Booking API với policy bảo vệ riêng.
- <code>GET /static/logo.svg</code> → nhóm dịch vụ tĩnh hoặc storage/CDN.
- <code>admin.example.com</code> → backend quản trị, với xác thực và chính sách truy cập chặt hơn.

~~~mermaid
flowchart TD
    C["HTTPS client"] --> L7["L7 load balancer<br/>TLS / HTTP routing"]
    L7 -- "Host: admin.example.com" --> ADMIN["Admin service"]
    L7 -- "Path: /api/*" --> API["Booking API"]
    L7 -- "Path: /static/*" --> STATIC["Static content origin"]
    L7 -- "Không khớp" --> DEFAULT["Default response hoặc backend"]
~~~

L7 cần đọc các thuộc tính HTTP để đưa ra quyết định, nên trong mô hình HTTPS điển hình, thành phần này **terminate TLS phía client**, rồi có thể dùng HTTP nội bộ hoặc TLS mới tới backend. Quyết định này liên quan trực tiếp tới vị trí quản lý chứng chỉ, dữ liệu dạng rõ và ranh giới tin cậy.

## 3. Không nhầm giao thức với tên dịch vụ load balancer

Câu hỏi đầu tiên nên là **client dùng giao thức gì**, yêu cầu ở tầng ứng dụng ra sao, và tính năng nào thật sự cần:

| Loại lưu lượng | Lựa chọn thường phù hợp | Điều phải xác minh trước khi chốt |
| --- | --- | --- |
| Web HTTP/HTTPS với nhiều host/path | L7 HTTP load balancer | HTTP versions, rule routing, TLS, WAF, quota, giá |
| REST API một backend đơn giản | L4 hoặc L7 tùy yêu cầu | Cần HTTP metrics/WAF/auth/redirect hay chỉ phân phối kết nối? |
| gRPC qua HTTP/2 | L7 **có hỗ trợ gRPC/HTTP/2 đúng cách**, hoặc L4 passthrough | Backend protocol, streaming, timeout, HTTP/2, health check |
| WebSocket | L7 hỗ trợ HTTP upgrade/WebSocket hoặc L4 passthrough | Idle timeout, draining, kết nối dài, sticky session |
| TCP tùy biến | L4 hoặc gateway hiểu giao thức cụ thể | Source IP, TCP reset, kết nối lâu, TLS, port |
| UDP tùy biến | L4 **có UDP support** | Flow affinity, health check, UDP timeout, NAT và quota |
| HTTP/3 chạy trên QUIC/UDP | Endpoint/L7 edge **được công bố hỗ trợ HTTP/3** | Hỗ trợ QUIC ở listener, TLS, fallback HTTP/2, backend protocol |
| Nhiều dịch vụ web sau một IP/hostname | L7 nếu cần route theo request | Host/path match, ưu tiên rule và an toàn default route |

**HTTP/3 không đồng nghĩa mọi UDP load balancer có khả năng phân tích HTTP/3.** Một L4 LB có thể chuyển tiếp UDP packet, còn việc chấm dứt QUIC và áp dụng chính sách HTTP/3 đòi hỏi thành phần hiểu giao thức và tính năng cụ thể.

Đối với **gRPC**, HTTP/2 là thành phần quan trọng, nhưng không phải L7 nào cũng hỗ trợ đầy đủ các kiểu streaming hoặc gRPC health check. Với **WebSocket**, kết nối có thể tồn tại lâu hơn request HTTP thông thường; cần cấu hình timeout và thoát backend khi deploy.

## 4. Luồng TLS và ranh giới bảo mật

TLS tạo kết nối mã hóa giữa hai điểm cuối. Vị trí giải mã quyết định thành phần nào có thể kiểm tra dữ liệu ứng dụng và nơi nào phải được coi là vùng tin cậy.

### 4.1. TLS passthrough

~~~mermaid
flowchart LR
    C["Client"] -- "TLS encrypted" --> L["L4 LB<br/>Chuyển luồng"]
    L -- "TLS encrypted" --> B["Backend<br/>Terminate TLS"]
~~~

Trong mô hình này, backend xử lý TLS của client, còn L4 LB chủ yếu định tuyến luồng. Các ưu điểm có thể là giữ mã hóa đến backend và cho phép ứng dụng kiểm soát chứng chỉ/chính sách TLS riêng. Đánh đổi: một LB không giải mã HTTP không thể kiểm tra đầy đủ URL/header hay áp dụng WAF dựa trên HTTP tại chính điểm đó.

TLS passthrough **không tự bảo đảm end-to-end an toàn** nếu các hệ thống quản lý chứng chỉ, xác minh hostname, cập nhật TLS hoặc bảo vệ backend được triển khai sai.

### 4.2. TLS termination tại L7 và kết nối tiếp

~~~mermaid
flowchart LR
    C["Client"] -- "HTTPS/TLS" --> L["L7 LB<br/>Terminate TLS, HTTP rules"]
    L -- "HTTP nội bộ hoặc HTTPS/TLS mới" --> B["Backend"]
~~~

Trong mô hình này, L7 LB có thể áp dụng host/path routing, rule HTTP, logging và các chính sách L7 tương ứng. Đổi lại, HTTP đã giải mã tồn tại bên trong tiến trình LB và có thể trên một đoạn mạng nội bộ nếu kết nối backend không mã hóa.

Nếu yêu cầu bảo vệ dữ liệu trên cả đoạn LB → backend, sử dụng **TLS re-encryption** với chính sách xác thực backend phù hợp. Có chứng chỉ ở backend nhưng LB không xác minh chứng chỉ hoặc danh tính máy chủ thì chưa thể kết luận kết nối đáp ứng mục tiêu bảo mật.

### 4.3. Những cấu hình thường phải quyết định

| Hạng mục | Câu hỏi thiết kế |
| --- | --- |
| Chứng chỉ | Ai cấp, gia hạn, luân chuyển? Dùng chứng chỉ một host hay wildcard? |
| Protocol & cipher | Phiên bản TLS nào được chấp nhận? Có chính sách loại bỏ phiên bản yếu? |
| Backend encryption | LB → backend mã hóa hay không, có xác minh certificate/hostname? |
| mTLS | Client có cần chứng chỉ khi kết nối đến edge hoặc ở tầng dịch vụ không? LB có hỗ trợ đúng mô hình? |
| SNI | Nhiều hostname dùng cùng điểm vào thì chọn chứng chỉ/đích như thế nào? |
| HTTP redirect | HTTP trên port 80 được chuyển sang HTTPS hay bị từ chối? |
| Headers | Có xóa/thiết lập lại các header định danh client không đáng tin cậy? |
| Secrets | Khóa riêng TLS nằm ở đâu, ai được quyền truy cập và audit? |

**Đừng suy diễn từ số lớp:** một L4 LB với TLS listener có thể terminate TLS, nhưng không vì thế trở thành reverse proxy HTTP đầy đủ. Ngược lại, một số L7 gateway có nhiều khả năng định tuyến nhưng vẫn cần kết nối mạng và firewall bảo vệ backend.

## 5. Thuật toán phân phối tải và vấn đề kết nối dài

Khi có nhiều backend đều khỏe, load balancer phải chọn nơi nhận lưu lượng. Tùy sản phẩm và tầng xử lý, các thuật toán có thể gồm:

- **Round robin:** phân phối lần lượt; dễ hiểu nhưng không tính đầy đủ thời gian xử lý mỗi yêu cầu.
- **Weighted round robin:** phân phối theo trọng số; hữu ích khi backend khác năng lực hoặc chạy canary.
- **Least connections:** ưu tiên đích có ít kết nối hoạt động, tùy khả năng sản phẩm; số kết nối không luôn phản ánh mức CPU.
- **Hash-based / affinity:** gán luồng đến backend tương đối ổn định dựa trên khóa hoặc cookie; phù hợp một số bài toán có trạng thái.
- **Các thuật toán dựa trên độ trễ/tải thực đo:** có thể được nền tảng cung cấp, nhưng không nên mặc định mọi cloud có hoặc hoạt động giống nhau.

### L4 không giống cân bằng số HTTP request

Giả sử một client duy trì kết nối TCP lâu dài và gửi nhiều yêu cầu qua kết nối. L4 thường chọn backend theo **connection**, nên 100 kết nối không nhất thiết chứa 100 đơn vị tải bằng nhau. Một client gửi nhiều request trên một kết nối có thể tạo phần lớn tải cho một backend.

Tương tự, HTTP/2 có thể **multiplex** nhiều stream trên một kết nối TCP; cách L7 phân phối stream/request phụ thuộc implementation và cách quản lý kết nối upstream. Không được mặc định một request trên HTTP/2 luôn nhận một backend độc lập.

Vì thế, khi thử tải, cần mô phỏng **số kết nối, request trên mỗi kết nối, thời gian sống, số stream và tỷ lệ request nặng/nhẹ** giống hành vi thực tế.

### Sticky session có phải cách xử lý state?

**Session affinity / sticky session** cố gắng gửi các request của một client về cùng backend trong một khoảng thời gian. Nó có thể giúp một hệ thống legacy dùng session trong bộ nhớ, nhưng tạo hạn chế:

1. Phân phối tải mất cân đối khi một số session hoạt động mạnh.
2. Backend chết hoặc được thay trong deployment khiến session cục bộ mất.
3. Autoscaling và rolling deploy khó dự đoán hơn.
4. Session cookie hoặc khóa affinity cần được bảo vệ và có timeout phù hợp.

Với ứng dụng web/API mới, nên cân nhắc **stateless application**, dùng session token phù hợp hoặc trạng thái lưu ngoài tiến trình khi nghiệp vụ yêu cầu. Session affinity là một công cụ có điều kiện, không thay thế tính bền vững dữ liệu.

## 6. Health check, chọn backend và xử lý sự cố

Load balancer cần biết backend có đủ điều kiện nhận lưu lượng mới không. Hai kiểm tra thường gặp:

**Kiểm tra ở tầng kết nối:** có thể mở TCP đến cổng dịch vụ. Điều này chứng minh cổng có phản hồi, **không chứng minh API đặt lịch còn hoạt động đúng**.

**Kiểm tra ở tầng ứng dụng:** gọi endpoint như <code>GET /health/ready</code> và kiểm tra HTTP status/điều kiện đáp ứng. Nó có thể phản ánh độ sẵn sàng thực tế hơn, nhưng phải tránh làm endpoint quá nặng hoặc phụ thuộc vào tất cả downstream một cách không cần thiết.

### Phân biệt liveness và readiness

- **Liveness:** tiến trình có bị treo hoặc không thể tự phục hồi không? Có thể dẫn tới restart theo khả năng runtime.
- **Readiness:** instance có sẵn sàng nhận **lưu lượng mới** không? Nếu chưa khởi động xong, đang draining hoặc quá tải, cần loại khỏi vòng phân phối.
- **Startup:** một số môi trường có kiểm tra riêng trong lúc ứng dụng khởi động lâu, tránh kill do readiness/liveness trước khi hoàn thành.

Đối với L7 LB, readiness endpoint có thể là HTTP path; đối với L4 LB, có thể sử dụng TCP check hoặc một endpoint health check riêng khi sản phẩm hỗ trợ. **Tầng của data-plane không bắt buộc tầng của health check phải giống hệt**: một số L4 LB cũng hỗ trợ health check HTTP.

### Ví dụ thiết kế health cho Booking API

| Tình huống | Liveness | Readiness | Hệ quả mong muốn |
| --- | --- | --- | --- |
| Ứng dụng đang khởi động | Có thể chưa đạt, phụ thuộc startup policy | Không đạt | Chưa nhận traffic |
| API đã sẵn sàng phục vụ | Đạt | Đạt | Được chọn làm backend |
| Instance đang dừng theo deployment | Có thể vẫn đạt | Không đạt | Ngừng nhận request mới, chờ hoàn tất request cũ |
| Thread pool quá tải nghiêm trọng | Có thể đạt | Có thể không đạt theo chính sách | Giảm lưu lượng tới instance, theo dõi áp lực chung |
| Database tạm lỗi | Ứng dụng có thể vẫn sống | Cần lựa chọn kiểm tra cẩn thận | Tránh restart đồng loạt nếu lỗi thuộc dịch vụ dùng chung |

Không phải mọi lỗi downstream đều nên khiến **tất cả backend** bị đánh dấu unhealthy. Nếu toàn bộ API đều có readiness phụ thuộc cứng vào một database đang lỗi, load balancer có thể loại hết backend mà không cải thiện khả năng phục hồi. Hệ thống cần policy rõ: trả lỗi có kiểm soát, áp dụng retry giới hạn, dùng cache cho một số đường đọc hoặc suy giảm chức năng theo nghiệp vụ.

### Health check có độ trễ phát hiện

Khi thiết lập chu kỳ kiểm tra, ngưỡng fail/success và thời gian timeout, nhóm phải chấp nhận **thời gian cần để phát hiện** backend không khỏe. Check quá thưa làm chuyển traffic chậm; check quá dày có thể tăng nhiễu và làm hệ thống bất ổn trong lúc chập chờn.

Để đánh giá HA, cần tính cả thời gian phát hiện, cập nhật tập backend, retry phía client, thời gian phục hồi và tác động lên các request đang chạy. Không đồng nhất “có hai instance” với “không downtime”.

## 7. Connection draining, timeout và triển khai không gián đoạn

Khi rolling deploy hoặc autoscale giảm, hệ thống cần ngừng gửi **lưu lượng mới** đến backend chuẩn bị dừng, đồng thời cho request/kết nối hiện tại hoàn tất trong một khoảng hợp lý. Quá trình này thường được gọi là **connection draining** hoặc **deregistration delay**, tùy nhà cung cấp và sản phẩm.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant LB as Load balancer
    participant OLD as API instance cũ
    participant NEW as API instance mới
    LB->>NEW: Health check
    NEW-->>LB: Ready
    LB->>OLD: Ngừng phân phối lưu lượng mới
    C->>LB: Request mới
    LB->>NEW: Chuyển request
    Note over OLD: Hoàn tất request đang xử lý nếu kịp
    OLD-->>LB: Hoàn tất response cũ
    Note over OLD: Dừng an toàn sau drain timeout
~~~

Các loại timeout cần xem riêng: kết nối ban đầu, idle, request, response, backend, health check và drain. Một WebSocket kết nối hàng giờ không thể được xử lý giống request REST 200 ms. Với streaming/gRPC, cần xác định cách đóng kết nối, retry an toàn và thời gian khách hàng có thể kết nối lại.

**Retry là nguồn rủi ro:** khi client, load balancer và ứng dụng cùng retry một yêu cầu ghi, số lần xử lý có thể nhân lên. Với thao tác đặt lịch hoặc thanh toán, cần **idempotency key** và xử lý lặp tại nghiệp vụ/database. Không nên retry vô điều kiện các method ghi hoặc request đang có side effect.

## 8. Đặt LB ở đâu: public, internal, regional và global

Một workload thường có nhiều điểm vào:

| Điểm vào | Ví dụ | Câu hỏi thiết kế |
| --- | --- | --- |
| **Public / Internet-facing** | Web và API dành cho khách hàng | DNS, TLS, WAF, DDoS, IP công khai, multi-AZ, rate limit |
| **Internal / Private** | API giữa các dịch vụ hoặc từ mạng công ty | Private routing, segmentation, mTLS, giới hạn mạng nguồn |
| **Regional** | API trong một region | Nhiều AZ, tuyến trong vùng, phụ thuộc regional |
| **Global / Cross-region** | Ứng dụng phục vụ nhiều khu vực | Latency routing, health, failover, data residency, đồng bộ dữ liệu |

Một LB *public* không đòi hỏi mọi backend ở public subnet. Mô hình phổ biến là **public frontend** nhận lưu lượng Internet, backend trong mạng riêng chỉ chấp nhận kết nối từ thành phần được phép.

Tách bạch ba trách nhiệm:

1. **DNS / global traffic management:** đưa client đến endpoint hoặc vùng thích hợp, theo policy và tình trạng được quan sát. DNS cache và TTL ảnh hưởng tốc độ chuyển vùng, không bảo đảm mọi client cập nhật ngay.
2. **Regional L4/L7 load balancer:** chọn backend trong phạm vi cấu hình của dịch vụ, theo kết nối hoặc request.
3. **Backend application:** xử lý nghiệp vụ và trạng thái, có chính sách retry, concurrency, idempotency và truy cập dữ liệu.

### Sơ đồ minh họa cho ứng dụng đặt lịch

~~~mermaid
flowchart TB
    CLIENT["Khách hàng Internet"] --> DNS["Public DNS"]
    DNS --> EDGE["CDN / WAF / DDoS protection<br/>Nếu có nhu cầu"]
    EDGE --> ALB["Public L7 load balancer<br/>HTTPS, host/path routing"]
    subgraph VPC["Private application network"]
        ALB --> API_A["Booking API - AZ A"]
        ALB --> API_B["Booking API - AZ B"]
        API_A --> DB[("Managed database<br/>HA theo cấu hình")]
        API_B --> DB
        API_A --> QUEUE["Managed queue"]
        API_B --> QUEUE
        QUEUE --> WORKER["Notification worker"]
        INTERNAL["Internal service client"] --> ILB["Private LB nếu cần"]
        ILB --> API_A
        ILB --> API_B
    end
~~~

**Không được hiểu sơ đồ là cấu hình mặc định.** Cần xác minh edge và LB có hỗ trợ tích hợp nhau, địa chỉ backend, security group/firewall, health check, TLS và tương tác với autoscaling. CDN hoặc WAF có thể được tích hợp vào chính sản phẩm edge/L7; không nhất thiết có một hop độc lập.

Nếu chọn **L4** làm public frontend cho một giao thức TCP tùy biến, kiến trúc có thể không có HTTP routing/WAF tại chính LB. Khi đó cần các cơ chế bảo vệ tương ứng ở lớp mạng, dịch vụ hoặc gateway khác.

### Multi-AZ và multi-region khác nhau

Triển khai L7 hoặc L4 LB với backend ở nhiều **availability zone** có thể tăng khả năng chịu sự cố zone, nhưng cần kiểm tra backend capacity và các phụ thuộc khác. Nếu mất một zone, vùng còn lại phải đủ năng lực tiếp nhận tải.

**Multi-region** lại là bài toán lớn hơn: chuyển lưu lượng giữa các region, quản lý state/data replication, đảm bảo thứ tự và tính nhất quán, giới hạn vùng lưu dữ liệu, kiểm thử failover và failback. Đặt hai load balancer ở hai region chưa đủ để tạo dịch vụ multi-region đáng tin cậy.

## 9. Source IP, proxy headers và quyền tin cậy

Khi request đi qua một hoặc nhiều proxy/load balancer, backend có thể thấy **địa chỉ IP của proxy** thay vì địa chỉ client ban đầu. Nếu hệ thống dùng IP để rate-limit, điều tra, audit hoặc chính sách truy cập, phải xác định cách truyền danh tính mạng.

Các cơ chế thường gặp:

- **Forwarded / X-Forwarded-For:** HTTP header ghi chuỗi proxy/client theo quy ước; dùng phổ biến sau reverse proxy L7.
- **X-Forwarded-Proto / Forwarded proto:** cho backend biết scheme ban đầu khi TLS terminate tại LB.
- **PROXY protocol:** truyền metadata kết nối ở tầng proxy/transport khi cả hai đầu hỗ trợ, thường hữu ích với L4.
- **Client IP preservation:** một số sản phẩm L4 có chế độ bảo toàn địa chỉ nguồn theo kiểu target, topology, network và cấu hình.

**Không bao giờ tin trực tiếp một header <code>X-Forwarded-For</code> do client Internet tự gửi.** Nếu ứng dụng tự lấy giá trị đầu tiên trong chuỗi header mà không xác định trusted proxy, attacker có thể giả mạo IP để qua rule hoặc làm sai audit.

Thiết kế đúng gồm:

1. Chỉ chấp nhận đường vào từ proxy/LB được quản lý, với chính sách network phù hợp.
2. Xác định danh sách **trusted proxies** và cách LB xử lý, thêm hoặc loại bỏ header do client cung cấp.
3. Cấu hình ứng dụng/framework hiểu số hop hoặc dải proxy tin cậy; kiểm tra request đi qua nhiều lớp CDN → LB → gateway.
4. Dùng identity/token cho authorization nghiệp vụ; IP chỉ là một tín hiệu phụ, không thay thế xác thực người dùng.

Ví dụ khi TLS kết thúc ở LB và backend nhận HTTP, nếu framework hiểu sai scheme gốc có thể tạo URL redirect sang <code>http://</code>, đánh dấu cookie thiếu thuộc tính Secure hoặc xây callback sai. Hãy cấu hình scheme/host forwarding theo đường tin cậy đã xác minh.

## 10. L4/L7 liên quan đến bảo mật như thế nào?

Load balancer tạo ranh giới xử lý traffic, nhưng **bảo mật là tổng hòa nhiều lớp**:

| Rủi ro | Biện pháp phù hợp để đánh giá |
| --- | --- |
| Lưu lượng không được phép đến backend | Private subnets, firewall/security groups, route và rule chỉ cho nguồn LB/gateway |
| Tấn công HTTP, payload độc hại | WAF hoặc cơ chế kiểm tra HTTP ở nơi có thể hiểu L7; ứng dụng vẫn phải validate |
| Lạm dụng API, credential stuffing | Rate limit theo định danh/IP phù hợp, auth, quota, chống bot, bảo vệ endpoint nhạy cảm |
| Flooding ở tầng mạng/vận chuyển | DDoS protection và khả năng hấp thụ lưu lượng theo nhà cung cấp; giám sát kết nối |
| Nghe lén/giả mạo trên đường truyền | TLS phù hợp, quản lý certificate/secret, mTLS khi có yêu cầu |
| Rò rỉ qua log | Che token, dữ liệu cá nhân; quyền truy cập, retention, vùng lưu |
| Route nhầm sang backend nhạy cảm | Kiểm tra host/path rule, default action, ACL và test quyền |
| Làm giả client IP | Trusted proxy configuration, loại bỏ/ghi lại header ở biên tin cậy |

**L7 LB không mặc định là WAF**, và **WAF không thay thế authorization trong ứng dụng**. API vẫn cần kiểm tra mỗi người dùng được truy cập đối tượng nào, chống injection, kiểm soát request body và xử lý session an toàn.

Khi route theo tên miền, cấu hình **default route** phải có chủ đích. Ví dụ host không được công bố có thể trả 404/403 theo thiết kế thay vì chuyển nhầm vào Admin backend. Cần kiểm thử các trường hợp Host header lạ, path encoding, slash/case và rule ưu tiên để tránh truy cập ngoài dự kiến.

## 11. L4/L7 có tác động đến khả năng mở rộng và chi phí

Load balancer thường đứng trước nhiều instance, nhưng nó không loại bỏ giới hạn tài nguyên của backend. Cần sizing theo **lưu lượng thực**, đặc biệt khi có các request lâu, upload lớn hoặc kết nối WebSocket.

### 11.1. Ước lượng sơ bộ backend capacity

Giả sử Booking API dự kiến **600 request/giây** ở thời điểm cao điểm. Qua thử tải, một instance xử lý bền vững **120 request/giây** ở mức CPU, p95 và tỷ lệ lỗi được chấp nhận.

~~~text
Số instance lý thuyết theo thông lượng
  = ceil(600 request/giây / 120 request/giây/instance)
  = 5 instance
~~~

**Năm instance chỉ đủ về thông lượng khi tất cả còn hoạt động và giả định tải không đổi.** Nếu cần chịu lỗi một availability zone, phải tính khả năng phần còn lại tiếp nhận **toàn bộ 600 RPS**. Chẳng hạn với hai zone và mục tiêu vẫn giữ tải này sau khi mất bất kỳ một zone nào, cần ít nhất **5 instance còn hoạt động ở zone sống sót**. Một phương án cân xứng có thể bắt đầu với 5 instance mỗi zone (tổng 10), trước khi tính thêm headroom, biến động tải, năng lực LB và những giới hạn khác.

Đây là **minh họa cách suy luận**, không phải số instance khuyến nghị cho hệ thống thật. Capacity của từng instance phải đo trong tải hỗn hợp có truy vấn database, TLS/proxy, kết nối thật, cache, write contention, quota và thời gian scale-out. Nếu tính năng autoscaling tạo instance mới mất vài phút, cần dự phòng cho giai đoạn chưa mở rộng kịp.

### 11.2. L4 thường chịu ảnh hưởng mạnh của connection/flow

Đối với TCP dài, quan sát **active connections**, connection setup rate, reset, connection duration và bytes. Với UDP, quan sát packet/byte rate, flow timeout, phân phối nguồn và độ trễ ứng dụng qua telemetry riêng.

Một LB có thể xử lý nhiều connection nhưng backend không đủ **file descriptors, thread, memory, connection pool** hoặc giới hạn socket. Nếu L4 thực hiện NAT, còn cần theo dõi khả năng cạn cổng nguồn/port allocation theo topology và dịch vụ, không suy từ RPS đơn thuần.

### 11.3. L7 thường cần quan sát thêm request-level

Ngoài connection metrics, cần đo **HTTP status code, request rate, p50/p95/p99 latency, response size, route/target group, TLS handshake, request timeout**, nếu nền tảng cung cấp. L7 phải xử lý nhiều thông tin ứng dụng hơn; mức chi phí tài nguyên sẽ tùy sản phẩm, thuật toán, kết nối, rule, logging và đặc tính tải.

### 11.4. Chi phí không chỉ là phí LB

Khi lập budget, xem:

- Phí cố định/giờ hoặc theo đơn vị cấu hình, **nếu dịch vụ áp dụng**.
- Phí theo byte, connection, request, rule, capacity unit hoặc metric tính tiền theo từng nhà cung cấp.
- Truyền dữ liệu qua zone/region, Internet egress, NAT, CDN hoặc đường private.
- Chi phí WAF, TLS/certificate, log access, metric, alert và lưu trữ log.
- Chi phí backend cần dự phòng để đáp ứng SLO và failover.
- Nhân công cấu hình, giám sát, chứng chỉ, xử lý sự cố và kiểm tra bảo mật.

Không có quy tắc “L4 luôn rẻ hơn L7”. Quy mô traffic, cách tính tiền, kiến trúc mạng, lượng log và thành phần đi kèm có thể đảo ngược kết luận. Ước lượng nên dựa trên **bảng giá và quota thực tế của dịch vụ được chọn**, với kịch bản tải cơ sở, tải đỉnh và tăng trưởng.

## 12. Dịch vụ tương ứng trên các cloud: ánh xạ ở mức khái niệm

Các nhà cung cấp có nhiều sản phẩm với phạm vi địa lý và tính năng khác nhau. Bảng sau giúp định hướng tìm kiếm phương án, **không phải ánh xạ tương đương một-một hoặc danh sách tính năng được bảo đảm ở mọi region**.

| Khả năng | AWS (ví dụ) | Azure (ví dụ) | Google Cloud (ví dụ) |
| --- | --- | --- | --- |
| Cân bằng tải L4 TCP/UDP theo sản phẩm | Network Load Balancer | Azure Load Balancer | Network Load Balancer, tùy biến thể passthrough/proxy |
| Cân bằng tải L7 HTTP/HTTPS | Application Load Balancer | Application Gateway; Azure Front Door cho một số kịch bản edge/global | Application Load Balancer với phạm vi regional/global tùy biến thể |
| Bảo vệ ứng dụng web ở L7 | AWS WAF tích hợp theo dịch vụ hỗ trợ | WAF ở Application Gateway/Front Door theo cấu hình | Cloud Armor với LB tương thích |
| Quản lý lưu lượng toàn cầu hoặc từ edge | CloudFront, Global Accelerator hoặc giải pháp DNS/route phù hợp | Azure Front Door, Traffic Manager và các dịch vụ tương ứng | Global external Application Load Balancer, Cloud CDN, Cloud DNS theo thiết kế |
| Private/internal traffic | LB nội bộ theo loại và VPC | Internal Load Balancer / Application Gateway private theo khả năng | Internal Application/Network Load Balancer theo sản phẩm |

Một số lưu ý:

- **AWS:** Application Load Balancer là lựa chọn L7 phổ biến cho HTTP/HTTPS và các tính năng phù hợp; Network Load Balancer phục vụ nhu cầu L4 theo giao thức/target được hỗ trợ. Không suy rằng mọi rule WAF, gRPC hoặc TLS đều có ở cả hai.
- **Azure:** Azure Load Balancer và Application Gateway giải quyết các lớp khác nhau; Azure Front Door tập trung kịch bản edge/global cho web. Khả năng hoạt động private/public và tích hợp WAF cần kiểm tra theo SKU/phiên bản và cấu hình.
- **Google Cloud:** có các biến thể Application/Network Load Balancer, proxy hoặc passthrough, regional hoặc global với tính năng khác nhau. Cần đọc đúng loại LB, protocol support và sơ đồ data path.

Trước khi ra quyết định, lập bảng kiểm tra riêng về **listener protocols, gRPC/WebSocket/HTTP3, backend type, cross-zone/cross-region, TLS, WAF, source IP, health checks, quotas, observability, private connectivity, SLA và chi phí** của đúng dịch vụ/SKU tại region sẽ triển khai.

## 13. Quy trình chọn L4 hay L7 từ yêu cầu nghiệp vụ

### Bước 1 — Liệt kê các điểm vào

Với mỗi client, ghi loại traffic, người dùng, độ nhạy dữ liệu và phạm vi kết nối. Ví dụ ứng dụng đặt lịch có public HTTPS API, web admin giới hạn nhân viên và một TCP service nội bộ nhận telemetry. Không mặc định cả ba đi qua cùng một frontend.

### Bước 2 — Chốt chức năng cần ở điểm vào

Cần route theo host/path không? Có WAF, HTTP redirect, xác thực, rate limit, traffic split/canary, mTLS hoặc HTTP metrics không? Nếu có tính năng L7 bắt buộc, cần một thành phần hiểu L7 tại đúng nơi áp dụng.

### Bước 3 — Xác định ranh giới TLS và network

Chứng chỉ ở đâu, có dùng TLS từ LB đến backend không, backend có public IP hay nằm private subnet, firewall cho phép nguồn nào? Nếu phải giữ TLS đến ứng dụng, thiết kế L4 passthrough hoặc L7 re-encryption theo đúng yêu cầu và hỗ trợ của nền tảng.

### Bước 4 — Thiết kế độ tin cậy và vận hành

Chọn health check, timeout, draining, số zone/region, hành vi khi không còn backend healthy, cơ chế retry và rollback. Xác định ai chịu trách nhiệm chứng chỉ, route, cập nhật target và ứng cứu.

### Bước 5 — Đo năng lực và tính chi phí

Thử trên loại tải có ý nghĩa: RPS, số connection, streaming/long-lived requests, tỷ lệ lỗi, traffic qua zone, kích thước response và thời gian scale-out. So sánh tổng chi phí chứ không chỉ phí giờ của LB.

### Bước 6 — Ghi quyết định kiến trúc

Tạo **ADR** (Architecture Decision Record) mô tả bối cảnh, phương án, lý do, hệ quả, kịch bản test và điều kiện review. Ví dụ tiêu đề: “Chọn L7 public LB cho Booking HTTPS API và L4 private LB cho TCP telemetry”.

### Cây quyết định tham khảo

~~~mermaid
flowchart TD
    START["Điểm vào mới"] --> HTTP{"Lưu lượng cần hiểu HTTP?"}
    HTTP -- "Không: TCP/UDP" --> L4["Đánh giá L4 LB và protocol support"]
    HTTP -- "Có" --> RULE{"Cần route theo host/path, WAF, HTTP features?"}
    RULE -- "Có" --> L7["Đánh giá L7 HTTP LB / gateway"]
    RULE -- "Không" --> SIMPLE["Đánh giá cả L4 passthrough và L7 đơn giản"]
    L4 --> VERIFY["Kiểm chứng TLS, health, network, HA, quota, chi phí"]
    L7 --> VERIFY
    SIMPLE --> VERIFY
    VERIFY --> ADR["Ghi ADR và phép thử thực tế"]
~~~

Cây trên giúp định hướng. Nó không thay thế kiểm tra giao thức đặc thù, yêu cầu tuân thủ hay tài liệu kỹ thuật của dịch vụ được chọn.

## 14. Bài thực hành: thiết kế điểm vào cho một nền tảng đặt lịch

**Bối cảnh giả định:** Một doanh nghiệp triển khai ứng dụng đặt lịch và cổng quản trị lên cloud với hai availability zone. Các thành phần:

- **Web frontend:** HTTPS, ảnh và nội dung tĩnh có thể cache.
- **Booking API:** REST HTTPS, cần endpoint <code>/api/*</code>, 600 RPS cao điểm, p95 dưới 300 ms và tỷ lệ giao dịch hợp lệ thành công 99,9% mỗi 30 ngày.
- **Admin API:** HTTPS trên <code>admin.example.com</code>, chỉ nhân viên được xác thực truy cập; yêu cầu audit.
- **Telemetry collector:** giao thức TCP riêng, nhận kết nối lâu, chỉ cho nguồn từ mạng doanh nghiệp.
- **Backend:** API chạy stateless ở hai zone, database managed và worker nhận queue; mỗi API instance đạt 120 RPS bền vững trong phép thử giả định.
- **Ràng buộc:** cần chịu lỗi một zone cho luồng Booking và bảo vệ dữ liệu khách hàng khi truyền; nhóm vận hành nhỏ.

Các số liệu trên là **dữ kiện của bài tập**, chưa phải khả năng đã được một nhà cung cấp bảo đảm.

### Nhiệm vụ 1 — Chọn các loại load balancer

Đề xuất điểm vào cho từng luồng. Với Web/Booking/Admin, giải thích tại sao L7 có thể có ích cho host/path rules, HTTP telemetry và WAF. Với TCP telemetry, giải thích khi nào L4 private LB là đủ và tại sao không cần phân tích HTTP.

### Nhiệm vụ 2 — Vẽ sơ đồ mạng và ranh giới TLS

Vẽ public frontend, private backend, hai AZ, đường đến database, mạng doanh nghiệp và điểm vào TCP nội bộ. Ghi rõ nơi terminate TLS; nếu LB → backend dùng TLS, chỉ ra cách xác thực backend. Phân quyền để Admin API không vô tình mở trực tiếp ra Internet chỉ vì được đưa sau public LB.

### Nhiệm vụ 3 — Tính capacity và kiểm tra failover

Với 600 RPS và 120 RPS/instance bền vững, tính số instance tối thiểu nếu mọi instance khỏe. Sau đó đề xuất số lượng hai AZ để khi một zone chết, zone kia vẫn đủ tải với headroom hợp lý. Đánh giá giới hạn database, tốc độ autoscale và chi phí của phương án.

### Nhiệm vụ 4 — Thiết kế health và deployment

Định nghĩa health check cho Booking API và TCP collector. Xác định readiness, liveness, timeout, draining và hành vi khi còn không đủ backend healthy. Mô tả cách deploy một phiên bản API mới mà không làm rớt request đang chạy quá phạm vi đã chấp nhận.

### Nhiệm vụ 5 — Xây bộ phép thử

| Phép thử | Điều kiện | Bằng chứng cần thu |
| --- | --- | --- |
| HTTP routing | Gọi <code>/api/*</code>, <code>/static/*</code> và host admin | Route chính xác; host/path không khớp có default an toàn |
| TLS & client IP | Gọi qua CDN/L7 và truyền header IP giả | TLS hợp lệ; backend xác định client IP qua trusted proxies |
| Backend failure | Dừng một API instance đã đăng ký | Health loại target lỗi, request chuyển sang target khác trong thời hạn chấp nhận |
| Zone failure | Giả lập mất một zone trong test kiểm soát | Tỷ lệ lỗi, p95, capacity và thời gian khôi phục theo SLO/RTO đã đề ra |
| Long-lived TCP | Giữ các kết nối telemetry hoạt động trong lúc rolling deploy | Quan sát reset, timeout, reconnect và dữ liệu mất/trùng |
| Request retries | Gửi lặp POST tạo lịch khi response bị gián đoạn | Không tạo booking trùng; idempotency được chứng minh |
| Load & scale | 600 RPS rồi tăng đột biến trong thời gian xác định | CPU, p95, 5xx, connection count, DB saturation và thời gian scale |
| Security | Thử direct access đến backend và Admin API trái quyền | Bị từ chối theo mạng/auth; log kiểm toán có dữ liệu phù hợp |
| Cost observation | Tạo tải thử có kiểm soát, thu request/bytes/connections | Có cơ sở ước lượng phí LB, WAF, data transfer và logs |

### Nhiệm vụ 6 — Review theo sáu trụ cột Well-Architected

| Trụ cột | Câu hỏi đánh giá điểm vào hệ thống |
| --- | --- |
| **Operational Excellence** | Có IaC, tự động cập nhật target, dashboard, runbook, rollback và chủ sở hữu chứng chỉ không? |
| **Security** | TLS, WAF, client IP, authentication, network boundary và chính sách header có đúng ranh giới tin cậy không? |
| **Reliability** | Backend được health-check, có draining, đủ capacity khi một zone lỗi và kế hoạch phục hồi không? |
| **Performance Efficiency** | Quyết định dựa trên kết quả thử kết nối, RPS, p95/p99, stream, quota và scale-out chưa? |
| **Cost Optimization** | Đã tính phí LB, request/byte, liên zone, WAF, logging và dự phòng backend chưa? |
| **Sustainability** | Có tránh backend nhàn rỗi quá mức, log trùng và truyền dữ liệu không cần thiết không? |

### Gợi ý hướng giải

Một phương án hợp lý là **public L7 HTTP LB** cho Booking/Web, cấu hình TLS và route theo host/path, tích hợp bảo vệ web phù hợp; **điểm vào Admin** có kiểm soát xác thực và phạm vi truy cập riêng; **private L4 TCP LB** cho collector được phép từ mạng doanh nghiệp. API stateless được phân phối qua hai AZ, backend riêng và health check phù hợp.

Với khả năng 120 RPS/instance, tối thiểu lý thuyết là 5 instance khi toàn bộ backend hoạt động. Nếu một AZ phải tiếp nhận đủ 600 RPS sau sự cố, thiết kế hai AZ **mỗi AZ có tối thiểu 5 instance** trong điều kiện giả định, rồi cộng thêm dự phòng theo kết quả thử. Cần kiểm tra tải database và thời gian autoscaling vì capacity API không đại diện cho capacity toàn bộ dịch vụ.

Hướng giải này chỉ được chấp nhận khi **tính năng của dịch vụ cloud thực tế** hỗ trợ những gì thiết kế đòi hỏi và các phép thử chứng minh mục tiêu vận hành. Có thể có phương án khác dùng CDN/edge riêng, API gateway hoặc cách phân tách Admin chặt hơn, tùy yêu cầu và rủi ro.

## 15. Những sai lầm thường gặp

**1. Chọn “Network Load Balancer” chỉ vì tên có chữ network.** Cần kiểm tra giao thức, layer, target type, TLS, client IP và routing thực tế; không suy từ tên marketing.

**2. Giả định L4 luôn nhanh hoặc rẻ hơn L7.** Độ trễ và giá phụ thuộc implementation, loại traffic, TLS, rule, cache, data transfer và hạ tầng backend. Phải đo.

**3. Mong L4 route theo HTTP path khi đang TLS passthrough.** Thành phần không đọc HTTP không thể áp rule theo URL; cần L7 ở vị trí có quyền giải mã hoặc thay đổi yêu cầu.

**4. Dùng sticky session để thay thế thiết kế state.** Khi instance chết, session trong RAM có thể mất; ứng dụng nên có chiến lược state và phục hồi rõ.

**5. Health check chỉ kiểm tra mở port rồi tuyên bố ứng dụng khỏe.** TCP port mở không chứng minh giao dịch nghiệp vụ thành công; phải bổ sung SLI và phép thử chức năng.

**6. Không tính connection draining và idle timeout.** Rolling deploy hoặc WebSocket/gRPC có thể mất kết nối bất ngờ.

**7. Để backend công khai vì frontend đã có WAF.** Cần chặn đường truy cập bỏ qua WAF/LB bằng network policy, routing và authentication thích hợp.

**8. Tin mọi giá trị X-Forwarded-For.** Header có thể bị client giả mạo; chỉ tin chuỗi proxy được cấu hình rõ.

**9. Coi nhiều backend là đủ HA.** Chưa chắc còn đủ capacity khi mất zone, chưa giải quyết database/queue, DNS và sự cố region.

**10. Quên giới hạn của kết nối dài hoặc HTTP/2 multiplexing.** Đếm HTTP request chưa đủ để dự báo số connection, khả năng phân phối và resource saturation.

**11. Bật retry ở nhiều tầng không kiểm soát.** Có thể gây tải khuếch đại và lặp giao dịch; phải có timeout, backoff và idempotency.

**12. Thiết kế theo một sơ đồ mẫu mà không ghi giả định.** Region, protocol support, target type và tính năng cloud khác nhau; ADR và kiểm thử giúp biết khi nào cần thay quyết định.

## 16. Checklist trước khi triển khai production

- [ ] Liệt kê mọi điểm vào và phân loại HTTP/HTTPS, gRPC, WebSocket, TCP hoặc UDP.
- [ ] Chọn L4/L7 dựa trên khả năng định tuyến cần thiết; xác minh tính năng đúng dịch vụ cloud/SKU.
- [ ] Định nghĩa public/private endpoint, vùng mạng, subnet, route, firewall và nguồn truy cập hợp lệ.
- [ ] Ghi rõ TLS termination/passthrough/re-encryption, chứng chỉ và kiểm tra danh tính backend.
- [ ] Cấu hình host/path routing, rule ưu tiên, default action và bảo vệ HTTP khi cần.
- [ ] Xác định trusted proxies, xử lý forwarded headers và audit client identity đúng cách.
- [ ] Có health check, readiness, timeout, draining và phương án khi backend bị loại hết.
- [ ] Kiểm chứng khả năng còn đủ tải khi mất instance/zone theo mục tiêu reliability.
- [ ] Thử đặc tính connection dài, HTTP/2/gRPC/streaming và UDP nếu sử dụng.
- [ ] Xác định retry/redirect/rate limit, tính idempotent của thao tác ghi và giới hạn tải.
- [ ] Có metric, access/error logs, cảnh báo tỷ lệ lỗi, độ trễ, target health và quota.
- [ ] Đã ước lượng tổng chi phí LB, backend dự phòng, WAF, networking và logging.
- [ ] Có IaC, rollback, owner, runbook, kết quả thử tải/thử lỗi và ADR cho lựa chọn quan trọng.

L4 và L7 đều là công cụ để xây dựng điểm vào đáng tin cậy, nhưng phục vụ các nhu cầu khác nhau. **L4 đưa ra quyết định chủ yếu từ kết nối hoặc luồng vận chuyển; L7 có thể hiểu và xử lý yêu cầu ở tầng ứng dụng.** Lựa chọn đúng là lựa chọn phù hợp với giao thức, chính sách bảo mật, mục tiêu SLO, khả năng phát hành và chi phí của workload cụ thể. Một sơ đồ đẹp cần được bổ sung bằng số đo và các thử nghiệm lỗi để chứng minh hệ thống thực sự vận hành như thiết kế.
