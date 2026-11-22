# Cấu hình gRPC server bằng properties trong Spring gRPC

Trong **SPRING_GRPC**, server được khởi tạo và cấu hình thông qua Spring Boot auto-configuration. Các properties quyết định server có được bật hay không, lắng nghe ở địa chỉ/cổng nào, dùng TLS ra sao và cách tích hợp các khả năng như reflection, health check hoặc servlet transport.

Cấu hình đúng giúp ứng dụng chạy nhất quán giữa máy phát triển, môi trường kiểm thử và production. Bài này tập trung vào prefix `spring.grpc.server.*`, cách đặt giá trị trong YAML/properties, ghi đè theo môi trường, phân biệt cổng HTTP với cổng gRPC và kiểm tra cấu hình bằng integration test.

## 1. Properties điều khiển phần nào của server?

Spring Boot dùng externalized configuration để bind giá trị từ `application.yml`, `application.properties`, biến môi trường, tham số dòng lệnh và các property source khác vào cấu hình tự động.

Với Spring gRPC, các thiết lập server nằm dưới prefix:

```text
spring.grpc.server
```

Một số property thường dùng:

| Property | Ý nghĩa |
| --- | --- |
| `spring.grpc.server.enabled` | Bật/tắt server auto-configuration |
| `spring.grpc.server.port` | Cổng của native gRPC server; giá trị `0` yêu cầu cổng động |
| `spring.grpc.server.address` | Địa chỉ mạng mà server bind; khi được đặt, có thể ưu tiên hơn cấu hình host/port |
| `spring.grpc.server.ssl.bundle` | Tên SSL bundle dùng cho TLS |
| `spring.grpc.server.ssl.client-auth` | Chính sách xác thực certificate phía client |
| `spring.grpc.server.reflection.enabled` | Bật/tắt gRPC reflection khi thư viện hỗ trợ có mặt |
| `spring.grpc.server.health.enabled` | Điều khiển việc tự cấu hình gRPC Health service |
| `spring.grpc.server.servlet.enabled` | Chọn servlet-based server trong ứng dụng web khi môi trường hỗ trợ |

Danh sách và điều kiện áp dụng cụ thể phụ thuộc phiên bản Spring Boot/Spring gRPC và transport trên classpath. Hãy kiểm tra configuration metadata của đúng starter mà dự án đang dùng; không giả định mọi phiên bản đều có cùng property.

Properties cấu hình server factory và transport. Chúng không thay thế hợp đồng `.proto`, cũng không tự triển khai nghiệp vụ RPC. Ứng dụng vẫn cần một bean `BindableService`, thường là lớp kế thừa generated `*ImplBase`.

## 2. Cấu hình cổng bằng application.yml

Ví dụ cấu hình native gRPC server:

```yaml
spring:
  grpc:
    server:
      enabled: true
      port: 9090
```

Ứng dụng sẽ khởi tạo gRPC server trên cổng `9090` nếu đang dùng native server factory phù hợp. Với môi trường container, có thể lấy cổng từ biến môi trường:

```yaml
spring:
  grpc:
    server:
      enabled: true
      port: ${GRPC_PORT:9090}
```

Nếu `GRPC_PORT` có giá trị, Spring Boot dùng giá trị đó; nếu biến không được đặt, giá trị mặc định trong placeholder là `9090`.

Cùng cấu hình trong `application.properties`:

```properties
spring.grpc.server.enabled=true
spring.grpc.server.port=9090
```

Hai dạng YAML và properties tương đương về mặt binding. Chọn một dạng nhất quán trong dự án để dễ review và vận hành.

### 2.1. Chọn địa chỉ bind

Nếu cần chỉ rõ địa chỉ mạng, có thể cấu hình `spring.grpc.server.address` theo dạng địa chỉ mà phiên bản starter hỗ trợ:

```yaml
spring:
  grpc:
    server:
      address: "0.0.0.0:9090"
```

Bind vào `0.0.0.0` cho phép server nhận kết nối qua các network interface của container/host. Ở môi trường chỉ cho phép truy cập cục bộ, cân nhắc bind vào loopback hoặc địa chỉ interface cụ thể.

Khi `address` được đặt và property này có ưu tiên trong phiên bản đang dùng, không nên đồng thời kỳ vọng `port` sẽ ghi đè phần cổng trong `address`. Hãy chọn một nguồn cấu hình rõ ràng và xác nhận địa chỉ thực tế trong startup log.

## 3. Phân biệt cổng HTTP và cổng gRPC

