# Cấu hình reverse proxy và load balancer cho kết nối dài hạn

RSocket thường duy trì một kết nối hai chiều trong thời gian dài. Trên một kết nối đó, client và server có thể ghép nhiều luồng request-response, request-stream, request-channel hoặc fire-and-forget. Vì vậy, cấu hình reverse proxy và load balancer cần tính đến vòng đời của cả kết nối, lưu lượng hai chiều và khả năng phục hồi khi một node ngừng phục vụ.

Điểm đầu tiên cần xác định là transport mà ứng dụng sử dụng. RSocket chạy trực tiếp trên TCP và RSocket chạy trên WebSocket có cách proxy khác nhau. TCP cần một proxy ở tầng kết nối; WebSocket bắt đầu bằng một HTTP handshake rồi chuyển thành kênh hai chiều lâu dài. Dùng nhầm cấu hình HTTP cho TCP hoặc bỏ sót các header Upgrade của WebSocket thường khiến kết nối không thể thiết lập.

~~~mermaid
flowchart LR
    C["RSocket client"]
    L4["L4 proxy / TCP load balancer"]
    L7["HTTP reverse proxy"]
    A1["RSocket node A"]
    A2["RSocket node B"]
    C -->|"RSocket frames over TCP"| L4
    C -->|"HTTP Upgrade, then WebSocket frames"| L7
    L4 --> A1
    L4 --> A2
    L7 --> A1
    L7 --> A2
~~~

## 1. Phân biệt TCP và WebSocket trước khi cấu hình

| Đặc điểm | RSocket qua TCP | RSocket qua WebSocket |
|---|---|---|
| Kết nối ban đầu | Mở socket TCP, sau đó trao đổi RSocket Setup | HTTP handshake, sau đó chuyển sang WebSocket |
| Proxy phù hợp | L4 TCP proxy, TCP mode của load balancer hoặc proxy hiểu RSocket | HTTP reverse proxy có hỗ trợ WebSocket Upgrade |
| Header HTTP Upgrade | Không sử dụng | Cần chuyển tiếp đúng |
| Dữ liệu sau khi kết nối | RSocket frames trên TCP | RSocket frames nằm trong WebSocket binary frames |
| TLS | Có thể TLS pass-through hoặc terminate rồi mã hóa lại tới backend | WSS thường được terminate ở edge hoặc chuyển tiếp TLS tới backend |

Với TCP thuần, proxy phải chuyển tiếp byte của socket tới một backend. Không thể đặt một HTTP location thông thường trước cổng TCP RSocket rồi mong proxy hiểu giao thức. Nếu muốn terminate TLS ở load balancer, listener và upstream đều phải được cấu hình theo chế độ TCP/TLS tương ứng.

Với WebSocket, client gửi một HTTP request có các header như:

~~~http
GET /rsocket HTTP/1.1
Host: rsocket.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: <random-key>
Origin: https://app.example.com
~~~

Server chấp nhận handshake bằng HTTP 101 Switching Protocols. Sau đó, kết nối trở thành WebSocket hai chiều; các frame RSocket được truyền bên trong WebSocket. Proxy phải dùng HTTP/1.1 cho kiểu handshake này và chuyển tiếp cả hai header Upgrade và Connection. Đây là các header hop-by-hop nên proxy HTTP có thể loại bỏ chúng nếu cấu hình không yêu cầu chuyển tiếp rõ ràng.

Một số hạ tầng hỗ trợ WebSocket qua HTTP/2 bằng cơ chế Extended CONNECT. Chỉ sử dụng cơ chế đó khi client, proxy và server đều hỗ trợ; cấu hình HTTP/1.1 Upgrade ở ví dụ dưới đây là lựa chọn tương thích phổ biến.

## 2. Thiết lập timeout phù hợp với kết nối dài hạn

Timeout ngắn thường là nguyên nhân khiến kết nối đang hoạt động bị ngắt sau một khoảng thời gian cố định. Cần kiểm tra timeout ở mọi lớp: client, reverse proxy, load balancer, firewall, NAT và server. Chỉ cần một lớp có idle timeout ngắn hơn các lớp còn lại là kết nối có thể bị đóng.

Phân biệt các loại timeout trước khi đặt giá trị:

