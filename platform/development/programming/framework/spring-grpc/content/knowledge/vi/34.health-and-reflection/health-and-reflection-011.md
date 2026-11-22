# Không coi port mở là service healthy

## 1. Mục tiêu

Một TCP port đang mở chỉ cho biết có tiến trình hoặc proxy đang lắng nghe và đường mạng có thể thiết lập kết nối ở mức TCP. Điều đó chưa chứng minh Spring gRPC application đã khởi tạo xong, service đã được đăng ký, dependency bắt buộc đang hoạt động hoặc RPC có thể xử lý đúng nghiệp vụ.

**Service healthy** phải được đánh giá theo khả năng thực hiện vai trò mà hệ thống mong đợi. Với gRPC, cần phân biệt ba tín hiệu:

- **Port/listener availability:** có thể kết nối tới địa chỉ và port.
- **gRPC protocol availability:** có thể thiết lập gRPC call và gọi method đã đăng ký.
- **Application readiness:** service đã sẵn sàng nhận traffic và các điều kiện bắt buộc để xử lý request đang đáp ứng.

Trong Spring gRPC, nên cung cấp gRPC Health Checking protocol, cập nhật trạng thái theo lifecycle và dependency readiness, rồi để load balancer, orchestrator hoặc client sử dụng tín hiệu đó. Không xem port-open hoặc TLS handshake là bằng chứng duy nhất rằng service healthy.

Sau bài học, bạn có thể:

- Giải thích giới hạn của TCP port check và TLS handshake.
- Phân biệt liveness, readiness và startup health.
- Triển khai gRPC Health Checking protocol với Check và Watch.
- Quản lý trạng thái NOT_SERVING và SERVING theo vòng đời Spring application.
- Đánh giá dependency health mà không tạo tải lớn hoặc restart storm.
- Thiết kế health probe và xử lý lỗi health check ở client/orchestrator.
- Kiểm thử service readiness thay vì chỉ kiểm tra port.

## 2. Port mở chứng minh được điều gì?

Khi một TCP probe kết nối thành công tới port gRPC, nó chỉ xác nhận rằng:

1. Địa chỉ có thể được định tuyến tới.
2. Có tiến trình hoặc proxy đang chấp nhận kết nối TCP.
3. Port đó chưa bị đóng hoặc firewall chặn tại thời điểm probe.

Probe này không biết:

- Spring application context đã tạo xong chưa.
- Generated gRPC service đã được đăng ký chưa.
- Handler có thể xử lý request hay đang lỗi.
- Database, cache, message broker hoặc service bắt buộc có sẵn không.
- Server có trả đúng status và response theo contract không.
- TLS identity và quyền gọi RPC có đúng không.

Ví dụ, tiến trình có thể bind port trước khi kết nối database hoàn tất. TCP probe trả success trong khi RPC cần database sẽ thất bại. Tương tự, proxy sidecar có thể tiếp tục nhận TCP connection dù application process phía sau đã dừng.

| Tín hiệu | Điều nó chứng minh | Điều nó không chứng minh |
|---|---|---|
| TCP port open | Listener nhận kết nối TCP | gRPC method hoặc nghiệp vụ hoạt động |
| TLS handshake thành công | Hai phía hoàn tất bắt tay và kiểm tra chứng thư theo cấu hình | Service đã sẵn sàng xử lý request |
| HTTP/2 connection established | Có thể thiết lập transport HTTP/2 | Method gRPC cụ thể được đăng ký |
| Một RPC bất kỳ trả OK | Method đó đã xử lý thành công một request cụ thể | Tất cả service và dependency đều healthy |
| gRPC health trả SERVING | Server báo service đang phục vụ | Mọi request tương lai chắc chắn thành công |

Health status là tín hiệu có chủ đích do application công bố. Giá trị của nó phụ thuộc vào việc application cập nhật trạng thái đúng với điều kiện readiness thực tế.