Một ứng dụng Spring Boot có thể chạy HTTP server cho REST, Actuator hoặc giao diện quản trị, đồng thời chạy native gRPC server trên một cổng khác.

Ví dụ:

```yaml
server:
  port: 8080

spring:
  grpc:
    server:
      port: 9090
```

Trong cấu hình native server:

- `server.port` là cổng web server của Spring Boot.
- `spring.grpc.server.port` là cổng listener gRPC.
- REST/Actuator có thể đi qua HTTP server, còn client gRPC kết nối đến listener gRPC.

Đây là hai listener độc lập. Mở cổng HTTP trong Kubernetes Service hoặc firewall không tự động mở cổng gRPC.

**Ngoại lệ quan trọng:** nếu ứng dụng chạy gRPC qua servlet container, servlet container quản lý network listener và HTTP/2. Trong chế độ này, một số native server properties như `spring.grpc.server.port` có thể không được sử dụng; cổng web `server.port` và cấu hình HTTP/2 của servlet container mới quyết định endpoint. Xác định transport mode trước khi xử lý lỗi “đã đổi port nhưng server vẫn nghe ở cổng cũ”.

## 4. Đăng ký service bean để server có endpoint

Properties có thể bật listener nhưng server chỉ có RPC nghiệp vụ khi các `BindableService` được đăng ký. Ví dụ, với service `StockService` đã sinh từ `.proto`:

```java
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.example.stock.v1.StockReply;
import vn.example.stock.v1.StockRequest;
import vn.example.stock.v1.StockServiceGrpc;

@Service
public class StockGrpcService
        extends StockServiceGrpc.StockServiceImplBase {

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> observer) {

        StockReply reply = StockReply.newBuilder()
                .setSku(request.getSku())
                .setAvailable(17)
                .build();

        observer.onNext(reply);
        observer.onCompleted();
    }
}
```

Component scan phát hiện bean này và Spring gRPC có thể bind `BindableService` vào server factory được cấu hình. Tên method và kiểu tham số phải khớp generated base class từ hợp đồng thực tế.

Nếu server mở cổng nhưng client nhận `UNIMPLEMENTED`, kiểm tra service bean có nằm trong application context và method đã được override đúng chưa. Chỉ tăng `port` hoặc đổi `address` không sửa được lỗi đăng ký RPC.

## 5. Ghi đè cấu hình theo môi trường

Không nên đóng cứng port production vào source code. Dùng profile và environment variable để cùng một artifact có thể chạy ở nhiều môi trường.

Ví dụ `application.yml`:

```yaml
spring:
  grpc:
    server:
      enabled: true
      port: 9090
```

Ví dụ `application-prod.yml`:

```yaml
spring:
  grpc:
    server:
      address: "0.0.0.0:9090"
```

Chạy với profile production:

```bash
java -jar stock-service.jar --spring.profiles.active=prod
```

Hoặc ghi đè trực tiếp bằng biến môi trường:

```bash
SPRING_GRPC_SERVER_PORT=9191
```

Tham số dòng lệnh cũng có thể ghi đè:

```bash
java -jar stock-service.jar --spring.grpc.server.port=9191
```

Spring Boot áp dụng thứ tự ưu tiên giữa các property source. Khi giá trị thực tế không như mong đợi, kiểm tra active profiles, biến môi trường của container, tham số dòng lệnh và cấu hình được nạp từ ConfigMap/secret. Đừng chỉ đọc `application.yml` rồi kết luận đó là giá trị cuối cùng.

Với Kubernetes, có thể đặt `SPRING_GRPC_SERVER_PORT` trong Deployment và khai báo đúng `containerPort`/Service `targetPort`. `containerPort` chỉ là metadata của Pod; Service/NetworkPolicy vẫn cần trỏ đúng cổng và cho phép lưu lượng.

## 6. Cấu hình TLS bằng SSL bundle

Trong môi trường production, gRPC thường cần TLS để bảo vệ dữ liệu trên đường truyền. Spring Boot cho phép khai báo SSL bundle và tham chiếu bundle đó từ gRPC server.

Ví dụ minh họa với keystore PKCS12:

```yaml
spring:
  ssl:
    bundle:
      jks:
        grpc-server:
          keystore:
            location: "classpath:tls/server.p12"
            password: ${GRPC_KEYSTORE_PASSWORD}
            type: PKCS12

  grpc:
    server:
      port: 9090
      ssl:
        bundle: grpc-server
        client-auth: none
```

