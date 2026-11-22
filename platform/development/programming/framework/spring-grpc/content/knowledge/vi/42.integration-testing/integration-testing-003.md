# Kiểm thử nhiều service cùng server

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cách một gRPC server đăng ký và định tuyến nhiều service trên cùng endpoint.
- Khai báo nhiều service Protobuf có tên đầy đủ khác nhau và triển khai thành Spring bean.
- Khởi động một server test chứa nhiều BindableService.
- Tạo một ManagedChannel và nhiều generated stub để gọi từng service.
- Kiểm tra service routing, status độc lập, interceptor và trạng thái dùng chung.
- Quản lý lifecycle, port động và test isolation khi nhiều service cùng chạy.

## 1. Nhiều service có thể dùng chung một gRPC server

Một gRPC server không bắt buộc chỉ đăng ký một service. Server có thể expose nhiều service definition trên cùng host và port. Mỗi service được định danh bằng tên đầy đủ trong Protobuf, gồm package và service name; method được định tuyến theo full method name.

Ví dụ, cùng một server có thể cung cấp:

- **demo.v1.GreetingService** để xử lý lời chào.
- **demo.v1.CatalogService** để tra cứu sản phẩm.
- **demo.v1.OrderService** để quản lý đơn hàng.

Client tạo stub riêng cho từng service nhưng có thể dùng chung một ManagedChannel vì tất cả service nằm trên cùng endpoint. gRPC phân luồng request tới handler tương ứng dựa trên method descriptor.

Trong **SPRING_GRPC**, các service implementation thường là Spring bean để dùng chung repository, cấu hình, interceptor và service nghiệp vụ. Integration test cần xác nhận tất cả service mong đợi được đăng ký vào cùng server và gọi được qua transport thật.

## 2. Định nghĩa các service trong Protobuf

Ví dụ hai service độc lập trong cùng package:

~~~proto
syntax = "proto3";

package demo.v1;

option java_package = "com.example.grpc.generated";
option java_multiple_files = true;

message GreetRequest {
  string name = 1;
}

message GreetReply {
  string message = 1;
}

message FindItemRequest {
  string item_id = 1;
}

message FindItemReply {
  string item_id = 1;
  string description = 2;
}

service GreetingService {
  rpc Greet(GreetRequest) returns (GreetReply);
}

service CatalogService {
  rpc FindItem(FindItemRequest) returns (FindItemReply);
}
~~~

Code generation tạo các base class và stub riêng, chẳng hạn **GreetingServiceGrpc** và **CatalogServiceGrpc**. Hai service có package chung nhưng full service name khác nhau, nên server có thể định tuyến từng RPC chính xác.

Không đổi tên package/service tùy tiện giữa client và server đã phát hành. Tên đầy đủ của service và method là một phần của đường dẫn RPC; thay đổi chúng có thể làm client cũ không còn gọi được method.

## 3. Mỗi service là một BindableService riêng

Các generated base class phía server triển khai BindableService. Service implementation kế thừa base class tương ứng:

~~~java
final class GreetingServiceImpl
        extends GreetingServiceGrpc.GreetingServiceImplBase {

    @Override
    public void greet(
            GreetRequest request,
            StreamObserver<GreetReply> responseObserver) {
        GreetReply reply = GreetReply.newBuilder()
            .setMessage("Hello, " + request.getName())
            .build();

        responseObserver.onNext(reply);
        responseObserver.onCompleted();
    }
}
~~~

Service thứ hai triển khai CatalogServiceGrpc.CatalogServiceImplBase:

~~~java
final class CatalogServiceImpl
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void findItem(
            FindItemRequest request,
            StreamObserver<FindItemReply> responseObserver) {
        if (!"item-1".equals(request.getItemId())) {
            responseObserver.onError(
                Status.NOT_FOUND
                    .withDescription("Item not found")
                    .asRuntimeException());
            return;
        }

        responseObserver.onNext(
            FindItemReply.newBuilder()
                .setItemId("item-1")
                .setDescription("Keyboard")
                .build());
        responseObserver.onCompleted();
    }
}
~~~