## 3. Phân biệt liveness, readiness và startup

Ba loại probe trả lời ba câu hỏi khác nhau:

| Probe | Câu hỏi | Khi thất bại, hệ thống thường làm gì? |
|---|---|---|
| Liveness | Process còn sống và có khả năng tiếp tục chạy không? | Khởi động lại process/container |
| Readiness | Instance đã đủ điều kiện nhận traffic chưa? | Tạm ngừng route traffic tới instance |
| Startup | Ứng dụng đã hoàn tất giai đoạn khởi động chưa? | Tiếp tục chờ startup hoặc restart khi hết ngưỡng |

Không đưa mọi dependency vào liveness. Nếu database tạm thời mất kết nối mà liveness cũng fail, orchestrator có thể restart tất cả instance liên tục, làm outage nặng hơn.

Readiness có thể phụ thuộc database hoặc dependency nếu thiếu chúng thì request không thể được xử lý đúng. Tuy nhiên, chỉ đưa dependency bắt buộc vào readiness. Một dependency tùy chọn nên có degraded mode hoặc fallback nếu nghiệp vụ cho phép.

Startup probe hữu ích khi Spring application cần thời gian tải cấu hình, migrate dữ liệu, khởi tạo cache hoặc đăng ký service. Trong giai đoạn này, instance chưa cần bị coi là chết chỉ vì chưa ready.

## 4. gRPC Health Checking protocol

gRPC định nghĩa một service health chuẩn trong package grpc.health.v1:

- Health/Check: unary RPC trả trạng thái hiện tại của một service.
- Health/Watch: server-streaming RPC gửi trạng thái hiện tại và các lần thay đổi tiếp theo.

Request chứa tên service. Quy ước phổ biến:

- Chuỗi rỗng biểu diễn sức khỏe tổng thể của server.
- Tên đầy đủ như catalog.v1.CatalogService biểu diễn một service cụ thể.

Tên service phải khớp với Protobuf package và service name được dùng để tạo full method path. Không dùng Java package nếu nó khác Protobuf package.

Health response có các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| UNKNOWN | Chưa xác định trạng thái |
| SERVING | Service đang sẵn sàng phục vụ |
| NOT_SERVING | Service hiện không sẵn sàng |
| SERVICE_UNKNOWN | Service được hỏi không được health server biết tới; thường xuất hiện trong Watch |

Với Check, service không biết thường được biểu diễn bằng gRPC status NOT_FOUND. Với Watch, server có thể gửi SERVICE_UNKNOWN để client biết service name không được quản lý. Client cũng phải phân biệt lỗi transport hoặc UNIMPLEMENTED khi server không triển khai health service.

Check thích hợp cho probe định kỳ. Watch thích hợp cho client hoặc control plane muốn nhận cập nhật liên tục mà không phải polling liên tục.

## 5. Đăng ký health service trong gRPC server

gRPC Java cung cấp HealthStatusManager trong artifact grpc-services. Thành phần này quản lý status và cung cấp implementation của health service chuẩn.

Dependency cần cùng release line với các thư viện gRPC Java đang dùng:

```kotlin
dependencies {
    implementation("io.grpc:grpc-services:<grpc-version>")
}
```

Thay grpc-version bằng version được quản lý tập trung trong BOM hoặc dependency constraints của dự án.

Ví dụ cấu hình manager:

```java
import io.grpc.BindableService;
import io.grpc.protobuf.services.HealthStatusManager;

@Configuration
public class GrpcHealthConfiguration {

    @Bean
    HealthStatusManager healthStatusManager() {
        return new HealthStatusManager();
    }

    @Bean
    BindableService grpcHealthService(
            HealthStatusManager healthStatusManager) {
        return healthStatusManager.getHealthService();
    }
}
```