| Loại timeout | Ý nghĩa | Cách chọn |
|---|---|---|
| Connect timeout | Thời gian cho phép thiết lập kết nối tới backend | Đặt ngắn, phù hợp với thời gian mở TCP/TLS trong mạng nội bộ |
| Handshake timeout | Thời gian hoàn tất HTTP/WebSocket handshake hoặc RSocket Setup | Đủ cho xác thực và khởi tạo nhưng có giới hạn để loại bỏ kết nối treo |
| Idle timeout | Thời gian không có dữ liệu trước khi đóng kết nối | Lớn hơn chu kỳ keepalive cộng thêm biên dự phòng |
| Read/send timeout | Thời gian giữa các lần đọc hoặc ghi dữ liệu theo cách định nghĩa của proxy | Kiểm tra đúng ngữ nghĩa của sản phẩm proxy; không mặc định đây là tổng thời lượng request |
| Drain timeout | Thời gian cho phép kết nối hiện hữu kết thúc khi node ngừng nhận kết nối mới | Dựa trên thời lượng phiên thực tế và chính sách reconnect |

RSocket có cơ chế KEEPALIVE ở tầng giao thức. Hai phía có thể gửi keepalive frame để xác nhận peer còn hoạt động; Setup mang thông tin về chu kỳ keepalive và thời gian tối đa chờ keepalive. Ví dụ, ứng dụng có thể bắt đầu thử nghiệm với chu kỳ 20 giây và thời gian sống 90 giây, sau đó điều chỉnh dựa trên độ trễ mạng và chính sách của hạ tầng.

Idle timeout của proxy phải dài hơn khoảng cách giữa các keepalive frame lớn nhất có thể quan sát được, cộng thêm biên cho jitter, tải cao và độ trễ. Không sao chép một con số cố định cho mọi môi trường: cần kiểm chứng proxy tính idle theo dữ liệu ở một hay cả hai chiều và keepalive có thực sự đi qua đường truyền đó hay không.

TCP keepalive của hệ điều hành và RSocket KEEPALIVE là hai cơ chế khác nhau. TCP keepalive thường được điều khiển ở tầng socket và có thể có chu kỳ mặc định rất dài. RSocket KEEPALIVE hoạt động ở tầng giao thức và có thể phát hiện peer không phản hồi theo thời gian ứng dụng đã chọn. Khi dùng WebSocket, cần đảm bảo các frame WebSocket ping/pong và RSocket keepalive không bị nhầm lẫn; chúng thuộc hai lớp giao thức khác nhau.

Không nên đặt mọi timeout thành vô hạn. Kết nối chết có thể giữ file descriptor, bộ nhớ và slot ở load balancer trong thời gian dài. Hãy chọn timeout có chủ đích, bật keepalive phù hợp và đo tỷ lệ disconnect trước khi tăng giới hạn.

## 3. Xử lý buffering và backpressure

Kết nối RSocket có thể mang dữ liệu liên tục theo cả hai chiều. Buffering quá mức ở proxy làm tăng độ trễ, tiêu thụ bộ nhớ và che giấu tình trạng consumer xử lý chậm. Với HTTP reverse proxy, tắt response buffering và request buffering trên route WebSocket nếu sản phẩm proxy áp dụng các tùy chọn đó cho đường truyền này. Sau khi WebSocket Upgrade thành công, nhiều proxy chuyển sang chế độ tunnel; hãy xác minh hành vi thực tế theo phiên bản proxy.

Không dùng proxy buffer như một hàng đợi không giới hạn. Giới hạn kích thước frame/payload, số kết nối, bộ nhớ đệm và tốc độ nhận dữ liệu. Ở tầng ứng dụng, dùng cơ chế request-N/backpressure của RSocket và Reactor để consumer yêu cầu lượng dữ liệu phù hợp với khả năng xử lý. Backpressure của RSocket không tự động bảo vệ một proxy được cấu hình để buffer vô hạn.

Khi kiểm thử, cần có trường hợp consumer chậm, payload lớn, stream kéo dài và kết nối bị ngắt giữa lúc truyền. Quan sát độ trễ, bộ nhớ, số phần tử đang chờ và hành vi hủy subscription. Với request-channel, kiểm tra cả chiều client gửi lên và chiều server gửi xuống.

## 4. Cân bằng tải và affinity