`grpc-server` là tên bundle do ứng dụng đặt; property `spring.grpc.server.ssl.bundle` tham chiếu đúng tên này. Mật khẩu lấy từ secret hoặc biến môi trường, không commit giá trị thật vào repository.

Nếu cần mutual TLS (mTLS), cấu hình `client-auth` theo chính sách được hỗ trợ, ví dụ `require`, và khai báo trust material phù hợp để server xác minh certificate client. Chỉ đặt `client-auth` mà thiếu truststore/CA phù hợp sẽ khiến handshake thất bại.

Một số điểm cần kiểm tra:

- Certificate còn hạn, SAN phù hợp hostname mà client dùng.
- Server có private key và certificate chain đúng.
- Client trust đúng CA của server.
- Nếu bật mTLS, server trust CA cấp certificate client.
- Cấu hình plaintext của test không bị đưa sang production.

Nếu ứng dụng chạy qua servlet transport, TLS thường được cấu hình ở servlet container/web server. Khi đó SSL bundle của native gRPC server có thể không điều khiển listener servlet.

## 7. Reflection và Health service

gRPC Reflection cho phép công cụ như grpcurl khám phá service descriptor trên server. gRPC Health cung cấp RPC chuẩn để probe trạng thái server/service.

Ví dụ tắt reflection:

```yaml
spring:
  grpc:
    server:
      reflection:
        enabled: false
```

Reflection service thường cần thư viện `grpc-services` có mặt trên classpath để auto-configuration đăng ký nó. Nếu không có dependency này, đổi property không thể tự tạo implementation.

Health service cũng phụ thuộc khả năng tích hợp của starter và dependency tương ứng. Khi dùng health check cho Kubernetes, phân biệt:

- **Liveness:** tiến trình có còn hoạt động để tiếp tục chạy không.
- **Readiness:** service đã sẵn sàng nhận traffic chưa.
- **gRPC Health:** trạng thái health được công bố qua giao thức gRPC.

Không cấu hình readiness luôn `SERVING` nếu ứng dụng chưa kết nối database hoặc dependency thiết yếu. Khi cần kiểm soát trạng thái service, cập nhật health manager theo lifecycle và trạng thái nghiệp vụ thực tế.

## 8. Thời gian shutdown và xử lý request đang chạy

Khi ứng dụng dừng hoặc được rolling update, gRPC server cần thời gian để hoàn tất các RPC đang xử lý. Spring gRPC có property cho graceful shutdown; tên property và cấu trúc duration cần được xác nhận theo phiên bản starter.

Khi cấu hình grace period:

- Chọn thời gian đủ cho RPC thông thường hoàn tất.
- Client vẫn cần deadline để request không treo vô hạn.
- Ứng dụng cần xử lý cancellation và ngừng nhận công việc mới khi shutdown.
- Readiness nên chuyển sang trạng thái không nhận traffic trước khi process kết thúc.
- Không chọn thời gian quá dài nếu nền tảng triển khai có termination grace period ngắn hơn.

Tổng thời gian chờ của nền tảng, Spring application shutdown và gRPC server phải tương thích. Nếu Kubernetes buộc kill process trước khi gRPC hoàn tất graceful shutdown, request đang chạy vẫn có thể bị ngắt.

## 9. Kiểm thử cấu hình server bằng cổng động

Trong integration test, dùng port `0` để hệ điều hành chọn cổng trống. Điều này tránh xung đột khi nhiều test chạy đồng thời:

```yaml
spring:
  grpc:
    server:
      port: 0
```

Với phiên bản Spring Boot cung cấp `@LocalGrpcServerPort`, có thể lấy cổng đã bind trong test:

```java
@SpringBootTest(properties = "spring.grpc.server.port=0")
class StockGrpcServerTest {

    @LocalGrpcServerPort
    int grpcPort;

    @Test
    void serverBindsToAnAvailablePort() {
        assertTrue(grpcPort > 0);
    }
}
```

Nếu dùng annotation trên, import annotation từ gói test support tương ứng với phiên bản Spring Boot/Spring gRPC của dự án. Với phiên bản chưa cung cấp annotation này, dùng API test server hoặc factory phù hợp để lấy địa chỉ listener thực tế.

Để kiểm tra RPC qua network thật, tạo channel trỏ tới `localhost` và `grpcPort`, gọi generated stub, rồi đóng channel trong `finally` hoặc `@AfterEach`. Chỉ dùng `usePlaintext()` trong test server không TLS; với TLS test, cấu hình trust certificate tương ứng.

