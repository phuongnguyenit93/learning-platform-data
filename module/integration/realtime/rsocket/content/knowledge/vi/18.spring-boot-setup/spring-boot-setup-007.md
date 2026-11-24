# Phân biệt cổng RSocket độc lập với cổng HTTP của ứng dụng

Một ứng dụng Spring Boot có thể cung cấp API HTTP và endpoint RSocket trong cùng một tiến trình. Tuy nhiên, cổng HTTP và cổng RSocket không phải lúc nào cũng là một. Cách chúng được mở phụ thuộc vào transport mà RSocket sử dụng.

Với RSocket qua TCP, ứng dụng thường mở một listener TCP riêng bằng spring.rsocket.server.port, bên cạnh cổng web do server.port cấu hình. Với RSocket qua WebSocket, endpoint RSocket được gắn vào web server hiện có, dùng chung cổng HTTP và được phân biệt bằng một đường dẫn WebSocket.

Hiểu rõ hai mô hình này giúp cấu hình đúng client, firewall, Docker, Kubernetes, reverse proxy và môi trường triển khai.

## 1. Hai loại cổng trong một ứng dụng Spring Boot

server.port là cổng của embedded web server mà Spring Boot sử dụng để nhận HTTP request. Ví dụ, controller REST có thể được truy cập tại http://localhost:8080/api/orders.

spring.rsocket.server.port là cổng listener của RSocket server khi transport được cấu hình là TCP. Client RSocket kết nối trực tiếp tới host và cổng này, ví dụ localhost:7000.

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| server.port | Cổng HTTP/HTTPS của web server | 8080 |
| spring.rsocket.server.transport | Chọn transport cho RSocket server | tcp hoặc websocket |
| spring.rsocket.server.port | Cổng TCP riêng của RSocket server | 7000 |
| spring.rsocket.server.mapping-path | Đường dẫn WebSocket endpoint khi dùng transport WebSocket | /rsocket |

server.port và spring.rsocket.server.port thuộc hai listener khác nhau khi RSocket chạy qua TCP. Chúng có thể cùng nằm trong một ứng dụng, nhưng cần được mở và định tuyến riêng ở tầng mạng.

## 2. Mô hình TCP: HTTP và RSocket dùng hai cổng độc lập

Khi cấu hình spring.rsocket.server.transport=tcp, Spring Boot khởi tạo RSocket TCP server trên cổng được chỉ định bởi spring.rsocket.server.port. Web server HTTP vẫn sử dụng server.port.

Ví dụ cấu hình trong application.properties:

~~~properties
# Web server nhận REST API và các HTTP request
server.port=8080

# RSocket server mở một TCP listener riêng
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
~~~

Kiến trúc lúc này có hai đường vào:

~~~mermaid
flowchart LR
    HC[HTTP client] -->|HTTP :8080| WEB[Spring Boot web server]
    RC[RSocket client] -->|TCP :7000| RS[RSocket TCP server]
    WEB --> APP[Business services]
    RS --> APP
~~~

Ví dụ, cùng một service nghiệp vụ có thể được gọi từ hai adapter:

- REST controller nhận HTTP request trên cổng 8080.
- RSocket controller nhận tương tác RSocket trên cổng 7000.

Hai adapter có thể gọi chung service, repository và logic nghiệp vụ. Việc dùng chung code không làm hai cổng trở thành một. HTTP client vẫn phải gọi web server; RSocket client vẫn phải kết nối tới RSocket listener.

### Client kết nối tới đúng cổng

Client HTTP sử dụng URL của web server:

~~~java
String url = "http://localhost:8080/api/orders";
~~~

Client RSocket sử dụng host và cổng TCP của RSocket server:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .connectTcp("localhost", 7000)
    .block();
~~~

Nếu client gọi RSocket vào cổng 8080, kết nối có thể bị từ chối hoặc nhận dữ liệu không đúng giao thức vì cổng đó đang chờ HTTP. Tương tự, gửi HTTP request tới cổng 7000 không làm RSocket server xử lý request như một REST endpoint.

### Khi nào dùng TCP riêng?

Mô hình này phù hợp khi client là service backend hoặc ứng dụng Java có thể mở TCP trực tiếp tới server. Nó cũng phù hợp khi nhóm vận hành muốn tách chính sách mạng, giới hạn truy cập và khả năng mở rộng của lưu lượng realtime khỏi lưu lượng HTTP.

