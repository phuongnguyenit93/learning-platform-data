# Cấu hình máy chủ TCP độc lập qua spring.rsocket.server

## Mục tiêu bài học

Spring Boot có thể khởi động một RSocket server TCP độc lập cùng với ứng dụng. Server lắng nghe trên một cổng TCP riêng, nhận các request RSocket và định tuyến chúng tới handler Spring. Cách triển khai này phù hợp khi service Java cần giao tiếp realtime hoặc service-to-service mà không đi qua HTTP/WebSocket.

Sau bài này, bạn có thể:

- Phân biệt cổng HTTP của Spring Boot với cổng TCP của RSocket server.
- Thêm dependency cần thiết để Spring Boot tự cấu hình RSocket server.
- Cấu hình transport TCP và port bằng spring.rsocket.server.
- Viết handler bằng @MessageMapping để nhận request RSocket.
- Kết nối client bằng RSocketRequester qua TCP.
- Kiểm tra server đã bind đúng địa chỉ và port.
- Triển khai TCP endpoint trong môi trường container hoặc mạng nội bộ.

## Máy chủ TCP độc lập là gì?

Một ứng dụng Spring Boot có thể đồng thời cung cấp HTTP endpoint và RSocket endpoint. Hai endpoint này có thể sử dụng hai cổng khác nhau:

~~~mermaid
flowchart TB
    A[Spring Boot application]
    A --> H[HTTP server]
    A --> R[RSocket TCP server]
    H --> HP[HTTP port 8080]
    R --> RP[RSocket port 7000]
    C1[HTTP client] --> HP
    C2[RSocket client] --> RP
~~~

Ví dụ:

- HTTP server lắng nghe ở port 8080 để cung cấp REST API, health endpoint hoặc trang quản trị.
- RSocket server lắng nghe ở port 7000 để nhận request-response, fire-and-forget, request-stream và request-channel.

Cụm từ **độc lập** có nghĩa RSocket TCP listener có transport và cổng riêng. Nó không phải endpoint WebSocket được nâng cấp từ HTTP server. Client RSocket TCP mở kết nối TCP trực tiếp đến host và port của RSocket server.

Cổng HTTP được cấu hình bằng server.port. Cổng RSocket được cấu hình bằng spring.rsocket.server.port. Thay đổi một thuộc tính không tự động thay đổi thuộc tính còn lại.

## Thêm dependency RSocket cho Spring Boot

Với Maven, thêm starter RSocket vào ứng dụng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
~~~

Nếu dự án đã dùng Spring Boot parent hoặc dependency management, để phiên bản starter được quản lý đồng bộ theo phiên bản Spring Boot của dự án. Không trộn tùy ý các phiên bản Spring Framework, RSocket và Reactor khác nhau.

Starter cung cấp các thành phần cần thiết để Spring Boot tự cấu hình RSocket server và tích hợp message handler. Ứng dụng vẫn cần transport phù hợp cho TCP; cấu hình server và dependency phải tương thích với phiên bản Spring Boot đang sử dụng.

Không cần tự tạo Netty server thủ công trong trường hợp thông thường. Spring Boot có thể tạo RSocket server từ cấu hình externalized và các handler được khai báo trong application context.

## Cấu hình bằng application.yml

Cấu hình tối thiểu để mở RSocket TCP server trên port 7000:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

Hai thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| spring.rsocket.server.transport | Chọn transport cho RSocket server; đặt tcp để mở TCP listener độc lập |
| spring.rsocket.server.port | Port TCP mà RSocket server bind và lắng nghe |

Với server độc lập, port là cấu hình bắt buộc. transport có giá trị mặc định là tcp trong Spring Boot; khai báo rõ transport giúp cấu hình dễ đọc và tránh nhầm với WebSocket.

Có thể đặt thêm địa chỉ bind nếu cần giới hạn interface mạng:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      address: 127.0.0.1
      port: 7000
~~~

Khi bind vào 127.0.0.1, chỉ các tiến trình có thể truy cập loopback trên cùng môi trường mạng mới kết nối được. Khi chạy trong container, bind loopback bên trong container thường khiến client ở container hoặc máy khác không thể truy cập. Hãy chọn địa chỉ bind theo topology mạng và chính sách bảo mật của môi trường.

Nếu cần nhận kết nối từ các interface của container hoặc máy chủ, cấu hình địa chỉ phù hợp với môi trường triển khai, đồng thời giới hạn truy cập bằng firewall, security group hoặc network policy.

### Cấu hình bằng application.properties

Cấu hình tương đương ở dạng properties:

~~~properties
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
~~~

Chỉ chọn một nguồn cấu hình chính cho cùng một môi trường để tránh khó xác định giá trị cuối cùng. Spring Boot có thể ghi đè cấu hình theo thứ tự ưu tiên của property source, ví dụ biến môi trường, tham số dòng lệnh hoặc file cấu hình profile.

## Phân biệt TCP với WebSocket

Spring Boot hỗ trợ nhiều transport RSocket. Với bài này, mục tiêu là TCP độc lập.

| Đặc điểm | TCP | WebSocket |
|---|---|---|
| Cấu hình transport | tcp | websocket |
| Cách client kết nối | TCP socket trực tiếp | WebSocket handshake qua HTTP |
| Cổng thường dùng | Cổng TCP riêng của service | Có thể dùng cổng HTTP hoặc cổng riêng |
| Client phù hợp | Java service, ứng dụng native có TCP | Trình duyệt và client hỗ trợ WebSocket |
| Mapping path | Không dùng HTTP path | Có thể cấu hình mapping path |
| Proxy/hạ tầng | Cần cho phép TCP tới port RSocket | Cần hỗ trợ HTTP Upgrade/WebSocket |

Với TCP, không cấu hình mapping-path để thay cho route RSocket. Route được gửi trong metadata theo hợp đồng RSocket, rồi được ánh xạ tới handler như @MessageMapping.

Trong ứng dụng WebFlux, Spring Boot có thể gắn RSocket WebSocket vào web server hiện có khi cấu hình mapping-path và transport là websocket, đồng thời không khai báo port RSocket độc lập. Bài này khai báo port và transport tcp nên server được khởi động như một listener riêng. Kiểu tích hợp WebSocket này cần Reactor Netty.

Không thể dùng URL HTTP thông thường như http://host:7000 để gọi RSocket TCP. Client phải dùng RSocket transport tương ứng.

## Tạo handler nhận request

Spring Messaging cho phép ánh xạ route RSocket vào method bằng @MessageMapping. Ví dụ server cung cấp route inventory.lookup:

~~~java
package com.example.realtime;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

record InventoryRequest(String sku) {}

record InventoryView(
    String sku,
    int available,
    String warehouse
) {}

@Controller
class InventoryController {

    private final InventoryService inventoryService;

    InventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @MessageMapping("inventory.lookup")
    Mono<InventoryView> lookup(InventoryRequest request) {
        return inventoryService.find(request.sku());
    }
}
~~~

Trong ví dụ:

- inventory.lookup là route logic mà client dùng để chọn handler.
- InventoryRequest là payload data được deserialize thành object Java.
- Mono<InventoryView> biểu diễn một kết quả bất đồng bộ.
- Spring RSocket message handler quản lý việc gọi method và chuyển kết quả thành response.

Route RSocket không phải URL path của HTTP controller. Không cần gắn @RestController hoặc @GetMapping cho method xử lý RSocket này.

Nếu service cần phát dữ liệu liên tục, handler có thể trả Flux:

~~~java
@MessageMapping("inventory.watch")
Flux<InventoryView> watch(InventoryWatchRequest request) {
    return inventoryService.watch(request.sku());
}
~~~

Đây là request-stream: client gửi một request ban đầu và nhận nhiều response. Việc chọn kiểu tương tác phụ thuộc vào kiểu dữ liệu mà handler trả về và cách client gọi route.

## Tạo ứng dụng Spring Boot

Một class khởi động thông thường:

~~~java
package com.example.realtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RealtimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(RealtimeApplication.class, args);
    }
}
~~~

Không cần thêm annotation riêng để bật một TCP listener nếu starter và cấu hình RSocket server đã được Spring Boot auto-configuration hỗ trợ. Đảm bảo controller nằm trong package được component scan và các dependency của handler được đăng ký thành bean.

Ví dụ service:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class InventoryService {

    Mono<InventoryView> find(String sku) {
        return Mono.just(
            new InventoryView(sku, 25, "HCM-01")
        );
    }
}
~~~

Đây là dữ liệu minh họa. Trong ứng dụng thật, service nên gọi repository hoặc nguồn dữ liệu phù hợp và giữ pipeline reactive nếu I/O hỗ trợ non-blocking.

## Kết nối từ client bằng RSocketRequester

