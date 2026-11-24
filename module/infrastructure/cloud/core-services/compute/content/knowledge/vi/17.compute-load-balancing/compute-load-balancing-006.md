# Session affinity và tác động của trạng thái phiên

Load balancer phân phối request đến nhiều máy chủ hoặc instance để tăng năng lực xử lý và tính sẵn sàng. Tuy nhiên, một ứng dụng có thể lưu trạng thái phiên (session state) trong bộ nhớ của từng instance. Khi request tiếp theo được chuyển đến instance khác, máy chủ mới có thể không tìm thấy dữ liệu phiên và người dùng bị đăng xuất, mất giỏ hàng hoặc phải thực hiện lại thao tác.

**Session affinity** (còn gọi là sticky session hoặc session persistence) là cơ chế cố gắng đưa các request tiếp theo của cùng một client hoặc phiên đến cùng một backend trong một khoảng thời gian. Cơ chế này hữu ích khi ứng dụng còn giữ session state cục bộ, nhưng nó cũng làm giảm mức độ tự do phân phối tải và có thể ảnh hưởng đến khả năng mở rộng, failover và cân bằng tải.

Bài học đặt session affinity trong bối cảnh thiết kế workload compute trên cloud: cần hiểu trạng thái phiên nằm ở đâu, load balancer xác định client bằng cách nào, điều gì xảy ra khi backend bị lỗi hoặc scale, và khi nào nên chuyển session state ra một kho dùng chung.

Sau bài học, bạn có thể:

- Giải thích session affinity và phân biệt nó với xác thực người dùng hoặc lưu session state.
- So sánh cookie-based affinity, source-IP affinity và consistent hashing.
- Mô tả ảnh hưởng của sticky session đến phân phối tải, autoscaling, health check và failover.
- Thiết kế ứng dụng stateless hoặc dùng session store dùng chung để giảm phụ thuộc vào một backend.
- Cấu hình và bảo vệ cookie phiên, thời hạn, quyền truy cập và dữ liệu session.
- Kiểm thử hành vi khi backend bị lỗi, thêm/bớt instance hoặc kết nối kéo dài.

## 1. Session state là gì?

Session là ngữ cảnh tương tác được duy trì giữa nhiều request của một người dùng hoặc client. HTTP vốn là giao thức stateless: mỗi request độc lập ở tầng giao thức. Ứng dụng thường tạo cơ chế session để nhớ trạng thái giữa các request.

Ví dụ, một website thương mại điện tử có thể lưu trong session:

- Người dùng đã đăng nhập hay chưa và định danh người dùng.
- Giỏ hàng tạm thời hoặc mã tham chiếu đến giỏ hàng.
- Ngôn ngữ, tiền tệ hoặc tùy chọn giao diện.
- Trạng thái nhiều bước của quy trình thanh toán.
- CSRF token hoặc dữ liệu điều hướng tạm thời.
- Một số dữ liệu nghiệp vụ ngắn hạn gắn với tương tác hiện tại.

Session thường được nhận diện qua một session ID được gửi trong cookie hoặc một cơ chế token. Server dùng ID đó để tìm trạng thái phiên ở nơi lưu trữ phù hợp.

### Session state có thể nằm ở đâu?

| Vị trí lưu | Cách hoạt động | Ưu điểm | Hạn chế |
|---|---|---|---|
| Bộ nhớ cục bộ của process | Mỗi instance giữ session trong RAM của chính nó | Nhanh, đơn giản, không cần dịch vụ ngoài | Mất khi process restart; request cần quay lại đúng instance; khó scale và failover |
| Local disk của instance | Session được ghi vào filesystem của VM/container | Có thể tồn tại qua process restart tùy vòng đời disk | Không chia sẻ tự nhiên giữa instance; local/ephemeral disk có thể mất khi thay host |
| Shared session store | Redis, database hoặc kho key-value dùng chung lưu session | Backend nào cũng có thể xử lý request nếu có quyền truy cập store | Thêm dependency, network latency, chi phí và yêu cầu HA/backup |
| Client-side protected state | Một phần trạng thái được ký hoặc mã hóa và gửi trong cookie/token | Giảm truy vấn session store | Giới hạn kích thước; thu hồi và cập nhật trạng thái khó; phải bảo vệ dữ liệu và khóa |
| Hybrid | Cookie giữ ID, shared store giữ dữ liệu; cache cục bộ có thể tăng tốc | Kết hợp hiệu năng và khả năng chia sẻ | Cần xử lý cache invalidation, consistency và expiration |

Không nên lưu mật khẩu, access token dài hạn, dữ liệu thanh toán nhạy cảm hoặc bí mật không cần thiết trong session. Session nên giữ thông tin tối thiểu hoặc tham chiếu đến dữ liệu được bảo vệ ở hệ thống phù hợp.

## 2. Session affinity hoạt động như thế nào?

