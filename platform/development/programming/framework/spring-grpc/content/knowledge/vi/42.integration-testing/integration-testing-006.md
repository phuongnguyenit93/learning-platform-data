# Kiểm thử health check

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích mục đích của gRPC Health Checking Protocol và hai RPC Check/Watch.
- Đăng ký health service vào cùng gRPC server với các service nghiệp vụ.
- Quản lý trạng thái sức khỏe toàn server và từng service bằng HealthStatusManager.
- Viết integration test qua channel thật để kiểm tra trạng thái SERVING/NOT_SERVING.
- Kiểm thử thay đổi trạng thái qua Watch và xử lý service không tồn tại.
- Phân biệt health/readiness với liveness và trạng thái của tiến trình.
- Cập nhật health state khi ứng dụng khởi động, mất dependency và shutdown.

## 1. Health check giải quyết vấn đề gì?

Một gRPC server có thể mở port và chấp nhận kết nối nhưng chưa sẵn sàng xử lý nghiệp vụ. Ví dụ, Spring context đã khởi động nhưng database pool chưa kết nối, cache chưa warm up hoặc service phụ thuộc chưa sẵn sàng. Ngược lại, một service có thể bị lỗi riêng trong khi các service khác trên cùng server vẫn hoạt động.

Health check cung cấp một giao thức chuẩn để client, load balancer hoặc hệ thống điều phối hỏi server có sẵn sàng phục vụ hay không. Với **SPRING_GRPC**, health status cần phản ánh khả năng xử lý RPC thực tế của từng service và của toàn server.

Health check không thay thế monitoring, alerting hoặc kiểm tra sâu mọi dependency. Nó là tín hiệu phục vụ quyết định nhận traffic. Một health check tốt phải nhanh, có ý nghĩa rõ ràng và được cập nhật khi trạng thái ứng dụng thay đổi.

## 2. Giao thức gRPC Health Checking

gRPC định nghĩa service chuẩn trong package **grpc.health.v1**:

- **Check** là unary RPC: client hỏi trạng thái hiện tại của một service.
- **Watch** là server-streaming RPC: server gửi trạng thái ban đầu và các thay đổi tiếp theo khi trạng thái đổi.

Request mang tên service đầy đủ. Ví dụ **acme.catalog.v1.CatalogService** là tên service Protobuf, không phải tên Java class hoặc tên method. Chuỗi rỗng đại diện cho trạng thái tổng thể của server.

Các trạng thái chính:

| Trạng thái | Ý nghĩa |
| --- | --- |
| **SERVING** | Service sẵn sàng nhận và xử lý request. |
| **NOT_SERVING** | Service hiện không nên nhận traffic. |
| **UNKNOWN** | Trạng thái chưa xác định hoặc chưa được cung cấp. |
| **SERVICE_UNKNOWN** | Được dùng trong Watch khi service được yêu cầu không được health service biết đến. |

Với Check, service không tồn tại thường được biểu diễn bằng gRPC status **NOT_FOUND**. Với Watch, giao thức có trạng thái **SERVICE_UNKNOWN** để client nhận biết tên service không được đăng ký trong health registry. Nếu server không cài health service, client có thể nhận **UNIMPLEMENTED**.

## 3. Phân biệt health service với service nghiệp vụ

Health service là một gRPC service độc lập, có service name **grpc.health.v1.Health**. Nó được đăng ký vào cùng server với service nghiệp vụ:

~~~text
gRPC server
  ├── acme.greeting.v1.GreetingService
  ├── acme.catalog.v1.CatalogService
  └── grpc.health.v1.Health
        ├── Check
        └── Watch
~~~

Client gọi Health.Check hoặc Health.Watch qua cùng endpoint và cùng ManagedChannel như các service khác. Health service không tự biết database hoặc dependency của ứng dụng đang khỏe; ứng dụng phải cập nhật trạng thái dựa trên readiness policy của mình.

Health service cũng không tự bảo vệ endpoint khỏi client không được phép. Nếu hệ thống yêu cầu health endpoint chỉ dành cho load balancer hoặc monitoring agent, áp dụng network policy hoặc authorization interceptor phù hợp.

## 4. Thêm grpc-services và HealthStatusManager

Trong gRPC Java, health implementation có trong artifact **grpc-services**. Dùng phiên bản tương thích với các dependency gRPC còn lại của dự án, tốt nhất quản lý tập trung bằng BOM/version alignment.

Với Maven, dependency thường có dạng sau; phiên bản nên được quản lý bởi gRPC BOM của dự án:

~~~xml
<dependency>
    <groupId>io.grpc</groupId>
    <artifactId>grpc-services</artifactId>
</dependency>
~~~

**HealthStatusManager** giữ trạng thái của server và cung cấp service implementation để đăng ký:

~~~java
import io.grpc.protobuf.services.HealthStatusManager;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;

HealthStatusManager healthStatusManager = new HealthStatusManager();

Server server = NettyServerBuilder.forPort(0)
    .addService(greetingService)
    .addService(catalogService)
    .addService(healthStatusManager.getHealthService())
    .build()
    .start();

healthStatusManager.setStatus("", ServingStatus.SERVING);
healthStatusManager.setStatus(
    "acme.greeting.v1.GreetingService",
    ServingStatus.SERVING);
healthStatusManager.setStatus(
    "acme.catalog.v1.CatalogService",
    ServingStatus.SERVING);
~~~

Đoạn mã minh họa server tự quản lý. Trong Spring gRPC, HealthStatusManager nên là bean có vòng đời gắn với server. Nếu starter đã auto-configure health service, hãy dùng API cấu hình của starter và không đăng ký thêm một health service thứ hai.

Đặt trạng thái tổng thể bằng service name rỗng và đặt trạng thái riêng cho từng service cần theo dõi. Không dùng tên class Java; dùng full service name trong Protobuf.

## 5. Đưa health server vào Spring test context

Nếu starter chưa tự quản lý health service, có thể tạo một fixture test chứa các service nghiệp vụ và health service. Fixture nhận cùng một HealthStatusManager bean để test thay đổi status trong khi server đang chạy:

~~~java
final class HealthTestGrpcServer {
    private final List<BindableService> services;
    private final HealthStatusManager health;
    private volatile Server server;

    HealthTestGrpcServer(
            List<BindableService> services,
            HealthStatusManager health) {
        this.services = List.copyOf(services);
        this.health = health;
    }

    synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }
        ServerBuilder<?> builder = NettyServerBuilder.forPort(0);
        services.forEach(builder::addService);
        builder.addService(health.getHealthService());
        try {
            server = builder.build().start();
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot start gRPC health test server", ex);
        }
    }

    int port() {
        Server current = server;
        if (current == null || current.isShutdown()) {
            throw new IllegalStateException("gRPC server is not running");
        }
        return current.getPort();
    }

    synchronized void stop() {
        Server current = server;
        server = null;
        if (current == null) {
            return;
        }
        current.shutdown();
        try {
            if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                current.shutdownNow();
            }
        } catch (InterruptedException ex) {
            current.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Đăng ký fixture và manager trong test configuration:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class GrpcHealthTestConfiguration {
    @Bean
    HealthStatusManager healthStatusManager() {
        return new HealthStatusManager();
    }

    @Bean(initMethod = "start", destroyMethod = "stop")
    HealthTestGrpcServer healthTestGrpcServer(
            GreetingServiceImpl greeting,
            CatalogServiceImpl catalog,
            HealthStatusManager health) {
        return new HealthTestGrpcServer(
            List.of(greeting, catalog), health);
    }
}
~~~

Spring gọi init method sau khi inject dependency và destroy method khi context đóng. Fixture bind port động và đăng ký health service đúng một lần. Nếu starter đã đăng ký health service trên server của nó, bỏ fixture này và dùng cơ chế cấu hình/port accessor do starter cung cấp; không khởi động hai server cho cùng test.

## 6. Quản lý health status trong Spring

Một cách tổ chức đơn giản là inject HealthStatusManager vào thành phần quản lý readiness. Khi các dependency thiết yếu sẵn sàng, chuyển service sang SERVING; khi shutdown bắt đầu hoặc dependency quan trọng mất khả năng phục vụ, chuyển sang NOT_SERVING.

~~~java
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.protobuf.services.HealthStatusManager;
import org.springframework.stereotype.Component;

@Component
final class GrpcReadiness {
    private static final String GREETING =
        "acme.greeting.v1.GreetingService";
    private static final String CATALOG =
        "acme.catalog.v1.CatalogService";

    private final HealthStatusManager health;

    GrpcReadiness(HealthStatusManager health) {
        this.health = health;
    }

    void markReady() {
        health.setStatus(GREETING, ServingStatus.SERVING);
        health.setStatus(CATALOG, ServingStatus.SERVING);
        health.setStatus("", ServingStatus.SERVING);
    }

    void markCatalogUnavailable() {
        health.setStatus(CATALOG, ServingStatus.NOT_SERVING);
    }

    void markShuttingDown() {
        health.setStatus("", ServingStatus.NOT_SERVING);
        health.setStatus(GREETING, ServingStatus.NOT_SERVING);
        health.setStatus(CATALOG, ServingStatus.NOT_SERVING);
    }
}
~~~

Đây là ví dụ điều phối trạng thái; các method cần được gọi từ lifecycle/event tương ứng của ứng dụng. Chỉ gọi markReady sau khi các điều kiện readiness thật sự thỏa mãn. Không đặt tất cả service SERVING ngay khi constructor chạy nếu dependency vẫn đang khởi tạo.

Với Spring, có thể nối việc cập nhật vào application event hoặc lifecycle component sau khi dependency sẵn sàng. Khi context đóng, cập nhật NOT_SERVING trước khi server ngừng nhận traffic nếu server lifecycle cho phép thứ tự đó.

## 7. Một server, nhiều trạng thái service

Nếu Greeting và Catalog dùng dependency khác nhau, trạng thái của chúng có thể khác:

| Sự kiện | Greeting | Catalog | Tổng server |
| --- | --- | --- | --- |
| Khởi động xong mọi dependency | SERVING | SERVING | SERVING |
| Catalog database mất kết nối | SERVING | NOT_SERVING | Theo policy của hệ thống |
| Dependency dùng chung không sẵn sàng | NOT_SERVING | NOT_SERVING | NOT_SERVING |
| Shutdown bắt đầu | NOT_SERVING | NOT_SERVING | NOT_SERVING |

Trạng thái tổng thể là quyết định của ứng dụng. Nếu một service quan trọng mất khả năng phục vụ nhưng các service khác vẫn đáp ứng, có thể giữ server tổng thể SERVING và chỉ đánh dấu service bị ảnh hưởng NOT_SERVING. Nếu endpoint chỉ được coi là sẵn sàng khi mọi service đều hoạt động, tổng thể phải NOT_SERVING.

Hãy định nghĩa policy rõ ràng thay vì tự động suy ra trạng thái tổng thể từ một service bất kỳ. Health check không thay thế việc định tuyến theo service name; client cần hỏi đúng service mà nó định gọi.

## 8. Kiểm thử Check qua channel TCP

Integration test nên gọi health service qua cùng server/transport mà ứng dụng sử dụng. Ví dụ dưới đây giả định server fixture đã đăng ký HealthStatusManager và expose port động:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.health.v1.HealthCheckRequest;
import io.grpc.health.v1.HealthCheckResponse.ServingStatus;
import io.grpc.health.v1.HealthGrpc;

@SpringBootTest
class GrpcHealthIntegrationTest {
    @Autowired
    HealthTestGrpcServer grpcServer;

    @Autowired
    HealthStatusManager healthStatusManager;

    private ManagedChannel channel;
    private HealthGrpc.HealthBlockingStub healthStub;

    @BeforeEach
    void connect() {
        healthStatusManager.setStatus("", ServingStatus.SERVING);
        healthStatusManager.setStatus(
            "acme.greeting.v1.GreetingService",
            ServingStatus.SERVING);
        healthStatusManager.setStatus(
            "acme.catalog.v1.CatalogService",
            ServingStatus.SERVING);

        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcServer.port())
            .usePlaintext()
            .build();

        healthStub = HealthGrpc.newBlockingStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @Test
    void reportsGreetingServiceAsServing() {
        HealthCheckResponse response = healthStub.check(
            HealthCheckRequest.newBuilder()
                .setService("acme.greeting.v1.GreetingService")
                .build());

        assertEquals(ServingStatus.SERVING, response.getStatus());
    }

    @AfterEach
    void closeChannel() throws InterruptedException {
        if (channel == null) {
            return;
        }
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }
}
~~~

Các kiểu **HealthGrpc**, **HealthCheckRequest** và **HealthCheckResponse** được cung cấp bởi grpc-services/protobuf health API tương ứng với phiên bản gRPC Java. Dùng channel plaintext ở đây chỉ cho test loopback không bật TLS; nếu ứng dụng triển khai health endpoint qua TLS, hãy kiểm thử bằng TLS channel riêng.

## 9. Kiểm thử trạng thái tổng thể và từng service

Gửi Check với service name rỗng để đọc trạng thái tổng thể:

~~~java
HealthCheckResponse overall = healthStub.check(
    HealthCheckRequest.getDefaultInstance());

assertEquals(ServingStatus.SERVING, overall.getStatus());
~~~

Sau đó kiểm tra service cụ thể bằng full service name. Test nên xác nhận Catalog có thể NOT_SERVING trong khi Greeting vẫn SERVING nếu policy cho phép hoạt động độc lập.

Khi service name không tồn tại, Check thường kết thúc bằng **NOT_FOUND**. Kiểm thử trường hợp này giúp phát hiện lỗi typo hoặc khác biệt package/service name giữa client và server.

Không chỉ assert status ở thời điểm khởi động. Hãy thay đổi health manager trong test, gọi Check lại và xác nhận status mới được phản ánh.

## 10. Kiểm thử Watch khi trạng thái thay đổi

Watch là server-streaming RPC. Client nhận trạng thái ban đầu rồi nhận các cập nhật khi server thay đổi trạng thái:

Đặt Catalog ở SERVING trước khi mở Watch. Test cần đợi callback trạng thái đầu tiên trước khi chuyển sang NOT_SERVING để không tạo race giữa đăng ký Watch và thay đổi status.

~~~java
healthStatusManager.setStatus(
    "acme.catalog.v1.CatalogService",
    ServingStatus.SERVING);

List<ServingStatus> updates = new CopyOnWriteArrayList<>();
CountDownLatch initial = new CountDownLatch(1);
CountDownLatch changed = new CountDownLatch(1);

HealthGrpc.newStub(channel).watch(
    HealthCheckRequest.newBuilder()
        .setService("acme.catalog.v1.CatalogService")
        .build(),
    new StreamObserver<>() {
        @Override
        public void onNext(HealthCheckResponse response) {
            updates.add(response.getStatus());
            if (updates.size() == 1) {
                initial.countDown();
            }
            if (response.getStatus() == ServingStatus.NOT_SERVING) {
                changed.countDown();
            }
        }

        @Override
        public void onError(Throwable error) {
            // Lưu lỗi để assertion ở test thread.
        }

        @Override
        public void onCompleted() {
            // Watch thường tiếp tục cho tới khi call bị hủy.
        }
    });

assertTrue(initial.await(2, TimeUnit.SECONDS));
healthStatusManager.setStatus(
    "acme.catalog.v1.CatalogService",
    ServingStatus.NOT_SERVING);

assertTrue(changed.await(3, TimeUnit.SECONDS));
assertEquals(
    List.of(ServingStatus.SERVING, ServingStatus.NOT_SERVING),
    updates);
~~~

Ví dụ giả định trạng thái ban đầu là SERVING và không có lần chuyển trạng thái trung gian. Trong test hoàn chỉnh, lưu lỗi từ onError vào AtomicReference và assert lỗi đó ở test thread. Không dựa vào Thread.sleep() để đoán thời điểm Watch đã đăng ký.

Watch thường là stream dài hạn. Sau khi assertion xong, hủy call hoặc channel để không giữ observer và executor qua test khác. Khi service name không được biết, Watch có thể gửi trạng thái SERVICE_UNKNOWN; test cần phân biệt trường hợp này với Check trả NOT_FOUND.

## 11. Readiness không đồng nghĩa liveness

**Readiness** trả lời câu hỏi: instance có nên nhận traffic mới không? **Liveness** trả lời: tiến trình có còn sống và có khả năng tiếp tục chạy không?

Một ứng dụng có thể NOT_SERVING vì database tạm thời không khả dụng nhưng tiến trình vẫn sống và có thể phục hồi. Nếu liveness cũng thất bại theo cùng điều kiện, hệ thống điều phối có thể restart liên tục, làm tình trạng dependency càng nặng hơn.

Health service gRPC thường được dùng làm readiness signal cho client/load balancer. Liveness của process có thể được kiểm tra bằng probe riêng phù hợp nền tảng triển khai. Đừng dùng một trạng thái duy nhất cho mọi mục tiêu.

## 12. Client health checking và load balancing

Một số gRPC client hỗ trợ health checking tích hợp qua service config. Khi bật tính năng này, client có thể mở Watch cho service được cấu hình và chỉ coi backend là healthy khi nhận trạng thái SERVING. Cách này hữu ích với load balancing vì backend không sẵn sàng có thể bị loại khỏi lựa chọn gửi RPC.

Client health checking phụ thuộc implementation, phiên bản và service config; không phải mọi client đều tự động gọi Health.Check. Nếu client không bật health checking, health service vẫn hữu ích cho probe/monitoring bên ngoài nhưng không tự ngăn client gửi request tới backend NOT_SERVING.

Kiểm thử tích hợp nên xác nhận đúng hành vi của client đang dùng: cấu hình health check service name, Watch được mở khi kết nối và backend NOT_SERVING không được chọn theo policy. Không suy luận rằng chỉ cần đăng ký health service là mọi client tự động tuân theo trạng thái.

## 13. Health check phải nhanh và an toàn

Không thực hiện truy vấn database mới hoặc gọi nhiều dependency đồng bộ trong từng lần Check nếu việc đó có thể làm health endpoint chậm và tạo tải khi hệ thống đang quá tải.

Thường nên cập nhật readiness state khi dependency/lifecycle thay đổi, sau đó để Check đọc trạng thái đã được quản lý. Nếu cần kiểm tra dependency định kỳ, dùng health contributor/probe có timeout và cache kết quả phù hợp; tránh tạo vòng lặp health check gọi lại chính health endpoint.

Health endpoint cũng có thể tiết lộ topology hoặc tình trạng nội bộ. Chỉ công khai mức thông tin cần thiết, giới hạn quyền truy cập nếu policy yêu cầu và không đưa exception, hostname nội bộ hoặc credential vào health response.

## 14. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Quên đăng ký Health service | Client nhận UNIMPLEMENTED | Thêm health service vào server do starter/fixture quản lý. |
| Dùng tên Java class thay full Protobuf service name | Check service cụ thể không tìm thấy | Dùng package + service name chính xác. |
| Chỉ cập nhật status tổng thể | Client hỏi service cụ thể không có trạng thái đúng | Đặt status cho từng service cần theo dõi. |
| Đánh dấu SERVING trước khi dependency sẵn sàng | Traffic tới instance chưa thể xử lý | Cập nhật sau readiness gate. |
| Đánh dấu toàn server NOT_SERVING khi một service lỗi không liên quan | Loại bỏ traffic của service vẫn khỏe | Định nghĩa policy theo service và dependency dùng chung. |
| Coi readiness là liveness | Restart loop khi dependency tạm thời lỗi | Tách probe nhận traffic khỏi probe sống của process. |
| Không đóng Watch trong test | Giữ stream và tài nguyên giữa các test | Hủy call/channel sau assertion. |
| Dùng Thread.sleep để đợi Watch | Test flaky | Dùng latch/condition có timeout. |
| Giả định client tự dùng health service | Backend NOT_SERVING vẫn có thể nhận RPC | Bật và kiểm thử client health checking nếu cần. |

## 15. Bài tập thực hành

Tạo integration test cho server có GreetingService và CatalogService:

1. Đăng ký health service chuẩn cùng hai service nghiệp vụ.
2. Khi context sẵn sàng, đặt trạng thái tổng thể và cả hai service là SERVING.
3. Gọi Check cho chuỗi rỗng, Greeting và Catalog; xác nhận status.
4. Đổi Catalog sang NOT_SERVING và xác nhận Check phản ánh trạng thái mới.
5. Xác nhận Greeting vẫn SERVING nếu policy cho phép độc lập.
6. Mở Watch cho Catalog, nhận trạng thái ban đầu và cập nhật sau khi status thay đổi.
7. Gọi Check với tên service không tồn tại và xác nhận NOT_FOUND; kiểm thử Watch cho SERVICE_UNKNOWN nếu implementation hỗ trợ theo protocol.
8. Khi shutdown bắt đầu, chuyển trạng thái cần thiết sang NOT_SERVING và xác nhận client không còn coi instance là sẵn sàng.
9. Đóng Watch, channel và server theo lifecycle của Spring test context.

**Tiêu chí hoàn thành:** health service được gọi qua transport thật, status tổng thể và theo service chính xác, Watch phát cập nhật, unknown service được xử lý đúng và readiness thay đổi theo lifecycle.

## 16. Ghi nhớ

- gRPC Health Checking Protocol cung cấp unary Check và server-streaming Watch.
- Service name phải là full Protobuf service name; chuỗi rỗng đại diện trạng thái tổng thể.
- Đăng ký health service cùng server và quản lý status bằng HealthStatusManager hoặc cơ chế tương đương của starter.
- SERVING chỉ nên được đặt sau khi service thực sự sẵn sàng; chuyển NOT_SERVING khi không nên nhận traffic.
- Check cho service không biết thường trả NOT_FOUND; Watch có trạng thái SERVICE_UNKNOWN.
- Readiness khác liveness; dependency lỗi không nhất thiết có nghĩa process cần restart.
- Client health checking không tự bật ở mọi client; cấu hình và kiểm thử theo implementation thực tế.
- Watch là stream dài hạn; test phải hủy call/channel và dùng synchronization có timeout.

Kiểm thử health check giúp xác nhận client và load balancer nhận đúng tín hiệu readiness của từng service, phát hiện trạng thái thay đổi và loại instance không sẵn sàng khỏi luồng xử lý.
