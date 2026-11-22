# Kết nối client test tới port động

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao integration test nên dùng port động thay vì cố định một port.
- Lấy port thực tế sau khi gRPC server đã bind thành công.
- Tạo **ManagedChannel** và stub trỏ tới địa chỉ server trong Spring test context.
- Đặt deadline cho RPC và đóng channel đúng vòng đời test.
- Phân biệt port của HTTP server Spring Boot với port của gRPC server.
- Tổ chức test chạy song song, context cache và TLS mà không phụ thuộc môi trường.

## 1. Vì sao client test cần port động?

Một integration test qua TCP cần client biết địa chỉ và port mà gRPC server đang lắng nghe. Nếu tất cả test đều dùng port cố định như **9090**, test có thể thất bại khi port đang được tiến trình khác sử dụng, khi nhiều test chạy song song hoặc khi hai application context cùng khởi động.

Giải pháp là để hệ điều hành cấp một port trống khi server bind. Với gRPC Java, truyền **0** vào **ServerBuilder.forPort(0)**. Sau khi server start thành công, đọc port thực tế bằng **Server.getPort()** rồi tạo client channel tới port đó.

Trong **SPRING_GRPC**, server thường được khởi động cùng Spring test context để service implementation, interceptor và dependency được inject như ứng dụng thật. Client test phải kết nối tới đúng gRPC listener của context đó. Port của web server Spring Boot, nếu có, là một listener khác và không thể dùng thay port gRPC.

## 2. Quy trình kết nối

~~~mermaid
flowchart TD
  A["Spring tạo test ApplicationContext"] --> B["gRPC server khởi động với port 0"]
  B --> C["Server bind thành công"]
  C --> D["Đọc port thực tế"]
  D --> E["Tạo ManagedChannel tới 127.0.0.1:port"]
  E --> F["Tạo stub và đặt deadline"]
  F --> G["Gọi RPC và kiểm tra kết quả"]
  G --> H["Shutdown channel"]
  H --> I["Spring đóng context và server"]
~~~

Thứ tự rất quan trọng: chỉ tạo channel sau khi server đã bind xong. Không đọc port trước **start()** và không tự đoán port từ cấu hình. Nếu server được Spring quản lý, hãy lấy port từ bean/lifecycle accessor của server sau khi context refresh hoàn tất.

## 3. Bind port 0 và đọc port thực tế

Với fixture tự quản lý server bằng gRPC Java:

~~~java
Server server = ServerBuilder.forPort(0)
    .addService(greeterService)
    .build()
    .start();

int actualPort = server.getPort();
~~~

**0** là yêu cầu cấp port động, không phải port mà client sẽ dùng. **getPort()** chỉ có ý nghĩa sau khi server start thành công. Nếu server không bind được, quá trình khởi động phải thất bại và test context không nên tiếp tục tạo channel.

Nếu Spring gRPC starter tự khởi động server, hãy bật port động bằng cấu hình mà đúng starter/phiên bản hỗ trợ và lấy port thực tế qua API test support hoặc server lifecycle bean của nó. Không giả định mọi starter đều dùng cùng property. Cũng không mặc định **@LocalServerPort** trả về port gRPC; annotation đó thường gắn với web server của Spring Boot.

Không dùng cách mở **ServerSocket(0)**, đọc port rồi đóng socket trước khi gRPC server bind. Port có thể bị tiến trình khác chiếm giữa hai thao tác. Hãy để chính gRPC server bind port 0.

## 4. Cung cấp port từ server fixture cho test

Một fixture Spring có thể expose port sau khi server đã start:

~~~java
final class TestGrpcServer implements SmartLifecycle {
    private final BindableService service;
    private volatile Server server;

    TestGrpcServer(BindableService service) {
        this.service = service;
    }