Khi client gửi request đầu tiên, load balancer chọn một backend dựa trên thuật toán phân phối tải. Nếu affinity được bật, load balancer tạo hoặc nhận một khóa nhận diện client/session rồi dùng khóa đó để cố gắng chọn lại backend ở những request sau.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant LB as Load balancer
    participant A as Backend A
    participant B as Backend B
    C->>LB: Request đầu tiên
    LB->>A: Chọn backend A
    A-->>LB: Response và dữ liệu affinity
    LB-->>C: Response + cookie affinity
    C->>LB: Request tiếp theo + cookie
    LB->>A: Chuyển lại backend A
    A-->>LB: Response dùng session cục bộ
    LB-->>C: Response
~~~

Cơ chế này thường được gọi là sticky session. Từ “sticky” mô tả sự gắn kết định tuyến giữa client và backend; nó không có nghĩa dữ liệu phiên đã được sao chép hoặc bảo vệ khỏi mất mát.

### Hai loại cookie có thể xuất hiện

Cần phân biệt:

1. **Application session cookie:** do ứng dụng tạo để nhận diện phiên và tra cứu trạng thái người dùng.
2. **Load balancer affinity cookie:** do load balancer hoặc ingress tạo để ghi nhớ backend đã chọn.

Hai cookie có thể cùng tồn tại. Session cookie của ứng dụng không tự động đảm bảo request quay lại cùng backend nếu load balancer không có thuật toán affinity tương ứng. Ngược lại, affinity cookie chỉ điều khiển định tuyến; nó không chứng minh người dùng đã đăng nhập và không thay thế xác thực/authorization.

## 3. Các phương pháp tạo affinity

### Cookie-based affinity

Load balancer tạo cookie hoặc đọc cookie được cấu hình để gắn client với một backend. Request sau mang cookie đó và load balancer chọn lại backend tương ứng.

Ưu điểm:

- Có thể phân biệt phiên trên cùng một địa chỉ IP công cộng.
- Không phụ thuộc quá nhiều vào NAT hoặc proxy chia sẻ IP.
- Phù hợp với ứng dụng web dùng HTTP/HTTPS.
- Có thể đặt thời hạn affinity và kiểm soát vòng đời cookie.

Hạn chế:

- Client phải giữ và gửi cookie; client không hỗ trợ cookie có thể không được sticky.
- Cookie hết hạn, bị xóa hoặc thay đổi có thể làm request chuyển backend.
- Khi backend không healthy, load balancer có thể phải chọn backend khác và session cục bộ có thể không còn.
- Cần hiểu cookie domain, path, Secure, HttpOnly và SameSite.
- Cookie affinity không nên được coi là credential xác thực.

Một số dịch vụ tạo cookie riêng, một số dùng cookie do ứng dụng cung cấp hoặc cấu hình thời hạn theo dịch vụ. Cách xử lý khi backend biến mất khác nhau giữa các nhà cung cấp.

### Source-IP affinity

Load balancer dùng địa chỉ IP nguồn để xác định client và cố gắng gửi request từ IP đó đến cùng backend.

Ưu điểm:

- Không cần cookie hoặc thay đổi ứng dụng.
- Có thể dùng cho giao thức không mang cookie.
- Dễ áp dụng trong một số môi trường TCP hoặc ứng dụng cũ.

Hạn chế:

- Nhiều người dùng có thể chia sẻ một public IP qua NAT, proxy hoặc mạng doanh nghiệp; họ có thể bị dồn vào cùng backend.
- Một người dùng có thể đổi IP khi chuyển mạng di động/Wi-Fi hoặc qua proxy khác.
- IPv4/IPv6, proxy chain và địa chỉ nguồn quan sát được có thể làm thay đổi khóa.
- Có thể tạo phân phối tải lệch nếu một IP đại diện cho nhiều client.
- Không phù hợp khi địa chỉ nguồn không ổn định hoặc không phản ánh phiên ứng dụng.

Source-IP affinity thường kém chính xác hơn cookie affinity đối với ứng dụng web có nhiều người dùng sau NAT.

### Consistent hashing

Load balancer hoặc proxy dùng một khóa như session ID, cookie, URL path hoặc header để tính backend bằng hash. Consistent hashing được thiết kế để hạn chế số lượng khóa phải chuyển backend khi thêm hoặc bớt node, nhất là khi dùng hash ring hoặc thuật toán tương đương.

Ưu điểm:

- Có thể tạo định tuyến ổn định dựa trên khóa ứng dụng.
- Có thể áp dụng cho HTTP, TCP hoặc hệ thống cache/proxy.
- Khi membership thay đổi, một phần khóa có thể tiếp tục ánh xạ đến node cũ.

Hạn chế:

- Nếu khóa phân bố không đều, backend có thể bị lệch tải.
- Hash không tự lưu session state và không bảo đảm dữ liệu tồn tại khi node mất.
- Khi node bị loại khỏi ring, các khóa của node đó phải chuyển sang node khác; session cục bộ vẫn có thể mất.
- Cần xử lý hash key rỗng, giả mạo hoặc có thể bị client kiểm soát.

### Header hoặc application-defined affinity

Một số hệ thống cho phép dùng header hoặc trường do ứng dụng xác định làm khóa. Cách này linh hoạt nhưng cần bảo đảm khóa không chứa thông tin nhạy cảm, có phân phối đủ tốt và không thể bị client thao túng để ép tải vào một backend.

### So sánh phương pháp

| Phương pháp | Khóa định tuyến | Phù hợp | Rủi ro chính |
|---|---|---|---|
| Cookie-based | Cookie affinity/session | HTTP/HTTPS, browser, ứng dụng web | Cookie mất/hết hạn; backend lỗi; cần bảo vệ cookie |
| Source-IP | IP nguồn | TCP hoặc client không hỗ trợ cookie | NAT/proxy làm nhiều client chung khóa; IP thay đổi |
| Consistent hashing | Session ID, cookie, header hoặc key | Proxy, cache, dịch vụ cần ánh xạ ổn định | Key skew; node membership thay đổi; không lưu state |
| Application-defined | Header/key do ứng dụng cung cấp | Hệ thống có quy ước định tuyến riêng | Khóa không tin cậy, phân phối lệch hoặc lộ dữ liệu |

## 4. Thuật toán cân bằng tải và affinity

Load balancer có thể hỗ trợ round robin, weighted round robin, least connections, least response time hoặc các biến thể khác. Khi bật affinity, thuật toán chọn backend thường chỉ được áp dụng cho request đầu tiên hoặc khi mapping cũ không còn hợp lệ.

Ví dụ:

- Request đầu tiên được chọn bằng least connections.
- Load balancer lưu mapping client/session → backend A.
- Các request tiếp theo tiếp tục đến A dù backend B đang ít kết nối hơn.
- Khi cookie hết hạn hoặc A bị đánh dấu unhealthy, load balancer có thể chọn backend khác.

Vì vậy, sticky session có thể làm giảm hiệu quả của thuật toán cân bằng tải. Nếu một phiên tạo rất nhiều request hoặc giữ kết nối lâu, một backend có thể nhận nhiều công việc hơn các backend còn lại.

Không nên giả định affinity luôn ưu tiên hơn health check. Thông thường backend unhealthy không nên tiếp tục nhận traffic chỉ vì còn cookie sticky, nhưng hành vi chính xác cần được kiểm tra theo load balancer.

## 5. Tác động đến trạng thái phiên và trải nghiệm người dùng

### Khi request quay lại đúng backend

Nếu session state chỉ nằm trong RAM của backend A, affinity giúp request tiếp theo quay lại A và ứng dụng có thể tìm thấy session. Đây là lợi ích chính của sticky session đối với ứng dụng stateful.

Ví dụ, người dùng thêm sản phẩm vào giỏ hàng ở A. Request xem giỏ hàng tiếp theo cũng đến A, nên dữ liệu cục bộ vẫn tồn tại.

### Khi request đến backend khác

Nếu request tiếp theo đến B và B không có session state, có thể xảy ra:

- Người dùng bị yêu cầu đăng nhập lại.
- Giỏ hàng hoặc wizard state không hiển thị.
- Request bị trả lỗi 401/403/404 hoặc redirect bất thường.
- Ứng dụng tạo session mới, dẫn đến trạng thái phân tách.
- Giao dịch nhiều bước không thể tiếp tục.

Đây là dấu hiệu thường gặp khi affinity bị mất, cookie không được gửi hoặc load balancer thay backend.

### Affinity không phải cơ chế lưu trữ bền vững

Ngay cả khi request luôn quay về A, session cục bộ vẫn có thể mất khi:

- Process restart hoặc deploy phiên bản mới.
- VM reboot hoặc host replacement.
- Container bị reschedule sang node khác.
- Instance bị terminate do autoscaling hoặc lỗi.
- Backend bị đánh dấu unhealthy.
- Load balancer thay đổi mapping sau khi cookie hết hạn.
- Người dùng đổi thiết bị hoặc trình duyệt.

Sticky session giảm khả năng request đi sang máy khác trong điều kiện bình thường; nó không bảo đảm session sống sót qua mọi sự cố.

## 6. Tác động đến cân bằng tải và khả năng mở rộng

Affinity làm thay đổi phân phối request. Một số backend có thể giữ nhiều phiên đang hoạt động trong khi backend mới nhận ít phiên hơn.

### Load skew

Giả sử có 4 backend với năng lực tương đương. Round robin có thể phân phối request tương đối đều nếu request có thời lượng tương tự. Với sticky session, một nhóm client có nhiều hoạt động hoặc phiên kéo dài có thể dồn vào cùng backend.