Client Java có thể dùng RSocketRequester để kết nối TCP tới host và port mà server đang lắng nghe:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class InventoryClient {

    private final RSocketRequester requester;

    InventoryClient(RSocketRequester.Builder requesterBuilder) {
        this.requester = requesterBuilder.tcp("localhost", 7000);
    }

    Mono<InventoryView> lookup(String sku) {
        return requester
            .route("inventory.lookup")
            .data(new InventoryRequest(sku))
            .retrieveMono(InventoryView.class);
    }
}
~~~

Client chọn route inventory.lookup, gửi InventoryRequest và nhận một response được giải mã thành InventoryView.

RSocketRequester duy trì kết nối/session để thực hiện nhiều tương tác. Trong ứng dụng thực tế, hãy tạo và quản lý requester theo vòng đời phù hợp, đóng kết nối khi ứng dụng dừng và xử lý lỗi khi server không sẵn sàng.

Không tạo requester mới cho từng request nếu kiến trúc cần tái sử dụng một kết nối lâu dài. Việc mở quá nhiều connection có thể làm tăng chi phí socket, handshake, buffer và tài nguyên phía server.

## Kiểm tra server đã bind thành công

Khi ứng dụng khởi động, kiểm tra log startup để xác nhận RSocket server đã bind đúng port. Nếu port đã được tiến trình khác sử dụng, server có thể không khởi động được hoặc application context thất bại.

Một số bước kiểm tra:

1. Xác nhận profile Spring Boot đang dùng đúng file cấu hình.
2. Xác nhận spring.rsocket.server.transport có giá trị tcp.
3. Xác nhận spring.rsocket.server.port là port dự kiến.
4. Kiểm tra địa chỉ bind có cho phép client truy cập hay không.
5. Kiểm tra port có bị chiếm bởi tiến trình khác không.
6. Dùng client RSocket thử gọi route đã khai báo.

Có thể dùng lệnh hệ điều hành để kiểm tra socket đang lắng nghe, ví dụ trên Linux:

~~~bash
ss -lntp
~~~

Trên Windows:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 7000
~~~

Lệnh này chỉ xác nhận có listener trên port. Nó không chứng minh RSocket SETUP thành công hoặc route nghiệp vụ hoạt động. Cần một client RSocket thực hiện kết nối và gửi request để kiểm tra end-to-end.

## Cấu hình port theo môi trường

Không nên hard-code port khác nhau trong nhiều file cấu hình. Có thể dùng placeholder để đọc port từ biến môi trường:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: ${RSOCKET_PORT:7000}
~~~

Trong môi trường chạy:

~~~bash
RSOCKET_PORT=7000
~~~

Trên Windows PowerShell:

~~~powershell
$env:RSOCKET_PORT = "7000"
~~~

Giá trị mặc định 7000 được dùng khi biến môi trường không tồn tại. Với môi trường staging và production, nên quản lý port trong cấu hình triển khai hoặc biến môi trường để tránh khác biệt giữa các máy.

Nếu ứng dụng đồng thời có HTTP server:

~~~yaml
server:
  port: 8080

spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

Hai listener có thể chạy đồng thời trong cùng ứng dụng. Hãy mở cả hai cổng trong cấu hình network nếu client cần truy cập từ bên ngoài, và chỉ công khai endpoint cần thiết.

## Triển khai trong Docker và Kubernetes

Khi chạy trong container, cần phân biệt port mà process bind bên trong container với port được publish hoặc expose ra ngoài.

Ví dụ Docker:

~~~bash
docker run -p 7000:7000 my-rsocket-service
~~~

Lệnh này ánh xạ TCP port 7000 trên host tới port 7000 trong container. Ứng dụng bên trong container cần bind vào interface có thể nhận lưu lượng từ network container, không chỉ loopback.

Với Kubernetes, Service cần khai báo port TCP tương ứng:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory-rsocket
spec:
  selector:
    app: inventory-rsocket
  ports:
    - name: rsocket
      protocol: TCP
      port: 7000
      targetPort: 7000
~~~

RSocket client trong cluster có thể kết nối qua DNS của Service, ví dụ inventory-rsocket:7000. Cần bảo đảm NetworkPolicy, firewall và service mesh (nếu có) cho phép TCP traffic. Không phải mọi HTTP ingress hoặc API gateway đều tự động hỗ trợ RSocket TCP.

## Bảo mật endpoint TCP

Một listener TCP mở trên network có thể được truy cập bởi các client có đường mạng tới nó. Không nên coi việc dùng port riêng là cơ chế bảo mật.

Hãy xác định:

- Client nào được phép kết nối tới port RSocket.
- Cách xác thực peer hoặc thông tin xác thực ở tầng RSocket.
- Quyền truy cập cho từng route và từng loại thao tác.
- Có cần TLS cho kết nối TCP hay không.
- Firewall, security group và network policy cần cho phép những nguồn nào.
- Cách xoay vòng credential và xử lý credential hết hạn.