    @Override
    public synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }
        try {
            server = ServerBuilder.forPort(0)
                .addService(service)
                .build()
                .start();
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot start gRPC test server", ex);
        }
    }

    int port() {
        Server current = server;
        if (current == null || current.isShutdown()) {
            throw new IllegalStateException("gRPC test server is not running");
        }
        return current.getPort();
    }

    @Override
    public synchronized void stop() {
        Server current = server;
        server = null;
        if (current != null) {
            current.shutdown();
        }
    }

    @Override
    public boolean isRunning() {
        return server != null && !server.isShutdown();
    }
}
~~~

Đây là fixture tối giản để minh họa việc publish port. Trong test thật, **stop()** nên đợi **awaitTermination** trong một khoảng thời gian hữu hạn rồi mới gọi **shutdownNow()** nếu cần; đồng thời giữ nguyên trạng thái interrupt nếu thread bị ngắt.

Đăng ký fixture bằng **@TestConfiguration** và để Spring inject service bean. Nếu starter đã sở hữu server, không tạo fixture thứ hai: expose port từ server do starter quản lý. Mỗi context chỉ nên có một chủ sở hữu server rõ ràng.

## 5. Tạo ManagedChannel tới port động

Khi context đã refresh và server đang chạy, test có thể inject port provider rồi tạo channel:

~~~java
@SpringBootTest
class GreeterIntegrationTest {
    @Autowired
    TestGrpcServer grpcServer;

    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;

    @BeforeEach
    void connectClient() {
        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcServer.port())
            .usePlaintext()
            .build();

        stub = GreeterGrpc.newBlockingStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);
    }
}
~~~

**@BeforeEach** chạy sau khi Spring đã tạo và refresh context, vì vậy lifecycle bean đã được start. Dùng **127.0.0.1** giúp tránh một số khác biệt phân giải **localhost** thành IPv4 hoặc IPv6 giữa các máy CI.

**usePlaintext()** chỉ dành cho test TCP cục bộ khi server không bật TLS. Nếu test xác minh TLS, channel phải được cấu hình trust certificate và transport security tương ứng.

## 6. Tạo stub và gọi RPC

Stub được tạo từ channel. Blocking stub phù hợp với test unary đơn giản:

~~~java
@Test
void connectsToTheDynamicallyBoundServer() {
    HelloReply reply = stub.sayHello(
        HelloRequest.newBuilder()
            .setName("Mai")
            .build());

    assertEquals("Hello, Mai", reply.getMessage());
}
~~~

Với streaming RPC, dùng async stub và observer:

~~~java
List<PriceUpdate> received = new CopyOnWriteArrayList<>();
CountDownLatch completed = new CountDownLatch(1);

GreeterGrpc.GreeterStub asyncStub =
    GreeterGrpc.newStub(channel)
        .withDeadlineAfter(3, TimeUnit.SECONDS);

asyncStub.watchPrices(
    SubscribeRequest.getDefaultInstance(),
    new StreamObserver<>() {
        @Override
        public void onNext(PriceUpdate update) {
            received.add(update);
        }

        @Override
        public void onError(Throwable error) {
            completed.countDown();
        }

        @Override
        public void onCompleted() {
            completed.countDown();
        }
    });

assertTrue(completed.await(4, TimeUnit.SECONDS));
~~~

Ví dụ minh họa cách đợi terminal callback; test thực tế nên giữ riêng lỗi nhận được để assert status, số lượng và thứ tự message. Timeout của latch nên dài hơn deadline RPC một khoảng nhỏ để test có thời gian quan sát kết quả call.

## 7. Deadline giúp test không treo

Mỗi RPC trong integration test nên có deadline hữu hạn:

~~~java
GreeterGrpc.GreeterBlockingStub boundedStub =
    GreeterGrpc.newBlockingStub(channel)
        .withDeadlineAfter(2, TimeUnit.SECONDS);
~~~