Hai implementation là hai service handler độc lập. Mỗi method chịu trách nhiệm phát đúng một terminal event cho response observer của call đó.

## 4. Đăng ký nhiều service vào cùng server

Ở gRPC Java thuần, ServerBuilder nhận nhiều lời gọi addService(...) trước khi build:

~~~java
Server server = ServerBuilder.forPort(0)
    .addService(greetingService)
    .addService(catalogService)
    .build()
    .start();
~~~

Server chỉ bind một port nhưng đăng ký cả hai service. Khi client gọi GreetingService/Greet, gRPC dispatch tới GreetingServiceImpl; khi gọi CatalogService/FindItem, request được chuyển tới CatalogServiceImpl.

Trong Spring, hãy để component scan/configuration tạo từng implementation thành bean. Nếu starter tự phát hiện và đăng ký các service bean, không gọi addService thêm lần nữa trên một server thủ công. Cần một chủ sở hữu server duy nhất và một cơ chế đăng ký nhất quán.

## 5. Test fixture chứa nhiều service

Khi không dùng starter auto-start server, có thể tạo fixture Spring quản lý lifecycle và nhận danh sách service:

~~~java
final class MultiServiceGrpcServer implements SmartLifecycle {
    private final List<BindableService> services;
    private volatile Server server;

    MultiServiceGrpcServer(List<BindableService> services) {
        this.services = List.copyOf(services);
    }

    @Override
    public synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }

        ServerBuilder<?> builder = ServerBuilder.forPort(0);
        services.forEach(builder::addService);

        try {
            server = builder.build().start();
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot start multi-service gRPC test server", ex);
        }
    }

    int port() {
        Server current = server;
        if (current == null || current.isShutdown()) {
            throw new IllegalStateException("gRPC server is not running");
        }
        return current.getPort();
    }

    @Override
    public synchronized void stop() {
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

    @Override
    public boolean isRunning() {
        Server current = server;
        return current != null && !current.isShutdown();
    }
}
~~~

Fixture bind port 0 để hệ điều hành cấp port động. port() chỉ trả giá trị sau khi server đã start. stop() đóng server graceful, chờ trong thời hạn hữu hạn rồi mới buộc dừng nếu cần.

Đây là test fixture tự quản lý server. Nếu Spring gRPC starter đã quản lý server, hãy đăng ký cả hai service bean vào server đó và lấy port từ API/test support của starter. Không vừa dùng auto-configuration vừa tạo fixture thứ hai chứa cùng service.

## 6. Đăng ký service bean trong Spring test context

Test configuration có thể tạo server từ hai service bean cụ thể:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class MultiServiceGrpcTestConfiguration {
    @Bean
    MultiServiceGrpcServer multiServiceGrpcServer(
            GreetingServiceImpl greeting,
            CatalogServiceImpl catalog) {
        return new MultiServiceGrpcServer(
            List.of(greeting, catalog));
    }
}
~~~

Trong ứng dụng thực, các implementation thường được component scan hoặc cấu hình production tạo sẵn. Test chỉ cần import cấu hình fixture và để Spring inject đúng bean. Dùng kiểu tham số cụ thể giúp tránh mơ hồ nếu context có nhiều BindableService.

Không đăng ký cùng một service definition hai lần. Các service cần có full name khác nhau; nếu có hai implementation cạnh tranh cho cùng một full service name, cấu hình server không còn rõ ràng và việc khởi động có thể thất bại.

## 7. Một channel, nhiều stub

Sau khi Spring context đã start server, test tạo một channel tới port của server rồi tạo stub cho từng service:

~~~java
@SpringBootTest
@Import(MultiServiceGrpcTestConfiguration.class)
class MultiServiceIntegrationTest {
    @Autowired
    MultiServiceGrpcServer grpcServer;

    private ManagedChannel channel;
    private GreetingServiceGrpc.GreetingServiceBlockingStub greetingStub;
    private CatalogServiceGrpc.CatalogServiceBlockingStub catalogStub;

    @BeforeEach
    void connect() {
        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcServer.port())
            .usePlaintext()
            .build();

        greetingStub =
            GreetingServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);
        catalogStub =
            CatalogServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);
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