Các nguyên nhân gây lệch:

- Một client tạo nhiều request hơn các client khác.
- Phiên có thời lượng dài hoặc workload không đồng đều.
- Source-IP affinity gom nhiều người dùng sau cùng NAT.
- Hash key có phân phối lệch.
- Backend mới chưa nhận được các phiên hiện tại.
- Kết nối WebSocket hoặc TCP dài hạn giữ backend trong thời gian lâu.

### Autoscaling và scale-in

Khi scale-out, instance mới có thể nhận phiên mới nhưng backend cũ vẫn giữ phần lớn phiên hiện tại. Vì vậy, số instance tăng không đồng nghĩa tải được tái phân phối ngay.

Khi scale-in, nếu instance đang giữ nhiều session bị terminate, session cục bộ có thể mất. Cần có quy trình drain để ngừng nhận phiên mới, cho phiên hoặc kết nối đang hoạt động kết thúc trong thời hạn hợp lý và lưu trạng thái quan trọng ở nơi bền vững.

### Thời gian drain và connection lifetime

Với HTTP keep-alive, WebSocket hoặc TCP connection dài hạn, load balancer có thể giữ kết nối với backend trong thời gian dài. Cần phối hợp:

- Connection idle timeout.
- Maximum connection lifetime nếu dịch vụ hỗ trợ.
- Deregistration delay hoặc connection draining.
- Application graceful shutdown.
- Session idle timeout và absolute timeout.
- Thời hạn cookie affinity.

Nếu thời gian cookie affinity dài hơn vòng đời instance hoặc thời gian drain, client có thể tiếp tục mang cookie trỏ đến backend đã bị loại. Load balancer cần có hành vi fallback an toàn.

## 7. So sánh sticky session với session store dùng chung

Một lựa chọn kiến trúc phổ biến là chuyển session state khỏi bộ nhớ của từng backend sang kho dùng chung. Khi đó, bất kỳ backend khỏe mạnh nào cũng có thể xử lý request nếu có session ID hợp lệ và quyền truy cập store.

~~~mermaid
flowchart LR
    C[Client] --> LB[Load balancer]
    LB --> A[Backend A]
    LB --> B[Backend B]
    LB --> D[Backend C]
    A --> S[(Shared session store)]
    B --> S
    D --> S
~~~

### Lợi ích của shared session store

- Backend có thể thay thế lẫn nhau; request không cần quay lại một instance cụ thể.
- Scale-out có thể nhận traffic mới và phân phối đều hơn.
- Backend restart hoặc failover ít làm mất session nếu store còn khả dụng.
- Rolling deployment và autoscaling đơn giản hơn.
- Có thể tách vòng đời session khỏi vòng đời VM/container.

### Chi phí và rủi ro

- Thêm network hop và latency khi đọc/ghi session.
- Session store trở thành dependency quan trọng, cần HA, capacity và monitoring.
- Nếu store quá tải hoặc mất kết nối, nhiều backend cùng bị ảnh hưởng.
- Cần xử lý consistency, expiration, serialization và schema version.
- Dữ liệu session cần encryption, access control và retention phù hợp.
- Cache eviction hoặc TTL quá ngắn có thể làm mất session trước thời hạn mong muốn.

### Khi nào chọn phương án nào?

| Tiêu chí | Sticky session + local state | Shared session store |
|---|---|---|
| Thay đổi ứng dụng | Thường ít thay đổi với ứng dụng cũ | Cần tích hợp session repository/client |
| Độ trễ đọc session | Có thể rất thấp do RAM cục bộ | Có thêm network hop |
| Scale-out | Phiên mới dễ vào node mới; phiên cũ vẫn bám node cũ | Backend mới có thể xử lý cả phiên hiện tại |
| Failover backend | Local state có thể mất | Có thể tiếp tục nếu store khả dụng |
| Scale-in/deploy | Cần drain và chấp nhận session migration/loss | Dễ drain backend hơn |
| Phụ thuộc mới | Ít hơn ở đường session | Session store cần HA và vận hành |
| Phù hợp | Ứng dụng legacy, state cục bộ khó thay đổi, workload ngắn hạn | Ứng dụng cần HA, autoscaling, rolling deploy và backend thay thế linh hoạt |

Một thiết kế khác là stateless session: backend không giữ trạng thái phiên cục bộ; client gửi token được ký hoặc mã hóa. Cách này giảm truy vấn store nhưng cần kế hoạch thu hồi token, rotation khóa, thời hạn ngắn và giới hạn dữ liệu trong token.

## 8. Thiết kế session an toàn

Session ID thường là bearer credential: ai sở hữu ID hợp lệ có thể được xem là đang giữ phiên. Vì vậy, bảo vệ session quan trọng không kém bảo vệ mật khẩu.