Đổi lại, hạ tầng phải cho phép kết nối TCP tới cổng RSocket. Firewall, security group, load balancer, Docker port mapping và Kubernetes Service đều cần khai báo cổng này nếu client ở ngoài network namespace tương ứng.

## 3. Mô hình WebSocket: RSocket dùng chung cổng web server

RSocket cũng có thể chạy trên WebSocket. Trong mô hình Spring Boot thông thường, WebSocket endpoint được đăng ký trên web server hiện có. Vì vậy, HTTP và RSocket WebSocket có thể dùng chung cổng server.port.

Ví dụ:

~~~properties
# Web server nhận HTTP và WebSocket Upgrade
server.port=8080

# RSocket sử dụng WebSocket transport
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
~~~

Client HTTP có thể gọi REST endpoint như http://localhost:8080/api/orders. Client RSocket dùng WebSocket URI ws://localhost:8080/rsocket. Cùng cổng 8080, nhưng đường dẫn và giao thức handshake giúp web server phân biệt các request.

~~~mermaid
flowchart TD
    H[HTTP client] -->|HTTP :8080 /api/orders| W[Spring Boot web server]
    R[RSocket client] -->|WebSocket Upgrade :8080 /rsocket| W
    W -->|REST route| REST[HTTP controller]
    W -->|RSocket WebSocket endpoint| RS[RSocket message handling]
    REST --> APP[Business services]
    RS --> APP
~~~

Trong mô hình này không cần mở thêm một cổng TCP RSocket riêng. RSocket frame được truyền bên trong kết nối WebSocket sau khi HTTP Upgrade thành công.

### Client kết nối qua WebSocket

~~~java
import java.net.URI;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
    .connectWebSocket(URI.create("ws://localhost:8080/rsocket"))
    .block();
~~~

Khi triển khai HTTPS, dùng wss:// và cấu hình TLS cho web server:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .connectWebSocket(URI.create("wss://api.example.com/rsocket"))
    .block();
~~~

/rsocket là mapping path của WebSocket endpoint, không phải route nghiệp vụ RSocket. Ví dụ route orders.status vẫn được gửi trong metadata của payload sau khi WebSocket đã được nâng cấp và phiên RSocket đã được thiết lập.

## 4. Phân biệt mapping path với route RSocket

Đây là hai khái niệm dễ bị nhầm khi dùng WebSocket:

| Thành phần | Ví dụ | Được dùng ở đâu? | Ý nghĩa |
|---|---|---|---|
| WebSocket mapping path | /rsocket | HTTP handshake/Upgrade | Chọn endpoint WebSocket mang RSocket |
| RSocket route | orders.status | Metadata của frame RSocket | Chọn handler nghiệp vụ sau khi phiên RSocket hoạt động |
| HTTP path | /api/orders | HTTP request | Chọn REST controller |

Ví dụ một client kết nối tới ws://localhost:8080/rsocket, sau đó gửi request tới route orders.status. Phần /rsocket giúp web server chọn đúng WebSocket endpoint. Route orders.status giúp RSocket message handler chọn phương thức nghiệp vụ.

Vì vậy, thay đổi spring.rsocket.server.mapping-path cần cập nhật URI kết nối WebSocket ở client và cấu hình proxy tương ứng. Thay đổi route @MessageMapping cần cập nhật metadata route mà client gửi; không nhất thiết thay đổi URL WebSocket.

## 5. Có thể bật cả TCP và WebSocket cùng lúc không?

Thuộc tính spring.rsocket.server.transport chọn transport cho RSocket server được Spring Boot auto-configure trong application context. Cấu hình thông thường chọn một transport cho server đó:

- Chọn tcp để có listener RSocket riêng.
- Chọn websocket để gắn RSocket vào web server.

Không nên khai báo hai giá trị transport cùng lúc trong cùng một thuộc tính hoặc giả định một cấu hình auto-configuration sẽ tự mở cả hai listener. Nếu hệ thống cần đồng thời TCP cho backend và WebSocket cho trình duyệt, có thể cân nhắc:

1. Tạo hai ứng dụng hoặc hai deployment riêng, mỗi ứng dụng dùng một transport.
2. Tạo thêm RSocket server/transport bằng cấu hình Java tùy chỉnh, quản lý riêng lifecycle, port, codec và bảo mật.
3. Đặt một gateway hoặc adapter phù hợp để tiếp nhận WebSocket và chuyển tiếp tới RSocket TCP backend.

Lựa chọn nào phù hợp phụ thuộc phiên bản Spring Boot, loại web server và yêu cầu vận hành. Khi tự cấu hình nhiều listener, cần bảo đảm chúng không bind trùng cổng và có cơ chế đóng tài nguyên khi ứng dụng dừng.

## 6. Cấu hình cổng trong Docker

Khi chạy ứng dụng trong container, cổng bên trong container và cổng được publish ra host là hai khái niệm khác nhau. Với mô hình TCP riêng, ví dụ:

~~~properties
server.port=8080
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
~~~

Container cần lắng nghe cả hai cổng. Khi chạy Docker, có thể publish chúng độc lập:

~~~bash
docker run --name order-service \
  -p 8080:8080 \
  -p 7000:7000 \
  order-service:latest
~~~

Mapping 8080:8080 đưa HTTP traffic từ host tới web server trong container. Mapping 7000:7000 đưa TCP traffic RSocket tới listener RSocket. Nếu chỉ publish 8080, REST API có thể hoạt động nhưng client RSocket bên ngoài host không thể kết nối trực tiếp tới cổng 7000.

Với mô hình WebSocket, nếu RSocket dùng chung web server port 8080, thường chỉ cần publish cổng web:

~~~bash
docker run --name order-service \
  -p 8080:8080 \
  order-service:latest
~~~

Client truy cập REST qua HTTP và RSocket qua WebSocket path /rsocket trên cùng cổng. Chỉ publish port không tự cấu hình firewall của máy chủ hoặc security group ở cloud; các lớp mạng đó vẫn phải cho phép lưu lượng cần thiết.

## 7. Cấu hình Kubernetes Service

Với RSocket TCP độc lập, Kubernetes Service cần khai báo cả cổng HTTP và RSocket nếu client bên ngoài pod cần truy cập cả hai:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: order-service
spec:
  selector:
    app: order-service
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
    - name: rsocket
      port: 7000
      targetPort: 7000
      protocol: TCP
  type: ClusterIP
~~~

Service port 80 chuyển tới HTTP listener 8080 trong pod. Service port 7000 chuyển tới RSocket TCP listener 7000. Các service backend trong cluster có thể kết nối tới DNS name của service và port tương ứng.

Với RSocket WebSocket chia sẻ web server, Service chỉ cần port HTTP:

~~~yaml
ports:
  - name: http
    port: 80
    targetPort: 8080
    protocol: TCP
~~~

Ingress hoặc gateway HTTP có thể định tuyến tới cùng service và chuyển tiếp WebSocket Upgrade nếu được cấu hình hỗ trợ. Với TCP RSocket, cần một cơ chế expose TCP phù hợp như Service type LoadBalancer, NodePort hoặc TCP proxy; HTTP Ingress thông thường không tự chuyển tiếp giao thức RSocket TCP thô.

## 8. Firewall, load balancer và reverse proxy

Trong mô hình TCP riêng, hạ tầng phải cho phép kết nối TCP tới RSocket port. Hãy kiểm tra:

- Server bind đúng interface và port, không chỉ bind vào loopback nếu client nằm ngoài container hoặc máy chủ.
- Firewall và security group cho phép nguồn client truy cập cổng RSocket.
- Load balancer hỗ trợ TCP forwarding và giữ kết nối lâu dài.
- Health check được cấu hình phù hợp với loại listener; HTTP health check không thay thế kiểm tra RSocket session.

Trong mô hình WebSocket, reverse proxy phải hỗ trợ HTTP Upgrade, chuyển tiếp các header cần thiết và duy trì kết nối hai chiều. Cần kiểm tra idle timeout, giới hạn kết nối, TLS termination và path /rsocket.

Đừng giả định proxy xử lý HTTP request ngắn cũng tự động phù hợp với một kết nối realtime sống lâu. Timeout quá ngắn có thể đóng WebSocket khi ứng dụng không gửi dữ liệu trong một khoảng thời gian.

## 9. Bảo mật cho hai mô hình cổng