Một ManagedChannel có thể phục vụ nhiều stub và nhiều RPC đồng thời. Stub chứa method/service descriptor; channel quản lý kết nối tới endpoint. Không cần mở một channel mới cho mỗi service nếu chúng cùng nằm trên một server.

## 8. Kiểm tra cả hai service qua cùng endpoint

Test nên gọi ít nhất một method của từng service:

~~~java
@Test
void routesCallsToBothServicesOnTheSameServer() {
    GreetReply greeting = greetingStub.greet(
        GreetRequest.newBuilder()
            .setName("An")
            .build());

    FindItemReply item = catalogStub.findItem(
        FindItemRequest.newBuilder()
            .setItemId("item-1")
            .build());

    assertEquals("Hello, An", greeting.getMessage());
    assertEquals("Keyboard", item.getDescription());
}
~~~

Một test như vậy xác nhận client dùng cùng channel nhưng request được dispatch tới đúng hai service handler. Nếu chỉ kiểm tra server đã start hoặc channel đã kết nối, chưa đủ chứng minh mọi service đều được đăng ký.

Nên có assertion cho dữ liệu trả về có ý nghĩa nghiệp vụ để phát hiện trường hợp stub trỏ nhầm service hoặc implementation không được inject đúng dependency.

## 9. Lỗi ở một service không được làm hỏng service khác

Mỗi RPC có status riêng. Ví dụ Catalog có thể trả NOT_FOUND trong khi Greeting vẫn hoạt động:

~~~java
@Test
void failureInOneServiceDoesNotStopTheOtherService() {
    StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> catalogStub.findItem(
            FindItemRequest.newBuilder()
                .setItemId("missing")
                .build()));

    assertEquals(Status.Code.NOT_FOUND,
        error.getStatus().getCode());

    GreetReply reply = greetingStub.greet(
        GreetRequest.newBuilder()
            .setName("Binh")
            .build());

    assertEquals("Hello, Binh", reply.getMessage());
}
~~~

Một lỗi nghiệp vụ của một method không tự động dừng toàn bộ server. Tuy nhiên, nếu một service làm cạn executor, heap hoặc connection pool dùng chung, service khác vẫn có thể bị ảnh hưởng. Integration test tải hoặc fault-injection có thể kiểm tra giới hạn tài nguyên dùng chung này.

## 10. Interceptor và metadata trên nhiều service

Một server có thể áp dụng interceptor ở phạm vi server hoặc service tùy API và starter đang dùng. Khi có nhiều service, kiểm tra rõ:

- Authentication/authorization có áp dụng cho mọi service cần bảo vệ không?
- Metadata như trace ID và correlation ID có được đọc nhất quán không?
- Interceptor toàn server có làm thay đổi status hoặc deadline ngoài dự kiến không?
- Service công khai và service nội bộ có cần policy khác nhau không?

Test nên gọi từng service với metadata hợp lệ và không hợp lệ để xác nhận policy. Đừng suy ra rằng một service đã được bảo vệ thì service khác tự động có cùng interceptor nếu cấu hình đăng ký không bảo đảm điều đó.

Nếu starter tự đăng ký service bean, hãy kiểm tra cơ chế gắn interceptor mà starter hỗ trợ. Không thêm interceptor bằng cách tạo server thứ hai chỉ để test.

## 11. Cô lập state giữa các service

Các service cùng server có thể chia sẻ dependency như repository, cache hoặc executor, nhưng không nên chia sẻ mutable state theo request một cách vô tình.

- Service implementation Spring singleton phải an toàn khi nhiều RPC chạy đồng thời.
- State của một call nên nằm trong object riêng của call.
- Dữ liệu test của Greeting không nên ảnh hưởng kết quả Catalog, trừ khi đó là hành vi tích hợp được thiết kế.
- Nếu nhiều service cùng ghi database, test nên dùng dữ liệu có namespace hoặc transaction/test fixture phù hợp.

Chạy hai service trên cùng server không có nghĩa chúng chạy tuần tự. gRPC có thể xử lý nhiều call đồng thời; shared dependency cần có concurrency semantics đúng.

## 12. Test nhiều service chạy đồng thời