Nếu bật TLS hoặc cấu hình xác thực, sử dụng API và property phù hợp với phiên bản Spring Boot/RSocket đang chạy. Không sao chép cấu hình SSL của HTTP server rồi giả định nó tự áp dụng cho RSocket TCP listener. Hai listener có thể có cấu hình bảo mật riêng.

Không ghi token, mật khẩu hoặc payload nhạy cảm vào log. Kiểm tra quyền trong handler hoặc lớp service theo danh tính đã được xác thực; route không phải cơ chế authorization.

## Xử lý lỗi khởi động và kết nối

Một số tình huống thường gặp:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Application không khởi động | Port bị chiếm hoặc cấu hình transport không hợp lệ | Kiểm tra log bind, port và property theo profile |
| Client connection refused | Server chưa lắng nghe hoặc sai host/port | Kiểm tra listener, container port mapping và firewall |
| TCP kết nối được nhưng SETUP thất bại | Hai phía không tương thích hoặc lỗi setup/security | Kiểm tra MIME type, phiên bản, TLS và cấu hình protocol |
| SETUP thành công nhưng route không được tìm thấy | Sai route hoặc handler không được component scan | Kiểm tra route metadata và @MessageMapping |
| Client timeout | Handler chậm, server quá tải hoặc mạng có vấn đề | Kiểm tra log, latency, thread/event loop và downstream |
| Chỉ truy cập được từ trong container | Bind address hoặc port publish chưa đúng | Kiểm tra địa chỉ bind và network mapping |

Phân biệt lỗi ở từng lớp giúp tránh thay đổi cấu hình ngẫu nhiên. Connection refused xảy ra trước khi RSocket xử lý route; lỗi route chỉ xuất hiện sau khi kết nối/session đã được thiết lập.

## Kiểm thử tích hợp TCP

Một kiểm thử tích hợp nên khởi động ứng dụng với cấu hình TCP, tạo client RSocketRequester tới port của server, gửi request và kiểm tra response.

Ví dụ luồng kiểm thử về mặt logic:

~~~java
Mono<InventoryView> result = requester
    .route("inventory.lookup")
    .data(new InventoryRequest("SKU-42"))
    .retrieveMono(InventoryView.class);

StepVerifier.create(result)
    .expectNextMatches(view ->
        view.sku().equals("SKU-42")
            && view.available() >= 0
    )
    .verifyComplete();
~~~

Kiểm thử cần xác nhận cả ba điều:

- TCP listener thực sự nhận được kết nối.
- RSocket SETUP thành công.
- Route được định tuyến tới handler và trả về payload đúng.

Ngoài trường hợp thành công, hãy kiểm tra port sai, server dừng, route không tồn tại, payload không hợp lệ và timeout. Nếu dùng port động trong test, hãy lấy port được cấp thực tế từ cơ chế khởi động test của ứng dụng; không giả định cổng cố định luôn trống.

## Checklist triển khai

Trước khi đưa RSocket TCP server vào môi trường dùng chung, hãy trả lời:

1. Starter RSocket có được khai báo và đồng bộ phiên bản Spring Boot không?
2. spring.rsocket.server.transport đã đặt là tcp chưa?
3. spring.rsocket.server.port có đúng với port mà client sẽ dùng không?
4. Địa chỉ bind có phù hợp với máy local, container hoặc cluster không?
5. HTTP port và RSocket port đã được phân biệt rõ chưa?
6. Handler @MessageMapping nằm trong component scan và route đã thống nhất với client chưa?
7. Firewall, Docker port mapping hoặc Kubernetes Service đã mở đúng TCP port chưa?
8. TLS, xác thực và authorization được cấu hình cho endpoint RSocket chưa?
9. Có health/observability phù hợp để theo dõi kết nối và lỗi handler không?
10. Integration test đã kiểm tra TCP, SETUP và route end-to-end chưa?

Với spring.rsocket.server.transport=tcp và spring.rsocket.server.port, Spring Boot có thể mở một RSocket TCP listener độc lập bên cạnh HTTP server. Khi quản lý đúng port, địa chỉ bind, handler, network policy và bảo mật, service Java có thể cung cấp giao tiếp RSocket realtime trực tiếp cho các client phù hợp.

## Tài liệu tham khảo

- [Spring Boot Reference: RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Boot 3.5: Common Application Properties — RSocket](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)