### Cookie attributes

Với cookie session của ứng dụng web, cân nhắc:

- **Secure:** chỉ gửi cookie qua HTTPS.
- **HttpOnly:** JavaScript phía client không đọc được cookie qua API thông thường.
- **SameSite:** giảm một số rủi ro CSRF tùy luồng điều hướng và tích hợp.
- **Path** và **Domain:** giới hạn phạm vi cookie cần thiết.
- **Max-Age** hoặc **Expires:** xác định thời hạn cookie.
- Cookie name có prefix phù hợp như __Host- khi đáp ứng yêu cầu của prefix đó.

Ví dụ response header minh họa:

~~~http
Set-Cookie: __Host-app_session=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Đây là cookie session của ứng dụng, không nhất thiết là cookie affinity của load balancer. Cấu hình cookie affinity do load balancer tạo có thể có tên và thuộc tính riêng; cần xem tài liệu dịch vụ và không tự sửa cookie do nền tảng quản lý nếu điều đó làm hỏng mapping.

### Session lifecycle

- Tạo session ID đủ ngẫu nhiên và khó đoán.
- Regenerate session ID sau đăng nhập hoặc thay đổi quyền quan trọng để giảm session fixation.
- Có idle timeout và absolute timeout phù hợp nghiệp vụ.
- Thu hồi session khi logout, đổi mật khẩu hoặc phát hiện rủi ro.
- Không đưa session ID vào URL, log, analytics hoặc referrer.
- Xoay vòng khóa ký/mã hóa và có kế hoạch chuyển tiếp khóa.
- Giới hạn dữ liệu và quyền truy cập của session store.
- Không lưu dữ liệu nhạy cảm vượt nhu cầu.

### Phân biệt cookie affinity và session authentication

Cookie affinity chỉ nên được xem như gợi ý định tuyến. Nếu client tự sửa hoặc replay cookie affinity, điều đó không được phép cấp quyền truy cập vào dữ liệu người dùng. Backend vẫn phải xác thực session/application token và kiểm tra authorization trên từng request.

## 9. Affinity trong các loại load balancer và giao thức

### Layer 7 HTTP/HTTPS load balancer

Layer 7 có thể đọc cookie, header, host và path nên hỗ trợ cookie-based affinity hoặc hash theo nội dung HTTP. Đây là nơi sticky session thường được dùng cho web application.

Cần kiểm tra TLS termination, cookie rewrite, domain/path, proxy chain và hành vi khi client không gửi cookie.

### Layer 4 TCP/UDP load balancer

Layer 4 thường không phân tích nội dung HTTP. Affinity có thể dựa vào source IP, source/destination tuple hoặc hash flow. Với TCP, một kết nối đang mở thường gắn với một backend trong vòng đời kết nối; điều đó khác với việc mọi kết nối mới của cùng một người dùng đều đến cùng backend.

### WebSocket và kết nối dài hạn

WebSocket bắt đầu bằng HTTP upgrade rồi duy trì kết nối hai chiều. Sau khi kết nối được thiết lập, load balancer thường giữ kết nối đến backend đã chọn cho đến khi đóng hoặc timeout. Affinity cho các request HTTP tiếp theo không nhất thiết điều khiển lại kết nối WebSocket đang mở.

Khi backend bị drain hoặc restart, WebSocket có thể bị ngắt và client cần reconnect. Nếu cần khôi phục trạng thái, ứng dụng nên lưu subscription, cursor hoặc trạng thái nghiệp vụ ở nơi dùng chung và thiết kế reconnect/resume.

### gRPC và streaming

gRPC có thể dùng HTTP/2 multiplexing và stream dài. Một channel có thể tái sử dụng nhiều RPC trên cùng kết nối, nên phân phối tải ở cấp connection khác với phân phối từng request. Cần xem khả năng load balancing của client, proxy và service mesh; không mặc định rằng một RPC luôn được phân phối độc lập.

## 10. Ví dụ cấu hình affinity ở mức khái niệm

Cấu hình cụ thể phụ thuộc cloud provider và sản phẩm load balancer. Ví dụ dưới đây minh họa những thuộc tính cần quyết định, không phải schema dùng trực tiếp cho mọi nền tảng.

~~~yaml
load_balancer:
  listener:
    protocol: HTTPS
    port: 443
  backend_pool:
    name: web-backends
    protocol: HTTP
    port: 8080
  session_affinity:
    enabled: true
    mode: cookie
    cookie_ttl: 1800s
  health_check:
    path: /health/ready
    interval: 10s
    unhealthy_threshold: 3
  connection_draining:
    enabled: true
    timeout: 60s
~~~

Khi thiết kế, cần trả lời:

- Affinity cookie do load balancer hay ứng dụng quản lý?
- TTL cookie là bao lâu và có đồng bộ với session idle timeout không?
- Khi backend unhealthy, load balancer có bỏ mapping cũ không?
- Khi scale-in, thời gian drain tối đa là bao lâu?
- Health check có phản ánh readiness của ứng dụng không?
- Client không có cookie sẽ được xử lý như thế nào?
- Cookie có thể bị lộ hoặc bị giả mạo để gây lệch tải không?

Không nên đặt TTL quá dài chỉ để tránh đăng nhập lại. TTL dài có thể giữ client bám backend cũ và làm chậm việc phân phối lại tải. TTL quá ngắn lại khiến session cục bộ dễ mất nếu mapping thay đổi trước khi session hết hạn.

## 11. Ví dụ NGINX với sticky routing

NGINX có nhiều cách triển khai affinity tùy phiên bản và module được cài. Ví dụ dưới đây dùng ip_hash để minh họa source-IP affinity cơ bản:

~~~nginx
upstream app_backends {
    ip_hash;

    server 10.20.1.11:8080;
    server 10.20.1.12:8080;
    server 10.20.1.13:8080;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    location / {
        proxy_pass http://app_backends;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
~~~

ip_hash minh họa cách ánh xạ theo IP client. Nếu nhiều client cùng đi qua NAT, chúng có thể cùng được ánh xạ đến một backend. Khi NGINX đứng sau một proxy khác, cần cấu hình trusted proxy và real client IP đúng cách; không tin cậy tùy tiện header X-Forwarded-For do client có thể tự gửi.

Đây là ví dụ học tập, cần điều chỉnh TLS, health checking, trusted proxy và phiên bản/module trước khi dùng production. Cấu hình này không minh họa cookie-based affinity.

## 12. Ví dụ: chuyển ứng dụng từ local session sang shared store

Một ứng dụng web cũ chạy ba VM. Session được lưu trong RAM của từng VM; load balancer dùng cookie affinity 30 phút. Khi VM A deploy lại, các người dùng đang gắn với A bị mất giỏ hàng tạm thời.

Có thể xử lý theo hai giai đoạn:

**Giai đoạn 1 — giảm rủi ro khi vẫn dùng local session**

- Bật affinity và xác minh cookie được gửi trên các request.
- Đặt health check đúng và connection draining khi deploy.
- Không terminate instance trước khi drain hoàn tất.
- Cảnh báo số phiên đang hoạt động trên mỗi backend.
- Chấp nhận rõ ràng rằng host failure vẫn có thể làm mất session cục bộ.
- Không lưu dữ liệu nghiệp vụ quan trọng chỉ trong RAM session.

**Giai đoạn 2 — chuyển sang shared session store**

- Tạo session repository dùng Redis hoặc kho phù hợp có HA.
- Ứng dụng ghi session vào store và chỉ giữ cache cục bộ có giới hạn.
- Đặt TTL và serialization schema có phiên bản.
- Dùng TLS, authentication và network policy cho session store.
- Chạy thử trên một nhóm instance canary.
- So sánh latency, error rate, store hit, connection pool và chi phí.
- Khi các backend đều đọc được session dùng chung, giảm hoặc tắt affinity theo kế hoạch.

~~~mermaid
flowchart TD
    A[Ứng dụng hiện tại: local session] --> B[Thêm shared session repository]
    B --> C[Canary: một nhóm backend]
    C --> D{Session đọc/ghi ổn định?}
    D -- Không --> E[Rollback và điều tra]
    D -- Có --> F[Chuyển dần traffic]
    F --> G[Kiểm thử scale, deploy và failover]
    G --> H[Giảm hoặc tắt sticky affinity]
~~~

Không nên tắt affinity trước khi tất cả backend đều có thể đọc cùng trạng thái phiên. Trong giai đoạn chuyển đổi, cần xử lý session cũ còn nằm trong RAM; có thể chờ hết TTL, migrate có kiểm soát hoặc yêu cầu người dùng đăng nhập lại theo kế hoạch nghiệp vụ.

## 13. Đo lường và giám sát session affinity

Dashboard cần cho biết affinity có giúp ứng dụng ổn định hay đang tạo lệch tải.

Metric có thể theo dõi:

- Số request và tỷ lệ request được route theo affinity.
- Số session hoặc client đang gắn với từng backend.
- Request rate, CPU, memory và connection count theo backend.
- Phân phối request/connection giữa các backend.
- Số lần affinity cookie không hợp lệ, hết hạn hoặc không được gửi (nếu có telemetry).
- Số lần backend bị đánh dấu unhealthy và mapping phải thay đổi.
- Session lookup miss hoặc session not found ở ứng dụng.
- Session store latency, error rate, connection usage và eviction.
- Thời gian drain và số kết nối còn hoạt động khi scale-in/deploy.
- WebSocket reconnect và session resume success rate.

Không đưa session ID, user ID hoặc cookie thô vào label metric hay log. Chỉ ghi nhận trạng thái tổng hợp hoặc mã định danh đã được bảo vệ khi thực sự cần điều tra.

### Dấu hiệu cần chú ý

- Một backend có request rate hoặc CPU cao hơn nhiều backend khác: có thể load skew.
- Backend mới gần như không nhận request trong khi backend cũ vẫn bận: sticky session đang giữ client cũ.
- Session miss tăng sau deploy hoặc scale-in: mapping bị thay đổi hoặc local state bị mất.
- Latency tăng khi session store chậm: dependency mới đang ảnh hưởng request.
- Connection draining kéo dài: client giữ kết nối hoặc session quá lâu.
- Nhiều client cùng IP bị dồn một backend: source-IP affinity có thể bị ảnh hưởng bởi NAT/proxy.

## 14. Kiểm thử affinity và tình huống lỗi

Kiểm thử trong staging hoặc một nhóm canary trước khi bật rộng.

| Kịch bản | Cách thử | Kết quả cần xác minh |
|---|---|---|
| Request liên tiếp | Gửi nhiều request với cùng cookie | Các request được route đến cùng backend trong thời hạn affinity |
| Không có cookie | Gửi request từ client mới hoặc xóa cookie | Load balancer chọn backend theo thuật toán mặc định |
| Cookie hết hạn | Chờ hết TTL hoặc dùng cookie thử nghiệm đã hết hạn | Mapping được tạo lại và ứng dụng vẫn xử lý đúng |
| Backend unhealthy | Dừng health endpoint hoặc loại backend khỏi pool | Traffic được chuyển sang backend khỏe; session cục bộ có hành vi đã dự kiến |
| Scale-out | Thêm backend mới | Phiên mới có thể dùng backend mới; tải cũ có thể vẫn bám backend cũ |
| Scale-in | Drain và loại một backend | Không nhận phiên mới; kết nối đang chạy được xử lý theo timeout |
| Rolling deployment | Thay phiên bản từng backend | Người dùng không mất dữ liệu quan trọng; cookie/session tương thích |
| NAT/proxy | Nhiều client thử nghiệm dùng chung source IP | Source-IP affinity có thể gom client; xác nhận tác động |
| Shared store outage | Mô phỏng session store chậm hoặc mất kết nối | Timeout, fallback và error được kiểm soát; không tạo retry storm |
| WebSocket reconnect | Ngắt backend có kết nối dài hạn | Client reconnect và khôi phục trạng thái theo thiết kế |

Kiểm thử phải xác nhận cả định tuyến và trạng thái ứng dụng. Chỉ thấy cùng backend ID chưa chứng minh session an toàn; cần kiểm tra dữ liệu phiên, quyền truy cập và khả năng phục hồi.

## 15. Chẩn đoán sự cố session affinity

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Người dùng bị đăng xuất ngẫu nhiên | Cookie không được gửi, TTL hết, backend thay đổi hoặc session local mất | Cookie attributes, load balancer mapping, deploy/restart event, session lookup |
| Một backend quá tải | Sticky session giữ nhóm client nặng hoặc source IP gom nhiều người | Request rate, session count, source IP distribution, CPU và connection |
| Scale-out nhưng tải không đều | Phiên cũ tiếp tục gắn backend cũ | Affinity TTL, session duration, backend selection và shared state |
| Deploy làm mất giỏ hàng | Session chỉ lưu trong RAM instance bị thay thế | Local session store, drain, session migration và persistent/shared storage |
| Client đổi mạng thì mất phiên | Source-IP affinity thay đổi hoặc cookie không tồn tại | Client IP, cookie, proxy/NAT và application session ID |
| Backend unhealthy vẫn bị gọi | Health check hoặc deregistration chưa đúng | Probe path, threshold, backend status và connection draining |
| Session store gây latency | Pool cạn, network chậm, eviction hoặc store quá tải | Store p95/p99, connection pool, memory, CPU và network |
| Cookie affinity có vẻ không hiệu lực | Domain/path/SameSite, TLS termination hoặc proxy rewrite | Browser devtools, response headers, request headers và LB logs |

Quy trình điều tra nên bắt đầu bằng một request mẫu có trace/correlation ID, backend ID và trạng thái session lookup. Không ghi cookie hoặc session ID thô vào ticket; nếu cần đối chiếu, dùng hash hoặc mã đã được bảo vệ theo chính sách.

## 16. Những sai lầm thường gặp

**Cho rằng sticky session bảo đảm session không mất.** Affinity chỉ định tuyến; restart, failover hoặc terminate backend vẫn có thể làm mất session local.

**Dùng source-IP affinity cho website có nhiều người dùng sau NAT.** Nhiều người có thể bị dồn vào một backend. Cookie affinity hoặc shared session store thường phù hợp hơn.

**Dùng cookie affinity làm bằng chứng đăng nhập.** Cookie định tuyến không xác thực người dùng. Ứng dụng vẫn phải kiểm tra session/token và authorization.

**Đặt affinity TTL quá dài.** Backend cũ giữ client lâu, làm scale-out và cân bằng tải kém hiệu quả.

**Tắt affinity khi session vẫn nằm cục bộ.** Request chuyển sang backend khác có thể không tìm thấy session. Chỉ giảm affinity sau khi trạng thái đã dùng chung hoặc ứng dụng stateless.

**Không drain backend khi scale-in.** Kết nối dài hạn và phiên đang hoạt động bị cắt đột ngột. Dùng deregistration delay và graceful shutdown phù hợp.

**Tăng shared store nhưng không giới hạn kết nối.** Nhiều backend có thể tạo connection storm và làm store quá tải. Thiết kế pool, timeout, cache và capacity.

**Lưu dữ liệu nhạy cảm trong cookie hoặc session không bảo vệ.** Session là mục tiêu có giá trị. Dùng HTTPS, cookie attributes, mã hóa khi cần, TTL và quyền tối thiểu.

## 17. Checklist lựa chọn và vận hành session affinity

### Thiết kế trạng thái

- [ ] Đã xác định session state nằm trong RAM, disk, shared store hay client-side token.
- [ ] Dữ liệu nghiệp vụ quan trọng không chỉ tồn tại trong session cục bộ.
- [ ] Đã đánh giá khả năng mất session khi restart, host failure hoặc reschedule.
- [ ] Có idle timeout, absolute timeout và quy trình logout/revoke.

### Thiết kế affinity

- [ ] Chọn cookie, source-IP hoặc consistent hashing theo giao thức và đặc tính client.
- [ ] Đã đánh giá ảnh hưởng của NAT, proxy và client đổi mạng.
- [ ] Affinity TTL phù hợp session lifetime và vòng đời backend.
- [ ] Health check có thể loại backend không khỏe dù còn affinity mapping.
- [ ] Đã xác định hành vi khi cookie mất, hết hạn hoặc backend bị loại.

### Scale và HA

- [ ] Có load distribution metric theo backend.
- [ ] Scale-out được kiểm thử với phiên cũ và phiên mới.
- [ ] Scale-in có connection draining và graceful shutdown.
- [ ] Backend failure không làm mất dữ liệu nghiệp vụ quan trọng.
- [ ] Shared session store (nếu dùng) có HA, timeout, capacity, encryption và monitoring.
- [ ] WebSocket/gRPC/long-lived connection có kế hoạch reconnect và resume.

### Bảo mật và quan sát

- [ ] Session cookie dùng Secure và HttpOnly; SameSite phù hợp luồng ứng dụng.
- [ ] Session ID không xuất hiện trong URL, log hoặc metric label.
- [ ] Cookie affinity không được dùng thay authentication/authorization.
- [ ] Có metric session miss, affinity distribution, backend health và store latency.
- [ ] Có kiểm thử backend unhealthy, deploy, scale và store outage.
- [ ] Có runbook và owner cho các vấn đề session/affinity.

## 18. Tự kiểm tra

1. Session state khác session ID như thế nào? Vì sao load balancer cần một khóa affinity?
2. Cookie-based affinity và source-IP affinity khác nhau ra sao khi nhiều người dùng truy cập qua cùng NAT?
3. Vì sao sticky session không bảo đảm người dùng giữ được trạng thái sau khi backend bị restart?
4. Khi bật autoscaling, affinity có thể làm backend mới nhận ít tải như thế nào?
5. Phân biệt application session cookie với load balancer affinity cookie.
6. Khi nào nên chuyển session state sang Redis hoặc shared store?
7. Vì sao cookie affinity không thể thay thế authentication và authorization?
8. Cần phối hợp những timeout nào khi drain backend có WebSocket hoặc TCP connection dài hạn?
9. Những metric nào giúp phát hiện load skew và session loss?
10. Hãy đề xuất kế hoạch chuyển một ứng dụng dùng local session sang shared session store mà không làm mất trạng thái ngoài ý muốn.

Session affinity là công cụ tương thích hữu ích khi ứng dụng còn giữ trạng thái cục bộ, nhưng nó tạo ràng buộc giữa client và backend. Khi hiểu rõ vị trí lưu session, giới hạn của từng phương pháp affinity, vòng đời cookie, health check và connection draining, đội ngũ có thể chọn thiết kế phù hợp. Với workload cần autoscaling, rolling deployment và failover linh hoạt, session store dùng chung hoặc thiết kế stateless thường giúp giảm phụ thuộc vào một instance cụ thể; dù chọn phương án nào, dữ liệu phiên vẫn cần được bảo vệ, giám sát và kiểm thử như một thành phần quan trọng của ứng dụng.