Ngoài gọi tuần tự, nên kiểm tra hai service có thể phục vụ call đồng thời qua cùng channel:

~~~java
CompletableFuture<GreetReply> greetingCall =
    CompletableFuture.supplyAsync(() ->
        greetingStub.greet(
            GreetRequest.newBuilder().setName("Concurrent").build()));

CompletableFuture<FindItemReply> catalogCall =
    CompletableFuture.supplyAsync(() ->
        catalogStub.findItem(
            FindItemRequest.newBuilder().setItemId("item-1").build()));

assertEquals("Hello, Concurrent", greetingCall.get(3, TimeUnit.SECONDS)
    .getMessage());
assertEquals("Keyboard", catalogCall.get(3, TimeUnit.SECONDS)
    .getDescription());
~~~

Trong test thực tế, nên dùng executor test có giới hạn và dọn executor sau khi chạy. Đặt timeout cho cả future và RPC để lỗi không treo suite. Nếu service có state hoặc tài nguyên dùng chung, thêm test xác nhận không có race hoặc rò dữ liệu giữa hai method.

## 13. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Khởi động một server cho mỗi service | Nhiều port và cấu hình không phản ánh topology cần test | Đăng ký nhiều BindableService vào cùng server. |
| Chỉ gọi một service trong test | Service còn lại có thể chưa được đăng ký | Gọi method của từng service qua channel thật. |
| Tạo một channel riêng cho mỗi stub | Tăng connection/thread không cần thiết | Dùng chung channel khi cùng endpoint. |
| Đăng ký trùng service definition | Server registry không rõ ràng hoặc khởi động thất bại | Dùng full service name duy nhất và một registration owner. |
| Chỉ test service routing thành công | Bỏ sót status, interceptor và policy | Kiểm tra cả lỗi và metadata trên từng service. |
| Cho rằng lỗi một RPC dừng server | Xử lý retry/health sai | Phân biệt status của call với lifecycle server. |
| Dùng chung mutable state không đồng bộ | Race giữa RPC thuộc service khác nhau | Bảo vệ shared dependency và cô lập call state. |
| Vừa auto-register vừa addService thủ công | Đăng ký lặp hoặc có hai server | Chọn một server lifecycle/registration owner. |

## 14. Bài tập thực hành

Tạo một Spring gRPC server có hai service:

1. Định nghĩa GreetingService và CatalogService trong Protobuf với full service name khác nhau.
2. Tạo hai implementation Spring bean.
3. Đăng ký cả hai vào cùng server, dùng port động trong test.
4. Tạo một ManagedChannel và hai generated blocking stub.
5. Gọi một method thành công của mỗi service và kiểm tra response.
6. Gọi Catalog với ID không tồn tại, xác nhận NOT_FOUND, rồi gọi Greeting thành công trên cùng channel.
7. Gọi hai service đồng thời để kiểm tra shared dependency và concurrency.
8. Kiểm tra interceptor/metadata áp dụng đúng cho cả hai service.

**Tiêu chí hoàn thành:** hai service được dispatch qua cùng server/port, client dùng chung channel, status của từng RPC độc lập và Spring quản lý đúng lifecycle của server cùng service bean.

## 15. Ghi nhớ

- Một gRPC server có thể đăng ký nhiều BindableService trên cùng endpoint.
- Full service name trong Protobuf giúp gRPC định tuyến request tới đúng service/method.
- Mỗi service có generated base class và stub riêng; nhiều stub có thể dùng chung ManagedChannel.
- Integration test phải gọi từng service qua server thật để xác nhận đăng ký và routing.
- Lỗi của một RPC không tự động dừng server hoặc service khác.
- Kiểm tra interceptor, metadata và authorization trên từng service.
- Service bean Spring singleton và dependency dùng chung phải an toàn khi nhiều RPC chạy đồng thời.
- Chỉ có một chủ sở hữu server lifecycle và registration; tránh auto-registration trùng với fixture thủ công.

Kiểm thử nhiều service cùng server giúp xác nhận topology gRPC thực tế, service routing, status độc lập và cách Spring quản lý các implementation dùng chung một endpoint.