Bean BindableService chỉ được tự động đăng ký nếu Spring gRPC starter/version của dự án hỗ trợ discovery loại bean đó. Nếu starter yêu cầu khai báo service theo registry hoặc server factory riêng, hãy đăng ký healthStatusManager.getHealthService() qua cơ chế đó. Điều quan trọng là health service phải được bind vào đúng gRPC server/port mà probe đang gọi.

Nếu server được dựng thủ công, có thể đăng ký trực tiếp:

```java
Server server = ServerBuilder.forPort(port)
        .addService(catalogService)
        .addService(healthStatusManager.getHealthService())
        .build()
        .start();
```

Không mở một port health riêng chỉ để làm probe xanh trong khi gRPC server nghiệp vụ chưa sẵn sàng, trừ khi kiến trúc chủ ý tách control plane và data plane. Nếu tách port, cần ghi rõ tín hiệu đó chứng minh phần nào của hệ thống.

## 6. Cập nhật status theo lifecycle Spring

Không nên đặt service ở SERVING ngay khi tạo HealthStatusManager. Lúc application mới khởi động, dependency hoặc service handler có thể chưa sẵn sàng.

Một trình tự điển hình:

1. Khởi tạo manager với overall status là NOT_SERVING.
2. Đặt từng service status là NOT_SERVING.
3. Khởi tạo cấu hình, service bean và dependency bắt buộc.
4. Kiểm tra các điều kiện readiness có deadline.
5. Chỉ khi sẵn sàng mới cập nhật service và overall status thành SERVING.
6. Khi bắt đầu graceful shutdown, chuyển status về NOT_SERVING trước khi ngừng nhận traffic.

Ví dụ cập nhật status:

```java
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;

public final class CatalogReadiness {

    private static final String CATALOG_SERVICE =
            "catalog.v1.CatalogService";

    private final HealthStatusManager health;

    public CatalogReadiness(HealthStatusManager health) {
        this.health = health;
    }

    public void markStarting() {
        health.setStatus("", ServingStatus.NOT_SERVING);
        health.setStatus(
                CATALOG_SERVICE, ServingStatus.NOT_SERVING);
    }

    public void markReady() {
        health.setStatus(
                CATALOG_SERVICE, ServingStatus.SERVING);
        health.setStatus("", ServingStatus.SERVING);
    }

    public void markStopping() {
        health.setStatus(
                CATALOG_SERVICE, ServingStatus.NOT_SERVING);
        health.setStatus("", ServingStatus.NOT_SERVING);
    }
}
```

HealthStatusManager.setStatus() cập nhật status mà health service công bố, bao gồm các client đang theo dõi bằng Watch. Trong ứng dụng thực tế, gọi các method này từ lifecycle coordinator có thứ tự rõ ràng. Có thể dùng ApplicationReadyEvent sau khi readiness gate đã hoàn tất và ContextClosedEvent hoặc SmartLifecycle.stop() để báo NOT_SERVING trước khi server dừng. Chọn hook phải phù hợp thứ tự khởi tạo và shutdown của starter.

Nếu server có nhiều service, không đặt tất cả thành SERVING chỉ vì một service đã sẵn sàng. Cập nhật status riêng cho từng full service name và tính overall status theo policy đã công bố.

## 7. Readiness phải phản ánh khả năng phục vụ thực tế

Một service healthy không nhất thiết có mọi dependency đều hoàn hảo. Readiness cần phản ánh những dependency bắt buộc cho các request mà instance nhận.

Ví dụ Catalog:

| Thành phần | Vai trò | Ảnh hưởng readiness |
|---|---|---|
| Catalog database | Đọc/ghi sản phẩm cốt lõi | Thường là bắt buộc |
| Cache | Tăng tốc truy vấn | Có thể degraded nếu database vẫn đáp ứng |
| Search index | Hỗ trợ tìm kiếm nâng cao | Tùy endpoint và fallback |
| Metrics exporter | Xuất số liệu | Thường không làm nghiệp vụ mất readiness |
| Recommendation service | Gợi ý liên quan | Có thể là tùy chọn |