## 10. Khi nào properties là đủ, khi nào cần Java customization?

Dùng properties cho các giá trị triển khai thường thay đổi giữa môi trường: enable/disable, port, address, SSL bundle và các tính năng server đã được starter expose.

Khi cần tinh chỉnh transport hoặc hành vi chưa có property tương ứng, Spring gRPC cung cấp extension point như `ServerBuilderCustomizer` cho server builder. Ví dụ, một yêu cầu giới hạn inbound message size có thể cần customizer tùy transport và version API.

Quy tắc lựa chọn:

- Nếu có property được tài liệu hóa, ưu tiên property để cấu hình rõ ràng từ môi trường.
- Nếu cần logic có điều kiện hoặc API builder chuyên sâu, dùng bean customization.
- Không tự đặt một key `spring.grpc.server.*` tùy ý rồi kỳ vọng auto-configuration bind nó.
- Nếu tự tạo `@ConfigurationProperties` cho ứng dụng, dùng prefix riêng của ứng dụng để tránh nhầm với property do starter sở hữu.

## 11. Chẩn đoán lỗi cấu hình phổ biến

| Triệu chứng | Kiểm tra |
| --- | --- |
| Client không kết nối được | Port/address thực tế, bind interface, firewall, Kubernetes Service và transport |
| Đổi `server.port` nhưng gRPC không đổi cổng | Native server dùng `spring.grpc.server.port`; kiểm tra servlet mode |
| Server mở cổng nhưng RPC trả `UNIMPLEMENTED` | `BindableService` bean, component scan, method override và service name |
| Port cấu hình không có hiệu lực | Active profile, env var, command-line args và `spring.grpc.server.address` có ưu tiên |
| TLS handshake thất bại | SSL bundle, private key, trust chain, hostname và client-auth |
| Reflection không hoạt động | `grpc-services` dependency và `spring.grpc.server.reflection.enabled` |
| Test thỉnh thoảng chiếm cùng port | Dùng port `0` và lấy port được bind thực tế |
| Shutdown làm request đang chạy bị ngắt | Grace period, client deadline và termination grace period của nền tảng |

Trong quá trình điều tra, ghi nhận property source đang hoạt động và startup log. Nếu có Spring Boot Actuator, endpoint `configprops` có thể giúp xem cấu hình đã bind; chỉ bật và bảo vệ endpoint này theo chính sách bảo mật vì nó có thể tiết lộ thông tin cấu hình.

## 12. Bài tập thực hành

1. Cấu hình `spring.grpc.server.port=9090` trong YAML và xác nhận listener gRPC khởi động.
2. Chạy HTTP server ở `8080`, gRPC server ở `9090`; xác nhận hai cổng phục vụ đúng giao thức.
3. Ghi đè cổng bằng `SPRING_GRPC_SERVER_PORT` và tham số dòng lệnh; kiểm tra giá trị hiệu lực.
4. Chạy với profile `prod` và cấu hình địa chỉ bind phù hợp môi trường container.
5. Đăng ký một bean kế thừa generated `StockServiceGrpc.StockServiceImplBase`; gọi RPC để xác nhận service được bind.
6. Dùng port `0` trong integration test và lấy cổng thực tế bằng test support của phiên bản đang dùng.
7. Cấu hình SSL bundle cho native server; xác minh handshake bằng client tin cậy.
8. Bật reflection khi có `grpc-services`, sau đó tắt bằng property và xác nhận hành vi thay đổi.
9. Thử graceful shutdown trong khi có RPC đang chạy; đối chiếu grace period với deadline và termination grace period.
10. Tạo bảng cấu hình cho local, test và production, ghi rõ property nào được ghi đè từ environment.

### Ghi nhớ

**Properties cấu hình cách gRPC server được khởi tạo và vận hành trong từng môi trường.** Dùng `spring.grpc.server.*` cho native server, phân biệt nó với `server.port` của web server, quản lý giá trị qua profile/environment và kiểm tra giá trị hiệu lực. TLS, reflection, health và shutdown chỉ hoạt động khi transport, dependency và phiên bản starter hỗ trợ. Sau khi cấu hình, xác minh listener, service bean và một RPC thực tế bằng integration test.

## Tài liệu tham khảo

- [Spring Boot Reference — gRPC](https://docs.spring.io/spring-boot/reference/io/grpc.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring gRPC Reference — Server](https://docs.spring.io/spring-grpc/reference/server.html)