Nếu server không start, client không kết nối được hoặc handler bị treo, deadline giúp call kết thúc thay vì giữ test suite vô thời hạn. Chọn thời gian phù hợp với CI; deadline quá ngắn có thể tạo flaky test trên máy tải cao.

Deadline của RPC không thay thế timeout chờ trong test framework. Với async streaming, cần cả deadline cho call và timeout cho **CountDownLatch**/future của test.

## 8. Đóng channel đúng vòng đời

Client channel là tài nguyên của test, không phải của server fixture. Đóng channel sau mỗi test method:

~~~java
@AfterEach
void closeClient() throws InterruptedException {
    if (channel == null) {
        return;
    }

    channel.shutdown();
    if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
        channel.shutdownNow();
    }
}
~~~

**shutdown()** yêu cầu đóng graceful; **awaitTermination()** đợi call/channel kết thúc trong thời hạn. Chỉ dùng **shutdownNow()** khi không thể kết thúc đúng hạn. Không đóng channel dùng chung khi một RPC khác vẫn đang chạy.

Server thuộc Spring context nên Spring/starter đóng server khi context bị đóng. Không gọi **server.shutdownNow()** từ từng test method nếu server được chia sẻ qua context cache; việc đó làm các test sau kết nối tới server đã dừng.

## 9. Vì sao không dùng port web của Spring Boot?

Một ứng dụng có thể đồng thời mở:

- HTTP server cho REST/Actuator.
- gRPC server cho HTTP/2 gRPC.
- Management server hoặc listener phụ khác.

**@LocalServerPort** thường cung cấp port của web server, không phải port của gRPC server. Dùng nhầm port có thể tạo lỗi handshake/protocol hoặc kết nối tới ứng dụng HTTP thay vì gRPC.

Hãy lấy port từ đúng gRPC server bean hoặc test support của starter. Nếu starter không expose port trực tiếp, tạo một abstraction test-only để đọc địa chỉ server sau khi lifecycle start, thay vì suy luận từ port web.

## 10. Port động với context cache và test chạy song song

Spring Test có thể cache application context giữa nhiều method hoặc class có cùng cấu hình. Khi đó server thường tiếp tục chạy cùng context; mỗi test chỉ tạo và đóng channel riêng.

Các nguyên tắc:

- Không giả định port mới được cấp cho mỗi **@Test**; port gắn với vòng đời server/context.
- Không đóng server từ **@AfterEach** nếu server thuộc context dùng chung.
- Nếu có hai context độc lập, mỗi context có thể bind port động riêng.
- Test song song cần state/service data isolation; port động chỉ tránh xung đột socket.
- Không chia sẻ một channel đã shutdown giữa các test.

Nếu một test làm context không thể tái sử dụng, **@DirtiesContext** có thể yêu cầu Spring loại context khỏi cache và đóng lifecycle bean. Chỉ dùng khi cần thiết vì context khởi động lại làm suite chậm.

## 11. Khi nào dùng DynamicPropertySource?

**@DynamicPropertySource** hữu ích khi port hoặc endpoint được tạo bên ngoài Spring context, chẳng hạn Testcontainers khởi động một dịch vụ phụ trước khi context cần đọc property.

Với gRPC server được tạo bên trong chính Spring context, không thể đọc port từ bean server trong **@DynamicPropertySource** trước khi context khởi tạo bean đó. Trường hợp này nên inject port provider rồi tạo channel sau refresh, ví dụ trong **@BeforeEach**.

Nếu starter yêu cầu port qua property, có thể cấu hình giá trị **0** trước khi context khởi động; sau đó vẫn cần một API/accessor để lấy port thực tế đã bind. Property cấu hình **0** không phải địa chỉ để client kết nối.

## 12. TCP test, in-process test và TLS