Nếu database là bắt buộc, mất kết nối có thể chuyển Catalog sang NOT_SERVING. Nếu cache mất nhưng hệ thống có thể truy vấn database trực tiếp trong giới hạn tải, service có thể vẫn SERVING nhưng phát metric degraded.

Với service có nhiều method, một dependency có thể chỉ ảnh hưởng một phần API. Health service chuẩn chỉ công bố status theo service name, không theo từng RPC method. Nếu một method không sẵn sàng nhưng các method khác vẫn hoạt động, cân nhắc:

- Chia service theo ranh giới availability thực sự.
- Giữ service SERVING nếu phần lớn contract vẫn được đáp ứng và xử lý lỗi ở method cụ thể.
- Dùng readiness policy theo nhóm endpoint ở tầng routing nếu hạ tầng hỗ trợ.

Không đánh dấu toàn bộ server NOT_SERVING vì một tính năng tùy chọn bị lỗi nếu các chức năng cốt lõi vẫn đáp ứng được contract.

## 8. Tránh gọi dependency đồng bộ mỗi lần probe

Health probe thường được gọi lặp lại bởi orchestrator, load balancer và monitoring. Nếu mỗi Check lại mở kết nối database, chạy query nặng và gọi mọi dependency, probe có thể tạo tải đáng kể.

Thiết kế tốt hơn:

- Cập nhật readiness từ lifecycle và health state được theo dõi định kỳ.
- Dùng timeout ngắn, hữu hạn cho health check dependency.
- Cache kết quả trong một khoảng phù hợp, kèm thời điểm kiểm tra cuối.
- Giới hạn concurrency của dependency probe.
- Dùng circuit breaker hoặc state machine nếu dependency chập chờn.
- Phân biệt degraded với NOT_SERVING theo tác động nghiệp vụ.
- Không để health probe chờ vô hạn hoặc chiếm hết worker thread.

Không nên dùng một RPC health để thực hiện synthetic transaction phức tạp hoặc ghi dữ liệu vào production mỗi vài giây. Nếu cần synthetic monitoring, tách nó khỏi readiness probe và giới hạn tần suất.

## 9. Liveness không phải dependency readiness

Liveness trả lời process có thể tiếp tục chạy không. Nó nên tập trung vào lỗi nội bộ không thể tự phục hồi, ví dụ deadlock hoặc runtime bị kẹt theo tiêu chí được đo lường.

Readiness trả lời instance có nên nhận traffic không. Nó có thể phản ánh database hoặc dependency bắt buộc.

| Sự cố | Liveness | Readiness |
|---|---|---|
| Database tạm thời mất kết nối | Thường vẫn healthy | Có thể NOT_SERVING nếu DB bắt buộc |
| Cache mất nhưng có fallback | Healthy | Có thể vẫn SERVING, ghi degraded metric |
| Spring context chưa hoàn tất startup | Process vẫn sống | NOT_SERVING |
| Event loop/worker pool bị deadlock nghiêm trọng | Có thể fail theo policy | Thường không ready |
| Đang graceful shutdown | Process vẫn sống trong giai đoạn drain | NOT_SERVING |

Nếu liveness phụ thuộc database, database outage có thể khiến orchestrator restart liên tục mọi instance. Các instance vừa restart lại đồng loạt kết nối database, làm tăng tải đúng lúc dependency đang phục hồi.

## 10. Gọi Health/Check từ client

Health service có generated stub chuẩn trong gRPC Java. Ví dụ client kiểm tra Catalog:

```java
HealthGrpc.HealthBlockingStub healthStub =
        HealthGrpc.newBlockingStub(channel)
                .withDeadlineAfter(
                        500, TimeUnit.MILLISECONDS);

HealthCheckResponse response = healthStub.check(
        HealthCheckRequest.newBuilder()
                .setService("catalog.v1.CatalogService")
                .build());

boolean serving =
        response.getStatus() == ServingStatus.SERVING;
```