Load balancer thông thường chọn backend khi một kết nối vật lý được thiết lập. Sau khi TCP socket hoặc WebSocket Upgrade đã gắn với một node, toàn bộ các stream RSocket trên kết nối đó tiếp tục đi tới node ấy. Load balancer tầng mạng không nhìn thấy từng request-response hay từng phần tử trong request-stream để phân phối chúng sang node khác.

Điều này có ba hệ quả:

1. Thuật toán round-robin hoặc least-connections cân bằng số kết nối, không nhất thiết cân bằng số stream, số message hay CPU. Một kết nối có thể mang nhiều stream nặng trong khi kết nối khác gần như nhàn rỗi.
2. Một client chỉ mở một kết nối dài hạn sẽ không tự phân phối tải qua tất cả backend. Nếu cần tăng mức song song, cân nhắc connection pool có giới hạn ở client và đo tác động tới tài nguyên.
3. Khi client reconnect, load balancer có thể chọn node khác. Nếu trạng thái phiên RSocket chỉ nằm trong bộ nhớ của node cũ, tính năng RESUME hoặc trạng thái ứng dụng gắn với phiên có thể không khôi phục được.

Không phải hệ thống nào cũng cần sticky session. Nếu server không giữ trạng thái phiên cần thiết giữa các kết nối độc lập, phân phối kết nối mới bằng least-connections hoặc round-robin thường đủ. Nếu cần resume dựa trên trạng thái cục bộ, hãy dùng affinity theo một khóa ổn định hoặc thiết kế kho trạng thái dùng chung tương thích với cơ chế resume đang triển khai. Affinity không cứu được phiên khi node cũ bị mất hoàn toàn và trạng thái chỉ tồn tại trên node đó.

Với nhiều kết nối từ cùng một client, có thể dùng consistent hashing theo tenant hoặc client key nếu yêu cầu nghiệp vụ cần các kết nối đó về cùng node. Khóa phải được xác thực và không được lấy trực tiếp từ header tùy ý do client gửi. Kiểm thử phân phối với nhiều client và nhiều kết nối; một bài thử chỉ dùng một kết nối không thể đánh giá thuật toán cân bằng tải.

## 5. Health check và graceful connection draining

Health check cần trả lời đúng câu hỏi mà load balancer đang cần:

- TCP connect check xác nhận cổng có thể nhận kết nối, nhưng không chứng minh ứng dụng hoàn tất RSocket Setup hay xử lý request được.
- HTTP readiness endpoint có thể kiểm tra trạng thái ứng dụng và các dependency cần thiết để nhận phiên mới. Ví dụ, dùng endpoint readiness của Spring Boot Actuator nếu ứng dụng đã tích hợp và bảo vệ endpoint đúng cách.
- WebSocket handshake check xác nhận route và Upgrade hoạt động. Một handshake thành công vẫn chưa chứng minh RSocket Setup, xác thực metadata hay request handler đều hoạt động.
- Liveness check trả lời tiến trình còn sống hay không; không nên dùng liveness thay cho readiness.

Khi triển khai phiên bản mới hoặc tắt một node, thực hiện draining theo thứ tự:

1. Đánh dấu node không còn ready để load balancer ngừng đưa kết nối mới tới node đó.
2. Giữ các kết nối hiện hữu trong thời gian drain đã định. Theo dõi số kết nối còn hoạt động và thời lượng phiên.
3. Nếu nghiệp vụ yêu cầu, gửi tín hiệu bảo trì ở tầng ứng dụng để client chuẩn bị reconnect. Với WebSocket có thể thực hiện close handshake với mã phù hợp như 1001 (Going Away); với TCP thuần, đóng transport theo cách graceful mà client hiểu được. RSocket không cung cấp một frame GOAWAY chung để thay thế toàn bộ quy trình drain.
4. Hết thời gian drain, đóng các kết nối còn lại, dừng server và để client reconnect theo exponential backoff có jitter.
5. Nếu bật RSocket RESUME, kiểm tra riêng trường hợp node được chọn lại và trường hợp node cũ đã mất. Chỉ coi resume thành công khi trạng thái phiên cần thiết vẫn có thể truy cập.