Với HTTP, TLS thường được cấu hình trên web server hoặc reverse proxy. Với RSocket TCP độc lập, cần cấu hình TLS cho listener TCP nếu dữ liệu đi qua mạng không tin cậy. Hai listener có thể có chính sách chứng thư, xác thực và firewall khác nhau.

Với RSocket WebSocket, dùng wss:// để mã hóa kết nối WebSocket bằng TLS của web server. Nếu TLS kết thúc tại reverse proxy, cần đánh giá bảo vệ chặng từ proxy tới ứng dụng. Việc dùng chung cổng HTTP không đồng nghĩa RSocket tự động được xác thực hoặc phân quyền.

Trong cả hai mô hình, ứng dụng vẫn phải xác thực peer và kiểm tra quyền truy cập route. Không xem việc kết nối thành công tới cổng TCP hoặc hoàn tất WebSocket Upgrade là bằng chứng người dùng được phép gọi nghiệp vụ.

## 10. Chẩn đoán khi kết nối sai cổng

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| REST API hoạt động nhưng RSocket TCP connection refused | Chưa mở spring.rsocket.server.port hoặc port chưa publish | Kiểm tra transport tcp, port listener, Docker/Kubernetes và firewall |
| RSocket client kết nối tới server.port nhưng thất bại | Nhầm cổng HTTP với cổng RSocket TCP | Dùng spring.rsocket.server.port trong connectTcp(...) |
| HTTP request gửi tới RSocket TCP port bị lỗi | Cổng đó không phục vụ HTTP | Gửi HTTP tới server.port |
| WebSocket handshake trả 404 | Mapping path sai hoặc proxy chưa chuyển tiếp path | Kiểm tra mapping-path và URI client |
| WebSocket handshake không trả 101 | Proxy, TLS hoặc Upgrade headers không đúng | Kiểm tra reverse proxy và web server |
| WebSocket kết nối được nhưng route không tồn tại | Nhầm mapping path với route RSocket | Kiểm tra metadata route và @MessageMapping |
| Chạy local được nhưng container không kết nối được | Chỉ bind loopback hoặc chưa publish port | Kiểm tra bind address và port mapping |

Một quy trình chẩn đoán hiệu quả:

1. Xác định RSocket đang dùng TCP hay WebSocket.
2. Đọc server.port, spring.rsocket.server.transport, spring.rsocket.server.port hoặc mapping-path.
3. Xác nhận listener thực sự đang mở ở đúng địa chỉ và cổng.
4. Kiểm tra client dùng đúng API: connectTcp(host, port) hoặc connectWebSocket(uri).
5. Kiểm tra Docker, Kubernetes, firewall và proxy có chuyển tiếp đúng cổng/path.
6. Khi transport đã kết nối, mới kiểm tra RSocket SETUP, metadata và route nghiệp vụ.

## 11. Checklist triển khai theo môi trường

| Môi trường | HTTP | RSocket TCP | RSocket WebSocket |
|---|---|---|---|
| Local development | localhost:8080 | localhost:7000 | ws://localhost:8080/rsocket |
| Docker | Publish 8080 | Publish 7000 riêng | Publish web port 8080 |
| Kubernetes nội bộ | Service HTTP port | Service TCP port riêng | Dùng HTTP Service port và mapping path |
| Qua reverse proxy | HTTP host/path | TCP forwarding riêng | WebSocket Upgrade qua host/path |
| TLS | HTTPS | TLS trên TCP transport | wss:// |

Trước khi phát hành, hãy kiểm tra client cấu hình theo địa chỉ của môi trường đích, không hard-code localhost cho môi trường container hoặc cluster. Có thể dùng biến môi trường hoặc cấu hình profile Spring để thay đổi host, port và URI mà không sửa mã nguồn.

## 12. Kết luận

server.port cấu hình cổng HTTP của web server. Khi RSocket chạy qua TCP, spring.rsocket.server.port cấu hình một listener TCP riêng. Khi RSocket chạy qua WebSocket, endpoint được gắn vào web server và dùng chung server.port, còn spring.rsocket.server.mapping-path xác định đường dẫn Upgrade.

Hãy phân biệt rõ host/port của transport với mapping path WebSocket và route nghiệp vụ RSocket. Cấu hình đúng từ Spring Boot tới client, Docker, Kubernetes và proxy sẽ giúp tránh lỗi kết nối sai cổng và triển khai realtime ổn định hơn.