Đoạn code cần các class generated health từ grpc-services và import tương ứng trong io.grpc.health.v1. Health check cũng cần deadline; probe không được chờ vô hạn.

Phân biệt:

- Response SERVING: server báo service sẵn sàng.
- Response NOT_SERVING: server còn trả lời health RPC nhưng không nhận traffic nghiệp vụ.
- gRPC NOT_FOUND: health server không biết service name được hỏi.
- gRPC UNIMPLEMENTED: server không cung cấp method health tương ứng.
- UNAVAILABLE, timeout hoặc lỗi TLS: không xác minh được health endpoint; không diễn giải thành SERVING.

Nếu health RPC thất bại vì network/TLS, probe nên báo trạng thái không healthy hoặc unknown theo policy của orchestrator. Không thay lỗi đó bằng một kết quả thành công chỉ vì TCP port vẫn mở.

## 11. Dùng Health/Watch để nhận thay đổi

Watch là server-streaming RPC. Server gửi trạng thái hiện tại rồi gửi thêm mỗi khi trạng thái thay đổi:

```java
HealthGrpc.HealthStub healthStub =
        HealthGrpc.newStub(channel);

healthStub.watch(
        HealthCheckRequest.newBuilder()
                .setService("catalog.v1.CatalogService")
                .build(),
        new StreamObserver<>() {
            @Override
            public void onNext(HealthCheckResponse response) {
                updateLocalReadiness(response.getStatus());
            }

            @Override
            public void onError(Throwable error) {
                markHealthStreamUnknown(error);
            }

            @Override
            public void onCompleted() {
                markHealthStreamClosed();
            }
        });
```

Client phải xử lý việc stream bị đóng, lỗi transport và reconnect theo policy. Không coi stream đã mở một lần là bằng chứng health mãi mãi. Nếu client cần trạng thái mới nhất sau reconnect, tạo watch mới và nhận lại trạng thái hiện tại.

Watch phù hợp cho control plane hoặc client quản lý nhiều backend. Với probe đơn giản theo chu kỳ, Check thường dễ vận hành hơn. Không mở một Watch mới cho mỗi inbound request nghiệp vụ.

## 12. Tích hợp với Spring Boot Actuator

Spring Boot Actuator có health indicator và endpoint health cho HTTP management plane. gRPC Health Checking protocol là một RPC service riêng. Hai cơ chế không tự động đồng nghĩa:

- Actuator có thể báo database indicator UP nhưng gRPC service chưa đăng ký.
- gRPC Health có thể báo SERVING dù một health indicator tùy chọn đang DOWN.
- Port management HTTP mở không chứng minh gRPC listener hoạt động.

Nếu ứng dụng dùng Actuator, có thể chia sẻ một readiness coordinator hoặc health state giữa hai endpoint:

1. Các component kiểm tra dependency cập nhật trạng thái readiness nội bộ.
2. Actuator readiness group đọc trạng thái đó.
3. gRPC HealthStatusManager cũng được cập nhật từ cùng coordinator.
4. Liveness được quản lý riêng, không tự động gộp tất cả dependency health vào.

Không gọi Actuator HTTP endpoint từ chính gRPC health handler trên mỗi probe nếu hai bên cùng process. Dùng chung state/component sẽ tránh vòng gọi qua network và giảm độ trễ.

## 13. Health service và security

Health endpoint có thể tiết lộ tên service hoặc trạng thái phụ thuộc. Cần quyết định ai được gọi:

- Probe nội bộ của orchestrator có thể cần quyền truy cập đơn giản và ổn định.
- Client ngoài cluster không nhất thiết cần xem health chi tiết của mọi service.
- Không đưa thông tin nhạy cảm như hostname database, credential, stack trace hoặc chi tiết topology vào health response.
- Nếu dùng TLS/mTLS, probe phải tin cậy certificate và gửi identity phù hợp.
- Không để health service bị chặn bởi authorization policy dành cho RPC nghiệp vụ nếu orchestrator cần truy cập; nhưng cũng không mở thông tin nội bộ rộng hơn mức cần thiết.

Health status chỉ nên trả một tín hiệu gọn: SERVING hoặc NOT_SERVING cùng service name. Chi tiết nguyên nhân nên nằm trong log, metric và diagnostic endpoint được bảo vệ.

## 14. Quan sát health và tránh trạng thái sai

Health check là một phần của observability, nhưng không thay thế metric/log/trace. Nên theo dõi:

- Tỷ lệ probe trả SERVING và NOT_SERVING.
- Số lần readiness chuyển trạng thái.
- Thời gian ở trạng thái NOT_SERVING.
- Lỗi health RPC theo status code.
- Độ trễ của Check và độ ổn định của Watch.
- Dependency health và thời điểm kiểm tra gần nhất.
- Số instance bị loại khỏi traffic.

Tránh cập nhật status liên tục qua lại khi dependency chập chờn. Có thể dùng failure threshold, recovery threshold hoặc thời gian ổn định trước khi chuyển status. Tuy nhiên, hysteresis không được trì hoãn việc ngừng traffic khi service thực sự không thể xử lý request an toàn.

Status SERVING là cam kết của application. Nếu application chỉ đặt status một lần lúc startup rồi không cập nhật khi database mất kết nối, health service sẽ trả tín hiệu stale và gây hiểu nhầm.

## 15. Kiểm thử health đúng cách

### Kiểm thử status manager

Test cần xác minh service chuyển trạng thái theo lifecycle. Cách sát contract nhất là dựng in-process server có đăng ký health service, sau đó gọi Health/Check bằng generated health stub:

```java
HealthStatusManager manager = new HealthStatusManager();
manager.setStatus(
        "catalog.v1.CatalogService",
        ServingStatus.NOT_SERVING);

Server server = InProcessServerBuilder.forName(serverName)
        .directExecutor()
        .addService(manager.getHealthService())
        .build()
        .start();

ManagedChannel channel = InProcessChannelBuilder
        .forName(serverName)
        .directExecutor()
        .build();

HealthCheckResponse response = HealthGrpc
        .newBlockingStub(channel)
        .check(HealthCheckRequest.newBuilder()
                .setService("catalog.v1.CatalogService")
                .build());

assertEquals(ServingStatus.NOT_SERVING, response.getStatus());
```

Trong test hoàn chỉnh, đặt channel và server trong JUnit lifecycle hoặc try/finally, luôn shutdown và await termination. Sau đó gọi manager.setStatus(..., SERVING) và xác minh Check trả trạng thái mới.

### Kiểm thử Watch

Xác minh Watch gửi trạng thái ban đầu và các lần thay đổi sau khi manager cập nhật status. Dùng latch có timeout để chờ callback; không dùng sleep tùy tiện hoặc chờ vô hạn.

### Kiểm thử Spring integration

Khởi động Spring application context và xác minh:

- Health service được đăng ký trên đúng gRPC server.
- Trạng thái ban đầu là NOT_SERVING.
- Sau readiness gate, status chuyển SERVING.
- Khi dependency bắt buộc không healthy, status chuyển theo policy.
- Khi shutdown bắt đầu, status chuyển NOT_SERVING trước khi server ngừng nhận call.
- TCP port mở nhưng health status NOT_SERVING vẫn được probe đánh giá là chưa ready.

### Kiểm thử transport