Trong Kubernetes, readiness có thể loại pod khỏi Service endpoints trước khi tiến trình kết thúc. Kết hợp readiness, preStop và terminationGracePeriodSeconds sao cho thời gian chờ thực tế đủ cho chính sách drain. Không mặc định rằng việc xóa pod khỏi endpoint sẽ tự đóng các kết nối đã được proxy chuyển tới pod đó.

## 6. Giới hạn tài nguyên và bảo vệ hệ thống

Kết nối dài hạn tiêu thụ tài nguyên ngay cả khi không có message. Xác định giới hạn ở cả edge proxy và RSocket server:

| Giới hạn | Lý do cần kiểm soát |
|---|---|
| Tổng kết nối và kết nối tối đa trên mỗi IP/tenant | Tránh cạn file descriptor, socket và bộ nhớ |
| Tốc độ tạo kết nối và số handshake đồng thời | Giảm tác động của reconnect storm hoặc client lỗi |
| Thời gian hoàn tất handshake và xác thực | Loại bỏ kết nối mở dở hoặc gửi metadata chậm |
| Số stream/interaction đồng thời | Giới hạn công việc mà một kết nối có thể tạo ra |
| Kích thước frame và payload tối đa | Tránh cấp phát bộ nhớ quá lớn |
| Buffer, queue và tốc độ message | Bảo vệ consumer chậm và tránh tích tụ bộ nhớ |
| Thời gian sống tối đa nếu có yêu cầu nghiệp vụ | Hạn chế phiên tồn tại vô thời hạn và hỗ trợ luân chuyển node |

Giới hạn theo IP cần tính đến NAT, proxy phía trước và mạng doanh nghiệp: nhiều người dùng có thể cùng xuất hiện dưới một địa chỉ IP. Ưu tiên quota theo danh tính đã xác thực hoặc tenant khi có thể. Đặt giới hạn đồng thời ở edge và ứng dụng để một lớp bị cấu hình sai không khiến lớp còn lại mất khả năng bảo vệ.

Không nên retry mọi lỗi với tốc độ cao. Client cần exponential backoff, jitter và giới hạn số lần thử. Với thao tác không idempotent như một số lệnh fire-and-forget hoặc message trong channel, thiết kế idempotency key hay cơ chế xác nhận ở tầng nghiệp vụ trước khi tự động gửi lại, tránh xử lý trùng sau reconnect.

## 7. Bảo mật khi đặt proxy trước RSocket

- Dùng TLS cho kết nối bên ngoài. Với RSocket TCP, chọn TLS pass-through hoặc terminate ở proxy rồi mã hóa lại tới backend theo yêu cầu bảo mật nội bộ. Với WebSocket, dùng WSS và chỉ chuyển tiếp tới backend qua mạng tin cậy hoặc TLS nội bộ.
- Nếu cần xác thực service-to-service, cân nhắc mutual TLS giữa proxy và backend. Quản lý chứng thư, xoay vòng và kiểm tra hostname/SNI ở đúng lớp terminate TLS.
- Với WebSocket, kiểm tra Origin theo danh sách cho phép khi mô hình client cần bảo vệ khỏi trang web không được phép mở kết nối. Origin không thay thế xác thực người dùng.
- Xác thực ở handshake và/hoặc metadata RSocket theo thiết kế. Proxy HTTP chỉ nhìn thấy header của handshake; nếu TLS đã được mã hóa end-to-end, proxy không thể đọc metadata hoặc payload RSocket bên trong.
- Chỉ tin X-Forwarded-For và X-Forwarded-Proto từ proxy tin cậy. Xóa hoặc ghi đè giá trị do client tự gửi ở edge. Với TCP pass-through, dùng PROXY protocol chỉ khi cả proxy và backend được cấu hình hỗ trợ; không gửi PROXY protocol tới server không hiểu định dạng này.
- Không ghi log payload hoặc token nhạy cảm. Ghi nhận connection ID, tenant đã xác thực, địa chỉ peer đã chuẩn hóa và mã lỗi cần thiết để điều tra.

## 8. Ví dụ cấu hình Nginx

Các đoạn sau là mẫu tham khảo. Đặt block stream và http ở context cấp cao nhất của nginx.conf; cần cài Nginx có module stream nếu proxy TCP. Thay địa chỉ backend, chứng thư TLS, đường dẫn và timeout theo môi trường thật.

### 8.1. Proxy RSocket TCP ở tầng stream