| Kiểu test | Kiểm tra được | Không chứng minh được |
| --- | --- | --- |
| **In-process** | Service dispatch, stub, một phần interceptor và logic gRPC | TCP socket, bind port, network HTTP/2 và TLS handshake. |
| **TCP với port động** | Server startup, bind, channel kết nối và HTTP/2 transport thực | TLS nếu test đang dùng plaintext. |
| **TCP với TLS** | Certificate, trust chain, hostname verification và handshake | Không tự kiểm tra mọi cấu hình production nếu cert/test trust khác nhau. |

Không dùng in-process test làm bằng chứng duy nhất rằng server production có thể mở port và nhận kết nối mạng. Một nhóm test TCP nhỏ với port động giúp kiểm tra đúng đường transport.

Khi test TLS, dùng certificate test có hostname/SAN phù hợp và cấu hình channel trust certificate đó. Không tắt certificate verification để làm test pass; điều đó bỏ qua chính hành vi cần kiểm tra.

## 13. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng port cố định | Xung đột khi test song song hoặc port đang bận | Bind port 0 và lấy port thực tế. |
| Kết nối trước khi server start | Connection refused hoặc test flaky | Tạo channel sau khi context refresh/lifecycle start. |
| Dùng **@LocalServerPort** cho gRPC | Kết nối nhầm web listener | Lấy port từ gRPC server/starter accessor. |
| Đọc port từ cấu hình **0** | Client cố kết nối port 0 | Đọc port đã bind từ server sau start. |
| Mở rồi đóng **ServerSocket** để dò port | Race chiếm port trước khi gRPC bind | Để server bind trực tiếp port 0. |
| Không shutdown channel | Rò thread/connection và làm suite treo | Đóng channel trong teardown. |
| Đóng server trong mỗi **@AfterEach** | Phá server dùng chung qua context cache | Để Spring lifecycle đóng server. |
| Dùng plaintext để kết luận TLS đúng | Không kiểm tra certificate/handshake | Có test TCP TLS riêng. |
| Chỉ kiểm tra in-process | Bỏ sót lỗi bind/transport | Bổ sung integration test TCP. |

## 14. Bài tập thực hành

Tạo integration test cho service **Greeter**:

1. Cho Spring khởi động gRPC server với port động (**0**) hoặc dùng port accessor của starter.
2. Sau khi context refresh, lấy port thực tế từ server lifecycle bean.
3. Tạo **ManagedChannel** tới **127.0.0.1** và port đó.
4. Tạo blocking stub có deadline và gọi unary RPC.
5. Tạo async stub để kiểm tra một server-streaming RPC, đợi terminal callback bằng latch có timeout.
6. Đóng channel trong teardown; để Spring đóng server khi context kết thúc.
7. Chạy test song song và xác nhận không có port collision.
8. Thêm một test TLS nếu ứng dụng triển khai gRPC qua TLS.

**Tiêu chí hoàn thành:** client test kết nối đúng gRPC listener bằng port thực tế, RPC có deadline, channel được đóng đúng lúc và server vẫn tuân theo lifecycle của Spring context.

## 15. Ghi nhớ

- Dùng port **0** để hệ điều hành cấp port cho gRPC server; đọc port thực tế sau khi server start.
- Tạo **ManagedChannel** sau khi Spring context refresh và server đã bind.
- Lấy port từ gRPC server hoặc starter test support; **@LocalServerPort** thường là port web.
- Tạo stub từ channel và đặt deadline cho từng RPC.
- Test sở hữu client channel và phải shutdown; Spring/starter sở hữu server lifecycle.
- Context cache có thể giữ server sống qua nhiều test method; không dừng server dùng chung từ teardown từng method.
- **@DynamicPropertySource** phù hợp với endpoint có trước context; server được tạo trong context cần port accessor sau refresh.
- In-process test không thay thế TCP/HTTP2 test; TLS cần test certificate và trust configuration riêng.

Kết nối client test tới port động giúp integration test Spring gRPC không phụ thuộc port cố định, chạy ổn định khi song song và kiểm tra được server lifecycle cùng transport thật.