Dùng TCP/TLS test riêng để xác minh certificate, authority, network route và proxy. Không lấy in-process test thay cho transport test vì in-process không tạo socket hoặc TLS handshake.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Port mở nhưng RPC nghiệp vụ lỗi | Chỉ dùng TCP probe | Gọi gRPC health service và kiểm tra readiness |
| Health trả SERVING ngay khi process bind port | Đặt status quá sớm | Khởi đầu NOT_SERVING, cập nhật sau readiness gate |
| Health vẫn SERVING khi database bắt buộc bị down | Status không được cập nhật theo dependency | Dùng readiness coordinator và dependency state |
| Database outage làm mọi instance restart | Liveness phụ thuộc database | Tách liveness khỏi readiness |
| Health RPC trả UNIMPLEMENTED | Chưa đăng ký health service hoặc server không hỗ trợ method | Đăng ký chuẩn health service |
| Probe hỏi sai service name và nhận NOT_FOUND | Dùng Java package hoặc tên không đúng Protobuf service | Dùng full Protobuf service name |
| Probe timeout dù server healthy | Deadline quá ngắn, worker bị nghẽn hoặc probe tạo tải | Đặt budget hợp lý và giữ health handler nhẹ |
| Watch không nhận trạng thái mới | Client xử lý stream không đúng hoặc server không cập nhật manager | Test lifecycle và reconnect |
| Health chập chờn | Dependency probe thiếu threshold/hysteresis | Ổn định trạng thái theo policy |
| Health endpoint tiết lộ topology | Response/log chứa chi tiết nội bộ | Chỉ công bố status tối thiểu, bảo vệ diagnostics |

## 17. Bài tập thực hành

**Tình huống:** Catalog gRPC server bind port 9090 ngay khi process khởi động. Spring application cần kết nối database trước khi phục vụ GetProduct. Hiện tại TCP probe báo healthy dù database chưa sẵn sàng.

Hãy thực hiện:

1. Thêm grpc-services cùng release line với gRPC Java runtime.
2. Đăng ký HealthStatusManager.getHealthService() trên cùng gRPC server với Catalog service.
3. Đặt overall và catalog.v1.CatalogService thành NOT_SERVING khi bắt đầu startup.
4. Tạo readiness coordinator theo dõi database readiness với timeout hữu hạn.
5. Chỉ chuyển Catalog và overall status thành SERVING sau khi dependency bắt buộc sẵn sàng.
6. Khi database mất khả năng phục vụ và không có fallback, chuyển status về NOT_SERVING theo policy.
7. Khi shutdown bắt đầu, chuyển status về NOT_SERVING trước khi dừng server.
8. Viết test Check cho overall và service-specific status; viết test Watch cho transition.
9. Giữ liveness độc lập với database để tránh restart storm.
10. Chạy TCP/TLS integration test riêng và chứng minh port open không đồng nghĩa health status là SERVING.

**Tiêu chí hoàn thành:** health service được đăng ký trên đúng listener; status phản ánh lifecycle và dependency readiness; service chưa ready không nhận traffic; liveness không phụ thuộc dependency tạm thời; Check/Watch có test; probe không tạo tải hoặc lộ thông tin nhạy cảm.

## 18. Ghi nhớ

TCP port open chỉ xác nhận có listener, không chứng minh Spring gRPC service đã sẵn sàng. TLS handshake và HTTP/2 connection cũng chỉ xác minh transport. Dùng gRPC Health Checking protocol với Check cho probe định kỳ và Watch cho cập nhật liên tục; quản lý status theo full Protobuf service name và overall service rỗng. Khởi đầu ở NOT_SERVING, chuyển sang SERVING sau readiness gate, rồi trở lại NOT_SERVING trước shutdown. Readiness có thể phụ thuộc dependency bắt buộc; liveness nên tập trung vào khả năng sống của process để tránh restart storm. Health handler phải nhẹ, có timeout, không tiết lộ chi tiết nội bộ và được kiểm thử qua generated health stub. Bổ sung TCP/TLS integration test cho transport; không dùng port-open làm tiêu chí healthy duy nhất.