~~~nginx
stream {
    upstream rsocket_tcp_nodes {
        least_conn;
        server 10.0.1.11:7000 max_fails=3 fail_timeout=10s;
        server 10.0.1.12:7000 max_fails=3 fail_timeout=10s;
    }

    server {
        listen 7000;
        proxy_pass rsocket_tcp_nodes;
        proxy_connect_timeout 5s;
        proxy_timeout 1h;
    }
}
~~~

Đoạn này chuyển tiếp TCP tới một backend được chọn khi kết nối bắt đầu. Nếu client dùng TLS, cấu hình trên có thể chuyển tiếp luồng TLS nguyên vẹn khi backend thực hiện TLS termination. Nếu muốn Nginx terminate TLS, cần cấu hình listener stream có SSL và chứng thư phù hợp, đồng thời quyết định có mã hóa lại kết nối upstream hay không. Timeout một giờ chỉ là giá trị minh họa; keepalive phải phát sinh thường xuyên hơn idle timeout này.

### 8.2. Reverse proxy cho RSocket qua WebSocket

~~~nginx
http {
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    upstream rsocket_ws_nodes {
        least_conn;
        server 10.0.1.11:8080;
        server 10.0.1.12:8080;
    }

    server {
        listen 443 ssl;
        server_name rsocket.example.com;

        # Khai báo ssl_certificate và ssl_certificate_key tại đây.

        location /rsocket {
            proxy_pass http://rsocket_ws_nodes;
            proxy_http_version 1.1;

            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

            proxy_connect_timeout 5s;
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;

            proxy_buffering off;
            proxy_request_buffering off;
        }
    }
}
~~~

Trong ví dụ này, Nginx nhận WSS ở cổng 443, chuyển tiếp HTTP/1.1 handshake tới backend và giữ đường truyền sau khi Upgrade thành công. Giá trị proxy_read_timeout và proxy_send_timeout cần lớn hơn khoảng không hoạt động dự kiến giữa các frame, có xét đến RSocket keepalive. Nếu route này dùng để phục vụ WebSocket, kiểm tra URL mapping ở server phải khớp chính xác với /rsocket.

Nếu dùng HAProxy cho TCP, frontend/backend cần ở mode tcp, chọn thuật toán như leastconn và bật health check TCP phù hợp. Với WebSocket, HAProxy thường xử lý Upgrade ở mode http và cần timeout tunnel đủ dài. Dù dùng sản phẩm nào, cần xác minh hành vi timeout, health check, drain và giới hạn kết nối bằng phiên bản đang triển khai; tên directive giữa các proxy không tương đương hoàn toàn.

## 9. Kiểm thử trước khi đưa vào production

Thực hiện kiểm thử từ phía client qua đúng hostname và load balancer sẽ được sử dụng thực tế:

1. Kiểm tra TCP reachability tới cổng RSocket. Công cụ như nc chỉ chứng minh socket có thể mở; nó không chứng minh RSocket Setup thành công.
2. Nếu TLS được bật, kiểm tra chứng thư, hostname/SNI và chuỗi tin cậy. Ví dụ, openssl s_client có thể kiểm tra TLS handshake nhưng không kiểm tra request RSocket.
3. Với WebSocket, xác nhận handshake trả về HTTP 101, route đúng và các header Upgrade/Connection được chuyển tiếp. Công cụ kiểm tra WebSocket thông thường chỉ chứng minh handshake; cần RSocket client thật để kiểm tra Setup và frame RSocket.
4. Dùng RSocket client thật để chạy request-response, request-stream, request-channel và fire-and-forget qua proxy. Xác minh metadata, xác thực và lỗi được truyền đúng.
5. Giữ kết nối lâu hơn idle timeout dự kiến, để client/server gửi keepalive và kiểm tra kết nối không bị proxy đóng ngoài ý muốn. Lặp lại với mạng có độ trễ hoặc packet loss trong giới hạn kiểm thử.
6. Tạo consumer chậm và payload lớn để quan sát backpressure, buffer, memory và giới hạn frame/payload.
7. Mở nhiều kết nối độc lập để đánh giá phân phối backend. Một kết nối dài hạn duy nhất không đủ để đánh giá cân bằng tải.
8. Đánh dấu một node unready rồi triển khai phiên bản mới. Xác nhận kết nối mới đi tới node khỏe, kết nối cũ được drain theo chính sách và client reconnect có backoff.
9. Dừng đột ngột một node để kiểm tra tình huống lỗi thật. Phân biệt reconnect thông thường với RESUME; kiểm tra trạng thái phiên và tính idempotent của thao tác được gửi lại.
10. Kiểm tra Origin, TLS/mTLS, token hết hạn, giới hạn kết nối, giới hạn payload và hành vi khi vượt quota.

## 10. Theo dõi và xử lý sự cố

Theo dõi đồng thời số liệu ở proxy và ứng dụng. Những chỉ số hữu ích gồm số kết nối đang mở theo node, số kết nối mới và reconnect, thời lượng kết nối, handshake thành công/thất bại, timeout, reset, TLS error, số stream đang chạy, request latency, số lần cancel/error, tốc độ message, kích thước payload, buffer/queue, CPU, heap và file descriptor. Với WebSocket, ghi nhận tỷ lệ handshake 101 và các phản hồi lỗi trước khi Upgrade.

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| WebSocket trả 400/426 hoặc không có 101 | Thiếu Upgrade/Connection, proxy dùng sai HTTP version, route hoặc backend không bật WebSocket |
| WebSocket trả 404 | Mapping path ở proxy và server không khớp |
| TCP mở được nhưng RSocket Setup thất bại | Sai transport, TLS mode, protocol hoặc xác thực |
| Kết nối rớt sau một khoảng thời gian gần như cố định | Idle timeout ở proxy, LB, firewall hoặc NAT; keepalive không đi qua được |
| Kết nối chỉ rớt khi server triển khai | Readiness/drain chưa đúng, termination grace period quá ngắn hoặc node bị đóng sớm |
| Một node chịu tải cao dù least-connections đang bật | Số kết nối ít, tải mỗi kết nối khác nhau hoặc client chỉ giữ một kết nối lâu dài |
| Reconnect thành công nhưng resume thất bại | Client tới node khác hoặc trạng thái resume không được chia sẻ/khôi phục |
| Stream bị trễ và bộ nhớ tăng | Buffering, queue không giới hạn, consumer chậm hoặc backpressure không được áp dụng |
| Nhiều kết nối mới thất bại cùng lúc | Reconnect storm, giới hạn connection/handshake, cạn file descriptor hoặc backend quá tải |

Khi điều tra một lần disconnect, đối chiếu timestamp và connection ID ở client, proxy và server. Ghi rõ node đã nhận kết nối, lý do đóng, thời gian kể từ frame cuối cùng và timeout hiệu lực ở từng lớp. Tránh kết luận rằng server lỗi chỉ từ một mã 502/504 ở proxy; cần kiểm tra log upstream và trạng thái node cùng thời điểm.

## 11. Checklist cấu hình vận hành

- [ ] Đã xác định transport là TCP hay WebSocket và chọn đúng loại proxy.
- [ ] WebSocket handshake có HTTP/1.1 Upgrade và chuyển tiếp đúng Upgrade/Connection.
- [ ] Idle/read/send timeout ở mọi lớp tương thích với chu kỳ RSocket keepalive và có biên dự phòng.
- [ ] Buffer, frame/payload, số kết nối, số stream và tốc độ handshake có giới hạn.
- [ ] Backpressure được kiểm tra với consumer chậm và stream dài.
- [ ] Thuật toán cân bằng tải được đánh giá ở cấp kết nối; affinity chỉ bật khi trạng thái phiên yêu cầu.
- [ ] Readiness, health check và graceful draining đã được thử trong một lần triển khai thực tế.
- [ ] Client reconnect có backoff/jitter; thao tác có thể gửi lại được bảo vệ khỏi xử lý trùng.
- [ ] TLS, Origin, xác thực, forwarded headers và log dữ liệu nhạy cảm đã được rà soát.
- [ ] Dashboard và cảnh báo bao gồm connection count, disconnect reason, timeout, handshake failure và tài nguyên node.

Một cấu hình proxy tốt giữ kết nối ổn định, phân phối kết nối mới có chủ đích và cho phép node rời hệ thống mà không làm gián đoạn mọi phiên đang hoạt động. Các giá trị timeout, giới hạn và chính sách affinity cần được xác nhận bằng tải thực tế, kiểm thử reconnect và quy trình triển khai của chính hệ thống.
